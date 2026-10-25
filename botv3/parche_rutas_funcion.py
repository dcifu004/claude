"""Parche del clasificador n8n (06a, 29-09-2026): rutas con nombre de funcion.

`archivos` (antes `claude`), `tecnica` (`codex`), `general` (`gpt`), `casa` (`ha`) y
`agenda` (`google`). El clasificador ACEPTA los dos nombres en `source` y DEVUELVE el
nuevo, pero solo al bot que manda `nombres_nuevos: true` (botv3.py desde el 06a). Un
bot viejo sigue recibiendo el nombre de siempre, asi que el flujo se puede publicar
antes o despues del bot sin cortar nada. Adentro el clasificador sigue pensando con
los nombres de hoy: solo se traduce al entrar y al salir.

Se aplica al `jsCode` del nodo "Validar y clasificar" (id `classify-request`), igual
que parche_codex_por_perfil.py. Es idempotente: si ya esta aplicado no cambia nada.
Uso desde otro script: `from parche_rutas_funcion import parchear`.

NO lo publica: `python3 parche_rutas_funcion.py <workflow.json>` edita ese archivo y
nada mas. Publicarlo en n8n lo hace Diego.
"""

MARCA = "NOMBRE_NUEVO"

ANCLA_SOURCE = "const source = String(input.source ?? '').trim().toLowerCase();\n"
NUEVO_SOURCE = (
    "// Nombres por funcion (06a, 29-09-2026). Se aceptan los dos y adentro se piensa\n"
    "// con el de siempre; la tabla es la misma que recetas.ALIAS_RUTA en el bot.\n"
    "const ALIAS_RUTA = { archivos: 'claude', tecnica: 'codex', general: 'gpt', casa: 'ha', agenda: 'google' };\n"
    "const NOMBRE_NUEVO = Object.fromEntries(Object.entries(ALIAS_RUTA).map(([n, v]) => [v, n]));\n"
    "const sourceCrudo = String(input.source ?? '').trim().toLowerCase();\n"
    "const source = ALIAS_RUTA[sourceCrudo] ?? sourceCrudo;\n"
    "// Solo el bot que lo pide recibe el nombre nuevo: uno viejo lo rechazaria como\n"
    "// \"ruta no permitida\".\n"
    "const nombresNuevos = input.nombres_nuevos === true;\n"
)

ANCLA_RESPUESTA = "return [{ json: { mode: 'decision', payload: { route } } }];"
NUEVA_RESPUESTA = (
    "return [{ json: { mode: 'decision', payload: {\n"
    "  route: nombresNuevos ? (NOMBRE_NUEVO[route] ?? route) : route } } }];"
)

ANCLA_MENSAJE = "'Ruta no permitida. El router solo acepta auto, sql, ha o gpt.'"
NUEVO_MENSAJE = "'Ruta no permitida. El router solo acepta auto, sql, ha (casa) o gpt (general).'"

# El alias no sirve si la lista lo rechaza después de traducirlo. `claude` y
# `codex` son decisiones locales: n8n sólo las devuelve al bot, igual que auto.
ANCLA_ALLOWED = "const allowed = new Set(['auto', 'sql', 'ha', 'gpt']);\n"
NUEVO_ALLOWED = "const allowed = new Set(['auto', 'sql', 'ha', 'gpt', 'claude', 'codex']);\n"
ANCLA_DIRECTA = (
    "if (source !== 'auto') {\n"
    "  if (source === 'gpt') return [{ json: { mode: 'groq', model: GROQ_MODEL, prompt } }];\n"
    "  return answer(pending[source]);\n"
    "}\n"
)
NUEVA_DIRECTA = (
    "if (source !== 'auto') {\n"
    "  if (source === 'gpt') return [{ json: { mode: 'groq', model: GROQ_MODEL, prompt } }];\n"
    "  // Claude/Codex son locales: devolver la decision permite que los aliases de\n"
    "  // funcion sirvan tambien como source, sin llamar un adaptador inexistente.\n"
    "  if (source === 'claude' || source === 'codex') return [{ json: { mode: 'decision', payload: {\n"
    "    route: nombresNuevos ? (NOMBRE_NUEVO[source] ?? source) : source } } }];\n"
    "  return answer(pending[source]);\n"
    "}\n"
)


def parchear(codigo: str) -> str:
    if MARCA in codigo:
        return codigo
    for ancla in (ANCLA_SOURCE, ANCLA_RESPUESTA, ANCLA_MENSAJE, ANCLA_ALLOWED, ANCLA_DIRECTA):
        if codigo.count(ancla) != 1:
            raise ValueError(f"ancla no encontrada exactamente una vez: {ancla[:50]!r}")
    return (codigo.replace(ANCLA_SOURCE, NUEVO_SOURCE)
                  .replace(ANCLA_RESPUESTA, NUEVA_RESPUESTA)
                  .replace(ANCLA_MENSAJE, NUEVO_MENSAJE)
                  .replace(ANCLA_ALLOWED, NUEVO_ALLOWED)
                  .replace(ANCLA_DIRECTA, NUEVA_DIRECTA))


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
