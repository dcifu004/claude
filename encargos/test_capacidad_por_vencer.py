#!/usr/bin/env python3
"""Pruebas aisladas de 50b: topes de encargos, quemar cuota y capacidad por vencer.

    python3 encargos/test_capacidad_por_vencer.py

No lee ni escribe el registro real ni /opt/nodo/datos: cada módulo apunta a una copia temporal.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
COLA = RAIZ / "encargos" / "cola-run.py"
APLICAR = RAIZ / "pi" / "aplicar-propuesta.py"
RECETAS = RAIZ / "botv3" / "recetas.py"
FIX = RAIZ / "encargos" / "46-fixtures"
CUENTAS = """# copia de prueba: no es botv3/cuentas.toml
[claude_diego]
nombre = "Claude (Diego)"
motor = "claude"
precio_mes_usd = 20
renueva = ""
umbral_semanal = 90
umbral_5h = 90

[claude_cami]
nombre = "Claude (Cami)"
motor = "claude"
precio_mes_usd = 20
renueva = ""
umbral_semanal = 90
umbral_5h = 90

[codex]
nombre = "Codex"
motor = "codex"
precio_mes_usd = 20
renueva = ""
umbral_semanal = 90
umbral_5h = 90
"""


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="capacidad-50b-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.registro = self.tmp / "cuentas.toml"
        self.registro.write_text(CUENTAS, encoding="utf-8")
        self.cola = cargar(f"cola_50b_{id(self)}", COLA)
        self.cola.REGISTROS = (self.registro,)
        self.cola.HISTORIAL = FIX / "historial.jsonl"
        self.ahora = datetime(2026, 10, 11, 19, 42, tzinfo=timezone(timedelta(hours=-3)))
        self.cola.ahora = lambda: self.ahora

    def escribir(self, extra, cid="claude_diego"):
        bloque = f'[{cid}]\nnombre = "{self.cola.nombre(cid)}"\nmotor = "{self.cola.MOTORES[cid]["motor"]}"\nprecio_mes_usd = 20\nrenueva = ""\numbral_semanal = 90\numbral_5h = 90'
        self.registro.write_text(CUENTAS.replace(bloque, bloque + "\n" + extra), encoding="utf-8")

    def uso_real(self, cid, momento=None, limites=None):
        """Llama uso() sobre la forma real que emite uso.py, nunca sobre un diccionario adaptado."""
        ruta = FIX / "uso-limites.json"
        if limites is not None:
            ruta = self.tmp / "uso.json"
            ruta.write_text(json.dumps({"cuentas_interactivo": {cid: {"limites": limites}}}), encoding="utf-8")
        return self.cola.uso(cid, ruta, momento or self.ahora)


class C1Compatibilidad(Base):
    def test_sin_campos_nuevos_conserva_los_topes_y_la_pausa(self):
        u = {"sem": 80.0, "5h": 70.0, "renueva_sem": self.ahora + timedelta(days=2),
             "renueva_5h": self.ahora + timedelta(hours=2), "fuente": "fixture"}
        self.assertEqual(self.cola.topes("claude_cami", u), (90, 90))
        self.assertEqual(self.cola.ventanas_cuota("claude_cami", {"pct_sem": 11, "pct_5h": 19}, u), [
            {"ventana": "semanal", "etiqueta": "semanal", "actual": 80.0, "pronostico": 11, "tope": 90,
             "renueva": u["renueva_sem"]},
            {"ventana": "5h", "etiqueta": "5 h", "actual": 70.0, "pronostico": 19, "tope": 90,
             "renueva": u["renueva_5h"]},
        ])


class C2SeparacionDelBot(Base):
    def test_la_cola_usa_su_tope_y_recetas_el_umbral_del_bot(self):
        self.escribir("tope_encargos_semanal = 95")
        self.assertEqual(self.cola.topes("claude_diego"), (95, 90))
        recetas = cargar(f"recetas_50b_{id(self)}", RECETAS)
        umbral = recetas.umbrales_de({"claude_diego": {"umbral_semanal": 90, "tope_encargos_semanal": 95}},
                                     ["claude_diego"])
        self.assertEqual(umbral["claude_diego"]["semanal"], 90)


class C3Quemar(Base):
    def test_solo_las_ultimas_horas_y_nunca_despues_de_renovar(self):
        self.escribir("quemar_horas = 6\nquemar_tope = 98", "claude_cami")
        # La API de Claude entrega estas renovaciones en UTC. uso() las normaliza y el texto sale local.
        limites = {"ventana_5h": {"usado_pct": 53, "renueva": "2026-10-12T00:50:00+00:00"},
                   "semanal": {"usado_pct": 81, "renueva": "2026-10-12T01:00:00+00:00"}}
        renueva = datetime.fromisoformat("2026-10-12T01:00:00+00:00")
        u = self.uso_real("claude_cami", limites=limites)
        self.ahora = renueva - timedelta(hours=5)
        self.assertEqual(self.cola.topes("claude_cami", u), (98, 90))
        ventana = self.cola.ventanas_cuota("claude_cami", {"pct_sem": 1, "pct_5h": 1}, u, self.ahora)[0]
        self.assertTrue(ventana["quemando"])
        hasta = renueva.astimezone().strftime("%H:%M")
        self.assertIn(f"quemando hasta {hasta}", self.cola._texto_ventana(ventana))
        self.assertIn(f"quemando hasta {hasta}", self.cola._texto_calculo(ventana))
        self.ahora = renueva - timedelta(hours=7)
        self.assertEqual(self.cola.topes("claude_cami", u), (90, 90))
        self.ahora = renueva + timedelta(minutes=1)
        self.assertEqual(self.cola.topes("claude_cami", u), (90, 90))
        u["renueva_sem"] = None
        self.assertTrue(self.cola.quema("claude_cami", u)["debil"])


class C4Capacidad(Base):
    def test_foto_del_11_10_respeta_las_ventanas_de_cinco_horas(self):
        # Foto registrada el 11-10 19:42, con exactamente la forma de uso.json de Claude (UTC).
        self.escribir("tope_encargos_semanal = 90\ntope_encargos_5h = 90", "claude_cami")
        limites = {"ventana_5h": {"usado_pct": 53, "renueva": "2026-10-12T00:50:00+00:00"},
                   "semanal": {"usado_pct": 81, "renueva": "2026-10-12T01:00:00+00:00"}}
        u = self.uso_real("claude_cami", limites=limites)
        r = self.cola.capacidad_por_vencer("claude_cami", u, self.ahora)
        # 37 puntos de la ventana abierta + 3 del último tramo: la razón real congelada es 0,121.
        self.assertAlmostEqual(self.cola._razon_sem_por_5h("claude_cami"), 0.121, delta=0.002)
        self.assertAlmostEqual(r["por_ventanas"], 4.8, delta=0.2)
        self.assertAlmostEqual(r["capacidad"], 4.8, delta=1.5)
        self.assertFalse(r["debil"])

    def test_sin_ventana_abierta_usa_una_ventana_limpia_desde_ahora(self):
        limites = {"ventana_5h": {"usado_pct": 0, "renueva": None},
                   "semanal": {"usado_pct": 60, "renueva": "2026-10-12T00:42:00+00:00"}}
        u = self.uso_real("claude_cami", limites=limites)
        r = self.cola.capacidad_por_vencer("claude_cami", u, self.ahora)
        self.assertIsNone(u["renueva_5h"])
        self.assertIsNotNone(r["capacidad"])
        self.assertGreater(r["capacidad"], 0)


class C6PanelYColasQueCaben(Base):
    def _panel_fixture(self, extra, activa_cami=False):
        self.escribir(extra, "claude_cami")
        vivos = self.tmp / "vivo"
        vivos.mkdir(exist_ok=True)
        for nombre in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola46.json"):
            v = json.loads((FIX / nombre).read_text(encoding="utf-8"))
            if activa_cami and v["nombre"] == "cola43r":
                v.update(estado="esperando_cuota", etapa="43", fase="autor",
                         reanuda=(self.ahora + timedelta(hours=1)).isoformat(), espera_desde=self.ahora.isoformat())
            (vivos / f"{v['nombre']}.json").write_text(json.dumps(v), encoding="utf-8")
        self.cola.E = self.cola.D = self.cola.L = self.tmp
        self.cola.MODELOS = FIX / "modelos.toml"
        self.cola.SIMULANDO = True
        ap = cargar(f"aplicar_50b_panel_{id(self)}", APLICAR)
        ap.CODEX_MODELOS = str(RAIZ / "pi" / "fixtures" / "encargos" / "models_cache.json")
        self.cola._AP_MOD = ap
        return self.cola.panel(vivos_dir=vivos, uso_de=lambda cid: self.cola.uso(cid, FIX / "uso-limites.json", self.ahora),
                               momento=self.ahora, viva=lambda nom: activa_cami and nom == "cola43r", timers=[],
                               manifiestos_dir=FIX / "manifiestos")

    def test_panel_es_json_con_quema_activa_y_regla_debil(self):
        for extra in ("quemar_horas = 6\nquemar_tope = 98", "quemar_horas = 6"):
            with self.subTest(extra=extra):
                panel = self._panel_fixture(extra, activa_cami=True)
                texto = json.dumps(panel, ensure_ascii=False)
                regla = next(r for r in panel["reglas"] if r["cuenta"] == "claude_cami")
                semanal = next(w for w in regla["ventanas"] if w["ventana"] == "semanal")
                self.assertIsInstance(semanal.get("quemar_hasta"), str)
                self.assertIn("quemar_hasta", texto)

    def test_fixture_real_publica_una_cola_que_cabe_y_otra_que_no(self):
        matriz = self._panel_fixture("tope_encargos_semanal = 84")
        caben = matriz["capacidad_por_vencer"]["claude_cami"]["colas_que_caben"]
        self.assertIn("cola41", caben)
        self.assertNotIn("cola43r", caben)


class C5AplicarPropuesta(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="propuesta-50b-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.registro = self.tmp / "cuentas.toml"
        self.registro.write_text(CUENTAS, encoding="utf-8")
        self.ap = cargar(f"aplicar_50b_{id(self)}", APLICAR)
        self.ap.REGISTRO_V = self.ap.REGISTRO_D = str(self.registro)

    def rechaza(self, valor):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.ap.plan_registro({"claude_cami": valor})

    def test_valida_los_cuatro_campos_en_una_copia_temporal(self):
        archivo, *_ = self.ap.plan_registro({"claude_cami": {"tope_encargos_semanal": 95,
                                                              "tope_encargos_5h": 91,
                                                              "quemar_horas": 6, "quemar_tope": 98}})
        r = self.ap.valores(archivo[0].nuevo)["claude_cami"]
        self.assertEqual((r["tope_encargos_semanal"], r["tope_encargos_5h"], r["quemar_horas"], r["quemar_tope"]),
                         (95, 91, 6, 98))
        for malo in ({"tope_encargos_semanal": 101}, {"tope_encargos_5h": "90"},
                     {"quemar_horas": 49}, {"quemar_tope": True}, {"desconocido": 1}):
            with self.subTest(malo=malo):
                self.rechaza(malo)

    def test_puede_quitar_las_llaves_y_rechaza_combinaciones_rotas(self):
        def aplicar(valor):
            archivo, *_ = self.ap.plan_registro({"claude_cami": valor})
            self.registro.write_text(archivo[0].nuevo, encoding="utf-8")
        aplicar({"tope_encargos_semanal": 95, "tope_encargos_5h": 91, "quemar_horas": 6, "quemar_tope": 98})
        aplicar({"tope_encargos_semanal": None, "tope_encargos_5h": None, "quemar_horas": None, "quemar_tope": None})
        r = self.ap.valores(self.registro.read_text(encoding="utf-8"))["claude_cami"]
        self.assertFalse({"tope_encargos_semanal", "tope_encargos_5h", "quemar_horas", "quemar_tope"} & set(r))
        for malo in ({"quemar_horas": 6}, {"quemar_tope": 50, "tope_encargos_semanal": 90},
                     {"tope_encargos_semanal": 80, "aviso_semanal": 85}):
            with self.subTest(malo=malo):
                self.rechaza(malo)


class C6Pagina(unittest.TestCase):
    def test_los_cuatro_campos_se_proponen_y_el_panel_sanitiza_los_textos(self):
        cuentas = (RAIZ / "pi" / "cockpit-cuentas" / "cuentas.js").read_text(encoding="utf-8")
        encargos = (RAIZ / "pi" / "cockpit-encargos" / "encargos.js").read_text(encoding="utf-8")
        for campo in ("tope_encargos_semanal", "tope_encargos_5h", "quemar_horas", "quemar_tope"):
            self.assertIn(campo, cuentas)
        self.assertIn("Capacidad por vencer:", encargos)
        self.assertIn("x.colas_que_caben.map(delPanel)", encargos)
        self.assertIn("delPanel(x.nombre)", encargos)


if __name__ == "__main__":
    unittest.main()
