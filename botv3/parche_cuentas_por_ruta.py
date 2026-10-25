"""Parche del clasificador n8n (09, 30-09-2026): cuenta preferida por perfil y ruta.

Se aplica despues de ``parche_codex_por_perfil.py`` y
``parche_rutas_funcion.py``. Agrega una tabla pequena y editable en el nodo Code:
la primera cuenta actual de cada ruta que usa agentes. Devuelve ``cuenta`` junto a
``route`` solo cuando la tabla tiene una. Es idempotente y no publica nada.

Uso desde otro script: ``from parche_cuentas_por_ruta import parchear``.
"""

MARCA = "CUENTAS_POR_RUTA"

ANCLA_TABLA = "const GROQ_MODEL = 'openai/gpt-oss-120b';\n"
NUEVA_TABLA = ANCLA_TABLA + (
    "\n"
    "// Cuenta inicial por perfil y ruta (09, 30-09-2026). Editar esta tabla en\n"
    "// n8n si cambia el primer valor de `cuentas` en botv3/perfiles/*.toml.\n"
    "// Las rutas usan nombres por funcion porque esta tabla se muestra al editar.\n"
    "const CUENTAS_POR_RUTA = {\n"
    "  jaime: { archivos: 'claude_diego', tecnica: 'codex', web: 'codex' },\n"
    "  pilar: { archivos: 'claude_cami', web: 'claude_cami' }\n"
    "};\n"
)

ANCLA_RESPUESTA = (
    "return [{ json: { mode: 'decision', payload: {\n"
    "  route: nombresNuevos ? (NOMBRE_NUEVO[route] ?? route) : route } } }];"
)
NUEVA_RESPUESTA = (
    "const rutaRespuesta = nombresNuevos ? (NOMBRE_NUEVO[route] ?? route) : route;\n"
    "const rutaFuncion = NOMBRE_NUEVO[route] ?? route;\n"
    "const cuenta = CUENTAS_POR_RUTA[perfil]?.[rutaFuncion];\n"
    "return [{ json: { mode: 'decision', payload: {\n"
    "  route: rutaRespuesta, ...(cuenta ? { cuenta } : {}) } } }];"
)


def parchear(codigo: str) -> str:
    if MARCA in codigo:
        return codigo
    for ancla in (ANCLA_TABLA, ANCLA_RESPUESTA):
        if codigo.count(ancla) != 1:
            raise ValueError(f"ancla no encontrada exactamente una vez: {ancla[:50]!r}")
    return (codigo.replace(ANCLA_TABLA, NUEVA_TABLA)
                  .replace(ANCLA_RESPUESTA, NUEVA_RESPUESTA))


if __name__ == "__main__":
    import json
    import sys

    ruta = sys.argv[1]
    with open(ruta, encoding="utf-8") as fh:
        wf = json.load(fh)
    nodo = next(n for n in wf["nodes"] if n.get("id") == "classify-request")
    nodo["parameters"]["jsCode"] = parchear(nodo["parameters"]["jsCode"])
    with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(wf, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("ok")
