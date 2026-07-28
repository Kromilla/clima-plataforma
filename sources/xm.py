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


class XMSinDatos(Exception):
    """Se lanza cuando no hay dato ni en la API ni en caché."""


def _ultima_hora_disponible(items: list[dict]) -> tuple[datetime, float] | None:
    """
    Recorre la respuesta de XM y devuelve (timestamp, valor) de la hora más
    reciente con dato.

    Formato de XM: cada día trae un dict `Values` con claves Hour01..Hour24,
    donde Hour01 = 00:00-01:00 y Hour24 = 23:00-24:00 hora local de Colombia.
    Los días parciales simplemente traen menos claves Hour*.
    """
    for item in reversed(items):  # el día más reciente primero
        entidades = item.get("HourlyEntities") or []
        if not entidades:
            continue
        valores = entidades[0].get("Values") or {}

        horas = sorted(k for k in valores if k.startswith("Hour"))
        if not horas:
            continue

        clave_hora = horas[-1]
        try:
            valor = float(valores[clave_hora])
            hora_idx = int(clave_hora.removeprefix("Hour"))  # 1..24
            dia = date.fromisoformat(item["Date"])
        except (ValueError, KeyError, TypeError):
            continue

        # Hour01 cubre 00:00-01:00 → lo anclamos al inicio del intervalo.
        ts = datetime(
            dia.year, dia.month, dia.day, tzinfo=_TZ_COLOMBIA
        ) + timedelta(hours=hora_idx - 1)
        return ts.astimezone(timezone.utc), valor

    return None


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

    hoy = datetime.now(_TZ_COLOMBIA).date()
    inicio = hoy - timedelta(days=_DIAS_VENTANA)

    try:
        resp = requests.post(
            _URL,
            json={
                "MetricId": "factorEmisionCO2e",
                "StartDate": inicio.isoformat(),
                "EndDate": hoy.isoformat(),
                "Entity": "Sistema",
            },
            timeout=20,
        )
        resp.raise_for_status()
        items = resp.json().get("Items") or []

        reciente = _ultima_hora_disponible(items)
        if reciente is None:
            raise XMSinDatos("XM respondió sin horas con dato en la ventana pedida")

        ts, valor = reciente
        lectura = Lectura(
            valor=valor,
            unidad=_UNIDAD,
            metrica=_METRICA,
            fuente=_FUENTE,
            procedencia="local",
            lugar_id=lugar_id,
            estacion_nombre="Sistema Interconectado Nacional (XM)",
            ts=ts,
        )
        storage.guardar(lectura)
        logger.info(
            "XM [oficial] intensidad=%.1f %s (dato de hace %d min) para %s",
            valor, _UNIDAD, lectura.antiguedad_min, lugar_id,
        )
        return lectura

    except (requests.RequestException, ValueError, XMSinDatos) as exc:
        logger.warning("XM falló para %s: %s", lugar_id, exc)
        lectura_cache = storage.ultimo_valor(_FUENTE, lugar_id, _METRICA)
        if lectura_cache is not None:
            logger.info("XM [caché] para %s", lugar_id)
            return lectura_cache
        raise XMSinDatos(
            f"Sin datos de intensidad de carbono para '{lugar_id}'"
        ) from exc
