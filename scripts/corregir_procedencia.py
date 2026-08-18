"""
scripts/corregir_procedencia.py — Corrige la procedencia de las lecturas de modelo.

Por qué existe: hasta el 2026-08-18 los adaptadores de Open-Meteo (aire y clima)
guardaban sus lecturas con `procedencia="local"`, así que el dashboard las
mostraba como "📍 Estación local (Modelo CAMS …)". Son modelos, no sensores: la
etiqueta presentaba una estimación como si fuera una medición.

Los adaptadores ya escriben `procedencia="modelo"`, pero las filas viejas siguen
mal etiquetadas. Este script las corrige de una vez.

No se ejecuta al arrancar la API a propósito: son ~124.000 filas y un UPDATE así
en cada boot sería un escaneo completo y un lock innecesario (la misma razón por
la que el ALTER de RLS consulta antes de tocar la tabla).

Uso:
    python scripts/corregir_procedencia.py            # simulación, no escribe
    python scripts/corregir_procedencia.py --aplicar  # escribe los cambios

Es idempotente: correrlo dos veces no cambia nada la segunda vez. Y es
reversible, porque solo toca la columna `procedencia`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import cargar_dotenv  # noqa: E402

# Fuentes que son modelos, no estaciones físicas.
FUENTES_MODELO = ("openmeteo-aire", "openmeteo-clima")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Escribe los cambios. Sin esta bandera solo informa qué haría.",
    )
    args = parser.parse_args()

    cargar_dotenv()
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://")):
        print("Este script es para la base de producción (DATABASE_URL de Postgres).")
        print("En SQLite local no hace falta: la base se regenera con datos nuevos.")
        return 1

    import psycopg

    marcadores = ", ".join(["%s"] * len(FUENTES_MODELO))
    with psycopg.connect(url) as con:
        pendientes = con.execute(
            f"SELECT COUNT(*) FROM lecturas "  # noqa: S608 — marcadores parametrizados
            f"WHERE fuente IN ({marcadores}) AND procedencia = 'local'",
            FUENTES_MODELO,
        ).fetchone()[0]

        print(f"Filas de modelo etiquetadas como 'local': {pendientes}")
        if pendientes == 0:
            print("Nada que corregir.")
            return 0

        if not args.aplicar:
            print("\nSimulación: no se escribió nada.")
            print("Para aplicarlo: python scripts/corregir_procedencia.py --aplicar")
            return 0

        cur = con.execute(
            f"UPDATE lecturas SET procedencia = 'modelo' "  # noqa: S608
            f"WHERE fuente IN ({marcadores}) AND procedencia = 'local'",
            FUENTES_MODELO,
        )
        print(f"Corregidas {cur.rowcount} filas.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
