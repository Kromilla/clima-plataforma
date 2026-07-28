"""
quiz.py — Quiz educativo sobre clima y calidad del aire (Módulo paralelo B).

12 preguntas con dato curioso en cada respuesta. Varias están ancladas a
Santa Marta y Colombia para que sea relevante a quien usa el dashboard.

Cada pregunta cita su fuente: si un dato cambia (o resulta estar mal), se sabe
de dónde salió. Las respuestas correctas no se envían al frontend hasta que el
usuario responde — se corrigen en el backend.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pregunta:
    id: int
    texto: str
    opciones: tuple[str, ...]
    correcta: int          # índice en `opciones`
    explicacion: str
    fuente: str
    categoria: str


PREGUNTAS: tuple[Pregunta, ...] = (
    Pregunta(
        id=1,
        texto="¿Qué es exactamente el PM2.5 que mide este dashboard?",
        opciones=(
            "Un gas de efecto invernadero",
            "Partículas de menos de 2.5 micras de diámetro",
            "La cantidad de polen en el aire",
            "Un índice de temperatura y humedad",
        ),
        correcta=1,
        explicacion=(
            "Son partículas 30 veces más finas que un cabello humano. Su tamaño es "
            "justo el problema: son tan pequeñas que atraviesan los pulmones y "
            "llegan al torrente sanguíneo."
        ),
        fuente="OMS, Guías de calidad del aire (2021)",
        categoria="Calidad del aire",
    ),
    Pregunta(
        id=2,
        texto="Según la OMS, ¿cuál es el límite anual recomendado de PM2.5?",
        opciones=("5 µg/m³", "25 µg/m³", "50 µg/m³", "100 µg/m³"),
        correcta=0,
        explicacion=(
            "La OMS bajó el límite de 10 a 5 µg/m³ en 2021 al confirmar que había "
            "daños a la salud por debajo del umbral anterior. Casi ninguna ciudad "
            "grande del mundo lo cumple."
        ),
        fuente="OMS, Guías de calidad del aire (2021)",
        categoria="Calidad del aire",
    ),
    Pregunta(
        id=3,
        texto="¿Cuántas muertes prematuras al año se atribuyen a la contaminación del aire?",
        opciones=("cerca de 100 mil", "cerca de 700 mil", "cerca de 7 millones", "cerca de 50 millones"),
        correcta=2,
        explicacion=(
            "Unos 7 millones de personas al año, sumando aire exterior e interior. "
            "Es una de las principales causas de muerte evitable en el mundo."
        ),
        fuente="OMS (2024)",
        categoria="Salud",
    ),
    Pregunta(
        id=4,
        texto="La red eléctrica de Colombia es de las más limpias del continente. ¿Por qué?",
        opciones=(
            "Porque la mayor parte es energía nuclear",
            "Porque la mayor parte es hidroeléctrica",
            "Porque importa electricidad de Brasil",
            "Porque casi todo es solar",
        ),
        correcta=1,
        explicacion=(
            "Cerca del 70% de la generación colombiana es hidroeléctrica. Por eso la "
            "intensidad de carbono que ves en la pestaña de Energía suele rondar "
            "150-250 gCO₂e/kWh, frente a más de 400 del promedio mundial."
        ),
        fuente="XM, operador del mercado eléctrico colombiano",
        categoria="Energía",
    ),
    Pregunta(
        id=5,
        texto="En Colombia, ¿en qué momento del día suele ser MÁS sucia la electricidad?",
        opciones=(
            "De madrugada, entre 1 y 5 a.m.",
            "A media mañana",
            "En la noche, entre 7 y 10 p.m.",
            "Es igual todo el día",
        ),
        correcta=2,
        explicacion=(
            "En el pico de demanda nocturna entran a operar plantas térmicas (gas y "
            "carbón) para complementar la hidroeléctrica. Mover consumos grandes "
            "fuera de ese pico reduce emisiones."
        ),
        fuente="XM, métrica factorEmisionCO2e por hora",
        categoria="Energía",
    ),
    Pregunta(
        id=6,
        texto="¿Qué mide la 'potencia radiativa' (FRP) de un foco de calor satelital?",
        opciones=(
            "Cuántas hectáreas se han quemado",
            "La intensidad de la energía que libera el fuego",
            "La velocidad a la que avanza el fuego",
            "Cuánto humo produce",
        ),
        correcta=1,
        explicacion=(
            "El FRP se mide en megavatios y estima la energía liberada. No dice "
            "cuánta superficie arde: un foco muy intenso puede ser pequeño."
        ),
        fuente="NASA FIRMS / documentación VIIRS",
        categoria="Incendios",
    ),
    Pregunta(
        id=7,
        texto="Un satélite detecta un 'foco de calor'. ¿Significa que hay un incendio?",
        opciones=(
            "Sí, siempre",
            "No: puede ser una quema agrícola o una fuente industrial",
            "Solo si es de noche",
            "Solo en época seca",
        ),
        correcta=1,
        explicacion=(
            "Es una anomalía térmica, no un incendio confirmado. Puede ser una quema "
            "controlada, una fogata grande, una refinería o una llamarada de gas. Por "
            "eso el mapa de este dashboard lo advierte explícitamente."
        ),
        fuente="NASA FIRMS, FAQ",
        categoria="Incendios",
    ),
    Pregunta(
        id=8,
        texto="Santa Marta está junto a la Sierra Nevada. ¿Qué la hace excepcional?",
        opciones=(
            "Es la montaña más alta del mundo",
            "Es la montaña costera más alta del mundo",
            "Es un volcán activo",
            "Es la montaña más antigua del planeta",
        ),
        correcta=1,
        explicacion=(
            "Pasa de 0 a 5.700 m en apenas 42 km desde el mar. Esa compresión de "
            "pisos térmicos concentra casi todos los ecosistemas de Colombia en un "
            "espacio diminuto, y la vuelve muy sensible al cambio climático."
        ),
        fuente="UNESCO, Reserva de Biosfera Sierra Nevada de Santa Marta",
        categoria="Santa Marta",
    ),
    Pregunta(
        id=9,
        texto="¿Qué actividad genera más emisiones a lo largo de un año típico?",
        opciones=(
            "Dejar el cargador del celular enchufado todo el año",
            "Un vuelo transatlántico de ida y vuelta",
            "Usar bolsas plásticas durante un año",
            "Ver televisión 4 horas diarias todo el año",
        ),
        correcta=1,
        explicacion=(
            "Un vuelo transatlántico ida y vuelta ronda 1 t CO₂e: más que el promedio "
            "anual de muchas personas. El cargador enchufado aporta unos pocos kg. "
            "Los gestos pequeños importan, pero no todos pesan igual."
        ),
        fuente="DEFRA 2024, factores de conversión",
        categoria="Huella personal",
    ),
    Pregunta(
        id=10,
        texto="¿Cuál de estos cambios de dieta reduce más la huella de carbono?",
        opciones=(
            "Comprar solo productos locales",
            "Pasar de mucha carne a poca carne",
            "Evitar alimentos empacados",
            "Comer solo productos de temporada",
        ),
        correcta=1,
        explicacion=(
            "El tipo de alimento pesa mucho más que su origen: el transporte suele "
            "ser menos del 10% de la huella alimentaria. Reducir carne roja cambia "
            "más que comprar local."
        ),
        fuente="Poore & Nemecek (2018), Science",
        categoria="Huella personal",
    ),
    Pregunta(
        id=11,
        texto="¿Por qué la brisa marina mejora la calidad del aire en ciudades costeras?",
        opciones=(
            "Porque el agua de mar absorbe los contaminantes",
            "Porque renueva el aire y dispersa los contaminantes",
            "Porque baja la temperatura y eso elimina el PM2.5",
            "Porque la sal neutraliza los gases",
        ),
        correcta=1,
        explicacion=(
            "La ventilación dispersa, no elimina. Cuando la brisa se detiene o hay "
            "inversión térmica, los contaminantes se acumulan — por eso una ciudad "
            "costera puede tener picos malos pese al mar."
        ),
        fuente="Principios de meteorología de capa límite",
        categoria="Santa Marta",
    ),
    Pregunta(
        id=12,
        texto="Este dashboard usa un modelo satelital para el PM2.5 de Santa Marta. ¿Por qué no una estación en tierra?",
        opciones=(
            "Porque los modelos son siempre más precisos",
            "Porque no hay estaciones de la red pública abierta en la ciudad",
            "Porque las estaciones cuestan dinero",
            "Porque el modelo actualiza más rápido",
        ),
        correcta=1,
        explicacion=(
            "Al validar el proyecto se comprobó que OpenAQ no tiene ninguna estación "
            "en Santa Marta, ni en Barranquilla, ni en toda la costa Caribe. Por eso "
            "se usa el modelo Copernicus CAMS, indicando siempre que es un modelo y "
            "no una medición en tierra."
        ),
        fuente="Validación del Día 1 de este proyecto (§8 del informe)",
        categoria="Sobre este proyecto",
    ),
)


@dataclass
class Resultado:
    puntaje: int
    total: int
    correctas: list[int]
    incorrectas: list[int]

    @property
    def porcentaje(self) -> float:
        return round(100 * self.puntaje / self.total, 1) if self.total else 0.0

    @property
    def nivel(self) -> str:
        p = self.porcentaje
        if p >= 90:
            return "🏆 Experto en clima"
        if p >= 70:
            return "🌟 Bien informado"
        if p >= 50:
            return "🌱 Vas por buen camino"
        return "📚 Hay mucho por descubrir"

    @property
    def mensaje(self) -> str:
        p = self.porcentaje
        if p >= 90:
            return "Dominas el tema. Comparte lo que sabes."
        if p >= 70:
            return "Buen conocimiento general, con algunos detalles por pulir."
        if p >= 50:
            return "Tienes las bases. Revisa las explicaciones de lo que fallaste."
        return "Justo para eso está el quiz: cada explicación enseña algo nuevo."


def preguntas_publicas() -> list[dict]:
    """
    Preguntas SIN la respuesta correcta, para enviar al frontend.
    La corrección ocurre en el backend: mandar `correcta` al cliente permitiría
    ver las respuestas en las herramientas de desarrollo.
    """
    return [
        {
            "id": p.id,
            "texto": p.texto,
            "opciones": list(p.opciones),
            "categoria": p.categoria,
        }
        for p in PREGUNTAS
    ]


def calificar(respuestas: dict[int, int]) -> Resultado:
    """
    Califica un intento.

    Args:
        respuestas: {id_pregunta: indice_elegido}. Las preguntas no respondidas
                    cuentan como incorrectas.
    """
    correctas: list[int] = []
    incorrectas: list[int] = []

    for p in PREGUNTAS:
        if respuestas.get(p.id) == p.correcta:
            correctas.append(p.id)
        else:
            incorrectas.append(p.id)

    return Resultado(
        puntaje=len(correctas),
        total=len(PREGUNTAS),
        correctas=correctas,
        incorrectas=incorrectas,
    )


def solucionario() -> list[dict]:
    """Respuestas y explicaciones — se entrega solo tras responder."""
    return [
        {
            "id": p.id,
            "correcta": p.correcta,
            "explicacion": p.explicacion,
            "fuente": p.fuente,
        }
        for p in PREGUNTAS
    ]


def texto_para_compartir(res: Resultado) -> str:
    """Texto corto para el botón de compartir."""
    bloques = "".join(
        "🟩" if p.id in res.correctas else "🟥" for p in PREGUNTAS
    )
    return (
        f"Quiz de Clima — Santa Marta\n"
        f"{res.puntaje}/{res.total} · {res.nivel}\n"
        f"{bloques}"
    )
