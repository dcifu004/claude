#!/usr/bin/env python3
"""Acciones para timers de usuario y del bot (sin root) y del sistema (por `sudo -n nodo-servicio`).

Las del sistema pasan por acá para que la línea de avisos.jsonl la escriba dcifu004, no root."""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NOMBRE = re.compile(r"[A-Za-z0-9@_.-]{1,64}$")
PROGRAMADOS = os.environ.get("PROGRAMADOS_ACCION", str(Path(__file__).with_name("programados.py")))
REGISTRO = Path(os.environ.get("PROGRAMADO_REGISTRO", "/opt/nodo/datos/avisos.jsonl"))
# El propio temporizadores.py, que es lo que nodo-desplegar instala (entrada botv3-temporizadores-py):
# un script aparte no tenía entrada y los botones llamaban a una ruta que no existía (revisión 35r2).
TEMPORIZADOR_ACCION = os.environ.get("TEMPORIZADOR_ACCION", "/opt/botv3/temporizadores.py")


def salir(texto):
    salida = json.dumps({"ok": False, "error": texto}, ensure_ascii=False)
    print(salida)
    print(salida, file=sys.stderr)
    raise SystemExit(1)


def avisar(texto, nivel):
    fila = {"momento": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "origen": "programados", "nivel": nivel, "texto": texto,
            "linea": None, "id": None, "estado": None}
    try:
        if os.path.ismount("/opt/nodo/datos"):
            fd = os.open(REGISTRO, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o664)
            os.fchmod(fd, 0o664)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except OSError:
        pass


def correr(orden):
    try:
        r = subprocess.run(orden + (["--no-block"] if orden[-1].endswith(".service") else []),
                           capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return None, {"orden": orden[1:], "rc": None, "detalle": "la orden agotó el tiempo de espera"}
    return r, {"orden": orden[1:], "rc": r.returncode, "detalle": (r.stderr or r.stdout).strip()[-600:]}


def reportado(fuente, ident):
    try:
        r = subprocess.run([sys.executable, PROGRAMADOS], capture_output=True, text=True, timeout=30)
        datos = json.loads(r.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if fuente in ("usuario", "sistema"):
        origen = "timer de usuario" if fuente == "usuario" else "timer del sistema"
        return next((t for t in datos.get("tareas", [])
                     if t.get("fuente") == origen and t.get("nombre") == ident), None)
    return next((t for t in datos.get("tareas", [])
                 if t.get("fuente") == "bot" and t.get("identificador") == ident), None)


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in {"usuario", "bot", "sistema"}:
        salir("uso: programado-accion.py <usuario|bot|sistema> <pausar|reanudar|correr> <nombre|id>")
    fuente, accion, ident = sys.argv[1:]
    if accion not in {"pausar", "reanudar", "correr"} or not NOMBRE.fullmatch(ident) or ".." in ident:
        salir("accion o nombre invalido")
    tarea = reportado(fuente, ident)
    if not tarea:
        salir("tarea no reportada por programados.py")
    if fuente == "bot":
        if not ident.isalnum() or len(ident) > 32:
            salir("id de temporizador invalido")
        if not os.path.isfile(TEMPORIZADOR_ACCION):
            salir(f"no está instalado {TEMPORIZADOR_ACCION}: falta desplegar el bot")
        try:
            r = subprocess.run(["python3", TEMPORIZADOR_ACCION, accion, ident],
                               capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            salir("la acción del temporizador agotó el tiempo de espera")
        try:
            resultado = json.loads(r.stdout)
        except ValueError:
            # Un temporizadores.py anterior al encargo 35 no trae las acciones: corre y no contesta nada.
            resultado = {"ok": False, "error": f"{TEMPORIZADOR_ACCION} no contestó: el bot instalado es anterior a "
                                               "esta página; falta desplegar botv3/temporizadores.py"}
        if r.returncode or not resultado.get("ok"):
            salir(resultado.get("error", "falló el temporizador"))
        avisar(f"✅ Temporizador del bot {ident}: {accion}.", "ok")
        print(json.dumps(resultado, ensure_ascii=False))
        return
    if fuente == "sistema":
        try:
            r = subprocess.run(["sudo", "-n", "/usr/local/bin/nodo-servicio", f"timer-{accion}", ident],
                               capture_output=True, text=True, timeout=120)
            resultado = json.loads(r.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            resultado = {"ok": False, "error": "nodo-servicio no respondió (¿falta autorizar en sudoers?)"}
        if not resultado.get("ok"):
            avisar(f"❌ Timer del sistema {ident}: {accion}: {resultado.get('error')}", "error")
            salir(resultado.get("error") or "falló nodo-servicio")
        avisar(f"✅ Timer del sistema {ident}: {accion}.", "ok")
        print(json.dumps(resultado, ensure_ascii=False))
        return
    unidad = f"{ident}.timer"
    servicio = tarea.get("servicio") or f"{ident}.service"
    ordenes = {"pausar": [["systemctl", "--user", "stop", unidad], ["systemctl", "--user", "disable", unidad]],
               "reanudar": [["systemctl", "--user", "enable", "--now", unidad]],
               "correr": [["systemctl", "--user", "start", servicio]]}[accion]
    resultados = []
    for orden in ordenes:
        r, detalle = correr(orden)
        resultados.append(detalle)
        if r is None or r.returncode:
            codigo = r.returncode if r is not None else "timeout"
            error = f"la orden falló (código {codigo})"
            avisar(f"❌ Timer de usuario {ident}: {accion}: {error}", "error")
            print(json.dumps({"ok": False, "error": error, "resultados": resultados}, ensure_ascii=False))
            return
    avisar(f"✅ Timer de usuario {ident}: {accion}.", "ok")
    print(json.dumps({"ok": True, "resultados": resultados}, ensure_ascii=False))


if __name__ == "__main__":
    main()
