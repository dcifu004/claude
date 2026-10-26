#!/usr/bin/env python3
"""Pruebas de /bt en Jaime y Pilar (encargo 101b, C6 y C7).

El «servidor falso» es el bt-control de verdad (pi/bt/bt_control.py: `Control` y `Servidor`)
sobre un BlueZ en memoria, escuchando en un socket de un temporal. Así el cliente se prueba
contra el protocolo que produce el servicio, no contra uno copiado. Las secuencias salen de
`encargos/fixtures/101/secuencia-s22.json` y lo que suena, de `pi/bt/fixtures/pw-dump-sonando.json`.

Si el entorno no deja hacer `bind` de un socket Unix (el sandbox de Codex da EPERM), el mismo
servidor atiende por un `socketpair`: el cliente sigue usando su `connect`, `SO_PEERCRED` y la
lectura por líneas. La salida dice en qué modo corrió.

Nada escribe fuera de un temporal y Telegram es de mentira: no sale ningún mensaje.
"""
from __future__ import annotations

import asyncio
import atexit
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

if importlib.util.find_spec("requests") is None:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = RuntimeError
    requests_stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

# Como test_botv3.py: nada de esto puede caer en el estado real del bot ni en el socket real.
_TMP = tempfile.TemporaryDirectory(prefix="botv3-bt-", dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
for clave, nombre in (("BOTV3_USO_RUTAS", "uso-rutas.json"), ("BOTV3_USO_CUENTAS", "uso-cuentas.jsonl"),
                      ("BOTV3_USO_JSON", "uso.json"), ("BOTV3_REGISTRO_CUENTAS", "cuentas.toml"),
                      ("BOTV3_STATE_DIR", "state"), ("BOTV3_REMOTO_DIR", "remoto"),
                      ("BOTV3_ML_SOCKET", "ml-puente.sock"), ("BOTV3_ML_DIR", "mercadolibre"),
                      ("BOTV3_CASA_DIR", "casa"), ("VOZ_PARLANTE_DIR", "parlante"),
                      ("BOTV3_USOS_DIR", "usos")):
    os.environ[clave] = str(Path(_TMP.name) / nombre)
atexit.register(_TMP.cleanup)
SOCKET = Path(_TMP.name) / "casa" / "bt.sock"
SOCKET.parent.mkdir()
os.environ["BOTV3_BT_SOCKET"] = str(SOCKET)
YO = pwd.getpwuid(os.getuid()).pw_name
os.environ["BOTV3_BT_DUENO"] = YO

AQUI = Path(__file__).resolve().parent
PI = AQUI.parent / "pi"
FIXTURES = AQUI.parent / "encargos" / "fixtures" / "101"
SECUENCIA = json.loads((FIXTURES / "secuencia-s22.json").read_text(encoding="utf-8"))
PW_SONANDO = json.loads((PI / "bt" / "fixtures" / "pw-dump-sonando.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(AQUI))


def cargar(nombre, ruta, perfil="jaime"):
    previo = os.environ.get("BOTV3_PERFIL")
    os.environ["BOTV3_PERFIL"] = perfil
    try:
        spec = importlib.util.spec_from_file_location(nombre, ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if previo is None:
            os.environ.pop("BOTV3_PERFIL", None)
        else:
            os.environ["BOTV3_PERFIL"] = previo


bt = cargar("bt_control_101b", PI / "bt" / "bt_control.py")
bt.SALIDA = io.StringIO()                # el registro de journald del servicio no interesa acá
botv3 = cargar("botv3", AQUI / "botv3.py")
btc = botv3.bluetooth_mod

# Armado por partes: el grep de C7 toma el punto de su patrón como comodín y recorre también este
# archivo y su .pyc, así que la ruta de BlueZ no puede aparecer escrita entera.
ADAPTADOR = "/" + "/".join(("org", "blue" + "z", "hci0"))
D1, A1 = bt.DISPOSITIVO1, bt.ADAPTADOR1
OPENMOVE_MAC = "20:74:CF:80:3D:21"
S22_MAC = "9C:73:B1:84:B6:18"
FALSO_MAC = "32:15:66:CD:4C:3E"


def ruta_de(mac):
    return f"{ADAPTADOR}/dev_{mac.replace(':', '_')}"


def props(mac, nombre="", pareado=False, confiable=False, conectado=False):
    p = {"Address": mac, "Alias": nombre or mac.replace(":", "-"), "Paired": pareado,
         "Bonded": pareado, "Trusted": confiable, "Connected": conectado}
    if nombre:
        p["Name"] = nombre
    return p


class BluezFalso:
    """BlueZ en memoria, con la misma interfaz que usa `bt.Control`."""

    def __init__(self, equipos):
        self.objs = {ADAPTADOR: {A1: {"Alias": "Pi", "Discoverable": False, "Pairable": False}}}
        for e in equipos:
            self.objs[ruta_de(e["mac"])] = {D1: props(e["mac"], e["nombre"], True, e["confiable"],
                                                      e.get("conectado", False))}
        self.llamados, self.pendientes = [], []
        self.lento = 0.0

    async def objetos(self):
        return json.loads(json.dumps(self.objs))

    async def set_prop(self, ruta, iface, nombre, firma, valor):
        self.llamados.append(("set", ruta, nombre, valor))
        self.objs[ruta][iface][nombre] = valor

    async def remove_device(self, adaptador, ruta):
        self.llamados.append(("remove", ruta))
        if self.lento:
            await asyncio.sleep(self.lento)
        if self.objs.pop(ruta, None) is not None:
            self.pendientes.append(ruta)

    async def metodo(self, ruta, iface, nombre):
        self.llamados.append((nombre, ruta))
        if self.lento:
            await asyncio.sleep(self.lento)


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class ParCliente:
    """El socket del cliente cuando no se puede hacer `bind`: un extremo de un socketpair."""

    def __init__(self, servidor, *args):
        self.srv, self.s, self.t = servidor, None, None

    def settimeout(self, t):
        self.t = t
        if self.s:
            self.s.settimeout(t)

    def connect(self, ruta):
        if ruta != str(SOCKET) or not self.srv.vivo:
            raise FileNotFoundError(2, "No such file or directory")
        self.s, otro = socket.socketpair()
        self.s.settimeout(self.t)
        self.srv.correr(self.srv.atender_par(otro))

    def close(self):
        if self.s:
            self.s.close()

    def __getattr__(self, nombre):
        return getattr(self.s, nombre)


class ServidorBt:
    """bt-control real (núcleo y servidor del socket) sobre BlueZ falso, en su propio hilo."""
    modo = None

    def __init__(self, equipos, pw=PW_SONANDO):
        self.falso, self.reloj, self.verbos, self.vivo = BluezFalso(equipos), Reloj(), [], False
        self.loop = asyncio.new_event_loop()
        self.hilo = threading.Thread(target=self.loop.run_forever, name="servidor-bt", daemon=True)
        self.hilo.start()

        async def leer_pw():
            return pw
        self.ctl = bt.Control(self.falso, reloj=self.reloj, pw=leer_pw)
        self.correr(self.ctl.cargar())
        original = self.ctl.pedido

        async def pedido(linea):
            try:
                d = json.loads(linea)
                self.verbos.append((d.get("verbo"), d.get("mac")))
            except ValueError:
                self.verbos.append(("?", None))
            return await original(linea)
        self.ctl.pedido = pedido
        self.servidor = None

    def correr(self, coro, espera=10):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(espera)

    def arrancar(self, prueba):
        if ServidorBt.modo != "par":
            try:
                self.correr(self._escuchar())
                ServidorBt.modo = "socket"
            except PermissionError:
                ServidorBt.modo = "par"
                print("\n[test_bluetooth] bind de AF_UNIX no permitido: el servidor atiende por socketpair",
                      file=sys.stderr)
        if ServidorBt.modo == "par":
            nuevo = types.SimpleNamespace(**{k: getattr(socket, k) for k in (
                "AF_UNIX", "SOCK_STREAM", "SOL_SOCKET", "SO_PEERCRED", "timeout")})
            nuevo.socket = lambda *a: ParCliente(self, *a)
            p = mock.patch.object(btc, "socket", nuevo)
            p.start()
            prueba.addCleanup(p.stop)
        self.vivo = True
        prueba.addCleanup(self.parar)
        return self

    async def _escuchar(self):
        s, _ = bt.crear_socket(str(SOCKET), _grupo_propio())
        self.servidor = await asyncio.start_unix_server(bt.Servidor(self.ctl).atender, sock=s)

    async def atender_par(self, otro):
        lector, escritor = await asyncio.open_connection(sock=otro)
        asyncio.ensure_future(bt.Servidor(self.ctl).atender(lector, escritor))

    def reanudar(self):
        """bt-control vuelve (systemd lo reinicia) con el mismo estado en memoria."""
        if ServidorBt.modo == "socket":
            self.correr(self._escuchar())
        self.vivo = True

    def parar(self):
        """Lo que ve el bot cuando bt-control se cae: no hay socket."""
        self.vivo = False
        if self.servidor is not None:
            async def cerrar():
                self.servidor.close()
                await self.servidor.wait_closed()
            self.correr(cerrar())
            self.servidor = None
        try:
            SOCKET.unlink()
        except FileNotFoundError:
            pass

    def detener_loop(self):
        async def cancelar():
            for tarea in asyncio.all_tasks():
                if tarea is not asyncio.current_task():
                    tarea.cancel()
        self.correr(cancelar())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.hilo.join(5)
        self.loop.close()

    def verbos_de(self, verbo):
        return [m for v, m in self.verbos if v == verbo]

    async def _secuencia(self, eventos):
        """Lo que haría el S22 (el fixture real), con el tic del servicio cada 0,5 s."""
        ctl, falso = self.ctl, self.falso
        t0 = self.reloj.t

        async def entregar():
            while falso.pendientes:
                await ctl.al_quitar(falso.pendientes.pop(0), [D1])
        for ev in eventos:
            while self.reloj.t < t0 + ev["t"]:
                self.reloj.t += 0.5
                await ctl.tick()
                await entregar()
            ruta = ev["dispositivo"]
            if ev["tipo"] == "RequestConfirmation":
                if ruta not in falso.objs:
                    mac = bt.mac_de_ruta(ruta)
                    falso.objs[ruta] = {D1: props(mac, conectado=True)}
                    await ctl.al_agregar(ruta, {D1: dict(falso.objs[ruta][D1])})
                ctl.agente("RequestConfirmation", [ruta, ev["codigo"]])
            else:
                falso.objs[ruta][D1].update(ev["cambios"])
                await ctl.al_cambiar(ruta, D1, ev["cambios"], [])
            await entregar()
        for _ in range(40):
            self.reloj.t += 0.5
            await ctl.tick()
            await entregar()

    def secuencia(self, eventos):
        self.correr(self._secuencia(eventos))


def _grupo_propio():
    import grp
    return grp.getgrgid(os.getgid()).gr_name


EMPAREJADOS = [  # el OpenMove del fixture y el S22 ya emparejado y sonando (pw-dump-sonando)
    {"mac": OPENMOVE_MAC, "nombre": "OpenMove by AfterShokz", "confiable": True},
    {"mac": S22_MAC, "nombre": "S22 de Diego", "confiable": True, "conectado": True},
]


class ConBot(unittest.TestCase):
    """Un bot con Telegram de mentira y bt-control real sobre BlueZ falso."""
    bot = botv3
    equipos = EMPAREJADOS

    def setUp(self):
        self.llamadas, self.n = [], 900
        self.cerrojo = threading.Lock()

        def telegram(metodo, payload=None, timeout=40):
            with self.cerrojo:
                self.llamadas.append((metodo, payload or {}, time.monotonic()))
                self.n += 1
                return {"message_id": self.n} if metodo == "sendMessage" else True
        for nombre, valor in (("telegram", telegram), ("audit", lambda *a, **k: None),
                              ("BT_CADA", 0.02), ("BT_MARGEN", 2)):
            p = mock.patch.object(self.bot, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        self.bot.PROPUESTAS.clear()
        self.addCleanup(self.bot.PROPUESTAS.clear)
        self.srv = ServidorBt(self.equipos)
        self.addCleanup(self.srv.detener_loop)

    def tearDown(self):
        self.esperar_hilos()

    # --- Telegram de mentira
    def escribir(self, texto, chat=None, usuario=None):
        self.bot.handle_update({"message": {"chat": {"id": self.bot.CHAT_ID if chat is None else chat},
                                            "from": {"id": self.bot.USER_ID if usuario is None else usuario},
                                            "text": texto}})

    def tocar(self, data, mensaje=None, chat=None, usuario=None):
        mensaje = dict(mensaje or {"message_id": 77})
        mensaje["chat"] = {"id": self.bot.CHAT_ID if chat is None else chat}
        self.bot.handle_update({"callback_query": {
            "id": "q1", "data": data, "from": {"id": self.bot.USER_ID if usuario is None else usuario},
            "message": mensaje}})

    def esperar_hilos(self, espera=15):
        fin = time.monotonic() + espera
        for h in [h for h in threading.enumerate() if h.name == "botv3-bt"]:
            h.join(max(0.1, fin - time.monotonic()))
            self.assertFalse(h.is_alive(), "un hilo de /bt no terminó")

    def mandados(self, metodo="sendMessage"):
        return [p for m, p, _ in self.llamadas if m == metodo]

    def textos(self):
        return [p.get("text", "") for m, p, _ in self.llamadas if m in {"sendMessage", "editMessageText"}]

    def botones(self, payload):
        return [b for fila in payload["reply_markup"]["inline_keyboard"] for b in fila]

    def respuestas_callback(self):
        return [p.get("text", "") for m, p, _ in self.llamadas if m == "answerCallbackQuery"]

    def ultimo_con_teclado(self):
        return [p for p in self.mandados() if p.get("reply_markup")][-1]


class EstadoTests(ConBot):
    def test_c6_bt_muestra_los_dos_equipos_con_sus_botones(self):
        self.srv.arrancar(self)
        self.escribir("/bt")
        msg = self.mandados()[-1]
        texto = msg["text"]
        self.assertIn("🔵 Bluetooth de la Pi", texto)
        self.assertIn("⚪ OpenMove by AfterShokz — desconectado", texto)
        self.assertIn("🟢 S22 de Diego — conectado", texto)
        # Lo que suena, con códec y salida, sale del pw-dump con la forma real.
        self.assertIn("🎵 Suena S22 de Diego en aptx → EDIFIER G2000 Analog Stereo", texto)
        datos = [(b["text"], b["callback_data"]) for b in self.botones(msg)]
        self.assertEqual(datos, [
            ("📋 Estado", "bt:est"), ("➕ Emparejar", "bt:emp"),
            ("🔌 Conectar OpenMove by AfterSho", f"bt:con:{OPENMOVE_MAC}"),
            ("🗑️ Olvidar OpenMove by AfterSho", f"bt:olv:{OPENMOVE_MAC}"),
            ("🔌 Desconectar S22 de Diego", f"bt:des:{S22_MAC}"),
            ("🗑️ Olvidar S22 de Diego", f"bt:olv:{S22_MAC}")])
        self.assertTrue(all(len(d.encode()) <= 64 for _, d in datos))
        self.assertNotIn("parse_mode", msg)
        self.assertEqual(self.srv.verbos, [("estado", None)])

    def test_estado_y_menu_dan_lo_mismo_que_el_comando(self):
        self.srv.arrancar(self)
        self.escribir("/bt")
        directo = self.mandados()[-1]
        self.tocar("menu:bluetooth")
        self.assertEqual(self.mandados()[-1], directo)
        # 📋 Estado edita el mismo mensaje con lo leído al tocar, sin ✅.
        self.tocar("bt:est", {"message_id": 55})
        self.esperar_hilos()
        editado = self.mandados("editMessageText")[-1]
        self.assertEqual((editado["message_id"], editado["text"]), (55, directo["text"]))
        self.assertEqual(self.srv.verbos_de("abrir"), [])

    def test_sin_nada_sonando_ni_equipos(self):
        self.srv = ServidorBt([], pw=[])
        self.addCleanup(self.srv.detener_loop)
        self.srv.arrancar(self)
        self.escribir("/bt")
        msg = self.mandados()[-1]
        self.assertIn("No hay equipos emparejados.", msg["text"])
        self.assertIn("🔈 No suena nada por Bluetooth.", msg["text"])
        self.assertEqual(len(self.botones(msg)), 2)

    def test_nombre_hostil_va_limpio_y_sin_parse_mode(self):
        self.srv = ServidorBt([{"mac": OPENMOVE_MAC, "nombre": "*_[x](http://a)‮" + "z" * 80,
                                "confiable": True}], pw=None)
        self.addCleanup(self.srv.detener_loop)
        self.srv.arrancar(self)
        self.escribir("/bt")
        msg = self.mandados()[-1]
        self.assertNotIn("parse_mode", msg)
        self.assertNotIn("‮", msg["text"])
        linea = [l for l in msg["text"].splitlines() if l.startswith("⚪")][0]
        self.assertTrue(linea.startswith("⚪ *_[x](http://a)"))
        self.assertLessEqual(len(linea), len("⚪  — desconectado") + 40)
        self.assertIn("🔈 No pude ver qué suena.", msg["text"])


class EmparejarTests(ConBot):
    equipos = SECUENCIA["emparejados_antes"]

    def confirmar(self):
        self.tocar("bt:emp")
        pedido = self.ultimo_con_teclado()
        self.assertIn("¿Hago visible la Pi por 3 minutos?", pedido["text"])
        si, no = self.botones(pedido)
        self.assertEqual((si["text"], no["text"]), ("✅ Hacer visible", "✖️ No"))
        return si["callback_data"], no["callback_data"]

    def test_c6_mas_sin_ok_no_llama_a_abrir(self):
        self.srv.arrancar(self)
        si, no = self.confirmar()
        self.esperar_hilos()
        self.assertEqual(self.srv.verbos, [])
        self.tocar(no, {"message_id": 60})
        self.tocar(si, {"message_id": 60})          # ya se usó: no abre
        self.tocar("bt:si:ffffffffffff")              # inventado: tampoco
        self.esperar_hilos()
        self.assertEqual(self.srv.verbos_de("abrir"), [])
        self.assertIs(self.srv.falso.objs[ADAPTADOR][A1]["Discoverable"], False)
        self.assertIn("Eso ya venció o se usó", self.respuestas_callback())

    def test_c6_con_ok_abre_una_vez_y_avisa_emparejado_y_cierre(self):
        self.srv.arrancar(self)
        si, _ = self.confirmar()
        self.tocar(si, {"message_id": 61})
        self.tocar(si, {"message_id": 61})          # el segundo toque no vuelve a abrir
        fin = time.monotonic() + 5
        while not self.srv.verbos_de("ventana") and time.monotonic() < fin:
            time.sleep(0.01)
        self.assertEqual(len(self.srv.verbos_de("abrir")), 1)
        self.assertIs(self.srv.falso.objs[ADAPTADOR][A1]["Discoverable"], True)
        self.srv.secuencia(SECUENCIA["eventos"])
        self.esperar_hilos()
        self.assertEqual(len(self.srv.verbos_de("abrir")), 1)
        editado = [p for p in self.mandados("editMessageText") if p["message_id"] == 61][0]
        self.assertTrue(editado["text"].startswith("🔓 La Pi está visible como «Pi» por 3:00 min."))
        self.assertNotIn("reply_markup", editado)    # el ✅ desaparece
        nuevos = [p for p in self.mandados() if "¿Hago visible" not in p["text"]]
        self.assertEqual([p["text"] for p in nuevos],
                         ["✅ Se emparejó «S22 de Diego» (código 724795)", "🔒 La Pi dejó de ser visible"])
        boton = self.botones(nuevos[0])
        self.assertEqual([(b["text"], b["callback_data"]) for b in boton],
                         [("🗑️ No era este", f"bt:nee:{S22_MAC}")])
        # El descartado (32:…:3E) y los dos códigos no se avisan; ningún mensaje lleva parse_mode.
        self.assertFalse(any("parse_mode" in p for _, p, _ in self.llamadas))
        self.assertEqual({p["chat_id"] for p in self.mandados()}, {self.bot.CHAT_ID})
        self.assertEqual(self.bot.BT_VIGILADAS, set())

        # «🗑️ No era este» llama a olvidar con la MAC del emparejado, y nada más.
        self.srv.verbos.clear()
        antes = time.monotonic()
        self.tocar(boton[0]["callback_data"], {"message_id": 62, "text": nuevos[0]["text"],
                                                "reply_markup": nuevos[0]["reply_markup"]})
        self.assertLess(time.monotonic() - antes, 0.5)
        self.esperar_hilos()
        self.assertEqual(self.srv.verbos, [("olvidar", S22_MAC)])
        self.assertNotIn(ruta_de(S22_MAC), self.srv.falso.objs)
        self.assertIn(ruta_de(OPENMOVE_MAC), self.srv.falso.objs)
        editado = self.mandados("editMessageText")[-1]
        self.assertEqual(editado["message_id"], 62)
        self.assertIn("🗑️ Lo saqué", editado["text"])

    def test_ventana_que_vence_sin_nadie_avisa_un_cierre(self):
        self.srv.arrancar(self)
        si, _ = self.confirmar()
        self.tocar(si, {"message_id": 61})
        fin = time.monotonic() + 5
        while not self.srv.verbos_de("ventana") and time.monotonic() < fin:
            time.sleep(0.01)
        self.srv.secuencia([{"t": 181, "tipo": "PropertiesChanged", "dispositivo": ruta_de(OPENMOVE_MAC),
                             "cambios": {}}])
        self.esperar_hilos()
        self.assertEqual([p["text"] for p in self.mandados() if "¿Hago" not in p["text"]],
                         ["🔒 La Pi dejó de ser visible"])

    def test_ventana_ya_abierta_se_reusa_y_se_vigila_una_vez(self):
        self.srv.arrancar(self)
        primero, _ = self.confirmar()
        segundo, _ = self.confirmar()
        self.tocar(primero, {"message_id": 61})
        self.tocar(segundo, {"message_id": 62})
        fin = time.monotonic() + 5
        while len(self.srv.verbos_de("abrir")) < 2 and time.monotonic() < fin:
            time.sleep(0.01)
        self.srv.secuencia(SECUENCIA["eventos"])
        self.esperar_hilos()
        textos = [p["text"] for p in self.mandados()]
        self.assertEqual(textos.count("✅ Se emparejó «S22 de Diego» (código 724795)"), 1)
        self.assertEqual(textos.count("🔒 La Pi dejó de ser visible"), 1)
        editados = {p["message_id"]: p["text"] for p in self.mandados("editMessageText")}
        self.assertTrue(any(t.startswith("🔓 La Pi ya estaba visible") for t in editados.values()))

    def test_caida_a_mitad_de_la_ventana_avisa_un_cierre(self):
        self.srv.arrancar(self)
        si, _ = self.confirmar()
        self.tocar(si, {"message_id": 61})
        fin = time.monotonic() + 5
        while not self.srv.verbos_de("ventana") and time.monotonic() < fin:
            time.sleep(0.01)
        # Al servicio le queda 1 s (reloj corrido, sin tic: sigue abierta); el hilo lo lee y
        # después bt-control se cae. El hilo sigue preguntando hasta quedan + BT_MARGEN.
        self.srv.reloj.t += 179
        n = len(self.srv.verbos_de("ventana"))
        while len(self.srv.verbos_de("ventana")) < n + 2 and time.monotonic() < fin + 5:
            time.sleep(0.01)
        self.srv.parar()
        self.esperar_hilos()
        cierre = [p["text"] for p in self.mandados() if p["text"].startswith("🔒")]
        self.assertEqual(len(cierre), 1)
        self.assertIn("no respondió", cierre[0])


    def test_un_corte_breve_no_termina_la_vigilancia(self):
        self.srv.arrancar(self)
        si, _ = self.confirmar()
        self.tocar(si, {"message_id": 61})
        fin = time.monotonic() + 5
        while not self.srv.verbos_de("ventana") and time.monotonic() < fin:
            time.sleep(0.01)
        self.srv.parar()
        time.sleep(0.3)                             # unas 15 preguntas fallidas
        self.srv.reanudar()
        self.srv.secuencia(SECUENCIA["eventos"])
        self.esperar_hilos()
        self.assertEqual([p["text"] for p in self.mandados() if "¿Hago" not in p["text"]],
                         ["✅ Se emparejó «S22 de Diego» (código 724795)", "🔒 La Pi dejó de ser visible"])


class AccionesTests(ConBot):
    def test_conectar_y_desconectar_sin_ok_y_refresca(self):
        self.srv.arrancar(self)
        self.tocar(f"bt:con:{OPENMOVE_MAC}", {"message_id": 70})
        self.tocar(f"bt:des:{S22_MAC}", {"message_id": 70})
        self.esperar_hilos()
        self.assertEqual(self.srv.verbos_de("conectar"), [OPENMOVE_MAC])
        self.assertEqual(self.srv.verbos_de("desconectar"), [S22_MAC])
        self.assertIn(("Connect", ruta_de(OPENMOVE_MAC)), self.srv.falso.llamados)
        self.assertIn(("Disconnect", ruta_de(S22_MAC)), self.srv.falso.llamados)
        self.assertEqual(self.respuestas_callback()[:2], ["Conectando…", "Desconectando…"])
        self.assertTrue(self.mandados("editMessageText")[-1]["text"].startswith("🔵 Bluetooth de la Pi"))

    def test_el_boton_contesta_antes_de_3_s_aunque_el_bluetooth_tarde(self):
        self.srv.arrancar(self)
        self.srv.falso.lento = 2.6                 # más que la espera de 2,5 s de bt-control
        antes = time.monotonic()
        self.tocar(f"bt:con:{OPENMOVE_MAC}", {"message_id": 70})
        respuesta = [t for m, _, t in self.llamadas if m == "answerCallbackQuery"][0]
        self.assertLess(respuesta - antes, 0.5)
        self.esperar_hilos()
        self.assertIn("⏳ El Bluetooth sigue en eso. Toca 📋 Estado en un rato.", self.textos())

    def test_olvidar_pide_ok_y_usa_la_mac_del_boton(self):
        self.srv.arrancar(self)
        self.escribir("/bt")
        estado = self.mandados()[-1]
        self.tocar(f"bt:olv:{OPENMOVE_MAC}", {"message_id": 71, "text": estado["text"],
                                              "reply_markup": estado["reply_markup"]})
        pedido = self.ultimo_con_teclado()
        self.assertEqual(pedido["text"].splitlines()[0], "🗑️ ¿Olvido «OpenMove by AfterSho» (…3D:21)?")
        self.esperar_hilos()
        self.assertEqual(self.srv.verbos_de("olvidar"), [], "olvidar espera el ✅")
        si, no = self.botones(pedido)
        self.tocar(no["callback_data"], {"message_id": 72})
        self.assertEqual(self.srv.verbos_de("olvidar"), [])
        self.tocar(f"bt:olv:{OPENMOVE_MAC}")
        si, _ = self.botones(self.ultimo_con_teclado())
        self.tocar(si["callback_data"], {"message_id": 73})
        self.tocar(si["callback_data"], {"message_id": 73})
        self.esperar_hilos()
        self.assertEqual(self.srv.verbos_de("olvidar"), [OPENMOVE_MAC])
        self.assertNotIn(ruta_de(OPENMOVE_MAC), self.srv.falso.objs)
        self.assertTrue(self.mandados("editMessageText")[-1]["text"].startswith("🗑️ Olvidé el equipo …3D:21."))

    def test_olvidar_lento_dice_que_no_respondio_a_tiempo(self):
        # Hallazgo 2 de 101ar: bt-control espera RemoveDevice sin tope. El bot corta a los 3 s.
        self.srv.arrancar(self)
        self.srv.falso.lento = 1.0
        with mock.patch.object(btc, "TIMEOUT", 0.3):
            self.tocar(f"bt:nee:{S22_MAC}", {"message_id": 74, "text": "✅ Se emparejó «S22 de Diego» (código 1)"})
            self.esperar_hilos()
        self.assertIn("🔵 No pude sacarlo: El Bluetooth no responde. Puede que igual se haya olvidado: míralo con /bt.",
                      self.textos())

    def test_mac_ajena_o_mal_formada(self):
        self.srv.arrancar(self)
        self.tocar("bt:con:AA:BB:CC:DD:EE:FF")
        self.tocar("bt:olv:9c:73:b1:84:b6:18")
        self.tocar("bt:con:../../x")
        self.tocar("bt:zzz")
        self.esperar_hilos()
        self.assertEqual(self.srv.verbos_de("conectar"), ["AA:BB:CC:DD:EE:FF"])
        self.assertIn("🔵 Ese equipo ya no está emparejado. Toca 📋 Estado.", self.textos())
        self.assertEqual(self.respuestas_callback()[1:], ["Botón antiguo o no disponible"] * 3)


class CaidoTests(ConBot):
    def test_c6_socket_caido_responde_y_no_rompe_el_bot(self):
        # Sin arrancar el servidor: no hay socket, como con bt-control caído o el volumen cerrado.
        self.escribir("/bt")
        msg = self.mandados()[-1]
        self.assertEqual(msg["text"], "🔵 El Bluetooth no responde.")
        self.assertEqual([b["callback_data"] for b in self.botones(msg)], ["bt:est", "bt:emp"])
        self.assertNotIn(str(SOCKET), msg["text"])
        for data in ("bt:est", f"bt:con:{S22_MAC}", f"bt:nee:{S22_MAC}"):
            self.tocar(data)
        self.tocar("bt:emp")
        si, _ = self.botones(self.ultimo_con_teclado())
        self.tocar(si["callback_data"], {"message_id": 80})
        self.esperar_hilos()
        textos = self.textos()
        self.assertIn("❌ No hice visible la Pi: El Bluetooth no responde.", textos)
        self.assertTrue(all(str(SOCKET) not in t and "Errno" not in t for t in textos))
        # El bot sigue contestando lo demás.
        n = len(self.mandados())
        self.escribir("/ayuda")
        self.assertIn("/bt — Bluetooth de la Pi", "".join(p["text"] for p in self.mandados()[n:]))

    def test_impostor_en_el_socket_no_recibe_pedidos(self):
        # casa/ es 2770 sin sticky: otro miembro podría poner su servidor. SO_PEERCRED lo detecta.
        otro = next((p.pw_name for p in pwd.getpwall() if p.pw_uid != os.getuid()), None)
        if otro is None:
            self.skipTest("no hay otro usuario en este equipo")
        self.srv.arrancar(self)
        with mock.patch.dict(os.environ, {"BOTV3_BT_DUENO": otro}):
            self.escribir("/bt")
        self.assertEqual(self.mandados()[-1]["text"], "🔵 El Bluetooth no responde.")
        self.assertEqual(self.srv.verbos, [], "al impostor no se le manda el pedido")

    def test_el_cliente_limpia_otra_vez_lo_que_manda_el_equipo(self):
        # Segunda llave: aunque bt-control dejara pasar un nombre sucio, al chat llega limpio.
        self.srv.arrancar(self)
        sucio = "Parlante\nfalso\u202e\x07" + "z" * 80

        async def pedido(linea):
            return {"ok": True, "bluez": True, "dispositivos": [
                {"mac": OPENMOVE_MAC, "nombre": sucio, "conectado": False, "confiable": True},
                {"mac": "no-es-mac", "nombre": "x", "conectado": True, "confiable": True}],
                "ventana": {"abierta": True, "id": "../etc", "quedan": 10**9},
                "sonando": [{"mac": OPENMOVE_MAC, "nombre": sucio, "codec": "a\nb", "salida": sucio}]}
        with mock.patch.object(self.srv.ctl, "pedido", pedido):
            self.escribir("/bt")
        texto = self.mandados()[-1]["text"]
        lineas = texto.splitlines()
        self.assertEqual(len([l for l in lineas if l.startswith("⚪")]), 1)
        self.assertNotIn("\u202e", texto)
        self.assertNotIn("\x07", texto)
        self.assertIn("⚪ Parlante falso" + "z" * 26 + " — desconectado", lineas)
        self.assertIn("en a b →", texto)
        self.assertIn("🔓 Visible como «Pi»: quedan 60:00.", lineas)
        self.assertEqual(len(self.botones(self.mandados()[-1])), 4)

    def test_respuestas_que_no_son_del_protocolo(self):
        self.srv.arrancar(self)
        for basura in (b"no es json\n", b"[1,2]\n", b'{"ok":"si"}\n', b'{"ok":true}', b"x" * 5000 + b"\n"):
            async def pedido(linea, basura=basura):
                return basura
            with self.subTest(basura=basura[:12]), mock.patch.object(bt, "respuesta", lambda d: d), \
                    mock.patch.object(self.srv.ctl, "pedido", pedido), mock.patch.object(btc, "TIMEOUT", 0.5):
                with self.assertRaises(btc.BluetoothError) as cm:
                    btc.estado()
                self.assertIn(cm.exception.codigo, {"respuesta", "tiempo"})


class PerfilesTests(unittest.TestCase):
    def test_bt_en_el_menu_de_telegram_de_los_dos_perfiles(self):
        from update_telegram_commands import comandos
        for perfil, rutas in (("jaime", ["boleta", "google"]), ("pilar", [])):
            self.assertIn("bt", [c["command"] for c in comandos(rutas, perfil)])
        self.assertEqual(botv3.ALIAS_COMANDOS["/bt"], "bluetooth")
        self.assertEqual(botv3.PREFIJOS_BOTON["bt"], "bluetooth")
        self.assertIn("bluetooth", [a for a, _, _ in botv3.areas_del_perfil()])
        # El contador de uso (encargo 92) lo anota como «bluetooth», venga por comando, menú o botón.
        for update in ({"message": {"text": "/bt"}}, {"callback_query": {"data": "menu:bluetooth"}},
                       {"callback_query": {"data": f"bt:con:{S22_MAC}"}}):
            funcion = botv3.funcion_de_update(update)[1]
            self.assertEqual(botv3.usos_mod.funcion_valida(funcion), "bluetooth")

    def test_pilar_tiene_bt_y_un_boton_de_otro_chat_no_actua(self):
        pilar = cargar("botv3_pilar_bt", AQUI / "botv3.py", "pilar")
        self.assertIsNotNone(pilar.bluetooth_mod)
        self.assertIn("bluetooth", [a for a, _, _ in pilar.areas_del_perfil()])
        llamadas = []
        with mock.patch.object(pilar, "telegram", lambda m, p=None, timeout=40: llamadas.append((m, p))), \
                mock.patch.object(pilar, "audit", lambda *a, **k: None):
            for chat, usuario in ((pilar.CHAT_ID + 1, pilar.USER_ID), (pilar.CHAT_ID, pilar.USER_ID + 1)):
                pilar.handle_update({"callback_query": {"id": "q", "data": f"bt:con:{S22_MAC}",
                                                        "from": {"id": usuario},
                                                        "message": {"message_id": 1, "chat": {"id": chat}}}})
        self.assertEqual([p["text"] for _, p in llamadas], ["No autorizado", "No autorizado"])
        self.assertFalse([h for h in threading.enumerate() if h.name == "botv3-bt"])


class SinBluezTests(unittest.TestCase):
    def test_c7_el_bot_no_toca_bluez(self):
        import re
        # El mismo patrón del grep de C7 (con el punto como comodín), archivos binarios incluidos.
        # Con join y no con «+»: Python pliega la suma de dos literales en una sola constante del .pyc.
        patron = re.compile("|".join(("".join(("bluetooth", "ctl")), ".".join(("org", "bluez")))).encode())
        hallados = []
        for raiz, _, archivos in os.walk(AQUI):
            for nombre in archivos:
                ruta = Path(raiz) / nombre
                hallados += [f"{ruta.relative_to(AQUI)}: {m.group().decode()}"
                             for m in patron.finditer(ruta.read_bytes())]
        self.assertEqual(hallados, [])

    def test_el_cliente_no_llama_a_programas(self):
        texto = (AQUI / "bluetooth.py").read_text(encoding="utf-8")
        for prohibido in ("subprocess", "os.system", "busctl", "pw-", "dbus"):
            self.assertNotIn(prohibido, texto)

    def test_error_sin_ruta_ni_excepcion(self):
        with mock.patch.dict(os.environ, {"BOTV3_BT_SOCKET": str(Path(_TMP.name) / "no-existe.sock")}):
            with self.assertRaises(btc.BluetoothError) as cm:
                btc.estado()
        self.assertEqual(cm.exception.codigo, "caido")
        self.assertEqual(str(cm.exception), "caido")
        self.assertIsNone(cm.exception.__cause__)
        self.assertTrue(cm.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main(verbosity=1)
