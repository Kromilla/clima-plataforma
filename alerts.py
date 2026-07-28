"""
alerts.py — Motor de alertas simple.

Principio del informe v3: hoy hay una sola regla (umbral PM2.5).
Se generaliza cuando exista una tercera regla real, no antes.
"""
from __future__ import annotations

from sources.base import Lectura


# Escala de calidad del aire (basada en ICA Colombia / WHO 2021)
_NIVELES_PM25 = [
    (0,   12,   "🟢 Buena",       "El aire está limpio. Actividad normal sin restricciones."),
    (12,  35.4, "🟡 Moderada",    "Aceptable. Personas muy sensibles pueden notar efectos."),
    (35.4, 55.4, "🟠 Dañina para grupos sensibles", "Niños, adultos mayores y personas con enf. respiratorias deben reducir esfuerzo prolongado."),
    (55.4, 150.4, "🔴 Dañina",    "Toda la población puede empezar a notar efectos. Reducir actividad al aire libre."),
    (150.4, 250.4, "🟣 Muy dañina", "Alerta de salud. Evitar actividad intensa al aire libre."),
    (250.4, float("inf"), "⚫ Peligrosa", "Emergencia sanitaria. Permanecer en interiores."),
]


def nivel_pm25(valor: float) -> tuple[str, str]:
    """Devuelve (etiqueta, recomendación) para un valor de PM2.5."""
    for lo, hi, etiqueta, recomendacion in _NIVELES_PM25:
        if lo <= valor < hi:
            return etiqueta, recomendacion
    return "⚫ Peligrosa", "Emergencia sanitaria. Permanecer en interiores."


def revisar_alerta(valor: float, umbral: float) -> str | None:
    """
    Evalúa si el valor supera el umbral.

    Args:
        valor:   Concentración de PM2.5 en µg/m³
        umbral:  Valor configurado por el usuario (default 50 µg/m³)

    Returns:
        Mensaje de alerta listo para enviar por Telegram, o None si no hay alerta.
    """
    if valor < umbral:
        return None

    etiqueta, recomendacion = nivel_pm25(valor)
    return (
        f"⚠️ *ALERTA DE CALIDAD DEL AIRE*\n\n"
        f"PM2.5 actual: *{valor:.1f} µg/m³*\n"
        f"Tu umbral configurado: {umbral:.1f} µg/m³\n"
        f"Calidad: {etiqueta}\n\n"
        f"💡 {recomendacion}"
    )


# Distancia por defecto para avisar de un foco de calor.
UMBRAL_FOCO_KM = 20.0


def revisar_alerta_incendio(focos: list, umbral_km: float = UMBRAL_FOCO_KM) -> str | None:
    """
    Segunda regla de alerta: foco de calor cerca del lugar.

    Sigue siendo un `if`, no un motor de reglas: el informe (§4) dice generalizar
    cuando exista una tercera regla real, no antes.

    Args:
        focos: lista de sources.firms.Foco, ordenada por cercanía
        umbral_km: distancia a partir de la cual se avisa

    Returns:
        Mensaje listo para Telegram, o None si no hay foco significativo cerca.
    """
    cercanos = [
        f for f in focos
        if f.distancia_km <= umbral_km and f.es_significativo
    ]
    if not cercanos:
        return None

    mas_cerca = cercanos[0]
    intensidad = max(f.frp for f in cercanos)

    lineas = [
        "🔥 *ALERTA DE FOCO DE CALOR*\n",
        f"Detectados *{len(cercanos)}* focos a menos de {umbral_km:.0f} km.",
        f"El más cercano está a *{mas_cerca.distancia_km:.1f} km*.",
        f"Intensidad máxima: {intensidad:.1f} MW",
        "",
        "💡 Puede afectar la calidad del aire. Si ves humo, cierra ventanas y "
        "evita actividad intensa al aire libre.",
        "",
        "_Detección satelital (NASA FIRMS) — no confirma un incendio en tierra._",
    ]
    return "\n".join(lineas)


def formato_estado(lectura: Lectura, umbral: float) -> str:
    """
    Genera el texto del comando /estado para mostrar al usuario.
    Incluye valor actual, procedencia, antigüedad y nivel de calidad.
    """
    etiqueta, recomendacion = nivel_pm25(lectura.valor)
    alerta_activa = lectura.valor >= umbral

    lineas = [
        f"🌍 *Estado del Aire — {lectura.lugar_id.replace('-', ' ').title()}*\n",
        f"PM2.5: *{lectura.valor:.1f} µg/m³*",
        f"Calidad: {etiqueta}",
        f"Fuente: {lectura.etiqueta_procedencia()}",
        "",
        f"💡 {recomendacion}",
        "",
        f"Tu umbral: {umbral:.1f} µg/m³ "
        f"{'🔔 ACTIVO' if alerta_activa else '✅ OK'}",
    ]
    return "\n".join(lineas)
