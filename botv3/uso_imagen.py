"""«¿Quién tiene margen?» en una imagen, para /uso (encargo 90).

Dibuja el `panel` que entrega ``bots-info --margen`` (``panel_margen`` en ``pi/bots-info.py``):
los números, los textos, los anchos de cada tramo y el rojo ya vienen resueltos ahí, con el
mismo cálculo que pinta la página 💳 Cuentas de Cockpit. Acá no se recalcula nada; si se
recalculara, el bot y el panel terminarían discrepando.

Es puro, en el molde de ``clima_imagen.py``: no habla con Telegram ni escribe archivos. Pillow
se importa dentro de ``tarjeta_png``: sin él, levanta ``ImportError`` y el bot manda el texto
de siempre. La letra es la misma Lato de ``clima_imagen.fuente`` (con su respaldo y su aviso).

Herramienta sin Telegram: ``python3 uso_imagen.py panel.json salida.png`` (el JSON puede ser la
salida entera de ``bots-info --margen`` o sólo su ``panel``).
"""

from __future__ import annotations

from io import BytesIO
import json
import sys
from typing import Any

import clima_imagen

ANCHO = 1080
MARGEN = 36
RELLENO = 30
ALTO_MAX = 4000

# Los tokens oscuros de pi/cockpit-comun/tokens.css y los tonos de cola de cuentas.css.
COLORES = {
    "fondo": "#151514", "tarjeta": "#1f1f1e", "borde": "#33332f", "texto": "#ecebe6",
    "tenue": "#9d9c95", "ok": "#4cc27c", "ok_fondo": "#173123", "mal": "#ec6a6a",
    "ojo": "#e5a93a", "ojo_fondo": "#3a2c12", "chip": "#2a2a28",
}
COLAS = ("#5b8ff0", "#a77cf0", "#3cb8b0", "#e06a9f")


def color_cola(i: int) -> str:
    """`colorCola` de cuentas.js: el lugar de la cola entre las activas, cuatro tonos."""
    return COLAS[int(i) % 4]


def _f(tamano: int, negrita: bool = False):
    return clima_imagen.fuente(tamano, negrita)


def _mezcla(a: str, b: str, t: float) -> tuple[int, int, int]:
    """`a` sobre `b` con opacidad `t`."""
    ca = [int(a[k:k + 2], 16) for k in (1, 3, 5)]
    cb = [int(b[k:k + 2], 16) for k in (1, 3, 5)]
    return tuple(round(x * t + y * (1 - t)) for x, y in zip(ca, cb))


class _Lienzo:
    """Escribe de arriba abajo con ajuste de línea. Los segmentos son (texto, tamaño, negrita, color)."""

    def __init__(self, draw, x0: int, ancho: int):
        self.draw, self.x0, self.ancho = draw, x0, ancho

    def parrafo(self, y: int, segmentos, alto: int | None = None) -> int:
        palabras = []
        for texto, tamano, negrita, color in segmentos:
            partes = texto.split(" ")
            for k, p in enumerate(partes):
                palabras.append((p, tamano, negrita, color, k < len(partes) - 1))
        tam = max(s[1] for s in segmentos)
        alto = alto or round(tam * 1.32)
        x = self.x0
        for p, tamano, negrita, color, espacio in palabras:
            font = _f(tamano, negrita)
            w = self.draw.textlength(p, font=font)
            sp = self.draw.textlength(" ", font=font)
            if x > self.x0 and x + w > self.x0 + self.ancho:
                x, y = self.x0, y + alto
            if p:
                self.draw.text((x, y), p, font=font, fill=color)
            x += w + (sp if espacio else 0)
        return y + alto


def _pastilla(draw, x: int, y: int, texto: str, color: str, fondo: str) -> int:
    font = _f(22, True)
    w = draw.textlength(texto, font=font)
    draw.rounded_rectangle((x, y, x + w + 24, y + 34), radius=17, fill=fondo)
    draw.text((x + 12, y + 4), texto, font=font, fill=color)
    return int(x + w + 24 + 10)


def _barra(imagen, x: int, y: int, ancho: int, alto: int, barra: dict[str, Any] | None, chica: bool = False) -> None:
    """La barra de `barraVentana`: uso de color, la carga rayada en el tono de cada cola, lo
    libre en gris y la línea roja del tope."""
    from PIL import Image, ImageDraw

    capa = Image.new("RGB", (ancho, alto), COLORES["chip"])
    d = ImageDraw.Draw(capa)
    pos = 0.0
    usado = float(barra.get("usado") or 0) if barra else 0.0
    color_uso = COLORES["mal"] if barra and barra.get("clase") == "lleno" else (
        COLORES["ojo"] if barra and barra.get("clase") == "justo" else COLORES["ok"])
    if usado > 0:
        d.rectangle((0, 0, round(ancho * usado / 100), alto), fill=color_uso)
        pos = usado
    for t in (barra or {}).get("tramos") or []:
        x0, x1 = round(ancho * pos / 100), round(ancho * (pos + float(t["ancho"])) / 100)
        base = _mezcla(color_cola(t["i"]), COLORES["tarjeta"], .6)
        d.rectangle((x0, 0, x1, alto), fill=base)
        claro = tuple(round(c * .65 + 255 * .35) for c in base)
        for k in range(x0 - alto, x1, 8):        # rayas a 45°, como el repeating-linear-gradient
            d.line((k, alto, k + alto, 0), fill=claro, width=3)
        d.line((x0, 0, x0, alto), fill=COLORES["tarjeta"], width=1)
        pos += float(t["ancho"])
    if barra and barra.get("proxima") is not None:
        x1 = round(ancho * float(barra["proxima"]) / 100)
        base = _mezcla(COLAS[0], COLORES["tarjeta"], .6)
        d.rectangle((0, 0, x1, alto), fill=base)
        claro = tuple(round(c * .65 + 255 * .35) for c in base)
        for k in range(-alto, x1, 8):
            d.line((k, alto, k + alto, 0), fill=claro, width=3)
        d.rectangle((x1, 0, ancho, alto), fill=COLORES["chip"])
    mascara = Image.new("L", (ancho, alto), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, ancho - 1, alto - 1), radius=alto // 2, fill=255)
    imagen.paste(capa, (x, y), mascara)
    tope = (barra or {}).get("tope")
    if tope is not None:
        xt = x + round(ancho * float(tope) / 100)
        ImageDraw.Draw(imagen).rectangle((xt - 2, y - 5, xt + 1, y + alto + 5), fill=COLORES["mal"])


def _ventana(imagen, lienzo: _Lienzo, y: int, v: dict[str, Any]) -> int:
    T, t = COLORES["texto"], COLORES["tenue"]
    if v["estado"] == "sin_dato":
        return lienzo.parrafo(y, [(v["texto"], 30, False, t)]) + 10
    if v["estado"] == "renovada":
        y = lienzo.parrafo(y, [(v["etiqueta"], 30, True, T), (": ya se renovó", 30, False, T),
                               (v.get("nota") or "", 30, False, t)])
    else:
        seg = [(v["etiqueta"], 30, True, T), (f": {v['usado']} usado · ", 30, False, T), (f"{v['libre']} libre", 30, True, T)]
        if v.get("sobre_umbral") is not None:
            seg.append((f" · sobre el umbral ({v['sobre_umbral']} %)", 30, False, COLORES["mal"]))
        y = lienzo.parrafo(y, seg)
    c = v.get("capacidad")
    if c:
        y = lienzo.parrafo(y + 2, [("Capacidad", 27, True, t), (": " + c["texto"][0], 27, False, t),
                                   (c["texto"][1], 27, bool(c["sobre_tope"]), COLORES["mal"] if c["sobre_tope"] else t),
                                   (c["texto"][2], 27, False, t)])
    _barra(imagen, lienzo.x0, y + 8, lienzo.ancho, 18, v.get("barra"))
    y += 8 + 18 + 12
    if v.get("despues"):
        dsp = v["despues"]
        # Lato no trae «↻»: «↻ desde las 21:30: …» se dibuja como «Desde las 21:30: …».
        texto = dsp["texto"].replace("↻ ", "", 1)
        y = lienzo.parrafo(y, [(texto[:1].upper() + texto[1:], 26, False, t)])
        _barra(imagen, lienzo.x0, y + 4, lienzo.ancho, 10, {"usado": 0, "tramos": [], "proxima": dsp["ancho"], "tope": dsp["tope"]})
        y += 4 + 10 + 12
    if v.get("renueva"):
        y = lienzo.parrafo(y, [(v["renueva"], 27, False, t)])
    return y + 14


def _tarjeta(imagen, draw, y0: int, c: dict[str, Any]) -> int:
    x0, x1 = MARGEN, ANCHO - MARGEN
    lienzo = _Lienzo(draw, x0 + RELLENO, x1 - x0 - 2 * RELLENO)
    y = y0 + RELLENO
    draw.text((lienzo.x0, y), c["nombre"], font=_f(36, True), fill=COLORES["texto"])
    x = int(lienzo.x0 + draw.textlength(c["nombre"], font=_f(36, True)) + 16)
    if c.get("con_margen"):
        x = _pastilla(draw, x, y + 4, "la con más margen", COLORES["ok"], COLORES["ok_fondo"])
    if c.get("sobre"):
        _pastilla(draw, x, y + 4, "el bot la salta", COLORES["ojo"], COLORES["ojo_fondo"])
    y += 58
    for v in c["ventanas"]:
        y = _ventana(imagen, lienzo, y, v)
    if c.get("leyenda"):
        font = _f(25)
        xl = lienzo.x0
        draw.text((xl, y), "Carga comprometida:", font=font, fill=COLORES["tenue"])
        xl += draw.textlength("Carga comprometida:", font=font) + 18
        for item in c["leyenda"]:
            w = draw.textlength(item["cola"], font=font)
            if xl + 26 + w > lienzo.x0 + lienzo.ancho:
                xl, y = lienzo.x0, y + 36
            draw.rounded_rectangle((xl, y + 8, xl + 18, y + 26), radius=4, fill=color_cola(item["i"]))
            draw.text((xl + 26, y), item["cola"], font=font, fill=COLORES["tenue"])
            xl += 26 + w + 22
        y += 44
    if c.get("renueva_semana"):
        y = lienzo.parrafo(y, [(c["renueva_semana"], 26, False, COLORES["tenue"])])
    y = lienzo.parrafo(y, [(c["medido"], 26, False, COLORES["tenue"])])
    y1 = y + RELLENO - 10
    borde = COLORES["ojo"] if c.get("sobre") else COLORES["borde"]
    draw.rounded_rectangle((x0, y0, x1, y1), radius=22, outline=borde, width=2)
    return y1


def validar(panel: Any) -> dict[str, Any]:
    """El `panel` de bots-info, o su salida entera. ValueError si no tiene la forma."""
    if isinstance(panel, dict) and "panel" in panel and "tarjetas" not in panel:
        panel = panel["panel"]
    if not (isinstance(panel, dict) and isinstance(panel.get("tarjetas"), list) and isinstance(panel.get("resumen"), dict)):
        raise ValueError("bots-info no trae el panel del margen")
    for c in panel["tarjetas"]:
        if not (isinstance(c, dict) and isinstance(c.get("nombre"), str) and isinstance(c.get("ventanas"), list)
                and all(isinstance(v, dict) and v.get("estado") in ("sin_dato", "renovada", "medida") for v in c["ventanas"])):
            raise ValueError("una tarjeta del panel no tiene la forma esperada")
    return panel


def pie(panel: dict[str, Any]) -> str:
    """La línea que acompaña la foto: la misma frase de arriba de la página."""
    r = validar(panel)["resumen"]
    return f"{r.get('nombre', '')}{r.get('texto', '')}".strip()


def tarjeta_png(panel: dict[str, Any]) -> bytes:
    """PNG de 1080 px de ancho (el alto, según las cuentas) con «¿Quién tiene margen?».
    Levanta ImportError sin Pillow y ValueError si el panel no tiene la forma."""
    from PIL import Image, ImageDraw

    panel = validar(panel)
    imagen = Image.new("RGB", (ANCHO, ALTO_MAX), COLORES["fondo"])
    draw = ImageDraw.Draw(imagen)
    lienzo = _Lienzo(draw, MARGEN, ANCHO - 2 * MARGEN)
    # Lato no trae emojis: el título va sin el ⏳ de la página.
    titulo = (panel.get("titulo") or "¿Quién tiene margen?").replace("⏳", "").strip()
    y = lienzo.parrafo(30, [(titulo, 42, True, COLORES["texto"])]) + 4
    r = panel["resumen"]
    y = lienzo.parrafo(y, [(r.get("nombre") or "", 31, True, COLORES["texto"]),
                           (r.get("texto") or "", 31, False, COLORES["texto"] if r.get("nombre") else COLORES["tenue"])]) + 14
    for c in panel["tarjetas"]:
        y = _tarjeta(imagen, draw, y, c) + 18
    if panel.get("gratis"):
        y = lienzo.parrafo(y, [(f"Sin cuenta pagada: {', '.join(panel['gratis'])}. Su límite es el gratis de cada "
                                "proveedor; al llegar, el bot pasa al siguiente.", 25, False, COLORES["tenue"])])
    if not panel.get("con_carga"):
        y = lienzo.parrafo(y + 4, [("Sin la carga comprometida de las colas: no hay dato fresco del panel de encargos.",
                                    25, False, COLORES["tenue"])])
    y = lienzo.parrafo(y + 4, [("El % es del límite de la cuenta entera (bots, sesiones de la Pi y los PC), "
                                "el mismo de la página Cuentas de Cockpit.", 25, False, COLORES["tenue"])])
    imagen = imagen.crop((0, 0, ANCHO, min(ALTO_MAX, y + 26)))
    salida = BytesIO()
    imagen.save(salida, "PNG", optimize=True)
    return salida.getvalue()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("uso: python3 uso_imagen.py panel.json salida.png")
    with open(sys.argv[1], encoding="utf-8") as fh:
        datos = json.load(fh)
    with open(sys.argv[2], "wb") as fh:
        fh.write(tarjeta_png(datos))
