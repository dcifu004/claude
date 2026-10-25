#!/usr/bin/python3
"""mensaje — una IA del nodo le escribe a Diego (Jaime) o a Camila (Pilar) por Telegram, sin token.

    mensaje --de claude_diego "La Pi volvió del reinicio y todo está arriba."
    estado --breve | mensaje --de codex -
    mensaje --de claude_diego --a pilar "Te dejo la guía de uso de Pilar."
    mensaje --de claude_diego --a pilar --archivo \\
        "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/35 - Guía de uso de Jaime y Pilar.html" \\
        "La guía de uso, para que la tengas a mano."

`--de` es claude_diego, claude_cami, codex o nodo (el bot lo muestra como «Claude (Diego)»,
«Claude (Cami)», «Codex» o «Nodo»).

A Jaime (por defecto, `--a jaime`): deja un JSON en la carpeta de salida del perfil jaime y
botv3 lo entrega en menos de 10 s; ver «Mensajes de las IA a Diego» en botv3.py. Por
defecto espera la entrega hasta 30 s (`--esperar 0` para no esperar).
Salida: 0 entregado (o encolado con --esperar 0), 2 uso, 3 volumen cifrado cerrado,
4 encolado pero sin entregar todavía (¿botv3@jaime caído?).

A Pilar (`--a pilar`, encargo 70): NADA sale sin el ✅ de Diego. Deja el envío en
/opt/nodo/datos/casa/para-pilar/<id>/ (con copia del `--archivo`, porque Pilar no ve los
vaults), manda la vista previa a Jaime y pide la firma con `nodo-desplegar sugerir`, cuyo
motivo lleva el sha256 entero del envío. El bot de Pilar lo entrega sólo con ese ✅, una vez,
dentro de 30 min y si el envío sigue siendo el de esa huella (el escucha sella el motivo en el
resultado); si no, lo descarta.
`--archivo` sólo acepta archivos de vault_personal (pdf png jpg jpeg webp md txt html, hasta
20 MB). Por defecto no espera: imprime el id y sale con 0 «pendiente de ✅». Con `--esperar N`
espera la entrega hasta N s: 0 entregado, 1 descartado (rechazado, vencido o inconsistente),
4 sigue pendiente. 5: no se pudo pedir la firma (no se envía nada).

Es texto libre para LEER, nada más: ningún bot ejecuta nada de lo que llega por acá.
Lo que Diego tenga que correr va por `nodo-desplegar sugerir`, que trae el botón ✅.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time

SALIDA_DIR = Path(os.environ.get("BOTV3_SALIDA_DIR", "/opt/nodo/datos/botv3/salida"))
REMITENTES = ("claude_diego", "claude_cami", "codex", "nodo")
MAX_LARGO = 8000

# --- A Pilar (encargo 70) -------------------------------------------------------------
# casa/ es root:casa 2770: lo único que comparten dcifu004 (agentes y Jaime) y botpilar.
# UMask=0077 gana sobre el grupo, así que cada modo se pone con chmod explícito.
CASA_DIR = Path(os.environ.get("BOTV3_CASA_DIR", "/opt/nodo/datos/casa"))
PARA_PILAR = "para-pilar"
VAULT = Path(os.environ.get("BOTV3_PERSONAL_VAULT", "/opt/nodo/datos/srv/vault_personal"))
NODO_DESPLEGAR = os.environ.get("BOTV3_NODO_DESPLEGAR", "/usr/local/bin/nodo-desplegar")
MAX_LARGO_PILAR = 4000
ARCHIVO_MAX = 20 * 1024 * 1024
ARCHIVO_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".md", ".txt", ".html")
PROHIBIDOS = ("secretos", ".git", ".obsidian")     # los mismos que `nodo-desplegar enviar`
MAX_NOMBRE = 120
RE_PEDIDO = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}")        # el RE_ID de nodo-desplegar
MODO_DIR = 0o2770
MODO_ARCHIVO = 0o660


def huella(texto: str, datos: bytes | None) -> str:
    """El sha256 de un envío: texto y archivo juntos, sin ambigüedad entre dónde termina uno y
    empieza el otro. botv3.huella_pilar es la misma cuenta; una prueba las compara."""
    t = texto.encode("utf-8")
    h = hashlib.sha256(b"%d\n" % len(t))
    h.update(t)
    h.update(datos or b"")
    return h.hexdigest()


def motivo_firma(mid: str, sha: str, nombre: str | None, n_bytes: int, texto: str) -> str:
    """El --motivo del `sugerir`, con la huella ENTERA. El escucha guarda su sha256 en el
    resultado del ✅ y el bot de Pilar lo rearma desde envio.json: si el envío cambió después
    de pedir la firma, no calza y no sale (70r1). botv3.motivo_pilar es la misma cuenta.
    Sólo vocabulario cerrado: lo que pasa por `sugerir` queda fuera del cifrado."""
    tipo = os.path.splitext(nombre)[1].lstrip(".") if nombre else "texto"
    kb = max(1, round((n_bytes if nombre else len(texto.encode("utf-8"))) / 1024))
    return (f"Enviar a Pilar el envío {mid} ({tipo}, {kb} KB, sha256 {sha}). "
            "La vista previa está en Jaime. ✅ = enviar")


def nombre_seguro(nombre: str) -> str:
    """El nombre con que se guarda la copia: sin '/', sin control, sin punto adelante y corto,
    conservando la extensión (que ya se validó)."""
    base, ext = os.path.splitext(nombre)
    base = re.sub(r"[\x00-\x1f\x7f/\\]", "_", base).strip().lstrip(".") or "archivo"
    return base[:MAX_NOMBRE - len(ext)] + ext.lower()


def leer_archivo(ruta_txt: str) -> tuple[str, bytes]:
    """(nombre, contenido) de un archivo de vault_personal, o ValueError con el motivo.

    Lo mismo que hace el escucha con `enviar`: la ruta se decide por su TEXTO (absoluta, sin
    `..`, bajo el vault, sin ocultos ni secretos) y después se abre tramo a tramo con O_NOFOLLOW,
    así que un enlace simbólico en cualquier tramo no se sigue. Corre como dcifu004, que ve los
    dos vaults: por eso el vault laboral se niega acá, no confiando en los permisos."""
    ruta = os.path.join(os.getcwd(), ruta_txt)
    if any(ord(c) < 32 or ord(c) == 127 for c in ruta) or len(ruta) > 1024:
        raise ValueError("ruta inválida (larguísima o con caracteres de control)")
    partes = ruta.split("/")[1:]
    if ".." in partes:
        raise ValueError("la ruta lleva «..»")
    if "" in partes or "." in partes:
        raise ValueError("la ruta lleva «//», «/./» o termina en «/»")
    base = VAULT.parts[1:]
    if tuple(partes[:len(base)]) != base or len(partes) == len(base):
        raise ValueError(f"fuera de vault_personal ({VAULT}/): sólo se envía desde ahí")
    for tramo in partes[len(base):]:
        if tramo.casefold() in PROHIBIDOS or tramo.startswith("."):
            raise ValueError(f"«{tramo}» no se envía (oculto o secreto)")
    ext = os.path.splitext(partes[-1])[1].lower()
    if ext not in ARCHIVO_EXT:
        raise ValueError(f"extensión no permitida: «{ext or 'sin extensión'}» (van {' '.join(ARCHIVO_EXT)})")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for i, tramo in enumerate(partes):
            ultimo = i == len(partes) - 1
            try:
                nuevo = os.open(tramo, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
                                | (os.O_NONBLOCK if ultimo else os.O_DIRECTORY), dir_fd=fd)
            except OSError as e:
                hasta = "/" + "/".join(partes[:i + 1])
                raise ValueError(f"no se pudo abrir sin seguir enlaces: {hasta} ({e.strerror})") from None
            os.close(fd)
            fd = nuevo
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("no es un archivo regular")
        if st.st_nlink != 1:
            raise ValueError("el archivo tiene enlaces duros")
        if st.st_size > ARCHIVO_MAX:
            raise ValueError(f"pesa {st.st_size / 1048576:.1f} MB; el tope es {ARCHIVO_MAX // 1048576} MB")
        datos = b""
        while len(datos) <= ARCHIVO_MAX:
            trozo = os.read(fd, ARCHIVO_MAX + 1 - len(datos))
            if not trozo:
                break
            datos += trozo
    finally:
        os.close(fd)
    if len(datos) > ARCHIVO_MAX:
        raise ValueError(f"pesa más de {ARCHIVO_MAX // 1048576} MB")
    if not datos:
        raise ValueError("el archivo está vacío")
    return nombre_seguro(partes[-1]), datos


def dejar_en_salida(datos: dict) -> Path:
    """Deja un JSON en la salida de jaime. El bot sólo mira *.json: se escribe con otro nombre
    y se renombra, así nunca lee un archivo a medio escribir."""
    SALIDA_DIR.mkdir(mode=0o700, exist_ok=True)
    tmp = SALIDA_DIR / f".{datos['id']}.tmp"
    destino = SALIDA_DIR / f"{datos['id']}.json"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.rename(tmp, destino)
    return destino


def nuevo_id() -> str:
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def _escribir(carpeta: Path, nombre: str, contenido: bytes) -> None:
    """Un archivo compartido: .tmp + rename, 0660 explícito (la umask del agente no manda)."""
    tmp = carpeta / f".{nombre}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, MODO_ARCHIVO)
    with os.fdopen(fd, "wb") as f:
        os.fchmod(f.fileno(), MODO_ARCHIVO)
        f.write(contenido)
    os.rename(tmp, carpeta / nombre)


def _carpeta_compartida(ruta: Path) -> None:
    """Crea `ruta` 2770 (el grupo `casa` lo hereda del setgid del padre), o verifica que lo que
    ya hay sea una carpeta y no un enlace."""
    try:
        os.mkdir(ruta, MODO_DIR)
        os.chmod(ruta, MODO_DIR)
    except FileExistsError:
        if not stat.S_ISDIR(os.lstat(ruta).st_mode):
            raise OSError(f"{ruta} no es una carpeta") from None


def pedir_firma(motivo: str) -> str | None:
    """`nodo-desplegar sugerir` con la línea inocua `true`; el id del pedido o None."""
    try:
        p = subprocess.run([NODO_DESPLEGAR, "sugerir", "--motivo", motivo, "--", "true"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    pid = (p.stdout.strip().splitlines() or [""])[-1].strip()
    return pid if p.returncode == 0 and RE_PEDIDO.fullmatch(pid) else None


def a_pilar(de: str, texto: str, archivo: str | None, esperar: int) -> int:
    if len(texto) > MAX_LARGO_PILAR:
        print(f"mensaje: aviso, se recorta a {MAX_LARGO_PILAR} caracteres", file=sys.stderr)
        texto = texto[:MAX_LARGO_PILAR].rstrip()
    nombre, datos = None, None
    if archivo is not None:
        try:
            nombre, datos = leer_archivo(archivo)
        except ValueError as e:
            print(f"mensaje: el archivo no se manda: {e}", file=sys.stderr)
            return 2
    if not texto and datos is None:
        print("mensaje: no hay texto ni archivo", file=sys.stderr)
        return 2
    # Sin el volumen, crear la carpeta escribiría en la raíz, debajo del punto de montaje.
    if not CASA_DIR.is_dir() or not SALIDA_DIR.parent.is_dir():
        print(f"mensaje: no existe {CASA_DIR} o {SALIDA_DIR.parent} (¿volumen cifrado cerrado?)",
              file=sys.stderr)
        return 3

    raiz = CASA_DIR / PARA_PILAR
    _carpeta_compartida(raiz)
    mid = nuevo_id()
    sha = huella(texto, datos)
    creado = time.time()
    tmp = raiz / f".{mid}.tmp"
    os.mkdir(tmp, MODO_DIR)
    os.chmod(tmp, MODO_DIR)
    try:
        if datos is not None:
            _escribir(tmp, nombre, datos)
        n_bytes = len(datos) if datos is not None else 0
        # La vista previa va por Jaime, dentro del cifrado: es lo que Diego lee antes del ✅.
        previa = texto or "(sin texto)"
        if nombre:
            previa += f"\n\n📎 {nombre} ({max(1, round(n_bytes / 1024))} KB)"
        previa += (f"\n\nEnvío {mid} · {sha[:8]}. Sale sólo con tu ✅ en el aviso de "
                   "nodo-desplegar (su sha256 empieza igual).")
        dejar_en_salida({"id": mid, "de": de, "para": "pilar", "texto": previa, "epoch": creado})
        pedido = pedir_firma(motivo_firma(mid, sha, nombre, n_bytes, texto))
        if pedido is None:
            dejar_en_salida({"id": nuevo_id(), "de": de, "para": "pilar", "epoch": time.time(),
                             "texto": f"El envío {mid} no sale: no se pudo pedir la firma."})
            print("mensaje: no se pudo pedir la firma a nodo-desplegar; no se envía nada",
                  file=sys.stderr)
            shutil.rmtree(tmp, ignore_errors=True)
            return 5
        # envio.json se escribe DESPUÉS de pedir la firma: su ctime (que nadie puede atrasar)
        # queda antes del ✅, y el bot de Pilar no acepta un ✅ anterior a ese momento.
        envio = {"id": mid, "de": de, "texto": texto, "archivo": nombre, "sha256": sha,
                 "bytes": n_bytes, "creado": creado, "pedido": pedido}
        _escribir(tmp, "envio.json", json.dumps(envio, ensure_ascii=False).encode("utf-8"))
        os.rename(tmp, raiz / mid)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    if esperar <= 0:
        print(f"{mid} pendiente de ✅")
        return 0
    carpeta = raiz / mid
    limite = time.monotonic() + esperar
    while time.monotonic() < limite:
        if (carpeta / "entregado.json").exists():
            print(f"{mid} entregado")
            return 0
        if (carpeta / "descartado.json").exists():
            print(f"mensaje: {mid} descartado (ver {carpeta / 'descartado.json'})", file=sys.stderr)
            return 1
        time.sleep(1)
    print(f"{mid} sigue pendiente de ✅ tras {esperar} s")
    return 4


def main() -> int:
    parser = argparse.ArgumentParser(description="Le manda a Diego (o, con ✅, a Camila) un texto por Telegram.")
    parser.add_argument("--de", required=True, choices=REMITENTES)
    parser.add_argument("--a", default="jaime", choices=("jaime", "pilar"))
    parser.add_argument("--archivo", metavar="RUTA", help="sólo con --a pilar: un archivo de vault_personal")
    parser.add_argument("--esperar", type=int, default=None, metavar="SEG")
    parser.add_argument("texto", nargs="?", help="el mensaje, o - para leerlo de stdin")
    args = parser.parse_args()

    if args.texto is None and not (args.a == "pilar" and args.archivo):
        parser.error("falta el texto (o - para leerlo de stdin)")
    texto = sys.stdin.read() if args.texto == "-" else (args.texto or "")
    texto = texto.strip()
    if args.a == "pilar":
        try:
            return a_pilar(args.de, texto, args.archivo, 0 if args.esperar is None else args.esperar)
        except OSError as e:
            print(f"mensaje: no se pudo dejar el envío para Pilar: {e}", file=sys.stderr)
            return 3
    if args.archivo:
        print("mensaje: --archivo es sólo para --a pilar; a Diego, `nodo-desplegar enviar`",
              file=sys.stderr)
        return 2
    esperar = 30 if args.esperar is None else args.esperar

    if not texto:
        print("mensaje: el texto está vacío", file=sys.stderr)
        return 2
    if len(texto) > MAX_LARGO:
        print(f"mensaje: aviso, se recorta a {MAX_LARGO} caracteres", file=sys.stderr)

    # Sin el volumen montado la carpeta no existe, y crearla escribiría en la raíz
    # por debajo del punto de montaje: el mensaje quedaría escondido al abrir LUKS.
    if not SALIDA_DIR.parent.is_dir():
        print(f"mensaje: no existe {SALIDA_DIR.parent} (¿volumen cifrado cerrado?)",
              file=sys.stderr)
        return 3

    mid = nuevo_id()
    destino = dejar_en_salida({"id": mid, "de": args.de, "texto": texto, "epoch": time.time()})

    if esperar <= 0:
        print(mid)
        return 0
    limite = time.monotonic() + esperar
    while time.monotonic() < limite:
        if not destino.exists():
            print(f"{mid} entregado")
            return 0
        time.sleep(1)
    print(f"mensaje: {mid} sigue en cola tras {esperar} s (¿botv3@jaime caído?)",
          file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
