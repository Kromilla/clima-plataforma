"""
huella.py — Calculadora de huella de carbono (Módulo paralelo A).

Estima toneladas de CO₂ equivalente al año a partir de transporte, energía del
hogar, dieta y residuos.

FACTORES DE EMISIÓN
Cada factor lleva su fuente citada en el propio código, como pide el informe.
Fuentes usadas:
  - EPA: "Emission Factors for Greenhouse Gas Inventories" (2024)
    https://www.epa.gov/climateleadership/ghg-emission-factors-hub
  - DEFRA/BEIS: "UK Government GHG Conversion Factors for Company Reporting" (2024)
    https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting
  - IPCC AR6 (2021) para potenciales de calentamiento global
  - XM: factor de emisión de la red eléctrica colombiana (dato real del proyecto)
  - Poore & Nemecek (2018), Science 360(6392) — huella de alimentos

LIMITACIONES (importantes al presentar el resultado)
Es una estimación educativa basada en promedios. No sustituye un inventario de
huella profesional: no cubre bienes de consumo, servicios, construcción de
vivienda ni infraestructura pública, que en países de renta alta pueden ser un
tercio del total.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── Transporte ────────────────────────────────────────────────────────────────
# kg CO₂e por kilómetro recorrido.
# Fuente: DEFRA 2024, "Business travel - land" y "Business travel - air".
# Los valores de auto son por vehículo (no por pasajero); los de transporte
# público ya vienen por pasajero.
FACTOR_TRANSPORTE_KM = {
    "auto_gasolina": 0.170,      # DEFRA 2024, average petrol car
    "auto_diesel": 0.171,        # DEFRA 2024, average diesel car
    "auto_hibrido": 0.120,       # DEFRA 2024, average hybrid car
    "auto_electrico": 0.048,     # DEFRA 2024, average battery EV (red UK)
    "moto": 0.114,               # DEFRA 2024, average motorbike
    "bus": 0.097,                # DEFRA 2024, average local bus, por pasajero
    "metro_tren": 0.035,         # DEFRA 2024, national rail, por pasajero
    "bicicleta_caminar": 0.0,
}

# kg CO₂e por hora de vuelo, por pasajero, en clase económica.
# Fuente: DEFRA 2024, promedio de vuelos de corta y larga distancia,
# SIN el multiplicador de forzamiento radiativo (radiative forcing).
FACTOR_VUELO_HORA = 90.0

# ── Energía del hogar ─────────────────────────────────────────────────────────
# kg CO₂e por kWh de electricidad.
# Para Colombia usamos el dato REAL de XM en vez de un promedio internacional:
# la red colombiana es mayoritariamente hidráulica, así que un factor genérico
# (~0.4) sobreestimaría la huella por un factor de ~2.
FACTOR_ELECTRICIDAD_KWH_CO = 0.190   # gCO₂e/kWh de XM ≈ 190 → 0.190 kg/kWh
FACTOR_ELECTRICIDAD_KWH_GLOBAL = 0.475  # IEA 2023, promedio mundial

# kg CO₂e por m³ de gas natural. Fuente: EPA 2024, natural gas (combustión).
FACTOR_GAS_M3 = 1.885
# kg CO₂e por kg de GLP (gas propano en cilindro, común en Colombia).
# Fuente: EPA 2024, propane.
FACTOR_GLP_KG = 2.983

# ── Dieta ─────────────────────────────────────────────────────────────────────
# Toneladas CO₂e al año por tipo de dieta, para una persona.
# Fuente: Poore & Nemecek (2018) Science, adaptado por Scarborough et al. (2023)
# Nature Food — huella dietaria en el Reino Unido.
FACTOR_DIETA_ANUAL_T = {
    "carne_alta": 2.62,      # >100 g de carne al día
    "carne_media": 1.94,     # 50-99 g al día
    "carne_baja": 1.62,      # <50 g al día
    "pescetariano": 1.39,
    "vegetariano": 1.16,
    "vegano": 0.91,
}

# ── Residuos ──────────────────────────────────────────────────────────────────
# kg CO₂e por kg de residuo. Fuente: EPA WARM v15.
# El relleno sanitario emite metano; reciclar evita emisiones de producción.
FACTOR_RESIDUO_KG = 0.58
# Factor de reducción por reciclar: proporción de la huella que se evita.
REDUCCION_POR_RECICLAJE = 0.30

# Promedios de referencia, en toneladas de CO₂e por persona al año.
# Fuente: Our World in Data / Global Carbon Budget 2023 (emisiones territoriales).
PROMEDIO_COLOMBIA_T = 1.9
PROMEDIO_MUNDIAL_T = 4.7
# Objetivo del Acuerdo de París para 2030: ~2.3 t per cápita.
OBJETIVO_PARIS_2030_T = 2.3

TipoVehiculo = Literal[
    "auto_gasolina", "auto_diesel", "auto_hibrido", "auto_electrico",
    "moto", "bus", "metro_tren", "bicicleta_caminar",
]
TipoDieta = Literal[
    "carne_alta", "carne_media", "carne_baja",
    "pescetariano", "vegetariano", "vegano",
]


@dataclass
class Respuestas:
    """Lo que responde el usuario en el formulario."""

    # Transporte
    transporte: TipoVehiculo = "auto_gasolina"
    km_semana: float = 0.0
    pasajeros_auto: int = 1       # compartir auto divide la huella
    horas_vuelo_anio: float = 0.0

    # Hogar
    kwh_mes: float = 0.0
    personas_hogar: int = 1       # la energía del hogar se reparte
    gas_m3_mes: float = 0.0
    glp_kg_mes: float = 0.0
    usa_factor_colombia: bool = True

    # Dieta y residuos
    dieta: TipoDieta = "carne_media"
    residuos_kg_semana: float = 0.0
    recicla: bool = False


@dataclass
class Resultado:
    """Desglose de la huella anual, en toneladas de CO₂e."""

    transporte_t: float
    vuelos_t: float
    hogar_t: float
    dieta_t: float
    residuos_t: float
    detalles: list[str] = field(default_factory=list)

    @property
    def total_t(self) -> float:
        return round(
            self.transporte_t + self.vuelos_t + self.hogar_t
            + self.dieta_t + self.residuos_t,
            2,
        )

    @property
    def desglose(self) -> dict[str, float]:
        return {
            "Transporte": round(self.transporte_t, 2),
            "Vuelos": round(self.vuelos_t, 2),
            "Hogar": round(self.hogar_t, 2),
            "Dieta": round(self.dieta_t, 2),
            "Residuos": round(self.residuos_t, 2),
        }

    @property
    def vs_colombia(self) -> float:
        """Cuántas veces el promedio colombiano."""
        return round(self.total_t / PROMEDIO_COLOMBIA_T, 2)

    @property
    def vs_mundial(self) -> float:
        return round(self.total_t / PROMEDIO_MUNDIAL_T, 2)

    @property
    def cumple_paris(self) -> bool:
        return self.total_t <= OBJETIVO_PARIS_2030_T


def _validar(r: Respuestas) -> None:
    """Rechaza entradas imposibles antes de calcular."""
    if r.km_semana < 0 or r.horas_vuelo_anio < 0:
        raise ValueError("Las distancias no pueden ser negativas")
    if r.kwh_mes < 0 or r.gas_m3_mes < 0 or r.glp_kg_mes < 0:
        raise ValueError("El consumo de energía no puede ser negativo")
    if r.residuos_kg_semana < 0:
        raise ValueError("Los residuos no pueden ser negativos")
    if r.pasajeros_auto < 1:
        raise ValueError("Debe haber al menos 1 ocupante en el vehículo")
    if r.personas_hogar < 1:
        raise ValueError("Debe haber al menos 1 persona en el hogar")
    if r.transporte not in FACTOR_TRANSPORTE_KM:
        raise ValueError(f"Transporte desconocido: {r.transporte}")
    if r.dieta not in FACTOR_DIETA_ANUAL_T:
        raise ValueError(f"Dieta desconocida: {r.dieta}")


def calcular(r: Respuestas) -> Resultado:
    """
    Calcula la huella anual a partir de las respuestas.

    Raises:
        ValueError: si alguna entrada es inválida.
    """
    _validar(r)
    detalles: list[str] = []

    # ── Transporte terrestre ──────────────────────────────────────────────
    factor = FACTOR_TRANSPORTE_KM[r.transporte]
    km_anio = r.km_semana * 52
    # Solo el auto se comparte entre ocupantes: los factores de bus y tren ya
    # están expresados por pasajero.
    divisor = r.pasajeros_auto if r.transporte.startswith("auto") else 1
    transporte_t = (km_anio * factor / divisor) / 1000

    if divisor > 1:
        detalles.append(
            f"Compartir el auto entre {divisor} personas divide su huella por {divisor}."
        )
    if r.transporte == "auto_electrico":
        detalles.append(
            "El factor del auto eléctrico usa la red del Reino Unido. Con la red "
            "colombiana (más hidráulica) la huella real sería aún menor."
        )

    # ── Vuelos ────────────────────────────────────────────────────────────
    vuelos_t = (r.horas_vuelo_anio * FACTOR_VUELO_HORA) / 1000
    if r.horas_vuelo_anio > 0:
        detalles.append(
            "Los vuelos no incluyen el forzamiento radiativo: el impacto climático "
            "real de volar puede ser hasta el doble del CO₂ contabilizado."
        )

    # ── Hogar ─────────────────────────────────────────────────────────────
    factor_elec = (
        FACTOR_ELECTRICIDAD_KWH_CO if r.usa_factor_colombia
        else FACTOR_ELECTRICIDAD_KWH_GLOBAL
    )
    kg_elec = r.kwh_mes * 12 * factor_elec
    kg_gas = r.gas_m3_mes * 12 * FACTOR_GAS_M3
    kg_glp = r.glp_kg_mes * 12 * FACTOR_GLP_KG
    hogar_t = ((kg_elec + kg_gas + kg_glp) / r.personas_hogar) / 1000

    if r.usa_factor_colombia:
        detalles.append(
            "La electricidad usa el factor real de la red colombiana (~190 gCO₂e/kWh, "
            "dato de XM), mucho más limpia que el promedio mundial por ser "
            "mayoritariamente hidráulica."
        )
    if r.personas_hogar > 1:
        detalles.append(
            f"La energía del hogar se reparte entre {r.personas_hogar} personas."
        )

    # ── Dieta ─────────────────────────────────────────────────────────────
    dieta_t = FACTOR_DIETA_ANUAL_T[r.dieta]

    # ── Residuos ──────────────────────────────────────────────────────────
    kg_residuos = r.residuos_kg_semana * 52 * FACTOR_RESIDUO_KG
    if r.recicla:
        kg_residuos *= 1 - REDUCCION_POR_RECICLAJE
        detalles.append(
            f"Reciclar reduce la huella de residuos en {REDUCCION_POR_RECICLAJE:.0%}."
        )
    residuos_t = kg_residuos / 1000

    return Resultado(
        transporte_t=transporte_t,
        vuelos_t=vuelos_t,
        hogar_t=hogar_t,
        dieta_t=dieta_t,
        residuos_t=residuos_t,
        detalles=detalles,
    )


def recomendaciones(r: Respuestas, res: Resultado) -> list[str]:
    """
    Sugerencias ordenadas por impacto real, calculadas sobre las respuestas del
    usuario — no una lista genérica.
    """
    sugerencias: list[tuple[float, str]] = []

    # Transporte: ¿cuánto ahorraría cambiando de modo?
    if r.transporte in ("auto_gasolina", "auto_diesel") and r.km_semana > 0:
        actual = res.transporte_t
        km_anio = r.km_semana * 52
        con_bus = (km_anio * FACTOR_TRANSPORTE_KM["bus"]) / 1000
        ahorro = actual - con_bus
        if ahorro > 0.05:
            sugerencias.append((
                ahorro,
                f"Cambiar el auto por transporte público te ahorraría "
                f"~{ahorro:.2f} t CO₂e al año.",
            ))
        if r.pasajeros_auto == 1:
            ahorro_compartir = actual / 2
            sugerencias.append((
                ahorro_compartir,
                f"Compartir el auto con una persona más ahorraría "
                f"~{ahorro_compartir:.2f} t CO₂e al año.",
            ))

    # Dieta: ¿cuánto ahorraría bajando un escalón?
    escalera = ["carne_alta", "carne_media", "carne_baja", "pescetariano",
                "vegetariano", "vegano"]
    if r.dieta in escalera:
        i = escalera.index(r.dieta)
        if i < len(escalera) - 1:
            siguiente = escalera[i + 1]
            ahorro = FACTOR_DIETA_ANUAL_T[r.dieta] - FACTOR_DIETA_ANUAL_T[siguiente]
            if ahorro > 0.05:
                sugerencias.append((
                    ahorro,
                    f"Pasar a una dieta '{siguiente.replace('_', ' ')}' ahorraría "
                    f"~{ahorro:.2f} t CO₂e al año.",
                ))

    # Vuelos: suelen ser el rubro más concentrado.
    if r.horas_vuelo_anio >= 4:
        ahorro = (4 * FACTOR_VUELO_HORA) / 1000
        sugerencias.append((
            ahorro,
            f"Un vuelo largo menos al año ahorraría ~{ahorro:.2f} t CO₂e.",
        ))

    # Reciclaje: solo si aún no recicla.
    if not r.recicla and r.residuos_kg_semana > 0:
        ahorro = res.residuos_t * REDUCCION_POR_RECICLAJE / (1 - 0)
        if ahorro > 0.01:
            sugerencias.append((
                ahorro,
                f"Empezar a reciclar ahorraría ~{ahorro:.2f} t CO₂e al año.",
            ))

    sugerencias.sort(key=lambda s: s[0], reverse=True)
    return [texto for _, texto in sugerencias[:4]]
