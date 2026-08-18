"""
tests/test_xm.py — Tests del adaptador XM, del registro y de la antigüedad.

Regla: cero llamadas a red. Todo con fixtures JSON grabados.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sources.base import LUGAR_NACIONAL, Lectura

FIXTURES_DIR = Path(__file__).parent / "fixtures"

LUGAR_TEST = {
    "_id": "santa-marta",
    "nombre": "Santa Marta, Colombia",
    "lat": 11.2408,
    "lon": -74.1990,
    "bbox": (-74.30, 11.05, -73.85, 11.40),
}


def _fixture_xm() -> dict:
    return json.loads((FIXTURES_DIR / "xm_factor_emision.json").read_text(encoding="utf-8"))


# ── Adaptador XM ─────────────────────────────────────────────────────────────

def test_xm_toma_la_hora_mas_reciente(monkeypatch, tmp_path):
    """De un payload de 2 días, usa la última hora del día más nuevo."""
    import storage as st
    db = str(tmp_path / "t.db")
    st.inicializar_bd(db)
    monkeypatch.setattr(st, "_db_path", lambda: db)

    import sources.xm as xm

    resp = MagicMock()
    resp.json.return_value = _fixture_xm()
    resp.raise_for_status.return_value = None

    with patch.object(xm.requests, "post", return_value=resp):
        lectura = xm.obtener_ultimo(LUGAR_TEST)

    # El fixture termina en 2026-07-25 Hour24 = 23:00 hora Colombia (UTC-5)
    # → 2026-07-26T04:00Z
    assert lectura.valor == pytest.approx(189.29923)
    assert lectura.fuente == "xm"
    assert lectura.metrica == "intensidad_co2"
    assert lectura.ts == datetime(2026, 7, 26, 4, 0, tzinfo=timezone.utc)


def test_xm_dia_parcial(monkeypatch, tmp_path):
    """Si el último día viene incompleto, toma su última hora disponible."""
    import storage as st
    db = str(tmp_path / "t.db")
    st.inicializar_bd(db)
    monkeypatch.setattr(st, "_db_path", lambda: db)

    import sources.xm as xm

    payload = {
        "Items": [
            {
                "Date": "2026-07-25",
                "HourlyEntities": [
                    {"Id": "Sistema", "Values": {"code": "Sistema", "Hour01": "100.0", "Hour02": "110.0"}}
                ],
            }
        ]
    }
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None

    with patch.object(xm.requests, "post", return_value=resp):
        lectura = xm.obtener_ultimo(LUGAR_TEST)

    assert lectura.valor == pytest.approx(110.0)
    # Hour02 = 01:00 Colombia = 06:00 UTC
    assert lectura.ts == datetime(2026, 7, 25, 6, 0, tzinfo=timezone.utc)


def test_xm_cae_a_cache_si_la_api_falla(monkeypatch, tmp_path):
    """Si XM está caído pero hay caché, devuelve el caché en vez de crashear."""
    import storage as st
    db = str(tmp_path / "t.db")
    st.inicializar_bd(db)
    monkeypatch.setattr(st, "_db_path", lambda: db)

    previa = Lectura(
        valor=150.0, unidad="gCO₂eq/kWh", metrica="intensidad_co2", fuente="xm",
        # Bajo el lugar nacional: XM no se guarda por ciudad.
        procedencia="local", lugar_id=LUGAR_NACIONAL, estacion_nombre="SIN",
        ts=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    st.guardar(previa, db)

    import sources.xm as xm

    with patch.object(xm.requests, "post", side_effect=xm.requests.RequestException("caído")):
        lectura = xm.obtener_ultimo(LUGAR_TEST)

    assert lectura.valor == pytest.approx(150.0)
    assert lectura.procedencia == "cache"


def test_xm_sin_api_ni_cache_lanza(monkeypatch, tmp_path):
    """Sin API y sin caché lanza XMSinDatos (no un error crudo de requests)."""
    import storage as st
    db = str(tmp_path / "t.db")
    st.inicializar_bd(db)
    monkeypatch.setattr(st, "_db_path", lambda: db)

    import sources.xm as xm

    with patch.object(xm.requests, "post", side_effect=xm.requests.RequestException("caído")):
        with pytest.raises(xm.XMSinDatos):
            xm.obtener_ultimo(LUGAR_TEST)


# ── Antigüedad y etiquetas honestas ──────────────────────────────────────────

def _lectura_con_edad(minutos: int, procedencia: str = "local") -> Lectura:
    return Lectura(
        valor=10.0, unidad="µg/m³", metrica="pm25", fuente="test",
        procedencia=procedencia, lugar_id="santa-marta", estacion_nombre="Est",
        ts=datetime.now(timezone.utc) - timedelta(minutes=minutos),
    )


@pytest.mark.parametrize(
    "minutos,esperado",
    [(5, "hace 5 min"), (200, "hace 3 h"), (60 * 24 * 3, "hace 3 días")],
)
def test_antiguedad_texto(minutos, esperado):
    assert _lectura_con_edad(minutos).antiguedad_texto() == esperado


def test_dato_viejo_se_marca_aunque_sea_local():
    """
    Un dato de 2 días no puede mostrarse como si fuera de ahora: es el requisito
    de "no fingir precisión que no tiene".
    """
    etiqueta = _lectura_con_edad(60 * 48).etiqueta_procedencia()
    assert "⚠️" in etiqueta
    assert "días" in etiqueta


def test_dato_fresco_no_lleva_advertencia():
    etiqueta = _lectura_con_edad(5).etiqueta_procedencia()
    assert "⚠️" not in etiqueta
    assert _lectura_con_edad(5).es_reciente()


# ── Registro de fuentes ──────────────────────────────────────────────────────

def test_registro_ids_unicos():
    from sources.registry import FUENTES
    ids = [f.id for f in FUENTES]
    assert len(ids) == len(set(ids)), "hay ids de fuente duplicados"


def test_registro_por_id():
    from sources.registry import por_id
    assert por_id("xm") is not None
    assert por_id("no-existe") is None


def test_guardar_es_idempotente(tmp_path):
    """
    Guardar dos veces la misma lectura no duplica filas.

    El recolector corre cada 15 min pero XM publica cada varias horas: sin esto
    la tabla se llena de copias del mismo dato y las gráficas salen planas.
    """
    import storage as st
    db = str(tmp_path / "t.db")
    st.inicializar_bd(db)

    lectura = Lectura(
        valor=189.3, unidad="gCO₂eq/kWh", metrica="intensidad_co2", fuente="xm",
        procedencia="local", lugar_id="santa-marta", estacion_nombre="SIN",
        ts=datetime(2026, 7, 26, 4, 0, tzinfo=timezone.utc),
    )

    assert st.guardar(lectura, db) is True, "la primera inserción debe ser nueva"
    assert st.guardar(lectura, db) is False, "la segunda debe ignorarse"
    assert st.guardar(lectura, db) is False

    assert len(st.historial("xm", "santa-marta", "intensidad_co2", 100, db)) == 1


def test_guardar_distingue_timestamps(tmp_path):
    """Un dato genuinamente nuevo (otro ts) sí se guarda."""
    import storage as st
    db = str(tmp_path / "t.db")
    st.inicializar_bd(db)

    base = datetime(2026, 7, 26, 4, 0, tzinfo=timezone.utc)
    for i in range(3):
        st.guardar(
            Lectura(
                valor=100.0 + i, unidad="gCO₂eq/kWh", metrica="intensidad_co2",
                fuente="xm", procedencia="local", lugar_id="santa-marta",
                estacion_nombre="SIN", ts=base + timedelta(hours=i),
            ),
            db,
        )

    assert len(st.historial("xm", "santa-marta", "intensidad_co2", 100, db)) == 3


def test_xm_tolera_rezago_en_el_semaforo():
    """
    XM publica con días de rezago: sus umbrales deben ser más laxos que los de
    una fuente en tiempo real, o el semáforo lo pintaría rojo para siempre.
    """
    from sources.registry import por_id
    xm_f = por_id("xm")
    aire = por_id("openmeteo-aire")
    assert xm_f.frescura_ok_min > aire.frescura_ok_min
    assert xm_f.frescura_ok_min >= 3 * 24 * 60
