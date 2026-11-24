#!/usr/bin/env python3
"""Obtiene de la cuenta Dyson la credencial local de cada purificador y la guarda en config.env.

Uso (una sola vez, en la Pi):  .venv/bin/python dyson_login.py
"""
import getpass
import os
import re
import sys

from libdyson.cloud import DysonAccount

from dyson import descubrir

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.env")
VENTILADORES = ("438", "520", "527", "358", "664", "455", "475", "469")


def tipo_mqtt(d):
    """Tipo que usa el equipo en sus temas MQTT, con variante (p. ej. 527K)."""
    t = d.product_type or ""
    if re.fullmatch(r"\d{3}[EKM]", t):
        return t
    if t in ("438", "527", "358"):
        firmware = d.version or ""
        v = (d.variant or "").strip().upper() or (firmware[3:4] if firmware.startswith(t) else "")
        if v in ("E", "K", "M"):
            return t + v
    return d.get_device_type()


def guardar(valor):
    lineas = []
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            lineas = [l for l in f.read().splitlines() if not l.startswith("DYSON_EQUIPOS=")]
    lineas.append(f"DYSON_EQUIPOS={valor}")
    tmp = CONFIG + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG)


def main():
    correo = input("Correo de la cuenta Dyson: ").strip()
    region = (input("País de la cuenta [MX]: ").strip() or "MX").upper()
    cuenta = DysonAccount()
    verificar = cuenta.login_email_otp(correo, region)
    codigo = input("Código que llegó al correo: ").strip()
    verificar(codigo, getpass.getpass("Contraseña de Dyson (no se guarda): "))

    equipos = []
    for d in cuenta.devices():
        tipo = tipo_mqtt(d)
        if not tipo or not tipo.startswith(VENTILADORES):
            print(f"- {d.name} ({d.serial}): tipo {d.product_type} no es purificador, se omite")
            continue
        try:
            host, tipo_red = descubrir(d.serial)
            tipo = tipo if re.fullmatch(r"\d{3}[EKM]", tipo) else tipo_red
        except Exception as e:
            host = ""
            print(f"- {d.name} ({d.serial}): sin IP por ahora ({e}); se buscará al arrancar")
        etiqueta = re.sub(r"[^\w \-]", "", d.name or "").strip() or d.serial
        equipos.append(f"{etiqueta}={d.serial}|{tipo}|{d.credential}|{host}".rstrip("|"))
        print(f"- {etiqueta}: serie {d.serial}, tipo {tipo}, IP {host or 'por mDNS'}")

    if not equipos:
        sys.exit("La cuenta no tiene purificadores con conexión local.")
    guardar(",".join(equipos))
    print(f"\nGuardado en {CONFIG}. Ahora: sudo systemctl restart pi-dashboard")


if __name__ == "__main__":
    main()
