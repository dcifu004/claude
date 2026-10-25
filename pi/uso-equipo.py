#!/usr/bin/env python3
"""Agrega el uso interactivo de un PC Windows sin sacar transcripts del PC.

Corre con Python 3.12 y sólo stdlib.  ``uso.py`` sigue siendo la fuente única
de la interpretación de los JSONL: acá se preparan los incrementos y se le
entregan directorios temporales, nunca se replica su contabilidad.
"""
import argparse
import datetime as dt
import glob
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import tomllib
import copy

RAIZ = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("uso_compartido", RAIZ / "pi" / "uso.py")
uso = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uso)
TZ = uso.TZ
RETENCION = dt.timedelta(days=35)


def _localappdata():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "uso-equipo"


def _perfil_usuario():
    return Path(os.environ.get("USERPROFILE", str(Path.home())))


def _json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as fh:
            dato = json.load(fh)
        return dato if isinstance(dato, type(defecto)) else defecto
    except (OSError, ValueError):
        return defecto


def _atomico(ruta, dato):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    with open(temporal, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dato, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(temporal, ruta)


def _cuenta_claude():
    cfg = _json(_perfil_usuario() / ".claude.json", {})
    correo = ((cfg.get("oauthAccount") or {}).get("emailAddress") or "").strip().lower()
    try:
        with open(RAIZ / "botv3" / "cuentas.toml", "rb") as fh:
            cuentas = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        cuentas = {}
    for cid, datos in cuentas.items():
        if datos.get("motor") == "claude" and correo and datos.get("correo", "").lower() == correo:
            return cid
    return "claude_desconocida"


def _nuevas_lineas(rutas, estado, temporal, tipo, vistos=None):
    """Copia la cola completa por líneas y prepara cursores, sin aún publicarlos."""
    vistos = vistos if isinstance(vistos, dict) else {}
    destino = Path(temporal) / tipo
    destino.mkdir(parents=True, exist_ok=True)
    for n, ruta in enumerate(sorted(rutas)):
        clave = os.path.normcase(os.path.abspath(ruta))
        anterior = estado.get(clave, {})
        try:
            tamano = os.path.getsize(ruta)
        except OSError:
            continue
        inicio = int(anterior.get("offset", 0)) if tamano >= int(anterior.get("offset", 0)) else 0
        # Codex necesita el total anterior como punto cero; no se conserva ninguna línea.
        prelude = anterior.get("total") if tipo == "codex" else None
        # claude_por_hora expects projects/<project>/<transcript>.jsonl.
        carpeta_salida = destino / str(n) if tipo == "claude" else destino
        carpeta_salida.mkdir(parents=True, exist_ok=True)
        salida = carpeta_salida / ("rollout-%d.jsonl" % n if tipo == "codex" else "%d.jsonl" % n)
        with open(ruta, "r", encoding="utf-8", errors="replace", newline="") as origen, open(salida, "w", encoding="utf-8", newline="\n") as out:
            if prelude and tamano > inicio:
                out.write(json.dumps({"_uso_equipo_prelude": True,
                                      "timestamp": anterior.get("momento", "1970-01-01T00:00:00+00:00"),
                                      "payload": {"type": "token_count", "info": {"total_token_usage": prelude}}}) + "\n")
            origen.seek(inicio)
            datos = origen.read()
            # A CLI may be appending right now. Leave its incomplete tail for the
            # next run instead of advancing the cursor beyond it.
            completo = datos.rsplit("\n", 1)[0] + "\n" if "\n" in datos else ""
            for linea in completo.splitlines(True):
                if tipo == "claude":
                    try:
                        d = json.loads(linea)
                    except ValueError:
                        continue
                    if d.get("type") != "assistant" or not isinstance((d.get("message") or {}).get("usage"), dict):
                        continue
                    clave_id = d.get("requestId") or d.get("uuid")
                    if clave_id and clave_id in vistos:
                        continue
                    if clave_id:
                        vistos[clave_id] = d.get("timestamp") or ""
                elif '"token_count"' not in linea:
                    continue
                out.write(linea)
                if tipo == "codex":
                    try:
                        d = json.loads(linea)
                        total = ((d.get("payload") or {}).get("info") or {}).get("total_token_usage")
                        if isinstance(total, dict):
                            anterior["total"] = {k: total.get(k) or 0 for k in
                                                  ("input_tokens", "cached_input_tokens", "output_tokens")}
                            anterior["momento"] = d.get("timestamp")
                    except ValueError:
                        pass
            anterior["offset"] = inicio + len(completo.encode("utf-8"))
        estado[clave] = anterior


def _sumar(a, b):
    for hora, valores in b.items():
        destino = a.setdefault(hora, {"entrada": 0, "salida": 0, "cache_lectura": 0,
                                      "cache_escritura": 0, "mensajes": 0})
        for k in destino:
            destino[k] += int(valores.get(k, 0) or 0)


def ejecutar(raiz=RAIZ, equipo=None, ahora=None):
    ahora = ahora or dt.datetime.now(TZ)
    equipo = equipo or os.environ.get("COMPUTERNAME") or socket.gethostname()
    # El nombre termina siendo una clave, no una ruta arbitraria proveniente del entorno.
    equipo = "".join(c if c.isalnum() or c in "-_" else "_" for c in equipo) or "equipo"
    estado_dir = _localappdata()
    estado_dir.mkdir(parents=True, exist_ok=True)
    estado_path = estado_dir / "estado.json"
    estado = _json(estado_path, {})
    destino = Path(raiz) / "uso-equipos" / (equipo + ".json")
    # A corrupt previous aggregate means its matching cursors are unsafe: reset
    # both together so a recovered report is reconstructed rather than losing data.
    previo = _json(destino, None)
    if previo is None:
        if destino.exists():
            estado = {}
        previo = {}
    elif not isinstance(previo, dict):
        previo = {}
    estado_nuevo = copy.deepcopy(estado)
    with tempfile.TemporaryDirectory(dir=estado_dir if estado_dir.exists() else None) as tmp:
        perfil = _perfil_usuario()
        claude = glob.glob(str(perfil / ".claude" / "projects" / "**" / "*.jsonl"), recursive=True)
        codex = glob.glob(str(perfil / ".codex" / "sessions" / "**" / "rollout-*.jsonl"), recursive=True)
        vistos = estado_nuevo.setdefault("claude_vistos", {})
        _nuevas_lineas(claude, estado_nuevo.setdefault("claude", {}), tmp, "claude", vistos)
        _nuevas_lineas(codex, estado_nuevo.setdefault("codex", {}), tmp, "codex")
        claude_nuevo = uso.claude_por_hora(str(Path(tmp) / "claude"))
        codex_nuevo = uso.codex_por_hora([str(Path(tmp) / "codex")], incluir_limites=True)
    limite = ahora - RETENCION
    for grupo in (estado_nuevo.get("claude", {}), estado_nuevo.get("codex", {})):
        for ruta in list(grupo):
            try:
                if dt.datetime.fromtimestamp(os.path.getmtime(ruta), TZ) < limite:
                    del grupo[ruta]
            except OSError:
                del grupo[ruta]
    for clave, momento in list(estado_nuevo.get("claude_vistos", {}).items()):
        try:
            if dt.datetime.fromisoformat(momento.replace("Z", "+00:00")).astimezone(TZ) < limite:
                del estado_nuevo["claude_vistos"][clave]
        except (AttributeError, ValueError):
            del estado_nuevo["claude_vistos"][clave]
    cuentas = previo.get("cuentas") if isinstance(previo.get("cuentas"), dict) else {}
    cid = _cuenta_claude()
    c = cuentas.setdefault(cid, {"motor": "claude", "por_hora": {}, "limites": None})
    _sumar(c["por_hora"], claude_nuevo)
    x = cuentas.setdefault("codex", {"motor": "codex", "por_hora": {}, "limites": None})
    _sumar(x["por_hora"], codex_nuevo["por_hora"])
    if codex_nuevo.get("limites"):
        x["limites"] = codex_nuevo["limites"]
    # Claude no abre ni refresca su cache: sólo publica la última que ya dejó el CLI.
    cfg = _json(_perfil_usuario() / ".claude.json", {})
    cache = cfg.get("cachedUsageUtilization")
    if isinstance(cache, dict):
        c["limites"] = uso.limites_claude_cache(cfg)
    for datos in cuentas.values():
        datos["por_hora"] = {h: v for h, v in datos.get("por_hora", {}).items()
                              if _hora_valida(h, limite)}
    salida = {"version": 1, "equipo": equipo, "actualizado": ahora.isoformat(timespec="seconds"),
              "cuentas": cuentas}
    # Publish before committing cursors. If the destination is unavailable, the
    # next run reads the same tail again instead of silently losing it.
    _atomico(destino, salida)
    _atomico(estado_path, estado_nuevo)
    return salida


def _hora_valida(hora, limite):
    try:
        valor = dt.datetime.fromisoformat(hora + ":00")
        valor = valor.replace(tzinfo=TZ)
        return valor >= limite
    except ValueError:
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--instalar-tarea", action="store_true")
    a = p.parse_args()
    if a.instalar_tarea:
        script = Path(__file__).resolve()
        print(f'schtasks /Create /TN "Uso equipo" /SC MINUTE /MO 30 /TR "pyw -3.12 \\\"{script}\\\"" /F')
        return
    ejecutar()


if __name__ == "__main__":
    main()
