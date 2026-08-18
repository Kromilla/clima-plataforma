"""
sources/metar.py — Condiciones actuales medidas por estaciones METAR de aeropuerto.

Por qué existe: el resto de las fuentes de clima son MODELOS (Open-Meteo, MET
Norway). Un modelo interpola; una estación METAR tiene termómetro, anemómetro y
barómetro físicos, y publica cada hora. Para "el dato más real posible" la
estación gana — pero solo si de verdad representa a la ciudad.

La trampa de la altitud: el aeropuerto no siempre está a la altura de la ciudad.
Rionegro (el internacional de Medellín) está 650 m más alto que Medellín, y
Chachagüí 750 m más bajo que Pasto: usar esas estaciones daría un error de varios
grados. Por eso cada ciudad declara la altitud de ambos, y solo se usa la
estación cuando la diferencia es menor que _TOLERANCIA_ALTITUD_M. Las ciudades
donde no cuadra no están en la tabla y siguen con el modelo.

Fuente: aviationweather.gov (NOAA). Gratis, sin API key. Pide User-Agent propio.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_URL = "https://aviationweather.gov/api/data/metar"
_UA = "ClimaBot/1.0 (github.com/Kromilla/clima-plataforma)"

# Diferencia máxima de altitud entre ciudad y estación para considerarla
# representativa. A 200 m el gradiente térmico estándar (~6.5 °C/km) da un sesgo
# de ~1.3 °C: del orden del error del propio modelo, así que es aceptable.
_TOLERANCIA_ALTITUD_M = 200


class EstacionMetar:
    """Estación asignada a una ciudad, con las altitudes que justifican usarla."""

    __slots__ = ("icao", "nombre", "alt_estacion_m", "alt_ciudad_m", "km")

    def __init__(self, icao: str, nombre: str, alt_estacion_m: int,
                 alt_ciudad_m: int, km: float) -> None:
        self.icao = icao
        self.nombre = nombre
        self.alt_estacion_m = alt_estacion_m
        self.alt_ciudad_m = alt_ciudad_m
        self.km = km

    @property
    def es_representativa(self) -> bool:
        return abs(self.alt_ciudad_m - self.alt_estacion_m) <= _TOLERANCIA_ALTITUD_M


# Altitudes verificadas contra la API de elevación de Open-Meteo (ciudad) y el
# campo `elev` del propio METAR (estación).
#
# Ausentes a propósito — la estación NO representa a la ciudad:
#   bucaramanga  SKBG  ciudad 969 m / estación 1187 m  (218 m)
#   ibague       SKIB  ciudad 1233 m / estación 899 m  (334 m)
#   pasto        SKPS  ciudad 2546 m / estación 1798 m (748 m)
# Esas tres siguen con el modelo, que sí evalúa el punto exacto de la ciudad.
#
# Medellín usa SKMD (Olaya Herrera, dentro de la ciudad), no SKRG (Rionegro):
# Rionegro está a 2132 m contra los 1476 m de Medellín y marcaba ~6 °C menos.
ESTACIONES: dict[str, EstacionMetar] = {
    "santa-marta":   EstacionMetar("SKSM", "Aeropuerto Simón Bolívar", 5, 10, 13.9),
    "bogota":        EstacionMetar("SKBO", "Aeropuerto El Dorado", 2547, 2557, 8.8),
    "medellin":      EstacionMetar("SKMD", "Aeropuerto Olaya Herrera", 1491, 1476, 3.7),
    "cali":          EstacionMetar("SKCL", "Aeropuerto Alfonso Bonilla", 967, 1009, 19.5),
    "barranquilla":  EstacionMetar("SKBQ", "Aeropuerto Ernesto Cortissoz", 23, 21, 9.5),
    "cartagena":     EstacionMetar("SKCG", "Aeropuerto Rafael Núñez", 6, 13, 7.4),
    "cucuta":        EstacionMetar("SKCC", "Aeropuerto Camilo Daza", 308, 310, 4.0),
    "pereira":       EstacionMetar("SKPE", "Aeropuerto Matecaña", 1341, 1410, 4.3),
    "manizales":     EstacionMetar("SKMZ", "Aeropuerto La Nubia", 2075, 2113, 6.6),
    "villavicencio": EstacionMetar("SKVV", "Aeropuerto Vanguardia", 421, 437, 2.4),
    "monteria":      EstacionMetar("SKMR", "Aeropuerto Los Garzones", 12, 18, 10.7),
}


class MetarNoDisponible(Exception):
    """No hay estación representativa para el lugar, o la estación no respondió."""


# Un METAR se publica una vez por hora, así que cachear 10 min no envejece el
# dato y evita pegarle a la NOAA en cada refresco del dashboard.
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_SEG = 600


def estacion_de(lugar: dict) -> EstacionMetar | None:
    """Estación representativa del lugar, o None si no hay una válida."""
    est = ESTACIONES.get(lugar.get("_id", ""))
    if est is None or not est.es_representativa:
        return None
    return est


def _humedad_relativa(temp_c: float, rocio_c: float) -> float:
    """
    Humedad relativa a partir de temperatura y punto de rocío (fórmula de Magnus).

    El METAR no publica humedad: publica el punto de rocío, que es la medición
    directa del sensor. La humedad se deriva de ambos.
    """
    def presion_vapor(t: float) -> float:
        return math.exp((17.625 * t) / (243.04 + t))

    return round(100.0 * presion_vapor(rocio_c) / presion_vapor(temp_c), 1)


# Nubosidad reportada → (fracción de cielo cubierto en %, código WMO base).
# METAR informa en octavos de cielo; el punto medio de cada categoría basta para
# la UI, que solo muestra un porcentaje aproximado.
_COBERTURA = {
    "SKC": (0, 0), "CLR": (0, 0), "CAVOK": (0, 0), "NCD": (0, 0), "NSC": (0, 0),
    "FEW": (19, 1), "SCT": (44, 2), "BKN": (75, 3), "OVC": (100, 3),
}

# Fenómenos del METAR → código WMO. Se recorre en orden y el primero que aparece
# gana, así que lo más severo va primero: una tormenta con lluvia debe reportarse
# como tormenta, no como lluvia.
_FENOMENOS = (
    ("TS", 95),
    ("GR", 95), ("GS", 95),
    ("SHRA", 80), ("SHSN", 85),
    ("FZRA", 66),
    ("DZ", 53),
    ("RA", 63),
    ("SN", 73),
    ("FG", 45), ("BR", 45),
    ("HZ", 45), ("FU", 45),
)

# Palabras del METAR que son solo letras pero NO describen el tiempo presente.
# Sin esta lista, "NOSIG" o "NSC" entrarían al buscador de fenómenos.
_NO_FENOMENOS = frozenset({
    "METAR", "SPECI", "AUTO", "COR", "NIL", "NOSIG", "CAVOK", "CLR", "SKC",
    "NSC", "NCD", "TEMPO", "BECMG", "PROB", "VRB", "TCU", "CB", "AMD", "RTD",
})


def _tokens_de_tiempo(crudo: str, icao: str = "") -> list[str]:
    """
    Palabras del METAR que pueden describir el tiempo presente.

    Dos filtros importan:

    1. Se corta en `RMK`. Todo lo que sigue son remarks: información
       suplementaria, no el tiempo oficial. Sin este corte, un `RMK HZ` en
       Cartagena hacía que el dashboard reportara calima cuando el cuerpo del
       reporte no traía ningún fenómeno.
    2. Solo pasan las palabras de puras letras. Los grupos de nubes
       (`BKN015TCU`), viento (`27003KT`), visibilidad (`9999`), presión
       (`Q1012`) y temperatura (`29/26`) llevan dígitos o barras, así que
       quedan fuera y no pueden producir coincidencias falsas.

    El identificador de la estación se descarta aparte: es puras letras, así que
    pasaría el filtro anterior, y un código como "SKRA" se leería como lluvia.
    """
    cuerpo = (crudo or "").upper().split(" RMK", 1)[0]
    descartar = _NO_FENOMENOS | {icao.upper()} if icao else _NO_FENOMENOS
    tokens = []
    for palabra in cuerpo.split():
        limpia = palabra.lstrip("-+").removeprefix("VC")
        if limpia.isalpha() and limpia not in descartar:
            tokens.append(limpia)
    return tokens


def _codigo_wmo(crudo: str, cobertura: str | None, icao: str = "") -> int:
    """
    Traduce el METAR al código WMO que ya usa el frontend para elegir el ícono.

    Reutilizar la escala de Open-Meteo evita un segundo mapeo en la UI.
    """
    tokens = _tokens_de_tiempo(crudo, icao)
    for marca, codigo in _FENOMENOS:
        if any(marca in token for token in tokens):
            return codigo
    return _COBERTURA.get((cobertura or "").upper(), (0, 3))[1]


def _nubosidad(cobertura: str | None) -> int | None:
    if not cobertura:
        return None
    return _COBERTURA.get(cobertura.upper(), (None, 0))[0]


def _direccion(wdir: object) -> int | None:
    """La dirección puede venir como 'VRB' (variable) en vez de grados."""
    if isinstance(wdir, bool):
        return None
    if isinstance(wdir, (int, float)):
        return int(wdir)
    return None  # 'VRB' u otro texto: no hay un rumbo único que mostrar


def _es_dia(ts: datetime, lugar: dict) -> bool:
    """
    Día o noche por la hora solar local, aproximada con la longitud.

    El METAR no dice si es de día. Colombia está cerca del ecuador, así que un
    umbral 6-18 en hora solar acierta salvo unos minutos en los bordes.
    """
    hora_solar = (ts.hour + ts.minute / 60 + lugar.get("lon", -74.0) / 15.0) % 24
    return 6 <= hora_solar < 18


def condiciones_actuales(lugar: dict) -> dict:
    """
    Condiciones medidas por la estación METAR asignada al lugar.

    Devuelve la misma forma que `openmeteo_clima.condiciones_actuales`, para que
    el endpoint pueda intercambiar una fuente por otra sin cambios.

    Raises:
        MetarNoDisponible: si el lugar no tiene estación representativa, si la
            NOAA no responde, o si el reporte llega sin temperatura.
    """
    est = estacion_de(lugar)
    if est is None:
        raise MetarNoDisponible(
            f"Sin estación representativa para {lugar.get('_id', 'desconocido')}"
        )

    cacheado = _CACHE.get(est.icao)
    if cacheado and time.monotonic() - cacheado[0] < _CACHE_TTL_SEG:
        return cacheado[1]

    try:
        resp = requests.get(
            _URL,
            params={"ids": est.icao, "format": "json"},
            headers={"User-Agent": _UA},
            timeout=8,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise MetarNoDisponible(f"La estación {est.icao} no respondió: {exc}") from exc

    reportes = resp.json() or []
    if not reportes:
        raise MetarNoDisponible(f"La estación {est.icao} no publicó reporte")

    r = reportes[0]
    if r.get("temp") is None:
        raise MetarNoDisponible(f"El reporte de {est.icao} llegó sin temperatura")

    temp = float(r["temp"])
    rocio = r.get("dewp")
    viento_kt = r.get("wspd")
    racha_kt = r.get("wgst")
    ts = datetime.fromtimestamp(int(r["obsTime"]), tz=timezone.utc)

    datos = {
        "origen": f"Estación {est.icao} · {est.nombre}",
        "es_estacion": True,
        "estacion_km": est.km,
        # Sin la 'Z' final: el frontend la agrega al construir la fecha, igual
        # que con Open-Meteo. Cambiar el formato aquí rompería ese parseo.
        "ts": ts.strftime("%Y-%m-%dT%H:%M"),
        "temperatura": temp,
        # El METAR no publica sensación térmica. Inventarla aquí sería fingir un
        # dato que la estación no mide.
        "sensacion": None,
        "humedad": _humedad_relativa(temp, float(rocio)) if rocio is not None else None,
        # La precipitación acumulada solo la informan algunos aeropuertos y con
        # formatos distintos; se deja fuera antes que reportar un 0 falso.
        "precipitacion": None,
        "codigo": _codigo_wmo(r.get("rawOb", ""), r.get("cover"), est.icao),
        "nubosidad": _nubosidad(r.get("cover")),
        "viento_kmh": round(float(viento_kt) * 1.852, 1) if viento_kt is not None else None,
        "rachas_kmh": round(float(racha_kt) * 1.852, 1) if racha_kt is not None else None,
        "viento_dir": _direccion(r.get("wdir")),
        "presion": float(r["altim"]) if r.get("altim") is not None else None,
        "es_dia": _es_dia(ts, lugar),
    }

    _CACHE[est.icao] = (time.monotonic(), datos)
    logger.info("METAR %s: %.1f °C (%s)", est.icao, temp, datos["ts"])
    return datos
