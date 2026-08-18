"""
scripts/deduplicar_lecturas.py — Quita las dos redundancias del histórico.

1. XM guardado por ciudad
   La intensidad de carbono es del Sistema Interconectado Nacional: un solo
   número para todo el país. Se guardaba una fila por ciudad, así que cada hora
   entraban 14 filas idénticas (17x de redundancia medida en producción).
   Ahora `xm` es de ámbito nacional (`sources/registry.py`) y se persiste bajo
   `LUGAR_NACIONAL`. Este paso consolida lo ya guardado: deja una fila por
   (ts, métrica) y la reetiqueta.

   IMPORTANTE: sin esta migración la pestaña de Energía se queda vacía tras el
   despliegue, porque el lector busca bajo el lugar nacional y las filas viejas
   siguen bajo los ids de ciudad.

2. Ciudades que ya no se monitorean
   El proyecto se recortó de 32 capitales a 14 (las remotas daban timeout), pero
   sus lecturas siguen en la tabla. Nadie las lee: no están en `locations.py`,
   así que ni la API ni el bot pueden pedirlas.

Uso:
    python scripts/deduplicar_lecturas.py            # simulación, no escribe
    python scripts/deduplicar_lecturas.py --aplicar  # aplica los cambios

Es idempotente y solo actúa sobre Postgres (la base de producción).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import cargar_dotenv  # noqa: E402
from locations import LUGARES  # noqa: E402
from sources.base import LUGAR_NACIONAL  # noqa: E402

FUENTE_NACIONAL = "xm"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true",
                        help="Escribe los cambios. Sin esta bandera solo informa.")
    args = parser.parse_args()

    cargar_dotenv()
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://")):
        print("Este script es para la base de producción (DATABASE_URL de Postgres).")
        return 1

    import psycopg

    # Los lugares vivos son las ciudades configuradas más el nacional.
    vivos = tuple(LUGARES) + (LUGAR_NACIONAL,)

    with psycopg.connect(url) as con:
        # ── 1. XM duplicado por ciudad ───────────────────────────────────────
        dup = con.execute(
            "SELECT COUNT(*) FROM lecturas a WHERE a.fuente = %s AND EXISTS ("
            "  SELECT 1 FROM lecturas b WHERE b.fuente = a.fuente"
            "    AND b.ts = a.ts AND b.metrica = a.metrica AND b.id < a.id)",
            (FUENTE_NACIONAL,),
        ).fetchone()[0]
        total_xm = con.execute(
            "SELECT COUNT(*) FROM lecturas WHERE fuente = %s", (FUENTE_NACIONAL,)
        ).fetchone()[0]
        print(f"1. XM: {total_xm} filas, {dup} son copias del mismo dato "
              f"→ quedarían {total_xm - dup}")

        # ── 2. Ciudades ya no monitoreadas ───────────────────────────────────
        huerfanas = con.execute(
            "SELECT COUNT(*) FROM lecturas WHERE lugar_id <> ALL(%s)", (list(vivos),)
        ).fetchone()[0]
        ciudades = con.execute(
            "SELECT COUNT(DISTINCT lugar_id) FROM lecturas WHERE lugar_id <> ALL(%s)",
            (list(vivos),),
        ).fetchone()[0]
        print(f"2. Ciudades fuera de locations.py: {huerfanas} filas de {ciudades} lugares")

        total = dup + huerfanas
        print(f"\nTotal de filas a eliminar: {total}")

        if total == 0:
            print("Nada que hacer.")
            return 0

        if not args.aplicar:
            print("\nSimulación: no se escribió nada.")
            print("Para aplicarlo: python scripts/deduplicar_lecturas.py --aplicar")
            return 0

        # Orden importante: primero se borran las copias, y solo entonces se
        # reetiqueta. Al revés, reetiquetar chocaría con el índice único
        # (fuente, lugar_id, metrica, ts).
        borradas = con.execute(
            "DELETE FROM lecturas a WHERE a.fuente = %s AND EXISTS ("
            "  SELECT 1 FROM lecturas b WHERE b.fuente = a.fuente"
            "    AND b.ts = a.ts AND b.metrica = a.metrica AND b.id < a.id)",
            (FUENTE_NACIONAL,),
        ).rowcount
        movidas = con.execute(
            "UPDATE lecturas SET lugar_id = %s WHERE fuente = %s AND lugar_id <> %s",
            (LUGAR_NACIONAL, FUENTE_NACIONAL, LUGAR_NACIONAL),
        ).rowcount
        print(f"\n1. XM: {borradas} copias borradas, {movidas} reetiquetadas "
              f"a '{LUGAR_NACIONAL}'.")

        limpiadas = con.execute(
            "DELETE FROM lecturas WHERE lugar_id <> ALL(%s)", (list(vivos),)
        ).rowcount
        print(f"2. Ciudades fuera de servicio: {limpiadas} filas borradas.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
