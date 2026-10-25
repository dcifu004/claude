#!/usr/bin/env python3
"""Horario local y cola segura del modo descanso."""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile
import tomllib
import urllib.request
from zoneinfo import ZoneInfo

URL_BOOSTR = "https://api.boostr.cl/holidays.json"
TZ = ZoneInfo("America/Santiago")
# Root y ProtectHome=true: configuración y caché comunes, fuera del hogar. El
# directorio StateDirectory es 0755, por lo que también lo puede leer la cola.
CONFIG = Path(os.environ.get("NODO_DESCANSO_CONFIG", "/var/lib/nodo-descanso/descanso.toml"))
# La cola privada queda junto al emisor; la copia pública de feriados no: la
# leen cola-run.py y `descanso estado` como dcifu004.
CACHE_DIR = Path(os.environ.get("NODO_DESCANSO_CACHE", "/var/lib/nodo-descanso"))
STATE_DIR = Path(os.environ.get("NODO_DESCANSO_STATE", "/var/lib/nodo"))
COLA = STATE_DIR / "descanso-cola.jsonl"
DEFECTO = {"inicio": "23:45", "fin_habil": "07:15", "fin_no_habil": "09:00",
           "feriados_locales": [], "urgentes": ["error", "cpu", "luks"]}

def configuracion() -> dict:
    try: bruto = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    # ValueError cubre TOML inválido y un archivo que no es UTF-8 (52br2, hallazgo 1).
    except (OSError, ValueError): bruto = {}
    return DEFECTO | {k: bruto[k] for k in DEFECTO if k in bruto}

def _hora(valor, defecto: str) -> time:
    if isinstance(valor, time): return valor
    if isinstance(valor, str):
        try: return time.fromisoformat(valor)
        except ValueError: pass
    return time.fromisoformat(defecto)

def _inicio(cfg: dict) -> time:
    inicio = _hora(cfg["inicio"], DEFECTO["inicio"])
    if inicio < time(12) and inicio >= max(_hora(cfg["fin_habil"], DEFECTO["fin_habil"]), _hora(cfg["fin_no_habil"], DEFECTO["fin_no_habil"])):
        return _hora(DEFECTO["inicio"], DEFECTO["inicio"])
    return inicio

def _urgentes(cfg: dict) -> set[str]:
    esperados = set(DEFECTO["urgentes"])
    valor = cfg.get("urgentes")
    if isinstance(valor, list) and all(isinstance(x, str) for x in valor) and set(valor) == esperados and len(valor) == len(esperados):
        return esperados
    return esperados

def _local(ahora: datetime) -> datetime:
    return ahora.replace(tzinfo=TZ) if ahora.tzinfo is None else ahora.astimezone(TZ)

def _fechas(datos, anio: int | None = None) -> set[str]:
    if not isinstance(datos, list) or not datos: return set()
    salida = set()
    for item in datos:
        if not isinstance(item, dict) or not isinstance(item.get("date"), str): return set()
        try:
            fecha = date.fromisoformat(item["date"])
            if anio is not None and fecha.year != anio: return set()
            salida.add(fecha.isoformat())
        except ValueError: return set()
    return salida

def _feriados_cache(anio: int) -> tuple[set[str], str]:
    try: fechas = _fechas(json.loads((CACHE_DIR / f"feriados-{anio}.json").read_text(encoding="utf-8")), anio)
    except (OSError, ValueError): fechas = set()
    return (fechas, "Boostr (copia)") if fechas else (set(), "sin dato")

def es_feriado(ahora: datetime) -> tuple[bool, str]:
    local = _local(ahora); cfg = configuracion(); propios = set()
    for valor in cfg["feriados_locales"] if isinstance(cfg["feriados_locales"], list) else []:
        if isinstance(valor, date): propios.add(valor.isoformat())
        elif isinstance(valor, str):
            try: propios.add(date.fromisoformat(valor).isoformat())
            except ValueError: pass
    remoto, fuente = _feriados_cache(local.year); clave = local.date().isoformat()
    return clave in propios | remoto, "local" if clave in propios else fuente

def _fin_del_dia(fecha: date, tz=TZ) -> datetime:
    cfg = configuracion(); feriado, _ = es_feriado(datetime.combine(fecha, time.min, tz))
    clave = "fin_no_habil" if fecha.weekday() >= 5 or feriado else "fin_habil"
    return datetime.combine(fecha, _hora(cfg[clave], DEFECTO[clave]), tz)

def en_descanso(ahora: datetime) -> bool:
    local = _local(ahora); inicio = _inicio(configuracion())
    if inicio < time(12):
        return inicio <= local.timetz().replace(tzinfo=None) < _fin_del_dia(local.date(), local.tzinfo).timetz().replace(tzinfo=None)
    return local.timetz().replace(tzinfo=None) >= inicio or local < _fin_del_dia(local.date(), local.tzinfo)

def fin_descanso(ahora: datetime) -> datetime | None:
    local = _local(ahora); inicio = _inicio(configuracion())
    if inicio < time(12):
        return _fin_del_dia(local.date(), local.tzinfo) if en_descanso(local) else None
    if local.timetz().replace(tzinfo=None) >= inicio: return _fin_del_dia(local.date() + timedelta(days=1), local.tzinfo)
    return _fin_del_dia(local.date(), local.tzinfo) if en_descanso(local) else None

def refrescar_feriados(ahora: datetime, url: str = URL_BOOSTR, abrir=urllib.request.urlopen) -> str:
    local = _local(ahora); destino = CACHE_DIR / f"feriados-{local.year}.json"
    try:
        with abrir(url, timeout=10) as respuesta: bruto = json.loads(respuesta.read().decode("utf-8"))
        datos = bruto.get("data") if isinstance(bruto, dict) else bruto
        if not _fechas(datos, local.year): raise ValueError("respuesta de feriados vacía o inválida")
        CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o755)
        os.chmod(CACHE_DIR, 0o755)
        fd, nombre = tempfile.mkstemp(prefix=".feriados-", dir=CACHE_DIR)
        with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(datos, f, ensure_ascii=False)
        os.chmod(nombre, 0o644)
        os.replace(nombre, destino); return "Boostr"
    except Exception: return "Boostr (copia)" if destino.exists() else "sin dato"

def es_urgente(texto: str, alerta_id: str | None = None, nivel: str | None = None) -> bool:
    urgentes = _urgentes(configuracion())
    return ("luks" in urgentes and alerta_id == "luks") or ("cpu" in urgentes and alerta_id == "medidor:temp_soc") or ("error" in urgentes and (nivel == "error" or texto.startswith("🚩")))

def _abrir_cola(flags: int) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(COLA, flags | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode): os.close(fd); raise OSError("cola no regular")
    os.fchmod(fd, 0o600); return fd

def encolar(texto: str, ahora: datetime) -> None:
    fd = _abrir_cola(os.O_WRONLY | os.O_APPEND)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX); os.write(fd, (json.dumps({"momento": _local(ahora).isoformat(), "texto": texto}, ensure_ascii=False) + "\n").encode())
    finally: fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)

def sacar_resumen() -> list[dict]:
    try: fd = _abrir_cola(os.O_RDONLY)
    except FileNotFoundError: return []
    try: fcntl.flock(fd, fcntl.LOCK_SH); bruto = os.read(fd, 8 * 1024 * 1024).decode("utf-8", "replace")
    finally: fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
    salida = []
    for linea in bruto.splitlines():
        try:
            valor = json.loads(linea)
            if isinstance(valor, dict) and isinstance(valor.get("texto"), str):
                valor["_descanso_linea"] = linea + "\n"
                salida.append(valor)
        except json.JSONDecodeError: pass
    return salida

def confirmar_resumen(items: list[dict]) -> None:
    """Vacía sólo después de entregar; retiene lo anexado durante el envío."""
    if not items: return
    fd = _abrir_cola(os.O_RDWR | os.O_APPEND)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX); os.lseek(fd, 0, os.SEEK_SET)
        lineas = os.read(fd, 8 * 1024 * 1024).decode("utf-8", "replace").splitlines(True)
        pendientes, conservar = list(items), []
        for linea in lineas:
            if pendientes and linea == pendientes[0].get("_descanso_linea"):
                pendientes.pop(0)
            else:
                conservar.append(linea)
        os.lseek(fd, 0, os.SEEK_SET); os.ftruncate(fd, 0); os.write(fd, "".join(conservar).encode())
    finally: fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("orden", choices=("estado", "refrescar")); a = p.parse_args(); ahora = datetime.now(TZ)
    fuente = refrescar_feriados(ahora) if a.orden == "refrescar" else es_feriado(ahora)[1]; fin = fin_descanso(ahora)
    print(json.dumps({"descanso": en_descanso(ahora), "fin": fin.isoformat() if fin else None, "feriados": fuente, "urgentes": sorted(_urgentes(configuracion()))}, ensure_ascii=False))
    return 0 if a.orden != "refrescar" or fuente == "Boostr" else 1
if __name__ == "__main__": raise SystemExit(main())
