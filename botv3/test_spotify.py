#!/usr/bin/env python3
"""Pruebas locales de Spotify: no llaman a Telegram ni a Spotify real."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import spotify

RECEPTOR_FIXTURE = json.loads((ROOT / "fixtures/spotify-receptor-v0.10.5.json").read_text())
STATUS_OBLIGATORIOS = {
    "username", "device_id", "device_type", "device_name", "play_origin",
    "play_origin_device_id", "context_uri", "context_name", "stopped", "paused",
    "buffering", "volume", "volume_steps", "repeat_context", "repeat_track",
    "shuffle_context", "track",
}
TRACK_OBLIGATORIOS = {
    "uri", "name", "artist_names", "artist_uris", "album_name", "album_uri",
    "album_cover_url", "position", "duration", "release_date", "track_number",
    "disc_number", "format", "codec", "bitrate", "sample_rate", "bit_depth",
}


class FrasesTests(unittest.TestCase):
    CAPTURA = [
        ("Hola Jaime. Reproducir oxitocina de Billie Eilish en Spotify.", False, "cancion"),
        ("reproduce Oxytocin de Billie Eilish", False, "cancion"),
        ("Pon Oxytocin en Spotify", False, "cancion"),
        ("tócame Bad Guy de Billie Eilish en spotify", False, "cancion"),
        ("Reproduce música de Billie Eilish.", False, "artista"),
        ("reproduce a Billie Eilish en Spotify", False, "artista"),
        ("Pausa la música.", False, "pausa"), ("pausa Spotify", False, "pausa"),
        ("sigue con la música", False, "sigue"), ("pausa", True, "pausa"),
    ]
    NO = ["pon una alarma a las 7", "pon un temporizador de 5 minutos", "pon pausa",
          "agrega leche a la lista", "¿quién canta Oxytocin?", "reproducir la última nota", "compré pan"]

    def test_c1_y_c2(self):
        for texto, sonando, accion in self.CAPTURA:
            with self.subTest(texto=texto): self.assertEqual(spotify.interpretar(texto, sonando)["accion"], accion)
        self.assertIsNone(spotify.interpretar("pausa", False))
        for texto in self.NO:
            with self.subTest(texto=texto): self.assertIsNone(spotify.interpretar(texto, False))

    # 88d (hallazgo 3 de la 88r): «toca …» es «es hora de …» si no se dice Spotify, y un «artista» con posesivo,
    # demostrativo o día no es un artista. Los artículos sí pueden serlo (Los Prisioneros, La Ley).
    NO_88D = ["toca sacar la basura de la cocina", "toca pagar la cuenta de la luz", "Jaime, toca pagar el arriendo de noviembre",
              "Toca regar las plantas de la terraza", "toca comprar leche de almendras", "toca a la puerta",
              "reproduce la última nota de mi proyecto", "reproduce el audio de esta reunión", "reproduce lo de ayer de hoy"]
    SI_88D = [("toca Bad Guy en Spotify", "cancion"), ("tócame Bad Guy de Billie Eilish", "cancion"),
              ("reproduce Tren al sur de Los Prisioneros", "cancion"), ("reproduce Mentira de La Ley", "cancion"),
              ("reproduce la última nota de mi banda en Spotify", "cancion")]

    def test_88d_frases_que_ya_no_roba(self):
        for texto in self.NO_88D:
            for sonando in (False, True):
                with self.subTest(texto=texto, sonando=sonando): self.assertIsNone(spotify.interpretar(texto, sonando))
        for texto, accion in self.SI_88D:
            with self.subTest(texto=texto): self.assertEqual(spotify.interpretar(texto, False)["accion"], accion)

    def test_88d_sigue_a_secas_queda_marcado(self):
        # Hallazgo 5: el bot decide con el estado del receptor; «sigue con la música» no cambia.
        self.assertEqual(spotify.interpretar("sigue", False), {"accion": "sigue", "sola": True})
        self.assertEqual(spotify.interpretar("Continúa.", False), {"accion": "sigue", "sola": True})
        self.assertEqual(spotify.interpretar("sigue con la música", False), {"accion": "sigue"})

    def test_fixture_y_whisper(self):
        datos = json.loads((ROOT / "fixtures/spotify-search-oxytocin.json").read_text())
        elegido = spotify.elegir(datos["tracks"]["items"], "oxitocina", "billi eilish")
        self.assertEqual(elegido["name"], "Oxytocin")
        self.assertEqual(elegido["artists"][0]["name"], "Billie Eilish")

    def test_fixture_receptor_respeta_forma_openapi_v0105(self):
        """C4/C7 usan todos los campos obligatorios del contrato del receptor."""
        for nombre in ("status_sonando", "status_detenido"):
            with self.subTest(nombre=nombre):
                estado = RECEPTOR_FIXTURE[nombre]
                self.assertEqual(set(estado), STATUS_OBLIGATORIOS)
        self.assertEqual(set(RECEPTOR_FIXTURE["status_sonando"]["track"]), TRACK_OBLIGATORIOS)
        self.assertEqual(set(RECEPTOR_FIXTURE["auth_code"]), {"url", "code", "expires_at"})


class ReceptorFalso:
    def __init__(self, sonando=False, registro=None, nombre="receptor"):
        self.sonando, self.llamadas = sonando, []
        padre = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def _enviar(self, codigo=200, datos=None):
                self.send_response(codigo); self.send_header("Content-Type", "application/json"); self.end_headers()
                if datos is not None: self.wfile.write(json.dumps(datos).encode())
            def do_GET(self):
                padre.llamadas.append(("GET", self.path)); padre.registro.append((padre.nombre, "GET", self.path))
                if self.path == "/status":
                    datos = dict(RECEPTOR_FIXTURE["status_sonando" if padre.sonando else "status_detenido"])
                    datos["device_name"] = f"Casa · {padre.nombre.capitalize()}"
                    self._enviar(200, datos)
                elif self.path == "/auth/code": self._enviar(204)
                else: self._enviar(404)
            def do_POST(self):
                padre.llamadas.append(("POST", self.path)); padre.registro.append((padre.nombre, "POST", self.path))
                if self.path == "/player/pause": padre.sonando = False
                if self.path == "/player/play": padre.sonando = True
                self._enviar()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.registro = registro if registro is not None else []
        self.nombre = nombre
        self.hilo = threading.Thread(target=self.http.serve_forever, daemon=True); self.hilo.start()
    @property
    def base(self): return f"http://127.0.0.1:{self.http.server_port}"
    def cerrar(self): self.http.shutdown(); self.http.server_close(); self.hilo.join()


class IntegracionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["BOTV3_STATE_DIR"] = str(Path(cls.tmp.name) / "estado")
        spec = importlib.util.spec_from_file_location("spotify_bot", ROOT / "botv3.py")
        cls.bot = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.bot)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_pausa_otro_antes_de_reproducir(self):
        try:
            orden = []
            jaime, pilar = ReceptorFalso(True, orden, "jaime"), ReceptorFalso(False, orden, "pilar")
        except PermissionError:
            self.skipTest("sandbox sin permiso para bind loopback; la Pi sí ejecuta este servidor local")
        self.addCleanup(jaime.cerrar); self.addCleanup(pilar.cerrar)
        previo, persona, nombre = self.bot.PERFIL_CFG, self.bot.PERSONA, self.bot.NOMBRE
        self.bot.PERFIL_CFG = {"spotify": {"api": pilar.base, "otros": [jaime.base]}}
        self.bot.PERSONA, self.bot.NOMBRE = "Camila", "Pilar"
        enviados = []
        with mock.patch.object(self.bot, "send_text", lambda _, texto: enviados.append(texto)), \
             mock.patch.object(spotify, "buscar", return_value=[{"name": "Oxytocin", "uri": "spotify:track:x", "artists": [{"name": "Billie Eilish"}]}]):
            self.assertTrue(self.bot.atender_spotify(1, "reproduce Oxytocin de Billie Eilish", False))
        self.bot.PERFIL_CFG, self.bot.PERSONA, self.bot.NOMBRE = previo, persona, nombre
        self.assertEqual(jaime.llamadas[-1], ("POST", "/player/pause"))
        self.assertEqual(pilar.llamadas[-1], ("POST", "/player/play"))
        self.assertLess(orden.index(("jaime", "POST", "/player/pause")),
                        orden.index(("pilar", "POST", "/player/play")))
        self.assertIn("▶️ Oxytocin — Billie Eilish · Spotify de Camila", enviados)

    def test_comando_codigo_y_vinculado(self):
        previo = self.bot.PERFIL_CFG
        self.bot.PERFIL_CFG = {"spotify": {"api": "http://127.0.0.1:1", "otros": []}}
        enviados = []
        with mock.patch.object(self.bot.spotify_mod, "estado", return_value=None), \
             mock.patch.object(self.bot.spotify_mod, "codigo", return_value=RECEPTOR_FIXTURE["auth_code"]), \
             mock.patch.object(self.bot, "send_text", lambda _, texto: enviados.append(texto)):
            self.bot.comando_spotify(1)
        self.assertIn("https://www.spotify.com/pair", enviados[0]); self.assertIn("ABCD-EFGH", enviados[0])
        enviados.clear()
        with mock.patch.object(self.bot.spotify_mod, "estado", return_value=RECEPTOR_FIXTURE["status_sonando"]), \
             mock.patch.object(self.bot, "send_text", lambda _, texto: enviados.append(texto)):
            self.bot.comando_spotify(1)
        self.assertIn("vinculado, sonando", enviados[0]); self.assertIn("Oxytocin — Billie Eilish", enviados[0])
        self.bot.PERFIL_CFG = previo

    def test_c2_no_consulta_receptor_y_vocativo_ajeno_no_activa(self):
        previo, nombre = self.bot.PERFIL_CFG, self.bot.NOMBRE
        self.bot.PERFIL_CFG = {"spotify": {"api": "http://127.0.0.1:3678", "otros": ["http://127.0.0.1:3679"]}}
        # El módulo de esta suite carga el perfil Jaime; Pilar es el vocativo ajeno.
        self.bot.NOMBRE = "Jaime"
        frases_c2 = [
            "pon una alarma a las 7", "pon un temporizador de 5 minutos", "pon pausa",
            "agrega leche a la lista", "¿quién canta Oxytocin?", "reproducir la última nota", "compré pan",
        ]
        try:
            with mock.patch.object(self.bot.spotify_mod, "estado") as estado, \
                 mock.patch.object(self.bot.spotify_mod, "buscar") as buscar:
                for texto in frases_c2:
                    with self.subTest(texto=texto): self.assertFalse(self.bot.atender_spotify(1, texto, False))
                self.assertFalse(self.bot.atender_spotify(1, "Hola Pilar. reproduce Oxytocin de Billie Eilish", False))
                self.assertEqual(estado.call_count, 0)
                self.assertEqual(buscar.call_count, 0)
            # La excepción deliberada es «pausa» sola: C2 exige dejarla pasar
            # cuando nada suena, lo que sólo se sabe consultando ambos estados.
            with mock.patch.object(self.bot.spotify_mod, "estado", side_effect=[
                    RECEPTOR_FIXTURE["status_detenido"], RECEPTOR_FIXTURE["status_detenido"]]) as estado:
                self.assertFalse(self.bot.atender_spotify(1, "pausa", False))
                self.assertEqual(estado.call_count, 2)
        finally:
            self.bot.PERFIL_CFG, self.bot.NOMBRE = previo, nombre


class OtroReceptorYSigue88dTests(unittest.TestCase):
    """88d (hallazgos 4 y 5 de la 88r). Los receptores son mocks de spotify.estado: nada abre un socket."""
    @classmethod
    def setUpClass(cls):
        IntegracionTests.setUpClass()
        cls.bot, cls.tmp = IntegracionTests.bot, IntegracionTests.tmp

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def correr(self, texto, estados):
        previo, persona, nombre = self.bot.PERFIL_CFG, self.bot.PERSONA, self.bot.NOMBRE
        self.bot.PERFIL_CFG = {"spotify": {"api": "http://127.0.0.1:3678", "otros": ["http://127.0.0.1:3679"]}}
        self.bot.PERSONA, self.bot.NOMBRE = "Diego", "Jaime"

        def estado(base):
            x = estados[base]
            if isinstance(x, Exception):
                raise x
            return x
        enviados, llamadas = [], []
        try:
            with mock.patch.object(self.bot.spotify_mod, "estado", side_effect=estado), \
                 mock.patch.object(self.bot.spotify_mod, "reproducir", lambda base, uri: llamadas.append(("play", base))), \
                 mock.patch.object(self.bot.spotify_mod, "reanudar", lambda base: llamadas.append(("resume", base))), \
                 mock.patch.object(self.bot.spotify_mod, "pausar", lambda base: llamadas.append(("pause", base))), \
                 mock.patch.object(self.bot.spotify_mod, "buscar", return_value=[{"name": "Oxytocin", "uri": "spotify:track:x", "artists": [{"name": "Billie Eilish"}]}]), \
                 mock.patch.object(self.bot, "send_text", lambda _, t: enviados.append(t)):
                r = self.bot.atender_spotify(1, texto, False)
        finally:
            self.bot.PERFIL_CFG, self.bot.PERSONA, self.bot.NOMBRE = previo, persona, nombre
        return r, enviados, llamadas

    def test_hallazgo_4_el_otro_caido_no_apaga_el_propio(self):
        caido = spotify.SpotifyError("el receptor Spotify no está disponible")
        propio = RECEPTOR_FIXTURE["status_detenido"]
        with self.assertLogs("botv3", "WARNING") as log:
            r, enviados, llamadas = self.correr("reproduce Oxytocin de Billie Eilish",
                                                {"http://127.0.0.1:3678": propio, "http://127.0.0.1:3679": caido})
        self.assertTrue(r)
        self.assertEqual(llamadas, [("play", "http://127.0.0.1:3678")])
        self.assertIn("▶️ Oxytocin — Billie Eilish · Spotify de Diego", enviados)
        self.assertNotIn("127.0.0.1", "\n".join(log.output))          # el log no lleva la URL
        pausado = dict(propio, stopped=False, paused=True)
        r, enviados, llamadas = self.correr("sigue con la música", {"http://127.0.0.1:3678": pausado, "http://127.0.0.1:3679": caido})
        self.assertEqual((r, llamadas), (True, [("resume", "http://127.0.0.1:3678")]))

    def test_hallazgo_4_el_propio_caido_si_se_dice(self):
        caido = spotify.SpotifyError("el receptor Spotify no está disponible")
        r, enviados, llamadas = self.correr("reproduce Oxytocin de Billie Eilish",
                                            {"http://127.0.0.1:3678": caido, "http://127.0.0.1:3679": RECEPTOR_FIXTURE["status_detenido"]})
        self.assertEqual((r, enviados, llamadas), (True, ["No pude usar Spotify ahora."], []))

    def test_hallazgo_5_sigue_a_secas_solo_en_pausa(self):
        detenido = RECEPTOR_FIXTURE["status_detenido"]
        r, enviados, llamadas = self.correr("sigue", {"http://127.0.0.1:3678": detenido, "http://127.0.0.1:3679": detenido})
        self.assertEqual((r, enviados, llamadas), (False, [], []))           # conversación: sigue su camino
        r, _, llamadas = self.correr("sigue", {"http://127.0.0.1:3678": None, "http://127.0.0.1:3679": detenido})
        self.assertEqual((r, llamadas), (False, []))                          # sin vincular tampoco lo toma
        pausado = dict(detenido, stopped=False, paused=True)
        r, enviados, llamadas = self.correr("sigue", {"http://127.0.0.1:3678": pausado, "http://127.0.0.1:3679": detenido})
        self.assertEqual((r, llamadas), (True, [("resume", "http://127.0.0.1:3678")]))
        self.assertIn("▶️ Spotify de Diego sigue.", enviados)


class ErroresYPerfilTests(unittest.TestCase):
    def test_secreto_no_sale_al_fallar(self):
        viejo = dict(os.environ); spotify._TOKEN, spotify._TOKEN_HASTA = "", 0
        os.environ["SPOTIFY_CLIENT_ID"] = "id-prueba-largo-123456"
        os.environ["SPOTIFY_CLIENT_SECRET"] = "sk-PRUEBA-NO-DEBE-SALIR"
        sesion = mock.Mock(); sesion.post.side_effect = spotify.requests.ConnectionError("sk-PRUEBA-NO-DEBE-SALIR")
        with self.assertRaises(spotify.SpotifyError) as error: spotify.buscar({"accion": "cancion", "titulo": "x"}, sesion)
        self.assertNotIn("sk-PRUEBA-NO-DEBE-SALIR", str(error.exception))
        os.environ.clear(); os.environ.update(viejo)

    def test_perfil_remoto_o_https_rechazado(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "jaime.toml").write_text('rutas=["gpt"]\n', encoding="utf-8")
            anterior = os.environ.get("BOTV3_PERFILES_DIR")
            os.environ["BOTV3_PERFILES_DIR"] = tmp
            spec = importlib.util.spec_from_file_location("perfil_spotify_prueba", ROOT / "botv3.py")
            modulo = importlib.util.module_from_spec(spec); spec.loader.exec_module(modulo)
            try:
                for valor in ('http://10.0.0.5:3678', 'https://127.0.0.1:3678'):
                    Path(tmp, "prueba.toml").write_text('rutas=["gpt"]\nspotify={api="' + valor + '"}\n')
                    with self.assertRaises(RuntimeError): modulo.cargar_perfil("prueba")
            finally:
                if anterior is None: os.environ.pop("BOTV3_PERFILES_DIR", None)
                else: os.environ["BOTV3_PERFILES_DIR"] = anterior


if __name__ == "__main__": unittest.main()
