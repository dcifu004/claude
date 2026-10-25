#!/usr/bin/env python3
"""Pruebas de Mercado Libre en Dcs_v3bot (encargo 40): enlaces, umbrales, la lista, la revisión
de 5 veces al día, los avisos y los comandos del bot. El puente es el de verdad (pi/ml_puente.py)
contestando con las respuestas capturadas en pi/fixtures/mercadolibre/. Sin red."""
import importlib.util
import io
import json
import os
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest import mock
from urllib.parse import urlsplit

if importlib.util.find_spec("requests") is None:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = RuntimeError
    requests_stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

# Igual que test_botv3.py: nada de esto puede caer en el estado real del bot, y menos en el
# socket del puente ni en la lista de vigilados de verdad.
_TMP = tempfile.TemporaryDirectory(prefix="botv3-ml-")
for clave, nombre in (("BOTV3_USO_RUTAS", "uso-rutas.json"), ("BOTV3_USO_CUENTAS", "uso-cuentas.jsonl"),
                      ("BOTV3_USO_JSON", "uso.json"), ("BOTV3_REGISTRO_CUENTAS", "cuentas.toml"),
                      ("BOTV3_STATE_DIR", "state"), ("BOTV3_ML_SOCKET", "ml-puente.sock"),
                      ("BOTV3_ML_DIR", "mercadolibre")):
    os.environ[clave] = str(Path(_TMP.name) / nombre)

BOTV3 = Path(__file__).resolve().parent
PI = BOTV3.parent / "pi"
FIXTURES = PI / "fixtures" / "mercadolibre"
sys.path.insert(0, str(BOTV3))


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


botv3 = cargar("botv3", BOTV3 / "botv3.py")
ml = botv3.mercadolibre_mod
ml_puente = cargar("ml_puente", PI / "ml_puente.py")

ENLACE_REAL = ("https://www.mercadolibre.cl/parlantes-multimedia-edifier-g2000-negro/p/MLC44720703"
               "#polycard_client=search-desktop&search_layout=grid&position=1&type=product"
               "&tracking_id=0e1d2c3b-aaaa-bbbb-cccc-1234567890ab&wid=MLC1186395107&sid=search")
SUELTA_JM = "https://articulo.mercadolibre.cl/MLC-4026071128-parlante-bluetooth-portatil-_JM"
SUELTA_UP = "https://www.mercadolibre.cl/parlante-edifier-g2000/up/MLCU415281688"
SECRETO = "S3cretoDeLaAppParaPruebas0123456"
AHORA = datetime(2026, 10, 10, 12, 4, tzinfo=ml.TZ)


def fx(nombre):
    d = json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))
    return d["http"], json.dumps(d["cuerpo"]).encode()


class PuenteDePrueba:
    """El puente de verdad, sin socket: lo que el bot pide llega a ml_puente.Puente.atender, y
    Mercado Libre contesta con los fixtures."""

    def __init__(self, carpeta: Path):
        (carpeta / "vivo").mkdir(parents=True)
        (carpeta / "app.json").write_text(json.dumps({"client_id": "1", "client_secret": SECRETO}))
        (carpeta / "vivo" / "token.json").write_text(json.dumps({"estado": "ok", "refresh_token": "TG-0123456789abcdef-a"}))
        self.parches = [mock.patch.object(ml_puente, "APP", str(carpeta / "app.json")),
                        mock.patch.object(ml_puente, "TOKEN", str(carpeta / "vivo" / "token.json")),
                        mock.patch.object(ml_puente.sys, "stderr", io.StringIO())]
        for p in self.parches:
            p.start()
        self.rutas, self.pedidos, self.rechazar = {}, [], False
        self.puente = ml_puente.Puente(http=self.http)

    def cerrar(self):
        for p in self.parches:
            p.stop()

    def http(self, metodo, url, cabeceras, datos=None):
        ruta = urlsplit(url).path
        if ruta == "/oauth/token":
            if self.rechazar:
                return 400, json.dumps({"error": "invalid_grant", "message":
                                        f"bad TG-0123456789abcdef-a {SECRETO}"}).encode()
            return 200, json.dumps({"access_token": "APP_USR-1-acceso", "expires_in": 21600,
                                    "refresh_token": "TG-0123456789abcdef-b"}).encode()
        return self.rutas.get(ruta, (404, b'{"message":"No winners found","error":"not_found"}'))

    def __call__(self, operacion, datos, ruta=None, timeout=60):
        self.pedidos.append((operacion, datos))
        _, r = self.puente.atender(operacion, datos)
        if not r.get("ok"):
            raise ml.ErrorPuente(ml.limpio(r.get("error", "")), r.get("codigo", "error"),
                                 int(r.get("reintentar_en") or 0))
        return r

    def precio(self, ident, precio, original=None, envio=True):
        """Deja a `ident` con una sola oferta a `precio`; None = sin ofertas (404)."""
        if precio is None:
            self.rutas.pop(f"/products/{ident}/items", None)
            return
        self.rutas[f"/products/{ident}/items"] = (200, json.dumps({
            "paging": {"total": 1, "offset": 0, "limit": 50},
            "results": [{"price": precio, "original_price": original, "currency_id": "CLP",
                         "condition": "new", "seller_id": 1, "official_store_id": None,
                         "shipping": {"free_shipping": envio}}]}).encode())


class ConMercadoLibre(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ml-bot-")
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "mercadolibre"
        self.dir.mkdir()
        self.pedir = PuenteDePrueba(Path(self._tmp.name) / "secretos")
        self.addCleanup(self.pedir.cerrar)
        self.pedir.rutas["/products/MLC44720703"] = fx("producto-MLC44720703.json")
        self.pedir.rutas["/products/MLC44720703/items"] = fx("ofertas-MLC44720703.json")
        self.avisos = []
        for nombre, valor in (("DIR", self.dir), ("puente", self.pedir),
                              ("avisar", lambda texto, linea=None: self.avisos.append((texto, linea)) or True)):
            p = mock.patch.object(ml, nombre, valor)
            p.start()
            self.addCleanup(p.stop)

    def alta(self, umbral="89990", ident="MLC44720703"):
        item, _ = ml.proponer(f"{ident} {umbral}", ahora=AHORA)
        ml.agregar(item)
        return item

    def textos(self):
        return [t for t, _ in self.avisos]


class EnlacesTests(unittest.TestCase):
    def test_el_enlace_real_del_usuario(self):
        self.assertEqual(ml.extraer_id(ENLACE_REAL), "MLC44720703")

    def test_con_y_sin_fragmento_y_consulta(self):
        base = "https://www.mercadolibre.cl/parlantes-multimedia-edifier-g2000-negro/p/MLC44720703"
        for enlace in (base, base + "?pdp_filters=item_id:MLC1186395107", base + "#reco_item_pos=2&x=/up/MLCU1",
                       base + "?a=1#b=2", base + "/", base + "/s?x=1", "http://mercadolibre.cl/p/MLC44720703",
                       "www.mercadolibre.cl/algo/p/MLC44720703", "  " + base + "  ", base.replace("/p/MLC", "/p/mlc"),
                       "MLC44720703", "mlc44720703", " MLC44720703 "):
            self.assertEqual(ml.extraer_id(enlace), "MLC44720703", enlace)

    def test_una_publicacion_suelta_se_rechaza_con_la_frase_para_el_usuario(self):
        for suelta in (SUELTA_JM, SUELTA_UP, "MLC-4026071128", "MLCU415281688",
                       "https://articulo.mercadolibre.cl/MLC-4026071128-_JM#position=1&/p/MLC44720703",
                       "https://www.mercadolibre.cl/up/MLCU415281688?x=/p/MLC44720703"):
            with self.assertRaises(ml.NoVigilable) as c:
                ml.extraer_id(suelta)
            self.assertEqual(str(c.exception), ml.NO_ES_CATALOGO, suelta)
        self.assertIn("publicación suelta", ml.NO_ES_CATALOGO)
        self.assertIn("no la puedo vigilar", ml.NO_ES_CATALOGO)
        self.assertIn("/p/MLC", ml.NO_ES_CATALOGO)

    def test_lo_que_no_es_de_mercado_libre_chile_no_pasa(self):
        for malo in ("https://evil.example/p/MLC44720703", "https://mercadolibre.cl.evil.example/p/MLC44720703",
                     "https://www.mercadolibre.com.ar/p/MLA44720703", "ftp://www.mercadolibre.cl/p/MLC44720703",
                     "https://www.mercadolibre.cl/ofertas", "https://www.mercadolibre.cl/p/MLC123",
                     "parlante edifier", "MLC123", "MLA44720703", "", "https://[::1"):
            with self.assertRaises(ml.NoVigilable, msg=malo):
                ml.extraer_id(malo)


class UmbralTests(unittest.TestCase):
    def test_precio_fijo(self):
        for texto in ("89990", "$89990", "$89.990", "89.990", "$ 89.990", "89.990 CLP", "89990,00"):
            self.assertEqual(ml.parse_umbral(texto), {"tipo": "precio", "valor": 89990}, texto)
        self.assertEqual(ml.parse_umbral("1.250.000"), {"tipo": "precio", "valor": 1250000})

    def test_porcentaje(self):
        for texto in ("-10%", "10%", "-10 %", "- 10 %", "10 %"):
            self.assertEqual(ml.parse_umbral(texto), {"tipo": "porcentaje", "valor": 10.0}, texto)
        self.assertEqual(ml.parse_umbral("-12,5%"), {"tipo": "porcentaje", "valor": 12.5})

    def test_lo_que_no_se_entiende_se_rechaza(self):
        for malo in ("", "barato", "-5000", "0", "0%", "100%", "150%", "99.9", "89.99.0", "10 por ciento", "$"):
            with self.assertRaises(ml.NoVigilable, msg=malo):
                ml.parse_umbral(malo)

    def test_parse_vigilar_separa_enlace_y_umbral(self):
        self.assertEqual(ml.parse_vigilar(f"{ENLACE_REAL} -10%"), ("MLC44720703", {"tipo": "porcentaje", "valor": 10.0}))
        self.assertEqual(ml.parse_vigilar("MLC44720703   $ 89.990"), ("MLC44720703", {"tipo": "precio", "valor": 89990}))
        for malo in ("", "MLC44720703", ENLACE_REAL):
            with self.assertRaises(ml.NoVigilable) as c:
                ml.parse_vigilar(malo)
            self.assertEqual(str(c.exception), ml.USO_VIGILAR)
        with self.assertRaises(ml.NoVigilable) as c:
            ml.parse_vigilar(f"{SUELTA_JM} 5000")
        self.assertEqual(str(c.exception), ml.NO_ES_CATALOGO)

    def test_el_objetivo_del_porcentaje_no_pierde_un_peso_por_la_coma_flotante(self):
        self.assertEqual(ml.objetivo({"tipo": "porcentaje", "valor": 10.0}, 99900), 89910)
        self.assertEqual(ml.objetivo({"tipo": "porcentaje", "valor": 12.5}, 99900), 87412)
        self.assertEqual(ml.objetivo({"tipo": "precio", "valor": 89990}, 99900), 89990)
        self.assertIsNone(ml.objetivo({"tipo": "porcentaje", "valor": 10.0}, None))
        for base in range(1000, 200000, 990):
            for n in (5, 10, 15, 20, 33):
                self.assertEqual(ml.objetivo({"tipo": "porcentaje", "valor": float(n)}, base), base * (100 - n) // 100)


class ListaTests(ConMercadoLibre):
    def test_proponer_no_escribe_y_muestra_el_producto_y_el_precio_de_hoy(self):
        item, texto = ml.proponer(f"{ENLACE_REAL} 89990", ahora=AHORA)
        self.assertEqual(ml.leer_lista(), [])
        self.assertEqual(list(self.dir.iterdir()), [])
        self.assertEqual((item["id"], item["nombre"], item["precio_base"], item["umbral"]),
                         ("MLC44720703", "Parlantes Multimedia Edifier G2000 Negro", 99900,
                          {"tipo": "precio", "valor": 89990}))
        self.assertIn("Parlantes Multimedia Edifier G2000 Negro (MLC44720703)", texto)
        self.assertIn("Hoy: desde $99.900 · 2 oferta(s) · envío gratis", texto)
        self.assertIn("Aviso: a $89.990 o menos.", texto)
        self.assertIn("https://www.mercadolibre.cl/p/MLC44720703", texto)

    def test_proponer_en_porcentaje_dice_el_precio_que_resulta(self):
        _, texto = ml.proponer("MLC44720703 -10%", ahora=AHORA)
        self.assertIn("Aviso: baja 10 % desde $99.900: $89.910 o menos.", texto)

    def test_proponer_avisa_si_ya_esta_bajo_el_umbral_o_sin_ofertas(self):
        _, texto = ml.proponer("MLC44720703 100000", ahora=AHORA)
        self.assertIn("Ya está bajo ese umbral", texto)
        self.pedir.precio("MLC44720703", None)
        item, texto = ml.proponer("MLC44720703 -10%", ahora=AHORA)
        self.assertIsNone(item["precio_base"])
        self.assertIn("Hoy no tiene ofertas", texto)
        self.assertIn("baja 10 % desde el primer precio que vea", texto)

    def test_un_producto_que_no_existe_no_se_propone(self):
        with self.assertRaises(ml.ErrorPuente) as c:
            ml.proponer("MLC99999999 5000")
        self.assertEqual(c.exception.codigo, "no_existe")

    def test_agregar_quitar_y_cambiar_el_umbral(self):
        self.alta("89990")
        self.assertEqual([i["id"] for i in ml.leer_lista()], ["MLC44720703"])
        item, _ = ml.proponer("MLC44720703 -15%", ahora=AHORA)
        self.assertTrue(ml.agregar(item), "el mismo producto no se duplica: cambia el umbral")
        self.assertEqual([i["umbral"] for i in ml.leer_lista()], [{"tipo": "porcentaje", "valor": 15.0}])
        self.assertEqual(ml.quitar("MLC44720703")["id"], "MLC44720703")
        self.assertIsNone(ml.quitar("MLC44720703"))
        self.assertEqual(ml.leer_lista(), [])

    def test_la_lista_se_escribe_entera_o_nada(self):
        self.alta("89990")
        antes = (self.dir / "vigilados.json").read_bytes()
        otro = dict(ml.leer_lista()[0], id="MLC55555555")
        for donde in ("write", "fsync", "replace"):
            with mock.patch.object(ml.os, donde, side_effect=OSError(28, "No space left on device")):
                with self.assertRaises(OSError):
                    ml.agregar(otro)
            self.assertEqual((self.dir / "vigilados.json").read_bytes(), antes, donde)
            self.assertFalse(any(".nuevo" in p.name for p in self.dir.iterdir()), donde)

    def test_tope_de_vigilados_y_entradas_rotas(self):
        item = self.alta("89990")
        with mock.patch.object(ml, "MAX_VIGILADOS", 1):
            with self.assertRaises(ml.NoVigilable):
                ml.agregar(dict(item, id="MLC55555555"))
            ml.agregar(item)        # el que ya estaba sí se puede actualizar
        (self.dir / "vigilados.json").write_text(json.dumps({"vigilados": [
            item, {"id": "../../etc/passwd", "umbral": item["umbral"]}, {"id": "MLC55555555"},
            {"id": "MLC66666666", "umbral": {"tipo": "regalo", "valor": 1}}, "basura"]}))
        self.assertEqual([i["id"] for i in ml.leer_lista()], ["MLC44720703"])
        (self.dir / "vigilados.json").write_text("{no es json")
        self.assertEqual(ml.leer_lista(), [])

    def test_elegir_para_dejar(self):
        with self.assertRaises(ml.NoVigilable):
            ml.elegir("1")
        self.alta("89990")
        self.assertEqual(ml.elegir(" 1 ")["id"], "MLC44720703")
        for malo in ("0", "2", "-1", "uno", "", "MLC44720703"):
            with self.assertRaises(ml.NoVigilable, msg=malo):
                ml.elegir(malo)


class RevisionTests(ConMercadoLibre):
    def revisar(self, precio="igual"):
        if precio != "igual":
            self.pedir.precio("MLC44720703", precio)
        antes = len(self.avisos)
        self.resumen = ml.revisar(ahora=AHORA)
        return self.textos()[antes:]

    def test_precio_fijo_avisa_una_vez_por_baja(self):
        self.alta("89990")
        self.assertEqual(self.revisar(), [], "$99.900 no baja de $89.990")
        self.assertEqual(self.revisar(90000), [])
        nuevos = self.revisar(89990)
        self.assertEqual(len(nuevos), 1, "llegar al umbral cuenta")
        self.assertIn("«Parlantes Multimedia Edifier G2000 Negro» bajó a $89.990, con envío gratis", nuevos[0])
        self.assertIn("Umbral: a $89.990 o menos", nuevos[0])
        self.assertIn("https://www.mercadolibre.cl/p/MLC44720703", nuevos[0])
        self.assertTrue(nuevos[0].startswith("🔔 Mercado Libre:"))
        self.assertEqual(self.revisar(89990), [], "la misma baja no se avisa dos veces")
        self.assertEqual(self.revisar(89990), [])
        self.assertEqual(self.revisar(89980), [], "$10 menos no es otra baja: los vendedores se rebajan de a poco")
        self.assertEqual(self.revisar(88200), [], "−1,99 % desde el aviso: todavía no")
        mas = self.revisar(85000)
        self.assertEqual(len(mas), 1, "−5 % desde el aviso anterior sí es otra baja")
        self.assertIn("siguió bajando: $85.000", mas[0])
        self.assertIn("el aviso anterior fue en $89.990", mas[0])
        self.assertEqual(self.revisar(87000), [], "subir un poco, aún bajo el umbral, no es noticia")
        self.assertEqual(self.revisar(84000), [], "−1,2 % desde $85.000")
        self.assertEqual(self.revisar(95000), [], "volver a subir no avisa")
        self.assertEqual(len(self.revisar(89000)), 1, "y la baja siguiente es otra")
        self.assertEqual(len(self.avisos), 3)

    def test_porcentaje_desde_que_empezo_a_vigilar(self):
        item = self.alta("-10%")
        self.assertEqual(item["precio_base"], 99900)
        self.assertEqual(self.revisar(89911), [], "un peso sobre el −10 %")
        nuevos = self.revisar(89910)
        self.assertEqual(len(nuevos), 1)
        self.assertIn("bajó a $89.910", nuevos[0])
        self.assertIn("Umbral: baja 10 % desde $99.900: $89.910 o menos", nuevos[0])
        self.assertEqual(self.revisar(89910), [])
        # La base no se mueve con las revisiones: sigue siendo el precio del día del alta.
        self.assertEqual(self.revisar(120000), [])
        self.assertEqual(self.revisar(100000), [], "−17 % desde 120.000 no cuenta: la base es 99.900")
        self.assertEqual(len(self.revisar(89000)), 1)

    def test_porcentaje_sobre_un_producto_agregado_sin_ofertas(self):
        self.pedir.precio("MLC44720703", None)
        self.alta("-10%")
        self.assertEqual(self.revisar(), [])
        nuevos = self.revisar(50000)
        self.assertEqual(len(nuevos), 1)
        self.assertIn("volvió a tener ofertas: desde $50.000", nuevos[0])
        self.assertEqual(self.revisar(45001), [], "la base es el primer precio visto: 50.000")
        self.assertEqual(len(self.revisar(45000)), 1)

    def test_si_el_aviso_no_sale_no_se_marca_y_se_reintenta(self):
        self.alta("89990")
        with mock.patch.object(ml, "avisar", lambda texto, linea=None: False):
            ml.revisar(ahora=AHORA)
            self.pedir.precio("MLC44720703", 80000)
            ml.revisar(ahora=AHORA)
            ml.revisar(ahora=AHORA)
        self.assertEqual(self.avisos, [])
        self.assertEqual(len(self.revisar()), 1, "la primera revisión en que el aviso sale, avisa")
        self.assertEqual(self.revisar(), [])

    def test_se_queda_sin_ofertas_y_vuelve_a_tener(self):
        self.alta("89990")
        self.revisar()
        nuevos = self.revisar(None)
        self.assertEqual(len(nuevos), 1)
        self.assertTrue(nuevos[0].startswith("📭 Mercado Libre: «Parlantes Multimedia Edifier G2000 Negro» se quedó sin ofertas"))
        self.assertEqual(self.revisar(None), [], "sigue sin ofertas: no se repite")
        vuelve = self.revisar(99900)
        self.assertEqual(len(vuelve), 1)
        self.assertTrue(vuelve[0].startswith("📦 Mercado Libre:"))
        self.assertIn("volvió a tener ofertas: desde $99.900", vuelve[0])
        self.assertEqual(self.revisar(99900), [])

    def test_vuelve_ya_bajo_el_umbral_y_es_un_solo_aviso(self):
        self.alta("89990")
        self.assertEqual(len(self.revisar(80000)), 1)
        self.assertEqual(len(self.revisar(None)), 1)
        vuelve = self.revisar(80000)
        self.assertEqual(len(vuelve), 1, "volvió al mismo precio de antes: igual es noticia, una sola")
        self.assertIn("bajó a $80.000", vuelve[0])
        self.assertEqual(self.revisar(80000), [])

    def test_sin_autorizacion_avisa_una_vez_con_la_linea_de_ml_oauth(self):
        self.alta("89990")
        self.revisar()
        self.pedir.rechazar = True
        self.pedir.puente._acceso = ""      # vence el token de acceso: la próxima consulta renueva
        nuevos = self.revisar()
        self.assertEqual(len(nuevos), 1)
        self.assertEqual(nuevos[0], "🔑 Mercado Libre pide autorizar: Mercado Libre rechazó la renovación "
                                    "(invalid_grant): hay que autorizar de nuevo (sudo ml-oauth url)")
        self.assertEqual(self.avisos[-1][1], "sudo ml-oauth url", "la línea copiable va al registro de avisos")
        self.assertEqual(self.resumen["puente"], "sin_autorizacion")
        for _ in range(4):
            self.assertEqual(self.revisar(), [], "una vez, no en cada revisión")
        for secreto in (SECRETO, "TG-", "APP_USR"):
            self.assertNotIn(secreto, nuevos[0])
        # Tras autorizar de nuevo, una revisión que pasa rearma el aviso.
        self.pedir.rechazar = False
        token = Path(ml_puente.TOKEN)
        token.write_text(json.dumps({"estado": "ok", "refresh_token": "TG-0123456789abcdef-c"}))
        self.assertEqual(self.revisar(), [])
        self.assertEqual(self.resumen["puente"], "ok")
        self.pedir.rechazar, self.pedir.puente._acceso = True, ""
        self.assertEqual(len(self.revisar()), 1)

    def test_sin_secret_key_la_linea_es_la_de_cargarla(self):
        self.alta("89990")
        Path(ml_puente.APP).unlink()
        self.pedir.puente._acceso = ""
        nuevos = self.revisar()
        self.assertEqual(nuevos, ["🔑 Mercado Libre pide autorizar: falta la Secret Key de la app "
                                  "(sudo ml-oauth cargar-secreto)"])
        self.assertEqual(self.avisos[-1][1], "sudo ml-oauth cargar-secreto")
        self.assertEqual(self.revisar(), [])

    def test_ultima_revision_es_la_ultima_que_pudo_consultar(self):
        self.alta("89990")
        ml.revisar(ahora=AHORA)
        self.pedir.rechazar, self.pedir.puente._acceso = True, ""
        ml.revisar(ahora=datetime(2026, 10, 10, 18, 17, tzinfo=ml.TZ))
        e = ml.leer_estado()
        self.assertEqual((e["ultima_revision"][:16], e["ultimo_intento"][:16]),
                         ("2026-10-10T12:04", "2026-10-10T18:17"))
        self.assertEqual(e["puente"]["estado"], "sin_autorizacion")

    def test_puente_caido_no_avisa_ni_pierde_el_estado(self):
        self.alta("89990")
        self.revisar(80000)
        antes = ml.leer_estado()["productos"]["MLC44720703"]

        def caido(*a, **k):
            raise ml.PuenteNoDisponible("el puente a Mercado Libre no responde (ConnectionRefusedError)")

        with mock.patch.object(ml, "puente", caido):
            self.assertEqual(self.revisar(), [])
        self.assertEqual(self.resumen["puente"], "no_responde")
        self.assertEqual(ml.leer_estado()["productos"]["MLC44720703"], antes)
        self.assertEqual(self.revisar(80000), [], "al volver, la baja ya avisada no se repite")

    def test_un_error_de_un_producto_no_frena_a_los_demas(self):
        self.alta("89990")
        self.pedir.rutas["/products/MLC55555555"] = fx("producto-MLC44720703.json")
        self.pedir.precio("MLC55555555", 50000)
        self.alta("40000", "MLC55555555")
        self.pedir.rutas["/products/MLC44720703/items"] = (503, b"upstream")
        self.pedir.precio("MLC55555555", 39000)
        nuevos = self.revisar()
        self.assertEqual(len(nuevos), 1)
        self.assertIn("$39.000", nuevos[0])
        self.assertEqual((self.resumen["revisados"], self.resumen["errores"]), (1, 1))
        self.assertIn("503", ml.leer_estado()["productos"]["MLC44720703"]["error"])

    def test_con_tope_espera_y_sigue_en_vez_de_dejar_siempre_a_los_ultimos(self):
        self.alta("89990")
        self.pedir.rutas["/products/MLC55555555"] = fx("producto-MLC44720703.json")
        self.pedir.precio("MLC55555555", 50000)
        self.alta("40000", "MLC55555555")
        self.pedir.precio("MLC55555555", 39000)
        real, topes, pausas = self.pedir, iter([True, False, False]), []

        def con_tope(op, datos, ruta=None, timeout=60):
            if op == "ofertas" and next(topes, False):
                raise ml.ErrorPuente("tope de 60 consultas por minuto", "tope", 17)
            return real(op, datos)

        with mock.patch.object(ml, "puente", con_tope):
            resumen = ml.revisar(ahora=AHORA, dormir=pausas.append)
        self.assertEqual(pausas, [17])
        self.assertEqual((resumen["revisados"], resumen["errores"]), (2, 0))
        self.assertEqual(len(self.avisos), 1)
        # Dos topes seguidos sobre el mismo producto: se corta la pasada, sin esperar más.
        with mock.patch.object(ml, "puente", lambda *a, **k: (_ for _ in ()).throw(
                ml.ErrorPuente("tope", "tope", 30))):
            resumen = ml.revisar(ahora=AHORA, dormir=pausas.append)
        self.assertEqual(pausas, [17, 30])
        self.assertEqual((resumen["revisados"], resumen["errores"]), (0, 1))

    def test_el_historial_guarda_el_minimo_de_cada_revision(self):
        self.alta("89990")
        for precio in (99900, 95000, None, 97000):
            self.revisar(precio)
        lineas = [json.loads(x) for x in (self.dir / "historial.jsonl").read_text().splitlines()]
        self.assertEqual([x["minimo"] for x in lineas], [99900, 95000, None, 97000])
        self.assertEqual({x["id"] for x in lineas}, {"MLC44720703"})
        self.assertEqual(set(lineas[0]), {"momento", "id", "minimo", "ofertas"})
        p = ml.leer_estado()["productos"]["MLC44720703"]
        self.assertEqual((p["minimo_historico"], p["ultimo"], p["revisiones"]), (95000, 97000, 4))

    def test_el_historial_no_crece_sin_limite(self):
        self.alta("89990")
        with mock.patch.object(ml, "MAX_HISTORIAL_BYTES", 600):
            for _ in range(30):
                self.revisar()
        lineas = (self.dir / "historial.jsonl").read_text().splitlines()
        self.assertTrue(2 <= len(lineas) < 30)
        for linea in lineas:
            json.loads(linea)

    def test_dar_de_alta_de_nuevo_olvida_lo_avisado_antes(self):
        self.alta("89990")
        self.assertEqual(len(self.revisar(85000)), 1)
        item, _ = ml.proponer("MLC44720703 86000", ahora=datetime(2026, 10, 11, 9, 0, tzinfo=ml.TZ))
        ml.agregar(item)
        self.assertEqual(len(self.revisar(85000)), 1, "umbral nuevo y el precio ya está debajo: avisa")
        self.assertEqual(self.revisar(85000), [])

    def test_dejar_de_vigilar_borra_su_estado_y_no_se_consulta_mas(self):
        self.alta("89990")
        self.revisar()
        ml.quitar("MLC44720703")
        self.pedir.pedidos.clear()
        self.revisar()
        self.assertEqual(self.pedir.pedidos, [])
        self.assertEqual(ml.leer_estado()["productos"], {})
        self.assertEqual(self.resumen, {"vigilados": 0, "revisados": 0, "errores": 0, "puente": "ok"})

    def test_dos_revisiones_a_la_vez_no_se_pisan(self):
        self.alta("89990")
        with ml._cerrojo(".revision.lock"):
            with self.assertRaises(OSError):
                ml.revisar(ahora=AHORA)


class AvisosTests(unittest.TestCase):
    """Los avisos salen por el camino que ya existe: la bandeja que lee pi/avisos.py."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ml-avisos-")
        self.addCleanup(self._tmp.cleanup)
        self.vol = Path(self._tmp.name)
        self.ra = ml._registro_avisos()
        for nombre, valor in (("VOLUMEN", self.vol), ("REGISTRO", self.vol / "avisos.jsonl"),
                              ("BANDEJA", self.vol / "avisos-salida.jsonl"),
                              ("BANDEJA_CERROJO", self.vol / ".avisos-salida.lock"),
                              ("BANDEJA_ESTADO", self.vol / "avisos-bandeja.json")):
            p = mock.patch.object(self.ra, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(self.ra.os.path, "ismount", lambda ruta: True)
        p.start()
        self.addCleanup(p.stop)

    def activar(self):
        (self.vol / "avisos-bandeja.json").write_text(json.dumps(
            {"version": self.ra.BANDEJA_VERSION, "ultimo_ciclo": time.time(), "ok": True}))

    def test_es_el_registro_unico_de_siempre(self):
        self.assertEqual(Path(self.ra.__file__).name, "registro_avisos.py")
        self.assertEqual(Path(self.ra.__file__).parent.name, "encargos")

    def test_el_aviso_queda_en_la_bandeja_que_lee_avisos_py_y_en_el_registro(self):
        self.activar()
        texto = ("🔔 Mercado Libre: «Parlantes Multimedia Edifier G2000 Negro» bajó a $89.990, con envío gratis. "
                 "Umbral: a $89.990 o menos. https://www.mercadolibre.cl/p/MLC44720703")
        self.assertTrue(ml.avisar(texto))
        avisos_py = cargar("avisos", PI / "avisos.py")
        pendientes = avisos_py.pendientes_bandeja((self.vol / "avisos-salida.jsonl").read_bytes(), {}, time.time())
        self.assertEqual([p["texto"] for p in pendientes], [texto], "avisos.py lo acepta tal cual y lo manda")
        registro = [json.loads(x) for x in (self.vol / "avisos.jsonl").read_text().splitlines()]
        self.assertEqual([(r["origen"], r["texto"], r["linea"]) for r in registro], [("mercadolibre", texto, None)])

    def test_el_aviso_de_autorizar_lleva_la_linea_copiable(self):
        self.activar()
        self.assertTrue(ml.avisar("🔑 Mercado Libre pide autorizar: falta autorizar. En la Pi: sudo ml-oauth url",
                                  ml.LINEA_AUTORIZAR))
        r = json.loads((self.vol / "avisos.jsonl").read_text())
        self.assertEqual(r["linea"], "sudo ml-oauth url")
        self.assertIn("sudo ml-oauth url", json.loads((self.vol / "avisos-salida.jsonl").read_text())["texto"])

    def test_sin_el_emisor_andando_no_se_da_por_avisado(self):
        self.assertFalse(ml.avisar("🔔 Mercado Libre: algo"), "sin avisos-bandeja.json fresco no hay quien lo mande")
        self.assertFalse((self.vol / "avisos-salida.jsonl").exists())
        self.assertFalse((self.vol / "avisos.jsonl").exists())
        (self.vol / "avisos-bandeja.json").write_text(json.dumps(
            {"version": self.ra.BANDEJA_VERSION, "ultimo_ciclo": time.time() - 3600, "ok": True}))
        self.assertFalse(ml.avisar("🔔 Mercado Libre: algo"))

    def test_un_token_en_el_texto_no_llega_a_la_bandeja(self):
        self.activar()
        self.assertTrue(ml.avisar("🔑 Mercado Libre pide autorizar: bad TG-0123456789abcdef-a APP_USR-1-acceso x"))
        todo = (self.vol / "avisos-salida.jsonl").read_text() + (self.vol / "avisos.jsonl").read_text()
        for secreto in ("TG-", "APP_USR"):
            self.assertNotIn(secreto, todo)

    def test_si_la_bandeja_falla_avisar_devuelve_false_y_no_lanza(self):
        self.activar()
        with mock.patch.object(self.ra, "a_la_bandeja", side_effect=RuntimeError("boom")), \
                mock.patch.object(ml.sys, "stderr", io.StringIO()):
            self.assertFalse(ml.avisar("🔔 Mercado Libre: algo"))


class TextosTests(ConMercadoLibre):
    def test_vigilados_muestra_precio_actual_minimo_y_umbral(self):
        self.assertIn("No hay productos vigilados", ml.texto_vigilados(AHORA))
        self.alta("89990")
        texto = ml.texto_vigilados(AHORA)
        self.assertIn("Vigilados en Mercado Libre (1) · aún sin revisar", texto)
        self.assertIn("Ahora: $99.900 (al agregarlo; aún sin revisar) · mínimo visto: $99.900", texto)
        ml.revisar(ahora=AHORA)
        self.pedir.precio("MLC44720703", 95000)
        ml.revisar(ahora=AHORA)
        self.pedir.precio("MLC44720703", 97000)
        ml.revisar(ahora=AHORA)
        texto = ml.texto_vigilados(AHORA)
        self.assertIn("🛒 Vigilados en Mercado Libre (1) · última revisión hoy 12:04", texto)
        self.assertIn("1. Parlantes Multimedia Edifier G2000 Negro", texto)
        self.assertIn("Ahora: $97.000 (1 oferta(s)) · mínimo visto: $95.000 (hoy 12:04)", texto)
        self.assertIn("Aviso: a $89.990 o menos", texto)
        self.assertIn("https://www.mercadolibre.cl/p/MLC44720703", texto)
        self.assertIn("/dejar <n>", texto)
        self.pedir.precio("MLC44720703", None)
        ml.revisar(ahora=AHORA)
        self.assertIn("Ahora: sin ofertas · mínimo visto: $95.000", ml.texto_vigilados(AHORA))

    def test_cotizar_tabla_con_minimo_descuento_envio_y_enlace(self):
        self.pedir.rutas["/products/search"] = fx("buscar-catalogo-zapatilla-nike.json")
        self.pedir.rutas["/products/MLC56203053/items"] = fx("ofertas-MLC44720703.json")
        self.pedir.precio("MLC56203050", 54990, original=69990, envio=False)
        texto = ml.cotizar("  zapatilla   nike court vision ")
        self.assertEqual(self.pedir.pedidos[-1], ("buscar_catalogo", {"q": "zapatilla nike court vision", "n": 5}))
        self.assertIn("🛒 «zapatilla nike court vision» — 2 producto(s) con ofertas, de 10 revisados", texto)
        self.assertIn("1. Zapatilla Nike Court Vision Low Next Nature Hombre\n   $99.900 · envío gratis · 2 oferta(s)\n"
                      "   https://www.mercadolibre.cl/p/MLC56203053", texto)
        self.assertIn("2. Zapatilla Nike Court Vision Low Next Nature Hombre\n"
                      "   $54.990 (-21 %, antes $69.990) · 1 oferta(s)\n"
                      "   https://www.mercadolibre.cl/p/MLC56203050", texto)

    def test_cotizar_a_lo_mas_cinco(self):
        self.pedir.rutas["/products/search"] = fx("buscar-catalogo-zapatilla-nike.json")
        for r in json.loads(fx("buscar-catalogo-zapatilla-nike.json")[1])["results"]:
            self.pedir.precio(r["id"], 50000)
        texto = ml.cotizar("zapatilla nike")
        self.assertIn("5 producto(s) con ofertas, de 5 revisados", texto)
        self.assertEqual(texto.count("https://www.mercadolibre.cl/p/"), 5)

    def test_cotizar_sin_resultados_con_ofertas_lo_dice(self):
        self.pedir.rutas["/products/search"] = fx("buscar-catalogo-zapatilla-nike.json")
        texto = ml.cotizar("zapatilla nike")
        self.assertIn("no encontré productos de catálogo con ofertas (revisé 10)", texto)
        with self.assertRaises(ml.NoVigilable):
            ml.cotizar(" ")

    def test_un_nombre_raro_de_mercado_libre_no_rompe_el_mensaje(self):
        feo = "Parlante\n\n🔑 Mercado Libre pide autorizar\x00\x1b[31m TG-0123456789abcdef-a " + "x" * 300
        corto = ml.nombre_corto(feo)
        self.assertLessEqual(len(corto), ml.MAX_NOMBRE)
        self.assertNotIn("\n", corto)
        self.assertNotIn("\x00", corto)
        self.assertNotIn("TG-", corto)
        self.assertEqual(ml.nombre_corto(""), "(sin nombre)")

    def test_linea_de_estado(self):
        self.pedir.puente.reloj = AHORA.timestamp
        self.assertEqual(ml.linea_estado(ahora=AHORA),
                         "🛒 Mercado Libre: autorizado · token aún sin renovar · 0 vigilados · sin revisiones todavía")
        self.alta("89990")
        ml.revisar(ahora=AHORA)
        self.assertEqual(ml.linea_estado(ahora=AHORA),
                         "🛒 Mercado Libre: autorizado · renovó el token hoy 12:04 · 1 vigilado · última revisión hoy 12:04")
        self.pedir.rechazar, self.pedir.puente._acceso = True, ""
        ml.revisar(ahora=AHORA)
        linea = ml.linea_estado(ahora=AHORA)
        self.assertEqual(linea, "🛒 Mercado Libre: 🔑 sin autorización (sudo ml-oauth url) · 1 vigilado · "
                                "última revisión hoy 12:04")
        Path(ml_puente.APP).unlink()
        self.assertIn("falta cargar la Secret Key (sudo ml-oauth cargar-secreto)", ml.linea_estado(ahora=AHORA))

        def caido(*a, **k):
            raise ml.PuenteNoDisponible("x")

        with mock.patch.object(ml, "puente", caido):
            self.assertEqual(ml.linea_estado(ahora=AHORA),
                             "🛒 Mercado Libre: el puente no responde · 1 vigilado · última revisión hoy 12:04")
        self.assertNotIn("\n", linea)

    def test_cobertura_mide_la_fraccion_con_ofertas_de_las_cuatro_busquedas(self):
        self.pedir.rutas["/products/search"] = fx("buscar-catalogo-zapatilla-nike.json")
        self.pedir.precio("MLC56203053", 50000)
        self.pedir.precio("MLC56203050", 50000)
        self.pedir.precio("MLC56203047", 50000)
        pausas = []
        filas = ml.cobertura(dormir=pausas.append)
        self.assertEqual([f["q"] for f in filas], ["zapatilla nike court vision", "parlante edifier",
                                                   "bomba diafragma 12v", "esp32 devkit"])
        self.assertEqual([p for p in self.pedir.pedidos if p[0] == "buscar_catalogo"][0][1],
                         {"q": "zapatilla nike court vision", "n": 20})
        self.assertEqual([(f["revisados"], f["con_ofertas"]) for f in filas], [(10, 3)] * 4)
        self.assertEqual(pausas, [30, 30, 30], "se espacian para no pasar el tope del puente")
        texto = ml.texto_cobertura(filas)
        self.assertIn("zapatilla nike court vision: 3 de 10 con ofertas (30 %)", texto)
        self.assertIn("Total: 12 de 40 (30 %)", texto)

    def test_cobertura_espera_si_el_puente_dice_tope(self):
        respuestas = iter([ml.ErrorPuente("tope", "tope", 12), {"revisados": 20, "con_ofertas": 5}])

        def pedir(op, datos, timeout=60):
            r = next(respuestas)
            if isinstance(r, Exception):
                raise r
            return r

        pausas = []
        filas = ml.cobertura(pedir=pedir, dormir=pausas.append, busquedas=("esp32 devkit",))
        self.assertEqual(pausas, [12])
        self.assertEqual(ml.texto_cobertura(filas), "esp32 devkit: 5 de 20 con ofertas (25 %)\nTotal: 5 de 20 (25 %)")


class BotTests(ConMercadoLibre):
    """Los comandos en Dcs_v3bot, con el Telegram de mentira."""

    def setUp(self):
        super().setUp()
        self.enviados, self.telegram = [], []
        for nombre, valor in (("send_text", lambda chat, texto: self.enviados.append(texto)),
                              ("telegram", lambda metodo, payload=None, timeout=40: self.telegram.append((metodo, payload))),
                              ("audit", lambda *a, **k: None), ("ml_falta", lambda: ""),
                              ("safe_command", lambda argv, timeout=45: "🟢 Nodo sano\ntodo ok")):
            p = mock.patch.object(botv3, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        botv3.PROPUESTAS.clear()
        self.addCleanup(botv3.PROPUESTAS.clear)

    def mensaje(self, texto):
        botv3.handle_message({"chat": {"id": botv3.CHAT_ID}, "from": {"id": botv3.USER_ID}, "text": texto})
        for hilo in [h for h in botv3.threading.enumerate() if h.name == "botv3-ml"]:
            hilo.join(10)

    def boton(self, decision="si", pid=None):
        pid = pid or next(iter(botv3.PROPUESTAS))
        botv3.handle_callback({"id": "q1", "data": f"mlv:{decision}:{pid}", "from": {"id": botv3.USER_ID},
                               "message": {"message_id": 77, "chat": {"id": botv3.CHAT_ID}}})

    def test_vigilar_propone_con_boton_y_no_escribe_hasta_el_ok(self):
        self.mensaje(f"/vigilar {ENLACE_REAL} 89990")
        self.assertEqual(self.enviados, ["⏳ Consultando Mercado Libre…"])
        metodo, payload = self.telegram[-1]
        self.assertEqual(metodo, "sendMessage")
        self.assertIn("¿Vigilo este producto?", payload["text"])
        self.assertIn("Parlantes Multimedia Edifier G2000 Negro (MLC44720703)", payload["text"])
        botones = payload["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([b["text"] for b in botones], ["✅ Vigilar", "✖️ Descartar"])
        self.assertTrue(all(len(b["callback_data"].encode()) <= 64 for b in botones))
        self.assertEqual(ml.leer_lista(), [], "agregar es una escritura: espera el ✅")
        self.boton("si")
        self.assertEqual([(i["id"], i["umbral"], i["precio_base"]) for i in ml.leer_lista()],
                         [("MLC44720703", {"tipo": "precio", "valor": 89990}, 99900)])
        metodo, payload = self.telegram[-1]
        self.assertEqual((metodo, payload["message_id"]), ("editMessageText", 77))
        self.assertIn("✅ Vigilando.", payload["text"])

    def test_descartar_no_escribe_y_el_boton_no_sirve_dos_veces(self):
        self.mensaje("/vigilar MLC44720703 -10%")
        pid = next(iter(botv3.PROPUESTAS))
        self.boton("no", pid)
        self.assertEqual(ml.leer_lista(), [])
        self.assertIn("✖️ Descartado.", self.telegram[-1][1]["text"])
        self.boton("si", pid)
        self.assertEqual(ml.leer_lista(), [])
        self.assertEqual(self.telegram[-1][1]["text"], "Esa propuesta ya venció o se usó")

    def test_un_boton_de_otro_usuario_no_agrega_nada(self):
        self.mensaje("/vigilar MLC44720703 -10%")
        pid = next(iter(botv3.PROPUESTAS))
        botv3.handle_callback({"id": "q1", "data": f"mlv:si:{pid}", "from": {"id": botv3.USER_ID + 1},
                               "message": {"message_id": 77, "chat": {"id": botv3.CHAT_ID}}})
        self.assertEqual(ml.leer_lista(), [])
        self.assertEqual(self.telegram[-1][1]["text"], "No autorizado")

    def test_el_boton_no_sirve_para_una_propuesta_de_otro_tipo(self):
        self.alta("89990")
        for ajena in ({"tipo": "google", "accion": {"accion": "crear_evento"}},
                      {"tipo": "compras_quitar", "id": "MLC44720703", "texto": "x"},
                      {"texto": "una memoria", "origen": "telegram"}):
            pid = botv3._nueva_propuesta(ajena)
            self.boton("si", pid)
            self.assertEqual(self.telegram[-1], ("answerCallbackQuery", {
                "callback_query_id": "q1", "text": "Esa propuesta ya venció o se usó"}))
        self.assertEqual(len(ml.leer_lista()), 1, "ni agrega ni saca nada")

    def test_una_publicacion_suelta_se_explica_y_no_consulta_al_puente(self):
        for suelta in (SUELTA_JM, SUELTA_UP):
            self.enviados.clear()
            self.mensaje(f"/vigilar {suelta} 5000")
            self.assertEqual(self.enviados, ["⏳ Consultando Mercado Libre…", ml.NO_ES_CATALOGO])
        self.assertEqual(self.pedir.pedidos, [])
        self.assertEqual(botv3.PROPUESTAS, {})

    def test_vigilar_sin_umbral_muestra_el_uso(self):
        self.mensaje("/vigilar MLC44720703")
        self.assertEqual(self.enviados[-1], ml.USO_VIGILAR)

    def test_vigilados_y_dejar(self):
        self.alta("89990")
        self.mensaje("/vigilados")
        self.assertIn("1. Parlantes Multimedia Edifier G2000 Negro", self.enviados[-1])
        self.assertNotIn("⏳ Consultando Mercado Libre…", self.enviados, "/vigilados no sale del nodo")
        self.mensaje("/dejar 1")
        metodo, payload = self.telegram[-1]
        self.assertIn("¿Dejo de vigilar este producto?", payload["text"])
        self.assertEqual(payload["reply_markup"]["inline_keyboard"][0][0]["text"], "✅ Dejar de vigilar")
        self.assertEqual(len(ml.leer_lista()), 1, "sacar también pide el botón")
        self.boton("si")
        self.assertEqual(ml.leer_lista(), [])
        self.assertIn("✅ Ya no se vigila.", self.telegram[-1][1]["text"])
        self.mensaje("/dejar 1")
        self.assertEqual(self.enviados[-1], "No hay productos vigilados.")

    def test_cotizar(self):
        self.pedir.rutas["/products/search"] = fx("buscar-catalogo-zapatilla-nike.json")
        self.pedir.precio("MLC56203050", 54990, original=69990)
        self.mensaje("/cotizar zapatilla nike court vision")
        self.assertEqual(self.enviados[0], "⏳ Consultando Mercado Libre…")
        self.assertIn("$54.990 (-21 %, antes $69.990) · envío gratis · 1 oferta(s)", self.enviados[1])
        self.assertIn("https://www.mercadolibre.cl/p/MLC56203050", self.enviados[1])
        self.mensaje("/cotizar")
        self.assertIn("Uso: /cotizar <texto>", self.enviados[-1])

    def test_estado_trae_una_linea_de_mercado_libre(self):
        self.alta("89990")
        self.mensaje("/estado")
        lineas = self.enviados[-1].splitlines()
        self.assertEqual(lineas[:2], ["🟢 Nodo sano", "todo ok"])
        self.assertEqual(len(lineas), 3)
        self.assertTrue(lineas[2].startswith("🛒 Mercado Libre: autorizado"))
        self.assertIn("1 vigilado", lineas[2])
        self.enviados.clear()
        self.mensaje("¿cómo está la Pi?")
        self.assertTrue(self.enviados[-1].splitlines()[-1].startswith("🛒 Mercado Libre:"))

    def test_la_ayuda_nombra_los_comandos_solo_donde_hay_mercado_libre(self):
        self.mensaje("/ayuda")
        for comando in ("/vigilar", "/vigilados", "/dejar", "/cotizar"):
            self.assertIn(comando, self.enviados[-1])
        with mock.patch.object(botv3, "ml_falta", lambda: "Mercado Libre no corresponde a este bot."):
            self.mensaje("/ayuda")
            self.assertEqual(self.enviados[-1], botv3.HELP)
            self.assertNotIn("/cotizar", self.enviados[-1])
            for comando in ("/vigilar MLC44720703 1000", "/vigilados", "/dejar 1", "/cotizar parlante"):
                self.mensaje(comando)
                self.assertEqual(self.enviados[-1], "Mercado Libre no corresponde a este bot.")
            self.mensaje("/estado")
            self.assertEqual(self.enviados[-1], "🟢 Nodo sano\ntodo ok")
        self.assertEqual(self.pedir.pedidos, [])

    def test_acciones_declara_la_unica_escritura(self):
        self.mensaje("/acciones")
        self.assertIn("Lo único que escribe es la lista de productos vigilados", self.enviados[-1])
        with mock.patch.object(botv3, "ml_falta", lambda: "Mercado Libre no corresponde a este bot."):
            self.mensaje("/acciones")
        self.assertEqual(self.enviados[-1], botv3.ACTIONS)

    def test_sin_autorizacion_el_bot_lo_dice_sin_mostrar_el_token(self):
        self.pedir.rechazar = True
        self.mensaje("/vigilar MLC44720703 89990")
        self.mensaje("/cotizar parlante edifier")
        self.mensaje("/estado")
        self.assertTrue(self.enviados[1].startswith("🔑 Mercado Libre pide autorizar:"))
        self.assertIn("sudo ml-oauth url", self.enviados[1])
        self.assertIn("🔑 sin autorización (sudo ml-oauth url)", self.enviados[-1])
        todo = json.dumps([self.enviados, self.telegram], ensure_ascii=False)
        for secreto in (SECRETO, "TG-", "APP_USR", "Bearer"):
            self.assertNotIn(secreto, todo)

    def test_nada_de_lo_que_manda_el_bot_trae_el_token_ni_la_secret_key(self):
        self.pedir.rutas["/products/search"] = fx("buscar-catalogo-zapatilla-nike.json")
        self.pedir.precio("MLC56203050", 54990)
        for texto in (f"/vigilar {ENLACE_REAL} -10%", "/vigilados", "/cotizar zapatilla nike", "/estado", "/ayuda"):
            self.mensaje(texto)
        self.boton("si")
        self.mensaje("/vigilados")
        self.mensaje("/dejar 1")
        self.boton("si")
        self.assertTrue(Path(ml_puente.TOKEN).read_text().count("TG-"), "el puente sí renovó: había token que filtrar")
        todo = json.dumps([self.enviados, self.telegram], ensure_ascii=False)
        for secreto in (SECRETO, "TG-", "APP_USR", "Bearer", "refresh", "client_secret"):
            self.assertNotIn(secreto, todo)

    def test_si_la_lista_no_se_puede_escribir_se_dice(self):
        self.mensaje("/vigilar MLC44720703 89990")
        with mock.patch.object(ml, "agregar", side_effect=OSError(30, "Read-only file system")):
            self.boton("si")
        self.assertIn("❌ No pude guardar la lista de vigilados", self.enviados[-1])
        self.assertEqual(ml.leer_lista(), [])

    def test_de_a_una_consulta_a_la_vez(self):
        self.assertTrue(botv3.ML_OCUPADO.acquire(blocking=False))
        try:
            self.mensaje("/cotizar parlante")
        finally:
            botv3.ML_OCUPADO.release()
        self.assertEqual(self.enviados, ["Ya estoy consultando Mercado Libre. Espera a que conteste y repite."])
        self.assertEqual(self.pedir.pedidos, [])
        self.mensaje("/vigilados")
        self.assertTrue(botv3.ML_OCUPADO.acquire(blocking=False), "el hilo devuelve el turno")
        botv3.ML_OCUPADO.release()


class AccesoTests(unittest.TestCase):
    def test_el_permiso_es_el_del_socket(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "ml.sock"
            self.assertIn("no está disponible ahora", ml.sin_acceso(str(ruta)))
            ruta.touch()
            self.assertEqual(ml.sin_acceso(str(ruta)), "")
            if os.geteuid() != 0:
                ruta.chmod(0)
                self.assertEqual(ml.sin_acceso(str(ruta)), "Mercado Libre no corresponde a este bot.")

    def test_la_suite_no_toca_el_socket_ni_la_lista_reales(self):
        self.assertTrue(ml.SOCKET.startswith(_TMP.name))
        self.assertNotEqual(ml.SOCKET, "/run/ml-puente.sock")
        self.assertTrue(str(cargar("ml_limpio", BOTV3 / "mercadolibre.py").DIR).startswith(_TMP.name))
        self.assertIn("no está disponible", botv3.ml_falta())

    def test_sin_puente_los_errores_se_dicen_en_una_frase(self):
        with self.assertRaises(ml.PuenteNoDisponible) as c:
            ml.puente("estado", {}, ruta="/nonexistent/ml.sock", timeout=1)
        self.assertEqual(ml.frase_error(c.exception),
                         "❌ Mercado Libre: el puente a Mercado Libre no responde (FileNotFoundError)")
        self.assertIn("Prueba en 12 s", ml.frase_error(ml.ErrorPuente("tope", "tope", 12)))

    def test_el_bot_no_sabe_donde_vive_el_token(self):
        for archivo in ("mercadolibre.py", "botv3.py"):
            codigo = (BOTV3 / archivo).read_text(encoding="utf-8")
            for prohibido in ("secretos/mercadolibre/vivo", "token.json", "app.json", "client_secret",
                              "refresh_token", "api.mercadolibre.com", "oauth/token"):
                self.assertNotIn(prohibido, codigo, f"{archivo}: {prohibido}")
        dropin = (BOTV3 / "jaime-20-mercadolibre.conf").read_text(encoding="utf-8")
        rutas = [x.split("=", 1)[1] for x in dropin.splitlines() if x.startswith("ReadWritePaths=")]
        self.assertEqual(rutas, ["-/opt/nodo/datos/mercadolibre"])
        perfil = (BOTV3 / "botv3@jaime.service.d" / "10-perfil.conf").read_text(encoding="utf-8")
        self.assertIn("-/opt/nodo/datos/secretos", [x for x in perfil.splitlines()
                                                     if x.startswith("InaccessiblePaths=-")][-1].split())


if __name__ == "__main__":
    unittest.main()
