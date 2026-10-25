"""Pruebas sin Node de los parches del clasificador n8n."""

import json
import unittest
from pathlib import Path

import parche_codex_por_perfil as codex
import parche_cuentas_por_ruta as cuentas
import parche_rutas_funcion as rutas


def codigo_vault() -> str:
    workflow = json.loads(Path(__file__).with_name("n8n-dcs-v3bot-router.workflow.json").read_text())
    return next(n for n in workflow["nodes"] if n["id"] == "classify-request")["parameters"]["jsCode"]


def sin_codex(codigo: str) -> str:
    """Reconstruye la forma pre-24-09 para probar su ancla original."""
    return codigo.replace(codex.NUEVO_PERFIL, codex.ANCLA_PERFIL).replace(codex.NUEVA_RAMA, codex.ANCLA_RAMA)


def balanceado_js(codigo: str) -> None:
    """Tokenizador acotado: strings, comentarios, regex y ${...}; no ejecuta JS."""
    pares = {"(": ")", "[": "]", "{": "}"}
    pila: list[str] = []
    i, n = 0, len(codigo)
    estado = "normal"
    escape = False
    template_expr = []
    while i < n:
        c = codigo[i]
        sig = codigo[i + 1] if i + 1 < n else ""
        if estado == "linea":
            if c in "\r\n": estado = "normal"
            i += 1; continue
        if estado == "bloque":
            if c == "*" and sig == "/": estado = "normal"; i += 2; continue
            i += 1; continue
        if estado in {"comilla", "dobles", "regex"}:
            if escape: escape = False
            elif c == "\\": escape = True
            elif (estado == "comilla" and c == "'") or (estado == "dobles" and c == '"') or (estado == "regex" and c == "/"):
                estado = "normal"
            i += 1; continue
        if estado == "template":
            if escape: escape = False
            elif c == "\\": escape = True
            elif c == "`": estado = "normal"
            elif c == "$" and sig == "{":
                pila.append("{"); template_expr.append(len(pila)); estado = "normal"; i += 2; continue
            i += 1; continue
        if c == "/" and sig == "/": estado = "linea"; i += 2; continue
        if c == "/" and sig == "*": estado = "bloque"; i += 2; continue
        if c == "'": estado = "comilla"; i += 1; continue
        if c == '"': estado = "dobles"; i += 1; continue
        if c == "`": estado = "template"; i += 1; continue
        # En este clasificador, un / tras (, =, !, : o | abre regex; el resto es división.
        if c == "/" and (not pila or i == 0 or codigo[max(0, i - 1)] in "(=!:|&,[{"):
            estado = "regex"; i += 1; continue
        if c in pares: pila.append(c)
        elif c in ")]}":
            if not pila or pares[pila.pop()] != c:
                raise AssertionError(f"cierre JS no corresponde en índice {i}: {c!r}")
            if c == "}" and template_expr and len(pila) < template_expr[-1]:
                template_expr.pop(); estado = "template"
        i += 1
    if estado != "normal" or pila or template_expr:
        raise AssertionError(f"JS sin cerrar: estado={estado}, pila={pila}, templates={template_expr}")


class ParchesN8nTests(unittest.TestCase):
    def setUp(self):
        self.vault = codigo_vault()
        self.base = sin_codex(self.vault)

    def test_orden_e_idempotencia(self):
        resultado = cuentas.parchear(rutas.parchear(codex.parchear(self.base)))
        self.assertEqual(codex.parchear(resultado), resultado)
        self.assertEqual(rutas.parchear(resultado), resultado)
        self.assertEqual(cuentas.parchear(resultado), resultado)
        self.assertIn("CUENTAS_POR_RUTA", resultado)
        self.assertIn("...(cuenta ? { cuenta } : {})", resultado)
        balanceado_js(resultado)

    def test_cada_ancla_ausente_aborta(self):
        casos = [
            (codex.parchear, self.base.replace(codex.ANCLA_RAMA, "")),
            (rutas.parchear, codex.parchear(self.base).replace(rutas.ANCLA_SOURCE, "")),
            (cuentas.parchear, rutas.parchear(codex.parchear(self.base)).replace(cuentas.ANCLA_RESPUESTA, "")),
        ]
        for parchear, codigo in casos:
            with self.subTest(parche=parchear.__module__):
                with self.assertRaises(ValueError):
                    parchear(codigo)

    def test_vault_y_resultado_estan_balanceados(self):
        balanceado_js(self.vault)
        balanceado_js(cuentas.parchear(rutas.parchear(codex.parchear(self.base))))


if __name__ == "__main__":
    unittest.main()
