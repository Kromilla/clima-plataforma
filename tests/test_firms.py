"""
tests/test_firms.py — Tests del adaptador FIRMS y de la alerta por incendio.

Sin red: el CSV de FIRMS se sirve desde un fixture grabado del formato real.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from alerts import revisar_alerta_incendio
from sources import firms

FIXTURES_DIR = Path(__file__).parent / "fixtures"

LUGAR_TEST = {
    "_id": "santa-marta",
    "lat": 11.2408,
    "lon": -74.1990,
    "bbox": (-74.30, 11.05, -73.85, 11.40),
}


def _csv_fixture() -> str:
    return (FIXTURES_DIR / "firms_focos.csv").read_text(encoding="utf-8")


def _respuesta(texto: str) -> MagicMock:
    resp = MagicMock()
    resp.text = texto
    resp.raise_for_status.return_value = None
    return resp


# ── Parseo del CSV ───────────────────────────────────────────────────────────

def test_parsear_csv_formato_real():
    focos = firms.parsear_csv(_csv_fixture())
    assert len(focos) == 4

    primero = focos[0]
    assert primero.lat == pytest.approx(11.2350)
    assert primero.frp == pytest.approx(12.5)
    assert primero.confianza == "nominal"
    assert primero.ts == datetime(2026, 7, 27, 3, 15, tzinfo=timezone.utc)


def test_parsear_csv_vacio_no_revienta():
    """Sin focos, FIRMS devuelve solo la cabecera."""
    solo_cabecera = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
        "satellite,confidence,version,bright_ti5,frp,daynight"
    )
    assert firms.parsear_csv(solo_cabecera) == []


def test_parsear_csv_salta_filas_corruptas():
    """Una fila mala no debe tumbar el resto del parseo."""
    texto = (
        "latitude,longitude,acq_date,acq_time,confidence,frp,satellite,daynight\n"
        "11.1,-74.2,2026-07-27,0315,nominal,10.0,N,N\n"
        "NO_ES_UN_NUMERO,-74.2,2026-07-27,0315,nominal,5.0,N,N\n"
        "11.3,-74.1,2026-07-27,0315,high,20.0,N,D\n"
    )
    focos = firms.parsear_csv(texto)
    assert len(focos) == 2, "debe conservar las filas válidas y descartar la mala"


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("low", "baja"), ("l", "baja"),
        ("nominal", "nominal"), ("n", "nominal"),
        ("high", "alta"), ("h", "alta"),
        ("10", "baja"), ("50", "nominal"), ("95", "alta"),  # MODIS usa porcentaje
        ("", "nominal"), ("basura", "nominal"),
    ],
)
def test_normalizar_confianza(entrada, esperado):
    assert firms._normalizar_confianza(entrada) == esperado


def test_acq_time_sin_ceros_a_la_izquierda():
    """FIRMS a veces manda '315' en vez de '0315'."""
    assert firms._parsear_ts("2026-07-27", "315").hour == 3
    assert firms._parsear_ts("2026-07-27", "0315").hour == 3


# ── Distancia ────────────────────────────────────────────────────────────────

def test_distancia_conocida():
    """Santa Marta ↔ Barranquilla son ~90 km en línea recta."""
    d = firms.distancia_km(11.2408, -74.1990, 10.9685, -74.7813)
    assert 60 < d < 80, f"distancia inesperada: {d} km"


def test_distancia_cero():
    assert firms.distancia_km(11.24, -74.19, 11.24, -74.19) == pytest.approx(0.0)


# ── obtener_focos ────────────────────────────────────────────────────────────

def test_focos_ordenados_por_cercania(monkeypatch):
    monkeypatch.setattr(firms.cfg, "FIRMS_MAP_KEY", "clave-de-prueba")

    with patch.object(firms.requests, "get", return_value=_respuesta(_csv_fixture())):
        focos = firms.obtener_focos(LUGAR_TEST)

    distancias = [f.distancia_km for f in focos]
    assert distancias == sorted(distancias)
    assert all(f.distancia_km > 0 for f in focos)


def test_sin_clave_lanza_error_claro(monkeypatch):
    monkeypatch.setattr(firms.cfg, "FIRMS_MAP_KEY", None)

    with pytest.raises(firms.FirmsSinClave) as exc:
        firms.obtener_focos(LUGAR_TEST)
    assert "FIRMS_MAP_KEY" in str(exc.value)


def test_clave_invalida_se_detecta(monkeypatch):
    """FIRMS responde 200 con 'Invalid MAP_KEY' en texto plano."""
    monkeypatch.setattr(firms.cfg, "FIRMS_MAP_KEY", "mala")

    with patch.object(firms.requests, "get", return_value=_respuesta("Invalid MAP_KEY.")):
        with pytest.raises(firms.FirmsSinClave):
            firms.obtener_focos(LUGAR_TEST)


def test_obtener_ultimo_cuenta_focos(monkeypatch, tmp_path):
    import storage as st
    db = str(tmp_path / "t.db")
    st.inicializar_bd(db)
    monkeypatch.setattr(st, "_db_path", lambda: db)
    monkeypatch.setattr(firms.cfg, "FIRMS_MAP_KEY", "clave-de-prueba")

    with patch.object(firms.requests, "get", return_value=_respuesta(_csv_fixture())):
        lectura = firms.obtener_ultimo(LUGAR_TEST)

    assert lectura.valor == 4.0
    assert lectura.metrica == "focos_activos"
    assert lectura.fuente == "firms"


# ── Regla de alerta por incendio ─────────────────────────────────────────────

def _foco(distancia: float, confianza: str = "nominal", frp: float = 10.0):
    return firms.Foco(
        lat=11.2, lon=-74.2, frp=frp, confianza=confianza,
        ts=datetime.now(timezone.utc), satelite="N", dia_noche="D",
        distancia_km=distancia,
    )


def test_alerta_incendio_cuando_hay_foco_cerca():
    mensaje = revisar_alerta_incendio([_foco(5.0)], umbral_km=20)
    assert mensaje is not None
    assert "5.0 km" in mensaje


def test_sin_alerta_si_el_foco_esta_lejos():
    assert revisar_alerta_incendio([_foco(50.0)], umbral_km=20) is None


def test_los_focos_de_baja_confianza_no_disparan_alerta():
    """Una detección dudosa no debe generar una alerta al usuario."""
    assert revisar_alerta_incendio([_foco(2.0, confianza="baja")], umbral_km=20) is None


def test_sin_focos_no_hay_alerta():
    assert revisar_alerta_incendio([], umbral_km=20) is None
