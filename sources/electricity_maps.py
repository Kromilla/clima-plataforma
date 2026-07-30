"""
sources/electricity_maps.py — Adaptador para la intensidad de carbono.

⚠️ NO está en uso. La fuente de energía activa es `sources/xm.py`.

Se conserva como alternativa por si algún día se contrata Electricity Maps, pero
tiene dos inconvenientes frente a XM para este proyecto:
  1. Requiere API key, y su tier gratuito es ambiguo (posiblemente solo un trial
     de 14 días).
  2. La cuenta gratuita se limita a una sola zona.
XM es gratis, sin key, y es la fuente oficial de Colombia.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
import requests

from config import cfg
import storage
from sources.base import Lectura

logger = logging.getLogger(__name__)

class ElectricityMapsError(Exception):
    pass

def obtener_ultimo(lugar: dict) -> Lectura:
    """
    Retorna la intensidad de carbono actual para el lugar usando Electricity Maps.
    """
    zona_id = lugar.get("zona_electricidad", "CO")
    token = cfg.ELECTRICITY_MAPS_KEY

    if not token:
        logger.warning("ELECTRICITY_MAPS_KEY no configurado. Intentando usar caché.")
        lectura_cache = storage.ultimo_valor("electricity_maps", lugar.get("_id", "desconocido"), "intensidad_co2")
        if lectura_cache:
            return lectura_cache.como_cache()
        raise ElectricityMapsError("Sin token y sin caché para Electricity Maps")

    url = f"https://api.electricitymap.org/v3/carbon-intensity/latest?zone={zona_id}"
    headers = {"auth-token": token}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        intensidad = data.get("carbonIntensity")
        if intensidad is None:
            raise ElectricityMapsError("No se recibió carbonIntensity")

        # Intentamos obtener timestamp si la API lo da, si no la hora actual
        ts = datetime.now(timezone.utc)
        if "datetime" in data:
            try:
                ts = datetime.fromisoformat(data["datetime"].replace('Z', '+00:00'))
            except ValueError:
                pass

        lectura = Lectura(
            valor=float(intensidad),
            unidad="gCO₂eq/kWh",
            metrica="intensidad_co2",
            fuente="electricity_maps",
            procedencia="local",
            lugar_id=lugar.get("_id", "desconocido"),
            estacion_nombre=f"Zona {zona_id}",
            ts=ts
        )
        storage.guardar(lectura)
        return lectura

    except Exception as e:
        logger.warning("Electricity Maps falló para zona %s: %s", zona_id, e)
        # Intentar caché
        lectura_cache = storage.ultimo_valor("electricity_maps", lugar.get("_id", "desconocido"), "intensidad_co2")
        if lectura_cache:
            return lectura_cache.como_cache()
        raise ElectricityMapsError(f"Sin datos de intensidad CO2 para zona '{zona_id}'") from e
