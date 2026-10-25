#!/usr/bin/env python3
"""
Estado del nodo Pi5Diego.

    estado            panel completo con colores y barras (para la terminal)
    estado --breve    seis lineas en texto plano (para Telegram)
    estado --json     todo en JSON (lo consume el bot y el timer)
    estado --ahora    recolecta EN VIVO en vez de leer el cache. Necesita root:
                      pide la contrasena de sudo.
    estado --escribir recolecta EN VIVO y deja el JSON en /opt/nodo/datos/estado.json.
                      Solo root; lo usa estado.service (ya no hay `sh -c` ni `mv`).

DE DONDE SALEN LOS DATOS. Por defecto NO se recolecta nada: se lee el
/opt/nodo/datos/estado.json que estado.timer deja cada 5 minutos corriendo como
root, y se muestra su antigüedad. Recolectar exige root —restic.pass, el socket
de Docker, smartctl— y antes de esto el script se elevaba solo con `sudo -n`, lo
que obligaba a un NOPASSWD sobre el interprete: `sudo python3 <cualquier cosa>`,
o sea root entero por la puerta de atras. Leer un archivo de 644 no necesita
nada. Ver `16 - Plan de seguridad y acceso` (Hueco 1, paso 3).

UNA SOLA FUENTE DE VERDAD. El panel, el resumen de Telegram y los avisos por
umbral salen todos de la misma recoleccion. Con dos recolectores distintos, en
tres meses el panel y el bot dicen cosas distintas y no hay forma de saber cual
miente.

Se instala en /usr/local/bin/estado y vive versionado en pi/estado.py.
"""

import colorsys
import datetime as dt
import glob
import json
import os
import pwd
import re
import secrets
import stat
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

DATOS = "/opt/nodo/datos"
RESPALDO = "/mnt/respaldo"
COMPOSE = "/opt/nodo/compose.yml"
SYNC_CFG = f"{DATOS}/srv/config/config.xml"
BOT_ESTADO = f"{DATOS}/captura/estado.json"
REPO = f"{RESPALDO}/restic"
PASS = f"{DATOS}/secretos/restic.pass"

# La salud del emisor de avisos, que vive FUERA del cifrado igual que el emisor.
# Esta ruta es el segundo camino del nodo: cuando el canal push muere no puede
# contar que murio —el que avisa es el que se cayo—, asi que lo cuenta /estado,
# que sale por otro bot, con otro token y otro proceso. Ver avisos.py, punto 7.
SALUD_AVISOS = "/var/lib/nodo/avisos-salud.json"

# El cache que deja estado.timer cada 5 min, corriendo como root. 644 a proposito
# (lo pone el ExecStart): lo leen este script sin privilegios y el bot.
CACHE = f"{DATOS}/estado.json"

# Un JSON mas viejo que esto NO se muestra como bueno. Un archivo viejo miente
# peor que uno ausente: el panel saldria en verde describiendo un nodo de hace
# horas. Pasada esa edad, la antigüedad ES la alerta. Misma regla que avisos.py.
MAX_EDAD_MIN = 20

# Lo que `luces` anota cada vez que cambia las luces del ventilador.
# Es la UNICA fuente del color: los WS2812 no se pueden leer.
LUCES = "/home/dcifu004/.local/state/nodo/luces.json"
LUCES_REGLAS = "/home/dcifu004/.config/nodo/luces-reglas.json"
LUCES_SENAL = "/home/dcifu004/.local/state/nodo/luces-senal.json"
# Se deriva de los EnvironmentFile y User reales de botv3@*.service: Jaime
# conserva el STATE_DIR histórico /botv3 y Pilar corre como botpilar.
CATALOGOS_MODELOS = {
    "jaime": {"ruta": f"{DATOS}/botv3/modelos-catalogo.json", "dueno": "dcifu004"},
    "pilar": {"ruta": f"{DATOS}/botv3-pilar/modelos-catalogo.json", "dueno": "botpilar"},
}
MAX_CATALOGO_MODELOS = 128 * 1024
CATALOGO_VIEJO_S = 48 * 3600


def sh(cmd, **kw):
    """Ejecuta y devuelve stdout limpio, o '' si algo falla."""
    try:
        return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                              text=True, timeout=kw.get("t", 15)).stdout.strip()
    except Exception:
        return ""


def num(s, default=None):
    m = re.search(r"-?\d+(\.\d+)?", s or "")
    return float(m.group()) if m else default


def _leer_catalogo_modelos(ruta: str, dueno: str):
    """Archivo de botv3: regular, del dueño esperado, acotado y sin symlinks."""
    try:
        uid = pwd.getpwnam(dueno).pw_uid; fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError: return None
    except (KeyError, OSError): return False
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != uid or st.st_size > MAX_CATALOGO_MODELOS: return False
        with os.fdopen(fd, "rb", closefd=False) as fh: bruto = fh.read(MAX_CATALOGO_MODELOS + 1)
        dato = json.loads(bruto.decode("utf-8"))
        return dato if len(bruto) <= MAX_CATALOGO_MODELOS and isinstance(dato, dict) else False
    except (OSError, UnicodeError, ValueError): return False
    finally: os.close(fd)


def alertas_catalogo_modelos(ahora=None):
    ahora, salida = ahora or dt.datetime.now().astimezone(), []
    for perfil, ficha_catalogo in CATALOGOS_MODELOS.items():
        # La estructura se valida antes de abrir: este módulo corre como root.
        if not isinstance(ficha_catalogo, dict):
            continue
        ruta, dueno = ficha_catalogo.get("ruta"), ficha_catalogo.get("dueno")
        if not isinstance(ruta, str) or not isinstance(dueno, str):
            continue
        dato = _leer_catalogo_modelos(ruta, dueno)
        if dato is None: continue
        if dato is False:
            salida.append({"id": f"modelo:ilegible:{perfil}",
                           "texto": f"centinela ilegible para modelos de {perfil.capitalize()}"})
            continue
        try: momento = dt.datetime.fromisoformat(dato["momento"]).astimezone(ahora.tzinfo); edad = (ahora - momento).total_seconds()
        except (KeyError, TypeError, ValueError, OverflowError):
            salida.append({"id": f"modelo:ilegible:{perfil}",
                           "texto": f"centinela ilegible para modelos de {perfil.capitalize()}"})
            continue
        if edad > CATALOGO_VIEJO_S:
            salida.append({"id": f"modelo:centinela:{perfil}", "texto": f"centinela detenido para modelos de {perfil.capitalize()} hace {edad / 3600:.0f} h"})
        filas = dato.get("modelos")
        if not isinstance(filas, list):
            salida.append({"id": f"modelo:ilegible:{perfil}",
                           "texto": f"centinela ilegible para modelos de {perfil.capitalize()}"})
            continue
        sin_dato = {}
        for fila in filas:
            if not isinstance(fila, dict): continue
            proveedor, modelo, rol, estado = (fila.get(k) for k in ("proveedor", "modelo", "rol", "estado"))
            if not all(isinstance(x, str) and 0 < len(x) <= 200 and x.isprintable() and "\n" not in x and "\r" not in x for x in (proveedor, modelo, rol, estado)): continue
            if estado == "ausente": salida.append({"id": f"modelo:{proveedor}:{modelo}", "texto": f"{proveedor.capitalize()} ya no ofrece `{modelo}` (ruta {rol.lower()} de {perfil.capitalize()}): el bot va a fallar en esa ruta"})
            elif estado == "sin_dato": sin_dato.setdefault(proveedor, []).append(fila.get("sin_dato_desde"))
        for proveedor, fechas in sin_dato.items():
            try: desde = min(dt.datetime.fromisoformat(x).astimezone(ahora.tzinfo) for x in fechas if isinstance(x, str))
            except (TypeError, ValueError, OverflowError): continue
            if (ahora - desde).total_seconds() > 3 * 86400: salida.append({"id": f"modelo:sin_dato:{perfil}:{proveedor}", "texto": f"no se pudo revisar el catálogo de {proveedor.capitalize()} desde {desde:%d-%m-%Y}"})
    # El id de ausencia es proveedor:modelo (sin perfil) por contrato: si ambos
    # perfiles usan el mismo modelo, un solo aviso basta y se resuelve junto.
    unicas = {}
    for alerta in salida:
        unicas.setdefault(alerta["id"], alerta)
    return list(unicas.values())


# ------------------------------------------------------------- auditor de rutas
# Encargo 94 (25-10-2026). Vigila perfil → ruta → cuenta en el `uso-cuentas.jsonl` de cada
# bot y avisa cuando aparece una combinación que lo desplegado no autoriza. Solo lee. La
# lista blanca NO se escribe acá: sale en cada corrida de `rutas` y `cuentas` del perfil
# desplegado, pasadas por `recetas.cadena_efectiva` (los mismos muros que aplica el bot).
# Si una propuesta aprobada cambia el perfil, la lista cambia con él.
# Dedup: los id son estables y avisos.py ya compara por id. Un hallazgo sigue activo
# mientras tenga líneas dentro de la ventana y se resuelve solo cuando sale de ella.
BOT_DIR = "/opt/botv3"
MAX_REGISTRO_USO = 4 * 1024 * 1024
VENTANA_RUTAS_S = 7 * 86400
VENTANA_MUERTA_S = 24 * 3600
FALLAS_MUERTA = 3
MOTORES_CON_CATALOGO = {"groq", "gemini", "openrouter"}


def _registros_uso():
    """{perfil: {registro, catalogo, dueno}}: el registro vive junto al catálogo 80a."""
    salida = {}
    for perfil, ficha in CATALOGOS_MODELOS.items():
        if isinstance(ficha, dict) and isinstance(ficha.get("ruta"), str) and isinstance(ficha.get("dueno"), str):
            salida[perfil] = {"registro": os.path.join(os.path.dirname(ficha["ruta"]), "uso-cuentas.jsonl"),
                              "catalogo": ficha["ruta"], "dueno": ficha["dueno"]}
    return salida


def _leer_cola_uso(ruta: str, dueno: str):
    """(líneas, problema). Solo la cola acotada: el registro crece sin tope y basta una semana.
    Mismo cuidado que el catálogo: este módulo corre como root."""
    try:
        uid = pwd.getpwnam(dueno).pw_uid; fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError: return None, "ausente"
    except (KeyError, OSError): return None, "ilegible"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != uid: return None, "ilegible"
        desde = max(0, st.st_size - MAX_REGISTRO_USO)
        os.lseek(fd, desde, os.SEEK_SET)
        with os.fdopen(fd, "rb", closefd=False) as fh: bruto = fh.read(MAX_REGISTRO_USO)
    except OSError: return None, "ilegible"
    finally: os.close(fd)
    lineas = bruto.decode("utf-8", "replace").splitlines()
    return (lineas[1:] if desde else lineas), None


def _leer_toml(ruta: str):
    import tomllib
    try:
        with open(ruta, "rb") as fh: dato = tomllib.load(fh)
    except (OSError, ValueError): return None
    return dato if isinstance(dato, dict) else None


def _cargar_recetas_bot(bot_dir: str):
    """recetas.py del bot DESPLEGADO, como bots-info: el del vault lo puede escribir cualquiera."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("recetas_auditor", f"{bot_dir}/recetas.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except (OSError, ImportError, SyntaxError, AttributeError):
        return None


def _dato_ok(x) -> bool:
    return isinstance(x, str) and 0 < len(x) <= 120 and x.isprintable()


def _lista_blanca(rec, cfg):
    """(rutas, cuentas_de(ruta)) que autoriza el perfil. None si el perfil no se entiende."""
    rutas = cfg.get("rutas")
    if not isinstance(rutas, list) or not all(isinstance(r, str) for r in rutas):
        return None
    rutas = {rec.ruta_interna(r) for r in rutas}
    recetas_cfg, _ = rec.normalizar_recetas(cfg.get("recetas"), tuple(rec.PROHIBIDO))
    cache = {}

    def cuentas_de(ruta):
        if ruta not in cache:
            ids = set(rec.cadena_efectiva(ruta, cfg.get("cuentas"))[0])
            receta = recetas_cfg.get(ruta)
            # `vision` sin receta es automática en el bot (VISION_RECETA).
            if (receta or {}).get("automatico") or (receta is None and ruta == "vision"):
                ids |= set(rec.cuentas_del_automatico(ruta))
            cache[ruta] = ids
        return cache[ruta]
    return rutas, cuentas_de


def _veces(n: int) -> str:
    return "1 vez" if n == 1 else f"{n} veces"


def alertas_rutas(ahora=None, bot_dir=BOT_DIR, registros=None, recetas_mod=None):
    ahora = ahora or dt.datetime.now().astimezone()
    salida = []

    def add(id_, texto):
        salida.append({"id": id_, "texto": texto})

    def hora(t):
        return f"{t.astimezone(ahora.tzinfo):%d-%m %H:%M}"
    rec = recetas_mod or _cargar_recetas_bot(bot_dir)
    if rec is None:
        add("rutas:recetas", f"🔎 auditor de rutas detenido: no puede cargar {bot_dir}/recetas.py")
        return salida
    registro_cuentas = _leer_toml(f"{bot_dir}/cuentas.toml")
    if registro_cuentas is None:
        add("rutas:cuentas_toml", "🔎 auditor de rutas: cuentas.toml ilegible; no revisa cuentas desconocidas")
    registros = _registros_uso() if registros is None else registros
    perfiles = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{bot_dir}/perfiles/*.toml"))
    desconocidas = {}
    motores_mal = {}

    def nombre_cuenta(c):
        ficha = (registro_cuentas or {}).get(c)
        nombre = ficha.get("nombre") if isinstance(ficha, dict) else None
        return nombre if _dato_ok(nombre) else rec.NOMBRE_CUENTA.get(c, c)
    for perfil in perfiles:
        P = perfil.capitalize()
        cfg = _leer_toml(f"{bot_dir}/perfiles/{perfil}.toml")
        blanca = _lista_blanca(rec, cfg) if cfg is not None else None
        if blanca is None:
            add(f"rutas:perfil:{perfil}", f"🔎 auditor de rutas: no entiende el perfil de {P}; no lo revisa")
            continue
        rutas_ok, cuentas_de = blanca
        ficha = registros.get(perfil)
        if not isinstance(ficha, dict):
            add(f"rutas:registro:{perfil}", f"🔎 auditor de rutas: no sabe dónde está el registro de uso de {P}")
            continue
        lineas, problema = _leer_cola_uso(ficha["registro"], ficha["dueno"])
        if problema == "ausente":
            add(f"rutas:registro:{perfil}", f"🔎 auditor de rutas: {P} no tiene registro de uso (uso-cuentas.jsonl)")
            continue
        if problema:
            add(f"rutas:registro:{perfil}", f"🔎 auditor de rutas: el registro de uso de {P} no se puede leer con seguridad (dueño, enlace o tipo)")
            continue
        eventos, rotas = [], 0
        for ln in lineas:
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
                if isinstance(d, dict) and d.get("tipo") == "calificacion":
                    continue
                t = dt.datetime.fromisoformat(d["ts"])
                if t.tzinfo is None: raise ValueError
                if not (_dato_ok(d["ruta"]) and _dato_ok(d["cuenta"])): raise ValueError
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                rotas += 1
                continue
            eventos.append((t, rec.ruta_interna(d["ruta"]), d["cuenta"], d.get("ok") is True,
                            d.get("motor") if _dato_ok(d.get("motor")) else None,
                            d.get("modelo") if _dato_ok(d.get("modelo")) else None,
                            d.get("forzada") is True))
        if rotas and (rotas >= max(3, (rotas + len(eventos)) // 10) or not eventos):
            add(f"rutas:registro:{perfil}", f"🔎 auditor de rutas: el registro de uso de {P} trae {rotas} líneas que no se leen")
        eventos.sort(key=lambda e: e[0])
        recientes = [e for e in eventos if 0 <= (ahora - e[0]).total_seconds() <= VENTANA_RUTAS_S]
        catalogo, catalogo_leido = set(), False
        if any(e[4] in MOTORES_CON_CATALOGO and e[5] for e in recientes):
            dato = _leer_catalogo_modelos(ficha["catalogo"], ficha["dueno"])
            if isinstance(dato, dict) and isinstance(dato.get("modelos"), list):
                catalogo_leido = True
                catalogo = {(f.get("proveedor"), f.get("modelo")) for f in dato["modelos"] if isinstance(f, dict)}
        rutas_mal, cuentas_mal, modelos_mal = {}, {}, {}
        for t, ruta, cuenta, ok, motor, modelo, forzada in recientes:
            if ruta not in rutas_ok:
                rutas_mal.setdefault(ruta, []).append(t)
            elif cuenta not in cuentas_de(ruta):
                cuentas_mal.setdefault((ruta, cuenta), []).append((t, forzada))
            if registro_cuentas is not None:
                ficha_c = registro_cuentas.get(cuenta)
                if not isinstance(ficha_c, dict):
                    desconocidas.setdefault(cuenta, []).append((perfil, t))
                elif motor and _dato_ok(ficha_c.get("motor")) and motor != ficha_c["motor"]:
                    motores_mal.setdefault((cuenta, motor, ficha_c["motor"]), []).append(t)
            if catalogo_leido and motor in MOTORES_CON_CATALOGO and modelo and (motor, modelo) not in catalogo:
                modelos_mal.setdefault((cuenta, modelo), []).append(t)
        for ruta, ts in sorted(rutas_mal.items()):
            add(f"rutas:ruta:{perfil}:{ruta}",
                f"🚩 auditor de rutas: {P} usó la ruta {rec.ruta_nombre(ruta)}, que su perfil no tiene "
                f"({_veces(len(ts))} en 7 días, la última {hora(ts[-1])})")
        for (ruta, cuenta), xs in sorted(cuentas_mal.items()):
            forzada = " (forzada)" if any(f for _, f in xs) else ""
            add(f"rutas:cuenta:{perfil}:{ruta}:{cuenta}",
                f"🚩 auditor de rutas: {P} → {rec.ruta_nombre(ruta)} → {nombre_cuenta(cuenta)} no está autorizado"
                f"{forzada} ({_veces(len(xs))} en 7 días, la última {hora(xs[-1][0])})")
        for (cuenta, modelo), ts in sorted(modelos_mal.items()):
            add(f"rutas:modelo:{perfil}:{cuenta}:{modelo}",
                f"🔎 auditor de rutas: {P} usó `{modelo}` de {nombre_cuenta(cuenta)}, que no está en su "
                f"catálogo vigilado ({_veces(len(ts))} en 7 días)")
        # Ruta muerta tapada por el respaldo: fallas seguidas de la misma cuenta en la
        # misma ruta, sin un ok de esa cuenta después.
        rachas, respaldos = {}, {}
        for t, ruta, cuenta, ok, *_ in eventos:
            if not 0 <= (ahora - t).total_seconds() <= VENTANA_MUERTA_S:
                continue
            if ok:
                rachas.pop((ruta, cuenta), None)
                for (r, c), racha in rachas.items():
                    if r == ruta and c != cuenta:
                        respaldos[(r, c)] = respaldos.get((r, c), 0) + 1
            else:
                racha = rachas.setdefault((ruta, cuenta), [])
                if not racha:
                    respaldos[(ruta, cuenta)] = 0
                racha.append(t)
        for (ruta, cuenta), racha in sorted(rachas.items()):
            if len(racha) >= FALLAS_MUERTA:
                tapada = respaldos.get((ruta, cuenta), 0)
                cola = (f"el respaldo contestó {_veces(tapada)} y la tapa" if tapada
                        else "nadie contestó por ella")
                add(f"rutas:muerta:{perfil}:{ruta}:{cuenta}",
                    f"🔎 auditor de rutas: {P} → {rec.ruta_nombre(ruta)} → {nombre_cuenta(cuenta)} falló "
                    f"{len(racha)} veces seguidas desde {hora(racha[0])}; {cola}")
    for cuenta, xs in sorted(desconocidas.items()):
        quienes = ", ".join(sorted({p.capitalize() for p, _ in xs}))
        add(f"rutas:desconocida:{cuenta}",
            f"🚩 auditor de rutas: la cuenta `{cuenta}` no existe en cuentas.toml y la usó {quienes} "
            f"({_veces(len(xs))} en 7 días)")
    for (cuenta, motor, esperado), ts in sorted(motores_mal.items()):
        add(f"rutas:motor:{cuenta}:{motor}",
            f"🔎 auditor de rutas: {nombre_cuenta(cuenta)} aparece con motor {motor} y cuentas.toml dice {esperado}")
    unicas = {}
    for alerta in salida:
        unicas.setdefault(alerta["id"], alerta)
    return list(unicas.values())


# ------------------------------------------------------------- inbox

INBOX = f"{DATOS}/srv/vault_personal/00-Inbox"


def inventario_inbox():
    """Que hay sin procesar en el buzon.

    Capturar quedo facilisimo y procesar no esta resuelto: si el inbox crece sin
    parar, el sistema deja de servir aunque funcione perfecto — y pasa en
    silencio, que es justo el modo de falla que este proyecto quiere evitar.
    Esto solo MIRA: no mueve, no edita, no clasifica. Mover notas es criterio
    humano, y ademas editarlas desde la Pi mientras estan abiertas en Obsidian
    es como se generan los conflictos de Syncthing (regla 4).
    """
    inv = {"pendientes": 0, "audios_pendientes": 0, "mas_vieja_dias": None,
           "lista": [], "total": 0}
    if not os.path.isdir(INBOX):
        inv["error"] = "no existe el inbox"
        return inv

    hoy = dt.date.today()
    for raiz, _dirs, files in os.walk(INBOX):
        for f in sorted(files):
            if not f.endswith(".md") or f.startswith("_"):
                continue
            ruta = os.path.join(raiz, f)
            inv["total"] += 1
            try:
                with open(ruta, encoding="utf-8") as fh:
                    cab = fh.read(600)
            except Exception:
                continue
            if "procesado: false" not in cab:
                continue
            inv["pendientes"] += 1
            if "transcripcion: pendiente" in cab:
                inv["audios_pendientes"] += 1
            m = re.search(r"^fecha:\s*(\d{4}-\d{2}-\d{2})", cab, re.M)
            dias = None
            if m:
                try:
                    dias = (hoy - dt.date.fromisoformat(m.group(1))).days
                except ValueError:
                    pass
            inv["lista"].append({"archivo": f, "dias": dias})

    con_dias = [x["dias"] for x in inv["lista"] if x["dias"] is not None]
    inv["mas_vieja_dias"] = max(con_dias) if con_dias else None
    # Las mas viejas primero: son las que se estan por perder de vista.
    inv["lista"].sort(key=lambda x: (-(x["dias"] or 0), x["archivo"]))
    inv["lista"] = inv["lista"][:15]
    return inv


# ------------------------------------------------------------- agentes

def agentes():
    """Sesiones de Claude Code y Codex vivas en el nodo.

    Se filtra por el NOMBRE del proceso (comm) y no por la linea de comandos:
    `pgrep -af claude` engancha tambien al `tmux new-session -s claude` y al
    `tmux attach -t claude`, que no son sesiones. Verificado el 09-09-2026: comm
    dice "claude" aunque el ejecutable real se llame "2.1.267" —Claude Code
    instala la version como nombre de archivo—, asi que deducir el comm del
    nombre del binario NO funciona.

    Y se usa ps, no `tmux ls`, porque este script corre como root: el servidor de
    tmux del root es /tmp/tmux-0 y el del usuario /tmp/tmux-1000, asi que
    `sudo tmux ls` falla, sh() se come el error y el panel diria cero sesiones
    habiendo dos. Como root, ps ve los procesos de todos los usuarios.

    OJO: el comm de codex quedo SIN verificar (no habia proceso corriendo al
    escribir esto). Comprobar con `ps -eo comm=,args= | grep -i codex` la
    proxima vez que se abra; si no es exactamente "codex", ajustar la tupla.
    """
    vivos = []
    for ln in sh("ps -eo comm=,pid=,etimes=,user=,args=").splitlines():
        p = ln.split(None, 4)
        if len(p) < 5:
            continue
        comm, pid, secs, usuario, args = p
        if comm not in ("claude", "codex"):
            continue
        # `claude` solo es una sesion; `claude auth login` es un subcomando que
        # quedo colgado. Distinguirlos es la diferencia entre "estoy trabajando"
        # y "hay basura desde ayer".
        partes = args.split()
        vivos.append({"agente": comm, "pid": int(pid), "usuario": usuario,
                      "horas": int(secs) / 3600,
                      "sub": partes[1] if len(partes) > 1 else ""})
    vivos.sort(key=lambda a: -a["horas"])
    return vivos


# Servicios de la tupla de recolectar() que existen solo cuando alguien los activa
# a proposito. El resto se vigila siempre: ausente o detenido, es una caida.
OPCIONALES = ("cloudflared-panel", "luces-senales")
SERVICIOS_USUARIO = ("luces-senales",)


def se_vigila(s):
    """Si un servicio de la tupla entra al panel en esta pasada.

    Uno opcional entra solo si esta habilitado (`systemctl is-enabled` dice
    exactamente "enabled") o si esta corriendo. Sin la unidad instalada
    is-enabled contesta "not-found", y tras `apagar`, "disabled": en los dos
    casos no se muestra, porque un tunel que nadie activo no esta caido.
    Habilitado e inactivo si se muestra, y como caido: es la puerta que
    deberia estar arriba.

    El "o si esta corriendo" es por lo inverso: un tunel levantado a mano con
    `systemctl start`, sin habilitar, es una puerta a Internet abierta. Que el
    panel no la nombre seria el mismo punto ciego de la tupla, al reves.
    """
    if s not in OPCIONALES:
        return True
    prefijo = "systemctl --user -M dcifu004@" if s in SERVICIOS_USUARIO else "systemctl"
    return (sh(f"{prefijo} is-enabled {s}") == "enabled"
            or sh(f"{prefijo} is-active {s}") == "active")


def servicios(nombres):
    """{servicio: esta activo} de los que se vigilan en esta pasada."""
    return {s: sh(f"{'systemctl --user -M dcifu004@' if s in SERVICIOS_USUARIO else 'systemctl'} is-active {s}") == "active"
            for s in nombres if se_vigila(s)}


# ------------------------------------------------------------- recoleccion

def recolectar():
    e = {"host": sh("hostname"), "momento": dt.datetime.now().isoformat(timespec="seconds")}
    e["encendida_hace"] = sh("uptime -p").replace("up ", "")

    # --- volumen cifrado ---
    montado = sh(f"mountpoint -q {DATOS} && echo si") == "si"
    e["luks"] = {"abierto": montado}
    if montado:
        d = sh(f"df -B1 --output=used,size,pcent {DATOS} | tail -1").split()
        if len(d) == 3:
            e["luks"].update(usado=int(d[0]), total=int(d[1]), pct=int(d[2].strip("%")))

    # --- servicios ---
    # captura-web es la app del monitor de plantas: si se cae, el QR de la
    # maceta no responde. home-assistant es el caso importante — es el UNICO
    # servicio que vive fuera del cifrado, para volver solo tras un corte de
    # luz. O sea el que tiene que estar arriba cuando ninguno de los otros
    # puede: no mirarlo era el hueco mas grande del panel.
    #
    # ESTA TUPLA ES EL PUNTO CIEGO DEL PANEL: cada servicio nuevo del nodo nace
    # invisible hasta que alguien lo agrega aca, y no hay nada que avise de la
    # omision. botv3 (el bot de consultas de solo lectura) vivio asi desde el
    # 11-09-2026. Al instalar un servicio en el nodo, agregarlo en la misma
    # sesion.
    e["servicios"] = servicios(("docker", "tailscaled", "ssh", "captura-telegram",
                                "captura-web", "home-assistant",
                                # Instancias de la unidad plantilla botv3@.service,
                                # con el @ incluido: `systemctl is-active botv3@jaime`.
                                # Cada perfil nuevo suma una linea aca o nace invisible.
                                # El `botv3` a secas se retiro el 13-09-2026, cuando
                                # Jaime paso a la plantilla: dejarlo lo reportaba caido.
                                "botv3@jaime", "botv3@pilar",
                                # Consola web (24-09-2026). Se mira el SOCKET, no el
                                # servicio: cockpit.service se activa por socket y
                                # esta inactivo mientras nadie entra, asi que
                                # vigilarlo daria "caido" falso y un aviso sin motivo.
                                "cockpit.socket",
                                # Luces de los ventiladores (24-09-2026): oneshot con
                                # RemainAfterExit, asi que "active" = restauro al
                                # arrancar. El color en si lo cuenta la linea de luces.
                                "luces", "luces-senales",
                                # Drive personal montado con rclone (24-09-2026).
                                "rclone-drive@personal",
                                # Puente a Google (24-09-2026): igual que cockpit, se
                                # mira el SOCKET — el servicio se activa al primer uso.
                                "google-puente.socket", "google-puente-hogar.socket",
                                # Tunel de Cloudflare hacia Cockpit (09-10-2026), la
                                # puerta publica panel.dcspi5.com. Es el unico de la
                                # tupla que puede NO estar instalado: lo pone
                                # `instalar-tunel.sh activar` y lo saca `apagar`, asi
                                # que pasa por se_vigila() y antes de activarlo no
                                # aparece, en vez de salir caido todos los dias.
                                "cloudflared-panel"))
    e["contenedores"] = []
    if montado and e["servicios"]["docker"]:
        for ln in sh(f"docker compose -f {COMPOSE} ps --format '{{{{.Service}}}}|{{{{.Status}}}}'").splitlines():
            if "|" in ln:
                n, st = ln.split("|", 1)
                e["contenedores"].append({"nombre": n, "estado": st,
                                          "ok": st.startswith("Up"),
                                          "runtime": "docker"})
    # Home Assistant corre en Podman, no en Docker, y su data-root esta fuera
    # del cifrado a proposito. Sin esta segunda fuente es invisible por las dos
    # puertas: no esta en compose.yml y `docker ps` no lo ve.
    for ln in sh("podman ps --format '{{.Names}}|{{.Status}}'").splitlines():
        if "|" in ln:
            n, st = ln.split("|", 1)
            e["contenedores"].append({"nombre": n, "estado": st,
                                      "ok": st.startswith("Up"),
                                      "runtime": "podman"})
    # Un contenedor en bucle se ve como "Up 10 seconds" y parece sano.
    # El guard es el mismo que arriba y NO es decorativo: con el demonio caido
    # `docker ps` se cuelga en vez de fallar, y sh() recien corta a los 15 s.
    # Sin esto, con el volumen cerrado /estado tardaba 15 segundos extra —
    # justo cuando lo consultas apurado desde el telefono.
    ids = sh("docker ps -q").split() if (montado and e["servicios"]["docker"]) else []
    e["reinicios"] = {}
    for i in ids:
        n = sh(f"docker inspect --format '{{{{.Name}}}}' {i}").lstrip("/")
        c = sh(f"docker inspect --format '{{{{.RestartCount}}}}' {i}")
        if c and c != "0":
            e["reinicios"][n] = int(c)

    # --- red ---
    ip_ts = sh("tailscale ip -4").splitlines()
    e["red"] = {"tailscale": ip_ts[0] if ip_ts else None,
                "ip_local": sh("hostname -I").split()[0] if sh("hostname -I") else None}
    try:
        self_ = json.loads(sh("tailscale status --json", t=20))["Self"]
        e["red"]["clave_vence"] = bool(self_.get("KeyExpiry"))
    except Exception:
        e["red"]["clave_vence"] = None

    # --- sincronizacion ---
    e["sync"] = {"carpetas": [], "dispositivos": []}
    try:
        root = ET.parse(SYNC_CFG).getroot()
        api = root.find("gui").findtext("apikey")
        nombres = {d.get("id"): d.get("name") for d in root.findall("device")}

        def get(p):
            r = urllib.request.Request("http://127.0.0.1:8384/rest" + p,
                                       headers={"X-API-Key": api})
            return json.load(urllib.request.urlopen(r, timeout=10))

        for f in get("/config/folders"):
            s = get("/db/status?folder=" + f["id"])
            e["sync"]["carpetas"].append({
                "label": f["label"], "archivos": s["localFiles"],
                "bytes": s["localBytes"], "faltan": s["needFiles"],
                "estado": s["state"],
                "ok": s["needFiles"] == 0 and s["state"] == "idle"})
        for k, v in get("/system/connections")["connections"].items():
            e["sync"]["dispositivos"].append({
                "nombre": nombres.get(k, k[:7]), "conectado": v["connected"],
                "lan": bool(v.get("isLocal")),
                "tipo": v.get("type", "").replace("-client", "").replace("-server", "")})
    except Exception as ex:
        e["sync"]["error"] = str(ex)

    # --- captura: si el sistema esta HACIENDO SU TRABAJO ---
    # El resto del panel dice que la maquina esta sana. Esto dice que sirve
    # para algo, que no es lo mismo.
    e["captura"] = {"activo": e["servicios"].get("captura-telegram", False)}
    try:
        with open(BOT_ESTADO) as fh:
            b = json.load(fh)
        hoy = dt.datetime.now().strftime("%Y-%m-%d")
        e["captura"]["hoy"] = b.get("guardadas_hoy", 0) if b.get("dia") == hoy else 0
        e["captura"]["ultimo_dia"] = b.get("dia") or None
    except Exception:
        e["captura"]["hoy"] = None

    e["inbox"] = inventario_inbox()
    e["agentes"] = agentes()

    # --- respaldo ---
    r = {"montado": sh(f"mountpoint -q {RESPALDO} && echo si") == "si"}
    if r["montado"]:
        d = sh(f"df -B1 --output=avail,size {RESPALDO} | tail -1").split()
        if len(d) == 2:
            r.update(libre=int(d[0]), total=int(d[1]))
        dev = sh(f"findmnt -no SOURCE {RESPALDO}")
        r["dispositivo"] = dev
        # Un respaldo en el mismo disco que los datos no sobrevive a la falla
        # que un respaldo existe para cubrir.
        r["en_disco_aparte"] = not (dev.startswith("/dev/nvme") or "mapper/datos" in dev)
        try:
            out = subprocess.run(
                ["restic", "--no-cache", "--repo", REPO, "--password-file", PASS,
                 "snapshots", "latest", "--tag", "archivos", "--json"],
                capture_output=True, text=True, timeout=60).stdout
            snaps = json.loads(out)
            if snaps:
                t = dt.datetime.fromisoformat(snaps[-1]["time"])
                r["ultimo"] = t.isoformat(timespec="seconds")
                r["horas"] = round((dt.datetime.now(t.tzinfo) - t).total_seconds() / 3600, 1)
        except Exception:
            pass
    nxt = sh("systemctl list-timers respaldo.timer --no-pager")
    ln = nxt.splitlines()
    r["proximo"] = " ".join(ln[1].split()[:3]) if len(ln) > 1 else None
    e["respaldo"] = r

    # --- salud ---
    # `systemctl --failed --no-legend` antepone un bullet de estado a cada linea
    # ("● unidad.service loaded failed ..."), asi que el split()[0] de antes se
    # llevaba el bullet y la alerta decia literal "unidades fallidas: ●", sin
    # nombrar la unidad. Se lee justo por Telegram, que es donde NO podes correr
    # systemctl para averiguar cual fue: el aviso despertaba sin decir nada
    # accionable. --plain suprime el bullet; el filtro por sufijo es el respaldo
    # por si una version de systemd no lo soporta en list-units.
    SUFIJOS = (".service", ".timer", ".mount", ".socket", ".target", ".path",
               ".slice", ".scope", ".automount", ".swap", ".device")
    fallidas = []
    for l in sh("systemctl --failed --no-legend --plain --no-pager").splitlines():
        for tok in l.split():
            if tok.endswith(SUFIJOS):
                fallidas.append(tok)
                break
    io = sh("dmesg -T | grep -icE 'I/O error|blk_update_request'")
    e["salud"] = {
        "unidades_fallidas": fallidas,
        "reloj_ntp": sh("timedatectl show -p NTPSynchronized --value") == "yes",
        "errores_io": int(io) if io.isdigit() else 0,
        "reinicio_pendiente": os.path.exists("/var/run/reboot-required"),
        "actualizaciones": len([l for l in sh("apt-get -s upgrade", t=60).splitlines()
                                if l.startswith("Inst")]),
    }

    # --- canal de avisos ---
    # Se LEE lo que dejo el emisor y no se recalcula nada: el unico que sabe si
    # Telegram acepto el mensaje es el que lo mando. Si el archivo no existe
    # queda en None y no genera alerta a proposito — un nodo recien desplegado,
    # o uno sin avisos, no tiene por que salir en rojo; que el servicio se caiga
    # ya lo cubre `unidades_fallidas`. Lo que este bloque agrega es el caso que
    # NO cubre: el emisor corre, sale con codigo 0 y no llega nada.
    e["avisos"] = None
    try:
        with open(SALUD_AVISOS) as fh:
            av = json.load(fh)
    except (OSError, json.JSONDecodeError):
        av = None
    if isinstance(av, dict):
        ciclo = av.get("ultimo_ciclo")
        e["avisos"] = {
            "permanente": bool(av.get("permanente")),
            "ultimo_error": av.get("ultimo_error"),
            "ultimo_envio": av.get("ultimo_envio"),
            "min_sin_ciclo": (round((time.time() - ciclo) / 60, 1)
                              if isinstance(ciclo, (int, float)) else None),
        }

    # --- medidores ---
    m = {}
    t = num(sh("vcgencmd measure_temp"))
    if t is not None:
        m["temp_soc"] = {"v": t, "max": 85, "am": 70, "ro": 80, "min": 30,
                         "u": "C", "nota": "ok <70 · limita 80 · corta 85"}
    smart = sh("smartctl -A /dev/nvme0", t=30)
    campos = {}
    for k, pat in (("usado", r"Percentage Used:\s+(\d+)"),
                   ("spare", r"Available Spare:\s+(\d+)"),
                   ("tnvme", r"Temperature:\s+(\d+)"),
                   ("horas", r"Power On Hours:\s+([\d,]+)"),
                   ("errores", r"Media and Data Integrity Errors:\s+([\d,]+)"),
                   ("escrito", r"Data Units Written:.*\[([\d.]+ \w+)\]")):
        mt = re.search(pat, smart)
        if mt:
            campos[k] = mt.group(1).replace(",", "")
    if "tnvme" in campos:
        m["temp_nvme"] = {"v": float(campos["tnvme"]), "max": 85, "am": 65, "ro": 75,
                          "min": 30, "u": "C", "nota": "ok <65 · critico 75"}
    if "usado" in campos:
        m["nvme_vida"] = {"v": float(campos["usado"]), "max": 100, "am": 50, "ro": 80,
                          "u": "%",
                          "nota": f"repuesto {campos.get('spare','?')}% · "
                                  f"{campos.get('escrito','?')} en {campos.get('horas','?')} h"}
    e["nvme_errores"] = int(campos.get("errores", 0) or 0)

    ncpu = int(sh("nproc") or 1)
    carga = num(open("/proc/loadavg").read().split()[0], 0)
    m["carga"] = {"v": carga, "max": ncpu, "am": ncpu * 0.75, "ro": ncpu, "u": "",
                  "nota": f"promedio 1 min · {ncpu} nucleos"}

    libre = sh("free -m").splitlines()
    mem = libre[1].split()
    m["memoria"] = {"v": int(mem[2]), "max": int(mem[1]), "am": int(mem[1]) * .8,
                    "ro": int(mem[1]) * .92, "u": "MB", "nota": "",
                    "texto": f"{int(mem[2])/1024:.1f}/{int(mem[1])/1024:.1f} GB"}
    for l in libre:
        if l.lower().startswith("swap"):
            sw = l.split()
            if int(sw[1]) > 0:
                m["swap"] = {"v": int(sw[2]), "max": int(sw[1]), "am": 256, "ro": 1024,
                             "u": "MB", "nota": "si sube, falta RAM"}

    for ruta, nom in (("/", "raiz"), (DATOS, "datos cifrados"), (RESPALDO, "disco respaldo")):
        d = sh(f"df -B1 --output=used,size,pcent {ruta} | tail -1").split()
        h = sh(f"df -h --output=used,size {ruta} | tail -1").split()
        if len(d) == 3:
            m[nom] = {"v": int(d[2].strip('%')), "max": 100, "am": 80, "ro": 92,
                      "u": "%", "nota": f"{h[0]}/{h[1]}" if len(h) == 2 else ""}
    e["medidores"] = m

    # glob y no os.walk: /sys/class/hwmon son enlaces simbolicos y os.walk no
    # los sigue, asi que el ventilador quedaba invisible.
    # La barra sale del pwm (0-255) y no de las rpm: el pwm es lo que el kernel
    # le ORDENA al ventilador, y las rpm no tienen un maximo conocido contra el
    # cual medir. Las dos juntas delatan un ventilador trabado: pwm > 0 y 0 rpm.
    e["ventilador_rpm"] = None
    e["ventilador"] = None
    for base in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if open(f"{base}/name").read().strip() == "pwmfan":
                rpm = int(open(f"{base}/fan1_input").read())
                pwm = int(open(f"{base}/pwm1").read())
                e["ventilador_rpm"] = rpm
                e["ventilador"] = {"rpm": rpm, "pwm": pwm, "pct": round(pwm * 100 / 255)}
        except Exception:
            pass
    e["luces"] = luces()
    e["throttled"] = sh("vcgencmd get_throttled") == "throttled=0x0"
    return e


def luces():
    """Que muestran las luces del ventilador, segun lo que anoto `luces`.

    Los WS2812 son de solo escritura, asi que esto es lo ultimo que `luces` dice
    haber escrito, contrastado con las dos cosas que SI se pueden comprobar: si
    la Pi se reinicio desde entonces (al perder corriente se apagan, y el archivo
    no se entera) y si la animacion sigue viva.
    """
    try:
        boot = open("/proc/sys/kernel/random/boot_id").read().strip()
        s = json.load(open(LUCES))
    except Exception:
        s = None
    # Lista y no string: con shell=True el `sh -c` lleva "arcoiris.py" en su
    # propia linea de comandos y pgrep se encontraria a si mismo.
    arcoiris_a_mano = bool(sh(["pgrep", "-f", "arcoiris.py"]))
    if s is None or s.get("boot_id") != boot:
        if arcoiris_a_mano:  # la receta vieja de la nota 18 no anota nada
            return {"modo": "arcoiris", "fuente": "proceso"}
        if s is not None:
            return {"modo": "apagado", "fuente": "reinicio"}
        return {"modo": "desconocido"}
    # Todo lo que se MUEVE (arcoiris, respiracion, una paleta que gira o respira)
    # es un proceso y anota su pid; si murio, las luces quedaron congeladas en algun
    # punto y no se sabe cual. Lo quieto no anota pid y no hay nada que revisar.
    if s.get("pid") and not os.path.exists(f"/proc/{s.get('pid')}"):
        return {"modo": "detenido", "momento": s.get("momento")}
    salida = {k: s.get(k) for k in ("modo", "rgb", "nombre", "momento", "brillo",
                                    "paleta", "girar", "respira")}
    # No se ejecuta `luces` desde acá: `estado --escribir` corre como root y el
    # programa de luces vive en el home del usuario. Sólo se leen sus dos JSON
    # de estado, como el resto de este panel lee registros publicados.
    salida["regla_visible"] = regla_visible_luces()
    return salida


def regla_visible_luces(ahora=None):
    """ID calculado y publicado por el vigilante, o None si no hay marca válida."""
    try:
        visible = json.load(open(LUCES_SENAL)).get("regla_visible")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return visible if isinstance(visible, str) else None


def config_error_luces():
    """Error publicado por el vigilante; root sólo lee su JSON compartido."""
    try:
        error = json.load(open(LUCES_SENAL)).get("config_error")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    patron = (r"(?:no existe|no es JSON|no valida: [A-Za-z0-9_.\[\] :]{0,80})"
              r"(?:; se usa la última guardada|; reglas apagadas)")
    if error is None:
        return None
    return error if isinstance(error, str) and re.fullmatch(patron, error) else "inválido"


def color_luces(l):
    """(emoji, texto) para mostrar las luces. None si no hay nada que decir."""
    modo = (l or {}).get("modo")
    if modo is None:
        return None
    if modo == "arcoiris":
        # girar es un nivel 0-10 desde el 24-09; un registro viejo sin la llave giraba.
        gira = l.get("girar", 5)
        return "🌈", ("arcoiris " + ("girando" if gira else "quieto")
                      + (" que respira" if l.get("respira") else ""))
    if modo == "paleta":
        detalle = [x for x, si in (("girando", l.get("girar")), ("respira", l.get("respira"))) if si]
        return "🎨", f"paleta {l.get('nombre') or ''}" + (f" · {' y '.join(detalle)}" if detalle else " · quieta")
    if modo == "detenido":
        return "⚪", "animacion detenida · color desconocido"
    if modo == "desconocido":
        return "⚪", "sin registro · cambialas con `luces`"
    r, g, b = l.get("rgb") or (0, 0, 0)
    if modo == "apagado" or max(r, g, b) < 10:
        return "⚫", "apagadas" + (" (se reinicio la Pi)" if l.get("fuente") == "reinicio" else "")
    h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s < 0.25:
        em, nom = "⚪", "blanco"
    else:
        h *= 360
        em, nom = next((em, nom) for lim, em, nom in (
            (15, "🔴", "rojo"), (40, "🟠", "naranja"), (70, "🟡", "amarillo"),
            (165, "🟢", "verde"), (200, "🔵", "cian"), (255, "🔵", "azul"),
            (290, "🟣", "morado"), (340, "🟣", "rosado"), (361, "🔴", "rojo")) if h < lim)
    texto = f"{l.get('nombre') or nom} #{r:02X}{g:02X}{b:02X}"
    if modo == "respiracion":
        texto = f"respiracion {texto}"
    brillo = l.get("brillo")
    if isinstance(brillo, int) and brillo < 100:
        texto += f" · brillo {brillo}%"
    return em, texto


def medidor_ventilador(v):
    # Nunca rojo: un ventilador a fondo no es una falla, es el ventilador
    # haciendo su trabajo. La alerta por calor ya la da temp_soc.
    return {"v": v["pct"], "max": 100, "am": 75, "ro": 101, "u": "%"}


def texto_ventilador(v):
    if v["pwm"] > 0 and v["rpm"] == 0:
        return False, f"{v['pct']}% · 0 rpm — NO GIRA"
    return True, "detenido" if v["pwm"] == 0 else f"{v['pct']}% · {v['rpm']} rpm"


# ------------------------------------------------------------- alertas
# La misma lista que usaran los avisos por umbral del bot. Definirlas aca y no
# en el bot es lo que evita que el panel diga "todo bien" mientras Telegram
# avisa de un problema, o al reves.

def alertas(e):
    """Lista de {id, texto}.

    El `id` es estable y el `texto` no: "respaldo hace 37 h" y "hace 38 h" son
    la MISMA alerta. Comparando por texto, el bot avisaria de nuevo cada hora
    hasta que dejes de leerlo — que es como se rompe un sistema de avisos.
    """
    a = []

    def add(id_, texto):
        a.append({"id": id_, "texto": texto})

    if not e["luks"]["abierto"]:
        add("luks", "volumen cifrado CERRADO: corre sudo abrir-datos")
    config_error = config_error_luces()
    if config_error:
        add("luces:reglas", "🚩 luces: luces-reglas.json " + config_error)
    for s, ok in e["servicios"].items():
        if not ok:
            add(f"servicio:{s}", f"servicio caido: {s}")
    for c in e["contenedores"]:
        if not c["ok"]:
            add(f"contenedor:{c['nombre']}", f"contenedor {c['nombre']}: {c['estado']}")
    r = e["respaldo"]
    if not r["montado"]:
        add("respaldo:disco", "disco de respaldo NO montado")
    elif r.get("horas") is None:
        add("respaldo:ilegible", "no se pudo leer el ultimo respaldo")
    elif r["horas"] >= 36:
        add("respaldo:viejo", f"ultimo respaldo hace {r['horas']:.0f} h")
    if r.get("en_disco_aparte") is False:
        add("respaldo:mismo_disco", "el repositorio esta en el M.2: eso no es un respaldo")
    if e["salud"]["unidades_fallidas"]:
        add("unidades", "unidades fallidas: " + ", ".join(e["salud"]["unidades_fallidas"]))
    # La alerta que el 19-09-2026 no tuvo a quien contarle: el canal push caido.
    # Sale por aca porque /estado se pide desde el bot de consultas, que no
    # comparte token ni proceso con el emisor. El umbral de 60 min son 6 ciclos
    # del timer, que es de 10: uno o dos fallos seguidos se resuelven solos y
    # alertar por eso seria justo lo que la doctrina prohibe.
    av = e.get("avisos") or {}
    if av.get("permanente"):
        add("avisos:muerto",
            f"el canal de avisos NO puede enviar ({av.get('ultimo_error') or 'sin detalle'}): "
            "regenera el token en BotFather y escribilo en /etc/nodo/avisos.env. "
            "Hasta entonces el nodo no avisa nada solo")
    elif (av.get("min_sin_ciclo") or 0) >= 60:
        add("avisos:detenido",
            f"el emisor de avisos no completa un ciclo hace {av['min_sin_ciclo']:.0f} min: "
            "mira avisos.timer")
    if not e["salud"]["reloj_ntp"]:
        add("reloj", "reloj sin sincronizar (la Pi 5 no tiene RTC)")
    if e["salud"]["errores_io"]:
        add("io", f"{e['salud']['errores_io']} errores de E/S en el log")
    if e["nvme_errores"]:
        add("nvme:errores", f"{e['nvme_errores']} errores de integridad del NVMe")
    # OJO: `syncing` NO es una alerta, es Syncthing haciendo su trabajo. Alertar
    # por eso llena Telegram de avisos cuando todo esta bien, y una alerta que
    # suena sin motivo se ignora — incluida la vez que si importa. Solo alerta
    # el estado `error`, que es el que no se resuelve solo.
    # El buzon sin vaciar no rompe nada hoy, y por eso mismo hay que avisarlo:
    # es la falla que llega despacio y termina matando el sistema por desuso.
    inb = e.get("inbox", {})
    if inb.get("pendientes", 0) >= 25:
        add("inbox:acumulado", f"{inb['pendientes']} capturas sin procesar")
    if (inb.get("mas_vieja_dias") or 0) >= 14:
        add("inbox:vieja",
            f"hay capturas sin procesar de hace {inb['mas_vieja_dias']} dias")

    # La AUSENCIA de un agente no es alerta: corre cuando te sentas y el resto
    # del tiempo no, igual que un telefono desconectado de Syncthing. Alertar
    # por eso seria un rojo permanente, y un rojo permanente se ignora. Lo
    # anomalo es lo contrario: algo vivo hace horas que nadie esta mirando, en
    # un nodo donde sudo todavia no pide contrasena (la clave SSH SI tiene frase
    # desde el 13-09-2026; ver `16 - Plan de seguridad y acceso`, Hueco 1).
    # OJO al nombre de la variable: el acumulador de esta funcion se llama `a` y
    # `add` es un closure sobre el. Un `for a in ...` aca lo pisa, `alertas()`
    # devuelve un dict en vez de la lista y el panel explota al formatear.
    for ag in e.get("agentes", []):
        if ag["horas"] >= 8:
            add(f"agente:{ag['pid']}",
                f"{ag['agente']} vivo hace {ag['horas']:.0f} h (pid {ag['pid']})")

    for c in e["sync"]["carpetas"]:
        if c["estado"] == "error":
            add(f"sync:{c['label']}", f"syncthing {c['label']}: en ERROR")
    for k, med in e["medidores"].items():
        if med["v"] >= med["ro"]:
            add(f"medidor:{k}", f"{k} en {med['v']:g}{med['u']} (limite {med['ro']:.0f})")
    a.extend(alertas_catalogo_modelos())
    # El auditor (94) lee archivos que escriben los bots: si algo raro se le escapa, se
    # dice como alerta y el resto del estado sale igual.
    try:
        a.extend(alertas_rutas())
    except Exception as exc:
        add("rutas:fallo", f"🔎 auditor de rutas falló: {type(exc).__name__}")
    return a


# ------------------------------------------------------------- salidas

C = {"cyan": "\033[1;36m", "v": "\033[32m", "a": "\033[33m", "r": "\033[31m",
     "gris": "\033[2m", "fin": "\033[0m"}
ANCHO = 20


def color(med):
    if med["v"] >= med["ro"]:
        return C["r"]
    if med["v"] >= med["am"]:
        return C["a"]
    return C["v"]


def barra(med):
    mn = med.get("min", 0)
    v = max(med["v"], mn)
    pct = 0 if med["max"] <= mn else min(100, max(0, int((v - mn) * 100 / (med["max"] - mn))))
    n = pct * ANCHO // 100
    return f"{color(med)}{'█'*n}{C['gris']}{'░'*(ANCHO-n)}{C['fin']}"


def punto(ok, etiqueta, texto, alerta=False):
    c = C["a"] if alerta else (C["v"] if ok else C["r"])
    print(f"  {c}●{C['fin']} {etiqueta:<22} {texto}")


def texto_completo(e):
    print(f"{C['cyan']}── NODO {e['host']} · {e['momento'][:16].replace('T',' ')} "
          f"· encendida hace {e['encendida_hace']}{C['fin']}")

    print(f"{C['cyan']}Captura{C['fin']}")
    cap = e["captura"]
    hoy = cap.get("hoy")
    punto(cap["activo"], "bot de Telegram", "escuchando" if cap["activo"] else "APAGADO")
    punto(hoy is not None, "notas hoy",
          f"{hoy}" if hoy is not None else "sin datos todavia")
    inb = e.get("inbox", {})
    if inb and "error" not in inb:
        v = inb.get("mas_vieja_dias")
        punto(inb["pendientes"] < 25, "sin procesar",
              f"{inb['pendientes']} de {inb['total']}"
              + (f" · la mas vieja hace {v} dias" if v else "")
              + (f" · {inb['audios_pendientes']} audios sin transcribir"
                 if inb.get("audios_pendientes") else ""))

    print(f"{C['cyan']}Agentes{C['fin']}")
    ag = e.get("agentes", [])
    if not ag:
        punto(True, "sesiones", "ninguna")
    for a in ag:
        punto(a["horas"] < 8, f"{a['agente']} {a['sub']}".strip(),
              f"pid {a['pid']} · hace {a['horas']:.1f} h · {a['usuario']}",
              alerta=a["horas"] >= 8)

    print(f"{C['cyan']}Volumen cifrado{C['fin']}")
    L = e["luks"]
    punto(L["abierto"], "LUKS",
          f"abierto · {L.get('pct','?')}% usado" if L["abierto"]
          else "CERRADO — corre: sudo abrir-datos")

    print(f"{C['cyan']}Servicios{C['fin']}")
    for s, ok in e["servicios"].items():
        punto(ok, s, "activo" if ok else "CAIDO")
    for c in e["contenedores"]:
        punto(c["ok"], c["nombre"], c["estado"])

    print(f"{C['cyan']}Red{C['fin']}")
    ve = e["red"].get("clave_vence")
    punto(True, "tailscale", f"{e['red']['tailscale']} · "
          + ("OJO: la clave vence" if ve else "clave sin vencimiento"))
    punto(True, "IP local", e["red"]["ip_local"] or "?")

    print(f"{C['cyan']}Sincronizacion{C['fin']}")
    for c in e["sync"]["carpetas"]:
        punto(c["ok"], c["label"],
              f"{c['archivos']} archivos · {c['bytes']/1048576:.1f} MB · faltan {c['faltan']}")
    for d in e["sync"]["dispositivos"]:
        # Desconectado va en amarillo, no en rojo: es lo normal en un telefono.
        if d["conectado"]:
            punto(True, d["nombre"],
                  f"conectado · {'LAN' if d['lan'] else 'remoto'} · {d['tipo']}")
        else:
            punto(False, d["nombre"], "sin conexion", alerta=True)

    print(f"{C['cyan']}Respaldo{C['fin']}")
    r = e["respaldo"]
    if r["montado"]:
        punto(True, "disco", f"{r.get('libre',0)/2**30:.0f}G libres de {r.get('total',0)/2**30:.0f}G")
        h = r.get("horas")
        if h is None:
            punto(False, "ultimo respaldo", "no se pudo leer")
        else:
            punto(h < 30, "ultimo respaldo",
                  f"{r['ultimo'][5:16].replace('T',' ')} — hace {h:.0f} h"
                  + ("" if h < 30 else " ⚠ se salteo uno"), alerta=30 <= h < 48)
        punto(r.get("en_disco_aparte", False), "en disco aparte", r.get("dispositivo", "?"))
    else:
        punto(False, "disco de respaldo", "NO montado")
    if r.get("proximo"):
        punto(True, "proximo", r["proximo"])

    print(f"{C['cyan']}Salud{C['fin']}")
    s = e["salud"]
    punto(not s["unidades_fallidas"], "unidades fallidas",
          ", ".join(s["unidades_fallidas"]) or "ninguna")
    punto(not e["reinicios"], "reinicios",
          ", ".join(f"{k}={v}" for k, v in e["reinicios"].items()) or "ninguno")
    punto(s["reloj_ntp"], "reloj",
          "sincronizado por NTP" if s["reloj_ntp"]
          else "SIN sincronizar — la Pi 5 no tiene RTC")
    punto(not s["errores_io"], "errores de E/S", s["errores_io"] or "ninguno")
    punto(not s["actualizaciones"], "actualizaciones",
          f"{s['actualizaciones']} pendientes" if s["actualizaciones"] else "al dia")
    # Se muestra SIEMPRE, no solo cuando falla: un canal de avisos sano es
    # invisible por diseno (doctrina 3, el silencio es la señal), y algo
    # invisible no se puede comprobar. Esta linea es donde se comprueba.
    av = e.get("avisos")
    if av is None:
        punto(True, "canal de avisos", "sin registro (no corrio todavia)")
    elif av.get("permanente"):
        punto(False, "canal de avisos",
              f"MUERTO — {av.get('ultimo_error') or 'sin detalle'}")
    else:
        m = av.get("min_sin_ciclo")
        punto(m is not None and m < 60, "canal de avisos",
              "vivo" + (f" · ultimo ciclo hace {m:.0f} min" if m is not None else ""))

    print(f"{C['cyan']}Medidores{C['fin']}")
    for k, med in e["medidores"].items():
        txt = med.get("texto") or f"{med['v']:g} {med['u']}".strip()
        print(f"  {k:<17} {barra(med)} {txt:<20} {C['gris']}{med['nota']}{C['fin']}")

    print(f"{C['cyan']}Hardware{C['fin']}")
    v = e.get("ventilador")
    if v is not None:
        ok, txt = texto_ventilador(v)
        c = C["v"] if ok else C["r"]
        print(f"  {c}●{C['fin']} {'ventilador':<22} {barra(medidor_ventilador(v))} {txt}")
    elif e.get("ventilador_rpm") is not None:
        punto(True, "ventilador", f"{e['ventilador_rpm']} rpm")
    lu = color_luces(e.get("luces"))
    if lu:
        regla = (e.get("luces") or {}).get("regla_visible")
        print(f"  {lu[0]} {'luces':<21} {lu[1]}" + (f" · regla {regla}" if regla else ""))
    punto(e["throttled"], "alimentacion",
          "sin limitaciones · nunca se limito" if e["throttled"] else "hubo limitacion")
    punto(not e["nvme_errores"], "NVMe errores", e["nvme_errores"] or "ninguno")

    al = alertas(e)
    if al:
        print(f"\n{C['r']}Requiere atencion{C['fin']}")
        for x in al:
            print(f"  {C['r']}▸{C['fin']} {x['texto']}")
    print()


def texto_telegram(e):
    """El panel completo, para mandar dentro de <pre> en Telegram.

    Mismo contenido que la terminal pero sin colores ANSI —que Telegram muestra
    como basura— y con barras de 10 en vez de 20, para que no se corten en una
    pantalla de celular. El estado se codifica con circulos de color, que es lo
    unico que reemplaza bien al color del texto.
    """
    A = 10

    def bar(med):
        mn = med.get("min", 0)
        v = max(med["v"], mn)
        pct = 0 if med["max"] <= mn else min(100, max(0, int((v - mn) * 100 / (med["max"] - mn))))
        n = pct * A // 100
        return "█" * n + "░" * (A - n)

    def sem(med):
        return "🔴" if med["v"] >= med["ro"] else ("🟡" if med["v"] >= med["am"] else "🟢")

    def p(ok):
        return "🟢" if ok else "🔴"

    al = alertas(e)
    L = []
    cab = "🟢 TODO EN ORDEN" if not al else f"⚠️ {len(al)} REQUIERE(N) ATENCION"
    L.append(cab)
    L.append(f"{e['host']} · {e['momento'][5:16].replace('T', ' ')}")
    L.append(f"encendida hace {e['encendida_hace']}")

    cap = e["captura"]
    L.append("")
    L.append("CAPTURA")
    L.append(f" {p(cap['activo'])} bot {'escuchando' if cap['activo'] else 'APAGADO'}"
             f" · {cap.get('hoy', '?')} notas hoy")
    inb = e.get("inbox", {})
    if inb:
        pen = inb.get("pendientes", 0)
        viej = inb.get("mas_vieja_dias")
        L.append(f" {'🟢' if pen < 25 else '🟡'} {pen} sin procesar"
                 + (f" · mas vieja {viej}d" if viej else "")
                 + (f" · {inb['audios_pendientes']} audios" if inb.get("audios_pendientes") else ""))

    # Se muestra siempre, tambien cuando no hay ninguna: la pregunta "hay un
    # agente corriendo en la Pi?" se contesta con "no" igual que con "si", y un
    # bloque ausente deja al que pregunta sin saber si mirar.
    ag = e.get("agentes", [])
    L.append("")
    L.append("AGENTES")
    if not ag:
        L.append(" ⚪ sin sesiones")
    for a in ag:
        L.append(f" {'🟡' if a['horas'] >= 8 else '🔵'} {a['agente']}"
                 + (f" {a['sub']}" if a["sub"] else "")
                 + f" · hace {a['horas']:.1f} h · pid {a['pid']}")

    L.append("")
    L.append("SERVICIOS")
    caidos = [s for s, ok in e["servicios"].items() if not ok] + \
             [c["nombre"] for c in e["contenedores"] if not c["ok"]]
    if caidos:
        for c in caidos:
            L.append(f" 🔴 {c}")
    else:
        n = len(e["servicios"]) + len(e["contenedores"])
        L.append(f" 🟢 los {n} arriba")
    L.append(f" {p(e['luks']['abierto'])} volumen cifrado "
             f"{'abierto' if e['luks']['abierto'] else 'CERRADO'}")

    L.append("")
    L.append("SINCRONIZACION")
    for c in e["sync"]["carpetas"]:
        L.append(f" {p(c['ok'])} {c['label'][:18]:<18} {c['archivos']:>4} arch"
                 + (f" · faltan {c['faltan']}" if c["faltan"] else ""))
    con = [d["nombre"] for d in e["sync"]["dispositivos"] if d["conectado"]]
    des = [d["nombre"] for d in e["sync"]["dispositivos"] if not d["conectado"]]
    if con:
        L.append(f" 🟢 {', '.join(con)}")
    # Un equipo desconectado NO es una falla: el telefono se va de la red todo
    # el tiempo y el notebook se apaga. Marcarlo en rojo entrena a ignorar los
    # rojos, que es lo contrario de lo que sirve un panel.
    if des:
        L.append(f" ⚪ {', '.join(des)} sin conexion")

    L.append("")
    L.append("RESPALDO")
    r = e["respaldo"]
    if r["montado"]:
        h = r.get("horas")
        L.append(f" {p(h is not None and h < 30)} ultimo hace "
                 + (f"{h:.0f} h" if h is not None else "?"))
        L.append(f" {p(r.get('en_disco_aparte'))} en {r.get('dispositivo', '?')}"
                 f" · {r.get('libre', 0)/2**30:.0f}G libres")
    else:
        L.append(" 🔴 disco NO montado")
    if r.get("proximo"):
        L.append(f"    proximo: {r['proximo']}")

    s = e["salud"]
    L.append("")
    L.append("SALUD")
    L.append(f" {p(not s['unidades_fallidas'])} unidades fallidas: "
             f"{', '.join(s['unidades_fallidas']) or 'ninguna'}")
    L.append(f" {p(s['reloj_ntp'])} reloj {'ok' if s['reloj_ntp'] else 'SIN NTP'}"
             f" · E/S {s['errores_io']} err"
             f" · {s['actualizaciones']} act pend")
    av = e.get("avisos")
    if av is not None:
        m = av.get("min_sin_ciclo")
        if av.get("permanente"):
            L.append(" 🔴 canal de avisos MUERTO: anda a BotFather")
        else:
            L.append(f" {p(m is not None and m < 60)} canal de avisos"
                     + (f" · ciclo hace {m:.0f} min" if m is not None else ""))

    L.append("")
    L.append("MEDIDORES")
    etiq = {"temp_soc": "temp SoC", "temp_nvme": "temp NVMe", "nvme_vida": "NVMe vida",
            "carga": "carga CPU", "memoria": "memoria", "swap": "swap",
            "raiz": "raiz", "datos cifrados": "datos", "disco respaldo": "respaldo"}
    for k, med in e["medidores"].items():
        txt = med.get("texto") or f"{med['v']:g}{med['u']}"
        L.append(f" {sem(med)} {etiq.get(k, k):<10} {bar(med)} {txt}")

    L.append("")
    L.append("HARDWARE")
    v = e.get("ventilador")
    if v is not None:
        ok, txt = texto_ventilador(v)
        med = medidor_ventilador(v)
        L.append(f" {sem(med) if ok else '🔴'} {'ventilador':<10} {bar(med)} {txt}")
    elif e.get("ventilador_rpm") is not None:
        L.append(f" 🟢 ventilador {e['ventilador_rpm']} rpm")
    lu = color_luces(e.get("luces"))
    if lu:
        regla = (e.get("luces") or {}).get("regla_visible")
        L.append(f" {lu[0]} {'luces':<10} {lu[1]}" + (f" · regla {regla}" if regla else ""))
    L.append(f" {p(e['throttled'])} alimentacion "
             f"{'sin limitaciones' if e['throttled'] else 'HUBO LIMITACION'}")

    if al:
        L.append("")
        L.append("REQUIERE ATENCION")
        for x in al:
            L.append(f" ▸ {x['texto']}")
    return "\n".join(L)


def texto_breve(e):
    """Para Telegram: lo que se lee en una pantalla de celular."""
    al = alertas(e)
    L = []
    L.append("✅ Todo en orden" if not al else f"⚠️ {len(al)} cosa(s) requieren atencion")
    cap = e["captura"]
    L.append(f"Capturas hoy: {cap.get('hoy') if cap.get('hoy') is not None else '?'}"
             + ("" if cap["activo"] else "  (BOT APAGADO)"))
    r = e["respaldo"]
    L.append("Respaldo: " + (f"hace {r['horas']:.0f} h" if r.get("horas") is not None
                             else "sin leer"))
    caidos = [s for s, ok in e["servicios"].items() if not ok] + \
             [c["nombre"] for c in e["contenedores"] if not c["ok"]]
    L.append("Servicios: " + ("todos arriba" if not caidos else "CAIDOS: " + ", ".join(caidos)))
    # Aca SOLO si hay algo: /breve tiene que caber en una pantalla de celular, y
    # "sin sesiones de agente" no es noticia. El panel completo de /estado si lo
    # dice siempre.
    ag = e.get("agentes", [])
    if ag:
        L.append("Agentes: " + ", ".join(
            f"{a['agente']}{(' ' + a['sub']) if a['sub'] else ''} ({a['horas']:.0f}h)"
            for a in ag))
    t = e["medidores"].get("temp_soc", {}).get("v")
    dsk = e["medidores"].get("datos cifrados", {}).get("v")
    L.append(f"Temperatura: {t:g} C" if t else "Temperatura: ?")
    L.append(f"Disco de datos: {dsk:g}% usado" if dsk is not None else "")
    if not e["luks"]["abierto"]:
        L.append("🔒 VOLUMEN CIFRADO CERRADO")
    if al:
        L.append("")
        L += [f"• {x['texto']}" for x in al]
    return "\n".join(x for x in L if x)


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


def leer_cache():
    """Devuelve (datos, edad_en_minutos) del JSON del timer, o (None, None).

    Falla en silencio a proposito: el motivo normal de "no se pudo leer" es el
    volumen cifrado cerrado, y de eso se encarga degradado() con algo accionable
    en vez de una traza.
    """
    try:
        edad = (time.time() - os.path.getmtime(CACHE)) / 60
        with open(CACHE) as f:
            return json.load(f), edad
    except Exception:
        return None, None


def nota_edad(edad):
    """Linea de antigüedad del cache. Vacia si viene de una recoleccion en vivo."""
    if not edad:
        return ""
    if edad > MAX_EDAD_MIN:
        return (f"{C['a']}⚠️ DATOS DE HACE {edad:.0f} MIN — el timer no esta al dia. "
                f"Recolecta en vivo con: estado --ahora{C['fin']}")
    return f"{C['gris']}(datos de hace {edad:.0f} min){C['fin']}"


def degradado(modo):
    """Sin cache y sin privilegios. Dice lo unico que importa en ese momento.

    Pasa casi siempre por la misma razon: estado.service tiene RequiresMountsFor
    y con el LUKS cerrado no corre, asi que el archivo ni se renueva ni se puede
    leer —vive adentro del volumen—. Y ese es justo el momento en que uno
    consulta el estado, donde "no pude abrir el archivo" no sirve de nada: lo
    accionable es la orden para abrirlo. `mountpoint` no necesita root.
    """
    montado = subprocess.run(["mountpoint", "-q", DATOS]).returncode == 0
    if not montado:
        txt = "🔒 VOLUMEN CIFRADO CERRADO — corre: sudo abrir-datos"
        al = [{"id": "luks", "texto": "volumen cifrado CERRADO: corre sudo abrir-datos"}]
    else:
        txt = (f"sin datos: {CACHE} no se pudo leer y el volumen SI esta montado.\n"
               "Mira: systemctl status estado.timer estado.service")
        al = [{"id": "estado:sin_cache",
               "texto": f"{CACHE} ilegible con el volumen montado"}]
    if modo == "--json":
        print(json.dumps({"degradado": True, "alertas": al,
                          "_breve": txt, "_telegram": txt}, indent=1))
    else:
        print(txt)
    sys.exit(1)


if __name__ == "__main__":
    args = sys.argv[1:]
    escribir = "--escribir" in args
    modo = "--json" if escribir else next((a for a in args if a != "--ahora"), "")

    if escribir:
        # Lo corre estado.service como root. Nunca se eleva con sudo: si no es root es
        # un error de la unidad y tiene que quedar a la vista, no pedir una contrasena.
        if os.geteuid() != 0:
            sys.exit("estado --escribir solo corre como root (lo lanza estado.service)")
        datos, edad = recolectar(), 0.0
    elif "--ahora" in args:
        # Recolectar SI necesita root. `sudo` sin -n a proposito: que pida la
        # contrasena en vez de fallar en silencio. Y por ruta absoluta, nunca
        # por sys.executable: una regla de sudoers sobre el interprete es
        # permiso para correr python arbitrario como root.
        if os.geteuid() != 0:
            os.execvp("sudo", ["sudo", "/usr/local/bin/estado"] + args)
        datos, edad = recolectar(), 0.0
    else:
        datos, edad = leer_cache()
        if datos is None:
            degradado(modo)

    if modo == "--json":
        # El resumen va YA FORMATEADO dentro del JSON: si el bot lo rearmara por
        # su cuenta, habria dos formatos que se separan con el tiempo y ninguna
        # forma de saber cual es el bueno.
        if "alertas" not in datos:
            datos["alertas"] = alertas(datos)
        if "_breve" not in datos:
            datos["_breve"] = texto_breve(datos)
        if "_telegram" not in datos:
            datos["_telegram"] = texto_telegram(datos)
        datos["edad_min"] = round(edad, 1)
        if escribir:
            try:
                escribir_seguro(CACHE, json.dumps(datos, indent=1, default=str) + "\n")
            except OSError as err:
                sys.exit(f"no pude escribir {CACHE}: {err}")
        else:
            print(json.dumps(datos, indent=1, default=str))
    elif modo == "--breve":
        print(datos.get("_breve") or texto_breve(datos))
    elif modo == "--telegram":
        print(datos.get("_telegram") or texto_telegram(datos))
    else:
        n = nota_edad(edad)
        if n:
            print(n)
        texto_completo(datos)
