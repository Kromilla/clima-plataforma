"""
dia1_chatid.py — Obtiene tu chat_id de Telegram
Instrucciones:
  1. Abre Telegram y escribe /start a @kromiclima_bot
  2. Corre este script: python dia1_chatid.py
  3. Copia el chat_id que aparece y ponlo en el .env
"""
import os
import sys

import requests

from config import cargar_dotenv

cargar_dotenv()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    sys.exit("Falta TELEGRAM_BOT_TOKEN en el .env")

BASE = f"https://api.telegram.org/bot{TOKEN}"

print("Buscando mensajes de @kromiclima_bot ...\n")
r = requests.get(f"{BASE}/getUpdates", params={"limit": 10, "offset": -10}, timeout=10)
updates = r.json().get("result", [])

if not updates:
    print("❌ Sin mensajes. Haz lo siguiente:")
    print("   1. Abre Telegram")
    print("   2. Busca @kromiclima_bot")
    print("   3. Escribe /start")
    print("   4. Vuelve aqui y corre este script de nuevo\n")
else:
    print(f"✅ {len(updates)} mensaje(s) encontrado(s):\n")
    vistos = set()
    for u in updates:
        msg = u.get("message", {})
        chat = msg.get("chat", {})
        cid = chat.get("id")
        if cid and cid not in vistos:
            vistos.add(cid)
            nombre = f"{chat.get('first_name', '')} {chat.get('last_name', '')}".strip()
            username = chat.get("username", "")
            texto = msg.get("text", "(sin texto)")
            print(f"  chat_id  : {cid}")
            print(f"  Nombre   : {nombre}")
            if username:
                print(f"  Username : @{username}")
            print(f"  Mensaje  : {texto}")
            print()

    if vistos:
        primer_id = list(vistos)[0]
        print(f"\n👉 Tu chat_id es probablemente: {primer_id}")
        print(f"   Ponlo en tu .env como: TELEGRAM_CHAT_ID={primer_id}\n")

        # Intentar actualizar .env automáticamente
        try:
            with open(".env", "r", encoding="utf-8") as f:
                contenido = f.read()
            if "TELEGRAM_CHAT_ID=" in contenido:
                lineas = contenido.splitlines()
                nuevas = []
                for linea in lineas:
                    if linea.startswith("TELEGRAM_CHAT_ID="):
                        nuevas.append(f"TELEGRAM_CHAT_ID={primer_id}")
                    else:
                        nuevas.append(linea)
                with open(".env", "w", encoding="utf-8") as f:
                    f.write("\n".join(nuevas) + "\n")
                print(f"✅ .env actualizado automáticamente con TELEGRAM_CHAT_ID={primer_id}")
        except Exception as e:
            print(f"No pude actualizar .env automáticamente: {e}")
            print(f"Edítalo manualmente: TELEGRAM_CHAT_ID={primer_id}")
