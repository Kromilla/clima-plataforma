"""
tests/test_clima.py — Clima en vivo (condiciones actuales) de Open-Meteo con
respaldo a MET Norway.

Cubre las fallas que se arreglaron tras la revisión de salud:
- el caché por punto no puede crecer sin límite (fuga de memoria con GPS);
- un símbolo desconocido de MET Norway cae a "nublado", no a "sol" falso;
- si Open-Meteo falla, condiciones_actuales usa MET Norway.
"""
from __future__ import annotations

import requests

from sources import openmeteo_clima as clima


def test_cache_no_crece_sin_limite():
    """Con más puntos que el tope, el caché se mantiene acotado."""
    for i in range(clima._CACHE_MAX + 50):
        clima._guardar_en_cache((float(i), 0.0), {"i": i})
    assert len(clima._CACHE_ACTUAL) <= clima._CACHE_MAX


def test_cache_purga_expiradas_antes_de_fifo(monkeypatch):
    """Al llenarse, primero se sueltan las entradas expiradas."""
    reloj = {"t": 1000.0}
    monkeypatch.setattr(clima.time, "monotonic", lambda: reloj["t"])

    # Llena el caché con entradas "viejas".
    for i in range(clima._CACHE_MAX):
        clima._guardar_en_cache((float(i), 0.0), {"i": i})

    # Avanza el reloj más allá del TTL: todas quedan expiradas.
    reloj["t"] += clima._CACHE_TTL_SEG + 1
    clima._guardar_en_cache((-1.0, -1.0), {"nuevo": True})

    # La purga por TTL deja solo la entrada nueva.
    assert clima._CACHE_ACTUAL == {(-1.0, -1.0): (reloj["t"], {"nuevo": True})}


class _RespFalsa:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_METNO_PAYLOAD = {
    "properties": {
        "timeseries": [
            {
                "time": "2026-08-07T23:00:00Z",
                "data": {
                    "instant": {
                        "details": {
                            "air_temperature": 30.0,
                            "relative_humidity": 68.0,
                            "wind_speed": 10.0,  # m/s
                            "wind_from_direction": 90.0,
                            "cloud_area_fraction": 75.0,
                            "air_pressure_at_sea_level": 1007.0,
                        }
                    },
                    "next_1_hours": {
                        "summary": {"symbol_code": "cloudy"},
                        "details": {"precipitation_amount": 0.0},
                    },
                },
            }
        ]
    }
}


def test_metno_parsea_campos_completos(monkeypatch):
    monkeypatch.setattr(clima.requests, "get", lambda *a, **k: _RespFalsa(_METNO_PAYLOAD))
    d = clima._via_metno({"lat": 11.24, "lon": -74.20})
    assert d["origen"] == "MET Norway"
    assert d["temperatura"] == 30.0
    assert d["humedad"] == 68.0
    assert d["viento_kmh"] == 36.0  # 10 m/s * 3.6
    assert d["presion"] == 1007.0
    assert d["codigo"] == 3  # "cloudy"


def test_metno_simbolo_desconocido_cae_a_nublado(monkeypatch):
    payload = {
        "properties": {"timeseries": [{
            "time": "2026-08-07T23:00:00Z",
            "data": {
                "instant": {"details": {"air_temperature": 25.0}},
                "next_1_hours": {"summary": {"symbol_code": "algo_raro_day"}},
            },
        }]}
    }
    monkeypatch.setattr(clima.requests, "get", lambda *a, **k: _RespFalsa(payload))
    d = clima._via_metno({"lat": 0.0, "lon": 0.0})
    assert d["codigo"] == 3  # desconocido → nublado, no sol


def test_condiciones_actuales_usa_metno_si_openmeteo_falla(monkeypatch):
    def _falla(_lugar):
        raise clima.ClimaActualError("429 simulado")

    monkeypatch.setattr(clima, "_via_openmeteo", _falla)
    monkeypatch.setattr(clima.requests, "get", lambda *a, **k: _RespFalsa(_METNO_PAYLOAD))
    d = clima.condiciones_actuales({"lat": 11.24, "lon": -74.20})
    assert d["origen"] == "MET Norway"
    assert d["temperatura"] == 30.0


def test_condiciones_actuales_reporta_error_de_openmeteo_si_ambas_fallan(monkeypatch):
    monkeypatch.setattr(
        clima, "_via_openmeteo",
        lambda _l: (_ for _ in ()).throw(clima.ClimaActualError("429 de Open-Meteo")),
    )

    def _metno_cae(*a, **k):
        raise requests.RequestException("met.no caído")

    monkeypatch.setattr(clima.requests, "get", _metno_cae)
    try:
        clima.condiciones_actuales({"lat": 1.0, "lon": 2.0})
        assert False, "debió lanzar ClimaActualError"
    except clima.ClimaActualError as exc:
        assert "Open-Meteo" in str(exc)  # se reporta el motivo de la fuente primaria
