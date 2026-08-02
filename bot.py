"""
bot.py — Bot de Telegram en modo polling, para correr local.

Los comandos viven en telegram_handlers (compartidos con el webhook de api.py).
En producción (Render) el bot corre por webhook, no con este archivo.

Comandos: /start, /estado, /umbral N, /ayuda.
"""
from __future__ import annotations

import logging
import time

from telegram.constants import ParseMode
from telegram.error import NetworkError
from telegram.ext import Application, ContextTypes

import logging_setup
import storage
import telegram_handlers
from alerts import revisar_alerta
from config import cfg
from locations import DEFAULT_LUGAR

# logging_setup fuerza UTF-8 en consola y silencia httpx (que logueaba el token).
logging_setup.configurar(cfg.LOG_FILE)
logger = logging.getLogger(__name__)

storage.inicializar_bd()


async def revisar_y_alertar(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job del JobQueue: revisa el aire y alerta si supera el umbral."""
    chat_id = cfg.TELEGRAM_CHAT_ID
    try:
        umbral = telegram_handlers.umbral_para_chat(chat_id)
        lectura = telegram_handlers.obtener_aire(DEFAULT_LUGAR)
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
            logger.info("Sin alerta: PM2.5=%.1f bajo el umbral %.1f", lectura.valor, umbral)
    except Exception as exc:  # noqa: BLE001 — el job nunca debe morir
        logger.exception("Error en chequeo de alertas: %s", exc)


def main() -> None:
    logger.info("Iniciando ClimaBot (polling) — ciudad: %s", DEFAULT_LUGAR)

    app = (
        Application.builder()
        .token(cfg.TELEGRAM_BOT_TOKEN)
        # Timeouts holgados: en una conexión doméstica un pico de latencia con los
        # de por defecto (5 s) bastaba para tumbar el arranque.
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .get_updates_connect_timeout(30.0)
        .get_updates_read_timeout(30.0)
        .build()
    )

    telegram_handlers.registrar(app)

    if app.job_queue is None:
        logger.error(
            "JobQueue no disponible — sin alertas automáticas. "
            'Instala: pip install "python-telegram-bot[job-queue]"'
        )
    else:
        app.job_queue.run_repeating(
            revisar_y_alertar, interval=cfg.POLLING_INTERVALO_SEG, first=10,
            name="chequeo-alertas",
        )
        logger.info("Chequeo de alertas cada %ds", cfg.POLLING_INTERVALO_SEG)

    logger.info("Bot escuchando comandos…")
    # bootstrap_retries=-1: reintenta la conexión inicial indefinidamente.
    app.run_polling(drop_pending_updates=True, bootstrap_retries=-1)


def main_supervisado(max_reinicios: int = 0) -> None:
    """
    Ejecuta el bot y lo reinicia (con espera creciente) si cae por red.
    max_reinicios=0 → sin límite.
    """
    intentos = 0
    while True:
        try:
            main()
            return
        except KeyboardInterrupt:
            logger.info("Detenido por el usuario.")
            return
        except NetworkError as exc:
            intentos += 1
            if max_reinicios and intentos > max_reinicios:
                logger.error("Demasiados reinicios (%d). Abandonando.", intentos)
                raise
            espera = min(5 * 2 ** (intentos - 1), 300)
            logger.warning("Bot caído por red (%s). Reiniciando en %d s… (intento %d)",
                           exc, espera, intentos)
            time.sleep(espera)
        except Exception:
            logger.exception("El bot murió por un error no recuperable.")
            raise


if __name__ == "__main__":
    main_supervisado()
