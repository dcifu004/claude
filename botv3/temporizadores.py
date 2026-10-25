"""Temporizadores y alarmas de la casa, por perfil, al estilo de un Google Home.

Diseño: `25 - Asistente de voz (funcionamiento y frases).md`. Sigue el molde de
`compras.py` —regex local, JSON con `flock` en `casa/`, `chmod` explícito— y le
suma la única pieza que la lista no tenía: el tiempo.

    /opt/nodo/datos/casa/temporizadores.json   0660 <dueño>:casa

Reparto de trabajo, que es lo que hace que un temporizador sobreviva:

- **El bot** (`botv3@jaime`, `botv3@pilar`) interpreta la frase, crea, consulta y
  cancela. Nunca hace sonar nada.
- **`parlante.service`** (Fase 3, el único dueño del parlante) revisa
  `vencidos()` cada segundo y es quien suena. Así un temporizador no muere cuando
  el bot se reinicia en un despliegue: el estado está en disco y quien lo hace
  sonar es otro proceso. Un `sleep` en un hilo del bot se perdería en cada
  `restart`, que es justo lo que el backlog advirtió.

Tres reglas que no se deducen del código:

1. **Es por perfil, aunque viva en el directorio común.** El temporizador de los
   tallarines de Diego no es de Camila: cada ítem lleva `perfil` y toda consulta
   filtra por él. Es la primera cosa de `casa/` que es estado privado en un lugar
   compartido.
2. **Cancelar no pide confirmación**, al revés que borrar de la lista de compras:
   quien cancela está ahí y lo descubre en el momento. No copiar la regla de
   compras por inercia.
3. **Un temporizador que venció con el nodo apagado no suena tarde.** Si pasaron
   más de `GRACIA` segundos, sólo se avisa por Telegram: que suene "los tallarines"
   una hora después de apagar la olla es ruido, no servicio.

Las horas son locales (la Pi está en America/Santiago). Todo lo que compara usa
`epoch`; el texto es sólo para leer.

Órdenes permanentes (encargo 35, D43, 07-10-2026). Una alarma o un recordatorio
puede llevar `recurrencia`; ausente = una sola vez, como siempre:

    {"dias": [0, 1, 2, 3, 4], "hora": "06:30"}                  lunes = 0
    {"cada_seg": 7200, "desde": "08:00", "hasta": "22:00"}      intervalo, mín. 1 h

`vence` sigue siendo la PRÓXIMA ocurrencia: quien no sabe de recurrencia
(`vencidos`, Cockpit, `resumen`) sigue funcionando. Cuatro reglas más:

4. **Una recurrente no se cierra al sonar ni al perderse: se reprograma** a la
   próxima ocurrencia futura. Con el nodo apagado tres días sale UN aviso de
   perdida, nunca tres alarmas juntas.
5. **La hora se guarda como `HH:MM` local y la próxima se calcula con el
   calendario de `America/Santiago`**, no sumando 86 400 s: «todos los días a
   las 7» suena a las 7 también la semana del cambio de hora.
6. **Por voz una orden recurrente no se guarda acá**: `atender` devuelve la
   propuesta y el bot la guarda sólo con el ✅ de Telegram (el wake word no
   autentica; mismo molde que la memoria de hogar). Escrita en Telegram se
   guarda y se ofrece deshacer.
7. **Borrar una orden es marcarla `borrado`**, recuperable una hora; pausar deja
   `pausado`. Ninguna de las dos pide confirmación. Este módulo sólo escribe
   datos (nivel 1 de D10): nunca crea unidades ni ejecuta nada por una orden.

Aviso programado del clima (encargo 75, 21-10-2026). Una orden más, de tipo
`clima`, sin nombre ni texto, sólo por días:

    {"tipo": "clima", "lugar": null, "recurrencia":
     {"dias": [0, 1, 2, 3, 4], "hora": "07:30", "feriados": "fin_de_semana"}}

8. **Un aviso de clima nunca pasa a `sonando`**: no es del parlante. `vencidos`
   no lo ve; lo recoge `climas_vencidos`, que lo reprograma ANTES de devolverlo
   (si el envío falla no se reintenta en bucle) y separa lo que se perdió por más
   de `GRACIA_CLIMA`: eso no se manda tarde.
9. **Con `"feriados": "fin_de_semana"` un feriado cuenta como domingo** en
   `proxima`: la de lunes a viernes no sale y la de sábado y domingo sí. Los
   feriados se LEEN de `feriados-<año>.json` del modo descanso; si falta o no se
   entiende, el día cuenta como normal y queda una línea en el log por día.
   `"lugar": null` es el del perfil al momento de enviar (lo cambia la 76).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time as hora_t, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # Windows: sólo para correr las pruebas en el notebook.
    fcntl = None  # type: ignore[assignment]

POSIX = fcntl is not None

try:
    from zoneinfo import ZoneInfo
    ZONA: Any = ZoneInfo("America/Santiago")
except Exception:  # Windows sin tzdata: sólo para correr las pruebas en el notebook.
    ZONA = None

CASA_DIR = Path(os.environ.get("BOTV3_CASA_DIR", "/opt/nodo/datos/casa"))
ARCHIVO = CASA_DIR / "temporizadores.json"
LOCK = CASA_DIR / ".temporizadores.lock"
MODO_ARCHIVO = 0o660

MAX_ACTIVOS = 10          # por perfil; más que eso es un error de dictado
MAX_SEGUNDOS = 24 * 3600  # un temporizador de dos días es una alarma mal dicha
MIN_SEGUNDOS = 5
# Cuánto puede llegar tarde un vencimiento y todavía sonar. Cubre un reinicio
# del nodo o un despliegue de `parlante`; más allá, sólo aviso por Telegram.
GRACIA = 300
# Los terminados y cancelados se guardan un día para poder decir "venció hace
# 3 minutos", y después se purgan solos.
RETENCION = 24 * 3600

# --- Órdenes recurrentes (encargo 35) ---
MAX_RECURRENTES = 10          # por perfil, aparte de MAX_ACTIVOS
MAX_DIAS_RECURRENTE = 7       # la próxima ocurrencia no puede quedar más lejos
MIN_INTERVALO = 3600          # «cada 20 minutos» es un temporizador mal dicho
VENTANA = ("08:00", "22:00")  # un intervalo no suena de madrugada
DESHACER_SEG = 3600           # cuánto vive el botón «↩️ Deshacer»
RENOVAR_DIAS = 30
AVISO_RENOVAR = 7 * 86400     # se ofrece renovar si vence en menos de esto
# Una orden vencida se guarda una semana para poder renovarla con el botón.
RETENCION_VENCIDA = 7 * 86400
VIVOS = ("activo", "sonando", "pausado")

# --- Aviso del clima (encargo 75) ---
# Más tarde que esto no se manda: el clima de las 7:30 a las 9 ya no sirve para salir.
GRACIA_CLIMA = 3600
# Un feriado puede correr la próxima de «los lunes» a dos semanas.
MAX_DIAS_CLIMA = 14
# Los feriados del modo descanso (`pi/descanso.py`): root 0644, el bot sólo los lee.
FERIADOS_DIR = Path(os.environ.get("BOTV3_FERIADOS_DIR", "/var/lib/nodo-descanso"))
MAX_FERIADOS_BYTES = 256 * 1024
LOG = logging.getLogger("botv3.temporizadores")

# ---------------------------------------------------------------------------
# Normalización y números dichos
# ---------------------------------------------------------------------------

UNIDADES = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiun": 21, "veintiuno": 21, "veintiuna": 21,
    "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
           "setenta": 70, "ochenta": 80, "noventa": 90}
_PALABRA_NUM = "|".join(sorted(list(UNIDADES) + list(DECENAS) + ["cien"],
                               key=len, reverse=True))
# Un número dicho: dígitos, "cuarenta y cinco", "veinte", "cien".
NUM = rf"(?:\d+(?:[.,]\d+)?|(?:{_PALABRA_NUM})(?:\s+y\s+(?:{_PALABRA_NUM}))?)"


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin signos salvo ':' de las horas."""
    plano = unicodedata.normalize("NFKD", texto.strip().lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    # "1,5 horas" es un decimal: la coma se cambia a punto ANTES de borrar signos.
    plano = re.sub(r"(\d),(\d)", r"\1.\2", plano)
    plano = re.sub(r"[¡!¿?,;\"«»()]", " ", plano)
    # "7.30" de Whisper es una hora, no un decimal; se unifica a "7:30".
    plano = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", plano)
    plano = re.sub(r"\.(?=\s|$)", " ", plano)
    return " ".join(plano.split())


def numero(texto: str) -> float | None:
    """'cuarenta y cinco' → 45, '1,5' → 1.5, 'un' → 1. None si no es número."""
    texto = texto.strip()
    if re.fullmatch(r"\d+(?:[.,]\d+)?", texto):
        return float(texto.replace(",", "."))
    if texto == "cien":
        return 100.0
    partes = [p for p in re.split(r"\s+y\s+", texto) if p]
    total = 0
    for parte in partes:
        if parte in UNIDADES:
            total += UNIDADES[parte]
        elif parte in DECENAS:
            total += DECENAS[parte]
        else:
            return None
    return float(total) if partes else None


# Vocativo: el wake word suele quedar al principio de la transcripción. Se quita
# para cualquiera de los dos nombres: la identidad ya la decidió `escucha`.
VOCATIVO_RE = re.compile(
    r"^(?:(?:hola|hey|oye|ok|ya)\s+)?(?:jaime|pilar|jarvis|alexa)\b\s*:?\s*")

# ---------------------------------------------------------------------------
# Duraciones
# ---------------------------------------------------------------------------

_UNIDAD_SEG = {"segundo": 1, "segundos": 1, "seg": 1, "s": 1,
               "minuto": 60, "minutos": 60, "min": 60, "mins": 60,
               "hora": 3600, "horas": 3600, "h": 3600, "hr": 3600, "hrs": 3600}
_UNIDAD = r"(?:segundos?|seg|minutos?|mins?|horas?|hrs?|h|s)"
_TRAMO = re.compile(rf"(?P<n>{NUM}|medio|media)\s+(?P<u>{_UNIDAD})\b"
                    rf"(?:\s+y\s+(?P<frac>medio|media|cuarto))?")
_ESPECIALES = [
    (re.compile(r"\bmedia\s+hora\b"), 1800),
    (re.compile(r"\btres\s+cuartos\s+de\s+hora\b"), 2700),
    (re.compile(r"\bun\s+cuarto\s+de\s+hora\b"), 900),
    (re.compile(r"\bmedio\s+minuto\b"), 30),
]


def duracion(texto: str) -> tuple[int, str] | None:
    """Segundos de una duración dicha, y el texto que la ocupó.

    Acepta lo que sale de Whisper en Chile: '10 minutos', 'diez minutos',
    'una hora y media', 'media hora', '1 hora 20 minutos', 'un minuto y medio',
    'hora y cuarto'. Devuelve None si no hay ninguna.
    """
    t = f" {texto} "
    usados: list[str] = []
    total = 0
    for patron, seg in _ESPECIALES:
        for m in patron.finditer(t):
            total += seg
            usados.append(m.group(0))
        t = patron.sub(" ", t)
    # "hora y media" sin artículo: Whisper a veces deja caer el "una".
    m = re.search(r"(?<!\w)hora\s+y\s+(media|cuarto)\b", t)
    if m and not re.search(rf"{NUM}\s+hora\s+y", t):
        total += 3600 + (1800 if m.group(1) == "media" else 900)
        usados.append(m.group(0))
        t = t.replace(m.group(0), " ")
    for m in _TRAMO.finditer(t):
        n_txt, u = m.group("n"), m.group("u")
        n = 0.5 if n_txt in ("medio", "media") else numero(n_txt)
        if n is None:
            continue
        seg = n * _UNIDAD_SEG[u]
        frac = m.group("frac")
        if frac:
            seg += _UNIDAD_SEG[u] * (0.5 if frac in ("medio", "media") else 0.25)
        total += seg
        usados.append(m.group(0))
    if not usados:
        return None
    return int(round(total)), " ".join(usados)


# ---------------------------------------------------------------------------
# Horas de reloj (alarmas)
# ---------------------------------------------------------------------------

_HORA = re.compile(
    rf"\b(?:a|para)\s+las?\s+(?P<h>\d{{1,2}}|{_PALABRA_NUM})"
    rf"(?::(?P<mm>\d{{2}})|\s+y\s+(?P<ymin>media|cuarto|{NUM})|\s+menos\s+(?P<menos>cuarto|{NUM}))?"
    rf"(?:\s+(?:horas?|hrs))?"
    rf"(?:\s+(?P<periodo>de\s+la\s+manana|de\s+la\s+tarde|de\s+la\s+noche|"
    rf"de\s+la\s+madrugada|am|a\s+m|pm|p\s+m)(?!\w))?")
_MEDIODIA = re.compile(r"\b(?:al?\s+)?(?:mediodia|medio\s+dia)\b")
_MEDIANOCHE = re.compile(r"\b(?:a\s+la\s+)?medianoche\b")


def _hora_min(texto: str) -> tuple[int, int, str] | None:
    """(hora, minuto, periodo) de una hora dicha. `periodo` vacío = no se dijo
    mañana ni tarde; 'fijo' = no hay dos lecturas (19:30, mediodía)."""
    if _MEDIODIA.search(texto):
        h, mi, periodo = 12, 0, "fijo"
    elif _MEDIANOCHE.search(texto):
        h, mi, periodo = 0, 0, "fijo"
    else:
        m = _HORA.search(texto)
        if not m:
            return None
        hn = numero(m.group("h"))
        if hn is None:
            return None
        h, mi = int(hn), 0
        if m.group("mm"):
            mi = int(m.group("mm"))
        elif m.group("ymin"):
            y = m.group("ymin")
            mi = 30 if y == "media" else 15 if y == "cuarto" else int(numero(y) or 0)
        elif m.group("menos"):
            me = m.group("menos")
            h, mi = h - 1, 60 - (15 if me == "cuarto" else int(numero(me) or 0))
        p = (m.group("periodo") or "").replace(" ", "")
        if p in ("delamanana", "delamadrugada", "am"):
            periodo = "am"
        elif p in ("delatarde", "delanoche", "pm"):
            periodo = "pm"
        else:
            periodo = ""
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return None
        if periodo == "pm" and h < 12:
            h += 12
        elif periodo == "am" and h == 12:
            h = 0
        if h > 12:
            periodo = "fijo"
    return h, mi, periodo


def hora_dicha(texto: str, ahora: datetime) -> tuple[datetime, bool] | None:
    """Próximo instante que corresponde a una hora dicha, y si era ambigua.

    'a las 7' sin 'de la mañana/tarde' se resuelve a la PRÓXIMA de las dos
    (7:00 o 19:00), como hace un Google Home; la respuesta hablada siempre dice
    cuál eligió, para que el error se corrija en el momento y no al otro día.
    'mañana' fuerza el día siguiente y, si es ambigua, la mañana.
    """
    # "mañana" como día, no como "de la mañana".
    manana_dia = bool(re.search(r"\bmanana\b", re.sub(r"de\s+la\s+manana", " ", texto)))
    hm = _hora_min(texto)
    if hm is None:
        return None
    h, mi, periodo = hm
    base = ahora.replace(second=0, microsecond=0)
    candidatos = [base.replace(hour=h, minute=mi)]
    ambigua = periodo == "" and 1 <= h <= 12
    if ambigua:
        candidatos.append(base.replace(hour=(h + 12) % 24, minute=mi))
    if manana_dia:
        # "mañana a las 7" sin más: la de la mañana. Es lo que se quiere al dictar
        # una alarma para el día siguiente casi siempre, y se dice en voz alta.
        return (base + timedelta(days=1)).replace(hour=h, minute=mi), ambigua
    futuros = []
    for c in candidatos:
        if c <= ahora:
            c += timedelta(days=1)
        futuros.append(c)
    return min(futuros), ambigua


# ---------------------------------------------------------------------------
# Recurrencia (encargo 35): «de lunes a viernes», «los sábados», «cada 2 horas»
# ---------------------------------------------------------------------------

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_DIAS_PLURAL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]
_DIA_NUM = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4,
            "sabado": 5, "sabados": 5, "domingo": 6, "domingos": 6}
_DIA = r"(?:lunes|martes|miercoles|jueves|viernes|sabados?|domingos?)"
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]

# El orden importa: «días de semana» antes que «todos los días».
_REC_HABILES = re.compile(r"\b(?:(?:todos\s+)?los\s+)?dias\s+(?:de\s+semana|habiles|de\s+trabajo)\b")
_REC_FINDE = re.compile(r"\b(?:(?:todos\s+)?los\s+)?fines\s+de\s+semana\b")
_REC_RANGO = re.compile(rf"\b(?:de\s+)?(?P<d1>{_DIA})\s+a\s+(?P<d2>{_DIA})\b")
_REC_DIARIO = re.compile(r"\b(?:todos\s+los\s+dias(?:\s+de\s+la\s+semana)?|cada\s+dia|a\s+diario|"
                         r"diariamente|todas\s+las\s+(?P<parte>mananas|tardes|noches))\b")
# «el lunes» es una sola vez; lo recurrente lo marca «los», «cada» o «todos los».
_REC_LISTA = re.compile(rf"\b(?:todos\s+los|cada|los)\s+(?P<lista>{_DIA}"
                        rf"(?:\s+(?:[ye]\s+)?(?:los\s+)?{_DIA})*)\b")
_REC_CADA = re.compile(rf"\bcada\s+(?P<d>(?:{NUM}|media)\s+{_UNIDAD}\b(?:\s+y\s+(?:media|medio|cuarto)\b)?"
                       rf"|hora(?:\s+y\s+(?:media|cuarto))?\b)")
# Con «las» obligatorio en los dos lados: «de una a dos pastillas» no es una ventana.
_REC_VENTANA = re.compile(r"\b(?:de|desde|entre)\s+las?\s+(?P<a>\d{1,2})(?::(?P<am>\d{2}))?"
                          r"\s+(?:a|hasta|y)\s+las?\s+(?P<b>\d{1,2})(?::(?P<bm>\d{2}))?(?:\s+horas)?\b")
# Repeticiones que se nombran pero todavía no se entienden: se contesta que no,
# en vez de crear una alarma de una sola vez en silencio.
_REC_NO_SOPORTADA = re.compile(
    rf"\bcada\s+(?:{NUM}\s+)?(?:dias|semanas?|mes(?:es)?|quincena|ano)\b|\bcada\s+\d{{1,2}}\s+de\b|"
    r"\btod[oa]s\s+l[oa]s\s+(?:semanas|meses|anos|quincenas)\b|"
    r"\b(?:semanal|quincenal|mensual|anual)(?:mente)?\b|\bdia\s+por\s+medio\b")

_POR = re.compile(rf"\b(?:por|durante)\s+(?P<n>{NUM})\s+(?P<u>dias?|semanas?|mes(?:es)?)\b")
_HASTA_FIN = re.compile(r"\bhasta\s+(?:el\s+)?fin(?:al|es)?\s+de(?:l)?\s+(?P<q>mes|ano)\b")
_HASTA_FECHA = re.compile(rf"\bhasta\s+el\s+(?P<dd>\d{{1,2}})\s+de\s+(?P<mes>{'|'.join(_MESES)})\b")


def _local(dt: datetime) -> datetime:
    """El mismo instante con el calendario de Santiago (con sus cambios de hora)."""
    return dt.astimezone(ZONA) if ZONA is not None else dt.astimezone()


def _hhmm(valor: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(valor))
    if not m or not (0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59):
        raise ValueError("No entendí la hora.")
    return int(m.group(1)), int(m.group(2))


# --- Feriados (encargo 75): la copia de Boostr que deja `pi/descanso.py` -------

_FERIADOS: dict[int, tuple[Any, set[str] | None, str]] = {}   # año → (firma, fechas, motivo)
_FERIADOS_AVISADOS: set[str] = set()


def _leer_feriados(anio: int) -> tuple[set[str] | None, str]:
    """Las fechas de `feriados-<año>.json`, con la forma de `descanso._fechas`
    (lista de {"date": "AAAA-MM-DD", …}). Lo que no calza —una fecha inválida,
    otro año, algo que no es objeto— se ignora una por una; sin ninguna fecha
    buena, o con el archivo ausente, truncado o enorme, (None, motivo)."""
    ruta = FERIADOS_DIR / f"feriados-{anio}.json"
    try:
        st = ruta.stat()
    except OSError as e:
        _FERIADOS.pop(anio, None)
        return None, f"no pude leer {ruta} ({type(e).__name__})"
    firma = (st.st_mtime_ns, st.st_size, st.st_ino)
    guardado = _FERIADOS.get(anio)
    if guardado and guardado[0] == firma:
        return guardado[1], guardado[2]
    fechas: set[str] | None = None
    motivo = ""
    if st.st_size > MAX_FERIADOS_BYTES:
        motivo = f"{ruta} pesa {st.st_size} bytes (tope {MAX_FERIADOS_BYTES})"
    else:
        try:
            datos = json.loads(ruta.read_bytes().decode("utf-8"))
            buenas = set()
            for item in datos if isinstance(datos, list) else []:
                valor = item.get("date") if isinstance(item, dict) else None
                if not isinstance(valor, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
                    continue
                try:
                    fecha = datetime.strptime(valor, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if fecha.year == anio:
                    buenas.add(fecha.isoformat())
            fechas = buenas or None
            if fechas is None:
                motivo = f"{ruta} no trae ninguna fecha de {anio}"
        except (OSError, ValueError, RecursionError) as e:
            motivo = f"{ruta} no se entiende ({type(e).__name__})"
    _FERIADOS[anio] = (firma, fechas, motivo)
    return fechas, motivo


def es_feriado(fecha: Any) -> bool:
    """Si `fecha` (un `date`) es feriado según el modo descanso. Sin dato, False,
    con una sola línea de log por fecha: el hilo pregunta cada 2 s."""
    try:
        fechas, motivo = _leer_feriados(fecha.year)
    except Exception as e:  # nada de acá puede tumbar el hilo de avisos
        fechas, motivo = None, f"error leyendo feriados ({type(e).__name__})"
    if fechas is None:
        clave = fecha.isoformat()
        if clave not in _FERIADOS_AVISADOS:
            if len(_FERIADOS_AVISADOS) > 1000:
                _FERIADOS_AVISADOS.clear()
            _FERIADOS_AVISADOS.add(clave)
            LOG.warning("feriados: %s; el %s cuenta como día normal", motivo, clave)
        return False
    return fecha.isoformat() in fechas


def _dia_efectivo(fecha: Any, rec: dict[str, Any]) -> int:
    """El día de la semana con que cuenta una fecha: un feriado, como domingo,
    si la orden lo pide."""
    if rec.get("feriados") == "fin_de_semana" and es_feriado(fecha):
        return 6
    return fecha.weekday()


def recurrencia_dicha(texto: str) -> tuple[dict[str, Any] | None, str, str]:
    """(recurrencia sin hora, la frase sin ese tramo, parte del día dicha).

    La recurrencia por días sale sin `hora`: la pone quien llama, porque la hora
    se lee del resto de la frase. Un intervalo de menos de 1 h se devuelve igual
    (con su `cada_seg`) para poder contestar por qué no.
    """
    m = _REC_CADA.search(texto)
    if m:
        d = duracion(m.group("d"))
        seg = d[0] if d else 3600  # «cada hora», sin número
        resto = texto[:m.start()] + " " + texto[m.end():]
        desde, hasta = VENTANA
        v = _REC_VENTANA.search(resto)
        if v:
            a, b = int(v.group("a")), int(v.group("b"))
            if b <= a and b <= 12:
                b += 12  # «de las 9 a las 9» es de 9 a 21
            if a <= 23 and b <= 23:
                desde = f"{a:02d}:{v.group('am') or '00'}"
                hasta = f"{b:02d}:{v.group('bm') or '00'}"
                resto = resto[:v.start()] + " " + resto[v.end():]
        return {"cada_seg": seg, "desde": desde, "hasta": hasta}, resto, ""
    dias: list[int] | None = None
    parte = ""
    for patron, fijos in ((_REC_HABILES, [0, 1, 2, 3, 4]), (_REC_FINDE, [5, 6])):
        m = patron.search(texto)
        if m:
            dias = fijos
            break
    if dias is None:
        m = _REC_RANGO.search(texto)
        if m:
            a, b = _DIA_NUM[m.group("d1")], _DIA_NUM[m.group("d2")]
            dias = sorted(range(a, b + 1) if a <= b else list(range(a, 7)) + list(range(0, b + 1)))
    if dias is None:
        m = _REC_DIARIO.search(texto)
        if m:
            dias, parte = list(range(7)), m.group("parte") or ""
    if dias is None:
        m = _REC_LISTA.search(texto)
        if m:
            dias = sorted({_DIA_NUM[d] for d in re.findall(_DIA, m.group("lista"))})
    if dias is None or m is None:
        return None, texto, ""
    return {"dias": dias}, texto[:m.start()] + " " + texto[m.end():], parte


def _hora_recurrente(h: int, mi: int, periodo: str, tipo: str, parte: str) -> str:
    """La hora fija de una orden. Acá no hay «la próxima de las dos»: una hora
    sin «de la mañana/tarde» es de la mañana, salvo un recordatorio entre la 1 y
    las 5, que nadie pide de madrugada sin decirlo. La respuesta dice cuál quedó."""
    if periodo == "" and 1 <= h <= 12:
        if parte in ("tardes", "noches"):
            h = 0 if (h == 12 and parte == "noches") else h if h == 12 else h + 12
        elif parte != "mananas" and tipo == "recordatorio" and h <= 5:
            h += 12
    return f"{h:02d}:{mi:02d}"


def vencimiento_dicho(texto: str, ahora: datetime) -> tuple[int | None, str]:
    """`hasta_epoch` si la frase lo dice («por 2 semanas», «hasta fin de mes»,
    «hasta el 15 de noviembre»), y la frase sin ese tramo."""
    loc = _local(ahora)
    m = _POR.search(texto)
    if m:
        n = numero(m.group("n")) or 0
        dias = n * (1 if m.group("u").startswith("dia") else 7 if m.group("u").startswith("semana") else 30)
        if dias >= 1:
            return _epoch(loc + timedelta(days=int(round(dias)))), texto[:m.start()] + " " + texto[m.end():]
    fin = None
    m = _HASTA_FIN.search(texto)
    if m:
        if m.group("q") == "ano":
            fin = loc.replace(month=12, day=31)
        else:
            fin = (loc.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    else:
        m = _HASTA_FECHA.search(texto)
        if m:
            try:
                fin = loc.replace(month=_MESES.index(m.group("mes")) + 1, day=int(m.group("dd")))
                if fin.date() < loc.date():
                    fin = fin.replace(year=fin.year + 1)
            except ValueError:
                return None, texto
    if fin is None or m is None:
        return None, texto
    fin = datetime.combine(fin.date(), hora_t(23, 59, 59), tzinfo=loc.tzinfo)
    return _epoch(fin), texto[:m.start()] + " " + texto[m.end():]


def _validar_recurrencia(rec: dict[str, Any]) -> dict[str, Any]:
    """La recurrencia en su forma canónica. ValueError con el motivo hablable."""
    if "cada_seg" in rec:
        cada = int(rec["cada_seg"])
        if cada < MIN_INTERVALO:
            raise ValueError("El intervalo mínimo es de 1 hora.")
        if cada > MAX_DIAS_RECURRENTE * 86400:
            raise ValueError(f"El intervalo máximo es de {MAX_DIAS_RECURRENTE} días.")
        desde, hasta = rec.get("desde") or VENTANA[0], rec.get("hasta") or VENTANA[1]
        return {"cada_seg": cada, "desde": "%02d:%02d" % _hhmm(desde), "hasta": "%02d:%02d" % _hhmm(hasta)}
    dias = sorted({int(d) for d in rec.get("dias") or []})
    if not dias or dias[0] < 0 or dias[-1] > 6:
        raise ValueError("No entendí qué días.")
    canon = {"dias": dias, "hora": "%02d:%02d" % _hhmm(rec.get("hora", ""))}
    if rec.get("feriados") == "fin_de_semana":
        canon["feriados"] = "fin_de_semana"
    return canon


def _en_ventana(loc: datetime, rec: dict[str, Any]) -> bool:
    ahora, desde, hasta = (loc.hour, loc.minute), _hhmm(rec["desde"]), _hhmm(rec["hasta"])
    return desde <= ahora <= hasta if desde <= hasta else (ahora >= desde or ahora <= hasta)


def proxima(rec: dict[str, Any], despues: datetime, ancla: int | None = None) -> datetime:
    """Primera ocurrencia estrictamente posterior a `despues`.

    Por días se arma con fecha y hora LOCALES de Santiago, no sumando 86 400 s:
    así «a las 7» sigue siendo a las 7 la semana del cambio de hora. Un
    intervalo cuenta desde `ancla` (la ocurrencia anterior) para no correrse con
    cada atraso; lo que cae fuera de la ventana pasa al próximo `desde`.
    """
    loc = _local(despues)
    if "dias" in rec:
        h, mi = _hhmm(rec["hora"])
        for d in range(MAX_DIAS_CLIMA + 2 if rec.get("feriados") else 9):
            fecha = loc.date() + timedelta(days=d)
            if _dia_efectivo(fecha, rec) in rec["dias"]:
                c = datetime.combine(fecha, hora_t(h, mi), tzinfo=loc.tzinfo)
                if c > despues:
                    return c
        raise ValueError("No entendí qué días.")
    cada, ahora_e = int(rec["cada_seg"]), _epoch(despues)
    if ancla is None:
        ancla = ahora_e - ahora_e % 60
    c_e = ancla + cada
    if c_e <= ahora_e:
        c_e += ((ahora_e - c_e) // cada + 1) * cada
    c = _local(datetime.fromtimestamp(c_e, timezone.utc))
    if not _en_ventana(c, rec):
        h, mi = _hhmm(rec["desde"])
        fecha = c.date()
        c2 = datetime.combine(fecha, hora_t(h, mi), tzinfo=c.tzinfo)
        if c2 <= c:
            c2 = datetime.combine(fecha + timedelta(days=1), hora_t(h, mi), tzinfo=c.tzinfo)
        c = c2
    return c


def _saltar(rec: dict[str, Any], vence: int, ahora: datetime) -> tuple[int, datetime]:
    """Cuántas ocurrencias quedaron atrás desde `vence`, y la próxima futura."""
    n, v = 0, datetime.fromtimestamp(vence, timezone.utc)
    while v <= ahora and n < 1000:
        n += 1
        v = proxima(rec, v, ancla=_epoch(v))
    if v <= ahora:
        v = proxima(rec, ahora, ancla=_epoch(v))
    return n, v


# ---------------------------------------------------------------------------
# Intención
# ---------------------------------------------------------------------------

@dataclass
class Intencion:
    # crear | consultar | cancelar | agregar | parar | pausar | reanudar | ordenes
    accion: str
    tipo: str = "temporizador"  # temporizador | alarma | recordatorio
    segundos: int = 0
    vence: datetime | None = None
    nombre: str = ""
    todos: bool = False
    ambigua: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


_TEMP = r"(?:temporizador(?:es)?|timer(?:s)?|cronometro|cuenta\s+regresiva)"
_ALARMA = r"(?:alarmas?|despertador)"
_CREAR = r"(?:pon(?:e|me|le|er|eme)?|programa(?:r|me)?|crea(?:r|me)?|activa(?:r|me)?|inicia(?:r)?|haz(?:me)?|configura(?:r)?)"
_CANCELAR = r"(?:cancela(?:r|lo|la|los|las)?|borra(?:r|lo|la)?|elimina(?:r|lo|la)?|quita(?:r|lo|la)?|saca(?:r|lo|la)?|apaga(?:r)?\s+(?:el|la|los|las)\s+(?:temporizador|alarma))"
_RECORDAR = r"(?:recuerdame|recuerdanos|recordarme|acuerdame|hazme\s+(?:acordar|recordar))"
_RECORDATORIO = r"recordatorios?"
_ORDEN = r"ordenes?(?:\s+(?:permanentes?|recurrentes?))?"
_PAUSAR = r"(?:pausa(?:r|me)?|pon(?:er|me)?\s+en\s+pausa|suspende(?:r)?|desactiva(?:r)?)"
_REANUDAR = r"(?:reanuda(?:r)?|reactiva(?:r)?|retoma(?:r)?|vuelve\s+a\s+activar|activa(?:r)?\s+de\s+nuevo)"
# «qué órdenes tengo». Anclado entero a propósito: «qué órdenes de compra hay en
# el proyecto» es una pregunta al vault y tiene que seguir al clasificador.
_LISTAR_ORDENES = re.compile(
    r"(?:que|cuales|cuantas)\s+(?:son\s+)?(?:mis\s+)?ordenes(?:\s+(?:permanentes|recurrentes))?"
    r"(?:\s+(?:tengo|tienes))?(?:\s+(?:activas|puestas|programadas))?|"
    r"(?:que|cuales|cuantas)\s+ordenes\s+(?:permanentes|recurrentes)\s+hay|"
    r"(?:mis|lista\s+(?:de\s+)?(?:mis\s+)?)\s*ordenes(?:\s+(?:permanentes|recurrentes))?")
# Un recordatorio de una sola vez con día o fecha («el lunes», «el 15») no cabe
# en 24 h: se deja pasar al clasificador (agenda) en vez de ponerlo mal.
_OTRO_DIA = re.compile(rf"\b{_DIA}\b|\bpasado\s+manana\b|\bel\s+\d{{1,2}}\s+de\b|\bel\s+dia\s+\d|"
                       r"\b(?:la\s+)?proxim[oa]\b|\bla\s+semana\s+que\s+viene\b|"
                       rf"\ben\s+{NUM}\s+(?:dias?|semanas?|mes(?:es)?)\b")
_PARAR = re.compile(
    r"^(?:para(?:lo|la)?|parar|detente|detenlo|ya|ya\s+para|listo|silencio|"
    r"basta|stop|callate|apaga(?:lo|la)?|ok|ya\s+esta|suficiente|gracias)$")
# "para la alarma" / "apaga el temporizador": con algo sonando es parar; sin
# nada sonando sigue de largo y "apaga la alarma" se lee como cancelar.
_PARAR_OBJETO = re.compile(
    r"^(?:para|parar|apaga|apagar|silencia|deten)\s+(?:el|la|los|las)\s+"
    r"(?:temporizador(?:es)?|timer|alarmas?)$")


# --- Aviso del clima (encargo 75) ---
# Anclado entero, como «qué órdenes tengo»: sólo se toma si no sobra nada fuera del
# verbo, «el clima» o «el pronóstico», la repetición y la hora. «dime el clima» sin
# repetición es la consulta de la 69 y sigue de largo; «el clima laboral», también.
_CLIMA_VERBO = (r"(?:mandame|mandanos|manda|enviame|envia|dime|dinos|avisame|avisanos|dame|cuentame|"
                r"me\s+(?:mandas|envias|dices|avisas|das))")
_CLIMA_OBJ = r"(?:el\s+)?(?:clima|pronostico)(?:\s+del\s+(?:clima|tiempo))?"
_CLIMA_PEDIDO = re.compile(rf"\b{_CLIMA_VERBO}\s+{_CLIMA_OBJ}\b")
# «manda el clima el sábado y domingo»: para el clima no hay «una sola vez», así
# que «el sábado» también es «los sábados».
_CLIMA_EL_DIA = re.compile(rf"\b(?:el|los)\s+(?P<lista>{_DIA}(?:\s+(?:[ye]\s+)?(?:el\s+|los\s+)?{_DIA})*)\b")
_CLIMA_RELLENO = re.compile(r"\b(?:por\s+favor|porfa|todos|todas|tambien|y)\b")
_CLIMA_QUE = (r"(?:(?:el|los|mis?|todos\s+los|todos\s+mis)\s+)?"
              r"(?:avisos?\s+(?:del?\s+|de\s+la\s+)?(?:clima|pronostico)|clima|pronostico)"
              r"(?:\s+(?:diario|programado|de\s+la\s+manana))?")
_CLIMA_LISTAR = re.compile(
    r"(?:que|cuales|cuantos)\s+avisos?\s+(?:del?\s+)?(?:clima|pronostico)\s+(?:tengo|hay|tienes)"
    r"(?:\s+(?:activos|programados|puestos))?|(?:mis|ver)\s+avisos?\s+del?\s+(?:clima|pronostico)|"
    r"a\s+que\s+hora\s+(?:me\s+)?(?:llega|mandas|envias)\s+el\s+(?:aviso\s+del\s+)?(?:clima|pronostico)")


def _clima(t: str, ahora: datetime) -> Intencion | None:
    """Pedir, pausar, reanudar, borrar o listar el aviso del clima. None si no es."""
    if _CLIMA_LISTAR.fullmatch(t):
        return Intencion("ordenes", tipo="clima")
    for accion, verbo in (("pausar", _PAUSAR), ("reanudar", _REANUDAR), ("cancelar", _CANCELAR)):
        if re.fullmatch(rf"{verbo}\s+{_CLIMA_QUE}", t):
            return Intencion(accion, tipo="clima", todos=True)
    m = _CLIMA_PEDIDO.search(t)
    if not m:
        return None
    resto = t[:m.start()] + " " + t[m.end():]
    rec, resto, parte = recurrencia_dicha(resto)
    if rec is None:
        d = _CLIMA_EL_DIA.search(resto)
        if d:
            rec = {"dias": sorted({_DIA_NUM[x] for x in re.findall(_DIA, d.group("lista"))})}
            resto = resto[:d.start()] + " " + resto[d.end():]
    if rec is None or "dias" not in rec:
        return None  # sin repetición es una consulta (69); «cada 2 horas», tampoco
    hm = _hora_min(resto)
    resto = _sin_hora(resto) if hm else resto
    if _CLIMA_RELLENO.sub(" ", resto).split():
        return None  # sobró algo: «… a Camila», «… si llueve»; no es de acá
    if hm is None:
        return Intencion("crear", tipo="clima", extra={"falta": "hora"})
    rec = dict(rec, hora=_hora_recurrente(*hm, "clima", parte), feriados="fin_de_semana")
    return Intencion("crear", tipo="clima", vence=proxima(rec, ahora),
                     extra={"recurrencia": rec, "hasta_epoch": None})


def _nombre_de(resto: str) -> str:
    """'para los tallarines' → 'los tallarines'. Vacío si no hay nombre.

    Se busca el conector cuyo resto NO empieza con otro conector: al sacar la
    duración de "temporizador de 10 minutos para los tallarines" queda
    "de para los tallarines", y el primer "de" se llevaría el "para".
    """
    resto = " ".join(resto.split())
    for m in re.finditer(r"\b(?:para|de|del)\s+", resto):
        n = resto[m.end():].strip()
        if not n or re.match(r"(?:para|de|del)\b", n):
            continue
        if not re.match(r"(?:el|la|los|las|mi|mis)\s+.+|[a-zñ]", n):
            continue
        # Lo que quedó de la duración o de la hora no es un nombre.
        if duracion(n) or re.fullmatch(rf"{NUM}.*", n) or n in ("hoy", "manana"):
            return ""
        return n[:40]
    return ""


def _sin_hora(texto: str) -> str:
    """La frase sin la hora dicha (sólo la primera: el resto es texto)."""
    for patron in (_MEDIODIA, _MEDIANOCHE):
        if patron.search(texto):
            return patron.sub(" ", texto, count=1)
    return _HORA.sub(" ", texto, count=1)


def _texto_recordatorio(resto: str) -> str:
    """Lo que hay que recordar: la frase sin el verbo, la hora ni la recurrencia."""
    resto = re.sub(rf"\b{_RECORDAR}\b", " ", resto)
    resto = re.sub(rf"^\s*(?:{_CREAR}\s+)?(?:(?:un|una|otro|el)\s+)?{_RECORDATORIO}\b", " ", resto)
    resto = re.sub(r"\bpor\s+favor\b", " ", resto)
    resto = " ".join(resto.split())
    resto = re.sub(r"^(?:(?:que|de|para|y|:)\s+)+", "", resto)
    resto = re.sub(r"\s+(?:y|que|de|para)$", "", resto)
    return resto[:80].strip()


def _crear_recurrente(tipo: str, rec: dict[str, Any], parte: str, hasta: int | None,
                      resto: str, ahora: datetime) -> Intencion:
    """La intención de una orden recurrente, con su recurrencia ya completa."""
    extra: dict[str, Any] = {"hasta_epoch": hasta}
    if "dias" in rec:
        hm = _hora_min(resto)
        if hm is None:
            return Intencion("crear", tipo=tipo, extra={"falta": "hora"})
        rec = dict(rec, hora=_hora_recurrente(*hm, tipo, parte))
        resto = _sin_hora(resto)
    elif rec["cada_seg"] < MIN_INTERVALO:
        return Intencion("crear", tipo=tipo, extra={"falta": "intervalo"})
    if tipo == "recordatorio":
        nombre = _texto_recordatorio(resto)
        if not nombre:
            return Intencion("crear", tipo=tipo, extra={"falta": "texto"})
    else:
        nombre = _nombre_de(re.sub(r"\bmanana\b", "", resto))
    extra["recurrencia"] = rec
    return Intencion("crear", tipo=tipo, vence=proxima(rec, ahora), nombre=nombre, extra=extra)


def interpretar(texto: str, ahora: datetime | None = None,
                sonando: bool = False) -> Intencion | None:
    """Lee una frase y devuelve qué se pidió, o None si no es de temporizadores.

    `sonando`: si hay algo sonando, las palabras sueltas ("para", "ya", "listo")
    paran. Sin nada sonando NO se capturan: "ya" a secas no es una orden.
    """
    ahora = ahora or datetime.now().astimezone()
    t = VOCATIVO_RE.sub("", normalizar(texto))
    if not t:
        return None
    if _PARAR.match(t):
        return Intencion("parar") if sonando else None
    if _PARAR_OBJETO.match(t) and sonando:
        return Intencion("parar")
    clima = _clima(t, ahora)
    if clima is not None:
        return clima

    menciona_temp = re.search(rf"\b{_TEMP}", t)
    menciona_alarma = re.search(rf"\b{_ALARMA}|\bdespiertame\b|\bdespertarme\b", t)
    recordar = re.search(rf"\b{_RECORDAR}\b", t)
    menciona_rec = recordar or re.search(rf"\b{_RECORDATORIO}\b", t)
    tipo = "alarma" if menciona_alarma and not menciona_temp else \
        "recordatorio" if menciona_rec and not menciona_temp else "temporizador"

    # Órdenes permanentes: listar, pausar y reanudar. Sólo con el objeto dicho:
    # «pausa» a secas sigue siendo del Roku, y «pausa el temporizador» no es de acá.
    if _LISTAR_ORDENES.fullmatch(t):
        return Intencion("ordenes", tipo="")
    for accion, verbo in (("pausar", _PAUSAR), ("reanudar", _REANUDAR)):
        m = re.match(rf"{verbo}\s+(?:(?:el|la|los|las|mi|mis|todas\s+las|todas\s+mis|todos\s+los)\s+)?"
                     rf"(?P<que>{_ALARMA}|{_RECORDATORIO}|{_ORDEN})\b(?P<resto>.*)$", t)
        if m and not menciona_temp:
            que = m.group("que")
            todos = bool(re.search(r"\b(?:todos|todas)\b", t))
            return Intencion(accion, todos=todos, nombre="" if todos else _nombre_de(m.group("resto")),
                             tipo="alarma" if re.match(_ALARMA, que) else
                             "recordatorio" if re.match(_RECORDATORIO, que) else "",
                             # Lo que no nombra una alarma puede ser de otra cosa
                             # (una orden de compra): si no calza con nada, sigue.
                             extra={"tentativo": not re.match(_ALARMA, que)})

    # Consultar: "cuánto le queda", "cuánto falta para los tallarines",
    # "qué temporizadores hay", "a qué hora suena la alarma".
    if re.search(r"\bcuanto\s+(?:tiempo\s+)?(?:le\s+)?(?:queda|falta)n?\b", t) or \
       re.search(rf"\b(?:que|cuales|cuantos|cuantas)\s+(?:{_TEMP}|{_ALARMA}|{_RECORDATORIO})", t) or \
       re.search(rf"\b(?:tengo|hay)\s+(?:algun(?:a|o)?\s+)?(?:{_TEMP}|{_ALARMA}|{_RECORDATORIO})", t) or \
       re.search(rf"\ba\s+que\s+hora\s+(?:suena|es)\s+(?:la\s+)?{_ALARMA}", t):
        resto = re.sub(r".*\b(?:queda|falta)n?\b", "", t) if re.search(r"queda|falta", t) else ""
        nombre = _nombre_de(resto) if resto else ""
        # "cuánto falta para el 18 de septiembre" también calza. Sin la palabra
        # temporizador/alarma la consulta es TENTATIVA: `responder` sólo la toma
        # si el nombre coincide con un temporizador vivo; si no, sigue al router.
        # «le queda» ya habla de un temporizador; «falta para» puede ser cualquier cosa.
        tentativo = bool(nombre) and not (menciona_temp or menciona_alarma) \
            and not re.search(r"\ble\s+queda", t)
        # «qué recordatorios tengo» también puede ser de la agenda: sin ninguno
        # propio, sigue al clasificador.
        if tipo == "recordatorio":
            tentativo = True
        return Intencion("consultar", tipo=tipo if (menciona_temp or menciona_alarma or menciona_rec) else "",
                         nombre=nombre, extra={"tentativo": tentativo})

    # Cancelar: "cancela el temporizador (de los tallarines)", "borra todas las alarmas".
    if re.search(rf"^{_CANCELAR}\b", t) and (menciona_temp or menciona_alarma):
        todos = bool(re.search(r"\b(?:todos|todas)\b", t))
        resto = re.split(rf"{_TEMP}|{_ALARMA}", t, maxsplit=1)[-1]
        return Intencion("cancelar", tipo=tipo, todos=todos,
                         nombre="" if todos else _nombre_de(resto))
    # «borra el recordatorio de la basura», «borra la orden de regar». Tentativo:
    # si no hay ninguno que calce, puede ser de la agenda y sigue al clasificador.
    m = re.match(rf"{_CANCELAR}\s+(?:(?:el|la|los|las|mi|mis|todas\s+las|todas\s+mis|todos\s+los|todos\s+mis)\s+)?"
                 rf"(?P<que>{_RECORDATORIO}|{_ORDEN})\b(?P<resto>.*)$", t)
    if m:
        todos = bool(re.search(r"\b(?:todos|todas)\b", t))
        es_rec = bool(re.match(_RECORDATORIO, m.group("que")))
        return Intencion("cancelar", tipo="recordatorio" if es_rec else "", todos=todos,
                         nombre="" if todos else _nombre_de(m.group("resto")),
                         extra={"tentativo": True, "solo_ordenes": not es_rec})

    # Agregar: "agrega 5 minutos (al de los tallarines)", "súmale 2 minutos".
    m = re.search(r"^(?:agrega(?:le)?|suma(?:le)?|anade(?:le)?|dale|ponle)\s+(?:otros?\s+)?(.+)$", t)
    if m and (menciona_temp or re.search(r"\bmas\b", t) or re.search(r"\bal\s+(?:de|del)\b", t)):
        d = duracion(m.group(1))
        if d:
            resto = m.group(1).replace(d[1], " ")
            nombre = ""
            mn = re.search(r"\bal?\s+(?:temporizador\s+)?(?:de|del)\s+(.+)$", resto)
            if mn:
                nombre = mn.group(1).strip()[:40]
            return Intencion("agregar", segundos=d[0], nombre=nombre)

    # Crear alarma: "pon una alarma a las 7", "despiértame mañana a las 6 y media".
    # Con recurrencia la frase puede empezar por ella: «todos los días pon una
    # alarma a las 7». Se mira el comienzo de lo que queda al sacarla.
    rec, sin_rec, parte = recurrencia_dicha(t)
    hasta, sin_rec = vencimiento_dicho(sin_rec, ahora) if rec else (None, sin_rec)
    sin_rec = " ".join(sin_rec.split())
    if menciona_alarma and (
            re.search(rf"^{_CREAR}\b", t) or re.search(r"\bdespiertame\b|\bdespertarme\b", t)
            or re.search(rf"^{_ALARMA}\b", t)
            or (rec and re.search(rf"^(?:{_CREAR}|{_ALARMA})\b", sin_rec))):
        if rec:
            return _crear_recurrente("alarma", rec, parte, hasta, sin_rec, ahora)
        if _REC_NO_SOPORTADA.search(t):
            return Intencion("crear", tipo="alarma", extra={"falta": "recurrencia"})
        h = hora_dicha(t, ahora)
        if h:
            resto = _HORA.sub(" ", t)
            return Intencion("crear", tipo="alarma", vence=h[0], ambigua=h[1],
                             nombre=_nombre_de(re.sub(r"\bmanana\b", "", resto)))
        return Intencion("crear", tipo="alarma", extra={"falta": "hora"})

    # Recordatorio: «recuérdame todos los lunes a las 8 sacar la basura», «cada 2
    # horas recuérdame tomar agua», «recuérdame a las 8 llamar al médico».
    if not menciona_temp and (recordar or re.search(
            rf"^(?:{_CREAR}\s+)?(?:(?:un|una|otro|el)\s+)?{_RECORDATORIO}\b", sin_rec if rec else t)):
        if rec:
            return _crear_recurrente("recordatorio", rec, parte, hasta, sin_rec, ahora)
        if _REC_NO_SOPORTADA.search(t):
            return Intencion("crear", tipo="recordatorio", extra={"falta": "recurrencia"})
        # De una sola vez: sólo con una hora o un plazo dichos y dentro de 24 h.
        # «recuérdame comprar pan» o «recuérdame el lunes…» siguen al clasificador.
        if _OTRO_DIA.search(t):
            return None
        m = re.search(r"\b(?:en|dentro\s+de)\s+(.+)$", t)
        d = duracion(m.group(1)) if m else None
        if m and d and m.group(1).startswith(d[1]):
            resto = t[:m.start()] + " " + m.group(1)[len(d[1]):]
            return Intencion("crear", tipo="recordatorio", vence=ahora + timedelta(seconds=d[0]),
                             nombre=_texto_recordatorio(resto))
        h = hora_dicha(t, ahora)
        if not h:
            return None
        resto = re.sub(r"\b(?:hoy|manana)\b", " ", re.sub(r"de\s+la\s+manana", " de_la_manana", t))
        resto = resto.replace("de_la_manana", "de la manana")
        return Intencion("crear", tipo="recordatorio", vence=h[0], ambigua=h[1],
                         nombre=_texto_recordatorio(_sin_hora(resto)))

    # Crear temporizador: "pon un temporizador de 10 minutos para los tallarines",
    # "temporizador 3 minutos", "avísame en 20 minutos".
    if menciona_temp or re.search(r"^(?:avisame|avisa(?:me)?)\s+en\b", t):
        d = duracion(t)
        if d:
            resto = t.replace(d[1], " ", 1)
            resto = re.sub(rf"\b{_TEMP}\b", " ", resto)
            nombre = _nombre_de(re.sub(r"\s+", " ", resto))
            return Intencion("crear", tipo="temporizador", segundos=d[0], nombre=nombre)
        if menciona_temp and re.search(rf"^{_CREAR}\b|^{_TEMP}", t):
            return Intencion("crear", tipo="temporizador", extra={"falta": "duracion"})
    return None


# ---------------------------------------------------------------------------
# Estado en disco (mismo molde que compras.py)
# ---------------------------------------------------------------------------

class _Sesion:
    """Lee el JSON con el lock tomado y lo devuelve escrito al salir.

    Copia deliberada de `compras._Sesion` con otro archivo: el lock va en un
    archivo aparte (el JSON se reemplaza por rename) y todo `chmod` es explícito
    porque `UMask=0077` de las unidades gana sobre el setgid del directorio.
    """

    def __init__(self, escribe: bool) -> None:
        self.escribe = escribe
        self.datos: dict[str, Any] = {}

    def __enter__(self) -> "_Sesion":
        CASA_DIR.mkdir(parents=True, exist_ok=True)
        nuevo = not LOCK.exists()
        self._lock = LOCK.open("a+")
        if nuevo:
            try:
                os.chmod(LOCK, MODO_ARCHIVO)
            except OSError:
                pass
        if POSIX:
            fcntl.flock(self._lock, fcntl.LOCK_EX)
        try:
            self.datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
            if not isinstance(self.datos.get("items"), list):
                raise ValueError("estructura inesperada")
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            self.datos = {"version": 1, "items": []}
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            if self.escribe and exc[0] is None:
                # `.tmp` propio de este proceso (trampa 23cr1): otro escritor no lo pisa.
                tmp = ARCHIVO.with_name(f".{ARCHIVO.stem}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
                try:
                    tmp.write_text(json.dumps(self.datos, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
                    os.chmod(tmp, MODO_ARCHIVO)
                    os.replace(tmp, ARCHIVO)
                finally:
                    tmp.unlink(missing_ok=True)
        finally:
            if POSIX:
                fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()

    @property
    def items(self) -> list[dict[str, Any]]:
        return self.datos["items"]


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


def _guardado(i: dict[str, Any], ahora: int) -> bool:
    """Si el ítem sigue en el archivo: los vivos siempre; los cerrados, un día
    (una orden vencida, una semana, para poder renovarla)."""
    if i["estado"] in VIVOS:
        return True
    limite = RETENCION_VENCIDA if i["estado"] == "vencida" else RETENCION
    return ahora - i.get("cerrado", ahora) < limite


def _purgar(items: list[dict[str, Any]], ahora: int) -> list[dict[str, Any]]:
    return [i for i in items if _guardado(i, ahora)]


def _es_orden(i: dict[str, Any]) -> bool:
    """Orden permanente: lo recurrente y lo que tiene vencimiento propio."""
    return bool(i.get("recurrencia")) or i.get("hasta_epoch") is not None


def activos(perfil: str, ahora: datetime | None = None) -> list[dict[str, Any]]:
    """Activos y sonando de ese perfil, del que vence primero al último."""
    with _Sesion(escribe=False) as s:
        # El aviso del clima no es un temporizador ni una alarma: sólo sale en /ordenes.
        mios = [i for i in s.items if i["perfil"] == perfil and i.get("tipo") != "clima"
                and i["estado"] in ("activo", "sonando", "pausado")]
    return sorted(mios, key=lambda i: i["vence"])


def _primera(recurrencia: dict[str, Any], hasta_epoch: int | None,
             ahora: datetime) -> tuple[dict[str, Any], datetime]:
    """Valida una orden recurrente y da su primera ocurrencia. ValueError hablable."""
    recurrencia = _validar_recurrencia(recurrencia)
    vence = proxima(recurrencia, ahora)
    tope = MAX_DIAS_CLIMA if recurrencia.get("feriados") else MAX_DIAS_RECURRENTE
    if (vence - ahora).total_seconds() > tope * 86400 + 60:
        raise ValueError(f"La próxima vez quedaría a más de {tope} días.")
    if hasta_epoch is not None and _epoch(vence) > hasta_epoch:
        raise ValueError("Esa orden vencería antes de sonar la primera vez.")
    return recurrencia, vence


def _cupo(items: list[dict[str, Any]], perfil: str, recurrente: bool) -> None:
    """Los dos topes van aparte: 10 recurrentes no impiden poner un temporizador."""
    vivos = [i for i in items if i["perfil"] == perfil and i["estado"] in VIVOS
             and bool(i.get("recurrencia")) == recurrente]
    if recurrente and len(vivos) >= MAX_RECURRENTES:
        raise ValueError(f"Ya tienes {MAX_RECURRENTES} órdenes recurrentes; borra alguna primero.")
    if not recurrente and len(vivos) >= MAX_ACTIVOS:
        raise ValueError(f"Ya tienes {MAX_ACTIVOS} activos; cancela alguno primero.")


def crear(perfil: str, tipo: str, vence: datetime | None, nombre: str = "",
          origen: str = "voz", ahora: datetime | None = None,
          recurrencia: dict[str, Any] | None = None,
          hasta_epoch: int | None = None) -> dict[str, Any]:
    """Guarda un temporizador, alarma o recordatorio. ValueError con el motivo hablable.

    Con `recurrencia`, `vence` se ignora y se calcula: es la próxima ocurrencia.
    Quien llama decide si una recurrente dictada por voz se guarda (ver `atender`).
    """
    ahora = ahora or datetime.now().astimezone()
    if tipo == "clima":
        recurrencia, nombre, hasta_epoch = _receta_clima(recurrencia), "", None
    if recurrencia:
        recurrencia, vence = _primera(recurrencia, hasta_epoch, ahora)
    seg = (vence - ahora).total_seconds()
    if not recurrencia:
        if seg < MIN_SEGUNDOS:
            raise ValueError("Eso es demasiado corto para un temporizador.")
        if seg > MAX_SEGUNDOS + 60:
            raise ValueError("Sólo puedo programar hasta 24 horas.")
    with _Sesion(escribe=True) as s:
        s.datos["items"] = _purgar(s.items, _epoch(ahora))
        if tipo == "clima" and any(_mismo_clima(i, perfil, recurrencia) for i in s.items):
            raise ValueError("Ya tienes ese aviso del clima.")
        _cupo(s.items, perfil, bool(recurrencia))
        item = _nuevo(perfil, tipo, nombre, origen, ahora, vence, seg, recurrencia, hasta_epoch)
        s.items.append(item)
    return item


def _nuevo(perfil: str, tipo: str, nombre: str, origen: str, ahora: datetime, vence: datetime,
           seg: float, recurrencia: dict[str, Any] | None, hasta_epoch: int | None) -> dict[str, Any]:
    item = {"id": uuid.uuid4().hex[:8], "perfil": perfil, "tipo": tipo,
            "nombre": nombre, "estado": "activo", "origen": origen,
            "creado": _epoch(ahora), "vence": _epoch(vence),
            "duracion": int(round(seg)) if tipo == "temporizador" else 0}
    if recurrencia:
        item["recurrencia"] = recurrencia
    if hasta_epoch is not None:
        item["hasta_epoch"] = int(hasta_epoch)
    if tipo == "clima":
        item["lugar"] = None  # = el del perfil al enviar (la 76 sólo cambia ese)
    return item


def _receta_clima(recurrencia: dict[str, Any] | None) -> dict[str, Any]:
    """Un aviso de clima es sólo por días y con los feriados como fin de semana."""
    if not recurrencia or "dias" not in recurrencia:
        raise ValueError("El aviso del clima va por días y a una hora: «de lunes a viernes a las 7:30».")
    return _validar_recurrencia(dict(recurrencia, feriados="fin_de_semana"))


def _mismo_clima(i: dict[str, Any], perfil: str, rec: dict[str, Any]) -> bool:
    return (i["perfil"] == perfil and i.get("tipo") == "clima" and i["estado"] in VIVOS
            and i.get("recurrencia") == rec)


def _elegir(candidatos: list[dict[str, Any]], nombre: str) -> list[dict[str, Any]]:
    if not nombre:
        return candidatos
    clave = normalizar(nombre)
    clave = re.sub(r"^(?:el|la|los|las|mi|mis)\s+", "", clave)
    return [i for i in candidatos if clave and clave in _buscable(i)]


def _buscable(i: dict[str, Any]) -> str:
    """Por qué se puede nombrar un ítem: su nombre y, si es recurrente, sus días
    («la alarma de los lunes», «la de lunes a viernes», «el de cada 2 horas»)."""
    texto = i["nombre"]
    rec = i.get("recurrencia")
    if rec:
        texto += " " + decir_recurrencia(rec)
        for d in rec.get("dias", []):
            texto += f" {DIAS[d]} {_DIAS_PLURAL[d]}"
    return normalizar(texto)


def cancelar(perfil: str, nombre: str = "", todos: bool = False, tipo: str = "",
             ahora: datetime | None = None, solo_ordenes: bool = False
             ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Cancela y devuelve (cancelados, candidatos_si_era_ambiguo).

    Sin nombre y con más de uno activo NO cancela nada: devuelve los candidatos
    para preguntar cuál. Cancelar es directo, pero adivinar cuál no lo es.
    """
    ahora_e = _epoch(ahora or datetime.now().astimezone())
    with _Sesion(escribe=True) as s:
        vivos = [i for i in s.items if i["perfil"] == perfil
                 and i["estado"] in ("activo", "sonando", "pausado") and (not tipo or i["tipo"] == tipo)
                 and (not solo_ordenes or _es_orden(i))]
        elegidos = vivos if todos else _elegir(vivos, nombre)
        if not todos and len(elegidos) > 1:
            return [], elegidos
        for i in elegidos:
            _cerrar(i, ahora_e)
    return elegidos, []


def _cerrar(i: dict[str, Any], ahora_e: int) -> None:
    """Cancela un ítem. Una orden permanente no se cancela: queda `borrado`, con
    el estado que tenía, y se puede recuperar (ver `deshacer`)."""
    if _es_orden(i):
        i["antes"] = "pausado" if i["estado"] == "pausado" else "activo"
        i["estado"], i["cerrado"] = "borrado", ahora_e
    else:
        i["estado"], i["cerrado"] = "cancelado", ahora_e


def agregar(perfil: str, segundos: int, nombre: str = "",
            ahora: datetime | None = None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Suma tiempo a un temporizador activo. (actualizado, candidatos_si_ambiguo)."""
    with _Sesion(escribe=True) as s:
        vivos = [i for i in s.items if i["perfil"] == perfil and i["estado"] == "activo"
                 and i["tipo"] == "temporizador"]
        elegidos = _elegir(vivos, nombre)
        if len(elegidos) != 1:
            return None, elegidos
        i = elegidos[0]
        if i["vence"] + segundos - _epoch(ahora or datetime.now().astimezone()) > MAX_SEGUNDOS:
            raise ValueError("Sólo puedo programar hasta 24 horas.")
        i["vence"] += segundos
        i["duracion"] += segundos
    return i, []


# --- Lo que usa `parlante.service` -------------------------------------------

def vencidos(ahora: datetime | None = None, perfil: str | None = None
             ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(para_sonar, solo_avisar) y los marca para no devolverlos dos veces.

    para_sonar: vencieron hace menos de GRACIA segundos → `sonando`.
    solo_avisar: vencieron con el nodo apagado → `perdido`, aviso por Telegram.

    `perfil`: mientras no exista `parlante.service`, cada bot revisa SÓLO los
    suyos y avisa por su propio chat. Sin el filtro, el hilo de Jaime marcaría
    el temporizador de Camila y se lo avisaría a Diego. `parlante` llama con
    perfil=None: es uno solo para la casa.
    """
    ahora = ahora or datetime.now().astimezone()
    ahora_e = _epoch(ahora)
    sonar, avisar = [], []
    with _Sesion(escribe=True) as s:
        for i in s.items:
            if perfil is not None and i["perfil"] != perfil:
                continue
            if i.get("tipo") == "clima":
                continue  # nunca suena: es de `climas_vencidos` (regla 8)
            rec = i.get("recurrencia")
            if i["estado"] == "activo" and i["vence"] <= ahora_e:
                if ahora_e - i["vence"] <= GRACIA:
                    i["estado"] = "sonando"
                    sonar.append(dict(i))
                elif rec:
                    # Recurrente perdida: UN aviso, con cuántas se saltaron, y
                    # directo a la próxima futura. Nunca suenan todas juntas.
                    copia = dict(i)
                    copia["perdidas"], siguiente = _saltar(rec, i["vence"], ahora)
                    _reprogramar(i, ahora, siguiente)
                    copia["proxima"] = i["vence"] if i["estado"] == "activo" else None
                    # Si con la caída además pasó su término, queda `vencida` y
                    # sale UN aviso, el de vencimiento (`vencidas_sin_avisar`),
                    # que trae «Renovar»: no dos mensajes por la misma orden.
                    if i["estado"] == "activo":
                        avisar.append(copia)
                else:
                    i["estado"], i["cerrado"] = "perdido", ahora_e
                    avisar.append(dict(i))
            elif i["estado"] == "activo" and rec:
                _realinear(i, ahora)
            if i["estado"] in ("activo", "pausado") and i.get("hasta_epoch") is not None \
                    and i["hasta_epoch"] <= ahora_e:
                i["estado"], i["cerrado"] = "vencida", ahora_e
    return sonar, avisar


def climas_vencidos(perfil: str, ahora: datetime | None = None
                    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(a_enviar, perdidos) entre los avisos de clima del perfil (regla 8).

    Cada uno queda reprogramado a su próxima ocurrencia futura ANTES de devolverlo:
    si después el envío falla, no se reintenta en cada vuelta. `a_enviar`: la
    última ocurrencia pasada fue hace `GRACIA_CLIMA` o menos (un reinicio del bot
    a las 7:31 todavía manda el de las 7:30). `perdidos`: el nodo estuvo apagado
    más que eso; no se manda tarde. La copia lleva `ocurrencia` (la que tocaba),
    `perdidas` (cuántas quedaron atrás sin mandar) y `proxima`.
    """
    ahora = ahora or datetime.now().astimezone()
    ahora_e = _epoch(ahora)
    enviar, perdidos = [], []
    with _Sesion(escribe=True) as s:
        for i in s.items:
            if i["perfil"] != perfil or i.get("tipo") != "clima" or i["estado"] != "activo":
                continue
            rec = i.get("recurrencia")
            try:
                rec = _validar_recurrencia(rec) if isinstance(rec, dict) and "dias" in rec else None
            except (ValueError, TypeError, KeyError):
                rec = None
            if rec is None:
                continue  # escrito a mano o roto: no se manda ni tumba la vuelta
            if i["vence"] > ahora_e:
                _realinear(i, ahora)  # Cockpit reanudó con `ahora + restante`
                continue
            ultima, n, v = i["vence"], 0, datetime.fromtimestamp(i["vence"], timezone.utc)
            while v <= ahora and n < 1000:
                ultima, n = _epoch(v), n + 1
                v = proxima(rec, v)
            if v <= ahora:
                v = proxima(rec, ahora)
            copia = dict(i, ocurrencia=ultima, proxima=_epoch(v))
            _reprogramar(i, ahora, v)
            if ahora_e - ultima <= GRACIA_CLIMA:
                enviar.append(dict(copia, perdidas=n - 1))
            else:
                perdidos.append(dict(copia, perdidas=n))
    return enviar, perdidos


def climas(perfil: str) -> list[dict[str, Any]]:
    """Los avisos de clima vivos del perfil, del primero de la semana al último."""
    def sano(i: dict[str, Any]) -> bool:
        try:
            return "dias" in _validar_recurrencia(i["recurrencia"])
        except (ValueError, TypeError, KeyError, AttributeError):
            return False

    with _Sesion(escribe=False) as s:
        mios = [dict(i) for i in s.items if i["perfil"] == perfil and i.get("tipo") == "clima"
                and i["estado"] in ("activo", "pausado") and sano(i)]
    return sorted(mios, key=lambda i: (min(i["recurrencia"]["dias"]), i["recurrencia"]["hora"]))


def programar_clima(perfil: str, horarios: list[dict[str, Any]], origen: str = "telegram",
                    ahora: datetime | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reemplaza TODOS los avisos de clima del perfil por `horarios` ({"dias", "hora"}),
    en una sola sesión del archivo: nunca quedan duplicados. Los de antes quedan
    `borrado` (recuperables una hora). Devuelve (nuevos, borrados). ValueError si no cabe."""
    ahora = ahora or datetime.now().astimezone()
    ahora_e = _epoch(ahora)
    listos = [_primera(_receta_clima(h), None, ahora) for h in horarios]
    with _Sesion(escribe=True) as s:
        s.datos["items"] = _purgar(s.items, ahora_e)
        viejos = [i for i in s.items if i["perfil"] == perfil and i.get("tipo") == "clima"
                  and i["estado"] in VIVOS]
        quedan = [i for i in s.items if not any(i is v for v in viejos)]
        for _ in listos:
            _cupo(quedan, perfil, True)
            quedan.append({"perfil": perfil, "estado": "activo", "recurrencia": True})
        for i in viejos:
            _cerrar(i, ahora_e)
        nuevos = [_nuevo(perfil, "clima", "", origen, ahora, vence, (vence - ahora).total_seconds(), rec, None)
                  for rec, vence in listos]
        s.items.extend(nuevos)
        return [dict(i) for i in nuevos], [dict(i) for i in viejos]


def _reprogramar(i: dict[str, Any], ahora: datetime, siguiente: datetime | None = None) -> None:
    """Deja una recurrente lista para su próxima ocurrencia futura, o `vencida`
    si esa ocurrencia ya cae después de su `hasta_epoch`."""
    if siguiente is None:
        siguiente = _saltar(i["recurrencia"], i["vence"], ahora)[1]
    i.pop("restante", None)
    i.pop("pausado_en", None)
    if i.get("hasta_epoch") is not None and _epoch(siguiente) > i["hasta_epoch"]:
        i["estado"], i["cerrado"] = "vencida", _epoch(ahora)
        return
    i["estado"], i["vence"] = "activo", _epoch(siguiente)
    i.pop("cerrado", None)


def _realinear(i: dict[str, Any], ahora: datetime) -> None:
    """Corrige un `vence` futuro que no es una ocurrencia de su recurrencia.

    Pasa cuando Cockpit reanuda una pausa: `temporizador-accion.py` no sabe de
    recurrencia y deja `vence = ahora + restante`, que para «los lunes a las 8»
    es cualquier hora. «Correr ahora» no pasa por acá (deja `vence` en el
    presente, suena, y `parar` reprograma)."""
    rec = i["recurrencia"]
    if "dias" in rec:
        esperado = _epoch(proxima(rec, ahora))
    elif _en_ventana(_local(datetime.fromtimestamp(i["vence"], timezone.utc)), rec):
        return
    else:
        esperado = _epoch(proxima(rec, ahora, ancla=i["vence"] - int(rec["cada_seg"])))
    if i["vence"] != esperado:
        i["vence"] = esperado


def sonando(perfil: str | None = None) -> list[dict[str, Any]]:
    """Los que están en `sonando`. El aviso por Telegram los recorre en cada
    vuelta: si el envío falló (sin red) o el bot se reinició entre marcar y
    avisar, el aviso sale en la vuelta siguiente en vez de perderse."""
    with _Sesion(escribe=False) as s:
        return [dict(i) for i in s.items if i["estado"] == "sonando"
                and (perfil is None or i["perfil"] == perfil)]


def parar(perfil: str | None = None, ids: list[str] | None = None,
          ahora: datetime | None = None) -> list[dict[str, Any]]:
    """Corta lo que está sonando (de un perfil, o todo si perfil es None).

    En la casa cualquiera puede decir "para": si suena el de Diego y Camila lo
    para, es lo que haría cualquiera con una alarma ajena. Por eso `escucha`
    llama esto con perfil=None cuando hay algo sonando.
    """
    ahora = ahora or datetime.now().astimezone()
    ahora_e = _epoch(ahora)
    parados = []
    with _Sesion(escribe=True) as s:
        for i in s.items:
            if i["estado"] == "sonando" and (perfil is None or i["perfil"] == perfil) \
               and (ids is None or i["id"] in ids):
                if i.get("recurrencia"):
                    _reprogramar(i, ahora)  # una recurrente no termina: vuelve a esperar
                else:
                    i["estado"], i["cerrado"] = "terminado", ahora_e
                parados.append(dict(i))
    return parados


# --- Órdenes permanentes: listar, pausar, reanudar, borrar, deshacer, renovar ---

def ordenes(perfil: str, ahora: datetime | None = None) -> list[dict[str, Any]]:
    """Las órdenes del perfil: recurrentes y con vencimiento, vivas, más las
    vencidas que todavía se pueden renovar. De la que suena primero a la última."""
    ahora_e = _epoch(ahora or datetime.now().astimezone())
    with _Sesion(escribe=False) as s:
        mias = [dict(i) for i in s.items if i["perfil"] == perfil and _es_orden(i)
                and (i["estado"] in VIVOS or i["estado"] == "vencida") and _guardado(i, ahora_e)]
    return sorted(mias, key=lambda i: (i["estado"] == "vencida", i["estado"] == "pausado", i["vence"]))


def renovable(i: dict[str, Any], ahora: datetime | None = None) -> bool:
    """Si corresponde ofrecer «🔁 Renovar»: ya venció o vence en menos de 7 días."""
    if i.get("hasta_epoch") is None:
        return False
    ahora_e = _epoch(ahora or datetime.now().astimezone())
    return i["estado"] == "vencida" or i["hasta_epoch"] - ahora_e < AVISO_RENOVAR


def _mias(s: _Sesion, perfil: str, estados: tuple[str, ...], nombre: str, tipo: str,
          ids: list[str] | None, todos: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Órdenes del perfil en esos estados que calzan. (elegidas, dudosas)."""
    cand = [i for i in s.items if i["perfil"] == perfil and _es_orden(i) and i["estado"] in estados
            and (not tipo or i["tipo"] == tipo) and (ids is None or i["id"] in ids)]
    elegidos = cand if (todos or ids is not None) else _elegir(cand, nombre)
    if not todos and ids is None and len(elegidos) > 1:
        return [], elegidos
    return elegidos, []


def pausar(perfil: str, nombre: str = "", tipo: str = "", ids: list[str] | None = None,
           todos: bool = False, ahora: datetime | None = None
           ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pone en pausa órdenes activas. (pausadas, candidatas_si_era_ambiguo).

    Sólo órdenes permanentes: un temporizador de cocina no se pausa por acá. No
    pide confirmación; el bot ofrece deshacer. Guarda `restante` porque es lo
    que Cockpit y `temporizador-accion.py` esperan de un `pausado`."""
    ahora_e = _epoch(ahora or datetime.now().astimezone())
    with _Sesion(escribe=True) as s:
        elegidos, dudosos = _mias(s, perfil, ("activo",), nombre, tipo, ids, todos)
        for i in elegidos:
            i["estado"], i["pausado_en"] = "pausado", ahora_e
            i["restante"] = max(0, i["vence"] - ahora_e)
        return [dict(i) for i in elegidos], [dict(i) for i in dudosos]


def reanudar(perfil: str, nombre: str = "", tipo: str = "", ids: list[str] | None = None,
             todos: bool = False, ahora: datetime | None = None
             ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Saca de la pausa y reprograma a la próxima ocurrencia futura."""
    ahora = ahora or datetime.now().astimezone()
    with _Sesion(escribe=True) as s:
        elegidos, dudosos = _mias(s, perfil, ("pausado",), nombre, tipo, ids, todos)
        for i in elegidos:
            _despertar(i, ahora)
        return [dict(i) for i in elegidos], [dict(i) for i in dudosos]


def _despertar(i: dict[str, Any], ahora: datetime) -> None:
    """Vuelve una orden a `activo` con un `vence` futuro (o a `vencida` si ya
    pasó su `hasta_epoch`)."""
    ahora_e = _epoch(ahora)
    if i.get("recurrencia"):
        _reprogramar(i, ahora, proxima(i["recurrencia"], ahora))
        return
    vence = ahora_e + int(i.pop("restante", max(0, i["vence"] - ahora_e)))
    i.pop("pausado_en", None)
    if i.get("hasta_epoch") is not None and i["hasta_epoch"] <= ahora_e:
        i["estado"], i["cerrado"] = "vencida", ahora_e
        return
    i["estado"], i["vence"] = "activo", vence
    i.pop("cerrado", None)


def borrar(perfil: str, ids: list[str], ahora: datetime | None = None) -> list[dict[str, Any]]:
    """Borra órdenes por id (los botones de /ordenes). Quedan `borrado`."""
    ahora_e = _epoch(ahora or datetime.now().astimezone())
    with _Sesion(escribe=True) as s:
        elegidos = [i for i in s.items if i["perfil"] == perfil and _es_orden(i)
                    and i["id"] in ids and (i["estado"] in VIVOS or i["estado"] == "vencida")]
        for i in elegidos:
            if i["estado"] == "vencida":
                i["antes"], i["estado"], i["cerrado"] = "vencida", "borrado", ahora_e
            else:
                _cerrar(i, ahora_e)
        return [dict(i) for i in elegidos]


def deshacer(perfil: str, que: str, ident: str, ahora: datetime | None = None) -> dict[str, Any]:
    """Vuelve atrás una creación, una pausa o un borrado de la última hora.

    `que`: crear | pausar | borrar, el que traía el botón. Se comprueba contra el
    estado real, así un botón viejo apretado dos veces no hace nada raro.
    Devuelve el ítem como quedó (con `estado` "eliminado" si se deshizo una
    creación). ValueError con el motivo si ya no se puede.
    """
    ahora = ahora or datetime.now().astimezone()
    ahora_e = _epoch(ahora)
    with _Sesion(escribe=True) as s:
        i = next((x for x in s.items if x["id"] == ident and x["perfil"] == perfil), None)
        if i is None:
            raise ValueError("Esa orden ya no existe.")
        desde = {"crear": i.get("creado"), "pausar": i.get("pausado_en"), "borrar": i.get("cerrado")}.get(que)
        if desde is None or ahora_e - desde > DESHACER_SEG:
            raise ValueError("Ya pasó la hora para deshacer.")
        if que == "crear" and i["estado"] in VIVOS:
            s.datos["items"] = [x for x in s.items if x is not i]
            return dict(i, estado="eliminado")
        if que == "pausar" and i["estado"] == "pausado":
            _despertar(i, ahora)
            return dict(i)
        if que == "borrar" and i["estado"] == "borrado":
            antes = i.pop("antes", "activo")
            _cupo(s.items, perfil, bool(i.get("recurrencia")))
            if antes == "vencida":
                i["estado"] = "vencida"
            elif antes == "pausado":
                i["estado"] = "pausado"
                i.pop("cerrado", None)
            else:
                i.pop("cerrado", None)
                i["estado"] = "pausado"  # para que `_despertar` lo reprograme al futuro
                _despertar(i, ahora)
            return dict(i)
        raise ValueError("Eso ya no se puede deshacer.")


def renovar(perfil: str, ident: str, dias: int = RENOVAR_DIAS,
            ahora: datetime | None = None) -> dict[str, Any]:
    """Corre el vencimiento de una orden a `dias` días desde ahora. Si ya había
    vencido, vuelve a quedar activa. ValueError con el motivo si no se puede."""
    ahora = ahora or datetime.now().astimezone()
    with _Sesion(escribe=True) as s:
        i = next((x for x in s.items if x["id"] == ident and x["perfil"] == perfil
                  and x.get("hasta_epoch") is not None
                  and (x["estado"] in VIVOS or x["estado"] == "vencida")), None)
        if i is None:
            raise ValueError("Esa orden ya no existe o no tiene vencimiento.")
        if i["estado"] == "vencida":
            _cupo(s.items, perfil, bool(i.get("recurrencia")))
        i["hasta_epoch"] = _epoch(_local(ahora) + timedelta(days=dias))
        i.pop("avisada", None)
        if i["estado"] == "vencida":
            i["estado"] = "pausado"
            _despertar(i, ahora)
        return dict(i)


def vencidas_sin_avisar(perfil: str) -> list[dict[str, Any]]:
    """Órdenes que llegaron a su `hasta_epoch` y todavía no se avisaron. Mismo
    molde que `sonando`: se avisa y RECIÉN después se marca, para reintentar."""
    with _Sesion(escribe=False) as s:
        return [dict(i) for i in s.items if i["perfil"] == perfil
                and i["estado"] == "vencida" and not i.get("avisada")]


def marcar_avisadas(perfil: str, ids: list[str]) -> None:
    with _Sesion(escribe=True) as s:
        for i in s.items:
            if i["perfil"] == perfil and i["id"] in ids and i["estado"] == "vencida":
                i["avisada"] = True


def hay_sonando() -> bool:
    with _Sesion(escribe=False) as s:
        return any(i["estado"] == "sonando" for i in s.items)


# ---------------------------------------------------------------------------
# Frases para decir en voz alta (Piper lee mejor palabras que "19:00")
# ---------------------------------------------------------------------------

def decir_duracion(seg: int) -> str:
    """3725 → '1 hora, 2 minutos y 5 segundos'. Redondea a lo que importa."""
    seg = max(0, int(seg))
    h, resto = divmod(seg, 3600)
    m, s = divmod(resto, 60)
    if h:
        s = 0  # con horas, los segundos son ruido
    partes = []
    if h:
        partes.append(f"{h} hora" + ("s" if h != 1 else ""))
    if m:
        partes.append(f"{m} minuto" + ("s" if m != 1 else ""))
    if s or not partes:
        partes.append(f"{s} segundo" + ("s" if s != 1 else ""))
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def decir_hora(dt: datetime, ahora: datetime) -> str:
    """'hoy a las 7 de la tarde', 'mañana a las 6 y media de la mañana'."""
    h, m = dt.hour, dt.minute
    if h == 0 and m == 0:
        hora = "la medianoche"
    elif h == 12 and m == 0:
        hora = "el mediodía"
    else:
        h12 = h % 12 or 12
        periodo = ("de la madrugada" if h < 6 else "de la mañana" if h < 12
                   else "de la tarde" if h < 20 else "de la noche")
        minutos = ("" if m == 0 else " y media" if m == 30 else " y cuarto" if m == 15
                   else f" y {m}")
        hora = f"{'la' if h12 == 1 else 'las'} {h12}{minutos} {periodo}"
    dia = "hoy" if dt.date() == ahora.date() else (
        "mañana" if dt.date() == (ahora + timedelta(days=1)).date()
        else f"el {DIAS[dt.weekday()]} {dt.day}")
    return f"{dia} a {hora}"


def decir_dia(dt: datetime, ahora: datetime) -> str:
    """'hoy', 'mañana martes', 'el lunes 12'. Para decir cuándo es la próxima."""
    dt, ahora = _local(dt), _local(ahora)
    if dt.date() == ahora.date():
        return "hoy"
    if dt.date() == ahora.date() + timedelta(days=1):
        return f"mañana {DIAS[dt.weekday()]}"
    return f"el {DIAS[dt.weekday()]} {dt.day}"


def _decir_hhmm(valor: str) -> str:
    """'06:30' → 'a las 6:30 de la mañana'. Con dígitos: es una hora fija que se
    va a leer muchas veces en una lista, no una frase de una sola vez."""
    h, m = _hhmm(valor)
    if m == 0 and h in (0, 12):
        return "a la medianoche" if h == 0 else "al mediodía"
    h12 = h % 12 or 12
    periodo = ("de la madrugada" if h < 6 else "de la mañana" if h < 12
               else "de la tarde" if h < 20 else "de la noche")
    return f"a {'la' if h12 == 1 else 'las'} {h12}{f':{m:02d}' if m else ''} {periodo}"


def decir_recurrencia(rec: dict[str, Any]) -> str:
    """'de lunes a viernes a las 6:30 de la mañana', 'los sábados a las 9 de la
    mañana', 'cada 2 horas, entre las 08:00 y las 22:00'."""
    if "cada_seg" in rec:
        return f"cada {decir_duracion(rec['cada_seg'])}, entre las {rec['desde']} y las {rec['hasta']}"
    dias = rec["dias"]
    if len(dias) == 7:
        cuales = "todos los días"
    elif len(dias) >= 3 and dias == list(range(dias[0], dias[-1] + 1)):
        cuales = f"de {DIAS[dias[0]]} a {DIAS[dias[-1]]}"
    else:
        nombres = [_DIAS_PLURAL[d] for d in dias]
        cuales = "los " + (nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1])
    return f"{cuales} {_decir_hhmm(rec['hora'])}"


_DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def dias_cortos(dias: list[int]) -> str:
    """[0..4] → 'lun–vie', [5, 6] → 'sáb–dom', los 7 → 'todos los días'."""
    dias = sorted(set(dias))
    if len(dias) == 7:
        return "todos los días"
    if len(dias) >= 2 and dias == list(range(dias[0], dias[-1] + 1)):
        return f"{_DIAS_CORTOS[dias[0]]}–{_DIAS_CORTOS[dias[-1]]}"
    nombres = [_DIAS_CORTOS[d] for d in dias]
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _feriados_tambien(rec: dict[str, Any]) -> bool:
    """Si un feriado de semana también trae el aviso: cuenta como domingo."""
    return rec.get("feriados") == "fin_de_semana" and 6 in rec["dias"] and len(rec["dias"]) < 7


def horario_clima(rec: dict[str, Any]) -> str:
    """'lun–vie 7:30', 'sáb–dom 10:00'."""
    h, m = _hhmm(rec["hora"])
    return f"{dias_cortos(rec['dias'])} {h}:{m:02d}"


def rotulo_clima(i: dict[str, Any]) -> str:
    """Una orden de clima en /ordenes: 'Clima · sáb–dom 10:00 (feriados también)'."""
    rec = i["recurrencia"]
    return f"Clima · {horario_clima(rec)}" + (" (feriados también)" if _feriados_tambien(rec) else "")


def describir(i: dict[str, Any]) -> str:
    """Qué se entendió de una orden, entero: es lo que se confirma con el ✅.
    'Alarma de lunes a viernes a las 6:30 de la mañana', 'Recordatorio «regar»
    los domingos a las 10 de la mañana, hasta el 31-10'."""
    if i["tipo"] == "clima":
        rec = i["recurrencia"]
        feriados = ", también los feriados" if _feriados_tambien(rec) else \
            ", salvo los feriados" if rec.get("feriados") and 6 not in rec["dias"] else ""
        return f"Aviso del clima {decir_recurrencia(rec)}{feriados}"
    que = "Recordatorio" if i["tipo"] == "recordatorio" else "Alarma" if i["tipo"] == "alarma" else "Temporizador"
    if i.get("nombre"):
        que += f" «{i['nombre']}»"
    if i.get("recurrencia"):
        que += " " + decir_recurrencia(i["recurrencia"])
    if i.get("hasta_epoch") is not None:
        que += f", hasta el {_local(datetime.fromtimestamp(i['hasta_epoch'], timezone.utc)):%d-%m}"
    return que


def decir_proxima(i: dict[str, Any], ahora: datetime) -> str:
    """'mañana martes' para lo que tiene hora fija; con la hora si es un intervalo."""
    vence = _local(datetime.fromtimestamp(i["vence"], timezone.utc))
    dia = decir_dia(vence, ahora)
    if "dias" in (i.get("recurrencia") or {}):
        return dia
    return f"{dia} a las {vence:%H:%M}"


def linea_orden(i: dict[str, Any], ahora: datetime | None = None) -> str:
    """Una orden en una línea de /ordenes, con su próxima ocurrencia."""
    ahora = ahora or datetime.now().astimezone()
    if i["tipo"] == "clima":
        if i["estado"] == "pausado":
            return f"🌦️ {rotulo_clima(i)} — en pausa"
        vence = _local(datetime.fromtimestamp(i["vence"], timezone.utc))
        return f"🌦️ {rotulo_clima(i)} — próxima: {decir_dia(vence, ahora)} a las {vence:%H:%M}"
    if i["estado"] == "vencida":
        return f"⌛ {describir(i)} — venció"
    if i["estado"] == "pausado":
        return f"⏸️ {describir(i)} — en pausa"
    vence = _local(datetime.fromtimestamp(i["vence"], timezone.utc))
    return f"🔁 {describir(i)} — próxima: {decir_dia(vence, ahora)} a las {vence:%H:%M}"


def resumen_ordenes(perfil: str, ahora: datetime | None = None) -> str:
    """Las órdenes del perfil, numeradas como los botones de /ordenes."""
    ahora = ahora or datetime.now().astimezone()
    mias = ordenes(perfil, ahora)
    if not mias:
        return "No tienes órdenes permanentes."
    return "\n".join(f"{n}. {linea_orden(i, ahora)}" for n, i in enumerate(mias, 1))


def _cual(i: dict[str, Any]) -> str:
    if i["tipo"] == "clima":
        return f"el aviso del clima {decir_recurrencia(i['recurrencia']).rsplit(' a la', 1)[0]}"
    if i["tipo"] == "recordatorio":
        return f"el recordatorio de {i['nombre']}" if i["nombre"] else "el recordatorio"
    if i["nombre"]:
        return f"el de {i['nombre']}" if i["tipo"] == "temporizador" else f"la alarma de {i['nombre']}"
    if i["tipo"] == "alarma" and i.get("recurrencia"):
        rec = i["recurrencia"]
        cuando = f"cada {decir_duracion(rec['cada_seg'])}" if "cada_seg" in rec else \
            decir_recurrencia(rec).rsplit(" a la", 1)[0].rsplit(" al mediodía", 1)[0]
        return f"la alarma {cuando}" if cuando.startswith("de ") else f"la alarma de {cuando}"
    return "el temporizador" if i["tipo"] == "temporizador" else "la alarma"


def _rotulo(i: dict[str, Any]) -> str:
    """Cómo nombrar un ítem al preguntar «¿cuál?»."""
    if i["tipo"] == "temporizador":
        return i["nombre"] or decir_duracion(i["duracion"])
    return _cual(i)


def frase_vencimiento(item: dict[str, Any], persona: str) -> str:
    """Lo que dice el parlante al sonar. Lleva el nombre de la persona porque
    hay dos perfiles en la misma cocina."""
    if item["tipo"] == "recordatorio":
        return f"{persona}, recuerda: {item['nombre']}." if item["nombre"] else f"{persona}, tu recordatorio."
    if item["tipo"] == "alarma":
        que = f"la alarma de {item['nombre']}" if item["nombre"] else "tu alarma"
        return f"{persona}, sonó {que}."
    que = f"el temporizador de {item['nombre']}" if item["nombre"] else \
        f"el temporizador de {decir_duracion(item['duracion'])}"
    return f"{persona}, terminó {que}."


def frase_telegram(item: dict[str, Any], perdido: bool = False,
                   ahora: datetime | None = None) -> str:
    """El aviso escrito. Sin el nombre de la persona: el chat ya es de ella."""
    vence = datetime.fromtimestamp(item["vence"]).astimezone()
    if perdido and item.get("recurrencia"):
        # Una recurrente perdida no se cerró: un solo aviso, aunque fueran varias.
        ahora = ahora or datetime.now().astimezone()
        local = _local(vence)
        veces = item.get("perdidas", 1)
        saltos = f" Se saltaron {veces} veces desde entonces." if veces > 1 else ""
        sigue = " La orden ya venció." if item.get("proxima") is None else \
            f" La próxima es {decir_proxima(dict(item, vence=item['proxima']), ahora)}."
        return (f"⏰ {describir(item)}: no sonó el {DIAS[local.weekday()]} {local:%d-%m} a las "
                f"{local:%H:%M}, porque el bot estaba detenido.{saltos}{sigue}")
    if item["tipo"] == "recordatorio" and not perdido:
        return f"🔔 Recordatorio: {item['nombre'] or 'sin texto'} ({vence:%H:%M})."
    if perdido:
        que = (f"el recordatorio de {item['nombre']}" if item["tipo"] == "recordatorio" and item["nombre"]
               else "tu recordatorio" if item["tipo"] == "recordatorio"
               else f"la alarma de {item['nombre']}" if item["tipo"] == "alarma" and item["nombre"]
               else "tu alarma" if item["tipo"] == "alarma"
               else f"el temporizador de {item['nombre']}" if item["nombre"]
               else f"el temporizador de {decir_duracion(item['duracion'])}")
        return (f"⏰ {que[0].upper() + que[1:]} venció a las {vence:%H:%M}, mientras el "
                f"bot estaba detenido. No sonó.")
    if item["tipo"] == "alarma":
        que = f" de {item['nombre']}" if item["nombre"] else ""
        return f"⏰ Sonó tu alarma{que} ({vence:%H:%M})."
    if item["nombre"]:
        return f"⏰ Terminó el temporizador de {item['nombre']} ({decir_duracion(item['duracion'])})."
    return f"⏰ Terminó tu temporizador de {decir_duracion(item['duracion'])}."


def resumen(perfil: str, ahora: datetime | None = None) -> str:
    """Todos los activos del perfil, escritos, para /temporizadores."""
    ahora = ahora or datetime.now().astimezone()
    vivos = activos(perfil, ahora)
    if not vivos:
        return "No tienes temporizadores ni alarmas activos."
    ahora_e = _epoch(ahora)
    lineas = []
    for i in vivos:
        nombre = f" · {i['nombre']}" if i["nombre"] else ""
        if i.get("recurrencia"):
            lineas.append(linea_orden(i, ahora))
        elif i["tipo"] == "recordatorio":
            cuando = decir_hora(datetime.fromtimestamp(i["vence"]).astimezone(), ahora)
            lineas.append(f"🔔 recordatorio{nombre} — en pausa; no sonará" if i["estado"] == "pausado"
                          else f"🔔 recordatorio{nombre} — {cuando}")
        elif i["tipo"] == "alarma":
            cuando = decir_hora(datetime.fromtimestamp(i["vence"]).astimezone(), ahora)
            lineas.append(f"⏰ alarma{nombre} — en pausa; no sonará" if i["estado"] == "pausado"
                          else f"⏰ alarma{nombre} — {cuando}")
        else:
            queda = i.get("restante", max(0, i["vence"] - ahora_e)) if i["estado"] == "pausado" \
                else i["vence"] - ahora_e
            prefijo = "en pausa; quedan " if i["estado"] == "pausado" else "quedan "
            lineas.append(f"⏲️ {decir_duracion(i['duracion'])}{nombre} — {prefijo}{decir_duracion(queda)}")
    return "\n".join(lineas)


@dataclass
class Respuesta:
    """Lo que `atender` le devuelve al bot: la frase, y lo que el bot tiene que
    ofrecer con botones (este módulo no sabe de Telegram)."""
    texto: str
    accion: str = ""
    # Orden recurrente dictada por voz: NO se guardó. Son los argumentos de
    # `crear`; el bot la guarda sólo cuando llega el ✅.
    propuesta: dict[str, Any] | None = None
    # Lo que se puede volver atrás durante una hora: ("crear"|"pausar"|"borrar", ítems).
    deshacer: tuple[str, list[dict[str, Any]]] | None = None
    # Con qué empieza el mensaje escrito (la frase hablada va sin él).
    icono: str = "⏲️"


def responder(texto: str, perfil: str, ahora: datetime | None = None,
              origen: str = "voz", sonando: bool | None = None) -> str | None:
    """Interpreta, ejecuta y devuelve la frase de respuesta. None si no aplica.

    Si devuelve texto, la frase era de temporizadores y ya se ejecutó; si
    devuelve None, sigue al clasificador. El bot usa `atender`, que además dice
    qué botones ofrecer.
    """
    r = atender(texto, perfil, ahora, origen, sonando)
    return r.texto if r else None


_FALTA = {
    "duracion": "¿De cuánto tiempo el temporizador?",
    "recurrencia": "Todavía no entiendo esa repetición. Prueba «todos los días», «de lunes a "
                   "viernes», «los sábados» o «cada 2 horas».",
    "intervalo": "El intervalo mínimo es de 1 hora.",
    "texto": "¿Qué te recuerdo?",
}


def atender(texto: str, perfil: str, ahora: datetime | None = None,
            origen: str = "voz", sonando: bool | None = None) -> Respuesta | None:
    """Interpreta y ejecuta. None si la frase no es de temporizadores ni órdenes."""
    ahora = ahora or datetime.now().astimezone()
    if sonando is None:
        sonando = hay_sonando()
    it = interpretar(texto, ahora, sonando=sonando)
    if it is None:
        return None
    if it.tipo == "clima":
        r = _atender_clima(it, perfil, ahora, origen)
        r.icono = "🌦️"
        return r
    if it.accion == "crear" and it.extra.get("recurrencia"):
        return _atender_recurrente(it, perfil, ahora, origen)
    if it.accion == "ordenes":
        return Respuesta(resumen_ordenes(perfil, ahora), "ordenes")
    if it.accion in ("pausar", "reanudar"):
        hacer = pausar if it.accion == "pausar" else reanudar
        hechos, dudosos = hacer(perfil, it.nombre, it.tipo, todos=it.todos, ahora=ahora)
        if dudosos:
            return Respuesta(f"Tienes {len(dudosos)}: " + "; ".join(_rotulo(i) for i in dudosos[:4])
                             + (". ¿Cuál pauso?" if it.accion == "pausar" else ". ¿Cuál reanudo?"), it.accion)
        if not hechos:
            if it.extra.get("tentativo"):
                return None
            return Respuesta("No encontré esa orden en pausa." if it.accion == "reanudar"
                             else "No encontré esa orden activa.", it.accion)
        if it.accion == "pausar":
            que = _cual(hechos[0]) if len(hechos) == 1 else f"{len(hechos)} órdenes"
            return Respuesta(f"Puse en pausa {que}. No sonará hasta que la reanudes.", "pausar",
                             deshacer=("pausar", hechos))
        if len(hechos) > 1:
            return Respuesta(f"Reanudé {len(hechos)} órdenes.", "reanudar")
        i = hechos[0]
        if i["estado"] == "vencida":
            return Respuesta(f"{_cual(i)[0].upper() + _cual(i)[1:]} ya venció; renuévala desde /ordenes.",
                             "reanudar")
        return Respuesta(f"Reanudé {_cual(i)}. La próxima es {decir_proxima(i, ahora)}.", "reanudar")
    if it.accion == "cancelar":
        hechos, dudosos = cancelar(perfil, it.nombre, it.todos, it.tipo, ahora,
                                   solo_ordenes=bool(it.extra.get("solo_ordenes")))
        if dudosos:
            return Respuesta(f"Tienes {len(dudosos)}: " + ", ".join(_rotulo(i) for i in dudosos[:4])
                             + ". ¿Cuál cancelo?", "cancelar")
        if not hechos:
            if it.extra.get("tentativo"):
                return None
            return Respuesta("No encontré ese temporizador." if it.nombre
                             else "No tienes nada que cancelar.", "cancelar")
        borrados = [i for i in hechos if i["estado"] == "borrado"]
        if len(hechos) == 1:
            frase = f"Borré {_cual(hechos[0])}." if borrados else f"Cancelé {_cual(hechos[0])}."
        else:
            frase = f"Cancelé {len(hechos)}."
        return Respuesta(frase, "cancelar", deshacer=("borrar", [dict(i) for i in borrados]) if borrados else None)
    frase = _responder_simple(it, perfil, ahora, origen)
    return Respuesta(frase, it.accion) if frase is not None else None


CLIMA_EJEMPLO = ("Escríbeme, por ejemplo: «mándame el clima de lunes a viernes a las 7:30» o "
                 "«avísame el clima los fines de semana a las 10».")


def _atender_clima(it: Intencion, perfil: str, ahora: datetime, origen: str) -> Respuesta:
    """Las frases del aviso del clima. Pausar, reanudar y borrar van sobre TODOS los
    del perfil: «pausa el aviso del clima» con «L–V» y «S–D» no pregunta cuál."""
    if it.accion == "ordenes":
        mios = climas(perfil)
        if not mios:
            return Respuesta("No tienes avisos del clima programados.", "ordenes_clima")
        return Respuesta("Avisos del clima:\n" + "\n".join(linea_orden(i, ahora) for i in mios), "ordenes_clima")
    if it.accion == "crear":
        if it.extra.get("falta") == "hora":
            return Respuesta("¿A qué hora te mando el clima? " + CLIMA_EJEMPLO, "crear")
        return _atender_recurrente(it, perfil, ahora, origen)
    if it.accion in ("pausar", "reanudar"):
        hechos, _ = (pausar if it.accion == "pausar" else reanudar)(perfil, tipo="clima", todos=True, ahora=ahora)
        if not hechos:
            return Respuesta("No tienes avisos del clima en pausa." if it.accion == "reanudar"
                             else "No tienes avisos del clima activos.", it.accion)
        que = _cual(hechos[0]) if len(hechos) == 1 else f"los {len(hechos)} avisos del clima"
        if it.accion == "pausar":
            return Respuesta(f"Puse en pausa {que}. No te llegará hasta que lo reanudes.", "pausar",
                             deshacer=("pausar", hechos))
        prox = min(hechos, key=lambda i: i["vence"])
        return Respuesta(f"Reanudé {que}. El próximo es {decir_proxima(prox, ahora)} a las "
                         f"{_local(datetime.fromtimestamp(prox['vence'], timezone.utc)):%H:%M}.", "reanudar")
    hechos, _ = cancelar(perfil, todos=True, tipo="clima", ahora=ahora)
    if not hechos:
        return Respuesta("No tienes avisos del clima.", "cancelar")
    que = _cual(hechos[0]) if len(hechos) == 1 else f"los {len(hechos)} avisos del clima"
    return Respuesta(f"Borré {que}.", "cancelar", deshacer=("borrar", [dict(i) for i in hechos]))


def _atender_recurrente(it: Intencion, perfil: str, ahora: datetime, origen: str) -> Respuesta:
    """Crear una orden recurrente. La respuesta SIEMPRE dice qué se entendió.

    D10, nivel 1: por voz no se guarda nada (el wake word no autentica) y la
    propuesta vuelve al bot para el ✅; escrita en Telegram el remitente ya está
    autenticado, se guarda, y el bot ofrece deshacer.
    """
    datos = {"perfil": perfil, "tipo": it.tipo, "nombre": it.nombre, "origen": origen,
             "recurrencia": it.extra["recurrencia"], "hasta_epoch": it.extra.get("hasta_epoch")}
    try:
        if origen == "voz":
            datos["recurrencia"], vence = _primera(datos["recurrencia"], datos["hasta_epoch"], ahora)
            with _Sesion(escribe=False) as s:
                _cupo(s.items, perfil, True)
            item = dict(datos, vence=_epoch(vence))
            return Respuesta(f"{describir(item)}. La próxima sería {decir_proxima(item, ahora)}. "
                             "Para dejarla fija, confírmala en Telegram.", "crear", propuesta=datos)
        item = crear(perfil, it.tipo, None, it.nombre, origen, ahora,
                     recurrencia=datos["recurrencia"], hasta_epoch=datos["hasta_epoch"])
    except ValueError as e:
        return Respuesta(str(e), "crear")
    return Respuesta(f"{describir(item)}. La próxima es {decir_proxima(item, ahora)}.", "crear",
                     deshacer=("crear", [item]))


def confirmar(propuesta: dict[str, Any], ahora: datetime | None = None) -> dict[str, Any]:
    """Guarda la propuesta que `atender` devolvió por voz. La llama el ✅."""
    return crear(propuesta["perfil"], propuesta["tipo"], None, propuesta.get("nombre", ""),
                 propuesta.get("origen", "voz"), ahora, recurrencia=propuesta["recurrencia"],
                 hasta_epoch=propuesta.get("hasta_epoch"))


def _responder_simple(it: Intencion, perfil: str, ahora: datetime, origen: str) -> str | None:
    """Lo de una sola vez: parar, crear, consultar y agregar, como siempre."""
    if it.accion == "parar":
        parados = parar(None, ahora=ahora)
        return "Listo." if parados else None

    if it.accion == "crear":
        if it.extra.get("falta") == "hora":
            return "¿A qué hora te lo recuerdo?" if it.tipo == "recordatorio" else "¿A qué hora pongo la alarma?"
        if it.extra.get("falta"):
            return _FALTA[it.extra["falta"]]
        try:
            if it.tipo == "recordatorio":
                item = crear(perfil, "recordatorio", it.vence, it.nombre, origen, ahora)
                que = f" «{it.nombre}»" if it.nombre else ""
                return f"Recordatorio{que} para {decir_hora(it.vence, ahora)}."
            if it.tipo == "alarma":
                item = crear(perfil, "alarma", it.vence, it.nombre, origen, ahora)
                frase = f"Alarma para {decir_hora(it.vence, ahora)}."
                return frase
            vence = ahora + timedelta(seconds=it.segundos)
            item = crear(perfil, "temporizador", vence, it.nombre, origen, ahora)
        except ValueError as e:
            return str(e)
        dur = decir_duracion(item["duracion"])
        return f"Listo, {dur} para {it.nombre}." if it.nombre else \
            f"Temporizador de {dur}, empezando ahora."

    if it.accion == "consultar":
        vivos = [i for i in activos(perfil, ahora) if not it.tipo or i["tipo"] == it.tipo]
        vivos = _elegir(vivos, it.nombre) if it.nombre else vivos
        if not vivos and it.extra.get("tentativo"):
            return None
        if not vivos:
            return ("No tienes alarmas." if it.tipo == "alarma"
                    else "No tienes recordatorios." if it.tipo == "recordatorio"
                    else "No tienes temporizadores activos.")
        ahora_e = _epoch(ahora)
        def una(i: dict[str, Any]) -> str:
            if i["tipo"] in ("alarma", "recordatorio"):
                return f"{_cual(i)} está en pausa y no sonará" if i["estado"] == "pausado" else \
                    f"{_cual(i)} suena {decir_hora(datetime.fromtimestamp(i['vence']).astimezone(), ahora)}"
            cual = _cual(i)
            cual = "al" + cual[2:] if cual.startswith("el ") else "a " + cual
            queda = i.get("restante", max(0, i["vence"] - ahora_e)) if i["estado"] == "pausado" \
                else i["vence"] - ahora_e
            return f"{cual} está en pausa y le quedan {decir_duracion(queda)}" if i["estado"] == "pausado" \
                else f"{cual} le quedan {decir_duracion(queda)}"
        if len(vivos) == 1:
            f = una(vivos[0])
            return f[0].upper() + f[1:] + "."
        return f"Tienes {len(vivos)}: " + "; ".join(una(i) for i in vivos[:4]) + "."

    if it.accion == "agregar":
        try:
            item, dudosos = agregar(perfil, it.segundos, it.nombre, ahora)
        except ValueError as e:
            return str(e)
        if item is None:
            if not dudosos:
                return "No tienes un temporizador al que sumarle."
            return "¿A cuál? Tienes " + ", ".join(i["nombre"] or decir_duracion(i["duracion"]) for i in dudosos[:4]) + "."
        return f"Sumé {decir_duracion(it.segundos)}; quedan {decir_duracion(item['vence'] - _epoch(ahora))}."
    return None


# --- Lo que usa Cockpit ⏰ (`programado-accion.py`), sin root -----------------

ACCIONES_COCKPIT = ("pausar", "reanudar", "correr")


def accion_cockpit(accion: str, ident: str, ahora: datetime | None = None) -> dict[str, Any]:
    """Pausa, reanuda o hace vencer ahora un ítem por su id. ValueError si no se puede.

    Vive acá, y no en un script aparte, para que llegue a la Pi con este mismo
    archivo: `temporizador-accion.py` nunca tuvo entrada de despliegue y los
    botones de Cockpit llamaban a una ruta que no existía (revisión 35r2).

    Una alarma o un recordatorio de una sola vez no se pausa ni se reanuda: le
    correría la hora. Una orden recurrente sí: en pausa no suena y al reanudar
    vuelve a su próxima ocurrencia, no a `ahora + restante`. «Correr» lo deja
    vencer en este instante y el hilo normal del bot lo recoge.
    """
    if accion not in ACCIONES_COCKPIT or not ident.isalnum() or len(ident) > 32:
        raise ValueError("accion o id invalido")
    ahora = ahora or datetime.now().astimezone()
    ahora_e = _epoch(ahora)
    with _Sesion(escribe=True) as s:
        item = next((i for i in s.items if i.get("id") == ident
                     and i.get("estado") in {"activo", "pausado"}), None)
        if item is None:
            raise ValueError("temporizador no reportado o no accionable")
        recurrente = bool(item.get("recurrencia"))
        if accion == "pausar":
            if item["tipo"] == "alarma" and not recurrente:
                raise ValueError("las alarmas no se pueden pausar; cancélala o córrela ahora")
            if item["estado"] != "activo":
                raise ValueError("el temporizador no está activo")
            item["restante"] = max(0, int(item["vence"]) - ahora_e)
            item["estado"] = "pausado"
            if recurrente:
                item["pausado_en"] = ahora_e        # la misma forma que deja `pausar`
        elif accion == "reanudar":
            if item["tipo"] == "alarma" and not recurrente:
                raise ValueError("las alarmas no se pueden reanudar")
            if item["estado"] != "pausado":
                raise ValueError("el temporizador no está pausado")
            # Cada tope cuenta sólo los de su clase: 10 temporizadores no traban una orden recurrente.
            en_marcha = sum(i.get("perfil") == item["perfil"] and i.get("estado") in ("activo", "sonando")
                            and bool(i.get("recurrencia")) == recurrente for i in s.items)
            if recurrente and en_marcha >= MAX_RECURRENTES:
                raise ValueError(f"Ya tienes {MAX_RECURRENTES} órdenes recurrentes; borra alguna primero.")
            if not recurrente and en_marcha >= MAX_ACTIVOS:
                raise ValueError(f"Ya tienes {MAX_ACTIVOS} activos; cancela alguno primero.")
            if recurrente:
                _despertar(item, ahora)             # a la próxima ocurrencia, o `vencida` si pasó su término
            else:
                item["vence"] = ahora_e + max(0, int(item.get("restante", 0)))
                item["estado"] = "activo"
        else:
            item["vence"], item["estado"] = ahora_e, "activo"
        return {"ok": True, "estado": item["estado"]}


def main(argv: list[str]) -> int:
    """`temporizadores.py <pausar|reanudar|correr> <id>`: una línea de JSON, como espera Cockpit."""
    try:
        if len(argv) != 3:
            raise ValueError("uso: temporizadores.py <pausar|reanudar|correr> <id>")
        resultado = accion_cockpit(argv[1], argv[2])
    except (ValueError, OSError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
