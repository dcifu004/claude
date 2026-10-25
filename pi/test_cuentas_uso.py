#!/usr/bin/env python3
"""Pruebas del historial y el reparto del precio por ciclo (bots-info, 30-09-2026).

    python3 test_cuentas_uso.py
"""
import importlib.util
import json
import os
import re
import shutil
import tempfile
import tomllib
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("bots_info", Path(__file__).with_name("bots-info.py"))
bi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bi)
TZ = bi.TZ
RECETAS_SPEC = importlib.util.spec_from_file_location("recetas_57a", Path(__file__).parents[1] / "botv3" / "recetas.py")
recetas_57a = importlib.util.module_from_spec(RECETAS_SPEC)
RECETAS_SPEC.loader.exec_module(recetas_57a)


def reg(renueva=""):
    return {"claude_diego": {**bi.CUENTAS["claude_diego"], "precio_mes_usd": 20, "renueva": renueva}}


def t(salida=0, entrada=0):
    return {"entrada": entrada, "salida": salida, "cache_lectura": 0, "cache_escritura": 0}


class CiclosTests(unittest.TestCase):
    AHORA = datetime(2026, 9, 30, 12, 0, tzinfo=TZ)  # miércoles

    def test_el_reparto_suma_el_precio_semanal(self):
        ev = [(self.AHORA - timedelta(hours=1), "claude_diego", "jaime/claude", True, t(100)),
              (self.AHORA - timedelta(hours=2), "claude_diego", "pi/interactivo", True, t(300))]
        r = bi.resumen_cuentas(reg(), ev, self.AHORA)
        ciclo = r["cuentas"]["claude_diego"]["ciclos"][0]
        self.assertTrue(ciclo["actual"])
        self.assertEqual(ciclo["usd_semana"], 4.62)
        self.assertEqual(ciclo["rutas"]["jaime/claude"]["usd"], 1.16)
        self.assertEqual(ciclo["rutas"]["pi/interactivo"]["usd"], 3.46)
        self.assertAlmostEqual(sum(x["usd"] for x in ciclo["rutas"].values())
                               + ciclo["ocioso_usd"], 4.62, places=2)
        self.assertEqual(r["por_ruta"]["jaime/claude"]["semana_usd"], 1.16)

    def test_sin_uso_todo_queda_ocioso(self):
        ciclo = bi.resumen_cuentas(reg(), [], self.AHORA)["cuentas"]["claude_diego"]["ciclos"][0]
        self.assertEqual(ciclo["rutas"], {})
        self.assertEqual(ciclo["ocioso_usd"], 4.62)

    def test_el_ciclo_empieza_en_la_renovacion(self):
        # Renueva los miércoles a las 10:00: las 09:59 del miércoles son del ciclo anterior.
        ev = [(datetime(2026, 9, 30, 9, 59, tzinfo=TZ), "claude_diego", "jaime/web", True, t(1)),
              (datetime(2026, 9, 30, 10, 1, tzinfo=TZ), "claude_diego", "jaime/web", True, t(1))]
        c = bi.resumen_cuentas(reg("mie 10:00"), ev, self.AHORA)["cuentas"]["claude_diego"]
        self.assertFalse(c["renueva_supuesto"])
        self.assertEqual([x["inicio"][:16] for x in c["ciclos"]],
                         ["2026-09-30T10:00", "2026-09-23T10:00"])
        self.assertEqual(c["proxima_renovacion"][:16], "2026-10-07T10:00")

    def test_renovacion_vacia_se_marca_como_supuesta(self):
        c = bi.resumen_cuentas(reg(""), [], self.AHORA)["cuentas"]["claude_diego"]
        self.assertTrue(c["renueva_supuesto"])
        self.assertEqual(c["renueva_origen"], "supuesto")
        self.assertEqual(c["ciclos"][0]["inicio"][:16], "2026-09-28T00:00")

    def test_renovacion_medida_solo_reemplaza_el_vacio(self):
        limites = {"claude_diego": {"semanal": {"renueva": "2026-10-05T14:30:00-03:00"}}}
        c = bi.resumen_cuentas(reg(""), [], self.AHORA, limites)["cuentas"]["claude_diego"]
        self.assertEqual(c["renueva_origen"], "medido")
        self.assertEqual(c["ciclos"][0]["inicio"][:16], "2026-09-28T14:30")
        self.assertEqual(c["limites"], limites["claude_diego"])
        registrado = bi.resumen_cuentas(reg("mie 10:00"), [], self.AHORA, limites)["cuentas"]["claude_diego"]
        self.assertEqual(registrado["renueva_origen"], "registro")

    def test_los_intentos_fallidos_no_pagan(self):
        ev = [(self.AHORA, "claude_diego", "jaime/web", False, None),
              (self.AHORA, "claude_diego", "jaime/claude", True, t(10))]
        ciclo = bi.resumen_cuentas(reg(), ev, self.AHORA)["cuentas"]["claude_diego"]["ciclos"][0]
        self.assertEqual(ciclo["rutas"]["jaime/web"]["fallidas"], 1)
        self.assertEqual(ciclo["rutas"]["jaime/web"]["usd"], 0)
        self.assertEqual(ciclo["rutas"]["jaime/claude"]["usd"], 4.62)

    def test_sin_tokens_se_reparte_por_consultas_y_se_dice(self):
        ev = [(self.AHORA, "claude_diego", "jaime/claude", True, None),
              (self.AHORA, "claude_diego", "pilar/web", True, t(999)),
              (self.AHORA, "claude_diego", "pilar/web", True, t(999))]
        ciclo = bi.resumen_cuentas(reg(), ev, self.AHORA)["cuentas"]["claude_diego"]["ciclos"][0]
        self.assertEqual(ciclo["reparto"], "consultas")
        self.assertEqual(ciclo["rutas"]["jaime/claude"]["usd"], 1.54)
        self.assertEqual(ciclo["rutas"]["pilar/web"]["usd"], 3.08)

    def test_el_peso_sigue_la_proporcion_de_precios(self):
        # Salida 5× entrada; leer caché 0,1×. Codex: total de tokens.
        self.assertEqual(bi.peso("claude", t(salida=1)), 5)
        self.assertEqual(bi.peso("claude", {"cache_lectura": 100}), 10)
        self.assertEqual(bi.peso("codex", {"total": 1234}), 1234)
        self.assertIsNone(bi.peso("claude", None))


class FormaRealTests(unittest.TestCase):
    def test_vuelta1_claude_cami_conserva_tope_real_90_y_se_salta_al_92(self):
        """El TOML real no puede volver a habilitar Claude (Cami) sobre su tope."""
        with open(Path(__file__).parents[1] / "botv3" / "cuentas.toml", "rb") as fh:
            registro = tomllib.load(fh)
        self.assertEqual(registro["claude_cami"]["nombre"], "Claude (Cami)")
        self.assertEqual(registro["claude_cami"]["umbral_semanal"], 90)
        limites = {"claude_cami": {"semanal": {"usado_pct": 92, "renueva": "2099-01-01T00:00:00+00:00"}},
                   "claude_diego": {"semanal": {"usado_pct": 10, "renueva": "2099-01-01T00:00:00+00:00"}}}
        umbrales = {cuenta: {"semanal": registro[cuenta]["umbral_semanal"], "5h": registro[cuenta]["umbral_5h"]}
                    for cuenta in ("claude_cami", "claude_diego")}
        eleccion = recetas_57a.elegir_orden(["claude_cami", "claude_diego"],
                                             ["claude_cami", "claude_diego"], set(umbrales),
                                             limites, umbrales, {"automatico": False},
                                             datetime(2026, 10, 13, tzinfo=TZ))
        self.assertEqual(eleccion["orden"], ["claude_diego"])

    def test_limites_se_leen_de_la_forma_real_de_uso_json(self):
        # uso.py publica {cuenta: {disponible, por_hora, limites}}; resumen_cuentas
        # espera {cuenta: limites}. El 29-09 el llamador pasaba el bloque entero y el
        # ciclo «medido» no se activaba nunca con datos reales, con las pruebas en verde.
        uso = {"cuentas_interactivo": {
            "codex": {"disponible": True, "por_hora": {},
                      "limites": {"momento": "2026-09-29T21:00:00-03:00",
                                  "semanal": {"usado_pct": 3.0, "renueva": "2026-10-02T14:30:00-03:00"}}},
            "claude_cami": {"disponible": True, "por_hora": {}}}}
        lim = bi.limites_de(uso)
        self.assertEqual(set(lim), {"codex"})
        reg_codex = {"codex": {**bi.CUENTAS["codex"], "precio_mes_usd": 20, "renueva": ""}}
        c = bi.resumen_cuentas(reg_codex, [], CiclosTests.AHORA, lim)["cuentas"]["codex"]
        self.assertEqual(c["renueva_origen"], "medido")
        self.assertEqual(c["proxima_renovacion"][:16], "2026-10-02T14:30")

    def test_interactivo_cuenta_uno_por_mensaje_del_balde(self):
        uso = {"cuentas_interactivo": {
            "claude_diego": {"por_hora": {
                "2026-09-30T11": {"entrada": 10, "salida": 0, "cache_lectura": 0,
                                     "cache_escritura": 0, "mensajes": 3}
            }}
        }}
        eventos = bi.eventos_de_uso([], uso)
        self.assertEqual(eventos[0][-1], 3)
        ciclo = bi.resumen_cuentas(reg(), eventos, CiclosTests.AHORA)["cuentas"]["claude_diego"]["ciclos"][0]
        self.assertEqual(ciclo["rutas"]["pi/interactivo"]["consultas"], 3)

    def test_dos_pc_y_un_reporte_viejo(self):
        ahora = CiclosTests.AHORA
        balde = {"entrada": 0, "salida": 10, "cache_lectura": 0, "cache_escritura": 0, "mensajes": 1}
        uso = {"equipos": {"activos": {
            "PC-Diego": {"actualizado": ahora.isoformat(), "cuentas": {"claude_diego": {"por_hora": {"2026-09-30T11": balde}}}},
            "PC-2503": {"actualizado": ahora.isoformat(), "cuentas": {"claude_diego": {"por_hora": {"2026-09-30T10": balde}}}},
        }, "vencidos": {"PC-viejo": "2026-09-20T12:00:00-03:00"}}}
        eventos = bi.eventos_de_uso([], uso)
        ciclo = bi.resumen_cuentas(reg(), eventos, ahora)["cuentas"]["claude_diego"]["ciclos"][0]
        self.assertEqual(set(ciclo["rutas"]), {"pc:PC-Diego", "pc:PC-2503"})
        self.assertAlmostEqual(sum(x["usd"] for x in ciclo["rutas"].values()) + ciclo["ocioso_usd"],
                               ciclo["usd_semana"], places=2)

    def test_limite_mas_reciente_gana_entre_pi_y_pc(self):
        uso = {"cuentas_interactivo": {"codex": {"limites": {"momento": "2026-09-30T10:00:00-03:00"}}},
               "equipos": {"activos": {"PC-Diego": {"cuentas": {"codex": {"limites": {
                   "momento": "2026-09-30T11:00:00-03:00", "semanal": {"usado_pct": 7}}}}}}}}
        self.assertEqual(bi.limites_de(uso)["codex"]["semanal"]["usado_pct"], 7)

    def test_claude_desconocida_queda_visible_sin_asignarle_costo(self):
        uso = {"equipos": {"activos": {"PC-2503": {"cuentas": {"claude_desconocida": {
            "por_hora": {"2026-09-30T11": {**t(salida=5000), "mensajes": 9}}}}}}}}
        eventos = bi.eventos_de_uso([], uso)
        resumen = bi.resumen_cuentas(reg(), eventos, CiclosTests.AHORA)
        self.assertIn("PC-2503 reportó 9 mensajes de una cuenta Claude que no está en cuentas.toml", resumen["alcance"])
        self.assertNotIn("pc:PC-2503", resumen["por_ruta"])


class RendimientoTests(unittest.TestCase):
    def test_rendimiento_usa_el_jsonl_real_con_modelo_votos_y_costo(self):
        # Forma de producción: una línea antigua sin id y una nueva escrita por
        # anotar_uso_cuenta. El lector debe conservar ambas y sumar también el
        # balde interactivo real de uso.json antes de asignar el USD.
        with tempfile.TemporaryDirectory() as raiz:
            libro = Path(raiz) / "uso-cuentas.jsonl"
            previo = os.environ.get("BOTV3_USO_CUENTAS")
            os.environ["BOTV3_USO_CUENTAS"] = str(libro)
            try:
                spec = importlib.util.spec_from_file_location("botv3_rendimiento", Path(__file__).parents[1] / "botv3" / "botv3.py")
                bot = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(bot)
                ahora = datetime.now(TZ)
                viejo = {"ts": ahora.isoformat(timespec="seconds"), "perfil": "jaime", "ruta": "claude",
                         "cuenta": "claude_diego", "motor": "claude",
                         "ok": True, "s": 2.0, "tokens": t(salida=10)}
                libro.write_text(json.dumps(viejo) + "\n", encoding="utf-8")
                bot._CONSUMO.modelo = "claude-sonnet-4-20250514"
                bot._CONSUMO.tokens = t(salida=10)
                intento = bot.anotar_uso_cuenta("claude", "claude_diego", "claude", True, 3.0)
                self.assertTrue(bot.anotar_calificacion(intento, 1))
                anterior_dir = bi.estado_dir
                bi.estado_dir = lambda perfil: raiz
                uso = {"cuentas_interactivo": {"claude_diego": {"por_hora": {
                    ahora.strftime("%Y-%m-%dT%H"): {**t(salida=30), "mensajes": 2}
                }}}}
                try:
                    intentos, votos = bi._libro_rendimiento(["jaime"])
                    salida = bi.rendimiento(reg(), ["jaime"], ahora, uso)
                    resumen = bi.resumen_cuentas(reg(), bi.eventos_de_uso(["jaime"], uso), ahora,
                                                  bi.limites_de(uso))
                finally:
                    bi.estado_dir = anterior_dir
            finally:
                if previo is None:
                    os.environ.pop("BOTV3_USO_CUENTAS", None)
                else:
                    os.environ["BOTV3_USO_CUENTAS"] = previo
        self.assertEqual(len(salida), 1)
        r = salida[0]
        self.assertEqual((r["cuenta"], r["motor"], r["modelo"]),
                         ("claude_diego", "claude", "claude-sonnet-4-20250514"))
        self.assertEqual((len(intentos), intentos[0]["id"], votos[intento]), (2, None, 1))
        self.assertEqual((r["intentos"], r["tasa_falla"], r["positivos"], r["base"]), (2, 0.0, 1, "👍"))
        # 2×50 de peso Claude contra 300 interactivos: la ruta recibe 1,85 USD,
        # exactamente lo que muestra resumen_cuentas; no los 4,62 de antes.
        self.assertEqual(r["usd_asignado"], resumen["por_ruta"]["jaime/claude"]["semana_usd"])
        self.assertEqual(r["costo_respuesta_util_usd"], 1.85)

    def test_fallas_sin_modelo_se_suman_a_su_cuenta_y_motor(self):
        """Timeout de Codex y error Claude sin modelUsage no crean filas aparte."""
        ahora = CiclosTests.AHORA
        intentos = [
            {"ts": ahora.isoformat(), "perfil": "jaime", "ruta": "web", "cuenta": "codex",
             "motor": "codex", "modelo": None, "ok": False, "s": 120.0, "tokens": None},
            {"ts": ahora.isoformat(), "perfil": "jaime", "ruta": "web", "cuenta": "codex",
             "motor": "codex", "modelo": "gpt-5-codex", "ok": True, "s": 2.0, "tokens": {"total": 10}},
            {"ts": ahora.isoformat(), "perfil": "jaime", "ruta": "claude", "cuenta": "claude_cami",
             "motor": "claude", "modelo": None, "ok": False, "s": 2.0, "tokens": None},
            {"ts": ahora.isoformat(), "perfil": "jaime", "ruta": "claude", "cuenta": "claude_cami",
             "motor": "claude", "modelo": "claude-sonnet-4-20250514", "ok": True, "s": 2.0,
             "tokens": t(salida=10)},
        ]
        with tempfile.TemporaryDirectory() as raiz:
            Path(raiz, "uso-cuentas.jsonl").write_text(
                "".join(json.dumps(i) + "\n" for i in intentos), encoding="utf-8")
            anterior_dir = bi.estado_dir
            bi.estado_dir = lambda perfil: raiz
            try:
                salida = bi.rendimiento({
                    "codex": {**bi.CUENTAS["codex"], "precio_mes_usd": 20, "renueva": ""},
                    "claude_cami": {**bi.CUENTAS["claude_cami"], "precio_mes_usd": 20, "renueva": ""},
                }, ["jaime"], ahora)
            finally:
                bi.estado_dir = anterior_dir
        self.assertEqual([(r["cuenta"], r["motor"], r["modelo"], r["intentos"], r["tasa_falla"])
                          for r in salida], [
            ("claude_cami", "claude", "claude-sonnet-4-20250514", 2, 0.5),
            ("codex", "codex", "gpt-5-codex", 2, 0.5),
        ])


# recetas.py del vault: en la Pi bots-info usa el desplegado en /opt/botv3.
_SPEC_R = importlib.util.spec_from_file_location(
    "recetas", Path(__file__).resolve().parent.parent / "botv3" / "recetas.py")
recetas = importlib.util.module_from_spec(_SPEC_R)
_SPEC_R.loader.exec_module(recetas)


class QuienContestariaTests(unittest.TestCase):
    """«¿Quién contestaría ahora?» (06a): la misma función que usa el bot."""
    AHORA = CiclosTests.AHORA
    FUTURO = "2026-10-05T00:59:59.967918+00:00"
    CFG = {"rutas": ["claude", "web", "gpt", "codex"],
           "cuentas": {"claude": ["claude_diego"], "codex": ["codex"],
                       "web": ["codex", "claude_cami"]}}
    SESION = {c: {"sesion": True} for c in bi.CUENTAS}

    def uso(self, **pcts):
        # Forma real de uso.json → cuentas_interactivo.<cuenta>.limites (encargos 01 y 03).
        return {"cuentas_interactivo": {cid: {"disponible": True, "por_hora": {}, "limites": {
            "momento": "2026-09-29T22:37:05-03:00", "plan": None,
            "ventana_5h": {"usado_pct": h5, "renueva": self.FUTURO},
            "semanal": {"usado_pct": sem, "renueva": self.FUTURO}}}
            for cid, (sem, h5) in pcts.items()}}

    def calcular(self, cfg, uso, registro=None, perfil="jaime"):
        return bi.recetas_de(perfil, cfg, self.SESION, bi.limites_de(uso), registro or {},
                             self.AHORA, mod=recetas)

    def test_nombres_nuevos_cadena_y_etiqueta_cyd(self):
        r = self.calcular(self.CFG, self.uso(claude_diego=(78, 50), codex=(43.0, 47.0),
                                             claude_cami=(3, 24)))["rutas"]
        self.assertEqual(sorted(r), ["archivos", "tecnica", "web"])
        self.assertEqual(r["archivos"]["contesta"], "claude_diego")
        self.assertEqual(r["web"]["contesta"], "claude_cami")
        self.assertTrue(r["archivos"]["lee_cyd"] and r["tecnica"]["lee_cyd"])
        self.assertFalse(r["web"]["lee_cyd"])

    def test_automatico_y_umbral_como_el_bot(self):
        cfg = {**self.CFG, "recetas": {"archivos": {"automatico": True}}}
        r = self.calcular(cfg, self.uso(claude_diego=(78, 50), codex=(85.0, 47.0),
                                        claude_cami=(3, 24)))["rutas"]
        self.assertEqual(r["archivos"]["orden"], ["claude_cami", "claude_diego", "codex"])
        self.assertEqual(r["web"]["contesta"], "claude_cami")  # Codex sobre el 80 %

    def test_todas_sobre_el_umbral(self):
        r = self.calcular(self.CFG, self.uso(codex=(92.0, 1.0), claude_cami=(85, 1)))["rutas"]
        self.assertEqual(r["web"]["aviso"], "⚠️ todas sobre el umbral, contestó Claude (Cami) (85 %)")

    def test_umbral_de_cuentas_toml(self):
        r = self.calcular(self.CFG, self.uso(codex=(85.0, 1.0), claude_cami=(3, 1)),
                          registro={"codex": {"umbral_semanal": 90}})["rutas"]
        self.assertEqual(r["web"]["contesta"], "claude_cami")

    def test_sin_dato_no_se_salta_nada(self):
        r = self.calcular(self.CFG, None)["rutas"]
        self.assertEqual(r["web"]["orden"], ["claude_cami"])

    def test_sin_modulo_o_sin_cuentas_no_inventa(self):
        self.assertIsNone(bi.recetas_de("jaime", {"rutas": ["web"]}, self.SESION, {}, {},
                                        self.AHORA, mod=recetas))

    def test_sin_ninguna_sesion_no_contesta_nadie_como_el_bot(self):
        # 06br1: la sesión sale de cuentas_de sobre directorios reales — Claude con
        # .claude.json de antes del login, Codex sin auth.json — no de un dict inventado.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        anterior = bi.estado_dir
        bi.estado_dir = lambda perfil: tmp
        self.addCleanup(setattr, bi, "estado_dir", anterior)
        for cid, c in bi.CUENTAS.items():
            os.makedirs(f"{tmp}/cuentas/{cid}")
            if c["motor"] == "claude":
                with open(f"{tmp}/cuentas/{cid}/.claude.json", "w", encoding="utf-8") as fh:
                    json.dump({"numStartups": 1}, fh)
        por_cuenta = bi.cuentas_de("jaime")
        self.assertFalse(any(v["sesion"] for v in por_cuenta.values()))
        cfg = {**self.CFG, "recetas": {"web": {"automatico": True}}}
        r = bi.recetas_de("jaime", cfg, por_cuenta, bi.limites_de(self.uso(codex=(1.0, 1.0))),
                          {}, self.AHORA, mod=recetas)["rutas"]
        for ruta in ("archivos", "tecnica", "web"):
            self.assertEqual(r[ruta]["orden"], [], ruta)
            self.assertIsNone(r[ruta]["contesta"], ruta)
            self.assertTrue(r[ruta]["sin_sesion"], ruta)
            self.assertFalse(r[ruta]["todas_sobre"], ruta)
            self.assertIsNone(r[ruta]["aviso"], ruta)
        # Con sólo Codex no hay respuesta: web no puede ejecutarlo (11).
        with open(f"{tmp}/cuentas/codex/auth.json", "w", encoding="utf-8") as fh:
            json.dump({"OPENAI_API_KEY": None, "tokens": {"access_token": "x"}}, fh)
        r = bi.recetas_de("jaime", cfg, bi.cuentas_de("jaime"), {}, {}, self.AHORA,
                          mod=recetas)["rutas"]
        self.assertIsNone(r["web"]["contesta"])
        self.assertTrue(r["web"]["sin_sesion"])


class MatrizYPropuestaTests(unittest.TestCase):
    """Muros y propuesta con la misma forma TOML que recibe aplicar-propuesta."""

    def test_general_solo_admite_proveedores_gratis_y_groq_cuesta_cero(self):
        # Hasta el 12 la general era fija en Groq; desde el 15 elige entre los gratis.
        # Lo que no cambia: una cuenta pagada declarada ahí se descarta.
        cfg = {"rutas": ["gpt"], "cuentas": {"gpt": ["claude_cami", "groq", "codex"]}}
        matriz = bi.matriz_de("jaime", cfg, {"groq": {"sesion_general": True}}, mod=recetas)
        fila = matriz["rutas"][0]
        self.assertEqual(fila["interna"], "gpt")
        self.assertIsNone(fila["fija"])
        self.assertEqual(fila["cadena"], ["groq"])
        celdas = {c["cuenta"]: c for c in fila["celdas"]}
        self.assertEqual({c for c, v in celdas.items() if v["permitida"]}, {"groq", "gemini", "openrouter"})
        for pagada in ("claude_diego", "claude_cami", "codex"):
            self.assertIn("las cuentas pagadas podrían leer credenciales del bot", celdas[pagada]["motivo"])
        for a in matriz["atajos"].values():
            self.assertFalse({"claude_diego", "claude_cami", "codex"} & set(a["cadenas"]["gpt"]), a["etiqueta"])
        registro = {"groq": {**bi.CUENTAS["groq"], "precio_mes_usd": 0, "renueva": ""}}
        ahora = CiclosTests.AHORA
        ciclo = bi.resumen_cuentas(registro, [(ahora, "groq", "jaime/web", True, t(10))],
                                    ahora)["cuentas"]["groq"]["ciclos"][0]
        self.assertEqual(ciclo["usd_semana"], 0)
        self.assertEqual(ciclo["rutas"]["jaime/web"]["usd"], 0)

    def test_aplicar_propuesta_rechaza_celda_prohibida_en_toml_real(self):
        spec = importlib.util.spec_from_file_location("aplicar_prueba", Path(__file__).with_name("aplicar-propuesta.py"))
        ap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ap)
        with tempfile.TemporaryDirectory() as raiz:
            vault, desplegado = Path(raiz) / "vault", Path(raiz) / "desplegado"
            vault.mkdir()
            desplegado.mkdir()
            perfil = ('nombre = "P"\npersona = "Diego"\nvaults = []\n'
                      'rutas = ["archivos"]\ncuentas = { archivos = ["claude_diego"] }\n')
            (vault / "p.toml").write_text(perfil, encoding="utf-8")
            (desplegado / "p.toml").write_text(perfil, encoding="utf-8")
            ap.VAULT_PI, ap.DESPLEGADO, ap.recetas = str(vault), str(desplegado), recetas
            with self.assertRaisesRegex(SystemExit, "1"):
                ap.armar_plan("p", "cuentas", {"archivos": ["groq"]})

    def aplicar(self, rutas, cuentas, entorno):
        """aplicar-propuesta sobre un perfil con la forma TOML real, con el recetas.py del
        vault y el entorno del bot ya reducido (lo que mide en /proc/<pid>/environ)."""
        spec = importlib.util.spec_from_file_location("aplicar_prueba", Path(__file__).with_name("aplicar-propuesta.py"))
        ap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ap)
        raiz = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, raiz, True)
        vault, desplegado = raiz / "vault", raiz / "desplegado"
        vault.mkdir()
        desplegado.mkdir()
        perfil = (f'nombre = "P"\npersona = "Diego"\nvaults = []\nrutas = {json.dumps(rutas)}\n'
                  f'cuentas = {cuentas}\n')
        (vault / "p.toml").write_text(perfil, encoding="utf-8")
        (desplegado / "p.toml").write_text(perfil, encoding="utf-8")
        ap.VAULT_PI, ap.DESPLEGADO, ap.recetas = str(vault), str(desplegado), recetas
        ap.entorno_del_bot = lambda perfil: entorno
        original = ap.tiene_sesion
        ap.tiene_sesion = lambda perfil, cuenta, ruta=None: True if cuenta in ap.PAGADAS \
            else original(perfil, cuenta, ruta)
        return ap

    def rechazo(self, ap, valor):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stderr(salida), contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaises(SystemExit):
            ap.armar_plan("p", "cuentas", valor)
        return salida.getvalue()

    def test_aplicar_propuesta_rechaza_cada_proveedor_gratis_en_una_ruta_de_vault(self):
        con_todo = {v: "1" for v in recetas.CLAVES_DE_ENTORNO}
        ap = self.aplicar(["archivos", "tecnica", "web", "general", "vision", "noticias"],
                          '{ archivos = ["claude_diego"], tecnica = ["codex"] }', con_todo)
        self.assertEqual(set(ap.sin_cuenta_pagada()), {"groq", "gemini", "openrouter", "tavily"})
        for proveedor in sorted(ap.sin_cuenta_pagada()):
            for ruta in ("archivos", "tecnica"):
                with self.subTest(proveedor=proveedor, ruta=ruta):
                    error = self.rechazo(ap, {ruta: ["claude_diego" if ruta == "archivos" else "codex", proveedor]})
                    self.assertIn(f"{recetas.NOMBRE_CUENTA[proveedor]} no puede ir en {ruta}: "
                                  "el vault no sale a una API externa", error)
        # Los demás muros del 15: cada proveedor sólo donde sirve, y la general sin pagadas.
        for valor, motivo in (({"web": ["gemini"]}, "no busca en la web"),
                              ({"web": ["openrouter", "claude_cami"]}, "no busca en la web"),
                              ({"vision": ["tavily", "claude_cami"]}, "es un buscador"),
                              ({"vision": ["openrouter"]}, "sin visión medida"),
                              ({"general": ["tavily"]}, "es un buscador"),
                              ({"general": ["groq", "claude_cami"]}, "las cuentas pagadas podrían leer credenciales"),
                              ({"noticias": ["gemini"]}, "sólo redacta lo que encuentra Tavily")):
            with self.subTest(valor=valor):
                self.assertIn(motivo, self.rechazo(ap, valor))
        # Lo permitido, con las keys cargadas, pasa y AMPLÍA (sale a una API externa nueva).
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as avisos:
            archivos, efecto, _, _, resumen = ap.armar_plan("p", "cuentas", {
                "web": ["tavily", "claude_cami", "claude_diego"], "general": ["groq", "gemini", "openrouter"],
                "vision": ["gemini", "claude_cami"], "noticias": ["tavily", "claude_cami"]})
        self.assertEqual(efecto, "AMPLIA")
        self.assertIn("web tavily → claude_cami → claude_diego", resumen)
        self.assertIn("pasa a poder salir a Tavily, una API externa sin cuenta pagada", avisos.getvalue())
        self.assertIn('gpt = ["groq", "gemini", "openrouter"]', archivos[0].nuevo)

    def test_aplicar_propuesta_rechaza_un_proveedor_sin_key(self):
        # Sin key cargada un proveedor no existe: no entra en ninguna cadena.
        solo_groq = {v: "" for v in recetas.CLAVES_DE_ENTORNO}
        solo_groq.update(GROQ_API_KEY="1", BOTV3_N8N_QUERY_URL="1")
        ap = self.aplicar(["web", "general", "vision"], '{ web = ["claude_cami"] }', solo_groq)
        for valor, proveedor, variable in (({"web": ["tavily", "claude_cami"]}, "Tavily", "TAVILY_API_KEY"),
                                           ({"general": ["groq", "gemini"]}, "Gemini", "GEMINI_API_KEY"),
                                           ({"general": ["groq", "openrouter"]}, "OpenRouter", "OPENROUTER_API_KEY"),
                                           ({"vision": ["gemini", "claude_cami"]}, "Gemini", "GEMINI_API_KEY")):
            with self.subTest(valor=valor):
                error = self.rechazo(ap, valor)
                self.assertIn(f"{proveedor} no esta listo en p (sin key ({variable})): no puede entrar en la cadena",
                              error)
                self.assertIn(f"sudo cargar-clave {variable} p", error)
        # Tavily con key pero sin ningún modelo gratis que redacte tampoco entra.
        ap.entorno_del_bot = lambda perfil: {"TAVILY_API_KEY": "1"}
        self.assertIn("sin un modelo gratis con key que redacte", self.rechazo(ap, {"web": ["tavily", "claude_cami"]}))
        # Con el bot detenido no hay entorno que medir: tampoco.
        ap.entorno_del_bot = lambda perfil: None
        self.assertIn("no se pudo medir el entorno del bot", self.rechazo(ap, {"web": ["tavily", "claude_cami"]}))

    def test_el_registro_conserva_los_proveedores_gratis_al_reescribirse(self):
        # `registro_cuentas` reescribe cuentas.toml entero: no puede borrar las tablas nuevas.
        ap = self.aplicar(["web"], '{ web = ["claude_cami"] }', {})
        raiz = Path(ap.VAULT_PI).parent
        shutil.copy(CUENTAS_FIJAS, raiz / "cuentas.toml")
        ap.REGISTRO_V = ap.REGISTRO_D = str(raiz / "cuentas.toml")
        archivos, efecto, *_ = ap.plan_registro({"claude_cami": {"precio_mes_usd": 25, "renueva": "jue 14:00"}})
        nuevo = ap.valores(archivos[0].nuevo)
        self.assertEqual(list(nuevo), ["claude_diego", "claude_cami", "codex", "groq", "gemini", "openrouter", "tavily"])
        self.assertEqual((nuevo["claude_cami"]["precio_mes_usd"], nuevo["claude_cami"]["renueva"]), (25, "jue 14:00"))
        for gratis in ("groq", "gemini", "openrouter", "tavily"):
            self.assertEqual(nuevo[gratis]["precio_mes_usd"], 0)
            self.assertEqual(nuevo[gratis]["motor"], gratis)
        # Un proveedor gratis no tiene precio ni renovación que proponer.
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ap.plan_registro({"gemini": {"precio_mes_usd": 5, "renueva": ""}})

    def test_el_registro_conserva_el_tope_de_busquedas_de_tavily(self):
        # 32br1: buscar-web.py lee `busquedas_max_encargo` de [tavily]; reescribir el registro no lo borra.
        ap = self.aplicar(["web"], '{ web = ["claude_cami"] }', {})
        raiz = Path(ap.VAULT_PI).parent
        texto = (PI.parent / "botv3" / "cuentas.toml").read_text(encoding="utf-8")   # el real, no la fixture
        self.assertEqual(ap.valores(texto)["tavily"]["busquedas_max_encargo"], 30)
        (raiz / "cuentas.toml").write_text(texto.replace("busquedas_max_encargo = 30", "busquedas_max_encargo = 12"),
                                           encoding="utf-8")
        ap.REGISTRO_V = ap.REGISTRO_D = str(raiz / "cuentas.toml")
        archivos, *_ = ap.plan_registro({"claude_cami": {"umbral_semanal": 70}})
        nuevo = ap.valores(archivos[0].nuevo)
        self.assertEqual(nuevo["tavily"]["busquedas_max_encargo"], 12)
        self.assertEqual(nuevo["claude_cami"]["umbral_semanal"], 70)

    def test_el_registro_actualiza_umbral_sin_perder_tablas_ni_cabecera(self):
        ap = self.aplicar(["web"], '{ web = ["claude_cami"] }', {})
        raiz = Path(ap.VAULT_PI).parent
        original = CUENTAS_FIJAS.read_text(encoding="utf-8")
        (raiz / "cuentas.toml").write_text(original, encoding="utf-8")
        ap.REGISTRO_V = ap.REGISTRO_D = str(raiz / "cuentas.toml")
        archivos, efecto, reiniciar, *_ = ap.plan_registro({"claude_cami": {"umbral_semanal": 75}})
        nuevo = ap.valores(archivos[0].nuevo)
        self.assertEqual(efecto, "neutro")
        self.assertFalse(reiniciar)  # registro_cuentas sigue en SIN_REINICIO
        self.assertEqual(nuevo["claude_cami"]["umbral_semanal"], 75)
        self.assertEqual(nuevo["claude_cami"]["umbral_5h"], 90)
        self.assertEqual(archivos[0].nuevo.split("\n[", 1)[0], original.split("\n[", 1)[0])
        self.assertEqual(list(nuevo), ["claude_diego", "claude_cami", "codex", "groq", "gemini", "openrouter", "tavily"])

    def test_el_registro_rechaza_umbral_fuera_de_tipo_o_rango(self):
        ap = self.aplicar(["web"], '{ web = ["claude_cami"] }', {})
        raiz = Path(ap.VAULT_PI).parent
        shutil.copy(CUENTAS_FIJAS, raiz / "cuentas.toml")
        ap.REGISTRO_V = ap.REGISTRO_D = str(raiz / "cuentas.toml")
        for valor in (0, 101, True, "75"):
            with self.subTest(valor=valor), self.assertRaises(SystemExit):
                ap.plan_registro({"claude_cami": {"umbral_semanal": valor}})

    def test_el_registro_con_solo_precio_conserva_los_umbrales_y_bots_info_lo_refleja(self):
        ap = self.aplicar(["web"], '{ web = ["claude_cami"] }', {})
        raiz = Path(ap.VAULT_PI).parent
        shutil.copy(CUENTAS_FIJAS, raiz / "cuentas.toml")
        ap.REGISTRO_V = ap.REGISTRO_D = str(raiz / "cuentas.toml")
        archivos, *_ = ap.plan_registro({"claude_cami": {"precio_mes_usd": 25}})
        registro = ap.valores(archivos[0].nuevo)
        self.assertEqual((registro["claude_cami"]["precio_mes_usd"],
                          registro["claude_cami"]["umbral_semanal"], registro["claude_cami"]["umbral_5h"]),
                         (25, 75, 90))
        margen = bi.margen_de(registro, {}, CiclosTests.AHORA, None, mod=recetas)
        self.assertEqual(margen["cuentas"]["claude_cami"]["umbral_semanal"], 75)
        archivos, *_ = ap.plan_registro({"claude_cami": {"umbral_semanal": 74}})
        registro = ap.valores(archivos[0].nuevo)
        margen = bi.margen_de(registro, {}, CiclosTests.AHORA, None, mod=recetas)
        self.assertEqual(margen["cuentas"]["claude_cami"]["umbral_semanal"], 74)

    # --- Encargo 24: el aviso previo por cuenta y ventana (aviso_5h, aviso_semanal) ---

    def _registro_de_avisos(self):
        ap = self.aplicar(["web"], '{ web = ["claude_cami"] }', {})
        raiz = Path(ap.VAULT_PI).parent
        shutil.copy(CUENTAS_FIJAS, raiz / "cuentas.toml")
        ap.REGISTRO_V = ap.REGISTRO_D = str(raiz / "cuentas.toml")
        return ap, raiz / "cuentas.toml"

    def _rechaza_registro(self, ap, valor):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            ap.plan_registro(valor)
        return err.getvalue()

    def test_el_registro_acepta_el_aviso_por_cuenta_y_ventana_y_lo_puede_quitar(self):
        ap, ruta = self._registro_de_avisos()
        original = ruta.read_text(encoding="utf-8")
        archivos, efecto, reiniciar, *_ = ap.plan_registro({"claude_cami": {"aviso_5h": 65, "aviso_semanal": 60}})
        nuevo = ap.valores(archivos[0].nuevo)
        self.assertEqual((efecto, reiniciar), ("neutro", False))
        self.assertEqual((nuevo["claude_cami"]["aviso_5h"], nuevo["claude_cami"]["aviso_semanal"]), (65, 60))
        # Solo esa cuenta: las demas no ganan clave, y los topes y la cabecera quedan.
        self.assertFalse([c for c in nuevo if c != "claude_cami" and ("aviso_5h" in nuevo[c] or "aviso_semanal" in nuevo[c])])
        self.assertEqual((nuevo["claude_cami"]["umbral_5h"], nuevo["claude_cami"]["umbral_semanal"]), (90, 75))
        self.assertEqual(archivos[0].nuevo.split("\n[", 1)[0], original.split("\n[", 1)[0])
        self.assertEqual(list(nuevo), ["claude_diego", "claude_cami", "codex", "groq", "gemini", "openrouter", "tavily"])
        # `null` lo quita: vuelve a no haber aviso, que es el comportamiento de antes del encargo 24.
        ruta.write_text(archivos[0].nuevo, encoding="utf-8")
        archivos, *_ = ap.plan_registro({"claude_cami": {"aviso_5h": None}})
        quitado = ap.valores(archivos[0].nuevo)["claude_cami"]
        self.assertNotIn("aviso_5h", quitado)
        self.assertEqual(quitado["aviso_semanal"], 60)

    def test_el_registro_rechaza_un_aviso_que_no_es_menor_que_el_tope_o_no_es_entero_de_1_a_100(self):
        ap, ruta = self._registro_de_avisos()
        # En o sobre el tope: llegaria cuando las colas ya esperan.
        for clave, tope in (("aviso_5h", 90), ("aviso_semanal", 75)):
            for valor in (tope, tope + 1, 100):
                with self.subTest(clave=clave, valor=valor):
                    self.assertIn("tiene que ser menor que", self._rechaza_registro(ap, {"claude_cami": {clave: valor}}))
        # Mismos rechazos que un umbral: fuera de 1-100, no entero, bool y texto.
        for valor in (0, -5, 101, 65.5, True, "65", [65]):
            with self.subTest(valor=valor):
                self.assertIn("tiene que ser un entero de 1 a 100", self._rechaza_registro(ap, {"claude_cami": {"aviso_5h": valor}}))
        # Un proveedor gratis no tiene aviso que proponer, y una clave que no conoce se rechaza.
        self._rechaza_registro(ap, {"groq": {"aviso_5h": 50}})
        self._rechaza_registro(ap, {"claude_cami": {"aviso_hora": 50}})
        # Contra el tope que QUEDARIA, no solo contra el que viaja: subir el aviso y bajar el tope en la misma propuesta.
        self.assertIn("tiene que ser menor que umbral_5h (60)", self._rechaza_registro(ap, {"claude_cami": {"aviso_5h": 70, "umbral_5h": 60}}))
        ap.plan_registro({"claude_cami": {"aviso_5h": 70, "umbral_5h": 80}})
        # Y bajar el tope por debajo de un aviso que ya esta puesto.
        archivos, *_ = ap.plan_registro({"claude_cami": {"aviso_5h": 70}})
        ruta.write_text(archivos[0].nuevo, encoding="utf-8")
        self.assertIn("tiene que ser menor que umbral_5h (65)", self._rechaza_registro(ap, {"claude_cami": {"umbral_5h": 65}}))
        self.assertEqual(ap.valores(ruta.read_text(encoding="utf-8"))["claude_cami"]["umbral_5h"], 90)    # un rechazo no escribe

    def test_la_pagina_propone_el_aviso_con_registro_cuentas_y_la_misma_validacion(self):
        js = leer(PAGINAS["cuentas"].parent / "cockpit-encargos" / "encargos.js")
        for linea in ('proponer({ tipo: "registro_cuentas", valor, clave: "avisos previos",',
                      "(Number.isInteger(n) && n >= 1 && n < x.tope)",
                      '"Proponer avisos previos"'):
            self.assertIn(linea, js)
        # La frase fija de 💳 Cuentas, sin un solo numero copiado.
        cuentas = leer(JS["cuentas"] if "cuentas" in JS else PAGINAS["cuentas"] / "cuentas.js")
        frase = cuentas.split("Las colas de encargos esperan cuando el % de ahora más el pronóstico", 1)[1].split(")", 1)[0]
        self.assertIn("pasa el tope", frase)
        self.assertNotRegex(frase.split("El aviso previo", 1)[0], r"\d")


# --- Encargo 13: 💳 Cuentas como herramienta propia de Cockpit ------------------------
PI = Path(__file__).resolve().parent
BOTV3 = PI.parent / "botv3"
CUENTAS_FIJAS = PI / "fixtures" / "avisos" / "cuentas.toml"
PAGINAS = {"bots": PI / "cockpit-bots", "nodo": PI / "cockpit-nodo", "cuentas": PI / "cockpit-cuentas"}
# Encargo 18: lo común se mudó del paquete `bots` al paquete `comun`, que no tiene menú.
COMUN = PI / "cockpit-comun"
JS = {"comun": COMUN / "comun.js", "bots": PAGINAS["bots"] / "bots.js",
      "nodo": PAGINAS["nodo"] / "nodo.js", "cuentas": PAGINAS["cuentas"] / "cuentas.js"}


def leer(ruta):
    return Path(ruta).read_text(encoding="utf-8")


def tokens_js(codigo, strings=False):
    """Tokenizador acotado de JS (en la Pi no hay node): recorre comentarios, strings,
    template literals con ${...} anidados y regex con clases, y devuelve el código que
    queda (sin nada de eso) después de comprobar que (), [] y {} cierran. No ejecuta.
    Con `strings`, los strings de comillas quedan en la salida, sin sus paréntesis,
    corchetes ni llaves: sirve para mirar cómo anida el código que arma la página."""
    pares = {")": "(", "]": "[", "}": "{"}
    pila, limpio = [], []          # pila: aperturas; "`" marca un ${ de template
    i, n = 0, len(codigo)
    previo = ""                    # último carácter significativo del código normal

    def error(msg):
        raise ValueError(f"{msg} en la línea {codigo.count(chr(10), 0, i) + 1}")

    def cadena(fin):
        nonlocal i
        inicio = i
        i += 1
        while i < n and codigo[i] != fin:
            if codigo[i] == "\n":
                error("string sin cerrar")
            i += 2 if codigo[i] == "\\" else 1
        if i >= n:
            error("string sin cerrar")
        i += 1
        if strings:
            limpio.append(re.sub(r"[()\[\]{}]", "", codigo[inicio:i]))

    def template():
        """Avanza por el texto de un template hasta su cierre o hasta un ${."""
        nonlocal i
        while i < n:
            c = codigo[i]
            if c == "\\":
                i += 2
            elif c == "`":
                i += 1
                return
            elif c == "$" and codigo[i + 1:i + 2] == "{":
                pila.append("`")
                i += 2
                return
            else:
                i += 1
        error("template literal sin cerrar")

    while i < n:
        c, sig = codigo[i], codigo[i + 1:i + 2]
        if c == "/" and sig == "/":
            while i < n and codigo[i] != "\n":
                i += 1
        elif c == "/" and sig == "*":
            fin = codigo.find("*/", i + 2)
            if fin < 0:
                error("comentario sin cerrar")
            i = fin + 2
        elif c in "'\"":
            cadena(c)
            previo = '"'
        elif c == "`":
            i += 1
            template()
            previo = '"'
        elif c == "/" and (previo == "" or previo in "(,=:[!&|?{};" or
                           re.search(r"\b(return|typeof)\s*$", "".join(limpio[-12:]))):
            i += 1
            clase = False
            while i < n and (clase or codigo[i] != "/"):
                if codigo[i] == "\n":
                    error("regex sin cerrar")
                if codigo[i] == "\\":
                    i += 1
                elif codigo[i] == "[":
                    clase = True
                elif codigo[i] == "]":
                    clase = False
                i += 1
            if i >= n:
                error("regex sin cerrar")
            i += 1
            previo = '"'
        else:
            if c in "([{":
                pila.append(c)
            elif c in ")]}":
                if not pila:
                    error(f"sobra «{c}»")
                abre = pila.pop()
                if c == "}" and abre == "`":
                    i += 1
                    template()   # se cerró un ${...}: sigue el texto del template
                    previo = '"'
                    continue
                if abre != pares[c]:
                    error(f"«{c}» cierra un «{abre}»")
            limpio.append(c)
            if not c.isspace():
                previo = c
            i += 1
    if pila:
        raise ValueError(f"quedaron sin cerrar: {''.join(pila)}")
    return "".join(limpio)


def declarados_arriba(codigo):
    """Nombres que un archivo declara en el nivel de arriba (columna 0)."""
    return set(re.findall(r"^(?:async\s+)?(?:function|const|let|var)\s+([A-Za-z_$][\w$]*)", codigo, re.M))


def tramo(codigo, marca):
    """Lo que hay entre el «(», «[» o «{» con que termina `marca` y su cierre, en código
    que ya pasó por `tokens_js(..., strings=True)`. None si `marca` no está."""
    if marca not in codigo:
        return None
    abre = marca[-1]
    cierra = {"(": ")", "[": "]", "{": "}"}[abre]
    inicio = i = codigo.index(marca) + len(marca)
    nivel = 1
    while nivel:
        nivel += (codigo[i] == abre) - (codigo[i] == cierra)
        i += 1
    return codigo[inicio:i - 1]


def forma_de_la_matriz(js):
    """Cómo arma la matriz el renderer de 💳 Cuentas, mirando cómo ANIDA su código (no
    hay con qué ejecutarlo en la Pi). La forma que manda es la de 13-notas-diego.md:
    una sola tabla, una fila por ruta, una columna por asistente y, en cada celda, los
    servicios de esa ruta en ese asistente."""
    codigo = tokens_js(js, strings=True)

    def dentro(marca, *trozos):
        t = tramo(codigo, marca)
        return t is not None and all(x in t for x in trozos)

    return {
        "una sola tabla": codigo.count('el("table", { class: "matriz-comun" }') == 1
                          and dentro("function pintarMatriz() {", 'el("table", { class: "matriz-comun" }')
                          and not dentro("function columnaPerfil(c, p, comun, repintar) {", 'el("table"'),
        "las filas son las rutas": dentro("comun.rutas.map(", 'el("tr"', 'el("th", { scope: "row", class: "ruta" }'),
        "cada fila tiene una celda por asistente": dentro("comun.rutas.map(", "columnas.map(col => col.celda(fila))"),
        "las columnas son los asistentes": "const columnas = comun.perfiles.map(c => columnaPerfil(" in codigo
                                           and ('el("thead", {}, el("tr", {}, el("th", { class: "ruta" }, "Ruta"), '
                                                'columnas.map(col => col.cabeza())))') in codigo,
        "la celda es de una ruta y un asistente": dentro("const celda = fila => {", "fila.celdas[perfil]",
                                                         'el("td", attrs('),
        "la celda trae sus servicios en orden": dentro("const celda = fila => {", "...edicion[r].map(de)",
                                                       "orden.map(muro => servicio(f, muro))"),
        "sin un panel por perfil": not any(x in codigo for x in (
            "panelMatriz", "panel-perfil", 'class: "perfiles"', "matriz-ruta", 'class: "celdas"', ".matriz.rutas")),
    }


def reglas_css(css):
    """[(media, selector, {propiedad: valor})] de una hoja sin más anidación que @media."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    reglas = []

    def bloque(texto, media):
        for selectores, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", texto):
            decl = {k.strip(): v.strip() for k, v in
                    (d.split(":", 1) for d in cuerpo.split(";") if ":" in d)}
            for sel in selectores.split(","):
                reglas.append((media, " ".join(sel.split()), decl))

    pos = 0
    for m in re.finditer(r"@media\s*([^{]+)\{((?:[^{}]*\{[^{}]*\})*[^{}]*)\}", css):
        bloque(css[pos:m.start()], "")
        bloque(m.group(2), " ".join(m.group(1).split()))
        pos = m.end()
    bloque(css[pos:], "")
    return reglas


class SalidaReal:
    """La salida REAL de bots-info, sin sudo: se llama a `bi.reunir()`, la misma función
    que imprime el script, sobre una copia en un temporal de lo que lee en la Pi. Los
    perfiles y cuentas.toml son los del vault (la forma desplegada); recetas.py, el del
    vault; uso.json y el libro, con la forma que ya usan las pruebas de arriba."""
    AHORA = datetime(2026, 10, 1, 21, 50, tzinfo=TZ)
    FUTURO_5H = "2026-10-02T03:39:59.685159+00:00"
    FUTURO_SEM = "2026-10-05T01:00:00.480719+00:00"
    PASADO = "2026-10-01T02:06:32-03:00"

    @classmethod
    def uso_json(cls):
        def limites(momento, h5, sem, renueva_5h, renueva_sem, plan=None):
            return {"momento": momento, "plan": plan,
                    "ventana_5h": {"usado_pct": h5, "renueva": renueva_5h},
                    "semanal": {"usado_pct": sem, "renueva": renueva_sem}}
        balde = {"entrada": 70, "salida": 38504, "cache_lectura": 14090211,
                 "cache_escritura": 378825, "mensajes": 35}
        return {"cuentas_interactivo": {
            "claude_diego": {"disponible": True, "por_hora": {"2026-10-01T20": balde},
                             "limites": limites("2026-10-01T21:33:33-03:00", 15, 97,
                                                cls.FUTURO_5H, "2026-10-03T06:59:59.685181+00:00")},
            # Cami sin ventana de 5 h abierta: `renueva` nulo, tal como lo publica uso.py.
            "claude_cami": {"disponible": True, "por_hora": {},
                            "limites": limites("2026-10-01T21:33:36-03:00", 0, 25, None, cls.FUTURO_SEM)},
            # Codex medido el día anterior: su ventana de 5 h ya se renovó.
            "codex": {"disponible": True, "por_hora": {},
                      "limites": limites("2026-09-30T21:59:55-03:00", 66.0, 84.0, cls.PASADO,
                                         "2026-10-03T16:52:39-03:00", plan="plus")}},
            "equipos": {"activos": {"DESKTOP-96QNU37": {
                "actualizado": "2026-09-30T20:48:44-03:00",
                "cuentas": {"claude_diego": {"limites": None, "motor": "claude",
                                             "por_hora": {"2026-09-30T19": balde}}}}},
                        "vencidos": {}}}

    @classmethod
    def armar(cls, caso, perfiles=("jaime", "pilar", "todas")):
        raiz = Path(tempfile.mkdtemp())
        caso.addCleanup(shutil.rmtree, raiz, True)
        bot = raiz / "botv3"
        (bot / "perfiles").mkdir(parents=True)
        for nombre in ("jaime", "pilar"):
            shutil.copy(BOTV3 / "perfiles" / f"{nombre}.toml", bot / "perfiles" / f"{nombre}.toml")
        # Un tercer perfil con TODAS las rutas que contesta un modelo: el TOML real de
        # jaime más `vision` y `noticias`, que hoy no trae ningún perfil.
        real = leer(BOTV3 / "perfiles" / "jaime.toml")
        linea = 'rutas = ["claude", "web", "gpt", "sql", "ha", "google", "codex", "boleta"]'
        caso.assertEqual(real.count(linea), 1, "cambió la línea `rutas` de jaime.toml")
        (bot / "perfiles" / "todas.toml").write_text(
            real.replace(linea, linea[:-1] + ', "vision", "noticias"]'), encoding="utf-8")
        shutil.copy(CUENTAS_FIJAS, bot / "cuentas.toml")
        (raiz / "uso.json").write_text(json.dumps(cls.uso_json()), encoding="utf-8")
        for perfil in ("jaime", "pilar", "todas"):
            estado = raiz / f"estado-{perfil}"
            for cid, c in bi.CUENTAS.items():
                if cid in bi.SIN_CUENTA_PAGADA:
                    continue
                (estado / "cuentas" / cid).mkdir(parents=True)
                if c["motor"] == "claude":
                    (estado / "cuentas" / cid / ".claude.json").write_text(json.dumps(
                        {"numStartups": 3, "oauthAccount": {"emailAddress": f"{cid}@example.com"}}),
                        encoding="utf-8")
            # Sólo jaime tiene login de Codex, como en la Pi.
            if perfil != "pilar":
                (estado / "cuentas" / "codex" / "auth.json").write_text(
                    json.dumps({"OPENAI_API_KEY": None, "tokens": {"access_token": "x"}}), encoding="utf-8")
        # El libro con la forma que escribe anotar_uso_cuenta (ver RendimientoTests).
        (raiz / "estado-jaime" / "uso-cuentas.jsonl").write_text(json.dumps(
            {"ts": "2026-10-01T20:00:00-03:00", "perfil": "jaime", "ruta": "claude",
             "cuenta": "claude_diego", "motor": "claude", "modelo": "claude-sonnet-4-20250514",
             "ok": True, "s": 2.0, "tokens": t(salida=10)}) + "\n", encoding="utf-8")
        (raiz / "voces").mkdir()
        (raiz / "propuestas").mkdir()
        (raiz / "unidades").mkdir()
        cambios = {
            "BOT_DIR": str(bot), "PERFILES": list(perfiles),
            "REGISTRO": str(bot / "cuentas.toml"), "USO_JSON": str(raiz / "uso.json"),
            "VOCES": str(raiz / "voces"), "PROPUESTAS": str(raiz / "propuestas"),
            "UNIDADES": str(raiz / "unidades"), "recetas": recetas,
            "estado_dir": lambda perfil: str(raiz / f"estado-{perfil}"),
            # `systemctl show` de una unidad detenida: las mismas claves, sin PID.
            "props": lambda unidad: {"ActiveState": "inactive", "SubState": "dead", "MainPID": "0",
                                     "User": "botv3", "ActiveEnterTimestamp": "",
                                     "ReadWritePaths": "", "ReadOnlyPaths": "",
                                     "InaccessiblePaths": "", "BindPaths": "",
                                     "BindReadOnlyPaths": "", "DropInPaths": ""},
        }
        for nombre, valor in cambios.items():
            caso.addCleanup(setattr, bi, nombre, getattr(bi, nombre))
            setattr(bi, nombre, valor)
        # La página recibe JSON: se pasa por el mismo viaje.
        return json.loads(json.dumps(bi.reunir(cls.AHORA), ensure_ascii=False))


class PaginaCuentasTests(unittest.TestCase):
    """💳 Cuentas armada con la forma real de bots-info (encargo 13)."""

    def setUp(self):
        self.info = SalidaReal.armar(self)

    def celdas(self, perfil):
        """Lo que la página pinta: {ruta: {cuenta: permitida}}, de `p.matriz.rutas`."""
        return {f["nombre"]: {c["cuenta"]: c["permitida"] for c in f["celdas"]}
                for f in self.info["perfiles"][perfil]["matriz"]["rutas"]}

    def test_la_matriz_respeta_los_muros(self):
        m = self.celdas("todas")
        self.assertEqual(set(m), {"archivos", "web", "general", "sql", "casa", "agenda",
                                  "tecnica", "vision", "noticias", "boleta"})
        # Codex fuera de web, noticias y vision.
        for ruta in ("web", "noticias", "vision"):
            self.assertIs(m[ruta]["codex"], False, ruta)
        # Groq fuera de archivos y tecnica (y de vision: no tiene visión).
        for ruta in ("archivos", "tecnica", "vision"):
            self.assertIs(m[ruta]["groq"], False, ruta)
        # 15: ningún proveedor gratis en las rutas que leen vaults.
        for ruta in ("archivos", "tecnica"):
            for proveedor in ("groq", "gemini", "openrouter", "tavily"):
                self.assertIs(m[ruta][proveedor], False, (ruta, proveedor))
        # general: sólo proveedores gratis (Tavily no: es un buscador); ninguna pagada.
        self.assertEqual({c for c, ok in m["general"].items() if ok}, {"groq", "gemini", "openrouter"})
        # Lo que sí se permite sigue estando: el muro no se comió la matriz.
        self.assertEqual({c for c, ok in m["archivos"].items() if ok},
                         {"claude_diego", "claude_cami", "codex"})
        self.assertEqual({c for c, ok in m["web"].items() if ok},
                         {"claude_diego", "claude_cami", "groq", "tavily"})
        self.assertEqual({c for c, ok in m["noticias"].items() if ok},
                         {"claude_diego", "claude_cami", "groq", "tavily"})
        self.assertEqual({c for c, ok in m["vision"].items() if ok}, {"claude_diego", "claude_cami", "gemini"})
        # Las herramientas fijas no ofrecen ninguna cuenta.
        for ruta in ("sql", "casa", "agenda"):
            self.assertEqual(m[ruta], {}, ruta)
        # Una celda prohibida trae su motivo; ninguna cadena ni atajo la usa.
        for f in self.info["perfiles"]["todas"]["matriz"]["rutas"]:
            prohibidas = {c["cuenta"] for c in f["celdas"] if not c["permitida"]}
            self.assertTrue(all(c["motivo"] for c in f["celdas"] if not c["permitida"]), f["nombre"])
            if f["fija"]:
                self.assertNotIn("cadena", f)
                continue
            self.assertFalse(prohibidas & set(f["cadena"]), f["nombre"])
            for a in self.info["perfiles"]["todas"]["matriz"]["atajos"].values():
                self.assertFalse(prohibidas & set(a["cadenas"][f["interna"]]), (a["etiqueta"], f["nombre"]))
        # Y es la misma tabla que valida aplicar-propuesta (recetas.permitida).
        for f in self.info["perfiles"]["todas"]["matriz"]["rutas"]:
            for c in f["celdas"]:
                self.assertEqual(c["permitida"], recetas.permitida(f["interna"], c["cuenta"])[0])

    def test_los_dos_perfiles_reales_van_juntos_y_cada_uno_con_lo_suyo(self):
        self.assertEqual(list(self.info["perfiles"])[:2], ["jaime", "pilar"])
        jaime = {f["nombre"]: f for f in self.info["perfiles"]["jaime"]["matriz"]["rutas"]}
        pilar = {f["nombre"]: f for f in self.info["perfiles"]["pilar"]["matriz"]["rutas"]}
        self.assertEqual(jaime["archivos"]["cadena"], ["claude_diego"])
        self.assertEqual(pilar["archivos"]["cadena"], ["claude_cami"])
        self.assertTrue(jaime["archivos"]["lee_archivos"] and not jaime["web"]["lee_archivos"])
        # `lista` se mide por perfil: pilar no tiene login de Codex y jaime sí.
        lista = lambda filas, ruta, cuenta: next(c["lista"] for c in filas[ruta]["celdas"] if c["cuenta"] == cuenta)
        self.assertTrue(lista(jaime, "archivos", "codex"))
        self.assertFalse(lista(pilar, "archivos", "codex"))
        self.assertIn("archivos", self.info["perfiles"]["jaime"]["lee_cyd"])

    def test_las_cuentas_y_sus_nombres_salen_de_bots_info(self):
        c = self.info["cuentas"]
        self.assertEqual({k: v["nombre"] for k, v in c.items()},
                         {"claude_diego": "Claude (Diego)", "claude_cami": "Claude (Cami)",
                          "codex": "Codex", "groq": "Groq", "gemini": "Gemini",
                          "openrouter": "OpenRouter", "tavily": "Tavily"})
        self.assertEqual({k for k, v in c.items() if v["pagada"]}, {"claude_diego", "claude_cami", "codex"})
        # Lo que antes era CUENTAS_CLAUDE en nodo.js.
        self.assertEqual({k: v["interactiva"] for k, v in c.items()},
                         {"claude_diego": {"config_dir": ""}, "claude_cami": {"config_dir": ".config/claude-cami"},
                          "codex": None, "groq": None, "gemini": None, "openrouter": None, "tavily": None})
        self.assertEqual({k for k, v in c.items() if v["ajena_a_cyd"]}, {"claude_cami"})

    def test_un_config_dir_raro_no_llega_a_la_pagina(self):
        # Termina en una línea de shell de 👾: nada de espacios, `;`, `$`, `..` ni absolutos.
        previo = dict(bi.INTERACTIVAS)
        self.addCleanup(lambda: (bi.INTERACTIVAS.clear(), bi.INTERACTIVAS.update(previo)))
        for malo in ("x; rm -rf ~", "$(id)", "../otro", "/etc", "a b", ".config/../x", "a/"):
            bi.INTERACTIVAS["claude_cami"] = malo
            self.assertIsNone(bi.cuentas_publicas()["claude_cami"]["interactiva"], malo)
        bi.INTERACTIVAS["claude_cami"] = ".config/claude-cami"
        self.assertEqual(bi.cuentas_publicas()["claude_cami"]["interactiva"], {"config_dir": ".config/claude-cami"})
        # Y la página lo vuelve a filtrar con la misma regla antes de usarlo.
        self.assertIn(r"/^[A-Za-z0-9._-]+(\/[A-Za-z0-9._-]+)*$/", leer(JS["comun"]))

    def test_margen_es_lo_primero_y_usa_el_criterio_del_bot(self):
        m = self.info["margen"]
        cami, diego, codex = (m["cuentas"][c] for c in ("claude_cami", "claude_diego", "codex"))
        self.assertEqual((cami["semanal"]["usado_pct"], cami["semanal"]["libre_pct"]), (25.0, 75.0))
        self.assertEqual(cami["semanal"]["renueva"], SalidaReal.FUTURO_SEM)
        # Sin ventana de 5 h abierta: 0 % usado y sin fecha, no «renovada».
        self.assertEqual(cami["ventana_5h"], {"usado_pct": 0.0, "libre_pct": 100.0,
                                              "renueva": None, "renovada": False})
        # 97 % semanal: pasó su umbral (75 en cuentas.toml desde el 03-10) y el bot la salta.
        self.assertTrue(diego["sobre"])
        self.assertEqual((diego["umbral_semanal"], diego["umbral_5h"], diego["libre_pct"]), (75, 90, 3.0))
        # La ventana de 5 h de Codex ya se renovó: ese 66 % no es dato (recetas.porcentaje).
        self.assertEqual(codex["ventana_5h"], {"usado_pct": None, "libre_pct": None,
                                               "renueva": SalidaReal.PASADO, "renovada": True})
        self.assertTrue(codex["sobre"])  # 84 % semanal
        self.assertEqual(codex["renueva_semana"], {"cuando": "2026-10-03T16:52:39-03:00", "origen": "medido"})
        self.assertFalse(m["cuentas"]["groq"]["pagada"])
        self.assertIsNone(m["cuentas"]["groq"]["semanal"])
        # Primero la que tiene margen; las que el bot salta, después; los gratis al final.
        self.assertEqual(m["orden"], ["claude_cami", "codex", "claude_diego", "groq", "gemini",
                                      "openrouter", "tavily"])
        for gratis in ("gemini", "openrouter", "tavily"):
            self.assertFalse(m["cuentas"][gratis]["pagada"])
            self.assertIsNone(m["cuentas"][gratis]["semanal"])
        self.assertEqual(m["con_margen"], "claude_cami")
        # Es el mismo «sobre» con que decide el bot en cada consulta.
        r = self.info["perfiles"]["jaime"]["recetas"]["rutas"]["archivos"]
        self.assertEqual(r["detalle"]["claude_diego"]["sobre"], diego["sobre"])
        # En la página, la sección de margen va antes que todas las demás.
        html = leer(PAGINAS["cuentas"] / "index.html")
        secciones = re.findall(r'<section class="tarjeta" id="([\w-]+)"', html)
        self.assertEqual(secciones, ["margen", "matriz", "proveedores", "cuentas-uso", "rendimiento",
                                     "pcs", "registro"])
        self.assertLess(leer(JS["cuentas"]).index("pintarMargen();"), leer(JS["cuentas"]).index("pintarMatriz();"))

    def test_sin_limites_no_se_inventa_margen(self):
        vacio = bi.margen_de(bi.registro_cuentas(), {}, SalidaReal.AHORA, None, mod=recetas)
        self.assertIsNone(vacio["con_margen"])
        self.assertIsNone(vacio["cuentas"]["claude_diego"]["semanal"])
        self.assertFalse(vacio["cuentas"]["claude_diego"]["sobre"])
        # Sin medición semanal, la renovación sale del ciclo del registro y se dice de dónde.
        resumen = bi.resumen_cuentas(bi.registro_cuentas(), [], SalidaReal.AHORA)
        m = bi.margen_de(bi.registro_cuentas(), {}, SalidaReal.AHORA, resumen, mod=recetas)
        self.assertEqual(m["cuentas"]["codex"]["renueva_semana"],
                         {"cuando": "2026-10-05T00:00-03:00", "origen": "supuesto"})

    def test_se_muda_el_uso_el_costo_el_rendimiento_y_los_pc(self):
        u = self.info["uso_cuentas"]
        self.assertEqual(set(u["cuentas"]), set(self.info["cuentas"]))
        self.assertIn("pc:DESKTOP-96QNU37", u["por_ruta"])           # el uso desde los PC (08)
        self.assertIn("jaime/claude", u["por_ruta"])
        self.assertEqual([(r["cuenta"], r["motor"]) for r in u["rendimiento"]], [("claude_diego", "claude")])
        self.assertEqual(u["cuentas"]["groq"]["precio_mes_usd"], 0)   # precio y renovación
        self.assertIn("proxima_renovacion", u["cuentas"]["codex"])
        js = leer(JS["cuentas"])
        for trozo in ("function pintarUso()", "function pintarRendimiento()", "function pintarPcs()",
                      "function pintarRegistro()", 'tipo: "registro_cuentas"', 'tipo: "cuentas"',
                      'tipo: "recetas"', "p.matriz.atajos", 'esPc = clave => clave.startsWith("pc:")'):
            self.assertIn(trozo, js)

    def test_la_pagina_usa_solo_campos_que_bots_info_entrega(self):
        # Cada `info.<campo>` de las páginas existe en la salida real. Era la falla de
        # siempre: una página en verde contra una forma que bots-info no entrega.
        for nombre, objeto in (("cuentas", "info"), ("bots", "info"), ("comun", "botsInfo")):
            usados = set(re.findall(rf"\b{objeto}\.([a-z_]+)\b", tokens_js(leer(JS[nombre]))))
            self.assertTrue(usados, nombre)
            self.assertFalse(usados - set(self.info), (nombre, usados - set(self.info)))
        # Lo mismo, un nivel más abajo, para lo que 💳 lee de cada fila, celda y margen.
        js = tokens_js(leer(JS["cuentas"]))
        fila = self.info["perfiles"]["todas"]["matriz"]["rutas"][0]
        for campo in ("interna", "nombre", "fija", "celdas", "cadena", "declarada", "lee_archivos",
                      "recomendada", "motivos"):
            self.assertIn(f"f.{campo}", js)
            self.assertIn(campo, fila)
        # La matriz común (filas = rutas, columnas = asistentes) y cada una de sus filas.
        for campo in ("perfiles", "rutas"):
            self.assertIn(f"comun.{campo}", js)
            self.assertIn(campo, self.info["matriz"])
        for campo in ("interna", "nombre", "celdas"):
            self.assertIn(f"fila.{campo}", js)
            self.assertIn(campo, self.info["matriz"]["rutas"][0])
        self.assertEqual(set(self.info["matriz"]["perfiles"][0]), {"id", "nombre", "persona"})
        for campo in ("cuenta", "permitida", "motivo", "aviso", "lista"):
            self.assertIn(f"muro.{campo}", js)
            self.assertIn(campo, fila["celdas"][0])
        # 15: lo que la página lee de un proveedor gratis, en la matriz y en su tabla.
        gratis = next(c for c in fila["celdas"] if c["cuenta"] == "tavily")
        for campo in ("falta", "estado"):
            self.assertIn(f"muro.{campo}", js)
            self.assertIn(campo, gratis)
        for campo in ("falta", "cargar", "lista", "cuenta"):
            self.assertIn(f"abierto.{campo}", js)
            self.assertIn(campo, gratis)
        tabla = self.info["proveedores"]
        for campo in ("proveedores", "probar"):
            self.assertIn(f"t.{campo}", js)
            self.assertIn(campo, tabla)
        for campo in ("nombre", "que_es", "rutas", "por_perfil", "nota", "modelo_var"):
            self.assertIn(f"p.{campo}", js)
            self.assertIn(campo, tabla["proveedores"]["tavily"])
        for campo in ("listo", "estado", "modelo", "falta", "medido", "key", "cargar"):
            self.assertIn(f"x.{campo}", js)
            self.assertIn(campo, tabla["proveedores"]["tavily"]["por_perfil"]["jaime"])
        for campo in ("orden", "con_margen", "cuentas"):
            self.assertIn(f"m.{campo}", js)
            self.assertIn(campo, self.info["margen"])
        cuenta = self.info["margen"]["cuentas"]["claude_diego"]
        for campo in ("pagada", "nombre", "sobre", "ventana_5h", "semanal", "umbral_5h",
                      "umbral_semanal", "renueva_semana", "momento", "viejo"):
            self.assertIn(f"c.{campo}", js)
            self.assertIn(campo, cuenta)
        for campo in ("usado_pct", "libre_pct", "renueva", "renovada"):
            self.assertIn(f"v.{campo}", js)
            self.assertIn(campo, cuenta["semanal"])
        # Un servicio prohibido se pinta gris y sin acción: sale de `permitida`, no de una lista.
        crudo = leer(JS["cuentas"])
        self.assertIn('if (!muro.permitida) {', crudo)
        self.assertIn('{ class: "chip servicio prohibida", title: muro.motivo }', crudo)
        self.assertIn('{ class: "servicio-boton", disabled: true, title: muro.motivo }', crudo)

    def test_asistentes_ya_no_tiene_la_matriz_pero_si_el_enlace(self):
        js, html = leer(JS["bots"]), leer(PAGINAS["bots"] / "index.html")
        for fuera in ("matriz-ruta", "celda-boton", "function tarjetaCuentas(", "function bloqueRecetas(",
                      "function pintarUsoCuentas(", "Proponer cuentas", "Proponer recetas", "p.matriz.atajos",
                      'tipo: "cuentas"', 'tipo: "recetas"', 'tipo: "registro_cuentas"', "Rendimiento por motor"):
            self.assertNotIn(fuera, js, fuera)
        self.assertNotIn("cuentas-uso", html)
        for selector in (".matriz", ".celda", ".atajos", ".recetas", ".cuenta-uso"):
            self.assertNotIn(selector, leer(PAGINAS["bots"] / "bots.css"), selector)
        # Queda el resumen de lectura por ruta y el enlace a la herramienta nueva.
        self.assertIn("function tarjetaCuentasResumen(p)", js)
        self.assertIn("tarjetaCuentasResumen(p)", js.split("async function pintarPerfil()")[1].split("\n}\n")[0])
        self.assertIn('cockpit.jump("/cuentas")', js)
        self.assertIn('"contesta ", (f.cadena || []).map(nombreCuenta).join(" → ")', js)
        resumen = js.split("function tarjetaCuentasResumen(p)")[1].split("\n}\n")[0]
        self.assertNotIn("proponer", resumen)      # sólo lectura
        self.assertNotIn("onclick: () => {", resumen)
        # El enlace apunta a un paquete que existe; el orden del menú es el del encargo 18.
        manifiestos = {d.name: json.loads(leer(d / "manifest.json")) for d in
                       (PI / n for n in ("cockpit-sistema", "cockpit-nodo", "cockpit-bots",
                                         "cockpit-luces", "cockpit-noticias", "cockpit-cuentas"))}
        cuentas = manifiestos["cockpit-cuentas"]
        self.assertEqual((cuentas["name"], cuentas["tools"]["index"]["label"]), ("cuentas", "💳 Cuentas"))
        orden = sorted(manifiestos.values(), key=lambda m: m["tools"]["index"]["order"])
        self.assertEqual([m["name"] for m in orden], ["sistema", "nodo", "bots", "cuentas", "noticias", "luces"])
        self.assertEqual(len({m["tools"]["index"]["order"] for m in orden}), 6)
        self.assertEqual(json.loads(leer(PAGINAS["nodo"] / "manifest.json"))["tools"]["index"]["label"], "👾 IA Agents")
        # 👾 mantiene su selector de cuenta interactiva.
        self.assertIn('<select id="cuenta-claude">', leer(PAGINAS["nodo"] / "index.html"))
        self.assertIn("guardarPreferencia(ev.target.value)", leer(JS["nodo"]))


class MatrizComunTests(unittest.TestCase):
    """La forma de la matriz que decidió Diego el 01-10 (encargos/13-notas-diego.md, que
    manda sobre el encargo): filas = rutas, columnas = Jaime y Pilar, y cada celda con
    los servicios de esa ruta en ese asistente. Arreglos de la vuelta 1 (13r1)."""

    RUTAS_DE_DIEGO = ["archivos", "tecnica", "web", "general", "vision", "noticias",
                      "casa", "agenda", "sql", "boleta"]

    def setUp(self):
        # Los dos perfiles REALES del vault, como en la Pi: sin el tercero de las otras pruebas.
        self.info = SalidaReal.armar(self, perfiles=("jaime", "pilar"))
        self.matriz = self.info["matriz"]

    def test_filas_son_rutas_y_columnas_los_dos_asistentes(self):
        m = self.matriz
        # Columnas: los dos asistentes, con el nombre que trae cada perfil real.
        self.assertEqual(m["perfiles"], [{"id": "jaime", "nombre": "Jaime", "persona": "Diego"},
                                         {"id": "pilar", "nombre": "Pilar", "persona": "Camila"}])
        # Filas: las rutas, una vez cada una y en el orden que anotó Diego.
        self.assertEqual([f["nombre"] for f in m["rutas"]], self.RUTAS_DE_DIEGO)
        # Cada fila tiene exactamente una celda por asistente, la tenga o no.
        for fila in m["rutas"]:
            self.assertEqual(list(fila["celdas"]), ["jaime", "pilar"], fila["nombre"])
        # Qué rutas tiene cada uno sale de su perfil real, no de una lista de la prueba.
        for perfil in ("jaime", "pilar"):
            toml = bi.leer_toml(str(BOTV3 / "perfiles" / f"{perfil}.toml"))
            suyas = {recetas.ruta_nombre(recetas.ruta_interna(r)) for r in toml["rutas"]}
            self.assertTrue(suyas)
            con_celda = {f["nombre"] for f in m["rutas"] if f["celdas"][perfil] is not None}
            self.assertEqual(con_celda, suyas, perfil)
            # Ninguna ruta del perfil se quedó sin fila, y la celda es la fila de ESE perfil.
            propia = {f["interna"]: f for f in self.info["perfiles"][perfil]["matriz"]["rutas"]}
            self.assertEqual(len(propia), len(suyas))
            for fila in m["rutas"]:
                self.assertEqual(fila["celdas"][perfil], propia.get(fila["interna"]), (perfil, fila["nombre"]))
        celda = lambda ruta, perfil: next(f for f in m["rutas"] if f["nombre"] == ruta)["celdas"][perfil]
        # La ruta que un asistente no tiene queda en la matriz, vacía: no se oculta la fila.
        for ruta in ("agenda", "sql"):
            self.assertIsNotNone(celda(ruta, "jaime"), ruta)
            self.assertIsNone(celda(ruta, "pilar"), ruta)
        # La cola 41 dejó técnica disponible para Pilar; este encargo la preserva.
        self.assertIsNotNone(celda("tecnica", "pilar"))
        for ruta in ("vision", "noticias"):
            self.assertEqual((celda(ruta, "jaime"), celda(ruta, "pilar")), (None, None), ruta)
        # De un vistazo, ruta por ruta, quién contesta en cada asistente.
        self.assertEqual((celda("archivos", "jaime")["cadena"], celda("archivos", "pilar")["cadena"]),
                         (["claude_diego"], ["claude_cami"]))
        self.assertEqual(celda("tecnica", "jaime")["cadena"], ["codex"])
        self.assertEqual((celda("web", "jaime")["cadena"], celda("web", "pilar")["cadena"]),
                         (["claude_cami", "claude_diego"], ["claude_cami", "claude_diego"]))
        # Cada celda trae TODOS los servicios (los que suma el 15 entran solos), con su
        # sesión medida en ese asistente y lo prohibido marcado con su motivo.
        for fila in m["rutas"]:
            for perfil, f in fila["celdas"].items():
                if f is None:
                    continue
                if f["fija"] and not f["celdas"]:
                    continue    # herramienta fija: no la contesta ningún servicio
                self.assertEqual([c["cuenta"] for c in f["celdas"]], list(self.info["cuentas"]),
                                 (perfil, fila["nombre"]))
                for c in f["celdas"]:
                    self.assertEqual(c["permitida"], recetas.permitida(f["interna"], c["cuenta"])[0])
                    self.assertTrue(c["permitida"] or c["motivo"])
                if not f["fija"]:
                    prohibidas = {c["cuenta"] for c in f["celdas"] if not c["permitida"]}
                    self.assertFalse(prohibidas & set(f["cadena"]), (perfil, fila["nombre"]))
        sesion = lambda ruta, perfil, cuenta: next(
            c["lista"] for c in celda(ruta, perfil)["celdas"] if c["cuenta"] == cuenta)
        self.assertTrue(sesion("archivos", "jaime", "codex"))
        self.assertFalse(sesion("archivos", "pilar", "codex"))
        # general (15): ya no es fija; elige entre los proveedores gratis y ninguna pagada.
        # Sin nada declarado sigue siendo Groq por n8n, en los dos asistentes.
        for perfil in ("jaime", "pilar"):
            f = celda("general", perfil)
            self.assertIsNone(f["fija"])
            self.assertEqual((f["cadena"], f["declarada"]), (["groq"], False))
            self.assertEqual([c["cuenta"] for c in f["celdas"] if c["permitida"]],
                             ["groq", "gemini", "openrouter"])

    def test_con_todas_las_rutas_la_fila_es_la_misma_y_no_se_duplica(self):
        # Con un perfil que sí trae vision y noticias, esas filas se llenan en SU columna
        # y siguen vacías en las otras; el orden y la cantidad de filas no cambian.
        info = SalidaReal.armar(self)
        m = info["matriz"]
        self.assertEqual([p["id"] for p in m["perfiles"]], ["jaime", "pilar", "todas"])
        self.assertEqual([f["nombre"] for f in m["rutas"]], self.RUTAS_DE_DIEGO)
        vision = next(f for f in m["rutas"] if f["nombre"] == "vision")["celdas"]
        self.assertEqual((vision["jaime"], vision["pilar"]), (None, None))
        self.assertEqual(vision["todas"]["cadena"], ["claude_cami", "claude_diego"])
        # Una herramienta fija que ningún perfil tiene (plantas) no agrega una fila vacía;
        # si un perfil la tiene, entra después de las de Diego.
        self.assertNotIn("plantas", [f["nombre"] for f in m["rutas"]])
        con_plantas = {"jaime": {"toml": {"nombre": "Jaime"}, "matriz": bi.matriz_de(
            "jaime", {"rutas": ["plantas", "claude"], "cuentas": {}}, {}, mod=recetas)}}
        self.assertEqual([f["nombre"] for f in bi.matriz_comun(con_plantas, mod=recetas)["rutas"]],
                         ["archivos", "tecnica", "web", "general", "vision", "noticias", "plantas"])

    def test_la_estrella_es_la_recomendada_por_funcion_y_trae_su_motivo(self):
        # 15: la ⭐ dejó de ser «la cuenta con más margen» (13) y pasó a ser la cadena que
        # calcula recetas.recomendada para la función de la ruta, con su motivo.
        celda = lambda info, ruta, perfil: next(
            f for f in info["matriz"]["rutas"] if f["nombre"] == ruta)["celdas"][perfil]
        # Como está la Pi hoy para la prueba: los bots detenidos, o sea sin entorno que
        # medir. Ningún proveedor gratis está listo y la recomendada es la cadena de hoy.
        for ruta, perfil in (("archivos", "jaime"), ("tecnica", "jaime"), ("web", "jaime"),
                             ("archivos", "pilar"), ("web", "pilar")):
            f = celda(self.info, ruta, perfil)
            self.assertEqual(f["recomendada"], f["cadena"], (ruta, perfil))
            self.assertEqual(set(f["motivos"]), set(f["cadena"]))
        self.assertEqual((celda(self.info, "general", "jaime")["recomendada"],
                          celda(self.info, "general", "jaime")["motivos"]), ([], {}))
        self.assertNotIn("recomendada", celda(self.info, "sql", "jaime"))       # herramienta fija
        self.assertIn("lee los vaults; ningún proveedor gratis puede",
                      celda(self.info, "archivos", "jaime")["motivos"]["claude_diego"])
        self.assertIn("no hay un proveedor gratis apto y listo en este bot para buscar en la web",
                      celda(self.info, "web", "jaime")["motivos"]["claude_cami"])

        # Con las keys cargadas en Jaime y sólo la de Groq en Pilar (cada bot, lo suyo).
        todo = {v: "1" for v in recetas.CLAVES_DE_ENTORNO}
        solo_groq = {**{v: "" for v in recetas.CLAVES_DE_ENTORNO}, "GROQ_API_KEY": "1", "BOTV3_N8N_QUERY_URL": "1"}
        self.addCleanup(bi.ENTORNO_DE_PRUEBA.clear)
        bi.ENTORNO_DE_PRUEBA.update(jaime=todo, pilar=solo_groq, todas=todo)
        info = SalidaReal.armar(self)
        self.assertEqual({r: celda(info, r, "jaime")["recomendada"] for r in ("archivos", "tecnica", "web", "general")},
                         {"archivos": ["claude_diego"], "tecnica": ["codex"],
                          "web": ["tavily", "claude_cami", "claude_diego"],
                          "general": ["groq", "gemini", "openrouter"]})
        self.assertEqual({r: celda(info, r, "todas")["recomendada"] for r in ("vision", "noticias")},
                         {"vision": ["gemini", "claude_cami", "claude_diego"],
                          "noticias": ["tavily", "claude_cami", "claude_diego"]})
        self.assertEqual(celda(info, "web", "jaime")["motivos"]["tavily"],
                         "Tavily + Groq: busca gratis y trae la fecha de la fuente")
        # Pilar no tiene la key de Tavily ni la de Gemini: su recomendada no los nombra.
        self.assertEqual({r: celda(info, r, "pilar")["recomendada"] for r in ("archivos", "web", "general")},
                         {"archivos": ["claude_cami"], "web": ["claude_cami", "claude_diego"], "general": ["groq"]})
        # Es exactamente lo que calcula recetas.recomendada con lo medido en ese bot, y nunca
        # una celda prohibida, un gratis sin key ni un gratis en una ruta de vault.
        for perfil in ("jaime", "pilar", "todas"):
            for f in info["perfiles"][perfil]["matriz"]["rutas"]:
                if f["fija"]:
                    self.assertNotIn("recomendada", f)
                    continue
                listas = {c["cuenta"]: c["lista"] for c in f["celdas"]}
                esperado = recetas.recomendada(f["interna"], lambda ruta, c: listas[c] if ruta == f["interna"]
                                               else info["perfiles"][perfil]["por_cuenta"][c]["sesion"], f["cadena"])
                self.assertEqual((f["recomendada"], f["motivos"]), (esperado[0], esperado[1]), (perfil, f["nombre"]))
                for c in f["recomendada"]:
                    self.assertTrue(recetas.permitida(f["interna"], c)[0], (perfil, f["nombre"], c))
                    if not info["cuentas"][c]["pagada"]:
                        self.assertTrue(listas[c], (perfil, f["nombre"], c))
                        self.assertFalse(f["lee_archivos"], (perfil, f["nombre"], c))
                self.assertNotEqual(f["recomendada"][:1], ["openrouter"])
        # El atajo «Recomendado por función» llena la edición con esa misma cadena.
        atajo = info["perfiles"]["jaime"]["matriz"]["atajos"]["recomendado"]
        self.assertEqual(atajo["etiqueta"], "Recomendado por función")
        for f in info["perfiles"]["jaime"]["matriz"]["rutas"]:
            if not f["fija"]:
                self.assertEqual(atajo["cadenas"][f["interna"]], f["recomendada"] or f["cadena"], f["nombre"])
        self.assertEqual(atajo["nota"], "")
        self.assertEqual(info["perfiles"]["pilar"]["matriz"]["atajos"]["recomendado"]["nota"],
                         "sin un proveedor gratis apto y con key para: web")

    def test_el_renderer_pinta_una_sola_tabla_ruta_por_asistente(self):
        js = leer(JS["cuentas"])
        forma = forma_de_la_matriz(js)
        self.assertEqual({k for k, v in forma.items() if not v}, set(), forma)
        # La inspección mide: la forma que rechazó la revisión 13r1 (un panel por perfil
        # y, adentro, una fila por ruta con una grilla de proveedores) no pasa.
        invertida = '''
            function pintarMatriz() {
                const paneles = ids.map(id => panelMatriz(id, info.perfiles[id]));
                cont.replaceChildren(el("div", { class: "perfiles" }, paneles));
            }
            function panelMatriz(perfil, p) {
                const filas = (p.matriz && p.matriz.rutas) || [];
                cuerpo.replaceChildren(...filas.map(f => el("div", { class: "matriz-ruta" },
                    el("div", { class: "celdas" }, f.celdas.map(m => celda(f, m))))));
                return el("div", { class: "panel-perfil", "data-perfil": perfil }, cuerpo);
            }'''
        self.assertEqual({k for k, v in forma_de_la_matriz(invertida).items() if v}, set())
        # Y cada condición falla por separado si se le saca su pieza al renderer real.
        roturas = {
            "una sola tabla": ('el("table", { class: "matriz-comun" },', 'el("div", { class: "matriz-comun" },'),
            "las filas son las rutas": ("comun.rutas.map(fila => el(\"tr\", {},", "comun.perfiles.map(fila => el(\"tr\", {},"),
            "cada fila tiene una celda por asistente": ("columnas.map(col => col.celda(fila))", "col0.celda(fila)"),
            "las columnas son los asistentes": ("const columnas = comun.perfiles.map(c => columnaPerfil(",
                                                 "const columnas = comun.rutas.map(c => columnaPerfil("),
            "la celda es de una ruta y un asistente": ("const f = fila.celdas[perfil];", "const f = fila;"),
            "la celda trae sus servicios en orden": ("orden.map(muro => servicio(f, muro))", "[]"),
            "sin un panel por perfil": ("const propias = comun.rutas.map(fila => fila.celdas[perfil]).filter(Boolean);",
                                        "const propias = p.matriz.rutas;"),
        }
        self.assertEqual(set(roturas), set(forma))
        for condicion, (viejo, nuevo) in roturas.items():
            self.assertEqual(js.count(viejo), 1, condicion)
            self.assertFalse(forma_de_la_matriz(js.replace(viejo, nuevo))[condicion], condicion)
        # La fila la arma UNA lista común: el renderer recorre `info.matriz`, que es la que
        # se comprobó arriba contra los dos perfiles reales.
        self.assertIn("const comun = info.matriz;", js)
        # La ruta que el asistente no tiene: celda vacía y tenue, pero celda (no se salta).
        columna = tramo(tokens_js(js, strings=True), "function columnaPerfil(c, p, comun, repintar) {")
        self.assertIn('if (problema || !f)\n            return el("td", attrs("vacia"),', columna)
        vacia = [d for _, sel, d in reglas_css(leer(PAGINAS["cuentas"] / "cuentas.css")) if sel == ".matriz-comun td.vacia"]
        self.assertEqual(len(vacia), 1)
        self.assertLess(float(vacia[0]["opacity"]), 1)
        self.assertNotIn("display", vacia[0])
        # Se edita tocando la celda (agregar, subir a primero, quitar), sin formularios.
        servicio = tramo(tokens_js(js, strings=True), "const servicio = (f, muro) => {")
        for accion in ("ids.push(cid)", "ids.splice(pos, 1); ids.unshift(cid)", "tocar(() => { ids.splice(pos, 1); })"):
            self.assertIn(accion, servicio, accion)
        for formulario in ('el("input"', 'el("select"', 'el("form"', 'el("textarea"'):
            self.assertNotIn(formulario, columna, formulario)
        # En el servicio se ve la sesión, el % de cuota, la ⭐ del recomendado y el gris de lo prohibido.
        # 15: la ⭐ es un botón propio (tocarla muestra el motivo, que llega en `f.motivos`) y
        # un proveedor gratis sin key no se puede agregar: tocarlo dice cómo cargarla.
        self.assertIn("const recomendado = (f.recomendada || []).includes(cid);", servicio)
        self.assertIn('recomendado ? el("button", { class: "estrella", title: (f.motivos || {})[cid]', servicio)
        self.assertIn("onclick: () => explicar(clave) }", servicio)
        self.assertIn("const ausente = !con && pos < 0 && !!muro.falta;", servicio)
        self.assertIn("onclick: () => ausente ? explicar(clave) : tocar(() => {", servicio)
        celda = tramo(tokens_js(js, strings=True), "const celda = fila => {")
        self.assertIn("f.motivos[abierto.cuenta]", celda)
        self.assertIn('el("code", {}, abierto.cargar)', celda)
        self.assertIn('el("span", { class: "estado " + (con ? "ok" : "mal") }', servicio)
        self.assertIn("semanal(cid)", servicio)
        self.assertIn('class: "chip servicio prohibida"', servicio)
        # La propuesta sigue siendo de UN perfil: la de la columna que se tocó.
        proponer = tramo(tokens_js(js, strings=True), "const proponerCuentas = () => {")
        self.assertIn('tipo: "cuentas"', proponer)
        self.assertTrue(proponer.rstrip().endswith("}, perfil);"), proponer[-40:])
        self.assertIn("const perfil = c.id;", columna)
        self.assertNotIn("info.perfiles", columna)      # una columna no mira al otro asistente

    def test_en_angosto_se_ve_una_sola_columna_sin_scroll_horizontal(self):
        reglas = reglas_css(leer(PAGINAS["cuentas"] / "cuentas.css"))
        self.assertEqual({m for m, _, _ in reglas}, {"", "(max-width: 900px)"})
        de = lambda media, selector: [d for m, s, d in reglas if (m, s) == (media, selector)]
        angosto = "(max-width: 900px)"
        # En ancho se ven todas las columnas y las pestañas no; en angosto, al revés: sólo
        # la columna del asistente activo, que es la misma tabla.
        self.assertEqual(de("", ".pestanas.solo-angosto"), [{"display": "none"}])
        self.assertEqual(de(angosto, ".pestanas.solo-angosto"), [{"display": "flex", "flex-wrap": "wrap"}])
        self.assertEqual(de(angosto, ".matriz-comun .col-perfil:not(.activa)"), [{"display": "none"}])
        ocultan = [(m, s) for m, s, d in reglas if "col-perfil" in s and d.get("display") == "none"]
        self.assertEqual(ocultan, [(angosto, ".matriz-comun .col-perfil:not(.activa)")])
        # «Activa» es exactamente una: todo lo de una columna (cabeza, celdas, pie y su
        # pestaña) lleva data-perfil, y elegir() deja activa sólo la del asistente elegido,
        # también después de repintar por una edición.
        js = leer(JS["cuentas"])
        codigo = tokens_js(js, strings=True)
        self.assertIn('const attrs = clase => ({ class: "col-perfil" + (clase ? " " + clase : ""), "data-perfil": perfil });', js)
        columna = tramo(codigo, "function columnaPerfil(c, p, comun, repintar) {")
        self.assertEqual(len(re.findall(r'el\("t[dh]", ', columna)), len(re.findall(r'el\("t[dh]", attrs\(', columna)))
        self.assertEqual(len(re.findall(r'el\("t[dh]", attrs\(', columna)), 6)   # cabeza, vacía, fija, celda y los dos pies
        elegir = tramo(codigo, "const elegir = id => {")
        self.assertIn("perfilVisible = id;", elegir)
        self.assertIn('n.classList.toggle("activa", n.dataset.perfil === id)', elegir)
        self.assertTrue(tramo(codigo, "const pintar = () => {").rstrip().endswith("elegir(perfilVisible);"))
        self.assertIn("if (!perfilVisible || !nombres.includes(perfilVisible)) perfilVisible = nombres[0];", js)
        self.assertIn('el("button", { "data-perfil": c.id, onclick: () => elegir(c.id) }', js)
        # Sin scroll horizontal: la tabla ocupa el ancho y lo reparte (no la ensancha el
        # contenido), los servicios bajan de línea y en angosto nada tiene ancho fijo.
        self.assertEqual(de("", ".matriz-comun"), [{"table-layout": "fixed", "width": "100%"}])
        self.assertEqual(de("", ".servicios")[0]["flex-wrap"], "wrap")
        self.assertEqual(de("", ".servicio")[0]["max-width"], "100%")
        self.assertEqual(de("", ".servicio-boton")[0]["flex-wrap"], "wrap")
        self.assertEqual(de("", ".matriz-comun .col-perfil")[0]["overflow-wrap"], "anywhere")
        for selector in (".matriz-comun", ".matriz-comun tr", ".matriz-comun th.ruta", ".matriz-comun .col-perfil.activa"):
            self.assertEqual(de(angosto, selector)[0], {"display": "block", "width": "auto"}, selector)
        de_la_matriz = re.compile(r"matriz-comun|servici|col-perfil|celda-nota|atajos|pestanas|avisos-cuentas")
        vistas = 0
        for media, selector, decl in reglas:
            if not de_la_matriz.search(selector):
                continue
            vistas += 1
            for prop, valor in decl.items():
                self.assertFalse(prop.startswith("overflow-x") or (prop == "overflow" and valor != "hidden"), selector)
                self.assertFalse(prop == "white-space" and "nowrap" in valor, selector)
                self.assertFalse(prop == "flex-wrap" and valor == "nowrap", selector)
                if prop in ("width", "min-width") and valor.endswith("px"):
                    # Lo único con ancho fijo: la columna de la ruta (en ancho) y el toque de la ✕.
                    self.assertLessEqual(float(valor[:-2]), 124, (media, selector, prop))
                    self.assertTrue(media == "" or selector == ".servicio .quitar", (media, selector, prop))
        self.assertGreater(vistas, 25)
        # La columna fija de la ruta deja de serlo en angosto (pasa a título de su celda).
        self.assertEqual(de("", ".matriz-comun th.ruta")[0]["width"], "124px")


class PaginasSinDuplicarTests(unittest.TestCase):
    """Cero duplicación, JS balanceado y nada de style= en línea (encargo 13)."""

    def test_js_balanceado_con_el_tokenizador(self):
        for nombre, ruta in JS.items():
            with self.subTest(nombre):
                self.assertTrue(tokens_js(leer(ruta)).strip())
        # Y el tokenizador mide algo: lo roto lo detecta, lo raro pero válido lo deja pasar.
        self.assertTrue(tokens_js('const a = `x ${f({ b: `y ${c}` })} z`; // }\nconst r = /[/)]\\//g;'))
        self.assertTrue(tokens_js("const d = (a + b) / 2; const s = '}' + \"(\"; /* ] */"))
        for roto in ("function f() { return (1; }", "const a = [1, 2;", "const t = `a ${b`;",
                     "if (x) { y(); ", "f());", "const s = 'abc;\n"):
            with self.assertRaises(ValueError, msg=roto):
                tokens_js(roto)
        roto = leer(JS["cuentas"]).replace("function pintarPcs() {", "function pintarPcs() {{", 1)
        with self.assertRaises(ValueError):
            tokens_js(roto)

    def test_no_hay_style_en_linea(self):
        archivos = [f for d in (*PAGINAS.values(), COMUN) for f in sorted(d.iterdir())
                    if f.suffix in (".html", ".js")]
        self.assertEqual(len(archivos), 10)    # 3 HTML, 3 JS de página y los 4 JS de `comun`
        for f in archivos:
            texto = leer(f)
            with self.subTest(f.name):
                self.assertIsNone(re.search(r"style\s*=", texto))
                self.assertNotIn("<style", texto)
                self.assertNotIn("innerHTML", texto)
                self.assertNotIn("cssText", texto)
                self.assertIsNone(re.search(r"""setAttribute\(\s*["']style""", texto))
                # el() pondría un atributo style: sólo se acepta el `style: false` de siempre.
                self.assertEqual(re.findall(r"\bstyle:\s*(\S+)", tokens_js(texto) if f.suffix == ".js" else texto),
                                 ["false,"] if f.name == "bots.js" else [])
                # Quien marca un ancho con data-ancho lo aplica por CSSOM.
                if f.suffix == ".js" and '"data-ancho"' in texto:
                    self.assertTrue("aplicarAnchos(" in texto or ".style.flexGrow = " in texto)
        self.assertIn("s.style.flexGrow = s.dataset.ancho", leer(JS["comun"]))
        self.assertEqual(leer(JS["cuentas"]).count("aplicarAnchos(cont);"), 2)   # margen y uso

    def test_lo_comun_vive_en_un_solo_archivo_que_cargan_las_tres(self):
        # Cockpit sirve `../comun/comun.js` entre paquetes (mismo origen, CSP 'self'), así
        # que no hay copias: el archivo existe una sola vez y las tres páginas lo cargan.
        # Desde el encargo 18 vive en el paquete `comun`, no en `bots`; comun.css ya no
        # existe (los chips y las barras están en base.css).
        self.assertEqual([str(f.relative_to(PI)) for f in sorted(PI.glob("cockpit-*/**/comun.js"))],
                         ["cockpit-comun/comun.js"])
        self.assertEqual(list(PI.glob("cockpit-*/**/comun.css")), [])
        comunes_js = ["../comun/dom.js", "../comun/barra.js", "../comun/comun.js"]
        for pagina in ("bots", "nodo", "cuentas"):
            html = leer(PAGINAS[pagina] / "index.html")
            scripts = re.findall(r'<script src="([^"]+)"', html)
            # dom.js (el), barra.js (barraNodo) y comun.js van, en ese orden, antes que el
            # script de la página, que usa sus funciones.
            self.assertEqual(scripts[-4:], comunes_js + [f"{pagina}.js"], pagina)
            self.assertIn('<link href="../comun/base.css" rel="stylesheet" />', html, pagina)
            self.assertNotIn("../bots/", html, pagina)
            # Todo lo que la página carga existe con la disposición instalada
            # (~/.local/share/cockpit/<paquete>/): `../comun/x` es pi/cockpit-comun/x.
            for ref in scripts + re.findall(r'<link href="([^"]+)"', html):
                if ref.startswith("../base1/"):
                    continue
                destino = COMUN / ref[len("../comun/"):] if ref.startswith("../comun/") \
                    else PAGINAS[pagina] / ref
                self.assertTrue(destino.is_file(), (pagina, ref))
            # Y cada id que el JS busca existe en su HTML o lo crea el propio JS (la barra
            # compartida crea #leido y #actualizar; comun.js, el diálogo).
            codigo = leer(COMUN / "barra.js") + leer(JS["comun"]) + leer(JS[pagina])
            creados = set(re.findall(r'\bid: "([\w-]+)"', codigo))
            en_html = set(re.findall(r'\bid="([\w-]+)"', html))
            buscados = set(re.findall(r'getElementById\("([\w-]+)"\)', leer(JS[pagina])))
            if pagina != "nodo":
                buscados |= {"error"}
            # Encargo 18: las propuestas se listan sólo en 🤖; 💳 muestra el contador.
            buscados |= {"bots": {"propuestas"}, "cuentas": {"propuestas-contador"}}.get(pagina, set())
            self.assertFalse(buscados - en_html - creados, (pagina, buscados - en_html - creados))
        # Lo común está en `comun` (dom.js, tema.js, comun.js) y en ningún otro: nadie lo
        # vuelve a declarar.
        comunes = (declarados_arriba(leer(JS["comun"])) | declarados_arriba(leer(COMUN / "dom.js"))
                   | declarados_arriba(leer(COMUN / "tema.js")) | declarados_arriba(leer(COMUN / "barra.js")))
        self.assertLessEqual({"el", "proponer", "pintarPropuestas", "nombreCuenta", "pagada", "nombreRuta",
                              "cuentasConocidas", "cuentasInteractivas", "leerBotsInfo", "aplicarTema",
                              "barraUso", "chipsMargen", "aplicarAnchos", "barraNodo"}, comunes)
        for nombre in ("bots", "nodo", "cuentas"):
            self.assertFalse(comunes & declarados_arriba(leer(JS[nombre])), nombre)
        # Los estilos de chips y barras, sólo en base.css.
        for hoja in (PAGINAS["bots"] / "bots.css", PAGINAS["cuentas"] / "cuentas.css", PAGINAS["nodo"] / "nodo.css"):
            self.assertIsNone(re.search(r"^\.(chips?|barra-ciclo|insignia)\s*\{", leer(hoja), re.M), hoja.name)
        self.assertIsNotNone(re.search(r"^\.chip \{", leer(COMUN / "base.css"), re.M))
        self.assertIsNotNone(re.search(r"^\.barra-ciclo \{", leer(COMUN / "base.css"), re.M))

    def test_ninguna_pagina_vuelve_a_escribir_las_cuentas_ni_los_muros(self):
        ids = set(bi.cuentas_todas(recetas))
        self.assertEqual(ids, {"claude_diego", "claude_cami", "codex", "groq", "gemini", "openrouter", "tavily"})
        for nombre, ruta in JS.items():
            codigo = tokens_js(leer(ruta))      # sin comentarios ni strings
            crudo = leer(ruta)
            with self.subTest(nombre):
                # Ni tablas de cuentas, ni ids, ni nombres para mostrar escritos a mano.
                self.assertIsNone(re.search(r"\bCUENTAS(_CLAUDE)?\b", codigo))
                self.assertIsNone(re.search(r"\b(claude_diego|claude_cami|groq)\b", codigo))
                self.assertIsNone(re.search(r"""["'`](claude_diego|claude_cami|groq)["'`]""", crudo))
                # 15: tampoco los proveedores gratis, sus variables ni sus reglas.
                self.assertIsNone(re.search(r"\b(gemini|openrouter|tavily)\b", codigo, re.I))
                self.assertIsNone(re.search(r"""["'`](gemini|openrouter|tavily)["'`]""", crudo, re.I))
                self.assertIsNone(re.search(r"_API_KEY|cargar-clave|APTITUD|FUNCION\b|recomendada\(", crudo))
                self.assertNotIn("Claude (Diego)", crudo)
                self.assertNotIn("Claude (Cami)", crudo)
                self.assertNotIn(".config/claude-cami", crudo)
                # Ni reglas de muros: listas de rutas con receta o que leen archivos.
                self.assertIsNone(re.search(r"\b(RUTAS_CON_RECETA|LEEN_ARCHIVOS|PROHIBIDO|MUROS)\b", codigo))
        # `codex` sólo queda como ruta (bots.js) y como agente con sesión propia (nodo.js),
        # nunca como cuenta en la página de cuentas ni en lo común.
        for nombre in ("cuentas", "comun"):
            self.assertIsNone(re.search(r"\bcodex\b", tokens_js(leer(JS[nombre]))), nombre)
            self.assertIsNone(re.search(r"""["'`]codex["'`]""", leer(JS[nombre])), nombre)
        # Los nombres llegan de bots-info y las páginas los piden a comun.js.
        self.assertIn("function nombreCuenta(id) {\n    return (cuentasConocidas()[id] || {}).nombre || id;",
                      leer(JS["comun"]))
        self.assertIn("return (botsInfo && botsInfo.cuentas) || {};", leer(JS["comun"]))
        self.assertIn("cuentasInteractivas(info.cuentas || {})", leer(JS["nodo"]))
        self.assertIn('const BOTS_INFO = ["sudo", "-n", "/usr/local/bin/bots-info"];', leer(JS["comun"]))
        for nombre in ("bots", "cuentas", "nodo"):
            self.assertNotIn("/usr/local/bin/bots-info\"]", leer(JS[nombre]), nombre)
            self.assertIn("leerBotsInfo()", leer(JS[nombre]), nombre)


def _cargar(nombre, ruta):
    # Sin dejar un __pycache__ al lado: la carpeta de la página se instala con `cp -r`.
    import sys
    antes, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location(nombre, ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    finally:
        sys.dont_write_bytecode = antes
    return modulo


# Keys de mentira con la forma de las reales (prefijo, largo y los «_», «-» y «.» que
# traen): si alguna aparece en una salida, la prueba la encuentra.
KEYS_FALSAS = {"GROQ_API_KEY": "gsk_FIXTURE0groq0" + "a1B2" * 10,
               "GEMINI_API_KEY": "AQ.FIXTURE-gemini_" + "c3D4" * 9,
               "OPENROUTER_API_KEY": "sk-or-v1-FIXTURE" + "e5f6" * 14,
               "TAVILY_API_KEY": "tvly-dev-FIXTURE_" + "g7H8" * 10}


class ProveedoresGratisTests(unittest.TestCase):
    """Encargo 15: lo que 💳 Cuentas muestra de los proveedores gratis («listo» o «sin
    key»), que ninguna key sale de bots-info, y los dos scripts nuevos."""

    def entorno(self, *variables, modelo=None):
        """Lo que hay en /proc/<pid>/environ de un bot, reducido por la función real."""
        pares = [f"{v}={KEYS_FALSAS[v]}" for v in variables if v in KEYS_FALSAS]
        pares += ["BOTV3_N8N_QUERY_URL=http://127.0.0.1:5678/webhook/x", "BOTV3_TOKEN=123:FIXTURE-token"]
        if modelo:
            pares.append(f"BOTV3_GEMINI_MODEL={modelo}")
        return bi.reducir_entorno("\0".join(pares).encode() + b"\0", recetas)

    def armar(self, **entornos):
        self.addCleanup(bi.ENTORNO_DE_PRUEBA.clear)
        bi.ENTORNO_DE_PRUEBA.update(entornos)
        return SalidaReal.armar(self)

    def test_cada_proveedor_figura_listo_o_sin_key_en_cada_asistente(self):
        info = self.armar(jaime=self.entorno(*KEYS_FALSAS, modelo="gemini-3.5-flash-lite"),
                          pilar=self.entorno("GROQ_API_KEY", "TAVILY_API_KEY"))
        tabla = info["proveedores"]["proveedores"]
        self.assertEqual(list(tabla), ["groq", "gemini", "openrouter", "tavily"])
        estado = lambda perfil: {c: p["por_perfil"][perfil]["estado"] for c, p in tabla.items()}
        self.assertEqual(estado("jaime"), {c: "listo" for c in tabla})
        self.assertEqual(estado("pilar"), {"groq": "listo", "gemini": "sin key", "openrouter": "sin key",
                                           "tavily": "listo"})
        # «todas» no tiene entorno medido (su bot no corre): no se da por listo ni por sin key.
        self.assertEqual(set(estado("todas").values()), {"sin medir"})
        sin = tabla["gemini"]["por_perfil"]["pilar"]
        self.assertEqual((sin["listo"], sin["key"], sin["falta"], sin["cargar"]),
                         (False, False, "sin key (GEMINI_API_KEY)", "sudo cargar-clave GEMINI_API_KEY pilar"))
        # El modelo: el de la variable del bot o el de por defecto de recetas.py.
        self.assertEqual(tabla["gemini"]["por_perfil"]["jaime"]["modelo"], "gemini-3.5-flash-lite")
        self.assertEqual(tabla["groq"]["por_perfil"]["pilar"]["modelo"], recetas.PROVEEDORES["groq"]["modelo"])
        self.assertEqual(tabla["tavily"]["por_perfil"]["jaime"]["modelo"], "")
        # En qué rutas puede ir cada uno sale de los muros, no de una lista aparte.
        self.assertEqual({c: p["rutas"] for c, p in tabla.items()},
                         {"groq": ["web", "general", "noticias"], "gemini": ["general", "vision"],
                          "openrouter": ["general"], "tavily": ["web", "noticias"]})
        self.assertEqual({c: p["key"] for c, p in tabla.items()},
                         {c: p["key"] for c, p in recetas.PROVEEDORES.items()})
        self.assertNotIn("url", tabla["tavily"])
        # En la matriz, el servicio sin key lo dice y trae la línea para cargarla.
        fila = next(f for f in info["perfiles"]["pilar"]["matriz"]["rutas"] if f["nombre"] == "general")
        celdas = {c["cuenta"]: c for c in fila["celdas"]}
        self.assertEqual((celdas["gemini"]["lista"], celdas["gemini"]["estado"], celdas["gemini"]["cargar"]),
                         (False, "sin key", "sudo cargar-clave GEMINI_API_KEY pilar"))
        self.assertEqual((celdas["groq"]["lista"], celdas["groq"]["estado"]), (True, "listo"))
        self.assertNotIn("estado", celdas["claude_cami"])       # las pagadas tienen sesión, no key
        # Tavily con key pero sin ningún modelo que redacte: «no listo», y dice qué falta.
        solo = self.armar(jaime=self.entorno("TAVILY_API_KEY"))["proveedores"]["proveedores"]["tavily"]
        self.assertEqual((solo["por_perfil"]["jaime"]["estado"], solo["por_perfil"]["jaime"]["key"]),
                         ("no listo", True))
        self.assertIn("que redacte", solo["por_perfil"]["jaime"]["falta"])
        # Sin key, un proveedor no entra en ninguna cadena ni atajo de ese asistente.
        for perfil in ("jaime", "pilar"):
            p = info["perfiles"][perfil]
            for f in p["matriz"]["rutas"]:
                if f["fija"]:
                    continue
                ausentes = {c["cuenta"] for c in f["celdas"] if c.get("estado") in ("sin key", "no listo")}
                self.assertFalse(ausentes & set(f["recomendada"]), (perfil, f["nombre"]))
                self.assertFalse(ausentes & set(p["matriz"]["atajos"]["recomendado"]["cadenas"][f["interna"]]))
        # Los cuatro cuestan cero y no tienen límite semanal.
        for c in tabla:
            self.assertEqual(info["uso_cuentas"]["cuentas"][c]["precio_mes_usd"], 0)
            self.assertEqual(info["uso_cuentas"]["cuentas"][c]["usd_semana"], 0)
        self.assertEqual(info["uso_cuentas"]["total_mes_usd"], 60)

    def test_ninguna_key_sale_de_bots_info(self):
        reducido = self.entorno(*KEYS_FALSAS, modelo="gemini-3.6-flash")
        self.assertEqual({k: v for k, v in reducido.items() if not k.endswith("_MODEL")},
                         {"BOTV3_N8N_QUERY_URL": "1", "GROQ_API_KEY": "1", "GEMINI_API_KEY": "1",
                          "OPENROUTER_API_KEY": "1", "TAVILY_API_KEY": "1"})
        self.assertEqual(reducido["BOTV3_GEMINI_MODEL"], "gemini-3.6-flash")
        # Una variable de modelo con algo que no parece un modelo no se muestra.
        raro = bi.reducir_entorno(b"BOTV3_GEMINI_MODEL=$(cat /etc/passwd)\0GEMINI_API_KEY= \0", recetas)
        self.assertEqual((raro.get("BOTV3_GEMINI_MODEL", ""), raro["GEMINI_API_KEY"]), ("", ""))
        salida = json.dumps(self.armar(jaime=reducido, pilar=reducido), ensure_ascii=False)
        for variable, key in KEYS_FALSAS.items():
            self.assertNotIn(key, salida, variable)
            self.assertNotIn(key[-12:], salida, variable)
        self.assertNotIn("FIXTURE", salida)
        self.assertNotIn("127.0.0.1:5678", salida)
        # aplicar-propuesta mide lo mismo y tampoco guarda valores.
        ap = _cargar("aplicar_prueba_env", PI / "aplicar-propuesta.py")
        ap.recetas = recetas
        self.assertEqual(set(recetas.CLAVES_DE_ENTORNO),
                         {"BOTV3_N8N_QUERY_URL"} | {p["key"] for p in recetas.PROVEEDORES.values()})

    def test_cargar_clave_no_muestra_la_key_y_acepta_guiones(self):
        cc = _cargar("cargar_clave", PI / "cargar-clave.py")
        # La lista fija es la de la tabla de proveedores, ni una más (Mistral se ignora).
        self.assertEqual(set(cc.VARIABLES), {p["key"] for p in recetas.PROVEEDORES.values()} |
                         {"SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"})
        self.assertNotIn("MISTRAL_API_KEY", cc.VARIABLES)
        for variable, key in KEYS_FALSAS.items():
            self.assertEqual(cc.problema_de_forma(key), "", variable)
            texto = cc.verificacion(variable, key)
            self.assertIn(f"{len(key)} caracteres", texto)
            self.assertNotIn(key[len(cc.VARIABLES[variable]):][:6], texto)
        # La forma de la de Mistral del 01-10 (con «_»), que la primera verificación midió como 0.
        con_guion_bajo = "Ab3_" + "xY9z" * 8 + "-_Q"
        self.assertEqual(cc.problema_de_forma(con_guion_bajo), "")
        self.assertEqual(cc.valor_en(f"OTRA=1\nGROQ_API_KEY={con_guion_bajo}\n", "GROQ_API_KEY"), con_guion_bajo)
        self.assertEqual(cc.valor_en(f'GROQ_API_KEY="{con_guion_bajo}"\n', "GROQ_API_KEY"), con_guion_bajo)
        self.assertEqual(cc.verificacion("GROQ_API_KEY", con_guion_bajo),
                         f"GROQ_API_KEY: {len(con_guion_bajo)} caracteres; empieza con «gsk_»: NO")
        self.assertIn("empieza con «gsk_»: si", cc.verificacion("GROQ_API_KEY", KEYS_FALSAS["GROQ_API_KEY"]))
        for mala in ("", "corta", "con espacio " + "a" * 30, "a" * 30 + "\n", "comilla'" + "a" * 30, "ñ" * 30):
            self.assertTrue(cc.problema_de_forma(mala), repr(mala))
            self.assertNotIn(mala.strip() or "¬", cc.problema_de_forma(mala))
        # Escribe de forma atómica, conserva lo demás byte por byte y los permisos, y respalda.
        raiz = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, raiz, True)
        archivo = raiz / "botv3-jaime.env"
        antes = ("BOTV3_TOKEN=123:abc\n# comentario\nGROQ_API_KEY=gsk_vieja_0000000000000000\n"
                 "BOTV3_CHAT_ID=1\nGROQ_API_KEY=gsk_repetida_000000000000\n")
        archivo.write_text(antes, encoding="utf-8")
        os.chmod(archivo, 0o640)
        cc.SECRETOS = str(raiz)
        import contextlib
        import io
        from datetime import datetime as fecha
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
            respaldo = cc.escribir(str(archivo), "GROQ_API_KEY", KEYS_FALSAS["GROQ_API_KEY"], fecha(2026, 10, 1, 23, 0, 0))
            cc.escribir(str(archivo), "TAVILY_API_KEY", KEYS_FALSAS["TAVILY_API_KEY"], fecha(2026, 10, 1, 23, 0, 1))
        self.assertEqual(archivo.read_text(encoding="utf-8"),
                         f"BOTV3_TOKEN=123:abc\n# comentario\nGROQ_API_KEY={KEYS_FALSAS['GROQ_API_KEY']}\n"
                         f"BOTV3_CHAT_ID=1\nTAVILY_API_KEY={KEYS_FALSAS['TAVILY_API_KEY']}\n")
        self.assertEqual(archivo.stat().st_mode & 0o777, 0o640)
        self.assertEqual((Path(respaldo).read_text(encoding="utf-8"), Path(respaldo).stat().st_mode & 0o777),
                         (antes, 0o600))
        self.assertEqual(sorted(f.name for f in raiz.iterdir() if f.name.startswith(".")), [])   # sin temporales
        # La key no se acepta como argumento (quedaría en el historial y en `ps`) y nada de
        # lo que imprime la trae. Sin root no llega a pedirla.
        for args in (["GROQ_API_KEY", KEYS_FALSAS["GROQ_API_KEY"]], ["GROQ_API_KEY", "jaime", KEYS_FALSAS["GROQ_API_KEY"]],
                     ["MISTRAL_API_KEY", "jaime"], ["GROQ_API_KEY"], ["GROQ_API_KEY", "noexiste"],
                     ["GROQ_API_KEY", "jaime"], ["--desde-botv3-env", "TAVILY_API_KEY", "jaime"]):
            with self.subTest(args=args[:1] + ["…"]), contextlib.redirect_stdout(salida), \
                    contextlib.redirect_stderr(salida), self.assertRaises(SystemExit):
                cc.pedir = lambda variable: self.fail("no debió pedir la key")
                cc.main(list(args))
        with contextlib.redirect_stdout(salida):
            self.assertEqual(cc.main(["--lista"]), 0)
        impreso = salida.getvalue()
        self.assertIn("necesita root", impreso)
        self.assertIn("¿pegaste la key como argumento?", impreso)
        self.assertIn("TAVILY_API_KEY  (empieza con tvly-)", impreso)
        for key in KEYS_FALSAS.values():
            self.assertNotIn(key, impreso)
            self.assertNotIn(key[10:22], impreso)
        # La línea que muestra la página es la de este script, con el perfil que mide cada bot.
        self.assertEqual(recetas.linea_para_cargar("openrouter", "pilar"), "sudo cargar-clave OPENROUTER_API_KEY pilar")
        self.assertIn("EnvironmentFile=/opt/nodo/datos/secretos/botv3-%i.env", leer(BOTV3 / "botv3@.service"))
        self.assertEqual(cc.archivo_de("pilar"), str(raiz / "botv3-pilar.env"))

    def test_probar_distingue_modelo_retirado_de_key_invalida_y_no_muestra_la_key(self):
        pp = _cargar("probar_proveedor", PAGINAS["cuentas"] / "probar-proveedor.py")
        # El botón corre el script que se instala con la página.
        self.assertEqual(bi.PROBAR[-1], "/home/dcifu004/.local/share/cockpit/cuentas/probar-proveedor.py")
        self.assertTrue((PAGINAS["cuentas"] / Path(bi.PROBAR[-1]).name).is_file())
        # En la carpeta de la página sólo va lo que se instala: nada de __pycache__.
        self.assertEqual(sorted(f.name for f in PAGINAS["cuentas"].iterdir()),
                         ["cuentas.css", "cuentas.js", "index.html", "manifest.json", "probar-proveedor.py"])
        self.assertIsNotNone(pp.cargar_recetas(str(BOTV3 / "recetas.py")))
        entorno = {v: k for v, k in KEYS_FALSAS.items()}
        vistas = []

        def con(estado, cuerpo):
            def llamar(url, clave, pedido):
                vistas.append((url, clave, pedido))
                return estado, cuerpo
            return llamar

        ok = {"model": "gemini-3.6-flash", "choices": [{"message": {"role": "assistant", "content": "OK"}}]}
        r = pp.probar(recetas, "gemini", "jaime", entorno, con(200, ok))
        self.assertEqual((r["ok"], r["modelo"], r["clase"], r["error"]), (True, "gemini-3.6-flash", "", ""))
        url, clave, pedido = vistas[-1]
        self.assertEqual((url, clave, pedido["model"]),
                         ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                          KEYS_FALSAS["GEMINI_API_KEY"], "gemini-3.6-flash"))
        self.assertEqual(len(vistas), 1)        # una llamada, sin reintentos
        # Los cuerpos reales del 01-10: el mismo 4xx, dos causas distintas.
        casos = (
            ("gemini", 404, [{"error": {"code": 404, "status": "NOT_FOUND", "message":
                                        "This model models/gemini-2.5-flash is no longer available to new users."}}],
             "modelo"),
            ("gemini", 400, [{"error": {"code": 400, "message": "Invalid Auth key.", "status": "INVALID_ARGUMENT"}}], "key"),
            ("groq", 400, {"error": {"message": "The model `llama3-8b-8192` has been decommissioned and is no "
                                     "longer supported.", "code": "model_decommissioned"}}, "modelo"),
            ("groq", 401, {"error": {"message": "Invalid API Key", "code": "invalid_api_key"}}, "key"),
            ("openrouter", 400, {"error": {"message": "x/y:free is not a valid model ID", "code": 400},
                                 "user_id": "user_FIXTURE"}, "modelo"),
            ("openrouter", 401, {"error": {"message": "User not found.", "code": 401}}, "key"),
            ("openrouter", 200, {"id": "gen-1", "error": {"message": "Upstream error from Nvidia: ResourceExhausted",
                                                         "code": 502}}, "saturado"),
            ("openrouter", 429, {"error": {"message": "Provider returned error", "code": 429, "metadata": {
                "raw": "x:free is temporarily rate-limited upstream."}}}, "limite"),
            ("tavily", 401, {"detail": {"error": "Unauthorized: missing or invalid API key."}}, "key"),
        )
        for proveedor, estado, cuerpo, clase in casos:
            with self.subTest(proveedor=proveedor, clase=clase):
                r = pp.probar(recetas, proveedor, "jaime", entorno, con(estado, cuerpo))
                self.assertFalse(r["ok"])
                self.assertEqual((r["clase"], r["explicacion"]), (clase, recetas.CLASES_DE_ERROR[clase]))
                # El error va tal cual lo dijo el proveedor.
                self.assertIn(recetas.detalle_de_error(cuerpo), r["error"])
                self.assertNotIn("user_FIXTURE", json.dumps(r))
        self.assertIn("la key está bien", recetas.CLASES_DE_ERROR["modelo"])
        self.assertIn("cargarla de nuevo", recetas.CLASES_DE_ERROR["key"])
        # Tavily es un buscador: se prueba buscando, no con un chat.
        r = pp.probar(recetas, "tavily", "jaime", entorno, con(200, {"results": []}))
        self.assertEqual((r["ok"], r["modelo"], vistas[-1][0], vistas[-1][2]["max_results"]),
                         (True, "buscador", "https://api.tavily.com/search", 1))
        # Sin key en el archivo del bot no llama a nadie y dice cómo cargarla.
        antes = len(vistas)
        r = pp.probar(recetas, "openrouter", "pilar", {}, con(200, ok))
        self.assertEqual((r["ok"], r["clase"], len(vistas)), (False, "key", antes))
        self.assertIn("sudo cargar-clave OPENROUTER_API_KEY pilar", r["explicacion"])
        # Aunque el proveedor o la red devuelvan la key en su mensaje, no sale.
        eco = {"error": {"message": f"Invalid API Key {KEYS_FALSAS['GROQ_API_KEY']}"}}
        r1 = pp.probar(recetas, "groq", "jaime", entorno, con(401, eco))

        def cae(url, clave, pedido):
            raise OSError(f"no pude conectar con Bearer {clave}")
        r2 = pp.probar(recetas, "groq", "jaime", entorno, cae)
        self.assertEqual((r2["ok"], r2["clase"]), (False, "otro"))
        for r in (r1, r2):
            self.assertNotIn(KEYS_FALSAS["GROQ_API_KEY"], json.dumps(r, ensure_ascii=False))
            self.assertIn("[KEY]", r["error"])
        # La página no arma la llamada: corre lo que le entrega bots-info y pinta el resultado.
        js = leer(JS["cuentas"])
        self.assertIn("cockpit.spawn([...t.probar, id, perfil], { err: \"message\" })", js)
        for campo in ("ok", "modelo", "segundos", "explicacion", "error"):
            self.assertIn(f"r.{campo}", js)
            self.assertIn(campo, r1)


# --- Encargo 23a: la propuesta `encargos_config` edita encargos/modelos.toml -----------
MODELOS_VIVO = PI.parent / "encargos" / "modelos.toml"      # el real: solo se comprueba que parsea y es valido
MODELOS_REAL = PI / "fixtures" / "encargos" / "modelos.toml"   # copia fija (23h): base de lo que se afirma
CACHE_CODEX = PI / "fixtures" / "encargos" / "models_cache.json"   # el real de la Pi, solo los campos leidos
CACHE_CODEX_VIVO = Path("/opt/nodo/datos/agentes/codex-home/models_cache.json")


def aplicar_encargos(prueba, cache=CACHE_CODEX):
    """aplicar-propuesta apuntado a una COPIA FIJA del modelos.toml (pi/fixtures/encargos), en una carpeta
    temporal: una propuesta aplicada al archivo vivo no puede poner rojas las pruebas."""
    ap = _cargar(f"aplicar_encargos_{id(prueba)}", PI / "aplicar-propuesta.py")
    raiz = Path(tempfile.mkdtemp())
    prueba.addCleanup(shutil.rmtree, raiz, True)
    shutil.copy(MODELOS_REAL, raiz / "modelos.toml")
    ap.MODELOS_ENCARGOS, ap.CODEX_MODELOS = str(raiz / "modelos.toml"), str(cache)
    return ap, raiz / "modelos.toml"


class EncargosConfigTests(unittest.TestCase):
    def setUp(self):
        self.ap, self.copia = aplicar_encargos(self)
        self.original = self.copia.read_text(encoding="utf-8")
        self.cfg = self.ap.valores(self.original)

    def rechazo(self, valor, motivo="", ap=None):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stderr(salida), contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaises(SystemExit):
            (ap or self.ap).armar_plan("no-es-un-perfil", "encargos_config", valor, motivo)
        self.assertEqual(self.copia.read_text(encoding="utf-8"), self.original)   # un rechazo no escribe
        return salida.getvalue()

    def test_el_archivo_vivo_parsea_y_es_valido(self):
        """Lo unico que se afirma del modelos.toml vivo (23h): sus valores cambian desde la pestana."""
        import tomllib
        crudo = MODELOS_VIVO.read_bytes()
        self.assertEqual(crudo.count(b"\r"), 0)
        cfg = tomllib.loads(crudo.decode("utf-8"))
        self.assertLessEqual({"niveles", "autorizacion", "naturaleza", "reparto"}, set(cfg))
        self.assertEqual(set(cfg["reparto"]), set(cfg["naturaleza"]))
        for nat, r in cfg["reparto"].items():
            with self.subTest(nat):
                self.assertEqual(set(r), {"autor", "revisor"})
                self.assertLessEqual(set(r.values()), set(self.ap.PAGADAS))
                self.assertNotEqual(r["autor"], r["revisor"])

    def test_la_copia_fija_trae_lo_que_la_propuesta_edita(self):
        self.assertEqual(MODELOS_REAL.read_bytes().count(b"\r"), 0)
        self.assertEqual(set(self.cfg), {"niveles", "autorizacion", "naturaleza", "reparto", "factor_modelo"})
        self.assertEqual(set(self.cfg["reparto"]), set(self.cfg["naturaleza"]))
        for nat, r in self.cfg["reparto"].items():
            with self.subTest(nat):
                self.assertEqual(set(r), {"autor", "revisor"})
                self.assertLessEqual(set(r.values()), set(self.ap.PAGADAS))
                self.assertNotEqual(r["autor"], r["revisor"])
        # Lo que hoy esta en los niveles existe en el catalogo: una propuesta puede volver a ponerlo.
        catalogo = self.ap.catalogo_modelos(self.cfg)
        for motor, tabla in self.cfg["niveles"].items():
            for nivel, v in tabla.items():
                with self.subTest(motor=motor, nivel=nivel):
                    self.assertIn(v["modelo"], catalogo[motor])
                    self.assertIn(v["esfuerzo"], ["", *catalogo[motor][v["modelo"]]])
        self.assertEqual(list(catalogo["claude"]), ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"])
        self.assertEqual(catalogo["claude"]["claude-haiku-4-5"], [])       # Haiku no acepta esfuerzo
        self.assertIn("gpt-reserve", catalogo["codex"])                    # oculto en el catalogo, pero se usa

    @unittest.skipUnless(CACHE_CODEX_VIVO.is_file(), "solo en la Pi: el models_cache.json vivo de Codex")
    def test_el_fixture_tiene_la_forma_del_catalogo_vivo_de_codex(self):
        self.ap.CODEX_MODELOS = str(CACHE_CODEX_VIVO)
        real = self.ap.catalogo_modelos(self.cfg)["codex"]
        self.assertTrue(real)
        self.assertTrue(all(real.values()), "un modelo de Codex sin esfuerzos: cambio la forma del catalogo")
        for v in self.cfg["niveles"]["codex"].values():
            self.assertIn(v["modelo"], real)
            self.assertIn(v["esfuerzo"], real[v["modelo"]])

    def test_conserva_la_cabecera_los_comentarios_y_el_registro(self):
        valor = {"naturaleza": {"pagina": {"fix": "normal"}},
                 "niveles": {"codex": {"agil": {"modelo": "gpt-5.6-luna", "esfuerzo": "medium"}},
                             "claude": {"liviano": {"modelo": "claude-haiku-4-5", "esfuerzo": ""}}},   # igual a hoy
                 "reparto": {"bot": {"autor": "codex", "revisor": "claude_diego"}},
                 "autorizacion": {"modelos": [*self.cfg["autorizacion"]["modelos"], "gpt-5.6-sol"]}}
        archivos, efecto, systemd, verificar, resumen = self.ap.armar_plan(
            "no-es-un-perfil", "encargos_config", valor, "probar Luna en lo ágil")
        (a,) = archivos
        self.assertEqual((efecto, systemd, verificar), ("neutro", False, None))
        self.assertIn("encargos_config", self.ap.APLICABLES)
        self.assertIn("encargos_config", self.ap.SIN_REINICIO)
        # Vive solo en el vault: sin copia desplegada no hay deriva que medir ni segundo archivo.
        self.assertIsNone(a.desp)
        self.assertFalse(a.deriva())
        nuevo, antes = a.nuevo, self.original
        self.assertNotIn("\r", nuevo)
        self.assertEqual(nuevo.split("\n[", 1)[0], antes.split("\n[", 1)[0])           # cabecera intacta
        comentarios = lambda t: [l for l in t.split("\n") if l.startswith("#")]
        self.assertEqual(comentarios(nuevo)[:-1], comentarios(antes))                   # ni uno menos, en orden
        registro = antes[antes.index("# Registro de cambios"):]
        self.assertTrue(nuevo.endswith(registro + comentarios(nuevo)[-1] + "\n"))       # el registro, mas una linea
        self.assertRegex(comentarios(nuevo)[-1], r"^# \d\d-\d\d-\d{4} · niveles\.codex\.agil: gpt-reserve medium → "
                         r"gpt-5\.6-luna medium; naturaleza\.pagina\.fix: agil → normal; reparto\.bot\.autor: "
                         r"claude_cami → codex; reparto\.bot\.revisor: codex → claude_diego; candado: \+ gpt-5\.6-sol · "
                         r"probar Luna en lo ágil \(propuesta desde el panel\)$")
        self.assertEqual(resumen.count(";"), 4)
        # Reemplazos puntuales: cambian exactamente las lineas tocadas y se agrega la del registro.
        distintas = [(x, y) for x, y in zip(antes.split("\n"), nuevo.split("\n")) if x != y]
        self.assertEqual(len(distintas), 6)      # 5 lineas editadas y la ultima (vacia → registro)
        self.assertEqual(len(nuevo.split("\n")), len(antes.split("\n")) + 1)
        esperado = json.loads(json.dumps(self.cfg))
        esperado["naturaleza"]["pagina"]["fix"] = "normal"
        esperado["niveles"]["codex"]["agil"] = {"modelo": "gpt-5.6-luna", "esfuerzo": "medium"}
        esperado["reparto"]["bot"] = {"autor": "codex", "revisor": "claude_diego"}
        esperado["autorizacion"]["modelos"].append("gpt-5.6-sol")
        self.assertEqual(self.ap.valores(nuevo), esperado)
        # El comentario de una linea de nivel solo se va si cambia el modelo (describia al anterior).
        self.assertIn('agil    = { modelo = "gpt-5.6-luna",   esfuerzo = "medium" }\n', nuevo)
        self.assertIn("# Haiku no acepta esfuerzo", nuevo)
        self.assertIn('patrones = ["fable", "mythos", "astra"]   # también por trozo del nombre', nuevo)
        # El diff que ve quien aplica es contra el archivo del vault.
        self.assertTrue("".join(a.diff()).startswith(f"--- vault:{self.copia}"))

    # --- Encargo 24: [factor_modelo] ---

    def test_el_factor_se_edita_linea_por_linea_y_queda_en_el_registro(self):
        self.assertEqual(self.cfg["factor_modelo"], {"claude-opus-5-5": 1.0, "claude-sonnet-5-5": 0.61, "claude-haiku-4-5": 0.25})
        (a,), efecto, *_ = self.ap.armar_plan("x", "encargos_config", {"factor_modelo": {"claude-sonnet-5-5": 0.7}}, "medido de nuevo")
        self.assertEqual(efecto, "neutro")
        antes, nuevo = self.original, a.nuevo
        distintas = [(x, y) for x, y in zip(antes.split("\n"), nuevo.split("\n")) if x != y]
        self.assertEqual(len(distintas), 2)      # la linea del factor y la ultima (vacia → registro)
        self.assertEqual(distintas[0], ('"claude-sonnet-5-5" = 0.61', '"claude-sonnet-5-5" = 0.7'))
        self.assertIn('"claude-opus-5-5"   = 1.0     # referencia de Claude\n', nuevo)      # el comentario de otra linea, intacto
        esperado = json.loads(json.dumps(self.cfg))
        esperado["factor_modelo"]["claude-sonnet-5-5"] = 0.7
        self.assertEqual(self.ap.valores(nuevo), esperado)
        ultimo = [l for l in nuevo.split("\n") if l.startswith("#")][-1]
        self.assertRegex(ultimo, r"^# \d\d-\d\d-\d{4} · factor_modelo\.claude-sonnet-5-5: 0\.61 → 0\.7 · medido de nuevo \(propuesta desde el panel\)$")
        # Con el mismo valor no hay nada que proponer.
        self.assertIn("no cambia nada", self.rechazo({"factor_modelo": {"claude-sonnet-5-5": 0.61}}))

    def test_un_modelo_sin_factor_recibe_su_linea_al_final_de_la_tabla_y_los_de_codex_siguen_sin_factor(self):
        self.assertNotIn("gpt-5.6-terra", self.cfg["factor_modelo"])
        (a,), *_ = self.ap.armar_plan("x", "encargos_config", {"factor_modelo": {"gpt-5.6-luna": 0.3}}, "")
        lineas = a.nuevo.split("\n")
        i = lineas.index('"claude-haiku-4-5"  = 0.25')
        self.assertEqual(lineas[i + 1], '"gpt-5.6-luna" = 0.3')
        self.assertEqual(self.ap.valores(a.nuevo)["factor_modelo"]["gpt-5.6-luna"], 0.3)
        self.assertNotIn("gpt-5.6-terra", self.ap.valores(a.nuevo)["factor_modelo"])
        self.assertTrue(a.nuevo.split("\n")[-2].startswith("# "))     # el registro sigue siendo lo ultimo

    def test_rechaza_un_factor_cero_negativo_no_numerico_o_de_un_modelo_que_no_existe(self):
        for k in (0, 0.0, -1, -0.5, True, False, "0.5", None, [1], 100.5, float("nan"), float("inf")):
            with self.subTest(factor=k):
                self.assertIn("el factor tiene que ser un numero mayor que 0", self.rechazo({"factor_modelo": {"claude-sonnet-5-5": k}}))
        self.assertIn("factor_modelo.gpt-7: el modelo no existe", self.rechazo({"factor_modelo": {"gpt-7": 0.5}}))
        self.assertIn("factor_modelo no trae ningun modelo", self.rechazo({"factor_modelo": {}}))
        self.assertIn("tiene que ser un objeto", self.rechazo({"factor_modelo": [0.5]}))
        # Un rechazo es entero: un factor bueno junto a uno malo tampoco se aplica.
        self.rechazo({"factor_modelo": {"claude-haiku-4-5": 0.3, "claude-sonnet-5-5": 0}})

    def test_aplicar_y_revertir_escriben_solo_el_archivo_del_vault(self):
        import pwd
        try:
            pwd.getpwnam(self.ap.DUENO)
        except KeyError:
            self.skipTest("solo en la Pi: escribir el vault usa al dueño real")
        (a,), *_ = self.ap.armar_plan("x", "encargos_config", {"naturaleza": {"menor": {"rev": "normal"}}}, "")
        a.aplicar()
        self.assertEqual(self.copia.read_text(encoding="utf-8"), a.nuevo)
        self.assertEqual(sorted(f.name for f in self.copia.parent.iterdir()), ["modelos.toml"])
        a.revertir()
        self.assertEqual(self.copia.read_text(encoding="utf-8"), self.original)

    def test_aplicar_nunca_deja_ver_el_archivo_vacio_ni_a_medias(self):
        """Hallazgo 1 de 23ar1: cola-run.py relee modelos.toml antes de cada fase. Se pausa la
        escritura en cada llamada del sistema que publica o toca el archivo y se lee EL MISMO
        archivo que lee la cola: siempre debe ser el viejo completo o el nuevo completo."""
        import pwd
        from unittest import mock
        try:
            pwd.getpwnam(self.ap.DUENO)
        except KeyError:
            self.skipTest("solo en la Pi: escribir el vault usa al dueño real")
        (a,), *_ = self.ap.armar_plan("x", "encargos_config", {"naturaleza": {"menor": {"rev": "normal"}}}, "")
        self.assertNotEqual(a.nuevo, self.original)
        vistas = []

        def mirar(etiqueta):
            vistas.append((etiqueta, self.copia.read_text(encoding="utf-8")))

        real_replace, real_fsync, real_trunc = os.replace, os.fsync, os.ftruncate
        def replace(*x, **k):
            mirar("antes del rename")
            r = real_replace(*x, **k)
            mirar("despues del rename")
            return r
        def fsync(fd):
            mirar("antes del fsync")
            return real_fsync(fd)
        def trunc(fd, n):
            mirar("truncate")
            return real_trunc(fd, n)
        with mock.patch.object(os, "replace", replace), mock.patch.object(os, "fsync", fsync), \
                mock.patch.object(os, "ftruncate", trunc):
            a.aplicar()
        self.assertEqual([e for e, _ in vistas], ["antes del fsync", "antes del rename", "despues del rename"])
        self.assertEqual([t == self.original for _, t in vistas], [True, True, False])
        self.assertEqual(vistas[-1][1], a.nuevo)
        # Mientras se escribia, lo que ve la cola es una configuracion completa y usable.
        for _, t in vistas:
            self.assertEqual(set(self.ap.valores(t)), {"niveles", "autorizacion", "naturaleza", "reparto", "factor_modelo"})
        self.assertEqual(sorted(f.name for f in self.copia.parent.iterdir()), ["modelos.toml"])   # sin restos
        # Y lo mismo al revertir. Dueño y modo del archivo se conservan.
        modo = self.copia.stat().st_mode
        vistas.clear()
        with mock.patch.object(os, "replace", replace), mock.patch.object(os, "fsync", fsync):
            a.revertir()
        self.assertEqual([t == a.nuevo for _, t in vistas], [True, True, False])
        self.assertEqual(self.copia.read_text(encoding="utf-8"), self.original)
        self.assertEqual(self.copia.stat().st_mode, modo)

    def test_si_la_escritura_atomica_falla_queda_el_archivo_viejo_y_sin_restos(self):
        import pwd
        from unittest import mock
        try:
            pwd.getpwnam(self.ap.DUENO)
        except KeyError:
            self.skipTest("solo en la Pi: escribir el vault usa al dueño real")
        (a,), *_ = self.ap.armar_plan("x", "encargos_config", {"naturaleza": {"menor": {"rev": "normal"}}}, "")
        with mock.patch.object(os, "replace", side_effect=OSError("disco lleno")), self.assertRaises(OSError):
            a.aplicar()
        self.assertEqual(self.copia.read_text(encoding="utf-8"), self.original)
        self.assertEqual(sorted(f.name for f in self.copia.parent.iterdir()), ["modelos.toml"])

    def test_rechaza_un_modelo_que_no_existe(self):
        for motor, modelo in (("claude", "claude-opus-9"), ("codex", "gpt-7-inventado"), ("codex", "claude-opus-5-5"),
                              ("claude", "gpt-5.6-terra")):
            with self.subTest(modelo=modelo):
                error = self.rechazo({"niveles": {motor: {"normal": {"modelo": modelo, "esfuerzo": "medium"}}}})
                self.assertIn(f"niveles.{motor}.normal: el modelo '{modelo}' no existe", error)
        # Tampoco un esfuerzo que ese modelo no acepta, ni un nivel, motor o campo inventado.
        for valor, motivo in (
                ({"niveles": {"claude": {"liviano": {"modelo": "claude-haiku-4-5", "esfuerzo": "high"}}}}, "no acepta el esfuerzo 'high'"),
                ({"niveles": {"codex": {"normal": {"modelo": "gpt-5.5", "esfuerzo": "max"}}}}, "no acepta el esfuerzo 'max'"),
                ({"niveles": {"codex": {"turbo": {"modelo": "gpt-5.5", "esfuerzo": "low"}}}}, "ese nivel no existe"),
                ({"niveles": {"gemini": {"normal": {"modelo": "gpt-5.5", "esfuerzo": "low"}}}}, "motor desconocido"),
                ({"niveles": {"codex": {"normal": {"modelo": "gpt-5.5"}}}}, "espera {modelo, esfuerzo}"),
                ({"niveles": {"codex": {"normal": {"modelo": "gpt-5.5", "esfuerzo": "low", "extra": "x"}}}}, "espera {modelo, esfuerzo}"),
                ({"naturaleza": {"pagina": {"fix": "turbo"}}}, "el nivel 'turbo' no existe"),
                ({"naturaleza": {"pagina": {"revisor": "normal"}}}, "el rol tiene que ser autor, rev, fix"),
                ({"naturaleza": {"nueva": {"fix": "normal"}}}, "naturaleza.nueva: no existe"),
                ({"modelos": {}}, "encargos_config espera"),
                (["naturaleza"], "encargos_config espera")):
            with self.subTest(valor=valor):
                self.assertIn(motivo, self.rechazo(valor))
        # Una propuesta con una parte buena y una mala se rechaza ENTERA.
        self.assertIn("no existe", self.rechazo({"naturaleza": {"pagina": {"fix": "normal"}},
                                                 "niveles": {"codex": {"agil": {"modelo": "gpt-7", "esfuerzo": ""}}}}))

    def test_sin_el_catalogo_de_codex_no_se_cambia_ningun_modelo_suyo(self):
        ap, _ = aplicar_encargos(self, cache=PI / "fixtures" / "encargos" / "no-existe.json")
        self.assertIsNone(ap.catalogo_modelos(self.cfg)["codex"])
        with self.assertRaises(SystemExit):
            ap.plan_encargos({"niveles": {"codex": {"agil": {"modelo": "gpt-5.6-luna", "esfuerzo": "low"}}}})
        # Lo demas sigue pudiendo proponerse.
        archivos, *_ = ap.plan_encargos({"naturaleza": {"pagina": {"fix": "normal"}}})
        self.assertEqual(ap.valores(archivos[0].nuevo)["naturaleza"]["pagina"]["fix"], "normal")

    def test_rechaza_quitar_un_candado(self):
        actuales = self.cfg["autorizacion"]["modelos"]
        self.assertEqual(actuales, ["claude-fable-5-1", "gpt-6-astra"])
        for lista in ([], ["gpt-6-astra"], ["claude-fable-5-1"], ["claude-fable-5-1", "gpt-5.6-sol"]):
            with self.subTest(lista=lista):
                self.assertIn("Quitar un candado no se hace desde la pagina",
                              self.rechazo({"autorizacion": {"modelos": lista}}))
        # Ni tocar los patrones o la espera, ni colar algo que no sea un nombre de modelo.
        for aut, motivo in (({"modelos": actuales, "patrones": []}, "solo se agregan modelos"),
                            ({"patrones": ["fable"]}, "solo se agregan modelos"),
                            ({"modelos": actuales, "espera_max_min": 1}, "solo se agregan modelos"),
                            ({"modelos": [*actuales, 'x"]\nespera_max_min = 0\n#']}, "sin repetir"),
                            ({"modelos": [*actuales, "gpt-5.5", "gpt-5.5"]}, "sin repetir"),
                            ({"modelos": "claude-fable-5-1"}, "sin repetir")):
            with self.subTest(aut=aut):
                self.assertIn(motivo, self.rechazo({"autorizacion": aut}))
        # Agregar si: restringe, y la lista conserva los de antes en su orden.
        archivos, efecto, *_ = self.ap.plan_encargos({"autorizacion": {"modelos": ["gpt-5.6-sol", *reversed(actuales)]}})
        self.assertEqual(efecto, "restringe")
        self.assertEqual(self.ap.valores(archivos[0].nuevo)["autorizacion"],
                         dict(self.cfg["autorizacion"], modelos=[*actuales, "gpt-5.6-sol"]))

    def test_rechaza_autor_igual_a_revisor(self):
        self.assertEqual(self.cfg["reparto"]["bot"], {"autor": "claude_cami", "revisor": "codex"})
        for r in ({"autor": "codex", "revisor": "codex"}, {"autor": "codex"}, {"revisor": "claude_cami"}):
            with self.subTest(r=r):
                self.assertIn("reparto.bot: autor y revisor serian la misma cuenta", self.rechazo({"reparto": {"bot": r}}))
        for r, motivo in (({"autor": "groq"}, "no es una cuenta"), ({"autor": "Codex"}, "no es una cuenta"),
                          ({"escritor": "codex"}, "espera {autor, revisor}"), ({}, "espera {autor, revisor}")):
            with self.subTest(r=r):
                self.assertIn(motivo, self.rechazo({"reparto": {"bot": r}}))
        self.assertIn("esa naturaleza no existe", self.rechazo({"reparto": {"nueva": {"autor": "codex", "revisor": "claude_cami"}}}))
        # Intercambiarlos en una sola propuesta si se puede.
        archivos, *_ = self.ap.plan_encargos({"reparto": {"bot": {"autor": "codex", "revisor": "claude_cami"}}})
        self.assertEqual(self.ap.valores(archivos[0].nuevo)["reparto"]["bot"], {"autor": "codex", "revisor": "claude_cami"})

    def test_una_propuesta_vacia_no_cambia_nada(self):
        igual = {"naturaleza": self.cfg["naturaleza"], "niveles": self.cfg["niveles"], "reparto": self.cfg["reparto"],
                 "autorizacion": {"modelos": self.cfg["autorizacion"]["modelos"]}}
        for valor in ({}, {"naturaleza": {}, "niveles": {}, "reparto": {}}, igual):
            with self.subTest(valor=valor):
                self.assertIn("no cambia nada", self.rechazo(valor))
        # Y el editor, sin cambios, devuelve el archivo byte por byte.
        nuevo, cambios, avisos = self.ap.cambios_encargos(self.cfg, igual, self.ap.catalogo_modelos(self.cfg))
        self.assertEqual((nuevo, cambios), (self.cfg, []))
        self.assertEqual(self.ap.texto_encargos(self.original, self.cfg, nuevo, ""), self.original)

    def test_el_motivo_no_puede_escribir_toml(self):
        valor = {"naturaleza": {"pagina": {"fix": "normal"}}}
        for motivo in ('x\n[autorizacion]\nmodelos = []', "a\rb", "m" * 201):
            with self.subTest(motivo=motivo[:12]):
                self.assertIn("el motivo tiene que ser una sola linea", self.rechazo(valor, motivo))
        archivos, *_ = self.ap.plan_encargos(valor, 7)      # un motivo que no es texto se ignora
        self.assertIn("· sin motivo escrito (propuesta desde el panel)\n", archivos[0].nuevo)

    def test_avisa_si_un_nivel_queda_en_un_modelo_con_candado_o_la_revision_bajo_el_autor(self):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.ap.plan_encargos({"niveles": {"claude": {"maximo": {"modelo": "claude-fable-5-1", "esfuerzo": "high"}}},
                                   "naturaleza": {"menor": {"autor": "normal", "rev": "liviano"}}})
        self.assertIn("🔒 niveles.claude.maximo pasa a claude-fable-5-1, que tiene candado", salida.getvalue())
        self.assertIn("naturaleza.menor: la revision (liviano) queda por debajo del autor (normal)", salida.getvalue())
        # Poner candado a un modelo que hoy esta en un nivel tambien se dice.
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.ap.plan_encargos({"autorizacion": {"modelos": [*self.cfg["autorizacion"]["modelos"], "gpt-reserve"]}})
        self.assertIn("🔒 niveles.codex.agil usa gpt-reserve: con el candado nuevo", salida.getvalue())
        # Y una propuesta que no toca nada de eso no avisa nada (hoy `diseno` ya revisa bajo el autor).
        self.assertEqual(self.ap.cambios_encargos(self.cfg, {"naturaleza": self.cfg["naturaleza"], "niveles": self.cfg["niveles"]},
                                                  self.ap.catalogo_modelos(self.cfg))[1:], ([], []))


if __name__ == "__main__":
    unittest.main()
