"""
scripts/telegram_test.py — Envía un mensaje de prueba por Telegram.

Sirve para confirmar que el token y el chat_id están bien configurados antes de
levantar el bot completo.

Uso:
    python scripts/telegram_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from config import cargar_dotenv  # noqa: E402

cargar_dotenv()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
if not TOKEN or not CHAT_ID:
    sys.exit("Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID en el .env")

mensaje = (
    "✅ ClimaBot está configurado correctamente.\n\n"
    "Comandos disponibles:\n"
    "/estado — calidad del aire ahora\n"
    "/umbral 35 — cambiar el umbral de alerta\n"
    "/ayuda — ver todos los comandos"
)

resp = requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    json={"chat_id": CHAT_ID, "text": mensaje},
    timeout=10,
).json()

if resp.get("ok"):
    print("Mensaje enviado correctamente. Revisa tu Telegram.")
else:
    sys.exit(f"Error al enviar: {resp}")
