import socket
import threading
import unittest

from ups import leer_nut, parsear_destinos, parsear_vars, resumir

RESPUESTA = """BEGIN LIST VAR cp1500
VAR cp1500 battery.charge "100"
VAR cp1500 battery.charge.low "10"
VAR cp1500 battery.runtime "2730"
VAR cp1500 battery.voltage "13.6"
VAR cp1500 device.model "CP1500AVRLCDa"
VAR cp1500 input.voltage "127.0"
VAR cp1500 output.voltage "127.0"
VAR cp1500 ups.load "22"
VAR cp1500 ups.realpower.nominal "900"
VAR cp1500 ups.status "OL BOOST"
VAR cp1500 ups.test.result "No test initiated"
VAR cp1500 ups.mfr "CPS \\"Cyber\\" Power"
END LIST VAR cp1500
"""


def servidor_falso(respuesta):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def atender():
        c, _ = srv.accept()
        with c:
            c.recv(1024)
            c.sendall(respuesta.encode())
            c.recv(1024)
        srv.close()

    threading.Thread(target=atender, daemon=True).start()
    return srv.getsockname()[1]


class Ups(unittest.TestCase):
    def test_destinos(self):
        self.assertEqual(parsear_destinos("CP1500=cp1500@localhost, sala@10.0.1.9:3494,cp850"), [
            {"etiqueta": "CP1500", "ups": "cp1500", "host": "localhost", "puerto": 3493},
            {"etiqueta": None, "ups": "sala", "host": "10.0.1.9", "puerto": 3494},
            {"etiqueta": None, "ups": "cp850", "host": "localhost", "puerto": 3493},
        ])
        self.assertEqual(parsear_destinos(""), [])

    def test_leer_y_resumir(self):
        v = leer_nut("127.0.0.1", servidor_falso(RESPUESTA), "cp1500")
        self.assertEqual(v["ups.mfr"], 'CPS "Cyber" Power')
        r = resumir(v)
        self.assertEqual(r["estado"], "red")
        self.assertEqual(r["banderas"], ["red", "avr_eleva"])
        self.assertEqual(r["soc"], 100)
        self.assertEqual(r["restante_min"], 46)
        self.assertEqual(r["potencia_w"], 198)
        self.assertEqual(r["modelo"], "CP1500AVRLCDa")

    def test_error_nut(self):
        with self.assertRaisesRegex(ConnectionError, "DRIVER-NOT-CONNECTED"):
            leer_nut("127.0.0.1", servidor_falso("ERR DRIVER-NOT-CONNECTED\n"), "cp1500")

    def test_en_bateria(self):
        r = resumir(parsear_vars(['VAR u ups.status "OB DISCHRG LB"', 'VAR u ups.load "50"',
                                  'VAR u ups.power.nominal "1500"'], "u"))
        self.assertEqual(r["estado"], "bateria")
        self.assertIn("baja", r["banderas"])
        self.assertEqual(r["nominal_w"], 900)
        self.assertEqual(r["potencia_w"], 450)


if __name__ == "__main__":
    unittest.main()
