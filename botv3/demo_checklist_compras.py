#!/usr/bin/env python3
"""Demo del checklist de compras con teclado inline (F2 del plan de compras v2).

Es una DEMO, no parte del bot: lee la lista real de la casa SIN escribirla y
manda UN mensaje con un boton por item. Al tocar, el mismo mensaje se redibuja
(⬜ <-> ✅). Lo marcado vive solo en este proceso: no toca compras.json.

    sudo systemctl stop botv3@jaime && sudo python3 demo_checklist_compras.py --atender 180; sudo systemctl start botv3@jaime

Por que hay que parar el servicio: dos procesos pidiendo getUpdates con el mismo
token dan 409 Conflict. Mientras la demo atiende, lo que se le escriba al bot
se consume aca y se pierde (la demo solo mira callback_query).

Se corre con sudo porque secretos/ es de root. Si la lista real esta vacia o no
se puede leer, usa items de ejemplo.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV_POR_DEFECTO = Path("/opt/nodo/datos/secretos/botv3-jaime.env")
LISTA = Path("/opt/nodo/datos/casa/compras.json")
API = "https://api.telegram.org/bot{token}/{metodo}"
EJEMPLO = [("Leche descremada 1L", "jaime"), ("Pan", "pilar"), ("Tomates", "jaime"),
           ("Aceite de oliva", "pilar"), ("Huevos", "jaime"), ("Café", "pilar")]
# 60 items de la lista + 2 de control quedan bajo el techo de 100 botones; la
# demo se corta antes para que el mensaje se lea en el telefono.
MAX_DEMO = 20

items: list[tuple[str, str]] = []
marcados: set[int] = set()


def leer_env(ruta: Path) -> dict[str, str]:
    try:
        crudo = ruta.read_text(encoding="utf-8")
    except FileNotFoundError:
        sys.exit(f"no existe {ruta}")
    except PermissionError:
        sys.exit(f"sin permiso para leer {ruta} (corre con sudo)")
    env = {}
    for linea in crudo.splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, _, v = linea.partition("=")
            env[k.strip()] = v.strip().strip('"')
    for clave in ("BOTV3_TOKEN", "BOTV3_CHAT_ID"):
        if not env.get(clave):
            sys.exit(f"falta {clave} en {ruta}")
    return env


def cargar_items() -> str:
    try:
        datos = json.loads(LISTA.read_text(encoding="utf-8"))
        reales = [(str(i["texto"]), str(i.get("quien", "?"))) for i in datos["items"]]
    except (OSError, ValueError, KeyError, TypeError):
        reales = []
    if reales:
        items.extend(reales[:MAX_DEMO])
        return "lista real"
    items.extend(EJEMPLO)
    return "items de ejemplo"


def api(token: str, metodo: str, payload: dict) -> dict:
    req = urllib.request.Request(API.format(token=token, metodo=metodo),
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=65) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")
        if e.code == 409:
            sys.exit("409 Conflict: botv3@jaime sigue haciendo getUpdates. Paralo antes.")
        if e.code == 400 and "message is not modified" in cuerpo:
            return {"ok": False, "ignorado": True}
        sys.exit(f"HTTP {e.code} en {metodo}: {cuerpo}")


def render(cerrado: bool = False) -> tuple[str, dict]:
    lineas = [f"🛒 Lista de compras — {len(marcados)} de {len(items)} en el carro", ""]
    lineas += [f"{'✅' if n in marcados else '⬜'} {t}  · {q}"
               for n, (t, q) in enumerate(items)]
    if cerrado:
        lineas += ["", "🏁 Compra terminada (demo: no se borró nada)"]
        return "\n".join(lineas), {"inline_keyboard": []}
    # Dos columnas: con 15 items en una sola el teclado tapa la pantalla. El
    # callback lleva el indice, nunca el texto (techo de 64 bytes).
    botones = [{"text": f"{'✅' if n in marcados else '⬜'} {t[:28]}",
                "callback_data": f"chk:{n}"} for n, (t, _) in enumerate(items)]
    filas = [botones[n:n + 2] for n in range(0, len(botones), 2)]
    filas.append([{"text": "🔄 Actualizar", "callback_data": "chk:ref"},
                  {"text": "🏁 Terminar compra", "callback_data": "chk:fin"}])
    return "\n".join(lineas), {"inline_keyboard": filas}


def atender(token: str, chat: str, mensaje_id: int, segundos: int) -> None:
    hasta, offset = time.time() + segundos, None
    print(f"atendiendo toques por {segundos}s (ctrl-c para cortar)")
    while time.time() < hasta:
        payload = {"timeout": 25, "allowed_updates": ["callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        for upd in api(token, "getUpdates", payload).get("result", []):
            offset = upd["update_id"] + 1
            cq = upd.get("callback_query")
            if not cq or not str(cq.get("data", "")).startswith("chk:"):
                continue
            dato = cq["data"][4:]
            cerrado = dato == "fin"
            if dato.isdigit() and int(dato) < len(items):
                marcados.symmetric_difference_update({int(dato)})
            # answerCallbackQuery SIEMPRE, o el boton queda girando.
            api(token, "answerCallbackQuery", {"callback_query_id": cq["id"],
                                               "text": "Compra terminada" if cerrado else ""})
            texto, teclado = render(cerrado)
            api(token, "editMessageText", {"chat_id": chat, "message_id": mensaje_id,
                                           "text": texto, "reply_markup": teclado})
            if cerrado:
                print("terminado por el usuario")
                return
    print("se acabó el tiempo; el mensaje queda dibujado pero sin atender")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=ENV_POR_DEFECTO)
    p.add_argument("--atender", type=int, default=0, metavar="SEGUNDOS")
    args = p.parse_args()
    env = leer_env(args.env)
    origen = cargar_items()
    texto, teclado = render()
    r = api(env["BOTV3_TOKEN"], "sendMessage",
            {"chat_id": env["BOTV3_CHAT_ID"], "text": texto, "reply_markup": teclado})
    mensaje_id = r["result"]["message_id"]
    print(f"checklist enviado ({origen}, {len(items)} items, message_id={mensaje_id})")
    if args.atender:
        atender(env["BOTV3_TOKEN"], env["BOTV3_CHAT_ID"], mensaje_id, args.atender)


if __name__ == "__main__":
    main()
