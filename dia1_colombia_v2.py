"""
dia1_colombia_v2.py — Búsqueda usando el endpoint correcto de v3
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


def explorar_api():
    """Verificar qué endpoints y parámetros funciona la v3."""

    # 1. Buscar por países disponibles
    print("=== Países disponibles en OpenAQ v3 ===")
    r = requests.get(f"{BASE}/countries", headers=HEADERS, params={"limit": 200}, timeout=15)
    print(f"Status: {r.status_code}")
    data = r.json()
    results = data.get("results", [])
    colombia = [c for c in results if c.get("code") == "CO" or "Colombia" in str(c.get("name", ""))]
    print(f"Total países: {len(results)}")
    print(f"Colombia encontrada: {colombia}")

    # 2. Buscar locations filtrando por countryId de Colombia
    if colombia:
        co_id = colombia[0].get("id")
        print(f"\n=== Estaciones en Colombia (countryId={co_id}) ===")
        r2 = requests.get(
            f"{BASE}/locations",
            headers=HEADERS,
            params={"countries_id": co_id, "limit": 100},
            timeout=20,
        )
        print(f"Status: {r2.status_code}")
        data2 = r2.json()
        results2 = data2.get("results", [])
        meta2 = data2.get("meta", {})
        print(f"Total: {meta2.get('found', len(results2))}")
        for loc in results2:
            coords = loc.get("coordinates", {})
            lat = coords.get("latitude", "?")
            lon = coords.get("longitude", "?")
            nombre = loc.get("name", "?")
            ciudad = loc.get("city", loc.get("locality", "?"))
            activa = loc.get("isActive", "?")
            params = [p.get("name") for p in loc.get("parameters", [])]
            print(f"  [{loc['id']}] {nombre} | {ciudad} | lat={lat} lon={lon} | activa={activa}")
            print(f"       Params: {params}")

    # 3. Búsqueda por texto "santa marta" o "magdalena"
    print("\n=== Búsqueda por nombre 'santa marta' ===")
    r3 = requests.get(
        f"{BASE}/locations",
        headers=HEADERS,
        params={"name": "santa", "limit": 20},
        timeout=15,
    )
    print(f"Status: {r3.status_code}")
    for loc in r3.json().get("results", []):
        coords = loc.get("coordinates", {})
        print(f"  [{loc['id']}] {loc.get('name')} | lat={coords.get('latitude')} lon={coords.get('longitude')}")

    # 4. Ver estructura de un location para entender la respuesta
    print("\n=== Estructura de la API v3 (endpoint raíz) ===")
    r4 = requests.get(f"{BASE}/locations", headers=HEADERS, params={"limit": 1}, timeout=10)
    import json
    sample = r4.json()
    print(json.dumps(sample.get("meta", {}), indent=2))
    if sample.get("results"):
        print("Primer resultado (keys):", list(sample["results"][0].keys()))


explorar_api()
