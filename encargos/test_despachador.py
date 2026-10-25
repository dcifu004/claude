#!/usr/bin/env python3
"""Pruebas aisladas del despachador (encargo 55).

Usa tmp_path, vivos copiados de 46-fixtures/ y manifiestos reales; tmux y el
lanzador son dobles. No toca /opt/nodo/datos, ninguna cola ni avisa.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ENCARGOS = Path(__file__).resolve().parent
FIX = ENCARGOS / "46-fixtures"


def cargar():
    spec = importlib.util.spec_from_file_location("despachador_prueba", ENCARGOS / "despachador.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


class TmuxFalso:
    def __init__(self, sesiones=()):
        self.sesiones = list(sesiones)

    def run(self, argv, **kwargs):
        self.assert_argv(argv)
        return subprocess.CompletedProcess(argv, 0 if self.sesiones else 1, "\n".join(self.sesiones), "")

    @staticmethod
    def assert_argv(argv):
        if argv[1:] != ["list-sessions", "-F", "#{session_name}"]:
            raise AssertionError(f"tmux inesperado: {argv}")


class Base(unittest.TestCase):
    def setUp(self):
        self.td = TemporaryDirectory(prefix="despachador-")
        self.addCleanup(self.td.cleanup)
        self.raiz = Path(self.td.name)
        self.vivos = self.raiz / "vivo"
        self.vivos.mkdir()
        self.d = cargar()
        self.tmux = TmuxFalso()
        self.d.subprocess = self.tmux
        self.lanzadas = []
        self.escribir_manifiesto("cola41")

    def escribir_manifiesto(self, nombre, depende=None):
        extra = "" if depende is None else "depende = [" + ", ".join(json.dumps(x) for x in depende) + "]\n"
        (self.raiz / f"cola-{nombre[4:]}.toml").write_text(
            f'nombre = "{nombre}"\n{extra}\n[[etapa]]\nid = "{nombre[4:]}"\n', encoding="utf-8")

    def prioridad(self, texto):
        p = self.raiz / "prioridad.txt"
        p.write_text(texto, encoding="utf-8")
        return p

    def poner(self, origen, *, nombre=None, **cambios):
        dato = json.loads((origen if isinstance(origen, Path) else FIX / origen).read_text(encoding="utf-8"))
        if nombre:
            dato["nombre"] = nombre
        dato.update(cambios)
        (self.vivos / f"{dato['nombre']}.json").write_text(json.dumps(dato), encoding="utf-8")
        return dato

    def pasar(self, texto="cola41\n", **kw):
        return self.d.pasada(carpeta=self.raiz, prioridad=self.prioridad(texto), vivos_dir=self.vivos,
                             tmux=("tmux-falso",), lanzar=lambda a: self.lanzadas.append(a) or 0, **kw)

    def registro(self):
        p = self.vivos / "acciones.jsonl"
        return [] if not p.exists() else [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


class C1Lanzamientos(Base):
    def test_sin_cuota_real_43s_reanuda_con_snapshot_y_manifiesto_real(self):
        # Snapshot congelado de la pausa real de cola43s (cola43s.out:33).
        shutil.copy2(ENCARGOS / "cola-43.toml", self.raiz / "cola-43.toml")
        self.poner("vivo-cola43s-sin-cuota.json")
        r = self.pasar("cola43s\n")
        self.assertEqual((r["lanzada"], self.lanzadas[0][-2:]), ("cola43s", ["--desde", "43b:rev3"]))

    def test_sin_margen_fixture_41_reanuda(self):
        self.poner("vivo-cola41.json")
        r = self.pasar()
        self.assertEqual((r["lanzada"], self.lanzadas[0][-1]), ("cola41", "41:rev3"))

    def test_sin_vivo_parte_desde_el_inicio(self):
        r = self.pasar()
        self.assertEqual((r["lanzada"], self.lanzadas[0][-1]), ("cola41", str(self.raiz / "cola-41.toml")))

    def test_esperando_cuota_antiguo_usa_su_etapa_y_fase(self):
        self.escribir_manifiesto("cola43")
        self.poner("vivo-cola43-esperando-cuota.json")
        r = self.pasar("cola43\n")
        self.assertEqual((r["lanzada"], self.lanzadas[0][-1]), ("cola43", "43:autor"))


class C2AC5(Base):
    def test_c2_con_una_cola_viva_no_lanza(self):
        self.tmux.sesiones = ["cola99"]
        self.assertIsNone(self.pasar()["lanzada"])
        self.assertFalse(self.lanzadas)

    def test_c3_pausa_salta_no_autorizada_pero_lanza_autorizada(self):
        (self.vivos / "despacho.json").write_text('{"estado":"pausa","autorizadas":["cola42"]}', encoding="utf-8")
        self.escribir_manifiesto("cola42")
        r = self.pasar("cola41\ncola42\n")
        self.assertEqual(r["lanzada"], "cola42")
        self.assertIn("no está autorizada", r["eventos"][0])

    def test_c4_depende_sin_y_con_terminar(self):
        self.escribir_manifiesto("cola42", ["cola41"])
        r = self.pasar("cola42\n")
        self.assertIsNone(r["lanzada"])
        self.poner("vivo-cola41.json", estado="terminada")
        self.assertEqual(self.pasar("cola42\n")["lanzada"], "cola42")

    def test_c5_detenida_y_consulta_se_anotan_y_sigue(self):
        self.escribir_manifiesto("cola42")
        self.poner("vivo-cola41.json", estado="detenida")
        r = self.pasar("cola41\ncola42\n")
        self.assertEqual(r["lanzada"], "cola42")
        self.assertEqual(self.registro()[0]["resultado"], "saltada")
        (self.vivos / "acciones.jsonl").unlink()
        self.poner("vivo-cola41.json", estado="en_consulta")
        r = self.pasar("cola41\ncola42\n")
        self.assertEqual(r["lanzada"], "cola42")


class C6C7(Base):
    def test_c6_dos_pasadas_con_flock_lanzan_una_sola(self):
        prioridad = self.prioridad("cola41\n")
        barrera, lanzadas = threading.Barrier(2), []
        candado = threading.Lock()
        def corre():
            barrera.wait()
            def lanza(argv):
                time.sleep(.03)
                with candado:
                    lanzadas.append(argv)
                    self.tmux.sesiones.append(argv[4])
                return 0
            self.d.pasada(carpeta=self.raiz, prioridad=prioridad, vivos_dir=self.vivos, tmux=("tmux-falso",),
                          lanzar=lanza)
        hilos = [threading.Thread(target=corre) for _ in range(2)]
        for h in hilos: h.start()
        for h in hilos: h.join()
        self.assertEqual(len(lanzadas), 1)

    def test_c7_simular_no_escribe_nada(self):
        antes = sorted(p.name for p in self.vivos.iterdir())
        r = self.pasar("cola41\n", simular=True)
        self.assertEqual(r["lanzada"], "cola41")
        self.assertEqual(sorted(p.name for p in self.vivos.iterdir()), antes)
        self.assertFalse(self.lanzadas)


class C8Formato(Base):
    def test_terminada_se_quita_y_cada_fila_es_del_despachador(self):
        self.poner("vivo-cola41.json", estado="terminada")
        self.escribir_manifiesto("cola42")
        p = self.prioridad("# conserva\ncola41\ncola42\n")
        self.d.pasada(carpeta=self.raiz, prioridad=p, vivos_dir=self.vivos, tmux=("tmux-falso",), lanzar=lambda a: 0)
        self.assertEqual(p.read_text(encoding="utf-8"), "# conserva\ncola42\n")
        self.assertTrue(all(x["por"] == "despachador" for x in self.registro()))

    def test_varias_terminadas_se_quitan_en_una_pasada(self):
        self.escribir_manifiesto("cola42")
        self.poner("vivo-cola41.json", estado="terminada")
        self.poner("vivo-cola42.json", estado="terminada")
        p = self.prioridad("cola41\ncola42\n")
        self.d.pasada(carpeta=self.raiz, prioridad=p, vivos_dir=self.vivos, tmux=("tmux-falso",), lanzar=lambda a: 0)
        self.assertEqual(p.read_text(encoding="utf-8"), "")
        self.assertEqual([x["resultado"] for x in self.registro()], ["quitada", "quitada"])

    def test_vivo_roto_no_es_nunca_partio(self):
        (self.vivos / "cola41.json").write_text('{"nombre":"cola41","estado":"deten', encoding="utf-8")
        r = self.pasar(simular=True)
        self.assertIsNone(r["lanzada"])
        self.assertIn("vivo ilegible", r["eventos"][0])

    def test_desde_debe_existir_en_manifiesto_real(self):
        shutil.copy2(ENCARGOS / "cola-41.toml", self.raiz / "cola-41.toml")
        self.poner("vivo-cola41.json", reanuda_desde="99:rev3")
        r = self.pasar(simular=True)
        self.assertIsNone(r["lanzada"])
        self.assertIn("reanuda_desde inválido", r["eventos"][0])

    def test_pausa_por_cuota_ya_despachada_deja_pasar_la_siguiente(self):
        self.escribir_manifiesto("cola42")
        self.poner("vivo-cola41.json")
        self.poner("vivo-cola42.json")
        (self.vivos / "acciones.jsonl").write_text(json.dumps({"momento": self.d.ahora(), "cola": "cola41", "resultado": "hecho", "por": "despachador"}) + "\n", encoding="utf-8")
        r = self.pasar("cola41\ncola42\n")
        self.assertEqual(r["lanzada"], "cola42")
        self.assertIn("sin vivo posterior", r["eventos"][0])

    def test_dos_pasadas_sin_vivo_no_relanzan_y_la_fila_es_real(self):
        primera = self.pasar()
        segunda = self.pasar()
        self.assertEqual(primera["lanzada"], "cola41")
        self.assertIsNone(segunda["lanzada"])
        self.assertEqual(len(self.lanzadas), 1)
        filas = self.registro()
        self.assertEqual(filas[0]["resultado"], "hecho")
        self.assertEqual(filas[0]["por"], "despachador")
        self.assertIn("sin vivo posterior", segunda["eventos"][0])

    def test_lanzamiento_inicial_no_gasta_el_reintento_de_cuota(self):
        primera = self.pasar()
        self.poner("vivo-cola41.json", escrito=self.d.ahora())
        segunda = self.pasar()
        self.assertEqual(primera["lanzada"], "cola41")
        self.assertEqual(segunda["lanzada"], "cola41")
        self.assertEqual([fila["desde"] for fila in self.registro() if fila["resultado"] == "hecho"],
                         [None, "41:rev3"])

    def test_registro_roto_no_abre_el_freno_y_la_fila_es_real(self):
        self.poner("vivo-cola41.json")
        primera = self.pasar()
        registro = self.vivos / "acciones.jsonl"
        registro.write_text("\n[]\n7\n" + registro.read_text(encoding="utf-8"), encoding="utf-8")
        segunda = self.pasar()
        self.assertEqual(primera["lanzada"], "cola41")
        self.assertIsNone(segunda["lanzada"])
        self.assertEqual(len(self.lanzadas), 1)
        filas = [json.loads(linea) for linea in registro.read_text(encoding="utf-8").splitlines()
                 if linea.startswith("{")]
        self.assertEqual(filas[0]["resultado"], "hecho")
        self.assertIn("sin vivo posterior", segunda["eventos"][0])

    def test_desde_remoto_usa_donde_igual_que_cola_run(self):
        man = {"etapa": [{"id": "41", "donde": "pc2503", "vueltas": 2}]}
        self.assertFalse(self.d._desde_valido("41:fix1", man))

    def test_acciones_fifo_falla_sin_colgar(self):
        os.mkfifo(self.vivos / "acciones.jsonl")
        with self.assertRaises(OSError):
            self.pasar()

    def test_unidad_declara_montaje_y_supervivencia_de_sesion_hija(self):
        unidad = (ENCARGOS / "despachador.service").read_text(encoding="utf-8")
        self.assertIn("ConditionPathIsMountPoint=/opt/nodo/datos", unidad)
        self.assertIn("KillMode=process", unidad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
