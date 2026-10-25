#!/usr/bin/env python3
"""temblores — avisa por el canal del nodo cuando un sismo reciente es relevante para la casa (encargo 91).

    temblores [--config RUTA] [--estado RUTA] [--simular]
    temblores --guardar-fixtures DIR        # baja las respuestas reales de las dos fuentes (para las pruebas)

Lo corre temblores.timer cada 5 min como dcifu004. DOCTRINA:

1. DOS FUENTES, LAS DOS EN CADA CORRIDA. La principal es el feed GeoJSON del USGS; el respaldo, el FDSN del
   EMSC (que para Chile publica las soluciones del CSN, agencia GUC). Se consultan ambas: si una se cae, o
   contesta algo que no se entiende, se usa la otra y queda escrito en el estado (`fuentes`) y en stderr.
   Si fallan las dos, sale con 1. El CSN (sismologia.cl) solo expone HTML: raspar se rompe en silencio
   (ver encargos-nube/91-PLAN.md).
2. LA CASA SALE DEL PERFIL: `clima.lat`/`clima.lon` de botv3/perfiles/jaime.toml, que ya son de comuna. Acá
   no se escribe ninguna coordenada, ni en el mensaje ni en el estado (el estado guarda el epicentro).
3. UN SISMO SE AVISA UNA VEZ. Lo avisado se recuerda por hora y epicentro, con tolerancia (y por id): el
   mismo sismo en las dos fuentes, o corregido después, no se repite.
4. EL CANAL ES EL DE LAS COLAS: la bandeja de salida y el registro único de encargos/registro_avisos.py.
   avisos.py (root, con el token) lo manda en su ciclo y le aplica el modo descanso con pi/descanso.py.
   Lo urgente parte con 🚩, que es lo que `descanso.es_urgente` deja pasar de noche; esta script lo comprueba
   con la biblioteca real. Lo demás, de noche, queda para el resumen de la mañana. Sin bandeja activa no se
   marca nada: se reintenta en la próxima corrida mientras el sismo tenga menos de `max_edad_h`.
5. EL MENSAJE ES CORTO Y NO TIENE NADA PERSONAL: magnitud, distancia a la casa, lugar de la fuente, hora de
   Chile y enlace. Ni la comuna ni coordenadas.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib
from typing import Any, Callable, NamedTuple
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

AQUI = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("TEMBLORES_CONFIG", str(AQUI / "temblores.toml")))
REGISTRO_AVISOS = AQUI.parent / "encargos" / "registro_avisos.py"
DESCANSO = AQUI / "descanso.py"
TZ = ZoneInfo("America/Santiago")
RADIO_TIERRA_KM = 6371.0
TOPE_BYTES = 5 * 1024 * 1024

URL_USGS = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}_day.geojson"
URL_EMSC = "https://www.seismicportal.eu/fdsnws/event/1/query"
URL_EMSC_EVENTO = "https://www.seismicportal.eu/eventdetails.html?unid={unid}"

DEFECTO: dict[str, Any] = {
    "estado": "/opt/nodo/datos/temblores/estado.json",
    "perfil": "/opt/botv3/perfiles/jaime.toml",
    "fuentes": ["usgs", "emsc"],
    "max_edad_h": 3.0,
    "tolerancia_s": 120.0,
    "tolerancia_km": 100.0,
    "retener_dias": 14.0,
    "timeout_s": 20.0,
    "regla": [{"nombre": "cerca", "mag": 5.0, "km": 300.0},
              {"nombre": "chile", "mag": 6.5, "caja": [-56.0, -17.5, -76.0, -66.0]}],
    "urgente": [{"mag": 6.5, "km": 300.0}, {"mag": 7.5, "km": 1000.0}],
}


class Sismo(NamedTuple):
    fuente: str
    id: str
    ids: tuple[str, ...]
    mag: float
    lugar: str
    t: datetime          # UTC
    lat: float
    lon: float
    prof: float | None
    url: str


# ---------------------------------------------------------------- configuración y casa

def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def cargar_config(ruta: Path | None = None) -> dict[str, Any]:
    """DEFECTO con lo que traiga el toml. Un valor que no tiene la forma esperada lanza ValueError: un
    umbral roto no puede silenciar los avisos sin que nadie se entere."""
    ruta = ruta or CONFIG
    try:
        bruto = tomllib.loads(Path(ruta).read_text(encoding="utf-8"))
    except FileNotFoundError:
        bruto = {}
    cfg = dict(DEFECTO, **{k: bruto[k] for k in DEFECTO if k in bruto})
    for k in ("max_edad_h", "tolerancia_s", "tolerancia_km", "retener_dias", "timeout_s"):
        if not _num(cfg[k]) or cfg[k] <= 0:
            raise ValueError(f"temblores.toml: `{k}` tiene que ser un número positivo")
    if not (isinstance(cfg["fuentes"], list) and cfg["fuentes"] and all(f in LECTORES for f in cfg["fuentes"])):
        raise ValueError(f"temblores.toml: `fuentes` es una lista de {', '.join(LECTORES)}")
    for clave in ("regla", "urgente"):
        if not isinstance(cfg[clave], list) or not cfg[clave]:
            raise ValueError(f"temblores.toml: falta al menos un [[{clave}]]")
        for r in cfg[clave]:
            caja = r.get("caja") if isinstance(r, dict) else None
            if not (isinstance(r, dict) and _num(r.get("mag")) and (_num(r.get("km")) or (
                    isinstance(caja, list) and len(caja) == 4 and all(_num(x) for x in caja)))):
                raise ValueError(f"temblores.toml: cada [[{clave}]] trae `mag` y `km` o `caja`")
    return cfg


def casa(perfil: str | Path) -> tuple[float, float]:
    """(lat, lon) del bloque `clima` del perfil: el de la comuna. ValueError si no está."""
    try:
        c = tomllib.loads(Path(perfil).read_text(encoding="utf-8")).get("clima")
    except (OSError, ValueError) as e:
        raise ValueError(f"no pude leer el perfil ({type(e).__name__})") from None
    if not (isinstance(c, dict) and _num(c.get("lat")) and _num(c.get("lon"))
            and -90 <= c["lat"] <= 90 and -180 <= c["lon"] <= 180):
        raise ValueError("el perfil no trae `clima` con lat y lon")
    return float(c["lat"]), float(c["lon"])


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df, dl = f2 - f1, math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_KM * math.asin(min(1.0, math.sqrt(a)))


# ---------------------------------------------------------------- fuentes

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _texto(x, tope: int = 120) -> str:
    return " ".join(_CONTROL.sub(" ", str(x or "")).split())[:tope]


def _features(cuerpo: bytes) -> list:
    d = json.loads(cuerpo.decode("utf-8"))
    if not (isinstance(d, dict) and d.get("type") == "FeatureCollection" and isinstance(d.get("features"), list)):
        raise ValueError("no es una FeatureCollection")
    return d["features"]


def leer_usgs(cuerpo: bytes) -> tuple[list[Sismo], int]:
    """El GeoJSON del USGS: (sismos, cuántos features se saltaron por malformados). ValueError si el
    cuerpo entero no tiene la forma."""
    out, malos = [], 0
    for f in _features(cuerpo):
        try:
            p, g = f["properties"], f["geometry"]["coordinates"]
            lon, lat = g[0], g[1]
            if not (_num(p["mag"]) and _num(p["time"]) and _num(lat) and _num(lon) and isinstance(f["id"], str)):
                raise ValueError
            ids = tuple(x for x in str(p.get("ids") or "").split(",") if x) or (f["id"],)
            url = p.get("url") if isinstance(p.get("url"), str) and p["url"].startswith("https://") else \
                f"https://earthquake.usgs.gov/earthquakes/eventpage/{urllib.parse.quote(f['id'])}"
            out.append(Sismo("usgs", f["id"], ids, float(p["mag"]), _texto(p.get("place")),
                             datetime.fromtimestamp(p["time"] / 1000, timezone.utc), float(lat), float(lon),
                             float(g[2]) if len(g) > 2 and _num(g[2]) else None, url))
        except (KeyError, TypeError, IndexError, ValueError, OverflowError, OSError):
            malos += 1
    return out, malos


def _iso_utc(x) -> datetime:
    d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def leer_emsc(cuerpo: bytes) -> tuple[list[Sismo], int]:
    """El JSON FDSN del EMSC (también una FeatureCollection). Lat, lon y profundidad salen de
    `properties`, que traen el signo de verdad (en `geometry` la profundidad va negativa)."""
    out, malos = [], 0
    for f in _features(cuerpo):
        try:
            p = f["properties"]
            unid = p.get("unid") or f["id"]
            if not (_num(p["mag"]) and _num(p["lat"]) and _num(p["lon"]) and isinstance(unid, str) and unid):
                raise ValueError
            ids = tuple(x for x in (unid, p.get("source_id")) if isinstance(x, str) and x)
            lugar = _texto(p.get("flynn_region")).title()
            out.append(Sismo("emsc", unid, ids, float(p["mag"]), lugar, _iso_utc(p["time"]), float(p["lat"]),
                             float(p["lon"]), float(p["depth"]) if _num(p.get("depth")) else None,
                             URL_EMSC_EVENTO.format(unid=urllib.parse.quote(unid))))
        except (KeyError, TypeError, ValueError, AttributeError):
            malos += 1
    return out, malos


LECTORES: dict[str, Callable[[bytes], tuple[list[Sismo], int]]] = {"usgs": leer_usgs, "emsc": leer_emsc}


def mag_minima(cfg: dict[str, Any]) -> float:
    return min(float(r["mag"]) for r in [*cfg["regla"], *cfg["urgente"]])


def url_de(fuente: str, cfg: dict[str, Any], ahora: datetime) -> str:
    minima = mag_minima(cfg)
    if fuente == "usgs":
        return URL_USGS.format(feed="4.5" if minima >= 4.5 else "2.5")
    desde = (ahora - timedelta(hours=float(cfg["max_edad_h"]) + 1)).astimezone(timezone.utc)
    return URL_EMSC + "?" + urllib.parse.urlencode({
        "format": "json", "limit": 500, "minmag": f"{max(0.0, minima - 0.3):.1f}",
        "start": desde.strftime("%Y-%m-%dT%H:%M:%S")})


def bajar(url: str, abrir=urllib.request.urlopen, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "nodo-pi5-temblores/1 (aviso domestico)",
                                               "Accept": "application/json"})
    with abrir(req, timeout=timeout) as r:
        estado = getattr(r, "status", 200)
        if estado != 200:
            raise ValueError(f"HTTP {estado}")
        cuerpo = r.read(TOPE_BYTES + 1)
    if len(cuerpo) > TOPE_BYTES:
        raise ValueError("respuesta demasiado grande")
    return cuerpo


def consultar(cfg: dict[str, Any], ahora: datetime, abrir=urllib.request.urlopen) -> tuple[list[Sismo], dict]:
    """Todas las fuentes, en orden. (sismos, salud por fuente). Una fuente que falla no corta a la otra."""
    sismos, salud = [], {}
    for fuente in cfg["fuentes"]:
        momento = ahora.isoformat(timespec="seconds")
        try:
            encontrados, malos = LECTORES[fuente](bajar(url_de(fuente, cfg, ahora), abrir, cfg["timeout_s"]))
        except Exception as e:  # noqa: BLE001 — una fuente rota no puede tumbar a la otra
            salud[fuente] = {"ok": False, "momento": momento, "error": f"{type(e).__name__}: {_texto(e, 200)}"}
            print(f"temblores: {fuente} no contestó bien ({salud[fuente]['error']}); se usa lo demás", file=sys.stderr)
            continue
        salud[fuente] = {"ok": True, "momento": momento, "sismos": len(encontrados), "malos": malos}
        if malos:
            print(f"temblores: {fuente} trajo {malos} sismo(s) malformado(s); se saltan", file=sys.stderr)
        sismos += encontrados
    return sismos, salud


# ---------------------------------------------------------------- decisión

def _cumple(r: dict, s: Sismo, dist: float) -> bool:
    if s.mag < float(r["mag"]):
        return False
    if _num(r.get("km")):
        return dist <= float(r["km"])
    la0, la1, lo0, lo1 = r["caja"]
    return la0 <= s.lat <= la1 and lo0 <= s.lon <= lo1


def evaluar(s: Sismo, hogar: tuple[float, float], cfg: dict[str, Any]) -> tuple[bool, bool, float]:
    """(relevante, urgente, km a la casa)."""
    dist = haversine_km(hogar[0], hogar[1], s.lat, s.lon)
    urgente = any(_cumple(r, s, dist) for r in cfg["urgente"])
    return urgente or any(_cumple(r, s, dist) for r in cfg["regla"]), urgente, dist


def mismo(a: dict, s: Sismo, cfg: dict[str, Any]) -> bool:
    """Si `s` es el sismo ya guardado `a`: un id en común, o hora y epicentro dentro de la tolerancia."""
    if set(a.get("ids") or ()) & set(s.ids):
        return True
    try:
        dt = abs((_iso_utc(a["t"]) - s.t).total_seconds())
        return dt <= float(cfg["tolerancia_s"]) and haversine_km(a["lat"], a["lon"], s.lat, s.lon) <= float(cfg["tolerancia_km"])
    except (KeyError, TypeError, ValueError):
        return False


def agrupar(sismos: list[Sismo], cfg: dict[str, Any]) -> list[list[Sismo]]:
    """Los registros de un mismo sismo (entre fuentes) juntos, en orden de llegada."""
    grupos: list[list[Sismo]] = []
    for s in sismos:
        for g in grupos:
            if any(mismo(_guardado(x), s, cfg) for x in g):
                g.append(s)
                break
        else:
            grupos.append([s])
    return grupos


def _guardado(s: Sismo) -> dict:
    return {"t": s.t.isoformat(timespec="seconds"), "lat": round(s.lat, 3), "lon": round(s.lon, 3),
            "mag": s.mag, "ids": list(s.ids), "fuente": s.fuente}


def _mag(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def mensaje(s: Sismo, dist: float, urgente: bool, ahora: datetime) -> str:
    local = s.t.astimezone(TZ)
    hora = f"{local:%H:%M}" if local.date() == ahora.astimezone(TZ).date() else f"{local:%d-%m %H:%M}"
    cabeza = "🚩 Temblor fuerte" if urgente else "🌎 Temblor"
    partes = [f"{cabeza} M {_mag(s.mag)} a {round(dist):d} km de la casa"]
    if s.lugar:
        partes.append(s.lugar)
    partes += [f"{hora} (hora de Chile)", s.url]
    return " · ".join(partes)


# ---------------------------------------------------------------- estado

def cargar_estado(ruta: Path) -> dict:
    try:
        d = json.loads(Path(ruta).read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("avisados"), list):
            return d
    except (OSError, ValueError):
        pass
    return {"version": 1, "avisados": [], "fuentes": {}}


def guardar_estado(ruta: Path, estado: dict) -> None:
    """Atómico: temporal nuevo en la misma carpeta y os.replace (crea la carpeta si falta)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    fd, tmp = tempfile.mkstemp(prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(estado, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------- canal

def _cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def publicar(texto: str, urgente: bool, ra) -> bool:
    """Bandeja de salida y registro único, como `avisar_texto` de cola-run.py: primero la bandeja y,
    solo si la aceptó, el registro (cada aviso por un solo camino)."""
    if not ra.bandeja_activa() or not ra.a_la_bandeja(texto):
        return False
    ra.registrar("temblores", texto, None, nivel="alerta" if urgente else "info")
    return True


# ---------------------------------------------------------------- corrida

def correr(cfg: dict[str, Any], estado_ruta: Path, ahora: datetime | None = None, abrir=urllib.request.urlopen,
           ra=None, descanso=None, simular: bool = False, salida=print) -> int:
    ahora = ahora or datetime.now(timezone.utc)
    hogar = casa(cfg["perfil"])
    estado = cargar_estado(estado_ruta)
    sismos, salud = consultar(cfg, ahora, abrir)
    estado["fuentes"] = salud
    ra = ra or (None if simular else _cargar("registro_avisos", REGISTRO_AVISOS))
    descanso = descanso or _cargar("descanso", DESCANSO)
    limite = ahora - timedelta(hours=float(cfg["max_edad_h"]))
    avisados = [a for a in estado["avisados"] if isinstance(a, dict)
                and _fecha_ok(a.get("avisado")) and _iso_utc(a["avisado"]) > ahora - timedelta(days=float(cfg["retener_dias"]))]
    rc_canal = 0
    for grupo in agrupar(sismos, cfg):
        if any(mismo(a, s, cfg) for a in avisados for s in grupo):
            continue
        # De lo que traen las fuentes, el registro de mayor magnitud (empate: el de la fuente principal).
        s = max(grupo, key=lambda x: (x.mag, -cfg["fuentes"].index(x.fuente)))
        if s.t < limite or s.t > ahora + timedelta(minutes=10):
            continue
        relevante, urgente, dist = evaluar(s, hogar, cfg)
        if not relevante:
            continue
        texto = mensaje(s, dist, urgente, ahora)
        if urgente and not descanso.es_urgente(texto):
            raise RuntimeError("descanso.es_urgente ya no reconoce el aviso urgente de temblores")
        if simular:
            salida(texto)
            continue
        if not publicar(texto, urgente, ra):
            print("temblores: la bandeja de avisos no está activa o no aceptó el aviso; se reintenta en la próxima "
                  "corrida", file=sys.stderr)
            rc_canal = 1
            continue
        if not urgente and descanso.en_descanso(ahora):
            print("temblores: en descanso; el aviso va al resumen de la mañana", file=sys.stderr)
        avisados.append(dict(_guardado(s), ids=sorted({i for x in grupo for i in x.ids}),
                             avisado=ahora.isoformat(timespec="seconds"), urgente=urgente))
    estado["avisados"] = avisados
    if not simular:
        guardar_estado(estado_ruta, estado)
    if salud and not any(v["ok"] for v in salud.values()):
        print("temblores: ninguna fuente contestó", file=sys.stderr)
        return 1
    return rc_canal


def _fecha_ok(x) -> bool:
    try:
        _iso_utc(x)
        return True
    except (TypeError, ValueError):
        return False


def guardar_fixtures(carpeta: Path, cfg: dict[str, Any], abrir=urllib.request.urlopen) -> int:
    carpeta.mkdir(parents=True, exist_ok=True)
    ahora, rc = datetime.now(timezone.utc), 0
    for fuente in cfg["fuentes"]:
        try:
            cuerpo = bajar(url_de(fuente, cfg, ahora), abrir, cfg["timeout_s"])
            LECTORES[fuente](cuerpo)            # que se entienda antes de guardarla
        except Exception as e:  # noqa: BLE001
            print(f"{fuente}: {type(e).__name__}: {e}", file=sys.stderr)
            rc = 1
            continue
        destino = carpeta / f"real-{fuente}-{ahora:%Y%m%d-%H%M}.json"
        destino.write_bytes(cuerpo)
        print(destino)
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path)
    ap.add_argument("--estado", type=Path)
    ap.add_argument("--simular", action="store_true", help="imprime lo que avisaría; no escribe nada")
    ap.add_argument("--guardar-fixtures", type=Path, metavar="DIR")
    a = ap.parse_args(argv)
    try:
        cfg = cargar_config(a.config)
        if a.guardar_fixtures:
            return guardar_fixtures(a.guardar_fixtures, cfg)
        return correr(cfg, a.estado or Path(cfg["estado"]), simular=a.simular)
    except ValueError as e:
        print(f"temblores: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
