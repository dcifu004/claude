#!/usr/bin/env python3
"""Recolector de tareas programadas de la Pi (encargo 22, documento 29).

    python3 programados.py            # JSON por stdout; lo llama la pestaña ⏰ con cockpit.spawn
    python3 programados.py --indent   # lo mismo, legible

Sólo lectura, sin `sudo`, sólo stdlib. Junta:
  - timers de systemd del sistema y del usuario (`list-timers` + `list-unit-files` + `show`);
  - cron: /etc/crontab, /etc/cron.d/*, /etc/cron.{hourly,daily,weekly,monthly}/* y `crontab -l`;
  - los temporizadores del bot (casa/temporizadores.json).
Lo que no se puede ver desde acá va en `no_visibles`, con su motivo.

Regla dura: de `Environment=` y `EnvironmentFile=` sale sólo el NOMBRE de las variables o la
RUTA del archivo, nunca un valor. Lo que parezca un token (hex o base64 largo, `123456:AA…`) se
enmascara en el comando y en el journal.

Todo lo que toca el sistema pasa por un objeto `Fuentes`; las pruebas (test_programados.py)
ponen uno falso que lee muestras reales guardadas en pi/fixtures/programados/.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEMPORIZADORES = Path(os.environ.get("BOTV3_CASA_DIR", "/opt/nodo/datos/casa")) / "temporizadores.json"
JOURNAL_LINEAS = 5
JOURNAL_ANCHO = 200
GRACIA_BOT = 300      # igual que botv3/temporizadores.GRACIA: más tarde que eso ya no suena
DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"]
DIAS_INGLES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
MESES_INGLES = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
DIRS_CRON = ["hourly", "daily", "weekly", "monthly"]
CADA_DIR = {"hourly": "cada hora", "daily": "todos los días", "weekly": "una vez por semana",
            "monthly": "una vez al mes"}

PROPS_TIMER = ("Id,Description,LoadState,ActiveState,UnitFileState,FragmentPath,Unit,TimersCalendar,"
               "TimersMonotonic,Persistent,RandomizedDelayUSec")
PROPS_SERVICIO = ("Id,Description,LoadState,ActiveState,Result,ExecMainStatus,ExecMainStartTimestamp,"
                  "ExecMainExitTimestamp,User,ExecStart,FragmentPath,EnvironmentFiles,Environment")
TIMER_PROTEGIDOS = {
    "respaldo": "es el respaldo; no se pausa desde el navegador",
    "avisos": "es el que avisa si algo se cae",
    "logrotate": "está protegido por seguridad del sistema",
    "fstrim": "está protegido por seguridad del sistema",
    "man-db": "está protegido por seguridad del sistema",
    "rpi-zram-writeback": "está protegido por seguridad del sistema",
}
TIMER_PROTEGIDOS_PREFIJOS = ("apt-", "dpkg-", "e2scrub", "systemd-")


# ---------------------------------------------------------------------------
# Lista blanca para lo que se publica
# ---------------------------------------------------------------------------

OCULTO = "«oculto»"
_PALABRA = re.compile(r"^[\wÀ-ÿ]+(?:[._-][\wÀ-ÿ]+)*$", re.UNICODE)
_NUMERO = re.compile(r"^\d+(?:[.:/-]\d+)*$" )
_FECHA_HORA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2})?$")
_RUTA = re.compile(r"^(?:/|~/|\./)[^\s]+$")
_PUNTUACION = re.compile(r"^[\[\](){},:;.!?%+*&|=@#'\"`…–—<>/-]+$")
_TRAMOS = re.compile(r"[\w]+", re.UNICODE)
_SEGMENTO_RUTA = re.compile(r"^\.?[\wÀ-ÿ]+(?:[._-][\wÀ-ÿ]+)*$", re.UNICODE)
_NOMBRE_SENSIBLE = re.compile(
    r"(?i)(?:token|key|secret|password|pass|pwd|auth|authorization|bearer|api)")
_ESTRUCTURA_JOURNAL = re.compile(
    r"(?:pam_unix\([\wÀ-ÿ:]+\)|[\wÀ-ÿ]+\(uid=\d+\))[.,:;)]*", re.UNICODE)


def _duro_sospechoso(token: str) -> bool:
    """Detecta longitudes y segmentación sospechosa antes de reconocer una forma."""
    # El límite es por corrida alfanumérica: los guiones sí separan palabras legibles,
    # pero no deben permitir una palabra larga escondida entre separadores.
    tramos = _TRAMOS.findall(token)
    estructura_legible = _ESTRUCTURA_JOURNAL.fullmatch(token)
    estructura_uid = re.fullmatch(r"[\wÀ-ÿ]+\([\wÀ-ÿ]+=\d+\)[.,:;)]*", token, re.UNICODE)
    if any(len(tramo) > 16 for tramo in tramos):
        return True
    if estructura_legible or estructura_uid:
        return False
    compacto = "".join(tramos)
    unidad_legible = re.fullmatch(
        r"[\wÀ-ÿ]+(?:-[\wÀ-ÿ]+)*\.(?:service|timer|mount|socket|target|path|slice|scope)[.,:;)]*",
        token, re.UNICODE)
    if len(compacto) > 16 and not (unidad_legible or estructura_legible):
        return True
    mezclados = [bool(re.search(r"\D", t, re.UNICODE)) and bool(re.search(r"\d", t)) for t in tramos]
    return len(tramos) >= 3 and sum(mezclados) >= 1


def _tramos_sospechosos(token: str) -> bool:
    """Aplica las dos reglas duras a una pieza que no es una forma especial."""
    tramos = _TRAMOS.findall(token)
    if any(len(t) > 16 for t in tramos):
        return True
    letras_digitos = [bool(re.search(r"[A-Za-zÀ-ÿ]", t)) and bool(re.search(r"\d", t)) for t in tramos]
    return sum(letras_digitos) >= 3 or (len(tramos) >= 3 and any(letras_digitos))


def _ruta_segmentada_sospechosa(partes: list[str]) -> bool:
    """Oculta cuatro segmentos consecutivos que mezclan letras y dígitos.

    Es una ruta improbable para los comandos de la Pi, pero permite partir un
    secreto en trozos cortos que, aislados, parecen nombres legibles.
    """
    seguidos = 0
    for parte in partes:
        mezcla = bool(re.search(r"[A-Za-zÀ-ÿ]", parte)) and bool(re.search(r"\d", parte))
        seguidos = seguidos + 1 if mezcla else 0
        if seguidos >= 4:
            return True
    return False


def _limpiar_envoltorio(token: str) -> str:
    """Quita sólo puntuación que envuelve un token de journal o JSON."""
    # No se quita `:`: distingue formas reales como `systemd[1]:` y también
    # permite saber que `password:` espera un valor en el token siguiente.
    return token.strip(".,;!?([{)]}»'\"")


def _token_seguro(token: str) -> bool:
    """True sólo para tokens cuya forma tiene un uso visible y reconocible."""
    if not token or token in {OCULTO, "«equipo»"}:
        return True
    # Las comillas de JSON/journal no cambian la naturaleza de una ruta. Hay que
    # quitarlas antes de aplicar las reglas duras, o una ruta larga entre comillas
    # se vuelve opaca por su longitud total.
    # Sólo comillas aquí: quitar `)` o `:` antes de reconocer las estructuras
    # del journal rompería `dcifu004(uid=1000)` y `systemd[1]:`.
    borde = token.strip("'\"")
    if borde != token:
        return bool(borde) and _token_seguro(borde)
    # Las rutas son una forma segura sólo si cada segmento es legible; no se concatena
    # la ruta completa, porque una ruta real puede tener muchos segmentos cortos.
    es_ruta = token == "/" or bool(_RUTA.fullmatch(token))
    borde_inicial = token.strip(".,:;!?)]}»")
    if re.fullmatch(r"[\wÀ-ÿ.-]+\[\d+\]", borde_inicial, re.UNICODE) or re.fullmatch(
            r"[\wÀ-ÿ.-]+\[\d+\]:", token, re.UNICODE):
        return True
    if _FECHA_HORA.fullmatch(token):
        return True
    if not es_ruta and _duro_sospechoso(token):
        return False
    if re.match(r"(?i)^(?:sk|pk|rk)-|^gh[pousr]_|^github_pat_|^xox[abprs]-|^AKIA|^eyJ|^\d{6,}:", token):
        return False
    if _PUNTUACION.fullmatch(token) or _NUMERO.fullmatch(token):
        return True
    if re.fullmatch(r"(?i)authorization:(?:bearer|basic|token)(?:[=:].*)?", token):
        return False
    if re.fullmatch(r"[\wÀ-ÿ]+\[\d+\]", token, re.UNICODE):
        return True
    estructura_uid = re.fullmatch(r"[\wÀ-ÿ]+\([\wÀ-ÿ]+=\d+\)[.,:;)]*", token, re.UNICODE)
    if estructura_uid:
        return True
    if _ESTRUCTURA_JOURNAL.fullmatch(token):
        return True
    # Tras reconocer las estructuras con dos puntos/paréntesis, la puntuación
    # terminal vuelve a ser sólo envoltorio (`restic.`, `estado.json;`).
    borde = token.strip(".,:;!?([{)]}»'\"")
    if borde != token:
        return bool(borde) and _token_seguro(borde)
    # Formas reales de journal como pam_unix(runuser:session):. Se aceptan sólo
    # piezas legibles; los límites duros ya se aplicaron al token completo.
    if _ESTRUCTURA_JOURNAL.fullmatch(token) or estructura_uid:
        piezas = re.findall(r"[\wÀ-ÿ]+", token, re.UNICODE)
        return bool(piezas) and all(_PALABRA.fullmatch(pieza) or _NUMERO.fullmatch(pieza) for pieza in piezas)
    if es_ruta:
        if ":" in token:
            return all(_token_seguro(pieza) for pieza in token.split(":"))
        partes = token[2:] if token.startswith("~/") else token[2:] if token.startswith("./") else token[1:]
        segmentos = [p for p in partes.split("/") if p]
        return (not _ruta_segmentada_sospechosa(segmentos)
                and all(not _tramos_sospechosos(p)
                   and not ("-" not in p and "_" not in p and len(p) >= 14
                            and re.search(r"[A-Z].*\d|\d.*[A-Z]", p))
                   and _SEGMENTO_RUTA.fullmatch(p) for p in segmentos))
    if re.fullmatch(r"[\wÀ-ÿ]+:(?:/|~/|\./)[^\s]+", token, re.UNICODE):
        prefijo, ruta = token.split(":", 1)
        return bool(_PALABRA.fullmatch(prefijo)) and _token_seguro(ruta)
    if token.startswith("--") or (token.startswith("-") and len(token) > 1):
        cuerpo = token.lstrip("-")
        if "=" in cuerpo:
            nombre, valor = cuerpo.split("=", 1)
            return (bool(_PALABRA.fullmatch(nombre)) and not _nombre_sensible(nombre)
                    and _token_seguro(valor))
        if token.lower() == "-pw":
            return True
        if token.startswith("-") and not token.startswith("--") and re.match(r"(?i)^p.+", cuerpo):
            return False
        return bool(_PALABRA.fullmatch(cuerpo)) and not _tramos_sospechosos(cuerpo)
    if "=" in token:
        nombre, valor = token.split("=", 1)
        return (bool(_PALABRA.fullmatch(nombre)) and not _tramos_sospechosos(nombre)
                and not _nombre_sensible(nombre) and _token_seguro(valor))
    if _PALABRA.fullmatch(token):
        return not _tramos_sospechosos(token)
    # Hora/fecha y nombres de unidad con puntuación común ya quedan cubiertos arriba;
    # cualquier otra mezcla opaca se oculta completa.
    return False


def _nombre_sensible(nombre: str) -> bool:
    """Nombres de campos cuyo valor no aporta información visible."""
    return bool(_NOMBRE_SENSIBLE.search(nombre))


def _marca_valor_sensible(token: str) -> bool:
    """Indica que el próximo token es el valor de una opción sensible."""
    limpio = _limpiar_envoltorio(token)
    if limpio.lower() in {"-p", "--p", "-pw"}:
        return True
    nombre_con_dos_puntos = limpio.rstrip(":").strip("'\"")
    if limpio.endswith(":") and _nombre_sensible(nombre_con_dos_puntos):
        return True
    if limpio.startswith("--"):
        nombre = limpio[2:].split("=", 1)[0]
        return _nombre_sensible(nombre)
    return False


def _clave_autorizacion(token: str) -> bool:
    """Distingue `Authorization: Basic valor` de una clave con valor directo."""
    return _limpiar_envoltorio(token).rstrip(":").strip("'\"").lower() == "authorization"


def enmascarar(texto: str) -> str:
    """Publica sólo tokens reconocibles; todo token restante se reemplaza completo."""
    if not texto:
        return texto
    partes = re.split(r"(\s+)", texto)
    anterior = ""
    salida = []
    for parte in partes:
        if not parte or parte.isspace():
            salida.append(parte)
            continue
        previo = _limpiar_envoltorio(anterior)
        es_esquema = _limpiar_envoltorio(parte).lower() in {"bearer", "basic", "token"}
        ocultar = (previo.lower() in {"bearer", "basic", "token"}
                   or re.search(r"(?i):(bearer|basic|token)$", previo) is not None
                   or (_marca_valor_sensible(anterior)
                       and not (es_esquema and _clave_autorizacion(anterior)))
                   or re.match(r"(?i)^authorization:(?:bearer|basic|token)(?:[=:]|$)", parte) is not None)
        salida.append(OCULTO if ocultar or not _token_seguro(parte) else parte)
        anterior = parte
    return "".join(salida)


def recortar(linea: str, ancho: int = JOURNAL_ANCHO) -> str:
    linea = linea.rstrip()
    # short-iso: el host de la Pi identifica a una persona y no aporta a la pestaña.
    linea = re.sub(r"^(\S+\s+)\S+(\s+)(?=\S+\[\d+\]:)", r"\1«equipo»\2", linea)
    linea = enmascarar(linea)
    return linea if len(linea) <= ancho else linea[: ancho - 1] + "…"


# ---------------------------------------------------------------------------
# Lo que lee el sistema
# ---------------------------------------------------------------------------

class Fuentes:
    """Todo lo que toca la máquina. Argumentos fijos, sin shell, con tiempo límite."""

    def __init__(self):
        self.entorno = dict(os.environ)
        self.entorno.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

    def _correr(self, args: list[str], tiempo: int = 15) -> str | None:
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=tiempo, env=self.entorno)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return r.stdout if r.returncode == 0 else None

    def _systemctl(self, ambito: str) -> list[str]:
        return ["systemctl"] + (["--user"] if ambito == "usuario" else [])

    def list_timers(self, ambito: str) -> str | None:
        return self._correr(self._systemctl(ambito) + ["list-timers", "--all", "--no-pager", "-o", "json"])

    def list_timer_units(self, ambito: str) -> str | None:
        return self._correr(self._systemctl(ambito) + ["list-unit-files", "--type=timer", "--all", "--no-pager", "-o", "json"])

    def show(self, ambito: str, unidades: list[str], props: str) -> str | None:
        return self._correr(self._systemctl(ambito) + ["show", "--timestamp=unix", "--no-pager",
                                                       "-p", props] + unidades)

    def journal(self, ambito: str, unidad: str, n: int) -> str:
        args = ["journalctl"] + (["--user"] if ambito == "usuario" else []) + \
               ["-u", unidad, "-n", str(n), "--no-pager", "-o", "short-iso"]
        return self._correr(args) or ""

    def leer(self, ruta: str) -> str | None:
        try:
            return Path(ruta).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def listar(self, ruta: str) -> list[str]:
        try:
            return sorted(p.name for p in Path(ruta).iterdir())
        except OSError:
            return []

    def existe(self, ruta: str) -> bool:
        return os.path.exists(ruta)

    def legible(self, ruta: str) -> bool:
        return os.access(ruta, os.R_OK)

    def crontab_usuario(self) -> str | None:
        return self._correr(["crontab", "-l"])

    def usuario(self) -> str:
        return os.environ.get("USER") or os.environ.get("LOGNAME") or str(os.getuid())

    def ahora(self) -> datetime:
        return datetime.now(timezone.utc).astimezone()


# ---------------------------------------------------------------------------
# Traducir expresiones a español
# ---------------------------------------------------------------------------

def hhmm(h: int, m: int, s: int = 0) -> str:
    return f"{h:02d}:{m:02d}" + (f":{s:02d}" if s else "")


def dur_es(texto: str) -> str:
    """'1h 40min' → '1 h 40 min'; '1d' → '1 d'."""
    return re.sub(r"(\d+(?:\.\d+)?)\s*(us|ms|s|min|h|d|w|month|y)\b",
                  lambda m: f"{m.group(1)} {m.group(2)}", texto.strip())


def _lista(campo: str) -> list[str]:
    return campo.split(",")


def _dias_es(spec: str) -> str | None:
    """'Sat' → 'sáb'; 'Mon..Fri' → 'lun–vie'; 'Mon,Tue' → 'lun, mar'."""
    partes = []
    for p in _lista(spec):
        a, _, b = p.partition("..")
        if a.lower()[:3] not in DIAS_INGLES or (b and b.lower()[:3] not in DIAS_INGLES):
            return None
        partes.append(DIAS[DIAS_INGLES[a.lower()[:3]]] + (f"–{DIAS[DIAS_INGLES[b.lower()[:3]]]}" if b else ""))
    return ", ".join(partes)


def legible_calendar(expr: str) -> str:
    """OnCalendar= → español. Lo que no reconoce vuelve tal cual, entre comillas."""
    e = expr.strip()
    atajos = {"minutely": "cada minuto", "hourly": "cada hora", "daily": "todos los días a las 00:00",
              "weekly": "los lunes a las 00:00", "monthly": "el día 1 de cada mes a las 00:00",
              "quarterly": "el día 1 de enero, abril, julio y octubre a las 00:00",
              "semiannually": "el día 1 de enero y julio a las 00:00", "yearly": "el 1 de enero a las 00:00",
              "annually": "el 1 de enero a las 00:00"}
    if e.lower() in atajos:
        return atajos[e.lower()]
    toks = e.split()
    dias = None
    if toks and re.match(r"(?i)^[a-z]{3}", toks[0]) and not re.match(r"^\d", toks[0]):
        dias = _dias_es(toks[0])
        if dias is None:
            return f"«{e}»"
        toks = toks[1:]
    fecha, hora = "*-*-*", "00:00:00"
    for t in toks:
        if ":" in t:
            hora = t
        elif "-" in t:
            fecha = t
    partes_hora = hora.split(":")
    while len(partes_hora) < 3:
        partes_hora.append("00")
    h, m, s = partes_hora[:3]
    partes_fecha = fecha.split("-")
    if len(partes_fecha) == 2:           # MM-DD
        partes_fecha = ["*"] + partes_fecha
    if len(partes_fecha) != 3:
        return f"«{e}»"
    anio, mes, dia = partes_fecha
    num = lambda x: re.fullmatch(r"\d+", x) is not None
    s_txt = int(s) if num(s) else None

    # Cuándo, en horas y minutos.
    if h == "*" and m.startswith("00/") and num(m[3:]) and s_txt == 0:
        cuando = f"cada {m[3:]} min"
    elif h == "*" and "/" in m and num(m.split("/")[1]) and s_txt == 0:
        cuando = f"cada {m.split('/')[1]} min"
    elif h == "*" and num(m) and s_txt == 0:
        cuando = "cada hora" if int(m) == 0 else f"cada hora, al minuto {int(m)}"
    elif "/" in h and num(h.split("/")[1]) and num(m) and s_txt is not None:
        paso = int(h.split("/")[1])
        cuando = f"cada {paso} h" + ("" if int(m) == 0 and s_txt == 0 else f" (minuto {int(m)})")
    elif all(num(x) for x in _lista(h)) and num(m) and s_txt is not None:
        horas = [hhmm(int(x), int(m), s_txt) for x in _lista(h)]
        cuando = "a las " + (horas[0] if len(horas) == 1 else ", ".join(horas[:-1]) + " y " + horas[-1])
    else:
        return f"«{e}»"

    if dias:
        return f"{dias} {cuando.removeprefix('a las ')}" if cuando.startswith("a las ") else f"{dias}, {cuando}"
    if anio == "*" and mes == "*" and dia == "*":
        return cuando if cuando.startswith("cada") else f"todos los días {cuando}"
    if anio == "*" and mes == "*" and num(dia):
        return f"el día {int(dia)} de cada mes {cuando}"
    if num(anio) and num(mes) and num(dia):
        f = f"{int(dia):02d}-{int(mes):02d}-{anio}"
        return f"una vez, el {f} {cuando}" if cuando.startswith("a las") else f"el {f}, {cuando}"
    return f"«{e}»"


def _unir_legibles(textos: list[str]) -> str:
    """Varias OnCalendar de un timer: si todas son «todos los días a las X», una sola frase."""
    pref = "todos los días a las "
    if len(textos) > 1 and all(t.startswith(pref) for t in textos):
        horas = sorted(t[len(pref):] for t in textos)
        return pref + ", ".join(horas[:-1]) + " y " + horas[-1]
    una = [t for t in textos if t.startswith("una vez, el ")]
    if len(una) > 1 and len(una) == len(textos):
        return "fechas fijas: " + ", ".join(t.removeprefix("una vez, el ").replace(" a las ", " ") for t in una)
    return "; ".join(textos)


MONOTONICOS = {"OnBootUSec": "tras el arranque", "OnStartupUSec": "tras iniciar systemd",
               "OnActiveUSec": "tras activarse el timer", "OnUnitInactiveUSec": "tras terminar la última corrida"}


def legible_monotonico(items: list[tuple[str, str]]) -> str:
    cada = [dur_es(v) for k, v in items if k == "OnUnitActiveUSec"]
    otros = [f"{dur_es(v)} {MONOTONICOS[k]}" for k, v in items if k in MONOTONICOS]
    if cada:
        return ("cada día" if cada[0] == "1 d" else f"cada {cada[0]}") + (f" (la primera, {otros[0]})" if otros else "")
    return "; ".join(otros)


# ---------------------------------------------------------------------------
# cron
# ---------------------------------------------------------------------------

_LIMITES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
ATAJOS_CRON = {"@hourly": "0 * * * *", "@daily": "0 0 * * *", "@midnight": "0 0 * * *",
               "@weekly": "0 0 * * 0", "@monthly": "0 0 1 * *", "@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *"}


def _campo_cron(campo: str, i: int) -> set[int] | None:
    lo, hi = _LIMITES[i]
    valores: set[int] = set()
    for parte in campo.split(","):
        rango, _, paso = parte.partition("/")
        if not paso.isdigit() and paso:
            return None
        paso_n = int(paso) if paso else 1
        if paso_n < 1:
            return None
        if rango == "*":
            a, b = lo, hi
        else:
            a_s, _, b_s = rango.partition("-")

            def conv(x):
                x = x.lower()
                if i == 3 and x[:3] in MESES_INGLES:
                    return MESES_INGLES[x[:3]]
                if i == 4 and x[:3] in DIAS_INGLES:
                    return DIAS_INGLES[x[:3]]
                return int(x) if x.isdigit() else None
            a = conv(a_s)
            b = conv(b_s) if b_s else (hi if paso else a)
            if a is None or b is None:
                return None
        if a < lo or b > hi or a > b:
            return None
        valores.update(range(a, b + 1, paso_n))
    if i == 4:
        valores = {v % 7 for v in valores}
    return valores


def parsear_cron(campos: list[str]) -> list[set[int]] | None:
    if len(campos) != 5:
        return None
    r = [_campo_cron(c, i) for i, c in enumerate(campos)]
    return None if any(x is None for x in r) else r  # type: ignore[return-value]


def proxima_cron(campos: list[str], desde: datetime) -> datetime | None:
    """Próximo minuto, estrictamente posterior a `desde`, que cumple los cinco campos."""
    p = parsear_cron(campos)
    if not p:
        return None
    minutos, horas, doms, meses, dows = p
    dom_libre, dow_libre = campos[2] == "*", campos[4] == "*"
    dia = desde.replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(0, 800):
        ok_dom, ok_dow = dia.day in doms, (dia.isoweekday() % 7) in dows
        ok_dia = (ok_dom or ok_dow) if not dom_libre and not dow_libre else (ok_dom and ok_dow)
        if dia.month in meses and ok_dia:
            for h in sorted(horas):
                for m in sorted(minutos):
                    cand = dia.replace(hour=h, minute=m)
                    if cand > desde:
                        return cand
        dia += timedelta(days=1)
    return None


def legible_cron(campos: list[str]) -> str:
    raw = " ".join(campos)
    if len(campos) != 5:
        return f"«{raw}»"
    m, h, dom, mes, dow = campos
    if mes != "*":
        return f"«{raw}»"
    paso = re.fullmatch(r"\*/(\d+)", m)
    if paso and h == "*" and dom == "*" and dow == "*":
        return f"cada {paso.group(1)} min"
    if m.isdigit() and h == "*" and dom == "*" and dow == "*":
        return "cada hora" if int(m) == 0 else f"cada hora, al minuto {int(m)}"
    if m.isdigit() and h.isdigit():
        t = hhmm(int(h), int(m))
        if dom == "*" and dow == "*":
            return f"todos los días a las {t}"
        if dom == "*" and re.fullmatch(r"[0-7]", dow):
            return f"{DIAS[int(dow) % 7]} {t}"
        if dow == "*" and dom.isdigit():
            return f"el día {int(dom)} de cada mes a las {t}"
    return f"«{raw}»"


def _epoch_local(texto: str | None) -> datetime | None:
    if not texto or texto in ("n/a", "0"):
        return None
    if texto.startswith("@") and texto[1:].isdigit():
        return datetime.fromtimestamp(int(texto[1:]), timezone.utc).astimezone()
    if texto.isdigit():
        return datetime.fromtimestamp(int(texto) / 1e6, timezone.utc).astimezone()
    return None


# ---------------------------------------------------------------------------
# systemctl show
# ---------------------------------------------------------------------------

def parsear_show(texto: str | None) -> dict[str, dict[str, list[str]]]:
    """Salida de `systemctl show` con varias unidades (bloques separados por línea en blanco)
    → {Id: {clave: [valores]}}. Las claves repetidas (TimersCalendar, Environment…) suman."""
    r: dict[str, dict[str, list[str]]] = {}
    for bloque in re.split(r"\n\s*\n", texto or ""):
        d: dict[str, list[str]] = {}
        for linea in bloque.splitlines():
            if "=" in linea:
                k, _, v = linea.partition("=")
                d.setdefault(k, []).append(v)
        if "Id" in d:
            r[d["Id"][0]] = d
    return r


def _uno(d: dict[str, list[str]], k: str) -> str:
    return (d.get(k) or [""])[0]


def calendarios(timer: dict[str, list[str]]) -> list[str]:
    return [m.group(1) for v in timer.get("TimersCalendar", []) if (m := re.match(r"\{ OnCalendar=(.*?) ;", v))]


def monotonicos(timer: dict[str, list[str]]) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for v in timer.get("TimersMonotonic", [])
            if (m := re.match(r"\{ (\w+)=(.*?) ;", v))]


def comando_de(servicio: dict[str, list[str]]) -> str | None:
    for v in servicio.get("ExecStart", []):
        m = re.search(r"argv\[\]=(.*?) ; ignore_errors=", v)
        if m:
            return enmascarar(m.group(1).strip())
    return None


def entorno_de(servicio: dict[str, list[str]]) -> dict[str, list[str]]:
    """Sólo nombres de variables y rutas de archivos; los valores no salen del parser."""
    nombres: list[str] = []
    for v in servicio.get("Environment", []):
        try:
            partes = shlex.split(v)
        except ValueError:
            partes = v.split()
        nombres += [p.split("=", 1)[0] for p in partes if "=" in p]
    archivos = []
    for v in servicio.get("EnvironmentFiles", []):
        ruta = re.sub(r"\s*\(ignore_errors=\w+\)\s*$", "", v).strip()
        if ruta:
            archivos.append(ruta)
    return {"variables": nombres, "archivos": archivos}


PROYECTOS = [  # (patrón sobre nombre + comando + ruta de la unidad, proyecto)
    (r"botv3|dcs_v3bot|temporizador", "bot"),
    (r"noticias|13-Agente-Noticias", "noticias"),
    (r"respaldo|restic", "respaldo"),
    (r"(^|[/\s-])(estado|avisos|uso)([.\s-]|$)", "panel de estado"),
    (r"desplegar", "despliegue"),
    (r"(^|[/\s-])cola-?\d+", "encargos"),
    (r"luces", "luces"),
]


def deducir_proyecto(*pistas: str | None) -> str | None:
    texto = " ".join(p for p in pistas if p)
    for patron, nombre in PROYECTOS:
        if re.search(patron, texto, re.I):
            return nombre
    return None


def habilitado_de(estado_archivo: str) -> bool | None:
    if not estado_archivo:
        return None
    return estado_archivo.startswith("enabled") or estado_archivo in ("static", "generated", "transient", "alias")


def _unidad_timer(x: dict) -> str | None:
    # list-timers usa «unit»; list-unit-files usa «unit_file» (systemd 257, muestra real).
    return x.get("unit") or x.get("unit_file") or x.get("UNIT") or x.get("Unit")


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


# ---------------------------------------------------------------------------
# Tareas
# ---------------------------------------------------------------------------

def tarea_base(**campos) -> dict:
    base = {"fuente": None, "nombre": None, "descripcion": None, "expresion": None, "legible": None,
            "proxima": None, "ultima": None, "resultado": None, "codigo_salida": None, "duracion_s": None,
            "usuario": None, "comando": None, "unidad": None, "persistente": None, "habilitado": None,
            "journal": [], "proyecto": None, "estado": "al_dia", "motivo": None, "banderas": [],
            "identificador": None, "acciones": None, "protegido": False, "motivo_accion": None,
            "entorno": {"variables": [], "archivos": []}}
    base.update(campos)
    return base


def timers_de(f: Fuentes, ambito: str, ahora: datetime) -> list[dict]:
    crudo = f.list_timers(ambito)
    if crudo is None:
        raise RuntimeError("systemctl list-timers no respondió")
    lista = json.loads(crudo or "[]")
    por_unidad = {_unidad_timer(t): t for t in lista if _unidad_timer(t)}
    try:
        archivos = json.loads(f.list_timer_units(ambito) or "[]")
    except (AttributeError, TypeError, ValueError):
        archivos = []
    for item in archivos:
        unidad = _unidad_timer(item)
        if unidad and unidad.endswith(".timer"):
            por_unidad.setdefault(unidad, {"unit": unidad, "activates": None, "next": None, "last": None})
    lista = list(por_unidad.values())
    unidades_timer = [t["unit"] for t in lista if t.get("unit")]
    # Un timer que solo sale en list-unit-files (deshabilitado) no trae «activates»: se pide el
    # servicio por defecto y, si el timer dice otro en `Unit=`, se pide en una segunda vuelta.
    servicios = [t.get("activates") or t["unit"].removesuffix(".timer") + ".service" for t in lista if t.get("unit")]
    props = PROPS_TIMER + "," + PROPS_SERVICIO
    show = parsear_show(f.show(ambito, unidades_timer + servicios, props)) if unidades_timer else {}
    otros = sorted({_uno(show.get(u, {}), "Unit") for u in unidades_timer} - set(show) - {""})
    if otros:
        show.update(parsear_show(f.show(ambito, otros, props)))
    fuente = "timer del sistema" if ambito == "sistema" else "timer de usuario"
    usuario_def = "root" if ambito == "sistema" else f.usuario()

    def una(t: dict) -> dict:
        nombre_timer = t["unit"]
        timer = show.get(nombre_timer, {})
        nombre_srv = t.get("activates") or _uno(timer, "Unit") or None
        srv = show.get(nombre_srv, {}) if nombre_srv else {}
        proxima, ultima = _epoch_local(str(t["next"])) if t.get("next") else None, \
            _epoch_local(str(t["last"])) if t.get("last") else None
        cals, mono = calendarios(timer), monotonicos(timer)
        crudo_expr = "; ".join([f"OnCalendar={c}" for c in cals] +
                               [f"{k.replace('USec', 'Sec')}={v}" for k, v in mono])
        legible = _unir_legibles([legible_calendar(c) for c in cals]) if cals else ""
        if mono:
            legible = "; ".join(x for x in (legible, legible_monotonico(mono)) if x)
        comando = comando_de(srv)
        usuario = _uno(srv, "User") or usuario_def
        inicio, fin = _epoch_local(_uno(srv, "ExecMainStartTimestamp")), _epoch_local(_uno(srv, "ExecMainExitTimestamp"))
        duracion = round((fin - inicio).total_seconds(), 1) if inicio and fin and fin >= inicio else None
        codigo = _uno(srv, "ExecMainStatus")
        resultado = _uno(srv, "Result") or None
        activo_srv = _uno(srv, "ActiveState")
        carga_srv = _uno(srv, "LoadState")

        motivos: list[str] = []
        estado = "al_dia"
        if not nombre_srv or nombre_srv not in show or carga_srv == "not-found":
            estado = "huerfano"
            motivos.append(f"El timer apunta a {nombre_srv or '(nada)'} y esa unidad no existe.")
        fallo_srv = (resultado not in (None, "success")) or activo_srv == "failed"
        if estado == "huerfano":
            pass
        elif fallo_srv:
            estado = "fallo"
            motivos.append(f"La última corrida terminó con «{resultado}»" +
                           (f" (código {codigo})." if codigo not in ("", "0") else "."))
        unidad_estado = _uno(timer, "UnitFileState")
        pausado = unidad_estado == "disabled" and _uno(timer, "ActiveState") != "active"
        if pausado:
            estado = "pausado"
            motivos.append("El timer está deshabilitado: lo pausó alguien o nunca se habilitó. "
                           "Reanudar lo habilita y lo arranca.")
        elif proxima is None:
            solo_fechas = bool(cals) and not mono and all(re.match(r"^\d{4}-\d\d-\d\d", c) for c in cals)
            motivos.append("Sólo tenía fechas fijas y ya pasaron: no va a volver a correr."
                           if solo_fechas else "No tiene próxima corrida.")
            if estado == "al_dia":
                estado = "vencido"
        if estado == "al_dia" and ultima is None and inicio is None:
            estado = "nunca"
            motivos.append("Todavía no ha corrido.")
        sub = _uno(timer, "ActiveState")
        if sub and sub != "active":
            motivos.append(f"El timer está {sub}.")
        proyecto = deducir_proyecto(nombre_timer, comando, _uno(srv, "FragmentPath"))
        banderas = [b for b, cond in (("huerfano", estado == "huerfano"), ("fallo", estado == "fallo" or fallo_srv),
                                      ("vencido", proxima is None and estado != "pausado")) if cond]
        base_timer = nombre_timer.removesuffix(".timer")
        motivo_protegido = TIMER_PROTEGIDOS.get(base_timer)
        if motivo_protegido is None and any(base_timer.startswith(p) for p in TIMER_PROTEGIDOS_PREFIJOS):
            motivo_protegido = "está protegido por seguridad del sistema"
        return tarea_base(
            fuente=fuente, nombre=nombre_timer.removesuffix(".timer"),
            descripcion=_uno(srv, "Description") or _uno(timer, "Description") or None,
            expresion=crudo_expr or None, legible=legible or None, proxima=iso(proxima), ultima=iso(ultima),
            resultado=resultado if carga_srv != "not-found" else None,
            codigo_salida=int(codigo) if codigo.isdigit() and inicio else None, duracion_s=duracion,
            usuario=usuario, comando=comando, unidad=_uno(srv, "FragmentPath") or _uno(timer, "FragmentPath") or None,
            persistente=_uno(timer, "Persistent") == "yes" if _uno(timer, "Persistent") else None,
            habilitado=habilitado_de(unidad_estado), proyecto=proyecto, estado=estado,
            motivo=" ".join(motivos) or None, banderas=banderas, entorno=entorno_de(srv),
            protegido=bool(motivo_protegido), motivo_accion=motivo_protegido,
            servicio=nombre_srv, _ambito=ambito)

    with ThreadPoolExecutor(max_workers=6) as pool:
        tareas = list(pool.map(una, lista))

    def diario(t: dict) -> list[str]:
        if not t.get("servicio") or t["estado"] == "huerfano":
            return []
        return [recortar(x) for x in f.journal(ambito, t["servicio"], JOURNAL_LINEAS).splitlines()
                if x.strip() and not x.startswith("-- ")][-JOURNAL_LINEAS:]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for t, j in zip(tareas, pool.map(diario, tareas)):
            t["journal"] = j
    for t in tareas:
        t.pop("_ambito", None)
    return tareas


# --- cron ------------------------------------------------------------------

def _lineas_cron(texto: str | None) -> list[str]:
    return [l.strip() for l in (texto or "").splitlines() if l.strip() and not l.strip().startswith("#")]


def tareas_de_crontab(texto: str | None, origen: str, ahora: datetime, con_usuario: bool,
                      usuario_def: str, f: Fuentes) -> list[dict]:
    r = []
    anacron = f.existe("/usr/sbin/anacron")
    for linea in _lineas_cron(texto):
        if re.match(r"^\w+\s*=", linea):               # SHELL=…, PATH=…: ni se mira
            continue
        toks = linea.split(None, 1)
        if toks[0] in ATAJOS_CRON:
            campos, resto = ATAJOS_CRON[toks[0]].split(), toks[1] if len(toks) > 1 else ""
            crudo = toks[0]
        elif toks[0] == "@reboot":
            campos, resto, crudo = [], toks[1] if len(toks) > 1 else "", "@reboot"
        else:
            t = linea.split(None, 5)
            if len(t) < 6:
                continue
            campos, resto, crudo = t[:5], t[5], " ".join(t[:5])
        usuario = usuario_def
        if con_usuario:
            u = resto.split(None, 1)
            usuario, resto = u[0], (u[1] if len(u) > 1 else "")
        comando = resto.strip()
        proxima = proxima_cron(campos, ahora) if campos else None
        motivos, estado, nota = [], "al_dia", None
        if not campos and crudo == "@reboot":
            legible = "al arrancar la Pi"
        else:
            legible = legible_cron(campos)
        if campos and proxima is None:
            estado, motivos = "vencido", ["No pude calcular la próxima corrida de esta expresión."]
        dir_cron = re.search(r"cron\.(hourly|daily|weekly|monthly)", comando)
        if dir_cron and "run-parts" in comando:
            nota = ("Lo corre anacron, no cron (esta línea se salta)." if anacron else
                    f"Corre /etc/cron.{dir_cron.group(1)} con run-parts: no hay anacron instalado.")
        if comando.startswith("test -e /run/systemd/system ||") and f.existe("/run/systemd/system"):
            nota = "Con systemd esta línea no corre: la condición `test -e /run/systemd/system ||` la salta."
        real = re.sub(r"^(\w+=\S*\s+)+", "", comando.split("||")[-1].strip())      # sin `VAR=1` ni el `test … ||`
        nombre = Path((real.split() or [crudo])[0].strip("{}; ")).name or crudo
        nombre = enmascarar(nombre)
        if dir_cron and "run-parts" in comando:
            nombre = f"run-parts cron.{dir_cron.group(1)}"
        r.append(tarea_base(
            fuente="cron", nombre=nombre, descripcion=nota, expresion=crudo, legible=legible,
            proxima=iso(proxima), usuario=usuario, comando=enmascarar(comando), unidad=origen,
            persistente=False, habilitado=True, proyecto=deducir_proyecto(comando, origen), estado=estado,
            motivo=" ".join(motivos) or None))
    return r


def tareas_cron(f: Fuentes, ahora: datetime) -> list[dict]:
    r: list[dict] = []
    crontab = f.leer("/etc/crontab")
    r += tareas_de_crontab(crontab, "/etc/crontab", ahora, True, "root", f)
    for nombre in f.listar("/etc/cron.d"):
        if re.fullmatch(r"[A-Za-z0-9_-]+", nombre):
            r += tareas_de_crontab(f.leer(f"/etc/cron.d/{nombre}"), f"/etc/cron.d/{nombre}", ahora, True, "root", f)
    # Cuándo toca cada directorio: la línea de /etc/crontab que lo llama (run-parts) o anacron.
    proximas = {}
    for t in r:
        m = re.search(r"cron\.(hourly|daily|weekly|monthly)", t["comando"] or "")
        if m and t["unidad"] == "/etc/crontab":
            proximas[m.group(1)] = t
    anacron = f.existe("/usr/sbin/anacron")
    for d in DIRS_CRON:
        for nombre in f.listar(f"/etc/cron.{d}"):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", nombre):
                continue
            ruta = f"/etc/cron.{d}/{nombre}"
            via = proximas.get(d)
            ultima = None
            ts = f.leer(f"/var/spool/anacron/cron.{d}")
            if ts and re.fullmatch(r"\d{8}\s*", ts):
                ultima = datetime.strptime(ts.strip(), "%Y%m%d").astimezone()
            r.append(tarea_base(
                fuente="cron", nombre=f"cron.{d}/{nombre}",
                descripcion=("Script de /etc/cron.%s: lo corre %s." % (d, "anacron" if anacron else "run-parts, llamado desde /etc/crontab")),
                expresion=f"cron.{d}", legible=f"{CADA_DIR[d]} (hora de /etc/crontab: {via['legible']})" if via else CADA_DIR[d],
                proxima=via["proxima"] if via else None, ultima=iso(ultima), usuario="root", comando=ruta,
                unidad=ruta, persistente=anacron, habilitado=True, proyecto=deducir_proyecto(nombre),
                estado="al_dia" if via else "vencido",
                motivo=None if via else f"No hay línea en /etc/crontab que llame a cron.{d}."))
    usuario = f.usuario()
    r += tareas_de_crontab(f.crontab_usuario(), f"crontab de {usuario}", ahora, False, usuario, f)
    return r


# --- temporizadores del bot ------------------------------------------------

_DIAS_BOT = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]


def _recurrencia_es(rec: dict) -> str:
    """La `recurrencia` de una orden del bot (encargo 35), legible.

    {"dias": [0, 1, 2, 3, 4], "hora": "06:30"} → 'lunes a viernes 06:30' (lunes = 0);
    {"cada_seg": 7200, "desde": "08:00", "hasta": "22:00"} → 'cada 2 h de 08:00 a 22:00'.
    """
    try:
        if rec.get("cada_seg"):
            return (f"cada {dur_es(_seg_a_texto(int(rec['cada_seg'])))} "
                    f"de {rec.get('desde', '08:00')} a {rec.get('hasta', '22:00')}")
        dias = sorted({int(d) for d in rec["dias"] if 0 <= int(d) <= 6})
        if len(dias) == 7:
            cuales = "todos los días"
        elif len(dias) >= 3 and dias == list(range(dias[0], dias[-1] + 1)):
            cuales = f"{_DIAS_BOT[dias[0]]} a {_DIAS_BOT[dias[-1]]}"
        else:
            cuales = ", ".join(_DIAS_BOT[d] for d in dias)
        return f"{cuales} {rec['hora']}" if dias else "recurrente"
    except (KeyError, TypeError, ValueError, AttributeError):
        return "recurrente"                             # forma desconocida: se dice, no se inventa


def tareas_bot(f: Fuentes, ahora: datetime) -> list[dict]:
    texto = f.leer(str(TEMPORIZADORES))
    if texto is None:
        raise RuntimeError(f"no pude leer {TEMPORIZADORES}")
    datos = json.loads(texto or "{}")
    r = []
    for i in datos.get("items", []):
        if i.get("estado") not in ("activo", "sonando", "pausado"):
            continue                                    # cancelado, terminado, perdido: ya no están programados
        vence = datetime.fromtimestamp(int(i["vence"]), timezone.utc).astimezone()
        creado = datetime.fromtimestamp(int(i["creado"]), timezone.utc).astimezone() if i.get("creado") else None
        alarma = i.get("tipo") == "alarma"
        # Encargo 35: `recordatorio` es una alarma con texto, y cualquiera de las dos puede traer
        # `recurrencia`. `vence` es siempre la próxima ocurrencia, así que lo demás no cambia.
        clase = i.get("tipo") if i.get("tipo") in ("alarma", "recordatorio") else "temporizador"
        # Encargo 75: el aviso del clima es una orden que nunca suena; el bot manda la foto por Telegram.
        clima = i.get("tipo") == "clima"
        if clima:
            clase = "aviso del clima"
        rec = i.get("recurrencia") if isinstance(i.get("recurrencia"), dict) else None
        en_pausa = i.get("estado") == "pausado"
        legible = (_recurrencia_es(rec) + (" (en pausa)" if en_pausa else "") if rec else
                   f"{clase} en pausa; no sonará" if clase != "temporizador" and en_pausa else
                   f"{clase} a las {vence:%H:%M}" if clase != "temporizador" else
                   f"temporizador en pausa; quedan {dur_es(_seg_a_texto(int(i.get('restante') or 0)))}"
                   if en_pausa else
                   f"temporizador de {dur_es(_seg_a_texto(int(i.get('duracion') or 0)))}")
        atrasado = i["estado"] == "activo" and (ahora - vence).total_seconds() > GRACIA_BOT
        termino = (f" Vence el {datetime.fromtimestamp(int(i['hasta_epoch']), timezone.utc).astimezone():%d-%m-%Y}."
                   if i.get("hasta_epoch") else "")
        r.append(tarea_base(
            fuente="bot", nombre=i.get("nombre") or clase,
            descripcion=f"{clase.capitalize()}{' recurrente' if rec else ''} del perfil {i.get('perfil')}, "
                        f"puesto por {i.get('origen', 'voz')}.{termino}"
                        + (" Está sonando." if i["estado"] == "sonando" else ""),
            expresion=(f"{json.dumps(rec, ensure_ascii=False)} · " if rec else "")
                      + f"vence {vence.isoformat(timespec='seconds')}", legible=legible,
            proxima=None if i.get("estado") == "pausado" else iso(vence),
            ultima=iso(creado), usuario=i.get("perfil"),
            comando="botv3 lo manda por Telegram; no suena" if clima else "parlante.service lo hace sonar",
            unidad=str(TEMPORIZADORES), persistente=True, habilitado=True, proyecto="bot",
            estado="pausado" if i.get("estado") == "pausado" else "vencido" if atrasado else "al_dia",
            motivo=("Está en pausa; no sonará hasta que se reanude." if i.get("estado") == "pausado" else
                    "Venció hace más de %d s y sigue «activo»: %s no lo recogió."
                    % (GRACIA_BOT, "el bot" if clima else "parlante.service")
                    if atrasado else None)))
        r[-1]["identificador"] = i.get("id")
        # Lo mismo que acepta temporizador-accion.py: las alarmas de una sola vez no se pausan ni se reanudan (aunque figuren pausadas, solo se corren); las que suenan no se tocan.
        # Un recordatorio de una sola vez tampoco: pausarlo le correría la hora como a un temporizador.
        # Lo recurrente sí, alarma o recordatorio: al reanudar vuelve a su próxima ocurrencia.
        r[-1]["acciones"] = ([] if i["estado"] == "sonando" else
                             ["correr"] if not rec and (alarma or clase == "recordatorio") else
                             ["reanudar", "correr"] if i["estado"] == "pausado" else ["pausar", "correr"])
        if i.get("estado") == "pausado":
            r[-1]["proxima"] = None
            r[-1]["legible"] = legible
    return r


def _seg_a_texto(s: int) -> str:
    h, resto = divmod(s, 3600)
    m, seg = divmod(resto, 60)
    return " ".join(x for x in (f"{h}h" if h else "", f"{m}min" if m else "", f"{seg}s" if seg else "") if x) or "0s"


# ---------------------------------------------------------------------------
# Todo junto
# ---------------------------------------------------------------------------

def recolectar(f: Fuentes) -> dict:
    ahora = f.ahora()
    tareas: list[dict] = []
    no_visibles: list[dict] = []
    for nombre, fn in (("timers del sistema", lambda: timers_de(f, "sistema", ahora)),
                       ("timers de usuario", lambda: timers_de(f, "usuario", ahora)),
                       ("cron", lambda: tareas_cron(f, ahora)),
                       ("temporizadores del bot", lambda: tareas_bot(f, ahora))):
        try:
            tareas += fn()
        except Exception as e:                           # una fuente rota no tumba las demás
            no_visibles.append({"fuente": nombre, "motivo": f"No se pudo leer: {type(e).__name__}: {e}"})
    if not f.legible("/var/spool/cron/crontabs/root"):
        no_visibles.append({"fuente": "crontab de root", "motivo": "Pide root: el archivo no se lee sin sudo."})
    no_visibles += [
        {"fuente": "flujos de n8n con horario", "motivo": "Piden una llave de API de n8n (fase 2)."},
        {"fuente": "otros equipos", "motivo": "Tareas de Windows en los PC del usuario y tareas de Claude Desktop: "
                                              "cada equipo tendría que escribir su JSON en el vault (fase 2)."},
        {"fuente": "rutinas en la nube", "motivo": "Como el informe semanal GOP-3: viven en los servidores de Anthropic "
                                                   "y no se ven desde la Pi (fase 2)."},
    ]
    for t in tareas:
        if not t["banderas"] and t["estado"] in ("fallo", "vencido", "huerfano"):
            t["banderas"] = [t["estado"]]
    tareas.sort(key=lambda t: (t["proxima"] is None, t["proxima"] or "", t["nombre"] or ""))
    return {"momento": iso(ahora), "tareas": tareas, "no_visibles": no_visibles}


def main(argv: list[str]) -> int:
    salida = recolectar(Fuentes())
    print(json.dumps(salida, ensure_ascii=False, indent=2 if "--indent" in argv else None))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
