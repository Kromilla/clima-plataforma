"""
logging_setup.py — Configuración de logging compartida por todos los ejecutables.

Por qué existe: en Windows la consola usa cp1252 por defecto, que no puede
codificar los caracteres que este proyecto usa por todos lados (µg/m³, gCO₂eq,
las flechas → de los logs y los emojis de las alertas). Cada línea de log con
uno de esos caracteres provocaba un traceback de "--- Logging error ---" que
ensuciaba la salida y escondía los mensajes reales.

La solución es forzar UTF-8 en la salida estándar. Si la consola aún no puede
dibujar un carácter, se sustituye en vez de reventar.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

FORMATO = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _forzar_utf8(flujo):
    """
    Reconfigura un flujo a UTF-8 cuando es posible.

    `errors="replace"` es el seguro: si la consola no puede dibujar un carácter
    aparece un símbolo de reemplazo, pero el programa sigue. Sin esto, un simple
    log de "µg/m³" tumbaba la línea entera.
    """
    try:
        flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        # Flujo redirigido o sin soporte de reconfiguración: no es fatal.
        pass
    return flujo


def forzar_utf8_consola() -> None:
    """
    Pone stdout y stderr en UTF-8.

    Lo llama `config.py` al importarse, así que cualquier archivo del proyecto
    (incluidos los scripts sueltos que hacen `print` de emojis) queda cubierto
    sin tener que acordarse de invocarlo.
    """
    _forzar_utf8(sys.stdout)
    _forzar_utf8(sys.stderr)


def configurar(archivo_log: str | Path | None = None, nivel: int = logging.INFO) -> None:
    """
    Configura el logging raíz para un ejecutable.

    Args:
        archivo_log: ruta del archivo de log. Si es None, solo escribe a consola.
        nivel: nivel mínimo a registrar.
    """
    forzar_utf8_consola()

    manejadores: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if archivo_log:
        manejadores.append(logging.FileHandler(archivo_log, encoding="utf-8"))

    logging.basicConfig(
        level=nivel,
        format=FORMATO,
        handlers=manejadores,
        force=True,  # reemplaza cualquier configuración previa
    )

    # httpx registra la URL completa de cada request, y la de Telegram lleva el
    # token embebido: en INFO eso escribiría el token en texto plano en el log.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # apscheduler es muy verboso con cada disparo del job de alertas.
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
