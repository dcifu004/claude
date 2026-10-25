#!/usr/bin/env python3
"""Prueba negativa para ejecutar sólo dentro del sandbox systemd de Bot V3."""

from pathlib import Path
import sys


failures = []


def expect_denied(path: Path) -> None:
    try:
        path.write_text("probe", encoding="utf-8")
    except OSError:
        return
    else:
        path.unlink(missing_ok=True)
        failures.append(f"escritura permitida: {path}")


expect_denied(Path("/opt/nodo/datos/srv/vault_personal/.botv3-write-probe"))
expect_denied(Path("/opt/nodo/datos/srv/vault_trabajo/.botv3-write-probe"))

try:
    list(Path("/opt/nodo/datos/secretos").iterdir())
except OSError:
    pass
else:
    failures.append("directorio de secretos visible")

try:
    Path("/run/docker.sock").open("rb")
except OSError:
    pass
else:
    failures.append("socket Docker accesible")

state_probe = Path("/opt/nodo/datos/botv3/.sandbox-state-probe")
try:
    state_probe.write_text("ok", encoding="utf-8")
    state_probe.unlink()
except OSError as exc:
    failures.append(f"estado operativo no escribible: {exc}")

if failures:
    print("FALLO: " + "; ".join(failures))
    raise SystemExit(1)
print("OK: vaults bloqueados; secretos y Docker inaccesibles; estado escribible")
