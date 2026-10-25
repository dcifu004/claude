#!/usr/bin/env python3
"""Lector de la memoria IA para la herramienta 🧠 Memoria de Cockpit (encargo 25, documento 30).

    python3 memoria-cockpit.py            # JSON por stdout; lo llamará la página con cockpit.spawn
    python3 memoria-cockpit.py --indent   # lo mismo, legible
    python3 memoria-cockpit.py --carpeta DIR --montaje DIR --vault DIR --umbral-bytes N --dias-antigua N

Sólo lectura, sin `sudo`, sólo stdlib. No escribe ni arregla nada: abre los archivos para leer y
nada más. Mira ÚNICAMENTE el primer nivel de la carpeta; no baja a las subcarpetas.

Qué es cada cosa:
  - nota       = todo `.md` del primer nivel que no sea el índice (`MEMORY.md`) ni un conflicto de
                 Syncthing. Los que no son memorias (sin `type`) cuentan como nota y salen en
                 `salud.sin_type`: así sus enlaces rotos no se pierden.
  - wikilink   = cada `[[destino]]` de una nota, contando repetidos. Se resuelve contra el `name`
                 del frontmatter Y contra el nombre de archivo sin `.md` (trampa del doc 30).
  - roto       = wikilink que no resuelve a ninguna nota. Único = par (origen, destino). Cada roto
                 dice además `en_vault`: true si ese nombre existe como `.md` en otra parte del vault
                 (`rutas_vault`, hasta 3, relativas al vault) y false si no existe en ningún lado;
                 `resumen.rotos_en_vault` cuenta los true. Sin `vault` esos campos no salen y el JSON
                 es idéntico al de antes. Sólo se recorren nombres de archivo, sin leerlos.
  - entrante   = otra nota que enlaza a ésta (una nota no se cuenta a sí misma).

Volumen cerrado: la memoria vive dentro del LUKS. Si `--montaje` no es un punto de montaje y la
carpeta no existe o no tiene notas, el estado es `volumen_cerrado`. Nunca sale `ok` con cero notas:
la memoria vacía en silencio ya engañó una vez. Cuando el estado no es `ok` el JSON NO trae `notas`,
`salud` ni `resumen` (ni siquiera vacíos): la página no puede dibujar «0 notas» por descuido.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

CARPETA = "/opt/nodo/datos/srv/vault_personal/90-Referencia/00-MemoriaIA"
MONTAJE = "/opt/nodo/datos"
VAULT = "/opt/nodo/datos/srv/vault_personal"     # donde se busca el destino de un enlace roto
MAX_RUTAS_VAULT = 3       # cuántas rutas se entregan por destino que existe en el vault
INDICE = "MEMORY.md"
UMBRAL_BYTES = 12_000     # una nota es «un hecho»: sobre ~12 KB (~3.000 tokens) conviene partirla
DIAS_ANTIGUA = 90
MAX_LECTURA = 1_000_000   # tope por archivo; lo que pase de ahí se marca `truncada`
INFRAESTRUCTURA = {".stfolder", ".stignore", ".stversions"}     # de Syncthing, no son ajenos

MARCA_CONFLICTO = ".sync-conflict-"
_CONFLICTO = re.compile(r"^(?P<base>.+?)\.sync-conflict-(?P<fecha>\d{8}-\d{6})-(?P<equipo>[A-Z0-9]+)(?P<ext>\.[^.]*)?$")
_WIKILINK = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
_CERCA = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODIGO_EN_LINEA = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_ENLACE_MD = re.compile(r"\]\(\s*(?:<([^>\n]+)>|([^)\s]+))")
_CLAVE = re.compile(r"^(\s*)([A-Za-z_][\w.-]*)\s*:(?:\s+(.*)|\s*)$")


def _norma(texto: str) -> str:
    return unicodedata.normalize("NFC", texto).strip()


def _iso(segundos: float) -> str:
    return datetime.fromtimestamp(segundos).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Frontmatter (YAML mínimo: no hay PyYAML en stdlib)
# ---------------------------------------------------------------------------

def _escalar(valor: str) -> str:
    valor = valor.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] == '"':
        try:
            return str(json.loads(valor))
        except ValueError:
            return valor[1:-1]
    if len(valor) >= 2 and valor[0] == valor[-1] == "'":
        return valor[1:-1].replace("''", "'")
    return re.sub(r"\s+#.*$", "", valor)


def leer_frontmatter(texto: str) -> tuple[dict | None, str]:
    """Devuelve (frontmatter, cuerpo). Sin bloque `---` inicial y cerrado, frontmatter es None.

    Entiende lo que escriben Claude y Codex en esta memoria: claves `clave: valor`, un nivel de
    anidamiento por sangría (`metadata:`), comillas, y escalares de varias líneas (`>`, `|` o
    continuación sangrada). Lo que no entiende lo salta; nunca lanza.
    """
    lineas = texto.split("\n")
    if not lineas or lineas[0].strip() != "---":
        return None, texto
    fin = next((i for i in range(1, len(lineas)) if lineas[i].strip() in ("---", "...")), None)
    if fin is None:
        return None, texto
    datos: dict = {}
    padre: dict | None = None          # dict del bloque anidado abierto
    sangria_padre = 0
    ultimo: tuple[dict, str, int] | None = None   # (dict, clave, sangría) del último escalar, para continuaciones
    for cruda in lineas[1:fin]:
        if not cruda.strip() or cruda.lstrip().startswith("#"):
            continue
        m = _CLAVE.match(cruda)
        sangria = len(cruda) - len(cruda.lstrip(" "))
        if not m or (ultimo and sangria > ultimo[2]):       # continuación de un escalar largo
            if ultimo:
                d, k, _ = ultimo
                d[k] = (d[k] + " " + cruda.strip()).strip()
            continue
        clave, valor = m.group(2), m.group(3)
        if padre is not None and sangria <= sangria_padre:
            padre = None
        destino = padre if padre is not None else datos
        if valor is None or valor.strip() == "":
            if padre is None:           # abre un bloque anidado (o queda vacío si no trae hijos)
                datos[clave] = {}
                padre, sangria_padre = datos[clave], sangria
            else:
                destino[clave] = ""
            ultimo = None
            continue
        if valor.strip() in (">", "|", ">-", "|-", ">+", "|+"):
            destino[clave] = ""
        else:
            destino[clave] = _escalar(valor)
        ultimo = (destino, clave, sangria)
    for clave, valor in list(datos.items()):       # `metadata:` sin hijos no es un bloque
        if valor == {}:
            datos[clave] = ""
    return datos, "\n".join(lineas[fin + 1:])


def _campo(fm: dict | None, clave: str) -> str | None:
    """`clave` del frontmatter: primero en `metadata`, después en la raíz. Vacío cuenta como ausente."""
    if not fm:
        return None
    meta = fm.get("metadata")
    for origen in (meta if isinstance(meta, dict) else {}, fm):
        valor = origen.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return None


# ---------------------------------------------------------------------------
# Wikilinks e índice
# ---------------------------------------------------------------------------

def wikilinks(cuerpo: str) -> list[tuple[str, bool]]:
    """Cada `[[destino]]` del texto, en orden y con repetidos: (destino, está_dentro_de_código).

    Del destino se quita el alias (`|alias`), la sección (`#título`) y un `.md` final. Los que
    están dentro de código (`` `[[así]]` `` o un bloque cercado) SE CUENTAN igual, porque la
    medición del doc 30 los cuenta, pero van marcados: suelen ser un ejemplo y no un enlace.
    """
    salida = []
    cerca = None
    for linea in cuerpo.split("\n"):
        m = _CERCA.match(linea)
        if m:
            marca = m.group(1)
            if cerca is None:
                cerca = marca[0] * 3
            elif marca.startswith(cerca):
                cerca = None
            continue
        tramos = [] if cerca else [c.span(2) for c in _CODIGO_EN_LINEA.finditer(linea)]
        for w in _WIKILINK.finditer(linea):
            destino = _norma(w.group(1).split("|", 1)[0].split("#", 1)[0])
            if destino.lower().endswith(".md"):
                destino = destino[:-3].rstrip()
            if destino:
                en_codigo = bool(cerca) or any(a <= w.start() and w.end() <= b for a, b in tramos)
                salida.append((destino, en_codigo))
    return salida


def leer_indice(texto: str) -> list[dict]:
    """Enlaces `[título](archivo.md)` de MEMORY.md, con su número de línea. Ignora URL y anclas."""
    entradas = []
    for n, linea in enumerate(texto.split("\n"), 1):
        for m in _ENLACE_MD.finditer(linea):
            destino = unquote(m.group(1) or m.group(2)).split("#", 1)[0].strip()
            if not destino or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", destino):
                continue
            while destino.startswith("./"):
                destino = destino[2:]
            entradas.append({"linea": n, "destino": _norma(destino), "texto": linea.strip()[:200]})
    return entradas


# ---------------------------------------------------------------------------
# Lectura de la carpeta
# ---------------------------------------------------------------------------

def _leer(ruta: Path) -> tuple[str, bool]:
    """Texto del archivo (UTF-8 tolerante, sin BOM ni CR) y si quedó truncado por el tope."""
    with open(ruta, "rb") as f:
        crudo = f.read(MAX_LECTURA + 1)
    truncado = len(crudo) > MAX_LECTURA
    texto = crudo[:MAX_LECTURA].decode("utf-8", errors="replace")
    return texto.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n"), truncado


def _dentro(ruta: str, raiz: str) -> bool:
    ruta, raiz = os.path.abspath(ruta), os.path.abspath(raiz)
    return ruta == raiz or ruta.startswith(raiz.rstrip(os.sep) + os.sep)


def _fecha_frontmatter(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone() if d.tzinfo else d.replace(tzinfo=datetime.now().astimezone().tzinfo)


def _clave_destino(destino: str) -> str:
    """Un destino como lo compara Obsidian: sólo el nombre final, sin `.md`, sin mayúsculas."""
    nombre = destino.replace("\\", "/").rsplit("/", 1)[-1]
    if nombre.lower().endswith(".md"):
        nombre = nombre[:-3]
    return _norma(nombre).casefold()


def indexar_vault(vault: str) -> dict[str, list[str]]:
    """Nombre sin `.md` (casefold) -> rutas relativas de todos los `.md` del vault. No lee contenido.
    Salta carpetas ocultas (.git, .obsidian, .stversions…) y no sigue enlaces simbólicos."""
    indice: dict[str, list[str]] = {}
    vault = os.path.abspath(vault)
    for raiz, carpetas, archivos in os.walk(vault, followlinks=False):
        carpetas[:] = sorted(c for c in carpetas if not c.startswith("."))
        for a in sorted(archivos):
            if a.lower().endswith(".md") and MARCA_CONFLICTO not in a:
                ruta = os.path.relpath(os.path.join(raiz, a), vault).replace(os.sep, "/")
                indice.setdefault(_norma(a[:-3]).casefold(), []).append(ruta)
    return indice


def _conflicto(nombre: str, info: os.stat_result, ahora: datetime) -> dict:
    """Copia que deja Syncthing cuando dos equipos editan lo mismo: `<base>.sync-conflict-<fecha>-<hora>-<equipo>.<ext>`."""
    c = {"archivo": nombre, "original": None, "equipo": None, "fecha": None, "dias": None,
         "mtime": _iso(info.st_mtime), "bytes": info.st_size}
    m = _CONFLICTO.match(nombre)
    if m:
        c.update(original=m["base"] + (m["ext"] or ""), equipo=m["equipo"])
        try:
            fecha = datetime.strptime(m["fecha"], "%Y%m%d-%H%M%S").replace(tzinfo=ahora.tzinfo)
            c.update(fecha=fecha.isoformat(timespec="seconds"), dias=max(0, (ahora.date() - fecha.date()).days))
        except ValueError:
            pass
    return c


def _salida(carpeta: str, ahora: datetime, estado: str, motivo: str = "", detalle: str = "",
            montado: bool | None = None, **resto) -> dict:
    base = {"generado": ahora.isoformat(timespec="seconds"), "carpeta": carpeta, "estado": estado,
            "motivo": motivo, "detalle": detalle, "montado": montado}
    base.update(resto)
    return base


def recolectar(carpeta: str = CARPETA, montaje: str = MONTAJE, umbral_bytes: int = UMBRAL_BYTES,
               dias_antigua: int = DIAS_ANTIGUA, ahora: datetime | None = None,
               es_montaje=os.path.ismount, vault: str | None = None) -> dict:
    """Lee la carpeta y arma el JSON. `ahora` y `es_montaje` se inyectan en las pruebas.
    `vault` (None = no buscar) es la raíz donde se mira si un destino roto existe fuera de la memoria."""
    ahora = (ahora or datetime.now()).astimezone()
    carpeta = os.path.abspath(carpeta)
    # El montaje sólo opina si la carpeta vive adentro; None = no aplica (p. ej. una carpeta de prueba).
    montado = bool(es_montaje(montaje)) if montaje and _dentro(carpeta, montaje) else None
    cerrado = dict(motivo="sin_montar", montado=False,
                   detalle=f"🔒 volumen cerrado: {montaje} no está montado (corre sudo abrir-datos)")

    try:
        entradas = sorted(os.scandir(carpeta), key=lambda e: e.name)
    except FileNotFoundError:
        if montado is False:
            return _salida(carpeta, ahora, "volumen_cerrado", **cerrado)
        return _salida(carpeta, ahora, "error", "carpeta_inexistente",
                       "la carpeta de la memoria no existe" + (" aunque el volumen está montado" if montado else ""),
                       montado)
    except OSError as e:
        return _salida(carpeta, ahora, "error", "sin_acceso",
                       f"no se pudo leer la carpeta: {e.strerror or type(e).__name__}", montado)

    notas: list[dict] = []
    conflictos, ajenos = [], []
    indice = {"archivo": INDICE, "existe": False, "entradas": 0, "lineas": 0, "bytes": 0, "mtime": None}
    entradas_indice: list[dict] = []
    archivos_md = 0
    regulares: set[str] = set()

    for e in entradas:
        try:
            info = e.stat(follow_symlinks=False)
        except OSError:
            continue
        regular = stat.S_ISREG(info.st_mode)
        if regular:
            regulares.add(e.name)
        es_md = regular and e.name.lower().endswith(".md")
        archivos_md += es_md
        if MARCA_CONFLICTO in e.name:
            conflictos.append(_conflicto(e.name, info, ahora))
            continue
        if not es_md:
            if e.name not in INFRAESTRUCTURA:
                tipo = "carpeta" if stat.S_ISDIR(info.st_mode) else "enlace" if stat.S_ISLNK(info.st_mode) else "archivo"
                ajenos.append({"nombre": e.name, "tipo": tipo})
            continue
        try:
            texto, truncada = _leer(Path(e.path))
            error = None
        except OSError as err:
            texto, truncada, error = "", False, f"no se pudo leer: {err.strerror or type(err).__name__}"
        if e.name == INDICE:
            entradas_indice = leer_indice(texto)
            indice.update(existe=True, entradas=len(entradas_indice), lineas=len(texto.splitlines()),
                          bytes=info.st_size, mtime=_iso(info.st_mtime))
            if error:
                indice["error"] = error
            continue
        fm, cuerpo = leer_frontmatter(texto)
        modificado = _fecha_frontmatter(_campo(fm, "modified"))
        cambio = datetime.fromtimestamp(info.st_mtime).astimezone()
        if modificado and modificado > cambio:
            cambio = modificado
        nota = {
            "archivo": e.name,
            "name": _campo(fm, "name"),
            "description": _campo(fm, "description"),
            "type": _campo(fm, "type"),
            "modified": _campo(fm, "modified"),
            "mtime": _iso(info.st_mtime),
            "bytes": info.st_size,
            "frontmatter": fm is not None,
            "salientes": [],
            "entrantes": {"cuenta": 0, "notas": []},
            "en_indice": False,
            "ultimo_cambio": cambio.isoformat(timespec="seconds"),
            "dias_sin_cambio": max(0, (ahora.date() - cambio.date()).days),
            "_enlaces": wikilinks(cuerpo),
        }
        if truncada:
            nota["truncada"] = True
        if error:
            nota["error"] = error
        notas.append(nota)

    if not notas:
        if montado is False:
            return _salida(carpeta, ahora, "volumen_cerrado", **cerrado)
        return _salida(carpeta, ahora, "error", "carpeta_vacia",
                       "la carpeta existe pero no tiene ninguna nota .md"
                       + (" aunque el volumen está montado: ¿Syncthing terminó de sincronizar?" if montado else ""),
                       montado)

    # --- Resolución: por `name` y por nombre de archivo; exacto primero, sin mayúsculas después ---
    exacto: dict[str, str] = {}
    flojo: dict[str, str] = {}
    for clave_de in (lambda n: n["archivo"][:-3], lambda n: n["name"]):     # el archivo manda sobre el name
        for n in notas:
            clave = clave_de(n)
            if clave:
                exacto.setdefault(_norma(clave), n["archivo"])
                flojo.setdefault(_norma(clave).casefold(), n["archivo"])

    def resolver(destino: str) -> str | None:
        return exacto.get(destino) or flojo.get(destino.casefold())

    por_archivo = {n["archivo"]: n for n in notas}
    rotos: dict[tuple[str, str], dict] = {}
    total_wikilinks = total_rotos = 0
    for n in notas:
        vistos: dict[str, dict] = {}
        for destino, en_codigo in n.pop("_enlaces"):
            total_wikilinks += 1
            s = vistos.get(destino)
            if s is None:
                s = vistos[destino] = {"destino": destino, "nota": resolver(destino), "veces": 0}
                n["salientes"].append(s)
            s["veces"] += 1
            if s["nota"] is None:
                total_rotos += 1
                r = rotos.setdefault((n["archivo"], destino), {"origen": n["archivo"], "destino": destino,
                                                               "veces": 0, "en_codigo": True})
                r["veces"] += 1
                r["en_codigo"] = r["en_codigo"] and en_codigo     # sólo si TODAS las apariciones son código
            elif s["nota"] != n["archivo"] and n["archivo"] not in por_archivo[s["nota"]]["entrantes"]["notas"]:
                por_archivo[s["nota"]]["entrantes"]["notas"].append(n["archivo"])
    for n in notas:
        n["entrantes"]["cuenta"] = len(n["entrantes"]["notas"])

    # --- Índice ---
    en_indice = {x["destino"] for x in entradas_indice}
    indice_sin_archivo = []
    for x in entradas_indice:
        d = x["destino"]
        existe = d in regulares if "/" not in d else (_dentro(os.path.join(carpeta, d), carpeta)
                                                      and os.path.isfile(os.path.join(carpeta, d)))
        if not existe:
            indice_sin_archivo.append(x)
    for n in notas:
        n["en_indice"] = n["archivo"] in en_indice

    lista_rotos = sorted(rotos.values(), key=lambda r: (r["origen"], r["destino"]))
    buscado = bool(vault) and os.path.isdir(vault)       # sin vault el formato es exactamente el de la Fase 1
    if buscado:
        en_vault = indexar_vault(vault) if lista_rotos else {}
        for r in lista_rotos:
            rutas = en_vault.get(_clave_destino(r["destino"]), [])
            r["en_vault"] = bool(rutas)
            r["rutas_vault"] = rutas[:MAX_RUTAS_VAULT]
    salud = {
        "enlaces_rotos": {"total": total_rotos, "unicos": lista_rotos},
        "sin_entrantes": [n["archivo"] for n in notas if n["entrantes"]["cuenta"] == 0],
        "fuera_de_indice": [n["archivo"] for n in notas if not n["en_indice"]],
        "indice_sin_archivo": indice_sin_archivo,
        "name_distinto": [{"archivo": n["archivo"], "name": n["name"]} for n in notas
                          if n["name"] and _norma(n["name"]) != _norma(n["archivo"][:-3])],
        "sobre_umbral": sorted(({"archivo": n["archivo"], "bytes": n["bytes"]} for n in notas
                                if n["bytes"] > umbral_bytes), key=lambda x: -x["bytes"]),
        "conflictos": conflictos,
        "sin_type": [n["archivo"] for n in notas if not n["type"]],
        "antiguas": sorted(({"archivo": n["archivo"], "dias_sin_cambio": n["dias_sin_cambio"]} for n in notas
                            if n["dias_sin_cambio"] >= dias_antigua), key=lambda x: -x["dias_sin_cambio"]),
        "ajenos": ajenos,
    }
    por_tipo: dict[str, int] = {}
    for n in notas:
        por_tipo[n["type"] or "sin_type"] = por_tipo.get(n["type"] or "sin_type", 0) + 1
    resumen = {
        "notas": len(notas),
        "archivos_md": archivos_md,       # notas + índice + conflictos .md: es el «71» del doc 30
        "bytes": sum(n["bytes"] for n in notas),
        "wikilinks": total_wikilinks,
        "rotos_unicos": len(lista_rotos),
        "rotos_total": total_rotos,
        "rotos_en_codigo": sum(1 for r in lista_rotos if r["en_codigo"]),
        "sin_entrantes": len(salud["sin_entrantes"]),
        "fuera_de_indice": len(salud["fuera_de_indice"]),
        "indice_sin_archivo": len(indice_sin_archivo),
        "name_distinto": len(salud["name_distinto"]),
        "sobre_umbral": len(salud["sobre_umbral"]),
        "conflictos": len(conflictos),
        "sin_type": len(salud["sin_type"]),
        "antiguas": len(salud["antiguas"]),
        "ajenos": len(ajenos),
        "por_tipo": dict(sorted(por_tipo.items())),
    }
    if buscado:
        resumen["rotos_en_vault"] = sum(1 for r in lista_rotos if r["en_vault"])
    return _salida(carpeta, ahora, "ok", montado=montado, umbral_bytes=umbral_bytes, dias_antigua=dias_antigua,
                   indice=indice, notas=notas, salud=salud, resumen=resumen)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Lee la memoria IA y entrega un JSON (sólo lectura).")
    p.add_argument("--carpeta", default=CARPETA)
    p.add_argument("--montaje", default=MONTAJE, help="punto de montaje del volumen cifrado")
    p.add_argument("--vault", default=VAULT, help="raíz del vault, para ubicar los destinos rotos (vacío = no buscar)")
    p.add_argument("--umbral-bytes", type=int, default=UMBRAL_BYTES)
    p.add_argument("--dias-antigua", type=int, default=DIAS_ANTIGUA)
    p.add_argument("--indent", action="store_true")
    a = p.parse_args(argv)
    try:
        salida = recolectar(a.carpeta, a.montaje, a.umbral_bytes, a.dias_antigua, vault=a.vault or None)
    except Exception as e:      # la página siempre recibe un JSON con estado, nunca un traceback
        salida = _salida(os.path.abspath(a.carpeta), datetime.now().astimezone(), "error", "interno",
                         f"{type(e).__name__}: {e}")
    print(json.dumps(salida, ensure_ascii=False, indent=2 if a.indent else None))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
