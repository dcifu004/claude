#!/usr/bin/python3
"""bots-info — lo que las paginas 🤖, 💳 y 👾 de Cockpit muestran de los bots y de
las cuentas, en JSON.

Instalado en /usr/local/bin/bots-info. SOLO LEE: no escribe, no reinicia, no
imprime tokens ni el contenido de ningun .env (de la key de cada proveedor gratis
solo dice si el bot la tiene: ver `entorno_del_bot`). La pagina lo llama con
`sudo -n /usr/local/bin/bots-info`; cuando se cierre el Hueco 1 (sudo con
contraseña), este es uno de los scripts que van a la lista blanca de sudoers,
por ruta absoluta y sin argumentos.

Por que root: la cuenta de Claude de cada perfil vive en un claude-config 0700
de otro usuario (botpilar), y la sonda de permisos entra al namespace del
servicio por /proc/<pid>/root, que para un proceso ajeno exige root.

Doctrina, la misma de estado.py: MEDIR en vez de declarar. El perfil dice
`vaults = []`; la sonda mira si el vault se ve DE VERDAD desde adentro del
servicio. Si las dos cosas no coinciden, eso es lo que la pagina pinta en rojo.
"""
import glob
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

VAULT_PI = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/botv3"
BOT_DIR = "/opt/botv3"
UNIDADES = "/etc/systemd/system"
VOCES = "/opt/piper/voces"
PROPUESTAS = "/home/dcifu004/.local/share/bots-propuestas"
TZ = ZoneInfo("America/Santiago")

# Perfiles: el que manda es lo desplegado. Un perfil sin unidad no se muestra.
PERFILES = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{BOT_DIR}/perfiles/*.toml"))

# Lo que la sonda busca adentro de cada servicio. `debe` es lo que corresponde
# segun el perfil: None = no hay expectativa (se informa, no se juzga).
def sondas(perfil, cfg):
    vaults = set(cfg.get("vaults", []))
    otros = [p for p in PERFILES if p != perfil]
    s = [
        ("vault personal", "/opt/nodo/datos/srv/vault_personal", "personal" in vaults),
        ("vault trabajo", "/opt/nodo/datos/srv/vault_trabajo", "trabajo" in vaults),
        ("secretos", "/opt/nodo/datos/secretos", False),
        ("Drive", "/opt/nodo/datos/drive", bool(cfg.get("drive"))),
        ("memoria del nodo", "/opt/nodo/datos/nodo-memoria", True),
        ("casa compartida", "/opt/nodo/datos/casa", True),
        ("/home", "/home", False),
        ("socket de Docker", "/run/docker.sock", False),
    ]
    for o in otros:
        s.append((f"estado de {o}", estado_dir(o), False))
    return s


def sondas_carpetas(perfil, cfg, pid):
    """Cada carpeta de lectura declarada: se tiene que ver DESDE ADENTRO como el
    mismo objeto que la subcarpeta del vault en el host (ver aplicar-propuesta)."""
    out = []
    for rel in cfg.get("carpetas", []) or []:
        nombre = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.basename(rel)).strip("-")[:40]
        dentro = f"/opt/nodo/datos/carpetas/{perfil}/{nombre}"
        visible = None
        if pid:
            try:
                h = os.stat(f"/opt/nodo/datos/srv/vault_personal/{rel}")
                n = os.stat(f"/proc/{pid}/root{dentro}")
                visible = (h.st_dev, h.st_ino) == (n.st_dev, n.st_ino)
            except OSError:
                visible = False
        out.append({"etiqueta": f"carpeta {rel}", "ruta": dentro, "debe": True, "visible": visible})
    return out


def uso_hoy(perfil):
    """Conteo de consultas por ruta de hoy, que deja botv3 en uso-rutas.json."""
    try:
        with open(f"{estado_dir(perfil)}/uso-rutas.json") as fh:
            d = json.load(fh)
        if d.get("fecha") == datetime.now().astimezone().strftime("%Y-%m-%d"):
            return d.get("conteo", {})
    except (OSError, ValueError):
        pass
    return {}


def leer_texto(ruta):
    try:
        with open(ruta, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def estado_dir(perfil):
    # Jaime conserva el directorio historico sin sufijo (ver 10-perfil.conf).
    return "/opt/nodo/datos/botv3" if perfil == "jaime" else f"/opt/nodo/datos/botv3-{perfil}"


def sh(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def md5(ruta):
    try:
        with open(ruta, "rb") as fh:
            return hashlib.md5(fh.read()).hexdigest()
    except OSError:
        return None


def leer_toml(ruta):
    try:
        with open(ruta, "rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def mostrar(pid, ruta):
    """True si desde el namespace del proceso se ve EL MISMO objeto que en el host.

    InaccessiblePaths no borra la ruta: monta encima un nodo de reemplazo de
    /run/systemd/inaccessible/, del MISMO TIPO y con modo 000. Root lo atraviesa
    igual, asi que ni "existe" ni "es un socket" distinguen nada — la primera
    version de esta sonda marco el socket de Docker como visible por eso. Lo que
    si distingue es la identidad: (st_dev, st_ino) del host contra la del
    namespace. Un bind de solo lectura conserva los dos.
    """
    if not pid:
        return None
    try:
        host = os.stat(ruta)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    try:
        dentro = os.stat(f"/proc/{pid}/root{ruta}")
    except FileNotFoundError:
        return False
    except OSError:
        return None
    return (host.st_dev, host.st_ino) == (dentro.st_dev, dentro.st_ino)


def cuenta(config_dir):
    try:
        with open(os.path.join(config_dir, ".claude.json")) as fh:
            a = json.load(fh).get("oauthAccount") or {}
        return a.get("emailAddress")
    except (OSError, ValueError):
        return None


# Encargo 15: los demas proveedores gratis (Gemini, OpenRouter, Tavily) NO se escriben
# aca: los suma `cuentas_todas` desde recetas.py.
# Las tres cuentas pagadas (29-09-2026) y Groq, proveedor SIN cuenta pagada (encargo
# 10): sin login, sin limite semanal y con precio 0. Mismo registro que botv3.py y
# aplicar-propuesta: si se agrega una alla, agregarla aca. Que cuenta puede ir en que
# ruta NO se repite aca: sale de recetas.py (PROHIBIDO), igual que en el bot.
CUENTAS = {
    "claude_diego": {"motor": "claude", "dueno": "Diego", "nombre": "Claude (Diego)"},
    "claude_cami": {"motor": "claude", "dueno": "Camila", "nombre": "Claude (Cami)"},
    "codex": {"motor": "codex", "dueno": "Diego", "nombre": "Codex"},
    "groq": {"motor": "groq", "dueno": "", "nombre": "Groq"},
}
SIN_CUENTA_PAGADA = {"groq"}

# Con que cuentas se abre la sesion interactiva de 👾 IA Agents y el CLAUDE_CONFIG_DIR
# de cada una, relativo al home de dcifu004 ("" = el de siempre, ~/.claude.json).
# Hasta el encargo 13 esta tabla vivia en nodo.js (CUENTAS_CLAUDE); ahora la pagina la
# recibe de aca. Codex tiene una sola cuenta: no hay nada que elegir.
INTERACTIVAS = {"claude_diego": "", "claude_cami": ".config/claude-cami"}
# La pagina arma con esto una linea de shell: solo un camino relativo y sin nada raro.
_DIR_INTERACTIVO = re.compile(r"(?!.*\.\.)[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")


# Las rutas con receta (automatico, umbral y «quien contestaria»). La matriz de la
# pagina usa TODAS las del perfil: ver matriz_de.
RUTAS_CON_CUENTA = ("claude", "codex", "web")

# Etiqueta «lee datos de CyD» por ruta (decision 5 de Diego, 29-09-2026): marcada a
# mano, no deducida de `vaults`. La misma tabla que aplicar-propuesta.
LEE_CYD = {"jaime": {"archivos", "tecnica", "licitaciones"}}
# Las rutas cuyo agente lee los vaults del perfil. La misma tupla que aplicar-propuesta.
RUTAS_LEEN_ARCHIVOS = ("claude", "codex")


def _cargar_recetas():
    """recetas.py del bot DESPLEGADO, no el del vault: bots-info corre como root y el
    vault lo puede escribir dcifu004 (y Syncthing). Si falta, no hay «quien contestaria»."""
    import importlib.util
    ruta = f"{BOT_DIR}/recetas.py"
    try:
        spec = importlib.util.spec_from_file_location("recetas", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except (OSError, ImportError, SyntaxError):
        return None


recetas = _cargar_recetas()


def cuentas_todas(mod=None):
    """CUENTAS mas los proveedores gratis que declara recetas.py (encargo 15: Gemini,
    OpenRouter y Tavily). No se escriben aca: salen de MOTOR_DE_CUENTA y
    MOTORES_SIN_CUENTA, el mismo lugar del que los toma el bot. Con un recetas.py
    anterior al 15 quedan las cuatro de siempre."""
    mod = mod or recetas
    out = dict(CUENTAS)
    gratis = getattr(mod, "MOTORES_SIN_CUENTA", None) or ()
    for cid, motor in (getattr(mod, "MOTOR_DE_CUENTA", None) or {}).items():
        if motor in gratis and cid not in out:
            out[cid] = {"motor": motor, "dueno": "", "nombre": mod.NOMBRE_CUENTA.get(cid, cid)}
    return out


def sin_cuenta_pagada(mod=None):
    mod = mod or recetas
    gratis = getattr(mod, "MOTORES_SIN_CUENTA", None) or ()
    return SIN_CUENTA_PAGADA | {c for c, v in cuentas_todas(mod).items() if v["motor"] in gratis}


def recetas_de(perfil, cfg, por_cuenta, limites, registro, ahora, mod=None):
    """Por ruta de agente: su receta y QUIEN CONTESTARIA AHORA. Usa recetas.elegir_orden,
    la misma funcion con la que decide el bot en cada consulta: la pagina no la repite."""
    mod = mod or recetas
    if mod is None or not isinstance(cfg.get("cuentas"), dict):
        return None
    rutas = {mod.ruta_interna(r) for r in cfg.get("rutas", [])}
    # Sin lo desconocido ni lo que el muro prohibe: lo mismo que descarta el bot.
    permitida = getattr(mod, "permitida", lambda ruta, cuenta: (True, ""))
    todas_las_cuentas = cuentas_todas(mod)
    cadenas = {mod.ruta_interna(r): [c for c in ids if c in todas_las_cuentas
                                     and permitida(mod.ruta_interna(r), c)[0]]
               for r, ids in cfg["cuentas"].items() if isinstance(ids, list)}
    limpias, problemas = mod.normalizar_recetas(cfg.get("recetas"), RUTAS_CON_CUENTA)
    umbrales = mod.umbrales_de(registro, list(todas_las_cuentas))
    con_sesion = {c for c, v in (por_cuenta or {}).items() if v.get("sesion")}
    out = {}
    for ruta in RUTAS_CON_CUENTA:
        if ruta not in rutas or not cadenas.get(ruta):
            continue
        receta = limpias.get(ruta)
        # Las que el automatico puede sumar: pagadas y permitidas en la ruta, como el bot.
        todas = mod.cuentas_del_automatico(ruta) if hasattr(mod, "cuentas_del_automatico") \
            else [c for c in CUENTAS if c not in SIN_CUENTA_PAGADA]
        e = mod.elegir_orden(cadenas[ruta], todas, con_sesion, limites, umbrales,
                             receta, ahora)
        contesta = e["orden"][0] if e["orden"] else None
        nombre = mod.ruta_nombre(ruta)
        out[nombre] = {
            "interna": ruta,
            "receta": receta or {"automatico": False},
            "cadena": cadenas[ruta],
            "orden": e["orden"],
            "contesta": contesta,
            "todas_sobre": e["todas_sobre"],
            # 06br1: sin ninguna sesion no contesta nadie; la pagina dice por que.
            "sin_sesion": bool(e.get("sin_sesion")),
            "aviso": mod.aviso_todas_sobre(contesta, todas_las_cuentas[contesta]["nombre"], e["detalle"])
                     if e["todas_sobre"] and contesta in todas_las_cuentas else None,
            "detalle": e["detalle"],
            "lee_cyd": nombre in LEE_CYD.get(perfil, set()),
        }
    return {"rutas": out, "problemas": problemas}


# Un nombre de modelo (o hasta tres, separados por coma): lo unico del entorno del bot
# cuyo VALOR sale de aca. Lo que no tenga esta forma no se muestra.
_MODELO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/, -]{0,299}")


def entorno_del_bot(pid, mod=None):
    """Si el proceso del bot tiene cada key (GROQ_API_KEY y, desde el 15, las de los
    demas proveedores gratis) y el webhook de n8n, medido en su entorno real
    (/proc/<pid>/environ) y reducido AHI MISMO a "1" o "": el valor no sale de esta
    funcion, ni a la pagina ni a un log. Las variables BOTV3_<ID>_MODEL no son
    secretas: de esas si se lee el valor. None = no se pudo medir."""
    if not pid:
        return None
    try:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            crudo = fh.read()
    except OSError:
        return None
    return reducir_entorno(crudo, mod)


def reducir_entorno(crudo, mod=None):
    """El contenido de /proc/<pid>/environ reducido a lo que se puede mostrar."""
    mod = mod or recetas
    claves = getattr(mod, "CLAVES_DE_ENTORNO", None) or ("BOTV3_N8N_QUERY_URL", "GROQ_API_KEY")
    modelos = getattr(mod, "VARIABLES_DE_MODELO", None) or ()
    out = {c: "" for c in claves}
    for par in crudo.split(b"\0"):
        clave, _, valor = par.partition(b"=")
        clave = clave.decode("ascii", "replace")
        if clave in out:
            out[clave] = "1" if valor.strip() else ""
        elif clave in modelos:
            texto = valor.decode("utf-8", "replace").strip()
            if _MODELO.fullmatch(texto):
                out[clave] = texto
    return out


def cuentas_de(perfil, entorno=None, mod=None):
    """Por cada cuenta, si ESTE bot tiene su login hecho. Medido en el directorio,
    no declarado: una cuenta sin sesion en la cadena falla y cae al respaldo.
    Groq no tiene login: `sesion` es que el bot tenga su key (rutas web y noticias) y
    `sesion_general`, que tenga el webhook de n8n, que es quien lo llama en la general."""
    mod = mod or recetas
    out = {}
    gratis = sin_cuenta_pagada(mod)
    for cid, c in cuentas_todas(mod).items():
        if cid in gratis:
            if hasattr(mod, "falta_para"):
                # 15: sin key un proveedor no existe. `falta` dice que le falta (la key,
                # el webhook o, a Tavily, un modelo que redacte) y `cargar`, la linea
                # con que se carga. Solo se sabe SI la key esta, nunca su valor.
                falta, falta_general = mod.falta_para("web", cid, entorno), mod.falta_para("gpt", cid, entorno)
                out[cid] = {**c, "sesion": not falta, "sesion_general": not falta_general,
                            "medido": entorno is not None, "correo": None, "existe": False,
                            "migrada": False, "falta": falta, "falta_general": falta_general,
                            "key": bool((entorno or {}).get(mod.PROVEEDORES[cid]["key"])),
                            "cargar": mod.linea_para_cargar(cid, perfil),
                            "modelo": mod.modelo_de(cid, entorno)}
                continue
            listo = getattr(mod, "groq_listo", lambda ruta, e: False)
            out[cid] = {**c, "sesion": listo("web", entorno), "sesion_general": listo("gpt", entorno),
                        "medido": entorno is not None, "correo": None, "existe": False,
                        "migrada": False}
            continue
        d = f"{estado_dir(perfil)}/cuentas/{cid}"
        if c["motor"] == "codex":
            sesion, correo = os.path.isfile(f"{d}/auth.json"), None
        else:
            correo = cuenta(d)
            sesion = bool(correo)
        out[cid] = {**c, "sesion": sesion, "correo": correo, "existe": os.path.isdir(d),
                    "migrada": os.path.islink(d)}
    return out


def estado_de_proveedor(falta, medido):
    """La palabra que la pagina muestra de un proveedor gratis en un bot: «listo»,
    «sin key», «no listo» (tiene key pero le falta otra cosa) o «sin medir» (el bot no
    esta corriendo y no hay entorno que mirar)."""
    if not falta:
        return "listo"
    if not medido:
        return "sin medir"
    return "sin key" if falta.startswith("sin key") else "no listo"


def recomendada_de(ruta, lista, cadena, mod):
    """(cadena, motivos) recomendada para una ruta: la calcula recetas.recomendada, POR
    FUNCION (encargo 15, reemplaza al criterio de «la cuenta con mas margen» del 13):
    primero los proveedores gratis aptos que estan listos en ESTE bot, despues los
    pagados de la cadena de hoy; en las rutas de vault, solo los pagados. La pagina le
    pone ⭐ a cada servicio de esa cadena y muestra su motivo: no repite ninguna regla.
    Con un recetas.py anterior al 15 no hay recomendacion."""
    if not hasattr(mod, "recomendada"):
        return [], {}
    return mod.recomendada(ruta, lista, cadena)


def matriz_de(perfil, cfg, por_cuenta, mod=None, limites=None, registro=None, ahora=None):
    """La matriz ruta × proveedor de la pagina (encargo 10): por cada ruta DEL PERFIL,
    su cadena efectiva (la declarada sin lo prohibido, o la de por defecto) o el motivo
    por el que es una herramienta fija; y los atajos de reparto ya calculados. Todo sale
    de recetas.py, la misma tabla de muros que usan el bot y aplicar-propuesta."""
    mod = mod or recetas
    if mod is None or not hasattr(mod, "muros"):
        return None
    filas, cadenas = [], {}

    gratis = sin_cuenta_pagada(mod)

    def lista(ruta, cuenta):
        c = (por_cuenta or {}).get(cuenta) or {}
        if cuenta in gratis and ruta == "gpt":
            return bool(c.get("sesion_general"))
        return bool(c.get("sesion"))

    def celda(ruta, cuenta, m):
        c = (por_cuenta or {}).get(cuenta) or {}
        out = {"cuenta": cuenta, "permitida": bool(m.get("permitida")),
               "motivo": m.get("motivo") or "", "aviso": m.get("aviso") or "",
               "lista": lista(ruta, cuenta)}
        if cuenta in gratis:
            # «sin key»: lo que le falta al proveedor en este bot y como se carga.
            out["falta"] = (c.get("falta_general") if ruta == "gpt" else c.get("falta")) or ""
            out["cargar"] = c.get("cargar") or ""
            out["estado"] = estado_de_proveedor(out["falta"], c.get("medido"))
        return out

    for nombre in cfg.get("rutas", []) or []:
        ruta = mod.ruta_interna(nombre)
        if ruta in cadenas or any(f["interna"] == ruta for f in filas):
            continue
        muro = (mod.muros().get("rutas", {}).get(ruta) or {})
        # Una celda por proveedor, ya resuelta (encargo 13): la pagina 💳 pinta lo que
        # llega y no vuelve a decidir que se permite. Las herramientas fijas no tienen
        # celdas. La general dejo de ser fija con el 15: elige entre los proveedores gratis.
        fila = {"interna": ruta, "nombre": mod.ruta_nombre(ruta), "fija": muro.get("fija"),
                "lee_archivos": ruta in RUTAS_LEEN_ARCHIVOS,
                "celdas": [celda(ruta, c, m) for c, m in (muro.get("cuentas") or {}).items()]}
        if ruta in mod.RUTAS_CON_CUENTA and not fila["fija"]:
            fila["cadena"], fila["declarada"] = mod.cadena_efectiva(ruta, cfg.get("cuentas"))
            fila["recomendada"], fila["motivos"] = recomendada_de(ruta, lista, fila["cadena"], mod)
            cadenas[ruta] = fila["cadena"]
        else:
            fila["fija"] = fila["fija"] or mod.RUTAS_FIJAS.get(
                ruta, "no la contesta un modelo con cuenta")
        filas.append(fila)

    return {"rutas": filas, "atajos": mod.atajos(cadenas, lista)}


def matriz_comun(perfiles, mod=None):
    """La matriz que pinta 💳 Cuentas, con la forma que decidio Diego el 01-10-2026
    (encargos/13-notas-diego.md): FILAS = rutas y COLUMNAS = asistentes. Cada celda es
    la fila de esa ruta en la matriz de ese perfil (`matriz_de`: sus servicios, su
    cadena y su ⭐), o None si el asistente no tiene la ruta: la pagina la deja vacia
    y tenue, no la oculta.
    Las filas salen de recetas.py, en su orden: primero las rutas que contesta un
    modelo (RUTAS_CON_CUENTA), SIEMPRE, las tenga o no algun perfil; despues las
    herramientas fijas (RUTAS_FIJAS) y, al final, cualquier otra, solo si algun perfil
    la tiene. `perfiles` es {id: {"toml": ..., "matriz": ...}}, en el orden de las
    columnas."""
    mod = mod or recetas
    if mod is None or not hasattr(mod, "muros"):
        return None
    por_perfil = {p: {f["interna"]: f for f in ((d.get("matriz") or {}).get("rutas") or [])}
                  for p, d in perfiles.items()}
    orden = list(mod.RUTAS_CON_CUENTA)
    resto = [r for filas in por_perfil.values() for r in filas]
    for ruta in list(mod.RUTAS_FIJAS) + resto:
        if ruta not in orden and any(ruta in filas for filas in por_perfil.values()):
            orden.append(ruta)
    return {
        "perfiles": [{"id": p, "nombre": (d.get("toml") or {}).get("nombre") or p,
                      "persona": (d.get("toml") or {}).get("persona") or ""}
                     for p, d in perfiles.items()],
        "rutas": [{"interna": ruta, "nombre": mod.ruta_nombre(ruta),
                   "celdas": {p: por_perfil[p].get(ruta) for p in perfiles}}
                  for ruta in orden],
    }


def cuentas_publicas(registro=None):
    """La lista de cuentas y proveedores que usan las paginas 🤖, 👾 y 💳 (encargo 13):
    nombre, motor, dueno, si es pagada y, si sirve para la sesion interactiva de 👾, su
    config dir. Es la UNICA lista que ven las paginas: ninguna la vuelve a escribir."""
    out = {}
    gratis = sin_cuenta_pagada()
    for cid, r in (registro or registro_cuentas()).items():
        rel = INTERACTIVAS.get(cid)
        if rel is not None and rel and not _DIR_INTERACTIVO.fullmatch(rel):
            rel = None
        out[cid] = {"nombre": r.get("nombre") or cid, "motor": r.get("motor"),
                    "dueno": r.get("dueno") or "", "pagada": cid not in gratis,
                    # Cuenta pagada de otra persona: lo de CyD que lea queda en su historial
                    # (el mismo criterio con que avisa aplicar-propuesta).
                    "ajena_a_cyd": cid not in gratis and (r.get("dueno") or "") != "Diego",
                    "interactiva": None if rel is None else {"config_dir": rel}}
    return out


def margen_de(registro, limites, ahora, resumen=None, mod=None):
    """«¿Quien tiene margen?», lo primero que muestra 💳 Cuentas (encargo 13): por
    cuenta, el % usado de la ventana de 5 h y de la semana, cuando se renueva cada una y
    si el bot la esta saltando por el umbral. El % y el «sobre el umbral» salen de
    recetas.elegir_orden, la misma funcion con la que decide el bot: una ventana cuya
    renovacion ya paso no es dato (`renovada`), igual que alla."""
    mod = mod or recetas
    if mod is None:
        return None
    limites = limites or {}
    umbrales = mod.umbrales_de(registro, list(registro))

    def ventana(cid, clave, usado):
        v = (limites.get(cid) or {}).get(clave)
        medido = isinstance(v, dict) and isinstance(v.get("usado_pct"), (int, float)) \
            and not isinstance(v.get("usado_pct"), bool)
        if not medido:
            return None
        usado = None if usado is None else max(0.0, min(100.0, float(usado)))
        return {"usado_pct": usado, "libre_pct": None if usado is None else round(100 - usado, 1),
                "renueva": v.get("renueva") or None,
                # Medido antes de una renovacion que ya paso: desde entonces no hay dato.
                "renovada": usado is None}

    cuentas = {}
    gratis = sin_cuenta_pagada(mod)
    for cid, r in registro.items():
        pagada = cid not in gratis
        item = {"nombre": r.get("nombre") or cid, "pagada": pagada, "momento": None,
                "viejo": False, "ventana_5h": None, "semanal": None, "sobre": False,
                "libre_pct": None, "renueva_semana": None}
        if pagada:
            d = mod.elegir_orden([cid], [cid], {cid}, limites, umbrales, None, ahora)["detalle"][cid]
            item["ventana_5h"] = ventana(cid, "ventana_5h", d["5h"])
            item["semanal"] = ventana(cid, "semanal", d["semanal"])
            item["umbral_semanal"], item["umbral_5h"] = d["umbral_semanal"], d["umbral_5h"]
            item["sobre"] = bool(d["sobre"])
            libres = [v["libre_pct"] for v in (item["ventana_5h"], item["semanal"])
                      if v and v["libre_pct"] is not None]
            # El margen real es el de la ventana mas apretada.
            item["libre_pct"] = min(libres) if libres else None
            momento = (limites.get(cid) or {}).get("momento")
            try:
                medido = datetime.fromisoformat(momento)
                item["momento"] = momento
                item["viejo"] = medido.tzinfo is not None and ahora - medido > timedelta(hours=24)
            except (TypeError, ValueError):
                pass
            # Cuando vuelve el limite semanal: lo medido si sigue vigente; si no, el
            # ciclo del registro (el mismo con que se reparte el precio).
            sem = item["semanal"]
            if sem and sem["renueva"] and not sem["renovada"]:
                item["renueva_semana"] = {"cuando": sem["renueva"], "origen": "medido"}
            else:
                c = ((resumen or {}).get("cuentas") or {}).get(cid) or {}
                if c.get("proxima_renovacion"):
                    item["renueva_semana"] = {"cuando": c["proxima_renovacion"],
                                              "origen": c.get("renueva_origen") or "supuesto"}
        cuentas[cid] = item
    pagadas = [c for c, v in cuentas.items() if v["pagada"]]
    # Primero las que el bot no esta saltando, con mas margen arriba; sin dato, al final.
    orden = sorted(pagadas, key=lambda c: (cuentas[c]["sobre"], cuentas[c]["libre_pct"] is None,
                                           -(cuentas[c]["libre_pct"] or 0), pagadas.index(c)))
    con_margen = next((c for c in orden if not cuentas[c]["sobre"]
                       and cuentas[c]["libre_pct"] is not None), None)
    return {"cuentas": cuentas, "orden": orden + [c for c in cuentas if c not in pagadas],
            "con_margen": con_margen}


# --- Historial y costo por ciclo semanal (30-09-2026) -------------------------------
# Cada cuenta se renueva por semana (su limite semanal). El precio mensual se prorratea
# por semana (× 12 / 52) y se reparte entre quienes la usaron EN ESE CICLO, en
# proporcion a lo que consumieron. Lo que nadie uso queda como «ocioso»: tambien se
# pago, y esconderlo haria creer que las rutas cuestan menos.
#
# El peso imita la proporcion de precios de cada proveedor, que no depende del modelo:
# en Anthropic la salida vale 5× la entrada, escribir cache 1,25× y leerlo 0,1×. Codex
# no da desglose en `exec`, asi que ahi el peso es el total de tokens (igual en el bot
# y en las sesiones interactivas, para que sean comparables). Si algun intento de un
# ciclo no trae tokens, ese ciclo se reparte por CONSULTAS y se dice.
REGISTRO = f"{BOT_DIR}/cuentas.toml"
# El boton «probar» de 💳 Cuentas (encargo 15) corre este script como dcifu004, sin sudo:
# se instala con la pagina. La pagina le agrega el proveedor y el perfil.
PROBAR = ["python3", "/home/dcifu004/.local/share/cockpit/cuentas/probar-proveedor.py"]
USO_JSON = "/opt/nodo/datos/uso.json"
DIAS = {"lun": 0, "mar": 1, "mie": 2, "mié": 2, "jue": 3, "vie": 4, "sab": 5, "sáb": 5, "dom": 6}
CICLOS_MOSTRADOS = 8


def registro_cuentas():
    reg = leer_toml(REGISTRO) or {}
    out = {}
    gratis = sin_cuenta_pagada()
    for cid, base in cuentas_todas().items():
        # Un proveedor gratis no se paga: 0 aunque el cuentas.toml desplegado sea
        # anterior a su tabla (Groq, encargo 10; Gemini, OpenRouter y Tavily, 15).
        r = {**base, "precio_mes_usd": 0 if cid in gratis else 20, "renueva": "",
             **(reg.get(cid) or {})}
        if cid in gratis:
            r["precio_mes_usd"] = 0
        out[cid] = r
    return out


def proveedores_gratis(perfiles, mod=None):
    """La tabla «🆓 Proveedores gratis» de 💳 Cuentas (encargo 15): que es cada uno, que
    variable trae su key, su modelo y su nota medida (todo de recetas.py), y por
    asistente si esta listo o «sin key», con la linea para cargarla. La pagina no decide
    nada de esto: lo pinta. Con un recetas.py anterior al 15, None."""
    mod = mod or recetas
    tabla = (mod.muros().get("proveedores") if mod is not None and hasattr(mod, "muros") else None)
    if not tabla:
        return None
    out = {}
    for cid, p in tabla.items():
        por_perfil = {}
        for perfil, d in perfiles.items():
            c = (d.get("por_cuenta") or {}).get(cid) or {}
            por_perfil[perfil] = {"key": bool(c.get("key")), "medido": bool(c.get("medido")),
                                  "listo": bool(c.get("sesion")), "falta": c.get("falta") or "",
                                  "estado": estado_de_proveedor(c.get("falta") or "", c.get("medido")),
                                  "cargar": c.get("cargar") or "", "modelo": c.get("modelo") or ""}
        rutas = [mod.ruta_nombre(r) for r in mod.RUTAS_CON_CUENTA if mod.permitida(r, cid)[0]]
        out[cid] = {**p, "rutas": rutas, "por_perfil": por_perfil}
    return {"proveedores": out, "clases_de_error": dict(getattr(mod, "CLASES_DE_ERROR", {})),
            # Lo que ejecuta el boton «probar» (una llamada, con la key del bot elegido).
            "probar": PROBAR}


def renovacion(texto):
    """'lun 09:00' → (dia 0-6, hora, minuto, supuesto). Vacio o raro = lunes 00:00."""
    m = re.fullmatch(r"\s*(\w+)\s+(\d{1,2}):(\d{2})\s*", texto or "")
    if m and m.group(1).lower() in DIAS and int(m.group(2)) < 24 and int(m.group(3)) < 60:
        return DIAS[m.group(1).lower()], int(m.group(2)), int(m.group(3)), False
    return 0, 0, 0, True


def inicio_ciclo(momento, dia, hora, minuto):
    base = momento.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    base -= timedelta(days=(momento.weekday() - dia) % 7)
    return base if base <= momento else base - timedelta(days=7)


def peso(motor, t):
    if not isinstance(t, dict):
        return None
    if motor == "codex":
        return t.get("total", (t.get("entrada") or 0) + (t.get("cache_lectura") or 0)
                     + (t.get("salida") or 0))
    return ((t.get("entrada") or 0) + 1.25 * (t.get("cache_escritura") or 0)
            + 0.1 * (t.get("cache_lectura") or 0) + 5 * (t.get("salida") or 0))


def eventos_de_uso(perfiles, uso_json):
    """Todo el consumo en una lista: (momento, cuenta, clave de ruta, ok, tokens)."""
    ev = []
    for p in perfiles:
        try:
            fh = open(f"{estado_dir(p)}/uso-cuentas.jsonl", encoding="utf-8")
        except OSError:
            continue
        with fh:
            for ln in fh:
                try:
                    d = json.loads(ln)
                    ev.append((datetime.fromisoformat(d["ts"]), d["cuenta"],
                               f"{d.get('perfil', p)}/{d['ruta']}", bool(d.get("ok")), d.get("tokens")))
                except (ValueError, KeyError, TypeError):
                    continue
    for cid, c in ((uso_json or {}).get("cuentas_interactivo") or {}).items():
        for hora, t in (c.get("por_hora") or {}).items():
            try:
                m = datetime.fromisoformat(hora + ":30").replace(tzinfo=TZ)
            except ValueError:
                continue
            # Un balde interactivo reúne varios mensajes. Su peso sigue siendo
            # el total de tokens del balde, pero para el reparto por consultas
            # vale cada mensaje, no una consulta artificial por hora.
            try:
                consultas = max(0, int(t.get("mensajes", 0)))
            except (AttributeError, TypeError, ValueError):
                consultas = 0
            ev.append((m, cid, "pi/interactivo", True, t, consultas))
    # Reportes ya filtrados por uso.py: cada PC es una ruta propia para que el
    # reparto no esconda consumo interactivo dentro de «ocioso».
    for equipo, reporte in ((uso_json or {}).get("equipos", {}).get("activos", {}) or {}).items():
        for cid, c in (reporte.get("cuentas") or {}).items():
            for hora, t in (c.get("por_hora") or {}).items():
                try:
                    m = datetime.fromisoformat(hora + ":30").replace(tzinfo=TZ)
                    consultas = max(0, int(t.get("mensajes", 0)))
                except (ValueError, TypeError, AttributeError):
                    continue
                ev.append((m, cid, f"pc:{equipo}", True, t, consultas))
    return ev


def _percentil(valores, p):
    """Percentil por rango más cercano: estable y legible con pocas respuestas."""
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[max(0, math.ceil(p * len(ordenados)) - 1)]


def _tokens_respuesta(tokens):
    if not isinstance(tokens, dict):
        return None
    try:
        if "total" in tokens:
            return int(tokens["total"] or 0)
        return sum(int(tokens.get(k) or 0) for k in
                   ("entrada", "salida", "cache_lectura", "cache_escritura"))
    except (TypeError, ValueError):
        return None


def _libro_rendimiento(perfiles):
    """Intentos y votos reales del JSONL; también conserva líneas previas al id."""
    intentos, votos = [], {}
    for p in perfiles:
        try:
            fh = open(f"{estado_dir(p)}/uso-cuentas.jsonl", encoding="utf-8")
        except OSError:
            continue
        with fh:
            for ln in fh:
                try:
                    d = json.loads(ln)
                    if d.get("tipo") == "calificacion":
                        if d.get("valor") in (1, -1) and isinstance(d.get("id"), str):
                            votos[d["id"]] = d["valor"]
                        continue
                    momento = datetime.fromisoformat(d["ts"])
                    # El id nació con los botones de calificación. Las líneas
                    # anteriores son consumo real y tienen que seguir entrando al
                    # reparto, aunque naturalmente no puedan recibir un voto.
                    if not all(k in d for k in ("cuenta", "motor", "ruta", "ok", "s")):
                        continue
                    intentos.append({**d, "id": d.get("id"),
                                     "perfil": d.get("perfil", p), "momento": momento})
                except (ValueError, TypeError, KeyError):
                    continue
    return intentos, votos


def _renovacion_de_cuenta(registro, limites):
    """La misma prioridad de renovación que la tabla «Por ruta»."""
    if registro.get("renueva"):
        dia, hh, mm, _ = renovacion(registro["renueva"])
    elif ((limites or {}).get("semanal") or {}).get("renueva"):
        try:
            medida = datetime.fromisoformat(limites["semanal"]["renueva"]).astimezone(TZ)
            dia, hh, mm = medida.weekday(), medida.hour, medida.minute
        except ValueError:
            dia, hh, mm, _ = renovacion("")
    else:
        dia, hh, mm, _ = renovacion("")
    return dia, hh, mm


def _costos_por_intento(registro, intentos, uso_json, limites):
    """Reparte cada USD de resumen_cuentas entre los intentos que lo originaron.

    Los baldes de uso interactivo participan aunque no tengan un id de intento:
    así absorben su parte antes de asignar el costo a las respuestas del bot.
    """
    eventos = []
    for i, e in enumerate(intentos):
        momento = e["momento"]
        if momento.tzinfo is None:
            momento = momento.replace(tzinfo=TZ)
        eventos.append({"momento": momento.astimezone(TZ), "cuenta": e.get("cuenta"),
                        "ruta": f"{e.get('perfil')}/{e.get('ruta')}", "ok": bool(e.get("ok")),
                        "tokens": e.get("tokens"), "consultas": 1, "indice": i})
    for m, cuenta, ruta, ok, tokens, consultas in eventos_de_uso([], uso_json):
        eventos.append({"momento": m.astimezone(TZ), "cuenta": cuenta, "ruta": ruta,
                        "ok": ok, "tokens": tokens, "consultas": consultas, "indice": None})

    costos = {}
    for cid, cuenta_reg in registro.items():
        dia, hh, mm = _renovacion_de_cuenta(cuenta_reg, (limites or {}).get(cid))
        semanal = round(float(cuenta_reg.get("precio_mes_usd") or 0) * 12 / 52, 2)
        ciclos = {}
        for evento in eventos:
            if evento["cuenta"] != cid:
                continue
            ciclo = inicio_ciclo(evento["momento"], dia, hh, mm)
            ciclos.setdefault(ciclo, []).append(evento)
        for eventos_ciclo in ciclos.values():
            exitosos = [e for e in eventos_ciclo if e["ok"]]
            sin_tokens = any(peso(cuenta_reg.get("motor"), e["tokens"]) is None for e in exitosos)
            por_ruta = {}
            for e in exitosos:
                r = por_ruta.setdefault(e["ruta"], [])
                r.append(e)
            total = sum(sum(e["consultas"] if sin_tokens else
                            (peso(cuenta_reg.get("motor"), e["tokens"]) or 0) for e in es)
                        for es in por_ruta.values())
            if not total:
                continue
            for es in por_ruta.values():
                peso_ruta = sum(e["consultas"] if sin_tokens else
                                 (peso(cuenta_reg.get("motor"), e["tokens"]) or 0) for e in es)
                # Mismo redondeo por ruta que resumen_cuentas; después se divide
                # entre sus intentos reales, sin regalar el consumo interactivo.
                usd_ruta = round(semanal * peso_ruta / total, 2)
                for e in es:
                    if e["indice"] is None:
                        continue
                    unidad = e["consultas"] if sin_tokens else (peso(cuenta_reg.get("motor"), e["tokens"]) or 0)
                    costos[e["indice"]] = usd_ruta * unidad / peso_ruta if peso_ruta else 0.0
    return costos


def rendimiento(registro, perfiles, ahora, uso_json=None):
    """Rendimiento de 30 días por cuenta y motor, y su costo semanal asignado."""
    intentos, votos = _libro_rendimiento(perfiles)
    desde = ahora - timedelta(days=30)
    # Primero se calcula el reparto completo del ciclo; recién después se filtra
    # la vista de 30 días. Es exactamente el reparto de resumen_cuentas.
    costos = _costos_por_intento(registro, intentos, uso_json, limites_de(uso_json))

    grupos = {}
    for i, e in enumerate(intentos):
        momento = e["momento"]
        if momento.tzinfo is None:
            momento = momento.replace(tzinfo=TZ)
        if momento.astimezone(TZ) < desde:
            continue
        # Las fallas pueden no traer modelo (timeout de Codex o error temprano de
        # Claude). Por eso la tasa se agrupa sólo por cuenta y motor; el modelo
        # mostrado se elige después entre los intentos OK que sí lo informan.
        clave = (e.get("cuenta"), e.get("motor"))
        g = grupos.setdefault(clave, {"cuenta": e.get("cuenta"), "motor": e.get("motor"),
                                      "modelos_ok": {}, "intentos": 0,
                                      "fallidas": 0, "segundos": [], "tokens_lista": [],
                                      "positivos": 0, "negativos": 0, "usd_asignado": 0.0,
                                      "ok": 0})
        g["intentos"] += 1
        g["fallidas"] += 0 if e.get("ok") else 1
        g["ok"] += 1 if e.get("ok") else 0
        modelo = e.get("modelo")
        if e.get("ok") and isinstance(modelo, str) and modelo.strip():
            modelo = modelo.strip()
            g["modelos_ok"][modelo] = g["modelos_ok"].get(modelo, 0) + 1
        try:
            g["segundos"].append(float(e.get("s")))
        except (TypeError, ValueError):
            pass
        tok = _tokens_respuesta(e.get("tokens"))
        if tok is not None:
            g["tokens_lista"].append(tok)
        voto = votos.get(e.get("id"))
        g["positivos"] += voto == 1
        g["negativos"] += voto == -1
        g["usd_asignado"] += costos.get(i, 0.0)
    salida = []
    for g in grupos.values():
        base_n = g["positivos"] or g["ok"]
        modelo = max(g["modelos_ok"].items(), key=lambda x: (x[1], x[0]))[0] \
            if g["modelos_ok"] else None
        salida.append({"cuenta": g["cuenta"], "motor": g["motor"], "modelo": modelo,
                       "intentos": g["intentos"],
                       "tasa_falla": round(g["fallidas"] / g["intentos"], 4),
                       "p50_s": _percentil(g["segundos"], .5), "p90_s": _percentil(g["segundos"], .9),
                       "tokens_medianos": _percentil(g["tokens_lista"], .5),
                       "positivos": g["positivos"], "negativos": g["negativos"],
                       "usd_asignado": round(g["usd_asignado"], 4),
                       "costo_respuesta_util_usd": round(g["usd_asignado"] / base_n, 4) if base_n else None,
                       "base": "👍" if g["positivos"] else "respuestas OK"})
    return sorted(salida, key=lambda x: (x["cuenta"] or "", x["motor"] or ""))


def resumen_cuentas(registro, eventos, ahora, limites_interactivo=None):
    cuentas, por_ruta = {}, {}
    mes_actual = ahora.strftime("%Y-%m")
    for cid, r in registro.items():
        limites = (limites_interactivo or {}).get(cid)
        if r.get("renueva"):
            dia, hh, mm, supuesto = renovacion(r["renueva"])
            renueva_origen = "registro"
        elif ((limites or {}).get("semanal") or {}).get("renueva"):
            try:
                medida = datetime.fromisoformat(limites["semanal"]["renueva"]).astimezone(TZ)
                dia, hh, mm, supuesto = medida.weekday(), medida.hour, medida.minute, False
                renueva_origen = "medido"
            except ValueError:
                dia, hh, mm, supuesto = renovacion("")
                renueva_origen = "supuesto"
        else:
            dia, hh, mm, supuesto = renovacion("")
            renueva_origen = "supuesto"
        semanal = round(float(r.get("precio_mes_usd") or 0) * 12 / 52, 2)
        actual = inicio_ciclo(ahora, dia, hh, mm)
        ciclos = {}
        for evento in eventos:
            m, c, clave, ok, t, *extra = evento
            consultas = extra[0] if extra else 1
            try:
                consultas = max(0, int(consultas))
            except (TypeError, ValueError):
                consultas = 1
            if c != cid:
                continue
            ini = inicio_ciclo(m.astimezone(TZ), dia, hh, mm)
            ci = ciclos.setdefault(ini, {"rutas": {}, "sin_tokens": False})
            ru = ci["rutas"].setdefault(clave, {"consultas": 0, "fallidas": 0, "peso": 0.0})
            if not ok:
                ru["fallidas"] += 1
                continue
            ru["consultas"] += consultas
            w = peso(r.get("motor"), t)
            if w is None:
                ci["sin_tokens"] = True
            else:
                ru["peso"] += w
        ciclos.setdefault(actual, {"rutas": {}, "sin_tokens": False})
        lista = []
        for ini in sorted(ciclos, reverse=True)[:CICLOS_MOSTRADOS]:
            ci = ciclos[ini]
            por_consulta = ci["sin_tokens"]
            total = sum(x["consultas" if por_consulta else "peso"] for x in ci["rutas"].values())
            rutas = {}
            for clave, x in sorted(ci["rutas"].items()):
                parte = (x["consultas"] if por_consulta else x["peso"]) / total if total else 0
                usd = round(semanal * parte, 2)
                rutas[clave] = {"consultas": x["consultas"], "fallidas": x["fallidas"],
                                "peso": round(x["peso"]), "parte": round(parte, 4), "usd": usd}
                agg = por_ruta.setdefault(clave, {"semana_usd": 0.0, "mes_usd": 0.0,
                                                  "consultas_semana": 0, "consultas_mes": 0,
                                                  "cuentas": {}})
                agg["cuentas"][cid] = agg["cuentas"].get(cid, 0) + x["consultas"]
                if ini == actual:
                    agg["semana_usd"] = round(agg["semana_usd"] + usd, 2)
                    agg["consultas_semana"] += x["consultas"]
                if ini.strftime("%Y-%m") == mes_actual:
                    agg["mes_usd"] = round(agg["mes_usd"] + usd, 2)
                    agg["consultas_mes"] += x["consultas"]
            usado = round(sum(v["usd"] for v in rutas.values()), 2)
            lista.append({"inicio": ini.isoformat(timespec="minutes"),
                          "fin": (ini + timedelta(days=7)).isoformat(timespec="minutes"),
                          "actual": ini == actual, "reparto": "consultas" if por_consulta else "tokens",
                          "rutas": rutas, "usd_semana": semanal,
                          "ocioso_usd": round(semanal - usado, 2)})
        cuentas[cid] = {**{k: r.get(k) for k in ("nombre", "motor", "dueno", "precio_mes_usd", "renueva",
                                                  "tope_encargos_semanal", "tope_encargos_5h",
                                                  "quemar_horas", "quemar_tope")},
                        "renueva_supuesto": supuesto, "renueva_origen": renueva_origen,
                        "limites": limites, "usd_semana": semanal,
                        "proxima_renovacion": (actual + timedelta(days=7)).isoformat(timespec="minutes"),
                        "ciclos": lista}
    vencidos = ((limites_interactivo or {}).get("_vencidos") or [])
    desconocidas = {}
    for _momento, cuenta, ruta, ok, _tokens, *extra in eventos:
        if cuenta == "claude_desconocida" and ruta.startswith("pc:") and ok:
            desconocidas[ruta[3:]] = desconocidas.get(ruta[3:], 0) + (extra[0] if extra else 1)
    alcance = ("Incluye bots y sesiones de esta Pi, más los PC que reportaron por Syncthing. "
               "Lo usado desde la web o el teléfono no se puede medir y queda dentro de «ocioso».")
    if vencidos:
        alcance += " Sin datos desde " + ", ".join(vencidos) + "."
    if desconocidas:
        detalle = ", ".join(f"{equipo} reportó {n} mensajes" for equipo, n in sorted(desconocidas.items()))
        alcance += " " + detalle + " de una cuenta Claude que no está en cuentas.toml; no se le asignó costo."
    return {"cuentas": cuentas, "por_ruta": por_ruta,
            "total_mes_usd": sum(float(r.get("precio_mes_usd") or 0) for r in registro.values()),
            "alcance": alcance}


def leer_uso_json():
    try:
        with open(USO_JSON, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def uso_cuentas(uso=None, registro=None, ahora=None):
    uso = leer_uso_json() if uso is None else uso
    ahora = ahora or datetime.now(TZ)
    registro = registro or registro_cuentas()
    limites = limites_de(uso)
    vencidos = [f"{equipo} ({momento})" for equipo, momento in
                (((uso or {}).get("equipos", {}).get("vencidos", {}) or {}).items())]
    limites["_vencidos"] = vencidos
    salida = resumen_cuentas(registro, eventos_de_uso(PERFILES, uso), ahora, limites)
    salida["rendimiento"] = rendimiento(registro, PERFILES, ahora, uso)
    return salida


def limites_de(uso):
    """{cuenta: limites} desde uso.json, donde cada cuenta viene como
    {disponible, por_hora, limites}. Separado para poder probar la forma REAL."""
    candidatos = []
    for cid, c in ((uso or {}).get("cuentas_interactivo") or {}).items():
        if isinstance(c, dict) and c.get("limites"):
            candidatos.append((cid, c["limites"]))
    for reporte in ((uso or {}).get("equipos", {}).get("activos", {}) or {}).values():
        for cid, c in (reporte.get("cuentas") or {}).items():
            if isinstance(c, dict) and c.get("limites"):
                candidatos.append((cid, c["limites"]))
    salida = {}
    for cid, limite in candidatos:
        try:
            momento = datetime.fromisoformat(limite.get("momento") or "")
        except (ValueError, AttributeError):
            continue
        anterior = salida.get(cid)
        try:
            anterior_momento = datetime.fromisoformat((anterior or {}).get("momento") or "")
        except (ValueError, AttributeError):
            anterior_momento = None
        if anterior_momento is None or momento > anterior_momento:
            salida[cid] = limite
    return salida


def props(unidad):
    claves = ["ActiveState", "SubState", "MainPID", "User", "ActiveEnterTimestamp",
              "ReadWritePaths", "ReadOnlyPaths", "InaccessiblePaths",
              "BindPaths", "BindReadOnlyPaths", "DropInPaths"]
    out = {}
    for l in sh(["systemctl", "show", unidad, *[f"-p{c}" for c in claves]]).splitlines():
        k, _, v = l.partition("=")
        out[k] = v
    return out


def deriva():
    """Compara la copia del vault en la Pi con lo desplegado.

    Syncthing sincroniza el vault, no /opt ni /etc: leer el vault y creer que es
    lo que corre ya costo dos confusiones (ver pi5-acceso-remoto-y-runtime).
    Para los TOML ademas compara los VALORES, porque una diferencia de solo
    comentarios no cambia el comportamiento y no merece el mismo color.
    """
    pares = [(f"{VAULT_PI}/{n}", f"{BOT_DIR}/{n}") for n in
             ("botv3.py", "compras.py", "agenda_correo.py", "temporizadores.py")]
    pares += [(f"{VAULT_PI}/perfiles/{p}.toml", f"{BOT_DIR}/perfiles/{p}.toml") for p in PERFILES]
    # El diccionario y el «sobre mi» pueden no existir en ningun lado, y eso no es deriva.
    for p in PERFILES:
        for sub, ext in (("pronunciacion", "toml"), ("sobre", "md")):
            v, d = f"{VAULT_PI}/perfiles/{sub}/{p}.{ext}", f"{BOT_DIR}/perfiles/{sub}/{p}.{ext}"
            if os.path.exists(v) or os.path.exists(d):
                pares.append((v, d))
    pares.append((f"{VAULT_PI}/botv3@.service", f"{UNIDADES}/botv3@.service"))
    for d in glob.glob(f"{VAULT_PI}/botv3@*.service.d/*.conf"):
        rel = os.path.relpath(d, VAULT_PI)
        pares.append((d, f"{UNIDADES}/{rel}"))
    res = []
    for v, d in pares:
        mv, md = md5(v), md5(d)
        item = {"archivo": os.path.relpath(v, VAULT_PI), "desplegado": d,
                "igual": mv is not None and mv == md,
                "falta_vault": mv is None, "falta_desplegado": md is None}
        if not item["igual"] and v.endswith(".toml") and mv and md:
            item["mismos_valores"] = leer_toml(v) == leer_toml(d)
        res.append(item)
    # Drop-ins desplegados sin fuente en el vault: existen y nadie los versiona.
    for d in glob.glob(f"{UNIDADES}/botv3@*.service.d/*.conf"):
        rel = os.path.relpath(d, UNIDADES)
        if not os.path.exists(f"{VAULT_PI}/{rel}"):
            res.append({"archivo": rel, "desplegado": d, "igual": False,
                        "falta_vault": True, "falta_desplegado": False})
    return res


def voces():
    out = []
    for m in sorted(glob.glob(f"{VOCES}/*.onnx")):
        meta = {}
        try:
            with open(m + ".json") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            pass
        cfg = meta.get("audio", {})
        # Multi-hablante (es_ES-sharvard trae M y F): {"M": 0, "F": 1}. El bot
        # todavía no elige hablante y usa siempre el 0.
        out.append({"ruta": m, "nombre": os.path.basename(m)[:-5],
                    "mb": round(os.path.getsize(m) / 1e6),
                    "sample_rate": cfg.get("sample_rate", 22050),
                    "calidad": cfg.get("quality"),
                    "hablantes": meta.get("speaker_id_map") or {}})
    return out


def casa_legado():
    """Memorias de hogar que quedaron en el STATE_DIR viejo de cada perfil.

    El 20-09-2026 `casa-<perfil>.md` se mudo a /opt/nodo/datos/casa/, pero lo ya
    anotado NO se movio: el bot dejo de leerlo y nadie lo noto. Se muestran en la
    tarjeta 🏠 como "por confirmar" para que alguien decida si van a casa.md.
    Lectura sola: el de pilar es de botpilar y 0600, por eso esto va por root.
    """
    out = []
    for p in PERFILES:
        archivo = f"{estado_dir(p)}/casa-{p}.md"
        try:
            with open(archivo, encoding="utf-8") as fh:
                lineas = fh.read().splitlines()
        except OSError:
            continue
        for l in lineas:
            if not l.startswith("-"):
                continue
            texto, _, meta = l[1:].partition("<!--")
            out.append({"perfil": p, "texto": texto.strip(),
                        "meta": meta.replace("-->", "").strip(),
                        "sha": hashlib.sha256(l.strip().encode("utf-8")).hexdigest()[:16],
                        "origen": "legado", "descartable": False})
    return out


def resultados():
    """Resultado de las propuestas ya aplicadas o rechazadas (los escribe aplicar-propuesta)."""
    out = {}
    for r in glob.glob(f"{PROPUESTAS}/*.resultado.json"):
        try:
            with open(r) as fh:
                out[os.path.basename(r)[:-len(".resultado.json")]] = json.load(fh)
        except (OSError, ValueError):
            pass
    return out


# Solo para las pruebas: el entorno ya reducido de un bot que no esta corriendo.
ENTORNO_DE_PRUEBA = {}


def reunir(ahora=None):
    """Todo lo que imprime bots-info, como dict. Separado de main() para que las pruebas
    armen las paginas con la salida REAL, sin sudo (encargo 13)."""
    perfiles = {}
    uso = leer_uso_json()
    limites, registro, ahora = limites_de(uso), registro_cuentas(), ahora or datetime.now(TZ)
    for p in PERFILES:
        cfg = leer_toml(f"{BOT_DIR}/perfiles/{p}.toml") or {}
        unidad = f"botv3@{p}.service"
        pr = props(unidad)
        pid = int(pr.get("MainPID") or 0) or None
        ed = estado_dir(p)
        web = cfg.get("claude_config_web") or f"{ed}/claude-config"
        pron = leer_toml(f"{BOT_DIR}/perfiles/pronunciacion/{p}.toml") or {}
        perfiles[p] = {
            "toml": cfg,
            "pronunciacion": pron.get("palabras", {}),
            "servicio": pr,
            "sonda": [{"etiqueta": e, "ruta": r, "debe": d, "visible": mostrar(pid, r)}
                      for e, r, d in sondas(p, cfg)] + sondas_carpetas(p, cfg, pid),
            "sobre": leer_texto(f"{BOT_DIR}/perfiles/sobre/{p}.md"),
            "uso_hoy": uso_hoy(p),
            "cuentas": {
                "claude": cuenta(f"{ed}/claude-config"),
                "claude_web": cuenta(web),
                "codex": os.path.isdir(f"{ed}/codex-home"),
            },
            "por_cuenta": cuentas_de(p, ENTORNO_DE_PRUEBA.get(p, entorno_del_bot(pid))),
            "lee_cyd": sorted(LEE_CYD.get(p, set())),
        }
        perfiles[p]["recetas"] = recetas_de(p, cfg, perfiles[p]["por_cuenta"], limites,
                                            registro, ahora)
        perfiles[p]["matriz"] = matriz_de(p, cfg, perfiles[p]["por_cuenta"],
                                          limites=limites, registro=registro, ahora=ahora)
    resumen = uso_cuentas(uso or {}, registro, ahora)
    return {
        "momento": datetime.now().astimezone().isoformat(timespec="seconds"),
        "perfiles": perfiles,
        "deriva": deriva(),
        "voces": voces(),
        "resultados": resultados(),
        "casa_legado": casa_legado(),
        "uso_cuentas": resumen,
        # Encargo 13: la lista de cuentas para las tres paginas y quien tiene margen.
        "cuentas": cuentas_publicas(registro),
        "margen": margen_de(registro, limites, ahora, resumen),
        # Nota de Diego del 01-10: la matriz comun, filas = rutas y columnas = asistentes.
        "matriz": matriz_comun(perfiles),
        # Encargo 15: los proveedores gratis, listos o «sin key» por asistente.
        "proveedores": proveedores_gratis(perfiles),
        # Nombre nuevo → viejo (06a), para que la pagina muestre los dos.
        "alias_rutas": recetas.ALIAS_RUTA if recetas else {},
        # Que proveedor puede ir en que ruta, con su motivo (encargo 10).
        "muros": recetas.muros() if recetas and hasattr(recetas, "muros") else None,
        "lee_cyd": {p: sorted(r) for p, r in LEE_CYD.items()},
    }


def main():
    json.dump(reunir(), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    if os.geteuid() != 0:
        sys.exit("bots-info necesita root: sudo /usr/local/bin/bots-info")
    main()
