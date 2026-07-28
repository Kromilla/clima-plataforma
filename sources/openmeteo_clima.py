"""
sources/openmeteo_clima.py — Adaptador para clima básico (Temperatura, Humedad, etc.) usando Open-Meteo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
import requests

import storage
from sources.base import Lectura

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"

class OpenMeteoClimaError(Exception):
    pass

def obtener_ultimo(lugar: dict) -> Lectura:
    """
    Retorna la temperatura actual para el lugar usando Open-Meteo Weather API.
    """
    lugar_id = lugar.get("_id", "desconocido")
    lat = lugar["lat"]
    lon = lugar["lon"]

    try:
        resp = requests.get(
            _BASE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                # La humedad se guarda como métrica secundaria: risk.py la
                # necesita para el índice de calor, y sin ella el historial
                # reciente queda incompleto justo donde el predictor mira.
                "current": "temperature_2m,relative_humidity_2m",
                # UTC a propósito: ver nota en openmeteo_aire.py.
                "timezone": "UTC",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        temp_val = current.get("temperature_2m")
        ts_str = current.get("time", "")

        if temp_val is None:
            raise OpenMeteoClimaError("temperatura no disponible")

        try:
            ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            ts = datetime.now(timezone.utc)

        estacion = f"Open-Meteo ({lat:.2f}°N, {lon:.2f}°W)"

        lectura = Lectura(
            valor=float(temp_val),
            unidad="°C",
            metrica="temperatura",
            fuente="openmeteo-clima",
            procedencia="local",
            lugar_id=lugar_id,
            estacion_nombre=estacion,
            ts=ts,
        )
        storage.guardar(lectura)

        # Métrica secundaria. La temperatura es la que reporta el semáforo; la
        # humedad se persiste igual porque el predictor de la Fase 4 la usa.
        humedad = current.get("relative_humidity_2m")
        if humedad is not None:
            storage.guardar(
                Lectura(
                    valor=float(humedad),
                    unidad="%",
                    metrica="humedad",
                    fuente="openmeteo-clima",
                    procedencia="local",
                    lugar_id=lugar_id,
                    estacion_nombre=estacion,
                    ts=ts,
                )
            )

        return lectura

    except Exception as exc:
        logger.warning("Open-Meteo Clima falló para %s: %s", lugar_id, exc)
        lectura_cache = storage.ultimo_valor("openmeteo-clima", lugar_id, "temperatura")
        if lectura_cache:
            return lectura_cache
        raise OpenMeteoClimaError(f"Sin datos de clima para '{lugar_id}'") from exc
