"""Recetas por ruta: alias de nombres, muros por proveedor, umbral por cuenta y orden
de la cadena.

Encargo 06a (29-09-2026, decisiones de Diego en encargos/06-recetas-y-voz.md). Vive
aparte de botv3.py para que `bots-info` calcule «¿quién contestaría ahora?» con ESTA
misma función, sin duplicarla en la página ni importar el bot entero (que carga un
perfil al importarse). Sólo funciones puras y lecturas de archivos: nada de red.

Desplegado en /opt/botv3/recetas.py, al lado de botv3.py. Si falta, el bot arranca
igual con la cadena de siempre y sin alias (mismo criterio que compras.py).

Encargo 15 (01-10-2026): acá viven también los proveedores gratis (PROVEEDORES), lo
que sabe hacer cada motor (APTITUD), lo que necesita cada ruta (FUNCION) y la
recomendación por función (`recomendada`). Sigue sin red: sólo tablas y funciones puras.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

# Nombres por función (decisión 1). La tabla va del nombre NUEVO al interno de hoy:
# todo lo que entra (n8n, comandos, perfil) se normaliza al llegar y adentro del bot
# nada cambia. `web`, `sql` y `plantas` no cambian.
ALIAS_RUTA = {"archivos": "claude", "tecnica": "codex", "general": "gpt",
              "casa": "ha", "agenda": "google"}
NOMBRE_NUEVO = {interna: nueva for nueva, interna in ALIAS_RUTA.items()}


def ruta_interna(nombre: Any) -> str:
    """El nombre interno de una ruta, llegue con el nombre viejo o el nuevo."""
    n = str(nombre or "").strip().lower()
    return ALIAS_RUTA.get(n, n)


def ruta_nombre(interna: str) -> str:
    """El nombre nuevo, el que muestran la interfaz y el libro."""
    return NOMBRE_NUEVO.get(interna, interna)


# --- Proveedores y muros por ruta (encargo 10, 30-09-2026) -------------------------
# El ÚNICO lugar donde se dice qué proveedor puede contestar cada ruta. Lo usan el bot
# (al cargar el perfil y en cada consulta), `aplicar-propuesta` (rechaza la celda
# prohibida) y `bots-info` (la matriz de la página la pinta gris con este motivo).
# Es fijo en el código a propósito: un perfil no puede pedir algo prohibido; si lo
# pide, se ignora y queda en el log.
#
# Groq es un proveedor SIN cuenta pagada: no tiene login, ni límite semanal, ni precio.
# Es una API externa que no está cubierta por la autorización del 12-09-2026 (nombra
# Claude, Codex u OpenAI), así que nunca recibe nada de un vault.
#
# Encargo 15 (01-10-2026, decisión de Diego: «agreguemos todo lo que es gratis; después
# los seleccionamos o no en Cockpit»): entran Gemini (key de AI Studio), OpenRouter
# (sólo modelos `:free`) y Tavily, que es un BUSCADOR y no un modelo. Sólo lo que es
# gratis sin tarjeta. Los tres van como Groq: sin cuenta pagada y nunca en una ruta
# que lee vaults. El id de un proveedor gratis es también el nombre de su motor.
MOTOR_DE_CUENTA = {"claude_diego": "claude", "claude_cami": "claude", "codex": "codex",
                   "groq": "groq", "gemini": "gemini", "openrouter": "openrouter",
                   "tavily": "tavily"}
NOMBRE_CUENTA = {"claude_diego": "Claude (Diego)", "claude_cami": "Claude (Cami)",
                 "codex": "Codex", "groq": "Groq", "gemini": "Gemini",
                 "openrouter": "OpenRouter", "tavily": "Tavily"}
# Motores sin cuenta pagada: sin login, sin límites (el umbral no los salta) y fuera
# del modo automático, que sólo reparte entre las cuentas pagadas.
MOTORES_SIN_CUENTA = {"groq", "gemini", "openrouter", "tavily"}
# Las rutas cuyo agente lee los vaults. Ningún proveedor sin cuenta pagada entra acá:
# `permitida` lo niega aunque alguien se olvide de escribirlo en PROHIBIDO.
RUTAS_DE_VAULT = ("claude", "codex")
# Las rutas que contesta un modelo y por lo tanto tienen cadena de cuentas.
RUTAS_CON_CUENTA = ("claude", "codex", "web", "gpt", "vision", "noticias")
# {ruta: {motor: motivo}}. Lo que no figura acá está permitido.
_VAULT_NO_SALE = "el vault no sale a una API externa"
_GENERAL_SIN_PAGADAS = ("general sólo usa proveedores gratis: las cuentas pagadas podrían "
                        "leer credenciales del bot")
_NO_BUSCA = "no busca en la web: contestaría de memoria"
_ES_BUSCADOR = "es un buscador, no un modelo"
PROHIBIDO = {
    "claude": {m: _VAULT_NO_SALE for m in sorted(MOTORES_SIN_CUENTA)},
    "codex": {m: _VAULT_NO_SALE for m in sorted(MOTORES_SIN_CUENTA)},
    "web": {"codex": "podría leer las credenciales del bot (11)",
            "gemini": _NO_BUSCA + " (el grounding de Google exige billing)",
            "openrouter": _NO_BUSCA},
    # Decisión de Diego, 30-09: la general no entrega STATE_DIR ni credenciales a
    # un CLI. Desde el 15 puede elegir entre los proveedores gratis (Groq por n8n,
    # como siempre, y los demás de respaldo); las cuentas pagadas siguen fuera.
    "gpt": {"claude": _GENERAL_SIN_PAGADAS, "codex": _GENERAL_SIN_PAGADAS,
            "tavily": _ES_BUSCADOR + ": la general no busca"},
    "vision": {"codex": "podría leer las credenciales del bot (06c)",
               "groq": "Groq no tiene visión",
               "openrouter": "sin visión medida en sus modelos gratis",
               "tavily": _ES_BUSCADOR},
    "boleta": {"codex": "podría leer las credenciales del bot (06c)",
               "groq": "Groq no tiene visión", "openrouter": "sin visión medida en sus modelos gratis",
               "tavily": _ES_BUSCADOR},
    # En noticias, Gemini y OpenRouter sólo redactan como parte de Tavily.
    "noticias": {"codex": "podría leer las credenciales del bot (11)",
                 "gemini": "no busca: en noticias sólo redacta lo que encuentra Tavily",
                 "openrouter": "no busca: en noticias sólo redacta lo que encuentra Tavily"},
}
# Herramientas fijas: no las contesta un modelo con cuenta, así que no hay qué elegir.
RUTAS_FIJAS = {
    "ha": "consulta Home Assistant por n8n; no pasa por ninguna cuenta",
    "google": "agenda y correo por google-puente; el contenido no sale del nodo",
    "sql": "consultas SELECT por n8n; los datos no pasan por ninguna cuenta",
    "plantas": "lectura directa del monitor de plantas",
}
# Permitido, pero con algo que conviene leer antes de elegirlo.
AVISOS = {
    ("web", "groq"): "calidad menor, medido el 12-09",
    ("gpt", "groq"): "lo llama n8n, como siempre",
    ("noticias", "groq"): "las notas son públicas",
    ("gpt", "gemini"): "la pregunta sale a Google con una cuenta gratis, que puede usarla para entrenar",
    ("vision", "gemini"): "la foto sale a Google con una cuenta gratis, que puede usarla para "
                          "entrenar; sólo imágenes, un PDF pasa a la siguiente",
    ("gpt", "openrouter"): "poco confiable (bolsa gratis compartida): sólo de último respaldo",
    ("web", "tavily"): "la pregunta sale tal cual a un buscador externo; redacta un modelo gratis",
    ("noticias", "tavily"): "busca noticias en la web en vez de usar las notas seleccionadas; "
                            "la pregunta sale tal cual a un buscador externo",
}
# La cadena de una ruta que el perfil no declara en `cuentas`. Las mismas que fija el
# bot (VISION_CADENA, NOTICIAS_CADENA y la general de siempre, por Groq).
CADENA_POR_DEFECTO = {"vision": ["claude_cami", "claude_diego"],
                      "boleta": ["gemini", "claude_cami", "claude_diego"],
                      "web": ["claude_cami", "claude_diego"],
                      "noticias": ["claude_cami", "claude_diego"], "gpt": ["groq"]}
# 11: mientras Codex monte `/` entero, estas rutas siempre usan las dos cuentas
# Claude. La página muestra la política aunque un perfil viejo aún nombre Codex.
CADENAS_SIN_CODEX = {"web", "boleta", "noticias"}


def permitida(ruta: str, cuenta: str) -> tuple[bool, str]:
    """(se puede, motivo si no). `ruta` en nombre interno; `cuenta`, su id."""
    motor = MOTOR_DE_CUENTA.get(cuenta)
    if motor is None:
        return False, "no es una cuenta conocida"
    if ruta in RUTAS_FIJAS:
        return False, f"fijo: herramienta ({RUTAS_FIJAS[ruta]})"
    if ruta not in PROHIBIDO:
        return False, "la ruta no usa cuentas"
    # El muro de los vaults no depende de que la tabla esté completa: un proveedor
    # sin cuenta pagada no está cubierto por la autorización del 12-09.
    if ruta in RUTAS_DE_VAULT and motor in MOTORES_SIN_CUENTA:
        return False, _VAULT_NO_SALE
    motivo = PROHIBIDO[ruta].get(motor)
    return (False, motivo) if motivo else (True, "")


def problema_de_cadena(ruta: str, ids: Any) -> str | None:
    """Por qué `ids` no sirve como cadena de `ruta`, o None si sirve. La misma regla
    para la propuesta que llega de la página y para lo que arman los atajos."""
    if not isinstance(ids, list) or not ids:
        return "tiene que ser una lista con al menos una cuenta"
    if any(not isinstance(c, str) for c in ids) or len(set(ids)) != len(ids):
        return "no puede repetir cuentas"
    for c in ids:
        ok, motivo = permitida(ruta, c)
        if not ok:
            return f"{NOMBRE_CUENTA.get(c, c)} no puede ir en {ruta_nombre(ruta)}: {motivo}"
    return None


def cuentas_del_automatico(ruta: str) -> list[str]:
    """Las cuentas que el modo automático puede sumar a una ruta aunque no estén en su
    cadena: las PAGADAS que el muro permite. Groq entra a una ruta sólo si alguien lo
    pone en la cadena, nunca porque el automático lo encontró disponible."""
    return [c for c, m in MOTOR_DE_CUENTA.items()
            if m not in MOTORES_SIN_CUENTA and permitida(ruta, c)[0]]


def cadena_efectiva(ruta: str, cuentas_cfg: Any) -> tuple[list[str], bool]:
    """(cadena, declarada) de una ruta según la tabla `cuentas` de un perfil: lo que
    el perfil escribió, sin lo desconocido ni lo prohibido; si no queda nada, la de
    por defecto. El mismo filtro que aplica el bot al cargar."""
    crudo = {}
    if isinstance(cuentas_cfg, dict):
        crudo = {ruta_interna(r): v for r, v in cuentas_cfg.items()}
    ids = crudo.get(ruta)
    buenas = []
    for c in ids if isinstance(ids, list) else []:
        if isinstance(c, str) and permitida(ruta, c)[0] and c not in buenas:
            buenas.append(c)
    if ruta == "gpt":
        # Las cuentas pagadas no pasan el muro: aunque un perfil viejo las traiga, la
        # general no abre una sesión pagada. Lo que queda son proveedores gratis; sin
        # ninguno, Groq por n8n, como siempre.
        return (buenas, True) if buenas else (list(CADENA_POR_DEFECTO[ruta]), bool(ids))
    if ruta in CADENAS_SIN_CODEX and not any(es_gratis(c) for c in buenas):
        # 11: sin un proveedor gratis declarado (15) rige lo de siempre, las dos
        # cuentas Claude, aunque un perfil viejo aún nombre a Codex.
        return list(CADENA_POR_DEFECTO[ruta]), bool(ids)
    if buenas:
        return buenas, True
    return list(CADENA_POR_DEFECTO.get(ruta, [])), False


def es_gratis(cuenta: str) -> bool:
    """Proveedor sin cuenta pagada (Groq, Gemini, OpenRouter, Tavily)."""
    return MOTOR_DE_CUENTA.get(cuenta) in MOTORES_SIN_CUENTA


def groq_listo(ruta: str, entorno: Any) -> bool:
    """Groq no tiene login: está listo si el bot tiene con qué llamarlo. En la ruta
    general lo llama n8n (hace falta el webhook); en las demás, el bot con su
    GROQ_API_KEY. Sólo se mira si el valor existe: nunca se devuelve ni se imprime."""
    clave = "BOTV3_N8N_QUERY_URL" if ruta == "gpt" else "GROQ_API_KEY"
    return bool(str((entorno or {}).get(clave) or "").strip())


# --- Proveedores gratis (encargo 15) -------------------------------------------------
# Lo que hace falta para llamar a cada uno. La KEY no está acá ni en cuentas.toml: el
# bot la lee de su entorno, de la variable `key`. Los tres modelos hablan el formato de
# OpenAI (`<url>/chat/completions`), así que el bot tiene UN adaptador y esta tabla;
# Tavily es otra cosa (`buscador`): busca, y redacta el primer modelo de REDACTORES
# que esté listo. El modelo se cambia con `modelo_var` en el entorno del bot; no se
# valida al arrancar (sería una llamada por proveedor en cada reinicio): la página
# tiene un botón «probar».
# `modelo` de OpenRouter son hasta 3 (su tope), separados por coma: van en el campo
# `models` de la petición y OpenRouter prueba el siguiente solo. Medido el 01-10: de
# 17 modelos `:free`, 10 contestaron, 4 dieron 429 o 502 por la bolsa gratis compartida
# y 2, 403; el catálogo cambia seguido (GET openrouter.ai/api/v1/models, sin key).
PROVEEDORES = {
    "groq": {"key": "GROQ_API_KEY", "que_es": "modelos abiertos, muy rápido",
             "url": "https://api.groq.com/openai/v1", "modelo": "openai/gpt-oss-120b",
             "modelo_var": "BOTV3_GROQ_MODEL", "modelo_var_antes": "BOTV3_GROQ_CHAT_MODEL",
             "prefijo": "gsk_"},
    "gemini": {"key": "GEMINI_API_KEY", "que_es": "Google AI Studio: texto y visión, sin búsqueda",
               "url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "modelo": "gemini-3.6-flash", "modelo_var": "BOTV3_GEMINI_MODEL",
               # La key del 01-10 no empieza con el `AIza` de siempre: no se exige prefijo.
               "prefijo": ""},
    "openrouter": {"key": "OPENROUTER_API_KEY", "que_es": "sólo modelos `:free`, bolsa compartida",
                   "url": "https://openrouter.ai/api/v1",
                   "modelo": "nvidia/nemotron-3-super-120b-a12b:free,"
                             "nvidia/nemotron-3-ultra-550b-a55b:free,poolside/laguna-s-2.1:free",
                   "modelo_var": "BOTV3_OPENROUTER_MODEL", "prefijo": "sk-or-"},
    "tavily": {"key": "TAVILY_API_KEY", "que_es": "buscador con fecha de publicación; redacta un modelo gratis",
               "url": "https://api.tavily.com/search", "buscador": True, "modelo": "",
               "modelo_var": "", "prefijo": "tvly-"},
}
# Quién redacta lo que encuentra Tavily: el primero que tenga key, en este orden.
REDACTORES = ("groq", "gemini", "openrouter")
MAX_MODELOS_OPENROUTER = 3
# Lo que `bots-info` y `aplicar-propuesta` miran en el entorno real del bot. De las keys
# y del webhook sólo se sabe si existen; de las variables de modelo se lee el valor.
VARIABLES_DE_MODELO = tuple(v for p in PROVEEDORES.values()
                            for v in (p["modelo_var"], p.get("modelo_var_antes", "")) if v)
CLAVES_DE_ENTORNO = ("BOTV3_N8N_QUERY_URL",) + tuple(p["key"] for p in PROVEEDORES.values())


def _hay(entorno: Any, variable: str) -> bool:
    return bool(str((entorno or {}).get(variable) or "").strip())


def modelo_de(proveedor: str, entorno: Any) -> str:
    """El modelo que usaría el bot: su variable del entorno o el de por defecto."""
    p = PROVEEDORES[proveedor]
    for variable in (p["modelo_var"], p.get("modelo_var_antes", "")):
        valor = str((entorno or {}).get(variable) or "").strip() if variable else ""
        if valor:
            return valor
    return p["modelo"]


def redactor_listo(entorno: Any) -> str | None:
    """El modelo gratis que redactaría lo que encuentra Tavily, o None."""
    return next((r for r in REDACTORES if _hay(entorno, PROVEEDORES[r]["key"])), None)


def falta_para(ruta: str, cuenta: str, entorno: Any) -> str:
    """Qué le falta a un proveedor gratis para contestar `ruta` en un bot, o "" si
    está listo. Sin key cargada, un proveedor no existe: no entra en ninguna cadena.
    Sólo se mira si cada valor existe: nunca se devuelve ni se imprime."""
    p = PROVEEDORES.get(cuenta)
    if p is None:
        return "no es un proveedor gratis"
    if cuenta == "groq" and ruta == "gpt":
        # En la general a Groq lo llama n8n con su propia credencial.
        return "" if _hay(entorno, "BOTV3_N8N_QUERY_URL") else "sin el webhook de n8n"
    if not _hay(entorno, p["key"]):
        return f"sin key ({p['key']})"
    if p.get("buscador") and redactor_listo(entorno) is None:
        return "sin un modelo gratis con key que redacte (Groq, Gemini u OpenRouter)"
    return ""


def proveedor_listo(ruta: str, cuenta: str, entorno: Any) -> bool:
    return falta_para(ruta, cuenta, entorno) == ""


def linea_para_cargar(cuenta: str, perfil: str) -> str:
    """La línea con que Diego carga la key de un proveedor en un bot (pi/cargar-clave):
    pide el valor sin eco, así la key no pasa por el chat ni por un argumento."""
    return f"sudo cargar-clave {PROVEEDORES[cuenta]['key']} {perfil}"


# «Modelo retirado» y «key inválida» se parecen y son cosas distintas: confundirlos
# manda a rotar una key que estaba bien. Las formas de abajo están medidas el 01-10
# con una key falsa y un modelo inexistente contra cada proveedor.
CLASES_DE_ERROR = {
    "key": "key inválida o revocada: hay que cargarla de nuevo",
    "modelo": "el modelo no existe, fue retirado o no está disponible para esta cuenta: "
              "la key está bien, hay que cambiar el modelo",
    "limite": "límite gratis alcanzado (por minuto o por día): la key y el modelo están bien",
    "saturado": "el proveedor está saturado o caído: la key y el modelo están bien",
    "otro": "error sin clasificar",
}


def detalle_de_error(cuerpo: Any) -> str:
    """El texto del error de una respuesta, en cualquiera de las formas medidas:
    `{"error": {"message"}}` (Groq, OpenRouter), `[{"error": {...}}]` (Gemini) y
    `{"detail": {"error"}}` (Tavily). Sólo el mensaje: el cuerpo de OpenRouter trae
    además el id del usuario y no se copia."""
    if isinstance(cuerpo, list) and cuerpo:
        cuerpo = cuerpo[0]
    if not isinstance(cuerpo, dict):
        return ""
    error = cuerpo.get("error", cuerpo.get("detail"))
    if isinstance(error, dict):
        crudo = (error.get("metadata") or {}).get("raw") if isinstance(error.get("metadata"), dict) else ""
        error = error.get("message") or error.get("error") or ""
        if crudo and str(error).strip() in ("", "Provider returned error"):
            error = crudo
    return re.sub(r"\s+", " ", str(error or "")).strip()[:300]


def clasificar_error(proveedor: str, estado: int, cuerpo: Any) -> str:
    """Una clase de CLASES_DE_ERROR para una respuesta de error de `proveedor`."""
    detalle = detalle_de_error(cuerpo).lower()
    codigo = ""
    c = cuerpo[0] if isinstance(cuerpo, list) and cuerpo else cuerpo
    if isinstance(c, dict) and isinstance(c.get("error"), dict):
        codigo = str(c["error"].get("code") or "").lower()
    if estado == 429 or "rate limit" in detalle or "rate-limited" in detalle or "quota" in detalle \
            or estado in (432, 433):
        return "limite"
    if "model" in detalle and estado in (400, 403, 404) or codigo in ("model_not_found", "model_decommissioned") \
            or "no endpoints found" in detalle or "agentic harnesses" in detalle:
        return "modelo"
    if estado in (401, 403) or "api key" in detalle or "auth key" in detalle \
            or "user not found" in detalle or codigo == "invalid_api_key":
        return "key"
    if estado >= 500 or "resourceexhausted" in detalle or "upstream error" in detalle:
        return "saturado"
    return "otro"


# --- La recomendación por función (encargo 15) --------------------------------------
# Lo que sabe hacer cada motor. La nota es lo MEDIDO acá, no lo que dice el catálogo.
APTITUD = {
    "claude": {"busca": True, "vision": True, "lee_archivos": True, "gratis": False,
               "nota": "WebSearch propio, lee fotos y PDF; `--restricted` lo confina"},
    "codex": {"busca": True, "vision": True, "lee_archivos": True, "gratis": False,
              "nota": "su sandbox monta `/` entero: fuera de web, noticias y visión (06c, 11)"},
    "groq": {"busca": False, "vision": False, "lee_archivos": False, "gratis": True,
             "nota": "rápido (0,4 s); `compound` contestó sin buscar en 4 de 5 preguntas (12-09)"},
    "gemini": {"busca": False, "vision": True, "lee_archivos": False, "gratis": True,
               "nota": "visión buena (12-09; 3 s el 01-10); sin búsqueda: el grounding exige billing"},
    "openrouter": {"busca": False, "vision": False, "lee_archivos": False, "gratis": True,
                   "nota": "bolsa gratis compartida: el 01-10 contestó 1 de 5 modelos (en 14 s) "
                           "a una hora y 10 de 17 a otra"},
    "tavily": {"busca": True, "vision": False, "lee_archivos": False, "gratis": True,
               "nota": "buscador (1,2 s): trae `published_date` en noticias; redacta un modelo gratis"},
}
# Lo que necesita cada ruta.
FUNCION = {
    "claude": {"necesita": ("lee_archivos",), "que": "leer los vaults"},
    "codex": {"necesita": ("lee_archivos",), "que": "leer los vaults"},
    "web": {"necesita": ("busca",), "que": "buscar en la web"},
    "noticias": {"necesita": ("busca",), "que": "buscar noticias"},
    "vision": {"necesita": ("vision",), "que": "leer una foto"},
    "boleta": {"necesita": ("vision",), "que": "leer una boleta"},
    "gpt": {"necesita": (), "que": "conocimiento general"},
}
# El orden entre los gratis aptos. OpenRouter va último en cualquier cadena y la
# recomendación nunca lo pone primero (medido el 01-10: poco confiable).
ORDEN_GRATIS = ("tavily", "groq", "gemini", "openrouter")
NUNCA_PRIMERO = {"openrouter"}
_MOTIVO_GRATIS = {
    ("web", "tavily"): "busca gratis y trae la fecha de la fuente",
    ("noticias", "tavily"): "busca noticias gratis y trae la fecha de la fuente",
    ("vision", "gemini"): "lee fotos gratis (los PDF pasan a Claude)",
    ("boleta", "gemini"): "lee fotos de boletas gratis (los PDF pasan a Claude)",
    ("gpt", "groq"): "gratis y rápido; lo llama n8n, como siempre",
    ("gpt", "gemini"): "gratis; contesta si Groq falla o se queda sin cuota",
    ("gpt", "openrouter"): "gratis; último respaldo, lento y poco confiable",
}


def apto(ruta: str, motor: str) -> bool:
    """Si el motor sabe hacer lo que la ruta necesita."""
    return all(APTITUD.get(motor, {}).get(n) for n in FUNCION.get(ruta, {}).get("necesita", ("?",)))


def recomendada(ruta: str, listo: Any, actual: Any = None) -> tuple[list[str], dict[str, str]]:
    """(cadena, motivos) que conviene para `ruta` según su función: primero los gratis
    aptos que están listos, después los pagados permitidos como respaldo. En las rutas
    de vault, sólo los pagados. `motivos` es {cuenta: frase}.

    `listo(ruta, cuenta)` dice si esa cuenta puede contestar en ese bot (las pagadas,
    su sesión; las gratis, su key). `actual` es la cadena de hoy: los pagados de
    respaldo son los que ya están en ella, en su orden, así que sin ningún gratis
    listo queda la cadena pagada de hoy. Sin `actual`, la de por defecto.

    Sólo recomienda: no cambia nada. El atajo llena la edición con esto, después se
    propone y `aplicar-propuesta` vuelve a validar los muros."""
    if ruta not in FUNCION or ruta not in PROHIBIDO:
        return [], {}

    def sirve(cuenta: str) -> bool:
        return permitida(ruta, cuenta)[0] and apto(ruta, MOTOR_DE_CUENTA[cuenta])

    gratis = [] if ruta in RUTAS_DE_VAULT else \
        [c for c in ORDEN_GRATIS if sirve(c) and listo(ruta, c)]
    if gratis and gratis[0] in NUNCA_PRIMERO:
        gratis = []
    pagadas = [c for c in (actual if isinstance(actual, list) else [])
               if isinstance(c, str) and c in MOTOR_DE_CUENTA and not es_gratis(c) and sirve(c)]
    if not pagadas:
        pagadas = [c for c in CADENA_POR_DEFECTO.get(ruta, []) if not es_gratis(c) and sirve(c)]
    if not pagadas:
        pagadas = [c for c in MOTOR_DE_CUENTA if not es_gratis(c) and sirve(c) and listo(ruta, c)]
    pagadas = list(dict.fromkeys(pagadas))

    motivos = {}
    for c in gratis:
        frase = _MOTIVO_GRATIS.get((ruta, c), "gratis y apto para " + FUNCION[ruta]["que"])
        nombre = NOMBRE_CUENTA[c]
        if PROVEEDORES[c].get("buscador"):
            redactor = next((r for r in REDACTORES if listo("web", r)), None)
            nombre += f" + {NOMBRE_CUENTA[redactor]}" if redactor else ""
        motivos[c] = f"{nombre}: {frase}"
    for c in pagadas:
        if ruta in RUTAS_DE_VAULT:
            frase = "lee los vaults; ningún proveedor gratis puede (" + _VAULT_NO_SALE + ")"
        elif gratis:
            frase = "respaldo pagado si el gratis falla o llega a su límite"
        else:
            frase = "no hay un proveedor gratis apto y listo en este bot para " + FUNCION[ruta]["que"]
        motivos[c] = f"{NOMBRE_CUENTA[c]}: {frase}"
    return gratis + pagadas, motivos


def muros() -> dict[str, Any]:
    """La tabla entera en una forma que la página puede pintar sin repetir reglas."""
    rutas = {}
    for ruta in RUTAS_CON_CUENTA:
        celdas = {}
        for cuenta, motor in MOTOR_DE_CUENTA.items():
            ok, motivo = permitida(ruta, cuenta)
            celdas[cuenta] = {"permitida": ok, "motivo": motivo,
                              "aviso": AVISOS.get((ruta, motor), "") if ok else ""}
        # Desde el 15 la general ya no es fija: elige entre los proveedores gratis.
        rutas[ruta] = {"nombre": ruta_nombre(ruta), "fija": None, "cuentas": celdas,
                       "necesita": list(FUNCION[ruta]["necesita"]), "que": FUNCION[ruta]["que"]}
    for ruta, motivo in RUTAS_FIJAS.items():
        rutas[ruta] = {"nombre": ruta_nombre(ruta), "fija": motivo, "cuentas": {}}
    return {"rutas": rutas,
            "cuentas": {c: {"nombre": NOMBRE_CUENTA[c], "motor": m,
                            "pagada": m not in MOTORES_SIN_CUENTA}
                        for c, m in MOTOR_DE_CUENTA.items()},
            "aptitud": {m: dict(a) for m, a in APTITUD.items()},
            # Sin `url`: la página no llama a nadie, sólo dice qué es cada uno.
            "proveedores": {c: {"nombre": NOMBRE_CUENTA[c], "key": p["key"], "que_es": p["que_es"],
                                "buscador": bool(p.get("buscador")), "modelo": p["modelo"],
                                "modelo_var": p["modelo_var"], "nota": APTITUD[c]["nota"]}
                            for c, p in PROVEEDORES.items()}}


# Atajos de reparto de la página 💳. Sólo LLENAN la edición: después se revisa y se
# propone, y `aplicar-propuesta` vuelve a validar todo. Se calculan acá, y no en el
# navegador, para que salgan de la misma tabla de muros y se puedan probar.
ATAJOS = (("recomendado", "Recomendado por función"),
          ("ahorrar_diego", "Ahorrar Claude (Diego)"),
          ("priorizar_cami", "Priorizar Claude (Cami)"),
          ("codex_primero", "Codex primero"),
          ("gratis", "Gratis donde se pueda"),
          ("desplegado", "Como está desplegado"))


def atajos(cadenas: dict[str, list[str]], lista: Any) -> dict[str, dict[str, Any]]:
    """{atajo: {etiqueta, cadenas, nota}} a partir de las cadenas desplegadas
    (`{ruta interna: [cuenta, ...]}`). `lista(ruta, cuenta)` dice si esa cuenta tiene
    sesión (o, Groq, con qué llamarlo) en ese bot: un atajo nunca pone delante una
    cuenta que no puede contestar ni una celda prohibida. Donde no puede hacer nada,
    deja la cadena como está y `nota` lo dice."""
    def primero(cuenta: str) -> tuple[dict[str, list[str]], list[str]]:
        nuevas, sin = {}, []
        for ruta, ids in cadenas.items():
            if permitida(ruta, cuenta)[0] and lista(ruta, cuenta):
                nuevas[ruta] = [cuenta] + [c for c in ids if c != cuenta]
            else:
                nuevas[ruta] = list(ids)
                if permitida(ruta, cuenta)[0]:
                    sin.append(ruta_nombre(ruta))
        return nuevas, sin

    def ahorrar(cuenta: str) -> tuple[dict[str, list[str]], list[str]]:
        nuevas, sin = {}, []
        for ruta, ids in cadenas.items():
            if cuenta not in ids:
                nuevas[ruta] = list(ids)
                continue
            otras = [c for c in ids if c != cuenta]
            if not otras:
                # Era la única: se le pone delante otra cuenta pagada que pueda contestar.
                otras = [c for c, m in MOTOR_DE_CUENTA.items()
                         if c != cuenta and m not in MOTORES_SIN_CUENTA
                         and permitida(ruta, c)[0] and lista(ruta, c)][:1]
                if not otras:
                    sin.append(ruta_nombre(ruta))
            nuevas[ruta] = otras + [cuenta]
        return nuevas, sin

    out = {}
    for clave, etiqueta in ATAJOS:
        if clave == "recomendado":
            # 15: por función. Donde `recomendada` no arma nada, la cadena queda igual.
            nuevas, sin = {}, []
            for ruta, ids in cadenas.items():
                rec = recomendada(ruta, lista, ids)[0]
                nuevas[ruta] = rec or list(ids)
                if ruta not in RUTAS_DE_VAULT and not any(es_gratis(c) for c in rec):
                    sin.append(ruta_nombre(ruta))
            nota = f"sin un proveedor gratis apto y con key para: {', '.join(sin)}" if sin else ""
        elif clave == "ahorrar_diego":
            nuevas, sin = ahorrar("claude_diego")
            nota = f"sin otra cuenta con sesión en: {', '.join(sin)}" if sin else ""
        elif clave == "desplegado":
            nuevas, nota = {r: list(ids) for r, ids in cadenas.items()}, ""
        else:
            cuenta = {"priorizar_cami": "claude_cami", "codex_primero": "codex",
                      "gratis": "groq"}[clave]
            nuevas, sin = primero(cuenta)
            nota = (f"{NOMBRE_CUENTA[cuenta]} no está listo en este bot para: "
                    f"{', '.join(sin)}") if sin else ""
        out[clave] = {"etiqueta": etiqueta, "cadenas": nuevas, "nota": nota}
    return out


# Umbral global por cuenta (decisión 3): se salta la cuenta si llegó al 80 % semanal
# o al 90 % de la ventana de 5 h. Se cambia por cuenta en cuentas.toml y una receta
# puede ponerle excepción para su ruta.
UMBRAL_SEMANAL = 80
UMBRAL_5H = 90


def umbral_valido(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 100


def umbrales_de(registro: dict[str, Any] | None, cuentas: list[str]) -> dict[str, dict[str, int]]:
    """{cuenta: {semanal, 5h}} desde cuentas.toml; lo que falte o no valga, el global."""
    out = {}
    for cid in cuentas:
        r = (registro or {}).get(cid) or {}
        sem, h5 = r.get("umbral_semanal"), r.get("umbral_5h")
        out[cid] = {"semanal": sem if umbral_valido(sem) else UMBRAL_SEMANAL,
                    "5h": h5 if umbral_valido(h5) else UMBRAL_5H}
    return out


def limites_de(uso: Any) -> dict[str, dict[str, Any]]:
    """{cuenta: limites} desde uso.json (`cuentas_interactivo.<cuenta>.limites`).
    La misma forma que lee bots-info (encargos 01 y 03)."""
    crudo = (uso or {}).get("cuentas_interactivo") if isinstance(uso, dict) else None
    return {cid: c["limites"] for cid, c in (crudo or {}).items()
            if isinstance(c, dict) and isinstance(c.get("limites"), dict)}


def leer_uso(ruta: str) -> Any:
    try:
        with open(ruta, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _fecha(texto: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(texto))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else None


def porcentaje(limites: dict[str, Any] | None, ventana: str, ahora: datetime) -> float | None:
    """% usado de una ventana (`semanal` o `ventana_5h`), o None si no hay dato. Una
    ventana cuya renovación ya pasó tampoco es dato: ese % es de antes del reinicio."""
    v = (limites or {}).get(ventana)
    if not isinstance(v, dict):
        return None
    pct = v.get("usado_pct")
    if isinstance(pct, bool) or not isinstance(pct, (int, float)):
        return None
    renueva = _fecha(v.get("renueva"))
    if renueva is not None and renueva <= ahora:
        return None
    return float(pct)


def tiene_sesion(motor: str, carpeta: str) -> bool:
    """El mismo criterio que `aplicar-propuesta`: no lee tokens. Codex, que exista
    auth.json; Claude, que .claude.json tenga el correo de oauthAccount. Groq no
    tiene login ni carpeta: eso se mira con `groq_listo`."""
    if motor in MOTORES_SIN_CUENTA:
        return False
    if motor == "codex":
        return os.path.isfile(os.path.join(carpeta, "auth.json"))
    try:
        with open(os.path.join(carpeta, ".claude.json"), encoding="utf-8") as fh:
            return bool((json.load(fh).get("oauthAccount") or {}).get("emailAddress"))
    except (OSError, ValueError, AttributeError):
        return False


def elegir_orden(cadena: list[str], todas: list[str], con_sesion: set[str],
                 limites: dict[str, Any], umbrales: dict[str, dict[str, int]],
                 receta: dict[str, Any] | None, ahora: datetime) -> dict[str, Any]:
    """El orden en que se prueban las cuentas de una ruta en ESTA consulta.

    - `cadena`: la lista `cuentas` del perfil para la ruta; `todas`: las cuentas
      conocidas (el modo automático puede usar cualquiera con sesión).
    - Se descartan las sin sesión. Si no queda ninguna, el orden sale vacío y
      `sin_sesion` lo dice: volver a probar las que se acaban de descartar sólo
      gasta un intento que va a fallar (06br1, cierra el hallazgo 1 del 06ar).
    - Automático: todas las con sesión, primero las bajo el umbral por menos %
      semanal, después las sin dato y al final, de respaldo, las sobre el umbral.
    - Si no: el orden de la cadena, saltando las que pasan el umbral.
    - Si todas pasan el umbral, contesta la menos cargada y `todas_sobre` lo avisa.
    - Sin dato de límites no se salta nada: falta de información no es cuota agotada.
    - Un proveedor sin cuenta pagada (Groq) no tiene límites de cuenta: el umbral no
      lo salta nunca, aunque alguien escriba un % a su nombre en uso.json.
    - 15: los proveedores gratis que la cadena pone DELANTE de toda cuenta pagada se
      quedan delante también en automático. El automático reparte la carga entre las
      pagadas; un gratis puesto primero está ahí justamente para no gastarlas.
    """
    receta = receta or {}
    automatico = bool(receta.get("automatico"))
    base = list(dict.fromkeys(cadena + [c for c in todas if c not in cadena])) \
        if automatico else list(cadena)
    candidatas = [c for c in base if c in con_sesion]

    detalle = {}
    for c in candidatas:
        u = dict(umbrales.get(c) or {"semanal": UMBRAL_SEMANAL, "5h": UMBRAL_5H})
        if umbral_valido(receta.get("umbral_semanal")):
            u["semanal"] = receta["umbral_semanal"]
        if umbral_valido(receta.get("umbral_5h")):
            u["5h"] = receta["umbral_5h"]
        sin_limites = MOTOR_DE_CUENTA.get(c) in MOTORES_SIN_CUENTA
        sem = None if sin_limites else porcentaje(limites.get(c), "semanal", ahora)
        h5 = None if sin_limites else porcentaje(limites.get(c), "ventana_5h", ahora)
        sobre = (sem is not None and sem >= u["semanal"]) or (h5 is not None and h5 >= u["5h"])
        detalle[c] = {"semanal": sem, "5h": h5, "umbral_semanal": u["semanal"],
                      "umbral_5h": u["5h"], "sobre": sobre, "sesion": c in con_sesion}

    def carga(c: str) -> tuple:
        d = detalle[c]
        # Sin dato va después de los que sí tienen, en el orden base.
        return (d["semanal"] is None, d["semanal"] or 0.0, d["5h"] or 0.0, base.index(c))

    bajo = [c for c in candidatas if not detalle[c]["sobre"]]
    todas_sobre = bool(candidatas) and not bajo
    if todas_sobre:
        orden = sorted(candidatas, key=carga)
    elif automatico:
        delante = []
        for c in cadena:
            if not es_gratis(c):
                break
            if c in candidatas:
                delante.append(c)
        resto = [c for c in bajo if c not in delante]
        # «Se ordenan todas y se ponen primero las que no pasan el umbral»: las de
        # arriba quedan de último respaldo, no afuera.
        orden = delante + sorted(resto, key=carga) + \
            sorted((c for c in candidatas if c not in bajo), key=carga)
    else:
        orden = bajo
    return {"orden": orden, "automatico": automatico, "todas_sobre": todas_sobre,
            "detalle": detalle, "sin_sesion": bool(base) and not candidatas}


def libre_de(detalle: dict[str, Any] | None) -> float | None:
    """«¿Quién tiene margen?» (encargo 13): lo libre de la ventana MÁS APRETADA, 5 h o semanal, de un `detalle` de
    elegir_orden. None sin dato. La usan el bot (ruta técnica, 96) y `bots-info` (margen_de): una sola cuenta."""
    d = detalle or {}
    libres = [round(100 - max(0.0, min(100.0, float(x))), 1) for x in (d.get("5h"), d.get("semanal"))
              if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return min(libres) if libres else None


def orden_por_margen(cuentas: list[str], detalle: dict[str, Any], base: list[str] | None = None,
                     fija: str | None = None) -> list[str]:
    """El orden de «¿Quién tiene margen?»: primero las que no pasan el umbral, por más libre (la ventana más
    apretada); después las sin dato; al final, de respaldo, las sobre el umbral. El empate lo decide `base` (la
    cadena del perfil). `fija` (96, modo fijo) va primero si no está sobre el umbral."""
    base = list(base or cuentas)
    pos = {c: (base.index(c) if c in base else len(base) + i) for i, c in enumerate(cuentas)}

    def clave(c: str) -> tuple:
        d = detalle.get(c) or {}
        libre = libre_de(d)
        return (bool(d.get("sobre")), libre is None, -(libre or 0.0), pos[c])
    orden = sorted(cuentas, key=clave)
    if fija in orden and not (detalle.get(fija) or {}).get("sobre"):
        orden.remove(fija)
        orden.insert(0, fija)
    return orden


def aviso_todas_sobre(cuenta: str, nombre: str, detalle: dict[str, Any]) -> str:
    """«⚠️ todas sobre el umbral, contestó Codex (85 %)», con el % semanal."""
    d = detalle.get(cuenta) or {}
    pct = d.get("semanal") if d.get("semanal") is not None else d.get("5h")
    cifra = f" ({pct:.0f} %)" if pct is not None else ""
    return f"⚠️ todas sobre el umbral, contestó {nombre}{cifra}"


def normalizar_recetas(crudo: Any, rutas_validas: tuple[str, ...]) -> tuple[dict[str, dict], list[str]]:
    """`recetas = { web = { automatico = true, umbral_semanal = 80, umbral_5h = 90 } }`
    del perfil, con las llaves ya en nombre interno. Lo raro se ignora y se informa:
    un valor malo no tumba el bot ni abre nada."""
    out, problemas = {}, []
    if crudo is None:
        return out, problemas
    if not isinstance(crudo, dict):
        return out, ["recetas no es una tabla; se ignora"]
    for nombre, r in crudo.items():
        ruta = ruta_interna(nombre)
        if ruta not in rutas_validas:
            problemas.append(f"recetas.{nombre}: la ruta no usa cuentas; se ignora")
            continue
        if not isinstance(r, dict):
            problemas.append(f"recetas.{nombre} no es una tabla; se ignora")
            continue
        limpia = {"automatico": r.get("automatico") is True}
        if "automatico" in r and not isinstance(r.get("automatico"), bool):
            problemas.append(f"recetas.{nombre}.automatico={r.get('automatico')!r} no es booleano")
        for k in ("umbral_semanal", "umbral_5h"):
            if k in r:
                if umbral_valido(r[k]):
                    limpia[k] = r[k]
                else:
                    problemas.append(f"recetas.{nombre}.{k}={r[k]!r} fuera de 1-100; se usa el global")
        out[ruta] = limpia
    return out, problemas
