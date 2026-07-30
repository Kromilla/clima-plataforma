"""
tests/test_robustez.py — Regresiones de fallos que ya ocurrieron una vez.

Cada test aquí corresponde a un bug real que se encontró ejecutando el proyecto,
no a un caso hipotético.
"""
from __future__ import annotations

import io
import logging
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import logging_setup
import storage
from sources.base import Lectura

RAIZ = Path(__file__).parent.parent


def _lectura(procedencia: str = "local", minutos: int = 5) -> Lectura:
    return Lectura(
        valor=12.3, unidad="µg/m³", metrica="pm25", fuente="test-fuente",
        procedencia=procedencia, lugar_id="santa-marta", estacion_nombre="Est",
        ts=datetime.now(timezone.utc) - timedelta(minutes=minutos),
    )


# ── Bug: la consola de Windows (cp1252) reventaba con µ, ³, ₂ y emojis ───────

def test_los_scripts_no_revientan_con_caracteres_no_ascii():
    """
    `python collector.py` en una consola cp1252 llenaba la salida de tracebacks
    de "--- Logging error ---" en cada línea con µg/m³ o gCO₂eq/kWh.

    Se lanza un subproceso forzando cp1252 para reproducir la consola de Windows.
    """
    codigo = (
        "import config\n"                       # dispara forzar_utf8_consola()
        "print('PM2.5: 5.5 µg/m³ · 189 gCO₂eq/kWh · 📍 🗄️ ⚠️ →')\n"
    )
    # Sin text=True: el hijo emite UTF-8 y decodificarlo como cp1252 fallaría en
    # el propio test. Se leen bytes y se decodifican explícitamente.
    proc = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True, cwd=RAIZ,
        env={"PYTHONIOENCODING": "cp1252", "PATH": "", "SYSTEMROOT": ""},
    )
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 0, f"el script murió: {stderr[-400:]}"
    assert "UnicodeEncodeError" not in stderr


def test_logging_no_pierde_lineas_con_no_ascii():
    """El logger debe emitir la línea aunque el flujo no soporte el carácter."""
    flujo = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="replace")
    manejador = logging.StreamHandler(flujo)
    logger = logging.getLogger("prueba-encoding")
    logger.handlers = [manejador]
    logger.setLevel(logging.INFO)

    logger.info("valor: 5.5 µg/m³ → 189 gCO₂eq/kWh")

    flujo.flush()
    assert flujo.buffer.getvalue(), "no se escribió nada"


def test_forzar_utf8_es_idempotente():
    """Llamarlo varias veces no debe romper nada (config lo llama al importarse)."""
    logging_setup.forzar_utf8_consola()
    logging_setup.forzar_utf8_consola()


# ── Bug: storage marcaba TODO como "cache" ───────────────────────────────────

def test_storage_conserva_la_procedencia_original(tmp_path):
    """
    `ultimo_valor` forzaba procedencia="cache", así que el dashboard mostraba
    "🗄️ último dato conocido" (que significa "la fuente se cayó") para datos que
    la API acababa de entregar.
    """
    db = str(tmp_path / "t.db")
    storage.inicializar_bd(db)
    storage.guardar(_lectura("local"), db)

    recuperada = storage.ultimo_valor("test-fuente", "santa-marta", "pm25", db)
    assert recuperada.procedencia == "local"
    assert "🗄️" not in recuperada.etiqueta_procedencia()


def test_storage_conserva_procedencia_fallback(tmp_path):
    """Un dato guardado como 'fallback' debe seguir siendo 'fallback' al leerlo."""
    db = str(tmp_path / "t.db")
    storage.inicializar_bd(db)
    storage.guardar(_lectura("fallback"), db)

    assert storage.ultimo_valor("test-fuente", "santa-marta", "pm25", db).procedencia == "fallback"


def test_como_cache_no_muta_el_original():
    original = _lectura("local")
    copia = original.como_cache()

    assert copia.procedencia == "cache"
    assert original.procedencia == "local", "como_cache() no debe mutar el original"
    assert copia.valor == original.valor
    assert copia.ts == original.ts


def test_todos_los_adaptadores_marcan_su_respaldo_como_cache():
    """
    Cada adaptador que sirve el último valor guardado porque su fuente falló
    debe marcarlo con `.como_cache()`. Olvidarlo hace que un dato de respaldo se
    presente como si fuera una lectura en vivo.
    """
    directorio = RAIZ / "sources"
    olvidos = []

    for archivo in directorio.glob("*.py"):
        texto = archivo.read_text(encoding="utf-8")
        for numero, linea in enumerate(texto.splitlines(), 1):
            despojada = linea.strip()
            if despojada == "return lectura_cache":
                olvidos.append(f"{archivo.name}:{numero}")

    assert not olvidos, (
        "estos adaptadores devuelven el respaldo sin marcarlo como caché: "
        + ", ".join(olvidos)
    )


# ── Bug: SQLite bloqueaba lecturas mientras el recolector escribía ───────────

def test_la_bd_usa_wal(tmp_path):
    """
    Con el modo por defecto ('delete'), el dashboard se bloqueaba durante las
    escrituras del recolector.
    """
    db = str(tmp_path / "t.db")
    storage.inicializar_bd(db)

    con = sqlite3.connect(db)
    modo = con.execute("PRAGMA journal_mode").fetchone()[0]
    con.close()
    assert modo.lower() == "wal"


def test_se_puede_leer_mientras_hay_una_escritura_abierta(tmp_path, monkeypatch):
    """Con WAL, un lector no debe fallar porque haya una transacción abierta."""
    db = str(tmp_path / "t.db")
    storage.inicializar_bd(db)
    # Sin esto, cualquier llamada que omita `db_path` escribiría en la BD real
    # del proyecto: ya pasó una vez y dejó filas de prueba en `clima.db`.
    monkeypatch.setattr(storage, "_db_path", lambda: db)
    storage.guardar(_lectura(), db)

    escritor = sqlite3.connect(db, timeout=5)
    escritor.execute("BEGIN")
    escritor.execute(
        "INSERT INTO lecturas (fuente,lugar_id,metrica,valor,unidad,procedencia,estacion,ts)"
        " VALUES ('w','santa-marta','pm25',1,'x','local','y','2026-01-01T00:00:00+00:00')"
    )
    try:
        # El lector no debe quedarse colgado ni lanzar "database is locked".
        assert storage.ultimo_valor("test-fuente", "santa-marta", "pm25", db) is not None
    finally:
        escritor.rollback()
        escritor.close()


# ── Bug: el modelo se reentrenaba en cada request ────────────────────────────

def test_el_modelo_se_cachea(monkeypatch, tmp_path):
    """
    Entrenar carga ~35.000 filas y tarda segundos: hacerlo en cada visita a la
    pestaña de riesgo la volvía lenta y machacaba la BD.
    """
    import risk

    db = str(tmp_path / "risk.db")
    storage.inicializar_bd(db)
    monkeypatch.setattr(storage, "_db_path", lambda: db)

    from tests.test_risk import _sembrar_historial
    _sembrar_historial(db, dias=120)

    risk.invalidar_cache()
    llamadas = {"n": 0}
    entrenar_real = risk.entrenar

    def contar(*args, **kwargs):
        llamadas["n"] += 1
        return entrenar_real(*args, **kwargs)

    monkeypatch.setattr(risk, "entrenar", contar)

    risk.evaluar_riesgo("santa-marta")
    risk.evaluar_riesgo("santa-marta")
    risk.evaluar_riesgo("santa-marta")

    assert llamadas["n"] == 1, f"reentrenó {llamadas['n']} veces en vez de 1"


def test_invalidar_cache_fuerza_reentrenamiento(monkeypatch, tmp_path):
    import risk

    db = str(tmp_path / "risk.db")
    storage.inicializar_bd(db)
    monkeypatch.setattr(storage, "_db_path", lambda: db)

    from tests.test_risk import _sembrar_historial
    _sembrar_historial(db, dias=120)

    risk.invalidar_cache()
    risk.evaluar_riesgo("santa-marta")
    assert "santa-marta" in risk._CACHE

    risk.invalidar_cache("santa-marta")
    assert "santa-marta" not in risk._CACHE


# ── Bug: el recolector guardaba dos veces la misma lectura ───────────────────

# ── Bug: un LIMIT negativo volcaba TODO el historial ─────────────────────────

def _cliente():
    from fastapi.testclient import TestClient

    from api import app
    return TestClient(app)


@pytest.mark.parametrize("limite", [-1, -5, 0, 5001, 10**9])
def test_limite_del_historial_esta_acotado(limite):
    """
    SQLite interpreta `LIMIT -1` como "sin límite": `limite=-1` devolvía las
    ~17.000 filas del historial en una sola respuesta.
    """
    resp = _cliente().get(
        f"/api/clima/historial?fuente=openmeteo-clima&metrica=temperatura&limite={limite}"
    )
    assert resp.status_code == 422, f"limite={limite} debería rechazarse"


def test_limite_valido_se_respeta():
    resp = _cliente().get(
        "/api/clima/historial?fuente=openmeteo-clima&metrica=temperatura&limite=5"
    )
    assert resp.status_code == 200
    assert len(resp.json()) <= 5


@pytest.mark.parametrize("dias", [0, -3, 11, 9999])
def test_dias_de_incendios_acotado(dias):
    assert _cliente().get(f"/api/incendios?dias={dias}").status_code == 422


# ── Bug: se exigía OPENAQ_API_KEY para arrancar ──────────────────────────────

def test_openaq_es_opcional():
    """
    OpenAQ no cubre la costa Caribe y no es la fuente primaria. Exigirla
    obligaba a registrarse en un servicio que el proyecto no usa.
    """
    import config

    fuente = Path(config.__file__).read_text(encoding="utf-8")
    assert '_validar(["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])' in fuente, (
        "OPENAQ_API_KEY no debe estar entre las variables obligatorias"
    )


def test_openaq_sin_clave_no_llama_a_la_api(monkeypatch, tmp_path):
    """Sin clave debe ir directo al caché en vez de pedir un 401 a la API."""
    import sources.openaq as openaq

    db = str(tmp_path / "t.db")
    storage.inicializar_bd(db)
    monkeypatch.setattr(storage, "_db_path", lambda: db)
    monkeypatch.setattr(openaq.cfg, "OPENAQ_API_KEY", None)

    def no_llamar(*args, **kwargs):
        raise AssertionError("no debería consultar la API sin clave")

    monkeypatch.setattr(openaq.requests, "get", no_llamar)

    with pytest.raises(openaq.OpenAQSinDatos, match="OPENAQ_API_KEY"):
        openaq.obtener_ultimo({"_id": "santa-marta", "bbox": (-74.3, 11.0, -73.8, 11.4)})


# ── Bug: el recolector contaba las fuentes sin clave como "ok" ───────────────

def test_las_fuentes_sin_clave_se_reportan_aparte():
    """Informar '4 ok' cuando una fuente ni se intentó es engañoso."""
    import inspect

    import collector

    codigo = inspect.getsource(collector.main)
    assert "omitidas" in codigo, (
        "el resumen debe distinguir las fuentes omitidas de las que sí funcionaron"
    )


# ── Bug: se pedía una semana de datos y se guardaba solo 1 punto ─────────────

def test_xm_guarda_la_serie_completa_no_solo_la_ultima_hora(monkeypatch, tmp_path):
    """
    XM devuelve ~120 horas por llamada y el adaptador se quedaba solo con la
    última, tirando 119. La gráfica del dashboard quedaba vacía para siempre por
    más que corriera el recolector.
    """
    import json
    from unittest.mock import MagicMock, patch

    import sources.xm as xm

    db = str(tmp_path / "t.db")
    storage.inicializar_bd(db)
    monkeypatch.setattr(storage, "_db_path", lambda: db)

    fixture = json.loads(
        (RAIZ / "tests" / "fixtures" / "xm_factor_emision.json").read_text(encoding="utf-8")
    )
    resp = MagicMock()
    resp.json.return_value = fixture
    resp.raise_for_status.return_value = None

    with patch.object(xm.requests, "post", return_value=resp):
        xm.obtener_ultimo({"_id": "santa-marta"})

    guardadas = storage.historial("xm", "santa-marta", "intensidad_co2", 1000, db)
    assert len(guardadas) == 48, f"esperaba 48 horas (2 días), guardó {len(guardadas)}"

    # Ordenadas y sin duplicados
    marcas = [lec.ts for lec in guardadas]
    assert marcas == sorted(marcas)
    assert len(marcas) == len(set(marcas))


def test_xm_parsea_las_24_horas_de_cada_dia():
    import json

    import sources.xm as xm

    fixture = json.loads(
        (RAIZ / "tests" / "fixtures" / "xm_factor_emision.json").read_text(encoding="utf-8")
    )
    serie = xm._parsear_serie(fixture["Items"])

    assert len(serie) == 48
    # Una hora de diferencia entre puntos consecutivos
    for anterior, siguiente in zip(serie, serie[1:]):
        assert (siguiente[0] - anterior[0]).total_seconds() == 3600


def test_openmeteo_descarta_las_horas_futuras():
    """
    Se pide `forecast_days=1`, así que la respuesta trae horas que aún no han
    ocurrido. Guardarlas mezclaría pronóstico con observación en el historial
    que entrena el predictor.
    """
    from datetime import timedelta as td

    import sources.openmeteo_aire as aire

    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    data = {
        "hourly": {
            "time": [
                (ahora - td(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                (ahora - td(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                (ahora + td(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                (ahora + td(hours=2)).strftime("%Y-%m-%dT%H:%M"),
            ],
            "pm2_5": [10.0, 11.0, 12.0, 13.0],
        }
    }
    lecturas = aire._parsear_serie(data, "santa-marta", "test")

    assert len(lecturas) == 2, "solo deben guardarse las horas ya ocurridas"
    assert all(lec.ts <= ahora for lec in lecturas)


def test_openmeteo_clima_guarda_temperatura_y_humedad():
    """El predictor necesita ambas: sin humedad no hay índice de calor."""
    from datetime import timedelta as td

    import sources.openmeteo_clima as clima

    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    data = {
        "hourly": {
            "time": [(ahora - td(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in (2, 1)],
            "temperature_2m": [28.0, 29.0],
            "relative_humidity_2m": [70.0, 72.0],
        }
    }
    lecturas = clima._parsear_serie(data, "santa-marta", "test")

    metricas = {lec.metrica for lec in lecturas}
    assert metricas == {"temperatura", "humedad"}
    assert len(lecturas) == 4


def test_openmeteo_tolera_huecos_en_la_serie():
    """Un None en el reanálisis no debe cortar el resto de la serie."""
    from datetime import timedelta as td

    import sources.openmeteo_aire as aire

    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    data = {
        "hourly": {
            "time": [(ahora - td(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in (3, 2, 1)],
            "pm2_5": [10.0, None, 12.0],
        }
    }
    lecturas = aire._parsear_serie(data, "santa-marta", "test")
    assert len(lecturas) == 2


def test_el_recolector_no_guarda_por_duplicado():
    """
    El adaptador ya persiste; el recolector volvía a llamar a `guardar`, lo que
    duplicaba el trabajo en cada pasada.
    """
    import inspect

    import collector

    codigo = inspect.getsource(collector.recolectar_una_vez)
    assert "storage.guardar(" not in codigo, (
        "el recolector no debe guardar: de eso se encarga cada adaptador"
    )
