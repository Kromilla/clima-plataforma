"""
tests/conftest.py — Configuración global de pytest.

Asegura que el directorio raíz del proyecto esté en el path de Python
para que los imports de `sources`, `storage`, `config`, etc. funcionen
sin instalar el paquete.
"""
import sys
from pathlib import Path

# Agrega la raíz del proyecto al PYTHONPATH
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
