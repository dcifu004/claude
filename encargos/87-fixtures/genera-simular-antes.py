#!/usr/bin/env python3
"""Genera simular-antes-82.txt y simular-antes-85.txt (encargo 87, C1).

    python3 -B encargos/87-fixtures/genera-simular-antes.py RUTA/cola-run.py

RUTA/cola-run.py es la copia del cola-run.py ANTERIOR al encargo 87 (la foto base de la etapa). Las
entradas quedan fijas para que la salida no dependa del día: el historial y modelos.toml congelados de
46-fixtures, sin cuentas.toml (los nombres salen como la clave), la medición de cuota constante y la
hora fija. test_cierre_barato.py corre el cola-run.py nuevo con las MISMAS entradas y compara byte a byte.
"""
import contextlib
import importlib.util
import io
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FIJAS = AQUI.parent / "46-fixtures"
MEDIDA = {"5h": 10.0, "sem": 20.0, "renueva_5h": None, "renueva_sem": None, "momento": None, "fuente": "fresco"}


def simular(cola_run: Path, manifiesto: Path) -> tuple[int, str]:
    spec = importlib.util.spec_from_file_location(f"cola_run_sim_{manifiesto.stem}", cola_run)
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        for origen in (FIJAS / "historial.jsonl", FIJAS / "modelos.toml", manifiesto):
            shutil.copy(origen, t / origen.name)
        cr.HISTORIAL, cr.MODELOS, cr.REGISTROS = t / "historial.jsonl", t / "modelos.toml", ()
        cr.medir = lambda cid: dict(MEDIDA)
        cr.ahora = lambda: datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
        argv = list(sys.argv)
        sys.argv = ["cola-run.py", str(t / manifiesto.name), "--simular"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                rc = cr.main()
        finally:
            sys.argv = argv
    return rc, out.getvalue()


if __name__ == "__main__":
    cola_run = Path(sys.argv[1])
    for n in ("82", "85"):
        rc, salida = simular(cola_run, AQUI / f"cola-{n}.toml")
        assert rc == 0, (n, rc)
        (AQUI / f"simular-antes-{n}.txt").write_text(salida, encoding="utf-8")
        print(f"simular-antes-{n}.txt: {len(salida.encode())} bytes")
