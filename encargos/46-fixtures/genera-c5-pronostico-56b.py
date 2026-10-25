#!/usr/bin/env python3
"""Regenera la captura C5 con el pronóstico conservador final del encargo 56b.

Trabaja sobre un temporal y la forma real de las fixtures; sólo escribe
`c5-pronostico-56b.json` si se invoca con `--escribir`.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import test_matriz_cuota as t  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="c5-pronostico-56b-"))
try:
    cr = t.cargar()
    t.preparar(cr, tmp, lambda: t.T)
    cr.USO = t.FIX / "uso-limites.json"
    muestras = t.muestras_c5(cr, tmp, lambda cid: cr.uso(cid, cr.USO, t.T))
    destino = t.FIX / "c5-pronostico-56b.json"
    if "--escribir" in sys.argv:
        destino.write_text(json.dumps(muestras, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("escrito", destino.name)
    else:
        igual = destino.exists() and json.loads(destino.read_text(encoding="utf-8")) == muestras
        print(f"{destino.name}: {'igual a la forma real final' if igual else 'DISTINTO'}")
        sys.exit(0 if igual else 1)
finally:
    shutil.rmtree(tmp, True)
