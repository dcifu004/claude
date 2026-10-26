#!/usr/bin/env python3
"""Sincroniza el menú de Telegram sin imprimir ni modificar el token.

Desde el 19-10-2026 el bot también importa `comandos()` y sincroniza su propio menú al
arrancar: `nodo-desplegar` sólo admite `restart:` y `daemon-reload` como acciones
posteriores, así que no puede correr este script, y un comando instalado quedaba
fuera del menú hasta que alguien se acordara de correrlo a mano. Correrlo a mano
sigue sirviendo, con el env del perfil cargado.
"""

import os
from pathlib import Path
import tomllib


def rutas_del_perfil() -> list[str]:
    perfil = os.environ.get("BOTV3_PERFIL", "jaime")
    carpeta = Path(os.environ.get("BOTV3_PERFILES_DIR", Path(__file__).parent / "perfiles"))
    with open(carpeta / f"{perfil}.toml", "rb") as f:
        return list(tomllib.load(f).get("rutas", []))


def spotify_del_perfil() -> bool:
    perfil = os.environ.get("BOTV3_PERFIL", "jaime")
    carpeta = Path(os.environ.get("BOTV3_PERFILES_DIR", Path(__file__).parent / "perfiles"))
    with open(carpeta / f"{perfil}.toml", "rb") as f:
        return isinstance(tomllib.load(f).get("spotify"), dict)


def comandos(rutas, perfil: str | None = None, spotify_activo: bool = False) -> list[dict[str, str]]:
    """El menú de un perfil según sus rutas. Única lista: la usan el bot y este script."""
    rutas = set(rutas)
    perfil = os.environ.get("BOTV3_PERFIL", "jaime") if perfil is None else perfil
    # Corto a propósito (decisión de Diego, 19-10, nota 34): /estado, /uso y /acciones
    # siguen funcionando escritos y se llegan desde /menu, que lleva a todo con botones.
    return [
        {"command": "menu", "description": "Todo con botones"},
        # Va arriba porque es el único que se usa a diario y desde el super, donde
        # abrir el menú con una mano es todo lo que se puede hacer.
        {"command": "compras", "description": "Lista de compras de la casa"},
        # /gastos anota en la misma planilla que la boleta: sin esa ruta no existe.
        *([{"command": "gastos", "description": "Gastos de la casa: anotar y ver"}]
          if "boleta" in rutas else []),
        # Solo en los perfiles con la ruta google: en el menu de Pilar seria un boton
        # que contesta "no corresponde a este bot".
        *([{"command": "google", "description": "Agenda y correo (crear pide confirmar)"}]
          if "google" in rutas else []),
        {"command": "temporizadores", "description": "Temporizadores y alarmas activos"},
        *([{"command": "spotify", "description": "Vincular y ver Spotify de este perfil"}]
          if spotify_activo else []),
        # 101b: los dos perfiles; el permiso es el del socket de bt-control (grupo casa).
        {"command": "bt", "description": "Bluetooth de la Pi: ver, emparejar, desconectar"},
        {"command": "buscar", "description": "Buscar en internet (sin IA)"},
        # 96: qué cuenta contesta la ruta técnica; sólo donde existe esa ruta.
        *([{"command": "cuenta_tecnica", "description": "Qué cuenta contesta la ruta técnica"}]
          if "codex" in rutas else []),
        # Remote Control abre una sesión de la cuenta de Diego: Pilar no debe verla
        # ni aunque sus rutas de agente sean parecidas.
        *([{"command": "remoto", "description": "Abrir o cerrar Remote Control (8 h)"}]
          if perfil == "jaime" else []),
        {"command": "ayuda", "description": "Mostrar instrucciones"},
    ]


if __name__ == "__main__":
    import requests

    token = os.environ["BOTV3_TOKEN"]
    response = requests.post(
        f"https://api.telegram.org/bot{token}/setMyCommands",
        json={"commands": comandos(rutas_del_perfil(), spotify_activo=spotify_del_perfil())}, timeout=20,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise SystemExit("Telegram rechazó el menú")
    # El nombre sale del perfil y no está escrito acá: este script se corre una vez
    # por bot, cargando el env de cada uno, y decir siempre "Dcs_v3bot" hacía creer
    # que se había actualizado el equivocado.
    print(f"Menú del perfil {os.environ.get('BOTV3_PERFIL', '?')} actualizado en Telegram")
