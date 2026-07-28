"""
tests/test_risk.py — Tests del predictor de riesgo de calor (Fase 4).

Sin red y sin depender de la BD real: los datos se generan de forma
determinista, así que el entrenamiento es reproducible (criterio de aceptación
del informe: "Test del entrenamiento con datos de fixture (reproducible)").
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

import risk
import storage
from sources.base import Lectura


# ── Índice de calor ──────────────────────────────────────────────────────────

def test_indice_calor_contra_tabla_de_la_noaa():
    """
    Valores de referencia de la tabla publicada por la NOAA.
    90 °F (32.2 °C) con 80% de humedad ≈ 113 °F ≈ 45 °C.
    """
    assert risk.indice_calor(32.2, 80) == pytest.approx(45.0, abs=1.5)
    # 95 °F (35 °C) con 60% ≈ 114 °F ≈ 45.6 °C
    assert risk.indice_calor(35.0, 60) == pytest.approx(45.6, abs=1.5)


def test_con_calor_humedo_el_indice_supera_la_temperatura():
    assert risk.indice_calor(32, 85) > 32


def test_con_temperatura_suave_el_indice_se_parece_a_la_temperatura():
    """Por debajo de ~27 °C la fórmula de Rothfusz no aplica."""
    assert risk.indice_calor(22, 50) == pytest.approx(22, abs=3)


def test_a_igual_temperatura_mas_humedad_da_mas_indice():
    assert risk.indice_calor(33, 90) > risk.indice_calor(33, 40)


# ── Generación de datos sintéticos reproducibles ─────────────────────────────

def _sembrar_historial(
    db: str,
    dias: int = 400,
    lugar_id: str = "santa-marta",
    con_senal: bool = True,
) -> None:
    """
    Crea un historial horario determinista con estacionalidad.

    `con_senal=True` hace que el calor se agrupe (días calurosos seguidos de
    días calurosos), que es lo que el modelo debe poder aprender.
    """
    inicio = datetime(2024, 1, 1, tzinfo=timezone.utc)
    lecturas: list[Lectura] = []

    for d in range(dias):
        fecha = inicio + timedelta(days=d)
        estacion = math.sin(2 * math.pi * d / 365.25)

        # Sin señal: el calor oscila rápido y no es predecible desde ayer.
        base = 28 + 4 * estacion if con_senal else 28 + 4 * math.sin(d * 2.7)

        for hora in range(24):
            ciclo = math.sin(math.pi * (hora - 6) / 12)
            temp = base + 4 * max(ciclo, -0.5)
            humedad = max(45.0, min(95.0, 75 - 12 * ciclo))
            ts = fecha + timedelta(hours=hora)

            lecturas.append(Lectura(
                valor=round(temp, 2), unidad="°C", metrica="temperatura",
                fuente=risk.FUENTE_CLIMA, procedencia="local", lugar_id=lugar_id,
                estacion_nombre="sintético", ts=ts,
            ))
            lecturas.append(Lectura(
                valor=round(humedad, 2), unidad="%", metrica="humedad",
                fuente=risk.FUENTE_CLIMA, procedencia="local", lugar_id=lugar_id,
                estacion_nombre="sintético", ts=ts,
            ))

    storage.guardar_muchas(lecturas, db)


@pytest.fixture
def db_con_historial(tmp_path, monkeypatch):
    db = str(tmp_path / "risk.db")
    storage.inicializar_bd(db)
    monkeypatch.setattr(storage, "_db_path", lambda: db)
    _sembrar_historial(db)
    return db


# ── Carga y agregación ───────────────────────────────────────────────────────

def test_agrega_horas_en_dias(db_con_historial):
    dias = risk._cargar_series("santa-marta")
    assert len(dias) >= 390
    assert all(d.temp_max >= d.temp_min for d in dias)


def test_descarta_dias_con_pocas_horas(tmp_path, monkeypatch):
    """Un día con 3 lecturas daría un máximo falso: debe ignorarse."""
    db = str(tmp_path / "parcial.db")
    storage.inicializar_bd(db)
    monkeypatch.setattr(storage, "_db_path", lambda: db)
    _sembrar_historial(db, dias=60)

    # Día extra con solo 3 horas
    suelto = datetime(2025, 6, 1, tzinfo=timezone.utc)
    storage.guardar_muchas([
        Lectura(valor=45.0, unidad="°C", metrica="temperatura",
                fuente=risk.FUENTE_CLIMA, procedencia="local",
                lugar_id="santa-marta", estacion_nombre="x",
                ts=suelto + timedelta(hours=h))
        for h in range(3)
    ] + [
        Lectura(valor=90.0, unidad="%", metrica="humedad",
                fuente=risk.FUENTE_CLIMA, procedencia="local",
                lugar_id="santa-marta", estacion_nombre="x",
                ts=suelto + timedelta(hours=h))
        for h in range(3)
    ], db)

    fechas = {d.fecha.date() for d in risk._cargar_series("santa-marta")}
    assert suelto.date() not in fechas


def test_sin_historial_lanza_error_con_instrucciones(tmp_path, monkeypatch):
    db = str(tmp_path / "vacia.db")
    storage.inicializar_bd(db)
    monkeypatch.setattr(storage, "_db_path", lambda: db)

    with pytest.raises(risk.DatosInsuficientes) as exc:
        risk._cargar_series("santa-marta")
    assert "backfill" in str(exc.value)


def test_historial_corto_lanza_error(tmp_path, monkeypatch):
    db = str(tmp_path / "corta.db")
    storage.inicializar_bd(db)
    monkeypatch.setattr(storage, "_db_path", lambda: db)
    _sembrar_historial(db, dias=5)

    with pytest.raises(risk.DatosInsuficientes):
        risk._cargar_series("santa-marta")


# ── Features ─────────────────────────────────────────────────────────────────

def test_features_tienen_la_forma_declarada(db_con_historial):
    dias = risk._cargar_series("santa-marta")
    X, y, fechas = risk.construir_features(dias)

    assert X.shape[1] == len(risk.NOMBRES_FEATURES)
    assert len(X) == len(y) == len(fechas)
    assert set(y.tolist()) <= {0, 1}


def test_features_saltan_huecos_en_la_serie(db_con_historial):
    """Con días no consecutivos los rezagos no tienen sentido."""
    dias = risk._cargar_series("santa-marta")
    # Quita un día del medio para abrir un hueco
    con_hueco = dias[:50] + dias[51:100]
    X, _, _ = risk.construir_features(con_hueco)

    # Menos muestras que si fueran todos consecutivos
    assert len(X) < len(con_hueco) - 3


def test_la_estacionalidad_es_circular(db_con_historial):
    """
    Diciembre 31 y enero 1 deben quedar cerca en el espacio de features, no en
    extremos opuestos: por eso se codifica con seno y coseno.
    """
    dias = risk._cargar_series("santa-marta")
    X, _, fechas = risk.construir_features(dias)

    i_dic = next(i for i, f in enumerate(fechas) if f.month == 12 and f.day == 30)
    i_ene = next(i for i, f in enumerate(fechas) if f.month == 1 and f.day == 3)

    sin_dic, cos_dic = X[i_dic][-2], X[i_dic][-1]
    sin_ene, cos_ene = X[i_ene][-2], X[i_ene][-1]
    distancia = math.hypot(sin_dic - sin_ene, cos_dic - cos_ene)
    assert distancia < 0.3, "fin y principio de año deberían quedar cerca"


# ── Entrenamiento ────────────────────────────────────────────────────────────

def test_entrena_y_es_reproducible(db_con_historial):
    """Misma semilla y mismos datos ⇒ mismas métricas."""
    m1, _ = risk.entrenar("santa-marta", umbral_ic=risk.UMBRAL_RIESGO_IC, semilla=7)
    m2, _ = risk.entrenar("santa-marta", umbral_ic=risk.UMBRAL_RIESGO_IC, semilla=7)

    assert m1.metricas.exactitud == m2.metricas.exactitud
    assert m1.metricas.f1 == m2.metricas.f1


def test_la_particion_es_cronologica(db_con_historial):
    """
    Con series temporales, una partición aleatoria filtra el futuro al
    entrenamiento e infla las métricas.
    """
    modelo, dias = risk.entrenar("santa-marta")
    X, _, _ = risk.construir_features(dias)

    esperado_train = int(len(X) * 0.8)
    assert modelo.metricas.n_entrenamiento == esperado_train
    assert modelo.metricas.n_prueba == len(X) - esperado_train


def test_reporta_la_tasa_base(db_con_historial):
    """
    Sin la referencia, una exactitud del 90% puede ser peor que decir siempre
    "no hay riesgo". El modelo debe exponerla.
    """
    modelo, _ = risk.entrenar("santa-marta")
    assert 0.0 <= modelo.metricas.tasa_base <= 1.0
    assert isinstance(modelo.metricas.es_util, bool)


def test_umbral_imposible_lanza_error_claro(db_con_historial):
    """Si ningún día supera el umbral no hay dos clases que distinguir."""
    with pytest.raises(risk.DatosInsuficientes) as exc:
        risk.entrenar("santa-marta", umbral_ic=200.0)
    assert "umbral" in str(exc.value).lower() or "ningún" in str(exc.value).lower()


def test_umbral_trivial_lanza_error(db_con_historial):
    """Si todos los días son de riesgo, tampoco hay clasificación posible."""
    with pytest.raises(risk.DatosInsuficientes):
        risk.entrenar("santa-marta", umbral_ic=-50.0)


def test_las_importancias_suman_uno(db_con_historial):
    modelo, _ = risk.entrenar("santa-marta")
    assert sum(modelo.metricas.importancias.values()) == pytest.approx(1.0, abs=0.02)
    assert set(modelo.metricas.importancias) == set(risk.NOMBRES_FEATURES)


# ── Predicción ───────────────────────────────────────────────────────────────

def test_prediccion_en_rango_valido(db_con_historial):
    modelo, dias = risk.entrenar("santa-marta")
    pred = modelo.predecir_manana(dias)

    assert 0.0 <= pred.probabilidad <= 1.0
    assert pred.nivel in ("bajo", "moderado", "alto")


def test_la_prediccion_apunta_al_dia_siguiente(db_con_historial):
    modelo, dias = risk.entrenar("santa-marta")
    pred = modelo.predecir_manana(dias)
    assert pred.fecha_objetivo.date() == (dias[-1].fecha + timedelta(days=1)).date()


def test_la_etiqueta_experimental_viaja_con_el_dato(db_con_historial):
    """
    "Etiqueta 'estimación experimental' visible siempre junto al resultado"
    (§6, Fase 4). Va en el objeto, no depende de que la UI la recuerde.
    """
    modelo, dias = risk.entrenar("santa-marta")
    pred = modelo.predecir_manana(dias)

    assert "experimental" in pred.etiqueta.lower()
    assert "no es una alerta oficial" in pred.etiqueta.lower()


def test_avisa_cuando_el_modelo_no_es_util(db_con_historial):
    """Si el modelo no supera la referencia, el mensaje debe decirlo."""
    modelo, dias = risk.entrenar("santa-marta")
    pred = modelo.predecir_manana(dias)
    pred_inutil = risk.Prediccion(
        probabilidad=pred.probabilidad,
        fecha_objetivo=pred.fecha_objetivo,
        ic_max_hoy=pred.ic_max_hoy,
        umbral_ic=pred.umbral_ic,
        modelo_es_util=False,
    )
    assert "no es informativa" in pred_inutil.mensaje


def test_predecir_sin_dias_suficientes_lanza(db_con_historial):
    modelo, dias = risk.entrenar("santa-marta")
    with pytest.raises(risk.DatosInsuficientes):
        modelo.predecir_manana(dias[:2])


def test_evaluar_riesgo_devuelve_prediccion_y_metricas(db_con_historial):
    pred, metricas = risk.evaluar_riesgo("santa-marta")
    assert isinstance(pred, risk.Prediccion)
    assert isinstance(metricas, risk.Metricas)
