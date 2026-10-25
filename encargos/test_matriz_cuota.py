#!/usr/bin/env python3
"""Pruebas de la matriz de cuota de cola-run.py (encargo 46a).

    python3 encargos/test_matriz_cuota.py             # la suite
    python3 encargos/test_matriz_cuota.py --captura   # lo que publica --panel con las fixtures

Todo corre sobre `46-fixtures/` (la foto real del 11-10-2026 a las 18:55) y una carpeta temporal:
- los `vivo` son los que escribió cola-run.py ese día (cola41, cola42, cola43r y cola46 pausadas por cuota;
  cola47 detenida; cola44 esperando, sin sesión; cola46 corriendo a las 19:36) y los límites son el bloque
  `cuentas_interactivo[*].limites` de uso.json;
- el historial y modelos.toml son copias congeladas del mismo día, para que los números no cambien cuando
  el historial real crezca;
- los manifiestos son los de ese día (`46-fixtures/manifiestos/`, sacados de la foto de las 19:36 del
  historial git): los cola-NN.toml del vault siguen cambiando (el cola-43.toml se rearmó a las 19:50 como
  cola43s, en tres etapas). La prueba del escenario real sí arma una cola desde el `cola-43.toml` de hoy.
La carpeta de los vivos, el uso, la hora, las sesiones tmux, los timers y los manifiestos se inyectan. Ninguna
prueba lee ni escribe el `vivo/` real ni /opt/nodo/datos/uso.json, ninguna llama a tmux, a systemctl ni a
nodo-desplegar (`subprocess.run` está cerrado), y ninguna manda avisos.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import tomllib
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ENCARGOS = Path(__file__).resolve().parent
FIX = ENCARGOS / "46-fixtures"
MANIFIESTOS = FIX / "manifiestos"
MANIFIESTOS_1950 = FIX / "manifiestos-1950"     # los tres que otra sesión dejó en el vault mientras corría la 46a
PI = ENCARGOS.parent / "pi"
T = datetime.fromisoformat("2026-10-11T18:55:30-03:00")     # la hora de la foto
PARTE = T + timedelta(minutes=140)                          # 21:15:30: cuando el timer relanza la cola

# La salida real de `systemctl --user show <servicio> -p ExecStart --value` en la Pi, el 11-10-2026.
EXEC_ORDEN_CADENA = ('{ path=/bin/bash ; argv[]=/bin/bash -c tmux new-session -d -s orden-$(date +%d%H%M) "flock '
                     '$HOME/encargos-logs/.reanudar-orden.lock bash /opt/nodo/datos/srv/vault_personal/10-Proyectos/'
                     '11-Pi5/encargos/reanudar-en-orden.sh cola41 cola42 cola43r cola46" ; ignore_errors=no ; '
                     'start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }\n')
EXEC_COLA36 = ('{ path=/bin/bash ; argv[]=/bin/bash -c tmux has-session -t =cola36 2>/dev/null && exit 0; tmux '
               'new-session -d -s cola36 "python3 /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/'
               'cola-run.py /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/cola-36.toml --desde '
               '36:fix2 2>&1 | tee -a $HOME/encargos-logs/cola36.out" ; ignore_errors=no ; start_time=[n/a] ; '
               'stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }\n')
# El de `orden-renov.service`, leído igual el 11-10-2026 a las 21:54: la cadena que lanza las colas de los
# manifiestos de las 19:50 (cola49, cola50 y cola43s, que todavía no tenían vivo) y reanuda cola41 y cola42.
EXEC_ORDEN_RENOV = ('{ path=/bin/bash ; argv[]=/bin/bash -c tmux new-session -d -s orden-$(date +%d%H%M) "flock '
                    '$HOME/encargos-logs/.reanudar-orden.lock bash /opt/nodo/datos/srv/vault_personal/10-Proyectos/'
                    '11-Pi5/encargos/reanudar-en-orden.sh cola49 cola50 cola43s cola41 cola42" ; ignore_errors=no ; '
                    'start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }\n')
# `systemctl --user list-timers --all --output=json` del mismo día. Ese día ningún timer tenía un disparo
# pendiente (`next` null en los dos); la tercera fila es la primera con un `next` puesto a mano, con la
# misma unidad que trae `last` (microsegundos desde 1970).
LIST_TIMERS = ('[{"next":null,"left":null,"last":0,"passed":0,"unit":"cola36-reanudar.timer","activates":"cola36-reanudar.service"},'
               '{"next":null,"left":null,"last":1791570617089772,"passed":0,"unit":"pedidos-0910.timer","activates":"pedidos-0910.service"},'
               '{"next":1791764430000000,"left":8100000000,"last":0,"passed":0,"unit":"orden-2110.timer","activates":"orden-cadena.service"}]\n')

# El manifiesto de la cola46 tal como estaba el 11-10 (tres etapas), para las muestras de compatibilidad:
# va escrito acá porque el archivo real puede cambiar mientras la cola siga abierta.
MANIFIESTO_46 = '''
nombre = "cola46"
motivo = "Carga vs. capacidad"
esperar = []
despliegue = "pedir"
paciencia_h = 1
pruebas = []

[[etapa]]
id = "46a"
encargo = "46a-matriz-motor.md"
autor = "claude_cami"
revisor = "codex"
vueltas = 2
naturaleza = "bot"

[[etapa]]
id = "46b"
encargo = "46b-matriz-paginas.md"
autor = "claude_cami"
revisor = "codex"
vueltas = 2
naturaleza = "pagina"

[[etapa]]
id = "46c"
encargo = "46c-botones-de-cola.md"
autor = "claude_cami"
revisor = "codex"
vueltas = 2
naturaleza = "seguridad"
'''
CUENTAS = '''
[claude_diego]
nombre = "Claude (Diego)"
umbral_semanal = 75
umbral_5h = 90

[claude_cami]
nombre = "Claude (Cami)"
umbral_semanal = 75
umbral_5h = 90

[codex]
nombre = "Codex"
umbral_semanal = 75
umbral_5h = 90
'''
_N = 0


def iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def cargar(ruta: Path = ENCARGOS / "cola-run.py"):
    global _N
    _N += 1
    spec = importlib.util.spec_from_file_location(f"cola_run_matriz_{_N}", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def preparar(cr, tmp: Path, reloj) -> list:
    """Apunta el módulo a la carpeta temporal y a las fixtures. Devuelve la lista donde caería un aviso."""
    (tmp / "vivo").mkdir(exist_ok=True)
    (tmp / "cuentas.toml").write_text(CUENTAS, encoding="utf-8")
    cr.E = cr.D = cr.L = tmp
    cr.ESTADO = tmp / "COLA-ESTADO.md"
    cr.HISTORIAL, cr.MODELOS = FIX / "historial.jsonl", FIX / "modelos.toml"
    cr.REGISTROS = (tmp / "cuentas.toml",)
    cr.USO = tmp / "no-hay-uso.json"
    cr.SIMULANDO = False
    cr.ahora = reloj
    avisos: list = []
    cr.avisar = lambda *a, **k: avisos.append(a)
    cr.avisar_texto = lambda *a, **k: avisos.append(a)
    return avisos


def muestras_c5(cr, tmp: Path, uso_de) -> dict:
    """Lo que leen avisos.py y las páginas, y la decisión de pausar, para unas entradas fijas. Con el
    cola-run.py anterior al encargo 46a esta misma función escribió `46-fixtures/c5-antes.json`."""
    campos = ("proximo", "proximo_por_cuenta", "cuentas_en_uso", "eta", "restante_min")

    def publicado(man: dict, **cambios) -> dict:
        cr.MANIFIESTO = man
        cr.VIVO.clear()
        cr.vivo(nombre=man["nombre"], motivo=man["motivo"], estado="partiendo", lanzada=iso(T - timedelta(minutes=20)),
                etapas=[e["id"] for e in man["etapa"]], inicio_trabajo=iso(T - timedelta(minutes=20)))
        cr.vivo(**cambios)
        v = json.loads((tmp / "vivo" / f"{man['nombre']}.json").read_text(encoding="utf-8"))
        return {k: v.get(k) for k in campos}

    m46 = tomllib.loads(MANIFIESTO_46)
    m43 = tomllib.loads((MANIFIESTOS / "cola-43.toml").read_text(encoding="utf-8"))
    for man in (m46, m43):
        cr.repartir(man["etapa"])
    out = {"vivo": {
        "corriendo 46a:autor": publicado(m46, estado="corriendo", etapa="46a", fase="autor", inicio_fase=iso(T)),
        "corriendo 46b:rev2, 4 min": publicado(m46, estado="corriendo", etapa="46b", fase="rev2",
                                               inicio_fase=iso(T - timedelta(minutes=4))),
        "esperando_cuota 46a:fix1": publicado(m46, estado="esperando_cuota", etapa="46a", fase="fix1",
                                              reanuda=iso(T + timedelta(minutes=90)), espera_desde=iso(T)),
        "corriendo 43:rev3": publicado(m43, estado="corriendo", etapa="43", fase="rev3", inicio_fase=iso(T)),
        "partiendo 43": publicado(m43),
    }}
    cr.MANIFIESTO = m46
    out["uso_de_cuentas"] = {f"{et}:{fase} actual={inc}": cr.uso_de_cuentas(et, fase, incluye_actual=inc)
                             for et, fase, inc in (("46a", "autor", True), ("46a", "rev1", False), ("46c", "rev3", False))}
    out["restante"] = {f"{et}:{fase} {tr}": cr.restante(m46["etapa"], et, fase, tr)
                       for et, fase, tr in (("46a", "autor", 0), ("46b", "fix1", 2.5), ("46c", "rev3", 99))}
    out["ventanas"], out["decision"] = {}, {}
    out["borde"] = {str(a): cr._alcanza({"actual": a, "pronostico": 25.0, "tope": 90}) for a in (64.9, 65.0, 65.1)}
    cr.medir = lambda cid: dict(uso_de(cid), fuente="fresco")
    for cid, rol in (("claude_cami", "autor"), ("claude_cami", "rev"), ("claude_diego", "autor"), ("codex", "rev"), ("codex", "fix")):
        mod = cr.modelo_de(m46["etapa"][0] | {"autor": cid, "revisor": cid}, rol)
        modelo = mod["modelo"]
        ventanas = cr.ventanas_cuota(cid, cr.pronostico(cid, rol, modelo, "", mod["esfuerzo"]), uso_de(cid))
        out["ventanas"][f"{cid} {rol}"] = [dict(w, renueva=iso(w["renueva"]) if w["renueva"] else None, alcanza=cr._alcanza(w))
                                           for w in ventanas]
        try:
            cr.chequear_cuota(cid, rol, "46a:" + rol, modelo, mod["esfuerzo"])
            out["decision"][f"{cid} {rol}"] = "sigue"
        except cr.Pausa as p:
            out["decision"][f"{cid} {rol}"] = f"pausa: {p.motivo}"
    return json.loads(json.dumps(out, ensure_ascii=False))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="matriz-cuota-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cr = cargar()
        self.reloj = T
        self.avisos = preparar(self.cr, self.tmp, lambda: self.reloj)
        self.vivos = self.tmp / "vivo"
        self.vivas: set[str] = set()
        self.timers: list = []
        self.uso_ruta = FIX / "uso-limites.json"

        def cerrado(cmd, *a, **k):
            raise AssertionError(f"la prueba no puede lanzar procesos: {cmd}")
        self.cr.subprocess = type("SinProcesos", (), {"run": staticmethod(cerrado), "CompletedProcess": object,
                                                      "SubprocessError": Exception, "DEVNULL": None})
        self.addCleanup(lambda: self.assertEqual(self.avisos, [], "ninguna prueba manda avisos"))

    def poner(self, fixture: str, **cambios) -> dict:
        """Copia un vivo de las fixtures a la carpeta temporal, como <nombre>.json."""
        v = json.loads((FIX / fixture).read_text(encoding="utf-8")) | cambios
        (self.vivos / f"{v['nombre']}.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
        return v

    def limites(self, **por_cuenta) -> None:
        """Una copia de uso-limites.json con cambios: limites(codex={"ventana_5h": {...}, "momento": "..."})."""
        d = json.loads((FIX / "uso-limites.json").read_text(encoding="utf-8"))
        for cid, cambios in por_cuenta.items():
            lim = d["cuentas_interactivo"][cid]["limites"]
            for k, val in cambios.items():
                lim[k] = lim[k] | val if isinstance(val, dict) else val
        self.uso_ruta = self.tmp / "uso.json"
        self.uso_ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

    def uso_de(self, cid: str) -> dict:
        return self.cr.uso(cid, self.uso_ruta, self.reloj)       # el uso() real sobre la forma real

    def entradas(self) -> dict:
        return {"vivos_dir": self.vivos, "uso_de": self.uso_de, "momento": self.reloj,
                "viva": lambda nom: nom in self.vivas, "timers": self.timers, "manifiestos_dir": MANIFIESTOS}

    def matriz(self) -> dict:
        return self.cr.matriz_cuota(**self.entradas())

    def regla(self, cid: str, matriz: dict | None = None) -> dict:
        return next(r for r in (matriz or self.matriz())["reglas"] if r["cuenta"] == cid)

    def ventana(self, regla: dict, cual: str) -> dict:
        return next(w for w in regla["ventanas"] if w["ventana"] == cual)

    def timer_para(self, *colas: str, cuando: datetime = PARTE) -> None:
        """Un timer de usuario que relanza esas colas: el ExecStart real de cola36-reanudar.service, con el nombre cambiado."""
        self.timers += [(cuando, EXEC_COLA36.replace("cola36", c).replace("cola-36.toml", f"cola-{c[4:]}.toml")) for c in colas]

    def a_mano(self, inicio: datetime, cuenta: str, etapas: list[dict]) -> list[tuple[datetime, float, dict]]:
        """(inicio, probabilidad, pronóstico) de las fases de `cuenta` en una cola que parte en `inicio` desde el
        autor de su primera etapa. Escrito a mano, sin `fases_restantes()` ni `fases_pendientes()`: por etapa, el
        autor, y por cada vuelta una revisión y un arreglo, más la revisión final; cada revisión rechaza con p,
        así que a la vuelta n se llega con p**n, y cada etapa vuelve a partir en 1."""
        p = self.cr.prob_rechazo()
        out, avance = [], 0.0
        for et in etapas:
            vueltas = int(et.get("vueltas", 2))
            tabla = [("autor", et["autor"], 1.0)]
            for n in range(vueltas + 1):
                tabla.append(("rev", et["revisor"], p ** n))
                if n < vueltas:
                    tabla.append(("fix", et["autor"], p ** (n + 1)))
            for rol, cid, prob in tabla:
                mod = self.cr.modelo_de(et, rol)
                f = self.cr.pronostico(cid, rol, mod["modelo"], "", mod["esfuerzo"])
                # La matriz reserva margen con p75; la ETA que construye `avance` sigue siendo mediana.
                f = dict(f, pct_5h=f["pct_5h_p75"], pct_sem=f["pct_sem_p75"])
                if cid == cuenta:
                    out.append((inicio + timedelta(minutes=avance), prob, f))
                avance += prob * f["min"]
        return out


class C1Suma(Base):
    def test_dos_colas_activas_sobre_la_misma_cuenta_solas_alcanzan_y_juntas_no(self):
        # Los vivo reales de cola43r (escribe Claude (Cami)) y cola42 (revisa Claude (Cami)), pausadas por cuota.
        self.poner("vivo-cola43r.json")
        self.poner("vivo-cola42.json")
        lejos = {"ventana_5h": {"usado_pct": 0, "renueva": iso(T + timedelta(hours=8))},
                 "semanal": {"usado_pct": 0, "renueva": iso(T + timedelta(days=5))}}
        self.limites(claude_cami=lejos, codex=lejos)
        self.timer_para("cola43r")
        sola_43 = self.ventana(self.regla("claude_cami"), "semanal")["pronostico"]
        self.timers.clear()
        self.timer_para("cola42")
        sola_42 = self.ventana(self.regla("claude_cami"), "semanal")["pronostico"]
        self.assertGreater(min(sola_43, sola_42), 1)
        # Un uso semanal al que cada una le cabe sola y las dos juntas no (tope 75 %).
        margen = max(sola_43, sola_42) + min(sola_43, sola_42) / 2
        self.limites(claude_cami=lejos | {"semanal": {"usado_pct": 75 - margen, "renueva": iso(T + timedelta(days=5))}}, codex=lejos)
        for cola, pct in (("cola42", sola_42), ("cola43r", sola_43)):
            self.timers.clear()
            self.timer_para(cola)
            r = self.regla("claude_cami")
            self.assertEqual((r["colas"], r["alcanza"]), ([cola], True), r["texto"])
            self.assertEqual(self.ventana(r, "semanal")["pronostico"], pct)
        self.timers.clear()
        self.timer_para("cola42", "cola43r")
        r = self.regla("claude_cami")
        self.assertEqual(r["colas"], ["cola42", "cola43r"])
        self.assertIs(r["alcanza"], False, r["texto"])
        sem = self.ventana(r, "semanal")
        self.assertAlmostEqual(sem["pronostico"], sola_42 + sola_43, delta=0.11)
        self.assertGreater(sem["actual"] + sem["pronostico"], sem["tope"])
        self.assertFalse(sem["alcanza"])
        self.assertTrue(self.ventana(r, "5h")["alcanza"])
        self.assertAlmostEqual(sum(c["pct_sem"] for c in r["celdas"].values()), sem["pronostico"], delta=0.11)
        self.assertIn("Claude (Cami) (cola42, cola43r): 5 h ahora 0 % + ", r["texto"])
        self.assertRegex(r["texto"], r" · sem ahora [\d,]+ % \+ [\d,]+ % = [\d,]+ % > tope 75 %: no alcanza$")

    def test_el_timer_real_de_la_cadena_activa_las_cuatro_y_cada_celda_es_lo_de_su_cola(self):
        for f in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola46.json"):
            self.poner(f)
        self.timers = [(PARTE, EXEC_ORDEN_CADENA)]
        m = self.matriz()
        cami = self.regla("claude_cami", m)
        # cola46 está en el timer, pero su vivo pide la etapa «46» y el manifiesto de hoy trae 46a, 46b y 46c:
        # no hay plan que sumar, y la suma de todas sale débil por eso.
        self.assertEqual(cami["colas"], ["cola41", "cola42", "cola43r"])
        self.assertTrue(cami["debil"])
        self.assertEqual(m["colas_fuera"], [])
        for k in ("pct_5h", "pct_sem"):
            ventana = self.ventana(cami, "5h" if k == "pct_5h" else "semanal")
            self.assertAlmostEqual(sum(c[k] for c in cami["celdas"].values()), ventana["pronostico"], delta=0.16)
        # Cada celda es lo que da esa cola sola.
        self.timers = []
        self.timer_para("cola41")
        self.assertEqual(self.regla("claude_cami")["celdas"]["cola41"], cami["celdas"]["cola41"])


class C2Renovacion(Base):
    def setUp(self):
        super().setUp()
        self.poner("vivo-cola43r.json")       # escribe Claude (Cami), revisa Codex; parte a las 21:15:30
        self.timer_para("cola43r")
        self.etapa = tomllib.loads((MANIFIESTOS / "cola-43.toml").read_text(encoding="utf-8"))["etapa"][0]
        self.revs = self.a_mano(PARTE, "codex", [self.etapa])      # rev1, rev2, rev3
        self.assertEqual([round(p, 4) for _, p, _ in self.revs], [1.0, self.cr.prob_rechazo(), round(self.cr.prob_rechazo() ** 2, 4)])

    def codex(self, ren_5h: datetime, ren_sem: datetime) -> dict:
        self.limites(codex={"ventana_5h": {"usado_pct": 69.0, "renueva": iso(ren_5h)},
                            "semanal": {"usado_pct": 11.0, "renueva": iso(ren_sem)}})
        return self.regla("codex")

    def test_la_fase_que_parte_despues_de_la_renovacion_de_5h_va_a_la_proxima_y_la_semanal_si_suma(self):
        # La ventana de 5 h de Codex se renueva un minuto antes de que parta su primera revisión.
        r = self.codex(self.revs[0][0] - timedelta(minutes=1), T + timedelta(days=5))
        todo_5h = sum(p * f["pct_5h"] for _, p, f in self.revs)
        todo_sem = sum(p * f["pct_sem"] for _, p, f in self.revs)
        celda = r["celdas"]["cola43r"]
        self.assertEqual((celda["pct_5h"], celda["pct_5h_min"], celda["pct_5h_max"]), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(celda["proxima_5h"], todo_5h, delta=0.06)
        self.assertAlmostEqual(r["proxima_5h"], todo_5h, delta=0.06)
        self.assertEqual(self.ventana(r, "5h"), {"ventana": "5h", "actual": 69.0, "pronostico": 0.0, "tope": 90, "alcanza": True})
        self.assertAlmostEqual(self.ventana(r, "semanal")["pronostico"], todo_sem, delta=0.06)
        self.assertGreater(todo_sem, 0)
        self.assertIn(f"↻ {self.cr.num_es(r['proxima_5h'])} % en la próxima ventana", r["texto"])
        self.assertEqual(r["renueva_5h"], iso(self.revs[0][0] - timedelta(minutes=1)))

    def test_la_renovacion_entre_dos_fases_parte_la_suma_y_el_rango_cuenta_solo_lo_seguro(self):
        # Se renueva medio minuto después de que parte la rev1: la rev1 cuenta ahora; la rev2 y la rev3, después.
        r = self.codex(self.revs[0][0] + timedelta(seconds=30), T + timedelta(days=5))
        (_, _, f1), (_, p2, f2), (_, p3, f3) = self.revs
        celda = r["celdas"]["cola43r"]
        self.assertEqual((celda["pct_5h"], celda["pct_5h_min"], celda["pct_5h_max"]), (f1["pct_5h"], f1["pct_5h"], f1["pct_5h"]))
        self.assertAlmostEqual(celda["proxima_5h"], p2 * f2["pct_5h"] + p3 * f3["pct_5h"], delta=0.06)
        # La semana entera: el mínimo es solo la fase segura (prob 1) y el máximo, todas las vueltas.
        self.assertEqual(celda["pct_sem_min"], f1["pct_sem"])
        self.assertAlmostEqual(celda["pct_sem_max"], f1["pct_sem"] + f2["pct_sem"] + f3["pct_sem"], delta=0.06)
        self.assertNotIn("↻ 0 %", r["texto"])

    def test_la_fase_que_parte_despues_de_la_renovacion_semanal_no_suma_a_la_semana(self):
        # La semana de Codex se renueva antes de su primera revisión: nada de la cola cae en esta semana.
        r = self.codex(T + timedelta(hours=8), self.revs[0][0] - timedelta(minutes=1))
        self.assertEqual(self.ventana(r, "semanal")["pronostico"], 0.0)
        self.assertEqual([r["celdas"]["cola43r"][k] for k in ("pct_sem", "pct_sem_min", "pct_sem_max")], [0.0, 0.0, 0.0])
        self.assertAlmostEqual(self.ventana(r, "5h")["pronostico"], sum(p * f["pct_5h"] for _, p, f in self.revs), delta=0.06)
        self.assertEqual(r["proxima_5h"], 0.0)
        # Y si se renueva después de la rev1 y antes de la rev2, suma solo la rev1.
        r = self.codex(T + timedelta(hours=8), self.revs[1][0] - timedelta(seconds=30))
        self.assertEqual(self.ventana(r, "semanal")["pronostico"], self.revs[0][2]["pct_sem"])

    def test_sin_hora_de_renovacion_todo_cuenta_ahora_y_la_cuenta_sale_debil(self):
        self.limites(codex={"ventana_5h": {"usado_pct": 69.0, "renueva": None}})
        r = self.regla("codex")
        self.assertTrue(r["debil"])
        self.assertIsNone(r["renueva_5h"])
        self.assertEqual(r["proxima_5h"], 0.0)
        self.assertAlmostEqual(self.ventana(r, "5h")["pronostico"], sum(p * f["pct_5h"] for _, p, f in self.revs), delta=0.06)


class C3EnEspera(Base):
    def setUp(self):
        super().setUp()
        cr = self.cr
        cr.MANIFIESTO = tomllib.loads((MANIFIESTOS / "cola-43.toml").read_text(encoding="utf-8"))   # cola43r, esperar = ["cola44"]
        cr.MANIFIESTO["pruebas"] = []
        cr.repartir(cr.MANIFIESTO["etapa"])
        cr.PARTIDA = ("43", "autor")
        cr.VIVO.clear()
        cr.vivo(nombre="cola43r", motivo=cr.MANIFIESTO["motivo"], estado="partiendo", lanzada=iso(T), etapas=["43"])

    def propio(self) -> dict:
        return json.loads((self.vivos / "cola43r.json").read_text(encoding="utf-8"))

    def esperar(self, vueltas: int, al_dormir) -> list[dict]:
        """Corre la espera real con una sesión que vive `vueltas` vueltas. Devuelve el vivo propio tal como
        estaba en el archivo al empezar cada vuelta (antes de dormir) y al terminar."""
        vistos, fotos = [0], []

        def viva(nom):
            self.assertEqual(nom, "cola44")
            vistos[0] += 1
            return vistos[0] <= vueltas + 1      # la primera consulta es la de antes de entrar

        def dormir(segundos):
            self.assertEqual(segundos, 60)
            fotos.append(self.propio())
            self.reloj += timedelta(seconds=segundos)
            al_dormir(len(fotos))
        self.cr.esperar_sesion("cola44", viva=viva, dormir=dormir)
        return fotos + [self.propio()]

    def test_publica_las_fases_desde_el_fin_esperado_de_la_otra_y_lo_refresca_en_cada_vuelta(self):
        # La otra: el vivo real de una cola corriendo (el de la cola46 del 11-10, 19:36), con el nombre que se espera.
        otra = self.poner("vivo-cola46-corriendo.json", nombre="cola44")
        self.assertEqual(otra["eta"]["esperado"], "2026-10-11T21:45-03:00")
        ruta_otra = self.vivos / "cola44.json"

        def al_dormir(vuelta):
            if vuelta == 1:      # la otra avanzó: ahora termina 40 min más tarde
                ruta_otra.write_text(json.dumps(otra | {"eta": otra["eta"] | {"esperado": "2026-10-11T22:25-03:00"}}), encoding="utf-8")
            if vuelta == 2:      # y después la pillamos a medio escribir
                ruta_otra.write_text(json.dumps(otra)[:300], encoding="utf-8")
        antes, vuelta1, vuelta2 = self.esperar(2, al_dormir)

        # Antes de entrar al bucle ya está publicado, en `esperando` y con las seis fases de la etapa.
        self.assertEqual((antes["estado"], antes["esperando"]), ("esperando", "cola44"))
        fases = antes["fases_restantes"]
        self.assertEqual([(f["etapa"], f["fase"], f["rol"], f["cuenta"]) for f in fases],
                         [("43", "autor", "autor", "claude_cami"), ("43", "rev1", "rev", "codex"), ("43", "fix1", "fix", "claude_cami"),
                          ("43", "rev2", "rev", "codex"), ("43", "fix2", "fix", "claude_cami"), ("43", "rev3", "rev", "codex")])
        self.assertEqual(set(fases[0]), {"etapa", "fase", "rol", "cuenta", "modelo", "min", "pct_5h", "pct_sem", "prob", "inicio_esperado", "debil"})
        fin_otra = datetime.fromisoformat("2026-10-11T21:45-03:00")
        self.assertEqual(datetime.fromisoformat(fases[0]["inicio_esperado"]), fin_otra)
        self.assertTrue(all(datetime.fromisoformat(f["inicio_esperado"]) >= fin_otra for f in fases))
        # Los números son los de pronostico() y la probabilidad, la de la ETA esperada.
        p = self.cr.prob_rechazo()
        self.assertEqual([f["prob"] for f in fases], [1.0, 1.0, p, p, round(p * p, 4), round(p * p, 4)])
        mod = self.cr.modelo_de(self.cr.MANIFIESTO["etapa"][0], "autor")
        autor = self.cr.pronostico("claude_cami", "autor", fases[0]["modelo"], "", mod["esfuerzo"])
        self.assertEqual((fases[0]["min"], fases[0]["pct_5h"], fases[0]["pct_sem"]),
                         (autor["min"], autor["pct_5h_p75"], autor["pct_sem_p75"]))
        self.assertEqual(datetime.fromisoformat(fases[1]["inicio_esperado"]), fin_otra + timedelta(minutes=autor["min"]))
        self.assertFalse(any(f["debil"] and not self.cr.pronostico(f["cuenta"], f["rol"], f["modelo"], "",
                                                                  self.cr.modelo_de(cr.MANIFIESTO["etapa"][0], f["rol"])["esfuerzo"])["debil"] for f in fases))

        # Vuelta 1: la otra corrió su fin y el vivo propio lo siguió.
        self.assertEqual(datetime.fromisoformat(vuelta1["fases_restantes"][0]["inicio_esperado"]),
                         datetime.fromisoformat("2026-10-11T22:25-03:00"))
        self.assertGreater(vuelta1["escrito"], antes["escrito"])
        # Vuelta 2: el vivo de la otra estaba a medias. No se cae: «ahora» y débil.
        self.assertEqual(datetime.fromisoformat(vuelta2["fases_restantes"][0]["inicio_esperado"]), self.reloj)
        self.assertTrue(all(f["debil"] for f in vuelta2["fases_restantes"]))
        self.assertEqual(self.reloj, T + timedelta(seconds=120))

    def test_si_la_otra_tambien_espera_se_encadena_con_el_fin_de_sus_fases(self):
        # La otra no corre todavía (no tiene `eta`): publica `fases_restantes` y de ahí sale su fin.
        m41 = tomllib.loads((MANIFIESTOS / "cola-41.toml").read_text(encoding="utf-8"))
        parte_otra = T + timedelta(minutes=50)
        sus_fases = self.cr.fases_restantes(m41["etapa"], "41", "rev3", parte_otra)
        self.assertEqual(len(sus_fases), 1)
        self.poner("vivo-cola44-esperando.json", fases_restantes=sus_fases)
        fotos = self.esperar(1, lambda vuelta: None)
        fin_otra = parte_otra + timedelta(minutes=sus_fases[0]["min"] + 1)       # su única fase más el minuto de pruebas
        for foto in fotos:
            self.assertEqual(datetime.fromisoformat(foto["fases_restantes"][0]["inicio_esperado"]), fin_otra.replace(microsecond=0))

    def test_sin_vivo_de_la_otra_o_con_un_nombre_que_no_es_de_cola_parte_ahora_y_debil(self):
        fotos = self.esperar(1, lambda vuelta: None)        # «cola44» no tiene vivo: era otra sesión tmux
        self.assertEqual(datetime.fromisoformat(fotos[0]["fases_restantes"][0]["inicio_esperado"]), T)
        self.assertTrue(all(f["debil"] for f in fotos[0]["fases_restantes"]))
        (self.tmp / "secreto.json").write_text(json.dumps({"estado": "corriendo", "eta": {"esperado": "2026-10-12T09:00-03:00"}}), encoding="utf-8")
        inicio, debil = self.cr._inicio_tras_espera("../secreto", T, self.vivos)      # no sale de la carpeta de los vivos
        self.assertEqual((inicio, debil), (T, True))

    def test_el_vivo_de_la_otra_que_es_un_enlace_hacia_fuera_no_se_lee(self):
        # 46ar1, hallazgo 1, en el otro lector de vivos: el de la cola a la que se espera.
        afuera = self.tmp / "afuera-de-vivo.json"
        v = json.loads((FIX / "vivo-cola46-corriendo.json").read_text(encoding="utf-8")) | {"nombre": "cola44"}
        afuera.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
        fin_de_afuera = datetime.fromisoformat(v["eta"]["esperado"])
        self.assertGreater(fin_de_afuera, T)
        (self.vivos / "cola44.json").symlink_to(afuera)
        self.assertEqual(self.cr._inicio_tras_espera("cola44", T, self.vivos), (T, True))
        fotos = self.esperar(1, lambda vuelta: None)
        self.assertEqual(datetime.fromisoformat(fotos[0]["fases_restantes"][0]["inicio_esperado"]), T)
        self.assertTrue(all(f["debil"] for f in fotos[0]["fases_restantes"]))
        # Control: el mismo contenido como archivo corriente sí da su fin. Lo único que cambia es el enlace.
        (self.vivos / "cola44.json").unlink()
        shutil.copyfile(afuera, self.vivos / "cola44.json")
        self.assertEqual(self.cr._inicio_tras_espera("cola44", T, self.vivos), (fin_de_afuera, False))

    def test_la_cola_en_espera_cuenta_en_la_matriz_con_lo_que_publica(self):
        self.poner("vivo-cola46-corriendo.json", nombre="cola44")
        self.esperar(1, lambda vuelta: None)
        (self.vivos / "cola44.json").unlink()
        self.vivas = {"cola43r"}
        self.reloj = T + timedelta(minutes=5)
        r = self.regla("claude_cami")
        self.assertEqual(r["colas"], ["cola43r"])
        cami = [f for f in self.propio()["fases_restantes"] if f["cuenta"] == "claude_cami"]
        # Parte a las 21:45: antes de la renovación de 5 h (21:49:59) y de la semanal (21:59:59) de Claude (Cami).
        self.assertEqual(r["celdas"]["cola43r"]["pct_5h_min"], cami[0]["pct_5h"])
        self.assertEqual(r["celdas"]["cola43r"]["pct_sem_min"], cami[0]["pct_sem"])
        self.assertAlmostEqual(r["proxima_5h"], sum(f["prob"] * f["pct_5h"] for f in cami[1:]), delta=0.06)


class C4FueraDeLaSuma(Base):
    def test_las_fixtures_solas_no_suman_nada_y_salen_en_colas_fuera_con_sus_fases(self):
        for f in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola46.json"):
            self.poner(f)
        m = self.matriz()       # ninguna tiene `reanuda` ni timer
        self.assertEqual(m["reglas"], [])
        fuera = {f["cola"]: f for f in m["colas_fuera"]}
        self.assertEqual(list(fuera), ["cola41", "cola42", "cola43r", "cola46"])
        self.assertEqual({f["estado"] for f in fuera.values()}, {"pausada_sin_timer"})
        self.assertEqual(set(fuera["cola41"]), {"cola", "estado", "motivo", "fase", "fases_restantes", "debil"})
        self.assertEqual(fuera["cola41"]["motivo"], "Claude (Cami) sin margen para rev: semanal 75 % + 2.0 % > tope 75 %")
        self.assertEqual({c: f["fase"] for c, f in fuera.items()}, {"cola41": "41:rev3", "cola42": "42:rev1", "cola43r": "43:autor", "cola46": "46:autor"})
        fases = lambda c: [(f["fase"], f["cuenta"]) for f in fuera[c]["fases_restantes"]]
        self.assertEqual(fases("cola41"), [("rev3", "claude_cami")])
        self.assertEqual(fases("cola42"), [("rev1", "claude_cami"), ("fix1", "codex"), ("rev2", "claude_cami"), ("fix2", "codex"), ("rev3", "claude_cami")])
        self.assertEqual(fases("cola43r"), [("autor", "claude_cami"), ("rev1", "codex"), ("fix1", "claude_cami"), ("rev2", "codex"), ("fix2", "claude_cami"), ("rev3", "codex")])
        # Misma forma que las activas, y como si se reanudara ahora.
        f = fuera["cola43r"]["fases_restantes"][0]
        self.assertEqual(set(f), {"etapa", "fase", "rol", "cuenta", "modelo", "min", "pct_5h", "pct_sem", "prob", "inicio_esperado", "debil"})
        self.assertEqual(datetime.fromisoformat(f["inicio_esperado"]), T)
        self.assertFalse(fuera["cola43r"]["debil"])
        # La cola46 quedó pausada pidiendo la etapa «46», y su manifiesto se rearmó después en 46a, 46b y 46c:
        # sale igual, sin fases que proyectar y marcada.
        self.assertEqual((fuera["cola46"]["fases_restantes"], fuera["cola46"]["debil"]), ([], True))
        self.assertIn("no se pudo proyectar: la etapa 46 no está en el manifiesto", fuera["cola46"]["motivo"])

    def test_detenidas_y_pausadas_sin_timer_no_cambian_ningun_numero_de_reglas(self):
        self.reloj = datetime.fromisoformat("2026-10-11T19:40:00-03:00")
        self.poner("vivo-cola46-corriendo.json")        # la única que corre sola
        self.vivas = {"cola46"}
        sola = self.matriz()
        self.assertEqual([r["cuenta"] for r in sola["reglas"]], ["claude_cami", "codex"])
        self.assertEqual(sola["colas_fuera"], [])
        for f in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola47-detenida.json", "vivo-cola44-esperando.json"):
            self.poner(f)
        con_todas = self.matriz()
        self.assertEqual(con_todas["reglas"], sola["reglas"])
        self.assertEqual([r["colas"] for r in con_todas["reglas"]], [["cola46"], ["cola46"]])
        fuera = {f["cola"]: f for f in con_todas["colas_fuera"]}
        self.assertEqual({c: f["estado"] for c, f in fuera.items()},
                         {"cola41": "pausada_sin_timer", "cola42": "pausada_sin_timer", "cola43r": "pausada_sin_timer",
                          "cola44": "detenida", "cola47": "detenida"})
        # cola44 quedó «esperando» el 10-10 y ya no tiene sesión: si se relanza, parte desde el principio.
        self.assertEqual(fuera["cola44"]["motivo"], "sin sesión y sin señal desde el 10-10 22:36 (quedó en «esperando»)")
        self.assertEqual((fuera["cola44"]["fase"], len(fuera["cola44"]["fases_restantes"])), ("44:autor", 6))
        # cola47 agotó sus vueltas: desde dónde sigue lo decide una persona, así que no hay fases que proyectar.
        self.assertEqual((fuera["cola47"]["fase"], fuera["cola47"]["fases_restantes"], fuera["cola47"]["debil"]), (None, [], False))
        self.assertEqual(fuera["cola47"]["motivo"], "una etapa quedó NO DESPLEGABLE o fallaron las pruebas finales")

    def test_los_manifiestos_que_dejo_otra_sesion_a_las_19_50_no_cambian_ningun_numero_de_reglas(self):
        """Revisión 2: el diff de la 46a traía además el `cola-43.toml` rearmado (cola43r pasó a ser cola43s, en
        tres etapas y sin `esperar`) y los `cola-49.toml` y `cola-50.toml` nuevos, que dejó otra sesión a las
        19:50. Con esos tres archivos tal como quedaron, los vivos reales de ese rato y el timer real que los
        lanza, la matriz da las mismas `reglas` que con los manifiestos de la foto de las 19:36."""
        cr = self.cr
        con_ajenos = self.tmp / "manifiestos-con-ajenos"
        shutil.copytree(MANIFIESTOS, con_ajenos)
        for ruta in sorted(MANIFIESTOS_1950.glob("cola-*.toml")):
            shutil.copy(ruta, con_ajenos / ruta.name)       # pisa el cola-43.toml y agrega el 49 y el 50
        antes, despues = cr.manifiestos_por_cola(MANIFIESTOS), cr.manifiestos_por_cola(con_ajenos)
        # Control: los tres se leen y dicen lo que la revisión describe.
        self.assertEqual(sorted(set(despues) - set(antes)), ["cola43s", "cola49", "cola50"])
        self.assertEqual(sorted(set(antes) - set(despues)), ["cola43r"])
        self.assertEqual((antes["cola43r"]["esperar"], [e["id"] for e in antes["cola43r"]["etapa"]]), (["cola44"], ["43"]))
        self.assertEqual((despues["cola43s"]["esperar"], [e["id"] for e in despues["cola43s"]["etapa"]]), ([], ["43a", "43b", "43c"]))
        self.assertEqual({c: antes[c] for c in ("cola41", "cola42", "cola44", "cola46")},
                         {c: despues[c] for c in ("cola41", "cola42", "cola44", "cola46")})

        self.reloj = datetime.fromisoformat("2026-10-11T19:57:00-03:00")
        self.poner("vivo-cola46-corriendo.json")
        for f in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json"):
            self.poner(f)
        self.vivas = {"cola46"}
        self.timers = [(datetime.fromisoformat("2026-10-11T22:05:00-03:00"), EXEC_ORDEN_RENOV)]
        m_antes = self.matriz()
        m_despues = cr.matriz_cuota(**self.entradas() | {"manifiestos_dir": con_ajenos})
        self.assertEqual([r["colas"] for r in m_antes["reglas"]], [["cola41", "cola42", "cola46"], ["cola42", "cola46"]])
        self.assertTrue(all(w["pronostico"] > 0 for r in m_antes["reglas"] for w in r["ventanas"] if w["ventana"] == "semanal"))
        self.assertEqual(m_despues["reglas"], m_antes["reglas"])        # entero: números, celdas, texto y `debil`
        self.assertEqual(m_despues["cuentas"], m_antes["cuentas"])
        # Las colas de los manifiestos nuevos no tienen vivo: no entran a la suma ni a `colas_fuera`.
        for m in (m_antes, m_despues):
            nombradas = {c for r in m["reglas"] for c in r["colas"]} | {f["cola"] for f in m["colas_fuera"]}
            self.assertEqual(nombradas, {"cola41", "cola42", "cola43r", "cola46"})
        # Lo único que cambia es la proyección de la cola43r, que ya estaba fuera de la suma: quedó sin manifiesto.
        f_antes, f_despues = m_antes["colas_fuera"], m_despues["colas_fuera"]
        self.assertEqual([(f["cola"], f["estado"], f["fase"]) for f in f_antes], [("cola43r", "pausada_sin_timer", "43:autor")])
        self.assertEqual([(f["cola"], f["estado"], f["fase"]) for f in f_despues], [("cola43r", "pausada_sin_timer", "43:autor")])
        self.assertEqual((len(f_antes[0]["fases_restantes"]), f_antes[0]["debil"]), (6, False))
        self.assertEqual((f_despues[0]["fases_restantes"], f_despues[0]["debil"]), ([], True))
        self.assertEqual(f_despues[0]["motivo"], f_antes[0]["motivo"] + " (no se pudo proyectar: no se encontró su manifiesto)")

    def test_que_hace_contar_a_una_pausada_y_que_no(self):
        self.poner("vivo-cola43r.json")
        estado = lambda: ([r["colas"] for r in self.matriz()["reglas"]], [f["estado"] for f in self.matriz()["colas_fuera"]])
        self.assertEqual(estado(), ([], ["pausada_sin_timer"]))
        # Un timer que nombra a otra cola (cola43, sin la r) no la activa.
        self.timers = [(PARTE, EXEC_COLA36.replace("cola36", "cola43"))]
        self.assertEqual(estado(), ([], ["pausada_sin_timer"]))
        self.timer_para("cola43r")
        self.assertEqual(estado(), ([["cola43r"], ["cola43r"]], []))
        # `reanuda` en su vivo, sin timer.
        self.timers = []
        self.poner("vivo-cola43r.json", reanuda=iso(PARTE))
        self.assertEqual(estado(), ([["cola43r"], ["cola43r"]], []))
        # Una reanudación que ya pasó no reanudó nada.
        self.poner("vivo-cola43r.json", reanuda=iso(T - timedelta(hours=1)))
        self.assertEqual(estado(), ([], ["pausada_sin_timer"]))
        # Una pausa que no es por cuota no cuenta ni con timer: la decide el usuario.
        self.timer_para("cola43r")
        self.poner("vivo-cola43r.json", motivo_pausa="claude-fable-5-1 pide autorización y no se dio. Cambia el nivel o fija otro modelo, y reanuda")
        self.assertEqual(estado(), ([], ["pausada_sin_timer"]))

    def test_una_cola_que_espera_tu_autorizacion_esta_en_candado_y_una_terminada_no_se_publica(self):
        self.poner("vivo-cola44-esperando.json", estado="esperando autorización", candado=["claude-fable-5-1"], escrito=iso(T))
        self.poner("vivo-cola47-detenida.json", estado="terminada")
        m = self.matriz()
        self.assertEqual(m["reglas"], [])
        self.assertEqual([(f["cola"], f["estado"], f["motivo"], f["fase"]) for f in m["colas_fuera"]],
                         [("cola44", "en_candado", "espera la autorización de claude-fable-5-1", "44:autor")])


class C5Compatibilidad(Base):
    def test_lo_que_leen_avisos_y_las_paginas_y_la_decision_de_pausar_salen_identicos_a_antes(self):
        antes = json.loads((FIX / "c5-pronostico-56b.json").read_text(encoding="utf-8"))
        self.limites()
        ahora = muestras_c5(self.cr, self.tmp, self.uso_de)
        self.assertEqual(set(ahora), {"vivo", "uso_de_cuentas", "restante", "ventanas", "decision", "borde"})
        self.assertEqual(antes["borde"], {"64.9": True, "65.0": True, "65.1": False})        # alcanza si actual + pronóstico ≤ tope
        for grupo in antes:
            for caso in antes[grupo]:
                with self.subTest(grupo=grupo, caso=caso):
                    self.assertEqual(ahora[grupo][caso], antes[grupo][caso])
        self.assertEqual(ahora, antes)
        # Las muestras cubren lo que importa: una pausa, un «sigue», la última fase y una espera de cuota.
        self.assertEqual(antes["decision"]["claude_cami autor"][:54], "pausa: Claude (Cami) sin margen para autor: semanal 81")
        self.assertEqual(antes["decision"]["codex rev"], "sigue")
        self.assertIsNone(antes["vivo"]["corriendo 43:rev3"]["proximo"])
        self.assertEqual(antes["vivo"]["esperando_cuota 46a:fix1"]["proximo"]["fase"], "fix1")
        self.assertEqual(antes["vivo"]["partiendo 43"], dict.fromkeys(("proximo", "proximo_por_cuenta", "cuentas_en_uso", "eta", "restante_min")))

    def test_el_vivo_solo_gana_fases_restantes_y_coincide_con_la_eta_esperada(self):
        cr = self.cr
        cr.MANIFIESTO = tomllib.loads(MANIFIESTO_46)
        cr.VIVO.clear()
        cr.vivo(nombre="cola46", motivo="", estado="partiendo", lanzada=iso(T), etapas=["46a", "46b", "46c"], inicio_trabajo=iso(T))
        cr.vivo(estado="corriendo", etapa="46a", fase="rev1", inicio_fase=iso(T - timedelta(minutes=2)))
        v = json.loads((self.vivos / "cola46.json").read_text(encoding="utf-8"))
        fases = v["fases_restantes"]
        self.assertEqual(len(fases), 5 + 6 + 6)
        self.assertEqual((fases[0]["fase"], fases[0]["prob"], datetime.fromisoformat(fases[0]["inicio_esperado"])), ("rev1", 1.0, T))
        self.assertEqual([f["prob"] for f in fases if f["fase"] == "autor"], [1.0, 1.0])       # cada etapa vuelve a partir en 1
        # El fin de la última fase más el minuto de pruebas es la `eta.esperado` que ya se publicaba.
        ultimo = fases[-1]
        fin = datetime.fromisoformat(ultimo["inicio_esperado"]) + timedelta(minutes=ultimo["prob"] * ultimo["min"] + 1)
        self.assertLess(abs((fin - datetime.fromisoformat(v["eta"]["esperado"])).total_seconds()), 61)
        # Una cola que ya no corre no deja fases viejas en su vivo.
        for estado in ("pausada", "detenida", "terminada"):
            cr.vivo(estado=estado)
            self.assertNotIn("fases_restantes", json.loads((self.vivos / "cola46.json").read_text(encoding="utf-8")))
        cr.vivo(estado="pruebas finales", fase=None)
        self.assertEqual(json.loads((self.vivos / "cola46.json").read_text(encoding="utf-8"))["fases_restantes"], [])


class C6MedicionVieja(Base):
    def test_limites_medidos_hace_tres_horas_dejan_la_cuenta_debil_y_lo_dicen_en_la_fuente(self):
        self.poner("vivo-cola43r.json")
        self.timer_para("cola43r")
        fresco = self.regla("codex")
        self.assertEqual(fresco["fuente"], "uso.json")           # en la foto, Codex se midió a las 18:42
        self.limites(codex={"momento": iso(T - timedelta(hours=3, minutes=5))})
        viejo = self.regla("codex")
        self.assertTrue(viejo["debil"])
        self.assertEqual(viejo["fuente"], "medido hace 3 h")
        self.assertEqual(viejo["ventanas"], fresco["ventanas"])  # los números no cambian: solo la confianza
        # Justo bajo las 2 h todavía vale; la otra cuenta no se contagia.
        self.limites(codex={"momento": iso(T - timedelta(hours=1, minutes=59))})
        self.assertEqual((self.regla("codex")["fuente"], self.regla("codex")["debil"]), ("uso.json", fresco["debil"]))
        self.limites(codex={"momento": iso(T - timedelta(hours=16))})
        self.assertEqual(self.regla("codex")["fuente"], "medido hace 16 h")
        self.assertEqual(self.regla("claude_cami")["fuente"], "uso.json")


class C7EscenarioReal(Base):
    def test_los_numeros_de_reglas_son_la_suma_a_mano_de_prob_por_pct(self):
        """La foto de las 18:55 más la cola43r activa (su manifiesto era el cola-43.toml de ese día), relanzada
        por un timer a las 21:15:30. Escribe Claude (Cami) y revisa Codex."""
        for f in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola46.json"):
            self.poner(f)
        # Con el p75 final las fases duran distinto; este instante conserva las tres ramas:
        # autor antes de renovar, último arreglo después y revisiones de Codex tras su renovación.
        inicio = PARTE + timedelta(minutes=15)
        self.timer_para("cola43r", cuando=inicio)
        m = self.matriz()
        self.assertEqual([r["cuenta"] for r in m["reglas"]], ["claude_cami", "codex"])
        etapa = tomllib.loads((MANIFIESTOS / "cola-43.toml").read_text(encoding="utf-8"))["etapa"][0]
        limites = json.loads((FIX / "uso-limites.json").read_text(encoding="utf-8"))["cuentas_interactivo"]
        a_mano = {}
        for cid in ("claude_cami", "codex"):
            lim = limites[cid]["limites"]
            ren_5h = datetime.fromisoformat(lim["ventana_5h"]["renueva"])
            ren_sem = datetime.fromisoformat(lim["semanal"]["renueva"])
            fases = self.a_mano(inicio, cid, [etapa])
            suma = {"5h": sum(p * f["pct_5h"] for ini, p, f in fases if ini < ren_5h),
                    "proxima_5h": sum(p * f["pct_5h"] for ini, p, f in fases if ini >= ren_5h),
                    "semanal": sum(p * f["pct_sem"] for ini, p, f in fases if ini < ren_sem)}
            a_mano[cid] = suma
            r = self.regla(cid, m)
            self.assertEqual(r["colas"], ["cola43r"])
            for ventana in ("5h", "semanal"):
                w = self.ventana(r, ventana)
                self.assertAlmostEqual(w["pronostico"], suma[ventana], delta=0.5, msg=f"{cid} {ventana}")
                self.assertEqual(w["actual"], float(lim["ventana_5h" if ventana == "5h" else "semanal"]["usado_pct"]))
                self.assertEqual(w["alcanza"], w["actual"] + w["pronostico"] <= w["tope"])
            self.assertAlmostEqual(r["proxima_5h"], suma["proxima_5h"], delta=0.5, msg=cid)
            self.assertAlmostEqual(r["celdas"]["cola43r"]["pct_5h"], suma["5h"], delta=0.5)
            self.assertAlmostEqual(r["celdas"]["cola43r"]["pct_sem"], suma["semanal"], delta=0.5)
        # Lo que la foto dice, sin tolerancia que lo esconda: el escenario ejercita las tres ramas.
        cami, codex = self.regla("claude_cami", m), self.regla("codex", m)
        self.assertGreater(a_mano["claude_cami"]["5h"], 20)          # el autor parte antes de las 21:49:59
        self.assertGreater(a_mano["claude_cami"]["proxima_5h"], 0)   # el último arreglo, después
        self.assertEqual(a_mano["codex"]["5h"], 0)                   # Codex renueva a las 21:21:56, antes de la rev1
        self.assertGreater(a_mano["codex"]["proxima_5h"], 10)
        self.assertGreater(a_mano["codex"]["semanal"], 2)
        self.assertIs(cami["alcanza"], False)                        # 81 % de la semana ya pasa el tope de 75 %
        self.assertIs(codex["alcanza"], True)
        self.assertEqual((cami["renueva_5h"], cami["renueva_sem"]), ("2026-10-12T00:49:59+00:00", "2026-10-12T00:59:59+00:00"))
        self.assertEqual(m["momento"], "2026-10-11T18:55:30-03:00")
        self.assertEqual(m["cuentas"]["claude_diego"], {"renueva_5h": "2026-10-12T00:30:00+00:00", "renueva_sem": "2026-10-17T07:00:00+00:00"})
        self.assertEqual([f["cola"] for f in m["colas_fuera"]], ["cola41", "cola42", "cola46"])


    def test_con_una_cola_activa_armada_desde_el_cola_43_toml_de_hoy(self):
        """El `cola-43.toml` que hay hoy en el vault, tal cual (el 11-10 a las 19:50 pasó a ser cola43s, con tres
        etapas): la cola recién lanzada, con el vivo que escribe el propio vivo(), sobre la foto de las 18:55."""
        cr = self.cr
        man = tomllib.loads((ENCARGOS / "cola-43.toml").read_text(encoding="utf-8"))
        cr.repartir(man["etapa"])
        if any(et.get("donde", "pi") != "pi" for et in man["etapa"]):
            self.skipTest("el cola-43.toml de hoy tiene una etapa en otro equipo: la suma a mano no la modela")
        for f in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola46.json"):
            self.poner(f)
        cr.MANIFIESTO, cr.PARTIDA = man, (man["etapa"][0]["id"], "autor")
        cr.VIVO.clear()
        cr.vivo(nombre=man["nombre"], motivo=man.get("motivo", ""), estado="partiendo", lanzada=iso(T), etapas=[e["id"] for e in man["etapa"]])
        cr.vivo(estado="línea base de pruebas", esperando=None)
        self.vivas = {man["nombre"]}
        m = self.matriz()
        cuentas = list(dict.fromkeys(c for et in man["etapa"] for c in (et["autor"], et["revisor"])))
        # Las filas salen en el orden fijo de las cuentas (MOTORES), no en el del manifiesto: el cola-43.toml de hoy
        # empieza por Codex y esta línea comparaba con el orden del archivo (corregido en el encargo 46c).
        self.assertEqual([r["cuenta"] for r in m["reglas"]], [c for c in cr.MOTORES if c in cuentas])
        limites = json.loads((FIX / "uso-limites.json").read_text(encoding="utf-8"))["cuentas_interactivo"]
        for cid in cuentas:
            lim = limites[cid]["limites"]
            ren_5h, ren_sem = (datetime.fromisoformat(lim[k]["renueva"]) for k in ("ventana_5h", "semanal"))
            fases = self.a_mano(T, cid, man["etapa"])
            r = self.regla(cid, m)
            self.assertEqual(r["colas"], [man["nombre"]])
            self.assertAlmostEqual(self.ventana(r, "5h")["pronostico"], sum(p * f["pct_5h"] for ini, p, f in fases if ini < ren_5h), delta=0.5, msg=cid)
            self.assertAlmostEqual(r["proxima_5h"], sum(p * f["pct_5h"] for ini, p, f in fases if ini >= ren_5h), delta=0.5, msg=cid)
            self.assertAlmostEqual(self.ventana(r, "semanal")["pronostico"], sum(p * f["pct_sem"] for ini, p, f in fases if ini < ren_sem), delta=0.5, msg=cid)
            self.assertGreater(sum(p * f["pct_5h"] for _, p, f in fases), 0)
            celda = r["celdas"][man["nombre"]]
            self.assertAlmostEqual(celda["pct_sem_min"], sum(f["pct_sem"] for ini, p, f in fases if p == 1 and ini < ren_sem), delta=0.5)
            self.assertAlmostEqual(celda["pct_sem_max"], sum(f["pct_sem"] for ini, p, f in fases if ini < ren_sem), delta=0.5)
        self.assertEqual({f["estado"] for f in m["colas_fuera"]}, {"pausada_sin_timer"})


class Invariantes(Base):
    def test_un_vivo_a_medias_o_con_otra_forma_se_salta_y_se_marca_debil_sin_caerse(self):
        self.poner("vivo-cola43r.json")
        self.timer_para("cola43r")
        limpio = self.matriz()
        entero = (FIX / "vivo-cola41.json").read_text(encoding="utf-8")
        (self.vivos / "cola41.json").write_text(entero[: len(entero) // 2], encoding="utf-8")      # a medio escribir
        (self.vivos / "cola42.json").write_text("[1, 2]", encoding="utf-8")
        (self.vivos / "cola77.json").write_text(json.dumps({"nombre": "../../etc/passwd", "estado": "corriendo", "escrito": iso(T)}), encoding="utf-8")
        (self.vivos / "cola78.json").mkdir()
        os.mkfifo(self.vivos / "cola79.json")       # abrirlo dejaría colgado al que lee
        consultadas = []
        entradas = self.entradas() | {"viva": lambda nom: consultadas.append(nom) or False}
        m = self.cr.matriz_cuota(**entradas)
        self.assertEqual(consultadas, [])           # ningún nombre sacado de un vivo malo llega a tmux
        malos = [f for f in m["colas_fuera"] if f["estado"] == "ilegible"]
        self.assertEqual([f["cola"] for f in malos], ["cola41", "cola42", "cola77", "cola78", "cola79"])
        self.assertTrue(all(f["debil"] and f["fases_restantes"] == [] for f in malos))
        self.assertEqual([r["colas"] for r in m["reglas"]], [["cola43r"], ["cola43r"]])
        self.assertTrue(all(r["debil"] for r in m["reglas"]))
        sin_debil = lambda reglas: [{k: v for k, v in r.items() if k != "debil"} for r in reglas]
        self.assertEqual(sin_debil(m["reglas"]), sin_debil(limpio["reglas"]))

    def test_un_vivo_que_es_un_enlace_simbolico_no_se_lee_ni_se_suma(self):
        # 46ar1, hallazgo 1: la reproducción del revisor. Un JSON fuera de `vivo/`, con la forma real de un vivo
        # y una fase de Codex, y `vivo/cola99.json` como enlace a él.
        self.poner("vivo-cola43r.json")
        self.timer_para("cola43r")
        fase = {"etapa": "9", "fase": "autor", "rol": "autor", "cuenta": "codex", "modelo": "", "min": 5, "pct_5h": 7.0,
                "pct_sem": 2.0, "prob": 1.0, "inicio_esperado": iso(T), "debil": False}
        v = json.loads((FIX / "vivo-cola46-corriendo.json").read_text(encoding="utf-8")) | {
            "nombre": "cola99", "escrito": iso(T), "fases_restantes": [fase]}
        afuera = self.tmp / "afuera-de-vivo.json"
        afuera.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
        self.vivas = {"cola99"}
        limpio = self.matriz()
        enlace = self.vivos / "cola99.json"
        enlace.symlink_to(afuera)
        self.assertTrue(enlace.is_symlink() and enlace.is_file())           # is_file() sigue el enlace: no sirve de filtro
        self.assertNotIn(self.vivos.resolve(), enlace.resolve().parents)    # el destino está fuera de vivo/
        (self.vivos / "cola98.json").symlink_to(self.tmp / "no-existe.json")    # un enlace roto tampoco tira al lector
        with self.assertRaises(OSError):
            self.cr._leer_vivo(enlace)
        abiertos = len(os.listdir("/proc/self/fd"))
        buenos, malos = self.cr.leer_vivos(self.vivos)
        self.assertEqual(len(os.listdir("/proc/self/fd")), abiertos)        # el rechazo no deja descriptores abiertos
        self.assertEqual(([b["nombre"] for b in buenos], malos), (["cola43r"], ["cola98", "cola99"]))
        consultadas = []
        m = self.cr.matriz_cuota(**(self.entradas() | {"viva": lambda nom: consultadas.append(nom) or nom in self.vivas}))
        self.assertNotIn("cola99", consultadas)                             # su nombre no llega a tmux
        fuera = {f["cola"]: f for f in m["colas_fuera"]}
        for nom in ("cola98", "cola99"):
            self.assertEqual((fuera[nom]["estado"], fuera[nom]["fases_restantes"], fuera[nom]["debil"]), ("ilegible", [], True))
        self.assertNotIn("7.0", json.dumps(fuera["cola99"]))
        self.assertEqual([r["colas"] for r in m["reglas"]], [["cola43r"], ["cola43r"]])
        self.assertTrue(all(r["debil"] for r in m["reglas"]))
        sin_debil = lambda reglas: [{k: v for k, v in r.items() if k != "debil"} for r in reglas]
        self.assertEqual(sin_debil(m["reglas"]), sin_debil(limpio["reglas"]))
        self.assertEqual(json.loads(afuera.read_text(encoding="utf-8")), v)  # y el archivo de fuera queda como estaba
        # Control: el mismo contenido como archivo corriente sí se lee y sí suma su 7 % a Codex. Lo único que
        # distingue los dos casos es el enlace.
        (self.vivos / "cola98.json").unlink()
        enlace.unlink()
        shutil.copyfile(afuera, enlace)
        r = self.regla("codex")
        self.assertEqual(r["colas"], ["cola43r", "cola99"])
        self.assertEqual(r["celdas"]["cola99"]["pct_5h"], 7.0)
        self.assertEqual(self.ventana(r, "5h")["pronostico"], self.ventana(self.regla("codex", limpio), "5h")["pronostico"] + 7.0)

    def test_las_fases_que_publica_otra_cola_se_leen_con_desconfianza(self):
        buena = {"etapa": "9", "fase": "autor", "rol": "autor", "cuenta": "codex", "modelo": "", "min": 5, "pct_5h": 10.0,
                 "pct_sem": 2.0, "prob": 1.0, "inicio_esperado": iso(T), "debil": False}
        malas = [dict(buena, cuenta="groq"), dict(buena, pct_5h="mucho"), dict(buena, prob=7), dict(buena, inicio_esperado="mañana"),
                 dict(buena, pct_sem=float("nan")), "autor", None, dict(buena, pct_5h=-50)]
        self.poner("vivo-cola46-corriendo.json", escrito=iso(T), fases_restantes=[buena] + malas)
        self.vivas = {"cola46"}
        r = self.regla("codex")
        self.assertEqual(r["celdas"]["cola46"]["pct_5h"], 10.0)
        self.assertTrue(r["debil"])
        self.assertEqual([x["cuenta"] for x in self.matriz()["reglas"]], ["codex"])
        # Y si no es ni una lista, se arma desde el manifiesto, como con un vivo anterior al encargo.
        self.reloj = datetime.fromisoformat("2026-10-11T19:40:00-03:00")
        self.poner("vivo-cola46-corriendo.json", fases_restantes="todas")
        self.assertEqual([x["cuenta"] for x in self.matriz()["reglas"]], ["claude_cami", "codex"])

    def test_el_panel_no_escribe_nada_ni_lanza_procesos_ni_avisa(self):
        cr = self.cr
        for f in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola46.json"):
            self.poner(f)
        self.timer_para("cola43r")
        cr._AP_MOD = cargar(PI / "aplicar-propuesta.py")
        cr._AP_MOD.CODEX_MODELOS = str(PI / "fixtures" / "encargos" / "models_cache.json")
        cr.SIMULANDO = True
        foto = lambda: sorted((str(p.relative_to(self.tmp)), p.stat().st_mtime_ns, p.stat().st_size) for p in self.tmp.rglob("*"))
        antes = foto()
        panel = cr.panel(**self.entradas())
        self.assertEqual(foto(), antes)
        self.assertEqual(set(panel), {"modelos", "catalogo", "cuentas", "pronosticos", "reglas", "colas_fuera", "capacidad_por_vencer", "momento", "colas", "despacho", "pasado"})   # `colas`: 46c; `despacho` y `pasado`: 50a; capacidad: 50b
        self.assertEqual(panel["momento"], "2026-10-11T18:55:30-03:00")
        self.assertEqual(panel["cuentas"]["codex"], {"nombre": "Codex", "motor": "codex", "renueva_5h": "2026-10-11T21:21:56-03:00",
                                                     "renueva_sem": "2026-10-18T16:21:56-03:00"})
        self.assertEqual({r["nombre"] for r in panel["reglas"]}, {"Claude (Cami)", "Codex"})
        self.assertEqual(panel["reglas"], self.matriz()["reglas"])
        json.dumps(panel)       # todo lo que sale es JSON
        # Y con SIMULANDO, vivo() tampoco escribe.
        cr.MANIFIESTO = tomllib.loads(MANIFIESTO_46)
        cr.vivo(nombre="cola99", estado="partiendo")
        self.assertEqual(foto(), antes)

    def test_el_vivo_se_escribe_con_un_tmp_propio_de_la_cola_y_un_rename(self):
        cr = self.cr
        cr.MANIFIESTO = tomllib.loads(MANIFIESTO_46)
        movidos = []
        replace_real = os.replace

        def replace(origen, destino):
            movidos.append((Path(origen).name, Path(destino).name, json.loads(Path(origen).read_text(encoding="utf-8"))["estado"]))
            replace_real(origen, destino)
        cr.os = type("Os", (), {"replace": staticmethod(replace)})
        cr.VIVO.clear()
        cr.vivo(nombre="cola46", estado="partiendo", etapas=["46a", "46b", "46c"])
        self.assertEqual(movidos, [(".cola46.json.tmp", "cola46.json", "partiendo")])
        self.assertEqual(sorted(p.name for p in self.vivos.iterdir()), ["cola46.json"])
        # Dueño y modo: los de cualquier archivo que crea este usuario, como los vivo de hoy (0644 con la umask del nodo).
        testigo = self.tmp / "testigo"
        testigo.write_text("x", encoding="utf-8")
        st, st_testigo = (self.vivos / "cola46.json").stat(), testigo.stat()
        self.assertEqual((st.st_uid, st.st_gid, st.st_mode), (st_testigo.st_uid, st_testigo.st_gid, st_testigo.st_mode))
        self.assertEqual(len(json.loads((self.vivos / "cola46.json").read_text(encoding="utf-8"))["fases_restantes"]), 18)

    def test_los_timers_se_leen_de_la_salida_real_de_systemctl_y_solo_cuentan_los_que_van_a_disparar(self):
        pedidos = []

        def correr(cmd, **k):
            pedidos.append(cmd)
            salida = LIST_TIMERS if cmd[2] == "list-timers" else EXEC_ORDEN_CADENA
            return type("P", (), {"stdout": salida, "returncode": 0})()
        timers = self.cr.timers_reanudacion(correr)
        self.assertEqual(pedidos, [["systemctl", "--user", "list-timers", "--all", "--output=json"],
                                   ["systemctl", "--user", "show", "orden-cadena.service", "-p", "ExecStart", "--value"]])
        self.assertEqual(timers, [(datetime.fromtimestamp(1791764430).astimezone(), EXEC_ORDEN_CADENA)])
        # Si systemd no contesta o contesta otra cosa, no hay timers y nada se cae.
        for roto in (lambda cmd, **k: (_ for _ in ()).throw(FileNotFoundError("systemctl")),
                     lambda cmd, **k: type("P", (), {"stdout": "Failed to connect to bus", "returncode": 1})(),
                     lambda cmd, **k: type("P", (), {"stdout": '{"next": 5}', "returncode": 0})()):
            self.assertEqual(self.cr.timers_reanudacion(roto), [])

    def test_sin_dato_de_cuota_la_cuenta_sale_sin_veredicto_pero_con_sus_celdas(self):
        self.poner("vivo-cola43r.json")
        self.timer_para("cola43r")
        self.uso_ruta = self.tmp / "no-existe.json"
        r = self.regla("codex")
        self.assertEqual((r["alcanza"], r["ventanas"], r["texto"], r["fuente"]), (None, [], "Codex: sin dato de cuota (sin dato)", "sin dato"))
        self.assertTrue(r["debil"])
        self.assertGreater(r["celdas"]["cola43r"]["pct_5h"], 0)


def captura() -> None:
    """Lo que publica `--panel` (la parte de la matriz) con las fixtures y la cola43r relanzada por un timer."""
    tmp = Path(tempfile.mkdtemp(prefix="matriz-cuota-"))
    try:
        cr = cargar()
        preparar(cr, tmp, lambda: T)
        for f in ("vivo-cola41.json", "vivo-cola42.json", "vivo-cola43r.json", "vivo-cola46.json"):
            v = json.loads((FIX / f).read_text(encoding="utf-8"))
            (tmp / "vivo" / f"{v['nombre']}.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
        cr._AP_MOD = cargar(PI / "aplicar-propuesta.py")
        cr._AP_MOD.CODEX_MODELOS = str(PI / "fixtures" / "encargos" / "models_cache.json")
        cr.SIMULANDO = True
        panel = cr.panel(vivos_dir=tmp / "vivo", uso_de=lambda cid: cr.uso(cid, FIX / "uso-limites.json", T), momento=T,
                         viva=lambda nom: False, manifiestos_dir=MANIFIESTOS,
                         timers=[(PARTE, EXEC_COLA36.replace("cola36", "cola43r").replace("cola-36.toml", "cola-43.toml"))])
        print(json.dumps({k: panel[k] for k in ("momento", "cuentas", "reglas", "colas_fuera")}, ensure_ascii=False, indent=1))
    finally:
        shutil.rmtree(tmp, True)


if __name__ == "__main__":
    if "--captura" in sys.argv:
        captura()
    else:
        unittest.main()
