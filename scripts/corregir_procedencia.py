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

# Cómo debe quedar etiquetada cada fuente. Ninguna de las cuatro es un sensor
# físico en la ciudad, que es lo que significa "local":
#   · Open-Meteo (aire y clima) calcula, no mide  → modelo
#   · XM mide de verdad, pero la red nacional      → nacional
#   · FIRMS detecta de verdad, pero desde órbita   → satelite
PROCEDENCIA_CORRECTA = {
    "openmeteo-aire": "modelo",
    "openmeteo-clima": "modelo",
    "xm": "nacional",
    "firms": "satelite",
}


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

    with psycopg.connect(url) as con:
        pendientes = {}
        for fuente, correcta in PROCEDENCIA_CORRECTA.items():
            n = con.execute(
                "SELECT COUNT(*) FROM lecturas WHERE fuente = %s AND procedencia <> %s "
                "AND procedencia <> 'cache'",
                (fuente, correcta),
            ).fetchone()[0]
            if n:
                pendientes[fuente] = (n, correcta)

        if not pendientes:
            print("Todas las lecturas ya están bien etiquetadas.")
            return 0

        total = sum(n for n, _ in pendientes.values())
        for fuente, (n, correcta) in pendientes.items():
            print(f"  {fuente:18} {n:>7} filas → '{correcta}'")
        print(f"\nTotal a corregir: {total}")

        if not args.aplicar:
            print("\nSimulación: no se escribió nada.")
            print("Para aplicarlo: python scripts/corregir_procedencia.py --aplicar")
            return 0

        print()
        for fuente, (_, correcta) in pendientes.items():
            cur = con.execute(
                "UPDATE lecturas SET procedencia = %s WHERE fuente = %s "
                "AND procedencia <> %s AND procedencia <> 'cache'",
                (correcta, fuente, correcta),
            )
            print(f"  {fuente:18} {cur.rowcount:>7} corregidas")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
