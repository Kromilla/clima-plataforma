# Despliegue gratis (Vercel + Render + Supabase)

Pone ClimaBot en línea sin tarjeta de crédito. Tres piezas:

| Pieza | Dónde | Qué corre |
|---|---|---|
| Base de datos | **Supabase** | Postgres (historial + config) |
| API | **Render** | FastAPI (web service) |
| Collector | **GitHub Actions** | recolecta cada 20 min y escribe a Supabase |
| Dashboard | **Vercel** | React estático |

> El collector NO va en Render: sus cron jobs son de pago. Se corre como workflow
> programado de GitHub Actions, que es gratis.
> El bot de Telegram **sí responde en producción**: no como worker 24/7 (son de
> pago), sino por *webhook* dentro del mismo servicio de la API. Telegram hace
> POST a `/telegram/webhook` cuando llega un comando, lo que además despierta el
> servicio si estaba dormido. Se configura solo al arrancar (usa la URL pública
> que Render inyecta en `RENDER_EXTERNAL_URL`); no hay que tocar nada.
> La alternativa "todo en una VM 24/7" está en [`DEPLOY_oracle.md`](DEPLOY_oracle.md).

---

## 1. Supabase (base de datos) ✅

Ya creado. Solo necesitas la cadena de conexión:

- Supabase → **Connect** → **Session pooler** → copia la URI.
- Reemplaza `[YOUR-PASSWORD]` por la contraseña de la BD (sin corchetes).
- Esa es tu `DATABASE_URL`. Úsala tal cual en Render (paso 2).

---

## 2. Render (API)

1. Entra a <https://render.com> y regístrate **con GitHub** (sin tarjeta).
2. **New +** → **Blueprint**.
3. Conecta el repositorio `clima-plataforma`. Render detecta `render.yaml` y
   propone un servicio: `climabot-api` (web).
4. Render pedirá las variables marcadas como secretas:
   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | la URI del Session pooler de Supabase (con tu password) |
   | `TELEGRAM_BOT_TOKEN` | tu token de @BotFather |
   | `TELEGRAM_CHAT_ID` | tu chat id |
   | `FIRMS_MAP_KEY` | *(opcional)* clave de NASA FIRMS |
5. **Apply** → Render construye y despliega.
6. Cuando termine, copia la URL de la API: algo como
   `https://climabot-api.onrender.com`.
   Pruébala: abre `https://climabot-api.onrender.com/api/lugares` → debe devolver JSON.

> **Nota:** el plan free se **duerme** tras 15 min sin tráfico; la primera visita
> luego de dormir tarda ~30-50 s en despertar. Es normal. Lo mismo aplica al bot:
> el primer comando tras un rato tarda en responder (ese POST es el que despierta
> el servicio); los siguientes son instantáneos.

---

## 3. Collector (GitHub Actions)

El recolector corre como workflow programado (ya está en el repo:
`.github/workflows/collector.yml`, cada 20 min). Solo hay que darle los secretos:

1. En GitHub → repo `clima-plataforma` → **Settings** → **Secrets and variables**
   → **Actions** → **New repository secret**. Agrega:
   | Secret | Valor |
   |---|---|
   | `DATABASE_URL` | la misma URI de Supabase |
   | `TELEGRAM_BOT_TOKEN` | tu token |
   | `TELEGRAM_CHAT_ID` | tu chat id |
   | `FIRMS_MAP_KEY` | *(opcional)* |
2. Pestaña **Actions** → workflow **Collector** → **Run workflow** para probarlo
   una vez. Debe terminar en verde y empezar a poblar Supabase.

---

## 4. Vercel (dashboard)

1. Entra a <https://vercel.com> y regístrate **con GitHub** (sin tarjeta).
2. **Add New → Project** → importa `clima-plataforma`.
3. Configura:
   - **Root Directory:** `dashboard-ui`
   - Framework: **Vite** (se detecta solo)
4. En **Environment Variables** agrega:
   | Variable | Valor |
   |---|---|
   | `VITE_API_URL` | la URL de Render, ej. `https://climabot-api.onrender.com` |
5. **Deploy**. Vercel te da la URL pública del dashboard 🎉

---

## 5. Ajustes opcionales

- **Restringir CORS** al dominio de Vercel: en Render, variable
  `CORS_ORIGINS=https://tu-app.vercel.app`.
- **Poblar el historial** para que las gráficas salgan llenas desde el inicio
  (en local, con `DATABASE_URL` de Supabase en tu `.env`):
  ```bash
  python backfill.py --dias 730
  ```
  Escribe ~2 años de clima directo en Supabase.

---

## Cómo encaja

```
Navegador → Vercel (dashboard) --VITE_API_URL--> Render (API) --> Supabase (Postgres)
GitHub Actions (collector, cada 20 min) ───────────────────────> Supabase
Telegram --POST /telegram/webhook--> Render (API, mismo servicio) --> Supabase
```

El código lee `DATABASE_URL` / `VITE_API_URL` del entorno; los secretos viven en
los paneles de Render, Vercel y GitHub (cifrados), nunca en git.
