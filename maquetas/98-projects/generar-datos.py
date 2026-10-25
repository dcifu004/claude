#!/usr/bin/env python3
"""Genera datos/datos-98.js a partir de encargos-nube/98-datos/.

No calcula nada: copia las tres fuentes a un .js para que la maqueta se abra con
file:// (sin servidor y sin fetch). Del historial sólo deja los campos que usa la
maqueta (ningún campo de texto libre: no hay); los números van tal cual.

    python3 maquetas/98-projects/generar-datos.py
"""
import json
import pathlib

AQUI = pathlib.Path(__file__).resolve().parent
FUENTE = AQUI.parent.parent / "encargos-nube" / "98-datos"
CAMPOS = ("encargo", "fase", "rol", "cuenta", "motor", "modelo", "naturaleza",
          "inicio", "min", "veredicto")


def cargar():
    historial = []
    with open(FUENTE / "historial.jsonl", encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                fila = json.loads(linea)
                historial.append({k: fila.get(k) for k in CAMPOS})
    indice = json.loads((FUENTE / "encargos-index.json").read_text(encoding="utf-8"))
    # Del índice: id, slug, título y los nombres de los RESULTADO (nunca su contenido).
    indice = [{"id": x["id"], "slug": x["slug"], "titulo": x["titulo"],
               "resultados": x.get("resultados", [])} for x in indice]
    borrador = json.loads((FUENTE / "proyectos-borrador.json").read_text(encoding="utf-8"))
    return {"historial": historial, "indice": indice, "borrador": borrador}


def main():
    datos = cargar()
    salida = AQUI / "datos" / "datos-98.js"
    salida.parent.mkdir(exist_ok=True)
    texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    salida.write_text(
        '"use strict";\n// Generado por generar-datos.py desde encargos-nube/98-datos/. No editar a mano.\n'
        f"window.DATOS98={texto};\n", encoding="utf-8")
    print(f"{salida.relative_to(AQUI)}: {len(datos['historial'])} fases, "
          f"{len(datos['indice'])} encargos, {len(datos['borrador']['proyectos'])} proyectos")


if __name__ == "__main__":
    main()
