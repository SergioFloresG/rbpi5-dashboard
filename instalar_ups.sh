#!/usr/bin/env bash
# Configura NUT para un UPS conectado por USB a la Pi (CyberPower, APC, Eaton...).
# Uso: ./instalar_ups.sh [nombre]   (nombre del UPS en NUT, por defecto cp1500)
set -euo pipefail

NOMBRE="${1:-cp1500}"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Paquetes de NUT"
sudo apt-get update
sudo apt-get install -y nut-server nut-client

echo "==> Permisos USB (reglas udev de NUT para el UPS ya conectado)"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --action=add
sudo udevadm settle

echo "==> Configuración en /etc/nut (respaldo en *.bak)"
for f in nut.conf ups.conf upsd.conf; do
  if [ -f "/etc/nut/$f" ] && [ ! -f "/etc/nut/$f.bak" ]; then sudo cp "/etc/nut/$f" "/etc/nut/$f.bak"; fi
done
echo "MODE=standalone" | sudo tee /etc/nut/nut.conf > /dev/null
sudo tee /etc/nut/ups.conf > /dev/null <<CONF
maxretry = 3

[${NOMBRE}]
  driver = usbhid-ups
  port = auto
  pollinterval = 5
  desc = "UPS del dashboard"
CONF
sudo tee /etc/nut/upsd.conf > /dev/null <<CONF
LISTEN 127.0.0.1 3493
CONF

echo "==> Servicios"
sudo systemctl restart nut-driver-enumerator.service || true
sudo upsdrvsvcctl resync 2>/dev/null || true
sudo systemctl restart "nut-driver@${NOMBRE}.service" || sudo upsdrvctl start "${NOMBRE}"
sudo systemctl enable --now nut-server.service
sudo systemctl restart nut-server.service
sleep 3
upsc "${NOMBRE}@localhost" || { echo "NUT no lee el UPS; revisa: journalctl -u nut-driver@${NOMBRE} -n 50"; exit 1; }

if [ -f "$DIR/config.env" ] && ! grep -qE '^UPS_NUT=.+' "$DIR/config.env"; then
  echo "==> Activando la tarjeta en config.env"
  sed -i '/^UPS_NUT=/d' "$DIR/config.env"
  echo "UPS_NUT=CP1500=${NOMBRE}@localhost" >> "$DIR/config.env"
fi
sudo systemctl restart pi-dashboard 2>/dev/null || true
echo "==> Listo: curl -s localhost:3000/api/ups"
