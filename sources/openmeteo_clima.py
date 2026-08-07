"""
sources/openmeteo_clima.py — Adaptador para clima básico (Temperatura, Humedad, etc.) usando Open-Meteo.
"""
from __future__ import annotations

import logging
import time
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
            timeout=8,
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


class ClimaActualError(Exception):
    pass


_CAMPOS_ACTUAL = (
    "temperature_2m", "apparent_temperature", "relative_humidity_2m",
    "precipitation", "weather_code", "cloud_cover",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
    "surface_pressure", "is_day",
)

# Caché por punto (lat/lon redondeados a ~1 km) para no pegarle a Open-Meteo en
# cada refresco ni por cada usuario: el clima no cambia en 2 minutos, y el tier
# gratis devuelve 429 (Too Many Requests) si la IP de Render se pasa de cuota.
_CACHE_ACTUAL: dict[tuple[float, float], tuple[float, dict]] = {}
_CACHE_TTL_SEG = 120


def condiciones_actuales(lugar: dict) -> dict:
    """
    Condiciones meteorológicas actuales (en vivo) de Open-Meteo, para la vista de
    clima en tiempo real. No se persiste: es una foto del momento.

    Cachea por punto durante _CACHE_TTL_SEG para respetar el límite de Open-Meteo.

    Raises:
        ClimaActualError: si la API falla o no trae el bloque `current`.
    """
    clave = (round(lugar["lat"], 2), round(lugar["lon"], 2))
    cacheado = _CACHE_ACTUAL.get(clave)
    if cacheado and time.monotonic() - cacheado[0] < _CACHE_TTL_SEG:
        return cacheado[1]

    try:
        resp = requests.get(
            _BASE_URL,
            params={
                "latitude": lugar["lat"],
                "longitude": lugar["lon"],
                "current": ",".join(_CAMPOS_ACTUAL),
                "wind_speed_unit": "kmh",
                "timezone": "UTC",
            },
            timeout=8,
        )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            raise ClimaActualError(
                "Demasiadas consultas a Open-Meteo ahora mismo. Reintenta en un minuto."
            ) from exc
        raise ClimaActualError(f"Open-Meteo no respondió: {exc}") from exc
    except requests.RequestException as exc:
        raise ClimaActualError(f"Open-Meteo no respondió: {exc}") from exc

    actual = (resp.json() or {}).get("current") or {}
    if actual.get("temperature_2m") is None:
        raise ClimaActualError("Open-Meteo respondió sin condiciones actuales")

    datos = {
        "ts": actual.get("time"),
        "temperatura": actual.get("temperature_2m"),
        "sensacion": actual.get("apparent_temperature"),
        "humedad": actual.get("relative_humidity_2m"),
        "precipitacion": actual.get("precipitation"),
        "codigo": actual.get("weather_code"),
        "nubosidad": actual.get("cloud_cover"),
        "viento_kmh": actual.get("wind_speed_10m"),
        "rachas_kmh": actual.get("wind_gusts_10m"),
        "viento_dir": actual.get("wind_direction_10m"),
        "presion": actual.get("surface_pressure"),
        "es_dia": bool(actual.get("is_day")),
    }
    _CACHE_ACTUAL[clave] = (time.monotonic(), datos)
    return datos
