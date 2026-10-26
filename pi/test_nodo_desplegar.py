#!/usr/bin/env python3
"""Pruebas de `nodo-desplegar enviar` (encargo 39b): spool, vault y Telegram falsos, sin root.

El pedido se deja con el `_dejar()` real y lo atiende el `Escucha.procesar_pedidos()` real. Lo
único falso es `urllib.request.urlopen`: recibe la petición ya armada (URL, cabeceras y cuerpo
multipart) y la desarma con el parser de `email`, que no comparte código con el que la armó.
Un corte de luz no se puede dar de verdad sin root: `Disco` es el modelo de lo que dejaría.
Nada escribe en /var/spool, /var/lib, /etc/nodo ni /opt/nodo/datos: `setUp` lo comprueba."""
import contextlib
import email
import email.policy
import hashlib
import html
import importlib.util
import io
import json
import os
import pwd
import secrets
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from unittest import mock

PI = Path(__file__).resolve().parent
SCRIPT = PI / "nodo-desplegar.py"
PROYECTO = PI.parent
# Con la forma de un token de bot, para que una fuga se vea igual que una real. No es de nadie.
TOKEN = "7123456789:AAFalsoFalsoFalso_falso-FALSO0123456789"
CHAT = "424242"
YO = pwd.getpwuid(os.getuid()).pw_name


class TelegramFalso:
    """Lo que `urlopen` recibiría. Guarda cada llamada desarmada y contesta como Telegram."""

    def __init__(self):
        self.llamadas: list[dict] = []
        self.falla = None      # callable(req) -> excepción a lanzar
        self.testigo = None    # callable(): la llamada ya llegó a Telegram

    def __call__(self, req, timeout=None):
        tipo = req.get_header("Content-type")
        ll = {"url": req.full_url, "metodo": req.full_url.rsplit("/", 1)[1], "tipo": tipo,
              "timeout": timeout, "crudo": req.data, "campos": {}, "archivos": {}}
        if tipo.startswith("multipart/form-data"):
            m = email.message_from_bytes(b"Content-Type: " + tipo.encode() + b"\r\n\r\n" + req.data,
                                         policy=email.policy.HTTP)
            for parte in m.iter_parts():
                nombre = parte.get_param("name", header="content-disposition")
                if parte.get_filename() is None:
                    ll["campos"][nombre] = parte.get_payload(decode=True).decode()
                else:
                    ll["archivos"][nombre] = {"nombre": parte.get_filename(),
                                              "tipo": parte.get_content_type(),
                                              "bytes": parte.get_payload(decode=True)}
        else:
            ll["campos"] = json.loads(req.data)
        self.llamadas.append(ll)
        if self.testigo:
            self.testigo()
        if self.falla:
            raise self.falla(req)
        return io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 77}}).encode())


class Disco:
    """Lo que un corte de luz puede dejar de UNA carpeta. Es un modelo, y es el pesimista: de un
    archivo sólo está en el disco lo que tenía en su último `fsync`; de la carpeta, los nombres
    que tenía en el suyo. Todo lo demás puede haber llegado o no. Hace falta porque el /tmp de
    las pruebas es tmpfs, donde `fsync` no hace nada: sin esto, ninguna prueba distingue un
    `guardar()` que confirma de uno que no.

    Envuelve `os.fsync`, `os.fdatasync`, `os.sync`, `os.replace`, `os.rename` y los dos `open`
    (por si alguien trunca un archivo en su lugar); los reales corren igual. Cada inodo que ve
    queda abierto hasta `soltar()`: así su número no se reutiliza y un archivo nuevo no hereda
    lo confirmado de uno viejo."""

    def __init__(self, raiz: Path, testigo):
        self.raiz, self.testigo = raiz, testigo
        st = os.stat(raiz)
        self.carpeta = (st.st_dev, st.st_ino)
        self.abiertos: dict[tuple, int] = {}
        self.reales = {n: getattr(os, n) for n in ("fsync", "fdatasync", "sync", "replace", "rename", "open")}
        self.reales["io.open"] = io.open
        # Lo que ya había al armarlo se da por escrito.
        self.firme = self.nombres()                                   # nombre → inodo, al último fsync de la carpeta
        self.datos = {i: self.leer(i) for i in self.firme.values()}   # inodo → bytes, a su último fsync
        self.sueltas: list[dict] = []                                 # lo que la caché mostró desde entonces
        self.parches = [mock.patch.object(os, n, f) for n, f in (
            ("fsync", self.confirma("fsync")), ("fdatasync", self.confirma("fdatasync")), ("sync", self.todo),
            ("replace", self.mueve("replace")), ("rename", self.mueve("rename")), ("open", self.abre_os))]
        self.parches += [mock.patch.object(io, "open", self.abre), mock.patch("builtins.open", self.abre)]
        for p in self.parches:
            p.start()

    def soltar(self) -> None:
        for p in self.parches:
            p.stop()
        for fd in self.abiertos.values():
            os.close(fd)
        self.parches, self.abiertos = [], {}

    def nombres(self) -> dict:
        vistos = {}
        with os.scandir(self.raiz) as carpeta:
            for e in carpeta:
                if e.is_file(follow_symlinks=False):
                    st = e.stat(follow_symlinks=False)
                    vistos[e.name] = self.fijar((st.st_dev, st.st_ino), e.path)
        return vistos

    def fijar(self, inodo: tuple, ruta: str) -> tuple:
        if inodo not in self.abiertos:
            self.abiertos[inodo] = self.reales["open"](ruta, os.O_RDONLY)
        return inodo

    def leer(self, inodo: tuple) -> bytes:
        fd = self.abiertos[inodo]
        return os.pread(fd, os.fstat(fd).st_size, 0)

    def cache(self) -> dict:
        return {n: self.leer(i) for n, i in self.nombres().items()}

    def confirma(self, cual: str):
        def envuelta(fd):
            self.reales[cual](fd)
            st = os.fstat(fd)
            inodo = (st.st_dev, st.st_ino)
            if inodo == self.carpeta:
                self.firme, self.sueltas = self.nombres(), []
            elif stat.S_ISREG(st.st_mode):
                # Lo que el archivo tiene AHORA: lo que siga en el búfer de Python no cuenta.
                self.datos[inodo] = self.leer(self.fijar(inodo, f"/proc/self/fd/{fd}"))
            self.testigo(cual)
        return envuelta

    def todo(self) -> None:
        self.reales["sync"]()
        self.firme, self.sueltas = self.nombres(), []
        self.datos = {i: self.leer(i) for i in self.abiertos}
        self.testigo("sync")

    def mueve(self, cual: str):
        def envuelta(src, dst, **k):
            self.reales[cual](src, dst, **k)
            if Path(dst).parent == self.raiz:
                self.sueltas.append(self.cache())
                self.testigo(cual)
        return envuelta

    def truncado(self, ruta, trunca: bool) -> None:
        # Un archivo vaciado en su lugar es, hasta su fsync, una versión más que puede quedar.
        if trunca and isinstance(ruta, (str, os.PathLike)) and Path(ruta).parent == self.raiz:
            self.sueltas.append(self.cache())
            self.testigo("open")

    def abre(self, ruta, mode="r", *a, **k):
        fh = self.reales["io.open"](ruta, mode, *a, **k)
        self.truncado(ruta, "w" in mode)
        return fh

    def abre_os(self, ruta, flags, *a, **k):
        fd = self.reales["open"](ruta, flags, *a, **k)
        self.truncado(ruta, bool(flags & os.O_TRUNC) and k.get("dir_fd") is None)
        return fd

    def posibles(self) -> list[dict]:
        """Cómo puede amanecer la carpeta si la luz se corta en este instante."""
        estados = [
            {n: self.datos.get(i, b"") for n, i in self.firme.items()},        # no llegó nada que no pasara por fsync
            {n: self.datos.get(i, b"") for n, i in self.nombres().items()},    # llegaron los nombres y no los datos
            *self.sueltas,                                                     # el kernel bajó solo una versión intermedia
            self.cache()]                                                      # o llegó todo
        return [e for i, e in enumerate(estados) if e not in estados[:i]]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="nodo-desplegar-")))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        spec = importlib.util.spec_from_file_location("nodo_desplegar", SCRIPT)
        self.nd = nd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nd)
        nd.SPOOL = self.tmp / "spool"
        nd.PEDIDOS, nd.RESULTADOS = nd.SPOOL / "pedidos", nd.SPOOL / "resultados"
        nd.ESTADO = self.tmp / "estado"
        nd.CATALOGO = self.tmp / "etc" / "catalogo.toml"
        nd.ENV = self.tmp / "etc" / "avisos.env"
        nd.RESPALDOS = self.tmp / "respaldos"
        nd.VAULT = self.tmp / "srv" / "vault_personal"
        nd.MONTAJE = Path("/")          # siempre es un punto de montaje: «el volumen está abierto»
        self.arranque_real = nd.ARRANQUE        # sólo se lee, en la prueba que mira su forma
        nd.ARRANQUE = self.tmp / "proc" / "boot_id"
        for d in (nd.PEDIDOS, nd.RESULTADOS, nd.ESTADO, nd.CATALOGO.parent, nd.VAULT, nd.ARRANQUE.parent):
            d.mkdir(parents=True)
        nd.ARRANQUE.write_text(f"{uuid.uuid4()}\n")     # como lo deja el kernel: un UUID y un salto de línea
        nd.CATALOGO.write_text("")
        nd.ENV.write_text(f"# de prueba\nTELEGRAM_TOKEN={TOKEN}\nCHAT_ID={CHAT}\n")
        # El candado: ninguna ruta del módulo queda apuntando al nodo real. Una constante de
        # ruta nueva en nodo-desplegar.py hace fallar esto hasta que alguien la redirija acá.
        for nombre, valor in vars(nd).items():
            if isinstance(valor, Path) and nombre != "MONTAJE":
                self.assertTrue(valor.is_relative_to(self.tmp), f"{nombre} sigue en {valor}")
        self.logs: list[str] = []
        nd.log = self.logs.append        # el real llama a `logger`: escribiría en el journal
        self.tg = TelegramFalso()
        self._n, self._token_hex = 0, secrets.token_hex
        for objeto, attr, falso in (
                (urllib.request, "urlopen", self.tg),
                (nd.subprocess, "run", mock.Mock(side_effect=AssertionError("nada corre procesos"))),
                # Ids sin choques dentro de una prueba: el real saca 2 bytes al azar por segundo.
                (nd.secrets, "token_hex", self._hex)):
            p = mock.patch.object(objeto, attr, falso)
            p.start()
            self.addCleanup(p.stop)

    def _hex(self, n=None):
        if n != 2:
            return self._token_hex(n)
        self._n += 1
        return f"{self._n:04x}"

    # ── piezas ──
    def archivo(self, relativa: str, data: bytes = b"%PDF-1.7 de prueba\n") -> str:
        ruta = self.nd.VAULT / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(data)
        return str(ruta)

    def dejar(self, ruta, motivo="", **extra) -> str:
        """Un pedido con la forma real, sin pasar por la validación del lado IA: «el lado IA
        puede mentir»."""
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.nd._dejar({"tipo": "enviar", "entradas": [], "ruta": ruta, "motivo": motivo, **extra})
        return salida.getvalue().strip()

    def cli(self, fn, args) -> str:
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(fn(args), 0)
        return salida.getvalue().strip()

    def atender(self):
        e = self.nd.Escucha()
        e.procesar_pedidos()
        return e

    def resultado(self, pid: str) -> dict:
        return json.loads((self.nd.RESULTADOS / f"{pid}.json").read_text())

    def esperar(self, pid: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return self.nd.esperar([pid, "--max", "1"])

    def rechazado(self, ruta, patron: str, **extra) -> dict:
        """El pedido se rechaza SIN llamar a Telegram, con un motivo que nombra la causa."""
        pid = self.dejar(ruta, "no debería salir", **extra)
        e = self.atender()
        self.assertEqual(self.tg.llamadas, [], f"{ruta!r} llegó a Telegram")
        r = self.resultado(pid)
        self.assertEqual(r["estado"], "rechazado", r)
        self.assertRegex(r["detalle"], patron)
        self.assertEqual(self.esperar(pid), 1)
        self.assertEqual((e.espera, e.pend, e.envios), ({}, {}, []), "no queda nada colgando ni gasta cupo")
        self.assertEqual(list(self.nd.PEDIDOS.iterdir()), [])
        self.assertEqual(r["envio"]["quien"], YO)
        self.assertTrue(any(pid in l and "rechazado" in l for l in self.logs), self.logs)
        return r

    def todo_lo_escrito(self) -> str:
        """Todo lo que la corrida dejó en disco o mandó a `logger`, para buscar el token."""
        textos = list(self.logs)
        for ruta in self.tmp.rglob("*"):
            if ruta.is_file() and not ruta.is_symlink() and ruta != self.nd.ENV \
                    and not ruta.is_relative_to(self.nd.VAULT):
                textos.append(ruta.read_text(errors="replace"))
        return "\n".join(textos)


class LadoIATests(Base):
    def test_el_pedido_tiene_la_forma_de_sugerir_y_solo_lleva_la_ruta(self):
        ruta = self.archivo("10-Proyectos/Huerta/lámina.pdf")
        id_s = self.cli(self.nd.sugerir, ["--motivo", "ver", "el", "disco", "--", "df", "-h"])
        id_e = self.cli(self.nd.enviar, [ruta, "--motivo", "Lámina", "de", "la", "huerta"])
        self.assertRegex(id_e, self.nd.RE_ID)
        pedidos = {}
        for pid in (id_s, id_e):
            f = self.nd.PEDIDOS / f"{pid}.json"
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
            pedidos[pid] = json.loads(f.read_text())
        self.assertEqual(pedidos[id_e], {"tipo": "enviar", "entradas": [], "ruta": ruta,
                                         "motivo": "Lámina de la huerta"})
        self.assertEqual(set(pedidos[id_e]) - {"ruta"}, set(pedidos[id_s]) - {"comando"})
        self.assertEqual(sorted(p.name for p in self.nd.PEDIDOS.iterdir()), sorted(f"{i}.json" for i in pedidos))

    def test_una_ruta_relativa_sale_absoluta_y_el_motivo_se_corta_en_200(self):
        self.archivo("Notas/a.md", b"# a\n")
        with mock.patch.object(os, "getcwd", return_value=str(self.nd.VAULT / "Notas")):
            pid = self.cli(self.nd.enviar, ["a.md", "--motivo", "x" * 500])
        pedido = json.loads((self.nd.PEDIDOS / f"{pid}.json").read_text())
        self.assertEqual(pedido["ruta"], str(self.nd.VAULT / "Notas/a.md"))
        self.assertEqual(pedido["motivo"], "x" * 200)

    def test_el_lado_ia_avisa_antes_y_no_deja_pedido(self):
        ruta = self.archivo("a.pdf")
        self.archivo("clave.env")
        casos = [([], "uso: nodo-desplegar enviar"), ([ruta, "otra.pdf"], "uso: nodo-desplegar enviar"),
                 ([str(self.nd.VAULT / "x/../a.pdf")], r"la ruta lleva «\.\.»"), (["/etc/hostname"], "fuera del vault personal"),
                 ([str(self.nd.VAULT / "clave.env")], "extensión no permitida"),
                 ([str(self.nd.VAULT / "no-esta.pdf")], "no existe")]
        for args, patron in casos:
            with self.subTest(args=args), self.assertRaisesRegex(SystemExit, patron):
                self.nd.enviar(args)
        self.assertEqual(list(self.nd.PEDIDOS.iterdir()), [])

    def test_la_ayuda_nombra_enviar(self):
        err = io.StringIO()
        with mock.patch.object(self.nd.sys, "argv", ["nodo-desplegar", "--help"]), contextlib.redirect_stderr(err):
            self.assertEqual(self.nd.main(), 2)
        self.assertIn("nodo-desplegar enviar <ruta> [--motivo T]", err.getvalue())
        self.assertIn("20 MB", err.getvalue())

    def test_la_documentacion_del_nodo_describe_enviar(self):
        for doc in ("IA_INSTRUCCIONES.md", "23 - Despliegue aprobado por Telegram (diseño).md"):
            self.assertTrue("nodo-desplegar enviar" in (PROYECTO / doc).read_text(encoding="utf-8"), doc)


class DuenosSpotifyTests(Base):
    """88a: un alta no puede regalar la propiedad de archivos a un usuario arbitrario."""

    def test_alta_guarda_el_dueno_y_solo_admite_las_dos_configs_privadas(self):
        destino = "/opt/nodo/datos/spotify/jaime/config.yml"
        pid = self.cli(self.nd.alta, ["spotify-jaime", "10-Proyectos/11-Pi5/pi/spotify/config-jaime.yml",
                                      destino, "--modo", "0600", "--dueno", "dcifu004:dcifu004"])
        pedido = json.loads((self.nd.PEDIDOS / f"{pid}.json").read_text())
        self.assertEqual(pedido["alta"]["dueno"], "dcifu004:dcifu004")
        self.nd.validar_dueno("dcifu004:dcifu004", Path(destino))
        with self.assertRaisesRegex(ValueError, "dcifu004 no permitido"):
            self.nd.validar_dueno("dcifu004:dcifu004", Path("/opt/nodo/datos/otro/config.yml"))
        with self.assertRaisesRegex(ValueError, "dueño no permitido"):
            self.nd.validar_dueno("nadie:nadie", Path(destino))

    def test_aplicar_deja_config_y_carpeta_privadas_del_usuario(self):
        destino = self.tmp / "spotify" / "jaime" / "config.yml"
        self.nd.PERMITIDOS = (str(self.tmp / "spotify") + "/",)
        self.nd.RUTAS_DUEÑO_USUARIO = {str(destino)}
        data = b"device_name: Casa de prueba\n"
        sha = hashlib.sha256(data).hexdigest()
        etapa = self.nd.ESTADO / "staging" / "id-prueba"
        etapa.mkdir(parents=True)
        (etapa / "spotify-jaime").write_bytes(data)
        escucha = self.nd.Escucha()
        pedido = {"id": "id-prueba", "tipo": "desplegar", "items": [{
            "nombre": "spotify-jaime", "tipo": "archivo", "destino": str(destino), "hash": sha,
            "modo": 0o600, "dueno": "dcifu004:dcifu004", "despues": [], "igual": False}], "alta": None}
        # Forma real del ataque revisado: el directorio del perfil es escribible por dcifu004.
        # La corrección no puede volver a hacer chown/chmod por ruta (un enlace lo redirigiría).
        with mock.patch.object(os, "chown", side_effect=AssertionError("chown por ruta prohibido")):
            estado, detalle = escucha.aplicar(pedido)
        self.assertEqual((estado, detalle.split(";", 1)[0]), ("aplicado", "1 archivo(s)"))
        self.assertEqual(destino.read_bytes(), data)
        self.assertEqual(stat.S_IMODE(destino.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(destino.parent.stat().st_mode), 0o700)
        self.assertEqual(destino.stat().st_uid, pwd.getpwnam("dcifu004").pw_uid)

    def test_carrera_de_perfil_hacia_enlace_no_toca_la_victima(self):
        """En la forma revisada, el perfil se reemplaza por un enlace durante el fchown."""
        destino = self.tmp / "spotify" / "jaime" / "config.yml"
        destino.parent.mkdir(parents=True)
        victima = self.tmp / "victima"
        victima.mkdir(mode=0o755)
        (victima / "no-tocar").write_text("contenido original\n")
        resguardo = self.tmp / "perfil-anclado"
        self.nd.PERMITIDOS = (str(self.tmp / "spotify") + "/",)
        self.nd.RUTAS_DUEÑO_USUARIO = {str(destino)}
        data = b"device_name: Casa de prueba\n"
        etapa = self.nd.ESTADO / "staging" / "id-carrera"
        etapa.mkdir(parents=True)
        (etapa / "spotify-jaime").write_bytes(data)
        real_chown, real_fchown, cambiado = os.chown, os.fchown, [False]

        def cambiar_por_enlace():
            if not cambiado[0]:
                cambiado[0] = True
                destino.parent.rename(resguardo)
                destino.parent.symlink_to(victima, target_is_directory=True)

        def fchown(fd, uid, gid):
            real_fchown(fd, uid, gid)
            cambiar_por_enlace()

        def chown(ruta, uid, gid):
            real_chown(ruta, uid, gid)
            cambiar_por_enlace()

        pedido = {"id": "id-carrera", "tipo": "desplegar", "items": [{
            "nombre": "spotify-jaime", "tipo": "archivo", "destino": str(destino),
            "hash": hashlib.sha256(data).hexdigest(), "modo": 0o600,
            "dueno": "dcifu004:dcifu004", "despues": [], "igual": False}], "alta": None}
        with mock.patch.object(os, "fchown", side_effect=fchown), \
                mock.patch.object(os, "chown", side_effect=chown):
            estado, _ = self.nd.Escucha().aplicar(pedido)
        self.assertEqual(estado, "aplicado")
        self.assertTrue(cambiado[0])
        self.assertEqual((victima / "no-tocar").read_text(), "contenido original\n")
        self.assertFalse((victima / "config.yml").exists())
        self.assertEqual(stat.S_IMODE(victima.stat().st_mode), 0o755)

    def test_fuente_del_tamano_real_del_binario_arm64_pasa_el_tope(self):
        # El ejecutable v0.10.5 extraído por Claude (Diego) mide 17 491 240 bytes; no se
        # disfraza de tar.gz. La prueba llama leer_fuente, no una copia del límite.
        ruta = self.nd.VAULT / "10-Proyectos/11-Pi5/pi/spotify/go-librespot-v0.10.5-linux-arm64"
        ruta.parent.mkdir(parents=True)
        with open(ruta, "wb") as fh:
            fh.truncate(17_491_240)
        with mock.patch.object(self.nd.os.path, "ismount", return_value=True):
            self.assertEqual(len(self.nd.leer_fuente(str(ruta.relative_to(self.nd.VAULT)))), 17_491_240)

    def test_fifo_del_perfil_se_rechaza_sin_esperar_un_escritor(self):
        destino = self.tmp / "spotify" / "jaime" / "config.yml"
        destino.parent.mkdir(parents=True)
        os.mkfifo(destino)
        # Forma real: el perfil es 0700 de dcifu004 y puede contener un FIFO. Antes `open`
        # esperaba indefinidamente a su escritor; stat por descriptor lo rechaza antes.
        with self.assertRaisesRegex(ValueError, "archivo regular seguro"):
            self.nd.leer_destino(destino)

    def test_tarjeta_de_un_elf_muestra_tamano_y_sha_sin_volcar_bytes(self):
        fuente = self.nd.VAULT / "10-Proyectos/11-Pi5/pi/spotify/elf-real"
        fuente.parent.mkdir(parents=True)
        datos = Path("/usr/bin/true").read_bytes()
        self.assertIn(b"\0", datos, "la prueba debe usar un ELF real, no texto con apariencia binaria")
        fuente.write_bytes(datos)
        destino = self.tmp / "opt" / "bin" / "elf-real"
        self.nd.PERMITIDOS = (str(self.tmp / "opt") + "/",)
        self.nd.CATALOGO.write_text("[entrada.elf-real]\n"
                                   f"fuente = \"{fuente.relative_to(self.nd.VAULT)}\"\n"
                                   f"destino = \"{destino}\"\nmodo = \"0755\"\n"
                                   "dueno = \"root:root\"\ndespues = []\n")
        pedido = {"tipo": "desplegar", "entradas": [{"nombre": "elf-real", "hash": ""}], "motivo": "ELF real"}
        with mock.patch.object(self.nd.os.path, "ismount", return_value=True):
            self.assertTrue(self.nd.Escucha().preparar("20261025-120000-eeee", os.getuid(), pedido, 0))
        tarjeta = self.tg.llamadas[-1]["campos"]["text"]
        self.assertIn(f"binario: {len(datos)} bytes, sha256 {hashlib.sha256(datos).hexdigest()}", tarjeta)
        self.assertNotIn("\\x00", tarjeta)

    def test_alta_enlace_solo_admite_el_binario_spotify_fijado(self):
        destino = "/usr/local/bin/go-librespot"
        objetivo = "/usr/local/lib/go-librespot/v0.10.5/go-librespot"
        pid = self.cli(self.nd.alta_enlace, ["spotify-bin", destino, objetivo])
        pedido = json.loads((self.nd.PEDIDOS / f"{pid}.json").read_text())
        self.assertEqual(pedido["alta"], {"tipo": "enlace", "destino": destino, "objetivo": objetivo})
        with self.assertRaisesRegex(ValueError, "lista cerrada"):
            self.nd.validar_enlace(Path(destino), "/etc/systemd/system/evil.service")

    def test_fuente_real_con_arroba_pasa_y_conserva_los_rechazos_de_ruta(self):
        relativa = "pi/spotify/spotify@.service"
        fuente = self.nd.VAULT / relativa
        fuente.parent.mkdir(parents=True)
        contenido = (PI / "spotify" / "spotify@.service").read_bytes()
        fuente.write_bytes(contenido)
        with mock.patch.object(self.nd.os.path, "ismount", return_value=True):
            self.assertEqual(self.nd.leer_fuente(relativa), contenido)
            for mala in ("pi/spotify/../spotify@.service", "/pi/spotify/spotify@.service"):
                with self.subTest(mala=mala), self.assertRaisesRegex(ValueError, "fuente invalida"):
                    self.nd.leer_fuente(mala)

    def test_unidad_botv3_con_arroba_ya_prepara(self):
        relativa = "10-Proyectos/11-Pi5/botv3/botv3@.service"
        fuente = self.nd.VAULT / relativa
        fuente.parent.mkdir(parents=True)
        fuente.write_bytes((PROYECTO / "botv3" / "botv3@.service").read_bytes())
        destino = self.tmp / "etc" / "botv3@.service"
        self.nd.PERMITIDOS = (str(self.tmp / "etc") + "/",)
        self.nd.CATALOGO.write_text("[entrada.unidad-botv3-at-service]\n"
                                   f"fuente = {relativa!r}\ndestino = {str(destino)!r}\n"
                                   'modo = "0644"\ndueno = "root:root"\ndespues = []\n')
        pedido = {"tipo": "desplegar", "entradas": [{"nombre": "unidad-botv3-at-service", "hash": ""}],
                  "motivo": "unidad real"}
        with mock.patch.object(self.nd.os.path, "ismount", return_value=True):
            self.assertTrue(self.nd.Escucha().preparar("20261025-120000-eeee", os.getuid(), pedido, 0))
        self.assertEqual(self.tg.llamadas[-1]["metodo"], "sendMessage")

    def test_bootstrap_entrega_a_sugerir_los_cinco_pasos_en_un_solo_comando(self):
        linea = next(l for l in (PI / "spotify" / "LEEME.md").read_text().splitlines()
                     if l.startswith("nodo-desplegar sugerir "))
        args = shlex.split(linea)
        self.assertEqual(args[:2], ["nodo-desplegar", "sugerir"])
        self.assertEqual(len(args[args.index("--") + 1:]), 1)
        pid = self.cli(self.nd.sugerir, args[2:])
        pedido = json.loads((self.nd.PEDIDOS / f"{pid}.json").read_text())
        self.assertEqual(pedido["comando"].count(" && "), 4)
        for paso in ("install -d", "install -m 0755", "install -m 0644",
                      "systemctl daemon-reload", "systemctl restart desplegar-escucha"):
            self.assertIn(paso, pedido["comando"])

    def test_enlace_igual_se_omite_pero_otro_objetivo_o_hash_se_rechaza(self):
        destino = self.tmp / "usr" / "local" / "bin" / "go-librespot"
        objetivo = str(self.tmp / "usr" / "local" / "lib" / "go-librespot" / "v0.10.5" / "go-librespot")
        destino.parent.mkdir(parents=True)
        destino.symlink_to(objetivo)
        self.nd.PERMITIDOS = (str(self.tmp / "usr") + "/",)
        self.nd.ENLACES_PERMITIDOS = {str(destino): objetivo}
        self.nd.CATALOGO.write_text("[entrada.spotify-bin]\n"
                                   'tipo = "enlace"\n'
                                   f"destino = {str(destino)!r}\nobjetivo = {objetivo!r}\n")
        bueno = {"tipo": "desplegar", "entradas": [{"nombre": "spotify-bin", "hash": hashlib.sha256(objetivo.encode()).hexdigest()}],
                 "motivo": "repetir enlace"}
        escucha = self.nd.Escucha()
        self.assertTrue(escucha.preparar("20261025-120000-eeee", os.getuid(), bueno, 0))
        self.assertEqual(self.resultado("20261025-120000-eeee")["estado"], "sin cambios")
        destino.unlink()
        destino.symlink_to("/otro/objetivo")
        with self.assertRaisesRegex(ValueError, "otro objetivo"):
            self.nd.Escucha().preparar("20261025-120001-eeee", os.getuid(), bueno, 0)
        destino.unlink()
        mal_hash = {**bueno, "entradas": [{"nombre": "spotify-bin", "hash": "00000000"}]}
        with self.assertRaisesRegex(ValueError, "hash pedido"):
            self.nd.Escucha().preparar("20261025-120002-eeee", os.getuid(), mal_hash, 0)

    def test_revertir_un_enlace_conserva_su_respaldo(self):
        destino = self.tmp / "usr" / "local" / "bin" / "go-librespot"
        objetivo = self.tmp / "usr" / "local" / "lib" / "go-librespot" / "v0.10.5" / "go-librespot"
        destino.parent.mkdir(parents=True)
        objetivo.parent.mkdir(parents=True)
        objetivo.write_bytes(b"binario real")
        self.nd.PERMITIDOS = (str(self.tmp / "usr") + "/",)
        self.nd.ENLACES_PERMITIDOS = {str(destino): str(objetivo)}
        item = {"nombre": "spotify-bin", "tipo": "enlace", "destino": str(destino),
                "objetivo": str(objetivo), "hash": hashlib.sha256(str(objetivo).encode()).hexdigest(),
                "modo": 0, "dueno": "root:root", "despues": [], "igual": False}
        self.nd.RESPALDOS.mkdir()
        escucha = self.nd.Escucha()
        escucha.despues = mock.Mock(side_effect=RuntimeError("falla posterior"))
        estado, _ = escucha.aplicar({"id": "enlace-prueba", "tipo": "desplegar", "items": [item]})
        self.assertEqual(estado, "revertido")
        self.assertFalse(destino.exists() or destino.is_symlink())
        self.assertEqual((self.nd.RESPALDOS / "desplegar-enlace-prueba" / "spotify-bin").read_text(),
                         str(objetivo) + "\n")

    def test_al_arrancar_limpia_solo_temporales_huerfanos_del_catalogo(self):
        destino = self.tmp / "usr" / "local" / "bin" / "programa"
        destino.parent.mkdir(parents=True)
        temporal = destino.parent / ".programa.nodo-desplegar-0123456789abcdef"
        conservar = destino.parent / ".programa.nodo-desplegar-no-es-un-hex"
        temporal.write_text("a medio escribir")
        conservar.write_text("no tocar")
        destino.symlink_to("/bin/true")
        self.nd.PERMITIDOS = (str(self.tmp / "usr") + "/",)
        self.nd.CATALOGO.write_text("[entrada.programa]\n"
                                   'fuente = "x"\n'
                                   f"destino = {str(destino)!r}\nmodo = \"0755\"\ndueno = \"root:root\"\ndespues = []\n")
        self.nd.Escucha()
        self.assertFalse(temporal.exists())
        self.assertEqual(conservar.read_text(), "no tocar")

    def test_escucha_tolera_ruta_de_binario_aun_no_creada_y_no_lee_home(self):
        unidad = (PI / "desplegar-escucha.service").read_text()
        self.assertIn("-/usr/local/lib/go-librespot", unidad)
        self.assertIn("/etc/systemd/user", unidad)
        self.assertIn("ProtectHome=yes", unidad)
        self.assertNotIn("/home/dcifu004", unidad)
        self.nd.validar_destino(Path("/etc/systemd/user/spotify@.service"))


class RootDespliegueTests(unittest.TestCase):
    def test_aplicar_y_revertir_root_por_descriptores_en_namespace_real(self):
        """La forma real es uid 0 aislado: aplica, respalda y revierte un archivo root:root."""
        lineas = [
            "import hashlib, importlib.util, json, tempfile",
            "from pathlib import Path",
            f"spec = importlib.util.spec_from_file_location('nd', {str(SCRIPT)!r})",
            "nd = importlib.util.module_from_spec(spec); spec.loader.exec_module(nd)",
            "raiz = Path(tempfile.mkdtemp(prefix='nd-root-'))",
            "nd.ESTADO, nd.RESPALDOS = raiz / 'estado', raiz / 'respaldos'",
            "nd.PERMITIDOS, nd.PERMITIDOS_EXACTOS = (str(raiz / 'opt') + '/',), set()",
            "[(d.mkdir(parents=True, exist_ok=True)) for d in (nd.ESTADO / 'staging' / 'p', nd.RESPALDOS)]",
            "destino = raiz / 'opt' / 'nuevo' / 'sub' / 'archivo'; destino.parent.mkdir(parents=True)",
            "destino.write_bytes(b'anterior\\n'); (nd.ESTADO / 'staging' / 'p' / 'archivo').write_bytes(b'nuevo\\n')",
            "item = {'nombre':'archivo','tipo':'archivo','destino':str(destino),'hash':hashlib.sha256(b'nuevo\\n').hexdigest(),'modo':0o755,'dueno':'root:root','despues':[],'igual':False}",
            "e = object.__new__(nd.Escucha); e.despues = lambda *a, **k: []",
            "estado, _ = e.aplicar({'id':'p','tipo':'desplegar','items':[item]}); resp = nd.RESPALDOS / 'desplegar-p'; nuevo = destino.read_bytes()",
            "e.revertir([(item, True)], resp)",
            "print(json.dumps({'uid':destino.stat().st_uid,'modo':oct(destino.stat().st_mode & 0o777),'aplicar':estado,'nuevo':nuevo.decode(),'revertido':destino.read_text(),'padre':oct(destino.parent.stat().st_mode & 0o777)}))",
        ]
        r = subprocess.run(["unshare", "-r", "python3", "-c", "\n".join(lineas)],
                           capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(r.stdout), {"uid": 0, "modo": "0o755", "aplicar": "aplicado",
                                                 "nuevo": "nuevo\n", "revertido": "anterior\n", "padre": "0o755"})


class EnvioTests(Base):
    def test_archivo_valido_sale_por_senddocument_multipart_y_queda_registrado(self):
        # Con el nombre del primer uso real, y bytes que rompen a un multipart mal hecho.
        data = b"%PDF-1.7\r\n" + bytes(range(256)) * 40 + b"\r\n--borde\r\nContent-Disposition: x\r\n\r\n\0fin"
        ruta = self.archivo("10-Proyectos/12-Monitoreo-Plantas/Huerta/Huerta - lámina de siembra y sensores.pdf", data)
        pid = self.cli(self.nd.enviar, [ruta, "--motivo", "Lámina de la huerta"])
        e = self.atender()

        self.assertEqual(len(self.tg.llamadas), 1)
        ll = self.tg.llamadas[0]
        self.assertEqual(ll["url"], f"https://api.telegram.org/bot{TOKEN}/sendDocument")
        self.assertRegex(ll["tipo"], r"^multipart/form-data; boundary=[0-9a-f]{32}$")
        self.assertEqual(ll["campos"], {"chat_id": CHAT, "caption": "Lámina de la huerta"})
        self.assertEqual(ll["archivos"], {"document": {"nombre": "Huerta - lámina de siembra y sensores.pdf",
                                                       "tipo": "application/pdf", "bytes": data}})
        self.assertEqual(ll["timeout"], self.nd.ENVIAR_ESPERA_S)

        r = self.resultado(pid)
        self.assertEqual(r["estado"], "hecho")
        self.assertEqual(r["envio"], {"ruta": ruta, "quien": YO, "bytes": len(data),
                                      "sha256": hashlib.sha256(data).hexdigest(), "mensaje": 77})
        self.assertRegex(r["hora"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
        self.assertEqual(stat.S_IMODE((self.nd.RESULTADOS / f"{pid}.json").stat().st_mode), 0o644)
        self.assertEqual(self.esperar(pid), 0)
        self.assertTrue(any(pid in l and ruta in l and r["envio"]["sha256"] in l and YO in l for l in self.logs), self.logs)
        # Sin ✅: no queda nada pendiente ni se mandó un teclado, y el pedido salió del spool.
        self.assertEqual((e.pend, e.espera), ({}, {}))
        self.assertEqual(list(self.nd.PEDIDOS.iterdir()), [])

    def test_sin_motivo_no_va_pie(self):
        pid = self.dejar(self.archivo("a.txt", b"hola\n"))
        self.atender()
        self.assertEqual(self.tg.llamadas[0]["campos"], {"chat_id": CHAT})
        self.assertEqual(self.resultado(pid)["estado"], "hecho")

    def test_cada_extension_permitida_sale_con_su_tipo(self):
        self.assertEqual(sorted(self.nd.ENVIAR_EXT), sorted([".pdf", ".png", ".jpg", ".jpeg", ".webp", ".md", ".txt", ".html"]))
        esperado = {"a.pdf": "application/pdf", "a.png": "image/png", "a.jpg": "image/jpeg", "a.jpeg": "image/jpeg",
                    "a.webp": "image/webp", "a.md": "text/markdown", "a.txt": "text/plain", "a.html": "text/html",
                    "MAYUS.PDF": "application/pdf"}
        for nombre in esperado:
            self.dejar(self.archivo(nombre))
        self.atender()
        self.assertEqual({ll["archivos"]["document"]["nombre"]: ll["archivos"]["document"]["tipo"]
                          for ll in self.tg.llamadas}, esperado)

    def test_el_root_no_usa_nada_del_pedido_salvo_ruta_y_motivo(self):
        ruta = self.archivo("real.pdf", b"lo que hay en el disco")
        pid = self.dejar(ruta, "pie\r\n--falso\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n999",
                         contenido="lo que dice la IA", document="x", nombre="otro.pdf", chat_id="999",
                         chat="999", sha256="0" * 64, bytes=1, quien="root", entradas=[{"nombre": "bin-avisos"}])
        self.atender()
        ll = self.tg.llamadas[0]
        self.assertEqual(ll["campos"]["chat_id"], CHAT)
        self.assertEqual(set(ll["campos"]), {"chat_id", "caption"})
        self.assertIn("999", ll["campos"]["caption"])      # el intento quedó como texto del pie
        self.assertEqual(ll["archivos"]["document"]["nombre"], "real.pdf")
        self.assertEqual(ll["archivos"]["document"]["bytes"], b"lo que hay en el disco")
        self.assertEqual(self.resultado(pid)["envio"], {
            "ruta": ruta, "quien": YO, "bytes": 22, "mensaje": 77,
            "sha256": hashlib.sha256(b"lo que hay en el disco").hexdigest()})

    def test_una_comilla_en_el_nombre_no_cierra_el_campo(self):
        self.dejar(self.archivo('a"; name="chat_id.pdf'))
        self.atender()
        ll = self.tg.llamadas[0]
        self.assertEqual(ll["campos"], {"chat_id": CHAT})
        self.assertEqual(list(ll["archivos"]), ["document"])
        self.assertNotIn(b'a"', ll["crudo"])

    def test_sugerir_sigue_saliendo_por_sendmessage_en_json(self):
        pid = self.cli(self.nd.sugerir, ["--motivo", "ver", "--", "df", "-h"])
        e = self.atender()
        ll = self.tg.llamadas[0]
        self.assertEqual((ll["url"], ll["tipo"]), (f"https://api.telegram.org/bot{TOKEN}/sendMessage", "application/json"))
        self.assertEqual(ll["campos"]["chat_id"], CHAT)
        self.assertIn("reply_markup", ll["campos"])
        self.assertEqual(ll["timeout"], 20)
        self.assertEqual(list(e.pend), [pid])
        self.assertEqual(e.envios, [], "sugerir no gasta cupo de envíos")


class SelloSugerirTests(Base):
    """Encargo 70r1: el resultado de un `sugerir` lleva el sha256 del motivo que Diego vio junto
    al botón, para que quien lo lea sepa QUÉ se aprobó. El toque es el `callback_data` del botón
    que recibió Telegram, desde el chat de Diego, como lo manda `getUpdates`."""

    # El motivo con que `mensaje --a pilar` pide la firma (forma real, con la huella entera).
    MOTIVO = ("Enviar a Pilar el envío 20261020-101500-a1b2c3 (html, 10 KB, sha256 " + "ab" * 32
              + "). La vista previa está en Jaime. ✅ = enviar")

    def tocar(self, e, accion: str) -> None:
        (ll,) = [l for l in self.tg.llamadas if l["metodo"] == "sendMessage"]
        (fila,) = ll["campos"]["reply_markup"]["inline_keyboard"]
        (data,) = [b["callback_data"] for b in fila if b["callback_data"].startswith(accion + "|")]
        e.callback({"id": "cb1", "from": {"id": int(CHAT)}, "message": {"chat": {"id": int(CHAT)}},
                    "data": data})

    def sello(self, motivo: str) -> str:
        return hashlib.sha256(motivo.encode("utf-8")).hexdigest()

    def test_el_check_deja_el_sha256_del_motivo_que_se_vio(self):
        pid = self.cli(self.nd.sugerir, ["--motivo", self.MOTIVO, "--", "true"])
        e = self.atender()
        self.assertIn(self.MOTIVO, self.tg.llamadas[0]["campos"]["text"])     # lo que Diego lee
        self.tocar(e, "ok2")
        r = self.resultado(pid)
        self.assertEqual((r["estado"], r["detalle"]), ("hecho", "Diego dice que lo corrió"))
        self.assertEqual(r["motivo_sha256"], self.sello(self.MOTIVO))
        self.assertNotIn("Pilar", json.dumps(r, ensure_ascii=False), "el motivo no queda en el 0644")
        self.assertEqual(set(r), {"id", "estado", "detalle", "hora", "motivo_sha256"})
        self.assertEqual(self.esperar(pid), 0)

    def test_otro_motivo_da_otro_sello(self):
        otro = self.MOTIVO.replace("ab" * 32, "cd" * 32)
        pid = self.cli(self.nd.sugerir, ["--motivo", otro, "--", "true"])
        self.tocar(self.atender(), "ok2")
        self.assertNotEqual(self.resultado(pid)["motivo_sha256"], self.sello(self.MOTIVO))

    def test_rechazado_y_vencido_tambien_lo_llevan(self):
        pid = self.cli(self.nd.sugerir, ["--motivo", self.MOTIVO, "--", "true"])
        self.tocar(self.atender(), "no")
        self.assertEqual(self.resultado(pid)["estado"], "rechazado")
        self.assertEqual(self.resultado(pid)["motivo_sha256"], self.sello(self.MOTIVO))
        self.tg.llamadas.clear()
        pid = self.cli(self.nd.sugerir, ["--motivo", self.MOTIVO, "--", "true"])
        e = self.atender()
        e.pend[pid]["creado"] -= self.nd.VENCE_S + 1
        e.limpiar()
        self.assertEqual(self.resultado(pid)["estado"], "vencido")
        self.assertEqual(self.resultado(pid)["motivo_sha256"], self.sello(self.MOTIVO))

    def test_un_pendiente_que_sobrevive_al_reinicio_del_escucha_sella_igual(self):
        pid = self.cli(self.nd.sugerir, ["--motivo", self.MOTIVO, "--", "true"])
        self.atender()
        self.tocar(self.nd.Escucha(), "ok2")                   # el escucha volvió del reinicio
        self.assertEqual(self.resultado(pid)["motivo_sha256"], self.sello(self.MOTIVO))

    def test_enviar_y_el_rechazo_al_leer_el_pedido_no_lo_llevan(self):
        pid = self.dejar(self.archivo("x.pdf"), "pie")
        self.atender()
        self.assertNotIn("motivo_sha256", self.resultado(pid))
        malo = self.nd.PEDIDOS / "20261020-101500-0abc.json"
        malo.write_text("{no es json")
        self.atender()
        self.assertEqual(set(self.resultado(malo.stem)), {"id", "estado", "detalle", "hora"})


class RechazosTests(Base):
    """Cada caso: sin llamada a Telegram, resultado «rechazado» y un motivo que dice por qué."""

    def setUp(self):
        super().setUp()
        self.afuera = self.tmp / "srv" / "afuera"
        self.afuera.mkdir()
        (self.afuera / "secreto.pdf").write_bytes(b"lo que dcifu004 no debe sacar")
        self.buena = self.archivo("Notas/buena.pdf")

    def test_ruta_con_punto_punto(self):
        # Resuelve a un archivo válido: se rechaza por el texto, no por adónde llega.
        self.rechazado(str(self.nd.VAULT / "Notas/../Notas/buena.pdf"), r"la ruta lleva «\.\.»")
        self.rechazado(str(self.nd.VAULT / "../afuera/secreto.pdf"), r"la ruta lleva «\.\.»")
        self.rechazado("/opt/../" + str(self.nd.VAULT)[1:] + "/Notas/buena.pdf", r"la ruta lleva «\.\.»")

    def test_ruta_sin_normalizar_o_relativa(self):
        self.rechazado(str(self.nd.VAULT) + "//Notas/buena.pdf", "«//»")
        self.rechazado(str(self.nd.VAULT) + "/./Notas/buena.pdf", "«/./»")
        self.rechazado("/" + str(self.nd.VAULT) + "/Notas/buena.pdf", "«//»")
        self.rechazado("Notas/buena.pdf", "absoluta")

    def test_enlace_simbolico_como_archivo(self):
        os.symlink(self.afuera / "secreto.pdf", self.nd.VAULT / "afuera.pdf")
        os.symlink(self.buena, self.nd.VAULT / "adentro.pdf")
        os.symlink("Notas/buena.pdf", self.nd.VAULT / "relativo.pdf")
        for nombre in ("afuera.pdf", "adentro.pdf", "relativo.pdf"):
            with self.subTest(nombre):
                self.rechazado(str(self.nd.VAULT / nombre), f"enlace simbólico en la ruta: .*{nombre}")

    def test_enlace_simbolico_en_un_tramo_intermedio(self):
        os.symlink(self.afuera, self.nd.VAULT / "carpeta")
        os.symlink(self.nd.VAULT / "Notas", self.nd.VAULT / "atajo")
        self.rechazado(str(self.nd.VAULT / "carpeta/secreto.pdf"), "enlace simbólico en la ruta: .*/carpeta$")
        self.rechazado(str(self.nd.VAULT / "atajo/buena.pdf"), "enlace simbólico en la ruta: .*/atajo$")

    def test_el_vault_mismo_cambiado_por_un_enlace(self):
        # /opt/nodo/datos/srv es de dcifu004: puede renombrar el vault y dejar un enlace en su lugar.
        laboral = self.tmp / "srv" / "vault_trabajo"
        laboral.mkdir()
        (laboral / "contrato.pdf").write_bytes(b"laboral")
        self.nd.VAULT.rename(self.tmp / "srv" / "vault_personal.bak")
        os.symlink(laboral, self.nd.VAULT)
        self.rechazado(str(self.nd.VAULT / "contrato.pdf"), "enlace simbólico en la ruta: .*/vault_personal$")

    def carrera(self):
        """Al mirar el tramo es una carpeta de verdad; al abrirlo ya es un enlace hacia afuera."""
        (self.nd.VAULT / "carpeta").mkdir()
        (self.nd.VAULT / "carpeta" / "secreto.pdf").write_bytes(b"inocente")
        stat_real = os.stat

        def cambia(ruta, *a, **k):
            st = stat_real(ruta, *a, **k)
            if ruta == "carpeta":
                (self.nd.VAULT / "carpeta").rename(self.nd.VAULT / "carpeta.vieja")
                os.symlink(self.afuera, self.nd.VAULT / "carpeta")
            return st
        return mock.patch.object(self.nd.os, "stat", cambia)

    def test_si_el_enlace_aparece_despues_del_lstat_lo_niega_el_open(self):
        with self.carrera():
            self.rechazado(str(self.nd.VAULT / "carpeta/secreto.pdf"), "no se pudo abrir sin seguir enlaces")

    def test_y_si_el_open_siguiera_el_enlace_lo_frena_la_ruta_real(self):
        # La segunda capa sola: un open sin O_NOFOLLOW llega al archivo de afuera, y /proc/self/fd
        # dice que lo abierto no es la ruta pedida.
        open_real = os.open
        with self.carrera(), mock.patch.object(
                self.nd.os, "open", lambda ruta, flags, *a, **k: open_real(ruta, flags & ~os.O_NOFOLLOW, *a, **k)):
            self.rechazado(str(self.nd.VAULT / "carpeta/secreto.pdf"), "la ruta cambió mientras se abría")

    def test_enlace_duro_a_un_archivo_de_afuera(self):
        os.link(self.afuera / "secreto.pdf", self.nd.VAULT / "duro.pdf")
        self.rechazado(str(self.nd.VAULT / "duro.pdf"), "enlaces duros")

    def test_secretos_git_obsidian_y_lo_oculto(self):
        for rel, patron in (("secretos/x.pdf", "«secretos» no se envía"), ("a/Secretos/x.pdf", "«Secretos» no se envía"),
                            ("secretos/sub/x.pdf", "«secretos» no se envía"), (".git/x.txt", "«.git» no se envía"),
                            ("repo/.git/hooks/x.txt", "«.git» no se envía"), (".obsidian/x.md", "«.obsidian» no se envía"),
                            (".stversions/Notas/buena.pdf", "lo oculto no se envía"), ("Notas/.oculto.pdf", "lo oculto no se envía")):
            with self.subTest(rel):
                self.rechazado(self.archivo(rel), patron)

    def test_fuera_del_vault_personal(self):
        laboral = self.tmp / "srv" / "vault_trabajo"
        for carpeta in (laboral, self.tmp / "secretos", self.tmp / "srv" / "vault_personal_copia", self.tmp / "etc"):
            carpeta.mkdir(exist_ok=True)
            (carpeta / "x.pdf").write_bytes(b"de afuera")
        for ruta in (laboral / "x.pdf", self.tmp / "secretos/x.pdf", self.tmp / "srv/vault_personal_copia/x.pdf",
                     self.tmp / "etc/x.pdf", self.afuera / "secreto.pdf", Path("/etc/hostname"), Path("/etc/passwd.pdf"),
                     Path("/opt/nodo/datos/srv/vault_trabajo/x.pdf"), Path("/opt/nodo/datos/secretos/botv3-jaime.env"),
                     Path("/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/IA_INSTRUCCIONES.md"),
                     self.nd.VAULT, Path(str(self.nd.VAULT) + ".pdf"), Path("/")):
            with self.subTest(str(ruta)):
                self.rechazado(str(ruta), r"fuera del vault personal|«//»")

    def test_fuera_del_vault_no_se_toca_el_disco(self):
        # Ni un stat: root no le dice a nadie si /root/x.pdf existe.
        with mock.patch.object(self.nd.os, "open", side_effect=AssertionError("abrió")), \
                mock.patch.object(self.nd.os, "stat", side_effect=AssertionError("miró")):
            with self.assertRaisesRegex(ValueError, "fuera del vault personal"):
                self.nd.leer_envio("/root/x.pdf")

    def test_extension_no_permitida(self):
        for nombre in ("clave.env", "guion.sh", "datos.json", "tabla.csv", "sin-extension", "truco.pdf.env",
                       "bot.py", "copia.pdf~", "audio.ogg", "comprimido.zip", "pdf"):
            with self.subTest(nombre):
                self.rechazado(self.archivo(f"Notas/{nombre}"), "extensión no permitida")

    def test_mas_de_20_mb(self):
        self.assertEqual(self.nd.ENVIAR_MAX, 20 * 1024 * 1024)
        justo, pasado = self.nd.VAULT / "justo.pdf", self.nd.VAULT / "pasado.pdf"
        for ruta, n in ((justo, self.nd.ENVIAR_MAX), (pasado, self.nd.ENVIAR_MAX + 1)):
            with open(ruta, "wb") as fh:
                fh.truncate(n)
        self.rechazado(str(pasado), r"pesa 20\.0 MB; el tope es 20 MB")     # por el tamaño, sin leerlo
        pid = self.dejar(str(justo))
        self.atender()
        self.assertEqual(self.resultado(pid)["estado"], "hecho")
        self.assertEqual(len(self.tg.llamadas[0]["archivos"]["document"]["bytes"]), self.nd.ENVIAR_MAX)

    def test_el_tope_vale_sobre_lo_leido_no_sobre_lo_que_dijo_el_stat(self):
        # El archivo crece entre el fstat y la lectura: se cuenta lo que se leyó.
        ruta = self.archivo("crece.pdf", b"x" * 4096)
        self.nd.ENVIAR_MAX = 1024
        fstat_real = os.fstat
        with mock.patch.object(self.nd.os, "fstat", lambda fd: os.stat_result(
                (*fstat_real(fd)[:6], 10, *fstat_real(fd)[7:]))):
            self.rechazado(ruta, "pesa más de")

    def test_directorio_inexistente_fifo_y_vacio(self):
        (self.nd.VAULT / "carpeta.pdf").mkdir()
        os.mkfifo(self.nd.VAULT / "tubo.pdf")
        self.rechazado(str(self.nd.VAULT / "carpeta.pdf"), "es un directorio")
        self.rechazado(str(self.nd.VAULT / "Notas"), "extensión no permitida")
        self.rechazado(str(self.nd.VAULT / "no-esta.pdf"), "no existe")
        self.rechazado(str(self.nd.VAULT / "no/esta/a.pdf"), "no existe: .*/no$")
        self.rechazado(str(self.nd.VAULT / "Notas/buena.pdf/x.pdf"), "no es una carpeta")
        self.rechazado(str(self.nd.VAULT / "tubo.pdf"), "no es un archivo regular")
        self.rechazado(self.archivo("vacio.pdf", b""), "vacío")

    def test_ruta_que_no_es_un_texto_razonable(self):
        for ruta in (None, 7, ["/etc/passwd"], {"a": 1}, "", str(self.nd.VAULT / "a\nb.pdf"),
                     str(self.nd.VAULT / "a\x00.pdf"), str(self.nd.VAULT / ("a" * 2000 + ".pdf")),
                     str(self.nd.VAULT / "a\udcff.pdf")):
            with self.subTest(repr(ruta)[:40]):
                self.rechazado(ruta, "ruta inválida")

    def test_pedido_sin_ruta(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.nd._dejar({"tipo": "enviar", "entradas": [], "motivo": "sin ruta"})
        self.atender()
        self.assertEqual(self.tg.llamadas, [])
        self.assertEqual(self.resultado(salida.getvalue().strip())["estado"], "rechazado")

    def test_un_motivo_que_no_es_utf8_no_llega_a_telegram(self):
        # Un sustituto suelto (\udcff) pasa por json.loads y revienta al guardar el estado: el
        # pedido termina rechazado sin que salga nada.
        pid = self.dejar(self.buena, "pie \udcff")
        e = self.atender()
        self.assertEqual(self.tg.llamadas, [])
        self.assertEqual(self.resultado(pid)["estado"], "rechazado")
        self.assertEqual((e.espera, e.pend), ({}, {}))
        e.guardar()                      # y el escucha sigue pudiendo guardar su estado

    def test_volumen_cerrado(self):
        self.nd.MONTAJE = self.tmp        # una carpeta cualquiera: no es un punto de montaje
        self.rechazado(self.buena, "sudo abrir-datos")


class TopeTests(Base):
    """El tope de 10 por hora, con los dos relojes en la mano: `time.time()` es la hora de pared,
    la que en la Pi (sin batería de reloj) parte atrasada y NTP corrige de un salto;
    `time.monotonic()` son los segundos desde que arrancó el equipo. Un reinicio del equipo es lo
    que es de verdad: otro boot_id y el monotónico otra vez cerca de cero."""

    def setUp(self):
        super().setUp()
        for nombre, valor in (("time", 1_800_000_000.0), ("monotonic", 7_200.0)):
            p = mock.patch.object(self.nd.time, nombre, return_value=valor)
            p.start()
            self.addCleanup(p.stop)

    def pasan(self, segundos: float) -> None:
        """Tiempo que pasa de verdad: avanzan los dos relojes."""
        self.nd.time.monotonic.return_value += segundos
        self.nd.time.time.return_value += segundos

    def salta_la_hora(self, segundos: float) -> None:
        """NTP (o nadie) corrige la hora de pared. No pasó tiempo."""
        self.nd.time.time.return_value += segundos

    def reinicia_el_equipo(self, uptime: float, salto_de_hora: float = 0.0) -> None:
        self.nd.ARRANQUE.write_text(f"{uuid.uuid4()}\n")
        self.nd.time.monotonic.return_value = uptime
        self.salta_la_hora(salto_de_hora)

    def guardado(self) -> dict:
        return json.loads((self.nd.ESTADO / "pendientes.json").read_text())

    def enviar_uno(self, i: int) -> dict:
        # Por el camino entero: `enviar()` → `_dejar()` → un Escucha nuevo (el tope sobrevive al
        # reinicio del escucha) → `procesar_pedidos()`.
        ruta = self.archivo(f"tope/{i}.txt", f"archivo {i}\n".encode())
        pid = self.cli(self.nd.enviar, [ruta, "--motivo", f"n.º {i}"])
        self.atender()
        return self.resultado(pid)

    def llenar(self) -> None:
        self.assertEqual([self.enviar_uno(i)["estado"] for i in range(10)], ["hecho"] * 10)
        self.assertEqual(len(self.tg.llamadas), 10)
        self.assertEqual(len(self.guardado()["envios"]), 10)

    def cerrado(self, i: int, faltan: str) -> dict:
        """El pedido se rechaza por el tope, no llega a Telegram y los diez cupos siguen anotados."""
        antes = len(self.tg.llamadas)
        r = self.enviar_uno(i)
        self.assertEqual(r["estado"], "rechazado", r)
        self.assertRegex(r["detalle"], rf"^tope de 10 envíos por hora; el próximo cupo se libera en {faltan} min$")
        self.assertEqual(len(self.tg.llamadas), antes, "llegó a Telegram")
        self.assertEqual(len(self.guardado()["envios"]), 10)
        return r

    def abierto(self, i: int) -> None:
        antes = len(self.tg.llamadas)
        self.assertEqual(self.enviar_uno(i)["estado"], "hecho")
        self.assertEqual(len(self.tg.llamadas), antes + 1)

    def test_diez_por_hora_y_el_once_no_llega_a_telegram(self):
        self.assertEqual((self.nd.ENVIAR_TOPE, self.nd.ENVIAR_VENTANA_S), (10, 3600))
        # Lo rechazado no gasta cupo.
        for _ in range(3):
            self.dejar("/etc/hostname")
        self.atender()
        self.llenar()
        for i in (10, 11):
            self.assertEqual(self.cerrado(i, faltan="60")["envio"]["bytes"], len(f"archivo {i}\n"))
        # Un segundo antes de la hora sigue cerrado; pasada la hora se abre.
        self.pasan(3599)
        self.cerrado(12, faltan="1")
        self.pasan(2)
        self.abierto(13)

    def test_el_cupo_se_guarda_con_el_reloj_monotonico_y_el_boot_id(self):
        # La forma del estado: lo que el próximo arranque va a leer.
        self.llenar()
        g = self.guardado()
        self.assertEqual(g["arranque"], self.nd.ARRANQUE.read_text().strip())
        self.assertEqual([set(e) for e in g["envios"]], [{"m", "id"}] * 10)
        self.assertEqual({e["m"] for e in g["envios"]}, {7_200.0})
        for e in g["envios"]:
            self.assertRegex(e["id"], self.nd.RE_ID)

    def test_un_salto_de_la_hora_no_vence_ni_un_cupo(self):
        # Mismo arranque, sin reiniciar nada: NTP corrige la hora después de los diez envíos.
        self.llenar()
        for salto in (86_400, -2 * 86_400, 10 * 365 * 86_400, -3_601, 3_601):
            with self.subTest(salto=salto):
                self.salta_la_hora(salto)
                self.cerrado(10, faltan="60")
        # Y con la hora todavía mal puesta, lo que abre el cupo es el tiempo que pasó.
        self.pasan(3599)
        self.cerrado(11, faltan="1")
        self.pasan(2)
        self.abierto(12)

    def reinicio_con_salto(self, salto: float) -> None:
        """La reproducción de la revisión 1: diez envíos, el equipo reinicia, la hora de pared
        parte corrida y no pasó una hora. El undécimo no sale."""
        self.llenar()
        self.reinicia_el_equipo(uptime=21.0, salto_de_hora=salto)
        self.cerrado(10, faltan="60")
        self.assertEqual(self.guardado()["arranque"], self.nd.ARRANQUE.read_text().strip())
        # Después NTP pone la hora en su lugar, dentro del mismo arranque: tampoco.
        self.salta_la_hora(-salto)
        self.cerrado(11, faltan="60")
        # Los cupos de antes valen una ventana entera de este arranque, ni un segundo menos.
        self.pasan(3599)
        self.cerrado(12, faltan="1")
        self.pasan(2)
        self.abierto(13)

    def test_reinicio_del_equipo_con_la_hora_un_dia_atras_no_regala_cupos(self):
        self.reinicio_con_salto(-86_400)

    def test_reinicio_del_equipo_con_la_hora_un_dia_adelante_no_regala_cupos(self):
        self.reinicio_con_salto(86_400)

    def test_reinicio_del_equipo_con_la_hora_bien_tampoco(self):
        self.reinicio_con_salto(0)

    def test_reinicio_del_equipo_y_el_escucha_vuelve_con_mas_uptime_que_antes(self):
        # Los envíos salieron a los 100 s del arranque anterior; en éste el escucha vuelve a las
        # 3 h. Restar un monotónico del otro diría «pasaron casi 3 h»: son arranques distintos.
        self.nd.time.monotonic.return_value = 100.0
        self.llenar()
        self.reinicia_el_equipo(uptime=10_800.0)
        self.cerrado(10, faltan="60")
        self.pasan(3599)
        self.cerrado(11, faltan="1")
        self.pasan(2)
        self.abierto(12)

    def test_tras_el_reinicio_la_ventana_parte_cuando_vuelve_el_escucha_y_queda_guardada(self):
        # El escucha vuelve sin pedidos que atender y más tarde se cae y lo levanta systemd, en
        # el mismo arranque: la ventana sigue contando desde la primera vez, no desde la segunda.
        self.llenar()
        self.reinicia_el_equipo(uptime=21.0, salto_de_hora=-86_400)
        self.nd.Escucha()
        g = self.guardado()
        self.assertEqual(g["arranque"], self.nd.ARRANQUE.read_text().strip())
        self.assertEqual({e["m"] for e in g["envios"]}, {21.0})
        self.assertTrue(any("otro arranque del equipo: 10 cupo(s)" in l for l in self.logs), self.logs)
        self.pasan(1800)
        self.cerrado(10, faltan="30")
        self.pasan(1799)
        self.cerrado(11, faltan="1")
        self.pasan(2)
        self.abierto(12)

    def test_reiniciar_el_escucha_en_el_mismo_arranque_no_alarga_la_ventana(self):
        # El boot_id es el mismo: los cupos conservan su edad real.
        self.llenar()
        self.pasan(1800)
        self.cerrado(10, faltan="30")
        self.pasan(1799)
        self.cerrado(11, faltan="1")
        self.pasan(2)
        self.abierto(12)

    def test_sin_boot_id_cada_arranque_del_escucha_cuenta_como_uno_del_equipo(self):
        self.nd.ARRANQUE.unlink()
        self.llenar()
        self.assertRegex(self.guardado()["arranque"], r"^sin-boot-id-[0-9a-f]{16}$")
        # Pasó más de una hora desde los envíos, pero el escucha que vuelve no puede saber si
        # el equipo reinició: los conserva la ventana entera.
        self.pasan(3700)
        self.cerrado(10, faltan="60")
        # El mismo proceso, sin reiniciar, sí sabe cuánto pasó.
        ruta = self.archivo("tope/mismo-proceso.txt", b"x\n")
        e = self.nd.Escucha()
        self.pasan(3599)
        pid = self.cli(self.nd.enviar, [ruta])
        e.procesar_pedidos()
        self.assertEqual(self.resultado(pid)["estado"], "rechazado")
        self.pasan(2)
        pid = self.cli(self.nd.enviar, [ruta])
        e.procesar_pedidos()
        self.assertEqual(self.resultado(pid)["estado"], "hecho")
        self.assertEqual(len(self.tg.llamadas), 11)

    def test_un_boot_id_que_no_es_un_uuid_es_como_no_tenerlo(self):
        ids = set()
        for contenido in (b"", b"\n", b"no-es-un-uuid\n", b"95C92047-E4AE-4E0C-BA00-1C4B3E322356\n",
                          b"95c92047-e4ae-4e0c-ba00-1c4b3e322356 y algo\n", b"\xff\xfe\n"):
            with self.subTest(contenido):
                self.nd.ARRANQUE.write_bytes(contenido)
                self.assertEqual(self.nd.leer_arranque(), "")
                ids.add(self.nd.Escucha().arranque)
        self.nd.ARRANQUE.unlink()
        self.nd.ARRANQUE.mkdir()
        self.assertEqual(self.nd.leer_arranque(), "")
        self.assertEqual(len(ids), 6, "dos arranques sin boot_id no se confunden entre sí")
        self.nd.ARRANQUE.rmdir()
        self.nd.ARRANQUE.write_text("95c92047-e4ae-4e0c-ba00-1c4b3e322356\n")
        self.assertEqual(self.nd.leer_arranque(), "95c92047-e4ae-4e0c-ba00-1c4b3e322356")

    def test_el_boot_id_y_el_reloj_reales_tienen_la_forma_que_el_codigo_espera(self):
        # Lo único de la suite que mira el equipo de verdad, y sólo lo lee.
        self.assertEqual(self.arranque_real, Path("/proc/sys/kernel/random/boot_id"))
        crudo = self.arranque_real.read_text()
        self.assertRegex(crudo, r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\n$")
        self.nd.ARRANQUE = self.arranque_real
        self.assertEqual(self.nd.leer_arranque(), crudo.strip())
        self.assertEqual(self.nd.Escucha().arranque, crudo.strip())
        reloj = self.nd.time.get_clock_info("monotonic")
        self.assertTrue(reloj.monotonic)
        self.assertFalse(reloj.adjustable, "el reloj del tope no puede ser uno que NTP corra de un salto")

    def test_el_estado_que_dejaba_la_version_anterior_no_regala_cupos(self):
        # Lo que escribía la vuelta 0: `t` con la hora de pared y sin `arranque`. No se sabe de
        # cuándo son: valen una ventana entera.
        (self.nd.ESTADO / "pendientes.json").write_text(json.dumps({
            "pend": {}, "espera": {}, "offset": 0,
            "envios": [{"t": 1_800_000_000.0 - 86_400 * i, "id": f"20261010-0200{i:02d}-{i:04x}"}
                       for i in range(10)]}))
        self.cerrado(10, faltan="60")
        self.assertEqual([set(e) for e in self.guardado()["envios"]], [{"m", "id"}] * 10)
        self.pasan(3599)
        self.cerrado(11, faltan="1")
        self.pasan(2)
        self.abierto(12)

    def test_un_cupo_con_un_reloj_imposible_no_se_da_por_vencido(self):
        # Mismo arranque, pero `m` no es un instante que ya pasó: en el futuro, NaN, o no es un
        # número. Ninguno cuenta como «anotado hace más de una hora».
        raros = [7_200.0 + 86_400, float("nan"), float("inf"), True, "7200", None, [1], {}, 1e300, 7_200.5]
        self.assertEqual(len(raros), 10)
        (self.nd.ESTADO / "pendientes.json").write_text(json.dumps({
            "pend": {}, "espera": {}, "offset": 0, "arranque": self.nd.ARRANQUE.read_text().strip(),
            "envios": [{"m": m, "id": f"20261010-0200{i:02d}-{i:04x}"} for i, m in enumerate(raros)]}))
        self.cerrado(10, faltan="60")
        self.assertEqual({e["m"] for e in self.guardado()["envios"]}, {7_200.0})
        self.pasan(3599)
        self.cerrado(11, faltan="1")
        self.pasan(2)
        self.abierto(12)

    def test_un_envio_que_telegram_rechaza_tambien_gasta_cupo(self):
        self.tg.falla = lambda req: urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b"{}"))
        self.assertEqual([self.enviar_uno(i)["estado"] for i in range(11)], ["rechazado"] * 11)
        self.assertEqual(len(self.tg.llamadas), 10)

    def test_si_el_escucha_muere_a_mitad_no_se_manda_dos_veces(self):
        class Corte(BaseException):
            pass
        ruta = self.archivo("a.pdf")
        pid = self.dejar(ruta)

        def muere(req):
            raise Corte()
        self.tg.falla = muere
        with self.assertRaises(Corte):
            self.atender()
        self.assertFalse((self.nd.RESULTADOS / f"{pid}.json").exists())
        self.tg.falla = None
        e = self.atender()               # arranca de nuevo y recupera el pedido en espera
        self.assertEqual(len(self.tg.llamadas), 1, "se volvió a mandar")
        r = self.resultado(pid)
        self.assertEqual(r["estado"], "rechazado")
        self.assertRegex(r["detalle"], "no se\\s+reintenta")
        self.assertEqual(e.espera, {})

    def test_si_se_corta_la_luz_a_mitad_tampoco_se_manda_dos_veces(self):
        # Lo mismo, pero lo que muere es el equipo: vuelve con otro boot_id y la hora atrasada.
        # La marca de «este pedido ya salió» es el cupo, y tiene que sobrevivir a ese arranque.
        class Corte(BaseException):
            pass
        pid = self.dejar(self.archivo("a.pdf"))

        def muere(req):
            raise Corte()
        self.tg.falla = muere
        with self.assertRaises(Corte):
            self.atender()
        self.assertEqual([e["id"] for e in self.guardado()["envios"]], [pid])
        self.tg.falla = None
        self.reinicia_el_equipo(uptime=15.0, salto_de_hora=-86_400)
        e = self.atender()
        self.assertEqual(len(self.tg.llamadas), 1, "se volvió a mandar")
        r = self.resultado(pid)
        self.assertEqual(r["estado"], "rechazado")
        self.assertRegex(r["detalle"], "no se\\s+reintenta")
        self.assertEqual((e.espera, [x["id"] for x in e.envios]), ({}, [pid]))


class CorteDeLuzTests(Base):
    """El hallazgo grave de la revisión 2: el cupo, que es también la marca de «este pedido ya
    salió», tiene que estar en el disco ANTES de llamar a Telegram, no en la caché del kernel.
    Los pedidos van por el camino entero y `Disco` anota, en cada paso de `guardar()` y en cada
    llamada a Telegram, todo lo que un corte ahí podría dejar. Después el equipo «vuelve» de
    cada uno: otro boot_id, el monotónico cerca de cero, y de la carpeta de estado sólo eso."""

    def setUp(self):
        super().setUp()
        for nombre, valor in (("time", 1_800_000_000.0), ("monotonic", 7_200.0)):
            p = mock.patch.object(self.nd.time, nombre, return_value=valor)
            p.start()
            self.addCleanup(p.stop)
        self.cortes: list[dict] = []
        self.en_curso = None
        self.extras = 0
        self.disco = Disco(self.nd.ESTADO, self.anotar)
        self.addCleanup(self.disco.soltar)
        self.tg.testigo = lambda: self.anotar("sendDocument")

    def documentos(self) -> list[str]:
        return [ll["archivos"]["document"]["nombre"] for ll in self.tg.llamadas]

    def anotar(self, donde: str) -> None:
        for queda in self.disco.posibles():
            corte = {"donde": donde, "salieron": self.documentos(), "pedido": self.en_curso, "queda": queda}
            if not any(all(c[k] == corte[k] for k in ("salieron", "pedido", "queda")) for c in self.cortes):
                self.cortes.append(corte)

    def pedidos(self, cuantos: int) -> None:
        for i in range(cuantos):
            ruta = self.archivo(f"corte/{i}.txt", f"archivo {i}\n".encode())
            pid = self.cli(self.nd.enviar, [ruta, "--motivo", f"n.º {i}"])
            # El pedido tal como lo dejó el lado IA: su unlink tampoco pasa por fsync.
            self.en_curso = (pid, (self.nd.PEDIDOS / f"{pid}.json").read_bytes())
            self.atender()
            self.assertEqual(self.resultado(pid)["estado"], "hecho")
        self.disco.soltar()
        self.tg.testigo = None
        self.assertEqual(len(self.tg.llamadas), cuantos)
        # Que la corrida anotó de verdad: hay cortes en cada llamada a Telegram.
        self.assertEqual(sorted({len(c["salieron"]) for c in self.cortes if c["donde"] == "sendDocument"}),
                         list(range(1, cuantos + 1)))

    def vuelve(self, corte: dict, reaparece: bool):
        """El equipo arranca después del corte y el escucha atiende lo que encuentre."""
        for carpeta in (self.nd.ESTADO, self.nd.PEDIDOS, self.nd.RESULTADOS):
            for f in carpeta.iterdir():
                if f.is_file():
                    f.unlink()
        for nombre, data in corte["queda"].items():
            (self.nd.ESTADO / nombre).write_bytes(data)
        if reaparece:
            pid, crudo = corte["pedido"]
            (self.nd.PEDIDOS / f"{pid}.json").write_bytes(crudo)
            os.chmod(self.nd.PEDIDOS / f"{pid}.json", 0o600)
        self.nd.ARRANQUE.write_text(f"{uuid.uuid4()}\n")
        self.nd.time.monotonic.return_value = 15.0
        self.tg.llamadas.clear()
        return self.atender()

    def uno_mas(self) -> dict:
        self.extras += 1
        ruta = self.archivo(f"corte/extra-{self.extras}.txt", b"otro\n")
        pid = self.cli(self.nd.enviar, [ruta])
        self.atender()
        return self.resultado(pid)

    def test_desde_cualquier_corte_de_luz_no_salen_mas_de_diez_en_la_hora(self):
        # La reproducción de la revisión 2 (diez envíos, vuelve la versión anterior de
        # pendientes.json, el undécimo sale), en todos los cortes y no sólo en el último.
        self.pedidos(10)
        self.assertGreaterEqual(len(self.cortes), 40)
        for corte in self.cortes:
            for reaparece in (False, True):
                # Sin subTest: con un `guardar()` que no confirma fallan cientos de cortes, y
                # el primero, con sus datos, ya dice cuál.
                cual = (f"corte en {corte['donde']} con {len(corte['salieron'])} enviados, el pedido "
                        f"{'reaparece' if reaparece else 'no reaparece'} y en la carpeta de estado queda "
                        f"{ {n: len(d) for n, d in corte['queda'].items()} }")
                self.vuelve(corte, reaparece)
                # Se pide hasta llenar la hora y uno más.
                ultimo = {}
                for _ in range(self.nd.ENVIAR_TOPE + 1 - len(corte["salieron"]) - len(self.tg.llamadas)):
                    ultimo = self.uno_mas()
                total = corte["salieron"] + self.documentos()
                self.assertEqual(len(total), len(set(total)), f"un archivo salió dos veces: {cual}")
                self.assertLessEqual(len(total), self.nd.ENVIAR_TOPE, f"salieron más de diez en la hora: {cual}")
                self.assertEqual(ultimo.get("estado"), "rechazado", f"el undécimo no se rechazó: {cual}")
                self.assertRegex(ultimo["detalle"], "^tope de 10 envíos por hora; el próximo cupo se libera en 60 min$", cual)

    def test_un_corte_entre_el_envio_y_el_resultado_no_lo_manda_dos_veces(self):
        # El documento ya llegó a Telegram y la luz se va antes de anotar nada más.
        self.pedidos(3)
        justo = [c for c in self.cortes if c["donde"] == "sendDocument"]
        self.assertGreaterEqual(len(justo), 3)
        for corte in justo:
            for reaparece in (False, True):
                cual = (f"corte con {len(corte['salieron'])} enviados, el pedido "
                        f"{'reaparece' if reaparece else 'no reaparece'} y en la carpeta de estado queda "
                        f"{ {n: len(d) for n, d in corte['queda'].items()} }")
                pid = corte["pedido"][0]
                e = self.vuelve(corte, reaparece)
                self.assertEqual(self.tg.llamadas, [], f"se volvió a mandar: {cual}")
                self.assertTrue((self.nd.RESULTADOS / f"{pid}.json").exists(),
                                f"el pedido que estaba en vuelo se perdió sin dejar resultado: {cual}")
                r = self.resultado(pid)
                self.assertEqual(r["estado"], "rechazado", cual)
                self.assertRegex(r["detalle"], "no se\\s+reintenta: puede haber llegado", cual)
                self.assertEqual(self.esperar(pid), 1)
                self.assertEqual(e.espera, {})
                self.assertEqual([x["id"] for x in e.envios], [c["pedido"][0] for c in justo
                                                                if len(c["salieron"]) <= len(corte["salieron"])], cual)

    def test_si_el_cupo_no_se_puede_confirmar_en_el_disco_el_archivo_no_sale(self):
        # Falla el fsync del archivo, o el de la carpeta, justo al anotar el cupo: sin la
        # confirmación no se llama a Telegram, y el cupo queda gastado igual.
        self.disco.soltar()
        self.tg.testigo = None
        reales, leer_real = {n: getattr(os, n) for n in ("fsync", "fdatasync")}, self.nd.leer_envio
        for cual in (1, 2):
            with self.subTest(fsync=cual):
                faltan = []

                def leer(ruta):
                    faltan.append(cual)      # el archivo ya se leyó: lo que sigue es anotar el cupo
                    return leer_real(ruta)

                def confirma(nombre):
                    def envuelta(fd):
                        if faltan:
                            faltan[0] -= 1
                            if faltan[0] == 0:
                                faltan.clear()
                                fallaron.append(cual)
                                raise OSError(5, "Input/output error")
                        return reales[nombre](fd)
                    return envuelta
                fallaron: list[int] = []
                pid = self.dejar(self.archivo(f"sin-disco-{cual}.pdf"))
                with mock.patch.object(self.nd, "leer_envio", leer), \
                        mock.patch.object(os, "fsync", confirma("fsync")), \
                        mock.patch.object(os, "fdatasync", confirma("fdatasync")):
                    e = self.atender()
                self.assertEqual(fallaron, [cual], "el fsync que tenía que fallar no se llamó")
                self.assertEqual(self.tg.llamadas, [], "salió sin el cupo confirmado")
                r = self.resultado(pid)
                self.assertEqual(r["estado"], "rechazado", r)
                self.assertIn("Input/output error", r["detalle"])
                self.assertEqual([x["id"] for x in e.envios][-1], pid)
                self.assertEqual(e.espera, {})

    def test_el_disco_de_prueba_distingue_lo_confirmado_de_lo_que_no(self):
        # El modelo, solo: si no distinguiera, las pruebas de arriba pasarían siempre.
        self.disco.soltar()
        carpeta = self.tmp / "modelo"
        carpeta.mkdir()
        (carpeta / "a.json").write_bytes(b"viejo")
        disco = Disco(carpeta, lambda donde: None)
        self.addCleanup(disco.soltar)
        self.assertEqual(disco.posibles(), [{"a.json": b"viejo"}])

        def escribe(data: bytes, *pasos: str) -> None:
            fh = open(carpeta / "a.tmp", "wb")
            fh.write(data)
            for paso in pasos:
                if paso == "flush":
                    fh.flush()
                elif paso == "fsync":
                    os.fsync(fh.fileno())
                elif paso == "replace":
                    fh.close()
                    os.replace(carpeta / "a.tmp", carpeta / "a.json")
                elif paso == "carpeta":
                    fd = os.open(carpeta, os.O_RDONLY | os.O_DIRECTORY)
                    os.fsync(fd)
                    os.close(fd)
            fh.close()
        # Sin fsync: puede quedar lo viejo (con o sin el temporal a medias), lo nuevo, o el
        # nombre nuevo con el archivo vacío.
        escribe(b"sin fsync", "replace")
        self.assertEqual(disco.posibles(), [{"a.json": b"viejo"}, {"a.json": b""},
                                            {"a.json": b"viejo", "a.tmp": b""}, {"a.json": b"sin fsync"}])
        # fsync del archivo sin el de la carpeta: el nombre puede seguir apuntando a lo viejo.
        escribe(b"solo el archivo", "flush", "fsync", "replace")
        self.assertIn({"a.json": b"viejo"}, disco.posibles())
        # fsync de la carpeta sin el del archivo: el nombre es firme y el contenido no.
        escribe(b"solo la carpeta", "replace", "carpeta")
        self.assertEqual(disco.posibles(), [{"a.json": b""}, {"a.json": b"solo la carpeta"}])
        # fsync sin flush: lo que seguía en el búfer de Python no llegó.
        escribe(b"sin flush", "fsync", "replace", "carpeta")
        self.assertEqual(disco.posibles(), [{"a.json": b""}, {"a.json": b"sin flush"}])
        # Los dos, en orden: no hay otra forma de amanecer.
        escribe(b"confirmado", "flush", "fsync", "replace", "carpeta")
        self.assertEqual(disco.posibles(), [{"a.json": b"confirmado"}])
        # Reescrito en su lugar, aunque después se confirme: en el medio estuvo vacío.
        vistos = []
        disco.testigo = lambda donde: vistos.extend(disco.posibles())
        with open(carpeta / "a.json", "wb") as fh:
            fh.write(b"en su lugar")
            fh.flush()
            os.fsync(fh.fileno())
        self.assertIn({"a.json": b""}, vistos)
        self.assertEqual(disco.posibles()[0], {"a.json": b"en su lugar"})


class TokenTests(Base):
    def test_un_envio_bueno_no_deja_el_token_en_ningun_lado(self):
        self.dejar(self.archivo("a.pdf"), "pie")
        self.atender()
        self.assertEqual(len(self.tg.llamadas), 1)
        escrito = self.todo_lo_escrito()
        self.assertIn("hecho", escrito)
        self.assertNotIn(TOKEN, escrito)
        self.assertNotIn(TOKEN.split(":")[1], escrito)

    def test_cuando_telegram_falla_el_error_no_trae_el_token(self):
        cuerpo = b'{"ok":false,"error_code":400,"description":"Bad Request: file must be non-empty"}'
        fallas = {
            "http": lambda req: urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(cuerpo)),
            "red": lambda req: urllib.error.URLError(f"sin ruta hacia {req.full_url}"),
            "timeout": lambda req: TimeoutError(f"timed out: {req.full_url}"),
            "raro": lambda req: Exception(f"POST {req.full_url} token={TOKEN}"),
        }
        for nombre, falla in fallas.items():
            with self.subTest(nombre):
                self.tg.falla = falla
                pid = self.dejar(self.archivo(f"{nombre}.pdf"))
                self.atender()
                r = self.resultado(pid)
                self.assertEqual(r["estado"], "rechazado")
                self.assertRegex(r["detalle"], "^Telegram no lo recibió: ")
                self.assertEqual(self.esperar(pid), 1)
                escrito = self.todo_lo_escrito()
                for parte in (TOKEN, *TOKEN.split(":")):      # ni entero ni por mitades
                    self.assertNotIn(parte, escrito)
        self.assertEqual(len(self.tg.llamadas), 4)
        self.assertIn("file must be non-empty", json.dumps(self.resultado(self.dejar_y_ver("http"))))

    def dejar_y_ver(self, nombre: str) -> str:
        return next(p.stem for p in sorted(self.nd.RESULTADOS.glob("*.json"))
                    if f"{nombre}.pdf" in p.read_text())

    def test_el_token_no_sale_de_la_memoria_de_root(self):
        # Ni al spool (que dcifu004 lee) ni a pendientes.json: solo vive en el objeto Telegram.
        e = self.atender()
        e.guardar()
        self.assertNotIn(TOKEN, self.todo_lo_escrito())
        self.assertNotIn(TOKEN, json.dumps({k: v for k, v in vars(e).items() if k != "tg"}, default=str))


# Las tres de la cola (encargos/cola-run.py, opciones_consulta()), tal cual las manda.
OPCIONES_COLA = [("aceptar", "Aceptar y seguir: la etapa se da por buena con esos hallazgos y la cola sigue"),
                 ("arreglar", "Que lo arregle: corre el arreglo y otra revisión"),
                 ("saltar", "Saltar: la cola queda pausada; se retoma con Reanudar")]
MOTIVO_COLA = ("❓ cola66 #1 · etapa 66, rev1 NO DESPLEGABLE sin graves: 1 [Media] y 2 [Baja] (títulos en "
               "encargos/66r1-RESULTADO.md). Sin respuesta en 2 h: C si hay otras colas esperando; si no, B.")


class ConsultarTests(Base):
    """Encargo 71: `consultar` es UN mensaje con las alternativas A, B, C y un botón por cada una.
    El toque es el `callback_data` del botón que recibió Telegram, desde el chat del usuario."""

    def args(self, opciones=OPCIONES_COLA, motivo=MOTIVO_COLA) -> list[str]:
        out = ["--motivo", motivo]
        for clave, etiqueta in opciones:
            out += ["--opcion", f"{clave}={etiqueta}"]
        return out

    def preguntar(self, **k):
        pid = self.cli(self.nd.consultar, self.args(**k))
        e = self.atender()
        return pid, e

    def mandados(self, metodo: str) -> list[dict]:
        return [l["campos"] for l in self.tg.llamadas if l["metodo"] == metodo]

    def toque(self, e, data: str, desde: int = int(CHAT), chat: int = int(CHAT)) -> str:
        antes = len(self.mandados("answerCallbackQuery"))
        e.callback({"id": "cb1", "from": {"id": desde}, "message": {"chat": {"id": chat}}, "data": data})
        (resp,) = self.mandados("answerCallbackQuery")[antes:]
        return resp["text"]

    def boton(self, letra: str) -> str:
        (msg,) = self.mandados("sendMessage")
        (data,) = [f[0]["callback_data"] for f in msg["reply_markup"]["inline_keyboard"]
                   if f[0]["text"].startswith(f"{letra} — ")]
        return data

    # ── C1: el lado IA ──
    def test_c1_tres_opciones_validas_dejan_un_pedido_consulta(self):
        pid = self.cli(self.nd.consultar, self.args())
        self.assertRegex(pid, self.nd.RE_ID)
        f = self.nd.PEDIDOS / f"{pid}.json"
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        self.assertEqual(json.loads(f.read_text()), {
            "tipo": "consulta", "entradas": [], "motivo": MOTIVO_COLA,
            "opciones": [{"clave": c, "etiqueta": t} for c, t in OPCIONES_COLA]})

    def test_c1_lo_que_no_calza_falla_entero_y_no_deja_pedido(self):
        a, b, c = OPCIONES_COLA
        casos = {"una": [a], "cinco": [a, b, c, ("otra", "Otra"), ("mas", "Más")],
                 "clave repetida": [a, b, ("aceptar", "Otra vez")], "mayúscula": [a, b, ("Saltar", "Saltar")],
                 "clave larga": [a, b, ("abcdefghijklm", "x")], "clave con dígito": [a, b, ("op1", "x")],
                 "clave vacía": [a, b, ("", "x")], "etiqueta con <": [a, b, ("saltar", "Saltar <b>ya</b>")],
                 "etiqueta con >": [a, b, ("saltar", "a > b")], "etiqueta con `": [a, b, ("saltar", "`rm`")],
                 "etiqueta en dos líneas": [a, b, ("saltar", "uno\ndos")], "etiqueta vacía": [a, b, ("saltar", " ")],
                 "etiqueta de 81": [a, b, ("saltar", "x" * 81)], "control de dirección": [a, b, ("saltar", "‮evil")]}
        for nombre, opciones in casos.items():
            with self.subTest(nombre), self.assertRaisesRegex(SystemExit, "consultar"):
                self.nd.consultar(self.args(opciones=opciones))
        for nombre, args in {"sin =": ["--motivo", "m", "--opcion", "aceptar", "--opcion", "b=B"],
                             "sin motivo": self.args(motivo="")[2:], "motivo en blanco": self.args(motivo="  "),
                             "motivo en dos líneas": self.args(motivo="uno\ndos"),
                             "argumento suelto": self.args() + ["--", "rm"],
                             "--opcion sin valor": self.args() + ["--opcion"]}.items():
            with self.subTest(nombre), self.assertRaisesRegex(SystemExit, "consultar"):
                self.nd.consultar(args)
        self.assertEqual(list(self.nd.PEDIDOS.iterdir()), [])

    def test_c1_por_main_el_rc_no_es_cero(self):
        for args, rc in ((self.args(), 0), (self.args(opciones=OPCIONES_COLA[:1]), "error")):
            with self.subTest(rc=rc), mock.patch.object(self.nd.sys, "argv", ["nodo-desplegar", "consultar", *args]), \
                    contextlib.redirect_stdout(io.StringIO()):
                if rc == 0:
                    self.assertEqual(self.nd.main(), 0)
                else:
                    with self.assertRaises(SystemExit) as cm:
                        self.nd.main()
                    self.assertNotIn(cm.exception.code, (0, None))
        self.assertEqual(len(list(self.nd.PEDIDOS.iterdir())), 1)

    def test_c1_el_motivo_se_corta_en_200_como_el_de_sugerir(self):
        pid = self.cli(self.nd.consultar, self.args(motivo="x" * 500))
        self.assertEqual(json.loads((self.nd.PEDIDOS / f"{pid}.json").read_text())["motivo"], "x" * 200)

    def test_la_ayuda_nombra_consultar(self):
        err = io.StringIO()
        with mock.patch.object(self.nd.sys, "argv", ["nodo-desplegar", "--help"]), contextlib.redirect_stderr(err):
            self.assertEqual(self.nd.main(), 2)
        self.assertIn("nodo-desplegar consultar --motivo T --opcion CLAVE=ETIQUETA", err.getvalue())

    # ── C2: un mensaje, un botón por opción ──
    def test_c2_un_solo_mensaje_con_tres_botones(self):
        pid, e = self.preguntar()
        (msg,) = self.mandados("sendMessage")
        self.assertEqual((msg["chat_id"], msg["parse_mode"]), (CHAT, "HTML"))
        filas = msg["reply_markup"]["inline_keyboard"]
        self.assertEqual([len(f) for f in filas], [1, 1, 1])
        nonce = e.pend[pid]["nonce"]
        self.assertEqual([f[0]["callback_data"] for f in filas], [f"op{i}|{pid}|{nonce}" for i in range(3)])
        for f in filas:
            self.assertLessEqual(len(f[0]["callback_data"].encode()), 64)
        self.assertEqual([f[0]["text"] for f in filas], ["A — Aceptar y seguir", "B — Que lo arregle", "C — Saltar"])
        texto = msg["text"]
        pos = [texto.index(f"{l} — {html.escape(t)}") for l, (_, t) in zip("ABC", OPCIONES_COLA)]
        self.assertEqual(pos, sorted(pos))
        self.assertIn(html.escape(MOTIVO_COLA), texto)
        self.assertNotIn("❌", json.dumps(msg["reply_markup"], ensure_ascii=False))
        self.assertEqual((list(e.pend), e.pend[pid]["tipo"]), ([pid], "consulta"))
        self.assertTrue(any(pid in l and "consulta" in l and "aceptar arreglar saltar" in l for l in self.logs))

    def test_c2_cuatro_opciones_y_etiquetas_largas_caben_en_el_boton(self):
        largas = [(c, "Una alternativa de nombre larguísimo que no cabe en un botón") for c in ("uno", "dos", "tres", "cuatro")]
        pid, e = self.preguntar(opciones=largas)
        (msg,) = self.mandados("sendMessage")
        botones = [f[0] for f in msg["reply_markup"]["inline_keyboard"]]
        self.assertEqual([b["text"][:4] for b in botones], ["A — ", "B — ", "C — ", "D — "])
        for b in botones:
            self.assertLessEqual(len(b["text"]), self.nd.MAX_BOTON)
            self.assertTrue(b["text"].endswith("…"))
            self.assertLessEqual(len(b["callback_data"].encode()), 64)
        self.assertIn("D — Una alternativa de nombre larguísimo que no cabe en un botón", msg["text"])

    # ── C3: el primer toque elige, el segundo no cambia nada ──
    def test_c3_tocar_b_elige_arreglar_y_quita_el_teclado(self):
        pid, e = self.preguntar()
        self.assertEqual(self.toque(e, self.boton("B")), "Elegido: B.")
        r = self.resultado(pid)
        self.assertEqual((r["estado"], r["opcion"], r["letra"]), ("hecho", "arreglar", "B"))
        self.assertEqual(set(r), {"id", "estado", "detalle", "hora", "opcion", "letra"})
        self.assertEqual(stat.S_IMODE((self.nd.RESULTADOS / f"{pid}.json").stat().st_mode), 0o644)
        self.assertEqual(self.esperar(pid), 0)
        (edit,) = self.mandados("editMessageText")
        self.assertEqual(edit["reply_markup"], {"inline_keyboard": []})
        self.assertRegex(edit["text"], r"Elegido: B — Que lo arregle: corre el arreglo y otra revisión</b> \(\d\d:\d\d\)$")
        self.assertIn(html.escape(MOTIVO_COLA), edit["text"])
        self.assertEqual((e.pend, json.loads((self.nd.ESTADO / "pendientes.json").read_text())["pend"]), ({}, {}))

    def test_c3_el_segundo_toque_no_cambia_el_resultado_ni_escribe_otro(self):
        pid, e = self.preguntar()
        b, a = self.boton("B"), self.boton("A")
        self.toque(e, b)
        ruta = self.nd.RESULTADOS / f"{pid}.json"
        antes = (ruta.read_bytes(), ruta.stat().st_mtime_ns, sorted(self.nd.RESULTADOS.iterdir()))
        for data, quien in ((b, e), (a, e), (a, self.nd.Escucha())):      # también tras reiniciar el escucha
            self.assertEqual(self.toque(quien, data), "Ya se eligió B.")
        self.assertEqual((ruta.read_bytes(), ruta.stat().st_mtime_ns, sorted(self.nd.RESULTADOS.iterdir())), antes)
        self.assertEqual(len(self.mandados("editMessageText")), 1)

    def test_c3_sale_de_pendientes_antes_de_escribir_el_resultado(self):
        pid, e = self.preguntar()
        vistos, real = [], self.nd.Escucha.resultado

        def resultado(*a, **k):
            vistos.append(json.loads((self.nd.ESTADO / "pendientes.json").read_text())["pend"])
            return real(*a, **k)
        with mock.patch.object(self.nd.Escucha, "resultado", staticmethod(resultado)):
            self.toque(e, self.boton("C"))
        self.assertEqual(vistos, [{}])
        self.assertEqual(self.resultado(pid)["opcion"], "saltar")

    def test_c3_un_pendiente_que_sobrevive_al_reinicio_elige_igual(self):
        pid, _ = self.preguntar()
        self.toque(self.nd.Escucha(), self.boton("A"))
        self.assertEqual(self.resultado(pid)["opcion"], "aceptar")

    # ── C4: toques que no valen ──
    def test_c4_otro_from_id_otro_chat_o_nonce_malo_no_resuelven(self):
        pid, e = self.preguntar()
        b = self.boton("B")
        self.assertEqual(self.toque(e, b, desde=999), "No autorizado.")
        self.assertEqual(self.toque(e, b, chat=999), "No autorizado.")
        self.assertEqual(self.toque(e, b.rsplit("|", 1)[0] + "|" + "x" * 12), "Ese pedido ya no existe o ya se resolvió.")
        for malo in (f"op3|{pid}|{e.pend[pid]['nonce']}", f"op9|{pid}|{e.pend[pid]['nonce']}",
                     f"op01|{pid}|{e.pend[pid]['nonce']}", f"op|{pid}|{e.pend[pid]['nonce']}",
                     f"no|{pid}|{e.pend[pid]['nonce']}", f"ok2|{pid}|{e.pend[pid]['nonce']}"):
            with self.subTest(malo):
                self.assertEqual(self.toque(e, malo), "Botón inválido.")
        self.assertEqual(list(e.pend), [pid])
        self.assertFalse((self.nd.RESULTADOS / f"{pid}.json").exists())
        self.assertEqual(self.mandados("editMessageText"), [])
        self.assertEqual(self.toque(e, b), "Elegido: B.")                 # el bueno, después, sí vale

    def test_c4_un_id_hostil_en_el_segundo_toque_no_lee_fuera_del_spool(self):
        (self.tmp / "afuera.json").write_text(json.dumps({"estado": "hecho", "letra": "A"}))
        _, e = self.preguntar()
        self.assertEqual(self.toque(e, "op0|../../afuera|x"), "Ese pedido ya no existe o ya se resolvió.")

    # ── vence como sugerir ──
    def test_vence_sin_respuesta_y_queda_sin_teclado(self):
        pid, e = self.preguntar()
        e.pend[pid]["creado"] -= self.nd.VENCE_S + 1
        e.limpiar()
        r = self.resultado(pid)
        self.assertEqual((r["estado"], set(r)), ("vencido", {"id", "estado", "detalle", "hora"}))
        self.assertEqual(self.esperar(pid), 1)
        (edit,) = self.mandados("editMessageText")
        self.assertEqual(edit["reply_markup"], {"inline_keyboard": []})
        self.assertRegex(edit["text"], r"Venció sin respuesta</b> \(\d\d:\d\d\)$")
        self.assertEqual(self.toque(e, self.boton("A")), "Ese pedido ya no existe o ya se resolvió.")

    # ── el escucha no confía en el spool ──
    def test_un_pedido_hostil_en_el_spool_se_rechaza_sin_llamar_a_telegram(self):
        a, b, c = [{"clave": k, "etiqueta": t} for k, t in OPCIONES_COLA]
        casos = {"etiqueta con <": [a, b, c | {"etiqueta": "<a href='x'>Saltar</a>"}], "cinco": [a, b, c, a | {"clave": "x"}, a | {"clave": "y"}],
                 "una": [a], "repetida": [a, a, c], "mayúscula": [a, b, c | {"clave": "SALTAR"}], "no es lista": {"a": a},
                 "opción que no es dict": [a, b, "saltar=Saltar"], "etiqueta no texto": [a, b, c | {"etiqueta": 7}]}
        for nombre, opciones in casos.items():
            with self.subTest(nombre):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.nd._dejar({"tipo": "consulta", "entradas": [], "motivo": "m", "opciones": opciones})
                e = self.atender()
                r = self.resultado(out.getvalue().strip())
                self.assertEqual(r["estado"], "rechazado")
                self.assertEqual((e.pend, e.espera), ({}, {}))
        for nombre, motivo in {"sin motivo": None, "vacío": "", "dos líneas": "a\nb", "no es texto": ["m"]}.items():
            with self.subTest(nombre):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.nd._dejar({"tipo": "consulta", "entradas": [], "motivo": motivo, "opciones": [a, b, c]})
                self.atender()
                self.assertEqual(self.resultado(out.getvalue().strip())["estado"], "rechazado")
        self.assertEqual(self.tg.llamadas, [])

    # Secretos ficticios con la forma de los reales: el token del bot (el mismo que el escucha lee de
    # avisos.env), una api key, y uno corto que enmascarar() no reconoce y sólo se salva si no se copia.
    SECRETOS = (TOKEN, "api_key=sk-ficticia-0123456789abcdef", "hunter2pass")

    def afuera(self, secreto: str) -> list[str]:
        """Dónde quedó algo del secreto entre lo que sale del escucha: resultados (644, fuera del
        cifrado), el journal y el estado del escucha."""
        pedazos = [secreto, *secreto.replace(":", "=").split("=")]
        donde = [f"resultados/{f.name}" for f in self.nd.RESULTADOS.iterdir()
                 if any(x in f.read_text() for x in pedazos)]
        donde += [f"log: {l}" for l in self.logs if any(x in l for x in pedazos)]
        donde += [f"estado/{f.name}" for f in self.nd.ESTADO.rglob("*")
                  if f.is_file() and any(x in f.read_text() for x in pedazos)]
        return donde

    def test_71r1_un_secreto_en_una_opcion_hostil_no_sale_del_escucha(self):
        a, b, c = [{"clave": k, "etiqueta": t} for k, t in OPCIONES_COLA]
        for secreto in self.SECRETOS:
            casos = {"primera clave": ([a | {"clave": secreto}, b, c], 1),
                     "tercera clave": ([a, b, c | {"clave": secreto}], 3),
                     "etiqueta": ([a, b | {"etiqueta": f"<{secreto}>"}, c], 2)}
            for nombre, (opciones, n) in casos.items():
                with self.subTest(secreto=secreto, caso=nombre):
                    for f in self.nd.RESULTADOS.iterdir():     # cada caso se mide solo
                        f.unlink()
                    self.logs.clear()
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        self.nd._dejar({"tipo": "consulta", "entradas": [], "motivo": MOTIVO_COLA,
                                        "opciones": opciones})
                    pid = out.getvalue().strip()
                    e = self.atender()
                    r = self.resultado(pid)
                    self.assertEqual(r["estado"], "rechazado")
                    self.assertRegex(r["detalle"], rf"^opción {n}: (clave|etiqueta) inválida")
                    self.assertEqual((e.pend, e.espera), ({}, {}))
                    self.assertTrue(self.logs, "el rechazo se anota en el journal, sin el secreto")
                    self.assertEqual(self.afuera(secreto), [])
        self.assertEqual(self.tg.llamadas, [])

    def test_71r1_el_cli_tampoco_repite_el_secreto(self):
        # Lo que imprime el CLI lo copia cola-run.py a ~/encargos-logs/avisos.log.
        a, b, _ = OPCIONES_COLA
        for secreto in self.SECRETOS:
            for opciones in ([(secreto, "Saltar"), a, b], [a, b, ("saltar", f"`{secreto}`")]):
                with self.subTest(secreto=secreto, opciones=opciones[0][0]), \
                        self.assertRaises(SystemExit) as cm:
                    self.nd.consultar(self.args(opciones=opciones))
                texto = str(cm.exception.code)
                self.assertIn("nodo-desplegar consultar: opción", texto)
                for x in [secreto, *secreto.replace(":", "=").split("=")]:
                    self.assertNotIn(x, texto)
        self.assertEqual(list(self.nd.PEDIDOS.iterdir()), [])

    def test_71r1_el_rechazo_comun_enmascara_lo_que_trae_del_spool(self):
        # El manejador de procesar_pedidos() es el mismo para todo tipo: un nombre de entrada hostil
        # en un pedido de `pedir` (su forma real) vuelve en «'<nombre>' no está en el catálogo», y un
        # nombre de archivo hostil en el spool, en el journal.
        largo = TOKEN.split(":", 1)[1]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.nd._dejar({"tipo": "desplegar", "entradas": [{"nombre": TOKEN, "hash": ""}], "motivo": "m"})
        pid = out.getvalue().strip()
        (self.nd.PEDIDOS / "token=corto123.json").write_text("{}")
        self.atender()
        r = self.resultado(pid)
        self.assertEqual(r["estado"], "rechazado")
        self.assertIn("no está en el catálogo", r["detalle"])
        self.assertIn("«oculto»", r["detalle"])
        self.assertNotIn(largo, (self.nd.RESULTADOS / f"{pid}.json").read_text())
        self.assertTrue(any("pedido invalido" in l for l in self.logs), self.logs)
        for l in self.logs:
            self.assertNotIn(largo, l)
            self.assertNotIn("corto123", l)
        self.assertEqual(self.tg.llamadas, [])

    def test_una_consulta_no_corre_nada(self):
        # subprocess.run es un Mock que falla (Base): si elegir corriera algo, la prueba lo diría.
        pid, e = self.preguntar()
        self.toque(e, self.boton("A"))
        self.assertEqual(self.nd.subprocess.run.call_count, 0)
        self.assertEqual(list((self.nd.ESTADO / "staging").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
