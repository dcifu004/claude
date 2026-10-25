"""Pruebas de clima_imagen.py (encargo 74).

Las 19 del prototipo (`propuestas/clima-pronostico/test_eventos.py` y
`test_render_png.py`) corren acá contra el módulo real, con la respuesta real de
Open-Meteo del 21-10-2026 (`fixtures/open-meteo-las-condes-2026-10-21.json`) y
"ahora" = miércoles 21-10-2026 07:30 en Santiago. Después, las de esta etapa:
validación de la respuesta, entradas hostiles, letra de reemplazo y herramienta.

Sin red y sin escribir fuera de un temporal. Las que dibujan se saltan sin Pillow
(lo dicen); las que prueban la caída sin Pillow corren siempre.
"""

import contextlib
from copy import deepcopy
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import clima_imagen as ci  # noqa: E402
from clima_imagen import (  # noqa: E402
    caja_ahora, cajas_hitos, cajas_tarjeta, conclusion, datos_tarjetas, eventos, geometria_ahora,
    hitos_dibujados, periodos_lluvia, pie, resumen_lluvia_dia, tarjeta_png, titulo_fecha,
)

try:
    from PIL import Image, ImageDraw
    HAY_PIL = True
except ImportError:
    HAY_PIL = False
SIN_PIL = "sin Pillow: esta prueba dibuja y se salta (en la Pi, apt install python3-pil)"

FIXTURE = AQUI / "fixtures" / "open-meteo-las-condes-2026-10-21.json"
AHORA = datetime(2026, 10, 21, 7, 30)


def cargar_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def sin_lluvia(datos):
    """Sintético derivado del fixture real: lluvia y probabilidad en 0, el resto igual."""
    datos = deepcopy(datos)
    datos["minutely_15"]["precipitation"] = [0] * len(datos["minutely_15"]["precipitation"])
    datos["hourly"]["precipitation"] = [0] * len(datos["hourly"]["precipitation"])
    datos["hourly"]["precipitation_probability"] = [0] * len(datos["hourly"]["precipitation_probability"])
    datos["daily"]["precipitation_sum"] = [0] * len(datos["daily"]["precipitation_sum"])
    return datos


# ── Las 6 de test_eventos.py ──

def datos_base(precipitacion=None, rachas=None, uv=None, temperaturas=None):
    inicio = datetime(2026, 10, 21)
    horas = [(inicio + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(72)]
    cuartos = [(inicio + timedelta(minutes=15 * i)).isoformat(timespec="minutes") for i in range(288)]
    return {
        "minutely_15": {
            "time": cuartos,
            "precipitation": precipitacion or [0.0] * 288,
        },
        "hourly": {
            "time": horas,
            "temperature_2m": temperaturas or [12.0] * 72,
            "precipitation": [0.0] * 72,
            "wind_gusts_10m": rachas or [10.0] * 72,
            "uv_index": uv or [0.0] * 72,
        },
    }


class EventosTest(unittest.TestCase):
    def setUp(self):
        self.ahora = AHORA

    def test_lluvia_exige_dos_intervalos_y_tolera_corte_de_quince_minutos(self):
        lluvia = [0.0] * 288
        lluvia[40:43] = [0.3, 0.3, 0.3]  # 10:00–10:45
        lluvia[44:47] = [0.3, 0.3, 0.3]  # corte único a las 10:45
        resultado = eventos(datos_base(precipitacion=lluvia), self.ahora)
        inicios = [e for e in resultado if e["tipo"] == "lluvia_inicio"]
        finales = [e for e in resultado if e["tipo"] == "lluvia_fin"]
        self.assertEqual([e["cuando"] for e in inicios], [datetime(2026, 10, 21, 10, 0)])
        self.assertEqual([e["cuando"] for e in finales], [datetime(2026, 10, 21, 11, 45)])

    def test_detecta_racha_uv_y_cambio_brusco(self):
        rachas = [10.0] * 72
        uv = [0.0] * 72
        temperaturas = [10.0] * 72
        rachas[9:12] = [41.0, 47.0, 42.0]
        uv[12:15] = [6.0, 7.2, 6.5]
        temperaturas[8:12] = [10.0, 12.0, 15.0, 18.0]
        tipos = {e["tipo"] for e in eventos(datos_base(rachas=rachas, uv=uv, temperaturas=temperaturas), self.ahora)}
        self.assertIn("racha_fuerte", tipos)
        self.assertIn("uv_alto", tipos)
        self.assertIn("cambio_temperatura", tipos)

    def test_maximo_tres_hitos_por_dia_y_ventana_de_sesenta_horas(self):
        lluvia = [0.3] * 288
        rachas = [45.0] * 72
        uv = [7.0] * 72
        resultado = eventos(datos_base(precipitacion=lluvia, rachas=rachas, uv=uv), self.ahora)
        por_dia = {}
        for evento in resultado:
            por_dia[evento["cuando"].date()] = por_dia.get(evento["cuando"].date(), 0) + 1
            self.assertLessEqual(evento["cuando"], self.ahora + timedelta(hours=60))
        self.assertTrue(all(cantidad <= 3 for cantidad in por_dia.values()))

    def test_muestra_real_solo_produce_frases_con_datos(self):
        resultado = eventos(cargar_fixture(), self.ahora)
        self.assertTrue(resultado)
        self.assertTrue(all(set(e) == {"cuando", "tipo", "frase"} for e in resultado))

    def test_muestra_usa_el_mismo_periodo_para_sombreado_y_fin_de_lluvia(self):
        datos = cargar_fixture()
        periodos = periodos_lluvia(datos)
        episodio_hoy = next(p for p in periodos if p[0].date() == self.ahora.date() and p[0].hour >= 7)
        self.assertEqual(episodio_hoy[0], datetime(2026, 10, 21, 12, 15))
        self.assertGreaterEqual(episodio_hoy[1], datetime(2026, 10, 21, 23, 0))
        self.assertLessEqual(episodio_hoy[0], datetime(2026, 10, 21, 16, 0))
        self.assertGreater(episodio_hoy[1], datetime(2026, 10, 21, 16, 0))
        finales_hoy = [e for e in eventos(datos, self.ahora)
                       if e["tipo"] == "lluvia_fin" and e["cuando"].date() == self.ahora.date()]
        # El error del prototipo: «deja de llover 15:15» con lluvia hasta las 22 h.
        self.assertNotIn(datetime(2026, 10, 21, 15, 15), [e["cuando"] for e in finales_hoy])

    def test_prioriza_regreso_diurno_sobre_chubasco_de_madrugada(self):
        resultado = eventos(cargar_fixture(), self.ahora)
        jueves = [e for e in resultado if e["cuando"].date() == date(2026, 10, 22)]
        inicios = [e for e in jueves if e["tipo"] == "lluvia_inicio"]
        self.assertEqual(len(jueves), 3)
        self.assertEqual([e["cuando"] for e in inicios], [datetime(2026, 10, 22, 11, 15)])
        self.assertTrue(all(not (e["tipo"].startswith("lluvia") and e["cuando"].hour < 7)
                            for e in jueves))


# ── Las 13 de test_render_png.py ──

class TarjetaLluviaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datos = cargar_fixture()
        cls.ahora = AHORA

    def test_barras_hitos_y_tarjetas_comparten_lluvia(self):
        periodos = periodos_lluvia(self.datos)
        for texto, mm in zip(self.datos["hourly"]["time"], self.datos["hourly"]["precipitation"]):
            cuando = datetime.fromisoformat(texto)
            if float(mm or 0) > 0:
                self.assertTrue(any(inicio < cuando + timedelta(hours=1) and fin > cuando
                                    for inicio, fin, _ in periodos), texto)
        for fecha in map(date.fromisoformat, self.datos["daily"]["time"]):
            principal, _ = resumen_lluvia_dia(self.datos, fecha)
            hay_barra = any(datetime.fromisoformat(t).date() == fecha and float(mm or 0) > 0
                            for t, mm in zip(self.datos["hourly"]["time"],
                                             self.datos["hourly"]["precipitation"]))
            self.assertFalse(hay_barra and principal == "Sin lluvia")

    def test_fin_de_lluvia_de_hoy_aparece_aunque_sea_a_las_23(self):
        finales = [h for h in hitos_dibujados(self.datos, self.ahora) if h["tipo"] == "lluvia_fin"]
        self.assertIn(datetime(2026, 10, 21, 23, 0), [h["cuando"] for h in finales])
        self.assertLessEqual(len(hitos_dibujados(self.datos, self.ahora)), 4)

    def test_no_hay_hito_uv_durante_la_lluvia_de_la_muestra(self):
        self.assertNotIn("uv_alto", {e["tipo"] for e in eventos(self.datos, self.ahora)})

    @unittest.skipUnless(HAY_PIL, SIN_PIL)
    def test_imagen_no_supera_1280_por_lado(self):
        imagen = Image.open(BytesIO(tarjeta_png(self.datos, self.ahora, "Las Condes")))
        self.assertLessEqual(imagen.width, 1280)
        self.assertLessEqual(imagen.height, 1280)

    def test_tarjetas_llevan_fecha_y_no_texto_de_lluvia(self):
        tarjetas = datos_tarjetas(self.datos)
        self.assertEqual([t["titulo"] for t in tarjetas], ["Mié 21", "Jue 22", "Vie 23"])
        self.assertEqual(titulo_fecha(date(2026, 10, 21)), "Mié 21")
        for tarjeta in tarjetas:
            self.assertEqual(set(tarjeta), {"titulo", "codigo", "cielo", "minimo", "maximo"})

    def test_conclusion_incluye_lluvia_del_tercer_dia(self):
        texto = conclusion(self.datos, self.ahora)
        for dia in ("hoy", "jueves", "viernes"):
            self.assertIn(dia, texto.lower())
        self.assertIn("todo el día", texto.lower())

    def test_conclusion_sin_lluvia(self):
        # Sintético derivado del fixture real (lluvia y probabilidad en 0): lo permite el encargo.
        texto = conclusion(sin_lluvia(self.datos), self.ahora)
        self.assertTrue(texto.startswith("Sin lluvia hasta el viernes."), texto)

    @unittest.skipUnless(HAY_PIL, SIN_PIL)
    def test_rotulo_ahora_queda_dentro_de_la_tarjeta(self):
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 1260), "white"))
        x0, y0, x1, y1 = caja_ahora(draw, 694)
        self.assertGreaterEqual(x0, 36)
        self.assertGreaterEqual(y0, 472)
        self.assertLessEqual(x1, 1044)
        self.assertLessEqual(y1, 1056)
        geometria = geometria_ahora(draw, 94, 694)
        raya_x, raya_y0, _, raya_y1 = geometria["raya"]
        caja = geometria["caja"]
        intersecta = caja[0] <= raya_x <= caja[2] and caja[1] <= raya_y1 and caja[3] >= raya_y0
        self.assertFalse(intersecta, geometria)

    @unittest.skipUnless(HAY_PIL, SIN_PIL)
    def test_textos_de_tarjetas_tienen_separacion_visible(self):
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 1260), "white"))
        margen, separacion = 36, 16
        ancho = (1080 - 2 * margen - 2 * separacion) // 3
        for indice, tarjeta in enumerate(datos_tarjetas(self.datos)):
            x0 = margen + indice * (ancho + separacion)
            cajas = cajas_tarjeta(draw, x0, x0 + ancho, 142, tarjeta)
            self.assertGreaterEqual(cajas["caja_cielo"][1] - cajas["caja_icono"][3], 12, cajas)
            self.assertGreaterEqual(cajas["caja_temp"][1] - cajas["caja_cielo"][3], 12, cajas)

    def test_responder_cae_a_texto_si_falla_el_dibujo(self):
        # En el prototipo era `responder_boton`; en el bot es `enviar_clima`, y se prueba ahí:
        # con el dibujo roto sale un solo mensaje, el texto de «clima hoy», y ninguna foto.
        bot, salida = _bot_con_fixture(self)
        with mock.patch.object(ci, "tarjeta_png", side_effect=RuntimeError("falla forzada")):
            bot.comando_clima(bot.CHAT_ID)
        self.assertEqual(salida["fotos"], [])
        self.assertEqual(len(salida["textos"]), 1)
        self.assertTrue(salida["textos"][0].startswith("Ahora en Las Condes"), salida)

    def test_pie_tiene_como_maximo_dos_lineas(self):
        texto = pie(self.datos, self.ahora)
        self.assertLessEqual(len(texto.splitlines()), 2)
        self.assertIn("12:15", texto)
        self.assertIn("11:15", texto)

    def test_resumenes_de_la_muestra(self):
        self.assertEqual(resumen_lluvia_dia(self.datos, date(2026, 10, 21)),
                         ("12:15 – noche", "+ madrugada"))
        # El error del prototipo: «+ madrugada» de un horario ya pasado.
        self.assertEqual(resumen_lluvia_dia(self.datos, date(2026, 10, 21), self.ahora),
                         ("12:15 – noche", None))
        self.assertEqual(resumen_lluvia_dia(self.datos, date(2026, 10, 22)),
                         ("11:15 – noche", "+ madrugada"))
        self.assertEqual(resumen_lluvia_dia(self.datos, date(2026, 10, 23)),
                         ("Todo el día", None))

    @unittest.skipUnless(HAY_PIL, SIN_PIL)
    def test_cajas_de_hitos_no_se_superponen(self):
        lienzo = Image.new("RGB", (1080, 1240), "white")
        draw = ImageDraw.Draw(lienzo)
        t0 = self.ahora
        t1 = datetime.combine(self.ahora.date() + timedelta(days=2), datetime.min.time())
        px = lambda t: 94 + (t - t0).total_seconds() / (t1 - t0).total_seconds() * (1020 - 94)  # noqa: E731
        cajas = cajas_hitos(draw, hitos_dibujados(self.datos, self.ahora), px, 94, 1020)
        self.assertNotIn("lluvia_madrugada", {hito["tipo"] for hito in cajas})
        for indice, actual in enumerate(cajas):
            a = actual["caja"]
            for otro in cajas[indice + 1:]:
                b = otro["caja"]
                se_cruzan = a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]
                self.assertFalse(se_cruzan, (actual, otro))


# ── Encargo 74 ──

class TextosExactosTest(unittest.TestCase):
    """C1: el pie y la conclusión, como cadenas, iguales a los del prototipo final."""

    PIE = "☔ Hoy llueve desde cerca de las 12:15 hasta la noche.\nMañana vuelve cerca de las 11:15."
    CONCLUSION = "Llueve los tres días: hoy desde ~12:15, jueves desde ~11:15 y viernes todo el día."

    def test_c1_pie_y_conclusion_del_fixture(self):
        datos = cargar_fixture()
        self.assertEqual(pie(datos, AHORA), self.PIE)
        self.assertEqual(conclusion(datos, AHORA), self.CONCLUSION)

    def test_c1_igual_con_lo_validado_y_con_hora_con_zona(self):
        if ci.TZ_LOCAL is None:
            self.skipTest("sin base de zonas")
        series = ci.leer_series(cargar_fixture())
        con_zona = AHORA.replace(tzinfo=ci.TZ_LOCAL)
        self.assertEqual(pie(series, con_zona), self.PIE)
        self.assertEqual(conclusion(series, con_zona), self.CONCLUSION)
        # 10:30 UTC son las 07:30 en Santiago (-03 en octubre).
        utc = datetime(2026, 10, 21, 10, 30, tzinfo=ci.ZoneInfo("UTC"))
        self.assertEqual(pie(series, utc), self.PIE)

    def test_sin_lluvia_nombra_el_tercer_dia(self):
        # El prototipo decía «el viernes» fijo; desde el jueves, el tercer día es el sábado.
        datos = sin_lluvia(cargar_fixture())
        self.assertEqual(pie(datos, AHORA), "Hoy no se espera lluvia; máxima de 19°.")
        self.assertTrue(conclusion(datos, AHORA).startswith("Sin lluvia hasta el viernes."))
        self.assertEqual(ci._nombre_dia(date(2026, 10, 22) + timedelta(days=2)), "sábado")

    @unittest.skipUnless(HAY_PIL, SIN_PIL)
    def test_c1_png_del_fixture(self):
        png = tarjeta_png(ci.leer_series(cargar_fixture()), AHORA, "Las Condes",
                          consultado=datetime(2026, 10, 21, 7, 20))
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(BytesIO(png)) as imagen:
            self.assertEqual(imagen.size, (1080, 1260))
            self.assertLessEqual(max(imagen.size), 1280)


class TodoElDiaTest(unittest.TestCase):
    """El prototipo sólo se probó a las 7:30. El mismo fixture (consultado a las 19:15 del 21)
    a cada cuarto de hora: textos coherentes con el gráfico y nada superpuesto."""

    @classmethod
    def setUpClass(cls):
        cls.datos = cargar_fixture()

    def a_las(self, h, m=0):
        return datetime(2026, 10, 21, h, m)

    def test_ya_lloviendo_no_dice_que_empieza_manana(self):
        # A las 21:14 llueve hasta las 23 (12:15–23 en `periodos_lluvia`).
        self.assertEqual(pie(self.datos, self.a_las(21, 14)),
                         "☔ Hoy llueve hasta cerca de las 23.\nMañana vuelve cerca de las 11:15.")
        self.assertEqual(conclusion(self.datos, self.a_las(21, 14)),
                         "Llueve los tres días: hoy hasta ~23 h, jueves desde ~11:15 y viernes todo el día.")
        self.assertEqual(pie(self.datos, self.a_las(15)),
                         "☔ Hoy llueve hasta la noche.\nMañana vuelve cerca de las 11:15.")
        # Pasada la lluvia de hoy, lo próximo es la madrugada del jueves.
        self.assertEqual(pie(self.datos, self.a_las(23, 15)), "☔ Mañana empieza cerca de las 2:15.")
        self.assertEqual(conclusion(self.datos, self.a_las(23, 15)),
                         "Lleva paraguas: jueves desde ~11:15 y viernes todo el día.")

    def test_de_madrugada_manda_la_lluvia_grande_y_no_la_llovizna(self):
        # A la 1 quedan 4–5 h (0,1 mm) y 12:15–23 h: el pie habla de la segunda, como la conclusión.
        for h in (0, 1, 3):
            with self.subTest(h=h):
                self.assertEqual(pie(self.datos, self.a_las(h)), TextosExactosTest.PIE)
                self.assertEqual(conclusion(self.datos, self.a_las(h)), TextosExactosTest.CONCLUSION)

    def test_pie_y_conclusion_no_se_contradicen_a_ninguna_hora(self):
        for cuarto in range(96):
            ahora = self.a_las(0) + timedelta(minutes=15 * cuarto)
            with self.subTest(ahora=ahora.time()):
                texto, final = pie(self.datos, ahora), conclusion(self.datos, ahora)
                llueve_hoy = any(b > ahora and a < datetime(2026, 10, 22) for a, b, _ in periodos_lluvia(self.datos))
                self.assertEqual(texto.startswith("☔ Hoy"), llueve_hoy, texto)
                self.assertEqual("hoy" in final, llueve_hoy, final)
                if any(a < ahora < b for a, b, _ in periodos_lluvia(self.datos)):
                    self.assertNotIn(f"~{ci._hora_breve(ahora)},", final, "la hora de ahora no es un inicio")

    @unittest.skipUnless(HAY_PIL, SIN_PIL)
    def test_rotulos_sin_superponerse_a_ninguna_hora(self):
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 1260), "white"))
        visibles = 0
        for cuarto in range(96):
            ahora = self.a_las(0) + timedelta(minutes=15 * cuarto)
            t1 = datetime(2026, 10, 23)
            px = lambda t: 94 + (t - ahora).total_seconds() / (t1 - ahora).total_seconds() * 926  # noqa: E731
            cajas = cajas_hitos(draw, hitos_dibujados(self.datos, ahora), px, 94, 1020)
            caja = geometria_ahora(draw, 94, 694)["caja"]
            with self.subTest(ahora=ahora.time()):
                for i, a in enumerate(cajas):
                    self.assertTrue(94 <= a["caja"][0] and a["caja"][2] <= 1020, a)
                    for b in cajas[i + 1:]:
                        self.assertFalse(ci._cajas_intersectan(a["caja"], b["caja"]), (a, b))
                if ci.texto_ahora_visible(caja, cajas):
                    visibles += 1
                    self.assertFalse(any(ci._cajas_intersectan(ci.fondo_ahora(caja), c["caja"]) for c in cajas))
        self.assertEqual(visibles, 96, "con este fixture el texto «Ahora» se ve a toda hora")

    @unittest.skipUnless(HAY_PIL, SIN_PIL)
    def test_ninguna_linea_cruza_el_texto_ahora(self):
        # En la imagen de verdad: dentro de la caja de «Ahora» sólo hay blanco y verde, ni el
        # gris de las guías (#9AABBE) ni el de la medianoche. A las 9 la guía de «~12:15» y a
        # las 21:14 la de «~23 h» y la medianoche pasaban por encima en el prototipo.
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 1260), "white"))
        x0, y0, x1, y1 = (round(v) for v in geometria_ahora(draw, 94, 694)["caja"])
        for h, m in ((7, 30), (9, 0), (21, 14), (23, 30)):
            with self.subTest(h=h, m=m):
                imagen = Image.open(BytesIO(tarjeta_png(self.datos, self.a_las(h, m), "Las Condes"))).convert("RGB")
                colores = {imagen.getpixel((x, y)) for x in range(x0, x1) for y in range(y0, y1)}
                self.assertNotIn((0x9A, 0xAB, 0xBE), colores)
                self.assertIn((0x31, 0xA4, 0x7C), colores, "el texto está")


class LeerSeriesTest(unittest.TestCase):
    """Lo que `_leer_open_meteo` usa para no dibujar con datos rotos: si algo no calza,
    ValueError y el bot cae a texto."""

    def test_fixture_real_pasa_con_tipos_limpios(self):
        series = ci.leer_series(cargar_fixture())
        self.assertEqual(set(series), {"hourly", "minutely_15", "daily"})
        self.assertEqual(len(series["hourly"]["time"]), 72)
        self.assertEqual(len(series["minutely_15"]["time"]), 288)
        self.assertEqual(series["daily"]["time"], ["2026-10-21", "2026-10-22", "2026-10-23"])
        self.assertTrue(all(isinstance(v, float) for v in series["hourly"]["temperature_2m"]))
        self.assertNotIn("apparent_temperature", series["hourly"], "sólo lo que se usa")

    def test_la_forma_de_la_69_no_alcanza(self):
        datos = cargar_fixture()
        for falta in ("hourly", "minutely_15"):
            cuerpo = deepcopy(datos)
            cuerpo.pop(falta)
            with self.subTest(falta=falta), self.assertRaises(ValueError):
                ci.leer_series(cuerpo)

    def test_entradas_hostiles(self):
        def cambiar(f):
            cuerpo = cargar_fixture()
            f(cuerpo)
            return cuerpo

        h = "hourly"
        rotos = {
            "no es objeto": [],
            "largos distintos": cambiar(lambda c: c[h]["precipitation"].pop()),
            "minutely más corto": cambiar(lambda c: c["minutely_15"]["time"].pop()),
            "NaN": cambiar(lambda c: c[h]["temperature_2m"].__setitem__(5, math.nan)),
            "infinito": cambiar(lambda c: c[h]["precipitation"].__setitem__(5, math.inf)),
            "enorme": cambiar(lambda c: c[h]["precipitation"].__setitem__(5, 1e9)),
            "negativo": cambiar(lambda c: c["minutely_15"]["precipitation"].__setitem__(5, -0.2)),
            "texto": cambiar(lambda c: c[h]["temperature_2m"].__setitem__(5, "12")),
            "bool": cambiar(lambda c: c[h]["precipitation_probability"].__setitem__(5, True)),
            "temperatura nula": cambiar(lambda c: c[h]["temperature_2m"].__setitem__(5, None)),
            "código no entero": cambiar(lambda c: c["daily"]["weather_code"].__setitem__(0, 3.5)),
            "código fuera de tabla": cambiar(lambda c: c["daily"]["weather_code"].__setitem__(0, 500)),
            "probabilidad 300": cambiar(lambda c: c[h]["precipitation_probability"].__setitem__(5, 300)),
            "hora con otra forma": cambiar(lambda c: c[h]["time"].__setitem__(5, "mañana")),
            "hora inexistente": cambiar(lambda c: c[h]["time"].__setitem__(5, "2026-10-21T25:00")),
            "hora con zona": cambiar(lambda c: c[h]["time"].__setitem__(5, "2026-10-21T05:00+00:00")),
            "desordenado": cambiar(lambda c: c[h]["time"].reverse()),
            "lista gigante": cambiar(lambda c: c["minutely_15"].update(
                time=["2026-10-21T00:00"] * 5000, precipitation=[0.0] * 5000)),
            "serie que no es lista": cambiar(lambda c: c[h].update(uv_index="alto")),
            "time vacío": cambiar(lambda c: c["daily"].update(time=[])),
        }
        for nombre, cuerpo in rotos.items():
            with self.subTest(nombre=nombre), self.assertRaises(ValueError):
                ci.leer_series(cuerpo)

    def test_nulos_permitidos_donde_open_meteo_los_pone(self):
        cuerpo = cargar_fixture()
        cuerpo["minutely_15"]["precipitation"][-4:] = [None] * 4
        cuerpo["hourly"]["uv_index"][3] = None
        cuerpo["hourly"]["precipitation_probability"][3] = None
        series = ci.leer_series(cuerpo)
        self.assertIsNone(series["minutely_15"]["precipitation"][-1])
        self.assertEqual(pie(series, AHORA), TextosExactosTest.PIE)

    def test_tres_dias_desde_ahora(self):
        series = ci.leer_series(cargar_fixture())
        # La caché puede traer la respuesta de ayer: el jueves ya no hay pasado mañana.
        with self.assertRaises(ValueError):
            pie(series, datetime(2026, 10, 22, 0, 10))
        with self.assertRaises(ValueError):
            pie(series, datetime(2026, 10, 20, 23, 50))
        # Una respuesta de 7 días se recorta a los tres que muestra la imagen.
        largo = _siete_dias(cargar_fixture())
        recorte = ci.tres_dias(ci.leer_series(largo), AHORA)
        self.assertEqual(recorte["daily"]["time"], ["2026-10-21", "2026-10-22", "2026-10-23"])
        self.assertEqual(len(recorte["hourly"]["time"]), 72)
        self.assertEqual(pie(ci.leer_series(largo), AHORA), TextosExactosTest.PIE)
        self.assertEqual(conclusion(ci.leer_series(largo), AHORA), TextosExactosTest.CONCLUSION)

    def test_parametros_piden_lo_que_se_valida(self):
        p = ci.parametros_open_meteo(-33.41, -70.57)
        self.assertEqual(p["hourly"].split(","), list(ci.HOURLY))
        self.assertEqual(p["minutely_15"], "precipitation")
        self.assertEqual((p["latitude"], p["longitude"], p["forecast_days"], p["timezone"]),
                         (-33.41, -70.57, 7, "America/Santiago"))


def _siete_dias(datos):
    """El fixture estirado a 7 días (como la consulta real): los días 4 a 7 repiten el 3."""
    datos = deepcopy(datos)
    for nombre, por_dia in (("hourly", 24), ("minutely_15", 96)):
        bloque = datos[nombre]
        ultimo = datetime.fromisoformat(bloque["time"][-1])
        paso = timedelta(minutes=15) if nombre == "minutely_15" else timedelta(hours=1)
        for k, v in bloque.items():
            if k == "time":
                bloque[k] = v + [(ultimo + paso * (i + 1)).isoformat(timespec="minutes") for i in range(4 * por_dia)]
            else:
                bloque[k] = v + v[-por_dia:] * 4
    d = datos["daily"]
    for k, v in d.items():
        d[k] = v + ([(date(2026, 10, 24) + timedelta(days=i)).isoformat() for i in range(4)]
                    if k == "time" else [v[-1]] * 4)
    return datos


@unittest.skipUnless(HAY_PIL, SIN_PIL)
class DibujoHostilTest(unittest.TestCase):
    """Valores extremos pero válidos: la imagen sale y nada se dibuja fuera de ella."""

    def test_extremos_no_tumban_ni_se_salen(self):
        cuerpo = sin_lluvia(cargar_fixture())
        h = cuerpo["hourly"]
        h["temperature_2m"] = [-90.0 if i % 2 else 70.0 for i in range(72)]
        h["wind_gusts_10m"] = [500.0] * 72
        h["uv_index"] = [40.0] * 72
        cuerpo["daily"]["temperature_2m_min"] = [-90.0] * 3
        cuerpo["daily"]["temperature_2m_max"] = [70.0] * 3
        series = ci.leer_series(cuerpo)
        png = tarjeta_png(series, AHORA, "Las Condes")
        with Image.open(BytesIO(png)) as imagen:
            self.assertEqual(imagen.size, (1080, 1260))
        # Mucha lluvia: barras topadas en la escala, sin salir del gráfico.
        mojado = cargar_fixture()
        mojado["hourly"]["precipitation"] = [500.0] * 72
        mojado["minutely_15"]["precipitation"] = [125.0] * 288
        self.assertTrue(tarjeta_png(ci.leer_series(mojado), AHORA, "Las Condes").startswith(b"\x89PNG"))

    def test_avisos_de_uv_y_rachas_quedan_dentro_de_la_tarjeta(self):
        cuerpo = sin_lluvia(cargar_fixture())
        cuerpo["hourly"]["wind_gusts_10m"] = [55.0] * 72
        cuerpo["hourly"]["uv_index"] = [11.0] * 72
        datos = ci.leer_series(cuerpo)
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 1260), "white"))
        ancho = (1080 - 2 * 36 - 2 * 16) // 3
        for indice, tarjeta in enumerate(datos_tarjetas(datos)):
            x0 = 36 + indice * (ancho + 16)
            x1 = x0 + ancho
            geo = cajas_tarjeta(draw, x0, x1, 142, tarjeta)
            alertas = ci._alertas_dia(datos, date(2026, 10, 21) + timedelta(days=indice))
            self.assertEqual([t for t, _ in alertas], ["uv", "viento"])
            for alerta in ci.cajas_alertas(draw, x0, x1, 142, alertas, geo["caja_titulo"]):
                a = alerta["caja"]
                self.assertTrue(x0 <= a[0] and a[2] <= x1 and 0 <= a[0] and a[2] <= 1080, alerta)
                self.assertFalse(ci._cajas_intersectan(a, geo["caja_titulo"]), alerta)
        # El caso seco sigue diciendo el aviso en la conclusión, como el prototipo.
        self.assertEqual(conclusion(datos, AHORA), "Sin lluvia hasta el viernes. UV 11.")

    def test_lugar_largo_cabe(self):
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 1260), "white"))
        lugar = "Pedro Aguirre Cerda Pedro Aguirre Cerda "[:40]
        texto, font = ci._titulo_lugar(draw, lugar, 1080 - 96)
        self.assertLessEqual(draw.textbbox((48, 24), texto, font=font)[2], 1080 - 48)
        self.assertTrue(tarjeta_png(cargar_fixture(), AHORA, lugar).startswith(b"\x89PNG"))

    def test_hora_del_pie_es_la_de_la_consulta(self):
        # Se compara contra la misma imagen con otra hora de consulta: tienen que diferir
        # sólo en la franja del pie (y > 1190).
        datos = cargar_fixture()
        a = Image.open(BytesIO(tarjeta_png(datos, AHORA, "Las Condes", datetime(2026, 10, 21, 7, 0))))
        b = Image.open(BytesIO(tarjeta_png(datos, AHORA, "Las Condes", datetime(2026, 10, 21, 7, 25))))
        from PIL import ImageChops
        caja = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox()
        self.assertIsNotNone(caja)
        self.assertGreater(caja[1], 1190, caja)


class LetraYPillowTest(unittest.TestCase):

    def setUp(self):
        self.addCleanup(ci._FUENTES.clear)
        self.addCleanup(ci._AVISADO.clear)
        ci._FUENTES.clear()
        ci._AVISADO.clear()

    @unittest.skipUnless(HAY_PIL, SIN_PIL)
    def test_sin_lato_dibuja_con_la_de_pillow_y_lo_dice(self):
        with tempfile.TemporaryDirectory() as vacia, \
                mock.patch.dict(os.environ, {"BOTV3_CLIMA_FUENTES": vacia}), \
                self.assertLogs("botv3.clima_imagen", "WARNING") as logs:
            png = tarjeta_png(cargar_fixture(), AHORA, "Las Condes")
            self.assertEqual(ci.fuente_usada(), "letra de Pillow")
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(len(logs.output), 1, "una línea, no una por tamaño")
        self.assertIn("no encontré Lato", logs.output[0])

    @unittest.skipUnless(HAY_PIL, SIN_PIL)
    @unittest.skipUnless(Path(ci.FUENTES_DIR, "Lato-Regular.ttf").is_file(),
                         "sin Lato en el sistema (en la Pi está en /usr/share/fonts/truetype/lato)")
    def test_usa_lato_del_sistema(self):
        with mock.patch.dict(os.environ, {"BOTV3_CLIMA_FUENTES": ""}):
            self.assertEqual(ci.fuente_usada(), "Lato-Regular.ttf")
            self.assertIn("Lato", " ".join(ci.fuente(40).getname()))
            self.assertIn("Bold", " ".join(ci.fuente(40, True).getname()))

    def test_sin_pillow_levanta_import_error(self):
        # Siempre corre: es lo que hace caer el botón al texto (C3).
        bloqueo = {nombre: None for nombre in ("PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont")}
        with mock.patch.dict(sys.modules, bloqueo):
            with self.assertRaises(ImportError):
                tarjeta_png(cargar_fixture(), AHORA, "Las Condes")
        # Y los textos no dependen de Pillow.
        with mock.patch.dict(sys.modules, bloqueo):
            self.assertEqual(pie(cargar_fixture(), AHORA), TextosExactosTest.PIE)

    def test_el_modulo_no_importa_pillow_al_cargarse(self):
        bloqueo = {nombre: None for nombre in ("PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont")}
        with mock.patch.dict(sys.modules, bloqueo):
            spec = importlib.util.spec_from_file_location("clima_imagen_sin_pil", AQUI / "clima_imagen.py")
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
        self.assertTrue(callable(modulo.tarjeta_png))


@unittest.skipUnless(HAY_PIL, SIN_PIL)
class HerramientaTest(unittest.TestCase):
    """`python3 clima_imagen.py --png …`, sin red: con `--json` (la respuesta guardada)."""

    def test_main_escribe_el_png_y_dice_que_hizo(self):
        with tempfile.TemporaryDirectory() as tmp:
            salida = Path(tmp) / "x.png"
            out = StringIO()
            with contextlib.redirect_stdout(out):
                rc = ci.main(["--png", str(salida), "--json", str(FIXTURE), "--ahora", "2026-10-21T07:30",
                              "--lugar", "Las Condes"])
            self.assertEqual(rc, 0)
            self.assertTrue(salida.read_bytes().startswith(b"\x89PNG"))
        lineas = out.getvalue().splitlines()
        self.assertIn("PNG 1080x1260, Las Condes", lineas[0])
        self.assertEqual(lineas[1], "Pie: " + TextosExactosTest.PIE.replace("\n", " / "))
        self.assertEqual(lineas[2], "Conclusión: " + TextosExactosTest.CONCLUSION)

    def test_sin_lugar_lo_toma_del_perfil(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"BOTV3_PERFIL": "jaime"}):
            out = StringIO()
            with contextlib.redirect_stdout(out):
                ci.main(["--png", str(Path(tmp) / "x.png"), "--json", str(FIXTURE), "--ahora", "2026-10-21T07:30"])
        self.assertIn(", Las Condes,", out.getvalue())
        self.assertEqual(ci._ubicacion_del_perfil("jaime"), (-33.41, -70.57, "Las Condes"))
        with self.assertRaises(SystemExit):
            ci._ubicacion_del_perfil("../secretos")

    def test_consulta_con_los_parametros_del_bot(self):
        llamadas = []

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return cargar_fixture()

        falso = type(sys)("requests")
        falso.get = lambda url, params=None, timeout=None: llamadas.append((url, params, timeout)) or Resp()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"requests": falso}):
            with contextlib.redirect_stdout(StringIO()):
                ci.main(["--png", str(Path(tmp) / "x.png"), "--lat", "-33.41", "--lon", "-70.57",
                         "--lugar", "Las Condes", "--ahora", "2026-10-21T07:30"])
        self.assertEqual(llamadas, [(ci.URL_OPEN_METEO, ci.parametros_open_meteo(-33.41, -70.57), 10)])


# ── El bot, con Telegram falso, para la prueba del prototipo `responder_boton` ──

_BOT = {}


def _bot_con_fixture(test):
    """botv3.py cargado con el estado en un temporal (como test_botv3.py), Open-Meteo con
    el fixture y Telegram anotado. Devuelve (módulo, {"fotos", "textos"})."""
    if "modulo" not in _BOT:
        tmp = tempfile.TemporaryDirectory(prefix="clima-imagen-bot-")
        _BOT["tmp"] = tmp
        base = Path(tmp.name)
        entorno = {
            "BOTV3_USO_RUTAS": base / "uso-rutas.json", "BOTV3_USO_CUENTAS": base / "uso-cuentas.jsonl",
            "BOTV3_USO_JSON": base / "uso.json", "BOTV3_REGISTRO_CUENTAS": base / "cuentas.toml",
            "BOTV3_STATE_DIR": base / "state", "BOTV3_REMOTO_DIR": base / "remoto",
            "BOTV3_ML_SOCKET": base / "ml-puente.sock", "BOTV3_ML_DIR": base / "mercadolibre",
            "BOTV3_CASA_DIR": base / "casa", "BOTV3_PERFIL": "jaime",
        }
        with mock.patch.dict(os.environ, {k: str(v) for k, v in entorno.items()}):
            spec = importlib.util.spec_from_file_location("botv3_clima_imagen", AQUI / "botv3.py")
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
        _BOT["modulo"] = modulo
    bot = _BOT["modulo"]
    if bot.clima_imagen is not ci:
        test.skipTest("botv3 cargó otro clima_imagen")
    salida = {"fotos": [], "textos": []}

    class OpenMeteo:
        def get(self, url, params=None, timeout=None):
            class Resp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return cargar_fixture()
            return Resp()

    ahora = AHORA.replace(tzinfo=bot.TZ_LOCAL)
    for nombre, valor in (("SES_CLIMA", OpenMeteo()), ("_CLIMA_CACHE", {}), ("ahora_santiago", lambda: ahora),
                          ("send_photo", lambda chat, png, pie, reply_markup=None: salida["fotos"].append(pie)),
                          ("send_text", lambda chat, texto: salida["textos"].append(texto)),
                          ("audit", lambda *a, **k: None)):
        test.addCleanup(setattr, bot, nombre, getattr(bot, nombre))
        setattr(bot, nombre, valor)
    return bot, salida


if __name__ == "__main__":
    unittest.main(verbosity=2)
