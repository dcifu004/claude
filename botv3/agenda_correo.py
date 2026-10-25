"""Ruta `google` de botv3: agenda (Calendar) y correo (Gmail), 24-09-2026.

El bot NO tiene el token de Google: habla con `google-puente` por un socket unix
(pi/google_puente.py). Este modulo solo interpreta el pedido, valida, formatea y
llama al puente. Crear un evento o un borrador nunca ocurre aca directo: se arma
una PROPUESTA que el bot muestra con botones, y se ejecuta al tocar "Crear".

Que viaja a Groq y que no: a Groq va SOLO la frase del pedido, para convertirla en
una accion estructurada. El contenido de correos y eventos que devuelve el puente
se formatea aca, sin modelo, y nunca vuelve a Groq ni al contexto conversacional
(`google` no esta en RUTAS_SIN_VAULT).
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time as dtime, timedelta
import http.client
import json
import re
import socket
import unicodedata
from typing import Any, Callable
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")
SOCKET = "/run/google-puente.sock"
DURACION_DEFECTO = timedelta(hours=1)
ACCIONES = {"agenda", "buscar_correo", "crear_evento", "crear_borrador", "preguntar", "otra"}
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


class GoogleNoDisponible(RuntimeError):
    pass


# --- Interpretacion ---------------------------------------------------------

def prompt_sistema(ahora: datetime) -> str:
    return f"""Conviertes un pedido de agenda o correo en JSON. Responde SOLO un objeto JSON.
Ahora es {DIAS[ahora.weekday()]} {ahora:%Y-%m-%d %H:%M} en Santiago de Chile.
Fechas y horas SIEMPRE locales, sin zona, formato "YYYY-MM-DDTHH:MM" (o "YYYY-MM-DD" si es todo el día).

Campo "accion", uno de:
- "agenda": consultar eventos. Campos "desde" y "hasta". Si no dice rango: desde hoy 00:00, hasta 7 días después.
- "buscar_correo": buscar correos. Campo "q" con sintaxis de búsqueda de Gmail (from:, subject:, is:unread, newer_than:7d, etc.).
- "crear_evento": campos "titulo" ("" si pide sin título), "inicio", "fin" (si no dice duración, omítelo),
  "todo_el_dia" (true/false), "lugar", "descripcion".
- "crear_borrador": campos "para" (dirección de correo SOLO si aparece literal en el pedido; si no, ""),
  "asunto", "cuerpo" (redáctalo en español de Chile, breve y cordial, firmado "Diego").
- "preguntar": falta un dato imprescindible (por ejemplo la hora de un evento que no es de todo el día).
  Campo "pregunta" con lo que hay que preguntarle a Diego.
- "otra": el pedido no es de agenda ni de correo.
Nunca inventes datos que el pedido no trae, salvo el cuerpo del borrador."""


def interpretar(pedido: str, llm: Callable[[str, str], str],
                ahora: datetime | None = None) -> dict[str, Any]:
    """Pide al modelo la accion y la VALIDA aca; el modelo propone, Python decide."""
    ahora = ahora or datetime.now(TZ)
    crudo = llm(prompt_sistema(ahora), pedido)
    try:
        datos = json.loads(crudo)
    except (TypeError, json.JSONDecodeError):
        return {"accion": "preguntar", "pregunta": "No entendí el pedido. ¿Me lo repites con fecha y hora?"}
    if not isinstance(datos, dict) or datos.get("accion") not in ACCIONES:
        return {"accion": "otra"}
    return validar(datos, ahora)


def _fecha_hora(valor: Any) -> datetime | None:
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(str(valor))
    except ValueError:
        return None
    return d.replace(tzinfo=TZ) if d.tzinfo is None else d.astimezone(TZ)


def validar(d: dict[str, Any], ahora: datetime) -> dict[str, Any]:
    accion = d["accion"]
    if accion == "agenda":
        hoy = datetime.combine(ahora.date(), dtime(0), TZ)
        desde = _fecha_hora(d.get("desde")) or hoy
        hasta = _fecha_hora(d.get("hasta")) or desde + timedelta(days=7)
        if hasta <= desde:
            hasta = desde + timedelta(days=1)
        return {"accion": accion, "desde": desde, "hasta": hasta}
    if accion == "buscar_correo":
        return {"accion": accion, "q": str(d.get("q", "")).strip()[:300]}
    if accion == "crear_evento":
        todo_el_dia = bool(d.get("todo_el_dia"))
        inicio = _fecha_hora(d.get("inicio"))
        if inicio is None:
            return {"accion": "preguntar", "pregunta": "¿Para qué día y hora es el evento?"}
        fin = _fecha_hora(d.get("fin"))
        if todo_el_dia:
            inicio = datetime.combine(inicio.date(), dtime(0), TZ)
            if fin is None or fin.date() <= inicio.date():
                fin = inicio + timedelta(days=1)
        elif fin is None or fin <= inicio:
            fin = inicio + DURACION_DEFECTO
        return {"accion": accion, "titulo": str(d.get("titulo", "")).strip()[:200],
                "inicio": inicio, "fin": fin, "todo_el_dia": todo_el_dia,
                "lugar": str(d.get("lugar", "") or "").strip()[:200],
                "descripcion": str(d.get("descripcion", "") or "").strip()[:1000]}
    if accion == "crear_borrador":
        para = str(d.get("para", "") or "").strip()
        if para and ("@" not in para or " " in para):
            para = ""  # un nombre no es una direccion: no se adivina
        return {"accion": accion, "para": para[:200],
                "asunto": str(d.get("asunto", "") or "").strip()[:200],
                "cuerpo": str(d.get("cuerpo", "") or "").strip()[:5000]}
    if accion == "preguntar":
        return {"accion": accion, "pregunta": str(d.get("pregunta") or "¿Me das más detalles?")[:300]}
    return {"accion": "otra"}


# --- Formato ----------------------------------------------------------------

def _dia(d: datetime | date) -> str:
    return f"{DIAS[d.weekday()]} {d:%d-%m}"


def texto_propuesta(a: dict[str, Any]) -> str:
    if a["accion"] == "crear_evento":
        titulo = a["titulo"] or "Sin título"
        if a["todo_el_dia"]:
            cuando = f"{_dia(a['inicio'])}-{a['inicio']:%Y} · todo el día"
        else:
            cuando = f"{_dia(a['inicio'])}-{a['inicio']:%Y} · {a['inicio']:%H:%M}–{a['fin']:%H:%M}"
            if a["fin"].date() != a["inicio"].date():
                cuando = f"{_dia(a['inicio'])} {a['inicio']:%H:%M} → {_dia(a['fin'])} {a['fin']:%H:%M}"
        lineas = ["📅 Crear evento", f"«{titulo}»", cuando]
        if a["lugar"]:
            lineas.append(f"📍 {a['lugar']}")
        if a["descripcion"]:
            lineas.append(a["descripcion"])
        return "\n".join(lineas + ["", "¿Lo creo en tu calendario?"])
    para = a["para"] or "(sin destinatario: lo completas tú)"
    return (f"✉️ Borrador de correo\nPara: {para}\nAsunto: {a['asunto'] or '(sin asunto)'}\n\n"
            f"{a['cuerpo']}\n\n¿Lo dejo en Borradores? No se envía.")


def formatear_agenda(a: dict[str, Any], eventos: list[dict[str, Any]], titulo: str = "") -> str:
    rango = f"{_dia(a['desde'])} → {_dia(a['hasta'] - timedelta(minutes=1))}"
    if titulo:
        # Los botones de /google (encargo 66) dicen qué día es; el rango sobra.
        if not eventos:
            return f"📅 {titulo}: sin eventos."
        lineas = [f"📅 {titulo}:"]
    elif not eventos:
        return f"📅 Sin eventos entre {rango}."
    else:
        lineas = [f"📅 Agenda {rango}:"]
    for e in eventos:
        ini = e.get("inicio", "")
        if "T" in ini:
            i, f = datetime.fromisoformat(ini).astimezone(TZ), datetime.fromisoformat(e["fin"]).astimezone(TZ)
            cuando = f"{_dia(i)} {i:%H:%M}–{f:%H:%M}"
        else:
            cuando = f"{_dia(date.fromisoformat(ini[:10]))} (todo el día)"
        linea = f"• {cuando}  {e.get('titulo') or 'Sin título'}"
        if e.get("lugar"):
            linea += f" · 📍 {e['lugar']}"
        lineas.append(linea)
    return "\n".join(lineas)


def formatear_correos(a: dict[str, Any], correos: list[dict[str, Any]]) -> str:
    busqueda = f" ({a['q']})" if a["q"] else ""
    if not correos:
        return f"📬 No encontré correos{busqueda}."
    lineas = [f"📬 {len(correos)} correo(s){busqueda}:"]
    for c in correos:
        de = c.get("de", "").split("<")[0].strip().strip('"') or c.get("de", "")
        marca = "🔵 " if c.get("no_leido") else ""
        lineas.append(f"• {marca}{de} — {c.get('asunto') or '(sin asunto)'}")
        if c.get("extracto"):
            lineas.append(f"   {c['extracto'][:140]}")
    return "\n".join(lineas)


# --- Puente -----------------------------------------------------------------

class _ConexionUnix(http.client.HTTPConnection):
    def __init__(self, ruta: str, timeout: float):
        super().__init__("google-puente", timeout=timeout)
        self._ruta = ruta

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._ruta)


def puente(operacion: str, datos: dict[str, Any], ruta: str = SOCKET,
           timeout: float = 40) -> dict[str, Any]:
    try:
        c = _ConexionUnix(ruta, timeout)
        c.request("POST", f"/{operacion}", json.dumps(datos, default=str),
                  {"Content-Type": "application/json"})
        r = json.loads(c.getresponse().read())
    except (OSError, ValueError) as exc:
        raise GoogleNoDisponible(f"el puente a Google no responde ({exc})") from exc
    if not r.get("ok"):
        raise RuntimeError(r.get("error", "error desconocido del puente"))
    return r


def carga_puente(a: dict[str, Any]) -> dict[str, Any]:
    """Traduce una accion validada al JSON que espera el puente."""
    if a["accion"] == "agenda":
        return {"desde": a["desde"].isoformat(), "hasta": a["hasta"].isoformat(), "max": 15}
    if a["accion"] == "buscar_correo":
        return {"q": a["q"], "max": 8}
    if a["accion"] == "crear_evento":
        return {"titulo": a["titulo"], "inicio": a["inicio"].isoformat(),
                "fin": a["fin"].isoformat(), "todo_el_dia": a["todo_el_dia"],
                "lugar": a["lugar"], "descripcion": a["descripcion"]}
    return {"para": a["para"], "asunto": a["asunto"], "cuerpo": a["cuerpo"]}


# --- Consultas sin modelo (menú de /google, encargo 66) -----------------------
#
# Las preguntas de todos los días no pasan por `interpretar`: el rango lo calcula
# Python y el texto sale de los mismos formateadores. Los rangos quedan sueltos
# porque el encargo 68 los reusa para «qué tengo hoy» dicho o escrito. Todos son
# [desde, hasta) como los de `validar`: «hasta las 23:59» es hasta las 00:00.

def ahora_local() -> datetime:
    return datetime.now(TZ)


def _medianoche(d: date) -> datetime:
    return datetime.combine(d, dtime(0), TZ)


def rango_hoy(ahora: datetime) -> tuple[datetime, datetime]:
    return ahora, _medianoche(ahora.date() + timedelta(days=1))


def rango_manana(ahora: datetime) -> tuple[datetime, datetime]:
    manana = ahora.date() + timedelta(days=1)
    return _medianoche(manana), _medianoche(manana + timedelta(days=1))


def rango_semana(ahora: datetime) -> tuple[datetime, datetime]:
    return ahora, ahora + timedelta(days=7)


def _inicio_evento(e: dict[str, Any]) -> datetime | None:
    ini = str(e.get("inicio") or "")
    try:
        if "T" in ini:
            return datetime.fromisoformat(ini).astimezone(TZ)
        return _medianoche(date.fromisoformat(ini[:10]))
    except ValueError:
        return None


def proximo_evento(eventos: list[dict[str, Any]], ahora: datetime) -> dict[str, Any] | None:
    """El primero que EMPIEZA después de ahora: el que va en curso (Calendar lo
    devuelve porque termina después) y el de todo el día de hoy no cuentan."""
    futuros = [(i, n, e) for n, e in enumerate(eventos)
               if (i := _inicio_evento(e)) is not None and i > ahora]
    return min(futuros, key=lambda t: (t[0], t[1]))[2] if futuros else None


CONSULTAS_LOCALES = ("hoy", "manana", "semana", "proximo", "noleidos")
Q_NO_LEIDOS = "is:unread newer_than:2d"
MAX_PUENTE = 20   # MAX_RESULTADOS de google_puente: más no devuelve por pedido
PAGINAS = 5       # hasta 100 eventos por pregunta; más allá se dice que no se vio todo
SIN_PROXIMO = "No tienes nada en los próximos 7 días."
PROXIMO_TAPADO = f"Tienes {MAX_PUENTE} o más eventos en curso y no alcanzo a ver el próximo."


def _fin_evento(e: dict[str, Any]) -> datetime | None:
    fin = str(e.get("fin") or "")
    try:
        if "T" in fin:
            return datetime.fromisoformat(fin).astimezone(TZ)
        return _medianoche(date.fromisoformat(fin[:10]))
    except ValueError:
        return None


def _clave(e: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(e.get(k) or "") for k in ("titulo", "inicio", "fin", "lugar"))


def eventos_recorridos(desde: datetime, hasta: datetime,
                       basta: Callable[[list[dict[str, Any]]], bool] | None = None,
                       ) -> tuple[list[dict[str, Any]], datetime | None]:
    """Los eventos de [desde, hasta) aunque sean más de los que el puente da de una vez.

    El puente devuelve a lo más MAX_PUENTE, ordenados por inicio, y Calendar incluye
    los que van en curso (los que terminan después de `desde`). Si la página viene
    llena, se pide de nuevo desde el inicio de su último evento: lo ya visto que sigue
    en curso vuelve a llegar y se descuenta. Devuelve (eventos, visto): `visto` es None
    si se vio la ventana entera; si no, todo lo que empieza antes de `visto` está en la
    lista, y lo de después puede faltar. Eso pasa cuando MAX_PUENTE o más eventos ya
    empezaron (Calendar no deja ver detrás de ellos), al llegar a PAGINAS, o cuando
    `basta(eventos)` dice que ya se tiene la respuesta.
    """
    eventos: list[dict[str, Any]] = []
    t, repetidos = desde, Counter()
    for _ in range(PAGINAS):
        pagina = puente("agenda", {"desde": t.isoformat(), "hasta": hasta.isoformat(),
                                   "max": MAX_PUENTE})["eventos"]
        for e in pagina:
            if repetidos[_clave(e)]:
                repetidos[_clave(e)] -= 1
            else:
                eventos.append(e)
        if len(pagina) < MAX_PUENTE:
            return eventos, None
        ultimo = _inicio_evento(pagina[-1])
        if ultimo is None or ultimo <= t or (basta and basta(eventos)):
            return eventos, max(ultimo or t, t)
        repetidos = Counter(_clave(e) for e in eventos if (f := _fin_evento(e)) and f > ultimo)
        t = ultimo
    return eventos, t


def _buscar_proximo(ahora: datetime) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
    """El ⏭️ Próximo del menú y «cuál es mi próxima reunión» (68): una sola búsqueda.

    Devuelve (acción, evento, completo). Sin evento y con `completo` en False, no se
    sabe si hay uno: lo tapan los que van en curso. Eso no es «no tienes nada».
    """
    desde, hasta = rango_semana(ahora)
    a = {"accion": "agenda", "desde": desde, "hasta": hasta}
    eventos, visto = eventos_recorridos(desde, hasta, lambda ev: proximo_evento(ev, ahora) is not None)
    e = proximo_evento(eventos, ahora)
    return a, e, e is not None or visto is None


def consulta_local(opcion: str, ahora: datetime | None = None) -> str:
    """El texto de un botón de consulta de /google. Levanta lo mismo que `puente`."""
    if opcion not in CONSULTAS_LOCALES:
        raise ValueError(f"consulta desconocida: {opcion!r}")
    if opcion == "noleidos":
        a = {"accion": "buscar_correo", "q": Q_NO_LEIDOS}
        return formatear_correos(a, puente("buscar_correo", {"q": a["q"], "max": 10})["correos"])
    ahora = ahora or ahora_local()
    if opcion == "proximo":
        a, e, completo = _buscar_proximo(ahora)
        if e:
            return formatear_agenda(a, [e], "Próximo evento")
        return f"📅 {SIN_PROXIMO if completo else PROXIMO_TAPADO}"
    rango = {"hoy": rango_hoy, "manana": rango_manana}.get(opcion, rango_semana)(ahora)
    a = {"accion": "agenda", "desde": rango[0], "hasta": rango[1]}
    eventos = puente("agenda", carga_puente(a))["eventos"]
    titulo = {"hoy": f"Hoy, {_dia(rango[0])}", "manana": f"Mañana, {_dia(rango[0])}",
              "semana": "Próximos 7 días"}[opcion]
    return formatear_agenda(a, eventos, titulo)


# --- Frases sin modelo, escritas o dictadas (encargo 68) ----------------------
#
# «qué tengo mañana», «cuál es mi próxima reunión», «me escribió Juan»: lo frecuente
# se reconoce con regex y se consulta directo, sin `interpretar`. Lo que no calza da
# None y sigue el camino de siempre (n8n → ruta google → LLM).
#
# Se trabaja sobre una versión en minúsculas y sin tildes del MISMO largo que la
# frase (una letra por letra), así el nombre del remitente se corta del original con
# sus mayúsculas. Whisper escribe «¿», vocativo y signos: se cambian por espacios.
#
# Choques que se evitan a propósito: «qué tengo que comprar» y «tengo algo en la
# lista» (compras) no traen un día al final; «mañana a las 7» (temporizadores) no
# empieza con una pregunta de agenda; «agenda» suelto es crear, salvo «mi agenda de
# hoy» o «agenda para mañana», que terminan en un día.

DIAS_DICHOS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_DIA_SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4,
               "sabado": 5, "domingo": 6}
MAX_AGENDA = 15            # lo de siempre en carga_puente
MAX_CORREOS = 10           # como ✉️ No leídos
DIAS_FILTRO = 14
TITULO_DICHO = 60


def _plano(texto: str) -> str:
    salida = []
    for c in texto:
        base = unicodedata.normalize("NFD", c)[0].lower()
        salida.append(base if len(base) == 1 else c)
    return "".join(salida)


_ANTES = (r"^\s*(?:(?:hola|hey|oye|ok|buenas)\s+)?(?:(?:jaime|pilar)\s+)?(?:por\s+favor\s+)?"
          r"(?:(?:dime|me\s+dices|me\s+puedes\s+decir|sabes)\s+)?")
_DESPUES = r"(?:\s+(?:jaime|pilar))?\s*$"
_DIA = (r"(?:el\s+dia\s+de\s+)?(?P<hoy>hoy)|(?P<pasado>pasado\s+manana)|(?P<manana>manana)"
        r"|(?:el\s+|este\s+)?(?P<prox>proximo\s+)?(?P<dsem>lunes|martes|miercoles|jueves|viernes|sabado|domingo)"
        r"|(?P<semana>(?:esta|la|en\s+la)\s+semana)")
_EN_AGENDA = r"(?:\s+en\s+(?:la|mi|el)\s+(?:agenda|calendario))?"
_AGENDA_RE = [re.compile(_ANTES + p + _DESPUES) for p in (
    rf"q(?:ue)?\s+(?:tengo|hay)(?:\s+agendado)?{_EN_AGENDA}(?:\s+para)?\s+(?:{_DIA}){_EN_AGENDA}",
    rf"tengo\s+(?:algo(?:\s+agendado)?|alguna\s+reunion|reuniones|eventos?)(?:\s+para)?\s+(?:{_DIA})",
    rf"(?:(?:como\s+(?:esta|viene)|muestrame|ver|revisa|leeme|lee)\s+)?(?:(?:mi|la)\s+)?agenda"
    rf"(?:\s+(?:de|del|para))?\s+(?:{_DIA})",
)]
_PROXIMO_RE = [re.compile(_ANTES + p + _DESPUES) for p in (
    r"(?:cual|cuando|a\s+que\s+hora)\s+es\s+(?:mi|la)\s+(?:proxima|siguiente)"
    r"(?:\s+(?:reunion|cita|evento|actividad))?",
    r"q(?:ue)?\s+(?:viene|sigue|tengo)\s+(?:ahora|despues)",
    r"(?:mi\s+)?(?:proxima|siguiente)\s+(?:reunion|cita|evento)",
)]
_FILTRO_RE = [re.compile(_ANTES + p + _DESPUES) for p in (
    r"(?:a\s+que\s+hora|cuando)\s+(?:es|tengo)\s+(?:la|el|mi)\s+(?:reunion|cita|junta|llamada|evento)"
    r"\s+(?:con|de|del)\s+(?P<x>.+?)",
    r"(?:a\s+que\s+hora|cuando)\s+(?:es|tengo)\s+(?:la|el|mi|los|las)\s+(?P<x>.+?)",
)]
_CORREO = r"(?:correos?|mails?|e\s*mails?)"
_CORREO_DE_RE = [re.compile(_ANTES + p + _DESPUES) for p in (
    r"me\s+(?:escribio|escribieron|respondio|contesto)\s+(?P<x>.+?)",
    rf"(?:(?:tengo|hay)\s+)?(?:algun(?:os)?\s+)?{_CORREO}(?:\s+nuevos?)?\s+(?:de|del)\s+(?P<x>.+?)",
    rf"(?:me\s+)?(?:llego|llegaron)\s+(?:algun(?:os)?\s+)?{_CORREO}\s+(?:de|del)\s+(?P<x>.+?)",
)]
_CORREO_RE = [re.compile(_ANTES + p + _DESPUES) for p in (
    rf"(?:tengo|hay)\s+(?:algun(?:os)?\s+)?{_CORREO}(?:\s+(?:nuevos?|sin\s+leer))?",
    rf"(?:me\s+)?(?:llego|llegaron)\s+(?:algun(?:os)?\s+)?{_CORREO}(?:\s+nuevos?)?",
    rf"{_CORREO}\s+(?:nuevos?|sin\s+leer)",
    r"(?:revisa|mira)\s+(?:mi|el)\s+correo",
)]
# «agenda dentista el jueves a las 4», «anota en mi calendario…», «crea una reunión…».
_CREAR_RE = re.compile(_ANTES + (
    r"(?:agenda(?:me|r)?\s+(?!(?:de|del|mia)\b)"
    r"|(?:anota(?:me)?|pon(?:me)?|agrega(?:me)?)\s+(?:en|a)\s+(?:mi|el|la)\s+(?:calendario|agenda)\s+"
    r"|(?:crea|programa)(?:me|r)?\s+(?:una|un)\s+(?:reunion|evento|cita)\s+)\S"))


def _frase(texto: str) -> tuple[str, str]:
    """(original, plano) del mismo largo, sin signos que Whisper agrega."""
    original = re.sub(r"[¿¡?!,;:]", " ", str(texto or ""))
    original = re.sub(r"\.+(?=\s|$)", " ", original)  # el punto final; los de juan.perez@x.cl quedan
    return original, _plano(original)


def _dia_pedido(m: re.Match, ahora: datetime) -> tuple[str, datetime, datetime] | None:
    if m.group("hoy"):
        return ("hoy", *rango_hoy(ahora))
    if m.group("manana"):
        return ("manana", *rango_manana(ahora))
    if m.group("semana"):
        return ("semana", *rango_semana(ahora))
    if m.group("pasado"):
        d = ahora.date() + timedelta(days=2)
        return "pasado", _medianoche(d), _medianoche(d + timedelta(days=1))
    if m.group("dsem"):
        dias = (_DIA_SEMANA[m.group("dsem")] - ahora.weekday()) % 7
        if dias == 0 and m.group("prox"):
            dias = 7
        if dias == 0:  # «qué tengo el martes», dicho un martes: lo que queda de hoy
            return ("hoy", *rango_hoy(ahora))
        d = ahora.date() + timedelta(days=dias)
        return m.group("dsem"), _medianoche(d), _medianoche(d + timedelta(days=1))
    return None


def _comparable(texto: str) -> str:
    """Minúsculas, sin tildes ni signos: «Dra. Muñoz» y «dra munoz» son lo mismo."""
    return " ".join("".join(c if c.isalnum() else " " for c in _plano(texto)).split())


def remitente_limpio(x: str) -> str:
    """Sólo letras, números, espacio, `.`, `@` y `-`; sin operadores de Gmail (OR, AND, -x)."""
    x = "".join(c for c in x if c.isalnum() or c in " .@-")
    palabras = [p.strip(".-") for p in x.split()]
    palabras = [p for p in palabras if p and p.upper() not in {"OR", "AND"}]
    if palabras and palabras[0].lower() in {"el", "la", "los", "las"}:
        palabras = palabras[1:]
    return " ".join(palabras)[:60].strip()


def intencion_agenda(texto: str, ahora: datetime) -> dict[str, Any] | None:
    """La consulta de agenda o correo de una frase, o None si no es una de las frecuentes."""
    original, plano = _frase(texto)
    if len(plano) > 160:
        return None
    for p in _AGENDA_RE:
        if m := p.match(plano):
            cuando, desde, hasta = _dia_pedido(m, ahora)
            return {"accion": "agenda", "desde": desde, "hasta": hasta, "cuando": cuando}
    if any(p.match(plano) for p in _PROXIMO_RE):
        desde, hasta = rango_semana(ahora)
        return {"accion": "proximo", "desde": desde, "hasta": hasta}
    for p in _FILTRO_RE:
        if m := p.match(plano):
            filtro = re.sub(r"^(?:el|la|los|las)\s+", "", _comparable(m.group("x")))
            if not 2 <= len(filtro) <= 40:
                return None
            return {"accion": "agenda", "desde": ahora, "hasta": ahora + timedelta(days=DIAS_FILTRO),
                    "cuando": "filtro", "filtro": filtro}
    for p in _CORREO_DE_RE:
        if m := p.match(plano):
            de = remitente_limpio(original[m.start("x"):m.end("x")])
            if not de:
                return None
            if de.lower() in {"alguien", "algo"}:
                break
            # Entre comillas si son varias palabras: «from:juan perez» buscaría «perez» en todo el correo.
            q = f'from:"{de}"' if " " in de else f"from:{de}"
            return {"accion": "buscar_correo", "q": f"{q} newer_than:7d", "de": de}
    else:
        if not any(p.match(plano) for p in _CORREO_RE):
            return None
    return {"accion": "buscar_correo", "q": Q_NO_LEIDOS, "de": ""}


def pide_crear_evento(texto: str) -> bool:
    """«agenda dentista el jueves a las 4»: va a ruta_google y su ✅, como siempre."""
    return bool(_CREAR_RE.match(_frase(texto)[1]))


def _hora_dicha(i: datetime) -> str:
    h = str(i.hour) if i.minute == 0 else f"{i.hour}:{i.minute:02d}"
    return f"a la {h}" if i.hour == 1 else f"a las {h}"


def _dia_dicho(d: date, ahora: datetime) -> str:
    if d == ahora.date():
        return "hoy"
    if d == ahora.date() + timedelta(days=1):
        return "mañana"
    return f"el {DIAS_DICHOS[d.weekday()]} {d.day}"


def _cuando_dicho(e: dict[str, Any], ahora: datetime, con_dia: bool) -> str:
    inicio = _inicio_evento(e)
    if inicio is None:
        return ""
    hora = "todo el día" if "T" not in str(e.get("inicio") or "") else _hora_dicha(inicio)
    if con_dia:
        # Lo que va en curso empezó antes: se dice desde hoy, no «el lunes 19».
        hora = f"{_dia_dicho(max(inicio.date(), ahora.date()), ahora)} {hora}"
    return hora


def titulo_dicho(e: dict[str, Any]) -> str:
    """El título tal cual (es del calendario del usuario), en una línea y cortado."""
    return " ".join(str(e.get("titulo") or "").split())[:TITULO_DICHO].rstrip() or "sin título"


def _evento_dicho(e: dict[str, Any], ahora: datetime, con_dia: bool) -> str:
    return ", ".join(p for p in (_cuando_dicho(e, ahora, con_dia), titulo_dicho(e)) if p)


def consulta_intencion(i: dict[str, Any], ahora: datetime | None = None) -> tuple[str, str]:
    """(texto_chat, frase_hablada) de una intención de `intencion_agenda`.

    La frase NUNCA trae el lugar, la descripción, los otros eventos, ni el asunto o
    el remitente completo de un correo: eso queda en el chat. Levanta lo mismo que `puente`.
    """
    ahora = ahora or ahora_local()
    if i["accion"] == "buscar_correo":
        a = {"accion": "buscar_correo", "q": i["q"]}
        correos = puente("buscar_correo", {"q": i["q"], "max": MAX_CORREOS})["correos"]
        n = len(correos)
        cuantos = f"{n} o más" if n >= MAX_CORREOS else str(n)
        if i.get("de"):
            de = i["de"] if "@" in i["de"] else i["de"][:1].upper() + i["de"][1:]
            frase = f"Tienes {cuantos} de {de}." if n else f"No tienes correos de {de}."
        else:
            frase = (f"Tienes {cuantos} correo{'s' if n != 1 else ''} sin leer." if n
                     else "No tienes correos sin leer.")
        return formatear_correos(a, correos), frase
    if i["accion"] == "proximo":
        a, e, completo = _buscar_proximo(ahora)
        if not e:
            frase = SIN_PROXIMO if completo else PROXIMO_TAPADO
            return f"📅 {frase}", frase
        return formatear_agenda(a, [e], "Próximo evento"), f"Tu próxima es {_evento_dicho(e, ahora, True)}."
    a = {"accion": "agenda", "desde": i["desde"], "hasta": i["hasta"]}
    cuando = i.get("cuando", "")
    filtro = i.get("filtro", "")
    if filtro:
        # Se recorre la ventana entera: con el tope del puente, el evento buscado
        # puede venir después de los primeros 20 (hallazgo 1 de 68r1).
        todos, visto = eventos_recorridos(a["desde"], a["hasta"])
        eventos = [e for e in todos if filtro in _comparable(str(e.get("titulo") or ""))]
        texto = formatear_agenda(a, eventos, f"«{filtro}» en los próximos {DIAS_FILTRO} días")
        if visto is not None:
            texto += (f"\n⚠️ Sólo alcancé a revisar hasta el {_dia(visto)} {visto:%H:%M}: "
                      "después puede haber más.")
        if not eventos:
            if visto is not None:
                return texto, f"No encontré {filtro} en lo que alcancé a revisar. Te dejo el detalle en el chat."
            return texto, f"No encontré {filtro} en los próximos {DIAS_FILTRO} días."
        return texto, f"Es {_evento_dicho(eventos[0], ahora, True)}."
    maximo = MAX_AGENDA
    eventos = puente("agenda", {"desde": a["desde"].isoformat(), "hasta": a["hasta"].isoformat(),
                                "max": maximo})["eventos"]
    d = a["desde"]
    etiqueta, titulo = {
        "hoy": ("Hoy", f"Hoy, {_dia(d)}"),
        "manana": ("Mañana", f"Mañana, {_dia(d)}"),
        "pasado": ("Pasado mañana", f"Pasado mañana, {_dia(d)}"),
        "semana": ("Esta semana", "Próximos 7 días"),
    }.get(cuando, (f"El {DIAS_DICHOS[d.weekday()]}", f"{DIAS_DICHOS[d.weekday()].capitalize()} {d:%d-%m}"))
    texto = formatear_agenda(a, eventos, titulo)
    n = len(eventos)
    if not n:
        return texto, f"{etiqueta} no tienes nada."
    primero = _evento_dicho(eventos[0], ahora, cuando == "semana")
    if n == 1:
        return texto, f"{etiqueta} tienes uno, {primero}."
    cuantos = f"{n} o más" if n >= maximo else str(n)
    return texto, f"{etiqueta} tienes {cuantos}. El primero, {primero}."
