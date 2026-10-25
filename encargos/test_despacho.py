#!/usr/bin/env python3
"""Pruebas del encargo 50a: `balance.py --json`, la mirada de pasado en `--panel`, el estado del despacho
(`vivo/despacho.json`, `cola-run.py --despacho`), la retención al arrancar y los botones de 🧵 Encargos.

    python3 encargos/test_despacho.py

Usa el andamio de la 46c (`test_acciones_cola.Base` y su espejo de la página, `Pagina`): todo corre sobre una
carpeta temporal y `46-fixtures/`, con la carpeta de los vivos inyectada (ahí van `despacho.json` y
`acciones.jsonl`), un tmux y un lanzador de mentira, y los avisos en una lista. Donde hace falta una cola
arrancando corre el `principal()` real con un motor de mentira. Ninguna prueba lanza una cola, toca
/opt/nodo/datos ni el `vivo/` real, ni avisa: al terminar se comprueba que el `vivo/` real quedó igual.
La única lectura fuera del temporal es `encargos/historial.jsonl` (C1 pide el historial real): solo se lee.
En la Pi no hay motor de JavaScript: la parte de la página es un espejo en Python, atado al JS por su texto.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import stat
import sys
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ENCARGOS = Path(__file__).resolve().parent
PI = ENCARGOS.parent / "pi"
sys.path[:0] = [str(ENCARGOS), str(PI)]
import test_acciones_cola as ta  # noqa: E402  (Base, el espejo de la página y las fixtures de la 46)
import test_matriz_cuota as mc  # noqa: E402

FIX, T, COLA_RUN, HOSTILES = ta.FIX, ta.T, ta.COLA_RUN, ta.HOSTILES
HISTORIAL_REAL = ENCARGOS / "historial.jsonl"
FASES_46 = ["46a-autor", "46a-rev1", "46b-autor", "46b-rev1", "46c-autor", "46c-rev1"]
AVISO_ROTO = "despacho.json no se pudo leer (el JSON está a medias o roto): el despacho se trata como abierto"
_REAL: dict = {}


def _despacho_real():
    """(tamaño, fecha) del despacho.json y del registro de verdad, o None: la suite no los puede cambiar."""
    out = {}
    for nombre in ("despacho.json", "acciones.jsonl"):
        try:
            st = (ENCARGOS / "vivo" / nombre).lstat()
            out[nombre] = (st.st_size, st.st_mtime_ns)
        except OSError:
            out[nombre] = None
    return out


def setUpModule():
    ta.setUpModule()
    _REAL.update(_despacho_real())


def tearDownModule():
    ta.tearDownModule()
    if _despacho_real() != _REAL:
        raise AssertionError("la suite cambió el despacho.json o el registro del vivo/ real")


def cargar_balance():
    return mc.cargar(ENCARGOS / "balance.py")


class Base(ta.Base):
    def despacho(self) -> dict:
        return json.loads((self.vivos / "despacho.json").read_text(encoding="utf-8"))

    def cambiar(self, orden, motivo=None, autorizar=(), por=None) -> dict:
        return self.cr.cambiar_despacho(orden, motivo, autorizar, por, vivos_dir=self.vivos, momento=self.reloj)

    def panel(self, **extra) -> dict:
        self.cr.SIMULANDO = True
        try:
            return self.cr.panel(**(dict(vivos_dir=self.vivos, uso_de=self.uso_de, momento=self.reloj, viva=lambda n: n in self.sesiones,
                                         manifiestos_dir=self.tmp, timers=[]) | extra))
        finally:
            self.cr.SIMULANDO = False

    def nada_corre(self):
        """Lo que una cola retenida no puede alcanzar a hacer: ni la línea base, ni esperar a otra, ni una fase."""
        for nombre in ("pruebas", "esperar_sesion", "foto", "git_foto", "chequear_cuota", "desplegar"):
            setattr(self.cr, nombre, lambda *a, _n=nombre, **k: self.fail(f"una cola retenida no llega a {_n}()"))


# ---------------------------------------------------------------- C1

class C1Pasado(Base):
    """`balance.py --json` da los mismos números que su salida de texto, y `--panel` los publica en `pasado`."""

    def salidas(self, historial: Path, manifiestos: Path, *extra) -> tuple[str, dict]:
        bal = cargar_balance()
        out = []
        for forma in ([], ["--json"]):
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                self.assertEqual(bal.principal(["--historial", str(historial), "--manifiestos", str(manifiestos), *extra, *forma]), 0)
            out.append(salida.getvalue())
        self.assertEqual(out[1].count("\n"), 1)                 # el JSON va en una línea
        return out[0].rstrip("\n"), json.loads(out[1])

    @staticmethod
    def pct(x):
        return "–" if x is None else f"{x} %"

    @staticmethod
    def dec(x, d):
        return f"{x:.{d}f}".replace(".", ",")

    def linea_familia(self, f: dict) -> str:
        return (f"{f['nombre']}: {f['encargos']} enc · 1ª {f['aprobados']}/{f['revisados']} · ret min {self.pct(f['ret_min_pct'])}"
                f" · tok C {self.pct(f['ret_usd_pct'])} X {self.pct(f['ret_tok_pct'])} · USD {self.dec(f['usd_por_encargo'], 2)}"
                f" · {f['tok_k_por_encargo']} k · err {self.pct(f['error_pct'])}")

    def linea_combo(self, c: dict) -> str:
        return (f"{c['motor']} {c['modelo']} {c['esfuerzo']} {c['rol']}: n {c['fases']} · {self.dec(c['min_por_fase'], 1)} min"
                + (f" · USD {self.dec(c['usd_por_fase'], 2)}" if c["usd_por_fase"] is not None else "")
                + (f" · {c['tok_k_por_fase']} k" if c["tok_k_por_fase"] is not None else ""))

    def comparar(self, texto: str, d: dict):
        """Cada línea del texto sale, letra por letra, de los datos; y no sobra ninguna familia en ninguno de los dos."""
        lineas = texto.split("\n")
        self.assertEqual(lineas[0], f"Balance de encargos {d['primero']}–{d['ultimo']}: {d['encargos']} encargos, {d['total']['fases']} fases")
        t = d["total"]
        self.assertIn(self.linea_familia(t) + f" · {t['min_ret']} de {t['min']} min en retrabajo", lineas)

        def seccion(titulo):
            i = lineas.index(titulo) + 1
            j = next((k for k in range(i, len(lineas)) if not lineas[k]), len(lineas))
            return lineas[i:j]
        for titulo, clave in (("POR NATURALEZA", "naturaleza"), ("POR AFINADO", "afinado"), ("POR EXPERIMENTO", "experimento")):
            self.assertEqual(seccion(titulo), [self.linea_familia(f) for f in d[clave]], titulo)
        del_texto = seccion("POR MOTOR, MODELO, ESFUERZO Y ROL (por fase)")
        de_datos = [self.linea_combo(c) for c in d["combos"]]
        if del_texto and del_texto[-1].startswith("… y "):          # el texto recorta para caber en un mensaje; los datos no
            self.assertEqual(del_texto[-1], f"… y {len(de_datos) - len(del_texto) + 1} combinaciones más, de menos minutos")
            del_texto = del_texto[:-1]
        self.assertEqual(del_texto, de_datos[:len(del_texto)])
        self.assertEqual(seccion("LOS 5 MÁS CAROS (por minutos)"),
                         [f"{e['id']}: {e['min']} min · USD {self.dec(e['usd'], 2)} · {e['tok_k']} k · {e['revisiones']} rev" for e in d["caros"]])
        self.assertEqual(sum(f["encargos"] for f in d["naturaleza"]), d["encargos"])
        notas = next((x for x in lineas if x.startswith("Notas: ")), "")
        self.assertEqual(bool(d["saltadas"]), "del historial saltada" in notas)
        self.assertEqual(bool(d["sin_manifiesto"]), "sin manifiesto: " in notas)
        for ident in d["sin_manifiesto"][:8]:
            self.assertIn(ident, notas)

    def test_con_las_fixtures_el_json_trae_los_numeros_del_texto(self):
        texto, d = self.salidas(FIX / "historial.jsonl", FIX / "manifiestos")
        self.comparar(texto, d)
        self.assertGreater(d["encargos"], 5)
        self.assertEqual(set(d), {"desde", "encargos", "primero", "ultimo", "total", "naturaleza", "combos", "afinado", "experimento",
                                  "caros", "saltadas", "sin_manifiesto", "ilegibles"})
        self.assertEqual(set(d["total"]), {"nombre", "encargos", "fases", "aprobados", "revisados", "min", "min_ret", "ret_min_pct", "ret_usd_pct",
                                           "ret_tok_pct", "usd_por_encargo", "tok_k_por_encargo", "error_pct"})
        self.assertEqual(set(d["combos"][0]), {"motor", "modelo", "esfuerzo", "rol", "fases", "min_por_fase", "usd_por_fase", "tok_k_por_fase"})

    def test_con_desde_y_con_un_historial_sin_filas(self):
        texto, d = self.salidas(FIX / "historial.jsonl", FIX / "manifiestos", "--desde", "40")
        self.comparar(texto, d)
        self.assertEqual(d["desde"], 40)
        self.assertGreaterEqual(int(re.match(r"\d+", d["primero"]).group()), 40)
        vacio = self.tmp / "vacio.jsonl"
        vacio.write_text('{"roto\n', encoding="utf-8")
        texto, d = self.salidas(vacio, self.tmp)
        self.assertEqual(texto, "Balance de encargos: no hay fases que contar (1 líneas del historial saltadas).")
        self.assertEqual((d["encargos"], d["total"], d["naturaleza"], d["combos"], d["saltadas"]), (0, None, [], [], 1))

    def test_con_el_experimento_y_el_afinado_de_un_manifiesto(self):
        # Un manifiesto con `experimento = "esfuerzo-v1"`: la familia sale con su conteo de casos.
        man = self.tmp / "manifiestos"
        man.mkdir()
        (man / "cola-41.toml").write_text('nombre = "cola41"\nafinado = "ligero"\nexperimento = "esfuerzo-v1"\n\n[[etapa]]\nid = "41"\nnaturaleza = "bot"\n',
                                           encoding="utf-8")
        texto, d = self.salidas(FIX / "historial.jsonl", man)
        self.comparar(texto, d)
        caso = next(f for f in d["experimento"] if f["nombre"] == "esfuerzo-v1")
        self.assertEqual((caso["encargos"], d["experimento"][0]["nombre"]), (1, "esfuerzo-v1"))
        self.assertEqual([f["nombre"] for f in d["afinado"]], ["ligero", "sin dato"])

    @unittest.skipUnless(HISTORIAL_REAL.is_file(), "no está el historial real")
    def test_con_el_historial_real_el_json_trae_los_numeros_del_texto(self):
        # Solo lee, y sobre una copia: una cola viva puede agregar una fila entre la salida de texto y la de datos.
        foto = self.tmp / "historial-real.jsonl"
        foto.write_bytes(HISTORIAL_REAL.read_bytes())
        texto, d = self.salidas(foto, ENCARGOS)
        self.comparar(texto, d)
        t = d["total"]
        self.assertIn(f"1ª {t['aprobados']}/{t['revisados']} · ret min {t['ret_min_pct']} %", texto)
        self.assertGreaterEqual((t["aprobados"], t["revisados"]), (13, 36))         # el 11-10 eran 13/36; el historial solo crece

    def test_el_panel_publica_en_pasado_lo_mismo_que_balance_json(self):
        _, d = self.salidas(FIX / "historial.jsonl", self.tmp)        # el historial y los manifiestos que ve el panel de la prueba
        self.manifiesto("cola-41.toml")
        _, con_manifiesto = self.salidas(FIX / "historial.jsonl", self.tmp)
        self.cr.HISTORIAL = FIX / "historial.jsonl"
        self.assertEqual(self.panel()["pasado"], con_manifiesto)
        self.assertNotEqual(con_manifiesto["sin_manifiesto"], d["sin_manifiesto"])
        fuente = COLA_RUN.read_text(encoding="utf-8")
        cuerpo = fuente[fuente.index("def pasado("):fuente.index("def modelos_con_candado(")]
        for llamada in ("bal.leer_historial(HISTORIAL)", "bal.leer_manifiestos(manifiestos_dir or E)", "bal.datos(filas, etapas, saltadas, ilegibles)"):
            self.assertIn(llamada, cuerpo)                             # expone las funciones de balance.py: acá no hay ninguna cuenta
        self.assertIsNone(re.search(r"[-+*/%]\s*\d|round\(|sum\(", cuerpo))

    def test_sin_historial_el_panel_sale_igual_con_pasado_nulo(self):
        self.cr.HISTORIAL = self.tmp / "no-existe.jsonl"
        panel = self.panel()
        self.assertIsNone(panel["pasado"])
        self.assertEqual(panel["despacho"], {"estado": "abierto", "desde": None, "motivo": "", "autorizadas": [], "por": "", "aviso": ""})


# ---------------------------------------------------------------- C2

class C2Retenida(Base):
    """Con el despacho en pausa, una cola no autorizada que arranca (o un `--desde`) no corre ninguna fase."""

    def test_una_cola_que_arranca_queda_retenida_sin_lanzar_ninguna_fase(self):
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46.replace("esperar = []", 'esperar = ["cola41"]'))
        self.sesiones.add("cola41")                                    # hay una sesión que esperar: no llega a mirarla
        self.assertTrue(self.cambiar("pausar", "orden del usuario", por="Claude (Diego)")["ok"])
        self.reloj += timedelta(minutes=5)
        self.nada_corre()
        historial = (self.tmp / "historial.jsonl").read_bytes()
        rc, corridas = self.correr_cola(ruta)
        self.assertEqual((rc, corridas, self.lanzados), (self.cr.CODIGO_RETENIDA, [], []))
        self.assertEqual(self.cr.CODIGO_RETENIDA, 5)
        v = self.vivo("cola46")
        motivo = "retenida por el despacho, en pausa desde las 18:55 (orden del usuario)"
        self.assertEqual((v["estado"], v["reanuda_desde"], v["motivo_pausa"], v["fin"], v["etapas"]),
                         ("retenida_por_despacho", "46a:autor", motivo, mc.iso(self.reloj), ["46a", "46b", "46c"]))
        for campo in ("fases_restantes", "lanzada", "fase", "etapa", "inicio_trabajo", "candado"):
            self.assertNotIn(campo, v)
        self.assertEqual((self.tmp / "historial.jsonl").read_bytes(), historial)      # ninguna fase quedó anotada
        self.assertEqual([p for p in self.pedidos if p[0] != "has-session"], [])       # y a tmux no se le pidió nada
        self.assertIn(f"⏸️ cola46 no partió: {motivo}. No corrió ninguna fase. Se reanuda desde 46a:autor", self.bitacora.read_text(encoding="utf-8"))
        (texto,), = self.avisos                                        # avisa como toda cola que termina (acá cae en la lista)
        self.assertIn("La cola cola46 no partió", texto)
        self.assertIn("ni gastó cuota", texto)
        self.assertFalse(self.marca("cola46").exists())
        self.assertEqual(sorted(p.name for p in self.vivos.iterdir()), ["acciones.jsonl", "cola46.json", "despacho.json"])

    def test_un_desde_tambien_queda_retenido_y_conserva_lo_andado(self):
        ruta = self.manifiesto("cola-41.toml")
        previo = self.poner("vivo-cola41.json")
        self.cambiar("pausar")
        self.nada_corre()
        rc, corridas = self.correr_cola(ruta, "--desde", "41:rev3")
        self.assertEqual((rc, corridas), (5, []))
        v = self.vivo("cola41")
        self.assertEqual((v["estado"], v["reanuda_desde"], v["motivo_pausa"]), ("retenida_por_despacho", "41:rev3", "retenida por el despacho, en pausa desde las 18:55"))
        self.assertEqual((v["lanzada"], v["fases_hechas"]), (previo["lanzada"], previo["fases_hechas"]))
        self.assertEqual(v["relanzamientos"], previo["relanzamientos"] + [{"momento": mc.iso(T), "desde": "41:rev3"}])
        self.assertIn("## Reanudación desde 41:rev3 · cola cola41", self.bitacora.read_text(encoding="utf-8"))
        # Y la cadena de reanudación (que no se edita) la deja para el usuario: su estado no es ninguno de los que relanza.
        cadena = (ENCARGOS / "reanudar-en-orden.sh").read_text(encoding="utf-8")
        self.assertIn('*) log "$c en «$est»: lo decide el usuario, se salta"; continue ;;', cadena)
        self.assertNotIn("retenida", cadena)

    def test_un_desde_sin_fase_queda_retenido_desde_el_autor_de_esa_etapa(self):
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46)
        self.cambiar("pausar")
        self.nada_corre()
        self.assertEqual(self.correr_cola(ruta, "--desde", "46b"), (5, []))
        self.assertEqual(self.vivo("cola46")["reanuda_desde"], "46b:autor")

    def test_la_cola_autorizada_corre_y_las_demas_no(self):
        ruta46 = self.manifiesto(texto=mc.MANIFIESTO_46)
        ruta47 = self.manifiesto(texto=mc.MANIFIESTO_46.replace('nombre = "cola46"', 'nombre = "cola47"'), destino="cola-47.toml")
        self.cambiar("pausar", autorizar=["cola46"])
        self.assertEqual(self.correr_cola(ruta47), (5, []))
        self.avisos.clear()
        rc, corridas = self.correr_cola(ruta46)
        self.assertEqual((rc, corridas, self.vivo("cola46")["estado"], self.vivo("cola47")["estado"]), (0, FASES_46, "terminada", "retenida_por_despacho"))
        self.assertNotIn("despacho", self.bitacora.read_text(encoding="utf-8").split("## Cola cola46")[1])
        # Un nombre que solo empieza igual no está autorizado.
        self.cambiar("abrir")
        self.cambiar("pausar", autorizar=["cola461"])
        self.assertEqual(self.correr_cola(ruta46), (5, []))

    def test_al_abrir_el_despacho_las_colas_vuelven_a_correr(self):
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46)
        self.cambiar("pausar")
        self.assertEqual(self.correr_cola(ruta), (5, []))
        self.avisos.clear()
        self.cambiar("abrir")
        self.assertEqual(self.correr_cola(ruta, "--desde", self.vivo("cola46")["reanuda_desde"])[1], FASES_46)
        self.assertEqual(self.vivo("cola46")["estado"], "terminada")

    def test_simular_y_panel_no_miran_el_despacho(self):
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46)
        self.cambiar("pausar", "orden del usuario")
        uso_real = self.cr.uso
        self.cr.uso = lambda cid, ruta=None, momento=None: uso_real(cid, ruta or self.uso_ruta, momento or self.reloj)
        antes = self.arbol()
        salida = io.StringIO()
        with mock.patch.object(sys, "argv", [str(COLA_RUN), str(ruta), "--simular"]), contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
            self.assertEqual(self.cr.principal(), 0)
        self.assertIn("⏱️ Duración de la cola", salida.getvalue())
        self.assertNotIn("despacho", salida.getvalue())
        rc, panel, _ = self.por_comandos("--panel")
        self.assertEqual((rc, panel["despacho"]["estado"], panel["despacho"]["motivo"]), (0, "pausa", "orden del usuario"))
        self.assertEqual((self.arbol(), self.avisos, self.lanzados), (antes, [], []))

    def test_despacho_json_no_se_cuenta_como_una_cola(self):
        # Vive en vivo/, al lado de los vivo/<cola>.json: el panel no lo lista como una cola ilegible ni deja débil la matriz.
        self.manifiesto(texto=mc.MANIFIESTO_46)
        self.poner("vivo-cola46-corriendo.json")
        self.sesiones = {"cola46"}
        self.reloj = datetime.fromisoformat("2026-10-11T19:40:00-03:00")
        antes = self.panel()
        for orden in ("pausar", "abrir"):
            self.cambiar(orden)
            ahora = self.panel()
            self.assertEqual((ahora["reglas"], ahora["colas_fuera"], ahora["colas"]), (antes["reglas"], antes["colas_fuera"], antes["colas"]))
        self.assertEqual(self.cr.leer_vivos(self.vivos)[1], [])
        (self.vivos / "despacho.json").write_bytes(b'{"estado": "pau')
        self.assertEqual((self.cr.leer_vivos(self.vivos)[1], self.panel()["colas_fuera"]), ([], antes["colas_fuera"]))

    def test_la_retenida_se_ve_en_el_panel_y_reanudar_la_autoriza_y_la_lanza(self):
        ruta = self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        self.cambiar("pausar", "orden del usuario")
        self.assertEqual(self.correr_cola(ruta, "--desde", "41:rev3"), (5, []))
        self.avisos.clear()
        panel = self.panel()
        fuera, = panel["colas_fuera"]
        self.assertEqual((fuera["cola"], fuera["estado"], fuera["fase"], fuera["motivo"]),
                         ("cola41", "retenida_por_despacho", "41:rev3", "retenida por el despacho, en pausa desde las 18:55 (orden del usuario)"))
        self.assertEqual([(f["etapa"], f["fase"]) for f in fuera["fases_restantes"]], [("41", "rev3")])
        self.assertEqual((panel["reglas"], panel["colas"]["cola41"]["acciones"]), ([], ["reanudar"]))     # no suma a la carga comprometida
        # Sin la confirmación extra, Reanudar se niega y no lanza; el despacho queda como estaba.
        antes = self.despacho()
        r = self.accion("reanudar", "cola41")
        self.assertEqual((r["ok"], self.lanzados, self.despacho()), (False, [], antes))
        self.assertEqual(r["error"], "no se puede reanudar cola41: el despacho está en pausa desde las 18:55 y la cola no está autorizada. "
                                     "El botón Reanudar pide la confirmación que la autoriza")
        self.assertEqual(r["despacho"], {"estado": "pausa", "desde": mc.iso(T), "motivo": "orden del usuario", "autorizada": False})
        # Con ella, la agrega a `autorizadas` y la lanza con el `--desde` de su vivo; y la cola lanzada corre.
        r = self.accion("reanudar", "cola41", autorizar=True)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["mensaje"], "cola41 se lanzó desde la etapa 41, fase rev3. Su sesión está viva; el estado cambia en unos segundos. "
                                       "Quedó autorizada mientras dure la pausa del despacho.")
        self.assertEqual((self.lanzados, self.despacho()), ([self.cr.argv_relanzar("cola41", ruta, "41:rev3")], antes | {"autorizadas": ["cola41"]}))
        self.assertEqual([(f["accion"], f["resultado"], f.get("autorizada_en_despacho")) for f in self.registro()],
                         [("despacho", "hecho", None), ("reanudar", "rechazada", None), ("reanudar", "hecho", True)])
        self.sesiones.clear()
        rc, corridas = self.correr_cola(ruta, *self.lanzados[0][8:])
        self.assertEqual((rc, corridas, self.vivo("cola41")["estado"]), (0, ["41-rev3"], "terminada"))


# ---------------------------------------------------------------- C3

class C3AusenteOCorrupto(Base):
    """Sin `despacho.json`, o con uno que no se puede leer, el despacho está abierto y la cola corre."""

    def test_sin_el_archivo_la_cola_corre_como_antes_y_no_hay_aviso(self):
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46)
        self.assertEqual(self.cr.leer_despacho(self.vivos), ({"estado": "abierto", "desde": None, "motivo": "", "autorizadas": [], "por": ""}, ""))
        rc, corridas = self.correr_cola(ruta)
        self.assertEqual((rc, corridas, self.vivo("cola46")["estado"]), (0, FASES_46, "terminada"))
        self.assertNotIn("despacho", self.bitacora.read_text(encoding="utf-8"))
        self.assertFalse((self.vivos / "despacho.json").exists())     # leer no lo crea

    def test_con_el_archivo_a_medias_la_cola_corre_y_queda_el_aviso_en_la_bitacora(self):
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46)
        self.cambiar("pausar", "orden del usuario")
        entero = (self.vivos / "despacho.json").read_bytes()
        (self.vivos / "despacho.json").write_bytes(entero[:len(entero) // 2])          # un JSON a medias, como el de un escritor no atómico
        rc, corridas = self.correr_cola(ruta)
        self.assertEqual((rc, corridas, self.vivo("cola46")["estado"]), (0, FASES_46, "terminada"))
        bitacora = self.bitacora.read_text(encoding="utf-8")
        self.assertEqual(bitacora.count(f"· ⚠️ {AVISO_ROTO}\n"), 1)
        self.assertLess(bitacora.index(AVISO_ROTO), bitacora.index("46a: autor"))      # antes de la primera fase
        self.assertEqual(self.panel()["despacho"], {"estado": "abierto", "desde": None, "motivo": "", "autorizadas": [], "por": "", "aviso": AVISO_ROTO})

    def test_toda_forma_que_no_sirve_es_abierto_con_aviso(self):
        ruta = self.vivos / "despacho.json"
        bueno = {"estado": "pausa", "desde": mc.iso(T), "motivo": "m", "autorizadas": ["cola46"], "por": "p"}
        fuera = self.tmp / "otro.json"
        fuera.write_text(json.dumps(bueno), encoding="utf-8")

        def enlace():
            ruta.symlink_to(fuera)
        casos = {
            "vacío": b"", "a medias": b'{"estado": "pau', "una lista": b"[]", "un texto": b'"pausa"', "no es UTF-8": b'{"estado": "\xff"}',
            "otro estado": json.dumps(bueno | {"estado": "cerrado"}).encode(), "sin estado": b'{"autorizadas": []}',
            "autorizadas no es lista": json.dumps(bueno | {"autorizadas": "cola46"}).encode(),
            "una autorizada hostil": json.dumps(bueno | {"autorizadas": ["cola46", "cola4; rm"]}).encode(),
            "una autorizada con salto": json.dumps(bueno | {"autorizadas": ["cola46\n"]}).encode(),
            "desde no es una hora": json.dumps(bueno | {"desde": "ayer"}).encode(),
            "demasiado grande": json.dumps(bueno | {"motivo": "x" * self.cr.TOPE_DESPACHO}).encode(),
            "anidado sin fin": b"[" * 60000,
            "un enlace a uno válido": enlace, "una carpeta": ruta.mkdir, "un FIFO": lambda: os.mkfifo(ruta),
        }
        for nombre, caso in casos.items():
            with self.subTest(caso=nombre):
                if ruta.is_dir() and not ruta.is_symlink():
                    ruta.rmdir()
                else:
                    ruta.unlink(missing_ok=True)
                caso() if callable(caso) else ruta.write_bytes(caso)
                d, aviso = self.cr.leer_despacho(self.vivos)            # un FIFO no lo deja colgado
                self.assertEqual(d, {"estado": "abierto", "desde": None, "motivo": "", "autorizadas": [], "por": ""})
                self.assertTrue(aviso.startswith("despacho.json no se pudo ") and aviso.endswith(": el despacho se trata como abierto"), aviso)
                self.assertNotIn("\n", aviso)
        self.assertEqual(json.loads(fuera.read_text(encoding="utf-8")), bueno)      # el destino del enlace no se tocó
        # Lo que sí sirve: el archivo entero, y uno mínimo (lo que falta vale vacío).
        ruta.unlink()
        ruta.write_text(json.dumps(bueno), encoding="utf-8")
        self.assertEqual(self.cr.leer_despacho(self.vivos), (bueno, ""))
        ruta.write_text('{"estado": "pausa", "motivo": "dos\\nlíneas", "autorizadas": ["cola46", "cola46"], "otra": 1}', encoding="utf-8")
        self.assertEqual(self.cr.leer_despacho(self.vivos), ({"estado": "pausa", "desde": None, "motivo": "dos líneas", "autorizadas": ["cola46"], "por": ""}, ""))

    def test_sobre_un_archivo_corrupto_la_orden_lo_reemplaza_y_lo_dice(self):
        (self.vivos / "despacho.json").write_bytes(b'{"estado": "pau')
        r = self.cambiar("pausar", "orden del usuario")
        self.assertEqual((r["ok"], r["aviso"], self.cr.leer_despacho(self.vivos)[1]), (True, AVISO_ROTO, ""))
        self.assertEqual(self.despacho()["estado"], "pausa")


# ---------------------------------------------------------------- C4

class C4Orden(Base):
    """`--despacho` valida los nombres con el patrón de `--accion`, escribe de forma atómica bajo `flock` y registra."""

    def test_pausar_y_abrir_dejan_la_forma_del_encargo_en_0600_y_su_linea_en_el_registro(self):
        r = self.cambiar("pausar", "  por orden\ndel usuario ", ["cola46"], "Claude (Diego)")
        esperado = {"estado": "pausa", "desde": mc.iso(T), "motivo": "por orden del usuario", "autorizadas": ["cola46"], "por": "Claude (Diego)"}
        self.assertEqual((r["ok"], r["accion"], r["orden"], r["despacho"], self.despacho()), (True, "despacho", "pausar", esperado, esperado))
        self.assertEqual(r["mensaje"], "El despacho quedó en pausa desde las 18:55. Una cola que arranque queda retenida, salvo las autorizadas. Colas autorizadas: cola46.")
        for nombre in ("despacho.json", "acciones.jsonl"):
            st = (self.vivos / nombre).stat()
            self.assertEqual((stat.S_IMODE(st.st_mode), st.st_uid), (0o600, os.getuid()), nombre)
        self.assertEqual(sorted(p.name for p in self.vivos.iterdir()), ["acciones.jsonl", "despacho.json"])        # no quedó ningún temporal
        # Pausar sobre una pausa: conserva desde, motivo y por, y suma las autorizadas (sin repetir).
        self.reloj += timedelta(hours=30)
        r = self.cambiar("pausar", autorizar=["cola50", "cola46"])
        self.assertEqual(r["despacho"], esperado | {"autorizadas": ["cola46", "cola50"]})
        self.assertEqual(r["mensaje"], "El despacho ya estaba en pausa desde el 11-10 a las 18:55; sigue en pausa. Colas autorizadas: cola46, cola50.")
        r = self.cambiar("pausar", "otro motivo", por="Codex")
        self.assertEqual(r["despacho"], esperado | {"autorizadas": ["cola46", "cola50"], "motivo": "otro motivo", "por": "Codex"})
        # Abrir: desde ahora, sin autorizadas ni el motivo de la pausa.
        r = self.cambiar("abrir")
        abierto = {"estado": "abierto", "desde": mc.iso(self.reloj), "motivo": "", "autorizadas": [], "por": "la terminal"}
        self.assertEqual((r["despacho"], self.despacho()), (abierto, abierto))
        self.assertEqual(self.cambiar("abrir")["mensaje"], "El despacho ya estaba abierto.")
        self.assertEqual(stat.S_IMODE((self.vivos / "despacho.json").stat().st_mode), 0o600)
        filas = self.registro()
        self.assertEqual([(f["accion"], f["orden"], f["resultado"], f["cola"], f["autorizadas"]) for f in filas],
                         [("despacho", "pausar", "hecho", None, ["cola46"]), ("despacho", "pausar", "hecho", None, ["cola46", "cola50"]),
                          ("despacho", "pausar", "hecho", None, ["cola46", "cola50"]), ("despacho", "abrir", "hecho", None, []),
                          ("despacho", "abrir", "hecho", None, [])])
        self.assertEqual(filas[0]["detalle"], "El despacho quedó en pausa desde las 18:55. Una cola que arranque queda retenida, salvo las autorizadas. Colas autorizadas: cola46.")

    def test_valida_los_nombres_con_el_patron_de_accion_y_no_escribe_nada(self):
        self.cambiar("pausar", autorizar=["cola41"])
        antes = (self.vivos / "despacho.json").read_bytes()
        for hostil in HOSTILES + [None, 46, ["cola46"]]:
            for lista in ([hostil], ["cola46", hostil]):
                with self.subTest(hostil=hostil):
                    r = self.cambiar("pausar", autorizar=lista)
                    self.assertEqual((r["ok"], r["error"]), (False, "nombre de cola inválido en las autorizadas: «cola», dos dígitos y, si sigue algo, "
                                                                    "letras minúsculas o dígitos"))
                    self.assertNotIn("despacho", r)
        self.assertEqual((self.vivos / "despacho.json").read_bytes(), antes)
        filas = self.registro()[1:]
        self.assertEqual({(f["resultado"], f["autorizadas"]) for f in filas}, {("rechazada", None)})
        self.assertNotIn("rm", json.dumps(filas))                      # el nombre hostil no queda escrito
        # Es el mismo patrón, el mismo objeto y con fullmatch: los nombres que acepta `--accion` y ninguno más.
        fuente = COLA_RUN.read_text(encoding="utf-8")
        cuerpo = fuente[fuente.index("def cambiar_despacho("):fuente.index("def _fase_texto(")]
        self.assertIn("if not all(isinstance(c, str) and RE_COLA.fullmatch(c) for c in autorizar):", cuerpo)
        self.assertEqual(fuente.count("RE_COLA = re.compile("), 1)
        for bueno in ("cola41", "cola22b", "cola43s"):
            self.assertEqual(self.cambiar("pausar", autorizar=[bueno])["ok"], self.accion("reanudar", bueno, True)["error"] != self.accion("reanudar", "cola4; rm", True)["error"])
        # Abrir no lleva autorizadas, y una orden que no existe no toca nada (ni el registro).
        r = self.cambiar("abrir", autorizar=["cola46"])
        self.assertEqual((r["ok"], r["error"]), (False, "abrir el despacho no lleva colas autorizadas: con el despacho abierto corren todas"))
        n = len(self.registro())
        self.assertEqual(self.cambiar("borrar")["error"], "orden de despacho desconocida")
        self.assertEqual((len(self.registro()), self.despacho()["estado"]), (n, "pausa"))

    def test_por_la_linea_de_comandos(self):
        rc, r, error = self.por_comandos("--despacho", "pausar", "--motivo", "orden del usuario", "--por", "Claude (Diego)", "--autorizar", "cola46", "cola50")
        self.assertEqual((rc, error, r["despacho"]), (0, "", {"estado": "pausa", "desde": mc.iso(T), "motivo": "orden del usuario",
                                                              "autorizadas": ["cola46", "cola50"], "por": "Claude (Diego)"}))
        self.assertEqual(self.despacho(), r["despacho"])
        rc, r, error = self.por_comandos("--despacho", "pausar", "--autorizar", "cola46", "../x")
        self.assertEqual((rc, r["ok"], json.loads(error)), (1, False, r))             # con código 1, el JSON se repite por stderr
        rc, r, _ = self.por_comandos("--despacho", "abrir")
        self.assertEqual((rc, r["despacho"]["estado"], r["despacho"]["por"]), (0, "abierto", "la terminal"))
        self.assertEqual((self.avisos, self.lanzados, self.pedidos), ([], [], []))
        self.assertFalse(self.bitacora.exists())                       # la orden no escribe la bitácora ni un vivo
        # Lo que no es la forma del encargo sale por argparse (código 2) sin tocar nada.
        antes = self.arbol()
        for mal in (["--despacho", "cerrar"], ["--despacho", "pausar", "cola-46.toml"], ["--despacho", "pausar", "--simular"],
                    ["--despacho", "pausar", "--panel"], ["--despacho", "abrir", "--accion", "reanudar"], ["--despacho", "pausar", "--desde", "46a:autor"],
                    ["--motivo", "x", "--panel"], ["--por", "x", "--panel"], ["--autorizar", "cola46", "--panel"], ["--panel", "--autorizar"],
                    ["cola-46.toml", "--autorizar", "cola46"], ["--accion", "pausar", "cola46", "--autorizar", "cola46"],
                    ["--accion", "reanudar", "cola46", "--autorizar"], ["--accion", "reanudar", "cola46", "--autorizar", "cola41"],
                    ["--accion", "reanudar", "cola46", "--autorizar", "cola46", "cola41"], ["--accion", "reanudar", "cola46", "--simular", "--autorizar", "cola46"]):
            with self.subTest(mal=mal), mock.patch.object(sys, "argv", [str(COLA_RUN), *mal]), contextlib.redirect_stderr(io.StringIO()), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as fin:
                self.cr.main()
            self.assertEqual(fin.exception.code, 2, mal)
        self.assertEqual(self.arbol(), antes)

    def test_si_la_orden_se_cae_no_avisa_ni_deja_un_vivo_ni_escribe_la_bitacora(self):
        # `--despacho` no es una cola: un error inesperado no puede terminar en «la cola ? se cayó» por Telegram ni en vivo/None.json.
        self.cr.cambiar_despacho = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("inesperado"))
        antes = self.arbol()
        error = io.StringIO()
        with mock.patch.object(sys, "argv", [str(COLA_RUN), "--despacho", "pausar"]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(error):
            rc = self.cr.principal()
        self.assertEqual((rc, error.getvalue(), self.avisos, self.arbol()), (2, "⛔ RuntimeError: inesperado\n", [], antes))

    def test_dos_llamadas_simultaneas_no_dejan_un_json_roto_ni_pierden_una_autorizada(self):
        self.cambiar("pausar", "orden del usuario")
        colas = [f"cola{i:02d}" for i in range(10, 34)]
        errores, vistos, parar = [], [[], []], threading.Event()
        partida = threading.Barrier(len(colas) + 2)

        def escribe(cola):
            try:
                partida.wait(5)
                r = self.cr.cambiar_despacho("pausar", None, [cola], vivos_dir=self.vivos, momento=self.reloj)
                if not r["ok"]:
                    errores.append(r)
            except Exception as e:      # noqa: BLE001
                errores.append(repr(e))

        def lee(suyos):                 # como una cola que arranca: sin candado, mientras otros escriben
            try:
                partida.wait(5)
                while not parar.is_set():
                    d, aviso = self.cr.leer_despacho(self.vivos)
                    suyos.append(len(d["autorizadas"]))
                    if aviso or d["estado"] != "pausa":
                        errores.append(aviso or d)
            except Exception as e:      # noqa: BLE001
                errores.append(repr(e))
        lectores = [threading.Thread(target=lee, args=(suyos,)) for suyos in vistos]
        escritores = [threading.Thread(target=escribe, args=(c,)) for c in colas]
        for h in lectores + escritores:
            h.start()
        for h in escritores:
            h.join(20)
        parar.set()
        for h in lectores:
            h.join(20)
        self.assertEqual(errores, [])
        d = self.despacho()                                            # un JSON entero…
        self.assertEqual((sorted(d["autorizadas"]), d["estado"], d["desde"], d["motivo"]), (colas, "pausa", mc.iso(T), "orden del usuario"))    # …y nadie pisó a nadie
        for suyos in vistos:
            self.assertGreater(len(suyos), 0)
            self.assertEqual(suyos, sorted(suyos))                     # cada lector vio siempre el archivo entero, con cada vez más autorizadas
        self.assertEqual(sorted(p.name for p in self.vivos.iterdir()), ["acciones.jsonl", "despacho.json"])
        filas = self.registro()
        self.assertEqual(len(filas), 1 + len(colas))
        self.assertEqual([len(f["autorizadas"]) for f in filas], list(range(len(colas) + 1)))      # una por vez, bajo el candado

    def test_el_reanudar_autorizado_y_la_orden_usan_el_mismo_candado(self):
        self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        self.cambiar("pausar")
        colas = [f"cola{i:02d}" for i in range(50, 62)]
        resultados = []
        partida = threading.Barrier(len(colas) + 1)

        def orden(cola):
            partida.wait(5)
            resultados.append(self.cr.cambiar_despacho("pausar", None, [cola], vivos_dir=self.vivos, momento=self.reloj)["ok"])

        def reanuda():
            partida.wait(5)
            resultados.append(self.accion("reanudar", "cola41", autorizar=True)["ok"])
        hilos = [threading.Thread(target=orden, args=(c,)) for c in colas] + [threading.Thread(target=reanuda)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(20)
        self.assertEqual(resultados, [True] * (len(colas) + 1))
        self.assertEqual(sorted(self.despacho()["autorizadas"]), sorted(colas + ["cola41"]))
        self.assertEqual(len(self.lanzados), 1)
        fuente = COLA_RUN.read_text(encoding="utf-8")
        self.assertEqual(fuente.count('_abrir_para_agregar(vivos_dir / "acciones.jsonl", 0o600)'), 2)      # accion_cola() y cambiar_despacho()
        self.assertEqual(fuente.count("_escribir_despacho(vivos_dir, "), 2)                                # los dos únicos escritores
        self.assertEqual(len(re.findall(r'"despacho\.json"', fuente)), 3)                                  # el lector, el escritor y leer_vivos(), que lo salta

    def test_si_no_se_puede_escribir_lo_dice_y_no_queda_un_temporal(self):
        self.cambiar("pausar", "orden del usuario")
        antes = (self.vivos / "despacho.json").read_bytes()
        with mock.patch.object(self.cr.os, "replace", side_effect=PermissionError("no")):
            r = self.cambiar("abrir")
        self.assertEqual((r["ok"], r["error"]), (False, "el despacho no se pudo cambiar (PermissionError)"))
        self.assertEqual((self.vivos / "despacho.json").read_bytes(), antes)
        self.assertEqual(sorted(p.name for p in self.vivos.iterdir()), ["acciones.jsonl", "despacho.json"])
        self.assertEqual(self.registro()[-1]["resultado"], "fallida")


# ---------------------------------------------------------------- C5

class C5Pagina(ta.Pagina):
    """El estado del despacho y sus botones en 🧵 Encargos, de punta a punta: el argv que arma la página (leído del JS)
    corre contra el `cola-run.py` real sobre fixtures, y lo que la página dibuja después sale del `--panel` real."""
    locals().update({n: None for n in dir(ta.Pagina) if n.startswith("test_")})       # las pruebas de la 46c corren en su suite

    TEXTO_PAUSAR = ("¿Pausar el despacho?\n\nDesde ahora, una cola que arranque queda retenida sin correr ninguna fase ni gastar cuota: también la que "
                    "lance un timer o la cadena de reanudación. Las que ya están corriendo siguen. Durante la pausa, Reanudar pide autorizar esa cola."
                    "\n\nMotivo (puede quedar vacío):")
    TEXTO_ABRIR = ("¿Abrir el despacho?\n\nLas colas vuelven a arrancar sin pedir autorización y se borran las autorizadas de esta pausa. Una cola que "
                   "quedó retenida no parte sola: se reanuda con el botón Reanudar.")
    POR = "el usuario, desde 🧵 Encargos"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        i, j = cls.js.index("// Encargo 50a: el estado del despacho y la mirada de pasado"), cls.js.index("// Encargo 46c: Reanudar, Pausar y Detener.")
        cls.bloque50 = cls.js[i:j]

    # ---- el espejo de la 50a
    def argv_despacho(self, orden, motivo):
        """argvDespacho(): el arreglo literal del JS, con sus constantes."""
        self.assertIn('const argvDespacho = (orden, motivo) => ["python3", COLA_RUN, "--despacho", orden, "--por", POR_PAGINA, '
                      '...(motivo ? ["--motivo", motivo] : [])];', self.bloque50)
        self.assertIn(f'const POR_PAGINA = "{self.POR}";', self.bloque50)
        return ["python3", self.RUTA_JS, "--despacho", orden, "--por", self.POR] + (["--motivo", motivo] if motivo else [])

    def correr_despacho(self, orden, motivo):
        if orden not in ("pausar", "abrir") or (motivo is not None and not isinstance(motivo, str)):
            raise ValueError("orden de despacho inválida")
        return self.respuesta_cola(self.argv_despacho(orden, motivo))

    def ordenar_despacho(self, orden, escrito="", confirma=True):
        """ordenarDespacho(): `escrito` es lo que devuelve prompt() al pausar (None = Cancelar) y `confirma`, el confirm() de abrir."""
        self.resultado = None
        try:
            motivo = None
            if orden == "pausar":
                self.dialogos.append(self.TEXTO_PAUSAR)
                if escrito is None:
                    return
                motivo = re.sub(r"\s+", " ", escrito).strip()[:200]
            else:
                self.dialogos.append(self.TEXTO_ABRIR)
                if not confirma:
                    return
            r = self.correr_despacho(orden, motivo)
            self.resultado = (False, self.del_panel(r["mensaje"]))
        except ValueError as e:
            self.resultado = (True, self.del_panel(str(e)))
        finally:
            self.leidas += 1

    def tarjeta_despacho(self, x) -> dict:
        """tarjetaDespacho(): (clase, texto, notas, aviso, botón) de lo que publica el panel en `despacho`."""
        if not isinstance(x, dict) or x.get("estado") not in ("abierto", "pausa"):
            return {"clase": "neutro", "texto": "Despacho: sin datos", "boton": None}
        pausa = x["estado"] == "pausa"
        autorizadas = [c for c in x["autorizadas"] if isinstance(c, str) and self.cola_valida.search(c)] if isinstance(x.get("autorizadas"), list) else []
        notas = [f"desde {self.desde_despacho(x['desde'])}" if x.get("desde") and not pausa else None,
                 f"lo dejó así {self.del_panel(x['por'])}" if x.get("por") else None,
                 (f"autorizadas: {', '.join(autorizadas)}" if autorizadas else "ninguna cola autorizada") if pausa else None]
        texto = f"Despacho en pausa desde {self.desde_despacho(x.get('desde'))} — {self.motivo_despacho(x)}" if pausa else "Despacho abierto"
        return {"clase": "ojo" if pausa else "ok", "texto": texto, "notas": " · ".join(n for n in notas if n),
                "aviso": self.del_panel(x["aviso"]) if x.get("aviso") else None, "boton": "Abrir despacho" if pausa else "Pausar despacho"}

    def panel_despacho(self) -> dict:
        self.cr.SIMULANDO = True
        return self.cr.panel(vivos_dir=self.vivos, uso_de=self.uso_de, momento=self.reloj, viva=lambda n: n in self.sesiones,
                             manifiestos_dir=self.tmp, timers=[])["despacho"]

    def despacho(self) -> dict:
        return json.loads((self.vivos / "despacho.json").read_text(encoding="utf-8"))

    # ---- las pruebas
    def test_el_espejo_es_el_js(self):
        for linea in (
                'const ORDENES_DESPACHO = new Map([["pausar", "Pausar despacho"], ["abrir", "Abrir despacho"]]);',
                'if (!ORDENES_DESPACHO.has(orden) || (motivo != null && typeof motivo !== "string")) throw new Error("orden de despacho inválida");',
                'return respuestaCola(cockpit.spawn(argvDespacho(orden, motivo), { err: "message" }));',
                'if (orden === "pausar") { const escrito = prompt(textoOrdenDespacho(orden), ""); if (escrito === null) return; '
                'motivo = escrito.replace(/\\s+/g, " ").trim().slice(0, 200); }',
                "else if (!confirm(textoOrdenDespacho(orden))) return;",
                "const r = await correrDespacho(orden, motivo);",
                'resultadoAccion = { cola: "Despacho", mal: false, texto: delPanel(r.mensaje) };',
                '} catch (e) { resultadoAccion = { cola: "Despacho", mal: true, texto: delPanel(e.message || String(e)) }; }',
                "finally { accionEnCurso = false; await leer().catch(() => pintar()); }",
                'function textoDespacho(x) { return x.estado === "pausa" ? `Despacho en pausa desde ${desdeDespacho(x.desde)} — ${motivoDespacho(x)}` : "Despacho abierto"; }',
                'const motivoDespacho = x => (x && typeof x.motivo === "string" && x.motivo.trim() ? delPanel(x.motivo) : "sin motivo");',
                'return t.toDateString() === new Date().toDateString() ? `las ${h}` : `el ${dos(t.getDate())}-${dos(t.getMonth() + 1)} a las ${h}`;',
                'if (!x || !["abierto", "pausa"].includes(x.estado)) return el("div", { class: "aviso neutro despacho" }, el("strong", {}, "Despacho: "), "sin datos");',
                'const pausa = x.estado === "pausa", orden = pausa ? "abrir" : "pausar";',
                'const autorizadas = (Array.isArray(x.autorizadas) ? x.autorizadas : []).filter(c => typeof c === "string" && COLA_VALIDA.test(c));',
                'const notas = [x.desde && !pausa ? `desde ${desdeDespacho(x.desde)}` : null, x.por ? `lo dejó así ${delPanel(x.por)}` : null,',
                'pausa ? (autorizadas.length ? `autorizadas: ${autorizadas.join(", ")}` : "ninguna cola autorizada") : null].filter(Boolean).join(" · ");',
                'return el("div", { class: `aviso ${pausa ? "ojo" : "ok"} despacho` },',
                'x.aviso ? el("span", { class: "chip ojo" }, delPanel(x.aviso)) : null),',
                'el("button", { class: "mini", disabled: accionEnCurso, onclick: () => ordenarDespacho(orden) }, ORDENES_DESPACHO.get(orden)));',
                'const faltaAutorizar = sim => !!sim && esObjeto(sim.despacho) && sim.despacho.estado === "pausa" && sim.despacho.autorizada !== true;'):
            self.assertIn(linea, self.bloque50, linea)
        # Los textos de las confirmaciones del espejo, letra por letra.
        llano = self.bloque50.replace("\\n\\n", "\n\n")
        for texto in (self.TEXTO_PAUSAR, self.TEXTO_ABRIR):
            self.assertIn(f'"{texto}"', llano)
        self.assertIn("`" + self.texto_autorizar("${cola}", {"desde": None, "motivo": ""}).replace("una hora sin datos", "${desdeDespacho(x.desde)}")
                      .replace("sin motivo", "${motivoDespacho(x)}") + "`", llano)
        # Dónde va: arriba de «Ahora», antes de las tarjetas de las colas; y el panel entrega `despacho` y `pasado`.
        self.assertIn("p.replaceChildren(...avisoAccion(), tarjetaDespacho(), ...ms.map(tarjetaCola), ...tarjetaCarga(ms), ...ahoraDeducida(vivo(), ms.length > 0));", self.js)
        self.assertIn("despacho: esObjeto(x.despacho) ? x.despacho : null, pasado: esObjeto(x.pasado) ? x.pasado : null,", self.js)
        self.assertIn("despacho: panelColas.despacho, pasado: panelColas.pasado,", self.js)
        self.assertIn('const esObjeto = x => !!x && typeof x === "object" && !Array.isArray(x);', self.js)
        # En ordenarDespacho(), la orden de verdad está después de la confirmación y se llama una sola vez.
        cuerpo = self.bloque50[self.bloque50.index("async function ordenarDespacho("):self.bloque50.index("// Arriba de «Ahora».")]
        self.assertEqual(cuerpo.count("correrDespacho("), 1)
        self.assertLess(max(cuerpo.index("prompt(textoOrdenDespacho(orden)"), cuerpo.index("confirm(textoOrdenDespacho(orden))")), cuerpo.index("correrDespacho(orden, motivo)"))
        self.assertEqual(len(re.findall(r"ordenarDespacho\(", self.js)), 2)            # la definición y el botón
        # La cola retenida: su nombre en «Detenidas o pausadas» y su tarjeta.
        self.assertIn('["retenida_por_despacho", "retenida por el despacho"]', self.js)
        self.assertIn('const retenida = m.estado === "retenida_por_despacho", suVivo = d.vivos.find(v => v.nombre === m.cola) || {};', self.js)
        self.assertIn('`No partió: ${delPanel(suVivo.motivo_pausa)}. No corrió ninguna fase. Se reanuda desde ${fasePanel(suVivo.reanuda_desde)} con el botón Reanudar.`', self.js)
        for clase in (".despacho", ".pasado-tabla"):
            self.assertIn(clase + " {", self.css)

    def test_los_unicos_comandos_son_el_argv_fijo_y_nada_va_como_html(self):
        codigo = self.tokens_js(self.bloque50, strings=True)
        self.assertEqual(re.findall(r"cockpit\.(\w+)\(([^)]{0,40})", codigo), [("spawn", "argvDespacho(orden, motivo")])
        for prohibido in ('"sh"', '"bash"', "shell", "superuser", "innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "localStorage", "fetch(", "cockpit.file", "sudo"):
            self.assertNotIn(prohibido, codigo, prohibido)
        # El motivo, por hostil que sea, entra entero en UN argumento: no arma un comando ni otro argumento.
        for motivo in ("x; rm -rf /", "--autorizar cola46", "$(id)", "a\nb"):
            self.assertEqual(self.argv_despacho("pausar", motivo), ["python3", self.RUTA_JS, "--despacho", "pausar", "--por", self.POR, "--motivo", motivo])
        self.assertEqual(self.argv_despacho("abrir", None), ["python3", self.RUTA_JS, "--despacho", "abrir", "--por", self.POR])
        for mala in ("cerrar", "", None, "pausar; rm"):
            with self.assertRaises(ValueError):
                self.correr_despacho(mala, None)
        with self.assertRaises(ValueError):
            self.correr_despacho("pausar", 5)
        self.assertEqual(self.spawns, [])

    def test_pausar_despacho_de_punta_a_punta(self):
        self.assertEqual(self.tarjeta_despacho(self.panel_despacho()),
                         {"clase": "ok", "texto": "Despacho abierto", "notas": "", "aviso": None, "boton": "Pausar despacho"})
        antes = self.arbol()
        self.ordenar_despacho("pausar", escrito=None)                 # Cancelar: ni spawn ni archivo
        self.assertEqual((self.spawns, self.resultado, self.arbol(), self.dialogos), ([], None, antes, [self.TEXTO_PAUSAR]))
        self.ordenar_despacho("pausar", escrito="  por orden\tdel usuario \n")
        self.assertEqual(self.spawns, [["python3", self.RUTA_JS, "--despacho", "pausar", "--por", self.POR, "--motivo", "por orden del usuario"]])
        self.assertEqual(self.resultado, (False, "El despacho quedó en pausa desde las 18:55. Una cola que arranque queda retenida, salvo las autorizadas."))
        self.assertEqual(self.despacho(), {"estado": "pausa", "desde": mc.iso(T), "motivo": "por orden del usuario", "autorizadas": [], "por": self.POR})
        self.assertEqual(stat.S_IMODE((self.vivos / "despacho.json").stat().st_mode), 0o600)
        self.assertEqual(self.leidas, 2)
        # Después de actuar la página relee: el panel dice «en pausa» y el botón pasa a ser Abrir despacho.
        self.assertEqual(self.tarjeta_despacho(self.panel_despacho()),
                         {"clase": "ojo", "texto": "Despacho en pausa desde las 18:55 — por orden del usuario",
                          "notas": "lo dejó así el usuario, desde 🧵 Encargos · ninguna cola autorizada", "aviso": None, "boton": "Abrir despacho"})
        self.reloj += timedelta(days=1)                               # al otro día dice también la fecha
        self.assertEqual(self.tarjeta_despacho(self.panel_despacho())["texto"], "Despacho en pausa desde el 11-10 a las 18:55 — por orden del usuario")
        # Sin motivo: el argv no lleva --motivo y la página dice «sin motivo».
        self.ordenar_despacho("abrir")
        self.ordenar_despacho("pausar", escrito="   ")
        self.assertEqual(self.spawns[-1], ["python3", self.RUTA_JS, "--despacho", "pausar", "--por", self.POR])
        self.assertEqual(self.tarjeta_despacho(self.panel_despacho())["texto"], "Despacho en pausa desde las 18:55 — sin motivo")

    def test_abrir_despacho_de_punta_a_punta(self):
        self.cr.cambiar_despacho("pausar", "orden del usuario", ["cola46"], "Claude (Diego)", vivos_dir=self.vivos, momento=self.reloj)
        self.assertEqual(self.tarjeta_despacho(self.panel_despacho()),
                         {"clase": "ojo", "texto": "Despacho en pausa desde las 18:55 — orden del usuario",
                          "notas": "lo dejó así Claude (Diego) · autorizadas: cola46", "aviso": None, "boton": "Abrir despacho"})
        antes = self.arbol()
        self.ordenar_despacho("abrir", confirma=False)
        self.assertEqual((self.spawns, self.resultado, self.arbol(), self.dialogos), ([], None, antes, [self.TEXTO_ABRIR]))
        self.reloj += timedelta(minutes=30)
        self.ordenar_despacho("abrir")
        self.assertEqual(self.spawns, [["python3", self.RUTA_JS, "--despacho", "abrir", "--por", self.POR]])
        self.assertEqual(self.resultado, (False, "El despacho quedó abierto. Una cola retenida no parte sola: se reanuda con el botón Reanudar."))
        self.assertEqual(self.despacho(), {"estado": "abierto", "desde": mc.iso(self.reloj), "motivo": "", "autorizadas": [], "por": self.POR})
        self.assertEqual(self.tarjeta_despacho(self.panel_despacho()),
                         {"clase": "ok", "texto": "Despacho abierto", "notas": "desde las 19:25 · lo dejó así el usuario, desde 🧵 Encargos",
                          "aviso": None, "boton": "Pausar despacho"})
        # Con el despacho abierto, una cola arranca y corre.
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46)
        self.assertEqual(self.correr_cola(ruta), (0, FASES_46))

    def test_reanudar_durante_una_pausa_pide_la_confirmacion_extra_que_autoriza(self):
        ruta = self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        self.ordenar_despacho("pausar", escrito="orden del usuario")
        self.spawns.clear(), self.dialogos.clear()
        self.assertEqual(self.botones(self.colas_panel(), "cola41", ["reanudar"]), ["reanudar"])
        antes = self.arbol()
        extra = ("El despacho está en pausa desde las 18:55 — orden del usuario.\n\n¿Autorizar cola41 a correr igual? Queda entre las autorizadas "
                 "mientras dure esta pausa y parte ahora. Las demás colas siguen retenidas.")
        simulacion = ["python3", self.RUTA_JS, "--accion", "reanudar", "cola41", "--simular"]
        # Sin la primera confirmación, o sin la extra: solo corrió la simulación; no se lanzó ni se autorizó nada.
        self.accionar("reanudar", "cola41", confirma=False)
        self.assertEqual(len(self.dialogos), 1)
        self.accionar("reanudar", "cola41", autoriza=False)
        self.assertEqual((self.dialogos[1].split("\n")[0], self.dialogos[2]), ("¿Reanudar cola41 desde 41:rev3?", extra))
        self.assertEqual((self.spawns, self.lanzados, self.resultado, self.arbol()), ([simulacion, simulacion], [], None, antes))
        # Con las dos: la acción lleva --autorizar con la misma cola, la deja en `autorizadas` y la lanza.
        self.accionar("reanudar", "cola41")
        self.assertEqual(self.spawns[2:], [simulacion, ["python3", self.RUTA_JS, "--accion", "reanudar", "cola41", "--autorizar", "cola41"]])
        self.assertEqual(self.lanzados, [self.cr.argv_relanzar("cola41", ruta, "41:rev3")])
        self.assertEqual(self.resultado, (False, "cola41 se lanzó desde la etapa 41, fase rev3. Su sesión está viva; el estado cambia en unos segundos. "
                                                 "Quedó autorizada mientras dure la pausa del despacho."))
        self.assertEqual(self.despacho()["autorizadas"], ["cola41"])
        self.assertEqual(self.tarjeta_despacho(self.panel_despacho())["notas"], "lo dejó así el usuario, desde 🧵 Encargos · autorizadas: cola41")
        # La cola lanzada arranca de verdad (está autorizada) y corre su fase.
        self.sesiones.clear()
        rc, corridas = self.correr_cola(ruta, *self.lanzados[0][8:])
        self.assertEqual((rc, corridas), (0, ["41-rev3"]))

    def test_una_cola_ya_autorizada_o_con_el_despacho_abierto_no_pide_la_confirmacion_extra(self):
        ruta = self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        self.cr.cambiar_despacho("pausar", "orden del usuario", ["cola41"], vivos_dir=self.vivos, momento=self.reloj)
        self.accionar("reanudar", "cola41")
        self.assertEqual(len(self.dialogos), 1)
        self.assertEqual(self.spawns[-1], ["python3", self.RUTA_JS, "--accion", "reanudar", "cola41"])
        self.assertEqual(self.lanzados, [self.cr.argv_relanzar("cola41", ruta, "41:rev3")])
        self.assertEqual(self.resultado[1], "cola41 se lanzó desde la etapa 41, fase rev3. Su sesión está viva; el estado cambia en unos segundos.")
        # Con el despacho abierto, la simulación ni trae `despacho`: Reanudar es el de la 46c.
        self.sesiones.clear()
        self.ordenar_despacho("abrir")
        self.assertNotIn("despacho", self.correr_accion("reanudar", "cola41", True))
        self.accionar("reanudar", "cola41")
        self.assertEqual((len(self.dialogos), self.spawns[-1]), (3, ["python3", self.RUTA_JS, "--accion", "reanudar", "cola41"]))
        self.assertEqual(self.despacho()["autorizadas"], [])

    def test_una_pagina_vieja_no_se_salta_la_confirmacion_extra(self):
        # La página simuló con el despacho abierto; entre medio se pausó. La acción sin --autorizar se rechaza en cola-run.py.
        self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        self.correr_accion("reanudar", "cola41", True)
        self.cr.cambiar_despacho("pausar", vivos_dir=self.vivos, momento=self.reloj)
        with self.assertRaises(ValueError) as error:
            self.correr_accion("reanudar", "cola41", False)
        self.assertIn("el despacho está en pausa desde las 18:55 y la cola no está autorizada", str(error.exception))
        self.assertEqual((self.lanzados, self.despacho()["autorizadas"]), ([], []))
        # Y --autorizar no sirve para autorizar otra cola ni viaja con otra acción (lo decide el JS y lo vuelve a decidir argparse).
        self.assertEqual(self.argv("pausar", "cola41", False, autorizar=False)[-2:], ["pausar", "cola41"])
        self.assertIn('autorizar === true && accion === "reanudar" && !simular', self.bloque)

    def test_la_cola_retenida_ofrece_reanudar_y_la_tarjeta_dice_por_que(self):
        ruta = self.manifiesto(texto=mc.MANIFIESTO_46)
        self.ordenar_despacho("pausar", escrito="orden del usuario")
        self.assertEqual(self.correr_cola(ruta), (5, []))
        self.avisos.clear()
        colas = self.colas_panel()
        self.assertEqual((self.botones(colas, "cola46", ["reanudar"]), self.botones(colas, "cola46", ["pausar", "detener"])), (["reanudar"], []))
        v = json.loads((self.vivos / "cola46.json").read_text(encoding="utf-8"))
        tarjeta = f"No partió: {self.del_panel(v['motivo_pausa'])}. No corrió ninguna fase. Se reanuda desde {self.fase_panel(v['reanuda_desde'])} con el botón Reanudar."
        self.assertEqual(tarjeta, "No partió: retenida por el despacho, en pausa desde las 18:55 (orden del usuario). No corrió ninguna fase. "
                                  "Se reanuda desde 46a:autor con el botón Reanudar.")
        self.accionar("reanudar", "cola46")
        self.assertEqual(self.lanzados, [self.cr.argv_relanzar("cola46", ruta, "46a:autor")])
        self.sesiones.clear()
        self.assertEqual(self.correr_cola(ruta, *self.lanzados[0][8:]), (0, FASES_46))

    def test_un_despacho_que_no_se_pudo_leer_se_ve_abierto_con_su_aviso(self):
        (self.vivos / "despacho.json").write_bytes(b'{"estado": "pau')
        self.assertEqual(self.tarjeta_despacho(self.panel_despacho()),
                         {"clase": "ok", "texto": "Despacho abierto", "notas": "", "aviso": AVISO_ROTO, "boton": "Pausar despacho"})
        for sin_datos in (None, [], {"estado": "cerrado"}, {}):
            self.assertEqual(self.tarjeta_despacho(sin_datos), {"clase": "neutro", "texto": "Despacho: sin datos", "boton": None})

    def test_todo_texto_del_despacho_pasa_por_la_lista_blanca_y_por_la_regla_de_nombres(self):
        self.manifiesto("cola-41.toml")
        self.poner("vivo-cola41.json")
        textos = []

        def junta(r):
            textos.extend([r.get("mensaje"), r.get("error"), r.get("aviso"), *(r.get("texto") or [])])
            return r
        cambiar = lambda *a, **k: junta(self.cr.cambiar_despacho(*a, vivos_dir=self.vivos, momento=self.reloj, **k))
        cambiar("abrir")
        cambiar("abrir")
        cambiar("abrir", autorizar=["cola46"])
        cambiar("pausar", "orden del usuario", ["cola46", "cola50"], "Claude (Diego)")
        cambiar("pausar", autorizar=["cola4; rm"])
        cambiar("borrar")
        junta(self.accion("reanudar", "cola41", True))
        junta(self.accion("reanudar", "cola41"))
        junta(self.accion("reanudar", "cola41", autorizar=True, lanzar=lambda argv: 1))
        self.reloj += timedelta(days=2)
        cambiar("pausar")
        junta(self.accion("reanudar", "cola41"))
        (self.vivos / "despacho.json").write_bytes(b"[]")
        cambiar("pausar")
        for roto in (b'{"estado": "pau', b'{"estado": "pausa", "autorizadas": 5}', b'{"estado": "pausa", "desde": "ayer"}', b"x" * (self.cr.TOPE_DESPACHO + 1)):
            (self.vivos / "despacho.json").write_bytes(roto)
            textos.append(self.cr.leer_despacho(self.vivos)[1])
        with mock.patch.object(self.cr.os, "replace", side_effect=PermissionError("no")):
            cambiar("abrir")
        textos = sorted({t for t in textos if t})
        self.assertGreaterEqual(len(textos), 14)
        for t in textos:
            self.assertEqual(self.del_panel(t), t)
        # El motivo de la retención, tal como queda en el vivo y sale en `colas_fuera`.
        self.assertEqual(self.del_panel("retenida por el despacho, en pausa desde el 11-10 a las 18:55 (orden del usuario)"),
                         "retenida por el despacho, en pausa desde el 11-10 a las 18:55 (orden del usuario)")
        # Lo que escribe una persona (motivo, por) es un dato: un secreto queda «oculto» y un nombre suelto, también.
        secreto = "sk-proj-Abc123Def456Ghi789Jkl012"
        self.cr.cambiar_despacho("pausar", f"token={secreto} lo pidió Diego", por="Camila", vivos_dir=self.vivos, momento=self.reloj + timedelta(seconds=1))
        t = self.tarjeta_despacho(self.panel_despacho())
        self.assertNotIn(secreto, json.dumps(t, ensure_ascii=False))
        self.assertEqual((t["texto"].split(" — ")[1], t["notas"].split(" · ")[0]), ("«oculto» lo pidió «oculto»", "lo dejó así «oculto»"))
        for cuenta in ("Claude (Diego)", "Claude (Cami)", "Codex"):
            self.assertEqual(self.del_panel(cuenta), cuenta)
        # Y los textos fijos del bloque no usan los términos que la página dejó de usar.
        visibles = "\n".join(re.findall(r'"([^"\n]{12,})"', self.bloque50) + re.findall(r"`([^`\n]{12,})`", self.bloque50))
        for viejo in ("próxima fase", "margen", "alcanza", "Total", "regla de"):
            self.assertNotIn(viejo, visibles, viejo)

    def test_el_bloque_de_pasado_muestra_lo_que_trae_el_panel_con_los_terminos_del_encargo(self):
        for texto in ('el("h2", {}, "Precisión del pronóstico")', 'el("strong", {}, "Aprobación en la 1ª revisión")', 'el("strong", {}, "Retrabajo")',
                      'el("strong", {}, "Error del pronóstico")', 'el("h3", {}, "Costo por naturaleza")', 'el("h3", {}, "Costo por modelo y esfuerzo")',
                      'el("h3", {}, `Experimento ${EXPERIMENTO}`)', 'const EXPERIMENTO = "esfuerzo-v1";',
                      'experimentos.some(f => f.nombre === EXPERIMENTO) ? null : el("p", {}, `${EXPERIMENTO}: 0 casos. Ningún encargo del historial lleva ese experimento en su manifiesto.`),',
                      'function lineaExperimento(f) { return `${delPanel(f.nombre)}: ${numPasado(f.encargos) ?? "sin datos"} casos · aprobados en la 1ª revisión ${primeraPasado(f)} · '
                      'retrabajo ${pctPasado(f.ret_min_pct)} de los minutos · error del pronóstico ${pctPasado(f.error_pct)}`; }',
                      'const nombrePasado = x => propio(BONITO, x) || delPanel(x);',
                      'if (!x) return el("section", { class: "tarjeta" }, cabeza, falta());'):
            self.assertIn(texto, self.bloque50, texto)
        # Va arriba de la pestaña Historial, también cuando el historial no se pudo leer.
        self.assertIn('if (!d.h) { p.replaceChildren(tarjetaPasado(), falta()); return; }', self.js)
        self.assertIn('dib(); p.replaceChildren(tarjetaPasado(), el("section", { class: "tarjeta" },', self.js)
        # Cada campo que la página lee existe en lo que publica el panel (con el historial de las fixtures)…
        self.cr.SIMULANDO = True
        self.cr.HISTORIAL = FIX / "historial.jsonl"
        self.manifiesto("cola-41.toml")
        pasado = self.cr.panel(vivos_dir=self.vivos, uso_de=self.uso_de, momento=self.reloj, viva=lambda n: False, manifiestos_dir=self.tmp, timers=[])["pasado"]
        cuerpo = self.bloque50[self.bloque50.index("// «Precisión del pronóstico»"):]
        usa = lambda nombre, desde, hasta: set(re.findall(rf"\b{nombre}\.(\w+)", cuerpo[cuerpo.index(desde):cuerpo.index(hasta)]))
        de_js = {"toLocaleString", "length", "filter", "map", "some", "join", "includes"}
        self.assertLessEqual(usa("f", "function filaFamilia", "function filaCombo") | usa("f", "function lineaExperimento", "function tarjetaPasado")
                             | usa("f", "const primeraPasado", "const filasPasado"), set(pasado["total"]))
        self.assertLessEqual(usa("c", "function filaCombo", "function lineaExperimento"), set(pasado["combos"][0]))
        en_tarjeta = cuerpo[cuerpo.index("function tarjetaPasado"):]
        self.assertLessEqual(set(re.findall(r"\bt\.(\w+)", en_tarjeta)) - de_js, set(pasado["total"]))
        self.assertLessEqual(set(re.findall(r"\bx\.(\w+)", en_tarjeta)) - de_js, set(pasado) | {"sin_manifiesto"})
        self.assertEqual({k for k in ("naturaleza", "combos", "experimento", "total", "primero", "ultimo", "saltadas", "sin_manifiesto", "ilegibles")
                          if f"x.{k}" in en_tarjeta}, {"naturaleza", "combos", "experimento", "total", "primero", "ultimo", "saltadas", "sin_manifiesto", "ilegibles"})
        # …la página no hace cuentas con ellos (ni sumas ni porcentajes): solo les da formato…
        sin_textos = self.tokens_js(cuerpo)
        self.assertIsNone(re.search(r"\b[fctx]\.\w+\s*[-+*/%]\s*[\w(]|[\w)]\s*[-+*/%]\s*[fctx]\.\w+|reduce\(|Math\.", sin_textos))
        # …y todo nombre que viene del historial o de un manifiesto pasa entero por la lista blanca.
        fuentes = [pasado]
        if HISTORIAL_REAL.is_file():
            bal = cargar_balance()
            filas, saltadas = bal.leer_historial(HISTORIAL_REAL)
            etapas, ilegibles = bal.leer_manifiestos(ENCARGOS)
            fuentes.append(bal.datos(filas, etapas, saltadas, ilegibles))
        for p in fuentes:
            nombres = {p["primero"], p["ultimo"]} | {f["nombre"] for k in ("naturaleza", "afinado", "experimento") for f in p[k]} \
                | {c[k] for c in p["combos"] for k in ("motor", "modelo", "esfuerzo", "rol")}
            self.assertGreater(len(nombres), 10)
            for n in nombres:
                self.assertEqual(self.del_panel(n), n)
        self.assertEqual(self.del_panel("sk-proj-Abc123Def456Ghi789Jkl012"), "«oculto»")      # y un nombre que no pasa no se muestra


if __name__ == "__main__":
    unittest.main()
