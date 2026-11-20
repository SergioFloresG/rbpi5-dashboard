# Pi Dashboard

Dashboard a pantalla completa para Raspberry Pi 5 con Ubuntu en modo terminal y un monitor Dell U2913WM (2560x1080).
La pantalla se divide en dos paneles: lado a lado en horizontal (1280x1080 c/u) o apilados si el monitor está girado a vertical (1080x1280 c/u).

- **Panel principal:** radar animado de fondo, reloj, clima, sensación térmica, humedad, viento, índice UV, calidad del aire, visibilidad, presión, sol y luna.
- **Segundo panel:** arriba, tarjeta de la batería EcoFlow Delta 3 Plus (si está configurada); el resto, por definir.

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
.venv/bin/pip install -r requirements.txt
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
| `ECOFLOW_EMAIL`, `ECOFLOW_PASSWORD` | Cuenta de la app EcoFlow para la tarjeta de batería (vacío = tarjeta oculta) |
| `ECOFLOW_SN` | Número de serie de la batería (app EcoFlow > dispositivo > Ajustes > Información) |
| `ECOFLOW_API_HOST` | `api.ecoflow.com` (América/global) o `api-e.ecoflow.com` (Europa) |
| `ECOFLOW_CAPACIDAD_WH` | Capacidad en Wh si la batería no la reporta (1024, Delta 3 Plus) |
| `ECOFLOW_DEMO` | `1` muestra datos simulados sin conectarse a EcoFlow |

Después de cambiarla: `sudo systemctl restart pi-dashboard`.

## Batería EcoFlow

Tarjeta arriba del panel derecho (abajo en vertical) para la Delta 3 / Delta 3 Plus: % de carga, tiempo para lleno o vacío, entrada (Solar 1, Solar 2, AC, batería extra), salida (AC, USB-C, USB-A, 12V), salud, ciclos y temperatura. Con batería adicional, el % y los Wh son del conjunto y la salud, ciclos y temperatura se muestran por batería (llegan como heartbeats BMS con `num` 1, 2…).

Usa la misma nube que la app de EcoFlow (no la API de desarrolladores ni Home Assistant): login en `/auth/login`, credenciales MQTT en `/iot-auth/app/certification` y datos en tiempo real por MQTT TLS (`/app/device/property/<SN>`). Los mensajes protobuf se decodifican en `ecoflow.py` con los campos de `ecoflow_campos.py`, tomados de [hassio-ecoflow-cloud](https://github.com/tolwi/hassio-ecoflow-cloud).

`GET /api/bateria` devuelve el `estado` de la conexión, un `resumen` para la tarjeta y todos los `campos` recibidos. Para revisar la conexión: `journalctl -u pi-dashboard -f` y `curl -s localhost:3000/api/bateria`.

Es una API no oficial: EcoFlow puede cambiarla.

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

- `app.py`: servidor Flask. `GET /api/clima` (caché de 15 min), `GET /api/radar`, `GET /api/config`, `GET /api/bateria`.
- `ecoflow.py`, `ecoflow_campos.py`: cliente de la nube EcoFlow y mapa de campos protobuf de la Delta 3.
- `static/`: página (`index.html`, `style.css`, `app.js`, `radar.js`, `bateria.js`) y Leaflet local en `vendor/`.
- `tests/`: pruebas del decodificador (`.venv/bin/python -m unittest tests/test_ecoflow.py`).
- `install.sh`: dependencias, servicio `systemd` y snaps del kiosco.
