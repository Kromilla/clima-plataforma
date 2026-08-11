"""
tests/test_clima.py — Clima en vivo (condiciones actuales) de Open-Meteo con
respaldo a MET Norway.

Cubre las fallas que se arreglaron tras la revisión de salud:
- el caché por punto no puede crecer sin límite (fuga de memoria con GPS);
- un símbolo desconocido de MET Norway cae a "nublado", no a "sol" falso;
- si Open-Meteo falla, condiciones_actuales usa MET Norway.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from sources import openmeteo_clima as clima
from sources.base import Lectura


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


# ── Integración del endpoint /api/clima/ahora ────────────────────────────────

def _cliente():
    from fastapi.testclient import TestClient

    from api import app
    return TestClient(app)


def _lectura(metrica: str, valor: float, edad_min: int) -> Lectura:
    ts = datetime.now(timezone.utc) - timedelta(minutes=edad_min)
    return Lectura(
        valor=valor, unidad="", metrica=metrica, fuente="openmeteo-clima",
        procedencia="local", lugar_id="santa-marta", ts=ts,
    )


def test_endpoint_gps_valido(monkeypatch):
    import api
    monkeypatch.setattr(
        api.openmeteo_clima, "condiciones_actuales",
        lambda lugar: {"origen": "Open-Meteo", "temperatura": 27.0, "es_dia": True},
    )
    resp = _cliente().get("/api/clima/ahora?lat=4.6&lon=-74.08")
    assert resp.status_code == 200
    d = resp.json()
    assert d["disponible"] is True
    assert d["etiqueta"] == "Tu ubicación"
    assert d["temperatura"] == 27.0


def test_endpoint_gps_fuera_de_rango():
    resp = _cliente().get("/api/clima/ahora?lat=999&lon=0")
    assert resp.status_code == 400


def test_endpoint_lugar_desconocido():
    resp = _cliente().get("/api/clima/ahora?lugar_id=narnia")
    assert resp.status_code == 404


def test_endpoint_respaldo_cuando_openmeteo_falla(monkeypatch):
    """Si el vivo falla en una ciudad, se sirve el último dato del collector."""
    import api

    def _falla(_lugar):
        raise api.openmeteo_clima.ClimaActualError("429 simulado")

    monkeypatch.setattr(api.openmeteo_clima, "condiciones_actuales", _falla)

    def _ultimo(fuente, lugar_id, metrica):
        if metrica == "temperatura":
            return _lectura("temperatura", 30.0, 45)
        return _lectura("humedad", 70.0, 45)

    monkeypatch.setattr(api.storage, "ultimo_valor", _ultimo)

    resp = _cliente().get("/api/clima/ahora?lugar_id=santa-marta")
    assert resp.status_code == 200
    d = resp.json()
    assert d["disponible"] is True
    assert d["cacheado"] is True
    assert d["temperatura"] == 30.0
    assert d["humedad"] == 70.0
    assert d["antiguedad_min"] >= 44


def test_endpoint_gps_sin_respaldo_devuelve_no_disponible(monkeypatch):
    """Un punto GPS sin historial y con el vivo caído → disponible: false."""
    import api

    def _falla(_lugar):
        raise api.openmeteo_clima.ClimaActualError("429 simulado")

    monkeypatch.setattr(api.openmeteo_clima, "condiciones_actuales", _falla)
    resp = _cliente().get("/api/clima/ahora?lat=4.6&lon=-74.08")
    assert resp.status_code == 200
    d = resp.json()
    assert d["disponible"] is False
    assert "mensaje" in d
