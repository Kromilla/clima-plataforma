"""
scripts/telegram_chat_id.py — Averigua tu TELEGRAM_CHAT_ID.

El bot necesita saber a qué chat enviar las alertas. Este script lee los últimos
mensajes que le escribiste al bot y muestra el chat_id correspondiente.

Uso:
    1. En Telegram, escríbele /start a tu bot.
    2. python scripts/telegram_chat_id.py
    3. Copia el chat_id en tu .env (lo intenta actualizar solo).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

# Permite ejecutar el script desde la raíz del repo sin instalar el paquete.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from config import cargar_dotenv  # noqa: E402

cargar_dotenv()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    sys.exit("Falta TELEGRAM_BOT_TOKEN en el .env")

BASE = f"https://api.telegram.org/bot{TOKEN}"

# Nombre del bot (para instrucciones claras) — se consulta a la API, no se hardcodea.
try:
    bot = requests.get(f"{BASE}/getMe", timeout=10).json().get("result", {})
    nombre_bot = "@" + bot.get("username", "tu_bot")
except requests.RequestException:
    nombre_bot = "tu bot"

print(f"Buscando mensajes recientes hacia {nombre_bot}…\n")
r = requests.get(f"{BASE}/getUpdates", params={"limit": 10, "offset": -10}, timeout=10)
updates = r.json().get("result", [])

if not updates:
    print("Sin mensajes. Haz lo siguiente:")
    print(f"   1. Abre Telegram y busca {nombre_bot}")
    print("   2. Escríbele /start")
    print("   3. Vuelve aquí y corre este script de nuevo\n")
    sys.exit(0)

print(f"{len(updates)} mensaje(s) encontrado(s):\n")
vistos: dict[int, str] = {}
for u in updates:
    chat = u.get("message", {}).get("chat", {})
    cid = chat.get("id")
    if cid and cid not in vistos:
        nombre = f"{chat.get('first_name', '')} {chat.get('last_name', '')}".strip()
        vistos[cid] = nombre or chat.get("username", "")
        print(f"  chat_id : {cid}   ({vistos[cid] or 'sin nombre'})")

primer_id = next(iter(vistos))
print(f"\nTu chat_id es: {primer_id}")

# Actualiza el .env de la raíz del repo si tiene la línea.
env = RAIZ / ".env"
try:
    if env.exists():
        lineas = env.read_text(encoding="utf-8").splitlines()
        if any(ln.startswith("TELEGRAM_CHAT_ID=") for ln in lineas):
            nuevas = [
                f"TELEGRAM_CHAT_ID={primer_id}" if ln.startswith("TELEGRAM_CHAT_ID=") else ln
                for ln in lineas
            ]
            env.write_text("\n".join(nuevas) + "\n", encoding="utf-8")
            print(f".env actualizado: TELEGRAM_CHAT_ID={primer_id}")
except OSError as exc:
    print(f"No pude actualizar el .env ({exc}). Ponlo a mano: TELEGRAM_CHAT_ID={primer_id}")
