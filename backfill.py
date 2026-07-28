"""
backfill.py — Rellena el historial con datos reales del archivo de Open-Meteo.

Por qué existe: la Fase 4 necesita "≥2-4 semanas de historial" para entrenar, y
el recolector empezó a correr hace días. En vez de esperar semanas, traemos el
histórico real de la misma variable y el mismo proveedor desde la API de archivo
de Open-Meteo (reanálisis ERA5), que cubre desde 1940.

No es hacer trampa ni inventar datos: son mediciones reales reanalizadas para
las coordenadas de Santa Marta. Se guardan con su timestamp original, así que
quedan claramente ubicadas en el pasado.

Uso:
    python backfill.py                    # último año
    python backfill.py --dias 730         # dos años
    python backfill.py --desde 2023-01-01 --hasta 2023-12-31
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

import requests

import logging_setup
import storage
from locations import DEFAULT_LUGAR, LUGARES
from sources.base import Lectura

logger = logging.getLogger("backfill")

_URL = "https://archive-api.open-meteo.com/v1/archive"
_FUENTE = "openmeteo-clima"   # misma fuente que en vivo: es la misma variable
# El reanálisis ERA5 tiene ~5 días de rezago respecto a hoy.
_REZAGO_ARCHIVO_DIAS = 6

# Qué variable de la API corresponde a qué métrica nuestra.
_VARIABLES = {
    "temperature_2m": ("temperatura", "°C"),
    "relative_humidity_2m": ("humedad", "%"),
}


def descargar(lugar: dict, desde: date, hasta: date) -> dict:
    """Trae el histórico horario del archivo de Open-Meteo."""
    resp = requests.get(
        _URL,
        params={
            "latitude": lugar["lat"],
            "longitude": lugar["lon"],
            "start_date": desde.isoformat(),
            "end_date": hasta.isoformat(),
            "hourly": ",".join(_VARIABLES),
            "timezone": "UTC",
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def guardar_historico(datos: dict, lugar_id: str) -> tuple[int, int]:
    """
    Persiste el histórico en storage.

    Returns:
        (nuevas, repetidas) — las repetidas son filas que ya existían; el índice
        único las ignora, así que el backfill es seguro de repetir.
    """
    horario = datos.get("hourly", {})
    tiempos = horario.get("time", [])
    if not tiempos:
        return 0, 0

    lecturas: list[Lectura] = []

    for variable, (metrica, unidad) in _VARIABLES.items():
        valores = horario.get(variable) or []

        for ts_str, valor in zip(tiempos, valores):
            if valor is None:
                continue  # hueco en el reanálisis
            try:
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            lecturas.append(
                Lectura(
                    valor=float(valor),
                    unidad=unidad,
                    metrica=metrica,
                    fuente=_FUENTE,
                    procedencia="local",
                    lugar_id=lugar_id,
                    estacion_nombre="Open-Meteo ERA5 (archivo)",
                    ts=ts,
                )
            )

    # Una sola transacción: insertar de a una tardaría minutos con 35k filas.
    nuevas = storage.guardar_muchas(lecturas)
    return nuevas, len(lecturas) - nuevas


_URL_RECIENTE = "https://api.open-meteo.com/v1/forecast"
# La API de pronóstico expone hasta 92 días de pasado.
_MAX_DIAS_RECIENTES = 92


def rellenar_reciente(lugar: dict, lugar_id: str, dias: int = 10) -> tuple[int, int]:
    """
    Cubre el hueco entre el final del archivo ERA5 y hoy.

    ERA5 tiene ~6 días de rezago, así que `descargar()` deja siempre una ventana
    reciente vacía. Sin esto, el predictor "de mañana" apunta a una fecha que ya
    pasó, que es justo lo que no queremos mostrar.
    """
    dias = max(1, min(dias, _MAX_DIAS_RECIENTES))

    resp = requests.get(
        _URL_RECIENTE,
        params={
            "latitude": lugar["lat"],
            "longitude": lugar["lon"],
            "hourly": ",".join(_VARIABLES),
            "past_days": dias,
            "forecast_days": 1,
            "timezone": "UTC",
        },
        timeout=60,
    )
    resp.raise_for_status()
    datos = resp.json()

    # No guardamos horas futuras: el predictor debe entrenar solo con lo ocurrido.
    ahora = datetime.now(timezone.utc)
    horario = datos.get("hourly", {})
    tiempos = horario.get("time", [])
    corte = len(tiempos)
    for i, ts_str in enumerate(tiempos):
        try:
            if datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc) > ahora:
                corte = i
                break
        except ValueError:
            continue

    datos["hourly"] = {
        clave: valores[:corte] if isinstance(valores, list) else valores
        for clave, valores in horario.items()
    }
    return guardar_historico(datos, lugar_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rellena el historial con datos reales del archivo de Open-Meteo.",
    )
    parser.add_argument("--dias", type=int, default=365,
                        help="Días hacia atrás desde hoy (default: 365).")
    parser.add_argument("--desde", type=str, help="Fecha inicial YYYY-MM-DD.")
    parser.add_argument("--hasta", type=str, help="Fecha final YYYY-MM-DD.")
    parser.add_argument("--lugar", type=str, default=DEFAULT_LUGAR)
    args = parser.parse_args()

    logging_setup.configurar()

    if args.lugar not in LUGARES:
        sys.exit(f"Lugar '{args.lugar}' no existe. Disponibles: {list(LUGARES)}")

    tope = date.today() - timedelta(days=_REZAGO_ARCHIVO_DIAS)
    hasta = date.fromisoformat(args.hasta) if args.hasta else tope
    desde = (
        date.fromisoformat(args.desde) if args.desde
        else hasta - timedelta(days=args.dias)
    )

    if hasta > tope:
        logger.warning(
            "El archivo ERA5 tiene ~%d días de rezago; recorto la fecha final a %s",
            _REZAGO_ARCHIVO_DIAS, tope,
        )
        hasta = tope
    if desde >= hasta:
        sys.exit(f"El rango es inválido: desde={desde} hasta={hasta}")

    lugar = LUGARES[args.lugar]
    logger.info("Descargando %s → %s para %s…", desde, hasta, args.lugar)

    try:
        datos = descargar(lugar, desde, hasta)
    except requests.RequestException as exc:
        sys.exit(f"No se pudo descargar el archivo: {exc}")

    storage.inicializar_bd()
    nuevas, repetidas = guardar_historico(datos, args.lugar)
    logger.info(
        "Archivo ERA5: %d lecturas nuevas, %d ya existían (%d días).",
        nuevas, repetidas, (hasta - desde).days,
    )

    # Cierra el hueco entre el final del archivo y ahora.
    if not args.hasta:
        try:
            n_rec, r_rec = rellenar_reciente(lugar, args.lugar)
            logger.info("Ventana reciente: %d nuevas, %d ya existían.", n_rec, r_rec)
        except requests.RequestException as exc:
            logger.warning("No se pudo rellenar la ventana reciente: %s", exc)


if __name__ == "__main__":
    main()
