#!/usr/bin/env python3
"""Pruebas de balance.py (encargo 47a).

Todo corre en un tempfile: el historial de prueba se arma COPIANDO filas reales de historial.jsonl
(que sólo se lee) y los manifiestos se escriben en el mismo temporal. Ninguna prueba escribe en
/opt/nodo/datos ni manda avisos."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

AQUI = Path(__file__).resolve().parent
REAL = AQUI / "historial.jsonl"
sys.dont_write_bytecode = True       # importar balance.py no deja __pycache__ nuevo


def _cargar(nombre, archivo):
    spec = importlib.util.spec_from_file_location(nombre, AQUI / archivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bal = _cargar("balance", "balance.py")

# Encargos viejos y cerrados del historial real: 19 (Codex + Claude, sin modelo ni naturaleza),
# 27c (con sufijo, aprobado a la primera) y 33b (con sufijo, Haiku con esfuerzo "", tres revisiones).
MUESTRA = ("19", "27c", "33b")

MANIFIESTO = '''nombre = "colaX"
afinado = "ligero"
experimento = "esfuerzo-v1"

[[etapa]]
id = "27c"
encargo = "27c-pruebas-inestables.md"
naturaleza = "menor"

[[etapa]]
id = "33b"
encargo = "33b-cierre-git.md"
naturaleza = "diseno"
'''

# Se llama como el encargo 19 pero no trae su etapa: el nombre del archivo no asocia nada.
SENUELO = '''afinado = "completo"

[[etapa]]
id = "99"
naturaleza = "seguridad"
'''


def _foto(carpeta):
    """Nombre, tipo, tamaño, mtime y contenido de todo lo que hay bajo la carpeta."""
    foto = {}
    for raiz, dirs, archivos in os.walk(carpeta):
        for n in dirs + archivos:
            p = Path(raiz) / n
            st = p.lstat()
            sha = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else ""
            foto[str(p.relative_to(carpeta))] = (st.st_mode, st.st_size, st.st_mtime_ns, sha)
    return foto


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.man = self.tmp / "manifiestos"
        self.man.mkdir()
        self.historial = self.tmp / "historial.jsonl"
        self.lineas = [l for l in REAL.read_text(encoding="utf-8").splitlines()
                       if l.strip() and json.loads(l)["encargo"] in MUESTRA]
        self.historial.write_text("\n".join(self.lineas) + "\n", encoding="utf-8")
        (self.man / "cola-zeta.toml").write_text(MANIFIESTO, encoding="utf-8")
        (self.man / "cola-19.toml").write_text(SENUELO, encoding="utf-8")

    def correr(self, *extra):
        salida, errores = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
            rc = bal.principal(["--historial", str(self.historial), "--manifiestos", str(self.man), *extra])
        return rc, salida.getvalue(), errores.getvalue()

    def linea(self, texto, prefijo):
        encontradas = [l for l in texto.splitlines() if l.startswith(prefijo)]
        self.assertEqual(len(encontradas), 1, f"se esperaba una línea «{prefijo}» en:\n{texto}")
        return encontradas[0]


class Calculo(Base):
    def test_la_muestra_trae_las_formas_reales_pedidas(self):
        filas = [json.loads(l) for l in self.lineas]
        self.assertEqual(len(filas), 10)
        self.assertTrue(any(f["motor"] == "claude" and "usd" in f["tokens"] for f in filas))
        self.assertTrue(any(f["motor"] == "codex" and list(f["tokens"]) == ["total"] for f in filas))
        self.assertTrue(any(f.get("esfuerzo") == "" for f in filas))
        self.assertTrue(any("modelo" not in f for f in filas))
        self.assertTrue(any(not f["encargo"].isdigit() for f in filas))

    def test_total(self):
        rc, out, err = self.correr()
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("Balance de encargos 19–33b: 3 encargos, 10 fases", out)
        # A mano, de las filas reales: 40,6 min, 15,7 en fix1+rev2+fix2+rev3 del 33b (39 %);
        # USD 2,2265 de Claude, 0,3140 en retrabajo (14 %); 564.741 tokens de Codex, 159.418 en
        # retrabajo (28 %); errores de pronóstico ordenados …0,242 | 0,250… → mediana 25 %.
        self.assertEqual(self.linea(out, "TOTAL:"),
                         "TOTAL: 3 enc · 1ª 2/3 · ret min 39 % · tok C 14 % X 28 % · USD 0,74 · 188 k"
                         " · err 25 % · 16 de 41 min en retrabajo")
        self.assertLessEqual(len(out), 3500)

    def test_naturaleza_sale_del_manifiesto_y_si_no_de_la_fila(self):
        _, out, _ = self.correr()
        # 33b: el manifiesto dice diseno aunque sus filas digan menor; 19 no tiene ni lo uno ni lo otro
        self.assertIn("diseno: 1 enc · 1ª 0/1 · ret min 70 %", out)
        self.assertIn("menor: 1 enc · 1ª 1/1 · ret min 0 %", out)
        self.assertIn("sin dato: 1 enc · 1ª 1/1", self.linea(out.split("POR MOTOR")[0], "sin dato:"))
        (self.man / "cola-zeta.toml").unlink()
        _, out, _ = self.correr()
        self.assertIn("menor: 2 enc · 1ª 1/2", out)

    def test_afinado_y_experimento_por_id_de_etapa_no_por_nombre_de_archivo(self):
        _, out, _ = self.correr()
        afinado = out.split("POR AFINADO")[1].split("POR EXPERIMENTO")[0]
        experimento = out.split("POR EXPERIMENTO")[1].split("LOS 5")[0]
        self.assertIn("ligero: 2 enc · 1ª 1/2", afinado)
        # cola-19.toml dice afinado = "completo", pero su etapa es la 99: el 19 queda sin dato
        self.assertIn("sin dato: 1 enc · 1ª 1/1", afinado)
        self.assertNotIn("completo", afinado)
        self.assertIn("esfuerzo-v1: 2 enc · 1ª 1/2", experimento)
        self.assertIn("sin dato: 1 enc", experimento)
        self.assertIn("sin manifiesto: 19.", out)

    def test_combos_por_fase(self):
        _, out, _ = self.correr()
        # Haiku trae esfuerzo "": 3 fases del 33b, (3,7+3,7+3,5)/3 = 3,6 min y USD 0,4809/3 = 0,16
        self.assertIn("claude haiku-4-5 — autor: n 1 · 3,7 min · USD 0,17", out)
        self.assertIn("claude haiku-4-5 — fix: n 2 · 3,6 min · USD 0,16", out)
        # gpt-reserve medium rev: 27c rev1 y las tres del 33b → 17,1 min y 430.685 tokens entre 4
        self.assertIn("codex gpt-reserve medium rev: n 4 · 4,3 min · 108 k", out)
        # el 19 no trae modelo ni esfuerzo
        self.assertIn("codex sin dato — autor: n 1 · 4,5 min · 134 k", out)
        self.assertIn("claude sin dato — rev: n 1 · 3,3 min · USD 1,24", out)

    def test_los_mas_caros_con_sus_revisiones(self):
        _, out, _ = self.correr()
        caros = out.split("LOS 5 MÁS CAROS")[1].splitlines()[1:4]
        self.assertEqual(caros, ["33b: 22 min · USD 0,48 · 261 k · 3 rev",
                                 "27c: 10 min · USD 0,50 · 169 k · 1 rev",
                                 "19: 8 min · USD 1,24 · 134 k · 1 rev"])

    def test_desde_filtra_por_numero_y_conserva_los_sufijos(self):
        _, out, _ = self.correr("--desde", "27")
        self.assertIn("Balance de encargos 27c–33b: 2 encargos, 8 fases", out)
        _, out, _ = self.correr("--desde", "33b")
        self.assertIn("Balance de encargos 33b–33b: 1 encargos, 6 fases", out)
        rc, out, _ = self.correr("--desde", "90")
        self.assertEqual(rc, 0)
        self.assertIn("no hay fases que contar desde el 90", out)

    def test_una_rev1_repetida_vale_por_su_ultimo_veredicto(self):
        rev1 = next(json.loads(l) for l in self.lineas
                    if json.loads(l)["encargo"] == "33b" and json.loads(l)["fase"] == "rev1")
        rev1["veredicto"] = "DESPLEGABLE"
        with self.historial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rev1) + "\n")
        _, out, _ = self.correr()
        self.assertIn("TOTAL: 3 enc · 1ª 3/3", out)


class Tolerancia(Base):
    def agregar(self, *lineas):
        with self.historial.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lineas))

    def test_linea_rota_o_a_medio_escribir_se_salta_y_se_cuenta(self):
        _, antes, _ = self.correr()
        media = self.lineas[0][: len(self.lineas[0]) // 2]          # cola-run.py a mitad de un write
        self.agregar("esto no es json", "[1, 2]", '{"fase": "autor"}', "", media)
        rc, out, err = self.correr()
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(self.linea(out, "TOTAL:"), self.linea(antes, "TOTAL:"))
        self.assertIn("4 línea(s) del historial saltada(s)", out)

    def test_filas_sin_pronostico_sin_tokens_y_con_modelo_nulo(self):
        base = json.loads(self.lineas[0])
        raras = [
            dict(base, encargo="50", fase="autor", modelo=None, esfuerzo=None, naturaleza=None, tokens={},
                 pronostico=None),
            dict(base, encargo="50", fase="rev1", veredicto=None, tokens=None, min=None),
            dict(base, encargo="50", fase="fix1", tokens={"usd": "caro", "total": float("nan")}, min="mucho",
                 pronostico={"min": 0}),
            {"encargo": "51a", "fase": "rev1", "veredicto": "DESPLEGABLE"},
        ]
        self.agregar(*(json.dumps(f) for f in raras))
        rc, out, err = self.correr("--desde", "50")
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("Balance de encargos 50–51a: 2 encargos, 4 fases", out)
        # sólo cuentan los 4,5 min reales de la fila base; la rev1 sin veredicto no entra al denominador
        self.assertIn("TOTAL: 2 enc · 1ª 1/1 · ret min 0 % · tok C – X – · USD 0,00 · 0 k · err –", out)

    def test_una_fase_cortada_por_cuota_no_entra_al_error_del_pronostico(self):
        # Dos fases cortadas que «clavan» el pronóstico (error 0): si entraran, la mediana bajaría a 21 %.
        base = json.loads(self.lineas[0])
        cortada = dict(base, sin_cuota=True, min=base["pronostico"]["min"])
        self.agregar(json.dumps(cortada), json.dumps(cortada))
        _, out, _ = self.correr()
        self.assertIn("3 encargos, 12 fases", out)
        self.assertIn("err 25 %", self.linea(out, "TOTAL:"))

    def test_falta_la_carpeta_de_manifiestos_o_un_manifiesto(self):
        self.man = self.tmp / "no-existe"
        rc, out, err = self.correr()
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("sin manifiesto: 19, 27c, 33b.", out)
        self.assertIn("sin dato: 3 enc", out.split("POR AFINADO")[1])

    def test_manifiesto_roto_se_anota_y_no_bota_el_resumen(self):
        (self.man / "cola-rota.toml").write_text("esto = no es [toml", encoding="utf-8")
        (self.man / "cola-rara.toml").write_text('etapa = "no es una lista"\nafinado = 3\n', encoding="utf-8")
        rc, out, _ = self.correr()
        self.assertEqual(rc, 0)
        self.assertIn("manifiestos no leídos: cola-rota.toml.", out)
        self.assertIn("ligero: 2 enc", out)

    def test_historial_que_falta_avisa_por_stderr(self):
        self.historial.unlink()
        rc, out, err = self.correr()
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("no se pudo leer el historial", err)

    def test_texto_hostil_no_rompe_las_lineas_del_resumen(self):
        fila = dict(json.loads(self.lineas[0]), encargo="60", modelo="m\nTOTAL: 0 enc\x1b[2J", naturaleza="x" * 500)
        self.agregar(json.dumps(fila))
        _, out, _ = self.correr()
        self.linea(out, "TOTAL:")                                     # sigue habiendo una sola
        self.assertNotIn("\x1b", out)
        self.assertTrue(all(len(l) < 200 for l in out.splitlines()))

    def test_con_muchas_combinaciones_el_resumen_sigue_cabiendo(self):
        base = json.loads(self.lineas[0])
        self.agregar(*(json.dumps(dict(base, encargo=str(100 + i), modelo=f"modelo-inventado-{i}"))
                       for i in range(120)))
        _, out, _ = self.correr()
        self.assertLessEqual(len(out), 3500)
        self.assertRegex(out, r"… y \d+ combinaciones más")
        self.assertIn("LOS 5 MÁS CAROS", out)


class EntradasHostiles(Base):
    def test_no_sigue_un_enlace_simbolico_a_un_manifiesto_de_afuera(self):
        afuera = self.tmp / "afuera.toml"
        afuera.write_text('afinado = "completo"\n\n[[etapa]]\nid = "19"\nnaturaleza = "seguridad"\n',
                          encoding="utf-8")
        (self.man / "cola-enlace.toml").symlink_to(afuera)
        rc, out, _ = self.correr()
        self.assertEqual(rc, 0)
        self.assertNotIn("seguridad", out)
        self.assertNotIn("completo", out)
        self.assertIn("manifiestos no leídos: cola-enlace.toml.", out)

    def test_un_fifo_o_una_carpeta_con_nombre_de_manifiesto_no_lo_cuelgan(self):
        os.mkfifo(self.man / "cola-fifo.toml")
        (self.man / "cola-carpeta.toml").mkdir()
        p = subprocess.run([sys.executable, "-B", str(AQUI / "balance.py"), "--historial", str(self.historial),
                            "--manifiestos", str(self.man)], capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("manifiestos no leídos: cola-carpeta.toml, cola-fifo.toml.", p.stdout)

    def test_un_historial_que_es_fifo_falla_sin_colgarse(self):
        self.historial.unlink()
        os.mkfifo(self.historial)
        p = subprocess.run([sys.executable, "-B", str(AQUI / "balance.py"), "--historial", str(self.historial),
                            "--manifiestos", str(self.man)], capture_output=True, text=True, timeout=20)
        self.assertEqual((p.returncode, p.stdout), (1, ""))


class SoloLectura(Base):
    def test_no_escribe_ni_cambia_nada(self):
        # Copia de balance.py al temporal, para que sus rutas por omisión (su propia carpeta) sean
        # el temporal: se corre SIN argumentos, como lo usará la skill, y se compara todo el árbol.
        carpeta = self.tmp / "encargos"
        carpeta.mkdir()
        (carpeta / "balance.py").write_bytes((AQUI / "balance.py").read_bytes())
        (carpeta / "historial.jsonl").write_bytes(self.historial.read_bytes())
        (carpeta / "cola-zeta.toml").write_text(MANIFIESTO, encoding="utf-8")
        (carpeta / "vivo").mkdir()
        antes = _foto(self.tmp)
        hogar = self.tmp / "hogar"
        entorno = {"PATH": os.environ.get("PATH", ""), "HOME": str(hogar), "TMPDIR": str(self.tmp / "tmp")}
        p = subprocess.run([sys.executable, str(carpeta / "balance.py")], capture_output=True, text=True,
                           timeout=20, cwd=self.tmp, env=entorno)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ligero: 2 enc", p.stdout)
        despues = _foto(self.tmp)
        self.assertEqual(antes, despues)
        self.assertFalse(hogar.exists())

    def test_todo_lo_que_abre_lo_abre_para_leer(self):
        abiertos = []
        os_open = os.open

        def espia(ruta, banderas, *a, **kw):
            abiertos.append((ruta, banderas))
            return os_open(ruta, banderas, *a, **kw)

        def sin_open(*a, **kw):
            raise AssertionError(f"balance.py no debe usar open(): {a}")

        with mock.patch.object(bal.os, "open", espia), mock.patch("builtins.open", sin_open):
            rc, out, _ = self.correr()
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(len(abiertos), 4)      # historial, carpeta y los dos manifiestos
        escritura = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
        self.assertEqual([r for r, b in abiertos if b & escritura], [])

    def test_el_temporal_de_las_pruebas_queda_fuera_del_volumen(self):
        self.assertFalse(str(self.tmp.resolve()).startswith("/opt/nodo/datos"))


if __name__ == "__main__":
    unittest.main()
