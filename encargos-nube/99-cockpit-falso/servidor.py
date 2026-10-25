#!/usr/bin/env python3
"""Cockpit falso del encargo 99: sirve pi/cockpit-encargos y pi/cockpit-comun en 127.0.0.1 y contesta las lecturas
(`cockpit.file`) y los comandos (`cockpit.spawn`) de la página con los archivos reales de la rama. Sólo lee; no corre
ningún comando de verdad. Uso: python3 encargos-nube/99-cockpit-falso/servidor.py [puerto]

El caso se elige con ?caso= en la URL de la página (lo reenvía cockpit.js):
  normal   proyectos.json de la rama, sin colas vivas
  vivo     además, dos colas vivas de prueba (86 en rev2 → Review, 77 en autor → In progress, 83 en rev1 → gana «abiertos»)
  ausente  sin proyectos.json
  roto     proyectos.json que no es JSON
  grande   proyectos.json de más de 1 MB
  hostil   proyectos.json con __proto__, tipos raros y títulos con HTML
"""
import http.server
import json
import pathlib
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

RAIZ = pathlib.Path(__file__).resolve().parents[2]
DIR = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos"
CUENTAS = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/botv3/cuentas.toml"
USO = "/opt/nodo/datos/uso.json"
CHILE = timezone(timedelta(hours=-3))
INDICE = json.loads((RAIZ / "encargos-nube/98-datos/encargos-index.json").read_text(encoding="utf-8"))
HISTORIAL = RAIZ / "encargos/historial.jsonl"
PRIMERA = {}
for linea in HISTORIAL.read_text(encoding="utf-8").splitlines():
    if linea.strip():
        f = json.loads(linea)
        PRIMERA.setdefault(str(f["encargo"]), f["inicio"])

VIVOS = {
    "cola86x": {"nombre": "cola86x", "estado": "corriendo", "etapas": ["86"], "etapa": "86", "fase": "rev2", "cuenta": "Claude (Cami)", "escrito": "2026-10-25T17:30:00-03:00"},
    "cola77x": {"nombre": "cola77x", "estado": "pausada", "etapas": ["77"], "etapa": "77", "fase": "autor", "cuenta": "Codex", "escrito": "2026-10-25T17:31:00-03:00"},
    "cola83x": {"nombre": "cola83x", "estado": "corriendo", "etapas": ["83"], "etapa": "83", "fase": "rev1", "cuenta": "Codex", "escrito": "2026-10-25T17:32:00-03:00"},
}


def mtime(x):
    """El índice de esta copia no trae los .md: la fecha de modificación sale de la fecha del título (12:00 de Chile) o,
    si no tiene, de la primera fase. Es una aproximación para la maqueta; en la Pi es la del archivo."""
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", x["titulo"])
    if m:
        return datetime(int(m[3]), int(m[2]), int(m[1]), 12, tzinfo=CHILE).timestamp()
    if x["id"] in PRIMERA:
        return datetime.fromisoformat(PRIMERA[x["id"]]).timestamp()
    return datetime(2026, 9, 29, 12, tzinfo=CHILE).timestamp()


def listado():
    lineas = []
    for x in INDICE:
        lineas.append(f"{mtime(x):.10f} {x['id']}-{x['slug']}.md")
        for r in x["resultados"]:
            lineas.append(f"{mtime(x):.10f} {r}.md")
    return "\n".join(dict.fromkeys(lineas)) + "\n"


def titulos():
    return "".join(f"{DIR}/{x['id']}-{x['slug']}.md:# {x['titulo']}\n" for x in INDICE)


def proyectos(caso):
    real = (RAIZ / "encargos/proyectos.json").read_text(encoding="utf-8")
    if caso == "ausente":
        return None
    if caso == "roto":
        return real[: len(real) // 2]
    if caso == "grande":
        d = json.loads(real)
        d["relleno"] = "x" * (1024 * 1024 + 10)
        return json.dumps(d)
    if caso == "hostil":
        return ('{"__proto__": {"columnas": 1}, "tope_wip": {"Review": "3", "In progress": 2}, "aging_dias": -4, '
                '"proyectos": [{"id": "voz", "nombre": "<img src=x onerror=alert(1)>", "resultado": 7, "encargos": ["16", 3, "<b>", "17"], '
                '"abiertos": {"16": "Hecho", "17": "Review", "__proto__": "Done"}, "ideas": "no es lista", "bloqueo": {"x": 1}}, '
                '{"id": "constructor", "nombre": "x", "encargos": "16"}, {"id": "voz", "nombre": "repetido"}, 5, null], '
                '"archivos_compartidos": {"__proto__": ["16"], "a.py": ["16", "17", {}]}}')
    return real


def archivo(ruta, caso):
    if ruta == f"{DIR}/proyectos.json":
        return proyectos(caso)
    mapa = {f"{DIR}/historial.jsonl": HISTORIAL, f"{DIR}/COLA-ESTADO.md": RAIZ / "pi/fixtures/encargos/COLA-ESTADO-cola23.md",
            USO: RAIZ / "pi/fixtures/avisos/uso-real.json", CUENTAS: RAIZ / "pi/fixtures/avisos/cuentas.toml"}
    if ruta in mapa:
        return mapa[ruta].read_text(encoding="utf-8")
    m = re.fullmatch(re.escape(DIR) + r"/(cola-[\w.-]+\.toml)", ruta)
    if m and (RAIZ / "encargos" / m[1]).is_file():
        return (RAIZ / "encargos" / m[1]).read_text(encoding="utf-8")
    m = re.fullmatch(re.escape(DIR) + r"/vivo/(\w+)\.json", ruta)
    if m and caso == "vivo" and m[1] in VIVOS:
        return json.dumps(VIVOS[m[1]])
    return None


def comando(argv, caso):
    a = list(argv)
    if a[:2] == ["tmux", "ls"]:
        return "cola86x\ncola83x\n" if caso == "vivo" else ""
    if a[:2] == ["find", DIR] and "cola-*.toml" in a:
        return "".join(f"{DIR}/{p.name}\n" for p in sorted((RAIZ / "encargos").glob("cola-*.toml")))
    if a[:2] == ["find", f"{DIR}/vivo"]:
        return "".join(f"{DIR}/vivo/{n}.json\n" for n in VIVOS) if caso == "vivo" else ""
    if a[:2] == ["find", DIR] and "-printf" in a:
        return listado()
    if a[:2] == ["find", DIR] and "-exec" in a:
        return titulos()
    if a == ["python3", f"{DIR}/cola-run.py", "--panel"]:
        return (RAIZ / "pi/fixtures/encargos/panel-46a-56b.json").read_text(encoding="utf-8")
    if a == ["python3", f"{DIR}/registro_avisos.py", "--panel"]:
        return json.dumps({"avisos": [], "pendientes": [], "alarmas": []})
    return None


class Manejador(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, codigo, cuerpo, tipo="application/json"):
        datos = cuerpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_POST(self):
        pedido = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        caso = pedido.get("caso") or "normal"
        if self.path == "/_falso/file":
            t = archivo(pedido["ruta"], caso)
            return self.responder(200, json.dumps({"texto": t}))          # null = no existe, como cockpit.file().read()
        if self.path == "/_falso/spawn":
            t = comando(pedido["argv"], caso)
            return self.responder(200, json.dumps({"texto": t, "error": None if t is not None else f"comando no simulado: {pedido['argv'][:2]}"}))
        self.responder(404, "{}")

    def translate_path(self, path):
        p = urllib.parse.urlparse(path).path
        if p.startswith("/encargos/"):
            return str(RAIZ / "pi/cockpit-encargos" / p[len("/encargos/"):])
        if p.startswith("/comun/"):
            return str(RAIZ / "pi/cockpit-comun" / p[len("/comun/"):])
        if p == "/base1/cockpit.js":
            return str(pathlib.Path(__file__).parent / "cockpit.js")
        return str(RAIZ / "nada")


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    http.server.ThreadingHTTPServer(("127.0.0.1", puerto), Manejador).serve_forever()
