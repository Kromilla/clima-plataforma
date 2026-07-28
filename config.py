"""
config.py — Carga y valida la configuración desde .env

Principio: si falta una variable obligatoria, el programa termina con un mensaje
claro antes de hacer cualquier otra cosa. Nunca un KeyError o AttributeError a
mitad de ejecución.

Uso:
    from config import cfg
    print(cfg.OPENAQ_API_KEY)
"""
import os
import sys
from pathlib import Path


def cargar_dotenv(path: Path | None = None) -> None:
    """
    Carga un archivo .env manualmente (sin dependencia extra).

    Público para que scripts sueltos (dia1_*.py) puedan leer las claves del .env
    sin hardcodearlas ni disparar la validación completa de _Config.
    """
    path = path or (Path(__file__).parent / ".env")
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            # Solo establece si no está ya en el entorno (permite override)
            os.environ.setdefault(clave, valor)


def _validar(variables: list[str]) -> None:
    """Verifica que todas las variables existan. Si no, sale con mensaje claro."""
    faltantes = [v for v in variables if not os.environ.get(v)]
    if faltantes:
        print("\n[ERROR] Variables de entorno obligatorias no encontradas:")
        for var in faltantes:
            print(f"  • {var}")
        print("\n→ Crea o edita el archivo .env en la raíz del proyecto.")
        print("→ Consulta .env.example para ver las variables requeridas.\n")
        sys.exit(1)


class _Config:
    """Contenedor de configuración con acceso por atributo."""

    def __init__(self) -> None:
        # Busca .env en el directorio del proyecto (un nivel arriba de este archivo)
        cargar_dotenv(Path(__file__).parent / ".env")

        # ── Variables obligatorias para la Fase 1 ──────────────────────────
        _validar(["OPENAQ_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])

        # API Keys
        self.OPENAQ_API_KEY: str = os.environ["OPENAQ_API_KEY"]
        self.TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
        self.TELEGRAM_CHAT_ID: str = os.environ["TELEGRAM_CHAT_ID"]

        # Electricity Maps (opcional en Fase 1 — no bloquea arranque)
        self.ELECTRICITY_MAPS_KEY: str | None = os.environ.get("ELECTRICITY_MAPS_KEY")

        # ── Parámetros de comportamiento (con defaults razonables) ──────────
        self.UMBRAL_PM25_DEFAULT: float = float(
            os.environ.get("UMBRAL_PM25_DEFAULT", "50.0")
        )
        self.OPENAQ_BASE_URL: str = "https://api.openaq.org/v3"
        self.POLLING_INTERVALO_SEG: int = int(
            os.environ.get("POLLING_INTERVALO_SEG", "900")  # 15 min
        )
        self.DB_PATH: str = os.environ.get("DB_PATH", "clima.db")
        self.LOG_FILE: str = os.environ.get("LOG_FILE", "bot.log")


# Instancia única — se importa directamente
cfg = _Config()
