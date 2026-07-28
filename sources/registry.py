"""
sources/registry.py — Registro único de las fuentes activas.

Este es el ÚNICO lugar donde se declara una fuente. `collector.py`, `api.py` y el
dashboard leen de aquí, así que agregar una fuente nueva es:
    1. Crear `sources/mi_fuente.py` con `obtener_ultimo(lugar) -> Lectura`
    2. Añadir una entrada en FUENTES
…y nada más. Es la "prueba de escalabilidad" del informe (§7): sumar FIRMS en la
Fase 3 no debe obligar a tocar bot.py ni el dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sources import firms, openmeteo_aire, openmeteo_clima, xm
from sources.base import Lectura


@dataclass(frozen=True)
class FuenteRegistrada:
    """Metadatos de una fuente para que la UI no tenga que hardcodearlos."""

    id: str                       # coincide con Lectura.fuente
    etiqueta: str                 # nombre legible para la UI
    metrica: str                  # métrica que produce
    obtener: Callable[[dict], Lectura]
    # Minutos tras los cuales el semáforo pasa de 🟢 a 🟡.
    # XM publica con días de rezago: exigirle 2 h lo pintaría rojo para siempre.
    frescura_ok_min: int = 120
    frescura_alerta_min: int = 720
    # True si la fuente necesita una API key que puede no estar configurada.
    # El recolector no la reporta como fallo cuando falta la clave.
    requiere_clave: bool = False

    def clave_configurada(self) -> bool:
        """Si la fuente pide clave, indica si está presente en el entorno."""
        if not self.requiere_clave:
            return True
        from config import cfg  # import diferido: evita ciclo con config
        return bool(getattr(cfg, _CLAVE_POR_FUENTE.get(self.id, ""), None))


# Qué variable de config mira cada fuente que requiere clave.
_CLAVE_POR_FUENTE = {
    "firms": "FIRMS_MAP_KEY",
}


FUENTES: tuple[FuenteRegistrada, ...] = (
    FuenteRegistrada(
        id="openmeteo-aire",
        etiqueta="Aire (CAMS)",
        metrica="pm25",
        obtener=openmeteo_aire.obtener_ultimo,
    ),
    FuenteRegistrada(
        id="openmeteo-clima",
        etiqueta="Clima",
        metrica="temperatura",
        obtener=openmeteo_clima.obtener_ultimo,
    ),
    FuenteRegistrada(
        id="xm",
        etiqueta="Energía (XM)",
        metrica="intensidad_co2",
        obtener=xm.obtener_ultimo,
        # XM publica con ~2-3 días de rezago; esto es normal, no una falla.
        frescura_ok_min=4 * 24 * 60,
        frescura_alerta_min=8 * 24 * 60,
    ),
    FuenteRegistrada(
        id="firms",
        etiqueta="Incendios (FIRMS)",
        metrica="focos_activos",
        obtener=firms.obtener_ultimo,
        # Los satélites VIIRS pasan ~2 veces al día; 12 h es una espera normal.
        frescura_ok_min=12 * 60,
        frescura_alerta_min=36 * 60,
        requiere_clave=True,
    ),
)


def por_id(fuente_id: str) -> FuenteRegistrada | None:
    """Busca una fuente registrada por su id."""
    return next((f for f in FUENTES if f.id == fuente_id), None)
