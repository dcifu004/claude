#!/usr/bin/env python3
"""buscar-web — búsqueda web con Tavily para los encargos de investigación (encargos 32 y 32c).

    python3 encargos/buscar-web.py "consulta" [--noticias] [--semana]
    python3 encargos/buscar-web.py --manual "consulta"      # fuera de la cola

Por qué existe: en la cola el autor corre sin `WebSearch` (HERRAMIENTAS de cola-run.py) y solo
encontraba lo que ya sabía dónde estaba, con `curl`. Tavily trae `published_date`, así que la
fecha llega escrita y no inferida.

Cómo se busca (32c): la cola es la intermediaria. Tavily NO está en la autorización (cubre Claude,
Codex y OpenAI) y la consulta la escribe un agente que ya leyó el vault, así que el muro va en el
camino y no en su buena voluntad:
  - el autor no llama a Tavily ni lee la key: le PIDE la búsqueda a la cola. `correr()` de
    cola-run.py abre, solo para las fases de autor (autor, fixN) de una etapa `investigacion`, una
    carpeta de buzón nueva (0700) en encargos/vivo/buzon/<al azar>/, pasa su ruta en ENCARGO_BUZON y
    levanta un hilo que la atiende mientras dura la fase. Sin `--manual`, este script deja ahí
    `pedido-<id>.json` (consulta, noticias, semana), espera `respuesta-<id>.json` (rc y texto) hasta
    ESPERA_S segundos e imprime lo mismo, con el mismo código de salida, que cuando buscaba él;
  - el hilo llama a `atender()` de este archivo con el encargo y la fase que la cola tiene en
    memoria. Lo que el pedido diga de encargo, fase o naturaleza se ignora, y ENCARGO_ID y
    ENCARGO_NATURALEZA son solo información: no autorizan nada. Sin buzón y sin `--manual`, exit 2;
  - al terminar la fase la cola para el hilo, contesta «fase terminada» a lo pendiente y borra la
    carpeta. Un revisor o una etapa de otra naturaleza nunca reciben ENCARGO_BUZON;
  - `atender()` es el único camino a Tavily, para el hilo y para `--manual`. Antes de llamar,
    `muro()` rechaza rutas y nombres del vault, términos laborales, nombres de personas y cualquier
    cosa con forma de secreto o dato personal. Ante la duda, rechaza;
  - cada pedido, aceptado o rechazado, queda en encargos/<ID>-busquedas.jsonl con su `via`
    («cola», más el nombre de la cola y la fase, o «manual»), y la plantilla de revisión obliga a
    leerlo;
  - el tope se cuenta y se registra bajo un flock del propio registro, que se mantiene durante la
    llamada a Tavily: 31 pedidos a la vez no pasan de 30 (32br2). Costo: las búsquedas de un mismo
    encargo se serializan;
  - la carpeta del registro, el archivo de la key y la fuente del tope NO se pueden cambiar por
    entorno ni por argumento (revisión 32br1), y ahora los usa el proceso de la cola, no el del
    autor. Las pruebas pasan una configuración por parámetro;
  - `--manual` se niega mientras viva CUALQUIER proceso `cola-run.py` en la Pi. No depende del
    árbol de procesos del que llama (setsid o doble fork no lo evaden) ni de las variables
    ENCARGO_*. Efecto: el usuario busca a mano solo con la cola detenida.
No redacta con ningún modelo: el autor ya es uno, y un resumen intermedio sería otra fuente de
fechas inventadas. La key nunca se imprime ni se registra.

Límite aceptado (decisión del usuario, 09-10-2026). El autor y la cola corren con el mismo usuario
Unix y el kernel de la Pi no trae Yama: todo lo que la cola escribe o demuestra, el autor lo puede
fabricar (32br3, hallazgo 1). Un agente decidido con ese uid puede:
  - fabricar un buzón y un proceso que lo atienda (o importar este archivo y llamar a `atender()`
    con el encargo que quiera), o dejar pedidos en el buzón abierto de otra cola;
  - leer la key, que ese usuario puede leer, y llamar a Tavily directo, sin muro, tope ni registro;
  - escribir o borrar líneas del registro.
Nada de eso se intenta impedir con más comprobaciones de pid, /proc, modos o JSON: es lo que la
decisión descartó, y dejarlas sugiere una garantía que no existe. Qué sigue protegiendo: en el
camino normal (autor → buzón → cola) toda consulta pasa por el muro, cuenta para el tope y queda
en el registro atribuida al encargo que la cola corre de verdad; el proceso del autor no recibe la
key ni abre la conexión; y la revisión lee el registro. Cerrarlo del todo exige un usuario Unix
aparte para la cola o para el buscador (opción B), que quedó fuera del encargo 32c.

Salidas: 0 bien · 2 uso o configuración (también «sin buzón» y «fase terminada») · 3 rechazada
por el muro · 4 tope de búsquedas · 5 error de Tavily o de red, o la cola no contestó a tiempo.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import date, datetime
from email.utils import parsedate_to_datetime
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import tomllib
import unicodedata
import urllib.error
import urllib.request

AQUI = Path(__file__).resolve().parent
URL = "https://api.tavily.com/search"
# Misma forma que _tavily_buscar de botv3.py (encargo 15).
MAX_RESULTADOS = 6
MAX_CONSULTA = 400
MAX_CONTENIDO = 300
# Archivo de entorno con una sola línea útil, TAVILY_API_KEY=… . Se crea con
# `sudo cargar-clave --desde-botv3-env TAVILY_API_KEY encargos` (perfil «encargos»).
CLAVE_DEFECTO = "/opt/nodo/datos/secretos/botv3-encargos.env"
# Búsquedas aceptadas por encargo: `busquedas_max_encargo` en [tavily] de cuentas.toml (el
# registro desplegado en /opt/botv3 y, si no está, el del repo; mismo orden que cola-run.py).
# Si la clave falta, vale TOPE_DEFECTO. TOPE_MAXIMO es un techo del código: como el autor puede
# editar el cuentas.toml del repo, subirlo desde el archivo no sirve; bajarlo sí.
REGISTROS_CUENTAS = (Path("/opt/botv3/cuentas.toml"), AQUI.parent / "botv3" / "cuentas.toml")
CLAVE_TOPE = "busquedas_max_encargo"
TOPE_DEFECTO = 30
TOPE_MAXIMO = 30
# Buzón de búsquedas (32c). Estas constantes son el protocolo entre el lado del autor (este script
# sin --manual) y el hilo de cola-run.py, que las importa de acá.
ESPERA_S = 90                   # cuánto espera el autor la respuesta de la cola
SONDEO_S = 0.1
MAX_PEDIDO = 4096               # bytes; una consulta válida (400 caracteres) cabe de sobra
PEDIDO = re.compile(r"pedido-([0-9a-f]{32})\.json")
CODIGOS = (0, 2, 3, 4, 5)
FASE_TERMINADA = ("⛔ fase terminada: la cola ya no atiende este buzón. Solo busca el autor de una "
                  "investigación, y solo mientras dura su fase.")
SOLO_LA_COLA = ("⛔ aquí solo busca la cola: este proceso no tiene buzón (ENCARGO_BUZON). La cola lo "
                "abre para el autor de una etapa `investigacion`; ENCARGO_ID y ENCARGO_NATURALEZA no "
                "autorizan nada. Fuera de la cola, el usuario busca con --manual.")


def leer_tope(registros=REGISTROS_CUENTAS) -> int:
    """Tope de búsquedas aceptadas por encargo. Valor inválido: ValueError (el script sale 2)."""
    for ruta in registros:
        try:
            datos = tomllib.loads(Path(ruta).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise ValueError(f"no se pudo leer {ruta}: {type(e).__name__}") from None
        tavily = datos.get("tavily")
        valor = tavily.get(CLAVE_TOPE, TOPE_DEFECTO) if isinstance(tavily, dict) else TOPE_DEFECTO
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
            raise ValueError(f"[tavily] {CLAVE_TOPE} en {ruta} tiene que ser un entero >= 1, no {valor!r}")
        return min(valor, TOPE_MAXIMO)
    return TOPE_DEFECTO


def config() -> dict:
    """Configuración de producción. Sin variables de entorno a propósito (ver el docstring)."""
    return {"clave": Path(CLAVE_DEFECTO), "registro": AQUI, "tope": leer_tope(), "proc": Path("/proc")}


# ---------------------------------------------------------------- el muro

def _normal(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


# Lista blanca de caracteres: letras (con tildes y ñ), dígitos, espacio y la puntuación de una
# pregunta. Fuera quedan los que delatan código, rutas, markdown o variables: _ # | ` { } [ ]
# < > = \ ~ @ ; y los saltos de línea (una línea copiada de un archivo).
_PERMITIDOS = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 .,:;¿?¡!'\"()/+%&$-]*")

_RECHAZOS: tuple[tuple[re.Pattern, str], ...] = (
    # Rutas y nombres del vault.
    (re.compile(r"vault|/opt/|/home/|/etc/|/srv/|10-proyectos|90-referencia|memoriaia|"
                r"\.(md|toml|jsonl?|py|env|sh)\b|frontmatter|syncthing|obsidian"), "nombra el vault o un archivo"),
    (re.compile(r"\w+/\w+/\w+"), "parece una ruta"),
    # Lo propio y lo laboral: personas, proyectos, la empresa y el nodo. Sale del PROPIO del
    # clasificador (sin los posesivos ni los sustantivos genéricos, que aquí rechazarían «memoria
    # RAM» o «nota técnica»), más lo laboral y lo que identifica el nodo.
    (re.compile(r"\b(cyd|gop|quinque|rinco|nahuel|calama|nuble|cgm|aif|aite|mandante|"
                r"inspeccion fiscal|mercado publico|licitacion(es)?|contratos?|propuestas?|"
                r"arnes(es)?|encargos?|camila|cami|pilar|jaime|diego|dcifu\w*|cifuentes|"
                r"pi5diego|dcspi5|tailnet|ts\.net|cockpit|botv3|dcs_v3bot)\b"), "nombra algo propio o laboral"),
    (re.compile(r"\b[a-z]{2,5}-\d{1,2}-\d{3,}\b"), "trae un código de contrato"),
    # Secretos y datos personales.
    # Con guion obligatorio (sin él, «sk» calza con «skateboard»); después puede venir otro, como
    # en las keys de Tavily, que son «tvly-dev-…».
    (re.compile(r"\b(tvly|gsk|sk|ghp|xox[abp])-[a-z0-9-]{6,}|\baiza[a-z0-9-]{20,}"), "trae una key"),
    (re.compile(r"[a-z0-9]{28,}"), "trae una cadena con forma de token"),
    (re.compile(r"\b(token|key|secret|password|passwd|api[ -]?key|clave)\s*[=:]"), "trae un secreto"),
    (re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dk]\b"), "trae un RUT"),
    (re.compile(r"(\+?56)?\s?9[\s-]?\d{4}[\s-]?\d{4}\b"), "trae un teléfono"),
    (re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b"), "trae una IP"),
)


def muro(consulta: str) -> str | None:
    """None si la consulta puede salir a Tavily; si no, el motivo del rechazo."""
    if not consulta.strip():
        return "consulta vacía"
    if len(consulta) > MAX_CONSULTA:
        return f"pasa de {MAX_CONSULTA} caracteres"
    if "@" in consulta:
        return "trae un correo"
    if not _PERMITIDOS.fullmatch(consulta):
        raros = sorted({c for c in consulta if not _PERMITIDOS.fullmatch(c)})
        return "trae caracteres que no van en una pregunta: " + " ".join(repr(c) for c in raros[:5])
    n = _normal(consulta)
    for patron, motivo in _RECHAZOS:
        if patron.search(n):
            return motivo
    return None


# ---------------------------------------------------------------- cola viva y registro

_ID = re.compile(r"\d{2}[a-z]?\d?")


def _cmdline(proc: Path, pid) -> list[str] | None:
    try:
        crudo = (proc / str(pid) / "cmdline").read_bytes()
    except OSError:
        return None
    return [a.decode("utf-8", "replace") for a in crudo.split(b"\0") if a]


def _es_cola(cmd: list[str] | None) -> bool:
    """`python… cola-run.py`: intérprete python y primer argumento que no es opción, el script. Un
    `grep cola-run.py` o el `bash -c "python3 … | tee"` de tmux no cuentan."""
    if not cmd or not os.path.basename(cmd[0]).startswith("python"):
        return False
    script = next((a for a in cmd[1:] if not a.startswith("-")), "")
    return os.path.basename(script) == "cola-run.py"


def cola_viva(proc: Path = Path("/proc")) -> bool:
    """True si hay algún proceso `python… cola-run.py` vivo en la máquina. Solo decide si `--manual`
    se niega; no autoriza nada. No mira ancestros: el autor puede desacoplarse de la cola (setsid,
    doble fork) y borrar su entorno, pero no puede esconder el proceso de la cola."""
    try:
        pids = [p for p in proc.iterdir() if p.name.isdigit()]
    except OSError:
        return True   # sin /proc no se puede descartar: se niega
    propio = str(os.getpid())
    return any(p.name != propio and _es_cola(_cmdline(proc, p.name)) for p in pids)


def archivo_registro(cfg: dict, eid: str) -> Path:
    return cfg["registro"] / f"{eid}-busquedas.jsonl"


def aceptadas(ruta: Path) -> int:
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return 0
    n = 0
    for linea in lineas:
        try:
            n += bool(json.loads(linea).get("aceptada"))
        except (ValueError, AttributeError):
            continue
    return n


@contextlib.contextmanager
def candado(ruta: Path):
    """flock exclusivo sobre el propio registro (se crea si falta). Quien cuenta las aceptadas y
    registra la suya tiene que tenerlo todo el rato, o dos procesos leen el mismo conteo."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def registrar(ruta: Path, fila: dict, clave: str = "") -> None:
    texto = json.dumps(fila, ensure_ascii=False, default=str)
    if clave:
        texto = texto.replace(clave, "[oculto]")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as f:
        f.write(texto + "\n")


# ---------------------------------------------------------------- Tavily

def leer_clave(ruta: Path) -> str:
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for linea in lineas:
        k, _, v = linea.strip().partition("=")
        if k.strip() == "TAVILY_API_KEY":
            return v.strip().strip("'\"")
    return ""


def fecha_tavily(valor) -> date | None:
    """Igual que fecha_tavily de botv3.py: lo que no se entiende es «sin fecha»."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        return parsedate_to_datetime(valor.strip()).date()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(valor.strip().replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _una_linea(texto, tope: int) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()[:tope]


def resultados(datos) -> list[dict]:
    """Copia de resultados_tavily de botv3.py (hay una prueba que compara las dos)."""
    crudos = datos.get("results") if isinstance(datos, dict) else None
    out = []
    for r in crudos if isinstance(crudos, list) else []:
        url = r.get("url") if isinstance(r, dict) else None
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        out.append({"url": url[:500], "titulo": _una_linea(r.get("title"), 200),
                    "contenido": _una_linea(r.get("content"), 700),
                    "fecha": fecha_tavily(r.get("published_date"))})
    return out[:MAX_RESULTADOS]


def buscar(consulta: str, clave: str, noticias: bool, semana: bool) -> list[dict]:
    cuerpo = {"query": consulta[:MAX_CONSULTA], "topic": "news" if noticias else "general",
              "max_results": MAX_RESULTADOS}
    if semana:
        cuerpo["time_range"] = "week"
    pedido = urllib.request.Request(URL, data=json.dumps(cuerpo).encode(), method="POST",
                                    headers={"Authorization": f"Bearer {clave}",
                                             "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as r:
            datos = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Tavily respondió {e.code}: {detalle}") from None
    except (OSError, http.client.HTTPException, ValueError) as e:
        # OSError cubre URLError y TimeoutError, y también un corte a mitad de la lectura.
        raise RuntimeError(f"no se pudo llamar a Tavily: {type(e).__name__}: {e}") from None
    return resultados(datos)


def imprimir(hallados: list[dict]) -> str:
    if not hallados:
        return "Sin resultados."
    lineas = []
    for i, r in enumerate(hallados, 1):
        fecha = r["fecha"].strftime("%d-%m-%Y") if r["fecha"] else "sin fecha"
        lineas.append(f"[{i}] fecha: {fecha} · {r['titulo']} · {r['url']}")
        if r["contenido"]:
            lineas.append(f"    {r['contenido'][:MAX_CONTENIDO]}")
    lineas.append("La fecha es la de publicación que entrega el buscador; «sin fecha» = la fuente no la trae.")
    return "\n".join(lineas)


# ---------------------------------------------------------------- atender (la cola y --manual)

def _fila(eid: str, origen: dict | None) -> dict:
    return {"hora": datetime.now().astimezone().isoformat(timespec="seconds"), **(origen or {}),
            "encargo": eid}


def anotar_rechazo(eid: str, cfg: dict, origen: dict | None, motivo: str) -> None:
    """Deja en el registro un pedido que ni siquiera se pudo leer (malformado o gigante): no trae
    consulta, pero la revisión tiene que ver que alguien lo intentó."""
    if eid == "manual" or _ID.fullmatch(eid):
        registrar(archivo_registro(cfg, eid), dict(_fila(eid, origen), aceptada=False, rechazo=motivo))


def atender(consulta: str, opciones: dict, eid: str, cfg: dict, origen: dict | None = None) -> tuple[int, str]:
    """Una búsqueda entera: muro, key, tope bajo flock, llamada a Tavily y registro. Es el único
    camino a Tavily; lo usan el hilo del buzón de cola-run.py y `--manual`. `eid` lo decide quien
    llama (la cola, de su memoria; nunca el pedido) y `origen` va a cada fila: {"via": "cola",
    "cola": …, "fase": …} o {"via": "manual"}. No imprime: devuelve (código de salida, texto)."""
    if eid != "manual" and not _ID.fullmatch(eid):
        return 2, f"⛔ el id de encargo {eid[:20]!r} no sirve para nombrar el registro de búsquedas."
    noticias, semana = bool(opciones.get("noticias")), bool(opciones.get("semana"))
    ruta = archivo_registro(cfg, eid)
    fila = dict(_fila(eid, origen), consulta=consulta, noticias=noticias, semana=semana)
    rechazo = muro(consulta)
    if rechazo:
        registrar(ruta, dict(fila, aceptada=False, rechazo=rechazo))
        return 3, f"⛔ consulta rechazada: {rechazo}. Escribe solo la pregunta pública, sin nada del vault."
    clave = leer_clave(cfg["clave"])
    if not clave:
        return 2, (f"⛔ no hay TAVILY_API_KEY en {cfg['clave']}. Se carga con: "
                   "sudo cargar-clave --desde-botv3-env TAVILY_API_KEY encargos")
    with candado(ruta):
        if aceptadas(ruta) >= cfg["tope"]:
            registrar(ruta, dict(fila, aceptada=False, rechazo=f"tope de {cfg['tope']} búsquedas"))
            return 4, f"⛔ este encargo ya usó sus {cfg['tope']} búsquedas."
        try:
            hallados = buscar(consulta, clave, noticias, semana)
        except RuntimeError as e:
            texto = str(e).replace(clave, "[oculto]")
            registrar(ruta, dict(fila, aceptada=True, error=texto), clave)
            return 5, f"⛔ {texto}"
        registrar(ruta, dict(fila, aceptada=True, resultados=len(hallados),
                             fuentes=[{"url": r["url"], "fecha": r["fecha"].isoformat() if r["fecha"] else None}
                                      for r in hallados]), clave)
    return 0, imprimir(hallados)


# ---------------------------------------------------------------- el lado del autor (buzón)

def escribir_atomico(ruta: Path, datos: bytes) -> None:
    """Entero o nada: temporal en la misma carpeta y rename. Quien sondea la carpeta nunca ve un
    archivo a medias. Lo usan el autor (pedido) y la cola (respuesta)."""
    tmp = ruta.with_name(f".{ruta.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(datos)
        os.replace(tmp, ruta)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def pedir_a_la_cola(buzon: Path, consulta: str, noticias: bool, semana: bool,
                    espera: float = ESPERA_S) -> tuple[int, str]:
    """Deja el pedido en el buzón de la fase y espera la respuesta de la cola. Este proceso no lee
    la key, no abre la conexión y no escribe el registro: todo eso lo hace la cola en `atender()`.
    No manda encargo ni fase: la cola no los leería."""
    pid = secrets.token_hex(16)
    pedido, respuesta = buzon / f"pedido-{pid}.json", buzon / f"respuesta-{pid}.json"
    cuerpo = json.dumps({"consulta": consulta, "noticias": noticias, "semana": semana}, ensure_ascii=False)
    try:
        escribir_atomico(pedido, cuerpo.encode("utf-8"))
    except (FileNotFoundError, NotADirectoryError):
        return 2, FASE_TERMINADA
    except OSError as e:
        return 2, f"⛔ no se pudo dejar el pedido en el buzón de la cola ({type(e).__name__})."
    limite = time.monotonic() + espera
    while True:
        try:
            crudo = respuesta.read_text(encoding="utf-8")
        except FileNotFoundError:
            crudo = None
        except OSError as e:
            return 5, f"⛔ no se pudo leer la respuesta de la cola ({type(e).__name__})."
        if crudo is not None:
            with contextlib.suppress(OSError):
                respuesta.unlink()
            try:
                datos = json.loads(crudo)
                rc, texto = datos["rc"], datos["texto"]
            except (ValueError, KeyError, TypeError):
                rc, texto = None, None
            if isinstance(rc, bool) or rc not in CODIGOS or not isinstance(texto, str):
                return 5, "⛔ la respuesta de la cola no se entiende; mira el registro antes de repetir la búsqueda."
            return rc, texto
        if not buzon.is_dir():
            return 2, FASE_TERMINADA
        if time.monotonic() >= limite:
            break
        time.sleep(SONDEO_S)
    try:
        pedido.unlink()
    except FileNotFoundError:
        return 5, (f"⛔ la cola no contestó en {espera:.0f} s y ya había tomado el pedido: puede que la "
                   "búsqueda se haya hecho y cuente para el tope. Mira el registro antes de repetirla.")
    except OSError:
        pass
    return 5, (f"⛔ la cola no contestó en {espera:.0f} s. El pedido se retiró: no se buscó nada. "
               "Si se repite, la cola no está atendiendo el buzón.")


# ---------------------------------------------------------------- principal

def principal(argv: list[str] | None = None, cfg: dict | None = None, espera: float = ESPERA_S) -> int:
    """`cfg` y `espera` solo los pasan las pruebas; desde la línea de comandos `cfg` es config() y
    solo se usa con --manual: el lado del autor no lee configuración, key ni registro."""
    ap = argparse.ArgumentParser(description="Búsqueda web con Tavily para encargos de investigación.")
    ap.add_argument("consulta")
    ap.add_argument("--noticias", action="store_true", help="topic news (trae published_date)")
    ap.add_argument("--semana", action="store_true", help="solo la última semana")
    ap.add_argument("--manual", action="store_true", help="fuera de la cola, a mano")
    a = ap.parse_args(argv)
    if a.manual:
        try:
            cfg = cfg or config()
        except ValueError as e:
            print(f"⛔ {e}", file=sys.stderr)
            return 2
        if cola_viva(cfg["proc"]):
            print("⛔ hay una cola de encargos corriendo: --manual está cerrado mientras tanto "
                  "(no se puede distinguir una búsqueda tuya de la de un encargo). Espera a que termine.",
                  file=sys.stderr)
            return 2
        rc, texto = atender(a.consulta, {"noticias": a.noticias, "semana": a.semana}, "manual", cfg,
                            {"via": "manual"})
    else:
        buzon = os.environ.get("ENCARGO_BUZON", "")
        if not buzon:
            print(SOLO_LA_COLA, file=sys.stderr)
            return 2
        rc, texto = pedir_a_la_cola(Path(buzon), a.consulta, a.noticias, a.semana, espera)
    print(texto, file=sys.stdout if rc == 0 else sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(principal())
