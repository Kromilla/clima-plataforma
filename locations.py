# Ciudades monitoreadas. Agregar una = una entrada más aquí; cero cambios en el
# resto del código (el collector itera LUGARES, la API expone lugar_id y el
# dashboard lo pasa en cada request).
#
# bbox = (lon_min, lat_min, lon_max, lat_max) — recuadro para FIRMS.
# zona_electricidad = "CO": XM publica la intensidad de la red NACIONAL, así que
# el dato de energía es el mismo para todas las ciudades de Colombia (el aire, el
# clima y los incendios sí son locales).
LUGARES = {
    "santa-marta": {
        "nombre": "Santa Marta, Colombia",
        "lat": 11.2408,
        "lon": -74.1990,
        "bbox": (-74.30, 11.05, -73.85, 11.40),
        "zona_electricidad": "CO",
        "fallback_openaq": "barranquilla",  # estación más cercana (~90 km)
    },
    "barranquilla": {
        "nombre": "Barranquilla, Colombia",
        "lat": 10.9685,
        "lon": -74.7813,
        "bbox": (-74.95, 10.85, -74.65, 11.10),
        "zona_electricidad": "CO",
        "fallback_openaq": "barranquilla",
    },
    "cartagena": {
        "nombre": "Cartagena, Colombia",
        "lat": 10.3910,
        "lon": -75.4794,
        "bbox": (-75.65, 10.25, -75.30, 10.55),
        "zona_electricidad": "CO",
        "fallback_openaq": "cartagena",
    },
    "bogota": {
        "nombre": "Bogotá, Colombia",
        "lat": 4.7110,
        "lon": -74.0721,
        "bbox": (-74.25, 4.55, -73.95, 4.85),
        "zona_electricidad": "CO",
        "fallback_openaq": "bogota",
    },
    "medellin": {
        "nombre": "Medellín, Colombia",
        "lat": 6.2442,
        "lon": -75.5812,
        "bbox": (-75.75, 6.10, -75.45, 6.40),
        "zona_electricidad": "CO",
        "fallback_openaq": "medellin",
    },
}

DEFAULT_LUGAR = "santa-marta"
