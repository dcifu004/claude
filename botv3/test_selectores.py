#!/usr/bin/env python3
"""Pruebas del encargo 96: selectores dichos («pregunta técnica: …», «pregunta rápida: …», «busca en internet …») y
la cuenta de la ruta técnica (margen, modo fijo, /cuenta_tecnica, gana el último cambio, libro). El bot de verdad
(`handle_message`) con Telegram y los motores simulados; todo en un temporal y sin red.

    python3 botv3/test_selectores.py
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import sys
import tempfile
import types
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
os.environ.setdefault("NODO_PRUEBAS", "1")

if importlib.util.find_spec("requests") is None:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = RuntimeError
    requests_stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

# Nada sale a la red (el modelo es la guarda de test_contador.py, 92b): un intento se anota y la prueba falla.
INTENTOS_DE_RED: list[str] = []
_connect_real = socket.socket.connect


def _sin_red(que):
    def bloqueo(*args, **kwargs):
        INTENTOS_DE_RED.append(que)
        raise OSError(f"test_selectores: {que} bloqueado")
    return bloqueo


def _connect_guardado(self, direccion):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        return _sin_red("socket.connect")(direccion)
    return _connect_real(self, direccion)


socket.socket.connect = _connect_guardado
socket.create_connection = _sin_red("socket.create_connection")
socket.getaddrinfo = _sin_red("socket.getaddrinfo")
urllib.request.urlopen = _sin_red("urllib.request.urlopen")

import recetas  # noqa: E402

CENTINELA = "zz-centinela-pregunta-9731"
AHORA = datetime.now(timezone.utc)
# C5: Claude (Cami) 5 h 80 % / sem 10 %; Claude (Diego) 5 h 20 % / sem 40 %; Codex 5 h 30 % / sem 30 %.
USO_C5 = {"cuentas_interactivo": {
    cid: {"limites": {"ventana_5h": {"usado_pct": h5, "renueva": (AHORA + timedelta(hours=2)).isoformat()},
                      "semanal": {"usado_pct": sem, "renueva": (AHORA + timedelta(days=3)).isoformat()}}}
    for cid, h5, sem in (("claude_cami", 80, 10), ("claude_diego", 20, 40), ("codex", 30, 30))}}
RECETA_JAIME = "\nrecetas = { tecnica = { automatico = true } }\n"     # la línea que escribe aplicar-propuesta


class Base(unittest.TestCase):
    perfil = "jaime"
    receta_jaime = True

    def setUp(self):
        INTENTOS_DE_RED.clear()
        self.addCleanup(self._sin_red)
        self.tmp = Path(tempfile.mkdtemp(prefix="test96-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        perfiles = self.tmp / "perfiles"
        perfiles.mkdir()
        for p in (AQUI / "perfiles").glob("*.toml"):
            texto = p.read_text(encoding="utf-8")
            if p.stem == "jaime" and self.receta_jaime:
                texto += RECETA_JAIME
            (perfiles / p.name).write_text(texto, encoding="utf-8")
        self.uso = self.tmp / "uso.json"
        self.uso.write_text(json.dumps(USO_C5), encoding="utf-8")
        self.registro = self.tmp / "cuentas.toml"
        shutil.copy(AQUI / "cuentas.toml", self.registro)
        self.entorno = {"BOTV3_PERFIL": self.perfil, "BOTV3_PERFILES_DIR": str(perfiles), "BOTV3_STATE_DIR": str(self.tmp / "state"),
                        "BOTV3_USO_CUENTAS": str(self.tmp / "uso-cuentas.jsonl"), "BOTV3_BUSCAR_USO": str(self.tmp / "buscar-uso.jsonl"),
                        "BOTV3_USO_JSON": str(self.uso), "BOTV3_REGISTRO_CUENTAS": str(self.registro),
                        "BOTV3_USO_RUTAS": str(self.tmp / "uso-rutas.json"), "BOTV3_USOS_DIR": str(self.tmp / "usos"),
                        "BOTV3_CASA_DIR": str(self.tmp / "casa"), "BOTV3_REMOTO_DIR": str(self.tmp / "remoto")}
        self.b = self.cargar()

    def _sin_red(self):
        intentos, INTENTOS_DE_RED[:] = list(INTENTOS_DE_RED), []
        self.assertEqual(intentos, [], "la prueba intentó salir a la red")

    def cargar(self):
        previo = {k: os.environ.get(k) for k in self.entorno}
        os.environ.update(self.entorno)
        try:
            spec = importlib.util.spec_from_file_location(f"botv3_96_{id(self)}_{len(previo)}", AQUI / "botv3.py")
            b = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(b)
        finally:
            for k, v in previo.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        b.CHAT_ID = b.USER_ID = 7
        self.enviados, self.consultas, self.busquedas = [], [], []
        b.telegram = lambda metodo, datos=None, *a, **k: (self.enviados.append((metodo, datos)) or {"ok": True})
        b.send_voice = lambda *a, **k: None
        b.sintetizar = lambda texto: None
        b.transcribir_voz = lambda *a, **k: self.dicho
        b.submit_query = b._marcador(lambda ruta, texto="", *a, **k: self.consultas.append((ruta, texto, k)),
                                     b._ruta_de_consulta, False)
        b.SES_SEARXNG = types.SimpleNamespace(get=lambda *a, **k: (self.busquedas.append(k.get("params", {}).get("q")) or
                                                                    types.SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": []})))
        b.sesion_en = lambda ruta, motor, carpeta: True       # todas con login en este bot
        b.tiene_sesion = lambda motor, carpeta: True
        b._CACHE_LIMITES["t"] = None
        return b

    def textos(self):
        return [d.get("text") for m, d in self.enviados if m == "sendMessage" and d]

    def texto(self, t):
        self.b.handle_update({"update_id": 1, "message": {"chat": {"id": 7}, "from": {"id": 7}, "text": t}})

    def voz(self, dicho):
        self.dicho = dicho
        self.b.handle_update({"update_id": 2, "message": {"chat": {"id": 7}, "from": {"id": 7}, "voice": {"file_id": "x", "file_size": 10}}})

    def orden(self, ruta="codex"):
        cadena, eleccion = self.b.orden_de_cuentas(ruta)
        return [c for c, _, _ in cadena], eleccion


class C1C2Frases(Base):
    def test_c1_frases_que_si(self):
        for frase, selector, resto in (
                ("Pregunta técnica: ¿por qué falla el cron?", "tecnica", "¿por qué falla el cron?"),
                ("pregunta tecnica, revisa el log de systemd", "tecnica", "revisa el log de systemd"),
                ("Hola Jaime, pregunta técnica: qué pasa con n8n", "tecnica", "qué pasa con n8n"),
                ("¿Pregunta rápida? cuánto es 15 % de 2300", "rapida", "cuánto es 15 % de 2300"),
                ("Busca en internet precios del G2000", "buscar", "precios del G2000"),
                ("búscame en internet el horario del Jumbo", "buscar", "el horario del Jumbo"),
                ("busca en la web cuándo abre el registro civil", "buscar", "cuándo abre el registro civil"),
                ("una pregunta técnica: por qué no arranca", "tecnica", "por qué no arranca"),
                ("Pregunta rápida. Capital de Uruguay.", "rapida", "Capital de Uruguay.")):
            self.assertEqual(self.b.selector_dicho(frase), (selector, resto), frase)

    def test_c1_vocativo_de_pilar(self):
        self.entorno["BOTV3_PERFIL"] = "pilar"
        b = self.cargar()
        self.assertEqual(b.selector_dicho("Oye Pilar, pregunta rápida: hola"), ("rapida", "hola"))

    def test_c2_frases_que_no(self):
        for frase in ("la pregunta técnica de ayer era otra", "no busques en internet", "falta leche",
                      "temporizador de 10 minutos", "pregúntale a Codex qué hora es", "pregunta tecnicamente hablando",
                      "buscar en internet es fácil", "/tecnica por qué"):
            self.assertEqual(self.b.selector_dicho(frase), (None, frase), frase)

    def test_c2_siguen_su_camino_de_hoy(self):
        self.texto("falta leche")
        self.assertEqual(self.consultas, [])                                  # compras, no una consulta
        self.texto("pregúntale a Codex qué hora es")
        self.assertEqual(self.consultas[-1][:2], ("auto", "qué hora es"))     # 06b, sin selector
        self.assertEqual(self.consultas[-1][2].get("cuenta"), "codex")
        self.assertNotIn("selector", self.consultas[-1][2])

    def test_c2_selector_sin_pregunta_pide_y_no_consulta(self):
        for t, pide in (("pregunta técnica", "¿Cuál es la pregunta técnica?"), ("Busca en internet.", "¿Qué quieres que busque?"),
                        ("pregunta rápida:", "¿Cuál es la pregunta rápida?")):
            self.texto(t)
            self.assertEqual(self.textos()[-1], pide, t)
        self.voz("Pregunta técnica.")
        self.assertEqual(self.textos()[-1], "¿Cuál es la pregunta técnica?")
        self.assertEqual(self.consultas, [])
        self.assertEqual(self.busquedas, [])


class C3C4Destino(Base):
    def test_rutas_y_canal(self):
        self.texto("pregunta técnica: por qué falla el cron")
        self.voz("Pregunta rápida: capital de Uruguay")
        self.assertEqual([(r, t, k.get("selector"), k.get("en_voz", False)) for r, t, k in self.consultas],
                         [("codex", "por qué falla el cron", "tecnica", False), ("gpt", "capital de Uruguay", "rapida", True)])

    def test_c3_rapida_no_crea_un_temporizador(self):
        antes = list(self.b.temporizadores_mod.listar(self.b.PERFIL)) if hasattr(self.b, "temporizadores_mod") and \
            self.b.temporizadores_mod and hasattr(self.b.temporizadores_mod, "listar") else None
        self.texto("pregunta rápida: pon un temporizador de 5 minutos")
        self.voz("Pregunta rápida: pon un temporizador de 5 minutos.")
        self.assertEqual([(r, t) for r, t, _ in self.consultas],
                         [("gpt", "pon un temporizador de 5 minutos"), ("gpt", "pon un temporizador de 5 minutos.")])
        self.assertFalse(any("⏰" in (t or "") or "Temporizador" in (t or "") for t in self.textos()), self.textos())
        if antes is not None:
            self.assertEqual(list(self.b.temporizadores_mod.listar(self.b.PERFIL)), antes)

    def test_buscar_va_al_buscador(self):
        self.texto("busca en internet precios del G2000")
        self.voz("Búscame en internet el horario del Jumbo.")
        self.assertEqual(self.busquedas, ["precios del G2000", "el horario del Jumbo."])
        self.assertEqual(self.consultas, [])

    def test_c4_cuenta_en_la_frase_es_la_06b(self):
        self.texto("pregunta técnica con Codex: por qué falla el cron")
        self.voz("Pregunta técnica, pregúntale a Claude (Cami) qué pasa con n8n")
        self.assertEqual([(r, t, k.get("cuenta")) for r, t, k in self.consultas],
                         [("codex", "por qué falla el cron", "codex"), ("codex", "qué pasa con n8n", "claude_cami")])
        # La 06b va sola y sin respaldo: orden_de_cuentas con forzada devuelve una sola cuenta.
        cadena, eleccion = self.b.orden_de_cuentas("codex", "codex")
        self.assertEqual(([c for c, _, _ in cadena], eleccion["forzada"]), (["codex"], "codex"))

    def test_ruta_que_el_perfil_no_tiene(self):
        modulo = self.b
        modulo.ALLOWED_AUTO_ROUTES = modulo.ALLOWED_AUTO_ROUTES - {"codex"}
        self.texto("pregunta técnica: algo")
        self.assertEqual(self.textos()[-1], "La ruta técnica no corresponde a este bot.")
        self.assertEqual(self.consultas, [])

    def test_hostiles(self):
        largo = "x" * 5000
        self.texto("pregunta técnica: " + largo)
        self.assertEqual(len(self.consultas[-1][1]), self.b.MAX_SELECTOR)
        self.texto("pregunta técnica: /estado")                  # no se ejecuta el comando: es la pregunta
        self.assertEqual(self.consultas[-1][:2], ("codex", "/estado"))
        self.texto("pregunta técnica, pregúntale a")             # «pregúntale a» sin cuenta: va como pregunta
        self.assertEqual(self.consultas[-1][:2], ("codex", "pregúntale a"))
        self.assertEqual(self.b.selector_dicho(None), (None, None))

    def test_contador_registra_el_selector_por_su_punto_unico(self):
        if self.b.REGISTRO_USOS is None:
            self.skipTest("usos.py no está")
        self.texto("pregunta técnica: por qué falla el cron")
        self.voz("busca en internet el horario")
        lineas = [json.loads(x) for p in sorted((self.tmp / "usos").glob("usos-*.jsonl")) for x in p.read_text().splitlines()]
        self.assertEqual([(x["funcion"], x["canal"]) for x in lineas], [("selector:tecnica", "texto"), ("selector:buscar", "voz")])
        self.assertNotIn("cron", json.dumps(lineas))


class C5Margen(Base):
    def test_c5_jaime_con_receta_ordena_por_libre(self):
        orden, eleccion = self.orden()
        self.assertEqual(orden, ["codex", "claude_diego", "claude_cami"])        # libres 70, 60 y 20
        self.assertEqual(eleccion["tecnica"]["modo"], "auto")
        # Las demás rutas no cambian: la de archivos sigue con su cadena.
        self.assertEqual(self.orden("claude")[0], ["claude_diego"])

    def test_c5_pilar_solo_sus_dos(self):
        self.entorno["BOTV3_PERFIL"] = "pilar"
        self.b = self.cargar()
        self.assertEqual(self.orden()[0], ["codex", "claude_cami"])
        self.assertEqual(self.b.elegibles_tecnica(), ["claude_cami", "codex"])

    def test_c5_el_mismo_fixture_en_margen_de(self):
        spec = importlib.util.spec_from_file_location("bots_info_96", AQUI.parent / "pi" / "bots-info.py")
        bi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bi)
        import tomllib
        registro = tomllib.loads(self.registro.read_text(encoding="utf-8"))
        m = bi.margen_de(registro, recetas.limites_de(USO_C5), AHORA, mod=recetas)
        self.assertEqual([c for c in m["orden"] if c in ("codex", "claude_diego", "claude_cami")], ["codex", "claude_diego", "claude_cami"])
        self.assertEqual({c: m["cuentas"][c]["libre_pct"] for c in ("codex", "claude_diego", "claude_cami")},
                         {"codex": 70.0, "claude_diego": 60.0, "claude_cami": 20.0})

    def test_libre_de_y_orden_por_margen(self):
        self.assertEqual(recetas.libre_de({"5h": 80, "semanal": 10}), 20.0)
        self.assertEqual(recetas.libre_de({"5h": None, "semanal": 130}), 0.0)
        self.assertIsNone(recetas.libre_de({}))
        detalle = {"a": {"5h": 10, "semanal": 10, "sobre": True}, "b": {"5h": None, "semanal": None},
                   "c": {"5h": 50, "semanal": 50}, "d": {"5h": 50, "semanal": 50}}
        self.assertEqual(recetas.orden_por_margen(["a", "b", "c", "d"], detalle, ["d", "c", "b", "a"]), ["d", "c", "b", "a"])
        self.assertEqual(recetas.orden_por_margen(["a", "b", "c", "d"], detalle, None, fija="b"), ["b", "c", "d", "a"])
        self.assertEqual(recetas.orden_por_margen(["a", "c"], detalle, None, fija="a"), ["c", "a"])     # fija sobre el umbral


class C6Agotada(Base):
    def correr_tecnica(self, fallan=()):
        def motor(nombre):
            def f(d):
                if nombre in fallan:
                    raise RuntimeError("caído")
                return {"message": "ok", "sources": []}
            return f
        return self.b._correr_cadena("codex", {"codex": motor("codex"), "claude": motor("claude")})

    def test_c6_auto_la_primera_sobre_el_umbral(self):
        texto = self.registro.read_text(encoding="utf-8").replace("[codex]\n", "[codex]\numbral_semanal = 25\n", 1)
        self.registro.write_text(texto.replace("umbral_semanal = 90\numbral_5h = 95\n\n[groq]", "umbral_5h = 95\n\n[groq]"), encoding="utf-8")
        self.b._CACHE_LIMITES["t"] = None
        self.assertEqual(self.orden()[0], ["claude_diego", "claude_cami", "codex"])
        r = self.correr_tecnica()
        self.assertEqual(r["aviso_cuentas"], "🔁 Contestó Claude (Diego): Codex estaba sobre el umbral")

    def test_c6_fija_que_falla_cae_a_la_siguiente(self):
        self.b.guardar_cuenta_tecnica("fija", "claude_cami")
        self.assertEqual(self.orden()[0], ["claude_cami", "codex", "claude_diego"])
        r = self.correr_tecnica(fallan=("claude",))
        self.assertEqual(r["aviso_cuentas"], "🔁 Claude (Cami) falló; contestó Codex")

    def test_c6_fija_sobre_el_umbral(self):
        self.b.guardar_cuenta_tecnica("fija", "claude_cami")
        uso = json.loads(self.uso.read_text())
        uso["cuentas_interactivo"]["claude_cami"]["limites"]["semanal"]["usado_pct"] = 99
        self.uso.write_text(json.dumps(uso))
        self.b._CACHE_LIMITES["t"] = None
        r = self.correr_tecnica()
        self.assertEqual(r["aviso_cuentas"], "🔁 Claude (Cami) está sobre el umbral; contestó Codex")

    def test_la_primera_no_avisa(self):
        self.assertNotIn("aviso_cuentas", self.correr_tecnica())


class C7Telegram(Base):
    def boton(self, data):
        self.b.handle_update({"update_id": 3, "callback_query": {"id": "q", "data": data, "from": {"id": 7},
                                                                  "message": {"chat": {"id": 7}, "message_id": 4}}})

    def teclado(self):
        datos = [d for m, d in self.enviados if m == "sendMessage" and d.get("reply_markup")][-1]
        return [b["callback_data"] for fila in datos["reply_markup"]["inline_keyboard"] for b in fila]

    def test_c7_pilar_no_ve_claude_diego_y_fijar_codex(self):
        self.entorno["BOTV3_PERFIL"] = "pilar"
        self.b = self.cargar()
        self.texto("/cuenta_tecnica")
        self.assertEqual(self.teclado(), ["ct:auto", "ct:claude_cami", "ct:codex"])
        self.boton("ct:claude_diego")                          # no elegible: se rechaza y se dice por qué
        self.assertIn("no puede contestar la ruta técnica", self.textos()[-1])
        self.assertFalse(self.b.CUENTA_TECNICA.exists())
        self.boton("ct:codex")
        ruta = self.b.CUENTA_TECNICA
        self.assertEqual(stat.S_IMODE(ruta.stat().st_mode), 0o600)
        dato = json.loads(ruta.read_text())
        self.assertEqual({k: dato[k] for k in ("modo", "cuenta", "desde")}, {"modo": "fija", "cuenta": "codex", "desde": "telegram"})
        self.assertEqual(dato["perfil_visto"], self.b.huella_tecnica())
        self.assertEqual(sorted(p.name for p in ruta.parent.iterdir()), [".cuenta-tecnica.lock", "cuenta-tecnica.json"])  # sin .tmp
        self.assertEqual(self.orden()[0][0], "codex")
        self.boton("ct:auto")
        self.assertEqual(json.loads(ruta.read_text())["modo"], "auto")

    def test_jaime_ve_las_tres(self):
        self.texto("/cuenta_tecnica")
        self.assertEqual(self.teclado(), ["ct:auto", "ct:codex", "ct:claude_diego", "ct:claude_cami"])   # su cadena y el automático

    def test_escritura_atomica_con_tmp_unico_y_replace(self):
        import inspect
        fuente = inspect.getsource(self.b.guardar_cuenta_tecnica)
        for x in ("fcntl.flock(candado, fcntl.LOCK_EX)", "os.getpid()", "uuid.uuid4().hex", "os.O_EXCL", "os.replace(tmp, CUENTA_TECNICA)", "0o600"):
            self.assertIn(x, fuente)

    def test_estado_hostil_se_ignora_y_se_dice_una_vez(self):
        ruta = self.b.CUENTA_TECNICA
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.assertLogs("botv3", "WARNING") as log:
            for contenido in ("{roto", json.dumps({"modo": "fija", "cuenta": "inventada", "perfil_visto": "x"}), "{roto otra vez"):
                ruta.write_text(contenido)
                self.assertIsNone(self.b.leer_cuenta_tecnica())
                self.assertEqual(self.orden()[0], ["codex", "claude_diego", "claude_cami"])     # rige el perfil
        self.assertEqual(len(log.records), 2)                  # «está roto» y «no tiene la forma esperada», una vez cada uno
        ruta.unlink()
        otro = self.tmp / "otro.json"
        otro.write_text(json.dumps({"modo": "fija", "cuenta": "codex", "perfil_visto": self.b.huella_tecnica()}))
        ruta.symlink_to(otro)
        self.assertIsNone(self.b.leer_cuenta_tecnica())        # un enlace no se sigue


class C8UltimoCambio(Base):
    def test_c8_huella_vieja_se_descarta_avisa_una_vez_y_rige_el_perfil(self):
        self.b.guardar_cuenta_tecnica("fija", "claude_cami")
        self.assertEqual(self.orden()[0][0], "claude_cami")
        # 💳 Cuentas cambia el perfil (otra receta) y la propuesta reinicia el bot.
        perfil = Path(self.entorno["BOTV3_PERFILES_DIR"]) / "jaime.toml"
        perfil.write_text(perfil.read_text().replace(RECETA_JAIME, "\nrecetas = { tecnica = { automatico = true, umbral_semanal = 85 } }\n"))
        self.b = self.cargar()
        self.assertIsNone(self.b.leer_cuenta_tecnica())        # ya no rige
        with self.assertLogs("botv3", "INFO"):
            self.b.revisar_cuenta_tecnica_al_arrancar()
        self.assertEqual([t for t in self.textos() if "💳 Cuentas" in t],
                         ["La cuenta técnica la cambiaste desde 💳 Cuentas; dejé sin efecto la de Telegram."])
        self.assertFalse(self.b.CUENTA_TECNICA.exists())
        self.b.revisar_cuenta_tecnica_al_arrancar()            # otro arranque: no vuelve a avisar
        self.assertEqual(len([t for t in self.textos() if "💳 Cuentas" in t]), 1)
        self.assertEqual(self.orden()[0], ["codex", "claude_diego", "claude_cami"])

    def test_misma_huella_no_se_toca(self):
        self.b.guardar_cuenta_tecnica("fija", "claude_cami")
        self.b = self.cargar()
        self.b.revisar_cuenta_tecnica_al_arrancar()
        self.assertTrue(self.b.CUENTA_TECNICA.exists())
        self.assertEqual(self.textos(), [])

    def test_jaime_sin_receta_es_fija_codex(self):
        self.receta_jaime = False
        Base.setUp(self)
        self.assertEqual(self.b.modo_tecnica(self.b.elegibles_tecnica()), ("fija", "codex", "perfil"))
        self.assertEqual(self.orden()[0], ["codex"])


class C9Libro(Base):
    def test_c9_libro_y_buscar_uso_sin_texto(self):
        b = self.b
        b.submit_query = lambda *a, **k: _submit(b, *a, **k)     # process_query de verdad, en este hilo
        b._vault_codex = lambda prompt, d=None: {"message": "respuesta", "sources": [], "command_suggestion": "", "command_context": ""}
        b._vault_claude = lambda prompt, d=None: {"message": "respuesta", "sources": [], "command_suggestion": "", "command_context": ""}
        b.aplicar_tope = lambda ruta: (ruta, "")
        self.texto(f"pregunta técnica: {CENTINELA}")
        self.voz(f"busca en internet {CENTINELA}")
        libro = [json.loads(x) for x in (self.tmp / "uso-cuentas.jsonl").read_text().splitlines()]
        self.assertEqual([(x["ruta"], x["cuenta"], x["selector"], x["canal"]) for x in libro], [("codex", "codex", "tecnica", "texto")])
        buscar = [json.loads(x) for x in (self.tmp / "buscar-uso.jsonl").read_text().splitlines()]
        self.assertEqual([(x["selector"], x["canal"]) for x in buscar], [("buscar", "voz")])
        for p in self.tmp.rglob("*"):
            if p.is_file():
                self.assertNotIn(CENTINELA, p.read_text(errors="replace"), p)
        # Una consulta sin selector no suma las claves.
        b._PEDIDO.selector = None
        b.anotar_uso_cuenta("codex", "codex", "codex", True, 1.0)
        ultima = json.loads((self.tmp / "uso-cuentas.jsonl").read_text().splitlines()[-1])
        self.assertNotIn("selector", ultima)
        self.assertNotIn("canal", ultima)


def _submit(b, adapter, prompt, en_voz=False, whisper_s=0.0, adjunto=None, cuenta=None, selector=None):
    """submit_query sin la cola de hilos: process_query de verdad, en este hilo (con su semáforo, que libera al final)."""
    b.QUEUE_SLOTS.acquire(blocking=False)
    b.process_query(adapter, prompt, en_voz, whisper_s, adjunto, cuenta, selector)


class D9Lectores(Base):
    def test_bots_info_lee_el_estado_sin_seguir_enlaces(self):
        spec = importlib.util.spec_from_file_location("bots_info_96b", AQUI.parent / "pi" / "bots-info.py")
        bi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bi)
        carpeta = self.tmp / "state"
        self.assertIsNone(bi.cuenta_tecnica_de("jaime", str(carpeta)))
        self.b.guardar_cuenta_tecnica("fija", "codex")
        dato = bi.cuenta_tecnica_de("jaime", str(carpeta))
        self.assertEqual({k: dato[k] for k in ("modo", "cuenta", "desde")}, {"modo": "fija", "cuenta": "codex", "desde": "telegram"})
        (carpeta / "cuenta-tecnica.json").unlink()
        (carpeta / "cuenta-tecnica.json").symlink_to(self.tmp / "uso.json")
        self.assertEqual(bi.cuenta_tecnica_de("jaime", str(carpeta)), {"error": "ilegible"})

    def test_bots_info_lee_el_libro_con_las_claves_nuevas(self):
        spec = importlib.util.spec_from_file_location("bots_info_96c", AQUI.parent / "pi" / "bots-info.py")
        bi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bi)
        carpeta = self.tmp / "estado-jaime"
        carpeta.mkdir()
        lineas = [{"ts": AHORA.isoformat(), "id": "a1b2c3d4e5f6", "perfil": "jaime", "ruta": "codex", "ruta_nombre": "tecnica",
                   "cuenta": "codex", "motor": "codex", "modelo": None, "ok": True, "s": 3.0, "tokens": {"total": 10},
                   "selector": "tecnica", "canal": "voz"},
                  {"ts": AHORA.isoformat(), "id": "a1b2c3d4e5f7", "perfil": "jaime", "ruta": "codex", "ruta_nombre": "tecnica",
                   "cuenta": "claude_diego", "motor": "claude", "modelo": None, "ok": True, "s": 3.0, "tokens": None}]
        (carpeta / "uso-cuentas.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lineas), encoding="utf-8")
        bi.estado_dir = lambda p: str(carpeta)
        eventos = bi.eventos_de_uso(["jaime"], None)
        self.assertEqual([(e[1], e[2]) for e in eventos], [("codex", "jaime/codex"), ("claude_diego", "jaime/codex")])
        self.assertEqual(len(bi._libro_rendimiento(["jaime"])[0]), 2)

    def test_menu_y_ayuda(self):
        from update_telegram_commands import comandos
        self.assertIn("cuenta_tecnica", [c["command"] for c in comandos(["codex"], "pilar")])
        self.assertNotIn("cuenta_tecnica", [c["command"] for c in comandos(["gpt", "web"], "pilar")])
        self.assertIn("«pregunta técnica: …»", self.b.HELP)
        self.assertEqual(self.b.ALIAS_COMANDOS["/cuenta_tecnica"], "cuenta_tecnica")
        self.assertEqual(self.b.PREFIJOS_BOTON["ct"], "cuenta_tecnica")


if __name__ == "__main__":
    unittest.main()
