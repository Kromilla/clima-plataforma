"""
bot.py — Bot de Telegram para alertas de calidad del aire — Santa Marta.

Fuentes de datos (ver sources/registry.py):
  Aire   : Open-Meteo Air Quality (modelo CAMS, cobertura global, sin API key)
  Clima  : Open-Meteo Forecast
  Energía: XM (operador oficial del mercado eléctrico colombiano, sin API key)

OpenAQ quedó como fuente secundaria: la validación del Día 1 (§8 del informe)
confirmó que no tiene ninguna estación en Santa Marta ni en Barranquilla — de
hecho no tiene ninguna en toda la costa Caribe.

Comandos:
    /start    — Bienvenida
    /estado   — Situación actual (aire, clima, energía)
    /umbral N — Cambiar umbral de alerta (ej. /umbral 35)
    /ayuda    — Lista de comandos

Regla: NUNCA deja una excepción sin capturar.
"""
from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import NetworkError
from telegram.ext import Application, CommandHandler, ContextTypes

import logging_setup
import storage
from alerts import formato_estado, revisar_alerta
from config import cfg
from locations import DEFAULT_LUGAR, LUGARES
from sources.openaq import OpenAQSinDatos
from sources.openaq import obtener_ultimo as openaq_obtener
from sources.openmeteo_aire import OpenMeteoAireSinDatos
from sources.openmeteo_aire import obtener_ultimo as openmeteo_obtener
from sources.registry import por_id

# ── Logging ───────────────────────────────────────────────────────────────────
# Centralizado en logging_setup: fuerza UTF-8 en consola (Windows usa cp1252 y
# reventaba con los µg/m³ y emojis) y silencia el logger de httpx, que escribía
# el token de Telegram en texto plano.
logging_setup.configurar(cfg.LOG_FILE)

logger = logging.getLogger(__name__)

storage.inicializar_bd()


def _lugar_con_id(lugar_id: str) -> dict:
    lugar = LUGARES[lugar_id].copy()
    lugar["_id"] = lugar_id
    return lugar


def _umbral_para_chat(chat_id: str) -> float:
    raw = storage.obtener_config(f"umbral:{chat_id}")
    try:
        return float(raw) if raw else cfg.UMBRAL_PM25_DEFAULT
    except ValueError:
        return cfg.UMBRAL_PM25_DEFAULT


def _obtener_aire(lugar_id: str):
    """
    Cascada de fuentes de aire:
      1. Open-Meteo (modelo global, siempre disponible)
      2. OpenAQ (estaciones físicas — hoy sin cobertura en la región)
    Devuelve None si ninguna tiene datos.
    """
    lugar = _lugar_con_id(lugar_id)

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


def _extras_estado(lugar_id: str) -> str:
    """
    Líneas extra de /estado con las demás fuentes registradas (clima, energía).
    Se leen de caché: /estado debe responder rápido, el recolector es quien
    refresca. Si una fuente no tiene dato, simplemente no aparece.
    """
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


# ── Handlers de comandos ──────────────────────────────────────────────────────

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
    umbral = _umbral_para_chat(chat_id)

    await update.message.reply_chat_action(action="typing")

    try:
        lectura = _obtener_aire(DEFAULT_LUGAR)
        if lectura is None:
            await update.message.reply_text(
                "⚠️ No hay datos de calidad del aire disponibles ahora mismo.\n"
                "Todas las fuentes están caídas y no hay caché reciente.\n"
                "Inténtalo de nuevo en unos minutos."
            )
            return
        texto = formato_estado(lectura, umbral) + _extras_estado(DEFAULT_LUGAR)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error inesperado en /estado: %s", exc)
        texto = "❌ Error interno obteniendo los datos. Inténtalo de nuevo."

    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def cmd_umbral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)

    if not context.args:
        umbral_actual = _umbral_para_chat(chat_id)
        await update.message.reply_text(
            f"Tu umbral actual es *{umbral_actual:.1f} µg/m³*.\n"
            f"Para cambiarlo: `/umbral 35`",
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
        "*Fuentes de datos:*\n"
        "• Aire: modelo Copernicus CAMS (Open-Meteo)\n"
        "• Clima: Open-Meteo\n"
        "• Energía: XM (operador eléctrico oficial de Colombia)\n\n"
        "*Escala PM2.5:*\n"
        "🟢 0-12 Buena · 🟡 12-35 Moderada · 🟠 35-55 Dañina grupos sensibles\n"
        "🔴 55-150 Dañina · 🟣 150-250 Muy dañina · ⚫ >250 Peligrosa"
    )
    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def cmd_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Última red de seguridad: ningún error debe tumbar el bot."""
    logger.exception("Excepción no capturada en un handler:", exc_info=context.error)


# ── Chequeo periódico de alertas ─────────────────────────────────────────────

async def revisar_y_alertar(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job del JobQueue de PTB: revisa el aire y envía alerta si supera el umbral.

    Corre en el mismo event loop que el bot. La versión anterior usaba un hilo
    aparte con `asyncio.run()`, lo que crea un event loop nuevo en cada vuelta
    mientras el cliente HTTP del bot está atado al loop principal — una fuente
    silenciosa de fallos.
    """
    chat_id = cfg.TELEGRAM_CHAT_ID
    try:
        umbral = _umbral_para_chat(chat_id)
        lectura = _obtener_aire(DEFAULT_LUGAR)
        if lectura is None:
            logger.warning("Chequeo de alertas: sin lectura disponible")
            return

        mensaje = revisar_alerta(lectura.valor, umbral)
        if mensaje:
            await context.bot.send_message(
                chat_id=chat_id, text=mensaje, parse_mode=ParseMode.MARKDOWN,
            )
            logger.info("Alerta enviada: PM2.5=%.1f (umbral %.1f)", lectura.valor, umbral)
        else:
            logger.info(
                "Sin alerta: PM2.5=%.1f bajo el umbral %.1f", lectura.valor, umbral
            )
    except Exception as exc:  # noqa: BLE001 — el job nunca debe morir
        logger.exception("Error en chequeo de alertas: %s", exc)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("Iniciando ClimaBot — ciudad: %s", DEFAULT_LUGAR)

    app = (
        Application.builder()
        .token(cfg.TELEGRAM_BOT_TOKEN)
        # Los timeouts por defecto (5 s) son cortos para una conexión doméstica:
        # bastaba un pico de latencia para tumbar el arranque.
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .get_updates_connect_timeout(30.0)
        .get_updates_read_timeout(30.0)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("umbral", cmd_umbral))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_error_handler(cmd_error)

    if app.job_queue is None:
        logger.error(
            "JobQueue no disponible — las alertas automáticas quedan desactivadas. "
            'Instala con: pip install "python-telegram-bot[job-queue]"'
        )
    else:
        app.job_queue.run_repeating(
            revisar_y_alertar,
            interval=cfg.POLLING_INTERVALO_SEG,
            first=10,  # primera revisión 10 s tras arrancar
            name="chequeo-alertas",
        )
        logger.info("Chequeo de alertas cada %ds", cfg.POLLING_INTERVALO_SEG)

    logger.info("Bot escuchando comandos…")
    # bootstrap_retries=-1 → reintentos infinitos al conectar.
    # Con el valor por defecto (0), PTB abortaba con "Failed run number 0 of 0"
    # ante un solo timeout de red al arrancar y el bot moría para siempre. Para
    # un proceso que debe correr desatendido enviando alertas, un hipo de red no
    # puede ser fatal.
    app.run_polling(drop_pending_updates=True, bootstrap_retries=-1)


def main_supervisado(max_reinicios: int = 0) -> None:
    """
    Ejecuta el bot reiniciándolo si muere por un fallo de red.

    Es la última red de seguridad: `bootstrap_retries` cubre la conexión inicial
    y PTB reintenta durante el polling, pero si aun así la excepción escapa,
    preferimos reiniciar antes que dejar de enviar alertas en silencio.

    Args:
        max_reinicios: 0 = sin límite.
    """
    intentos = 0
    while True:
        try:
            main()
            return  # salida limpia (Ctrl+C)
        except KeyboardInterrupt:
            logger.info("Detenido por el usuario.")
            return
        except NetworkError as exc:
            intentos += 1
            if max_reinicios and intentos > max_reinicios:
                logger.error("Demasiados reinicios (%d). Abandonando.", intentos)
                raise
            espera = min(5 * 2 ** (intentos - 1), 300)
            logger.warning(
                "El bot cayó por un problema de red (%s). Reiniciando en %d s… (intento %d)",
                exc, espera, intentos,
            )
            time.sleep(espera)
        except Exception:
            logger.exception("El bot murió por un error no recuperable.")
            raise


if __name__ == "__main__":
    main_supervisado()
