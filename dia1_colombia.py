"""
dia1_colombia.py — Búsqueda amplia de estaciones OpenAQ en Colombia
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


def buscar_colombia():
    print("\n=== Estaciones OpenAQ en Colombia (país CO) ===")
    r = requests.get(
        f"{BASE}/locations",
        params={"country": "CO", "limit": 100},
        headers=HEADERS,
        timeout=20,
    )
    print(f"HTTP Status: {r.status_code}")
    data = r.json()
    results = data.get("results", [])
    total = data.get("meta", {}).get("found", len(results))
    print(f"Total estaciones en Colombia: {total}\n")

    for loc in results:
        coords = loc.get("coordinates", {})
        lat = coords.get("latitude", "?")
        lon = coords.get("longitude", "?")
        ciudad = loc.get("city", loc.get("locality", "?"))
        nombre = loc.get("name", "?")
        activa = loc.get("isActive", "?")
        params = [p.get("name", "?") for p in loc.get("parameters", [])]
        print(f"  [{loc['id']}] {nombre}")
        print(f"    Ciudad: {ciudad} | lat={lat}, lon={lon} | Activa: {activa}")
        print(f"    Params: {params}")
        print()


def buscar_mas_cercanas_sm():
    """Busca estaciones en un radio mayor alrededor de Santa Marta"""
    print("\n=== Radio ampliado: costa Caribe (bbox grande) ===")
    # Bbox que cubre la costa desde Cartagena hasta La Guajira
    r = requests.get(
        f"{BASE}/locations",
        params={"bbox": "-76.00,9.50,-72.50,12.50", "limit": 50},
        headers=HEADERS,
        timeout=20,
    )
    print(f"HTTP Status: {r.status_code}")
    data = r.json()
    results = data.get("results", [])
    print(f"Estaciones en costa Caribe: {len(results)}")
    for loc in results:
        coords = loc.get("coordinates", {})
        nombre = loc.get("name", "?")
        ciudad = loc.get("city", "?")
        lat = coords.get("latitude", "?")
        lon = coords.get("longitude", "?")
        params = [p.get("name") for p in loc.get("parameters", [])]
        print(f"  [{loc['id']}] {nombre} ({ciudad}) | lat={lat} lon={lon}")
        print(f"    Params: {params}")


buscar_colombia()
buscar_mas_cercanas_sm()
