#!/usr/bin/env python3
"""Manda al chat de un perfil los tres modos de checklist de Telegram.

Es una DEMO, no parte del bot: no toca botv3.py ni el router. Sirve para ver en
el telefono como se comporta cada mecanica antes de decidir cual se implementa.

    sudo python3 demo_checklist.py                 # manda los tres ejemplos
    sudo python3 demo_checklist.py --atender 180   # ademas atiende los toques

Sin --atender los botones del ejemplo 1 se dibujan pero nadie contesta: al
tocarlos quedan girando y despues dan "query is too old". El polling de la demo
y el de botv3.service son EXCLUYENTES (Telegram da 409 Conflict al segundo que
pide getUpdates), asi que para --atender hay que parar el servicio:

    sudo systemctl stop botv3 && sudo python3 demo_checklist.py --atender 180
    sudo systemctl start botv3

El env por defecto es el del perfil jaime (@Dcs_v3bot); con --env se apunta a
botv3-pilar.env. Se lee con sudo porque secretos/ es de root.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV_POR_DEFECTO = Path("/opt/nodo/datos/secretos/botv3.env")
API = "https://api.telegram.org/bot{token}/{metodo}"

# Los items del checklist de ejemplo 1. El estado vive aca, en el proceso; en
# una implementacion de verdad va a SQLite en BOTV3_STATE_DIR, que es lo unico
# escribible bajo ProtectSystem=strict.
ITEMS = ["Revisar humedad maceta 1", "Rellenar estanque", "Verificar bomba"]
marcados: set[int] = set()


def leer_env(ruta: Path) -> dict[str, str]:
    if not ruta.exists():
        sys.exit(f"no existe {ruta}")
    try:
        crudo = ruta.read_text(encoding="utf-8")
    except PermissionError:
        sys.exit(f"sin permiso para leer {ruta} (corre con sudo)")
    env = {}
    for linea in crudo.splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, _, v = linea.partition("=")
            env[k.strip()] = v.strip()
    for clave in ("BOTV3_TOKEN", "BOTV3_CHAT_ID"):
        if not env.get(clave):
            sys.exit(f"falta {clave} en {ruta}")
    return env


def api(token: str, metodo: str, payload: dict) -> dict:
    datos = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API.format(token=token, metodo=metodo),
        data=datos,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=65) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")
        if e.code == 409:
            sys.exit("409 Conflict: botv3.service ya esta haciendo getUpdates. "
                     "Paralo antes de usar --atender.")
        # 400 "message is not modified" llega cuando dos toques casi simultaneos
        # redibujan el mismo estado. No es un error real: se ignora y se sigue.
        if e.code == 400 and "message is not modified" in cuerpo:
            return {"ok": False, "ignorado": True}
        sys.exit(f"HTTP {e.code} en {metodo}: {cuerpo}")


def render() -> tuple[str, dict]:
    """Texto + teclado del checklist, derivados del estado actual."""
    lineas = ["*Checklist riego* — demo", ""]
    lineas += [f"{'✅' if i in marcados else '⬜'} {t}" for i, t in enumerate(ITEMS)]
    lineas += ["", f"_{len(marcados)} de {len(ITEMS)} listos_"]
    # callback_data tiene un techo de 64 bytes: va el indice, nunca el texto.
    botones = [[{"text": f"{'✅' if i in marcados else '⬜'} {t}",
                 "callback_data": f"chk:{i}"}] for i, t in enumerate(ITEMS)]
    botones.append([{"text": "Cerrar checklist", "callback_data": "chk:fin"}])
    return "\n".join(lineas), {"inline_keyboard": botones}


def ejemplo_1(token: str, chat: str) -> int:
    texto, teclado = render()
    r = api(token, "sendMessage", {
        "chat_id": chat, "text": texto,
        "parse_mode": "Markdown", "reply_markup": teclado,
    })
    return r["result"]["message_id"]


def ejemplo_2(token: str, chat: str) -> None:
    # Telegram lleva la cuenta solo. A cambio no se puede editar despues ni
    # ordenar los items, y el techo son 10 opciones.
    api(token, "sendPoll", {
        "chat_id": chat,
        "question": "Checklist riego (modo encuesta)",
        "options": json.dumps(ITEMS),
        "is_anonymous": False,
        "allows_multiple_answers": True,
    })


def ejemplo_3(token: str, chat: str) -> None:
    # ForceReply abre el teclado con la cita puesta. Es lo unico que sirve si
    # los items son texto libre, pero obliga a un mensaje por item.
    api(token, "sendMessage", {
        "chat_id": chat,
        "text": "Checklist riego (modo respuesta)\n\n"
                "1/3 — Revisar humedad maceta 1.\n"
                "Responde *listo*, *no* o una nota.",
        "parse_mode": "Markdown",
        "reply_markup": {"force_reply": True,
                         "input_field_placeholder": "listo / no / nota"},
    })


def atender(token: str, chat: str, mensaje_id: int, segundos: int) -> None:
    hasta, offset = time.time() + segundos, None
    print(f"atendiendo toques por {segundos}s (ctrl-c para cortar)")
    while time.time() < hasta:
        payload = {"timeout": 25, "allowed_updates": ["callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        r = api(token, "getUpdates", payload)
        for upd in r.get("result", []):
            offset = upd["update_id"] + 1
            cq = upd.get("callback_query")
            if not cq:
                continue
            dato = cq.get("data", "")
            # answerCallbackQuery SIEMPRE, aunque sea vacio, o el boton se
            # queda girando en el cliente.
            if dato == "chk:fin":
                api(token, "answerCallbackQuery",
                    {"callback_query_id": cq["id"], "text": "Checklist cerrado"})
                api(token, "editMessageReplyMarkup",
                    {"chat_id": chat, "message_id": mensaje_id,
                     "reply_markup": {"inline_keyboard": []}})
                print("cerrado por el usuario")
                return
            if dato.startswith("chk:"):
                i = int(dato.split(":")[1])
                marcados.symmetric_difference_update({i})
                api(token, "answerCallbackQuery", {"callback_query_id": cq["id"]})
                texto, teclado = render()
                # Editar el MISMO mensaje: no notifica y no ensucia el chat.
                api(token, "editMessageText",
                    {"chat_id": chat, "message_id": mensaje_id, "text": texto,
                     "parse_mode": "Markdown", "reply_markup": teclado})
                print(f"  {ITEMS[i]} -> {'marcado' if i in marcados else 'desmarcado'}")
    print("se acabo el tiempo; el checklist queda dibujado pero sin atender")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=ENV_POR_DEFECTO)
    p.add_argument("--atender", type=int, default=0, metavar="SEGUNDOS")
    args = p.parse_args()

    env = leer_env(args.env)
    token, chat = env["BOTV3_TOKEN"], env["BOTV3_CHAT_ID"]

    mensaje_id = ejemplo_1(token, chat)
    print(f"1/3 teclado inline enviado (message_id={mensaje_id})")
    ejemplo_2(token, chat)
    print("2/3 encuesta multiple enviada")
    ejemplo_3(token, chat)
    print("3/3 ForceReply enviado")

    if args.atender:
        atender(token, chat, mensaje_id, args.atender)
    else:
        print("\nsin --atender los botones no responden: es solo el dibujo.")


if __name__ == "__main__":
    main()
