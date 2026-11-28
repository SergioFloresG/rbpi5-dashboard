import json
import os
import time
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from astral import LocationInfo, moon, sun
from flask import Flask, jsonify, send_from_directory

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


_radar = {"t": 0, "data": None}


@app.get("/api/radar")
def radar():
    ahora = time.time()
    d = _radar["data"]
    # Solo se consulta cuando ya debería existir un cuadro nuevo (uno cada 10 min), y a lo más una vez por minuto.
    if not d or (ahora - d["frames"][-1]["time"] > 600 and ahora - _radar["t"] > 60):
        try:
            _radar["t"] = ahora
            r = _get(RADAR_URL)
            _radar["data"] = {
                "host": r["host"],
                "frames": r["radar"]["past"],
                "nowcast": r["radar"].get("nowcast") or [],
            }
        except Exception as e:
            if not _radar["data"]:
                return jsonify({"error": str(e)}), 502
    return jsonify(_radar["data"])


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
