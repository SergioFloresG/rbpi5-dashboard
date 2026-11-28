import unittest

import app


def fuente(corte, n=3):
    return {"host": "h", "radar": {
        "past": [{"time": corte - 600, "path": "/a"}, {"time": corte, "path": "/b"}],
        "nowcast": [{"time": corte + 600 * i, "path": f"/n{i}"} for i in range(1, n + 1)]}}


class RadarPronostico(unittest.TestCase):
    def test_conserva_pronostico_anterior_mientras_el_nuevo_no_es_estable(self):
        previo = app._radar_armar(fuente(1000), None, 0, 5000)
        self.assertEqual([f["g"] for f in previo["nowcast"]], [1000] * 3)

        d = app._radar_armar(fuente(1600), previo, 5000, 5000 + app.PRON_ESPERA_SEG - 1)
        self.assertEqual(d["frames"][-1]["time"], 1600)
        self.assertEqual([(f["time"], f["g"]) for f in d["nowcast"]], [(2200, 1000), (2800, 1000)])
        self.assertEqual(app._radar_dirs(d)[1600][0], "real/1600")

        d = app._radar_armar(fuente(1600), d, 5000, 5000 + app.PRON_ESPERA_SEG)
        self.assertEqual([(f["time"], f["g"]) for f in d["nowcast"]], [(2200, 1600), (2800, 1600), (3400, 1600)])
        self.assertEqual(app._radar_dirs(d)[2200], (None, "/n1", "?g=1600"))

    def test_arranque_con_cuadro_recien_publicado_no_muestra_pronostico(self):
        self.assertEqual(app._radar_armar(fuente(1000), None, 5000, 5010)["nowcast"], [])


if __name__ == "__main__":
    unittest.main()
