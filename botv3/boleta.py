"""Reglas locales de la ruta boleta; el modelo sólo propone datos, Python decide."""
from __future__ import annotations

import json
import os
import re
import http.client
import socket
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SOCKET = "/run/google-puente-hogar.sock"
TTL = 24 * 60 * 60
REPARTOS = {"40/60", "50/50", "100/0", "0/100"}
FORMULA = ("=", "+", "-", "@")
MONTO_TOPE = 10_000_000
# «15000», «15.000», «$15.000» o «15 lucas»; el número tiene que ir solo, así que
# «15.5 lucas» o «15000feria» no se adivinan.
MONTO_MANUAL = re.compile(r"\$?\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:\s+(lucas?))?(?:\s+(.+))?", re.I)


class PuenteNoDisponible(RuntimeError):
    pass


class _ConexionUnix(http.client.HTTPConnection):
    def __init__(self, ruta: str, timeout: float):
        super().__init__("google-puente-hogar", timeout=timeout); self.ruta = ruta
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); self.sock.settimeout(self.timeout); self.sock.connect(self.ruta)


def puente(operacion: str, datos: dict[str, Any], ruta: str = SOCKET) -> dict[str, Any]:
    con = None
    try:
        con = _ConexionUnix(ruta, 40); con.request("POST", "/" + operacion, json.dumps(datos), {"Content-Type": "application/json"})
        respuesta = json.loads(con.getresponse().read())
    except (OSError, ValueError) as exc:
        raise PuenteNoDisponible(f"el puente de hogar no responde ({exc})") from exc
    finally:
        if con is not None:
            con.close()
    if not respuesta.get("ok"): raise RuntimeError(respuesta.get("error", "error desconocido del puente"))
    return respuesta


def validar_modelo(crudo: str | dict[str, Any], hoy: date | None = None) -> dict[str, Any]:
    """Normaliza la única forma admitida. Fecha dudosa no se inventa ni corrige."""
    hoy = hoy or date.today()
    try:
        d = json.loads(crudo) if isinstance(crudo, str) else crudo
    except (TypeError, json.JSONDecodeError):
        d = {}
    if not isinstance(d, dict): d = {}
    total = d.get("total")
    if isinstance(total, bool) or not isinstance(total, int) or total <= 0: total = None
    fecha_txt, fecha_ok = d.get("fecha"), True
    try:
        fecha = datetime.strptime(str(fecha_txt), "%d/%m/%Y").date()
        if not hoy - timedelta(days=60) <= fecha <= hoy: fecha_ok = False
    except (TypeError, ValueError):
        fecha, fecha_ok = None, False
    comercio = " ".join(str(d.get("comercio") or "").split())[:120]
    detalle = " ".join(str(d.get("detalle") or "").split())[:160]
    documento = " ".join(str(d.get("n_documento") or "").split())[:50] or None
    return {"fecha": fecha.strftime("%d/%m/%Y") if fecha else None, "fecha_valida": fecha_ok,
            "comercio": comercio or "Comercio sin identificar", "detalle": detalle,
            "total": total, "n_documento": documento}


def _sin_formula(texto: str) -> str:
    # El puente escribe C con USER_ENTERED: lo que empieza con = + - @ sería una
    # fórmula. El ' de adelante lo deja como texto y Sheets no lo muestra.
    return "'" + texto if texto[:1] in FORMULA else texto


def concepto(item: dict[str, Any]) -> str:
    extra = item.get("detalle") or (f"N° {item['n_documento']}" if item.get("n_documento") else "")
    # También para la foto: el comercio lo lee un modelo desde una imagen ajena y
    # «concepto …» de ✏️ lo escribe cualquiera. Ya protegido, no se dobla el '.
    return _sin_formula(" · ".join(x for x in (item.get("comercio"), extra) if x))[:250]


def desde_texto(linea: str, pagador: str, hoy: date | None = None) -> dict[str, Any]:
    """«15000 feria, 50/50» → el mismo item de una boleta. Sin modelo ni adivinanza."""
    hoy = hoy or date.today()
    primero, _, resto = str(linea or "").partition(",")
    m = MONTO_MANUAL.fullmatch(" ".join(primero.split()))
    if not m:
        raise ValueError("Falta el monto al principio, por ejemplo «15000 feria»")
    total = int(m.group(1).replace(".", "")) * (1000 if m.group(2) else 1)
    nombre = m.group(3) or ""
    if not nombre:
        raise ValueError("Falta el concepto después del monto, por ejemplo «15000 feria»")
    item = {"fecha": hoy.strftime("%d/%m/%Y"), "fecha_valida": hoy - timedelta(days=60) <= hoy <= hoy,
            "comercio": _sin_formula(nombre)[:250], "detalle": "", "total": total, "n_documento": None,
            "pagador": pagador, "reparto": "40/60", "origen": "manual"}
    # Lo que sigue a la primera coma son las mismas correcciones de ✏️.
    item = corregir(item, resto, hoy)
    if not item.get("total"):
        raise ValueError(TOPE_AVISO)
    return revisar_tope(item)


TOPE_AVISO = "El monto tiene que ser mayor que cero y no pasar de $10.000.000"


def revisar_tope(item: dict[str, Any]) -> dict[str, Any]:
    """Tope del gasto manual, en el texto inicial y tras cada ✏️. La foto no cambia."""
    total = item.get("total")
    if item.get("origen") == "manual" and isinstance(total, int) and total > MONTO_TOPE:
        raise ValueError(TOPE_AVISO)
    return item


def propuesta(item: dict[str, Any], pagador: str, duplicados: list[dict[str, Any]] | None = None,
              encabezado: str | None = None) -> str:
    fecha = item.get("fecha") or "⚠️ fecha por corregir"
    monto = f"${item['total']:,}".replace(",", ".") if item.get("total") else "⚠️ monto por corregir"
    alerta = []
    if not item.get("fecha_valida"): alerta.append("⚠️ La fecha está fuera de los últimos 60 días o es futura: corrígela.")
    if not item.get("total"): alerta.append("⚠️ No pude leer el total: corrígelo antes de anotar.")
    if duplicados:
        alerta.append("⚠️ Posible duplicado: " + ", ".join(f"fila {d['fila']} ({d['fecha']})" for d in duplicados))
    if item.get("aviso_duplicados"):
        alerta.append(str(item["aviso_duplicados"]))
    encabezado = encabezado or ("✍️ Gasto" if item.get("origen") == "manual" else "🧾 Boleta")
    return "\n".join([encabezado, f"{fecha} · {concepto(item)} · {monto}",
                      f"Paga: {pagador} · {item.get('reparto', '40/60')}", *alerta])


def corregir(item: dict[str, Any], linea: str, hoy: date | None = None) -> dict[str, Any]:
    """Aplica correcciones separadas por coma; no usa modelo ni acepta otras órdenes."""
    hoy = hoy or date.today(); nuevo = dict(item)
    for parte in (x.strip() for x in linea.split(",") if x.strip()):
        m = re.fullmatch(r"monto\s+(\d+)", parte, re.I)
        if m:
            nuevo["total"] = int(m.group(1)); continue
        m = re.fullmatch(r"fecha\s+(\d{1,2}/\d{1,2})(?:/(\d{2,4}))?", parte, re.I)
        if m:
            ano = m.group(2) or str(hoy.year)
            if len(ano) == 2: ano = "20" + ano
            try: d = datetime.strptime(m.group(1) + "/" + ano, "%d/%m/%Y").date()
            except ValueError: raise ValueError("fecha inválida") from None
            nuevo.update(fecha=d.strftime("%d/%m/%Y"), fecha_valida=hoy - timedelta(days=60) <= d <= hoy); continue
        m = re.fullmatch(r"concepto\s+(.+)", parte, re.I)
        if m: nuevo.update(comercio=m.group(1).strip()[:250], detalle="", n_documento=None); continue
        m = re.fullmatch(r"paga\s+(Cami|Diego)", parte, re.I)
        if m: nuevo["pagador"] = m.group(1).title(); continue
        if parte in REPARTOS: nuevo["reparto"] = parte; continue
        raise ValueError(f"No entendí «{parte}»")
    if not nuevo.get("total"): nuevo["total"] = None
    return nuevo


def cargar(estado: Path) -> dict[str, Any]:
    try: datos = json.loads(estado.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    ahora = time.time()
    return {k: v for k, v in datos.items() if isinstance(v, dict) and ahora - v.get("ts", 0) <= TTL}


def guardar(estado: Path, datos: dict[str, Any]) -> None:
    estado.parent.mkdir(parents=True, exist_ok=True)
    temporal = estado.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, estado)


def nueva(estado: Path, item: dict[str, Any]) -> str:
    datos = cargar(estado); ident = uuid.uuid4().hex[:12]
    datos[ident] = {"ts": time.time(), "item": item}; guardar(estado, datos)
    return ident


def sacar(estado: Path, ident: str) -> dict[str, Any] | None:
    datos = cargar(estado); item = datos.pop(ident, None); guardar(estado, datos)
    return item
