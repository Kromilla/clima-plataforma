"""
sources/xm.py — Adaptador de intensidad de carbono de la red eléctrica colombiana.

Fuente: XM S.A. E.S.P., el operador oficial del mercado eléctrico de Colombia.
API pública, SIN registro y SIN API key: https://servapibi.xm.com.co

Métrica usada: `factorEmisionCO2e` — "Emisiones de CO2 Eq/kWh por Sistema",
horaria, en gCO₂eq/kWh. Es el equivalente directo del "carbon intensity" de
Electricity Maps, pero oficial para Colombia y sin límite de zonas.

Por qué XM y no Electricity Maps:
    El tier gratuito de Electricity Maps resultó ambiguo (posiblemente solo un
    trial de 14 días) y limita la cuenta a una sola zona. XM es gratis de forma
    permanente, es la fuente primaria de la que se derivan los datos de Colombia,
    y no requiere gestionar credenciales.

Nota sobre el rezago: XM publica con ~2-3 días de retraso. La lectura se etiqueta
con su timestamp real, así que `antiguedad_min` y la UI muestran la antigüedad
honestamente en vez de fingir que es un dato en tiempo real.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import requests

import storage
from sources.base import Lectura

logger = logging.getLogger(__name__)

_URL = "https://servapibi.xm.com.co/hourly"
_METRICA = "intensidad_co2"
_UNIDAD = "gCO₂eq/kWh"
_FUENTE = "xm"
# XM publica con rezago; pedimos una ventana amplia y usamos el dato más reciente.
_DIAS_VENTANA = 7
# Colombia = UTC-5, sin horario de verano.
_TZ_COLOMBIA = timezone(timedelta(hours=-5))

# La serie es NACIONAL (idéntica para todas las ciudades): se cachea por pasada
# para no repetir el POST 14 veces (una por ciudad) en el collector.
_CACHE_SERIE: tuple[float, list[tuple[datetime, float]]] | None = None
_CACHE_TTL_SEG = 900


class XMSinDatos(Exception):
    """Se lanza cuando no hay dato ni en la API ni en caché."""


def _parsear_serie(items: list[dict]) -> list[tuple[datetime, float]]:
    """
    Convierte la respuesta de XM en una serie horaria completa, ordenada.

    Formato de XM: cada día trae un dict `Values` con claves Hour01..Hour24,
    donde Hour01 = 00:00-01:00 y Hour24 = 23:00-24:00 hora local de Colombia.
    Los días parciales simplemente traen menos claves Hour*.

    Se devuelve la serie entera y no solo el último punto: una sola llamada trae
    ~120 horas de datos, y quedarse con una sola dejaba la gráfica del dashboard
    permanentemente vacía por más que corriera el recolector.
    """
    serie: list[tuple[datetime, float]] = []

    for item in items:
        entidades = item.get("HourlyEntities") or []
        if not entidades:
            continue
        valores = entidades[0].get("Values") or {}

        try:
            dia = date.fromisoformat(item["Date"])
        except (ValueError, KeyError, TypeError):
            continue

        for clave, crudo in valores.items():
            if not clave.startswith("Hour"):
                continue
            try:
                valor = float(crudo)
                hora_idx = int(clave.removeprefix("Hour"))  # 1..24
            except (ValueError, TypeError):
                continue
            if not 1 <= hora_idx <= 24:
                continue

            # Hour01 cubre 00:00-01:00 → se ancla al inicio del intervalo.
            ts = datetime(
                dia.year, dia.month, dia.day, tzinfo=_TZ_COLOMBIA
            ) + timedelta(hours=hora_idx - 1)
            serie.append((ts.astimezone(timezone.utc), valor))

    serie.sort(key=lambda par: par[0])
    return serie


def _ultima_hora_disponible(items: list[dict]) -> tuple[datetime, float] | None:
    """Última hora con dato, o None si no hay ninguna."""
    serie = _parsear_serie(items)
    return serie[-1] if serie else None


def _serie_nacional() -> list[tuple[datetime, float]]:
    """
    Serie horaria de intensidad de carbono del sistema nacional, cacheada por
    pasada. XM reporta a nivel país, así que las 14 ciudades comparten el dato;
    sin caché se repetiría el mismo POST 14 veces por pasada del collector.
    """
    global _CACHE_SERIE
    ahora = time.monotonic()
    if _CACHE_SERIE is not None and (ahora - _CACHE_SERIE[0]) < _CACHE_TTL_SEG:
        return _CACHE_SERIE[1]

    hoy = datetime.now(_TZ_COLOMBIA).date()
    inicio = hoy - timedelta(days=_DIAS_VENTANA)
    resp = requests.post(
        _URL,
        json={
            "MetricId": "factorEmisionCO2e",
            "StartDate": inicio.isoformat(),
            "EndDate": hoy.isoformat(),
            "Entity": "Sistema",
        },
        timeout=8,
    )
    resp.raise_for_status()
    items = resp.json().get("Items") or []
    serie = _parsear_serie(items)
    if not serie:
        raise XMSinDatos("XM respondió sin horas con dato en la ventana pedida")
    _CACHE_SERIE = (ahora, serie)
    return serie


def obtener_ultimo(lugar: dict) -> Lectura:
    """
    Retorna la intensidad de carbono más reciente de la red eléctrica colombiana.

    XM reporta a nivel de sistema nacional (no por ciudad), así que el valor es
    el mismo para cualquier lugar de Colombia. Se guarda por `lugar_id` para
    mantener la misma forma que las demás fuentes.

    Args:
        lugar: dict de LUGARES con '_id'
    """
    lugar_id = lugar.get("_id", "desconocido")

    try:
        serie = _serie_nacional()

        # Se guarda la serie completa, no solo el último punto: el índice único
        # ignora lo ya conocido, así que repetirlo es barato y la gráfica tiene
        # historial desde la primera ejecución.
        lecturas = [
            Lectura(
                valor=valor,
                unidad=_UNIDAD,
                metrica=_METRICA,
                fuente=_FUENTE,
                procedencia="local",
                lugar_id=lugar_id,
                estacion_nombre="Sistema Interconectado Nacional (XM)",
                ts=ts,
            )
            for ts, valor in serie
        ]
        nuevas = storage.guardar_muchas(lecturas)

        lectura = lecturas[-1]
        logger.info(
            "XM [oficial] intensidad=%.1f %s (dato de hace %d min) para %s "
            "— %d horas recibidas, %d nuevas",
            lectura.valor, _UNIDAD, lectura.antiguedad_min, lugar_id,
            len(lecturas), nuevas,
        )
        return lectura

    except (requests.RequestException, ValueError, XMSinDatos) as exc:
        logger.warning("XM falló para %s: %s", lugar_id, exc)
        lectura_cache = storage.ultimo_valor(_FUENTE, lugar_id, _METRICA)
        if lectura_cache is not None:
            logger.info("XM [caché] para %s", lugar_id)
            return lectura_cache.como_cache()
        raise XMSinDatos(
            f"Sin datos de intensidad de carbono para '{lugar_id}'"
        ) from exc
