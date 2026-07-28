"""
sources/openmeteo_aire.py — Adaptador de calidad del aire via Open-Meteo Air Quality API.

Open-Meteo tiene cobertura GLOBAL (incluye Santa Marta) y NO requiere API key.
Usa el modelo Copernicus CAMS para PM2.5, PM10, NO2, O3.

Documentación: https://air-quality-api.open-meteo.com/

Esta fuente actúa como fuente primaria de PM2.5 cuando OpenAQ no tiene
cobertura local (como en Santa Marta/Barranquilla).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from sources.base import Lectura

logger = logging.getLogger(__name__)

_BASE_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
_METRICA = "pm25"
_UNIDAD = "µg/m³"


class OpenMeteoAireSinDatos(Exception):
    """Se lanza cuando la API no devuelve datos válidos."""


def obtener_ultimo(lugar: dict) -> Lectura:
    """
    Retorna PM2.5 actual para el lugar usando Open-Meteo Air Quality.

    Open-Meteo no requiere API key y cubre cualquier coordenada del mundo.
    Los datos son de modelo (Copernicus CAMS), no de estación física.

    Args:
        lugar: dict de LUGARES con 'lat', 'lon', '_id'
    """
    import storage  # lazy import

    lugar_id = lugar.get("_id", "desconocido")
    lat = lugar["lat"]
    lon = lugar["lon"]

    try:
        resp = requests.get(
            _BASE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,ozone,dust",
                # UTC a propósito: abajo interpretamos el timestamp como UTC. Pedir
                # una zona local devolvería hora de Bogotá y el dato aparecería
                # 5 h más viejo de lo que es.
                "timezone": "UTC",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        pm25_val = current.get("pm2_5")
        ts_str = current.get("time", "")

        if pm25_val is None:
            raise OpenMeteoAireSinDatos("pm2_5 no disponible en la respuesta")

        try:
            ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            ts = datetime.now(timezone.utc)

        lectura = Lectura(
            valor=float(pm25_val),
            unidad=_UNIDAD,
            metrica=_METRICA,
            fuente="openmeteo-aire",
            procedencia="local",
            lugar_id=lugar_id,
            estacion_nombre=f"Modelo CAMS ({lat:.2f}°N, {lon:.2f}°W)",
            ts=ts,
        )
        storage.guardar(lectura)
        logger.info(
            "Open-Meteo Aire [modelo] PM2.5=%.1f para %s", lectura.valor, lugar_id
        )
        return lectura

    except requests.RequestException as exc:
        logger.warning("Open-Meteo Aire falló para %s: %s", lugar_id, exc)
        # Intentar caché
        lectura_cache = storage.ultimo_valor("openmeteo-aire", lugar_id, _METRICA)
        if lectura_cache:
            logger.info("Open-Meteo Aire [caché] para %s", lugar_id)
            return lectura_cache
        raise OpenMeteoAireSinDatos(
            f"Sin datos de calidad del aire para '{lugar_id}'"
        ) from exc
