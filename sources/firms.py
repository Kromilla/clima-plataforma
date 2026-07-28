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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
# VIIRS S-NPP tiene 375 m de resolución: mejor que MODIS (1 km) para focos chicos.
_SATELITE = "VIIRS_SNPP_NRT"
_DIAS = 2          # "focos de las últimas 24-48h" (§6, Fase 3)
_DIAS_MAX = 10     # límite duro de la API


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


def obtener_focos(lugar: dict, dias: int = _DIAS) -> list[Foco]:
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

    url = f"{_BASE_URL}/{cfg.FIRMS_MAP_KEY}/{_SATELITE}/{area}/{dias}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise FirmsSinDatos(f"FIRMS no respondió: {exc}") from exc

    texto = resp.text.strip()
    # FIRMS devuelve 200 con un mensaje de error en texto plano si la key es mala.
    if texto.lower().startswith("invalid"):
        raise FirmsSinClave(f"FIRMS rechazó la MAP_KEY: {texto[:100]}")

    focos = parsear_csv(texto)

    centro_lat, centro_lon = lugar["lat"], lugar["lon"]
    focos = [
        Foco(
            lat=f.lat, lon=f.lon, frp=f.frp, confianza=f.confianza, ts=f.ts,
            satelite=f.satelite, dia_noche=f.dia_noche,
            distancia_km=round(distancia_km(centro_lat, centro_lon, f.lat, f.lon), 1),
        )
        for f in focos
    ]
    focos.sort(key=lambda f: f.distancia_km)
    return focos


def obtener_ultimo(lugar: dict) -> Lectura:
    """
    Retorna la cantidad de focos activos como Lectura, para encajar en el
    contrato común (registro, semáforo, historial). El detalle de cada foco se
    obtiene con obtener_focos().
    """
    lugar_id = lugar.get("_id", "desconocido")

    try:
        focos = obtener_focos(lugar)
        # El timestamp es el de la detección más reciente, no "ahora": así la
        # antigüedad refleja cuándo pasó el satélite de verdad.
        ts = max((f.ts for f in focos), default=datetime.now(timezone.utc))

        lectura = Lectura(
            valor=float(len(focos)),
            unidad=_UNIDAD,
            metrica=_METRICA,
            fuente=_FUENTE,
            procedencia="local",
            lugar_id=lugar_id,
            estacion_nombre=f"NASA FIRMS / {_SATELITE}",
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
