"""Parche del clasificador n8n (24-09-2026): la rama tecnica vuelve a `codex`, pero
SOLO para los perfiles que tienen `codex` en sus rutas.

Se aplica al `jsCode` del nodo "Validar y clasificar", tanto en el JSON del vault como
en la version publicada de n8n (workflow_history). Es idempotente: si ya esta aplicado
no cambia nada. Uso desde otro script: `from parche_codex_por_perfil import parchear`.
"""

MARCA = "PERFILES_CON_CODEX"

ANCLA_PERFIL = "const prompt = String(input.prompt ?? '').trim();\n"
NUEVO_PERFIL = ANCLA_PERFIL + (
    "// El bot manda su perfil como DATO. No decide permisos —el bot intersecta la\n"
    "// ruta con las suyas—, solo preferencias de ruta. Ver la rama tecnica.\n"
    "const perfil = String(input.perfil ?? '').trim().toLowerCase();\n"
    "// Perfiles cuyo TOML tiene `codex` en `rutas` (24-09-2026). Tiene que calzar con\n"
    "// botv3/perfiles/*.toml; un desfase se degrada en el bot, no abre nada.\n"
    "const PERFILES_CON_CODEX = new Set(['jaime']);\n"
)

ANCLA_RAMA = ("  // Si `codex` vuelve al perfil, esta linea vuelve con el.\n"
              "  route = 'claude';\n")
NUEVA_RAMA = (
    "  // VOLVIO el 24-09-2026, por decision de Diego desde la pagina 🤖 de Cockpit,\n"
    "  // pero SOLO para los perfiles con `codex` en sus rutas. El clasificador es uno\n"
    "  // para todos los bots: mandarle `codex` a un perfil sin esa ruta lo degradaria\n"
    "  // a `gpt` en el bot, o sea Groq opinando sobre archivos que no ve. Sin perfil\n"
    "  // (una version vieja del bot) sigue siendo `claude`.\n"
    "  route = PERFILES_CON_CODEX.has(perfil) ? 'codex' : 'claude';\n"
)


def parchear(codigo: str) -> str:
    if MARCA in codigo:
        return codigo
    for ancla in (ANCLA_PERFIL, ANCLA_RAMA):
        if codigo.count(ancla) != 1:
            raise ValueError(f"ancla no encontrada exactamente una vez: {ancla[:50]!r}")
    return codigo.replace(ANCLA_PERFIL, NUEVO_PERFIL).replace(ANCLA_RAMA, NUEVA_RAMA)


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
