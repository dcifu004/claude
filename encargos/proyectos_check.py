#!/usr/bin/env python3
"""Valida encargos/proyectos.json (encargo 99). Sólo lee; no escribe nada.

    python3 encargos/proyectos_check.py                      # el proyectos.json y los NN-*.md de esta carpeta
    python3 encargos/proyectos_check.py otro.json --indice indice.json

Errores (rc 1): JSON inválido o de más de 1 MB, columnas o topes que no existen, ids con mala forma, un id en dos
proyectos, una columna de «abiertos» inventada, archivos_compartidos con mala forma y encargos del índice sin
proyecto. Avisos (rc 0): una columna con más abiertos que su tope. La skill `encargar` lo llama al preparar un encargo.
"""
import argparse
import json
import pathlib
import re
import sys

AQUI = pathlib.Path(__file__).resolve().parent
COLUMNAS = ["Idea", "Ready", "In progress", "Review", "Done"]
RE_ID = re.compile(r"^[0-9]{2}[a-z0-9]{0,8}$")
RE_PROYECTO = re.compile(r"^[a-z0-9_-]{1,32}$")
RE_MD = re.compile(r"^([0-9]{2}[a-z0-9]{0,8})-([A-Za-z0-9._-]{1,120})\.md$")
MAX_BYTES = 1024 * 1024


def indice_de_carpeta(carpeta):
    """Los NN-slug.md de la carpeta (sin RESULTADO ni PLAN): los mismos que lista la pestaña con `find`."""
    ids = []
    for p in sorted(carpeta.glob("[0-9]*-*.md")):
        m = RE_MD.match(p.name)
        if m and not re.fullmatch(r"[A-Z]+", m[2]):
            ids.append(m[1])
    return list(dict.fromkeys(ids))


def revisar(texto, indice):
    """Devuelve (errores, avisos)."""
    errores, avisos = [], []
    if len(texto.encode("utf-8")) > MAX_BYTES:
        return ["proyectos.json pesa más de 1 MB (la pestaña no lo lee)"], avisos
    try:
        d = json.loads(texto)
    except json.JSONDecodeError as e:
        return [f"JSON inválido: {e}"], avisos
    if not isinstance(d, dict):
        return ["la raíz no es un objeto"], avisos
    if d.get("columnas") != COLUMNAS:
        errores.append(f"«columnas» tiene que ser {COLUMNAS}")
    topes = d.get("tope_wip", {})
    if not isinstance(topes, dict):
        errores.append("«tope_wip» no es un objeto")
        topes = {}
    for c, v in topes.items():
        if c not in COLUMNAS:
            errores.append(f"tope_wip: la columna «{c}» no existe")
        elif not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            errores.append(f"tope_wip: el tope de «{c}» tiene que ser un entero positivo")
    aging = d.get("aging_dias", 7)
    if not isinstance(aging, int) or isinstance(aging, bool) or not 0 < aging < 366:
        errores.append("«aging_dias» tiene que ser un entero entre 1 y 365")
    proyectos = d.get("proyectos")
    if not isinstance(proyectos, list) or not proyectos:
        return errores + ["«proyectos» tiene que ser una lista con al menos un proyecto"], avisos
    duenos, vistos, abiertos_por_columna = {}, set(), {c: [] for c in COLUMNAS}
    for i, p in enumerate(proyectos):
        if not isinstance(p, dict):
            errores.append(f"proyecto {i}: no es un objeto")
            continue
        pid = p.get("id")
        if not isinstance(pid, str) or not RE_PROYECTO.match(pid):
            errores.append(f"proyecto {i}: id «{pid}» no vale (minúsculas, dígitos, - o _)")
            continue
        if pid in vistos:
            errores.append(f"proyecto «{pid}» repetido")
        vistos.add(pid)
        for campo in ("nombre", "resultado"):
            if not isinstance(p.get(campo), str) or not p.get(campo).strip():
                errores.append(f"{pid}: falta «{campo}»")
        encargos = p.get("encargos", [])
        abiertos = p.get("abiertos", {})
        if not isinstance(encargos, list):
            errores.append(f"{pid}: «encargos» no es una lista")
            encargos = []
        if not isinstance(abiertos, dict):
            errores.append(f"{pid}: «abiertos» no es un objeto")
            abiertos = {}
        for e in encargos:
            if not isinstance(e, str) or not RE_ID.match(e):
                errores.append(f"{pid}: el encargo «{e}» no tiene la forma NN o NNx")
        for e, col in abiertos.items():
            if not RE_ID.match(e):
                errores.append(f"{pid}: «abiertos» tiene el id «{e}», que no tiene la forma NN o NNx")
            if col not in COLUMNAS:
                errores.append(f"{pid}: «abiertos» pone {e} en «{col}», que no es una columna")
            else:
                abiertos_por_columna[col].append(e)
        for e in set(x for x in encargos if isinstance(x, str)) | set(abiertos):
            if e in duenos and duenos[e] != pid:
                errores.append(f"el encargo {e} está en dos proyectos: {duenos[e]} y {pid}")
            duenos.setdefault(e, pid)
        for campo, tipo in (("docs", list), ("ideas", list), ("bloqueo", str)):
            if campo in p and not isinstance(p[campo], tipo):
                errores.append(f"{pid}: «{campo}» tiene un tipo que no corresponde")
    compartidos = d.get("archivos_compartidos", {})
    if not isinstance(compartidos, dict):
        errores.append("«archivos_compartidos» no es un objeto")
        compartidos = {}
    for ruta, ids in compartidos.items():
        if ruta.startswith("_"):
            continue
        if not isinstance(ids, list) or not all(isinstance(x, str) and RE_ID.match(x) for x in ids):
            errores.append(f"archivos_compartidos: «{ruta}» tiene que ser una lista de ids")
    for c, tope in topes.items():
        if c in abiertos_por_columna and isinstance(tope, int) and len(abiertos_por_columna[c]) > tope:
            avisos.append(f"{c}: {len(abiertos_por_columna[c])} en «abiertos», tope {tope} ({', '.join(abiertos_por_columna[c])})")
    # Un número sin letra cubre sus variantes (23 cubre 23a…23h), como en la pestaña.
    sin = [e for e in indice if e not in duenos and re.match(r"\d+", e)[0] not in duenos]
    if sin:
        errores.append(f"encargos del índice sin proyecto: {', '.join(sin)} (agrégalos a un proyecto, aunque sea a «otros»)")
    return errores, avisos


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("archivo", nargs="?", default=str(AQUI / "proyectos.json"))
    a.add_argument("--indice", help="JSON con la lista del índice ([{id, …}] o [id, …]); por omisión, los NN-*.md de la carpeta del archivo")
    o = a.parse_args(argv)
    ruta = pathlib.Path(o.archivo)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as e:
        print(f"ERROR: no se pudo leer {ruta}: {e.strerror}")
        return 1
    if o.indice:
        crudo = json.loads(pathlib.Path(o.indice).read_text(encoding="utf-8"))
        indice = [x["id"] if isinstance(x, dict) else x for x in crudo]
    else:
        indice = indice_de_carpeta(ruta.parent)
    errores, avisos = revisar(texto, indice)
    for x in errores:
        print(f"ERROR: {x}")
    for x in avisos:
        print(f"AVISO: {x}")
    print(f"{ruta.name}: {len(errores)} error(es), {len(avisos)} aviso(s); índice de {len(indice)} encargos")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
