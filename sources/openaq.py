"""
sources/openaq.py — Adaptador para OpenAQ API v3.

Cascada de fallback (nunca crashea):
    1. Estación LOCAL dentro del bbox del lugar
    2. Estación FALLBACK (Barranquilla u otra en locations.py)
    3. Último valor en CACHÉ (SQLite)

Si ninguna capa funciona y no hay caché, lanza OpenAQSinDatos (caso extremo
que bot.py captura y convierte a mensaje amigable).

Reintentos: 3 intentos por intento, con espera creciente: 1 s, 3 s, 9 s.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

import storage
from config import cfg
from locations import LUGARES
from sources.base import Lectura

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────
_BASE_URL = "https://api.openaq.org/v3"
_METRICA = "pm25"
_UNIDAD = "µg/m³"
_INTENTOS = 3
_ESPERAS = [1, 3, 9]  # segundos entre reintentos


class OpenAQSinDatos(Exception):
    """Se lanza cuando no hay dato ni en la API ni en caché."""


# ── Helpers internos ──────────────────────────────────────────────────────────

def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def _consultar_bbox(bbox: tuple, api_key: str) -> list[dict]:
    """
    Consulta locations + mediciones recientes dentro de un bbox.
    Devuelve lista de mediciones con campo 'value', 'stationName', 'date'.
    Lanza requests.RequestException si todos los reintentos fallan.
    """
    lon_min, lat_min, lon_max, lat_max = bbox

    for intento in range(_INTENTOS):
        try:
            # Paso 1: buscar estaciones dentro del bbox
            resp = requests.get(
                f"{_BASE_URL}/locations",
                params={
                    "bbox": f"{lon_min},{lat_min},{lon_max},{lat_max}",
                    "limit": 10,
                },
                headers=_headers(api_key),
                timeout=10,
            )
            resp.raise_for_status()
            locations = resp.json().get("results", [])

            if not locations:
                return []

            # Paso 2: obtener la medición más reciente de PM2.5 de la primera estación
            loc_id = locations[0]["id"]
            loc_nombre = locations[0].get("name", str(loc_id))

            resp2 = requests.get(
                f"{_BASE_URL}/locations/{loc_id}/measurements",
                params={"parameter": "pm25", "limit": 1},
                headers=_headers(api_key),
                timeout=10,
            )
            resp2.raise_for_status()
            mediciones = resp2.json().get("results", [])

            # Adjuntar nombre de estación para trazabilidad
            for m in mediciones:
                m["stationName"] = loc_nombre
            return mediciones

        except requests.RequestException as exc:
            if intento < _INTENTOS - 1:
                espera = _ESPERAS[intento]
                logger.warning(
                    "OpenAQ intento %d/%d falló (%s). Esperando %ds…",
                    intento + 1, _INTENTOS, exc, espera,
                )
                time.sleep(espera)
            else:
                logger.error("OpenAQ: todos los reintentos agotados: %s", exc)
                raise

    return []


def _medicion_a_lectura(
    medicion: dict, procedencia: str, lugar_id: str
) -> Lectura:
    """Convierte un dict de la API en un objeto Lectura."""
    ts_raw = medicion.get("date", {}).get("utc", "")
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        ts = datetime.now(timezone.utc)

    return Lectura(
        valor=float(medicion["value"]),
        unidad=_UNIDAD,
        metrica=_METRICA,
        fuente="openaq",
        procedencia=procedencia,
        lugar_id=lugar_id,
        estacion_nombre=medicion.get("stationName", ""),
        ts=ts,
    )


# ── Función pública principal ─────────────────────────────────────────────────

def obtener_ultimo(lugar: dict) -> Lectura:
    """
    Retorna la lectura de PM2.5 más reciente para el lugar dado.

    Nunca lanza excepción al caller salvo OpenAQSinDatos (cuando ni la API
    ni el caché tienen datos — situación de bootstrapping o lugar sin cobertura).

    Args:
        lugar: Diccionario de LUGARES (locations.py). Debe tener:
               'bbox', 'fallback_openaq' (opcional), y el lugar_id se
               infiere del campo 'nombre' o se pasa por el llamador.
    """
    lugar_id: str = lugar.get("_id", "desconocido")
    bbox: tuple = lugar["bbox"]
    fallback_id: str | None = lugar.get("fallback_openaq")

    # ── Capa 1: estación local ────────────────────────────────────────────
    try:
        mediciones = _consultar_bbox(bbox, cfg.OPENAQ_API_KEY)
        if mediciones:
            lectura = _medicion_a_lectura(mediciones[0], "local", lugar_id)
            storage.guardar(lectura)
            logger.info("OpenAQ [local] PM2.5=%.1f para %s", lectura.valor, lugar_id)
            return lectura
        logger.info("OpenAQ: sin estaciones locales para %s — intentando fallback", lugar_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAQ capa 1 falló: %s", exc)

    # ── Capa 2: estación fallback (Barranquilla u otra) ───────────────────
    if fallback_id:
        # Buscamos el lugar de fallback en LUGARES para obtener su bbox
        lugar_fb = LUGARES.get(fallback_id)
        if lugar_fb:
            try:
                mediciones_fb = _consultar_bbox(lugar_fb["bbox"], cfg.OPENAQ_API_KEY)
                if mediciones_fb:
                    lectura_fb = _medicion_a_lectura(mediciones_fb[0], "fallback", lugar_id)
                    lectura_fb.estacion_nombre = (
                        lugar_fb.get("nombre", fallback_id)
                    )
                    storage.guardar(lectura_fb)
                    logger.info(
                        "OpenAQ [fallback=%s] PM2.5=%.1f para %s",
                        fallback_id, lectura_fb.valor, lugar_id,
                    )
                    return lectura_fb
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenAQ capa 2 (fallback) falló: %s", exc)

    # ── Capa 3: caché SQLite ──────────────────────────────────────────────
    lectura_cache = storage.ultimo_valor("openaq", lugar_id, _METRICA)
    if lectura_cache is not None:
        logger.info(
            "OpenAQ [caché] PM2.5=%.1f (hace %d min) para %s",
            lectura_cache.valor, lectura_cache.antiguedad_min, lugar_id,
        )
        return lectura_cache

    # ── Sin datos en ninguna capa ─────────────────────────────────────────
    raise OpenAQSinDatos(
        f"No hay datos de PM2.5 para '{lugar_id}': "
        "API caída y sin caché disponible."
    )
