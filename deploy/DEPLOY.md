# Despliegue en Oracle Cloud (Always Free)

Guía para poner ClimaBot 24/7 en una VM gratuita de Oracle. Corre todo en una
sola máquina (API + collector + bot + SQLite), sin dormir y sin costo.

La parte de crear la cuenta y la VM la haces tú (Oracle pide verificación con
tarjeta). El resto es un script.

---

## 1. Crear la cuenta y la VM (tu parte)

1. **Cuenta:** regístrate en <https://www.oracle.com/cloud/free/>. Pide una
   tarjeta para verificar identidad — **no cobra** en el tier Always Free.

2. **Crear instancia** (Compute → Instances → Create):
   - **Image:** Canonical **Ubuntu 24.04** (trae Python 3.12; el proyecto necesita 3.11+).
   - **Shape:** `VM.Standard.A1.Flex` (ARM Ampere) — el Always Free da hasta 4
     OCPU y 24 GB gratis. Con 1 OCPU / 6 GB sobra.
     *Si en tu región no hay capacidad ARM, usa `VM.Standard.E2.1.Micro` (AMD, también Always Free).*
   - **SSH keys:** sube tu clave pública (o deja que Oracle genere una y guarda la privada).

3. **Abrir el puerto 80** (el paso que más se olvida):
   Networking → VCN → Security List → **Add Ingress Rule**:
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: TCP · Destination Port: `80` (y `443` si luego quieres HTTPS)

4. Anota la **IP pública** de la instancia.

---

## 2. Instalar la app (una línea)

Conéctate por SSH y corre:

```bash
ssh ubuntu@TU_IP_PUBLICA

git clone https://github.com/Kromilla/clima-plataforma.git
cd clima-plataforma

# Crea el .env con tu token de Telegram (ver .env.example)
nano .env
#   TELEGRAM_BOT_TOKEN=...   (de @BotFather)
#   TELEGRAM_CHAT_ID=...     (o córrelo luego: .venv/bin/python dia1_chatid.py)
#   FIRMS_MAP_KEY=...         (opcional, activa el mapa de incendios)

bash deploy/setup.sh
```

El script instala Python, Node y nginx; compila el dashboard; deja corriendo los
tres servicios con systemd; y configura nginx. Al terminar imprime la URL.

Opcional — historial para el predictor (necesita el `.env` ya creado):

```bash
.venv/bin/python backfill.py --dias 730
```

Abre **http://TU_IP_PUBLICA** 🎉

---

## 3. Operación

```bash
# Ver estado / logs
sudo systemctl status climabot-api climabot-collector climabot-bot
journalctl -u climabot-bot -f          # logs del bot en vivo

# Actualizar a la última versión del repo
bash deploy/update.sh
```

---

## 4. HTTPS con dominio propio (opcional)

Si apuntas un dominio a la IP:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tudominio.com
```

Certbot edita nginx y renueva el certificado solo.

---

## Notas

- **CORS:** no hace falta configurarlo — nginx sirve el frontend y el `/api` en el
  mismo origen.
- **Base de datos:** SQLite en `clima.db`, en el disco de la VM (persistente). No
  hay que migrar a Postgres como sí haría falta en un PaaS efímero.
- **"No carga la página":** casi siempre es el puerto 80 sin abrir en la Security
  List de Oracle (paso 1.3). El firewall del sistema ya lo abre `setup.sh`.
- **Bot y Telegram:** correrlo en la nube evita los cortes intermitentes de
  Telegram que se veían desde una conexión doméstica.
