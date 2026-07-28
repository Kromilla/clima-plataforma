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

# Días de historial que se piden en cada llamada; vienen en la misma petición.
_DIAS_HISTORIAL = 7

# Qué variable de la API corresponde a qué métrica nuestra.
_VARIABLES = {
    "temperature_2m": ("temperatura", "°C"),
    "relative_humidity_2m": ("humedad", "%"),
}


class OpenMeteoClimaError(Exception):
    pass


def _parsear_serie(data: dict, lugar_id: str, estacion: str) -> list[Lectura]:
    """
    Convierte la respuesta horaria en Lecturas, descartando horas futuras.

    Con `forecast_days=1` la respuesta trae horas que aún no han ocurrido, y
    guardarlas mezclaría pronóstico con observación — algo especialmente dañino
    aquí, porque este historial es el que entrena el predictor de la Fase 4.
    """
    horario = data.get("hourly") or {}
    tiempos = horario.get("time") or []
    ahora = datetime.now(timezone.utc)

    lecturas: list[Lectura] = []
    for variable, (metrica, unidad) in _VARIABLES.items():
        valores = horario.get(variable) or []

        for ts_str, valor in zip(tiempos, valores):
            if valor is None:
                continue
            try:
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if ts > ahora:
                break  # a partir de aquí es pronóstico

            lecturas.append(
                Lectura(
                    valor=float(valor),
                    unidad=unidad,
                    metrica=metrica,
                    fuente="openmeteo-clima",
                    procedencia="local",
                    lugar_id=lugar_id,
                    estacion_nombre=estacion,
                    ts=ts,
                )
            )

    return lecturas

def obtener_ultimo(lugar: dict) -> Lectura:
    """
    Retorna la temperatura actual para el lugar usando Open-Meteo Weather API.
    """
    lugar_id = lugar.get("_id", "desconocido")
    lat = lugar["lat"]
    lon = lugar["lon"]

    estacion = f"Open-Meteo ({lat:.2f}°N, {lon:.2f}°W)"

    try:
        resp = requests.get(
            _BASE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                # Serie horaria en vez de un solo punto: la API la da en la misma
                # llamada y así el historial no tarda días en formarse.
                # La humedad va junto porque risk.py la necesita para el índice
                # de calor, y sin ella el historial reciente queda incompleto
                # justo donde mira el predictor.
                "hourly": "temperature_2m,relative_humidity_2m",
                "past_days": _DIAS_HISTORIAL,
                "forecast_days": 1,
                # UTC a propósito: ver nota en openmeteo_aire.py.
                "timezone": "UTC",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        lecturas = _parsear_serie(data, lugar_id, estacion)
        temperaturas = [lec for lec in lecturas if lec.metrica == "temperatura"]
        if not temperaturas:
            raise OpenMeteoClimaError("temperatura no disponible")

        nuevas = storage.guardar_muchas(lecturas)
        lectura = temperaturas[-1]
        logger.info(
            "Open-Meteo Clima temp=%.1f °C para %s — %d lecturas, %d nuevas",
            lectura.valor, lugar_id, len(lecturas), nuevas,
        )
        return lectura

    except Exception as exc:
        logger.warning("Open-Meteo Clima falló para %s: %s", lugar_id, exc)
        lectura_cache = storage.ultimo_valor("openmeteo-clima", lugar_id, "temperatura")
        if lectura_cache:
            return lectura_cache.como_cache()
        raise OpenMeteoClimaError(f"Sin datos de clima para '{lugar_id}'") from exc
