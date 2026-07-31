#!/usr/bin/env bash
# ── update.sh — Actualiza ClimaBot a la última versión y reinicia los servicios ──
# Uso (desde /home/ubuntu/clima-plataforma):  bash deploy/update.sh
set -euo pipefail

cd /home/ubuntu/clima-plataforma

echo "▶ Trayendo cambios…"
git pull --ff-only

echo "▶ Dependencias de Python…"
./.venv/bin/pip install -r requirements.txt

echo "▶ Recompilando el dashboard…"
npm ci --prefix dashboard-ui
npm run build --prefix dashboard-ui

echo "▶ Reiniciando servicios…"
sudo systemctl restart climabot-api climabot-collector climabot-bot
sudo systemctl reload nginx

echo "✅ Actualizado."
