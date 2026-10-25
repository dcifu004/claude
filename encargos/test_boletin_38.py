#!/usr/bin/env python3
"""Pruebas del encargo 38 (boletín en audio con Piper), sobre los archivos REALES de la muestra.

    python3 encargos/test_boletin_38.py

Nacen de la revisión 1 (encargos/38r1-RESULTADO.md). Cada clase cubre un hallazgo:

  - ContenidoTests (hallazgo 2): el guion sólo usa lo que trae la entrega. Se lee la entrega real
    y, de sólo lectura (`mode=ro`), la base de la cosecha, para comprobar que nada de lo que está
    en la base y no en la entrega llegó al guion.
  - LargoTests (hallazgo 3): palabras del guion real y duración del .ogg real, leída de sus
    páginas Ogg (no del número que imprime el script).
  - FragmentosTests (hallazgo 4): los dos fragmentos de comparación duran «unos 40 s».
  - TopeTests (hallazgo 5): con `opusenc` de verdad, un .ogg que no cabe en el tope no se escribe.
  - ParrafosTests (hallazgo 6): `--parrafos` sólo acepta enteros positivos.

La revisión 2 (encargos/38r2-RESULTADO.md, hallazgo 2) agregó a ContenidoTests la procedencia de las
UNIDADES: el guion decía «millones de pesos» y la entrega trae `$4.200 millones`, sin nombrar moneda.

No sintetiza el boletín completo ni reproduce audio. Las pruebas que necesitan Piper, opusenc o la
base se SALTAN si no están (fuera de la Pi): mirar la cuenta de `skipped`, no sólo el OK.
"""
from __future__ import annotations

import contextlib
import html
import importlib.util
import io
import os
import random
import re
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import wave
from pathlib import Path

AQUI = Path(__file__).resolve().parent
NOTICIAS = AQUI.parents[1] / "13-Agente-Noticias"
MUESTRA = NOTICIAS / "muestras" / "2026-10-09-1930"
ENTREGA = NOTICIAS / "entregas" / "2026-10-09 1930 - noticias - Pi5Diego.md"
CARTERA = NOTICIAS / "cartera-contratos.md"
SCRIPT = NOTICIAS / "pi" / "boletin_audio.py"
BASE = Path("/opt/nodo/datos/noticias/noticias.db")
HISTORIAL = Path("/opt/nodo/datos/git/13-Agente-Noticias.git")      # fotos de la hermana (fuera del vault)
FOTO_REVISADA_R2 = "abee882"        # el guion que revisó Codex en la revisión 2, con «millones de pesos»
PIPER = Path("/opt/piper/piper")
OPUSENC = Path("/usr/bin/opusenc")

# Párrafo del guion (1 = saludo) donde se cuenta cada ítem de la entrega, por hash. Los ítems 1 y 3
# son la misma nota (sitio y Mastodon de DF) y van al mismo párrafo. Los párrafos 1, 2, 10 y 11 son
# saludo, advertencia con los temas, repaso y cierre.
PARRAFO_DE = {
    "a171d958b31ca4b5": 3, "d1652e4f92ca1618": 4, "d1cf4d59799534e9": 3, "68b4f7e280d2cd9f": 5,
    "c46e9f6eb7cf86be": 6, "b5b0131d4c71b31b": 7, "231279bb537d717c": 8, "a603c649dac36453": 9,
}
# Cómo se dice en voz alta el identificador de medio de la entrega. Es lo ÚNICO del guion que no
# está literal en ella: `df-cms` no se puede leer. Queda declarado acá y en el RESULTADO.
MEDIO_DICHO = {
    "df-cms": "Diario Financiero", "masto-df": "Mastodon", "elrancaguino": "El Rancagüino",
    "masto-biobiochile": "BioBioChile en Mastodon", "timeline": "Timeline",
    "elperiodico": "El Periódico", "radiouchile": "Radio Universidad de Chile",
}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]

# Palabras corrientes con que empieza alguna frase del guion (por eso van con mayúscula). Lista
# cerrada: una mayúscula que no esté acá, ni en la entrega, ni en MEDIO_DICHO hace fallar la prueba.
INICIOS = set("""
    antes aqui buenas cuarta despues es esas eso esta este estos fondos hasta hay porque primera primero
    quinta rechazo repasamos repetimos segun segunda septima sexta tampoco tercera un una vamos
""".split())

NUMEROS = {
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
    "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100,
    "ciento": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400, "quinientos": 500,
    "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900,
}
MULTIPLOS = {"mil": 1000, "millon": 10 ** 6, "millones": 10 ** 6}

# Revisión 2, hallazgo 2. Nombres de moneda y de unidad de medida: en el guion sólo puede estar el que
# también esté en un título de la entrega (hoy, sólo «horas»). Lista cerrada y sin tildes.
MONEDAS = set("""
    peso pesos dolar dolares euro euros libra libras yen yenes yuan yuanes real reales sol soles
    bolivar bolivares uf utm fomento clp usd eur
""".split())
MEDIDAS = set("""
    kilo kilos kilogramo kilogramos gramo gramos tonelada toneladas litro litros metro metros
    kilometro kilometros hectarea hectareas dosis hora horas minuto minutos dia dias
    semana semanas mes meses ano anos
""".split())                         # «por ciento» se busca aparte: «ciento ocho» es número
# Lo que viene después de una cifra dicha y NO es su unidad. Lista cerrada.
SIN_UNIDAD = {"y", "es", "son"}
# Las únicas unidades que el guion pone por su cuenta, declaradas: a los 8 elegidos los llama
# «titulares»; 8 menos el duplicado son 7 «noticias»; la duplicada llegó 2 «veces».
UNIDAD_DERIVADA = {("elegidos", "titulares"), ("noticias distintas", "noticias"), ("veces", "veces")}


def norm(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar «Araucanía» con «araucania»."""
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def palabras(texto: str) -> list[str]:
    return re.findall(r"[a-zñ]+", norm(texto))


def titulo_limpio(titulo: str) -> str:
    """El título sin el enlace recortado que Mastodon le pega al final («… Acciona df.cl/regiones/…»).
    La revisión 1 fijó que lo que sale del enlace (región, monto en dólares) NO es título."""
    return re.split(r"\s+\S+\.cl/", titulo, maxsplit=1)[0].strip()


def leer_entrega() -> dict:
    texto = ENTREGA.read_text(encoding="utf-8")
    cabecera = dict(re.findall(r"^(\w+): (.+)$", texto.split("---")[1], flags=re.M))
    items = []
    for m in re.finditer(r"^- \[[ x]\] (?P<titulo>.*?) · `(?P<evento>[^`]*)` · `[^`]*` · \*(?P<medio>[^*]+)\*"
                         r" · \[ver\]\((?P<url>[^)]+)\) <!-- (?P<hash>[0-9a-f]{16}) [^>]*-->$", texto, flags=re.M):
        d = m.groupdict()
        d["titulo"] = html.unescape(d["titulo"])
        d["limpio"] = titulo_limpio(d["titulo"])
        items.append(d)
    return {"cabecera": cabecera, "items": items}


def leer_guion(nombre="guion.txt") -> list[str]:
    texto = (MUESTRA / nombre).read_text(encoding="utf-8")
    return [" ".join(b.split()) for b in texto.split("\n\n") if b.strip()]


def numeros_dichos(texto: str) -> list[tuple[int, str]]:
    """Cada número escrito en palabras, con su valor: «cuatro mil doscientos millones» → 4200000000.
    «un/uno/una» no se cuentan: en el guion son artículos."""
    return [(valor, como) for valor, como, _ in cifras_con_unidad(texto)]


def cifras_con_unidad(texto: str) -> list[tuple[int, str, str | None]]:
    """Como `numeros_dichos`, más la UNIDAD que el texto le pone a cada cifra: la palabra que la sigue,
    saltando un «de» («millones de pesos» → pesos; «tres detenidos» → detenidos). None si después viene
    un signo de puntuación o se acaba el texto."""
    fichas = re.findall(r"[a-zñ]+|[^\sa-zñ]", norm(texto))      # un signo de puntuación corta el número
    out, total, actual, tramo = [], 0, 0, []

    def cerrar(i):
        nonlocal total, actual, tramo
        while tramo and tramo[-1] == "y":
            tramo.pop()
            i -= 1
        if tramo:
            cola = fichas[i:i + 2]
            if cola[:1] == ["de"]:
                cola = cola[1:]
            unidad = cola[0] if cola and re.fullmatch(r"[a-zñ]+", cola[0]) else None
            out.append((total + actual, " ".join(tramo), unidad))
        total, actual, tramo = 0, 0, []

    for i, p in enumerate(fichas):
        if p in NUMEROS:
            actual += NUMEROS[p]
            tramo.append(p)
        elif p in MULTIPLOS and (tramo or p == "mil"):
            if p == "mil":
                total += max(actual, 1) * 1000
            else:
                total = (total + actual) * MULTIPLOS[p]
            actual = 0
            tramo.append(p)
        elif p == "y" and tramo and tramo[-1] in NUMEROS and NUMEROS[tramo[-1]] % 10 == 0 and NUMEROS[tramo[-1]] < 100:
            tramo.append(p)
        else:
            cerrar(i)
    cerrar(len(fichas))
    return out


def unidades_de_la_entrega(entrega: dict) -> dict[int, set[str]]:
    """Por cada número de la entrega, las unidades que ELLA le pone: la palabra que lo sigue en el título
    (`$4.200 millones en droga` → «en»: no hay moneda con nombre; `3 detenidos` → «detenidos») o, en la
    cabecera, el nombre del campo y el mes de la fecha. Más las tres derivadas declaradas."""
    cab, items = entrega["cabecera"], entrega["items"]
    out: dict[int, set[str]] = {}
    for it in items:
        for cifra, millones, sigue in re.findall(r"(\d[\d.]*)( millones)?(?:\s+(\w+))?", it["limpio"]):
            valor = int(cifra.replace(".", "")) * (10 ** 6 if millones else 1)
            out.setdefault(valor, set()).update(palabras(sigue))
    fecha = cab["corrida"].split()[0]
    out.setdefault(int(fecha[8:10]), set()).add(MESES[int(fecha[5:7]) - 1])
    out.setdefault(int(cab["candidatos"]), set()).add("candidatos")
    out.setdefault(int(cab["elegidos"]), set()).add("elegidos")
    for valor, origen in numeros_de_la_entrega(entrega).items():
        out.setdefault(valor, set()).update(u for clave, u in UNIDAD_DERIVADA if origen.startswith(clave))
    return out


def unidades_sin_respaldo(texto: str, entrega: dict) -> list[tuple[str, str]]:
    """(cifra, unidad) de cada cifra del texto cuya unidad la entrega no le pone a ese mismo número."""
    respaldo = unidades_de_la_entrega(entrega)
    return [(como, unidad) for valor, como, unidad in cifras_con_unidad(texto)
            if unidad and unidad not in SIN_UNIDAD and unidad not in respaldo.get(valor, set())]


def numeros_de_la_entrega(entrega: dict) -> dict[int, str]:
    """Todo número que la entrega trae, con su origen. Los únicos derivados son los del duplicado."""
    cab, items = entrega["cabecera"], entrega["items"]
    fecha, hora = cab["corrida"].split()
    anio, mes, dia = (int(x) for x in fecha.split("-"))
    out = {anio: "año de la corrida", dia: "día de la corrida", int(hora[:2]) % 12 or 12: "hora de la corrida (12 h)",
           int(cab["candidatos"]): "candidatos", int(cab["elegidos"]): "elegidos"}
    for it in items:
        for cifra, millones in re.findall(r"(\d[\d.]*)( millones)?", it["limpio"]):
            out[int(cifra.replace(".", "")) * (10 ** 6 if millones else 1)] = f"título de {it['hash']}"
    repetidos = len(items) - len(set(PARRAFO_DE.values()))
    out[len(items) - repetidos] = "noticias distintas (elegidos menos el duplicado)"
    out[repetidos + 1] = "veces que llegó la noticia duplicada"
    return out


def duracion_ogg(ruta: Path) -> float:
    """Segundos de un Ogg Opus leídos de sus páginas: (posición granular final − pre-skip) / 48000."""
    datos = ruta.read_bytes()
    cabeza = datos.index(b"OpusHead")
    preskip = struct.unpack_from("<H", datos, cabeza + 10)[0]
    ultima = datos.rindex(b"OggS")
    granulo = struct.unpack_from("<q", datos, ultima + 6)[0]
    return (granulo - preskip) / 48000


def cargar_script():
    spec = importlib.util.spec_from_file_location("boletin_audio_38", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    salida = sys.stdout                 # el script reconfigura stdout al importarse; se deja como estaba
    spec.loader.exec_module(mod)
    sys.stdout = salida
    return mod


class EntregaRealTests(unittest.TestCase):
    """Antes de usarla de vara, que la entrega se lea entera y tenga la forma que el guion supone."""

    def test_la_entrega_real_se_lee_completa(self):
        e = leer_entrega()
        self.assertEqual(e["cabecera"]["corrida"], "2026-10-09 1930")
        self.assertEqual(int(e["cabecera"]["elegidos"]), len(e["items"]))
        self.assertEqual(len(e["items"]), 8)
        self.assertEqual([it["hash"] for it in e["items"]], list(PARRAFO_DE))
        self.assertEqual({it["medio"] for it in e["items"]}, set(MEDIO_DICHO))

    def test_la_entrega_no_trae_resumen_ni_motivo(self):
        """Lo que obliga al guion a quedarse en el titular: cada ítem es título, etiquetas, medio y enlace."""
        lineas = [l for l in ENTREGA.read_text(encoding="utf-8").splitlines() if l.startswith("- [")]
        self.assertEqual(len(lineas), 8)
        for l in lineas:
            self.assertEqual(l.count(" · "), 4, l)
            self.assertNotRegex(norm(l), r"\b(resumen|motivo|por que te llega)\b")

    def test_el_titulo_limpio_bota_el_enlace_pegado_y_nada_mas(self):
        por_hash = {it["hash"]: it for it in leer_entrega()["items"]}
        self.assertTrue(por_hash["c46e9f6eb7cf86be"]["titulo"].endswith("4-200-millone"))
        self.assertEqual(por_hash["c46e9f6eb7cf86be"]["limpio"],
                         "$4.200 millones en droga decomisada y 3 detenidos en menos de 24 horas tras operativos en Ruta 5 Norte")
        self.assertNotIn("coquimbo", norm(por_hash["c46e9f6eb7cf86be"]["limpio"]))
        self.assertNotIn("metropolitana", norm(por_hash["68b4f7e280d2cd9f"]["limpio"]))
        self.assertNotIn("564", por_hash["d1cf4d59799534e9"]["limpio"])
        self.assertEqual(por_hash["a171d958b31ca4b5"]["limpio"], por_hash["a171d958b31ca4b5"]["titulo"])


class ContenidoTests(unittest.TestCase):
    """Hallazgo 2: el guion sólo usa la entrega (título y medio; la cabecera para el saludo)."""

    @classmethod
    def setUpClass(cls):
        cls.entrega = leer_entrega()
        cls.guion = leer_guion()
        cls.todo = " ".join(cls.guion)
        cls.vocab_titulos = set(palabras(" ".join(it["limpio"] for it in cls.entrega["items"])))
        cls.vocab_medios = set(palabras(" ".join(MEDIO_DICHO.values())))

    def test_cada_item_tiene_su_parrafo_en_el_orden_de_la_entrega(self):
        self.assertEqual(len(self.guion), 11)
        orden = [PARRAFO_DE[it["hash"]] for it in self.entrega["items"]]
        self.assertEqual(sorted(set(orden)), list(range(3, 10)))            # todo párrafo de noticia tiene ítem
        primeras = [orden.index(n) for n in sorted(set(orden))]
        self.assertEqual(primeras, sorted(primeras))                         # mismo orden que la entrega
        for it in self.entrega["items"]:
            parrafo = norm(self.guion[PARRAFO_DE[it["hash"]] - 1])
            clave = [p for p in palabras(it["limpio"]) if len(p) >= 5]
            dichas = [p for p in clave if p in parrafo]
            self.assertGreaterEqual(len(dichas) / len(clave), 0.7, (it["limpio"], set(clave) - set(dichas)))
            self.assertIn(norm(MEDIO_DICHO[it["medio"]]), parrafo, it["medio"])

    def test_todo_nombre_propio_del_guion_esta_en_la_entrega(self):
        """Lista cerrada: una palabra con mayúscula es de un título, de un medio o un inicio de frase corriente."""
        # «Ruta Cinco Norte»: el 5 del título, dicho en palabras; los números tienen su propia prueba.
        permitidas = self.vocab_titulos | self.vocab_medios | INICIOS | set(MESES) | set(NUMEROS)
        raras = sorted({p for p in re.findall(r"\b[A-ZÁÉÍÓÚÑ][\wáéíóúüñ]*", self.todo) if norm(p) not in permitidas})
        self.assertEqual(raras, [])
        # Y los inicios de frase son eso: ninguno aparece con mayúscula en medio de una frase.
        for parrafo in self.guion:
            for frase in re.split(r"[.?!:]\s+|¿", parrafo):
                for p in re.findall(r"\b[A-ZÁÉÍÓÚÑ][\wáéíóúüñ]*", " ".join(frase.split()[1:])):
                    self.assertIn(norm(p), self.vocab_titulos | self.vocab_medios | set(NUMEROS), (p, frase))

    def test_todo_numero_del_guion_esta_en_la_entrega(self):
        self.assertNotRegex(self.todo, r"[0-9$%]")
        permitidos = numeros_de_la_entrega(self.entrega)
        dichos = numeros_dichos(self.todo)
        self.assertGreaterEqual(len(dichos), 15)                             # el lector de números sí encuentra algo
        self.assertIn((4_200_000_000, "cuatro mil doscientos millones"), dichos)
        self.assertIn((733, "setecientos treinta y tres"), dichos)
        self.assertIn((2026, "dos mil veintiseis"), dichos)
        for valor, como in dichos:
            self.assertIn(valor, permitidos, f"«{como}» no sale de la entrega")
        cab = self.entrega["cabecera"]["corrida"]
        self.assertIn(MESES[int(cab[5:7]) - 1], norm(self.guion[0]))
        self.assertEqual(cab[-4:], "1930")
        self.assertIn("siete y media de la tarde", self.guion[0])

    def test_el_lector_de_numeros_lee_bien(self):
        self.assertEqual(numeros_dichos("en los últimos cinco años recibió ciento ocho millones, cinco mil "
                                        "cuatrocientos setenta y dos pesos y dos mil quinientos sesenta y cuatro millones"),
                         [(5, "cinco"), (108_000_000, "ciento ocho millones"),
                          (5472, "cinco mil cuatrocientos setenta y dos"),
                          (2_564_000_000, "dos mil quinientos sesenta y cuatro millones")])
        self.assertEqual(numeros_dichos("la ruta hache cuarenta y cinco ge, y tres detenidos"),
                         [(45, "cuarenta y cinco"), (3, "tres")])

    # --- revisión 2, hallazgo 2: la unidad de cada cifra también sale de la entrega ---

    def test_la_entrega_trae_el_signo_y_no_el_nombre_de_la_moneda(self):
        """Forma real, y la razón del hallazgo: `$4.200 millones` y `$108 millones`, sin decir de qué."""
        por_hash = {it["hash"]: it["limpio"] for it in self.entrega["items"]}
        self.assertTrue(por_hash["c46e9f6eb7cf86be"].startswith("$4.200 millones en droga"))
        self.assertIn("más de $108 millones para impulsar", por_hash["b5b0131d4c71b31b"])
        self.assertEqual([it["limpio"] for it in self.entrega["items"] if "$" in it["limpio"]],
                         [por_hash["c46e9f6eb7cf86be"], por_hash["b5b0131d4c71b31b"]])
        # Ni en los títulos ni en ninguna otra parte de las ocho líneas (enlace pegado, etiquetas, URL).
        lineas = [l for l in ENTREGA.read_text(encoding="utf-8").splitlines() if l.startswith("- [")]
        self.assertEqual(len(lineas), 8)
        self.assertEqual(sorted(set(re.findall(r"[a-zñ]+", norm(" ".join(lineas)))) & MONEDAS), [])
        self.assertEqual(sorted(self.vocab_titulos & MEDIDAS), ["horas"])

    def test_ninguna_moneda_ni_medida_que_no_este_en_los_titulos(self):
        dichas = set(palabras(self.todo))
        self.assertEqual(sorted(dichas & MONEDAS), [])
        self.assertEqual(sorted(dichas & MEDIDAS - self.vocab_titulos), [])
        self.assertNotRegex(norm(self.todo), r"\bpor ciento\b")
        self.assertIn("horas", dichas)                                       # la lista sí mira algo que está

    def test_la_unidad_de_cada_cifra_es_la_que_le_pone_la_entrega(self):
        respaldo = unidades_de_la_entrega(self.entrega)
        self.assertEqual(respaldo[4_200_000_000], {"en"})                    # la entrega no le pone moneda
        self.assertEqual(respaldo[108_000_000], {"para"})
        self.assertEqual((respaldo[3], respaldo[24], respaldo[12]), ({"detenidos"}, {"horas"}, {"proyectos"}))
        self.assertEqual((respaldo[8], respaldo[7], respaldo[2]), ({"elegidos", "titulares"}, {"noticias"}, {"veces"}))
        cifras = cifras_con_unidad(self.todo)
        self.assertEqual(len(cifras), len(numeros_dichos(self.todo)))
        con_unidad = [(como, u) for _, como, u in cifras if u and u not in SIN_UNIDAD]
        self.assertGreaterEqual(len(con_unidad), 12)                         # el lector sí encuentra unidades
        self.assertIn(("veinticuatro", "horas"), con_unidad)
        self.assertIn(("cuatro mil doscientos millones", "en"), con_unidad)
        self.assertIn(("ciento ocho millones", "para"), con_unidad)
        self.assertEqual(unidades_sin_respaldo(self.todo, self.entrega), [])
        # Las dos cifras con signo se dicen, y nunca seguidas de «de <algo>».
        for monto in ("cuatro mil doscientos millones", "ciento ocho millones"):
            self.assertGreaterEqual(norm(self.todo).count(monto), 2)
            self.assertNotRegex(norm(self.todo), monto + r" de\b")

    def test_el_lector_de_unidades_lee_bien(self):
        self.assertEqual(cifras_con_unidad("Cuatro mil doscientos millones de pesos en droga y tres detenidos, "
                                           "a las siete y media. Son doce."),
                         [(4_200_000_000, "cuatro mil doscientos millones", "pesos"), (3, "tres", "detenidos"),
                          (7, "siete", "y"), (12, "doce", None)])
        # La misma cifra con otra moneda, con otra medida o con la unidad de OTRA cifra: todo se detecta.
        for frase, mala in (("ciento ocho millones de pesos para impulsar", "pesos"),
                            ("ciento ocho millones de dólares para impulsar", "dolares"),
                            ("cuatro mil doscientos millones de dosis en droga", "dosis"),
                            ("tres proyectos", "proyectos"), ("doce detenidos", "detenidos"),
                            ("veinticuatro días", "dias")):
            self.assertEqual([u for _, u in unidades_sin_respaldo(frase, self.entrega)], [mala], frase)
        self.assertEqual(unidades_sin_respaldo("doce proyectos, tres detenidos en menos de veinticuatro horas y "
                                               "ciento ocho millones para impulsar", self.entrega), [])

    @unittest.skipUnless((HISTORIAL / "HEAD").is_file() and Path("/usr/bin/git").is_file(),
                         f"no está {HISTORIAL} (sólo existe en la Pi)")
    def test_las_pruebas_de_unidades_fallan_con_el_guion_que_reviso_codex(self):
        """Forma real del hallazgo: el guion de la foto que revisó la revisión 2 (sólo lectura, `git show`)
        hace saltar las dos pruebas nuevas, y por lo mismo que encontró Codex: párrafos 6, 7 y 10."""
        p = subprocess.run(["/usr/bin/git", "--git-dir", str(HISTORIAL), "show",
                            f"{FOTO_REVISADA_R2}:muestras/2026-10-09-1930/guion.txt"], capture_output=True)
        if p.returncode != 0:
            self.skipTest(f"el historial ya no tiene la foto {FOTO_REVISADA_R2}")
        viejo = [" ".join(b.split()) for b in p.stdout.decode("utf-8").split("\n\n") if b.strip()]
        self.assertEqual(len(viejo), 11)
        self.assertEqual([n for n, parrafo in enumerate(viejo, 1) if "pesos" in palabras(parrafo)], [6, 7, 10])
        self.assertEqual(set(palabras(" ".join(viejo))) & MONEDAS, {"pesos"})
        malas = unidades_sin_respaldo(" ".join(viejo), self.entrega)
        self.assertEqual(sorted(malas), [("ciento ocho millones", "pesos")] * 2
                         + [("cuatro mil doscientos millones", "pesos")] * 3)
        # Y la prueba que ya existía no lo veía: los valores de esas cifras sí están en la entrega.
        permitidos = numeros_de_la_entrega(self.entrega)
        self.assertEqual([c for v, c in numeros_dichos(" ".join(viejo)) if v not in permitidos], [])

    def test_sin_url_markdown_ni_emojis(self):
        for parrafo in self.guion:
            self.assertNotRegex(parrafo, r"(?i)https?://|www\.|\.cl\b|\.com\b|/")
            self.assertNotRegex(parrafo, r"[*_#`\[\]<>|\\]")
            self.assertEqual([c for c in parrafo if ord(c) > 0x2000 and c not in "…"], [])

    def test_nada_de_lo_que_la_revision_encontro_sigue_en_el_guion(self):
        """Los datos que la revisión 1 rastreó hasta el `desc` de la base o hasta el enlace."""
        vetados = ["seguridad naval", "trafico portuario", "subsecretaria", "fuerzas armadas", "cinco anos",
                   "turismo", "biodiversidad", "hache", "cuarenta y cinco", "peatones", "quebradas",
                   "programa de asistencia", "ministerio", "artesanal", "productores", "danstar", "stanley",
                   "buque", "inteligencia", "fines de ano", "epew", "kine", "dos semanas", "metropolitana",
                   "coquimbo", "dolares", "quinientos sesenta y cuatro"]
        texto = norm(self.todo)
        self.assertEqual([v for v in vetados if v in texto], [])

    @unittest.skipUnless(BASE.is_file(), f"no está {BASE} (sólo existe en la Pi)")
    def test_ninguna_palabra_que_solo_esta_en_la_base_llega_al_guion(self):
        """Forma real: se abre la base de sólo lectura y se leen los ocho ítems de la entrega por hash."""
        con = sqlite3.connect(f"file:{BASE}?mode=ro", uri=True)
        try:
            filas = con.execute(f"SELECT hash, titulo, desc, region FROM items WHERE hash IN "
                                f"({','.join('?' * len(PARRAFO_DE))})", list(PARRAFO_DE)).fetchall()
        finally:
            con.close()
        if len(filas) != len(PARRAFO_DE):
            self.skipTest(f"la base ya no tiene los 8 ítems de la entrega (quedan {len(filas)})")
        con_desc = [f for f in filas if f[2] and norm(f[2]) != norm(f[1])]
        self.assertGreaterEqual(len(con_desc), 5)                            # la base sí trae más que el título
        de_la_base = set(palabras(" ".join(f"{f[2] or ''} {f[3] or ''}" for f in filas)))
        self.assertTrue({"naval", "danstar", "stanley", "subsecretaria"} <= de_la_base)
        solo_base = {p for p in de_la_base - self.vocab_titulos - self.vocab_medios if len(p) >= 4}
        self.assertGreater(len(solo_base), 100)
        # Palabras del guion que también están en algún `desc`: sólo conectores y verbos corrientes, que
        # no llevan ningún dato de la noticia. Lista cerrada; cualquier otra coincidencia hace fallar.
        corrientes = set(SOLO_CORRIENTES.split())
        coincidencias = sorted(set(palabras(self.todo)) & solo_base)
        self.assertEqual([p for p in coincidencias if p not in corrientes], [])

    def test_ningun_nombre_de_la_cartera_que_no_este_en_el_titulo(self):
        """Cada palabra de un contrato, mandante o licitación de cartera-contratos.md que aparezca en un
        párrafo tiene que estar también en el título de la noticia de ese párrafo (decisión cerrada 2)."""
        texto = CARTERA.read_text(encoding="utf-8")
        celdas = []
        for linea in texto.splitlines():
            if linea.startswith("| GOP-"):
                celdas += [c.strip() for c in linea.strip("|").split("|")][1::2]     # Contrato y Mandante
        celdas += re.findall(r"^- .*$", texto.split("## Cruce con las licitaciones")[1], flags=re.M)
        articulos = {"el", "la", "lo", "los", "las", "de", "del", "y", "sin"}
        terminos = {norm(t) for t in re.findall(r"\b[A-ZÁÉÍÓÚÑ][\wáéíóúüñ-]*|\b\w*\d[\w-]*", " ".join(celdas))}
        terminos -= articulos | set(NUMEROS) | set(MULTIPLOS)        # los números tienen su propia prueba
        self.assertGreater(len(terminos), 90)
        self.assertTrue({"araucania", "ruta", "patache", "walmart", "futaleufu", "cruce", "camino", "mop"} <= terminos)
        items = self.entrega["items"]
        titulos_de = {n: norm(" ".join(it["limpio"] for it in items if PARRAFO_DE[it["hash"]] == n)) for n in range(3, 10)}
        todos = norm(" ".join(it["limpio"] for it in items))
        hallados = []
        for n, parrafo in enumerate(self.guion, 1):
            for p in sorted(set(re.findall(r"[\w-]+", norm(parrafo))) & terminos):
                hallados.append((n, p))
                self.assertIn(p, titulos_de.get(n, todos), f"«{p}» está en el párrafo {n} y no en su título")
        self.assertEqual(sorted({p for _, p in hallados}), ["araucania", "norte", "proyecto", "ruta"])


# Ver test_ninguna_palabra_que_solo_esta_en_la_base_llega_al_guion.
# - cinco: el 5 de «Ruta 5 Norte». rechazo, unanime, region: la misma palabra del título en otra forma
#   («Rechazado»/«rechaza», «unanimidad», «Regional»). El resto no nombra nada.
SOLO_CORRIENTES = """
    cinco rechazo unanime region
    cuenta desde este fueron noticias primero sobre
"""


class LargoTests(unittest.TestCase):
    """Hallazgo 3: 700 a 1.100 palabras y 5 a 8 minutos, medidos en los archivos reales."""

    def test_el_guion_tiene_entre_700_y_1100_palabras(self):
        n = len((MUESTRA / "guion.txt").read_text(encoding="utf-8").split())
        self.assertTrue(700 <= n <= 1100, n)

    def test_saludo_noticias_y_cierre_de_una_linea(self):
        guion = leer_guion()
        self.assertTrue(guion[0].startswith("Buenas tardes."))
        self.assertLessEqual(len(guion[-1].split()), 15)
        self.assertEqual(len(re.findall(r"[.?!]", guion[-1])), 2)

    def test_el_ogg_completo_dura_entre_5_y_8_minutos(self):
        ogg = MUESTRA / "boletin-daniela.ogg"
        d = duracion_ogg(ogg)
        self.assertTrue(300 <= d <= 480, d)
        # Y es el audio de ESTE guion: se sintetizó después de la última edición y el ritmo es de habla.
        self.assertGreaterEqual(ogg.stat().st_mtime, (MUESTRA / "guion.txt").stat().st_mtime)
        ritmo = len(" ".join(leer_guion()).split()) / d * 60
        self.assertTrue(150 <= ritmo <= 210, ritmo)

    @unittest.skipUnless(Path("/usr/bin/opusinfo").is_file(), "no está opusinfo")
    def test_la_duracion_leida_coincide_con_opusinfo(self):
        for ogg in sorted(MUESTRA.glob("*.ogg")):
            salida = subprocess.run(["/usr/bin/opusinfo", str(ogg)], capture_output=True, text=True).stdout
            m, s = re.search(r"Playback length: (\d+)m:([\d.]+)s", salida).groups()
            self.assertAlmostEqual(int(m) * 60 + float(s), duracion_ogg(ogg), delta=0.01, msg=ogg.name)

    def test_ningun_ogg_de_la_muestra_pasa_de_5_mb(self):
        oggs = sorted(MUESTRA.glob("*.ogg"))
        self.assertEqual([o.name for o in oggs], ["boletin-daniela.ogg", "fragmento-davefx.ogg", "fragmento-sharvard.ogg"])
        for o in oggs:
            self.assertLess(o.stat().st_size, 5 * 1024 * 1024, o.name)


class FragmentosTests(unittest.TestCase):
    """Hallazgo 4: fragmentos de comparación de «unos 40 s» (acá: entre 35 y 45), saludo + primera noticia."""

    def test_los_dos_fragmentos_duran_unos_40_segundos(self):
        for nombre in ("fragmento-davefx.ogg", "fragmento-sharvard.ogg"):
            ogg = MUESTRA / nombre
            d = duracion_ogg(ogg)
            self.assertTrue(35 <= d <= 45, (nombre, d))
            self.assertGreaterEqual(ogg.stat().st_mtime, (MUESTRA / "guion-fragmento.txt").stat().st_mtime)

    def test_el_fragmento_es_el_saludo_y_el_comienzo_de_la_primera_noticia(self):
        """El mismo texto del boletín, recortado: nada escrito sólo para la comparación."""
        guion, frag = leer_guion(), leer_guion("guion-fragmento.txt")
        self.assertEqual(len(frag), 2)
        self.assertEqual(frag[0], guion[0])
        self.assertTrue(frag[1].startswith("Primera noticia."))
        self.assertTrue(guion[2].startswith(frag[1] + " "))
        self.assertRegex(frag[1], r"[.?!]$")


@unittest.skipUnless(OPUSENC.is_file(), f"no está {OPUSENC} (sólo en la Pi)")
class TopeTests(unittest.TestCase):
    """Hallazgo 5: con opusenc de verdad, lo que no cabe en el tope no llega a la salida."""

    @classmethod
    def setUpClass(cls):
        cls.ba = cargar_script()

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name) / "tmp"
        self.destino = Path(self._t.name) / "vault"
        self.tmp.mkdir()
        self.destino.mkdir()
        # 20 s de ruido a 22.050 Hz mono de 16 bits, el formato que entrega Piper. El ruido no comprime:
        # el .ogg pesa lo que diga el bitrate.
        azar = random.Random(38)
        self.wav = self.tmp / "boletin.wav"
        with wave.open(str(self.wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(bytes(azar.getrandbits(8) for _ in range(22050 * 2 * 20)))

    def codificar(self, tope_mb, bitrate=32):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            try:
                return self.ba.codificar(self.wav, self.destino / "b.ogg", bitrate, tope_mb), salida.getvalue()
            except SystemExit as e:
                return e, salida.getvalue()

    def pesos(self):
        """Lo que pesa de verdad este WAV a cada peldaño de la escalera."""
        out = {}
        for b in self.ba.BITRATES:
            p = self.tmp / f"medida-{b}.ogg"
            subprocess.run(self.ba.orden_opusenc(self.wav, p, b), check=True, capture_output=True)
            out[b] = p.stat().st_size
            p.unlink()
        return out

    def test_si_cabe_se_escribe_al_bitrate_pedido(self):
        r, _ = self.codificar(5.0)
        self.assertEqual(r, 32)
        self.assertAlmostEqual(duracion_ogg(self.destino / "b.ogg"), 20.0, delta=0.05)

    def test_baja_peldanos_hasta_que_cabe(self):
        pesos = self.pesos()
        self.assertTrue(pesos[32] > pesos[24] > pesos[16] > pesos[12] > 20000, pesos)
        tope_mb = (pesos[16] + 500) / 1024 / 1024              # caben 16 y 12, no 32 ni 24
        r, dicho = self.codificar(tope_mb)
        self.assertEqual(r, 16)
        self.assertEqual(dicho.count("se baja el bitrate"), 2)
        self.assertLessEqual((self.destino / "b.ogg").stat().st_size, tope_mb * 1024 * 1024)

    def test_si_ni_el_ultimo_peldano_cabe_aborta_y_no_deja_archivo(self):
        """La reproducción de la revisión: antes devolvía 12 y dejaba el .ogg sobre el tope."""
        pesos = self.pesos()
        tope_mb = (pesos[12] - 500) / 1024 / 1024
        r, dicho = self.codificar(tope_mb)
        self.assertIsInstance(r, SystemExit)
        self.assertIn("no se escribió", str(r.code))
        self.assertIn("12 kbps", str(r.code))
        self.assertEqual(list(self.destino.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["boletin.wav"])
        self.assertEqual(len(re.findall(r"pesa más de", dicho)), 4)

    def test_una_salida_anterior_no_se_pisa_con_un_archivo_que_no_cabe(self):
        anterior = self.destino / "b.ogg"
        anterior.write_bytes(b"el de ayer")
        r, _ = self.codificar(0.001)
        self.assertIsInstance(r, SystemExit)
        self.assertEqual(anterior.read_bytes(), b"el de ayer")

    @unittest.skipUnless(PIPER.is_file(), f"no está {PIPER} (sólo en la Pi)")
    def test_el_script_completo_con_piper_no_deja_ogg_ni_temporales(self):
        """De punta a punta con el fragmento real y Piper: tope imposible → error, sin salida y sin WAV."""
        salida = self.destino / "muestra.ogg"
        antes = set(Path(tempfile.gettempdir()).glob("boletin-audio-*"))
        p = subprocess.run([sys.executable, str(SCRIPT), str(MUESTRA / "guion-fragmento.txt"), "--voz",
                            "es_ES-davefx-medium", "--salida", str(salida), "--parrafos", "1", "--max-mb", "0.001"],
                           capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("no se escribió", p.stderr)
        self.assertIn("bloque  1/1", p.stdout)                               # sí sintetizó: el corte fue por tamaño
        self.assertFalse(salida.exists())
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("boletin-audio-*")) - antes, set())


class ParrafosTests(unittest.TestCase):
    """Hallazgo 6 (bajo): `--parrafos -1` tomaba todos menos el último."""

    def correr(self, *extra):
        with tempfile.TemporaryDirectory() as t:
            return subprocess.run([sys.executable, str(SCRIPT), str(MUESTRA / "guion.txt"), "--voz", "es_AR-daniela-high",
                                   "--salida", str(Path(t) / "x.ogg"), "--dry-run", *extra], capture_output=True, text=True,
                                  env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def test_negativos_cero_y_texto_se_rechazan(self):
        for malo in ("-1", "0", "dos", "1.5"):
            p = self.correr("--parrafos", malo)
            self.assertEqual(p.returncode, 2, malo)
            self.assertIn("entero mayor que cero", p.stderr)
            self.assertNotIn("párrafos,", p.stdout)

    def test_positivos_toman_los_primeros_n(self):
        guion = leer_guion()
        p = self.correr("--parrafos", "2")
        self.assertIn(f"— 2 párrafos, {len(' '.join(guion[:2]).split())} palabras", p.stdout)
        self.assertIn(f"— 11 párrafos, {len(' '.join(guion).split())} palabras", self.correr().stdout)

    def test_dry_run_anuncia_el_corte_por_tamano_y_no_escribe(self):
        p = self.correr()
        self.assertIn("error y no se escribe la salida", p.stdout)


if __name__ == "__main__":
    unittest.main()
