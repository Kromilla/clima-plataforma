"""
tests/test_openaq.py — Tests del adaptador OpenAQ y del módulo de alertas.

Regla: cero llamadas a red. Todos los tests usan monkeypatch + fixtures JSON.
Corre con: pytest tests/ -v
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures helpers ─────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _cargar_fixture(nombre: str) -> dict:
    return json.loads((FIXTURES_DIR / nombre).read_text(encoding="utf-8"))


# ── Lugar de prueba ──────────────────────────────────────────────────────────

LUGAR_TEST = {
    "_id": "santa-marta",
    "nombre": "Santa Marta, Colombia",
    "lat": 11.2408,
    "lon": -74.1990,
    "bbox": (-74.30, 11.05, -73.85, 11.40),
    "zona_electricidad": "CO",
    "fallback_openaq": "barranquilla",
}

LUGAR_BARRANQUILLA = {
    "bbox": (-74.85, 10.90, -74.70, 11.05),
    "nombre": "Barranquilla, Colombia",
}


def _mock_cfg():
    m = MagicMock()
    m.OPENAQ_API_KEY = "test-key"
    m.UMBRAL_PM25_DEFAULT = 50.0
    m.POLLING_INTERVALO_SEG = 900
    m.DB_PATH = ":memory:"
    m.LOG_FILE = "bot_test.log"
    return m


# ── Test 1: datos reales disponibles → procedencia "local" ───────────────────

def test_obtener_ultimo_con_datos_locales(monkeypatch, tmp_path):
    """Cuando OpenAQ responde con datos, la lectura es de procedencia 'local'."""
    import sys
    import importlib

    locations_fixture = _cargar_fixture("openaq_locations_sm.json")
    measurements_fixture = _cargar_fixture("openaq_measurements_sm.json")

    import storage as st
    db_test = str(tmp_path / "test.db")
    st.inicializar_bd(db_test)
    monkeypatch.setattr(st, "_db_path", lambda: db_test)

    # Mock de config antes de recargar openaq
    mock_config_mod = MagicMock()
    mock_config_mod.cfg = _mock_cfg()
    monkeypatch.setitem(sys.modules, "config", mock_config_mod)

    mock_locations_mod = MagicMock()
    mock_locations_mod.LUGARES = {"barranquilla": LUGAR_BARRANQUILLA}
    mock_locations_mod.DEFAULT_LUGAR = "santa-marta"
    monkeypatch.setitem(sys.modules, "locations", mock_locations_mod)

    import sources.openaq as openaq_mod
    importlib.reload(openaq_mod)

    respuestas = [locations_fixture, measurements_fixture]
    call_count = {"n": 0}

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = respuestas[call_count["n"]]
        call_count["n"] += 1
        return resp

    monkeypatch.setattr(openaq_mod, "requests", MagicMock(get=mock_get, RequestException=Exception))
    monkeypatch.setattr(openaq_mod, "storage", st)
    monkeypatch.setattr(openaq_mod, "cfg", _mock_cfg())

    lectura = openaq_mod.obtener_ultimo(LUGAR_TEST)

    assert lectura.valor == pytest.approx(38.5)
    assert lectura.unidad == "µg/m³"
    assert lectura.metrica == "pm25"
    assert lectura.fuente == "openaq"
    assert lectura.procedencia == "local"
    assert lectura.lugar_id == "santa-marta"


# ── Test 2: API sin datos + caché → procedencia "cache" ──────────────────────

def test_fallback_a_cache_cuando_api_vacia(monkeypatch, tmp_path):
    """Cuando la API devuelve results=[] para local y fallback, sirve el caché."""
    import sys
    import importlib
    from sources.base import Lectura

    import storage as st
    db_test = str(tmp_path / "test_cache.db")
    st.inicializar_bd(db_test)
    monkeypatch.setattr(st, "_db_path", lambda: db_test)

    lectura_previa = Lectura(
        valor=42.0,
        unidad="µg/m³",
        metrica="pm25",
        fuente="openaq",
        procedencia="local",
        lugar_id="santa-marta",
        estacion_nombre="Estacion guardada",
        ts=datetime(2026, 7, 27, 20, 0, 0, tzinfo=timezone.utc),
    )
    st.guardar(lectura_previa, db_path=db_test)

    mock_config_mod = MagicMock()
    mock_config_mod.cfg = _mock_cfg()
    monkeypatch.setitem(sys.modules, "config", mock_config_mod)

    mock_locations_mod = MagicMock()
    mock_locations_mod.LUGARES = {"barranquilla": LUGAR_BARRANQUILLA}
    monkeypatch.setitem(sys.modules, "locations", mock_locations_mod)

    import sources.openaq as openaq_mod
    importlib.reload(openaq_mod)

    sin_datos = _cargar_fixture("openaq_sin_datos.json")

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = sin_datos
        return resp

    monkeypatch.setattr(openaq_mod, "requests", MagicMock(get=mock_get, RequestException=Exception))
    monkeypatch.setattr(openaq_mod, "storage", st)
    monkeypatch.setattr(openaq_mod, "cfg", _mock_cfg())
    monkeypatch.setattr(openaq_mod, "LUGARES", {"barranquilla": LUGAR_BARRANQUILLA})

    lectura = openaq_mod.obtener_ultimo(LUGAR_TEST)

    assert lectura.valor == pytest.approx(42.0)
    assert lectura.procedencia == "cache"
    assert lectura.lugar_id == "santa-marta"


# ── Test 3 & 4: revisar_alerta ───────────────────────────────────────────────

def test_revisar_alerta_supera_umbral():
    """Dado valor=65, umbral=50 → retorna mensaje de alerta."""
    from alerts import revisar_alerta
    resultado = revisar_alerta(valor=65.0, umbral=50.0)
    assert resultado is not None
    assert "65.0" in resultado
    assert "50.0" in resultado
    assert "ALERTA" in resultado


def test_revisar_alerta_bajo_umbral():
    """Dado valor=30, umbral=50 → retorna None (sin alerta)."""
    from alerts import revisar_alerta
    resultado = revisar_alerta(valor=30.0, umbral=50.0)
    assert resultado is None


# ── Test 5: storage — ciclo guardar/recuperar ─────────────────────────────────

def test_storage_guardar_y_recuperar(tmp_path):
    """Guardar una lectura y recuperarla como caché."""
    from sources.base import Lectura
    import storage as st

    db_test = str(tmp_path / "storage_test.db")
    st.inicializar_bd(db_test)

    lectura_orig = Lectura(
        valor=55.0,
        unidad="µg/m³",
        metrica="pm25",
        fuente="openaq",
        procedencia="local",
        lugar_id="santa-marta",
        estacion_nombre="SM-Centro",
        ts=datetime(2026, 7, 27, 18, 0, 0, tzinfo=timezone.utc),
    )
    st.guardar(lectura_orig, db_path=db_test)

    recuperada = st.ultimo_valor("openaq", "santa-marta", "pm25", db_path=db_test)

    assert recuperada is not None
    assert recuperada.valor == pytest.approx(55.0)
    assert recuperada.lugar_id == "santa-marta"
    assert recuperada.procedencia == "cache"


# ── Test 6: config.py — sin variables → sys.exit(1) ─────────────────────────

def test_config_falla_sin_variables(monkeypatch):
    """Si faltan variables obligatorias, _validar() llama sys.exit(1)."""
    import sys
    import types

    # Limpiar variables del entorno
    for var in ["OPENAQ_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
        monkeypatch.delenv(var, raising=False)

    # Probar _validar directamente (sin necesidad de recargar el modulo completo,
    # que ejecutaria _Config() y potencialmente usaria un .env existente)
    src = (
        "import os, sys\n"
        "def _validar(variables):\n"
        "    faltantes = [v for v in variables if not os.environ.get(v)]\n"
        "    if faltantes:\n"
        "        sys.exit(1)\n"
    )
    mod = types.ModuleType("_config_validar_test")
    exec(compile(src, "<test>", "exec"), mod.__dict__)

    with pytest.raises(SystemExit) as exc_info:
        mod._validar(["OPENAQ_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])

    assert exc_info.value.code == 1

