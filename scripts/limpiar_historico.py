"""
scripts/limpiar_historico.py — Recorta el histórico que ya no se usa.

Qué borra y qué no
------------------
Las gráficas del dashboard piden como mucho las últimas 24-48 horas, así que
guardar meses de PM2.5, energía o focos no aporta nada: son filas que solo
ocupan espacio en la base.

`openmeteo-clima` queda FUERA a propósito. Es la serie que entrena el predictor
de riesgo (`risk.py` exige 30 días como mínimo y usa estacionalidad anual), así
que recortarla lo rompería. Si algún día se decide tocarla, hay que revisar
`risk.DIAS_MINIMOS` primero.

Uso:
    python scripts/limpiar_historico.py                 # simulación, no borra
    python scripts/limpiar_historico.py --aplicar       # borra de verdad
    python scripts/limpiar_historico.py --dias 7        # otro corte

Funciona igual en SQLite (local) y Postgres (producción): `ts` se guarda como
ISO 8601 UTC, y en ese formato el orden alfabético coincide con el cronológico.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import storage  # noqa: E402
from config import cargar_dotenv  # noqa: E402

# Fuentes cuyo histórico solo alimenta gráficas de las últimas horas.
FUENTES_RECORTABLES = ("openmeteo-aire", "xm", "firms")

# Excluida a propósito: alimenta el predictor de riesgo.
FUENTE_PREDICTOR = "openmeteo-clima"

# 30 días: las gráficas piden 24-48 h, así que sobra margen, y el techo evita
# que el histórico crezca sin límite. El job semanal de .github/workflows/
# limpieza.yml lo mantiene solo.
DIAS_POR_DEFECTO = 30


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dias", type=int, default=DIAS_POR_DEFECTO,
                        help=f"Días de histórico a conservar (default: {DIAS_POR_DEFECTO}).")
    parser.add_argument("--aplicar", action="store_true",
                        help="Borra de verdad. Sin esta bandera solo informa.")
    args = parser.parse_args()

    if args.dias < 1:
        print("--dias debe ser al menos 1.")
        return 1

    cargar_dotenv()
    corte = (datetime.now(timezone.utc) - timedelta(days=args.dias)).isoformat()

    print(f"Conservando los últimos {args.dias} días (desde {corte[:16]} UTC).")
    print(f"Sin tocar '{FUENTE_PREDICTOR}': alimenta el predictor de riesgo.\n")

    marcadores = ", ".join(["?"] * len(FUENTES_RECORTABLES))
    total = 0

    with storage._conexion() as (con, es_pg):
        for fuente in FUENTES_RECORTABLES:
            viejas = con.execute(
                storage._ph(
                    "SELECT COUNT(*) FROM lecturas WHERE fuente = ? AND ts < ?", es_pg),
                (fuente, corte),
            ).fetchone()
            # SQLite devuelve tupla; psycopg con dict_row devuelve dict.
            n = list(viejas.values())[0] if isinstance(viejas, dict) else viejas[0]
            total += n
            print(f"  {fuente:18} {n:>8} filas por borrar")

        conservadas = con.execute(
            storage._ph("SELECT COUNT(*) FROM lecturas WHERE fuente = ?", es_pg),
            (FUENTE_PREDICTOR,),
        ).fetchone()
        n_pred = (list(conservadas.values())[0] if isinstance(conservadas, dict)
                  else conservadas[0])
        print(f"  {FUENTE_PREDICTOR:18} {n_pred:>8} filas intactas (predictor)")

        print(f"\nTotal por borrar: {total}")

        if total == 0:
            print("Nada que limpiar.")
            return 0

        if not args.aplicar:
            print("\nSimulación: no se borró nada.")
            print(f"Para aplicarlo: python scripts/limpiar_historico.py "
                  f"--dias {args.dias} --aplicar")
            return 0

        cur = con.execute(
            storage._ph(
                f"DELETE FROM lecturas WHERE fuente IN ({marcadores}) AND ts < ?",  # noqa: S608
                es_pg),
            (*FUENTES_RECORTABLES, corte),
        )
        print(f"\nBorradas {cur.rowcount} filas.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
