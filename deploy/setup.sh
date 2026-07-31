#!/usr/bin/env bash
# ── setup.sh — Instalación de ClimaBot en una VM Ubuntu (Oracle Cloud Free) ──
#
# Uso (desde la raíz del repo, como usuario 'ubuntu'):
#   bash deploy/setup.sh
#
# Requisitos previos:
#   - Ubuntu 24.04 (trae Python 3.12; el proyecto necesita 3.11+).
#   - El repo clonado en /home/ubuntu/clima-plataforma
#   - Un archivo .env creado (ver DEPLOY.md). El bot lo necesita para arrancar.
set -euo pipefail

APP_DIR="/home/ubuntu/clima-plataforma"
cd "$APP_DIR"

echo "▶ 1/7  Paquetes del sistema…"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip nginx git curl

echo "▶ 2/7  Node.js 20…"
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

echo "▶ 3/7  Entorno de Python…"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "▶ 4/7  Compilando el dashboard…"
npm ci --prefix dashboard-ui
npm run build --prefix dashboard-ui

if [ ! -f "$APP_DIR/.env" ]; then
  echo "✋ Falta $APP_DIR/.env — créalo antes de continuar (ver deploy/DEPLOY.md)."
  echo "   Los servicios se instalarán pero el bot no arrancará sin él."
fi

echo "▶ 5/7  Servicios systemd…"
sudo cp deploy/systemd/climabot-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now climabot-api climabot-collector climabot-bot

echo "▶ 6/7  nginx…"
sudo cp deploy/nginx-climabot.conf /etc/nginx/sites-available/climabot
sudo ln -sf /etc/nginx/sites-available/climabot /etc/nginx/sites-enabled/climabot
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "▶ 7/7  Firewall del sistema (puerto 80)…"
# Las imágenes de Oracle traen iptables restrictivo. Esto NO reemplaza abrir el
# puerto 80 en la Security List de la consola de Oracle (ver DEPLOY.md).
if ! sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT || true
  sudo netfilter-persistent save 2>/dev/null || sudo bash -c 'iptables-save > /etc/iptables/rules.v4' 2>/dev/null || true
fi

echo
echo "✅ Listo. Estado de los servicios:"
sudo systemctl --no-pager --lines=0 status climabot-api climabot-collector climabot-bot | grep -E "climabot|Active" || true
echo
echo "→ Abre  http://$(curl -s ifconfig.me 2>/dev/null || echo TU_IP_PUBLICA)"
echo "→ Si no carga, revisa que el puerto 80 esté abierto en la Security List de Oracle."
