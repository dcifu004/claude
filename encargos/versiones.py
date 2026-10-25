#!/usr/bin/env python3
"""Historial de versiones de 10-Proyectos/11-Pi5 con git (encargo 33, 07-10-2026).

    python3 encargos/versiones.py init
    python3 encargos/versiones.py foto "mensaje"
    python3 encargos/versiones.py log [archivo] [-n N]
    python3 encargos/versiones.py diff <desde> [<hasta>]
    python3 encargos/versiones.py recuperar <commit> <archivo>

Por qué así: el vault se sincroniza con Syncthing entre la Pi, el PC y el teléfono. Un `.git` dentro
del vault viajaría a todos los equipos y se corrompería con operaciones concurrentes. Por eso el
repositorio vive SOLO en la Pi, fuera del vault (`/opt/nodo/datos/git/11-Pi5.git`), y el árbol de
trabajo es `10-Proyectos/11-Pi5`. Cada comando de git lleva GIT_DIR y GIT_WORK_TREE explícitos: no
se crea ningún `.git` (carpeta ni archivo puntero) dentro del árbol, y `Repo` se niega a trabajar si
el repositorio quedara dentro de él.

- `foto` hace commit de todo lo que cambió; si no cambió nada no hace nada y sale 0.
- `recuperar` NUNCA pisa: escribe la versión vieja en `<archivo>.recuperado-<commit>` al lado del
  original (y se niega si ese nombre ya existe). Esos archivos no entran al historial.
- Las exclusiones (secretos, cachés, binarios, datos de otros equipos) viven en `info/exclude` del
  repositorio, no en un `.gitignore` del vault; las escribe este archivo (EXCLUSIONES) en cada
  `init` y `foto`. Los archivos de más de 5 MB se excluyen solos y quedan en la misma lista.

Para que cola-run.py lo use: `foto(mensaje)` y `diff(desde, hasta)` de este módulo. Stdlib, sin sudo.
Códigos de salida: 0 bien, 1 error, 2 uso.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
import time
from collections import namedtuple
from pathlib import Path

REPO_POR_DEFECTO = Path("/opt/nodo/datos/git/11-Pi5.git")
ARBOL_POR_DEFECTO = Path(__file__).resolve().parent.parent      # .../10-Proyectos/11-Pi5
IDENTIDAD = ("cola-run", "cola@pi5")
LIMITE_BYTES = 5 * 1024 * 1024
TIMEOUT_GIT_S = 300
ESPERA_CANDADO_S = 120
TOPE_DIFF_BYTES = 2 * 1024 * 1024
DIRS_SIN_RECORRER = {".git", "__pycache__", ".venv", "venv", "node_modules"}

# Un patrón por línea, como en un .gitignore. Se anclan con «/» a la raíz del árbol (11-Pi5).
EXCLUSIONES = """\
# --- Escrito por encargos/versiones.py: no editar a mano (se reescribe en cada foto). ---

# El vault no lleva .git; que nunca entre uno anidado.
.git

# Secretos y credenciales.
*.env
.env
.env.*
!*.env.example
!*.env.ejemplo
!.env.example
secretos/
*.key
*.pem
*.pfx
*.p12
*.pass
*.token
token.json
credentials*.json
client_secret*.json
auth.json
.codex/
.agents/
.claude/

# Cachés y entornos regenerables.
__pycache__/
*.pyc
.venv/
venv/
node_modules/
.pytest_cache/

# Estado vivo de las colas (cambia cada pocos minutos; los permisos de búsqueda son secretos efímeros).
/encargos/vivo/
# Telemetría de otro equipo, regenerada por pi/uso-equipo.py.
/uso-equipos/

# PDFs y binarios (los de más de 5 MB se agregan solos al final).
*.pdf
*.zip
*.img
*.iso
*.7z
*.tar
*.tgz
*.gz
*.db
*.sqlite
*.sqlite3

# Datos laborales y de otros equipos: nada de esto se versiona aunque algún día aparezca acá.
vault_trabajo/
encargos-buzon/
/pc2503/estado/
/pc2503/pendientes/

# Temporales de Syncthing y del sistema; copias que deja `recuperar`.
.stversions/
.stfolder
~syncthing~*
.syncthing.*.tmp
.DS_Store
Thumbs.db
desktop.ini
*.recuperado-*
"""

Foto = namedtuple("Foto", "hash nueva avisos")      # hash del commit actual (None si el repo aún no tiene)


class VersionesError(Exception):
    pass


def _escapar(ruta: str) -> str:
    """Una ruta relativa como patrón anclado de .gitignore, con sus caracteres especiales."""
    for c in "\\*?[]":
        ruta = ruta.replace(c, "\\" + c)
    if ruta.endswith(" "):
        ruta = ruta[:-1] + "\\ "
    return "/" + ruta


class Repo:
    def __init__(self, git_dir: Path | str, arbol: Path | str):
        self.git_dir = Path(os.path.abspath(git_dir))
        self.arbol = Path(os.path.abspath(arbol))
        if not self.arbol.is_dir():
            raise VersionesError(f"el árbol de trabajo no existe: {self.arbol}")
        g, a = Path(os.path.realpath(self.git_dir)), Path(os.path.realpath(self.arbol))
        if g == a or a in g.parents or self.git_dir.name == ".git":
            raise VersionesError(f"el repositorio no puede vivir dentro del árbol de trabajo ni llamarse .git "
                                 f"({self.git_dir}); el vault se sincroniza y se corrompería")

    # ------------------------------------------------------------ git
    def _env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_DIR=str(self.git_dir), GIT_WORK_TREE=str(self.arbol),
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
                   GIT_AUTHOR_NAME=IDENTIDAD[0], GIT_AUTHOR_EMAIL=IDENTIDAD[1],
                   GIT_COMMITTER_NAME=IDENTIDAD[0], GIT_COMMITTER_EMAIL=IDENTIDAD[1])
        return env

    def git(self, *args: str, check: bool = True, entrada: bytes | None = None) -> subprocess.CompletedProcess:
        try:
            p = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=self.arbol, env=self._env(),
                               input=entrada, capture_output=True, timeout=TIMEOUT_GIT_S)
        except subprocess.TimeoutExpired:
            raise VersionesError(f"git {args[0]} tardó más de {TIMEOUT_GIT_S} s") from None
        if check and p.returncode != 0:
            raise VersionesError(f"git {args[0]} falló (rc {p.returncode}): "
                                 f"{(p.stderr or p.stdout).decode('utf-8', 'replace').strip()}")
        return p

    def existe(self) -> bool:
        return (self.git_dir / "HEAD").is_file() and (self.git_dir / "objects").is_dir()

    def _requiere(self) -> None:
        if not self.existe():
            raise VersionesError(f"no hay historial en {self.git_dir}; corre `versiones.py init`")

    def _candado(self):
        class _C:
            def __enter__(s):
                s.fd = os.open(self.git_dir / "versiones.lock", os.O_RDWR | os.O_CREAT, 0o600)
                fin = time.monotonic() + ESPERA_CANDADO_S
                while True:
                    try:
                        fcntl.flock(s.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        return s
                    except BlockingIOError:
                        if time.monotonic() > fin:
                            os.close(s.fd)
                            raise VersionesError("otra foto lleva más de 2 min en curso") from None
                        time.sleep(0.2)

            def __exit__(s, *a):
                os.close(s.fd)       # cierra y suelta el flock
        return _C()

    def head(self) -> str | None:
        p = self.git("rev-parse", "--verify", "-q", "HEAD", check=False)
        return p.stdout.decode().strip() if p.returncode == 0 else None

    def resolver(self, ref: str) -> str:
        if not ref or ref.startswith("-"):
            raise VersionesError(f"commit inválido: {ref!r}")
        p = self.git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False)
        if p.returncode != 0:
            raise VersionesError(f"no existe el commit {ref!r}")
        return p.stdout.decode().strip()

    # ------------------------------------------------------------ init / exclusiones
    def _grandes(self) -> list[str]:
        """Rutas (relativas, con «/») de archivos de más de 5 MB en el árbol."""
        out = []
        for raiz, dirs, archivos in os.walk(self.arbol):
            dirs[:] = [d for d in dirs if d not in DIRS_SIN_RECORRER]
            for n in archivos:
                ruta = os.path.join(raiz, n)
                try:
                    st = os.lstat(ruta)
                except OSError:
                    continue
                if os.path.isfile(ruta) and not os.path.islink(ruta) and st.st_size > LIMITE_BYTES:
                    out.append(os.path.relpath(ruta, self.arbol).replace(os.sep, "/"))
        return sorted(out)

    def _escribir_exclusiones(self) -> list[str]:
        grandes = self._grandes()
        texto = EXCLUSIONES + "\n# Más de 5 MB (automático, se recalcula en cada foto).\n" + "".join(
            _escapar(r) + "\n" for r in grandes)
        ruta = self.git_dir / "info" / "exclude"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if not ruta.exists() or ruta.read_text(encoding="utf-8") != texto:
            tmp = ruta.with_name("exclude.tmp")
            tmp.write_text(texto, encoding="utf-8")
            os.replace(tmp, ruta)
        return grandes

    def init(self) -> Foto:
        """Crea el repositorio separado si no existe y, si no tiene commits, hace el primero."""
        if not self.existe():
            self.git_dir.parent.mkdir(parents=True, exist_ok=True)
            self.git("init", "-q", "--initial-branch=main")
        with self._candado():
            for k, v in (("user.name", IDENTIDAD[0]), ("user.email", IDENTIDAD[1]), ("core.autocrlf", "false"),
                         ("core.quotepath", "false"), ("core.excludesFile", os.devnull), ("core.hooksPath", os.devnull),
                         ("commit.gpgsign", "false"), ("gc.auto", "256")):
                self.git("config", k, v)
            self._escribir_exclusiones()
        return self.foto("estado inicial") if self.head() is None else Foto(self.head(), False, [])

    # ------------------------------------------------------------ foto
    def foto(self, mensaje: str) -> Foto:
        """Commit de todo lo que cambió. Sin cambios no hace nada: devuelve el commit actual y nueva=False."""
        if not mensaje or not mensaje.strip():
            raise VersionesError("falta el mensaje de la foto")
        self._requiere()
        avisos: list[str] = []
        with self._candado():
            grandes = self._escribir_exclusiones()
            if grandes:     # si ya estaban en el historial, dejan de seguirse (los commits viejos los conservan)
                tracked = {r for r in self.git("ls-files", "-z").stdout.decode("utf-8", "replace").split("\0") if r}
                sacar = [r for r in grandes if r in tracked]
                if sacar:
                    self.git("rm", "-q", "--cached", "--ignore-unmatch", "--pathspec-from-file=-", "--pathspec-file-nul",
                             entrada="\0".join(sacar).encode() + b"\0")
                    avisos.append(f"{len(sacar)} archivo(s) pasaron de 5 MB y dejaron de versionarse: {', '.join(sacar[:3])}")
            p = self.git("add", "-A", "--ignore-errors", check=False)
            if p.returncode != 0:       # p. ej. un archivo sin permiso de lectura: se anota y se sigue con el resto
                avisos.append("git add con avisos: " + (p.stderr or b"").decode("utf-8", "replace").strip()[:300])
            if self.git("diff", "--cached", "--quiet", check=False).returncode == 0:
                return Foto(self.head(), False, avisos)
            self.git("commit", "-q", "--no-verify", "--no-gpg-sign", "-m", mensaje.strip())
            return Foto(self.head(), True, avisos)

    # ------------------------------------------------------------ consultas
    def _rel(self, archivo: str) -> str:
        """Ruta de un archivo del árbol, relativa a él y con «/». Una relativa se lee desde el directorio
        actual si éste cuelga del árbol (como cualquier comando); si no, desde la raíz del árbol."""
        p = Path(archivo)
        if not p.is_absolute():
            cwd = Path.cwd()
            base = cwd if (cwd == self.arbol or self.arbol in cwd.parents) else self.arbol
            p = base / p
        p = Path(os.path.normpath(p))
        try:
            rel = p.relative_to(self.arbol)
        except ValueError:
            raise VersionesError(f"{archivo!r} no está dentro de {self.arbol}") from None
        if not rel.parts or ".git" in rel.parts:
            raise VersionesError(f"ruta inválida: {archivo!r}")
        return rel.as_posix()

    def log(self, archivo: str | None = None, n: int | None = None) -> str:
        self._requiere()
        args = ["log", "--no-color", "--date=format:%d-%m-%Y %H:%M", "--format=%h  %ad  %s"]
        if n:
            args.append(f"-n{int(n)}")
        if archivo:
            rel = self._rel(archivo)
            if not (self.arbol / rel).is_dir():
                args.append("--follow")
            args += ["--", rel]
        return self.git(*args).stdout.decode("utf-8", "replace")

    def diff(self, desde: str, hasta: str = "HEAD", tope: int | None = None) -> str:
        """Resumen y diff completo entre dos commits (lo borrado incluido). Con `tope` recorta el texto."""
        self._requiere()
        a, b = self.resolver(desde), self.resolver(hasta)
        texto = self.git("diff", "--no-color", "--no-ext-diff", "--no-textconv", "-M", "--stat", "--patch",
                         a, b, "--").stdout.decode("utf-8", "replace")
        if tope and len(texto.encode()) > tope:
            corte = texto.encode()[:tope].decode("utf-8", "ignore")
            texto = (corte + f"\n\n[recortado: el diff completo pesa {len(texto.encode())} bytes; "
                     f"`python3 encargos/versiones.py diff {a[:7]} {b[:7]}`]\n")
        return texto

    def recuperar(self, commit: str, archivo: str) -> Path:
        """Escribe la versión de `archivo` en `commit` a `<archivo>.recuperado-<commit>`; nunca pisa nada."""
        self._requiere()
        h, rel = self.resolver(commit), self._rel(archivo)
        if self.git("cat-file", "-t", f"{h}:{rel}", check=False).stdout.decode().strip() != "blob":
            raise VersionesError(f"{rel} no es un archivo en el commit {h[:7]}")
        datos = self.git("cat-file", "blob", f"{h}:{rel}").stdout
        destino = self.arbol / f"{rel}.recuperado-{h[:7]}"
        # Cada paso queda atado al directorio ya abierto (dir_fd + O_NOFOLLOW): si otro proceso cambia un tramo
        # por un enlace después de abrirlo, las operaciones siguen en el directorio original, no en el enlace.
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        partes = destino.parent.relative_to(self.arbol).parts
        fd = os.open(self.arbol, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for parte in partes:
                try:
                    os.mkdir(parte, dir_fd=fd)
                except FileExistsError:
                    pass
                try:
                    sig = os.open(parte, flags, dir_fd=fd)
                except OSError as e:
                    raise VersionesError(f"{parte!r} es un enlace simbólico o no es una carpeta; "
                                         f"no recupero a través de él") from e
                os.close(fd)
                fd = sig
            try:
                ffd = os.open(destino.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=fd)
            except FileExistsError:
                raise VersionesError(f"ya existe {destino}; no lo piso (muévelo o bórralo y repite)") from None
            with os.fdopen(ffd, "wb") as fh:
                fh.write(datos)
        finally:
            os.close(fd)
        return destino

    def tam_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.git_dir.rglob("*") if f.is_file())


# ---------------------------------------------------------------- uso desde cola-run.py y la línea de comandos

def abrir(git_dir: str | None = None, arbol: str | None = None) -> Repo:
    """Repo por argumento, por entorno (VERSIONES_REPO / VERSIONES_ARBOL) o por defecto."""
    return Repo(git_dir or os.environ.get("VERSIONES_REPO") or REPO_POR_DEFECTO,
                arbol or os.environ.get("VERSIONES_ARBOL") or ARBOL_POR_DEFECTO)


def foto(mensaje: str) -> Foto:
    return abrir().foto(mensaje)


def diff(desde: str, hasta: str = "HEAD", tope: int | None = TOPE_DIFF_BYTES) -> str:
    return abrir().diff(desde, hasta, tope)


def _tam_humano(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{n / 1024:.0f} KB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="versiones.py", description="Historial de versiones de 11-Pi5 (git fuera del vault).")
    ap.add_argument("--repo", help=f"directorio git (por defecto {REPO_POR_DEFECTO}; env VERSIONES_REPO)")
    ap.add_argument("--arbol", help="árbol de trabajo (por defecto 11-Pi5; env VERSIONES_ARBOL)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="crea el repositorio separado si no existe y hace el primer commit")
    s = sub.add_parser("foto", help="commit de todo lo que cambió (sin cambios: no hace nada)")
    s.add_argument("mensaje")
    s = sub.add_parser("log", help="historial, de todo o de un archivo")
    s.add_argument("archivo", nargs="?")
    s.add_argument("-n", type=int, help="solo las últimas N")
    s = sub.add_parser("diff", help="qué cambió entre dos commits (hasta = HEAD)")
    s.add_argument("desde")
    s.add_argument("hasta", nargs="?", default="HEAD")
    s = sub.add_parser("recuperar", help="escribe la versión vieja de un archivo a <archivo>.recuperado-<commit>")
    s.add_argument("commit")
    s.add_argument("archivo")
    a = ap.parse_args(argv)
    try:
        r = abrir(a.repo, a.arbol)
        if a.cmd == "init":
            existia = r.existe()
            f = r.init()
            print(f"{'ya existía' if existia else 'creado'}: {r.git_dir} · árbol {r.arbol} · commit {(f.hash or '-')[:7]}"
                  f" · {_tam_humano(r.tam_bytes())}")
        elif a.cmd == "foto":
            f = r.foto(a.mensaje)
            print(f"foto {f.hash[:7]}: {a.mensaje}" if f.nueva else "sin cambios")
            for v in f.avisos:
                print(f"aviso: {v}", file=sys.stderr)
        elif a.cmd == "log":
            sys.stdout.write(r.log(a.archivo, a.n))
        elif a.cmd == "diff":
            sys.stdout.write(r.diff(a.desde, a.hasta))
        else:
            print(r.recuperar(a.commit, a.archivo))
    except VersionesError as e:
        print(f"versiones: {e}", file=sys.stderr)
        return 1
    except (BrokenPipeError, KeyboardInterrupt):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
