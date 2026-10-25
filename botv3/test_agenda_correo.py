"""Pruebas de la ruta `google` (agenda_correo.py), sin red ni Groq ni puente."""
from collections import Counter
from datetime import date, datetime, time, timedelta
import importlib.util
import json
from pathlib import Path
import random
import unittest
import urllib.parse
from zoneinfo import ZoneInfo

import agenda_correo as ac

AHORA = datetime(2026, 9, 24, 21, 30, tzinfo=ac.TZ)  # jueves


def llm_fijo(respuesta):
    return lambda sistema, usuario: json.dumps(respuesta)


class InterpretarTests(unittest.TestCase):
    def test_evento_sin_titulo_manana_a_las_12_dura_una_hora(self):
        a = ac.interpretar("Crear un evento sin titulo mañana a las 12", llm_fijo(
            {"accion": "crear_evento", "titulo": "", "inicio": "2026-09-25T12:00"}), AHORA)
        self.assertEqual(a["accion"], "crear_evento")
        self.assertEqual(a["inicio"].hour, 12)
        self.assertEqual((a["fin"] - a["inicio"]).seconds, 3600)
        # La zona la pone Python, no el modelo: Chile en septiembre es -03.
        self.assertEqual(a["inicio"].utcoffset().total_seconds(), -3 * 3600)
        self.assertIn("«Sin título»", ac.texto_propuesta(a))
        self.assertIn("12:00–13:00", ac.texto_propuesta(a))

    def test_evento_sin_hora_pregunta_en_vez_de_inventar(self):
        a = ac.interpretar("agenda algo", llm_fijo({"accion": "crear_evento", "titulo": "x"}), AHORA)
        self.assertEqual(a["accion"], "preguntar")

    def test_fin_anterior_al_inicio_se_corrige(self):
        a = ac.interpretar("x", llm_fijo({"accion": "crear_evento", "inicio": "2026-09-25T12:00",
                                          "fin": "2026-09-25T11:00"}), AHORA)
        self.assertEqual(a["fin"].hour, 13)

    def test_todo_el_dia_termina_al_dia_siguiente(self):
        a = ac.interpretar("x", llm_fijo({"accion": "crear_evento", "inicio": "2026-09-25",
                                          "todo_el_dia": True}), AHORA)
        self.assertEqual(a["fin"].date().day, 26)
        self.assertEqual(ac.carga_puente(a)["fin"][:10], "2026-09-26")

    def test_borrador_no_adivina_la_direccion(self):
        a = ac.interpretar("x", llm_fijo({"accion": "crear_borrador", "para": "Camila",
                                          "asunto": "Hola", "cuerpo": "..."}), AHORA)
        self.assertEqual(a["para"], "")
        self.assertIn("No se envía", ac.texto_propuesta(a))

    def test_json_roto_y_accion_desconocida(self):
        self.assertEqual(ac.interpretar("x", lambda s, u: "no es json", AHORA)["accion"], "preguntar")
        self.assertEqual(ac.interpretar("x", llm_fijo({"accion": "enviar_correo"}), AHORA)["accion"], "otra")

    def test_agenda_sin_rango_son_siete_dias_desde_hoy(self):
        a = ac.interpretar("mi agenda", llm_fijo({"accion": "agenda"}), AHORA)
        self.assertEqual(a["desde"].day, 24)
        self.assertEqual((a["hasta"] - a["desde"]).days, 7)


class FormatoTests(unittest.TestCase):
    def test_agenda(self):
        a = ac.validar({"accion": "agenda", "desde": "2026-09-25T00:00", "hasta": "2026-09-26T00:00"}, AHORA)
        texto = ac.formatear_agenda(a, [
            {"titulo": "", "inicio": "2026-09-25T12:00:00-03:00", "fin": "2026-09-25T13:00:00-03:00"},
            {"titulo": "Feriado", "inicio": "2026-09-25", "fin": "2026-09-26"}])
        self.assertIn("vie 25-09 12:00–13:00  Sin título", texto)
        self.assertIn("(todo el día)  Feriado", texto)

    def test_correos(self):
        a = {"q": "is:unread"}
        texto = ac.formatear_correos(a, [{"de": '"Banco" <no@banco.cl>', "asunto": "Cartola",
                                          "extracto": "Su cartola", "no_leido": True}])
        self.assertIn("🔵 Banco — Cartola", texto)


MARTES = datetime(2026, 10, 20, 14, 30, tzinfo=ac.TZ)
# La forma de google_puente.agenda: dateTime con zona, o date para todo el día.
EVENTOS = [
    {"titulo": "En curso", "inicio": "2026-10-20T14:00:00-03:00", "fin": "2026-10-20T15:00:00-03:00", "lugar": ""},
    {"titulo": "Hoy todo el día", "inicio": "2026-10-20", "fin": "2026-10-21", "lugar": ""},
    {"titulo": "Dentista", "inicio": "2026-10-20T16:00:00-03:00", "fin": "2026-10-20T17:00:00-03:00",
     "lugar": "Providencia"},
    {"titulo": "Justo ahora", "inicio": "2026-10-20T14:30:00-03:00", "fin": "2026-10-20T15:00:00-03:00", "lugar": ""},
]


class ConsultasLocalesTests(unittest.TestCase):
    """Encargo 66: los botones de /google calculan el rango en Python, sin modelo."""

    def setUp(self):
        self.llamadas = []
        self.originales = (ac.puente, ac.interpretar)
        ac.puente = lambda op, datos: self.llamadas.append((op, datos)) or (
            {"ok": True, "eventos": EVENTOS} if op == "agenda" else {"ok": True, "correos": []})
        ac.interpretar = lambda *a, **k: self.fail("las consultas locales no usan modelo")

    def tearDown(self):
        ac.puente, ac.interpretar = self.originales

    def test_rangos(self):
        self.assertEqual(MARTES.weekday(), 1)
        iso = lambda r: tuple(d.isoformat() for d in r)
        self.assertEqual(iso(ac.rango_hoy(MARTES)), ("2026-10-20T14:30:00-03:00", "2026-10-21T00:00:00-03:00"))
        self.assertEqual(iso(ac.rango_manana(MARTES)), ("2026-10-21T00:00:00-03:00", "2026-10-22T00:00:00-03:00"))
        self.assertEqual(iso(ac.rango_semana(MARTES)), ("2026-10-20T14:30:00-03:00", "2026-10-27T14:30:00-03:00"))

    def test_manana_el_dia_del_cambio_de_hora(self):
        # 06-09-2026: Chile pasa de -04 a -03 a las 00:00 (esa hora no existe).
        desde, hasta = ac.rango_manana(datetime(2026, 9, 5, 21, 0, tzinfo=ac.TZ))
        self.assertEqual(desde.date().isoformat(), "2026-09-06")
        self.assertEqual(hasta.isoformat(), "2026-09-07T00:00:00-03:00")
        self.assertLess(desde, hasta)

    def test_proximo_es_el_primero_que_empieza_despues_de_ahora(self):
        self.assertEqual(ac.proximo_evento(EVENTOS, MARTES)["titulo"], "Dentista")
        self.assertIsNone(ac.proximo_evento(EVENTOS[:2] + EVENTOS[3:], MARTES))
        self.assertIsNone(ac.proximo_evento([{"titulo": "roto", "inicio": "x"}], MARTES))

    def test_consulta_local_pide_y_formatea(self):
        texto = ac.consulta_local("proximo", MARTES)
        self.assertEqual(texto, "📅 Próximo evento:\n• mar 20-10 16:00–17:00  Dentista · 📍 Providencia")
        self.assertEqual(self.llamadas, [("agenda", {"desde": "2026-10-20T14:30:00-03:00",
                                                    "hasta": "2026-10-27T14:30:00-03:00", "max": 20})])
        self.assertTrue(ac.consulta_local("hoy", MARTES).startswith("📅 Hoy, mar 20-10:\n• mar 20-10 14:00–15:00  En curso"))
        self.assertEqual(ac.consulta_local("noleidos", MARTES), "📬 No encontré correos (is:unread newer_than:2d).")
        self.assertEqual(self.llamadas[-1], ("buscar_correo", {"q": "is:unread newer_than:2d", "max": 10}))
        with self.assertRaises(ValueError):
            ac.consulta_local("evento", MARTES)

    def test_sin_titulo_el_formato_de_siempre(self):
        a = {"desde": MARTES, "hasta": MARTES + timedelta(days=1)}
        self.assertEqual(ac.formatear_agenda(a, []), "📅 Sin eventos entre mar 20-10 → mié 21-10.")
        self.assertEqual(ac.formatear_agenda(a, [], "Hoy, mar 20-10"), "📅 Hoy, mar 20-10: sin eventos.")


# Encargo 68: tres eventos con lugar el miércoles 21, como los devuelve el puente.
MIERCOLES = [
    {"titulo": "Reunión con Pedro", "inicio": "2026-10-21T10:00:00-03:00", "fin": "2026-10-21T11:00:00-03:00",
     "lugar": "Oficina Apoquindo"},
    {"titulo": "Almuerzo familiar", "inicio": "2026-10-21T13:30:00-03:00", "fin": "2026-10-21T15:00:00-03:00",
     "lugar": "Casa de la abuela"},
    {"titulo": "Dentista", "inicio": "2026-10-21T18:00:00-03:00", "fin": "2026-10-21T19:00:00-03:00",
     "lugar": "Providencia"},
]
CORREOS = [{"de": '"Juan Pérez" <juan@x.cl>', "asunto": "Presupuesto secreto", "fecha": "Tue, 20 Oct 2026 09:00:00 -0300",
            "extracto": "Te mando el presupuesto", "no_leido": True},
           {"de": "Banco <no@banco.cl>", "asunto": "Cartola", "fecha": "Tue, 20 Oct 2026 08:00:00 -0300",
            "extracto": "Su cartola", "no_leido": True}]


class IntencionAgendaTests(unittest.TestCase):
    """68: las frases frecuentes, como las escribe Whisper, con el martes 14:30 congelado."""

    def rango(self, frase):
        i = ac.intencion_agenda(frase, MARTES)
        self.assertIsNotNone(i, frase)
        return i["accion"], i["desde"].isoformat(), i["hasta"].isoformat()

    def test_c1(self):
        manana = ("agenda", "2026-10-21T00:00:00-03:00", "2026-10-22T00:00:00-03:00")
        self.assertEqual(self.rango("¿Jaime, qué tengo mañana?"), manana)
        self.assertEqual(self.rango("qué tengo el viernes"),
                         ("agenda", "2026-10-23T00:00:00-03:00", "2026-10-24T00:00:00-03:00"))
        self.assertEqual(ac.intencion_agenda("cuál es mi próxima reunión", MARTES)["accion"], "proximo")
        i = ac.intencion_agenda("a qué hora es la reunión con Pedro", MARTES)
        self.assertEqual((i["accion"], i["filtro"]), ("agenda", "pedro"))
        self.assertEqual((i["desde"], i["hasta"] - i["desde"]), (MARTES, timedelta(days=14)))

    def test_formas_de_whisper(self):
        hoy = ("agenda", "2026-10-20T14:30:00-03:00", "2026-10-21T00:00:00-03:00")
        manana = ("agenda", "2026-10-21T00:00:00-03:00", "2026-10-22T00:00:00-03:00")
        semana = ("agenda", "2026-10-20T14:30:00-03:00", "2026-10-27T14:30:00-03:00")
        casos = {
            "Jaime, ¿qué tengo hoy?": hoy, "que tengo hoy": hoy, "Qué tengo hoy.": hoy, "mi agenda de hoy": hoy,
            "Hola Jaime, ¿qué tengo para hoy?": hoy, "¿qué tengo el martes?": hoy,
            "Jaime qué tengo mañana": manana, "¿Tengo algo mañana?": manana, "tengo algo para mañana": manana,
            "que hay en mi agenda mañana": manana, "¿Qué tengo mañana, Jaime?": manana,
            "agenda para mañana": manana, "dime qué tengo mañana": manana,
            "qué tengo pasado mañana": ("agenda", "2026-10-22T00:00:00-03:00", "2026-10-23T00:00:00-03:00"),
            "qué tengo esta semana": semana, "¿Qué tengo en la semana?": semana,
            "Que tengo el miercoles": manana,
            "qué tengo el próximo martes": ("agenda", "2026-10-27T00:00:00-03:00", "2026-10-28T00:00:00-03:00"),
            "¿qué tengo el domingo?": ("agenda", "2026-10-25T00:00:00-03:00", "2026-10-26T00:00:00-03:00"),
        }
        for frase, esperado in casos.items():
            self.assertEqual(self.rango(frase), esperado, frase)
        for frase in ("¿Cuál es mi próxima reunión?", "Jaime, qué viene ahora", "a qué hora es mi próxima",
                      "A que hora es mi proxima reunion", "¿Qué tengo después?", "mi próxima cita"):
            self.assertEqual(ac.intencion_agenda(frase, MARTES)["accion"], "proximo", frase)
        for frase, filtro in (("cuándo es el dentista", "dentista"), ("¿Cuándo es el Dentista?", "dentista"),
                              ("Jaime, ¿a qué hora es la reunión con Pedro?", "pedro"),
                              ("a qué hora tengo la cita con la Dra. Muñoz", "dra munoz")):
            self.assertEqual(ac.intencion_agenda(frase, MARTES)["filtro"], filtro, frase)

    def test_correo(self):
        for frase in ("¿Tengo correos nuevos?", "Jaime, tengo correos", "hay algún correo nuevo",
                      "¿Me llegó algún correo?", "correos sin leer", "me escribió alguien"):
            i = ac.intencion_agenda(frase, MARTES)
            self.assertEqual((i["accion"], i["q"]), ("buscar_correo", "is:unread newer_than:2d"), frase)
        for frase, q in (("me escribió Juan", "from:Juan newer_than:7d"),
                         ("¿Jaime, me escribió la Cami?", "from:Cami newer_than:7d"),
                         ("algún correo de Juan Pérez", 'from:"Juan Pérez" newer_than:7d'),
                         ("tengo correos del banco", "from:banco newer_than:7d"),
                         ("me llegó algún correo de juan.perez@x.cl?", "from:juan.perez@x.cl newer_than:7d")):
            self.assertEqual(ac.intencion_agenda(frase, MARTES)["q"], q, frase)

    def test_c2_siguen_como_hoy(self):
        for frase in ("qué tengo que comprar", "tengo algo en la lista", "qué hora es",
                      "temporizador mañana a las 7", "avísame mañana a las 7",
                      "¿Jaime, qué tengo que comprar?", "qué tengo que hacer mañana", "agenda dentista el jueves a las 4",
                      "tengo que ir mañana", "qué hay de nuevo", "mañana", "la agenda está llena",
                      "cuándo es navidad", "qué tengo", "anota leche"):
            self.assertIsNone(ac.intencion_agenda(frase, MARTES), frase)

    def test_c7_remitente_hostil(self):
        for frase in ("me escribió x OR from:*", "me escribió juan OR subject:clave", "algún correo de -in:spam juan",
                      'me escribió "juan" AND is:starred', "me escribió (juan) {x}"):
            i = ac.intencion_agenda(frase, MARTES)
            self.assertEqual(i["accion"], "buscar_correo", frase)
            x = i["q"].removeprefix("from:").removesuffix(" newer_than:7d").strip('"')
            self.assertNotIn(":", x, frase)
            self.assertNotIn("OR", x.split(), frase)
            self.assertNotIn("AND", x.split(), frase)
            self.assertFalse(any(p.startswith("-") for p in x.split()), frase)
            self.assertTrue(all(c.isalnum() or c in " .@-" for c in x), frase)
        self.assertIsNone(ac.intencion_agenda("me escribió :*()", MARTES))

    def test_crear(self):
        for frase in ("agenda dentista el jueves a las 4", "Jaime, agenda dentista el jueves a las 4.",
                      "agéndame el dentista el jueves", "anota en mi calendario el dentista el jueves a las 4",
                      "crea una reunión con Pedro mañana a las 10", "pon en el calendario la junta del lunes"):
            self.assertTrue(ac.pide_crear_evento(frase), frase)
            self.assertIsNone(ac.intencion_agenda(frase, MARTES), frase)
        for frase in ("mi agenda de hoy", "agenda de hoy", "anota leche", "anota leche a la lista",
                      "qué tengo mañana", "crea un evento", "agenda"):
            self.assertFalse(ac.pide_crear_evento(frase), frase)


class FrasesHabladasTests(unittest.TestCase):
    """68: lo que se dice por voz. Nunca el lugar, los otros eventos ni el asunto."""

    def setUp(self):
        self.llamadas, self.eventos, self.correos = [], list(MIERCOLES), list(CORREOS)
        self.originales = (ac.puente, ac.interpretar)
        ac.puente = lambda op, datos: self.llamadas.append((op, datos)) or (
            {"ok": True, "eventos": self.eventos} if op == "agenda" else {"ok": True, "correos": self.correos})
        ac.interpretar = lambda *a, **k: self.fail("las frases locales no usan modelo")

    def tearDown(self):
        ac.puente, ac.interpretar = self.originales

    def responder(self, frase):
        return ac.consulta_intencion(ac.intencion_agenda(frase, MARTES), MARTES)

    def test_agenda_de_un_dia(self):
        texto, dicho = self.responder("qué tengo mañana")
        self.assertEqual(dicho, "Mañana tienes 3. El primero, a las 10, Reunión con Pedro.")
        self.assertEqual(self.llamadas, [("agenda", {"desde": "2026-10-21T00:00:00-03:00",
                                                    "hasta": "2026-10-22T00:00:00-03:00", "max": 15})])
        self.assertTrue(texto.startswith("📅 Mañana, mié 21-10:\n"))
        for e in MIERCOLES:
            self.assertIn(e["titulo"], texto)
            self.assertIn(e["lugar"], texto)
            self.assertNotIn(e["lugar"], dicho)
        self.assertEqual(self.responder("qué tengo el viernes")[1], "El viernes tienes 3. El primero, a las 10, Reunión con Pedro.")
        self.eventos = MIERCOLES[2:]
        self.assertEqual(self.responder("qué tengo mañana")[1], "Mañana tienes uno, a las 18, Dentista.")
        self.eventos = []
        self.assertEqual(self.responder("qué tengo mañana"), ("📅 Mañana, mié 21-10: sin eventos.", "Mañana no tienes nada."))
        self.assertEqual(self.responder("qué tengo hoy")[1], "Hoy no tienes nada.")

    def test_semana_proximo_y_filtro_dicen_el_dia(self):
        self.assertEqual(self.responder("qué tengo esta semana")[1],
                         "Esta semana tienes 3. El primero, mañana a las 10, Reunión con Pedro.")
        self.assertEqual(self.responder("cuál es mi próxima reunión")[1], "Tu próxima es mañana a las 10, Reunión con Pedro.")
        self.eventos = [{"titulo": "Café", "inicio": "2026-10-20T16:00:00-03:00", "fin": "2026-10-20T17:00:00-03:00", "lugar": "x"}]
        self.assertEqual(self.responder("qué viene ahora")[1], "Tu próxima es hoy a las 16, Café.")
        self.eventos = []
        self.assertEqual(self.responder("qué viene ahora")[1], "No tienes nada en los próximos 7 días.")
        self.eventos = list(MIERCOLES) + [{"titulo": "Control dentista", "inicio": "2026-10-29T13:15:00-03:00",
                                           "fin": "2026-10-29T14:00:00-03:00", "lugar": "Las Condes"}]
        texto, dicho = self.responder("¿Cuándo es el DENTISTA?")
        self.assertEqual(dicho, "Es mañana a las 18, Dentista.")
        self.assertEqual(self.llamadas[-1][1]["max"], 20)
        self.assertIn("Control dentista", texto)
        self.assertNotIn("Pedro", texto)
        self.eventos = [{"titulo": "Cita Dra. Muñoz (control)", "inicio": "2026-10-23T09:00:00-03:00",
                         "fin": "2026-10-23T10:00:00-03:00", "lugar": ""}]
        self.assertEqual(self.responder("a qué hora tengo la cita con la Dra. Muñoz")[1],
                         "Es el viernes 23 a las 9, Cita Dra. Muñoz (control).")
        self.assertEqual(self.responder("a qué hora es la reunión con Andrés")[1],
                         "No encontré andres en los próximos 14 días.")

    def test_hora_dicha_y_todo_el_dia(self):
        self.eventos = [{"titulo": "Feriado", "inicio": "2026-10-21", "fin": "2026-10-22", "lugar": ""},
                        {"titulo": "Siesta", "inicio": "2026-10-21T13:00:00-03:00", "fin": "2026-10-21T14:00:00-03:00"}]
        self.assertEqual(self.responder("qué tengo mañana")[1], "Mañana tienes 2. El primero, todo el día, Feriado.")
        self.eventos = [{"titulo": "Algo", "inicio": "2026-10-21T01:00:00-03:00", "fin": "2026-10-21T02:00:00-03:00"},
                        {"titulo": "Otro", "inicio": "2026-10-21T09:45:00-03:00", "fin": "2026-10-21T10:00:00-03:00"}]
        self.assertEqual(self.responder("qué tengo mañana")[1], "Mañana tienes 2. El primero, a la 1, Algo.")
        self.eventos = self.eventos[1:]
        self.assertEqual(self.responder("qué tengo mañana")[1], "Mañana tienes uno, a las 9:45, Otro.")

    def test_titulo_largo_se_corta(self):
        largo = "Reunión de coordinación del proyecto con todo el equipo de ingeniería y los contratistas"
        self.eventos = [{"titulo": largo + "\n con salto", "inicio": "2026-10-21T10:00:00-03:00",
                         "fin": "2026-10-21T11:00:00-03:00", "lugar": "Sala 3"}]
        dicho = self.responder("qué tengo mañana")[1]
        self.assertEqual(dicho, f"Mañana tienes uno, a las 10, {largo[:60].rstrip()}.")
        self.assertNotIn("\n", dicho)

    def test_correo_sin_asunto_ni_remitente_completo(self):
        texto, dicho = self.responder("tengo correos nuevos")
        self.assertEqual(dicho, "Tienes 2 correos sin leer.")
        self.assertEqual(self.llamadas[-1], ("buscar_correo", {"q": "is:unread newer_than:2d", "max": 10}))
        self.assertIn("Presupuesto secreto", texto)
        for prohibido in ("Presupuesto", "Pérez", "juan@x.cl", "Banco", "Cartola"):
            self.assertNotIn(prohibido, dicho)
        self.assertEqual(self.responder("me escribió juan")[1], "Tienes 2 de Juan.")
        self.assertEqual(self.llamadas[-1][1]["q"], "from:juan newer_than:7d")
        self.correos = CORREOS[:1]
        self.assertEqual(self.responder("hay correos sin leer")[1], "Tienes 1 correo sin leer.")
        self.correos = CORREOS * 5
        self.assertEqual(self.responder("hay correos sin leer")[1], "Tienes 10 o más correos sin leer.")
        self.correos = []
        self.assertEqual(self.responder("hay correos sin leer")[1], "No tienes correos sin leer.")
        self.assertEqual(self.responder("me escribió juan@x.cl")[1], "No tienes correos de juan@x.cl.")


# --- 68r1: el tope real del puente ---------------------------------------------
#
# El `agenda` de pi/google_puente.py, tal cual, con su `_api` cambiado por un Calendar
# falso que filtra como `events.list` de Google: `timeMin` acota el FIN (exclusivo),
# `timeMax` el INICIO (exclusivo), `orderBy=startTime` y `maxResults` corta. Así el
# tope de 20 (MAX_RESULTADOS) y la normalización a `titulo/inicio/fin/lugar` son los
# del puente que corre en la Pi, y los eventos en curso llegan primero, como en la vida real.

_SCL = ZoneInfo("America/Santiago")


def cargar_google_puente():
    ruta = Path(__file__).resolve().parent.parent / "pi" / "google_puente.py"
    spec = importlib.util.spec_from_file_location("google_puente_68r1", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def item_calendar(titulo, inicio, fin, lugar=""):
    """Un item de `events.list`: `date` si es de todo el día, `dateTime` con zona si no."""
    lado = lambda v: {"date": v} if len(v) == 10 else {"dateTime": datetime.fromisoformat(v).replace(tzinfo=_SCL).isoformat()}
    item = {"summary": titulo, "start": lado(inicio), "end": lado(fin)}
    if lugar:
        item["location"] = lugar
    return item


class CalendarFalso:
    def __init__(self, items):
        self.items, self.pedidos = list(items), []
        self.gp = cargar_google_puente()
        self.gp._api = self._api

    @staticmethod
    def _t(lado):
        if "dateTime" in lado:
            return datetime.fromisoformat(lado["dateTime"])
        return datetime.combine(date.fromisoformat(lado["date"]), time(0), _SCL)

    def _api(self, metodo, url, cuerpo=None, cuenta="personal"):
        assert metodo == "GET" and "/events?" in url, url
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
        self.pedidos.append(q)
        t_min, t_max = datetime.fromisoformat(q["timeMin"]), datetime.fromisoformat(q["timeMax"])
        assert q["singleEvents"] == "true" and q["orderBy"] == "startTime"
        dentro = [it for it in self.items if self._t(it["end"]) > t_min and self._t(it["start"]) < t_max]
        dentro.sort(key=lambda it: self._t(it["start"]))
        return {"items": dentro[:int(q["maxResults"])]}

    def puente(self, operacion, datos, **_k):
        """Lo que hace el bot con el socket: JSON de ida, `{"ok": True, **agenda(p)}` de vuelta."""
        assert operacion == "agenda", operacion
        p = json.loads(json.dumps(datos, default=str))
        return json.loads(json.dumps({"ok": True, **self.gp.agenda(p)}))

    def todos(self, desde, hasta):
        """Lo que hay en Calendar en [desde, hasta), en la forma del puente, sin tope."""
        dentro = [it for it in self.items if self._t(it["end"]) > desde and self._t(it["start"]) < hasta]
        dentro.sort(key=lambda it: self._t(it["start"]))
        return [{"titulo": it.get("summary", ""), "inicio": it["start"].get("dateTime") or it["start"].get("date"),
                 "fin": it["end"].get("dateTime") or it["end"].get("date"), "lugar": it.get("location", "")}
                for it in dentro]


class TopeDelPuenteTests(unittest.TestCase):
    """68r1, hallazgo 1: el tope del puente no puede convertirse en un «no hay» falso."""

    def setUp(self):
        self.originales = (ac.puente, ac.interpretar)
        ac.interpretar = lambda *a, **k: self.fail("las frases locales no usan modelo")

    def tearDown(self):
        ac.puente, ac.interpretar = self.originales

    def calendario(self, items):
        self.cal = CalendarFalso(items)
        ac.puente = self.cal.puente
        return self.cal

    def responder(self, frase):
        return ac.consulta_intencion(ac.intencion_agenda(frase, MARTES), MARTES)

    @staticmethod
    def en_curso(n, fin="2026-10-20T17:00"):
        return [item_calendar(f"En curso {k}", "2026-10-20T14:00", fin) for k in range(n)]

    def test_reproduccion_proximo_con_15_en_curso(self):
        # La de 68r1 (y la de 66r1): 15 empezados a las 14:00 hasta las 17:00, y Dentista a las 16:00.
        self.calendario(self.en_curso(15) + [item_calendar("Dentista", "2026-10-20T16:00", "2026-10-20T17:00", "Providencia")])
        texto, dicho = self.responder("cuál es mi próxima reunión")
        self.assertEqual(dicho, "Tu próxima es hoy a las 16, Dentista.")
        self.assertEqual(texto, "📅 Próximo evento:\n• mar 20-10 16:00–17:00  Dentista · 📍 Providencia")
        self.assertEqual(ac.consulta_local("proximo", MARTES), texto)
        self.assertEqual([q["maxResults"] for q in self.cal.pedidos], ["20", "20"])

    def test_proximo_tapado_no_dice_que_no_hay(self):
        # 20 o más que ya empezaron: Calendar no deja ver detrás. No es «no tienes nada».
        for n in (20, 25):
            with self.subTest(en_curso=n):
                self.calendario(self.en_curso(n) + [item_calendar("Dentista", "2026-10-20T16:00", "2026-10-20T17:00")])
                texto, dicho = self.responder("qué viene ahora")
                self.assertEqual(dicho, "Tienes 20 o más eventos en curso y no alcanzo a ver el próximo.")
                self.assertEqual(texto, f"📅 {dicho}")
                self.assertNotIn("No tienes nada", dicho)
                self.assertEqual(ac.consulta_local("proximo", MARTES), texto)
        # Con 19 todavía entra en una página: el puente devuelve 20 y el último es Dentista.
        self.calendario(self.en_curso(19) + [item_calendar("Dentista", "2026-10-20T16:00", "2026-10-20T17:00")])
        self.assertEqual(self.responder("qué viene ahora")[1], "Tu próxima es hoy a las 16, Dentista.")
        # Y sin nada, sigue siendo «no tienes nada» (una página corta es la ventana entera).
        self.calendario(self.en_curso(3))
        self.assertEqual(self.responder("qué viene ahora")[1], "No tienes nada en los próximos 7 días.")

    def test_reproduccion_filtro_con_pedro_el_21(self):
        # La de 68r1: 20 que no calzan dentro de los 14 días, y «Reunión con Pedro» es el 21.º.
        items = [item_calendar(f"Pega {k}", f"2026-10-{21 + k // 2}T{9 + 4 * (k % 2):02d}:00",
                               f"2026-10-{21 + k // 2}T{10 + 4 * (k % 2):02d}:00") for k in range(20)]
        items.append(item_calendar("Reunión con Pedro", "2026-11-01T11:00", "2026-11-01T12:00", "Oficina"))
        self.calendario(items)
        texto, dicho = self.responder("a qué hora es la reunión con Pedro")
        self.assertEqual(dicho, "Es el domingo 1 a las 11, Reunión con Pedro.")
        self.assertIn("Reunión con Pedro · 📍 Oficina", texto)
        self.assertNotIn("Pega", texto)
        self.assertNotIn("⚠️", texto)
        self.assertEqual([(q["timeMin"], q["maxResults"]) for q in self.cal.pedidos],
                         [("2026-10-20T14:30:00-03:00", "20"), ("2026-10-30T13:00:00-03:00", "20")])
        # Si de verdad no está, se dice después de ver la ventana entera.
        self.calendario(items[:-1])
        self.assertEqual(self.responder("a qué hora es la reunión con Pedro")[1],
                         "No encontré pedro en los próximos 14 días.")
        self.assertEqual(len(self.cal.pedidos), 2)

    def test_filtro_tapado_no_dice_que_no_hay(self):
        # 20 de varios días que van en curso tapan a Pedro: se dice que no se vio todo.
        items = self.en_curso(20, fin="2026-11-05") + [item_calendar("Reunión con Pedro", "2026-10-22T11:00", "2026-10-22T12:00")]
        self.calendario(items)
        texto, dicho = self.responder("a qué hora es la reunión con Pedro")
        self.assertEqual(dicho, "No encontré pedro en lo que alcancé a revisar. Te dejo el detalle en el chat.")
        self.assertIn("⚠️ Sólo alcancé a revisar hasta el mar 20-10 14:30: después puede haber más.", texto)
        self.assertNotIn("14 días.", dicho)

    def test_filtro_con_mas_de_cinco_paginas(self):
        # 120 eventos cortos en 14 días: se ven 5 páginas y se avisa hasta dónde.
        items = [item_calendar(f"Pega {k}", (datetime(2026, 10, 20, 15) + timedelta(hours=2 * k)).strftime("%Y-%m-%dT%H:%M"),
                               (datetime(2026, 10, 20, 16) + timedelta(hours=2 * k)).strftime("%Y-%m-%dT%H:%M")) for k in range(120)]
        items.append(item_calendar("Dentista", "2026-11-02T10:00", "2026-11-02T11:00"))
        self.calendario(items)
        texto, dicho = self.responder("cuándo es el dentista")
        self.assertEqual(dicho, "No encontré dentista en lo que alcancé a revisar. Te dejo el detalle en el chat.")
        self.assertEqual(len(self.cal.pedidos), ac.PAGINAS)
        self.assertIn("⚠️ Sólo alcancé a revisar hasta el", texto)

    def test_recorrido_entrega_cada_evento_una_vez(self):
        # 55 eventos al azar (con semilla): largos que cruzan páginas, de todo el día, empates
        # a la misma hora y repetidos idénticos (Calendar puede tener dos iguales). Caben en
        # PAGINAS: el caso de no alcanzar es test_filtro_con_mas_de_cinco_paginas.
        azar = random.Random(681)
        items = []
        for k in range(55):
            if k % 9 == 0:
                d = date(2026, 10, 20) + timedelta(days=azar.randrange(14))
                items.append(item_calendar(f"Día {k}", d.isoformat(), (d + timedelta(days=azar.choice((1, 2)))).isoformat()))
                continue
            ini = datetime(2026, 10, 20, 12) + timedelta(minutes=30 * azar.randrange(14 * 48))
            fin = ini + timedelta(minutes=30 * azar.randrange(1, 20))
            items.append(item_calendar(f"Ev {k}", ini.strftime("%Y-%m-%dT%H:%M"), fin.strftime("%Y-%m-%dT%H:%M"), "x"))
        items += [items[3], items[3], item_calendar("Empate", "2026-10-25T10:00", "2026-10-25T11:00")]
        items += [item_calendar(f"Empate {k}", "2026-10-25T10:00", "2026-10-25T10:30") for k in range(4)]
        # Dos idénticos que van en curso en todas las páginas: cada uno se descuenta una vez.
        items += [item_calendar("Viaje", "2026-10-20", "2026-11-04", "Arica")] * 2
        cal = self.calendario(items)
        desde, hasta = MARTES, MARTES + timedelta(days=14)
        eventos, visto = ac.eventos_recorridos(desde, hasta)
        self.assertIsNone(visto)
        self.assertGreater(len(cal.pedidos), 2, "tiene que haber pedido varias páginas")
        esperado = cal.todos(desde, hasta)
        self.assertGreater(len(esperado), 55)
        self.assertEqual(Counter(map(ac._clave, eventos)), Counter(map(ac._clave, esperado)))
        inicios = [ac._inicio_evento(e) for e in eventos]
        self.assertEqual(inicios, sorted(inicios))


class PuenteTests(unittest.TestCase):
    def test_sin_socket_es_no_disponible(self):
        with self.assertRaises(ac.GoogleNoDisponible):
            ac.puente("agenda", {}, ruta="/no/existe.sock", timeout=1)


if __name__ == "__main__":
    unittest.main()
