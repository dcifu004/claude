#!/usr/bin/env python3
"""Pruebas del cierre barato en rev2/rev3 (encargo 87). Todo corre en un temporal: árbol e historial git
propios (versiones.py real, VERSIONES_REPO/VERSIONES_ARBOL), historial.jsonl temporal y un motor falso que
captura la instrucción. Ni `claude` ni `codex` reales, ni red, ni avisos, ni /opt/nodo."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FIJAS = AQUI / "87-fixtures"
os.environ["NODO_PRUEBAS"] = "1"


def cargar(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fila_real(fase: str, rol: str) -> dict:
    """Una fila de verdad de historial.jsonl: la forma (claves, tipos, hora) es la que escribe anotar()."""
    for x in reversed((AQUI / "historial.jsonl").read_text(encoding="utf-8").splitlines()):     # la más reciente
        try:
            f = json.loads(x)
        except ValueError:
            continue
        if f.get("fase") == fase and f.get("rol") == rol and isinstance(f.get("min"), (int, float)):
            return f
    raise AssertionError(f"no hay fila real {fase}/{rol}")


R1 = "# Revisión 1\n\n### [Grave] H1 la función suma mal\nMARCA_R1_UNICA\n\nVEREDICTO: NO DESPLEGABLE\n"
MODULO = "".join(f"def f{k}():\n    return {k}\n" for k in range(50))       # 100 líneas


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = Path(self.tmp.name)
        self.arbol, self.e = raiz / "arbol", raiz / "arbol" / "encargos"
        self.e.mkdir(parents=True)
        anterior = {k: os.environ.get(k) for k in ("VERSIONES_REPO", "VERSIONES_ARBOL")}
        os.environ.update(VERSIONES_REPO=str(raiz / "git"), VERSIONES_ARBOL=str(self.arbol))
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in anterior.items()])
        cr = self.cr = cargar(AQUI / "cola-run.py", f"cola_run_87_{id(self)}")
        cr.D, cr.E, cr.L = self.arbol, self.e, raiz / "logs"
        cr.L.mkdir()
        shutil.copy(AQUI / "46-fixtures" / "modelos.toml", self.e / "modelos.toml")
        (self.e / "87-revision-escalonada.md").write_text("encargo temporal\n", encoding="utf-8")
        cr.MODELOS, cr.HISTORIAL, cr.REGISTROS = self.e / "modelos.toml", raiz / "historial.jsonl", ()
        cr.ESTADO = raiz / "COLA-ESTADO.md"
        cr.PLANTILLA_REV = AQUI / "revision-plantilla-v2.md"
        cr.PLANTILLA_CIERRE = AQUI / "revision-cierre-plantilla.md"
        cr.MANIFIESTO = {"nombre": "cola87t", "pruebas": ["encargos/test_x.py"], "etapa": []}
        cr.VIVO = {}
        cr.GIT_BASE.clear()
        cr._VERS_MOD = None
        repo = cr._vers().abrir()
        repo.init()
        repo.foto("inicio")
        cr.ahora = lambda: datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
        cr.log = lambda texto: self.logs.append(texto)
        cr.atender_pausa = lambda *a: None
        cr.sesion_viva = lambda *a: False
        cr.avisar_texto = lambda *a, **k: None
        self.medida = {"5h": 1.0, "sem": 1.0, "renueva_5h": None, "renueva_sem": None,
                       "momento": "2026-10-25T12:00:00+00:00", "fuente": "fresco"}
        cr.medir = lambda *a: dict(self.medida)
        self.cuota, self.vivos, self.consultas, self.llamadas, self.logs = [], [], [], [], []

        def chequear(cid, rol, desde, modelo="", esfuerzo=""):
            self.cuota.append((rol, modelo, esfuerzo))
            if rol == "cierre" and self.antes_del_cierre:
                self.antes_del_cierre()
            return cr.pronostico(cid, rol, modelo, "", esfuerzo), dict(self.medida)
        cr.chequear_cuota = chequear
        self.antes_del_cierre = None

        def vivo(**cambios):
            cr.VIVO.update(cambios)
            cr.VIVO["eta"] = {"esperado": "2026-10-25T12:10", "min": "2026-10-25T12:01", "max": "2026-10-25T12:20"}
            self.vivos.append(dict(cr.VIVO))
        cr.vivo = vivo
        cr.consultar_o_seguir = lambda et, fase, texto: self.consultas.append((fase, texto))
        self.guion = {}
        cr.correr = self.motor

    # -- motor falso ------------------------------------------------------------------------------
    def motor(self, cid, prompt, nombre, mod=None, herramientas=None, limite_s=None):
        fase = nombre.split("-", 1)[1]
        self.llamadas.append({"fase": fase, "cid": cid, "modelo": mod["modelo"], "esfuerzo": mod["esfuerzo"],
                              "nivel": mod["nivel"], "prompt": prompt, "limite_s": limite_s})
        r = {"rc": 0, "min": 1.0, "tokens": {"total": 1}, "sin_cuota": False, "modelo_real": mod["modelo"]}
        accion = self.guion.get(fase, self.por_defecto.get(fase))
        if accion:
            r.update(accion() or {})
        return r

    def escribir(self, rel, texto):
        p = self.arbol / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")

    def cambiar_lineas(self, rel, n):
        """Reemplaza las primeras `n` líneas de un archivo: 2·n líneas en --numstat."""
        p = self.arbol / rel
        lineas = p.read_text(encoding="utf-8").splitlines(keepends=True)
        p.write_text("".join(f"# cambiada {k}\n" for k in range(n)) + "".join(lineas[n:]), encoding="utf-8")

    @property
    def por_defecto(self):
        return {
            "autor": lambda: (self.escribir("encargos/modulo.py", MODULO),
                              self.escribir("encargos/otro.py", "SOLO_DEL_AUTOR = 1\n"),
                              self.escribir("encargos/87-RESULTADO.md", "# Resultado\n")) and None,
            "rev1": lambda: self.escribir("encargos/87r-RESULTADO.md", R1),
            "fix1": lambda: self.cambiar_lineas("encargos/modulo.py", 10),
            "rev2-cierre": lambda: self.escribir("encargos/87r-RESULTADO.md", "H1 cerrado\n\nVEREDICTO: DESPLEGABLE\n"),
            "rev2": lambda: self.escribir("encargos/87r-RESULTADO.md", "completa\nVEREDICTO: DESPLEGABLE\n"),
            "fix2": lambda: self.cambiar_lineas("encargos/modulo.py", 3),
            "rev3-cierre": lambda: self.escribir("encargos/87r-RESULTADO.md", "VEREDICTO: DESPLEGABLE\n"),
            "rev3": lambda: self.escribir("encargos/87r-RESULTADO.md", "VEREDICTO: DESPLEGABLE\n"),
        }

    def etapa(self, **extra):
        et = {"id": "87", "encargo": "87-revision-escalonada.md", "autor": "claude_cami", "revisor": "codex",
              "vueltas": 2, "naturaleza": "seguridad", "cierre_barato": True}
        et.update(extra)
        self.cr.MANIFIESTO["etapa"] = [et]
        return et

    def historial(self):
        if not self.cr.HISTORIAL.exists():
            return []
        return [json.loads(x) for x in self.cr.HISTORIAL.read_text(encoding="utf-8").splitlines()]

    def fases_roles(self):
        return [(f["fase"], f["rol"]) for f in self.historial()]


class C1SinCambiosPorDefecto(Base):
    def test_simular_igual_byte_a_byte_a_la_foto_base(self):
        gen = cargar(FIJAS / "genera-simular-antes.py", "genera_simular_87")
        for n in ("82", "85"):
            rc, salida = gen.simular(AQUI / "cola-run.py", FIJAS / f"cola-{n}.toml")
            self.assertEqual(rc, 0)
            self.assertEqual(salida.encode("utf-8"), (FIJAS / f"simular-antes-{n}.txt").read_bytes(), n)

    def test_manifiestos_de_c1_son_copias_reales(self):
        for n in ("82", "85"):
            self.assertEqual((FIJAS / f"cola-{n}.toml").read_bytes(), (AQUI / f"cola-{n}.toml").read_bytes())

    def test_corrida_de_dos_vueltas_sin_campo(self):
        et = self.etapa()
        del et["cierre_barato"]
        self.guion = {"rev2": lambda: self.escribir("encargos/87r-RESULTADO.md", R1),
                      "rev3": lambda: self.escribir("encargos/87r-RESULTADO.md", R1)}
        self.assertFalse(self.cr.etapa(et))
        self.assertEqual(self.fases_roles(), [("autor", "autor"), ("rev1", "rev"), ("fix1", "fix"),
                                              ("rev2", "rev"), ("fix2", "fix"), ("rev3", "rev")])
        self.assertNotIn("cierre", [c[0] for c in self.cuota])
        self.assertTrue(all(ll["limite_s"] is None for ll in self.llamadas))
        self.assertEqual(set(self.historial()[0]), set(fila_real("rev2", "rev")))
        self.assertFalse(any("rol" in v for v in self.vivos))

    def test_cierre_barato_que_no_es_true_no_aplica(self):
        for valor in (False, "true", 1, None):
            self.assertFalse(self.cr.cierre_aplica(self.etapa(cierre_barato=valor), "rev2"))


class C2VaAlCierre(Base):
    def test_fix_de_20_lineas_corre_cierre_con_agil_y_solo_su_diff(self):
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles(), [("autor", "autor"), ("rev1", "rev"), ("fix1", "fix"), ("rev2", "cierre")])
        cierre = next(ll for ll in self.llamadas if ll["fase"] == "rev2-cierre")
        self.assertEqual((cierre["cid"], cierre["modelo"], cierre["esfuerzo"], cierre["nivel"]),
                         ("codex", "gpt-reserve", "medium", "agil"))
        self.assertEqual(cierre["limite_s"], self.cr.CIERRE_MAX_MIN * 60)
        self.assertIn("MARCA_R1_UNICA", cierre["prompt"])
        self.assertIn("+# cambiada 9", cierre["prompt"])
        self.assertNotIn("SOLO_DEL_AUTOR", cierre["prompt"])     # el diff del autor no va
        self.assertNotIn("-diff.txt", cierre["prompt"])
        self.assertNotIn("{", cierre["prompt"].split("## Revisión 1")[0])  # sin marcadores sin reemplazar
        fila = self.historial()[-1]
        self.assertEqual((fila["modelo"], fila["nivel"], fila["veredicto"]), ("gpt-reserve", "agil", "DESPLEGABLE"))
        self.assertEqual(set(fila), set(fila_real("rev2", "rev")))
        self.assertIn(("cierre", "gpt-reserve", "medium"), self.cuota)

    def test_vivo_muestra_rol_cierre_solo_durante_el_cierre(self):
        self.guion = {"rev2-cierre": lambda: self.escribir("encargos/87r-RESULTADO.md", "VEREDICTO: ESCALAR\n")}
        self.assertTrue(self.cr.etapa(self.etapa()))
        con_rol = [v for v in self.vivos if v.get("rol") == "cierre"]
        self.assertEqual([(v["fase"], v["modelo"]) for v in con_rol], [("rev2", "gpt-reserve medium")])
        ultima_rev2 = [v for v in self.vivos if v.get("fase") == "rev2"][-1]
        self.assertNotIn("rol", ultima_rev2)
        self.assertEqual(ultima_rev2["modelo"], "gpt-5.6-terra xhigh")

    def test_plantilla_recibe_arreglos_y_plan(self):
        (self.e / "87-PLAN.md").write_text("PLAN_MARCA\n", encoding="utf-8")
        (self.e / "87r1-RESULTADO.md").write_text(R1, encoding="utf-8")
        (self.e / "87-RESULTADO.md").write_text("# R\n\n## Arreglos vuelta 1\nARREGLO_MARCA {ID}\n\n## Otra\nFUERA\n",
                                                encoding="utf-8")
        self.cr.MANIFIESTO["pruebas"] = ["encargos/test_x.py"]
        txt = self.cr.prompt_cierre(self.etapa(plan=True), "rev2", "DIFF_MARCA\n")
        for marca in ("PLAN_MARCA", "ARREGLO_MARCA {ID}", "DIFF_MARCA", "MARCA_R1_UNICA", "fix1", "encargos/87r-RESULTADO.md"):
            self.assertIn(marca, txt)
        self.assertNotIn("FUERA", txt)


class C3Escala(Base):
    def correr_y_ver_completa(self, motivo):
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles(), [("autor", "autor"), ("rev1", "rev"), ("fix1", "fix"), ("rev2", "rev")])
        rev2 = self.historial()[-1]
        self.assertEqual((rev2["modelo"], rev2["esfuerzo"], rev2["nivel"]), ("gpt-5.6-terra", "xhigh", "maximo"))
        self.assertFalse([ll for ll in self.llamadas if ll["fase"].endswith("cierre")])
        self.assertTrue(any(motivo in x for x in self.logs), self.logs)

    def test_e1_archivo_nuevo_para_la_etapa(self):
        self.guion = {"fix1": lambda: self.escribir("encargos/nuevo.py", "x = 1\n")}
        self.correr_y_ver_completa("E1: fix1 toca archivos que no estaban en el diff de la etapa: encargos/nuevo.py")

    def test_e2_unidad_systemd(self):
        autor = self.por_defecto["autor"]
        self.guion = {"autor": lambda: (autor(), self.escribir("pi/x.service", "[Unit]\n")) and None,
                      "fix1": lambda: self.escribir("pi/x.service", "[Unit]\nDescription=x\n")}
        self.correr_y_ver_completa("E2: fix1 toca rutas sensibles: pi/x.service")

    def test_e2_modelos_toml(self):
        autor = self.por_defecto["autor"]
        agrega = lambda texto: (self.e / "modelos.toml").write_text(
            (self.e / "modelos.toml").read_text(encoding="utf-8") + texto, encoding="utf-8")
        self.guion = {"autor": lambda: (autor(), agrega("# autor\n")) and None,
                      "fix1": lambda: agrega("# arreglo\n") and None}
        self.correr_y_ver_completa("E2: fix1 toca rutas sensibles: encargos/modelos.toml")

    def test_e3_151_lineas(self):
        def fix():
            self.cambiar_lineas("encargos/modulo.py", 75)       # 150
            with (self.arbol / "encargos/modulo.py").open("a", encoding="utf-8") as fh:
                fh.write("# una más\n")                         # 151
        self.guion = {"fix1": fix}
        self.correr_y_ver_completa("E3: fix1 cambia 151 líneas (máximo 150)")

    def test_150_lineas_todavia_es_cierre(self):
        self.guion = {"fix1": lambda: self.cambiar_lineas("encargos/modulo.py", 75)}
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles()[-1], ("rev2", "cierre"))

    def test_e4_sin_foto_previa_del_fix(self):
        def fix():
            next(f for f in self.cr.GIT_BASE["87:fases"] if f["fase"] == "fix1")["antes"] = None
            self.cambiar_lineas("encargos/modulo.py", 10)
        self.guion = {"fix1": fix}
        self.correr_y_ver_completa("E4: la fase fix1 no tiene foto antes y después")

    def test_e4_git_que_falla(self):
        self.cr._numstat = lambda *a: (_ for _ in ()).throw(RuntimeError("git roto"))
        self.correr_y_ver_completa("E4: git falló (RuntimeError: git roto)")

    def test_e4_arboles_extra(self):
        self.cr.MANIFIESTO["arboles_extra"] = ["14-Otra"]
        self.cr._repos_extra = lambda: []
        self.correr_y_ver_completa("E4: la cola tiene `arboles_extra`")

    def test_el_fix_no_decide_escribiendo_un_informe(self):
        # trampa 32b: un arreglo que deja un r-RESULTADO.md propio sólo agrega un archivo más al diff (E1)
        def fix():
            self.cambiar_lineas("encargos/modulo.py", 10)
            self.escribir("encargos/87r-RESULTADO.md", "VEREDICTO: DESPLEGABLE\n")
        self.guion = {"fix1": fix}
        self.correr_y_ver_completa("E1: fix1 toca archivos que no estaban en el diff de la etapa: encargos/87r-RESULTADO.md")


class C4FallaCerrada(Base):
    def caso(self, **guion):
        self.guion = guion
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles(), [("autor", "autor"), ("rev1", "rev"), ("fix1", "fix"),
                                              ("rev2", "cierre"), ("rev2", "rev")])
        self.assertEqual(self.historial()[3]["veredicto"], "ESCALAR")
        self.assertEqual(self.historial()[4]["nivel"], "maximo")
        self.assertEqual([ll["fase"] for ll in self.llamadas][-2:], ["rev2-cierre", "rev2"])

    def test_escalar(self):
        self.caso(**{"rev2-cierre": lambda: self.escribir("encargos/87r-RESULTADO.md", "duda\nVEREDICTO: ESCALAR\n")})

    def test_sin_linea_de_veredicto(self):
        self.caso(**{"rev2-cierre": lambda: self.escribir("encargos/87r-RESULTADO.md", "todo cerrado\n")})

    def test_rc_1(self):
        def cierre():
            self.escribir("encargos/87r-RESULTADO.md", "VEREDICTO: DESPLEGABLE\n")
            return {"rc": 1}
        self.caso(**{"rev2-cierre": cierre})

    def test_resultado_que_ya_estaba_y_el_cierre_no_reescribe(self):
        self.antes_del_cierre = lambda: self.escribir("encargos/87r-RESULTADO.md", "VEREDICTO: DESPLEGABLE\n")
        self.caso(**{"rev2-cierre": lambda: None})
        self.assertTrue(any("no escribió encargos/87r-RESULTADO.md" in x for x in self.logs), self.logs)

    def test_desplegable_en_la_linea_10_de_40(self):
        texto = "".join("VEREDICTO: DESPLEGABLE\n" if k == 9 else f"línea {k + 1}\n" for k in range(40))
        self.caso(**{"rev2-cierre": lambda: self.escribir("encargos/87r-RESULTADO.md", texto)})

    def test_veredicto_con_espacios_o_mayusculas_raras(self):
        for raro in (" VEREDICTO: DESPLEGABLE", "VEREDICTO: DESPLEGABLE ", "veredicto: Desplegable",
                     "VEREDICTO:  DESPLEGABLE", "**VEREDICTO: DESPLEGABLE**"):
            self.assertEqual(self.cr.veredicto_cierre(f"x\n{raro}\n"), "", raro)
        self.assertEqual(self.cr.veredicto_cierre("VEREDICTO: DESPLEGABLE\nVEREDICTO: NO DESPLEGABLE\n"), "")
        self.assertEqual(self.cr.veredicto_cierre("x\nVEREDICTO: DESPLEGABLE\n\n"), "DESPLEGABLE")
        self.caso(**{"rev2-cierre": lambda: self.escribir("encargos/87r-RESULTADO.md", "x\n veredicto: Desplegable \n")})

    def test_corte_por_tiempo(self):
        self.caso(**{"rev2-cierre": lambda: (self.escribir("encargos/87r-RESULTADO.md", "VEREDICTO: DESPLEGABLE\n"),
                                             {"rc": 124, "corte": "tiempo"})[1]})
        self.assertTrue(any("corte por tiempo" in x for x in self.logs), self.logs)

    def test_correr_corta_por_tiempo_de_verdad(self):
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        (bin_dir / "claude").write_text("#!/bin/sh\nexec sleep 5\n", encoding="utf-8")
        (bin_dir / "claude").chmod(0o755)
        viejo = os.environ["PATH"]
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{viejo}"
        self.addCleanup(lambda: os.environ.__setitem__("PATH", viejo))
        cr = self.cr
        r = cr._correr(cr.MOTORES["claude_diego"], "claude_diego", "hola", "87-rev2-cierre", {}, cr.HERRAMIENTAS,
                       dict(os.environ), limite_s=0.5)
        self.assertEqual((r["rc"], r["corte"], r["sin_cuota"]), (124, "tiempo", False))
        self.assertIn("cortado", (cr.L / "87-rev2-cierre.log").read_text(encoding="utf-8"))


class C5NoDesplegableDelCierre(Base):
    def test_sigue_fix2_con_la_consulta_y_copia_r2(self):
        r2 = "### [Media] H1 sigue abierto\n\nVEREDICTO: NO DESPLEGABLE\n"
        self.guion = {"rev2-cierre": lambda: self.escribir("encargos/87r-RESULTADO.md", r2)}
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles(), [("autor", "autor"), ("rev1", "rev"), ("fix1", "fix"), ("rev2", "cierre"),
                                              ("fix2", "fix"), ("rev3", "cierre")])
        self.assertEqual((self.e / "87r2-RESULTADO.md").read_text(encoding="utf-8"), r2)
        self.assertEqual(self.consultas, [("rev1", R1), ("rev2", r2)])
        self.assertEqual(self.historial()[3]["veredicto"], "NO DESPLEGABLE")
        fix2 = next(ll for ll in self.llamadas if ll["fase"] == "fix2")
        self.assertIn("encargos/87r2-RESULTADO.md", fix2["prompt"])


class C6PronosticoYBalance(Base):
    def test_pronostico_cierre_sin_historial_no_es_keyerror(self):
        for cid, modelo in (("codex", "gpt-reserve"), ("claude_cami", "claude-sonnet-5-5")):
            f, rev = self.cr.pronostico(cid, "cierre", modelo, "", "medium"), self.cr.pronostico(cid, "rev", modelo, "", "medium")
            self.assertEqual(f["min"], round(rev["min"] * .3, 1))
            self.assertTrue(f["debil"])
            self.assertEqual(self.cr.etiqueta_pronostico(f), "débil, factor 0,3")

    def test_fases_pendientes_y_restantes(self):
        et = self.etapa()
        self.assertEqual([(f, r) for _, f, r, _ in self.cr.fases_pendientes([et], "87", "autor")],
                         [("autor", "autor"), ("rev1", "rev"), ("fix1", "fix"), ("rev2", "cierre"),
                          ("fix2", "fix"), ("rev3", "cierre")])
        filas = self.cr.fases_restantes([et], "87", "autor", datetime(2026, 10, 25, tzinfo=timezone.utc))
        cierres = [x for x in filas if x["rol"] == "cierre"]
        self.assertEqual([(x["fase"], x["cuenta"], x["modelo"], x["debil"]) for x in cierres],
                         [("rev2", "codex", "gpt-reserve", True), ("rev3", "codex", "gpt-reserve", True)])
        remota = self.etapa(donde="pc2503", arnes="x", prompt="y")
        self.assertFalse(self.cr.cierre_aplica(remota, "rev2"))
        self.assertNotIn("cierre", [r for _, _, r, _ in self.cr.fases_pendientes([remota], "87", "autor")])

    def test_restante_maximo_supone_completa(self):
        con, sin = self.etapa(), dict(self.etapa(), cierre_barato=False)
        r_con, r_sin = self.cr.restante([con], "87", "autor", 0), self.cr.restante([sin], "87", "autor", 0)
        cierre = self.cr.pronostico("codex", "cierre", "gpt-reserve", "", "medium")["min"]
        self.assertAlmostEqual(r_con["max"], round(r_sin["max"] + 2 * cierre, 1), places=1)
        self.assertLess(r_con["esperado"], r_sin["esperado"])
        self.assertEqual(r_con["min"], r_sin["min"])

    def test_simular_con_el_campo_muestra_cierre(self):
        gen = cargar(FIJAS / "genera-simular-antes.py", "genera_simular_87c")
        ruta = Path(self.tmp.name) / "cola-82c.toml"
        ruta.write_text((FIJAS / "cola-82.toml").read_text(encoding="utf-8")
                        .replace('naturaleza = "seguridad"', 'naturaleza = "seguridad"\ncierre_barato = true'),
                        encoding="utf-8")
        rc, salida = gen.simular(AQUI / "cola-run.py", ruta)
        self.assertEqual(rc, 0)
        linea = next(x for x in salida.splitlines() if x.startswith("  cierre codex"))
        self.assertIn("gpt-reserve medium", linea)
        self.assertIn("[agil]", linea)
        self.assertTrue(linea.endswith("[débil, factor 0,3]"), linea)
        self.assertIn("cierre: rev2+", salida)

    def test_balance_real_igual_y_cierre_sintetico_es_retrabajo(self):
        bal = cargar(AQUI / "balance.py", "balance_87")
        real = AQUI / "historial.jsonl"
        lineas = real.read_text(encoding="utf-8").splitlines()
        sin_cierre = Path(self.tmp.name) / "historial-sin-cierre.jsonl"
        sin_cierre.write_text("\n".join(x for x in lineas if '"rol": "cierre"' not in x) + "\n", encoding="utf-8")

        def salida(ruta):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(bal.principal(["--historial", str(ruta), "--manifiestos", str(AQUI), "--desde", "47"]), 0)
            return out.getvalue()
        self.assertEqual(salida(real), salida(sin_cierre))
        fila = dict(fila_real("rev2", "rev"), rol="cierre", encargo="87")
        self.assertEqual(bal.medir([fila])["min_ret"], fila["min"])
        self.assertEqual(bal.medir([dict(fila, fase="rev1")])["min_ret"], 0)

    def test_candado_y_esfuerzo_del_cierre(self):
        et = self.etapa(modelo_cierre="gpt-6-astra")
        self.assertEqual(self.cr.modelos_con_candado([et]), {"gpt-6-astra": ["87 cierre"]})
        self.assertEqual(self.cr.modelos_con_candado([dict(et, cierre_barato=False)]), {})
        self.assertEqual(self.cr.modelo_de(self.etapa(esfuerzo_cierre="low"), "cierre"),
                         {"modelo": "gpt-reserve", "esfuerzo": "low", "nivel": "agil"})
        self.cr.pedir_autorizacion = lambda *a: False
        self.cr.MANIFIESTO["etapa"] = [et]
        with self.assertRaises(self.cr.Pausa):
            self.cr.exigir_candado(et, "cierre", self.cr.modelo_de(et, "cierre"), "87:rev2")


class C7PausaYDesde(Base):
    def test_cierre_sin_cuota_pausa_y_desde_recalcula(self):
        self.guion = {"rev2-cierre": lambda: {"sin_cuota": True}}
        with self.assertRaises(self.cr.Pausa) as p:
            self.cr.etapa(self.etapa())
        self.assertEqual(p.exception.desde, "87:rev2")
        self.assertEqual(self.fases_roles()[-1], ("rev2", "cierre"))
        # Relanzamiento: GIT_BASE se recupera del archivo y la decisión se vuelve a tomar con lo de ahora.
        self.cr.GIT_BASE.clear()
        self.cr.git_base_cargar()
        self.assertTrue(self.cr.GIT_BASE.get("87:fases"))
        self.cr.CIERRE_MAX_LINEAS = 5
        self.guion = {}
        self.assertTrue(self.cr.etapa(self.etapa(), "rev2", reanuda=True))
        self.assertEqual(self.fases_roles()[-1], ("rev2", "rev"))
        self.assertTrue(any("E3: fix1 cambia 20 líneas (máximo 5)" in x for x in self.logs), self.logs)

    def test_desde_rev2_sin_cambio_vuelve_a_cierre(self):
        self.guion = {"rev2-cierre": lambda: {"sin_cuota": True}}
        with self.assertRaises(self.cr.Pausa):
            self.cr.etapa(self.etapa())
        self.guion = {}
        self.assertTrue(self.cr.etapa(self.etapa(), "rev2", reanuda=True))
        self.assertEqual([f for f in self.fases_roles() if f[0] == "rev2"], [("rev2", "cierre"), ("rev2", "cierre")])


# ------------------------------------------------------------------------------------- 87b (arreglos vuelta 1)
SECRETO = "SECRETO_DE_AFUERA_87B"


class C8EnlacesSimbolicos(Base):
    """Hallazgo 1: los informes que lee el cierre no siguen enlaces. Ante uno, revisión completa."""

    def afuera(self, texto):
        ruta = Path(self.tmp.name) / "afuera.md"          # fuera de encargos/ (y del árbol)
        ruta.write_text(texto, encoding="utf-8")
        return ruta

    def completa_sin_secreto(self, motivo):
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles(), [("autor", "autor"), ("rev1", "rev"), ("fix1", "fix"), ("rev2", "rev")])
        self.assertFalse([ll for ll in self.llamadas if ll["fase"].endswith("cierre")])
        self.assertNotIn("cierre", [c[0] for c in self.cuota])
        self.assertFalse([ll for ll in self.llamadas if SECRETO in ll["prompt"]])
        self.assertTrue(any(motivo in x for x in self.logs), self.logs)

    def test_resultado_del_autor_reemplazado_por_un_enlace(self):
        externo = self.afuera(f"# R\n\n## Arreglos vuelta 1\n{SECRETO}\n")

        def fix():
            self.cambiar_lineas("encargos/modulo.py", 10)
            (self.e / "87-RESULTADO.md").unlink()
            (self.e / "87-RESULTADO.md").symlink_to(externo)
        self.guion = {"fix1": fix}
        self.completa_sin_secreto("E4: encargos/87-RESULTADO.md no se puede abrir sin seguir enlaces")

    def test_revision_previa_reemplazada_por_un_enlace_justo_antes_del_cierre(self):
        externo = self.afuera(f"{SECRETO}\nVEREDICTO: NO DESPLEGABLE\n")
        r1 = self.e / "87r1-RESULTADO.md"
        # Pasa la decisión y cambia antes de armar el prompt: prompt_cierre también lo rechaza.
        decidir = self.cr.decidir_cierre

        def decidir_y_cambiar(et, fase):
            res = decidir(et, fase)
            r1.unlink()
            r1.symlink_to(externo)
            return res
        self.cr.decidir_cierre = decidir_y_cambiar
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertFalse([ll for ll in self.llamadas if ll["fase"].endswith("cierre")])
        self.assertNotIn("cierre", [c[0] for c in self.cuota])          # ni siquiera esperó cuota
        self.assertFalse([ll for ll in self.llamadas if SECRETO in ll["prompt"]])
        self.assertEqual(self.fases_roles()[-1], ("rev2", "rev"))
        self.assertTrue(any("87r1-RESULTADO.md no se puede abrir sin seguir enlaces" in x for x in self.logs), self.logs)

    def test_informe_final_del_cierre_que_es_un_enlace_escala(self):
        externo = self.afuera("todo bien\nVEREDICTO: DESPLEGABLE\n")
        self.guion = {"rev2-cierre": lambda: (self.e / "87r-RESULTADO.md").symlink_to(externo)}
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles(), [("autor", "autor"), ("rev1", "rev"), ("fix1", "fix"),
                                              ("rev2", "cierre"), ("rev2", "rev")])
        self.assertEqual(self.historial()[3]["veredicto"], "ESCALAR")
        self.assertTrue(any("87r-RESULTADO.md no se puede abrir sin seguir enlaces" in x for x in self.logs), self.logs)

    def test_leer_informe(self):
        cr, e = self.cr, self.e
        (e / "ok.md").write_text("hola ñ\n", encoding="utf-8")
        self.assertEqual(cr.leer_informe(e / "ok.md"), "hola ñ\n")
        (e / "enlace.md").symlink_to(e / "ok.md")                     # enlace aunque apunte adentro
        (e / "grande.md").write_bytes(b"x" * (cr.CIERRE_MAX_BYTES + 1))
        (e / "binario.md").write_bytes(b"\xff\xfe\x00")
        os.link(e / "ok.md", e / "duro.md")                            # dos nombres
        os.mkfifo(e / "fifo.md")
        (e / "carpeta.md").mkdir()
        (Path(self.tmp.name) / "fuera.md").write_text("x", encoding="utf-8")
        for malo in ("enlace.md", "grande.md", "binario.md", "duro.md", "fifo.md", "carpeta.md", "no-existe.md"):
            with self.assertRaises(cr.InformeInseguro, msg=malo):
                cr.leer_informe(e / malo)
        with self.assertRaises(cr.InformeInseguro):
            cr.leer_informe(e / ".." / "fuera.md")
        (e / "sub").mkdir()
        (e / "sub" / "x.md").write_text("x", encoding="utf-8")
        with self.assertRaises(cr.InformeInseguro):
            cr.leer_informe(e / "sub" / "x.md")


def vivo_pid(pid: int) -> bool:
    """Si el PID existe y no es un zombi (un zombi ya no ejecuta nada; lo recoge init)."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            return fh.read().decode("ascii", "replace").rsplit(")", 1)[-1].split()[0] not in ("Z", "X")
    except OSError:
        return False


class C9GrupoDeProcesos(Base):
    """Hallazgo 2: el CLI corre en su propio grupo y el grupo entero muere al cortar o al terminar, en toda fase."""

    def cli(self, nombre, cuerpo):
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / nombre).write_text("#!/bin/sh\n" + cuerpo, encoding="utf-8")
        (bin_dir / nombre).chmod(0o755)
        viejo = os.environ["PATH"]
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{viejo}"
        self.addCleanup(lambda: os.environ.__setitem__("PATH", viejo))
        self.pidfile = Path(self.tmp.name) / "hijo.pid"
        self.addCleanup(self.matar_hijo)

    def matar_hijo(self):          # si la prueba falla, el hijo no queda vivo
        try:
            os.kill(int(self.pidfile.read_text()), 9)
        except (OSError, ValueError):
            pass

    def hijo(self):
        self.assertTrue(self.pidfile.exists(), "el CLI falso no alcanzó a lanzar su hijo")
        return int(self.pidfile.read_text())

    def correr(self, motor, fase, limite_s=None):
        cr = self.cr
        cid = "claude_diego" if motor == "claude" else "codex"
        t0 = time.monotonic()
        r = cr._correr(cr.MOTORES[cid], cid, "hola", f"87-{fase}", {}, cr.HERRAMIENTAS, dict(os.environ),
                       limite_s=limite_s)
        return r, time.monotonic() - t0

    def test_corte_por_tiempo_mata_al_hijo(self):
        self.cli("claude", f"sleep 30 >/dev/null 2>&1 &\necho $! > {self.tmp.name}/hijo.pid\nsleep 30\n")
        r, dur = self.correr("claude", "rev2-cierre", limite_s=1.0)
        self.assertEqual((r["rc"], r["corte"], r["sin_cuota"]), (124, "tiempo", False))
        self.assertLess(dur, 10)
        self.assertFalse(vivo_pid(self.hijo()), "el hijo del CLI siguió vivo tras el corte")
        self.assertIn("cortado", (self.cr.L / "87-rev2-cierre.log").read_text(encoding="utf-8"))

    def test_fin_normal_mata_lo_que_el_cli_dejo_y_lee_igual(self):
        salida = json.dumps({"result": "listo", "usage": {"input_tokens": 3, "output_tokens": 4},
                             "modelUsage": {"claude-x": {}}, "is_error": False})
        for fase in ("autor", "rev1", "fix1"):
            self.cli("claude", f"sleep 30 >/dev/null 2>&1 &\necho $! > {self.tmp.name}/hijo.pid\n"
                               f"cat > /dev/null\necho '{salida}'\n")
            r, dur = self.correr("claude", fase)
            self.assertEqual((r["rc"], r["sin_cuota"], r["modelo_real"]), (0, False, "claude-x"), fase)
            self.assertEqual((r["tokens"]["entrada"], r["tokens"]["salida"]), (3, 4))
            self.assertNotIn("corte", r)
            self.assertLess(dur, 10)
            self.assertFalse(vivo_pid(self.hijo()), f"{fase}: el hijo del CLI siguió vivo al terminar")
            self.assertIn("listo", (self.cr.L / f"87-{fase}.log").read_text(encoding="utf-8"))

    def test_hijo_que_retiene_la_salida_no_cuelga_la_fase(self):
        # Antes: subprocess.run esperaba el EOF de las tuberías, o sea al hijo (30 s, o para siempre).
        self.cli("codex", f"sleep 30 &\necho $! > {self.tmp.name}/hijo.pid\ncat > /dev/null\n"
                          "echo 'model: gpt-x'\necho 'tokens used: 1,234'\n")
        r, dur = self.correr("codex", "fix1")
        self.assertEqual((r["rc"], r["tokens"], r["modelo_real"]), (0, {"total": 1234}, "gpt-x"))
        self.assertLess(dur, 10)
        self.assertFalse(vivo_pid(self.hijo()))

    def test_el_prompt_llega_entero_y_el_rc_se_conserva(self):
        grande = "x" * 300_000          # más que el búfer de una tubería
        self.cli("claude", f"wc -c > {self.tmp.name}/bytes\nexit 3\n")
        cr = self.cr
        r = cr._correr(cr.MOTORES["claude_diego"], "claude_diego", grande, "87-autor", {}, cr.HERRAMIENTAS,
                       dict(os.environ))
        self.assertEqual(r["rc"], 3)
        self.assertEqual(int((Path(self.tmp.name) / "bytes").read_text().strip()), len(grande))


    def test_detener_la_cola_mata_tambien_al_cli(self):
        """`detener` hace tmux kill-session: SIGHUP a la cola. El CLI, en su propia sesión, no lo recibe; la
        cola tiene que matar su grupo antes de morir, o el revisor seguiría escribiendo el árbol."""
        import signal
        import subprocess
        d = Path(self.tmp.name)
        corredor = d / "corredor.py"
        corredor.write_text(
            "import importlib.util, os, sys\n"
            f"spec = importlib.util.spec_from_file_location('cr', {str(AQUI / 'cola-run.py')!r})\n"
            "cr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cr)\n"
            f"cr.D = __import__('pathlib').Path({str(d)!r})\n"
            "cr.ejecutar_cli(['sh', '-c', 'echo $$ > cli.pid; sleep 30 >/dev/null 2>&1 & echo $! > hijo.pid; sleep 30'],"
            " '', dict(os.environ))\n", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, "-B", str(corredor)], cwd=d, env=dict(os.environ, NODO_PRUEBAS="1"))
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        limite = time.monotonic() + 20
        while not ((d / "hijo.pid").exists() and (d / "hijo.pid").read_text().strip()) and time.monotonic() < limite:
            time.sleep(0.05)
        cli, hijo = int((d / "cli.pid").read_text()), int((d / "hijo.pid").read_text())
        self.addCleanup(lambda: [os.kill(x, 9) for x in (cli, hijo) if vivo_pid(x)])
        self.assertTrue(vivo_pid(cli) and vivo_pid(hijo))
        proc.send_signal(signal.SIGHUP)
        self.assertEqual(proc.wait(timeout=20), 128 + signal.SIGHUP)
        self.assertFalse(vivo_pid(cli), "el CLI siguió vivo tras detener la cola")
        self.assertFalse(vivo_pid(hijo), "el hijo del CLI siguió vivo tras detener la cola")


class C10ColasVivas(Base):
    """Hallazgo 3: si la foto del arreglo registra otra cola viva, se cruza su atribución antes del cierre."""
    OTRA = "cola88x"

    def con_otra(self, fases_otra=None, crudo=None):
        fix = self.por_defecto["fix1"]

        def fix1():
            fix()
            mias = self.cr.GIT_BASE["87:fases"]
            next(f for f in mias if f["fase"] == "fix1")["vivas"] = [self.OTRA]
            ruta = self.cr.L / f"{self.OTRA}-git.json"
            if crudo is not None:
                ruta.write_text(crudo, encoding="utf-8")
            elif fases_otra is not None:
                ruta.write_text(json.dumps({"88:fases": fases_otra(mias)}), encoding="utf-8")
        self.guion = {"fix1": fix1}

    @staticmethod
    def de(f, abierta=False):
        x = {"fase": "autor", "antes": f["antes"], "vivas": [], "inicio": "2026-10-25T11:00:00+00:00"}
        if not abierta:
            x.update(despues=f["despues"], fin="2026-10-25T13:00:00+00:00")
        return x

    def escala(self, motivo):
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles()[-1], ("rev2", "rev"))
        self.assertFalse([ll for ll in self.llamadas if ll["fase"].endswith("cierre")])
        self.assertTrue(any(motivo in x for x in self.logs), self.logs)

    def solo_ajeno(self, mias):
        """Un par de fotos reales cuyo diff es sólo encargos/ajeno.txt (que al final no queda en el árbol)."""
        repo, ajeno = self.cr._vers().abrir(), self.e / "ajeno.txt"
        ajeno.write_text("de la otra cola\n", encoding="utf-8")
        repo.foto("otra cola (después)")
        con = repo.head()
        ajeno.unlink()
        repo.foto("otra cola (antes)")
        return {"antes": repo.head(), "despues": con}

    def test_cerrada_sin_ruta_en_comun_deja_el_cierre(self):
        self.con_otra(lambda mias: [self.de(self.solo_ajeno(mias))])
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles()[-1], ("rev2", "cierre"))

    def test_cerrada_con_una_ruta_del_arreglo_escala(self):
        self.con_otra(lambda mias: [self.de(next(f for f in mias if f["fase"] == "autor"))])
        self.escala("E1: fix1 comparte archivos con otra cola viva: encargos/modulo.py (cola88x)")

    def test_abierta_escala(self):
        self.con_otra(lambda mias: [self.de(next(f for f in mias if f["fase"] == "autor"), abierta=True)])
        self.escala("encargos/modulo.py (cola88x (registro abierto))")

    def test_ilegible_escala(self):
        self.con_otra(crudo="{ esto no es json")
        self.escala("encargos/modulo.py (cola88x (registro dudoso))")

    def test_falta_el_registro_escala(self):
        self.con_otra()
        self.escala("encargos/modulo.py (cola88x (registro dudoso))")

    def test_cerrada_pero_de_otra_hora_no_cuenta(self):
        def lejos(mias):
            x = self.de(next(f for f in mias if f["fase"] == "autor"))
            x.update(inicio="2026-10-24T08:00:00+00:00", fin="2026-10-24T09:00:00+00:00")
            return [x]
        self.con_otra(lejos)
        self.assertTrue(self.cr.etapa(self.etapa()))
        self.assertEqual(self.fases_roles()[-1], ("rev2", "cierre"))


if __name__ == "__main__":
    unittest.main()
