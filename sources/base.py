"""
sources/base.py — Contrato común para todos los adaptadores de fuentes de datos.

Regla: cada fuente (openaq, openmeteo, firms…) devuelve un objeto `Lectura`.
La capa superior (bot.py, dashboard.py) nunca sabe de dónde vino el dato —
solo lee los campos de `Lectura`.

Procedencias posibles:
    "local"    — estación dentro del bbox del lugar pedido
    "fallback" — estación alternativa (ej. Barranquilla para Santa Marta)
    "cache"    — último valor guardado en SQLite (la API estaba caída)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@dataclass
class Lectura:
    """Resultado normalizado de cualquier fuente de datos."""

    # ── Dato en sí ──────────────────────────────────────────────────────────
    valor: float
    unidad: str                          # "µg/m³", "°C", "gCO₂eq/kWh", …
    metrica: str                         # "pm25", "temperatura", "intensidad_co2", …
    fuente: str                          # "openaq", "openmeteo", "electricity_maps", …

    # ── Trazabilidad ────────────────────────────────────────────────────────
    procedencia: str                     # "local" | "fallback" | "cache"
    lugar_id: str                        # clave en LUGARES, ej. "santa-marta"
    estacion_nombre: str = ""            # nombre de la estación o zona, si aplica

    # ── Temporal ────────────────────────────────────────────────────────────
    ts: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def antiguedad_min(self) -> int:
        """Minutos desde que se generó este dato."""
        delta = datetime.now(timezone.utc) - self.ts
        return int(delta.total_seconds() / 60)

    def antiguedad_texto(self) -> str:
        """Antigüedad en la unidad más legible: min, horas o días."""
        mins = self.antiguedad_min
        if mins < 90:
            return f"hace {mins} min"
        if mins < 48 * 60:
            return f"hace {mins // 60} h"
        return f"hace {mins // 1440} días"

    def es_reciente(self, umbral_min: int = 120) -> bool:
        """True si el dato es lo bastante fresco como para no advertir al usuario."""
        return self.antiguedad_min < umbral_min

    def etiqueta_procedencia(self) -> str:
        """
        Texto legible para mostrar al usuario.

        La antigüedad se muestra siempre que el dato no sea reciente, sin importar
        la procedencia: una fuente como XM publica con días de rezago aunque el
        dato venga "en vivo" de su API. Ocultar eso sería fingir una precisión que
        el dato no tiene.
        """
        if self.procedencia == "cache":
            return f"🗄️ Último dato conocido ({self.antiguedad_texto()})"

        if self.procedencia == "local":
            base = f"📍 Estación local ({self.estacion_nombre or self.lugar_id})"
        elif self.procedencia == "fallback":
            base = f"📡 Estación alternativa ({self.estacion_nombre or 'fallback'})"
        else:
            return self.procedencia

        if not self.es_reciente():
            return f"{base} — ⚠️ dato de {self.antiguedad_texto()}"
        return base

    def __str__(self) -> str:
        return (
            f"{self.metrica}: {self.valor} {self.unidad} "
            f"[{self.etiqueta_procedencia()}]"
        )


@runtime_checkable
class FuenteDatos(Protocol):
    """Protocolo que debe cumplir cualquier adaptador de fuente."""

    def obtener_ultimo(self, lugar: dict) -> Lectura:
        """
        Retorna la lectura más reciente para el lugar dado.

        Args:
            lugar: Diccionario de un lugar de locations.py
                   (tiene 'lat', 'lon', 'bbox', 'zona_electricidad', etc.)

        Returns:
            Lectura — nunca lanza excepción al caller; usa caché si la API falla.
        """
        ...
