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
    La partición train/test es CRONOLÓGICA, no aleatoria. Con series temporales,
    un split aleatorio deja horas del futuro en el entrenamiento y produce
    métricas infladas que no se sostienen en producción.

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
    """No hay suficiente historial para entrenar."""


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
    importancias: dict[str, float] = field(default_factory=dict)

    @property
    def es_util(self) -> bool:
        """
        Un modelo que no supera a "predecir siempre la clase mayoritaria" no
        aporta nada, por alta que sea su exactitud.
        """
        return self.mejora_sobre_base > 0.01


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
    etiqueta: str = "⚠️ Estimación experimental — no es una alerta oficial"

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
                f"El modelo no supera a la referencia estadística con los datos "
                f"disponibles, así que esta probabilidad ({pct:.0f}%) no es "
                f"informativa todavía."
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
    from sklearn.ensemble import RandomForestClassifier
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
            f"Ningún día del historial supera un índice de calor de {umbral_ic} °C, "
            "así que no hay nada que aprender a distinguir. Baja el umbral o "
            "amplía el periodo."
        )
    if n_riesgo == len(y):
        raise DatosInsuficientes(
            f"Todos los días superan {umbral_ic} °C de índice de calor: sin "
            "variación no hay clasificación posible."
        )

    # Partición cronológica: entrenar con el pasado, evaluar con el futuro.
    corte = int(len(X) * (1 - proporcion_prueba))
    X_tr, X_te = X[:corte], X[corte:]
    y_tr, y_te = y[:corte], y[corte:]

    if len(np.unique(y_tr)) < 2:
        raise DatosInsuficientes(
            "El periodo de entrenamiento tiene una sola clase. Amplía el historial."
        )

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=6,          # acotado: con ~700 muestras un árbol profundo memoriza
        min_samples_leaf=5,
        class_weight="balanced",  # los días de riesgo suelen ser minoría
        random_state=semilla,
        n_jobs=-1,
    )
    clf.fit(X_tr, y_tr)

    y_pred = clf.predict(X_te)
    exactitud = float((y_pred == y_te).mean())

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_te, y_pred, average="binary", zero_division=0,
    )

    # Referencia: acertar siempre con la clase más frecuente del test.
    tasa_base = float(y_te.mean()) if len(y_te) else 0.0
    exactitud_base = max(tasa_base, 1 - tasa_base)

    metricas = Metricas(
        n_entrenamiento=len(X_tr),
        n_prueba=len(X_te),
        exactitud=round(exactitud, 3),
        precision=round(float(precision), 3),
        recall=round(float(recall), 3),
        f1=round(float(f1), 3),
        tasa_base=round(tasa_base, 3),
        mejora_sobre_base=round(exactitud - exactitud_base, 3),
        importancias={
            nombre: round(float(imp), 3)
            for nombre, imp in sorted(
                zip(NOMBRES_FEATURES, clf.feature_importances_),
                key=lambda kv: kv[1], reverse=True,
            )
        },
    )

    logger.info(
        "Modelo entrenado: %d train / %d test, exactitud=%.3f (base %.3f), F1=%.3f",
        metricas.n_entrenamiento, metricas.n_prueba,
        metricas.exactitud, exactitud_base, metricas.f1,
    )

    modelo = Modelo(
        clasificador=clf,
        metricas=metricas,
        umbral_ic=umbral_ic,
        entrenado_en=datetime.now(timezone.utc),
        dias_usados=len(dias),
    )
    return modelo, dias


def evaluar_riesgo(lugar_id: str = DEFAULT_LUGAR) -> tuple[Prediccion, Metricas]:
    """Entrena y predice de una vez. Es lo que consume la API."""
    modelo, dias = entrenar(lugar_id)
    return modelo.predecir_manana(dias), modelo.metricas
