"""Lectura local de purificadores Dyson por MQTT (puerto 1883 del propio equipo).

DYSON_EQUIPOS acepta una lista separada por comas de `[Etiqueta=]serie|tipo|credencial[|host]`,
p. ej. `Sala=X3X-MX-ABC1234A|527K|credencial|10.0.1.40`. `dyson_login.py` la genera con la
cuenta Dyson. Sin host, el equipo se busca por mDNS.
"""
import json
import logging
import os
import random
import threading
import time
from datetime import datetime

log = logging.getLogger("dyson")

EQUIPOS = os.environ.get("DYSON_EQUIPOS", "").strip()
DEMO = os.environ.get("DYSON_DEMO", "0").strip() in ("1", "true", "si", "sí")
INTERVALO_SEG = int(os.environ.get("DYSON_INTERVALO_SEG", "30"))
PUERTO = 1883
MDNS = "_dyson_mqtt._tcp.local."
SIN_CONEXION_MAX = 6

# Límite superior de cada nivel (1 buena, 2 aceptable, 3 mala; arriba de eso, 4 muy mala)
NIVELES = {"pm2_5": (35, 53, 70), "pm10": (50, 75, 100), "cov": (3, 6, 8), "no2": (3, 6, 8)}


def parsear_equipos(texto):
    equipos = []
    for parte in filter(None, (p.strip() for p in texto.split(","))):
        cabeza, barra, resto = parte.partition("|")
        etiqueta, _, serie = cabeza.rpartition("=")
        campos = [c.strip() for c in resto.split("|")] if barra else []
        if len(campos) < 2 or not serie.strip() or not all(campos[:2]):
            raise ValueError("DYSON_EQUIPOS: se esperaba [Etiqueta=]serie|tipo|credencial[|host]")
        equipos.append({"etiqueta": etiqueta.strip() or None, "serie": serie.strip(), "tipo": campos[0],
                        "credencial": campos[1], "host": campos[2] if len(campos) > 2 and campos[2] else None})
    return equipos


def _valor(datos, campo):
    v = datos.get(campo)
    return v[1] if isinstance(v, list) and len(v) > 1 else v


def _num(datos, campo, divisor=1):
    try:
        return float(_valor(datos, campo)) / divisor
    except (TypeError, ValueError):
        return None


def nivel(campo, v):
    if v is None:
        return None
    return next((i for i, tope in enumerate(NIVELES[campo], 1) if v <= tope), 4)


def resumir(estado, ambiente):
    def primero(*campos):
        return next((v for v in (_num(ambiente, c) for c in campos) if v is not None), None)

    kelvin = _num(ambiente, "tact", 10)
    r = {
        "pm2_5": primero("p25r", "pm25"),
        "pm10": primero("p10r", "pm10"),
        "cov": _num(ambiente, "va10", 10),
        "no2": _num(ambiente, "noxl", 10),
        "temp": round(kelvin - 273.15, 1) if kelvin is not None else None,
        "humedad": _num(ambiente, "hact"),
        "hcho": _num(ambiente, "hchr", 1000),
    }
    r["niveles"] = {c: nivel(c, r[c]) for c in NIVELES}
    r["calidad"] = max(filter(None, r["niveles"].values()), default=None)
    r.update({
        "encendido": _valor(estado, "fpwr") == "ON",
        "auto": _valor(estado, "auto") == "ON",
        "noche": _valor(estado, "nmod") == "ON",
        "calor": _valor(estado, "hmod") == "HEAT",
        "monitoreo": _valor(estado, "rhtm") == "ON",
        "filtro_hepa": _num(estado, "hflr"),
        "filtro_carbon": _num(estado, "cflr"),
    })
    return r


def descubrir(serie, espera_seg=8):
    """Busca por mDNS el equipo con ese número de serie; devuelve (ip, tipo MQTT)."""
    import socket

    from zeroconf import ServiceBrowser, Zeroconf

    hallado = threading.Event()
    ip = []

    class Escucha:
        def add_service(self, zc, tipo, nombre):
            modelo, _, sn = nombre.split(".")[0].partition("_")
            if sn != serie:
                return
            info = zc.get_service_info(tipo, nombre)
            if info and info.addresses:
                ip.append((socket.inet_ntoa(info.addresses[0]), modelo))
                hallado.set()

        update_service = add_service

        def remove_service(self, *_):
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, MDNS, Escucha())
        hallado.wait(espera_seg)
    finally:
        zc.close()
    if not ip:
        raise ConnectionError(f"no se encontró {serie} en la red (mDNS)")
    return ip[0]


class Dyson:
    def __init__(self):
        self.lock = threading.Lock()
        self.error_config = None
        try:
            self.equipos = parsear_equipos(EQUIPOS) if not DEMO else [
                {"etiqueta": "Sala (demo)", "serie": "demo", "tipo": "527K", "credencial": "", "host": None}]
        except ValueError as e:
            log.error("%s", e)
            self.equipos, self.error_config = [], str(e)
        self.lecturas = {e["serie"]: {"estado_equipo": {}, "ambiente": {}, "ultimo": 0.0, "error": None,
                                      "estado": "conectando"} for e in self.equipos}

    def _set(self, e, estado, error=None):
        with self.lock:
            l = self.lecturas[e["serie"]]
            if error and l["error"] != error:
                log.warning("Dyson %s: %s", e["serie"], error)
            l["estado"], l["error"] = estado, error

    def recibir(self, e, payload):
        try:
            m = json.loads(payload)
        except ValueError:
            return
        if not isinstance(m, dict):
            return
        with self.lock:
            l = self.lecturas[e["serie"]]
            if m.get("msg") == "ENVIRONMENTAL-CURRENT-SENSOR-DATA" and isinstance(m.get("data"), dict):
                l["ambiente"], l["ultimo"] = m["data"], time.time()
            elif m.get("msg") in ("CURRENT-STATE", "STATE-CHANGE") and isinstance(m.get("product-state"), dict):
                l["estado_equipo"].update(m["product-state"])

    def _cliente(self, e):
        import paho.mqtt.client as mqtt

        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv31)
        cli.username_pw_set(e["serie"], e["credencial"])
        cli.reconnect_delay_set(5, 60)
        orden = f"{e['tipo']}/{e['serie']}/command"

        def pedir():
            for msg in ("REQUEST-CURRENT-STATE", "REQUEST-PRODUCT-ENVIRONMENT-CURRENT-SENSOR-DATA"):
                cli.publish(orden, json.dumps({"msg": msg, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))

        def on_connect(c, _u, _f, rc, _p):
            if rc.is_failure:
                self._set(e, "rechazado" if rc.value in (4, 5, 134, 135) else "desconectado", f"MQTT: {rc}")
                return
            c.subscribe(f"{e['tipo']}/{e['serie']}/status/current")
            self._set(e, "en_linea")
            pedir()

        def on_disconnect(_c, _u, _f, rc, _p):
            with self.lock:
                rechazado = self.lecturas[e["serie"]]["estado"] == "rechazado"
            if not rechazado:
                self._set(e, "desconectado", f"MQTT: {rc}")

        cli.on_connect, cli.on_disconnect = on_connect, on_disconnect
        cli.on_message = lambda _c, _u, msg: self.recibir(e, msg.payload)
        return cli, pedir

    def _bucle(self, e):
        while True:
            cli = None
            try:
                host = e["host"] or descubrir(e["serie"])[0]
                cli, pedir = self._cliente(e)
                cli.connect(host, PUERTO, keepalive=30)
                cli.loop_start()
                fallos = 0
                while fallos < SIN_CONEXION_MAX:
                    time.sleep(INTERVALO_SEG)
                    if cli.is_connected():
                        fallos = 0
                        pedir()
                    else:
                        fallos += 1
            except Exception as ex:
                self._set(e, "desconectado", str(ex) or type(ex).__name__)
            finally:
                if cli:
                    cli.loop_stop()
                    cli.disconnect()
            time.sleep(10)

    def _demo(self):
        e = self.equipos[0]
        self._set(e, "en_linea")
        t0 = time.time()
        while True:
            pico = 60 if int((time.time() - t0) / 60) % 3 == 2 else 0
            self.recibir(e, json.dumps({"msg": "CURRENT-STATE", "product-state": {
                "fpwr": "ON", "auto": "ON", "nmod": "OFF", "hmod": "OFF", "rhtm": "ON", "hflr": "0087", "cflr": "INV"}}))
            self.recibir(e, json.dumps({"msg": "ENVIRONMENTAL-CURRENT-SENSOR-DATA", "data": {
                "tact": str(2981 + random.randint(0, 6)), "hact": f"{58 + random.randint(0, 3):04d}",
                "pm25": f"{6 + pico + random.randint(0, 3):04d}", "pm10": f"{9 + pico + random.randint(0, 3):04d}",
                "va10": f"{10 + random.randint(0, 6):04d}", "noxl": f"{4 + random.randint(0, 2):04d}",
                "p25r": f"{6 + pico + random.randint(0, 3):04d}", "p10r": f"{9 + pico + random.randint(0, 3):04d}",
                "sltm": "OFF"}}))
            time.sleep(5)

    def iniciar(self):
        if DEMO:
            threading.Thread(target=self._demo, daemon=True).start()
        else:
            for e in self.equipos:
                threading.Thread(target=self._bucle, args=(e,), daemon=True).start()
        return self

    def datos(self):
        with self.lock:
            lecturas = {k: {**v, "estado_equipo": dict(v["estado_equipo"])} for k, v in self.lecturas.items()}
        lista = []
        for e in self.equipos:
            l = lecturas[e["serie"]]
            lista.append({
                "id": e["serie"],
                "etiqueta": e["etiqueta"],
                "tipo": e["tipo"],
                "estado": l["estado"],
                "error": l["error"],
                "actualizado": datetime.fromtimestamp(l["ultimo"]).isoformat(timespec="seconds") if l["ultimo"] else None,
                "hace_seg": round(time.time() - l["ultimo"]) if l["ultimo"] else None,
                "resumen": resumir(l["estado_equipo"], l["ambiente"]) if l["ultimo"] else None,
                "ambiente": l["ambiente"],
                "estado_equipo": l["estado_equipo"],
            })
        return {"configurado": bool(self.equipos) or bool(self.error_config), "demo": DEMO,
                "error": self.error_config, "equipos": lista}
