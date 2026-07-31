# Despliegue gratis (Vercel + Render + Supabase)

Pone ClimaBot en línea sin tarjeta de crédito. Tres piezas:

| Pieza | Dónde | Qué corre |
|---|---|---|
| Base de datos | **Supabase** | Postgres (historial + config) |
| API + collector | **Render** | FastAPI (web) + collector (cron cada 15 min) |
| Dashboard | **Vercel** | React estático |

> El bot de Telegram no se despliega aquí (los workers 24/7 de Render son de pago).
> Corre local, o migra a webhooks más adelante. La alternativa "todo en una VM
> 24/7" está en [`DEPLOY_oracle.md`](DEPLOY_oracle.md).

---

## 1. Supabase (base de datos) ✅

Ya creado. Solo necesitas la cadena de conexión:

- Supabase → **Connect** → **Session pooler** → copia la URI.
- Reemplaza `[YOUR-PASSWORD]` por la contraseña de la BD (sin corchetes).
- Esa es tu `DATABASE_URL`. Úsala tal cual en Render (paso 2).

---

## 2. Render (API + collector)

1. Entra a <https://render.com> y regístrate **con GitHub** (sin tarjeta).
2. **New +** → **Blueprint**.
3. Conecta el repositorio `clima-plataforma`. Render detecta `render.yaml` y
   propone dos servicios: `climabot-api` (web) y `climabot-collector` (cron).
4. Render pedirá las variables marcadas como secretas. Ponlas en **ambos**
   servicios:
   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | la URI del Session pooler de Supabase |
   | `TELEGRAM_BOT_TOKEN` | tu token de @BotFather |
   | `TELEGRAM_CHAT_ID` | tu chat id |
   | `FIRMS_MAP_KEY` | *(opcional)* clave de NASA FIRMS |
5. **Apply** → Render construye y despliega.
6. Cuando termine, copia la URL de la API: algo como
   `https://climabot-api.onrender.com`.
   Pruébala: abre `https://climabot-api.onrender.com/api/lugares` → debe devolver JSON.

> **Nota:** el plan free de la API se **duerme** tras 15 min sin tráfico; la
> primera visita luego de dormir tarda ~30-50 s en despertar. Es normal.

---

## 3. Vercel (dashboard)

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

## 4. Ajustes opcionales

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
Navegador → Vercel (dashboard)  --VITE_API_URL-->  Render (API)  -->  Supabase (Postgres)
                                                    Render (cron collector) --> Supabase
```

El código lee `DATABASE_URL` / `VITE_API_URL` del entorno; los secretos viven en
los paneles de Render y Vercel (cifrados), nunca en git.
