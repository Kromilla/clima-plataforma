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


# Días de historial que se piden en cada llamada. La API los da gratis en la
# misma petición, así que la gráfica tiene forma desde la primera ejecución.
_DIAS_HISTORIAL = 7


class OpenMeteoAireSinDatos(Exception):
    """Se lanza cuando la API no devuelve datos válidos."""


def _parsear_serie(data: dict, lugar_id: str, estacion: str) -> list[Lectura]:
    """
    Convierte la respuesta horaria en Lecturas, descartando horas futuras.

    Con `forecast_days=1` la respuesta incluye horas que aún no han ocurrido:
    guardarlas mezclaría pronóstico con observación en el mismo historial.
    """
    horario = data.get("hourly") or {}
    tiempos = horario.get("time") or []
    valores = horario.get("pm2_5") or []
    ahora = datetime.now(timezone.utc)

    lecturas: list[Lectura] = []
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
                unidad=_UNIDAD,
                metrica=_METRICA,
                fuente="openmeteo-aire",
                procedencia="local",
                lugar_id=lugar_id,
                estacion_nombre=estacion,
                ts=ts,
            )
        )

    return lecturas


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

    estacion = f"Modelo CAMS ({lat:.2f}°N, {lon:.2f}°W)"

    try:
        resp = requests.get(
            _BASE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                # Se pide la serie horaria y no solo `current`: con un punto por
                # llamada la gráfica del dashboard tardaba días en tener forma,
                # pudiendo traer una semana de historial de una vez.
                "hourly": "pm2_5",
                "past_days": _DIAS_HISTORIAL,
                "forecast_days": 1,
                # UTC a propósito: abajo interpretamos el timestamp como UTC. Pedir
                # una zona local devolvería hora de Bogotá y el dato aparecería
                # 5 h más viejo de lo que es.
                "timezone": "UTC",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()

        lecturas = _parsear_serie(data, lugar_id, estacion)
        if not lecturas:
            raise OpenMeteoAireSinDatos("pm2_5 no disponible en la respuesta")

        nuevas = storage.guardar_muchas(lecturas)
        lectura = lecturas[-1]
        logger.info(
            "Open-Meteo Aire [modelo] PM2.5=%.1f para %s — %d horas, %d nuevas",
            lectura.valor, lugar_id, len(lecturas), nuevas,
        )
        return lectura

    except requests.RequestException as exc:
        logger.warning("Open-Meteo Aire falló para %s: %s", lugar_id, exc)
        # Intentar caché
        lectura_cache = storage.ultimo_valor("openmeteo-aire", lugar_id, _METRICA)
        if lectura_cache:
            logger.info("Open-Meteo Aire [caché] para %s", lugar_id)
            return lectura_cache.como_cache()
        raise OpenMeteoAireSinDatos(
            f"Sin datos de calidad del aire para '{lugar_id}'"
        ) from exc
