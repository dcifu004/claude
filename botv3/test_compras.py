#!/usr/bin/env python3
"""Pruebas de la lista de compras compartida y del reconocimiento por voz.

    python3 test_compras.py

No toca Telegram ni la Pi: apunta `BOTV3_CASA_DIR` a un temporal. Las pruebas
que importan no son las de "agregar funciona" sino las tres que corresponden a
errores que este diseño puede cometer en silencio: el archivo que nace 0600 y
deja al otro perfil afuera, el dictado que parte "aceite de oliva" en tres
compras, y el borrado por texto que se lleva lo que no era.
"""

from __future__ import annotations

import os
import json
import stat
import sys
import tempfile
from pathlib import Path

# La consola de Windows es cp1252 y revienta con los emoji del resumen. En la Pi
# ya es utf-8; esto sólo evita que una prueba en verde termine en traceback.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

TMP = tempfile.mkdtemp(prefix="test-compras-")
os.environ["BOTV3_CASA_DIR"] = TMP
sys.path.insert(0, str(Path(__file__).resolve().parent))

import compras  # noqa: E402

FALLAS: list[str] = []


def check(nombre: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  ok  {nombre}")
    else:
        FALLAS.append(f"{nombre}{': ' + detalle if detalle else ''}")
        print(f"FALLA  {nombre} {detalle}")


def limpiar() -> None:
    compras.vaciar()


print("— partir un dictado —")
check("separa por comas y por 'y'",
      compras.partir("tomates, aceite de oliva y queso") ==
      ["tomates", "aceite de oliva", "queso"],
      str(compras.partir("tomates, aceite de oliva y queso")))
check("NO parte por espacios cuando no hay separador",
      compras.partir("aceite de oliva") == ["aceite de oliva"])
check("descarta duplicados dentro del mismo dictado",
      compras.partir("pan, Pan, PAN") == ["pan"])
check("aguanta 'y' dentro de una palabra",
      compras.partir("yogur, yerba") == ["yogur", "yerba"])

print("— agregar —")
limpiar()
agregados, repetidos = compras.agregar(["tomates", "queso"], "jaime")
check("agrega dos", agregados == ["tomates", "queso"] and not repetidos)
agregados, repetidos = compras.agregar(["Tomates"], "pilar")
check("no duplica ignorando mayúsculas y tildes",
      not agregados and repetidos == ["Tomates"])
check("hay dos ítems", len(compras.leer()) == 2)
check("guarda quién pidió cada cosa",
      compras.leer()[0]["quien"] == "jaime")

print("— permisos, que es donde esto falla en silencio —")
if not compras.POSIX:
    # Windows no tiene modos POSIX: esta prueba sólo concluye en la Pi, que es
    # donde el problema existe. Se dice que se saltó en vez de darla por buena.
    print("  -- saltado: no es POSIX (corre esto en la Pi antes de desplegar)")
else:
    modo = stat.S_IMODE(os.stat(compras.LISTA).st_mode)
    check("el archivo queda 0660 y no 0600", modo == 0o660, oct(modo))
    os.umask(0o077)  # lo que hace la unidad con UMask=0077
    compras.agregar(["leche"], "pilar")
    modo = stat.S_IMODE(os.stat(compras.LISTA).st_mode)
    check("sigue 0660 aunque la umask sea 0077", modo == 0o660, oct(modo))

print("— buscar y eliminar —")
limpiar()
compras.agregar(["leche descremada", "leche condensada", "pan"], "jaime")
check("buscar encuentra las dos leches",
      len(compras.buscar("leche")) == 2)
check("buscar no borra", len(compras.leer()) == 3)
ids = [i["id"] for i in compras.buscar("leche condensada")]
check("elimina sólo la que se eligió",
      compras.eliminar(ids) == ["leche condensada"])
check("quedan dos", len(compras.leer()) == 2)
check("eliminar un id que ya no está no rompe",
      compras.eliminar(ids) == [])

print("— formato para leer y para escuchar —")
limpiar()
compras.agregar(["pan", "queso"], "jaime")
check("el texto del chat muestra checklist y quién",
      "⬜ pan" in compras.formatear() and "jaime" in compras.formatear())
check("lo hablado no lleva números ni emoji",
      compras.para_recitar() == "En la lista hay 2 cosas: pan y queso.",
      compras.para_recitar())
limpiar()
check("vacía se dice distinto en voz",
      compras.para_recitar() == "La lista de compras está vacía.")

print("— forma real de listas pegadas y deshacer —")
check("no corrompe decimales", compras.partir("1.5 kg de papas, pan") == ["1.5 kg de papas", "pan"])
check("limpia viñeta y casilla Markdown", compras.partir("- [ ] pan\n- [x] leche") == ["pan", "leche"])
limpiar()
r = compras.agregar(["tomates aceite de oliva queso"], "jaime")
check("agregar guarda ultima_accion JSON", bool(compras.puede_deshacer("jaime")))
check("deshacer borra el ítem dictado sin separador", compras.deshacer("jaime") == ["tomates aceite de oliva queso"])

print("— archivo corrupto —")
compras.LISTA.write_text("{esto no es json", encoding="utf-8")
check("un JSON roto no revienta, arranca vacío", compras.leer() == [])
compras.agregar(["arroz"], "jaime")
check("y se puede volver a escribir encima", len(compras.leer()) == 1)

print("— JSON anterior sin campos nuevos —")
compras.LISTA.write_text(json.dumps({"version": 1, "items": [
    {"id": "a1b2c3d4", "texto": "arroz", "quien": "jaime", "ts": "2026-09-19 12:00"}
]}), encoding="utf-8")
check("marca un ítem antiguo sin epoch ni comprado", compras.alternar("a1b2c3d4", "pilar") is True)
check("termina el ítem antiguo y guarda historial", compras.terminar_compra() == ["arroz"]
      and compras.leer() == [])

print("— intención en lenguaje natural —")
# Se prueba el regex sin importar botv3.py entero (necesita token y perfiles):
# se reconstruye igual que allá, que es justo lo que hay que mantener en sync.
import re  # noqa: E402

# Cada bot sólo responde a SU nombre: el de Jaime no atiende "hola Pilar", y eso
# es correcto — son dos chats distintos. Por eso el vocativo se parametriza acá,
# igual que en botv3.py, donde sale del perfil cargado.
def vocativo_re(perfil: str, nombre: str) -> re.Pattern[str]:
    return re.compile(
        rf"^\s*(?:hola|hey|oye|ok|buenas|ya)?[\s,]*(?:{perfil}|{nombre})\b[\s,:.!¡¿?-]*",
        re.IGNORECASE)


VOCATIVO_RE = vocativo_re("jaime", "Jaime")
# El vocabulario se LEE de botv3.py (encargo 61): antes era una copia a mano y
# nada avisaba si se desfasaba. Son literales de texto, así que `ast` basta.
import ast  # noqa: E402
import unicodedata  # noqa: E402

_FUENTE = ast.parse((Path(__file__).resolve().parent / "botv3.py").read_text(encoding="utf-8"))
_VOCABULARIO = {nodo.targets[0].id: ast.literal_eval(nodo.value) for nodo in _FUENTE.body
                if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name)
                and nodo.targets[0].id in {"_LISTA", "_AGREGAR", "_QUITAR", "_REVISAR", "_ENVIAR"}}
_LISTA, _AGREGAR, _QUITAR, _REVISAR, _ENVIAR = (
    _VOCABULARIO[n] for n in ("_LISTA", "_AGREGAR", "_QUITAR", "_REVISAR", "_ENVIAR"))


def _plano(texto: str) -> str:
    """Igual que en botv3.py: minúsculas, sin tildes y con el mismo largo."""
    salida = []
    for c in texto:
        base = unicodedata.normalize("NFD", c)[0]
        bajo = base.lower()
        salida.append(bajo if len(bajo) == 1 else base)
    return "".join(salida)


FALTA = [
    re.compile(r"^\s*(?:nos\s+)?(?:falta|faltan|se\s+acabo|se\s+nos\s+acabo)\s+(.+?)\s*[.!]?$", re.S),
    re.compile(r"^\s*(?:necesit(?:o|amos)|hay\s+que\s+comprar|tenemos\s+que\s+comprar|acuerdate\s+de\s+comprar|compr(?:a|ar)(?!s\b))\s+(.+?)\s*[.!]?$", re.S),
]
NO_ES_COMPRA = re.compile(r"^\s*(?:que\s+|de\s+)?\w{3,}(?:ar|er|ir)\b", re.I)
ENV_A = re.compile(rf"^\s*(?:{_ENVIAR})\s+(?:me\s+)?(?:{_LISTA})\s+a\s+([a-z]+)\s*[.!?]?$")
AGR = [re.compile(rf"^\s*(?:{_AGREGAR})\s+(?:a\s+|en\s+|al\s+)?(?:{_LISTA})[\s:,.-]+(.+)$", re.S),
       re.compile(rf"^\s*(?:{_AGREGAR})\s+(.+?)\s+(?:a|en|al)\s+(?:{_LISTA})\s*[.!]?$", re.S)]
QUI = [re.compile(rf"^\s*(?:{_QUITAR})\s+(.+?)\s+(?:de|del)\s+(?:{_LISTA})\s*[.!]?$", re.S),
       re.compile(rf"^\s*(?:{_QUITAR})\s+(?:de\s+|del\s+)?(?:{_LISTA})[\s:,.-]+(.+)$", re.S)]
REV = re.compile(rf"^\s*(?:{_REVISAR})\s+(?:a\s+)?(?:{_LISTA})\s*[.!?]?$")
ENV = re.compile(rf"^\s*(?:{_ENVIAR})\s+(?:me\s+)?(?:{_LISTA})\s*[.!?]?$")


def intencion(texto: str, voc: re.Pattern[str] = VOCATIVO_RE):
    limpio = voc.sub("", texto, count=1).strip()
    plano = _plano(limpio)

    def grupo(m):
        return limpio[m.start(1):m.end(1)].strip()
    for p in QUI:
        if (m := p.match(plano)):
            return "quitar", grupo(m)
    for p in AGR:
        if (m := p.match(plano)):
            return "agregar", grupo(m)
    if (m := ENV_A.match(plano)):
        return "enviar_a", grupo(m)
    if ENV.match(plano):
        return "enviar", ""
    if REV.match(plano):
        return "revisar", ""
    for p in FALTA:
        if (m := p.match(plano)) and not NO_ES_COMPRA.match(m.group(1).strip()):
            return "agregar", grupo(m)
    return None


casos = [
    ("hola jaime agregar a lista de compras tomates, aceite de oliva, queso",
     ("agregar", "tomates, aceite de oliva, queso")),
    ("Jaime, agrega tomates a la lista", ("agregar", "tomates")),
    ("anota pan en la lista de compras", ("agregar", "pan")),
    ("qué hay en la lista", ("revisar", "")),
    ("saca el queso de la lista", ("quitar", "el queso")),
    ("elimina de la lista de compras el pan", ("quitar", "el pan")),
    ("manda la lista de compras", ("enviar", "")),
    ("pásame la lista", ("enviar", "")),
]
for frase, esperado in casos:
    check(f"«{frase[:44]}»", intencion(frase) == esperado, str(intencion(frase)))

print("— como se dice en la casa, sin nombrar la lista —")
for frase, esperado in [
    ("falta leche", ("agregar", "leche")),
    ("nos falta pan y queso", ("agregar", "pan y queso")),
    ("se acabó el café", ("agregar", "el café")),
    ("necesitamos papel higiénico", ("agregar", "papel higiénico")),
    ("hay que comprar tomates", ("agregar", "tomates")),
    ("acuérdate de comprar plátanos", ("agregar", "plátanos")),
]:
    check(f"«{frase}»", intencion(frase) == esperado, str(intencion(frase)))

print("— la guarda del infinitivo: tareas que NO son compras —")
for frase in [
    "falta terminar el informe",
    "necesito revisar el contrato de Calama",
    "nos falta cerrar la licitación",
    "hay que comprar",          # sin complemento no es nada
]:
    check(f"no captura «{frase[:38]}»", intencion(frase) is None,
          str(intencion(frase)))

print("— enviar a otra persona de la casa —")
for frase, esperado in [
    ("manda la lista a pilar", ("enviar_a", "pilar")),
    ("pásame la lista de compras a camila", ("enviar_a", "camila")),
    ("envía la lista a jaime", ("enviar_a", "jaime")),
    ("manda la lista", ("enviar", "")),
]:
    check(f"«{frase}»", intencion(frase) == esperado, str(intencion(frase)))

print("— el buzón entre perfiles —")
compras.BUZON = Path(TMP) / "buzon"
pid = compras.dejar_pedido("pilar", "jaime")
check("el pedido queda escrito", (compras.BUZON / f"{pid}.json").exists())
check("el destinatario equivocado no lo ve", compras.recoger_pedidos("jaime") == [])
recogidos = compras.recoger_pedidos("pilar")
check("el destinatario correcto lo recibe",
      len(recogidos) == 1 and recogidos[0]["de"] == "jaime")
check("y se borra al leerlo, no se entrega dos veces",
      compras.recoger_pedidos("pilar") == [])
import json as _json  # noqa: E402
pid = compras.dejar_pedido("pilar", "jaime")
viejo = compras.BUZON / f"{pid}.json"
datos = _json.loads(viejo.read_text(encoding="utf-8"))
datos["epoch"] -= compras.TTL_BUZON + 60
viejo.write_text(_json.dumps(datos), encoding="utf-8")
recogidos = compras.recoger_pedidos("pilar")
check("un pedido viejo llega marcado como vencido",
      len(recogidos) == 1 and recogidos[0].get("vencido") is True)

print("— ítems viejos —")
limpiar()
compras.agregar(["pan fresco", "pilas AAA"], "jaime")
check("recién anotado, nada es viejo", compras.viejos() == [])
with compras._Sesion(escribe=True) as s:
    s.items[1]["epoch"] -= int((compras.DIAS_VIEJO + 7) * 86400)
vencidos = compras.viejos()
check("el de 3 semanas sale marcado",
      len(vencidos) == 1 and vencidos[0]["texto"] == "pilas AAA")
check("y se ve en el texto con los días",
      "⏳ 21d" in compras.formatear(), compras.formatear())
check("el reciente no lleva marca",
      "pan fresco  · jaime\n" in compras.formatear() + "\n")
with compras._Sesion(escribe=True) as s:
    # Un ítem anterior al 20-09-2026 no tiene `epoch`. Si tampoco se puede leer
    # el ts, la edad es desconocida y NO debe marcarse: ofrecer borrar algo
    # recién anotado es peor que dejar un ítem viejo de más.
    s.items[0].pop("epoch", None)
    s.items[0]["ts"] = "fecha rara"
check("edad desconocida no cuenta como vieja",
      all(v["texto"] != "pan fresco" for v in compras.viejos()))

print("— el buzón avisa de vuelta —")
compras.BUZON = Path(TMP) / "buzon2"
pid = compras.dejar_pedido("jaime", "pilar", tipo="aviso",
                           texto="No te pude entregar la lista")
aviso = compras.recoger_pedidos("jaime")
check("el aviso llega con su texto",
      len(aviso) == 1 and aviso[0]["tipo"] == "aviso"
      and "No te pude" in aviso[0]["texto"], str(aviso))

print("— el vocativo es de cada bot —")
VOC_PILAR = vocativo_re("pilar", "Pilar")
check("el bot de Pilar entiende «hola pilar revisar lista de compras»",
      intencion("hola pilar revisar lista de compras", VOC_PILAR) == ("revisar", ""))
check("el bot de Jaime NO atiende a «hola pilar»",
      intencion("hola pilar revisar lista de compras") is None)
check("y el de Pilar tampoco atiende a «Jaime»",
      intencion("Jaime, agrega tomates a la lista", VOC_PILAR) is None)

print("— sinónimos y pronombres pegados (encargo 61) —")
for frase, esperado in [
    ("muéstrame el carrito", ("revisar", "")),
    ("enséñame la lista del súper", ("revisar", "")),
    ("abre el carro de las compras", ("revisar", "")),
    ("qué tengo en mis compras", ("revisar", "")),
    ("agrégame plátanos al carrito", ("agregar", "plátanos")),
    ("sácame el pan de la lista del supermercado", ("quitar", "el pan")),
    ("mándame la lista a Camila", ("enviar_a", "Camila")),
]:
    check(f"«{frase}»", intencion(frase) == esperado, str(intencion(frase)))

print("— lo que NO debe capturar —")
no_capturar = [
    "cuánto vale la lista de útiles del colegio",
    "qué temperatura hay en el living",
    "resume la última nota de mi proyecto",
    "agrega una columna a la planilla de costos",
    # «el carro» es el auto en Chile: no es sinónimo de la lista.
    "muéstrame el carro",
    "lava el carro",
    "saca el auto del carro",
]
for frase in no_capturar:
    check(f"deja pasar «{frase[:40]}»", intencion(frase) is None,
          str(intencion(frase)))

print()
if FALLAS:
    print(f"❌ {len(FALLAS)} fallas:")
    for f in FALLAS:
        print(f"   · {f}")
    sys.exit(1)
print("✅ todo en verde")
