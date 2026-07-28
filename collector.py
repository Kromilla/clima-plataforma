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

import storage
from config import cfg
from locations import LUGARES
from sources.registry import FUENTES

logger = logging.getLogger("collector")


def _lugar_con_id(lugar_id: str) -> dict:
    lugar = LUGARES[lugar_id].copy()
    lugar["_id"] = lugar_id
    return lugar


def recolectar_una_vez() -> dict[str, str]:
    """
    Consulta todas las fuentes para todos los lugares y persiste los resultados.

    Returns:
        Resumen {"<lugar>/<fuente>": "ok 8.4 µg/m³" | "ERROR: ..."} — pensado
        para logging y para que los tests puedan afirmar sobre el resultado.
    """
    resumen: dict[str, str] = {}

    for lugar_id in LUGARES:
        lugar = _lugar_con_id(lugar_id)

        for fuente in FUENTES:
            clave = f"{lugar_id}/{fuente.id}"
            try:
                lectura = fuente.obtener(lugar)
                resumen[clave] = f"ok {lectura.valor:.1f} {lectura.unidad}"
                logger.info(
                    "%s → %.1f %s (%s)",
                    clave, lectura.valor, lectura.unidad, lectura.antiguedad_texto(),
                )
                # El adaptador ya guardó. Reintentar aquí es barato y nos dice si
                # la fuente publicó algo nuevo o si seguimos viendo el mismo dato.
                if not storage.guardar(lectura):
                    logger.debug("%s: sin dato nuevo (mismo timestamp)", clave)
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

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(cfg.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    storage.inicializar_bd()

    if args.una_vez:
        resumen = recolectar_una_vez()
        fallos = sum(1 for v in resumen.values() if v.startswith("ERROR"))
        logger.info("Pasada única completa: %d ok, %d con error",
                    len(resumen) - fallos, fallos)
        sys.exit(1 if fallos == len(resumen) else 0)

    logger.info(
        "Recolector iniciado — %d fuentes × %d lugares cada %ds",
        len(FUENTES), len(LUGARES), args.intervalo,
    )
    while True:
        try:
            recolectar_una_vez()
        except Exception as exc:  # noqa: BLE001 — el bucle nunca debe morir
            logger.exception("Error inesperado en la pasada: %s", exc)
        time.sleep(args.intervalo)


if __name__ == "__main__":
    main()
