#!/usr/bin/env python3
"""Pruebas del contador de uso de los bots (encargo 92). El bot de verdad (`handle_update`) con Telegram y
los motores simulados; el registro en un temporal. Nada sale a la red ni se escribe fuera del temporal.

    NODO_PRUEBAS=1 python3 -B -m unittest botv3/test_contador.py
"""
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

if importlib.util.find_spec("requests") is None:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = RuntimeError
    requests_stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

_TMP = tempfile.TemporaryDirectory(prefix="botv3-contador-")
for clave, nombre in (("BOTV3_USO_RUTAS", "uso-rutas.json"), ("BOTV3_USO_CUENTAS", "uso-cuentas.jsonl"),
                      ("BOTV3_USO_JSON", "uso.json"), ("BOTV3_REGISTRO_CUENTAS", "cuentas.toml"),
                      ("BOTV3_STATE_DIR", "state"), ("BOTV3_REMOTO_DIR", "remoto"),
                      ("BOTV3_ML_SOCKET", "ml-puente.sock"), ("BOTV3_ML_DIR", "mercadolibre"),
                      ("BOTV3_CASA_DIR", "casa")):
    os.environ[clave] = str(Path(_TMP.name) / nombre)

import usos  # noqa: E402

SECRETO = "mi-clave-del-banco-4321"


def cargar_bot(perfil, usos_dir, otros=""):
    previo = {k: os.environ.get(k) for k in ("BOTV3_PERFIL", "BOTV3_USOS_DIR", "BOTV3_USOS_OTROS")}
    os.environ.update(BOTV3_PERFIL=perfil, BOTV3_USOS_DIR=str(usos_dir), BOTV3_USOS_OTROS=otros)
    try:
        spec = importlib.util.spec_from_file_location(f"botv3_contador_{perfil}_{id(usos_dir)}", AQUI / "botv3.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in previo.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


class Base(unittest.TestCase):
    perfil = "jaime"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=_TMP.name)
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "usos"
        self.bot = b = cargar_bot(self.perfil, self.dir)
        self.assertIsNotNone(b.usos_mod, "botv3.py no encontró usos.py")
        b.CHAT_ID = b.USER_ID = 7
        self.enviados, self.consultas = [], []
        b.telegram = lambda metodo, datos=None, *a, **k: (self.enviados.append((metodo, datos)) or {"ok": True})
        b.safe_command = lambda argv, timeout=45: f"salida de {argv[0]}"
        # La consulta a los motores no sale: se reemplaza lo que hay DEBAJO de la marca, no la marca.
        b.submit_query = b._marcador(lambda ruta, texto="", *a, **k: self.consultas.append(ruta), b._ruta_de_consulta, False)
        b.transcribir_voz = lambda *a, **k: self.dicho

    def mensaje(self, texto=None, voz=False, extra=None):
        m = {"chat": {"id": 7}, "from": {"id": 7}}
        if voz:
            m["voice"] = {"file_id": "x", "file_size": 10}
        else:
            m["text"] = texto
        m.update(extra or {})
        self.bot.handle_update({"update_id": 1, "message": m})

    def boton(self, data):
        self.bot.handle_update({"update_id": 2, "callback_query": {"id": "q", "data": data, "from": {"id": 7},
                                                                    "message": {"chat": {"id": 7}, "message_id": 3}}})

    def lineas(self):
        if not self.dir.exists():
            return []
        return [json.loads(x) for p in sorted(self.dir.glob("usos-*.jsonl"))
                for x in p.read_text(encoding="utf-8").splitlines()]

    def crudo(self):
        return "".join(p.read_text(encoding="utf-8") for p in self.dir.glob("*")) if self.dir.exists() else ""


class CadaUsoDejaUnaLinea(Base):
    def test_cada_comando(self):
        b = self.bot
        comandos = sorted(set(b.ALIAS_COMANDOS) | {"/start", "/claude hola", "/inventado"})
        for c in comandos:
            antes = len(self.lineas())
            try:
                self.mensaje(c)
            except Exception:       # un comando que falla igual deja su línea (con error)
                pass
            self.assertEqual(len(self.lineas()), antes + 1, c)
        funciones = [x["funcion"] for x in self.lineas()]
        self.assertIn("menu", funciones)
        self.assertIn("usos", funciones)
        self.assertIn("consulta:claude", funciones)
        self.assertEqual(funciones[comandos.index("/inventado")], "desconocido")
        self.assertTrue(all(x["canal"] == "texto" and x["bot"] == "jaime" for x in self.lineas()))

    def test_los_comandos_publicados_estan_cubiertos(self):
        spec = importlib.util.spec_from_file_location("utc_contador", AQUI / "update_telegram_commands.py")
        texto = (AQUI / "update_telegram_commands.py").read_text(encoding="utf-8")
        import re
        publicados = set(re.findall(r'"command": "([a-z_]+)"', texto))
        self.assertTrue(publicados)
        sin_cubrir = {c for c in publicados if f"/{c}" not in self.bot.ALIAS_COMANDOS
                      and self.bot.ruta_interna(c) not in self.bot.RUTAS_CONOCIDAS}
        self.assertEqual(sin_cubrir, set())

    def test_cada_boton_del_menu_y_los_prefijos(self):
        areas = [a for a, _, _ in self.bot.areas_del_perfil()]
        for a in areas:
            try:
                self.boton(f"menu:{a}")
            except Exception:
                pass
        for data in ("gas:ultimos", "cmp:x:y", "cal:5:z", "zzz:1:2"):
            try:
                self.boton(data)
            except Exception:
                pass
        lineas = self.lineas()
        self.assertEqual([x["funcion"] for x in lineas], areas + ["gastos", "compras", "calificar", "desconocido"])
        self.assertTrue(all(x["canal"] == "boton" for x in lineas))

    def test_frases_marcadas_por_su_manejador(self):
        for texto, funcion in (("agrega leche a la lista", "compras"), ("¿cuánta cuota queda?", "uso"),
                               ("¿cómo está la Pi?", "estado"), ("qué hora es", "hora"),
                               ("cuéntame un chiste", "consulta:auto")):
            self.mensaje(texto)
            self.assertEqual(self.lineas()[-1]["funcion"], funcion, texto)
        self.assertIn("auto", self.consultas)

    def test_no_autorizado_no_se_cuenta(self):
        self.bot.handle_update({"message": {"chat": {"id": 99}, "from": {"id": 99}, "text": "/menu"}})
        self.bot.handle_update({"callback_query": {"id": "q", "data": "menu:clima", "from": {"id": 99},
                                                   "message": {"chat": {"id": 99}}}})
        self.assertEqual(self.lineas(), [])


class Canal(Base):
    def test_voz_y_texto(self):
        self.dicho = "agrega huevos a la lista"
        self.mensaje(voz=True)
        self.mensaje("agrega huevos a la lista")
        self.assertEqual([(x["funcion"], x["canal"]) for x in self.lineas()], [("compras", "voz"), ("compras", "texto")])

    def test_voz_que_no_se_entiende(self):
        self.dicho = ""
        self.mensaje(voz=True)
        self.assertEqual(self.lineas()[-1]["canal"], "voz")
        self.assertEqual(self.lineas()[-1]["funcion"], "desconocido")


class SinTexto(Base):
    def test_el_texto_del_mensaje_no_queda(self):
        self.dicho = f"anota {SECRETO} en la lista"
        for t in (f"agrega {SECRETO}", f"/buscar {SECRETO}", f"/claude {SECRETO}", f"recuérdame {SECRETO}",
                  f"/inventado {SECRETO}"):
            try:
                self.mensaje(t)
            except Exception:
                pass
        self.mensaje(voz=True)
        self.assertGreaterEqual(len(self.lineas()), 6)
        self.assertNotIn(SECRETO, self.crudo())
        self.assertNotIn("4321", self.crudo())
        for x in self.lineas():
            self.assertEqual(set(x), {"t", "bot", "funcion", "canal", "resultado"})
            self.assertEqual(usos.funcion_valida(x["funcion"]), x["funcion"])

    def test_una_funcion_fuera_de_la_lista_queda_desconocida(self):
        r = usos.Registro(self.dir, "jaime")
        r.anotar(f"texto libre {SECRETO}", "texto", "ok")
        r.anotar("consulta:con espacios y cosas", "texto", "ok")
        self.assertEqual([x["funcion"] for x in self.lineas()], ["desconocido", "desconocido"])
        self.assertNotIn(SECRETO, self.crudo())


class EscritorQueNoFalla(Base):
    def test_carpeta_que_no_se_puede_escribir(self):
        bloqueo = Path(self.tmp.name) / "es-un-archivo"
        bloqueo.write_text("x", encoding="utf-8")
        self.bot.REGISTRO_USOS.carpeta = bloqueo / "usos"      # su padre es un archivo: mkdir falla siempre
        with self.assertLogs("botv3.usos", logging.WARNING) as registro:
            self.mensaje("/menu")
            self.mensaje("/ayuda")
            self.mensaje("agrega pan")
        self.assertEqual(len(registro.records), 1)              # una sola advertencia
        textos = [d.get("text") for m, d in self.enviados if m == "sendMessage"]
        self.assertTrue(any(t and t.startswith("🏠") for t in textos))     # /menu contestó
        self.assertTrue(len(textos) >= 3)

    def test_error_del_manejador_se_anota_y_se_relanza(self):
        def roto(*a, **k):
            raise RuntimeError("roto")
        self.bot.comando_estado = roto
        with self.assertRaises(RuntimeError):
            self.mensaje("/estado")
        self.assertEqual(self.lineas()[-1]["resultado"], "error")

    def test_error_contestado_cuenta_como_error(self):
        self.bot.safe_command = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caído"))
        self.mensaje("/estado")
        self.assertEqual(self.lineas()[-1]["resultado"], "error")
        self.mensaje("/menu")
        self.assertEqual(self.lineas()[-1]["resultado"], "ok")


class Resumen(unittest.TestCase):
    AHORA = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=_TMP.name)
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)

    def registro(self, bot, momentos_funciones):
        carpeta = self.d / bot
        reloj = {"t": self.AHORA}
        r = usos.Registro(carpeta, bot, reloj=lambda: reloj["t"])
        for momento, funcion, canal, resultado in momentos_funciones:
            reloj["t"] = momento
            r.anotar(funcion, canal, resultado)
        return carpeta

    def test_cuenta_por_funcion_canal_y_errores_y_lo_nunca_usado(self):
        h = lambda dias: self.AHORA - timedelta(days=dias)
        jaime = self.registro("jaime", [(h(1), "compras", "voz", "ok"), (h(2), "compras", "texto", "ok"),
                                        (h(3), "compras", "boton", "error"), (h(6.9), "uso", "texto", "ok"),
                                        (h(8), "clima", "boton", "ok"), (h(100), "buscar", "texto", "ok")])
        res = usos.resumen({"jaime": jaime}, {"jaime": ["compras", "uso", "clima", "buscar", "remoto", "ordenes"]}, self.AHORA)
        b = res["bots"]["jaime"]
        self.assertEqual(b["total"], 4)
        self.assertEqual(b["funciones"]["compras"], {"total": 3, "texto": 1, "voz": 1, "boton": 1, "error": 1})
        self.assertEqual(list(b["funciones"]), ["compras", "uso"])          # el de hace 8 días no entra
        self.assertEqual(b["nunca"], ["ordenes", "remoto"])                 # clima y buscar sí se usaron (antes)
        texto = usos.texto_resumen(res)
        self.assertIn("Jaime: 4 usos", texto)
        self.assertIn("🛒 compras: 3 (texto 1, voz 1, botón 1) · 1 con error", texto)
        self.assertIn("Sin usar nunca (en 180 días): 🔁 órdenes, 📱 Remote Control", texto)
        json.dumps(res, ensure_ascii=False)

    def test_pilar_ve_solo_lo_suyo_y_jaime_los_dos(self):
        hace = self.AHORA - timedelta(hours=2)
        jdir = Path(self.tmp.name) / "jaime-usos"
        pdir = Path(self.tmp.name) / "pilar-usos"
        jaime = cargar_bot("jaime", jdir, otros=f"pilar={pdir}")
        pilar = cargar_bot("pilar", pdir, otros=f"jaime={jdir}")       # Pilar ignora BOTV3_USOS_OTROS
        self.assertEqual(pilar.USOS_OTROS, {})
        usos.Registro(jdir, "jaime", reloj=lambda: hace).anotar("compras", "voz", "ok")
        usos.Registro(pdir, "pilar", reloj=lambda: hace).anotar("gastos", "texto", "ok")
        pilar.REGISTRO_USOS.publicar_catalogo(pilar.catalogo_usos())
        for b in (jaime, pilar):
            b.CHAT_ID = b.USER_ID = 7
            b.ahora_santiago = lambda: self.AHORA.astimezone(usos.TZ)
        enviados = {}
        jaime.send_text = lambda chat, t: enviados.__setitem__("jaime", t)
        pilar.send_text = lambda chat, t: enviados.__setitem__("pilar", t)
        jaime.comando_usos(7)
        pilar.comando_usos(7)
        self.assertIn("Jaime: 1 uso", enviados["jaime"])
        self.assertIn("Pilar: 1 uso", enviados["jaime"])
        self.assertIn("Pilar: 1 uso", enviados["pilar"])
        self.assertNotIn("Jaime", enviados["pilar"])
        # Sin la carpeta de Pilar montada, Jaime lo dice en vez de inventar un cero.
        sin = cargar_bot("jaime", jdir)
        sin.CHAT_ID = sin.USER_ID = 7
        sin.ahora_santiago = lambda: self.AHORA.astimezone(usos.TZ)
        sin.send_text = lambda chat, t: enviados.__setitem__("sin", t)
        sin.comando_usos(7)
        self.assertIn("Pilar: sin dato (no puedo leer su registro)", enviados["sin"])

    def test_bots_info_expone_el_mismo_resumen(self):
        spec = importlib.util.spec_from_file_location("bots_info_92", AQUI.parent / "pi" / "bots-info.py")
        bi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bi)
        hace = self.AHORA - timedelta(hours=1)
        carpetas = {"jaime": self.d / "j", "pilar": self.d / "p"}
        usos.Registro(carpetas["jaime"], "jaime", reloj=lambda: hace).anotar("uso", "texto", "ok")
        usos.Registro(carpetas["pilar"], "pilar", reloj=lambda: hace).anotar("compras", "boton", "ok")
        out = bi.usos_bots(["jaime", "pilar"], self.AHORA, usos, carpeta_de=lambda p: carpetas[p])
        self.assertEqual(out, usos.resumen(carpetas, None, self.AHORA))
        self.assertEqual(out["bots"]["pilar"]["funciones"]["compras"]["boton"], 1)
        self.assertIsNone(bi._cargar_usos("/no/existe/usos.py"))
        bi._cargar_usos = lambda *a: None                        # usos.py sin desplegar: no hay usos_bots
        self.assertIsNone(bi.usos_bots(["jaime"], self.AHORA, None, carpeta_de=lambda p: carpetas[p]))
        json.dumps(out, ensure_ascii=False)


class Rotacion(unittest.TestCase):
    def test_rotar_no_pierde_lineas_y_borra_solo_lo_vencido(self):
        with tempfile.TemporaryDirectory(dir=_TMP.name) as t:
            carpeta = Path(t) / "usos"
            reloj = {"t": datetime(2026, 1, 1, 12, tzinfo=timezone.utc)}
            r = usos.Registro(carpeta, "jaime", reloj=lambda: reloj["t"])
            escritas = []
            # Un uso cada 9 h durante 300 días: cruza diez cambios de mes.
            for k in range(800):
                reloj["t"] = datetime(2026, 1, 1, 12, tzinfo=timezone.utc) + timedelta(hours=9 * k)
                self.assertTrue(r.anotar("compras", "texto", "ok"))
                escritas.append(usos._local(reloj["t"]).isoformat(timespec="seconds"))
            ahora = reloj["t"]
            limite = usos._local(ahora) - timedelta(days=usos.RETENCION_DIAS)
            quedan = [x["t"].isoformat(timespec="seconds") for x in usos.leer(carpeta)]
            # Todo lo de los últimos 180 días está, en orden y sin repetidos.
            recientes = [x for x in escritas if datetime.fromisoformat(x) >= limite]
            self.assertEqual([x for x in quedan if datetime.fromisoformat(x) >= limite], recientes)
            self.assertEqual(len(quedan), len(set(quedan)))
            # Lo borrado es sólo de meses que terminaron antes del límite.
            for x in set(escritas) - set(quedan):
                m = usos._local(datetime.fromisoformat(x))
                self.assertLessEqual(usos._fin_del_mes(m.year, m.month), limite)
            self.assertTrue(set(escritas) - set(quedan))                # algo se borró
            self.assertEqual(sorted(p.name for p in carpeta.iterdir() if not usos.RE_ARCHIVO.fullmatch(p.name)), [])

    def test_rotar_ignora_lo_que_no_es_suyo(self):
        with tempfile.TemporaryDirectory(dir=_TMP.name) as t:
            carpeta = Path(t)
            for nombre in ("usos-2020-01.jsonl", "notas.txt", "usos-2020-01.jsonl.bak", "catalogo.json"):
                (carpeta / nombre).write_text("x\n", encoding="utf-8")
            borrados = usos.rotar(carpeta, datetime(2026, 10, 25, tzinfo=timezone.utc))
            self.assertEqual(borrados, ["usos-2020-01.jsonl"])
            self.assertEqual(sorted(p.name for p in carpeta.iterdir()), ["catalogo.json", "notas.txt", "usos-2020-01.jsonl.bak"])


if __name__ == "__main__":
    unittest.main()
