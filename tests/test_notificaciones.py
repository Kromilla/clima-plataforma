"""
tests/test_notificaciones.py — Alertas proactivas de PM2.5 (notificador.py).

Cubre la máquina de estados (histéresis anti-spam) y el flujo completo con
`storage` real (SQLite temporal) y un enviador falso, sin tocar Telegram.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import notificador
import storage
from notificador import decidir
from sources.base import Lectura

CHAT = "0"
LUGAR = "santa-marta"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _sembrar_aire(db: str, valor: float, minutos_atras: int = 5) -> None:
    storage.guardar(
        Lectura(
            valor=valor, unidad="µg/m³", metrica="pm25", fuente="openmeteo-aire",
            procedencia="local", lugar_id=LUGAR, estacion_nombre="CAMS",
            ts=_ahora() - timedelta(minutes=minutos_atras),
        ),
        db,
    )


@pytest.fixture
def db(tmp_path, monkeypatch):
    ruta = str(tmp_path / "notif.db")
    storage.inicializar_bd(ruta)
    monkeypatch.setattr(storage, "_db_path", lambda: ruta)
    # Umbral explícito para no depender de la variable de entorno.
    storage.guardar_config(f"umbral:{CHAT}", "50", ruta)
    return ruta


# ── Máquina de estados (función pura) ────────────────────────────────────────

def test_normal_a_malo_alerta():
    accion, estado, _ = decidir(80, 50, "normal", None, _ahora())
    assert accion == "alerta"
    assert estado == "activa"


def test_malo_sostenido_dentro_del_cooldown_no_repite():
    ahora = _ahora()
    accion, estado, _ = decidir(80, 50, "activa", ahora - timedelta(minutes=30), ahora)
    assert accion == "nada"
    assert estado == "activa"


def test_malo_sostenido_tras_el_cooldown_recuerda():
    ahora = _ahora()
    accion, estado, ts = decidir(80, 50, "activa", ahora - timedelta(hours=7), ahora)
    assert accion == "recordatorio"
    assert estado == "activa"
    assert ts == ahora


def test_malo_a_normal_avisa_normalizado():
    accion, estado, _ = decidir(10, 50, "activa", _ahora(), _ahora())
    assert accion == "normalizado"
    assert estado == "normal"


def test_normal_sostenido_no_hace_nada():
    accion, estado, _ = decidir(10, 50, "normal", None, _ahora())
    assert accion == "nada"
    assert estado == "normal"


def test_valor_igual_al_umbral_alerta():
    """El umbral es inclusivo (>=): 50 con umbral 50 debe alertar."""
    accion, _, _ = decidir(50, 50, "normal", None, _ahora())
    assert accion == "alerta"


# ── Flujo completo con storage y enviador falso ──────────────────────────────

class _Espia:
    def __init__(self, exito: bool = True):
        self.exito = exito
        self.mensajes: list[tuple[str, str]] = []

    def __call__(self, texto: str, chat_id: str) -> bool:
        self.mensajes.append((texto, chat_id))
        return self.exito


def test_flujo_alerta_y_persiste_estado(db):
    _sembrar_aire(db, 80)
    espia = _Espia()

    accion = notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia)

    assert accion == "alerta"
    assert len(espia.mensajes) == 1
    assert "ALERTA" in espia.mensajes[0][0]
    assert storage.obtener_config(f"alerta:estado:{CHAT}", db_path=db) == "activa"


def test_no_repite_dentro_del_cooldown(db):
    _sembrar_aire(db, 80)
    espia = _Espia()

    notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia)          # alerta
    accion = notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia)  # inmediato

    assert accion == "nada"
    assert len(espia.mensajes) == 1, "no debe reenviar dentro del cooldown"


def test_recordatorio_tras_cooldown(db):
    _sembrar_aire(db, 80)
    espia = _Espia()

    ayer = _ahora() - timedelta(hours=7)
    notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia, ahora=ayer)  # alerta
    accion = notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia)      # 7 h después

    assert accion == "recordatorio"
    assert "Recordatorio" in espia.mensajes[1][0]


def test_avisa_cuando_se_normaliza(db):
    espia = _Espia()
    _sembrar_aire(db, 80)
    notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia)  # activa

    _sembrar_aire(db, 8)  # el aire mejora
    accion = notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia)

    assert accion == "normalizado"
    assert "normalizado" in espia.mensajes[1][0].lower()
    assert storage.obtener_config(f"alerta:estado:{CHAT}", db_path=db) == "normal"


def test_lectura_obsoleta_no_alerta(db):
    _sembrar_aire(db, 200, minutos_atras=300)  # 5 h de antigüedad
    espia = _Espia()

    accion = notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia)

    assert accion == "obsoleto"
    assert espia.mensajes == []


def test_sin_datos_no_alerta(db):
    espia = _Espia()
    accion = notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia)
    assert accion == "sin_datos"
    assert espia.mensajes == []


def test_si_falla_el_envio_no_avanza_el_estado(db):
    """Si Telegram está inalcanzable, se reintenta luego en vez de perder el aviso."""
    _sembrar_aire(db, 80)
    espia = _Espia(exito=False)

    notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia)

    # El estado sigue en "normal": la próxima pasada volverá a intentar.
    assert storage.obtener_config(f"alerta:estado:{CHAT}", db_path=db, default="normal") == "normal"

    # Y en la siguiente pasada (ya con envío ok) sí alerta.
    espia_ok = _Espia()
    accion = notificador.revisar_y_notificar(LUGAR, CHAT, enviar=espia_ok)
    assert accion == "alerta"
    assert len(espia_ok.mensajes) == 1


# ── Alerta de incendio (2ª regla) ────────────────────────────────────────────

def _foco(dist=5.0, sig=True, frp=30.0):
    from types import SimpleNamespace

    return SimpleNamespace(distancia_km=dist, es_significativo=sig, frp=frp)


def test_incendio_alerta_y_estado(db):
    espia = _Espia()
    accion = notificador.revisar_y_notificar_incendio(LUGAR, CHAT, enviar=espia, focos=[_foco()])

    assert accion == "alerta"
    assert "FOCO DE CALOR" in espia.mensajes[0][0]
    assert storage.obtener_config(f"alerta:incendio:estado:{CHAT}", db_path=db) == "activa"


def test_incendio_no_repite_dentro_del_cooldown(db):
    espia = _Espia()
    notificador.revisar_y_notificar_incendio(LUGAR, CHAT, enviar=espia, focos=[_foco()])
    accion = notificador.revisar_y_notificar_incendio(LUGAR, CHAT, enviar=espia, focos=[_foco()])

    assert accion == "nada"
    assert len(espia.mensajes) == 1


def test_incendio_despejado_reset_silencioso(db):
    espia = _Espia()
    notificador.revisar_y_notificar_incendio(LUGAR, CHAT, enviar=espia, focos=[_foco()])  # activa
    accion = notificador.revisar_y_notificar_incendio(LUGAR, CHAT, enviar=espia, focos=[])  # despejado

    assert accion == "normalizado"
    assert len(espia.mensajes) == 1, "el despeje no debe mandar mensaje (evita ruido)"
    assert storage.obtener_config(f"alerta:incendio:estado:{CHAT}", db_path=db) == "normal"


def test_incendio_foco_lejano_no_alerta(db):
    espia = _Espia()
    accion = notificador.revisar_y_notificar_incendio(
        LUGAR, CHAT, enviar=espia, focos=[_foco(dist=80.0)],
    )
    assert accion == "nada"
    assert espia.mensajes == []


def test_incendio_firms_caido_sin_datos(db, monkeypatch):
    """Si FIRMS no responde (o falta la clave), se omite en vez de reventar."""
    monkeypatch.setattr(notificador, "_obtener_focos", lambda *a, **k: None)
    espia = _Espia()
    accion = notificador.revisar_y_notificar_incendio(LUGAR, CHAT, enviar=espia)

    assert accion == "sin_datos"
    assert espia.mensajes == []
