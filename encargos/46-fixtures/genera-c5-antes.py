#!/usr/bin/env python3
"""De dónde sale `c5-antes.json` (encargo 46a, criterio C5): corre `muestras_c5()` de test_matriz_cuota.py con el
cola-run.py ANTERIOR al encargo, sacado de la foto «cola46 · 46a · autor (antes)» del historial git, y compara
el resultado con el archivo. Con `--escribir` lo reescribe. No toca el vault: trabaja en un temporal.

    python3 encargos/46-fixtures/genera-c5-antes.py
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

FOTO = "cf34dce"        # cola46 · 46a · autor (antes)
GIT = "/opt/nodo/datos/git/11-Pi5.git"
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import test_matriz_cuota as t  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="c5-antes-"))
try:
    viejo = tmp / "cola-run-antes.py"
    viejo.write_bytes(subprocess.run(["git", f"--git-dir={GIT}", "show", f"{FOTO}:encargos/cola-run.py"],
                                     capture_output=True, check=True).stdout)
    print("sha256 del cola-run.py anterior:", hashlib.sha256(viejo.read_bytes()).hexdigest())
    cr = t.cargar(viejo)
    assert not hasattr(cr, "matriz_cuota") and not hasattr(cr, "fases_restantes"), "esa foto ya trae el encargo 46a"
    t.preparar(cr, tmp, lambda: t.T)

    class Reloj(datetime):      # el _normalizar anterior no recibe la hora de corte: se le fija el reloj
        @classmethod
        def now(cls, tz=None):
            return t.T.astimezone(tz)

    def cerrado(*a, **k):
        raise AssertionError("sin procesos")
    cr.datetime, cr.USO = Reloj, t.FIX / "uso-limites.json"
    cr.subprocess = type("SinProcesos", (), {"run": staticmethod(cerrado)})
    muestras = t.muestras_c5(cr, tmp, cr.uso)
    destino = t.FIX / "c5-antes.json"
    if "--escribir" in sys.argv:
        destino.write_text(json.dumps(muestras, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("escrito", destino.name)
    else:
        igual = json.loads(destino.read_text(encoding="utf-8")) == muestras
        print(f"{destino.name}: {'igual a lo que da el cola-run.py anterior' if igual else 'DISTINTO'}")
        sys.exit(0 if igual else 1)
finally:
    shutil.rmtree(tmp, True)
