#!/usr/bin/env python3
"""Pruebas del rediseño visual de Cockpit, plan B (encargo 18, documento 26).

    python3 test_cockpit_paginas.py

Leen los archivos de las seis páginas (`cockpit-sistema`, `-nodo`, `-bots`, `-cuentas`,
`-noticias`, `-luces`) y del paquete común (`cockpit-comun`). En la Pi no hay motor de
JavaScript: nada de acá EJECUTA las páginas. Lo que se comprueba es cómo están armadas
(qué cargan, qué declaran, qué leen) y, para 🏠 Inicio, un ESPEJO en Python del modelo
de `inicio.js`, corrido con datos de la forma real y atado al JS por pruebas de texto.
"""
import json
import copy
import contextlib
import io
import math
import os
import re
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

PI = Path(__file__).resolve().parent
sys.path.insert(0, str(PI))
import test_cuentas_uso as previas  # noqa: E402  (tokenizador, reglas_css y la salida real de bots-info)

tokens_js, reglas_css, declarados_arriba = previas.tokens_js, previas.reglas_css, previas.declarados_arriba
tramo = previas.tramo

# ---- Encargo 27c: ninguna prueba escribe en el nodo real (avisos*.jsonl, bandeja, bitácora, historial). ----
# Las pruebas que cargan cola-run.py / registro_avisos.py / paginas-pendientes.py reciben las rutas de
# avisos, bandeja, bitácora e historial apuntadas a una carpeta temporal DESDE LA CARGA; cada prueba
# puede cambiarlas después, pero una que se olvide ya no cae en /opt/nodo/datos (que sale a Telegram).
AVISOS_REALES = (Path("/opt/nodo/datos/avisos.jsonl"), Path("/opt/nodo/datos/avisos-salida.jsonl"))
_CARGAR_ORIGINAL = previas._cargar
_NODO_FALSO = None


def _huella(ruta):
    try:
        e = ruta.stat()
        return (e.st_size, e.st_mtime_ns)
    except OSError:
        return None


_HUELLA_INICIAL = {r: _huella(r) for r in AVISOS_REALES}


def _cargar_aislado(nombre, ruta):
    global _NODO_FALSO
    import tempfile
    if _NODO_FALSO is None:
        _NODO_FALSO = Path(tempfile.mkdtemp(prefix="nodo-falso-"))
    m = _CARGAR_ORIGINAL(nombre, ruta)
    archivo, falso = Path(ruta).name, _NODO_FALSO
    if archivo == "registro_avisos.py":
        _cargar_aislado_ra(m)
    elif archivo == "cola-run.py":
        _historial_git_aislado(Path(ruta).with_name("versiones.py"))
        m.L = m.E = falso
        m.ESTADO, m.HISTORIAL = falso / "COLA-ESTADO.md", falso / "historial.jsonl"
        m._RA_MOD = _CARGAR_ORIGINAL(f"{nombre}_registro", Path(ruta).with_name("registro_avisos.py"))
        _cargar_aislado_ra(m._RA_MOD)
    elif archivo == "paginas-pendientes.py" and hasattr(m, "L"):
        m.L = falso
        m._RA_MOD = _CARGAR_ORIGINAL(f"{nombre}_registro", Path(ruta).with_name("registro_avisos.py"))
        _cargar_aislado_ra(m._RA_MOD)
    return m


def _historial_git_aislado(versiones):
    """Encargo 48, vuelta 2: una prueba que corre main() de cola-run.py saca fotos con versiones.py, y
    sin esto iban al historial real (/opt/nodo/datos/git/11-Pi5.git, «antes de cola9»). Desde la primera
    carga, el historial y el árbol que ve la suite son temporales; cada prueba puede cambiarlos después."""
    repo, arbol = _NODO_FALSO / "git" / "11-Pi5.git", _NODO_FALSO / "arbol"
    if os.environ.get("VERSIONES_REPO") != str(repo):
        arbol.mkdir(parents=True, exist_ok=True)
        os.environ["VERSIONES_REPO"], os.environ["VERSIONES_ARBOL"] = str(repo), str(arbol)
        _CARGAR_ORIGINAL("versiones_aislado", versiones).abrir(str(repo), str(arbol)).init()


def _cargar_aislado_ra(m):
    falso = _NODO_FALSO
    m.REGISTRO, m.BANDEJA, m.PENDIENTE_AVISOS = falso / "avisos.jsonl", falso / "avisos-salida.jsonl", falso / "avisos-registro-pendiente.jsonl"
    m.BANDEJA_ESTADO, m.BANDEJA_CERROJO = falso / "avisos-bandeja.json", falso / ".avisos-salida.lock"


previas._cargar = _cargar_aislado


def tearDownModule():
    import shutil
    previas._cargar = _CARGAR_ORIGINAL
    if _NODO_FALSO is not None:
        shutil.rmtree(_NODO_FALSO, True)
    cambiados = {str(r): (_HUELLA_INICIAL[r], _huella(r)) for r in AVISOS_REALES if _huella(r) != _HUELLA_INICIAL[r]}
    if cambiados:
        raise AssertionError(f"la suite escribió en los avisos reales del nodo (antes, después): {cambiados}")


COMUN = PI / "cockpit-comun"
# Paquete → (order, etiqueta del menú). El orden es el del documento 26.
MENU = {"sistema": (0, "🍇 Raspberry Pi"), "nodo": (1, "👾 IA Agents"), "bots": (2, "🤖 Asistentes"),
        "cuentas": (3, "💳 Cuentas"), "encargos": (4, "🏭 AI Ops"), "noticias": (5, "📰 Noticias"),
        "luces": (6, "🌈 Luces"), "memoria": (3, "🧠 Memoria")}
PAGINAS = {nombre: PI / f"cockpit-{nombre}" for nombre in MENU}


def leer(ruta):
    return Path(ruta).read_text(encoding="utf-8")


def pestanas_encargos(html):
    """Encargo 85a: pestañas superiores de AI Ops, en orden, como (data-p, texto)."""
    return re.findall(r'<button class="consola-pestana" role="tab" data-p="(\w+)" data-term="[^"]+">([^<]+)', html)

def riel_encargos(html):
    """Compatibilidad de pruebas históricas: la estructura actual se consulta con pestanas_encargos()."""
    return pestanas_encargos(html)


def hojas(carpeta):
    return sorted(carpeta.glob("*.css"))


def guiones(carpeta):
    return sorted(carpeta.glob("*.js"))      # sin vendor/: xterm no es nuestro


def variables_css(css):
    """Nombres de las variables que una hoja DEFINE (`--x: valor`), no las que usa."""
    return set(re.findall(r"(--[\w-]+)\s*:", re.sub(r"/\*.*?\*/", "", css, flags=re.S)))


# Los valores que estaban copiados en las cinco hojas antes del encargo 18.
TOKENS = {
    "claro": {"--fondo": "#f5f5f4", "--tarjeta": "#ffffff", "--borde": "#e2e2df", "--texto": "#1c1c1a",
              "--tenue": "#6b6b66", "--acento": "#2f6fdb", "--acento-texto": "#ffffff", "--ok": "#2e9b5a",
              "--ok-fondo": "#e6f4ec", "--mal": "#c93b3b", "--mal-fondo": "#fbe9e9", "--ojo": "#a86a00",
              "--ojo-fondo": "#fdf3df", "--chip": "#efefec", "--terminal": "#1b1b1a",
              "--terminal-texto": "#e8e6df"},
    "oscuro": {"--fondo": "#151514", "--tarjeta": "#1f1f1e", "--borde": "#33332f", "--texto": "#ecebe6",
               "--tenue": "#9d9c95", "--acento": "#5b8ff0", "--acento-texto": "#0d0d0c", "--ok": "#4cc27c",
               "--ok-fondo": "#173123", "--mal": "#ec6a6a", "--mal-fondo": "#3a1c1c", "--ojo": "#e5a93a",
               "--ojo-fondo": "#3a2c12", "--chip": "#2a2a28", "--terminal": "#0d0d0c",
               "--terminal-texto": "#e8e6df"},
}


class GuardianDelNodoTests(unittest.TestCase):
    """Encargo 27c: la suite no escribe en los avisos reales del nodo. Esta prueba mira lo ocurrido
    hasta su turno; la revisión de toda la corrida está en tearDownModule."""

    def test_los_avisos_reales_no_cambiaron_y_las_cargas_estan_aisladas(self):
        self.assertEqual({r: _huella(r) for r in AVISOS_REALES}, _HUELLA_INICIAL)
        cr = previas._cargar("cola_run_guardian", ENCARGOS_DIR / "cola-run.py")
        for ruta in (cr.L, cr.E, cr.ESTADO, cr.HISTORIAL, cr._RA_MOD.REGISTRO, cr._RA_MOD.BANDEJA, cr._RA_MOD.BANDEJA_ESTADO,
                     cr._RA_MOD.PENDIENTE_AVISOS, cr._RA_MOD.BANDEJA_CERROJO):
            self.assertTrue(str(ruta).startswith(str(_NODO_FALSO)), ruta)
        cr.SIMULANDO = False
        for ruta in (cr._RA_MOD.BANDEJA_ESTADO, cr._RA_MOD.BANDEJA, cr._RA_MOD.REGISTRO):    # la carpeta falsa es de toda la corrida: no dejar la bandeja «activa»
            self.addCleanup(ruta.unlink, missing_ok=True)
        cr._RA_MOD.BANDEJA_ESTADO.write_text(json.dumps({"version": cr._RA_MOD.BANDEJA_VERSION, "ok": True,
                                                         "ultimo_ciclo": __import__("time").time()}), encoding="utf-8")
        cr.avisar_texto("✅ Cola de prueba DESPLEGADA.")
        self.assertTrue(cr._RA_MOD.BANDEJA.exists())
        self.assertEqual({r: _huella(r) for r in AVISOS_REALES}, _HUELLA_INICIAL)


    def test_las_fotos_de_cola_run_no_van_al_historial_git_real(self):
        """Encargo 48, vuelta 2: las pruebas que corren main() sacaban fotos del árbol real en
        /opt/nodo/datos/git/11-Pi5.git. La carga aislada deja el historial en la carpeta falsa."""
        cr = previas._cargar("cola_run_guardian_git", ENCARGOS_DIR / "cola-run.py")
        repo = cr._vers().abrir()
        self.assertNotEqual(cr._vers().REPO_POR_DEFECTO, repo.git_dir)
        for ruta in (repo.git_dir, repo.arbol):
            self.assertTrue(str(ruta).startswith(str(_NODO_FALSO)), ruta)
        real = cr._vers().REPO_POR_DEFECTO
        cabeza = lambda: subprocess.run(["git", f"--git-dir={real}", "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        antes = cabeza()
        cr.SIMULANDO, cr.MANIFIESTO = False, {"nombre": "cola-guardian"}
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            (repo.arbol / "guardian.txt").write_text("x\n", encoding="utf-8")
            self.addCleanup((repo.arbol / "guardian.txt").unlink, missing_ok=True)
            self.assertEqual(cr.git_foto("foto del guardián"), repo.head())            # la foto se sacó, y en el temporal
        self.assertEqual(salida.getvalue(), "")                                        # sin «⚠️ historial git»
        self.assertEqual(repo.git("log", "-1", "--format=%s").stdout.decode().strip(), "foto del guardián")
        self.assertEqual(cabeza(), antes)


class MenuTests(unittest.TestCase):
    def test_orden_del_menu_y_todo_en_tools(self):
        for nombre, (orden, etiqueta) in MENU.items():
            m = json.loads(leer(PAGINAS[nombre] / "manifest.json"))
            with self.subTest(nombre):
                self.assertEqual(m["name"], nombre)
                # Diego decidió que nada sube a `menu`: todo queda en «Herramientas».
                self.assertNotIn("menu", m)
                self.assertNotIn("dashboard", m)
                self.assertEqual(list(m["tools"]), ["index"])
                self.assertEqual((m["tools"]["index"]["order"], m["tools"]["index"]["label"]), (orden, etiqueta))
        self.assertEqual(sorted(json.loads(leer(PAGINAS[n] / "manifest.json"))["tools"]["index"]["order"]
                                for n in MENU), [0, 1, 2, 3, 3, 4, 5, 6])
        # 🧠 comparte el 3 con 💳 hasta el reorden de la Fase 2b (espera decisión del usuario).
        # El paquete común no agrega ninguna entrada al menú.
        comun = json.loads(leer(COMUN / "manifest.json"))
        self.assertEqual(comun["name"], "comun")
        for seccion in ("menu", "tools", "dashboard"):
            self.assertNotIn(seccion, comun)
        # Lo que se instala del común: nada más que esto (sin __pycache__ ni copias).
        self.assertEqual(sorted(f.name for f in COMUN.iterdir()),
                         ["barra.js", "base.css", "comun.js", "dom.js", "manifest.json", "tema.js", "tokens.css"])


class ComunTests(unittest.TestCase):
    def test_los_tokens_viven_en_un_solo_lugar_con_los_mismos_valores(self):
        reglas = reglas_css(leer(COMUN / "tokens.css"))
        self.assertEqual([(m, s) for m, s, _ in reglas], [("", ":root"), ("", ':root[data-theme="dark"]')])
        self.assertEqual(reglas[0][2], TOKENS["claro"])
        self.assertEqual(reglas[1][2], TOKENS["oscuro"])
        comunes = set(TOKENS["claro"])
        # Ninguna hoja de página (ni base.css) vuelve a definir un color del tema.
        vistas = 0
        for hoja in [COMUN / "base.css", *(h for d in PAGINAS.values() for h in hojas(d))]:
            vistas += 1
            with self.subTest(hoja.name):
                self.assertEqual(variables_css(leer(hoja)) & comunes, set())
        self.assertEqual(vistas, 9)       # base.css y una hoja por página
        # La prueba mide: una hoja que redefine un token la detecta, y lo que es de una
        # sola página (la tira de LEDs, la paleta de los gráficos) no es un token común.
        self.assertEqual(variables_css(":root { --fondo: #000; --tira: #111; }") & comunes, {"--fondo"})
        self.assertEqual(variables_css(".x { color: var(--fondo); }"), set())
        propias = {v for d in PAGINAS.values() for h in hojas(d) for v in variables_css(leer(h))}
        self.assertLessEqual({"--tira", "--led-apagado", "--apagado", "--term-fondo", "--s1", "--sin"}, propias)
        # Las seis cargan tokens.css antes que base.css y que su hoja.
        for nombre, carpeta in PAGINAS.items():
            enlaces = re.findall(r'<link href="([^"]+)" rel="stylesheet" />', leer(carpeta / "index.html"))
            propios = [e for e in enlaces if not e.startswith("vendor/")]
            self.assertEqual(propios, ["../comun/tokens.css", "../comun/base.css", f"{nombre}.css"], nombre)

    def test_aplicar_tema_y_el_estan_una_sola_vez(self):
        self.assertEqual(leer(COMUN / "tema.js").count("function aplicarTema()"), 1)
        self.assertEqual(leer(COMUN / "dom.js").count("function el(tag, attrs = {}, ...hijos)"), 1)
        vistos = 0
        for carpeta in [*PAGINAS.values(), COMUN]:
            for js in guiones(carpeta):
                if js.parent == COMUN and js.name in ("tema.js", "dom.js"):
                    continue
                vistos += 1
                codigo = leer(js)
                with self.subTest(js.name):
                    self.assertFalse({"aplicarTema", "el"} & declarados_arriba(codigo))
                    self.assertNotIn("function aplicarTema", codigo)
                    self.assertNotIn("function el(", codigo)
                    # Nadie más mira el tema de Cockpit ni pone data-theme. Encargo 84a: el selector de tema de la
                    # consola escribe la preferencia de Cockpit (la misma que su menú) y quien la aplica es tema.js.
                    if js.name == "encargos.js":
                        self.assertEqual(codigo.count("shell:style"), 1)
                        self.assertIn('const ESTILO = "shell:style"', codigo)
                        self.assertEqual(re.findall(r"localStorage\.(\w+)\(([^,)]*)", codigo), [("getItem", "ESTILO"), ("setItem", "ESTILO")])
                        self.assertIn("try { localStorage.setItem(ESTILO, t[0]); } catch (e) { /* sin storage: queda como está */ } aplicarTema(); pintarTema(); }", codigo)
                    else:
                        self.assertNotIn("shell:style", codigo)
                    self.assertNotIn("dataset.theme", codigo)
                    self.assertNotIn("prefers-color-scheme", codigo)
        self.assertEqual(vistos, 17)      # suma glosario.js (85a), además de los archivos de la consola 84/84b, y modelo.js y proyectos.js (99)

    def test_las_seis_cargan_el_comun_y_ninguna_el_paquete_bots(self):
        for nombre, carpeta in PAGINAS.items():
            html = leer(carpeta / "index.html")
            scripts = re.findall(r'<script src="([^"]+)"', html)
            cabeza, cuerpo = html.split("</head>")
            with self.subTest(nombre):
                # El tema se aplica en el <head>, antes de pintar; el() y la barra, antes
                # que el script de la página, que los usa.
                self.assertIn('<script src="../comun/tema.js"></script>', cabeza)
                self.assertNotIn("../comun/tema.js", cuerpo)
                del_cuerpo = re.findall(r'<script src="([^"]+)"', cuerpo)
                self.assertEqual(del_cuerpo[:2], ["../comun/dom.js", "../comun/barra.js"])
                self.assertEqual(del_cuerpo[-1], f"{nombre}.js")
                self.assertNotIn("../bots/", html)
                self.assertNotIn("../nexus/", html)
                # Todo lo que carga existe con la disposición instalada
                # (~/.local/share/cockpit/<paquete>/): `../comun/x` es pi/cockpit-comun/x.
                for ref in scripts + re.findall(r'<link href="([^"]+)"', html):
                    if ref.startswith("../base1/"):
                        continue
                    destino = COMUN / ref[len("../comun/"):] if ref.startswith("../comun/") else carpeta / ref
                    self.assertTrue(destino.is_file(), ref)
        # comun.js (propuestas, cuentas, chips, barras) lo cargan las tres que lo usan, y
        # sólo desde `comun`. El paquete `bots` ya no tiene nada común: no es dependencia.
        for nombre in ("nodo", "bots", "cuentas"):
            self.assertIn('<script src="../comun/comun.js"></script>', leer(PAGINAS[nombre] / "index.html"))
        self.assertEqual(sorted(f.name for f in PAGINAS["bots"].iterdir()),
                         ["bots.css", "bots.js", "index.html", "manifest.json"])
        self.assertEqual(sorted(PI.glob("cockpit-*/comun.*")), [COMUN / "comun.js"])
        # 🍇, 📰 y 🌈 no cargan comun.js: tienen sus propios `hace`, `coma` y `cuando`. Lo
        # que sí cargan las seis (dom.js, barra.js, tema.js) no choca con ningún nombre suyo.
        de_todas = set()
        for js in ("dom.js", "barra.js", "tema.js"):
            de_todas |= declarados_arriba(leer(COMUN / js))
        self.assertEqual(de_todas, {"el", "barraNodo", "aplicarTema"})
        for nombre, carpeta in PAGINAS.items():
            declarados = [declarados_arriba(leer(js)) for js in guiones(carpeta)]
            cargados = declarados + ([declarados_arriba(leer(COMUN / "comun.js"))]
                                     if "../comun/comun.js" in leer(carpeta / "index.html") else [])
            juntos = set().union(*cargados)
            # Un nombre declarado dos veces entre los scripts de una página rompe el segundo.
            self.assertEqual(sum(len(d) for d in cargados), len(juntos), nombre)
            self.assertFalse(juntos & de_todas, nombre)

    def test_un_solo_ancho_maximo(self):
        base = reglas_css(leer(COMUN / "base.css"))
        self.assertEqual([d["max-width"] for m, s, d in base if s == "main"], ["var(--ancho-pagina)"])
        self.assertEqual([d["--ancho-pagina"] for m, s, d in base if s == ":root"], ["1100px"])
        for carpeta in PAGINAS.values():
            for hoja in hojas(carpeta):
                for media, selector, decl in reglas_css(leer(hoja)):
                    with self.subTest(hoja=hoja.name, selector=selector):
                        if selector in ("main", "body", "html"):
                            self.assertNotIn("max-width", decl)
                        self.assertNotIn("--ancho-pagina", decl)

    def test_js_balanceado_con_el_tokenizador(self):
        archivos = [js for carpeta in [*PAGINAS.values(), COMUN] for js in guiones(carpeta)]
        self.assertEqual(sorted(a.name for a in archivos),
                     ["barra.js", "bots.js", "comun.js", "cuentas.js", "dom.js", "encargos.js", "glosario.js", "inicio.js", "luces.js",
                          "memoria.js", "modelo.js", "nodo.js", "noticias.js", "programados.js", "proyectos.js", "red.js", "revisar-anchos.js", "sistema.js", "tema.js"])
        for js in archivos:
            with self.subTest(js.name):
                self.assertTrue(tokens_js(leer(js)).strip())
        roto = leer(PAGINAS["sistema"] / "inicio.js").replace("function filasPi(e, ahora) {", "function filasPi(e, ahora) {{", 1)
        with self.assertRaises(ValueError):
            tokens_js(roto)

    def test_no_hay_style_en_linea(self):
        archivos = [f for carpeta in [*PAGINAS.values(), COMUN] for f in sorted(carpeta.iterdir())
                    if f.suffix in (".html", ".js") and not f.name.startswith("maqueta")]   # la maqueta no se instala
        self.assertEqual(len(archivos), 27)       # suma glosario.js de AI Ops (85a), y modelo.js y proyectos.js (99)
        for f in archivos:
            texto = leer(f)
            # En los JS se mira el código y sus strings, sin los comentarios (que nombran
            # el atributo para explicar por qué no se usa).
            codigo = tokens_js(texto, strings=True) if f.suffix == ".js" else texto
            with self.subTest(f"{f.parent.name}/{f.name}"):
                self.assertIsNone(re.search(r"style\s*=", codigo))
                self.assertNotIn("<style", codigo)
                for prohibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "cssText", "document.write"):
                    self.assertNotIn(prohibido, codigo, prohibido)
                self.assertIsNone(re.search(r"""setAttribute\(\s*["']style""", codigo))
                # el() pondría un atributo style: sólo se acepta el `style: false` de bots.js.
                self.assertEqual(re.findall(r"\bstyle:\s*(\S+)", tokens_js(texto) if f.suffix == ".js" else texto),
                                 ["false,"] if f.name == "bots.js" else [])
                # Quien marca un ancho con data-ancho lo aplica por CSSOM.
                if f.suffix == ".js" and '"data-ancho"' in texto:
                    self.assertTrue("aplicarAnchos(" in texto or ".style.flexGrow = " in texto)
        # La prueba mide: las tres formas de colar un estilo en línea se detectan.
        for malo in ('el("div", { style: "width: 10px" })', 'x.setAttribute("style", "a")',
                     'cont.innerHTML = "<b style=\\"a\\">";'):
            limpio = tokens_js(malo, strings=True)
            self.assertTrue(re.search(r"style\s*=|\bstyle:|innerHTML|setAttribute\(\s*[\"']style", limpio), malo)

    def test_ningun_script_ni_regla_de_sudo_nuevos(self):
        # Los comandos fijos que las páginas ya llamaban antes del encargo 18.
        conocidos = {"/usr/local/bin/bots-info", "/usr/local/bin/nodo-servicio", "/usr/local/bin/nodo-respaldo",
                     "/usr/local/bin/noticias-cockpit", "/usr/local/bin/piper", "/usr/local/bin/casa-cockpit",
                     "/home/dcifu004/.local/bin/luces"}
        usados = set()
        for carpeta in [*PAGINAS.values(), COMUN]:
            for js in guiones(carpeta):
                usados |= set(re.findall(r'"(/(?:usr/local/bin|home/dcifu004/\.local/bin)/[\w.-]+)"', leer(js)))
        self.assertEqual(usados, conocidos)
        # Con sudo, sólo lo que ya estaba en la lista blanca (pi/sudoers no cambió).
        con_sudo = set()
        for carpeta in [*PAGINAS.values(), COMUN]:
            for js in guiones(carpeta):
                codigo = leer(js)
                con_sudo |= set(re.findall(r'\["sudo", "-n", "(/(?:usr/local/bin|home/dcifu004/\.local/bin)/[^" ]+)"', codigo))
                con_sudo |= set(re.findall(r'raiz\("([^"]+)"', codigo))
        self.assertEqual(con_sudo, {"/usr/local/bin/bots-info", "/usr/local/bin/nodo-servicio",
                                    "/usr/local/bin/nodo-respaldo", "systemctl"})
        sudoers = leer(PI / "sudoers" / "020-nodo-lista-blanca")
        self.assertIn('/usr/local/bin/bots-info ""', sudoers)
        # La barra va en las seis páginas: no usa sudo.
        self.assertNotIn("sudo", tokens_js(leer(COMUN / "barra.js"), strings=True))


# ---- El espejo en Python del «leído hace X» de barra.js (revisión 18r1, hallazgo 1). ----
FECHA_INVALIDA = "Invalid Date"


def fecha_js(iso):
    """`new Date(iso)` para las fechas ISO que publican las fuentes (sin zona = hora local)."""
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return FECHA_INVALIDA
    return t.astimezone() if t.tzinfo is None else t


class LeidoBarra:
    """`marca`, `leido()` y `pintarLeido()` de barra.js, más el texto de `#leido`, que
    cualquier script de la página puede escribir por su cuenta."""

    def __init__(self):
        self.marca = None            # let marca = null;
        self.texto = ""              # el <span id="leido"> nace vacío

    def pintar(self, ahora):         # pintarLeido(): al marcar y, después, cada 30 s
        if self.marca is None or self.marca == FECHA_INVALIDA:
            self.texto = ""
        else:
            self.texto = "leído " + hace_inicio(redondea((ahora - self.marca).total_seconds() / 60))

    def leido(self, cuando, ahora):  # barraNodo.leido(cuando)
        self.marca = fecha_js(cuando) if cuando else ahora
        self.pintar(ahora)

    def escribir(self, texto):       # document.getElementById("leido").textContent = …
        self.texto = texto


def marcas_de_leido(js):
    """Lo que el código de una página le hace a «leído hace X», en el orden en que está
    escrito: ("barra", <primer argumento>) por cada `barraNodo.leido(…)` y ("directo", None)
    por cada vez que busca `#leido` para escribirlo ella."""
    codigo = tokens_js(js, strings=True)
    pasos = []
    for m in re.finditer(r'barraNodo\.leido\(|getElementById\("leido"\)|"#leido"', codigo):
        if m.group() == "barraNodo.leido(":
            pasos.append(("barra", tramo(codigo[m.start():], "barraNodo.leido(").split(",")[0].strip()))
        else:
            pasos.append(("directo", None))
    return pasos


def leido_tras(pasos, fuentes, ahora, espera=timedelta(seconds=30)):
    """La página carga (corre sus pasos) y pasa `espera` hasta un tick de la barra.
    Devuelve el texto de `#leido` al cargar y después del tick."""
    barra = LeidoBarra()
    for clase, arg in pasos:
        if clase == "directo":
            barra.escribir("leído recién")
        else:
            barra.leido(fuentes[arg] if arg else None, ahora)
    al_cargar = barra.texto
    barra.pintar(ahora + espera)     # setInterval(pintarLeido, 30000)
    return al_cargar, barra.texto


class BarraTests(unittest.TestCase):
    def setUp(self):
        self.js = leer(COMUN / "barra.js")
        self.codigo = tokens_js(self.js, strings=True)

    def test_es_un_componente_unico_que_ponen_las_seis(self):
        for nombre, carpeta in PAGINAS.items():
            html = leer(carpeta / "index.html")
            with self.subTest(nombre):
                if nombre == "encargos":
                    # Encargo 84a: 🧵 es la consola. No pone el hueco: dibuja la lista de barra.js tal cual.
                    self.assertNotIn('id="barra"', html)
                    self.assertIn("const MODULOS = barraNodo.GRUPOS.flat();", leer(carpeta / "encargos.js"))
                    continue
                # La página sólo pone el hueco: la barra la arma barra.js.
                self.assertEqual(re.findall(r'<nav id="barra" data-pagina="(\w+)"></nav>', html), [nombre])
                self.assertLess(html.index('<nav id="barra"'), html.index('<header class="cabeza">'))
                for js in guiones(carpeta):
                    self.assertNotIn("barra-enlace", leer(js))
        # Sus estilos, sólo en base.css.
        for carpeta in PAGINAS.values():
            for hoja in hojas(carpeta):
                self.assertNotIn("barra-nodo", leer(hoja), hoja.name)
                self.assertNotIn("barra-enlace", leer(hoja), hoja.name)

    def test_orden_grupos_y_salto(self):
        grupos = tramo(self.codigo, "const GRUPOS = [")
        # Inicio · Agents Asistentes Cuentas · Noticias · Luces: cuatro grupos, en el
        # orden del menú, separados por un punto.
        por_grupo = [re.findall(r'id: "(\w+)", icono: "[^"]+", texto: "(\w+)", destino: "(/\w+)"', g)
                     for g in re.findall(r"\[([^\[\]]+)\]", grupos)]
        self.assertEqual([[t for _, t, _ in g] for g in por_grupo],
                         [["Inicio"], ["Agents", "Asistentes", "Cuentas"], ["Encargos"], ["Noticias"], ["Luces"]])
        planos = [x for g in por_grupo for x in g]
        self.assertEqual([i for i, _, _ in planos], [n for n in MENU if n != "memoria"])   # la barra aún no conoce 🧠 (Fase 2b)
        for ident, _, destino in planos:
            self.assertEqual(destino, "/" + ident)     # el paquete que existe
        self.assertIn('i ? el("span", { class: "barra-punto", "aria-hidden": "true" }, "·") : null', self.codigo)
        self.assertIn("else cockpit.jump(p.destino);", self.codigo)
        # La actual va resaltada, y tocarla no salta: avisa (🍇 vuelve a 🏠 Inicio).
        self.assertIn('class: "barra-enlace" + (p.id === actual ? " actual" : "")', self.codigo)
        self.assertIn('if (p.id === actual) window.dispatchEvent(new CustomEvent("barra:actual"));', self.codigo)
        self.assertIn('window.addEventListener("barra:actual", () => mostrar("inicio"));',
                      leer(PAGINAS["sistema"] / "sistema.js"))

    def test_contadores_y_leido(self):
        # Propuestas por aplicar en 🤖 y noticias sin votar en 📰, en ámbar.
        self.assertIn('contar("bots", propuestas,', self.codigo)
        self.assertIn('contar("noticias", votar,', self.codigo)
        base = {s: d for m, s, d in reglas_css(leer(COMUN / "base.css")) if not m}
        self.assertEqual((base[".barra-contador"]["background"], base[".barra-contador"]["color"]),
                         ("var(--ojo-fondo)", "var(--ojo)"))
        # Sin dato no hay contador: no se muestra un 0.
        self.assertIn("c.hidden = !(n > 0);", self.codigo)
        # Cinco de antes (más bitácora/cola ilegible) y tres de la parte B: veredictoFase sin dato (2) y
        # leerProgramados ilegible. Sin dato no hay contador: nunca un 0.
        self.assertEqual(self.codigo.count("return null;"), 9)      # el noveno: horaFecha de una fecha ilegible (encargo 24)
        self.assertIn('contar("sistema", malas,', self.codigo)
        self.assertIn('contar("encargos", encargos &&', self.codigo)
        # «leído hace X» y Actualizar van a la derecha y los crea la barra.
        self.assertIn('const leidoTexto = el("span", { id: "leido", class: "tenue" });', self.codigo)
        self.assertIn('const actualizar = el("button", { id: "actualizar", class: "secundario mini" }, "Actualizar");',
                      self.codigo)
        self.assertIn('el("div", { class: "barra-lado" }, leidoTexto, actualizar)', self.codigo)
        self.assertEqual(base[".barra-lado"]["margin-left"], "auto")
        # Cada página dice cuándo leyó y qué hace su Actualizar.
        for nombre, carpeta in PAGINAS.items():
            codigo = "".join(leer(js) for js in guiones(carpeta))
            with self.subTest(nombre):
                # «leído» sólo por la barra: lo que una página escriba por su cuenta en
                # #leido lo borra el tick de 30 s (revisión 18r1, hallazgo 1).
                self.assertIn("barraNodo.leido(", codigo)
                self.assertNotIn('getElementById("leido")', codigo)
                if nombre == "encargos":
                    # Encargo 85a: sin #barra ni botón de actualizar, las lecturas programadas conservan la frescura.
                    self.assertNotIn("barraNodo.alActualizar(", codigo)
                    self.assertIn('setInterval(() => { if (!document.hidden && (panel === "ahora" || panel === "flujo")) leer()', codigo)
                    continue
                self.assertTrue("barraNodo.alActualizar(" in codigo or 'getElementById("actualizar")' in codigo)

    def test_leido_sigue_a_la_vista_despues_del_tick(self):
        # Revisión 18r1, hallazgo 1: 🤖 escribía #leido por su cuenta, la barra no tenía
        # marca y a los 30 s `pintarLeido()` lo dejaba vacío. Acá corre esa secuencia
        # (cargar la página + el tick) con lo que cada página hace de verdad en su código.
        # 1. El espejo (`LeidoBarra`) dice lo que dice barra.js.
        for linea in ("let marca = null;",
                      'leidoTexto.textContent = marca && !Number.isNaN(marca.getTime()) ? "leído " + haceTexto(marca) : "";',
                      "marca = cuando ? new Date(cuando) : new Date();",
                      "const min = Math.round((Date.now() - d.getTime()) / 60000);",
                      'if (min < 1) return "recién";', "const h = Math.floor(min / 60);",
                      "setInterval(pintarLeido, 30000);"):
            self.assertEqual(self.codigo.count(linea), 1, linea)
        for linea in ("if (min < 60) return `hace ${min} min`;",
                      "return h < 48 ? `hace ${h} h` : `hace ${Math.floor(h / 24)} días`;"):
            self.assertEqual(self.js.count(linea), 1, linea)
        self.assertIn("pintarLeido();", tramo(self.codigo, "function leido(cuando, detalle) {"))
        # Nadie más pone la marca ni escribe el texto.
        self.assertEqual(len(re.findall(r"\bmarca = ", self.codigo)), 2)        # el `let` y leido()
        self.assertEqual(self.codigo.count("leidoTexto.textContent"), 1)
        # 2. Las fechas que las páginas le pasan, con la forma real de sus fuentes:
        # `momento` de bots-info (bi.reunir()) y de estado.json.
        info = previas.SalidaReal.armar(self)
        fuentes = {"info.momento": info["momento"], "estado.momento": estado_real()["momento"],
                   "d.momento": programados_real()["momento"],
                   # `generado` del lector de 🧠 (isoformat con zona, timespec="seconds")
                   "datos.generado": "2026-10-04T20:54:00-03:00"}
        self.assertRegex(info["momento"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        for iso in fuentes.values():
            self.assertNotEqual(fecha_js(iso), FECHA_INVALIDA, iso)
        ahora = fecha_js(info["momento"]) + timedelta(seconds=2)
        # 3. En las seis: tras cargar y tras el tick, «leído …» sigue ahí.
        for nombre, carpeta in PAGINAS.items():
            pasos = marcas_de_leido("".join(leer(js) for js in guiones(carpeta)))
            with self.subTest(nombre):
                self.assertTrue(pasos)
                self.assertEqual([p for p in pasos if p[0] == "directo"], [])
                self.assertLessEqual({arg for _, arg in pasos}, {"", *fuentes})
                al_cargar, tras_tick = leido_tras(pasos, fuentes, ahora)
                self.assertTrue(al_cargar.startswith("leído "), al_cargar)
                self.assertTrue(tras_tick.startswith("leído "), repr(tras_tick))
        # 🤖 y 💳 muestran la hora del dato de bots-info, y el texto envejece con el tick.
        for nombre in ("bots", "cuentas"):
            pasos = marcas_de_leido("".join(leer(js) for js in guiones(PAGINAS[nombre])))
            self.assertEqual(pasos, [("barra", "info.momento")], nombre)
            # 2 s al cargar; 32 s en el tick, que Math.round ya cuenta como un minuto.
            self.assertEqual(leido_tras(pasos, fuentes, ahora), ("leído recién", "leído hace 1 min"))
            self.assertEqual(leido_tras(pasos, fuentes, ahora, timedelta(minutes=5))[1], "leído hace 5 min")
        # 4. La prueba mide: con la línea que tenía bots.js, el texto se pierde en el tick.
        actual = leer(PAGINAS["bots"] / "bots.js")
        self.assertEqual(actual.count("    barraNodo.leido(info.momento);\n"), 1)
        vieja = actual.replace("    barraNodo.leido(info.momento);\n",
                               '    document.getElementById("leido").textContent = "leído " + hace(info.momento);\n')
        self.assertEqual(marcas_de_leido(vieja), [("directo", None)])
        self.assertEqual(leido_tras(marcas_de_leido(vieja), fuentes, ahora), ("leído recién", ""))
        # Y una fecha que no se entiende no se muestra como «recién».
        self.assertEqual(leido_tras([("barra", "x")], {"x": "no es una fecha"}, ahora), ("", ""))

    def test_cabe_en_el_telefono(self):
        # Envuelve: nada de la barra fuerza una sola línea ni un ancho fijo.
        vistas = 0
        for media, selector, decl in reglas_css(leer(COMUN / "base.css")):
            if "barra-" not in selector or "barra-ciclo" in selector:
                continue
            vistas += 1
            for prop, valor in decl.items():
                self.assertFalse(prop.startswith("overflow"), selector)
                self.assertFalse(prop == "white-space" and "nowrap" in valor, selector)
                self.assertFalse(prop == "flex-wrap" and valor == "nowrap", selector)
                self.assertFalse(prop in ("width", "min-width") and valor.endswith("px") and float(valor[:-2]) > 0,
                                 selector)
        self.assertGreaterEqual(vistas, 7)
        base = {s: d for m, s, d in reglas_css(leer(COMUN / "base.css")) if not m}
        for selector in (".barra-nodo", ".barra-enlaces", ".barra-lado"):
            self.assertEqual(base[selector]["flex-wrap"], "wrap", selector)
        self.assertEqual(base[".barra-enlaces"]["min-width"], "0")

    def test_cabecera_estandar(self):
        for nombre, carpeta in PAGINAS.items():
            html = leer(carpeta / "index.html")
            with self.subTest(nombre):
                cabeceras = re.findall(r'<header class="cabeza">(.*?)</header>', html, re.S)
                self.assertEqual(len(cabeceras), 1)
                if nombre == "encargos":
                    # Encargo 85a: AI Ops tiene una sola barra; el título es el de la pestaña de portada.
                    self.assertEqual(html.count("<header"), 2)
                    self.assertEqual(html.count('<header class="consola-barra">'), 1)
                    self.assertEqual(re.findall(r'<h1 id="titulo">([^<]+)</h1>', cabeceras[0]), ["Flow"])
                    self.assertIn('data-term="AI Ops">🏭 AI Ops', html)
                else:
                    self.assertEqual(html.count("<header"), 1)
                    # Título (el del menú) y un subtítulo; «leído» y Actualizar, en la barra.
                    self.assertEqual(re.findall(r"<h1>([^<]+)</h1>", cabeceras[0]), [MENU[nombre][1]])
                self.assertEqual(len(re.findall(r'<p class="sub"', cabeceras[0])), 1)
                self.assertNotIn('id="leido"', html)
                self.assertNotIn('id="actualizar"', html)
                self.assertEqual(html.count("<h1"), 1)        # 84a: el de 🧵 lleva id="titulo"


class CuentasTests(unittest.TestCase):
    def setUp(self):
        self.html = leer(PAGINAS["cuentas"] / "index.html")
        self.js = leer(PAGINAS["cuentas"] / "cuentas.js")

    def test_margen_fijo_arriba_y_lo_demas_en_pestanas(self):
        secciones = re.findall(r'<section class="tarjeta" id="([\w-]+)"( data-pestana="(\w+)")?( hidden)?>', self.html)
        self.assertEqual([(i, p, bool(h)) for i, _, p, h in secciones], [
            ("margen", "", False),                      # fijo arriba: no es de ninguna pestaña
            ("matriz", "rutas", False),                 # la pestaña que abre
            ("proveedores", "proveedores", True),
            ("cuentas-uso", "uso", True),
            ("rendimiento", "uso", True),               # el rendimiento por motor y
            ("pcs", "uso", True),                       # el uso de los PC van en Uso y costo
            ("registro", "renovacion", True)])
        botones = re.findall(r'<button data-p="(\w+)"( class="activa")?>([^<]+)</button>', self.html)
        self.assertEqual([(p, bool(a), t.split(" ", 1)[1]) for p, a, t in botones],
                         [("rutas", True, "Rutas"), ("proveedores", False, "Proveedores"),
                          ("uso", False, "Uso y costo"), ("renovacion", False, "Registro")])
        self.assertLess(self.html.index('id="margen"'), self.html.index('<nav class="pestanas" id="paneles">'))
        self.assertLess(self.html.index('<nav class="pestanas" id="paneles">'), self.html.index('id="matriz"'))
        # La pestaña sólo decide qué secciones se ven; el margen no se toca.
        mostrar = tramo(tokens_js(self.js, strings=True), "function mostrarPanel(p) {")
        self.assertIn("s.hidden = s.dataset.pestana !== p;", mostrar)
        self.assertIn('document.querySelectorAll("section[data-pestana]").forEach(s => { s.hidden = s.dataset.pestana !== p; });',
                      self.js)
        self.assertIn('b.classList.toggle("activa", b.dataset.p === p)', mostrar)
        self.assertIn('document.querySelectorAll("#paneles button").forEach(b => b.addEventListener("click", () => mostrarPanel(b.dataset.p)));',
                      self.js)
        # Al releer bots-info se queda en la pestaña que se estaba mirando.
        self.assertIn("mostrarPanel(panelVisible);", tramo(tokens_js(self.js, strings=True), "async function cargar() {"))

    def test_las_propuestas_se_listan_solo_en_asistentes(self):
        # 💳 ya no tiene la lista: ni el contenedor ni la llamada que la pinta.
        self.assertNotIn('id="propuestas"', self.html)
        self.assertNotIn("📝 Propuestas", self.html)
        self.assertNotIn("pintarPropuestas(", self.js)
        self.assertNotIn("Copiar comando", self.js)
        # Muestra un contador con enlace a 🤖 Asistentes.
        self.assertEqual(self.html.count('<div id="propuestas-contador" class="aviso neutro"></div>'), 1)
        self.assertIn("pintarContadorPropuestas();", tramo(tokens_js(self.js, strings=True), "async function cargar() {"))
        contador = tramo(tokens_js(leer(COMUN / "comun.js"), strings=True), "async function pintarContadorPropuestas() {")
        self.assertIn('document.getElementById("propuestas-contador")', contador)
        self.assertIn('cockpit.jump("/bots")', contador)
        self.assertIn("await barraNodo.refrescar()", contador)
        # Sin poder leer la carpeta dice «sin datos», no «no hay».
        self.assertIn('propuestas == null ? "📝 Propuestas por aplicar: sin datos', contador)
        # Sigue pudiendo PROPONER (cada propuesta se guarda y el contador sube).
        for tipo in ('tipo: "cuentas"', 'tipo: "recetas"', 'tipo: "registro_cuentas"'):
            self.assertIn(tipo, self.js)
        for texto in ("Tope semanal %", "Tope 5 h %", "lo usan el bot y los encargos",
                      "umbral_semanal: umbral(f.semanal)", "umbral_5h: umbral(f.h5)"):
            self.assertIn(texto, self.js)
        guardar = tramo(tokens_js(leer(COMUN / "comun.js"), strings=True), "async function guardarPropuesta() {")
        self.assertIn("await pintarContadorPropuestas();", guardar)
        # La lista queda en 🤖, y sólo ahí.
        con_lista = [n for n, c in PAGINAS.items() if 'id="propuestas"' in leer(c / "index.html")]
        self.assertEqual(con_lista, ["bots"])
        self.assertIn("await pintarPropuestas();", leer(PAGINAS["bots"] / "bots.js"))


class LucesYVentiladorTests(unittest.TestCase):
    def test_spawn_nunca_recibe_input_como_opcion(self):
        """13-10-2026: `{ input: ... }` no es opción de cockpit.spawn; se ignoraba y
        `luces reglas guardar` quedaba colgado esperando stdin, sin error en la página.
        El texto va con .input(datos), que escribe y cierra."""
        for nombre, carpeta in PAGINAS.items():
            for js in sorted(carpeta.glob("*.js")):
                self.assertNotRegex(leer(js), r"spawn\([^;]*\{[^}]*\binput\s*:",
                                    f"{nombre}/{js.name}: usa .input(datos), no la opción input")
        js = leer(PAGINAS["luces"] / "luces.js")
        self.assertEqual(js.count('"reglas", "guardar"], { err: "message" }).input(JSON.stringify(reglas))'), 2)

    def test_luces_queda_solo_con_los_led(self):
        html, js, css = (leer(PAGINAS["luces"] / n) for n in ("index.html", "luces.js", "luces.css"))
        for fuera in ('id="temp"', 'id="rpm"', 'id="pwm-barra"', 'id="pwm-txt"', "🌀 Ventilador"):
            self.assertNotIn(fuera, html, fuera)
        codigo = tokens_js(js, strings=True)
        for fuera in ("ventilador", "temp_c", "pwm", "rpm"):
            self.assertNotIn(fuera, codigo, fuera)
        self.assertNotIn(".ventilador", css)
        # Los LED siguen: la tira, los colores y los tres deslizadores.
        for queda in ('id="tira"', 'id="muestras"', 'id="girar"', 'id="respira"', 'id="brillo"', 'id="apagar"'):
            self.assertIn(queda, html, queda)

    def test_temperatura_y_ventilador_estan_en_estado(self):
        js = leer(PAGINAS["sistema"] / "sistema.js")
        codigo = tokens_js(js, strings=True)
        tarjeta = tramo(codigo, "function tarjetaVentilador(e) {")
        self.assertIn("tarjetaVentilador(e),", tramo(codigo, "async function pintarEstado() {"))
        for trozo in ('"🌀 Temperatura y ventilador"', ".temp_soc", "e.ventilador", "v.rpm", "v.pct"):
            self.assertIn(trozo, tarjeta, trozo)
        # Sin dato dice «sin datos», no 0; el ancho de la barra va por CSSOM.
        self.assertEqual(tarjeta.count('"sin datos"'), 2)
        self.assertIn("if (pct != null) barra.style.width = `${pct}%`;", js)
        # Los campos que lee existen en estado.json (forma real).
        e = estado_real()
        self.assertEqual(set(e["ventilador"]), {"rpm", "pwm", "pct"})
        self.assertIn("v", e["medidores"]["temp_soc"])
        self.assertIn(".ventilador", leer(PAGINAS["sistema"] / "sistema.css"))

    def test_reglas_y_horario_usan_la_salida_real_y_no_abren_una_via_de_texto_libre(self):
        """F4: fixture de `luces reglas` con la forma publicada por F1/F3.

        No hay Node en la Pi: se ata la estructura de la interfaz al JS y se usa el
        catálogo/configuración reales del módulo aislado de luces, sin tocar hardware.
        """
        import tempfile, types
        falso = types.SimpleNamespace(neopixel_write=lambda *_: None)
        anterior = sys.modules.get("adafruit_raspberry_pi5_neopixel_write")
        sys.modules["adafruit_raspberry_pi5_neopixel_write"] = falso
        try:
            luces_mod = previas._cargar("luces_fixture_reglas", PI / "luces.py")
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                luces_mod.REGLAS = str(tmp / "luces-reglas.json")
                luces_mod.REGLAS_OK = str(tmp / "luces-reglas.ok.json")
                luces_mod.SENAL = str(tmp / "luces-senal.json")
                luces_mod.ESTADO = str(tmp / "luces.json")
                luces_mod.guardar_reglas({"reglas": luces_mod.REGLAS_DEFECTO,
                                          "horario_brillo": luces_mod.CONFIG_DEFECTO["horario_brillo"]})
                Path(luces_mod.SENAL).write_text('{"senales": {}, "toques": []}', encoding="utf-8")
                Path(luces_mod.ESTADO).write_text('{"modo": "apagado", "rgb": [0, 0, 0], "brillo": 100}', encoding="utf-8")
                salida = io.StringIO()
                with contextlib.redirect_stdout(salida): luces_mod.main(["reglas"])
                fixture = json.loads(salida.getvalue())
        finally:
            if anterior is None: sys.modules.pop("adafruit_raspberry_pi5_neopixel_write", None)
            else: sys.modules["adafruit_raspberry_pi5_neopixel_write"] = anterior
        self.assertEqual(set(fixture), {"configuracion", "catalogo", "activas", "reglas_activas"})
        self.assertTrue(fixture["reglas_activas"])
        self.assertIn("boleta_registrada", fixture["catalogo"])
        self.assertFalse(fixture["catalogo"]["boleta_registrada"]["conectado"])
        self.assertEqual(set(fixture["configuracion"]), {"reglas", "horario_brillo"})
        js, html = leer(PAGINAS["luces"] / "luces.js"), leer(PAGINAS["luces"] / "index.html")
        for control in ("regla-agregar", "reglas-defecto", "horario-agregar", "tabla-reglas", "tabla-horario"):
            self.assertIn(f'id="{control}"', html)
        for trozo in ('JSON.parse(await luces("reglas"))', '"reglas", "guardar"', 'ESPERA_COLOR_MS',
                      'setTimeout(() => { reglaMostrada = anterior; pintar(true); }, 5000)',
                      'if (regla.tipo === "toque") await luces("evento", regla.evento);', 'textoReglasSeguro', 'RE_TEXTO_REGLAS'):
            self.assertIn(trozo, js)
        # La configuración que duplica la página es la misma que acepta el backend real.
        bloque = re.search(r"const REGLAS_DEFECTO = \[(.*?)\n\];", js, re.S).group(1)
        filas_js = re.findall(r'\["([^"]+)", "([^"]+)", "([^"]+)", "([^"]+)", (\d+), (\d+), (\d+), (\d+), (\d+)\]', bloque)
        self.assertEqual(len(filas_js), len(fixture["configuracion"]["reglas"]))
        for fila_js, fila_py in zip(filas_js, fixture["configuracion"]["reglas"]):
            self.assertEqual(fila_js[:4], tuple(fila_py[k] for k in ("id", "tipo", "color", "animacion")))
            self.assertEqual(tuple(map(int, fila_js[4:])), tuple(fila_py[k] for k in ("nivel", "repetir", "dura_s", "cada_s", "prioridad")))
        self.assertEqual(re.search(r'if \(id === "cpu_caliente"\) regla\.umbral_c = (\d+);', js).group(1), "67")
        horario = re.search(r"horario_brillo: (\[.*?\]) };", js, re.S).group(1)
        horario = json.loads(horario.replace("hora:", '"hora":').replace("brillo:", '"brillo":'))
        self.assertEqual(horario, fixture["configuracion"]["horario_brillo"])
        modelo = copy.deepcopy(fixture["configuracion"])
        validar = luces_mod.validar_configuracion
        agregado = {"id": "regla-prueba", "evento": "aviso_error", "activa": True, "tipo": "toque",
                    "color": "rojo", "animacion": "destello", "nivel": 5, "repetir": 1,
                    "dura_s": 5, "cada_s": 0, "prioridad": 3}
        modelo["reglas"].append(agregado); validar(modelo)
        modelo["reglas"].insert(1, {**agregado, "id": "regla-prueba-copia"}); validar(modelo)
        modelo["reglas"].pop(1); validar(modelo)
        modelo["reglas"][0]["evento"] = "cpu_caliente"; modelo["reglas"][0]["tipo"] = fixture["catalogo"]["cpu_caliente"]["tipo"]; validar(modelo)
        modelo["horario_brillo"].append({"hora": "12:00", "brillo": 75}); validar(modelo)
        modelo["horario_brillo"].pop(); validar(modelo)
        # Los botones alteran el mismo documento completo que se guarda; no hay una vía
        # paralela de texto libre ni una copia de la lista blanca escrita en la prueba.
        for operacion in ('reglas.reglas.push(', 'reglas.reglas.splice(i + 1, 0, { ...regla, id })',
                          'reglas.reglas.splice(i, 1)', 'reglas = configuracionDefecto(reglasEstanActivas(reglas))',
                          'reglas.horario_brillo.push(', 'reglas.horario_brillo.splice(i, 1)'):
            self.assertIn(operacion, js)
        self.assertIn('await luces("estado")', js)
        self.assertIn('if (reglasActualizadas && !reglasSucias) pintarReglas();', js)
        self.assertIn('if (!reglasSucias) {', js)
        self.assertIn('if (version === versionReglas) {', js)
        self.assertIn('const tenue = [32, 32, 32];', js)
        self.assertIn('regla.color === "base" && regla.animacion === "respira"', js)
        self.assertIn('class="tabla-reglas"', html); self.assertIn('class="tabla-horario"', html)
        self.assertIn('.error-detalle', leer(PAGINAS["luces"] / "luces.css"))

    def test_57b_interruptor_aviso_y_catalogo(self):
        """57b: el interruptor sólo cambia por CLI y no se pierde al guardar."""
        js, html, css = (leer(PAGINAS["luces"] / n) for n in ("luces.js", "index.html", "luces.css"))
        self.assertIn('id="reglas-activas"', html)
        self.assertIn('id="config-error"', html)
        self.assertIn('Reglas apagadas: las luces muestran sólo lo elegido arriba.', html)
        self.assertIn('.reglas-apagadas', css)
        self.assertIn('function reglasEstanActivas(configuracion) {\n    return configuracion.reglas_activas !== false;', js)
        self.assertTrue({}.get("reglas_activas", True))
        self.assertFalse({"reglas_activas": False}.get("reglas_activas", True))
        # Los únicos cambios del interruptor son los dos argumentos fijos de la CLI.
        self.assertIn('[LUCES, "reglas", prendidas ? "prender" : "apagar"]', js)
        self.assertEqual(len(re.findall(r'cockpit\.spawn\(\[LUCES, "reglas", .*?\]', js)), 3)
        # Todos los guardados serializan la configuración ya leída, incluida la clave.
        # (Por .input(): la opción `input:` dejaba `guardar` colgado; ver test_spawn_nunca_…)
        self.assertEqual(js.count('.input(JSON.stringify(reglas))'), 2)
        self.assertNotIn('reglas.reglas_activas =', js)
        # 57br3: «Volver a valores por defecto» conserva el interruptor leído; ninguna
        # configuración armada en la página fija reglas_activas a un literal.
        defecto_js = tramo(js, "function configuracionDefecto(reglasActivas) {")
        self.assertIn("reglas_activas: reglasActivas,", defecto_js)
        self.assertNotRegex(js, r"reglas_activas:\s*(true|false)")
        self.assertEqual(js.count("configuracionDefecto("), 2)
        self.assertIn('await leer();', tramo(js, 'async function cambiarReglasActivas() {'))
        # El aviso sólo llega como texto y el filtro rechaza HTML hostil.
        patron = re.search(r"const RE_TEXTO_REGLAS = (/.+?/);", js).group(1)
        seguro = re.compile(patron[1:patron.rfind("/")])
        mensaje = "no valida: reglas[0].color; se usa la última guardada"
        self.assertRegex(mensaje, seguro)
        self.assertNotRegex("<img src=x onerror=1>", seguro)
        defecto = "La configuración de reglas no es válida; se usa la última guardada"
        texto_visible = lambda valor: valor if isinstance(valor, str) and seguro.fullmatch(valor) else defecto
        self.assertEqual(texto_visible(mensaje), mensaje)
        self.assertEqual(texto_visible("<img src=x onerror=1>"), defecto)
        self.assertFalse(isinstance(None, str))
        self.assertIn('textoReglasSeguro(mensaje, "La configuración de reglas no es válida; se usa la última guardada")', js)
        self.assertNotIn("innerHTML", js)
        bloque = re.search(r"const REGLAS_DEFECTO = \[(.*?)\n\];", js, re.S).group(1)
        ids_js = set(re.findall(r'\["([^"]+)",', bloque))
        import types
        falso = types.SimpleNamespace(neopixel_write=lambda *_: None)
        anterior = sys.modules.get("adafruit_raspberry_pi5_neopixel_write")
        sys.modules["adafruit_raspberry_pi5_neopixel_write"] = falso
        try:
            luces_mod = previas._cargar("luces_fixture_57b", PI / "luces.py")
            ids_py = {regla["id"] for regla in luces_mod.REGLAS_DEFECTO}
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                luces_mod.REGLAS, luces_mod.REGLAS_OK = str(tmp / "reglas.json"), str(tmp / "reglas-ok.json")
                luces_mod.SENAL, luces_mod.ESTADO = str(tmp / "senal.json"), str(tmp / "estado.json")
                Path(luces_mod.SENAL).write_text('{"senales": {}, "toques": []}', encoding="utf-8")
                sin_clave = copy.deepcopy(luces_mod.CONFIG_DEFECTO)
                luces_mod.guardar_reglas(sin_clave)
                salida = io.StringIO()
                with contextlib.redirect_stdout(salida): luces_mod.main(["reglas"])
                self.assertNotIn("reglas_activas", json.loads(salida.getvalue())["configuracion"])
                con_clave = {**sin_clave, "reglas_activas": False}
                luces_mod.guardar_reglas(con_clave)
                salida = io.StringIO()
                with contextlib.redirect_stdout(salida): luces_mod.main(["reglas"])
                self.assertFalse(json.loads(salida.getvalue())["configuracion"]["reglas_activas"])
        finally:
            if anterior is None: sys.modules.pop("adafruit_raspberry_pi5_neopixel_write", None)
            else: sys.modules["adafruit_raspberry_pi5_neopixel_write"] = anterior
        self.assertEqual(ids_js, ids_py)
        # Vuelta 2: una edición pendiente bloquea el interruptor; no puede iniciar el
        # guardado completo por este camino. La configuración usada abajo sale de la
        # salida real de `luces reglas`, no de un diccionario reducido inventado.
        toggle = tramo(js, "async function cambiarReglasActivas() {")
        self.assertNotIn("guardarReglasAhora", toggle)
        self.assertIn('if (reglasSucias) {', toggle)
        self.assertIn('control.disabled = true;', toggle)
        self.assertIn('[LUCES, "reglas", prendidas ? "prender" : "apagar"]', toggle)
        self.assertIn('control.disabled = reglasSucias;', js)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            luces_mod.REGLAS, luces_mod.REGLAS_OK = str(tmp / "reglas.json"), str(tmp / "reglas-ok.json")
            base = copy.deepcopy(luces_mod.CONFIG_DEFECTO)
            base["reglas_activas"] = False
            luces_mod.guardar_reglas(base)
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida): luces_mod.main(["reglas"])
            local = json.loads(salida.getvalue())["configuracion"]
            local["reglas"][0]["color"] = "verde"
            luces_mod.guardar_reglas(local)  # representa el guardado ya programado
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida): luces_mod.main(["reglas"])
            despues = json.loads(salida.getvalue())["configuracion"]
            self.assertEqual(despues["reglas"][0]["color"], "verde")
            self.assertFalse(despues["reglas_activas"])
        self.assertIn('setTimeout(correr, espera)', js)  # 450 ms para toques
        self.assertIn('programarReglas(fila, guardarAhora)', js)  # sliders sólo al soltar
        self.assertNotIn("innerHTML", js)
        # Los textos que llegan al DOM son catálogo/campos validados o pasan por la lista blanca.
        regex_fuente = re.search(r"const RE_TEXTO_REGLAS = (/.+?/);", js).group(1)
        patron = regex_fuente[1:regex_fuente.rfind("/")]
        self.assertRegex("reglas[0].nivel: debe estar entre 1 y 10", re.compile(patron))
        self.assertNotRegex('reglas[0].nivel: "rojo" <bad>', re.compile(patron))
        self.assertIn('class="tabla-reglas"', html)
        self.assertIn('class="tabla-horario"', html)
        self.assertIn('.error-detalle', leer(PAGINAS["luces"] / "luces.css"))


# --- 🏠 Inicio ----------------------------------------------------------------------
AHORA = datetime(2026, 10, 3, 17, 45, 0).astimezone()
SIN_DATOS = "sin datos"


def estado_real():
    """estado.json con la forma que publica estado.py (copiada del de la Pi, 03-10-2026)."""
    return {
        "host": "Pi5Diego", "momento": "2026-10-03T17:40:57",
        "encendida_hace": "1 week, 2 days, 19 hours, 16 minutes",
        "luks": {"abierto": True, "usado": 1866178560, "total": 202705911808, "pct": 1},
        "servicios": {"docker": True, "tailscaled": True, "ssh": True, "captura-telegram": True,
                      "captura-web": True, "home-assistant": True, "botv3@jaime": True, "botv3@pilar": True,
                      "cockpit.socket": True, "luces": True, "rclone-drive@personal": True,
                      "google-puente.socket": True},
        "contenedores": [{"nombre": "n8n", "estado": "Up 2 days", "ok": True, "runtime": "docker"},
                         {"nombre": "postgres", "estado": "Up 9 days (healthy)", "ok": True, "runtime": "docker"},
                         {"nombre": "syncthing", "estado": "Up 9 days (healthy)", "ok": True, "runtime": "docker"},
                         {"nombre": "home-assistant", "estado": "Up 9 days", "ok": True, "runtime": "podman"}],
        "reinicios": {},
        "red": {"tailscale": "100.64.0.1", "ip_local": "192.168.0.2", "clave_vence": False},
        "sync": {"carpetas": [{"label": "vault_trabajo", "archivos": 428, "bytes": 84379360, "faltan": 0,
                               "estado": "idle", "ok": True}],
                 "dispositivos": [{"nombre": "DESKTOP-96QNU37", "conectado": True, "lan": False, "tipo": "tcp"}]},
        "captura": {"activo": True, "hoy": 0, "ultimo_dia": "2026-10-02"},
        "inbox": {"pendientes": 0, "audios_pendientes": 0, "mas_vieja_dias": None, "lista": [], "total": 15},
        "agentes": [{"agente": "codex", "pid": 1882744, "usuario": "dcifu004", "horas": 90.75972222222222, "sub": ""}],
        "respaldo": {"montado": True, "libre": 13958770688, "total": 15275532288, "dispositivo": "/dev/sdb1",
                     "en_disco_aparte": True, "ultimo": "2026-10-03T03:30:17-03:00", "horas": 14.2,
                     "proximo": "Sun 2026-10-04 03:30:00"},
        "salud": {"unidades_fallidas": [], "reloj_ntp": True, "errores_io": 0, "reinicio_pendiente": False,
                  "actualizaciones": 11},
        "avisos": {"permanente": False, "ultimo_error": None, "ultimo_envio": 1790992947.17, "min_sin_ciclo": 5.7},
        "nvme_errores": 0,
        "medidores": {
            "temp_soc": {"v": 49.9, "max": 85, "am": 70, "ro": 80, "min": 30, "u": "C", "nota": "ok <70 · limita 80 · corta 85"},
            "temp_nvme": {"v": 50.0, "max": 85, "am": 65, "ro": 75, "min": 30, "u": "C", "nota": "ok <65 · critico 75"},
            "raiz": {"v": 37, "max": 100, "am": 80, "ro": 92, "u": "%", "nota": "14G/39G"}},
        "ventilador_rpm": 0, "ventilador": {"rpm": 0, "pwm": 0, "pct": 0},
        "luces": {"modo": "arcoiris", "rgb": None, "nombre": None, "momento": "2026-09-28T23:24:36",
                  "brillo": 90, "paleta": None, "girar": 8, "respira": 0},
        "throttled": True,
        "alertas": [{"id": "agente:1882744", "texto": "codex vivo hace 91 h (pid 1882744)"}],
        "edad_min": 0.0,
    }


def uso_real():
    """uso.json con la forma que publica uso.py: lo de `SalidaReal` (límites por cuenta)
    más el bloque `claude` de las sesiones de la Pi, que es el que lee 👾."""
    balde = {"entrada": 0, "salida": 0, "cache_lectura": 0, "cache_escritura": 0, "pensamiento": 0,
             "mensajes": 0, "modelos": {}}
    return {"cuenta": "dcifu004", "host": "Pi5Diego", "momento": "2026-10-03T17:39:17-03:00",
            "claude": {"disponible": True, "hoy": dict(balde, mensajes=12),
                       "semana": dict(balde, mensajes=67), "total": dict(balde, mensajes=449),
                       "sidechain_mensajes": 0, "transcripts": 19, "desde": "2026-09-09"},
            "codex": {"disponible": False, "razon": "Codex no expone consumo por CLI", "home": "/x"},
            **previas.SalidaReal.uso_json()}


def noticias_real():
    """La salida de `noticias-cockpit estado` (misma forma que lee la pestaña 🗳️ Entregas)."""
    elegido = {"marcado": False, "titulo": "Un titular", "evento": "otro", "cobertura": 1,
               "medio": "un-medio", "url": "https://example.com/1", "hash": "cf005061fcab075f", "tema": "obras"}
    return {
        "corridas": {"lista": [{"id": "2026-10-03T190537", "cuando": "2026-10-03T19:05:37.661791+00:00",
                                "items": 2300, "grupos": 2086,
                                "ciegos": json.dumps({"fuentes_caidas": ["elquintopoder", "mercopress", "lic"]})}],
                     "nuevos_hoy": 855, "total": 22382},
        "turnos": {"noticias-cosecha": {"proximo": "Sat 2026-10-03 18:00:10 -03", "ultimo": "Sat 2026-10-03 16:01:57 -03"},
                   "noticias-seleccion": {"proximo": "Sat 2026-10-03 19:30:00 -03", "ultimo": "Sat 2026-10-03 12:00:12 -03"}},
        "entregas": [{"archivo": "2026-10-03 1200 - noticias - Pi5Diego.md",
                      "elegidos": [dict(elegido, hash=f"{i:016x}") for i in range(8)],
                      "descartados": [{"titulo": "Otro titular", "evento": "emergencia", "puntaje": 0.502}]}],
        "preferencias": {"eventos": {}, "temas": {}, "medios": {}, "items": 198, "marcados": 0},
    }


def luces_real():
    """La salida de `luces estado`."""
    return {"modo": "arcoiris", "rgb": None, "nombre": None, "momento": "2026-09-28T23:24:36", "paleta": None,
            "brillo": 90, "girar": 8, "respira": 0, "vigente": True, "animacion_viva": True,
            "colores": {"rojo": [255, 0, 0], "verde": [0, 255, 0]},
            "ventilador": {"temp_c": 49.0, "rpm": 1688, "pwm": 75}}


# ---- El espejo en Python de inicio.js. Mismo orden, mismos nombres, mismas reglas. ----

def redondea(x):
    return math.floor(x + 0.5)       # Math.round


def fila_inicio(dato, valor, avisa=False):
    falta = valor is None or valor == "" or (isinstance(valor, float) and not math.isfinite(valor))
    if isinstance(valor, bool):
        valor = "true" if valor else "false"
    return {"dato": dato, "valor": SIN_DATOS if falta else str(valor),
            "nivel": "gris" if falta else "ojo" if avisa else ""}


def punto_inicio(filas):
    if any(f["nivel"] == "ojo" for f in filas):
        return "ojo"
    return "gris" if not filas or any(f["nivel"] == "gris" for f in filas) else "ok"


def minutos_desde(iso, ahora):
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.astimezone()            # sin zona = hora local, como `new Date()` en el navegador
    return max(0, redondea((ahora - t).total_seconds() / 60))


def hace_inicio(minutos):
    if minutos is None:
        return None
    if minutos < 1:
        return "recién"
    if minutos < 60:
        return f"hace {minutos} min"
    h = minutos // 60
    return f"hace {h} h" if h < 48 else f"hace {h // 24} días"


def coma_inicio(x, dec):
    return f"{float(x):.{dec}f}".replace(".", ",")


def fecha_inicio(iso):
    try:
        d = datetime.fromisoformat(iso).astimezone()
    except (TypeError, ValueError):
        return None
    return f"{d.day:02d}-{d.month:02d} {d.hour:02d}:{d.minute:02d}"


def filas_pi(e, ahora):
    serv = list(e["servicios"].items()) if e and e.get("servicios") else None
    cont = e["contenedores"] if e and isinstance(e.get("contenedores"), list) else None
    caidos = ([n for n, ok in serv if not ok] + [c["nombre"] for c in cont if not c["ok"]]
              if serv and cont is not None and serv is not None else None)
    m = (e or {}).get("medidores") or {}
    temp, raiz = m.get("temp_soc"), m.get("raiz")
    vent = e.get("ventilador") if e else None
    luks = e.get("luks") if e else None
    r = e.get("respaldo") if e else None
    alertas = e["alertas"] if e and isinstance(e.get("alertas"), list) else None
    edad = minutos_desde(e.get("momento"), ahora) if e else None
    return [
        fila_inicio("Servicios", None if caidos is None else
                    (f"{len(caidos)} caído(s): {', '.join(caidos)}" if caidos else f"{len(serv) + len(cont)} arriba"),
                    bool(caidos)),
        fila_inicio("Temperatura", f"{coma_inicio(temp['v'], 1)} °C" if temp and temp.get("v") is not None else None,
                    bool(temp and temp.get("am") is not None and temp["v"] >= temp["am"])),
        fila_inicio("Ventilador", (f"{vent['rpm']} rpm" + (f" · {vent['pct']} %" if vent.get("pct") is not None else ""))
                    if vent and vent.get("rpm") is not None else None),
        fila_inicio("Disco raíz", f"{redondea(raiz['v'])} % usado" if raiz and raiz.get("v") is not None else None,
                    bool(raiz and raiz.get("am") is not None and raiz["v"] >= raiz["am"])),
        fila_inicio("Volumen cifrado", None if not luks else
                    ("abierto" + (f" · {luks['pct']} % usado" if luks.get("pct") is not None else "")
                     if luks.get("abierto") else "CERRADO"), bool(luks and not luks.get("abierto"))),
        fila_inicio("Respaldo", hace_inicio(minutos_desde(r["ultimo"], ahora)) if r and r.get("ultimo") else None),
        fila_inicio("Disco de respaldo", None if not r else ("montado" if r.get("montado") else "no montado"),
                    bool(r and not r.get("montado"))),
        fila_inicio("Alertas", None if alertas is None else
                    (f"{len(alertas)}: {alertas[0].get('texto') or alertas[0].get('id')}" if alertas else "ninguna"),
                    bool(alertas)),
        fila_inicio("Medido", hace_inicio(edad), edad is not None and edad > 20),
    ]


def filas_agentes(e, u, ahora):
    agentes = e["agentes"] if e and isinstance(e.get("agentes"), list) else None
    alertas = e["alertas"] if e and isinstance(e.get("alertas"), list) else []

    def sesion(nombre):
        if agentes is None:
            return fila_inicio(nombre, None)
        suyos = [a for a in agentes if str(a.get("agente")).lower() == nombre.lower()]
        if not suyos:
            return fila_inicio(nombre, "sin sesión")
        horas = [a["horas"] for a in suyos if isinstance(a.get("horas"), (int, float))]
        avisa = any(x.get("id") == f"agente:{a.get('pid')}" for a in suyos for x in alertas)
        return fila_inicio(nombre, (f"{len(suyos)} procesos · " if len(suyos) > 1 else "") + "corriendo" +
                           (f" {hace_inicio(redondea(60 * max(horas)))}" if horas else ""), avisa)

    hoy = u["claude"]["hoy"] if u and u.get("claude") and u["claude"].get("disponible") else None
    return [
        sesion("Claude"),
        sesion("Codex"),
        fila_inicio("Claude hoy en la Pi", f"{hoy['mensajes']} mensajes" if hoy and hoy.get("mensajes") is not None else None),
        fila_inicio("Uso medido", hace_inicio(minutos_desde(u.get("momento"), ahora)) if u else None),
    ]


def filas_asistentes(b, propuestas):
    perfiles = list(b["perfiles"].items()) if b and b.get("perfiles") else None
    if perfiles:
        bots = []
        for ident, p in perfiles:
            activo = p["servicio"].get("ActiveState") if p.get("servicio") else None
            bots.append(fila_inicio((p.get("toml") or {}).get("nombre") or ident,
                                    ("activo" if activo == "active" else activo) if activo else None,
                                    bool(activo) and activo != "active"))
    else:
        bots = [fila_inicio("Bots", None)]
    deriva = ([d for d in b["deriva"] if not d.get("igual") and not d.get("mismos_valores")]
              if b and isinstance(b.get("deriva"), list) else None)
    return [
        *bots,
        fila_inicio("Propuestas", None if propuestas is None else
                    (f"{propuestas} por aplicar" if propuestas else "ninguna por aplicar"),
                    propuestas is not None and propuestas > 0),
        fila_inicio("Vault y desplegado", None if deriva is None else
                    (f"{len(deriva)} archivo(s) distintos" if deriva else "iguales"), bool(deriva)),
    ]


def filas_cuentas(b):
    m = b.get("margen") if b else None
    pagadas = ([c for c in (m["cuentas"].get(i) for i in m["orden"]) if c and c.get("pagada")]
               if m and isinstance(m.get("orden"), list) and m.get("cuentas") else None)
    mejor = m["cuentas"].get(m["con_margen"]) if m and m.get("con_margen") and m.get("cuentas") else None
    uso = b.get("uso_cuentas") if b else None
    return [
        fila_inicio("Con más margen", None if not m else (mejor["nombre"] if mejor else "ninguna bajo el umbral"),
                    bool(m) and not mejor),
        *([fila_inicio(c["nombre"], f"{redondea(c['libre_pct'])} % libre" if c.get("libre_pct") is not None else None,
                       bool(c.get("sobre"))) for c in pagadas]
          if pagadas is not None else [fila_inicio("Margen por cuenta", None)]),
        fila_inicio("Costo del mes", f"US$ {coma_inicio(uso['total_mes_usd'], 2)}"
                    if uso and uso.get("total_mes_usd") is not None else None),
    ]


def filas_luces(l):
    modos = {"arcoiris": "arcoíris", "respiracion": "respiración", "paleta": "paleta de colores",
             "fijo": "color fijo", "apagado": "apagadas"}
    sin_restaurar = bool(l) and bool(l.get("modo")) and not l.get("vigente")
    detenida = bool(l) and l.get("animacion_viva") is False
    modo = None if not l else ("apagadas tras el reinicio" if sin_restaurar else
                               "animación detenida" if detenida else modos.get(l.get("modo")) or l.get("modo"))
    movimiento = ((" y ".join(x for x in ("gira" if l.get("girar") else None,
                                          "respira" if l.get("respira") else None) if x) or "quieto")
                  if l and l.get("modo") else None)
    return [
        fila_inicio("Modo", modo, sin_restaurar or detenida),
        fila_inicio("Brillo", f"{l['brillo']} %" if l and l.get("brillo") is not None else None),
        fila_inicio("Movimiento", movimiento),
    ]


def filas_noticias(n, sin_votar):
    corridas = n.get("corridas") if n else None
    ultima = corridas["lista"][0] if corridas and isinstance(corridas.get("lista"), list) and corridas["lista"] else None
    caidas = None
    if ultima:
        try:
            ciegos = json.loads(ultima.get("ciegos") or "{}")
            caidas = ciegos["fuentes_caidas"] if isinstance(ciegos.get("fuentes_caidas"), list) else None
        except ValueError:
            caidas = None
    entrega = n["entregas"][0] if n and isinstance(n.get("entregas"), list) and n["entregas"] else None
    elegidos = entrega["elegidos"] if entrega and isinstance(entrega.get("elegidos"), list) else None
    pref = n.get("preferencias") if n else None
    turno = n["turnos"].get("noticias-seleccion") if n and n.get("turnos") else None
    return [
        fila_inicio("Última cosecha", f"{fecha_inicio(ultima['cuando'])} · {ultima['items']} ítems"
                    if ultima and fecha_inicio(ultima.get("cuando")) else None),
        fila_inicio("Nuevas hoy", corridas.get("nuevos_hoy") if corridas else None),
        fila_inicio("Fuentes caídas", None if caidas is None else
                    (f"{len(caidas)}: {', '.join(caidas)}" if caidas else "ninguna")),
        fila_inicio("Última entrega",
                    re.sub(r" - noticias - .*\.md$", "", str(entrega["archivo"])) +
                    f" · {len(elegidos)} elegidas · {sum(1 for x in elegidos if x.get('marcado'))} marcadas"
                    if elegidos is not None else None, sin_votar is not None and sin_votar > 0),
        fila_inicio("Votos", f"{pref['marcados']} de {pref['items']} entregadas"
                    if pref and pref.get("items") is not None and pref.get("marcados") is not None else None,
                    bool(pref) and (pref.get("items") or 0) > 0 and not pref.get("marcados")),
        fila_inicio("Próxima selección", turno.get("proximo") if turno else None),
    ]


def sin_votar(noticias):
    """barraNodo.sinVotar: las elegidas de la última entrega si ninguna tiene marca."""
    if not noticias or not isinstance(noticias.get("entregas"), list):
        return None
    if not noticias["entregas"]:
        return 0
    ultima = noticias["entregas"][0]
    if not isinstance(ultima.get("elegidos"), list):
        return None
    return 0 if any(n.get("marcado") for n in ultima["elegidos"]) else len(ultima["elegidos"])


def filas_encargos(e):
    if not e:
        return [fila_inicio("Cola", None)]
    con_barra = [c for c in e.get("colas") or [] if c["tipo"] == "barra"]
    return [fila_inicio("Cola", "corriendo" if e.get("viva") else "detenida" if e.get("detenida") else "nada corriendo",
                        bool(e.get("viva") or e.get("detenida"))),
            *[fila_inicio(c["cola"], f'{c["fase"] or c["estado"]} · ~{c["pct"]} % · termina ~{c["termina"]["esperado"]}', True)
              for c in con_barra]]


def filas_programados(p):
    """Espejo de filasProgramados (inicio.js): sin dato o sin problemas, None (no hay baldosa)."""
    if not p or p["fallo"] + p["vencido"] + p["huerfano"] == 0:
        return None
    return [fila_inicio("La última falló", p["fallo"], p["fallo"] > 0), fila_inicio("Vencidas", p["vencido"], p["vencido"] > 0),
            fila_inicio("Huérfanas", p["huerfano"], p["huerfano"] > 0), fila_inicio("Programadas en total", p["total"])]


def modelo_inicio(f, ahora=AHORA):
    def baldosa(ident, titulo, destino, forma, filas):
        return {"id": ident, "titulo": titulo, "destino": destino, "forma": forma, "filas": filas,
                "estado": punto_inicio(filas)}
    return [
        baldosa("sistema", "🍇 Raspberry Pi", "/sistema", "alta", filas_pi(f["estado"], ahora)),
        baldosa("nodo", "👾 IA Agents", "/nodo", "", filas_agentes(f["estado"], f["uso"], ahora)),
        baldosa("bots", "🤖 Asistentes", "/bots", "", filas_asistentes(f["bots"], f["propuestas"])),
        baldosa("cuentas", "💳 Cuentas", "/cuentas", "", filas_cuentas(f["bots"])),
        baldosa("encargos", "🧵 Encargos", "/encargos", "", filas_encargos(f["encargos"])),
        baldosa("luces", "🌈 Luces", "/luces", "", filas_luces(f["luces"])),
        *([baldosa("programados", "⏰ Programados", "/sistema", "", filas_programados(f.get("programados")))]
          if filas_programados(f.get("programados")) else []),
        baldosa("noticias", "📰 Noticias", "/noticias", "ancha", filas_noticias(f["noticias"], f["sinVotar"])),
    ]


# Qué baldosas dependen de cada fuente.
USA = {"estado": {"sistema", "nodo"}, "uso": {"nodo"}, "bots": {"bots", "cuentas"},
       "luces": {"luces"}, "noticias": {"noticias"}, "propuestas": {"bots"}, "encargos": {"encargos"}}


class InicioTests(unittest.TestCase):
    def setUp(self):
        self.js = leer(PAGINAS["sistema"] / "inicio.js")
        self.codigo = tokens_js(self.js, strings=True)
        self.sistema = tokens_js(leer(PAGINAS["sistema"] / "sistema.js"), strings=True)

    def fuentes(self, **cambios):
        noticias = cambios.get("noticias", noticias_real())
        f = {"estado": estado_real(), "uso": uso_real(), "bots": previas.SalidaReal.armar(self),
             "luces": luces_real(), "noticias": noticias, "propuestas": 0, "encargos": {"viva": False, "detenida": False},
             "programados": None}
        f.update(cambios)
        f["sinVotar"] = sin_votar(f["noticias"])
        return f

    def valores(self, modelo, ident):
        return {f["dato"]: f["valor"] for f in next(b for b in modelo if b["id"] == ident)["filas"]}

    def estados(self, modelo):
        return {b["id"]: b["estado"] for b in modelo}

    # -- la página --

    def test_inicio_es_la_pestana_que_abre(self):
        html = leer(PAGINAS["sistema"] / "index.html")
        botones = re.findall(r'<button data-p="(\w+)"( class="activa")?>', html)
        self.assertEqual(botones, [("inicio", ' class="activa"'), ("estado", ""), ("servicios", ""),
                                   ("respaldo", ""), ("programados", ""), ("turno", "")])
        paneles = re.findall(r'<section data-panel="(\w+)"( hidden)?></section>', html)
        self.assertEqual(paneles, [("inicio", ""), ("estado", " hidden"), ("servicios", " hidden"),
                                   ("respaldo", " hidden"), ("programados", " hidden"), ("turno", " hidden")])
        self.assertIn('let panelActual = "inicio";', self.sistema)
        arranque = self.sistema[self.sistema.index("cockpit.transport.wait("):]
        self.assertIn('mostrar("inicio");', arranque)
        self.assertIn("inicio: pintarInicio", self.sistema)
        # inicio.js va antes que sistema.js y no repite ningún nombre suyo.
        scripts = re.findall(r'<script src="([^"]+)"', html)
        self.assertEqual(scripts[-3:], ["inicio.js", "programados.js", "sistema.js"])
        propios = [declarados_arriba(leer(PAGINAS["sistema"] / f)) for f in ("inicio.js", "programados.js", "sistema.js")]
        self.assertFalse(propios[0] & propios[2])
        self.assertFalse(propios[1] & propios[2])
        self.assertFalse(propios[0] & propios[1])

    def test_el_bento_cabe_en_el_telefono_y_toda_baldosa_salta(self):
        reglas = reglas_css(leer(PAGINAS["sistema"] / "sistema.css"))
        de = lambda media, selector: [d for m, s, d in reglas if (m, s) == (media, selector)]
        # auto-fit: en el teléfono queda una sola columna; nada tiene un ancho fijo.
        self.assertEqual(de("", ".bento")[0]["grid-template-columns"], "repeat(auto-fit, minmax(280px, 1fr))")
        self.assertEqual(de("", ".baldosa.alta"), [{"grid-row": "span 2"}])          # 🍇
        self.assertEqual(de("", ".baldosa.ancha"), [{"grid-column": "1 / -1"}])      # 📰, a lo ancho
        self.assertEqual(de("(max-width: 640px)", ".baldosa.alta"), [{"grid-row": "auto"}])
        for media, selector, decl in reglas:
            if re.search(r"bento|baldosa|lista-estado", selector):
                for prop, valor in decl.items():
                    self.assertFalse(prop in ("width", "min-width") and valor.endswith("px"), selector)
                    self.assertFalse(prop == "white-space" and "nowrap" in valor, selector)
        self.assertEqual(de("", ".lista-estado dd")[0]["overflow-wrap"], "anywhere")
        # Las formas las pone el modelo: 🍇 alta, 📰 ancha y al final, las otras cuatro chicas.
        modelo = modelo_inicio(self.fuentes())
        self.assertEqual([(b["id"], b["forma"]) for b in modelo],
                         [("sistema", "alta"), ("nodo", ""), ("bots", ""), ("cuentas", ""), ("encargos", ""), ("luces", ""),
                          ("noticias", "ancha")])
        # ⏰ (encargo 22) sólo existe cuando algo falló, quedó vencido o huérfano; va antes de 📰.
        con_problemas = modelo_inicio(self.fuentes(programados={"total": 29, "fallo": 1, "vencido": 1, "huerfano": 0}))
        self.assertEqual([b["id"] for b in con_problemas],
                         ["sistema", "nodo", "bots", "cuentas", "encargos", "luces", "programados", "noticias"])
        en_js = re.findall(r'baldosa\("(\w+)", "([^"]+)", "(/\w+)", "(\w*)", filas(\w+)\(', self.codigo)
        self.assertEqual([(i, t, d, f) for i, t, d, f, _ in en_js],
                         [(b["id"], b["titulo"], b["destino"], b["forma"]) for b in con_problemas])
        self.assertEqual([t for i, t, _, _, _ in en_js if i != "programados"],
                         [("🧵 Encargos" if i == "encargos" else MENU[i][1]) for i, *_ in en_js if i != "programados"])
        # Toda baldosa salta a su página (🍇, que es esta, abre 📊 Estado), con toque o Enter.
        baldosa = tramo(self.sistema, "function baldosa(b) {")
        self.assertIn('const ir = () => (b.id === "sistema" ? mostrar("estado") : b.id === "programados" ? mostrar("programados") : cockpit.jump(b.destino));', baldosa)
        self.assertIn("onclick: ir", baldosa)
        self.assertIn('onkeydown: ev => { if (ev.key === "Enter") ir(); }', baldosa)
        self.assertIn('role: "link", tabindex: "0"', baldosa)
        # Punto en el título y filas «dato → valor».
        self.assertIn('el("span", { class: "punto" + (clase ? " " + clase : ""), title: titulo }), b.titulo', baldosa)
        self.assertIn('[el("dt", {}, f.dato), el("dd", { class: f.nivel }, f.valor)]', baldosa)
        puntos = tramo(self.sistema, "const PUNTO_INICIO = {")
        self.assertEqual(re.findall(r'(\w+): \["(\w*)"', puntos), [("ok", ""), ("ojo", "ojo"), ("gris", "gris")])
        base = {s: d for m, s, d in reglas_css(leer(COMUN / "base.css")) if not m}
        self.assertEqual((base[".punto"]["background"], base[".punto.ojo"]["background"], base[".punto.gris"]["background"]),
                         ("var(--ok)", "var(--ojo)", "var(--tenue)"))

    def test_solo_lee_fuentes_que_ya_existen(self):
        leer_fuentes = tramo(self.sistema, "async function leerFuentes() {")
        for fuente in ("oNada(leerEstado())", "oNada(cockpit.file(USO_JSON, { syntax: JSON }).read())",
                       "oNada(json(BOTS_INFO))", "oNada(json(LUCES))", "oNada(barraNodo.refrescar())"):
            self.assertIn(fuente, leer_fuentes, fuente)
        self.assertEqual(leer_fuentes.count("oNada("), 5)          # las cinco fuentes, y ninguna otra
        # La que falla o llega vacía queda en null: nunca un objeto vacío ni un 0.
        self.assertIn("const oNada = promesa => Promise.resolve(promesa).then(v => (v == null ? null : v), () => null);",
                      leer_fuentes)
        self.assertIn('const USO_JSON = "/opt/nodo/datos/uso.json";', self.sistema)
        self.assertIn('const ESTADO_JSON = "/opt/nodo/datos/estado.json";', self.sistema)
        self.assertIn('const BOTS_INFO = ["sudo", "-n", "/usr/local/bin/bots-info"];', self.sistema)
        self.assertIn('const LUCES = ["/home/dcifu004/.local/bin/luces", "estado"];', self.sistema)
        self.assertIn('const NOTICIAS = ["/usr/local/bin/noticias-cockpit", "estado"];',
                      tokens_js(leer(COMUN / "barra.js"), strings=True))
        # El modelo no lee nada: ni cockpit ni DOM.
        for fuera in ("cockpit", "document", "window", "fetch(", "barraNodo"):
            self.assertNotIn(fuera, self.codigo, fuera)

    # -- el modelo, con datos de la forma real --

    def test_con_todas_las_fuentes(self):
        modelo = modelo_inicio(self.fuentes())
        pi = self.valores(modelo, "sistema")
        self.assertEqual(pi["Servicios"], "16 arriba")                # 12 unidades y 4 contenedores
        self.assertEqual(pi["Temperatura"], "49,9 °C")
        self.assertEqual(pi["Ventilador"], "0 rpm · 0 %")             # un 0 que sí se leyó se muestra
        self.assertEqual(pi["Disco raíz"], "37 % usado")
        self.assertEqual(pi["Volumen cifrado"], "abierto · 1 % usado")
        self.assertEqual(pi["Respaldo"], "hace 14 h")
        self.assertEqual(pi["Disco de respaldo"], "montado")
        self.assertEqual(pi["Alertas"], "1: codex vivo hace 91 h (pid 1882744)")
        self.assertEqual(pi["Medido"], "hace 4 min")
        agentes = self.valores(modelo, "nodo")
        self.assertEqual(agentes, {"Claude": "sin sesión", "Codex": "corriendo hace 3 días",
                                   "Claude hoy en la Pi": "12 mensajes", "Uso medido": "hace 6 min"})
        bots = self.valores(modelo, "bots")
        self.assertEqual(bots["Propuestas"], "ninguna por aplicar")   # 0 leído, no «sin datos»
        self.assertEqual(bots["Vault y desplegado"].split(" ")[-1] in ("iguales", "distintos"), True)
        self.assertEqual(bots["Jaime"], "inactive")                   # la unidad detenida de la salida de prueba
        cuentas = self.valores(modelo, "cuentas")
        # Los nombres llegan de bots-info: son los del registro de cuentas.
        self.assertEqual(cuentas["Con más margen"], "Claude (Cami)")
        self.assertEqual((cuentas["Claude (Cami)"], cuentas["Claude (Diego)"], cuentas["Codex"]),
                         ("75 % libre", "3 % libre", "16 % libre"))
        self.assertTrue(cuentas["Costo del mes"].startswith("US$ "))
        self.assertNotIn("Groq", cuentas)                             # sin cuenta pagada: no tiene margen
        self.assertEqual(self.valores(modelo, "luces"), {"Modo": "arcoíris", "Brillo": "90 %", "Movimiento": "gira"})
        noticias = self.valores(modelo, "noticias")
        self.assertRegex(noticias["Última cosecha"], r"^\d\d-10 \d\d:05 · 2300 ítems$")
        self.assertEqual(noticias["Nuevas hoy"], "855")
        self.assertEqual(noticias["Fuentes caídas"], "3: elquintopoder, mercopress, lic")
        self.assertEqual(noticias["Última entrega"], "2026-10-03 1200 · 8 elegidas · 0 marcadas")
        self.assertEqual(noticias["Votos"], "0 de 198 entregadas")
        self.assertEqual(noticias["Próxima selección"], "Sat 2026-10-03 19:30:00 -03")
        # Los puntos: ámbar donde hay algo que mirar (alerta del agente, bots detenidos,
        # cuentas sobre el umbral, noticias sin votar); verde sólo en las luces.
        self.assertEqual(self.estados(modelo), {"sistema": "ojo", "nodo": "ojo", "bots": "ojo", "cuentas": "ojo",
                                                "encargos": "ok", "luces": "ok", "noticias": "ojo"})
        niveles = {f["dato"]: f["nivel"] for b in modelo for f in b["filas"]}
        self.assertEqual({d for d, n in niveles.items() if n == "ojo"},
                         {"Alertas", "Codex", "Jaime", "Pilar", "Claude (Diego)", "Última entrega", "Votos"}
                         | ({"Vault y desplegado"} if bots["Vault y desplegado"] != "iguales" else set()))
        self.assertNotIn(SIN_DATOS, [f["valor"] for b in modelo for f in b["filas"]])

    def test_todo_en_orden_da_verde(self):
        e = estado_real()
        e["alertas"] = []
        n = noticias_real()
        n["entregas"][0]["elegidos"][0]["marcado"] = True
        n["preferencias"]["marcados"] = 1
        bots = previas.SalidaReal.armar(self)
        for p in bots["perfiles"].values():
            p["servicio"]["ActiveState"] = "active"
        bots["deriva"] = [dict(d, igual=True) for d in bots["deriva"]]
        for c in bots["margen"]["cuentas"].values():
            c["sobre"] = False
        modelo = modelo_inicio(self.fuentes(estado=e, noticias=n, bots=bots))
        self.assertEqual(set(self.estados(modelo).values()), {"ok"})
        self.assertEqual(self.valores(modelo, "bots")["Jaime"], "activo")

    def test_una_fuente_ausente_da_sin_datos_nunca_cero_ni_verde(self):
        completo = modelo_inicio(self.fuentes())
        for fuente, afectadas in USA.items():
            with self.subTest(fuente):
                modelo = modelo_inicio(self.fuentes(**{fuente: None}))
                estados = self.estados(modelo)
                for b in modelo:
                    vacias = [f for f in b["filas"] if f["valor"] == SIN_DATOS]
                    if b["id"] in afectadas:
                        self.assertTrue(vacias, b["id"])
                        self.assertNotEqual(estados[b["id"]], "ok", b["id"])        # nunca verde
                        for f in vacias:
                            self.assertEqual(f["nivel"], "gris")
                    else:
                        # Lo que no depende de esa fuente queda igual.
                        self.assertEqual(b, next(x for x in completo if x["id"] == b["id"]))
        # Con el volumen cifrado cerrado no hay estado.json: 🍇 queda entera en «sin datos».
        modelo = modelo_inicio(self.fuentes(estado=None))
        pi = next(b for b in modelo if b["id"] == "sistema")
        self.assertEqual({f["valor"] for f in pi["filas"]}, {SIN_DATOS})
        self.assertEqual(pi["estado"], "gris")
        self.assertEqual(len(pi["filas"]), 9)           # las mismas filas: la baldosa no cambia de forma
        # Sin ninguna fuente: seis baldosas grises y ni un número.
        nada = modelo_inicio({"estado": None, "uso": None, "bots": None, "luces": None, "noticias": None,
                              "propuestas": None, "sinVotar": None, "encargos": None})
        self.assertEqual(set(self.estados(nada).values()), {"gris"})
        for b in nada:
            self.assertEqual({f["valor"] for f in b["filas"]}, {SIN_DATOS}, b["id"])
            self.assertEqual({f["nivel"] for f in b["filas"]}, {"gris"}, b["id"])
        self.assertIsNone(sin_votar(None))

    def test_un_campo_ausente_tampoco_se_inventa(self):
        # Fuentes que llegan, pero con un pedazo menos (un estado.py viejo, un bots-info viejo).
        e = estado_real()
        del e["ventilador"], e["respaldo"], e["alertas"]
        e["medidores"] = {}
        e["luks"] = None
        pi = self.valores(modelo_inicio(self.fuentes(estado=e)), "sistema")
        for dato in ("Temperatura", "Ventilador", "Disco raíz", "Volumen cifrado", "Respaldo",
                     "Disco de respaldo", "Alertas"):
            self.assertEqual(pi[dato], SIN_DATOS, dato)
        self.assertEqual(pi["Servicios"], "16 arriba")
        bots = previas.SalidaReal.armar(self)
        del bots["margen"], bots["uso_cuentas"]
        modelo = modelo_inicio(self.fuentes(bots=bots))
        self.assertEqual(self.valores(modelo, "cuentas"),
                         {"Con más margen": SIN_DATOS, "Margen por cuenta": SIN_DATOS, "Costo del mes": SIN_DATOS})
        self.assertEqual(self.estados(modelo)["cuentas"], "gris")
        # Una cuenta pagada sin medición: su fila dice «sin datos», no «0 % libre».
        bots = previas.SalidaReal.armar(self)
        for c in bots["margen"]["cuentas"].values():
            c["sobre"] = False
        bots["margen"]["cuentas"]["codex"]["libre_pct"] = None
        modelo = modelo_inicio(self.fuentes(bots=bots))
        self.assertEqual(self.valores(modelo, "cuentas")["Codex"], SIN_DATOS)
        self.assertEqual(self.estados(modelo)["cuentas"], "gris")
        # uso.json sin el bloque de Claude (`disponible: false`).
        u = uso_real()
        u["claude"] = {"disponible": False, "razon": "sin transcripts"}
        self.assertEqual(self.valores(modelo_inicio(self.fuentes(uso=u)), "nodo")["Claude hoy en la Pi"], SIN_DATOS)
        # Noticias con `ciegos` ilegible o sin entregas.
        n = noticias_real()
        n["corridas"]["lista"][0]["ciegos"] = "{roto"
        n["entregas"] = []
        noticias = self.valores(modelo_inicio(self.fuentes(noticias=n)), "noticias")
        self.assertEqual((noticias["Fuentes caídas"], noticias["Última entrega"]), (SIN_DATOS, SIN_DATOS))
        self.assertEqual(sin_votar(n), 0)

    def test_lo_que_avisa_queda_en_ambar(self):
        e = estado_real()
        e["alertas"] = []
        e["servicios"]["botv3@pilar"] = False
        e["contenedores"][0]["ok"] = False
        e["luks"]["abierto"] = False
        e["respaldo"]["montado"] = False
        e["medidores"]["temp_soc"]["v"] = 71.5
        e["momento"] = (AHORA - timedelta(hours=3)).replace(tzinfo=None).isoformat()
        modelo = modelo_inicio(self.fuentes(estado=e, propuestas=2))
        pi = next(b for b in modelo if b["id"] == "sistema")
        ambar = {f["dato"]: f["valor"] for f in pi["filas"] if f["nivel"] == "ojo"}
        self.assertEqual(ambar, {"Servicios": "2 caído(s): botv3@pilar, n8n", "Temperatura": "71,5 °C",
                                 "Volumen cifrado": "CERRADO", "Disco de respaldo": "no montado",
                                 "Medido": "hace 3 h"})          # estado.json viejo: el timer no corrió
        self.assertEqual(pi["estado"], "ojo")
        bots = next(b for b in modelo if b["id"] == "bots")
        self.assertIn({"dato": "Propuestas", "valor": "2 por aplicar", "nivel": "ojo"}, bots["filas"])
        # Luces: tras un reinicio sin restaurar, o con la animación detenida.
        apagadas = dict(luces_real(), vigente=False)
        self.assertEqual(filas_luces(apagadas)[0], {"dato": "Modo", "valor": "apagadas tras el reinicio", "nivel": "ojo"})
        self.assertEqual(filas_luces(dict(luces_real(), animacion_viva=False))[0]["nivel"], "ojo")
        # Noticias: con un voto en la última entrega deja de avisar esa fila.
        n = noticias_real()
        n["entregas"][0]["elegidos"][3]["marcado"] = True
        self.assertEqual(sin_votar(n), 0)
        self.assertEqual(sin_votar(noticias_real()), 8)
        self.assertEqual(filas_noticias(n, sin_votar(n))[3]["nivel"], "")

    # -- el espejo y el JS dicen lo mismo --

    def test_el_espejo_sigue_a_inicio_js(self):
        # 1. Las mismas filas, con los mismos rótulos y en el mismo orden.
        completo = modelo_inicio(self.fuentes())
        vacio = modelo_inicio({"estado": None, "uso": None, "bots": None, "luces": None, "noticias": None,
                               "propuestas": None, "sinVotar": None, "encargos": None})
        funciones = {"sistema": "function filasPi(e, ahora) {", "nodo": "function filasAgentes(e, u, ahora) {",
                     "bots": "function filasAsistentes(b, propuestas) {", "cuentas": "function filasCuentas(b) {",
                     "encargos": "function filasEncargos(q) {", "luces": "function filasLuces(l) {", "noticias": "function filasNoticias(n, sinVotar) {"}
        dinamicos = {"nodo": ["Claude", "Codex"], "bots": [], "cuentas": []}
        for ident, firma in funciones.items():
            cuerpo = tramo(self.codigo, firma)
            self.assertIsNotNone(cuerpo, firma)
            rotulos = re.findall(r'filaInicio\("([^"]+)"', cuerpo) + re.findall(r'sesion\("(\w+)"\)', cuerpo)
            del_espejo = {f["dato"] for b in (completo, vacio) for f in next(x for x in b if x["id"] == ident)["filas"]}
            with self.subTest(ident):
                # Los nombres de bots y cuentas llegan de bots-info: no están escritos en el JS.
                nombres = ({"Jaime", "Pilar"} if ident == "bots" else
                           {"Claude (Cami)", "Claude (Diego)", "Codex"} if ident == "cuentas" else set())
                self.assertEqual(set(rotulos), del_espejo - nombres)
                for nombre in nombres:
                    self.assertNotIn(f'"{nombre}"', cuerpo)
        # 2. La regla del punto y la de «sin datos», tal cual.
        self.assertIn('const falta = valor == null || valor === "" || (typeof valor === "number" && !Number.isFinite(valor));',
                      self.codigo)
        self.assertIn('return { dato, valor: falta ? SIN_DATOS : String(valor), nivel: falta ? "gris" : avisa ? "ojo" : "" };',
                      self.codigo)
        punto = tramo(self.codigo, "function puntoInicio(filas) {")
        self.assertIn('if (filas.some(f => f.nivel === "ojo")) return "ojo";', punto)
        self.assertIn('return !filas.length || filas.some(f => f.nivel === "gris") ? "gris" : "ok";', punto)
        self.assertIn("({ id, titulo, destino, forma, filas, estado: puntoInicio(filas) })", self.codigo)
        self.assertEqual(self.codigo.count('const SIN_DATOS = "sin datos";'), 1)
        # 3. Nada escribe «sin datos», «ok» ni una fila por fuera de esas dos funciones.
        self.assertEqual(self.codigo.count('"sin datos"'), 1)
        self.assertEqual(self.codigo.count('"ok"'), 1)
        self.assertEqual(self.codigo.count("{ dato,"), 1)
        self.assertEqual(self.codigo.count("estado:"), 1)
        # 4. Sin valores por defecto que conviertan una ausencia en un número.
        sin_strings = tokens_js(self.js)
        for inventa in (r"\|\|\s*0\b", r"\?\?\s*0\b", r"\|\|\s*\[\]", r"\|\|\s*\"\"\s*\)", r"Number\(\s*\w+\s*\)\s*\|\|",
                        r"parseInt|parseFloat", r"[?:]\s*0\s*[,);]"):
            self.assertIsNone(re.search(inventa, sin_strings), inventa)
        self.assertEqual(len(re.findall(r"\?\s*\{\}|\:\s*\{\}", sin_strings)), 1)      # sólo `medidores`, que es un mapa
        self.assertEqual(len(re.findall(r":\s*\[\];", sin_strings)), 1)                # y las alertas de 👾 (sólo colorean)
        # 5. El umbral de dato viejo es el mismo.
        self.assertIn("const ESTADO_VIEJO_MIN = 20;", self.codigo)
        self.assertIn("edad != null && edad > ESTADO_VIEJO_MIN", self.codigo)
        # 6. barraNodo.sinVotar hace lo que hace el espejo.
        votar = tramo(tokens_js(leer(COMUN / "barra.js"), strings=True), "function sinVotar(noticias) {")
        for linea in ("if (!noticias || !Array.isArray(noticias.entregas)) return null;", "if (!ultima) return 0;",
                      "if (!Array.isArray(ultima.elegidos)) return null;",
                      "return ultima.elegidos.some(n => n.marcado) ? 0 : ultima.elegidos.length;"):
            self.assertIn(linea, votar)

    def test_inicio_usa_solo_campos_que_las_fuentes_entregan(self):
        # Cada `<fuente>.<campo>` que lee inicio.js existe en la fuente con forma real.
        # (El espacio tras `${` separa las expresiones de una plantilla: el tokenizador
        # quita el texto de la plantilla y las dejaría pegadas.)
        codigo = tokens_js(self.js.replace("${", "${ "))
        bots = previas.SalidaReal.armar(self)
        e, u, n, l = estado_real(), uso_real(), noticias_real(), luces_real()
        margen = bots["margen"]
        cuenta = margen["cuentas"]["claude_diego"]
        perfil = bots["perfiles"]["jaime"]
        objetos = {
            "e": e, "u": u, "b": bots, "n": n, "l": l, "luks": e["luks"], "vent": e["ventilador"],
            "r": e["respaldo"], "temp": e["medidores"]["temp_soc"], "raiz": e["medidores"]["raiz"],
            "a": e["agentes"][0], "x": {**e["alertas"][0], **n["entregas"][0]["elegidos"][0]},
            "m": {**margen, **e["medidores"]}, "c": {**cuenta, **e["contenedores"][0]},
            # `mismos_valores` sólo viene en un .toml que difiere (bots-info.deriva): es opcional.
            "p": perfil, "d": {**bots["deriva"][0], "mismos_valores": None}, "uso": bots["uso_cuentas"],
            "hoy": u["claude"]["hoy"],
            "corridas": n["corridas"], "ultima": n["corridas"]["lista"][0], "entrega": n["entregas"][0],
            "pref": n["preferencias"], "turno": n["turnos"]["noticias-seleccion"],
            "ciegos": json.loads(n["corridas"]["lista"][0]["ciegos"]), "fuentes": self.fuentes(),
            "q": {"viva": False, "detenida": False, "colas": []}, "prog": programados_resumen(),
            "cola": modelo_cola(vivo_real("corriendo-rev1"), ESCRITO_VIVO + timedelta(minutes=2), True),
        }
        propios_de_js = {"length", "filter", "map", "some", "join", "concat", "replace", "toLowerCase",
                         "getTime", "getDate", "getMonth", "getHours", "getMinutes"}
        vistos = 0
        for nombre, objeto in objetos.items():
            usados = set(re.findall(rf"(?<![\w.]){re.escape(nombre)}\.([A-Za-z_]\w*)", codigo)) - propios_de_js
            with self.subTest(nombre):
                self.assertTrue(usados, nombre)
                self.assertFalse(usados - set(objeto), (nombre, usados - set(objeto)))
            vistos += len(usados)
        self.assertGreaterEqual(vistos, 50)
        # Los sub-objetos se sacan de donde dice el espejo.
        for trozo in ("e.ventilador", "e.luks", "e.respaldo", "m.temp_soc", "m.raiz", "u.claude.hoy", "b.margen",
                      "b.uso_cuentas", "n.corridas", "n.preferencias", 'n.turnos["noticias-seleccion"]',
                      "p.servicio.ActiveState", "p.toml.nombre", "alertas[0].texto", "m.cuentas[m.con_margen]"):
            self.assertIn(trozo, self.js, trozo)

    def test_las_formas_de_prueba_son_las_de_la_pi(self):
        # En la Pi se comparan con lo que hay de verdad (sólo lectura, sin sudo). En otro
        # equipo se salta y se dice.
        # Mapas cuya llave es un dato (una hora, un equipo), no un campo: se compara la
        # forma de sus valores contra la misma llave del real o, si no está, contra otra.
        por_dato = {"por_hora", "activos", "vencidos"}
        vistos = set()

        def dentro(prueba, real, donde):
            """Toda llave del dato de prueba existe en el real, con el mismo tipo de
            contenedor, a cualquier profundidad (revisión 18r1, hallazgo 2); de una lista
            se mira el primer elemento. Un `null` o una lista vacía, de cualquiera de los
            dos lados, no tiene forma que comparar."""
            vistos.add(donde)
            if prueba is None or real is None:
                return None
            if isinstance(prueba, dict):
                if not isinstance(real, dict):
                    return f"{donde} es un objeto en la prueba y {type(real).__name__} en el real"
                for k, v in prueba.items():
                    if donde.rsplit(".", 1)[-1] in por_dato:
                        if not real:
                            continue
                        molde = real[k] if k in real else next(iter(real.values()))
                    elif k not in real:
                        return f"{donde}.{k} no existe en el real"
                    else:
                        molde = real[k]
                    falla = dentro(v, molde, f"{donde}.{k}")
                    if falla:
                        return falla
            elif isinstance(prueba, list):
                if not isinstance(real, list):
                    return f"{donde} es una lista en la prueba y {type(real).__name__} en el real"
                if prueba and real:
                    return dentro(prueba[0], real[0], f"{donde}[]")
            elif isinstance(real, (dict, list)):
                return f"{donde} es {type(real).__name__} en el real y un valor suelto en la prueba"
            return None

        reales = {}
        try:
            reales["estado"] = json.loads(leer("/opt/nodo/datos/estado.json"))
            reales["uso"] = json.loads(leer("/opt/nodo/datos/uso.json"))
        except (OSError, ValueError):
            pass
        for nombre, orden in (("noticias", ["/usr/local/bin/noticias-cockpit", "estado"]),
                              ("luces", ["/home/dcifu004/.local/bin/luces", "estado"])):
            if os.access(orden[0], os.X_OK):
                try:
                    reales[nombre] = json.loads(subprocess.run(orden, capture_output=True, text=True, timeout=30).stdout)
                except (OSError, ValueError, subprocess.SubprocessError):
                    pass
        if len(reales) < 4:
            self.skipTest(f"no es la Pi o el volumen está cerrado: sólo pude leer {sorted(reales)}")
        pruebas = {"estado": estado_real(), "uso": uso_real(), "noticias": noticias_real(), "luces": luces_real()}
        for nombre, real in reales.items():
            with self.subTest(nombre):
                self.assertIsNone(dentro(pruebas[nombre], real, nombre))
        # Bajó de verdad: llegó a campos que están dos y tres niveles adentro.
        for hondo in ("estado.luks.pct", "estado.medidores.temp_soc.v", "estado.respaldo.horas",
                      "estado.contenedores[].ok", "uso.claude.hoy.mensajes",
                      "uso.cuentas_interactivo.claude_diego.limites.semanal.usado_pct",
                      "noticias.corridas.lista[].ciegos", "noticias.entregas[].elegidos[].marcado",
                      "noticias.turnos.noticias-seleccion.proximo", "luces.ventilador.rpm"):
            self.assertIn(hondo, vistos)
        # La prueba mide: un campo interno inventado, o un contenedor cambiado, se nota.
        inventado = estado_real()
        inventado["luks"]["inventado"] = 1
        self.assertEqual(dentro(inventado, reales["estado"], "estado"), "estado.luks.inventado no existe en el real")
        inventado = noticias_real()
        inventado["entregas"][0]["elegidos"][0]["inventado"] = 1
        self.assertEqual(dentro(inventado, reales["noticias"], "noticias"),
                         "noticias.entregas[].elegidos[].inventado no existe en el real")
        inventado = uso_real()
        inventado["cuentas_interactivo"]["claude_diego"]["por_hora"]["2026-10-01T20"]["inventado"] = 1
        self.assertIn("inventado no existe en el real", dentro(inventado, reales["uso"], "uso") or "")
        inventado = luces_real()
        inventado["ventilador"] = 1688
        self.assertIn("luces.ventilador es dict en el real", dentro(inventado, reales["luces"], "luces") or "")
        self.assertEqual(set(reales["estado"]["ventilador"] or {"rpm": 0, "pwm": 0, "pct": 0}), {"rpm", "pwm", "pct"})
        self.assertLessEqual({"agente", "pid", "horas"}, set((reales["estado"]["agentes"] or [estado_real()["agentes"][0]])[0]))
        self.assertLessEqual({"nombre", "ok"}, set(reales["estado"]["contenedores"][0]))
        self.assertLessEqual({"archivo", "elegidos"}, set(reales["noticias"]["entregas"][0]))

class EncargosTests(unittest.TestCase):
    """Espejo Python de los parseos puros de encargos.js, sin motor JS en la Pi.

    Los fixtures son copias inmutables de las formas reales del 03-10. No se leen los
    libros vivos: la cola puede escribir mientras corre una suite. Cada aserción queda
    además atada al fragmento equivalente de encargos.js.
    """

    CUENTAS = '''[claude_diego]
nombre = "Claude (Diego)"
[claude_cami]
nombre = "Claude (Cami)"
[codex]
nombre = "Codex"
'''
    COLA19 = '''nombre = "cola19"
esperar = ["cockpit18"]
[[etapa]]
id = "19"
autor = "codex"
revisor = "claude_cami"
'''
    COLA20 = '''nombre = "cola20"
esperar = ["cola19", "cockpit18"]
despliegue = "solo-avisar"
[paginas]
encargos = "cockpit-encargos"
[[etapa]]
id = "20"
autor = "codex"
revisor = "claude_cami"
'''
    ESTADO = '''## Cola cola20 (cola-run): 🧵 Encargos: ventana de las colas en Cockpit, sólo lectura (encargo 20, doc 28).

- 03-10 19:55 · Línea base de pruebas: 0 fallas previas
- 03-10 19:55 · 20: autor con Codex (pronóstico 6 min, +15 % 5 h, débil)
- 03-10 19:59 · 20: autor terminó en 4.5 min (rc 0)
- 03-10 19:59 · 20: rev1 con Claude (Cami) (pronóstico 5 min, +10 % 5 h, débil)
'''
    HISTORIAL = [
        {"encargo": "19", "fase": "autor", "rol": "autor", "cuenta": "codex", "inicio": "2026-10-03T18:20:35-03:00", "min": 4.5, "tokens": {"total": 134056}, "pct_5h": [0.0, 21.0], "pct_sem": [4.0, 7.0], "veredicto": None, "pronostico": {"min": 6}},
        {"encargo": "19", "fase": "rev1", "rol": "rev", "cuenta": "claude_cami", "inicio": "2026-10-03T18:25:02-03:00", "min": 3.3, "tokens": {"entrada": 30, "salida": 20380, "cache_lectura": 866430, "cache_escritura": 82777, "usd": 1.243222}, "pct_5h": [44.0, 44.0], "pct_sem": [56.0, 56.0], "veredicto": "DESPLEGABLE", "pronostico": {"min": 5}},
        {"encargo": "20", "fase": "autor", "rol": "autor", "cuenta": "codex", "inicio": "2026-10-03T19:55:13-03:00", "min": 4.5, "tokens": {"total": 156487}, "pct_5h": [22.0, 22.0], "pct_sem": [7.0, 7.0], "veredicto": None, "pronostico": {"min": 6}},
    ]

    @staticmethod
    def nombres(texto):
        salida, clave = {}, None
        for linea in texto.splitlines():
            seccion = re.match(r"^\[([^\]]+)\]", linea)
            if seccion:
                clave = seccion.group(1)
                salida[clave] = clave
            nombre = re.match(r'^nombre\s*=\s*"([^"]+)"', linea)
            if nombre and clave:
                salida[clave] = nombre.group(1)
        return salida

    @staticmethod
    def espera(texto):
        nombre = re.search(r'^nombre\s*=\s*"([^"]+)"', texto, re.M)
        lista = re.search(r'^esperar\s*=\s*\[([^\]]*)\]', texto, re.M)
        return None if not nombre else {"n": nombre.group(1), "a": re.findall(r'"([^"]+)"', lista.group(1) if lista else "")}

    @staticmethod
    def fase(texto, sesion):
        etapa = re.sub(r"^cola", "", sesion)
        patron = re.compile(rf"\b({re.escape(etapa)}): (autor|rev\d+|fix\d+) con .*?\(pronóstico (\d+(?:\.\d+)?) min", re.I)
        for linea in reversed(texto.splitlines()):
            dato = patron.search(linea)
            fecha = re.search(r"- (\d\d)-(\d\d) (\d\d:\d\d) ·", linea)
            if dato:
                return {"etapa": dato.group(1), "fase": dato.group(2), "inicio": f"2026-{fecha.group(2)}-{fecha.group(1)}T{fecha.group(3)}:00-03:00" if fecha else None, "pronostico": {"min": float(dato.group(3))}, "deducido": True}
        return {}

    @staticmethod
    def cuenta_fase(texto, etapa, fase):
        for bloque in texto.split("[[etapa]]")[1:]:
            dato = lambda clave: (re.search(rf'^{clave}\s*=\s*"([^"]+)"', bloque, re.M) or [None, None])[1]
            if dato("id") == str(etapa):
                return dato("revisor") if re.match(r"^rev", fase, re.I) else dato("autor")
        return None

    @staticmethod
    def tokens(tokens):
        return tokens.get("total", sum(tokens.get(k, 0) for k in ("entrada", "salida", "cache_lectura", "cache_escritura")))

    @staticmethod
    def vivo(sesiones):
        return None if not sesiones else {"cola": sesiones[0]}

    @staticmethod
    def val(valor):
        return "sin datos" if valor is None or valor == "" else str(valor)

    def test_formas_reales_de_cuentas_y_esperas(self):
        js = leer(PAGINAS["encargos"] / "encargos.js")
        self.assertIn(r'/^\[([^\]]+)\]/', js)
        self.assertIn(r'/^esperar\s*=\s*\[([^\]]*)\]/m', js)
        nombres = self.nombres(self.CUENTAS)
        self.assertEqual(nombres, {"claude_diego": "Claude (Diego)", "claude_cami": "Claude (Cami)", "codex": "Codex"})
        self.assertEqual(self.espera(self.COLA19), {"n": "cola19", "a": ["cockpit18"]})
        self.assertEqual(self.espera(self.COLA20), {"n": "cola20", "a": ["cola19", "cockpit18"]})

    def test_forma_real_de_cola_viva_deducida(self):
        js = leer(PAGINAS["encargos"] / "encargos.js")
        self.assertIn("pronostico: { min: Number(m[3]) }", js)
        self.assertIn("cuentaFase(v.etapa, v.fase)", js)
        viva = self.fase(self.ESTADO, "cola20")
        self.assertEqual(viva, {"etapa": "20", "fase": "rev1", "inicio": "2026-10-03T19:59:00-03:00", "pronostico": {"min": 5.0}, "deducido": True})
        cuenta = self.cuenta_fase(self.COLA20, viva["etapa"], viva["fase"])
        self.assertEqual(cuenta, "claude_cami")
        self.assertEqual(self.nombres(self.CUENTAS)[cuenta], "Claude (Cami)")
        uso = {"cuentas_interactivo": {"claude_cami": {"limites": {"ventana_5h": {"usado_pct": 50}, "semanal": {"usado_pct": 57}}}}}
        limites = uso["cuentas_interactivo"][cuenta]["limites"]
        self.assertEqual(f'5 h {limites["ventana_5h"]["usado_pct"]} % · semanal {limites["semanal"]["usado_pct"]} %', "5 h 50 % · semanal 57 %")
        self.assertEqual(self.fase(self.ESTADO, "cola21"), {})  # sesión viva sin línea propia: no inventa una fase

    def test_tokens_reales_excluyen_usd_y_el_autor_no_tiene_veredicto(self):
        js = leer(PAGINAS["encargos"] / "encargos.js")
        self.assertIn('["entrada", "salida", "cache_lectura", "cache_escritura"]', js)
        self.assertIn('x.rol === "rev" ? val(x.veredicto) : "—"', js)
        self.assertEqual(self.tokens(self.HISTORIAL[0]["tokens"]), 134056)
        self.assertEqual(self.tokens(self.HISTORIAL[1]["tokens"]), 969617)
        self.assertEqual(self.HISTORIAL[1]["tokens"]["usd"], 1.243222)
        self.assertIsNone(self.HISTORIAL[0]["veredicto"])

    def test_gantt_por_encargo_tiene_pronostico_y_aviso_historico(self):
        js = leer(PAGINAS["encargos"] / "encargos.js")
        self.assertIn("function agrupar(xs, clave)", js)
        self.assertIn('class: "pronostico"', js)
        self.assertGreaterEqual(js.count("El historial empieza en el encargo 19; los anteriores se ven sólo en la Bitácora."), 2)
        fases = [*self.HISTORIAL, {**self.HISTORIAL[2], "encargo": "21", "inicio": "2026-10-04T19:55:13-03:00"}]
        grupos = {}
        for fila in fases:
            grupos.setdefault(fila["encargo"], []).append(fila)
        # Cada tarjeta toma su propio rango: la primera fase de 20 no se aplasta por la 21.
        for filas in grupos.values():
            ini = min(datetime.fromisoformat(x["inicio"]) for x in filas)
            fin = max(datetime.fromisoformat(x["inicio"]) + timedelta(minutes=max(x["min"], x["pronostico"]["min"])) for x in filas)
            self.assertGreater((fin - ini).total_seconds(), 0)
        self.assertEqual(min(datetime.fromisoformat(x["inicio"]) for x in grupos["20"]), datetime.fromisoformat("2026-10-03T19:55:13-03:00"))

    def test_sin_cola_y_fuente_ausente_son_sin_datos(self):
        js = leer(PAGINAS["encargos"] / "encargos.js")
        self.assertIn("if (!s) return null;", js)
        self.assertIn("catch (e) { return null; }", js)
        self.assertIn('const val = x => x == null || x === "" ? "sin datos" : String(x);', js)
        self.assertIsNone(self.vivo([]))                 # sin sesión tmux: no hay cola viva
        self.assertEqual(self.val(None), "sin datos")   # archivo ausente/ilegible: nunca 0
        self.assertEqual(self.val(""), "sin datos")


def natural(s):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.findall(r"\d+|\D+", s)]


def fecha_corta(iso):
    m = re.match(r"^\d{4}-(\d\d)-(\d\d)T(\d\d:\d\d)", iso or "")
    return f"{m[2]}-{m[1]} {m[3]}" if m else "sin datos"


FIXTURES_ENCARGOS = PI / "fixtures" / "encargos"


class HistorialOrdenTests(unittest.TestCase):
    """Encargo 31: el Historial se ordena. Espejo en Python de ordenar() de encargos.js (en la Pi no hay
    motor de JS), atado al JS por texto. Las filas son REALES: copiadas de encargos/historial.jsonl a
    fixtures/encargos/historial-31.jsonl (no se lee el libro vivo; no se escribe en ningún archivo real)."""

    FILAS = [json.loads(x) for x in leer(FIXTURES_ENCARGOS / "historial-31.jsonl").splitlines() if x.strip()]
    FILAS_86 = [json.loads(x) for x in leer(FIXTURES_ENCARGOS / "historial-34.jsonl").splitlines() if x.strip()]
    NOMBRES = {"codex": "Codex", "claude_cami": "Claude (Cami)", "claude_diego": "Claude (Diego)"}

    def setUp(self):
        self.js = leer(PAGINAS["encargos"] / "encargos.js")
        self.tokens = tokens_js(self.js, strings=True)

    @classmethod
    def valor(cls, x, clave):
        if clave == "fecha":
            return datetime.fromisoformat(x["inicio"]).timestamp() if x.get("inicio") else None
        if clave == "encargo":
            return None if x.get("encargo") in (None, "") else natural(str(x["encargo"]))
        if clave == "cuenta":
            return cls.NOMBRES.get(x["cuenta"], "sin datos") if x.get("cuenta") else None
        if clave == "rol":
            return {"autor": 0, "rev": 1, "fix": 2, "plan": 3, "revplan": 4}.get(x.get("rol"))
        if clave == "min":
            return x["min"] if isinstance(x.get("min"), (int, float)) else None
        if clave == "tokens":
            t = x.get("tokens")
            if not isinstance(t, dict):
                return None
            if isinstance(t.get("total"), (int, float)):
                return t["total"]
            valores = [t.get(k) for k in ("entrada", "salida", "cache_lectura", "cache_escritura") if isinstance(t.get(k), (int, float))]
            return sum(valores) if valores else None
        if clave == "usd":
            usd = (x.get("tokens") or {}).get("usd")
            return usd if isinstance(usd, (int, float)) else None
        if clave in ("pct_5h", "pct_sem"):
            p = x.get(clave)
            return p[1] - p[0] if isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p) else None
        return {"DESPLEGABLE": 0, "NO DESPLEGABLE": 1}.get(x.get("veredicto")) if x.get("rol") == "rev" else None

    @classmethod
    def ordenar(cls, xs, clave, desc):
        con = [x for x in xs if cls.valor(x, clave) is not None]
        sin = [x for x in xs if cls.valor(x, clave) is None]
        return sorted(con, key=lambda x: cls.valor(x, clave), reverse=desc) + sin

    @staticmethod
    def ids(xs):
        return [f'{x["encargo"]}/{x["fase"]}' for x in xs]

    def test_el_orden_por_defecto_es_lo_mas_reciente_primero(self):
        self.assertIn('const orden = { clave: "fecha", desc: true };', self.js)
        self.assertIn('["fecha:desc", "Fecha (más reciente)"], ["fecha:asc", "Fecha (más antigua)"]', self.js)
        self.assertIn("ordenar(d.h.filter(", self.js)            # la tabla sale de ordenar(), no del orden del archivo
        self.assertEqual(self.ids(self.ordenar(self.FILAS, "fecha", True)),
                         ["27b/rev3", "26b/autor", "23d/autor", "22b/fix2", "20/autor", "19/rev1", "19/autor"])
        self.assertEqual(self.ids(self.ordenar(self.FILAS, "fecha", False)), self.ids(self.FILAS))   # el archivo va de lo viejo a lo nuevo

    def test_filas_sin_inicio_van_al_final_en_cualquier_sentido(self):
        sin = {**self.FILAS[0], "encargo": "99", "fase": "autor", "inicio": None}
        sin2 = {k: v for k, v in self.FILAS[1].items() if k != "inicio"} | {"encargo": "98"}
        mezcla = [sin, *self.FILAS, sin2]
        for desc in (True, False):
            ids = self.ids(self.ordenar(mezcla, "fecha", desc))
            self.assertEqual(ids[-2:], ["99/autor", "98/rev1"], desc)
            self.assertEqual(len(ids), len(mezcla))
        self.assertIn(".concat(sin)", self.js)                   # los sin dato se agregan después de ordenar, sin invertirse
        self.assertIn("Number.isNaN(t) ? null : t", self.js)     # inicio ausente o ilegible = sin dato

    def test_cada_columna_ordena_y_los_ids_con_letra_van_en_orden_natural(self):
        self.assertEqual(self.ids(self.ordenar(self.FILAS, "encargo", False))[:1], ["19/autor"])
        enc = [x["encargo"] for x in self.ordenar(self.FILAS, "encargo", False)]
        self.assertEqual(enc, ["19", "19", "20", "22b", "23d", "26b", "27b"])
        self.assertIn('{ numeric: true }', self.js)
        mins = [x["min"] for x in self.ordenar(self.FILAS, "min", True)]
        self.assertEqual(mins, sorted(mins, reverse=True))
        usd = [x["tokens"].get("usd") for x in self.ordenar(self.FILAS, "usd", True)]
        self.assertEqual(usd[:3], sorted([u for u in usd if u is not None], reverse=True)[:3])
        self.assertTrue(all(u is None for u in usd[3:]))         # sin USD (Codex): siempre al final
        cuentas = [self.NOMBRES[x["cuenta"]] for x in self.ordenar(self.FILAS, "cuenta", False)]
        self.assertEqual(cuentas, sorted(cuentas))

    def test_86_las_diez_columnas_y_los_dos_sentidos_cubren_las_cabezas(self):
        """C1/C2 86. Regla espejo de valorOrden(): roles en flujo; tokens como la celda; deltas después − antes;
        veredicto DESPLEGABLE, NO DESPLEGABLE y luego las filas sin dato. La muestra es una copia real, no el libro vivo."""
        cabezas = ["Fecha", "Encargo", "Cuenta", "Rol", "Min", "Tokens", "USD", "Δ 5 h", "Δ semanal", "Veredicto"]
        claves = ["fecha", "encargo", "cuenta", "rol", "min", "tokens", "usd", "pct_5h", "pct_sem", "veredicto"]
        self.assertEqual(re.findall(r'const COLUMNAS_ORDEN = \{ (.+) \};', self.js)[0].count(":"), len(cabezas))
        self.assertEqual(set(re.findall(r'\["([a-z0-9_]+):(asc|desc)",', self.js)), {(k, s) for k in claves for s in ("asc", "desc")})
        self.assertEqual([self.js.split('const CABEZAS_HISTORIAL = ')[1].split(';', 1)[0].count(f'"{h}"') for h in cabezas], [1] * len(cabezas))
        extremos = {
            ("fecha", False): ("19/autor", "23b/rev3"), ("fecha", True): ("23b/rev3", "19/autor"),
            ("encargo", False): ("19/autor", "23b/rev3"), ("encargo", True): ("23b/autor", "19/rev1"),
            ("cuenta", False): ("19/rev1", "23b/rev3"), ("cuenta", True): ("19/autor", "23b/fix2"),
            ("rol", False): ("19/autor", "23b/fix2"), ("rol", True): ("20/fix1", "23b/autor"),
            ("min", False): ("22/fix2", "23b/autor"), ("min", True): ("23b/autor", "22/fix2"),
            ("tokens", False): ("21/autor", "23b/autor"), ("tokens", True): ("23b/autor", "21/autor"),
            ("usd", False): ("22/fix2", "23b/rev3"), ("usd", True): ("23b/autor", "23b/rev3"),
            ("pct_5h", False): ("21/rev2", "23b/autor"), ("pct_5h", True): ("23b/autor", "21/rev2"),
            ("pct_sem", False): ("19/rev1", "23b/autor"), ("pct_sem", True): ("22c/autor", "23b/fix1"),
            ("veredicto", False): ("19/rev1", "23b/fix2"), ("veredicto", True): ("20/rev1", "23b/fix2"),
        }
        for (clave, desc), (primero, ultimo) in extremos.items():
            with self.subTest(clave=clave, desc=desc):
                ordenadas = self.ordenar(self.FILAS_86, clave, desc)
                self.assertEqual((self.ids(ordenadas)[0], self.ids(ordenadas)[-1]), (primero, ultimo))
                sin = [x for x in self.FILAS_86 if self.valor(x, clave) is None]
                self.assertEqual(self.ids(ordenadas[-len(sin):]) if sin else [], self.ids(sin))

    def test_encabezados_y_selector_comparten_el_mismo_estado(self):
        for clave in ("fecha", "encargo", "cuenta", "rol", "min", "tokens", "usd", "pct_5h", "pct_sem", "veredicto"):
            self.assertIn(f'{clave}:', self.js)
        self.assertIn('function cambiarOrden(clave, desc) { if (desc == null) { if (orden.clave === clave) orden.desc = !orden.desc;', self.js)   # clic repetido alterna
        self.assertIn('`${t} ${orden.desc ? "▼" : "▲"}`', self.js)                                                      # indicador en la activa
        self.assertIn('"aria-sort"', self.js)
        self.assertIn('o.value = `${orden.clave}:${orden.desc ? "desc" : "asc"}`;', self.js)                            # dib() sincroniza el selector
        self.assertIn('cambiarOrden(clave, sentido === "desc"); dib();', self.js)                                       # el selector mueve el mismo estado
        self.assertIn("el(\"div\", { class: \"encargo-filtros\" }, a, c, o)", self.js)                                   # junto a los filtros
        valores = set(re.findall(r'\["(\w+:(?:asc|desc))", "', self.js))
        self.assertEqual(valores, {f"{k}:{s}" for k in ("fecha", "encargo", "cuenta", "rol", "min", "tokens", "usd", "pct_5h", "pct_sem", "veredicto") for s in ("asc", "desc")})
        self.assertIn('"data-term": t === "Tokens" ? "Tokens" : null', self.js)

    def test_86_el_orden_actualiza_la_url_sin_disparar_hashchange(self):
        """El camino real de cambiarOrden conserva el alcance de Flow y usa replaceState: no reconstruye Traces ni pierde filtros."""
        node = next((x for x in ("node", "/home/dcifu004/.local/bin/node", str(Path.home() / ".local/bin/node")) if shutil.which(x) or Path(x).exists()), None)
        self.assertIsNotNone(node)
        script = r'''const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8");
const fn = src.match(/^function cambiarOrden.*$/m)[0];
const ctx = { URLSearchParams, location: { hash: "#/flujo?e=23b&c=claude_cami" }, panel: "flujo",
    orden: { clave: "fecha", desc: true }, hashchanges: 0,
    history: { replaceState: (_s, _t, h) => { ctx.location.hash = h; } } };
vm.runInNewContext(fn + "; globalThis.cambiarOrden = cambiarOrden;", ctx);
ctx.cambiarOrden("usd");
if (ctx.location.hash !== "#/flujo?e=23b&c=claude_cami&o=usd:desc" || ctx.hashchanges !== 0) process.exit(1);
process.stdout.write(ctx.location.hash);
'''
        salida = subprocess.run([node, "-e", script, str(PAGINAS["encargos"] / "encargos.js")], capture_output=True, text=True, check=True)
        self.assertEqual(salida.stdout, "#/flujo?e=23b&c=claude_cami&o=usd:desc")

    def test_primera_columna_fecha_corta_y_filtros_y_totales_intactos(self):
        self.assertIn('["Fecha", "Encargo", "Cuenta", "Rol", "Min", "Tokens", "USD", "Δ 5 h", "Δ semanal", "Veredicto"]', self.js)
        self.assertIn("el(\"td\", {}, fechaCorta(x.inicio)), el(\"td\", {}, x.encargo)", self.js)
        self.assertEqual(fecha_corta("2026-10-07T21:35:48-03:00"), "07-10 21:35")
        self.assertEqual(fecha_corta(None), "sin datos")
        self.assertEqual(fecha_corta("basura"), "sin datos")
        # Los totales por cuenta se calculan sobre todo d.h (no sobre lo filtrado ni lo ordenado), como antes.
        self.assertIn("agrupar(d.h, x => x.cuenta)", self.js)
        self.assertIn("(!a.value || x.encargo === a.value) && (!c.value || x.cuenta === c.value)", self.js)
        total = {}
        for x in self.FILAS:
            total[x["cuenta"]] = total.get(x["cuenta"], 0) + x["min"]
        for desc in (True, False):
            orden = self.ordenar(self.FILAS, "fecha", desc)
            self.assertEqual(sum(x["min"] for x in orden), sum(total.values()))

    def test_el_js_cierra_con_el_tokenizador_y_sin_style_inline(self):
        tokens_js(self.js)                                       # ValueError si algún ({[ queda sin cerrar
        self.assertNotIn("style=", self.js)
        self.assertNotIn('"style"', self.js)
        self.assertNotIn("style=", leer(PAGINAS["encargos"] / "index.html"))
        self.assertNotIn("style=", leer(PAGINAS["encargos"] / "encargos.css"))
        self.assertIn(".ordenable", leer(PAGINAS["encargos"] / "encargos.css"))

    def test_la_prueba_solo_lee_su_fixture(self):
        # El libro vivo del historial y los avisos del nodo no se abren ni se escriben.
        self.assertTrue(str(FIXTURES_ENCARGOS).startswith(str(PI)))
        self.assertEqual(len(self.FILAS), 7)


# ---- Encargo 22: ⏰ Programados y la barra de progreso de las colas ----
FIXTURES = PI / "fixtures"


def programados_real():
    """Una corrida real del recolector en esta Pi (03-10-2026), guardada tal cual."""
    return json.loads(leer(FIXTURES / "programados" / "salida-real.json"))


def programados_resumen():
    tareas = programados_real()["tareas"]
    cuenta = lambda e: sum(1 for t in tareas if t["estado"] == e)
    return {"total": len(tareas), "fallo": cuenta("fallo"), "vencido": cuenta("vencido"), "huerfano": cuenta("huerfano")}


def vivo_real(nombre):
    """encargos/vivo/<cola>.json generado con vivo() del propio cola-run.py (ver fixtures/vivo)."""
    return json.loads(leer(FIXTURES / "vivo" / f"{nombre}.json"))


ESCRITO_VIVO = datetime.fromisoformat(vivo_real("corriendo-rev1")["escrito"])
FINALES = ["terminada", "detenida", "pausada", "caída", "sin autorización"]
CON_BARRA = ["corriendo", "pruebas finales", "desplegando"]


def nombre_fase(f):
    m = re.fullmatch(r"(autor|rev|fix)(\d*)", f or "")
    if not m:
        return f or None
    return "autor" if m.group(1) == "autor" else f'{"revisión" if m.group(1) == "rev" else "arreglo"} {m.group(2)}'.strip()


def hora_local(iso):
    return datetime.fromisoformat(iso).strftime("%H:%M")      # el archivo trae la hora de la Pi (-03:00)


def hora_fecha(iso, ahora):
    """Espejo de horaFecha (barra.js): la hora, con el día si no es hoy."""
    d = datetime.fromisoformat(iso)
    hora = d.strftime("%H:%M")
    return hora if d.date() == ahora.astimezone(d.tzinfo).date() else f"{d:%d-%m} {hora}"


def veredicto_fase(v, i, historial=None):
    """Espejo de veredictoFase (barra.js)."""
    f = v["fases_hechas"][i]
    if not f["fase"].startswith("rev"):
        return None
    fila = [x for x in historial or [] if str(x["encargo"]) == str(f["etapa"]) and x["fase"] == f["fase"] and x.get("veredicto")]
    if fila:
        return "ok" if fila[-1]["veredicto"] == "DESPLEGABLE" else "mal"
    sigue = v["fases_hechas"][i + 1] if i + 1 < len(v["fases_hechas"]) else None
    if sigue and sigue["fase"].startswith("fix"):
        return "mal"
    if i == len(v["fases_hechas"]) - 1 and v["estado"] in ("terminada", "desplegando", "pruebas finales"):
        return "ok"
    if i == len(v["fases_hechas"]) - 1 and v["estado"] == "detenida":
        return "mal"
    return None


def modelo_cola(v, ahora, viva, historial=None):
    """Espejo de modeloCola (barra.js): lee sólo campos que vivo() de cola-run.py escribe."""
    escrito = datetime.fromisoformat(v["escrito"])
    final = v["estado"] in FINALES
    m = {"cola": v["nombre"], "estado": v["estado"], "cuenta": v.get("cuenta"), "modelo": v.get("modelo"),
         "fase": nombre_fase(v.get("fase")), "etapa": v.get("etapa"), "tipo": "sin_barra", "detalle": None, "pct": None,
         "fill": 0, "marcas": None, "termina": None, "fin": hora_local(v["fin"]) if v.get("fin") else None}
    m["segmentos"] = [{"fase": nombre_fase(f["fase"]), "cuenta": f["cuenta"], "min": f["min"], "pronostico": f["pronostico_min"],
                       "veredicto": veredicto_fase(v, i, historial)} for i, f in enumerate(v.get("fases_hechas") or [])]
    if v["estado"] == "corriendo" and v.get("fase"):
        m["segmentos"].append({"fase": nombre_fase(v["fase"]), "cuenta": v.get("cuenta"), "enCurso": True, "veredicto": None,
                               "min": max(0, (ahora - datetime.fromisoformat(v["inicio_fase"])).total_seconds() / 60),
                               "pronostico": v.get("pronostico_fase_min")})
    if not final and not viva and (ahora - escrito).total_seconds() > 2 * 3600:
        m["tipo"] = "sin_senal"
        m["detalle"] = f'sin señal desde las {hora_local(v["escrito"])}: la sesión ya no está viva'
        return m
    if final:
        m["tipo"] = "llena" if v["estado"] in ("terminada", "detenida") else "sin_barra"
        m["pct"] = 100 if m["tipo"] == "llena" else None
        m["detalle"] = (f'{v.get("motivo_pausa") or "pausada"}' + (f' · se reanuda desde {v["reanuda_desde"]}' if v.get("reanuda_desde") else "")
                        if v["estado"] == "pausada" else (v.get("error") or "caída") if v["estado"] == "caída"
                        else "no se autorizó el modelo: no corrió nada" if v["estado"] == "sin autorización" else None)
        return m
    if v["estado"] == "esperando":
        m["detalle"] = f'esperando a que termine «{v["esperando"]}»'
        return m
    if v["estado"] == "esperando autorización":
        m["detalle"] = "esperando autorización por Telegram" + (f' ({", ".join(v["candado"])})' if v.get("candado") else "")
        return m
    if v["estado"] == "esperando_cuota":
        m["tipo"], m["modelo"] = "espera_cuota", None
        m["espera"] = {"cuenta": v.get("cuenta"), "calculo": v.get("calculo_texto"),
                       "reanuda": hora_fecha(v["reanuda"], ahora) if v.get("reanuda") else None,
                       "termina": hora_fecha(v["eta"]["esperado"], ahora) if v.get("eta") else None,
                       "debil": bool(v.get("pronostico_debil"))}
        m["detalle"] = f'{m["espera"]["cuenta"] or "sin datos"}: {m["espera"]["calculo"] or "sin datos"}'
        return m
    e = v.get("eta")
    if v["estado"] in CON_BARRA and e and v.get("inicio_trabajo"):
        t0 = datetime.fromisoformat(v["inicio_trabajo"]).timestamp() * 1000
        mn, esp, mx = (datetime.fromisoformat(e[k]).timestamp() * 1000 for k in ("min", "esperado", "max"))
        ms = ahora.timestamp() * 1000
        span = max(1, max(mx, ms) - t0)
        m["tipo"] = "barra"
        m["fill"] = min(1, max(0, (ms - t0) / span))
        m["marcas"] = {"min": (mn - t0) / span, "esperado": (esp - t0) / span}
        m["pct"] = min(99, max(0, round(100 * (ms - t0) / max(1, max(esp, ms + 30000) - t0))))
        m["termina"] = {"esperado": hora_local(e["esperado"]), "min": hora_local(e["min"]), "max": hora_local(e["max"])}
        return m
    m["detalle"] = v["estado"]
    return m


class ColasVivasTests(unittest.TestCase):
    """Parte B del encargo 22: la barra de progreso de las colas. Los archivos de entrada son
    vivo/*.json REALES: los escribió vivo() de cola-run.py (fixtures/vivo); el modelo es el espejo
    de modeloCola (barra.js), atado al JS por texto, porque en la Pi no hay motor de JavaScript."""

    def setUp(self):
        self.barra = tokens_js(leer(COMUN / "barra.js"), strings=True)
        self.encargos = tokens_js(leer(PAGINAS["encargos"] / "encargos.js"), strings=True)

    def test_los_archivos_reales_traen_los_campos_que_la_pagina_lee(self):
        # Los campos que lee modeloCola: todos existen en lo que escribe vivo() (o son opcionales
        # de un estado: motivo_pausa, reanuda_desde, error, esperando, candado, fin, fases_hechas).
        cuerpo = tramo(self.barra, "function modeloCola(v, ahoraMs, viva, historial) {")
        leidos = set(re.findall(r"(?<![\w.])v\.([a-z_]+)", cuerpo + tramo(self.barra, "function veredictoFase(v, i, historial) {")))
        siempre = {"nombre", "estado", "escrito", "lanzada", "etapas", "motivo"}
        for nombre in ("corriendo-autor", "corriendo-rev1", "pausada", "terminada", "esperando", "esperando-cuota"):
            self.assertLessEqual(siempre, set(vivo_real(nombre)), nombre)
        union = set().union(*(set(vivo_real(n)) for n in ("corriendo-autor", "corriendo-rev1", "pausada", "terminada", "esperando", "esperando-cuota")))
        self.assertEqual(leidos - union - {"candado", "error"}, set(), "campos que ningún vivo() real trae")
        # candado y error los escribe vivo() en los estados de autorización y caída (cola-run.py).
        fuente = leer(PI.parent / "encargos" / "cola-run.py")
        for campo in ("candado=", "error="):
            self.assertIn(campo, fuente)
        # Lo que trae cada estado, tal como lo escribe cola-run.py.
        corriendo = vivo_real("corriendo-rev1")
        self.assertEqual(corriendo["estado"], "corriendo")
        self.assertEqual(set(corriendo["eta"]), {"esperado", "min", "max"})
        self.assertEqual(set(corriendo["restante_min"]), {"esperado", "min", "max"})
        self.assertEqual(set(corriendo["fases_hechas"][0]), {"etapa", "fase", "cuenta", "min", "pronostico_min"})
        self.assertIn("motivo_pausa", vivo_real("pausada"))
        self.assertIn("reanuda_desde", vivo_real("pausada"))
        self.assertEqual(vivo_real("terminada")["progreso_pct"], 100)
        self.assertEqual(vivo_real("esperando")["esperando"], "cola20")

    def test_corriendo_interpola_con_el_reloj_y_no_llega_a_100(self):
        v = vivo_real("corriendo-rev1")
        # inicio_trabajo y escrito coinciden en el archivo real; el reloj corre solo.
        inicio = datetime.fromisoformat(v["inicio_trabajo"])
        esperado = datetime.fromisoformat(v["eta"]["esperado"])
        previos = []
        for min_ in (0, 2, 4, 8):
            m = modelo_cola(v, inicio + timedelta(minutes=min_), True)
            self.assertEqual(m["tipo"], "barra")
            previos.append((m["fill"], m["pct"]))
        self.assertEqual([x[0] for x in previos], sorted(x[0] for x in previos))      # sólo avanza
        self.assertGreater(previos[-1][0], previos[0][0])
        # Pasado el ETA esperado y hasta el máximo, sigue por debajo de 100 %.
        tarde = modelo_cola(v, esperado + timedelta(minutes=30), True)
        self.assertEqual(tarde["tipo"], "barra")
        self.assertLessEqual(tarde["pct"], 99)
        self.assertLessEqual(tarde["fill"], 1)
        # Las marcas del ETA mínimo y del esperado quedan dentro de la pista y en orden.
        m = modelo_cola(v, inicio + timedelta(minutes=1), True)
        self.assertTrue(0 < m["marcas"]["min"] < m["marcas"]["esperado"] <= 1, m["marcas"])
        horas = m["termina"]
        self.assertEqual(horas, {"esperado": hora_local(v["eta"]["esperado"]), "min": hora_local(v["eta"]["min"]),
                                 "max": hora_local(v["eta"]["max"])})
        self.assertRegex(horas["esperado"], r"^\d\d:\d\d$")
        self.assertEqual((m["fase"], m["cuenta"], m["modelo"]), ("revisión 1", "Codex", "gpt-5.6-terra medium"))

    def test_segmentos_real_contra_pronostico_y_veredicto(self):
        v = vivo_real("corriendo-rev1")
        m = modelo_cola(v, datetime.fromisoformat(v["inicio_trabajo"]) + timedelta(minutes=3), True)
        self.assertEqual([(s["fase"], s["min"], s["pronostico"]) for s in m["segmentos"]],
                         [("autor", 14.2, 12), ("revisión 1", 3.0, 8)])
        self.assertTrue(m["segmentos"][1]["enCurso"])
        # El autor no tiene veredicto; una revisión seguida de un arreglo fue ❌; la última de una cola terminada, ✅.
        t = vivo_real("terminada")
        self.assertEqual([veredicto_fase(t, i) for i in range(3)], [None, None, "ok"])
        con_arreglo = dict(t, fases_hechas=[*t["fases_hechas"][:2], {**t["fases_hechas"][0], "fase": "fix1"}, t["fases_hechas"][2]])
        self.assertEqual([veredicto_fase(con_arreglo, i) for i in range(4)], [None, "mal", None, "ok"])
        # El historial manda sobre la deducción.
        hist = [{"encargo": "22", "fase": "rev2", "veredicto": "NO DESPLEGABLE"}]
        self.assertEqual(veredicto_fase(t, 2, hist), "mal")
        self.assertEqual(modelo_cola(t, ESCRITO_VIVO, False)["segmentos"][2]["veredicto"], "ok")

    def test_los_estados_sin_barra_dicen_su_motivo(self):
        p = modelo_cola(vivo_real("pausada"), ESCRITO_VIVO, False)
        self.assertEqual((p["tipo"], p["pct"]), ("sin_barra", None))
        self.assertIn("se quedó sin cuota a mitad de rev1", p["detalle"])
        self.assertIn("se reanuda desde 22:rev1", p["detalle"])
        e = modelo_cola(vivo_real("esperando"), ESCRITO_VIVO, True)
        self.assertEqual((e["tipo"], e["detalle"]), ("sin_barra", "esperando a que termine «cola20»"))
        caida = dict(vivo_real("terminada"), estado="caída", error="RuntimeError: x")
        self.assertEqual(modelo_cola(caida, ESCRITO_VIVO, False)["detalle"], "RuntimeError: x")
        sin = dict(vivo_real("terminada"), estado="sin autorización")
        self.assertIn("no se autorizó", modelo_cola(sin, ESCRITO_VIVO, False)["detalle"])
        # Esos estados no se pintan con barra, ni siquiera con un eta viejo en el archivo.
        for m in (p, e):
            self.assertIsNone(m["marcas"])

    def test_terminada_queda_llena_con_la_hora_de_fin(self):
        t = modelo_cola(vivo_real("terminada"), ESCRITO_VIVO + timedelta(hours=1), False)
        self.assertEqual((t["tipo"], t["pct"], t["fill"]), ("llena", 100, 0))   # la barra llena la pone el estado, no el fill
        self.assertEqual(t["fin"], hora_local(vivo_real("terminada")["fin"]))
        self.assertIn('fraccion(caja, "--fill", m.tipo === "llena" ? 1 : m.fill);', leer(PAGINAS["encargos"] / "encargos.js"))
        detenida = modelo_cola(dict(vivo_real("terminada"), estado="detenida"), ESCRITO_VIVO, False)
        self.assertEqual(detenida["tipo"], "llena")
        self.assertIn('m.estado === "terminada" ? "ok" : "mal"', leer(PAGINAS["encargos"] / "encargos.js"))   # detenida: llena y en rojo

    def test_sin_senal_si_escribio_hace_mas_de_2_h_y_la_sesion_no_vive(self):
        v = vivo_real("corriendo-rev1")
        viejo = ESCRITO_VIVO + timedelta(hours=2, minutes=1)
        self.assertEqual(modelo_cola(v, viejo, False)["tipo"], "sin_senal")
        self.assertIn("sin señal desde las", modelo_cola(v, viejo, False)["detalle"])
        self.assertEqual(modelo_cola(v, viejo, True)["tipo"], "barra")                      # la sesión sigue viva
        self.assertEqual(modelo_cola(v, ESCRITO_VIVO + timedelta(hours=1, minutes=59), False)["tipo"], "barra")
        # Un estado final no se vuelve «sin señal» con el tiempo.
        self.assertEqual(modelo_cola(vivo_real("terminada"), viejo, False)["tipo"], "llena")
        self.assertEqual(modelo_cola(vivo_real("pausada"), viejo, False)["tipo"], "sin_barra")

    def test_esperando_cuota_es_una_tarjeta_sin_la_barra_de_corriendo_con_el_calculo_la_hora_y_la_eta(self):
        v = vivo_real("esperando-cuota")
        ahora = datetime.fromisoformat(v["escrito"]) + timedelta(minutes=5)
        m = modelo_cola(v, ahora, True)
        self.assertEqual((m["tipo"], m["estado"], m["pct"], m["fill"], m["marcas"], m["termina"], m["modelo"]),
                         ("espera_cuota", "esperando_cuota", None, 0, None, None, None))
        self.assertEqual(m["espera"], {"cuenta": "Claude (Cami)", "calculo": "5 h 74 % + 25 % > tope 90 %", "reanuda": "20:32",
                                       "termina": hora_fecha(v["eta"]["esperado"], ahora), "debil": True})
        self.assertGreaterEqual(m["espera"]["termina"], m["espera"]["reanuda"])         # la ETA corrida por la espera
        self.assertEqual(m["detalle"], "Claude (Cami): 5 h 74 % + 25 % > tope 90 %")
        self.assertEqual(len(m["segmentos"]), len(v["fases_hechas"]))                   # ninguna fase «en curso»: no corre nada
        # No es un estado final ni de los que llevan barra: la tarjeta nunca dibuja la barra de «corriendo».
        self.assertNotIn("esperando_cuota", FINALES + CON_BARRA)
        self.assertIn('const FINALES = ["terminada", "detenida", "pausada", "caída", "sin autorización"];', self.barra)
        self.assertIn('const CON_BARRA = ["corriendo", "pruebas finales", "desplegando"];', self.barra)
        self.assertIn('if (v.estado === "esperando_cuota") {', self.barra)
        self.assertIn('m.tipo = "espera_cuota";', self.barra)
        self.assertIn('d.toDateString() === new Date(ahoraMs).toDateString() ? horaLocal(iso) : `${dia(d)} ${horaLocal(iso)}`', leer(COMUN / "barra.js"))
        js = leer(PAGINAS["encargos"] / "encargos.js")
        rama = js.split('} else if (m.tipo === "espera_cuota") {', 1)[1].split("} else {", 1)[0]
        self.assertNotIn("barraCola(", rama)
        self.assertIn('`${e.cuenta || "sin datos"}: ${e.calculo || "sin datos"}`', rama)
        self.assertIn('`Sigue ${e.reanuda.length > 5 ? "el" : "a las"} ${e.reanuda}.`', rama)
        self.assertIn('`Termina ~${e.termina}, con la espera incluida.`', rama)
        self.assertIn('espera_cuota: "Esperando cuota" }[m.tipo]', js)
        self.assertNotIn("calculo_texto", js)          # la página no arma el cálculo: lo dice cola-run.py
        # Lo que la tarjeta dice, con la forma del archivo real.
        e = m["espera"]
        self.assertEqual([f'{e["cuenta"]}: {e["calculo"]}', f'Sigue {"el" if len(e["reanuda"]) > 5 else "a las"} {e["reanuda"]}.'],
                         ["Claude (Cami): 5 h 74 % + 25 % > tope 90 %", "Sigue a las 20:32."])
        # Pasadas 2 h con la sesión viva no es «sin señal»; sin sesión sí.
        tarde = datetime.fromisoformat(v["escrito"]) + timedelta(hours=2, minutes=1)
        self.assertEqual((modelo_cola(v, tarde, True)["tipo"], modelo_cola(v, tarde, False)["tipo"]), ("espera_cuota", "sin_senal"))

    def test_el_espejo_sigue_a_barra_js(self):
        for linea in ('const SIN_SENAL_MS = 2 * 3600 * 1000;', 'const RECIENTE_MS = 12 * 3600 * 1000;',
                      'const FINALES = ["terminada", "detenida", "pausada", "caída", "sin autorización"];',
                      'const CON_BARRA = ["corriendo", "pruebas finales", "desplegando"];',
                      'if (!final && !viva && ahoraMs - m.escrito > SIN_SENAL_MS) {',
                      'm.fill = Math.min(1, Math.max(0, (ahoraMs - t0) / span));',
                      'm.pct = Math.min(99, Math.max(0, Math.round(100 * (ahoraMs - t0) / Math.max(1, Math.max(eEsp, ahoraMs + 30000) - t0))));',
                      'const fin = Math.max(eMax, ahoraMs), span = Math.max(1, fin - t0);',
                      'm.marcas = { min: (eMin - t0) / span, esperado: (eEsp - t0) / span };',
                      'm.tipo = ["terminada", "detenida"].includes(v.estado) ? "llena" : "sin_barra";'):
            self.assertIn(linea, self.barra, linea)
        # El tokenizador quita las regex: esta línea se mira en el texto crudo.
        self.assertIn('if (sigue && /^fix/.test(sigue.fase)) return "mal";', leer(COMUN / "barra.js"))
        # Lo reciente: sesión viva o escrito hace menos de 12 h.
        self.assertIn("sesiones.includes(v.nombre) || ahoraMs - Date.parse(v.escrito) < RECIENTE_MS", self.barra)
        # La página sólo dibuja: no recalcula nada del avance.
        self.assertNotIn("eta.", self.encargos)
        self.assertNotIn("progreso_pct", self.encargos)
        # Va también en la baldosa de 🏠 Inicio: lo dice el espejo de filasEncargos.
        e = {"viva": True, "detenida": False, "colas": [modelo_cola(vivo_real("corriendo-rev1"), ESCRITO_VIVO + timedelta(minutes=2), True)]}
        filas = filas_encargos(e)
        self.assertEqual([f["dato"] for f in filas], ["Cola", "cola22"])
        self.assertRegex(filas[1]["valor"], r"^revisión 1 · ~\d+ % · termina ~\d\d:\d\d$")
        self.assertEqual(filas[1]["nivel"], "ojo")
        self.assertEqual([f["dato"] for f in filas_encargos({"viva": False, "detenida": False, "colas": [modelo_cola(vivo_real("terminada"), ESCRITO_VIVO, False)]})], ["Cola"])

    def test_la_pagina_lee_los_vivos_con_comandos_fijos_y_sin_estilos_en_linea(self):
        js = tokens_js(leer(COMUN / "barra.js"), strings=True)
        self.assertIn('["find", VIVO_DIR, "-maxdepth", "1", "-name", "*.json"]', js)
        self.assertIn('const VIVO_DIR = ENCARGOS.slice(0, ENCARGOS.lastIndexOf("/")) + "/vivo";', js)
        # Un archivo ilegible o a medias se salta; sin carpeta, lista vacía.
        self.assertIn("try { return JSON.parse(await cockpit.file(ruta).read()); } catch (e) { return undefined; }", js)
        self.assertIn("return leidos.filter(v => v && v.nombre && v.estado);", js)
        # Los anchos van por CSSOM (--fill, --pos, --ancho); el CSS los consume.
        css = leer(PAGINAS["encargos"] / "encargos.css")
        for var in ("--fill", "--pos", "--ancho"):
            self.assertIn(f"var({var}", css)
            self.assertIn(f'"{var}"', self.encargos)
        # Se interpola cada 20 s sin releer, y se relee cada minuto.
        self.assertIn("20000", self.encargos)
        self.assertIn("60000", self.encargos)
        # Una cola de sesión vieja, sin vivo/<cola>.json, sigue saliendo «deducida» de la bitácora.
        self.assertIn("d.sesiones.find(x => !d.vivos.some(v => v.nombre === x))", self.encargos)


# ---- Encargo 23a: «⚙️ Reparto y modelos» en 🧵 Encargos, y el reparto en cola-run.py. ----
ENCARGOS_DIR = PI.parent / "encargos"
MEDIDA_FIJA = {"5h": 10.0, "sem": 20.0, "renueva_5h": None, "renueva_sem": None, "momento": None, "fuente": "fresco"}


def valor_config(a, b):
    """Espejo de valorConfig (encargos.js): la propuesta lleva solo lo que cambio."""
    v = {}
    for nat, roles in b["naturaleza"].items():
        for rol, nivel in roles.items():
            if nivel != a["naturaleza"][nat][rol]:
                v.setdefault("naturaleza", {}).setdefault(nat, {})[rol] = nivel
    for motor, tabla in b["niveles"].items():
        for nivel, x in tabla.items():
            y = a["niveles"][motor][nivel]
            if x["modelo"] != y["modelo"] or (x.get("esfuerzo") or "") != (y.get("esfuerzo") or ""):
                v.setdefault("niveles", {}).setdefault(motor, {})[nivel] = {"modelo": x["modelo"], "esfuerzo": x.get("esfuerzo") or ""}
    for nat, r in b["reparto"].items():
        for rol in ("autor", "revisor"):
            if r[rol] != a["reparto"][nat][rol]:
                v.setdefault("reparto", {}).setdefault(nat, {})[rol] = r[rol]
    if len(b["autorizacion"]["modelos"]) != len(a["autorizacion"]["modelos"]):
        v["autorizacion"] = {"modelos": b["autorizacion"]["modelos"]}
    for modelo, k in b["factor_modelo"].items():
        if k != a["factor_modelo"].get(modelo):
            v.setdefault("factor_modelo", {})[modelo] = k
    return v


class RepartoYModelosTests(unittest.TestCase):
    """cola-run.py corre de verdad (main(), con sys.argv), sobre una COPIA del modelos.toml real y
    una copia del historial; lo único fijo es la medición de cuota, que en vivo cambia a cada rato."""

    def setUp(self):
        import shutil
        import tempfile
        self.ap, self.modelos = previas.aplicar_encargos(self)
        self.tmp = self.modelos.parent
        shutil.copy(ENCARGOS_DIR / "historial.jsonl", self.tmp / "historial.jsonl")
        self.js = leer(PAGINAS["encargos"] / "encargos.js")

    def cola_run(self):
        """Un cola-run.py recién cargado (sin CFG_SIMULADA de otra corrida) que no toca nada vivo."""
        cr = previas._cargar(f"cola_run_{id(self)}", ENCARGOS_DIR / "cola-run.py")
        cr.MODELOS, cr.HISTORIAL, cr.ESTADO, cr.L = self.modelos, self.tmp / "historial.jsonl", self.tmp / "ESTADO.md", self.tmp
        cr.E = self.tmp      # vivo/<cola>.json y los prompts: si una regresión lanzara algo, no cae en la carpeta viva
        cr.medir = lambda cid: dict(MEDIDA_FIJA)
        cr.avisar = lambda *a, **k: self.fail("simular no avisa por Telegram")
        cr._AP_MOD = self.ap
        return cr

    def correr(self, *args, entrada=""):
        import contextlib
        import io
        from unittest import mock
        cr, salida, error = self.cola_run(), io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["cola-run.py", *map(str, args)]), mock.patch.object(sys, "stdin", io.StringIO(entrada)), \
                contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            try:
                rc = cr.main()
            except SystemExit as e:
                rc = e.code
        self.assertFalse((self.tmp / "ESTADO.md").exists(), "simular no escribe en la bitácora")
        self.assertFalse((self.tmp / "vivo").exists(), "simular no escribe el estado en vivo")
        return rc, salida.getvalue(), error.getvalue()

    def manifiesto(self, etapa, cabeza='nombre = "prueba"\n'):
        ruta = self.tmp / "prueba.toml"
        ruta.write_text(cabeza + "[[etapa]]\n" + etapa, encoding="utf-8")
        return ruta

    def test_la_cola_no_corre_con_el_default_si_modelos_toml_esta_vacio_o_roto(self):
        """Hallazgo 1 de 23ar1: un modelos.toml vacío (escritura en curso) se leía como {} y una
        etapa con autor y revisor corría con «default del CLI». Ahora se espera y, si sigue mal,
        la cola se detiene; sin archivo sigue siendo «sin configuración»."""
        from unittest import mock
        cr = self.cola_run()
        cr.time = mock.Mock()                      # sin esperar de verdad
        etapa = {"id": "1", "autor": "claude_cami", "revisor": "codex", "naturaleza": "bot"}
        bueno = self.modelos.read_text(encoding="utf-8")
        esperado = cr.modelo_de(etapa, "autor")
        self.assertTrue(esperado["modelo"] and esperado["nivel"] != "default del CLI")   # la forma real: no es el default
        for malo in ("", "  \n", "[niveles\n"):
            with self.subTest(malo=malo):
                self.modelos.write_text(malo, encoding="utf-8")
                with self.assertRaises(RuntimeError) as c:
                    cr.modelo_de(etapa, "autor")
                self.assertIn("no corro con el modelo por defecto", str(c.exception))
                with self.assertRaises(RuntimeError):
                    cr.repartir([{"id": "2", "naturaleza": "bot"}])
                with self.assertRaises(RuntimeError):
                    cr.modelos_con_candado([etapa])
        # Una escritura que termina durante los reintentos: lee el archivo nuevo, no el default.
        self.modelos.write_text("", encoding="utf-8")
        cr.time.sleep.side_effect = lambda s: self.modelos.write_text(bueno, encoding="utf-8")
        self.assertEqual(cr.modelo_de(etapa, "autor"), esperado)
        # Sin archivo no hay configuración (como antes).
        self.modelos.unlink()
        self.assertEqual(cr.modelo_de(etapa, "autor")["nivel"], "default del CLI")

    EJEMPLO_SIMULACION = PI.parents[2] / "90-Referencia" / "01-SkillsIA" / "encargar" / "ejemplo-simulacion.toml"

    def test_un_esfuerzo_sin_modelo_corre_con_el_modelo_de_la_naturaleza(self):
        """Encargo 48: el manifiesto real del experimento `esfuerzo-v1` declara solo `esfuerzo_autor`.
        Salía con el modelo vacío (default del CLI) y nivel «esfuerzo declarado»: el experimento
        comparaba modelos distintos además del esfuerzo."""
        import shutil
        import tomllib
        cr = self.cola_run()
        etapa = tomllib.loads(leer(self.EJEMPLO_SIMULACION))["etapa"][0]
        self.assertEqual((etapa["naturaleza"], etapa["esfuerzo_autor"]), ("pagina", "low"))
        self.assertNotIn("modelo_autor", etapa)
        cfg = tomllib.loads(self.modelos.read_text(encoding="utf-8"))
        nivel = cfg["naturaleza"]["pagina"]["autor"]
        de_la_naturaleza = cfg["niveles"]["claude"][nivel]
        self.assertTrue(de_la_naturaleza["modelo"])
        self.assertNotEqual(de_la_naturaleza["esfuerzo"], "low")      # si no, la prueba no distingue nada
        self.assertEqual(cr.modelo_de(etapa, "autor"),
                         {"modelo": de_la_naturaleza["modelo"], "esfuerzo": "low", "nivel": nivel})
        # El esfuerzo de un rol no toca los otros: rev y fix salen igual que sin `esfuerzo_autor`.
        sin = {k: v for k, v in etapa.items() if k != "esfuerzo_autor"}
        self.assertEqual(cr.modelo_de(sin, "autor"), dict(de_la_naturaleza, nivel=nivel))
        for rol in ("rev", "fix"):
            self.assertEqual(cr.modelo_de(etapa, rol), cr.modelo_de(sin, rol))
        # Y `--simular` sobre una copia del manifiesto real lo muestra así en la fila del autor (C1).
        rc, salida, error = self.correr(shutil.copy(self.EJEMPLO_SIMULACION, self.tmp), "--simular")
        self.assertEqual((rc, error), (0, ""))
        fila = next(x for x in salida.splitlines() if x.startswith("  autor "))
        self.assertIn(f" {de_la_naturaleza['modelo']} low ", fila)
        self.assertIn(f"[{nivel}]", fila)
        self.assertNotIn("esfuerzo declarado", salida)
        self.assertNotIn(" - low", fila)

    def test_un_esfuerzo_declarado_no_cambia_el_modelo_fijado_ni_inventa_uno(self):
        """Encargo 48, C3 a C5: `modelo_<rol>` sigue ganando; sin naturaleza el esfuerzo va con el
        default del CLI; y ningún `esfuerzo_*` cambia el modelo ni lo saca del candado."""
        cr = self.cola_run()
        base = {"id": "1", "autor": "claude_cami", "revisor": "codex"}
        fijada = dict(base, naturaleza="pagina", modelo_autor="claude-sonnet-5-5", esfuerzo_autor="low")
        self.assertEqual(cr.modelo_de(fijada, "autor"), {"modelo": "claude-sonnet-5-5", "esfuerzo": "low", "nivel": "fijado"})
        for sin_naturaleza in (dict(base, esfuerzo_autor="low"), dict(base, naturaleza="no-existe", esfuerzo_autor="low")):
            self.assertEqual(cr.modelo_de(sin_naturaleza, "autor"), {"modelo": "", "esfuerzo": "low", "nivel": "default del CLI"})
            self.assertEqual(cr.modelo_de(sin_naturaleza, "rev"), {"modelo": "", "esfuerzo": "", "nivel": "default del CLI"})
        for nat in ("seguridad", "diseno", "bot", "pagina", "investigacion", "menor"):
            for rol in ("autor", "rev", "fix"):
                with self.subTest(nat=nat, rol=rol):
                    sin = cr.modelo_de(dict(base, naturaleza=nat), rol)
                    con = cr.modelo_de(dict(base, naturaleza=nat, **{f"esfuerzo_{rol}": "low"}), rol)
                    self.assertEqual(con, dict(sin, esfuerzo="low"))
        # El candado mira el modelo, y el esfuerzo no lo esconde ni lo provoca.
        con_candado = dict(base, naturaleza="pagina", modelo_autor="claude-fable-5-1", esfuerzo_autor="low")
        self.assertEqual(cr.modelos_con_candado([con_candado]), {"claude-fable-5-1": ["1 autor"]})
        self.assertEqual(cr.modelos_con_candado([dict(base, naturaleza="pagina", esfuerzo_autor="low",
                                                      esfuerzo_rev="low", esfuerzo_fix="low")]), {})

    def test_simular_da_lo_mismo_antes_y_despues_de_una_propuesta_vacia(self):
        import contextlib
        import io
        manifiestos = [ENCARGOS_DIR / "cola-23.toml", ENCARGOS_DIR / "cola-22.toml", ENCARGOS_DIR / "ejemplo-reparto.toml"]
        antes = [self.correr(m, "--simular") for m in manifiestos]
        for rc, salida, error in antes:
            self.assertEqual((rc, error), (0, ""))
            self.assertIn("⏱️ Duración de la cola", salida)
        cfg = self.ap.valores(self.modelos.read_text(encoding="utf-8"))
        igual = {"naturaleza": cfg["naturaleza"], "niveles": cfg["niveles"], "reparto": cfg["reparto"],
                 "autorizacion": {"modelos": cfg["autorizacion"]["modelos"]}}
        original = self.modelos.read_bytes()
        for vacia in ({}, igual):
            with contextlib.redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit):
                self.ap.armar_plan("x", "encargos_config", vacia, "")
            self.assertIn("no cambia nada", error.getvalue())
        self.assertEqual(self.modelos.read_bytes(), original)
        self.assertEqual([self.correr(m, "--simular") for m in manifiestos], antes)
        # Y simular «con cambios» sin ningún cambio es la misma salida, letra por letra.
        for vacia in ("", "{}", json.dumps(igual)):
            self.assertEqual([self.correr(m, "--simular", "--con-cambios", entrada=vacia) for m in manifiestos], antes)

    def test_un_candado_puesto_a_mitad_de_cola_pide_autorizacion_antes_de_la_fase(self):
        """23a-1: al lanzar no hay candado; una propuesta pasa `normal` a un modelo con candado; la
        fase siguiente de la MISMA cola lo usaba sin pedir nada. Ahora etapa() lo pide antes de gastar."""
        from unittest import mock
        cr = self.cola_run()
        cr.MANIFIESTO = {"nombre": "prueba", "pruebas": []}
        etapa = {"id": "1", "autor": "claude_cami", "revisor": "codex", "naturaleza": "bot", "vueltas": 0}
        self.assertEqual(cr.modelos_con_candado([etapa]), {})           # al lanzar: nada que pedir
        cr.AUTORIZADOS.clear()
        texto = self.modelos.read_text(encoding="utf-8")
        viejo = 'normal  = { modelo = "claude-opus-5-5",   esfuerzo = "medium" }'
        self.assertEqual(texto.count(viejo), 1)
        self.modelos.write_text(texto.replace(viejo, 'normal  = { modelo = "claude-fable-5-1", esfuerzo = "high" }'), encoding="utf-8")
        class Salto(Exception):
            pass
        cr.chequear_cuota = mock.Mock(side_effect=Salto)                # lo primero que sigue al candado
        pedidos = []
        cr.pedir_autorizacion = lambda nom, usos: (pedidos.append((nom, usos)), False)[1]
        with self.assertRaises(cr.Pausa) as c:                          # sin ✅: pausa, y no gasta nada
            cr.etapa(etapa)
        self.assertEqual(pedidos, [("prueba", {"claude-fable-5-1": ["1 autor"]})])
        self.assertEqual(c.exception.desde, "1:autor")
        cr.chequear_cuota.assert_not_called()
        cr.pedir_autorizacion = lambda nom, usos: (pedidos.append((nom, usos)), True)[1]
        with self.assertRaises(Salto):                                  # con ✅: sigue a la cuota
            cr.etapa(etapa)
        self.assertEqual(len(pedidos), 2)
        with self.assertRaises(Salto):                                  # y no vuelve a preguntar por el mismo modelo
            cr.etapa(etapa)
        self.assertEqual(len(pedidos), 2)
        # Un modelo que ya se aprobó al lanzar no se pregunta de nuevo; uno sin candado, tampoco.
        cr.AUTORIZADOS.clear(); cr.AUTORIZADOS.add("claude-fable-5-1"); pedidos.clear()
        with self.assertRaises(Salto):
            cr.etapa(etapa)
        self.modelos.write_text(texto, encoding="utf-8")
        cr.AUTORIZADOS.clear()
        with self.assertRaises(Salto):
            cr.etapa(etapa)
        self.assertEqual(pedidos, [])

    def test_simular_con_modelos_toml_roto_solo_imprime(self):
        """23a-2: un modelos.toml ilegible hacía caer la simulación por `principal()`, que avisaba por
        Telegram, escribía la bitácora y pisaba vivo/<cola>.json. Ahora imprime el error y sale con 2."""
        import contextlib
        import io
        from unittest import mock
        cr = self.cola_run()
        cr.time = mock.Mock()
        avisos = []
        cr.avisar = lambda *a, **k: avisos.append(a)
        cr.subprocess = mock.Mock(side_effect=AssertionError("simular no llama a nodo-desplegar"))
        for malo in ("", "[niveles\n"):
            for extra in ([], ["--panel"]):
                with self.subTest(malo=malo, extra=extra):
                    self.modelos.write_text(malo, encoding="utf-8")
                    salida, error = io.StringIO(), io.StringIO()
                    args = ["cola-run.py", *(extra or [str(ENCARGOS_DIR / "cola-23.toml"), "--simular"])]
                    with mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
                        rc = cr.principal()
                    self.assertEqual(rc, 2)
                    self.assertIn("no corro con el modelo por defecto", error.getvalue())
                    self.assertEqual(avisos, [])
                    self.assertFalse((self.tmp / "ESTADO.md").exists())
                    self.assertFalse((self.tmp / "vivo").exists())
                    self.assertFalse((self.tmp / "avisos.log").exists())
                    cr.SIMULANDO = False
        # Sin simular, la misma caída sí avisa (el motor de las colas no cambia).
        self.modelos.write_text("", encoding="utf-8")
        cr.L.mkdir(exist_ok=True)
        with mock.patch.object(sys, "argv", ["cola-run.py", str(ENCARGOS_DIR / "cola-23.toml")]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(RuntimeError):
            cr.principal()
        self.assertEqual(len(avisos), 1)

    def test_los_manifiestos_que_ya_existen_no_cambian(self):
        import tomllib
        cr = self.cola_run()
        reales = sorted(ENCARGOS_DIR.glob("cola-*.toml"))
        self.assertGreaterEqual(len(reales), 7)
        for ruta in reales:
            etapas = tomllib.loads(leer(ruta))["etapa"]
            copia = json.loads(json.dumps(etapas))
            cr.repartir(etapas)
            with self.subTest(ruta.name):
                self.assertEqual(etapas, copia)      # ya traen autor y revisor: ni se tocan ni se marcan
        # La línea de una etapa con autor y revisor escritos sigue siendo la de siempre.
        rc, salida, _ = self.correr(ENCARGOS_DIR / "cola-23.toml", "--simular")
        self.assertEqual(salida.splitlines()[0], "23a · naturaleza: pagina")
        self.assertRegex(salida.splitlines()[1], r"^  autor Claude \(Cami\)   claude-opus-5-5 medium   \[normal\] +[\d.]+ min  "
                         r"\+[\d.]+ % 5 h \(p75 [\d.]+ %; ahora 10.0, tope \d+\)  \+[\d.]+ % sem \(ahora 20.0, tope \d+\)  fresco")
        self.assertNotIn("[reparto.", salida)
        self.assertNotIn("✏️", salida)

    def test_sin_autor_se_usa_el_reparto_de_la_naturaleza(self):
        rc, salida, error = self.correr(self.manifiesto('id = "1"\nencargo = "x.md"\nnaturaleza = "bot"\n'), "--simular")
        self.assertEqual((rc, error), (0, ""))
        lineas = salida.splitlines()
        self.assertEqual(lineas[0], "1 · naturaleza: bot · autor y revisor por [reparto.bot]")
        self.assertRegex(lineas[1], r"^  autor Claude \(Cami\) +claude-opus-5-5 medium +\[normal\]")
        self.assertRegex(lineas[2], r"^  rev   Codex +gpt-5.6-terra high +\[fuerte\]")
        # Solo falta el revisor: se sugiere ese y el autor escrito se respeta.
        rc, salida, _ = self.correr(self.manifiesto('id = "1"\nautor = "claude_diego"\nnaturaleza = "bot"\n'), "--simular")
        self.assertEqual(salida.splitlines()[0], "1 · naturaleza: bot · revisor por [reparto.bot]")
        self.assertRegex(salida.splitlines()[1], r"^  autor Claude \(Diego\) ")
        self.assertRegex(salida.splitlines()[2], r"^  rev   Codex ")

    def test_el_reparto_sugerido_nunca_deja_autor_igual_a_revisor(self):
        casos = {
            # el autor escrito es justo el revisor sugerido
            'id = "1"\nautor = "codex"\nnaturaleza = "bot"\n': "autor y revisor serían la misma cuenta (codex)",
            # ni con `autorrevision`: esa excepción es para un manifiesto que escribe los dos
            'id = "1"\nautor = "codex"\nnaturaleza = "bot"\nautorrevision = "usuario, 04-10"\n': "el reparto sugerido nunca lo acepta",
            'id = "1"\nrevisor = "claude_cami"\nnaturaleza = "bot"\n': "autor y revisor serían la misma cuenta (claude_cami)",
            # sin naturaleza, o con una que no tiene tabla, no hay de dónde sugerir
            'id = "1"\nencargo = "x.md"\n': "no trae `autor` y modelos.toml no lo sugiere en [reparto.(sin naturaleza)]",
            'id = "1"\nnaturaleza = "otra"\n': "modelos.toml no lo sugiere en [reparto.otra]",
        }
        for etapa, motivo in casos.items():
            with self.subTest(etapa=etapa):
                rc, salida, error = self.correr(self.manifiesto(etapa), "--simular")
                self.assertEqual((rc, salida), (2, ""))
                self.assertIn(motivo, error)
        # Un modelos.toml editado a mano con la misma cuenta en los dos lados tampoco pasa.
        texto = self.modelos.read_text(encoding="utf-8")
        roto = texto.replace('[reparto.bot]\nautor   = "claude_cami"', '[reparto.bot]\nautor   = "codex"', 1)
        self.assertNotEqual(roto, texto)
        self.modelos.write_text(roto, encoding="utf-8")
        rc, salida, error = self.correr(self.manifiesto('id = "1"\nnaturaleza = "bot"\n'), "--simular")
        self.assertEqual(rc, 2)
        self.assertIn("serían la misma cuenta (codex)", error)
        # Fuera de simular el mismo error detiene la cola antes de correr nada (y ahí sí avisa).
        cr = self.cola_run()
        from unittest import mock
        with mock.patch.object(sys, "argv", ["cola-run.py", str(self.manifiesto('id = "1"\nnaturaleza = "bot"\n'))]), \
                self.assertRaisesRegex(SystemExit, "serían la misma cuenta"):
            cr.main()
        self.assertFalse((self.tmp / "ESTADO.md").exists())
        # Lo que ya se podía sigue pudiéndose: los dos escritos e iguales, con `autorrevision`.
        etapas = [{"id": "1", "autor": "codex", "revisor": "codex", "autorrevision": "usuario, 04-10", "naturaleza": "bot"}]
        cr.repartir(etapas)
        self.assertNotIn("reparto_sugerido", etapas[0])

    def test_el_manifiesto_de_ejemplo_solo_se_simula_y_cubre_todas_las_naturalezas(self):
        import fnmatch
        import tomllib
        ejemplo = tomllib.loads(leer(ENCARGOS_DIR / "ejemplo-reparto.toml"))
        cfg = tomllib.loads(leer(FIXTURES / "encargos" / "modelos.toml"))      # copia fija: no el vivo
        self.assertEqual([e["naturaleza"] for e in ejemplo["etapa"]], list(cfg["naturaleza"]))
        self.assertFalse(any("autor" in e or "revisor" in e for e in ejemplo["etapa"]))
        self.assertIs(ejemplo["solo_simular"], True)
        # La página lista las colas con `find -name cola-*.toml`: el ejemplo no es una cola.
        self.assertIn('"-name", "cola-*.toml"', self.js)
        self.assertFalse(fnmatch.fnmatch("ejemplo-reparto.toml", "cola-*.toml"))
        rc, salida, error = self.correr(ENCARGOS_DIR / "ejemplo-reparto.toml")      # sin --simular
        self.assertEqual((rc, salida), (2, ""))
        self.assertIn("solo corre con --simular", error)
        rc, salida, error = self.correr(ENCARGOS_DIR / "ejemplo-reparto.toml", "--simular")
        self.assertEqual(rc, 0)
        self.assertEqual(sum(1 for l in salida.splitlines() if "por [reparto." in l), len(cfg["naturaleza"]))
        self.assertNotIn("default del CLI", salida)

    def test_simular_con_cambios_muestra_el_efecto_y_rechaza_lo_que_se_rechazaria(self):
        ejemplo = ENCARGOS_DIR / "ejemplo-reparto.toml"
        original = self.modelos.read_bytes()
        valor = {"naturaleza": {"menor": {"autor": "agil"}}, "reparto": {"bot": {"autor": "codex", "revisor": "claude_diego"}},
                 "niveles": {"codex": {"normal": {"modelo": "gpt-5.6-luna", "esfuerzo": "high"}}}}
        rc, salida, error = self.correr(ejemplo, "--simular", "--con-cambios", entrada=json.dumps(valor))
        self.assertEqual((rc, error), (0, ""))
        bloque = lambda nat: salida[salida.index(f"\n{nat} · "):].splitlines()[1:5]
        self.assertRegex(bloque("bot")[1], r"^  autor Codex +gpt-5.6-luna high +\[normal\]")
        self.assertRegex(bloque("bot")[2], r"^  rev   Claude \(Diego\) +claude-opus-5-5 high +\[fuerte\]")
        self.assertRegex(bloque("menor")[1], r"^  autor Claude \(Cami\) +claude-sonnet-5-5 medium +\[agil\]")
        self.assertEqual([l for l in salida.splitlines() if l.startswith("✏️")],
                         ["✏️ sin aplicar · niveles.codex.normal: gpt-5.6-terra medium → gpt-5.6-luna high",
                          "✏️ sin aplicar · naturaleza.menor.autor: liviano → agil",
                          "✏️ sin aplicar · reparto.bot.autor: claude_cami → codex",
                          "✏️ sin aplicar · reparto.bot.revisor: codex → claude_diego"])
        # Un modelo con candado se ve con 🔒 antes de proponer.
        fable = {"niveles": {"claude": {"maximo": {"modelo": "claude-fable-5-1", "esfuerzo": "high"}}}}
        rc, salida, _ = self.correr(ejemplo, "--simular", "--con-cambios", entrada=json.dumps(fable))
        self.assertIn("🔒 claude-fable-5-1 pide autorización por Telegram al lanzar (diseno autor)", salida)
        # Lo que aplicar-propuesta rechazaría, la simulación también: mismo mensaje, código 1, sin salida.
        for malo, motivo in (({"reparto": {"bot": {"autor": "codex"}}}, "autor y revisor serian la misma cuenta"),
                             ({"niveles": {"codex": {"agil": {"modelo": "gpt-7", "esfuerzo": ""}}}}, "el modelo 'gpt-7' no existe"),
                             ({"autorizacion": {"modelos": []}}, "Quitar un candado no se hace desde la pagina")):
            with self.subTest(malo=malo):
                rc, salida, error = self.correr(ejemplo, "--simular", "--con-cambios", entrada=json.dumps(malo))
                self.assertEqual((rc, salida), (1, ""))
                self.assertIn(motivo, error)
        self.assertEqual(self.modelos.read_bytes(), original)     # simular nunca escribe modelos.toml
        # --con-cambios es solo de la simulación: una cola real no puede correr con una configuración sin aplicar.
        rc, salida, error = self.correr(ejemplo, "--con-cambios", entrada="{}")
        self.assertEqual(rc, 2)
        self.assertIn("--con-cambios solo va con --simular", error)

    def test_panel_entrega_lo_que_la_pestana_dibuja(self):
        rc, salida, error = self.correr("--panel")
        self.assertEqual((rc, error), (0, ""))
        panel = json.loads(salida)
        self.assertEqual(set(panel), {"modelos", "catalogo", "cuentas", "pronosticos", "reglas", "colas_fuera", "capacidad_por_vencer", "momento", "colas", "despacho", "pasado"})
        self.assertEqual(panel["modelos"], self.ap.valores(self.modelos.read_text(encoding="utf-8")))
        self.assertEqual({c: v["nombre"] for c, v in panel["cuentas"].items()},
                         {"claude_cami": "Claude (Cami)", "claude_diego": "Claude (Diego)", "codex": "Codex"})
        self.assertEqual(panel["catalogo"], self.ap.catalogo_modelos(panel["modelos"]))
        # Los campos que lee la página existen en esa salida.
        for campo in ("cfg.modelos", "cfg.catalogo", "cfg.cuentas", "a.niveles", "m.naturaleza", "m.reparto",
                      "m.autorizacion.modelos", "m.autorizacion.patrones", "m.autorizacion.espera_max_min"):
            self.assertIn(campo, self.js)
        self.assertEqual(set(panel["modelos"]["autorizacion"]), {"modelos", "patrones", "espera_max_min"})
        # Las cuentas del reparto son las que cola-run sabe correr y las que acepta la propuesta.
        self.assertEqual(set(panel["cuentas"]), set(self.ap.PAGADAS))

    def test_la_propuesta_que_arma_la_pagina_es_la_que_acepta_aplicar_propuesta(self):
        # El espejo sigue a valorConfig.
        cuerpo = tramo(self.js, "function valorConfig(a, b) {")
        for linea in ('if (nivel !== a.naturaleza[nat][rol]) pon("naturaleza", nat, rol, nivel);',
                      'if (x.modelo !== y.modelo || (x.esfuerzo || "") !== (y.esfuerzo || "")) pon("niveles", motor, nivel, { modelo: x.modelo, esfuerzo: x.esfuerzo || "" });',
                      'for (const rol of ["autor", "revisor"]) if (r[rol] !== a.reparto[nat][rol]) pon("reparto", nat, rol, r[rol]);',
                      "if (b.autorizacion.modelos.length !== a.autorizacion.modelos.length) v.autorizacion = { modelos: b.autorizacion.modelos };",
                      "for (const [modelo, k] of Object.entries(b.factor_modelo)) if (k !== a.factor_modelo[modelo]) (v.factor_modelo ||= {})[modelo] = k;"):
            self.assertIn(linea, cuerpo)
        a = json.loads(self.correr("--panel")[1])["modelos"]
        self.assertEqual(valor_config(a, json.loads(json.dumps(a))), {})        # sin tocar nada no hay propuesta
        b = json.loads(json.dumps(a))
        b["naturaleza"]["pagina"]["fix"] = "normal"
        b["niveles"]["claude"]["agil"] = {"modelo": "claude-haiku-4-5", "esfuerzo": ""}
        b["reparto"]["menor"] = {"autor": "codex", "revisor": "claude_cami"}
        b["autorizacion"]["modelos"] = [*b["autorizacion"]["modelos"], "gpt-5.6-sol"]
        b["factor_modelo"]["claude-haiku-4-5"] = 0.3
        b["factor_modelo"]["gpt-5.6-luna"] = 0.4
        valor = valor_config(a, b)
        self.assertEqual(valor, {"naturaleza": {"pagina": {"fix": "normal"}},
                                 "niveles": {"claude": {"agil": {"modelo": "claude-haiku-4-5", "esfuerzo": ""}}},
                                 "reparto": {"menor": {"autor": "codex", "revisor": "claude_cami"}},
                                 "autorizacion": {"modelos": ["claude-fable-5-1", "gpt-6-astra", "gpt-5.6-sol"]},
                                 "factor_modelo": {"claude-haiku-4-5": 0.3, "gpt-5.6-luna": 0.4}})
        archivos, efecto, *_ = self.ap.armar_plan("x", "encargos_config", valor, "desde la página")
        self.assertEqual(self.ap.valores(archivos[0].nuevo), b)
        # La página propone con proponer() de comun.js, como 💳, y con un perfil válido de bots-info.
        self.assertIn('proponer({ tipo: "encargos_config", valor, clave: "modelos.toml",', self.js)
        self.assertIn("perfilPropuesta = (botsInfo && botsInfo.perfiles && Object.keys(botsInfo.perfiles)[0]) || null;", self.js)
        self.assertIn("disabled: !hay || rotas.length > 0 || rotos.length > 0 || !perfilPropuesta", self.js)
        comun = leer(COMUN / "comun.js")
        self.assertIn('if (tipo === "encargos_config" && valor && typeof valor === "object") {', comun)
        self.assertIn('cambio.tipo === "encargos_config" ? "Propuesta para el reparto y los modelos de los encargos"', comun)

    def test_el_factor_de_cada_modelo_se_edita_en_la_pestana_con_su_pronostico_y_no_acepta_cero(self):
        self.assertIn('el("h2", {}, "Factor de cuota por modelo")', self.js)
        cuerpo = tramo(self.js, "function pintarConfig() {")
        for linea in ('const rotos = factoresRotos(m);',
                      'type: "number", min: "0.01", max: "100", step: "0.01"',
                      'placeholder: "sin factor"',
                      "Object.values(cfg.catalogo).flatMap(x => Object.keys(x || {})).map(filaFactor)",
                      "disabled: !hay || rotas.length > 0 || rotos.length > 0 || !perfilPropuesta",
                      "tiene que ser un número mayor que 0."):
            self.assertIn(linea, cuerpo, linea)
        self.assertIn("function factoresRotos(m) { return Object.entries(m.factor_modelo).filter(([, k]) => !(Number.isFinite(k) && k > 0)).map(([modelo]) => modelo); }", self.js)
        # El pronóstico que muestra junto al factor es el que publica `cola-run.py --panel` para cada modelo del catálogo.
        panel = json.loads(self.correr("--panel")[1])
        self.assertEqual(set(panel["pronosticos"]), {m for t in panel["catalogo"].values() for m in t})
        self.assertIn("cfg.pronosticos[modelo]", cuerpo)
        self.assertIn("p.etiqueta", cuerpo)
        # La propuesta con un factor 0 la rechaza aplicar-propuesta, igual que la página la apaga.
        a = panel["modelos"]
        for k in (0, -1, True):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                self.ap.armar_plan("x", "encargos_config", {"factor_modelo": {"claude-sonnet-5-5": k}}, "")
        self.assertEqual(a["factor_modelo"]["claude-sonnet-5-5"], 0.61)

    def test_la_pestana_existe_y_solo_usa_comandos_fijos(self):
        html = leer(PAGINAS["encargos"] / "index.html")
        self.assertIn(("config", "Policies"), pestanas_encargos(html))
        self.assertIn('<section data-panel="config" hidden></section>', html)
        self.assertEqual(re.findall(r"<button[^>]*data-p=\"(\w+)\"", html), ["flujo", "ahora", "tiempo", "historial", "bitacora", "avisos", "config"])
        self.assertIn('<script src="../comun/comun.js"></script><script src="glosario.js"></script><script src="red.js"></script><script src="encargos.js"></script>', html)
        self.assertIn("({ flujo, ahora, tiempo, historial: hist, bitacora, avisos, config })[panel]();", self.js)
        # Lee y simula con cola-run.py del vault; los argumentos son fijos y lo editado va por stdin.
        self.assertIn("const COLA_RUN = `${DIR}/cola-run.py`, EJEMPLO = `${DIR}/ejemplo-reparto.toml`;", self.js)
        self.assertIn('cockpit.spawn(["python3", COLA_RUN, "--panel"], { err: "message" })', self.js)
        self.assertIn('cockpit.spawn(["python3", COLA_RUN, EJEMPLO, "--simular", "--con-cambios"], { err: "message" }).input(clave)', self.js)
        self.assertEqual(len(re.findall(r"cockpit\.spawn\(", self.js)), 8)      # tmux, find, los dos de arriba, el de 🔔 Avisos (23b), la matriz de carga (24 y 46b), el de los botones de cola (46c) y el del despacho (50a)
        self.assertTrue((ENCARGOS_DIR / "ejemplo-reparto.toml").is_file())
        # La página no escribe modelos.toml ni ningún otro archivo: sólo lee.
        self.assertEqual(re.findall(r"cockpit\.file\([^)]*\)\.(\w+)", self.js), ["read"])
        self.assertNotIn("modelos.toml`", self.js)
        # La pestaña se lee una vez: la relectura de cada minuto no borra lo que se está editando.
        self.assertIn("function config() { if (!configPedida) cargarConfig();", self.js)
        # Las cuatro partes y la simulación.
        for titulo in ("Nivel por naturaleza y rol", "Modelo y esfuerzo de cada nivel", "Reparto por defecto", "Candados",
                       "Efecto antes de proponer"):
            self.assertIn(f'el("h2", {{}}, "{titulo}")', self.js)
        # Candados: desde la página sólo se agregan. Lo único que se puede sacar es uno recién agregado, sin proponer.
        cuerpo = tramo(self.js, "function pintarConfig() {")
        self.assertEqual(cuerpo.count("m.autorizacion.modelos = "), 2)
        self.assertIn("m.autorizacion.modelos = [...m.autorizacion.modelos, nuevoCandado.value];", cuerpo)
        self.assertIn("a.autorizacion.modelos.includes(x) ? el(\"span\", { class: \"chip dato\" }, `🔒 ${x}`)", cuerpo)
        self.assertIn("Quitar uno no se hace desde la página.", cuerpo)
        # Mismo criterio de candado que cola-run.py (nombre exacto o trozo).
        self.assertIn("(aut.modelos || []).some(x => String(x).toLowerCase() === m) || (aut.patrones || []).some(x => m.includes(String(x).toLowerCase()))", self.js)
        self.assertIn("m.lower() in candado or any(p in m.lower() for p in patrones)", leer(ENCARGOS_DIR / "cola-run.py"))
        # Autor igual a revisor: la página lo marca y no deja proponer.
        self.assertIn("filter(([, r]) => r.autor === r.revisor)", self.js)
        # Las clases propias existen en la hoja, y nada lleva estilos en línea (lo mira la prueba general).
        css = leer(PAGINAS["encargos"] / "encargos.css")
        for clase in sorted(set(re.findall(r"config-[a-z]+", self.js))):
            self.assertIn(f".{clase}", css, clase)
        self.assertEqual(sorted(set(re.findall(r"config-[a-z]+", self.js))),
                         ["config-ancho", "config-cambiado", "config-mal", "config-par", "config-roto", "config-simulacion", "config-tabla"])
        # Las cuentas se muestran con su nombre, nunca con la clave suelta.
        self.assertIn("const cuentas = Object.entries(cfg.cuentas).map(([id, c]) => [id, c.nombre]);", self.js)
        self.assertNotRegex(self.js + leer(COMUN / "comun.js"), r"\b(Diego|Cami|Camila)\b(?!\))")


# ---- Encargo 23b: 🔔 Avisos. Registro único (encargos/registro_avisos.py) y su pestaña. ----
FIX_AVISOS = FIXTURES / "avisos"
ID_PEDIDO, ID_LINEA, ID_OTRO = "20261004-165405-a108", "20261004-163132-1596", "20261004-165447-06dc"


class AvisosTests(unittest.TestCase):
    """El registro vive en una carpeta temporal; lo que se lee de otros (resultados de nodo-desplegar,
    manifiesto de noticias, uso.json, cuentas.toml, estado.py) son copias o los archivos reales del
    vault. Lo único falso es `nodo-desplegar`, que mandaría un mensaje de verdad: devuelve lo que
    imprime el real, un id en la última línea."""

    def setUp(self):
        import shutil
        import sqlite3
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = self.r = _CARGAR_ORIGINAL(f"registro_avisos_{id(self)}", ENCARGOS_DIR / "registro_avisos.py")   # con las rutas reales, para compararlas
        self.reales = {k: getattr(r, k) for k in ("REGISTRO", "PENDIENTE_AVISOS", "RESULTADOS", "USO", "CUENTAS", "FUENTES")}
        r.REGISTRO = self.tmp / "avisos.jsonl"
        r.PENDIENTE_AVISOS = self.tmp / "avisos-registro-pendiente.jsonl"
        r.BANDEJA, r.BANDEJA_ESTADO, r.BANDEJA_CERROJO = self.tmp / "avisos-salida.jsonl", self.tmp / "avisos-bandeja.json", self.tmp / ".avisos-salida.lock"
        r.RESULTADOS = self.tmp / "resultados"
        shutil.copytree(FIX_AVISOS / "resultados", r.RESULTADOS)
        r.USO = FIX_AVISOS / "uso-real.json"
        r.CUENTAS = (self.tmp / "cuentas.toml",)
        shutil.copy(FIX_AVISOS / "cuentas.toml", self.tmp / "cuentas.toml")   # copia fija: no depende de los topes vivos
        r.FUENTES = {k: (PI / f"{k}.py", PI / f"{k}.py") for k in ("estado", "avisos", "nodo-desplegar")}
        r.NOTICIAS = self.tmp / "noticias"
        r.NOTICIAS.mkdir()
        shutil.copy(FIX_AVISOS / "manifiesto-real.jsonl", r.NOTICIAS / "manifiesto.jsonl")
        shutil.copy(PI.parent.parent / "13-Agente-Noticias" / "_operacion.json", r.NOTICIAS / "_operacion.json")
        r.NOTICIAS_DB = self.tmp / "noticias.db"
        con = sqlite3.connect(r.NOTICIAS_DB)      # el esquema que crea urgente.py (preparar_tabla)
        con.execute("CREATE TABLE avisados (hash TEXT PRIMARY KEY, firma TEXT, titulo TEXT, puntaje REAL, cuando TEXT, par TEXT)")
        con.execute("INSERT INTO avisados VALUES (?,?,?,?,?,?)", ("h1", '["puent", "colap"]', "Colapsa puente en Lautaro", 1.21,
                                                                 "2026-10-02T14:05:11.301222-03:00", "emergencia|araucania"))
        con.commit()
        con.close()
        self.js = leer(PAGINAS["encargos"] / "encargos.js")
        self.bloque = self.js.split("// Encargo 23b: «🔔 Avisos».", 1)[1].split("// pintar() llega acá", 1)[0]

    def lineas(self):
        return [json.loads(x) for x in self.r.REGISTRO.read_text(encoding="utf-8").splitlines()]

    def nodo_desplegar(self, ids, rc=0):
        """Reemplaza subprocess.run mientras dura la prueba (y lo repone): anota cada llamada a
        `nodo-desplegar` y devuelve lo que imprime el real, el id en la última línea."""
        from unittest import mock
        llamadas, cola = [], list(ids)

        def run(cmd, **kw):
            llamadas.append((cmd, kw))
            self.assertEqual(cmd[0], "nodo-desplegar")
            if cmd[1] == "esperar":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, rc, (cola.pop(0) + "\n") if rc == 0 else "", "" if rc == 0 else "el escucha no responde\n")
        parche = mock.patch.object(subprocess, "run", run)
        parche.start()
        self.addCleanup(parche.stop)
        return llamadas

    def cola_run(self):
        cr = previas._cargar(f"cola_run_avisos_{id(self)}", ENCARGOS_DIR / "cola-run.py")
        cr.L = cr.E = self.tmp
        cr.ESTADO, cr.HISTORIAL = self.tmp / "ESTADO.md", self.tmp / "historial.jsonl"
        cr._RA_MOD = self.r
        return cr

    def test_las_rutas_reales_son_las_del_encargo(self):
        self.assertEqual(str(self.reales["REGISTRO"]), "/opt/nodo/datos/avisos.jsonl")
        self.assertEqual(str(self.reales["RESULTADOS"]), "/var/spool/nodo-desplegar/resultados")
        # El mismo archivo de espera que escribe avisos.py, y el mismo cuentas.toml que lee.
        av = previas._cargar("avisos_rutas", PI / "avisos.py")
        self.assertEqual(self.reales["PENDIENTE_AVISOS"], av.REGISTRO_PENDIENTE)
        self.assertEqual(str(self.reales["REGISTRO"]), str(av.REGISTRO))
        self.assertEqual(self.reales["CUENTAS"][0], av.CUENTAS)
        self.assertEqual(str(self.reales["USO"]), str(av.USO))
        self.assertEqual(self.reales["FUENTES"]["avisos"], (Path("/usr/local/bin/avisos"), PI / "avisos.py"))
        # RE_ID y el plazo de los resultados son los de nodo-desplegar.
        nd = leer(PI / "nodo-desplegar.py")
        self.assertIn(f'RE_ID = re.compile(r"{self.r.RE_ID.pattern}")', nd)
        self.assertIn(f"> {self.r.RESULTADOS_DIAS} * 86400", nd)

    def test_cola_run_escribe_cada_aviso_sin_cambiar_como_lo_envia(self):
        cr = self.cola_run()
        llamadas = self.nodo_desplegar([ID_LINEA])
        motivo = "⏸️ Cola cola23 en pausa: Claude (Cami) sin margen para autor: semanal 74 % + 5 % > tope 75 %. Nada quedó desplegado. Esta línea la reanuda desde 23b:autor."
        linea = "tmux new-session -d -s cola23 python3 /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/cola-run.py cola-23.toml --desde 23b:autor"
        cr.avisar(motivo, linea)
        # El envío es el de siempre: el mismo comando, y la salida va a avisos.log.
        self.assertEqual([c for c, _ in llamadas], [["nodo-desplegar", "sugerir", "--motivo", motivo, "--", linea]])
        self.assertEqual(leer(self.tmp / "avisos.log"), ID_LINEA + "\n")
        (a,) = self.lineas()
        self.assertEqual(tuple(a), self.r.CLAVES)
        self.assertEqual(a, {"momento": a["momento"], "origen": "cola", "nivel": "alerta", "texto": motivo,
                             "linea": linea, "id": ID_LINEA, "estado": None})
        self.assertIsNotNone(datetime.fromisoformat(a["momento"]).utcoffset())
        # El nivel sale del emoji con que la cola ya abre cada aviso (los de cola-run.py, tal cual).
        fuente = leer(ENCARGOS_DIR / "cola-run.py")
        for emoji, nivel in (("⛔", "error"), ("💥", "error"), ("⏸️", "alerta"), ("⏳", "alerta"), ("🔒", "alerta"), ("✅", "ok"), ("🚀", "info")):
            self.assertRegex(fuente, rf'f?"{emoji} ', emoji)
            self.assertEqual(self.r.nivel_de(f"{emoji} Cola x: algo"), nivel, emoji)

    def test_la_autorizacion_y_el_pedido_de_despliegue_tambien_quedan(self):
        cr = self.cola_run()
        llamadas = self.nodo_desplegar([ID_LINEA, ID_PEDIDO, ID_OTRO])
        import contextlib
        import io
        cr._cfg_modelos = lambda: {"autorizacion": {"espera_max_min": 30}}
        cr.MANIFIESTO = {"nombre": "cola23", "motivo": "Reparto editable y 🔔 Avisos.", "despliegue": "pedir"}
        antes = {"entradas": {"bin-avisos": "aaaaaaaaaaaa"}, "paginas": {}, "sin_catalogo": set()}
        with contextlib.redirect_stdout(io.StringIO()):      # la bitácora de la cola, que acá no se mira
            self.assertTrue(cr.pedir_autorizacion("cola23", {"claude-fable-5-1": ["23b autor"]}))
            cr.desplegar(antes, dict(antes, entradas={"bin-avisos": "bbbbbbbbbbbb"}))
        candado, pedido, hecho = self.lineas()
        self.assertEqual((candado["nivel"], candado["id"], candado["linea"]),
                         ("alerta", ID_LINEA, "echo 'Autorizo claude-fable-5-1 para la cola cola23'"))
        self.assertTrue(candado["texto"].startswith("🔒 La cola cola23 quiere usar modelos que requieren tu autorización"))
        self.assertEqual((pedido["origen"], pedido["nivel"], pedido["id"], pedido["linea"]), ("cola", "info", ID_PEDIDO, None))
        self.assertIn("bin-avisos=bbbbbbbbbbbb", pedido["texto"])
        self.assertEqual((hecho["nivel"], hecho["id"], hecho["texto"]),
                         ("ok", ID_OTRO, "✅ Cola cola23 DESPLEGADA. Esta línea muestra el resumen."))
        # El pedido que se manda es el mismo de antes del encargo.
        self.assertIn(["nodo-desplegar", "pedir", "bin-avisos=bbbbbbbbbbbb", "--motivo", "Cola cola23: Reparto editable y 🔔 Avisos."],
                      [c for c, _ in llamadas])

    def test_paginas_pendientes_escribe_con_su_origen(self):
        pp = previas._cargar(f"paginas_pendientes_{id(self)}", ENCARGOS_DIR / "paginas-pendientes.py")
        pp.L, pp._RA_MOD = self.tmp, self.r
        llamadas = self.nodo_desplegar([ID_LINEA])
        motivo = "📦 Instalación ÚNICA de páginas de Cockpit (encargos): junta lo pendiente."
        linea = "mkdir -p ~/.local/share/cockpit/encargos && cp -r /home/dcifu004/encargos-logs/paginas-pendientes-20261004-1700/encargos/. ~/.local/share/cockpit/encargos/"
        pp.avisar(motivo, linea)
        self.assertEqual([c for c, _ in llamadas], [["nodo-desplegar", "sugerir", "--motivo", motivo, "--", linea]])
        (a,) = self.lineas()
        self.assertEqual(a, {"momento": a["momento"], "origen": "paginas", "nivel": "info", "texto": motivo,
                             "linea": linea, "id": ID_LINEA, "estado": None})
        self.assertEqual(self.r.nivel_de("⛔ No se armó la instalación única de páginas"), "error")
        # Con la marca que hereda un agente no se convierte un registro descartado en
        # un pedido real. L queda en su valor productivo, pero el doble confirma que
        # no llegó ninguna llamada adicional a nodo-desplegar.
        pp.L = Path.home() / "encargos-logs"
        with mock.patch.dict(os.environ, {"NODO_PRUEBAS": "1"}, clear=True):
            pp.avisar(motivo, linea)
        self.assertEqual(len(llamadas), 1)

    def test_un_aviso_que_no_salio_queda_dicho_y_registrar_nunca_detiene_a_la_cola(self):
        cr = self.cola_run()
        self.nodo_desplegar([], rc=1)
        cr.avisar("⛔ Cola cola23: 23b quedó NO DESPLEGABLE.", "cat ESTADO.md")
        (a,) = self.lineas()
        self.assertEqual((a["id"], a["estado"]), (None, "no enviado"))
        self.assertIn("el escucha no responde", leer(self.tmp / "avisos.log"))
        # Sin dónde escribir: registrar devuelve False y avisar termina igual.
        import contextlib
        import io
        self.r.REGISTRO = self.tmp / "no-existe" / "avisos.jsonl"
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertIs(self.r.registrar("cola", "x"), False)
            cr.avisar("✅ Cola cola23 DESPLEGADA.", "cat ESTADO.md")
        self.assertIn("no se pudo registrar el aviso", err.getvalue())
        # Con el volumen cerrado no se escribe en la carpeta vacía de la raíz.
        self.r.REGISTRO, self.r.VOLUMEN = self.tmp / "avisos.jsonl", self.tmp
        self.assertFalse(os.path.ismount(self.tmp))
        self.assertIs(self.r.registrar("cola", "✅ algo"), False)
        self.assertEqual(len(self.lineas()), 1)
        # Y si el propio módulo del registro no carga, la cola avisa igual.
        cr._RA_MOD = None
        cr.importlib = type("roto", (), {"util": type("u", (), {"spec_from_file_location": staticmethod(lambda *a: 1 / 0)})})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cr.avisar("✅ Cola cola23 DESPLEGADA.", "cat ESTADO.md")
        self.assertIn("no se pudo registrar el aviso (ZeroDivisionError", out.getvalue())

    def test_el_agente_marcado_no_cae_al_aviso_real_si_descarta_la_bandeja(self):
        cr = self.cola_run()
        cr.L = Path.home() / "encargos-logs"
        llamadas = self.nodo_desplegar([ID_LINEA])
        with mock.patch.dict(os.environ, {"NODO_PRUEBAS": "1"}, clear=True):
            cr.avisar_texto("⏸️ Aviso de prueba descartado.", viejo=("⏸️ Aviso de prueba descartado.", "cat ESTADO.md"))
        self.assertEqual(llamadas, [])
        self.assertFalse(self.r.BANDEJA.exists())
        self.assertFalse(self.r.REGISTRO.exists())

    def test_ningun_token_ni_chat_id_llega_al_registro(self):
        token, chat = "7123456789:AAH" + "k3J9-xQ_w" * 4, "5900000017"
        self.assertTrue(self.r.registrar(
            "cola", f"💥 Cola x se cayó: HTTPError https://api.telegram.org/bot{token}/sendMessage chat_id={chat} TELEGRAM_TOKEN={token}",
            f"curl -s https://api.telegram.org/bot{token}/sendMessage -d chat_id={chat} -d text=listo"))
        crudo = self.r.REGISTRO.read_text(encoding="utf-8")
        for secreto in (token, token.split(":")[1], chat):
            self.assertNotIn(secreto, crudo)
        (a,) = self.lineas()
        self.assertIn("Cola x se cayó", a["texto"])
        self.assertIn("curl -s https://api.telegram.org/bot[token]/sendMessage", a["linea"])
        # Una línea normal de las colas no se toca.
        normal = "nodo-desplegar pedir bin-avisos=0a1b2c3d4e5f unidad-avisos-service=aabbccddeeff --motivo \"Cola cola23\""
        self.assertEqual(self.r.sin_secretos(normal), normal)
        # avisos.py lleva la misma limpieza (no puede importar ésta: vive fuera del cifrado).
        av = previas._cargar("avisos_secretos", PI / "avisos.py")
        self.assertEqual([(p.pattern, c) for p, c in av._SECRETOS], [(p.pattern, c) for p, c in self.r._SECRETOS])
        # Ni los emisores ni el registro leen el archivo del token.
        for f in ("registro_avisos.py", "cola-run.py", "paginas-pendientes.py"):
            self.assertNotIn("avisos.env", leer(ENCARGOS_DIR / f), f)

    def test_el_registro_se_crea_escribible_por_el_grupo(self):
        viejo = os.umask(0o077)       # el umask del que escribe primero no decide
        try:
            self.r.asegurar()
            self.assertEqual(self.r.REGISTRO.stat().st_mode & 0o777, 0o664)
            self.r.REGISTRO.unlink()
            self.assertTrue(self.r.registrar("cola", "✅ algo"))
            self.assertEqual(self.r.REGISTRO.stat().st_mode & 0o777, 0o664)
        finally:
            os.umask(viejo)
        self.assertIn("SupplementaryGroups=dcifu004", leer(PI / "avisos.service"))

    def historial(self, ahora="2026-10-04T18:00:00-03:00"):
        return self.r.historial(datetime.fromisoformat(ahora).timestamp())

    def test_el_estado_de_cada_pedido_se_lee_de_nodo_desplegar_sin_tocarlo(self):
        antes = {f.name: f.read_bytes() for f in self.r.RESULTADOS.iterdir()}
        f = lambda **k: json.dumps(self.r.fila(**k), ensure_ascii=False) + "\n"
        self.r.REGISTRO.write_text(
            f(origen="cola", texto="✅ Cola cola22 DESPLEGADA.", linea="cat ESTADO.md", id=ID_LINEA, momento="2026-10-04T16:31:32-03:00")
            + f(origen="cola", texto="🔒 La cola cola23 quiere usar modelos…", linea="echo 'Autorizo'", id=ID_PEDIDO, momento="2026-10-04T16:54:05-03:00")
            + f(origen="paginas", texto="📦 Instalación ÚNICA de páginas", linea="mkdir -p x", id="20261004-175500-beef", momento="2026-10-04T17:55:00-03:00")
            + f(origen="cola", texto="⏳ Cola vieja en espera", linea="cat ESTADO.md", id="20260920-101010-cafe", momento="2026-09-20T10:10:10-03:00")
            + "esto no es JSON\n"
            + f(origen="nodo", texto="🔴 Nodo Pi5\n• ultimo respaldo hace 37 h", nivel="alerta", momento="2026-10-04T03:40:00-03:00"),
            encoding="utf-8")
        self.r.PENDIENTE_AVISOS.write_text(
            f(origen="nodo", texto="🔴 Nodo Pi5 (visibilidad reducida)\n• volumen cifrado CERRADO", nivel="alerta", momento="2026-10-04T17:58:00-03:00"),
            encoding="utf-8")
        h = self.historial()
        por_id = {a["id"]: a for a in h["avisos"] if a["id"]}
        self.assertEqual(por_id[ID_LINEA]["estado"], "hecho")            # resultado real: «hecho»
        self.assertEqual(por_id[ID_PEDIDO]["estado"], "rechazado")       # resultado real: «rechazado»
        self.assertEqual(por_id["20261004-175500-beef"]["estado"], "pendiente")      # sin resultado todavía
        self.assertIsNone(por_id["20260920-101010-cafe"]["estado"])      # el resultado ya se borró: sin datos, no «pendiente»
        # El pedido que nadie registró aparece con origen nodo-desplegar y la forma del resultado real.
        otro = por_id[ID_OTRO]
        self.assertEqual((otro["origen"], otro["nivel"], otro["estado"], otro["momento"]),
                         ("nodo-desplegar", "alerta", "vencido", datetime(2026, 10, 4, 17, 24, 54).astimezone().isoformat()))
        self.assertEqual(otro["texto"], f"Pedido {ID_OTRO}: vencido")       # id y estado; el detalle no se publica
        self.assertEqual([a["id"] for a in h["avisos"]].count(ID_LINEA), 1)      # no se duplica el que sí se registró
        # Línea pendiente de ✅: sólo la que no tiene resultado.
        self.assertEqual([(a["id"], a["linea"]) for a in h["pendientes"]], [("20261004-175500-beef", "mkdir -p x")])
        # Una línea rota no esconde las demás, y lo que avisos.py no pudo volcar se ve igual.
        self.assertEqual((h["ilegibles"], h["sin_volcar"]), (1, 1))
        self.assertEqual(h["avisos"][0]["texto"].splitlines()[1], "• volumen cifrado CERRADO")
        momentos = [datetime.fromisoformat(a["momento"]).timestamp() for a in h["avisos"]]
        self.assertEqual(momentos, sorted(momentos, reverse=True))
        self.assertTrue(all(tuple(a) == self.r.CLAVES for a in h["avisos"]))
        # Sólo se leyó: los resultados de nodo-desplegar quedan idénticos.
        self.assertEqual({f.name: f.read_bytes() for f in self.r.RESULTADOS.iterdir()}, antes)
        fuente = leer(ENCARGOS_DIR / "registro_avisos.py")
        self.assertNotRegex(fuente, r"RESULTADOS[^\n]*\.(write|unlink|rename|open\()")
        self.assertNotIn("subprocess", fuente)

    def test_el_detalle_de_nodo_desplegar_no_llega_a_la_pestana(self):
        """23br1, hallazgo 1. Los resultados reales traen «rechazado por …» y «… dice que lo corrió» con
        el nombre de una persona. Nadie registró esos pedidos, así que los tres entran por
        de_nodo_desplegar(), y lo que se revisa es todo lo que la pestaña recibe (historial y alarmas)."""
        crudos = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in self.r.RESULTADOS.iterdir()}
        # La muestra mide: es la forma real (id, estado, detalle, hora) y trae el nombre suelto.
        self.assertEqual({tuple(c) for c in crudos.values()}, {("id", "estado", "detalle", "hora")})
        self.assertEqual({i: c["detalle"] for i, c in crudos.items()},
                         {ID_LINEA: "Diego dice que lo corrió", ID_PEDIDO: "rechazado por Diego", ID_OTRO: "nadie lo aprobó a tiempo"})
        panel = dict(self.historial(), alarmas=self.r.alarmas())
        propios = {a["id"]: a for a in panel["avisos"] if a["origen"] == "nodo-desplegar"}
        self.assertEqual({i: (a["texto"], a["estado"], a["nivel"]) for i, a in propios.items()},
                         {ID_LINEA: (f"Pedido {ID_LINEA}: hecho", "hecho", "ok"),
                          ID_PEDIDO: (f"Pedido {ID_PEDIDO}: rechazado", "rechazado", "alerta"),
                          ID_OTRO: (f"Pedido {ID_OTRO}: vencido", "vencido", "alerta")})
        publicado = json.dumps(panel, ensure_ascii=False)
        for c in crudos.values():
            self.assertNotIn(c["detalle"], publicado)
        # Ningún nombre individual sin su etiqueta: se quitan las formas permitidas y no puede quedar ninguno.
        # (No sirve mirar si lo sigue un «)»: «(rechazado por Diego)» también termina así.)
        sin_etiquetas = re.sub(r"Claude \((?:Diego|Cami)\)", "", publicado)
        self.assertIn("Claude (Cami)", publicado)        # las cuentas sí se nombran, con su etiqueta
        self.assertNotRegex(sin_etiquetas, r"\b(Diego|Cami|Camila)\b")
        # Un pedido que una cola sí registró tampoco lo hereda al resolver su estado.
        self.r.REGISTRO.write_text(json.dumps(self.r.fila(origen="cola", texto="🔒 La cola cola23 quiere usar modelos…", id=ID_PEDIDO,
                                                          momento="2026-10-04T16:54:05-03:00"), ensure_ascii=False) + "\n", encoding="utf-8")
        h = self.historial()
        self.assertEqual([(a["origen"], a["estado"]) for a in h["avisos"] if a["id"] == ID_PEDIDO], [("cola", "rechazado")])
        self.assertNotRegex(re.sub(r"Claude \((?:Diego|Cami)\)", "", json.dumps(h, ensure_ascii=False)), r"\b(Diego|Cami|Camila)\b")
        # Y resultados() ni siquiera lo carga: no queda a mano para que otro lo publique después.
        self.assertEqual({tuple(v) for v in self.r.resultados().values()}, {("estado", "momento")})

    def test_las_noticias_entran_solo_con_los_avisos_que_el_agente_ya_manda(self):
        manifiesto = [json.loads(x) for x in leer(FIX_AVISOS / "manifiesto-real.jsonl").splitlines()]
        self.assertEqual([isinstance(m.get("telegram"), dict) and m["telegram"]["ok"] for m in manifiesto], [True, True, False])
        # Un envío que falló, con la forma que deja seleccion.py cuando no encuentra credenciales.
        fallido = dict(manifiesto[1], cuando="2026-10-04T16:00:02.000001-03:00",
                       telegram={"ok": False, "env_probados": ["/etc/nodo/avisos.env"], "detalle": "ningún .env tenía TELEGRAM_TOKEN + CHAT_ID legibles"})
        self.assertIn('"detalle": "ningún .env tenía TELEGRAM_TOKEN + CHAT_ID legibles"', leer(PI.parent.parent / "13-Agente-Noticias" / "pi" / "seleccion.py"))
        with (self.r.NOTICIAS / "manifiesto.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(fallido, ensure_ascii=False) + "\n")
        ns = [a for a in self.historial()["avisos"] if a["origen"] == "noticias"]
        # Dos entregas con Telegram en ok y un aviso urgente. La corrida sin Telegram no es un aviso.
        self.assertEqual([(a["nivel"], a["momento"]) for a in ns],
                         [("info", "2026-10-04T12:00:11.111283-03:00"), ("info", "2026-10-04T07:30:00.345469-03:00"),
                          ("alerta", "2026-10-02T14:05:11.301222-03:00")])
        self.assertEqual(ns[0]["texto"], "📰 Noticias: 8 elegidas de 174 candidatas (ventana de 5 h)")
        self.assertEqual(ns[2]["texto"], "🚨 Noticia importante: Colapsa puente en Lautaro")
        # Ni la nota ni su ruta: el contenido sigue en 📰 Noticias.
        self.assertFalse([a for a in ns if "entregas/" in a["texto"] or ".md" in a["texto"] or a["linea"]])
        # El esquema de la prueba es el que crea el agente.
        self.assertIn("hash TEXT PRIMARY KEY, firma TEXT, titulo TEXT, puntaje REAL, cuando TEXT",
                      leer(PI.parent.parent / "13-Agente-Noticias" / "pi" / "urgente.py"))
        # Sin base o sin manifiesto: sin noticias, sin error.
        self.r.NOTICIAS_DB, self.r.NOTICIAS = self.tmp / "no.db", self.tmp / "no"
        self.assertEqual([a for a in self.historial()["avisos"] if a["origen"] == "noticias"], [])
        self.assertFalse((self.tmp / "no.db").exists())

    def test_el_cuentas_toml_vivo_parsea_y_tiene_topes_validos(self):
        """Lo unico que se pide del archivo vivo: que sea valido. Que valor tengan los topes
        lo decide el usuario desde 💳 Cuentas, y ninguna otra prueba depende de eso."""
        import tomllib
        datos = tomllib.loads(leer(PI.parent / "botv3" / "cuentas.toml"))
        pagadas = [c for c in datos.values() if isinstance(c, dict) and "umbral_semanal" in c]
        self.assertTrue(pagadas)
        for c in pagadas:
            for k in ("umbral_semanal", "umbral_5h"):
                with self.subTest(cuenta=c.get("nombre"), tope=k):
                    self.assertIs(type(c[k]), int)
                    self.assertTrue(1 <= c[k] <= 100)

    def test_las_alarmas_de_cuota_salen_de_cuentas_toml_y_no_se_duplican(self):
        cuota = [a for a in self.r.alarmas() if a["grupo"] == "Cuota"]
        self.assertEqual([a["alarma"] for a in cuota],
                         ["Claude (Diego) · semanal", "Claude (Diego) · ventana de 5 h", "Claude (Cami) · semanal",
                          "Claude (Cami) · ventana de 5 h", "Codex · semanal", "Codex · ventana de 5 h"])
        cami = cuota[2]
        self.assertEqual(cami["umbral"], "avisa al 70 % (tope 75 % − 5); desde el 75 % las colas esperan o se pausan")
        self.assertEqual(cuota[3]["umbral"], "avisa al 85 % (tope 90 % − 5); desde el 90 % las colas esperan o se pausan")
        self.assertEqual((cami["ahora"], cuota[5]["ahora"]), ("65 %", "41 %"))       # la muestra real de uso.json
        self.assertIn("cuentas.toml · umbral_semanal (el de 💳 Cuentas)", cami["fuente"])
        self.assertIn("MARGEN_CUOTA", cami["fuente"])
        self.assertIsNone(cami["nota"])
        # El usuario cambia el tope en 💳 Cuentas: la alarma que se muestra cambia sola.
        toml = self.tmp / "cuentas.toml"
        toml.write_text(leer(toml).replace("umbral_semanal = 75", "umbral_semanal = 60"), encoding="utf-8")
        self.assertEqual([a["umbral"].split(";")[0] for a in self.r.alarmas() if a["grupo"] == "Cuota"][2], "avisa al 55 % (tope 60 % − 5)")
        # Y es el número que usa la regla de avisos.py con el mismo cuentas.toml.
        av = previas._cargar("avisos_alarmas", PI / "avisos.py")
        self.assertEqual(self.r.constantes(PI / "avisos.py")["MARGEN_CUOTA"], av.MARGEN_CUOTA)
        # Ningún umbral de cuota escrito en el registro ni en la pestaña.
        codigo = leer(ENCARGOS_DIR / "registro_avisos.py").split('"""', 2)[2]
        for texto in (codigo, self.bloque):
            self.assertIsNone(re.search(r"\b(70|75|85|90)\b", texto))
        # Con el avisos.py desplegado de antes del encargo (sin la regla), la fila lo dice.
        viejo = self.tmp / "avisos-desplegado"
        viejo.write_text("MAX_ANTIGUEDAD_S = 20 * 60\n", encoding="utf-8")
        self.r.FUENTES["avisos"] = (viejo, PI / "avisos.py")
        fila = [a for a in self.r.alarmas() if a["grupo"] == "Cuota"][0]
        self.assertEqual(fila["umbral"], "tope 60 %; desde el 60 % las colas esperan o se pausan")
        self.assertEqual(fila["nota"], "la alarma de cuota de avisos.py todavía no está desplegada")

    def test_las_alarmas_del_nodo_se_leen_del_codigo_que_las_dispara(self):
        import ast
        alarmas = self.r.alarmas()
        nodo = {a["alarma"].split(": ")[0]: a for a in alarmas if a["grupo"] == "Nodo" and "alertas()" in a["fuente"]}
        self.assertEqual(nodo["respaldo:viejo"]["umbral"], "r['horas'] >= 36")
        self.assertEqual(nodo["inbox:acumulado"]["umbral"], "inb.get('pendientes', 0) >= 25")
        self.assertEqual(nodo["agente:…"]["umbral"], "ag['horas'] >= 8")
        self.assertEqual(nodo["avisos:detenido"]["umbral"], "(av.get('min_sin_ciclo') or 0) >= 60")
        self.assertIn("volumen cifrado CERRADO", nodo["luks"]["alarma"])
        # Ninguna alerta de estado.py queda afuera: una fila por cada add() de alertas().
        fuente = leer(PI / "estado.py")
        fn = next(n for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.FunctionDef) and n.name == "alertas")
        llamadas = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "add"]
        self.assertEqual(len(self.r.reglas(PI / "estado.py", "alertas")), len(llamadas))
        self.assertGreaterEqual(len(llamadas), 15)
        # Las que arma el propio avisos.py cuando no hay estado.json, y su plazo.
        propias = [a for a in alarmas if "alertas_actuales()" in a["fuente"]]
        self.assertEqual([a["alarma"].split(": ")[0] for a in propias],
                         ["recolector:detenido", "nodo:ciego", "luks", "recolector:ausente", "respaldo:disco"])
        self.assertEqual([a for a in alarmas if "MAX_ANTIGUEDAD_S" in a["fuente"]][0]["umbral"], "20 min sin actualizar")
        # nodo-desplegar no se toca: su plazo se lee, sin ejecutar nada, del script.
        (vence,) = [a for a in alarmas if a["grupo"] == "Despliegue"]
        self.assertEqual((vence["umbral"], vence["fuente"]), ("30 min", f"{PI / 'nodo-desplegar.py'} · VENCE_S"))
        self.assertIn("VENCE_S = 30 * 60", leer(PI / "nodo-desplegar.py"))
        self.assertEqual([a["umbral"] for a in alarmas if a["grupo"] == "Colas"], ["30 min"])
        (noticia,) = [a for a in alarmas if a["grupo"] == "Noticias"]
        self.assertRegex(noticia["umbral"], r"^puntaje ≥ [\d.]+; hasta \d+ al día; en silencio de \d\d:\d\d a \d\d:\d\d$")
        # Todas con umbral y fuente.
        self.assertTrue(all(a["umbral"] and a["fuente"] for a in alarmas))
        # Si lo desplegado no es lo del vault, se dice; y se lee lo desplegado, que es lo que dispara.
        viejo = self.tmp / "estado-desplegado"
        viejo.write_text(fuente.replace("r[\"horas\"] >= 36", "r[\"horas\"] >= 48"), encoding="utf-8")
        self.r.FUENTES["estado"] = (viejo, PI / "estado.py")
        fila = [a for a in self.r.alarmas() if a["alarma"].startswith("respaldo:viejo")][0]
        self.assertEqual((fila["umbral"], fila["nota"]), ("r['horas'] >= 48", "el del vault es distinto: hay cambios sin desplegar"))
        # Un script que no se puede leer no rompe el panel.
        self.r.FUENTES["estado"] = (self.tmp / "no", self.tmp / "tampoco")
        self.assertFalse([a for a in self.r.alarmas() if "estado" in a["fuente"] and a["grupo"] == "Nodo" and "alertas()" in a["fuente"]
                          and "avisos" not in a["fuente"]])

    @staticmethod
    def filtrar(avisos, f):
        """Espejo de filtrarAvisos (encargos.js)."""
        return [x for x in avisos if (not f["origen"] or x["origen"] == f["origen"]) and (not f["nivel"] or x["nivel"] == f["nivel"])]

    def test_la_pestana_dibuja_lo_que_el_panel_publica(self):
        self.r.registrar("cola", "⏸️ Cola cola23 en pausa", "tmux new-session -d -s cola23", "20261004-175500-beef")
        self.r.registrar("paginas", "📦 Instalación ÚNICA", "mkdir -p x", ID_LINEA)
        self.r.registrar("nodo", "🔴 Nodo Pi5\n• algo", nivel="alerta")
        self.r.registrar("cuota", "🟡 Cuota\n• Claude (Cami) llegó al 70 % semanal", nivel="alerta")
        p = json.loads(json.dumps(self.r.panel(), ensure_ascii=False))       # lo que recibe la página
        html = leer(PAGINAS["encargos"] / "index.html")
        pestanas = pestanas_encargos(html)
        self.assertIn([("bitacora", "Logs"), ("avisos", "Alerts "), ("config", "Policies")], [pestanas[i:i + 3] for i in range(len(pestanas))])
        self.assertIn('<section data-panel="avisos" hidden></section>', html)
        self.assertIn("({ flujo, ahora, tiempo, historial: hist, bitacora, avisos, config })[panel]();", self.js)
        # Lee con un comando fijo, sin argumentos de la página; no propone, no usa sudo, no escribe.
        self.assertIn("const REGISTRO_AVISOS = `${DIR}/registro_avisos.py`;", self.js)
        self.assertEqual(re.findall(r"cockpit\.\w+\([^)]*\)", self.bloque), ['cockpit.spawn(["python3", REGISTRO_AVISOS, "--panel"], { err: "message" })'])
        for prohibido in ("proponer(", ".input(", "sudo", ".replace(", "cockpit.file"):
            self.assertNotIn(prohibido, self.bloque, prohibido)
        # Cada campo que la pestaña lee existe en lo que publica el panel, con la forma real.
        self.assertLessEqual(set(re.findall(r"\bav\.(\w+)", self.bloque)), set(p))
        campos = set(re.findall(r"\bx\.(\w+)", self.bloque))
        # Las filas de cuota traen además lo que usa la edición del aviso previo (encargo 24), que vive aparte de
        # este bloque de solo lectura: ahí se leen cuenta, tope, aviso, aviso_previo y ventana.
        edicion = self.js.split("// Encargo 24: el aviso previo de cuota se edita", 1)[1].split("// Encargo 23b", 1)[0]
        de_edicion = {"cuenta", "tope", "aviso", "aviso_previo"}
        self.assertEqual(campos, set(self.r.CLAVES) | (set(p["alarmas"][0]) - de_edicion))
        self.assertLessEqual(set(re.findall(r"\bx\.(\w+)", edicion)), set(p["alarmas"][0]))
        self.assertLessEqual(de_edicion, set(re.findall(r"\bx\.(\w+)", edicion)))
        self.assertTrue(all(set(a) == set(self.r.CLAVES) for a in p["avisos"] + p["pendientes"]))
        # Niveles y orígenes: los que la pestaña sabe nombrar son los que se escriben.
        niveles = re.search(r"const NIVELES = \{(.*?)\};", self.bloque).group(1)
        self.assertEqual(re.findall(r"(\w+): \[", niveles), list(self.r.NIVELES))
        self.assertEqual(p["niveles"], list(self.r.NIVELES))
        origenes = re.findall(r'"?([\w-]+)"?: "', re.search(r"const ORIGENES = \{(.*?)\};", self.bloque).group(1))
        self.assertEqual(sorted(origenes), sorted({a["origen"] for a in p["avisos"]}))
        self.assertEqual(sorted(origenes), ["cola", "cuota", "nodo", "nodo-desplegar", "noticias", "paginas"])
        # Filtro por origen y por nivel, sobre lo publicado.
        self.assertIn("function filtrarAvisos(xs, f) { return xs.filter(x => (!f.origen || x.origen === f.origen) && (!f.nivel || x.nivel === f.nivel)); }", self.bloque)
        todos = p["avisos"]
        self.assertEqual(self.filtrar(todos, {"origen": "", "nivel": ""}), todos)
        self.assertEqual([a["texto"] for a in self.filtrar(todos, {"origen": "cuota", "nivel": ""})], ["🟡 Cuota\n• Claude (Cami) llegó al 70 % semanal"])
        self.assertEqual({a["origen"] for a in self.filtrar(todos, {"origen": "", "nivel": "alerta"})}, {"cola", "nodo", "cuota", "nodo-desplegar", "noticias"})
        self.assertEqual([a["id"] for a in self.filtrar(todos, {"origen": "nodo-desplegar", "nivel": "ok"})], [])     # el «hecho» está registrado por paginas
        self.assertEqual(self.filtrar(todos, {"origen": "paginas", "nivel": "error"}), [])
        # Las tres partes: pendientes de ✅, historial y alarmas.
        for titulo in ('"Esperan tu ✅ en Telegram"', '"Historial"', '"Alarmas configuradas"'):
            self.assertIn(titulo, self.bloque)
        self.assertEqual([(a["id"], a["linea"]) for a in p["pendientes"]], [("20261004-175500-beef", "tmux new-session -d -s cola23")])
        self.assertIn("p.replaceChildren(pendientes, historial, alarmas);", self.bloque)
        # Las clases que usa existen en la hoja de la página o en la común.
        css = leer(PAGINAS["encargos"] / "encargos.css") + leer(COMUN / "base.css")
        clases = set(" ".join(re.findall(r'class: "([^"]+)"', self.bloque) + re.findall(r'"(chip dato[^"]*)"', self.bloque)).split())
        self.assertLessEqual({"avisos-tabla", "aviso-linea", "avisos-pendientes", "chip", "mal", "ojo"}, clases)
        for clase in clases:
            self.assertIn(f".{clase}", css, clase)
        # Los nombres de las cuentas llegan de cuentas.toml: en la pestaña no hay ninguno escrito.
        self.assertNotRegex(self.bloque, r"Claude|Codex")

    def test_la_linea_de_una_pausa_va_en_el_registro_con_un_boton_de_copiar_y_no_en_el_mensaje(self):
        self.assertIn('x.linea ? el("div", { class: "aviso-copiable" }, el("code", { class: "aviso-linea" }, x.linea), '
                      'el("button", { class: "mini", title: "Copiar la línea", onclick: ev => copiar(ev.target, x.linea) }, "Copiar")) : null', self.bloque)
        self.assertIn("navigator.clipboard.writeText(texto).then(", self.bloque)
        texto = "⏸️ La cola cola9 está en pausa: se quedó sin cuota. Se reanuda desde 9:autor con la línea que muestra 🔔 Avisos, en 🧵 Encargos."
        linea = "tmux new-session -d -s cola9 python3 /x/cola-run.py /x/cola-9.toml --desde 9:autor"
        self.r.registrar("cola", texto, linea)
        (pausa,) = [a for a in json.loads(json.dumps(self.r.panel()))["avisos"] if a["origen"] == "cola"]
        self.assertEqual((pausa["texto"], pausa["linea"], pausa["nivel"]), (texto, linea, "alerta"))
        self.assertNotIn("tmux", pausa["texto"])               # el mensaje es información; lo copiable viaja aparte
        css = leer(PAGINAS["encargos"] / "encargos.css")
        for clase in ("aviso-copiable", "aviso-previo"):       # 46b: .regla-no y .regla-cuotas se fueron con la lista que reemplazó la matriz
            self.assertIn(f".{clase}", css)


# ---- Encargo 24: la espera de cuota se ve, se avisa y se anticipa. ----
# cola-run.py corre DE VERDAD sobre una carpeta de mktemp -d: bitácora, historial (copia de las 34 filas reales
# del 04-10), modelos.toml, vivo/<cola>.json, registro de avisos y bandeja. Lo único falso es lo que no se puede
# dejar real: medir() (cambia a cada rato), time.sleep (horas) y el envío (nodo-desplegar y Telegram, que
# mandarían algo de verdad). El reloj es una variable de la prueba.
import contextlib
import io
import shutil
import tempfile
import threading
import time
import tomllib
from datetime import timezone
from unittest import mock

SUEÑO_REAL = time.sleep       # ColaRealBase reemplaza time.sleep por uno que adelanta el reloj; los hilos del cerrojo necesitan el de verdad
CHILE = timezone(timedelta(hours=-3))
ETAPA_24 = {"autor": "claude_cami", "revisor": "codex", "vueltas": 2, "naturaleza": "bot",
            "modelo_autor": "claude-opus-5-5", "esfuerzo_autor": "medium", "modelo_fix": "claude-opus-5-5",
            "esfuerzo_fix": "medium", "modelo_rev": "gpt-5.6-terra", "esfuerzo_rev": "medium"}
TEXTO_ESPERA = ("⏳ La cola cola23 espera la cuota de Claude (Cami): 5 h 74 % + 25 % > tope 90 %. "
                "Sigue sola a las 20:32; no hay que hacer nada.")


class ColaRealBase(unittest.TestCase):
    ARRANQUE = datetime.fromisoformat("2026-10-04T18:01:30-03:00")      # el caso del 04-10: Claude (Cami) en 74 % de 5 h
    RENUEVA = datetime.fromisoformat("2026-10-04T20:30:00-03:00")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for origen, destino in (("encargos/historial-34.jsonl", "historial.jsonl"), ("encargos/modelos.toml", "modelos.toml"),
                                ("avisos/cuentas.toml", "cuentas.toml")):
            shutil.copy(FIXTURES / origen, self.tmp / destino)
        cr = self.cr = previas._cargar(f"cola_run_{id(self)}", ENCARGOS_DIR / "cola-run.py")
        cr.MODELOS, cr.HISTORIAL, cr.ESTADO = self.tmp / "modelos.toml", self.tmp / "historial.jsonl", self.tmp / "ESTADO.md"
        cr.L = cr.E = cr.D = self.tmp
        cr.REGISTROS = (self.tmp / "cuentas.toml",)
        cr.SIMULANDO = False
        # D es el temporal y ahí no hay pi/aplicar-propuesta.py. En el nodo sí está, junto a cola-run.py, y
        # desde 48r2-1 una cola que declara `esfuerzo_<rol>` no corre sin él: se carga el real, con la copia
        # del catálogo de Codex de las fixtures.
        cr._AP_MOD = previas._cargar(f"aplicar_{id(self)}", PI / "aplicar-propuesta.py")
        cr._AP_MOD.CODEX_MODELOS = str(FIXTURES / "encargos" / "models_cache.json")
        ra = self.ra = previas._cargar(f"registro_avisos_{id(self)}", ENCARGOS_DIR / "registro_avisos.py")
        ra.REGISTRO, ra.BANDEJA, ra.BANDEJA_ESTADO = self.tmp / "avisos.jsonl", self.tmp / "avisos-salida.jsonl", self.tmp / "avisos-bandeja.json"
        ra.BANDEJA_CERROJO = self.tmp / ".avisos-salida.lock"
        cr._RA_MOD = ra
        self.reloj = self.ARRANQUE
        cr.ahora = lambda: self.reloj
        self.dormidas, self.envios = [], []
        self.al_dormir = lambda: None
        self.pct_5h = lambda reloj: 74.0
        cr.medir = self.medida

        def dormir(segundos):
            self.dormidas.append(segundos)
            self.reloj += timedelta(seconds=segundos)
            self.al_dormir()

        def run(cmd, *a, **k):
            if cmd and cmd[0] == "nodo-desplegar":
                self.envios.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 1 if cmd[1] == "esperar" else 0,
                                                   "{}" if cmd[1] == "catalogo" else "20261004-180100-abcd\n", "")
            return run_real(cmd, *a, **k)
        run_real = subprocess.run
        salida = mock.patch("sys.stdout", io.StringIO())      # log() imprime cada línea de la bitácora
        salida.start()
        self.addCleanup(salida.stop)
        for objetivo, doble in (("time.sleep", dormir), ("subprocess.run", run)):
            parche = mock.patch(objetivo, doble)
            parche.start()
            self.addCleanup(parche.stop)

    def medida(self, cid):
        ya = self.reloj >= self.RENUEVA
        return {"5h": 0.0 if ya else self.pct_5h(self.reloj), "sem": 40.0, "renueva_5h": None if ya else self.RENUEVA,
                "renueva_sem": self.reloj + timedelta(days=3), "momento": None, "fuente": "fresco"}

    def manifiesto(self, **extra):
        self.cr.MANIFIESTO = dict({"nombre": "cola23", "motivo": "Reparto editable y 🔔 Avisos (encargos 23a–23d).", "paciencia_h": 12,
                                   "pruebas": [], "etapa": [dict(ETAPA_24, id="23d"), dict(ETAPA_24, id="23e")]}, **extra)

    def arrancar(self, estado, etapa, fase, cuenta, modelo):
        """VIVO como lo dejaría cola23 en esa fase: lo que hay en el archivo lo escribe vivo() del propio cola-run."""
        self.manifiesto()
        cr, reloj = self.cr, self.reloj
        cr.VIVO.clear()
        cr.vivo(nombre="cola23", motivo=cr.MANIFIESTO["motivo"], estado="partiendo", lanzada=(reloj - timedelta(hours=3)).isoformat(timespec="seconds"),
                etapas=["23d", "23e"], inicio_trabajo=(reloj - timedelta(hours=3)).isoformat(timespec="seconds"),
                fases_hechas=[{"etapa": "23d", "fase": "autor", "cuenta": "Claude (Cami)", "min": 36.6, "pronostico_min": 12},
                              {"etapa": "23d", "fase": "rev1", "cuenta": "Codex", "min": 6.0, "pronostico_min": 4.4}])
        cr.vivo(estado=estado, etapa=etapa, fase=fase, cuenta=cuenta, modelo=modelo, inicio_fase=reloj.isoformat(timespec="seconds"),
                pronostico_fase_min=4.4, remoto=None)

    def vivo_json(self):
        return json.loads((self.tmp / "vivo" / "cola23.json").read_text(encoding="utf-8"))

    def lineas(self, ruta=None):
        ruta = ruta or self.ra.REGISTRO
        return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()] if ruta.exists() else []

    def sugeridos(self):
        """Lo que la cola le pidió a nodo-desplegar para avisar (sin las consultas de catálogo de foto())."""
        return [e for e in self.envios if e[1] != "catalogo"]

    def lado_nuevo_activo(self, **estado):
        import time as reloj_real
        (self.tmp / "avisos-bandeja.json").write_text(json.dumps(dict({"version": 1, "ultimo_ciclo": reloj_real.time(), "ok": True}, **estado)), encoding="utf-8")

    def espera_del_04_10(self):
        """Claude (Cami) autor de 23e con 74 % de 5 h y +25 %: 74 + 25 > 90. Devuelve lo que escribió vivo() en cada tramo."""
        self.arrancar("corriendo", "23d", "rev1", "Codex", "gpt-5.6-terra medium")
        tramos = []
        self.al_dormir = lambda: tramos.append(self.vivo_json())
        return tramos, self.cr.chequear_cuota("claude_cami", "autor", "23e:autor", "claude-opus-5-5")


class EsperaDeCuotaTests(ColaRealBase):
    def test_el_caso_del_04_10_la_espera_se_ve_con_su_calculo_y_su_eta(self):
        tramos, (f, u) = self.espera_del_04_10()
        self.assertEqual((f["pct_5h"], u["5h"]), (25, 0.0))        # el historial real: 2 filas propias → BASE × factor 1,0; y a las 20:32 la ventana ya se renovó
        v = tramos[0]
        self.assertEqual((v["estado"], v["etapa"], v["fase"]), ("esperando_cuota", "23e", "autor"))
        self.assertEqual((v["cuenta"], v["cuenta_clave"]), ("Claude (Cami)", "claude_cami"))
        self.assertEqual(v["calculo"], [{"ventana": "5h", "actual": 74.0, "pronostico": 25, "tope": 90}])
        self.assertEqual(v["calculo_texto"], "5 h 74 % + 25 % > tope 90 %")
        self.assertEqual(v["espera_desde"], "2026-10-04T18:01:30-03:00")
        self.assertEqual(v["reanuda"], "2026-10-04T20:32:00-03:00")          # la renovación de las 20:30 + los 2 min que ya se suman
        self.assertTrue(v["pronostico_debil"])
        # La ETA corrida: hora de reanudación + lo que falte de la cola, sin descontar tiempo transcurrido.
        reanuda = datetime.fromisoformat(v["reanuda"])
        for k in ("min", "esperado", "max"):
            self.assertGreaterEqual(datetime.fromisoformat(v["eta"][k]), reanuda, k)
        esperado_min = round((datetime.fromisoformat(v["eta"]["esperado"]) - reanuda).total_seconds() / 60, 1)
        self.assertLess(abs(esperado_min - v["restante_min"]["esperado"]), 1)             # la ETA se trunca al minuto
        # Falta 23e entero y no se descuenta nada: es el `restante()` desde la fase pendiente con 0 min transcurridos.
        self.assertEqual(v["restante_min"], self.cr.restante(self.cr.MANIFIESTO["etapa"], "23e", "autor", 0))
        self.assertEqual(v["modelo"], "claude-opus-5-5")             # el de la fase que espera, no el de la que acaba de terminar
        self.assertEqual(v["fases_hechas"][0]["etapa"], "23d")        # la historia no se pierde en la espera
        # La barra no cuenta la espera como trabajo: el avance es lo hecho hasta que empezó a esperar (3 h) sobre lo que falta.
        self.assertEqual(v["progreso_pct"], round(100 * 180 / (180 + v["restante_min"]["esperado"]), 1))
        self.assertEqual({t["progreso_pct"] for t in tramos}, {v["progreso_pct"]})        # y no se mueve con los latidos
        # La bitácora lo dice igual que antes, con el mismo cálculo.
        self.assertIn("⏳ Claude (Cami) sin margen para autor: 5 h 74 % + 25 % > tope 90 %. Se renueva a las 04-10 20:30: la cola espera",
                      (self.tmp / "ESTADO.md").read_text(encoding="utf-8"))
        # Al alcanzar, vuelve a «corriendo» sin restos de la espera.
        final = self.vivo_json()
        self.assertEqual(final["estado"], "corriendo")
        for campo in self.cr.CAMPOS_ESPERA:
            self.assertNotIn(campo, final)
        # Ya renovada, el re-chequeo de cada 10 min la deja seguir sin esperar los 2 min de margen que traía `reanuda`.
        self.assertTrue(self.RENUEVA <= self.reloj <= datetime.fromisoformat(v["reanuda"]), self.reloj)
        self.assertEqual(final["tiempo_muerto_min"], round((self.reloj - self.ARRANQUE).total_seconds() / 60, 1))

    def test_durante_la_espera_escrito_late_cada_5_min_y_no_se_vuelve_sin_senal(self):
        tramos, _ = self.espera_del_04_10()
        escritos = [datetime.fromisoformat(v["escrito"]) for v in tramos]
        self.assertGreaterEqual(len(escritos), 25)                        # 2 h 30 min en tramos de 5
        self.assertTrue(all(b - a == timedelta(minutes=5) for a, b in zip(escritos, escritos[1:])), "un latido cada 5 min")
        self.assertTrue(all(0 < s <= 300 for s in self.dormidas), "ningún sleep largo: la ficha no se congela")
        self.assertEqual(max(self.dormidas), 300)
        self.assertTrue(all(v["estado"] == "esperando_cuota" for v in tramos))
        # Pasadas 2 h con la sesión viva, la tarjeta sigue siendo «esperando cuota»: nunca «sin señal».
        tarde = datetime.fromisoformat(tramos[0]["escrito"]) + timedelta(hours=2, minutes=30)
        m = modelo_cola(tramos[0], tarde, True)
        self.assertEqual(m["tipo"], "espera_cuota")
        # Sin sesión viva y con el archivo de hace 2 h sí: la sesión murió.
        self.assertEqual(modelo_cola(tramos[0], tarde, False)["tipo"], "sin_senal")
        # El archivo que lee la página lo escribe el propio vivo(): ni tmp ni archivos sueltos.
        self.assertEqual(sorted(x.name for x in (self.tmp / "vivo").iterdir()), ["cola23.json"])

    def test_si_la_cuenta_ya_alcanza_la_cola_sigue_sin_esperar_la_hora_completa(self):
        # El usuario gastó menos de lo previsto: a los 35 min el 5 h baja a 60 y 60 + 25 ≤ 90.
        self.pct_5h = lambda reloj: 74.0 if reloj < self.ARRANQUE + timedelta(minutes=35) else 60.0
        tramos, (f, u) = self.espera_del_04_10()
        self.assertEqual(u["5h"], 60.0)
        self.assertEqual(sum(self.dormidas), 40 * 60)                     # se volvió a medir a los 10, 20, 30 y 40 min
        self.assertLess(self.reloj, self.RENUEVA)
        final = self.vivo_json()
        self.assertEqual(final["estado"], "corriendo")
        self.assertFalse(set(self.cr.CAMPOS_ESPERA) & set(final))
        # Lo esperado no cuenta como trabajo hecho: inicio_trabajo se corre por el tiempo muerto.
        self.assertEqual(final["tiempo_muerto_min"], 40.0)
        self.assertEqual(final["inicio_trabajo"], "2026-10-04T15:41:30-03:00")        # 3 h antes de las 18:01:30, más 40 min

    def test_si_no_hay_que_esperar_no_se_toca_vivo_y_si_la_renovacion_no_cabe_en_la_paciencia_se_pausa(self):
        self.pct_5h = lambda reloj: 50.0
        self.arrancar("corriendo", "23d", "rev1", "Codex", "gpt-5.6-terra medium")
        antes = self.vivo_json()
        self.cr.chequear_cuota("claude_cami", "autor", "23e:autor", "claude-opus-5-5")
        self.assertEqual((self.dormidas, self.vivo_json()), ([], antes))
        self.pct_5h = lambda reloj: 74.0
        self.cr.MANIFIESTO["paciencia_h"] = 1                             # la renovación es en 2 h 30 min
        with self.assertRaises(self.cr.Pausa) as p:
            self.cr.chequear_cuota("claude_cami", "autor", "23e:autor", "claude-opus-5-5")
        self.assertIn("5 h 74 % + 25 % > tope 90 %", p.exception.motivo)
        self.assertEqual(self.dormidas, [])
        self.assertFalse(set(self.cr.CAMPOS_ESPERA) & set(self.vivo_json()))


    def test_el_vivo_de_la_espera_es_el_que_escribe_vivo_y_esta_en_los_fixtures(self):
        tramos, _ = self.espera_del_04_10()
        generado = json.dumps(tramos[0], ensure_ascii=False, indent=1)
        ruta = FIXTURES / "vivo" / "esperando-cuota.json"
        if os.environ.get("REGENERAR_FIXTURES_VIVO"):
            ruta.write_text(generado, encoding="utf-8")
        self.assertEqual(ruta.read_text(encoding="utf-8"), generado)

    def test_el_vivo_corriendo_publica_las_cuentas_en_uso_y_el_pronostico_de_la_proxima_fase(self):
        self.arrancar("partiendo", "23d", "rev3", "Codex", "gpt-5.6-terra medium")
        self.cr.vivo(estado="corriendo")
        v = self.vivo_json()
        self.assertEqual(v["cuentas_en_uso"], ["claude_cami", "codex"])
        self.assertEqual(v["proximo"], {"cuenta": "claude_cami", "etapa": "23e", "fase": "autor", "pct_5h": 25, "pct_sem": 5, "debil": True})
        self.assertEqual(v["proximo_por_cuenta"]["claude_cami"], v["proximo"])
        self.assertEqual(set(v["proximo_por_cuenta"]), {"claude_cami", "codex"})
        generado = json.dumps(v, ensure_ascii=False, indent=1)
        ruta = FIXTURES / "vivo" / "corriendo-uso.json"
        if os.environ.get("REGENERAR_FIXTURES_VIVO"):
            ruta.write_text(generado, encoding="utf-8")
        self.assertEqual(ruta.read_text(encoding="utf-8"), generado)

    def test_la_primera_fase_de_la_cola_tambien_puede_esperar(self):
        # Sin fase anterior no hay inicio_fase ni inicio_trabajo: la espera igual se ve y al salir no revienta.
        self.manifiesto()
        self.cr.VIVO.clear()
        self.cr.vivo(nombre="cola23", motivo="x", estado="partiendo", lanzada=self.reloj.isoformat(timespec="seconds"), etapas=["23d", "23e"])
        tramos = []
        self.al_dormir = lambda: tramos.append(self.vivo_json())
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.cr.chequear_cuota("claude_cami", "autor", "23d:autor", "claude-opus-5-5")
        self.assertEqual(tramos[0]["estado"], "esperando_cuota")
        self.assertNotIn("progreso_pct", tramos[0])                  # todavía no hay trabajo hecho que medir
        final = self.vivo_json()
        self.assertEqual(final["estado"], "partiendo")                # etapa() fija «corriendo» enseguida
        self.assertNotIn("inicio_trabajo", final)
        self.assertFalse(set(self.cr.CAMPOS_ESPERA) & set(final))

    def test_un_vivo_que_no_se_puede_calcular_no_tira_la_cola(self):
        self.arrancar("corriendo", "23d", "rev1", "Codex", "gpt-5.6-terra medium")
        self.cr.MODELOS.write_text("", encoding="utf-8")              # modelos.toml roto: el avance es adorno, la cola sigue
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            self.cr.vivo()
        self.assertIn("no se pudo calcular el avance", salida.getvalue())
        self.assertEqual(self.vivo_json()["estado"], "corriendo")


class AvisosDeLaColaTests(ColaRealBase):
    """Espera, pausa y fin: texto simple, sin línea de comando, por el canal de avisos del panel 🔔."""

    def test_con_el_lado_nuevo_inactivo_la_espera_sale_por_avisar_de_siempre_y_no_queda_sin_aviso(self):
        self.espera_del_04_10()
        (envio,) = self.envios
        self.assertEqual(envio[:2], ["nodo-desplegar", "sugerir"])
        self.assertIn("Esta línea muestra el estado", envio[3])           # lo de hoy, tal cual
        (linea,) = self.lineas()
        self.assertEqual((linea["origen"], linea["id"], linea["linea"]), ("cola", "20261004-180100-abcd", f"cat {self.cr.ESTADO}"))
        self.assertFalse(self.ra.BANDEJA.exists())
        # Archivo viejo, de otra versión o con ok=false: tampoco está activo.
        import time as reloj_real
        for estado in ({"ultimo_ciclo": reloj_real.time() - 26 * 60}, {"version": 2}, {"ok": False}, {"ultimo_ciclo": "ayer"}):
            with self.subTest(estado=estado):
                self.lado_nuevo_activo(**estado)
                self.assertFalse(self.ra.bandeja_activa())
        (self.tmp / "avisos-bandeja.json").write_text("{roto", encoding="utf-8")
        self.assertFalse(self.ra.bandeja_activa())

    def test_con_el_lado_nuevo_activo_la_espera_es_una_linea_de_texto_en_el_registro_y_en_la_bandeja(self):
        self.lado_nuevo_activo()
        self.assertTrue(self.ra.bandeja_activa())
        self.espera_del_04_10()
        self.assertEqual(self.envios, [], "nada pasa por nodo-desplegar: es información, no un comando para copiar")
        (linea,) = self.lineas()
        self.assertEqual((linea["origen"], linea["nivel"], linea["texto"], linea["linea"], linea["id"]), ("cola", "alerta", TEXTO_ESPERA, None, None))
        (salida,) = self.lineas(self.ra.BANDEJA)
        self.assertEqual(set(salida), {"id", "momento", "texto"})
        self.assertEqual(salida["texto"], TEXTO_ESPERA)               # el mismo texto, una sola vez en cada lado
        self.assertRegex(salida["id"], r"^s-\d{8}-\d{6}-[0-9a-f]{8}$")
        self.assertNotIn("\n", salida["texto"])
        self.assertNotRegex(salida["texto"], r"\b(cat|tmux|echo|sudo|nodo-desplegar)\b")

    def test_una_espera_de_menos_de_15_min_no_avisa(self):
        self.lado_nuevo_activo()
        self.RENUEVA = self.ARRANQUE + timedelta(minutes=8)             # 8 min + los 2 de margen
        self.espera_del_04_10()
        self.assertEqual((self.envios, self.lineas(), self.ra.BANDEJA.exists()), ([], [], False))
        self.assertIn("la cola espera", (self.tmp / "ESTADO.md").read_text(encoding="utf-8"))     # la bitácora sí

    def test_la_espera_semanal_cruza_dias_y_el_aviso_dice_el_dia(self):
        self.lado_nuevo_activo()
        semanal = self.ARRANQUE + timedelta(days=2, hours=3)

        def medida(cid):
            ya = self.reloj >= semanal
            return {"5h": 10.0, "sem": 10.0 if ya else 72.0, "renueva_5h": None, "renueva_sem": None if ya else semanal,
                    "momento": None, "fuente": "fresco"}
        self.cr.medir = medida
        self.arrancar("corriendo", "23d", "rev1", "Codex", "gpt-5.6-terra medium")
        self.cr.MANIFIESTO["paciencia_h"] = 100
        tramos = []
        self.al_dormir = lambda: tramos.append(self.vivo_json())
        self.cr.chequear_cuota("claude_cami", "autor", "23e:autor", "claude-opus-5-5")
        v = tramos[0]
        self.assertEqual(v["calculo_texto"], "semanal 72 % + 5 % > tope 75 %")
        (salida,) = self.lineas(self.ra.BANDEJA)
        self.assertIn("Sigue sola a las 21:03 del 06-10", salida["texto"])
        # La tarjeta también dice el día, no solo la hora.
        self.assertEqual(modelo_cola(v, self.ARRANQUE, True)["espera"]["reanuda"], "06-10 21:03")
        self.assertEqual(modelo_cola(v, datetime.fromisoformat(v["reanuda"]) - timedelta(minutes=1), True)["espera"]["reanuda"], "21:03")

    def correr_cola(self, etapa_extra="", correr=None, pruebas="", desde=None, nombre="cola9", despliegue="nada", motivo="prueba de avisos"):
        """main() de verdad con un manifiesto de una etapa. Devuelve (rc, error o None)."""
        (self.tmp / "9.md").write_text("# Encargo 9\n", encoding="utf-8")
        manifiesto = self.tmp / "cola-9.toml"
        manifiesto.write_text(f'nombre = "{nombre}"\nmotivo = "{motivo}"\ndespliegue = "{despliegue}"\npaciencia_h = 1\npruebas = [{pruebas}]\n'
                              '[[etapa]]\nid = "9"\nencargo = "9.md"\nautor = "claude_cami"\nrevisor = "codex"\nvueltas = 1\n'
                              'modelo_autor = "claude-sonnet-5-5"\nesfuerzo_autor = "medium"\nmodelo_fix = "claude-sonnet-5-5"\n'
                              'modelo_rev = "gpt-5.6-terra"\nesfuerzo_rev = "medium"\n' + etapa_extra, encoding="utf-8")
        self.pct_5h = lambda reloj: 10.0

        def correr_falso(cid, prompt, nombre_log, mod=None, herramientas=""):
            if correr:
                correr(cid, nombre_log)
            return {"rc": 0, "min": 1.0, "tokens": None, "sin_cuota": False, "modelo_real": None}
        self.cr.correr = correr_falso
        argv = ["cola-run.py", str(manifiesto), *(["--desde", desde] if desde else [])]
        error = None
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                rc = self.cr.principal()
            except BaseException as e:      # noqa: BLE001 — principal() relanza todo después de avisar
                rc, error = None, e
        return rc, error

    def veredicto(self, desplegable):
        def hacer(cid, nombre_log):
            if nombre_log.endswith("rev1") or nombre_log.endswith("rev2"):
                (self.tmp / "9r-RESULTADO.md").write_text("# Revisión\n\nVEREDICTO: " + ("DESPLEGABLE" if desplegable else "NO DESPLEGABLE") + "\n", encoding="utf-8")
        return hacer

    def texto_unico(self):
        """El único aviso que dejó la cola, ya sea por la bandeja o por avisar() de siempre."""
        (linea,) = self.lineas()
        return linea

    def test_el_fin_de_una_cola_avisa_en_texto_simple_por_cada_camino(self):
        casos = (
            ("terminada", dict(correr=self.veredicto(True)), 0, "✅ La cola cola9 terminó: revisada, y no cambió nada que desplegar."),
            ("detenida", dict(correr=self.veredicto(False)), 1, "⛔ La cola cola9 se detuvo: la etapa 9 quedó NO DESPLEGABLE. No se desplegó nada."),
        )
        for nombre, kw, rc_esperado, texto in casos:
            for activo in (True, False):
                with self.subTest(caso=nombre, lado_nuevo=activo):
                    self.setUp()
                    if activo:
                        self.lado_nuevo_activo()
                    kw2 = dict(kw)
                    rc, error = self.correr_cola(**kw2)
                    self.assertEqual((rc, error), (rc_esperado, None))
                    linea = self.texto_unico()
                    if activo:
                        self.assertEqual((linea["texto"], linea["linea"], self.sugeridos()), (texto, None, []))
                        self.assertEqual([x["texto"] for x in self.lineas(self.ra.BANDEJA)], [texto])
                    else:     # el de siempre: nodo-desplegar sugerir, con su línea que muestra el estado
                        self.assertEqual(len(self.sugeridos()), 1)
                        self.assertEqual(self.sugeridos()[0][:2], ["nodo-desplegar", "sugerir"])
                        self.assertEqual(linea["linea"], f"cat {self.cr.ESTADO}")
                        self.assertFalse(self.ra.BANDEJA.exists())

    def test_una_pausa_manda_texto_y_la_linea_para_reanudar_va_solo_en_el_registro(self):
        def sin_cuota(cid, nombre_log):
            raise self.cr.Pausa("Claude (Cami) se quedó sin cuota a mitad de autor (3.0 min)", "9:autor")
        self.lado_nuevo_activo()
        rc, error = self.correr_cola(correr=sin_cuota)
        self.assertEqual((rc, error), (3, None))
        linea = self.texto_unico()
        self.assertEqual(linea["nivel"], "alerta")
        self.assertEqual(linea["texto"], "⏸️ La cola cola9 está en pausa: Claude (Cami) se quedó sin cuota a mitad de autor (3.0 min). "
                                         "Nada quedó desplegado. Se reanuda desde 9:autor con la línea que muestra 🔔 Avisos, en 🧵 Encargos.")
        self.assertRegex(linea["linea"], r"^tmux new-session -d -s cola9 python3 \S+cola-run\.py \S+cola-9\.toml --desde 9:autor$")
        self.assertNotIn("tmux", linea["texto"])
        self.assertEqual(self.lineas(self.ra.BANDEJA)[0]["texto"], linea["texto"])
        self.assertNotIn("tmux", json.dumps(self.lineas(self.ra.BANDEJA)))
        self.assertEqual(self.sugeridos(), [])
        # Solo la pausa lleva `linea`: un fin sin nada que copiar no inventa una.
        self.setUp()
        self.lado_nuevo_activo()
        self.correr_cola(correr=self.veredicto(True))
        self.assertIsNone(self.texto_unico()["linea"])

    def test_sin_autorizacion_caida_y_fallas_nuevas_avisan_en_texto(self):
        # sin autorización: la etapa fija Claude Fable 5.1, que tiene candado; la cola pide autorización y nadie da el ✅.
        self.lado_nuevo_activo()
        (self.tmp / "9.md").write_text("# Encargo 9\n", encoding="utf-8")
        ruta = self.tmp / "cola-9.toml"
        ruta.write_text('nombre = "cola9"\nmotivo = "x"\nespera = 1\npruebas = []\n[[etapa]]\nid = "9"\nencargo = "9.md"\nautor = "claude_cami"\n'
                        'revisor = "codex"\nmodelo_autor = "claude-fable-5-1"\n', encoding="utf-8")
        with mock.patch.object(sys, "argv", ["cola-run.py", str(ruta)]), contextlib.redirect_stdout(io.StringIO()):
            rc = self.cr.principal()
        self.assertEqual(rc, 4)
        textos = [x["texto"] for x in self.lineas()]
        self.assertEqual(len(textos), 2)         # la petición (lleva su ✅ en Telegram) y el aviso de que no corrió nada
        self.assertEqual(textos[1], "⛔ La cola cola9 no corrió: no se autorizó claude-fable-5-1. Para lanzarla sin esos modelos, "
                                    "cambia la naturaleza o fija otro modelo en el manifiesto.")
        self.assertEqual([x["texto"] for x in self.lineas(self.ra.BANDEJA)], [textos[1]])     # la petición sigue por nodo-desplegar: es una acción
        self.assertEqual([e[1] for e in self.envios if e[1] == "sugerir"], ["sugerir"])
        # caída: un error inesperado a mitad de la corrida.
        self.setUp()
        self.lado_nuevo_activo()

        def cae(cid, nombre_log):
            raise RuntimeError("boom")
        rc, error = self.correr_cola(correr=cae)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(self.texto_unico()["texto"], "💥 La cola cola9 se cayó por un error inesperado (RuntimeError). Lo que estaba a medias "
                                                      "no se desplegó. El final del registro está en la bitácora de 🧵 Encargos.")
        self.assertEqual(self.vivo_json_de("cola9")["estado"], "caída")
        # fallas nuevas en las pruebas: la suite pasa al empezar y falla al terminar.
        self.setUp()
        self.lado_nuevo_activo()
        (self.tmp / "suite.py").write_text('import os, sys\nif os.path.exists("marca"):\n    print("FAIL: test_x (m.C)")\n    sys.exit(1)\n', encoding="utf-8")
        desplegable = self.veredicto(True)

        def deja_una_falla(cid, nombre_log):
            desplegable(cid, nombre_log)
            (self.tmp / "marca").write_text("1")
        rc, error = self.correr_cola(pruebas='"suite.py"', correr=deja_una_falla, despliegue="nada")
        self.assertEqual((rc, error), (1, None))
        self.assertEqual(self.texto_unico()["texto"], "⛔ La cola cola9 quedó revisada, pero dejó 1 fallas nuevas en las pruebas. No se desplegó nada.")

    def vivo_json_de(self, nombre):
        return json.loads((self.tmp / "vivo" / f"{nombre}.json").read_text(encoding="utf-8"))

    def test_si_la_bandeja_no_se_puede_escribir_el_aviso_sale_por_avisar_y_no_se_pierde(self):
        self.lado_nuevo_activo()
        self.ra.BANDEJA.mkdir()           # un directorio donde va el archivo: abrirlo falla
        self.espera_del_04_10()
        self.assertEqual(len(self.envios), 1)
        self.assertEqual(len(self.lineas()), 1)
        # Con el volumen cerrado (sin /opt/nodo/datos montado) la bandeja ni se intenta.
        self.ra.BANDEJA.rmdir()
        with mock.patch.object(self.ra.os.path, "ismount", return_value=False), mock.patch.object(self.ra, "BANDEJA", self.ra.VOLUMEN / "avisos-salida.jsonl"):
            self.assertFalse(self.ra.a_la_bandeja("⏳ algo"))

    def test_pruebas_lanza_las_suites_con_la_marca_de_aislamiento(self):
        suite = self.tmp / "suite-marca.py"
        marca = self.tmp / "marca.txt"
        suite.write_text("import os, pathlib, sys\n"
                         f"pathlib.Path({str(marca)!r}).write_text(os.environ.get('NODO_PRUEBAS', ''))\n"
                         "sys.exit(0 if os.environ.get('NODO_PRUEBAS') == '1' else 1)\n", encoding="utf-8")
        self.cr.MANIFIESTO = {"pruebas": [str(suite)]}
        self.assertEqual(self.cr.pruebas()[0], set())
        self.assertEqual(marca.read_text(encoding="utf-8"), "1")

    def test_los_secretos_no_llegan_a_la_bandeja_y_la_bandeja_no_crece_sin_tope(self):
        token = "7123456789:AAH" + "k3J9-xQ_w" * 4
        self.assertTrue(self.ra.a_la_bandeja(f"⛔ falló con {token} y chat_id=5900000017\ny otra línea"))
        (x,) = self.lineas(self.ra.BANDEJA)
        self.assertNotIn(token, json.dumps(x))
        self.assertNotIn("5900000017", json.dumps(x))
        self.assertNotIn("\n", x["texto"])
        for i in range(self.ra.BANDEJA_TOPE + 5):
            self.ra.a_la_bandeja(f"aviso {i}")
        n = len(self.lineas(self.ra.BANDEJA))
        self.assertLessEqual(n, self.ra.BANDEJA_TOPE)
        self.assertEqual(self.lineas(self.ra.BANDEJA)[-1]["texto"], f"aviso {self.ra.BANDEJA_TOPE + 4}")
        self.assertEqual(oct(self.ra.BANDEJA.stat().st_mode & 0o777), "0o644")
        self.assertFalse(self.ra.BANDEJA.is_symlink())

    # ---- arreglos vuelta 1 (24r1): la bandeja no cuelga a la cola y no pierde avisos concurrentes

    def test_una_bandeja_que_es_un_fifo_no_cuelga_a_la_cola_y_cae_al_camino_de_siempre(self):
        # 24r1 hallazgo 1: open(O_WRONLY) sobre un FIFO espera un lector para siempre. Con un lector real
        # abierto (el caso que SÍ abre) el objeto se rechaza por no ser archivo común; sin lector, ENXIO.
        os.mkfifo(self.ra.BANDEJA)
        for con_lector in (False, True):
            lector = os.open(self.ra.BANDEJA, os.O_RDONLY | os.O_NONBLOCK) if con_lector else None
            try:
                resultado = []
                hilo = threading.Thread(target=lambda: resultado.append(self.ra.a_la_bandeja("⏳ prueba")), daemon=True)
                hilo.start()
                hilo.join(5)
                self.assertFalse(hilo.is_alive(), "a_la_bandeja se colgó sobre un FIFO")
                self.assertEqual(resultado, [False])
            finally:
                if lector is not None:
                    os.close(lector)
        # y la cola entera sigue por avisar() (nodo-desplegar) y deja su línea en el registro
        self.lado_nuevo_activo()
        self.espera_del_04_10()
        self.assertEqual(len(self.envios), 1)
        self.assertEqual(len(self.lineas()), 1)

    def test_la_bandeja_rechaza_lo_que_no_es_un_archivo_comun_propio(self):
        # enlace simbólico final, enlace duro (otro nombre) y un directorio: todos devuelven False sin escribir.
        blanco = self.tmp / "blanco.txt"
        blanco.write_text("no tocar\n", encoding="utf-8")
        self.ra.BANDEJA.symlink_to(blanco)
        self.assertFalse(self.ra.a_la_bandeja("⏳ x"))
        self.assertEqual(blanco.read_text(encoding="utf-8"), "no tocar\n")
        self.ra.BANDEJA.unlink()
        os.link(blanco, self.ra.BANDEJA)
        self.assertFalse(self.ra.a_la_bandeja("⏳ x"))
        self.assertEqual(blanco.read_text(encoding="utf-8"), "no tocar\n")
        self.ra.BANDEJA.unlink()
        self.ra.BANDEJA.mkdir()
        self.assertFalse(self.ra.a_la_bandeja("⏳ x"))
        self.ra.BANDEJA.rmdir()
        # un cerrojo que es un FIFO tampoco cuelga: sin cerrojo no se escribe y se cae al camino de siempre.
        self.ra.BANDEJA_CERROJO.unlink(missing_ok=True)
        os.mkfifo(self.ra.BANDEJA_CERROJO)
        resultado = []
        hilo = threading.Thread(target=lambda: resultado.append(self.ra.a_la_bandeja("⏳ x")), daemon=True)
        hilo.start()
        hilo.join(5)
        self.assertEqual((hilo.is_alive(), resultado, self.ra.BANDEJA.exists()), (False, [False], False))

    def sueno_real(self):
        parche = mock.patch("time.sleep", SUEÑO_REAL)
        parche.start()
        self.addCleanup(parche.stop)

    def test_el_recorte_no_pierde_la_linea_que_otra_cola_agrega_en_medio(self):
        # 24r1 hallazgo 2: A lee la bandeja llena para recortarla; B agrega en ese instante; A hace replace.
        # Sin cerrojo la línea de B desaparece. Con cerrojo B espera a que A termine, y las dos quedan.
        ra = self.ra
        for i in range(ra.BANDEJA_TOPE):
            self.assertTrue(ra.a_la_bandeja(f"previo {i}"))
        self.assertEqual(len(self.lineas(ra.BANDEJA)), ra.BANDEJA_TOPE)
        en_el_recorte, sigue = threading.Event(), threading.Event()
        replace_real = os.replace

        def replace_tras_una_pausa(origen, destino):      # el punto exacto de la carrera: ya leyó, todavía no hizo replace
            if not en_el_recorte.is_set():                # solo A se detiene; B (si llega a recortar) pasa de largo
                en_el_recorte.set()
                sigue.wait(10)
            return replace_real(origen, destino)
        resultados = {}
        self.sueno_real()
        with mock.patch.object(ra.os, "replace", replace_tras_una_pausa):
            a = threading.Thread(target=lambda: resultados.setdefault("a", ra.a_la_bandeja("aviso A")))
            a.start()
            self.assertTrue(en_el_recorte.wait(10))
            b = threading.Thread(target=lambda: resultados.setdefault("b", ra.a_la_bandeja("aviso B")))
            b.start()
            SUEÑO_REAL(0.3)                 # B ya está esperando el cerrojo (o, sin cerrojo, ya habría escrito)
            sigue.set()
            a.join(10)
            b.join(10)
        self.assertEqual(resultados, {"a": True, "b": True})
        textos = [x["texto"] for x in self.lineas(ra.BANDEJA)]
        self.assertIn("aviso A", textos)
        self.assertIn("aviso B", textos)
        self.assertEqual(len(textos), len(set(textos)))

    def test_muchas_colas_a_la_vez_dejan_cada_aviso_una_vez_y_el_cerrojo_no_cuelga(self):
        ra = self.ra

        def en_paralelo(n):
            hilos = [threading.Thread(target=ra.a_la_bandeja, args=(f"cola {i}",)) for i in range(n)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join(30)
            self.assertFalse(any(h.is_alive() for h in hilos))
        self.sueno_real()
        en_paralelo(40)                       # bajo el tope: ni uno se pierde ni se duplica
        textos = [x["texto"] for x in self.lineas(ra.BANDEJA)]
        self.assertEqual(sorted(textos), sorted(f"cola {i}" for i in range(40)))
        with mock.patch.object(ra, "BANDEJA_TOPE", 30), mock.patch.object(ra, "BANDEJA_QUEDAN", 20):
            en_paralelo(40)                   # recortando a media carrera: el recorte descarta lo viejo, pero nunca deja una línea rota ni repetida
        filas = self.lineas(ra.BANDEJA)
        self.assertLessEqual(len(filas), 40 + 40)
        self.assertEqual(len({x["id"] for x in filas}), len(filas))
        self.assertTrue(all(set(x) == {"id", "momento", "texto"} for x in filas))
        # cerrojo ocupado por otro proceso más tiempo del que se espera: False (cae a avisar), sin colgarse
        with mock.patch.object(ra, "BANDEJA_CERROJO_S", 0.2):
            fd = ra._cerrojo()
            try:
                t0 = time.monotonic()
                self.assertFalse(ra.a_la_bandeja("⏳ con el cerrojo tomado"))
                self.assertLess(time.monotonic() - t0, 3)
            finally:
                os.close(fd)
        self.assertNotIn("⏳ con el cerrojo tomado", [x["texto"] for x in self.lineas(ra.BANDEJA)])

    def test_la_bandeja_se_recorta_tambien_por_bytes_para_que_avisos_py_la_pueda_leer(self):
        ra = self.ra
        self.assertLess(ra.BANDEJA_BYTES_TOPE, 256 * 1024)       # avisos.BANDEJA_MAX_BYTES: más que eso no lo lee
        grande = "ñ" * ra.MAX_BANDEJA_TEXTO
        for _ in range(ra.BANDEJA_TOPE - 1):                     # bajo el tope de líneas, pero pesa más que el de bytes
            ra.a_la_bandeja(grande)
        self.assertLessEqual(ra.BANDEJA.stat().st_size, 256 * 1024)


class ReanudacionTests(ColaRealBase):
    """`--desde` conserva la historia: sobre una copia del vivo/cola23.json y de la bitácora REALES."""

    def setUp(self):
        super().setUp()
        self.reloj = datetime.fromisoformat("2026-10-05T12:00:00-03:00")
        (self.tmp / "vivo").mkdir()
        shutil.copy(FIXTURES / "vivo" / "cola23-real.json", self.tmp / "vivo" / "cola23.json")
        shutil.copy(FIXTURES / "encargos" / "COLA-ESTADO-cola23.md", self.tmp / "ESTADO.md")
        self.previo = self.vivo_json()
        self.bitacora_antes = (self.tmp / "ESTADO.md").read_bytes()
        # El manifiesto real de la cola 23, sin las suites de verdad ni el despliegue; los archivos de encargo, de mentira.
        texto = (ENCARGOS_DIR / "cola-23.toml").read_text(encoding="utf-8")
        texto = re.sub(r"^pruebas = .*$", "pruebas = []", texto, flags=re.M)
        texto = re.sub(r'^despliegue = "[^"]*"', 'despliegue = "nada"', texto, flags=re.M)
        self.manifiesto_23 = self.tmp / "cola-23.toml"
        self.manifiesto_23.write_text(texto, encoding="utf-8")
        for et in tomllib.loads(texto)["etapa"]:
            (self.tmp / et["encargo"]).write_text("# encargo\n", encoding="utf-8")
        self.snapshots = []
        self.pct_5h = lambda reloj: 10.0

        def correr(cid, prompt, nombre_log, mod=None, herramientas=""):
            self.snapshots.append((nombre_log, self.vivo_json()))
            self.reloj += timedelta(minutes=5)
            if "rev" in nombre_log:
                et = nombre_log.split("-")[0]
                (self.tmp / f"{et}r-RESULTADO.md").write_text("VEREDICTO: DESPLEGABLE\n", encoding="utf-8")
            return {"rc": 0, "min": 5.0, "tokens": None, "sin_cuota": False, "modelo_real": None}
        self.cr.correr = correr

    def lanzar(self, *argumentos):
        with mock.patch.object(sys, "argv", ["cola-run.py", str(self.manifiesto_23), *argumentos]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.cr.principal()

    def test_el_vivo_real_es_el_que_dejo_la_cola_23_y_pierde_la_historia_sin_desde(self):
        self.assertEqual((self.previo["estado"], self.previo["lanzada"]), ("detenida", "2026-10-04T20:47:42-03:00"))
        self.assertEqual(self.previo["etapas"], ["23a", "23b", "23c", "23d", "23e"])
        self.assertEqual(len(self.previo["fases_hechas"]), 6)             # las de 23a–23c ya se habían perdido en un relanzamiento
        # Con 5 corridas de la 23 en la bitácora, ninguna dice que sea una reanudación.
        self.assertEqual(self.bitacora_antes.decode().count("## Cola cola23 (cola-run):"), 5)
        self.assertNotRegex(self.bitacora_antes.decode(), r"(?m)^## Reanudación desde .* · cola cola23")

    def test_relanzar_conserva_lanzada_y_fases_hechas_agrega_relanzamientos_y_el_progreso_no_baja_a_0(self):
        self.assertEqual(self.lanzar("--desde", "23d:fix2"), 0)
        (nombre0, v0), *resto = self.snapshots
        self.assertEqual(nombre0, "23d-fix2")
        self.assertEqual(v0["lanzada"], self.previo["lanzada"])
        self.assertEqual(v0["fases_hechas"], self.previo["fases_hechas"])            # lo anterior, intacto
        self.assertEqual(v0["relanzamientos"], [{"momento": "2026-10-05T12:00:00-03:00", "desde": "23d:fix2"}])
        self.assertGreater(v0["progreso_pct"], 50)                                    # no vuelve a 0 %
        final = self.vivo_json()
        self.assertEqual(final["estado"], "terminada")
        self.assertEqual(final["fases_hechas"][:6], self.previo["fases_hechas"])
        self.assertEqual([(f["etapa"], f["fase"]) for f in final["fases_hechas"][6:]],
                         [("23d", "fix2"), ("23d", "rev3"), ("23e", "autor"), ("23e", "rev1")])
        self.assertEqual(final["lanzada"], self.previo["lanzada"])
        # Un segundo relanzamiento suma, no pisa.
        self.snapshots.clear()
        self.assertEqual(self.lanzar("--desde", "23e:autor"), 0)
        self.assertEqual([r["desde"] for r in self.vivo_json()["relanzamientos"]], ["23d:fix2", "23e:autor"])

    def test_inicio_trabajo_se_corre_por_el_hueco_y_la_barra_no_cuenta_la_espera_como_trabajo(self):
        self.lanzar("--desde", "23d:fix2")
        v0 = self.snapshots[0][1]
        previo_hecho = (datetime.fromisoformat(self.previo["escrito"]) - datetime.fromisoformat(self.previo["inicio_trabajo"])).total_seconds()
        hecho_al_partir = (self.ARRANQUE.replace(year=2026, month=10, day=5, hour=12, minute=0, second=0) - datetime.fromisoformat(v0["inicio_trabajo"])).total_seconds()
        self.assertEqual(hecho_al_partir, previo_hecho)                  # lo que llevaba hecho, no el hueco hasta las 12:00
        self.assertGreater(v0["tiempo_muerto_min"], 9 * 60)              # de las 02:00 a las 12:00 nadie trabajó
        self.assertLessEqual(datetime.fromisoformat(v0["inicio_trabajo"]), datetime.fromisoformat(v0["escrito"]))
        # Si se corta en plena espera de cuota, el trabajo llega hasta que empezó a esperar y no hasta el último latido.
        plena_espera = dict(self.previo, estado="esperando_cuota", espera_desde="2026-10-05T00:30:00-03:00", escrito="2026-10-05T02:00:00-03:00")
        (self.tmp / "vivo" / "cola23.json").write_text(json.dumps(plena_espera), encoding="utf-8")
        self.snapshots.clear()
        # El reloj de la prueba trae fracciones de segundo: `time.sleep` está parchado para toda la suite y la espera con
        # `timeout` de subprocess (los git de la primera corrida) duerme de a milisegundos por ahí. El vivo se escribe con
        # segundos enteros, así que se compara desde el segundo entero (era la prueba inestable de la 46a y la 46b).
        arranque = self.reloj.replace(microsecond=0)
        self.lanzar("--desde", "23d:fix2")
        hecho = (arranque - datetime.fromisoformat(self.snapshots[0][1]["inicio_trabajo"])).total_seconds()
        self.assertEqual(hecho, (datetime.fromisoformat("2026-10-05T00:30:00-03:00") - datetime.fromisoformat(self.previo["inicio_trabajo"])).total_seconds())

    def test_la_bitacora_solo_crece_y_el_encabezado_de_una_reanudacion_lo_dice(self):
        self.lanzar("--desde", "23d:fix2")
        despues = (self.tmp / "ESTADO.md").read_bytes()
        self.assertTrue(despues.startswith(self.bitacora_antes), "la bitácora nunca se reescribe: solo se agrega")
        nuevo = despues[len(self.bitacora_antes):].decode()
        self.assertIn("\n## Reanudación desde 23d:fix2 · cola cola23 · 05-10 12:00\n", nuevo)
        self.assertIn("Motivo de la cola: Reparto editable, 🔔 Avisos, acciones de ⏰ y trabajador de PC-2503 (encargos 23a–23d).", nuevo)
        self.assertNotIn("## Cola cola23", nuevo)
        # Sin --desde es una cola nueva: encabezado de siempre, VIVO parte vacío y no hereda nada.
        antes = despues
        self.snapshots.clear()
        self.lanzar()
        v0 = self.snapshots[0][1]
        self.assertNotIn("relanzamientos", v0)
        self.assertNotEqual(v0["lanzada"], self.previo["lanzada"])
        self.assertEqual(len(v0["fases_hechas"]) if "fases_hechas" in v0 else 0, 0)
        nuevo = (self.tmp / "ESTADO.md").read_bytes()
        self.assertTrue(nuevo.startswith(antes))
        self.assertIn("## Cola cola23 (cola-run): ", nuevo[len(antes):].decode())

    def test_si_el_vivo_anterior_no_existe_o_esta_roto_el_relanzamiento_parte_vacio(self):
        (self.tmp / "vivo" / "cola23.json").write_text("{roto", encoding="utf-8")
        self.assertEqual(self.lanzar("--desde", "23e:autor"), 0)
        v0 = self.snapshots[0][1]
        self.assertNotIn("relanzamientos", v0)
        self.assertIn("Reanudación desde 23e:autor", (self.tmp / "ESTADO.md").read_text(encoding="utf-8"))


class PronosticoPorFactorTests(ColaRealBase):
    HISTORIAL_REAL = FIXTURES / "encargos" / "historial-34.jsonl"

    def sin_factor(self):
        """El modelos.toml de antes del encargo 24: sin [factor_modelo]."""
        texto = self.cr.MODELOS.read_text(encoding="utf-8")
        self.assertEqual(texto.count("\n[factor_modelo]\n"), 1)
        cr = previas._cargar(f"cola_run_sin_{id(self)}", ENCARGOS_DIR / "cola-run.py")
        sin = self.tmp / "sin-factor.toml"
        sin.write_text(re.sub(r"\n\[factor_modelo\]\n(?:\"[^\n]*\n)+", "\n", texto), encoding="utf-8")
        self.assertNotIn("factor_modelo", tomllib.loads(sin.read_text(encoding="utf-8")))
        cr.MODELOS, cr.HISTORIAL = sin, self.cr.HISTORIAL
        cr.REGISTROS = self.cr.REGISTROS
        cr._AP_MOD = self.cr._AP_MOD        # el mismo catálogo: `simular` deja D en el temporal (48r2-1)
        return cr

    def test_el_historial_real_son_34_filas_y_claude_cami_no_tiene_3_de_autor(self):
        filas = [json.loads(x) for x in self.HISTORIAL_REAL.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(filas), 34)
        autor_cami = [h for h in filas if h["cuenta"] == "claude_cami" and h["rol"] == "autor"]
        self.assertEqual({h["modelo"] for h in autor_cami}, {"claude-opus-5-5"})
        self.assertEqual(len(autor_cami), 2)

    def test_sin_historial_del_modelo_sale_la_base_por_el_factor_y_dice_debil_y_el_factor(self):
        cr = self.cr
        self.assertEqual(cr.factores(), {"claude-opus-5-5": 1.0, "claude-sonnet-5-5": 0.61, "claude-haiku-4-5": 0.25})
        for modelo, k in (("claude-opus-5-5", 1.0), ("claude-sonnet-5-5", 0.61), ("claude-haiku-4-5", 0.25)):
            with self.subTest(modelo=modelo):
                f = cr.pronostico("claude_cami", "autor", modelo)
                self.assertEqual((f["pct_5h"], f["pct_sem"]), (round(25 * k, 2) if k != 1.0 else 25, round(5 * k, 2) if k != 1.0 else 5))
                self.assertTrue(f["debil"])
                self.assertEqual(f["por_factor"], k)
                self.assertEqual(f["min"], 12)         # los minutos no se escalan: el costo no mide el tiempo
        self.assertEqual(cr.etiqueta_pronostico(cr.pronostico("claude_cami", "autor", "claude-sonnet-5-5")), "débil, factor 0,61")
        self.assertEqual(cr.etiqueta_pronostico(cr.pronostico("claude_cami", "autor", "claude-haiku-4-5")), "débil, factor 0,25")
        self.assertEqual(cr.etiqueta_pronostico(cr.pronostico("claude_cami", "autor", "claude-opus-5-5")), "débil")

    def test_las_filas_de_otro_modelo_se_normalizan_antes_de_la_mediana(self):
        cr = self.cr
        # claude_cami como revisor tiene filas de Sonnet (22b, 22c): sus deltas medidos ya son «de Sonnet».
        f_sonnet = cr.pronostico("claude_cami", "rev", "claude-sonnet-5-5")
        self.assertTrue(f_sonnet["por_modelo"])      # 4 filas propias del modelo: la mediana medida, sin factor
        self.assertIsNone(f_sonnet["por_factor"])
        # Pedir Haiku normaliza esas mismas filas (÷ 0,61) y las multiplica por 0,25.
        f_haiku = cr.pronostico("claude_cami", "rev", "claude-haiku-4-5")
        self.assertFalse(f_haiku["por_modelo"])
        self.assertEqual((f_haiku["por_factor"], f_haiku["debil"]), (0.25, True))
        medido = f_sonnet["pct_5h"]
        self.assertAlmostEqual(f_haiku["pct_5h"], round(statistics_mediana_de_cami_rev_normalizada(self.HISTORIAL_REAL) * 0.25, 1), places=1)
        self.assertLess(f_haiku["pct_5h"], medido)

    def test_con_3_filas_propias_del_modelo_se_usa_la_mediana_medida(self):
        cr = self.cr
        base = json.loads(self.HISTORIAL_REAL.read_text(encoding="utf-8").splitlines()[28])      # 23b autor de Claude (Cami)
        filas = []
        for delta, sem in ((4.0, 0.5), (5.0, 0.5), (6.0, 1.0)):
            fila = dict(base, modelo="claude-sonnet-5-5", medicion="fresco", min=3.0, pct_5h=[10.0, 10.0 + delta], pct_sem=[20.0, 20.0 + sem])
            filas.append(json.dumps(fila, ensure_ascii=False))
        with cr.HISTORIAL.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(filas) + "\n")
        f = cr.pronostico("claude_cami", "autor", "claude-sonnet-5-5")
        self.assertEqual((f["pct_5h"], f["pct_sem"], f["min"]), (5.0, 0.5, 3.0))
        self.assertTrue(f["por_modelo"])
        self.assertIsNone(f["por_factor"])
        self.assertFalse(f["debil"])
        self.assertEqual(cr.etiqueta_pronostico(f), "")
        # Opus sigue sin sus 3 filas propias: las de Sonnet entran normalizadas (÷ 0,61) y × 1.
        fo = cr.pronostico("claude_cami", "autor", "claude-opus-5-5")
        self.assertTrue(fo["debil"])
        self.assertFalse(fo["por_modelo"])

    def test_un_modelo_de_codex_sin_factor_sale_igual_que_hoy_y_lo_dice(self):
        antes = self.sin_factor()
        for cuenta, rol, modelo in (("codex", "rev", "gpt-5.6-terra"), ("codex", "autor", "gpt-5.6-luna"), ("codex", "fix", "gpt-reserve"),
                                    ("claude_cami", "autor", "claude-fable-5-1")):
            with self.subTest(modelo=modelo):
                hoy, ahora = antes.pronostico(cuenta, rol, modelo), self.cr.pronostico(cuenta, rol, modelo)
                self.assertEqual({k: ahora[k] for k in ("min", "pct_5h", "pct_sem", "debil", "n", "por_modelo")},
                                 {k: hoy[k] for k in ("min", "pct_5h", "pct_sem", "debil", "n", "por_modelo")})
                self.assertTrue(ahora["sin_factor"])
        luna = self.cr.pronostico("codex", "autor", "gpt-5.6-luna")
        self.assertIsNone(luna["por_factor"])
        self.assertEqual(self.cr.etiqueta_pronostico(luna), "sin factor")
        self.assertEqual(self.cr.etiqueta_pronostico(self.cr.pronostico("codex", "rev", "gpt-5.6-terra")), "")      # medido: no hay nada que decir

    def test_los_factores_rotos_valen_sin_factor_y_nunca_cero(self):
        cr = self.cr
        for roto in ("0", "-1", "0.0", '"x"', "true"):
            with self.subTest(factor=roto):
                cr.MODELOS.write_text(cr.MODELOS.read_text(encoding="utf-8").replace('"claude-sonnet-5-5" = 0.61', f'"claude-sonnet-5-5" = {roto}'), encoding="utf-8")
                self.assertNotIn("claude-sonnet-5-5", cr.factores())
                self.assertGreater(cr.pronostico("claude_cami", "autor", "claude-sonnet-5-5")["pct_5h"], 0)
                cr.MODELOS.write_text(cr.MODELOS.read_text(encoding="utf-8").replace(f'"claude-sonnet-5-5" = {roto}', '"claude-sonnet-5-5" = 0.61'), encoding="utf-8")

    def simular(self, cr, manifiesto):
        with mock.patch.object(sys, "argv", ["cola-run.py", str(manifiesto), "--simular"]), contextlib.redirect_stdout(io.StringIO()) as salida, \
                contextlib.redirect_stderr(io.StringIO()):
            cr.medir = lambda cid: {"5h": 10.0, "sem": 20.0, "renueva_5h": None, "renueva_sem": None, "momento": None, "fuente": "fresco"}
            cr.E = cr.D = self.tmp
            cr.SIMULANDO = True
            self.assertEqual(cr.main(), 0)
        return salida.getvalue().splitlines()

    def test_simular_da_lo_mismo_que_antes_salvo_los_modelos_que_no_son_el_de_referencia(self):
        antes = self.sin_factor()
        for manifiesto in ("cola-24.toml", "cola-23.toml", "cola-22.toml", "cola-19.toml"):
            with self.subTest(manifiesto=manifiesto):
                # «antes» = sin la tabla de factores; lo único que agrega el encargo 24 a esas líneas es «sin factor».
                limpio = lambda l: re.sub(r"\s*\[sin factor\]$", "", re.sub(r", sin factor\]$", "]", l))
                a = [limpio(l) for l in self.simular(antes, ENCARGOS_DIR / manifiesto)]
                b = [limpio(l) for l in self.simular(self.cr, ENCARGOS_DIR / manifiesto)]
                self.assertEqual(len(a), len(b))
                distintas = [(x, y) for x, y in zip(a, b) if x != y]
                # Cambian solo los % de cuota de los modelos con factor (Claude): ni minutos, ni cuentas, ni topes, ni Codex.
                sin_pct = lambda l: re.sub(r"\s*\[(débil[^\]]*|sin factor)\]$", "", re.sub(r"\+([\d.]+) % 5 h \(p75 [\d.]+ %;", "+? % 5 h (p75 ? %;", re.sub(r"\+[\d.]+ % sem", "+? % sem", l)))
                for x, y in distintas:
                    self.assertIn("claude-", x)
                    self.assertEqual(sin_pct(x), sin_pct(y))
                self.assertEqual([l for l in a if "claude-" not in l], [l for l in b if "claude-" not in l])
                self.assertTrue([y for _, y in distintas if re.search(r"claude-(sonnet|haiku)", y)] or manifiesto == "cola-19.toml", manifiesto)
        # Una línea de Sonnet, con el factor a la vista.
        lineas = self.simular(self.cr, ENCARGOS_DIR / "cola-24.toml")
        sonnet = [l for l in lineas if "claude-sonnet-5-5" in l and l.strip().startswith("autor")]
        self.assertTrue(sonnet and all("factor 0,61" in l for l in sonnet), sonnet)

    def test_el_panel_publica_el_pronostico_de_cada_modelo_con_su_factor(self):
        self.cr._AP_MOD = previas._cargar(f"aplicar_{id(self)}", PI / "aplicar-propuesta.py")
        self.cr._AP_MOD.CODEX_MODELOS = str(FIXTURES / "encargos" / "models_cache.json")
        with contextlib.redirect_stdout(io.StringIO()):
            panel = self.cr.panel()
        self.assertEqual(panel["modelos"]["factor_modelo"], {"claude-opus-5-5": 1.0, "claude-sonnet-5-5": 0.61, "claude-haiku-4-5": 0.25})
        p = panel["pronosticos"]
        self.assertEqual((p["claude-sonnet-5-5"]["etiqueta"], p["claude-sonnet-5-5"]["pct_5h"]), ("débil, factor 0,61", 15.25))
        self.assertEqual((p["claude-haiku-4-5"]["etiqueta"], p["claude-haiku-4-5"]["pct_5h"]), ("débil, factor 0,25", 6.25))
        self.assertEqual(p["gpt-5.6-luna"]["etiqueta"], "sin factor")
        self.assertIsNone(p["gpt-5.6-luna"]["por_factor"])
        for cuenta in (p["claude-sonnet-5-5"]["cuenta"], p["gpt-5.6-luna"]["cuenta"]):
            self.assertIn(cuenta, panel["cuentas"])


def statistics_mediana_de_cami_rev_normalizada(ruta):
    """La normalización a mano: cada delta de 5 h de las filas frescas de claude_cami/rev, ÷ el factor de su modelo."""
    import statistics
    factor = {"claude-opus-5-5": 1.0, "claude-sonnet-5-5": 0.61, "claude-haiku-4-5": 0.25}
    filas = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()]
    filas = [h for h in filas if h["cuenta"] == "claude_cami" and h["rol"] == "rev" and not h.get("sin_cuota")]
    deltas = [(h["pct_5h"][1] - h["pct_5h"][0]) / factor.get(h["modelo"] or "", 1.0) for h in filas
              if h.get("medicion") == "fresco" and None not in h["pct_5h"] and h["pct_5h"][1] >= h["pct_5h"][0]]
    return statistics.median(deltas)


class ReglaDeLasColasTests(ColaRealBase):
    """`cola-run.py --panel` publica la regla «alcanza / no alcanza»; la página sólo la dibuja."""

    def preparar(self, estado="corriendo"):
        self.arrancar("partiendo", "23d", "rev3", "Codex", "gpt-5.6-terra medium")
        self.cr.vivo(estado=estado)
        self.cr._AP_MOD = previas._cargar(f"aplicar_{id(self)}", PI / "aplicar-propuesta.py")
        self.cr._AP_MOD.CODEX_MODELOS = str(FIXTURES / "encargos" / "models_cache.json")
        self.cr.uso = lambda cid: dict({"claude_cami": {"5h": 74.0, "sem": 40.0}, "codex": {"5h": 20.0, "sem": 30.0},
                                        "claude_diego": {"5h": 0.0, "sem": 10.0}}[cid],      # 46a: el panel trae la renovación de las tres
                                       renueva_5h=None, renueva_sem=None, momento=None, fuente="uso.json")

    def test_una_linea_por_cuenta_con_el_calculo_y_si_alcanza(self):
        self.reloj = datetime.now(CHILE)          # la cola «escribió ahora» para el reloj real de la prueba
        self.preparar()
        reglas = self.cr.reglas_cuota()
        self.assertEqual([r["cuenta"] for r in reglas], ["claude_cami", "codex"])
        cami = reglas[0]
        self.assertFalse(cami["alcanza"])
        # Encargo 46a: ya no es la próxima fase sino TODO lo que le falta a la cola, ponderado por la probabilidad
        # de llegar (rechazo 0,59): autor de 23e 25 + arreglos 4 × 0,59 + 4 × 0,3481 = 28,8 de 5 h; de la semana, 5.
        self.assertEqual(cami["texto"], "Claude (Cami) (cola23): 5 h ahora 74 % + 32,5 % = 106,5 % > tope 90 %: no alcanza · "
                                        "sem ahora 40 % + 5,9 % = 45,9 % ≤ tope 75 %: alcanza")
        self.assertEqual(cami["ventanas"], [{"ventana": "semanal", "actual": 40.0, "pronostico": 5.9, "tope": 75, "alcanza": True},
                                            {"ventana": "5h", "actual": 74.0, "pronostico": 32.5, "tope": 90, "alcanza": False}])
        self.assertEqual(cami["celdas"], {"cola23": {"pct_5h": 32.5, "pct_5h_min": 25.0, "pct_5h_max": 41.0, "pct_sem": 5.9, "pct_sem_min": 5.0,
                                                     "pct_sem_max": 7.0, "proxima_5h": 0.0, "debil": True}})
        # Codex: la rev3 que corre (8) + las tres revisiones de 23e (8 + 8 × 0,59 + 8 × 0,3481) = 23,5.
        self.assertTrue(reglas[1]["alcanza"])
        self.assertEqual([w["pronostico"] for w in reglas[1]["ventanas"]], [2.9, 23.5])
        # Una cola final o sin vivo no aporta cuentas; sin colas activas no hay líneas.
        self.cr.vivo(estado="detenida")
        self.assertEqual(self.cr.reglas_cuota(), [])

    def test_el_panel_la_trae_y_la_pagina_solo_la_dibuja(self):
        self.reloj = datetime.now(CHILE)
        self.preparar()
        with contextlib.redirect_stdout(io.StringIO()):
            panel = self.cr.panel()
        self.assertEqual([r["cuenta"] for r in panel["reglas"]], ["claude_cami", "codex"])
        js = leer(PAGINAS["encargos"] / "encargos.js")
        self.assertIn('cockpit.spawn(["python3", `${DIR}/cola-run.py`, "--panel"], { err: "ignore" })', js)
        # Encargo 46b: la lista «regla de cuotas» pasó a ser la matriz «Carga vs. capacidad» (CargaVsCapacidadTests).
        # De cada regla lee sólo campos que el panel publica; ya no dibuja `texto` ni `alcanza`.
        self.assertNotIn("function tarjetaRegla(", js)
        cuerpo = tramo(js, "function matrizCarga(reglas, fuera) {") + tramo(js, "function celdaHolgura(r, extra, renueva) {") + tramo(js, "function holguras(regla, extra) {")
        leidos = set(re.findall(r"\b(?:r|regla)\.(\w+)", cuerpo))
        self.assertEqual(leidos, {"cuenta", "celdas", "nombre", "fuente", "debil", "ventanas", "proxima_5h"})
        self.assertLessEqual(leidos, set(panel["reglas"][0]))
        self.assertNotIn(".regla-no", leer(PAGINAS["encargos"] / "encargos.css"))


# ---- Encargo 48, revisión 1: un `esfuerzo_<rol>` declarado no llega a un modelo que no lo acepta. ----
class EsfuerzoQueElModeloNoAceptaTests(ColaRealBase):
    """La cola corre de verdad (principal(), con sys.argv) sobre el manifiesto real del experimento
    `esfuerzo-v1`, copiado al temporal y con los cambios que hace la skill al escribir una cola. Lo
    único falso de más es el motor: `claude` y `codex` no se invocan, se anota el comando."""

    EJEMPLO = RepartoYModelosTests.EJEMPLO_SIMULACION
    BASE_CLAUDE = ["claude", "-p", "--output-format", "json", "--permission-mode", "acceptEdits", "--allowedTools"]

    def setUp(self):
        super().setUp()
        cr = self.cr
        cr._AP_MOD = previas._cargar(f"aplicar_{id(self)}", PI / "aplicar-propuesta.py")
        cr._AP_MOD.CODEX_MODELOS = str(FIXTURES / "encargos" / "models_cache.json")
        self.pct_5h = lambda reloj: 10.0
        self.comandos = []
        anterior = subprocess.run          # el doble de ColaRealBase: git y lo demás siguen siendo reales

        def run(cmd, *a, **k):
            if cmd and cmd[0] in ("claude", "codex"):
                self.comandos.append(list(cmd))
                if cmd[0] == "codex":
                    (self.tmp / "21r-RESULTADO.md").write_text("# Revisión\n\nVEREDICTO: DESPLEGABLE\n", encoding="utf-8")
                    return subprocess.CompletedProcess(cmd, 0, "model: gpt-5.6-terra\n" + "x" * 500, "")
                return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": "listo " * 100, "usage": {}}), "")
            return anterior(cmd, *a, **k)
        parche = mock.patch("subprocess.run", run)
        parche.start()
        self.addCleanup(parche.stop)

    def manifiesto_real(self, naturaleza="pagina", esfuerzo='esfuerzo_autor = "low"\n', extra=""):
        """El ejemplo real con lo que cambia al pasar a cola de verdad: sin `solo_simular`, sin suites
        (correrían las del vault) y con la naturaleza y el esfuerzo del caso."""
        texto = leer(self.EJEMPLO)
        for viejo, nuevo in (("solo_simular = true\n", ""), ('naturaleza = "pagina"\n', f'naturaleza = "{naturaleza}"\n'),
                             ('esfuerzo_autor = "low"\n', esfuerzo + extra)):
            self.assertEqual(texto.count(viejo), 1, viejo)
            texto = texto.replace(viejo, nuevo)
        texto = re.sub(r"^pruebas = .*$", "pruebas = []", texto, count=1, flags=re.M)
        self.assertIn("pruebas = []\n", texto)
        (self.tmp / "21-ventana-encargos.md").write_text("# Encargo 21\n", encoding="utf-8")
        ruta = self.tmp / "cola-prueba.toml"
        ruta.write_text(texto, encoding="utf-8")
        return ruta

    def lanzar(self, ruta, *args):
        salida, error = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["cola-run.py", str(ruta), *args]), contextlib.redirect_stdout(salida), \
                contextlib.redirect_stderr(error):
            try:
                rc = self.cr.principal()
            except SystemExit as e:
                rc = e.code
        return rc, salida.getvalue(), error.getvalue()

    def historial(self):
        return self.lineas(self.cr.HISTORIAL)

    def test_el_experimento_en_menor_se_rechaza_antes_de_partir_y_no_llega_al_cli(self):
        """48r1-1: `naturaleza = "menor"` resuelve el autor a Claude Haiku 4.5, que no acepta
        `--effort`. Con `esfuerzo_autor = "medium"` (el NN par de la skill) el comando salía con
        `--model claude-haiku-4-5 --effort medium` y lo rechazaba el CLI con la cola ya andando."""
        cfg = tomllib.loads(self.cr.MODELOS.read_text(encoding="utf-8"))
        liviano = cfg["niveles"]["claude"][cfg["naturaleza"]["menor"]["autor"]]
        self.assertEqual(liviano, {"modelo": "claude-haiku-4-5", "esfuerzo": ""})        # la forma real de hoy
        antes = self.historial()
        for esfuerzo in ("medium", "low"):                    # NN par e impar del experimento
            with self.subTest(esfuerzo=esfuerzo):
                ruta = self.manifiesto_real("menor", f'esfuerzo_autor = "{esfuerzo}"\n')
                motivo = (f'etapa 21: `esfuerzo_autor = "{esfuerzo}"` no sirve con claude-haiku-4-5 [liviano], que no '
                          "acepta esfuerzo; quita `esfuerzo_autor` o fija un `modelo_autor` que lo acepte")
                rc, salida, error = self.lanzar(ruta, "--simular")
                self.assertEqual((rc, salida, error), (2, "", f"⛔ {motivo}\n"))
                self.assertEqual(self.lineas(), [])                               # simular no avisa
                self.cr.SIMULANDO = False
                rc, _, _ = self.lanzar(ruta)
                self.assertEqual(rc, motivo)
                self.assertEqual(self.comandos, [])                               # ni claude ni codex
                self.assertFalse((self.tmp / "ESTADO.md").exists())
                self.assertFalse((self.tmp / "vivo").exists())
                self.assertEqual(self.historial(), antes)
                self.assertEqual([x["texto"] for x in self.lineas()], [f"⛔ Cola cola-prueba-encargar no partió: {motivo}"])   # un solo aviso, por el camino de siempre
                self.ra.REGISTRO.unlink()
        # modelo_de sigue siendo una función pura y dice lo que la etapa pide: el que frena es el validador.
        etapa = tomllib.loads(ruta.read_text(encoding="utf-8"))["etapa"][0]
        self.assertEqual(self.cr.modelo_de(etapa, "autor"), {"modelo": "claude-haiku-4-5", "esfuerzo": "low", "nivel": "liviano"})

    def test_el_experimento_en_pagina_llega_al_cli_con_el_modelo_de_la_naturaleza_y_su_esfuerzo(self):
        """El caso que sí se permite, de punta a punta: el comando de `claude` y la fila del historial."""
        for esfuerzo in ("low", "medium"):
            with self.subTest(esfuerzo=esfuerzo):
                self.comandos.clear()
                antes = len(self.historial())
                rc, salida, error = self.lanzar(self.manifiesto_real("pagina", f'esfuerzo_autor = "{esfuerzo}"\n'))
                self.assertEqual((rc, error), (0, ""), salida)
                autor, rev = self.comandos
                self.assertEqual(autor, self.BASE_CLAUDE + [self.cr.HERRAMIENTAS, "--model", "claude-opus-5-5", "--effort", esfuerzo])
                self.assertEqual(rev[-5:], ["-m", "gpt-5.6-terra", "-c", 'model_reasoning_effort="medium"', "-"])
                fila_autor, fila_rev = self.historial()[antes:]
                self.assertEqual([fila_autor[k] for k in ("encargo", "fase", "modelo", "esfuerzo", "nivel", "naturaleza")],
                                 ["21", "autor", "claude-opus-5-5", esfuerzo, "normal", "pagina"])
                self.assertEqual([fila_rev[k] for k in ("fase", "modelo", "esfuerzo", "nivel")], ["rev1", "gpt-5.6-terra", "medium", "normal"])

    def test_menor_sin_esfuerzo_declarado_corre_como_antes_sin_effort(self):
        rc, salida, error = self.lanzar(self.manifiesto_real("menor", ""))
        self.assertEqual((rc, error), (0, ""), salida)
        self.assertEqual(self.comandos[0], self.BASE_CLAUDE + [self.cr.HERRAMIENTAS, "--model", "claude-haiku-4-5"])
        self.assertNotIn("--effort", self.comandos[0])
        self.assertEqual([self.historial()[-2][k] for k in ("modelo", "esfuerzo", "nivel")], ["claude-haiku-4-5", "", "liviano"])

    def test_un_nivel_cambiado_a_mitad_de_cola_pausa_la_fase_antes_de_gastar(self):
        """Al lanzar, `pagina` + `low` calza (Claude Opus 5.5). Una propuesta pasa `normal` a Haiku con
        la cola andando: la fase siguiente relee el archivo y no puede pasarle `--effort low`."""
        cr = self.cr
        ruta = self.manifiesto_real()
        cr.MANIFIESTO = tomllib.loads(ruta.read_text(encoding="utf-8"))
        etapa = cr.MANIFIESTO["etapa"][0]
        cr.validar_esfuerzos([etapa])                                   # al lanzar: nada que objetar
        texto = cr.MODELOS.read_text(encoding="utf-8")
        viejo = 'normal  = { modelo = "claude-opus-5-5",   esfuerzo = "medium" }'
        self.assertEqual(texto.count(viejo), 1)
        cr.MODELOS.write_text(texto.replace(viejo, 'normal  = { modelo = "claude-haiku-4-5",  esfuerzo = "" }'), encoding="utf-8")
        cr.chequear_cuota = mock.Mock(side_effect=AssertionError("la fase siguió hasta la cuota"))   # lo primero que sigue: no se llega
        with self.assertRaises(cr.Pausa) as c:
            cr.etapa(etapa)
        self.assertEqual(c.exception.desde, "21:autor")
        self.assertIn('`esfuerzo_autor = "low"` no sirve con claude-haiku-4-5 [normal], que no acepta esfuerzo', c.exception.motivo)
        cr.chequear_cuota.assert_not_called()
        self.assertEqual(self.comandos, [])

    def test_se_rechaza_lo_incompatible_y_pasa_lo_que_el_catalogo_cargado_no_conoce(self):
        cr = self.cr
        base = {"id": "1", "autor": "claude_cami", "revisor": "codex"}
        malas = (
            (dict(base, naturaleza="menor", esfuerzo_fix="medium"), "`esfuerzo_fix = \"medium\"` no sirve con claude-haiku-4-5 [liviano]"),
            (dict(base, naturaleza="pagina", modelo_autor="claude-haiku-4-5", esfuerzo_autor="low"), "claude-haiku-4-5 [fijado], que no acepta esfuerzo"),
            (dict(base, naturaleza="bot", esfuerzo_autor="ultra"), "claude-opus-5-5 [normal], que acepta low, medium, high, xhigh, max"),
            (dict(base, naturaleza="menor", esfuerzo_rev="ultra"), "`esfuerzo_rev = \"ultra\"` no sirve con gpt-reserve [agil], que acepta low, medium, high, xhigh, max"),
        )
        for etapa, motivo in malas:
            with self.subTest(etapa=etapa):
                with self.assertRaises(ValueError) as c:
                    cr.validar_esfuerzos([etapa])
                self.assertIn(motivo, str(c.exception))
        buenas = (
            dict(base, autor="codex", revisor="claude_cami", naturaleza="menor", esfuerzo_rev="low"),   # rev de menor es `agil` (Sonnet): acepta
            dict(base, esfuerzo_autor="low"),                                          # C4: sin naturaleza, default del CLI
            dict(base, naturaleza="bot", modelo_autor="claude-de-manana", esfuerzo_autor="low"),   # fuera del catálogo: no se sabe
            dict(base, naturaleza="menor"),                                            # nada declarado: no se mira
            dict(base, naturaleza="pagina", esfuerzo_rev="ultra"),                     # gpt-5.6-terra sí acepta ultra
            dict(ETAPA_24, id="24"),
        )
        for etapa in buenas:
            with self.subTest(etapa=etapa):
                cr.validar_esfuerzos([etapa])
                for rol in ("autor", "rev", "fix"):
                    self.assertEqual(cr.esfuerzo_incompatible(etapa, rol), "")
        # Las colas que ya corrieron siguen pasando: ninguna declaró un esfuerzo que su modelo no acepte.
        colas = sorted(ENCARGOS_DIR.glob("cola-*.toml"))
        self.assertGreater(len(colas), 10)
        for ruta in colas:
            with self.subTest(cola=ruta.name):
                etapas = tomllib.loads(leer(ruta))["etapa"]
                cr.repartir(etapas)
                cr.validar_esfuerzos(etapas)

    # ---- 48r2-1: si la comprobación no se puede hacer, la cola no corre (antes devolvía permiso). ----

    def sin_rastro(self):
        self.assertEqual(self.comandos, [])                               # ni claude ni codex: nunca se arma `--effort`
        self.assertFalse((self.tmp / "ESTADO.md").exists())
        self.assertFalse((self.tmp / "vivo").exists())

    def test_sin_aplicar_propuesta_la_cola_con_esfuerzo_declarado_no_parte(self):
        """La reproducción de la revisión 2, de punta a punta: el manifiesto real con `menor` y
        `esfuerzo_autor = "medium"`, y `pi/aplicar-propuesta.py` no cargable. Antes: una advertencia,
        rc 0 y el plan `claude-haiku-4-5 medium`."""
        cr = self.cr
        antes = self.historial()
        origen = self.tmp / "pi" / "aplicar-propuesta.py"
        roto = "def catalogo_modelos(cfg=None):\n    return {\n"               # a medio escribir: no compila
        sin_funcion = "CLAUDE_MODELOS = ()\n"                                  # carga, pero no trae el catálogo
        casos = ((None, "FileNotFoundError"), (sin_funcion, "AttributeError"), (roto, "SyntaxError"))     # el roto al final: ver abajo
        for contenido, error_esperado in casos:
            for naturaleza, esfuerzo, modelo in (("menor", "medium", "claude-haiku-4-5 [liviano]"), ("pagina", "low", "claude-opus-5-5 [normal]")):
                with self.subTest(error=error_esperado, naturaleza=naturaleza):
                    cr._AP_MOD = None                         # lo carga _ap_mod() de verdad, desde D (el temporal)
                    shutil.rmtree(origen.parent, True)
                    if contenido is not None:
                        origen.parent.mkdir()
                        origen.write_text(contenido, encoding="utf-8")
                    ruta = self.manifiesto_real(naturaleza, f'esfuerzo_autor = "{esfuerzo}"\n')
                    inicio = (f'⛔ etapa 21: `esfuerzo_autor = "{esfuerzo}"` no se pudo verificar con {modelo}: no cargó el '
                              f"catálogo de modelos ({error_esperado}: ")
                    rc, salida, error = self.lanzar(ruta, "--simular")
                    self.assertEqual((rc, salida), (2, ""), error)              # ni una fila del plan, ni una advertencia suelta
                    self.assertTrue(error.startswith(inicio), error)
                    self.assertTrue(error.endswith("); la cola no corre sin esa comprobación\n"), error)
                    self.assertEqual(error.count("\n"), 1)
                    self.assertEqual(self.lineas(), [])                         # simular no avisa
                    self.sin_rastro()
                    cr.SIMULANDO = False
                    rc, _, _ = self.lanzar(ruta)
                    self.assertEqual("⛔ " + rc + "\n", error)                  # al lanzar, el mismo motivo
                    self.sin_rastro()
                    self.assertEqual(self.historial(), antes)
                    self.assertEqual([x["texto"] for x in self.lineas()], [f"⛔ Cola cola-prueba-encargar no partió: {rc}"])
                    self.ra.REGISTRO.unlink()
        # Una carga fallida no deja el módulo a medias: cuando el archivo vuelve, la respuesta es la de verdad.
        self.assertIsNone(cr._AP_MOD)
        shutil.copy(PI / "aplicar-propuesta.py", origen)
        rc, salida, error = self.lanzar(self.manifiesto_real("menor", 'esfuerzo_autor = "medium"\n'), "--simular")
        self.assertEqual((rc, salida, error), (2, "", '⛔ etapa 21: `esfuerzo_autor = "medium"` no sirve con claude-haiku-4-5 [liviano], que no '
                                                      "acepta esfuerzo; quita `esfuerzo_autor` o fija un `modelo_autor` que lo acepte\n"))
        rc, salida, error = self.lanzar(self.manifiesto_real("pagina", 'esfuerzo_autor = "low"\n'), "--simular")
        self.assertEqual((rc, error), (0, ""), salida)
        self.assertRegex(salida, r"(?m)^  autor Claude \(Cami\)\s+claude-opus-5-5 low\s+\[normal\]")
        self.sin_rastro()

    def test_sin_catalogo_solo_corre_lo_que_no_tiene_nada_que_verificar(self):
        """Lo que la falla del catálogo NO frena: una etapa sin `esfuerzo_*` (no se consulta) y C4,
        sin naturaleza, donde no hay modelo conocido cuya compatibilidad comprobar."""
        cr = self.cr
        cr._AP_MOD = None                                                  # D es el temporal: no hay pi/aplicar-propuesta.py
        rc, salida, error = self.lanzar(self.manifiesto_real("menor", ""))
        self.assertEqual((rc, error), (0, ""), salida)
        self.assertEqual(self.comandos[0], self.BASE_CLAUDE + [cr.HERRAMIENTAS, "--model", "claude-haiku-4-5"])
        self.comandos.clear()
        texto = leer(self.manifiesto_real())
        self.assertEqual(texto.count('naturaleza = "pagina"\n'), 1)
        (self.tmp / "cola-prueba.toml").write_text(texto.replace('naturaleza = "pagina"\n', ""), encoding="utf-8")
        rc, salida, error = self.lanzar(self.tmp / "cola-prueba.toml")
        self.assertEqual((rc, error), (0, ""), salida)
        self.assertEqual(self.comandos[0], self.BASE_CLAUDE + [cr.HERRAMIENTAS, "--effort", "low"])      # C4: default del CLI, sin --model
        self.assertIsNone(cr._AP_MOD)                                      # de verdad no hubo catálogo en todo el camino

    def test_el_catalogo_de_codex_ilegible_frena_el_esfuerzo_declarado_para_codex(self):
        """La otra forma de quedarse sin comprobación: aplicar-propuesta carga, pero `models_cache.json`
        no se lee y el catálogo trae `codex = None`. Claude no depende de ese archivo."""
        cr = self.cr
        base = {"id": "1", "autor": "claude_cami", "revisor": "codex"}
        for ilegible in ("no-existe.json", "roto.json", "sin-models.json"):
            with self.subTest(cache=ilegible):
                (self.tmp / "roto.json").write_text('{"models": [', encoding="utf-8")
                (self.tmp / "sin-models.json").write_text('{"fetched_at": "2026-10-11"}', encoding="utf-8")
                cr._AP_MOD.CODEX_MODELOS = str(self.tmp / ilegible)
                self.assertIsNone(cr._AP_MOD.catalogo_modelos(cr._cfg_modelos())["codex"])     # la forma real de la falla
                for etapa in (dict(base, naturaleza="pagina", esfuerzo_rev="medium"), dict(ETAPA_24, id="1")):
                    with self.assertRaises(ValueError) as c:
                        cr.validar_esfuerzos([etapa])
                    self.assertEqual(str(c.exception), 'etapa 1: `esfuerzo_rev = "medium"` no se pudo verificar con gpt-5.6-terra '
                                     f"[{'fijado' if etapa.get('modelo_rev') else 'normal'}]: el catálogo no trae los modelos de codex; "
                                     "la cola no corre sin esa comprobación")
                cr.validar_esfuerzos([dict(base, naturaleza="pagina", esfuerzo_autor="low")])          # Claude: se verifica y calza
                cr.validar_esfuerzos([dict(base, naturaleza="pagina")])                                # sin esfuerzo declarado: no se mira
                with self.assertRaises(ValueError) as c:
                    cr.validar_esfuerzos([dict(base, naturaleza="menor", esfuerzo_autor="medium")])
                self.assertIn("claude-haiku-4-5 [liviano], que no acepta esfuerzo", str(c.exception))

    def test_el_catalogo_que_deja_de_cargar_a_mitad_de_cola_pausa_la_fase_antes_de_gastar(self):
        cr = self.cr
        cr.MANIFIESTO = tomllib.loads(self.manifiesto_real().read_text(encoding="utf-8"))
        etapa = cr.MANIFIESTO["etapa"][0]
        cr.validar_esfuerzos([etapa])                                   # al lanzar había catálogo
        cr._AP_MOD.catalogo_modelos = mock.Mock(side_effect=OSError("se desmontó el volumen"))
        cr.chequear_cuota = mock.Mock(side_effect=AssertionError("la fase siguió hasta la cuota"))
        with self.assertRaises(cr.Pausa) as c:
            cr.etapa(etapa)
        self.assertEqual(c.exception.desde, "21:autor")
        self.assertEqual(c.exception.motivo, 'etapa 21: `esfuerzo_autor = "low"` no se pudo verificar con claude-opus-5-5 [normal]: no cargó '
                         "el catálogo de modelos (OSError: se desmontó el volumen); la cola no corre sin esa comprobación")
        cr.chequear_cuota.assert_not_called()
        self.assertEqual(self.comandos, [])

    def test_la_skill_ya_no_ofrece_el_experimento_para_menor(self):
        """La otra mitad del hallazgo: el paso 4c permitía `menor` o `pagina`. Mientras `menor` sea
        Haiku queda fuera, y la skill instalada es la misma que la fuente del proyecto."""
        fuente, instalada = ENCARGOS_DIR / "skill-encargar" / "SKILL.md", self.EJEMPLO.with_name("SKILL.md")
        self.assertEqual(leer(fuente), leer(instalada))
        paso = tramo_4c(leer(instalada))
        self.assertIn("Sólo para naturaleza `pagina`, rol autor.", paso)
        self.assertNotIn("`menor` o `pagina`", paso)
        self.assertIn("`menor` queda fuera", paso)
        # Lo que la skill permite es lo que la cola acepta, con el modelos.toml de hoy.
        permitidas = re.findall(r"Sólo para naturaleza ((?:`\w+`(?:, | o )?)+), rol autor", paso)
        self.assertEqual(len(permitidas), 1)
        for nat in re.findall(r"`(\w+)`", permitidas[0]):
            for esfuerzo in re.findall(r'`esfuerzo_autor = "(\w+)"`', paso):
                self.cr.validar_esfuerzos([{"id": "1", "autor": "claude_cami", "revisor": "codex", "naturaleza": nat, "esfuerzo_autor": esfuerzo}])
        self.assertEqual(sorted(set(re.findall(r'`esfuerzo_autor = "(\w+)"`', paso))), ["low", "medium"])


# ---- Encargo 48b: la cola no lee fuera de 11-Pi5; la skill instalada no entra al diff de la etapa. ----
class DiffDeEtapaSinLaSkillInstaladaTests(ColaRealBase):
    """La cola corre de verdad (principal()) sobre el manifiesto real del experimento, con git de verdad
    en un historial temporal y una copia de las dos carpetas reales de la skill: la fuente dentro del
    árbol y la instalada fuera, en `90-Referencia`, como en el vault."""

    FUENTE = ENCARGOS_DIR / "skill-encargar"
    EJEMPLO = RepartoYModelosTests.EJEMPLO_SIMULACION
    INSTALADA = EJEMPLO.parent
    VIEJO = "Sólo para naturaleza `pagina`, rol autor."
    NUEVO = "Sólo para naturaleza `pagina`, rol autor (editado por la fase)."

    def setUp(self):
        super().setUp()
        cr = self.cr
        self.vault = self.tmp / "vault"
        self.arbol = self.vault / "10-Proyectos" / "11-Pi5"
        self.fuente = self.arbol / "encargos" / "skill-encargar"
        self.instalada = self.vault / "90-Referencia" / "01-SkillsIA" / "encargar"
        shutil.copytree(self.FUENTE, self.fuente)
        shutil.copytree(self.INSTALADA, self.instalada)
        self.assertEqual(leer(self.instalada / "SKILL.md").count(self.VIEJO), 1)
        cr.VAULT, cr.D = self.vault, self.arbol
        cr._VERS_MOD = None
        entorno = mock.patch.dict(os.environ, {"VERSIONES_REPO": str(self.tmp / "git" / "11-Pi5.git"), "VERSIONES_ARBOL": str(self.arbol)})
        entorno.start()
        self.addCleanup(entorno.stop)
        cr._vers().abrir().init()
        self.pct_5h = lambda reloj: 10.0
        self.autor = lambda: None
        anterior = subprocess.run          # el doble de ColaRealBase: git sigue siendo real

        def run(cmd, *a, **k):
            if cmd and cmd[0] == "claude":
                self.autor()
                return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": "listo " * 100, "usage": {}}), "")
            if cmd and cmd[0] == "codex":
                self.diff_que_vio_el_revisor = leer(self.tmp / "cola-prueba-encargar-21-diff.txt")
                self.prompt_del_revisor = k.get("input") or ""
                (self.tmp / "21r-RESULTADO.md").write_text("# Revisión\n\nVEREDICTO: DESPLEGABLE\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "model: gpt-5.6-terra\n" + "x" * 500, "")
            return anterior(cmd, *a, **k)
        parche = mock.patch("subprocess.run", run)
        parche.start()
        self.addCleanup(parche.stop)

    def test_el_diff_de_la_etapa_no_trae_nada_de_90_referencia_aunque_la_instalada_difiera_de_la_copia(self):
        """48r3-1: el comparador mandaba al revisor lo que hubiera en esa carpeta. Ya no existe."""
        def autor():
            ruta = self.instalada / "SKILL.md"
            ruta.write_bytes(ruta.read_bytes().replace(self.VIEJO.encode(), self.NUEVO.encode()))
            (self.instalada / "nuevo.md").write_text("TOKEN=no-debe-salir\n", encoding="utf-8")
        self.autor = autor
        ruta = EsfuerzoQueElModeloNoAceptaTests.manifiesto_real(self)
        with mock.patch.object(sys, "argv", ["cola-run.py", str(ruta)]), contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual((self.cr.principal(), error.getvalue()), (0, ""))
        self.assertNotEqual(leer(self.instalada / "SKILL.md"), leer(self.fuente / "SKILL.md"))   # la instalada sí difiere
        diff = self.diff_que_vio_el_revisor
        self.assertIn("cola-prueba-encargar-21-diff.txt", self.prompt_del_revisor)       # es el archivo que recibe el revisor
        self.assertIn("(la etapa no cambió ningún archivo)", diff)
        for prohibido in ("90-Referencia", "01-SkillsIA", "Fuera del árbol", self.NUEVO, "no-debe-salir", "nuevo.md"):
            self.assertNotIn(prohibido, diff)


def tramo_4c(skill):
    """El paso 4c de SKILL.md, hasta el paso 5."""
    return skill[skill.index("4c. **Experimento `esfuerzo-v1`:**"):skill.index("\n5. ")]


# ---- Encargo 34: resumen por cola y etapa, y barra de uso por fase en 🧵 Encargos. ----
class ResumenYUsoTests(unittest.TestCase):
    """Espejo en Python de las funciones puras del encargo 34 de encargos.js (en la Pi no hay motor de JS).

    Los RE_ del espejo NO están copiados: se leen del propio encargos.js. Las filas son REALES, copiadas de
    encargos/historial.jsonl a fixtures/encargos/historial-uso-34.jsonl (encargos 19, 29 y 32b), y los manifiestos
    son copias de cola-34.toml (con `resumen`) y cola-31.toml (sin él). Nada de acá abre los libros vivos ni
    escribe en ningún archivo."""

    FILAS = [json.loads(x) for x in leer(FIXTURES_ENCARGOS / "historial-uso-34.jsonl").splitlines() if x.strip()]
    COLA34, COLA31 = leer(FIXTURES_ENCARGOS / "cola-34.toml"), leer(FIXTURES_ENCARGOS / "cola-31.toml")
    NOMBRES = {"codex": "Codex", "claude_cami": "Claude (Cami)", "claude_diego": "Claude (Diego)"}
    # Primera línea real de cada encargo (copiada de encargos/NN-*.md el 08-10-2026).
    TITULO34 = "# Encargo 34: resumen por encargo y etapa, y barra de uso por modelo en 🧵 Encargos (Claude (Diego), 07-10-2026)\n\n## Contexto\n"
    TITULO31 = "# Encargo 31 — 🧵 Encargos → Historial: ordenar, y lo más reciente primero — 07-10-2026\n\nTexto.\n"
    TITULO20 = "# Encargo 20: 🧵 Encargos, ventana de las colas en Cockpit (escribe {AUTOR}; revisa {REVISOR})\n"
    ESFUERZOS = ["low", "medium", "high", "xhigh"]

    @classmethod
    def setUpClass(cls):
        import tomllib
        cls.js = leer(PAGINAS["encargos"] / "encargos.js")
        cls.css = leer(PAGINAS["encargos"] / "encargos.css")
        cls.RE = {n: re.compile(fuente, re.I if "i" in banderas else 0)
                  for n, fuente, banderas in re.findall(r"^const (RE_\w+) = /((?:[^/\\\n]|\\.)+)/([gi]*);$", cls.js, re.M)}
        # La paleta sale de [niveles.*] de modelos.toml (copia fija), en el orden del archivo, como la entrega --panel.
        cls.MODELOS = tomllib.loads(leer(FIXTURES_ENCARGOS / "modelos.toml"))
        cls.PALETA = cls.modelos_paleta(cls.MODELOS)

    # --- espejo de seguro() ---
    @staticmethod
    def mixto(s):
        return bool(re.search(r"[A-Za-z_À-ÿ]", s)) and bool(re.search(r"[0-9]", s))

    @classmethod
    def tramos_malos(cls, t):
        rs = cls.RE["RE_TRAMO"].findall(t)
        n = sum(cls.mixto(r) for r in rs)
        return any(len(r) > 16 for r in rs) or n >= 3 or (len(rs) >= 3 and n >= 1)

    @classmethod
    def ruta_segura(cls, t):
        seguidos = 0
        for s in filter(None, cls.RE["RE_RUTA"].sub("", t, count=1).split("/")):
            seguidos = seguidos + 1 if cls.mixto(s) else 0
            if (seguidos >= 4 or cls.tramos_malos(s) or not cls.RE["RE_SEGMENTO"].search(s)
                    or (not re.search(r"[-_]", s) and len(s) >= 14 and cls.RE["RE_MAYUSCULA_Y_DIGITO"].search(s))):
                return False
        return True

    @classmethod
    def token_seguro(cls, t):
        c = cls.RE["RE_BORDE"].sub("", t)
        rs = cls.RE["RE_TRAMO"].findall(c)
        if not rs:
            return True
        if cls.RE["RE_PREFIJO"].search(c):
            return False
        if cls.RE["RE_RUTA"].search(c):
            return cls.ruta_segura(c)
        if cls.tramos_malos(c) or len("".join(rs)) > 16:
            return False
        if cls.RE["RE_NUMERO"].search(c):
            return True
        if "=" in c:
            n, valor = c.split("=", 1)
            n = re.sub(r"^-+", "", n)
            return bool(cls.RE["RE_SEGMENTO"].search(n)) and not cls.RE["RE_SENSIBLE"].search(n) and cls.token_seguro(valor)
        if c.startswith("-"):
            return not re.search(r"^-p.", c, re.I) and bool(cls.RE["RE_SEGMENTO"].search(re.sub(r"^-+", "", c)))
        return bool(cls.RE["RE_PALABRA"].search(c))

    @classmethod
    def seguro(cls, texto):
        previo, salida = "", []
        for p in re.split(r"(\s+)", str(texto)):
            if not p.strip():
                salida.append(p)
                continue
            a = cls.RE["RE_BORDE"].sub("", previo)
            marcado = (bool(cls.RE["RE_ESQUEMA"].search(a)) or bool(cls.RE["RE_CLAVE"].search(previo) and cls.RE["RE_SENSIBLE"].search(previo))
                       or (a.startswith("--") and bool(cls.RE["RE_SENSIBLE"].search(a.split("=")[0]))))
            previo = p
            salida.append("«oculto»" if marcado or not cls.token_seguro(p) else p)
        return "".join(salida)

    @classmethod
    def una_linea(cls, x):
        return cls.seguro(re.sub(r"\s+", " ", str(x)).strip())

    # --- espejo de resumenes(), tituloLimpio(), resumenCola(), etapaDe() y resumenEtapa() ---
    @staticmethod
    def cadena(b, k):
        m = re.search(rf'^{k}\s*=\s*"((?:[^"\\]|\\.)*)"', b, re.M)
        return re.sub(r'\\(["\\])', r"\1", m[1]) if m and m[1] else None

    @classmethod
    def resumenes(cls, t):
        raiz = re.split(r"^\s*\[", t or "", maxsplit=1, flags=re.M)[0]
        cola = cls.cadena(raiz, "nombre")
        if not cola:
            return None
        etapas = [{"id": cls.cadena(b, "id"), "resumen": cls.cadena(b, "resumen"), "encargo": cls.cadena(b, "encargo")} for b in t.split("[[etapa]]")[1:]]
        return {"cola": cola, "resumen": cls.cadena(raiz, "resumen"), "motivo": cls.cadena(raiz, "motivo"), "etapas": [e for e in etapas if e["id"]]}

    @classmethod
    def titulo_limpio(cls, md):
        m = re.search(r"^# +(.+)$", md or "", re.M)
        if not m:
            return None
        t = m[1]
        for n in ("RE_TITULO_PREFIJO", "RE_TITULO_AUTOR", "RE_TITULO_FECHA"):
            t = cls.RE[n].sub("", t, count=1)
        return t.strip() or None

    @classmethod
    def resumen_cola(cls, rs, nombre):
        c = next((x for x in rs if x["cola"] == nombre), None)
        t = c and (c["resumen"] or c["motivo"])
        return cls.una_linea(t) if t else "sin resumen"

    @staticmethod
    def etapa_de(rs, etapa):
        xs = [{"cola": c["cola"], **e} for c in rs for e in c["etapas"] if e["id"] == str(etapa)]
        return sorted(xs, key=lambda x: natural(x["cola"]))[-1] if xs else None

    @classmethod
    def resumen_etapa(cls, e, titulos):
        t = e and (e["resumen"] or titulos.get(e["encargo"]))
        return cls.una_linea(t) if t else "sin resumen"

    # --- espejo de la barra de uso ---
    @staticmethod
    def modelos_paleta(modelos):
        return list(dict.fromkeys(x["modelo"] for t in (modelos or {}).get("niveles", {}).values() for x in t.values() if x.get("modelo")))

    @staticmethod
    def modelo_fila(x):
        return x.get("modelo_real") or x.get("modelo") or None

    @classmethod
    def tono(cls, modelo):
        i = cls.PALETA.index(modelo) if modelo in cls.PALETA else -1
        return f"uso-m{i + 1}" if 0 <= i < 8 else "uso-gris"

    @classmethod
    def clase_esfuerzo(cls, e):
        return f"uso-e-{e}" if e in cls.ESFUERZOS else "uso-e-vacio"

    @staticmethod
    def delta_uso(x):
        p = x.get("pct_5h")
        ok = isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p)
        return math.floor((p[1] - p[0]) * 10 + 0.5) / 10 if ok else None       # Math.round

    @classmethod
    def medida_tramo(cls, x, medida):
        v = cls.delta_uso(x) if medida == "delta" else x.get("min")
        return v if isinstance(v, (int, float)) and math.isfinite(v) and v > 0 else None

    @staticmethod
    def num_js(v):
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)      # 8.0 se escribe «8» en JS

    @classmethod
    def tokens_txt(cls, t):
        return ", ".join(f"{k} {cls.num_js(v)}" for k, v in t.items()) if isinstance(t, dict) and t else "sin datos"

    @classmethod
    def titulo_tramo(cls, x):
        dl, e = cls.delta_uso(x), x.get("esfuerzo")
        return " · ".join([x.get("fase") or "sin datos", cls.NOMBRES.get(x.get("cuenta"), "sin datos"), cls.modelo_fila(x) or "modelo desconocido",
                           f"esfuerzo {e}" if e else "sin esfuerzo" if e == "" else "esfuerzo sin datos",
                           f'{cls.num_js(x["min"])} min' if isinstance(x.get("min"), (int, float)) else "minutos sin datos",
                           f"Δ 5 h +{cls.num_js(dl)} %" if dl is not None and dl > 0 else "Δ 5 h sin cambio medido", f'tokens: {cls.tokens_txt(x.get("tokens"))}'])

    @classmethod
    def barra(cls, fs, medida):
        orden = sorted(fs, key=lambda x: datetime.fromisoformat(x["inicio"]).timestamp() if x.get("inicio") else 0)
        return [{"fase": x["fase"], "clases": [cls.tono(cls.modelo_fila(x)), cls.clase_esfuerzo(x.get("esfuerzo"))] + ([] if cls.medida_tramo(x, medida) is not None else ["uso-sin-medida"]),
                 "peso": cls.medida_tramo(x, medida), "titulo": cls.titulo_tramo(x)} for x in orden]

    def de(self, encargo):
        return [x for x in self.FILAS if x["encargo"] == encargo]

    # ---------------- resumen ----------------
    def test_el_manifiesto_con_resumen_lo_muestra_en_la_raiz_y_en_la_etapa(self):
        r = self.resumenes(self.COLA34)
        self.assertEqual(r["cola"], "cola34")
        self.assertEqual(r["resumen"], "Muestra en 🧵 qué hace cada encargo y etapa, y una barra de uso coloreada por modelo y esfuerzo.")
        self.assertEqual(r["etapas"], [{"id": "34", "resumen": "Resumen por encargo y etapa, y barra de uso por modelo y esfuerzo.", "encargo": "34-resumen-y-barra-de-uso.md"}])
        self.assertLessEqual(len(r["resumen"]), 120)
        self.assertLessEqual(len(r["etapas"][0]["resumen"]), 80)
        self.assertEqual(self.resumen_cola([r], "cola34"), r["resumen"])                     # el resumen gana al motivo
        self.assertEqual(self.resumen_etapa(self.etapa_de([r], "34"), {}), r["etapas"][0]["resumen"])
        # El `resumen` de la etapa no se toma por el de la cola: la raíz es sólo lo que va antes de la primera tabla.
        sin_raiz = self.COLA34.replace('resumen = "Muestra en', '# resumen = "Muestra en', 1)
        self.assertIsNone(self.resumenes(sin_raiz)["resumen"])
        self.assertEqual(self.resumenes(sin_raiz)["etapas"][0]["resumen"], r["etapas"][0]["resumen"])
        self.assertIn('const raiz = (t || "").split(/^\\s*\\[/m)[0], cola = cadena(raiz, "nombre");', self.js)
        self.assertIn('etapas: t.split("[[etapa]]").slice(1).map(b => ({ id: cadena(b, "id"), resumen: cadena(b, "resumen"), encargo: cadena(b, "encargo") })).filter(x => x.id)', self.js)

    def test_el_manifiesto_real_sin_resumen_cae_al_motivo_y_al_titulo_del_md(self):
        r = self.resumenes(self.COLA31)
        self.assertIsNone(r["resumen"])
        self.assertIsNone(r["etapas"][0]["resumen"])
        self.assertEqual(self.resumen_cola([r], "cola31"), "Historial de 🧵 Encargos: columna Fecha, lo más reciente primero y «Ordenar por» (encargo 31).")
        titulos = {"31-historial-ordenar.md": self.titulo_limpio(self.TITULO31)}
        self.assertEqual(self.resumen_etapa(self.etapa_de([r], "31"), titulos), "🧵 Encargos → Historial: ordenar, y lo más reciente primero")
        # Sin el .md (no se pudo leer) y sin cola que traiga la etapa: «sin resumen», nunca un texto inventado.
        self.assertEqual(self.resumen_etapa(self.etapa_de([r], "31"), {}), "sin resumen")
        self.assertIsNone(self.etapa_de([r], "99"))
        self.assertEqual(self.resumen_etapa(None, titulos), "sin resumen")
        self.assertEqual(self.resumen_cola([r], "cola99"), "sin resumen")
        sin_motivo = re.sub(r"^motivo = .*\n", "", self.COLA31, flags=re.M)
        self.assertEqual(self.resumen_cola([self.resumenes(sin_motivo)], "cola31"), "sin resumen")
        self.assertIn('t = c && (c.resumen || c.motivo); return t ? unaLinea(t) : "sin resumen";', self.js)
        self.assertIn('const t = e && (e.resumen || titulos.get(e.encargo)); return t ? unaLinea(t) : "sin resumen";', self.js)
        # Si dos colas traen la misma etapa, vale la más nueva (orden natural del nombre de la cola).
        otra = self.resumenes(self.COLA31.replace('"cola31"', '"cola9"', 1).replace('encargo = "31-historial-ordenar.md"', 'resumen = "vieja"', 1))
        self.assertEqual(self.etapa_de([r, otra], "31")["cola"], "cola31")
        self.assertEqual(self.etapa_de([otra, r], "31")["cola"], "cola31")
        self.assertIn('a.cola.localeCompare(b.cola, "es", { numeric: true })).at(-1) || null', self.js)

    def test_el_titulo_del_md_sale_sin_prefijo_ni_autor_ni_fecha(self):
        self.assertEqual(self.titulo_limpio(self.TITULO34), "resumen por encargo y etapa, y barra de uso por modelo en 🧵 Encargos")
        self.assertEqual(self.titulo_limpio(self.TITULO31), "🧵 Encargos → Historial: ordenar, y lo más reciente primero")
        self.assertEqual(self.titulo_limpio("# Encargo 22b: ⏰ Programados con lista blanca en vez de tapar secretos (Claude (Diego), 04-10-2026)"),
                         "⏰ Programados con lista blanca en vez de tapar secretos")
        self.assertEqual(self.titulo_limpio("# Encargo 23e — Cerrar los hallazgos de la revisión 3 de 23c (04-10-2026)"), "Cerrar los hallazgos de la revisión 3 de 23c")
        # Un paréntesis que no es de autor y fecha se queda: sólo se quita lo que el encargo pide.
        self.assertEqual(self.titulo_limpio(self.TITULO20), "🧵 Encargos, ventana de las colas en Cockpit (escribe {AUTOR}; revisa {REVISOR})")
        self.assertEqual(self.titulo_limpio("# Título (con paréntesis) al medio (Claude (Cami), 01-01-2026)"), "Título (con paréntesis) al medio")
        for nada in (None, "", "sin encabezado\n## Sólo un h2\n", "# Encargo 40:  (Claude (Diego), 07-10-2026)"):
            self.assertIsNone(self.titulo_limpio(nada), nada)
        self.assertIn('const m = (md || "").match(/^# +(.+)$/m); return m ? m[1].replace(RE_TITULO_PREFIJO, "").replace(RE_TITULO_AUTOR, "").replace(RE_TITULO_FECHA, "").trim() || null : null;', self.js)
        # El .md se lee sólo si la etapa no trae `resumen`, una vez, y con un nombre que no puede salir de DIR.
        self.assertIn('filter(e => !e.resumen && /^[A-Za-z0-9_.-]+\\.md$/.test(e.encargo || ""))', self.js)
        self.assertIn(".filter(f => !titulos.has(f));", self.js)
        self.assertIn("const t = await archivo(`${DIR}/${f}`); if (t != null) titulos.set(f, tituloLimpio(t));", self.js)

    def test_el_resumen_se_dibuja_en_ahora_y_en_la_linea_de_tiempo_como_texto_de_una_linea(self):
        linea = tramo(self.js, "function lineaResumen(texto, antes) {")
        self.assertIn('el("p", { class: `resumen${texto === "sin resumen" ? " tenue" : ""}`, title: texto }', linea)     # el texto completo en title
        self.assertIn("el(\"h2\", {}, mencionCola(m.cola), ` · ${titulo}`), lineaResumen(resumenCola(m.cola)),", self.js)  # tarjeta de la cola en Ahora (95)
        self.assertIn('el("h2", {}, "Cola viva: ", mencionCola(v.cola)), lineaResumen(resumenCola(v.cola)),', self.js)       # la cola deducida de la bitácora (95)
        self.assertIn('el("h2", {}, `Encargo ${id}`), lineaResumen(e ? resumenCola(e.cola) : "sin resumen"), lineaResumen(resumenEtapa(e), `Etapa ${id} · `),', self.js)
        regla = {s: d for m, s, d in reglas_css(self.css) if not m}[".resumen"]
        self.assertEqual((regla["white-space"], regla["overflow"], regla["text-overflow"]), ("nowrap", "hidden", "ellipsis"))
        self.assertEqual(self.una_linea("  dos\n líneas \t y   espacios "), "dos líneas y espacios")
        self.assertIn('const unaLinea = x => seguro(String(x).replace(/\\s+/g, " ").trim());', self.js)
        # Todo lo que sale de un .toml o de un .md pasa por unaLinea() → seguro(); nada llega al DOM por otro camino.
        for campo in ("c.resumen ||", "c.motivo", "e.resumen ||", "titulos.get("):
            usos = [l for l in self.js.splitlines() if campo in l]
            self.assertTrue(usos and all("unaLinea(t)" in l for l in usos), campo)

    # ---------------- lista blanca ----------------
    def test_los_regex_del_espejo_se_leen_del_js(self):
        self.assertEqual(set(self.RE), {"RE_TRAMO", "RE_PALABRA", "RE_SEGMENTO", "RE_NUMERO", "RE_RUTA", "RE_PREFIJO", "RE_SENSIBLE", "RE_BORDE",
                                        "RE_ESQUEMA", "RE_CLAVE", "RE_MAYUSCULA_Y_DIGITO", "RE_TITULO_PREFIJO", "RE_TITULO_AUTOR", "RE_TITULO_FECHA"})
        for linea in ('const mixto = s => /[A-Za-z_À-ÿ]/.test(s) && /[0-9]/.test(s);',
                      "return rs.some(r => r.length > 16) || n >= 3 || (rs.length >= 3 && n >= 1);",
                      "if (seguidos >= 4 || tramosMalos(s) || !RE_SEGMENTO.test(s) || (!/[-_]/.test(s) && s.length >= 14 && RE_MAYUSCULA_Y_DIGITO.test(s))) return false;",
                      'const c = t.replace(RE_BORDE, ""), rs = c.match(RE_TRAMO) || [];',
                      "if (!rs.length) return true;", "if (RE_PREFIJO.test(c)) return false;", "if (RE_RUTA.test(c)) return rutaSegura(c);",
                      'if (tramosMalos(c) || rs.join("").length > 16) return false;', "if (RE_NUMERO.test(c)) return true;",
                      "return RE_SEGMENTO.test(n) && !RE_SENSIBLE.test(n) && tokenSeguro(c.slice(i + 1));",
                      'if (c.startsWith("-")) return !/^-p./i.test(c) && RE_SEGMENTO.test(c.replace(/^-+/, ""));', "return RE_PALABRA.test(c);",
                      'const marcado = RE_ESQUEMA.test(a) || (RE_CLAVE.test(previo) && RE_SENSIBLE.test(previo)) || (a.startsWith("--") && RE_SENSIBLE.test(a.split("=")[0]));',
                      "return marcado || !tokenSeguro(p) ? OCULTO : p;"):
            self.assertIn(linea, self.js)
        # Un regex con la bandera g guarda estado en .test(): los globales sólo se usan con match() y replace().
        globales = re.findall(r"^const (RE_\w+) = /(?:[^/\\\n]|\\.)+/[i]*g[i]*;$", self.js, re.M)
        self.assertEqual(sorted(globales), ["RE_BORDE", "RE_TRAMO"])
        for n in globales:
            self.assertNotIn(f"{n}.test(", self.js)

    def test_ningun_secreto_de_la_22b_y_la_22c_sale_en_un_resumen(self):
        secretos = ["a" * 32, "A1b2C3d4" * 8, "0123456789abcdef" * 2, "0123456789abcdef" * 2 + "01234567", "0123456789abcdef" * 4,
                    "550e8400-e29b-41d4-a716-446655440000", "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz", "ghp_AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGh",
                    "xoxb-" + "123456789012-123456789012-abcdefghijklmnop", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTYifQ.sig",
                    "QWxhZGRpbjpvcGVuIHNlc2FtZQ==/abcde12345", "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXotXw", "AKIAIOSFODNN7EXAMPLE",
                    "123456789:AAEhBP0av28zQ7Gz_abcdefghijklmnopqrs", "R4nd0m20CharacterZZ", "sk-ant-xyz", "/srv/a1b2/c3d4/e5f6/g7h8", "/opt/AbCdEfGh1jKlMn/x"]
        for secreto in secretos:
            for molde in ("Arregla {} en la página.", "resumen «{}»", "usa `{}`.", "({})", "clave={}", "--opcion={}", "ruta:{}", '"{}",', "{}"):
                with self.subTest(secreto=secreto[:12], molde=molde):
                    self.assertNotIn(secreto, self.una_linea(molde.format(secreto)))
        # Valores cortos tras una clave sensible (22c): se oculta el valor aunque parezca una palabra.
        for texto, valor in (("password: corta", "corta"), ('"token": "abc"', "abc"), ("--api-key valor1", "valor1"), ("Authorization: Bearer abc", "abc"),
                             ("TOKEN=corta", "corta"), ("--password=corta", "corta"), ("Bearer abcdefghijklmnop", "abcdefghijklmnop"), ("mysql -pclave", "clave"),
                             ("mysql -p clave", "clave"), ("api_key= valor", "valor")):
            with self.subTest(texto):
                self.assertNotIn(valor, self.una_linea(texto).replace("password", "").replace("api-key", ""))
        # Un prefijo de credencial conocido se oculta aunque el resto sea corto y parezca una palabra.
        for corto in ("AKIAabcd", "eyJhbGci", "ghp_corto", "github_pat_ab", "sk-corto", "xoxb-corto"):
            self.assertEqual(self.una_linea(f"usa {corto} acá"), "usa «oculto» acá", corto)
        # La prueba mide: lo legible sí pasa, con sus signos.
        self.assertEqual(self.una_linea("Lee /opt/nodo/datos y ~/.config (rev1/fix1) el 07-10-2026 a las ~23:00: 5,5 % — ok."),
                         "Lee /opt/nodo/datos y ~/.config (rev1/fix1) el 07-10-2026 a las ~23:00: 5,5 % — ok.")

    def test_los_textos_reales_pasan_enteros_y_el_criterio_no_es_mas_blando_que_programados(self):
        reales = [self.resumenes(self.COLA34)["resumen"], self.resumenes(self.COLA34)["motivo"], self.resumenes(self.COLA34)["etapas"][0]["resumen"],
                  self.resumenes(self.COLA31)["motivo"], self.titulo_limpio(self.TITULO34), self.titulo_limpio(self.TITULO31), self.titulo_limpio(self.TITULO20)]
        for texto in reales:
            with self.subTest(texto[:30]):
                self.assertEqual(self.una_linea(texto), texto)             # emoji, «comillas», → y paréntesis incluidos
        # Atado a la lista blanca de la 22b/22c: un token que acá se muestra y que programados.py ocultaría difiere
        # sólo por lo que se relajó a propósito para la prosa (signos y emoji en los bordes; «/», «–», «—» y «,» entre palabras).
        P = previas._cargar("programados_34", PI / "cockpit-sistema" / "programados.py")
        muestras = " ".join(reales) + " cola-run.py historial.jsonl rev1/fix1 23a–23d 5,5 claude-opus-5-5 gpt-5.6-terra (07-10-2026) `vision` «pagina» ¿sirve? " \
            "/opt/nodo/datos ~/.local/bin --simular --opcion=valor NOMBRE=valor 22:53 test_uso.py D43). x=1 a.b-c_d"
        distintos = set()
        for token in muestras.split():
            if self.token_seguro(token):
                nucleo = self.RE["RE_BORDE"].sub("", token)
                if nucleo and not P._token_seguro(nucleo):
                    distintos.add(nucleo)
        self.assertTrue(all(re.search(r"[/–—,]", t) for t in distintos), distintos)
        self.assertLessEqual({"rev1/fix1", "23a–23d", "5,5"}, distintos)
        # Lo que la lista blanca le cuesta a un resumen: un nombre largo de archivo o un id pegado con guiones sale «oculto».
        self.assertEqual(self.una_linea("Toca test_cockpit_paginas.py y cola-22b.toml."), "Toca «oculto» y «oculto»")

    # ---------------- barra de uso ----------------
    def test_las_filas_son_las_formas_reales_que_pide_el_encargo(self):
        self.assertEqual([x["fase"] for x in self.de("32b")], ["autor", "rev1", "fix1", "rev2", "fix2", "rev3"])
        self.assertEqual({(x["motor"], x["modelo_real"]) for x in self.de("32b")}, {("claude", "claude-sonnet-5-5"), ("codex", "gpt-5.6-terra")})
        self.assertEqual(set(self.de("32b")[0]["tokens"]), {"entrada", "salida", "cache_lectura", "cache_escritura", "usd"})     # Claude
        self.assertEqual(set(self.de("32b")[1]["tokens"]), {"total"})                                                            # Codex
        self.assertEqual(self.de("29")[1]["pct_5h"], [33.0, 33.0])                                                               # Δ 0
        self.assertTrue(all("modelo_real" not in x and "modelo" not in x and "esfuerzo" not in x for x in self.de("19")))         # filas viejas
        # El historial real no tiene ninguna fila con esfuerzo "" (Haiku no ha corrido en una cola): ese caso se
        # arma más abajo sobre una fila real, cambiando sólo modelo y esfuerzo.
        self.assertFalse([x for x in self.FILAS if x.get("esfuerzo") == ""])

    def test_la_paleta_sale_de_modelos_toml_por_el_panel_y_no_esta_copiada(self):
        self.assertEqual(self.PALETA, ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5", "gpt-5.6-terra", "gpt-reserve", "gpt-5.6-luna"])
        self.assertEqual(self.tono("claude-sonnet-5-5"), "uso-m2")
        self.assertEqual(self.tono("gpt-5.6-terra"), "uso-m4")
        self.assertEqual(self.tono("gpt-6-astra"), "uso-gris")          # existe, pero no está en [niveles.*]
        self.assertEqual(self.tono(None), "uso-gris")
        self.assertIn("function modelosPaleta(modelos) { return [...new Set(Object.values((modelos || {}).niveles || {}).flatMap(t => Object.values(t || {}).map(x => x && x.modelo)).filter(Boolean))]; }", self.js)
        self.assertIn('cuentas: x.cuentas || {}, colas: x.colas && typeof x.colas === "object" ? x.colas : {}, paleta: modelosPaleta(x.modelos) };', self.js)       # 46b: el panel trae además colas_fuera y cuentas; 46c: colas
        self.assertIn('function tono(modelo) { const i = modelo ? (d.paleta || []).indexOf(modelo) : -1; return i >= 0 && i < TONOS ? `uso-m${i + 1}` : "uso-gris"; }', self.js)
        self.assertIn("const TONOS = 8,", self.js)
        # El panel real entrega esos mismos niveles, en el orden del archivo (se corre sobre la copia fija, sin tocar el nodo).
        cr = previas._cargar("cola_run_34", ENCARGOS_DIR / "cola-run.py")
        self.assertEqual(self.modelos_paleta({"niveles": cr.tomllib.loads(leer(FIXTURES_ENCARGOS / "modelos.toml"))["niveles"]}), self.PALETA)
        # Ningún nombre de modelo está escrito en la página ni en su hoja: un modelo nuevo en modelos.toml toma el tono que sigue.
        for modelo in self.PALETA + ["opus", "sonnet", "haiku", "gpt-"]:
            self.assertNotIn(modelo, tokens_js(self.js, strings=True), modelo)
            self.assertNotIn(modelo, self.css, modelo)
        con_mas = {"niveles": {"claude": {f"n{i}": {"modelo": f"m{i}"} for i in range(10)}}}
        paleta = self.modelos_paleta(con_mas)
        self.assertEqual([f"uso-m{i + 1}" if i < 8 else "uso-gris" for i in range(10)], [("uso-m%d" % (paleta.index(m) + 1)) if paleta.index(m) < 8 else "uso-gris" for m in paleta])

    def test_un_tramo_por_fila_en_orden_de_inicio_con_los_dos_motores(self):
        desordenadas = list(reversed(self.de("32b")))
        b = self.barra(desordenadas, "min")
        self.assertEqual([t["fase"] for t in b], ["autor", "rev1", "fix1", "rev2", "fix2", "rev3"])
        self.assertEqual([t["peso"] for t in b], [1.4, 7.5, 7.5, 8.0, 6.3, 6.4])                    # largo = minutos
        self.assertEqual([t["clases"] for t in b], [["uso-m2", "uso-e-medium"], ["uso-m4", "uso-e-medium"]] * 3)
        self.assertEqual(b[0]["titulo"], "autor · Claude (Cami) · claude-sonnet-5-5 · esfuerzo medium · 1.4 min · Δ 5 h +2 % · "
                                         "tokens: entrada 18, salida 10898, cache_lectura 352474, cache_escritura 46751, usd 0.3665148")
        self.assertEqual(b[1]["titulo"], "rev1 · Codex · gpt-5.6-terra · esfuerzo medium · 7.5 min · Δ 5 h +7 % · tokens: total 120568")
        d = self.barra(self.de("32b"), "delta")
        self.assertEqual([t["peso"] for t in d], [2.0, 7.0, 5.0, 7.0, 5.0, 7.0])                    # largo = Δ % 5 h de su cuenta
        self.assertIn("const porInicio = fs => [...fs].sort((a, b) => (Date.parse(a.inicio) || 0) - (Date.parse(b.inicio) || 0));", self.js)
        cuerpo = tramo(self.js, "function barraDeUso(fs, medida) {")
        self.assertIn('class: `uso-tramo ${tono(modeloFila(x))} ${claseEsfuerzo(x.esfuerzo)}${v == null ? " uso-sin-medida" : ""}`, title: t, role: "img", "aria-label": t', cuerpo)
        self.assertIn('if (v != null) i.style.setProperty("--peso", String(v));', cuerpo)           # el largo va por CSSOM
        self.assertIn("const modeloFila = x => x.modelo_real || x.modelo || null;", self.js)
        self.assertIn("barraDeUso(fs, medidaUso), leyendaUso(fs, medidaUso));", self.js)
        # Los tokens van tal como vienen, sin sumar: la forma de Claude y la de Codex no se mezclan.
        self.assertIn("Object.entries(t).map(([k, v]) => `${k} ${v}`).join(\", \") : \"sin datos\"", self.js)
        self.assertNotIn("reduce", tramo(self.js, "function tituloTramo(x) {"))

    def test_delta_cero_o_ausente_va_rayado_con_ancho_minimo_y_sin_cambio_medido(self):
        autor, rev1 = self.barra(self.de("29"), "delta")
        self.assertEqual((autor["peso"], autor["clases"]), (8.0, ["uso-m2", "uso-e-medium"]))
        self.assertEqual((rev1["peso"], rev1["clases"]), (None, ["uso-m5", "uso-e-medium", "uso-sin-medida"]))      # [33.0, 33.0]
        self.assertEqual(rev1["titulo"], "rev1 · Codex · gpt-reserve · esfuerzo medium · 3.3 min · Δ 5 h sin cambio medido · tokens: total 125578")
        self.assertEqual(self.barra(self.de("29"), "min")[1]["peso"], 3.3)                           # en minutos sí tiene medida
        base = self.de("29")[1]
        for pct in ([40.0, 12.0], None, [33.0], [33.0, None], "33"):                                  # ventana renovada, ausente o ilegible
            fila = {**base, "pct_5h": pct}
            self.assertIsNone(self.medida_tramo(fila, "delta"), pct)
            self.assertIn("Δ 5 h sin cambio medido", self.titulo_tramo(fila))
        self.assertIsNone(self.medida_tramo({k: v for k, v in base.items() if k != "pct_5h"}, "delta"))
        self.assertIsNone(self.medida_tramo({**base, "min": None}, "min"))
        self.assertIn("minutos sin datos", self.titulo_tramo({**base, "min": None}))
        self.assertIn('function medidaTramo(x, medida) { const v = medida === "delta" ? deltaUso(x) : x.min; return Number.isFinite(v) && v > 0 ? v : null; }', self.js)
        self.assertIn("Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) ? Math.round((p[1] - p[0]) * 10) / 10 : null;", self.js)
        self.assertIn('`Δ 5 h ${dl != null && dl > 0 ? `+${dl} %` : "sin cambio medido"}`', self.js)
        self.assertIn('muestra("uso-gris uso-e-medium uso-sin-medida", medida === "delta" ? "sin cambio medido" : "sin datos")', self.js)
        css = {s: d for m, s, d in reglas_css(self.css) if not m}
        self.assertEqual(css[".uso-sin-medida"]["flex"], "0 0 14px")
        self.assertIn("repeating-linear-gradient(45deg", css[".uso-sin-medida"]["background-image"])
        # El selector «Medir por» mueve la misma variable y redibuja; por defecto, minutos.
        self.assertIn('const MEDIDAS = [["min", "minutos"], ["delta", "Δ % 5 h de su cuenta"]];', self.js)
        self.assertIn('let medidaUso = "min";', self.js)
        self.assertIn('sel.value = medidaUso; sel.onchange = () => { medidaUso = sel.value; tiempo(); };', self.js)
        self.assertIn('el("label", { class: "uso-medida" }, "Medir por: ", sel)', self.js)

    def test_sin_esfuerzo_sin_modelo_y_modelo_fuera_de_la_lista(self):
        # Haiku no acepta esfuerzo: fila real del 32b con sólo modelo y esfuerzo cambiados (no hay ninguna así en el historial).
        haiku = {**self.de("32b")[0], "modelo": "claude-haiku-4-5", "modelo_real": "claude-haiku-4-5", "esfuerzo": ""}
        t = self.barra([haiku], "min")[0]
        self.assertEqual(t["clases"], ["uso-m3", "uso-e-vacio"])
        self.assertIn(" · claude-haiku-4-5 · sin esfuerzo · ", t["titulo"])
        # Encargo 19: filas reales sin modelo, sin modelo_real y sin esfuerzo.
        viejas = self.barra(self.de("19"), "min")
        self.assertEqual([x["clases"] for x in viejas], [["uso-gris", "uso-e-vacio"]] * 2)
        self.assertEqual(viejas[0]["titulo"], "autor · Codex · modelo desconocido · esfuerzo sin datos · 4.5 min · Δ 5 h +21 % · tokens: total 134056")
        self.assertIn("rev1 · Claude (Cami) · modelo desconocido · esfuerzo sin datos · 3.3 min · Δ 5 h sin cambio medido · tokens: entrada 30, salida 20380, ", viejas[1]["titulo"])
        # `modelo` vale cuando falta `modelo_real`; un modelo que no está en modelos.toml va en gris con su nombre.
        sin_real = {k: v for k, v in self.de("32b")[1].items() if k != "modelo_real"}
        self.assertEqual(self.barra([sin_real], "min")[0]["clases"][0], "uso-m4")
        raro = {**self.de("32b")[1], "modelo": "gpt-5.6-terra", "modelo_real": "gpt-6-astra", "esfuerzo": "xhigh"}
        t = self.barra([raro], "min")[0]
        self.assertEqual(t["clases"], ["uso-gris", "uso-e-xhigh"])
        self.assertIn(" · gpt-6-astra · esfuerzo xhigh · ", t["titulo"])
        self.assertIn('const nombre = m => (!m ? "modelo desconocido" : tono(m) === "uso-gris" ? `${m} (no está en modelos.toml)` : m);', self.js)
        self.assertIn('modeloFila(x) || "modelo desconocido", x.esfuerzo ? `esfuerzo ${x.esfuerzo}` : x.esfuerzo === "" ? "sin esfuerzo" : "esfuerzo sin datos"', self.js)
        self.assertIn('const claseEsfuerzo = e => (ESFUERZOS.includes(e) ? `uso-e-${e}` : "uso-e-vacio");', self.js)
        self.assertEqual(self.titulo_tramo({**sin_real, "tokens": None}).rsplit(" · ", 1)[1], "tokens: sin datos")
        self.assertIn("claude_diego", self.NOMBRES)                 # las cuentas salen con la etiqueta de cuentas.toml
        self.assertIn("[val(x.fase), cuenta(x.cuenta), ", tramo(self.js, "function tituloTramo(x) {"))

    def test_la_hoja_trae_un_tono_por_modelo_en_los_dos_temas_y_la_escala_de_esfuerzo(self):
        claro = {}
        for m, s, d in reglas_css(self.css):                    # un selector puede venir en más de una regla
            if not m:
                claro.setdefault(s, {}).update(d)
        tonos = [claro[f".uso-m{i}"]["--tono"] for i in range(1, 9)]
        self.assertEqual(len(set(tonos)), 8)
        oscuros = [claro.get(f':root[data-theme="dark"] .uso-m{i}', claro[f".uso-m{i}"])["--tono"] for i in range(1, 9)]
        self.assertEqual(len(set(oscuros)), 8)
        self.assertGreaterEqual(sum(a != b for a, b in zip(tonos, oscuros)), 7)       # el tema oscuro tiene sus propios pasos
        self.assertNotIn(claro[".uso-gris"]["--tono"], tonos)
        self.assertIn(':root[data-theme="dark"] .uso-gris', claro)
        # Ningún tono es un color de estado de tokens.css: en esta página verde, ámbar y rojo ya significan otra cosa.
        self.assertFalse(set(tonos + oscuros) & {v for tema in TOKENS.values() for v in tema.values()})
        # low < medium < high < xhigh: cada vez menos blanco y, al final, negro. Sin esfuerzo = medio, con borde punteado.
        mezcla = lambda clase: re.fullmatch(r"color-mix\(in oklab, var\(--tono\) (\d+)%, (white|black)\)", clase["--relleno"])
        low, medium, xhigh = mezcla(claro[".uso-e-low"]), mezcla(claro[".uso-e-medium"]), mezcla(claro[".uso-e-xhigh"])
        self.assertTrue(low and medium and xhigh)
        self.assertEqual((low[2], medium[2], xhigh[2]), ("white", "white", "black"))
        self.assertLess(int(low[1]), int(medium[1]))
        self.assertEqual(claro[".uso-e-high"]["--relleno"], "var(--tono)")
        self.assertEqual(claro[".uso-e-vacio"], {"--relleno": claro[".uso-e-medium"]["--relleno"], "border": "2px dotted var(--texto)"})
        self.assertEqual(claro[".uso-barra"]["gap"], "2px")
        self.assertIn("var(--peso", claro[".uso-tramo"]["flex"])
        self.assertIn("min-width", claro[".uso-tramo"])
        # La leyenda nombra los modelos presentes y la escala: el color nunca va solo.
        leyenda = tramo(self.js, "function leyendaUso(fs, medida) {")
        self.assertIn("[...new Set(porInicio(fs).map(modeloFila))].map(m => muestra(`${tono(m)} uso-e-high`, nombre(m)))", leyenda)
        self.assertIn('ESFUERZOS.map(e => muestra(`uso-gris uso-e-${e}`, e))', leyenda)
        self.assertIn('fs.some(x => !ESFUERZOS.includes(x.esfuerzo)) ? muestra("uso-gris uso-e-vacio", "sin esfuerzo") : null', leyenda)
        self.assertIn('const TONOS = 8, ESFUERZOS = ["low", "medium", "high", "xhigh"];', self.js)

    def test_la_pagina_sigue_sin_escribir_y_sin_comandos_nuevos(self):
        tokens_js(self.js)                                           # ValueError si algún ({[ queda sin cerrar
        codigo = tokens_js(self.js, strings=True)
        self.assertEqual(re.findall(r"cockpit\.file\([^)]*\)\.(\w+)", self.js), ["read"])
        self.assertEqual(len(re.findall(r"cockpit\.spawn\(", self.js)), 10)                          # los seis de antes del encargo 34, el de los botones de cola (46c), el del despacho (50a) y los dos `find` del índice (99)
        for prohibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "sudo"):
            self.assertNotIn(prohibido, codigo)
        self.assertNotIn("style=", self.css)
        # La prueba sólo lee sus copias dentro de pi/fixtures.
        self.assertTrue(str(FIXTURES_ENCARGOS).startswith(str(PI)))
        self.assertEqual(len(self.FILAS), 10)


# ---- Encargo 46b: «Carga vs. capacidad» en 🧵 Encargos y «Capacidad» en 💳 Cuentas. ----
def _js_redondeo(x):
    """Math.round(x * 10) / 10: la mitad sube (no es el redondeo al par de Python)."""
    return math.floor(x * 10 + 0.5) / 10


def n1(x):
    """Espejo de n1(): un decimal, coma y el signo menos tipográfico. String(12) es «12», no «12.0»."""
    v = _js_redondeo(x)
    return (str(int(v)) if v == int(v) else repr(v)).replace(".", ",").replace("-", "−")


class CargaVsCapacidadTests(unittest.TestCase):
    """Espejo en Python de las funciones puras del encargo 46b (en la Pi no hay motor de JS), atado al JS por texto.

    PANEL es la captura real de `--panel` de 46a-RESULTADO.md (`encargos/test_matriz_cuota.py --captura`), guardada
    en fixtures/encargos/panel-46a.json. Nada de acá lee /opt/nodo/datos, escribe un archivo ni manda un aviso."""

    PANEL = json.loads(leer(FIXTURES_ENCARGOS / "panel-46a.json"))
    VENTANAS = [("5h", "5 h", "pct_5h"), ("semanal", "sem", "pct_sem")]
    CLAVES = ["pct_5h", "pct_5h_min", "pct_5h_max", "pct_sem", "pct_sem_min", "pct_sem_max", "proxima_5h"]
    ESTADOS = {"pausada_sin_timer": "pausada, sin reanudación programada", "detenida": "detenida", "en_candado": "espera autorización",
               "caida": "caída", "sin_autorizacion": "sin autorización", "ilegible": "no se pudo leer"}
    TERMINOS = ["Capacidad", "Uso", "Carga comprometida", "Carga proyectada", "Holgura", "Renovación"]
    # Los nombres reales de encargos/vivo/ y de los manifiestos, copiados el 11-10-2026.
    COLAS_REALES = ("cola19 cola20 cola21 cola22 cola22b cola22c cola23 cola24 cola27 cola28 cola31 cola32 cola32c cola33 cola33b cola34 cola35 "
                    "cola36 cola37 cola38 cola39 cola40 cola41 cola42 cola43 cola43r cola43s cola44 cola46 cola47 cola48 cola48b cola49 cola50").split()

    @classmethod
    def setUpClass(cls):
        ResumenYUsoTests.setUpClass()                    # los RE_ de la lista blanca, leídos de encargos.js
        cls.js = leer(PAGINAS["encargos"] / "encargos.js")
        cls.css = leer(PAGINAS["encargos"] / "encargos.css")
        cls.cjs = leer(PAGINAS["cuentas"] / "cuentas.js")
        cls.ccss = leer(PAGINAS["cuentas"] / "cuentas.css")
        i, j = cls.js.index("// Encargo 46b: «Carga vs. capacidad»."), cls.js.index("function ahora() {")
        cls.bloque = cls.js[i:j]                          # todo lo nuevo de 🧵 Encargos
        i, j = cls.cjs.index("/* ---------- carga comprometida de las colas"), cls.cjs.index("/* ---------- ⏳ quién tiene margen")
        cls.cbloque = cls.cjs[i:j]                        # todo lo nuevo de 💳 Cuentas (menos los cinco cambios de pintarMargen)

    # --- espejo de 🧵 Encargos ---
    @staticmethod
    def con_etiqueta(t):
        partes = re.split(r"(Claude \((?:(?:Diego)|(?:Cami))\))", str(t))
        return "".join(x if i % 2 else re.sub(r"(^|[^A-Za-z0-9_À-ÿ])(?:(?:Diego)|(?:Camila)|(?:Cami))(?![A-Za-z0-9_À-ÿ])", r"\1«oculto»", x)
                       for i, x in enumerate(partes))

    @classmethod
    def del_panel(cls, x):
        return "sin datos" if x is None or x == "" else cls.con_etiqueta(ResumenYUsoTests.una_linea(x))

    @classmethod
    def fase_panel(cls, x):
        return "sin datos" if x is None or x == "" else ":".join(cls.del_panel(p) for p in str(x).split(":"))

    @staticmethod
    def hora(iso):
        return datetime.fromisoformat(iso).astimezone(CHILE).strftime("%H:%M") if isinstance(iso, str) else None

    @classmethod
    def renovacion(cls, pct, iso):
        h = cls.hora(iso)
        return f"↻ {n1(pct)} % " + (f"desde las {h}" if h else "en la próxima ventana")

    @staticmethod
    def nivel(h):
        return "mal" if h < 0 else "ojo" if h <= 10 else "ok"

    @classmethod
    def proyectar(cls, cola, cuentas):
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

        def fecha(v):       # Date.parse(): NaN si no es una fecha
            try:
                return datetime.fromisoformat(v) if isinstance(v, str) else None
            except ValueError:
                return None
        por_cuenta, debil = {}, bool(cola.get("debil"))
        for f in cola.get("fases_restantes") if isinstance(cola.get("fases_restantes"), list) else []:
            cu = cuentas.get(f.get("cuenta")) if isinstance(f, dict) and isinstance(f.get("cuenta"), str) else None
            ini = fecha(f.get("inicio_esperado")) if isinstance(f, dict) else None
            if not cu or ini is None or not all(num(f.get(k)) for k in ("prob", "pct_5h", "pct_sem")):
                debil = True
                continue
            if f.get("donde"):
                continue
            c = por_cuenta.setdefault(f["cuenta"], dict.fromkeys(cls.CLAVES, 0) | {"debil": False})
            for k in ("pct_5h", "pct_sem"):
                ren = fecha(cu.get("renueva_5h" if k == "pct_5h" else "renueva_sem"))
                if ren is None:
                    c["debil"] = True
                if ren is None or ini < ren:
                    c[k] += f["prob"] * f[k]
                    c[k + "_max"] += f[k]
                    c[k + "_min"] += f[k] if f["prob"] >= 1 else 0
                elif k == "pct_5h":
                    c["proxima_5h"] += f["prob"] * f[k]
            c["debil"] = c["debil"] or bool(f.get("debil"))
        for c in por_cuenta.values():
            c["debil"] = c["debil"] or debil
        return por_cuenta

    @classmethod
    def holguras(cls, regla, extra):
        salida = []
        for vid, etiqueta, k in cls.VENTANAS:
            w = next((x for x in (regla or {}).get("ventanas") or [] if x and x.get("ventana") == vid), None)
            if not w or any(not isinstance(w.get(c), (int, float)) for c in ("tope", "actual", "pronostico")):
                salida.append({"etiqueta": etiqueta, "sinDatos": True})
                continue
            real = _js_redondeo(w["tope"] - w["actual"] - w["pronostico"])
            salida.append({"etiqueta": etiqueta, "tope": w["tope"], "uso": w["actual"], "real": real, "nivel": cls.nivel(real),
                           "proyectada": _js_redondeo(w["tope"] - w["actual"] - w["pronostico"] - extra[k]) if extra else None})
        return salida

    @classmethod
    def celda(cls, c, proyectada, renueva):
        """Las líneas de una celda, en orden: lo que celdaCarga() pone en el <td>."""
        if not isinstance(c, dict):
            return {"clase": "vacia" + (" proyectada" if proyectada else ""), "lineas": ["—"]}
        lineas = ([f"+{n1(c['pct_5h'])} % 5 h", f"{n1(c['pct_5h_min'])}–{n1(c['pct_5h_max'])}"] if c["pct_5h"] > 0 else []) \
            + [f"+{n1(c['pct_sem'])} % sem ({n1(c['pct_sem_min'])}–{n1(c['pct_sem_max'])})"] \
            + ([cls.renovacion(c["proxima_5h"], renueva)] if c["proxima_5h"] > 0 else []) + (["débil"] if c.get("debil") else [])
        return {"clase": "num" + (" proyectada" if proyectada else ""), "lineas": lineas}

    @classmethod
    def matriz(cls, panel, marcadas=()):
        """Espejo de matrizCarga(): columnas, y por fila la cuenta, su uso, sus celdas y su Holgura."""
        reglas, cuentas = panel["reglas"], panel["cuentas"]
        activas = list(dict.fromkeys(c for r in reglas for c in r.get("celdas") or {}))
        proy = [(x["cola"], cls.proyectar(x, cuentas)) for x in panel["colas_fuera"] if x["cola"] in marcadas]
        proy = [(n, p) for n, p in proy if p]
        columnas = [(c, None) for c in activas] + proy
        ids = [c for c in dict.fromkeys([*cuentas, *(r["cuenta"] for r in reglas)])
               if any(r["cuenta"] == c for r in reglas) or any(c in p for _, p in proy)]
        filas = []
        for cid in ids:
            r = next((x for x in reglas if x["cuenta"] == cid), None)
            renueva = (r or cuentas.get(cid) or {}).get("renueva_5h")
            suyas = [p[cid] for _, p in proy if cid in p]
            extra = {k: sum(c[k] for c in suyas) for k in cls.CLAVES} if suyas else None
            hs = cls.holguras(r, extra)
            vieja = bool(r) and isinstance(r.get("fuente"), str) and r["fuente"].startswith("medido hace ")
            debiles = bool(r) and any(c and c.get("debil") for c in (r.get("celdas") or {}).values())
            filas.append({
                "cuenta": cls.del_panel(r["nombre"] if r else (cuentas.get(cid) or {}).get("nombre")),
                "uso": "Uso: " + (" · ".join(f"{n1(h['uso'])} % {h['etiqueta']}" for h in hs if not h.get("sinDatos")) or "sin datos"),
                "chip": cls.del_panel(r["fuente"]) if vieja else "débil" if r and r.get("debil") and not debiles else None,
                "celdas": [cls.celda(p.get(cid) if p is not None else (r or {}).get("celdas", {}).get(cola), p is not None, renueva) for cola, p in columnas],
                "holgura": [(h["etiqueta"], None, None) if h.get("sinDatos") else (h["etiqueta"], f"{n1(h['real'])} %", h["nivel"]) for h in hs],
                "renovacion": cls.renovacion(r["proxima_5h"], renueva) if r and r.get("proxima_5h", 0) > 0 else None,
                "proyectada": ("con carga proyectada: " + " · ".join(
                    [f"{h['etiqueta']} " + ("sin datos" if h.get("sinDatos") else f"{n1(h['proyectada'])} %") for h in hs]
                    + ([cls.renovacion(extra["proxima_5h"], renueva)] if extra["proxima_5h"] > 0 else []))) if extra else None})
        return {"columnas": [(cls.del_panel(c), "carga proyectada" if p is not None else "carga comprometida") for c, p in columnas],
                "filas": filas, "leyenda": "incluye carga proyectada" if proy else None}

    # --- espejo de 💳 Cuentas ---
    @staticmethod
    def cola_segura(x):
        return x if isinstance(x, str) and re.search(r"^[a-z]{1,12}[0-9]{0,4}[a-z]{0,2}$", x) and not re.search(r"(?:diego)|(?:cami)", x) else "«oculto»"

    @staticmethod
    def carga_de(reglas, cid):
        """Espejo de cargaDe(): por ventana, el uso, el tope y un tramo por cola; None si no hay nada que agregar."""
        r = next((x for x in reglas or [] if x.get("cuenta") == cid), None)
        if not r or not isinstance(r.get("celdas"), dict):
            return None
        colas = list(dict.fromkeys(c for x in reglas for c in (x.get("celdas") or {})))

        def ventana(vid, k, proxima):
            w = next((x for x in r.get("ventanas") or [] if x and x.get("ventana") == vid), None)
            if not w:
                return None
            partes = [(cola, i, r["celdas"][cola][k]) for i, cola in enumerate(colas) if cola in r["celdas"] and r["celdas"][cola][k] > 0]
            despues = r["proxima_5h"] if proxima and r.get("proxima_5h", 0) > 0 else 0
            return {"uso": w["actual"], "tope": w["tope"], "carga": w["pronostico"], "partes": partes, "despues": despues,
                    "renueva": r.get("renueva_5h")} if partes or despues else None
        h5, sem = ventana("5h", "pct_5h", True), ventana("semanal", "pct_sem", False)
        usadas = {c for w in (h5, sem) if w for c, _, _ in w["partes"]}
        return {"h5": h5, "sem": sem, "colas": [(c, i) for i, c in enumerate(colas) if c in usadas]} if h5 or sem else None

    @classmethod
    def barra_ventana(cls, usado, w):
        """Espejo de barraVentana(): los tramos de la barra, [(clase, data-ancho)]. Sin carga es la barra de siempre."""
        u = max(0, min(100, usado or 0))
        if not w:
            return [("usado", round(10 * u)), ("ocioso", round(10 * (100 - u)))]
        u = x = max(0, min(100, w["uso"]))
        tramos = [("usado", math.floor(10 * u + 0.5))]
        for _, i, pct in w["partes"]:
            ancho = max(0, min(pct, 100 - x))
            x += pct
            if ancho > 0:
                tramos.append((f"fantasma cola-c{i % 4 + 1}", math.floor(10 * ancho + 0.5)))
        return tramos + [("ocioso", math.floor(10 * max(0, 100 - max(u, x)) + 0.5))]

    # ---------------- C1: la matriz con la captura real ----------------
    def test_c1_la_matriz_dibuja_la_captura_real_del_panel(self):
        # La fixture ES la captura de 46a-RESULTADO.md: sus dos `texto` están ahí, letra por letra.
        resultado = leer(ENCARGOS_DIR / "46a-RESULTADO.md")
        for r in self.PANEL["reglas"]:
            self.assertIn(f'"texto": "{r["texto"]}"', resultado)
        self.assertEqual(set(self.PANEL), {"momento", "cuentas", "reglas", "colas_fuera"})
        m = self.matriz(self.PANEL)
        # Filas por cuenta (sólo las que usan las colas activas) y columnas por cola.
        self.assertEqual(m["columnas"], [("cola43r", "carga comprometida")])
        self.assertEqual([f["cuenta"] for f in m["filas"]], ["Claude (Cami)", "Codex"])
        cami, codex = m["filas"]
        self.assertEqual(cami["uso"], "Uso: 47 % 5 h · 81 % sem")
        # La celda: el esperado, su rango, la semana con su rango y ↻ con la hora de la renovación (00:49 UTC = 21:49).
        self.assertEqual(cami["celdas"], [{"clase": "num", "lineas": ["+30,9 % 5 h", "22,5–35", "+5,2 % sem (3–7)", "↻ 5,6 % desde las 21:49"]}])
        # A Codex todo el gasto de 5 h le cae después de su renovación (21:21): no hay línea de 5 h, sólo ↻.
        self.assertEqual(codex["celdas"], [{"clase": "num", "lineas": ["+4,2 % sem (2–6)", "↻ 19,1 % desde las 21:21"]}])
        # Holgura = tope − uso − carga comprometida: 90 − 47 − 30,9 = 12,1 (verde) y 75 − 81 − 5,2 = −11,2 (rojo).
        self.assertEqual(cami["holgura"], [("5 h", "12,1 %", "ok"), ("sem", "−11,2 %", "mal")])
        self.assertEqual(codex["holgura"], [("5 h", "21 %", "ok"), ("sem", "59,8 %", "ok")])
        self.assertEqual((cami["renovacion"], codex["renovacion"]), ("↻ 5,6 % desde las 21:49", "↻ 19,1 % desde las 21:21"))
        self.assertEqual((cami["chip"], cami["proyectada"], m["leyenda"]), (None, None, None))
        # Los colores de la Holgura: verde, ámbar a 10 puntos o menos del tope (el 0 incluido) y rojo si es negativa.
        self.assertEqual([self.nivel(h) for h in (59.8, 10.1, 10, 0.1, 0, -0.1, -11.2)], ["ok", "ok", "ojo", "ojo", "ojo", "mal", "mal"])
        self.assertIn('const nivelHolgura = h => (h < 0 ? "mal" : h <= 10 ? "ojo" : "ok");', self.js)
        self.assertIn("const real = Math.round((w.tope - w.actual - w.pronostico) * 10) / 10;", self.js)
        self.assertIn('el("b", { class: `valor ${h.nivel}` }, `${n1(h.real)} %`)', self.js)
        self.assertIn(".valor.ok { color: var(--ok); }.valor.ojo { color: var(--ojo); }.valor.mal { color: var(--mal); font-weight: 700; }", self.css)
        ambar = json.loads(json.dumps(self.PANEL))
        ambar["reglas"][0]["ventanas"][1]["actual"] = 50.0          # 90 − 50 − 30,9 = 9,1
        self.assertEqual(self.matriz(ambar)["filas"][0]["holgura"][0], ("5 h", "9,1 %", "ojo"))
        # El dibujo es el del espejo.
        for linea in ('c.pct_5h > 0 ? [el("span", { class: "linea grande" }, `+${v("pct_5h")} % 5 h`), el("span", { class: "linea tenue" }, `${v("pct_5h_min")}–${v("pct_5h_max")}`)] : null,',
                      'el("span", { class: "linea" }, `+${v("pct_sem")} % sem `, el("span", { class: "tenue" }, `(${v("pct_sem_min")}–${v("pct_sem_max")})`)),',
                      'c.proxima_5h > 0 ? el("span", { class: "chip" }, renovacion(c.proxima_5h, renueva)) : null,',
                      'c.debil ? el("span", { class: "chip ojo" }, "débil") : null);',
                      'const renovacion = (pct, iso) => { const h = horaCorta(iso); return `↻ ${n1(pct)} % ${h ? `desde las ${h}` : "en la próxima ventana"}`; };',
                      'const n1 = x => String(Math.round(x * 10) / 10).replace(".", ",").replace("-", "−");',
                      "const activas = [...new Set(reglas.flatMap(r => Object.keys(r.celdas || {})))];",
                      'el("span", { class: "carga-nota" }, `Uso: ${uso || "sin datos"}`),'):
            self.assertIn(linea, self.js)
        self.assertEqual((n1(35.0), n1(-11.200000000000003), n1(0.05), n1(-0.04)), ("35", "−11,2", "0,1", "0"))

    def test_c1_la_medicion_vieja_se_ve_con_el_texto_de_la_fuente(self):
        viejo = json.loads(json.dumps(self.PANEL))
        viejo["reglas"][0].update(fuente="medido hace 3 h", debil=True)      # la forma que publica la 46a (C6 de su informe)
        self.assertIn('f"medido hace {int((momento - medido).total_seconds() // 3600)} h"', leer(ENCARGOS_DIR / "cola-run.py"))
        cami, codex = self.matriz(viejo)["filas"]
        self.assertEqual((cami["chip"], codex["chip"]), ("medido hace 3 h", None))
        # Débil por otra razón (falta una hora de renovación): lo dice la fila. Si la débil es una celda, lo dice la celda.
        viejo["reglas"][0]["fuente"] = "uso.json"
        self.assertEqual(self.matriz(viejo)["filas"][0]["chip"], "débil")
        viejo["reglas"][0]["celdas"]["cola43r"]["debil"] = True
        fila = self.matriz(viejo)["filas"][0]
        self.assertEqual((fila["chip"], fila["celdas"][0]["lineas"][-1]), (None, "débil"))
        self.assertIn('const vieja = r && typeof r.fuente === "string" && r.fuente.startsWith("medido hace ");', self.js)
        self.assertIn('vieja ? el("span", { class: "chip ojo" }, delPanel(r.fuente)) : r && r.debil && !celdasDebiles ? el("span", { class: "chip ojo" }, "débil") : null),', self.js)
        # Sin dato de cuota (ventanas vacías, como lo publica la 46a): Holgura y Uso «sin datos», nunca un 0.
        viejo["reglas"][1].update(ventanas=[], alcanza=None)
        codex = self.matriz(viejo)["filas"][1]
        self.assertEqual((codex["uso"], codex["holgura"]), ("Uso: sin datos", [("5 h", None, None), ("sem", None, None)]))
        self.assertIn("if (!w || ![w.tope, w.actual, w.pronostico].every(Number.isFinite)) return { etiqueta, sinDatos: true };", self.js)

    # ---------------- C2: «¿y si la reanudo?» ----------------
    def test_c2_una_cola_fuera_no_esta_en_la_matriz_hasta_marcar_su_casilla(self):
        fuera = [c["cola"] for c in self.PANEL["colas_fuera"]]
        self.assertEqual(fuera, ["cola41", "cola42", "cola46"])
        sin = self.matriz(self.PANEL)
        self.assertFalse({c for c, _ in sin["columnas"]} & set(fuera))
        con = self.matriz(self.PANEL, {"cola41"})
        self.assertEqual(con["columnas"], [("cola43r", "carga comprometida"), ("cola41", "carga proyectada")])
        cami, codex = con["filas"]
        # cola41 retoma en rev3 con Claude (Cami): 15 % de 5 h y 2 % de la semana, con prob 1. A Codex no le toca.
        self.assertEqual(cami["celdas"][1], {"clase": "num proyectada", "lineas": ["+15 % 5 h", "15–15", "+2 % sem (2–2)"]})
        self.assertEqual(codex["celdas"][1], {"clase": "vacia proyectada", "lineas": ["—"]})
        # La Holgura real no cambia ni de valor ni de color; la proyectada va aparte: 12,1 − 15 = −2,9 y −11,2 − 2 = −13,2.
        self.assertEqual([f["holgura"] for f in con["filas"]], [f["holgura"] for f in sin["filas"]])
        self.assertEqual((cami["proyectada"], codex["proyectada"]), ("con carga proyectada: 5 h −2,9 % · sem −13,2 %", None))
        self.assertEqual(con["leyenda"], "incluye carga proyectada")
        # Dos casillas se suman. cola42: rev1 + rev2 × 0,67 + rev3 × 0,4489 en Claude (Cami) y dos arreglos en Codex.
        dos = self.matriz(self.PANEL, {"cola41", "cola42"})
        self.assertEqual([c for c, _ in dos["columnas"]], ["cola43r", "cola41", "cola42"])
        self.assertEqual(dos["filas"][0]["celdas"][2]["lineas"], ["+31,8 % 5 h", "15–45", "+4,2 % sem (2–6)"])
        self.assertEqual(dos["filas"][1]["celdas"][2]["lineas"], ["+7,8 % 5 h", "0–14", "+1,1 % sem (0–2)"])
        self.assertEqual(dos["filas"][0]["proyectada"], "con carga proyectada: 5 h −34,7 % · sem −17,4 %")
        self.assertEqual(dos["filas"][1]["proyectada"], "con carga proyectada: 5 h 13,2 % · sem 58,7 %")
        # cola46 no trae fases (su etapa no está en el manifiesto): la casilla va apagada y marcarla no agrega nada.
        self.assertEqual(self.proyectar(self.PANEL["colas_fuera"][2], self.PANEL["cuentas"]), {})
        self.assertEqual(self.matriz(self.PANEL, {"cola46"}), sin)
        self.assertIn('const casilla = el("input", { type: "checkbox", checked: n > 0 && marcadas.has(id), disabled: !n, '
                      "onchange: ev => { if (ev.target.checked) marcadas.add(id); else marcadas.delete(id); ahora(); } });", self.js)
        # El dibujo: borde punteado en la columna y en la línea de la Holgura, que no lleva la clase del color.
        self.assertIn('el("th", { class: `col-cola ${colorCola(i)}${c.porCuenta ? " proyectada" : ""}`, scope: "col" }', self.js)
        self.assertIn('extra ? el("span", { class: "linea proyectada" }, "con carga proyectada: ",', self.js)
        self.assertNotIn("valor", tramo(self.js, 'extra ? el("span", { class: "linea proyectada" }, "con carga proyectada: ",\n            [')) 
        self.assertIn(".carga-matriz th.proyectada, .carga-matriz td.proyectada { border: 2px dotted var(--tenue); }", self.css)
        self.assertIn(".carga-matriz .linea.proyectada { margin-top: 4px; padding: 2px 4px; border: 2px dotted var(--tenue);", self.css)
        self.assertIn('"incluye carga proyectada: ", proy.flatMap((p, i) => [i ? ", " : null, mencionCola(p.cola)]), ". Es un cálculo', self.js)

    def test_c2_la_casilla_no_escribe_en_ninguna_parte(self):
        # `marcadas` es un Set en la memoria de la pestaña: se pierde al recargar.
        self.assertIn("const marcadas = new Set();", self.bloque)
        self.assertEqual(sorted(set(re.findall(r"marcadas\.(\w+)", self.js))), ["add", "delete", "has"])
        codigo = tokens_js(self.bloque, strings=True)
        for escritura in ("cockpit.", "localStorage", "sessionStorage", "indexedDB", "document.cookie", "fetch(", "XMLHttpRequest", "proponer(",
                          "location.", "history.", "navigator."):
            self.assertNotIn(escritura, codigo, escritura)
        # Y la página entera sigue con sus seis spawn de siempre (ninguno nuevo) y sin un solo .replace( de cockpit.file.
        self.assertEqual(len(re.findall(r"cockpit\.spawn\(", self.js)), 10)       # el séptimo es el de los botones de cola (46c), el octavo el del despacho (50a) y los dos últimos los `find` del índice de Projects (99): fuera de este bloque
        self.assertEqual(re.findall(r"cockpit\.file\([^)]*\)\.(\w+)", self.js), ["read"])

    def test_c2_la_proyeccion_es_la_misma_suma_de_la_46a(self):
        """La misma cola, con el cola-run.py REAL, de las dos maneras: relanzada por un timer a las 21:15:30 (activa: sus
        celdas las calcula matriz_cuota()) y pausada sin timer, mirada a las 21:15:30 (fuera: sus fases las suma la página).
        Tiene que dar lo mismo, cuenta por cuenta y clave por clave."""
        import shutil
        import tempfile
        sys.path.insert(0, str(ENCARGOS_DIR))
        import test_matriz_cuota as mc

        def panel(momento, timers):
            tmp = Path(tempfile.mkdtemp(prefix="carga-46b-"))
            try:
                cr = mc.cargar()
                mc.preparar(cr, tmp, lambda: mc.T)
                for f in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola46.json"):
                    v = json.loads(leer(mc.FIX / f))
                    (tmp / "vivo" / f"{v['nombre']}.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
                cr._AP_MOD = mc.cargar(PI / "aplicar-propuesta.py")
                cr._AP_MOD.CODEX_MODELOS = str(FIXTURES_ENCARGOS / "models_cache.json")
                cr.SIMULANDO = True
                return cr.panel(vivos_dir=tmp / "vivo", uso_de=lambda cid: cr.uso(cid, mc.FIX / "uso-limites.json", mc.T), momento=momento,
                                viva=lambda nom: False, manifiestos_dir=mc.MANIFIESTOS, timers=timers)
            finally:
                shutil.rmtree(tmp, True)
        activa = panel(mc.T, [(mc.PARTE, mc.EXEC_COLA36.replace("cola36", "cola43r").replace("cola-36.toml", "cola-43.toml"))])
        # La captura de la fixture es exactamente este panel: si cola-run.py cambia lo que publica, acá se nota.
        final = json.loads(leer(FIXTURES_ENCARGOS / "panel-46a-56b.json"))
        self.assertEqual(activa, final)
        fuera = panel(mc.PARTE, [])
        self.assertEqual(fuera["reglas"], [])
        (cola,) = [c for c in fuera["colas_fuera"] if c["cola"] == "cola43r"]
        self.assertEqual(len(cola["fases_restantes"]), 6)
        mia = self.proyectar(cola, fuera["cuentas"])
        self.assertEqual(set(mia), {"claude_cami", "codex"})
        for r in activa["reglas"]:
            with self.subTest(r["cuenta"]):
                suya = r["celdas"]["cola43r"]
                self.assertEqual({k: round(v, 1) for k, v in mia[r["cuenta"]].items() if k != "debil"}, {k: suya[k] for k in self.CLAVES})
                self.assertEqual(mia[r["cuenta"]]["debil"], suya["debil"])
        # El JS hace esa misma cuenta, línea por línea (las de matriz_cuota() de cola-run.py, al lado).
        cr = leer(ENCARGOS_DIR / "cola-run.py")
        for js, py in (("if (Number.isNaN(ren) || ini < ren) { c[k] += f.prob * f[k]; c[`${k}_max`] += f[k]; if (f.prob >= 1) c[`${k}_min`] += f[k]; }",
                        'if ren[k] is None or ini < ren[k]:\n                        c[k] += f["prob"] * f[k]\n                        c[k + "_max"] += f[k]\n'
                        '                        c[k + "_min"] += f[k] if f["prob"] >= 1 else 0'),
                       ('else if (k === "pct_5h") c.proxima_5h += f.prob * f[k];',
                        'elif k == "pct_5h":\n                        c["proxima_5h"] += f["prob"] * f[k]'),
                       ("if (f.donde) continue;", 'if not f.get("donde"):'),
                       ('const CLAVES_CELDA = ["pct_5h", "pct_5h_min", "pct_5h_max", "pct_sem", "pct_sem_min", "pct_sem_max", "proxima_5h"];', "CLAVES_CELDA")):
            self.assertIn(js, self.js)
            self.assertIn(py, cr)
        self.assertEqual(list(cr_claves(cr)), self.CLAVES)
        self.assertIn('const ren = Date.parse(k === "pct_5h" ? cu.renueva_5h : cu.renueva_sem);', self.js)
        # Casos de borde del espejo: una fase en PC-2503 no gasta cuota; sin hora de renovación todo cuenta ahora y sale débil;
        # una fase sin la forma esperada o de una cuenta que el panel no conoce se salta y deja débil lo demás.
        cuentas = {"codex": {"renueva_5h": "2026-10-11T21:00:00-03:00", "renueva_sem": None}}
        fase = lambda **k: {"cuenta": "codex", "pct_5h": 10.0, "pct_sem": 2.0, "prob": 0.5, "inicio_esperado": "2026-10-11T20:00:00-03:00", "debil": False} | k
        self.assertEqual(self.proyectar({"fases_restantes": [fase(donde="pc2503")]}, cuentas), {})
        c = self.proyectar({"fases_restantes": [fase(), fase(inicio_esperado="2026-10-11T22:00:00-03:00", prob=1.0)]}, cuentas)["codex"]
        self.assertEqual(c, {"pct_5h": 5.0, "pct_5h_min": 0, "pct_5h_max": 10.0, "pct_sem": 3.0, "pct_sem_min": 2.0, "pct_sem_max": 4.0,
                             "proxima_5h": 10.0, "debil": True})
        raras = {"fases_restantes": [fase(cuenta="__proto__"), fase(prob="1"), None, fase(inicio_esperado="mañana"), fase()]}
        self.assertEqual(self.proyectar(raras, cuentas | {"claude_cami": {}}), {"codex": dict(c, pct_5h=5.0, pct_5h_max=10.0, pct_sem=1.0, pct_sem_min=0,
                                                                                         pct_sem_max=2.0, proxima_5h=0)})
        self.assertIn("const porCuenta = Object.create(null);", self.js)
        self.assertIn("if (!cu || Number.isNaN(ini) || ![f.prob, f.pct_5h, f.pct_sem].every(Number.isFinite)) { debil = true; continue; }", self.js)

    # ---------------- C3: 💳 Cuentas sin colas activas queda como hoy ----------------
    def test_c3_sin_colas_activas_la_barra_de_cuentas_queda_identica(self):
        antes = leer(FIXTURES / "cuentas" / "pintarMargen-antes-46b.js")       # pintarMargen() de antes de este encargo
        i, j = self.cjs.index("function pintarMargen() {"), self.cjs.index("/* ---------- 🧭 matriz común")
        ahora = self.cjs[i:j]
        # Los cinco cambios, deshechos uno por uno, dejan la función de antes letra por letra.
        cambios = [("(etiqueta, v, umbral, w) => {", "(etiqueta, v, umbral) => {"),
                   ("barraVentana(0, `${etiqueta}: sin medir desde la renovación`, w));", "barraUso(0, `${etiqueta}: sin medir desde la renovación`));"),
                   ("barraVentana(v.usado_pct, `${etiqueta}: ${pct(v.usado_pct)} usado`, w),", "barraUso(v.usado_pct, `${etiqueta}: ${pct(v.usado_pct)} usado`),"),
                   ("        const carga = cargaDe(cid);\n", ""),
                   ("c.umbral_5h, carga && carga.h5),", "c.umbral_5h),"), ("c.umbral_semanal, carga && carga.sem),\n            leyendaCarga(carga),\n", "c.umbral_semanal),\n")]
        for nuevo, viejo in cambios:
            self.assertEqual(ahora.count(nuevo), 1, nuevo)
            ahora = ahora.replace(nuevo, viejo)
        self.assertEqual(ahora, antes)
        # Y sin colas activas cada cambio entrega lo de antes: el panel sin reglas (o ilegible) es null, cargaDe() es null,
        # no hay leyenda (el() salta los null) y barraVentana() devuelve la barra de siempre, sola.
        self.assertIn("return Array.isArray(x.reglas) && x.reglas.length ? x.reglas.filter(r => r && typeof r === \"object\") : null;", self.cjs)
        self.assertRegex(tramo(tokens_js(self.cjs, strings=True), "async function leerCarga() {"), r"catch \(e\) \{\s*return null;\s*\}")
        self.assertIn("if (!r || !r.celdas || typeof r.celdas !== \"object\") return null;", self.cjs)
        self.assertIn("if (!w) return [barraUso(usado, titulo)];", self.cjs)
        self.assertIn("if (!carga || !carga.colas.length) return null;", self.cjs)
        self.assertIn("if (h == null || h === false) continue;", leer(COMUN / "dom.js"))
        self.assertIn("for (const h of hijos.flat()) {", leer(COMUN / "dom.js"))            # [barra] se aplana: mismo DOM
        for cid in ("claude_cami", "claude_diego", "codex"):
            self.assertIsNone(self.carga_de(None, cid))
            self.assertIsNone(self.carga_de([], cid))
        self.assertIsNone(self.carga_de(self.PANEL["reglas"], "claude_diego"))     # ninguna cola activa la usa: su barra no cambia
        self.assertEqual(self.barra_ventana(47, None), [("usado", 470), ("ocioso", 530)])
        self.assertIn('el("span", { class: "usado", "data-ancho": String(Math.round(10 * u)) }),\n'
                      '        el("span", { class: "ocioso", "data-ancho": String(Math.round(10 * (100 - u))) }));', leer(COMUN / "comun.js"))
        # El paquete común no se tocó: barraUso() sigue siendo de comun.js, y esta página sólo lee el panel.
        self.assertEqual(re.findall(r"cockpit\.spawn\(\[[^\]]*\]", self.cbloque), ['cockpit.spawn(["python3", COLA_RUN, "--panel"]'])
        # La ruta es fija y es la misma carpeta que lee 🧵 Encargos (no se arma con ningún dato).
        (carpeta,) = re.findall(r'^const DIR = "([^"]+)";$', self.js, re.M)
        self.assertIn(f'const COLA_RUN = "{carpeta}/cola-run.py";', self.cjs)
        self.assertEqual(Path(carpeta).parts[-2:], ("11-Pi5", "encargos"))

    def test_c3_con_colas_activas_la_barra_lleva_los_tramos_el_tope_y_la_renovacion(self):
        reglas = self.PANEL["reglas"]
        cami, codex = self.carga_de(reglas, "claude_cami"), self.carga_de(reglas, "codex")
        # Claude (Cami): 47 de uso + 30,9 de cola43r en 5 h (tope 90) y 5,6 que caen tras la renovación; en la semana, 81 + 5,2 (tope 75).
        self.assertEqual(cami["h5"], {"uso": 47.0, "tope": 90, "carga": 30.9, "partes": [("cola43r", 0, 30.9)], "despues": 5.6,
                                      "renueva": "2026-10-12T00:49:59+00:00"})
        self.assertEqual((cami["sem"]["uso"], cami["sem"]["tope"], cami["sem"]["partes"], cami["sem"]["despues"]), (81.0, 75, [("cola43r", 0, 5.2)], 0))
        self.assertEqual(self.barra_ventana(None, cami["h5"]), [("usado", 470), ("fantasma cola-c1", 309), ("ocioso", 221)])
        self.assertEqual(self.barra_ventana(None, cami["sem"]), [("usado", 810), ("fantasma cola-c1", 52), ("ocioso", 138)])
        # Codex: en 5 h no gasta nada ahora (todo va a la próxima ventana): la barra sin tramos, con el tope y la barra chica.
        self.assertEqual((codex["h5"]["partes"], codex["h5"]["despues"]), ([], 19.1))
        self.assertEqual(self.barra_ventana(None, codex["h5"]), [("usado", 690), ("ocioso", 310)])
        self.assertEqual(cami["colas"], [("cola43r", 0)])
        # Un tramo que no cabe se corta en 100 y no queda parte ociosa; el color sigue el orden de las colas activas.
        llena = {"uso": 80.0, "tope": 90, "carga": 37.0, "partes": [("a", 0, 12.0), ("b", 1, 25.0)], "despues": 0}
        self.assertEqual(self.barra_ventana(None, llena), [("usado", 800), ("fantasma cola-c1", 120), ("fantasma cola-c2", 80), ("ocioso", 0)])
        for linea in ("const ancho = Math.max(0, Math.min(p.pct, 100 - x));", "x += p.pct;",
                      'el("span", { class: "ocioso", "data-ancho": String(Math.round(10 * Math.max(0, 100 - Math.max(u, x)))) })),',
                      'marca.style.setProperty("--pos", `${Math.max(0, Math.min(100, w.tope))}%`);',
                      "const colorCola = i => `cola-c${i % 4 + 1}`;",
                      'el("div", { class: "tenue num" }, el("strong", {}, "Capacidad"),',
                      '`↻ ${horaCorta(w.renueva) ? `desde las ${horaCorta(w.renueva)}` : "en la próxima ventana"}: `,'):
            self.assertIn(linea, self.cjs)
        self.assertIn("aplicarAnchos(cont);", tramo(tokens_js(self.cjs, strings=True), "function pintarMargen() {"))
        # el() aplana un solo nivel de hijos (dom.js): barraVentana() devuelve una lista plana, sin listas adentro.
        cuerpo = tramo(tokens_js(self.cjs, strings=True), "function barraVentana(usado, titulo, w) {")
        self.assertIn("...(w.despues ? [", cuerpo)
        self.assertNotRegex(cuerpo, r"(?<!\.\.\.\()w\.despues \? \[")
        self.assertIn("e.append(h instanceof Node ? h : document.createTextNode(String(h)));", leer(COMUN / "dom.js"))
        # Las proyecciones de «¿y si la reanudo?» no llegan a 💳: la página no mira colas_fuera ni fases_restantes.
        for ajeno in ("colas_fuera", "fases_restantes", "marcadas", "proyect"):
            self.assertNotIn(ajeno, tokens_js(self.cjs, strings=True), ajeno)
        # Los mismos cuatro tonos en las dos hojas, y en el mismo orden de colas en los dos JS.
        tonos = lambda css: re.findall(r'^(?::root\[data-theme="dark"\] )?\.cola-c\d \{ --c: #[0-9a-f]{6}; \}.*$', css, re.M)
        self.assertEqual(len(tonos(self.css)), 3)
        self.assertEqual(tonos(self.css), tonos(self.ccss))
        self.assertIn("const colorCola = i => `cola-c${i % 4 + 1}`;", self.js)
        for clase in ("capacidad-pista", "capacidad-tope", "capacidad-leyenda", "capacidad-punto"):
            self.assertIn(f".{clase}", self.ccss)
            self.assertIn(clase, self.cjs)

    # ---------------- C4: los textos del panel son datos ----------------
    def test_c4_todo_texto_del_panel_pasa_por_la_lista_blanca_y_la_regla_de_nombres(self):
        self.assertIn('const delPanel = x => (x == null || x === "" ? "sin datos" : conEtiqueta(unaLinea(x)));', self.js)
        self.assertIn("function conEtiqueta(t) { return String(t).split(/(Claude \\((?:(?:Diego)|(?:Cami))\\))/).map((p, i) => (i % 2 ? p : "
                      "p.replace(/(^|[^A-Za-z0-9_À-ÿ])(?:(?:Diego)|(?:Camila)|(?:Cami))(?![A-Za-z0-9_À-ÿ])/g, `$1${OCULTO}`))).join(\"\"); }", self.js)
        # Cada campo de texto del panel que llega al DOM lo hace envuelto: cola, estado, motivo, fase, fuente y nombre.
        codigo = tokens_js(self.bloque, strings=True)
        campos = r"\b(?:x|c|p|r)\.(?:cola|motivo|fase|estado|fuente|nombre)\b|\)\.nombre\b"
        self.assertEqual(len(re.findall(campos, codigo)), 18)
        self.assertEqual(codigo.count("fasePanel(x.fase)"), 1)
        codigo = codigo.replace("fasePanel(x.fase)", "")           # la fase: delPanel() parte por parte (abajo)
        # Los usos que no muestran nada: la clave de la casilla, la búsqueda de la celda y las preguntas por el valor.
        for uso, veces in (("marcadas.has(String(x.cola))", 1), ("cola: String(x.cola),", 1), ("const id = String(x.cola),", 1),
                           ("propio(r && r.celdas, c.cola)", 1), ('typeof r.fuente === "string" && r.fuente.startsWith("medido hace ")', 1),
                           ("ESTADOS_FUERA.get(x.estado)", 1), ("x.motivo ? ", 1)):
            self.assertEqual(codigo.count(uso), veces, uso)
            codigo = codigo.replace(uso, "")
        # 95: los nombres de `colas_que_caben` (una lista, no un campo) van uno a uno por mencionCola().
        self.assertEqual(codigo.count("mencionCola(c)"), 1)
        codigo = codigo.replace("mencionCola(c)", "")
        # Los que sí muestran: todos dentro de delPanel() o, si es el nombre de una cola, de mencionCola() (95), que deja
        # un nombre válido tal cual y pasa por delPanel() el que no lo es. Quitados esos, no queda ningún campo de texto.
        envueltos = re.findall(r"(?:delPanel|mencionCola)\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)", codigo)
        self.assertEqual(len(envueltos), 8)
        for e in envueltos:
            self.assertRegex(e, campos)
            codigo = codigo.replace(e, "")
        self.assertEqual(re.findall(campos, codigo), [])
        self.assertIn('ESTADOS_FUERA.get(x.estado) || delPanel(String(x.estado ?? "").replace(/_/g, " "))', self.js)
        self.assertIn("`fase ${fasePanel(x.fase)} · ${x.motivo ? delPanel(x.motivo) : \"sin motivo\"}`", self.js)
        self.assertIn('const fasePanel = x => (x == null || x === "" ? "sin datos" : String(x).split(":").map(delPanel).join(":"));', self.js)
        # La fase real («41:rev3») entera no pasa la lista blanca (una palabra con «:» en medio): por eso va por partes.
        self.assertEqual((self.del_panel("41:rev3"), self.fase_panel("41:rev3"), self.fase_panel("46a:autor"), self.fase_panel(None)),
                         ("«oculto»", "41:rev3", "46a:autor", "sin datos"))
        self.assertEqual(self.fase_panel("41:sk-proj-A1b2C3d4E5f6G7h8:Diego"), "41:«oculto»:«oculto»")
        self.assertIn('el("strong", {}, mencionCola(x.cola))', self.js)
        # Los textos reales de la captura pasan enteros: la lista blanca no se come nada (trampa 22br1).
        self.assertEqual([self.fase_panel(c["fase"]) for c in self.PANEL["colas_fuera"]], ["41:rev3", "42:rev1", "46:autor"])
        reales = [str(c[k]) for c in self.PANEL["colas_fuera"] for k in ("cola", "motivo")] + \
                 [r[k] for r in self.PANEL["reglas"] for k in ("nombre", "fuente")] + [c for r in self.PANEL["reglas"] for c in r["colas"]] + \
                 ["medido hace 3 h", "sin sesión y sin señal desde el 11-10 18:55 (quedó en «corriendo»)", "espera la autorización de claude-fable-5-1",
                  "su vivo no se pudo leer (a medio escribir o sin la forma esperada)", "una etapa quedó NO DESPLEGABLE o fallaron las pruebas finales"]
        self.assertEqual(len(reales), 17)
        self.assertEqual([self.del_panel(t) for t in reales], reales)
        self.assertEqual([self.ESTADOS[c["estado"]] for c in self.PANEL["colas_fuera"]], ["pausada, sin reanudación programada"] * 3)
        for clave, texto in self.ESTADOS.items():
            self.assertIn(f'["{clave}", "{texto}"]', self.js)
        # Entradas hostiles: un secreto se oculta, un nombre suelto se oculta, la etiqueta de la cuenta se conserva, y el
        # HTML queda como texto (el() sólo crea nodos de texto; la prueba general prohíbe innerHTML en las dos páginas).
        self.assertEqual(self.del_panel("rechazado por Diego"), "rechazado por «oculto»")
        self.assertEqual(self.del_panel("Claude (Cami) sin margen; avisar a Cami y a Camila"), "Claude (Cami) sin margen; avisar a «oculto» y a «oculto»")
        self.assertEqual(self.del_panel("Claude (Camila) y (Diego)"), "Claude («oculto») y («oculto»)")
        self.assertEqual(self.del_panel("Diego"), "«oculto»")
        self.assertEqual(self.del_panel("el camino de Camino"), "el camino de Camino")                     # no es un nombre
        self.assertEqual(self.del_panel("token: sk-proj-A1b2C3d4E5f6G7h8"), "token: «oculto»")
        self.assertEqual(self.del_panel("falló\ncon   AKIAIOSFODNN7EXAMPLE"), "falló con «oculto»")
        self.assertEqual(self.del_panel('<img src=x onerror=alert(1)>'), "<img src=x «oculto»")      # «<img» queda a la vista, como texto
        self.assertEqual((self.del_panel(None), self.del_panel("")), ("sin datos", "sin datos"))
        hostil = json.loads(json.dumps(self.PANEL))
        hostil["colas_fuera"][0].update(cola="Diego", motivo="lo pidió Diego")
        hostil["reglas"][0]["nombre"] = "Cami"
        m = self.matriz(hostil, {"Diego"})
        self.assertEqual((m["columnas"][1][0], m["filas"][0]["cuenta"]), ("«oculto»", "«oculto»"))
        self.assertNotRegex(re.sub(r"Claude \((?:Diego|Cami)\)", "", json.dumps(m, ensure_ascii=False)), r"\b(Diego|Cami|Camila)\b")
        # Una clave que es un dato no llega a un objeto con prototipo.
        self.assertIn("const propio = (o, k) => (o && typeof o === \"object\" && typeof k === \"string\" && Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined);", self.js)
        self.assertIn("const ESTADOS_FUERA = new Map([", self.js)

    def test_c4_en_cuentas_el_nombre_de_la_cola_pasa_por_una_lista_mas_estricta(self):
        self.assertIn("const RE_COLA = /^[a-z]{1,12}[0-9]{0,4}[a-z]{0,2}$/;", self.cjs)
        self.assertIn("const RE_PERSONA = /(?:diego)|(?:cami)/;", self.cjs)
        self.assertIn('const colaSegura = x => (typeof x === "string" && RE_COLA.test(x) && !RE_PERSONA.test(x) ? x : "«oculto»");', self.cjs)
        # Los 34 nombres reales se ven enteros; lo que no tiene forma de nombre de cola, no.
        self.assertEqual(len(self.COLAS_REALES), 34)
        self.assertEqual([self.cola_segura(c) for c in self.COLAS_REALES], self.COLAS_REALES)
        hostiles = ["Diego", "diego", "colacami", "cami7", "<b>cola</b>", "cola 41", "sk-abc123", "AKIAIOSFODNN7EXAMPLE", "cola41; rm -rf", "cola-41",
                    "a" * 15, "cola12345", "cola41abc", "", None, 41, "__proto__", "ghp_abcdef"]
        self.assertEqual({self.cola_segura(c) for c in hostiles}, {"«oculto»"})
        # No es más blanda que la lista blanca de 🧵 Encargos: lo que acá se muestra, allá también, igual.
        for c in [*self.COLAS_REALES, *(h for h in hostiles if isinstance(h, str) and h)]:
            if self.cola_segura(c) != "«oculto»":
                self.assertEqual(self.del_panel(c), c, c)
        # Es el único texto del panel que 💳 muestra (lo demás son números): los dos usos pasan por ella.
        codigo = tokens_js(self.cbloque, strings=True)
        self.assertEqual(len(re.findall(r"\bcolaSegura\((?:p|c)\.cola\)", codigo)), 2)
        self.assertEqual(len(re.findall(r"\.cola\b", codigo)), 4)          # los otros dos comparan nombres, no los muestran
        self.assertEqual((codigo.count("w.partes.map(x => x.cola)"), codigo.count("usadas.has(x.cola)")), (1, 1))
        for campo in ("motivo", "estado", "texto", "nombre", "fuente"):
            self.assertNotRegex(codigo, rf"\.{campo}\b", campo)

    # ---------------- C5: el celular ----------------
    def test_c5_en_el_celular_la_matriz_se_desplaza_con_la_columna_de_cuentas_fija(self):
        reglas = {sel: decl for media, sel, decl in reglas_css(self.css) if not media}
        self.assertEqual(reglas[".carga-envoltura"]["overflow-x"], "auto")
        tabla, fija = reglas[".carga-matriz"], reglas[".carga-matriz th.fila"]
        self.assertEqual(tabla["min-width"], "560px")              # más ancha que un teléfono: se desplaza dentro de la envoltura
        self.assertEqual(tabla["border-collapse"], "separate")     # con collapse, sticky pierde el borde de la celda
        self.assertEqual({k: fija[k] for k in ("position", "left", "background", "z-index")},
                         {"position": "sticky", "left": "0", "background": "var(--tarjeta)", "z-index": "1"})
        # La tabla va dentro de la envoltura, y la primera celda de cada fila (cabecera y cuerpo) es la fija.
        self.assertIn('return [el("div", { class: "carga-envoltura" }, el("table", { class: "carga-matriz" }, el("thead", {}, cabeza), el("tbody", {}, filas))),', self.js)
        self.assertIn('const cabeza = el("tr", {}, el("th", { class: "fila", scope: "col" }, "Cuenta"),', self.js)
        self.assertIn('return el("tr", {}, el("th", { class: "fila", scope: "row" }, delPanel(', self.js)
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1.0" />', leer(PAGINAS["encargos"] / "index.html"))
        # Nada de la matriz ensancha la página: las reglas nuevas no tocan main ni body (lo mira también la prueba general).
        self.assertFalse([sel for sel in reglas if sel in ("main", "body", "html")])

    # ---------------- C7 y C8 ----------------
    def test_c7_el_manifiesto_instala_las_dos_paginas(self):
        import tomllib
        man = tomllib.loads(leer(ENCARGOS_DIR / "cola-46.toml"))
        self.assertEqual(man["paginas"], {"encargos": "cockpit-encargos", "cuentas": "cockpit-cuentas"})
        self.assertIn("pi/test_cockpit_paginas.py", man["pruebas"])
        # Este encargo no toca el paquete común (no está en [paginas]): las dos páginas traen lo suyo.
        for nombre in ("conEtiqueta", "delPanel", "colaSegura", "colorCola", "cargaDe", "barraVentana", "n1", "horaCorta"):
            for comun in ("comun.js", "barra.js", "dom.js"):
                self.assertNotIn(nombre, declarados_arriba(leer(COMUN / comun)), nombre)

    def test_c8_los_textos_visibles_usan_solo_los_terminos_de_la_pagina(self):
        textos = lambda codigo: [t for t in re.findall(r'"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`', codigo) for t in t if t]
        visibles = textos(self.bloque) + textos(self.cbloque)
        junto = "\n".join(visibles)
        # Los títulos y las leyendas que pide el encargo, tal cual.
        for texto in ("Carga vs. capacidad", "Detenidas o pausadas", "incluye carga proyectada", "¿y si la reanudo?", "Holgura", "carga comprometida",
                      "carga proyectada", "Capacidad", "desde las ", "tope − uso − carga comprometida"):
            self.assertIn(texto, junto, texto)
        self.assertIn('el("h2", {}, "Carga vs. capacidad")', self.js)
        self.assertIn('el("h3", {}, "Detenidas o pausadas")', self.js)
        self.assertIn('el("th", { class: "holgura", scope: "col" }, "Holgura",', self.js)
        self.assertIn('el("strong", {}, "Capacidad")', self.cjs)
        # La ayuda de la matriz explica cada término en una línea: los seis de la tabla, en su orden.
        ayuda = re.findall(r'^    \["([^"]+)", "([^"\n]+)"\],?', tramo(self.js, "const AYUDA_CARGA = ["), re.M) + \
            re.findall(r'^    \["([^"]+)", "([^"\n]+)"\]\];$', self.js, re.M)
        self.assertEqual(list(dict.fromkeys(t for t, _ in ayuda)), self.TERMINOS)
        self.assertIn('el("details", { class: "carga-ayuda" }, el("summary", {}, "Qué significa cada término"), '
                      'el("dl", {}, AYUDA_CARGA.flatMap(([t, x]) => [el("dt", {}, t), el("dd", {}, x)]))),', self.js)
        self.assertTrue(all("\n" not in x and len(x) < 130 for _, x in ayuda))
        # Los términos nuevos pasan enteros por la lista blanca de textos.
        for texto in [*self.TERMINOS, "Carga vs. capacidad", "Detenidas o pausadas", "incluye carga proyectada", "¿y si la reanudo?",
                      "tope − uso − carga comprometida", "con carga proyectada: 5 h −2,9 % · sem −13,2 %", "↻ 5,6 % desde las 21:49"]:
            self.assertEqual(self.del_panel(texto), texto, texto)
        # Los términos retirados no están en ningún texto de lo nuevo, ni la lista vieja en la página.
        for retirado in ("regla de cuotas", "regla de las colas", "Total", "total", "pronóstico", "Pronóstico", "próxima fase", "costo", "margen", "alcanza"):
            self.assertNotIn(retirado, junto, retirado)
        for viejo in ("La regla de las colas", "regla-cuotas", "regla-no", "tarjetaRegla", "próxima fase"):
            self.assertNotIn(viejo, self.js + self.css, viejo)
        # Ningún nombre de campo del JSON cambió: la página lee los que publica el panel (y cola-run.py no se tocó).
        cr = leer(ENCARGOS_DIR / "cola-run.py")
        for campo in ("reglas", "colas_fuera", "cuentas", "celdas", "fases_restantes", "ventanas", "proxima_5h", "renueva_5h", "renueva_sem",
                      "inicio_esperado", "pct_5h_min", "pct_sem_max", "pronostico", "actual", "tope", "fuente", "debil", "donde", "prob"):
            self.assertIn(f'"{campo}"', cr, campo)
            self.assertRegex(self.bloque + self.js[self.js.index("async function leerPanel()"):self.js.index("async function leer()")], rf"\b{campo}\b", campo)


# ---- Encargo 84a: 🧵 Encargos pasa a ser la consola del nodo (marco y navegación). ----
class ConsolaEncargosTests(unittest.TestCase):
    """Pruebas estáticas del marco: en la Pi no hay motor de JS. Recargar en el mismo submódulo (C5, la parte visual) y
    los anchos (C6) los verifica Claude (Diego) en el PC con el cockpit falso. Nada de acá lee ni escribe en el nodo."""

    # Los spawn de la página antes de la 84a: los de la copia instalada el 24-10-2026, que hasta la línea 818 es igual a la
    # del vault antes del cambio. La consola no agrega ninguno (C3).
    SPAWN_ANTES = {'["find", DIR, "-maxdepth", "1", "-name", "cola-*.toml", "-print"]', '["python3", COLA_RUN, "--panel"]',
                   '["python3", COLA_RUN, EJEMPLO, "--simular", "--con-cambios"]', '["python3", REGISTRO_AVISOS, "--panel"]',
                   '["python3", `${DIR}/cola-run.py`, "--panel"]', '["tmux", "ls", "-F", "#{session_name}"]',
                   'argvAccion(accion, cola, simular, autorizar === true && accion === "reanudar" && !simular)', 'argvDespacho(orden, motivo)'}
    # Encargo 99: los dos `find` de argumentos fijos del índice de NN-*.md (Projects). Ninguno lleva datos ni sudo.
    SPAWN_99 = {'["find", DIR, "-maxdepth", "1", "-name", MD_ENCARGOS, "-printf", "%T@ %f\\\\n"]',
                '["find", DIR, "-maxdepth", "1", "-name", MD_ENCARGOS, "-exec", "grep", "-m1", "-H", "^# ", "{}", "+"]'}
    SUBMODULOS = ["flujo", "ahora", "projects", "tiempo", "historial", "bitacora", "avisos", "config"]

    @classmethod
    def setUpClass(cls):
        CargaVsCapacidadTests.setUpClass()                 # el espejo de delPanel() (y los RE_ de la lista blanca)
        cls.html = leer(PAGINAS["encargos"] / "index.html")
        cls.js = leer(PAGINAS["encargos"] / "encargos.js")
        cls.css = leer(PAGINAS["encargos"] / "encargos.css")
        cls.codigo = tokens_js(cls.js, strings=True)
        cls.consola = tokens_js(cls.js[cls.js.index("// Encargo 84a: la consola del nodo"):], strings=True)
        cls.barra = tokens_js(leer(COMUN / "barra.js"), strings=True)

    def test_c2_los_modulos_son_los_de_barra_js(self):
        # Ctrl+K usa MODULOS, que viene de barra.js; la consola no copia destinos ni etiquetas.
        grupos = re.findall(r'\{ id: "(\w+)", icono: "([^"]+)", texto: "([^"]+)", destino: "([^"]+)" \}', tramo(self.barra, "const GRUPOS = ["))
        self.assertEqual([i for i, _, _, _ in grupos], [n for n in MENU if n != "memoria"])
        self.assertIn(("encargos", "🧵", "Encargos", "/encargos"), grupos)
        self.assertIn("CARPETA_PROPUESTAS, GRUPOS, actual,", self.barra)          # barraNodo la exporta
        self.assertIn("const MODULOS = barraNodo.GRUPOS.flat();", self.js)
        consola = [g for grupo in [[x] for x in grupos] for g in grupo]           # .flat() de grupos de un nivel
        self.assertEqual(consola, grupos)
        # Ninguna copia a mano: ni `destino:` ni los textos o destinos de barra.js como literales de la página.
        self.assertEqual(re.findall(r"\bdestino\s*:", self.codigo), [])
        sin_timer = self.codigo.replace('cockpit.jump("/sistema")', "")             # el «ver en ⏰ Programados» de la 46c
        for _, _, texto, destino in grupos:
            self.assertNotIn(f'"{texto}"', self.consola, texto)                    # «Encargos» sí es una columna de «Precisión del pronóstico»
            self.assertNotIn(f'"{destino}"', sin_timer, destino)
        # Ctrl+K conserva los destinos de barra.js; la única navegación externa es m.destino.
        entradas = tramo(self.js, "function entradasBusqueda() {")
        self.assertIn('MODULOS.map(m => ({ tipo: "módulo", texto: `${m.icono} ${m.texto}`, ir: () => irModulo(m) }))', entradas)
        self.assertIn("function irModulo(m) { if (m.id === PAQUETE) ir(PORTADA); else cockpit.jump(m.destino); }", self.js)
        self.assertIn('const PAQUETE = "encargos", PORTADA = "flujo";', self.js)              # 84b: la portada es 🕸️ Flujo
        self.assertEqual(sorted(re.findall(r"cockpit\.jump\(([^)]*)\)", self.codigo)), ['"/sistema"', "m.destino"])
        self.assertNotIn("cuentasPie", self.js)
        for muerto in (".consola-riel", ".consola-cajon", ".consola-modulo", ".riel-pie", ".consola-velo"):
            self.assertNotIn(muerto, self.css, muerto)

    def test_c3_sin_ejecucion_nueva(self):
        self.assertEqual(set(re.findall(r"cockpit\.spawn\((\[[^\]]*\]|\w+\([^)]*\))", self.js)), self.SPAWN_ANTES | self.SPAWN_99)
        self.assertEqual(len(re.findall(r"cockpit\.spawn\(", self.js)), 10)
        self.assertIn('MD_ENCARGOS = "[0-9]*-*.md";', self.js)
        self.assertIn('const argvAccion = (accion, cola, simular, autorizar) => ["python3", COLA_RUN, "--accion", accion, cola, ...(simular ? ["--simular"] : []), ...(autorizar ? ["--autorizar", cola] : [])];', self.js)
        self.assertIn('const argvDespacho = (orden, motivo) => ["python3", COLA_RUN, "--despacho", orden, "--por", POR_PAGINA, ...(motivo ? ["--motivo", motivo] : [])];', self.js)
        self.assertIn("const COLA_VALIDA = /^cola[0-9]{2}[a-z0-9]*$/;", self.js)
        self.assertNotIn("sudo", self.codigo)
        self.assertEqual(re.findall(r"cockpit\.file\([^)]*\)\.(\w+)", self.js), ["read"])
        for x in ("fetch(", "XMLHttpRequest", "cockpit.http", "cockpit.channel", "cockpit.dbus", "cockpit.script", "WebSocket", "eval(", "new Function"):
            self.assertNotIn(x, self.codigo, x)
        # Lo nuevo sólo llama a cockpit para saltar de página, y lo único que guarda es el tema de Cockpit.
        self.assertEqual(re.findall(r"cockpit\.\w+", self.consola), ["cockpit.jump"])
        self.assertEqual(re.findall(r"(?:local|session)Storage\.\w+", self.consola), ["localStorage.getItem", "localStorage.setItem"])
        self.assertNotIn("proponer(", self.consola)
        # El badge de 🔔 lee los avisos con la función de la pestaña (su comando fijo), no con uno propio.
        self.assertIn("cargarAvisos().then(pintarConsola);", self.consola)
        # La prueba mide: un spawn nuevo en la consola cambia el conjunto.
        malo = self.js + '\ncockpit.spawn(["sudo", "-n", "/usr/local/bin/x"]);'
        self.assertNotEqual(set(re.findall(r"cockpit\.spawn\((\[[^\]]*\]|\w+\([^)]*\))", malo)), self.SPAWN_ANTES | self.SPAWN_99)

    def test_c4_csp(self):
        self.assertIsNone(re.search(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", self.html))
        self.assertNotIn("<style", self.html)
        self.assertIsNone(re.search(r"style\s*=", self.html))
        self.assertIsNone(re.search(r"""setAttribute\(\s*["']style""", self.codigo))
        # La única URL del JS es el espacio de nombres de SVG, que no se carga: es el nombre de createElementNS.
        self.assertEqual(re.findall(r"https?://[^\"'`\s]*", self.codigo), ["http://www.w3.org/2000/svg"])
        self.assertIn("document.createElementNS(SVG, tag)", self.js)
        self.assertNotIn("innerHTML", self.codigo)
        # svg() pone atributos: ninguno es style ni un enlace.
        for attrs in re.findall(r'svg\("\w+", \{([^}]*)\}', self.consola):
            self.assertIsNone(re.search(r"\b(?:style|href|src)\b", attrs), attrs)
        self.assertNotIn("url(", self.css)
        self.assertNotIn("@import", self.css)
        man = leer(PAGINAS["encargos"] / "manifest.json")
        self.assertNotIn("unsafe-inline", man)
        self.assertNotIn("content-security-policy", json.loads(man))
        self.assertNotIn("revisar-anchos", self.html)                           # el archivo de QA no se carga

    def test_c4_glosario_y_tooltip_accesible(self):
        glosario = leer(PAGINAS["encargos"] / "glosario.js")
        requeridos = {"AI Ops", "Flow", "Runs", "Timeline", "Traces", "Logs", "Alerts", "Policies", "Task", "Run", "Minutes", "Steps", "Rework rate", "Estimation error", "Cost per task", "Worker", "Orchestrator", "Cross-model review", "HITL", "Release gate", "Model routing", "Guardrails", "Home", "Providers", "Agents", "Infrastructure", "News", "Scope", "Pipeline", "Forecast"}
        definidos = dict(re.findall(r'^    "([^"]+)": "([^"]+)"[,]?$', glosario, re.M))
        self.assertTrue(requeridos <= set(definidos))
        self.assertTrue(all(v and len(v) <= 200 for v in definidos.values()))
        usados = set(re.findall(r'data-term="([^"]+)"', self.html + self.js + leer(PAGINAS["encargos"] / "red.js")))
        usados |= set(re.findall(r'\["[^]]*", "([^"]+)", "', glosario))
        self.assertTrue(usados <= set(definidos))
        self.assertIn('id="term-tooltip" class="term-tooltip" role="tooltip"', self.html)
        self.assertIn('id="releer"', self.html)
        self.assertIn('id="campana"', self.html)
        self.assertNotIn("consola-solo-ancho", self.html + self.css)
        for linea in ('n.setAttribute("aria-describedby", "term-tooltip");', 'if (!n.matches("button, a, input, select, textarea, [tabindex]")) n.setAttribute("tabindex", "0");', 'n.addEventListener("pointerenter", mostrarTooltip);', 'n.addEventListener("focus", mostrarTooltip);', 'const origen = ev.currentTarget; if (ev.pointerType !== "mouse") espera = setTimeout(() => mostrarTooltip({ currentTarget: origen }), 450);'):
            self.assertIn(linea, self.js)

    def test_c5_cada_submodulo_tiene_su_ruta(self):
        riel = riel_encargos(self.html)
        ids = [p for p, _ in riel]
        self.assertEqual(ids, self.SUBMODULOS)
        self.assertEqual(re.findall(r'data-p="(\w+)"', self.html), ids)          # sólo los del riel
        self.assertEqual(re.findall(r'<section data-panel="(\w+)"', self.html), ids)
        self.assertEqual(re.findall(r"<section data-panel=\"\w+\"( hidden)?></section>", self.html), [""] + [" hidden"] * 7)
        self.assertIn("({ flujo, ahora, projects, tiempo, historial: hist, bitacora, avisos, config })[panel]();", self.js)
        # Espejo de rutaDeHash(): el RUTA del propio JS ($ de JS = \Z de Python) y la lista del riel.
        (fuente,) = re.findall(r"^const RUTA = /(.+)/;$", self.js, re.M)
        ruta = re.compile(fuente.replace("$", r"\Z"))
        self.assertIn("function rutaDeHash(h) { const m = RUTA.exec(h || \"\"); return m && botonesPestanas().some(b => b.dataset.p === m[1]) ? m[1] : null; }", self.js)
        self.assertIn('const botonesPestanas = () => [...document.querySelectorAll("#pestanas [data-p]")];', self.js)

        def ruta_de_hash(h):
            m = ruta.match(h or "")
            return m.group(1) if m and m.group(1) in ids else None
        for p in ids:
            self.assertEqual(ruta_de_hash(f"#/{p}"), p)
        self.assertEqual(ruta_de_hash("#/historial?o=usd:desc"), "historial")
        self.assertEqual(ruta_de_hash("#/flujo?e=85b&o=tokens:asc"), "flujo")
        for h in ("", "#", "#ahora", "#/", "#/Ahora", "#/ahora/", "#/ahora?x=1", "#/Flujo", "#/flujo/", "#/red", "#/../ahora", "#/%3Cimg%3E", "#/constructor", "#/__proto__", "#/ahora\n"):
            self.assertIsNone(ruta_de_hash(h), h)
        self.assertEqual(ids[0], "flujo")                                         # PORTADA (84b), primera del riel
        # Navegar cambia el hash; el hash elige el panel; al cargar se vuelve al del hash o a la portada.
        for linea in ('function ir(p) { const h = `#/${p}?o=${orden.clave}:${orden.desc ? "desc" : "asc"}`; if (location.hash === h) mostrar(p); else location.hash = h; }',
                      'window.addEventListener("hashchange", () => mostrar(rutaDeHash(location.hash) || PORTADA));',
                      "mostrar(rutaDeHash(location.hash) || PORTADA);", "if (!rutaDeHash(location.hash)) location.replace(`#/${panel}`);",
                      'botonesPestanas().forEach(b => b.addEventListener("click", () => ir(b.dataset.p)));'):
            self.assertEqual(self.js.count(linea), 1, linea)
        self.assertIn('q.set("o", `${orden.clave}:${orden.desc ? "desc" : "asc"}`); history.replaceState(null, "", `#/${panel}?${q.toString().replace(/%3A/gi, ":")}`);', self.js)
        self.assertIn('history.replaceState(null, "", `#/${panel}?${q.toString().replace(/%3A/gi, ":")}`);', self.js)
        # 84b suma `flujo` con un botón y una sección: el riel y la ruta no tienen la lista escrita. El único nombre de
        # submódulo en lo nuevo es el destino de un encargo en el buscador (su tarjeta de la Línea de tiempo).
        self.assertEqual(re.findall(r'"(tiempo|historial|bitacora|config)"', self.consola), ["tiempo"])
        for f in ("function rutaDeHash(h) {", "function mostrar(p) {", "function nombreSub(p) {"):
            self.assertIsNone(re.search(r'"(?:ahora|tiempo|historial|bitacora|avisos|config)"', tramo(self.codigo, f)), f)
        self.assertIn('id="pestanas" class="consola-pestanas"', self.html)

    def test_c6_anchos(self):
        qa = leer(PAGINAS["encargos"] / "revisar-anchos.js")
        self.assertIn("const ANCHOS_OBJETIVO=[1280,1024,800,720,375];", qa)
        self.assertIn("window.revisarAnchos=revisarAnchos;", qa)
        self.assertIn('document.querySelectorAll("header, header *, aside, aside *, main, main *")', qa)
        self.assertEqual(declarados_arriba(qa), set())
        r = {(m, s): d for m, s, d in reglas_css(self.css)}
        self.assertEqual(r[("", ".consola-pestanas")]["overflow-x"], "auto")
        self.assertEqual(r[("(max-width: 719px)", ".consola-pestanas")]["display"], "none")
        self.assertEqual(r[("(max-width: 719px)", ".consola-pestanas-select")]["display"], "block")
        # El cuerpo no se desplaza; el área de trabajo, sí. La barra mide entre 60 y 68 px.
        self.assertEqual(r[("", ".consola")]["overflow"], "hidden")
        self.assertEqual(r[("", ".consola")]["grid-template-rows"], "64px minmax(0, 1fr)")
        self.assertEqual(r[("", ".consola-trabajo")]["overflow"], "auto")
        self.assertIn('<body class="consola">', self.html)
        self.assertIn('<main class="consola-trabajo">', self.html)

    def test_el_buscador_muestra_texto_seguro_y_solo_navega(self):
        b = tramo(self.js, "function entradasBusqueda() {")                      # con las plantillas enteras
        partes = set(re.findall(r"\$\{(.*?)\}", " ".join(re.findall(r"texto: `([^`]*)`", b))))
        self.assertEqual(partes, {"m.icono", "m.texto", "nombreSub(b.dataset.p)", "c", "conEtiqueta(resumenCola(c))", "delPanel(id)",
                                  "conEtiqueta(resumenEtapa(etapaDe(id)))", "momentoAviso(x.momento)", 'delPanel(String(x.texto ?? "").split("\\n")[0])'})
        self.assertIn('.filter(c => typeof c === "string" && COLA_VALIDA.test(c))', b)   # el nombre de cola se muestra sólo si es válido
        # Cada resultado navega: ir() (hash), irA() (hash y deja la tarjeta a la vista) o irModulo() (cockpit.jump).
        self.assertEqual(sorted(set(re.findall(r"ir: \(\) => (\w+)\(", b))), ["ir", "irA", "irModulo"])
        abrir = tramo(self.codigo, "function abrirBuscador() {")
        self.assertIn('el("span", { class: "buscador-texto" }, x.texto)', abrir)       # como nodo de texto
        self.assertIn("const elegir = x => { cerrarBuscador(); x.ir(); };", abrir)
        # Con el texto real que trae un aviso hostil, delPanel() deja fuera la clave y el nombre suelto.
        hostil = 'token: sk-AbC123xyz9QQ <img src=x onerror=alert(1)> lo pidió Diego\nsegunda línea'
        visto = CargaVsCapacidadTests.del_panel(hostil.split("\n")[0])
        for fuera in ("sk-AbC123xyz9QQ", "Diego", "segunda"):
            self.assertNotIn(fuera, visto)
        self.assertEqual(CargaVsCapacidadTests.del_panel("cola84 · Claude (Diego) revisa"), "cola84 · Claude (Diego) revisa")

    def test_pulso_badges_y_cuentas(self):
        pc = tramo(self.js, "function pintarConsola() {")
        # «Viva» es una sesión cola* de tmux: lo mismo que barra.js (`viva = sesiones.length > 0`) y que «Ahora».
        self.assertIn("const vivas = d ? d.sesiones.length : 0, pendientes = av ? av.pendientes.length : 0;", pc)
        self.assertIn("const viva = sesiones.length > 0;", self.barra)
        self.assertIn('sesiones: tmux.split("\\n").filter(x => /^cola[\\w-]+$/.test(x))', self.js)
        self.assertIn('pulso.classList.toggle("viva", vivas > 0);', pc)
        self.assertEqual(len(re.findall(r'svg\("circle"', self.consola)), 1)
        self.assertEqual(len(re.findall(r"\[\d+, \d+\]", re.search(r"PUNTOS = (\[\[.*?\]\])", self.js).group(1))), 5)
        # Las tres cuentas, con su etiqueta con paréntesis (cuentas.toml) y uso(), sin un nombre suelto escrito.
        self.assertIn('const CUENTAS_BARRA = ["claude_diego", "claude_cami", "codex"];', self.js)
        self.assertIn('el("strong", {}, cuenta(id)), el("span", {}, uso(id))', self.consola)
        self.assertIn("function uso(id) { try { const x = d.uso.cuentas_interactivo[id].limites; return `5 h ${x.ventana_5h.usado_pct} % · semanal ${x.semanal.usado_pct} %`; } catch (e) { return \"sin datos\"; } }", self.js)
        self.assertIsNone(re.search(r"(?<!\()\b(?:Diego|Cami|Camila)\b", self.consola))
        # Ambos badges están en las pestañas superiores.
        self.assertIn('badge($(\'#pestanas [data-p="avisos"] .riel-badge\'), pendientes', pc)

    def test_84ar1_el_refresco_sigue_fuera_de_ahora(self):
        # Hallazgo 1 de la revisión: sin #barra, barra.js no arranca su refresco (su bloque exige el nodo) y la página sólo
        # releía en «Ahora». Se prueba sobre la forma real: el arranque de barra.js, el HTML y los temporizadores del JS.
        arranque = self.barra[self.barra.index("const REFRESCO_MS"):]
        self.assertIn('document.getElementById("barra")', self.barra)                      # el refresco de barra.js depende de #barra
        self.assertIn("setInterval(() => { if (!document.hidden) refrescar(); }, REFRESCO_MS);", arranque)
        self.assertNotIn('id="barra"', self.html)                                           # por eso no lo da ya
        timers = re.findall(r"^setInterval\((.*?), (\d+(?: \* \d+)*)\);$", self.js, re.M)
        lecturas = [(c, ms) for c, ms in timers if "leer()" in c]
        dentro = [x for x in lecturas if 'panel === "ahora"' in x[0]]
        fuera = [x for x in lecturas if 'panel !== "ahora"' in x[0]]
        self.assertEqual(len(dentro), 1)
        self.assertEqual(len(fuera), 1, "fuera de «Ahora» tiene que haber una lectura programada")
        self.assertIn("!document.hidden", fuera[0][0])
        self.assertLessEqual(eval(fuera[0][1], {"__builtins__": {}}), 5 * 60 * 1000)    # a lo sumo el REFRESCO_MS de barra.js
        self.assertEqual(eval(re.search(r"const REFRESCO_MS = ([\d *]+);", self.barra).group(1), {"__builtins__": {}}), 5 * 60 * 1000)
        # Cambiar de panel no limpia ni reemplaza ese temporizador: ningún clearInterval en la página.
        self.assertNotIn("clearInterval", self.codigo)

    # ---------------- Encargo 95: tooltip de las colas ----------------
    # Fixtures reales de encargos-nube/95-fixtures/ (manifiestos e historial de las colas 84, 88, 91n, 93n y 9092n). Esa
    # carpeta no trae vivo/: los dos vivo de abajo están armados acá con la forma del real fixtures/vivo-cola85-85b.json.
    FIX95 = PI.parent / "encargos-nube" / "95-fixtures"
    VIVO_91N = {"nombre": "cola91n", "estado": "detenida", "etapas": ["91n"], "etapa": "91n", "fase": "rev1", "cuenta": "Codex",
                "escrito": "2026-10-25T17:06:40-03:00"}
    VIVO_88 = {"nombre": "cola88", "estado": "terminada", "etapas": ["88a", "88c", "88b"], "etapa": "88b", "fase": "rev2",
               "cuenta": "Codex", "escrito": "2026-10-25T16:59:20-03:00", "fin": "2026-10-25T16:59:20-03:00"}
    HOSTIL = ('nombre = "cola99x"\n'
              'resumen = "<img src=x onerror=alert(1)> clave sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWx __proto__ ' + "relleno " * 40 + '"\n'
              'motivo = "<script>alert(2)</script> token=sk-ant-oculto-123"\n\n[[etapa]]\nid = "99x"\nresumen = "__proto__ <b>negrita</b>"\n')
    ESTADOS_95 = {"pausada_sin_timer": "pausada, sin reanudación programada", "detenida": "detenida", "en_candado": "espera autorización",
                  "caida": "caída", "sin_autorizacion": "sin autorización", "ilegible": "no se pudo leer", "pausada_por_usuario": "pausada por el usuario",
                  "retenida_por_despacho": "retenida por el despacho"}

    @staticmethod
    def linea_95(js, inicio):
        """La línea de `js` que empieza con `inicio` (las definiciones de una línea que necesita la prueba con node)."""
        i = js.index(inicio)
        return js[i:js.index("\n", i)]

    @classmethod
    def datos_95(cls, vivos=()):
        rs = [ResumenYUsoTests.resumenes(leer(p)) for p in sorted(cls.FIX95.glob("cola-*.toml"))]
        h = [json.loads(x) for x in leer(cls.FIX95 / "historial.jsonl").splitlines() if x.strip()]
        return {"resumenes": [r for r in rs if r], "vivos": list(vivos), "h": h,
                "nombres": {"claude_diego": "Claude (Diego)", "claude_cami": "Claude (Cami)", "codex": "Codex"}}

    @staticmethod
    def fecha_chile(iso):
        from zoneinfo import ZoneInfo
        try:
            return datetime.fromisoformat(iso).astimezone(ZoneInfo("America/Santiago")).strftime("%d-%m %H:%M")
        except (TypeError, ValueError):
            return None

    @classmethod
    def lineas_cola(cls, d, nombre):
        """Espejo de lineasCola() (en la Pi no hay motor de JS; la prueba con node de abajo corre el JS real)."""
        ry, dp = ResumenYUsoTests, CargaVsCapacidadTests.del_panel
        c = next((x for x in d["resumenes"] if x["cola"] == nombre), None)
        v = next((x for x in d["vivos"] if x.get("nombre") == nombre), None)
        if not isinstance(nombre, str) or (not c and not v):
            return [["Cola", "sin datos de esta cola"]]
        ids = {str(x) for x in ([e["id"] for e in c["etapas"]] if c else []) + (v.get("etapas") if v and isinstance(v.get("etapas"), list) else [])}
        filas = sorted((x for x in d["h"] if str(x.get("encargo")) in ids), key=lambda x: datetime.fromisoformat(x["inicio"]).timestamp())
        ultima = filas[-1] if filas else None
        actual = str(v["etapa"]) if v and v.get("etapa") not in (None, "") else str(ultima["encargo"]) if ultima else None
        etapa = next((e for e in c["etapas"] if e["id"] == actual), None) if c and actual else None
        de_etapa = ry.resumen_etapa(etapa, {}) if etapa else "sin resumen"
        que = ry.resumen_cola(d["resumenes"], nombre) + (f" · etapa {dp(actual)}: {de_etapa}" if de_etapa != "sin resumen" else "")
        cuenta = lambda i: dp(d["nombres"][i]) if i in d["nombres"] else dp(i) if i else "sin datos"
        if v:
            partes = [dp(x) for x in (v.get("etapa"), v.get("fase")) if x not in (None, "")]
            partes += [x for x in (dp(v["cuenta"]) if v.get("cuenta") else None, cls.ESTADOS_95.get(v.get("estado")) or dp(str(v.get("estado") or "").replace("_", " ")),
                                   cls.fecha_chile(v.get("fin")) or cls.fecha_chile(v.get("escrito"))) if x]
            fase = " · ".join(partes)
        else:
            fase = " · ".join(x for x in (dp(ultima["encargo"]), dp(ultima["fase"]), cuenta(ultima["cuenta"]), cls.fecha_chile(ultima["inicio"])) if x) if ultima else "sin fases todavía"
        revs = [x for x in filas if x.get("rol") == "rev" and isinstance(x.get("veredicto"), str) and x["veredicto"]]
        r = revs[-1] if revs else None
        minutos = f"{str(round(r['min'] * 10) / 10).replace('.', ',')} min" if r else ""
        revision = " · ".join([dp(r["encargo"]), dp(r["fase"]), cuenta(r["cuenta"]), minutos, r["veredicto"] if r["veredicto"] in ("DESPLEGABLE", "NO DESPLEGABLE") else dp(r["veredicto"])]) if r else "sin revisión todavía"
        corte = lambda t: t if len(t) <= 180 else t[:179].rstrip() + "…"
        return [[e, corte(t)] for e, t in (["Qué hace", que], ["Última fase", fase or "sin datos"], ["Última revisión", revision])]

    def test_95_c1_las_tres_lineas_con_los_fixtures_reales(self):
        d = self.datos_95([self.VIVO_91N])
        l91 = dict(self.lineas_cola(d, "cola91n"))
        self.assertTrue(l91["Qué hace"].startswith("Codex revisa pi/temblores.py, sus unidades y su suite; los arreglos vuelven a la nube."), l91)
        self.assertIn("etapa 91n: Revisión de Codex del 91", l91["Qué hace"])
        self.assertEqual(l91["Última fase"], "91n · rev1 · Codex · detenida · 25-10 17:06")
        self.assertEqual(l91["Última revisión"], "91n · rev1 · Codex · 5,7 min · NO DESPLEGABLE")
        self.assertTrue(dict(self.lineas_cola(d, "cola93n"))["Última revisión"].endswith("· DESPLEGABLE"))
        self.assertEqual(dict(self.lineas_cola(d, "cola9092n"))["Última revisión"], "9092n · rev1 · Codex · 8,3 min · DESPLEGABLE")
        self.assertEqual(dict(self.lineas_cola(d, "cola84"))["Última revisión"], "84b · rev1 · Codex · 4,1 min · DESPLEGABLE")

    def test_95_c1_trampa_88_la_ultima_es_por_inicio_no_por_nombre(self):
        # 88c (16:13–16:20) corrió antes que 88b (16:28–16:52): la última es 88b, con vivo y sin él.
        for vivos in ([], [self.VIVO_88]):
            l = dict(self.lineas_cola(self.datos_95(vivos), "cola88"))
            self.assertEqual(l["Última revisión"], "88b · rev2 · Codex · 6,3 min · DESPLEGABLE", vivos)
            self.assertTrue(l["Última fase"].startswith("88b · rev2 · Codex"), l)
            self.assertNotIn("88c", l["Última revisión"] + l["Última fase"])
            self.assertNotIn("88a", l["Última revisión"] + l["Última fase"])
        self.assertEqual(dict(self.lineas_cola(self.datos_95(), "cola88"))["Última fase"], "88b · rev2 · Codex · 25-10 16:52")

    def test_95_c5_desconocida_y_sin_revision(self):
        d = self.datos_95()
        for nombre in ("cola00z", "__proto__", "constructor", "", None):
            self.assertEqual(self.lineas_cola(d, nombre), [["Cola", "sin datos de esta cola"]], nombre)
        sin_rev = dict(self.lineas_cola(dict(d, h=[x for x in d["h"] if x["encargo"] == "93n" and x["rol"] != "rev"]), "cola93n"))
        self.assertEqual(sin_rev["Última revisión"], "sin revisión todavía")
        # La tarjeta ya acepta una línea más (la ampliación del primer hallazgo grave).
        self.assertIn("function lineasCola(nombre, extra = []) {", self.js)
        self.assertIn('[["Qué hace", que], ["Última fase", fase || "sin datos"], ["Última revisión", revision], ...extra]', self.js)
        self.assertIn('const COLA_SIN_DATOS = "sin datos de esta cola"', self.js)
        self.assertIn('"sin revisión todavía"', self.js)

    def test_95_c4_datos_hostiles_no_llegan_como_html(self):
        d = self.datos_95([dict(self.VIVO_91N, nombre="cola99x", etapas=["99x"], etapa="99x", cuenta="__proto__", estado="<i>x</i>")])
        d["resumenes"].append(ResumenYUsoTests.resumenes(self.HOSTIL))
        d["h"].append({"encargo": "99x", "fase": "rev1", "rol": "rev", "cuenta": "__proto__", "min": 1.25, "inicio": "2026-10-25T18:00:00-03:00", "veredicto": "<b>SÍ</b>"})
        lineas = self.lineas_cola(d, "cola99x")
        texto = " ".join(t for _, t in lineas)
        self.assertNotIn("sk-ant", texto)
        self.assertIn("«oculto»", texto)
        self.assertTrue(all(len(t) <= 180 for _, t in lineas), lineas)
        # Todo sale por el() (texto), nunca como HTML; las claves se buscan sin prototipo.
        bloque = self.js[self.js.index("const COLA_SIN_DATOS"):self.js.index("function cuentaFase(")] + tramo(self.js, "function mostrarCola(nombre) {") + tramo(self.js, "function activarMenciones(raiz = document) {")
        for prohibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            self.assertNotIn(prohibido, bloque)
        self.assertIn("const cuentaCola = id => { const n = propio(d.nombres, id);", self.js)
        self.assertIn('const propio = (o, k) => (o && typeof o === "object" && typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined);', self.js)

    def test_95_c2_cada_lugar_del_inventario_usa_mencionCola(self):
        red = leer(PAGINAS["encargos"] / "red.js")
        lugares = ['el("h2", {}, "Cola viva: ", mencionCola(v.cola))',                          # Ahora · cola deducida
                   'mencionCola(x.n), ": espera ", ...x.a.flatMap((a, j) => [j ? ", " : null, mencionCola(a)])',   # colas en espera
                   'el("h2", {}, mencionCola(m.cola), ` · ${titulo}`)',                          # tarjeta de cola
                   'scope: "col" }, mencionCola(c.cola), el("span", { class: "carga-nota" }',   # matriz · cabeceras
                   'proy.flatMap((p, i) => [i ? ", " : null, mencionCola(p.cola)])',             # matriz · leyenda
                   'el("li", {}, el("strong", {}, mencionCola(x.cola)), " ",',                  # colas_fuera
                   'x.colas_que_caben.flatMap((c, i) => [i ? ", " : null, mencionCola(c)])',     # capacidad por vencer
                   'autorizadas.flatMap((c, i) => [i ? ", " : null, mencionCola(c)])',           # despacho · autorizadas
                   'r.cola === "Despacho" ? "Despacho" : mencionCola(r.cola), ": "']              # resultado de la acción
        for x in lugares:
            self.assertIn(x, self.js)
        self.assertIn('el("i", { class: "red-punto", "aria-hidden": "true" }), mencionCola(v.nombre), texto);', red)   # Flow · franja Ahora
        # Ningún nombre de cola queda pintado suelto: ni interpolado ni con delPanel() directo. La clave de caché de la red
        # (`${v.nombre}:${v.estado}:…`) no se pinta: se descuenta una vez.
        self.assertEqual(red.count("colasVivas().map(v => `${v.nombre}:${v.estado}:"), 1)
        for codigo in (self.js, red.replace("colasVivas().map(v => `${v.nombre}:${v.estado}:", "")):
            self.assertEqual(re.findall(r"\$\{(?:v|m|x|c|p|r)\.(?:cola|n|nombre)\}", codigo), [])
            self.assertEqual(re.findall(r"delPanel\((?:v|m|x|c|p|r)\.cola\)|colas_que_caben\.map\(delPanel\)|autorizadas\.join\(", codigo), [])
        self.assertNotIn("const cola = typeof v.nombre", red)
        # Una sola función arma la mención.
        self.assertEqual(len(re.findall(r'"mencion-cola"', self.js + red)), 1)
        self.assertIn('return el("span", { class: "mencion-cola", "data-cola": typeof nombre === "string" ? nombre.slice(0, 64) : "" }, texto);', self.js)

    def test_95_c3_accesible_igual_que_el_glosario(self):
        bloque = tramo(self.js, "function activarMenciones(raiz = document) {")
        for linea in ('blanco.setAttribute("aria-describedby", "term-tooltip");',
                      'if (!blanco.matches("button, a, input, select, textarea, [tabindex]")) blanco.setAttribute("tabindex", "0");',
                      'blanco.addEventListener("pointerenter", ver);', 'blanco.addEventListener("focus", ver);', 'blanco.addEventListener("blur", ocultarTooltip);',
                      'if (ev.pointerType !== "mouse") espera = setTimeout(ver, 450);', 'const blanco = n.closest("button, a") || n;'):
            self.assertIn(linea, bloque)
        self.assertIn("    activarMenciones(raiz);\n}", self.js)                      # el mismo componente: activarGlosario lo llama
        self.assertIn('const t = $("#term-tooltip")', tramo(self.js, "function mostrarCola(nombre) {"))
        self.assertIn("activarGlosario(S.franja);", leer(PAGINAS["encargos"] / "red.js"))
        self.assertIn("activarGlosario(p);", tramo(self.js, "function ahora() {"))
        self.assertIn(".term-tooltip .linea-cola { display: block;", self.css)
        self.assertIn(".mencion-cola {", self.css)
        self.assertEqual(self.html.count('id="term-tooltip"'), 1)                     # un solo tooltip en la página

    @unittest.skipUnless(shutil.which("node"), "sin node (en la Pi no hay): cubren el espejo y la fuente")
    def test_95_el_js_real_con_node(self):
        js = self.js
        tramos = [js[js.index('"use strict";'):js.index("// Encargo 22, parte B")],
                  js[js.index("const ESTADOS_FUERA"):js.index("const AYUDA_CARGA")],
                  *(self.linea_95(js, x) for x in ("function conEtiqueta(t) {", "const delPanel = x =>", "const propio = (o, k) =>", "const porInicio = fs =>", "const COLA_VALIDA ="))]
        datos = {"tomls": [leer(p) for p in sorted(self.FIX95.glob("cola-*.toml"))] + [self.HOSTIL], "historial": leer(self.FIX95 / "historial.jsonl"),
                 "cuentas": leer(PI.parent / "botv3" / "cuentas.toml") if (PI.parent / "botv3" / "cuentas.toml").exists() else "",
                 "vivos": [self.VIVO_91N, dict(self.VIVO_91N, nombre="cola99x", etapas=["99x"], etapa="99x", cuenta="__proto__")]}
        programa = ("const el = (tag, attrs = {}, ...h) => ({ tag, attrs, hijos: h.flat().filter(x => x != null && x !== false).map(x => typeof x === 'object' ? x : String(x)) });\n"
                    + "\n".join(tramos) + "\nconst D = " + json.dumps(datos) + ";\n"
                    "d = { resumenes: D.tomls.map(resumenes).filter(Boolean), vivos: D.vivos, h: historia(D.historial), nombres: nombres(D.cuentas) };\n"
                    "const sin = { ...d, vivos: [] };\n"
                    "const r = { c91: lineasCola('cola91n'), c93: lineasCola('cola93n'), c99: lineasCola('cola99x'), proto: lineasCola('__proto__'),\n"
                    "  nada: lineasCola('cola00z'), m: mencionCola('cola91n'), mala: mencionCola('<img src=x>'), extra: lineasCola('cola91n', [['Hallazgo', 'x']]) };\n"
                    "d = sin; r.c88 = lineasCola('cola88');\n"
                    "console.log(JSON.stringify(r));\n")
        p = subprocess.run(["node", "-e", programa], capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        r = json.loads(p.stdout)
        c91 = dict(r["c91"])
        self.assertEqual(c91["Última fase"], "91n · rev1 · Codex · detenida · 25-10 17:06")
        self.assertEqual(c91["Última revisión"], "91n · rev1 · Codex · 5,7 min · NO DESPLEGABLE")
        self.assertTrue(c91["Qué hace"].startswith("Codex revisa pi/temblores.py"))
        self.assertTrue(dict(r["c93"])["Última revisión"].endswith("DESPLEGABLE"))
        self.assertEqual(dict(r["c88"])["Última revisión"], "88b · rev2 · Codex · 6,3 min · DESPLEGABLE")
        self.assertEqual(dict(r["c88"])["Última fase"], "88b · rev2 · Codex · 25-10 16:52")
        self.assertEqual(r["proto"], [["Cola", "sin datos de esta cola"]])
        self.assertEqual(r["nada"], [["Cola", "sin datos de esta cola"]])
        hostil = " ".join(t for _, t in r["c99"])
        self.assertNotIn("sk-ant", hostil)
        self.assertIn("«oculto»", hostil)
        self.assertTrue(all(len(t) <= 180 for _, t in r["c99"]))
        self.assertEqual(len(r["extra"]), 4)
        self.assertEqual(r["m"], {"tag": "span", "attrs": {"class": "mencion-cola", "data-cola": "cola91n"}, "hijos": ["cola91n"]})
        # Un nombre que no es de cola pasa por delPanel() y queda como TEXTO (un solo hijo string), nunca como nodo armado.
        self.assertEqual(len(r["mala"]["hijos"]), 1)
        self.assertIsInstance(r["mala"]["hijos"][0], str)
        # El espejo de Python dice lo mismo que el JS real.
        d = self.datos_95([self.VIVO_91N])
        self.assertEqual(self.lineas_cola(d, "cola91n"), r["c91"])
        self.assertEqual(self.lineas_cola(self.datos_95(), "cola88"), r["c88"])


class FlujoEncargosTests(unittest.TestCase):
    """Encargo 84b: 🕸️ Flujo, la red de encargos con luces (red.js). Pruebas estáticas y espejos en Python: en la Pi no
    hay motor de JS. Leen el historial real sólo para leer (una foto en memoria) y no escriben en /opt/nodo/datos. Lo
    visual (nodos encimados, recortes a 1280/800/375 px, Foco desde «Ahora», filtro del Historial) es C6: lo verifica
    Claude (Diego) en el PC con el cockpit falso."""

    HISTORIAL = PI.parent / "encargos" / "historial.jsonl"
    # Las rutas que lee la página con cockpit.file (todas pasan por archivo()), tal como las dejó la 84a.
    ARCHIVOS_ANTES = {"CUENTAS", "USO", "`${DIR}/${f}`", "`${DIR}/COLA-ESTADO.md`", "`${DIR}/historial.jsonl`", "x", "PROYECTOS_JSON"}       # PROYECTOS_JSON: encargo 99

    @classmethod
    def setUpClass(cls):
        import importlib.util
        CargaVsCapacidadTests.setUpClass()                 # el espejo de delPanel()
        cls.html = leer(PAGINAS["encargos"] / "index.html")
        cls.js = leer(PAGINAS["encargos"] / "encargos.js")
        cls.css = leer(PAGINAS["encargos"] / "encargos.css")
        cls.red = leer(PAGINAS["encargos"] / "red.js")
        cls.codigo = tokens_js(cls.red, strings=True)
        spec = importlib.util.spec_from_file_location("balance_84b", PI.parent / "encargos" / "balance.py")
        cls.balance = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.balance)
        # Una foto del historial real, sólo hasta el último salto de línea: cola-run.py puede estar escribiendo.
        with open(cls.HISTORIAL, "rb") as fh:
            crudo = fh.read()
        cls.lineas = crudo[:crudo.rfind(b"\n") + 1].decode("utf-8").splitlines()

    @staticmethod
    def texto_id(v):
        """Espejo de textoId() de red.js."""
        if isinstance(v, bool):
            return ""
        if isinstance(v, str) or (isinstance(v, (int, float)) and math.isfinite(v)):
            s = v if isinstance(v, str) else (str(int(v)) if float(v).is_integer() else str(v))
            return s if s.strip() else ""
        return ""

    @staticmethod
    def num(v):
        """Espejo de num() de red.js."""
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 else 0.0

    def filas_de_la_pagina(self):
        """Lo que la página tiene en d.h (historia(): JSON.parse por línea no vacía) filtrado como filasDelPeriodo() con «Todo»."""
        h = [json.loads(x) for x in self.lineas if x]
        return [x for x in h if isinstance(x, dict) and self.texto_id(x.get("encargo")) and self.texto_id(x.get("fase"))]

    def retrabajo_js(self):
        (fuente,) = re.findall(r"^    const RETRABAJO = /(.+)/;$", self.red, re.M)
        return fuente

    def test_c1_retrabajo_es_la_regla_de_balance(self):
        fuente = self.retrabajo_js()
        # La misma expresión, anclada en los dos extremos (balance.py la usa con fullmatch).
        self.assertEqual(fuente, "^" + self.balance.RETRABAJO.pattern.rstrip("$") + "$")
        js = re.compile(fuente.replace("$", r"\Z"))
        self.assertIn("const esRetrabajo = x => RETRABAJO.test(textoId(x.fase));", self.red)
        filas = self.filas_de_la_pagina()
        self.assertGreaterEqual(len(filas), 351)
        self.assertGreaterEqual(len({str(x["encargo"]) for x in filas}), 83)
        de_la_pagina = {i for i, x in enumerate(filas) if js.match(self.texto_id(x["fase"]))}
        de_balance = {i for i, x in enumerate(filas) if self.balance.RETRABAJO.fullmatch(self.balance._texto(x["fase"]))}
        self.assertEqual(de_la_pagina, de_balance)
        self.assertTrue(de_balance)
        # Las fases de borde también: fullmatch, no búsqueda.
        for fase, si in (("fix", True), ("fix12", True), ("rev2", True), ("rev10", True), ("plan2", True), ("revplan2", True),
                         ("rev1", False), ("rev", False), ("autor", False), ("xfix1", False), ("fix1x", False), ("rev01", True), ("plan21", False)):
            self.assertEqual(bool(js.match(fase)), si, fase)
            self.assertEqual(bool(self.balance.RETRABAJO.fullmatch(fase)), si, fase)

    def test_c1_el_porcentaje_de_minutos_es_el_de_balance(self):
        import tempfile
        # balance.py sobre la misma foto (en un temporal: nada se escribe junto al historial real).
        with tempfile.TemporaryDirectory() as tmp:
            foto = Path(tmp) / "historial.jsonl"
            foto.write_text("\n".join(self.lineas) + "\n", encoding="utf-8")
            filas_b, saltadas = self.balance.leer_historial(foto)
        m = self.balance.medir(filas_b)
        pct_balance = self.balance._pct_num(m["min_ret"], m["min"])
        # La página: la misma suma que pintarCabeza() (y la etiqueta del arco), con Math.round de JS.
        self.assertIn("tot = reales.reduce((n, x) => n + num(x.min), 0), re = reales.filter(esRetrabajo).reduce((n, x) => n + num(x.min), 0);", self.red)
        self.assertIn('kpi(`${tot > 0 ? Math.round(100 * re / tot) : "–"} %`, "Rework rate", "Rework rate")', self.red)
        self.assertIn('const num = v => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : 0);', self.red)
        self.assertIn('periodo: "todo"', self.red)                                   # al abrir, la página muestra «Todo»
        filas = self.filas_de_la_pagina()
        js = re.compile(self.retrabajo_js().replace("$", r"\Z"))
        tot = sum(self.num(x.get("min")) for x in filas)
        ret = sum(self.num(x.get("min")) for x in filas if js.match(self.texto_id(x["fase"])))
        self.assertEqual(saltadas, 0)
        self.assertEqual(len(filas), len(filas_b))
        self.assertAlmostEqual(tot, m["min"], places=6)
        self.assertAlmostEqual(ret, m["min_ret"], places=6)
        self.assertEqual(math.floor(100 * ret / tot + 0.5), pct_balance)
        self.assertTrue(30 <= pct_balance <= 60, pct_balance)                      # el orden de magnitud de la maqueta (46 %)

    def test_c2_sin_lectura_ni_ejecucion_nueva(self):
        # red.js no toca cockpit: ni spawn, ni archivos, ni sudo, ni red.
        for x in ("cockpit", "spawn", "sudo", "fetch(", "XMLHttpRequest", "WebSocket", "eval(", "new Function", "import("):
            self.assertNotIn(x, self.codigo, x)
        # encargos.js: los mismos spawn y las mismas rutas leídas que dejó la 84a.
        self.assertEqual(set(re.findall(r"cockpit\.spawn\((\[[^\]]*\]|\w+\([^)]*\))", self.js)), ConsolaEncargosTests.SPAWN_ANTES | ConsolaEncargosTests.SPAWN_99)
        self.assertEqual(len(re.findall(r"cockpit\.spawn\(", self.js)), 10)
        self.assertEqual(re.findall(r"cockpit\.file\(([^)]*)\)", self.js), ["p"])           # sólo dentro de archivo()
        self.assertIn("async function archivo(p, json) { try { const x = await cockpit.file(p).read();", self.js)
        self.assertEqual(set(re.findall(r"(?<![\w.])archivo\((`[^`]*`|\w+)(?:, true)?\)", self.js)), self.ARCHIVOS_ANTES)
        # La red usa lo que ya leyó leer(): se le pasa `d` entero.
        self.assertIn('function flujo() { redEncargos.pintar($("[data-panel=flujo]"), d, alcanceFlujo(), hashFlujo); }', self.js)
        # La prueba mide: una lectura nueva cambia el conjunto.
        malo = self.js + "\nawait archivo(`${DIR}/vivo/otra.json`);"
        self.assertNotEqual(set(re.findall(r"(?<![\w.])archivo\((`[^`]*`|\w+)(?:, true)?\)", malo)), self.ARCHIVOS_ANTES)

    def test_c3_csp_y_accesibilidad(self):
        for texto in (self.red, self.html):
            self.assertIsNone(re.search(r"https?://", texto))
            self.assertIsNone(re.search(r"""setAttribute\(\s*["']style""", texto))
            self.assertNotIn("<style", texto)
        for x in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "cssText"):
            self.assertNotIn(x, self.codigo, x)
        self.assertNotIn("url(", self.css)
        # Lo que pide el plan de luces, en red.js.
        for x in ("prefers-reduced-motion", "document.hidden", "IntersectionObserver", "requestAnimationFrame", "visibilitychange"):
            self.assertIn(x, self.red, x)
        (tope,) = re.findall(r"^    const TOPE_LUCES = (\d+);", self.red, re.M)
        self.assertLessEqual(int(tope), 120)
        self.assertIn("tope = Math.max(0, Math.floor(TOPE_LUCES * S.escala) - (S.lucesPipeline || 0))", self.red)
        self.assertIn("S.lucesPipeline = tramos ? Math.min(24, tramos.hechas.length + (tramos.corriendo ? 1 : 0) + tramos.pronosticadas.length) : 0", self.red)
        self.assertIn("candidatas.slice(0, tope)", self.red)
        self.assertIn("const CUADRO_MS = 8;", self.red)
        self.assertIn("if (performance.now() - t0 > CUADRO_MS && S.escala > 0.2) {", self.red)
        # Con movimiento reducido o con las luces apagadas, flechas fijas y ninguna luz.
        self.assertIn('flechas = quieto() || !S.luces;', self.red)
        self.assertIn('if (flechas) e.trazo.setAttribute("marker-end", "url(#red-flecha)");', self.red)
        self.assertIn("if (!S.luces || quieto()) { soltarPulso(); return; }", self.red)
        # ⏸ Luces: lo único que se guarda, siempre dentro de try/catch.
        self.assertEqual(re.findall(r"(?:local|session)Storage\.\w+\([^)]*\)", self.red),
                         ['localStorage.setItem(LUCES_GUARDADAS, S.luces ? "si" : "no")', "localStorage.getItem(LUCES_GUARDADAS)"])
        self.assertIn('function guardarLuces() { try { localStorage.setItem(', self.red)
        self.assertIn('function leerLuces() { try { return localStorage.getItem(', self.red)
        # El pulso de la barra late con las luces de «En vivo»; sin animación vuelve al CSS (que respeta el movimiento reducido).
        self.assertIn('pulso.classList.toggle("sincro", !!S.enVivo); if (S.enVivo) pulso.style.setProperty("--latido",', self.red)
        self.assertIn(".consola-pulso.viva.sincro circle { animation: none; opacity: calc(.35 + .65 * var(--latido, 0)); }", self.css)
        # Un solo nombre global, que no choca con encargos.js, y se carga antes que ella.
        self.assertEqual(declarados_arriba(self.red), {"redEncargos"})
        self.assertNotIn("redEncargos", declarados_arriba(self.js))
        self.assertIn('<script src="red.js"></script><script src="modelo.js"></script><script src="proyectos.js"></script><script src="encargos.js"></script>', self.html)       # 99: el modelo y la vista de Projects van entre red.js y encargos.js

    def etiqueta_modelo(self, ident):
        """Espejo de etiquetaModelo() con el mapa MODELOS extraído de red.js (sin el paso final de delPanel)."""
        mapa = dict(re.findall(r'"([^"]+)": "([^"]+)"', re.search(r"^    const MODELOS = \{(.*)\};$", self.red, re.M).group(1)))
        crudo = ident.strip().lower() if isinstance(ident, str) else ""
        if not crudo:
            return "sin datos"
        if crudo in mapa:
            return mapa[crudo]
        limpio = re.sub(r"(\d+)-(\d+)", r"\1.\2", re.sub(r"^(?:claude|anthropic|openai)-", "", crudo))
        partes = [p.upper() if re.fullmatch(r"gpt|api|ia", p) else (p[:1].upper() + p[1:] if i == 0 else p)
                  for i, p in enumerate(x for x in re.split(r"[-_\s]+", limpio) if x)]
        return " ".join(partes) or "sin datos"

    def test_c4_etiquetas_de_modelo(self):
        f = tramo(self.codigo, "function etiquetaModelo(id) {")
        self.assertIn("Object.prototype.hasOwnProperty.call(MODELOS, crudo)", f)
        self.assertIn('.replace(/^(?:claude|anthropic|openai)-/, "").replace(/(\\d+)-(\\d+)/g, "$1.$2")', self.red)
        self.assertIn('return partes.length ? delPanel(partes.join(" ")) : "sin datos";', self.red)
        self.assertEqual(self.red.count("function etiquetaModelo("), 1)                 # una sola función
        filas = [json.loads(x) for x in self.lineas if x]
        modelos = {x.get(k) for x in filas for k in ("modelo", "modelo_real")}
        self.assertGreaterEqual(len(modelos - {None}), 5)
        for m in modelos:
            e = self.etiqueta_modelo(m)
            with self.subTest(m):
                for malo in ("5 5", "4 5", "-"):
                    self.assertNotIn(malo, e)
                self.assertNotEqual(e, m)
        self.assertLessEqual({self.etiqueta_modelo(m) for m in modelos}, {"Opus 5.5", "Sonnet 5.5", "Haiku 4.5", "Terra", "GPT Reserve", "sin datos"})
        # Un id nuevo cae en la regla general; uno vacío o que no es texto, en «sin datos».
        for crudo, esperado in (("claude-opus-6-1", "Opus 6.1"), ("gpt-5.7-mega", "GPT 5.7 mega"), ("claude-haiku-5-0-beta", "Haiku 5.0 beta"),
                                ("", "sin datos"), (None, "sin datos"), (55, "sin datos")):
            self.assertEqual(self.etiqueta_modelo(crudo), esperado, crudo)
        # El esfuerzo se agrega sólo si es uno de los conocidos.
        self.assertIn("return ESFUERZOS.includes(x.esfuerzo) ? `${m} · ${x.esfuerzo}` : m;", self.red)

    def test_entradas_hostiles_van_como_texto_seguro(self):
        # Todo dato de un agente que se muestra pasa por delPanel() (lista blanca y regla de nombres) o es una cola válida.
        for linea in ("recientes.has(enc) ? nodo(3, enc, `Encargo ${delPanel(enc)}`)",
                      'const fase = `${delPanel(v.etapa)} · ${delPanel(v.fase)} · ${delPanel(String(v.estado ?? "").replace(/_/g, " "))}`;',
                      'el("i", { class: "red-punto", "aria-hidden": "true" }), mencionCola(v.nombre), texto);',
                      'delPanel(bonito(x.naturaleza))', 'delPanel(textoId(x.fase).replace(/\\d+$/, ""))',
                      'return typeof n === "string" && n !== "sin datos" ? delPanel(n) : id ? delPanel(id) : "sin datos"; }'):
            self.assertIn(linea, self.red)
        # Los tooltips son <title> con textContent; no hay HTML armado con texto.
        self.assertEqual(len(re.findall(r'svg\("title", \{\}\)', self.red)), 2)
        asignados = re.findall(r"\.textContent = ([^;]*);", self.red)
        self.assertEqual(len(asignados), 7)
        for a in asignados:                                    # etiquetas ya armadas (con delPanel) o textos fijos, nunca un campo crudo
            self.assertIsNone(re.search(r"\b[vxd]\.\w+", a), a)
        # Los mapas que se indexan con un dato no caen en el prototipo.
        self.assertIn("Object.prototype.hasOwnProperty.call(BRILLO, x.esfuerzo)", self.red)
        self.assertIn("Object.prototype.hasOwnProperty.call(ROLES_RED, x.rol)", self.red)
        # Los vivo/*.json rotos o vacíos (1 byte) los descarta leerVivos() de barra.js; la red, además, sólo toma objetos.
        self.assertIn("return leidos.filter(v => v && v.nombre && v.estado);", leer(COMUN / "barra.js"))
        self.assertIn('return d.vivos.filter(v => colaActiva(v, d.sesiones));', self.red)
        # Una fila del historial que no es un objeto no rompe la firma ni la red.
        self.assertIn('h.length ? (h.at(-1) || {}).inicio : ""', self.red)
        self.assertIn('const valida = x => !!x && typeof x === "object" && !!textoId(x.encargo) && !!textoId(x.fase);', self.red)
        # El espejo de delPanel() con un id hostil: deja fuera la clave y el nombre suelto.
        visto = CargaVsCapacidadTests.del_panel("84z token: sk-AbC123xyz9QQ de Diego")
        for fuera in ("sk-AbC123xyz9QQ", "Diego"):
            self.assertNotIn(fuera, visto)

    def test_historial_reutiliza_las_filas_y_pagina_de_a_50(self):
        # Una sola fila de Historial: hist() y la red llaman a filaHistorial(); no queda la copia de antes.
        self.assertEqual(self.js.count("function filaHistorial(x) {"), 1)
        self.assertNotIn("const fila = x =>", self.js)
        self.assertIn("el(\"tr\", {}, ...CABEZAS_HISTORIAL.map(t => cabeza(t, dib)))), el(\"tbody\", {}, fs.map(filaHistorial))", self.js)
        self.assertIn('CABEZAS_HISTORIAL.map(t => cabeza(t, () => { S.pagina = 0; pintarHistorial(); }))', self.red)
        self.assertIn("trozo.map(filaHistorial)", self.red)
        self.assertIn('ordenar(red ? red.filas.filter(', self.red)
        self.assertIn('orden.clave, orden.desc)', self.red)
        self.assertIn("const POR = 50,", self.red)
        self.assertIn("trozo = filas.slice(desde, desde + POR)", self.red)
        # El filtro dice qué filtra y tiene su ✕; la fase en curso (sin minutos) no entra.
        self.assertIn("`filtrado por ${foco.titulo}`", self.red)
        self.assertIn('"aria-label": "Quitar el filtro", onclick: () => enfocar(null) }, "✕")', self.red)
        self.assertIn("red.filas.filter((x, i) => !x._vivo &&", self.red)

    def test_portada_modos_y_ahora(self):
        self.assertEqual(riel_encargos(self.html)[0], ("flujo", "Flow"))
        self.assertIn('<section data-panel="flujo"></section><section data-panel="ahora" hidden></section>', self.html)
        # «Ahora» relee cada minuto también en Flujo (su modo En vivo); el resto, cada 5 min como antes.
        self.assertIn('setInterval(() => { if (!document.hidden && (panel === "ahora" || panel === "flujo")) leer()', self.js)
        self.assertIn('setInterval(() => { if (!document.hidden && panel !== "ahora" && panel !== "flujo") leer()', self.js)
        # Las colas vivas son las de «viva» (sesión de tmux con su vivo); sin ellas, el texto lo dice.
        self.assertIn('"sin colas en curso"', self.red)
        self.assertIn('if (S.modo === "vivo" && vivas.size) return { lista: red.enlaces.filter(e => cruza(e.filas, vivas))', self.red)
        # La pastilla lleva el estimado sólo si vivo trae un número; tocarla entra en Foco sobre su camino.
        self.assertIn("typeof r === \"number\" && Number.isFinite(r) && r >= 0 ? ` · ~${es(r, 0)} min` : \"\"", self.red)
        self.assertIn('onclick: () => elegirEncargo(v.etapa, v.nombre)', self.red)
        # Selectores pedidos, aviso de tokens y KPI.
        for x in ('["min", "Minutos"]', '["usd", "USD"]', '["tokens", "Tokens"]', '["pct", "Puntos de % semanal"]', '["7", "7 días"]', '["30", "30 días"]', '["todo", "Todo"]',
                  '["vivo", "En vivo"]', '["ambiente", "Ambiente"]', "compararlos entre proveedores es orientativo", '"Steps"', '"Tasks"', '"Task"', '"Rework rate"'):
            self.assertIn(x, self.red, x)
        # D3 queda preparado, no implementado: el estado tiene un reloj y las filas lo respetan.
        self.assertIn("reloj: null", self.red)
        self.assertIn("(S.reloj == null || (t != null && t <= S.reloj))", self.red)
        # D1 A: el arco del retrabajo, ámbar, desde «Retrabajo» hasta un rol.
        self.assertIn('vuelta = { id: "vuelta", a: capas[4].get("Retrabajo"), b: destino,', self.red)
        self.assertIn(".red .retrabajo { --c: var(--ojo); }", self.css)
        # Altura desde la capa más poblada, con al menos 8 px entre nodos.
        self.assertIn("SEPARACION = 8", self.red)
        self.assertIn("m.size * ALTO_NODO[c] + Math.max(0, m.size - 1) * SEPARACION", self.red)

    def test_la_altura_deja_8_px_entre_nodos_con_el_historial_real(self):
        """Espejo de ubicar() con las capas que salen del historial real («Todo», 10 recientes): ningún par de vecinos
        de una capa queda a menos de 8 px y las columnas no se tocan a 1160 px (el ancho mínimo del lienzo)."""
        g = lambda name: int(re.search(rf"\b{name} = (\d+)", self.red).group(1))
        anchos = [int(x) for x in re.search(r"const ANCHO_NODO = \[([\d, ]+)\]", self.red).group(1).split(", ")]
        altos = [int(x) for x in re.search(r"ALTO_NODO = \[([\d, ]+)\]", self.red).group(1).split(", ")]
        sep, my, mx, arco = g("SEPARACION"), g("MARGEN_Y"), g("MARGEN_X"), g("ARCO")
        filas = self.filas_de_la_pagina()
        rol = lambda x: (x.get("naturaleza"), x.get("rol") or re.sub(r"\d+$", "", str(x["fase"])))
        enc = {}
        for x in filas:
            enc.setdefault(str(x["encargo"]), []).append(x)
        n_encargos = min(len(enc), g("RECIENTES")) + (1 if len(enc) > g("RECIENTES") else 0)
        cuentas = {x.get("cuenta") for x in filas}
        modelos = {(self.etiqueta_modelo(x.get("modelo") or x.get("modelo_real")), x.get("esfuerzo") if x.get("esfuerzo") in ("low", "medium", "high", "xhigh") else None) for x in filas}
        cuantos = [len(cuentas), len(modelos), len({rol(x) for x in filas}), n_encargos, 5]
        util = max(c * altos[i] + max(0, c - 1) * sep for i, c in enumerate(cuantos))
        alto = my * 2 + max(util, 300) + arco
        for i, c in enumerate(cuantos):
            if c > 1:
                salto = (alto - arco - my * 2 - altos[i]) / (c - 1)
                self.assertGreaterEqual(salto - altos[i], sep - 1e-9, (i, c))
        paso = (1160 - mx * 2) / 4
        for i in range(4):
            self.assertGreater(paso - anchos[i] / 2 - anchos[i + 1] / 2, 20, i)
        self.assertGreaterEqual(mx, max(anchos) / 2)

    def test_85b_tramos_con_fixture_vivo_y_archivo_de_un_byte(self):
        """C2 85b: ejecuta la función real del JS con la forma real del vivo y del historial."""
        fixture = PI / "fixtures" / "vivo-cola85-85b.json"
        vivo = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(vivo["nombre"], "cola85")
        self.assertIn("function fasesTramos(dato, encargo) {", self.red)
        self.assertIn("Array.isArray(vivo.fases_restantes)", self.red)
        self.assertIn("x.prob >= 0 && x.prob <= 1", self.red)
        node = next((x for x in ("node", "/home/dcifu004/.local/bin/node", str(Path.home() / ".local/bin/node")) if shutil.which(x) or Path(x).exists()), None)
        self.assertIsNotNone(node, "la prueba C2 necesita ejecutar el JS real con node")
        # No se reconstruye h: son las filas completas que historia() entrega al JS desde historial.jsonl.
        h = self.filas_de_la_pagina()
        dato = {"h": h, "vivos": [vivo], "sesiones": [vivo["nombre"]]}
        script = "const vm=require('vm'), fs=require('fs'); const src=fs.readFileSync(process.argv[1],'utf8')+'\\n;globalThis.fn=redEncargos.fasesTramos;'; const c={console}; vm.runInNewContext(src,c); process.stdout.write(JSON.stringify(c.fn(JSON.parse(process.argv[2]),process.argv[3])));"
        salida = subprocess.run([node, "-e", script, str(PI / "cockpit-encargos/red.js"), json.dumps(dato), "85b"], capture_output=True, text=True, check=True)
        tramos_js = json.loads(salida.stdout)
        self.assertEqual(len(tramos_js["hechas"]), sum(x["encargo"] == "85b" for x in h))
        self.assertEqual(tramos_js["corriendo"]["fase"], "autor")
        self.assertEqual(len(tramos_js["pronosticadas"]), len(vivo["fases_restantes"]) - 1)
        self.assertTrue(tramos_js["publica"])
        salida_85a = subprocess.run([node, "-e", script, str(PI / "cockpit-encargos/red.js"), json.dumps(dato), "85a"], capture_output=True, text=True, check=True)
        tramos_85a = json.loads(salida_85a.stdout)
        self.assertEqual(len(tramos_85a["hechas"]), sum(x["encargo"] == "85a" for x in h))
        self.assertIsNone(tramos_85a["corriendo"])
        self.assertEqual(tramos_85a["pronosticadas"], [])
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vacio = Path(tmp) / "vivo-un-byte.json"
            vacio.write_bytes(b" ")
            self.assertEqual(vacio.stat().st_size, 1)
            # Es la misma operación de leerVivos(): JSON.parse falla sobre el byte y el elemento se descarta.
            with self.assertRaises(json.JSONDecodeError):
                json.loads(vacio.read_text(encoding="utf-8"))
            sin_vivo = {"h": h, "vivos": [], "sesiones": []}
            salida_vacio = subprocess.run([node, "-e", script, str(PI / "cockpit-encargos/red.js"), json.dumps(sin_vivo), "85b"], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(salida_vacio.stdout)["pronosticadas"], [])

    def test_85b_estados_reales_visibles_con_y_sin_sesion(self):
        """Los estados publicados por cola-run.py no desaparecen de Ahora por el punto exacto de la fase."""
        fixture = json.loads((PI / "fixtures" / "vivo-cola85-85b.json").read_text(encoding="utf-8"))
        node = next((x for x in ("node", "/home/dcifu004/.local/bin/node", str(Path.home() / ".local/bin/node")) if shutil.which(x) or Path(x).exists()), None)
        self.assertIsNotNone(node)
        script = "const vm=require('vm'), fs=require('fs'); const src=fs.readFileSync(process.argv[1],'utf8')+'\\n;globalThis.fn=redEncargos.fasesTramos;'; const c={console}; vm.runInNewContext(src,c); process.stdout.write(JSON.stringify(c.fn(JSON.parse(process.argv[2]),process.argv[3])));"
        con_sesion = ("partiendo", "esperando autorización", "esperando", "línea base de pruebas", "corriendo", "esperando_cuota", "pruebas finales", "desplegando")
        for estado in con_sesion:
            v = copy.deepcopy(fixture); v["estado"] = estado
            salida = subprocess.run([node, "-e", script, str(PI / "cockpit-encargos/red.js"), json.dumps({"h": [], "vivos": [v], "sesiones": [v["nombre"]]}), "85b"], capture_output=True, text=True, check=True)
            self.assertIsNotNone(json.loads(salida.stdout)["corriendo"], estado)
        for nombre in ("pausada", "pausada_por_usuario", "retenida_por_despacho", "en_consulta"):
            real = json.loads((PI / "fixtures" / "vivo" / ("pausada.json" if nombre != "en_consulta" else "esperando.json")).read_text(encoding="utf-8"))
            real["estado"] = nombre
            salida = subprocess.run([node, "-e", script, str(PI / "cockpit-encargos/red.js"), json.dumps({"h": [], "vivos": [real], "sesiones": []}), "22"], capture_output=True, text=True, check=True)
            self.assertIsNotNone(json.loads(salida.stdout)["corriendo"], nombre)

    def test_85b_alcance_hash_y_selector(self):
        for texto in ('["curso", "e", "n", "c"].forEach(k => q.delete(k));', 'if (tipo === "encargo") q.set("e", valor);', 'if (tipo === "naturaleza") q.set("n", valor);', 'if (tipo === "cuenta") q.set("c", valor);', 'return `#/flujo${q.size ? `?${q.toString().replace(/%3A/gi, ":")}` : ""}`;'):
            self.assertIn(texto, self.js)
        for texto in ('["todo", "Todo"]', '["curso", `En curso (${colasActivas().length})`]', '["encargo", "Encargo…"]', '["naturaleza", "Naturaleza"]', '["cuenta", "Cuenta"]', 'onclick: () => elegirEncargo(v.etapa, v.nombre)'):
            self.assertIn(texto, self.red)
        self.assertIn("S.alcance = alcance; S.escribirHash = escribirHash;", self.red)


# ---- Encargo 99: 📋 Projects. Un espejo en Python de modelo.js (asignación, columna deducida, semanas de Chile,
# throughput y cycle time) y el modelo real con node cuando lo hay (en la Pi no hay: esas pruebas se saltan). ----
FIX_PROYECTOS = PI / "fixtures" / "proyectos"
COLUMNAS_99 = ["Idea", "Ready", "In progress", "Review", "Done"]
RE_ID_99 = re.compile(r"^[0-9]{2}[a-z0-9]{0,8}$")


def semana_chile(t):
    """Lunes (AAAA-MM-DD) de la semana de t en hora de Chile, como semana() de modelo.js."""
    from zoneinfo import ZoneInfo
    d = t.astimezone(ZoneInfo("America/Santiago")).date()
    return (d - timedelta(days=d.weekday())).isoformat()


def modelo_99(proyectos, historial, indice, vivos):
    """Espejo de modeloProyectos.armar(): sólo lo que fijan C2 y C3 (proyecto, columna, fin, cycle y throughput)."""
    ps = [p for p in proyectos["proyectos"] if isinstance(p, dict)]
    abiertos = {}
    for p in ps:
        for k, v in (p.get("abiertos") or {}).items():
            abiertos.setdefault(k, v)
    fases = {}
    for f in historial:
        fases.setdefault(str(f["encargo"]), []).append(f)
    for xs in fases.values():
        xs.sort(key=lambda f: datetime.fromisoformat(f["inicio"]))
    cola = {}
    for v in vivos:
        if re.match(r"^(corriendo|pausada.*)$", str(v.get("estado", ""))) and RE_ID_99.match(str(v.get("etapa", ""))):
            col = "Review" if v["fase"].startswith("rev") else "In progress" if re.match(r"^(autor|fix|plan)", v["fase"]) else None
            if col:
                cola[str(v["etapa"])] = col
    ix = {x["id"]: x for x in indice}
    tarjetas = {}
    for id_ in dict.fromkeys([*ix, *fases, *abiertos, *cola]):
        num = re.match(r"\d+", id_)[0]
        p = next((p for p in ps if id_ in p.get("encargos", []) or id_ in (p.get("abiertos") or {})), None) \
            or next((p for p in ps if num in p.get("encargos", []) or num in (p.get("abiertos") or {})), None)
        fs = fases.get(id_, [])
        revs = [f for f in fs if f.get("veredicto")]
        t = {"proyecto": p["id"] if p else "otros", "fin": None, "cycle": None}
        desp = revs and revs[-1]["veredicto"] == "DESPLEGABLE"
        if id_ in abiertos:
            t["columna"] = abiertos[id_]
        elif id_ in cola:
            t["columna"] = cola[id_]
        elif desp:
            t["columna"] = "Done"
        elif not fs and id_ in ix and not ix[id_].get("resultados"):
            t["columna"] = "Ready"
        elif fs or (id_ in ix and ix[id_].get("resultados")):
            t["columna"] = "Done"
        else:
            t["columna"] = "Idea"
        if t["columna"] == "Done" and desp:
            ini = datetime.fromisoformat(fs[0]["inicio"])
            t["fin"] = datetime.fromisoformat(revs[-1]["inicio"]) + timedelta(minutes=revs[-1]["min"] or 0)
            t["cycle"] = (t["fin"] - ini).total_seconds() / 60
        tarjetas[id_] = t
    semanas = {}
    for t in tarjetas.values():
        if t["fin"]:
            s = semana_chile(t["fin"])
            semanas[s] = semanas.get(s, 0) + 1
    return tarjetas, dict(sorted(semanas.items()))


def historial_99(ruta):
    return [json.loads(x) for x in leer(ruta).splitlines() if x.strip()]


class ProyectosTests(unittest.TestCase):
    """Encargo 99: la pestaña Projects. Lo visual (anchos, temas, consola sin errores, el enlace a Flow) lo verifica
    Claude (Diego) en el PC con el cockpit falso (encargos-nube/99-capturar.js)."""

    @classmethod
    def setUpClass(cls):
        carpeta = PAGINAS["encargos"]
        cls.html, cls.js, cls.css = leer(carpeta / "index.html"), leer(carpeta / "encargos.js"), leer(carpeta / "encargos.css")
        cls.modelo, cls.vista = leer(carpeta / "modelo.js"), leer(carpeta / "proyectos.js")
        cls.proyectos = json.loads(leer(PI.parent / "encargos" / "proyectos.json"))
        cls.indice = json.loads(leer(FIX_PROYECTOS / "indice-98.json"))
        cls.h98 = historial_99(FIX_PROYECTOS / "historial-98.jsonl")
        cls.node = shutil.which("node")

    def node_modelo(self, entrada):
        programa = ("const M = require(process.argv[1]); const e = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                    "const r = M.armar(e); const t = {}; for (const x of r.tarjetas) t[x.id] = { proyecto: x.proyecto, columna: x.columna, fin: x.fin ?? null, cycle: x.cycle ?? null };\n"
                    "console.log(JSON.stringify({ semanas: r.semanas, porSemana: r.global.porSemana, tarjetas: t, errores: r.errores, cobertura: r.cobertura, conteo: r.conteo }));")
        p = subprocess.run([self.node, "-e", programa, str(PAGINAS["encargos"] / "modelo.js")], input=json.dumps(entrada), capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_99_js_balanceado_un_nombre_y_sin_ejecutar_nada(self):
        for nombre, codigo, global_ in (("modelo.js", self.modelo, "modeloProyectos"), ("proyectos.js", self.vista, "vistaProyectos")):
            with self.subTest(nombre):
                self.assertTrue(tokens_js(codigo).strip())                         # ValueError si algo queda sin cerrar
                self.assertEqual(declarados_arriba(codigo), {global_})
                limpio = tokens_js(codigo, strings=True)
                for x in ("cockpit.", "spawn", "sudo", "fetch(", "XMLHttpRequest", "WebSocket", "eval(", "new Function", "import(", "innerHTML", "outerHTML",
                          "insertAdjacentHTML", "document.write", "cssText", "localStorage", "location.hash ="):
                    self.assertNotIn(x, limpio, x)
        self.assertNotIn("document", tokens_js(self.modelo, strings=True))          # el modelo no toca el DOM
        # Se cargan antes que encargos.js, que es la última (ComunTests) y la que los usa.
        self.assertIn('<script src="red.js"></script><script src="modelo.js"></script><script src="proyectos.js"></script><script src="encargos.js"></script>', self.html)

    def test_99_tokens_en_un_solo_lugar_y_colores_propios_con_tema(self):
        comunes = set(TOKENS["claro"])
        self.assertEqual(variables_css(self.css) & comunes, set())
        propias = {v for v in variables_css(self.css) if v.startswith("--cfd-")}
        self.assertEqual(propias, {"--cfd-prog", "--cfd-rev", "--cfd-done"})
        reglas = reglas_css(self.css)
        oscuras = [d for m, s, d in reglas if s.startswith(':root[data-theme="dark"] .proy-cfd')]
        self.assertEqual(len(oscuras), 1)
        self.assertEqual(set(oscuras[0]), propias)                                 # cada color propio tiene su variante oscura
        self.assertNotIn("url(", self.css)
        # Los anchos van por CSSOM (--w), nunca por un atributo style.
        self.assertIn('nodo.style.setProperty("--w"', self.vista)

    def test_99_la_pestana_va_en_la_url(self):
        self.assertIn('data-p="projects" data-term="Projects">Projects <span class="riel-badge" hidden></span></button>', self.html)
        self.assertEqual([p for p, _ in pestanas_encargos(self.html)][:3], ["flujo", "ahora", "projects"])   # entre Runs y Timeline
        (fuente,) = re.findall(r"^const RUTA = /(.+)/;$", self.js, re.M)
        ruta = re.compile(fuente.replace("$", r"\Z"))
        for h in ("#/projects", "#/projects?p=voz", "#/projects?v=conflicts", "#/projects?v=board&p=voz", "#/projects?o=fecha:desc&v=flow", "#/historial?e=84a", "#/flujo?e=86"):
            self.assertTrue(ruta.match(h), h)
        for h in ("#/projects?x=1", "#/projects/", "#/projects?p=voz#x", "#/Projects"):
            self.assertIsNone(ruta.match(h), h)
        # p y v son datos de la URL: sólo valen si son una vista conocida o un proyecto de proyectos.json.
        self.assertIn('const VISTAS = ["board", "carriles", "conflicts", "flow"];', self.vista)
        self.assertIn('return { v: VISTAS.includes(v) ? v : "board", p: p && ctx.m.proyectos.some(x => x.id === p) ? p : null };', self.vista)
        # El badge es «en Review / tope», y el nombre de la pestaña lo descuenta.
        self.assertIn("badgeReview($('#pestanas [data-p=\"projects\"] .riel-badge'), d && d.proy);", self.js)
        self.assertIn('replace(/\\s+\\d+(?:\\/\\d+)?$/, "")', self.js)

    def test_99_proyectos_json_ausente_roto_o_enorme_no_rompe_la_pagina(self):
        bloque = tramo(self.js, "async function leerProyectos() {")
        self.assertIn('if (t == null) return { error: "Projects: no se pudo leer encargos/proyectos.json.", indice };', bloque)
        self.assertIn("if (t.length > MAX_PROYECTOS) return", bloque)
        self.assertIn("try { return { datos: JSON.parse(t), indice }; } catch (e) { return { error:", bloque)
        self.assertIn("MAX_PROYECTOS = 1024 * 1024", self.js)
        armar = tramo(self.js, "function armarProyectos(proy) {")
        self.assertIn("try { d.proy = modeloProyectos.armar(", armar)
        self.assertIn("catch (e) { d.proyError =", armar)
        self.assertIn('if (!ctx.m) { nodo.replaceChildren(el("p", { class: "aviso ojo" }, ctx.error || "Projects: sin datos de proyectos.")); return; }', self.vista)
        # El modelo copia proyectos.json a estructuras sin prototipo y descarta tipos raros.
        self.assertIn("Object.create(null)", self.modelo)
        self.assertIn("Object.prototype.hasOwnProperty.call(o, k)", self.modelo)

    @unittest.skipUnless(shutil.which("node"), "sin node (en la Pi no hay motor de JS)")
    def test_99_modelo_real_con_datos_hostiles(self):
        hostil = {"__proto__": {"columnas": 1}, "tope_wip": {"Review": "3"}, "aging_dias": -4,
                  "proyectos": [{"id": "voz", "nombre": "<img src=x onerror=alert(1)>", "resultado": 7, "encargos": ["16", 3, "<b>"],
                                 "abiertos": {"16": "Hecho", "17": "Review", "__proto__": "Done"}, "ideas": "x", "bloqueo": {"x": 1}},
                                {"id": "constructor", "nombre": "x", "encargos": "16"}, {"id": "voz"}, 5, None],
                  "archivos_compartidos": {"__proto__": ["16"], "a.py": ["16", {}]}}
        r = self.node_modelo({"proyectos": hostil, "historial": self.h98, "indice": self.indice, "vivos": [], "ahora": 1761424110000})
        self.assertEqual(r["tarjetas"]["17"]["columna"], "Review")
        self.assertEqual(r["tarjetas"]["16"]["proyecto"], "voz")
        self.assertTrue(any("Hecho" in e for e in r["errores"]))
        self.assertTrue(any("repetido" in e for e in r["errores"]))
        r = self.node_modelo({"proyectos": [1, 2], "historial": "no", "indice": None, "vivos": {"x": 1}, "ahora": 0})
        self.assertEqual(r["errores"], ["proyectos.json no es un objeto"])

    def test_99_c2_las_cifras_del_98_con_el_espejo(self):
        tarjetas, semanas = modelo_99(self.proyectos, self.h98, self.indice, [])
        self.assertEqual(list(semanas.values()), [7, 22, 19, 28])
        self.assertEqual(list(semanas), ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"])
        self.assertAlmostEqual(tarjetas["19"]["cycle"], 7.75, places=2)            # 18:20:35 → 18:25:02 + 3,3 min
        self.assertAlmostEqual(tarjetas["84a"]["cycle"], 30.733, places=2)          # 11:57:29 → 12:24:19 + 3,9 min
        self.assertEqual(round(tarjetas["19"]["cycle"], 1), 7.8)
        self.assertEqual(round(tarjetas["84a"]["cycle"], 1), 30.7)
        # Con el historial de la rama (encargos/historial.jsonl, una copia más corta: 387 de las 397 fases), lo mismo
        # salvo la última semana, que todavía no tiene las 10 fases del final.
        rama = historial_99(PI.parent / "encargos" / "historial.jsonl")
        t2, s2 = modelo_99(self.proyectos, rama, self.indice, [])
        self.assertEqual(rama, self.h98[:len(rama)])
        self.assertEqual(list(s2.values())[:3], [7, 22, 19])
        self.assertEqual((round(t2["19"]["cycle"], 1), round(t2["84a"]["cycle"], 1)), (7.8, 30.7))

    @unittest.skipUnless(shutil.which("node"), "sin node (en la Pi no hay motor de JS)")
    def test_99_c2_el_modelo_de_la_pagina_da_lo_mismo_que_el_espejo(self):
        for historial in (self.h98, historial_99(PI.parent / "encargos" / "historial.jsonl")):
            ahora = max(datetime.fromisoformat(f["inicio"]).timestamp() + (f["min"] or 0) * 60 for f in historial) * 1000
            r = self.node_modelo({"proyectos": self.proyectos, "historial": historial, "indice": self.indice, "vivos": [], "ahora": ahora})
            tarjetas, semanas = modelo_99(self.proyectos, historial, self.indice, [])
            self.assertEqual(dict(zip(r["semanas"], r["porSemana"])), semanas)
            self.assertEqual({k: (v["proyecto"], v["columna"]) for k, v in r["tarjetas"].items()}, {k: (v["proyecto"], v["columna"]) for k, v in tarjetas.items()})
            for k in ("19", "84a"):
                self.assertAlmostEqual(r["tarjetas"][k]["cycle"] * 1440, tarjetas[k]["cycle"], places=6)
            self.assertEqual(r["cobertura"]["perdidos"], [])
            self.assertEqual(r["cobertura"]["indice"], 124)
        self.assertEqual(r["errores"], [])

    def test_99_c3_columna_deducida_con_colas_vivas(self):
        vivos = [{"nombre": "cola86x", "estado": "corriendo", "etapa": "86", "fase": "rev2"},
                 {"nombre": "cola77x", "estado": "pausada", "etapa": "77", "fase": "autor"},
                 {"nombre": "cola83x", "estado": "corriendo", "etapa": "83", "fase": "rev1"},       # 83 está en «abiertos» (Ready)
                 {"nombre": "cola61x", "estado": "terminada", "etapa": "61", "fase": "rev1"}]      # terminada: no cuenta
        self.assertNotIn("86", json.dumps([p.get("abiertos") for p in self.proyectos["proyectos"]]))
        sin, _ = modelo_99(self.proyectos, self.h98, self.indice, [])
        con, _ = modelo_99(self.proyectos, self.h98, self.indice, vivos)
        self.assertEqual((sin["86"]["columna"], sin["77"]["columna"], sin["83"]["columna"], sin["61"]["columna"]), ("Done", "Done", "Ready", "Done"))
        self.assertEqual((con["86"]["columna"], con["77"]["columna"], con["83"]["columna"], con["61"]["columna"]), ("Review", "In progress", "Ready", "Done"))
        # Y en el JS real, el mismo orden: abiertos, cola viva, DESPLEGABLE, escrito sin fases.
        orden = [self.modelo.index(x) for x in ("if (ab) { t.columna = ab.abiertos.get(id);", "else if (viva) { t.columna = viva.columna;",
                                                 'else if (ultimaRev && ultimaRev.veredicto === "DESPLEGABLE") { t.columna = "Done";',
                                                 'else if (!fs.length && x && !t.resultados) { t.columna = "Ready";')]
        self.assertEqual(orden, sorted(orden))
        self.assertIn("const VIVA = /^(corriendo|pausada.*)$/;", self.modelo)
        if shutil.which("node"):
            r = self.node_modelo({"proyectos": self.proyectos, "historial": self.h98, "indice": self.indice, "vivos": vivos, "ahora": 1761424110000})
            self.assertEqual([r["tarjetas"][k]["columna"] for k in ("86", "77", "83", "61")], ["Review", "In progress", "Ready", "Done"])

    def test_99_c4_proyectos_check(self):
        check = PI.parent / "encargos" / "proyectos_check.py"
        indice = ["--indice", str(FIX_PROYECTOS / "indice-98.json")]
        bien = subprocess.run([sys.executable, str(check), *indice], capture_output=True, text=True, timeout=60)
        self.assertEqual(bien.returncode, 0, bien.stdout)
        for nombre, error in (("id-repetido", "está en dos proyectos"), ("columna-inventada", "que no es una columna"), ("json-invalido", "JSON inválido")):
            with self.subTest(nombre):
                r = subprocess.run([sys.executable, str(check), str(FIX_PROYECTOS / f"{nombre}.json"), *indice], capture_output=True, text=True, timeout=60)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn(error, r.stdout)
        # Sólo lee: ni open(..., "w"), ni write_text, ni subprocess.
        fuente = leer(check)
        for x in ('"w"', "'w'", "write_text", "subprocess", "os.remove", "unlink"):
            self.assertNotIn(x, fuente, x)

    def test_99_enlaces_a_flow_y_traces(self):
        self.assertIn('el("a", { href: `#/flujo?e=${e}` }, `Ver en Flow · encargo ${t.id} ›`)', self.vista)
        self.assertIn('el("a", { href: `#/historial?e=${e}` }, "Ver en Traces ›")', self.vista)
        self.assertIn("const e = encodeURIComponent(t.id);", self.vista)
        # Traces preselecciona el encargo del hash sólo si es una de sus opciones.
        self.assertIn('if (e0 && [...a.options].some(x => x.value === e0)) a.value = e0;', self.js)

    def test_99_los_datos_van_como_texto(self):
        # Títulos de los .md: por la limpieza de la página (delPanel); nombres de proyecto: como texto, recortados.
        self.assertIn("const titulo = t => ctx.limpiar(t.titulo);", self.vista)
        self.assertIn("limpiar: delPanel", self.js)
        self.assertIn('const texto = x => (typeof x === "string" ? x.replace(/\\s+/g, " ").trim().slice(0, MAX_TEXTO) : "");', self.modelo)
        self.assertEqual(re.findall(r"\bstyle:\s*\S+", tokens_js(self.vista)), [])
        glosario = leer(PAGINAS["encargos"] / "glosario.js")
        definidos = dict(re.findall(r'^    "([^"]+)": "([^"]+)"[,]?$', glosario, re.M))
        for t in ("Projects", "Board", "WIP limit", "Cycle time", "Lead time", "Throughput", "Aging", "Cumulative flow", "Now/Next/Later", "Forecast", "Conflicts"):
            self.assertIn(t, definidos)
        usados = set(re.findall(r'"data-term": "([^"]+)"', self.vista))
        self.assertLessEqual(usados, set(definidos))


def cr_claves(fuente):
    """CLAVES_CELDA de cola-run.py, leída de su texto."""
    return re.findall(r'"(\w+)"', re.search(r"^CLAVES_CELDA = \(([^)]*)\)", fuente, re.M).group(1))


if __name__ == "__main__":
    unittest.main()
