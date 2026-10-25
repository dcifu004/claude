#!/usr/bin/env python3
"""panel-cache — deja la carga comprometida de las colas donde la lee `bots-info --margen` (encargo 90).

    panel-cache [--cola-run RUTA] [--salida RUTA]

Corre `cola-run.py --panel`, el MISMO comando con que 💳 Cuentas dibuja la carga sobre las barras,
y guarda sólo sus `reglas` (y el `momento` del cálculo) en /opt/nodo/datos/encargos-panel.json,
de forma atómica y 0644. Así el bot no ejecuta código del vault (lo escriben los agentes) y root
tampoco: este script corre como dcifu004, el mismo usuario con que la página corre --panel.

Si --panel falla o trae otra forma, no toca el archivo: el caché envejece y, pasados 15 min,
`bots-info --margen` lo da por vencido y la imagen sale sin carga (como la página cuando --panel
falla). Sale con 1 en ese caso, para que la unidad lo deje en el journal.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

COLA_RUN = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/cola-run.py"
SALIDA = "/opt/nodo/datos/encargos-panel.json"
TZ = ZoneInfo("America/Santiago")
TIMEOUT_S = 120


def leer_panel(cola_run=COLA_RUN, correr=subprocess.run):
    """El JSON de `cola-run.py --panel`. ValueError si falla o no trae `reglas`."""
    p = correr(["python3", cola_run, "--panel"], capture_output=True, text=True, timeout=TIMEOUT_S)
    if p.returncode != 0:
        raise ValueError(f"--panel salió con {p.returncode}: {(p.stderr or '').strip()[-300:]}")
    d = json.loads(p.stdout)
    if not isinstance(d, dict) or not isinstance(d.get("reglas"), list):
        raise ValueError("--panel no trae `reglas`")
    return d


def armar(panel, ahora=None):
    """Lo único que se guarda: las reglas (cuenta, ventanas, celdas por cola) y cuándo."""
    ahora = ahora or datetime.now(TZ)
    return {"escrito": ahora.isoformat(timespec="seconds"), "momento": panel.get("momento"),
            "reglas": [r for r in panel["reglas"] if isinstance(r, dict)]}


def escribir(ruta, datos):
    """Atómico: temporal nuevo en la misma carpeta y rename. El bot nunca lee a medias."""
    carpeta = os.path.dirname(os.path.abspath(ruta))
    fd, tmp = tempfile.mkstemp(prefix=".encargos-panel.", suffix=".tmp", dir=carpeta)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False)
            fh.flush()
            os.fchmod(fh.fileno(), 0o644)
            os.fsync(fh.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cola-run", default=COLA_RUN)
    ap.add_argument("--salida", default=SALIDA)
    a = ap.parse_args(argv)
    try:
        escribir(a.salida, armar(leer_panel(a.cola_run)))
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        print(f"panel-cache: no actualicé {a.salida}: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
