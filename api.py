"""
api.py — API REST con FastAPI para proveer datos al frontend React.

Las fuentes no se listan aquí: se leen de `sources/registry.py`, así que agregar
una fuente nueva no requiere tocar este archivo (principio §5.1 del informe).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import storage
from locations import DEFAULT_LUGAR, LUGARES
from sources.base import Lectura
from sources.registry import FUENTES, por_id

app = FastAPI(title="ClimaBot API")

# Habilitar CORS para desarrollo con Vite (React)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En produccion restringir a los dominios correctos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage.inicializar_bd()


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
    limite: int = 24,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
