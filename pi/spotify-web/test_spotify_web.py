#!/usr/bin/env python3
"""Pruebas de spotify-web (encargo 100) con un Chromium FALSO (chromium_falso.py, CDP por los fds 3/4).

    python3 pi/spotify-web/test_spotify_web.py

Ninguna prueba escribe en /opt/nodo/datos (la carpeta de datos y el origen de la CDM se
inyectan en temporales), abre puertos fuera de 127.0.0.1 ni lanza un Chromium real (C8).
El DOM sale de fixtures/dom-tema-2026-10-25.json y la forma de /status, del fixture de
go-librespot de la 88b.
"""
import http.client
import importlib.util
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
FALSO = AQUI / "chromium_falso.py"
DOM = json.loads((AQUI / "fixtures" / "dom-tema-2026-10-25.json").read_text(encoding="utf-8"))
RECEPTOR = json.loads((RAIZ / "botv3" / "fixtures" / "spotify-receptor-v0.10.5.json").read_text(encoding="utf-8"))
OXYTOCIN = "spotify:track:4t2OeILB07eMGTXSUbMPEu"

spec = importlib.util.spec_from_file_location("spotify_web", AQUI / "spotify-web.py")
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)


def cargar_bot():
    """El botv3.py REAL (no una copia de _spotify_suena), cargado como lo carga botv3/test_spotify.py."""
    os.environ.setdefault("BOTV3_STATE_DIR", tempfile.mkdtemp(prefix="sw-botv3-"))
    sys.path.insert(0, str(RAIZ / "botv3"))
    s = importlib.util.spec_from_file_location("spotify_web_bot", RAIZ / "botv3" / "botv3.py")
    bot = importlib.util.module_from_spec(s)
    s.loader.exec_module(bot)
    return bot


class Base(unittest.TestCase):
    """Un controlador con sus datos en un temporal, el Chromium falso y su HTTP en 127.0.0.1:<libre>."""
    ESCENARIO = {}
    RAPIDO = {"espera_boton": 2.0, "espera_suena": 2.0, "paso": 0.05, "terminar": 2.0, "arranque": 30.0}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="spotify-web-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, True))
        self.registro = self.tmp / "registro.jsonl"
        self.cdm = self.tmp / "WidevineCdm" / "gmp-widevinecdm" / "latest"
        self.cdm.mkdir(parents=True)
        (self.cdm / "manifest.json").write_text(json.dumps({"name": "WidevineCdm", "version": "4.10.2662.3"}))
        (self.cdm / "libwidevinecdm.so").write_bytes(b"\x7fELF falso " * 100)
        self.reloj = [1000.0]
        self.ctl = self.controlador(dict(self.ESCENARIO))

    def controlador(self, escenario, **extra):
        esc = self.tmp / f"escenario-{len(list(self.tmp.glob('escenario-*')))}.json"
        esc.write_text(json.dumps({"registro": str(self.registro), **escenario}))
        ctl = sw.Controlador("jaime", datos=self.tmp / "datos", cdm_origen=self.cdm, chromium=[sys.executable, str(FALSO), str(esc)],
                             reloj=lambda: self.reloj[0], sondeo=3600, **{**self.RAPIDO, **extra})
        self.addCleanup(self.cerrar, ctl)
        return ctl

    def cerrar(self, ctl):
        ctl.parar.set()
        ctl.cerrar_navegador()
        srv = getattr(ctl, "_srv", None)
        if srv:
            srv.shutdown()
            srv.server_close()

    def http(self, ctl=None):
        ctl = ctl or self.ctl
        srv = sw.servir(ctl, puerto=0)
        ctl._srv = srv
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        return srv.server_address

    def pedir(self, metodo, ruta, cuerpo=None, direccion=None, crudo=None, cabeceras=None):
        host, puerto = direccion
        c = http.client.HTTPConnection(host, puerto, timeout=5)
        datos = crudo if crudo is not None else (json.dumps(cuerpo).encode() if cuerpo is not None else None)
        t0 = time.monotonic()
        c.request(metodo, ruta, body=datos, headers=cabeceras or ({"Content-Type": "application/json"} if datos else {}))
        r = c.getresponse()
        texto = r.read()
        dt = time.monotonic() - t0
        c.close()
        return r.status, (json.loads(texto) if texto else None), dt

    def eventos(self):
        if not self.registro.exists():
            return []
        return [json.loads(l) for l in self.registro.read_text(encoding="utf-8").splitlines() if l.strip()]

    def esperar(self, cond, plazo=8.0):
        fin = time.monotonic() + plazo
        while time.monotonic() < fin:
            r = cond()
            if r:
                return r
            time.sleep(0.05)
        self.fail("no se cumplió a tiempo")

    def sonando(self, ctl=None):
        ctl = ctl or self.ctl
        return self.esperar(lambda: (ctl.status() or {}).get("track", {}) and not ctl.status()["paused"]
                            and not ctl.status()["buffering"] and ctl.status()["track"]["name"] == "Oxytocin" and ctl.status())


class C1Status(Base):
    def test_sin_sesion_204_y_auth_code_204(self):
        self.ctl.sesion = False
        dire = self.http()
        self.assertEqual(self.pedir("GET", "/status", direccion=dire)[0], 204)
        self.assertEqual(self.pedir("GET", "/auth/code", direccion=dire)[0], 204)

    def test_sesion_desconocida_sale_del_perfil_de_chromium(self):
        self.assertFalse(self.ctl.sesion)                         # sin estado.json ni chromium/Default
        (self.tmp / "datos" / "jaime" / "web" / "chromium" / "Default").mkdir(parents=True)
        self.assertTrue(self.controlador({}).sesion)              # la sesión migrada de la Prueba 0

    def test_sonando_con_la_forma_de_go_librespot_y_spotify_suena_real(self):
        self.ctl.sesion = True
        dire = self.http()
        codigo, _, _ = self.pedir("POST", "/player/play", {"uri": OXYTOCIN}, dire)
        self.assertEqual(codigo, 202)
        self.sonando()
        codigo, st, _ = self.pedir("GET", "/status", direccion=dire)
        self.assertEqual(codigo, 200)
        self.assertEqual((st["stopped"], st["paused"], st["buffering"]), (False, False, False))
        self.assertEqual(st["track"]["name"], "Oxytocin")
        self.assertEqual(st["track"]["artist_names"], ["Billie Eilish"])
        self.assertEqual(st["track"]["uri"], OXYTOCIN)
        self.assertEqual(st["device_name"], "Casa · Jaime")
        self.assertIsNone(st["ultimo_error"])
        # La misma forma que el receptor go-librespot (88b): todas sus claves, más ultimo_error.
        self.assertLessEqual(set(RECEPTOR["status_sonando"]), set(st))
        self.assertLessEqual(set(RECEPTOR["status_sonando"]["track"]), set(st["track"]))
        bot = cargar_bot()
        self.assertTrue(bot._spotify_suena(st))
        self.assertTrue(bot._spotify_suena(RECEPTOR["status_sonando"]))          # control: el fixture de go-librespot
        self.assertFalse(bot._spotify_suena(dict(st, paused=True)))
        # estado.json: atómico, 0600, con el último tema; la carpeta web/, 0700.
        web = self.tmp / "datos" / "jaime" / "web"
        self.assertEqual(json.loads((web / "estado.json").read_text())["ultimo"]["uri"], OXYTOCIN)
        self.assertEqual(stat.S_IMODE((web / "estado.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(web.stat().st_mode), 0o700)
        self.assertEqual(list(web.glob(".*.tmp")), [])

    def test_volumen_501_y_rutas_desconocidas_404(self):
        dire = self.http()
        self.assertEqual(self.pedir("POST", "/player/volume", {"volume": 10}, dire)[0], 501)
        self.assertEqual(self.pedir("GET", "/player/x", direccion=dire)[0], 404)
        self.assertEqual(self.pedir("POST", "/x", {}, dire)[0], 404)


class C2Latencia(Base):
    ESCENARIO = {"arranque_s": 20}

    def test_responde_en_menos_de_500_ms_con_un_chromium_que_tarda_20_s(self):
        self.ctl.sesion = True
        dire = self.http()
        tiempos = {}
        for nombre, (metodo, ruta, cuerpo) in {"status": ("GET", "/status", None), "play": ("POST", "/player/play", {"uri": OXYTOCIN}),
                                                "status-2": ("GET", "/status", None), "pause": ("POST", "/player/pause", None),
                                                "resume": ("POST", "/player/resume", None), "status-3": ("GET", "/status", None)}.items():
            codigo, _, dt = self.pedir(metodo, ruta, cuerpo, dire)
            tiempos[nombre] = dt
            self.assertLess(dt, 0.5, (nombre, dt))
        self.assertEqual(self.pedir("GET", "/status", direccion=dire)[1]["buffering"], True)   # el play sigue en su hilo
        self.esperar(lambda: self.ctl.arrancando is not None, plazo=3)                          # y el navegador todavía arranca
        self.assertIsNone(self.ctl.cdp)
        print(f"\n    C2 (Chromium falso con 20 s de arranque): " + ", ".join(f"{k} {v * 1000:.0f} ms" for k, v in tiempos.items()), file=sys.stderr)


class C3Boton(Base):
    def lista_del_fixture(self):
        primeros = DOM["play_buttons_primeros"]
        tema = {"aria": 'Play', "dentro_de": "action-bar"}
        relleno = [{"aria": "Play <elemento de la biblioteca del usuario>", "dentro_de": "root"}] * (DOM["play_buttons_total"] - len(primeros) - 1)
        return [*primeros, tema, *relleno]

    def test_elige_el_play_exacto_de_la_cabecera_y_no_play_liked_songs(self):
        botones = self.lista_del_fixture()
        self.assertEqual(len(botones), 65)
        self.assertEqual(botones[0]["aria"], "Play Liked Songs")
        self.assertIn('aria-label="Play"', DOM["play_button_tema"])                  # el del tema, tal como vino del DOM real
        i = sw.elegir_boton(botones)
        self.assertEqual(i, 5)
        self.assertEqual(botones[i]["aria"], "Play")
        self.assertIsNone(sw.elegir_boton([b for b in botones if b["aria"] != "Play"]))
        self.assertIsNone(sw.elegir_boton([{"aria": "Play", "dentro_de": "root"}]))   # un «Play» suelto fuera de la cabecera
        self.assertIsNone(sw.elegir_boton("no es una lista"))

    def test_de_punta_a_punta_aprieta_el_del_tema(self):
        self.ctl.sesion = True
        self.ctl.play("track", OXYTOCIN.rsplit(":", 1)[1])
        self.sonando()
        clics = [e for e in self.eventos() if "clic" in e]
        self.assertEqual(clics, [{"clic": 5, "aria": "Play"}])
        nav = [e["params"]["url"] for e in self.eventos() if e.get("metodo") == "Page.navigate"]
        self.assertEqual(nav, ["https://open.spotify.com/track/4t2OeILB07eMGTXSUbMPEu"])

    def test_sin_el_boton_del_tema_no_aprieta_nada(self):
        ctl = self.controlador({"botones": "sin_tema"}, espera_boton=0.6)
        ctl.sesion = True
        ctl.play("track", OXYTOCIN.rsplit(":", 1)[1])
        st = self.esperar(lambda: ctl.status()["ultimo_error"] and ctl.status())
        self.assertEqual(st["ultimo_error"], "Spotify cambió su página web (no encuentro ▶ del tema)")
        self.assertEqual([e for e in self.eventos() if "clic" in e], [])
        self.assertFalse(st["buffering"])


class C4OtroDispositivo(Base):
    ESCENARIO = {"otro": "Casa · Jaime"}

    def test_playing_on_otro_pausa_y_lo_dice(self):
        self.assertEqual(sw.otro_dispositivo("Oxytocin\nPlaying on Casa · Jaime"), "Casa · Jaime")
        self.assertIsNone(sw.otro_dispositivo(DOM["now_playing_bar"]))                # la barra real, sonando aquí
        self.ctl.sesion = True
        self.ctl.play("track", OXYTOCIN.rsplit(":", 1)[1])
        st = self.esperar(lambda: self.ctl.status()["ultimo_error"] and self.ctl.status())
        self.assertEqual(st["ultimo_error"], "Spotify está sonando en otro dispositivo")
        self.assertTrue(st["paused"])
        self.assertIn({"playpause": "Pause", "actual": "Pause"}, self.eventos())     # se pausó de verdad


class C5Cdm(Base):
    def test_arma_la_estructura_de_chromium_y_es_idempotente(self):
        web = self.tmp / "datos" / "jaime" / "web"
        escritos = sw.preparar_cdm(self.cdm, web)
        so = web / "cdm" / "4.10.2662.3" / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
        man = web / "cdm" / "4.10.2662.3" / "manifest.json"
        pista = web / "chromium" / "WidevineCdm" / "latest-component-updated-widevine-cdm"
        self.assertEqual(set(escritos), {str(so), str(man), str(pista)})
        self.assertEqual(sw.sha256(so), sw.sha256(self.cdm / "libwidevinecdm.so"))
        self.assertEqual(sw.sha256(man), sw.sha256(self.cdm / "manifest.json"))
        self.assertEqual(json.loads(pista.read_text()), {"Path": str(web / "cdm" / "4.10.2662.3")})
        for archivo in (so, man, pista):
            self.assertEqual(stat.S_IMODE(archivo.stat().st_mode), 0o600, archivo)
        for carpeta in (web / "cdm", so.parent, pista.parent):
            self.assertEqual(stat.S_IMODE(carpeta.stat().st_mode), 0o700, carpeta)
        antes = {p: p.stat().st_mtime_ns for p in (so, man, pista)}
        time.sleep(0.02)
        self.assertEqual(sw.preparar_cdm(self.cdm, web), [])                          # segunda corrida: nada
        self.assertEqual({p: p.stat().st_mtime_ns for p in (so, man, pista)}, antes)
        (self.cdm / "libwidevinecdm.so").write_bytes(b"\x7fELF otra version")          # cambió el .so: se recopia
        self.assertEqual(sw.preparar_cdm(self.cdm, web), [str(so)])
        self.assertEqual(sw.sha256(so), sw.sha256(self.cdm / "libwidevinecdm.so"))
        self.assertEqual([p for p in web.rglob("*") if p.name.endswith(".tmp")], [])

    def test_version_hostil_no_arma_rutas(self):
        (self.cdm / "manifest.json").write_text(json.dumps({"version": "../../x"}))
        with self.assertRaises(RuntimeError):
            sw.preparar_cdm(self.cdm, self.tmp / "web")
        self.assertFalse((self.tmp / "web" / "cdm").exists())


class C6Inactividad(Base):
    def test_cierra_tras_15_min_en_pausa_y_resume_lo_reabre(self):
        self.ctl.sesion = True
        self.ctl.play("track", OXYTOCIN.rsplit(":", 1)[1])
        self.sonando()
        proc = self.ctl.cdp.proc
        self.ctl.pause()
        self.esperar(lambda: self.ctl.status()["paused"] and not self.ctl.orden.locked())
        self.ctl.tick()                                           # marca desde cuándo está quieto
        self.reloj[0] += 14 * 60
        self.ctl.tick()
        self.assertIsNone(proc.poll())                            # 14 min: sigue abierto
        self.reloj[0] += 60
        self.ctl.tick()                                           # 15 min: se cierra
        self.assertIsNotNone(proc.poll())
        self.assertIsNone(self.ctl.cdp)
        st = self.ctl.status()
        self.assertTrue(st["stopped"])
        self.assertEqual(st["track"]["name"], "Oxytocin")         # con el último tema
        self.ctl.resume()                                         # vuelve a abrir y pone el último tema
        self.sonando()
        self.assertIsNot(self.ctl.cdp.proc, proc)
        self.assertEqual(len([e for e in self.eventos() if "argv" in e]), 2)

    def test_pause_con_el_navegador_cerrado_no_lo_abre(self):
        self.ctl.sesion = True
        self.ctl.pause()
        self.ctl.resume()                                         # sin último tema: tampoco
        time.sleep(0.3)
        self.assertEqual(self.eventos(), [])


class C7Hostil(Base):
    def test_uris_y_cuerpos_hostiles_dan_400_sin_navegar(self):
        self.ctl.sesion = True
        dire = self.http()
        malos = [{"uri": "spotify:track:../../x"}, {"uri": "spotify:track:" + "a" * 23}, {"uri": "spotify:track:" + "a" * 21},
                 {"uri": "javascript:alert(1)"}, {"uri": "spotify:playlist:" + "a" * 22}, {"uri": "spotify:track:4t2OeILB07eMGTXSUbMPE'"},
                 {"uri": ["spotify:track:4t2OeILB07eMGTXSUbMPEu"]}, {"uri": 7}, {}, [], "spotify:track:4t2OeILB07eMGTXSUbMPEu",
                 {"uri": OXYTOCIN + "\n"}]
        for cuerpo in malos:
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(self.pedir("POST", "/player/play", cuerpo, dire)[0], 400)
        for crudo in (b"{no es json", b"\xff\xfe", json.dumps({"uri": OXYTOCIN, "x": "a" * 5000}).encode()):
            with self.subTest(crudo=crudo[:20]):
                self.assertEqual(self.pedir("POST", "/player/play", direccion=dire, crudo=crudo)[0], 400)
        time.sleep(0.2)
        self.assertEqual(self.eventos(), [])                     # ni siquiera se abrió el navegador
        self.assertIsNone(self.ctl.cdp)
        self.assertEqual(sw.validar_uri(json.dumps({"uri": OXYTOCIN}).encode()), ("track", "4t2OeILB07eMGTXSUbMPEu"))
        self.assertEqual(sw.validar_uri(b'{"uri": "spotify:artist:6qqNVTkY8uBg9cP3Jd7DAH"}'), ("artist", "6qqNVTkY8uBg9cP3Jd7DAH"))

    def test_la_uri_nunca_entra_al_javascript(self):
        for js in (sw.JS_LEER, sw.JS_BOTONES, sw.JS_CLIC, sw.JS_PLAYPAUSE):
            self.assertNotIn("uri", js.lower())
        fuente = (AQUI / "spotify-web.py").read_text(encoding="utf-8")
        self.assertIn('cdp.evaluar(JS_CLIC.replace("{indice}", str(int(i))))', fuente)
        self.assertEqual(fuente.count("JS_CLIC.replace("), 1)
        self.assertEqual(fuente.count("JS_PLAYPAUSE.replace("), 2)
        self.assertEqual(fuente.count('json.dumps("Pause")') + fuente.count("json.dumps(quiero)"), 2)


class C8Aislamiento(Base):
    def test_datos_inyectados_loopback_y_chromium_falso_por_pipe(self):
        self.assertEqual(sw.DATOS, Path("/opt/nodo/datos/spotify"))
        self.assertTrue(str(self.ctl.web).startswith(str(self.tmp)))
        self.assertEqual(self.http()[0], "127.0.0.1")
        self.ctl.sesion = True
        self.ctl.play("track", OXYTOCIN.rsplit(":", 1)[1])
        self.sonando()
        argv = next(e["argv"] for e in self.eventos() if "argv" in e)
        for bandera in ("--headless=new", "--remote-debugging-pipe", "--autoplay-policy=no-user-gesture-required", "--no-first-run", "--window-size=1280,800"):
            self.assertIn(bandera, argv)
        self.assertFalse(any(a.startswith("--remote-debugging-port") for a in argv))
        self.assertIn(f"--user-data-dir={self.ctl.web / 'chromium'}", argv)
        self.assertTrue(all(e.get("sesion") in (None, "S1") for e in self.eventos() if "metodo" in e))

    def test_vincular_se_niega_si_el_servicio_esta_activo(self):
        ocupado = socket.socket()
        try:
            ocupado.bind(("127.0.0.1", sw.PUERTOS["jaime"]))
            ocupado.listen()
        except OSError:
            pass                                                  # ya está ocupado (p. ej. el receptor real): sirve igual
        self.addCleanup(ocupado.close)
        self.ctl.chromium = ["/ruta/que/no/existe"]               # si intentara lanzar, explotaría
        self.assertEqual(sw.vincular(self.ctl, plazo=1), 2)
        self.assertFalse((self.ctl.web / "estado.json").exists())

    def test_hay_sesion_cuando_la_pagina_volvio_a_open_spotify(self):
        self.assertFalse(sw.hay_sesion_en([{"type": "page", "url": sw.LOGIN}]))
        self.assertTrue(sw.hay_sesion_en([{"type": "page", "url": "https://open.spotify.com/"}]))
        self.assertFalse(sw.hay_sesion_en([{"type": "service_worker", "url": "https://open.spotify.com/sw.js"}]))
        self.assertFalse(sw.hay_sesion_en("x"))


class LecturaTests(unittest.TestCase):
    def test_parsear_ahora_y_tiempos(self):
        aria = next(x for x in DOM["now_playing_bar"].split('"') if x.startswith("Now playing: "))
        self.assertEqual(sw.parsear_ahora(aria), ("Oxytocin", ["Billie Eilish"]))
        self.assertEqual(sw.parsear_ahora("Now playing: Under Pressure by Queen, David Bowie"), ("Under Pressure", ["Queen", "David Bowie"]))
        self.assertEqual(sw.parsear_ahora(None), (None, []))
        self.assertEqual((sw.a_ms("3:30"), sw.a_ms("1:02:03"), sw.a_ms("x"), sw.a_ms(None)), (210000, 3723000, 0, 0))

    def test_la_unidad(self):
        u = (AQUI / "spotify-web@.service").read_text(encoding="utf-8")
        for linea in ("Conflicts=spotify@%i.service", "After=pipewire-pulse.service", "Wants=pipewire-pulse.service",
                      "ConditionPathIsDirectory=/opt/nodo/datos/spotify/%i", "ExecStart=/usr/local/bin/spotify-web --perfil %i",
                      "Restart=on-failure", "RestartSec=10", "MemoryMax=1800M", "NoNewPrivileges=yes", "WantedBy=default.target"):
            self.assertIn(linea + "\n", u)
        directivas = "\n".join(l for l in u.splitlines() if l and not l.startswith("#"))
        for prohibido in ("PrivateNetwork", "RestrictNamespaces", "ProtectHome=yes", "remote-debugging-port"):
            self.assertNotIn(prohibido, directivas)


if __name__ == "__main__":
    unittest.main()
