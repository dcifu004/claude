#!/usr/bin/env python3
"""Pruebas del encargo 51: consultas al usuario entre fases.

    NODO_PRUEBAS=1 python3 encargos/test_consultas.py

Usa el andamio de la 46c (`test_acciones_cola.Base`): carpeta temporal, `46-fixtures/`, tmux y lanzador de
mentira, reloj inyectado y avisos en una lista. La cola de verdad (`principal()`) corre con un motor de mentira
que escribe la revisión con títulos copiados de revisiones reales (52br1, 55r2, 57br1, 58r2).
El canal es de mentira: `SUGERIR_CONSULTA` devuelve ids con la forma de nodo-desplegar y los resultados del
escucha se escriben en un `resultados/` temporal, con el uid de la prueba como «dueño del escucha». Ninguna
prueba llama a nodo-desplegar, a Telegram ni al tmux del usuario, ni escribe en /opt/nodo/datos.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import sys
import threading
import tomllib
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ENCARGOS = Path(__file__).resolve().parent
PI = ENCARGOS.parent / "pi"
sys.path[:0] = [str(ENCARGOS), str(PI)]
import test_acciones_cola as ta  # noqa: E402
import test_matriz_cuota as mc  # noqa: E402

T, COLA_RUN = ta.T, ta.COLA_RUN
UID = os.getuid()

# Títulos reales, copiados de las revisiones del vault (archivo:línea).
GRAVE_57BR1 = "### 1. [Grave] Cambiar el interruptor mientras hay una edición automática pendiente pierde la edición"
MEDIA_52BR1 = "### 2. [Media] Las líneas de despliegue de «solo-avisar» y de «solo páginas» vuelven a salir de noche"
MEDIA_52BR1_B = "### 3. [Media] La prueba de instalación pasa igual con el nombre equivocado, y los caminos de la cola siguen sin prueba"
BAJA_52BR1 = "### 4. [Baja] `urgentes` quedó sin efecto: las dos ramas devuelven lo mismo"
IMPORTANTE_55R2 = "### 2. [Importante, pide decisión] El freno retoma la pausa de cuota el lunes a las 00:00, no cuando renueva la cuenta"


def revision(*titulos: str) -> str:
    cuerpo = "\n\n".join(f"{t}\n\nDetalle del hallazgo." for t in titulos)
    return f"# Revisión\n\n## Hallazgos, de más grave a menos grave\n\n{cuerpo}\n\nVEREDICTO: NO DESPLEGABLE\n"


SOLO_MEDIAS = revision(MEDIA_52BR1, MEDIA_52BR1_B, BAJA_52BR1)
CON_GRAVE = revision(GRAVE_57BR1, MEDIA_52BR1)


def setUpModule():
    ta.setUpModule()


def tearDownModule():
    ta.tearDownModule()


class Base(ta.Base):
    def setUp(self):
        super().setUp()
        cr = self.cr
        self.mensajes: list[tuple[str, str]] = []
        self.n_id = 0
        self.eventos: list[str] = []            # el orden en que la cola usó el canal y systemd
        self.falla: set[str] = set()            # las opciones que el canal no acepta (devuelve None, como _sugerir_real)
        self.falla_una_vez: set[str] = set()    # las que fallan solo la primera vez

        def sugerir(motivo, linea):
            op = re.search(r"consulta cola\w+ #\d: (aceptar|arreglar|saltar)", linea)[1]
            self.eventos.append(f"sugerir:{op}")
            if op in self.falla or op in self.falla_una_vez:
                self.falla_una_vez.discard(op)
                return None
            self.n_id += 1
            self.mensajes.append((motivo, linea))
            return f"20261011-1900{self.n_id:02d}-{self.n_id:04x}"
        cr.SUGERIR_CONSULTA = sugerir
        # El canal de la 71. Por defecto es el nodo-desplegar instalado hoy, que no conoce `consultar`: las pruebas
        # de la 51 corren así por la caída a los tres `sugerir`. `ConConsultar` lo enciende.
        self.con_consultar = False
        self.consultas: list[tuple[str, list]] = []     # lo que llegó a `consultar` (motivo, opciones)
        self.falla_consultar = 0                         # cuántas veces más `consultar` falla (devuelve None)

        def consultar(motivo, opciones):
            if not self.con_consultar:
                return cr.SIN_CONSULTAR
            self.eventos.append("consultar")
            if self.falla_consultar:
                self.falla_consultar -= 1
                return None
            self.n_id += 1
            self.consultas.append((motivo, list(opciones)))
            return f"20261011-1900{self.n_id:02d}-{self.n_id:04x}"
        cr.CONSULTAR_CONSULTA = consultar
        # systemd de mentira, con la forma de `systemctl --user list-timers --output=json` de la Pi (17-10).
        self.timers: list[str] = []
        self.systemd: list[list[str]] = []
        self.systemd_falla = False

        def systemd(argv):
            argv = list(argv)
            self.systemd.append(argv)
            self.eventos.append(" ".join(argv[:3]))
            P = lambda rc, out="": ta.subprocess.CompletedProcess(argv, rc, out, "")
            if argv[:3] == ["systemctl", "--user", "list-timers"]:
                patron = argv[-1].rstrip("*")
                return P(0, json.dumps([{"next": 1792243661095882, "left": 1792243661095882, "last": 0, "passed": 0, "unit": u,
                                         "activates": u.removesuffix(".timer") + ".service"} for u in self.timers if u.startswith(patron)]))
            if argv[:2] == ["systemd-run", "--user"]:
                if self.systemd_falla:
                    return P(1)
                self.timers.append(next(x for x in argv if x.startswith("--unit="))[len("--unit="):] + ".timer")
                return P(0)
            if argv[:3] == ["systemctl", "--user", "stop"]:
                self.timers = [u for u in self.timers if u not in argv[3:]]
                return P(0)
            raise AssertionError(f"systemd no esperado: {argv}")
        cr.SYSTEMD = systemd
        self.descansos: list[datetime] = []
        self.descanso = False
        cr.EN_DESCANSO = lambda m: (self.descansos.append(m), self.descanso)[1]
        self.resultados = self.tmp / "resultados"
        self.resultados.mkdir()
        cr.RESULTADOS_DESPLEGAR, cr.DUENO_RESULTADOS = self.resultados, UID
        self.ruta = self.manifiesto(texto=mc.MANIFIESTO_46)

    def correr(self, *argumentos, textos: dict | None = None, ruta: Path | None = None, sesion: str = "cola46"):
        """principal() con un motor que deja, por fase de revisión, el texto de `textos` (por defecto DESPLEGABLE)."""
        corridas, cr = [], self.cr

        def correr(cid, prompt, nombre_log, mod=None, herramientas=""):
            corridas.append(nombre_log)
            self.prompts[nombre_log] = prompt
            self.reloj += timedelta(minutes=5)
            if "rev" in nombre_log:
                et = nombre_log.rsplit("-", 1)[0]
                (self.tmp / f"{et}r-RESULTADO.md").write_text((textos or {}).get(nombre_log, "VEREDICTO: DESPLEGABLE\n"), encoding="utf-8")
            return {"rc": 0, "min": 5.0, "tokens": None, "sin_cuota": False, "modelo_real": None}
        self.prompts = getattr(self, "prompts", {})
        cr.correr = correr
        self.sesiones.add(sesion)
        with mock.patch.object(sys, "argv", [str(COLA_RUN), str(ruta or self.ruta), *argumentos]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = cr.principal()
        self.sesiones.discard(sesion)
        return rc, corridas

    def contestar(self, op: str, estado: str = "hecho", hora: str = "2026-10-11 19:20:00", ronda: int = -1, **cambios):
        """El resultado que escribe el escucha, con la forma de Escucha.cerrar(): en una ronda de `consultar`, el del
        toque en esa alternativa (`opcion` y `letra`); en una de tres `sugerir`, el del ✅ de ese mensaje."""
        r0 = self.vivo("cola46")["consulta"]["rondas"][ronda]
        if r0.get("canal") == "consultar":
            pid, letra = r0["id"], self.cr.RESPUESTAS[op].letra
            r = {"id": pid, "estado": estado, "detalle": f"el usuario eligió {letra} ({op})", "hora": hora}
            r |= {"opcion": op, "letra": letra} if estado == "hecho" else {}
            r |= cambios
            (self.resultados / f"{pid}.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
            return pid
        pid = r0["ids"][op]
        r = {"id": pid, "estado": estado, "detalle": "el usuario dice que lo corrió", "hora": hora} | cambios
        (self.resultados / f"{pid}.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        return pid

    def atender(self, **extra) -> list[dict]:
        entradas = dict(vivos_dir=self.vivos, manifiestos_dir=self.tmp, momento=self.reloj, tmux=ta.TMUX_FALSO,
                        lanzar=self.lanzar, resultados_dir=self.resultados, dueno=UID, carpeta_decisiones=self.tmp)
        return self.cr.atender_consultas(**(entradas | extra))

    def decisiones(self, et: str = "46a") -> str:
        ruta = self.tmp / f"{et}-decisiones.md"
        return ruta.read_text(encoding="utf-8") if ruta.exists() else ""

    def otra_esperando(self):
        """cola47 esperando su turno: un vivo fresco en «esperando», con la forma que escribe vivo()."""
        v = {"nombre": "cola47", "estado": "esperando", "esperando": "cola46", "escrito": mc.iso(self.reloj),
             "etapas": ["47"], "lanzada": mc.iso(self.reloj)}
        (self.vivos / "cola47.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")

    def preguntar(self):
        rc, corridas = self.correr(textos={"46a-rev1": SOLO_MEDIAS})
        self.assertEqual((rc, corridas), (self.cr.CODIGO_EN_CONSULTA, ["46a-autor", "46a-rev1"]))
        return self.vivo("cola46")


# ---------------------------------------------------------------- C1

class C1Disparador(Base):
    def test_solo_medias_y_bajas_pregunta_y_la_cola_queda_estacionada(self):
        v = self.preguntar()
        self.assertEqual((v["estado"], v["reanuda_desde"], v["consultas_n"]), ("en_consulta", "46a:fix1", 1))
        c = v["consulta"]
        self.assertEqual((c["n"], c["etapa"], c["fase"], c["defecto"]), (1, "46a", "rev1", "arreglar"))
        self.assertEqual(c["plazo"], (datetime.fromisoformat(c["desde"]) + timedelta(hours=2)).isoformat())
        self.assertEqual(sorted(c["rondas"][0]["ids"]), ["aceptar", "arreglar", "saltar"])
        self.assertEqual(len(self.mensajes), 3)                         # tres mensajes por ronda, no más
        self.assertLessEqual(len(c["pregunta"]), 600)
        self.assertIn("[Media] Las líneas de despliegue", c["pregunta"])
        self.assertIn("[Baja] urgentes quedó sin efecto", c["pregunta"])
        self.assertIn("en consulta al usuario", v["motivo_pausa"])
        self.assertNotIn("46a-fix1", self.prompts)
        self.assertEqual(self.avisos, [])                                # ni un aviso más que los tres botones

    def test_un_grave_no_pregunta_y_va_al_arreglo(self):
        rc, corridas = self.correr(textos={"46a-rev1": CON_GRAVE})
        self.assertEqual(corridas[:3], ["46a-autor", "46a-rev1", "46a-fix1"])
        self.assertEqual((rc, self.mensajes, self.vivo("cola46")["estado"]), (0, [], "terminada"))
        self.assertIn("trae un [Grave]: va al arreglo", self.bitacora.read_text(encoding="utf-8"))

    def test_una_etiqueta_que_no_es_media_ni_baja_no_pregunta(self):
        rc, corridas = self.correr(textos={"46a-rev1": revision(IMPORTANTE_55R2, MEDIA_52BR1)})
        self.assertEqual((rc, self.mensajes, corridas[2]), (0, [], "46a-fix1"))

    def test_sin_titulos_con_gravedad_es_como_antes(self):
        rc, corridas = self.correr(textos={"46a-rev1": "VEREDICTO: NO DESPLEGABLE\n"})
        self.assertEqual((rc, self.mensajes, corridas[2]), (0, [], "46a-fix1"))

    def test_la_ultima_revision_no_pregunta_no_hay_arreglo_detras(self):
        textos = {"46a-rev1": CON_GRAVE, "46a-rev2": CON_GRAVE, "46a-rev3": SOLO_MEDIAS}
        rc, corridas = self.correr(textos=textos)
        self.assertEqual((rc, self.mensajes, corridas[-1]), (1, [], "46a-rev3"))

    def test_tercera_pregunta_en_la_misma_cola_no_se_hace(self):
        self.preguntar()                                                 # #1 en 46a:rev1
        self.contestar("arreglar")
        self.atender()
        rc, corridas = self.correr("--desde", "46a:fix1", textos={"46a-rev2": SOLO_MEDIAS})
        self.assertEqual((rc, corridas), (6, ["46a-fix1", "46a-rev2"]))  # #2 en 46a:rev2
        self.assertEqual(self.vivo("cola46")["consultas_n"], 2)
        self.contestar("arreglar", hora="2026-10-11 19:50:00")
        self.atender()
        antes = len(self.mensajes)
        rc, corridas = self.correr("--desde", "46a:fix2", textos={"46b-rev1": SOLO_MEDIAS})
        self.assertEqual(corridas[:5], ["46a-fix2", "46a-rev3", "46b-autor", "46b-rev1", "46b-fix1"])
        self.assertEqual((rc, len(self.mensajes)), (0, antes))           # la tercera no se hizo: fue al arreglo
        self.assertIn("ya hizo 2 consultas (tope 2)", self.bitacora.read_text(encoding="utf-8"))

    def test_revisiones_reales_del_vault(self):
        leer = lambda n: (ENCARGOS / n).read_text(encoding="utf-8")
        for archivo, pregunta in (("57br1-RESULTADO.md", False), ("52br1-RESULTADO.md", False),
                                  ("55r2-RESULTADO.md", False), ("58r2-RESULTADO.md", True)):
            with self.subTest(archivo=archivo):
                self.assertEqual(self.cr.disparador(leer(archivo))[0], pregunta)
        # 58r2: «[Media, y es lo que impide el veredicto]» y cuatro «[Menor]»: se habría preguntado.
        self.assertEqual([g for g, _ in self.cr.hallazgos(leer("58r2-RESULTADO.md"))], ["media", "media", "baja", "baja", "baja", "baja"])


# ---------------------------------------------------------------- C2

class C2Descanso(Base):
    def test_en_descanso_no_pregunta_y_si_es_la_ultima_se_arregla(self):
        self.descanso = True
        rc, corridas = self.correr(textos={"46a-rev1": SOLO_MEDIAS})
        self.assertEqual((rc, self.mensajes, corridas[:3]), (0, [], ["46a-autor", "46a-rev1", "46a-fix1"]))
        self.assertEqual(self.descansos, [T + timedelta(minutes=10)])    # se consultó con el reloj inyectado
        self.assertIn("arreglar («Que lo arregle») · quién: defecto, en silencio: modo descanso", self.decisiones())
        self.assertNotIn("consultas_n", self.vivo("cola46"))             # no cuenta como pregunta

    def test_en_descanso_con_otras_esperando_salta_en_silencio(self):
        self.descanso = True
        self.otra_esperando()
        rc, corridas = self.correr(textos={"46a-rev1": SOLO_MEDIAS})
        v = self.vivo("cola46")
        self.assertEqual((rc, self.mensajes, corridas), (6, [], ["46a-autor", "46a-rev1"]))
        self.assertEqual((v["estado"], v["consulta"]["respuesta"], v["reanuda_desde"]), ("en_consulta", "saltar", "46a:fix1"))
        self.assertIn("saltar («Saltar»)", self.decisiones())
        self.assertEqual(self.atender(), [])                             # ya contestada: el timer no la toca

    def test_con_la_biblioteca_real_de_descanso_y_reloj_inyectado(self):
        spec = importlib.util.spec_from_file_location("descanso_prueba_51", PI / "descanso.py")
        mod = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, {"NODO_DESCANSO_CONFIG": str(self.tmp / "no-hay.toml"),
                                          "NODO_DESCANSO_CACHE": str(self.tmp), "NODO_DESCANSO_STATE": str(self.tmp)}):
            spec.loader.exec_module(mod)
        self.cr.EN_DESCANSO, self.cr._DESCANSO_MOD = None, mod
        self.assertTrue(self.cr.en_descanso(datetime.fromisoformat("2026-10-13T02:00:00-03:00")))    # martes 02:00
        self.assertFalse(self.cr.en_descanso(datetime.fromisoformat("2026-10-13T18:55:00-03:00")))
        self.reloj = datetime.fromisoformat("2026-10-13T01:30:00-03:00")
        rc, corridas = self.correr(textos={"46a-rev1": SOLO_MEDIAS})
        self.assertEqual((self.mensajes, corridas[2]), ([], "46a-fix1"))


# ---------------------------------------------------------------- C3

class C3Respuestas(Base):
    def test_aceptar_reanuda_sin_arreglo_y_anota_la_decision(self):
        self.preguntar()
        pid = self.contestar("aceptar")
        (r,) = self.atender()
        self.assertEqual((r["accion"], r["reanudar"]["ok"], r["reanudar"]["desde"]), ("aceptar", True, "46a:fix1"))
        self.assertEqual(self.lanzados[-1][-2:], ["--desde", "46a:fix1"])
        v = self.vivo("cola46")
        self.assertEqual(v["aceptadas_usuario"][0] | {"momento": None}, {"etapa": "46a", "tras": "rev1", "pedido": pid, "momento": None})
        self.assertIn(f"aceptar («Aceptar y seguir») · quién: el usuario (✅ en Telegram, pedido {pid})", self.decisiones())
        self.sesiones.discard("cola46")
        rc, corridas = self.correr("--desde", "46a:fix1")
        self.assertEqual((rc, corridas[0]), (0, "46b-autor"))            # 46a no se arregló: siguió con la etapa siguiente
        self.assertIn("aceptada por el usuario tras rev1", self.bitacora.read_text(encoding="utf-8"))

    def test_arreglar_reanuda_con_el_arreglo(self):
        self.preguntar()
        self.contestar("arreglar")
        (r,) = self.atender()
        self.assertEqual((r["accion"], r["reanudar"]["ok"]), ("arreglar", True))
        self.sesiones.discard("cola46")
        rc, corridas = self.correr("--desde", "46a:fix1")
        self.assertEqual((rc, corridas[:2]), (0, ["46a-fix1", "46a-rev2"]))
        self.assertIn("arreglar («Que lo arregle») · quién: el usuario", self.decisiones())
        self.assertIn("encargos/46a-decisiones.md", self.prompts["46a-fix1"])   # el arreglo la recibe

    def test_saltar_deja_la_cola_estacionada_y_reanudar_la_retoma(self):
        self.preguntar()
        self.contestar("saltar")
        (r,) = self.atender()
        v = self.vivo("cola46")
        self.assertEqual((r["accion"], self.lanzados, v["estado"], v["consulta"]["respuesta"]), ("saltar", [], "en_consulta", "saltar"))
        self.assertIn("se retoma con Reanudar", v["motivo_pausa"])
        self.assertIn("saltar («Saltar») · quién: el usuario", self.decisiones())
        self.assertEqual(self.atender(), [])
        res = self.accion("reanudar", "cola46")                          # 46c: el botón Reanudar
        self.assertEqual((res["ok"], res["desde"]), (True, "46a:fix1"))

    def test_rechazar_no_es_respuesta_y_el_primer_ok_gana(self):
        self.preguntar()
        self.contestar("aceptar", estado="rechazado")
        self.assertEqual(self.atender()[0]["accion"], "nada")
        self.contestar("saltar", hora="2026-10-11 19:30:00")
        self.contestar("arreglar", hora="2026-10-11 19:31:00")
        self.assertEqual(self.atender()[0]["accion"], "saltar")

    def test_un_resultado_que_no_es_del_escucha_root_se_ignora_y_se_anota(self):
        self.preguntar()
        self.contestar("aceptar")                                        # escrito por este usuario, no por root
        (r,) = self.atender(dueno=0)
        self.assertEqual((r["accion"], self.lanzados), ("nada", []))
        self.assertIn("respuesta IGNORADA (no viene del chat del usuario): aceptar", self.decisiones())
        self.assertIn("no lo escribió el escucha de nodo-desplegar (no es de root)", self.decisiones())
        self.atender(dueno=0)
        self.assertEqual(self.decisiones().count("IGNORADA"), 1)        # se anota una vez, no en cada pasada
        self.assertIsNone(self.vivo("cola46")["consulta"].get("respuesta"))

    def test_un_resultado_con_otro_id_o_enlazado_se_ignora(self):
        self.preguntar()
        pid = self.contestar("aceptar", id="20261011-190000-ffff")
        self.assertEqual(self.atender()[0]["accion"], "nada")
        os.unlink(self.resultados / f"{pid}.json")
        ajeno = self.tmp / "ajeno.json"
        ajeno.write_text(json.dumps({"id": pid, "estado": "hecho"}), encoding="utf-8")
        os.symlink(ajeno, self.resultados / f"{pid}.json")
        self.assertEqual(self.atender()[0]["accion"], "nada")
        self.assertEqual(self.decisiones().count("IGNORADA"), 2)

    def test_una_aceptacion_fabricada_en_el_vivo_no_salta_el_arreglo(self):
        self.preguntar()
        v = self.vivo("cola46")
        v["aceptadas_usuario"] = [{"etapa": "46a", "tras": "rev1", "pedido": "20261011-190001-0001"}]   # sin ✅ del escucha
        (self.vivos / "cola46.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
        rc, corridas = self.correr("--desde", "46a:fix1")
        self.assertEqual(corridas[0], "46a-fix1")
        self.assertIn("no se pudo verificar", self.bitacora.read_text(encoding="utf-8"))

    def test_con_la_sesion_viva_no_se_toca(self):
        self.preguntar()
        self.contestar("aceptar")
        self.sesiones.add("cola46")
        self.assertEqual((self.atender()[0]["accion"], self.lanzados), ("nada", []))


# ---------------------------------------------------------------- C4

class C4Plazo(Base):
    def test_al_vencer_la_ronda_se_vuelve_a_preguntar_hasta_el_plazo(self):
        self.preguntar()
        self.reloj += timedelta(minutes=20)
        self.assertEqual(self.atender()[0]["accion"], "nada")
        for k in range(3):
            self.reloj += timedelta(minutes=30)
            self.assertEqual(self.atender()[0]["accion"], "ronda", k)
        self.assertEqual(len(self.mensajes), 12)                         # 4 rondas de 3 en las 2 h
        self.reloj += timedelta(minutes=5)
        self.assertEqual(self.atender()[0]["accion"], "nada")
        self.contestar("aceptar", ronda=0)                               # un botón de la primera ronda también vale
        self.assertEqual(self.atender()[0]["accion"], "aceptar")

    def test_plazo_vencido_con_otras_colas_esperando_salta(self):
        self.preguntar()
        self.reloj += timedelta(hours=2, minutes=1)
        self.otra_esperando()
        (r,) = self.atender()
        v = self.vivo("cola46")
        self.assertEqual((r["accion"], self.lanzados, v["estado"]), ("saltar", [], "en_consulta"))
        self.assertIn("defecto: venció el plazo de 2 h; hay otras colas esperando (cola47)", self.decisiones())

    def test_plazo_vencido_siendo_la_ultima_va_al_arreglo(self):
        self.preguntar()
        self.reloj += timedelta(hours=2, minutes=1)
        (r,) = self.atender()
        self.assertEqual((r["accion"], self.lanzados[-1][-2:]), ("arreglar", ["--desde", "46a:fix1"]))
        self.assertIn("defecto: venció el plazo de 2 h; no hay otras colas esperando", self.decisiones())

    def test_descanso_con_la_ronda_vencida_aplica_el_defecto_sin_preguntar(self):
        self.preguntar()
        self.reloj += timedelta(minutes=31)
        self.descanso = True
        (r,) = self.atender()
        self.assertEqual((r["accion"], len(self.mensajes)), ("arreglar", 3))

    def test_por_la_linea_de_comandos(self):
        self.preguntar()
        self.cr.E = self.tmp
        self.cr.RESULTADOS_DESPLEGAR, self.cr.DUENO_RESULTADOS = self.resultados, UID
        self.contestar("saltar")
        rc, salida, _ = self.por_comandos("--consultas")
        self.assertEqual((rc, salida[0]["accion"]), (0, "saltar"))


# ---------------------------------------------------------------- C5

class C5Despliegue(Base):
    def preparar(self, aceptada: bool, propios: list[str] | None):
        cr = self.cr
        cr.MANIFIESTO = tomllib.loads(mc.MANIFIESTO_46)
        cr.VIVO.clear()
        cr.VIVO.update(nombre="cola46", estado="desplegando")
        if aceptada:
            cr.VIVO["aceptadas_usuario"] = [{"etapa": "46a", "tras": "rev1", "pedido": "20261011-190001-0001"}]
        cr.GIT_BASE.clear()
        if propios is not None:
            cr.GIT_BASE["46a:fases"] = [{"fase": "autor", "antes": "a", "despues": "b"}]
            git = type("G", (), {"git": staticmethod(lambda *a: type("R", (), {"stdout": "\0".join(propios).encode()})())})
            cr._vers = lambda: type("V", (), {"abrir": staticmethod(lambda: git)})
        self.ordenes = []
        real = self.proceso

        def proceso(cmd, *a, **k):
            if list(cmd)[:1] == ["nodo-desplegar"]:
                self.ordenes.append(list(cmd))
                return ta.subprocess.CompletedProcess(cmd, 1 if cmd[1] == "esperar" else 0, "20261011-190500-abcd\n", "")
            return real(cmd, *a, **k)
        cr.subprocess.run = staticmethod(proceso)
        cr.registrar_aviso = lambda *a: None

    def foto(self, cambia: bool) -> tuple[dict, dict]:
        antes = {"entradas": {"bin-x": "111"}, "fuentes": {"bin-x": "pi/x.py"}, "paginas": {}, "sin_catalogo": set()}
        return antes, antes | {"entradas": {"bin-x": "222" if cambia else "111"}}

    def test_sin_aceptacion_el_despliegue_pide_su_ok_como_siempre(self):
        self.preparar(False, ["pi/x.py"])
        self.cr.desplegar(*self.foto(True))
        self.assertEqual(self.ordenes[0][:3], ["nodo-desplegar", "pedir", "bin-x=222"])
        self.assertEqual(self.ordenes[1][:2], ["nodo-desplegar", "esperar"])

    def test_con_aceptacion_y_root_no_se_pide_ni_se_manda_la_linea(self):
        self.preparar(True, ["pi/x.py"])
        self.cr.desplegar(*self.foto(True))
        self.assertEqual(self.ordenes, [])
        (aviso,) = self.avisos
        self.assertIn("una aceptación no autoriza eso: no se pidió el despliegue", aviso[0])

    def test_con_aceptacion_y_secretos_no_se_despliega_ni_una_pagina(self):
        self.preparar(True, ["secretos/telegram.env"])
        self.cr.desplegar(*self.foto(False))
        self.assertEqual(self.ordenes, [])
        self.assertIn("toca root o secretos", self.bitacora.read_text(encoding="utf-8"))

    def test_con_aceptacion_y_sin_diff_verificable_tampoco(self):
        self.preparar(True, None)
        self.cr.desplegar(*self.foto(False))
        self.assertEqual(self.ordenes, [])

    def test_con_aceptacion_sin_root_termina_como_siempre(self):
        self.preparar(True, ["encargos/46a-RESULTADO.md"])
        self.cr.desplegar(*self.foto(False))
        self.assertEqual(self.ordenes, [])
        self.assertIn("no cambió nada que desplegar", self.avisos[0][0])


# ---------------------------------------------------------------- invariantes

class Invariantes(Base):
    def test_la_pregunta_hostil_sale_escapada_y_sugerir_real_la_acepta(self):
        hostiles = ["<script>alert(1)</script>", "uno\ndos", "'; rm -rf ~ #", "XXX TODO", "‮evil", "a" * 400]
        texto = revision(*[f"### {k}. [Media] {t}" for k, t in enumerate(hostiles * 5, 1)])
        ok, _, h = self.cr.disparador(texto)
        pregunta = self.cr.armar_pregunta("cola46", "46a", "rev1", 1, h)
        self.assertTrue(ok)
        self.assertLessEqual(len(pregunta), 600)
        for malo in ("<", ">", "\n", "'", "‮", "XXX", "TODO"):
            self.assertNotIn(malo, pregunta)
        # El `sugerir` de verdad (pi/nodo-desplegar.py), con su validación, sin dejar el pedido en el spool.
        spec = importlib.util.spec_from_file_location("nodo_desplegar_51", PI / "nodo-desplegar.py")
        nd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nd)
        dejados = []
        nd._dejar = lambda pedido: dejados.append(pedido) or 0
        # Al canal va el resumen de vocabulario cerrado (51r1, hallazgo 1), nunca la pregunta con los títulos.
        resumen = self.cr.resumen_canal("46a", "rev1", self.cr.conteo(h))
        for op, (motivo, linea) in self.cr.lineas_consulta("cola46", 1, resumen).items():
            self.assertEqual(nd.sugerir(["--motivo", motivo, "--", linea]), 0)
            self.assertEqual(shlex.split(linea)[0], "echo")
            self.assertEqual(len(shlex.split(linea)), 2)                # un solo argumento: no hay otro comando
            self.assertLessEqual(len(motivo), 200)
        self.assertEqual([p["tipo"] for p in dejados], ["sugerir"] * 3)
        self.assertIn("consulta cola46 #1: aceptar · etapa 46a, rev1 NO DESPLEGABLE sin graves: 30 [Media].", dejados[0]["comando"])
        for p in dejados:
            for t in ("script", "rm -rf", "evil", "aaaa", "dos"):
                self.assertNotIn(t, p["comando"] + p["motivo"])
        for malo in ("../x", "cola46\n", "x'; rm"):
            with self.assertRaises(ValueError):
                self.cr.resumen_canal(malo, "rev1", {"media": 1})
            with self.assertRaises(ValueError):
                self.cr.lineas_consulta(malo, 1, resumen)

    def test_nombres_y_respuestas_hostiles(self):
        self.preguntar()
        v = self.vivo("cola46")
        v["consulta"]["rondas"][0]["ids"]["root"] = "20261011-190009-0009"
        (self.vivos / "cola46.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
        (self.resultados / "20261011-190009-0009.json").write_text(json.dumps({"id": "20261011-190009-0009", "estado": "hecho"}))
        self.assertEqual(self.atender()[0]["accion"], "nada")
        self.assertIn("root: no es una de las tres respuestas", self.decisiones())
        v = self.vivo("cola46")
        v["consulta"]["etapa"] = "../x"
        (self.vivos / "cola46.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
        self.assertIn("no tiene la forma", self.atender()[0]["detalle"])
        with self.assertRaises(ValueError):
            self.cr.anotar_decision("../x", "- algo", self.tmp)
        for nombre in ta.HOSTILES[:6]:
            self.assertIsNone(self.cr.leer_resultado(nombre, self.resultados, UID)[0])

    def test_decisiones_se_anexan_con_candado_desde_varios_hilos(self):
        hilos = [threading.Thread(target=self.cr.anotar_decision, args=("46a", f"- línea {k}", self.tmp)) for k in range(20)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        texto = self.decisiones()
        self.assertEqual(texto.count("# Decisiones del usuario"), 1)
        self.assertEqual(sorted(x for x in texto.splitlines() if x.startswith("- línea")), sorted(f"- línea {k}" for k in range(20)))

    def test_el_panel_ofrece_reanudar_a_una_cola_en_consulta(self):
        self.preguntar()
        botones = self.cr.botones_colas(vivos_dir=self.vivos, viva=lambda n: False, manifiestos_dir=self.tmp,
                                        momento=self.reloj, timers_todos=[])
        self.assertIn("reanudar", botones["cola46"]["acciones"])

    def test_la_plantilla_de_revision_pide_los_titulos_y_respeta_las_decisiones(self):
        txt = (ENCARGOS / "revision-plantilla-v2.md").read_text(encoding="utf-8")
        self.assertIn("`### 1. [Grave] …`, `### 2. [Media] …` o `### 3. [Baja] …`", txt)
        self.assertIn("Lo decidido ahí no se vuelve a marcar como hallazgo", txt)
        self.assertEqual(set(__import__("re").findall(r"\{[A-Z]+\}", txt)), {"{ID}", "{ENCARGO}", "{AUTOR}", "{REVISOR}", "{EXTRA}", "{SUITES}", "{DIFF}"})


# ---------------------------------------------------------------- arreglos de la vuelta 1 (51r1)

# Un título con la forma de los reales, pero con una ruta del vault y un dato personal (lo que 51r1 reprodujo).
RUTA_51R1 = "### 5. [Baja] /opt/nodo/datos/srv/vault_personal/20-Personas/ficha.md trae el RUT 12.345.678-9 sin enmascarar"
CON_RUTA = revision(MEDIA_52BR1, MEDIA_52BR1_B, BAJA_52BR1, RUTA_51R1)
# Lo único que puede viajar por `sugerir` (motivo y línea), armado con el vocabulario cerrado de la cola.
MOTIVO_CERRADO = re.compile(r"❓ Consulta cola46 #[12]: tocar ✅ en ESTE mensaje = «(Aceptar y seguir|Que lo arregle|Saltar)»\. "
                            r"❌ no cuenta como respuesta\.( El resumen va en el mensaje de «Aceptar y seguir»\.)?")
LINEA_CERRADA = re.compile(r"echo 'consulta cola46 #[12]: (arreglar|saltar|aceptar · etapa 46a, rev[12] NO DESPLEGABLE sin "
                           r"graves: (\d+ \[Media\])?( y )?(\d+ \[Baja\])?\. Los títulos están en encargos/46ar[12]-RESULTADO\.md "
                           r"\(no salen del volumen cifrado\)\. Sin respuesta en 2 h: saltar si hay otras colas esperando; si no, "
                           r"que lo arregle\.)'")
SENSIBLES = ("/opt/nodo", "vault_personal", "20-Personas", "RUT", "12.345.678", "Las líneas de despliegue", "urgentes",
             "La prueba de instalación")


class Hallazgo1NadaDeLaRevisionFueraDelVolumen(Base):
    """51r1, hallazgo 1: lo que va a `sugerir` termina en el spool, en /var/lib/nodo-desplegar/pendientes.json y en el
    journal del escucha root. Se prueba con el escucha de verdad (pi/nodo-desplegar.py) apuntado a un temporal."""

    def escucha(self):
        spec = importlib.util.spec_from_file_location("nodo_desplegar_51r1", PI / "nodo-desplegar.py")
        nd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nd)
        nd.ESTADO = self.tmp / "var-lib-nodo-desplegar"
        nd.ESTADO.mkdir()
        spool, journal = [], []
        nd._dejar = lambda pedido: spool.append(json.dumps(pedido, ensure_ascii=False)) or 0
        nd.log = journal.append                                          # lo que iría a `logger -t nodo-desplegar`
        e = object.__new__(nd.Escucha)                                   # sin __init__: no lee /etc ni el token
        e.chat, e.pend, e.espera, e.offset, e.envios, e.arranque = "1", {}, {}, 0, [], "arranque-de-prueba"
        e.tg = lambda metodo, **k: {"message_id": 7}
        return nd, e, spool, journal

    def pasar_por_el_escucha(self, mensajes):
        """Cada (motivo, línea) por el `sugerir` del CLI y por `preparar_sugerencia` del escucha, como en la Pi."""
        nd, e, spool, journal = self.escucha()
        for k, (motivo, linea) in enumerate(mensajes):
            self.assertEqual(nd.sugerir(["--motivo", motivo, "--", linea]), 0)
            self.assertTrue(e.preparar_sugerencia(f"20261011-1910{k:02d}-{k:04x}", UID, json.loads(spool[-1])))
        return (nd.ESTADO / "pendientes.json").read_text(encoding="utf-8"), "\n".join(spool), "\n".join(journal)

    def test_la_consulta_no_lleva_titulos_y_el_escucha_real_no_los_guarda(self):
        rc, _ = self.correr(textos={"46a-rev1": CON_RUTA})
        self.assertEqual(rc, 6)
        self.assertEqual(len(self.mensajes), 3)
        for motivo, linea in self.mensajes:
            self.assertRegex(motivo, f"^{MOTIVO_CERRADO.pattern}$")
            self.assertRegex(linea, f"^{LINEA_CERRADA.pattern}$")
        self.assertIn("sin graves: 2 [Media] y 2 [Baja].", self.mensajes[0][1])   # los cuenta, no los copia
        pendientes, spool, journal = self.pasar_por_el_escucha(self.mensajes)
        for donde, texto in (("pendientes.json", pendientes), ("spool", spool), ("journal", journal)):
            for s in SENSIBLES:
                self.assertNotIn(s, texto, f"{s!r} llegó a {donde}")
        # La pregunta con los títulos sí queda, pero dentro del volumen: en el vivo.
        self.assertIn("/opt/nodo/datos/srv/vault_personal/20-Personas", self.vivo("cola46")["consulta"]["pregunta"])

    def test_el_detector_no_es_vacuo_la_pregunta_vieja_si_se_habria_guardado(self):
        # Control: con lo que mandaba la versión anterior (la pregunta en la línea), el mismo escucha sí la guarda.
        _, _, h = self.cr.disparador(CON_RUTA)
        pregunta = self.cr.armar_pregunta("cola46", "46a", "rev1", 1, h)
        viejo = [("❓ Consulta cola46 #1", "echo " + shlex.quote(f"consulta cola46 #1: aceptar · {pregunta}"))]
        pendientes, spool, journal = self.pasar_por_el_escucha(viejo)
        self.assertIn("/opt/nodo/datos/srv/vault_personal/20-Personas", pendientes)
        self.assertIn("/opt/nodo/datos/srv/vault_personal/20-Personas", spool)
        self.assertIn("[Media] Las líneas", journal)                     # los primeros 120 caracteres: ya trae un título

    def test_las_rondas_siguientes_rehacen_el_resumen_y_no_copian_el_vivo(self):
        self.preguntar()
        v = self.vivo("cola46")
        v["consulta"]["pregunta"] = "/opt/nodo/datos/srv/vault_personal/20-Personas RUT 12.345.678-9"   # un vivo alterado
        (self.vivos / "cola46.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
        self.reloj += timedelta(minutes=31)
        self.assertEqual(self.atender()[0]["accion"], "ronda")
        self.assertEqual(len(self.mensajes), 6)
        for motivo, linea in self.mensajes[3:]:
            self.assertRegex(linea, f"^{LINEA_CERRADA.pattern}$")
            for s in SENSIBLES:
                self.assertNotIn(s, motivo + linea)


class Hallazgo2ElTimerQueRecogeLaRespuesta(Base):
    """51r1, hallazgo 2: nadie instalaba consultas.timer. Ahora la cola arma un timer transitorio de usuario antes de
    preguntar, verifica que quedó activo, y la última pasada sin consultas abiertas lo detiene."""

    def armado(self) -> list[str]:
        (argv,) = [a for a in self.systemd if a[:2] == ["systemd-run", "--user"]]
        return argv

    def test_arma_el_timer_antes_de_preguntar_y_lo_verifica(self):
        self.preguntar()
        argv = self.armado()
        self.assertRegex(self.timers[0], r"^encargos-consultas-\d{8}-\d{6}-[0-9a-f]{4}\.timer$")
        for p in ("--on-active=300s", "--on-unit-active=300s", "Type=oneshot", "KillMode=process"):
            self.assertIn(p, argv)
        self.assertEqual(argv[argv.index("--") + 1:], ["/usr/bin/python3", str(COLA_RUN.resolve()), "--consultas"])
        # Primero se mira si ya hay uno, se arma, se verifica que systemd lo lista; recién entonces el primer mensaje.
        i_sug = self.eventos.index("sugerir:aceptar")
        self.assertEqual(self.eventos[:i_sug], ["systemctl --user list-timers",
                                                f"systemd-run --user --unit={self.timers[0].removesuffix('.timer')}",
                                                "systemctl --user list-timers"])

    def test_la_orden_del_timer_procesa_un_resultado_del_escucha_y_lo_detiene(self):
        self.preguntar()
        tail = self.armado()[self.armado().index("--") + 1:]
        self.assertEqual(tail[:2], ["/usr/bin/python3", str(COLA_RUN.resolve())])
        self.cr.E = self.tmp
        self.cr.RESULTADOS_DESPLEGAR, self.cr.DUENO_RESULTADOS = self.resultados, UID
        pid = self.contestar("aceptar")
        rc, salida, _ = self.por_comandos(*tail[2:])                     # lo que corre el timer: cola-run.py --consultas
        self.assertEqual((rc, salida[0]["accion"], salida[0]["reanudar"]["desde"]), (0, "aceptar", "46a:fix1"))
        self.assertIn(f"pedido {pid}", self.decisiones())
        self.assertEqual(self.timers, [])                                # ya no quedan consultas abiertas: se detuvo
        self.assertTrue(any(a[:3] == ["systemctl", "--user", "stop"] for a in self.systemd))

    def test_con_la_consulta_abierta_el_timer_sigue(self):
        self.preguntar()
        self.reloj += timedelta(minutes=5)
        self.assertEqual(self.atender()[0]["accion"], "nada")
        self.assertEqual(len(self.timers), 1)
        self.assertFalse(any(a[:3] == ["systemctl", "--user", "stop"] for a in self.systemd))

    def test_sin_timer_no_se_pregunta_y_se_aplica_el_defecto(self):
        self.systemd_falla = True
        rc, corridas = self.correr(textos={"46a-rev1": SOLO_MEDIAS})
        self.assertEqual((rc, self.mensajes, corridas[:3]), (0, [], ["46a-autor", "46a-rev1", "46a-fix1"]))
        self.assertIn("defecto: no se pudo armar el timer que recoge la respuesta", self.decisiones())

    def test_un_reinicio_se_lleva_el_timer_y_la_proxima_cola_lo_rearma(self):
        self.preguntar()
        self.timers.clear()                                              # reinicio: el timer transitorio no vuelve
        otra = self.manifiesto(texto=mc.MANIFIESTO_46.replace("46", "47"))
        rc, _ = self.correr(ruta=otra, sesion="cola47")
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.timers), 1)
        self.contestar("saltar")
        self.assertEqual(self.atender()[0]["accion"], "saltar")
        self.assertEqual(self.timers, [])

    def test_la_cola_que_parte_sin_consultas_ajenas_no_toca_systemd(self):
        rc, _ = self.correr()
        self.assertEqual((rc, self.systemd), (0, []))


class Hallazgo3RondaCompletaONada(Base):
    """51r1, hallazgo 3: una ronda a medias no estaciona la cola; en las rondas siguientes se reintenta lo que falta
    sin mover el plazo."""

    def a_medias(self, falla: frozenset, otra: bool):
        self.falla = set(falla)
        if otra:
            self.otra_esperando()
        rc, corridas = self.correr(textos={"46a-rev1": SOLO_MEDIAS})
        v = self.vivo("cola46")
        llegaron = 3 - len(falla)
        self.assertEqual(len(self.mensajes), llegaron)
        self.assertEqual(self.eventos.count("sugerir:aceptar") + self.eventos.count("sugerir:arreglar")
                         + self.eventos.count("sugerir:saltar"), 3 + len(falla))   # cada una que falló, reintentada una vez
        if otra:                                                         # defecto: saltar, sin consulta abierta
            self.assertEqual((rc, corridas, v["estado"], v["consulta"]["respuesta"], v["consulta"]["rondas"]),
                             (6, ["46a-autor", "46a-rev1"], "en_consulta", "saltar", []))
        else:                                                            # defecto: arreglar, como antes del 51
            self.assertEqual((rc, corridas[2]), (0, "46a-fix1"))
            self.assertNotIn("consulta", v)
        if llegaron:
            self.assertIn(f"no aceptó la consulta completa (faltan: {', '.join(o for o in ('aceptar', 'arreglar', 'saltar') if o in falla)})",
                          self.decisiones())
            self.assertEqual(v["consultas_n"], 1)                        # algo le llegó al usuario: cuenta para el tope
            (aviso,) = [a for a in self.avisos if "no se pudo mandar completa" in a[0]]
            self.assertIn(f"llegaron {llegaron} de 3 botones y no cuentan", aviso[0])
        else:
            self.assertIn("no aceptó ningún mensaje de la consulta", self.decisiones())
            self.assertNotIn("consultas_n", v)
        self.assertEqual(self.atender(), [])                             # nada queda esperando respuesta
        self.assertEqual(self.timers, [])                                # y el timer armado se detiene

    def test_una_falla_pasajera_se_reintenta_y_la_ronda_queda_completa(self):
        self.falla_una_vez = {"arreglar"}
        v = self.preguntar()
        self.assertEqual(sorted(v["consulta"]["rondas"][0]["ids"]), ["aceptar", "arreglar", "saltar"])
        self.assertNotIn("faltan", v["consulta"]["rondas"][0])
        self.assertEqual(self.eventos.count("sugerir:arreglar"), 2)

    def test_una_ronda_siguiente_a_medias_reintenta_lo_que_falta_con_el_mismo_plazo(self):
        v0 = self.preguntar()
        plazo = v0["consulta"]["plazo"]
        self.reloj += timedelta(minutes=31)
        self.falla = {"saltar"}
        (r,) = self.atender()
        c = self.vivo("cola46")["consulta"]
        self.assertEqual((r["accion"], c["plazo"], c["rondas"][1]["faltan"], sorted(c["rondas"][1]["ids"])),
                         ("ronda", plazo, ["saltar"], ["aceptar", "arreglar"]))
        self.reloj += timedelta(minutes=5)
        self.falla = set()
        (r,) = self.atender()
        c = self.vivo("cola46")["consulta"]
        self.assertEqual((r["accion"], c["plazo"], c["rondas"][1]["faltan"], len(c["rondas"])), ("ronda", plazo, [], 2))
        self.assertEqual(c["rondas"][1]["completada"], self.reloj.isoformat(timespec="seconds"))
        self.contestar("saltar")                                         # el botón que llegó tarde vale
        self.assertEqual(self.atender()[0]["accion"], "saltar")

    def test_si_el_canal_no_vuelve_se_deja_de_reintentar_y_el_plazo_aplica_el_defecto(self):
        v0 = self.preguntar()
        self.reloj += timedelta(minutes=31)
        self.falla = {"aceptar", "saltar"}
        for _ in range(6):
            self.atender()
            self.reloj += timedelta(minutes=5)
        c = self.vivo("cola46")["consulta"]
        self.assertEqual((c["rondas"][1]["reintentos"], c["rondas"][1]["faltan"], c["plazo"]),
                         (self.cr.CONSULTA_REINTENTOS, ["aceptar", "saltar"], v0["consulta"]["plazo"]))
        self.reloj = datetime.fromisoformat(c["plazo"]) + timedelta(minutes=1)
        (r,) = self.atender()
        self.assertEqual(r["accion"], "arreglar")
        self.assertIn("defecto: venció el plazo de 2 h", self.decisiones())


# ---------------------------------------------------------------- encargo 71: un mensaje A/B/C

class ConConsultar(Base):
    """El nodo-desplegar de la 71: la ronda es UN `consultar` con las tres alternativas."""

    def setUp(self):
        super().setUp()
        self.con_consultar = True

    def test_c5_una_sola_llamada_por_ronda_y_la_ronda_guarda_su_id(self):
        v = self.preguntar()
        (ronda,) = v["consulta"]["rondas"]
        self.assertEqual(set(ronda), {"enviada", "id", "canal"})
        self.assertEqual(ronda["canal"], "consultar")
        self.assertRegex(ronda["id"], self.cr.RE_ID_DESPLEGAR)
        self.assertEqual((len(self.consultas), self.mensajes), (1, []))     # ni un `sugerir`
        motivo, opciones = self.consultas[0]
        self.assertEqual([c for c, _ in opciones], ["aceptar", "arreglar", "saltar"])
        self.assertEqual([t.split(":")[0] for _, t in opciones], ["Aceptar y seguir", "Que lo arregle", "Saltar"])
        self.assertIn("la etapa se da por buena con esos hallazgos y la cola sigue", opciones[0][1])
        self.assertIn("corre el arreglo y otra revisión", opciones[1][1])
        self.assertIn("la cola queda pausada; se retoma con Reanudar", opciones[2][1])
        self.assertEqual(motivo, "❓ cola46 #1 · etapa 46a, rev1 NO DESPLEGABLE sin graves: 2 [Media] y 1 [Baja] (títulos en "
                                 "encargos/46ar1-RESULTADO.md). Sin respuesta en 2 h: C si hay otras colas esperando; si no, B.")
        self.assertIn("consulta #1 al usuario (1 mensaje)", self.bitacora.read_text(encoding="utf-8"))
        self.assertNotIn("no conoce `consultar`", self.bitacora.read_text(encoding="utf-8"))
        self.assertEqual(self.avisos, [])

    def test_las_etiquetas_y_el_motivo_caben_y_pasan_la_validacion_real(self):
        nd = cargar_nodo_desplegar("nodo_desplegar_71_val")
        for cola, et, cuenta in (("cola46", "46a", {"media": 2, "baja": 1}), ("cola48bxyzw12345", "48bxyz", {"media": 12, "baja": 10}),
                                 ("cola66", "66", {"media": 0, "baja": 0})):
            motivo = self.cr.motivo_consulta(cola, 2, et, "rev2", cuenta)
            self.assertLessEqual(len(motivo), 200)
            self.assertIn("Sin respuesta en 2 h: C si hay otras colas esperando; si no, B.", motivo)
            self.assertEqual(nd.validar_motivo_consulta(motivo), motivo)
        opciones = self.cr.opciones_consulta()
        self.assertEqual(nd.validar_opciones([{"clave": c, "etiqueta": t} for c, t in opciones]),
                         [{"clave": c, "etiqueta": t} for c, t in opciones])
        for malo in ("../x", "cola46\n", "x'; rm"):
            with self.assertRaises(ValueError):
                self.cr.motivo_consulta(malo, 1, "46a", "rev1", {"media": 1})
            with self.assertRaises(ValueError):
                self.cr.motivo_consulta("cola46", 1, malo, "rev1", {"media": 1})

    def test_la_consulta_no_lleva_titulos(self):
        self.correr(textos={"46a-rev1": CON_RUTA})
        ((motivo, opciones),) = self.consultas
        for s in SENSIBLES:
            self.assertNotIn(s, motivo + json.dumps(opciones, ensure_ascii=False))
        self.assertIn("sin graves: 2 [Media] y 2 [Baja]", motivo)

    def test_c6_aceptar_reanuda_sin_arreglo(self):
        self.preguntar()
        pid = self.contestar("aceptar")
        (r,) = self.atender()
        self.assertEqual((r["accion"], r["reanudar"]["desde"]), ("aceptar", "46a:fix1"))
        self.assertEqual(self.vivo("cola46")["aceptadas_usuario"][0]["pedido"], pid)
        self.assertIn(f"aceptar («Aceptar y seguir») · quién: el usuario (✅ en Telegram, pedido {pid})", self.decisiones())
        self.sesiones.discard("cola46")
        rc, corridas = self.correr("--desde", "46a:fix1")
        self.assertEqual((rc, corridas[0]), (0, "46b-autor"))
        self.assertIn("aceptada por el usuario tras rev1", self.bitacora.read_text(encoding="utf-8"))

    def test_c6_arreglar_reanuda_con_el_arreglo(self):
        self.preguntar()
        self.contestar("arreglar")
        (r,) = self.atender()
        self.assertEqual((r["accion"], r["reanudar"]["ok"]), ("arreglar", True))
        self.sesiones.discard("cola46")
        rc, corridas = self.correr("--desde", "46a:fix1")
        self.assertEqual((rc, corridas[:2]), (0, ["46a-fix1", "46a-rev2"]))
        self.assertIn("arreglar («Que lo arregle») · quién: el usuario", self.decisiones())

    def test_c6_saltar_deja_la_cola_estacionada(self):
        self.preguntar()
        self.contestar("saltar")
        (r,) = self.atender()
        v = self.vivo("cola46")
        self.assertEqual((r["accion"], self.lanzados, v["estado"]), ("saltar", [], "en_consulta"))
        self.assertIn("se retoma con Reanudar", v["motivo_pausa"])
        self.assertIn("saltar («Saltar») · quién: el usuario", self.decisiones())

    def test_c6_una_opcion_que_no_es_de_las_tres_se_ignora(self):
        self.preguntar()
        for k, opcion in enumerate(("root", "Aceptar", ["aceptar"], None, 1)):
            with self.subTest(opcion=opcion):
                self.contestar("aceptar", opcion=opcion)
                (r,) = self.atender()
                self.assertEqual((r["accion"], self.lanzados), ("nada", []))
        self.assertIn("root (20261011-190001-0001): no es una de las tres respuestas", self.decisiones())
        self.assertEqual(self.decisiones().count("no es una de las tres respuestas"), 5)
        self.contestar("aceptar", estado="hecho")
        r = json.loads(next(self.resultados.iterdir()).read_text(encoding="utf-8"))
        del r["opcion"]                                                  # un «hecho» sin opción tampoco
        next(self.resultados.iterdir()).write_text(json.dumps(r), encoding="utf-8")
        self.assertEqual(self.atender()[0]["accion"], "nada")

    def test_c6_un_resultado_que_no_es_de_root_se_ignora(self):
        self.preguntar()
        self.contestar("aceptar")
        (r,) = self.atender(dueno=0)
        self.assertEqual((r["accion"], self.lanzados), ("nada", []))
        self.assertIn("respuesta IGNORADA (no viene del chat del usuario): consulta (20261011-190001-0001): el resultado no "
                      "lo escribió el escucha de nodo-desplegar (no es de root)", self.decisiones())

    def test_vencido_no_es_respuesta(self):
        self.preguntar()
        self.contestar("aceptar", estado="vencido")
        self.assertEqual(self.atender()[0]["accion"], "nada")

    def test_cada_ronda_es_una_llamada_hasta_el_plazo(self):
        self.preguntar()
        for k in range(3):
            self.reloj += timedelta(minutes=30)
            (r,) = self.atender()
            self.assertEqual(r["accion"], "ronda", k)
            self.assertIn("(1 mensajes)", r["detalle"])
        self.assertEqual(len(self.consultas), 4)                         # 4 rondas de 1 mensaje en las 2 h
        self.reloj += timedelta(minutes=5)
        self.assertEqual(self.atender()[0]["accion"], "nada")
        self.contestar("saltar", ronda=0)                                # el mensaje de la primera ronda también vale
        self.assertEqual(self.atender()[0]["accion"], "saltar")

    def test_una_falla_pasajera_se_reintenta_una_vez(self):
        self.falla_consultar = 1
        v = self.preguntar()
        self.assertEqual((self.eventos.count("consultar"), len(v["consulta"]["rondas"])), (2, 1))

    def test_si_consultar_falla_dos_veces_se_aplica_el_defecto_y_no_cae_a_sugerir(self):
        self.falla_consultar = 2
        rc, corridas = self.correr(textos={"46a-rev1": SOLO_MEDIAS})
        self.assertEqual((rc, corridas[2], self.mensajes), (0, "46a-fix1", []))
        self.assertIn("defecto: nodo-desplegar no aceptó ningún mensaje de la consulta", self.decisiones())
        self.assertNotIn("consultas_n", self.vivo("cola46"))
        self.assertEqual(self.atender(), [])                             # nada queda esperando respuesta
        self.assertEqual(self.timers, [])                                # y el timer armado se detiene

    def test_una_ronda_siguiente_que_falla_se_vuelve_a_intentar_en_la_pasada_siguiente(self):
        v0 = self.preguntar()
        self.reloj += timedelta(minutes=31)
        self.falla_consultar = 2
        self.assertEqual(self.atender()[0]["accion"], "nada")
        self.assertEqual(len(self.vivo("cola46")["consulta"]["rondas"]), 1)
        self.reloj += timedelta(minutes=5)
        self.assertEqual(self.atender()[0]["accion"], "ronda")
        c = self.vivo("cola46")["consulta"]
        self.assertEqual((len(c["rondas"]), c["plazo"]), (2, v0["consulta"]["plazo"]))

    def test_una_aceptacion_con_el_id_de_la_consulta_vale_solo_si_lo_elegido_fue_aceptar(self):
        self.preguntar()
        pid = self.contestar("arreglar")
        cr = self.cr
        cr.VIVO.clear()
        cr.VIVO["aceptadas_usuario"] = [{"etapa": "46a", "tras": "rev1", "pedido": pid}]   # un vivo fabricado
        self.assertIsNone(cr._aceptada("46a", "fix1"))
        self.contestar("aceptar")
        self.assertEqual(cr._aceptada("46a", "fix1")["pedido"], pid)


class CompatibilidadConsultar(Base):
    """Encargo 71, punto 8: la cola anda antes y después de instalar el nodo-desplegar nuevo."""

    def test_c5_sin_consultar_cae_a_tres_sugerir_y_lo_anota(self):
        v = self.preguntar()                                             # Base: el nodo-desplegar viejo
        self.assertEqual(sorted(v["consulta"]["rondas"][0]["ids"]), ["aceptar", "arreglar", "saltar"])
        self.assertEqual((len(self.mensajes), self.consultas), (3, []))
        self.assertIn("el nodo-desplegar instalado no conoce `consultar` (es anterior a la 71): la consulta #1 va en "
                      "tres `sugerir`, como antes", self.bitacora.read_text(encoding="utf-8"))
        self.contestar("saltar")
        self.assertEqual(self.atender()[0]["accion"], "saltar")

    def test_c6_un_vivo_de_antes_se_resuelve_con_la_cola_nueva(self):
        """Un vivo en `en_consulta` con rondas de tres ids (la forma que dejaba la cola hasta la 70) y, ya instalado
        el nodo-desplegar nuevo, la ronda siguiente es un `consultar`: valen los dos."""
        self.preguntar()
        self.con_consultar = True
        self.reloj += timedelta(minutes=31)
        self.assertEqual(self.atender()[0]["accion"], "ronda")
        rondas = self.vivo("cola46")["consulta"]["rondas"]
        self.assertEqual(([sorted(r.get("ids", {})) for r in rondas], rondas[1].get("canal")),
                         ([["aceptar", "arreglar", "saltar"], []], "consultar"))
        self.contestar("arreglar", hora="2026-10-11 19:40:00")          # el de la ronda nueva
        self.contestar("aceptar", hora="2026-10-11 19:35:00", ronda=0)  # el ✅ del mensaje viejo, antes
        (r,) = self.atender()
        self.assertEqual(r["accion"], "aceptar")                         # gana el primero, de cualquier ronda

    def test_c6_la_ronda_vieja_de_tres_ids_sigue_ignorando_lo_que_no_es_de_root(self):
        self.preguntar()
        self.contestar("aceptar")
        self.assertEqual(self.atender(dueno=0)[0]["accion"], "nada")

    def test_una_ronda_vieja_a_medias_reintenta_por_sugerir_aunque_ya_haya_consultar(self):
        v0 = self.preguntar()
        self.reloj += timedelta(minutes=31)
        self.falla = {"saltar"}
        (r,) = self.atender()                                            # ronda 2 de sugerir, a medias
        self.assertEqual(self.vivo("cola46")["consulta"]["rondas"][1]["faltan"], ["saltar"])
        self.con_consultar, self.falla = True, set()
        self.reloj += timedelta(minutes=5)
        (r,) = self.atender()
        c = self.vivo("cola46")["consulta"]
        self.assertEqual((r["accion"], c["rondas"][1]["faltan"], self.consultas), ("ronda", [], []))
        self.assertEqual(c["plazo"], v0["consulta"]["plazo"])


def cargar_nodo_desplegar(nombre: str, fuente: Path = PI / "nodo-desplegar.py"):
    spec = importlib.util.spec_from_file_location(nombre, fuente)
    nd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nd)
    return nd


# Un `nodo-desplegar` de verdad para `cola-run.py`: corre el main() de un nodo-desplegar.py con el spool en el temporal.
# La caja no deja salir nada: si una ruta del módulo no quedó en el temporal, sale sin correr.
ENVOLTURA = '''import importlib.machinery, importlib.util, os, sys
from pathlib import Path
fuente, raiz = os.environ["NODO71_FUENTE"], Path(os.environ["NODO71_RAIZ"])
cargador = importlib.machinery.SourceFileLoader("nodo_desplegar_71", fuente)
nd = importlib.util.module_from_spec(importlib.util.spec_from_loader("nodo_desplegar_71", cargador))
cargador.exec_module(nd)
nd.SPOOL = raiz / "spool"
nd.PEDIDOS, nd.RESULTADOS = nd.SPOOL / "pedidos", nd.SPOOL / "resultados"
for n in ("ESTADO", "CATALOGO", "ENV", "VAULT", "RESPALDOS", "ARRANQUE"):
    setattr(nd, n, raiz / "no-se-usa" / n.lower())
for n, v in vars(nd).items():
    if isinstance(v, Path) and n != "MONTAJE" and not v.is_relative_to(raiz):
        sys.exit(f"{n} sigue en {v}")
sys.argv[0] = "nodo-desplegar"
sys.exit(nd.main())
'''


class PuntaAPunta71(Base):
    """`cola-run.py` con su `_consultar_real`/`_sugerir_real`, que corren un `nodo-desplegar` de verdad (el main() de
    pi/nodo-desplegar.py, o el de antes de la 71) como proceso aparte con el spool en el temporal; el Escucha real de
    ese mismo archivo atiende el pedido con un Telegram falso; el toque es el callback_data del botón que mandó; el
    resultado lo lee la cola. Nada llama a Telegram ni al escucha real."""

    def setUp(self):
        super().setUp()
        cr = self.cr
        self.raiz = self.tmp / "nodo-desplegar"
        (self.raiz / "spool" / "pedidos").mkdir(parents=True)
        self.resultados_nd = self.raiz / "spool" / "resultados"
        self.resultados_nd.mkdir()
        cr.RESULTADOS_DESPLEGAR = self.resultados_nd
        self.envoltura = self.tmp / "envoltura-nodo-desplegar.py"
        self.envoltura.write_text(ENVOLTURA, encoding="utf-8")
        self.fuente = PI / "nodo-desplegar.py"
        self.corridas_nd: list[list[str]] = []
        real = self.proceso

        def proceso(cmd, *a, **k):
            if list(cmd)[:1] == ["nodo-desplegar"]:
                self.corridas_nd.append(list(cmd))
                env = {"PATH": "/usr/bin:/bin", "NODO71_FUENTE": str(self.fuente), "NODO71_RAIZ": str(self.raiz)}
                return ta.subprocess.run([sys.executable, "-I", str(self.envoltura), *cmd[1:]], env=env, **k)
            return real(cmd, *a, **k)
        cr.subprocess.run = staticmethod(proceso)
        cr.registrar_aviso = lambda *a: None                             # el registro real escribe en /opt/nodo/datos
        cr.CONSULTAR_CONSULTA, cr.SUGERIR_CONSULTA = cr._consultar_real, cr._sugerir_real

    def escucha(self):
        nd = cargar_nodo_desplegar("nodo_desplegar_71_escucha")
        nd.SPOOL = self.raiz / "spool"
        nd.PEDIDOS, nd.RESULTADOS = nd.SPOOL / "pedidos", self.resultados_nd
        nd.ESTADO, nd.RESPALDOS, nd.VAULT = self.raiz / "estado", self.raiz / "respaldos", self.raiz / "vault"
        nd.CATALOGO, nd.ENV, nd.ARRANQUE = self.raiz / "etc" / "catalogo.toml", self.raiz / "etc" / "avisos.env", self.raiz / "boot_id"
        for nombre, valor in vars(nd).items():
            if isinstance(valor, Path) and nombre != "MONTAJE":
                self.assertTrue(valor.is_relative_to(self.tmp), f"{nombre} sigue en {valor}")
        nd.CATALOGO.parent.mkdir(parents=True, exist_ok=True)
        nd.CATALOGO.write_text("")
        nd.ENV.write_text("TELEGRAM_TOKEN=7123456789:AAFalsoFalsoFalso\nCHAT_ID=424242\n")
        nd.ARRANQUE.write_text("8c1f5f5e-3c1e-4a8e-9d55-2f3b0c1d2e3f\n")
        self.journal: list[str] = []
        nd.log = self.journal.append
        self.telegram: list[tuple[str, dict]] = []

        def urlopen(req, timeout=None):
            self.telegram.append((req.full_url.rsplit("/", 1)[1], json.loads(req.data)))
            return io.BytesIO(b'{"ok": true, "result": {"message_id": 77}}')
        for objeto, attr, falso in ((nd.urllib.request, "urlopen", urlopen),
                                    (nd.subprocess, "run", mock.Mock(side_effect=AssertionError("nada corre")))):
            p = mock.patch.object(objeto, attr, falso)
            p.start()
            self.addCleanup(p.stop)
        e = nd.Escucha()
        e.procesar_pedidos()
        return e

    def tocar(self, e, texto_boton: str, en: str = "") -> str:
        """El toque en el botón que empieza con `texto_boton` del único mensaje cuyo texto trae `en`."""
        (enviado,) = [p for m, p in self.telegram if m == "sendMessage" and en in p["text"]]
        botones = [b for fila in enviado["reply_markup"]["inline_keyboard"] for b in fila]
        (data,) = [b["callback_data"] for b in botones if b["text"].startswith(texto_boton)]
        e.callback({"id": "cb", "from": {"id": 424242}, "message": {"chat": {"id": 424242}}, "data": data})
        return [p for m, p in self.telegram if m == "answerCallbackQuery"][-1]["text"]

    def test_de_punta_a_punta_consultar_un_mensaje_toque_b_y_la_cola_lo_lee(self):
        v = self.preguntar()
        (corrida,) = self.corridas_nd
        self.assertEqual(corrida[:2], ["nodo-desplegar", "consultar"])
        (ronda,) = v["consulta"]["rondas"]
        self.assertEqual(ronda["canal"], "consultar")
        pedido = json.loads((self.raiz / "spool" / "pedidos" / f"{ronda['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual((pedido["tipo"], [o["clave"] for o in pedido["opciones"]]), ("consulta", ["aceptar", "arreglar", "saltar"]))
        e = self.escucha()
        enviados = [p for m, p in self.telegram if m == "sendMessage"]
        self.assertEqual(len(enviados), 1)
        self.assertEqual([b["text"] for f in enviados[0]["reply_markup"]["inline_keyboard"] for b in f],
                         ["A — Aceptar y seguir", "B — Que lo arregle", "C — Saltar"])
        self.assertEqual(self.tocar(e, "B — "), "Elegido: B.")
        self.assertEqual(self.tocar(e, "A — "), "Ya se eligió B.")
        r = json.loads((self.resultados_nd / f"{ronda['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual((r["estado"], r["opcion"]), ("hecho", "arreglar"))
        (res,) = self.atender(resultados_dir=None)                       # la cola lee el resultado del escucha
        self.assertEqual((res["accion"], res["reanudar"]["desde"]), ("arreglar", "46a:fix1"))
        self.assertIn(f"arreglar («Que lo arregle») · quién: el usuario (✅ en Telegram, pedido {ronda['id']})", self.decisiones())
        for s in SENSIBLES:                                              # 51r1: nada de la revisión fuera del volumen
            self.assertNotIn(s, "\n".join(self.journal) + (self.raiz / "estado" / "pendientes.json").read_text(encoding="utf-8"))

    def test_de_punta_a_punta_con_el_nodo_desplegar_de_antes_caen_tres_sugerir(self):
        # El nodo-desplegar.py de antes de la 71 (el de la 70, a3f0b031…): sin `consultar` en su main().
        viejo = self.tmp / "viejo" / "nodo-desplegar.py"
        viejo.parent.mkdir()
        texto = (PI / "nodo-desplegar.py").read_text(encoding="utf-8")
        texto = texto.replace('"consultar": consultar, ', "")
        texto = re.sub(r"    nodo-desplegar consultar .*?El resultado lleva `opcion` = CLAVE\n", "", texto, flags=re.S)
        viejo.write_text(texto, encoding="utf-8")
        self.fuente = viejo
        err = ta.subprocess.run([sys.executable, "-I", str(self.envoltura), "consultar", "--motivo", "m"], capture_output=True,
                                text=True, env={"PATH": "/usr/bin:/bin", "NODO71_FUENTE": str(viejo), "NODO71_RAIZ": str(self.raiz)})
        self.assertEqual(err.returncode, 2)
        self.assertNotIn("consultar", err.stderr)                       # como el instalado hoy: la ayuda, sin «consultar»
        self.assertIn("nodo-desplegar sugerir", err.stderr)
        v = self.preguntar()
        self.assertEqual([c[:2] for c in self.corridas_nd], [["nodo-desplegar", "consultar"]] + [["nodo-desplegar", "sugerir"]] * 3)
        ids = v["consulta"]["rondas"][0]["ids"]
        self.assertEqual(sorted(ids), ["aceptar", "arreglar", "saltar"])
        e = self.escucha()
        self.assertEqual(len([p for m, p in self.telegram if m == "sendMessage"]), 3)
        self.assertEqual(self.tocar(e, "✅", en="consulta cola46 #1: saltar"), "Anotado: la IA verifica.")
        (res,) = self.atender(resultados_dir=None)
        self.assertEqual(res["accion"], "saltar")

    def test_el_instalado_hoy_contesta_como_supone_la_caida(self):
        instalado = Path("/usr/local/bin/nodo-desplegar")
        if not instalado.is_file():
            self.skipTest("sin /usr/local/bin/nodo-desplegar en este equipo")
        texto = instalado.read_text(encoding="utf-8")                   # se lee, no se corre
        if '"consultar": consultar' in texto:
            self.skipTest("el instalado ya trae `consultar`")
        ayuda = texto.split('"""')[1].split("\n\n")[1]
        self.assertNotIn("consultar", ayuda)
        self.assertIn("print(__doc__.split(\"\\n\\n\")[1], file=sys.stderr)\n        return 2", texto)


for _falla in ({"aceptar"}, {"arreglar"}, {"saltar"}, {"aceptar", "arreglar"}, {"aceptar", "saltar"},
               {"arreglar", "saltar"}, {"aceptar", "arreglar", "saltar"}):
    for _otra in (False, True):
        setattr(Hallazgo3RondaCompletaONada, f"test_falla_{'_'.join(sorted(_falla))}{'_con_otra_esperando' if _otra else ''}",
                lambda self, f=frozenset(_falla), o=_otra: self.a_medias(f, o))


if __name__ == "__main__":
    unittest.main()
