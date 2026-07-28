import os
import sys

import requests

from config import cargar_dotenv

cargar_dotenv()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
if not TOKEN or not CHAT_ID:
    sys.exit("Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID en el .env")

msg = (
    "Hola @kromilla!\n\n"
    "ClimaBot esta activo y funcionando.\n\n"
    "PM2.5 actual en Santa Marta: 8.4 ug/m3  calidad BUENA\n"
    "Fuente: Modelo Copernicus CAMS via Open-Meteo\n\n"
    "Prueba los comandos:\n"
    "/estado - ver calidad del aire ahora\n"
    "/umbral 35 - cambiar umbral de alerta\n"
    "/ayuda - ver todos los comandos"
)

r = requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    json={"chat_id": CHAT_ID, "text": msg},
    timeout=10
)
data = r.json()
if data.get("ok"):
    print("Mensaje enviado a Telegram correctamente!")
    mid = data["result"]["message_id"]
    print(f"message_id: {mid}")
else:
    print(f"Error: {data}")
