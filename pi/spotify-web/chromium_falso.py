#!/usr/bin/env python3
"""Chromium FALSO para test_spotify_web.py (encargo 100). No se instala.

Habla el DevTools Protocol por pipe como `chromium --remote-debugging-pipe`: lee los comandos del
fd 3 y escribe las respuestas en el fd 4, en mensajes JSON terminados en \\0. Lo que devuelve la
página sale de fixtures/dom-tema-2026-10-25.json (DOM real de open.spotify.com/track/<id>,
capturado en la Prueba 0). Cada `Runtime.evaluate` se reconoce por el marcador /*sw:…*/ del JS
fijo de spotify-web.py.

    chromium_falso.py <escenario.json> [las banderas de Chromium, que se anotan y se ignoran]

Escenario: {"arranque_s": 0, "sesion": true, "botones": "fixture"|"sin_tema", "otro": null|"Casa · Jaime",
            "registro": "<ruta.jsonl>"}
"""
import html
import json
import os
import re
import sys
import time
from pathlib import Path

DOM = json.loads((Path(__file__).parent / "fixtures" / "dom-tema-2026-10-25.json").read_text(encoding="utf-8"))
ESC = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
REGISTRO = ESC.get("registro")


def anotar(x):
    if REGISTRO:
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")


def atributo(fragmento, nombre):
    m = re.search(rf'{nombre}="([^"]*)"', fragmento)
    return html.unescape(m.group(1)) if m else None


# Lo que el JS fijo leería de este DOM. El ▶ del tema es el de DOM["play_button_tema"]: está en la
# cabecera del tema (action-bar). Los demás son los de DOM["play_buttons_primeros"] y relleno de la
# biblioteca del usuario, hasta DOM["play_buttons_total"].
def botones():
    primeros = [dict(b) for b in DOM["play_buttons_primeros"]]
    tema = {"aria": atributo(DOM["play_button_tema"], "aria-label"), "dentro_de": "action-bar"}
    relleno = [{"aria": "Play <elemento de la biblioteca del usuario>", "dentro_de": "root"}]
    if ESC.get("botones") == "sin_tema":
        return primeros + relleno * (DOM["play_buttons_total"] - len(primeros))
    resto = DOM["play_buttons_total"] - len(primeros) - 1
    return primeros + [tema] + relleno * resto


AHORA = html.unescape(re.search(r'aria-label="(Now playing: [^"]*)"', DOM["now_playing_bar"]).group(1))
TEXTO_BARRA = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", DOM["now_playing_bar"]))).strip()
estado = {"suena": False, "url": "about:blank", "pagina": False}


def leer():
    tema_cargado = estado["url"].startswith("https://open.spotify.com/")
    barra = TEXTO_BARRA if estado["pagina"] else ""
    if ESC.get("otro") and estado["pagina"]:
        barra += f"\nPlaying on {ESC['otro']}"
    return {"login": not ESC.get("sesion", True) and tema_cargado, "usuario": bool(ESC.get("sesion", True)) and DOM["user_widget"] and tema_cargado,
            "ahora": AHORA if estado["pagina"] else None,
            "boton": (atributo(DOM["playpause"], "aria-label") if estado["suena"] else "Play") if estado["pagina"] else None,
            "barra": barra or None, "pos": None, "dur": None}


def evaluar(expr):
    if expr.startswith("/*sw:leer*/"):
        return leer()
    if expr.startswith("/*sw:botones*/"):
        return botones() if estado["url"].startswith("https://open.spotify.com/") and ESC.get("sesion", True) else []
    if expr.startswith("/*sw:clic*/"):
        i = int(re.search(r"\((\d+)\)\s*$", expr).group(1))
        b = botones()[i] if i < len(botones()) else None
        anotar({"clic": i, "aria": b and b["aria"]})
        if b and b["aria"] == "Play":
            estado["pagina"] = True
            estado["suena"] = True
        return bool(b)
    if expr.startswith("/*sw:playpause*/"):
        quiero = json.loads(re.search(r"\)\((\"[^\"]*\")\)\s*$", expr).group(1))
        actual = "Pause" if estado["suena"] else "Play"
        anotar({"playpause": quiero, "actual": actual})
        if estado["pagina"] and quiero == actual:
            estado["suena"] = not estado["suena"]
            return True
        return False
    raise ValueError("expresión desconocida")


def main():
    anotar({"argv": sys.argv[2:], "pid": os.getpid()})
    time.sleep(float(ESC.get("arranque_s", 0)))
    entrada, salida = os.fdopen(3, "rb", buffering=0), os.fdopen(4, "wb", buffering=0)
    resto = b""
    while True:
        trozo = entrada.read(65536)
        if not trozo:
            return
        resto += trozo
        while b"\0" in resto:
            linea, resto = resto.split(b"\0", 1)
            msg = json.loads(linea)
            metodo, params = msg.get("method"), msg.get("params", {})
            anotar({"metodo": metodo, "params": params, "sesion": msg.get("sessionId")})
            try:
                if metodo == "Target.createTarget":
                    r = {"targetId": "T1"}
                elif metodo == "Target.attachToTarget":
                    r = {"sessionId": "S1"}
                elif metodo == "Page.navigate":
                    estado["url"], estado["pagina"], estado["suena"] = params["url"], False, False
                    r = {"frameId": "F1"}
                elif metodo == "Runtime.evaluate":
                    r = {"result": {"type": "object", "value": evaluar(params["expression"])}}
                else:
                    r = {}
                respuesta = {"id": msg["id"], "result": r}
            except Exception as exc:
                respuesta = {"id": msg["id"], "error": {"code": -32000, "message": str(exc)}}
            salida.write(json.dumps(respuesta).encode() + b"\0")


if __name__ == "__main__":
    main()
