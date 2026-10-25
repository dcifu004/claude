#!/usr/bin/env python3
"""Genera las dos muestras del encargo 90 con los fixtures de pi/fixtures/cuentas/ (sin red, sin Telegram).

    BOTV3_CLIMA_FUENTES=<carpeta con Lato-Regular.ttf y Lato-Bold.ttf> python3 -B encargos-nube/90-muestras/genera.py
"""
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "botv3"))
import uso_imagen  # noqa: E402


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def panel_de(caso):
    bi = cargar("bots_info_muestra", RAIZ / "pi/bots-info.py")
    bi.recetas = cargar("recetas_muestra", RAIZ / "botv3/recetas.py")
    bi.REGISTRO = str(RAIZ / "pi/fixtures/avisos/cuentas.toml")
    f = json.loads((RAIZ / f"pi/fixtures/cuentas/margen-{caso}.json").read_text(encoding="utf-8"))
    ahora = datetime.fromisoformat(f["ahora"]).astimezone(bi.TZ)
    registro, limites = bi.registro_cuentas(), bi.limites_de(f["uso"])
    margen = bi.margen_de(registro, limites, ahora, bi.resumen_cuentas(registro, [], ahora, dict(limites)), bi.recetas)
    return bi.panel_margen(margen, f["reglas"], ahora)


if __name__ == "__main__":
    for caso, nombre in (("normal", "uso-normal.png"), ("pasado", "uso-pasado-del-tope.png")):
        png = uso_imagen.tarjeta_png(panel_de(caso))
        (Path(__file__).parent / nombre).write_bytes(png)
        print(nombre, len(png), "bytes")
