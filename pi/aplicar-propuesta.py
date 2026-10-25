#!/usr/bin/python3
"""aplicar-propuesta — aplica un cambio de perfil armado en la pagina 🤖 de Cockpit.

Instalado en /usr/local/bin/aplicar-propuesta. Se corre A MANO, por SSH:

    sudo aplicar-propuesta              # lista las propuestas pendientes
    sudo aplicar-propuesta <id>         # muestra el diff y pide confirmar

La pagina SOLO escribe la propuesta (un JSON en ~/.local/share/bots-propuestas/,
como dcifu004). Nunca aplica: mientras sudo no pida contraseña (Hueco 1), el
navegador no puede ser el lugar donde se amplian permisos. Cuando el hueco se
cierre, este script entra a la lista blanca de sudoers y la pagina puede
llamarlo con el modo administrativo de Cockpit, que pide la clave.

TODO LO QUE VIENE DE LA PROPUESTA SE TRATA COMO NO CONFIABLE: lo escribio un
proceso sin privilegios. Se valida contra listas cerradas y el efecto
(restringe / neutro / AMPLIA) lo calcula este script, no lo que diga el JSON.

Cada propuesta arma un PLAN: uno o mas archivos (el TOML del perfil, el
diccionario, el «sobre mi», el drop-in de systemd de las carpetas), cada uno con
su copia canonica en el vault de la Pi y su copia desplegada. En orden: valida ·
comprueba que vault y desplegado digan LO MISMO (si no, hay deriva y aborta) ·
muestra los diffs · respalda · escribe vault y desplegado · daemon-reload si toca
systemd · reinicia el bot · VERIFICA (que este activo y, para carpetas, que el
namespace muestre lo que debe) · si algo falla, REVIERTE TODO el plan junto.
"""
import difflib
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import time
import tomllib
from datetime import datetime

PROPUESTAS = "/home/dcifu004/.local/share/bots-propuestas"
VAULT_BOT = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/botv3"
VAULT_PI = f"{VAULT_BOT}/perfiles"
DESPLEGADO = "/opt/botv3/perfiles"
UNIDADES = "/etc/systemd/system"
VOCES = "/opt/piper/voces"
RESPALDOS = "/opt/nodo/datos/botv3/deploy-backups"
VAULT_PERSONAL = "/opt/nodo/datos/srv/vault_personal"
VAULT_TRABAJO = "/opt/nodo/datos/srv/vault_trabajo"
CARPETAS_DIR = "/opt/nodo/datos/carpetas"
DUENO = "dcifu004"

# Las rutas que existen en botv3.py. Agregar una que no esta aca no se puede ni
# proponiendo: primero tiene que existir en el codigo y en el router de n8n.
# `vision` (06b): existe en el bot pero no en ningun perfil; se agrega con una
# propuesta `agregar_ruta` (AMPLIA). Su cadena de cuentas por defecto la fija el bot.
# `noticias` (07) igual: existe en el bot, en ningun perfil.
RUTAS_CONOCIDAS = {"claude", "web", "gpt", "sql", "ha", "google", "plantas", "codex", "vision",
                   "noticias"}

# Los mismos valores que acepta botv3.py: lo que pasa aca, el bot lo acepta. Si se
# cambian alla, cambiarlos aca (y al reves).
RITMO = {"voz_length_scale": (0.6, 1.6), "voz_pausa_s": (0.0, 1.5)}
MAX_PRONUNCIACION = 300
TONOS = ("neutro", "cercano", "formal")
LARGOS = ("normal", "breve", "detallado")
MODELOS_CLAUDE = ("", "sonnet", "opus", "haiku")
RUTAS_CON_TOPE = ("claude", "codex", "web", "gpt", "vision", "noticias")
MAX_SOBRE = 1500

APLICABLES = {"voz", "voz_ritmo", "pronunciacion", "quitar_ruta", "agregar_ruta",
              "personalidad", "sobre", "modelo_claude", "tope_diario",
              "carpeta_lectura", "quitar_carpeta", "cuentas", "registro_cuentas", "recetas",
              "encargos_config"}
# Tipos que no cambian nada que el bot lea al arrancar: no se reinicia (se cortaria
# una consulta en curso por nada). El texto dice quien lee el archivo.
SIN_REINICIO = {"registro_cuentas": "Sin reinicio: sólo lo lee bots-info.",
                "encargos_config": "Sin reinicio: lo lee cola-run.py al simular y en cada fase de una cola."}
REGISTRO_V, REGISTRO_D = f"{VAULT_BOT}/cuentas.toml", "/opt/botv3/cuentas.toml"
RENUEVA = re.compile(r"(lun|mar|mie|jue|vie|sab|dom) ([01]?\d|2[0-3]):[0-5]\d")

# Encargo 23a: `encargos_config` edita encargos/modelos.toml (niveles, naturalezas, reparto
# y candados). El archivo vive SOLO en el vault: cola-run.py lo lee de ahi, no hay copia
# desplegada.
MODELOS_ENCARGOS = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/modelos.toml"
# El catalogo que Codex baja de su servidor: de ahi salen los modelos de Codex que existen
# y los esfuerzos que acepta cada uno.
CODEX_MODELOS = "/opt/nodo/datos/agentes/codex-home/models_cache.json"
# Los modelos de Claude que estaban en modelos.toml al escribir el encargo (en los niveles y
# en el candado). Uno nuevo se agrega aca, con su prueba, cuando el CLI lo acepte.
CLAUDE_MODELOS = ("claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5")
CLAUDE_ESFUERZOS = ("low", "medium", "high", "xhigh", "max")   # `claude --effort`; Haiku no acepta
ROLES_ENCARGO = ("autor", "rev", "fix")
NOMBRE_MODELO = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}")

# Encargo 15: los demas proveedores gratis (Gemini, OpenRouter, Tavily) NO se escriben
# aca: los suma `cuentas_todas` desde recetas.py.
# Las tres cuentas pagadas (29-09-2026) y Groq, proveedor SIN cuenta pagada (encargo
# 10). Las mismas que CUENTAS_CONOCIDAS en botv3.py: si se agrega una alla, agregarla
# aca (y en bots-info y la pagina).
CUENTAS = {
    "claude_diego": {"motor": "claude", "dueno": "Diego", "nombre": "Claude (Diego)"},
    "claude_cami": {"motor": "claude", "dueno": "Camila", "nombre": "Claude (Cami)"},
    "codex": {"motor": "codex", "dueno": "Diego", "nombre": "Codex"},
    "groq": {"motor": "groq", "dueno": "", "nombre": "Groq"},
}
SIN_CUENTA_PAGADA = {"groq"}
PAGADAS = [c for c in CUENTAS if c not in SIN_CUENTA_PAGADA]
# Las rutas con receta (automatico y umbral). La cadena de cuentas se puede proponer
# para TODAS las que contesta un modelo: esa lista y que proveedor puede ir en cada
# una salen de recetas.py (ver _cargar_recetas), no se repiten aca.
RUTAS_CON_CUENTA = ("claude", "codex", "web", "gpt", "vision", "noticias")
RUTAS_LEEN_ARCHIVOS = ("claude", "codex")
BOT_DIR = "/opt/botv3"


def _cargar_recetas():
    """recetas.py del bot DESPLEGADO (de root), no el del vault, que lo puede escribir
    dcifu004: de ahi salen los muros por ruta, los mismos que aplica el bot. El mismo
    criterio que bots-info."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("recetas", f"{BOT_DIR}/recetas.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except (OSError, ImportError, SyntaxError, AttributeError):
        return None


recetas = _cargar_recetas()


def cuentas_todas():
    """CUENTAS mas los proveedores gratis que declara recetas.py (encargo 15: Gemini,
    OpenRouter y Tavily). Salen de MOTOR_DE_CUENTA y MOTORES_SIN_CUENTA, el mismo lugar
    del que los toma el bot; con un recetas.py anterior al 15 quedan las de siempre."""
    out = dict(CUENTAS)
    gratis = getattr(recetas, "MOTORES_SIN_CUENTA", None) or ()
    for cid, motor in (getattr(recetas, "MOTOR_DE_CUENTA", None) or {}).items():
        if motor in gratis and cid not in out:
            out[cid] = {"motor": motor, "dueno": "", "nombre": recetas.NOMBRE_CUENTA.get(cid, cid)}
    return out


def sin_cuenta_pagada():
    gratis = getattr(recetas, "MOTORES_SIN_CUENTA", None) or ()
    return SIN_CUENTA_PAGADA | {c for c, v in cuentas_todas().items() if v["motor"] in gratis}

# Nombres por funcion (06a): los mismos alias que recetas.ALIAS_RUTA en el bot. Las
# recetas se escriben con el nombre nuevo; el bot normaliza al leer.
ALIAS_RUTA = {"archivos": "claude", "tecnica": "codex", "general": "gpt",
              "casa": "ha", "agenda": "google"}
NOMBRE_NUEVO = {v: k for k, v in ALIAS_RUTA.items()}

# Etiqueta «lee datos de CyD» por ruta (decision 5 de Diego, 29-09-2026): MARCADA A
# MANO, no deducida de `vaults`. `licitaciones` entra ya, aunque la ruta no exista,
# para que nazca marcada. La misma tabla en bots-info.
LEE_CYD = {"jaime": {"archivos", "tecnica", "licitaciones"}}
UMBRAL_MIN, UMBRAL_MAX = 1, 100
BIN = {"claude": "/opt/botv3/bin/claude", "codex": "/opt/botv3/bin/codex"}


def estado_dir(perfil):
    # El mismo que bots-info: Jaime conserva el directorio historico sin sufijo.
    return "/opt/nodo/datos/botv3" if perfil == "jaime" else f"/opt/nodo/datos/botv3-{perfil}"


def dir_cuenta(perfil, cuenta):
    return f"{estado_dir(perfil)}/cuentas/{cuenta}"


def entorno_del_bot(perfil):
    """Si el proceso del bot tiene cada key (GROQ_API_KEY y, desde el 15, las de los
    demas proveedores gratis) y el webhook de n8n, medido en su entorno real y reducido
    aca mismo a "1" o "": el valor no se guarda ni se imprime.
    None = no se pudo medir (el bot no esta corriendo)."""
    pid = subprocess.run(["systemctl", "show", f"botv3@{perfil}.service", "-p", "MainPID",
                          "--value"], capture_output=True, text=True).stdout.strip()
    if not pid.isdigit() or pid == "0":
        return None
    try:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            crudo = fh.read()
    except OSError:
        return None
    claves = getattr(recetas, "CLAVES_DE_ENTORNO", None) or ("GROQ_API_KEY", "BOTV3_N8N_QUERY_URL")
    out = {c: "" for c in claves}
    for par in crudo.split(b"\0"):
        clave, _, valor = par.partition(b"=")
        if clave.decode("ascii", "replace") in out:
            out[clave.decode("ascii")] = "1" if valor.strip() else ""
    return out


def tiene_sesion(perfil, cuenta, ruta=None):
    """Mide si el directorio de la cuenta tiene un login hecho. No lee tokens: para
    Claude, el correo de oauthAccount; para Codex, que exista auth.json. Groq no tiene
    login: esta listo si el bot tiene su key (o, en la general, el webhook de n8n)."""
    if cuenta in sin_cuenta_pagada():
        return falta_al_proveedor(perfil, cuenta, ruta) == ""
    d = dir_cuenta(perfil, cuenta)
    if CUENTAS[cuenta]["motor"] == "codex":
        return os.path.isfile(f"{d}/auth.json")
    try:
        with open(f"{d}/.claude.json") as fh:
            return bool((json.load(fh).get("oauthAccount") or {}).get("emailAddress"))
    except (OSError, ValueError):
        return False


def falta_al_proveedor(perfil, cuenta, ruta):
    """Que le falta a un proveedor gratis para contestar `ruta` en ese bot, o "" si esta
    listo (recetas.falta_para, la misma regla que usa el bot). Sin key cargada un
    proveedor no existe (encargo 15)."""
    if not recetas:
        return "falta recetas.py"
    entorno = entorno_del_bot(perfil)
    if entorno is None:
        return "no se pudo medir el entorno del bot (no esta corriendo)"
    if hasattr(recetas, "falta_para"):
        return recetas.falta_para(ruta, cuenta, entorno)
    return "" if recetas.groq_listo(ruta, entorno) else "sin key o sin el webhook de n8n"


def usuario_de(perfil):
    return subprocess.run(["systemctl", "show", f"botv3@{perfil}.service", "-p", "User",
                           "--value"], capture_output=True, text=True).stdout.strip() or None


def iniciar_sesion(perfil, cuenta):
    """`sudo aplicar-propuesta --login <perfil> <cuenta>`: crea el directorio de la
    cuenta con el dueño y permisos del bot y abre el login COMO el usuario del bot.
    Es lo unico que la pagina no puede hacer: el login es interactivo y lo hace Diego
    (o quien tenga la clave de esa cuenta) una sola vez por par (perfil, cuenta)."""
    if perfil not in perfiles() or cuenta not in PAGADAS:
        salir(f"uso: aplicar-propuesta --login <{'|'.join(perfiles())}> <{'|'.join(PAGADAS)}>")
    usuario = usuario_de(perfil)
    if not usuario:
        salir(f"no pude saber con que usuario corre botv3@{perfil}")
    u = pwd.getpwnam(usuario)
    destino = dir_cuenta(perfil, cuenta)
    if os.path.islink(destino):
        salir(f"{destino} es un symlink (cuenta migrada del esquema viejo): el login ya esta "
              f"hecho en su destino, {os.path.realpath(destino)}")
    # Root cambia dueño y permisos en una carpeta del bot: por fd y sin seguir
    # enlaces (ver _dir_seguro), o un symlink puesto a tiempo le regalaria cualquier
    # archivo del sistema al usuario del bot.
    for d in (os.path.dirname(destino), destino):
        try:
            fd = _dir_seguro(d, crear=True, dueno=u)
        except OSError as e:
            salir(f"no pude preparar {d}: {e}")
        try:
            os.fchown(fd, u.pw_uid, u.pw_gid)
            os.fchmod(fd, 0o700)
        finally:
            os.close(fd)
    motor = CUENTAS[cuenta]["motor"]
    home = f"{estado_dir(perfil)}/runtime-home"
    if motor == "codex":
        cmd = ["env", f"HOME={home}", f"CODEX_HOME={dir_cuenta(perfil, cuenta)}",
               BIN["codex"], "login", "--device-auth"]
        print("Se abre el login de Codex con un codigo para el navegador.")
    else:
        cmd = ["env", f"HOME={home}", f"CLAUDE_CONFIG_DIR={dir_cuenta(perfil, cuenta)}",
               BIN["claude"]]
        print("Se abre Claude: escribe /login, entra con la cuenta de "
              f"{CUENTAS[cuenta]['dueno']} y sal con /exit.")
    subprocess.run(["sudo", "-u", usuario, *cmd])
    print(f"\n{CUENTAS[cuenta]['nombre']} en {perfil}: "
          f"{'✅ con sesion' if tiene_sesion(perfil, cuenta) else '❌ todavia sin sesion'}")


def salir(msg, codigo=1):
    print(msg, file=sys.stderr)
    sys.exit(codigo)


def perfiles():
    return sorted(f[:-5] for f in os.listdir(DESPLEGADO) if f.endswith(".toml"))


def _dir_seguro(carpeta, crear=False, dueno=None):
    """fd de `carpeta` recorriendola desde / con O_NOFOLLOW en CADA componente.

    Este script corre como root y lee y escribe en el vault y en ~/.local/share, que son
    de dcifu004. Con un open() comun, un symlink en el archivo o en CUALQUIER carpeta del
    camino manda la escritura de root a donde quiera dcifu004 (/etc/sudoers.d, por
    ejemplo): cerrado el Hueco 1, eso es escalar a root esperando a que Diego aplique
    una propuesta. Revisar con realpath y abrir despues deja una carrera; recorrer con
    dir_fd no. Encontrado el 27-09-2026 al armar nodo-desplegar (doc 23).
    """
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for parte in [p for p in carpeta.split("/") if p]:
            if parte in (".", ".."):
                raise OSError(f"ruta con {parte!r}: {carpeta}")
            try:
                sig = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not crear:
                    raise
                os.mkdir(parte, 0o755, dir_fd=fd)
                sig = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                if dueno:
                    os.fchown(sig, dueno.pw_uid, dueno.pw_gid)
            os.close(fd)
            fd = sig
        return fd
    except BaseException:
        os.close(fd)
        raise


def _fd_comun(fd, ruta):
    """Un archivo regular con un solo nombre. Si no, se cierra y se aborta: un hard link
    a un archivo de root haria que el O_TRUNC de abajo lo vacie."""
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
        os.close(fd)
        raise OSError(f"{ruta}: no es un archivo comun o tiene hard links; no sigo")
    return fd


def _abrir_seguro(ruta, flags, modo=0o644):
    carpeta, base = os.path.split(ruta)
    dfd = _dir_seguro(carpeta)
    try:
        return _fd_comun(os.open(base, flags | os.O_NOFOLLOW, modo, dir_fd=dfd), ruta)
    finally:
        os.close(dfd)


def leer(ruta):
    with os.fdopen(_abrir_seguro(ruta, os.O_RDONLY), encoding="utf-8") as fh:
        return fh.read()


def leer_o_nada(ruta):
    try:
        return leer(ruta)
    except FileNotFoundError:
        return None


def valores(texto):
    return tomllib.loads(texto or "")


def sin_comentarios(texto):
    return [l.strip() for l in (texto or "").splitlines() if l.strip() and not l.strip().startswith("#")]


def carpeta_segura():
    """La carpeta de propuestas es de un usuario sin privilegios y root escribe ahi.

    Hoy da lo mismo (sudo no pide contraseña), pero el dia que se cierre el Hueco 1
    un symlink en esa carpeta seria la forma de hacer que root escriba donde no
    debe. Por eso: la carpeta no puede ser un symlink, y el archivo se abre con
    O_NOFOLLOW.
    """
    if os.path.islink(PROPUESTAS) or os.path.realpath(PROPUESTAS) != PROPUESTAS:
        salir("la carpeta de propuestas es un symlink; no sigo")


def escribir_resultado(pid, estado, detalle, respaldo=None):
    ruta = os.path.join(PROPUESTAS, f"{pid}.resultado.json")
    fd = _abrir_seguro(ruta, os.O_WRONLY | os.O_CREAT, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.truncate(0)
        json.dump({"estado": estado, "detalle": detalle, "respaldo": respaldo,
                   "momento": datetime.now().astimezone().isoformat(timespec="seconds")},
                  fh, ensure_ascii=False, indent=1)
        u = pwd.getpwnam(DUENO)
        os.fchown(fh.fileno(), u.pw_uid, u.pw_gid)
    subprocess.run(["logger", "-t", "aplicar-propuesta", f"{pid}: {estado} — {detalle}"])


def listar():
    if not os.path.isdir(PROPUESTAS):
        print("No hay propuestas.")
        return
    hechas = {f[:-len(".resultado.json")] for f in os.listdir(PROPUESTAS)
              if f.endswith(".resultado.json")}
    pend = sorted(f[:-5] for f in os.listdir(PROPUESTAS)
                  if f.endswith(".json") and not f.endswith(".resultado.json")
                  and f[:-5] not in hechas)
    if not pend:
        print("No hay propuestas pendientes.")
    for p in pend:
        try:
            d = json.loads(leer(os.path.join(PROPUESTAS, p + ".json")))
            print(f"  {p}   {d.get('perfil')} · {d.get('tipo')} · {d.get('valor')}")
        except (OSError, ValueError):
            print(f"  {p}   (ilegible)")


# --- edicion del TOML por linea ---------------------------------------------------
# Se edita por linea y no se re-serializa: en estos archivos los comentarios son la
# mitad del valor, y tomllib no escribe.

def linea_toml(texto, clave, nueva):
    patron = re.compile(rf"^{clave}\s*=.*$", re.M)
    hallados = patron.findall(texto)
    if len(hallados) != 1:
        salir(f"la clave `{clave}` aparece {len(hallados)} veces en una sola linea; "
              f"editala a mano")
    return patron.sub(nueva.replace("\\", "\\\\"), texto, count=1)


NOTAS = {
    "voz_length_scale": "# Ritmo (pagina 🤖, documento 20): >1 es mas lento, <1 mas rapido.",
    "voz_pausa_s": "# Silencio tras cada oracion, en segundos.",
    "tono": "# Tono de las respuestas (pagina 🤖): neutro, cercano o formal.",
    "largo": "# Largo de las respuestas (pagina 🤖): normal, breve o detallado.",
    "modelo_claude": "# Modelo de Claude (pagina 🤖): vacio = el de la cuenta.",
    "tope_diario": "# Tope diario de consultas por ruta (pagina 🤖). codex topado cae a claude;\n"
                   "# las demas contestan que se llego al tope.",
    "carpetas": "# Carpetas de lectura de vault_personal (pagina 🤖). Las monta systemd con\n"
                "# BindReadOnlyPaths en 30-carpetas.conf; esta lista solo las declara.",
    "cuentas": "# Quien paga cada ruta de agente, en orden: la primera contesta y las demas\n"
               "# son el respaldo (pagina 💳 Cuentas). `gpt` es la general: con `groq`\n"
               "# primero la contesta n8n como siempre; solo admite proveedores gratis.",
    "recetas": "# Receta por ruta (pagina 🤖 → 💳 Cuentas, encargo 06a): `automatico` usa cualquier\n"
               "# cuenta con sesion, la menos cargada primero; los umbrales son la excepcion de\n"
               "# esta ruta al global de cuentas.toml (80 % semanal, 90 % en 5 h).",
}


def poner_clave(texto, clave, linea):
    """Reemplaza `clave = ...`; si no existe, la agrega tras la ultima llave `voz*`
    (o, si no hay, tras la ultima llave de nivel superior) con su comentario."""
    if re.search(rf"^{clave}\s*=", texto, re.M):
        return linea_toml(texto, clave, linea)
    anclas = list(re.finditer(r"^voz\w*\s*=.*$", texto, re.M)) or \
        list(re.finditer(r"^\w+\s*=.*$", texto, re.M))
    if not anclas:
        salir(f"no encontre donde ubicar `{clave}`; editalo a mano")
    fin = anclas[-1].end()
    return texto[:fin] + f"\n\n{NOTAS[clave]}\n{linea}" + texto[fin:]


def lista_toml(xs):
    return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in xs) + "]"


def texto_toml(s):
    return json.dumps(s, ensure_ascii=False)


# --- archivos que no son el perfil -----------------------------------------------

def validar_tabla(valor):
    """Mismas reglas que cargar_pronunciacion() en botv3.py, pero aca se RECHAZA en
    vez de descartar: una propuesta rara se corrige en la pagina, no se aplica a medias."""
    if not isinstance(valor, dict) or len(valor) > MAX_PRONUNCIACION:
        salir(f"el diccionario tiene que ser un objeto de hasta {MAX_PRONUNCIACION} entradas")
    tabla = {}
    for k, v in valor.items():
        if not isinstance(v, str) or not 0 < len(k.strip()) <= 40 or not 0 < len(v.strip()) <= 80 \
                or any(ord(c) < 32 for c in k + v):
            salir(f"entrada invalida en el diccionario: {k!r} = {v!r}")
        tabla[k.strip()] = v.strip()
    return tabla


def texto_pronunciacion(perfil, tabla):
    lineas = [
        f"# Diccionario de pronunciacion del perfil `{perfil}`.",
        "# Lo escribe aplicar-propuesta desde la pagina 🤖 de Cockpit (documento 20);",
        "# editarlo a mano tambien sirve. Se aplica SOLO al texto que va a Piper: el",
        "# chat muestra la palabra bien escrita. Palabras enteras, sin importar mayusculas.",
        "",
        "[palabras]",
    ]
    lineas += [f"{texto_toml(k)} = {texto_toml(v)}"
               for k, v in sorted(tabla.items(), key=lambda kv: kv[0].lower())]
    return "\n".join(lineas) + "\n"


def nombre_carpeta(relativa):
    # El mismo que botv3.nombre_carpeta(): de eso depende que el bot la encuentre.
    return re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.basename(relativa)).strip("-")[:40]


def validar_carpeta(rel):
    """Una subcarpeta de vault_personal que se puede abrir. Devuelve la ruta real."""
    if not isinstance(rel, str) or not rel.strip():
        salir("carpeta vacia")
    rel = rel.strip().strip("/")
    if rel.startswith("vault_personal/"):
        rel = rel[len("vault_personal/"):]
    partes = rel.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in partes):
        salir(f"carpeta invalida: {rel!r}")
    if rel.startswith("90-Referencia/00-MemoriaIA") or any(ord(c) < 32 for c in rel):
        salir("esa carpeta no se abre a ningun bot")
    real = os.path.realpath(os.path.join(VAULT_PERSONAL, rel))
    if not real.startswith(VAULT_PERSONAL + "/") or not os.path.isdir(real):
        salir(f"no existe como carpeta dentro de vault_personal: {rel!r}")
    if not nombre_carpeta(rel):
        salir("la carpeta no deja un nombre usable")
    return rel, real


def ilegibles_para_otros(raiz):
    """Archivos que un usuario ajeno (botpilar) NO podra leer: sin permiso de otros.
    No bloquea —la decision es de quien aplica—, pero se dice, porque el bot los
    veria como inexistentes sin ningun error: el peor modo de falla de un lector."""
    malos = []
    for d, dirs, files in os.walk(raiz):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        if (os.stat(d).st_mode & 0o005) != 0o005:  # entrar Y listar, para otros
            malos.append(d)
        for f in files:
            if not os.stat(os.path.join(d, f)).st_mode & 0o004:
                malos.append(os.path.join(d, f))
    return malos


def texto_dropin(perfil, carpetas):
    lineas = [
        f"# Carpetas de lectura del perfil `{perfil}` — lo GENERA aplicar-propuesta",
        "# (pagina 🤖 de Cockpit, documento 20) y lo reescribe ENTERO en cada cambio:",
        "# no editarlo a mano, cambiar `carpetas` en el perfil con una propuesta.",
        "#",
        "# BindReadOnlyPaths monta la subcarpeta en /opt/nodo/datos/carpetas/<perfil>/,",
        "# FUERA del vault, mientras InaccessiblePaths sigue tapando el vault entero.",
        "# Probado el 24-09-2026: la carpeta se ve, el vault da Permission denied y",
        "# escribir da Read-only file system.",
        "[Service]",
        "BindReadOnlyPaths=",
    ]
    for rel in carpetas:
        lineas.append(f"BindReadOnlyPaths={VAULT_PERSONAL}/{rel}:"
                      f"{CARPETAS_DIR}/{perfil}/{nombre_carpeta(rel)}")
    return "\n".join(lineas) + "\n"


def mismo_objeto(pid, ruta_host, ruta_ns):
    try:
        h, n = os.stat(ruta_host), os.stat(f"/proc/{pid}/root{ruta_ns}")
        return (h.st_dev, h.st_ino) == (n.st_dev, n.st_ino)
    except OSError:
        return False


# --- el plan ------------------------------------------------------------------------

class Archivo:
    """Un archivo del plan: su copia canonica en el vault y la desplegada."""

    def __init__(self, vault, desp, nuevo, toml=True, atomico=False):
        self.vault, self.desp, self.nuevo, self.toml = vault, desp, nuevo, toml
        # `atomico`: el archivo lo lee una cola mientras corre; nunca debe verse vacio ni a medias.
        self.atomico = atomico
        # `desp` None: el archivo vive solo en el vault (modelos.toml de los encargos).
        self.orig_v, self.orig_d = leer_o_nada(vault), leer_o_nada(desp) if desp else None

    def deriva(self):
        if not self.desp:
            return False
        if self.toml:
            return valores(self.orig_v) != valores(self.orig_d)
        return sin_comentarios(self.orig_v) != sin_comentarios(self.orig_d)

    def diff(self):
        nombre = self.desp or self.vault
        return difflib.unified_diff(((self.orig_d if self.desp else self.orig_v) or "").splitlines(True),
                                    (self.nuevo or "").splitlines(True),
                                    fromfile=f"{'desplegado' if self.desp else 'vault'}:{nombre}",
                                    tofile=f"propuesto:{nombre}")

    @staticmethod
    def _poner(ruta, texto, vault, atomico=False):
        # Todo por dir_fd y O_NOFOLLOW: ver _dir_seguro. Ningun componente del camino ni
        # el archivo final puede ser un symlink, o se aborta antes de escribir.
        carpeta, base = os.path.split(ruta)
        if texto is None:
            try:
                dfd = _dir_seguro(carpeta)
            except FileNotFoundError:
                return
            try:
                os.remove(base, dir_fd=dfd)  # borra el nombre mismo, nunca un destino
            except FileNotFoundError:
                pass
            finally:
                os.close(dfd)
            return
        u = pwd.getpwnam(DUENO)
        dfd = _dir_seguro(carpeta, crear=True, dueno=u if vault else None)
        try:
            if vault and atomico and texto is not None:
                # Un lector concurrente (cola-run.py relee modelos.toml antes de cada fase) ve el
                # archivo viejo completo o el nuevo completo, nunca uno truncado: se arma aparte y
                # se publica con rename, copiando dueño y modo del existente.
                try:
                    st = os.stat(base, dir_fd=dfd, follow_symlinks=False)
                    if not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
                        raise OSError(f"{ruta}: no es un archivo comun o tiene hard links; no sigo")
                    uid, gid, modo = st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)
                except FileNotFoundError:
                    uid, gid, modo = u.pw_uid, u.pw_gid, 0o644
                tmp = f".{base}.nuevo"
                try:
                    os.remove(tmp, dir_fd=dfd)
                except FileNotFoundError:
                    pass
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dfd)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        fh.write(texto)
                        fh.flush()
                        os.fchown(fh.fileno(), uid, gid)
                        os.fchmod(fh.fileno(), modo)
                        os.fsync(fh.fileno())
                    os.replace(tmp, base, src_dir_fd=dfd, dst_dir_fd=dfd)
                except BaseException:
                    try:
                        os.remove(tmp, dir_fd=dfd)
                    except FileNotFoundError:
                        pass
                    raise
                return
            if vault:
                # El vault se escribe EN EL LUGAR: conserva dueño e inodo, y Syncthing
                # lo ve como una edicion normal.
                try:
                    os.stat(base, dir_fd=dfd, follow_symlinks=False)
                    nuevo = False
                except FileNotFoundError:
                    nuevo = True
                nombre = base
                fd = os.open(nombre, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o644, dir_fd=dfd)
            else:
                nombre = base + ".nuevo"
                try:
                    os.remove(nombre, dir_fd=dfd)
                except FileNotFoundError:
                    pass
                fd = os.open(nombre, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o644, dir_fd=dfd)
            with os.fdopen(_fd_comun(fd, ruta), "w", encoding="utf-8") as fh:
                fh.truncate(0)  # recien despues de comprobar que es un archivo comun
                fh.write(texto)
                if not vault:
                    os.fchmod(fh.fileno(), 0o644)
                    os.fchown(fh.fileno(), 0, 0)
                elif nuevo:
                    os.fchown(fh.fileno(), u.pw_uid, u.pw_gid)
                    os.fchmod(fh.fileno(), 0o644)
            if not vault:
                os.replace(nombre, base, src_dir_fd=dfd, dst_dir_fd=dfd)
        finally:
            os.close(dfd)

    def aplicar(self):
        self._poner(self.vault, self.nuevo, True, self.atomico)
        if self.desp:
            self._poner(self.desp, self.nuevo, False)

    def revertir(self):
        self._poner(self.vault, self.orig_v, True, self.atomico)
        if self.desp:
            self._poner(self.desp, self.orig_d, False)


def armar_plan(perfil, tipo, valor, motivo=""):
    """Devuelve (archivos, efecto, toca_systemd, verificar, resumen)."""
    if tipo == "encargos_config":
        # No es de ningun perfil: no lee ni exige el TOML de uno.
        return plan_encargos(valor, motivo)
    perfil_v, perfil_d = f"{VAULT_PI}/{perfil}.toml", f"{DESPLEGADO}/{perfil}.toml"
    base = leer_o_nada(perfil_v)
    if base is None or leer_o_nada(perfil_d) is None:
        salir("falta el perfil en el vault o en lo desplegado")
    cfg = valores(base)
    verificar = None
    systemd = False

    def en_perfil(nuevo_texto, esperado):
        r = valores(nuevo_texto)
        if any(r.get(k) != v for k, v in esperado.items()):
            salir("el TOML resultante no quedo como se esperaba; no se aplica nada")
        return Archivo(perfil_v, perfil_d, nuevo_texto)

    if tipo == "voz":
        nombre = os.path.basename(str(valor))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.onnx", nombre) or \
                not os.path.isfile(os.path.join(VOCES, nombre)):
            salir(f"voz inexistente en {VOCES}: {valor!r}")
        destino = os.path.join(VOCES, nombre)
        archivos = [en_perfil(linea_toml(base, "voz", f'voz = "{destino}"'), {"voz": destino})]
        return archivos, "neutro", systemd, verificar, nombre

    if tipo == "voz_ritmo":
        if not isinstance(valor, dict):
            salir("voz_ritmo espera {voz_length_scale, voz_pausa_s}")
        nuevo, esperado = base, {}
        for clave, (lo, hi) in RITMO.items():
            x = valor.get(clave)
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not lo <= x <= hi:
                salir(f"{clave}={x!r} fuera de [{lo}, {hi}]")
            nuevo = poner_clave(nuevo, clave, f"{clave} = {round(float(x), 2)!r}")
            esperado[clave] = round(float(x), 2)
        return [en_perfil(nuevo, esperado)], "neutro", systemd, verificar, "ritmo"

    if tipo == "pronunciacion":
        tabla = validar_tabla(valor)
        a = Archivo(f"{VAULT_PI}/pronunciacion/{perfil}.toml",
                    f"{DESPLEGADO}/pronunciacion/{perfil}.toml", texto_pronunciacion(perfil, tabla))
        if valores(a.nuevo).get("palabras") != tabla:
            salir("el diccionario resultante no quedo como se esperaba")
        return [a], "neutro", systemd, verificar, f"{len(tabla)} palabras"

    if tipo in ("quitar_ruta", "agregar_ruta"):
        if valor not in RUTAS_CONOCIDAS:
            salir(f"ruta desconocida: {valor!r}")
        rutas = list(cfg.get("rutas", []))
        if tipo == "quitar_ruta":
            if valor not in rutas:
                salir(f"`{valor}` no esta en las rutas de {perfil}")
            rutas.remove(valor)
            efecto = "restringe"
        else:
            if valor in rutas:
                salir(f"`{valor}` ya esta en las rutas de {perfil}")
            rutas.append(valor)
            efecto = "AMPLIA"
        a = en_perfil(linea_toml(base, "rutas", f"rutas = {lista_toml(rutas)}"), {"rutas": rutas})
        return [a], efecto, systemd, verificar, valor

    if tipo == "personalidad":
        if not isinstance(valor, dict) or valor.get("tono") not in TONOS \
                or valor.get("largo") not in LARGOS:
            salir(f"personalidad espera tono en {TONOS} y largo en {LARGOS}")
        nuevo = poner_clave(base, "tono", f"tono = {texto_toml(valor['tono'])}")
        nuevo = poner_clave(nuevo, "largo", f"largo = {texto_toml(valor['largo'])}")
        a = en_perfil(nuevo, {"tono": valor["tono"], "largo": valor["largo"]})
        return [a], "neutro", systemd, verificar, f"{valor['tono']} · {valor['largo']}"

    if tipo == "sobre":
        if not isinstance(valor, str) or len(valor) > MAX_SOBRE or \
                any(ord(c) < 32 and c not in "\n\t" for c in valor):
            salir(f"el «sobre mi» tiene que ser texto de hasta {MAX_SOBRE} caracteres")
        texto = valor.strip()
        a = Archivo(f"{VAULT_PI}/sobre/{perfil}.md", f"{DESPLEGADO}/sobre/{perfil}.md",
                    (texto + "\n") if texto else None, toml=False)
        return [a], "neutro", systemd, verificar, f"{len(texto)} caracteres"

    if tipo == "modelo_claude":
        if valor not in MODELOS_CLAUDE:
            salir(f"modelo desconocido: {valor!r} (validos: {MODELOS_CLAUDE})")
        a = en_perfil(poner_clave(base, "modelo_claude", f"modelo_claude = {texto_toml(valor)}"),
                      {"modelo_claude": valor})
        return [a], "neutro", systemd, verificar, valor or "el de la cuenta"

    if tipo == "tope_diario":
        if not isinstance(valor, dict):
            salir("tope_diario espera {ruta: n}")
        topes = {}
        for ruta, n in valor.items():
            if ruta not in RUTAS_CON_TOPE:
                salir(f"no se puede topar la ruta {ruta!r}")
            if n in (0, None):
                continue  # 0 = sin tope
            if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 1000:
                salir(f"tope invalido para {ruta}: {n!r} (1 a 1000, 0 = sin tope)")
            topes[ruta] = n
        linea = "tope_diario = { " + ", ".join(f"{r} = {n}" for r, n in topes.items()) + " }" \
            if topes else "tope_diario = {}"
        a = en_perfil(poner_clave(base, "tope_diario", linea), {"tope_diario": topes})
        return [a], "neutro", systemd, verificar, ", ".join(f"{r} {n}" for r, n in topes.items()) or "sin topes"

    if tipo in ("carpeta_lectura", "quitar_carpeta"):
        if "personal" in cfg.get("vaults", []):
            salir(f"{perfil} ya ve vault_personal entero: una carpeta suelta no aporta nada")
        rel, real = validar_carpeta(valor)
        carpetas = list(cfg.get("carpetas", []))
        if tipo == "carpeta_lectura":
            if rel in carpetas:
                salir(f"{rel} ya esta abierta para {perfil}")
            if nombre_carpeta(rel) in {nombre_carpeta(c) for c in carpetas}:
                salir(f"ya hay otra carpeta que se llama {nombre_carpeta(rel)}")
            carpetas.append(rel)
            efecto = "AMPLIA"
            ilegibles = ilegibles_para_otros(real)
            if ilegibles:
                print(f"⚠️  {len(ilegibles)} archivo(s) o carpeta(s) de ahi NO son legibles para "
                      f"otros usuarios:\n     el bot los vera como inexistentes. Ejemplo: "
                      f"{ilegibles[0]}")
        else:
            if rel not in carpetas:
                salir(f"{rel} no esta abierta para {perfil}")
            carpetas.remove(rel)
            efecto = "restringe"
        perfil_a = en_perfil(poner_clave(base, "carpetas", f"carpetas = {lista_toml(carpetas)}"),
                             {"carpetas": carpetas})
        dropin = Archivo(f"{VAULT_BOT}/botv3@{perfil}.service.d/30-carpetas.conf",
                         f"{UNIDADES}/botv3@{perfil}.service.d/30-carpetas.conf",
                         texto_dropin(perfil, carpetas) if carpetas else None, toml=False)
        systemd = True

        def verificar(pid):
            # Medir, no declarar: cada carpeta abierta tiene que verse DESDE ADENTRO
            # como el mismo objeto que en el host, y los vaults enteros NO.
            for c in carpetas:
                if not mismo_objeto(pid, f"{VAULT_PERSONAL}/{c}",
                                    f"{CARPETAS_DIR}/{perfil}/{nombre_carpeta(c)}"):
                    return False, f"la carpeta {c} no se ve desde el bot"
            if tipo == "quitar_carpeta" and mismo_objeto(
                    pid, real, f"{CARPETAS_DIR}/{perfil}/{nombre_carpeta(rel)}"):
                return False, f"la carpeta {rel} se sigue viendo"
            for v in (VAULT_PERSONAL, VAULT_TRABAJO):
                if mismo_objeto(pid, v, v):
                    return False, f"¡{v} quedo visible entero!"
            return True, "carpetas verificadas desde adentro del servicio"

        return [perfil_a, dropin], efecto, systemd, verificar, rel

    if tipo == "cuentas":
        return plan_cuentas(perfil, cfg, base, valor, en_perfil)

    if tipo == "registro_cuentas":
        return plan_registro(valor)

    if tipo == "recetas":
        return plan_recetas(perfil, cfg, base, valor, en_perfil)

    salir(f"tipo desconocido: {tipo!r}")


def plan_registro(valor):
    """Registro de las 3 cuentas pagadas (cuentas.toml), sin reiniciar el bot."""
    actual = leer_o_nada(REGISTRO_V)
    if actual is None:
        salir(f"falta {REGISTRO_V}: primero desplegar el registro")
    reg = valores(actual)
    # Solo las pagadas: los proveedores gratis no tienen registro que proponer.
    if not isinstance(valor, dict) or set(valor) - set(PAGADAS):
        salir("registro_cuentas espera {cuenta: {precio_mes_usd, renueva, "
              f"umbral_semanal, umbral_5h, tope_encargos_semanal, tope_encargos_5h, "
              f"quemar_horas, quemar_tope, aviso_semanal, aviso_5h}} de {sorted(PAGADAS)}")
    for cid, v in valor.items():
        if not isinstance(v, dict) or set(v) - {"precio_mes_usd", "renueva", "umbral_semanal", "umbral_5h",
                                                "tope_encargos_semanal", "tope_encargos_5h", "quemar_horas",
                                                "quemar_tope", "aviso_semanal", "aviso_5h"}:
            salir(f"{cid}: espera precio_mes_usd, renueva, umbral_semanal, umbral_5h, "
                  f"tope_encargos_semanal, tope_encargos_5h, quemar_horas, quemar_tope, "
                  f"aviso_semanal y/o aviso_5h: {v!r}")
        cambio = {}
        if "precio_mes_usd" in v:
            precio = v["precio_mes_usd"]
            if isinstance(precio, bool) or not isinstance(precio, int) or not 0 <= precio <= 1000:
                salir(f"{cid}: precio_mes_usd tiene que ser un entero de 0 a 1000, no {precio!r}")
            cambio["precio_mes_usd"] = precio
        if "renueva" in v:
            renueva = v["renueva"]
            if not isinstance(renueva, str) or (renueva and not RENUEVA.fullmatch(renueva)):
                salir(f"{cid}: renueva tiene que ser «lun 09:00» (dia sin tilde y hora), no {renueva!r}")
            cambio["renueva"] = renueva
        for clave in ("umbral_semanal", "umbral_5h"):
            if clave not in v:
                continue
            umbral = v[clave]
            if recetas is None or not recetas.umbral_valido(umbral):
                salir(f"{cid}: {clave} tiene que ser un entero de 1 a 100, no {umbral!r}")
            cambio[clave] = umbral
        for clave in ("tope_encargos_semanal", "tope_encargos_5h", "quemar_tope"):
            if clave not in v:
                continue
            tope = v[clave]
            if tope is not None and (recetas is None or not recetas.umbral_valido(tope)):
                salir(f"{cid}: {clave} tiene que ser un entero de 1 a 100 (o null para quitarlo), no {tope!r}")
            cambio[clave] = tope
        if "quemar_horas" in v:
            horas = v["quemar_horas"]
            if horas is not None and (isinstance(horas, bool) or not isinstance(horas, int) or not 0 <= horas <= 48):
                salir(f"{cid}: quemar_horas tiene que ser un entero de 0 a 48 (o null para quitarlo), no {horas!r}")
            cambio["quemar_horas"] = horas
        # Encargo 24: el % en que avisa la regla de aviso previo de avisos.py, por cuenta y por ventana. Misma
        # validacion que el umbral (entero de 1 a 100) y siempre por debajo del tope: un aviso en o sobre el
        # tope llegaria cuando las colas ya esperan. `null` lo quita (sin aviso, como antes del encargo 24).
        for clave in ("aviso_semanal", "aviso_5h"):
            if clave not in v:
                continue
            aviso = v[clave]
            if aviso is not None and (recetas is None or not recetas.umbral_valido(aviso)):
                salir(f"{cid}: {clave} tiene que ser un entero de 1 a 100 (o null para quitarlo), no {aviso!r}")
            cambio[clave] = aviso
        reg.setdefault(cid, {}).update(cambio)
        for clave in [k for k, x in reg[cid].items()
                      if k in ("tope_encargos_semanal", "tope_encargos_5h", "quemar_horas", "quemar_tope",
                               "aviso_semanal", "aviso_5h") and x is None]:
            del reg[cid][clave]
        semanal = reg[cid].get("tope_encargos_semanal", reg[cid].get("umbral_semanal", 75))
        quemar_horas = reg[cid].get("quemar_horas", 0)
        quemar_tope = reg[cid].get("quemar_tope")
        if quemar_horas > 0 and quemar_tope is None:
            salir(f"{cid}: quemar_horas mayor que 0 exige quemar_tope")
        if quemar_tope is not None and quemar_tope < semanal:
            salir(f"{cid}: quemar_tope ({quemar_tope}) no puede bajar el tope_encargos_semanal ({semanal})")
        # Contra el tope de encargos que quedaria (el propio o el umbral del bot si no hay propio).
        for clave, tope_clave, defecto in (("aviso_semanal", "tope_encargos_semanal", 75),
                                           ("aviso_5h", "tope_encargos_5h", 90)):
            respaldo = "umbral_semanal" if clave == "aviso_semanal" else "umbral_5h"
            etiqueta_tope = tope_clave if tope_clave in reg[cid] else respaldo
            tope = reg[cid].get(tope_clave, reg[cid].get(respaldo, defecto))
            if clave in reg[cid] and reg[cid][clave] >= tope:
                salir(f"{cid}: {clave} ({reg[cid][clave]}) tiene que ser menor que {etiqueta_tope} ({tope}): "
                      "el aviso llega antes de que las colas esperen")
    # Se reescribe entero conservando la cabecera de comentarios: la clave `renueva`
    # se repite en cada tabla y la edicion por linea no sabe cual es cual.
    cabecera = actual.split("\n[", 1)[0].rstrip("\n")
    bloques = []
    # Todas las del registro: las pagadas y los proveedores gratis (Groq, y desde el 15
    # Gemini, OpenRouter y Tavily). Reescribir sin ellos borraria sus tablas.
    for cid in list(cuentas_todas()) + [c for c in reg if c not in cuentas_todas()]:
        if cid not in PAGADAS and cid not in reg:
            continue  # un cuentas.toml anterior al encargo 10 o al 15 no trae su tabla
        r = reg.get(cid, {})
        bloques.append(f"[{cid}]\n" + "\n".join(
            f"{k} = {texto_toml(r[k]) if isinstance(r[k], str) else r[k]}"
            for k in ("nombre", "motor", "dueno", "correo", "precio_mes_usd", "renueva",
                      "umbral_semanal", "umbral_5h", "tope_encargos_semanal", "tope_encargos_5h",
                      "quemar_horas", "quemar_tope", "aviso_semanal", "aviso_5h",
                      "busquedas_max_encargo") if k in r))
    nuevo = cabecera + "\n\n" + "\n\n".join(bloques) + "\n"
    if valores(nuevo) != reg:
        salir("el registro resultante no quedo como se esperaba; no se aplica nada")
    resumen = "; ".join(f"{c} " + " ".join(f"{k}={x}" for k, x in v.items())
                         for c, v in valor.items())
    return [Archivo(REGISTRO_V, REGISTRO_D, nuevo)], "neutro", False, None, resumen


# --- encargos/modelos.toml (encargo 23a) --------------------------------------------

def catalogo_modelos(cfg=None):
    """{motor: {modelo: [esfuerzos]}} de los modelos que existen. Claude: la lista cerrada de
    arriba mas los que ya esten en [niveles.claude]. Codex: los de su models_cache.json (todos:
    `gpt-reserve` esta oculto y se usa). `codex` es None si el catalogo no se pudo leer: ahi no
    se acepta ningun cambio de modelo de Codex, en vez de aceptar cualquiera."""
    claude = list(CLAUDE_MODELOS)
    for v in (((cfg or {}).get("niveles") or {}).get("claude") or {}).values():
        m = v.get("modelo") if isinstance(v, dict) else None
        if isinstance(m, str) and NOMBRE_MODELO.fullmatch(m) and m not in claude:
            claude.append(m)
    codex = None
    try:
        modelos = json.loads(leer(CODEX_MODELOS)).get("models")
        codex = {}
        for m in modelos:
            slug = m.get("slug")
            if isinstance(slug, str) and NOMBRE_MODELO.fullmatch(slug):
                codex[slug] = [x["effort"] for x in m.get("supported_reasoning_levels") or []
                               if isinstance(x, dict) and isinstance(x.get("effort"), str)
                               and re.fullmatch(r"[a-z]{1,12}", x["effort"])]
    except (OSError, ValueError, AttributeError, TypeError):
        codex = None
    return {"claude": {m: ([] if "haiku" in m else list(CLAUDE_ESFUERZOS)) for m in claude},
            "codex": codex or None}


def con_candado(cfg, modelo):
    """Lo mismo que mira cola-run.py: por nombre exacto o por trozo."""
    aut = cfg.get("autorizacion") or {}
    m = modelo.lower()
    return m in {str(x).lower() for x in aut.get("modelos") or []} or \
        any(str(p).lower() in m for p in aut.get("patrones") or [])


def cambios_encargos(cfg, valor, catalogo):
    """Valida la propuesta ENTERA contra lo que hay en modelos.toml y devuelve
    (cfg nuevo, [cambios «clave: antes → despues»], avisos). No escribe nada. Algo que no
    calza termina con salir(): no se aplica una parte. La usa tambien `cola-run.py
    --con-cambios`, para que la pagina simule exactamente lo que despues se aceptaria."""
    if not isinstance(valor, dict) or set(valor) - {"naturaleza", "niveles", "reparto", "autorizacion", "factor_modelo"}:
        salir("encargos_config espera {naturaleza, niveles, reparto, autorizacion, factor_modelo}: "
              f"{sorted(valor) if isinstance(valor, dict) else valor!r}")
    for parte in valor:
        if not isinstance(valor[parte], dict):
            salir(f"encargos_config.{parte} tiene que ser un objeto")
    nuevo = json.loads(json.dumps(cfg))   # copia honda: son solo tablas, textos, listas y numeros
    cambios, avisos = [], []
    niveles = nuevo.get("niveles") or {}
    # Un nivel sirve en una naturaleza si lo tienen TODOS los motores: el autor puede ser
    # cualquiera de ellos.
    comunes = [n for n in next(iter(niveles.values()), {}) if all(n in t for t in niveles.values())]

    for motor, tabla in (valor.get("niveles") or {}).items():
        if motor not in niveles or not isinstance(tabla, dict):
            salir(f"niveles.{motor!s}: motor desconocido ({', '.join(niveles)})")
        modelos = catalogo.get(motor)
        for nivel, v in tabla.items():
            if nivel not in niveles[motor]:
                salir(f"niveles.{motor}.{nivel!s}: ese nivel no existe ({', '.join(niveles[motor])})")
            if not isinstance(v, dict) or set(v) != {"modelo", "esfuerzo"} \
                    or not all(isinstance(x, str) for x in v.values()):
                salir(f"niveles.{motor}.{nivel} espera {{modelo, esfuerzo}}: {v!r}")
            antes = niveles[motor][nivel]
            if v == {"modelo": antes.get("modelo"), "esfuerzo": antes.get("esfuerzo", "")}:
                continue
            if modelos is None:
                salir(f"niveles.{motor}.{nivel}: no pude leer el catalogo de modelos de {motor} "
                      f"({CODEX_MODELOS}); sin el no se cambia ningun modelo")
            if v["modelo"] not in modelos:
                salir(f"niveles.{motor}.{nivel}: el modelo {v['modelo']!r} no existe "
                      f"(existen: {', '.join(modelos)})")
            if v["esfuerzo"] and v["esfuerzo"] not in modelos[v["modelo"]]:
                salir(f"niveles.{motor}.{nivel}: {v['modelo']} no acepta el esfuerzo {v['esfuerzo']!r} "
                      f"(acepta: {', '.join(modelos[v['modelo']]) or 'ninguno, va vacio'})")
            cambios.append(f"niveles.{motor}.{nivel}: {antes.get('modelo')} {antes.get('esfuerzo', '')}".rstrip()
                           + f" → {v['modelo']} {v['esfuerzo']}".rstrip())
            niveles[motor][nivel] = dict(antes, **v)
            if con_candado(nuevo, v["modelo"]):
                avisos.append(f"🔒 niveles.{motor}.{nivel} pasa a {v['modelo']}, que tiene candado: cada cola "
                              "que lo use va a pedir la autorizacion por Telegram.")

    naturalezas = nuevo.get("naturaleza") or {}
    for nat, roles in (valor.get("naturaleza") or {}).items():
        if nat not in naturalezas or not isinstance(roles, dict):
            salir(f"naturaleza.{nat!s}: no existe ({', '.join(naturalezas)})")
        antes = dict(naturalezas[nat])
        for rol, nivel in roles.items():
            if rol not in ROLES_ENCARGO or rol not in naturalezas[nat]:
                salir(f"naturaleza.{nat}.{rol!s}: el rol tiene que ser {', '.join(ROLES_ENCARGO)}")
            if not isinstance(nivel, str) or nivel not in comunes:
                salir(f"naturaleza.{nat}.{rol}: el nivel {nivel!r} no existe ({', '.join(comunes)})")
            if nivel != naturalezas[nat][rol]:
                cambios.append(f"naturaleza.{nat}.{rol}: {naturalezas[nat][rol]} → {nivel}")
                naturalezas[nat][rol] = nivel
        # El criterio del doc 27 (7.2), como aviso y no como muro: es una hipotesis que el
        # usuario puede querer probar. Solo si esta propuesta toca esa naturaleza.
        orden = {n: i for i, n in enumerate(comunes)}
        if naturalezas[nat] != antes and orden.get(naturalezas[nat].get("rev"), 0) > orden.get(naturalezas[nat].get("autor"), 0):
            avisos.append(f"⚠️  naturaleza.{nat}: la revision ({naturalezas[nat]['rev']}) queda por "
                          f"debajo del autor ({naturalezas[nat]['autor']}).")

    reparto = nuevo.get("reparto") or {}
    for nat, r in (valor.get("reparto") or {}).items():
        if nat not in naturalezas:
            salir(f"reparto.{nat!s}: esa naturaleza no existe ({', '.join(naturalezas)})")
        if nat not in reparto:
            salir(f"reparto.{nat}: modelos.toml no tiene la tabla [reparto.{nat}]; se agrega a mano")
        if not isinstance(r, dict) or not r or set(r) - {"autor", "revisor"}:
            salir(f"reparto.{nat} espera {{autor, revisor}}: {r!r}")
        for rol, cid in r.items():
            if not isinstance(cid, str) or cid not in PAGADAS:
                salir(f"reparto.{nat}.{rol}: {cid!r} no es una cuenta ({', '.join(PAGADAS)})")
            if cid != reparto[nat].get(rol):
                cambios.append(f"reparto.{nat}.{rol}: {reparto[nat].get(rol)} → {cid}")
                reparto[nat][rol] = cid
        if reparto[nat].get("autor") == reparto[nat].get("revisor"):
            salir(f"reparto.{nat}: autor y revisor serian la misma cuenta ({reparto[nat]['autor']}). "
                  "El reparto por defecto nunca lo acepta; la excepcion va en el manifiesto, con "
                  "`autorrevision`.")

    if "autorizacion" in valor:
        aut = valor["autorizacion"]
        if set(aut) != {"modelos"}:
            salir("autorizacion: desde la pagina solo se agregan modelos a la lista (`modelos`); "
                  "los patrones y la espera se editan a mano")
        pedida, actual = aut["modelos"], list((nuevo.get("autorizacion") or {}).get("modelos") or [])
        if not isinstance(pedida, list) or len(set(map(str, pedida))) != len(pedida) or \
                any(not isinstance(m, str) or not NOMBRE_MODELO.fullmatch(m) for m in pedida):
            salir(f"autorizacion.modelos tiene que ser una lista de nombres de modelo sin repetir: {pedida!r}")
        faltan = [m for m in actual if m not in pedida]
        if faltan:
            salir(f"autorizacion.modelos: falta {', '.join(faltan)}. Quitar un candado no se hace "
                  "desde la pagina: se edita modelos.toml a mano y se anota en su registro.")
        agregados = [m for m in pedida if m not in actual]
        if len(pedida) > 40:
            salir("autorizacion.modelos: mas de 40 modelos con candado")
        conocidos = {m for t in catalogo.values() for m in (t or {})}
        for m in agregados:
            cambios.append(f"candado: + {m}")
            if m not in conocidos:
                avisos.append(f"ℹ️  {m} no esta entre los modelos conocidos: el candado queda puesto igual.")
        nuevo["autorizacion"]["modelos"] = actual + agregados

        # Un candado nuevo sobre un modelo que ya esta en un nivel: desde ahora esas colas piden permiso.
        for motor, tabla in niveles.items():
            for nivel, v in tabla.items():
                if v.get("modelo") in agregados:
                    avisos.append(f"🔒 niveles.{motor}.{nivel} usa {v['modelo']}: con el candado nuevo, cada "
                                  "cola que lo use va a pedir la autorizacion por Telegram.")
    if "factor_modelo" in valor:
        # Encargo 24: cuanta cuota gasta cada modelo relativo al de referencia de su motor (Claude Opus 5.5
        # = 1,0). Lo usa pronostico() cuando no hay 3 filas del mismo modelo. Solo modelos que existen y
        # un numero positivo de verdad: un 0 haria pronosticar que una fase no cuesta nada.
        pedidos = valor["factor_modelo"]
        conocidos = {m for t in catalogo.values() for m in (t or {})}
        if not pedidos:
            salir("factor_modelo no trae ningun modelo")
        tabla = nuevo.setdefault("factor_modelo", {})
        for modelo, k in pedidos.items():
            if not isinstance(modelo, str) or modelo not in conocidos:
                salir(f"factor_modelo.{modelo!s}: el modelo no existe (existen: {', '.join(sorted(conocidos))})")
            if isinstance(k, bool) or not isinstance(k, (int, float)) or not k == k or not 0 < k <= 100:
                salir(f"factor_modelo.{modelo}: el factor tiene que ser un numero mayor que 0 y hasta 100 "
                      f"(nunca 0), no {k!r}")
            if tabla.get(modelo) != k:
                cambios.append(f"factor_modelo.{modelo}: {tabla.get(modelo, 'sin factor')} → {k}")
                tabla[modelo] = k
    return nuevo, cambios, avisos


def _agregar_en_tabla(lineas, seccion, nueva):
    """Una linea nueva al final de la tabla [seccion] (despues de su ultima clave)."""
    dentro, ultima = None, None
    for i, linea in enumerate(lineas):
        cabeza = re.match(r"\[([^\]]+)\]", linea)
        if cabeza:
            dentro = cabeza.group(1).strip()
        elif dentro == seccion and re.match(r"\s*[\w\"]", linea) and "=" in linea.split("#")[0]:
            ultima = i
    if ultima is None:
        salir(f"modelos.toml no trae la tabla [{seccion}]; agregala a mano y anotalo en su registro")
    lineas.insert(ultima + 1, nueva)


def _editar_linea(lineas, seccion, clave, cambiar):
    """Reemplazo puntual: la UNICA linea `clave = ...` de la tabla [seccion]."""
    dentro, hallados = None, []
    for i, linea in enumerate(lineas):
        cabeza = re.match(r"\[([^\]]+)\]", linea)
        if cabeza:
            dentro = cabeza.group(1).strip()
        elif dentro == seccion and re.match(rf'\s*"?{re.escape(clave)}"?\s*=', linea):
            hallados.append(i)
    if len(hallados) != 1:
        salir(f"`{clave}` aparece {len(hallados)} veces en [{seccion}] de modelos.toml; editalo a mano")
    nueva = cambiar(lineas[hallados[0]])
    if nueva is None:
        salir(f"no entendi la linea `{clave}` de [{seccion}] en modelos.toml; editalo a mano")
    lineas[hallados[0]] = nueva


def _poner_texto(clave, texto):
    """`clave = "x"` → `clave = "texto"`, sin tocar la alineacion ni el comentario."""
    def cambiar(linea):
        nueva, n = re.subn(rf'^(\s*{re.escape(clave)}\s*=\s*)"[^"]*"',
                           lambda m: m.group(1) + texto_toml(texto), linea)
        return nueva if n == 1 else None
    return cambiar


def texto_encargos(actual, cfg, nuevo, linea_registro):
    """modelos.toml con los valores de `nuevo`, editado linea por linea: los comentarios, el
    orden y el registro de cambios quedan como estaban. Sin cambios devuelve `actual` igual."""
    lineas = actual.split("\n")
    for nat, roles in (nuevo.get("naturaleza") or {}).items():
        for rol, nivel in roles.items():
            if nivel != cfg["naturaleza"][nat][rol]:
                _editar_linea(lineas, f"naturaleza.{nat}", rol, _poner_texto(rol, nivel))
    for nat, r in (nuevo.get("reparto") or {}).items():
        for rol, cid in r.items():
            if cid != cfg["reparto"][nat].get(rol):
                _editar_linea(lineas, f"reparto.{nat}", rol, _poner_texto(rol, cid))
    for motor, tabla in (nuevo.get("niveles") or {}).items():
        for nivel, v in tabla.items():
            antes = cfg["niveles"][motor][nivel]
            if v == antes:
                continue

            def cambiar(linea, v=v, antes=antes):
                for campo in ("modelo", "esfuerzo"):
                    linea, n = re.subn(rf'(\b{campo}\s*=\s*)"[^"]*"',
                                       lambda m: m.group(1) + texto_toml(v[campo]), linea)
                    if n != 1:
                        return None
                # El comentario de la linea describia al modelo anterior («el default de
                # hoy»): con otro modelo quedaria mintiendo. El cambio queda en el registro.
                return re.sub(r"(\})\s*#.*$", r"\1", linea) if v["modelo"] != antes.get("modelo") else linea
            _editar_linea(lineas, f"niveles.{motor}", nivel, cambiar)
    for modelo, k in (nuevo.get("factor_modelo") or {}).items():
        antes = (cfg.get("factor_modelo") or {}).get(modelo)
        if k == antes:
            continue
        valor = repr(float(k))
        if antes is None:
            _agregar_en_tabla(lineas, "factor_modelo", f'"{modelo}" = {valor}')
        else:
            def cambiar(linea, valor=valor):
                nueva, n = re.subn(r"^(\s*\"?[^=\s\"]+\"?\s*=\s*)[-+0-9.eE]+", lambda m: m.group(1) + valor, linea)
                return nueva if n == 1 else None
            _editar_linea(lineas, "factor_modelo", modelo, cambiar)
    lista = (nuevo.get("autorizacion") or {}).get("modelos")
    if lista != (cfg.get("autorizacion") or {}).get("modelos"):
        def cambiar(linea):
            nueva, n = re.subn(r"^(\s*modelos\s*=\s*)\[[^\]]*\]", lambda m: m.group(1) + lista_toml(lista), linea)
            return nueva if n == 1 else None
        _editar_linea(lineas, "autorizacion", "modelos", cambiar)
    if linea_registro:
        # El registro es el ultimo bloque del archivo, todo comentarios: la linea nueva va al final.
        titulos = [i for i, l in enumerate(lineas) if l.startswith("# Registro de cambios")]
        if len(titulos) != 1 or lineas[-1] != "" or \
                any(l and not l.startswith("#") for l in lineas[titulos[0]:]):
            salir("no encontre el «Registro de cambios» al final de modelos.toml; editalo a mano")
        lineas.insert(len(lineas) - 1, linea_registro)
    return "\n".join(lineas)


def plan_encargos(valor, motivo=""):
    """Reparto, niveles, naturalezas y candados de los encargos (encargos/modelos.toml). No
    reinicia nada y no tiene copia desplegada: cola-run.py lee el archivo del vault."""
    actual = leer_o_nada(MODELOS_ENCARGOS)
    if actual is None:
        salir(f"falta {MODELOS_ENCARGOS}")
    try:
        cfg = valores(actual)
    except tomllib.TOMLDecodeError as e:
        salir(f"modelos.toml no se puede leer ({e}); arreglalo antes de proponer")
    for tabla in ("niveles", "naturaleza", "autorizacion"):
        if not isinstance(cfg.get(tabla), dict):
            salir(f"modelos.toml no trae [{tabla}]; no es el archivo que conozco")
    nuevo, cambios, avisos = cambios_encargos(cfg, valor, catalogo_modelos(cfg))
    if not cambios:
        salir("no cambia nada")
    # El motivo viene de la propuesta y termina en un comentario del TOML: una sola linea
    # sin caracteres de control, o un salto de linea escribiria claves nuevas.
    motivo = motivo if isinstance(motivo, str) else ""
    if len(motivo) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in motivo):
        salir("el motivo tiene que ser una sola linea de hasta 200 caracteres")
    registro = (f"# {datetime.now():%d-%m-%Y} · {'; '.join(cambios)} · "
                f"{motivo.strip() or 'sin motivo escrito'} (propuesta desde el panel)")
    texto = texto_encargos(actual, cfg, nuevo, registro)
    comentarios = lambda t: [l for l in t.split("\n") if l.startswith("#")]
    if valores(texto) != nuevo or comentarios(texto) != comentarios(actual) + [registro]:
        salir("modelos.toml no quedo como se esperaba; no se aplica nada")
    for a in avisos:
        print(a)
    efecto = "restringe" if all(c.startswith("candado: + ") for c in cambios) else "neutro"
    return [Archivo(MODELOS_ENCARGOS, None, texto, atomico=True)], efecto, False, None, "; ".join(cambios)


def plan_cuentas(perfil, cfg, base, valor, en_perfil):
    """El orden de cuentas de cada ruta de agente. Cambia QUIEN PAGA y en que
    historial queda la conversacion, no lo que la ruta puede leer: eso lo siguen
    decidiendo `vaults`, `drive` y el namespace de systemd."""
    if not isinstance(cfg.get("cuentas"), dict):
        salir("el perfil todavia no tiene `cuentas`: primero la migracion del documento 20")
    if recetas is None or not hasattr(recetas, "problema_de_cadena"):
        salir(f"falta {BOT_DIR}/recetas.py con los muros por ruta (encargo 10): sin esa tabla "
              "no se puede saber que cuenta puede ir en que ruta. Primero desplegarlo.")
    if not isinstance(valor, dict) or not valor:
        salir("cuentas espera {ruta: [cuenta, ...]}")
    # Los dos nombres de cada ruta valen (`archivos` y `claude`); adentro, el interno.
    antes = {ruta_interna(r): v for r, v in cfg["cuentas"].items()}
    pedido = {}
    for r, ids in valor.items():
        if ruta_interna(r) in pedido:
            salir(f"cuentas trae dos veces la ruta {r!r}")
        pedido[ruta_interna(r)] = ids
    rutas_perfil = {ruta_interna(r) for r in cfg.get("rutas", [])}
    for ruta, ids in pedido.items():
        nombre = recetas.ruta_nombre(ruta)
        fija = (recetas.muros().get("rutas", {}).get(ruta) or {}).get("fija")
        if fija:
            salir(f"cuentas.{nombre}: es fija ({fija}); no tiene cuentas que elegir")
        if ruta in recetas.RUTAS_FIJAS:
            salir(f"cuentas.{nombre}: es una herramienta fija ({recetas.RUTAS_FIJAS[ruta]}); "
                  "no tiene cuentas que elegir")
        if ruta not in recetas.RUTAS_CON_CUENTA:
            salir(f"rutas sin cuenta: {sorted(set(pedido) - set(recetas.RUTAS_CON_CUENTA))}")
        if ruta not in rutas_perfil:
            salir(f"cuentas.{nombre}: la ruta no esta en las rutas de {perfil}")
        if isinstance(ids, list) and any(not isinstance(c, str) or c not in cuentas_todas() for c in ids):
            salir(f"cuentas.{nombre} tiene que ser una lista sin repetidos de {sorted(cuentas_todas())}: {ids!r}")
        # El muro: la misma tabla que aplica el bot. Una celda prohibida se rechaza
        # entera, no se descarta en silencio: la propuesta se corrige en la pagina.
        problema = recetas.problema_de_cadena(ruta, ids)
        if problema:
            salir(f"cuentas.{nombre}: {problema}")
    nuevo = {}
    for ruta in recetas.RUTAS_CON_CUENTA:
        if ruta in pedido:
            nuevo[ruta] = list(pedido[ruta])
        elif ruta in antes:
            nuevo[ruta] = list(antes[ruta])
    if nuevo == antes:
        salir("no cambia nada")

    persona = cfg.get("persona", "")
    avisos, amplia = [], False
    # Desde aca, con los proveedores gratis del 15 incluidos (tapan a las de arriba).
    CUENTAS, SIN_CUENTA_PAGADA = cuentas_todas(), sin_cuenta_pagada()
    for ruta, ids in nuevo.items():
        # Contra lo que la ruta usa HOY: su cadena declarada o, si el perfil no la
        # declara (general, vision, noticias), la de por defecto del bot.
        viejas = set(recetas.cadena_efectiva(ruta, antes)[0])
        agregadas = [c for c in ids if c not in viejas]
        if agregadas:
            amplia = True
        for c in agregadas:
            dueno = CUENTAS[c]["dueno"]
            if c in SIN_CUENTA_PAGADA:
                # 15: sin key cargada un proveedor no existe y no entra en ninguna cadena.
                falta = falta_al_proveedor(perfil, c, ruta)
                if falta:
                    cargar = (f" Primero: {recetas.linea_para_cargar(c, perfil)} y reiniciar el bot."
                              if hasattr(recetas, "linea_para_cargar") and "key" in falta else "")
                    salir(f"cuentas.{recetas.ruta_nombre(ruta)}: {CUENTAS[c]['nombre']} no esta listo en "
                          f"{perfil} ({falta}): no puede entrar en la cadena.{cargar}")
                aviso = recetas.AVISOS.get((ruta, CUENTAS[c]["motor"]), "")
                avisos.append(f"`{recetas.ruta_nombre(ruta)}` pasa a poder salir a {CUENTAS[c]['nombre']}, "
                              "una API externa sin cuenta pagada"
                              + (f" ({aviso})." if aviso else "."))
                continue
            if dueno != persona:
                avisos.append(f"`{ruta}` pasa a poder gastar {CUENTAS[c]['nombre']}, que no es la "
                              f"cuenta propia del perfil.")
            if ruta in RUTAS_LEEN_ARCHIVOS and dueno != "Diego" and \
                    "trabajo" in cfg.get("vaults", []):
                avisos.append(f"⚠️  `{ruta}` LEE vault_trabajo: fragmentos de CyD quedarian en el "
                              f"historial de {CUENTAS[c]['nombre']}. La autorizacion del documento 11 "
                              "nombra proveedores (Claude, Codex, OpenAI), no cuentas: decidilo a "
                              "proposito.")
        # Medir, no declarar: una cuenta sin login falla en cada consulta y cae a la
        # siguiente pagando el tiempo. Si ninguna tiene sesion, la ruta queda muda.
        sin = [c for c in ids if not tiene_sesion(perfil, c, ruta)]
        if len(sin) == len(ids):
            salir(f"ninguna cuenta de `{ruta}` tiene sesion en {perfil}. Primero:\n"
                  + "\n".join(f"    sudo aplicar-propuesta --login {perfil} {c}"
                              if c not in SIN_CUENTA_PAGADA else
                              f"    {CUENTAS[c]['nombre']}: {falta_al_proveedor(perfil, c, ruta)}"
                              for c in ids))
        if ids[0] in sin and ids[0] in SIN_CUENTA_PAGADA:
            avisos.append(f"`{ruta}`: {CUENTAS[ids[0]]['nombre']} va primero pero no esta listo "
                          f"({falta_al_proveedor(perfil, ids[0], ruta)}): contestara el respaldo.")
        elif ids[0] in sin:
            avisos.append(f"`{ruta}`: la primera cuenta ({ids[0]}) no tiene sesion; cada consulta "
                          f"fallara ahi antes de caer al respaldo. "
                          f"`sudo aplicar-propuesta --login {perfil} {ids[0]}`")
        elif sin:
            avisos.append(f"`{ruta}`: {', '.join(sin)} de respaldo sin sesion — el respaldo no "
                          f"respalda nada hasta hacer el --login.")
    if "gpt" in nuevo and "gpt" not in antes:
        avisos.append("`general` queda declarada en `cuentas`: solo proveedores gratis. Con Groq "
                      "primero la sigue contestando n8n, como hoy; los demas son el respaldo, que "
                      "llama el bot si n8n o Groq fallan, y cada intento se anota en el libro.")
    for a in avisos:
        print(a)
    # Sin cuentas nuevas: sacar alguna restringe; sólo reordenar es neutro.
    efecto = "AMPLIA" if amplia else (
        "restringe" if any(set(nuevo[r]) != set(recetas.cadena_efectiva(r, antes)[0])
                           for r in nuevo) else "neutro")
    linea = "cuentas = { " + ", ".join(f"{r} = {lista_toml(ids)}" for r, ids in nuevo.items()) + " }"
    a = en_perfil(poner_clave(base, "cuentas", linea), {"cuentas": nuevo})
    resumen = "; ".join(f"{r} {' → '.join(ids)}" for r, ids in nuevo.items())
    return [a], efecto, False, None, resumen


def ruta_interna(nombre):
    n = str(nombre or "").strip().lower()
    return ALIAS_RUTA.get(n, n)


def plan_recetas(perfil, cfg, base, valor, en_perfil):
    """Receta por ruta de agente: `automatico` y la excepcion de umbral (06a). Se
    valida igual que `cuentas`: listas cerradas, sesion medida y AMPLIA si la ruta
    pasa a poder gastar una cuenta que hoy no esta en su cadena. Que Claude (Cami)
    entre a una ruta que lee datos de CyD NO amplia por eso: lo decidio Diego el
    29-09-2026 y queda como aviso informativo."""
    cadenas = {ruta_interna(r): ids for r, ids in (cfg.get("cuentas") or {}).items()} \
        if isinstance(cfg.get("cuentas"), dict) else None
    if cadenas is None:
        salir("el perfil todavia no tiene `cuentas`: primero la migracion del documento 20")
    if not isinstance(valor, dict) or not valor:
        salir("recetas espera {ruta: {automatico, umbral_semanal, umbral_5h}}")
    rutas_perfil = {ruta_interna(r) for r in cfg.get("rutas", [])}
    crudo = cfg.get("recetas") if isinstance(cfg.get("recetas"), dict) else {}
    antes = {NOMBRE_NUEVO.get(ruta_interna(r), ruta_interna(r)): v for r, v in crudo.items()}
    nuevo = {k: dict(v) for k, v in antes.items()}
    for nombre, r in valor.items():
        interna = ruta_interna(nombre)
        if interna not in RUTAS_CON_CUENTA:
            salir(f"recetas: {nombre!r} no es una ruta con cuentas "
                  f"({', '.join(NOMBRE_NUEVO.get(x, x) for x in RUTAS_CON_CUENTA)})")
        if interna not in rutas_perfil:
            salir(f"recetas: `{nombre}` no esta en las rutas de {perfil}")
        if not isinstance(r, dict) or set(r) - {"automatico", "umbral_semanal", "umbral_5h"} \
                or not isinstance(r.get("automatico"), bool):
            salir(f"recetas.{nombre} espera {{automatico: true|false, umbral_semanal, umbral_5h}}: {r!r}")
        limpia = {"automatico": r["automatico"]}
        for k in ("umbral_semanal", "umbral_5h"):
            x = r.get(k)
            if x is None:
                continue  # sin excepcion: rige el global de cuentas.toml
            if isinstance(x, bool) or not isinstance(x, int) or not UMBRAL_MIN <= x <= UMBRAL_MAX:
                salir(f"recetas.{nombre}.{k} tiene que ser un entero de {UMBRAL_MIN} a {UMBRAL_MAX}: {x!r}")
            limpia[k] = x
        clave = NOMBRE_NUEVO.get(interna, interna)
        if limpia == {"automatico": False}:
            nuevo.pop(clave, None)  # igual a no tener receta: no se escribe
        else:
            nuevo[clave] = limpia
    if nuevo == antes:
        salir("no cambia nada")

    persona, avisos, amplia, restringe = cfg.get("persona", ""), [], False, False
    # Solo las pagadas: el automatico nunca suma a Groq (recetas.cuentas_del_automatico).
    con_sesion = [c for c in PAGADAS if tiene_sesion(perfil, c)]
    for clave in sorted(set(antes) | set(nuevo)):
        interna = ruta_interna(clave)
        era = bool((antes.get(clave) or {}).get("automatico"))
        sera = bool((nuevo.get(clave) or {}).get("automatico"))
        if era and not sera:
            restringe = True
        if not sera or era:
            continue
        # Medir, no declarar: el automatico sin ninguna cuenta con sesion deja la ruta
        # con la cadena de siempre, pero proponerlo asi es un error de la pagina.
        if not con_sesion:
            salir(f"ninguna cuenta tiene sesion en {perfil}: `{clave}` automatico no tendria a quien usar")
        extra = [c for c in con_sesion if c not in cadenas.get(interna, [])]
        if extra:
            amplia = True
        for c in extra:
            avisos.append(f"`{clave}` en automatico pasa a poder gastar {CUENTAS[c]['nombre']}, "
                          "que no esta en su cadena de cuentas.")
            if CUENTAS[c]["dueno"] != persona:
                avisos.append(f"`{clave}`: {CUENTAS[c]['nombre']} no es la cuenta propia del perfil.")
            if clave in LEE_CYD.get(perfil, set()) and CUENTAS[c]["dueno"] != "Diego":
                avisos.append(f"ℹ️  `{clave}` lee datos de CyD: fragmentos quedarian en el historial de "
                              f"{CUENTAS[c]['nombre']}. Permitido por decision de Diego (29-09-2026); "
                              "solo informativo.")
    for a in avisos:
        print(a)
    efecto = "AMPLIA" if amplia else ("restringe" if restringe else "neutro")

    def tabla(r):
        return "{ " + ", ".join(f"{k} = {str(v).lower() if isinstance(v, bool) else v}"
                                for k, v in r.items()) + " }"
    linea = ("recetas = { " + ", ".join(f"{k} = {tabla(v)}" for k, v in nuevo.items()) + " }") \
        if nuevo else "recetas = {}"
    a = en_perfil(poner_clave(base, "recetas", linea), {"recetas": nuevo})
    resumen = "; ".join(
        f"{k} {'automatico' if v.get('automatico') else 'cadena'}"
        + "".join(f" {x}={v[x]}" for x in ("umbral_semanal", "umbral_5h") if x in v)
        for k, v in nuevo.items()) or "sin recetas"
    return [a], efecto, False, None, resumen


def main():
    args =[a for a in sys.argv[1:] if not a.startswith("--")]
    auto = "--si" in sys.argv
    if os.geteuid() != 0:
        salir("aplicar-propuesta necesita root: sudo aplicar-propuesta <id>")
    if "--login" in sys.argv:
        if len(args) != 2:
            salir("uso: sudo aplicar-propuesta --login <perfil> <cuenta>")
        iniciar_sesion(*args)
        return
    carpeta_segura()
    if not args:
        listar()
        return
    pid = args[0]
    if not re.fullmatch(r"[a-z0-9-]{1,80}", pid):
        salir("id invalido")
    ruta_p = os.path.join(PROPUESTAS, pid + ".json")
    if os.path.exists(os.path.join(PROPUESTAS, pid + ".resultado.json")):
        salir("esa propuesta ya tiene resultado; crea una nueva desde la pagina")
    try:
        prop = json.loads(leer(ruta_p))
    except (OSError, ValueError) as e:
        salir(f"no pude leer la propuesta: {e}")

    perfil, tipo, valor = prop.get("perfil"), prop.get("tipo"), prop.get("valor")
    if perfil not in perfiles():
        salir(f"perfil desconocido: {perfil!r}")
    if tipo not in APLICABLES:
        salir(f"tipo desconocido: {tipo!r}")

    archivos, efecto, toca_systemd, verificar, resumen = armar_plan(perfil, tipo, valor,
                                                                    prop.get("motivo") or "")
    for a in archivos:
        if a.deriva():
            salir(f"DERIVA en {a.desp}: el vault y lo desplegado dicen cosas distintas.\n"
                  "Resolvelo antes (desplegar o revertir) — aplicar ahora mezclaria las dos.")

    print(f"\nPropuesta {pid}")
    print(f"  perfil: {perfil}   tipo: {tipo}   efecto: {efecto}")
    if prop.get("motivo"):
        print(f"  motivo: {prop['motivo']}")
    print()
    for a in archivos:
        sys.stdout.writelines(a.diff())
        print()
    if efecto == "AMPLIA":
        print("⚠️  Esto AMPLIA lo que puede hacer el bot. Lee los comentarios del perfil\n"
              "   antes de confirmar.")
    if toca_systemd:
        print("Toca systemd: se hace daemon-reload y se verifica desde adentro del servicio.")
    if tipo not in SIN_REINICIO:
        print(f"Se reinicia botv3@{perfil}: una consulta en curso se corta.")
    if not auto:
        if not sys.stdin.isatty():
            salir("sin terminal no confirmo nada; usa --si si de verdad es a proposito")
        if input("¿Aplicar? escribe 'si': ").strip().lower() != "si":
            print("No se aplico nada.")
            return

    # --- respaldo ---
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    resp = os.path.join(RESPALDOS, f"propuesta-{pid}-{stamp}")
    os.makedirs(resp, mode=0o700)
    for n, a in enumerate(archivos):
        for etiqueta, ruta in (("desplegado", a.desp), ("vault", a.vault)):
            if ruta and os.path.lexists(ruta):
                # Sin seguir enlaces: copy2 leeria como root el destino de un symlink.
                with os.fdopen(_abrir_seguro(ruta, os.O_RDONLY), "rb") as src, \
                        open(os.path.join(resp, f"{n}-{etiqueta}-{os.path.basename(ruta)}"), "wb") as dst:
                    shutil.copyfileobj(src, dst)

    unidad = f"botv3@{perfil}.service"

    def reiniciar():
        if toca_systemd:
            subprocess.run(["systemctl", "daemon-reload"])
        subprocess.run(["systemctl", "restart", unidad])
        time.sleep(6)
        return subprocess.run(["systemctl", "is-active", "--quiet", unidad]).returncode == 0

    for a in archivos:
        a.aplicar()
    if tipo in SIN_REINICIO:
        ok, detalle = True, SIN_REINICIO[tipo]
    else:
        ok, detalle = reiniciar(), ""
    if not ok:
        detalle = "el bot no quedo activo con el cambio"
    elif verificar is not None:
        main_pid = subprocess.run(["systemctl", "show", unidad, "-p", "MainPID", "--value"],
                                  capture_output=True, text=True).stdout.strip()
        ok, detalle = verificar(main_pid)
    if ok:
        escribir_resultado(pid, "aplicada", f"{tipo} {resumen} en {perfil} ({efecto})", resp)
        print(f"\n✅ Aplicada. {'' if tipo in SIN_REINICIO else unidad + ' activo. '}{detalle} Respaldo en {resp}")
        return

    for a in archivos:
        a.revertir()
    volvio = reiniciar()
    escribir_resultado(pid, "revertida",
                       f"{detalle}; se restauro lo anterior"
                       + ("" if volvio else " Y EL BOT NO VOLVIO — revisar a mano"), resp)
    salir(f"\n❌ {detalle}. Se revirtio. "
          f"{'Volvio a quedar activo.' if volvio else 'NO VOLVIO: journalctl -u ' + unidad}")


if __name__ == "__main__":
    main()
