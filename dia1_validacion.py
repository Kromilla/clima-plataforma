"""
dia1_validacion.py — Validación Día 1 (§8 del informe v3)
Verifica cobertura de OpenAQ para Santa Marta y Barranquilla.
"""
import os
import sys

import requests

from config import cargar_dotenv

cargar_dotenv()
KEY = os.environ.get("OPENAQ_API_KEY")
if not KEY:
    sys.exit("Falta OPENAQ_API_KEY en el .env")

HEADERS = {"X-API-Key": KEY}
BASE = "https://api.openaq.org/v3"


def consultar_bbox(nombre, bbox):
    lon_min, lat_min, lon_max, lat_max = bbox
    print(f"\n{'='*55}")
    print(f"  {nombre}")
    print(f"  bbox: {bbox}")
    print(f"{'='*55}")
    try:
        r = requests.get(
            f"{BASE}/locations",
            params={"bbox": f"{lon_min},{lat_min},{lon_max},{lat_max}", "limit": 10},
            headers=HEADERS,
            timeout=15,
        )
        print(f"  HTTP Status: {r.status_code}")
        if r.status_code != 200:
            print(f"  Error: {r.text[:300]}")
            return

        data = r.json()
        results = data.get("results", [])
        total = data.get("meta", {}).get("found", len(results))
        print(f"  Estaciones encontradas: {total}")

        if not results:
            print("  *** SIN ESTACIONES en esta zona ***")
            return

        for loc in results:
            loc_id = loc.get("id", "?")
            nombre_loc = loc.get("name", "Sin nombre")
            coords = loc.get("coordinates", {})
            lat = coords.get("latitude", "?")
            lon = coords.get("longitude", "?")
            is_active = loc.get("isActive", "?")
            params = [p.get("name", "?") for p in loc.get("parameters", [])]

            print(f"\n  >>> Estacion ID={loc_id}")
            print(f"      Nombre   : {nombre_loc}")
            print(f"      Coords   : lat={lat}, lon={lon}")
            print(f"      Activa   : {is_active}")
            print(f"      Params   : {params}")

            # Obtener ultima medicion de pm25 si existe
            if "pm25" in params or "PM25" in [p.upper() for p in params]:
                r2 = requests.get(
                    f"{BASE}/locations/{loc_id}/measurements",
                    params={"parameter": "pm25", "limit": 1},
                    headers=HEADERS,
                    timeout=15,
                )
                if r2.status_code == 200:
                    meds = r2.json().get("results", [])
                    if meds:
                        m = meds[0]
                        val = m.get("value", "?")
                        fecha = m.get("date", {}).get("utc", "?")
                        print(f"      PM2.5    : {val} ug/m3  @ {fecha}")
                    else:
                        print("      PM2.5    : sin mediciones recientes")
    except Exception as e:
        print(f"  ERROR: {e}")


# 1. Santa Marta
consultar_bbox(
    "SANTA MARTA, Colombia",
    (-74.30, 11.05, -73.85, 11.40),
)

# 2. Barranquilla (fallback)
consultar_bbox(
    "BARRANQUILLA, Colombia (fallback)",
    (-74.85, 10.90, -74.70, 11.05),
)

# 3. Verificar autenticacion con un endpoint simple
print(f"\n{'='*55}")
print("  TEST DE AUTENTICACION (v3/providers)")
print(f"{'='*55}")
r_auth = requests.get(f"{BASE}/providers", headers=HEADERS, timeout=10)
print(f"  HTTP Status: {r_auth.status_code}")
if r_auth.status_code == 200:
    print("  API key valida y funcionando correctamente.")
else:
    print(f"  Respuesta: {r_auth.text[:200]}")
