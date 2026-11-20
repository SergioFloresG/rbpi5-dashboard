"""Lectura de una EcoFlow Delta 3 / 3 Plus por la nube de EcoFlow (misma API que la app).

Flujo: POST /auth/login -> GET /iot-auth/app/certification -> MQTT TLS.
Los mensajes llegan en protobuf; se decodifican aquí sin depender de `protobuf`.
"""
import base64
import json
import logging
import os
import random
import ssl
import struct
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime

from ecoflow_campos import MENSAJES

log = logging.getLogger("ecoflow")

EMAIL = os.environ.get("ECOFLOW_EMAIL", "").strip()
PASSWORD = os.environ.get("ECOFLOW_PASSWORD", "")
SN = os.environ.get("ECOFLOW_SN", "").strip()
API_HOST = os.environ.get("ECOFLOW_API_HOST", "api.ecoflow.com").strip()
CAPACIDAD_WH = float(os.environ.get("ECOFLOW_CAPACIDAD_WH", "1024"))
DEMO = os.environ.get("ECOFLOW_DEMO", "0").strip() in ("1", "true", "si", "sí")

SIN_DATOS_SEG = 300
REINTENTO_SEG = 60
REINTENTO_LOGIN_SEG = 1800

TIPOS = {
    (254, 21): "DisplayPropertyUpload",
    (254, 22): "RuntimePropertyUpload",
    (32, 2): "CMSHeartBeatReport",
}
BMS_HEARTBEAT = {(3, 1), (3, 2), (3, 30), (3, 50), (32, 1), (32, 3),
                 (32, 50), (32, 51), (32, 52), (254, 24), (254, 25)}
GRUPO = {"DisplayPropertyUpload": "display", "RuntimePropertyUpload": "runtime",
         "CMSHeartBeatReport": "cms", "BMSHeartBeatReport": "bms"}

HEADER = {1: "pdata", 2: "src", 3: "dest", 6: "enc_type", 8: "cmd_func", 9: "cmd_id", 14: "seq"}


# --- protobuf mínimo -------------------------------------------------------

def _varint(buf, i):
    n = s = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << s
        if not b & 0x80:
            return n, i
        s += 7


def _campos_crudos(buf):
    """Itera (número, tipo_wire, valor) de un mensaje protobuf."""
    i = 0
    while i < len(buf):
        clave, i = _varint(buf, i)
        num, wt = clave >> 3, clave & 7
        if wt == 0:
            v, i = _varint(buf, i)
        elif wt == 1:
            v, i = buf[i:i + 8], i + 8
        elif wt == 2:
            n, i = _varint(buf, i)
            v, i = buf[i:i + n], i + n
        elif wt == 5:
            v, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"tipo wire {wt} no soportado")
        yield num, wt, v


def _escalar(tipo, wt, v):
    if tipo == "float":
        return round(struct.unpack("<f", v)[0], 3) if wt == 5 else None
    if tipo in ("uint32", "uint64"):
        return v
    if tipo in ("int32", "int64"):
        return v - (1 << 64) if v >= 1 << 63 else v
    if tipo in ("sint32", "sint64"):
        return (v >> 1) ^ -(v & 1)
    if tipo == "string":
        return bytes(v).decode("utf-8", "replace")
    if tipo == "bytes":
        return bytes(v).hex()
    return None


def _empaquetados(tipo, buf):
    out, i = [], 0
    if tipo == "float":
        return [round(x, 3) for x in struct.unpack(f"<{len(buf) // 4}f", buf)]
    while i < len(buf):
        v, i = _varint(buf, i)
        out.append(_escalar(tipo, 0, v))
    return out


def decodificar(nombre, buf):
    """Decodifica un mensaje de ecoflow_campos.MENSAJES a un dict plano."""
    esquema = MENSAJES[nombre]
    datos = {}
    for num, wt, v in _campos_crudos(buf):
        if num not in esquema:
            continue
        campo, tipo, repetido = esquema[num]
        if tipo in MENSAJES:
            datos.update(decodificar(tipo, v))
        elif repetido:
            vals = _empaquetados(tipo, v) if wt == 2 and tipo not in ("string", "bytes") else [_escalar(tipo, wt, v)]
            datos.setdefault(campo, []).extend(vals)
        else:
            datos[campo] = _escalar(tipo, wt, v)
    return datos


def _enc_varint(n):
    n &= (1 << 64) - 1
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _enc(num, valor):
    if isinstance(valor, int):
        return _enc_varint(num << 3) + _enc_varint(valor)
    datos = valor.encode() if isinstance(valor, str) else valor
    return _enc_varint(num << 3 | 2) + _enc_varint(len(datos)) + datos


def peticion_estado_completo():
    """Delta3SendHeaderMsg con un header vacío: la batería responde con todo su estado."""
    seq = 999900000 + random.randint(10000, 99999)
    header = _enc(2, 32) + _enc(3, 32) + _enc(14, seq) + _enc(23, "pi-dashboard")
    return _enc(1, header)


def decodificar_paquete(raw):
    """Devuelve [(grupo, dict)] de un paquete MQTT (Delta3HeaderMessage)."""
    try:
        raw = base64.b64decode(raw, validate=True)
    except Exception:
        pass
    resultado = []
    for num, wt, hbuf in _campos_crudos(raw):
        if num != 1 or wt != 2:
            continue
        h = {}
        for n, w, v in _campos_crudos(hbuf):
            if n in HEADER:
                h[HEADER[n]] = bytes(v) if n == 1 else _escalar("int32", w, v)
        pdata = h.get("pdata")
        if not pdata:
            continue
        if h.get("enc_type") == 1 and h.get("src") != 32:
            k = h.get("seq", 0) & 0xFF
            pdata = bytes(b ^ k for b in pdata)
        par = (h.get("cmd_func"), h.get("cmd_id"))
        tipo = TIPOS.get(par) or ("BMSHeartBeatReport" if par in BMS_HEARTBEAT else None)
        if not tipo:
            continue
        try:
            resultado.append((GRUPO[tipo], decodificar(tipo, pdata)))
        except Exception as e:
            log.debug("No se pudo decodificar %s: %s", par, e)
    return resultado


# --- resumen para la tarjeta ------------------------------------------------

def _primero(*vals):
    return next((v for v in vals if v is not None), None)


def _w(v):
    return round(abs(v)) if v is not None else 0


def resumir(campos):
    d = campos.get("display", {})
    c, b = campos.get("cms", {}), campos.get("bms", {})
    soc = _primero(d.get("bms_batt_soc"), d.get("cms_batt_soc"), c.get("cms_batt_soc"), b.get("f32_show_soc"))
    edo = _primero(d.get("bms_chg_dsg_state"), d.get("cms_chg_dsg_state"), c.get("cms_chg_dsg_state"))
    estado = {0: "reposo", 1: "descargando", 2: "cargando"}.get(edo)
    if estado == "cargando":
        mins = _primero(d.get("bms_chg_rem_time"), d.get("cms_chg_rem_time"), c.get("cms_chg_rem_time"))
    else:
        mins = _primero(d.get("bms_dsg_rem_time"), d.get("cms_dsg_rem_time"), c.get("cms_dsg_rem_time"))
    if mins is not None and (mins <= 0 or mins >= 5999):
        mins = None
    return {
        "soc": round(soc, 1) if soc is not None else None,
        "estado": estado,
        "restante_min": mins,
        "wh": round(CAPACIDAD_WH * soc / 100) if soc is not None else None,
        "capacidad_wh": CAPACIDAD_WH,
        "min_descarga": _primero(d.get("cms_min_dsg_soc"), c.get("cms_min_dsg_soc")),
        "max_carga": _primero(d.get("cms_max_chg_soc"), c.get("cms_max_chg_soc")),
        "entrada_w": _w(d.get("pow_in_sum_w")),
        "entradas": {
            "solar1": _w(d.get("pow_get_pv")),
            "solar2": _w(d.get("pow_get_pv2")),
            "ac": _w(d.get("pow_get_ac_in")),
            "extra": _w(d.get("pow_get_dcp")),
        },
        "salida_w": _w(d.get("pow_out_sum_w")),
        "salidas": {
            "ac": _w(_primero(d.get("pow_get_ac_out"), d.get("pow_get_ac"))),
            "usb_c": _w(d.get("pow_get_typec1")) + _w(d.get("pow_get_typec2")),
            "usb_a": _w(d.get("pow_get_qcusb1")) + _w(d.get("pow_get_qcusb2")),
            "dc12v": _w(d.get("pow_get_12v")),
        },
        "salud": _primero(d.get("bms_batt_soh"), b.get("soh"), d.get("cms_batt_soh")),
        "ciclos": b.get("cycles"),
        "temp": _primero(d.get("bms_max_cell_temp"), b.get("max_cell_temp"), b.get("temp")),
    }


# --- cliente ------------------------------------------------------------------

class EcoFlow:
    def __init__(self):
        self.lock = threading.Lock()
        self.campos = {"display": {}, "runtime": {}, "cms": {}, "bms": {}}
        self.estado = "sin_configurar"
        self.error = None
        self.ultimo = 0.0
        self.mqtt = None

    # HTTP

    def _api(self, ruta, token=None, cuerpo=None, user_id=None):
        url = f"https://{API_HOST}{ruta}"
        headers = {"lang": "en_US", "content-type": "application/json", "User-Agent": "pi-dashboard"}
        if token:
            headers["authorization"] = f"Bearer {token}"
            data = urllib.parse.urlencode({"userId": user_id}).encode()
            headers["content-type"] = "application/x-www-form-urlencoded"
            req = urllib.request.Request(url, data=data, headers=headers, method="GET")
        else:
            req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.load(r)
        if str(resp.get("message", "")).lower() != "success":
            raise PermissionError(f"{ruta}: {resp.get('message')} (code {resp.get('code')})")
        return resp["data"]

    def _credenciales_mqtt(self):
        login = self._api("/auth/login", cuerpo={
            "email": EMAIL,
            "password": base64.b64encode(PASSWORD.encode()).decode(),
            "scene": "IOT_APP",
            "userType": "ECOFLOW",
        })
        user_id = login["user"]["userId"]
        cert = self._api("/iot-auth/app/certification", token=login["token"], user_id=user_id)
        return user_id, cert

    # MQTT

    def _conectar(self):
        import paho.mqtt.client as mqtt

        user_id, cert = self._credenciales_mqtt()
        topic_datos = f"/app/device/property/{SN}"
        topic_get = f"/app/{user_id}/{SN}/thing/property/get"
        topic_reply = f"/app/{user_id}/{SN}/thing/property/get_reply"

        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                          client_id=f"ANDROID_{uuid.uuid4().hex.upper()}_{user_id}", clean_session=True)
        cli.username_pw_set(cert["certificateAccount"], cert["certificatePassword"])
        cli.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        cli.reconnect_delay_set(5, 120)

        def on_connect(c, _u, _f, rc, _p):
            if rc.is_failure:
                self._set_estado("desconectado", f"MQTT: {rc}")
                return
            c.subscribe([(topic_datos, 1), (topic_reply, 1)])
            c.publish(topic_get, peticion_estado_completo(), 1)
            self._set_estado("conectado")

        def on_disconnect(_c, _u, _f, rc, _p):
            self._set_estado("desconectado", f"MQTT: {rc}")

        def on_message(_c, _u, msg):
            self.recibir(msg.payload)

        cli.on_connect, cli.on_disconnect, cli.on_message = on_connect, on_disconnect, on_message
        cli.connect(cert["url"], int(cert["port"]), keepalive=15)
        cli.loop_start()
        self.mqtt = (cli, topic_get)

    def recibir(self, payload):
        partes = decodificar_paquete(payload)
        if not partes:
            return
        with self.lock:
            for grupo, datos in partes:
                self.campos[grupo].update(datos)
            self.ultimo = time.time()
            self.estado, self.error = "en_linea", None

    def _set_estado(self, estado, error=None):
        with self.lock:
            self.estado, self.error = estado, error

    def _bucle(self):
        while True:
            try:
                self._set_estado("conectando")
                self._conectar()
                desconectado_desde = None
                while True:
                    time.sleep(30)
                    cli, topic_get = self.mqtt
                    if not cli.is_connected():
                        desconectado_desde = desconectado_desde or time.time()
                        if time.time() - desconectado_desde > 600:
                            raise ConnectionError("MQTT desconectado más de 10 min")
                        continue
                    desconectado_desde = None
                    if time.time() - self.ultimo > SIN_DATOS_SEG:
                        cli.publish(topic_get, peticion_estado_completo(), 1)
            except PermissionError as e:
                log.error("EcoFlow rechazó el login: %s", e)
                self._set_estado("error_login", str(e))
                espera = REINTENTO_LOGIN_SEG
            except Exception as e:
                log.warning("EcoFlow: %s", e)
                self._set_estado("desconectado", str(e))
                espera = REINTENTO_SEG
            if self.mqtt:
                self.mqtt[0].loop_stop()
                self.mqtt[0].disconnect()
                self.mqtt = None
            time.sleep(espera)

    def _demo(self):
        t0 = time.time()
        while True:
            m = (time.time() - t0) / 60
            pv1, pv2, ac_in = round(214 + 20 * (m % 3)), 138, 60
            ac, c1, a1 = 160, 18, 8
            soc = min(100.0, 78 + m * 0.2)
            with self.lock:
                self.campos["display"].update({
                    "bms_batt_soc": round(soc, 1), "bms_chg_dsg_state": 2, "bms_chg_rem_time": 85,
                    "pow_in_sum_w": pv1 + pv2 + ac_in, "pow_get_pv": pv1, "pow_get_pv2": pv2,
                    "pow_get_ac_in": ac_in, "pow_get_dcp": 0, "pow_out_sum_w": ac + c1 + a1,
                    "pow_get_ac_out": -ac, "pow_get_typec1": -c1, "pow_get_typec2": 0,
                    "pow_get_qcusb1": -a1, "pow_get_qcusb2": 0, "pow_get_12v": 0,
                    "bms_batt_soh": 99.0, "bms_max_cell_temp": 29, "cms_min_dsg_soc": 10, "cms_max_chg_soc": 100,
                })
                self.campos["bms"].update({"cycles": 37, "soh": 99})
                self.ultimo = time.time()
                self.estado = "en_linea"
            time.sleep(5)

    def iniciar(self):
        if DEMO:
            threading.Thread(target=self._demo, daemon=True).start()
        elif EMAIL and PASSWORD and SN:
            threading.Thread(target=self._bucle, daemon=True).start()
        return self

    def datos(self):
        with self.lock:
            campos = {k: dict(v) for k, v in self.campos.items()}
            ultimo, estado, error = self.ultimo, self.estado, self.error
        return {
            "estado": estado,
            "error": error,
            "demo": DEMO,
            "actualizado": datetime.fromtimestamp(ultimo).isoformat(timespec="seconds") if ultimo else None,
            "hace_seg": round(time.time() - ultimo) if ultimo else None,
            "resumen": resumir(campos) if ultimo else None,
            "campos": campos,
        }
