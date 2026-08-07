"""
api.py — API REST con FastAPI para proveer datos al frontend React.

Las fuentes no se listan aquí: se leen de `sources/registry.py`, así que agregar
una fuente nueva no requiere tocar este archivo (principio §5.1 del informe).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import risk
import storage
import telegram_handlers
from config import cfg
from locations import COLOMBIA, DEFAULT_LUGAR, LUGARES
from sources import firms, openmeteo_clima
from sources.base import Lectura
from sources.registry import FUENTES, por_id

# httpx (que usa la librería de Telegram) loguea la URL con el token; silenciarlo.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("api")


# ── Bot de Telegram por webhook ───────────────────────────────────────────────
# En Render, Telegram hace POST a este servicio en vez de que el bot haga polling
# (que necesitaría un proceso 24/7 aparte). Se activa solo si hay una URL pública
# (RENDER_EXTERNAL_URL la define Render); en local no se toca (ahí corre bot.py).

def _webhook_base() -> str | None:
    return os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL")


def _webhook_secret() -> str:
    """Secreto determinista derivado del token (sin configuración extra)."""
    return hashlib.sha256(cfg.TELEGRAM_BOT_TOKEN.encode()).hexdigest()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from telegram import Update
    from telegram.ext import Application

    app.state.tg = None
    base = _webhook_base()
    if base and cfg.TELEGRAM_BOT_TOKEN:
        try:
            tg = Application.builder().token(cfg.TELEGRAM_BOT_TOKEN).updater(None).build()
            telegram_handlers.registrar(tg)
            await tg.initialize()
            await tg.start()
            url = f"{base.rstrip('/')}/telegram/webhook"
            await tg.bot.set_webhook(
                url=url, secret_token=_webhook_secret(),
                allowed_updates=Update.ALL_TYPES,
            )
            app.state.tg = tg
            logger.info("Webhook de Telegram configurado en %s", url)
        except Exception as exc:  # noqa: BLE001 — un fallo del bot no debe tumbar la API
            logger.warning("No se pudo configurar el webhook de Telegram: %s", exc)

    yield

    if app.state.tg is not None:
        # No se borra el webhook: así Telegram sigue despertando el servicio dormido.
        await app.state.tg.stop()
        await app.state.tg.shutdown()


app = FastAPI(title="ClimaBot API", lifespan=lifespan)

# Dashboard (Vercel) y API (Render) viven en dominios distintos → hace falta CORS.
# credentials=False porque la app no usa cookies (y con credenciales el "*" sería
# inválido). Restringir con CORS_ORIGINS="https://tu-app.vercel.app".
_origenes = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origenes],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage.inicializar_bd()


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    """
    Recibe los updates que Telegram envía por webhook (solo en Render).

    El header secreto lo comprueba primero: descarta POST falsos sin tocar el bot.
    """
    # compare_digest: comparación en tiempo constante, sin fuga por timing.
    if not hmac.compare_digest(x_telegram_bot_api_secret_token, _webhook_secret()):
        raise HTTPException(status_code=403, detail="Token de webhook inválido")

    tg = getattr(app.state, "tg", None)
    if tg is None:
        raise HTTPException(status_code=503, detail="Bot no inicializado")

    from telegram import Update

    update = Update.de_json(await request.json(), tg.bot)
    await tg.process_update(update)
    return {"ok": True}


class LecturaSchema(BaseModel):
    valor: float
    unidad: str
    metrica: str
    fuente: str
    procedencia: str
    lugar_id: str
    estacion_nombre: str
    ts: str
    # Campos derivados: el frontend no debe recalcular la antigüedad por su cuenta.
    antiguedad_min: int
    antiguedad_texto: str
    etiqueta_procedencia: str
    es_reciente: bool


def _serializar(lectura: Lectura) -> LecturaSchema:
    """Convierte una Lectura del dominio al schema que consume el frontend."""
    return LecturaSchema(
        valor=lectura.valor,
        unidad=lectura.unidad,
        metrica=lectura.metrica,
        fuente=lectura.fuente,
        procedencia=lectura.procedencia,
        lugar_id=lectura.lugar_id,
        estacion_nombre=lectura.estacion_nombre,
        ts=lectura.ts.isoformat(),
        antiguedad_min=lectura.antiguedad_min,
        antiguedad_texto=lectura.antiguedad_texto(),
        etiqueta_procedencia=lectura.etiqueta_procedencia(),
        es_reciente=lectura.es_reciente(),
    )


def _validar_lugar(lugar_id: str) -> None:
    if lugar_id not in LUGARES:
        raise HTTPException(
            status_code=404,
            detail=f"Lugar '{lugar_id}' no encontrado. Disponibles: {list(LUGARES)}",
        )


@app.get("/api/lugares")
def listar_lugares():
    """
    Lugares disponibles. El frontend usa esto en vez de hardcodear el id —
    hardcodearlo fue justo lo que rompió el dashboard antes (pedía 'CO-SMR').
    """
    return {
        "default": DEFAULT_LUGAR,
        "lugares": [
            {"id": lid, "nombre": datos.get("nombre", lid), "lat": datos["lat"], "lon": datos["lon"]}
            for lid, datos in LUGARES.items()
        ],
    }


@app.get("/api/fuentes")
def listar_fuentes():
    """Fuentes registradas y qué métrica produce cada una."""
    return [
        {"id": f.id, "etiqueta": f.etiqueta, "metrica": f.metrica}
        for f in FUENTES
    ]


@app.get("/api/clima/actual")
def obtener_clima_actual(lugar_id: str = DEFAULT_LUGAR) -> dict[str, LecturaSchema | None]:
    """
    Último valor conocido de cada fuente registrada, con su antigüedad.
    Las claves son los ids de fuente (ver /api/fuentes).
    """
    _validar_lugar(lugar_id)

    resultado: dict[str, LecturaSchema | None] = {}
    for fuente in FUENTES:
        lectura = storage.ultimo_valor(fuente.id, lugar_id, fuente.metrica)
        resultado[fuente.id] = _serializar(lectura) if lectura else None

    return resultado


@app.get("/api/clima/historial", response_model=list[LecturaSchema])
def obtener_historial(
    fuente: str,
    lugar_id: str = DEFAULT_LUGAR,
    metrica: str | None = None,
    # Acotado a propósito: SQLite interpreta un LIMIT negativo como "sin
    # límite", así que `limite=-1` volcaba las ~17.000 filas del historial en
    # una sola respuesta.
    limite: int = Query(default=24, ge=1, le=5000),
):
    """
    Historial para las gráficas. `metrica` es opcional: si se omite se usa la
    métrica declarada por la fuente en el registro.
    """
    _validar_lugar(lugar_id)

    registrada = por_id(fuente)
    if metrica is None:
        if registrada is None:
            raise HTTPException(
                status_code=400,
                detail=f"Fuente '{fuente}' no registrada; especifica 'metrica' explícitamente.",
            )
        metrica = registrada.metrica

    return [_serializar(h) for h in storage.historial(fuente, lugar_id, metrica, limite)]


@app.get("/api/clima/ahora")
def obtener_clima_ahora(
    lugar_id: str = DEFAULT_LUGAR,
    lat: float | None = None,
    lon: float | None = None,
):
    """
    Condiciones meteorológicas actuales en vivo (para la pestaña de clima en
    tiempo real). A diferencia de /api/clima/actual (que lee de storage), esto
    consulta Open-Meteo en el momento. Nunca devuelve 500: si falla, responde
    `disponible: false` con el motivo.

    Si llegan `lat`/`lon` (geolocalización del navegador), se consulta ese punto
    exacto en vez de una ciudad de la lista — así la pestaña sirve estés donde
    estés, no solo en las 14 capitales monitoreadas.
    """
    if lat is not None and lon is not None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise HTTPException(status_code=400, detail="Coordenadas fuera de rango")
        lugar = {"lat": lat, "lon": lon, "nombre": "Tu ubicación", "_id": "gps"}
        etiqueta = "Tu ubicación"
    else:
        _validar_lugar(lugar_id)
        lugar = LUGARES[lugar_id].copy()
        lugar["_id"] = lugar_id
        etiqueta = lugar["nombre"]

    try:
        datos = openmeteo_clima.condiciones_actuales(lugar)
    except openmeteo_clima.ClimaActualError as exc:
        # Open-Meteo en vivo falló (típico: 429). Para una ciudad monitoreada,
        # el collector ya guardó temp+humedad recientes: mejor mostrar ese dato
        # real con su antigüedad que un error. Para un punto GPS arbitrario no
        # hay historial, así que queda el mensaje.
        respaldo = _clima_de_respaldo(lugar_id) if lat is None else None
        if respaldo is not None:
            return {"disponible": True, "lugar_id": lugar_id, "etiqueta": etiqueta,
                    "cacheado": True, **respaldo}
        return {"disponible": False, "mensaje": str(exc)}

    return {"disponible": True, "lugar_id": lugar_id, "etiqueta": etiqueta, **datos}


def _clima_de_respaldo(lugar_id: str) -> dict | None:
    """Último temp+humedad guardados por el collector, o None si no hay."""
    temp = storage.ultimo_valor("openmeteo-clima", lugar_id, "temperatura")
    if temp is None:
        return None
    hum = storage.ultimo_valor("openmeteo-clima", lugar_id, "humedad")
    return {
        "ts": temp.ts.strftime("%Y-%m-%dT%H:%M"),
        "temperatura": temp.valor,
        "humedad": hum.valor if hum is not None else None,
        "antiguedad_min": temp.antiguedad_min,
    }


@app.get("/api/estado/fuentes")
def estado_fuentes(lugar_id: str = DEFAULT_LUGAR):
    """
    Semáforo de salud por fuente (verde/amarillo/rojo).

    Los umbrales vienen del registro, no son globales: XM publica con días de
    rezago por diseño, así que exigirle 2 h lo pintaría rojo permanentemente.
    """
    _validar_lugar(lugar_id)

    ahora = datetime.now(timezone.utc)
    estados = {}

    for fuente in FUENTES:
        if fuente.requiere_clave and not fuente.clave_configurada():
            estados[fuente.id] = {
                "estado": "gris",
                "etiqueta": fuente.etiqueta,
                "detalle": "sin API key",
            }
            continue

        ultima = storage.ultimo_valor(fuente.id, lugar_id, fuente.metrica)
        if ultima is None:
            estado, detalle = "rojo", "sin datos"
        else:
            edad_min = (ahora - ultima.ts).total_seconds() / 60
            if edad_min < fuente.frescura_ok_min:
                estado = "verde"
            elif edad_min < fuente.frescura_alerta_min:
                estado = "amarillo"
            else:
                estado = "rojo"
            detalle = ultima.antiguedad_texto()

        estados[fuente.id] = {
            "estado": estado,
            "etiqueta": fuente.etiqueta,
            "detalle": detalle,
        }

    return estados


@app.get("/api/incendios")
def obtener_incendios(
    lugar_id: str = DEFAULT_LUGAR,
    dias: int = Query(default=2, ge=1, le=10),
    nacional: bool = False,
):
    """
    Focos de calor para el mapa (Fase 3).

    A diferencia del resto de endpoints, este consulta FIRMS en vivo: el mapa
    necesita las coordenadas de cada foco, y `storage` solo guarda el conteo.

    Nunca devuelve error al frontend: si falta la clave o FIRMS está caído,
    responde con `disponible: false` y el motivo, para que el mapa muestre un
    mensaje claro en vez de romperse.
    """
    # Vista nacional: cubre todo el país (como IDEAM). Si no, el bbox de la ciudad.
    if nacional:
        lugar = COLOMBIA.copy()
        lugar["_id"] = "colombia"
    else:
        _validar_lugar(lugar_id)
        lugar = LUGARES[lugar_id].copy()
        lugar["_id"] = lugar_id

    try:
        focos = firms.obtener_focos(lugar, dias=dias)
    except firms.FirmsSinClave as exc:
        return {
            "disponible": False,
            "motivo": "sin_clave",
            "mensaje": str(exc),
            "focos": [],
            "centro": {"lat": lugar["lat"], "lon": lugar["lon"]},
        }
    except firms.FirmsSinDatos as exc:
        return {
            "disponible": False,
            "motivo": "fuente_caida",
            "mensaje": str(exc),
            "focos": [],
            "centro": {"lat": lugar["lat"], "lon": lugar["lon"]},
        }

    return {
        "disponible": True,
        "motivo": None,
        "mensaje": None,
        "centro": {"lat": lugar["lat"], "lon": lugar["lon"]},
        "bbox": lugar["bbox"],
        "dias": dias,
        "focos": [
            {
                "lat": f.lat,
                "lon": f.lon,
                "frp": f.frp,
                "confianza": f.confianza,
                "ts": f.ts.isoformat(),
                "satelite": f.satelite,
                "dia_noche": f.dia_noche,
                "distancia_km": f.distancia_km,
            }
            for f in focos
        ],
    }


# ── Fase 4: predictor de riesgo ──────────────────────────────────────────────

@app.get("/api/riesgo")
def obtener_riesgo(lugar_id: str = DEFAULT_LUGAR):
    """
    Estimación experimental de riesgo de calor extremo.

    El modelo se entrena al vuelo con el historial guardado. Con ~700 muestras
    tarda menos de un segundo, así que no vale la pena persistirlo todavía.

    Nunca devuelve 500: si falta historial responde `disponible: false` con
    instrucciones, igual que el endpoint de incendios.
    """
    _validar_lugar(lugar_id)

    try:
        prediccion, metricas = risk.evaluar_riesgo(lugar_id)
    except risk.DatosInsuficientes as exc:
        return {
            "disponible": False,
            "motivo": getattr(exc, "motivo", "sin_historial"),
            "mensaje": str(exc),
            "etiqueta": "⚠️ Estimación experimental — no es una alerta oficial",
        }

    return {
        "disponible": True,
        "etiqueta": prediccion.etiqueta,
        "probabilidad": prediccion.probabilidad,
        "nivel": prediccion.nivel,
        "mensaje": prediccion.mensaje,
        "fecha_objetivo": prediccion.fecha_objetivo.date().isoformat(),
        "ic_max_hoy": prediccion.ic_max_hoy,
        "umbral_ic": prediccion.umbral_ic,
        "modelo": {
            "es_util": metricas.es_util,
            "exactitud": metricas.exactitud,
            "precision": metricas.precision,
            "recall": metricas.recall,
            "f1": metricas.f1,
            "tasa_base": metricas.tasa_base,
            "mejora_sobre_base": metricas.mejora_sobre_base,
            "n_entrenamiento": metricas.n_entrenamiento,
            "n_prueba": metricas.n_prueba,
            "importancias": metricas.importancias,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
