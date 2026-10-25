#!/usr/bin/env python3
"""Pruebas del diff propio (encargo 53).

Todo usa un repositorio, árbol, vivos y logs dentro de TemporaryDirectory: no toca el historial real,
~/encargos-logs ni manda avisos.
"""
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


AQUI = Path(__file__).resolve().parent


def cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, AQUI / "cola-run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DiffPropio(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        raiz = Path(self.t.name)
        self.vault, self.git, self.logs, self.estado = raiz / "vault", raiz / "git", raiz / "logs", raiz / "estado"
        self.arbol = self.vault / "10-Proyectos" / "11-Pi5"
        self.arbol.mkdir(parents=True)
        self.logs.mkdir()
        self.estado.mkdir()
        (self.arbol / "pi").mkdir()
        (self.arbol / "pi" / "base.py").write_text("base\n", encoding="utf-8")
        # `foto()` se ejercita de verdad: el falso sólo reemplaza el binario root y
        # entrega exactamente el JSON que entrega `nodo-desplegar catalogo`.
        self.bin, self.catalogo_json = raiz / "bin", raiz / "catalogo.json"
        self.bin.mkdir()
        falso = self.bin / "nodo-desplegar"
        falso.write_text("#!/usr/bin/env python3\nimport os, sys\nfrom pathlib import Path\n"
                         "if sys.argv[1:] == ['catalogo']:\n"
                         "    print(Path(os.environ['CATALOGO_FALSO']).read_text(encoding='utf-8'), end='')\n"
                         "else:\n    raise SystemExit(2)\n", encoding="utf-8")
        falso.chmod(0o755)
        self.env = {"VERSIONES_REPO": str(self.git), "VERSIONES_ARBOL": str(self.arbol),
                    "CATALOGO_FALSO": str(self.catalogo_json),
                    "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}
        self.cr = cargar("cola_run_diff_propio")
        self.cr.L, self.cr.E, self.cr.D = self.logs, self.estado, self.arbol
        self.cr.VAULT = self.vault
        self.cr.MANIFIESTO = {"nombre": "cola53", "paginas": {}, "despliegue": "nada"}
        self.cr.log = lambda _: None
        self.cr.avisar = self.cr.avisar_texto = lambda *a, **k: None
        self.momento = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
        self.cr.ahora = lambda: self.momento
        with mock.patch.dict(os.environ, self.env, clear=False):
            self.repo = self.cr._vers().abrir()
            self.repo.init()

    def fase(self, fase, rel, texto):
        with mock.patch.dict(os.environ, self.env, clear=False):
            antes = self.repo.head()
            self.cr.git_base_guardar("53", antes, fase)
            ruta = self.arbol / rel
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(texto, encoding="utf-8")
            despues = self.repo.foto(f"cola53 · 53 · {fase}").hash
            self.cr.git_base_guardar("53", despues, fase, despues=True)

    def test_c1_c2_c4_diff_propio_sobrevive_reinicio_y_anota_vivas(self):
        self.fase("autor", "pi/A.py", "A\n")
        hostil = 'B\n## Fase propia falsa "\\\\'.replace("\\n", "\n")
        (self.arbol / "pi" / hostil).write_text("B\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            self.repo.foto("otra cola entre fases")
        vivo = self.estado / "vivo"
        vivo.mkdir(parents=True)
        (vivo / "cola99.json").write_text(json.dumps({"nombre": "cola99", "estado": "corriendo",
                                                         "escrito": "2026-10-13T09:30:00-03:00"}), encoding="utf-8")
        self.fase("fix1", "pi/C.py", "C\n")
        with mock.patch.dict(os.environ, self.env, clear=False):
            ruta = self.cr.git_diff_etapa("53", self.repo.head())
        primero = Path(ruta).read_text(encoding="utf-8")
        propio, ajeno = primero.split("## Cambios ajenos", 1)
        self.assertIn("pi/A.py", propio)
        self.assertIn("pi/C.py", propio)
        self.assertNotIn(hostil, propio)
        self.assertIn(json.dumps("pi/" + hostil, ensure_ascii=False), ajeno)
        self.assertNotIn("+B", ajeno)
        self.assertIn("hubo otras colas vivas durante la fase fix1: \"cola99\"", primero)

        otra = cargar("cola_run_diff_propio_reinicio")
        otra.L, otra.E, otra.D = self.logs, self.estado, self.arbol
        otra.MANIFIESTO, otra.log = self.cr.MANIFIESTO, lambda _: None
        with mock.patch.dict(os.environ, self.env, clear=False):
            otra.git_base_cargar()
            segunda = Path(otra.git_diff_etapa("53", self.repo.head())).read_text(encoding="utf-8")
        self.assertEqual(primero, segunda)

    def test_c3_despliegue_ignora_ajeno_y_bloquea_nuevo_propio(self):
        self.fase("autor", "pi/propio.py", "propio\n")
        (self.arbol / "pi" / "ajeno.py").write_text("ajeno\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            self.repo.foto("otra cola")
        # Misma forma que `nodo-desplegar catalogo`: fuente, destino y despues.
        catalogo = {"propio": {"fuente": "10-Proyectos/11-Pi5/pi/propio.py",
                                "destino": "/usr/local/bin/propio", "despues": []},
                    "ajeno": {"fuente": "10-Proyectos/11-Pi5/pi/ajeno.py",
                               "destino": "/usr/local/bin/ajeno", "despues": ["restart:ajeno.service"]}}
        llamadas, mensajes = [], []
        self.cr.log = mensajes.append
        self.cr.avisar_texto = lambda *a, **k: None
        real_run = subprocess.run
        def run(cmd, **kwargs):
            llamadas.append(cmd)
            if cmd[0] in ("git", "cp"):
                return real_run(cmd, **kwargs)
            return subprocess.CompletedProcess(cmd, 0, json.dumps(catalogo), "")
        antes = {"entradas": {"propio": "viejo", "ajeno": "viejo"},
                 "fuentes": {k: v["fuente"].split("10-Proyectos/11-Pi5/", 1)[1] for k, v in catalogo.items()},
                 "paginas": {}, "sin_catalogo": set()}
        despues = {"entradas": {"propio": "nuevo", "ajeno": "nuevo"},
                   "fuentes": {k: v["fuente"].split("10-Proyectos/11-Pi5/", 1)[1] for k, v in catalogo.items()}, "paginas": {},
                   "sin_catalogo": {str(self.arbol / "pi" / "ajeno_nuevo.py")}}
        with mock.patch.dict(os.environ, self.env, clear=False), mock.patch.object(self.cr.subprocess, "run", run):
            self.cr.desplegar(antes, despues)
        self.assertTrue(any("propio=nuevo" in m for m in mensajes), mensajes)
        self.assertFalse(any("ajeno=nuevo" in m or "ajeno_nuevo.py" in m for m in mensajes), mensajes)

        despues["sin_catalogo"] = {str(self.arbol / "pi" / "propio_nuevo.py")}
        self.fase("fix1", "pi/propio_nuevo.py", "sin catalogo\n")
        mensajes.clear()
        with mock.patch.dict(os.environ, self.env, clear=False), mock.patch.object(self.cr.subprocess, "run", run):
            self.cr.desplegar(antes, despues)
        self.assertTrue(any("Archivos nuevos sin entrada" in m and "propio_nuevo.py" in m for m in mensajes), mensajes)

        # Páginas: una propia y otra ajena con la forma que devuelve foto(); sólo se copia la propia.
        self.cr.MANIFIESTO["paginas"] = {"propia": "cockpit-propia", "ajena": "cockpit-ajena"}
        self.fase("fix2", "pi/cockpit-propia/pagina.py", "propia\n")
        (self.arbol / "pi" / "cockpit-ajena").mkdir()
        (self.arbol / "pi" / "cockpit-ajena" / "pagina.py").write_text("ajena\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            self.repo.foto("página de otra cola")
        despues["paginas"] = {"propia": "nuevo", "ajena": "nuevo"}
        despues["sin_catalogo"] = set()
        mensajes.clear()
        with mock.patch.dict(os.environ, self.env, clear=False), mock.patch.object(self.cr.subprocess, "run", run):
            self.cr.desplegar(antes, despues)
        copias = list(self.logs.glob("cola53-paginas-*/"))
        self.assertEqual(len(copias), 1)
        self.assertTrue((copias[0] / "propia").is_dir())
        self.assertFalse((copias[0] / "ajena").exists())

    def test_c5_git_roto_no_detiene_la_cola_y_desplegar_vuelve_al_control_amplio(self):
        self.cr._VERS_MOD = type("Roto", (), {"foto": staticmethod(lambda _: (_ for _ in ()).throw(OSError("roto")))})()
        mensajes = []
        self.cr.log = mensajes.append
        self.assertIsNone(self.cr.git_foto("foto rota"))
        self.assertTrue(any("la cola sigue" in m for m in mensajes), mensajes)

        # Forma real que persiste una foto fallida: el despliegue no puede concluir que no hubo cambios.
        self.cr.GIT_BASE.clear()
        self.cr.GIT_BASE["53:fases"] = [{"fase": "autor", "antes": None, "despues": None, "vivas": []}]
        antes = {"entradas": {"bin": "viejo"}, "fuentes": {"bin": "pi/A.py"}, "paginas": {}, "sin_catalogo": set()}
        despues = {"entradas": {"bin": "nuevo"}, "fuentes": {"bin": "pi/A.py"}, "paginas": {},
                   "sin_catalogo": {str(self.arbol / "pi" / "sin_catalogo.py")}}
        self.cr.desplegar(antes, despues)
        self.assertTrue(any("Archivos nuevos sin entrada" in m for m in mensajes), mensajes)
        self.assertFalse(any("no cambió nada" in m for m in mensajes), mensajes)

        # Tampoco hay permiso para filtrar si el JSON persistido real no trae ninguna fase.
        (self.logs / "cola53-git.json").write_text("{}", encoding="utf-8")
        self.cr.git_base_cargar()
        mensajes.clear()
        self.cr.desplegar(antes, despues)
        self.assertTrue(any("Archivos nuevos sin entrada" in m for m in mensajes), mensajes)
        self.assertFalse(any("no cambió nada" in m for m in mensajes), mensajes)

    def test_foto_real_entrega_fuentes_relativas_y_desplegar_filtra_con_ellas(self):
        """`foto()` y `desplegar()` reciben la forma real del catálogo, no diccionarios armados a mano."""
        catalogo = {
            "propio": {"fuente": "10-Proyectos/11-Pi5/pi/propio.py", "destino": "/usr/local/bin/propio", "despues": []},
            "ajeno": {"fuente": "10-Proyectos/11-Pi5/pi/ajeno.py", "destino": "/usr/local/bin/ajeno", "despues": []},
        }
        mensajes = []
        self.cr.log, self.cr.avisar_texto = mensajes.append, lambda *a, **k: None
        ejecutar_real = subprocess.run

        def catalogo_real(cmd, **kwargs):
            if cmd == ["nodo-desplegar", "catalogo"]:
                return subprocess.CompletedProcess(cmd, 0, json.dumps(catalogo), "")
            return ejecutar_real(cmd, **kwargs)

        with mock.patch.object(self.cr.subprocess, "run", side_effect=catalogo_real), \
             mock.patch.dict(os.environ, self.env, clear=False):
            antes = self.cr.foto()
            self.fase("autor", "pi/propio.py", "propio\n")
            (self.arbol / "pi" / "ajeno.py").write_text("ajeno\n", encoding="utf-8")
            self.repo.foto("otra cola entre fases")
            despues = self.cr.foto()
            self.cr.desplegar(antes, despues)

        self.assertEqual(despues["fuentes"], {"propio": "pi/propio.py", "ajeno": "pi/ajeno.py"})
        self.assertTrue(any("propio=" in m for m in mensajes), mensajes)
        self.assertFalse(any("ajeno=" in m for m in mensajes), mensajes)

    def test_etapa_real_guarda_antes_y_despues_con_git_temporal(self):
        """Ejercita el cableado de etapa(), no sólo git_base_guardar() llamado a mano."""
        self.cr.GIT_BASE.clear()
        self.cr.FASES = ("autor", "rev1", "fix1", "rev2")
        self.cr.VIVO = {"eta": {"esperado": "2026-10-13T12:10", "min": "2026-10-13T12:01", "max": "2026-10-13T12:20"}}
        self.cr.atender_pausa = self.cr.exigir_candado = self.cr.vivo = self.cr.anotar = lambda *a, **k: None
        self.cr.esfuerzo_incompatible = lambda *a, **k: ""
        self.cr.modelo_de = lambda *a, **k: {"modelo": "prueba", "esfuerzo": "", "nivel": "prueba"}
        self.cr.nombre = lambda _: "Codex"
        self.cr.donde_fase = lambda *a: None
        self.cr.chequear_cuota = lambda *a: ({"min": 1, "pct_5h": 0, "min_motor": 1, "debil": False},
                                              {"5h": 0, "fuente": "temporal"})
        self.cr.prompt_de = lambda *a, **k: ""
        def correr(_, __, nombre_log, *___):
            if nombre_log.endswith("autor"):
                (self.arbol / "pi" / "desde_etapa.py").write_text("escrito por el autor\n", encoding="utf-8")
            elif nombre_log.endswith("fix1"):
                (self.arbol / "pi" / "arreglo_desde_etapa.py").write_text("escrito por el arreglo\n", encoding="utf-8")
            elif nombre_log.endswith("rev1"):
                (self.cr.E / "53r-RESULTADO.md").write_text("VEREDICTO: NO DESPLEGABLE\n", encoding="utf-8")
            return {"min": 1, "sin_cuota": False, "rc": 0}
        self.cr.correr = correr
        with mock.patch.dict(os.environ, self.env, clear=False):
            self.assertFalse(self.cr.etapa({"id": "53", "autor": "codex", "revisor": "claude_cami", "vueltas": 1}))
            guardado = json.loads((self.logs / "cola53-git.json").read_text(encoding="utf-8"))
            self.assertEqual([x["fase"] for x in guardado["53:fases"]], ["autor", "fix1"])
            for tramo in guardado["53:fases"]:
                self.assertIsInstance(tramo["antes"], str)
                self.assertIsInstance(tramo["despues"], str)
            diff = Path(self.cr.git_diff_etapa("53", self.repo.head())).read_text(encoding="utf-8")
        self.assertIn("desde_etapa.py", diff)
        self.assertIn("arreglo_desde_etapa.py", diff)

    def test_fase_interrumpida_y_registro_viejo_no_ocultan_el_trabajo(self):
        # Autor terminado; fix1 queda cortado después de escribir. Al reanudar, la foto inicial nueva
        # cierra el tramo interrumpido y el contenido queda visible para la revisión.
        self.fase("autor", "pi/A.py", "autor\n")
        with mock.patch.dict(os.environ, self.env, clear=False):
            antes_fix = self.repo.head()
            self.cr.git_base_guardar("53", antes_fix, "fix1")
            (self.arbol / "pi" / "medio_arreglo.py").write_text("peligroso\n", encoding="utf-8")
            self.repo.foto("el proceso fue detenido")
            # Si no se relanza, la foto que toma la revisión cierra el último tramo cortado.
            diff_al_revisar = Path(self.cr.git_diff_etapa("53", self.repo.head())).read_text(encoding="utf-8")
        self.assertIn("peligroso", diff_al_revisar)
        self.assertIn("interrupción", diff_al_revisar)
        otra = cargar("cola_run_diff_propio_corte")
        otra.L, otra.E, otra.D = self.logs, self.estado, self.arbol
        otra.MANIFIESTO, otra.log, otra.ahora = self.cr.MANIFIESTO, lambda _: None, self.cr.ahora
        with mock.patch.dict(os.environ, self.env, clear=False):
            otra.git_base_cargar()
            otra.git_base_guardar("53", self.repo.head(), "fix1")
            (self.arbol / "pi" / "C.py").write_text("arreglo\n", encoding="utf-8")
            despues = self.repo.foto("fix1 reanudado").hash
            otra.git_base_guardar("53", despues, "fix1", despues=True)
            diff = Path(otra.git_diff_etapa("53", self.repo.head())).read_text(encoding="utf-8")
        self.assertIn("medio_arreglo.py", diff)
        self.assertIn("peligroso", diff)
        self.assertIn("interrupción", diff)

        # Forma vieja real: sólo la base simple de una cola pausada antes de que existieran tramos.
        antigua = cargar("cola_run_diff_propio_forma_vieja")
        antigua.L, antigua.E, antigua.D = self.logs, self.estado, self.arbol
        antigua.MANIFIESTO, antigua.log, antigua.ahora = self.cr.MANIFIESTO, lambda _: None, self.cr.ahora
        with mock.patch.dict(os.environ, self.env, clear=False):
            base = self.repo.head()
            (self.arbol / "pi" / "autor_antiguo.py").write_text("autor de la forma vieja\n", encoding="utf-8")
            self.repo.foto("autor antes de actualizar cola-run")
            (self.logs / "cola53-git.json").write_text(json.dumps({"53": base}), encoding="utf-8")
            antigua.git_base_cargar()
            antigua.git_base_guardar("53", self.repo.head(), "fix1")
            (self.arbol / "pi" / "fix_nuevo.py").write_text("fix\n", encoding="utf-8")
            despues = self.repo.foto("fix después de actualizar cola-run").hash
            antigua.git_base_guardar("53", despues, "fix1", despues=True)
            diff = Path(antigua.git_diff_etapa("53", self.repo.head())).read_text(encoding="utf-8")
        self.assertIn("autor_antiguo.py", diff)
        self.assertIn("fix_nuevo.py", diff)

        # Forma real tras fallar sólo la foto inicial: fix1 ya escribió C y fix2 parte después.
        # C debe quedar bajo una fase propia conservadora, nunca bajo «ajenos: no los revises».
        antigua.GIT_BASE.clear()
        antigua.git_base_guardar("54", self.repo.head(), "autor")
        (self.arbol / "pi" / "A54.py").write_text("A\n", encoding="utf-8")
        cierre_autor = self.repo.foto("autor 54").hash
        antigua.git_base_guardar("54", cierre_autor, "autor", despues=True)
        (self.arbol / "pi" / "C54.py").write_text("C peligroso\n", encoding="utf-8")
        cierre_fix1 = self.repo.foto("fix1 54 sin foto inicial").hash
        antigua.GIT_BASE["54:fases"].append({"fase": "fix1", "antes": None, "despues": cierre_fix1, "vivas": []})
        antigua.git_base_guardar("54", cierre_fix1, "fix2")
        (self.arbol / "pi" / "D54.py").write_text("D\n", encoding="utf-8")
        cierre_fix2 = self.repo.foto("fix2 54").hash
        antigua.git_base_guardar("54", cierre_fix2, "fix2", despues=True)
        with mock.patch.dict(os.environ, self.env, clear=False):
            incompleto = Path(antigua.git_diff_etapa("54", cierre_fix2)).read_text(encoding="utf-8")
        self.assertIn("no tiene foto inicial", incompleto)
        propio, ajeno = incompleto.split("## Cambios ajenos", 1) if "## Cambios ajenos" in incompleto else (incompleto, "")
        self.assertIn("C peligroso", propio)
        self.assertNotIn("C54.py", ajeno)

    def test_arbol_extra_con_corte_y_registro_viejo_muestra_toda_la_etapa(self):
        """Las fotos reales de una carpeta hermana vuelven al diff base..HEAD, como antes del encargo 53."""
        extra = "13-Agente-Noticias"
        hermana = self.vault / "10-Proyectos" / extra
        hermana.mkdir()
        (hermana / "base.txt").write_text("base\n", encoding="utf-8")
        self.cr.MANIFIESTO["arboles_extra"] = [extra]
        with mock.patch.dict(os.environ, self.env, clear=False):
            repo_extra = self.cr._repos_extra()[0][1]
            repo_extra.init()
            self.cr.git_base_guardar("53", self.repo.head(), "autor")
            (hermana / "autor.py").write_text("del autor\n", encoding="utf-8")
            repo_extra.foto("autor extra")
            self.cr.git_base_guardar("53", self.repo.head(), "autor", despues=True)
            self.cr.git_base_guardar("53", self.repo.head(), "fix1")
            (hermana / "medio.py").write_text("peligroso\n", encoding="utf-8")
            repo_extra.foto("fix1 extra cortado")
            diff_corte = Path(self.cr.git_diff_etapa("53", self.repo.head())).read_text(encoding="utf-8")
        self.assertIn("medio.py", diff_corte)
        self.assertIn("peligroso", diff_corte)

        # JSON viejo real: sólo las dos bases, de antes de que existieran «:fases».
        with mock.patch.dict(os.environ, self.env, clear=False):
            base_principal, base_extra = self.repo.head(), repo_extra.head()
            (hermana / "autor_viejo.py").write_text("autor antiguo\n", encoding="utf-8")
            repo_extra.foto("autor previo al formato de fases")
            (self.logs / "cola53-git.json").write_text(
                json.dumps({"53": base_principal, f"53@{extra}": base_extra}), encoding="utf-8")
            self.cr.git_base_cargar()
            self.cr.git_base_guardar("53", self.repo.head(), "fix1")
            (hermana / "fix_nuevo.py").write_text("fix\n", encoding="utf-8")
            repo_extra.foto("fix posterior")
            self.cr.git_base_guardar("53", self.repo.head(), "fix1", despues=True)
            diff_viejo = Path(self.cr.git_diff_etapa("53", self.repo.head())).read_text(encoding="utf-8")
        self.assertIn("autor_viejo.py", diff_viejo)
        self.assertIn("autor antiguo", diff_viejo)
        self.assertIn("fix_nuevo.py", diff_viejo)

    def test_vivas_frescas_y_archivo_compartido_entre_fases(self):
        vivo = self.estado / "vivo"
        vivo.mkdir(parents=True)
        (vivo / "cola_muerta.json").write_text(json.dumps({"nombre": "cola_muerta", "estado": "corriendo",
                                                              "escrito": "2026-10-10T09:00:00-03:00"}), encoding="utf-8")
        (vivo / "cola_fresca.json").write_text(json.dumps({"nombre": "cola_fresca", "estado": "corriendo",
                                                              "escrito": "2026-10-13T09:30:00-03:00"}), encoding="utf-8")
        (vivo / "cola_terminada.json").write_text(json.dumps({"nombre": "cola_terminada", "estado": "terminada",
                                                                 "escrito": "2026-10-13T09:30:00-03:00"}), encoding="utf-8")
        (vivo / "cola53.json").write_text(json.dumps({"nombre": "cola53", "estado": "corriendo",
                                                         "escrito": "2026-10-13T09:30:00-03:00"}), encoding="utf-8")
        self.cr.sesion_viva = lambda _: False
        with mock.patch.dict(os.environ, self.env, clear=False):
            antes = self.repo.head()
            self.cr.git_base_guardar("53", antes, "autor")
            (vivo / "cola_llego_despues.json").write_text(json.dumps({"nombre": "cola_llego_despues", "estado": "corriendo",
                                                                         "escrito": "2026-10-13T09:30:00-03:00"}), encoding="utf-8")
            despues = self.repo.foto("cierre de autor").hash
            self.cr.git_base_guardar("53", despues, "autor", despues=True)
        vivas = self.cr.GIT_BASE["53:fases"][0]["vivas"]
        self.assertEqual(vivas, ["cola_fresca", "cola_llego_despues"])

        self.fase("autor", "pi/A.py", "autor\n")
        (self.arbol / "pi" / "A.py").write_text("autor\najeno sin revisar\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            self.repo.foto("otra cola entre fases")
        self.fase("fix1", "pi/A.py", "autor\najeno sin revisar\nfix\n")
        with mock.patch.dict(os.environ, self.env, clear=False):
            diff = Path(self.cr.git_diff_etapa("53", self.repo.head())).read_text(encoding="utf-8")
        self.assertIn('"pi/A.py" (también lo cambió esta etapa: lo que se despliegue lo incluye)', diff)

    def test_registro_de_fases_se_publica_atomico(self):
        reemplazos = []
        real_replace = os.replace
        def reemplazar(origen, destino):
            reemplazos.append((Path(origen), Path(destino)))
            return real_replace(origen, destino)
        with mock.patch.object(self.cr.os, "replace", side_effect=reemplazar):
            self.cr.git_base_guardar("53", self.repo.head(), "autor")
        self.assertEqual(len(reemplazos), 1)
        temporal, destino = reemplazos[0]
        self.assertEqual(destino, self.logs / "cola53-git.json")
        self.assertIn(".cola53-git.json.", temporal.name)
        self.assertFalse(temporal.exists())
        self.assertIsInstance(json.loads(destino.read_text(encoding="utf-8"))["53:fases"], list)

    # Encargo 79: los casos de pedido usan el repositorio git temporal real de arriba y la forma
    # exacta del catálogo (`fuente`, `destino`, `despues`). `despliegue = nada` evita todo pedido real.
    def _catalogo(self, *nombres):
        destino = self.t.name + "/instalado"
        return {n: {"fuente": f"10-Proyectos/11-Pi5/pi/{n}.py", "destino": f"{destino}/{n}", "despues": []}
                for n in nombres}

    def _foto_catalogo(self, catalogo):
        self.catalogo_json.write_text(json.dumps(catalogo), encoding="utf-8")
        return self.cr.foto()

    def _vivo(self, nombre, estado="corriendo"):
        vivo = self.estado / "vivo"
        vivo.mkdir(exist_ok=True)
        (vivo / f"{nombre}.json").write_text(json.dumps({"nombre": nombre, "estado": estado,
                                                            "escrito": self.momento.isoformat()}), encoding="utf-8")

    def _desplegar_y_leer(self, antes, despues):
        mensajes, avisos = [], []
        self.cr.log, self.cr.avisar_texto = mensajes.append, lambda *a, **k: avisos.append(a[0])
        with mock.patch.dict(os.environ, self.env, clear=False):
            self.cr.desplegar(antes, despues)
        return mensajes, avisos

    def test_79_c1_linea_base_persistente_pide_autor_y_fix_al_reanudar(self):
        catalogo = self._catalogo("x", "y")
        (self.arbol / "pi" / "x.py").write_text("base x\n", encoding="utf-8")
        (self.arbol / "pi" / "y.py").write_text("base y\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            self.repo.foto("base catálogo")
            antes = self._foto_catalogo(catalogo)
            self.assertEqual(self.cr.tomar_linea_base_catalogo(False, "cola53"), antes)
            self.fase("autor", "pi/x.py", "autor x\n")
            # Simula proceso nuevo y --desde: no toma una foto nueva como línea base.
            otra = cargar("cola_run_79_c1")
            otra.L, otra.E, otra.D, otra.VAULT = self.logs, self.estado, self.arbol, self.vault
            otra.MANIFIESTO, otra.log, otra.avisar_texto = self.cr.MANIFIESTO, lambda _: None, lambda *a, **k: None
            otra.git_base_cargar()
            self.assertEqual(otra.tomar_linea_base_catalogo(True, "cola53"), antes)
            self.fase("fix1", "pi/y.py", "fix y\n")
            despues = self._foto_catalogo(catalogo)
            # Segundo proceso real de --desde: la base persistida incluye ahora autor y fix.
            otra.git_base_cargar()
            linea_base = otra.tomar_linea_base_catalogo(True, "cola53")
        mensajes, avisos = [], []
        otra.log, otra.avisar_texto = mensajes.append, lambda *a, **k: avisos.append(a[0])
        with mock.patch.dict(os.environ, self.env, clear=False):
            otra.desplegar(linea_base, despues)
        texto = "\n".join(mensajes)
        self.assertIn("x=", texto)
        self.assertIn("y=", texto)

    def test_79_c2_y_c3_excluye_ajeno_y_compartido_de_ventanas_solapadas(self):
        catalogo = self._catalogo("propio", "t", "compartido")
        for n in catalogo:
            (self.arbol / "pi" / f"{n}.py").write_text("base\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            base = self.repo.foto("base 79").hash
            antes = self._foto_catalogo(catalogo)
            self._vivo("cola75")
            self.cr.git_base_guardar("53", base, "fix1")
            # cola75 modifica T y compartido mientras cola53 está en fix1.
            (self.arbol / "pi" / "t.py").write_text("de cola75\n", encoding="utf-8")
            (self.arbol / "pi" / "compartido.py").write_text("cola75\n", encoding="utf-8")
            cierre_75 = self.repo.foto("cola75 autor").hash
            (self.logs / "cola75-git.json").write_text(json.dumps({"75:fases": [{"fase": "autor", "antes": base,
                                                                        "despues": cierre_75,
                                                                        "inicio": self.momento.isoformat(), "fin": self.momento.isoformat()}]}), encoding="utf-8")
            (self.arbol / "pi" / "propio.py").write_text("de cola53\n", encoding="utf-8")
            (self.arbol / "pi" / "compartido.py").write_text("de ambas\n", encoding="utf-8")
            cierre_53 = self.repo.foto("cola53 fix1").hash
            self.cr.git_base_guardar("53", cierre_53, "fix1", despues=True)
            self.assertEqual(self.cr.GIT_BASE["53:fases"][0]["vivas"], ["cola75"])
            despues = self._foto_catalogo(catalogo)
        mensajes, avisos = self._desplegar_y_leer(antes, despues)
        texto = "\n".join(mensajes + avisos)
        self.assertIn("propio=", texto)
        self.assertNotIn(" t=", texto)
        self.assertNotIn(" compartido=", texto)
        self.assertIn("pi/t.py cambiado en la ventana de cola75, sin pedir", texto)
        self.assertIn("pi/compartido.py cambiado en la ventana de cola75, sin pedir", texto)

        # C3: vista desde cola75, el archivo que ambas tocaron tampoco se pide sola.
        otra = cargar("cola_run_79_c3")
        otra.L, otra.E, otra.D, otra.VAULT = self.logs, self.estado, self.arbol, self.vault
        otra.MANIFIESTO = {"nombre": "cola75", "paginas": {}, "despliegue": "nada"}
        otra.ahora = lambda: self.momento
        self._vivo("cola53")
        otra.git_base_guardar("75", base, "autor")
        otra.git_base_guardar("75", cierre_75, "autor", despues=True)
        otra_mensajes, otra_avisos = [], []
        otra.log, otra.avisar_texto = otra_mensajes.append, lambda *a, **k: otra_avisos.append(a[0])
        with mock.patch.dict(os.environ, self.env, clear=False):
            otra.desplegar(antes, despues)
        otro_texto = "\n".join(otra_mensajes + otra_avisos)
        self.assertNotIn(" compartido=", otro_texto)
        self.assertIn("pi/compartido.py cambiado en la ventana de cola53, sin pedir", otro_texto)

    def test_79_c4_y_c5_forma_vieja_advierte_y_destino_igual_no_se_pide(self):
        catalogo = self._catalogo("igual")
        (self.arbol / "pi" / "igual.py").write_text("vault\n", encoding="utf-8")
        Path(catalogo["igual"]["destino"]).parent.mkdir()
        Path(catalogo["igual"]["destino"]).write_text("vault\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            base = self.repo.foto("base viejo 79").hash
            (self.logs / "cola53-git.json").write_text(json.dumps({"53": base}), encoding="utf-8")
            mensajes, avisos = [], []
            self.cr.log, self.cr.avisar_texto = mensajes.append, lambda *a, **k: avisos.append(a[0])
            linea_vieja = self.cr.tomar_linea_base_catalogo(True, "cola53")
            self.assertIn("línea base no persistida", "\n".join(mensajes).lower())
            self.assertIn("revisa con `cmp`", "\n".join(avisos))
            self.cr.git_base_guardar("53", base, "fix1")
            (self.arbol / "pi" / "igual.py").write_text("vault\n# revisado\n", encoding="utf-8")
            cierre = self.repo.foto("cambio propio ya instalado").hash
            self.cr.git_base_guardar("53", cierre, "fix1", despues=True)
            Path(catalogo["igual"]["destino"]).write_text("vault\n# revisado\n", encoding="utf-8")
            despues = self._foto_catalogo(catalogo)
        mensajes, _ = self._desplegar_y_leer(linea_vieja, despues)
        self.assertFalse(any("igual=" in m for m in mensajes), mensajes)
        self.assertTrue(any("no cambió nada desplegable" in m for m in mensajes), mensajes)

    def test_79_registro_ajeno_hostil_y_pagina_reanudada_no_rompen_ni_se_cuelan(self):
        # Un JSON ajeno a medio escribir o con otra forma no da permiso: el archivo queda compartido dudoso.
        catalogo = self._catalogo("dudoso")
        (self.arbol / "pi" / "dudoso.py").write_text("base\n", encoding="utf-8")
        pagina = self.arbol / "pi" / "cockpit-79"
        pagina.mkdir()
        (pagina / "index.html").write_text("base\n", encoding="utf-8")
        self.cr.MANIFIESTO["paginas"] = {"panel79": "cockpit-79"}
        with mock.patch.dict(os.environ, self.env, clear=False):
            base_git = self.repo.foto("base hostil 79").hash
            antes = self._foto_catalogo(catalogo) | {"paginas": {"panel79": self.cr.sha_dir(pagina)}}
            self.assertEqual(self.cr.tomar_linea_base_catalogo(False, "cola53"), antes)
            self.cr.git_base_guardar("53", base_git, "fix1")
            (self.arbol / "pi" / "dudoso.py").write_text("cambio\n", encoding="utf-8")
            cierre = self.repo.foto("fix dudoso").hash
            self.cr.git_base_guardar("53", cierre, "fix1", despues=True)
            self.cr.GIT_BASE["53:fases"][0]["vivas"] = ["cola99"]
            # Forma hostil: hashes con forma válida, pero inexistentes. No puede ensanchar el pedido.
            (self.logs / "cola99-git.json").write_text(json.dumps({"99:fases": [{"fase": "x", "antes": "0" * 40,
                                                                        "despues": "f" * 40}]}), encoding="utf-8")
            self.cr.git_base_guardar("53", cierre, "fix2")
            (pagina / "index.html").write_text("cambio página\n", encoding="utf-8")
            cierre = self.repo.foto("fix con panel").hash
            self.cr.git_base_guardar("53", cierre, "fix2", despues=True)
            despues = self._foto_catalogo(catalogo) | {"paginas": {"panel79": self.cr.sha_dir(pagina)}}
        mensajes, avisos = self._desplegar_y_leer(antes, despues)
        texto = "\n".join(mensajes + avisos)
        self.assertNotIn("dudoso=", texto)
        self.assertIn("pi/dudoso.py cambiado en la ventana de cola99 (registro dudoso), sin pedir", texto)
        copias = list(self.logs.glob("cola53-paginas-*/panel79/index.html"))
        self.assertEqual([p.read_text(encoding="utf-8") for p in copias], ["cambio página\n"])

    def test_79r1_esperando_no_anula_pedido(self):
        """Una cola encadenada sale de vivo/ real, pero ANTES_DE_PARTIR no la hace competidora."""
        catalogo = self._catalogo("x")
        (self.arbol / "pi" / "x.py").write_text("base\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            base = self.repo.foto("base cadena").hash
            antes = self._foto_catalogo(catalogo)
            self._vivo("cola79", "esperando")
            self.cr.git_base_guardar("53", base, "autor")
            self.assertEqual(self.cr.GIT_BASE["53:fases"][0]["vivas"], [])
            (self.arbol / "pi" / "x.py").write_text("autor\n", encoding="utf-8")
            cierre = self.repo.foto("autor cadena").hash
            self.cr.git_base_guardar("53", cierre, "autor", despues=True)
            despues = self._foto_catalogo(catalogo)
        mensajes, _ = self._desplegar_y_leer(antes, despues)
        self.assertIn("x=", "\n".join(mensajes))

    def test_79r1_sin_git_no_pide_pendiente_anterior(self):
        """Con el diff roto, `foto()` real conserva el filtro de la corrida, no todo el catálogo."""
        catalogo = self._catalogo("x", "z")
        for n in catalogo:
            (self.arbol / "pi" / f"{n}.py").write_text("base\n", encoding="utf-8")
            Path(catalogo[n]["destino"]).parent.mkdir(parents=True, exist_ok=True)
        Path(catalogo["x"]["destino"]).write_text("base\n", encoding="utf-8")
        Path(catalogo["z"]["destino"]).write_text("instalado viejo\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            self.repo.foto("base sin git")
            antes = self._foto_catalogo(catalogo)
            (self.arbol / "pi" / "x.py").write_text("cambio de esta cola\n", encoding="utf-8")
            self.repo.foto("cambio sin git")
            despues = self._foto_catalogo(catalogo)
            with mock.patch.object(self.cr, "_propios_atribuidos", side_effect=RuntimeError("git roto")):
                mensajes, _ = self._desplegar_y_leer(antes, despues)
        texto = "\n".join(mensajes)
        self.assertIn("x=", texto)
        self.assertNotIn(" z=", texto)

    def test_79r1_fase_ajena_abierta_se_retiene_y_no_atribuye_autor(self):
        """Una fase ajena abierta sale del -git.json real: retiene, no se omite ni acusa a su autor."""
        catalogo = self._catalogo("y")
        (self.arbol / "pi" / "y.py").write_text("base\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self.env, clear=False):
            base = self.repo.foto("base abierta").hash
            antes = self._foto_catalogo(catalogo)
            self._vivo("cola75")
            (self.logs / "cola75-git.json").write_text(json.dumps({"75:fases": [{"fase": "autor", "antes": base,
                                                                        "inicio": self.momento.isoformat()}]}), encoding="utf-8")
            self.cr.git_base_guardar("53", base, "fix1")
            (self.arbol / "pi" / "y.py").write_text("fix propio\n", encoding="utf-8")
            cierre = self.repo.foto("fix con ajena abierta").hash
            self.cr.git_base_guardar("53", cierre, "fix1", despues=True)
            despues = self._foto_catalogo(catalogo)
        mensajes, avisos = self._desplegar_y_leer(antes, despues)
        texto = "\n".join(mensajes + avisos)
        self.assertNotIn(" y=", texto)
        self.assertIn("pi/y.py cambiado en la ventana de cola75 (registro abierto), sin pedir", texto)
        self.assertIn("pendientes de despliegue conjunto", texto)

    def test_79r1_pagina_con_archivo_compartido_no_se_copia(self):
        catalogo = self._catalogo()
        pagina = self.arbol / "pi" / "cockpit-79r"
        pagina.mkdir()
        (pagina / "index.html").write_text("base\n", encoding="utf-8")
        (pagina / "app.js").write_text("base\n", encoding="utf-8")
        self.cr.MANIFIESTO["paginas"] = {"panel79r": "cockpit-79r"}
        with mock.patch.dict(os.environ, self.env, clear=False):
            base = self.repo.foto("base pagina").hash
            antes = self._foto_catalogo(catalogo)
            self._vivo("cola75")
            self.cr.git_base_guardar("53", base, "fix1")
            (pagina / "app.js").write_text("sin revisar de 75\n", encoding="utf-8")
            cierre_75 = self.repo.foto("cambio 75 pagina").hash
            (self.logs / "cola75-git.json").write_text(json.dumps({"75:fases": [{"fase": "autor", "antes": base,
                                                                        "despues": cierre_75, "inicio": self.momento.isoformat(),
                                                                        "fin": self.momento.isoformat()}]}), encoding="utf-8")
            (pagina / "index.html").write_text("revisado por 53\n", encoding="utf-8")
            cierre = self.repo.foto("cambio 53 pagina").hash
            self.cr.git_base_guardar("53", cierre, "fix1", despues=True)
            despues = self._foto_catalogo(catalogo)
        mensajes, avisos = self._desplegar_y_leer(antes, despues)
        texto = "\n".join(mensajes + avisos)
        self.assertFalse(list(self.logs.glob("cola53-paginas-*/panel79r")))
        self.assertIn("pi/cockpit-79r/app.js cambiado en la ventana de cola75, sin pedir", texto)

    def test_79r1_crlf_y_base_corrupta_no_generan_pedido_ni_traceback(self):
        catalogo = self._catalogo("x")
        fuente, destino = self.arbol / "pi" / "x.py", Path(catalogo["x"]["destino"])
        fuente.write_bytes(b"base\r\n")
        destino.parent.mkdir(parents=True)
        destino.write_bytes(b"base\n")
        with mock.patch.dict(os.environ, self.env, clear=False):
            base = self.repo.foto("base crlf").hash
            antes = self._foto_catalogo(catalogo)
            self.cr.git_base_guardar("53", base, "fix1")
            fuente.write_bytes(b"revisado\r\n")
            destino.write_bytes(b"revisado\n")
            cierre = self.repo.foto("fix crlf").hash
            self.cr.git_base_guardar("53", cierre, "fix1", despues=True)
            despues = self._foto_catalogo(catalogo)
        mensajes, _ = self._desplegar_y_leer(antes, despues)
        self.assertNotIn("x=", "\n".join(mensajes))
        with mock.patch.dict(os.environ, self.env, clear=False):
            (self.logs / "cola53-git.json").write_text(json.dumps({"__catalogo_base": {"entradas": {}}}), encoding="utf-8")
            self.cr.git_base_cargar()
            mensajes, avisos = [], []
            self.cr.log, self.cr.avisar_texto = mensajes.append, lambda *a, **k: avisos.append(a[0])
            recuperada = self.cr.tomar_linea_base_catalogo(True, "cola53")
            self.cr.desplegar(recuperada, despues)
        self.assertEqual(recuperada, despues)
        self.assertIn("línea base no persistida", "\n".join(mensajes).lower())


class CodexEscribeArbolesExtra(unittest.TestCase):
    """Cola 59: el sandbox de Codex sólo escribe en --cd; las hermanas validadas van con --add-dir."""

    def test_codex_recibe_add_dir_solo_de_hermanas_validadas(self):
        cr = cargar("cola_run_59")
        # `_correr()` deja su salida en L: aun esta prueba de argumentos debe aislarla del log real.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cr.L = Path(tmp.name)
        vistos = []

        # 87b: el CLI ya no sale por subprocess.run sino por ejecutar_cli (grupo de procesos propio).
        def falso_run(cmd, prompt, env, limite_s=None):
            vistos.append(cmd)
            return 0, "", "", False

        with mock.patch.object(cr, "_repos_extra", return_value=[("14-App-Matrimonio", object())]), \
                mock.patch.object(cr, "ejecutar_cli", side_effect=falso_run):
            cr._correr({"motor": "codex"}, "codex", "x", "59-autor", {}, cr.HERRAMIENTAS, {})
        cmd = vistos[0]
        i = cmd.index("--add-dir")
        self.assertEqual(cmd[i + 1], str(cr.D.parent / "14-App-Matrimonio"))
        self.assertEqual(cmd.count("--add-dir"), 1)
        self.assertEqual(cmd[-1], "-")

        vistos.clear()
        with mock.patch.object(cr, "_repos_extra", return_value=[]), \
                mock.patch.object(cr, "ejecutar_cli", side_effect=falso_run):
            cr._correr({"motor": "codex"}, "codex", "x", "59-autor", {}, cr.HERRAMIENTAS, {})
        self.assertNotIn("--add-dir", vistos[0])


if __name__ == "__main__":
    unittest.main()
