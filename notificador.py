"""
notificador.py — Alertas proactivas de PM2.5 por Telegram.

Lo dispara el collector (que corre cada 20 min en GitHub Actions). Los runners de
GitHub sí alcanzan api.telegram.org, así que el aviso sale desde ahí aunque la red
del usuario tenga bloqueado Telegram (por eso el bot responde por webhook, ver
telegram_handlers).

Evita el spam con histéresis y un estado guardado en `storage` (config_usuario),
que persiste entre ejecuciones porque cada pasada del collector es un proceso
nuevo:

  - normal → aire malo   : ALERTA (una vez, al cruzar el umbral)
  - aire malo (sostenido): RECORDATORIO, como mucho cada COOLDOWN
  - aire malo → normal   : aviso de NORMALIZADO
  - sin cambios          : nada

Si la última lectura está vieja (la fuente se cayó), no se alerta: avisar sobre
un dato obsoleto sería peor que no avisar.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

import storage
from alerts import nivel_pm25, revisar_alerta
from config import cfg
from locations import DEFAULT_LUGAR

logger = logging.getLogger(__name__)

FUENTE_AIRE = "openmeteo-aire"
METRICA_AIRE = "pm25"

# Mientras el aire siga malo, no repetir el aviso más seguido que esto.
COOLDOWN_ALERTA_SEG = 6 * 3600
# No alertar con datos más viejos que esto (la fuente pudo haberse caído).
MAX_ANTIGUEDAD_ALERTA_MIN = 180


def _umbral(chat_id: str) -> float:
    """Umbral configurado por el usuario, o el default. Igual que en el bot."""
    raw = storage.obtener_config(f"umbral:{chat_id}")
    try:
        return float(raw) if raw else cfg.UMBRAL_PM25_DEFAULT
    except ValueError:
        return cfg.UMBRAL_PM25_DEFAULT


def _parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def decidir(
    valor: float,
    umbral: float,
    estado: str,
    ultima_ts: datetime | None,
    ahora: datetime,
    cooldown_seg: float = COOLDOWN_ALERTA_SEG,
) -> tuple[str, str, datetime | None]:
    """
    Máquina de estados de la alerta. Función pura (sin I/O) para poder testearla.

    Returns:
        (accion, nuevo_estado, nueva_ts) con accion ∈
        {"alerta", "recordatorio", "normalizado", "nada"}.
    """
    if valor >= umbral:
        if estado != "activa":
            return "alerta", "activa", ahora
        if ultima_ts is None or (ahora - ultima_ts).total_seconds() >= cooldown_seg:
            return "recordatorio", "activa", ahora
        return "nada", "activa", ultima_ts

    if estado == "activa":
        return "normalizado", "normal", ultima_ts
    return "nada", "normal", ultima_ts


def _mensaje_normalizado(valor: float, umbral: float) -> str:
    etiqueta, _ = nivel_pm25(valor)
    return (
        "✅ *Aire normalizado*\n\n"
        f"PM2.5 bajó a *{valor:.1f} µg/m³*, por debajo de tu umbral "
        f"({umbral:.1f} µg/m³).\n"
        f"Calidad: {etiqueta}"
    )


def enviar_telegram(texto: str, chat_id: str) -> bool:
    """Envía un mensaje por la API de Telegram. Devuelve True si lo logró."""
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — un fallo de envío no debe frenar el collector
        logger.warning("No se pudo enviar la alerta por Telegram: %s", exc)
        return False


def revisar_y_notificar(
    lugar_id: str = DEFAULT_LUGAR,
    chat_id: str | None = None,
    *,
    enviar=enviar_telegram,
    ahora: datetime | None = None,
) -> str:
    """
    Revisa la última lectura de aire y notifica si corresponde.

    `enviar` y `ahora` son inyectables para los tests. Devuelve la acción tomada
    ("alerta" | "recordatorio" | "normalizado" | "nada" | "sin_datos" | "obsoleto").
    """
    chat_id = chat_id or cfg.TELEGRAM_CHAT_ID
    ahora = ahora or datetime.now(timezone.utc)

    lectura = storage.ultimo_valor(FUENTE_AIRE, lugar_id, METRICA_AIRE)
    if lectura is None:
        logger.info("Alertas: sin lectura de aire, nada que evaluar")
        return "sin_datos"

    antiguedad_min = (ahora - lectura.ts).total_seconds() / 60
    if antiguedad_min > MAX_ANTIGUEDAD_ALERTA_MIN:
        logger.info(
            "Alertas: la lectura de aire tiene %.0f min; se omite para no alertar "
            "sobre un dato obsoleto", antiguedad_min,
        )
        return "obsoleto"

    umbral = _umbral(chat_id)
    estado = storage.obtener_config(f"alerta:estado:{chat_id}", "normal")
    ultima_ts = _parse_ts(storage.obtener_config(f"alerta:ultima:{chat_id}", ""))

    accion, nuevo_estado, nueva_ts = decidir(
        lectura.valor, umbral, estado, ultima_ts, ahora,
    )

    enviado = True
    if accion in ("alerta", "recordatorio"):
        mensaje = revisar_alerta(lectura.valor, umbral) or ""
        if accion == "recordatorio":
            mensaje = "🔁 *Recordatorio — la alerta sigue activa*\n\n" + mensaje
        enviado = enviar(mensaje, chat_id)
    elif accion == "normalizado":
        enviado = enviar(_mensaje_normalizado(lectura.valor, umbral), chat_id)

    # El estado solo avanza si el envío funcionó: si Telegram estaba inalcanzable,
    # se reintenta en la próxima pasada en vez de perder el aviso.
    if enviado and accion != "nada":
        storage.guardar_config(f"alerta:estado:{chat_id}", nuevo_estado)
        storage.guardar_config(
            f"alerta:ultima:{chat_id}", nueva_ts.isoformat() if nueva_ts else "",
        )

    logger.info(
        "Alertas: PM2.5=%.1f umbral=%.1f estado=%s -> %s (envío=%s)",
        lectura.valor, umbral, estado, accion, "ok" if enviado else "falló",
    )
    return accion
