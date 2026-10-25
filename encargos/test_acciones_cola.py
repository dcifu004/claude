#!/usr/bin/env python3
"""Pruebas de los botones de cola de 🧵 Encargos (encargo 46c): `cola-run.py --accion {reanudar|pausar|detener}`.

    python3 encargos/test_acciones_cola.py

Todo corre sobre una carpeta temporal y `46-fixtures/`:
- los `vivo` son los que escribió cola-run.py (cola41, cola42 y cola46 pausadas por cuota el 11-10; cola44
  esperando sin sesión; cola46 corriendo; cola47 detenida; y, copiados del `vivo/` real el 12-10, cola43 en
  `esperando_cuota` y cola50 `retenida_por_usuario`), y los manifiestos son los de `46-fixtures/manifiestos/`;
- los timers son la salida real de `systemctl --user list-timers --all --output=json` y de `show … -p ExecStart`
  del 12-10-2026 (`46-fixtures/timers-usuario-1210.json`);
- donde la prueba necesita una cola corriendo, corre el `principal()` real con un motor de mentira (`correr`).
La carpeta de los vivos (ahí van la marca y el registro), los manifiestos, la bitácora, el comando tmux, el
lanzador, la hora y la espera se inyectan. tmux es un doble que calza por prefijo cuando el destino no lleva
«=», como el de verdad. Una sola prueba usa el binario tmux: en un servidor PROPIO (`-L`, otro socket) y con
nombres que no existen en el nodo. Para que ni un error llegue al tmux del usuario, toda la suite corre con
`TMUX_TMPDIR` apuntado a un temporal y sin `TMUX`.
Ninguna prueba lanza una cola, mata una sesión del usuario, toca /opt/nodo/datos ni el `vivo/` real, ni avisa.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ENCARGOS = Path(__file__).resolve().parent
PI = ENCARGOS.parent / "pi"
sys.path[:0] = [str(ENCARGOS), str(PI)]
import test_matriz_cuota as mc  # noqa: E402  (cargar, preparar, las fixtures y la hora de la foto)

FIX, MANIFIESTOS, T = mc.FIX, mc.MANIFIESTOS, mc.T
COLA_RUN = ENCARGOS / "cola-run.py"
TIMERS_REALES = json.loads((FIX / "timers-usuario-1210.json").read_text(encoding="utf-8"))
TMUX_FALSO = ("tmux-de-prueba",)
HOSTILES = ["cola4; rm", "../x", "cola46 ", " cola46", "cola46\n", "cola4", "cola", "", "COLA46", "cola46/../cola41",
            "cola46.json", "=cola46", "cola46;", "cola46$(id)", "-t", "cola4a", "cola46-b", "cola46\x00", "cola46b_", "ćola46"]
_ENTORNO: dict = {}
_VIVO_REAL = ENCARGOS / "vivo"


def _ajenos_al_vivo_real() -> set[str]:
    """Lo que esta suite podría dejar por error en el vivo/ de verdad: el registro, marcas y temporales de acción."""
    try:
        return {p.name for p in _VIVO_REAL.iterdir() if p.name == "acciones.jsonl" or p.suffix == ".pausar" or ".accion-" in p.name}
    except OSError:
        return set()


def setUpModule():
    _ENTORNO.update(tmp=tempfile.mkdtemp(prefix="tmux-de-prueba-"), TMUX=os.environ.pop("TMUX", None),
                    TMUX_TMPDIR=os.environ.get("TMUX_TMPDIR"), antes=_ajenos_al_vivo_real())
    os.environ["TMUX_TMPDIR"] = _ENTORNO["tmp"]


def tearDownModule():
    for k in ("TMUX", "TMUX_TMPDIR"):
        os.environ.pop(k, None)
        if _ENTORNO.get(k) is not None:
            os.environ[k] = _ENTORNO[k]
    shutil.rmtree(_ENTORNO["tmp"], True)
    nuevos = _ajenos_al_vivo_real() - _ENTORNO["antes"]
    if nuevos:
        raise AssertionError(f"la suite escribió en el vivo/ real: {sorted(nuevos)}")


class Muerte(BaseException):
    """La cola murió de golpe (como con SIGHUP): nada de lo suyo alcanza a correr."""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="acciones-cola-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cr = cr = mc.cargar()
        self.reloj = T
        self.avisos = mc.preparar(cr, self.tmp, lambda: self.reloj)
        shutil.copy(FIX / "historial.jsonl", self.tmp / "historial.jsonl")      # anotar() agrega: nunca sobre la fixture
        cr.HISTORIAL = self.tmp / "historial.jsonl"
        cr._AP_MOD = mc.cargar(PI / "aplicar-propuesta.py")
        cr._AP_MOD.CODEX_MODELOS = str(PI / "fixtures" / "encargos" / "models_cache.json")
        self.vivos, self.bitacora = self.tmp / "vivo", self.tmp / "COLA-ESTADO.md"
        self.sesiones: set[str] = set()
        self.pedidos: list[list[str]] = []      # lo que se le pidió a tmux
        self.lanzados: list[list[str]] = []
        self.dormidas: list[float] = []
        self.al_cortar = lambda nom: None
        self.al_dormir = lambda: None
        self.corta = True                       # si kill-session de verdad cierra la sesión
        self.uso_ruta = FIX / "uso-limites.json"
        cr.subprocess = type("SoloDobles", (), {"run": staticmethod(self.proceso), "CompletedProcess": subprocess.CompletedProcess,
                                                "SubprocessError": subprocess.SubprocessError, "TimeoutExpired": subprocess.TimeoutExpired,
                                                "DEVNULL": subprocess.DEVNULL})
        cr.TMUX, cr._lanzar = TMUX_FALSO, self.lanzar           # también por la línea de comandos (main())
        cr.time = type("Reloj", (), {"sleep": staticmethod(self.dormir), "monotonic": staticmethod(time.monotonic)})
        for nombre in ("pedir_autorizacion", "nodo_desplegar"):
            setattr(cr, nombre, lambda *a, **k: self.fail("la prueba no pide nada a Telegram"))
        # Lo de una cola en marcha que no es de estas pruebas: suites, catálogo y fotos de git.
        cr.pruebas = lambda: (set(), "")
        cr.foto = lambda: {"entradas": {}, "paginas": {}, "sin_catalogo": set()}
        cr.git_foto = lambda mensaje: None
        cr.git_base_guardar = cr.git_base_cargar = lambda *a, **k: None
        cr.git_diff_etapa = lambda *a: ""
        cr.medir = lambda cid: {"5h": 10.0, "sem": 10.0, "renueva_5h": self.reloj + timedelta(hours=3),
                                "renueva_sem": self.reloj + timedelta(days=3), "momento": None, "fuente": "fresco"}

    # ---- dobles
    def proceso(self, cmd, *a, **k):
        cmd = list(cmd)
        P = lambda rc, salida="": subprocess.CompletedProcess(cmd, rc, salida, "")
        if cmd[:3] == ["systemctl", "--user", "list-timers"]:
            return P(0, TIMERS_REALES["list_timers"])
        if cmd[:3] == ["systemctl", "--user", "show"]:
            return P(0, TIMERS_REALES["exec_start"][cmd[3]])
        if tuple(cmd[:1]) != TMUX_FALSO or k.get("shell"):
            raise AssertionError(f"la prueba no puede lanzar procesos: {cmd}")
        self.pedidos.append(cmd[1:])
        orden, (_, destino) = cmd[1], cmd[2:4]
        self.assertIn(orden, ("has-session", "kill-session"))
        self.assertEqual(cmd[2], "-t")
        # Como tmux: con «=» el nombre tiene que ser entero; sin «=», primero el exacto y si no el que empiece así.
        if destino.startswith("="):
            halladas = [s for s in self.sesiones if s == destino[1:]]
        else:
            halladas = [s for s in self.sesiones if s == destino] or sorted(s for s in self.sesiones if s.startswith(destino))
        if orden == "kill-session" and halladas and self.corta:
            self.sesiones.discard(halladas[0])
            self.al_cortar(halladas[0])
        return P(0 if halladas else 1)

    def lanzar(self, argv):
        self.lanzados.append(list(argv))
        self.sesiones.add(argv[4])
        return 0

    def dormir(self, segundos):
        self.dormidas.append(segundos)
        self.al_dormir()

    def uso_de(self, cid):
        return self.cr.uso(cid, self.uso_ruta, self.reloj)

    # ---- escenario
    def poner(self, fixture: str, **cambios) -> dict:
        v = json.loads((FIX / fixture).read_text(encoding="utf-8")) | cambios
        (self.vivos / f"{v['nombre']}.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
        return v

    def manifiesto(self, origen: str | Path = "cola-41.toml", texto: str | None = None, destino: str | None = None) -> Path:
        """Un manifiesto de las fixtures en la carpeta temporal, sin las suites de verdad ni despliegue."""
        if texto is None:
            texto = (MANIFIESTOS / origen).read_text(encoding="utf-8")
        texto = re.sub(r"^pruebas = .*$", "pruebas = []", texto, flags=re.M)
        texto = re.sub(r'^despliegue = "[^"]*"', 'despliegue = "nada"', texto, flags=re.M)
        man = tomllib.loads(texto)
        ruta = self.tmp / (destino or f"cola-{man['nombre'][4:]}.toml")
        ruta.write_text(texto, encoding="utf-8")
        for et in man["etapa"]:
            (self.tmp / et["encargo"]).write_text("# encargo\n", encoding="utf-8")
        return ruta

    def vivo(self, cola: str) -> dict:
        return json.loads((self.vivos / f"{cola}.json").read_text(encoding="utf-8"))

    def marca(self, cola: str) -> Path:
        return self.vivos / f"{cola}.pausar"

    def registro(self) -> list[dict]:
        ruta = self.vivos / "acciones.jsonl"
        return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()] if ruta.exists() else []

    def arbol(self) -> dict:
        """Todo lo que hay en la carpeta temporal: nombre → (tipo, modo, bytes). Para probar que algo no escribió."""
        out = {}
        for p in sorted(self.tmp.rglob("*")):
            st = p.lstat()
            regular = stat.S_ISREG(st.st_mode)        # la fecha de una carpeta cambia con solo crear algo adentro: lo delata la lista
            out[str(p.relative_to(self.tmp))] = (stat.S_IFMT(st.st_mode), stat.S_IMODE(st.st_mode), st.st_mtime_ns if regular else None,
                                                 p.read_bytes() if regular else None)
        return out

    def accion(self, accion: str, cola, simular: bool = False, **extra) -> dict:
        entradas = dict(vivos_dir=self.vivos, manifiestos_dir=self.tmp, tmux=TMUX_FALSO, lanzar=self.lanzar,
                        estado_md=self.bitacora, momento=self.reloj, dormir=self.dormir, uso_de=self.uso_de, timers=[])
        return self.cr.accion_cola(accion, cola, simular, **(entradas | extra))

    def por_comandos(self, *argumentos) -> tuple[int, dict, str]:
        """`cola-run.py <argumentos>` como lo corre la página: (código, el JSON de stdout, stderr)."""
        salida, error = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", [str(COLA_RUN), *argumentos]), contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            rc = self.cr.principal()
        return rc, json.loads(salida.getvalue()), error.getvalue()

    def correr_cola(self, ruta: Path, *argumentos, motor=None, veredictos: dict | None = None, con_main: bool = False):
        """La cola de verdad (`principal()`) sobre ese manifiesto, con un motor de mentira. Devuelve (código, fases que
        corrieron). `motor(nombre_log)` corre a mitad de cada fase; `veredictos` dice qué revisión aprueba."""
        corridas, cr = [], self.cr
        nom = tomllib.loads(ruta.read_text(encoding="utf-8"))["nombre"]

        def correr(cid, prompt, nombre_log, mod=None, herramientas=""):
            corridas.append(nombre_log)
            if motor:
                motor(nombre_log)
            self.reloj += timedelta(minutes=5)
            if "rev" in nombre_log:
                et = nombre_log.rsplit("-", 1)[0]
                ok = (veredictos or {}).get(nombre_log, True)
                (self.tmp / f"{et}r-RESULTADO.md").write_text("VEREDICTO: DESPLEGABLE\n" if ok else "VEREDICTO: NO DESPLEGABLE\n", encoding="utf-8")
            return {"rc": 0, "min": 5.0, "tokens": None, "sin_cuota": False, "modelo_real": None}
        cr.correr = correr
        self.sesiones.add(nom)                  # la cola corre dentro de su sesión tmux
        try:
            with mock.patch.object(sys, "argv", [str(COLA_RUN), str(ruta), *argumentos]), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = cr.main() if con_main else cr.principal()
        except Muerte:
            rc = None
        else:
            self.sesiones.discard(nom)          # terminó: tmux cierra la sesión
        return rc, corridas


class C1Nombres(Base):
    def test_rechaza_todo_nombre_que_no_calza_entero_sin_tocar_tmux_ni_archivos(self):
        self.manifiesto("cola-46.toml")
        self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46", "cola41"}
        antes = {k: v for k, v in self.arbol().items()}
        for accion in self.cr.ACCIONES:
            for nombre in HOSTILES + [None, 46, ["cola46"]]:
                with self.subTest(accion=accion, nombre=nombre):
                    r = self.accion(accion, nombre)
                    self.assertEqual((r["ok"], r["cola"]), (False, None))
                    # El mensaje es fijo: el dato hostil no vuelve en la respuesta.
                    self.assertEqual(r["error"], "nombre de cola inválido: «cola», dos dígitos y, si sigue algo, letras minúsculas o dígitos")
                    self.assertEqual(set(r), {"ok", "accion", "cola", "simulado", "error"})
        self.assertEqual((self.pedidos, self.lanzados, self.sesiones), ([], [], {"cola46", "cola41"}))
        despues = self.arbol()
        self.assertEqual(set(despues) - set(antes), {"vivo/acciones.jsonl"})          # lo único nuevo: el registro
        self.assertEqual({k: despues[k] for k in antes}, antes)
        filas = self.registro()
        self.assertEqual(len(filas), 3 * (len(HOSTILES) + 3))
        self.assertEqual({(f["cola"], f["resultado"]) for f in filas}, {(None, "rechazada")})   # el nombre hostil no queda escrito

    def test_el_regex_es_el_del_encargo_y_se_usa_con_fullmatch(self):
        fuente = COLA_RUN.read_text(encoding="utf-8")
        self.assertEqual(self.cr.RE_COLA.pattern, "cola[0-9]{2}[a-z0-9]*")           # ^cola[0-9]{2}[a-z0-9]*$, anclado por fullmatch
        self.assertEqual(re.findall(r"RE_COLA\.(\w+)\(", fuente), ["fullmatch"] * 5)       # los dos de la 46c, por la 50a el lector y el escritor del despacho, y por la 51 `_es_cola()`
        for bueno in ("cola41", "cola22b", "cola43s", "cola99", "cola461"):
            self.assertTrue(self.cr.RE_COLA.fullmatch(bueno), bueno)
        self.assertTrue(re.match(r"^cola[0-9]{2}[a-z0-9]*$", "cola46\n"))            # la trampa del `$`: con match pasaría
        self.assertIsNone(self.cr.RE_COLA.fullmatch("cola46\n"))

    def test_sin_un_manifiesto_con_ese_nombre_no_hay_accion(self):
        self.manifiesto("cola-43.toml")              # el archivo es cola-43.toml, pero su `nombre` es cola43r
        self.poner("vivo-cola43r.json", nombre="cola43")
        self.poner("vivo-cola41.json")               # cola41 tiene vivo, pero ningún manifiesto
        self.sesiones = {"cola43", "cola41"}
        for accion in self.cr.ACCIONES:
            for cola in ("cola43", "cola41", "cola99"):
                r = self.accion(accion, cola)
                self.assertEqual((r["ok"], r["cola"]), (False, cola))
                self.assertIn("no hay un manifiesto", r["error"])
        self.assertEqual((self.pedidos, self.lanzados, self.sesiones), ([], [], {"cola43", "cola41"}))
        self.assertFalse(list(self.vivos.glob("*.pausar")))

    def test_un_manifiesto_que_es_un_enlace_o_un_ejemplo_no_lanza_nada(self):
        fuera = Path(tempfile.mkdtemp(prefix="fuera-"))
        self.addCleanup(shutil.rmtree, fuera, True)
        shutil.copy(MANIFIESTOS / "cola-41.toml", fuera / "cola-41.toml")
        (self.tmp / "cola-41.toml").symlink_to(fuera / "cola-41.toml")
        self.poner("vivo-cola41.json")
        self.assertIn("no hay un manifiesto", self.accion("reanudar", "cola41")["error"])
        # El primero por orden de archivo es el enlace: aunque después venga uno bueno con el mismo nombre, no se usa.
        self.manifiesto("cola-41.toml", destino="cola-41z.toml")
        self.assertIn("no hay un manifiesto", self.accion("reanudar", "cola41")["error"])
        (self.tmp / "cola-41.toml").unlink()
        (self.tmp / "cola-41z.toml").write_text("solo_simular = true\n" + (self.tmp / "cola-41z.toml").read_text(encoding="utf-8"), encoding="utf-8")
        self.assertIn("no hay un manifiesto", self.accion("reanudar", "cola41")["error"])
        self.assertEqual(self.lanzados, [])

    def test_el_nombre_que_es_prefijo_de_otra_sesion_no_la_alcanza(self):
        # El caso del encargo: `cola4` con `cola46` viva. No pasa del nombre, y nadie le pregunta nada a tmux.
        self.manifiesto("cola-46.toml")
        self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        for accion in self.cr.ACCIONES:
            self.assertFalse(self.accion(accion, "cola4")["ok"])
        self.assertEqual((self.pedidos, self.sesiones), ([], {"cola46"}))
        # Y con un nombre válido que es prefijo de otra sesión viva: cola41 pausada, `cola41x` viva.
        self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        self.sesiones = {"cola41x"}
        self.assertEqual(self.proceso([*TMUX_FALSO, "has-session", "-t", "cola41"]).returncode, 0)     # sin «=», tmux diría que existe
        self.pedidos.clear()
        self.assertIn("no hay nada que detener", self.accion("detener", "cola41")["error"])
        self.assertIn("no tiene una sesión viva", self.accion("pausar", "cola41")["error"])
        r = self.accion("reanudar", "cola41")                                   # no se niega por la sesión de otra
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.sesiones, {"cola41x", "cola41"})
        self.assertTrue(self.pedidos)
        self.assertTrue(all(p[1:] == ["-t", "=cola41"] for p in self.pedidos), self.pedidos)
        # Corriendo de verdad sin sesión propia: Detener la marca detenida y a la otra no la toca.
        self.sesiones = {"cola46b"}
        self.assertTrue(self.accion("detener", "cola46")["ok"])
        self.assertEqual(self.sesiones, {"cola46b"})

    def test_en_el_codigo_todo_destino_de_tmux_lleva_el_igual_y_no_hay_shell_ni_sudo(self):
        fuente = COLA_RUN.read_text(encoding="utf-8")
        i, j = fuente.index("# ---------------------------------------------------------------- botones de 🧵 Encargos"), fuente.index("# ---------------------------------------------------------------- principal")
        seccion = fuente[i:j]
        import ast
        arbol = ast.parse(seccion)
        for nodo in ast.walk(arbol):            # sin comentarios (ast no los guarda) ni docstrings
            if isinstance(nodo, (ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(nodo) is not None:
                nodo.body = nodo.body[1:] or [ast.Pass()]
        codigo = ast.unparse(arbol)
        self.assertEqual(re.findall(r'"-t", ([^\]]+)\]', seccion), ['f"={nom}"', 'f"={cola}"'])
        for prohibido in ("shell=True", "sudo", "os.system", "Popen", "os.environ", "getenv"):
            self.assertNotIn(prohibido, codigo, prohibido)
        # Los únicos procesos de la sección: tmux (has-session, kill-session), el lanzador y systemctl --user para leer timers.
        self.assertEqual(len(re.findall(r"subprocess\.run\(", seccion)), 3)
        self.assertEqual(len(re.findall(r"correr\(\[\"systemctl\", \"--user\", \"(?:list-timers|show)\"", seccion)), 2)


class C2Reanudar(Base):
    def linea(self, cola: str, desde: str) -> str:
        """La línea `relanzar` tal como la escribía cola-run.py antes de este encargo."""
        return f"tmux new-session -d -s {cola} python3 {COLA_RUN} {self.tmp / f'cola-{cola[4:]}.toml'} --desde {desde}"

    def test_con_el_vivo_real_de_una_pausa_por_cuota_arma_la_linea_relanzar(self):
        self.manifiesto("cola-41.toml")
        v = self.poner("vivo-cola41.json")
        self.assertEqual((v["estado"], v["reanuda_desde"]), ("pausada", "41:rev3"))
        self.assertIn("sin margen para rev: semanal 75 %", v["motivo_pausa"])
        r = self.accion("reanudar", "cola41")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.lanzados, [self.linea("cola41", "41:rev3").split(" ")])
        self.assertEqual((r["linea"], r["desde"], r["sesion"]), (self.linea("cola41", "41:rev3"), "41:rev3", True))
        self.assertEqual(self.registro(), [{"momento": mc.iso(T), "accion": "reanudar", "cola": "cola41", "resultado": "hecho",
                                            "detalle": r["mensaje"], "desde": "41:rev3"}])
        self.assertEqual(self.vivo("cola41"), v)             # reanudar no escribe el vivo: lo escribe la cola al partir

    def test_es_la_misma_linea_que_manda_la_pausa_de_la_cola_de_verdad(self):
        # La cola real se queda sin cuota semanal antes de rev3 (el caso de cola41) y avisa con su línea `relanzar`.
        ruta = self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        self.cr.medir = lambda cid: {"5h": 10.0, "sem": 75.0 if cid == "claude_cami" else 10.0, "renueva_5h": self.reloj + timedelta(hours=3),
                                     "renueva_sem": self.reloj + timedelta(days=3), "momento": None, "fuente": "fresco"}
        rc, corridas = self.correr_cola(ruta, "--desde", "41:rev3")
        self.assertEqual((rc, corridas), (3, []))
        v = self.vivo("cola41")
        self.assertEqual((v["estado"], v["reanuda_desde"]), ("pausada", "41:rev3"))
        self.assertRegex(v["motivo_pausa"], r"^Claude \(Cami\) sin margen para rev: semanal 75 % \+ [\d.]+ % > tope 75 %$")
        texto, linea = next((aviso[0], aviso[1]) for aviso in self.avisos
                             if len(aviso) == 2 and aviso[1] == self.linea("cola41", "41:rev3"))
        self.assertEqual(linea, self.linea("cola41", "41:rev3"))
        self.avisos.clear()
        r = self.accion("reanudar", "cola41")
        self.assertTrue(r["ok"], r)
        self.assertEqual(" ".join(self.lanzados[0]), linea)
        self.assertEqual(self.lanzados[0], self.cr.argv_relanzar("cola41", ruta, "41:rev3"))
        # En el código hay una sola forma de la línea: la pausa y el botón usan argv_relanzar().
        fuente = COLA_RUN.read_text(encoding="utf-8")
        self.assertEqual(fuente.count('"new-session"'), 1)
        self.assertIn('relanzar = lambda desde: " ".join(argv_relanzar(nom, ruta, desde))', fuente)

    def test_con_la_sesion_viva_se_niega(self):
        self.manifiesto("cola-41.toml")
        v = self.poner("vivo-cola41.json")
        self.sesiones = {"cola41"}
        r = self.accion("reanudar", "cola41")
        self.assertEqual((r["ok"], r["sesion"]), (False, True))
        self.assertIn("su sesión ya está viva", r["error"])
        self.assertEqual((self.lanzados, self.vivo("cola41")), ([], v))
        self.assertEqual(self.pedidos, [["has-session", "-t", "=cola41"]])
        self.assertEqual([(f["resultado"], f["cola"]) for f in self.registro()], [("rechazada", "cola41")])
        # Si tmux no contesta, tampoco: no se supone que no hay sesión.
        self.cr.subprocess.run = staticmethod(lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("tmux")))
        self.assertIn("no se pudo consultar tmux", self.accion("reanudar", "cola41")["error"])
        self.assertEqual(self.lanzados, [])

    def test_con_dos_clics_simultaneos_se_lanza_una_sola_vez(self):
        self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")

        def carrera() -> list[dict]:
            self.sesiones.clear()
            self.lanzados.clear()
            juntos, resultados = threading.Barrier(2), []

            def lento(argv):
                self.lanzados.append(list(argv))
                time.sleep(0.3)                 # tmux tarda en crear la sesión: el otro clic llega en el medio
                self.sesiones.add(argv[4])
                return 0

            def clic():
                juntos.wait()
                resultados.append(self.accion("reanudar", "cola41", lanzar=lento))
            hilos = [threading.Thread(target=clic) for _ in range(2)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join(20)
            return resultados
        resultados = carrera()
        self.assertEqual(len(self.lanzados), 1)
        self.assertEqual(sorted(r["ok"] for r in resultados), [False, True])
        self.assertIn("su sesión ya está viva", next(r["error"] for r in resultados if not r["ok"]))
        self.assertEqual(sorted(f["resultado"] for f in self.registro()), ["hecho", "rechazada"])      # dos líneas enteras
        # Lo que lo impide es el flock: sin él, la misma carrera lanza dos veces (la prueba distingue los dos casos).
        self.cr.fcntl = type("SinCandado", (), {"flock": staticmethod(lambda fd, modo: None), "LOCK_EX": 2})
        carrera()
        self.assertEqual(len(self.lanzados), 2)

    def test_que_colas_se_reanudan_y_cuales_no(self):
        self.manifiesto("cola-41.toml")
        base = json.loads((FIX / "vivo-cola41.json").read_text(encoding="utf-8"))
        casos = [
            ("pausada por cuota (el vivo real)", {}, "41:rev3"),
            ("pausada por el usuario", {"estado": "pausada_por_usuario", "motivo_pausa": self.cr.MOTIVO_PAUSA_USUARIO, "reanuda_desde": "41:fix1"}, "41:fix1"),
            ("detenida con su --desde", {"estado": "detenida", "reanuda_desde": "41:rev1"}, "41:rev1"),
            ("quedó «corriendo» hace 20 h, sin sesión", {"estado": "corriendo", "etapa": "41", "fase": "fix2", "reanuda_desde": None,
                                                        "escrito": mc.iso(T - timedelta(hours=20))}, "41:fix2"),
            ("pausada por otro motivo", {"motivo_pausa": "no hay dato de cuota semanal de Codex (uso.json)"}, "no es la cuota"),
            ("detenida sin --desde (NO DESPLEGABLE)", {"estado": "detenida", "reanuda_desde": None}, "sin dejar desde dónde seguir"),
            ("pausada sin reanuda_desde", {"reanuda_desde": None}, "no deja una fase"),
            ("un --desde con una etapa que el manifiesto no tiene", {"reanuda_desde": "46:autor"}, "no deja una fase"),
            ("un --desde con una fase que la etapa no tiene", {"reanuda_desde": "41:rev4"}, "no deja una fase"),
            ("un --desde con forma de opción", {"reanuda_desde": "41:rev1 --con-cambios"}, "no deja una fase"),
            ("corriendo hace 5 min y sin sesión", {"estado": "corriendo", "etapa": "41", "fase": "fix2", "escrito": mc.iso(T - timedelta(minutes=5))}, "primero Detener"),
            ("en pruebas finales hace 20 h", {"estado": "pruebas finales", "etapa": "41", "fase": None, "reanuda_desde": None,
                                              "escrito": mc.iso(T - timedelta(hours=20))}, "no deja una fase"),
            ("caída", {"estado": "caída", "error": "RuntimeError: x"}, "no se reanuda desde acá"),
            ("sin autorización", {"estado": "sin autorización"}, "no se reanuda desde acá"),
            ("terminada", {"estado": "terminada"}, "no se reanuda desde acá"),
            ("retenida a mano (el estado real de cola50)", json.loads((FIX / "vivo-cola50-retenida.json").read_text(encoding="utf-8")) | {"nombre": "cola41", "reanuda_desde": None},
             "no se reanuda desde acá"),
        ]
        for nombre, cambios, esperado in casos:
            with self.subTest(nombre):
                self.sesiones.clear()
                self.lanzados.clear()
                (self.vivos / "cola41.json").write_text(json.dumps(base | cambios, ensure_ascii=False), encoding="utf-8")
                r = self.accion("reanudar", "cola41")
                if ":" in esperado:
                    self.assertTrue(r["ok"], r)
                    self.assertEqual(self.lanzados, [self.linea("cola41", esperado).split(" ")])
                else:
                    self.assertFalse(r["ok"], r)
                    self.assertIn(esperado, r["error"])
                    self.assertEqual(self.lanzados, [])

    def test_los_vivos_reales_de_las_fixtures(self):
        # cola44 quedó «esperando» sin sesión hace 20 h: el panel la llama detenida y parte desde su primera fase.
        for man in ("cola-44.toml", "cola-42.toml", "cola-46.toml"):
            self.manifiesto(man)
        self.manifiesto(texto=mc.MANIFIESTO_46.replace('"cola46"', '"cola47"').replace("46", "47").replace("cola47", "cola47", 1))
        self.poner("vivo-cola44-esperando.json")
        self.poner("vivo-cola42.json")
        self.poner("vivo-cola46.json")
        self.poner("vivo-cola47-detenida.json")
        self.assertEqual(self.accion("reanudar", "cola44")["desde"], "44:autor")
        self.assertEqual(self.accion("reanudar", "cola42")["desde"], "42:rev1")
        # El vivo de cola46 se pausó en «46:autor» cuando la cola tenía una sola etapa; el manifiesto de hoy tiene 46a, 46b
        # y 46c. Con ese --desde la cola se saltaría todo y pediría el despliegue: no se lanza.
        self.assertIn("no deja una fase del manifiesto", self.accion("reanudar", "cola46")["error"])
        r = self.accion("reanudar", "cola47")           # agotó sus vueltas en 47b:rev3: no dejó desde dónde seguir
        self.assertIn("sin dejar desde dónde seguir", r["error"])
        self.assertEqual([a[4] for a in self.lanzados], ["cola44", "cola42"])

    def test_un_vivo_a_medias_un_enlace_o_ninguno_se_rechazan_sin_caerse(self):
        self.manifiesto("cola-41.toml")
        entero = (FIX / "vivo-cola41.json").read_text(encoding="utf-8")
        destino = self.vivos / "cola41.json"
        for nombre, preparar in (("no hay vivo", lambda: None),
                                 ("JSON a medias", lambda: destino.write_text(entero[: len(entero) // 2], encoding="utf-8")),
                                 ("vacío", lambda: destino.write_text("", encoding="utf-8")),
                                 ("no es un objeto", lambda: destino.write_text("[1, 2]", encoding="utf-8")),
                                 ("es de otra cola", lambda: destino.write_text(entero.replace('"cola41"', '"cola42"'), encoding="utf-8")),
                                 ("es un enlace", lambda: (destino.unlink(), (self.tmp / "otro.json").write_text(entero, encoding="utf-8"),
                                                           destino.symlink_to(self.tmp / "otro.json")))):
            with self.subTest(nombre):
                preparar()
                r = self.accion("reanudar", "cola41")
                self.assertFalse(r["ok"])
                self.assertIn("no tiene un vivo legible", r["error"])
        self.assertEqual(self.lanzados, [])
        # La cola que relee su vivo mientras alguien lo escribe tampoco se cae: parte sin historia.
        destino.unlink()
        destino.write_text(entero[: len(entero) // 2], encoding="utf-8")
        self.assertIsNone(self.cr.vivo_anterior("cola41"))

    def test_si_tmux_no_crea_la_sesion_lo_dice_y_queda_en_el_registro(self):
        self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        r = self.accion("reanudar", "cola41", lanzar=lambda argv: 1)
        self.assertEqual((r["ok"], self.sesiones), (False, set()))
        self.assertIn("tmux no pudo crear la sesión", r["error"])
        r = self.accion("reanudar", "cola41", lanzar=lambda argv: 0)       # dice que la creó, pero al leer no está
        self.assertEqual((r["ok"], r["sesion"]), (False, False))
        self.assertIn("su sesión ya no está", r["error"])
        r = self.accion("reanudar", "cola41", lanzar=lambda argv: (_ for _ in ()).throw(FileNotFoundError("tmux")))
        self.assertIn("no se pudo completar (FileNotFoundError)", r["error"])
        self.assertEqual([f["resultado"] for f in self.registro()], ["fallida"] * 3)


class C3Pausar(Base):
    def test_con_la_marca_termina_la_fase_en_curso_y_no_empieza_la_siguiente(self):
        ruta = self.manifiesto("cola-41.toml")
        clics = []

        def motor(fase):
            if fase == "41-autor":              # a mitad de la fase de autor, el usuario aprieta Pausar (dos veces)
                clics.append((self.accion("pausar", "cola41"), self.vivo("cola41")["estado"], self.marca("cola41").read_text(encoding="utf-8")))
                self.reloj += timedelta(minutes=1)
                clics.append((self.accion("pausar", "cola41"), None, self.marca("cola41").read_text(encoding="utf-8")))
        rc, corridas = self.correr_cola(ruta, motor=motor)
        self.assertEqual((rc, corridas), (3, ["41-autor"]))           # la fase en curso terminó; rev1 no empezó
        (r1, estado, marca1), (r2, _, marca2) = clics
        self.assertEqual((r1["ok"], r1["ya_pedida"], r1["pausa_pedida"], estado), (True, False, True, "corriendo"))
        self.assertEqual((r2["ok"], r2["ya_pedida"], marca2), (True, True, marca1))      # creación exclusiva: la segunda no la pisa
        self.assertEqual(json.loads(marca1), {"momento": mc.iso(T), "cola": "cola41"})
        v = self.vivo("cola41")
        self.assertEqual((v["estado"], v["reanuda_desde"], v["motivo_pausa"]), ("pausada_por_usuario", "41:rev1", "pausada por el usuario desde 🧵 Encargos"))
        self.assertEqual([(f["etapa"], f["fase"]) for f in v["fases_hechas"]], [("41", "autor")])
        self.assertNotIn("fases_restantes", v)
        self.assertFalse(self.marca("cola41").exists())               # la marca se borra al atenderla
        self.assertIn("⏸️ PAUSA pedida desde 🧵 Encargos: pausada por el usuario desde 🧵 Encargos. Se reanuda desde 41:rev1",
                      self.bitacora.read_text(encoding="utf-8"))
        # Avisa como toda cola que termina (acá cae en la lista de la prueba), con la línea que la reanuda.
        (texto, linea), = self.avisos
        self.assertIn("quedó en pausa, como pediste", texto)
        self.assertEqual(linea.split(" "), self.cr.argv_relanzar("cola41", ruta, "41:rev1"))
        self.avisos.clear()
        # El historial tiene la fase que sí corrió y nada más.
        nuevas = [json.loads(x) for x in (self.tmp / "historial.jsonl").read_text(encoding="utf-8").splitlines()][len((FIX / "historial.jsonl").read_text(encoding="utf-8").splitlines()):]
        self.assertEqual([(h["encargo"], h["fase"]) for h in nuevas], [("41", "autor")])
        # Reanudar la retoma en la fase siguiente.
        r = self.accion("reanudar", "cola41")
        self.assertTrue(r["ok"], r)
        self.sesiones.clear()
        rc, corridas = self.correr_cola(ruta, *self.lanzados[0][8:])
        self.assertEqual((rc, corridas, self.vivo("cola41")["estado"]), (0, ["41-rev1"], "terminada"))
        self.avisos.clear()

    def test_entre_dos_etapas_deja_el_desde_de_la_etapa_siguiente(self):
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46)
        rc, corridas = self.correr_cola(ruta, motor=lambda fase: fase == "46a-rev1" and self.accion("pausar", "cola46"))
        self.assertEqual((rc, corridas), (3, ["46a-autor", "46a-rev1"]))
        v = self.vivo("cola46")
        self.assertEqual((v["estado"], v["reanuda_desde"]), ("pausada_por_usuario", "46b:autor"))
        self.assertFalse(self.marca("cola46").exists())
        self.avisos.clear()

    def test_pedida_durante_una_espera_de_cuota_la_fase_no_empieza(self):
        ruta = self.manifiesto("cola-41.toml")
        renueva = T + timedelta(hours=2)
        self.cr.medir = lambda cid: {"5h": 0.0 if self.reloj >= renueva else 89.0, "sem": 10.0, "renueva_5h": None if self.reloj >= renueva else renueva,
                                     "renueva_sem": self.reloj + timedelta(days=3), "momento": None, "fuente": "fresco"}
        estados = []

        def al_dormir():
            self.reloj += timedelta(seconds=self.dormidas[-1])
            if len(self.dormidas) == 1:         # en el primer tramo de la espera, el usuario aprieta Pausar
                estados.append(self.vivo("cola41")["estado"])
                self.assertTrue(self.accion("pausar", "cola41")["ok"])
        self.al_dormir = al_dormir
        rc, corridas = self.correr_cola(ruta)
        self.assertEqual((rc, corridas, estados), (3, [], ["esperando_cuota"]))     # esperó, y al salir de la espera no gastó
        v = self.vivo("cola41")
        self.assertEqual((v["estado"], v["reanuda_desde"]), ("pausada_por_usuario", "41:autor"))
        self.assertFalse({"reanuda", "espera_desde", "calculo"} & set(v))            # sin los campos de la espera
        self.assertFalse(self.marca("cola41").exists())
        self.avisos.clear()

    def test_pedida_antes_de_una_fase_sin_cuota_no_se_queda_esperando(self):
        # La revisión de Claude (Cami) tendría que esperar 2 h la cuota de 5 h. Con la pausa ya pedida durante el autor, la
        # cola no entra a esa espera ni la anuncia: se pausa apenas termina la fase en curso.
        ruta = self.manifiesto("cola-41.toml")
        renueva = T + timedelta(hours=2)
        self.cr.medir = lambda cid: {"5h": 89.0 if cid == "claude_cami" else 10.0, "sem": 10.0, "renueva_5h": renueva,
                                     "renueva_sem": self.reloj + timedelta(days=3), "momento": None, "fuente": "fresco"}
        estados = []
        real = self.cr.vivo
        self.cr.vivo = lambda **cambios: (real(**cambios), estados.append(self.cr.VIVO.get("estado")))[0]

        def al_dormir():                # si llegara a esperar, que falle acá y no se quede dando vueltas
            raise AssertionError("la cola se puso a esperar la cuota con la pausa ya pedida")
        self.al_dormir = al_dormir
        rc, corridas = self.correr_cola(ruta, motor=lambda fase: self.accion("pausar", "cola41"))
        self.assertEqual((rc, corridas, self.dormidas), (3, ["41-autor"], []))
        self.assertNotIn("esperando_cuota", estados)
        self.assertEqual(estados[-1], "pausada_por_usuario")
        self.assertEqual(self.vivo("cola41")["reanuda_desde"], "41:rev1")
        (texto, _), = self.avisos                    # un solo aviso, el de la pausa: ninguno de «espera la cuota»
        self.assertIn("quedó en pausa, como pediste", texto)
        self.avisos.clear()

    def test_si_se_cruza_con_una_pausa_por_cuota_gana_la_del_usuario(self):
        # Una cola «pausada» por cuota la relanza sola un timer: si el usuario pidió pausar, no puede quedar así.
        ruta = self.manifiesto("cola-41.toml")
        self.cr.medir = lambda cid: {"5h": 10.0, "sem": 75.0 if cid == "claude_cami" else 10.0, "renueva_5h": self.reloj + timedelta(hours=3),
                                     "renueva_sem": self.reloj + timedelta(days=3), "momento": None, "fuente": "fresco"}
        # La marca llega durante el autor (Codex); la revisión de Claude (Cami) no tiene cuota. Se quita el primer punto de
        # pausa para que la cola llegue a chequear la cuota con la marca puesta.
        real = self.cr.atender_pausa
        vistos = []
        self.cr.atender_pausa = lambda desde: vistos.append(desde) if len(vistos) < 3 else real(desde)
        rc, corridas = self.correr_cola(ruta, motor=lambda fase: self.accion("pausar", "cola41"))
        self.assertEqual((rc, corridas), (3, ["41-autor"]))
        v = self.vivo("cola41")
        self.assertEqual((v["estado"], v["reanuda_desde"]), ("pausada_por_usuario", "41:rev1"))
        self.assertRegex(v["motivo_pausa"], r"^pausada por el usuario desde 🧵 Encargos \(además: Claude \(Cami\) sin margen para rev: semanal 75 %")
        self.assertFalse(self.marca("cola41").exists())
        self.avisos.clear()
        # Sin marca, la misma cola queda «pausada» por cuota, como siempre.
        self.sesiones.clear()
        self.cr.atender_pausa = real
        rc, _ = self.correr_cola(ruta, "--desde", "41:rev1")
        self.assertEqual((rc, self.vivo("cola41")["estado"]), (3, "pausada"))
        self.avisos.clear()

    def test_solo_se_pausa_una_cola_viva_a_la_que_le_queda_una_fase(self):
        self.manifiesto(texto=mc.MANIFIESTO_46)
        for nombre, cambios, viva, esperado in (
                ("sin sesión", {}, False, "no tiene una sesión viva"),
                ("en pruebas finales", {"estado": "pruebas finales", "fase": None}, True, "ya no le queda una fase por empezar"),
                ("desplegando", {"estado": "desplegando", "fase": None}, True, "ya no le queda una fase por empezar"),
                ("ya pausada, cerrando", {"estado": "pausada", "reanuda_desde": "46b:autor"}, True, "ya no le queda una fase por empezar"),
                ("terminada", {"estado": "terminada"}, True, "ya no le queda una fase por empezar")):
            with self.subTest(nombre):
                self.poner("vivo-cola46-corriendo.json", **cambios)
                self.sesiones = {"cola46"} if viva else set()
                r = self.accion("pausar", "cola46")
                self.assertFalse(r["ok"])
                self.assertIn(esperado, r["error"])
                self.assertFalse(self.marca("cola46").exists())
        for estado in self.cr.PAUSABLES:
            with self.subTest(estado):
                self.poner("vivo-cola46-corriendo.json", estado=estado)
                self.sesiones = {"cola46"}
                self.assertTrue(self.accion("pausar", "cola46")["ok"])
                self.marca("cola46").unlink()
        self.assertEqual(set(self.cr.ESTADOS_ACTIVOS) - set(self.cr.PAUSABLES), {"pruebas finales", "desplegando"})

    def test_la_marca_es_un_archivo_corriente_creado_en_exclusiva(self):
        self.manifiesto(texto=mc.MANIFIESTO_46)
        self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        fuente = COLA_RUN.read_text(encoding="utf-8")
        self.assertIn("os.open(_marca_pausa(cola, vivos_dir), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o666)", fuente)
        # Un enlace con el nombre de la marca: no se escribe a través de él y no pausa a nadie.
        ajeno = self.tmp / "ajeno.txt"
        ajeno.write_text("intacto", encoding="utf-8")
        self.marca("cola46").symlink_to(ajeno)
        r = self.accion("pausar", "cola46")
        self.assertEqual((r["ok"], ajeno.read_text(encoding="utf-8")), (False, "intacto"))
        self.assertIn("no quedó escrita", r["error"])
        self.assertFalse(self.cr.pausa_pedida("cola46", self.vivos))
        self.marca("cola46").unlink()
        self.marca("cola46").mkdir()            # ni una carpeta
        self.assertFalse(self.cr.pausa_pedida("cola46", self.vivos))
        self.marca("cola46").rmdir()
        # El dueño y el modo: los de cualquier archivo que crea este usuario en vivo/.
        self.assertTrue(self.accion("pausar", "cola46")["ok"])
        testigo = self.vivos / "testigo"
        testigo.write_text("x", encoding="utf-8")
        st, st_t = self.marca("cola46").stat(), testigo.stat()
        self.assertEqual((st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)), (st_t.st_uid, st_t.st_gid, stat.S_IMODE(st_t.st_mode)))

    def test_si_la_cola_termino_justo_antes_no_queda_nada_pausado(self):
        self.manifiesto(texto=mc.MANIFIESTO_46)
        self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        veces = []

        def run(cmd, *a, **k):          # la sesión se cierra entre la primera consulta y la relectura
            veces.append(cmd)
            if len(veces) == 2:
                self.sesiones.clear()
            return self.proceso(cmd, *a, **k)
        self.cr.subprocess.run = staticmethod(run)
        r = self.accion("pausar", "cola46")
        self.assertEqual((r["ok"], r["sesion"], r["pausa_pedida"]), (False, False, False))
        self.assertIn("terminó antes de ver la pausa", r["error"])
        self.assertFalse(self.marca("cola46").exists())

    def test_una_marca_que_sobro_no_pausa_a_la_corrida_siguiente_y_la_ultima_fase_la_suelta(self):
        ruta = self.manifiesto("cola-41.toml")
        self.vivos.mkdir(exist_ok=True)
        self.marca("cola41").write_text("{}", encoding="utf-8")           # quedó de una corrida anterior
        rc, corridas = self.correr_cola(ruta)
        self.assertEqual((rc, corridas, self.vivo("cola41")["estado"]), (0, ["41-autor", "41-rev1"], "terminada"))
        # Pedida durante la última fase: no queda una fase que frenar; la cola termina y la marca no sobrevive.
        self.sesiones.clear()
        rc, corridas = self.correr_cola(ruta, motor=lambda fase: fase == "41-rev1" and self.accion("pausar", "cola41"))
        self.assertEqual((rc, corridas, self.vivo("cola41")["estado"]), (0, ["41-autor", "41-rev1"], "terminada"))
        self.assertFalse(self.marca("cola41").exists())
        # Una acción o una simulación no sueltan la marca de una cola que sí corre.
        self.poner("vivo-cola41.json", estado="corriendo", etapa="41", fase="autor")
        self.sesiones = {"cola41"}
        self.assertEqual(self.por_comandos("--accion", "pausar", "cola41")[0], 0)
        self.assertEqual(self.por_comandos("--accion", "pausar", "cola41", "--simular")[0], 0)
        self.assertTrue(self.marca("cola41").exists())
        self.avisos.clear()


class C4Detener(Base):
    def cortar_en(self, ruta: Path, fase_del_corte: str, *argumentos, veredictos: dict | None = None, **extra):
        """La cola corre de verdad y, a mitad de `fase_del_corte`, el usuario aprieta Detener: la sesión muere ahí."""
        hecho = {}

        def motor(fase):
            if fase == fase_del_corte:
                hecho["antes"] = self.vivo(ruta.stem.replace("-", ""))
                hecho["r"] = self.accion("detener", ruta.stem.replace("-", ""), **extra)
                raise Muerte()
        rc, corridas = self.correr_cola(ruta, *argumentos, motor=motor, veredictos=veredictos, con_main=True)
        self.assertIsNone(rc)
        return hecho["r"], hecho["antes"], corridas

    def test_corta_deja_detenida_con_el_desde_de_la_fase_cortada_y_reanudar_retoma_ahi(self):
        ruta = self.manifiesto("cola-41.toml")
        self.marca("cola41").parent.mkdir(exist_ok=True)
        r, antes, corridas = self.cortar_en(ruta, "41-fix1", veredictos={"41-rev1": False})
        self.assertEqual(corridas, ["41-autor", "41-rev1", "41-fix1"])
        self.assertEqual((antes["estado"], antes["etapa"], antes["fase"]), ("corriendo", "41", "fix1"))
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["sesion"], r["estado"], r["desde"]), (False, "detenida", "41:fix1"))      # leído después de actuar
        self.assertEqual(self.pedidos[:3], [["has-session", "-t", "=cola41"], ["kill-session", "-t", "=cola41"], ["has-session", "-t", "=cola41"]])
        self.assertNotIn("cola41", self.sesiones)
        v = self.vivo("cola41")
        self.assertEqual((v["estado"], v["reanuda_desde"], v["motivo_pausa"]),
                         ("detenida", "41:fix1", "detenida por el usuario desde 🧵 Encargos (cortada en 41:fix1)"))
        self.assertEqual((v["fin"], v["escrito"]), (mc.iso(self.reloj), mc.iso(self.reloj)))
        self.assertNotIn("fases_restantes", v)
        self.assertEqual([(f["etapa"], f["fase"]) for f in v["fases_hechas"]], [("41", "autor"), ("41", "rev1")])     # lo andado no se pierde
        self.assertEqual(v["lanzada"], antes["lanzada"])
        linea = self.bitacora.read_text(encoding="utf-8").splitlines()[-1]
        self.assertEqual(linea, f"- {self.reloj:%d-%m %H:%M} · ⏹️ cola41: detenida por el usuario desde 🧵 Encargos (cortada en 41:fix1). Se reanuda desde 41:fix1")
        self.assertEqual([(f["accion"], f["cola"], f["resultado"], f["desde"]) for f in self.registro()], [("detener", "cola41", "hecho", "41:fix1")])
        # El panel la lista entre las detenidas, con las fases que le faltan desde la cortada.
        matriz = self.cr.matriz_cuota(vivos_dir=self.vivos, uso_de=self.uso_de, momento=self.reloj, viva=lambda n: n in self.sesiones,
                                      timers=[], manifiestos_dir=self.tmp)
        (fuera,) = [x for x in matriz["colas_fuera"] if x["cola"] == "cola41"]
        self.assertEqual((fuera["estado"], fuera["fase"], fuera["motivo"]), ("detenida", "41:fix1", v["motivo_pausa"]))
        self.assertEqual([(f["etapa"], f["fase"]) for f in fuera["fases_restantes"]], [("41", "fix1"), ("41", "rev2"), ("41", "fix2"), ("41", "rev3")])
        # Y un Reanudar posterior retoma desde ahí.
        self.assertEqual(self.avisos, [])
        r2 = self.accion("reanudar", "cola41")
        self.assertTrue(r2["ok"], r2)
        self.assertEqual(self.lanzados[0][8:], ["--desde", "41:fix1"])
        self.sesiones.clear()
        rc, corridas = self.correr_cola(ruta, *self.lanzados[0][8:])
        self.assertEqual((rc, corridas), (0, ["41-fix1", "41-rev2"]))
        final = self.vivo("cola41")
        self.assertEqual((final["estado"], [x["desde"] for x in final["relanzamientos"]]), ("terminada", ["41:fix1"]))
        self.assertEqual([(f["etapa"], f["fase"]) for f in final["fases_hechas"]], [("41", "autor"), ("41", "rev1"), ("41", "fix1"), ("41", "rev2")])
        self.avisos.clear()

    def test_el_vivo_se_reemplaza_entero_con_un_temporal_propio_y_el_modo_de_siempre(self):
        ruta = self.manifiesto("cola-41.toml")
        vistos = []
        real = os.replace

        def replace(origen, destino):
            if Path(destino).name == "cola41.json" and ".accion-" in Path(origen).name:
                vistos.append((Path(origen).name, json.loads(Path(origen).read_text(encoding="utf-8"))["estado"], self.vivo("cola41")["estado"]))
            return real(origen, destino)
        with mock.patch.object(os, "replace", replace):
            r, _, _ = self.cortar_en(ruta, "41-autor")
        self.assertTrue(r["ok"], r)
        # Hasta el rename, el que lee ve el vivo anterior entero; el temporal no es el de la cola (.cola41.json.tmp).
        (nombre, nuevo, viejo), = vistos
        self.assertRegex(nombre, rf"^\.cola41\.json\.accion-{os.getpid()}-[0-9a-f]{{8}}\.tmp$")
        self.assertEqual((nuevo, viejo), ("detenida", "corriendo"))
        self.assertEqual(sorted(p.name for p in self.vivos.iterdir()), ["acciones.jsonl", "cola41.json"])       # sin restos
        testigo = self.vivos / "testigo"
        testigo.write_text("x", encoding="utf-8")
        st, st_t = (self.vivos / "cola41.json").stat(), testigo.stat()
        self.assertEqual((st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)), (st_t.st_uid, st_t.st_gid, stat.S_IMODE(st_t.st_mode)))
        self.assertEqual(stat.S_IMODE((self.vivos / "acciones.jsonl").stat().st_mode), 0o600)

    def test_si_la_cola_alcanzo_a_escribir_mientras_moria_se_vuelve_a_dejar_detenida(self):
        self.manifiesto(texto=mc.MANIFIESTO_46)
        v = self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        tardio = []

        def al_dormir():                # el último latido de la cola cae después de la escritura de la acción
            if not tardio and self.vivo("cola46")["estado"] == "detenida":
                tardio.append(1)
                (self.vivos / "cola46.json").write_text(json.dumps(v | {"escrito": mc.iso(T + timedelta(seconds=1))}), encoding="utf-8")
        self.al_dormir = al_dormir
        self.reloj = T + timedelta(hours=1)
        r = self.accion("detener", "cola46")
        self.assertEqual((tardio, r["ok"], r["estado"]), ([1], True, "detenida"))
        self.assertEqual(self.vivo("cola46")["estado"], "detenida")

    def test_la_fase_cortada_es_la_que_dice_el_vivo_despues_del_corte(self):
        self.manifiesto(texto=mc.MANIFIESTO_46)
        v = self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        # Entre la primera lectura y el corte, la cola terminó el autor y empezó la revisión.
        self.al_cortar = lambda nom: (self.vivos / "cola46.json").write_text(json.dumps(v | {"fase": "rev1"}), encoding="utf-8")
        self.reloj = T + timedelta(hours=1)
        r = self.accion("detener", "cola46")
        self.assertEqual((r["ok"], r["desde"], self.vivo("cola46")["reanuda_desde"]), (True, "46a:rev1", "46a:rev1"))
        # Si en ese hueco la cola terminó sola, su estado final no se pisa.
        self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        self.al_cortar = lambda nom: (self.vivos / "cola46.json").write_text(json.dumps(v | {"estado": "terminada"}), encoding="utf-8")
        r = self.accion("detener", "cola46")
        self.assertEqual((r["ok"], r["estado"], r["desde"]), (True, "terminada", None))
        self.assertIn("Su estado no cambió", r["mensaje"])

    def test_si_la_sesion_no_se_corta_no_se_cambia_nada(self):
        self.manifiesto(texto=mc.MANIFIESTO_46)
        v = self.poner("vivo-cola46-corriendo.json")
        self.sesiones, self.corta = {"cola46"}, False
        r = self.accion("detener", "cola46")
        self.assertEqual((r["ok"], r["sesion"], r["estado"]), (False, True, "corriendo"))
        self.assertIn("no se pudo cortar la sesión", r["error"])
        self.assertEqual((self.vivo("cola46"), self.bitacora.exists(), self.sesiones), (v, False, {"cola46"}))
        self.assertEqual(len(self.dormidas), self.cr.CORTE_VUELTAS)
        self.assertEqual([f["resultado"] for f in self.registro()], ["fallida"])

    def test_cortada_en_una_espera_de_cuota_no_cuenta_la_espera_como_trabajo(self):
        # El vivo real de cola43 del 10-10 (esperando la cuota de 5 h desde las 22:07), con el nombre de su manifiesto.
        self.manifiesto("cola-43.toml")
        v = self.poner("vivo-cola43-esperando-cuota.json", nombre="cola43r", inicio_trabajo="2026-10-10T21:30:00-03:00", tiempo_muerto_min=4.0)
        self.assertEqual((v["estado"], v["espera_desde"]), ("esperando_cuota", "2026-10-10T22:07:32-03:00"))
        self.sesiones = {"cola43r"}
        self.reloj = datetime.fromisoformat("2026-10-10T23:07:32-03:00")       # una hora esperando
        r = self.accion("detener", "cola43r")
        self.assertEqual((r["ok"], r["desde"]), (True, "43:autor"))
        d = self.vivo("cola43r")
        self.assertEqual((d["estado"], d["reanuda_desde"]), ("detenida", "43:autor"))
        self.assertFalse(set(self.cr.CAMPOS_ESPERA) & set(d))                # sin `reanuda`: no dice que sigue sola
        self.assertEqual((d["inicio_trabajo"], d["tiempo_muerto_min"]), ("2026-10-10T22:30:00-03:00", 64.0))
        # heredar_vivo() mide lo hecho hasta `escrito`: 37 min y medio de trabajo, no 97.
        hecho = (datetime.fromisoformat(d["escrito"]) - datetime.fromisoformat(d["inicio_trabajo"])).total_seconds()
        self.assertEqual(hecho, (datetime.fromisoformat(v["espera_desde"]) - datetime.fromisoformat("2026-10-10T21:30:00-03:00")).total_seconds())

    def test_sin_sesion_y_a_medias_la_marca_detenida_y_fuera_de_las_fases_no_deja_desde(self):
        self.manifiesto(texto=mc.MANIFIESTO_46)
        v = self.poner("vivo-cola46-corriendo.json")             # «corriendo» desde las 19:36, pero la sesión ya no está
        self.reloj = datetime.fromisoformat("2026-10-11T19:46:15-03:00")
        r = self.accion("detener", "cola46")
        self.assertTrue(r["ok"], r)
        self.assertIn("cola46 ya no tenía sesión", r["mensaje"])
        self.assertEqual(self.pedidos, [["has-session", "-t", "=cola46"]] * 2)       # nada que matar
        d = self.vivo("cola46")
        self.assertEqual((d["estado"], d["reanuda_desde"]), ("detenida", "46a:autor"))
        self.assertEqual((d["inicio_trabajo"], d["tiempo_muerto_min"]), ("2026-10-11T19:46:15-03:00", 10.0))   # 10 min sin que nadie trabajara
        self.assertEqual(self.accion("reanudar", "cola46")["desde"], "46a:autor")
        # En pruebas finales no hay fase que retomar: queda detenida, sin `reanuda_desde`, y Reanudar se niega.
        self.poner("vivo-cola46-corriendo.json", estado="pruebas finales", fase=None, reanuda_desde="46a:autor")
        self.sesiones = {"cola46"}
        r = self.accion("detener", "cola46")
        self.assertEqual((r["ok"], r["desde"]), (True, None))
        self.assertIn("no deja una fase desde donde reanudar", r["mensaje"])
        d = self.vivo("cola46")
        self.assertEqual((d["estado"], "reanuda_desde" in d, d["motivo_pausa"]), ("detenida", False, "detenida por el usuario desde 🧵 Encargos (estaba en «pruebas finales»)"))
        self.assertIn("sin dejar desde dónde seguir", self.accion("reanudar", "cola46")["error"])
        # Una cola que no corre y no tiene sesión: nada que detener.
        v = self.poner("vivo-cola46.json")
        r = self.accion("detener", "cola46")
        self.assertIn("no hay nada que detener", r["error"])
        self.assertEqual(self.vivo("cola46"), v)
        # Con sesión pero ya en un estado final (cerrando): se corta y el estado no se toca.
        self.sesiones = {"cola46"}
        r = self.accion("detener", "cola46")
        self.assertEqual((r["ok"], r["estado"], self.sesiones, self.vivo("cola46")), (True, "pausada", set(), v))

    def test_detener_suelta_una_pausa_pendiente(self):
        self.manifiesto(texto=mc.MANIFIESTO_46)
        self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        self.assertTrue(self.accion("pausar", "cola46")["ok"])
        self.assertTrue(self.accion("detener", "cola46")["ok"])
        self.assertFalse(self.marca("cola46").exists())


class C5Simular(Base):
    def test_ninguna_accion_simulada_escribe_nada(self):
        for man in ("cola-41.toml", "cola-42.toml"):
            self.manifiesto(man)
        self.manifiesto(texto=mc.MANIFIESTO_46)
        self.poner("vivo-cola41.json")
        self.poner("vivo-cola42.json")
        self.poner("vivo-cola46-corriendo.json")
        self.bitacora.write_text("# bitácora\n", encoding="utf-8")
        self.sesiones = {"cola46"}
        antes = self.arbol()
        casos = [("reanudar", "cola41", True), ("reanudar", "cola42", True), ("pausar", "cola46", True), ("detener", "cola46", True),
                 ("reanudar", "cola46", False), ("pausar", "cola41", False), ("detener", "cola41", False), ("detener", "cola4; rm", False),
                 ("reanudar", "cola99", False)]
        for accion, cola, ok in casos:
            for por_comandos in (False, True):
                with self.subTest(accion=accion, cola=cola, por_comandos=por_comandos):
                    if por_comandos:
                        rc, r, error = self.por_comandos("--accion", accion, cola, "--simular")
                        self.assertEqual((rc, bool(error)), (0 if ok else 1, not ok))
                    else:
                        r = self.accion(accion, cola, True)
                    self.assertEqual((r["ok"], r["simulado"]), (ok, True))
                    self.assertEqual(self.arbol(), antes)                # ni marca, ni registro, ni vivo, ni bitácora
        self.assertEqual((self.lanzados, self.sesiones, self.dormidas), ([], {"cola46"}, []))
        self.assertEqual({p[0] for p in self.pedidos}, {"has-session"})
        self.assertFalse((self.vivos / "acciones.jsonl").exists())
        self.assertEqual(self.avisos, [])

    def test_reanudar_simulado_imprime_la_carga_proyectada(self):
        self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        r = self.accion("reanudar", "cola41", True)
        self.assertEqual((r["ok"], r["desde"], r["ya_comprometida"]), (True, "41:rev3", False))
        self.assertEqual(r["linea"], " ".join(self.cr.argv_relanzar("cola41", self.tmp / "cola-41.toml", "41:rev3")))
        # cola41 retoma en rev3 con Claude (Cami): 15 % de 5 h y 2 % de la semana, con probabilidad 1. La cuenta está en
        # 47 % de 5 h y 81 % de la semana (uso-limites.json): 90 − 47 − 15 = 28 y 75 − 81 − 2 = −8.
        (c,) = r["carga"]
        self.assertEqual({k: c[k] for k in ("cuenta", "nombre", "pct_5h", "pct_5h_min", "pct_5h_max", "pct_sem", "pct_sem_min", "pct_sem_max", "proxima_5h", "debil")},
                         {"cuenta": "claude_cami", "nombre": "Claude (Cami)", "pct_5h": 17.0, "pct_5h_min": 17.0, "pct_5h_max": 17.0, "pct_sem": 2.0,
                          "pct_sem_min": 2.0, "pct_sem_max": 2.0, "proxima_5h": 0.0, "debil": False})
        self.assertEqual(c["ventanas"], [{"ventana": "5h", "actual": 47.0, "comprometida": 0.0, "proyectada": 17.0, "tope": 90, "holgura": 26.0},
                                         {"ventana": "semanal", "actual": 81.0, "comprometida": 0.0, "proyectada": 2.0, "tope": 75, "holgura": -8.0}])
        self.assertEqual(r["texto"], ["Claude (Cami): +17 % 5 h (entre 17 y 17) · +2 % sem (entre 2 y 2) · holgura con esta carga: 5 h 26 % · sem −8 %"])
        json.dumps(r)               # todo lo que sale es JSON

    def test_la_carga_proyectada_es_la_suma_de_la_matriz_y_descuenta_la_carga_comprometida(self):
        """La misma cola43r de las dos maneras, como en la 46b: relanzada por un timer a las 21:15:30 (activa: su celda la
        calcula matriz_cuota()) y pausada sin timer, mirada a esa hora (fuera: la suma `carga_proyectada()`)."""
        self.manifiesto("cola-43.toml")
        self.manifiesto("cola-41.toml")
        self.poner("vivo-cola43r.json")
        entradas = dict(vivos_dir=self.vivos, uso_de=self.uso_de, viva=lambda n: False, manifiestos_dir=self.tmp)
        timer = [(mc.PARTE, mc.EXEC_COLA36.replace("cola36", "cola43r").replace("cola-36.toml", "cola-43.toml"))]
        activa = self.cr.matriz_cuota(momento=T, timers=timer, **entradas)
        self.assertEqual({r["cuenta"] for r in activa["reglas"]}, {"claude_cami", "codex"})
        self.reloj = mc.PARTE
        r = self.accion("reanudar", "cola43r", True)
        self.assertEqual([c["cuenta"] for c in r["carga"]], ["claude_cami", "codex"])
        for regla in activa["reglas"]:
            suya = next(c for c in r["carga"] if c["cuenta"] == regla["cuenta"])
            self.assertEqual({k: suya[k] for k in self.cr.CLAVES_CELDA + ("debil",)}, regla["celdas"]["cola43r"])
        # Con el timer puesto ya cuenta como carga comprometida: se informa su celda y la Holgura no la resta dos veces.
        self.reloj = T
        ya = self.accion("reanudar", "cola43r", True, timers=timer)
        self.assertTrue(ya["ya_comprometida"])
        cami = next(c for c in ya["carga"] if c["cuenta"] == "claude_cami")
        regla = next(x for x in activa["reglas"] if x["cuenta"] == "claude_cami")
        self.assertEqual({k: cami[k] for k in self.cr.CLAVES_CELDA}, {k: regla["celdas"]["cola43r"][k] for k in self.cr.CLAVES_CELDA})
        for w in cami["ventanas"]:
            de_la_regla = next(x for x in regla["ventanas"] if x["ventana"] == w["ventana"])
            self.assertEqual((w["comprometida"], w["holgura"]), (0.0, round(de_la_regla["tope"] - de_la_regla["actual"] - de_la_regla["pronostico"], 1)))
        self.assertEqual(ya["texto"][-1], "ya cuenta como carga comprometida: tiene una reanudación programada")
        # Con otra cola activa en la misma cuenta, la Holgura de la proyección resta también la de esa otra.
        self.poner("vivo-cola41.json")
        otra = [(mc.PARTE, mc.EXEC_COLA36.replace("cola36", "cola41").replace("cola-36.toml", "cola-41.toml"))]
        con = self.accion("reanudar", "cola43r", True, timers=otra)
        w5 = next(c for c in con["carga"] if c["cuenta"] == "claude_cami")["ventanas"][0]
        self.assertEqual((w5["ventana"], w5["comprometida"]), ("5h", 17.0))
        self.assertEqual(w5["holgura"], round(w5["tope"] - w5["actual"] - 17.0 - w5["proyectada"], 1))
        # Las líneas de la suma son las de matriz_cuota(), una al lado de la otra.
        fuente = COLA_RUN.read_text(encoding="utf-8")
        for linea in ('if ren[k] is None or ini < ren[k]:', 'c[k] += f["prob"] * f[k]', 'c[k + "_max"] += f[k]', 'c[k + "_min"] += f[k] if f["prob"] >= 1 else 0',
                      'elif k == "pct_5h":', 'c["proxima_5h"] += f["prob"] * f[k]'):
            self.assertEqual(fuente.count(linea), 2, linea)


class Registro(Base):
    def test_cada_accion_deja_una_linea_en_un_archivo_0600_que_no_se_abre_por_un_enlace(self):
        self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        viejo = os.umask(0o002)                 # con la umask más abierta del nodo sigue en 0600
        try:
            self.assertTrue(self.accion("reanudar", "cola41")["ok"])
        finally:
            os.umask(viejo)
        self.reloj += timedelta(minutes=3)
        self.accion("pausar", "cola41")
        self.accion("pausar", "cola99")
        self.accion("detener", "../x")
        registro = self.vivos / "acciones.jsonl"
        self.assertEqual(stat.S_IMODE(registro.stat().st_mode), 0o600)
        self.assertEqual(registro.stat().st_uid, os.getuid())
        filas = self.registro()
        self.assertEqual([set(f) for f in filas], [{"momento", "accion", "cola", "resultado", "detalle", "desde"}] * 4)
        self.assertEqual([(f["momento"], f["accion"], f["cola"], f["resultado"]) for f in filas],
                         [(mc.iso(T), "reanudar", "cola41", "hecho"), (mc.iso(T + timedelta(minutes=3)), "pausar", "cola41", "rechazada"),
                          (mc.iso(T + timedelta(minutes=3)), "pausar", "cola99", "rechazada"), (mc.iso(T + timedelta(minutes=3)), "detener", None, "rechazada")])
        self.assertTrue(all(isinstance(f["detalle"], str) and f["detalle"] for f in filas))
        # Un archivo abierto de más (0644) vuelve a 0600 en la acción siguiente.
        os.chmod(registro, 0o644)
        self.accion("pausar", "cola99")
        self.assertEqual(stat.S_IMODE(registro.stat().st_mode), 0o600)
        # Si el registro es un enlace o un FIFO, la acción no se hace (no hay acción sin registro) y no se cuelga.
        self.sesiones.clear()
        self.lanzados.clear()
        ajeno = self.tmp / "ajeno.txt"
        ajeno.write_text("intacto", encoding="utf-8")
        registro.unlink()
        registro.symlink_to(ajeno)
        r = self.accion("reanudar", "cola41")
        self.assertEqual((r["ok"], self.lanzados, ajeno.read_text(encoding="utf-8")), (False, [], "intacto"))
        registro.unlink()
        os.mkfifo(registro)
        r = self.accion("reanudar", "cola41")
        self.assertEqual((r["ok"], self.lanzados), (False, []))
        self.assertIn("no se pudo completar", r["error"])

    def test_el_registro_la_marca_y_los_temporales_no_son_vivos_para_nadie(self):
        self.manifiesto("cola-41.toml")
        self.manifiesto(texto=mc.MANIFIESTO_46)
        self.poner("vivo-cola41.json")
        self.poner("vivo-cola46-corriendo.json")
        entradas = dict(vivos_dir=self.vivos, uso_de=self.uso_de, momento=T, viva=lambda n: n in self.sesiones, timers=[], manifiestos_dir=self.tmp)
        self.sesiones = {"cola46"}
        antes = self.cr.matriz_cuota(**entradas)
        self.accion("pausar", "cola46")
        self.accion("reanudar", "cola99")
        (self.vivos / ".cola46.json.accion-1-abcdef01.tmp").write_text("{", encoding="utf-8")
        self.assertEqual(sorted(p.name for p in self.vivos.iterdir()), [".cola46.json.accion-1-abcdef01.tmp", "acciones.jsonl", "cola41.json", "cola46.json", "cola46.pausar"])
        self.assertEqual(self.cr.matriz_cuota(**entradas), antes)
        self.assertEqual(self.cr.leer_vivos(self.vivos)[1], [])
        # La página busca los vivos con `find -name '*.json'`: ninguno de los tres calza.
        import fnmatch
        self.assertEqual([p.name for p in self.vivos.iterdir() if fnmatch.fnmatch(p.name, "*.json")].sort(), ["cola41.json", "cola46.json"].sort())
        self.assertEqual(sorted(p.name for p in self.vivos.iterdir() if fnmatch.fnmatch(p.name, "*.json")), ["cola41.json", "cola46.json"])

    def test_ninguna_ruta_del_modulo_bajo_prueba_apunta_al_nodo(self):
        cr = self.cr
        for ruta in (cr.E, cr.D, cr.L, cr.ESTADO, cr.HISTORIAL, cr.USO, *cr.REGISTROS, self.vivos, self.bitacora):
            self.assertTrue(str(ruta).startswith(str(self.tmp)), ruta)
        self.assertEqual((cr.TMUX, os.environ.get("TMUX"), os.environ["TMUX_TMPDIR"]), (TMUX_FALSO, None, _ENTORNO["tmp"]))
        self.assertFalse(str(self.tmp).startswith("/opt/nodo"))
        # Y por defecto, en el nodo, todo queda dentro de encargos/: la marca y el registro en vivo/, el tmux de siempre.
        real = mc.cargar()
        self.assertEqual(real.E, Path("/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos"))
        self.assertEqual((real._marca_pausa("cola46"), real.TMUX, real.ESTADO), (real.E / "vivo" / "cola46.pausar", ("tmux",), real.E / "COLA-ESTADO.md"))


class Panel(Base):
    """`--panel` dice qué botones valen en cada cola y qué timers la nombran: la página solo dibuja eso."""

    def panel(self, **extra) -> dict:
        self.cr.SIMULANDO = True
        return self.cr.panel(**(dict(vivos_dir=self.vivos, uso_de=self.uso_de, momento=self.reloj, viva=lambda n: n in self.sesiones,
                                     manifiestos_dir=self.tmp) | extra))

    def escenario(self):
        for man in ("cola-41.toml", "cola-42.toml", "cola-44.toml"):
            self.manifiesto(man)
        self.manifiesto(texto=mc.MANIFIESTO_46)
        self.manifiesto(texto=mc.MANIFIESTO_46.replace('nombre = "cola46"', 'nombre = "cola47"'), destino="cola-47.toml")
        self.manifiesto(texto=mc.MANIFIESTO_46.replace('nombre = "cola46"', 'nombre = "cola50"'), destino="cola-50.toml")
        self.poner("vivo-cola41.json")
        self.poner("vivo-cola42.json", estado="terminada")
        self.poner("vivo-cola43r.json")                       # pausada por cuota, sin manifiesto con su nombre
        self.poner("vivo-cola44-esperando.json")
        self.poner("vivo-cola46-corriendo.json")
        self.poner("vivo-cola47-detenida.json")
        self.poner("vivo-cola50-retenida.json")
        self.sesiones = {"cola46"}

    def test_los_botones_de_cada_cola_y_los_timers_reales_del_12_10(self):
        self.escenario()
        self.reloj = datetime.fromisoformat("2026-10-11T19:40:00-03:00")
        self.assertTrue(self.accion("pausar", "cola46")["ok"])
        colas = self.panel()["colas"]              # sin timers inyectados: lee los de systemd (acá, la salida real guardada)
        self.assertEqual({c: x["acciones"] for c, x in colas.items()},
                         {"cola41": ["reanudar"], "cola43r": [], "cola44": ["reanudar", "detener"], "cola46": ["pausar", "detener"],
                          "cola47": [], "cola50": []})                          # la terminada no se publica
        self.assertEqual({c: x["pausa_pedida"] for c, x in colas.items() if x["pausa_pedida"]}, {"cola46": True})
        self.assertEqual({c: x["no_reanuda"] for c, x in colas.items() if x["no_reanuda"]},
                         {"cola43r": "no hay un manifiesto con ese nombre",
                          "cola47": "se detuvo sin dejar desde dónde seguir (una etapa quedó NO DESPLEGABLE o fallaron las pruebas finales)",
                          "cola50": "está en «retenida_por_usuario»: no se reanuda desde acá"})
        # orden-renov-1122.timer nombra a cola49, cola50, cola43s, cola41 y cola42, y ya disparó: vencido.
        vencido = [{"unidad": "orden-renov-1122.timer", "proxima": None, "vencido": True}]
        self.assertEqual({c: x["timers"] for c, x in colas.items()},
                         {"cola41": vencido, "cola43r": [], "cola44": [], "cola46": [], "cola47": [], "cola50": vencido})
        self.assertEqual(set(self.panel()) - {"colas"}, {"modelos", "catalogo", "pronosticos", "reglas", "colas_fuera", "capacidad_por_vencer", "momento", "cuentas", "despacho", "pasado"})

    def test_la_salida_real_de_systemctl_y_un_timer_que_todavia_va_a_disparar(self):
        filas = self.cr.timers_usuario(self.proceso)
        self.assertEqual([(t["unidad"], t["proxima"], t["ultima"]) for t in filas],
                         [("cola36-reanudar.timer", None, None),
                          ("orden-renov-1122.timer", None, datetime.fromtimestamp(1791767110.788844).astimezone()),
                          ("pedidos-0910.timer", None, datetime.fromtimestamp(1791570617.089772).astimezone())])
        self.assertIn("reanudar-en-orden.sh cola49 cola50 cola43s cola41 cola42", filas[1]["orden"])
        self.assertEqual([self.cr._nombra(filas[1]["orden"], c) for c in ("cola41", "cola4", "cola43", "cola43s", "cola5", "orden")], [True, False, False, True, False, False])
        self.assertTrue(self.cr._nombra(filas[0]["orden"], "cola36"))
        for roto in (lambda cmd, **k: (_ for _ in ()).throw(FileNotFoundError("systemctl")),
                     lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, "Failed to connect to bus", ""),
                     lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, '{"next": 5}', "")):
            self.assertEqual(self.cr.timers_usuario(roto), [])
        # Con una próxima hora: la misma fila real, con el `next` de la fixture de la 46a (21:15:30 del 11-10).
        self.escenario()
        futuro = [dict(filas[1], proxima=mc.PARTE)]
        colas = self.panel(timers_todos=futuro, timers=[])["colas"]
        self.assertEqual(colas["cola41"]["timers"], [{"unidad": "orden-renov-1122.timer", "proxima": mc.iso(mc.PARTE), "vencido": False}])
        self.reloj = mc.PARTE + timedelta(minutes=1)             # la hora ya pasó
        self.assertTrue(self.panel(timers_todos=futuro, timers=[])["colas"]["cola41"]["timers"][0]["vencido"])
        # Quien inyecta los timers de la matriz no consulta systemd: salen de esos, sin nombre de unidad.
        self.reloj = T
        self.cr.subprocess.run = staticmethod(lambda cmd, *a, **k: self.fail(f"no se consulta: {cmd}"))
        colas = self.panel(timers=[(mc.PARTE, filas[1]["orden"])])["colas"]
        self.assertEqual(colas["cola41"]["timers"], [{"unidad": "", "proxima": mc.iso(mc.PARTE), "vencido": False}])

    def test_todo_boton_que_el_panel_ofrece_funciona_y_ninguno_que_no_ofrece(self):
        self.escenario()
        self.reloj = datetime.fromisoformat("2026-10-11T19:40:00-03:00")
        ofrecidas = {c: x["acciones"] for c, x in self.panel(timers=[])["colas"].items()}
        foto = {p.name: p.read_bytes() for p in self.vivos.iterdir()}
        for cola in ofrecidas:
            for accion in self.cr.ACCIONES:
                with self.subTest(cola=cola, accion=accion):
                    shutil.rmtree(self.vivos)
                    self.vivos.mkdir()
                    for nombre, datos in foto.items():
                        (self.vivos / nombre).write_bytes(datos)
                    self.sesiones = {"cola46"}
                    self.assertEqual(self.accion(accion, cola)["ok"], accion in ofrecidas[cola])


class Pagina(Base):
    """Los botones de 🧵 Encargos, de punta a punta: lo que la página lanzaría (el argv de `argvAccion`, leído del JS)
    corre contra el `cola-run.py` real sobre fixtures, y lo que la página dibuja después sale del `--panel` real.
    En la Pi no hay motor de JavaScript: la parte de la página es un espejo en Python, atado al JS por su texto."""

    @classmethod
    def setUpClass(cls):
        import test_cockpit_paginas as pag
        pag.ResumenYUsoTests.setUpClass()               # los RE_ de la lista blanca, leídos de encargos.js
        cls.del_panel, cls.fase_panel = pag.CargaVsCapacidadTests.del_panel, pag.CargaVsCapacidadTests.fase_panel
        cls.tokens_js = staticmethod(pag.tokens_js)
        cls.js = (PI / "cockpit-encargos" / "encargos.js").read_text(encoding="utf-8")
        cls.css = (PI / "cockpit-encargos" / "encargos.css").read_text(encoding="utf-8")
        i, j = cls.js.index("// Encargo 46c: Reanudar, Pausar y Detener."), cls.js.index("// Encargo 34: la barra de uso.")
        cls.bloque = cls.js[i:j]
        cls.cola_valida = re.compile(re.search(r"const COLA_VALIDA = /(.+)/;", cls.js).group(1).replace("$", r"\Z"))
        # La ruta que la página le pasa a spawn: el cola-run.py de la carpeta de encargos del nodo (la `E` del propio script).
        cls.RUTA_JS = re.search(r'^const DIR = "([^"]+)";', cls.js, re.M).group(1) + "/cola-run.py"
        assert Path(cls.RUTA_JS) == mc.cargar().E / "cola-run.py", cls.RUTA_JS

    def setUp(self):
        super().setUp()
        # Por la línea de comandos no se inyecta el uso: sale de uso(), que acá lee la fixture a la hora de la foto.
        uso_real = self.cr.uso
        self.cr.uso = lambda cid, ruta=None, momento=None: uso_real(cid, ruta or self.uso_ruta, momento or self.reloj)
        self.spawns: list[list[str]] = []
        self.dialogos: list[str] = []
        self.leidas = 0
        self.resultado = None

    # ---- el espejo
    def argv(self, accion, cola, simular, autorizar=False):
        """argvAccion(): el arreglo literal del JS, con sus constantes. `autorizar` es la confirmación extra de la 50a."""
        self.assertIn('const argvAccion = (accion, cola, simular, autorizar) => ["python3", COLA_RUN, "--accion", accion, cola, '
                      '...(simular ? ["--simular"] : []), ...(autorizar ? ["--autorizar", cola] : [])];', self.bloque)
        self.assertIn("const COLA_RUN = `${DIR}/cola-run.py`", self.js)
        return ["python3", self.RUTA_JS, "--accion", accion, cola] + (["--simular"] if simular else []) + (["--autorizar", cola] if autorizar else [])

    def correr_accion(self, accion, cola, simular, autorizar=False):
        """correrAccion(): valida, lanza con cockpit.spawn (acá, el cola-run.py real) y entrega el JSON o lanza el error."""
        if accion not in ("reanudar", "pausar", "detener") or not isinstance(cola, str) or not self.cola_valida.search(cola):
            raise ValueError("nombre de cola inválido")
        argv = self.argv(accion, cola, simular, autorizar is True and accion == "reanudar" and not simular)
        return self.respuesta_cola(argv)

    def respuesta_cola(self, argv):
        """respuestaCola(): lo que contesta el proceso lanzado, o su error."""
        self.spawns.append(argv)
        rc, r, error = self.por_comandos(*argv[2:])
        if rc != 0:                                 # cockpit.spawn rechaza y `e.message` trae stderr
            raise ValueError(json.loads(error)["error"])
        if r.get("ok") is not True:
            raise ValueError(r.get("error") or "la acción no se hizo")
        return r

    def texto_confirmacion(self, accion, cola, sim=None):
        if accion == "reanudar":
            return "\n".join([f"¿Reanudar {cola} desde {self.fase_panel(sim['desde'])}?", "", "Carga proyectada:", *map(self.del_panel, sim["texto"]), "",
                              "Lanza la cola ahora y gasta cuota. Si usa un modelo con candado, la cola pide su ✅ por Telegram."])
        if accion == "pausar":
            return f"¿Pausar {cola}?\n\nTermina la fase en curso y no empieza la siguiente. Queda pausada por el usuario y sigue cuando la reanudes."
        return (f"Detener {cola} corta su sesión de inmediato: lo que lleva la fase en curso se pierde y esa fase se repite al reanudar.\n\n"
                "Para confirmar, escribe el nombre de la cola:")

    def desde_despacho(self, iso):
        """desdeDespacho(): «las 16:55» si fue hoy y «el 11-10 a las 16:55» si no."""
        try:
            t = datetime.fromisoformat(iso).astimezone()
        except (TypeError, ValueError):
            return "una hora sin datos"
        return f"las {t:%H:%M}" if t.date() == self.reloj.astimezone().date() else f"el {t:%d-%m} a las {t:%H:%M}"

    def motivo_despacho(self, x):
        return self.del_panel(x["motivo"]) if isinstance(x.get("motivo"), str) and x["motivo"].strip() else "sin motivo"

    @staticmethod
    def falta_autorizar(sim):
        return isinstance(sim.get("despacho"), dict) and sim["despacho"].get("estado") == "pausa" and sim["despacho"].get("autorizada") is not True

    def texto_autorizar(self, cola, x):
        return (f"El despacho está en pausa desde {self.desde_despacho(x.get('desde'))} — {self.motivo_despacho(x)}.\n\n"
                f"¿Autorizar {cola} a correr igual? Queda entre las autorizadas mientras dure esta pausa y parte ahora. Las demás colas siguen retenidas.")

    def accionar(self, accion, cola, confirma=True, escrito=None, autoriza=True):
        """accionar(): `confirma` es lo que contesta confirm() y `escrito`, lo que devuelve prompt() (None = cancelar).
        `autoriza` es lo que contesta el confirm() extra de Reanudar con el despacho en pausa (50a)."""
        self.resultado = None
        autorizar = False
        try:
            if accion == "reanudar":
                sim = self.correr_accion("reanudar", cola, True)
                self.dialogos.append(self.texto_confirmacion(accion, cola, sim))
                if not confirma:
                    return
                autorizar = self.falta_autorizar(sim)
                if autorizar:
                    self.dialogos.append(self.texto_autorizar(cola, sim["despacho"]))
                    if not autoriza:
                        return
            elif accion == "pausar":
                self.dialogos.append(self.texto_confirmacion(accion, cola))
                if not confirma:
                    return
            else:
                self.dialogos.append(self.texto_confirmacion(accion, cola))
                if escrito is None:
                    return
                if not (isinstance(escrito, str) and escrito == cola):
                    self.resultado = (True, "No se detuvo nada: lo escrito no es el nombre de la cola.")
                    return
            r = self.correr_accion(accion, cola, False, autorizar)
            self.resultado = (False, self.del_panel(r["mensaje"]))
        except ValueError as e:
            self.resultado = (True, self.del_panel(str(e)))
        finally:
            self.leidas += 1                        # leer(): la página relee todo después de actuar

    def colas_panel(self, **extra) -> dict:
        self.cr.SIMULANDO = True
        return self.cr.panel(**(dict(vivos_dir=self.vivos, uso_de=self.uso_de, momento=self.reloj, viva=lambda n: n in self.sesiones,
                                     manifiestos_dir=self.tmp, timers=[]) | extra))["colas"]

    def botones(self, colas: dict, cola, cuales) -> list[str]:
        """botonesCola(): de los botones que caben en ese lugar, los que el panel dice que valen."""
        info = colas.get(cola) if isinstance(cola, str) else None
        valido = isinstance(cola, str) and bool(self.cola_valida.search(cola))
        return [a for a in cuales if a in info["acciones"]] if valido and isinstance(info, dict) and isinstance(info.get("acciones"), list) else []

    def timers(self, info: dict, reanudable: bool) -> list[str]:
        return ["⏰ " + self.timer_panel(t["unidad"]) + ": " + (("vencido: usa Reanudar" if reanudable else "vencido") if t["vencido"] else "próxima …")
                + " · ver en ⏰ Programados" for t in info.get("timers", [])]

    def timer_panel(self, x):
        return "".join(p if i % 2 else self.del_panel(p) for i, p in enumerate(re.split(r"([.-])", x))) if isinstance(x, str) and x else "sin datos"

    # ---- las pruebas
    def test_el_espejo_es_el_js(self):
        for linea in (
                "const COLA_VALIDA = /^cola[0-9]{2}[a-z0-9]*$/;",
                'const ACCIONES_COLA = new Map([["reanudar", "Reanudar"], ["pausar", "Pausar"], ["detener", "Detener"]]);',
                'const nombreConfirmado = (escrito, cola) => typeof escrito === "string" && escrito === cola;',
                'if (!ACCIONES_COLA.has(accion) || typeof cola !== "string" || !COLA_VALIDA.test(cola)) throw new Error("nombre de cola inválido");',
                'return respuestaCola(cockpit.spawn(argvAccion(accion, cola, simular, autorizar === true && accion === "reanudar" && !simular), { err: "message" }));',
                "try { salida = await lanzado; }",
                'if (!r || r.ok !== true) throw new Error(r && typeof r.error === "string" ? r.error : "la acción no se hizo");',
                'if (accion === "reanudar") { const sim = await correrAccion("reanudar", cola, true); if (!confirm(textoConfirmacion(accion, cola, sim))) return; '
                'autorizar = faltaAutorizar(sim); if (autorizar && !confirm(textoAutorizar(cola, sim.despacho))) return; }',
                'else if (accion === "pausar") { if (!confirm(textoConfirmacion(accion, cola))) return; }',
                'else { const escrito = prompt(textoConfirmacion(accion, cola), ""); if (escrito === null) return; if (!nombreConfirmado(escrito, cola)) { '
                'resultadoAccion = { cola, mal: true, texto: "No se detuvo nada: lo escrito no es el nombre de la cola." }; return; } }',
                "const r = await correrAccion(accion, cola, false, autorizar);",
                "resultadoAccion = { cola, mal: false, texto: delPanel(r.mensaje) };",
                "} catch (e) { resultadoAccion = { cola, mal: true, texto: delPanel(e.message || String(e)) }; }",
                "finally { accionEnCurso = false; await leer().catch(() => pintar()); }",
                'const info = propio(d.colasPanel, cola) || {}, valido = typeof cola === "string" && COLA_VALIDA.test(cola);',
                "const ofrecidas = valido && Array.isArray(info.acciones) ? cuales.filter(a => info.acciones.includes(a)) : [];",
                'disabled: accionEnCurso, onclick: () => accionar(a, cola) }, ACCIONES_COLA.get(a))',
                't.vencido ? (reanudable ? "vencido: usa Reanudar" : "vencido") : `próxima ${cuando(t.proxima) || "sin datos"}`',
                'const timerPanel = x => (typeof x === "string" && x ? x.split(/([.-])/).map((p, i) => (i % 2 ? p : delPanel(p))).join("") : "sin datos");',
                '`¿Reanudar ${cola} desde ${fasePanel(sim.desde)}?`, "", "Carga proyectada:", ...(Array.isArray(sim.texto) ? sim.texto : []).map(delPanel), "",'):
            self.assertIn(linea, self.bloque, linea)
        for accion in ("pausar", "detener"):          # los textos de confirmación del espejo, letra por letra
            for trozo in self.texto_confirmacion(accion, "${cola}").split("\n\n"):
                self.assertIn(trozo, self.bloque.replace("\\n\\n", "\n\n"))
        # Dónde va cada botón: Pausar y Detener en la tarjeta de cada cola; Reanudar en «Detenidas o pausadas».
        self.assertIn('...cuerpo, botonesCola(m.cola, ["pausar", "detener"]), m.segmentos.length ? segmentos(m) : null);', self.js)
        self.assertIn('botonesCola(id, ["reanudar"]));', self.js)
        self.assertEqual(len(re.findall(r"botonesCola\(", self.js)), 3)
        # En accionar(), la acción de verdad está después de las tres confirmaciones y se llama una sola vez.
        cuerpo = self.bloque[self.bloque.index("async function accionar("):self.bloque.index("// La unidad de un timer")]
        self.assertEqual(cuerpo.count("correrAccion("), 2)
        self.assertLess(max(cuerpo.index("confirm(textoConfirmacion(accion, cola, sim))"), cuerpo.index("confirm(textoConfirmacion(accion, cola)))"),
                            cuerpo.index("nombreConfirmado(escrito, cola)"), cuerpo.index("confirm(textoAutorizar(cola, sim.despacho))")),
                        cuerpo.index("correrAccion(accion, cola, false, autorizar)"))
        self.assertEqual(self.resultado, None)
        # La cola que se lee de `colas` y el estado nuevo que la tarjeta sabe decir.
        self.assertIn('colas: x.colas && typeof x.colas === "object" ? x.colas : {}', self.js)
        self.assertIn('["pausada_por_usuario", "pausada por el usuario"]', self.js)
        self.assertIn('const porUsuario = m.estado === "pausada_por_usuario";', self.js)
        for clase in (".cola-acciones", ".cola-botones", "button.mini.peligro", ".cola-timer", ".accion-resultado"):
            self.assertIn(clase + " {", self.css)

    def test_los_unicos_comandos_son_el_argv_fijo_y_no_hay_systemctl_ni_shell(self):
        codigo = self.tokens_js(self.bloque, strings=True)
        self.assertEqual(re.findall(r"cockpit\.(\w+)\(([^)]{0,40})", codigo), [("spawn", "argvAccion(accion, cola, simular, autori"), ("jump", '"/sistema"')])
        self.assertEqual(len(re.findall(r"cockpit\.spawn\(", self.js)), 8)          # el octavo es el del despacho (50a), fuera de este bloque
        for prohibido in ("systemctl", "timer-pausar", "timer-reanudar", "timer-correr", "programado-accion", "nodo-servicio", "sudo"):
            self.assertNotIn(prohibido, self.js, prohibido)
        for prohibido in ('"sh"', '"bash"', "shell", "superuser", "innerHTML", "eval(", "localStorage", "fetch("):
            self.assertNotIn(prohibido, codigo, prohibido)
        # El argv no se arma con texto: son seis elementos fijos y la cola entra entera en uno solo.
        for cola in ("cola41", "cola22b"):
            self.assertEqual(self.argv("detener", cola, False), ["python3", self.RUTA_JS, "--accion", "detener", cola])
            self.assertEqual(self.argv("reanudar", cola, True)[-2:], [cola, "--simular"])
        # Un nombre que no es de cola no llega a spawn (y cola-run.py lo rechazaría igual).
        for hostil in HOSTILES + [None, 46]:
            with self.assertRaises(ValueError):
                self.correr_accion("detener", hostil, False)
            self.assertEqual(self.botones({hostil: {"acciones": ["reanudar", "pausar", "detener"]}} if isinstance(hostil, str) else {}, hostil, ["detener"]), [])
        with self.assertRaises(ValueError):
            self.correr_accion("borrar", "cola41", False)
        self.assertEqual(self.spawns, [])
        self.assertEqual(self.cola_valida.pattern, "^" + self.cr.RE_COLA.pattern + r"\Z")       # la misma regla en la página y en cola-run.py

    def test_reanudar_de_punta_a_punta(self):
        ruta = self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        colas = self.colas_panel()
        self.assertEqual((self.botones(colas, "cola41", ["reanudar"]), self.botones(colas, "cola41", ["pausar", "detener"])), (["reanudar"], []))
        antes = self.arbol()
        # Sin confirmar: se pidió la simulación, se mostró la carga proyectada y no se lanzó ni se escribió nada.
        self.accionar("reanudar", "cola41", confirma=False)
        self.assertEqual(self.spawns, [["python3", self.RUTA_JS, "--accion", "reanudar", "cola41", "--simular"]])
        self.assertEqual((self.lanzados, self.resultado, self.arbol(), self.leidas), ([], None, antes, 1))
        self.assertEqual(self.dialogos[0].split("\n"), [
            "¿Reanudar cola41 desde 41:rev3?", "", "Carga proyectada:",
            "Claude (Cami): +17 % 5 h (entre 17 y 17) · +2 % sem (entre 2 y 2) · holgura con esta carga: 5 h 26 % · sem −8 %", "",
            "Lanza la cola ahora y gasta cuota. Si usa un modelo con candado, la cola pide su ✅ por Telegram."])
        # Confirmando: la simulación y después la acción, una vez; lanzó la línea `relanzar` y la página releyó.
        self.accionar("reanudar", "cola41")
        self.assertEqual(self.spawns[1:], [["python3", self.RUTA_JS, "--accion", "reanudar", "cola41", "--simular"],
                                           ["python3", self.RUTA_JS, "--accion", "reanudar", "cola41"]])
        self.assertEqual(self.lanzados, [self.cr.argv_relanzar("cola41", ruta, "41:rev3")])
        self.assertEqual(self.resultado, (False, "cola41 se lanzó desde la etapa 41, fase rev3. Su sesión está viva; el estado cambia en unos segundos."))
        self.assertEqual(self.leidas, 2)
        # Después de actuar, el panel ya no ofrece Reanudar; un segundo clic sobre una página vieja se rechaza en cola-run.py.
        self.assertEqual(self.botones(self.colas_panel(), "cola41", ["reanudar"]), [])
        self.accionar("reanudar", "cola41")
        self.assertEqual((len(self.lanzados), self.resultado), (1, (True, "no se puede reanudar cola41: su sesión ya está viva")))
        self.assertEqual([f["resultado"] for f in self.registro()], ["hecho"])       # la simulación rechazada no deja línea

    def test_pausar_de_punta_a_punta(self):
        self.manifiesto(texto=mc.MANIFIESTO_46)
        self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        self.reloj = datetime.fromisoformat("2026-10-11T19:40:00-03:00")
        colas = self.colas_panel()
        self.assertEqual((self.botones(colas, "cola46", ["pausar", "detener"]), self.botones(colas, "cola46", ["reanudar"])), (["pausar", "detener"], []))
        antes = self.arbol()
        self.accionar("pausar", "cola46", confirma=False)
        self.assertEqual((self.spawns, self.resultado, self.arbol()), ([], None, antes))
        self.accionar("pausar", "cola46")
        self.assertEqual(self.spawns, [["python3", self.RUTA_JS, "--accion", "pausar", "cola46"]])
        self.assertEqual(self.resultado, (False, "Pausa pedida para cola46: termina la fase en curso y no empieza la siguiente."))
        self.assertTrue(self.marca("cola46").is_file())
        despues = self.colas_panel()["cola46"]
        self.assertEqual((despues["pausa_pedida"], despues["acciones"]), (True, ["pausar", "detener"]))
        self.assertIn('info.pausa_pedida ? el("span", { class: "chip ojo" }, "pausa pedida: se detiene al terminar la fase en curso") : null,', self.bloque)
        self.accionar("pausar", "cola46")
        self.assertEqual(self.resultado, (False, "cola46 ya tenía una pausa pedida: se detiene cuando termine la fase en curso."))

    def test_detener_de_punta_a_punta_y_sin_el_nombre_exacto_no_ejecuta_nada(self):
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46)
        v = self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        self.reloj = datetime.fromisoformat("2026-10-11T19:40:00-03:00")
        self.assertEqual(self.botones(self.colas_panel(), "cola46", ["pausar", "detener"]), ["pausar", "detener"])
        antes = self.arbol()
        for escrito in ("", "cola4", "cola46 ", " cola46", "Cola46", "COLA46", "cola46\n", "cola461", "=cola46", "sí", "detener", 46, True):
            with self.subTest(escrito=escrito):
                self.accionar("detener", "cola46", escrito=escrito)
                self.assertEqual(self.resultado, (True, "No se detuvo nada: lo escrito no es el nombre de la cola."))
        self.accionar("detener", "cola46", escrito=None)         # Cancelar
        self.assertEqual(self.resultado, None)
        self.assertEqual((self.spawns, self.pedidos, self.sesiones, self.arbol(), self.vivo("cola46")), ([], [], {"cola46"}, antes, v))
        # Con el nombre exacto: corta, deja detenida con el --desde de la fase cortada y la página relee.
        self.accionar("detener", "cola46", escrito="cola46")
        self.assertEqual(self.spawns, [["python3", self.RUTA_JS, "--accion", "detener", "cola46"]])
        self.assertEqual(self.resultado, (False, "Se cortó la sesión de cola46. Quedó detenida; se reanuda desde la etapa 46a, fase autor."))
        self.assertEqual((self.sesiones, self.vivo("cola46")["estado"], self.vivo("cola46")["reanuda_desde"]), (set(), "detenida", "46a:autor"))
        self.assertEqual(self.pedidos[1], ["kill-session", "-t", "=cola46"])
        colas = self.colas_panel()
        self.assertEqual((self.botones(colas, "cola46", ["pausar", "detener"]), self.botones(colas, "cola46", ["reanudar"])), ([], ["reanudar"]))
        # Y Reanudar, desde «Detenidas o pausadas», retoma en esa fase.
        self.accionar("reanudar", "cola46")
        self.assertEqual(self.lanzados, [self.cr.argv_relanzar("cola46", ruta, "46a:autor")])
        self.assertIn("¿Reanudar cola46 desde 46a:autor?", self.dialogos[-1])

    def test_los_timers_se_ven_en_modo_solo_lectura(self):
        for man in ("cola-41.toml",):
            self.manifiesto(man)
        self.manifiesto(texto=mc.MANIFIESTO_46.replace('nombre = "cola46"', 'nombre = "cola50"'), destino="cola-50.toml")
        self.manifiesto(texto=mc.MANIFIESTO_46.replace('nombre = "cola46"', 'nombre = "cola36"'), destino="cola-36.toml")
        self.poner("vivo-cola41.json")
        self.poner("vivo-cola50-retenida.json")
        self.poner("vivo-cola47-detenida.json", nombre="cola36")
        colas = self.colas_panel(timers=None)              # los timers reales del 12-10 (la salida de systemctl guardada)
        self.assertEqual(self.timers(colas["cola41"], bool(self.botones(colas, "cola41", ["reanudar"]))),
                         ["⏰ orden-renov-1122.timer: vencido: usa Reanudar · ver en ⏰ Programados"])
        self.assertEqual(self.timers(colas["cola50"], bool(self.botones(colas, "cola50", ["reanudar"]))),
                         ["⏰ orden-renov-1122.timer: vencido · ver en ⏰ Programados"])     # sin botón Reanudar no se le manda a usarlo
        self.assertEqual(self.timers(colas["cola36"], False), ["⏰ cola36-reanudar.timer: vencido · ver en ⏰ Programados"])
        self.assertEqual(self.del_panel("cola36-reanudar.timer"), "«oculto»")       # entera no pasa la lista blanca: por eso va por partes
        self.assertEqual(self.timer_panel("sk-proj-Abc123Def456Ghi789Jkl012.timer"), "sk-proj-«oculto».timer")
        futuro = [dict(self.cr.timers_usuario(self.proceso)[1], proxima=mc.PARTE)]
        self.assertEqual(self.timers(self.colas_panel(timers_todos=futuro)["cola41"], True), ["⏰ orden-renov-1122.timer: próxima … · ver en ⏰ Programados"])
        # El único botón del timer abre 🍇 Raspberry Pi, donde está ⏰ Programados. Nada de la página lo acciona.
        self.assertIn('el("button", { class: "mini", title: "Abre 🍇 Raspberry Pi; los timers se accionan en su pestaña ⏰ Programados", '
                      'onclick: () => cockpit.jump("/sistema") }, "ver en ⏰ Programados")', self.bloque)
        self.assertIn("...timersCola(info, ofrecidas.includes(\"reanudar\"))", self.bloque)
        self.assertEqual(set(colas["cola41"]["timers"][0]), {"unidad", "proxima", "vencido"})       # el ExecStart no se publica

    def test_todo_texto_que_viene_de_cola_run_pasa_entero_por_la_lista_blanca(self):
        for man in ("cola-41.toml", "cola-42.toml", "cola-43.toml", "cola-44.toml"):
            self.manifiesto(man)
        self.manifiesto(texto=mc.MANIFIESTO_46)
        textos = []

        def junta(r):
            textos.extend([r.get("mensaje"), r.get("error"), *(r.get("texto") or [])])
            return r
        for fixture, cambios, viva, acciones in (
                ("vivo-cola41.json", {}, False, ("reanudar", "pausar", "detener")),
                ("vivo-cola41.json", {}, True, ("reanudar", "detener")),
                ("vivo-cola41.json", {"motivo_pausa": "no hay dato de cuota semanal de Codex (uso.json)"}, False, ("reanudar",)),
                ("vivo-cola41.json", {"estado": "detenida", "reanuda_desde": None}, False, ("reanudar",)),
                ("vivo-cola41.json", {"estado": "caída"}, False, ("reanudar",)),
                ("vivo-cola41.json", {"reanuda_desde": "99:rev1"}, False, ("reanudar",)),
                ("vivo-cola42.json", {}, False, ("reanudar",)),
                ("vivo-cola43r.json", {}, False, ("reanudar",)),
                ("vivo-cola44-esperando.json", {}, False, ("reanudar", "detener")),
                ("vivo-cola46-corriendo.json", {}, True, ("pausar", "pausar", "detener")),
                ("vivo-cola46-corriendo.json", {}, False, ("reanudar", "pausar", "detener")),
                ("vivo-cola46-corriendo.json", {"estado": "pruebas finales", "fase": None}, True, ("pausar", "detener")),
                ("vivo-cola46-corriendo.json", {"estado": "esperando autorización"}, True, ("detener",))):
            for simular in (True, False):
                self.sesiones.clear()
                v = self.poner(fixture, **cambios)
                if viva:
                    self.sesiones.add(v["nombre"])
                for accion in acciones:
                    junta(self.accion(accion, v["nombre"], simular))
        junta(self.accion("reanudar", "cola99"))
        junta(self.accion("reanudar", "cola4; rm"))
        self.corta = False
        self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        junta(self.accion("detener", "cola46"))
        junta(self.accion("reanudar", "cola41", lanzar=lambda argv: 1))
        textos = sorted({t for t in textos if t})
        self.assertGreater(len(textos), 30)
        for t in textos:
            self.assertEqual(self.del_panel(t), t)
        # Lo mismo las razones que el panel publica en `no_reanuda`, y ninguno usa los términos que la página no usa.
        for info in self.colas_panel().values():
            self.assertEqual(self.del_panel(info["no_reanuda"] or "x"), info["no_reanuda"] or "x")
        visibles = "\n".join(textos + re.findall(r'"([^"\n]{12,})"', self.bloque) + re.findall(r"`([^`\n]{12,})`", self.bloque))
        for viejo in ("pronóstico", "próxima fase", "costo", "margen", "alcanza", "Total", "regla de"):
            self.assertNotIn(viejo, visibles.replace("sin margen para", ""), viejo)


class TmuxDeVerdad(unittest.TestCase):
    """El binario tmux, en un servidor PROPIO (`-L`: otro socket) y con nombres que no existen en el nodo. Lo que se
    comprueba es lo que un doble no puede: que «=» de verdad exige el nombre entero y que kill-session corta."""

    def setUp(self):
        if not shutil.which("tmux"):
            self.skipTest("no hay tmux")
        self.tmp = Path(tempfile.mkdtemp(prefix="acciones-tmux-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tmux = ("tmux", "-L", f"acciones-{os.getpid()}-{secrets.token_hex(4)}", "-f", "/dev/null")
        self.addCleanup(lambda: subprocess.run([*self.tmux, "kill-server"], capture_output=True))
        self.assertEqual(os.environ["TMUX_TMPDIR"], _ENTORNO["tmp"])           # ni el socket por defecto es el del usuario
        self.cr = cr = mc.cargar()
        self.avisos = mc.preparar(cr, self.tmp, lambda: T)
        real = subprocess.run

        def run(cmd, *a, **k):
            if tuple(cmd[: len(self.tmux)]) != self.tmux:
                raise AssertionError(f"solo el tmux propio: {cmd}")
            return real(cmd, *a, **k)
        cr.subprocess = type("SoloTmuxPropio", (), {"run": staticmethod(run), "SubprocessError": subprocess.SubprocessError,
                                                   "TimeoutExpired": subprocess.TimeoutExpired})
        self.lanzados = []
        for nombre in ("cola91", "cola91x"):
            texto = re.sub(r"^pruebas = .*$", "pruebas = []", (MANIFIESTOS / "cola-41.toml").read_text(encoding="utf-8"), flags=re.M)
            (self.tmp / f"cola-{nombre[4:]}.toml").write_text(texto.replace('nombre = "cola41"', f'nombre = "{nombre}"'), encoding="utf-8")

    def sesiones(self) -> list[str]:
        p = subprocess.run([*self.tmux, "ls", "-F", "#{session_name}"], capture_output=True, text=True)
        return sorted(p.stdout.split())

    def nueva(self, nombre: str) -> None:
        subprocess.run([*self.tmux, "new-session", "-d", "-s", nombre, "sleep", "600"], check=True, capture_output=True)

    def lanzar(self, argv):
        """En vez de la cola, un `sleep` con el mismo nombre de sesión, en el servidor propio."""
        self.lanzados.append(list(argv))
        return subprocess.run([*self.tmux, *argv[1:5], "sleep", "600"], capture_output=True).returncode

    def accion(self, accion, cola, **extra):
        return self.cr.accion_cola(accion, cola, vivos_dir=self.tmp / "vivo", manifiestos_dir=self.tmp, tmux=self.tmux, lanzar=self.lanzar,
                                   estado_md=self.tmp / "COLA-ESTADO.md", momento=T, **extra)

    def poner(self, nombre: str, **cambios) -> None:
        v = json.loads((FIX / "vivo-cola41.json").read_text(encoding="utf-8")) | {"nombre": nombre} | cambios
        (self.tmp / "vivo" / f"{nombre}.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")

    def test_reanudar_pausar_y_detener_contra_un_tmux_propio(self):
        try:
            self.nueva("cola91x")
        except subprocess.CalledProcessError:
            self.skipTest("el sandbox no permite crear un servidor tmux temporal")
        # Sin «=», tmux calza por prefijo: `cola91` existiría. Por eso todo destino lleva «=».
        self.assertEqual(subprocess.run([*self.tmux, "has-session", "-t", "cola91"], capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run([*self.tmux, "has-session", "-t", "=cola91"], capture_output=True).returncode, 1)
        self.poner("cola91")
        self.assertIn("no hay nada que detener", self.accion("detener", "cola91")["error"])
        self.assertEqual(self.sesiones(), ["cola91x"])
        r = self.accion("reanudar", "cola91")                  # la sesión de la otra no la frena
        self.assertEqual((r["ok"], r["sesion"]), (True, True))
        self.assertEqual(self.sesiones(), ["cola91", "cola91x"])
        self.assertEqual(self.lanzados[0][:6] + self.lanzados[0][8:], ["tmux", "new-session", "-d", "-s", "cola91", "python3", "--desde", "41:rev3"])
        self.assertIn("su sesión ya está viva", self.accion("reanudar", "cola91")["error"])
        self.assertEqual(len(self.lanzados), 1)
        self.poner("cola91", estado="corriendo", etapa="41", fase="rev3", reanuda_desde=None)
        r = self.accion("pausar", "cola91")
        self.assertEqual((r["ok"], r["sesion"], (self.tmp / "vivo" / "cola91.pausar").is_file()), (True, True, True))
        r = self.accion("detener", "cola91")
        self.assertEqual((r["ok"], r["sesion"], r["estado"], r["desde"]), (True, False, "detenida", "41:rev3"))
        self.assertEqual(self.sesiones(), ["cola91x"])          # cortó la suya y solo la suya
        self.assertFalse((self.tmp / "vivo" / "cola91.pausar").exists())
        self.assertEqual(self.avisos, [])


if __name__ == "__main__":
    unittest.main()
