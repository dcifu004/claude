#!/usr/bin/env python3
"""Pruebas de versiones.py y de lo que cola-run.py hace con él (encargo 33).

Todo corre en un mktemp -d con un repositorio y un árbol falsos: ninguna prueba toca /opt/nodo/datos ni
el vault. Los repos de prueba van en una carpeta hermana del árbol, nunca dentro."""
import contextlib
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

AQUI = Path(__file__).resolve().parent


def _cargar(nombre, archivo):
    spec = importlib.util.spec_from_file_location(nombre, AQUI / archivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vs = _cargar("versiones", "versiones.py")


def escribir(arbol: Path, rel: str, texto="x\n") -> Path:
    p = arbol / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8")
    return p


def hay_git_en(arbol: Path) -> list[str]:
    return [os.path.join(r, n) for r, ds, fs in os.walk(arbol) for n in ds + fs if n == ".git"]


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.raiz = Path(self._t.name)
        self.arbol = self.raiz / "vault" / "11-Pi5"
        self.arbol.mkdir(parents=True)
        self.git_dir = self.raiz / "git" / "11-Pi5.git"
        escribir(self.arbol, "README.md", "uno\n")
        escribir(self.arbol, "encargos/cola-run.py", "print('a')\n")
        escribir(self.arbol, "Guía de implementación.md", "tilde\n")
        self.repo = vs.Repo(self.git_dir, self.arbol)

    def tearDown(self):
        # Pase lo que pase, ninguna operación deja un .git (carpeta o archivo) dentro del árbol.
        self.assertEqual(hay_git_en(self.arbol), [])

    def seguidos(self) -> set[str]:
        return set(filter(None, self.repo.git("ls-files", "-z").stdout.decode().split("\0")))

    def commits(self) -> int:
        return int(self.repo.git("rev-list", "--count", "HEAD").stdout.decode())

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = vs.main(["--repo", str(self.git_dir), "--arbol", str(self.arbol), *args])
        return rc, out.getvalue(), err.getvalue()


class InitTests(Base):
    def test_init_crea_repo_separado_y_primer_commit(self):
        self.assertFalse(self.repo.existe())
        f = self.repo.init()
        self.assertTrue(f.nueva)
        self.assertTrue(self.repo.existe())
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.repo.git("log", "-1", "--format=%an <%ae>").stdout.decode().strip(), "cola-run <cola@pi5>")
        self.assertIn("README.md", self.seguidos())
        self.assertIn("Guía de implementación.md", self.seguidos())      # sin comillas ni escapes en la tilde

    def test_init_dos_veces_no_agrega_commits(self):
        self.repo.init()
        f = self.repo.init()
        self.assertFalse(f.nueva)
        self.assertEqual(self.commits(), 1)

    def test_cli_init_imprime_ruta_y_tamano(self):
        rc, out, err = self.cli("init")
        self.assertEqual((rc, err), (0, ""))
        self.assertIn(str(self.git_dir), out)
        self.assertRegex(out, r"\d+ KB|\d+\.\d MB")

    def test_no_crea_git_dentro_del_arbol_ni_con_variables_de_entorno_ajenas(self):
        ajeno = self.raiz / "otro.git"
        with mock.patch.dict(os.environ, {"GIT_DIR": str(ajeno), "GIT_WORK_TREE": str(self.raiz)}):
            self.repo.init()
            self.repo.foto("x")
        self.assertFalse(ajeno.exists())
        self.assertFalse((self.raiz / ".git").exists())

    def test_se_niega_a_vivir_dentro_del_arbol(self):
        for malo in (self.arbol / ".git", self.arbol / "historial.git", self.arbol):
            with self.assertRaises(vs.VersionesError):
                vs.Repo(malo, self.arbol)
        link = self.raiz / "enlace"
        link.symlink_to(self.arbol)
        with self.assertRaises(vs.VersionesError):
            vs.Repo(link / "h.git", self.arbol)

    def test_sin_init_foto_falla_con_mensaje(self):
        rc, out, err = self.cli("foto", "x")
        self.assertEqual(rc, 1)
        self.assertIn("init", err)
        self.assertFalse(self.git_dir.exists())


class FotoTests(Base):
    def setUp(self):
        super().setUp()
        self.repo.init()

    def test_foto_sin_cambios_no_hace_nada_y_sale_0(self):
        antes = self.repo.head()
        rc, out, err = self.cli("foto", "nada")
        self.assertEqual((rc, out.strip()), (0, "sin cambios"))
        self.assertEqual(self.repo.head(), antes)
        self.assertEqual(self.commits(), 1)

    def test_foto_con_cambios_hace_un_commit_con_todo(self):
        escribir(self.arbol, "README.md", "dos\n")
        escribir(self.arbol, "nuevo/archivo.md", "n\n")
        (self.arbol / "encargos/cola-run.py").unlink()
        rc, out, err = self.cli("foto", "cola33 · 33 · autor")
        self.assertEqual(rc, 0)
        self.assertIn("foto ", out)
        self.assertEqual(self.commits(), 2)
        self.assertEqual(self.repo.git("log", "-1", "--format=%s").stdout.decode().strip(), "cola33 · 33 · autor")
        self.assertEqual(self.seguidos(), {"README.md", "nuevo/archivo.md", "Guía de implementación.md"})
        self.assertEqual(self.repo.git("status", "--porcelain").stdout, b"")

    def test_foto_exige_mensaje(self):
        with self.assertRaises(vs.VersionesError):
            self.repo.foto("  ")

    def test_log_general_y_de_un_archivo(self):
        escribir(self.arbol, "README.md", "dos\n")
        self.repo.foto("toca el README")
        escribir(self.arbol, "otro.md")
        self.repo.foto("agrega otro")
        general = self.repo.log()
        self.assertEqual(len(general.strip().splitlines()), 3)
        solo = self.repo.log("README.md")
        self.assertIn("toca el README", solo)
        self.assertNotIn("agrega otro", solo)
        self.assertEqual(len(self.repo.log(n=1).strip().splitlines()), 1)
        rc, out, _ = self.cli("log", "README.md")
        self.assertEqual(rc, 0)
        self.assertIn("estado inicial", out)

    def test_log_de_archivo_ya_borrado_y_de_carpeta(self):
        (self.arbol / "README.md").unlink()
        self.repo.foto("borra README")
        self.assertIn("borra README", self.repo.log("README.md"))
        self.assertIn("estado inicial", self.repo.log("encargos"))
        with self.assertRaises(vs.VersionesError):
            self.repo.log("/etc/passwd")

    def test_diff_muestra_lo_borrado(self):
        base = self.repo.head()
        escribir(self.arbol, "README.md", "dos\n")
        (self.arbol / "encargos/cola-run.py").unlink()
        self.repo.foto("cambios")
        d = self.repo.diff(base)
        self.assertIn("-uno", d)
        self.assertIn("+dos", d)
        self.assertIn("deleted file mode", d)
        self.assertIn("-print('a')", d)
        self.assertEqual(self.repo.diff(base, "HEAD"), d)
        self.assertEqual(self.repo.diff(base, base), "")
        self.assertIn("deleted file mode", self.cli("diff", base[:7])[1])

    def test_diff_con_tope_recorta(self):
        base = self.repo.head()
        escribir(self.arbol, "grande.md", "línea larga\n" * 5000)
        self.repo.foto("grande")
        d = self.repo.diff(base, tope=2000)
        self.assertIn("recortado", d)
        self.assertLess(len(d.encode()), 3000)

    def test_commit_invalido(self):
        for malo in ("no-existe", "-p", "", "HEAD~50"):
            with self.assertRaises(vs.VersionesError, msg=malo):
                self.repo.diff(malo)
        self.assertEqual(self.cli("diff", "no-existe")[0], 1)


class ExclusionTests(Base):
    def setUp(self):
        super().setUp()
        for rel in ("botv3/botv3-jaime.env", ".env", "pi/.env.local", "secretos/clave.txt", "botv3/secretos/x.txt",
                    "botv3/__pycache__/a.cpython-313.pyc", "x.pyc", ".venv/lib/a.py", "encargos/vivo/cola33.json",
                    "encargos/vivo/leases/token.json", "uso-equipos/PC.json", "doc.pdf", "sub/otro.PDF".lower(),
                    "paquete.zip", "tmp.img", "pc2503/estado/x.json", "vault_trabajo/dato.md", ".codex/auth.json",
                    "google/token.json", "llaves/id.pem", ".stversions/v.md", "x.md.recuperado-abc1234"):
            escribir(self.arbol, rel, "dato sensible\n")
        # Lo que SÍ debe entrar, incluidos nombres parecidos.
        for rel in ("botv3/botv3.env.example", "pi/env.ejemplo", "pi/fixtures/vivo/cola.json",
                    "encargos/historial.jsonl", "pi/cockpit-comun/tokens.css", "pc2503/trabajador.py"):
            escribir(self.arbol, rel)
        self.repo.init()

    def test_secretos_cachés_y_binarios_no_entran(self):
        dentro = self.seguidos()
        for rel in ("botv3/botv3-jaime.env", ".env", "pi/.env.local", "secretos/clave.txt", "botv3/secretos/x.txt",
                    "botv3/__pycache__/a.cpython-313.pyc", "x.pyc", ".venv/lib/a.py", "encargos/vivo/cola33.json",
                    "encargos/vivo/leases/token.json", "uso-equipos/PC.json", "doc.pdf", "sub/otro.pdf", "paquete.zip",
                    "tmp.img", "pc2503/estado/x.json", "vault_trabajo/dato.md", ".codex/auth.json", "google/token.json",
                    "llaves/id.pem", ".stversions/v.md", "x.md.recuperado-abc1234"):
            self.assertNotIn(rel, dentro, rel)
        # Ni en el contenido de ningún commit.
        todo = subprocess.run(["git", "--git-dir", str(self.git_dir), "grep", "-l", "dato sensible", "HEAD"],
                              capture_output=True, text=True)
        self.assertEqual(todo.returncode, 1, todo.stdout)

    def test_lo_que_se_parece_pero_no_es_secreto_si_entra(self):
        dentro = self.seguidos()
        for rel in ("botv3/botv3.env.example", "pi/env.ejemplo", "pi/fixtures/vivo/cola.json", "encargos/historial.jsonl",
                    "pi/cockpit-comun/tokens.css", "pc2503/trabajador.py"):
            self.assertIn(rel, dentro, rel)

    def test_las_exclusiones_viven_en_info_exclude_y_no_en_el_vault(self):
        ex = (self.git_dir / "info" / "exclude").read_text(encoding="utf-8")
        for patron in ("*.env", "secretos/", "__pycache__/", ".venv/", "/encargos/vivo/", "*.pdf"):
            self.assertIn(patron, ex)
        self.assertFalse((self.arbol / ".gitignore").exists())

    def test_mas_de_5_mb_no_entra_y_uno_que_crece_deja_de_seguirse(self):
        with open(self.arbol / "grande.bin", "wb") as fh:
            fh.truncate(vs.LIMITE_BYTES + 1)
        with open(self.arbol / "justo.bin", "wb") as fh:
            fh.truncate(vs.LIMITE_BYTES)
        self.repo.foto("con binarios")
        self.assertNotIn("grande.bin", self.seguidos())
        self.assertIn("justo.bin", self.seguidos())
        # Un archivo que ya estaba en el historial y pasa de 5 MB deja de versionarse, con aviso.
        escribir(self.arbol, "crece.md", "chico\n")
        self.repo.foto("chico")
        self.assertIn("crece.md", self.seguidos())
        with open(self.arbol / "crece.md", "wb") as fh:
            fh.truncate(vs.LIMITE_BYTES + 10)
        f = self.repo.foto("ya no es chico")
        self.assertNotIn("crece.md", self.seguidos())
        self.assertTrue(any("crece.md" in a for a in f.avisos), f.avisos)
        self.assertEqual(self.repo.git("show", "HEAD~1:crece.md").stdout, b"chico\n")      # el historial lo conserva

    def test_nombre_con_caracteres_de_patron(self):
        with open(self.arbol / "raro [1] *.bin", "wb") as fh:
            fh.truncate(vs.LIMITE_BYTES + 1)
        escribir(self.arbol, "raro [1] otro.md")
        self.repo.foto("raros")
        dentro = self.seguidos()
        self.assertNotIn("raro [1] *.bin", dentro)
        self.assertIn("raro [1] otro.md", dentro)


class RecuperarTests(Base):
    def setUp(self):
        super().setUp()
        self.repo.init()
        self.v1 = self.repo.head()
        escribir(self.arbol, "README.md", "dos\n")
        self.repo.foto("v2")

    def test_recupera_a_ruta_nueva_sin_pisar_el_original(self):
        destino = self.repo.recuperar(self.v1[:7], "README.md")
        self.assertEqual(destino, self.arbol / f"README.md.recuperado-{self.v1[:7]}")
        self.assertEqual(destino.read_text(encoding="utf-8"), "uno\n")
        self.assertEqual((self.arbol / "README.md").read_text(encoding="utf-8"), "dos\n")
        self.assertEqual(self.repo.git("status", "--porcelain").stdout, b"")      # la copia recuperada no ensucia el historial

    def test_nunca_pisa_una_recuperacion_previa_ni_un_enlace(self):
        destino = self.repo.recuperar(self.v1, "README.md")
        destino.write_text("editado por el usuario\n", encoding="utf-8")
        with self.assertRaises(vs.VersionesError):
            self.repo.recuperar(self.v1, "README.md")
        self.assertEqual(destino.read_text(encoding="utf-8"), "editado por el usuario\n")
        destino.unlink()
        blanco = self.raiz / "blanco.txt"
        blanco.write_text("no tocar\n", encoding="utf-8")
        destino.symlink_to(blanco)
        with self.assertRaises(vs.VersionesError):
            self.repo.recuperar(self.v1, "README.md")
        self.assertEqual(blanco.read_text(encoding="utf-8"), "no tocar\n")

    def test_recupera_un_archivo_borrado_y_con_tilde_por_cli(self):
        (self.arbol / "Guía de implementación.md").unlink()
        self.repo.foto("borra")
        rc, out, err = self.cli("recuperar", self.v1[:7], "Guía de implementación.md")
        self.assertEqual((rc, err), (0, ""))
        nuevo = Path(out.strip())
        self.assertEqual(nuevo.read_text(encoding="utf-8"), "tilde\n")
        self.assertFalse((self.arbol / "Guía de implementación.md").exists())

    def test_ruta_relativa_se_lee_desde_el_directorio_actual(self):
        viejo = Path.cwd()
        os.chdir(self.arbol / "encargos")
        try:
            destino = self.repo.recuperar(self.v1, "cola-run.py")
        finally:
            os.chdir(viejo)
        self.assertEqual(destino.parent, self.arbol / "encargos")

    def test_rechaza_rutas_fuera_del_arbol_y_commits_raros(self):
        for archivo in ("../fuera.md", "/etc/passwd", ".git/config", "encargos/../../fuera.md"):
            with self.assertRaises(vs.VersionesError, msg=archivo):
                self.repo.recuperar(self.v1, archivo)
        for commit in ("no-existe", "-x", ""):
            with self.assertRaises(vs.VersionesError, msg=commit):
                self.repo.recuperar(commit, "README.md")
        with self.assertRaises(vs.VersionesError):
            self.repo.recuperar(self.v1, "no-existia.md")
        with self.assertRaises(vs.VersionesError):
            self.repo.recuperar(self.v1, "encargos")        # una carpeta no es un archivo
        self.assertFalse((self.raiz / "fuera.md.recuperado-" f"{self.v1[:7]}").exists())

    def test_carpeta_destino_que_es_enlace_hacia_afuera(self):
        afuera = self.raiz / "afuera"
        afuera.mkdir()
        (self.arbol / "encargos/cola-run.py").unlink()
        (self.arbol / "encargos").rmdir()
        (self.arbol / "encargos").symlink_to(afuera)
        with self.assertRaises(vs.VersionesError):
            self.repo.recuperar(self.v1, "encargos/cola-run.py")
        self.assertEqual(list(afuera.iterdir()), [])
        (self.arbol / "encargos").unlink()

    def test_enlace_intermedio_no_crea_carpetas_afuera(self):
        """Reproducción de la revisión 1: a/nested/x.md con `a` reemplazado por un enlace a «afuera»."""
        escribir(self.arbol, "a/nested/x.md", "profundo\n")
        self.repo.foto("anidado")
        commit = self.repo.head()
        shutil.rmtree(self.arbol / "a")
        afuera = self.raiz / "afuera"
        afuera.mkdir()
        (self.arbol / "a").symlink_to(afuera)
        with self.assertRaises(vs.VersionesError):
            self.repo.recuperar(commit, "a/nested/x.md")
        self.assertEqual(list(afuera.iterdir()), [])            # ni «nested» ni el archivo
        # enlace en el tramo más profundo, con el padre real
        (self.arbol / "a").unlink()
        (self.arbol / "a").mkdir()
        (self.arbol / "a/nested").symlink_to(afuera)
        with self.assertRaises(vs.VersionesError):
            self.repo.recuperar(commit, "a/nested/x.md")
        self.assertEqual(list(afuera.iterdir()), [])

    def _carrera(self, cuando):
        """Fotografía a/nested/x.md y recupera con un gancho que, al cumplirse `cuando(operación, ruta)`, cambia
        `a` por un enlace a «afuera» (la carpeta original se aparta). Devuelve (error|None, afuera, apartada)."""
        escribir(self.arbol, "a/nested/x.md", "profundo\n")
        self.repo.foto("anidado")
        commit = self.repo.head()
        afuera = self.raiz / "afuera"
        afuera.mkdir()
        real_open, real_mkdir, hecho = os.open, os.mkdir, []

        def cambiar():
            if not hecho:
                hecho.append(1)
                os.rename(self.arbol / "a", self.arbol / "a-apartada")
                (self.arbol / "a").symlink_to(afuera)

        def mkdir(path, *a, **k):
            r = real_mkdir(path, *a, **k)
            if cuando("mkdir", path):
                cambiar()
            return r

        def abrir(path, *a, **k):
            r = real_open(path, *a, **k)
            if cuando("open", path):
                cambiar()
            return r

        error = None
        shutil.rmtree(self.arbol / "a")
        with mock.patch.object(vs.os, "mkdir", mkdir), mock.patch.object(vs.os, "open", abrir):
            try:
                self.repo.recuperar(commit, "a/nested/x.md")
            except vs.VersionesError as e:
                error = e
        return error, afuera, self.arbol / "a-apartada"

    def test_carrera_enlace_tras_abrir_el_tramo_no_escapa(self):
        """Codex vuelta 2, hallazgo 1: `a` pasa a enlace JUSTO después de abrirlo. Nada debe llegar a «afuera»."""
        error, afuera, apartada = self._carrera(lambda op, p: op == "open" and p == "a")
        self.assertEqual(list(afuera.iterdir()), [])
        self.assertTrue(error is not None or list(apartada.rglob("x.md.recuperado-*")))

    def test_carrera_enlace_antes_de_abrir_el_tramo_se_rechaza(self):
        """El cambio ocurre entre crear `a` y abrirlo: O_NOFOLLOW lo rechaza y «afuera» sigue vacía."""
        error, afuera, apartada = self._carrera(lambda op, p: op == "mkdir" and p == "a")
        self.assertEqual(list(afuera.iterdir()), [])
        self.assertIsNotNone(error)

    def test_crea_carpetas_faltantes_dentro_del_arbol(self):
        escribir(self.arbol, "b/c/d.md", "hondo\n")
        self.repo.foto("hondo")
        commit = self.repo.head()
        shutil.rmtree(self.arbol / "b")
        destino = self.repo.recuperar(commit, "b/c/d.md")
        self.assertEqual(destino.read_text(encoding="utf-8"), "hondo\n")
        self.assertEqual(destino.parent, self.arbol / "b/c")

    def test_el_arbol_real_no_tiene_git_dentro(self):
        """Verificación de cierre: ni carpeta ni puntero `.git` en el árbol real (solo se lee)."""
        real = Path(__file__).resolve().parent.parent
        self.assertFalse((real / ".git").exists() or (real / ".git").is_symlink(),
                         f"borra {real / '.git'} (rmdir si está vacía): el repo vive fuera del vault")


class ColaRunTests(Base):
    """cola-run.py con git de verdad en un temporal y con git roto: la cola sigue."""

    @classmethod
    def setUpClass(cls):
        cls.cr = _cargar("cola_run", "cola-run.py")

    def setUp(self):
        super().setUp()
        self.logs = self.raiz / "logs"
        self.logs.mkdir()
        self.eventos: list[str] = []
        self.parches = [
            mock.patch.object(self.cr, "L", self.logs), mock.patch.object(self.cr, "E", self.raiz / "enc"),
            mock.patch.object(self.cr, "SIMULANDO", False), mock.patch.object(self.cr, "MANIFIESTO", {
                "nombre": "colaT", "pruebas": ["a.py"], "etapa": []}),
            mock.patch.object(self.cr, "log", lambda t: self.eventos.append(t)),
            mock.patch.object(self.cr, "vivo", lambda **k: None), mock.patch.object(self.cr, "nombre", lambda c: c),
            mock.patch.object(self.cr, "anotar", lambda *a, **k: None),
            mock.patch.object(self.cr, "MODELOS", self.raiz / "no-hay-modelos.toml"),
            mock.patch.object(self.cr, "VIVO", {"eta": {k: "2026-10-07T00:00" for k in ("esperado", "min", "max")}}),
            mock.patch.object(self.cr, "_VERS_MOD", None),
            mock.patch.dict(os.environ, {"VERSIONES_REPO": str(self.git_dir), "VERSIONES_ARBOL": str(self.arbol)}),
        ]
        for p in self.parches:
            p.start()
            self.addCleanup(p.stop)
        self.cr.GIT_BASE.clear()
        (self.raiz / "enc").mkdir()
        (self.raiz / "enc" / "33-x.md").write_text("# encargo de prueba\n", encoding="utf-8")
        self.prompts: list[tuple[str, str]] = []

    def etapa_falsa(self, git_roto: bool, autor_extra=None):
        et = {"id": "33", "encargo": "33-x.md", "autor": "claude_cami", "revisor": "codex", "vueltas": 1}
        f = {"min": 1, "pct_5h": 1, "pct_sem": 1, "debil": False, "por_factor": None}

        def correr(cid, prompt, nombre_log, mod=None, herramientas=""):
            self.prompts.append((nombre_log, prompt))
            if nombre_log.endswith("autor"):
                escribir(self.arbol, "README.md", "dos\n")
                (self.arbol / "encargos/cola-run.py").unlink()
                if autor_extra:
                    autor_extra()
            else:
                (self.raiz / "enc" / "33r-RESULTADO.md").write_text("ok\nVEREDICTO: DESPLEGABLE\n", encoding="utf-8")
            return {"rc": 0, "min": 0.1, "tokens": None, "sin_cuota": False, "modelo_real": None}

        parches = [mock.patch.object(self.cr, "chequear_cuota", lambda *a, **k: (f, {"5h": 1.0, "fuente": "x"})),
                   mock.patch.object(self.cr, "correr", correr)]
        if git_roto:
            malo = mock.Mock()
            malo.foto.side_effect = vs.VersionesError("git no funciona")
            malo.diff.side_effect = vs.VersionesError("git no funciona")
            parches.append(mock.patch.object(self.cr, "_vers", lambda: malo))
        with contextlib.ExitStack() as st:
            for p in parches:
                st.enter_context(p)
            return self.cr.etapa(et)

    def test_fotos_antes_y_despues_y_diff_para_el_revisor(self):
        self.repo.init()
        self.assertTrue(self.etapa_falsa(git_roto=False))
        msgs = self.repo.git("log", "--format=%s", "--reverse").stdout.decode().splitlines()
        self.assertEqual(msgs, ["estado inicial", "colaT · 33 · autor"])      # las demás no cambiaron nada: sin commit
        (nombre, prompt), = [x for x in self.prompts if x[0].endswith("rev1")]
        diff = self.logs / "colaT-33-diff.txt"
        self.assertIn(str(diff), prompt)
        self.assertNotIn("{DIFF}", prompt)
        texto = diff.read_text(encoding="utf-8")
        self.assertIn("-uno", texto)
        self.assertIn("+dos", texto)
        self.assertIn("-print('a')", texto)         # lo borrado
        self.assertEqual(json.loads((self.logs / "colaT-git.json").read_text())["33"], self.repo.git(
            "rev-list", "--max-parents=0", "HEAD").stdout.decode().strip())
        self.assertEqual([e for e in self.eventos if "historial git" in e], [])

    def test_si_git_falla_la_cola_sigue_y_lo_anota(self):
        self.assertTrue(self.etapa_falsa(git_roto=True))
        avisos = [e for e in self.eventos if "historial git" in e]
        self.assertGreaterEqual(len(avisos), 3)
        self.assertTrue(all("la cola sigue" in e or "la revisión sigue" in e for e in avisos), avisos)
        (nombre, prompt), = [x for x in self.prompts if x[0].endswith("rev1")]
        diff = self.logs / "colaT-33-diff.txt"
        self.assertIn(str(diff), prompt)                              # la plantilla igual recibe una ruta que existe
        self.assertIn("No hay diff", diff.read_text(encoding="utf-8"))
        self.assertTrue((self.arbol / "README.md").read_text() == "dos\n")      # el autor falso sí trabajó

    def test_sin_repositorio_iniciado_la_cola_tambien_sigue(self):
        self.assertFalse(self.git_dir.exists())
        self.assertTrue(self.etapa_falsa(git_roto=False))
        self.assertTrue(any("init" in e for e in self.eventos), self.eventos)
        self.assertFalse(self.git_dir.exists())

    def test_git_foto_nunca_lanza_y_simulando_no_hace_nada(self):
        with mock.patch.object(self.cr, "_vers", side_effect=RuntimeError("no hay módulo")):
            self.assertIsNone(self.cr.git_foto("x"))
        self.assertIn("la cola sigue", self.eventos[-1])
        with mock.patch.object(self.cr, "SIMULANDO", True), mock.patch.object(self.cr, "_vers") as v:
            self.assertIsNone(self.cr.git_foto("x"))
            v.assert_not_called()

    def test_base_guardada_sobrevive_a_un_desde(self):
        self.cr.git_base_guardar("33", "a" * 40)
        self.cr.GIT_BASE.clear()
        self.cr.git_base_cargar()
        self.assertEqual(self.cr.GIT_BASE, {"33": "a" * 40})
        (self.logs / "colaT-git.json").write_text("{roto", encoding="utf-8")
        self.cr.git_base_cargar()
        self.assertEqual(self.cr.GIT_BASE, {})

    def test_plantilla_tiene_el_marcador_y_el_revisor_lo_recibe(self):
        txt = (AQUI / "revision-plantilla-v2.md").read_text(encoding="utf-8")
        self.assertIn("{DIFF}", txt)
        et = {"id": "33", "encargo": "33-x.md", "autor": "claude_cami", "revisor": "codex"}
        p = self.cr.prompt_de("rev1", et, False, "", "/tmp/d.txt")
        self.assertIn("`/tmp/d.txt`", p)
        self.assertIn("incluido lo\n  borrado", p)
        self.assertIn("no hay diff", self.cr.prompt_de("rev1", et, False))

    # --- arboles_extra (encargo 38, revisión 1, hallazgo 1): lo escrito en una carpeta hermana entra al diff ---

    HERMANA = "13-Agente-Noticias"

    def hermana(self, iniciar=True):
        """Carpeta hermana de 11-Pi5 con su historial al lado del principal, como en la Pi."""
        arbol = self.arbol.parent / self.HERMANA
        escribir(arbol, "pi/seleccion.py", "print('ya estaba')\n")
        repo = vs.Repo(self.git_dir.parent / f"{self.HERMANA}.git", arbol)
        if iniciar:
            repo.init()
        return arbol, repo

    def autor_del_38(self, arbol):
        """Lo mismo que creó el autor de la etapa 38: un script, un guion y un .ogg (binario) en la hermana."""
        def escribe():
            escribir(arbol, "pi/boletin_audio.py", "print('boletin')\n")
            escribir(arbol, "muestras/2026-10-09-1930/guion.txt", "Buenas tardes.\n")
            (arbol / "muestras/2026-10-09-1930/boletin-daniela.ogg").write_bytes(b"OggS\x00\x02" + bytes(range(256)))
        return escribe

    def test_sin_arboles_extra_lo_de_la_hermana_no_aparece_en_el_diff(self):
        """Reproduce el hallazgo: con el manifiesto de antes, el diff solo ve 11-Pi5."""
        self.repo.init()
        arbol, repo = self.hermana()
        self.assertTrue(self.etapa_falsa(git_roto=False, autor_extra=self.autor_del_38(arbol)))
        texto = (self.logs / "colaT-33-diff.txt").read_text(encoding="utf-8")
        self.assertIn("+dos", texto)
        self.assertNotIn("boletin_audio.py", texto)
        self.assertEqual(repo.git("log", "--format=%s").stdout.decode().splitlines(), ["estado inicial"])

    def test_arboles_extra_fotos_y_diff_de_la_carpeta_hermana(self):
        self.repo.init()
        arbol, repo = self.hermana()
        self.cr.MANIFIESTO["arboles_extra"] = [self.HERMANA]
        self.assertTrue(self.etapa_falsa(git_roto=False, autor_extra=self.autor_del_38(arbol)))
        base = repo.git("rev-list", "--max-parents=0", "HEAD").stdout.decode().strip()
        self.assertEqual(repo.git("log", "--format=%s", "--reverse").stdout.decode().splitlines(),
                         ["estado inicial", "colaT · 33 · autor"])
        self.assertEqual(json.loads((self.logs / "colaT-git.json").read_text())[f"33@{self.HERMANA}"], base)
        texto = (self.logs / "colaT-33-diff.txt").read_text(encoding="utf-8")
        self.assertIn("+dos", texto)                                    # el árbol principal sigue estando
        principal, extra = texto.split(f"# Árbol extra {self.HERMANA}", 1)
        self.assertNotIn("boletin_audio.py", principal)
        self.assertIn(f"{base[:7]}..{repo.head()[:7]}", extra)
        self.assertIn("pi/boletin_audio.py", extra)
        self.assertIn("+print('boletin')", extra)
        self.assertIn("+Buenas tardes.", extra)
        self.assertIn("Binary files /dev/null and b/muestras/2026-10-09-1930/boletin-daniela.ogg differ", extra)
        self.assertNotIn("seleccion.py", extra)                         # lo que ya estaba no es de la etapa
        self.assertEqual([e for e in self.eventos if "historial git" in e], [])
        self.assertEqual(hay_git_en(arbol), [])
        # Se puede revertir: la versión previa al autor no tiene el script y la de ahora sí.
        self.assertNotEqual(repo.git("cat-file", "-e", f"{base}:pi/boletin_audio.py", check=False).returncode, 0)
        self.assertEqual(repo.git("cat-file", "-p", "HEAD:pi/boletin_audio.py").stdout, b"print('boletin')\n")

    def test_arbol_extra_sin_historial_se_anota_y_la_cola_sigue(self):
        self.repo.init()
        arbol, repo = self.hermana(iniciar=False)
        self.cr.MANIFIESTO["arboles_extra"] = [self.HERMANA]
        self.assertTrue(self.etapa_falsa(git_roto=False, autor_extra=self.autor_del_38(arbol)))
        self.assertFalse(repo.git_dir.exists())                         # la cola no crea historiales por su cuenta
        self.assertTrue(any(self.HERMANA in e and "init" in e and "la cola sigue" in e for e in self.eventos),
                        self.eventos)
        texto = (self.logs / "colaT-33-diff.txt").read_text(encoding="utf-8")
        self.assertIn("+dos", texto)
        self.assertIn(f"# Árbol extra {self.HERMANA}: no hay diff", texto)
        self.assertIn("Revisa los archivos directamente", texto.split("# Árbol extra", 1)[1])

    def test_arboles_extra_solo_acepta_carpetas_hermanas(self):
        self.repo.init()
        (self.raiz / "afuera").mkdir()
        (self.arbol / "encargos").mkdir(exist_ok=True)
        malos = ["../afuera", "11-Pi5", "11-Pi5/encargos", "no-existe", "/etc", ".", "..", "", 7]
        self.cr.MANIFIESTO["arboles_extra"] = malos
        self.assertEqual(self.cr._repos_extra(), [])
        self.assertEqual(len([e for e in self.eventos if "no es una carpeta hermana" in e]), len(malos))
        self.assertIsNotNone(self.cr.git_foto("igual saca la foto principal"))
        self.assertEqual(sorted(x.name for x in (self.raiz / "git").iterdir()), ["11-Pi5.git"])

    # --- encargo 38, revisión 2, hallazgo 1: un enlace simbólico no es una carpeta hermana ---

    def enlace_a_arbol_ajeno(self, nombre="Noticias"):
        """La reproducción de la revisión: una «hermana» que es un enlace a una carpeta de fuera de
        10-Proyectos, con un `secreto.md`. El historial existe (alguien corrió `init` sobre el enlace):
        es el peor caso, porque ya nada más frena la foto."""
        ajeno = self.raiz / "afuera" / "privado"
        escribir(ajeno, "secreto.md", "no es de la etapa\n")
        (self.arbol.parent / nombre).symlink_to(ajeno, target_is_directory=True)
        repo = vs.Repo(self.git_dir.parent / f"{nombre}.git", self.arbol.parent / nombre)
        repo.init()
        return ajeno, repo

    def test_arboles_extra_rechaza_un_enlace_a_un_arbol_ajeno(self):
        self.repo.init()
        ajeno, repo = self.enlace_a_arbol_ajeno()
        self.assertTrue((self.arbol.parent / "Noticias").is_dir())      # `is_dir()` sigue el enlace: no basta
        antes = repo.head()
        self.cr.MANIFIESTO["arboles_extra"] = ["Noticias"]
        self.assertEqual(self.cr._repos_extra(), [])
        self.assertTrue(any("'Noticias'" in e and "enlace" in e and "la cola sigue" in e for e in self.eventos),
                        self.eventos)
        # La etapa entera: el «autor» escribe en el árbol ajeno a través del enlace y nada de eso se
        # fotografía ni llega al diff del revisor.
        escribe = lambda: escribir(self.arbol.parent / "Noticias", "secreto.md", "cambiado por la etapa\n")
        self.assertTrue(self.etapa_falsa(git_roto=False, autor_extra=escribe))
        self.assertEqual((ajeno / "secreto.md").read_text(encoding="utf-8"), "cambiado por la etapa\n")
        self.assertEqual(repo.head(), antes)                            # ni una foto nueva del árbol ajeno
        self.assertNotIn("33@Noticias", json.loads((self.logs / "colaT-git.json").read_text()))
        texto = (self.logs / "colaT-33-diff.txt").read_text(encoding="utf-8")
        self.assertIn("+dos", texto)                                    # el principal sí
        self.assertNotIn("secreto", texto)
        self.assertNotIn("Árbol extra", texto)
        self.assertEqual(hay_git_en(ajeno), [])

    def test_arboles_extra_rechaza_enlaces_aunque_apunten_adentro(self):
        """Lo conservador: un alias de una hermana de verdad tampoco pasa, ni una hermana real cuyo
        historial es un enlace (las fotos irían a otro repositorio)."""
        self.repo.init()
        arbol, repo = self.hermana()
        (self.arbol.parent / "Alias").symlink_to(arbol, target_is_directory=True)
        (self.arbol.parent / "Alias-relativo").symlink_to(self.HERMANA, target_is_directory=True)
        (self.arbol.parent / "Al-principal").symlink_to(self.arbol, target_is_directory=True)
        self.cr.MANIFIESTO["arboles_extra"] = ["Alias", "Alias-relativo", "Al-principal"]
        self.assertEqual(self.cr._repos_extra(), [])
        self.assertEqual(len([e for e in self.eventos if "enlace" in e]), 3)
        otra = self.arbol.parent / "14-Otra"
        escribir(otra, "a.md")
        (self.git_dir.parent / "14-Otra.git").symlink_to(repo.git_dir, target_is_directory=True)
        self.cr.MANIFIESTO["arboles_extra"] = ["14-Otra"]
        self.assertEqual(self.cr._repos_extra(), [])
        self.assertIn("14-Otra", self.eventos[-1])
        # Y la hermana de verdad, que es un directorio real con su historial real, sigue entrando.
        self.cr.MANIFIESTO["arboles_extra"] = ["Alias", self.HERMANA]
        self.assertEqual([n for n, _ in self.cr._repos_extra()], [self.HERMANA])

    def test_arboles_extra_con_el_vault_alcanzado_por_un_enlace(self):
        """Que el camino HASTA 10-Proyectos pase por un enlace no convierte a la hermana en enlace: se
        comparan rutas resueltas, no textos."""
        self.repo.init()
        arbol, repo = self.hermana()
        atajo = self.raiz / "atajo"
        atajo.symlink_to(self.arbol.parent, target_is_directory=True)
        with mock.patch.dict(os.environ, {"VERSIONES_ARBOL": str(atajo / self.arbol.name)}):
            self.cr.MANIFIESTO["arboles_extra"] = [self.HERMANA]
            (n, r), = self.cr._repos_extra()
        self.assertEqual(n, self.HERMANA)
        self.assertEqual(os.path.realpath(r.arbol), os.path.realpath(arbol))

    def test_la_carpeta_hermana_real_del_38_no_es_un_enlace(self):
        """Forma real: lo que declara cola-38.toml es un directorio de verdad dentro de 10-Proyectos."""
        import tomllib
        m = tomllib.loads((AQUI / "cola-38.toml").read_text(encoding="utf-8"))
        padre = AQUI.parent.parent
        for n in m["arboles_extra"]:
            self.assertFalse((padre / n).is_symlink(), n)
            self.assertEqual(os.path.realpath(padre / n), os.path.join(os.path.realpath(padre), n))
            historial = Path("/opt/nodo/datos/git") / f"{n}.git"
            if historial.exists():                                       # solo en la Pi
                self.assertFalse(historial.is_symlink(), historial)

    def test_manifiesto_real_del_38_declara_la_carpeta_hermana_que_escribe(self):
        """Forma real: cola-38.toml dice en su motivo que escribe en 13-Agente-Noticias; tiene que declararla."""
        import tomllib
        m = tomllib.loads((AQUI / "cola-38.toml").read_text(encoding="utf-8"))
        nombradas = set(re.findall(r"(\d\d-[\w-]+)/", m["motivo"]))
        self.assertEqual(nombradas, {"13-Agente-Noticias"})
        self.assertEqual(set(m.get("arboles_extra", [])), nombradas)
        for n in nombradas:
            self.assertTrue((AQUI.parent.parent / n).is_dir(), n)


if __name__ == "__main__":
    unittest.main()
