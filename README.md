# Plataforma de Clima y Sostenibilidad 🌤️

Monitor de calidad del aire, clima y energía para **Santa Marta, Colombia**.

> Proyecto personal de Carlos · Bot de Telegram · Dashboard React

---

## Estado actual

| Fase | Estado |
|---|---|
| **Fase 1** — Fundaciones + Bot de alertas | ✅ Funcionando |
| **Fase 2** — Dashboard + historial | 🟢 En curso |
| **Fase 3** — Monitor de incendios | ⏳ Pendiente |
| **Módulo A** — Calculadora de huella | ⏳ Pendiente |
| **Módulo B** — Quiz educativo | ⏳ Pendiente |
| **Fase 4** — Predictor de riesgo | ⏳ Pendiente |

---

## Fuentes de datos

| Fuente | Datos | API key | Frescura |
|---|---|---|---|
| [Open-Meteo Air Quality](https://open-meteo.com) | PM2.5 (modelo CAMS) | No | Horaria |
| [Open-Meteo Forecast](https://open-meteo.com) | Temperatura | No | Horaria |
| [XM](https://servapibi.xm.com.co) | Intensidad de carbono de la red | No | ~2-3 días de rezago |
| [OpenAQ v3](https://api.openaq.org) | Estaciones físicas | Sí | *sin cobertura local* |
| NASA FIRMS | Focos de incendios | — | Fase 3 |

### Hallazgos de la validación del Día 1

Dos decisiones del plan original no sobrevivieron al contacto con las APIs reales:

**OpenAQ no cubre Santa Marta.** No hay estaciones en el bbox de la ciudad, ni en
Barranquilla, ni en ninguna parte de la costa Caribe — se verificó contra las 66
estaciones que OpenAQ tiene en toda Colombia (están en Bogotá, Medellín, Cali y
Bucaramanga). La fuente primaria de aire pasó a ser **Open-Meteo Air Quality**
(modelo Copernicus CAMS), que sí tiene cobertura global y no pide API key.
OpenAQ se conserva como fuente secundaria por si algún día suman estaciones.

**Electricity Maps se reemplazó por XM.** Su tier gratuito resultó ambiguo
(posiblemente solo un trial de 14 días) y limita la cuenta a una sola zona.
**XM**, el operador oficial del mercado eléctrico colombiano, publica la métrica
`factorEmisionCO2e` (gCO₂eq/kWh, horaria) de forma gratuita y sin registro.
El adaptador de Electricity Maps queda en el repo pero sin usar.

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

Solo `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` son necesarios para el bot
(obtén el chat_id con `python dia1_chatid.py`). Las fuentes de aire, clima y
energía funcionan sin ninguna API key.

### 3. Tests

```bash
pytest tests/ -v
```

> Corren **sin conexión a internet**, con fixtures JSON grabados.

### 4. Levantar el proyecto

Son tres procesos independientes:

```bash
python collector.py
```

```bash
python api.py
```

```bash
npm run dev --prefix dashboard-ui
```

Y el bot de Telegram:

```bash
python bot.py
```

El dashboard queda en http://localhost:5173 (proxy a la API en el puerto 8000).

---

## Arquitectura

```
Una fuente nueva → un archivo en sources/ + una entrada en sources/registry.py
Un lugar nuevo   → una entrada en locations.py
```

Nada más. El bot, la API y el dashboard leen del registro, así que agregar una
fuente no obliga a tocarlos (es la "prueba de escalabilidad" del informe §7).

| Archivo | Rol |
|---|---|
| `config.py` | Carga y valida `.env`; termina con mensaje claro si falta algo |
| `locations.py` | Diccionario plano de lugares |
| `sources/base.py` | `Lectura`: valor + procedencia + antigüedad |
| `sources/registry.py` | Registro único de fuentes activas |
| `storage.py` | SQLite: única puerta a los datos + caché |
| `collector.py` | Consulta todas las fuentes en bucle y persiste |
| `alerts.py` | Umbral de PM2.5 y formato de mensajes |
| `bot.py` | Bot de Telegram |
| `api.py` | API REST para el dashboard |
| `dashboard-ui/` | Frontend React + Vite |

### Nunca crashear, nunca fingir precisión

Cada fuente cae en cascada: **API → caché SQLite → error amigable**. Y toda
lectura arrastra su procedencia y antigüedad hasta la UI: un dato de hace dos
días se muestra como tal, no disfrazado de dato en vivo.

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

## Licencia

MIT — Ver decisión final en Fase 2/3.
