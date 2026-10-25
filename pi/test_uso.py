#!/usr/bin/env python3
"""Pruebas del lector de rollouts de Codex.

    python3 test_uso.py
"""
import importlib.util
import json
import tempfile
import unittest
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("uso", Path(__file__).with_name("uso.py"))
uso = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uso)
SPEC_EQUIPO = importlib.util.spec_from_file_location("uso_equipo", Path(__file__).with_name("uso-equipo.py"))
equipo = importlib.util.module_from_spec(SPEC_EQUIPO)
SPEC_EQUIPO.loader.exec_module(equipo)


class CodexRolloutTests(unittest.TestCase):
    def test_acumula_tokens_y_usa_el_limite_mas_reciente(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp, "2026", "rollout-prueba.jsonl")
            rollout.parent.mkdir()
            primero = datetime(2026, 9, 29, 12, 0, tzinfo=uso.TZ)
            segundo = datetime(2026, 9, 29, 13, 0, tzinfo=uso.TZ)
            eventos = [
                {"timestamp": primero.isoformat(), "payload": {
                    "type": "token_count",
                    "info": {"total_token_usage": {"input_tokens": 100,
                                                      "cached_input_tokens": 20,
                                                      "output_tokens": 30}},
                    "rate_limits": {"primary": {"used_percent": 6.0,
                                                   "resets_at": int(segundo.timestamp())},
                                    "secondary": {"used_percent": 3.0,
                                                  "resets_at": int(segundo.timestamp())},
                                    "plan_type": "plus"}}},
                {"timestamp": segundo.isoformat(), "payload": {
                    "type": "token_count",
                    "info": {"total_token_usage": {"input_tokens": 150,
                                                      "cached_input_tokens": 30,
                                                      "output_tokens": 50}},
                    "rate_limits": {"primary": {"used_percent": 9.0,
                                                   "resets_at": int(segundo.timestamp())},
                                    "secondary": {"used_percent": 7.0,
                                                  "resets_at": int(segundo.timestamp())},
                                    "plan_type": "plus"}}},
            ]
            rollout.write_text("".join(json.dumps(e) + "\n" for e in eventos), encoding="utf-8")
            resultado = uso.codex_por_hora([tmp], incluir_limites=True)

        self.assertEqual(resultado["por_hora"]["2026-09-29T12"]["entrada"], 80)
        self.assertEqual(resultado["por_hora"]["2026-09-29T13"]["entrada"], 40)
        self.assertEqual(resultado["por_hora"]["2026-09-29T13"]["salida"], 20)
        self.assertEqual(resultado["limites"]["momento"], segundo.isoformat(timespec="seconds"))
        self.assertEqual(resultado["limites"]["plan"], "plus")
        self.assertEqual(resultado["limites"]["ventana_5h"]["usado_pct"], 9.0)
        self.assertEqual(resultado["limites"]["semanal"]["usado_pct"], 7.0)
        self.assertEqual(resultado["limites"]["semanal"]["renueva"], segundo.isoformat(timespec="seconds"))


class ClaudeLimitesTests(unittest.TestCase):
    def test_cache_claude_usa_respaldo_y_tolera_json_truncado(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp, ".claude.json")
            archivo.write_text(json.dumps({
                "oauthAccount": {"subscriptionType": "pro"},
                "cachedUsageUtilization": {
                    "fetchedAtMs": 1790729838100,
                    "utilization": {
                        # Falta five_hour: corresponde usar limits/session.
                        "seven_day": {"utilization": 7, "resets_at": "2026-10-05T01:00:00+00:00"},
                        "limits": [
                            {"kind": "session", "percent": 3,
                             "resets_at": "2026-09-30T05:10:00+00:00"}
                        ],
                    },
                },
            }), encoding="utf-8")
            config = {"cuenta": "prueba", "archivo": str(archivo)}
            with patch.object(uso, "_refrescar_limite_claude"):
                limites = uso.limites_claude(config)
            self.assertEqual(limites["plan"], "pro")
            self.assertEqual(limites["momento"], "2026-09-29T21:57:18-03:00")
            self.assertEqual(limites["ventana_5h"],
                             {"usado_pct": 3, "renueva": "2026-09-30T05:10:00+00:00"})
            self.assertEqual(limites["semanal"]["usado_pct"], 7)

            # La otra cuenta puede estar justo reemplazando el archivo: no rompe ni inventa datos.
            archivo.write_text('{"cachedUsageUtilization": ', encoding="utf-8")
            with patch.object(uso, "_refrescar_limite_claude"):
                self.assertIsNone(uso.limites_claude(config))


class UsoEquipoTests(unittest.TestCase):
    def _entorno_pc(self, raiz):
        perfil, local = Path(raiz, "C", "Users", "Diego"), Path(raiz, "local")
        (perfil / ".claude" / "projects" / "proyecto-real").mkdir(parents=True)
        (perfil / ".codex" / "sessions" / "2026").mkdir(parents=True)
        (perfil / ".claude.json").write_text(json.dumps({"oauthAccount": {"emailAddress": "nadie@ejemplo.cl"}}))
        return perfil, local

    def test_incremental_con_las_fixtures_reales_y_deduplicacion_persistente(self):
        """Tres líneas reales anonimizadas, en dos corridas y un transcript copiado."""
        with tempfile.TemporaryDirectory() as raiz:
            perfil, local = self._entorno_pc(raiz)
            fixtures = Path(__file__).parent / "fixtures" / "uso-equipo"
            claude_lineas = (fixtures / "claude-real-anon.jsonl").read_text(encoding="utf-8").splitlines(True)
            codex_lineas = (fixtures / "codex-real-anon.jsonl").read_text(encoding="utf-8").splitlines(True)
            claude_ruta = perfil / ".claude" / "projects" / "proyecto-real" / "sesion.jsonl"
            codex_ruta = perfil / ".codex" / "sessions" / "2026" / "rollout-prueba.jsonl"
            claude_ruta.write_text("".join(claude_lineas[:2]), encoding="utf-8", newline="\n")
            codex_ruta.write_text("".join(codex_lineas[:2]), encoding="utf-8", newline="\n")
            viejo = {k: os.environ.get(k) for k in ("USERPROFILE", "LOCALAPPDATA", "COMPUTERNAME")}
            os.environ.update({"USERPROFILE": str(perfil), "LOCALAPPDATA": str(local), "COMPUTERNAME": "PC-Diego"})
            try:
                primero = equipo.ejecutar(raiz=raiz)
                # La segunda corrida trae datos nuevos reales, no sólo una cola vacía.
                with claude_ruta.open("a", encoding="utf-8", newline="\n") as fh: fh.write(claude_lineas[2])
                with codex_ruta.open("a", encoding="utf-8", newline="\n") as fh: fh.write(codex_lineas[2])
                # --resume/fork: el requestId antiguo vuelve a aparecer en otro transcript.
                copia = perfil / ".claude" / "projects" / "proyecto-copiado"
                copia.mkdir()
                (copia / "sesion.jsonl").write_text(claude_lineas[0], encoding="utf-8", newline="\n")
                segundo = equipo.ejecutar(raiz=raiz)
            finally:
                for k, v in viejo.items():
                    if v is None: os.environ.pop(k, None)
                    else: os.environ[k] = v
            self.assertIn("claude_desconocida", primero["cuentas"])
            self.assertTrue(primero["cuentas"]["claude_desconocida"]["por_hora"])
            esperado_claude = uso.claude_por_hora(str(perfil / ".claude" / "projects"))
            esperado_codex = uso.codex_por_hora([str(perfil / ".codex" / "sessions")])
            self.assertEqual(segundo["cuentas"]["claude_desconocida"]["por_hora"], esperado_claude)
            self.assertEqual(segundo["cuentas"]["codex"]["por_hora"], esperado_codex)

    def test_publicacion_fallida_no_confirma_los_cursores(self):
        with tempfile.TemporaryDirectory() as raiz:
            perfil, local = self._entorno_pc(raiz)
            shutil.copy(Path(__file__).parent / "fixtures" / "uso-equipo" / "codex-real-anon.jsonl",
                        perfil / ".codex" / "sessions" / "2026" / "rollout-real.jsonl")
            Path(raiz, "uso-equipos").write_text("bloquea directorio", encoding="utf-8")
            viejo = {k: os.environ.get(k) for k in ("USERPROFILE", "LOCALAPPDATA", "COMPUTERNAME")}
            os.environ.update({"USERPROFILE": str(perfil), "LOCALAPPDATA": str(local), "COMPUTERNAME": "PC-2503"})
            try:
                with self.assertRaises(FileExistsError):
                    equipo.ejecutar(raiz=raiz)
                self.assertFalse((local / "uso-equipo" / "estado.json").exists())
                Path(raiz, "uso-equipos").unlink()
                Path(raiz, "uso-equipos").mkdir()
                recuperado = equipo.ejecutar(raiz=raiz)
            finally:
                for k, v in viejo.items():
                    if v is None: os.environ.pop(k, None)
                    else: os.environ[k] = v
            esperado = uso.codex_por_hora([str(perfil / ".codex" / "sessions")])
            self.assertEqual(recuperado["cuentas"]["codex"]["por_hora"], esperado)

    def test_reporte_corrupto_reinicia_cursores_y_reconstruye_las_fixtures_reales(self):
        with tempfile.TemporaryDirectory() as raiz:
            perfil, local = self._entorno_pc(raiz)
            shutil.copy(Path(__file__).parent / "fixtures" / "uso-equipo" / "codex-real-anon.jsonl",
                        perfil / ".codex" / "sessions" / "2026" / "rollout-real.jsonl")
            viejo = {k: os.environ.get(k) for k in ("USERPROFILE", "LOCALAPPDATA", "COMPUTERNAME")}
            os.environ.update({"USERPROFILE": str(perfil), "LOCALAPPDATA": str(local), "COMPUTERNAME": "PC-2503"})
            try:
                equipo.ejecutar(raiz=raiz)
                (Path(raiz) / "uso-equipos" / "PC-2503.json").write_text("{truncado", encoding="utf-8")
                recuperado = equipo.ejecutar(raiz=raiz)
            finally:
                for k, v in viejo.items():
                    if v is None: os.environ.pop(k, None)
                    else: os.environ[k] = v
            esperado = uso.codex_por_hora([str(perfil / ".codex" / "sessions")])
            self.assertEqual(recuperado["cuentas"]["codex"]["por_hora"], esperado)

    def test_importa_sin_pwd_ni_base_iana(self):
        with tempfile.TemporaryDirectory() as vacio:
            codigo = '''import importlib.util, json, os, pathlib, shutil, sys, tempfile
sys.modules["pwd"] = None
script, fixture = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("u", script)
lector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lector)
with tempfile.TemporaryDirectory() as raiz:
    raiz = pathlib.Path(raiz)
    perfil = raiz / "C" / "Users" / "Diego"
    (perfil / ".claude" / "projects" / "real").mkdir(parents=True)
    (perfil / ".codex" / "sessions" / "2026").mkdir(parents=True)
    (perfil / ".claude.json").write_text(json.dumps({"oauthAccount": {"emailAddress": "nadie@ejemplo.cl"}}))
    shutil.copy(fixture / "claude-real-anon.jsonl", perfil / ".claude" / "projects" / "real" / "s.jsonl")
    shutil.copy(fixture / "codex-real-anon.jsonl", perfil / ".codex" / "sessions" / "2026" / "rollout-real.jsonl")
    os.environ.update({"USERPROFILE": str(perfil), "LOCALAPPDATA": str(raiz / "local"), "COMPUTERNAME": "PC-Windows"})
    salida = lector.ejecutar(raiz=raiz)
    print(lector.uso.TZ_ES_LOCAL, sum(x["mensajes"] for x in salida["cuentas"]["claude_desconocida"]["por_hora"].values()), sum(x["mensajes"] for x in salida["cuentas"]["codex"]["por_hora"].values()))'''
            env = {**os.environ, "PYTHONTZPATH": vacio}
            r = subprocess.run([sys.executable, "-c", codigo, str(Path(__file__).with_name("uso-equipo.py")),
                                str(Path(__file__).parent / "fixtures" / "uso-equipo")],
                               env=env, text=True, capture_output=True, check=True)
        self.assertEqual(r.stdout.strip(), "True 3 3")

    def test_uso_pi_separa_reporte_viejo(self):
        with tempfile.TemporaryDirectory() as raiz:
            Path(raiz, "nuevo.json").write_text(json.dumps({"actualizado": "2026-09-30T11:00:00-03:00", "cuentas": {}}))
            Path(raiz, "viejo.json").write_text(json.dumps({"actualizado": "2026-01-01T00:00:00-03:00", "cuentas": {}}))
            anterior = uso.USO_EQUIPOS
            uso.USO_EQUIPOS = raiz
            try:
                r = uso.equipos_uso(datetime(2026, 9, 30, 12, tzinfo=uso.TZ))
            finally:
                uso.USO_EQUIPOS = anterior
        self.assertEqual(set(r["activos"]), {"nuevo"})
        self.assertEqual(set(r["vencidos"]), {"viejo"})


if __name__ == "__main__":
    unittest.main()
