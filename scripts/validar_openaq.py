"""
scripts/validar_openaq.py — Comprueba la cobertura de OpenAQ para un bbox.

Es la herramienta con la que se validó la premisa del proyecto: OpenAQ no tiene
estaciones en Santa Marta ni en la costa Caribe (por eso la fuente de aire es
Open-Meteo). Se conserva como diagnóstico: si algún día quieres evaluar otra
ciudad, corre esto con su bbox antes de asumir que hay datos de estación.

Uso:
    python scripts/validar_openaq.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from config import cargar_dotenv  # noqa: E402

cargar_dotenv()
KEY = os.environ.get("OPENAQ_API_KEY")
if not KEY:
    sys.exit("Falta OPENAQ_API_KEY en el .env")

HEADERS = {"X-API-Key": KEY}
BASE = "https://api.openaq.org/v3"


def consultar_bbox(nombre: str, bbox: tuple[float, float, float, float]) -> None:
    lon_min, lat_min, lon_max, lat_max = bbox
    print(f"\n{'=' * 55}\n  {nombre}\n  bbox: {bbox}\n{'=' * 55}")
    try:
        r = requests.get(
            f"{BASE}/locations",
            params={"bbox": f"{lon_min},{lat_min},{lon_max},{lat_max}", "limit": 10},
            headers=HEADERS,
            timeout=15,
        )
        print(f"  HTTP: {r.status_code}")
        if r.status_code != 200:
            print(f"  Error: {r.text[:300]}")
            return

        results = r.json().get("results", [])
        print(f"  Estaciones encontradas: {len(results)}")
        if not results:
            print("  *** SIN ESTACIONES en esta zona ***")
            return

        for loc in results:
            coords = loc.get("coordinates", {})
            params = [p.get("name", "?") for p in loc.get("parameters", [])]
            print(f"\n  >>> [{loc.get('id', '?')}] {loc.get('name', 'sin nombre')}")
            print(f"      Coords: {coords.get('latitude', '?')}, {coords.get('longitude', '?')}")
            print(f"      Activa: {loc.get('isActive', '?')}  ·  Params: {params}")
    except requests.RequestException as exc:
        print(f"  ERROR: {exc}")


if __name__ == "__main__":
    consultar_bbox("Santa Marta, Colombia", (-74.30, 11.05, -73.85, 11.40))
    consultar_bbox("Barranquilla, Colombia (fallback)", (-74.85, 10.90, -74.70, 11.05))

    print(f"\n{'=' * 55}\n  Autenticación (v3/providers)\n{'=' * 55}")
    auth = requests.get(f"{BASE}/providers", headers=HEADERS, timeout=10)
    print(f"  HTTP: {auth.status_code}", "→ API key OK" if auth.status_code == 200 else auth.text[:200])
