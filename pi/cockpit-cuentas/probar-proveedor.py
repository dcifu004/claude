#!/usr/bin/python3
"""probar-proveedor — el boton «probar» de 💳 Cuentas (encargo 15, 01-10-2026).

    python3 probar-proveedor.py <proveedor> <perfil>

Hace UNA llamada al proveedor con la key del bot de ese perfil y dice, en JSON, que
modelo contesto o el error tal cual. El bot no valida sus modelos contra el catalogo al
arrancar (seria una llamada por proveedor en cada reinicio): para eso esta este boton.

«Modelo retirado» y «key invalida» se parecen y son cosas distintas: confundirlos manda
a rotar una key que estaba bien. La clase del error sale de recetas.clasificar_error,
con las formas medidas el 01-10 contra cada proveedor.

Se instala con la pagina (~/.local/share/cockpit/cuentas/) y corre como dcifu004, sin
sudo: lee la key de /opt/nodo/datos/secretos/botv3-<perfil>.env, que su grupo `captura`
puede leer. Que proveedores hay, su URL, su variable y su modelo salen del recetas.py
DESPLEGADO (/opt/botv3, de root), no del vault. La key viaja solo en el header: no se
imprime, no va en la URL y se tapa en cualquier texto que salga de aca.

Ojo: mide el ARCHIVO de entorno. Si la key se cargo y el bot no se reinicio, aca anda y
el bot todavia no la tiene; eso lo dice la columna «listo / sin key» de la pagina.
"""
import importlib.util
import json
import re
import sys
import time
import urllib.error
import urllib.request

BOT_DIR = "/opt/botv3"
SECRETOS = "/opt/nodo/datos/secretos"
PERFIL = re.compile(r"[a-z][a-z0-9]{0,19}")
TIMEOUT_S = 60


def cargar_recetas(ruta=None):
    try:
        spec = importlib.util.spec_from_file_location("recetas", ruta or f"{BOT_DIR}/recetas.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod if hasattr(mod, "PROVEEDORES") else None
    except (OSError, ImportError, SyntaxError, AttributeError):
        return None


def entorno_de(perfil):
    """Las variables del archivo de entorno del bot, tal como las leeria systemd."""
    out = {}
    with open(f"{SECRETOS}/botv3-{perfil}.env", encoding="utf-8") as fh:
        for linea in fh:
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$", linea.rstrip("\n"))
            if not m:
                continue
            valor = m.group(2).strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            out[m.group(1)] = valor
    return out


def llamar(url, clave, cuerpo):
    """(estado HTTP, cuerpo ya parseado o texto). Sin reintentos."""
    pedido = urllib.request.Request(
        url, data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json",
                 "User-Agent": "botv3-probar/1"})
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_S) as r:
            estado, crudo = r.status, r.read()
    except urllib.error.HTTPError as e:
        estado, crudo = e.code, e.read()
    texto = crudo.decode("utf-8", "replace")
    try:
        return estado, json.loads(texto)
    except ValueError:
        return estado, texto[:300]


def probar(mod, proveedor, perfil, entorno, llamar=llamar):
    """El resultado de una llamada de prueba, como dict. Nunca levanta ni trae la key."""
    p = mod.PROVEEDORES[proveedor]
    clave = (entorno.get(p["key"]) or "").strip()
    out = {"proveedor": proveedor, "nombre": mod.NOMBRE_CUENTA.get(proveedor, proveedor),
           "perfil": perfil, "ok": False, "modelo": "", "segundos": None, "estado": None,
           "clase": "", "explicacion": "", "error": ""}

    def tapar(texto):
        return str(texto).replace(clave, "[KEY]") if clave else str(texto)

    if not clave:
        out.update(clase="key", error=f"sin key: {p['key']} no esta en botv3-{perfil}.env",
                   explicacion=f"Se carga con: {mod.linea_para_cargar(proveedor, perfil)}")
        return out
    pedido = mod.modelo_de(proveedor, entorno)
    if p.get("buscador"):
        url, cuerpo = p["url"], {"query": "prueba", "topic": "general", "max_results": 1}
    else:
        url = p["url"].rstrip("/") + "/chat/completions"
        cuerpo = {"messages": [{"role": "user", "content": "Responde solo: OK"}]}
        modelos = [m.strip() for m in pedido.split(",") if m.strip()]
        if proveedor == "openrouter" and len(modelos) > 1:
            cuerpo["models"] = modelos[:mod.MAX_MODELOS_OPENROUTER]
        else:
            cuerpo["model"] = modelos[0] if modelos else ""
    inicio = time.monotonic()
    try:
        estado, datos = llamar(url, clave, cuerpo)
    except Exception as e:        # red caida, DNS, timeout
        out.update(clase="otro", error=tapar(f"{type(e).__name__}: {e}")[:300],
                   explicacion="no se pudo llegar al proveedor")
        return out
    out["segundos"], out["estado"] = round(time.monotonic() - inicio, 1), estado
    con_error = isinstance(datos, dict) and datos.get("error") and not datos.get("choices")
    if estado >= 400 or con_error:
        if con_error and estado < 400 and isinstance(datos["error"], dict) \
                and isinstance(datos["error"].get("code"), int):
            estado = datos["error"]["code"]       # OpenRouter: HTTP 200 con el error adentro
        clase = mod.clasificar_error(proveedor, estado, datos)
        detalle = mod.detalle_de_error(datos) or (datos if isinstance(datos, str) else "")
        out.update(clase=clase, explicacion=mod.CLASES_DE_ERROR[clase],
                   error=tapar(f"HTTP {estado}: {detalle}" if detalle else f"HTTP {estado}"),
                   modelo=pedido)
        return out
    if p.get("buscador"):
        resultados = datos.get("results") if isinstance(datos, dict) else None
        out.update(ok=isinstance(resultados, list), modelo="buscador",
                   error="" if isinstance(resultados, list) else "la respuesta no trae `results`")
        return out
    try:
        texto = datos["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        texto = None
    out.update(ok=isinstance(texto, str) and bool(texto.strip()),
               modelo=tapar(datos.get("model") or pedido) if isinstance(datos, dict) else pedido)
    if not out["ok"]:
        out.update(clase="otro", error="contesto sin texto", explicacion=mod.CLASES_DE_ERROR["otro"])
    return out


def main(args):
    mod = cargar_recetas()
    if mod is None:
        print(json.dumps({"ok": False, "clase": "otro", "error":
                          f"{BOT_DIR}/recetas.py es anterior al encargo 15: falta desplegarlo"},
                         ensure_ascii=False))
        return 1
    if len(args) != 2 or args[0] not in mod.PROVEEDORES or not PERFIL.fullmatch(args[1]):
        print(json.dumps({"ok": False, "clase": "otro", "error":
                          f"uso: probar-proveedor <{'|'.join(mod.PROVEEDORES)}> <perfil>"},
                         ensure_ascii=False))
        return 2
    proveedor, perfil = args
    try:
        entorno = entorno_de(perfil)
    except OSError as e:
        print(json.dumps({"ok": False, "proveedor": proveedor, "perfil": perfil, "clase": "otro",
                          "error": f"no pude leer botv3-{perfil}.env: {e.strerror}"}, ensure_ascii=False))
        return 1
    print(json.dumps(probar(mod, proveedor, perfil, entorno), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
