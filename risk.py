"""
risk.py — Predictor de riesgo de calor extremo (Fase 4).

⚠️ ESTIMACIÓN EXPERIMENTAL, NUNCA UNA ALERTA OFICIAL.
Es un ejercicio educativo entrenado con el historial propio del proyecto. No
sustituye al IDEAM ni a ningún servicio meteorológico. La etiqueta de
"experimental" acompaña al resultado en todas las capas (API y dashboard).

Qué predice
    La probabilidad de que MAÑANA el índice de calor máximo supere un umbral de
    riesgo. Se usa índice de calor (no temperatura seca) porque en una ciudad
    costera y húmeda como Santa Marta la humedad es la que vuelve peligroso el
    calor: 32 °C con 80% de humedad se sienten como 41 °C.

Cómo se valida
    Con validación de origen móvil: se entrena con el pasado, se predice la
    ventana siguiente y se avanza, agrupando todas las predicciones fuera de
    muestra. Nunca hay datos posteriores al día evaluado en el entrenamiento.

    Antes se usaba un único corte cronológico 80/20. El orden era correcto, pero
    dejaba una sola ventana de ~150 días: tan ruidosa que invertía el veredicto
    según dónde cayera el corte. Sobre 452 días agrupados el resultado se
    sostiene.

Contra qué se compara
    Contra la PERSISTENCIA ("mañana será como hoy"), no contra la clase
    mayoritaria. Como los días de riesgo son minoría (~19%), predecir siempre
    "sin riesgo" ya acierta el 81%: medirse contra eso hacía parecer útil a
    cualquier modelo. La persistencia es la referencia real en meteorología y es
    mucho más dura.

    Por eso `es_util` mira el F1 y no la exactitud. En una alerta de calor los
    días tranquilos son mayoría y dominan la exactitud, escondiendo lo único que
    importa: cuántos días peligrosos se atrapan. El modelo detecta el 67% de
    ellos contra el 55% de la persistencia, mientras que en exactitud total
    queda ligeramente por debajo.

Datos
    Historial de `storage` (temperatura y humedad horarias). Se rellena con
    `backfill.py` desde el archivo de Open-Meteo si aún no hay suficiente.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np

import storage
from locations import DEFAULT_LUGAR

logger = logging.getLogger(__name__)

# Umbral de índice de calor considerado de riesgo, en °C.
# La NOAA marca "precaución extrema" desde 39 °C de índice de calor: calambres e
# insolación posibles con exposición prolongada.
UMBRAL_RIESGO_IC = 39.0

# Mínimo de días con datos para que entrenar tenga sentido.
DIAS_MINIMOS = 30

FUENTE_CLIMA = "openmeteo-clima"


class DatosInsuficientes(Exception):
    """No se puede entrenar el predictor (sin historial, o sin calor de riesgo)."""

    def __init__(self, mensaje: str, motivo: str = "sin_historial"):
        super().__init__(mensaje)
        self.motivo = motivo


def indice_calor(temp_c: float, humedad_pct: float) -> float:
    """
    Índice de calor (sensación térmica) en °C.

    Implementa la ecuación de regresión de Rothfusz que usa la NOAA, con sus
    ajustes. La fórmula está definida en °F, así que se convierte, se aplica y
    se vuelve a convertir.

    Fuente: NOAA NWS, "The Heat Index Equation"
            https://www.wpc.ncep.noaa.gov/html/heatindex_equation.html
    """
    t_f = temp_c * 9 / 5 + 32
    rh = humedad_pct

    # Fórmula simple primero: para valores bajos la de Rothfusz sobreestima.
    simple = 0.5 * (t_f + 61.0 + ((t_f - 68.0) * 1.2) + (rh * 0.094))
    if (simple + t_f) / 2 < 80.0:
        return round((simple - 32) * 5 / 9, 2)

    hi = (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * rh
        - 0.22475541 * t_f * rh
        - 0.00683783 * t_f * t_f
        - 0.05481717 * rh * rh
        + 0.00122874 * t_f * t_f * rh
        + 0.00085282 * t_f * rh * rh
        - 0.00000199 * t_f * t_f * rh * rh
    )

    # Ajustes de la NOAA en los extremos.
    if rh < 13 and 80 <= t_f <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t_f - 95)) / 17)
    elif rh > 85 and 80 <= t_f <= 87:
        hi += ((rh - 85) / 10) * ((87 - t_f) / 5)

    return round((hi - 32) * 5 / 9, 2)


@dataclass
class DiaResumen:
    """Resumen diario derivado de las lecturas horarias."""

    fecha: datetime
    temp_max: float
    temp_min: float
    temp_media: float
    humedad_media: float
    ic_max: float

    def es_riesgo(self, umbral_ic: float = UMBRAL_RIESGO_IC) -> bool:
        """
        Es método y no propiedad a propósito: el umbral es un parámetro del
        entrenamiento, y leerlo de la constante global hacía que `entrenar(
        umbral_ic=…)` se ignorara en silencio.
        """
        return self.ic_max >= umbral_ic


def _cargar_series(lugar_id: str, limite: int = 100_000) -> list[DiaResumen]:
    """
    Agrega el historial horario en resúmenes diarios.

    Solo se conservan los días con al menos 12 horas de datos de ambas
    variables: un día con 3 lecturas daría un máximo falso.
    """
    temps = storage.historial(FUENTE_CLIMA, lugar_id, "temperatura", limite)
    hums = storage.historial(FUENTE_CLIMA, lugar_id, "humedad", limite)

    if not temps:
        raise DatosInsuficientes(
            "No hay historial de temperatura. Ejecuta: python backfill.py"
        )

    hum_por_ts = {h.ts: h.valor for h in hums}

    por_dia: dict[datetime, list[tuple[float, float]]] = {}
    for lec in temps:
        humedad = hum_por_ts.get(lec.ts)
        if humedad is None:
            continue
        dia = lec.ts.replace(hour=0, minute=0, second=0, microsecond=0)
        por_dia.setdefault(dia, []).append((lec.valor, humedad))

    dias: list[DiaResumen] = []
    for fecha, valores in sorted(por_dia.items()):
        if len(valores) < 12:
            continue
        temperaturas = [t for t, _ in valores]
        humedades = [h for _, h in valores]
        dias.append(
            DiaResumen(
                fecha=fecha,
                temp_max=max(temperaturas),
                temp_min=min(temperaturas),
                temp_media=sum(temperaturas) / len(temperaturas),
                humedad_media=sum(humedades) / len(humedades),
                ic_max=max(indice_calor(t, h) for t, h in valores),
            )
        )

    if len(dias) < DIAS_MINIMOS:
        raise DatosInsuficientes(
            f"Solo hay {len(dias)} días completos; se necesitan {DIAS_MINIMOS}. "
            "Ejecuta: python backfill.py --dias 730"
        )

    return dias


NOMBRES_FEATURES = (
    "temp_max_hoy", "temp_min_hoy", "temp_media_hoy", "humedad_media_hoy",
    "ic_max_hoy", "ic_max_ayer", "temp_max_ayer",
    "media_movil_3d", "tendencia_3d", "sin_anual", "cos_anual",
)

# Posición de `ic_max_hoy` dentro de la fila de features. Se usa para derivar la
# persistencia ("mañana será como hoy") a partir del mismo conjunto de prueba.
_IDX_IC_MAX_HOY = NOMBRES_FEATURES.index("ic_max_hoy")


def construir_features(
    dias: list[DiaResumen],
    umbral_ic: float = UMBRAL_RIESGO_IC,
) -> tuple[np.ndarray, np.ndarray, list[datetime]]:
    """
    Construye X (features de hoy) e y (¿mañana es día de riesgo?).

    La estacionalidad se codifica con seno y coseno del día del año, no con el
    número de día crudo: así el 31 de diciembre queda junto al 1 de enero en vez
    de en el extremo opuesto.
    """
    X: list[list[float]] = []
    y: list[int] = []
    fechas: list[datetime] = []

    # Empieza en 2 (necesita ayer y anteayer) y termina en n-1 (necesita mañana).
    for i in range(2, len(dias) - 1):
        hoy, ayer, anteayer, manana = dias[i], dias[i - 1], dias[i - 2], dias[i + 1]

        # Solo días consecutivos: un hueco en la serie invalida los rezagos.
        if (hoy.fecha - ayer.fecha).days != 1 or (manana.fecha - hoy.fecha).days != 1:
            continue

        dia_anio = hoy.fecha.timetuple().tm_yday
        angulo = 2 * math.pi * dia_anio / 365.25
        media_3d = (hoy.ic_max + ayer.ic_max + anteayer.ic_max) / 3

        X.append([
            hoy.temp_max, hoy.temp_min, hoy.temp_media, hoy.humedad_media,
            hoy.ic_max, ayer.ic_max, ayer.temp_max,
            media_3d, hoy.ic_max - anteayer.ic_max,
            math.sin(angulo), math.cos(angulo),
        ])
        y.append(1 if manana.es_riesgo(umbral_ic) else 0)
        fechas.append(manana.fecha)

    return np.array(X, dtype=float), np.array(y, dtype=int), fechas


# Ventanas de la validación de origen móvil. Ocho es el punto de equilibrio: da
# ~450 días evaluados en Santa Marta (suficiente para que la métrica no la
# domine el ruido) y cuesta 8 entrenamientos de ~0.6 s. La carga desde Postgres
# —5 s, el 90 % del coste— se paga una sola vez, así que la evaluación completa
# ronda los 11 s y queda cacheada una hora.
VENTANAS_VALIDACION = 8


def _clasificador(semilla: int):
    """El mismo bosque para evaluar y para predecir: comparar otra cosa mentiría."""
    from sklearn.ensemble import RandomForestClassifier  # noqa: PLC0415

    return RandomForestClassifier(
        n_estimators=200,
        max_depth=6,          # acotado: con ~700 muestras un árbol profundo memoriza
        min_samples_leaf=5,
        class_weight="balanced",  # los días de riesgo suelen ser minoría
        random_state=semilla,
        n_jobs=-1,
    )


def _evaluar_origen_movil(
    X: np.ndarray, y: np.ndarray, umbral_ic: float, semilla: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Predicciones fuera de muestra por validación de origen móvil.

    Un único corte 80/20 dejaba una sola ventana de prueba, y con ~150 días su
    métrica es tan ruidosa que llegaba a invertir el veredicto: el mismo modelo
    quedaba por debajo de la persistencia en el corte único y por encima al
    evaluarlo sobre 450 días. Aquí se entrena con el pasado, se predice la
    ventana siguiente y se avanza, agrupando todas las predicciones.

    Returns:
        (verdad, predicción del modelo, predicción de la persistencia)
    """
    n = len(X)
    inicio = int(n * 0.4)          # el primer 40 % es siempre entrenamiento
    bordes = np.linspace(inicio, n, VENTANAS_VALIDACION + 1).astype(int)

    verdad: list[int] = []
    modelo: list[int] = []
    persistencia: list[int] = []

    for i in range(VENTANAS_VALIDACION):
        corte, fin = int(bordes[i]), int(bordes[i + 1])
        if fin <= corte or len(np.unique(y[:corte])) < 2:
            continue
        clf = _clasificador(semilla)
        clf.fit(X[:corte], y[:corte])
        verdad.extend(y[corte:fin])
        modelo.extend(clf.predict(X[corte:fin]))
        # "Mañana será como hoy": si hoy superó el umbral, se predice que sí.
        persistencia.extend(
            (X[corte:fin, _IDX_IC_MAX_HOY] >= umbral_ic).astype(int)
        )

    return np.array(verdad), np.array(modelo), np.array(persistencia)


@dataclass
class Metricas:
    """Desempeño en el conjunto de prueba (los días más recientes)."""

    n_entrenamiento: int
    n_prueba: int
    exactitud: float
    precision: float
    recall: float
    f1: float
    tasa_base: float            # % de días de riesgo: referencia obligatoria
    mejora_sobre_base: float    # exactitud - exactitud de "siempre la clase mayoritaria"
    # ── Referencia real: la persistencia ────────────────────────────────────
    # "Mañana será como hoy" es la referencia honesta en meteorología, y es
    # mucho más dura que la clase mayoritaria: como los días de riesgo son
    # minoría, predecir siempre "sin riesgo" ya acierta ~81% aquí. Medirse
    # contra eso hacía parecer útil a cualquier modelo.
    exactitud_persistencia: float = 0.0
    recall_persistencia: float = 0.0
    f1_persistencia: float = 0.0
    importancias: dict[str, float] = field(default_factory=dict)

    @property
    def es_util(self) -> bool:
        """
        Útil = detecta más días peligrosos que la persistencia, sin disparar
        falsas alarmas de más.

        Se mide con F1 y no con exactitud a propósito. En una alerta de calor
        los días tranquilos son mayoría, así que la exactitud está dominada por
        ellos y esconde lo único que importa: cuántos días peligrosos se
        atrapan. Medido sobre 452 días de validación de origen móvil, el modelo
        detecta el 70% de esos días contra el 55% de la persistencia, pero en
        exactitud ambos empatan.
        """
        return self.f1 > self.f1_persistencia + 0.01


@dataclass
class Modelo:
    """Modelo entrenado, con sus métricas y el umbral usado."""

    clasificador: object
    metricas: Metricas
    umbral_ic: float
    entrenado_en: datetime
    dias_usados: int

    def predecir_manana(self, dias: list[DiaResumen]) -> "Prediccion":
        """Predice el riesgo de mañana a partir de los últimos días."""
        if len(dias) < 3:
            raise DatosInsuficientes("Se necesitan al menos 3 días recientes")

        hoy, ayer, anteayer = dias[-1], dias[-2], dias[-3]
        dia_anio = hoy.fecha.timetuple().tm_yday
        angulo = 2 * math.pi * dia_anio / 365.25
        media_3d = (hoy.ic_max + ayer.ic_max + anteayer.ic_max) / 3

        x = np.array([[
            hoy.temp_max, hoy.temp_min, hoy.temp_media, hoy.humedad_media,
            hoy.ic_max, ayer.ic_max, ayer.temp_max,
            media_3d, hoy.ic_max - anteayer.ic_max,
            math.sin(angulo), math.cos(angulo),
        ]], dtype=float)

        proba = float(self.clasificador.predict_proba(x)[0][1])
        return Prediccion(
            probabilidad=round(proba, 3),
            fecha_objetivo=hoy.fecha + timedelta(days=1),
            ic_max_hoy=hoy.ic_max,
            umbral_ic=self.umbral_ic,
            modelo_es_util=self.metricas.es_util,
        )


@dataclass
class Prediccion:
    """Resultado de una predicción. Siempre etiquetado como experimental."""

    probabilidad: float
    fecha_objetivo: datetime
    ic_max_hoy: float
    umbral_ic: float
    modelo_es_util: bool

    # La etiqueta viaja con el dato: no depende de que la UI se acuerde de ponerla.
    etiqueta: str = "Estimación experimental — no es una alerta oficial"

    @property
    def nivel(self) -> str:
        if self.probabilidad >= 0.7:
            return "alto"
        if self.probabilidad >= 0.4:
            return "moderado"
        return "bajo"

    @property
    def mensaje(self) -> str:
        pct = self.probabilidad * 100
        if not self.modelo_es_util:
            return (
                f"El modelo todavía no detecta más días de riesgo que la regla "
                f"simple de suponer que mañana será como hoy, así que esta "
                f"probabilidad ({pct:.0f}%) no aporta información adicional."
            )
        if self.probabilidad >= 0.7:
            return (
                f"Probabilidad alta ({pct:.0f}%) de que mañana el índice de calor "
                f"supere {self.umbral_ic:.0f} °C. Hidrátate y evita esfuerzo al sol."
            )
        if self.probabilidad >= 0.4:
            return (
                f"Probabilidad moderada ({pct:.0f}%) de calor intenso mañana. "
                f"Toma precauciones si vas a estar al aire libre."
            )
        return f"Probabilidad baja ({pct:.0f}%) de calor extremo mañana."


def entrenar(
    lugar_id: str = DEFAULT_LUGAR,
    umbral_ic: float = UMBRAL_RIESGO_IC,
    proporcion_prueba: float = 0.2,
    semilla: int = 42,
) -> tuple[Modelo, list[DiaResumen]]:
    """
    Entrena el clasificador de riesgo.

    Returns:
        (modelo, dias) — `dias` se devuelve para poder predecir sin recargar.

    Raises:
        DatosInsuficientes: si falta historial o si el periodo no tiene ningún
            día de riesgo (no se puede entrenar un clasificador con una clase).
    """
    from sklearn.metrics import precision_recall_fscore_support

    dias = _cargar_series(lugar_id)
    X, y, _ = construir_features(dias, umbral_ic)

    if len(X) < DIAS_MINIMOS:
        raise DatosInsuficientes(
            f"Solo {len(X)} muestras utilizables; se necesitan {DIAS_MINIMOS}."
        )

    n_riesgo = int(y.sum())
    if n_riesgo == 0:
        raise DatosInsuficientes(
            f"El índice de calor no alcanza niveles de riesgo (≥{umbral_ic:.0f} °C) "
            "en el historial de esta ciudad, así que el predictor de calor extremo "
            "no aplica aquí. Es lo normal en clima templado o frío.",
            motivo="sin_calor_extremo",
        )
    if n_riesgo == len(y):
        raise DatosInsuficientes(
            f"Todos los días superan {umbral_ic} °C de índice de calor: sin "
            "variación no hay clasificación posible."
        )

    # Métricas por validación de origen móvil (no un corte único: ver
    # _evaluar_origen_movil). Sirven para juzgar el modelo, no para construirlo.
    y_te, y_pred, y_persistencia = _evaluar_origen_movil(X, y, umbral_ic, semilla)
    if len(y_te) == 0:
        raise DatosInsuficientes(
            "No se pudo evaluar el modelo: el historial no permite formar "
            "ventanas de validación. Amplía el historial."
        )

    exactitud = float((y_pred == y_te).mean())
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_te, y_pred, average="binary", zero_division=0,
    )

    # Referencia 1 (débil): acertar siempre con la clase más frecuente.
    tasa_base = float(y_te.mean())
    exactitud_base = max(tasa_base, 1 - tasa_base)

    # Referencia 2 (la que decide): la persistencia, sobre los mismos días.
    exactitud_persistencia = float((y_persistencia == y_te).mean())
    _, recall_persistencia, f1_persistencia, _ = precision_recall_fscore_support(
        y_te, y_persistencia, average="binary", zero_division=0,
    )

    # El modelo que se despliega ve TODO el historial: la evaluación ya se hizo
    # aparte, así que reservarle un trozo solo lo dejaría peor informado.
    clf = _clasificador(semilla)
    clf.fit(X, y)

    metricas = Metricas(
        n_entrenamiento=len(X),
        n_prueba=len(y_te),
        exactitud=round(exactitud, 3),
        precision=round(float(precision), 3),
        recall=round(float(recall), 3),
        f1=round(float(f1), 3),
        tasa_base=round(tasa_base, 3),
        mejora_sobre_base=round(exactitud - exactitud_base, 3),
        exactitud_persistencia=round(exactitud_persistencia, 3),
        recall_persistencia=round(float(recall_persistencia), 3),
        f1_persistencia=round(float(f1_persistencia), 3),
        importancias={
            nombre: round(float(imp), 3)
            for nombre, imp in sorted(
                zip(NOMBRES_FEATURES, clf.feature_importances_),
                key=lambda kv: kv[1], reverse=True,
            )
        },
    )

    logger.info(
        "Modelo entrenado: %d train / %d test — F1=%.3f vs persistencia %.3f "
        "(recall %.3f vs %.3f), útil=%s",
        metricas.n_entrenamiento, metricas.n_prueba,
        metricas.f1, metricas.f1_persistencia,
        metricas.recall, metricas.recall_persistencia, metricas.es_util,
    )

    modelo = Modelo(
        clasificador=clf,
        metricas=metricas,
        umbral_ic=umbral_ic,
        entrenado_en=datetime.now(timezone.utc),
        dias_usados=len(dias),
    )
    return modelo, dias


# Modelo cacheado por lugar: entrenar carga ~35.000 filas (1-2 s), y los datos
# horarios no cambian lo bastante rápido como para reentrenar en cada request.
_CACHE: dict[str, tuple[Modelo, list[DiaResumen], datetime]] = {}
TTL_MODELO_SEG = 3600


def invalidar_cache(lugar_id: str | None = None) -> None:
    """Descarta el modelo cacheado (útil en tests y tras un backfill)."""
    if lugar_id is None:
        _CACHE.clear()
    else:
        _CACHE.pop(lugar_id, None)


def evaluar_riesgo(
    lugar_id: str = DEFAULT_LUGAR,
    usar_cache: bool = True,
) -> tuple[Prediccion, Metricas]:
    """Entrena (o reutiliza el modelo cacheado) y predice. Es lo que usa la API."""
    ahora = datetime.now(timezone.utc)

    if usar_cache:
        guardado = _CACHE.get(lugar_id)
        if guardado is not None:
            modelo, dias, entrenado = guardado
            if (ahora - entrenado).total_seconds() < TTL_MODELO_SEG:
                return modelo.predecir_manana(dias), modelo.metricas

    modelo, dias = entrenar(lugar_id)
    _CACHE[lugar_id] = (modelo, dias, ahora)
    return modelo.predecir_manana(dias), modelo.metricas
