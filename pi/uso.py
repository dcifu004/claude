#!/usr/bin/env python3
"""
Uso de tokens de los agentes en el nodo Pi5Diego.

    uso              texto para la terminal
    uso --telegram   lo mismo, es el que manda el comando /uso del bot
    uso --json       todo en JSON
    uso --escribir   deja el JSON en /opt/nodo/datos/uso.json (lo corre el timer)

ALCANCE, y va en TODAS las salidas: mide solo las sesiones corridas EN ESTA PI
con la cuenta dcifu004. El uso de tokens es por cuenta, no por maquina, y
tambien se corren agentes en PC-2503, en el notebook y desde el telefono. Un
numero de aca es una PORCION del consumo real, y presentarlo sin decirlo seria
justo el modo de falla que este proyecto persigue: una salida que se ve
completa mintiendo por omision.

LA CUOTA RESTANTE NO SE PUEDE LEER. Claude Code no la expone en ningun lado:
no esta en las metricas OTEL, ni en los eventos, ni en archivos, ni en
variables de entorno. Solo la muestra /usage dentro de una sesion interactiva.
Asi que esto informa CONSUMO y nunca "cuanto queda", y lo dice explicitamente
para que nadie lo venga a buscar aca.

UNA SOLA FUNCION DE FORMATO. estado.py tiene tres y su propio comentario
advierte que con el tiempo se separan; aca la terminal y Telegram salen de la
misma, que es la unica forma de que no puedan divergir.

Se instala en /usr/local/bin/uso y vive versionado en pi/uso.py.
"""

import datetime as dt
import glob
import json
import os
import secrets
import socket
import stat
import subprocess
import sys
import zoneinfo

try:
    # Windows does not ship the IANA database. On the two PCs its system zone is
    # Santiago, so the fallback is its local offset without needing tzdata.
    TZ = zoneinfo.ZoneInfo("America/Santiago")
    TZ_ES_LOCAL = False
except zoneinfo.ZoneInfoNotFoundError:
    TZ = dt.datetime.now().astimezone().tzinfo
    TZ_ES_LOCAL = True
CUENTA = "dcifu004"
CLAUDE_PROYECTOS = f"/home/{CUENTA}/.claude/projects"
CODEX_HOME = "/opt/nodo/datos/agentes/codex-home"
SALIDA = "/opt/nodo/datos/uso.json"
REFRESCOS_LIMITES = "/opt/nodo/datos/uso-limites-refresco.json"
REFRESCO_LIMITES_MINUTOS = 10
USO_EQUIPOS = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/uso-equipos"


def _vacio():
    return {"entrada": 0, "salida": 0, "cache_lectura": 0, "cache_escritura": 0,
            "pensamiento": 0, "mensajes": 0, "modelos": {}}


def _sumar(acc, u, modelo):
    acc["entrada"] += u.get("input_tokens") or 0
    acc["salida"] += u.get("output_tokens") or 0
    acc["cache_lectura"] += u.get("cache_read_input_tokens") or 0
    acc["cache_escritura"] += u.get("cache_creation_input_tokens") or 0
    det = u.get("output_tokens_details") or {}
    acc["pensamiento"] += det.get("thinking_tokens") or 0
    acc["mensajes"] += 1
    acc["modelos"][modelo] = acc["modelos"].get(modelo, 0) + 1


# --------------------------------------------------------------- claude

def claude_uso():
    """Suma el `usage` de los transcripts por ventana de tiempo.

    Dos decisiones que cambian el resultado y no son obvias:

    - SE DEDUPLICA POR requestId. Un `--resume`, un fork o un /compact copian
      mensajes viejos al transcript nuevo. Sin deduplicar, cada reanudacion
      infla el total con trafico que se pago una sola vez.
    - NO se suma todo en un numero unico. En un mensaje real de esta Pi habia 2
      tokens de entrada y 34.809 de lectura de cache: un total quedaria
      dominado por el cache y dejaria de significar nada. Las cuatro categorias
      van separadas a proposito.

    El formato del transcript es interno de Claude Code, no una API publica: si
    una version cambia los nombres de los campos, esto queda en cero SIN dar
    error. De ahi que la salida muestre siempre el conteo de mensajes — un cero
    ahi es la senal de que hay que volver a mirar el formato.
    """
    hoy = dt.datetime.now(TZ).date()
    r = {"disponible": os.path.isdir(CLAUDE_PROYECTOS), "hoy": _vacio(),
         "semana": _vacio(), "total": _vacio(), "sidechain_mensajes": 0,
         "transcripts": 0, "desde": None}
    if not r["disponible"]:
        r["razon"] = f"no existe {CLAUDE_PROYECTOS}"
        return r

    vistos = set()
    desde = None
    archivos = glob.glob(os.path.join(CLAUDE_PROYECTOS, "*", "*.jsonl"))
    r["transcripts"] = len(archivos)
    for ruta in archivos:
        try:
            fh = open(ruta, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for ln in fh:
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                if d.get("type") != "assistant":
                    continue
                m = d.get("message") or {}
                u = m.get("usage")
                if not isinstance(u, dict):
                    continue
                clave = d.get("requestId") or d.get("uuid")
                if clave in vistos:
                    continue
                vistos.add(clave)

                modelo = m.get("model") or "?"
                if d.get("isSidechain"):
                    r["sidechain_mensajes"] += 1
                _sumar(r["total"], u, modelo)

                # El timestamp viene en UTC con Z. La ventana "hoy" es el dia
                # de Diego, no el de Greenwich: en Santiago son 3-4 h de
                # diferencia, o sea todo lo trabajado de noche caeria en el dia
                # siguiente y "hoy" arrancaria mintiendo.
                try:
                    f = dt.datetime.fromisoformat(
                        (d.get("timestamp") or "").replace("Z", "+00:00")
                    ).astimezone(TZ).date()
                except ValueError:
                    continue
                if desde is None or f < desde:
                    desde = f
                if f == hoy:
                    _sumar(r["hoy"], u, modelo)
                if 0 <= (hoy - f).days < 7:
                    _sumar(r["semana"], u, modelo)

    r["desde"] = desde.isoformat() if desde else None
    return r


# --------------------------------------------------------------- codex

def codex_uso():
    """Estructura lista, sin datos todavia — a proposito.

    Codex no expone consumo: `codex --help` no tiene subcomando de uso ni de
    costo (si tiene `doctor`, que es salud de la instalacion). En el codex-home
    hay sqlite —logs_2.sqlite, queue_1.sqlite, goals_1.sqlite— que PODRIAN
    tener contadores, pero al 2026-09-09 nadie los abrio, y no se va a afirmar
    lo que no se verifico: un numero inventado aca es peor que un "sin datos".

    Cuando se verifique, se rellena esta funcion con las mismas claves que
    devuelve claude_uso() y las salidas lo muestran solas, sin tocar el formato.
    """
    return {
        "disponible": False,
        "razon": "Codex no expone consumo por CLI; las sqlite del codex-home "
                 "estan sin verificar",
        "home": CODEX_HOME if os.path.isdir(CODEX_HOME) else None,
    }


# ------------------------------------------ por cuenta y por hora (30-09-2026)
# Para el historial de las 3 cuentas pagadas (pagina 🤖 → 💳 Cuentas): el consumo
# interactivo de ESTA Pi en baldes de una hora, por cuenta, para que bots-info lo corte
# en los ciclos semanales de renovacion de cada una. Las consultas de los bots NO
# estan aca (corren con --no-session-persistence / --ephemeral): van en su propio
# libro, uso-cuentas.jsonl, y por eso no se cuentan dos veces.

CLAUDE_POR_CUENTA = {
    "claude_diego": CLAUDE_PROYECTOS,
    "claude_cami": f"/home/{CUENTA}/.config/claude-cami/projects",
}
CLAUDE_LIMITES = {
    "claude_diego": {"cuenta": "claude_diego", "archivo": f"/home/{CUENTA}/.claude.json"},
    "claude_cami": {"cuenta": "claude_cami",
                     "archivo": f"/home/{CUENTA}/.config/claude-cami/.claude.json",
                     "config_dir": f"/home/{CUENTA}/.config/claude-cami"},
}
CODEX_SESIONES = [f"/home/{CUENTA}/.codex/sessions", f"{CODEX_HOME}/sessions"]


def _hora(ts):
    """Balde local 'YYYY-MM-DDTHH', o None si el timestamp no se entiende."""
    try:
        return dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00")) \
            .astimezone(TZ).strftime("%Y-%m-%dT%H")
    except ValueError:
        return None


def _balde(por_hora, hora):
    return por_hora.setdefault(hora, {"entrada": 0, "salida": 0, "cache_lectura": 0,
                                      "cache_escritura": 0, "mensajes": 0})


def _leer_json(ruta):
    """Lee una vez más: Claude puede estar reemplazando su caché justo ahora."""
    for _ in range(2):
        try:
            with open(ruta, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            pass
    return None


def _refrescos(ruta):
    datos = _leer_json(ruta)
    return datos if isinstance(datos, dict) else {}


def escribir_seguro(ruta, texto, modo=0o644):
    """Deja `texto` en `ruta` sin que root siga nunca un enlace puesto por dcifu004.

    /opt/nodo/datos es de dcifu004: con `> .estado.tmp && mv` o un open() comun, un symlink
    (o un hard link) en el temporal o en el destino manda la escritura de root a cualquier
    archivo del sistema (Hueco 1, doc 23; encargo 27). Aca: la carpeta se recorre desde /
    con O_NOFOLLOW en cada componente; el temporal es nuevo (O_CREAT|O_EXCL|O_NOFOLLOW, nombre
    al azar), asi que uno plantado de antemano no se usa; y el destino NUNCA se abre: el
    rename lo reemplaza como nombre, sin seguirlo ni tocar lo que apunte. Si el destino
    existente no es un archivo comun, con un solo nombre y de quien escribe, se deja en
    stderr (el log de la unidad) y se reemplaza igual. Atomico: el bot nunca lee a medias.
    """
    carpeta, base = os.path.split(ruta)
    dfd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for parte in [p for p in carpeta.split("/") if p]:
            if parte in (".", ".."):
                raise OSError(f"ruta con {parte!r}: {carpeta}")
            sig = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dfd)
            os.close(dfd)
            dfd = sig
        for nombre in (base, base + ".tmp", "." + base + ".tmp"):
            try:
                st = os.stat(nombre, dir_fd=dfd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or st.st_uid != os.geteuid()):
                print(f"aviso: {carpeta}/{nombre} no es un archivo comun, tiene otros "
                      f"enlaces o no es de uid {os.geteuid()}; no se sigue, "
                      f"{'se reemplaza' if nombre == base else 'se ignora'}", file=sys.stderr)
        tmp = f".{base}.{secrets.token_hex(8)}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                     dir_fd=dfd)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(texto)
                fh.flush()
                os.fchmod(fh.fileno(), modo)   # el bot y Cockpit leen sin ser root
                os.fsync(fh.fileno())
            os.replace(tmp, base, src_dir_fd=dfd, dst_dir_fd=dfd)
        except BaseException:
            try:
                os.unlink(tmp, dir_fd=dfd)
            except OSError:
                pass
            raise
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _guardar_refrescos(ruta, datos):
    """Sólo guarda horas de intento, dentro del volumen cifrado."""
    try:
        escribir_seguro(ruta, json.dumps(datos))
    except OSError as err:
        print(f"no guardo {ruta}: {err}", file=sys.stderr)


def _refrescar_limite_claude(config):
    """Pide al CLI que actualice su caché, como el dueño de la sesión.

    La respuesta humana de /usage se descarta: el dato que se publica es la
    caché JSON que el CLI acaba de actualizar. Un fallo conserva la caché previa.
    """
    ruta_refrescos = config.get("refrescos", REFRESCOS_LIMITES)
    cuenta = config["cuenta"]
    ahora = dt.datetime.now(dt.timezone.utc).timestamp()
    marcas = _refrescos(ruta_refrescos)
    try:
        reciente = float(marcas.get(cuenta, 0))
    except (TypeError, ValueError):
        reciente = 0
    if ahora - reciente < REFRESCO_LIMITES_MINUTOS * 60:
        return

    # Se registra incluso un fallo para no golpear el CLI en cada tick del timer.
    marcas[cuenta] = ahora
    _guardar_refrescos(ruta_refrescos, marcas)
    env = [f"HOME=/home/{CUENTA}"]
    if config.get("config_dir"):
        env.append(f"CLAUDE_CONFIG_DIR={config['config_dir']}")
    comando = ["env", *env, "claude", "-p", "/usage", "--no-session-persistence",
               "--output-format", "json"]
    try:
        # pwd and geteuid are POSIX-only. Importing this shared module must work
        # for the Windows reader even though this refresh branch is Pi-only.
        import pwd
        if os.geteuid() != pwd.getpwnam(CUENTA).pw_uid:
            comando = ["runuser", "-u", CUENTA, "--", *comando]
        subprocess.run(comando, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired, KeyError):
        pass


def _iso_santiago(valor):
    try:
        return dt.datetime.fromtimestamp(float(valor) / 1000, TZ).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _limite_claude(utilizacion, directo, kind):
    dato = utilizacion.get(directo) if isinstance(utilizacion, dict) else None
    if not isinstance(dato, dict):
        dato = next((x for x in (utilizacion.get("limits") or [])
                     if isinstance(x, dict) and x.get("kind") == kind), {}) \
            if isinstance(utilizacion, dict) else {}
        return {"usado_pct": dato.get("percent"), "renueva": dato.get("resets_at")}
    return {"usado_pct": dato.get("utilization"), "renueva": dato.get("resets_at")}


def limites_claude(config):
    """Límites de una cuenta Claude desde su caché, o None si no hay dato útil."""
    _refrescar_limite_claude(config)
    datos = _leer_json(config["archivo"])
    return limites_claude_cache(datos)


def limites_claude_cache(datos):
    """Normaliza una caché ya leída; el lector de PC no debe invocar el CLI."""
    cache = (datos or {}).get("cachedUsageUtilization")
    if not isinstance(cache, dict):
        return None
    utilizacion = cache.get("utilization") or {}
    cuenta = (datos or {}).get("oauthAccount") or {}
    return {"momento": _iso_santiago(cache.get("fetchedAtMs")),
            "plan": cuenta.get("subscriptionType") or datos.get("subscriptionType"),
            "ventana_5h": _limite_claude(utilizacion, "five_hour", "session"),
            "semanal": _limite_claude(utilizacion, "seven_day", "weekly_all")}


def claude_por_hora(proyectos):
    """Mismo recorrido y misma deduplicacion por requestId que claude_uso()."""
    por_hora, vistos = {}, set()
    for ruta in glob.glob(os.path.join(proyectos, "*", "*.jsonl")):
        try:
            fh = open(ruta, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for ln in fh:
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                u = (d.get("message") or {}).get("usage") if d.get("type") == "assistant" else None
                clave = d.get("requestId") or d.get("uuid")
                hora = _hora(d.get("timestamp"))
                if not isinstance(u, dict) or clave in vistos or not hora:
                    continue
                vistos.add(clave)
                b = _balde(por_hora, hora)
                b["entrada"] += u.get("input_tokens") or 0
                b["salida"] += u.get("output_tokens") or 0
                b["cache_lectura"] += u.get("cache_read_input_tokens") or 0
                b["cache_escritura"] += u.get("cache_creation_input_tokens") or 0
                b["mensajes"] += 1
    return por_hora


def _limites_codex(rate_limits, momento):
    """Normaliza los limites de cuenta que Codex deja en un token_count.

    `resets_at` viene como epoch UTC; la pagina y los ciclos trabajan con la
    hora de Diego, por eso se transforma aqui y no se deja al navegador adivinar
    una zona horaria.
    """
    def ventana(nombre):
        limite = rate_limits.get(nombre) or {}
        try:
            renueva = dt.datetime.fromtimestamp(limite["resets_at"], TZ) \
                .isoformat(timespec="seconds")
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            renueva = None
        return {"usado_pct": limite.get("used_percent"), "renueva": renueva}

    return {"momento": momento.isoformat(timespec="seconds"),
            "plan": rate_limits.get("plan_type"),
            "ventana_5h": ventana("primary"), "semanal": ventana("secondary")}


def codex_por_hora(carpetas, incluir_limites=False):
    """Los rollout-*.jsonl de las sesiones interactivas de Codex traen eventos
    `token_count` con el total ACUMULADO de la sesion (verificado el 30-09-2026 en
    codex-cli 0.154). Se suma la diferencia entre eventos seguidos, en la hora del
    evento: sumar `last_token_usage` contaria dos veces un turno que se reemite."""
    por_hora, limites, limite_momento = {}, None, None
    for base in carpetas:
        for ruta in glob.glob(os.path.join(base, "**", "rollout-*.jsonl"), recursive=True):
            previo = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
            try:
                fh = open(ruta, encoding="utf-8", errors="replace")
            except OSError:
                continue
            with fh:
                for ln in fh:
                    if '"token_count"' not in ln:
                        continue
                    try:
                        d = json.loads(ln)
                    except ValueError:
                        continue
                    momento_texto = d.get("timestamp") or ""
                    try:
                        momento = dt.datetime.fromisoformat(
                            momento_texto.replace("Z", "+00:00")).astimezone(TZ)
                    except ValueError:
                        continue
                    payload = d.get("payload") or {}
                    rate_limits = payload.get("rate_limits")
                    if isinstance(rate_limits, dict) and (limite_momento is None or momento > limite_momento):
                        limites, limite_momento = _limites_codex(rate_limits, momento), momento
                    info = payload.get("info") or {}
                    total = info.get("total_token_usage")
                    hora = _hora(momento_texto)
                    if not isinstance(total, dict) or not hora:
                        continue
                    if d.get("_uso_equipo_prelude"):
                        previo = {k: total.get(k) or 0 for k in previo}
                        continue
                    delta = {k: max(0, (total.get(k) or 0) - previo[k]) for k in previo}
                    previo = {k: total.get(k) or 0 for k in previo}
                    if not any(delta.values()):
                        continue
                    b = _balde(por_hora, hora)
                    b["entrada"] += delta["input_tokens"] - min(delta["input_tokens"],
                                                                delta["cached_input_tokens"])
                    b["cache_lectura"] += delta["cached_input_tokens"]
                    b["salida"] += delta["output_tokens"]
                    b["mensajes"] += 1
    if incluir_limites:
        return {"por_hora": por_hora, "limites": limites}
    return por_hora


def cuentas_interactivo():
    r = {c: {"disponible": os.path.isdir(d), "por_hora": claude_por_hora(d),
             "limites": limites_claude(CLAUDE_LIMITES[c])}
         for c, d in CLAUDE_POR_CUENTA.items()}
    codex = codex_por_hora(CODEX_SESIONES, incluir_limites=True)
    r["codex"] = {"disponible": any(os.path.isdir(d) for d in CODEX_SESIONES), **codex}
    return r


def equipos_uso(ahora=None):
    """Reportes agregados de Windows. Nunca abre transcripts ni archivos de login.

    Un reporte viejo se conserva sólo como diagnóstico: no entra al costo ni a los
    límites, porque hacerlo haría que un PC apagado pareciera estar reportando.
    """
    ahora = ahora or dt.datetime.now(TZ)
    activos, vencidos = {}, {}
    for ruta in glob.glob(os.path.join(USO_EQUIPOS, "*.json")):
        dato = _leer_json(ruta)
        if not isinstance(dato, dict) or not isinstance(dato.get("cuentas"), dict):
            continue
        equipo = os.path.splitext(os.path.basename(ruta))[0]
        try:
            actualizado = dt.datetime.fromisoformat(dato["actualizado"]).astimezone(TZ)
        except (KeyError, TypeError, ValueError):
            vencidos[equipo] = None
            continue
        destino = activos if ahora - actualizado <= dt.timedelta(days=3) else vencidos
        destino[equipo] = {"actualizado": actualizado.isoformat(timespec="seconds"),
                           "cuentas": dato["cuentas"]} if destino is activos else actualizado.isoformat(timespec="seconds")
    return {"activos": activos, "vencidos": vencidos}


# --------------------------------------------------------------- salida

def h(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def texto(d):
    L = ["USO DE TOKENS",
         f"cuenta {d['cuenta']} · {d['host']} · {d['momento'][5:16].replace('T', ' ')}",
         "⚠️ SOLO las sesiones de esta Pi — no es el",
         "total de la cuenta (tambien corres agentes",
         "en el notebook y en PC-2503)."]

    c = d["claude"]
    L += ["", "CLAUDE CODE"]
    if not c["disponible"]:
        L.append(f" ⚪ sin datos: {c.get('razon', '?')}")
    else:
        for etiq, k in (("hoy", "hoy"), ("7 dias", "semana"), ("todo", "total")):
            v = c[k]
            if not v["mensajes"]:
                L.append(f" {etiq:<7} sin actividad")
                continue
            L.append(f" {etiq:<7} {h(v['entrada'])} entrada · "
                     f"{h(v['salida'])} salida · {v['mensajes']} msj")
            L.append(f"         cache: {h(v['cache_lectura'])} leido · "
                     f"{h(v['cache_escritura'])} escrito")
        mods = c["total"]["modelos"]
        if mods:
            L.append(" modelos: " + ", ".join(
                f"{k} ({v})" for k, v in sorted(mods.items(), key=lambda x: -x[1])))
        if c["sidechain_mensajes"]:
            L.append(f" incluye {c['sidechain_mensajes']} msj de subagentes")
        if c["desde"]:
            L.append(f" desde {c['desde']} · {c['transcripts']} transcripts")

    x = d["codex"]
    L += ["", "CODEX"]
    if x["disponible"]:
        for etiq, k in (("hoy", "hoy"), ("7 dias", "semana"), ("todo", "total")):
            v = x[k]
            L.append(f" {etiq:<7} {h(v['entrada'])} entrada · "
                     f"{h(v['salida'])} salida · {v['mensajes']} msj")
    else:
        L.append(" ⚪ sin datos")
        L.append(f"    {x['razon']}")

    L += ["", "La CUOTA restante no se puede leer desde",
          "aca: solo la muestra /usage adentro de una",
          "sesion interactiva. Esto es consumo."]
    return "\n".join(L)


def escribir(d):
    """Atomico: si la Pi se corta a mitad de escritura, el bot lee el anterior
    entero y no un JSON truncado que lo haria responder un error. 644 porque el
    timer corre como root y el bot como otro usuario: sin eso el bot responderia
    "no pude leer el uso" por permisos y no por falta de datos."""
    escribir_seguro(SALIDA, json.dumps(d, indent=1, default=str))


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    datos = {"cuenta": CUENTA, "host": socket.gethostname(),
             "momento": dt.datetime.now(TZ).isoformat(timespec="seconds"),
             "claude": claude_uso(), "codex": codex_uso(),
             "cuentas_interactivo": cuentas_interactivo(), "equipos": equipos_uso()}
    # El texto va YA FORMATEADO dentro del JSON: si el bot lo rearmara por su
    # cuenta habria dos formatos que se separan con el tiempo. Mismo criterio
    # que estado.py.
    datos["_telegram"] = texto(datos)

    if modo == "--json":
        print(json.dumps(datos, indent=1, default=str))
    elif modo == "--escribir":
        escribir(datos)
    else:
        print(datos["_telegram"])
