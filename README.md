# Pi Dashboard

Dashboard a pantalla completa para Raspberry Pi 5 con Ubuntu en modo terminal y un monitor Dell U2913WM (2560x1080).
La pantalla se divide en dos paneles: lado a lado en horizontal (1280x1080 c/u) o apilados si el monitor está girado a vertical (1080x1280 c/u).

- **Panel principal:** radar animado de fondo (2 h pasadas + pronóstico a ~1 h) con línea de tiempo bajo el reloj, reloj, clima, sensación térmica, humedad, viento, índice UV, calidad del aire, visibilidad, presión, sol y luna.
- **Segundo panel:** arriba, tarjetas de la batería EcoFlow Delta 3 Plus, del UPS y de los purificadores Dyson (si están configurados); el resto, por definir.

Fuentes, sin API key: [Open-Meteo](https://open-meteo.com) (clima y calidad del aire), [LibreWXR](https://librewxr.net) (radar, con lluvia estimada por satélite donde no hay radar) y Esri Canvas (mapa base). La luna y el sol se calculan localmente con `astral`.

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
| `DASH_RADAR_CACHE` | Carpeta de la copia local de tiles definitivos del radar (`radar-cache/`); el pronóstico y el cuadro real recién publicado no se guardan. Borrar un archivo fuerza su descarga |
| `DASH_TEMA` | `AUTO` (claro de amanecer a anochecer), `BLACK` o `WHITE` |
| `ECOFLOW_EMAIL`, `ECOFLOW_PASSWORD` | Cuenta de la app EcoFlow para la tarjeta de batería (vacío = tarjeta oculta) |
| `ECOFLOW_SN` | Número de serie de la batería (app EcoFlow > dispositivo > Ajustes > Información) |
| `ECOFLOW_API_HOST` | `api.ecoflow.com` (América/global) o `api-e.ecoflow.com` (Europa) |
| `ECOFLOW_CAPACIDAD_WH` | Capacidad en Wh si la batería no la reporta (1024, Delta 3 Plus) |
| `ECOFLOW_SALIDA_MAX_W` | Salida máxima en W para el % de carga si la batería no la reporta (1800, Delta 3 Plus) |
| `ECOFLOW_DEMO` | `1` muestra datos simulados sin conectarse a EcoFlow |
| `UPS_NUT` | UPS en NUT: `[Etiqueta=]ups[@host[:puerto]]`, separados por comas (vacío = tarjeta oculta) |
| `UPS_INTERVALO_SEG` | Segundos entre lecturas del UPS (5) |
| `UPS_DEMO` | `1` muestra un UPS simulado sin NUT |
| `DYSON_EQUIPOS` | Purificadores Dyson: `[Etiqueta=]serie\|tipo\|credencial[\|host]`, separados por comas (vacío = tarjeta oculta). Lo llena `dyson_login.py` |
| `DYSON_INTERVALO_SEG` | Segundos entre lecturas del purificador (30) |
| `DYSON_DEMO` | `1` muestra un purificador simulado |

Después de cambiarla: `sudo systemctl restart pi-dashboard`.

## Batería EcoFlow

Tarjeta arriba del panel derecho (abajo en vertical) para la Delta 3 / Delta 3 Plus: % de carga, tiempo para lleno o vacío, entrada (Solar 1, Solar 2, AC, batería extra), salida (AC, USB-C, USB-A, 12V, % de carga sobre la salida máxima), salud, ciclos y temperatura. Con batería adicional, el % y los Wh son del conjunto y la salud, ciclos y temperatura se muestran por batería (llegan como heartbeats BMS con `num` 1, 2…).

Usa la misma nube que la app de EcoFlow (no la API de desarrolladores ni Home Assistant): login en `/auth/login`, credenciales MQTT en `/iot-auth/app/certification` y datos en tiempo real por MQTT TLS (`/app/device/property/<SN>`). Los mensajes protobuf se decodifican en `ecoflow.py` con los campos de `ecoflow_campos.py`, tomados de [hassio-ecoflow-cloud](https://github.com/tolwi/hassio-ecoflow-cloud).

`GET /api/bateria` devuelve el `estado` de la conexión, un `resumen` para la tarjeta y todos los `campos` recibidos. Para revisar la conexión: `journalctl -u pi-dashboard -f` y `curl -s localhost:3000/api/bateria`.

Es una API no oficial: EcoFlow puede cambiarla.

## UPS (NUT)

Tarjeta debajo de la batería por cada UPS de `UPS_NUT`: % de carga, autonomía, estado (en red, en batería, cargando, batería baja), consumo en W y % de carga, voltaje de entrada, salida y batería, AVR, prueba y alarma. Los datos vienen de [NUT](https://networkupstools.org) por el puerto 3493 (`LIST VAR`), así que también sirve un UPS conectado a otro equipo con NUT (`sala=cp1000@10.0.1.20`).

Para un UPS por USB a la Pi (p. ej. CyberPower CP1500AVR):

```bash
cd ~/pi-dashboard && ./instalar_ups.sh cp1500
```

Instala `nut-server`, crea `/etc/nut/ups.conf` con `usbhid-ups` (respalda los originales en `*.bak`), deja `upsd` solo en `127.0.0.1`, agrega `UPS_NUT=CP1500=cp1500@localhost` a `config.env` y reinicia el dashboard. Para revisar: `upsc cp1500@localhost` y `curl -s localhost:3000/api/ups`.

## Purificador Dyson

Tarjeta de un tercio del ancho, debajo del UPS, por cada purificador de `DYSON_EQUIPOS`: calidad del aire (el peor nivel entre los contaminantes que mide el equipo), temperatura, humedad, modo y vida del filtro; abajo, una barra por contaminante con los niveles de la app MyDyson. PM2.5 (µg/m³): buena 0-35, aceptable 36-53, mala 54-70, muy mala 71-150, extremadamente mala 151-250, grave 251+. PM10 (µg/m³): 0-50, 51-75, 76-100, 101-350, 351-420, 421+. COV y NO₂ (índice): buena 0-3, aceptable 4-6, mala 7-8, muy mala 9+. Los Pure Cool Link (tipo 475) solo reportan polvo y COV como índice 0-10; se usan con la escala de los gases. Solo se dibujan las barras de los sensores que reporta cada equipo. Los datos se leen directo del equipo por MQTT en la red local (puerto 1883), sin la nube ni Home Assistant.

La credencial local de cada equipo sale de la cuenta Dyson una sola vez:

```bash
cd ~/pi-dashboard && .venv/bin/pip install -r requirements.txt
.venv/bin/python dyson_login.py     # correo, código que llega por correo y contraseña
sudo systemctl restart pi-dashboard
```

`dyson_login.py` usa [libdyson-neon](https://github.com/libdyson-wg/libdyson-neon), busca cada equipo por mDNS y escribe `DYSON_EQUIPOS` en `config.env`; la contraseña no se guarda. Si la IP no queda en `DYSON_EQUIPOS`, el dashboard busca el equipo por mDNS al conectar; conviene fijarle la IP en el router. Para revisar: `curl -s localhost:3000/api/dyson`.

Con el purificador apagado, los sensores solo reportan si el monitoreo continuo está activo en la app MyDyson.

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

- `app.py`: servidor Flask. `GET /api/clima` (caché de 15 min), `GET /api/radar`, `GET /api/config`, `GET /api/bateria`, `GET /api/ups`, `GET /api/dyson`.
- `ecoflow.py`, `ecoflow_campos.py`: cliente de la nube EcoFlow y mapa de campos protobuf de la Delta 3.
- `ups.py`, `instalar_ups.sh`: lector de NUT y configuración de NUT para un UPS por USB.
- `dyson.py`, `dyson_login.py`: lector MQTT local de purificadores Dyson y obtención de la credencial con la cuenta Dyson.
- `static/`: página (`index.html`, `style.css`, `app.js`, `radar.js`, `bateria.js`, `ups.js`, `dyson.js`) y Leaflet local en `vendor/`.
- `tests/`: pruebas del decodificador (`.venv/bin/python -m unittest discover tests`).
- `install.sh`: dependencias, servicio `systemd` y snaps del kiosco.
