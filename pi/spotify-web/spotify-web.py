#!/usr/bin/env python3
"""spotify-web@: receptor Spotify con el reproductor web oficial (diseño 39, encargo 100).

Ocupa el puerto del receptor go-librespot del perfil (Jaime 3678, Pilar 3679) y responde el
mismo subconjunto de su API que usa el bot de la 88b (/status, /auth/code, /player/play,
/player/pause, /player/resume y /player/volume). Reproduce con open.spotify.com dentro de un
Chromium sin pantalla, hijo de este proceso, controlado por el DevTools Protocol POR PIPE
(fds 3 y 4): no abre ningún puerto de depuración, salvo en `--vincular`.

Sólo biblioteca estándar. Corre como dcifu004 (unidad de usuario `spotify-web@<perfil>`) y
sólo escribe en /opt/nodo/datos/spotify/<perfil>/web/ (0700/0600).

    spotify-web --perfil jaime              # el servicio
    spotify-web --perfil jaime --vincular   # iniciar sesión una vez, por túnel SSH
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

PUERTOS = {"jaime": 3678, "pilar": 3679}
NOMBRES = {"jaime": "Casa · Jaime", "pilar": "Casa · Pilar"}
DATOS = Path("/opt/nodo/datos/spotify")
CDM_ORIGEN = Path("/opt/WidevineCdm/gmp-widevinecdm/latest")
CHROMIUM = ["chromium"]
BANDERAS = ["--headless=new", "--autoplay-policy=no-user-gesture-required", "--no-first-run",
            "--window-size=1280,800"]
PUERTO_VINCULAR = 9222
TUNEL = f"ssh -L {PUERTO_VINCULAR}:127.0.0.1:{PUERTO_VINCULAR} dcifu004@nodo.example"
LOGIN = "https://accounts.spotify.com/login?continue=https%3A%2F%2Fopen.spotify.com%2F"

INACTIVIDAD_S = 15 * 60      # en pausa o detenido: se cierra Chromium (≈1,35 GB de PSS)
SONDEO_S = 2.0
ESPERA_BOTON_S = 15.0
ESPERA_SUENA_S = 15.0
VINCULAR_S = 10 * 60
MAX_CUERPO = 4096
TERMINAR_S = 10.0

RE_URI = re.compile(r"spotify:(track|artist):([0-9A-Za-z]{22})")
RE_VERSION = re.compile(r"[0-9]{1,6}(?:\.[0-9]{1,6}){1,4}")

ERROR_PAGINA = "Spotify cambió su página web (no encuentro ▶ del tema)"
ERROR_OTRO = "Spotify está sonando en otro dispositivo"
ERROR_NO_SUENA = "Spotify no empezó a sonar en este navegador"
ERROR_NAVEGADOR = "no pude abrir el navegador"
ERROR_SESION = "falta iniciar sesión en Spotify (spotify-web --vincular)"

# JavaScript FIJO. Nunca se interpola nada que venga de afuera: el único dato que entra es un
# índice entero elegido en Python. El marcador del comentario lo usa el Chromium falso.
JS_LEER = """/*sw:leer*/(() => {
  const q = s => document.querySelector(s), barra = q('[data-testid=now-playing-bar]');
  const w = q('[data-testid=now-playing-widget-v2]') || q('[data-testid=now-playing-widget]');
  const pp = q('[data-testid=control-button-playpause]');
  const t = s => { const e = q(s); return e ? e.textContent.trim() : null; };
  return { login: !!q('[data-testid=login-button]'), usuario: !!q('[data-testid=user-widget-link]'),
           ahora: w ? w.getAttribute('aria-label') : null, boton: pp ? pp.getAttribute('aria-label') : null,
           barra: barra ? barra.innerText.slice(0, 2000) : null,
           pos: t('[data-testid=playback-position]'), dur: t('[data-testid=playback-duration]') };
})()"""
JS_BOTONES = """/*sw:botones*/[...document.querySelectorAll('[data-testid=play-button]')].map(b => ({
  aria: b.getAttribute('aria-label'),
  dentro_de: b.closest('[data-testid=action-bar]') ? 'action-bar' : b.closest('[data-testid=entity-header]') ? 'entity-header' : 'root' }))"""
JS_CLIC = "/*sw:clic*/(i => { const b = document.querySelectorAll('[data-testid=play-button]')[i]; if (!b) return false; b.click(); return true; })({indice})"
JS_PLAYPAUSE = """/*sw:playpause*/(quiero => { const b = document.querySelector('[data-testid=control-button-playpause]');
  if (!b || b.getAttribute('aria-label') !== quiero) return false; b.click(); return true; })({etiqueta})"""


def log(texto: str) -> None:
    print(texto, file=sys.stderr, flush=True)


# ── Lectura de la página (funciones puras, probadas con el DOM real del fixture) ────────────

def elegir_boton(botones: list[dict[str, Any]]) -> int | None:
    """Índice del ▶ del tema: `aria-label` exactamente «Play», en la cabecera del tema.

    La página trae ~65 `[data-testid=play-button]`; el primero es «Play Liked Songs» y otros
    son de la biblioteca del usuario («Play <algo>»). Sin uno exacto en la cabecera: None.
    """
    for i, b in enumerate(botones if isinstance(botones, list) else []):
        if isinstance(b, dict) and b.get("aria") == "Play" and b.get("dentro_de") in ("action-bar", "entity-header"):
            return i
    return None


def parsear_ahora(aria: Any) -> tuple[str | None, list[str]]:
    """«Now playing: Oxytocin by Billie Eilish» → («Oxytocin», ["Billie Eilish"])."""
    if not isinstance(aria, str) or not aria.startswith("Now playing: "):
        return None, []
    resto = aria[len("Now playing: "):]
    if " by " not in resto:
        return resto.strip() or None, []
    nombre, artistas = resto.rsplit(" by ", 1)
    return nombre.strip() or None, [a.strip() for a in artistas.split(",") if a.strip()]


def otro_dispositivo(barra: Any) -> str | None:
    m = re.search(r"Playing on ([^\n]{1,80})", barra) if isinstance(barra, str) else None
    return m.group(1).strip() if m else None


def a_ms(texto: Any) -> int:
    """«3:30» o «1:02:03» → milisegundos; lo demás, 0."""
    if not isinstance(texto, str) or not re.fullmatch(r"\d{1,3}(?::\d{2}){1,2}", texto.strip()):
        return 0
    seg = 0
    for parte in texto.strip().split(":"):
        seg = seg * 60 + int(parte)
    return seg * 1000


def validar_uri(cuerpo: bytes) -> tuple[str, str] | None:
    """Cuerpo de /player/play → (tipo, id) o None. Nada que no sea exactamente la forma."""
    try:
        datos = json.loads(cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    uri = datos.get("uri") if isinstance(datos, dict) else None
    m = RE_URI.fullmatch(uri) if isinstance(uri, str) else None
    return (m.group(1), m.group(2)) if m else None


# ── Archivos: atómicos, 0700/0600 ──────────────────────────────────────────────────────────

def carpeta_privada(ruta: Path) -> Path:
    ruta.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ruta.is_symlink():
        raise RuntimeError(f"{ruta} es un enlace simbólico")
    os.chmod(ruta, 0o700)
    return ruta


def escribir_atomico(ruta: Path, datos: bytes) -> None:
    carpeta_privada(ruta.parent)
    tmp = ruta.with_name(f".{ruta.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, ruta)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def preparar_cdm(origen: Path, web: Path) -> list[str]:
    """Copia la CDM de Widevine del formato de Firefox (paquete de Raspberry Pi) al de Chromium.

    Devuelve las rutas escritas (vacío si ya estaba igual). Ver diseño 39, §5b.
    """
    manifiesto = json.loads((origen / "manifest.json").read_text(encoding="utf-8"))
    version = str(manifiesto.get("version", ""))
    if not RE_VERSION.fullmatch(version):
        raise RuntimeError("la CDM no trae una versión válida en manifest.json")
    destino = web / "cdm" / version
    so_dst = destino / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    escritos = []
    for src, dst in ((origen / "manifest.json", destino / "manifest.json"), (origen / "libwidevinecdm.so", so_dst)):
        if not dst.exists() or sha256(dst) != sha256(src):
            carpeta_privada(dst.parent)
            tmp = dst.with_name(f".{dst.name}.tmp")
            shutil.copyfile(src, tmp)
            os.chmod(tmp, 0o600)
            os.replace(tmp, dst)
            escritos.append(str(dst))
    for c in (web / "cdm", destino, destino / "_platform_specific", so_dst.parent):
        carpeta_privada(c)
    pista = web / "chromium" / "WidevineCdm" / "latest-component-updated-widevine-cdm"
    contenido = json.dumps({"Path": str(destino)}).encode()
    if not pista.exists() or pista.read_bytes() != contenido:
        escribir_atomico(pista, contenido)
        escritos.append(str(pista))
    return escritos


# ── DevTools Protocol por pipe ─────────────────────────────────────────────────────────────

class CdpError(RuntimeError):
    pass


def _hijo_fds(lee: int, escribe: int) -> Callable[[], None]:
    """En el hijo: Chromium LEE comandos del fd 3 y ESCRIBE respuestas en el fd 4."""
    def acomodar() -> None:
        a = fcntl.fcntl(lee, fcntl.F_DUPFD, 10)
        b = fcntl.fcntl(escribe, fcntl.F_DUPFD, 10)
        os.dup2(a, 3)
        os.dup2(b, 4)
    return acomodar


_RESERVA = threading.Lock()


def _reservar_3_y_4() -> None:
    """Con pass_fds=(3, 4), el hijo marca 3 y 4 como heredables ANTES de preexec_fn: si en el padre no
    hay nada abierto en esos números, el exec falla con EBADF. Se ocupan con /dev/null (no heredable)."""
    for fd in (3, 4):
        try:
            os.fstat(fd)
        except OSError:
            n = os.open(os.devnull, os.O_RDONLY)
            if n != fd:
                os.dup2(n, fd, inheritable=False)
                os.close(n)


class Cdp:
    """Un Chromium hijo y su conversación CDP por pipe (mensajes JSON terminados en \\0)."""

    def __init__(self, argv: list[str]):
        with _RESERVA:
            _reservar_3_y_4()
        a_hijo_r, self._w = os.pipe()       # comandos: nosotros → fd 3 del hijo
        self._r, del_hijo_w = os.pipe()     # respuestas: fd 4 del hijo → nosotros
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         pass_fds=(3, 4), preexec_fn=_hijo_fds(a_hijo_r, del_hijo_w), start_new_session=True)
        finally:
            os.close(a_hijo_r)
            os.close(del_hijo_w)
        self._id = 0
        self._lock = threading.Lock()
        self._esperas: dict[int, list[Any]] = {}
        self.sesion: str | None = None
        self._lector = threading.Thread(target=self._leer, daemon=True)
        self._lector.start()

    def _leer(self) -> None:
        resto = b""
        with os.fdopen(self._r, "rb", buffering=0) as f:
            while True:
                trozo = f.read(65536)
                if not trozo:
                    break
                resto += trozo
                while b"\0" in resto:
                    linea, resto = resto.split(b"\0", 1)
                    try:
                        msg = json.loads(linea)
                    except ValueError:
                        continue
                    espera = self._esperas.get(msg.get("id")) if isinstance(msg, dict) else None
                    if espera is not None:
                        espera[1] = msg
                        espera[0].set()
        for espera in list(self._esperas.values()):
            espera[0].set()

    def enviar(self, metodo: str, params: dict[str, Any] | None = None, timeout: float = 30.0, en_pagina: bool = True) -> dict[str, Any]:
        with self._lock:
            self._id += 1
            ident = self._id
            espera: list[Any] = [threading.Event(), None]
            self._esperas[ident] = espera
            msg: dict[str, Any] = {"id": ident, "method": metodo, "params": params or {}}
            if en_pagina and self.sesion:
                msg["sessionId"] = self.sesion
            try:
                os.write(self._w, json.dumps(msg).encode() + b"\0")
            except OSError as exc:
                self._esperas.pop(ident, None)
                raise CdpError("el navegador no responde") from exc
        try:
            if not espera[0].wait(timeout) or espera[1] is None:
                raise CdpError(f"sin respuesta a {metodo}")
        finally:
            self._esperas.pop(ident, None)
        if "error" in espera[1]:
            raise CdpError(f"{metodo}: {str(espera[1]['error'].get('message', ''))[:120]}")
        return espera[1].get("result", {})

    def abrir_pagina(self, timeout: float) -> None:
        objetivo = self.enviar("Target.createTarget", {"url": "about:blank"}, timeout, en_pagina=False)["targetId"]
        self.sesion = self.enviar("Target.attachToTarget", {"targetId": objetivo, "flatten": True}, timeout, en_pagina=False)["sessionId"]
        self.enviar("Page.enable", timeout=timeout)

    def evaluar(self, expresion: str, timeout: float = 10.0) -> Any:
        r = self.enviar("Runtime.evaluate", {"expression": expresion, "returnByValue": True}, timeout)
        if r.get("exceptionDetails"):
            raise CdpError("error de JavaScript en la página")
        return r.get("result", {}).get("value")

    def vivo(self) -> bool:
        return self.proc.poll() is None

    def cerrar(self, espera: float = TERMINAR_S) -> None:
        try:
            os.close(self._w)
        except OSError:
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(espera)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)


# ── El controlador ─────────────────────────────────────────────────────────────────────────

class Controlador:
    def __init__(self, perfil: str, datos: Path = DATOS, cdm_origen: Path = CDM_ORIGEN, chromium: list[str] | None = None,
                 reloj: Callable[[], float] = time.monotonic, inactividad: float = INACTIVIDAD_S, sondeo: float = SONDEO_S,
                 espera_boton: float = ESPERA_BOTON_S, espera_suena: float = ESPERA_SUENA_S, paso: float = 0.5,
                 terminar: float = TERMINAR_S, arranque: float = 60.0):
        if perfil not in PUERTOS:
            raise ValueError("perfil desconocido")
        self.perfil, self.puerto, self.nombre = perfil, PUERTOS[perfil], NOMBRES[perfil]
        self.web = Path(datos) / perfil / "web"
        self.cdm_origen, self.chromium = Path(cdm_origen), list(chromium or CHROMIUM)
        self.reloj, self.inactividad, self.sondeo, self.paso = reloj, inactividad, sondeo, paso
        self.espera_boton, self.espera_suena, self.terminar, self.arranque = espera_boton, espera_suena, terminar, arranque
        self.lock = threading.Lock()          # la caché
        self.orden = threading.Lock()          # una acción del navegador a la vez
        self.cdp: Cdp | None = None
        self.arrancando: Cdp | None = None     # el que todavía no contesta: también se cierra al salir
        self.parar = threading.Event()
        self.cache: dict[str, Any] = {"stopped": True, "paused": False, "buffering": False, "track": None, "ultimo_error": None}
        self.inactivo_desde: float | None = None
        guardado = self._leer_estado()
        self.ultimo: dict[str, Any] | None = guardado.get("ultimo") if isinstance(guardado.get("ultimo"), dict) else None
        if isinstance(guardado.get("sesion"), bool):
            self.sesion = guardado["sesion"]
        else:   # sin estado.json (p. ej. la sesión migrada de la Prueba 0): el perfil de Chromium manda
            self.sesion = (self.web / "chromium" / "Default").is_dir()
        if self.ultimo and self.ultimo.get("uri"):
            self.cache["track"] = self._track(self.ultimo)

    # estado.json: sesión y último tema; atómico, 0600.
    def _leer_estado(self) -> dict[str, Any]:
        try:
            datos = json.loads((self.web / "estado.json").read_text(encoding="utf-8"))
            return datos if isinstance(datos, dict) else {}
        except (OSError, ValueError):
            return {}

    def _guardar_estado(self) -> None:
        escribir_atomico(self.web / "estado.json", json.dumps({"sesion": self.sesion, "ultimo": self.ultimo}, ensure_ascii=False).encode())

    @staticmethod
    def _track(t: dict[str, Any]) -> dict[str, Any]:
        return {"uri": t.get("uri"), "name": t.get("name"), "artist_names": list(t.get("artist_names") or []), "artist_uris": [],
                "album_name": None, "album_uri": None, "album_cover_url": None, "position": int(t.get("position") or 0),
                "duration": int(t.get("duration") or 0), "release_date": None, "track_number": None, "disc_number": None,
                "format": None, "codec": None, "bitrate": None, "sample_rate": None, "bit_depth": None}

    # ── /status desde la caché: nunca espera al navegador ──
    def status(self) -> dict[str, Any] | None:
        with self.lock:
            if not self.sesion:
                return None
            c = dict(self.cache)
        return {"username": None, "device_id": f"spotify-web-{self.perfil}", "device_type": "SPEAKER", "device_name": self.nombre,
                "play_origin": "spotify-web", "play_origin_device_id": None, "context_uri": None, "context_name": None,
                "stopped": c["stopped"], "paused": c["paused"], "buffering": c["buffering"], "volume": None, "volume_steps": None,
                "repeat_context": False, "repeat_track": False, "shuffle_context": False, "track": c["track"], "ultimo_error": c["ultimo_error"]}

    def _poner(self, **cambios: Any) -> None:
        with self.lock:
            self.cache.update(cambios)

    def _error(self, texto: str | None) -> None:
        if texto:
            log(f"spotify-web {self.perfil}: {texto}")
        self._poner(ultimo_error=texto)

    # ── órdenes: responden de inmediato, el trabajo va en un hilo ──
    def _en_hilo(self, fn: Callable[..., None], *args: Any) -> None:
        threading.Thread(target=self._con_orden, args=(fn, *args), daemon=True).start()

    def _con_orden(self, fn: Callable[..., None], *args: Any) -> None:
        with self.orden:
            try:
                fn(*args)
            except Exception as exc:          # un hilo de orden nunca tumba el servicio
                self._error(f"{ERROR_NAVEGADOR}: {type(exc).__name__}")
                self._poner(buffering=False)

    def play(self, tipo: str, ident: str) -> None:
        self._poner(buffering=True, stopped=False, paused=False, ultimo_error=None)
        self.inactivo_desde = None
        self._en_hilo(self._reproducir, tipo, ident)

    def pause(self) -> None:
        if self.cdp is None or not self.cdp.vivo():
            return
        self._poner(paused=True)
        self._en_hilo(self._playpause, "Pause")

    def resume(self) -> None:
        if self.cdp is None or not self.cdp.vivo():
            m = RE_URI.fullmatch(str((self.ultimo or {}).get("uri", "")))
            if m:
                self.play(m.group(1), m.group(2))
            return
        self._poner(paused=False)
        self._en_hilo(self._playpause, "Play")

    # ── navegador ──
    def _asegurar_navegador(self) -> Cdp:
        if self.cdp is not None and self.cdp.vivo():
            return self.cdp
        carpeta_privada(self.web)
        try:
            preparar_cdm(self.cdm_origen, self.web)
        except (OSError, ValueError, RuntimeError) as exc:
            log(f"spotify-web {self.perfil}: CDM sin preparar ({type(exc).__name__}); se sigue con la que haya")
        argv = [*self.chromium, *BANDERAS, "--remote-debugging-pipe", f"--user-data-dir={carpeta_privada(self.web / 'chromium')}", "about:blank"]
        cdp = self.arrancando = Cdp(argv)
        try:
            cdp.abrir_pagina(self.arranque)
        except CdpError:
            cdp.cerrar(self.terminar)
            raise
        finally:
            self.arrancando = None
        if self.parar.is_set():
            cdp.cerrar(self.terminar)
            raise CdpError("el servicio se está cerrando")
        self.cdp = cdp
        return cdp

    def _leer(self, cdp: Cdp) -> dict[str, Any]:
        v = cdp.evaluar(JS_LEER)
        return v if isinstance(v, dict) else {}

    def _aplicar(self, v: dict[str, Any], uri: str | None = None) -> None:
        """Pasa lo leído de la página a la caché (y a estado.json si cambia la sesión o el tema)."""
        if v.get("login") and not v.get("usuario"):
            if self.sesion:
                self.sesion = False
                self._guardar_estado()
            self._poner(buffering=False)
            return
        if v.get("usuario") and not self.sesion:
            self.sesion = True
            self._guardar_estado()
        nombre, artistas = parsear_ahora(v.get("ahora"))
        sonando = v.get("boton") == "Pause"
        cambios: dict[str, Any] = {"paused": not sonando and nombre is not None, "stopped": nombre is None, "buffering": False}
        if nombre:
            previo = self.ultimo or {}
            t = {"uri": uri or (previo.get("uri") if previo.get("name") == nombre else None), "name": nombre, "artist_names": artistas,
                 "position": a_ms(v.get("pos")), "duration": a_ms(v.get("dur"))}
            if (previo.get("uri"), previo.get("name")) != (t["uri"], t["name"]):
                self.ultimo = {k: t[k] for k in ("uri", "name", "artist_names", "duration")}
                self._guardar_estado()
            cambios["track"] = self._track(t)
        self._poner(**cambios)
        if sonando:
            self.inactivo_desde = None
        elif self.inactivo_desde is None:
            self.inactivo_desde = self.reloj()

    def _esperar(self, plazo: float, prueba: Callable[[], Any]) -> Any:
        fin = time.monotonic() + plazo
        while True:
            r = prueba()
            if r is not None or time.monotonic() >= fin or self.parar.is_set():
                return r
            time.sleep(self.paso)

    def _reproducir(self, tipo: str, ident: str) -> None:
        cdp = self._asegurar_navegador()
        uri = f"spotify:{tipo}:{ident}"
        cdp.enviar("Page.navigate", {"url": f"https://open.spotify.com/{tipo}/{ident}"})   # id ya validado: [0-9A-Za-z]{22}

        def boton() -> int | None:
            v = self._leer(cdp)
            if v.get("login") and not v.get("usuario"):
                return -1
            return elegir_boton(cdp.evaluar(JS_BOTONES))
        i = self._esperar(self.espera_boton, boton)
        if i == -1:
            self._aplicar({"login": True})
            self._error(ERROR_SESION)
            return
        if i is None:
            self._poner(buffering=False, stopped=True)
            self._error(ERROR_PAGINA)
            return
        cdp.evaluar(JS_CLIC.replace("{indice}", str(int(i))))

        def suena() -> dict[str, Any] | None:
            v = self._leer(cdp)
            if otro_dispositivo(v.get("barra")):
                return {"otro": True, **v}
            return v if v.get("boton") == "Pause" and parsear_ahora(v.get("ahora"))[0] else None
        v = self._esperar(self.espera_suena, suena)
        if v and v.get("otro"):
            cdp.evaluar(JS_PLAYPAUSE.replace("{etiqueta}", json.dumps("Pause")))
            self._poner(paused=True, stopped=False, buffering=False)
            self._error(ERROR_OTRO)
            self.inactivo_desde = self.reloj()
            return
        if not v:
            self._poner(buffering=False)
            self._error(ERROR_NO_SUENA)
            return
        self._aplicar(v, uri)
        self._error(None)

    def _playpause(self, quiero: str) -> None:
        cdp = self.cdp
        if cdp is None or not cdp.vivo():
            return
        cdp.evaluar(JS_PLAYPAUSE.replace("{etiqueta}", json.dumps(quiero)))
        self._aplicar(self._leer(cdp))

    def cerrar_navegador(self) -> None:
        cdp, self.cdp = self.cdp, None
        for x in (cdp, self.arrancando):
            if x is not None:
                x.cerrar(self.terminar)
        self._poner(stopped=True, paused=False, buffering=False)
        self.inactivo_desde = None

    def tick(self) -> None:
        """Un sondeo: lee la página y cierra el navegador tras la inactividad."""
        cdp = self.cdp
        if cdp is None:
            return
        if not cdp.vivo():
            self.cerrar_navegador()
            return
        if not self.orden.acquire(blocking=False):
            return                             # hay una orden en curso: ella actualiza la caché
        try:
            try:
                self._aplicar(self._leer(cdp))
            except CdpError:
                pass
            if self.inactivo_desde is not None and self.reloj() - self.inactivo_desde >= self.inactividad:
                log(f"spotify-web {self.perfil}: {int(self.inactividad // 60)} min sin sonar, cierro el navegador")
                self.cerrar_navegador()
        finally:
            self.orden.release()

    def bucle(self) -> None:
        while not self.parar.wait(self.sondeo):
            try:
                self.tick()
            except Exception as exc:
                log(f"spotify-web {self.perfil}: sondeo falló ({type(exc).__name__})")


# ── HTTP ───────────────────────────────────────────────────────────────────────────────────

def manejador(ctl: Controlador) -> type[BaseHTTPRequestHandler]:
    class Manejador(BaseHTTPRequestHandler):
        server_version = "spotify-web"
        timeout = 5

        def log_message(self, *a: Any) -> None:
            pass

        def _responder(self, codigo: int, datos: Any = None) -> None:
            cuerpo = b"" if datos is None else json.dumps(datos, ensure_ascii=False).encode()
            self.send_response(codigo)
            if cuerpo:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _cuerpo(self) -> bytes | None:
            try:
                largo = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if largo < 0 or largo > MAX_CUERPO:
                self.close_connection = True
                return None
            return self.rfile.read(largo) if largo else b""

        def do_GET(self) -> None:
            if self.path == "/status":
                datos = ctl.status()
                self._responder(204 if datos is None else 200, datos)
            elif self.path == "/auth/code":
                self._responder(204)          # la vinculación es manual (--vincular): no hay código
            else:
                self._responder(404)

        def do_POST(self) -> None:
            cuerpo = self._cuerpo()
            if self.path == "/player/play":
                v = validar_uri(cuerpo) if cuerpo is not None else None
                if v is None:
                    self._responder(400, {"error": "uri inválida"})
                    return
                ctl.play(*v)
                self._responder(202)
            elif cuerpo is None:
                self._responder(400, {"error": "cuerpo inválido"})
            elif self.path == "/player/pause":
                ctl.pause()
                self._responder(204)
            elif self.path == "/player/resume":
                ctl.resume()
                self._responder(204)
            elif self.path == "/player/volume":
                self._responder(501)
            else:
                self._responder(404)
    return Manejador


def servir(ctl: Controlador, puerto: int | None = None) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer(("127.0.0.1", ctl.puerto if puerto is None else puerto), manejador(ctl))
    servidor.daemon_threads = True
    return servidor


# ── --vincular ─────────────────────────────────────────────────────────────────────────────

def puerto_ocupado(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", puerto))
        except OSError:
            return True
    return False


def hay_sesion_en(paginas: Any) -> bool:
    """La página quedó en open.spotify.com (el login de accounts.spotify.com ya devolvió)."""
    return any(isinstance(p, dict) and p.get("type") == "page" and str(p.get("url", "")).startswith("https://open.spotify.com/")
               for p in (paginas if isinstance(paginas, list) else []))


def vincular(ctl: Controlador, plazo: float = VINCULAR_S, paso: float = 5.0) -> int:
    if puerto_ocupado(ctl.puerto):
        print(f"spotify-web@{ctl.perfil} está activo (el puerto {ctl.puerto} está ocupado). Detenlo antes: "
              f"systemctl --user stop spotify-web@{ctl.perfil}", file=sys.stderr)
        return 2
    carpeta_privada(ctl.web)
    try:
        preparar_cdm(ctl.cdm_origen, ctl.web)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Aviso: no pude preparar la CDM ({type(exc).__name__}); el inicio de sesión igual funciona.", file=sys.stderr)
    argv = [*ctl.chromium, *BANDERAS, "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={PUERTO_VINCULAR}",
            f"--user-data-dir={carpeta_privada(ctl.web / 'chromium')}", LOGIN]
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(f"Desde el PC: {TUNEL}\nLuego chrome://inspect → «Configure…» 127.0.0.1:{PUERTO_VINCULAR} → inspect, e inicia sesión en Spotify.\n"
          f"Espero hasta {int(plazo // 60)} min.", flush=True)
    ok = False
    fin = time.monotonic() + plazo
    try:
        while time.monotonic() < fin and proc.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_VINCULAR}/json", timeout=3) as r:
                    if hay_sesion_en(json.loads(r.read(1 << 20))):
                        ok = True
                        break
            except (OSError, ValueError):
                pass
            time.sleep(paso)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(TERMINAR_S)
            except subprocess.TimeoutExpired:
                proc.kill()
    ctl.sesion = ok
    ctl._guardar_estado()
    print("Sesión guardada." if ok else "No quedó sesión iniciada.", flush=True)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description="Receptor Spotify con el reproductor web oficial (diseño 39).")
    a.add_argument("--perfil", required=True, choices=sorted(PUERTOS))
    a.add_argument("--vincular", action="store_true")
    o = a.parse_args(argv)
    os.umask(0o077)
    ctl = Controlador(o.perfil)
    if o.vincular:
        return vincular(ctl)
    carpeta_privada(ctl.web)
    servidor = servir(ctl)                    # si el puerto está ocupado, falla acá: un solo proceso por perfil
    threading.Thread(target=ctl.bucle, daemon=True).start()

    def salir(*_: Any) -> None:
        threading.Thread(target=servidor.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, salir)
    signal.signal(signal.SIGINT, salir)
    log(f"spotify-web {o.perfil}: escuchando en 127.0.0.1:{ctl.puerto}")
    try:
        servidor.serve_forever(poll_interval=0.5)
    finally:
        ctl.parar.set()
        ctl.cerrar_navegador()
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
