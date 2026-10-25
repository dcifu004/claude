#!/usr/bin/env python3
"""Registro único de avisos (encargo 23b, doc 27 §5.5).

    python3 registro_avisos.py --panel      # lo que dibuja la pestaña 🔔 Avisos de 🧵 Encargos

Cada aviso que sale a Telegram deja UNA línea en /opt/nodo/datos/avisos.jsonl:

    {"momento", "origen", "nivel", "texto", "linea", "id", "estado"}

- `nivel` es info, ok, alerta o error. `linea` es la línea sugerida, si el aviso trae una. `id` es
  el del pedido de nodo-desplegar y `estado` el suyo, cuando se conoce al escribir; si no, queda
  vacío y la pestaña lo resuelve al leer.
- Acá escriben cola-run.py (origen «cola») y paginas-pendientes.py («paginas») con registrar().
  avisos.py («nodo» y «cuota») escribe la MISMA forma con su propia copia de la función: vive fuera
  del cifrado y no puede importar nada del vault.
- Registrar no cambia cómo se envía y nunca detiene al que avisa: si no se puede escribir, devuelve
  False y el aviso sale igual.
- Nunca se escriben tokens ni el CHAT_ID (sin_secretos).

Lo que NO pasa por registrar() se lee de su propio estado, sin modificarlo:
- nodo-desplegar (es root): /var/spool/nodo-desplegar/resultados/<id>.json. De ahí sale el estado
  de cada pedido; los que nadie registró aparecen con origen «nodo-desplegar». Solo se usan `id`,
  `estado` y `hora`: el `detalle` es texto libre de nodo-desplegar (puede nombrar a una persona o
  traer la salida de un comando) y no se lee ni se publica.
- Las noticias: solo los avisos que el agente ya manda (manifiesto.jsonl con Telegram en ok y la
  tabla `avisados` de noticias.db). Las notas siguen en 📰 Noticias.
"""
from __future__ import annotations

import argparse
import ast
import fcntl
import json
import os
import re
import secrets
import sqlite3
import stat
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

VOLUMEN = Path("/opt/nodo/datos")
REGISTRO = VOLUMEN / "avisos.jsonl"
VAULT = VOLUMEN / "srv/vault_personal"
D = VAULT / "10-Proyectos/11-Pi5"
# Lo que avisos.py no pudo escribir en REGISTRO (volumen cerrado o sin permiso) y todavía no volcó.
PENDIENTE_AVISOS = Path("/var/lib/nodo/avisos-registro-pendiente.jsonl")
RESULTADOS = Path("/var/spool/nodo-desplegar/resultados")
RESULTADOS_DIAS = 7       # nodo-desplegar borra los resultados a los 7 días (limpiar)
USO = VOLUMEN / "uso.json"
CUENTAS = (Path("/opt/botv3/cuentas.toml"), D / "botv3/cuentas.toml")
NOTICIAS = VAULT / "10-Proyectos/13-Agente-Noticias"
NOTICIAS_DB = VOLUMEN / "noticias/noticias.db"
# Desplegado primero: es lo que de verdad dispara. El del vault puede estar sin desplegar.
FUENTES = {"estado": (Path("/usr/local/bin/estado"), D / "pi/estado.py"),
           "avisos": (Path("/usr/local/bin/avisos"), D / "pi/avisos.py"),
           "nodo-desplegar": (Path("/usr/local/bin/nodo-desplegar"), D / "pi/nodo-desplegar.py")}

# Bandeja de salida (encargo 24): lo que la cola escribe para que avisos.py —que es root y tiene el
# token— lo mande a Telegram en su próximo ciclo. Vive en el volumen, de dcifu004; avisos.py solo la
# lee. El estado de ese lado, afuera del cifrado y legible por todos, lo escribe avisos.py.
BANDEJA = VOLUMEN / "avisos-salida.jsonl"
BANDEJA_ESTADO = Path("/var/lib/nodo/avisos-bandeja.json")
BANDEJA_VERSION = 1             # la que entiende este emisor; avisos.py publica la suya
BANDEJA_FRESCA_S = 25 * 60      # el timer corre cada 10 min: más viejo que esto = no está andando
MAX_BANDEJA_TEXTO, BANDEJA_TOPE, BANDEJA_QUEDAN = 1000, 200, 100
BANDEJA_BYTES_TOPE = 192 * 1024  # bajo los 256 KiB que avisos.py acepta leer (BANDEJA_MAX_BYTES)
# Cerrojo de las colas entre sí (avisos.py no lo toma: solo lee, y el recorte es un os.replace atómico).
BANDEJA_CERROJO = VOLUMEN / ".avisos-salida.lock"
BANDEJA_CERROJO_S = 5.0
# Estas son las únicas dos rutas que una marca de pruebas debe interceptar. Se fijan al
# cargar el módulo: las suites pueden cambiar VOLUMEN para aislar otros estados, pero
# eso no puede convertir por accidente una ruta real en una ruta de pruebas (ni al revés).
REGISTRO_PRODUCCION = REGISTRO
BANDEJA_PRODUCCION = BANDEJA

NIVELES = ("info", "ok", "alerta", "error")
CLAVES = ("momento", "origen", "nivel", "texto", "linea", "id", "estado")
RE_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")
MAX_TEXTO, MAX_LINEA, MAX_HISTORIAL = 4000, 1000, 400

# El nivel sale del emoji con que el emisor ya abre el aviso: no se le pide nada nuevo.
_POR_EMOJI = (("error", ("⛔", "💥", "❌")), ("alerta", ("⏸", "⏳", "🔒", "🔴", "🟡", "⚠", "🚨")),
              ("ok", ("✅", "🟢", "🔓")))

_SECRETOS = (
    # El token de un bot. Sin \b al inicio: en la URL va pegado a «bot» (…/bot123456:AA…/sendMessage).
    (re.compile(r"(?<!\d)\d{6,}:[A-Za-z0-9_-]{30,}"), "[token]"),
    (re.compile(r"(?i)\b(chat_?id\s*[=:]\s*)-?\d+"), r"\1[oculto]"),
    (re.compile(r"(?i)((?:token|key|secret|password|passwd|api)[\w-]*\s*[=:]\s*)\S+"), r"\1[oculto]"),
)


def nivel_de(texto: str) -> str:
    cabeza = (texto or "").lstrip()[:4]
    for nivel, marcas in _POR_EMOJI:
        if any(m in cabeza for m in marcas):
            return nivel
    return "info"


def sin_secretos(texto: str, *exactos: str) -> str:
    """El texto sin tokens ni CHAT_ID. `exactos` son valores que el emisor conoce y no deben quedar."""
    for valor in exactos:
        if valor:
            texto = texto.replace(str(valor), "[oculto]")
    for patron, cambio in _SECRETOS:
        texto = patron.sub(cambio, texto)
    return texto


def fila(origen: str, texto: str, linea: str | None = None, id: str | None = None,
         estado: str | None = None, nivel: str | None = None, momento: str | None = None) -> dict:
    """La forma única de una línea del registro."""
    texto = sin_secretos(str(texto))[:MAX_TEXTO]
    return {"momento": momento or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "origen": str(origen),
            "nivel": nivel if nivel in NIVELES else nivel_de(texto),
            "texto": texto,
            "linea": sin_secretos(str(linea))[:MAX_LINEA] if linea else None,
            "id": id if isinstance(id, str) and RE_ID.fullmatch(id) else None,
            "estado": str(estado) if estado else None}


def _dentro_del_volumen(ruta: Path) -> bool:
    try:
        ruta.relative_to(VOLUMEN)
        return True
    except ValueError:
        return False


def _abrir(ruta: Path) -> int:
    """Abre para agregar, creándolo con 0664: avisos.py entra por el grupo, no como dueño."""
    fd = os.open(ruta, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o664)
    try:
        st = os.fstat(fd)
        if st.st_uid == os.geteuid() and (st.st_mode & 0o777) != 0o664:
            os.fchmod(fd, 0o664)        # el umask del que crea no decide quién más escribe
    except OSError:
        pass
    return fd


def registrar(origen: str, texto: str, linea: str | None = None, id: str | None = None,
              estado: str | None = None, nivel: str | None = None) -> bool:
    """Agrega una línea al registro. Nunca lanza: registrar no puede detener al que avisa."""
    try:
        ruta = REGISTRO
        # Las suites ya reemplazan REGISTRO por un temporal antes de cargar el módulo. La
        # marca solo debe proteger la ruta de producción fijada al cargarlo; redirigir
        # también esos temporales haría que las pruebas dejen de ejercitar su propia forma.
        if os.environ.get("NODO_PRUEBAS") == "1" and ruta == REGISTRO_PRODUCCION:
            temporal = os.environ.get("NODO_AVISOS_DIR")
            if not temporal:
                print("aviso de prueba descartado: falta NODO_AVISOS_DIR", file=sys.stderr)
                return False
            ruta = Path(temporal) / REGISTRO_PRODUCCION.name
        # Con el volumen cerrado /opt/nodo/datos es la carpeta vacía de la raíz: ahí no se escribe.
        if _dentro_del_volumen(ruta) and not os.path.ismount(VOLUMEN):
            return False
        cuerpo = (json.dumps(fila(origen, texto, linea, id, estado, nivel), ensure_ascii=False) + "\n").encode()
        fd = _abrir(ruta)
        try:
            os.write(fd, cuerpo)        # una sola escritura con O_APPEND: las líneas no se mezclan
        finally:
            os.close(fd)
        return True
    except Exception as e:  # noqa: BLE001 — ver docstring
        print(f"no se pudo registrar el aviso en {ruta}: {type(e).__name__}", file=sys.stderr)
        return False


def bandeja_activa(ahora: float | None = None) -> bool:
    """True si el lado nuevo de avisos.py está desplegado, andando y puede leer la bandeja. Lo dice
    él mismo en /var/lib/nodo/avisos-bandeja.json (versión, último ciclo y si leyó bien); nadie edita
    un interruptor. Sin archivo, ilegible, de otra versión o viejo: no está activo."""
    try:
        d = json.loads(BANDEJA_ESTADO.read_text(encoding="utf-8"))
        ciclo = d["ultimo_ciclo"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    ahora = time.time() if ahora is None else ahora
    return (isinstance(d, dict) and d.get("version") == BANDEJA_VERSION and d.get("ok") is True
            and isinstance(ciclo, (int, float)) and not isinstance(ciclo, bool) and 0 <= ahora - ciclo <= BANDEJA_FRESCA_S)


def _abrir_regular(ruta: Path, flags: int, modo: int = 0o644) -> int:
    """Abre `ruta` SIN bloquear y sin seguir enlaces, y solo la entrega si es un archivo común, de este
    usuario y con un solo nombre. Un FIFO con lector colgaría un open() normal; con O_NONBLOCK abre (o falla
    con ENXIO) y el fstat lo rechaza. Lanza OSError si no sirve."""
    fd = os.open(ruta, flags | os.O_NONBLOCK | os.O_NOFOLLOW, modo)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.geteuid():
            raise OSError(f"{ruta.name} no es un archivo común propio")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _cerrojo(espera_s: float | None = None, ruta: Path | None = None) -> int:
    """El cerrojo (flock) que serializa a las colas que escriben o recortan la bandeja. Se pide sin
    bloquear y se reintenta hasta `espera_s`: si no llega, lanza OSError y la cola avisa por el camino de
    siempre en vez de colgarse."""
    fd = _abrir_regular(ruta or BANDEJA_CERROJO, os.O_RDWR | os.O_CREAT)
    limite = time.monotonic() + (BANDEJA_CERROJO_S if espera_s is None else espera_s)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= limite:
                os.close(fd)
                raise OSError("la bandeja está ocupada") from None
            time.sleep(0.02)
        except BaseException:
            os.close(fd)
            raise


def a_la_bandeja(texto: str) -> bool:
    """Deja UNA línea de texto en la bandeja: {id, momento, texto}. Sin comando: lo copiable va al
    registro. Con el volumen cerrado no hay cola ni bandeja. Agregar y recortar ocurren juntos bajo un
    cerrojo, así una cola no pisa lo que otra acaba de agregar. Nunca lanza ni se cuelga."""
    try:
        bandeja, cerrojo_ruta = BANDEJA, BANDEJA_CERROJO
        # Igual que en registrar(): solo se aparta la bandeja de producción fijada al
        # cargar el módulo. Una suite que ya aisló BANDEJA conserva su escritura normal.
        if os.environ.get("NODO_PRUEBAS") == "1" and bandeja == BANDEJA_PRODUCCION:
            temporal = os.environ.get("NODO_AVISOS_DIR")
            if not temporal:
                print("aviso de prueba descartado: falta NODO_AVISOS_DIR", file=sys.stderr)
                return False
            bandeja = Path(temporal) / BANDEJA_PRODUCCION.name
            cerrojo_ruta = Path(temporal) / BANDEJA_CERROJO.name
        if _dentro_del_volumen(bandeja) and not os.path.ismount(VOLUMEN):
            return False
        ahora = datetime.now(timezone.utc).astimezone()
        limpio = " ".join(sin_secretos(str(texto)).split())[:MAX_BANDEJA_TEXTO]
        if not limpio:
            return False
        cuerpo = (json.dumps({"id": f"s-{ahora:%Y%m%d-%H%M%S}-{secrets.token_hex(4)}",
                              "momento": ahora.isoformat(timespec="seconds"), "texto": limpio},
                             ensure_ascii=False) + "\n").encode()
        cerrojo = _cerrojo(ruta=cerrojo_ruta)
        try:
            fd = _abrir_regular(bandeja, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
            try:
                os.write(fd, cuerpo)
            finally:
                os.close(fd)
            _recortar_bandeja(bandeja)
        finally:
            os.close(cerrojo)        # cierra y suelta el flock
        return True
    except Exception:  # noqa: BLE001 — la bandeja es un camino; si falla, la cola avisa por el de siempre
        return False


def _recortar_bandeja(bandeja: Path | None = None) -> None:
    """Que la bandeja no crezca sola: pasado el tope (de líneas o de bytes, que avisos.py no lee por
    encima de su máximo) se reescribe entera con las últimas líneas, por un temporal y `os.replace`, así
    avisos.py ve la vieja completa o la nueva completa. Solo se llama con el cerrojo tomado."""
    bandeja = bandeja or BANDEJA
    tmp = bandeja.with_name(f".{bandeja.name}.{os.getpid()}-{secrets.token_hex(3)}.nuevo")
    try:
        fd = _abrir_regular(bandeja, os.O_RDONLY)
        try:
            with os.fdopen(fd, "rb", closefd=False) as fh:
                crudo = fh.read(BANDEJA_BYTES_TOPE * 4)
        finally:
            os.close(fd)
        lineas = crudo.decode("utf-8", "replace").splitlines()
        if len(lineas) <= BANDEJA_TOPE and len(crudo) <= BANDEJA_BYTES_TOPE:
            return
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644)
        try:
            os.write(fd, ("\n".join(lineas[-BANDEJA_QUEDAN:]) + "\n").encode())
        finally:
            os.close(fd)
        os.replace(tmp, bandeja)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def id_de(salida: str) -> str | None:
    """El id que imprime `nodo-desplegar sugerir|pedir` en su última línea, si es uno."""
    ultima = (salida.strip().splitlines() or [""])[-1].strip()
    return ultima if RE_ID.fullmatch(ultima) else None


# ---------------------------------------------------------------- lectura (pestaña 🔔 Avisos)

def _lineas(ruta: Path) -> tuple[list[dict], int]:
    """(filas, ilegibles) de un .jsonl. Una línea rota no esconde las demás."""
    buenas, malas = [], 0
    try:
        crudo = ruta.read_text(encoding="utf-8")
    except OSError:
        return [], 0
    for ln in crudo.splitlines():
        if not ln.strip():
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            malas += 1
            continue
        if isinstance(d, dict) and isinstance(d.get("momento"), str) and isinstance(d.get("texto"), str):
            buenas.append({k: d.get(k) for k in CLAVES})
        else:
            malas += 1
    return buenas, malas


def _ts(iso: str | None) -> float:
    try:
        m = datetime.fromisoformat(str(iso))
    except ValueError:
        return 0.0
    return (m if m.tzinfo else m.astimezone()).timestamp()


def resultados() -> dict[str, dict]:
    """{id: {estado, momento}} de lo que nodo-desplegar ya cerró. Solo se lee, y sin el `detalle`."""
    out = {}
    try:
        archivos = list(RESULTADOS.glob("*.json"))
    except OSError:
        return out
    for f in archivos:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            momento = datetime.strptime(r["hora"], "%Y-%m-%d %H:%M:%S").astimezone().isoformat(timespec="seconds")
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(r, dict) and RE_ID.fullmatch(str(r.get("id", ""))):
            out[r["id"]] = {"estado": str(r.get("estado") or ""), "momento": momento}
    return out


_NIVEL_RESULTADO = {"aplicado": "ok", "hecho": "ok", "probado": "ok", "sin cambios": "info"}


def de_nodo_desplegar(res: dict[str, dict], ya: set[str]) -> list[dict]:
    """Los pedidos cerrados que nadie registró (los hizo un agente a mano, no una cola)."""
    return [fila("nodo-desplegar", f"Pedido {pid}: {r['estado']}",
                 id=pid, estado=r["estado"], nivel=_NIVEL_RESULTADO.get(r["estado"], "alerta"), momento=r["momento"])
            for pid, r in res.items() if pid not in ya]


def de_noticias() -> list[dict]:
    """Los avisos que el agente de noticias ya mandó. Las notas no entran."""
    out = []
    try:
        crudo = (NOTICIAS / "manifiesto.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        crudo = []
    for ln in crudo:
        try:
            m = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(m, dict) or not isinstance(m.get("telegram"), dict) or m["telegram"].get("ok") is not True:
            continue                    # sin --enviar o con el envío fallido: no hubo aviso
        out.append(fila("noticias", f"📰 Noticias: {m.get('elegidos', '?')} elegidas de {m.get('candidatos', '?')} "
                                    f"candidatas (ventana de {m.get('ventana_horas', '?')} h)",
                        nivel="info", momento=str(m.get("cuando") or "")))
    try:
        con = sqlite3.connect(f"file:{NOTICIAS_DB}?mode=ro", uri=True, timeout=2)
        try:
            filas = con.execute("SELECT titulo, cuando FROM avisados").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        filas = []
    for titulo, cuando in filas:
        out.append(fila("noticias", f"🚨 Noticia importante: {titulo}", nivel="alerta", momento=str(cuando or "")))
    return [x for x in out if _ts(x["momento"])]


def historial(ahora: float | None = None) -> dict:
    ahora = time.time() if ahora is None else ahora
    propias, malas = _lineas(REGISTRO)
    sin_volcar, malas2 = _lineas(PENDIENTE_AVISOS)
    res = resultados()
    todas = propias + sin_volcar
    for a in todas:
        r = res.get(a["id"] or "")
        if a["estado"]:
            continue
        if r:
            a["estado"] = r["estado"]
        elif a["id"] and ahora - _ts(a["momento"]) < RESULTADOS_DIAS * 86400:
            a["estado"] = "pendiente"   # el escucha deja un resultado al cerrar (también al vencer)
    todas += de_nodo_desplegar(res, {a["id"] for a in todas if a["id"]}) + de_noticias()
    todas.sort(key=lambda a: _ts(a["momento"]), reverse=True)
    return {"avisos": todas[:MAX_HISTORIAL], "total": len(todas), "ilegibles": malas + malas2,
            "sin_volcar": len(sin_volcar),
            "pendientes": [a for a in todas if a["estado"] == "pendiente"]}


# ---------------------------------------------------------------- alarmas configuradas

def _fuente(clave: str) -> tuple[Path | None, str, str | None]:
    """(archivo a leer, cómo nombrarlo, nota). Lee el desplegado; si el del vault difiere, lo dice."""
    desplegado, vault = FUENTES[clave]
    leer = lambda p: p.read_bytes() if p.is_file() else None
    try:
        a = leer(desplegado)
    except OSError:
        a = None
    try:
        b = leer(vault)
    except OSError:
        b = None
    if a is None:
        return (vault, f"{vault.name} (vault)", "no pude leer el desplegado") if b is not None else (None, vault.name, "sin datos")
    return desplegado, str(desplegado), ("el del vault es distinto: hay cambios sin desplegar" if b is not None and a != b else None)


def _numero(n: ast.AST) -> float | None:
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
        return n.value
    if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Mult, ast.Add, ast.Sub)):
        a, b = _numero(n.left), _numero(n.right)
        if a is None or b is None:
            return None
        return a * b if isinstance(n.op, ast.Mult) else a + b if isinstance(n.op, ast.Add) else a - b
    return None


def constantes(ruta: Path | None) -> dict[str, float]:
    """Las constantes numéricas de un script, leídas del código SIN ejecutarlo."""
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, AttributeError, ValueError):
        return {}
    out = {}
    for n in arbol.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            v = _numero(n.value)
            if v is not None:
                out[n.targets[0].id] = v
    return out


def _plantilla(n: ast.AST) -> str:
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value
    if isinstance(n, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "…" for v in n.values)
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        return _plantilla(n.left) + _plantilla(n.right)
    return "…"


def reglas(ruta: Path | None, funcion: str) -> list[dict]:
    """[{id, texto, condicion}] de las alertas que arma `funcion`, leídas del código sin ejecutarlo:
    cada add(id, texto) o {"id": …, "texto": …}, con los `if` que lo rodean. Así el umbral que se
    muestra es el que está escrito en el script y no una copia."""
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == funcion)
    except (OSError, SyntaxError, AttributeError, ValueError, StopIteration):
        return []
    out = []

    def hallar(nodo: ast.AST, conds: list[str]) -> None:
        for n in ast.walk(nodo):
            par = None
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "add" and len(n.args) >= 2:
                par = n.args[0], n.args[1]
            elif isinstance(n, ast.Dict):
                d = {k.value: v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant)}
                if "id" in d and "texto" in d:
                    par = d["id"], d["texto"]
            if par:
                out.append({"id": _plantilla(par[0]), "texto": _plantilla(par[1]), "condicion": " y ".join(conds)})

    def andar(sentencias: list[ast.stmt], conds: list[str]) -> None:
        for s in sentencias:
            if isinstance(s, ast.If):
                c = ast.unparse(s.test)
                andar(s.body, conds + [c])
                # Un `elif` se muestra con su propia condición; un `else`, como la negación.
                es_elif = len(s.orelse) == 1 and isinstance(s.orelse[0], ast.If)
                andar(s.orelse, conds if es_elif else conds + [f"no ({c})"])
            elif isinstance(s, (ast.For, ast.While, ast.With, ast.Try)):
                for parte in ("body", "orelse", "finalbody"):
                    andar(getattr(s, parte, []), conds)
                for h in getattr(s, "handlers", []):
                    andar(h.body, conds)
            elif not isinstance(s, (ast.FunctionDef, ast.ClassDef)):
                hallar(s, conds)

    andar(fn.body, [])
    return out


def _cuentas() -> tuple[dict, str]:
    for r in CUENTAS:
        try:
            return tomllib.loads(r.read_text(encoding="utf-8")), str(r)
        except (OSError, tomllib.TOMLDecodeError):
            continue
    return {}, ""


def _entero(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 100


def alarmas() -> list[dict]:
    """Cada alarma con su umbral y su fuente. Nada se copia acá: el umbral se lee de donde vive."""
    out = []

    def poner(grupo, alarma, umbral, fuente, ahora=None, nota=None, **extra):
        out.append({"grupo": grupo, "alarma": alarma, "umbral": umbral, "fuente": fuente, "ahora": ahora, "nota": nota, **extra})

    # Cuota: los mismos umbral_semanal y umbral_5h que muestra y edita 💳 Cuentas.
    ruta_avisos, nombre_avisos, nota_avisos = _fuente("avisos")
    k = constantes(ruta_avisos)
    margen = k.get("MARGEN_CUOTA")
    cuentas, ruta_cuentas = _cuentas()
    try:
        uso = json.loads(USO.read_text(encoding="utf-8"))["cuentas_interactivo"]
    except (OSError, ValueError, KeyError, TypeError):
        uso = {}
    for cid, c in cuentas.items():
        if not isinstance(c, dict) or not (_entero(c.get("umbral_semanal")) or _entero(c.get("umbral_5h"))):
            continue
        for campo, ventana, etiqueta, aviso_campo in (("umbral_semanal", "semanal", "semanal", "aviso_semanal"),
                                                      ("umbral_5h", "ventana_5h", "ventana de 5 h", "aviso_5h")):
            if not _entero(c.get(campo)):
                continue
            aviso = c.get(aviso_campo) if _entero(c.get(aviso_campo)) and c[aviso_campo] < c[campo] else None
            pct = (((uso.get(cid) or {}).get("limites") or {}).get(ventana) or {}).get("usado_pct")
            # Una sola fila por tope: el aviso (tope − margen) y la espera de las colas salen del mismo número.
            poner("Cuota", f"{c.get('nombre') or cid} · {etiqueta}",
                  (f"avisa al {c[campo] - margen:g} % (tope {c[campo]} % − {margen:g})" if margen is not None
                   else f"tope {c[campo]} %") + f"; desde el {c[campo]} % las colas esperan o se pausan",
                  f"{ruta_cuentas} · {campo} (el de 💳 Cuentas); el margen, {nombre_avisos} · MARGEN_CUOTA",
                  f"{pct:g} %" if isinstance(pct, (int, float)) else None,
                  nota_avisos if margen is not None else "la alarma de cuota de avisos.py todavía no está desplegada",
                  # Para editar el aviso previo desde la pestaña (encargo 24): propuesta `registro_cuentas`.
                  cuenta=cid, tope=c[campo], aviso=aviso, aviso_campo=aviso_campo,
                  aviso_previo=(f"avisa al {aviso} % solo si una cola activa usa la cuenta" if aviso is not None
                                else "sin aviso previo (se pone desde acá)"))
    try:
        modelos = tomllib.loads((D / "encargos/modelos.toml").read_text(encoding="utf-8"))
        espera = (modelos.get("autorizacion") or {}).get("espera_max_min")
        if espera is not None:
            poner("Colas", "Modelo con candado sin autorizar: la cola no corre", f"{espera} min",
                  "encargos/modelos.toml · [autorizacion] espera_max_min")
    except (OSError, tomllib.TOMLDecodeError):
        pass

    # Nodo: las alertas que calcula estado.py y empuja avisos.py, cuando aparecen y cuando se resuelven.
    for clave, funcion in (("estado", "alertas"), ("avisos", "alertas_actuales")):
        ruta, nombre, nota = _fuente(clave)
        for r in reglas(ruta, funcion):
            poner("Nodo", f"{r['id']}: {r['texto']}", r["condicion"] or "siempre que se llegue a ese punto",
                  f"{nombre} · {funcion}()", nota=nota)
    if "MAX_ANTIGUEDAD_S" in k:
        poner("Nodo", "estado.json viejo no se lee como bueno", f"{k['MAX_ANTIGUEDAD_S'] / 60:g} min sin actualizar",
              f"{nombre_avisos} · MAX_ANTIGUEDAD_S", nota=nota_avisos)

    # Despliegue: un pedido o una línea sugerida sin respuesta.
    ruta, nombre, nota = _fuente("nodo-desplegar")
    vence = constantes(ruta).get("VENCE_S")
    if vence is not None:
        poner("Despliegue", "Pedido o línea sugerida sin ✅: vence", f"{vence / 60:g} min", f"{nombre} · VENCE_S", nota=nota)

    # Noticias: el aviso inmediato del agente.
    try:
        u = json.loads((NOTICIAS / "_operacion.json").read_text(encoding="utf-8"))["vigente"]["urgente"]
        silencio = u.get("silencio") or []
        poner("Noticias", "Noticia importante" + ("" if u.get("activo") else " (apagada)"),
              f"puntaje ≥ {u.get('umbral')}; hasta {u.get('tope_diario')} al día"
              + (f"; en silencio de {silencio[0]} a {silencio[1]}" if len(silencio) == 2 else ""),
              "13-Agente-Noticias/_operacion.json · vigente.urgente (se edita en 📰 Noticias)")
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        pass
    return out


def asegurar() -> None:
    """Deja creado el registro vacío (0664). avisos.py no puede crear archivos en /opt/nodo/datos:
    entra por el grupo y solo agrega a uno que ya exista."""
    try:
        if not REGISTRO.exists() and (not _dentro_del_volumen(REGISTRO) or os.path.ismount(VOLUMEN)):
            os.close(_abrir(REGISTRO))
    except OSError:
        pass


def panel() -> dict:
    asegurar()
    return dict(historial(), alarmas=alarmas(), registro=str(REGISTRO), niveles=list(NIVELES))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--panel", action="store_true")
    a = ap.parse_args()
    if not a.panel:
        ap.error("falta --panel")
    print(json.dumps(panel(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
