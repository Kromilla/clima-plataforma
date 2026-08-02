"""
collector.py — Proceso que consulta todas las fuentes y persiste cada lectura.

Cubre el P0 de la Fase 2: "El proceso que consulta las fuentes persiste cada
lectura en storage.py de forma continua". Sin esto el dashboard solo tiene el
dato que el bot alcanzó a guardar del aire, y las pestañas de Clima y Energía
quedan vacías.

Uso:
    python collector.py            # corre en bucle continuo
    python collector.py --una-vez  # una sola pasada (útil para probar o para cron)

Cada fuente se consulta de forma aislada: si una falla, las demás siguen. Los
adaptadores ya guardan en `storage` y se degradan a caché por su cuenta, así que
aquí solo orquestamos y registramos el resultado.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

import logging_setup
import notificador
import storage
from config import cfg
from locations import LUGARES
from sources.registry import FUENTES

logger = logging.getLogger("collector")


def _notificar() -> None:
    """Dispara las alertas proactivas tras una pasada. Nunca frena al collector."""
    for revisar in (notificador.revisar_y_notificar, notificador.revisar_y_notificar_incendio):
        try:
            revisar()
        except Exception as exc:  # noqa: BLE001 — un fallo de alerta no debe frenar la recolección
            logger.exception("Error en %s: %s", revisar.__name__, exc)


def _lugar_con_id(lugar_id: str) -> dict:
    lugar = LUGARES[lugar_id].copy()
    lugar["_id"] = lugar_id
    return lugar


def recolectar_una_vez() -> dict[str, str]:
    """
    Consulta todas las fuentes para todos los lugares y persiste los resultados.

    Returns:
        Resumen {"<lugar>/<fuente>": "ok 8.4 µg/m³" | "sin clave" | "ERROR: ..."}
        — pensado para logging y para que los tests puedan afirmar sobre él.
    """
    resumen: dict[str, str] = {}

    for lugar_id in LUGARES:
        lugar = _lugar_con_id(lugar_id)

        for fuente in FUENTES:
            clave = f"{lugar_id}/{fuente.id}"

            if fuente.requiere_clave and not fuente.clave_configurada():
                resumen[clave] = "sin clave"
                logger.debug("%s: omitida (sin API key configurada)", clave)
                continue

            try:
                lectura = fuente.obtener(lugar)
                resumen[clave] = f"ok {lectura.valor:.1f} {lectura.unidad}"
                # El adaptador ya persistió la lectura; aquí solo orquestamos.
                logger.info(
                    "%s -> %.1f %s (%s)",
                    clave, lectura.valor, lectura.unidad, lectura.antiguedad_texto(),
                )
            except Exception as exc:  # noqa: BLE001 — una fuente caída no frena las demás
                resumen[clave] = f"ERROR: {exc}"
                logger.warning("%s → falló: %s", clave, exc)

    return resumen


def main() -> None:
    parser = argparse.ArgumentParser(description="Recolector de lecturas de todas las fuentes.")
    parser.add_argument(
        "--una-vez",
        action="store_true",
        help="Hace una sola pasada y termina (por defecto corre en bucle).",
    )
    parser.add_argument(
        "--intervalo",
        type=int,
        default=cfg.POLLING_INTERVALO_SEG,
        help=f"Segundos entre pasadas (default: {cfg.POLLING_INTERVALO_SEG}).",
    )
    args = parser.parse_args()

    logging_setup.configurar(cfg.LOG_FILE)

    storage.inicializar_bd()

    if args.una_vez:
        resumen = recolectar_una_vez()
        _notificar()
        fallos = sum(1 for v in resumen.values() if v.startswith("ERROR"))
        omitidas = sum(1 for v in resumen.values() if v == "sin clave")
        exitos = len(resumen) - fallos - omitidas

        # Las omitidas se cuentan aparte: informar "4 ok" cuando una fuente ni
        # se intentó da una falsa sensación de que todo está funcionando.
        mensaje = "Pasada única completa: %d ok, %d con error"
        args_log = [exitos, fallos]
        if omitidas:
            mensaje += ", %d omitidas (sin API key)"
            args_log.append(omitidas)
        logger.info(mensaje, *args_log)

        # Solo es fallo si nada de lo que se intentó funcionó.
        intentadas = len(resumen) - omitidas
        sys.exit(1 if intentadas and fallos == intentadas else 0)

    logger.info(
        "Recolector iniciado — %d fuentes × %d lugares cada %ds",
        len(FUENTES), len(LUGARES), args.intervalo,
    )
    while True:
        try:
            recolectar_una_vez()
            _notificar()
        except Exception as exc:  # noqa: BLE001 — el bucle nunca debe morir
            logger.exception("Error inesperado en la pasada: %s", exc)
        time.sleep(args.intervalo)


if __name__ == "__main__":
    main()
