import json
import unittest

from dyson import Dyson, nivel, parsear_equipos, resumir

AMBIENTE = {"tact": "2981", "hact": "0061", "pm25": "0008", "pm10": "0012", "va10": "0045", "noxl": "0004",
            "p25r": "0009", "p10r": "0060", "sltm": "OFF"}
ESTADO = {"fpwr": "ON", "auto": "ON", "nmod": "OFF", "hmod": "HEAT", "rhtm": "ON", "hflr": "0087", "cflr": "INV"}


class Equipos(unittest.TestCase):
    def test_parsear(self):
        self.assertEqual(parsear_equipos("Sala=X3X-MX-ABC1234A|527K|aB+/cd==|10.0.1.40, NK6-EU-XYZ0000A|438|zz=="), [
            {"etiqueta": "Sala", "serie": "X3X-MX-ABC1234A", "tipo": "527K", "credencial": "aB+/cd==", "host": "10.0.1.40"},
            {"etiqueta": None, "serie": "NK6-EU-XYZ0000A", "tipo": "438", "credencial": "zz==", "host": None},
        ])
        self.assertEqual(parsear_equipos(""), [])

    def test_incompleto(self):
        for texto in ("X3X-MX-ABC1234A", "X3X-MX-ABC1234A|527K", "|527K|cred"):
            with self.assertRaises(ValueError):
                parsear_equipos(texto)


class Resumen(unittest.TestCase):
    def test_valores(self):
        r = resumir(ESTADO, AMBIENTE)
        self.assertEqual((r["pm2_5"], r["pm10"], r["cov"], r["no2"]), (9, 60, 4.5, 0.4))
        self.assertEqual((r["temp"], r["humedad"]), (25.0, 61))
        self.assertEqual(r["niveles"], {"pm2_5": 1, "pm10": 2, "cov": 2, "no2": 1})
        self.assertEqual(r["calidad"], 2)
        self.assertTrue(r["encendido"] and r["auto"] and r["calor"])
        self.assertFalse(r["noche"])
        self.assertEqual(r["filtro_hepa"], 87)
        self.assertIsNone(r["filtro_carbon"])
        self.assertIsNone(r["hcho"])

    def test_sensores_apagados(self):
        r = resumir({"fpwr": "OFF", "rhtm": "OFF"}, {"tact": "OFF", "hact": "OFF", "pm25": "INIT", "va10": "FAIL"})
        self.assertEqual([r[c] for c in ("pm2_5", "pm10", "cov", "no2", "temp", "humedad", "calidad")], [None] * 7)
        self.assertFalse(r["encendido"])

    def test_niveles(self):
        self.assertEqual([nivel("pm2_5", v) for v in (0, 35, 36, 53, 70, 71, 300)], [1, 1, 2, 2, 3, 4, 4])
        self.assertEqual([nivel("pm10", v) for v in (50, 51, 75, 100, 101)], [1, 2, 2, 3, 4])
        self.assertEqual([nivel("no2", v) for v in (3, 3.1, 6, 8, 8.1)], [1, 2, 2, 3, 4])
        self.assertIsNone(nivel("cov", None))

    def test_cambio_de_estado(self):
        r = resumir({"fpwr": ["OFF", "ON"], "auto": ["ON", "OFF"]}, AMBIENTE)
        self.assertTrue(r["encendido"])
        self.assertFalse(r["auto"])


class Mensajes(unittest.TestCase):
    def test_recibir(self):
        d = Dyson()
        d.equipos = parsear_equipos("Sala=S1|527K|cred")
        d.lecturas = {"S1": {"estado_equipo": {}, "ambiente": {}, "ultimo": 0.0, "error": None, "estado": "en_linea"}}
        e = d.equipos[0]
        d.recibir(e, b"no es json")
        d.recibir(e, json.dumps({"msg": "CURRENT-STATE", "product-state": ESTADO}))
        self.assertIsNone(d.datos()["equipos"][0]["resumen"])
        d.recibir(e, json.dumps({"msg": "ENVIRONMENTAL-CURRENT-SENSOR-DATA", "data": AMBIENTE}))
        d.recibir(e, json.dumps({"msg": "STATE-CHANGE", "product-state": {"fpwr": ["ON", "OFF"]}}))
        eq = d.datos()["equipos"][0]
        self.assertEqual(eq["resumen"]["pm2_5"], 9)
        self.assertFalse(eq["resumen"]["encendido"])
        self.assertTrue(eq["resumen"]["auto"])


if __name__ == "__main__":
    unittest.main()
