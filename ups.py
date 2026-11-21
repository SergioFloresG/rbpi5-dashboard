"""Lectura de UPS por NUT (Network UPS Tools): `LIST VAR` al upsd por TCP, sin dependencias.

UPS_NUT acepta una lista separada por comas de `[Etiqueta=]ups[@host[:puerto]]`,
p. ej. `CP1500=cp1500@localhost`.
"""
import logging
import os
import random
import shlex
import socket
import threading
import time
from datetime import datetime

log = logging.getLogger("ups")

NUT = os.environ.get("UPS_NUT", "").strip()
DEMO = os.environ.get("UPS_DEMO", "0").strip() in ("1", "true", "si", "sí")
INTERVALO_SEG = int(os.environ.get("UPS_INTERVALO_SEG", "5"))
TIMEOUT_SEG = 5

ESTADOS = {"OL": "red", "OB": "bateria", "LB": "baja", "HB": "alta", "RB": "reemplazar",
           "CHRG": "cargando", "DISCHRG": "descargando", "BYPASS": "bypass", "CAL": "calibrando",
           "OFF": "apagado", "OVER": "sobrecarga", "TRIM": "avr_reduce", "BOOST": "avr_eleva",
           "FSD": "apagado_forzado"}


def parsear_destinos(texto):
    destinos = []
    for parte in filter(None, (p.strip() for p in texto.split(","))):
        etiqueta, _, ref = parte.rpartition("=")
        nombre, _, servidor = ref.partition("@")
        host, _, puerto = (servidor or "localhost").partition(":")
        destinos.append({"etiqueta": etiqueta.strip() or None, "ups": nombre.strip(),
                         "host": host.strip() or "localhost", "puerto": int(puerto or 3493)})
    return destinos


def parsear_vars(lineas, ups):
    vars_ = {}
    for linea in lineas:
        if linea.startswith("ERR "):
            raise ConnectionError(f"NUT: {linea[4:]}")
        partes = shlex.split(linea)
        if len(partes) == 4 and partes[0] == "VAR" and partes[1] == ups:
            vars_[partes[2]] = partes[3]
    return vars_


def leer_nut(host, puerto, ups):
    with socket.create_connection((host, puerto), timeout=TIMEOUT_SEG) as s:
        s.sendall(f"LIST VAR {ups}\n".encode())
        f = s.makefile("r", encoding="utf-8", errors="replace")
        lineas = []
        for linea in f:
            linea = linea.rstrip("\n")
            if linea.startswith("ERR ") or linea == f"END LIST VAR {ups}":
                lineas.append(linea)
                break
            lineas.append(linea)
        s.sendall(b"LOGOUT\n")
    return parsear_vars(lineas, ups)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def resumir(v):
    banderas = (v.get("ups.status") or "").split()
    carga = _num(v.get("ups.load"))
    nominal = _num(v.get("ups.realpower.nominal"))
    if nominal is None and _num(v.get("ups.power.nominal")) is not None:
        nominal = round(_num(v["ups.power.nominal"]) * 0.6)
    potencia = _num(v.get("ups.realpower"))
    if potencia is None and carga is not None and nominal:
        potencia = round(carga * nominal / 100)
    runtime = _num(v.get("battery.runtime"))
    estado = "bateria" if "OB" in banderas else "red" if "OL" in banderas else "desconocido"
    return {
        "modelo": v.get("device.model") or v.get("ups.model"),
        "fabricante": v.get("device.mfr") or v.get("ups.mfr"),
        "estado": estado,
        "banderas": [ESTADOS.get(b, b.lower()) for b in banderas],
        "soc": _num(v.get("battery.charge")),
        "soc_bajo": _num(v.get("battery.charge.low")),
        "restante_min": round(runtime / 60) if runtime is not None else None,
        "carga_pct": carga,
        "potencia_w": potencia,
        "nominal_w": nominal,
        "v_entrada": _num(v.get("input.voltage")),
        "v_salida": _num(v.get("output.voltage")),
        "v_bateria": _num(v.get("battery.voltage")),
        "v_nominal": _num(v.get("input.voltage.nominal")),
        "prueba": v.get("ups.test.result"),
        "alarma": v.get("ups.beeper.status"),
    }


class Ups:
    def __init__(self):
        self.lock = threading.Lock()
        self.destinos = parsear_destinos(NUT) if not DEMO else [
            {"etiqueta": "CP1500 (demo)", "ups": "demo", "host": "-", "puerto": 0}]
        self.lecturas = {self._id(d): {"vars": {}, "ultimo": 0.0, "error": None, "estado": "conectando"}
                         for d in self.destinos}

    @staticmethod
    def _id(d):
        return f"{d['ups']}@{d['host']}:{d['puerto']}"

    def _guardar(self, d, vars_=None, error=None):
        with self.lock:
            l = self.lecturas[self._id(d)]
            if error:
                l["error"], l["estado"] = error, "desconectado"
            else:
                l["vars"], l["ultimo"], l["error"], l["estado"] = vars_, time.time(), None, "en_linea"

    def _bucle(self):
        while True:
            for d in self.destinos:
                try:
                    self._guardar(d, leer_nut(d["host"], d["puerto"], d["ups"]))
                except Exception as e:
                    if self.lecturas[self._id(d)]["error"] != str(e):
                        log.warning("UPS %s: %s", self._id(d), e)
                    self._guardar(d, error=str(e) or type(e).__name__)
            time.sleep(INTERVALO_SEG)

    def _demo(self):
        t0 = time.time()
        while True:
            m = (time.time() - t0) / 60
            en_bateria = int(m) % 4 == 3
            carga = 21 + random.randint(0, 3)
            soc = 100 - 30 * (m % 1) if en_bateria else 100
            self._guardar(self.destinos[0], {
                "device.mfr": "CPS", "device.model": "CP1500AVRLCDa", "ups.realpower.nominal": "900",
                "ups.status": "OB DISCHRG" if en_bateria else "OL", "ups.load": str(carga),
                "battery.charge": str(round(soc)), "battery.charge.low": "10",
                "battery.runtime": str(round(2400 * soc / 100)), "battery.voltage": "13.5" if en_bateria else "13.6",
                "input.voltage": "0.0" if en_bateria else str(126 + random.randint(0, 3)),
                "output.voltage": "120.0" if en_bateria else "127.0", "input.voltage.nominal": "120",
                "ups.test.result": "No test initiated", "ups.beeper.status": "enabled",
            })
            time.sleep(INTERVALO_SEG)

    def iniciar(self):
        if self.destinos:
            threading.Thread(target=self._demo if DEMO else self._bucle, daemon=True).start()
        return self

    def datos(self):
        with self.lock:
            lecturas = {k: dict(v) for k, v in self.lecturas.items()}
        lista = []
        for d in self.destinos:
            l = lecturas[self._id(d)]
            lista.append({
                "id": self._id(d),
                "etiqueta": d["etiqueta"],
                "estado": l["estado"],
                "error": l["error"],
                "actualizado": datetime.fromtimestamp(l["ultimo"]).isoformat(timespec="seconds") if l["ultimo"] else None,
                "hace_seg": round(time.time() - l["ultimo"]) if l["ultimo"] else None,
                "resumen": resumir(l["vars"]) if l["ultimo"] else None,
                "vars": l["vars"],
            })
        return {"configurado": bool(self.destinos), "demo": DEMO, "ups": lista}
