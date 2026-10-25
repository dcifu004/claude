#!/usr/bin/env python3
"""Pruebas aisladas del aviso de quema: no usa /opt/nodo/datos, Telegram ni tmux."""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path

ENCARGOS = Path(__file__).resolve().parent
PI = ENCARGOS.parent / "pi" / "nodo-desplegar.py"
spec = importlib.util.spec_from_file_location("quema_prueba", ENCARGOS / "quema.py")
quema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quema)
PANEL = json.loads((ENCARGOS / "fixtures/quema-panel-20261024.json").read_text(encoding="utf-8"))
SIMULACION_CODEX = (ENCARGOS / "fixtures/quema-simular-codex-20261024.txt").read_text(encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="quema-"))
        self.proyecto = self.tmp / "Pi5"
        shutil.copytree(ENCARGOS / "quema", self.proyecto / "encargos/quema")
        (self.proyecto / "encargos").mkdir(exist_ok=True)
        (self.proyecto / "encargos/cola-run.py").write_text("# falso\n", encoding="utf-8")
        self.consultas, self.lanzados = [], []
        self.respuesta = None
        spec_nd = importlib.util.spec_from_file_location(f"nodo_desplegar_quema_{id(self)}", PI)
        self.nd = importlib.util.module_from_spec(spec_nd)
        spec_nd.loader.exec_module(self.nd)
        self.nd.RESULTADOS = self.tmp / "resultados"
        self.nd.RESULTADOS.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def app(self, panel=PANEL):
        def consultar(motivo, opciones):
            self.consultas.append((motivo, opciones))
            return f"20261023-1600{len(self.consultas):02d}-abcd"
        def esperar(pid):
            if self.respuesta is not None:
                return self.respuesta
            # La forma la escribe la misma función que usa el escucha root para una consulta;
            # consultar no produce motivo_sha256.
            self.nd.Escucha.resultado(pid, "hecho", "el usuario eligió A (memoria)", opcion="memoria", letra="A")
            return json.loads((self.nd.RESULTADOS / f"{pid}.json").read_text(encoding="utf-8"))
        def lanzar(argv):
            self.lanzados.append(argv)
            return 0
        return quema.Quema(self.tmp / "datos", self.proyecto, montado=lambda: True, panel=lambda: panel,
                           simular=self.simular_real, consultar=consultar, esperar=esperar,
                           lanzar=lanzar, sesion=lambda _: True)

    @staticmethod
    def simular_real(ruta):
        cuenta = __import__("tomllib").loads(ruta.read_text(encoding="utf-8"))["etapa"][0]["autor"]
        nombre = quema.NOMBRES[cuenta]
        # Copia de las filas que imprime --simular: autor y fix, porcentajes por 5 h y semana.
        return 0, (f"99q · naturaleza: investigacion\n"
                   f"  autor {nombre}   modelo medium   [agil]  6.0 min  +1.0 % 5 h (p75 1.0 %)  +2.0 % sem\n"
                   f"  rev   Claude (Cami) modelo medium [normal] 5.0 min  +1.0 % 5 h (p75 1.0 %)  +1.0 % sem\n"
                   f"  fix   {nombre}   modelo medium   [agil]  3.0 min  +1.0 % 5 h (p75 1.0 %)  +2.0 % sem\n")


class SeleccionTests(Base):
    def test_c1_miercoles_solo_codex_y_viernes_solo_las_dos_claude(self):
        self.respuesta = {"estado": "hecho", "opcion": "no_quemar", "letra": "D", "id": "20261023-160001-abcd"}
        self.app().ejecutar(datetime.fromisoformat("2026-10-28T16:00:00-03:00"))
        self.assertEqual([x[0] for x in self.consultas], ["Codex 51 % 21:32"])
        otra = self.app()
        otra.ejecutar(datetime.fromisoformat("2026-10-30T16:00:00-03:00"))
        self.assertEqual([x[0] for x in self.consultas], ["Codex 51 % 21:32", "Claude (Diego) 62 % 03:59"])

    def test_c1_descarta_menos_de_15_o_mas_de_72_horas(self):
        panel = json.loads(json.dumps(PANEL))
        panel["capacidad_por_vencer"]["claude_diego"]["capacidad"] = 14.9
        panel["capacidad_por_vencer"]["claude_cami"]["renueva"] = "2026-11-04T22:00:00-03:00"
        self.app(panel).ejecutar(datetime.fromisoformat("2026-10-30T16:00:00-03:00"))
        self.assertEqual(self.consultas, [])

    def test_c2_alternativas_cerradas_y_maximo_tres_mas_no_quemar(self):
        self.respuesta = {"estado": "hecho", "opcion": "no_quemar", "letra": "D", "id": "20261023-160001-abcd"}
        self.app().ejecutar(datetime.fromisoformat("2026-10-28T16:00:00-03:00"))
        motivo, opciones = self.consultas[0]
        self.assertEqual([k for k, _ in opciones], ["memoria", "auditoria", "revision", "no_quemar"])
        self.assertTrue(quema._linea_cerrada(motivo))
        self.assertTrue(all(quema._linea_cerrada(x) for _, x in opciones))

    def test_capacidad_decimal_real_se_comunica_hacia_abajo_y_no_aborta(self):
        panel = json.loads(json.dumps(PANEL))
        panel["capacidad_por_vencer"]["codex"]["capacidad"] = 18.7
        self.app(panel).ejecutar(datetime.fromisoformat("2026-10-28T16:00:00-03:00"))
        self.assertEqual(self.consultas[0][0], "Codex 18 % 21:32")

    def test_simulador_con_rc_de_error_o_carga_mayor_no_ofrece_plantilla(self):
        app = self.app()
        app.simular = lambda _: (2, "⛔ no se pudo simular\n")
        self.assertEqual(app.candidatas("codex", 63, datetime.fromisoformat("2026-10-28T16:00:00-03:00")), [])
        app.simular = lambda ruta: (0, self.simular_real(ruta)[1].replace("+2.0 % sem", "+64.0 % sem"))
        self.assertEqual(app.candidatas("codex", 63, datetime.fromisoformat("2026-10-28T16:00:00-03:00")), [])

    def test_salida_real_de_simular_suma_autor_y_fix(self):
        self.assertEqual(quema.Quema._carga_autor(SIMULACION_CODEX, "codex"), 0.0)


class RespuestaTests(Base):
    def test_c3_no_quemar_vencida_y_ausente_no_lanzan_y_solo_reintentan_dos_veces(self):
        app = self.app()
        self.respuesta = {"estado": "vencido"}
        for hora in (16, 18, 20, 21):
            app.ejecutar(datetime.fromisoformat(f"2026-10-28T{hora:02d}:00:00-03:00"))
        self.assertEqual((len(self.consultas), self.lanzados), (3, []))
        self.respuesta = {"estado": "hecho", "opcion": "no_quemar", "letra": "D", "id": "20261023-160001-abcd"}
        otro = self.app()
        otro.ejecutar(datetime.fromisoformat("2026-10-23T16:00:00-03:00"))
        self.assertEqual(self.lanzados, [])

    def test_opcion_hostil_se_anota_y_no_lanza(self):
        self.respuesta = {"estado": "hecho", "opcion": "raiz", "letra": "A", "id": "20261023-160001-abcd"}
        self.app().ejecutar(datetime.fromisoformat("2026-10-28T16:00:00-03:00"))
        filas = (self.tmp / "datos/quema/registro.jsonl").read_text(encoding="utf-8")
        self.assertIn('"resultado": "invalida"', filas)
        self.assertEqual(self.lanzados, [])

    def test_respuesta_real_del_escucha_sin_firma_lanza(self):
        self.app().ejecutar(datetime.fromisoformat("2026-10-28T16:00:00-03:00"))
        self.assertEqual(len(self.lanzados), 1)

    def test_letra_o_id_incoherentes_se_rechazan(self):
        self.respuesta = {"id": "20261023-160001-abcd", "estado": "hecho", "opcion": "memoria", "letra": "B"}
        self.app().ejecutar(datetime.fromisoformat("2026-10-28T16:00:00-03:00"))
        self.assertEqual(self.lanzados, [])

    def test_una_eleccion_en_el_segundo_intento_no_abre_un_tercero(self):
        app = self.app()
        self.respuesta = {"estado": "vencido"}
        app.ejecutar(datetime.fromisoformat("2026-10-28T16:00:00-03:00"))
        self.respuesta = None
        app.ejecutar(datetime.fromisoformat("2026-10-28T18:00:00-03:00"))
        app.ejecutar(datetime.fromisoformat("2026-10-28T20:00:00-03:00"))
        self.assertEqual((len(self.consultas), len(self.lanzados)), (2, 1))


class LanzamientoTests(Base):
    def test_c4_manifiesto_autor_revisor_distintos_y_lanzador_igual_a_relanzar(self):
        app = self.app()
        hechos = app.ejecutar(datetime.fromisoformat("2026-10-28T16:00:00-03:00"))
        self.assertEqual(len(hechos), 1)
        ruta = next((self.tmp / "datos/quema/manifiestos").glob("*.toml"))
        texto = ruta.read_text(encoding="utf-8")
        self.assertIn('autor = "codex"', texto)
        self.assertIn('revisor = "claude_cami"', texto)
        self.assertIn('despliegue = "nada"', texto)
        nombre = hechos[0]
        self.assertEqual(self.lanzados[0], ["tmux", "new-session", "-d", "-s", nombre, "python3",
                                             str(self.proyecto / "encargos/cola-run.py"), str(ruta)])

    def test_c4_cuarta_quema_se_rechaza(self):
        app = self.app()
        ahora = datetime.fromisoformat("2026-10-28T16:00:00-03:00")
        for i in range(3):
            self.assertTrue(app._reservar("codex", ahora, "lanzamiento"))
        app.ejecutar(ahora)
        self.assertEqual(self.lanzados, [])

    def test_c5_manifiesto_fuera_de_encargos_y_reserva_simultanea(self):
        app = self.app()
        ahora = datetime.fromisoformat("2026-10-28T16:00:00-03:00")
        hilos = [threading.Thread(target=app.ejecutar, args=(ahora,)) for _ in range(2)]
        for h in hilos: h.start()
        for h in hilos: h.join()
        rutas = list((self.tmp / "datos/quema/manifiestos").glob("*.toml"))
        self.assertEqual((len(rutas), len(self.lanzados)), (1, 1))
        self.assertFalse(str(rutas[0]).startswith(str(self.proyecto / "encargos")))
        self.assertEqual(list((self.proyecto / "encargos").glob("cola-*.toml")), [])

    def test_las_dos_claude_generan_etapas_y_colas_distintas(self):
        app = self.app()
        p = app.plantillas()["memoria"]
        ahora = datetime.fromisoformat("2026-10-30T16:00:00-03:00")
        a = app._manifestar("claude_diego", "memoria", p, ahora)
        b = app._manifestar("claude_cami", "memoria", p, ahora)
        ma, mb = __import__("tomllib").loads(a.read_text()), __import__("tomllib").loads(b.read_text())
        self.assertNotEqual((ma["nombre"], ma["etapa"][0]["id"]), (mb["nombre"], mb["etapa"][0]["id"]))
        self.assertRegex(ma["nombre"], r"^cola[0-9]{2}[a-z0-9]*$")

    def test_lanzador_real_suelta_el_servidor_tmux_del_cgroup_transitorio(self):
        vistos = []
        class R:
            returncode = 0
        original = quema.subprocess.run
        quema.subprocess.run = lambda argv, **_: vistos.append(argv) or R()
        try:
            rc = quema.Quema._lanzar_real(["tmux", "new-session", "-d", "-s", "cola99q20261028160000x", "python3", "cola-run.py", "x.toml"])
        finally:
            quema.subprocess.run = original
        self.assertEqual(rc, 0)
        self.assertEqual(vistos[0][:8], ["systemd-run", "--user", "--unit=quema-cola99q20261028160000x", "--collect", "--service-type=exec", "--no-block", "-p", "KillMode=process"])
        self.assertEqual(vistos[0][-8:], ["--", "tmux", "new-session", "-d", "-s", "cola99q20261028160000x", "python3", "cola-run.py", "x.toml"][-8:])


class AislamientoTests(Base):
    def test_c6_luks_cerrado_sale_sin_consultar(self):
        app = quema.Quema(self.tmp / "datos", self.proyecto, montado=lambda: False,
                          panel=lambda: self.fail("no debe leer panel"))
        self.assertEqual(app.ejecutar(datetime.fromisoformat("2026-10-28T16:00:00-03:00")), [])

    def test_unidad_conserva_el_socket_tmux_y_solo_abre_el_spool(self):
        servicio = (ENCARGOS.parent / "pi/quema-aviso.service").read_text(encoding="utf-8")
        self.assertIn("PrivateTmp=false", servicio)
        self.assertIn("/var/spool/nodo-desplegar/pedidos", servicio)
        self.assertIn("/var/spool/nodo-desplegar/resultados", servicio)
        self.assertIn("ProtectSystem=strict", servicio)


if __name__ == "__main__":
    unittest.main(verbosity=2)
