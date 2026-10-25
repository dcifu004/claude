#!/usr/bin/env python3
"""Pruebas de la fase plan (encargo 54): todo usa tmp_path y lanzadores falsos."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import tomllib
import unittest
from datetime import datetime, timezone
from pathlib import Path


AQUI = Path(__file__).resolve().parent


def cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, AQUI / "cola-run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FasePlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.e = Path(self.tmp.name)
        self.cr = cargar("cola_run_plan")
        self.git_foto_real = self.cr.git_foto
        self.git_base_guardar_real = self.cr.git_base_guardar
        self.anotar_real = self.cr.anotar
        self.cr.E = self.cr.D = self.cr.L = self.e
        (self.e / "54-fase-plan.md").write_text("encargo temporal\n", encoding="utf-8")
        self.cr.HISTORIAL = self.e / "historial.jsonl"
        self.cr.MANIFIESTO = {"nombre": "cola54", "pruebas": [], "etapa": []}
        self.cr.VIVO = {"eta": {"esperado": "2026-10-13T12:10", "min": "2026-10-13T12:01", "max": "2026-10-13T12:20"}}
        self.cr.ahora = lambda: datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
        self.cr.atender_pausa = self.cr.exigir_candado = self.cr.git_base_guardar = lambda *a, **k: None
        self.cr.esfuerzo_incompatible = lambda *a, **k: ""
        self.cr.modelo_de = lambda et, rol: {"modelo": "prueba", "esfuerzo": et.get(f"esfuerzo_{rol}", "high"), "nivel": "prueba"}
        self.cr.donde_fase = lambda *a: ""
        self.cr.chequear_cuota = lambda *a: ({"min": 10, "pct_5h": 1, "pct_sem": 1, "debil": False},
                                               {"5h": 0, "sem": 0, "fuente": "temporal", "momento": None})
        self.cr.git_foto = lambda *_: "foto"
        self.cr.log = lambda *_: None
        self.cr.anotar = lambda *a, **k: None
        self.cr.vivo = lambda **c: self.cr.VIVO.update(c)
        self.fases, self.prompts = [], []

        class Repo:
            def __init__(self, padre): self.padre = padre
            def git(self, *a):
                return type("R", (), {"stdout": self.padre.diff})()
        self.diff = b"encargos/54-PLAN.md\0"
        self.cr._VERS_MOD = type("V", (), {"abrir": lambda _, *a: Repo(self)})()

    def etapa(self):
        return {"id": "54", "encargo": "54-fase-plan.md", "autor": "codex", "revisor": "claude_cami", "vueltas": 1,
                "naturaleza": "seguridad", "plan": True}

    def preparar_main(self, guion):
        """`main()` real sobre árbol e historial git temporales; sólo el motor queda simulado."""
        self.cr.D, self.cr.E = self.e, self.e / "encargos"
        self.cr.E.mkdir()
        (self.cr.E / "54-fase-plan.md").write_text("encargo temporal\n", encoding="utf-8")
        self.cr.HISTORIAL = self.cr.E / "historial.jsonl"
        repo_dir = self.e.parent / "git-main"
        anterior = {k: os.environ.get(k) for k in ("VERSIONES_REPO", "VERSIONES_ARBOL")}
        os.environ.update(VERSIONES_REPO=str(repo_dir), VERSIONES_ARBOL=str(self.e))
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in anterior.items()])
        shutil.copy(AQUI / "46-fixtures" / "modelos.toml", self.cr.E / "modelos.toml")
        self.cr.MODELOS, self.cr.ESTADO = self.cr.E / "modelos.toml", self.cr.E / "COLA-ESTADO.md"
        self.cr.L = self.e.parent / f"{self.e.name}-logs"
        self.cr.L.mkdir()
        self.cr._VERS_MOD = None
        repo = self.cr._vers().abrir()
        repo.init()
        repo.foto("inicio")
        self.cr.git_foto = self.git_foto_real
        self.cr.git_base_guardar = self.git_base_guardar_real
        self.cr.anotar = self.anotar_real
        self.cr.pruebas = lambda: (set(), "")
        self.cr.foto = lambda: {}
        self.cr.desplegar = lambda *a: None
        self.cr.avisar_texto = lambda *a, **k: None
        self.cr.pedir_autorizacion = lambda *a: True
        self.cr.sesion_viva = lambda *a: False
        def vivo_realista(**cambios):
            self.cr.VIVO.update(cambios)
            if self.cr.VIVO.get("estado") == "corriendo":
                self.cr.VIVO["eta"] = {"esperado": "2026-10-13T12:10", "min": "2026-10-13T12:01", "max": "2026-10-13T12:20"}
            d = self.cr.E / "vivo"; d.mkdir(exist_ok=True)
            (d / "cola91.json").write_text(json.dumps(self.cr.VIVO), encoding="utf-8")
        self.cr.vivo = vivo_realista
        medida = {"5h": 1.0, "sem": 1.0, "renueva_5h": None, "renueva_sem": None,
                  "momento": "2026-10-13T12:00:00+00:00", "fuente": "fresco"}
        self.cr.medir = lambda *a: dict(medida)
        self.cr.chequear_cuota = lambda cid, rol, desde, modelo, esfuerzo="": (
            {"min": 1.0, "pct_5h": 1.0, "pct_sem": 1.0, "debil": False, "por_factor": None}, dict(medida))
        self.cr.correr = guion
        ruta = self.cr.E / "cola-91.toml"
        ruta.write_text('nombre = "cola91"\nmotivo = "arnés"\nesperar = []\ndespliegue = "nada"\npruebas = []\n\n'
                        '[[etapa]]\nid = "54"\nencargo = "54-fase-plan.md"\nautor = "codex"\nrevisor = "claude_cami"\n'
                        'vueltas = 1\nnaturaleza = "seguridad"\nplan = true\n', encoding="utf-8")
        return ruta

    def test_c1_c2_fases_y_pronostico(self):
        sin = dict(self.etapa(), plan=False)
        self.assertEqual([f for _, f, _, _ in self.cr.fases_pendientes([sin], "54", "autor")],
                         ["autor", "rev1", "fix1", "rev2"])
        con = self.cr.fases_restantes([self.etapa()], "54", "plan", datetime(2026, 10, 13, tzinfo=timezone.utc))
        self.assertEqual([x["fase"] for x in con[:3]], ["plan", "revplan", "plan2"])
        self.assertTrue(con[0]["debil"] and con[1]["debil"])
        self.assertEqual(self.cr.pronostico("codex", "plan", "prueba")["min"],
                         round(self.cr.pronostico("codex", "autor", "prueba")["min"] * .3, 1))
        for ruta in (AQUI / "cola-54.toml", AQUI / "46-fixtures" / "manifiestos" / "cola-46.toml"):
            etapa = tomllib.loads(ruta.read_text(encoding="utf-8"))["etapa"][0]
            self.assertFalse(etapa.get("plan", False))
            self.assertEqual([f for _, f, _, _ in self.cr.fases_pendientes([etapa], etapa["id"], "autor")][:2],
                             ["autor", "rev1"])

    def test_c3_plan_con_archivo_ajeno_se_detiene(self):
        # Repo.git() entrega bytes (versiones.py real), no el str de un doble de prueba.
        repo_dir = self.e.parent / "git-real"
        anterior = {k: os.environ.get(k) for k in ("VERSIONES_REPO", "VERSIONES_ARBOL")}
        os.environ.update(VERSIONES_REPO=str(repo_dir), VERSIONES_ARBOL=str(self.e))
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in anterior.items()])
        self.cr._VERS_MOD = None
        repo = self.cr._vers().abrir()
        repo.init()
        repo.foto("inicio")
        self.cr.git_foto = self.git_foto_real
        def correr(cid, prompt, nombre, *a):
            (self.e / "54-PLAN.md").write_text("plan válido\n", encoding="utf-8")
            (self.e / "ajeno.py").write_text("no permitido\n", encoding="utf-8")
            return {"min": 1, "sin_cuota": False, "rc": 0, "tokens": {}}
        self.cr.correr = correr
        with self.assertRaises(self.cr.Pausa):
            self.cr.etapa(self.etapa())
        self.assertIn("violación de plan", self.cr.VIVO["motivo_pausa"])

    def test_c4_rechazo_dos_veces_no_llega_a_codigo(self):
        def correr(cid, prompt, nombre, *a):
            self.fases.append(nombre.rsplit("-", 1)[1])
            if nombre.endswith("plan") or nombre.endswith("plan2"):
                (self.e / "54-PLAN.md").write_text("enfoque\n", encoding="utf-8")
            if nombre.endswith("revplan") or nombre.endswith("revplan2"):
                (self.e / "54rplan-RESULTADO.md").write_text("motivos\nPLAN RECHAZADO\n", encoding="utf-8")
            return {"min": 1, "sin_cuota": False, "rc": 0, "tokens": {}}
        self.cr.correr = correr
        self.assertFalse(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases, ["plan", "revplan", "plan2", "revplan2"])
        self.assertIn("rechazado dos veces", self.cr.VIVO["motivo_pausa"])

    def test_c5_autor_recibe_el_plan_aprobado_y_revplan_es_medium(self):
        def correr(cid, prompt, nombre, mod, *a):
            self.prompts.append((nombre, prompt, mod["esfuerzo"]))
            if nombre.endswith("revplan"):
                (self.e / "54rplan-RESULTADO.md").write_text("motivos\nPLAN APROBADO\n", encoding="utf-8")
            elif nombre.endswith("plan"):
                (self.e / "54-PLAN.md").write_text("PLAN APROBADO: alcance real\n", encoding="utf-8")
            elif nombre.endswith("rev1"):
                (self.e / "54r-RESULTADO.md").write_text("VEREDICTO: DESPLEGABLE\n", encoding="utf-8")
            return {"min": 1, "sin_cuota": False, "rc": 0, "tokens": {}}
        self.cr.correr = correr
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertIn("PLAN APROBADO: alcance real", next(p for n, p, _ in self.prompts if n.endswith("autor")))
        self.assertEqual(next(e for n, _, e in self.prompts if n.endswith("revplan")), "medium")

    def test_c6_balance_solo_segunda_vuelta_es_retrabajo(self):
        spec = importlib.util.spec_from_file_location("balance_plan", AQUI / "balance.py")
        bal = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bal)
        self.cr.anotar = self.anotar_real
        f = {"min": 1, "pct_5h": 1, "pct_sem": 1, "debil": False, "por_factor": None}
        antes = {"5h": 0, "sem": 0, "momento": None, "fuente": "temporal"}
        r = {"inicio": "2026-10-13T12:00:00+00:00", "min": 1, "tokens": {}, "sin_cuota": False}
        mod = {"modelo": "prueba", "esfuerzo": "medium", "nivel": "prueba", "naturaleza": "seguridad"}
        self.cr.medir = lambda *_: dict(antes)
        for fase in ("plan", "revplan", "plan2", "revplan2"):
            self.cr.anotar("54", fase, "codex", "plan" if fase.startswith("plan") else "revplan", f, antes, r, mod)
        filas = [json.loads(x) for x in self.cr.HISTORIAL.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(bal.medir(filas)["min_ret"], 2)

    def test_reanudar_main_desde_autor_no_repite_plan(self):
        fases, prompts = [], []
        def motor(cid, prompt, nombre, mod, *a):
            fase = nombre.rsplit("-", 1)[1]
            fases.append(fase); prompts.append(prompt)
            if fase == "plan":
                (self.cr.E / "54-PLAN.md").write_text("plan fijado\n", encoding="utf-8")
            elif fase == "revplan":
                (self.cr.E / "54rplan-RESULTADO.md").write_text("PLAN APROBADO\n", encoding="utf-8")
            elif fase == "autor" and fases.count("autor") == 1:
                return {"min": 1, "sin_cuota": True, "rc": 0, "tokens": {}, "modelo_real": mod["modelo"]}
            elif fase == "rev1":
                (self.cr.E / "54r-RESULTADO.md").write_text("VEREDICTO: DESPLEGABLE\n", encoding="utf-8")
            return {"min": 1, "sin_cuota": False, "rc": 0, "tokens": {}, "modelo_real": mod["modelo"]}
        ruta = self.preparar_main(motor)
        viejo = list(sys.argv)
        self.addCleanup(lambda: setattr(sys, "argv", viejo))
        sys.argv = ["cola-run.py", str(ruta)]
        self.assertEqual(self.cr.main(), 3, self.cr.VIVO)
        sys.argv = ["cola-run.py", str(ruta), "--desde", "54:autor"]
        self.assertEqual(self.cr.main(), 0)
        self.assertEqual(fases, ["plan", "revplan", "autor", "autor", "rev1"])
        self.assertIn("corrida anterior", prompts[3])

    def test_reanudar_segunda_vuelta_no_se_salta(self):
        for desde in ("plan2", "revplan2"):
            fases = []
            if desde == "revplan2":
                (self.e / "54-PLAN.md").write_text("plan de segunda vuelta\n", encoding="utf-8")
            def correr(cid, prompt, nombre, mod, *a):
                fase = nombre.rsplit("-", 1)[1]; fases.append(fase)
                if fase == "plan2":
                    (self.e / "54-PLAN.md").write_text("plan de segunda vuelta\n", encoding="utf-8")
                elif fase == "revplan2":
                    (self.e / "54rplan-RESULTADO.md").write_text("PLAN APROBADO\n", encoding="utf-8")
                elif fase == "rev1":
                    (self.e / "54r-RESULTADO.md").write_text("VEREDICTO: DESPLEGABLE\n", encoding="utf-8")
                return {"min": 1, "sin_cuota": False, "rc": 0, "tokens": {}}
            self.cr.correr = correr
            self.assertTrue(self.cr.etapa(self.etapa(), desde, reanuda=True))
            esperado = ["plan2", "revplan2", "autor", "rev1"] if desde == "plan2" else ["revplan2", "autor", "rev1"]
            self.assertEqual(fases, esperado)

    def test_plan_aprobado_cambiado_detiene_antes_de_revisar(self):
        fases = []
        def correr(cid, prompt, nombre, mod, *a):
            fase = nombre.rsplit("-", 1)[1]; fases.append(fase)
            if fase == "plan":
                (self.e / "54-PLAN.md").write_text("plan aprobado\n", encoding="utf-8")
            elif fase == "revplan":
                (self.e / "54rplan-RESULTADO.md").write_text("PLAN APROBADO\n", encoding="utf-8")
            elif fase == "autor":
                (self.e / "54-PLAN.md").write_text("plan cambiado\n", encoding="utf-8")
            return {"min": 1, "sin_cuota": False, "rc": 0, "tokens": {}}
        self.cr.correr = correr
        self.assertFalse(self.cr.etapa(self.etapa()))
        self.assertEqual(fases, ["plan", "revplan", "autor"])
        self.assertIn("inmutable", self.cr.VIVO["motivo_pausa"])


if __name__ == "__main__":
    unittest.main()
