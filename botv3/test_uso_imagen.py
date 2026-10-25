#!/usr/bin/env python3
"""Pruebas de /uso como imagen (encargo 90): la imagen sale del panel de bots-info sin recalcular,
tiene el tamaño esperado y el rojo cuando se pasa el tope; y el bot cae al texto de siempre si algo
falla. Sin red, sin Telegram y sin escribir fuera de un temporal.

    NODO_PRUEBAS=1 python3 -B -m unittest botv3/test_uso_imagen.py
"""
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from datetime import datetime

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

if importlib.util.find_spec("requests") is None:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = RuntimeError
    requests_stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

# El mismo aislamiento que test_botv3.py: todo el estado del bot en un temporal.
_TMP = tempfile.TemporaryDirectory(prefix="botv3-uso-imagen-")
for clave, nombre in (("BOTV3_USO_RUTAS", "uso-rutas.json"), ("BOTV3_USO_CUENTAS", "uso-cuentas.jsonl"),
                      ("BOTV3_USO_JSON", "uso.json"), ("BOTV3_REGISTRO_CUENTAS", "cuentas.toml"),
                      ("BOTV3_STATE_DIR", "state"), ("BOTV3_REMOTO_DIR", "remoto"),
                      ("BOTV3_ML_SOCKET", "ml-puente.sock"), ("BOTV3_ML_DIR", "mercadolibre"),
                      ("BOTV3_CASA_DIR", "casa")):
    os.environ[clave] = str(Path(_TMP.name) / nombre)

import uso_imagen  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bi = cargar("bots_info_uso_imagen", AQUI.parent / "pi" / "bots-info.py")
recetas = cargar("recetas_uso_imagen", AQUI / "recetas.py")


def panel(caso):
    """El panel de bots-info sobre los fixtures de pi/fixtures/cuentas/, como lo entrega --margen."""
    f = json.loads((AQUI.parent / f"pi/fixtures/cuentas/margen-{caso}.json").read_text(encoding="utf-8"))
    ahora = datetime.fromisoformat(f["ahora"]).astimezone(bi.TZ)
    registro = {k: v for k, v in bi.leer_toml(str(AQUI.parent / "pi/fixtures/avisos/cuentas.toml")).items()
                if isinstance(v, dict)}
    limites = bi.limites_de(f["uso"])
    margen = bi.margen_de(registro, limites, ahora, bi.resumen_cuentas(registro, [], ahora, dict(limites)), recetas)
    return bi.panel_margen(margen, f["reglas"], ahora)


def rojos(png):
    """Píxeles del rojo de «mal» (#ec6a6a), con algo de tolerancia por el suavizado."""
    im = Image.open(BytesIO(png)).convert("RGB")
    crudo = im.tobytes()
    return sum(1 for k in range(0, len(crudo), 3)
               if crudo[k] > 200 and 80 < crudo[k + 1] < 130 and 80 < crudo[k + 2] < 130)


@unittest.skipIf(Image is None, "sin Pillow")
class Imagen(unittest.TestCase):
    def test_png_de_1080_de_ancho_con_alto_segun_las_cuentas(self):
        png = uso_imagen.tarjeta_png(panel("normal"))
        self.assertTrue(png.startswith(b"\x89PNG"))
        im = Image.open(BytesIO(png))
        self.assertEqual(im.width, 1080)
        self.assertGreater(im.height, 900)
        self.assertLess(im.height, uso_imagen.ALTO_MAX)
        con_una = dict(panel("normal"))
        con_una["tarjetas"] = con_una["tarjetas"][:1]
        self.assertLess(Image.open(BytesIO(uso_imagen.tarjeta_png(con_una))).height, im.height)

    def test_el_rojo_aparece_al_pasar_el_tope(self):
        normal, pasado = rojos(uso_imagen.tarjeta_png(panel("normal"))), rojos(uso_imagen.tarjeta_png(panel("pasado")))
        self.assertGreater(pasado, normal * 1.5 + 200, (normal, pasado))
        # Lo mismo sin tocar otra cosa que el «sobre_tope» que calcula bots-info: la imagen no decide.
        p = panel("normal")
        for t in p["tarjetas"]:
            for v in t["ventanas"]:
                if v["capacidad"]:
                    v["capacidad"]["sobre_tope"] = True
        self.assertGreater(rojos(uso_imagen.tarjeta_png(p)), normal + 200)

    def test_no_recalcula_dibuja_lo_que_trae_el_panel(self):
        p = panel("normal")
        codex = next(t for t in p["tarjetas"] if t["cuenta"] == "codex")
        codex["ventanas"][0]["capacidad"]["texto"][1] = "999 %"
        codex["ventanas"][0]["capacidad"]["suma"] = 999
        self.assertNotEqual(uso_imagen.tarjeta_png(p), uso_imagen.tarjeta_png(panel("normal")))

    def test_sin_dato_renovada_y_sin_carga(self):
        p = panel("normal")
        t = p["tarjetas"][0]
        t["ventanas"] = [{"etiqueta": "5 h", "estado": "sin_dato", "texto": "5 h: sin dato"},
                         {"etiqueta": "Semana", "estado": "renovada", "texto": "Semana: ya se renovó", "nota": "",
                          "barra": {"usado": 0, "tramos": [], "tope": None, "clase": ""}, "capacidad": None,
                          "despues": None, "renueva": None}]
        p["con_carga"] = False
        self.assertTrue(uso_imagen.tarjeta_png(p).startswith(b"\x89PNG"))

    def test_sin_lato_usa_la_letra_de_pillow(self):
        viejo = os.environ.get("BOTV3_CLIMA_FUENTES")
        os.environ["BOTV3_CLIMA_FUENTES"] = str(Path(_TMP.name) / "sin-fuentes")
        self.addCleanup(lambda: os.environ.pop("BOTV3_CLIMA_FUENTES") if viejo is None
                        else os.environ.__setitem__("BOTV3_CLIMA_FUENTES", viejo))
        with self.assertLogs("botv3.clima_imagen", "WARNING"):
            self.assertTrue(uso_imagen.tarjeta_png(panel("normal")).startswith(b"\x89PNG"))

    def test_pie_y_forma_invalida(self):
        self.assertEqual(uso_imagen.pie(panel("normal")),
                         "Claude (Diego) es la que tiene más margen: 75 % libre en su ventana más apretada.")
        self.assertEqual(uso_imagen.pie({"panel": panel("normal")}), uso_imagen.pie(panel("normal")))
        for malo in (None, {}, {"panel": None}, {"tarjetas": [{"nombre": 1}], "resumen": {}}):
            with self.assertRaises(ValueError):
                uso_imagen.tarjeta_png(malo)


class Bot(unittest.TestCase):
    """/uso, el botón y «¿cuánta cuota queda?» mandan lo mismo, y caen al texto de hoy."""

    @classmethod
    def setUpClass(cls):
        cls.bot = cargar("botv3_uso_imagen", AQUI / "botv3.py")

    def setUp(self):
        b = self.bot
        self.fotos, self.textos, self.comandos, self.auditoria = [], [], [], []
        self.salida = {"/usr/local/bin/bots-info": json.dumps({"panel": panel("normal")}),
                       "/usr/local/bin/uso-agentes": "texto de uso-agentes"}
        originales = {k: getattr(b, k) for k in ("send_photo", "send_text", "safe_command", "audit", "uso_imagen")}
        self.addCleanup(lambda: [setattr(b, k, v) for k, v in originales.items()])

        def safe_command(argv, timeout=45):
            self.comandos.append(tuple(argv))
            salida = self.salida[argv[0]]
            if isinstance(salida, Exception):
                raise salida
            return salida
        b.safe_command = safe_command
        b.send_photo = lambda chat, png, pie, reply_markup=None: self.fotos.append((chat, png, pie))
        b.send_text = lambda chat, texto, *a, **k: self.textos.append(texto)
        b.audit = lambda *a: self.auditoria.append(a)
        b.uso_imagen = uso_imagen

    def test_uso_manda_la_imagen_con_el_pie(self):
        if Image is None:
            self.skipTest("sin Pillow")
        self.bot.comando_uso(1)
        self.assertEqual(len(self.fotos), 1)
        self.assertTrue(self.fotos[0][1].startswith(b"\x89PNG"))
        self.assertEqual(self.fotos[0][2], uso_imagen.pie(panel("normal")))
        self.assertEqual(self.textos, [])
        self.assertEqual(self.comandos, [("/usr/local/bin/bots-info", "--margen")])

    def test_la_frase_da_lo_mismo_que_uso(self):
        if Image is None:
            self.skipTest("sin Pillow")
        self.bot.comando_uso(1)
        por_comando = list(self.fotos)
        self.fotos.clear()
        self.assertEqual(self.bot.intencion_nodo("¿cuánta cuota queda?"), "uso")
        self.bot.atender_nodo(1, "uso", "telegram", False)
        self.assertEqual(self.fotos, por_comando)
        self.assertEqual(self.auditoria[-1], ("nodo_uso", "telegram", "ok"))

    def test_respaldo_a_texto(self):
        casos = {
            "sin módulo": lambda: setattr(self.bot, "uso_imagen", None),
            "bots-info falla": lambda: self.salida.__setitem__("/usr/local/bin/bots-info", RuntimeError("no está")),
            "JSON roto": lambda: self.salida.__setitem__("/usr/local/bin/bots-info", "{roto"),
            "sin panel": lambda: self.salida.__setitem__("/usr/local/bin/bots-info", json.dumps({"panel": None})),
            "sendPhoto rechazado": lambda: setattr(self.bot, "send_photo", self._rechazo),
        }
        for nombre, romper in casos.items():
            with self.subTest(nombre):
                self.setUp()
                romper()
                self.assertEqual(self.bot.enviar_uso(1), "texto")
                self.assertEqual(self.textos, ["texto de uso-agentes"])

    def test_sin_pillow_cae_al_texto(self):
        viejo = uso_imagen.tarjeta_png
        self.addCleanup(setattr, uso_imagen, "tarjeta_png", viejo)
        uso_imagen.tarjeta_png = lambda panel: (_ for _ in ()).throw(ImportError("No module named 'PIL'"))
        self.assertEqual(self.bot.enviar_uso(1), "texto")
        self.assertEqual(self.textos, ["texto de uso-agentes"])

    def test_foto_que_pudo_llegar_no_se_duplica(self):
        if Image is None:
            self.skipTest("sin Pillow")
        def ambiguo(*a, **k):
            raise ValueError("200 ilegible")
        self.bot.send_photo = ambiguo
        self.assertEqual(self.bot.enviar_uso(1), "incierto")
        self.assertEqual(self.textos, [])

    def test_si_tampoco_hay_texto_lo_dice(self):
        self.bot.uso_imagen = None
        self.salida["/usr/local/bin/uso-agentes"] = RuntimeError("uso-agentes roto")
        self.assertEqual(self.bot.enviar_uso(1), "error")
        self.assertTrue(self.textos[0].startswith("No pude obtener el uso"))
        self.bot.atender_nodo(1, "uso", "telegram", False)
        self.assertEqual(self.auditoria[-1], ("nodo_uso", "telegram", "error"))

    def test_safe_command_acepta_solo_margen(self):
        b = cargar("botv3_uso_imagen_safe", AQUI / "botv3.py")
        with self.assertRaises(RuntimeError):
            b.safe_command(["/usr/local/bin/bots-info"])
        with self.assertRaises(RuntimeError):
            b.safe_command(["/usr/local/bin/bots-info", "--margen", "--otra"])

    def _rechazo(self, *a, **k):
        r = types.SimpleNamespace(status_code=400)
        exc = RuntimeError("Bad Request")
        exc.response = r
        raise exc


if __name__ == "__main__":
    unittest.main()
