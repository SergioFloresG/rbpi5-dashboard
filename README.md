# Pi Dashboard

Dashboard a pantalla completa para Raspberry Pi 5 con Ubuntu en modo terminal y un monitor Dell U2913WM (2560x1080).
La pantalla se divide en dos paneles: lado a lado en horizontal (1280x1080 c/u) o apilados si el monitor está girado a vertical (1080x1280 c/u).

- **Panel principal:** radar animado de fondo, reloj, clima, sensación térmica, humedad, viento, índice UV, calidad del aire, visibilidad, presión, sol y luna.
- **Segundo panel:** por definir (siempre en negro).

Fuentes, sin API key: [Open-Meteo](https://open-meteo.com) (clima y calidad del aire), [RainViewer](https://www.rainviewer.com/api.html) (radar) y Esri Canvas (mapa base). La luna y el sol se calculan localmente con `astral`.

## Instalación en la Pi

```bash
git clone https://github.com/SergioFloresG/rbpi5-dashboard.git ~/pi-dashboard
cd ~/pi-dashboard
cp config.env.example config.env
nano config.env                    # ciudad, coordenadas, zona horaria, tema
./install.sh
sudo reboot
```

Al encender, la Pi arranca el servidor (`pi-dashboard.service`) y el kiosco (Ubuntu Frame + WPE) muestra `http://localhost:3000`.

## Actualizar

```bash
cd ~/pi-dashboard && git pull
sudo systemctl restart pi-dashboard
```

`config.env` no está en git, así que `git pull` no toca tu configuración.

## Configuración (`config.env`)

| Variable | Uso |
|---|---|
| `DASH_CIUDAD`, `DASH_LAT`, `DASH_LON`, `DASH_TZ` | Ubicación para clima, sol y luna |
| `DASH_HOST` | `127.0.0.1` solo la Pi; `0.0.0.0` accesible desde la LAN |
| `DASH_PORT` | Puerto (3000) |
| `DASH_CACHE_SEG` | Segundos de caché del clima (900) |
| `DASH_RADAR_ZOOM` | Zoom del radar (máx. 7) |
| `DASH_TEMA` | `AUTO` (claro de amanecer a anochecer), `BLACK` o `WHITE` |

Después de cambiarla: `sudo systemctl restart pi-dashboard`.

## Pantalla

| Acción | Comando |
|---|---|
| Ocultar el cursor | `sudo snap set ubuntu-frame config="cursor=null"` |
| Girar a vertical | `snap get ubuntu-frame display > d.yaml`, cambiar `orientation: normal` por `left` y `sudo snap set ubuntu-frame display="$(cat d.yaml)"` |
| Si el kiosco no arranca (Ubuntu clásico) | `sudo snap connect wpe-webkit-mir-kiosk:wayland && sudo /snap/wpe-webkit-mir-kiosk/current/bin/setup.sh` |

Tras cambiar Ubuntu Frame: `sudo snap restart ubuntu-frame && sudo snap restart wpe-webkit-mir-kiosk`.

## Comandos útiles

| Acción | Comando |
|---|---|
| Ver logs del servidor | `journalctl -u pi-dashboard -f` |
| Reiniciar servidor | `sudo systemctl restart pi-dashboard` |
| Recargar la pantalla | `sudo snap restart wpe-webkit-mir-kiosk` |
| Volver a la terminal | `sudo snap stop --disable wpe-webkit-mir-kiosk ubuntu-frame` |
| Probar en otra PC | `.venv/bin/python app.py` y abrir `http://localhost:3000` |

## Estructura

- `app.py`: servidor Flask. `GET /api/clima` (caché de 15 min), `GET /api/radar`, `GET /api/config`.
- `static/`: página (`index.html`, `style.css`, `app.js`, `radar.js`) y Leaflet local en `vendor/`.
- `install.sh`: dependencias, servicio `systemd` y snaps del kiosco.
