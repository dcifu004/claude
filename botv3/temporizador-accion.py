#!/usr/bin/env python3
"""Acciones acotadas sobre un temporizador del bot, sin root.

Desde la revisión 35r2 la lógica vive en `temporizadores.accion_cockpit`, y
Cockpit (`programado-accion.py`) llama directo a `temporizadores.py`, que es el
archivo que sí tiene entrada de despliegue. Este script queda como el mismo
comando de siempre para quien lo corra desde el vault; no hace falta en la Pi.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import temporizadores


if __name__ == "__main__":
    if not hasattr(temporizadores, "main"):
        print(json.dumps({"ok": False, "error": "temporizadores.py es anterior a las acciones de Cockpit"},
                         ensure_ascii=False))
        raise SystemExit(1)
    raise SystemExit(temporizadores.main(sys.argv))
