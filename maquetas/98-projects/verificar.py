#!/usr/bin/env python3
"""Verificación de C2 y C3 de la maqueta 98, recalculada en Python sin usar modelo.js.

- C2: throughput semanal, cycle time y fechas de dos encargos, leídos directo de historial.jsonl.
- C3: los 124 encargos del índice caen en algún proyecto o en Sueltos.

Después corre modelo.js con node (el mismo que usa la página) y compara las cifras.

    python3 maquetas/98-projects/verificar.py
"""
import collections
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

AQUI = pathlib.Path(__file__).resolve().parent
DATOS = AQUI.parent.parent / "encargos-nube" / "98-datos"
CHILE = dt.timezone(dt.timedelta(hours=-3))
A_MANO = ("19", "84a")


def cargar():
    fases = [json.loads(l) for l in open(DATOS / "historial.jsonl", encoding="utf-8") if l.strip()]
    indice = json.load(open(DATOS / "encargos-index.json", encoding="utf-8"))
    borrador = json.load(open(DATOS / "proyectos-borrador.json", encoding="utf-8"))
    return fases, indice, borrador


def fin(f):
    return dt.datetime.fromisoformat(f["inicio"]) + dt.timedelta(minutes=f["min"] or 0)


def lunes(t):
    d = t.astimezone(CHILE).date()
    return d - dt.timedelta(days=d.weekday())


def cerrados(fases, abiertos):
    """Encargo → (primera fase, fin de la DESPLEGABLE) si su última revisión fue DESPLEGABLE y no está abierto."""
    por = collections.defaultdict(list)
    for f in fases:
        por[f["encargo"]].append(f)
    out = {}
    for e, fs in por.items():
        fs.sort(key=lambda f: f["inicio"])
        revs = [f for f in fs if f["veredicto"]]
        if e not in abiertos and revs and revs[-1]["veredicto"] == "DESPLEGABLE":
            out[e] = (dt.datetime.fromisoformat(fs[0]["inicio"]), fin(revs[-1]))
    return out, por


def main():
    fases, indice, borrador = cargar()
    proyectos = borrador["proyectos"]
    abiertos = {k for p in proyectos for k in p.get("abiertos", {})}
    hechos, por = cerrados(fases, abiertos)

    print("== C2: dos encargos a mano ==")
    for e in A_MANO:
        for f in por[e]:
            print(f"  {e} {f['fase']:<5} inicio {f['inicio']}  {f['min']:>5} min  {f['veredicto'] or '—'}")
        ini, fn = hechos[e]
        print(f"  → primera fase {ini.astimezone(CHILE):%d-%m %H:%M}, DESPLEGABLE termina {fn.astimezone(CHILE):%d-%m %H:%M}, "
              f"cycle time {(fn - ini).total_seconds() / 60:.1f} min, cuenta en la semana del {lunes(fn):%d-%m}")

    semanas = collections.Counter(lunes(fn) for _, fn in hechos.values())
    print("== C2: throughput por semana (lunes, hora de Chile) ==")
    for s in sorted(semanas):
        print(f"  {s:%d-%m}: {semanas[s]}")
    ciclos = sorted((fn - ini).total_seconds() / 86400 for ini, fn in hechos.values())
    mediana = ciclos[max(0, -(-len(ciclos) // 2) - 1)]
    print(f"  {len(hechos)} encargos terminados · media {sum(semanas.values()) / len(semanas):.2f}/sem · "
          f"cycle time mediana {mediana * 1440:.1f} min")

    print("== C3: cobertura del índice ==")
    def proyecto_de(i):
        for p in proyectos:
            if i in p["encargos"] or i in p.get("abiertos", {}):
                return p["id"]
        n = re.match(r"\d+", i).group(0)
        for p in proyectos:
            if n in p["encargos"] or n in p.get("abiertos", {}):
                return p["id"]
        return "otros"
    asign = {x["id"]: proyecto_de(x["id"]) for x in indice}
    perdidos = [i for i, p in asign.items() if p is None]
    print(f"  índice {len(indice)} · con proyecto {sum(p != 'otros' for p in asign.values())} · "
          f"en Sueltos {sum(p == 'otros' for p in asign.values())} · perdidos {len(perdidos)}")

    # Contra modelo.js (lo que dibuja la página).
    js = (
        'global.window=globalThis;require("./datos/datos-98.js");require("./modelo.js");const M=MODELO98;'
        'console.log(JSON.stringify({semanas:M.semanas.map(M.fmt.ddmm),porSemana:M.global.porSemana,hechas:M.global.hechas,'
        'mediana:M.global.cycleMediana,c3:M.c3,asign:Object.fromEntries(M.tarjetas.map(t=>[t.id,t.proyecto])),'
        f'mano:{json.dumps(list(A_MANO))}.map(i=>[i,M.tarjeta[i].inicio,M.tarjeta[i].fin,M.tarjeta[i].cycle])}}))')
    m = json.loads(subprocess.run(["node", "-e", js], cwd=AQUI, capture_output=True, text=True, check=True).stdout)
    fallas = []
    py_sem = {f"{s:%d-%m}": n for s, n in semanas.items()}
    if [py_sem.get(s, 0) for s in m["semanas"]] != m["porSemana"]:
        fallas.append(f"throughput: python {py_sem} ≠ página {dict(zip(m['semanas'], m['porSemana']))}")
    if m["hechas"] != len(hechos):
        fallas.append(f"terminados: python {len(hechos)} ≠ página {m['hechas']}")
    if abs(m["mediana"] - mediana) > 1e-9:
        fallas.append(f"mediana: python {mediana} ≠ página {m['mediana']}")
    for i, ini, fn, cyc in m["mano"]:
        pi, pf = hechos[i]
        if abs(ini / 1000 - pi.timestamp()) > 1 or abs(fn / 1000 - pf.timestamp()) > 1:
            fallas.append(f"{i}: fechas distintas")
    distintos = [i for i in asign if m["asign"].get(i) != asign[i]]
    if distintos:
        fallas.append(f"asignación distinta: {distintos}")
    if m["c3"]["perdidos"] or m["c3"]["cubiertos"] != len(indice):
        fallas.append(f"C3 en la página: {m['c3']}")
    print("== Página (modelo.js) ==")
    print(f"  semanas {m['semanas']} · throughput {m['porSemana']} · c3 {m['c3']['cubiertos']}/{m['c3']['indice']}, "
          f"en Sueltos {m['c3']['enSueltos']}")
    if fallas:
        print("FALLAS:\n  " + "\n  ".join(fallas))
        return 1
    print("OK: Python y la página dan lo mismo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
