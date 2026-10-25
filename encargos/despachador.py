#!/usr/bin/env python3
"""Una pasada del despachador de colas, sin modificar los vivo/.

Solo el registro de acciones y prioridad.txt se escriben aquí; cola-run.py sigue
siendo dueño del estado de cada cola.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import stat
import subprocess
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ENCARGOS = Path(__file__).resolve().parent
RE_COLA = re.compile(r"cola[0-9]{2}[a-z0-9]*")
CUOTA = re.compile(r"sin margen|sin cuota", re.I)


def ahora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _leer_json(ruta: Path) -> dict | None:
    try:
        fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        with os.fdopen(fd, encoding="utf-8") as fh:
            dato = json.load(fh)
    except (OSError, ValueError):
        return None
    return dato if isinstance(dato, dict) else None


def vivo(nombre: str, vivos_dir: Path) -> dict | None:
    dato = _leer_json(vivos_dir / f"{nombre}.json")
    return dato if dato and dato.get("nombre") == nombre and isinstance(dato.get("estado"), str) else None


def vivo_con_estado(nombre: str, vivos_dir: Path) -> tuple[dict | None, bool]:
    """(vivo, roto): la ausencia permite partir; un archivo ilegible no."""
    ruta = vivos_dir / f"{nombre}.json"
    dato = _leer_json(ruta)
    if dato is not None and dato.get("nombre") == nombre and isinstance(dato.get("estado"), str):
        return dato, False
    try:
        existe = ruta.exists() or ruta.is_symlink()
    except OSError:
        existe = True
    return None, existe


def manifiestos(carpeta: Path) -> dict[str, tuple[Path, dict]]:
    """Resuelve la cola por `nombre`, no por un nombre convertido en ruta."""
    base, salida = carpeta.resolve(), {}
    for ruta in sorted(carpeta.glob("cola-*.toml")):
        try:
            real = ruta.resolve(strict=True)
            if ruta.is_symlink() or real.parent != base or not real.is_file():
                continue
            man = tomllib.loads(real.read_text(encoding="utf-8"))
        except (OSError, ValueError, tomllib.TOMLDecodeError):
            continue
        nombre = man.get("nombre")
        if (isinstance(nombre, str) and RE_COLA.fullmatch(nombre) and isinstance(man.get("etapa"), list)
                and man["etapa"] and not man.get("solo_simular") and nombre not in salida
                and all(isinstance(et, dict) and isinstance(et.get("id"), str) for et in man["etapa"])):
            salida[nombre] = (real, man)
    return salida


def leer_prioridad(ruta: Path) -> list[str]:
    try:
        return ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def escribir_prioridad(ruta: Path, lineas: list[str]) -> None:
    fd, temporal = tempfile.mkstemp(prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lineas) + ("\n" if lineas else ""))
            fh.flush()
            os.fsync(fh.fileno())
            try:
                os.fchmod(fh.fileno(), stat.S_IMODE(ruta.stat().st_mode))
            except OSError:
                os.fchmod(fh.fileno(), 0o644)
        os.replace(temporal, ruta)
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise


def sesiones_vivas(tmux: tuple[str, ...]) -> tuple[bool | None, list[str]]:
    try:
        p = subprocess.run([*tmux, "list-sessions", "-F", "#{session_name}"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None, []
    if p.returncode not in (0, 1):
        return None, []
    return True, [x for x in p.stdout.splitlines() if RE_COLA.fullmatch(x)]


def lanzamiento(nombre: str, manifiesto: Path, desde: str | None) -> list[str]:
    argv = ["tmux", "new-session", "-d", "-s", nombre, "python3", str(ENCARGOS / "cola-run.py"), str(manifiesto)]
    return argv + (["--desde", desde] if desde else [])


def _despacho(vivos_dir: Path) -> dict:
    d = _leer_json(vivos_dir / "despacho.json")
    if not (d and d.get("estado") in ("abierto", "pausa") and isinstance(d.get("autorizadas", []), list)):
        return {"estado": "abierto", "autorizadas": []}
    if not all(isinstance(x, str) and RE_COLA.fullmatch(x) for x in d["autorizadas"]):
        return {"estado": "abierto", "autorizadas": []}
    return {"estado": d["estado"], "autorizadas": d["autorizadas"]}


def _depende(man: dict, vivos_dir: Path) -> tuple[bool, str]:
    deps = man.get("depende", [])
    if not isinstance(deps, list) or not all(isinstance(x, str) and RE_COLA.fullmatch(x) for x in deps):
        return False, "depende inválido"
    pendientes = [x for x in deps if (vivo(x, vivos_dir) or {}).get("estado") != "terminada"]
    return (not pendientes, "" if not pendientes else "depende de " + ", ".join(pendientes))


def _desde(v: dict | None) -> tuple[str | None, str]:
    if v is None:
        return None, "nunca partió"
    estado = v["estado"]
    if estado == "esperando_cuota" or (estado == "pausada" and CUOTA.search(str(v.get("motivo_pausa", "")))):
        desde = v.get("reanuda_desde")
        # Los vivos antiguos de espera de cuota todavía publican etapa/fase, no
        # reanuda_desde. Es el mismo punto de continuación y evita dejarlos
        # detenidos al migrar al despachador (cola43 de 46-fixtures).
        if not isinstance(desde, str) and estado == "esperando_cuota":
            etapa, fase = v.get("etapa"), v.get("fase")
            desde = f"{etapa}:{fase}" if isinstance(etapa, str) and isinstance(fase, str) else None
        return (desde, "pausada por cuota" if isinstance(desde, str) and desde else "sin reanuda_desde")
    return None, estado


def _desde_valido(desde: str | None, man: dict) -> bool:
    if not isinstance(desde, str) or desde.count(":") != 1:
        return False
    etapa, fase = desde.split(":", 1)
    encontrada = next((x for x in man["etapa"] if x["id"] == etapa), None)
    if encontrada is None:
        return False
    try:
        vueltas = 0 if encontrada.get("donde", "pi") == "pc2503" else int(encontrada.get("vueltas", 2))
    except (TypeError, ValueError):
        return False
    fases = ("autor", "rev1", "fix1", "rev2", "fix2", "rev3", "fix3")[:1 + 2 * vueltas + 1]
    return fase in fases


def _ultimo_hecho(ruta: Path, nombre: str, solo_reanudaciones: bool = False) -> datetime | None:
    """Último lanzamiento propio válido; una línea incompleta no invalida el registro."""
    ultimo = None
    try:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            try:
                fila = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if not isinstance(fila, dict):
                continue
            if fila.get("por") != "despachador" or fila.get("resultado") != "hecho" or fila.get("cola") != nombre:
                continue
            if solo_reanudaciones and not isinstance(fila.get("desde"), str):
                continue
            try:
                momento = datetime.fromisoformat(fila["momento"])
            except (KeyError, TypeError, ValueError):
                continue
            if ultimo is None or momento > ultimo:
                ultimo = momento
    except OSError:
        return None
    return ultimo


def _vivo_confirma_lanzamiento(v: dict | None, lanzamiento: datetime) -> bool:
    """Un vivo escrito después del lanzamiento prueba que cola-run alcanzó a partir."""
    if v is None:
        return False
    try:
        return datetime.fromisoformat(v["escrito"]) >= lanzamiento
    except (KeyError, TypeError, ValueError):
        return False


def _registro(fd: int, cola: str | None, resultado: str, detalle: str, desde: str | None = None) -> None:
    fila = {"momento": ahora(), "accion": "despachar", "cola": cola, "resultado": resultado,
            "detalle": detalle, "desde": desde, "por": "despachador"}
    os.write(fd, (json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8"))


def pasada(*, carpeta: Path = ENCARGOS, prioridad: Path | None = None, vivos_dir: Path | None = None,
           tmux: tuple[str, ...] = ("tmux",), lanzar=None, simular: bool = False) -> dict:
    """Hace una pasada y, como máximo, lanza una cola."""
    carpeta, prioridad, vivos_dir = Path(carpeta), Path(prioridad or carpeta / "prioridad.txt"), Path(vivos_dir or carpeta / "vivo")
    lanzar = lanzar or (lambda argv: subprocess.run(argv, capture_output=True, timeout=30).returncode)
    eventos: list[str] = []
    registro = None
    try:
        if not simular:
            registro = os.open(vivos_dir / "acciones.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
            if not stat.S_ISREG(os.fstat(registro).st_mode):
                raise OSError("acciones.jsonl no es archivo corriente")
            os.fchmod(registro, 0o600)
            fcntl.flock(registro, fcntl.LOCK_EX)
        d = _despacho(vivos_dir)
        ok_tmux, activas = sesiones_vivas(tuple(tmux))
        if ok_tmux is not True:
            detalle = "tmux no respondió: no se lanza nada"
            eventos.append(detalle)
            if registro is not None: _registro(registro, None, "saltada", detalle)
            return {"lanzada": None, "eventos": eventos}
        if activas:
            detalle = "hay cola viva: " + ", ".join(activas)
            eventos.append(detalle)
            if registro is not None: _registro(registro, None, "saltada", detalle)
            return {"lanzada": None, "eventos": eventos}
        disponibles, lineas = manifiestos(carpeta), leer_prioridad(prioridad)
        restantes = list(lineas)
        for cruda in lineas:
            nombre = cruda.strip()
            if not nombre or nombre.startswith("#"):
                continue
            if not RE_COLA.fullmatch(nombre):
                detalle, cola = f"{nombre}: nombre inválido, se salta", None
            elif nombre not in disponibles:
                detalle, cola = f"{nombre}: sin manifiesto válido, se salta", nombre
            elif d["estado"] == "pausa" and nombre not in d["autorizadas"]:
                detalle, cola = f"{nombre}: despacho en pausa y no está autorizada, se salta", nombre
            else:
                cola, (ruta, man) = nombre, disponibles[nombre]
                v, roto = vivo_con_estado(nombre, vivos_dir)
                if roto:
                    detalle = f"{nombre}: vivo ilegible, se salta; lo decide el usuario"
                    eventos.append(detalle)
                    if registro is not None: _registro(registro, nombre, "saltada", detalle)
                    continue
                if v and v["estado"] == "terminada":
                    detalle = f"{nombre}: terminada, se quita de prioridad"
                    eventos.append(detalle)
                    if not simular:
                        restantes.remove(cruda)
                        escribir_prioridad(prioridad, restantes)
                        _registro(registro, nombre, "quitada", detalle)
                    continue
                cumple, razon = _depende(man, vivos_dir)
                if not cumple:
                    detalle = f"{nombre}: {razon}, se salta"
                else:
                    desde, estado = _desde(v)
                    ultimo_hecho = _ultimo_hecho(vivos_dir / "acciones.jsonl", nombre)
                    ultimo_reinicio = _ultimo_hecho(vivos_dir / "acciones.jsonl", nombre, solo_reanudaciones=True)
                    if estado == "sin reanuda_desde":
                        detalle = f"{nombre}: espera cuota sin reanuda_desde, se salta"
                    elif desde is not None and not _desde_valido(desde, man):
                        detalle = f"{nombre}: reanuda_desde inválido para el manifiesto, se salta"
                    elif ultimo_hecho is not None and not _vivo_confirma_lanzamiento(v, ultimo_hecho):
                        detalle = (f"{nombre}: ya despachada, sin vivo posterior que confirme el inicio; "
                                  "se salta; lo decide el usuario")
                    elif desde is not None and ultimo_reinicio is not None and ultimo_reinicio.astimezone().isocalendar()[:2] == datetime.now().astimezone().isocalendar()[:2]:
                        detalle = f"{nombre}: ya relanzada por cuota esta semana ISO, se salta"
                    elif v is not None and estado != "pausada por cuota":
                        detalle = f"{nombre}: está en «{estado}», se salta; lo decide el usuario"
                    else:
                        detalle = f"{nombre}: se lanza " + (f"desde {desde}" if desde else "desde el inicio")
                        eventos.append(detalle)
                        argv = lanzamiento(nombre, ruta, desde)
                        if simular:
                            return {"lanzada": nombre, "argv": argv, "eventos": eventos}
                        if lanzar(argv) == 0:
                            _registro(registro, nombre, "hecho", detalle, desde)
                            return {"lanzada": nombre, "argv": argv, "eventos": eventos}
                        detalle = f"{nombre}: tmux no pudo lanzar la cola"
                        eventos.append(detalle)
                        _registro(registro, nombre, "fallida", detalle, desde)
                        return {"lanzada": None, "eventos": eventos}
            eventos.append(detalle)
            if registro is not None: _registro(registro, cola, "saltada", detalle)
        return {"lanzada": None, "eventos": eventos}
    finally:
        if registro is not None:
            os.close(registro)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Despacha una sola cola según prioridad.txt")
    ap.add_argument("--simular", action="store_true")
    ns = ap.parse_args(argv)
    resultado = pasada(simular=ns.simular)
    print("\n".join(resultado["eventos"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
