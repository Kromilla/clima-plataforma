"""
tests/conftest.py — Configuración global de pytest.

Asegura que el directorio raíz del proyecto esté en el path de Python para que
los imports de `sources`, `storage`, `config`, etc. funcionen sin instalar el
paquete, y provee variables de entorno de prueba.
"""
import os
import sys
from pathlib import Path

import pytest

# Agrega la raíz del proyecto al PYTHONPATH.
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# `config.py` ejecuta _Config() al importarse y hace sys.exit(1) si faltan las
# variables obligatorias. Importar cualquier módulo que dependa de config (vía
# sources/firms, por ejemplo) durante la recolección de pytest dispararía ese
# sys.exit en un entorno sin .env — como el runner de CI. Definir valores dummy
# aquí hace que la suite sea autónoma: corre igual con o sin .env.
# `setdefault` no pisa un .env o entorno real si ya está presente.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "0")


@pytest.fixture(autouse=True)
def _limpiar_caches_modulo():
    """Los caches de módulo (firms, xm) se limpian para aislar cada test."""
    import sources.firms as firms
    import sources.xm as xm
    firms._CACHE_FOCOS.clear()
    xm._CACHE_SERIE = None
    yield
    firms._CACHE_FOCOS.clear()
    xm._CACHE_SERIE = None
