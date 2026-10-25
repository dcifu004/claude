#!/usr/bin/env python3
"""Pruebas del pronóstico conservador de cuota (encargo 56).

Trabaja siempre con una copia temporal del historial real: no lee ni escribe uso.json,
no llama procesos ni manda avisos.
"""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ENCARGOS = Path(__file__).resolve().parent


def cargar():
    spec = importlib.util.spec_from_file_location("cola_run_pronostico", ENCARGOS / "cola-run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PronosticoReal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pronostico-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.historial = self.tmp / "historial.jsonl"
        shutil.copyfile(ENCARGOS / "56-fixtures" / "historial-12-10.jsonl", self.historial)
        self.cr = cargar()
        self.cr.HISTORIAL = self.historial

    def test_c1_c2_y_c5_p75_decide_y_mediana_sigue_en_eta(self):
        high = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "high")
        xhigh = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "xhigh")
        self.assertGreaterEqual(high["pct_5h_p75"], 30)
        self.assertGreaterEqual(xhigh["pct_5h_p75"], 45)
        # C2 pasa por chequear_cuota(), que es la ruta de etapa(), con una medición
        # de la misma forma que devuelve uso.json. Sin renovación no puede dormir ni
        # escribir vivo: debe pausar antes de partir.
        self.cr.medir = lambda cid: {"5h": 77.0, "sem": 0.0, "renueva_5h": None,
                                     "renueva_sem": None, "fuente": "prueba"}
        with self.assertRaises(self.cr.Pausa):
            self.cr.chequear_cuota("claude_cami", "rev", "43b:rev3", "claude-opus-5-5", "high")
        self.cr.medir = lambda cid: {"5h": 52.0, "sem": 0.0, "renueva_5h": None,
                                     "renueva_sem": None, "fuente": "prueba"}
        with self.assertRaises(self.cr.Pausa):
            self.cr.chequear_cuota("claude_cami", "rev", "50b:rev2", "claude-opus-5-5", "xhigh")
        filas = [h["min"] for h in self.cr.historial() if h.get("cuenta") == "claude_cami" and not h.get("sin_cuota")
                 and h.get("rol") == "rev" and h.get("modelo") == "claude-opus-5-5"
                 and h.get("esfuerzo") == "high"][-12:]
        self.assertEqual(high["min"], round(self.cr.statistics.median(filas), 1))
        self.assertNotEqual(high["pct_5h"], high["pct_5h_p75"])

    def test_c3_corte_sube_y_linea_a_medias_se_tolera(self):
        sin_corte = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "high")
        filas = [json.loads(x) for x in self.historial.read_text(encoding="utf-8").splitlines()]
        # Copia la forma real de la 43b rev3, pero con una cota observada mayor: una
        # fase cortada debe elevar el pronóstico conservador, jamás borrarse.
        base = next(h for h in filas if h.get("encargo") == "43b" and h.get("fase") == "rev3")
        filas.append(dict(base, encargo="corte-real-forma", sin_cuota=True, pct_5h=[80.0, 160.0], pct_sem=[50.0, 100.0]))
        self.historial.write_text("\n".join(json.dumps(x) for x in filas) + "\n{", encoding="utf-8")
        con_corte = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "high")
        self.assertGreater(con_corte["pct_5h_p75"], sin_corte["pct_5h_p75"])
        self.assertGreater(con_corte["pct_sem_p75"], sin_corte["pct_sem_p75"])
        self.historial.write_text("\n".join(json.dumps(x) for x in filas) + "\n", encoding="utf-8")
        sano = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "high")
        self.historial.write_text("\n".join(json.dumps(x) for x in filas) + "\n{", encoding="utf-8")
        self.assertEqual(self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "high"), sano)

    def test_c4_menos_de_tres_esfuerzos_cae_a_modelo_y_es_debil(self):
        f = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "xhigh")
        self.assertEqual(f["n"], 12)  # con el historial completo cae a las últimas doce del mismo modelo
        self.assertTrue(f["debil"])

    def test_cotas_reales_de_xhigh_siguen_contando_tras_doce_medium(self):
        """Con la forma real de 50b y 43c, otras revisiones no pueden rebajar el corte xhigh."""
        filas = list(self.cr.historial())
        base = next(h for h in filas if h.get("encargo") == "50b" and h.get("fase") == "rev1")
        for i in range(12):
            filas.append(dict(base, encargo=f"medio{i}", esfuerzo="medium", sin_cuota=False, min=8.0,
                              pct_5h=[10.0, 18.0], pct_sem=[40.0, 42.0], medicion="fresco"))
        self.historial.write_text("\n".join(json.dumps(x) for x in filas) + "\n", encoding="utf-8")
        xhigh = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "xhigh")
        self.assertGreaterEqual(xhigh["pct_5h_p75"], 45)

    def test_dos_cortes_no_bajan_p75_ni_entran_a_los_minutos(self):
        filas = list(self.cr.historial())
        alto = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "high")
        base = next(h for h in reversed(filas) if h.get("cuenta") == "claude_cami" and h.get("rol") == "rev"
                    and h.get("modelo") == "claude-opus-5-5" and h.get("esfuerzo") == "high" and not h.get("sin_cuota"))
        for i in range(2):
            filas.append(dict(base, encargo=f"corte{i}", sin_cuota=True, min=1.0,
                              pct_5h=[80.0, 82.0], pct_sem=[50.0, 52.0]))
        self.historial.write_text("\n".join(json.dumps(x) for x in filas) + "\n", encoding="utf-8")
        con_cortes = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "high")
        self.assertGreaterEqual(con_cortes["pct_5h_p75"], alto["pct_5h_p75"])
        self.assertEqual(con_cortes["min"], alto["min"])

    def test_c3_ordenes_reales_cff_fcf_y_ffc_no_caen_a_la_base(self):
        """Las dos filas reales xhigh de 50b, reordenadas como llegaron; una cortada conserva su cota."""
        filas = list(self.cr.historial())
        xhigh = [h for h in filas if h.get("encargo") == "50b" and h.get("rol") == "rev"]
        self.assertEqual([(h["sin_cuota"], h["pct_5h"]) for h in xhigh], [(False, [0.0, 52.0]), (True, [52.0, 98.0])])
        otras = [h for h in filas if h not in xhigh]
        for orden in ("CFF", "FCF", "FFC"):
            c = next(h for h in xhigh if h["sin_cuota"])
            f = next(h for h in xhigh if not h["sin_cuota"])
            nuevas = otras + [dict(c if letra == "C" else f, encargo=f"orden-{orden}-{n}") for n, letra in enumerate(orden)]
            self.historial.write_text("\n".join(json.dumps(h) for h in nuevas) + "\n", encoding="utf-8")
            pron = self.cr.pronostico("claude_cami", "rev", "claude-opus-5-5", "", "xhigh")
            self.assertGreaterEqual(pron["pct_5h_p75"], 46, orden)
            self.cr.medir = lambda _: {"5h": 60.0, "sem": 0.0, "renueva_5h": None, "renueva_sem": None, "fuente": "forma-real"}
            with self.assertRaises(self.cr.Pausa, msg=orden):
                self.cr.chequear_cuota("claude_cami", "rev", f"orden:{orden}", "claude-opus-5-5", "xhigh")


if __name__ == "__main__":
    unittest.main()
