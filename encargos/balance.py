#!/usr/bin/env python3
"""Balance de los encargos: cuánto se va en retrabajo, por familia (encargo 47a).

    python3 encargos/balance.py [--historial RUTA] [--manifiestos DIR] [--desde NN] [--json]

Sólo lee: `historial.jsonl` (una fila por fase, la escribe cola-run.py) y los `cola-*.toml` de la
carpeta de manifiestos. No crea ni toca ningún archivo, no manda avisos y no usa red. El resumen sale
por stdout en texto plano y cabe en un mensaje de Telegram (≤ 3500 caracteres). Con `--json` sale lo mismo
como datos, en una línea y sin recortar (encargo 50a): es lo que `cola-run.py --panel` publica en `pasado`.

- Retrabajo: las fases `fix*`, las revisiones desde la segunda (`rev2`, `rev3`…) y la segunda vuelta de plan (`plan2`, `revplan2`).
- Tokens en retrabajo: Claude y Codex no se pueden sumar (Claude cuenta caché, Codex un solo total),
  así que van aparte: Claude pesado por `tokens.usd` y Codex por `tokens.total`.
- Error del pronóstico: mediana de |min real − min pronosticado| / min pronosticado, por fase.
- El historial se lee sin lock y línea a línea, porque cola-run.py lo escribe con colas vivas: una
  línea a medio escribir o rota se salta y se cuenta al pie.
- Los manifiestos se abren sólo dentro de `--manifiestos`, sin seguir enlaces simbólicos y sólo si
  son archivos regulares. La etapa se asocia al encargo por el `id` de `[[etapa]]`, no por el nombre
  del archivo.
"""
import argparse
import fnmatch
import json
import math
import os
import re
import stat
import statistics
import sys
import tomllib
from pathlib import Path

AQUI = Path(__file__).resolve().parent
LIMITE = 3500                    # caracteres: un mensaje de Telegram con holgura
MAX_MANIFIESTO = 1 << 20         # un cola-*.toml real pesa 1–4 KB
RETRABAJO = re.compile(r"(fix\d*|rev([2-9]|\d{2,})|plan2|revplan2)$")
SIN_DATO = "sin dato"


# ---------------------------------------------------------------- lectura

def _abrir_regular(ruta, dir_fd=None, seguir=True):
    """Abre para leer y devuelve el descriptor sólo si es un archivo regular. O_NONBLOCK evita que
    un FIFO deje colgado el open; sin `seguir`, un enlace simbólico final falla con ELOOP."""
    banderas = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | (0 if seguir else os.O_NOFOLLOW)
    fd = os.open(ruta, banderas, dir_fd=dir_fd)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise OSError("no es un archivo regular")
    return fd


def leer_historial(ruta):
    """(filas, saltadas): las filas útiles y cuántas líneas se saltaron por JSON roto o por no traer
    `encargo` y `fase`."""
    filas, saltadas = [], 0
    with os.fdopen(_abrir_regular(ruta), "rb") as fh:
        for cruda in fh:
            linea = cruda.decode("utf-8", errors="replace").strip()
            if not linea:
                continue
            try:
                fila = json.loads(linea)
            except ValueError:
                saltadas += 1
                continue
            if not (isinstance(fila, dict) and _texto(fila.get("encargo")) and _texto(fila.get("fase"))):
                saltadas += 1
                continue
            filas.append(fila)
    return filas, saltadas


def leer_manifiestos(carpeta):
    """(etapas, ilegibles): `etapas` va de id de etapa a {naturaleza, afinado, experimento}, con
    `afinado` y `experimento` tomados de la raíz de su manifiesto. Si un id sale en varios manifiestos
    gana el último en orden de nombre (la cola que lo relanzó). Lo que no se pudo leer (enlace,
    no regular, TOML roto) queda en `ilegibles`; una carpeta que falta no es un error: sale todo
    «sin dato»."""
    etapas, ilegibles = {}, []
    try:
        dfd = os.open(carpeta, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError:
        return etapas, ilegibles
    try:
        nombres = sorted((n for n in os.listdir(dfd) if fnmatch.fnmatchcase(n, "cola-*.toml")), key=_orden)
        for n in nombres:
            try:
                with os.fdopen(_abrir_regular(n, dir_fd=dfd, seguir=False), "rb") as fh:
                    crudo = fh.read(MAX_MANIFIESTO + 1)
                if len(crudo) > MAX_MANIFIESTO:
                    raise ValueError("demasiado grande")
                man = tomllib.loads(crudo.decode("utf-8"))
            except (OSError, ValueError):      # TOMLDecodeError y UnicodeDecodeError son ValueError
                ilegibles.append(_texto(n))
                continue
            lista = man.get("etapa")
            for et in lista if isinstance(lista, list) else []:
                if isinstance(et, dict) and _texto(et.get("id")):
                    etapas[_texto(et["id"])] = {"naturaleza": et.get("naturaleza"),
                                                "afinado": man.get("afinado"),
                                                "experimento": man.get("experimento")}
    finally:
        os.close(dfd)
    return etapas, ilegibles


# ---------------------------------------------------------------- valores tolerantes

def _texto(v, largo=24):
    """Un valor del historial o de un manifiesto como texto de una línea: sin saltos ni caracteres
    de control, recortado. Lo que no es texto ni número vale vacío."""
    if isinstance(v, bool) or not isinstance(v, (str, int)):
        return ""
    limpio = " ".join("".join(c if c.isprintable() else " " for c in str(v)).split())
    return limpio[:largo]


def _num(v):
    """Un número finito y no negativo, o 0: `min`, `usd` y `total` pueden faltar o venir mal."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        return 0.0
    return float(v)


def _orden(ident):
    """Orden natural de encargos y manifiestos: 22 < 22b < 23a < 100."""
    m = re.search(r"\d+", ident)
    return (int(m.group()) if m else math.inf, ident)


def numero(ident):
    m = re.match(r"\d+", ident)
    return int(m.group()) if m else None


def _tokens(fila):
    t = fila.get("tokens")
    return t if isinstance(t, dict) else {}


def _error_pronostico(fila):
    p = fila.get("pronostico")
    pron = _num(p.get("min")) if isinstance(p, dict) else 0.0
    if pron <= 0 or fila.get("sin_cuota") is True or not isinstance(fila.get("min"), (int, float)):
        return None
    return abs(_num(fila["min"]) - pron) / pron


# ---------------------------------------------------------------- cálculo

def agrupar(filas, etapas, desde=None):
    """Lista de encargos en orden natural; cada uno con sus fases y la familia a la que pertenece."""
    por_id = {}
    for f in filas:
        por_id.setdefault(_texto(f["encargo"]), []).append(f)
    encargos = []
    for ident in sorted(por_id, key=_orden):
        if desde is not None and (numero(ident) is None or numero(ident) < desde):
            continue
        fases, et = por_id[ident], etapas.get(ident)
        naturaleza = _texto((et or {}).get("naturaleza")) or next(
            (_texto(f.get("naturaleza")) for f in fases if _texto(f.get("naturaleza"))), "") or SIN_DATO
        afinado = _texto((et or {}).get("afinado")).lower()
        experimento = _texto((et or {}).get("experimento"))
        veredictos = [_texto(f.get("veredicto")).upper() for f in fases
                      if _texto(f["fase"]) == "rev1" and _texto(f.get("veredicto"))]
        encargos.append({
            "id": ident, "fases": fases, "con_manifiesto": et is not None,
            "naturaleza": naturaleza,
            "afinado": afinado if afinado in ("completo", "ligero") else SIN_DATO,
            "experimento": experimento or ("ninguno" if et is not None else SIN_DATO),
            # una rev1 repetida (cola relanzada) vale por su último veredicto
            "primera": (veredictos[-1] == "DESPLEGABLE") if veredictos else None,
            "revisiones": sum(1 for f in fases if _texto(f["fase"]).startswith("rev")),
        })
    return encargos


def medir(fases):
    """Sumas de un conjunto de fases: minutos, USD de Claude y tokens de Codex, total y en retrabajo."""
    m = {"n": len(fases), "min": 0.0, "min_ret": 0.0, "usd": 0.0, "usd_ret": 0.0, "tok": 0.0, "tok_ret": 0.0}
    errores = []
    for f in fases:
        t = _tokens(f)
        valores = {"min": _num(f.get("min")), "usd": _num(t.get("usd")), "tok": _num(t.get("total"))}
        ret = bool(RETRABAJO.fullmatch(_texto(f["fase"])))
        for k, v in valores.items():
            m[k] += v
            if ret:
                m[k + "_ret"] += v
        e = _error_pronostico(f)
        if e is not None:
            errores.append(e)
    m["error"] = statistics.median(errores) if errores else None
    return m


def medir_encargos(encargos):
    m = medir([f for e in encargos for f in e["fases"]])
    m["encargos"] = len(encargos)
    m["revisados"] = sum(1 for e in encargos if e["primera"] is not None)
    m["aprobados"] = sum(1 for e in encargos if e["primera"])
    return m


def combos(encargos):
    """Fases por (motor, modelo, esfuerzo, rol), de más a menos minutos. `esfuerzo` vacío y nulo van
    juntos como «—»."""
    grupos = {}
    for e in encargos:
        for f in e["fases"]:
            clave = (_texto(f.get("motor")) or SIN_DATO, _texto(f.get("modelo")) or SIN_DATO,
                     _texto(f.get("esfuerzo")) or "—", _texto(f.get("rol")) or SIN_DATO)
            grupos.setdefault(clave, []).append(f)
    return sorted(((c, medir(fs)) for c, fs in grupos.items()), key=lambda cm: (-cm[1]["min"], cm[0]))


# ---------------------------------------------------------------- texto

def _dec(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def _pct(parte, todo):
    return f"{round(100 * parte / todo)} %" if todo > 0 else "–"


def _linea_familia(nombre, m):
    n = m["encargos"]
    error = f"{round(100 * m['error'])} %" if m["error"] is not None else "–"
    return (f"{nombre}: {n} enc · 1ª {m['aprobados']}/{m['revisados']} · ret min {_pct(m['min_ret'], m['min'])}"
            f" · tok C {_pct(m['usd_ret'], m['usd'])} X {_pct(m['tok_ret'], m['tok'])}"
            f" · USD {_dec(m['usd'] / n, 2)} · {round(m['tok'] / n / 1000)} k · err {error}")


def _familia(encargos, campo, orden=None):
    valores = sorted({e[campo] for e in encargos}, key=orden or (lambda v: (v == SIN_DATO, v)))
    return [_linea_familia(v, medir_encargos([e for e in encargos if e[campo] == v])) for v in valores]


def _linea_combo(clave, m):
    motor, modelo, esfuerzo, rol = clave
    modelo = modelo.removeprefix(motor + "-")
    partes = [f"n {m['n']}", f"{_dec(m['min'] / m['n'])} min"]
    if motor == "claude" or m["usd"] > 0:
        partes.append(f"USD {_dec(m['usd'] / m['n'], 2)}")
    if motor == "codex" or m["tok"] > 0:
        partes.append(f"{round(m['tok'] / m['n'] / 1000)} k")
    return f"{motor} {modelo} {esfuerzo} {rol}: " + " · ".join(partes)


def resumen(filas, etapas, saltadas=0, ilegibles=(), desde=None):
    encargos = agrupar(filas, etapas, desde)
    if not encargos:
        return "Balance de encargos: no hay fases que contar" + (f" desde el {desde}" if desde is not None else "") \
            + (f" ({saltadas} líneas del historial saltadas)" if saltadas else "") + "."
    total = medir_encargos(encargos)
    cabeza = [
        f"Balance de encargos {encargos[0]['id']}–{encargos[-1]['id']}: {total['encargos']} encargos, {total['n']} fases",
        "ret = fix y rev2+ · tok ret: C = USD de Claude, X = tokens de Codex · USD y k (tokens Codex) por"
        " encargo · err = mediana del error del pronóstico de min",
        "",
        _linea_familia("TOTAL", total)
        + f" · {round(total['min_ret'])} de {round(total['min'])} min en retrabajo",
        "", "POR NATURALEZA", *_familia(encargos, "naturaleza"),
    ]
    por_combo = [_linea_combo(c, m) for c, m in combos(encargos)]
    caros = sorted(encargos, key=lambda e: -sum(_num(f.get("min")) for f in e["fases"]))[:5]
    cola = [
        "", "POR AFINADO", *_familia(encargos, "afinado", ["completo", "ligero", SIN_DATO].index),
        "", "POR EXPERIMENTO", *_familia(encargos, "experimento", lambda v: (v in ("ninguno", SIN_DATO), v)),
        "", "LOS 5 MÁS CAROS (por minutos)",
    ]
    for e in caros:
        m = medir(e["fases"])
        cola.append(f"{e['id']}: {round(m['min'])} min · USD {_dec(m['usd'], 2)} · {round(m['tok'] / 1000)} k"
                    f" · {e['revisiones']} rev")
    notas = []
    if saltadas:
        notas.append(f"{saltadas} línea(s) del historial saltada(s) por rota(s) o incompleta(s)")
    sin_manifiesto = [e["id"] for e in encargos if not e["con_manifiesto"]]
    if sin_manifiesto:
        notas.append("sin manifiesto: " + ", ".join(sin_manifiesto[:8])
                     + (f" y {len(sin_manifiesto) - 8} más" if len(sin_manifiesto) > 8 else ""))
    if ilegibles:
        notas.append("manifiestos no leídos: " + ", ".join(list(ilegibles)[:4])
                     + (f" y {len(ilegibles) - 4} más" if len(ilegibles) > 4 else ""))
    if notas:
        cola += ["", "Notas: " + "; ".join(notas) + "."]

    # Los combos son la familia que crece: si el mensaje no cabe, quedan los de más minutos.
    quedan = len(por_combo)
    while True:
        titulo = "POR MOTOR, MODELO, ESFUERZO Y ROL (por fase)"
        medio = ["", titulo, *por_combo[:quedan]]
        if quedan < len(por_combo):
            medio.append(f"… y {len(por_combo) - quedan} combinaciones más, de menos minutos")
        texto = "\n".join(cabeza + medio + cola)
        if len(texto) <= LIMITE or quedan == 0:
            break
        quedan -= 1
    return texto if len(texto) <= LIMITE else texto[:LIMITE - 12].rstrip() + "\n… (cortado)"


# ---------------------------------------------------------------- datos (--json, encargo 50a)

def _pct_num(parte, todo):
    """El número de `_pct()`, o None donde el texto pone «–»."""
    return round(100 * parte / todo) if todo > 0 else None


def _familia_datos(nombre, m):
    """Los números de `_linea_familia()`, con las mismas cuentas y los mismos redondeos."""
    n = m["encargos"]
    return {"nombre": nombre, "encargos": n, "fases": m["n"], "aprobados": m["aprobados"], "revisados": m["revisados"],
            "min": round(m["min"]), "min_ret": round(m["min_ret"]),
            "ret_min_pct": _pct_num(m["min_ret"], m["min"]), "ret_usd_pct": _pct_num(m["usd_ret"], m["usd"]),
            "ret_tok_pct": _pct_num(m["tok_ret"], m["tok"]),
            "usd_por_encargo": round(m["usd"] / n, 2), "tok_k_por_encargo": round(m["tok"] / n / 1000),
            "error_pct": round(100 * m["error"]) if m["error"] is not None else None}


def _familias_datos(encargos, campo, orden=None):
    valores = sorted({e[campo] for e in encargos}, key=orden or (lambda v: (v == SIN_DATO, v)))
    return [_familia_datos(v, medir_encargos([e for e in encargos if e[campo] == v])) for v in valores]


def _combo_datos(clave, m):
    """Los números de `_linea_combo()`. `usd_por_fase` y `tok_k_por_fase` van en None donde el texto no los pone."""
    motor, modelo, esfuerzo, rol = clave
    return {"motor": motor, "modelo": modelo.removeprefix(motor + "-"), "esfuerzo": esfuerzo, "rol": rol, "fases": m["n"],
            "min_por_fase": round(m["min"] / m["n"], 1),
            "usd_por_fase": round(m["usd"] / m["n"], 2) if motor == "claude" or m["usd"] > 0 else None,
            "tok_k_por_fase": round(m["tok"] / m["n"] / 1000) if motor == "codex" or m["tok"] > 0 else None}


def datos(filas, etapas, saltadas=0, ilegibles=(), desde=None):
    """Lo que imprime `resumen()`, como datos: las mismas familias, con los mismos cálculos (`agrupar`,
    `medir_encargos`, `combos`). No se recorta: van todas las combinaciones y todos los encargos sin manifiesto."""
    encargos = agrupar(filas, etapas, desde)
    out = {"desde": desde, "encargos": len(encargos), "primero": None, "ultimo": None, "total": None,
           "naturaleza": [], "combos": [], "afinado": [], "experimento": [], "caros": [],
           "saltadas": saltadas, "sin_manifiesto": [e["id"] for e in encargos if not e["con_manifiesto"]],
           "ilegibles": list(ilegibles)}
    if not encargos:
        return out
    caros = sorted(encargos, key=lambda e: -sum(_num(f.get("min")) for f in e["fases"]))[:5]
    medidos = [(e, medir(e["fases"])) for e in caros]
    out.update(
        primero=encargos[0]["id"], ultimo=encargos[-1]["id"], total=_familia_datos("TOTAL", medir_encargos(encargos)),
        naturaleza=_familias_datos(encargos, "naturaleza"),
        combos=[_combo_datos(c, m) for c, m in combos(encargos)],
        afinado=_familias_datos(encargos, "afinado", ["completo", "ligero", SIN_DATO].index),
        experimento=_familias_datos(encargos, "experimento", lambda v: (v in ("ninguno", SIN_DATO), v)),
        caros=[{"id": e["id"], "min": round(m["min"]), "usd": round(m["usd"], 2), "tok_k": round(m["tok"] / 1000),
                "revisiones": e["revisiones"]} for e, m in medidos])
    return out


def _desde(valor):
    n = numero(valor.strip())
    if n is None:
        raise argparse.ArgumentTypeError("se espera un número de encargo, como 36 o 39b")
    return n


def principal(argv=None):
    ap = argparse.ArgumentParser(description="Balance de los encargos (sólo lectura).")
    ap.add_argument("--historial", default=str(AQUI / "historial.jsonl"), help="historial.jsonl a leer")
    ap.add_argument("--manifiestos", default=str(AQUI), help="carpeta con los cola-*.toml")
    ap.add_argument("--desde", type=_desde, metavar="NN", help="sólo los encargos desde el número NN")
    ap.add_argument("--json", action="store_true", help="lo mismo, como datos (una línea de JSON)")
    a = ap.parse_args(argv)
    try:
        filas, saltadas = leer_historial(a.historial)
    except OSError as e:
        print(f"balance: no se pudo leer el historial {a.historial}: {e.strerror or e}", file=sys.stderr)
        return 1
    etapas, ilegibles = leer_manifiestos(a.manifiestos)
    if a.json:
        print(json.dumps(datos(filas, etapas, saltadas, ilegibles, a.desde), ensure_ascii=False))
    else:
        print(resumen(filas, etapas, saltadas, ilegibles, a.desde))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
