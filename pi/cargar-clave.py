#!/usr/bin/python3
"""cargar-clave — carga o rota la API key de un proveedor gratis en el entorno de un bot.

    sudo cargar-clave <VARIABLE> <perfil> [<perfil> ...]
    sudo cargar-clave --desde-botv3-env <VARIABLE> <perfil> [<perfil> ...]
    cargar-clave --lista

Encargo 15 (01-10-2026). Instalado en /usr/local/bin/cargar-clave. Lo corre Diego, a
mano y con su clave de sudo: no esta en la lista blanca de sudoers ni lo llama ninguna
pagina.

Por que existe: la key NUNCA pasa por el chat, por Telegram ni por un argumento de
comando (queda en el historial y en `ps`). Aca se pide con un prompt sin eco y va
directo al archivo. Lo unico que se escribe en la linea de comando es el NOMBRE de la
variable, elegido de una lista fija, y el perfil.

Donde escribe: cada bot lee `EnvironmentFile=/opt/nodo/datos/secretos/botv3-<perfil>.env`
(unidad botv3@.service). `botv3.env`, sin sufijo, era el de la unidad vieja
`botv3.service` y hoy NO lo lee ningun bot: una key que solo este ahi no existe para
nadie. Por eso el perfil es obligatorio, y `--desde-botv3-env` copia a un perfil una
key que ya esta en `botv3.env`, de archivo a archivo y sin mostrarla.

Que hace: valida la forma, deja un respaldo del archivo, reemplaza (o agrega) la linea
`VARIABLE=valor` de forma atomica conservando dueño y permisos, y verifica releyendo.
No imprime la key ni un trozo de ella: solo su largo y si empieza con el prefijo que se
espera de ese proveedor. No reinicia el bot: dice la linea para hacerlo.
"""
import getpass
import os
import re
import sys
import tempfile
from datetime import datetime

SECRETOS = "/opt/nodo/datos/secretos"
ORIGEN_COMUN = f"{SECRETOS}/botv3.env"

# La lista fija incluye las variables de recetas.PROVEEDORES y las dos credenciales
# Client Credentials de Spotify. El prefijo es el que tenían las keys cargadas el
# 01-10; "" = no se sabe. No coincidir no rechaza: se avisa y se pregunta.
VARIABLES = {
    "GROQ_API_KEY": "gsk_",
    "GEMINI_API_KEY": "",
    "OPENROUTER_API_KEY": "sk-or-",
    "TAVILY_API_KEY": "tvly-",
    "SPOTIFY_CLIENT_ID": "",
    "SPOTIFY_CLIENT_SECRET": "",
}

# Una key: letras, numeros, «_», «-» y «.». La primera verificacion del 01-10 solo
# aceptaba letras y numeros y dio un falso «0 caracteres» con una key que traia «_».
FORMA = re.compile(r"[A-Za-z0-9._-]{20,300}")
PERFIL = re.compile(r"[a-z][a-z0-9]{0,19}")


def salir(msg, codigo=1):
    print(msg, file=sys.stderr)
    sys.exit(codigo)


def archivo_de(perfil):
    return f"{SECRETOS}/botv3-{perfil}.env"


def problema_de_forma(valor):
    """Por que `valor` no sirve como key, o "" si sirve. No dice nada del contenido."""
    if not valor:
        return "esta vacia"
    if valor != valor.strip() or re.search(r"\s", valor):
        return "trae espacios o saltos de linea"
    if not FORMA.fullmatch(valor):
        return ("no tiene forma de key: se esperan de 20 a 300 letras, numeros, «_», «-» o «.» "
                f"y llegaron {len(valor)} caracteres")
    return ""


def verificacion(variable, valor):
    """Lo unico que se muestra de una key: su largo y si empieza con el prefijo esperado."""
    prefijo = VARIABLES[variable]
    texto = f"{variable}: {len(valor)} caracteres"
    if prefijo:
        texto += f"; empieza con «{prefijo}»: {'si' if valor.startswith(prefijo) else 'NO'}"
    return texto


def valor_en(texto, variable):
    """El valor de `variable` en el texto de un .env, o None. Acepta cualquier caracter
    en el valor (tambien «_» y «-») y las comillas que systemd permite."""
    hallado = None
    for linea in texto.splitlines():
        m = re.match(rf"\s*{re.escape(variable)}=(.*)$", linea)
        if m:
            hallado = m.group(1).strip()
            if len(hallado) >= 2 and hallado[0] == hallado[-1] and hallado[0] in "\"'":
                hallado = hallado[1:-1]
    return hallado


def con_variable(texto, variable, valor):
    """El texto del .env con `VARIABLE=valor`: reemplaza su linea (y borra repetidas) o
    la agrega al final. Las demas lineas quedan igual, byte por byte."""
    lineas, puesta = [], False
    for linea in texto.split("\n"):
        if re.match(rf"\s*{re.escape(variable)}=", linea):
            if not puesta:
                lineas.append(f"{variable}={valor}")
                puesta = True
            continue
        lineas.append(linea)
    if not puesta:
        while lineas and lineas[-1] == "":
            lineas.pop()
        lineas += [f"{variable}={valor}", ""]
    return "\n".join(lineas)


def escribir(ruta, variable, valor, ahora=None):
    """Reemplaza el archivo de forma atomica, con el mismo dueño y permisos, y deja un
    respaldo `.bak-<fecha>` (0600). Devuelve la ruta del respaldo."""
    with open(ruta, encoding="utf-8") as fh:
        antes = fh.read()
    info = os.stat(ruta)
    respaldo = f"{ruta}.bak-{(ahora or datetime.now()).strftime('%Y%m%d-%H%M%S')}"
    fd = os.open(respaldo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(antes)
    fd, temporal = tempfile.mkstemp(dir=os.path.dirname(ruta), prefix=".cargar-clave-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(con_variable(antes, variable, valor))
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temporal, info.st_mode & 0o777)
        if os.geteuid() == 0:
            os.chown(temporal, info.st_uid, info.st_gid)
        os.replace(temporal, ruta)
    except BaseException:
        if os.path.exists(temporal):
            os.unlink(temporal)
        raise
    with open(ruta, encoding="utf-8") as fh:
        if valor_en(fh.read(), variable) != valor:
            salir(f"{ruta}: la verificacion fallo; el archivo de antes quedo en {respaldo}")
    return respaldo


def pedir(variable):
    """La key, sin eco. Solo desde una terminal: asi no llega por un pipe que deje el
    valor en el historial de la shell."""
    if not sys.stdin.isatty():
        salir("cargar-clave pide la key en una terminal, sin eco: no se le puede pasar por un pipe")
    return getpass.getpass(f"Pega la {variable} (no se va a ver) y Enter: ").strip()


def main(args):
    if args == ["--lista"]:
        for variable, prefijo in VARIABLES.items():
            print(variable + (f"  (empieza con {prefijo})" if prefijo else ""))
        return 0
    copiar = "--desde-botv3-env" in args
    args = [a for a in args if a != "--desde-botv3-env"]
    if len(args) < 2 or args[0] not in VARIABLES or any(a.startswith("-") for a in args):
        salir("uso: sudo cargar-clave [--desde-botv3-env] <VARIABLE> <perfil> [<perfil> ...]\n"
              f"     VARIABLE: {', '.join(VARIABLES)}\n"
              "     La key no va en la linea de comando: se pide despues, sin eco.")
    variable, perfiles = args[0], args[1:]
    for perfil in perfiles:
        if not PERFIL.fullmatch(perfil):
            salir(f"perfil invalido: {perfil[:20]!r} (¿pegaste la key como argumento? No va ahi)")
        if not os.path.isfile(archivo_de(perfil)):
            salir(f"no existe {archivo_de(perfil)}: ese bot no tiene archivo de entorno")
    if os.geteuid() != 0:
        salir("cargar-clave necesita root: sudo cargar-clave " + " ".join(args))
    if copiar:
        try:
            with open(ORIGEN_COMUN, encoding="utf-8") as fh:
                valor = valor_en(fh.read(), variable)
        except OSError as e:
            salir(f"no pude leer {ORIGEN_COMUN}: {e.strerror}")
        if not valor:
            salir(f"{variable} no esta en {ORIGEN_COMUN}")
    else:
        valor = pedir(variable)
    problema = problema_de_forma(valor)
    if problema:
        salir(f"{variable} no se cargo: {problema}")
    print(verificacion(variable, valor))
    prefijo = VARIABLES[variable]
    if prefijo and not valor.startswith(prefijo):
        if not sys.stdin.isatty() or \
                input(f"No empieza con «{prefijo}». ¿Cargarla igual? [s/N] ").strip().lower() != "s":
            salir("no se cargo nada")
    for perfil in perfiles:
        respaldo = escribir(archivo_de(perfil), variable, valor)
        print(f"✅ {variable} quedo en {archivo_de(perfil)} ({len(valor)} caracteres). "
              f"Respaldo: {respaldo}")
    print("El bot la lee al arrancar. Para que la tome:")
    for perfil in perfiles:
        print(f"    sudo systemctl restart botv3@{perfil}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
