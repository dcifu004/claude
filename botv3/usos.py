"""Contador de uso de los bots (encargo 92, alternativa A): una línea por uso, propia y durable.

    {"t": "2026-10-25T15:04:05-03:00", "bot": "jaime", "funcion": "compras", "canal": "voz", "resultado": "ok"}

Lo usan botv3.py (escribe, en `handle_update`) y bots-info (lee, para Cockpit), con este mismo archivo.

- NUNCA se guarda el texto del mensaje: sólo la función, de una lista cerrada (`FUNCIONES`); lo que no
  está ahí queda como «desconocido».
- El escritor no falla nunca: si no puede escribir, el bot contesta igual y queda UNA advertencia en el log.
- Un archivo por mes (`usos-AAAA-MM.jsonl`) en la carpeta `usos/` del estado del bot, 0644 en una carpeta 0755:
  no trae texto, y así Jaime puede leer el de Pilar si se le monta esa carpeta (y bots-info, que es root).
  Al arrancar, cada bot deja ahí `catalogo.json`: lo que ese bot tiene, para saber qué no se usó nunca. Se agrega con O_APPEND en
  una sola escritura. ROTAR NO PIERDE LÍNEAS porque nunca se renombra ni se reescribe nada: cada línea va al
  archivo de su mes y sólo se borra un archivo cuyo mes terminó hace más de `RETENCION_DIAS`.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterable

try:
    from zoneinfo import ZoneInfo
    TZ: Any = ZoneInfo("America/Santiago")
except Exception:  # pragma: no cover - sin base de zonas
    TZ = timezone.utc

LOG = logging.getLogger("botv3.usos")
RETENCION_DIAS = 180
DIAS_RESUMEN = 7
BOTS = ("jaime", "pilar")
CANALES = ("texto", "voz", "boton")
RESULTADOS = ("ok", "error")
RE_ARCHIVO = re.compile(r"usos-(\d{4})-(\d{2})\.jsonl")
TOPE_LECTURA = 32 * 1024 * 1024

# Funciones canónicas: el mismo nombre llegue por comando, botón o frase. Las rutas de consulta van aparte
# como «consulta:<ruta>» (la ruta, nunca la pregunta).
FUNCIONES = {
    "menu": "🏠 /menu", "ayuda": "❓ /ayuda", "acciones": "/acciones", "olvidar": "/olvidar",
    "compras": "🛒 compras", "gastos": "💳 gastos", "boleta": "🧾 boleta", "google": "📅 agenda y correo",
    "temporizadores": "⏰ temporizadores", "ordenes": "🔁 órdenes", "buscar": "🔎 buscar",
    "clima": "🌦️ clima", "hora": "🕐 hora", "comuna": "📍 comuna del clima", "estado": "🩺 estado",
    "uso": "💳 uso de cuotas", "usos": "📊 /usos", "remoto": "📱 Remote Control", "memoria": "🧠 memoria",
    "calificar": "⭐ calificar", "mercadolibre": "🛍️ Mercado Libre", "desconocido": "otro",
}
RE_CONSULTA = re.compile(r"consulta:[a-z_]{1,24}")


def funcion_valida(nombre: Any) -> str:
    """El nombre si es de la lista cerrada (o una ruta de consulta); si no, «desconocido»."""
    return nombre if isinstance(nombre, str) and (nombre in FUNCIONES or RE_CONSULTA.fullmatch(nombre)) else "desconocido"


def _local(momento: datetime | None = None) -> datetime:
    momento = momento or datetime.now(timezone.utc)
    return (momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)).astimezone(TZ)


def archivo_del_mes(carpeta: Path, momento: datetime) -> Path:
    m = _local(momento)
    return Path(carpeta) / f"usos-{m:%Y-%m}.jsonl"


class Registro:
    """El escritor. `anotar` nunca lanza; la primera falla deja una advertencia y las siguientes, nada."""

    def __init__(self, carpeta: Path | str, bot: str, reloj: Callable[[], datetime] | None = None,
                 retencion_dias: int = RETENCION_DIAS):
        self.carpeta, self.bot = Path(carpeta), bot
        self.reloj = reloj or (lambda: datetime.now(timezone.utc))
        self.retencion_dias = retencion_dias
        self.avisado = False
        self._ultimo_mes: str | None = None

    def anotar(self, funcion: str, canal: str, resultado: str) -> bool:
        try:
            momento = _local(self.reloj())
            fila = {"t": momento.isoformat(timespec="seconds"), "bot": self.bot, "funcion": funcion_valida(funcion),
                    "canal": canal if canal in CANALES else "texto",
                    "resultado": resultado if resultado in RESULTADOS else "error"}
            self.carpeta.mkdir(parents=True, exist_ok=True, mode=0o755)
            ruta = archivo_del_mes(self.carpeta, momento)
            fd = os.open(ruta, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
            try:
                os.write(fd, (json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8"))
            finally:
                os.close(fd)
            mes = f"{momento:%Y-%m}"
            if mes != self._ultimo_mes:         # una vez por mes (y al arrancar): borrar lo vencido
                self._ultimo_mes = mes
                rotar(self.carpeta, momento, self.retencion_dias)
            return True
        except Exception as exc:  # noqa: BLE001 — contar nunca puede tumbar una respuesta
            if not self.avisado:
                self.avisado = True
                LOG.warning("usos: no pude anotar en %s (%s); el bot sigue y no vuelvo a avisar",
                            self.carpeta, type(exc).__name__)
            return False


    def publicar_catalogo(self, funciones: Iterable[str]) -> bool:
        """`catalogo.json`: las funciones que este bot tiene. Atómico; nunca lanza."""
        try:
            self.carpeta.mkdir(parents=True, exist_ok=True, mode=0o755)
            tmp = self.carpeta / f".catalogo.{os.getpid()}.tmp"
            tmp.write_text(json.dumps({"bot": self.bot, "funciones": sorted({funcion_valida(f) for f in funciones})},
                                      ensure_ascii=False), encoding="utf-8")
            os.chmod(tmp, 0o644)
            os.replace(tmp, self.carpeta / "catalogo.json")
            return True
        except Exception as exc:  # noqa: BLE001
            if not self.avisado:
                self.avisado = True
                LOG.warning("usos: no pude dejar el catálogo en %s (%s)", self.carpeta, type(exc).__name__)
            return False


def leer_catalogo(carpeta: Path | str | None) -> list[str]:
    try:
        d = json.loads((Path(carpeta) / "catalogo.json").read_text(encoding="utf-8"))
        return [f for f in d.get("funciones", []) if funcion_valida(f) == f]
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def _fin_del_mes(anio: int, mes: int) -> datetime:
    sig = datetime(anio + (mes == 12), mes % 12 + 1, 1, tzinfo=TZ)
    return sig


def rotar(carpeta: Path, momento: datetime, retencion_dias: int = RETENCION_DIAS) -> list[str]:
    """Borra sólo los archivos de meses que TERMINARON hace más de `retencion_dias`. Devuelve los borrados."""
    borrados, limite = [], _local(momento) - timedelta(days=retencion_dias)
    try:
        nombres = sorted(os.listdir(carpeta))
    except OSError:
        return borrados
    for nombre in nombres:
        m = RE_ARCHIVO.fullmatch(nombre)
        if m and _fin_del_mes(int(m.group(1)), int(m.group(2))) <= limite:
            try:
                os.unlink(Path(carpeta) / nombre)
                borrados.append(nombre)
            except OSError:
                pass
    return borrados


def leer(carpeta: Path | str, desde: datetime | None = None) -> list[dict]:
    """Las líneas válidas de `carpeta` desde `desde` (incluida). Una línea rota se salta."""
    out = []
    try:
        nombres = sorted(n for n in os.listdir(carpeta) if RE_ARCHIVO.fullmatch(n))
    except OSError:
        return out
    for nombre in nombres:
        if desde is not None:
            m = RE_ARCHIVO.fullmatch(nombre)
            if _fin_del_mes(int(m.group(1)), int(m.group(2))) <= _local(desde):
                continue
        try:
            with open(Path(carpeta) / nombre, "rb") as fh:
                crudo = fh.read(TOPE_LECTURA)
        except OSError:
            continue
        for linea in crudo.decode("utf-8", "replace").splitlines():
            try:
                d = json.loads(linea)
                t = datetime.fromisoformat(d["t"])
            except (ValueError, KeyError, TypeError):
                continue
            if not isinstance(d, dict) or t.tzinfo is None or (desde is not None and t < desde):
                continue
            out.append({"t": t, "bot": str(d.get("bot")), "funcion": funcion_valida(d.get("funcion")),
                        "canal": d.get("canal") if d.get("canal") in CANALES else "texto",
                        "resultado": d.get("resultado") if d.get("resultado") in RESULTADOS else "error"})
    return out


def resumen(carpetas: dict[str, Path | str | None], catalogo: dict[str, Iterable[str]] | None = None,
            ahora: datetime | None = None, dias: int = DIAS_RESUMEN) -> dict:
    """Por bot: usos de los últimos `dias` por función (con canal y errores) y las funciones de su catálogo que
    no se usaron NUNCA en lo retenido. El catálogo de un bot que no se pasa sale de su `catalogo.json`. Una
    carpeta None o que no se puede leer sale como `legible: False`."""
    catalogo = catalogo or {}
    ahora = _local(ahora)
    desde = ahora - timedelta(days=dias)
    out = {"momento": ahora.isoformat(timespec="seconds"), "dias": dias, "retencion_dias": RETENCION_DIAS, "bots": {}}
    for bot, carpeta in carpetas.items():
        legible = carpeta is not None and os.access(carpeta, os.R_OK | os.X_OK)
        todas = leer(carpeta) if legible else []
        todas = [x for x in todas if x["bot"] == bot]
        recientes = [x for x in todas if x["t"] >= desde]
        por = defaultdict(lambda: {"total": 0, "texto": 0, "voz": 0, "boton": 0, "error": 0})
        for x in recientes:
            f = por[x["funcion"]]
            f["total"] += 1
            f[x["canal"]] += 1
            f["error"] += x["resultado"] == "error"
        usadas = {x["funcion"] for x in todas}
        propio = catalogo.get(bot)
        propio = leer_catalogo(carpeta) if propio is None and legible else (propio or ())
        primera = min((x["t"] for x in todas), default=None)
        out["bots"][bot] = {
            "legible": bool(legible), "total": len(recientes),
            "funciones": dict(sorted(por.items(), key=lambda kv: (-kv[1]["total"], kv[0]))),
            "nunca": sorted(set(propio) - usadas),
            "desde_registro": primera.isoformat(timespec="seconds") if primera else None,
        }
    return out


def nombre_funcion(f: str) -> str:
    if f.startswith("consulta:"):
        return f"💬 consulta {f.split(':', 1)[1]}"
    return FUNCIONES.get(f, f)


def texto_resumen(res: dict, nombres: dict[str, str] | None = None) -> str:
    """El mensaje de /usos: corto, por bot."""
    nombres = nombres or {"jaime": "Jaime", "pilar": "Pilar"}
    lineas = [f"📊 Usos de los últimos {res['dias']} días"]
    for bot, b in res["bots"].items():
        lineas.append("")
        if not b["legible"]:
            lineas.append(f"{nombres.get(bot, bot)}: sin dato (no puedo leer su registro)")
            continue
        lineas.append(f"{nombres.get(bot, bot)}: {b['total']} uso{'s' if b['total'] != 1 else ''}")
        for f, c in b["funciones"].items():
            canales = ", ".join(f"{k} {c[k]}" for k in ("texto", "voz", "boton") if c[k])
            lineas.append(f"• {nombre_funcion(f)}: {c['total']} ({canales.replace('boton', 'botón')})"
                          + (f" · {c['error']} con error" if c["error"] else ""))
        if b["nunca"]:
            lineas.append(f"Sin usar nunca (en {res['retencion_dias']} días): "
                          + ", ".join(nombre_funcion(f) for f in b["nunca"]))
    return "\n".join(lineas)
