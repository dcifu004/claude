#!/usr/bin/env python3
"""Pruebas del encargo 97: una sola salida con canal (M2: telegram, voz_telegram y sala) y «qué puedes
hacer» (M4). El bot de verdad (`handle_update` y `atender_dicho`) con Telegram, Piper y los motores
simulados; la carpeta de la sala (`VOZ_PARLANTE_DIR`) es un temporal fijado ANTES de cargar el módulo.
Sin red: la guarda de test_contador.py (92b) hace fallar la prueba que intente conectarse.

    python3 botv3/test_sala.py
"""
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock
import urllib.request

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
os.environ.setdefault("NODO_PRUEBAS", "1")

if importlib.util.find_spec("requests") is None:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = RuntimeError
    requests_stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

INTENTOS_DE_RED: list[str] = []
_connect_real = socket.socket.connect


def _sin_red(que):
    def bloqueo(*args, **kwargs):
        INTENTOS_DE_RED.append(que)
        raise OSError(f"test_sala: {que} bloqueado")
    return bloqueo


def _connect_guardado(self, direccion):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        return _sin_red("socket.connect")(direccion)
    return _connect_real(self, direccion)


socket.socket.connect = _connect_guardado
socket.create_connection = _sin_red("socket.create_connection")
socket.getaddrinfo = _sin_red("socket.getaddrinfo")
urllib.request.urlopen = _sin_red("urllib.request.urlopen")

CENTINELA = "zz-centinela-secreto-9797"
NOMBRE_JSON = re.compile(r"^\d{8}-\d{6}-\d{6}-(jaime|pilar)-[0-9a-f]{12}\.json$")
ES_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0

# El texto de M4 aprobado por Diego el 25-10-2026 (encargo 97, «Texto de M4»).
HABLADO_JAIME = ("Puedo poner temporizadores y alarmas, anotar en la lista de compras, decirte la hora, el clima y "
                 "tu agenda, y contestar preguntas. Te dejé la lista completa en el chat.")
HABLADO_PILAR = ("Puedo poner temporizadores y alarmas, anotar compras y gastos, decirte la hora y el clima, y "
                 "contestar preguntas. Te dejé la lista completa en el chat.")
CHAT_M4 = """Esto puedo hacer, escrito o por voz:

⏰ Temporizadores y alarmas — «temporizador de 10 minutos para los tallarines»
🔁 Órdenes que se repiten — «despiértame de lunes a viernes a las 6:30»
🛒 Compras — «falta leche», «qué hay en la lista»
[💳 Gastos — «anota un gasto de 15 lucas en la feria» (se confirma acá)]
[📅 Agenda y correo — «qué tengo mañana», «tengo correos nuevos»]
🌦️ Clima y hora — «va a llover hoy», «qué hora es»
[🎵 Spotify — «pon música»]
🩺 El nodo — «cómo está la Pi»

Para elegir quién contesta, empieza con:
🧠 «pregunta técnica: …» — la cuenta con más margen
🔎 «busca en internet: …» — hasta 5 enlaces
⚡ «pregunta rápida: …» — respuesta corta

Todo con botones: /menu · Detalle: /ayuda"""


def chat_m4(gastos: bool, agenda: bool, spotify: bool) -> str:
    """El texto aprobado, con las líneas entre corchetes según su condición."""
    salida = []
    for linea in CHAT_M4.split("\n"):
        if linea.startswith("["):
            quiere = {"💳": gastos, "📅": agenda, "🎵": spotify}[linea[1]]
            if quiere:
                salida.append(linea[1:-1])
            continue
        salida.append(linea)
    return "\n".join(salida)


def resultado(ruta, mensaje, **extra):
    return {"route": ruta, "message": mensaje, "sources": [], "command_suggestion": "",
            "command_context": "", **extra}


class Base(unittest.TestCase):
    perfil = "jaime"
    quitar_rutas: tuple = ()

    def setUp(self):
        INTENTOS_DE_RED.clear()
        self.addCleanup(self._sin_red)
        self.tmp = Path(tempfile.mkdtemp(prefix="test97-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.sala = self.tmp / "parlante"
        self.sala.mkdir()
        perfiles = self.tmp / "perfiles"
        perfiles.mkdir()
        for p in (AQUI / "perfiles").glob("*.toml"):
            texto = p.read_text(encoding="utf-8")
            for ruta in self.quitar_rutas:
                texto = texto.replace(f', "{ruta}"', "").replace(f'"{ruta}", ', "")
            (perfiles / p.name).write_text(texto, encoding="utf-8")
        self.entorno = {"BOTV3_PERFILES_DIR": str(perfiles), "BOTV3_STATE_DIR": str(self.tmp / "state"),
                        "BOTV3_USO_CUENTAS": str(self.tmp / "uso-cuentas.jsonl"),
                        "BOTV3_BUSCAR_USO": str(self.tmp / "buscar-uso.jsonl"),
                        "BOTV3_USO_JSON": str(self.tmp / "uso.json"),
                        "BOTV3_REGISTRO_CUENTAS": str(AQUI / "cuentas.toml"),
                        "BOTV3_USO_RUTAS": str(self.tmp / "uso-rutas.json"), "BOTV3_USOS_DIR": str(self.tmp / "usos"),
                        "BOTV3_CASA_DIR": str(self.tmp / "casa"), "BOTV3_REMOTO_DIR": str(self.tmp / "remoto"),
                        "BOTV3_ML_SOCKET": str(self.tmp / "ml.sock"), "BOTV3_ML_DIR": str(self.tmp / "ml"),
                        "VOZ_PARLANTE_DIR": str(self.sala)}
        self.b = self.cargar(self.perfil)
        # compras.py y temporizadores.py se importan una sola vez (sys.modules) y se quedarían con la
        # casa de la primera prueba: cada una los apunta a la suya, y así tampoco quedan restos en /tmp.
        casa = self.tmp / "casa"
        for modulo, nombres in ((self.b.compras_mod, {"LISTA": "compras.json", "LOCK": ".compras.lock", "BUZON": "buzon"}),
                                (self.b.temporizadores_mod, {"ARCHIVO": "temporizadores.json", "LOCK": ".temporizadores.lock"})):
            if modulo is not None:
                parche = mock.patch.multiple(modulo, CASA_DIR=casa, **{k: casa / v for k, v in nombres.items()})
                parche.start()
                self.addCleanup(parche.stop)

    def _sin_red(self):
        intentos, INTENTOS_DE_RED[:] = list(INTENTOS_DE_RED), []
        self.assertEqual(intentos, [], "la prueba intentó salir a la red")

    def cargar(self, perfil):
        entorno = {**self.entorno, "BOTV3_PERFIL": perfil}
        previo = {k: os.environ.get(k) for k in entorno}
        os.environ.update(entorno)
        try:
            spec = importlib.util.spec_from_file_location(f"botv3_97_{perfil}_{id(self)}", AQUI / "botv3.py")
            b = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(b)
        finally:
            for k, v in previo.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        b.CHAT_ID = b.USER_ID = 7
        self.enviados, self.voz, self.notas, self.consultas = [], [], [], []
        b.telegram = lambda metodo, datos=None, *a, **k: (self.enviados.append((metodo, datos)) or {"ok": True})
        b.sintetizar = lambda texto: (self.voz.append(texto) or b"ogg")
        b.send_voice = lambda chat, audio: self.notas.append(audio)
        b.transcribir_voz = lambda *a, **k: self.dicho
        b.audit = lambda *a, **k: None
        # Las consultas corren en este hilo, con un motor falso que anota en el libro como una cuenta real.
        b.WORKERS = types.SimpleNamespace(submit=lambda f, *a: f(*a))

        def ejecutar(ruta, prompt, *a):
            self.consultas.append((ruta, prompt))
            b.anotar_uso_cuenta(ruta, "codex", "codex", True, 1.0)
            return self.respuesta(ruta, prompt)
        b.ejecutar_ruta = ejecutar
        b.auto_query = lambda prompt: ejecutar("gpt", prompt)
        self.respuesta = lambda ruta, prompt: resultado(ruta, "Respuesta corta.")
        b.SES_SEARXNG = types.SimpleNamespace(get=lambda *a, **k: types.SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: {"results": [
                {"title": "G2000", "url": "https://ejemplo.cl/g2000", "content": CENTINELA}]}))
        return b

    # -- ayudas --
    def textos(self):
        return [d.get("text") for m, d in self.enviados if m == "sendMessage" and d]

    def texto(self, t):
        self.b.handle_update({"update_id": 1, "message": {"chat": {"id": 7}, "from": {"id": 7}, "text": t}})

    def nota(self, dicho):
        self.dicho = dicho
        self.b.handle_update({"update_id": 2, "message": {"chat": {"id": 7}, "from": {"id": 7},
                                                          "voice": {"file_id": "x", "file_size": 10}}})

    def jsons(self, borrar=True):
        archivos = sorted(self.sala.iterdir())
        datos = []
        for f in archivos:
            self.assertRegex(f.name, NOMBRE_JSON, "ni .tmp sueltos ni nombres raros en la carpeta de la sala")
            datos.append(json.loads(f.read_text(encoding="utf-8")))
            if borrar:
                f.unlink()
        return datos

    def dichos(self):
        return [d["texto"] for d in self.jsons()]

    def limpiar(self):
        self.enviados.clear(), self.voz.clear(), self.notas.clear(), self.jsons()


class C1Canales(Base):
    def test_hora_por_los_tres_canales(self):
        hora = self.b.respuesta_hora("hora", self.b.ahora_santiago())
        self.texto("qué hora es")
        self.assertEqual(len(self.textos()), 1)
        self.assertRegex(self.textos()[0], r"^Son las ")
        self.assertEqual((self.voz, self.notas, self.jsons()), ([], [], []), "telegram: sólo texto")

        self.limpiar()
        self.nota("¿Qué hora es?")
        self.assertEqual(self.textos()[0], "🎤 Entendí: ¿Qué hora es?")
        self.assertRegex(self.textos()[1], r"^Son las ")
        self.assertEqual(len(self.voz), 1)
        self.assertEqual(self.voz[0], self.textos()[1])
        self.assertEqual(self.notas, [b"ogg"])
        self.assertEqual(self.jsons(), [], "voz_telegram: texto y nota de voz, nada a la sala")

        self.limpiar()
        self.b.atender_dicho("Jaime, ¿qué hora es?")
        archivos = list(self.sala.iterdir())
        self.assertEqual(len(archivos), 1)
        self.assertEqual(stat.S_IMODE(archivos[0].stat().st_mode), 0o640)
        (d,) = self.jsons()
        self.assertEqual(set(d), {"perfil", "texto", "voz", "prioridad", "ts", "id", "tipo"})
        self.assertEqual((d["perfil"], d["voz"], d["prioridad"], d["tipo"]),
                         ("jaime", "es_ES-davefx-medium", "normal", "respuesta"))
        self.assertRegex(d["texto"], r"^Son las ")
        self.assertEqual(d["texto"][:8], hora[:8])
        self.assertIn(d["id"], archivos[0].name)
        self.assertEqual(self.textos(), [], "la sala lo dijo entero: no hace falta el chat")
        self.assertEqual((self.voz, self.notas), ([], []), "la sala no sintetiza ni manda notas de voz")

    def test_ruta_rapida_por_la_sala_se_dice_y_el_detalle_queda_en_el_chat(self):
        self.b.atender_dicho("cuál es la capital de Uruguay")
        self.assertEqual(self.dichos(), ["Respuesta corta."])
        self.assertTrue(any("Ruta: gpt" in t for t in self.textos()), "la ruta y las fuentes quedan escritas")
        self.assertEqual(self.notas, [])

    def test_responder_reparte_los_botones_en_el_ultimo_trozo(self):
        teclado = {"inline_keyboard": [[{"text": "👍", "callback_data": "cal:1:x"}]]}
        for origen in ("telegram", "voz_telegram", "sala"):
            with self.subTest(origen=origen):
                self.limpiar()
                self.b.responder(origen, 7, "a" * 9000, "Hola.", botones=teclado)
                mensajes = [d for m, d in self.enviados if m == "sendMessage"]
                self.assertGreater(len(mensajes), 1)
                self.assertEqual([("reply_markup" in d) for d in mensajes], [False] * (len(mensajes) - 1) + [True])
                self.assertEqual(self.dichos(), ["Hola."] if origen == "sala" else [])
                self.assertEqual(self.voz, ["Hola."] if origen == "voz_telegram" else [])


class C2Gobernadas(Base):
    def consulta_sala(self, ruta, mensaje, **extra):
        self.respuesta = lambda r, p: resultado(ruta, mensaje, **extra)
        self.assertTrue(self.b.QUEUE_SLOTS.acquire(blocking=False))
        self.b.process_query(ruta, "pregunta", en_voz=True, origen="sala")

    def test_google_y_boleta_por_la_sala_no_dicen_su_contenido(self):
        # Ni con la llave de la nota de voz privada ni aunque la ruta contestara rápido: así lo que se
        # prueba es la guarda de la sala en responder(), no la de decidir_voz.
        self.b.VOZ_HABLA_VAULT = True
        self.b.RUTAS_EN_VOZ = {"gpt", "ha", "google", "boleta"}
        for ruta in ("google", "boleta"):
            with self.subTest(ruta=ruta):
                self.limpiar()
                self.consulta_sala(ruta, f"Reunión {CENTINELA} a las 10")
                (d,) = self.jsons(borrar=False)
                self.assertEqual(d["texto"], "Te lo mando al chat.")
                self.assertNotIn(CENTINELA, json.dumps(self.jsons()))
                self.assertTrue(any(CENTINELA in t for t in self.textos()), "el texto va a Telegram")
        # Por contraste: la nota de voz privada sí la dice con VOZ_HABLA_VAULT si la ruta fuera rápida.
        self.limpiar()
        self.b.RUTAS_EN_VOZ = {"gpt", "ha", "google"}
        self.respuesta = lambda r, p: resultado("google", "Agenda corta.")
        self.assertTrue(self.b.QUEUE_SLOTS.acquire(blocking=False))
        self.b.process_query("google", "pregunta", en_voz=True)
        self.assertEqual(self.voz, ["Agenda corta."])

    def test_frase_fija_sin_datos_si_se_dice(self):
        self.consulta_sala("google", f"Propuesta {CENTINELA}", frase_hablada=self.b.EVENTO_DICHO)
        self.assertEqual(self.dichos(), [self.b.EVENTO_DICHO])
        self.assertTrue(any(CENTINELA in t for t in self.textos()))

    def test_lenta_por_la_sala(self):
        self.consulta_sala("claude", "Respuesta del vault.")
        self.assertEqual(self.dichos(), ["Te lo mando al chat."])

    def test_gasto_por_la_sala_no_dice_el_monto(self):
        self.assertTrue(self.b._gastos_activos())
        self.b.atender_dicho("anota un gasto de 15 lucas en la feria")
        dichos = self.dichos()
        self.assertEqual(dichos, [self.b.GASTO_DICHO])
        self.assertNotRegex(json.dumps(dichos), r"15|lucas|feria")
        self.assertTrue(any("15" in t for t in self.textos()), "la propuesta con su ✅ queda en el chat")
        # Sin propuesta (sin frase), la sala no improvisa: «Te lo mando al chat.» y el detalle por escrito.
        self.b.atender_gasto_texto = lambda chat_id, linea: (f"❌ No entendí el gasto de 15 lucas {CENTINELA}", None)
        self.b.atender_dicho("anota un gasto de 15 lucas en la feria")
        self.assertEqual(self.dichos(), ["Te lo mando al chat."])

    def test_busqueda_por_la_sala_no_dice_enlaces(self):
        self.b.atender_dicho("busca en internet precios del G2000")
        self.assertEqual(self.dichos(), ["Te lo mando al chat."])
        self.assertTrue(any("ejemplo.cl" in t for t in self.textos()))

    def test_falla_de_la_consulta_no_deja_la_sala_muda(self):
        def falla(r, p):
            raise RuntimeError("se cayó")
        self.respuesta = falla
        self.b.atender_dicho("cuál es la capital de Mongolia")
        self.assertEqual(self.dichos(), ["Te lo mando al chat."])
        self.assertTrue(any(t.startswith("❌ No pude completar la consulta") for t in self.textos()))

    def test_cola_llena_no_deja_la_sala_muda(self):
        lleno = "Hay demasiadas consultas en espera. Intenta nuevamente en un momento."
        tomados = 0
        while self.b.QUEUE_SLOTS.acquire(blocking=False):
            tomados += 1
        self.addCleanup(lambda: [self.b.QUEUE_SLOTS.release() for _ in range(tomados)])
        for dicho in ("pregunta técnica: por qué falla el cron", "cuál es la capital de Mongolia"):
            with self.subTest(dicho=dicho):
                self.limpiar()
                self.b.atender_dicho(dicho)
                self.assertEqual(self.dichos(), [lleno])
                self.assertEqual(self.textos(), [lleno], "el chat lo conserva")
                self.assertEqual(self.consultas, [])
        # Por la nota de voz y por texto, igual que antes: sólo el texto, sin audio ni sala.
        self.limpiar()
        self.nota("cuál es la capital de Mongolia")
        self.texto("cuál es la capital de Mongolia")
        self.assertEqual(self.textos(), ["🎤 Entendí: cuál es la capital de Mongolia", lleno, lleno])
        self.assertEqual((self.voz, self.notas, self.jsons()), ([], [], []))


class C3Atomico(Base):
    def test_escrituras_simultaneas_no_se_pisan(self):
        pilar = self.cargar("pilar")
        barrera = threading.Barrier(4)

        def escribir(modulo, n):
            barrera.wait()
            for i in range(25):
                self.assertTrue(modulo.escribir_sala(f"frase {n}-{i}"))
        hilos = [threading.Thread(target=escribir, args=(m, n)) for n, m in enumerate((self.b, pilar, self.b, pilar))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        datos = self.jsons()
        self.assertEqual(len(datos), 100)
        self.assertEqual(len({d["id"] for d in datos}), 100)
        self.assertEqual(sorted(d["texto"] for d in datos), sorted(f"frase {n}-{i}" for n in range(4) for i in range(25)))
        self.assertEqual({d["perfil"] for d in datos}, {"jaime", "pilar"})
        self.assertEqual(list(self.sala.iterdir()), [], "sin .tmp sueltos")

    def _no_se_puede(self, preparar):
        preparar()
        with self.assertLogs("botv3", logging.WARNING) as registro:
            for _ in range(3):
                self.b.atender_dicho("qué hora es")
        avisos = [r for r in registro.output if "sala: no pude escribir" in r]
        self.assertEqual(len(avisos), 1, "se anota una sola vez")
        textos = self.textos()
        self.assertEqual(sum(t.startswith("🔇 No pude hablar por la sala") for t in textos), 1)
        self.assertEqual(sum(t.startswith("Son las ") for t in textos), 3, "Telegram contesta las tres")

    def test_carpeta_que_no_existe(self):
        self._no_se_puede(lambda: setattr(self.b, "VOZ_PARLANTE_DIR", self.tmp / "no-existe"))
        self.assertFalse((self.tmp / "no-existe").exists(), "el bot no crea la carpeta de la sala")

    def test_carpeta_enlace_simbolico(self):
        enlace = self.tmp / "enlace"
        enlace.symlink_to(self.sala)
        self._no_se_puede(lambda: setattr(self.b, "VOZ_PARLANTE_DIR", enlace))
        self.assertEqual(list(self.sala.iterdir()), [])

    @unittest.skipIf(ES_ROOT, "root escribe en una carpeta 0555")
    def test_carpeta_sin_permiso_y_vuelve(self):
        self.addCleanup(os.chmod, self.sala, 0o755)
        self._no_se_puede(lambda: os.chmod(self.sala, 0o555))
        os.chmod(self.sala, 0o755)
        self.enviados.clear()
        self.b.atender_dicho("qué hora es")
        self.assertEqual(len(self.jsons()), 1)
        self.assertEqual(self.textos(), [])
        # Una falla nueva, después de andar, se vuelve a decir una vez.
        os.chmod(self.sala, 0o555)
        self.b.atender_dicho("qué hora es")
        self.assertEqual(sum(t.startswith("🔇") for t in self.textos()), 1)

    def _write_corto(self, cuantos):
        """os.write real, pero que escribe sólo `cuantos(n)` de los n bytes que le piden (como POSIX
        permite ante una señal, cuota o disco lleno). Sólo para los .tmp de la sala."""
        write_real = os.write
        llamadas = []

        def corto(fd, datos):
            if not os.readlink(f"/proc/self/fd/{fd}").startswith(str(self.sala)):
                return write_real(fd, datos)
            n = cuantos(len(datos), len(llamadas))
            llamadas.append(n)
            if isinstance(n, BaseException):
                raise n
            return write_real(fd, bytes(datos[:n])) if n else 0
        return mock.patch.object(self.b.os, "write", corto), llamadas

    def test_escritura_corta_se_completa(self):
        parche, llamadas = self._write_corto(lambda n, i: max(1, n // 2))
        with parche:
            self.assertTrue(self.b.escribir_sala('respuesta que debe quedar "completa"\ny entera'))
        self.assertGreater(len(llamadas), 3, "de verdad se escribió en pedazos")
        (d,) = self.jsons()
        self.assertEqual(d["texto"], 'respuesta que debe quedar "completa" y entera')
        self.assertEqual(set(d), {"perfil", "texto", "voz", "prioridad", "ts", "id", "tipo"})

    def test_escritura_que_no_avanza_no_publica_nada(self):
        # La mitad y después 0 (nada más cabe), o la mitad y después ENOSPC: ningún JSON final, ningún
        # .tmp suelto, la última frase no cambia y Telegram contesta con el aviso una sola vez.
        for falla in (0, OSError(28, "No space left on device")):
            with self.subTest(falla=falla):
                self.limpiar()
                self.b.atender_dicho("estás ahí")
                self.jsons()
                parche, llamadas = self._write_corto(lambda n, i: max(1, n // 2) if i == 0 else falla)
                with parche, self.assertLogs("botv3", logging.WARNING) as registro:
                    self.b.atender_dicho("qué hora es")
                self.assertEqual(len(llamadas), 2)
                self.assertEqual(list(self.sala.iterdir()), [], "ni JSON a medias ni .tmp")
                self.assertEqual(sum("sala: no pude escribir" in r for r in registro.output), 1)
                textos = self.textos()
                self.assertEqual(sum(t.startswith("🔇 No pude hablar por la sala") for t in textos), 1)
                self.assertEqual(sum(t.startswith("Son las ") for t in textos), 1, "la hora va a Telegram")
                self.b.atender_dicho("repite")
                self.assertEqual(self.dichos(), ["Sí."], "«repite» no dice la frase que nunca se publicó")

    def test_entradas_hostiles(self):
        self.b.responder("sala", 7, "texto", 'Uno\n"dos"\r\n\tcomillas \' y } { ]')
        (d,) = self.jsons()
        self.assertEqual(d["texto"], 'Uno "dos" comillas \' y } { ]')
        self.enviados.clear()
        self.b.responder("sala", 7, "x" * 4000, "x" * 4000)
        self.assertEqual(self.dichos(), ["Te lo mando al chat."])
        self.assertEqual("".join(self.textos()), "x" * 4000)
        self.b.atender_dicho("¿" + "qué " * 1500 + "?")      # 6000 caracteres: no se cae
        self.assertEqual(self.dichos(), ["Respuesta corta."])
        self.assertLessEqual(len(self.consultas[-1][1]), self.b.MAX_DICHO)
        self.b.atender_dicho("   ")
        self.assertEqual(self.jsons(), [])
        with self.assertRaises(ValueError):
            self.b.atender_dicho("hola", origen="telegram")


class C4SoloSala(Base):
    def test_repite_cancela_y_estas_ahi_por_la_sala(self):
        self.b.atender_dicho("repite")
        self.assertEqual(self.dichos(), ["No tengo nada que repetir."])
        self.b.atender_dicho("qué hora es")
        (hora,) = self.dichos()
        for frase in ("repite", "Jaime, repítelo", "¿Repite eso, por favor?"):
            self.b.atender_dicho(frase)
            self.assertEqual(self.dichos(), [hora], frase)
        self.b.atender_dicho("¿Estás ahí, Jaime?")
        self.assertEqual(self.dichos(), ["Sí."])
        for frase in ("cancela", "Olvídalo.", "Jaime, cancela"):
            self.b.atender_dicho(frase)
            self.assertEqual(self.jsons(), [], frase)
        self.assertEqual(self.textos(), [], "nada de esto va al chat")
        self.assertEqual(self.consultas, [])

    def test_por_telegram_siguen_su_camino(self):
        for frase in ("repite", "estás ahí", "olvídalo"):
            self.texto(frase)
            self.nota(frase)
        self.assertEqual([p for _, p in self.consultas], ["repite", "repite", "estás ahí", "estás ahí",
                                                          "olvídalo", "olvídalo"])
        self.assertEqual(self.jsons(), [])

    def test_cancela_el_de_los_tallarines_sigue_cancelando(self):
        activos = lambda: self.b.temporizadores_mod.activos(self.b.PERFIL)
        self.texto("temporizador de 10 minutos para los tallarines")
        self.assertIn("tallarines", self.textos()[-1])
        self.assertEqual(len(activos()), 1)
        self.texto("cancela el temporizador de los tallarines")
        self.assertEqual(activos(), [])
        # Por la sala, lo mismo: no es «cancela» a secas.
        self.b.atender_dicho("pon un temporizador de 10 minutos para los tallarines")
        self.assertEqual(len(activos()), 1)
        self.b.atender_dicho("cancela el temporizador de los tallarines")
        self.assertEqual(activos(), [])
        self.assertEqual(len(self.dichos()), 2)
        self.assertEqual(self.consultas, [])
        # «cancela el de los tallarines» (la forma del encargo) no la toma temporizadores.py ni antes ni
        # ahora: sigue al clasificador, igual por Telegram que por la sala. Lo que importa acá es que el
        # «cancela» de la sala no se la come.
        self.b.atender_dicho("pon un temporizador de 10 minutos para los tallarines")
        self.texto("cancela el de los tallarines")
        self.b.atender_dicho("cancela el de los tallarines")
        self.assertEqual([p for _, p in self.consultas], ["cancela el de los tallarines"] * 2)
        self.assertEqual(len(activos()), 1)


class C5Capacidades(Base):
    def spotify_activo(self):
        return self.b.spotify_mod is not None and bool(self.b.PERFIL_CFG.get("spotify"))

    def test_jaime(self):
        self.texto("¿Qué puedes hacer?")
        self.assertEqual(self.textos(), [chat_m4(gastos=True, agenda=True, spotify=self.spotify_activo())])
        self.assertEqual(self.voz, [], "escrito no se habla")
        chat, frase = self.b.texto_capacidades()
        # Jaime tiene `boleta` en sus rutas: la regla («compras [y gastos]») suma los gastos.
        self.assertEqual(frase, HABLADO_JAIME.replace("anotar en la lista de compras", "anotar compras y gastos"))

    def test_las_frases_y_las_que_no(self):
        for frase in ("qué puedes hacer", "Qué sabes hacer", "¿para qué sirves?", "qué haces", "Ayuda",
                      "Jaime, ¿qué puedes hacer?", "hola Jaime, ayuda", "qué haces, Jaime"):
            self.assertTrue(self.b.intencion_capacidades(frase), frase)
        for frase in ("ayuda con la lista", "qué puedes hacer con la lista", "necesito ayuda", "qué haces mañana",
                      "/ayuda", "pregunta rápida: qué puedes hacer"):
            self.assertFalse(self.b.intencion_capacidades(frase), frase)
        self.texto("ayuda con la lista")
        self.assertNotIn("Esto puedo hacer", "\n".join(t or "" for t in self.textos()))
        self.enviados.clear()
        self.texto("/ayuda")
        self.assertIn("consultas de solo lectura", self.textos()[0])

    def test_por_voz_y_por_la_sala(self):
        chat, frase = self.b.texto_capacidades()
        self.nota("Jaime, qué puedes hacer")
        self.assertEqual(self.textos()[1:], [chat])
        self.assertEqual(self.voz, [frase])
        self.limpiar()
        self.b.atender_dicho("qué sabes hacer")
        self.assertEqual(self.dichos(), [frase])
        self.assertEqual(self.textos(), [chat], "la lista completa queda en el chat")

    def test_los_ejemplos_del_texto_funcionan(self):
        """«Nunca nombra algo que ese bot no puede hacer»: cada ejemplo que nombra lo toma su intención."""
        b = self.b
        self.assertEqual(b.intencion_nodo("cómo está la Pi"), "estado")
        self.assertEqual(b.intencion_hora("qué hora es"), "hora")
        self.assertIsNotNone(b.intencion_clima("va a llover hoy"))
        self.assertEqual(b.intencion_compras("falta leche")[0], "agregar")
        self.assertIsNotNone(b.intencion_compras("qué hay en la lista"))
        self.assertIsNotNone(b.intencion_gasto("anota un gasto de 15 lucas en la feria"))
        for frase in ("temporizador de 10 minutos para los tallarines", "despiértame de lunes a viernes a las 6:30"):
            self.assertIsNotNone(b.temporizadores_mod.interpretar(frase, sonando=False), frase)
        for frase in ("pregunta técnica: x", "busca en internet: x", "pregunta rápida: x"):
            self.assertIsNotNone(b.selector_dicho(frase)[0], frase)


class C5Pilar(Base):
    perfil = "pilar"

    def test_pilar(self):
        chat, frase = self.b.texto_capacidades()
        self.assertEqual(frase, HABLADO_PILAR)
        spotify = self.b.spotify_mod is not None and bool(self.b.PERFIL_CFG.get("spotify"))
        self.assertEqual(chat, chat_m4(gastos=True, agenda=False, spotify=spotify))
        self.assertNotIn("Agenda", chat)


class C5JaimeSinBoleta(Base):
    quitar_rutas = ("boleta",)

    def test_sin_boleta_no_nombra_gastos(self):
        self.assertNotIn("boleta", self.b.ALLOWED_AUTO_ROUTES)
        chat, frase = self.b.texto_capacidades()
        self.assertEqual(frase, HABLADO_JAIME, "el texto aprobado, palabra por palabra")
        spotify = self.b.spotify_mod is not None and bool(self.b.PERFIL_CFG.get("spotify"))
        self.assertEqual(chat, chat_m4(gastos=False, agenda=True, spotify=spotify))
        self.assertNotIn("asto", chat + frase)


class C5SinSelectores(Base):
    quitar_rutas = ("codex", "gpt", "google")

    def test_sin_rutas_no_las_nombra(self):
        chat, frase = self.b.texto_capacidades()
        self.assertNotIn("pregunta técnica", chat)
        self.assertNotIn("pregunta rápida", chat)
        self.assertIn("busca en internet", chat, "el buscador lo tienen todos (96)")
        self.assertNotIn("Agenda", chat)
        self.assertNotIn("agenda", frase)


class C6Registros(Base):
    def usos(self):
        filas = []
        for f in sorted((self.tmp / "usos").glob("usos-*.jsonl")):
            filas += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
        return [(x["funcion"], x["canal"]) for x in filas]

    def libro(self):
        ruta = self.tmp / "uso-cuentas.jsonl"
        return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()] if ruta.exists() else []

    def test_sala_en_el_contador_y_en_el_libro(self):
        self.b.atender_dicho("qué hora es")
        self.b.atender_dicho("pregunta técnica: por qué falla el cron")
        self.b.atender_dicho("cuál es la capital de Mongolia")
        self.b.atender_dicho("estás ahí")
        self.b.atender_dicho("qué puedes hacer")
        self.assertEqual(self.usos(), [("hora", "sala"), ("selector:tecnica", "sala"), ("consulta:auto", "sala"),
                                       ("sala", "sala"), ("capacidades", "sala")])
        libro = self.libro()
        self.assertEqual([(x.get("selector"), x.get("canal")) for x in libro], [("tecnica", "sala"), (None, "sala")])
        # Telegram sin selector sigue sin `canal` en el libro (96), y con selector, «texto».
        self.texto("cuál es la capital de Chile")
        self.texto("pregunta técnica: y el log")
        self.assertEqual([(x.get("selector"), x.get("canal")) for x in self.libro()[2:]], [(None, None), ("tecnica", "texto")])
        self.assertEqual(self.usos()[-2:], [("consulta:auto", "texto"), ("selector:tecnica", "texto")])

    def test_busqueda_por_la_sala(self):
        self.b.atender_dicho("busca en internet precios del G2000")
        filas = [json.loads(x) for x in (self.tmp / "buscar-uso.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(x.get("selector"), x.get("canal")) for x in filas], [("buscar", "sala")])

    def test_resumen_de_usos_cuenta_la_sala(self):
        self.b.atender_dicho("qué hora es")
        self.texto("qué hora es")
        res = self.b.usos_mod.resumen({"jaime": self.tmp / "usos"}, {"jaime": []})
        self.assertEqual(res["bots"]["jaime"]["funciones"]["hora"], {"total": 2, "texto": 1, "voz": 0, "boton": 0,
                                                                     "sala": 1, "error": 0})
        self.assertIn("hora: 2 (texto 1, sala 1)", self.b.usos_mod.texto_resumen(res))


class MigradasPorLaSala(Base):
    """Las intenciones locales que pasaron por responder(), dichas en la sala."""

    def test_compras_temporizador_y_clima(self):
        self.b.atender_dicho("falta leche")
        self.assertEqual(self.dichos(), ["Anoté leche."])
        self.assertTrue(any("leche" in t for t in self.textos()), "lo que se escribe se ve en el chat")
        self.b.atender_dicho("qué hay en la lista")
        self.assertEqual(len(self.dichos()), 1)
        self.limpiar()
        self.b.atender_dicho("pon un temporizador de 5 minutos")
        (frase,) = self.dichos()
        self.assertIn("5 minutos", frase)
        self.assertEqual(self.notas, [])

    def test_nodo(self):
        llamadas = []

        def safe(argv, timeout=45):
            llamadas.append(argv[-1])
            return "Todo bien, sin alertas." if argv[-1] == "--breve" else f"🩺 Detalle largo {CENTINELA}"
        self.b.safe_command = safe
        self.b.texto_estado = lambda: safe(["/usr/local/bin/estado", "--telegram"])
        self.b.atender_dicho("cómo está la Pi")
        self.assertEqual(self.dichos(), ["Todo bien, sin alertas."])
        self.assertTrue(any(CENTINELA in t for t in self.textos()))
        self.b.enviar_uso = lambda chat: "ok"
        self.b.atender_dicho("cómo va la cuota")
        self.assertEqual(self.dichos(), ["Te lo mando al chat."])
        # Por la nota de voz de Telegram, como antes: el detalle escrito y la breve hablada.
        self.limpiar()
        self.nota("cómo está la Pi")
        self.assertEqual(self.voz, ["Todo bien, sin alertas."])
        self.limpiar()
        self.nota("cómo va la cuota")
        self.assertEqual(self.voz, [])

    def test_spotify(self):
        if self.b.spotify_mod is None or not self.b.PERFIL_CFG.get("spotify"):
            self.skipTest("spotify.py no está o el perfil no lo configura")
        sp = self.b.spotify_mod
        with mock.patch.object(sp, "estado", side_effect=sp.SpotifyError("caído")):
            self.b.atender_dicho("reproduce música de Los Prisioneros")
            self.assertEqual(self.dichos(), ["No pude usar Spotify ahora."])
            self.nota("reproduce música de Los Prisioneros")
            self.assertEqual(self.voz, [], "por la nota de voz, los errores de Spotify siguen sin audio")
        self.limpiar()
        with mock.patch.object(sp, "estado", return_value={"paused": False, "stopped": False}), \
                mock.patch.object(sp, "pausar") as pausar:
            self.b.atender_dicho("pausa")
            self.assertTrue(pausar.called)
            self.assertEqual(self.jsons(), [], "lo que funcionó se calla: la música ya paró")
            self.assertIn("⏸️ Spotify en pausa.", self.textos())


if __name__ == "__main__":
    unittest.main(verbosity=1)
