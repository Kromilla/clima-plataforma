"""
telegram_handlers.py — Comandos del bot, compartidos por dos modos de ejecución:

  - bot.py  → polling (para correr local).
  - api.py  → webhook (en Render; Telegram hace POST a la API).

Sin efectos de import (no configura logging ni toca la BD): eso lo hace quien lo
use. Así la API puede importar los handlers sin arrastrar el arranque del bot.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

import storage
from alerts import formato_estado
from config import cfg
from locations import DEFAULT_LUGAR, LUGARES
from sources.openaq import OpenAQSinDatos
from sources.openaq import obtener_ultimo as openaq_obtener
from sources.openmeteo_aire import OpenMeteoAireSinDatos
from sources.openmeteo_aire import obtener_ultimo as openmeteo_obtener
from sources.registry import por_id

logger = logging.getLogger(__name__)


def lugar_con_id(lugar_id: str) -> dict:
    lugar = LUGARES[lugar_id].copy()
    lugar["_id"] = lugar_id
    return lugar


def umbral_para_chat(chat_id: str) -> float:
    raw = storage.obtener_config(f"umbral:{chat_id}")
    try:
        return float(raw) if raw else cfg.UMBRAL_PM25_DEFAULT
    except ValueError:
        return cfg.UMBRAL_PM25_DEFAULT


def obtener_aire(lugar_id: str):
    """
    Cascada de fuentes de aire: Open-Meteo (modelo global) → OpenAQ (estaciones,
    hoy sin cobertura). Devuelve None si ninguna tiene datos.
    """
    lugar = lugar_con_id(lugar_id)
    try:
        return openmeteo_obtener(lugar)
    except OpenMeteoAireSinDatos as exc:
        logger.warning("Open-Meteo falló, intentando OpenAQ: %s", exc)
    except Exception as exc:  # noqa: BLE001 — nunca dejar escapar una excepción
        logger.exception("Open-Meteo error inesperado: %s", exc)

    try:
        return openaq_obtener(lugar)
    except OpenAQSinDatos:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.exception("OpenAQ error inesperado: %s", exc)

    return None


def extras_estado(lugar_id: str) -> str:
    """Líneas extra de /estado con clima y energía (leídas de caché)."""
    lineas: list[str] = []
    for fuente_id in ("openmeteo-clima", "xm"):
        registrada = por_id(fuente_id)
        if registrada is None:
            continue
        lectura = storage.ultimo_valor(fuente_id, lugar_id, registrada.metrica)
        if lectura is None:
            continue
        lineas.append(
            f"{registrada.etiqueta}: *{lectura.valor:.1f} {lectura.unidad}* "
            f"({lectura.antiguedad_texto()})"
        )
    return "\n" + "\n".join(lineas) if lineas else ""


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = (
        "🌤️ *¡Bienvenido a ClimaBot — Santa Marta!*\n\n"
        "Monitoreo de calidad del aire para Santa Marta, Colombia.\n\n"
        "Comandos disponibles:\n"
        "• `/estado` — Ver la situación ahora\n"
        "• `/umbral N` — Cambiar tu umbral de alerta (ej. `/umbral 35`)\n"
        "• `/ayuda` — Más información\n\n"
        "ℹ️ Los datos de aire provienen del modelo Copernicus CAMS."
    )
    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    umbral = umbral_para_chat(chat_id)

    await update.message.reply_chat_action(action="typing")

    try:
        lectura = obtener_aire(DEFAULT_LUGAR)
        if lectura is None:
            await update.message.reply_text(
                "⚠️ No hay datos de calidad del aire disponibles ahora mismo.\n"
                "Inténtalo de nuevo en unos minutos."
            )
            return
        texto = formato_estado(lectura, umbral) + extras_estado(DEFAULT_LUGAR)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error inesperado en /estado: %s", exc)
        texto = "❌ Error interno obteniendo los datos. Inténtalo de nuevo."

    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def cmd_umbral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)

    if not context.args:
        umbral_actual = umbral_para_chat(chat_id)
        await update.message.reply_text(
            f"Tu umbral actual es *{umbral_actual:.1f} µg/m³*.\nPara cambiarlo: `/umbral 35`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    try:
        nuevo = float(context.args[0])
        if not (1 <= nuevo <= 500):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Usa un número entre 1 y 500.\nEjemplo: `/umbral 35`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    storage.guardar_config(f"umbral:{chat_id}", str(nuevo))
    await update.message.reply_text(
        f"✅ Umbral actualizado a *{nuevo:.1f} µg/m³*.\n"
        f"Recibirás alertas cuando PM2.5 supere este valor.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = (
        "🌤️ *ClimaBot — Santa Marta*\n\n"
        "*Comandos:*\n"
        "• `/estado` — Situación actual\n"
        "• `/umbral N` — Cambiar umbral de alerta\n"
        "• `/ayuda` — Esta ayuda\n\n"
        "*Fuentes:*\n"
        "• Aire: modelo Copernicus CAMS (Open-Meteo)\n"
        "• Clima: Open-Meteo · Energía: XM\n\n"
        "*Escala PM2.5:*\n"
        "🟢 0-12 Buena · 🟡 12-35 Moderada · 🟠 35-55 Dañina grupos sensibles\n"
        "🔴 55-150 Dañina · 🟣 150-250 Muy dañina · ⚫ >250 Peligrosa"
    )
    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def cmd_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Última red de seguridad: ningún error debe tumbar el bot."""
    logger.exception("Excepción no capturada en un handler:", exc_info=context.error)


def registrar(app: Application) -> None:
    """Registra los comandos y el error handler en una Application de PTB."""
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("umbral", cmd_umbral))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_error_handler(cmd_error)
