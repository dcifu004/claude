#!/usr/bin/env python3
"""Pruebas de pi/temblores.py (encargo 91). Red simulada (un `abrir` que sirve los fixtures), canal real
(encargos/registro_avisos.py con NODO_AVISOS_DIR) y descanso real (pi/descanso.py con sus rutas en un
temporal). Nada se escribe fuera del temporal.

    NODO_PRUEBAS=1 python3 -B -m unittest pi/test_temblores.py
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

AQUI = Path(__file__).resolve().parent
FIJ = AQUI / "fixtures" / "temblores"
_TMP = tempfile.TemporaryDirectory(prefix="temblores-")
# descanso.py lee sus rutas del entorno al cargarse: van al temporal antes de cargarlo.
os.environ.update(NODO_PRUEBAS="1", NODO_DESCANSO_CONFIG=str(Path(_TMP.name) / "descanso.toml"),
                  NODO_DESCANSO_CACHE=str(Path(_TMP.name) / "descanso-cache"),
                  NODO_DESCANSO_STATE=str(Path(_TMP.name) / "descanso-estado"))


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tb = cargar("temblores_91", AQUI / "temblores.py")
descanso = cargar("descanso_91", AQUI / "descanso.py")
AHORA = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)     # domingo 15:00 en Chile: fuera de descanso
NOCHE = datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc)      # martes 03:00 en Chile: en descanso


class Respuesta(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def red(usgs=None, emsc=None):
    """Un urlopen falso. `usgs`/`emsc`: bytes, una excepción o None (el fixture de forma)."""
    cuerpos = {"usgs": usgs if usgs is not None else (FIJ / "forma-usgs-4.5_day.json").read_bytes(),
               "emsc": emsc if emsc is not None else (FIJ / "forma-emsc-fdsn.json").read_bytes()}
    pedidas = []

    def abrir(req, timeout=None):
        url = req.full_url
        pedidas.append(url)
        cuerpo = cuerpos["usgs" if "usgs.gov" in url else "emsc"]
        if isinstance(cuerpo, Exception):
            raise cuerpo
        return Respuesta(cuerpo)
    abrir.pedidas = pedidas
    return abrir


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=_TMP.name)
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        perfil = self.d / "jaime.toml"
        # La forma del perfil real: la casa a nivel de comuna (la misma línea de botv3/perfiles/jaime.toml).
        linea = next(x for x in (AQUI.parent / "botv3/perfiles/jaime.toml").read_text(encoding="utf-8").splitlines()
                     if x.startswith("clima ="))
        perfil.write_text(linea + "\n", encoding="utf-8")
        self.cfg = tb.cargar_config(AQUI / "temblores.toml")
        self.cfg["perfil"] = str(perfil)
        self.estado = self.d / "estado" / "estado.json"
        # Canal real: registro_avisos.py con su bandeja y su registro en el temporal (NODO_AVISOS_DIR).
        self.avisos_dir = self.d / "avisos"
        self.avisos_dir.mkdir()
        os.environ["NODO_AVISOS_DIR"] = str(self.avisos_dir)
        self.ra = cargar(f"registro_avisos_{id(self)}", AQUI.parent / "encargos" / "registro_avisos.py")
        self.ra.BANDEJA_ESTADO = self.d / "avisos-bandeja.json"
        self.bandeja_activa(True)

    def bandeja_activa(self, si):
        datos = {"version": 1, "ultimo_ciclo": time.time(), "ok": si}
        self.ra.BANDEJA_ESTADO.write_text(json.dumps(datos), encoding="utf-8")

    def correr(self, abrir=None, ahora=AHORA, **k):
        return tb.correr(self.cfg, self.estado, ahora, abrir or red(), self.ra, descanso, **k)

    def bandeja(self):
        ruta = self.avisos_dir / "avisos-salida.jsonl"
        return [json.loads(x)["texto"] for x in ruta.read_text(encoding="utf-8").splitlines()] if ruta.exists() else []

    def registro(self):
        ruta = self.avisos_dir / "avisos.jsonl"
        return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()] if ruta.exists() else []


class Distancia(unittest.TestCase):
    def test_haversine(self):
        self.assertAlmostEqual(tb.haversine_km(-33.45, -70.66, -33.05, -71.62), 99.0, delta=3)     # Santiago–Valparaíso
        self.assertAlmostEqual(tb.haversine_km(0, 0, 0, 180), 20015.1, delta=1)
        self.assertEqual(tb.haversine_km(-33.41, -70.57, -33.41, -70.57), 0.0)
        self.assertAlmostEqual(tb.haversine_km(-33.41, -70.57, -23.65, -70.40), tb.haversine_km(-23.65, -70.40, -33.41, -70.57))

    def test_la_casa_sale_del_perfil_real(self):
        lat, lon = tb.casa(AQUI.parent / "botv3/perfiles/jaime.toml")
        self.assertEqual((lat, lon), (-33.41, -70.57))
        for malo in ("clima = { lugar = \"x\" }\n", "otra = 1\n", "clima = { lat = 200, lon = 0 }\n"):
            with tempfile.NamedTemporaryFile("w", suffix=".toml", dir=_TMP.name, delete=False) as fh:
                fh.write(malo)
            with self.assertRaises(ValueError):
                tb.casa(fh.name)


class Umbrales(Base):
    def sismo(self, mag, lat, lon, t=AHORA - timedelta(minutes=10)):
        return tb.Sismo("usgs", "x", ("x",), mag, "lugar", t, lat, lon, 10.0, "https://ejemplo")

    def punto_a(self, km):
        """Un epicentro a `km` al oeste de la casa, sobre su mismo paralelo (casi)."""
        lat, lon = tb.casa(self.cfg["perfil"])
        dlon = km / (111.32 * __import__("math").cos(__import__("math").radians(lat)))
        return lat, lon - dlon

    def test_bordes_de_magnitud_y_distancia(self):
        hogar = tb.casa(self.cfg["perfil"])
        cerca = self.punto_a(299.5)
        lejos = self.punto_a(301)
        self.assertEqual(tb.evaluar(self.sismo(5.0, *cerca), hogar, self.cfg)[:2], (True, False))
        self.assertEqual(tb.evaluar(self.sismo(4.9, *cerca), hogar, self.cfg)[:2], (False, False))
        self.assertEqual(tb.evaluar(self.sismo(5.5, *lejos), hogar, self.cfg)[:2], (False, False))
        self.assertEqual(tb.evaluar(self.sismo(6.5, *cerca), hogar, self.cfg)[:2], (True, True))
        self.assertEqual(tb.evaluar(self.sismo(6.4, *cerca), hogar, self.cfg)[:2], (True, False))

    def test_chile_y_urgente_lejano(self):
        hogar = tb.casa(self.cfg["perfil"])
        self.assertEqual(tb.evaluar(self.sismo(6.5, -23.35, -70.30), hogar, self.cfg)[:2], (True, False))   # Antofagasta
        self.assertEqual(tb.evaluar(self.sismo(6.4, -23.35, -70.30), hogar, self.cfg)[:2], (False, False))
        self.assertEqual(tb.evaluar(self.sismo(7.0, 39.6, 143.35), hogar, self.cfg)[:2], (False, False))     # Japón
        self.assertEqual(tb.evaluar(self.sismo(7.5, -38.0, -73.5), hogar, self.cfg)[:2], (True, True))       # ~600 km
        self.assertEqual(tb.evaluar(self.sismo(7.6, -27.0, -67.0), hogar, self.cfg)[:2], (True, True))       # ~790 km
        self.assertEqual(tb.evaluar(self.sismo(7.6, -24.5, -66.5), hogar, self.cfg)[:2], (True, False))      # ~1060 km: Chile, no urgente

    def test_config_rota_no_silencia(self):
        for malo in ('max_edad_h = "tres"\n', 'fuentes = ["csn"]\n', '[[regla]]\nmag = 5\n', 'urgente = []\n'):
            ruta = self.d / "malo.toml"
            ruta.write_text(malo, encoding="utf-8")
            with self.assertRaises(ValueError, msg=malo):
                tb.cargar_config(ruta)
        self.assertEqual(tb.cargar_config(self.d / "no-existe.toml")["regla"], tb.DEFECTO["regla"])
        self.assertEqual(tb.cargar_config(AQUI / "temblores.toml")["urgente"],
                         [{"mag": 6.5, "km": 300}, {"mag": 7.5, "km": 1000}])


class Fuentes(Base):
    def test_lectores_sobre_la_forma_documentada(self):
        usgs, malos = tb.leer_usgs((FIJ / "forma-usgs-4.5_day.json").read_bytes())
        self.assertEqual((len(usgs), malos), (6, 1))
        s = usgs[0]
        self.assertEqual((s.id, s.mag, s.lat, s.lon, s.prof), ("us7000r1a1", 5.4, -33.05, -71.75, 31.2))
        self.assertEqual(s.ids, ("us7000r1a1", "gu2026uvwx"))
        self.assertEqual(s.t, datetime(2026, 10, 25, 17, 20, 5, tzinfo=timezone.utc))
        emsc, malos = tb.leer_emsc((FIJ / "forma-emsc-fdsn.json").read_bytes())
        self.assertEqual((len(emsc), malos), (3, 1))
        self.assertEqual((emsc[0].lat, emsc[0].lon, emsc[0].prof), (-33.10, -71.70, 30.0))   # de properties, no de geometry
        self.assertEqual(emsc[0].lugar, "Offshore Valparaiso, Chile")
        self.assertTrue(emsc[0].url.startswith("https://www.seismicportal.eu/eventdetails.html?unid="))

    def test_respuestas_reales_si_las_hay(self):
        reales = sorted(FIJ.glob("real-*.json"))
        if not reales:
            self.skipTest("todavía no hay real-*.json: se guardan en la Pi con --guardar-fixtures")
        for ruta in reales:
            lector = tb.leer_usgs if "-usgs-" in ruta.name else tb.leer_emsc
            sismos, _ = lector(ruta.read_bytes())
            self.assertTrue(all(-90 <= s.lat <= 90 and -180 <= s.lon <= 180 for s in sismos), ruta.name)

    def test_respuesta_rota(self):
        for cuerpo in (b"<html>mantenimiento</html>", b'{"type": "Feature"}', b'{"features": 3}', b"\xff\xfe"):
            with self.assertRaises(ValueError):
                tb.leer_usgs(cuerpo)
            with self.assertRaises(ValueError):
                tb.leer_emsc(cuerpo)

    def test_urls(self):
        self.assertEqual(tb.url_de("usgs", self.cfg, AHORA),
                         "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson")
        bajo = dict(self.cfg, regla=[{"mag": 4.0, "km": 100}])
        self.assertTrue(tb.url_de("usgs", bajo, AHORA).endswith("/2.5_day.geojson"))
        e = tb.url_de("emsc", self.cfg, AHORA)
        self.assertIn("format=json", e)
        self.assertIn("minmag=4.7", e)
        self.assertIn("start=2026-10-25T14%3A00%3A00", e)

    def test_una_fuente_caida_usa_la_otra_y_queda_registrado(self):
        abrir = red(usgs=OSError("connection refused"))
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(self.correr(abrir), 0)
        self.assertIn("usgs no contestó bien", err.getvalue())
        estado = json.loads(self.estado.read_text(encoding="utf-8"))
        self.assertEqual(estado["fuentes"]["usgs"]["ok"], False)
        self.assertIn("OSError", estado["fuentes"]["usgs"]["error"])
        self.assertTrue(estado["fuentes"]["emsc"]["ok"])
        textos = self.bandeja()
        self.assertTrue(textos and all("seismicportal.eu" in t for t in textos))

    def test_respuesta_rota_de_una_fuente_y_las_dos_caidas(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(self.correr(red(emsc=b"no es json")), 0)
            self.assertFalse(json.loads(self.estado.read_text(encoding="utf-8"))["fuentes"]["emsc"]["ok"])
            self.assertEqual(self.correr(red(usgs=OSError("x"), emsc=b"{")), 1)


class Avisos(Base):
    def test_avisa_lo_relevante_una_vez_y_sin_duplicar_entre_fuentes(self):
        self.assertEqual(self.correr(), 0)
        textos = self.bandeja()
        # Valparaíso M5,5 (USGS 5,4 y EMSC 5,5: el mismo, una vez), Antofagasta M6,6 (Chile), San Antonio M6,9
        # (urgente; USGS 6,8 y EMSC 6,9) y el M5,1 que solo trae EMSC. No: M4,9, Japón, el de hace 9 h, el malformado.
        self.assertEqual(len(textos), 4, textos)
        self.assertEqual(sum("Valparaiso" in t or "Valparaíso" in t for t in textos), 2)   # el M5,5 y el M5,1 de EMSC
        self.assertEqual(sum(t.startswith("🚩") for t in textos), 1)
        self.assertFalse(any("Japan" in t or "Rancagua" in t or "M 4,9" in t for t in textos))
        registro = self.registro()
        self.assertEqual([r["texto"] for r in registro], textos)
        self.assertEqual({r["origen"] for r in registro}, {"temblores"})
        self.assertEqual([r["nivel"] for r in registro if r["texto"].startswith("🚩")], ["alerta"])
        # Segunda corrida: nada nuevo.
        self.assertEqual(self.correr(ahora=AHORA + timedelta(minutes=5)), 0)
        self.assertEqual(self.bandeja(), textos)

    def test_correccion_de_magnitud_no_se_repite(self):
        self.correr()
        doc = json.loads((FIJ / "forma-usgs-4.5_day.json").read_text(encoding="utf-8"))
        for f in doc["features"]:
            if f["id"] == "us7000r1a1":
                f["properties"]["mag"] = 5.7                           # corregido después
                f["properties"]["time"] += 20 * 1000                   # y la hora, 20 s
                f["geometry"]["coordinates"][0] += 0.2                 # y el epicentro, ~18 km
                f["id"] = "us7000zzzz"                                 # incluso con otro id
                f["properties"]["ids"] = ",us7000zzzz,"
        antes = list(self.bandeja())
        self.correr(red(usgs=json.dumps(doc).encode()), ahora=AHORA + timedelta(minutes=5))
        self.assertEqual(self.bandeja(), antes)

    def test_dedup_por_id_aunque_cambie_mucho(self):
        a = {"t": "2026-10-25T10:00:00+00:00", "lat": 0, "lon": 0, "ids": ["gu2026uvwx"]}
        s = tb.leer_usgs((FIJ / "forma-usgs-4.5_day.json").read_bytes())[0][0]
        self.assertTrue(tb.mismo(a, s, self.cfg))
        self.assertFalse(tb.mismo(dict(a, ids=["otro"]), s, self.cfg))

    def test_mensaje_corto_y_sin_datos_personales(self):
        self.correr()
        perfil = Path(self.cfg["perfil"]).read_text(encoding="utf-8")
        for t in self.bandeja():
            self.assertLess(len(t), 220, t)
            self.assertNotIn("Las Condes", t)
            self.assertNotIn("33.41", t)
            self.assertNotIn("-70.57", t)
            self.assertRegex(t, r"^(🌎 Temblor|🚩 Temblor fuerte) M \d+,\d a \d+ km de la casa · .+ · "
                                r"\d\d:\d\d \(hora de Chile\) · https://\S+$")
        self.assertIn("Las Condes", perfil)     # la comuna está en el perfil, no en el mensaje

    def test_bandeja_inactiva_no_marca_y_reintenta(self):
        self.bandeja_activa(False)
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(self.correr(), 1)
        self.assertIn("no está activa", err.getvalue())
        self.assertEqual(self.bandeja(), [])
        self.assertEqual(json.loads(self.estado.read_text(encoding="utf-8"))["avisados"], [])
        self.bandeja_activa(True)
        self.assertEqual(self.correr(ahora=AHORA + timedelta(minutes=5)), 0)
        self.assertEqual(len(self.bandeja()), 4)

    def test_lo_viejo_no_se_avisa_tras_un_corte(self):
        self.assertEqual(self.correr(ahora=AHORA + timedelta(hours=4)), 0)
        self.assertEqual(self.bandeja(), [])

    def test_simular_no_escribe_nada(self):
        vistos = []
        self.assertEqual(self.correr(simular=True, salida=vistos.append), 0)
        self.assertEqual(len(vistos), 4)
        self.assertFalse(self.estado.exists())
        self.assertEqual(self.bandeja(), [])

    def test_estado_atomico_y_dentro_del_temporal(self):
        antes = {p for p in AQUI.parent.rglob("*") if ".git" not in p.parts}
        real = Path(tb.DEFECTO["estado"])
        marca_real = real.stat().st_mtime_ns if real.exists() else None
        self.correr()
        despues = {p for p in AQUI.parent.rglob("*") if ".git" not in p.parts and "__pycache__" not in p.parts}
        self.assertEqual(despues - antes, set())          # nada nuevo en el repositorio
        self.assertEqual(real.stat().st_mtime_ns if real.exists() else None, marca_real)    # el estado de verdad, intacto
        self.assertEqual(sorted(p.name for p in self.estado.parent.iterdir()), ["estado.json"])   # sin temporales
        estado = json.loads(self.estado.read_text(encoding="utf-8"))
        self.assertEqual(len(estado["avisados"]), 4)
        self.assertTrue(all(set(a) >= {"t", "lat", "lon", "mag", "ids", "avisado"} for a in estado["avisados"]))
        # Un fallo a mitad de la escritura no deja el estado a medias ni temporales.
        with mock.patch("json.dump", side_effect=RuntimeError("disco lleno")):
            with self.assertRaises(RuntimeError):
                tb.guardar_estado(self.estado, {"x": 1})
        self.assertEqual(json.loads(self.estado.read_text(encoding="utf-8")), estado)
        self.assertEqual(sorted(p.name for p in self.estado.parent.iterdir()), ["estado.json"])


class Descanso(Base):
    """Con la biblioteca real: de noche lo no urgente queda para el resumen; lo urgente sale igual."""

    def setUp(self):
        super().setUp()
        avisos_mod = cargar("avisos_91", AQUI / "avisos.py")
        self.avisos = avisos_mod
        self.enviados = []
        avisos_mod.enviar = lambda token, chat, texto: self.enviados.append(texto) or avisos_mod.Envio(True, "", False)
        avisos_mod._descanso = lambda: descanso
        os.environ["NODO_DESCANSO_PRUEBA_REAL"] = "1"
        self.addCleanup(os.environ.pop, "NODO_DESCANSO_PRUEBA_REAL", None)

    def test_noche_frente_a_urgente(self):
        self.assertTrue(descanso.en_descanso(NOCHE))
        self.assertFalse(descanso.en_descanso(AHORA))
        doc = json.loads((FIJ / "forma-usgs-4.5_day.json").read_text(encoding="utf-8"))
        for f in doc["features"]:          # los mismos sismos, corridos a la noche del martes
            f["properties"]["time"] += int((NOCHE - AHORA).total_seconds() * 1000)
        emsc = json.loads((FIJ / "forma-emsc-fdsn.json").read_text(encoding="utf-8"))
        for f in emsc["features"]:
            if isinstance(f["properties"].get("time"), str):
                t = tb._iso_utc(f["properties"]["time"]) + (NOCHE - AHORA)
                f["properties"]["time"] = t.isoformat()
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(self.correr(red(json.dumps(doc).encode(), json.dumps(emsc).encode()), ahora=NOCHE), 0)
        self.assertIn("resumen de la mañana", err.getvalue())
        textos = self.bandeja()
        self.assertEqual(len(textos), 4)
        # Lo que hace avisos.py con cada línea de la bandeja, con descanso.py real:
        for t in textos:
            r = self.avisos.enviar_respetando_descanso("token", "chat", t, ahora=NOCHE)
            self.assertEqual(r.estado, "enviado" if t.startswith("🚩") else "encolado", t)
        self.assertEqual(self.enviados, [t for t in textos if t.startswith("🚩")])
        encolados = descanso.sacar_resumen()
        self.assertEqual([x["texto"] for x in encolados], [t for t in textos if not t.startswith("🚩")])
        # De día sale todo.
        for t in textos:
            self.assertEqual(self.avisos.enviar_respetando_descanso("token", "chat", t, ahora=AHORA).estado, "enviado")

    def test_el_urgente_lo_reconoce_descanso(self):
        s = tb.leer_usgs((FIJ / "forma-usgs-4.5_day.json").read_bytes())[0][3]
        self.assertTrue(descanso.es_urgente(tb.mensaje(s, 135, True, AHORA)))
        self.assertFalse(descanso.es_urgente(tb.mensaje(s, 135, False, AHORA)))


if __name__ == "__main__":
    unittest.main()
