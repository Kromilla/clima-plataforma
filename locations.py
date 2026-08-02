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
    ("neiva", "Neiva", 2.9273, -75.2819),
    ("armenia", "Armenia", 4.5339, -75.6811),
    ("popayan", "Popayán", 2.4448, -76.6147),
    ("valledupar", "Valledupar", 10.4631, -73.2532),
    ("sincelejo", "Sincelejo", 9.3047, -75.3978),
    ("riohacha", "Riohacha", 11.5449, -72.9072),
    ("tunja", "Tunja", 5.5353, -73.3678),
    ("florencia", "Florencia", 1.6144, -75.6062),
    ("quibdo", "Quibdó", 5.6947, -76.6611),
    ("yopal", "Yopal", 5.3378, -72.3959),
    ("mocoa", "Mocoa", 1.1519, -76.6483),
    ("san-jose-del-guaviare", "San José del Guaviare", 2.5698, -72.6407),
    ("arauca", "Arauca", 7.0844, -70.7591),
    ("leticia", "Leticia", -4.2153, -69.9406),
    ("mitu", "Mitú", 1.2536, -70.2339),
    ("puerto-carreno", "Puerto Carreño", 6.1890, -67.4859),
    ("inirida", "Inírida", 3.8653, -67.9239),
    ("san-andres", "San Andrés", 12.5847, -81.7006),
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
