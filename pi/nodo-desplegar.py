#!/usr/bin/python3
"""nodo-desplegar — despliegue aprobado por Telegram (doc 23). Version permanente, 27-09-2026.

  Lado IA (como dcifu004, SIN sudo; devuelven un id):
    nodo-desplegar pedir <entrada>[=<sha256>]... [--motivo T]    instala entradas del catalogo
    nodo-desplegar probar <entrada>[=<sha256>] [--motivo T] [-- ARGS...]
                                                   corre UNA vez como root la version del vault
    nodo-desplegar alta <nombre> <fuente> <destino> [--modo 0755] [--dueno USER:GROUP]
                         [--despues ACC...] [--motivo T]
                                                   agrega una entrada al catalogo y la instala
    nodo-desplegar alta-enlace <nombre> <destino> <objetivo> [--motivo T]
                                                   da de alta el único enlace Spotify permitido
    nodo-desplegar sugerir [--motivo T] -- <comando en una linea>
                                                   le manda a Diego la linea EXACTA para copiar y
                                                   pegar en Termux, ya envuelta en `ssh -t` a la
                                                   Pi; no ejecuta nada. ✅ = la corrio. El
                                                   resultado lleva `motivo_sha256`
    nodo-desplegar consultar --motivo T --opcion CLAVE=ETIQUETA [--opcion ...]
                                                   UN mensaje con 2 a 4 alternativas (A, B,
                                                   C, D), un boton por cada una; no ejecuta
                                                   nada. El resultado lleva `opcion` = CLAVE
    nodo-desplegar enviar <ruta> [--motivo T]      le manda al usuario, como documento de
                                                   Telegram, UN archivo del vault personal
                                                   (pdf png jpg jpeg webp md txt html, hasta
                                                   20 MB, 10 por hora); el motivo va de pie.
                                                   Sin ✅: `esperar` dice hecho o rechazado
    nodo-desplegar esperar <id> [--max SEG]        exit 0 aplicado/probado ok/hecho, 1 no,
                                                   3 sin respuesta, 4 sin cambios
    nodo-desplegar catalogo                        lista las entradas (sin root)

  Lado root:
    nodo-desplegar escuchar                        el escucha (desplegar-escucha.service)

  `=<sha256>` (8+ hex, prefijo): el escucha espera hasta 3 min a que Syncthing traiga esa
  version antes de preparar. Sin eso, un pedido hecho apenas se edita en el notebook ve la
  version vieja (Syncthing tarda ~1 min; pagado el 27-09).

LA IA PROPONE, DIEGO APRUEBA CON UN BOTON, Y LO APROBABLE ESTA ACOTADO POR EL CATALOGO,
NO POR QUIEN APRIETA. Lo que no se deduce leyendo el codigo:

1. El pedido SOLO NOMBRA ENTRADAS de /etc/nodo/desplegar.toml (root). Una entrada nueva
   (`alta`) es un pedido mas, siempre con marca roja y doble confirmacion.
2. Las fuentes se copian a staging root AL PREPARAR, no al aprobar: el vault lo escribe
   dcifu004, y sin esto podria cambiar el archivo entre el ✅ y la instalacion (TOCTOU). Se
   abren con O_NOFOLLOW y se verifica por /proc/self/fd que el archivo abierto este dentro
   del vault: un enlace simbolico no sirve para leer como root lo que dcifu004 no puede.
3. PERMITIDOS/PROHIBIDOS van escritos aca y no en el catalogo, a proposito: un aprobador
   cuya lista de prohibidos se despliega por el mismo camino termina aprobandose solo. La
   unidad los repite como ReadWritePaths: si el codigo tiene un bug, el kernel igual niega.
4. El callback vale solo si viene del CHAT_ID de Diego, con el nonce del pedido, antes de
   que venza y una vez. El token no puede fabricar un toque: Telegram firma el from.id.
5. Los bots de Telegram no tienen cifrado de extremo a extremo: nada de secretos/ ni *.env
   como fuente, y diff y salidas se enmascaran antes de salir.
6. Se contesta el toque ANTES de trabajar. Si el answerCallbackQuery llega tarde el boton
   queda con el relojito y la persona vuelve a tocar (pagado en la prueba del 27-09).
7. SOLO IPv4 hacia Telegram: ver el comentario junto a socket.getaddrinfo.
8. `probar` corre fuera del sandbox del escucha (systemd-run --wait): las pruebas reales
   necesitan Docker, smartctl, el LUKS. Ejecutar como root algo no desplegado es tan
   delicado como desplegarlo, por eso pasa por el mismo boton.
9. `enviar` no pide ✅ (es un envio al propio usuario, como `sugerir`) y por eso lo unico
   que lo acota son sus limites, que se validan ACA, del lado root: el pedido solo trae una
   RUTA y el escucha abre el archivo el mismo, tramo por tramo y sin seguir un solo enlace.
   No mira el contenido: lo que dcifu004 pueda copiar al vault personal, puede salir.
   El tope por hora NO se mide con la hora de pared: la Pi no tiene bateria de reloj, parte
   atrasada y NTP la corrige de un salto, y ese salto no es una hora que paso. Se mide con
   el reloj monotonico, que solo vale dentro de un arranque del equipo (boot_id): si el
   arranque es otro, cada cupo guardado vuelve a valer una ventana entera.
   El cupo se confirma en el disco (fsync) ANTES de llamar a Telegram: un corte de luz no
   lo devuelve, y es tambien lo que impide mandar dos veces el pedido que quedo a medias.
10. `consultar` (encargo 71) es una pregunta con alternativas en UN mensaje: tres mensajes
   con su ✅ cada uno invitaban a tocar los tres (cola66, 19-10). No corre nada: solo anota
   la clave elegida. El primer toque valido lo saca de pendientes ANTES de escribir el
   resultado y deja el mensaje sin teclado; no queda nada mas que tocar. Las opciones se
   validan en el CLI y otra vez aca (root no confia en el spool) y se rechaza el pedido
   entero si una no calza: nada se recorta en silencio.
"""
from __future__ import annotations

import difflib
import hashlib
import html
import json
import os
import pwd
import re
import secrets
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

# SOLO IPv4 hacia Telegram. La Pi tiene ruta IPv6 por defecto (RA del router, wlan0) pero
# api.telegram.org no responde por ahi: urllib prueba IPv6 primero, espera el timeout
# entero y recien cae a IPv4 (0,2 s). Medido el 27-09: 21 s por cada mensaje del bot,
# que es justo lo que hace incomodo aprobar. curl no lo sufre porque hace happy eyeballs.
_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: ([r for r in _getaddrinfo(*a, **k)
                                       if r[0] == socket.AF_INET] or _getaddrinfo(*a, **k))

SPOOL = Path("/var/spool/nodo-desplegar")
PEDIDOS = SPOOL / "pedidos"        # root:dcifu004 1730 — el grupo crea, no lista ni lee
RESULTADOS = SPOOL / "resultados"  # root 755, archivos 644 — lo lee `esperar`
ESTADO = Path("/var/lib/nodo-desplegar")  # root 700: staging, probar, pendientes
# En carpeta propia: la unidad la deja como UNICO lugar escribible bajo /etc/nodo, asi el
# escucha puede reemplazarla atomicamente (alta) sin poder tocar avisos.env ni panico.env.
CATALOGO = Path("/etc/nodo/desplegar/catalogo.toml")
ENV = Path("/etc/nodo/avisos.env")
VAULT = Path("/opt/nodo/datos/srv/vault_personal")
RESPALDOS = Path("/opt/nodo/datos/botv3/deploy-backups")
SSH_DESTINO = "usuario@nodo.example"  # `sugerir`: desde Termux en el S22, por Tailscale SSH

VENCE_S = 30 * 60
ESPERA_SYNC_S = 3 * 60
MAX_PEDIDO = 16 * 1024
# El ejecutable arm64 de go-librespot v0.10.5 ya extraído mide más de 17 MB. El límite deja
# margen sólo para ese binario publicado, no para convertir al escucha en instalador genérico.
MAX_FUENTE = 24 * 1024 * 1024
MAX_MENSAJE = 4000
MAX_SALIDA = 1500
PROBAR_MAX_S = 120

# `consultar`: de 2 a 4 alternativas, cada una con su letra y su boton.
LETRAS = "ABCD"
RE_CLAVE = re.compile(r"[a-z]{1,12}")
MAX_ETIQUETA = 80
MAX_BOTON = 32               # lo que se lee entero en un boton del telefono

# `enviar`: lo que puede salir como documento. Lista de lo que SI va, no de lo que no.
ENVIAR_EXT = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
              ".jpeg": "image/jpeg", ".webp": "image/webp", ".md": "text/markdown",
              ".txt": "text/plain", ".html": "text/html"}
ENVIAR_MAX = 20 * 1024 * 1024
ENVIAR_TOPE = 10             # envios por ventana, entre todos: el chat es uno solo
ENVIAR_VENTANA_S = 60 * 60
ENVIAR_ESPERA_S = 120        # subir 20 MB por el wifi de la casa
ENVIAR_PROHIBIDOS = ("secretos", ".git", ".obsidian")
MAX_RUTA = 1024
MONTAJE = Path("/opt/nodo/datos")
# El kernel lo sortea en cada arranque del equipo: dice si dos lecturas del reloj monotonico
# (el que mide el tope de `enviar`) se pueden restar.
ARRANQUE = Path("/proc/sys/kernel/random/boot_id")

PERMITIDOS = ("/etc/systemd/system/", "/etc/systemd/user/", "/usr/local/bin/", "/usr/local/lib/go-librespot/",
              "/opt/nodo/", "/opt/botv3/", "/opt/captura/")
# No quedan excepciones de archivo único: Spotify usa el prefijo de /etc/systemd/user.
PERMITIDOS_EXACTOS: set[str] = set()
PROHIBIDOS = ("/etc/sudoers", "/etc/pam.d", "/etc/ssh", "/etc/nodo", "/etc/fstab",
              "/etc/crypttab", "/etc/passwd", "/etc/shadow", "/etc/group", "/root",
              "/opt/nodo/datos/secretos", "/opt/nodo/datos/srv", "/opt/nodo/.env",
              "/usr/local/bin/nodo-desplegar", "/etc/systemd/system/desplegar-escucha")
MODOS = {"0644", "0755", "0600", "0700"}
DUEÑOS = {"root:root", "dcifu004:dcifu004"}
RUTAS_DUEÑO_USUARIO = {
    "/opt/nodo/datos/spotify/jaime/config.yml",
    "/opt/nodo/datos/spotify/pilar/config.yml",
}
ENLACES_PERMITIDOS = {
    "/usr/local/bin/go-librespot": "/usr/local/lib/go-librespot/v0.10.5/go-librespot",
}

RE_NOMBRE = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
RE_HASH = re.compile(r"[0-9a-f]{8,64}")
RE_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")
RE_UNIDAD = re.compile(r"[A-Za-z0-9@_.-]{1,64}\.(service|timer|path|socket)")
RE_ARG = re.compile(r"[A-Za-z0-9._=/:,@+-]{0,64}")
RE_ARRANQUE = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")
RE_FUENTE = re.compile(r"[\w ./()@-]{1,200}")
RE_TEMPORAL = re.compile(r"\.[^/]+\.nodo-desplegar-[0-9a-f]{16}")
RE_CLAVES_UNIDAD = re.compile(
    r"^\s*-?(ExecStart\w*|ExecStop\w*|User|Group|DynamicUser|SupplementaryGroups|"
    r"AmbientCapabilities|CapabilityBoundingSet|NoNewPrivileges|ProtectSystem|ProtectHome|"
    r"PrivateTmp|ReadWritePaths|InaccessiblePaths|BindPaths|BindReadOnlyPaths)\s*=")
RE_SECRETO = re.compile(r"(?i)((?:token|key|secret|password|passwd|pass|api)[\w-]*\s*[=:]\s*)\S+")
# Sin "/" y no a mitad de una ruta: la primera version tapaba la ruta del respaldo
# (/opt/nodo/datos/botv3/deploy-backups/desplegar-<id>) como si fuera un token.
# Un SHA-256 de una tarjeta de despliegue es justamente la prueba verificable que se pide;
# los demás blobs largos se siguen ocultando como posible secreto.
RE_LARGO = re.compile(r"(?<![\w/.-])(?<!sha256 )[A-Za-z0-9+_=-]{32,}")


# ─────────────────────────── lado de la IA (sin root) ───────────────────────────

def _sacar(args: list[str], flag: str, n: int | None = 1) -> tuple[list[str], list[str]]:
    """Saca `flag` y sus valores de args. n=None: hasta el proximo --flag o el final."""
    if flag not in args:
        return args, []
    i = args.index(flag)
    if n is None:
        j = next((k for k in range(i + 1, len(args)) if args[k].startswith("--")), len(args))
    else:
        j = i + 1 + n
    return args[:i] + args[j:], args[i + 1:j]


def _entrada(txt: str) -> dict:
    nombre, _, h = txt.partition("=")
    if not RE_NOMBRE.fullmatch(nombre) or (h and not RE_HASH.fullmatch(h)):
        raise SystemExit(f"entrada invalida: {txt!r} (nombre[=sha256 de 8+ hex])")
    return {"nombre": nombre, "hash": h}


def _dejar(pedido: dict) -> int:
    pid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    cuerpo = json.dumps(pedido).encode()
    if len(cuerpo) > MAX_PEDIDO:
        raise SystemExit("pedido demasiado grande")
    tmp = PEDIDOS / f".{pid}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(cuerpo)
    os.rename(tmp, PEDIDOS / f"{pid}.json")
    print(pid)
    return 0


def pedir(args: list[str]) -> int:
    args, motivo = _sacar(args, "--motivo", None)
    if not args:
        raise SystemExit("uso: nodo-desplegar pedir <entrada>[=<sha256>]... [--motivo T]")
    return _dejar({"tipo": "desplegar", "entradas": [_entrada(a) for a in args],
                   "motivo": " ".join(motivo)[:200]})


def probar(args: list[str]) -> int:
    extra = []
    if "--" in args:
        i = args.index("--")
        args, extra = args[:i], args[i + 1:]
    args, motivo = _sacar(args, "--motivo", None)
    if len(args) != 1 or len(extra) > 8 or not all(RE_ARG.fullmatch(a) for a in extra):
        raise SystemExit("uso: nodo-desplegar probar <entrada>[=<sha256>] [--motivo T] [-- ARGS]")
    return _dejar({"tipo": "probar", "entradas": [_entrada(args[0])], "args": extra,
                   "motivo": " ".join(motivo)[:200]})


def alta(args: list[str]) -> int:
    args, motivo = _sacar(args, "--motivo", None)
    args, despues = _sacar(args, "--despues", None)
    args, modo = _sacar(args, "--modo")
    args, dueno = _sacar(args, "--dueno")
    if len(args) != 3:
        raise SystemExit("uso: nodo-desplegar alta <nombre> <fuente> <destino> "
                         "[--modo 0755] [--dueno USER:GROUP] [--despues ACC...] [--motivo T]")
    nombre, fuente, destino = args
    return _dejar({"tipo": "alta", "entradas": [_entrada(nombre)],
                   "alta": {"fuente": fuente, "destino": destino,
                            "modo": modo[0] if modo else "0644",
                            "dueno": dueno[0] if dueno else "root:root", "despues": despues},
                   "motivo": " ".join(motivo)[:200]})


def alta_enlace(args: list[str]) -> int:
    args, motivo = _sacar(args, "--motivo", None)
    if len(args) != 3:
        raise SystemExit("uso: nodo-desplegar alta-enlace <nombre> <destino> <objetivo> [--motivo T]")
    nombre, destino, objetivo = args
    try:
        validar_enlace(Path(destino), objetivo)
    except ValueError as e:
        raise SystemExit(f"nodo-desplegar alta-enlace: {e}")
    return _dejar({"tipo": "alta_enlace", "entradas": [_entrada(nombre)],
                   "alta": {"tipo": "enlace", "destino": destino, "objetivo": objetivo},
                   "motivo": " ".join(motivo)[:200]})


def sugerir(args: list[str]) -> int:
    # A Diego le cuesta escribir en tmux desde el telefono (27-09): lo que tenga que correr
    # el va como linea exacta, completa y sin placeholders, para copiar con un toque.
    if "--" not in args:
        raise SystemExit("uso: nodo-desplegar sugerir [--motivo T] -- <comando en una linea>")
    i = args.index("--")
    _, motivo = _sacar(args[:i], "--motivo", None)
    comando = " ".join(args[i + 1:]).strip()
    if not comando or "\n" in comando or len(comando) > 1000:
        raise SystemExit("el comando tiene que ser UNA linea, de hasta 1000 caracteres")
    if re.search(r"<[a-z_ -]+>|\bXXX\b|\bTODO\b", comando):
        raise SystemExit("el comando tiene un placeholder: Diego no completa nada a mano")
    return _dejar({"tipo": "sugerir", "entradas": [], "comando": comando,
                   "motivo": " ".join(motivo)[:200]})


def validar_opciones(opciones) -> list[dict]:
    """Las alternativas de `consultar` (regla 10), igual en el CLI y en el escucha. Se rechaza
    la lista entera si algo no calza: nada se recorta."""
    if not isinstance(opciones, list) or not 2 <= len(opciones) <= len(LETRAS):
        raise ValueError(f"van de 2 a {len(LETRAS)} opciones")
    out = []
    # El error nombra la opción por su número y nunca lleva lo recibido: en el escucha termina en el
    # resultado 644 y en el journal, fuera del cifrado, y root no confía en el spool (71r1).
    for n, o in enumerate(opciones, 1):
        clave, etiqueta = (o.get("clave"), o.get("etiqueta")) if isinstance(o, dict) else (None, None)
        if not isinstance(clave, str) or not RE_CLAVE.fullmatch(clave):
            raise ValueError(f"opción {n}: clave inválida (de 1 a 12 letras a-z)")
        if clave in (x["clave"] for x in out):
            raise ValueError(f"opción {n}: clave repetida")
        if not isinstance(etiqueta, str) or not etiqueta.strip() or len(etiqueta) > MAX_ETIQUETA \
                or not etiqueta.isprintable() or any(c in etiqueta for c in "<>`"):
            raise ValueError(f"opción {n}: etiqueta inválida (una línea imprimible, de hasta "
                             f"{MAX_ETIQUETA} caracteres, sin < > ni `)")
        out.append({"clave": clave, "etiqueta": etiqueta})
    return out


def validar_motivo_consulta(motivo) -> str:
    """El motivo de `consultar`: el tope de `sugerir` (200) y, como es la pregunta misma, no
    vacio y en una linea imprimible."""
    if not isinstance(motivo, str) or not motivo[:200].strip() or not motivo[:200].isprintable():
        raise ValueError("el motivo es la pregunta: no vacío, una línea imprimible")
    return motivo[:200]


def consultar(args: list[str]) -> int:
    uso = ("uso: nodo-desplegar consultar --motivo T --opcion CLAVE=ETIQUETA "
           f"[--opcion ...] (de 2 a {len(LETRAS)} opciones)")
    opciones = []
    while "--opcion" in args:
        args, valor = _sacar(args, "--opcion")
        clave, igual, etiqueta = (valor or [""])[0].partition("=")
        if not igual:
            raise SystemExit(uso)
        opciones.append({"clave": clave, "etiqueta": etiqueta})
    args, motivo = _sacar(args, "--motivo", None)
    if args:
        raise SystemExit(uso)
    try:
        pedido = {"tipo": "consulta", "entradas": [], "motivo": validar_motivo_consulta(" ".join(motivo)),
                  "opciones": validar_opciones(opciones)}
    except ValueError as e:
        raise SystemExit(f"nodo-desplegar consultar: {e}")
    return _dejar(pedido)


def enviar(args: list[str]) -> int:
    # El pedido lleva la RUTA y nada mas: el archivo lo lee el escucha. La validacion de aca
    # es solo para fallar antes y con un mensaje claro; la que vale es la del lado root.
    args, motivo = _sacar(args, "--motivo", None)
    if len(args) != 1:
        raise SystemExit("uso: nodo-desplegar enviar <ruta> [--motivo T]")
    ruta = os.path.join(os.getcwd(), args[0])
    try:
        validar_ruta_envio(ruta)
        if not os.path.isfile(ruta):
            raise ValueError("no existe o no es un archivo")
    except ValueError as e:
        raise SystemExit(f"no se puede enviar: {e}")
    return _dejar({"tipo": "enviar", "entradas": [], "ruta": ruta,
                   "motivo": " ".join(motivo)[:200]})


def esperar(args: list[str]) -> int:
    if not args or not RE_ID.fullmatch(args[0]):
        raise SystemExit("uso: nodo-desplegar esperar <id> [--max SEG]")
    _, tope = _sacar(args, "--max")
    ruta = RESULTADOS / f"{args[0]}.json"
    fin = time.time() + (int(tope[0]) if tope else VENCE_S + ESPERA_SYNC_S + 60)
    while time.time() < fin:
        if ruta.exists():
            r = json.loads(ruta.read_text())
            print(json.dumps(r, ensure_ascii=False, indent=1))
            return {"aplicado": 0, "hecho": 0, "probado": 0 if r.get("rc") == 0 else 1,
                    "sin cambios": 4}.get(r.get("estado"), 1)
        time.sleep(2)
    print(json.dumps({"id": args[0], "estado": "sin respuesta todavia"}))
    return 3


def catalogo(_args: list[str]) -> int:
    # El catalogo es root 600; esta copia publica la deja el escucha al arrancar y en cada alta.
    ruta = SPOOL / "catalogo.json"
    print(ruta.read_text() if ruta.exists() else "el escucha todavia no publico el catalogo")
    return 0


# ─────────────────────────────── lado root ───────────────────────────────

def log(msg: str) -> None:
    subprocess.run(["logger", "-t", "nodo-desplegar", msg], check=False)


def cargar_env() -> tuple[str, str]:
    cfg = {}
    for linea in ENV.read_text().splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            k, _, v = linea.partition("=")
            cfg[k.strip()] = v.strip()
    return cfg["TELEGRAM_TOKEN"], cfg["CHAT_ID"]


class Telegram:
    def __init__(self, token: str):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}/"

    def __call__(self, metodo: str, **params):
        return self._pedir(metodo, json.dumps(params).encode(), "application/json",
                           params.get("timeout", 0) + 20)

    def documento(self, chat: str, nombre: str, data: bytes, tipo: str, pie: str = ""):
        """sendDocument por multipart/form-data: el archivo viaja en el cuerpo."""
        # El borde es al azar en cada llamada: un pie escrito por la IA no puede cerrar su
        # parte y abrir otra (un chat_id propio, por ejemplo) sin adivinarlo.
        borde = secrets.token_hex(16)
        campos = [("chat_id", chat)] + ([("caption", pie)] if pie else [])
        cuerpo = b"".join(f'--{borde}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'
                          f"{v}\r\n".encode() for k, v in campos)
        # El nombre va en UTF-8 tal cual (asi lo mandan curl y los navegadores); la ruta ya
        # llego sin caracteres de control, y la comilla es lo unico que cerraria el campo.
        cuerpo += (f'--{borde}\r\nContent-Disposition: form-data; name="document"; '
                   f'filename="{nombre.replace(chr(34), "%22")}"\r\n'
                   f"Content-Type: {tipo}\r\n\r\n").encode() + data + f"\r\n--{borde}--\r\n".encode()
        try:
            return self._pedir("sendDocument", cuerpo, f"multipart/form-data; boundary={borde}",
                               ENVIAR_ESPERA_S)
        except Exception as e:
            # Lo que no es HTTPError (red caida, timeout) sale tal cual de urllib: se le saca el
            # token por si algun dia trae la URL (trampa 17 de IA_INSTRUCCIONES).
            texto = str(e) if isinstance(e, RuntimeError) else f"sendDocument: {type(e).__name__}: {e}"
            raise RuntimeError(texto.replace(self.token, "«token»")) from None

    def _pedir(self, metodo: str, cuerpo: bytes, tipo: str, espera: float):
        req = urllib.request.Request(self.base + metodo, data=cuerpo,
                                     headers={"Content-Type": tipo})
        try:
            with urllib.request.urlopen(req, timeout=espera) as r:
                return json.load(r)["result"]
        except urllib.error.HTTPError as e:
            cuerpo = e.read()[:300]
            if e.code == 429:
                try:
                    time.sleep(json.loads(cuerpo)["parameters"]["retry_after"])
                except (ValueError, KeyError):
                    time.sleep(5)
            # Nunca loguear la URL: lleva el token adentro.
            raise RuntimeError(f"{metodo}: HTTP {e.code} {cuerpo!r}") from None


def validar_destino(destino: Path) -> None:
    s = str(destino)
    if not destino.is_absolute() or ".." in destino.parts:
        raise ValueError(f"destino no absoluto o con ..: {s}")
    if (not s.startswith(PERMITIDOS) and s not in PERMITIDOS_EXACTOS) or s.startswith(PROHIBIDOS):
        raise ValueError(f"destino fuera de lo permitido: {s}")
    if destino.is_symlink() or any(p.is_symlink() for p in destino.parents):
        raise ValueError(f"destino con enlace simbolico: {s}")


def validar_dueno(dueno, destino: Path) -> None:
    """Sólo los dos dueños necesarios; dcifu004 sólo puede recibir sus configs Spotify."""
    if dueno not in DUEÑOS:
        raise ValueError(f"dueño no permitido: {dueno}")
    if dueno == "dcifu004:dcifu004" and str(destino) not in RUTAS_DUEÑO_USUARIO:
        raise ValueError(f"dueño dcifu004 no permitido para: {destino}")


def ids_dueno(dueno: str) -> tuple[int, int]:
    if dueno == "root:root":
        return 0, 0
    usuario = pwd.getpwnam("dcifu004")
    return usuario.pw_uid, usuario.pw_gid


def validar_enlace(destino: Path, objetivo: str) -> None:
    """El único enlace instalable está fijado junto con la versión del binario Spotify."""
    if ENLACES_PERMITIDOS.get(str(destino)) != objetivo:
        raise ValueError("enlace fuera de la lista cerrada")


def abrir_directorio(ruta: Path, crear: bool = False) -> int:
    """Abre cada tramo por descriptor, sin seguir enlaces que un usuario pueda intercambiar.

    El descriptor resultante ancla las operaciones posteriores aunque alguien renombre una
    carpeta mientras se prepara el despliegue. Sólo se llama después de validar la ruta textual.
    """
    if not ruta.is_absolute():
        raise ValueError("directorio no absoluto")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for tramo in ruta.parts[1:]:
            try:
                nuevo = os.open(tramo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not crear:
                    raise
                try:
                    os.mkdir(tramo, 0o755, dir_fd=fd)
                except FileExistsError:
                    pass
                nuevo = os.open(tramo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nuevo
        return fd
    except Exception:
        os.close(fd)
        raise


def leer_destino(destino: Path) -> bytes | None:
    """Lee un destino existente por descriptores; un enlace nunca llega al diff ni al respaldo."""
    try:
        padre = abrir_directorio(destino.parent)
    except FileNotFoundError:
        return None
    try:
        try:
            # Primero se mira el nombre sin seguirlo. Abrir un FIFO en modo lectura antes de
            # saber qué es espera a un escritor y deja colgado al único escucha.
            esperado = os.stat(destino.name, dir_fd=padre, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(esperado.st_mode) or esperado.st_nlink != 1:
            raise ValueError(f"destino no es archivo regular seguro: {destino}")
        try:
            fd = os.open(destino.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=padre)
        except FileNotFoundError:
            return None
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or (st.st_dev, st.st_ino) != (esperado.st_dev, esperado.st_ino)):
                raise ValueError(f"destino no es archivo regular seguro: {destino}")
            with os.fdopen(fd, "rb", closefd=False) as fh:
                return fh.read()
        finally:
            os.close(fd)
    finally:
        os.close(padre)


def leer_enlace(destino: Path) -> str | None:
    try:
        padre = abrir_directorio(destino.parent)
    except FileNotFoundError:
        return None
    try:
        try:
            return os.readlink(destino.name, dir_fd=padre)
        except FileNotFoundError:
            return None
    finally:
        os.close(padre)


def escribir_destino(destino: Path, data: bytes, uid: int, gid: int, modo: int,
                      privado: bool = False) -> None:
    """Escritura atómica sin seguir enlaces.

    Los únicos directorios controlados por ``dcifu004`` son los dos perfiles Spotify. Tras
    anclarlos por descriptor, el archivo se crea con su identidad efectiva: aun si cambia un
    nombre por enlace, no queda un escritor root sobre una ruta de root.
    """
    padre = abrir_directorio(destino.parent, crear=True)
    try:
        if privado:
            os.fchown(padre, uid, gid)
            os.fchmod(padre, 0o700)
        else:
            st = os.fstat(padre)
            if st.st_uid != 0 or stat.S_IMODE(st.st_mode) & 0o022:
                raise ValueError(f"directorio root no seguro: {destino.parent}")
        previo_uid, previo_gid = os.geteuid(), os.getegid()
        if privado:
            os.setegid(gid)
            os.seteuid(uid)
        try:
            tmp = f".{destino.name}.nodo-desplegar-{secrets.token_hex(8)}"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         modo, dir_fd=padre)
            try:
                escritos = 0
                while escritos < len(data):
                    escritos += os.write(fd, data[escritos:])
                os.fsync(fd)
                os.fchmod(fd, modo)
            finally:
                os.close(fd)
            os.replace(tmp, destino.name, src_dir_fd=padre, dst_dir_fd=padre)
            os.fsync(padre)
        finally:
            if privado:
                os.seteuid(previo_uid)
                os.setegid(previo_gid)
    finally:
        os.close(padre)


def crear_enlace(destino: Path, objetivo: str) -> None:
    validar_enlace(destino, objetivo)
    # Se comprueba el binario ya instalado con la misma apertura sin enlaces antes de publicar
    # el enlace. El directorio de /usr/local/bin tiene que seguir siendo root y no escribible.
    binario = Path(objetivo)
    datos = leer_destino(binario)
    if datos is None:
        raise ValueError("el binario objetivo no existe")
    padre = abrir_directorio(destino.parent, crear=True)
    try:
        st = os.fstat(padre)
        if st.st_uid != 0 or stat.S_IMODE(st.st_mode) & 0o022:
            raise ValueError(f"directorio root no seguro: {destino.parent}")
        tmp = f".{destino.name}.nodo-desplegar-{secrets.token_hex(8)}"
        os.symlink(objetivo, tmp, dir_fd=padre)
        os.replace(tmp, destino.name, src_dir_fd=padre, dst_dir_fd=padre)
        os.fsync(padre)
    finally:
        os.close(padre)


def validar_despues(acciones: list) -> None:
    for d in acciones:
        if not isinstance(d, str) or (d != "daemon-reload" and not (
                d.startswith("restart:") and RE_UNIDAD.fullmatch(d[8:]))):
            raise ValueError(f"accion no permitida: {d}")


def leer_fuente(relativa: str) -> bytes:
    """Lee una fuente del vault como root sin seguir enlaces fuera de el (regla 2)."""
    if (not RE_FUENTE.fullmatch(relativa) or Path(relativa).is_absolute()
            or ".." in relativa.split("/")):
        raise ValueError(f"fuente invalida: {relativa}")
    if not os.path.ismount("/opt/nodo/datos"):
        raise ValueError("el volumen cifrado está cerrado: corre sudo abrir-datos")
    fd = os.open(VAULT / relativa, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        real = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if not real.is_relative_to(VAULT.resolve()) or "secretos" in real.parts \
                or real.name.endswith(".env") or not os.path.isfile(real):
            raise ValueError(f"fuente no permitida: {relativa}")
        data = os.read(fd, MAX_FUENTE + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_FUENTE:
        raise ValueError(f"fuente demasiado grande: {relativa}")
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def validar_ruta_envio(ruta) -> None:
    """Lo que se decide con el TEXTO de la ruta, antes de tocar el disco: asi una ruta de
    afuera del vault no llega ni a un stat, y root no le cuenta a nadie que existe."""
    if not isinstance(ruta, str) or not 0 < len(ruta) <= MAX_RUTA \
            or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in ruta):
        raise ValueError("ruta inválida (vacía, larguísima o con caracteres de control)")
    if not ruta.startswith("/"):
        raise ValueError("la ruta tiene que ser absoluta")
    partes = ruta.split("/")[1:]
    if ".." in partes:
        raise ValueError("la ruta lleva «..»")
    if "" in partes or "." in partes:
        raise ValueError("la ruta lleva «//», «/./» o termina en «/»")
    base = VAULT.parts[1:]
    if tuple(partes[:len(base)]) != base or len(partes) == len(base):
        raise ValueError(f"fuera del vault personal ({VAULT}/)")
    for tramo in partes[len(base):]:
        if tramo.casefold() in ENVIAR_PROHIBIDOS:
            raise ValueError(f"«{tramo}» no se envía")
        if tramo.startswith("."):
            raise ValueError(f"lo oculto no se envía: «{tramo}»")
    ext = Path(partes[-1]).suffix.lower()
    if ext not in ENVIAR_EXT:
        raise ValueError(f"extensión no permitida: «{ext or 'sin extensión'}» "
                         f"(van {' '.join(ENVIAR_EXT)})")


def leer_envio(ruta) -> bytes:
    """Lee como root el archivo de `enviar` (regla 9). Cada tramo se abre desde el anterior
    con O_NOFOLLOW: la ruta pedida ES la real, o no se abre. El lstat previo solo sirve para
    decir por que; lo que niega es el open."""
    validar_ruta_envio(ruta)
    if not os.path.ismount(MONTAJE):
        raise ValueError("el volumen cifrado está cerrado: corre sudo abrir-datos")
    partes = ruta.split("/")[1:]
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for i, tramo in enumerate(partes):
            ultimo = i == len(partes) - 1
            hasta = "/" + "/".join(partes[:i + 1])
            try:
                st = os.stat(tramo, dir_fd=fd, follow_symlinks=False)
            except OSError:
                raise ValueError(f"no existe: {hasta}") from None
            if stat.S_ISLNK(st.st_mode):
                raise ValueError(f"enlace simbólico en la ruta: {hasta}")
            if ultimo and stat.S_ISDIR(st.st_mode):
                raise ValueError("es un directorio, no un archivo")
            if not (stat.S_ISREG if ultimo else stat.S_ISDIR)(st.st_mode):
                raise ValueError(f"no es {'un archivo regular' if ultimo else 'una carpeta'}: {hasta}")
            # O_NONBLOCK: un FIFO con nombre de .pdf no deja colgado al escucha.
            try:
                nuevo = os.open(tramo, os.O_RDONLY | os.O_NOFOLLOW | (
                    os.O_NONBLOCK if ultimo else os.O_DIRECTORY), dir_fd=fd)
            except OSError as e:
                raise ValueError(f"no se pudo abrir sin seguir enlaces: {hasta} ({e.strerror})") from None
            os.close(fd)
            fd = nuevo
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("no es un archivo regular")
        # Un enlace duro no es un tramo de la ruta: es el mismo archivo con otro nombre, que
        # puede estar fuera del vault. protected_hardlinks ya lo frena; esto no depende de eso.
        if st.st_nlink != 1:
            raise ValueError("el archivo tiene enlaces duros")
        if os.readlink(f"/proc/self/fd/{fd}") != ruta:
            raise ValueError("la ruta cambió mientras se abría")
        if st.st_size > ENVIAR_MAX:
            raise ValueError(f"pesa {st.st_size / 1048576:.1f} MB; el tope es "
                             f"{ENVIAR_MAX // 1048576} MB")
        data = b""
        while len(data) <= ENVIAR_MAX:
            trozo = os.read(fd, ENVIAR_MAX + 1 - len(data))
            if not trozo:
                break
            data += trozo
    finally:
        os.close(fd)
    if len(data) > ENVIAR_MAX:
        raise ValueError(f"pesa más de {ENVIAR_MAX // 1048576} MB")
    if not data:
        raise ValueError("el archivo está vacío")
    return data


def leer_arranque() -> str:
    """El boot_id de este arranque del equipo, o "" si no se puede leer."""
    try:
        txt = ARRANQUE.read_text().strip()
    except (OSError, ValueError):
        return ""
    return txt if RE_ARRANQUE.fullmatch(txt) else ""


def enmascarar(texto: str) -> str:
    return RE_LARGO.sub("«oculto»", RE_SECRETO.sub(r"\1«oculto»", texto))


def marcas(destino: Path, actual: bytes | None, nuevo: bytes) -> list[str]:
    unidad = destino.suffix in (".service", ".timer", ".path", ".socket")
    viejas = set((actual or b"").decode(errors="replace").splitlines())
    nuevas = set(nuevo.decode(errors="replace").splitlines())
    claves = [l for l in sorted(viejas ^ nuevas) if unidad and RE_CLAVES_UNIDAD.match(l)]
    if actual is None:
        # Un archivo nuevo es UNA marca, no una por cada ExecStart (ruido de la prueba).
        extra = f" ({', '.join(l.split('=')[0].strip() for l in claves)})" if claves else ""
        return [f"archivo NUEVO: {destino}{extra}"]
    return [("+ " if l in nuevas else "− ") + l.strip()[:70] for l in claves][:6]


class Escucha:
    def __init__(self):
        token, self.chat = cargar_env()
        self.tg = Telegram(token)
        for d in (ESTADO / "staging", ESTADO / "probar", ESTADO / "respaldos"):
            d.mkdir(parents=True, exist_ok=True, mode=0o700)
        guardado = self._leer(ESTADO / "pendientes.json") or {}
        self.pend: dict[str, dict] = guardado.get("pend", {})
        self.espera: dict[str, dict] = guardado.get("espera", {})
        self.offset = guardado.get("offset", 0)
        # Sin boot_id no se sabe si el equipo reinicio: cada arranque del escucha cuenta como
        # uno del equipo. Es de mas, nunca de menos.
        self.arranque = leer_arranque() or f"sin-boot-id-{secrets.token_hex(8)}"
        self.envios = self.recuperar_envios(guardado)
        if self.envios and guardado.get("arranque") != self.arranque:
            # Queda anotado ya en este arranque: si el escucha cae de nuevo antes del proximo
            # pedido, la ventana no vuelve a partir de cero.
            self.guardar()
            log(f"otro arranque del equipo: {len(self.envios)} cupo(s) de enviar se conservan "
                f"{ENVIAR_VENTANA_S // 60} min más")
        self.limpiar_temporales()
        self.publicar_catalogo()

    @staticmethod
    def _leer(ruta: Path):
        try:
            return json.loads(ruta.read_text())
        except (OSError, ValueError):
            return None

    def recuperar_envios(self, guardado: dict) -> list[dict]:
        """Los cupos de `enviar` que quedaron guardados (regla 9). `m` es time.monotonic(), que
        se puede restar solo dentro del arranque del equipo en que se anoto. Si este arranque es
        otro, no hay como saber cuanto paso mientras tanto, y la hora de pared no lo dice: cada
        cupo se conserva una ventana entera desde ahora. Un cupo de mas de una hora es el costo;
        diez envios de regalo por cada correccion de NTP era la alternativa."""
        ahora = time.monotonic()
        mismo = guardado.get("arranque") == self.arranque
        envios = []
        for e in guardado.get("envios", []):
            m = e.get("m")
            # `not m <= ahora` y no `m > ahora`: asi un NaN tampoco pasa por anotado hace mucho.
            if not mismo or isinstance(m, bool) or not isinstance(m, (int, float)) \
                    or not m <= ahora:
                m = ahora
            envios.append({"m": m, "id": e.get("id")})
        return envios

    def guardar(self) -> None:
        """Cuando vuelve, el estado esta EN EL DISCO y no solo en la cache del kernel: fsync
        del archivo antes de renombrarlo y de la carpeta despues, en ese orden. El cupo de
        `enviar` se anota con esto justo antes de llamar a Telegram (regla 9); sin los fsync,
        un corte de luz volvia con el pendientes.json anterior, regalaba cupos y podia repetir
        un envio. Si un fsync falla, esto falla: no se sigue con un estado sin confirmar."""
        ruta = ESTADO / "pendientes.json"
        tmp = ruta.with_suffix(".tmp")
        with open(tmp, "w") as fh:
            fh.write(json.dumps({"pend": self.pend, "espera": self.espera,
                                 "offset": self.offset, "envios": self.envios,
                                 "arranque": self.arranque},
                                ensure_ascii=False))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, ruta)
        fd = os.open(ESTADO, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def cat(self) -> dict:
        return tomllib.loads(CATALOGO.read_text()).get("entrada", {})

    def publicar_catalogo(self) -> None:
        pub = {n: ({"tipo": "enlace", "destino": e["destino"], "objetivo": e["objetivo"]}
                   if e.get("tipo") == "enlace" else
                   {"fuente": e["fuente"], "destino": e["destino"],
                    "dueno": e.get("dueno", "root:root"),
                    "modo": e.get("modo", "0644"), "despues": e.get("despues", [])})
               for n, e in self.cat().items()}
        ruta = SPOOL / "catalogo.json"
        ruta.write_text(json.dumps(pub, ensure_ascii=False, indent=1))
        os.chmod(ruta, 0o644)

    def limpiar_temporales(self) -> None:
        """Quita sólo los temporales huérfanos que este escucha pudo dejar al caer.

        Se deriva cada carpeta del catálogo (más el único enlace cerrado), en vez de recorrer
        árboles amplios como /opt/nodo. No se sigue ningún enlace al abrir o borrar.
        """
        entradas = list(self.cat().values()) + [
            {"destino": destino} for destino in ENLACES_PERMITIDOS
        ]
        padres: set[Path] = set()
        for entrada in entradas:
            destino = Path(entrada.get("destino", ""))
            # validar_destino() rechaza acertadamente el enlace ya publicado. Acá sólo se
            # necesita decidir si su carpeta es una de las autorizadas; abrir_directorio()
            # vuelve a verificar cada tramo sin seguir enlaces antes de borrar nada.
            s = str(destino)
            if (not destino.is_absolute() or ".." in destino.parts
                    or (not s.startswith(PERMITIDOS) and s not in PERMITIDOS_EXACTOS)
                    or s.startswith(PROHIBIDOS)):
                continue
            padres.add(destino.parent)
        borrados = 0
        for padre_ruta in padres:
            try:
                padre = abrir_directorio(padre_ruta)
            except (FileNotFoundError, NotADirectoryError):
                continue
            try:
                for nombre in os.listdir(padre):
                    if not RE_TEMPORAL.fullmatch(nombre):
                        continue
                    try:
                        st = os.stat(nombre, dir_fd=padre, follow_symlinks=False)
                        if stat.S_ISREG(st.st_mode) and st.st_nlink == 1:
                            os.unlink(nombre, dir_fd=padre)
                            borrados += 1
                    except FileNotFoundError:
                        pass
            finally:
                os.close(padre)
        if borrados:
            log(f"limpié {borrados} temporal(es) huérfano(s) de nodo-desplegar")

    # ── pedidos ──
    def procesar_pedidos(self) -> None:
        for f in sorted(PEDIDOS.iterdir()):
            if f.name.startswith(".") or not f.name.endswith(".json"):
                continue
            pid = f.name[:-5]
            try:
                st = f.lstat()
                fd = os.open(f, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as fh:
                    crudo = fh.read(MAX_PEDIDO + 1)
                f.unlink()
                if not RE_ID.fullmatch(pid) or len(crudo) > MAX_PEDIDO:
                    raise ValueError("pedido mal formado")
                self.espera[pid] = {"datos": json.loads(crudo), "uid": st.st_uid,
                                    "desde": time.time()}
                self.guardar()
            except Exception as e:  # un pedido malo no tumba al escucha
                f.unlink(missing_ok=True)
                # El error puede traer algo del spool: enmascarado, como lo que deja cerrar() (71r1).
                self.resultado(pid, "rechazado", enmascarar(f"pedido invalido: {e}"))
                log(enmascarar(f"{pid}: pedido invalido: {e}"))
        for pid, w in list(self.espera.items()):
            try:
                if self.preparar(pid, w["uid"], w["datos"], w["desde"]):
                    del self.espera[pid]
                    self.guardar()
            except Exception as e:
                del self.espera[pid]
                self.guardar()
                shutil.rmtree(ESTADO / "staging" / pid, ignore_errors=True)
                self.resultado(pid, "rechazado", enmascarar(str(e)))
                log(enmascarar(f"{pid}: rechazado al preparar: {e}"))

    def preparar(self, pid: str, uid: int, datos: dict, desde: float) -> bool:
        """Devuelve False si todavia espera a Syncthing; True si ya se resolvio."""
        tipo = datos.get("tipo")
        if tipo == "sugerir":
            return self.preparar_sugerencia(pid, uid, datos)
        if tipo == "enviar":
            return self.preparar_envio(pid, uid, datos)
        if tipo == "consulta":
            return self.preparar_consulta(pid, uid, datos)
        entradas = datos.get("entradas")
        if tipo not in ("desplegar", "probar", "alta", "alta_enlace") or not isinstance(entradas, list) \
                or not 1 <= len(entradas) <= 10 or (tipo != "desplegar" and len(entradas) != 1):
            raise ValueError("pedido mal formado")
        cat = self.cat()
        rojos: list[str] = []
        if tipo in ("alta", "alta_enlace"):
            a = datos.get("alta") or {}
            nombre = entradas[0]["nombre"]
            if nombre in cat:
                raise ValueError(f"'{nombre}' ya existe en el catálogo")
            destino_alta = Path(a.get("destino", ""))
            validar_destino(destino_alta)
            if tipo == "alta_enlace":
                if a.get("tipo") != "enlace":
                    raise ValueError("alta de enlace inválida")
                validar_enlace(destino_alta, a.get("objetivo", ""))
                cat = {nombre: {"tipo": "enlace", "destino": a["destino"],
                                "objetivo": a["objetivo"]}}
            else:
                if a.get("modo") not in MODOS:
                    raise ValueError(f"modo no permitido: {a.get('modo')}")
                validar_dueno(a.get("dueno", "root:root"), destino_alta)
                validar_despues(a.get("despues", []))
                cat = {nombre: {"fuente": a["fuente"], "destino": a["destino"], "modo": a["modo"],
                                "dueno": a.get("dueno", "root:root"), "despues": a.get("despues", [])}}
            rojos.append(f"ALTA en el catálogo: {nombre} → {a['destino']}")

        items, diffs, cambios = [], [], 0
        for ent in entradas:
            n, esperado = ent.get("nombre"), ent.get("hash", "")
            if n not in cat:
                raise ValueError(f"'{n}' no está en el catálogo")
            e = cat[n]
            destino = Path(e["destino"])
            if e.get("tipo") == "enlace":
                if tipo == "probar":
                    raise ValueError("no se puede probar un enlace como ejecutable")
                validar_enlace(destino, e.get("objetivo", ""))
                objetivo = e["objetivo"]
                h = hashlib.sha256(objetivo.encode()).hexdigest()
                if esperado and not h.startswith(esperado):
                    if time.time() - desde > ESPERA_SYNC_S:
                        raise ValueError(f"{n}: el hash pedido no corresponde al enlace (es {h[:12]})")
                    return False
                actual_enlace = leer_enlace(destino)
                # El enlace instalado es el único caso válido en que el destino es un enlace.
                # Se mira antes de validar_destino(), que correctamente rechaza enlaces para
                # archivos normales. Uno distinto no se reemplaza silenciosamente.
                if actual_enlace is not None and actual_enlace != objetivo:
                    raise ValueError(f"enlace existente apunta a otro objetivo: {destino}")
                if actual_enlace is None:
                    validar_destino(destino)
                items.append({"nombre": n, "tipo": "enlace", "destino": str(destino), "hash": h,
                              "objetivo": objetivo, "modo": 0, "dueno": "root:root", "despues": [],
                              "igual": actual_enlace == objetivo})
                if actual_enlace != objetivo:
                    cambios += 1
                    diffs.append(f"enlace {destino} → {objetivo}")
                continue
            validar_destino(destino)
            validar_dueno(e.get("dueno", "root:root"), destino)
            validar_despues(e.get("despues", []))
            nuevo = leer_fuente(e["fuente"])
            h = hashlib.sha256(nuevo).hexdigest()
            if esperado and not h.startswith(esperado):
                if time.time() - desde > ESPERA_SYNC_S:
                    raise ValueError(f"{n}: la versión pedida no llegó por Syncthing en "
                                     f"{ESPERA_SYNC_S // 60} min (el vault tiene {h[:12]})")
                return False
            actual = leer_destino(destino)
            items.append({"nombre": n, "tipo": "archivo", "destino": str(destino), "hash": h,
                          "modo": int(e.get("modo", "0644"), 8),
                          "dueno": e.get("dueno", "root:root"),
                          "despues": e.get("despues", []), "igual": actual == nuevo})
            stage = ESTADO / "staging" / pid
            stage.mkdir(mode=0o700, exist_ok=True)
            (stage / n).write_bytes(nuevo)
            if actual == nuevo:
                continue
            cambios += 1
            rojos += marcas(destino, actual, nuevo)
            if b"\0" in nuevo or (actual is not None and b"\0" in actual):
                anterior = f", anterior sha256 {hashlib.sha256(actual).hexdigest()}" if actual is not None else ""
                diffs.append(f"binario: {len(nuevo)} bytes, sha256 {h}{anterior}")
            else:
                d = difflib.unified_diff((actual or b"").decode(errors="replace").splitlines(),
                                         nuevo.decode(errors="replace").splitlines(),
                                         f"actual {destino.name}", "nuevo", n=1, lineterm="")
                diffs.append("\n".join(list(d)[2:]))

        if cambios == 0 and tipo == "desplegar":
            shutil.rmtree(ESTADO / "staging" / pid, ignore_errors=True)
            # No es "aplicado": una IA que espera un cambio y recibe esto probablemente
            # pidio antes de que Syncthing trajera el archivo (pagado el 27-09).
            self.resultado(pid, "sin cambios", "todo igual a lo desplegado: ¿llegó ya el "
                           "archivo por Syncthing? Pide con =<sha256> para que espere.")
            return True
        try:
            quien = pwd.getpwuid(uid).pw_name
        except KeyError:
            quien = str(uid)
        p = {"id": pid, "tipo": tipo, "quien": quien, "motivo": str(datos.get("motivo", ""))[:200],
             "items": items, "rojos": rojos, "creado": time.time(),
             "nonce": secrets.token_urlsafe(9), "confirmado1": False,
             "args": [a for a in datos.get("args", []) if RE_ARG.fullmatch(a)][:8],
             "alta": cat[entradas[0]["nombre"]] if tipo in ("alta", "alta_enlace") else None}
        p["texto"] = self.texto(p, "\n\n".join(diffs) if diffs else "(sin diferencias con lo desplegado)")
        t = time.time()
        msg = self.tg("sendMessage", chat_id=self.chat, text=p["texto"], parse_mode="HTML",
                      reply_markup=self.teclado(p))
        p["msg"] = msg["message_id"]
        self.pend[pid] = p
        self.guardar()
        log(f"{pid}: {tipo} de {quien}: {[i['nombre'] for i in items]} "
            f"({len(rojos)} marcas), enviado en {time.time() - t:.1f} s")
        return True

    RIESGOS = [
        (r"curl[^|]*\|\s*(sudo\s+)?(ba|z)?sh", "baja algo de internet y lo ejecuta"),
        (r"\brm\s+-[a-z]*r[a-z]*f?\s+/(\s|$)", "borra desde la raíz"),
        (r"sudoers|visudo", "toca sudoers"),
        (r"/etc/ssh|sshd", "toca SSH"),
        (r"chmod\s+(-R\s+)?[0-7]?777", "da permisos a todo el mundo"),
        (r"base64\s+-d|\bxxd\b", "decodifica algo escondido"),
        (r"\bpasswd\b|/etc/shadow", "toca contraseñas"),
        (r"\bdd\b.*of=/dev/", "escribe un disco directo"),
    ]

    def preparar_sugerencia(self, pid: str, uid: int, datos: dict) -> bool:
        comando = str(datos.get("comando", ""))
        if not comando or "\n" in comando or len(comando) > 1000:
            raise ValueError("comando inválido")
        try:
            quien = pwd.getpwuid(uid).pw_name
        except KeyError:
            quien = str(uid)
        motivo = str(datos.get("motivo", ""))[:200]
        avisos = [txt for pat, txt in self.RIESGOS if re.search(pat, comando)]
        # La linea va COMPLETA, con la entrada a la Pi: Diego la pega en Termux, no adentro
        # de la Pi (pedido del 27-09). -t para que sudo pueda pedir la clave; la IP de
        # Tailscale y no MagicDNS, que es la que anda desde el S22.
        linea = f"ssh -t {SSH_DESTINO} {shlex.quote(comando)}"
        l = [f"🧑‍💻 <b>Para pegar en Termux</b> <code>{pid}</code>",
             f"De: {html.escape(quien)}" + (f" · {html.escape(motivo)}" if motivo else ""), "",
             "Toca el bloque para copiarlo (ya incluye la entrada a la Pi):",
             f'<pre><code class="language-bash">{html.escape(linea)}</code></pre>']
        if re.search(r"\bsudo\b", comando):
            l.append("🔑 Pide tu clave de sudo.")
        if avisos:
            l += ["", "⚠️ <b>Revísalo antes de pegar:</b> " + html.escape("; ".join(avisos)) + "."]
        l += ["", "Cuando termine, toca ✅ para que la IA verifique."]
        p = {"id": pid, "tipo": "sugerir", "quien": quien, "motivo": motivo, "items": [],
             "rojos": [], "creado": time.time(), "nonce": secrets.token_urlsafe(9),
             "confirmado1": False, "comando": comando, "texto": "\n".join(l)}
        msg = self.tg("sendMessage", chat_id=self.chat, text=p["texto"], parse_mode="HTML",
                      reply_markup=self.teclado(p))
        p["msg"] = msg["message_id"]
        self.pend[pid] = p
        self.guardar()
        log(f"{pid}: sugerir de {quien}: {comando[:120]}")
        return True

    def preparar_consulta(self, pid: str, uid: int, datos: dict) -> bool:
        """UN mensaje con las alternativas y un boton por cada una (regla 10). Del pedido solo
        se usan el motivo y las opciones, validados otra vez aca."""
        opciones = validar_opciones(datos.get("opciones"))
        motivo = validar_motivo_consulta(datos.get("motivo"))
        try:
            quien = pwd.getpwuid(uid).pw_name
        except KeyError:
            quien = str(uid)
        p = {"id": pid, "tipo": "consulta", "quien": quien, "motivo": motivo, "items": [],
             "rojos": [], "creado": time.time(), "nonce": secrets.token_urlsafe(9),
             "confirmado1": False, "opciones": opciones}
        p["texto"] = self.texto_consulta(p, f"Toca la letra que eliges. Vence en {VENCE_S // 60} min.")
        msg = self.tg("sendMessage", chat_id=self.chat, text=p["texto"], parse_mode="HTML",
                      reply_markup=self.teclado(p))
        p["msg"] = msg["message_id"]
        self.pend[pid] = p
        self.guardar()
        log(f"{pid}: consulta de {quien}: {' '.join(o['clave'] for o in opciones)}")
        return True

    @staticmethod
    def texto_consulta(p: dict, pie: str) -> str:
        l = [f"❓ <b>Consulta</b> <code>{p['id']}</code>", f"De: {html.escape(p['quien'])}", "",
             html.escape(p["motivo"]), ""]
        l += [f"{LETRAS[i]} — {html.escape(o['etiqueta'])}" for i, o in enumerate(p["opciones"])]
        return "\n".join(l + ["", pie])

    def elegir(self, p: dict, accion: str, responder) -> None:
        """El toque en una alternativa de `consultar`: `op<N>` con N el indice de la opcion."""
        m = re.fullmatch(r"op([0-9])", accion)
        if not m or int(m[1]) >= len(p["opciones"]):
            return responder("Botón inválido.")
        i = int(m[1])
        responder(f"Elegido: {LETRAS[i]}.")
        # Se saca de pendientes ANTES de escribir el resultado: un segundo toque (o un reinicio
        # a mitad) ya no lo encuentra y no se elige dos veces.
        self.pend.pop(p["id"], None)
        self.guardar()
        self.cerrar(p, "hecho", f"el usuario eligió {LETRAS[i]} ({p['opciones'][i]['clave']})", opcion=i)

    @staticmethod
    def ya_elegida(pid: str) -> str | None:
        """La letra de una consulta ya resuelta, leida de su resultado (lo escribe este mismo
        escucha), para contestar el segundo toque; None si no lo es."""
        if not RE_ID.fullmatch(pid):
            return None
        r = Escucha._leer(RESULTADOS / f"{pid}.json")
        letra = r.get("letra") if isinstance(r, dict) and r.get("estado") == "hecho" else None
        return letra if isinstance(letra, str) and len(letra) == 1 and letra in LETRAS else None

    def preparar_envio(self, pid: str, uid: int, datos: dict) -> bool:
        """Manda un archivo del vault personal al chat del usuario y deja el resultado. Del
        pedido solo se usan la ruta y el motivo; el nombre, el contenido y el chat salen de aca."""
        try:
            quien = pwd.getpwuid(uid).pw_name
        except KeyError:
            quien = str(uid)
        ruta = datos.get("ruta")
        # Lo rechazado tambien queda anotado con ruta y quien: interesa saber que se intento.
        # (La ruta pedida es texto de la IA: se anota recortada y sin nada que no sea UTF-8.)
        envio = {"ruta": (ruta if isinstance(ruta, str) else repr(ruta))[:MAX_RUTA]
                 .encode(errors="backslashreplace").decode(), "quien": quien}
        try:
            # Si el escucha murio entre mandar y anotar, el pedido sigue en espera. No se
            # reintenta: mejor un envio de menos que el mismo archivo cada 10 s de reinicio.
            if any(e["id"] == pid for e in self.envios):
                raise ValueError("el escucha se reinició a mitad de este envío y no se "
                                 "reintenta: puede haber llegado")
            data = leer_envio(ruta)
            envio |= {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            # Reloj monotonico, no time.time(): un salto de la hora de pared no vence ni un cupo.
            ahora = time.monotonic()
            self.envios = [e for e in self.envios if ahora - e["m"] < ENVIAR_VENTANA_S]
            if len(self.envios) >= ENVIAR_TOPE:
                falta = min(e["m"] for e in self.envios) + ENVIAR_VENTANA_S - ahora
                raise ValueError(f"tope de {ENVIAR_TOPE} envíos por hora; el próximo cupo "
                                 f"se libera en {int(-(-falta // 60))} min")
            # El cupo se anota ANTES de llamar y no se devuelve si Telegram falla: cuenta lo
            # que se intento mandar, y es tambien la marca de «este pedido ya salio».
            self.envios.append({"m": ahora, "id": pid})
            self.guardar()
            nombre = ruta.rsplit("/", 1)[1]
            try:
                msg = self.tg.documento(self.chat, nombre, data,
                                        ENVIAR_EXT[Path(nombre).suffix.lower()],
                                        str(datos.get("motivo", ""))[:200])
            except Exception as e:
                raise ValueError(f"Telegram no lo recibió: {enmascarar(str(e))}") from None
        except (ValueError, OSError) as e:
            self.resultado(pid, "rechazado", str(e), envio=envio)
            log(f"{pid}: enviar de {quien} rechazado: {envio['ruta'][:200]!r}: {e}")
            return True
        envio["mensaje"] = msg.get("message_id") if isinstance(msg, dict) else None
        self.resultado(pid, "hecho", f"enviado como documento: {nombre} ({len(data)} bytes)",
                       envio=envio)
        log(f"{pid}: enviar de {quien}: {ruta!r} {len(data)} bytes sha256={envio['sha256']}")
        return True

    def texto(self, p: dict, diff: str) -> str:
        titulo = {"desplegar": "📦 <b>Pedido de despliegue</b>",
                  "probar": "▶️ <b>Pedido de prueba como root</b>",
                  "alta": "🆕 <b>Alta en el catálogo</b>",
                  "alta_enlace": "🆕 <b>Alta de enlace en el catálogo</b>"}[p["tipo"]]
        l = [f"{titulo} <code>{p['id']}</code>",
             f"De: {html.escape(p['quien'])}" + (f" · {html.escape(p['motivo'])}" if p["motivo"] else ""),
             ""]
        for it in p["items"]:
            est = "sin cambios" if it["igual"] else "cambia"
            l.append(f"• <b>{it['nombre']}</b> → <code>{html.escape(it['destino'])}</code> ({est})")
            for d in it["despues"] if p["tipo"] != "probar" else []:
                l.append(f"   ↳ {html.escape(d)}")
        if p["tipo"] == "probar":
            l.append(f"   ▶️ corre la versión del vault con: <code>"
                     f"{html.escape(' '.join(p['args']) or '(sin argumentos)')}</code>")
        if p["rojos"]:
            l += ["", "🔴 <b>Marcas rojas</b> (piden doble confirmación):"]
            l += [f"   {html.escape(r)}" for r in p["rojos"]]
        cabeza = "\n".join(l)
        pie = f"Vence en {VENCE_S // 60} min."
        diff = enmascarar(diff)
        cuerpo = html.escape(diff)
        cabida = MAX_MENSAJE - len(cabeza) - len(pie) - 60
        if len(cuerpo) > cabida:
            # Se recorta el texto ya escapado y sin cortar una entidad (&lt; a medias).
            cuerpo = cuerpo[:max(cabida, 100)]
            amp = cuerpo.rfind("&")
            if amp != -1 and ";" not in cuerpo[amp:]:
                cuerpo = cuerpo[:amp]
            cuerpo += "\n… (diff recortado)"
        return f"{cabeza}\n\n<pre>{cuerpo}</pre>\n{pie}"

    def teclado(self, p: dict) -> dict:
        cb = lambda a: f"{a}|{p['id']}|{p['nonce']}"
        if p["tipo"] == "consulta":
            # Un boton por fila, con la letra y el nombre de la alternativa (lo de antes de «: »);
            # lo que pasa despues ya va en el texto. Sin ❌: no responder es dejarla vencer.
            filas = []
            for i, o in enumerate(p["opciones"]):
                t = f"{LETRAS[i]} — {o['etiqueta'].split(': ', 1)[0]}"
                t = t if len(t) <= MAX_BOTON else t[:MAX_BOTON - 1].rstrip() + "…"
                filas.append([{"text": t, "callback_data": cb(f"op{i}")}])
            return {"inline_keyboard": filas}
        if p["tipo"] == "sugerir":
            return {"inline_keyboard": [[{"text": "✅ Listo, lo corrí", "callback_data": cb("ok2")},
                                         {"text": "❌ No lo voy a correr", "callback_data": cb("no")}]]}
        verbo = "Probar" if p["tipo"] == "probar" else "Aplicar"
        if p["rojos"] and not p["confirmado1"]:
            ok = {"text": f"⚠️ Revisar y {verbo.lower()}", "callback_data": cb("ok1")}
        elif p["rojos"]:
            ok = {"text": f"🔴 Sí, {verbo.lower()} igual", "callback_data": cb("ok2")}
        else:
            ok = {"text": f"✅ {verbo}", "callback_data": cb("ok2")}
        return {"inline_keyboard": [[ok, {"text": "❌ Rechazar", "callback_data": cb("no")}]]}

    # ── callbacks ──
    def callbacks(self) -> None:
        ups = self.tg("getUpdates", offset=self.offset, timeout=5,
                      allowed_updates=["callback_query"])
        for u in ups:
            self.offset = u["update_id"] + 1
            self.guardar()
            q = u.get("callback_query")
            if q:
                try:
                    self.callback(q)
                except Exception as e:  # un toque que falla no tumba el ciclo
                    log(f"error en callback: {e}")

    def callback(self, q: dict) -> None:
        def responder(t: str) -> None:
            try:
                self.tg("answerCallbackQuery", callback_query_id=q["id"], text=t)
            except RuntimeError as e:
                log(f"answerCallbackQuery: {e}")
        if str(q["from"]["id"]) != self.chat or str(q["message"]["chat"]["id"]) != self.chat:
            log(f"callback de un from.id ajeno: {q['from'].get('id')}")
            return responder("No autorizado.")
        try:
            accion, pid, nonce = q.get("data", "").split("|")
        except ValueError:
            return responder("Botón inválido.")
        p = self.pend.get(pid)
        if not p or not secrets.compare_digest(nonce, p["nonce"]):
            if not p and (letra := self.ya_elegida(pid)):
                return responder(f"Ya se eligió {letra}.")
            return responder("Ese pedido ya no existe o ya se resolvió.")
        if p["tipo"] == "consulta":
            return self.elegir(p, accion, responder)
        if accion == "no":
            responder("Rechazado.")
            return self.cerrar(p, "rechazado", "rechazado por Diego")
        if accion == "ok1" and p["rojos"]:
            if p["confirmado1"]:
                return responder("Ya está: ahora toca el botón 🔴.")
            responder("Tiene marcas rojas: confirma otra vez.")
            p["confirmado1"] = True
            self.guardar()
            self.tg("editMessageReplyMarkup", chat_id=self.chat, message_id=p["msg"],
                    reply_markup=self.teclado(p))
            return
        if accion == "ok2" and p["tipo"] == "sugerir":
            responder("Anotado: la IA verifica.")
            return self.cerrar(p, "hecho", "Diego dice que lo corrió")
        if accion == "ok2" and (not p["rojos"] or p["confirmado1"]):
            responder("Corriendo…" if p["tipo"] == "probar" else "Aplicando…")
            # Se saca de pendientes ANTES de aplicar: un doble toque o un reinicio a mitad
            # no debe aplicar dos veces.
            self.pend.pop(pid, None)
            self.guardar()
            t = time.time()
            if p["tipo"] == "probar":
                estado, detalle, rc = self.correr_prueba(p)
            else:
                estado, detalle = self.aplicar(p)
                rc = None
            log(f"{pid}: {p['tipo']} tomó {time.time() - t:.1f} s")
            return self.cerrar(p, estado, detalle, rc)
        responder("Botón fuera de orden.")

    # ── aplicar ──
    def aplicar(self, p: dict) -> tuple[str, str]:
        base = RESPALDOS if RESPALDOS.is_dir() else ESTADO / "respaldos"
        resp = base / f"desplegar-{p['id']}"
        resp.mkdir(mode=0o700, parents=True, exist_ok=True)
        hechos = []
        try:
            if p["tipo"] in ("alta", "alta_enlace"):
                self.agregar_al_catalogo(p["items"][0]["nombre"], p["alta"])
            for it in p["items"]:
                if it["igual"]:
                    continue
                dest = Path(it["destino"])
                validar_destino(dest)
                if it.get("tipo") == "enlace":
                    # Nunca se reemplaza un enlace previo: preparar sólo deja llegar acá si no
                    # existía. El respaldo conserva qué enlace alcanzó a publicarse si algo
                    # posterior obliga a revertir el pedido.
                    (resp / it["nombre"]).write_text(it["objetivo"] + "\n")
                    crear_enlace(dest, it["objetivo"])
                    hechos.append((it, False))
                    continue
                data = (ESTADO / "staging" / p["id"] / it["nombre"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != it["hash"]:
                    raise RuntimeError(f"{it['nombre']}: el staging cambió")
                validar_dueno(it["dueno"], dest)
                anterior = leer_destino(dest)
                previo = anterior is not None
                if previo:
                    (resp / it["nombre"]).write_bytes(anterior)
                uid, gid = ids_dueno(it["dueno"])
                escribir_destino(dest, data, uid, gid, it["modo"],
                                 privado=it["dueno"] == "dcifu004:dcifu004")
                hechos.append((it, previo))
            unidades = self.despues(p)
            malas = [u for u in unidades if self.activo(u) != "active"]
            if malas:
                log_u = self.journal(malas[0])
                self.revertir(hechos, resp)
                self.despues(p, revertido=True)
                return "revertido", f"{', '.join(malas)} no quedó active; se revirtió.\n{log_u}"
            return "aplicado", f"{len(hechos)} archivo(s)" + (
                f", {len(unidades)} unidad(es) active" if unidades else "") + f"; respaldo en {resp}"
        except Exception as e:
            self.revertir(hechos, resp)
            return "revertido", f"error: {e}"

    def agregar_al_catalogo(self, nombre: str, e: dict) -> None:
        if nombre in self.cat():
            raise RuntimeError(f"'{nombre}' ya existe en el catálogo")
        bloque = f"\n# alta aprobada por Telegram el {time.strftime('%Y-%m-%d %H:%M')}\n[entrada.{nombre}]\n"
        if e.get("tipo") == "enlace":
            bloque += f"tipo     = \"enlace\"\ndestino = {json.dumps(e['destino'])}\nobjetivo = {json.dumps(e['objetivo'])}\n"
        else:
            bloque += (f"fuente  = {json.dumps(e['fuente'])}\n"
                       f"destino = {json.dumps(e['destino'])}\n"
                       f"modo    = {json.dumps(e['modo'])}\n"
                       f"dueno   = {json.dumps(e.get('dueno', 'root:root'))}\n"
                       f"despues = {json.dumps(e.get('despues', []))}\n")
        texto = CATALOGO.read_text() + bloque
        tomllib.loads(texto)  # que el catalogo siga siendo valido antes de escribirlo
        tmp = CATALOGO.with_suffix(".tmp")
        tmp.write_text(texto)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CATALOGO)
        self.publicar_catalogo()

    def correr_prueba(self, p: dict) -> tuple[str, str, int]:
        it = p["items"][0]
        data = (ESTADO / "staging" / p["id"] / it["nombre"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != it["hash"]:
            return "rechazado", "el staging cambió", -1
        ruta = ESTADO / "probar" / f"{p['id']}-{it['nombre']}"
        ruta.write_bytes(data)
        os.chmod(ruta, 0o700)
        try:
            r = subprocess.run(["systemd-run", "--wait", "--pipe", "--collect", "--quiet",
                                f"--unit=desplegar-probar-{p['id']}",
                                f"-p", f"RuntimeMaxSec={PROBAR_MAX_S}",
                                "--setenv=NODO_DESPLEGAR_PRUEBA=1", str(ruta), *p["args"]],
                               capture_output=True, text=True, timeout=PROBAR_MAX_S + 30,
                               stdin=subprocess.DEVNULL)
            salida, rc = (r.stdout + r.stderr), r.returncode
        except subprocess.TimeoutExpired:
            salida, rc = f"(pasó de {PROBAR_MAX_S} s)", -1
        finally:
            ruta.unlink(missing_ok=True)
        return "probado", f"exit {rc}\n{salida.strip()[-8000:]}", rc

    def despues(self, p: dict, revertido: bool = False) -> list[str]:
        acciones = []
        for it in p["items"]:
            if not it["igual"]:
                acciones += [a for a in it["despues"] if a not in acciones]
        unidades = []
        for a in acciones:
            if a == "daemon-reload":
                subprocess.run(["systemctl", "daemon-reload"], check=False)
            else:
                u = a[8:]
                existe = subprocess.run(["systemctl", "cat", u], capture_output=True).returncode == 0
                if revertido and not existe:
                    subprocess.run(["systemctl", "reset-failed", u], capture_output=True)
                    continue
                subprocess.run(["systemctl", "restart", u], capture_output=True, timeout=90)
                unidades.append(u)
        if unidades:
            time.sleep(2)  # que un servicio que muere al arrancar alcance a morir
        return unidades

    @staticmethod
    def activo(u: str) -> str:
        return subprocess.run(["systemctl", "is-active", u], capture_output=True,
                              text=True).stdout.strip()

    @staticmethod
    def journal(u: str) -> str:
        return subprocess.run(["journalctl", "-u", u, "-n", "4", "--no-pager", "-o", "cat"],
                              capture_output=True, text=True).stdout.strip()[-400:]

    @staticmethod
    def revertir(hechos: list, resp: Path) -> None:
        for it, previo in reversed(hechos):
            dest = Path(it["destino"])
            if it.get("tipo") == "enlace":
                # Un enlace nuevo sólo se publica después de que su objetivo existe. Si la
                # operación posterior falla, quitarlo por descriptor no sigue su objetivo.
                padre = abrir_directorio(dest.parent)
                try:
                    os.unlink(dest.name, dir_fd=padre)
                finally:
                    os.close(padre)
                continue
            if previo:
                uid, gid = ids_dueno(it["dueno"])
                escribir_destino(dest, (resp / it["nombre"]).read_bytes(), uid, gid, it["modo"],
                                 privado=it["dueno"] == "dcifu004:dcifu004")
            else:
                padre = abrir_directorio(dest.parent)
                try:
                    os.unlink(dest.name, dir_fd=padre)
                except FileNotFoundError:
                    pass
                finally:
                    os.close(padre)

    # ── cierre ──
    def cerrar(self, p: dict, estado: str, detalle: str, rc: int | None = None,
               opcion: int | None = None) -> None:
        icono = {"aplicado": "✅", "hecho": "✅", "rechazado": "❌", "revertido": "↩️", "vencido": "⌛",
                 "probado": "✅" if rc == 0 else "⚠️"}[estado]
        visible = enmascarar(detalle)
        if len(visible) > MAX_SALIDA:
            visible = "…" + visible[-MAX_SALIDA:]
        cola = f"\n\n{icono} <b>{estado.upper()}</b> {time.strftime('%H:%M')}"
        cola += f"\n<pre>{html.escape(visible)}</pre>" if "\n" in visible else f" — {html.escape(visible)}"
        base = p["texto"]
        if len(base) + len(cola) > 4096:
            # Sin el diff: cortar HTML por la mitad hace que Telegram rechace el mensaje.
            base = base.split("\n\n<pre>")[0] + "\n\n(diff omitido para que quepa el resultado)"
        texto = base + cola
        teclado, elegida = {}, {}
        if p.get("tipo") == "consulta":
            # La pregunta queda como se leyó, con la elección (o el vencimiento) al pie y el
            # teclado vacío explícito: no queda nada más que tocar (regla 10).
            hora = time.strftime("%H:%M")
            if estado == "hecho" and opcion is not None:
                o = p["opciones"][opcion]
                pie = f"✅ <b>Elegido: {LETRAS[opcion]} — {html.escape(o['etiqueta'])}</b> ({hora})"
                elegida = {"opcion": o["clave"], "letra": LETRAS[opcion]}
            elif estado == "vencido":
                pie = f"⌛ <b>Venció sin respuesta</b> ({hora})"
            else:
                pie = f"{icono} <b>{estado.upper()}</b> ({hora})"
            texto, teclado = self.texto_consulta(p, pie), {"reply_markup": {"inline_keyboard": []}}
        try:
            self.tg("editMessageText", chat_id=self.chat, message_id=p["msg"],
                    text=texto[:4096], parse_mode="HTML", **teclado)
        except RuntimeError as e:
            log(f"{p['id']}: no pude editar el mensaje: {e}")
        self.pend.pop(p["id"], None)
        self.guardar()
        shutil.rmtree(ESTADO / "staging" / p["id"], ignore_errors=True)
        # El sha256 del motivo que Diego vio junto al botón: con eso, quien lea el resultado
        # sabe QUÉ se aprobó, no sólo que se tocó ✅ (encargo 70r1: el bot de Pilar entrega sólo
        # el contenido cuya huella va en ese motivo). El hash y no el motivo: el resultado es 0644.
        sello = (hashlib.sha256(str(p.get("motivo", "")).encode("utf-8")).hexdigest()
                 if p.get("tipo") == "sugerir" else None)
        self.resultado(p["id"], estado, enmascarar(detalle), rc, motivo_sha256=sello, **elegida)
        log(f"{p['id']}: {estado}: {detalle.splitlines()[0] if detalle else ''}")

    @staticmethod
    def resultado(pid: str, estado: str, detalle: str, rc: int | None = None,
                  envio: dict | None = None, motivo_sha256: str | None = None,
                  opcion: str | None = None, letra: str | None = None) -> None:
        if not RE_ID.fullmatch(pid):
            return
        r = {"id": pid, "estado": estado, "detalle": detalle,
             "hora": time.strftime("%Y-%m-%d %H:%M:%S")}
        if rc is not None:
            r["rc"] = rc
        if envio is not None:
            r["envio"] = envio
        if motivo_sha256 is not None:
            r["motivo_sha256"] = motivo_sha256
        if opcion is not None:
            r["opcion"], r["letra"] = opcion, letra
        ruta = RESULTADOS / f"{pid}.json"
        ruta.write_text(json.dumps(r, ensure_ascii=False))
        os.chmod(ruta, 0o644)

    def limpiar(self) -> None:
        for p in list(self.pend.values()):
            if time.time() - p["creado"] > VENCE_S:
                self.cerrar(p, "vencido", "nadie eligió a tiempo" if p.get("tipo") == "consulta"
                            else "nadie lo aprobó a tiempo")
        for f in RESULTADOS.glob("*.json"):
            if time.time() - f.stat().st_mtime > 7 * 86400:
                f.unlink(missing_ok=True)

    def correr(self) -> None:
        log(f"escucha arriba ({len(self.pend)} pendientes recuperados)")
        while True:
            try:
                self.procesar_pedidos()
                self.limpiar()
                self.callbacks()
            except Exception as e:
                log(f"error en el ciclo: {e}")
                time.sleep(10)


def main() -> int:
    cmds = {"pedir": pedir, "probar": probar, "alta": alta, "alta-enlace": alta_enlace, "sugerir": sugerir,
            "consultar": consultar, "enviar": enviar, "esperar": esperar, "catalogo": catalogo}
    if len(sys.argv) < 2 or sys.argv[1] not in (*cmds, "escuchar"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    if sys.argv[1] == "escuchar":
        if os.geteuid() != 0:
            sys.exit("el escucha corre como root")
        Escucha().correr()
    return cmds[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
