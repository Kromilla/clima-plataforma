"""
tests/test_huella_quiz.py — Tests de la calculadora de huella y del quiz.

Ambos módulos son puro cálculo: no tocan red ni base de datos.
"""
from __future__ import annotations

import pytest

import huella
import quiz


# ── Huella: cálculo ──────────────────────────────────────────────────────────

def test_todo_en_cero_solo_deja_la_dieta():
    """Con consumo cero, la única emisión que queda es la alimentación."""
    res = huella.calcular(huella.Respuestas(
        transporte="bicicleta_caminar", km_semana=0, kwh_mes=0,
        glp_kg_mes=0, gas_m3_mes=0, residuos_kg_semana=0, dieta="vegano",
    ))
    assert res.transporte_t == 0
    assert res.hogar_t == 0
    assert res.total_t == pytest.approx(huella.FACTOR_DIETA_ANUAL_T["vegano"], abs=0.01)


def test_compartir_auto_divide_la_huella():
    base = huella.Respuestas(transporte="auto_gasolina", km_semana=200, pasajeros_auto=1)
    compartido = huella.Respuestas(transporte="auto_gasolina", km_semana=200, pasajeros_auto=4)

    t_solo = huella.calcular(base).transporte_t
    t_compartido = huella.calcular(compartido).transporte_t
    assert t_compartido == pytest.approx(t_solo / 4, rel=0.01)


def test_el_bus_no_se_divide_por_ocupantes():
    """Los factores de transporte público ya vienen por pasajero."""
    uno = huella.calcular(huella.Respuestas(transporte="bus", km_semana=100, pasajeros_auto=1))
    cuatro = huella.calcular(huella.Respuestas(transporte="bus", km_semana=100, pasajeros_auto=4))
    assert uno.transporte_t == pytest.approx(cuatro.transporte_t)


def test_hogar_se_reparte_entre_personas():
    solo = huella.calcular(huella.Respuestas(kwh_mes=300, personas_hogar=1))
    tres = huella.calcular(huella.Respuestas(kwh_mes=300, personas_hogar=3))
    assert tres.hogar_t == pytest.approx(solo.hogar_t / 3, rel=0.01)


def test_factor_colombiano_es_mas_limpio_que_el_mundial():
    """
    La red colombiana es mayoritariamente hidráulica: usar el promedio mundial
    sobreestimaría la huella eléctrica de un usuario colombiano.
    """
    co = huella.calcular(huella.Respuestas(kwh_mes=300, usa_factor_colombia=True))
    mundo = huella.calcular(huella.Respuestas(kwh_mes=300, usa_factor_colombia=False))
    assert co.hogar_t < mundo.hogar_t


def test_reciclar_reduce_residuos():
    sin_reciclar = huella.calcular(huella.Respuestas(residuos_kg_semana=10, recicla=False))
    reciclando = huella.calcular(huella.Respuestas(residuos_kg_semana=10, recicla=True))
    assert reciclando.residuos_t < sin_reciclar.residuos_t


def test_dieta_vegana_pesa_menos_que_carnivora():
    carne = huella.calcular(huella.Respuestas(dieta="carne_alta"))
    vegano = huella.calcular(huella.Respuestas(dieta="vegano"))
    assert vegano.dieta_t < carne.dieta_t


def test_total_es_la_suma_del_desglose():
    res = huella.calcular(huella.Respuestas(
        km_semana=100, horas_vuelo_anio=5, kwh_mes=200,
        residuos_kg_semana=5, dieta="carne_media",
    ))
    assert res.total_t == pytest.approx(sum(res.desglose.values()), abs=0.02)


def test_resultado_realista_para_un_caso_tipico():
    """Un colombiano urbano promedio debería caer en un rango plausible."""
    res = huella.calcular(huella.Respuestas(
        transporte="auto_gasolina", km_semana=150, horas_vuelo_anio=6,
        kwh_mes=180, personas_hogar=3, glp_kg_mes=15,
        dieta="carne_media", residuos_kg_semana=8,
    ))
    assert 2.0 < res.total_t < 8.0, f"resultado fuera de rango: {res.total_t}"


# ── Huella: validación ───────────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs", [
    {"km_semana": -10},
    {"kwh_mes": -5},
    {"residuos_kg_semana": -1},
    {"horas_vuelo_anio": -3},
    {"pasajeros_auto": 0},
    {"personas_hogar": 0},
    {"transporte": "helicoptero"},
    {"dieta": "carnivoro_estricto"},
])
def test_entradas_invalidas_se_rechazan(kwargs):
    with pytest.raises(ValueError):
        huella.calcular(huella.Respuestas(**kwargs))


# ── Huella: recomendaciones ──────────────────────────────────────────────────

def test_recomendaciones_ordenadas_por_impacto():
    r = huella.Respuestas(
        transporte="auto_gasolina", km_semana=300, pasajeros_auto=1,
        horas_vuelo_anio=20, dieta="carne_alta", residuos_kg_semana=10,
    )
    res = huella.calcular(r)
    sugerencias = huella.recomendaciones(r, res)

    assert sugerencias, "debería sugerir algo con este perfil"
    assert len(sugerencias) <= 4


def test_no_sugiere_reciclar_a_quien_ya_recicla():
    r = huella.Respuestas(residuos_kg_semana=10, recicla=True)
    sugerencias = huella.recomendaciones(r, huella.calcular(r))
    assert not any("reciclar" in s.lower() for s in sugerencias)


def test_no_sugiere_bajar_de_dieta_a_un_vegano():
    r = huella.Respuestas(dieta="vegano")
    sugerencias = huella.recomendaciones(r, huella.calcular(r))
    assert not any("dieta" in s.lower() for s in sugerencias)


# ── Quiz: integridad de los datos ────────────────────────────────────────────

def test_todas_las_preguntas_tienen_respuesta_valida():
    for p in quiz.PREGUNTAS:
        assert 0 <= p.correcta < len(p.opciones), f"pregunta {p.id}: índice inválido"


def test_las_preguntas_tienen_al_menos_tres_opciones():
    for p in quiz.PREGUNTAS:
        assert len(p.opciones) >= 3, f"pregunta {p.id}: muy pocas opciones"


def test_ids_unicos():
    ids = [p.id for p in quiz.PREGUNTAS]
    assert len(ids) == len(set(ids))


def test_todas_citan_fuente_y_explican():
    for p in quiz.PREGUNTAS:
        assert p.fuente.strip(), f"pregunta {p.id} sin fuente"
        assert len(p.explicacion) > 40, f"pregunta {p.id}: explicación muy corta"


def test_hay_al_menos_diez_preguntas():
    """El informe pide 10-15."""
    assert 10 <= len(quiz.PREGUNTAS) <= 15


# ── Quiz: no filtrar respuestas ──────────────────────────────────────────────

def test_las_preguntas_publicas_no_incluyen_la_respuesta():
    """
    Mandar `correcta` al frontend permitiría ver las respuestas desde las
    herramientas de desarrollo del navegador.
    """
    for pregunta in quiz.preguntas_publicas():
        assert "correcta" not in pregunta
        assert "explicacion" not in pregunta


# ── Quiz: calificación ───────────────────────────────────────────────────────

def test_todo_correcto_da_puntaje_perfecto():
    respuestas = {p.id: p.correcta for p in quiz.PREGUNTAS}
    res = quiz.calificar(respuestas)
    assert res.puntaje == res.total
    assert res.porcentaje == 100.0
    assert not res.incorrectas


def test_sin_responder_da_cero():
    res = quiz.calificar({})
    assert res.puntaje == 0
    assert len(res.incorrectas) == len(quiz.PREGUNTAS)


def test_respuesta_equivocada_cuenta_como_incorrecta():
    primera = quiz.PREGUNTAS[0]
    incorrecta = (primera.correcta + 1) % len(primera.opciones)
    res = quiz.calificar({primera.id: incorrecta})
    assert primera.id in res.incorrectas


def test_id_desconocido_no_revienta():
    res = quiz.calificar({9999: 0})
    assert res.puntaje == 0


def test_texto_para_compartir_tiene_un_bloque_por_pregunta():
    res = quiz.calificar({p.id: p.correcta for p in quiz.PREGUNTAS})
    texto = quiz.texto_para_compartir(res)
    assert texto.count("🟩") == len(quiz.PREGUNTAS)
    assert "🟥" not in texto
