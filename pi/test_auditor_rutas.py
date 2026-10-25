"""Pruebas del 🔎 auditor de rutas (encargo 94): `alertas_rutas()` de pi/estado.py.

Todo en `tempfile`, con un /opt/botv3 de mentira (perfiles, cuentas.toml y el recetas.py de
este repo) y registros `uso-cuentas.jsonl` inventados. No escribe en /opt ni usa la red.

    python3 pi/test_auditor_rutas.py
"""
import datetime as dt
import importlib.util
import json
import os
import pwd
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("estado_auditor", RAIZ / "pi" / "estado.py")
estado = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(estado)

TZ = dt.timezone(dt.timedelta(hours=-3))
AHORA = dt.datetime(2026, 10, 25, 12, 0, tzinfo=TZ)
YO = pwd.getpwuid(os.getuid()).pw_name


def linea(perfil, ruta, cuenta, ok=True, horas=1.0, motor=None, modelo=None, **extra):
    motor = motor or {"claude_diego": "claude", "claude_cami": "claude"}.get(cuenta, cuenta)
    d = {"ts": (AHORA - dt.timedelta(hours=horas)).isoformat(timespec="seconds"),
         "id": "abc123abc123", "perfil": perfil, "ruta": ruta, "ruta_nombre": ruta,
         "cuenta": cuenta, "motor": motor, "modelo": modelo, "ok": ok, "s": 3.2, "tokens": None}
    d.update(extra)
    return json.dumps(d, ensure_ascii=False)


class AuditorRutas(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="auditor94-"))
        self.bot = self.tmp / "botv3"
        (self.bot / "perfiles").mkdir(parents=True)
        shutil.copy(RAIZ / "botv3" / "recetas.py", self.bot / "recetas.py")
        shutil.copy(RAIZ / "botv3" / "cuentas.toml", self.bot / "cuentas.toml")
        for p in ("jaime", "pilar"):
            shutil.copy(RAIZ / "botv3" / "perfiles" / f"{p}.toml", self.bot / "perfiles" / f"{p}.toml")
        self.registros = {}
        for p in ("jaime", "pilar"):
            d = self.tmp / f"estado-{p}"
            d.mkdir()
            self.registros[p] = {"registro": str(d / "uso-cuentas.jsonl"),
                                 "catalogo": str(d / "modelos-catalogo.json"), "dueno": YO}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def escribir(self, perfil, lineas):
        Path(self.registros[perfil]["registro"]).write_text(
            "".join(x + "\n" for x in lineas), encoding="utf-8")

    def correr(self):
        return {a["id"]: a["texto"] for a in
                estado.alertas_rutas(ahora=AHORA, bot_dir=str(self.bot), registros=self.registros)}

    def autorizado(self):
        self.escribir("jaime", [linea("jaime", "claude", "claude_diego"),
                                linea("jaime", "codex", "codex"),
                                linea("jaime", "web", "claude_cami"),
                                linea("jaime", "web", "claude_diego"),
                                linea("jaime", "boleta", "gemini")])
        self.escribir("pilar", [linea("pilar", "claude", "claude_cami"),
                                linea("pilar", "codex", "claude_cami", ok=False),
                                linea("pilar", "codex", "codex"),
                                linea("pilar", "web", "claude_cami"),
                                json.dumps({"tipo": "calificacion", "id": "abc123abc123", "valor": 1})])

    def test_todo_autorizado_no_avisa(self):
        self.autorizado()
        self.assertEqual(self.correr(), {})

    def test_96_lineas_con_selector_y_canal_no_dan_avisos_falsos(self):
        # Encargo 96: el libro suma `selector` y `canal` cuando la pregunta vino por «pregunta técnica: …». Son claves
        # nuevas: el auditor las ignora. Con la receta automática de la técnica (la propuesta de Diego), Jaime puede
        # contestar con las tres cuentas, y la lista blanca lo sigue.
        toml = self.bot / "perfiles" / "jaime.toml"
        toml.write_text(toml.read_text(encoding="utf-8") + "\nrecetas = { tecnica = { automatico = true } }\n", encoding="utf-8")
        self.escribir("jaime", [linea("jaime", "codex", c, selector="tecnica", canal=canal)
                                for c, canal in (("codex", "voz"), ("claude_diego", "texto"), ("claude_cami", "texto"))])
        self.escribir("pilar", [linea("pilar", "codex", "codex", selector="tecnica", canal="voz"),
                                linea("pilar", "gpt", "groq", selector="rapida", canal="texto")])
        self.assertEqual(self.correr(), {})
        # Sin la receta, Claude (Diego) en la técnica de Jaime sí es un aviso (la lista blanca no se ensancha sola).
        toml.write_text(toml.read_text(encoding="utf-8").replace("recetas = { tecnica = { automatico = true } }", ""), encoding="utf-8")
        self.assertIn("rutas:cuenta:jaime:codex:claude_diego", self.correr())

    def test_pilar_web_por_codex_avisa(self):
        self.autorizado()
        with open(self.registros["pilar"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("pilar", "web", "codex", ok=False, horas=2) + "\n")
        al = self.correr()
        self.assertEqual(list(al), ["rutas:cuenta:pilar:web:codex"])
        texto = al["rutas:cuenta:pilar:web:codex"]
        self.assertTrue(texto.startswith("🚩"))
        self.assertIn("Pilar → web → Codex", texto)

    def test_jaime_web_por_codex_tambien_avisa_aunque_el_perfil_lo_declare(self):
        # jaime.toml dice web = ["codex", ...], pero el muro 11 lo ignora en el bot.
        self.autorizado()
        with open(self.registros["jaime"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("jaime", "web", "codex") + "\n")
        self.assertIn("rutas:cuenta:jaime:web:codex", self.correr())

    def test_ruta_fuera_del_perfil(self):
        self.autorizado()
        with open(self.registros["pilar"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("pilar", "noticias", "claude_cami") + "\n")
        al = self.correr()
        self.assertEqual(list(al), ["rutas:ruta:pilar:noticias"])

    def test_forzada_fuera_de_la_cadena_avisa_marcada(self):
        self.autorizado()
        with open(self.registros["pilar"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("pilar", "claude", "claude_diego", forzada=True) + "\n")
        self.assertIn("(forzada)", self.correr()["rutas:cuenta:pilar:claude:claude_diego"])

    def test_ruta_muerta_tapada_por_el_respaldo(self):
        # Claude (Cami) muerta en la web de Jaime; Claude (Diego) contesta cada vez.
        lineas = []
        for h in (6, 4, 2):
            lineas += [linea("jaime", "web", "claude_cami", ok=False, horas=h),
                       linea("jaime", "web", "claude_diego", horas=h - 0.01)]
        self.escribir("jaime", lineas)
        self.escribir("pilar", [linea("pilar", "claude", "claude_cami")])
        al = self.correr()
        self.assertEqual(list(al), ["rutas:muerta:jaime:web:claude_cami"])
        self.assertIn("3 veces seguidas", al["rutas:muerta:jaime:web:claude_cami"])
        self.assertIn("el respaldo contestó 3 veces", al["rutas:muerta:jaime:web:claude_cami"])

    def test_dos_fallas_o_un_ok_en_medio_no_es_ruta_muerta(self):
        self.escribir("jaime", [linea("jaime", "web", "claude_cami", ok=False, horas=6),
                                linea("jaime", "web", "claude_cami", ok=False, horas=5),
                                linea("jaime", "web", "claude_cami", ok=True, horas=4),
                                linea("jaime", "web", "claude_cami", ok=False, horas=3),
                                linea("jaime", "web", "claude_cami", ok=False, horas=2)])
        self.escribir("pilar", [linea("pilar", "claude", "claude_cami")])
        self.assertEqual(self.correr(), {})

    def test_fallas_de_hace_mas_de_24_h_no_cuentan(self):
        self.escribir("jaime", [linea("jaime", "web", "claude_cami", ok=False, horas=h) for h in (40, 30, 26)])
        self.escribir("pilar", [linea("pilar", "claude", "claude_cami")])
        self.assertEqual(self.correr(), {})

    def test_cuenta_desconocida(self):
        self.autorizado()
        with open(self.registros["jaime"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("jaime", "claude", "claude_tercera", motor="claude") + "\n")
        al = self.correr()
        self.assertIn("rutas:desconocida:claude_tercera", al)
        self.assertIn("Jaime", al["rutas:desconocida:claude_tercera"])
        # Y tampoco está en la cadena de su ruta.
        self.assertIn("rutas:cuenta:jaime:claude:claude_tercera", al)

    def test_motor_que_no_calza_con_cuentas_toml(self):
        self.autorizado()
        with open(self.registros["jaime"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("jaime", "codex", "codex", motor="claude") + "\n")
        self.assertIn("rutas:motor:codex:claude", self.correr())

    def test_modelo_fuera_del_catalogo(self):
        self.autorizado()
        Path(self.registros["jaime"]["catalogo"]).write_text(json.dumps({
            "momento": AHORA.isoformat(), "modelos": [
                {"proveedor": "gemini", "modelo": "gemini-2.5-flash", "rol": "receta", "estado": "presente"}]}),
            encoding="utf-8")
        with open(self.registros["jaime"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("jaime", "boleta", "gemini", modelo="gemini-2.5-flash") + "\n")
            fh.write(linea("jaime", "boleta", "gemini", modelo="gemini-9-fantasma") + "\n")
        al = self.correr()
        self.assertEqual(list(al), ["rutas:modelo:jaime:gemini:gemini-9-fantasma"])

    def test_perfil_que_cambia_por_propuesta(self):
        self.autorizado()
        with open(self.registros["pilar"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("pilar", "claude", "claude_diego") + "\n")
        self.assertIn("rutas:cuenta:pilar:claude:claude_diego", self.correr())
        # Propuesta aprobada: Pilar suma Claude (Diego) de respaldo en `claude`.
        toml = self.bot / "perfiles" / "pilar.toml"
        texto = toml.read_text(encoding="utf-8")
        nuevo = texto.replace('cuentas = { claude = ["claude_cami"]',
                              'cuentas = { claude = ["claude_cami", "claude_diego"]')
        self.assertNotEqual(texto, nuevo)
        toml.write_text(nuevo, encoding="utf-8")
        self.assertEqual(self.correr(), {})
        # Y si otra propuesta le quita `codex` de las rutas, sus líneas de codex avisan.
        toml.write_text(nuevo.replace('"claude", "codex", "boleta"]', '"claude", "boleta"]'), encoding="utf-8")
        self.assertIn("rutas:ruta:pilar:codex", self.correr())

    def test_dedup_id_estable_y_un_solo_aviso_por_hallazgo(self):
        self.autorizado()
        with open(self.registros["pilar"]["registro"], "a", encoding="utf-8") as fh:
            for h in (5, 3, 1):
                fh.write(linea("pilar", "web", "codex", horas=h) + "\n")
        primero = self.correr()
        self.assertEqual(list(primero), ["rutas:cuenta:pilar:web:codex"])
        self.assertIn("3 veces", primero["rutas:cuenta:pilar:web:codex"])
        with open(self.registros["pilar"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("pilar", "web", "codex", horas=0.5) + "\n")
        segundo = self.correr()
        # Mismo id (avisos.py no lo repite); solo cambia la cantidad del texto.
        self.assertEqual(list(segundo), list(primero))
        # Pasado el plazo de 7 días sin líneas nuevas, se resuelve solo.
        self.escribir("pilar", [linea("pilar", "web", "codex", horas=24 * 8)])
        self.assertEqual(self.correr(), {})

    def test_registro_ausente_lo_dice_una_vez_y_no_se_cae(self):
        self.escribir("jaime", [linea("jaime", "claude", "claude_diego")])
        al = self.correr()
        self.assertEqual(list(al), ["rutas:registro:pilar"])
        self.assertEqual(al, self.correr())  # id estable: avisos.py lo manda una sola vez

    def test_registro_roto_no_se_cae(self):
        self.escribir("jaime", ["{no es json", "[]", '{"ts": "ayer"}', "\x00\x01",
                                linea("jaime", "claude", "claude_diego")])
        self.escribir("pilar", [linea("pilar", "claude", "claude_cami")])
        al = self.correr()
        self.assertEqual(list(al), ["rutas:registro:jaime"])
        self.assertIn("4 líneas", al["rutas:registro:jaime"])

    def test_una_linea_cortada_sola_no_avisa(self):
        self.escribir("jaime", [linea("jaime", "claude", "claude_diego")] * 20 + ['{"ts": "2026-10'])
        self.escribir("pilar", [linea("pilar", "claude", "claude_cami")])
        self.assertEqual(self.correr(), {})

    def test_registro_que_es_enlace_no_se_sigue(self):
        self.escribir("pilar", [linea("pilar", "claude", "claude_cami")])
        os.symlink(self.registros["pilar"]["registro"], self.registros["jaime"]["registro"])
        al = self.correr()
        self.assertEqual(list(al), ["rutas:registro:jaime"])
        self.assertIn("no se puede leer con seguridad", al["rutas:registro:jaime"])

    def test_cola_acotada_descarta_la_primera_linea_cortada(self):
        viejo = estado.MAX_REGISTRO_USO
        try:
            estado.MAX_REGISTRO_USO = 2000
            self.escribir("jaime", [linea("jaime", "web", "codex", horas=1)] +
                          [linea("jaime", "claude", "claude_diego")] * 40)
            self.escribir("pilar", [linea("pilar", "claude", "claude_cami")])
            # La línea mala quedó fuera de la cola; la primera de la cola, cortada, se descarta.
            self.assertEqual(self.correr(), {})
        finally:
            estado.MAX_REGISTRO_USO = viejo

    def test_perfil_ilegible_y_cuentas_toml_ilegible(self):
        self.autorizado()
        (self.bot / "perfiles" / "pilar.toml").write_text("rutas = [", encoding="utf-8")
        (self.bot / "cuentas.toml").write_text("no = es = toml", encoding="utf-8")
        al = self.correr()
        self.assertEqual(sorted(al), ["rutas:cuentas_toml", "rutas:perfil:pilar"])

    def test_sin_recetas_se_detiene_y_lo_dice(self):
        (self.bot / "recetas.py").unlink()
        self.assertEqual(list(self.correr()), ["rutas:recetas"])

    def test_los_avisos_no_llevan_texto_de_mensajes(self):
        self.autorizado()
        with open(self.registros["pilar"]["registro"], "a", encoding="utf-8") as fh:
            fh.write(linea("pilar", "web", "codex", texto="secreto de Camila", pregunta="otra cosa") + "\n")
        for t in self.correr().values():
            self.assertNotIn("secreto", t)
            self.assertNotIn("otra cosa", t)

    def test_alertas_no_se_cae_si_el_auditor_revienta(self):
        originales = (estado.alertas_rutas, estado.alertas_catalogo_modelos, estado.config_error_luces)
        try:
            estado.alertas_rutas = lambda: 1 / 0
            estado.alertas_catalogo_modelos = lambda: []
            e = {"luks": {"abierto": True}, "servicios": {}, "contenedores": [],
                 "respaldo": {"montado": True, "horas": 1, "en_disco_aparte": True},
                 "salud": {"unidades_fallidas": [], "reloj_ntp": True, "errores_io": 0},
                 "nvme_errores": 0, "sync": {"carpetas": []}, "medidores": {}}
            estado.config_error_luces = lambda: None
            ids = [a["id"] for a in estado.alertas(e)]
            self.assertEqual(ids, ["rutas:fallo"])
        finally:
            estado.alertas_rutas, estado.alertas_catalogo_modelos, estado.config_error_luces = originales


if __name__ == "__main__":
    unittest.main(verbosity=2)
