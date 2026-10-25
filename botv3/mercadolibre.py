#!/usr/bin/env python3
"""Mercado Libre para Dcs_v3bot: vigilar precios y cotizar, sin IA (encargo 40, 10-10-2026).

Tres cosas en un módulo, porque comparten el cliente del puente y la lista:

- lo que usa el bot: leer un enlace o un umbral, la lista de vigilados y los textos de
  /vigilar, /vigilados, /dejar, /cotizar y la línea de /estado;
- la revisión que corre `ml-vigilar.timer` 5 veces al día, a minutos al azar (`mercadolibre.py revisar`);
- la medición de cobertura de /cotizar (`mercadolibre.py cobertura`).

Nada de esto tiene el token de Mercado Libre: todo pasa por ml-puente (/run/ml-puente.sock),
que sólo lee. Y sólo se vigilan productos de CATÁLOGO (enlaces …/p/MLC<dígitos>): la API
responde 403 a las publicaciones sueltas (…/MLC-<dígitos>-…_JM, …/up/MLCU<dígitos>).

Archivos, en /opt/nodo/datos/mercadolibre/ (dentro del LUKS, de dcifu004):

- `vigilados.json`: la lista. La escribe el bot cuando el usuario toca ✅, y nadie más.
- `estado.json`: lo que vio la última revisión de cada producto y qué se avisó. La escribe
  sólo la revisión. Dos archivos y dos escritores: ninguno pisa al otro.
- `historial.jsonl`: una línea por producto y revisión, con el mínimo.

Avisos: por el camino que ya existe. La revisión deja el texto en la bandeja de salida
(encargos/registro_avisos.py, desplegado junto a este archivo) y `avisos.py` lo manda por
@Dcs_v5bot en su próximo ciclo; también queda en la pestaña 🔔 Avisos. Si la bandeja no lo
acepta, NO se marca como avisado y se vuelve a intentar en la revisión siguiente.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import fcntl
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import time
from typing import Any, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")
# Las dos rutas se pueden mover por entorno para que las pruebas no toquen las reales.
SOCKET = os.environ.get("BOTV3_ML_SOCKET", "/run/ml-puente.sock")
DIR = Path(os.environ.get("BOTV3_ML_DIR", "/opt/nodo/datos/mercadolibre"))
MAX_VIGILADOS = 30
MAX_HISTORIAL_BYTES = 2 * 1024 * 1024
MAX_NOMBRE = 80
COTIZAR_N = 5
# Ya avisada una baja, se vuelve a avisar sólo si el precio cae al menos esto bajo el del aviso
# anterior: los vendedores se rebajan de a $10 entre sí y eso no es otra baja.
PASO_NUEVA_BAJA = 0.02
ENLACE = "https://www.mercadolibre.cl/p/{}"
LINEA_AUTORIZAR = "sudo ml-oauth url"
LINEA_SECRETO = "sudo ml-oauth cargar-secreto"
BUSQUEDAS_COBERTURA = ("zapatilla nike court vision", "parlante edifier",
                       "bomba diafragma 12v", "esp32 devkit")

RE_ID = re.compile(r"MLC\d{6,12}")
RE_CATALOGO = re.compile(r"/p/(MLC\d{6,12})(?=/|$)", re.IGNORECASE)
RE_SUELTA = re.compile(r"/MLC-\d+|/up/MLCU\d+|/MLCU\d+", re.IGNORECASE)
RE_PORCENTAJE = re.compile(r"-?\s*(\d{1,2}(?:[.,]\d)?)\s*%")
RE_PRECIO = re.compile(r"\$?\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?")
_FORMA_SECRETO = re.compile(r"APP_USR-[A-Za-z0-9_-]+|TG-[A-Za-z0-9_-]{8,}")

NO_ES_CATALOGO = (
    "Ese enlace es de una publicación suelta, no de un producto de catálogo. Mercado Libre no "
    "deja leer publicaciones sueltas por su API, así que no la puedo vigilar. Sirven los enlaces "
    "que traen /p/MLC… (la ficha del producto, donde compiten varias ofertas).")
USO_VIGILAR = ("Uso: /vigilar <enlace o id> <precio | -N%>\n"
               "Ejemplos: /vigilar MLC44720703 89990 · /vigilar <enlace con /p/MLC…> -10%")


class NoVigilable(ValueError):
    """Lo que el usuario mandó no sirve; el texto es la frase para el chat."""


class PuenteNoDisponible(RuntimeError):
    """El socket no responde: puente caído, sin desplegar o volumen cerrado."""


class ErrorPuente(RuntimeError):
    def __init__(self, mensaje: str, codigo: str = "error", reintentar_en: int = 0):
        super().__init__(mensaje)
        self.codigo, self.reintentar_en = codigo, reintentar_en


def limpio(texto: Any) -> str:
    """El bot no tiene el token, pero ningún texto del puente llega al chat sin este filtro."""
    return _FORMA_SECRETO.sub("[oculto]", " ".join(str(texto).split()))


# ───────────────────────────────────────────────────────────── lo que escribe el usuario

def extraer_id(texto: str) -> str:
    """El id de catálogo de un enlace …/p/MLC… (con o sin #… y ?…) o de un id suelto."""
    t = texto.strip()
    if RE_ID.fullmatch(t.upper()):
        return t.upper()
    if re.fullmatch(r"MLC-\d+|MLCU\d+", t, re.IGNORECASE):
        raise NoVigilable(NO_ES_CATALOGO)
    if "://" not in t and re.match(r"(?i)(www\.|articulo\.)?mercadolibre\.", t):
        t = "https://" + t
    try:
        u = urlsplit(t)
        host = (u.hostname or "").lower()
    except ValueError:
        u, host = None, ""
    if u is None or u.scheme not in ("http", "https") or not (
            host == "mercadolibre.cl" or host.endswith(".mercadolibre.cl")):
        raise NoVigilable("No reconozco eso como un id MLC… ni como un enlace de mercadolibre.cl. "
                          "Abre el producto y copia el enlace completo: tiene que traer /p/MLC…")
    m = RE_CATALOGO.search(u.path)
    if m:
        return m.group(1).upper()
    if RE_SUELTA.search(u.path) or host.startswith("articulo."):
        raise NoVigilable(NO_ES_CATALOGO)
    raise NoVigilable("Ese enlace no trae /p/MLC…: no es la ficha de un producto de catálogo, y "
                      "sólo ésas se pueden vigilar por la API.")


def parse_umbral(texto: str) -> dict[str, Any]:
    """«89990», «$89.990» → precio fijo; «-10%», «10 %» → baja N % desde que se empezó a vigilar."""
    t = re.sub(r"(?i)\bclp\b", "", texto).strip()
    m = RE_PORCENTAJE.fullmatch(t)
    if m:
        n = float(m.group(1).replace(",", "."))
        if not 0 < n < 100:
            raise NoVigilable("El porcentaje tiene que estar entre 0 y 100, por ejemplo -10%.")
        return {"tipo": "porcentaje", "valor": n}
    m = RE_PRECIO.fullmatch(t)
    if m:
        v = int(m.group(1).replace(".", ""))
        if not 0 < v <= 1_000_000_000:
            raise NoVigilable("Ese precio no sirve como umbral.")
        return {"tipo": "precio", "valor": v}
    raise NoVigilable("No entendí el umbral: va un precio (89990 o $89.990) o una baja (-10%).\n"
                      + USO_VIGILAR)


def parse_vigilar(argumento: str) -> tuple[str, dict[str, Any]]:
    primero, _, resto = argumento.strip().partition(" ")
    if not primero or not resto.strip():
        raise NoVigilable(USO_VIGILAR)
    return extraer_id(primero), parse_umbral(resto)


def objetivo(umbral: dict[str, Any], base: float | None) -> int | None:
    """El precio en pesos bajo el cual se avisa; None si es «-N %» y todavía no hay precio base."""
    if umbral.get("tipo") == "precio":
        return int(umbral["valor"])
    if base is None:
        return None
    # (100 − N) antes de dividir: 99.900 × 0,9 en coma flotante puede dar 89.909,99….
    return math.floor(round(base * (100 - float(umbral["valor"])) / 100, 6))


# ───────────────────────────────────────────────────────────── formato

def pesos(v: float | None) -> str:
    return "sin precio" if v is None else "$" + f"{int(round(v)):,}".replace(",", ".")


def nombre_corto(nombre: Any, largo: int = MAX_NOMBRE) -> str:
    n = limpio("".join(c for c in str(nombre or "") if c.isprintable())) or "(sin nombre)"
    return n if len(n) <= largo else n[:largo - 1].rstrip() + "…"


def cuando(momento: Any, ahora: datetime | None = None) -> str:
    """«hoy 12:04», «ayer 18:10» o «08-10 06:17», en hora de Santiago."""
    try:
        d = (datetime.fromtimestamp(momento, TZ) if isinstance(momento, (int, float))
             else datetime.fromisoformat(str(momento)).astimezone(TZ))
    except (ValueError, TypeError, OverflowError, OSError):
        return "sin fecha"
    dias = ((ahora or datetime.now(TZ)).astimezone(TZ).date() - d.date()).days
    dia = "hoy" if dias == 0 else "ayer" if dias == 1 else d.strftime("%d-%m")
    return f"{dia} {d:%H:%M}"


def texto_umbral(umbral: dict[str, Any], base: float | None) -> str:
    meta = objetivo(umbral, base)
    if umbral.get("tipo") == "precio":
        return f"a {pesos(meta)} o menos"
    n = f"{umbral['valor']:g}".replace(".", ",")
    if meta is None:
        return f"baja {n} % desde el primer precio que vea"
    return f"baja {n} % desde {pesos(base)}: {pesos(meta)} o menos"


def descuento(precio: float, original: float | None) -> str:
    if original is None or original <= precio:
        return ""
    return f" (-{round((1 - precio / original) * 100)} %, antes {pesos(original)})"


# ───────────────────────────────────────────────────────────── el puente

def sin_acceso(ruta: str | None = None) -> str:
    """"" si este proceso puede hablar con el puente; si no, la frase para el chat. El permiso
    es el del socket (root:captura 0660): un bot fuera de ese grupo no tiene Mercado Libre."""
    ruta = ruta or SOCKET
    if not os.path.exists(ruta):
        return "Mercado Libre no está disponible ahora: el puente no está arriba (¿volumen cerrado?)."
    if not os.access(ruta, os.R_OK | os.W_OK):
        return "Mercado Libre no corresponde a este bot."
    return ""


def puente(operacion: str, datos: dict[str, Any], ruta: str | None = None,
           timeout: float = 60) -> dict[str, Any]:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(ruta or SOCKET)
        c = http.client.HTTPConnection("localhost", timeout=timeout)
        c.sock = s
        c.request("POST", f"/{operacion}", json.dumps(datos), {"Content-Type": "application/json"})
        r = json.loads(c.getresponse().read())
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise PuenteNoDisponible(
            f"el puente a Mercado Libre no responde ({type(exc).__name__})") from exc
    finally:
        s.close()
    if not isinstance(r, dict) or not r.get("ok"):
        r = r if isinstance(r, dict) else {}
        espera = r.get("reintentar_en")
        raise ErrorPuente(limpio(r.get("error") or "error desconocido del puente")[:300],
                          str(r.get("codigo") or "error"),
                          int(espera) if isinstance(espera, (int, float)) else 0)
    return r


def frase_error(exc: Exception) -> str:
    """Un error del puente dicho para el chat."""
    if isinstance(exc, ErrorPuente) and exc.codigo in ("sin_autorizacion", "sin_configurar"):
        return f"🔑 Mercado Libre pide autorizar: {limpio(exc)}"
    if isinstance(exc, ErrorPuente) and exc.codigo == "tope":
        return f"⏳ Muchas consultas seguidas a Mercado Libre. Prueba en {exc.reintentar_en or 60} s."
    return f"❌ Mercado Libre: {limpio(exc)}"


# ───────────────────────────────────────────────────────────── archivos

def _escribir_json(ruta: Path, datos: Any) -> None:
    """Entero o nada: temporal en la misma carpeta, fsync y rename."""
    tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.nuevo")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        try:
            os.write(fd, json.dumps(datos, ensure_ascii=False, indent=1).encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _leer_json(ruta: Path) -> Any:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@contextmanager
def _cerrojo(nombre: str, espera_s: float = 5.0):
    """flock sobre un archivo de DIR. Lanza OSError si no llega en `espera_s`."""
    DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(DIR / nombre, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        limite = time.monotonic() + espera_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= limite:
                    raise OSError(f"{nombre} está ocupado") from None
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


def _umbral_valido(u: Any) -> bool:
    return (isinstance(u, dict) and u.get("tipo") in ("precio", "porcentaje")
            and isinstance(u.get("valor"), (int, float)) and not isinstance(u.get("valor"), bool)
            and u["valor"] > 0)


def leer_lista() -> list[dict[str, Any]]:
    """Los vigilados bien formados, en el orden en que se agregaron."""
    crudo = _leer_json(DIR / "vigilados.json")
    items = crudo.get("vigilados") if isinstance(crudo, dict) else None
    return [i for i in (items if isinstance(items, list) else [])
            if isinstance(i, dict) and isinstance(i.get("id"), str) and RE_ID.fullmatch(i["id"])
            and _umbral_valido(i.get("umbral"))]


def agregar(item: dict[str, Any]) -> bool:
    """Agrega un vigilado, o le cambia el umbral si ya estaba. Devuelve True si ya estaba."""
    with _cerrojo(".vigilados.lock"):
        lista = leer_lista()
        estaba = any(i["id"] == item["id"] for i in lista)
        if not estaba and len(lista) >= MAX_VIGILADOS:
            raise NoVigilable(f"Ya hay {MAX_VIGILADOS} productos vigilados: saca alguno con /dejar.")
        lista = [i for i in lista if i["id"] != item["id"]] + [item]
        _escribir_json(DIR / "vigilados.json", {"version": 1, "vigilados": lista})
    return estaba


def quitar(ident: str) -> dict[str, Any] | None:
    with _cerrojo(".vigilados.lock"):
        lista = leer_lista()
        fuera = next((i for i in lista if i["id"] == ident), None)
        if fuera is not None:
            _escribir_json(DIR / "vigilados.json",
                           {"version": 1, "vigilados": [i for i in lista if i["id"] != ident]})
    return fuera


def leer_estado() -> dict[str, Any]:
    e = _leer_json(DIR / "estado.json")
    e = e if isinstance(e, dict) else {}
    e["productos"] = e["productos"] if isinstance(e.get("productos"), dict) else {}
    e["puente"] = e["puente"] if isinstance(e.get("puente"), dict) else {}
    return e


def _al_historial(linea: dict[str, Any]) -> None:
    ruta = DIR / "historial.jsonl"
    try:
        if ruta.stat().st_size > MAX_HISTORIAL_BYTES:
            # Liviano de verdad: pasado el tope queda la mitad más nueva.
            lineas = ruta.read_text(encoding="utf-8", errors="replace").splitlines()
            tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.nuevo")
            tmp.write_text("\n".join(lineas[len(lineas) // 2:]) + "\n", encoding="utf-8")
            os.replace(tmp, ruta)
    except OSError:
        pass
    fd = os.open(ruta, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (json.dumps(linea, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


# ───────────────────────────────────────────────────────────── /vigilar, /vigilados, /dejar, /cotizar

def proponer(argumento: str, pedir: Callable[..., dict[str, Any]] | None = None,
             ahora: datetime | None = None) -> tuple[dict[str, Any], str]:
    """(item, texto de la propuesta) para /vigilar. No escribe nada: eso es `agregar`, tras el ✅."""
    pedir = pedir or puente
    ident, umbral = parse_vigilar(argumento)
    ficha = pedir("producto", {"id": ident})["producto"]
    o = pedir("ofertas", {"id": ident})
    base = o.get("minimo")
    item = {"id": ident, "nombre": nombre_corto(ficha.get("nombre"), 200), "umbral": umbral,
            "precio_base": base,
            "desde": (ahora or datetime.now(TZ)).astimezone(TZ).isoformat(timespec="seconds")}
    lineas = ["🛒 ¿Vigilo este producto?", "", f"{nombre_corto(item['nombre'])} ({ident})"]
    if base is None:
        lineas.append("Hoy no tiene ofertas. Te aviso cuando vuelva a tener.")
    else:
        envio = " · envío gratis" if o["ofertas"] and o["ofertas"][0].get("free_shipping") else ""
        lineas.append(f"Hoy: desde {pesos(base)} · {o.get('total', len(o['ofertas']))} oferta(s){envio}")
    lineas.append(f"Aviso: {texto_umbral(umbral, base)}.")
    meta = objetivo(umbral, base)
    if base is not None and meta is not None and base <= meta:
        lineas.append("Ya está bajo ese umbral: el aviso llega en la próxima revisión.")
    lineas += [ENLACE.format(ident), "", "Reviso 5 veces al día: después de las 8, 12, 16, 19 y 21:30, a un minuto al azar."]
    return item, "\n".join(lineas)


def texto_vigilados(ahora: datetime | None = None) -> str:
    lista, estado = leer_lista(), leer_estado()
    if not lista:
        return "No hay productos vigilados.\n" + USO_VIGILAR
    rev = estado.get("ultima_revision")
    lineas = [f"🛒 Vigilados en Mercado Libre ({len(lista)}) · "
              + (f"última revisión {cuando(rev, ahora)}" if rev else "aún sin revisar")]
    for n, i in enumerate(lista, 1):
        p = estado["productos"].get(i["id"]) or {}
        if p.get("desde") != i.get("desde") or "ultimo_momento" not in p:
            p = {}      # lo que haya es de una vigilancia anterior, o todavía no se revisó
        base = i.get("precio_base") if i.get("precio_base") is not None else p.get("base")
        if not p:
            actual = (f"{pesos(base)} (al agregarlo; aún sin revisar)" if base is not None
                      else "sin ofertas al agregarlo; aún sin revisar")
        elif p.get("con_ofertas") and p.get("ultimo") is not None:
            actual = f"{pesos(p['ultimo'])} ({p.get('ofertas', '?')} oferta(s))"
        else:
            actual = "sin ofertas"
        minimo = p.get("minimo_historico", base)
        visto = (f"{pesos(minimo)}" + (f" ({cuando(p['minimo_momento'], ahora)})"
                                        if p.get("minimo_momento") else "")
                 if minimo is not None else "todavía ninguno")
        lineas += ["", f"{n}. {nombre_corto(i.get('nombre'))}",
                   f"   Ahora: {actual} · mínimo visto: {visto}",
                   f"   Aviso: {texto_umbral(i['umbral'], base)}",
                   f"   {ENLACE.format(i['id'])}"]
    lineas += ["", "/dejar <n> para dejar de vigilar uno."]
    return "\n".join(lineas)


def elegir(argumento: str) -> dict[str, Any]:
    """El vigilado n.º `argumento` de /vigilados, para /dejar."""
    lista = leer_lista()
    if not lista:
        raise NoVigilable("No hay productos vigilados.")
    try:
        n = int(argumento.strip())
    except ValueError:
        raise NoVigilable("Uso: /dejar <n>, con el número que muestra /vigilados.") from None
    if not 1 <= n <= len(lista):
        raise NoVigilable(f"No hay un vigilado n.º {n}: la lista tiene {len(lista)}. Mira /vigilados.")
    return lista[n - 1]


def texto_cotizar(q: str, r: dict[str, Any]) -> str:
    productos = r.get("productos") or []
    revisados = r.get("revisados", 0)
    q = nombre_corto(q, 60)
    if not productos:
        return (f"🛒 «{q}»: no encontré productos de catálogo con ofertas (revisé {revisados}). "
                "Prueba con otras palabras, o con marca y modelo.")
    lineas = [f"🛒 «{q}» — {len(productos)} producto(s) con ofertas, de {revisados} revisados"]
    for n, p in enumerate(productos, 1):
        usado = "" if p.get("condition") in ("new", "") else " · usado o reacondicionado"
        lineas += ["", f"{n}. {nombre_corto(p.get('nombre'))}",
                   f"   {pesos(p.get('minimo'))}{descuento(p['minimo'], p.get('original_price'))}"
                   + (" · envío gratis" if p.get("free_shipping") else "")
                   + f" · {p.get('ofertas', '?')} oferta(s){usado}",
                   f"   {ENLACE.format(p['id'])}"]
    if r.get("cortado"):
        lineas += ["", "Corté la búsqueda por tiempo: puede haber más."]
    lineas += ["", "Para seguir uno: /vigilar <id o enlace> <precio | -N%>"]
    return "\n".join(lineas)


def cotizar(q: str, pedir: Callable[..., dict[str, Any]] | None = None) -> str:
    pedir = pedir or puente
    q = " ".join(q.split())
    if len(q) < 2:
        raise NoVigilable("Uso: /cotizar <texto>, por ejemplo /cotizar parlante edifier")
    return texto_cotizar(q, pedir("buscar_catalogo", {"q": q[:120], "n": COTIZAR_N}))


def linea_estado(pedir: Callable[..., dict[str, Any]] | None = None,
                 ahora: datetime | None = None) -> str:
    """La línea de /estado: autorización, última renovación, vigilados y última revisión.
    Nunca lanza ni trae un secreto."""
    try:
        e = (pedir or puente)("estado", {}, timeout=5)
        if e.get("autorizado"):
            salud = "autorizado" + (f" · renovó el token {cuando(e['renovado'], ahora)}"
                                    if e.get("renovado") else " · token aún sin renovar")
            if e.get("guardado") is False:
                salud += " · ⚠️ el token rotado no se pudo guardar"
        elif e.get("estado") == "sin_configurar":
            salud = f"🔑 falta cargar la Secret Key ({LINEA_SECRETO})"
        else:
            salud = f"🔑 sin autorización ({LINEA_AUTORIZAR})"
    except Exception:  # noqa: BLE001 — /estado no se cae por Mercado Libre
        salud = "el puente no responde"
    try:
        n, rev = len(leer_lista()), leer_estado().get("ultima_revision")
        resto = (f"{n} vigilado{'s' if n != 1 else ''} · "
                 + (f"última revisión {cuando(rev, ahora)}" if rev else "sin revisiones todavía"))
    except Exception:  # noqa: BLE001
        resto = "no pude leer la lista"
    return f"🛒 Mercado Libre: {salud} · {resto}"


# ───────────────────────────────────────────────────────────── la revisión (5 veces al día)

_RA_MOD = None


def _registro_avisos():
    """encargos/registro_avisos.py: el registro único y la bandeja de salida. Desplegado al lado
    de este archivo; en el vault está en encargos/."""
    global _RA_MOD
    if _RA_MOD is None:
        aca = Path(__file__).resolve().parent
        ruta = next((p for p in (aca / "registro_avisos.py", aca.parent / "encargos" / "registro_avisos.py")
                     if p.is_file()), None)
        if ruta is None:
            raise OSError("no encuentro registro_avisos.py")
        spec = importlib.util.spec_from_file_location("registro_avisos", ruta)
        _RA_MOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_RA_MOD)
    return _RA_MOD


def avisar(texto: str, linea: str | None = None) -> bool:
    """Deja el aviso en la bandeja de salida (lo manda avisos.py) y en el registro único.
    True sólo si la bandeja lo aceptó: lo que no salió no se da por avisado."""
    try:
        ra = _registro_avisos()
        if not (ra.bandeja_activa() and ra.a_la_bandeja(limpio(texto))):
            return False
        ra.registrar("mercadolibre", limpio(texto), linea)
        return True
    except Exception as exc:  # noqa: BLE001 — avisar no puede tumbar la revisión
        print(f"no se pudo dejar el aviso ({type(exc).__name__})", file=sys.stderr)
        return False


def _revisar_producto(item: dict[str, Any], p: dict[str, Any], o: dict[str, Any],
                      momento: str, avisar_fn: Callable[..., bool]) -> None:
    """Actualiza `p` (el estado del producto) con lo que devolvió `ofertas` y avisa lo que cambió.
    Cada marca de «ya avisé» se pone sólo si el aviso salió."""
    nombre, enlace = nombre_corto(item.get("nombre")), ENLACE.format(item["id"])
    minimo = o.get("minimo")
    con = minimo is not None
    p.update(ultimo=minimo, ultimo_momento=momento, con_ofertas=con,
             ofertas=o.get("total", 0), revisiones=int(p.get("revisiones") or 0) + 1)
    p.pop("error", None)
    # Lo último que el usuario sabe: al agregarlo vio si tenía ofertas (la propuesta lo dice),
    # así que ese es el punto de partida y no un aviso.
    if "dicho_con_ofertas" not in p:
        p["dicho_con_ofertas"] = item.get("precio_base") is not None
    if not con:
        if p["dicho_con_ofertas"] and avisar_fn(
                f"📭 Mercado Libre: «{nombre}» se quedó sin ofertas. La sigo vigilando. {enlace}"):
            # Cuando vuelva, aunque sea al mismo precio, es una noticia nueva.
            p["dicho_con_ofertas"], p["avisado"] = False, None
        return
    if p.get("minimo_historico") is None or minimo < p["minimo_historico"]:
        p["minimo_historico"], p["minimo_momento"] = minimo, momento
    if item.get("precio_base") is None and p.get("base") is None:
        p["base"] = minimo      # «-N %» sobre un producto que se agregó sin ofertas
    base = item["precio_base"] if item.get("precio_base") is not None else p.get("base")
    meta = objetivo(item["umbral"], base)
    envio = ", con envío gratis" if o.get("ofertas") and o["ofertas"][0].get("free_shipping") else ""
    if meta is not None and minimo <= meta:
        avisado = p.get("avisado")
        if avisado is None:
            texto = (f"🔔 Mercado Libre: «{nombre}» bajó a {pesos(minimo)}{envio}. "
                     f"Umbral: {texto_umbral(item['umbral'], base)}. {enlace}")
        elif minimo <= avisado * (1 - PASO_NUEVA_BAJA):
            texto = (f"🔔 Mercado Libre: «{nombre}» siguió bajando: {pesos(minimo)}{envio} "
                     f"(el aviso anterior fue en {pesos(avisado)}). {enlace}")
        else:
            texto = ""          # la misma baja: ya se avisó
        if texto and avisar_fn(texto):
            p["avisado"] = minimo
            p["dicho_con_ofertas"] = True
        return
    p["avisado"] = None         # volvió a subir sobre el umbral: la próxima baja es otra
    if not p["dicho_con_ofertas"] and avisar_fn(
            f"📦 Mercado Libre: «{nombre}» volvió a tener ofertas: desde {pesos(minimo)}{envio}. {enlace}"):
        p["dicho_con_ofertas"] = True


def _ofertas_con_paciencia(pedir: Callable[..., dict[str, Any]], ident: str,
                           dormir: Callable[[float], None]) -> dict[str, Any]:
    """Las ofertas de un producto. Si el puente dice «tope», espera lo que pide y repite UNA vez:
    sin esto, con una lista larga siempre quedarían sin revisar los mismos del final."""
    try:
        return pedir("ofertas", {"id": ident})
    except ErrorPuente as exc:
        if exc.codigo != "tope":
            raise
        dormir(min(max(exc.reintentar_en, 5), 65))
        return pedir("ofertas", {"id": ident})


def revisar(pedir: Callable[..., dict[str, Any]] | None = None,
            avisar_fn: Callable[..., bool] | None = None,
            ahora: datetime | None = None,
            dormir: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Una pasada por la lista: consulta las ofertas de cada vigilado, deja el mínimo en el
    historial y avisa lo que cambió. Devuelve un resumen sin datos privados."""
    pedir, avisar_fn = pedir or puente, avisar_fn or avisar
    momento = (ahora or datetime.now(TZ)).astimezone(TZ).isoformat(timespec="seconds")
    resumen = {"vigilados": 0, "revisados": 0, "errores": 0, "puente": "ok"}
    with _cerrojo(".revision.lock", espera_s=0.5):
        lista, estado = leer_lista(), leer_estado()
        resumen["vigilados"] = len(lista)
        estado["productos"] = {k: v for k, v in estado["productos"].items()
                               if isinstance(v, dict) and any(i["id"] == k for i in lista)}
        salud = estado["puente"]
        for item in lista:
            p = estado["productos"].setdefault(item["id"], {})
            if p.get("desde") != item.get("desde"):
                # Se volvió a dar de alta (otro umbral, u otra vez tras /dejar): lo avisado
                # antes era de la vigilancia anterior.
                p.clear()
                p["desde"] = item.get("desde")
            try:
                o = _ofertas_con_paciencia(pedir, item["id"], dormir)
            except ErrorPuente as exc:
                if exc.codigo in ("sin_autorizacion", "sin_configurar"):
                    # Una vez, y no en cada revisión: la marca se borra recién cuando una
                    # revisión vuelve a pasar.
                    resumen["puente"] = exc.codigo
                    linea = LINEA_SECRETO if exc.codigo == "sin_configurar" else LINEA_AUTORIZAR
                    motivo = limpio(exc)
                    if not salud.get("aviso_autorizar") and avisar_fn(
                            f"🔑 Mercado Libre pide autorizar: {motivo}"
                            + ("" if linea in motivo else f". En la Pi: {linea}"), linea):
                        salud["aviso_autorizar"] = True
                    break
                resumen["errores"] += 1
                p["error"] = limpio(exc)[:200]
                if exc.codigo == "tope":
                    break
                continue
            except PuenteNoDisponible:
                # Puente caído: no es una noticia de precios. Queda en el estado y /estado lo dice.
                resumen["puente"] = "no_responde"
                break
            salud["aviso_autorizar"] = False
            _revisar_producto(item, p, o, momento, avisar_fn)
            _al_historial({"momento": momento, "id": item["id"], "minimo": o.get("minimo"),
                           "ofertas": o.get("total", 0)})
            resumen["revisados"] += 1
        salud["estado"] = resumen["puente"]
        estado.update(version=1, ultimo_intento=momento, puente=salud)
        if resumen["puente"] == "ok":
            # «Última revisión» es la última que de verdad pudo consultar precios.
            estado["ultima_revision"] = momento
        _escribir_json(DIR / "estado.json", estado)
    return resumen


# ───────────────────────────────────────────────────────────── cobertura de /cotizar

def cobertura(pedir: Callable[..., dict[str, Any]] | None = None,
              dormir: Callable[[float], None] = time.sleep,
              busquedas: tuple[str, ...] = BUSQUEDAS_COBERTURA) -> list[dict[str, Any]]:
    """Qué fracción de los primeros 20 resultados de catálogo tiene ofertas, por búsqueda.
    Cada búsqueda son hasta 21 consultas: se espacian para no pasar el tope del puente."""
    pedir, filas = pedir or puente, []
    for n, q in enumerate(busquedas):
        if n:
            dormir(30)
        for intento in (1, 2):
            try:
                r = pedir("buscar_catalogo", {"q": q, "n": 20}, timeout=90)
                filas.append({"q": q, "revisados": r.get("revisados", 0),
                              "con_ofertas": r.get("con_ofertas", 0), "cortado": bool(r.get("cortado"))})
                break
            except ErrorPuente as exc:
                if exc.codigo == "tope" and intento == 1:
                    dormir(min(max(exc.reintentar_en, 5), 70))
                    continue
                filas.append({"q": q, "error": frase_error(exc)})
                break
            except PuenteNoDisponible as exc:
                filas.append({"q": q, "error": limpio(exc)})
                break
    return filas


def texto_cobertura(filas: list[dict[str, Any]]) -> str:
    lineas, rev, con = [], 0, 0
    for f in filas:
        if "error" in f:
            lineas.append(f"{f['q']}: {f['error']}")
            continue
        rev, con = rev + f["revisados"], con + f["con_ofertas"]
        pct = f"{round(100 * f['con_ofertas'] / f['revisados'])} %" if f["revisados"] else "sin resultados"
        lineas.append(f"{f['q']}: {f['con_ofertas']} de {f['revisados']} con ofertas ({pct})"
                      + (" — cortado por tiempo" if f["cortado"] else ""))
    if rev:
        lineas.append(f"Total: {con} de {rev} ({round(100 * con / rev)} %)")
    return "\n".join(lineas)


def main(args: list[str]) -> int:
    if args == ["revisar"]:
        falta = sin_acceso()
        if falta:
            print(falta, file=sys.stderr)
            return 1
        try:
            r = revisar()
        except OSError as exc:
            print(f"no se pudo revisar: {exc}", file=sys.stderr)
            return 1
        print(f"vigilados={r['vigilados']} revisados={r['revisados']} errores={r['errores']} "
              f"puente={r['puente']}")
        return 0
    if args == ["cobertura"]:
        print(texto_cobertura(cobertura()))
        return 0
    if args == ["lista"]:
        print(texto_vigilados())
        return 0
    if args == ["estado"]:
        print(linea_estado())
        return 0
    print("uso: mercadolibre.py revisar | cobertura | lista | estado", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
