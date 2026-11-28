import json
import os
import re
import shutil
import time
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from astral import LocationInfo, moon, sun
from flask import Flask, Response, abort, jsonify, send_file, send_from_directory

from dyson import Dyson
from ecoflow import EcoFlow
from ups import Ups

LAT = float(os.environ.get("DASH_LAT", "21.1619"))
LON = float(os.environ.get("DASH_LON", "-86.8515"))
TZ = os.environ.get("DASH_TZ", "America/Cancun")
CIUDAD = os.environ.get("DASH_CIUDAD", "Cancún")
CACHE_SEG = int(os.environ.get("DASH_CACHE_SEG", "900"))
RADAR_ZOOM = int(os.environ.get("DASH_RADAR_ZOOM", "7"))
TEMA = {"BLACK": "BLACK", "DARK": "BLACK", "WHITE": "WHITE", "LIGHT": "WHITE"}.get(
    os.environ.get("DASH_TEMA", "AUTO").strip().upper(), "AUTO")
RADAR_URL = os.environ.get("DASH_RADAR_URL", "https://api.librewxr.net/public/weather-maps.json")
RADAR_CACHE = os.environ.get("DASH_RADAR_CACHE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "radar-cache")

FORECAST = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
    "wind_speed_10m,wind_direction_10m,wind_gusts_10m,visibility,uv_index,"
    "pressure_msl,weather_code,is_day"
    "&daily=sunrise,sunset,uv_index_max,temperature_2m_max,temperature_2m_min,"
    "weather_code,precipitation_probability_max"
    "&hourly=temperature_2m,precipitation_probability,precipitation,weather_code,is_day"
    "&timezone={tz}&forecast_days=5&forecast_hours=8"
)
AIRE = (
    "https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}"
    "&longitude={lon}&current=us_aqi,pm2_5,pm10&timezone={tz}"
)

app = Flask(__name__, static_folder="static")
_cache = {"t": 0, "data": None}
bateria = EcoFlow().iniciar()
ups = Ups().iniciar()
dyson = Dyson().iniciar()


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pi-dashboard"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _luna(hoy, tz):
    obs = LocationInfo(CIUDAD, "", TZ, LAT, LON).observer
    edad = moon.phase(hoy)

    def hora(fn):
        for dias in (0, 1):
            try:
                t = fn(obs, hoy + timedelta(days=dias), tzinfo=tz)
            except ValueError:
                t = None
            if t:
                return {"hora": t.strftime("%H:%M"), "manana": bool(dias)}
        return None

    return {
        "edad": round(edad, 1),
        "ciclo": round(edad / 27.99, 3),
        "salida": hora(moon.moonrise),
        "puesta": hora(moon.moonset),
    }


def _datos():
    params = {"lat": LAT, "lon": LON, "tz": TZ}
    f = _get(FORECAST.format(**params))
    try:
        a = _get(AIRE.format(**params))["current"]
    except Exception:
        a = {}
    tz = ZoneInfo(TZ)
    c, d, h = f["current"], f["daily"], f["hourly"]
    return {
        "ciudad": CIUDAD,
        "zona": TZ,
        "actualizado": datetime.now(tz).isoformat(timespec="minutes"),
        "actual": {
            "temp": c["temperature_2m"],
            "sensacion": c["apparent_temperature"],
            "humedad": c["relative_humidity_2m"],
            "viento": c["wind_speed_10m"],
            "viento_dir": c["wind_direction_10m"],
            "rafagas": c["wind_gusts_10m"],
            "visibilidad_km": round(c["visibility"] / 1000, 1),
            "uv": c["uv_index"],
            "presion": c["pressure_msl"],
            "codigo": c["weather_code"],
            "es_dia": bool(c["is_day"]),
        },
        "hoy": {
            "max": d["temperature_2m_max"][0],
            "min": d["temperature_2m_min"][0],
            "uv_max": d["uv_index_max"][0],
            "amanecer": d["sunrise"][0][-5:],
            "anochecer": d["sunset"][0][-5:],
        },
        "aire": {
            "aqi": a.get("us_aqi"),
            "pm2_5": a.get("pm2_5"),
            "pm10": a.get("pm10"),
        },
        "horas": [
            {
                "hora": t,
                "temp": h["temperature_2m"][i],
                "lluvia_prob": h["precipitation_probability"][i],
                "lluvia_mm": h["precipitation"][i],
                "codigo": h["weather_code"][i],
                "es_dia": bool(h["is_day"][i]),
            }
            for i, t in enumerate(h["time"])
        ],
        "dias": [
            {
                "fecha": t,
                "max": d["temperature_2m_max"][i],
                "min": d["temperature_2m_min"][i],
                "lluvia_prob": d["precipitation_probability_max"][i],
                "codigo": d["weather_code"][i],
            }
            for i, t in enumerate(d["time"]) if i
        ],
        "luna": _luna(date.fromisoformat(d["time"][0]), tz),
    }


@app.get("/api/config")
def config():
    tz = ZoneInfo(TZ)
    try:
        s = sun.sun(LocationInfo(CIUDAD, "", TZ, LAT, LON).observer,
                    date=datetime.now(tz).date(), tzinfo=tz)
        sol = {"amanecer": s["sunrise"].strftime("%H:%M"),
               "anochecer": s["sunset"].strftime("%H:%M")}
    except ValueError:
        sol = None
    return jsonify({"ciudad": CIUDAD, "zona": TZ, "lat": LAT, "lon": LON,
                    "radar_zoom": RADAR_ZOOM, "tema": TEMA, "sol": sol})


@app.get("/api/clima")
def clima():
    if not _cache["data"] or time.time() - _cache["t"] > CACHE_SEG:
        try:
            _cache["data"] = _datos()
            _cache["t"] = time.time()
        except Exception as e:
            if not _cache["data"]:
                return jsonify({"error": str(e)}), 502
    return jsonify(_cache["data"])


_radar = {"t": 0, "data": None, "visto": 0, "fuente": None, "sondeo": 0, "provisionales": set()}
# Tras publicarse un cuadro real, la fuente sigue entregando un rato tiles del pronóstico anterior;
# pedirlos en ese lapso mezcla dos pronósticos (cortes rectos). Mientras, se conserva el anterior.
PRON_ESPERA_SEG = 120
# La fuente marca los tiles definitivos con un max-age largo; el pronóstico y el cuadro real recién
# publicado llevan uno corto y son provisionales: no se guardan en disco.
FIRME_MAX_AGE = 7200
PROVISIONAL_MAX_SEG = 1800


def _tile(url):
    """Descarga un tile; devuelve (bytes, es_definitivo)."""
    req = urllib.request.Request(url, headers={"User-Agent": "pi-dashboard"})
    with urllib.request.urlopen(req, timeout=15) as r:
        m = re.search(r"max-age=(\d+)", r.headers.get("Cache-Control") or "")
        return r.read(), bool(m) and int(m.group(1)) >= FIRME_MAX_AGE


def _radar_limpiar(d):
    vigentes = {str(f["time"]) for f in d["frames"]}
    base = os.path.join(RADAR_CACHE, "real")
    if os.path.isdir(base):
        for nombre in os.listdir(base):
            if nombre not in vigentes:
                shutil.rmtree(os.path.join(base, nombre), ignore_errors=True)
    shutil.rmtree(os.path.join(RADAR_CACHE, "pron"), ignore_errors=True)


def _radar_armar(r, previo, visto, ahora, provisionales=()):
    """Combina la lista de la fuente con el pronóstico vigente: el nuevo se adopta cuando ya es estable."""
    corte = r["radar"]["past"][-1]["time"]
    if ahora - visto >= PRON_ESPERA_SEG:
        pron = [{"time": f["time"], "path": f["path"], "g": corte} for f in r["radar"].get("nowcast") or []]
    else:
        pron = [f for f in (previo or {}).get("nowcast", []) if f["time"] > corte]
    reales = [{"time": f["time"], "path": f["path"], "firme": f["time"] not in provisionales}
              for f in r["radar"]["past"]]
    return {"host": r["host"], "frames": reales, "nowcast": pron}


def _radar_sondear(r, ahora):
    """Revisa (un tile por cuadro) si los cuadros reales provisionales ya son definitivos."""
    prov = _radar["provisionales"]
    rutas = {f["time"]: f["path"] for f in r["radar"]["past"]}
    prov.intersection_update(t for t in rutas if ahora - t < PROVISIONAL_MAX_SEG)
    for t in sorted(prov):
        try:
            if _tile(f"{r['host']}{rutas[t]}/256/0/0/0/2/1_1.png?p={time.time_ns()}")[1]:
                prov.discard(t)
        except Exception:
            pass


def _radar_datos():
    ahora = time.time()
    d = _radar["data"]
    # Solo se consulta cuando ya debería existir un cuadro nuevo (uno cada 10 min), y a lo más una vez por minuto.
    if not d or (ahora - d["frames"][-1]["time"] > 600 and ahora - _radar["t"] > 60):
        _radar["t"] = ahora
        try:
            r = _get(RADAR_URL)
            corte = r["radar"]["past"][-1]["time"]
            if not d or corte != d["frames"][-1]["time"]:
                # Al arrancar no se sabe cuándo se publicó: solo un cuadro reciente obliga a esperar.
                reciente = d or ahora - corte < 300
                _radar["visto"] = ahora if reciente else 0
                _radar["provisionales"].add(corte)
                _radar["sondeo"] = 0
            _radar["fuente"] = r
        except Exception:
            if not d:
                raise
    r = _radar["fuente"]
    if r:
        if _radar["provisionales"] and ahora - _radar["sondeo"] > 60:
            _radar["sondeo"] = ahora
            _radar_sondear(r, ahora)
        nuevo = _radar_armar(r, d, _radar["visto"], ahora, _radar["provisionales"])
        if nuevo != d:
            _radar["data"] = nuevo
            _radar_limpiar(nuevo)
    return _radar["data"]


@app.get("/api/radar")
def radar():
    try:
        return jsonify(_radar_datos())
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/radar/tile/<int:t>/<int:z>/<int:x>/<int:y>.png")
def radar_tile(t, z, x, y):
    """Tile del radar. Los definitivos tienen copia local: se descargan una vez y después se sirven
    del archivo (si se borra, se vuelve a descargar). Los provisionales siempre se piden a la fuente."""
    try:
        d = _radar_datos()
    except Exception:
        abort(502)
    real = next((f for f in d["frames"] if f["time"] == t), None)
    cuadro = real or next((f for f in d["nowcast"] if f["time"] == t), None)
    if not cuadro:
        abort(404)
    archivo = os.path.join(RADAR_CACHE, "real", str(t), f"{z}-{x}-{y}.png")
    firme = bool(real and real["firme"])
    if firme and os.path.isfile(archivo):
        return send_file(archivo, mimetype="image/png", max_age=0)
    # Los provisionales llevan una query única para saltar la caché de 5 min de la fuente.
    q = "?r=1" if firme else f"?p={time.time_ns()}"
    try:
        datos, definitivo = _tile(f"{d['host']}{cuadro['path']}/256/{z}/{x}/{y}/2/1_1.png{q}")
    except Exception:
        abort(502)
    if firme and definitivo:
        os.makedirs(os.path.dirname(archivo), exist_ok=True)
        tmp = f"{archivo}.{os.getpid()}.{time.time_ns()}.tmp"
        with open(tmp, "wb") as f:
            f.write(datos)
        os.replace(tmp, archivo)
    return Response(datos, mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/bateria")
def api_bateria():
    return jsonify(bateria.datos())


@app.get("/api/ups")
def api_ups():
    return jsonify(ups.datos())


@app.get("/api/dyson")
def api_dyson():
    return jsonify(dyson.datos())


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    app.run(host=os.environ.get("DASH_HOST", "127.0.0.1"),
            port=int(os.environ.get("DASH_PORT", "3000")))
