LUGARES = {
    "santa-marta": {
        "nombre": "Santa Marta, Colombia",
        "lat": 11.2408,
        "lon": -74.1990,
        "bbox": (-74.30, 11.05, -73.85, 11.40),
        "zona_electricidad": "CO",        # Electricity Maps zone (tier gratuito = 1 zona)
        "fallback_openaq": "barranquilla", # Estación más cercana si no hay local (~90 km)
    },
    # Agregar un lugar nuevo = una entrada más aquí. Cero cambios en el resto del código.
}

DEFAULT_LUGAR = "santa-marta"
