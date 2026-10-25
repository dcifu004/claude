#!/usr/bin/env python3
"""Comprueba las plantillas 88a sin red ni escrituras fuera de este árbol."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ESQUEMA = json.loads((RAIZ / "fixtures" / "config_schema.v0.10.5.json").read_text())


def leer_yaml_simple(ruta: Path) -> dict:
    """Lee el subconjunto YAML de estas plantillas, sin dependencia externa."""
    raiz: dict = {}
    actual = raiz
    for linea in ruta.read_text().splitlines():
        if not linea or linea.lstrip().startswith("#"):
            continue
        sangria = len(linea) - len(linea.lstrip())
        clave, separador, valor = linea.strip().partition(":")
        if not separador:
            raise ValueError(f"YAML inválido en {ruta.name}: {linea!r}")
        if sangria == 0:
            actual = raiz
        elif sangria != 2:
            raise ValueError(f"sangría no admitida en {ruta.name}: {linea!r}")
        if valor.strip() == "":
            dato = {}
        elif valor.strip() in ("true", "false"):
            dato = valor.strip() == "true"
        elif valor.strip().isdigit():
            dato = int(valor.strip())
        elif valor.strip().startswith('"') and valor.strip().endswith('"'):
            dato = valor.strip()[1:-1]
        else:
            dato = valor.strip()
        actual[clave] = dato
        if isinstance(dato, dict):
            actual = dato
    return raiz


def validar(valor, esquema, ruta="config"):
    tipo = esquema.get("type")
    if tipo == "object":
        if not isinstance(valor, dict):
            raise AssertionError(f"{ruta}: se esperaba objeto")
        props = esquema.get("properties", {})
        if esquema.get("additionalProperties") is False:
            extras = set(valor) - set(props)
            if extras:
                raise AssertionError(f"{ruta}: claves no admitidas: {sorted(extras)}")
        for clave, dato in valor.items():
            if clave not in props:
                raise AssertionError(f"{ruta}: clave fuera del esquema: {clave}")
            validar(dato, props[clave], f"{ruta}.{clave}")
    elif tipo == "string" and not isinstance(valor, str):
        raise AssertionError(f"{ruta}: se esperaba texto")
    elif tipo == "boolean" and type(valor) is not bool:
        raise AssertionError(f"{ruta}: se esperaba booleano")
    elif tipo == "integer" and (type(valor) is not int):
        raise AssertionError(f"{ruta}: se esperaba entero")
    if "enum" in esquema and valor not in esquema["enum"]:
        raise AssertionError(f"{ruta}: {valor!r} no pertenece a {esquema['enum']}")
    minimo = esquema.get("minimum", esquema.get("min"))
    if minimo is not None and valor < minimo:
        raise AssertionError(f"{ruta}: menor que {minimo}")


class PlantillasTests(unittest.TestCase):
    def setUp(self):
        self.jaime = leer_yaml_simple(RAIZ / "config-jaime.yml")
        self.pilar = leer_yaml_simple(RAIZ / "config-pilar.yml")
        self.unidad = (RAIZ / "spotify@.service").read_text()

    def test_plantillas_validan_con_el_esquema_fijado(self):
        esquema = ESQUEMA["definitions"]["config"]
        validar(self.jaime, esquema)
        validar(self.pilar, esquema)
        # v0.10.5 usa la extensión `min` (no `minimum`) para initial_volume: este caso
        # demuestra que se está ejecutando la restricción real, no un extracto inventado.
        invalida = copy.deepcopy(self.jaime)
        invalida["initial_volume"] = -1
        with self.assertRaisesRegex(AssertionError, "menor que 0"):
            validar(invalida, esquema)

    def test_aislamiento_por_perfil_y_loopback(self):
        self.assertEqual(self.jaime["server"]["address"], "127.0.0.1")
        self.assertEqual(self.pilar["server"]["address"], "127.0.0.1")
        self.assertEqual({self.jaime["server"]["port"], self.pilar["server"]["port"]}, {3678, 3679})
        for perfil in (self.jaime, self.pilar):
            self.assertFalse(perfil["zeroconf_enabled"])
            self.assertEqual(perfil["credentials"]["type"], "device_auth")
            self.assertEqual(perfil["audio_backend"], "pulseaudio")
            self.assertEqual(perfil["initial_volume"], 40)
            self.assertEqual(perfil["bitrate"], 160)
        self.assertNotEqual(self.jaime["device_name"], self.pilar["device_name"])

    def test_unidad_usa_instancia_y_condicion_del_config(self):
        # pflag interpreta un solo guión como -c + "onfig_dir"; ésta es la forma que el
        # binario real expone en --help.
        self.assertIn("ExecStart=/usr/local/bin/go-librespot --config_dir /opt/nodo/datos/spotify/%i", self.unidad)
        self.assertIn("ConditionPathExists=/opt/nodo/datos/spotify/%i/config.yml", self.unidad)
        self.assertIn("Restart=on-failure", self.unidad)
        self.assertIn("RestartSec=10", self.unidad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
