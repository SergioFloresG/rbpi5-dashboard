#!/usr/bin/env bash
# Instala el dashboard en una Raspberry Pi con Ubuntu (sin escritorio).
# Uso: ./install.sh   (como tu usuario normal; pide sudo cuando hace falta)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
USUARIO="$(id -un)"
[ -f "$DIR/config.env" ] || cp "$DIR/config.env.example" "$DIR/config.env"
PUERTO="$(grep -E '^DASH_PORT=' "$DIR/config.env" | cut -d= -f2)"
PUERTO="${PUERTO:-3000}"

echo "==> Paquetes del sistema"
sudo apt-get update
sudo apt-get install -y python3-venv

echo "==> Entorno de Python"
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --upgrade pip
"$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"

echo "==> Kiosco (Ubuntu Frame + navegador WPE)"
sudo snap install ubuntu-frame
sudo snap install wpe-webkit-mir-kiosk
# En Ubuntu clásico la interfaz wayland no se conecta sola
sudo snap connect wpe-webkit-mir-kiosk:wayland || true
sudo /snap/wpe-webkit-mir-kiosk/current/bin/setup.sh || true
sudo snap set ubuntu-frame daemon=true
sudo snap set ubuntu-frame config="cursor=null"
sudo snap set wpe-webkit-mir-kiosk daemon=true url="http://localhost:${PUERTO}"

echo "==> Servicio del dashboard"
sudo tee /etc/systemd/system/pi-dashboard.service > /dev/null <<UNIT
[Unit]
Description=Pi Dashboard
After=network-online.target
Wants=network-online.target

[Service]
User=${USUARIO}
WorkingDirectory=${DIR}
EnvironmentFile=${DIR}/config.env
ExecStart=${DIR}/.venv/bin/python ${DIR}/app.py
ExecStartPost=+/bin/sh -c 'sleep 3; snap restart wpe-webkit-mir-kiosk || true'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now pi-dashboard.service

echo "==> Listo. El dashboard está en http://localhost:${PUERTO} y en pantalla."
