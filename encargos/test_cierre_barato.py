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


if __name__ == "__main__":
    unittest.main()
