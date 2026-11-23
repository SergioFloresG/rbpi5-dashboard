import base64
import struct
import unittest

import ecoflow
from ecoflow import _enc, decodificar_paquete, peticion_estado_completo, resumir


def flotante(num, v):
    return ecoflow._enc_varint(num << 3 | 5) + struct.pack("<f", v)


def paquete(cmd_func, cmd_id, pdata, seq=0, enc=0, src=2):
    if enc:
        pdata = bytes(b ^ (seq & 0xFF) for b in pdata)
    h = _enc(1, pdata) + _enc(2, src) + _enc(6, enc) + _enc(8, cmd_func) + _enc(9, cmd_id) + _enc(14, seq)
    return _enc(1, h)


class Decodificador(unittest.TestCase):
    def test_display_con_xor(self):
        pdata = flotante(3, 412.0) + flotante(4, 186.0) + flotante(242, 81.5) + _enc(281, 2) + flotante(70, 138.0)
        partes = decodificar_paquete(paquete(254, 21, pdata, seq=123456789, enc=1))
        self.assertEqual(len(partes), 1)
        grupo, d = partes[0]
        self.assertEqual(grupo, "display")
        self.assertEqual(d["pow_in_sum_w"], 412.0)
        self.assertEqual(d["bms_batt_soc"], 81.5)
        self.assertEqual(d["bms_chg_dsg_state"], 2)
        self.assertEqual(d["pow_get_pv2"], 138.0)

    def test_base64_y_bms(self):
        pdata = _enc(14, 37) + _enc(10, 99)
        raw = base64.b64encode(paquete(32, 50, pdata))
        grupo, d = decodificar_paquete(raw)[0]
        self.assertEqual(grupo, "bms")
        self.assertEqual(d["cycles"], 37)

    def test_negativo_y_desconocido(self):
        pdata = flotante(368, -160.0)
        self.assertEqual(decodificar_paquete(paquete(254, 21, pdata))[0][1]["pow_get_ac_out"], -160.0)
        self.assertEqual(decodificar_paquete(paquete(99, 99, pdata)), [])

    def test_resumen(self):
        r = resumir({"display": {"bms_batt_soc": 50, "bms_chg_dsg_state": 1, "bms_dsg_rem_time": 5999,
                                 "pow_get_ac_out": -160.0, "pow_get_typec1": -18, "pow_get_typec2": -2},
                     "bms": {"cycles": 37, "soh": 100}})
        self.assertEqual(r["estado"], "descargando")
        self.assertIsNone(r["restante_min"])
        self.assertEqual(r["salidas"]["ac"], 160)
        self.assertEqual(r["salidas"]["usb_c"], 20)
        self.assertEqual(r["ciclos"], 37)
        self.assertEqual(r["salud"], 100)
        r = resumir({"display": {"bms_chg_dsg_state": 0, "bms_dsg_rem_time": 7189, "bms_chg_rem_time": 12927}})
        self.assertEqual(r["restante_min"], 7189)
        r = resumir({"display": {"bms_chg_dsg_state": 2, "bms_chg_rem_time": 143999}})
        self.assertIsNone(r["restante_min"])

    def test_bateria_extra(self):
        e = ecoflow.EcoFlow()
        for num, sn, ciclos in ((0, "P351", 23), (1, "P361", 12)):
            pdata = _enc(1, num) + _enc(14, ciclos) + _enc(81, sn)
            e.recibir(paquete(32, 50, pdata))
        self.assertEqual(e.campos["bms"]["cycles"], 23)
        self.assertEqual(e.campos["bms_extra"]["1"]["pack_sn"], "P361")
        self.assertIn("1", e.datos()["campos"]["bms_extra"])
        e.visto_extra["1"] -= ecoflow.EXTRA_VIGENCIA_SEG + 1
        self.assertEqual(e.datos()["campos"]["bms_extra"], {})
        r = resumir({"display": {"bms_batt_soc": 90},
                     "bms": {"full_cap": 20000, "remain_cap": 18000, "design_cap": 20000, "cell_series_num": 16, "soh": 100},
                     "bms_extra": {"1": {"full_cap": 20000, "remain_cap": 14000, "design_cap": 20000, "cell_series_num": 16}}})
        self.assertEqual(r["soc"], 80.0)
        self.assertEqual(r["capacidad_wh"], 2048)
        self.assertEqual([p["nombre"] for p in r["baterias"]], ["Principal", "Extra"])
        r = resumir({"display": {"bms_batt_soc": 90},
                     "bms": {"full_cap": 20000, "remain_cap": 18000},
                     "bms_extra": {"1": {"full_cap": 20000, "remain_cap": 0}}})
        self.assertEqual(r["soc"], 45.0)

    def test_peticion(self):
        h = dict((n, v) for n, _, v in ecoflow._campos_crudos(next(ecoflow._campos_crudos(peticion_estado_completo()))[2]))
        self.assertEqual((h[2], h[3], bytes(h[23])), (32, 32, b"pi-dashboard"))


if __name__ == "__main__":
    unittest.main()
