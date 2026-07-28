# Informe Técnico: Plataforma de Clima y Sostenibilidad — Plan de Desarrollo v3

**Autor:** Carlos (con apoyo de investigación, planeación y revisión de Claude)
**Fecha:** 27 de julio de 2026
**Versión:** 3 (recorte de v2.1 tras revisión técnica)
**Estado:** Listo para desarrollo — ciudad por defecto: Santa Marta, Colombia
**Propósito:** Hoja de ruta técnica lista para iniciar el desarrollo en Claude Code. Conserva lo que ya demostró valor (adaptadores por fuente, caché con degradación con gracia, Santa Marta validada primero) y recorta lo que resolvía problemas que el proyecto todavía no tiene.

---

## Registro de cambios

| De → A | Cambios principales |
|---|---|
| **v1 → v2.1** | (generado en otra sesión) Arquitectura plana → capas con adaptadores. Fase 0 de fundaciones. Modelo jerárquico de lugares (ciudad→depto→país) con herencia. Motor de reglas. Docker, CI, structlog, tenacity, tests VCR. Duración 6-8 → 7-9 semanas. |
| **v2.1 → v3** | Fase 0 y Fase 1 **fusionadas** en un solo arranque de 3-5 días. Jerarquía de 3 niveles → **diccionario plano de lugares** (misma ventaja de "agregar lugar = 1 entrada", sin la complejidad de herencia). Motor de reglas genérico → función de umbral simple. `tenacity`/`structlog`/Docker/CI/VCR → **pospuestos explícitamente** (no descartados, solo no son día-1). Corregido: los `curl` de validación de OpenAQ ahora incluyen el header `X-API-Key` requerido (faltaba en v2.1 y habría fallado con 401). Añadida nota sobre el límite de "una sola zona por cuenta" del tier gratuito de Electricity Maps. |

---

## 1. Resumen ejecutivo

Carlos, desarrollador solo, construye una plataforma de datos climáticos: alertas por Telegram, dashboard en tiempo real, monitor de incendios, predictor de riesgo, calculadora de huella y quiz educativo — para Santa Marta, Colombia, como primer lugar.

**Principio rector de esta versión:** cada práctica de confiabilidad se justifica por un dolor real y cercano (APIs gratuitas que fallan o tienen rate limits); cada práctica de escalabilidad especulativa (múltiples países, múltiples reglas, contribuidores externos) se pospone hasta que exista evidencia de que hace falta. El código queda en estado "publicable" como open source en todo momento, sin invertir tiempo en construir esa capa todavía.

**Objetivo inmediato:** bot funcionando y enviando alertas reales en 3-5 días.

---

## 2. Problema

Los datos abiertos sobre calidad del aire, clima, incendios y energía existen (OpenAQ, Open-Meteo, NASA FIRMS, Electricity Maps), pero están dispersos en APIs distintas, sin una interfaz unificada para alguien que quiera monitorear su entorno sin ser científico de datos.

**A quién afecta:** personas interesadas en el aire y clima de Santa Marta, y —para Carlos— sirve como portafolio técnico y eventual base de un proyecto de mayor impacto.

**Riesgo que esta versión evita:** construir sobre una premisa no validada. Antes de escribir una sola línea de bot, se confirma si existe cobertura real de datos de aire para Santa Marta (ver §8, Día 1).

---

## 3. Objetivos

1. Bot funcional enviando alertas reales en ≤5 días desde el inicio.
2. Unificar 4 fuentes (OpenAQ, Open-Meteo, NASA FIRMS, Electricity Maps) para el final de la Fase 3.
3. Cero crashes por fallo de API externa: toda fuente se degrada a caché etiquetado, nunca a error visible para el usuario.
4. Agregar una fuente nueva no debe requerir tocar el bot ni el dashboard (validado al final de la Fase 3).
5. Agregar un lugar nuevo no debe requerir tocar código (una entrada en `locations.py`).
6. Mantener el código publicable en GitHub desde el día uno.
7. Completar las 4 fases + 2 módulos paralelos en 6-8 semanas trabajando solo.

## 4. Fuera de alcance (Non-Goals) — v1

- **Multiusuario/autenticación** — v1 es de un usuario; el esquema de BD usa `chat_id` como clave, así que escalar a multiusuario después es barato.
- **Jerarquía geográfica (departamento/país) y geocoding a cualquier lugar del mundo** — se arranca con un lugar (Santa Marta); agregar 1-2 lugares más es trivial con el diccionario plano. La jerarquía con herencia se reconsidera solo si de verdad se necesitan más de ~5-6 lugares con configuración distinta entre sí.
- **Motor de reglas genérico** — hoy hay una sola regla (umbral de PM2.5); se generaliza cuando exista una tercera regla real, no antes.
- **Docker, CI, logging estructurado, reintentos con librería dedicada** — no se descartan, se posponen a cuando el proyecto los necesite de verdad (ver §8, "Pospuesto explícitamente").
- **Gobernanza open source formal, app móvil, monetización** — fuera de alcance, sin cambios respecto a versiones anteriores.
- **Modelo de predicción de nivel productivo (Fase 4)** — educativo/demostrativo, nunca alerta oficial.

## 5. Arquitectura y stack

### 5.1 Principios

1. **Un adaptador por fuente, misma forma de retorno.** Agregar una fuente = crear un archivo en `sources/`, nunca editar los existentes.
2. **Un lugar = una entrada en un diccionario.** Sin YAML, sin jerarquía, sin resolución de herencia — eso se agrega el día que realmente haga falta.
3. **Una sola puerta a los datos:** `storage.py`. SQLite ahora; si algún día hace falta Postgres, se toca un solo archivo.
4. **Nunca crashear por una fuente externa caída.** Reintento simple (3 intentos, espera creciente) y, si sigue fallando, se sirve el último valor cacheado con su antigüedad visible.
5. **Configuración en `.env`, nunca hardcodeada ni commiteada.**

### 5.2 Estructura del repositorio

```
clima-plataforma/
├── README.md
├── requirements.txt
├── .env.example
├── config.py                 # carga .env, valida al arrancar (sin librería extra obligatoria)
├── locations.py               # diccionario plano de lugares (ver §5.4)
├── storage.py                  # SQLite: guarda lecturas + sirve último valor como caché
├── alerts.py                    # función de umbral simple
├── sources/
│   ├── base.py                 # firma común: obtener_ultimo(lugar) -> Lectura
│   ├── openaq.py                # Fase 1 — con reintentos y cascada de fallback
│   ├── openmeteo.py             # Fase 2
│   ├── electricity_maps.py      # Fase 2
│   └── firms.py                 # Fase 3
├── bot.py                        # Fase 1
├── dashboard.py                   # Fase 2-3 (Streamlit, pestañas simples)
├── huella.py                      # Módulo paralelo A
├── quiz.py                        # Módulo paralelo B
├── risk.py                        # Fase 4
└── tests/
    ├── fixtures/                  # 1-2 respuestas JSON grabadas por fuente
    └── test_openaq.py
```

*Nota: esta estructura deja espacio para crecer hacia la versión en capas de v2.1 (adaptadores → `sources/`, `storage.py` → repository) sin reescritura — solo se difiere la ceremonia (Protocol, jerarquía de errores, YAML) hasta que el proyecto la necesite.*

### 5.3 Stack

| Componente | Elección | Nota |
|---|---|---|
| Lenguaje | Python 3.11+ | Ecosistema de datos maduro |
| HTTP | `requests` | Simple, suficiente para el volumen actual |
| Bot | `python-telegram-bot` | Estándar |
| Dashboard | `Streamlit` | Rápido sin pelear con frontend |
| Mapas | `folium` | Integra con Streamlit |
| ML (Fase 4) | `scikit-learn` + `pandas` | Proporcional a un predictor educativo |
| BD | SQLite | Cero configuración |
| Tests | `pytest` | Fixtures JSON simples, sin `vcrpy` todavía |
| Despliegue bot | Render (free tier), sin Docker | Soporta Python directo |
| Despliegue dashboard | Streamlit Community Cloud | Gratis |
| Licencia (al publicar) | MIT o Apache 2.0 | Decisión en Fase 2/3 |

### 5.4 Lugares (`locations.py`)

```python
LUGARES = {
    "santa-marta": {
        "nombre": "Santa Marta, Colombia",
        "lat": 11.2408,
        "lon": -74.1990,
        "bbox": (-74.30, 11.05, -73.85, 11.40),
        "zona_electricidad": "CO",
        "fallback_openaq": "barranquilla",   # estación más cercana si no hay local
    },
    # Agregar un lugar nuevo = una entrada más aquí. Cero cambios en el resto del código.
}
DEFAULT_LUGAR = "santa-marta"
```

### 5.5 Nota importante sobre Electricity Maps

El tier gratuito limita la cuenta a **una sola zona en total** (se elige al registrarse, no por request). Para Colombia esto no debería ser un problema — el país se representa como una sola zona (`CO`) — pero si en algún momento quieres datos de otro país, necesitarás reconfigurar la cuenta o pasar a un tier pago. No construyas nada que asuma múltiples zonas simultáneas mientras estés en el tier gratis.

---

## 6. Fases del proyecto

### Fase 1 — Fundaciones + bot de alertas (fusionado)

**Duración estimada:** 3-5 días
**Objetivo:** Validar la premisa, dejar una base simple y confiable, y tener el bot enviando alertas reales.

**Historias de usuario:**
- Como usuario, quiero recibir un mensaje de Telegram cuando la calidad del aire supere mi umbral.
- Como usuario, quiero un comando `/estado` con la situación actual bajo demanda.
- Como usuario, quiero que el bot me diga claramente si un dato es viejo o de una estación lejana, no que finja precisión que no tiene.

**Requisitos — Must-Have (P0):**
- [ ] `.env` + `config.py`: carga variables, revisa que las obligatorias existan y termina con mensaje claro si falta alguna (sin librería adicional obligatoria)
- [ ] `locations.py` con Santa Marta (§5.4)
- [ ] `sources/base.py`: firma común `obtener_ultimo(lugar: dict) -> Lectura`
- [ ] `sources/openaq.py`: adaptador con reintentos simples (3 intentos, espera creciente) y cascada de fallback: estación local → estación más cercana (Barranquilla) → último valor en caché, cada uno con etiqueta visible de procedencia
- [ ] `storage.py`: tabla `lecturas` en SQLite; función `ultimo_valor(fuente, lugar, metrica)` que sirve de caché
- [ ] `alerts.py`: función simple `revisar_alerta(valor, umbral) -> str | None`
- [ ] `bot.py`: comandos `/estado`, `/umbral <valor>`, `/ayuda`; nunca deja una excepción sin capturar
- [ ] `tests/test_openaq.py`: al menos 2 tests usando un JSON de fixture grabado (sin red)
- [ ] Bot desplegado (Render free tier, sin Docker) o corriendo local mientras se prueba

**Nice-to-Have (P1):**
- [ ] `/lugar <id>` si ya agregaste más de un lugar en `locations.py`
- [ ] `logging` estándar de Python a archivo (sin `structlog` todavía)
- [ ] `/historial` con las últimas N alertas

**Pospuesto explícitamente (no es que esté mal, es que no toca todavía):**
- Docker / docker-compose — agrégalo si necesitas paridad exacta local/producción o vas a onboardear a alguien más
- CI en GitHub Actions — barato de sumar en la Fase 2, no bloquea nada ahora
- `structlog`, `tenacity`, `pydantic-settings` — las versiones simples de estas prácticas ya están cubiertas arriba; cambia a la librería dedicada si el código manual empieza a doler
- Jerarquía de lugares con herencia, motor de reglas genérico, geocoding libre — reconsiderar solo si el proyecto crece a varios lugares/reglas de verdad distintas

**Criterios de aceptación:**
- Dado que falta `OPENAQ_API_KEY` en `.env`, cuando arranca el bot, entonces termina con un mensaje claro, no un traceback
- Dado que OpenAQ falla 3 veces, cuando se consulta `/estado`, entonces responde con el último valor cacheado y su antigüedad — nunca un error crudo
- Dado un umbral de 50 µg/m³ y una lectura de 65, cuando corre la consulta programada, entonces llega la alerta a Telegram en <15 min
- `pytest` pasa en verde sin conexión a internet

**Entregable:** Bot en producción para Santa Marta, con caché y reintentos reales.

---

### Fase 2 — Dashboard en tiempo real + acumulación de historial

**Duración estimada:** 1-2 semanas
**Objetivo:** Casa visual del proyecto; empieza a acumular historial (esto adelanta el reloj de la Fase 4).

**Requisitos — Must-Have (P0):**
- [ ] `sources/openmeteo.py` y `sources/electricity_maps.py`, misma firma que `openaq.py`
- [ ] Dashboard Streamlit con 3 pestañas: Aire, Clima, Energía — cada una con valor actual + tendencia de 7 días
- [ ] Semáforo de salud por fuente (🟢🟡🔴) visible en el header
- [ ] El proceso que consulta las fuentes persiste cada lectura en `storage.py` de forma continua

**Nice-to-Have (P1):**
- [ ] CI en GitHub Actions (buen momento para sumarlo — el proyecto ya tiene forma)
- [ ] Selector de lugar en la interfaz (si ya agregaste más de uno)
- [ ] Export a CSV

**Criterios de aceptación:**
- El dashboard carga en <5 s con datos reales
- Dado que Electricity Maps falla, cuando cargo el panel, entonces Aire y Clima funcionan y Energía muestra "🔴 no disponible — último dato hace X min"
- Tras 2 semanas corriendo, hay acumulación continua sin huecos mayores a 1 h

**Entregable:** Dashboard público por URL + historial acumulándose.

---

### Fase 3 — Monitor de incendios

**Duración estimada:** 1-2 semanas
**Objetivo:** Capa de mapa como una pestaña más del dashboard.

**Requisitos — Must-Have (P0):**
- [ ] `sources/firms.py`, misma firma que las demás fuentes (focos últimas 24-48h dentro del `bbox` del lugar)
- [ ] Pestaña de mapa en el dashboard (folium) con los focos como puntos navegables

**Nice-to-Have (P1):**
- [ ] Regla de alerta: foco de calor a <N km → aviso por bot (usa `alerts.py`, sin necesidad de generalizarlo todavía — un segundo `if` es suficiente para 2 reglas)
- [ ] Capa de pérdida forestal (Global Forest Watch) — su API no es REST simple; evaluar costo de integración, no bloquea la fase si es alto

**Criterios de aceptación:**
- El mapa muestra focos de los últimos 2 días para Santa Marta
- *Prueba de escalabilidad:* agregar FIRMS no requirió tocar `bot.py` ni `dashboard.py` — solo crear `firms.py` y registrarlo

**Entregable:** Mapa de incendios integrado al dashboard.

---

### Módulo paralelo A — Calculadora de huella de carbono
**Duración:** ~1 semana (en cualquier momento tras la Fase 2)
**Requisitos (P0):** formulario (transporte, energía, dieta) → t CO₂e/año usando factores públicos (EPA/DEFRA) documentados con su fuente en el código. Pestaña "Mi huella" en el dashboard.

### Módulo paralelo B — Quiz educativo
**Duración:** ~1 semana (en cualquier momento tras la Fase 2)
**Requisitos (P0):** 10-15 preguntas, resultado con puntaje y datos curiosos, botón de compartir. Pestaña "Quiz" en el dashboard.

---

### Fase 4 — Predictor simple de riesgo climático

**Duración estimada:** 2-3 semanas (empieza cuando haya ≥2-4 semanas de historial desde la Fase 2)
**Objetivo:** Estimación educativa de riesgo de calor extremo.

**Requisitos — Must-Have (P0):**
- [ ] `risk.py` con modelo básico (scikit-learn) entrenado con el historial propio
- [ ] Etiqueta "estimación experimental" visible siempre junto al resultado
- [ ] Test del entrenamiento con datos de fixture (reproducible)

**Criterios de aceptación:**
- El modelo entrena sin errores con datos reales
- Nunca se presenta como alerta oficial

**Entregable:** Sección de riesgo estimado en el dashboard.

---

## 7. Métricas de éxito

**Tempranas:** Fase 1 en producción con alertas reales (sí/no, fecha) · Uptime del bot >95% en la primera semana · Dashboard público desplegado (sí/no)

**De confiabilidad:** cero crashes en producción por fallo de API externa (revisar logs) · toda fuente caída se degrada a caché etiquetado, nunca a error visible

**De escalabilidad (validación, no aspiración):** al final de la Fase 3, las 4 fuentes coexisten sin haber tocado `bot.py` ni `dashboard.py` fuera de registrar cada nueva pestaña/fuente

**Largo plazo:** usuarios reales usando bot/dashboard · si se abre como open source: estrellas, forks, primer colaborador externo

## 8. Plan del Día 1 (antes de escribir el bot)

```bash
# 1. ¿Hay estación OpenAQ en Santa Marta? (incluye el header — sin esto, 401)
curl "https://api.openaq.org/v3/locations?bbox=-74.30,11.05,-73.85,11.40&limit=10" \
  -H "X-API-Key: $OPENAQ_API_KEY"

# 2. Si no hay, revisar Barranquilla (~90 km) como fallback
curl "https://api.openaq.org/v3/locations?bbox=-74.85,10.90,-74.70,11.05&limit=10" \
  -H "X-API-Key: $OPENAQ_API_KEY"

# 3. ¿Electricity Maps cubre la zona CO en el tier gratis? (recuerda: la cuenta
#    gratuita solo permite 1 zona total — configúrala como CO al registrarte)
curl -H "auth-token: $ELECTRICITY_MAPS_KEY" \
  "https://api.electricitymap.org/v3/carbon-intensity/latest?zone=CO"
```

Si OpenAQ no tiene nada ni en Santa Marta ni en Barranquilla, hay una alternativa real que vale la pena investigar antes de descartar la idea: Corpamag (la autoridad ambiental de Magdalena) opera una red de ~14 estaciones de monitoreo en la zona costera entre Santa Marta y Ciénaga desde 1999. No hay confirmación de que sus datos lleguen a OpenAQ, pero es un dato a un correo o portal de datos abiertos de distancia si hace falta un plan B.

## 9. Preguntas abiertas

| # | Pregunta | Estado |
|---|---|---|
| 1 | ¿Ciudad por defecto? | 🟢 Resuelta: Santa Marta, Colombia |
| 2 | ¿OpenAQ tiene estación en Santa Marta? | 🟠 Validar Día 1 (§8) — fallback a Barranquilla o Corpamag si no |
| 3 | ¿Electricity Maps cubre `CO` en el tier gratis? | 🟠 Validar Día 1 (§8) |
| 4 | ¿Cuándo hacer público el repo? | 🟡 No bloqueante — sugerido al cerrar Fase 2 |
| 5 | ¿Fase 4 con datos propios o dataset público complementario? | 🟡 Decidir al llegar a la Fase 4, con el historial real ya acumulado |

## 10. Plan de tiempo

| Fase | Duración | Depende de |
|---|---|---|
| Fase 1 — Fundaciones + bot | 3-5 días | — |
| Fase 2 — Dashboard + historial | 1-2 semanas | Fase 1 |
| Fase 3 — Monitor de incendios | 1-2 semanas | Fase 2 |
| Módulo A — Huella | ~1 semana | Fase 2 (paralelo) |
| Módulo B — Quiz | ~1 semana | Fase 2 (paralelo) |
| Fase 4 — Predictor | 2-3 semanas | Fase 2 + historial acumulado |

**Total: 6-8 semanas** trabajando solo.

## 11. Notas para el modo de desarrollo

1. **Empieza por el Día 1 (§8) antes de escribir código** — dos curls confirman si la premisa central funciona para Santa Marta.
2. **Cada fase en commits independientes y funcionales.**
3. **Los criterios de aceptación son la definición de "hecho."**
4. **Claves en `.env`, nunca commiteadas**; `.env.example` se actualiza en el mismo commit que introduce una variable nueva.
5. **Toda fuente nueva respeta la firma de `sources/base.py`** — si agregar una fuente obliga a tocar `bot.py` o `dashboard.py`, es una señal de alarma.
6. **Todo lugar nuevo es una entrada en `locations.py`** — si agregar un lugar requiere tocar otro archivo, la abstracción se rompió.
7. **No adoptes Docker, CI, `tenacity` o `structlog` "porque sí"** — son buenas prácticas, pero su momento es cuando el dolor que resuelven ya es real (ver §6, "Pospuesto explícitamente" en cada fase), no antes.
8. **Primer commit:** estructura de carpetas de §5.2 + `requirements.txt` + `locations.py` con Santa Marta.
