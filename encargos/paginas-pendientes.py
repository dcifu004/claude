#!/usr/bin/env python3
"""Una sola línea para instalar TODAS las páginas de Cockpit que quedaron pendientes (03-10-2026).

    python3 paginas-pendientes.py [--esperar colaNN ...] [--simular]

Por qué existe: cada cola manda su propia línea con solo las páginas que tocó. Si el usuario
corre una línea vieja (la de la cola 20) después de una nueva (la de la 22), la vieja pisa la
página nueva. Este script compara cada página del vault con la instalada en
~/.local/share/cockpit y arma UNA línea, desde una copia tomada en el mismo instante. Con esa
línea, todas las anteriores quedan obsoletas.

- Espera a que terminen las sesiones de --esperar. Si alguna no terminó en «terminada»
  (vivo/<cola>.json), no manda nada: no se instala trabajo que no quedó en verde.
- No incluye una página que esté en el [paginas] de una cola todavía viva: estaría a medio hacer.
- Nexus no se instala (doc 28).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

D = Path("/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5")
E = D / "encargos"
L = Path.home() / "encargos-logs"
INSTALADAS = Path.home() / ".local/share/cockpit"
ESTADO = E / "COLA-ESTADO.md"
PAGINAS = ["comun", "sistema", "nodo", "bots", "cuentas", "encargos", "noticias", "luces"]


def sha_dir(p: Path) -> str | None:
    if not p.is_dir():
        return None
    h = hashlib.sha256()
    for f in sorted(x for x in p.rglob("*") if x.is_file() and "__pycache__" not in x.parts):
        h.update(str(f.relative_to(p)).encode() + b"\0" + f.read_bytes())
    return h.hexdigest()[:12]


def difiere(vault: Path, instalada: Path) -> bool:
    """True si algún archivo del vault falta o cambia en la instalada. Lo que sobra en la
    instalada no cuenta: `cp -r` no borra, y quedan restos como bots/comun.js (movido a
    cockpit-comun por la cola 18) que de otro modo harían pendiente a la página para siempre."""
    for f in vault.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            g = instalada / f.relative_to(vault)
            if not g.is_file() or g.read_bytes() != f.read_bytes():
                return True
    return False


def viva(s: str) -> bool:
    return subprocess.run(["tmux", "has-session", "-t", f"={s}"], capture_output=True).returncode == 0


def log(texto: str) -> None:
    linea = f"- {datetime.now():%d-%m %H:%M} · {texto}"
    print(linea, flush=True)
    with ESTADO.open("a", encoding="utf-8") as fh:
        fh.write(linea + "\n")


_RA_MOD = None


def avisar(motivo: str, linea: str) -> None:
    # Las ejecuciones de agentes llevan la marca de prueba: nunca pueden convertir un
    # descarte de su registro en un pedido real a nodo-desplegar. Las suites aíslan L.
    if os.environ.get("NODO_PRUEBAS") == "1" and L == Path.home() / "encargos-logs":
        return
    with (L / "avisos.log").open("a", encoding="utf-8") as fh:
        p = subprocess.run(["nodo-desplegar", "sugerir", "--motivo", motivo, "--", linea],
                           capture_output=True, text=True)
        fh.write(p.stdout + p.stderr)
    # Encargo 23b: el aviso queda también en el registro único, con el id que devolvió
    # nodo-desplegar. No cambia cómo se envía y, si falla, el aviso ya salió.
    global _RA_MOD
    try:
        if _RA_MOD is None:
            spec = importlib.util.spec_from_file_location("registro_avisos", Path(__file__).resolve().parent / "registro_avisos.py")
            _RA_MOD = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_RA_MOD)
        _RA_MOD.registrar("paginas", motivo, linea, _RA_MOD.id_de(p.stdout or ""),
                          None if p.returncode == 0 else "no enviado")
    except Exception as e:
        print(f"⚠️ no se pudo registrar el aviso ({type(e).__name__}: {e})", flush=True)


def paginas_de_colas_vivas() -> set[str]:
    ocupadas = set()
    for m in E.glob("cola-*.toml"):
        try:
            man = tomllib.loads(m.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if man.get("nombre") and viva(man["nombre"]):
            ocupadas |= set((man.get("paginas") or {}).keys())
    return ocupadas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--esperar", nargs="*", default=[])
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args()

    if a.esperar and not a.simular:
        log(f"📦 Instalación única de páginas: espera a {', '.join(a.esperar)}")
    for s in a.esperar:
        while not a.simular and viva(s):
            time.sleep(60)
        try:
            estado = json.loads((E / "vivo" / f"{s}.json").read_text(encoding="utf-8")).get("estado")
        except (OSError, ValueError):
            estado = "sin archivo vivo"
        if estado != "terminada" and not a.simular:
            log(f"⛔ Instalación única: {s} terminó en «{estado}», no en «terminada». No se manda nada")
            avisar(f"⛔ No se armó la instalación única de páginas: {s} terminó en «{estado}». "
                   "No instales ninguna línea anterior de páginas. Esta línea muestra el estado.", f"cat {ESTADO}")
            return 1

    ocupadas = paginas_de_colas_vivas()
    pendientes = [n for n in PAGINAS
                  if n not in ocupadas and (D / "pi" / f"cockpit-{n}").is_dir() and
                  difiere(D / "pi" / f"cockpit-{n}", INSTALADAS / n)]
    print(f"pendientes: {pendientes or 'ninguna'}; ocupadas por colas vivas: {sorted(ocupadas) or 'ninguna'}")
    if a.simular:
        return 0
    if not pendientes:
        log("📦 Instalación única: todas las páginas ya están al día")
        return 0
    foto = L / f"paginas-pendientes-{datetime.now():%Y%m%d-%H%M}"
    foto.mkdir(parents=True, exist_ok=True)
    for n in pendientes:
        subprocess.run(["cp", "-r", str(D / "pi" / f"cockpit-{n}"), str(foto / n)], check=True)
    linea = " && ".join(f"mkdir -p ~/.local/share/cockpit/{n} && cp -r {foto}/{n}/. ~/.local/share/cockpit/{n}/"
                        for n in pendientes)
    log(f"📦 Instalación única lista ({', '.join(pendientes)}) desde {foto}")
    avisar(f"📦 Instalación ÚNICA de páginas de Cockpit ({', '.join(pendientes)}): junta lo pendiente de las "
           "colas 20 y 22 desde una copia de este momento. Reemplaza las líneas anteriores de páginas: no "
           "corras ninguna de esas. Después recarga Cockpit.", linea)
    return 0


if __name__ == "__main__":
    sys.exit(main())
