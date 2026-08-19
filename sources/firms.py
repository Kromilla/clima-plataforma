"""
sources/firms.py — Adaptador de focos de calor (incendios) vía NASA FIRMS.

FIRMS publica detecciones de focos de calor de los satélites VIIRS y MODIS casi
en tiempo real (~3 h desde la pasada del satélite).

Requiere una MAP_KEY gratuita: https://firms.modaps.eosdis.nasa.gov/api/map_key/
Si no está configurada, la fuente se degrada como cualquier otra (caché → sin
datos) en vez de romper el dashboard.

Dos interfaces:
    obtener_ultimo(lugar) -> Lectura   # cantidad de focos, para el registro/semáforo
    obtener_focos(lugar)  -> list[Foco] # detalle geográfico, para el mapa

La primera respeta el contrato común de `sources/base.py`; la segunda existe
porque un mapa necesita los puntos, no un escalar.

Nota sobre "confidence": VIIRS reporta low/nominal/high y MODIS un porcentaje
0-100. Se normaliza a una escala común para poder filtrar igual en ambos.
"""
from __future__ import annotations

import csv
import io
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt

import requests

import storage
from config import cfg
from sources.base import Lectura

logger = logging.getLogger(__name__)

_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
_FUENTE = "firms"
_METRICA = "focos_activos"
_UNIDAD = "focos"
# VIIRS (375 m) de los tres satélites: S-NPP + NOAA-20 + NOAA-21. Cada uno pasa
# ~2 veces/día, así que juntarlos multiplica la cobertura temporal (usar solo uno
# se perdía focos que los otros sí veían, como los que muestra el IDEAM).
_SATELITES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
_DIAS = 2          # "focos de las últimas 24-48h" (§6, Fase 3)
_DIAS_MAX = 10     # límite duro de la API

# Cache breve de focos por (bbox, días): el collector consulta FIRMS al recolectar
# y el notificador otra vez en la misma pasada. VIIRS actualiza ~2 veces/día, así
# que reusar unos minutos elimina la llamada duplicada sin perder frescura.
_CACHE_FOCOS: dict[str, tuple[float, list]] = {}
_CACHE_TTL_SEG = 900


class FirmsSinDatos(Exception):
    """Se lanza cuando no hay dato ni en la API ni en caché."""


class FirmsSinClave(FirmsSinDatos):
    """No hay FIRMS_MAP_KEY configurada."""


@dataclass(frozen=True)
class Foco:
    """Una detección de foco de calor."""

    lat: float
    lon: float
    # Potencia radiativa del fuego en megavatios: proxy de intensidad.
    frp: float
    confianza: str            # "baja" | "nominal" | "alta"
    ts: datetime
    satelite: str
    dia_noche: str            # "D" | "N"
    distancia_km: float = 0.0  # al centro del lugar; lo llena obtener_focos()

    @property
    def es_significativo(self) -> bool:
        """Descarta detecciones de baja confianza para avisos al usuario."""
        return self.confianza != "baja"


def _normalizar_confianza(valor: str) -> str:
    """
    Unifica la confianza de VIIRS (low/nominal/high) y MODIS (0-100).
    """
    v = (valor or "").strip().lower()
    if v in ("l", "low"):
        return "baja"
    if v in ("n", "nominal"):
        return "nominal"
    if v in ("h", "high"):
        return "alta"
    try:
        pct = float(v)
    except ValueError:
        return "nominal"
    if pct < 30:
        return "baja"
    if pct < 80:
        return "nominal"
    return "alta"


def _parsear_ts(acq_date: str, acq_time: str) -> datetime:
    """
    Combina acq_date (YYYY-MM-DD) y acq_time (HHMM, UTC) en un datetime.
    acq_time viene sin ceros a la izquierda en algunos casos ("315" = 03:15).
    """
    hhmm = (acq_time or "0").strip().zfill(4)
    try:
        return datetime.strptime(f"{acq_date} {hhmm}", "%Y-%m-%d %H%M").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return datetime.now(timezone.utc)


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia haversine en kilómetros."""
    r = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * r * asin(sqrt(a))


def parsear_csv(texto: str) -> list[Foco]:
    """
    Convierte el CSV de FIRMS en una lista de Foco.

    Se lee por nombre de cabecera, no por posición: FIRMS agrega columnas
    (country_id, por ejemplo) según el endpoint, y depender del orden rompería
    el parser en silencio.
    """
    focos: list[Foco] = []
    lector = csv.DictReader(io.StringIO(texto.strip()))

    for fila in lector:
        try:
            lat = float(fila["latitude"])
            lon = float(fila["longitude"])
        except (KeyError, ValueError, TypeError):
            continue  # fila corrupta: la saltamos en vez de tumbar todo

        try:
            frp = float(fila.get("frp") or 0.0)
        except ValueError:
            frp = 0.0

        focos.append(
            Foco(
                lat=lat,
                lon=lon,
                frp=frp,
                confianza=_normalizar_confianza(fila.get("confidence", "")),
                ts=_parsear_ts(fila.get("acq_date", ""), fila.get("acq_time", "")),
                satelite=fila.get("satellite", "?"),
                dia_noche=(fila.get("daynight") or "?").strip().upper(),
            )
        )

    return focos


def _fusionar(focos: list[Foco]) -> list[Foco]:
    """
    Junta detecciones de varios satélites en un foco por ubicación y día.

    Distintos satélites ven el mismo incendio en pasadas distintas; se colapsan a
    un punto (~100 m) por día, quedándose con el de mayor FRP (potencia).
    """
    por_clave: dict[tuple, Foco] = {}
    for f in focos:
        clave = (round(f.lat, 3), round(f.lon, 3), f.ts.strftime("%Y-%m-%d"))
        previo = por_clave.get(clave)
        if previo is None or f.frp > previo.frp:
            por_clave[clave] = f
    return list(por_clave.values())


# Contorno de Colombia (lon, lat), simplificado de un GeoJSON oficial. Se usa para
# filtrar la vista nacional: FIRMS devuelve un rectángulo que incluye focos de
# Venezuela, Panamá y Ecuador; con esto solo se muestran los de Colombia.
_POLIGONO_COLOMBIA = (
    (-75.373, -0.152), (-75.801, 0.085), (-76.292, 0.416), (-76.576, 0.257),
    (-77.425, 0.396), (-77.669, 0.826), (-77.855, 0.81), (-78.855, 1.381),
    (-78.991, 1.691), (-78.618, 1.766), (-78.662, 2.267), (-78.428, 2.63),
    (-77.932, 2.697), (-77.51, 3.325), (-77.128, 3.85), (-77.496, 4.088),
    (-77.308, 4.668), (-77.533, 5.583), (-77.319, 5.845), (-77.477, 6.691),
    (-77.882, 7.224), (-77.753, 7.71), (-77.431, 7.638), (-77.243, 7.935),
    (-77.475, 8.524), (-77.353, 8.671), (-76.837, 8.639), (-76.086, 9.337),
    (-75.675, 9.443), (-75.665, 9.774), (-75.48, 10.619), (-74.907, 11.083),
    (-74.277, 11.102), (-74.197, 11.31), (-73.415, 11.227), (-72.628, 11.732),
    (-72.238, 11.956), (-71.754, 12.437), (-71.4, 12.376), (-71.137, 12.113),
    (-71.332, 11.776), (-71.974, 11.609), (-72.228, 11.109), (-72.615, 10.822),
    (-72.905, 10.45), (-73.028, 9.737), (-73.305, 9.152), (-72.789, 9.085),
    (-72.66, 8.625), (-72.44, 8.405), (-72.361, 8.003), (-72.48, 7.633),
    (-72.444, 7.424), (-72.198, 7.34), (-71.96, 6.992), (-70.674, 7.088),
    (-70.093, 6.96), (-69.389, 6.1), (-68.985, 6.207), (-68.265, 6.153),
    (-67.695, 6.267), (-67.341, 6.095), (-67.522, 5.557), (-67.745, 5.221),
    (-67.823, 4.504), (-67.622, 3.839), (-67.338, 3.542), (-67.303, 3.318),
    (-67.81, 2.821), (-67.447, 2.6), (-67.181, 2.251), (-66.876, 1.253),
    (-67.065, 1.13), (-67.26, 1.72), (-67.538, 2.037), (-67.869, 1.692),
    (-69.817, 1.715), (-69.805, 1.089), (-69.219, 0.986), (-69.252, 0.603),
    (-69.452, 0.706), (-70.016, 0.541), (-70.021, -0.185), (-69.577, -0.55),
    (-69.42, -1.123), (-69.444, -1.556), (-69.894, -4.298), (-70.394, -3.767),
    (-70.693, -3.743), (-70.048, -2.725), (-70.813, -2.257), (-71.414, -2.343),
    (-71.775, -2.17), (-72.326, -2.434), (-73.07, -2.309), (-73.66, -1.26),
    (-74.122, -1.003), (-74.442, -0.531), (-75.107, -0.057), (-75.373, -0.152),
)


def _dentro_de_colombia(lon: float, lat: float) -> bool:
    """Point-in-polygon (ray casting) contra el contorno de Colombia."""
    p = _POLIGONO_COLOMBIA
    dentro = False
    j = len(p) - 1
    for i in range(len(p)):
        xi, yi = p[i]
        xj, yj = p[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def obtener_focos(lugar: dict, dias: int = _DIAS, sensores: tuple = _SATELITES) -> list[Foco]:
    """
    Devuelve los focos dentro del bbox del lugar, ordenados por cercanía.

    Raises:
        FirmsSinClave: si falta FIRMS_MAP_KEY
        FirmsSinDatos: si la API falla
    """
    if not cfg.FIRMS_MAP_KEY:
        raise FirmsSinClave(
            "Falta FIRMS_MAP_KEY en el .env. "
            "Consíguela gratis en https://firms.modaps.eosdis.nasa.gov/api/map_key/"
        )

    lon_min, lat_min, lon_max, lat_max = lugar["bbox"]
    area = f"{lon_min},{lat_min},{lon_max},{lat_max}"
    dias = max(1, min(dias, _DIAS_MAX))

    clave = f"{area}/{dias}/{','.join(sensores)}"
    en_cache = _CACHE_FOCOS.get(clave)
    if en_cache is not None and (time.monotonic() - en_cache[0]) < _CACHE_TTL_SEG:
        return list(en_cache[1])

    # Se consulta cada satélite pedido y se fusionan. Si uno falla se sigue con los
    # demás; solo se considera caída si fallan todos. Timeout corto a propósito:
    # FIRMS es intermitente desde CI y el collector (14 ciudades) no puede colgarse.
    crudos: list[Foco] = []
    fallos = 0
    for sat in sensores:
        url = f"{_BASE_URL}/{cfg.FIRMS_MAP_KEY}/{sat}/{area}/{dias}"
        try:
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("FIRMS %s no respondió: %s", sat, exc)
            fallos += 1
            continue
        texto = resp.text.strip()
        # FIRMS devuelve 200 con un mensaje de error en texto plano si la key es mala.
        if texto.lower().startswith("invalid"):
            raise FirmsSinClave(f"FIRMS rechazó la MAP_KEY: {texto[:100]}")
        crudos.extend(parsear_csv(texto))

    if fallos == len(sensores):
        raise FirmsSinDatos("FIRMS no respondió (ningún satélite disponible)")

    focos = _fusionar(crudos)

    centro_lat, centro_lon = lugar["lat"], lugar["lon"]
    focos = [
        Foco(
            lat=f.lat, lon=f.lon, frp=f.frp, confianza=f.confianza, ts=f.ts,
            satelite=f.satelite, dia_noche=f.dia_noche,
            distancia_km=round(distancia_km(centro_lat, centro_lon, f.lat, f.lon), 1),
        )
        for f in focos
    ]
    # Vista nacional (lugar con "pais"): descarta focos fuera del contorno de
    # Colombia — el bbox de FIRMS es un rectángulo que abarca países vecinos.
    if lugar.get("pais"):
        focos = [f for f in focos if _dentro_de_colombia(f.lon, f.lat)]
    focos.sort(key=lambda f: f.distancia_km)
    _CACHE_FOCOS[clave] = (time.monotonic(), list(focos))
    return focos


def obtener_ultimo(lugar: dict) -> Lectura:
    """
    Retorna la cantidad de focos activos como Lectura, para encajar en el
    contrato común (registro, semáforo, historial). El detalle de cada foco se
    obtiene con obtener_focos().
    """
    lugar_id = lugar.get("_id", "desconocido")

    try:
        # El conteo del semáforo usa un solo satélite (rápido); el mapa on-demand
        # sí consulta los tres. Así el collector de 14 ciudades no se cuelga.
        focos = obtener_focos(lugar, sensores=(_SATELITES[0],))
        # El timestamp es el de la detección más reciente, no "ahora": así la
        # antigüedad refleja cuándo pasó el satélite de verdad.
        ts = max((f.ts for f in focos), default=datetime.now(timezone.utc))

        lectura = Lectura(
            valor=float(len(focos)),
            unidad=_UNIDAD,
            metrica=_METRICA,
            fuente=_FUENTE,
            # Detección real, pero desde órbita: no hay estación en tierra.
            procedencia="satelite",
            lugar_id=lugar_id,
            estacion_nombre="NASA FIRMS / VIIRS S-NPP",
            ts=ts,
        )
        storage.guardar(lectura)
        logger.info("FIRMS: %d focos en %s", len(focos), lugar_id)
        return lectura

    except FirmsSinDatos as exc:
        logger.warning("FIRMS falló para %s: %s", lugar_id, exc)
        lectura_cache = storage.ultimo_valor(_FUENTE, lugar_id, _METRICA)
        if lectura_cache is not None:
            return lectura_cache.como_cache()
        raise
