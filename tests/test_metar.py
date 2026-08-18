"""
tests/test_metar.py — Estaciones METAR de aeropuerto (medición física real).

Lo que se protege aquí:
- La regla de altitud: solo se usa la estación cuando representa a la ciudad.
- El parseo del tiempo presente, que tuvo dos bugs reales:
    · se leía la sección RMK (remarks) y Cartagena reportaba calima falsa;
    · el identificador de la estación podía leerse como un fenómeno.
- Las conversiones (nudos → km/h, punto de rocío → humedad).

Todos los reportes son fijos: la suite no toca la red.
"""
from __future__ import annotations

import pytest
import requests

from sources import metar


# ── Regla de altitud ─────────────────────────────────────────────────────────

def test_ciudades_con_estacion_representativa():
    """Las 11 ciudades de la tabla tienen la estación validada por altitud."""
    assert len(metar.ESTACIONES) == 11
    for cid, est in metar.ESTACIONES.items():
        assert est.es_representativa, f"{cid} no debería estar en la tabla"


@pytest.mark.parametrize("cid", ["pasto", "ibague", "bucaramanga"])
def test_ciudades_sin_estacion_representativa_usan_modelo(cid):
    """
    El aeropuerto de estas tres está a una altitud muy distinta de la ciudad
    (Pasto: 748 m). Usar su estación daría varios grados de error, así que no
    están en la tabla y el endpoint debe caer al modelo.
    """
    assert cid not in metar.ESTACIONES
    assert metar.estacion_de({"_id": cid}) is None


def test_medellin_usa_la_estacion_dentro_de_la_ciudad():
    """
    Medellín debe usar SKMD (Olaya Herrera, 1491 m), no SKRG (Rionegro, 2132 m).
    Rionegro está 650 m más alto y marcaba ~6 °C menos que la ciudad.
    """
    est = metar.ESTACIONES["medellin"]
    assert est.icao == "SKMD"
    assert abs(est.alt_ciudad_m - est.alt_estacion_m) <= metar._TOLERANCIA_ALTITUD_M


def test_estacion_fuera_de_tolerancia_se_rechaza():
    """La propiedad que decide es la diferencia de altitud, no la cercanía."""
    lejana = metar.EstacionMetar("SKXX", "Aeropuerto alto", 2500, 1000, 5.0)
    assert not lejana.es_representativa


def test_lugar_sin_id_no_tiene_estacion():
    """Un punto GPS arbitrario no trae '_id', así que nunca usa estación."""
    assert metar.estacion_de({"lat": 4.6, "lon": -74.08}) is None


# ── Tiempo presente: los dos bugs reales ─────────────────────────────────────

def test_ignora_la_seccion_rmk():
    """
    Regresión: el `HZ` de las remarks de Cartagena hacía que el dashboard
    reportara calima cuando el cuerpo del reporte no traía ningún fenómeno.
    Las remarks son información suplementaria, no el tiempo oficial.
    """
    crudo = "METAR SKCG 181700Z 20006KT 8000 SCT012 OVC035 32/26 Q1011 RMK HZ"
    assert metar._codigo_wmo(crudo, "OVC", "SKCG") == 3  # nublado, no niebla


def test_no_confunde_el_codigo_de_la_estacion_con_un_fenomeno():
    """Un ICAO como 'SKRA' contiene 'RA' y se leería como lluvia."""
    crudo = "METAR SKRA 181700Z 27003KT 9999 NSC 29/26 Q1012"
    assert metar._codigo_wmo(crudo, "CLR", "SKRA") == 0  # despejado


def test_detecta_fenomeno_en_el_cuerpo():
    """`DZ` en el cuerpo del reporte sí es llovizna real (caso Bogotá)."""
    crudo = "METAR SKBO 181700Z VRB05G15KT 9999 DZ FEW030 SCT050 18/12 Q1029 NOSIG"
    assert metar._codigo_wmo(crudo, "SCT", "SKBO") == 53


def test_detecta_niebla_compuesta():
    """`BCFG` (bancos de niebla) debe leerse como niebla (caso Manizales)."""
    crudo = "METAR SKMZ 181700Z 32008KT 7000 BCFG SCT007 BKN015TCU 20/16 Q1027"
    assert metar._codigo_wmo(crudo, "BKN", "SKMZ") == 45


def test_la_tormenta_gana_sobre_la_lluvia():
    """Con `TSRA` debe reportarse tormenta, no lluvia: lo severo manda."""
    crudo = "METAR SKBO 181700Z 18010KT 5000 TSRA BKN020CB 20/18 Q1015"
    assert metar._codigo_wmo(crudo, "BKN", "SKBO") == 95


def test_los_grupos_con_digitos_no_producen_fenomenos():
    """
    Grupos de nubes, viento y presión llevan dígitos, así que no pueden
    coincidir con un fenómeno. Sin cielo reportado ni fenómeno: despejado.
    """
    crudo = "METAR SKSM 181700Z 27003KT 9999 NSC 29/26 Q1012"
    assert metar._tokens_de_tiempo(crudo, "SKSM") == []
    assert metar._codigo_wmo(crudo, "CLR", "SKSM") == 0


def test_cobertura_desconocida_no_revienta():
    """Una cobertura que no está en la tabla cae a nublado, no a sol falso."""
    assert metar._codigo_wmo("METAR SKSM 181700Z", "RARO", "SKSM") == 3


# ── Conversiones ─────────────────────────────────────────────────────────────

def test_humedad_relativa_saturada():
    """Con temperatura igual al punto de rocío el aire está saturado: 100 %."""
    assert metar._humedad_relativa(20.0, 20.0) == 100.0


def test_humedad_relativa_conocida():
    """29 °C con rocío de 26 °C da ~84 % (caso real de Santa Marta)."""
    assert 83.0 <= metar._humedad_relativa(29.0, 26.0) <= 85.0


def test_direccion_variable_no_inventa_rumbo():
    """'VRB' significa viento variable: no hay un rumbo único que mostrar."""
    assert metar._direccion("VRB") is None
    assert metar._direccion(270) == 270


# ── Parseo completo, sin red ──────────────────────────────────────────────────

_REPORTE_SKSM = [{
    "icaoId": "SKSM",
    "obsTime": 1787072400,          # 2026-08-18T17:00:00Z
    "temp": 29,
    "dewp": 26,
    "wdir": 270,
    "wspd": 3,                      # nudos
    "wgst": 10,
    "altim": 1012,
    "cover": "CLR",
    "rawOb": "METAR SKSM 181700Z 27003KT 9999 NSC 29/26 Q1012",
}]


class _RespFalsa:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_condiciones_actuales_parsea_todo(monkeypatch):
    monkeypatch.setattr(metar.requests, "get", lambda *a, **k: _RespFalsa(_REPORTE_SKSM))
    d = metar.condiciones_actuales({"_id": "santa-marta", "lat": 11.24, "lon": -74.20})

    assert d["es_estacion"] is True
    assert "SKSM" in d["origen"]
    assert d["temperatura"] == 29.0
    assert 83.0 <= d["humedad"] <= 85.0
    assert d["viento_kmh"] == 5.6          # 3 nudos × 1.852
    assert d["rachas_kmh"] == 18.5         # 10 nudos × 1.852
    assert d["viento_dir"] == 270
    assert d["presion"] == 1012.0
    assert d["codigo"] == 0
    assert d["estacion_km"] == 13.9
    # Sin 'Z' final: el frontend la agrega, igual que con Open-Meteo.
    assert d["ts"] == "2026-08-18T17:00"


def test_no_inventa_sensacion_ni_precipitacion(monkeypatch):
    """
    El METAR no mide sensación térmica ni publica precipitación de forma
    uniforme. Deben quedar en None para que la UI oculte esos tiles en vez de
    mostrar un 0 que el sensor nunca reportó.
    """
    monkeypatch.setattr(metar.requests, "get", lambda *a, **k: _RespFalsa(_REPORTE_SKSM))
    d = metar.condiciones_actuales({"_id": "santa-marta", "lat": 11.24, "lon": -74.20})
    assert d["sensacion"] is None
    assert d["precipitacion"] is None


def test_reporte_sin_temperatura_no_se_usa(monkeypatch):
    """Villavicencio llegó a publicar '28///' (sin rocío) y temp nula."""
    sin_temp = [{**_REPORTE_SKSM[0], "temp": None}]
    monkeypatch.setattr(metar.requests, "get", lambda *a, **k: _RespFalsa(sin_temp))
    with pytest.raises(metar.MetarNoDisponible):
        metar.condiciones_actuales({"_id": "santa-marta", "lat": 11.24, "lon": -74.20})


def test_estacion_caida_lanza_no_disponible(monkeypatch):
    def _cae(*a, **k):
        raise requests.RequestException("NOAA caída")

    monkeypatch.setattr(metar.requests, "get", _cae)
    with pytest.raises(metar.MetarNoDisponible):
        metar.condiciones_actuales({"_id": "santa-marta", "lat": 11.24, "lon": -74.20})


def test_respuesta_vacia_lanza_no_disponible(monkeypatch):
    monkeypatch.setattr(metar.requests, "get", lambda *a, **k: _RespFalsa([]))
    with pytest.raises(metar.MetarNoDisponible):
        metar.condiciones_actuales({"_id": "santa-marta", "lat": 11.24, "lon": -74.20})


def test_ciudad_sin_estacion_lanza_no_disponible():
    """No debe ni intentar la petición si la ciudad no tiene estación válida."""
    with pytest.raises(metar.MetarNoDisponible):
        metar.condiciones_actuales({"_id": "pasto", "lat": 1.21, "lon": -77.28})


def test_cachea_por_estacion(monkeypatch):
    """Un METAR se publica una vez por hora: la segunda consulta usa el caché."""
    llamadas = []

    def _contar(*a, **k):
        llamadas.append(1)
        return _RespFalsa(_REPORTE_SKSM)

    monkeypatch.setattr(metar.requests, "get", _contar)
    lugar = {"_id": "santa-marta", "lat": 11.24, "lon": -74.20}
    metar.condiciones_actuales(lugar)
    metar.condiciones_actuales(lugar)
    assert len(llamadas) == 1


def test_es_dia_segun_hora_solar(monkeypatch):
    """
    El METAR no dice si es de día. A las 17:00 UTC en Colombia (UTC-5) son las
    12 del día; a las 03:00 UTC es de noche.
    """
    monkeypatch.setattr(metar.requests, "get", lambda *a, **k: _RespFalsa(_REPORTE_SKSM))
    lugar = {"_id": "santa-marta", "lat": 11.24, "lon": -74.20}
    assert metar.condiciones_actuales(lugar)["es_dia"] is True

    metar._CACHE.clear()
    de_noche = [{**_REPORTE_SKSM[0], "obsTime": 1787072400 - 14 * 3600}]  # 03:00Z
    monkeypatch.setattr(metar.requests, "get", lambda *a, **k: _RespFalsa(de_noche))
    assert metar.condiciones_actuales(lugar)["es_dia"] is False
