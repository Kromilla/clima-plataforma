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


def test_se_puede_leer_mientras_hay_una_escritura_abierta(tmp_path):
    """Con WAL, un lector no debe fallar porque haya una transacción abierta."""
    db = str(tmp_path / "t.db")
    storage.inicializar_bd(db)
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
