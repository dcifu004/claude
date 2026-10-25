#!/usr/bin/env python3
"""Regenera la captura de matriz C2 con el p75 final del encargo 56b."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import test_matriz_cuota as mc  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="panel-46a-56b-"))
try:
    cr = mc.cargar()
    mc.preparar(cr, tmp, lambda: mc.T)
    for nombre in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola46.json"):
        vivo = json.loads((mc.FIX / nombre).read_text(encoding="utf-8"))
        (tmp / "vivo" / f"{vivo['nombre']}.json").write_text(json.dumps(vivo, ensure_ascii=False), encoding="utf-8")
    cr._AP_MOD = mc.cargar(AQUI.parents[1] / "pi" / "aplicar-propuesta.py")
    cr._AP_MOD.CODEX_MODELOS = str(AQUI.parents[1] / "pi" / "fixtures" / "encargos" / "models_cache.json")
    cr.SIMULANDO = True
    timer = [(mc.PARTE, mc.EXEC_COLA36.replace("cola36", "cola43r").replace("cola-36.toml", "cola-43.toml"))]
    panel = cr.panel(vivos_dir=tmp / "vivo", uso_de=lambda cid: cr.uso(cid, mc.FIX / "uso-limites.json", mc.T),
                     momento=mc.T, viva=lambda _: False, manifiestos_dir=mc.MANIFIESTOS, timers=timer)
    destino = AQUI.parents[1] / "pi" / "fixtures" / "encargos" / "panel-46a-56b.json"
    if "--escribir" in sys.argv:
        destino.write_text(json.dumps(panel, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("escrito", destino.name)
    else:
        igual = destino.exists() and json.loads(destino.read_text(encoding="utf-8")) == panel
        print(f"{destino.name}: {'igual a la forma real final' if igual else 'DISTINTO'}")
        sys.exit(0 if igual else 1)
finally:
    shutil.rmtree(tmp, True)
