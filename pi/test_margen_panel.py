#!/usr/bin/env python3
"""Pruebas del margen ya resuelto para /uso como imagen (encargo 90): `capacidad_de`, `panel_margen`,
`bots-info --margen` y `panel-cache.py`. Todo sobre fixtures de pi/fixtures/cuentas/ y temporales.

    NODO_PRUEBAS=1 python3 -B -m unittest pi/test_margen_panel.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FIJ = AQUI / "fixtures" / "cuentas"
CIDS = ["codex", "claude_cami", "claude_diego", "otra"]


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bi = cargar("bots_info_90", AQUI / "bots-info.py")
recetas = cargar("recetas_90", AQUI.parent / "botv3" / "recetas.py")
pc = cargar("panel_cache_90", AQUI / "panel-cache.py")


def caso(nombre):
    return json.loads((FIJ / f"margen-{nombre}.json").read_text(encoding="utf-8"))


def panel_de(nombre, reglas="fixture"):
    f = caso(nombre)
    ahora = datetime.fromisoformat(f["ahora"]).astimezone(bi.TZ)
    registro = bi.registro_cuentas.__globals__["leer_toml"](str(AQUI / "fixtures/avisos/cuentas.toml"))
    registro = {k: v for k, v in registro.items() if isinstance(v, dict)}
    limites = bi.limites_de(f["uso"])
    margen = bi.margen_de(registro, limites, ahora, bi.resumen_cuentas(registro, [], ahora, dict(limites)), recetas)
    return margen, bi.panel_margen(margen, f["reglas"] if reglas == "fixture" else reglas, ahora), f


class PortDeCargaDe(unittest.TestCase):
    """El port en Python da lo mismo que `cargaDe` de cuentas.js corrido con node."""

    def test_igual_a_la_salida_guardada_de_node(self):
        js = json.loads((FIJ / "cargaDe-js.json").read_text(encoding="utf-8"))
        for nombre in ("normal", "pasado"):
            py = {c: bi.capacidad_de(caso(nombre)["reglas"], c) for c in CIDS}
            self.assertEqual(json.loads(json.dumps(py)), js[nombre], nombre)

    @unittest.skipUnless(shutil.which("node"), "sin node (en la Pi no hay): vale la salida guardada")
    def test_igual_a_cuentas_js_en_vivo(self):
        p = subprocess.run(["node", str(FIJ / "genera-cargaDe-js.mjs"), "--stdout"], capture_output=True, text=True,
                           timeout=60, check=True)
        self.assertEqual(json.loads(p.stdout), json.loads((FIJ / "cargaDe-js.json").read_text(encoding="utf-8")),
                         "cuentas.js cambió: vuelve a generar cargaDe-js.json y revisa el port")

    def test_formas_raras_no_inventan_carga(self):
        self.assertIsNone(bi.capacidad_de(None, "codex"))
        self.assertIsNone(bi.capacidad_de([{"cuenta": "codex", "celdas": []}], "codex"))
        malo = {"cuenta": "codex", "celdas": {"c1": {"pct_5h": True}},
                "ventanas": [{"ventana": "5h", "actual": "41", "tope": 90, "pronostico": 3}]}
        self.assertIsNone(bi.capacidad_de([malo], "codex"))


class PanelMargen(unittest.TestCase):
    def test_numeros_iguales_a_margen_de_y_a_la_carga(self):
        margen, panel, f = panel_de("normal")
        por_cuenta = {t["cuenta"]: t for t in panel["tarjetas"]}
        self.assertEqual([t["cuenta"] for t in panel["tarjetas"]], [c for c in margen["orden"] if margen["cuentas"][c]["pagada"]])
        for cid, t in por_cuenta.items():
            m = margen["cuentas"][cid]
            for v, clave in zip(t["ventanas"], ("ventana_5h", "semanal")):
                self.assertEqual(v["usado_pct"], m[clave]["usado_pct"])
                self.assertEqual(v["libre_pct"], m[clave]["libre_pct"])
        codex = por_cuenta["codex"]["ventanas"][0]
        self.assertEqual(codex["capacidad"]["suma"], 71.2)       # 41 + 30,2
        self.assertEqual(codex["capacidad"]["texto"], ["uso 41 % + carga comprometida 30,2 % = ", "71,2 %", " · tope 90 %"])
        self.assertFalse(codex["capacidad"]["sobre_tope"])
        self.assertEqual(codex["barra"]["tramos"], [{"cola": "cola87", "i": 0, "ancho": 30.2, "pct": 30.2}])
        self.assertIsNone(por_cuenta["claude_cami"]["ventanas"][0]["capacidad"])   # sin carga: barra simple
        self.assertEqual(panel["resumen"]["nombre"], margen["cuentas"][margen["con_margen"]]["nombre"])
        self.assertTrue(por_cuenta[margen["con_margen"]]["con_margen"])
        self.assertEqual(por_cuenta["codex"]["medido"], "medido hace 30 min")
        self.assertEqual(codex["renueva"], "se renueva dom 04-10 20:31 (en 2 h 42 min)")
        diego = por_cuenta["claude_diego"]
        self.assertEqual(diego["ventanas"][0]["despues"]["texto"], "↻ desde las 21:30: carga comprometida 12,5 %")
        self.assertEqual(diego["leyenda"], [{"cola": "cola87", "i": 0}, {"cola": "cola88", "i": 1}])
        self.assertEqual(panel["gratis"], ["Groq", "Gemini", "OpenRouter", "Tavily"])

    def test_pasado_del_tope_en_rojo(self):
        _, panel, _ = panel_de("pasado")
        diego = next(t for t in panel["tarjetas"] if t["cuenta"] == "claude_diego")
        h5, sem = (v["capacidad"] for v in diego["ventanas"])
        self.assertEqual((h5["suma"], h5["tope"], h5["sobre_tope"]), (95.1, 90, True))
        self.assertEqual((sem["suma"], sem["tope"], sem["sobre_tope"]), (80.0, 75, True))
        self.assertEqual(diego["ventanas"][0]["barra"]["tramos"][-1]["ancho"], 26.0)
        otras = [v["capacidad"]["sobre_tope"] for t in panel["tarjetas"] if t["cuenta"] != "claude_diego"
                 for v in t["ventanas"] if v["capacidad"]]
        self.assertEqual(otras, [False, False])

    def test_suma_justo_en_el_tope_no_es_rojo_y_redondea_como_js(self):
        w = {"uso": 60.0, "carga": 30.0, "tope": 90, "partes": [], "despues": 0, "renueva": None}
        self.assertFalse(bi._barra(60, w)[1]["sobre_tope"])
        self.assertEqual(bi.n1_texto(0.25), "0,3")      # Math.round, no el bancario
        self.assertEqual(bi.pct_texto(12.5), "13 %")
        self.assertEqual(bi.n1_texto(-1.5), "−1,5")

    def test_sin_reglas_es_la_barra_de_siempre(self):
        _, panel, _ = panel_de("normal", reglas=None)
        self.assertFalse(panel["con_carga"])
        self.assertTrue(all(v["capacidad"] is None and not v["barra"]["tramos"]
                            for t in panel["tarjetas"] for v in t["ventanas"]))

    def test_nombre_de_cola_raro_sale_oculto(self):
        f = caso("normal")
        f["reglas"][0]["celdas"] = {"cola-diego": f["reglas"][0]["celdas"]["cola87"]}
        ahora = datetime.fromisoformat(f["ahora"]).astimezone(bi.TZ)
        margen, _, _ = panel_de("normal")
        panel = bi.panel_margen(margen, f["reglas"], ahora)
        codex = next(t for t in panel["tarjetas"] if t["cuenta"] == "codex")
        self.assertEqual(codex["leyenda"][0]["cola"], "«oculto»")


class CacheYMargenJson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        self.ahora = datetime(2026, 10, 4, 17, 49, 30, tzinfo=bi.TZ)

    def cache(self, escrito, reglas):
        ruta = self.d / "encargos-panel.json"
        ruta.write_text(json.dumps({"escrito": escrito.isoformat(), "momento": None, "reglas": reglas}), encoding="utf-8")
        return ruta

    def test_cache_fresco_viejo_roto_y_ausente(self):
        reglas = caso("normal")["reglas"]
        self.assertEqual(bi.leer_panel_cache(self.cache(self.ahora - timedelta(minutes=5), reglas), self.ahora), (reglas, ""))
        self.assertIsNone(bi.leer_panel_cache(self.cache(self.ahora - timedelta(minutes=16), reglas), self.ahora)[0])
        roto = self.d / "roto.json"
        roto.write_text("{no es json", encoding="utf-8")
        self.assertIsNone(bi.leer_panel_cache(roto, self.ahora)[0])
        self.assertIsNone(bi.leer_panel_cache(self.d / "no-existe.json", self.ahora)[0])
        self.assertIsNone(bi.leer_panel_cache(self.cache(self.ahora, {"no": "lista"}), self.ahora)[0])

    def test_margen_json_con_rutas_temporales(self):
        f = caso("pasado")
        uso = self.d / "uso.json"
        uso.write_text(json.dumps(f["uso"]), encoding="utf-8")
        viejo = (bi.USO_JSON, bi.REGISTRO, bi.recetas)
        self.addCleanup(lambda: setattr(bi, "USO_JSON", viejo[0]) or setattr(bi, "REGISTRO", viejo[1])
                        or setattr(bi, "recetas", viejo[2]))
        bi.USO_JSON, bi.REGISTRO, bi.recetas = str(uso), str(AQUI / "fixtures/avisos/cuentas.toml"), recetas
        ahora = datetime.fromisoformat(f["ahora"]).astimezone(bi.TZ)
        out = bi.margen_json(ahora, self.cache(ahora, f["reglas"]))
        self.assertEqual(out["carga_motivo"], "")
        self.assertEqual(out["panel"], panel_de("pasado")[1])
        json.dumps(out, ensure_ascii=False)     # lo que imprime --margen

    def test_margen_no_pide_root(self):
        if os.geteuid() == 0:
            self.skipTest("corre como root: no se puede ver si --margen pide root")
        p = subprocess.run([sys.executable, "-B", str(AQUI / "bots-info.py"), "--margen"], capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("panel", json.loads(p.stdout))

    def test_margen_corre_y_entrega_json_aunque_no_haya_nada(self):
        # Como root en esta copia: /opt no existe, así que sale sin margen, pero en JSON y sin escribir nada.
        antes = set(os.listdir(self.d))
        p = subprocess.run([sys.executable, "-B", str(AQUI / "bots-info.py"), "--margen"], capture_output=True,
                           text=True, timeout=60, cwd=self.d)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(set(json.loads(p.stdout)), {"momento", "margen", "panel", "carga_motivo"})
        self.assertEqual(set(os.listdir(self.d)), antes)


class PanelCache(unittest.TestCase):
    def test_guarda_solo_las_reglas_atomico_y_0644(self):
        with tempfile.TemporaryDirectory() as t:
            salida = Path(t) / "encargos-panel.json"
            panel = json.loads((AQUI / "fixtures/encargos/panel-46a-56b.json").read_text(encoding="utf-8"))
            corrida = lambda argv, **k: subprocess.CompletedProcess(argv, 0, json.dumps(panel), "")
            datos = pc.armar(pc.leer_panel("/no/importa/cola-run.py", corrida), datetime(2026, 10, 11, 12, tzinfo=pc.TZ))
            pc.escribir(str(salida), datos)
            leido = json.loads(salida.read_text(encoding="utf-8"))
            self.assertEqual(set(leido), {"escrito", "momento", "reglas"})
            self.assertEqual(leido["reglas"], panel["reglas"])
            self.assertEqual(salida.stat().st_mode & 0o777, 0o644)
            self.assertEqual(os.listdir(t), ["encargos-panel.json"])        # sin temporales
            ahora = datetime(2026, 10, 11, 12, 5, tzinfo=pc.TZ)
            self.assertEqual(bi.leer_panel_cache(salida, ahora), (panel["reglas"], ""))

    def test_panel_que_falla_no_toca_el_cache(self):
        with tempfile.TemporaryDirectory() as t:
            salida = Path(t) / "encargos-panel.json"
            salida.write_text('{"escrito": "x"}', encoding="utf-8")
            for corrida in (lambda argv, **k: subprocess.CompletedProcess(argv, 2, "", "boom"),
                            lambda argv, **k: subprocess.CompletedProcess(argv, 0, "no json", ""),
                            lambda argv, **k: subprocess.CompletedProcess(argv, 0, '{"reglas": 3}', "")):
                with self.assertRaises(ValueError):
                    pc.leer_panel("x", corrida)
            rc = pc.main(["--cola-run", str(Path(t) / "no-existe.py"), "--salida", str(salida)])
            self.assertEqual(rc, 1)
            self.assertEqual(salida.read_text(encoding="utf-8"), '{"escrito": "x"}')


if __name__ == "__main__":
    unittest.main()
