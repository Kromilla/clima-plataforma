# Plataforma de Clima y Sostenibilidad 🌤️

Monitor de calidad del aire, clima, energía e incendios para **Santa Marta, Colombia**.

> Proyecto personal de Carlos · Bot de Telegram · Dashboard React

---

## Estado

| Fase | Estado |
|---|---|
| **Fase 1** — Fundaciones + bot de alertas | ✅ |
| **Fase 2** — Dashboard + historial | ✅ |
| **Fase 3** — Monitor de incendios | ✅ *(requiere clave gratuita de NASA)* |
| **Módulo A** — Calculadora de huella | ✅ |
| **Módulo B** — Quiz educativo | ✅ |
| **Fase 4** — Predictor de riesgo | ✅ *(estimación experimental)* |

---

## Fuentes de datos

| Fuente | Datos | API key | Frescura |
|---|---|---|---|
| [Open-Meteo Air Quality](https://open-meteo.com) | PM2.5 (modelo CAMS) | No | Horaria |
| [Open-Meteo Forecast](https://open-meteo.com) | Temperatura, humedad | No | Horaria |
| [XM](https://servapibi.xm.com.co) | Intensidad de carbono de la red | No | ~2-3 días de rezago |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov) | Focos de calor (VIIRS 375 m) | Sí, gratuita | ~3 h |
| [Open-Meteo Archive](https://open-meteo.com) | Histórico ERA5 para el predictor | No | ~6 días de rezago |
| [OpenAQ v3](https://api.openaq.org) | Estaciones físicas | Sí | *sin cobertura local* |

### Hallazgos de la validación del Día 1

Dos decisiones del plan original no sobrevivieron al contacto con las APIs reales:

**OpenAQ no cubre Santa Marta.** No hay estaciones en el bbox de la ciudad, ni en
Barranquilla, ni en ninguna parte de la costa Caribe — verificado contra las 66
estaciones que OpenAQ tiene en toda Colombia (están en Bogotá, Medellín, Cali y
Bucaramanga). La fuente primaria de aire pasó a ser **Open-Meteo Air Quality**
(modelo Copernicus CAMS), con cobertura global y sin API key. OpenAQ queda como
fuente secundaria por si algún día suman estaciones.

**Electricity Maps se reemplazó por XM.** Su tier gratuito resultó ambiguo
(posiblemente solo un trial de 14 días) y limita la cuenta a una sola zona.
**XM**, el operador oficial del mercado eléctrico colombiano, publica
`factorEmisionCO2e` (gCO₂eq/kWh, horaria) gratis y sin registro.

> Corpamag opera ~14 estaciones reales entre Santa Marta y Ciénaga y publica en
> [datos.gov.co](https://www.datos.gov.co/resource/dgnf-6h7v.json) sin API key,
> pero con ~3 meses de rezago. Sirve como contexto histórico, no para alertas.

---

## Inicio rápido

### 1. Entorno

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
```

### 2. Variables de entorno

```bash
cp .env.example .env
```

Solo `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` son obligatorios (el chat_id lo
obtienes con `python dia1_chatid.py`). Aire, clima y energía funcionan sin
ninguna API key. `FIRMS_MAP_KEY` es opcional y solo activa el mapa de incendios.

### 3. Historial para el predictor

La Fase 4 necesita semanas de datos. En vez de esperar, se traen del archivo
ERA5 — son mediciones reales reanalizadas, guardadas con su fecha original:

```bash
python backfill.py --dias 730
```

### 4. Tests

```bash
pytest tests/ -q
```

> 99 tests, todos **sin conexión a internet**.

### 5. Levantar el proyecto

Tres procesos independientes:

```bash
python collector.py
```

```bash
python api.py
```

```bash
npm run dev --prefix dashboard-ui
```

Y el bot:

```bash
python bot.py
```

Dashboard en http://localhost:5173 · API en http://localhost:8000

---

## Arquitectura

```
Una fuente nueva → un archivo en sources/ + una entrada en sources/registry.py
Un lugar nuevo   → una entrada en locations.py
```

Nada más. El bot, la API y el dashboard leen del registro, así que agregar una
fuente no obliga a tocarlos. Sumar FIRMS en la Fase 3 no requirió modificar
`bot.py` ni las páginas existentes del dashboard — la prueba de escalabilidad
del informe (§7).

| Archivo | Rol |
|---|---|
| `config.py` | Carga y valida `.env` |
| `locations.py` | Diccionario plano de lugares |
| `sources/base.py` | `Lectura`: valor + procedencia + antigüedad |
| `sources/registry.py` | Registro único de fuentes |
| `storage.py` | SQLite: única puerta a los datos + caché |
| `collector.py` | Consulta todas las fuentes en bucle y persiste |
| `backfill.py` | Trae histórico real para el predictor |
| `alerts.py` | Umbral de PM2.5 y alerta por foco cercano |
| `huella.py` | Calculadora de huella (Módulo A) |
| `quiz.py` | Quiz educativo (Módulo B) |
| `risk.py` | Predictor de riesgo de calor (Fase 4) |
| `bot.py` | Bot de Telegram |
| `api.py` | API REST |
| `dashboard-ui/` | Frontend React + Vite |

### Nunca crashear, nunca fingir precisión

Cada fuente cae en cascada: **API → caché SQLite → mensaje claro**. Toda lectura
arrastra su procedencia y antigüedad hasta la UI: un dato de hace dos días se
muestra como tal, no disfrazado de dato en vivo. Los umbrales del semáforo son
por fuente, porque el rezago de XM es normal y no una falla.

### Sobre el predictor (Fase 4)

Estima la probabilidad de que el **índice de calor** (temperatura + humedad,
fórmula de la NOAA) supere 39 °C al día siguiente. Se usa índice de calor y no
temperatura seca porque en una ciudad costera la humedad es la que vuelve
peligroso el calor.

La validación es **cronológica**: entrena con el pasado y evalúa con los días
siguientes. Una partición aleatoria filtraría el futuro al entrenamiento e
inflaría las métricas. El dashboard muestra siempre la **mejora sobre la
referencia** (acertar siempre la clase mayoritaria) — sin eso, una exactitud
alta puede ocultar un modelo inútil.

Va etiquetado como estimación experimental en todas las capas. No es una alerta
oficial: para eso está el IDEAM.

---

## Comandos del bot

| Comando | Descripción |
|---|---|
| `/estado` | Aire, clima y energía actuales |
| `/umbral N` | Cambiar umbral de alerta (ej. `/umbral 35`) |
| `/ayuda` | Lista de comandos |

---

## Principios de diseño

1. **Un adaptador por fuente** — agregar una fuente = crear un archivo + registrarlo
2. **Un lugar = una entrada** en `locations.py`
3. **Una sola puerta a los datos**: `storage.py`
4. **Nunca crashear** por una fuente externa caída
5. **Nunca fingir frescura** que el dato no tiene
6. **Configuración en `.env`**, nunca hardcodeada

---

## Vulnerabilidad conocida

`npm audit` reporta un fallo alto en `react-router-dom` (bypass de CSRF en modo
RSC). Ya está en la última versión publicada y no hay parche. **No aplica a este
proyecto**: es un SPA con `BrowserRouter`, sin RSC ni server actions. Hacer
`npm audit fix --force` degradaría a un major anterior y rompería la app.

---

## Licencia

MIT
