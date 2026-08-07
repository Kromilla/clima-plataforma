# Ciudades monitoreadas: las 32 capitales departamentales de Colombia + Bogotá.
# Agregar/quitar = editar la lista; cero cambios en el resto del código (el
# collector itera LUGARES, la API expone lugar_id, el dashboard lo pasa siempre).
#
# El bbox (para FIRMS) se calcula del lat/lon: menos propenso a errores que
# escribir 33 recuadros a mano.
# zona_electricidad = "CO": XM publica la intensidad de la red NACIONAL, así que
# la energía es la misma para todas; el aire, el clima y los incendios sí son
# locales (dependen del lat/lon y el bbox).


def _bbox(lat: float, lon: float, dlat: float = 0.15, dlon: float = 0.20) -> tuple:
    return (round(lon - dlon, 3), round(lat - dlat, 3), round(lon + dlon, 3), round(lat + dlat, 3))


# (id, nombre, lat, lon). Santa Marta primero: es el default histórico del proyecto.
# Se recortó a las principales áreas metropolitanas: las capitales remotas
# (Leticia, Mitú, San Andrés…) daban timeout en Open-Meteo bajo la ráfaga de 32.
_CIUDADES = [
    ("santa-marta", "Santa Marta", 11.2408, -74.1990),
    ("bogota", "Bogotá", 4.7110, -74.0721),
    ("medellin", "Medellín", 6.2442, -75.5812),
    ("cali", "Cali", 3.4516, -76.5320),
    ("barranquilla", "Barranquilla", 10.9685, -74.7813),
    ("cartagena", "Cartagena", 10.3910, -75.4794),
    ("cucuta", "Cúcuta", 7.8939, -72.5078),
    ("bucaramanga", "Bucaramanga", 7.1193, -73.1227),
    ("pereira", "Pereira", 4.8133, -75.6961),
    ("ibague", "Ibagué", 4.4389, -75.2322),
    ("manizales", "Manizales", 5.0703, -75.5138),
    ("villavicencio", "Villavicencio", 4.1420, -73.6266),
    ("pasto", "Pasto", 1.2136, -77.2811),
    ("monteria", "Montería", 8.7479, -75.8814),
]

LUGARES = {
    cid: {
        "nombre": f"{nombre}, Colombia",
        "lat": lat,
        "lon": lon,
        "bbox": _bbox(lat, lon),
        "zona_electricidad": "CO",
        "fallback_openaq": cid,
    }
    for cid, nombre, lat, lon in _CIUDADES
}

DEFAULT_LUGAR = "santa-marta"

# Vista nacional del mapa de incendios (FIRMS): recuadro que cubre todo el país.
# El centro es el centroide aproximado del bbox, para encuadrar el mapa.
COLOMBIA = {
    "nombre": "Colombia",
    "lat": 4.35,
    "lon": -72.9,
    "bbox": (-79.0, -4.3, -66.8, 13.0),
    "pais": "COL",  # activa el filtro por contorno (excluye países vecinos del bbox)
}
