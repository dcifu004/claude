"""Pronóstico de tres días en una imagen, para el botón 🌦️ del menú (encargo 74).

Porta el prototipo aprobado de ``propuestas/clima-pronostico/`` (``eventos.py`` y
``render_png.py``) sin rediseñarlo. Es puro: no habla con Telegram ni escribe
archivos; ``botv3.py`` lo usa para mandar la foto y, si algo falla, cae al texto
de «clima hoy».

Lluvia: se considera medible desde 0,1 mm por intervalo de 15 minutos o 0,1 mm
en la serie horaria. Se usa la unión conservadora de ambas resoluciones porque una
puede redondear a cero mientras la otra aún pronostica lluvia. Se confirma con dos
intervalos húmedos consecutivos y se da por terminada sólo después de cuatro
intervalos secos (una hora), para no anunciar como «fin» un corte de 15 minutos.

Las horas de ``minutely_15`` son interpolación del modelo horario en Chile, no
radar: por eso las frases dicen «cerca de las…» y los rótulos «~».

Pillow se importa dentro de ``tarjeta_png``: sin él, levanta ``ImportError`` y el
bot manda el texto. La fuente es Lato (``/usr/share/fonts/truetype/lato``,
redirigible con ``BOTV3_CLIMA_FUENTES``); si falta, la de Pillow y una línea en el
log, nunca una excepción.

Herramienta sin Telegram: ``python3 clima_imagen.py --png <salida> [--lat --lon --lugar]``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from io import BytesIO
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable

try:
    from zoneinfo import ZoneInfo
    TZ_LOCAL: Any = ZoneInfo("America/Santiago")
except Exception:  # sin base de zonas: sólo se aceptan horas sin zona
    TZ_LOCAL = None

LOG = logging.getLogger("botv3.clima_imagen")

URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
FUENTES_DIR = "/usr/share/fonts/truetype/lato"

UMBRAL_LLUVIA_15_MIN = 0.1
UMBRAL_LLUVIA_HORA = 0.1
CONFIRMACION_LLUVIA = 2
CONFIRMACION_SECO = 4
VENTANA_HORAS = 60
MAX_EVENTOS_POR_DIA = 3

ANCHO, ALTO = 1080, 1260
ESCALA_LLUVIA = 4.0

WMO = {
    0: "Despejado", 1: "Poco nublado", 2: "Nubosidad parcial", 3: "Nublado",
    45: "Niebla", 48: "Niebla", 51: "Llovizna", 53: "Llovizna", 55: "Llovizna",
    56: "Llovizna", 57: "Llovizna", 61: "Lluvia", 63: "Lluvia", 65: "Lluvia",
    66: "Lluvia", 67: "Lluvia", 71: "Nieve", 73: "Nieve", 75: "Nieve",
    77: "Nieve", 80: "Chubascos", 81: "Chubascos", 82: "Chubascos",
    85: "Nieve", 86: "Nieve", 95: "Tormenta", 96: "Tormenta", 99: "Tormenta",
}

COLORES = {
    "fondo": "#F4F7FB", "tarjeta": "#FFFFFF", "texto": "#17243A",
    "secundario": "#596981", "azul": "#2188D9", "azul_oscuro": "#075DAD",
    "probable": "#EAF4FB", "amarillo": "#FFCC4D", "linea": "#DCE5EE",
    "nube": "#AFC0D4", "verde": "#31A47C",
}

_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


# ── Lectura y validación de la respuesta de Open-Meteo ──

# Lo que se le pide a Open-Meteo además de lo de la 69. `uv_index` y `wind_gusts_10m`
# no estaban en la lista del encargo, pero el prototipo los usa (avisos de UV y rachas
# del caso seco): sin ellos no se porta tal cual.
HOURLY = ("temperature_2m", "precipitation", "precipitation_probability", "weather_code",
          "uv_index", "wind_gusts_10m")
MINUTELY_15 = ("precipitation",)
DAILY = ("temperature_2m_max", "temperature_2m_min", "precipitation_probability_max", "weather_code")


def parametros_open_meteo(lat: float, lon: float) -> dict[str, Any]:
    """La consulta de `botv3._consultar_open_meteo`, para la herramienta de prueba."""
    return {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,precipitation,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "hourly": ",".join(HOURLY), "minutely_15": ",".join(MINUTELY_15),
        "timezone": "America/Santiago", "forecast_days": 7,
    }


# (mínimo, máximo, admite null). Fuera de rango, NaN, bool o texto: la imagen no se dibuja.
_RANGOS = {
    "temperature_2m": (-90.0, 70.0, False),
    "temperature_2m_max": (-90.0, 70.0, False),
    "temperature_2m_min": (-90.0, 70.0, False),
    "precipitation": (0.0, 500.0, True),
    "precipitation_probability": (0.0, 100.0, True),
    "precipitation_probability_max": (0.0, 100.0, True),
    "uv_index": (0.0, 40.0, True),
    "wind_gusts_10m": (0.0, 500.0, True),
    "weather_code": (0.0, 99.0, False),
}
# Siete días piden 168 horas y 672 cuartos; el tope deja margen y corta listas absurdas.
_MAX_FILAS = {"hourly": 24 * 16 + 2, "minutely_15": 96 * 16 + 8, "daily": 16}
_RE_HORA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_RE_DIA = re.compile(r"\d{4}-\d{2}-\d{2}")


def _valor(nombre: str, x: Any) -> float | None:
    minimo, maximo, nulo = _RANGOS[nombre]
    if x is None and nulo:
        return None
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not minimo <= x <= maximo:
        raise ValueError(f"{nombre}: valor inesperado {str(x)[:20]!r}")  # NaN no pasa el rango
    if nombre == "weather_code" and x != int(x):
        raise ValueError(f"{nombre}: código no entero {x!r}")
    return float(x)


def _bloque(cuerpo: dict[str, Any], nombre: str, columnas: Iterable[str], patron: re.Pattern) -> dict[str, list]:
    bloque = cuerpo.get(nombre)
    if not isinstance(bloque, dict):
        raise ValueError(f"Open-Meteo no trae {nombre}")
    tiempos = bloque.get("time")
    if not isinstance(tiempos, list) or not tiempos or len(tiempos) > _MAX_FILAS[nombre]:
        raise ValueError(f"{nombre}.time vacío o fuera de tamaño")
    salida: dict[str, list] = {"time": []}
    anterior = None
    for texto in tiempos:
        if not isinstance(texto, str) or not patron.fullmatch(texto):
            raise ValueError(f"{nombre}.time con forma rara: {str(texto)[:20]!r}")
        cuando = datetime.fromisoformat(texto)  # levanta ValueError si el día no existe
        if anterior is not None and cuando < anterior:
            raise ValueError(f"{nombre}.time desordenado")
        anterior = cuando
        salida["time"].append(texto)
    for columna in columnas:
        valores = bloque.get(columna)
        if not isinstance(valores, list) or len(valores) != len(tiempos):
            raise ValueError(f"{nombre}.{columna} falta o tiene otro largo")
        salida[columna] = [_valor(columna, x) for x in valores]
    return salida


def leer_series(cuerpo: Any) -> dict[str, Any]:
    """Las series que dibuja la imagen, validadas y con la forma de Open-Meteo.

    Levanta ValueError si falta algo o viene mal. El bot lo llama aparte de lo de la 69:
    si esto falla sólo se pierde la imagen; «clima hoy», «mañana» y «semana» siguen."""
    if not isinstance(cuerpo, dict):
        raise ValueError("respuesta de Open-Meteo que no es un objeto")
    return {"hourly": _bloque(cuerpo, "hourly", HOURLY, _RE_HORA),
            "minutely_15": _bloque(cuerpo, "minutely_15", MINUTELY_15, _RE_HORA),
            "daily": _bloque(cuerpo, "daily", DAILY, _RE_DIA)}


def _local(ahora: datetime) -> datetime:
    """La hora de la respuesta es local y sin zona: `ahora` se lleva a la misma forma."""
    if ahora.tzinfo is not None:
        if TZ_LOCAL is None:
            raise ValueError("sin base de zonas para convertir la hora")
        ahora = ahora.astimezone(TZ_LOCAL).replace(tzinfo=None)
    return ahora


def tres_dias(datos: dict[str, Any], ahora: datetime) -> dict[str, Any]:
    """Recorta las series a hoy, mañana y pasado (lo que muestra la imagen).

    Con la caché de 30 min la respuesta puede ser de antes de medianoche: se toma desde
    el día de `ahora`, no desde el primero de la respuesta. Levanta ValueError si faltan
    días u horas."""
    ahora = _local(ahora)
    hoy = ahora.date()
    desde = datetime.combine(hoy, time.min)
    hasta = desde + timedelta(days=3)
    diario = datos["daily"]
    filas = [i for i, t in enumerate(diario["time"]) if hoy <= date.fromisoformat(t) < hasta.date()]
    if [diario["time"][i] for i in filas] != [(hoy + timedelta(days=n)).isoformat() for n in range(3)]:
        raise ValueError("Open-Meteo no trae hoy, mañana y pasado")
    salida: dict[str, Any] = {"daily": {k: [v[i] for i in filas] for k, v in diario.items()}}
    for nombre, paso in (("hourly", timedelta(hours=1)), ("minutely_15", timedelta(minutes=15))):
        bloque = datos[nombre]
        filas = [i for i, t in enumerate(bloque["time"]) if desde <= datetime.fromisoformat(t) < hasta]
        if not filas:
            raise ValueError(f"{nombre} no cubre los tres días")
        primero = datetime.fromisoformat(bloque["time"][filas[0]])
        ultimo = datetime.fromisoformat(bloque["time"][filas[-1]])
        # Una hora de holgura en cada punta: el día del cambio de hora no tiene las 00:00.
        if primero > desde + timedelta(hours=1) or ultimo < hasta - paso - timedelta(hours=1):
            raise ValueError(f"{nombre} no cubre los tres días")
        salida[nombre] = {k: [v[i] for i in filas] for k, v in bloque.items()}
    return salida


# ── Hitos (eventos.py del prototipo) ──

def _dt(valor: str) -> datetime:
    return datetime.fromisoformat(valor)


def _redondear(valor: float) -> int:
    return math.floor(valor + 0.5) if valor >= 0 else math.ceil(valor - 0.5)


def _hora(cuando: datetime, *, aproximada: bool = False) -> str:
    if cuando.minute:
        texto = f"{cuando.hour}:{cuando.minute:02d}"
    else:
        texto = str(cuando.hour)
    return f"cerca de las {texto}" if aproximada else f"a las {texto}"


def _columnas(bloque: dict[str, Any], nombres: Iterable[str]) -> list[list[Any]]:
    columnas = [bloque.get(nombre) for nombre in nombres]
    if not all(isinstance(columna, list) for columna in columnas):
        raise ValueError("Open-Meteo no trae todas las series necesarias")
    if not columnas or len({len(columna) for columna in columnas}) != 1:
        raise ValueError("Las series de Open-Meteo tienen largos distintos")
    return columnas  # type: ignore[return-value]


def _intervalos_lluvia(datos: dict[str, Any]) -> list[tuple[datetime, float, bool]]:
    """Serie común de 15 min usada por hitos y gráfico.

    El valor sirve para ordenar episodios por intensidad. El booleano es el
    criterio canónico: precipitación medible en la serie de 15 min *o* en la
    hora que contiene el intervalo.
    """
    tiempos, precipitaciones = _columnas(datos.get("minutely_15", {}), ("time", "precipitation"))
    hourly = datos.get("hourly", {})
    h_tiempos = hourly.get("time", [])
    h_precipitaciones = hourly.get("precipitation", [])
    if not isinstance(h_tiempos, list) or not isinstance(h_precipitaciones, list) \
            or len(h_tiempos) != len(h_precipitaciones):
        raise ValueError("Open-Meteo no trae una serie horaria de precipitación válida")
    por_hora = {_dt(t): float(p or 0.0) for t, p in zip(h_tiempos, h_precipitaciones)}
    filas = []
    for texto, valor in zip(tiempos, precipitaciones):
        cuando = _dt(texto)
        mm_15 = float(valor or 0.0)
        hora = cuando.replace(minute=0, second=0, microsecond=0)
        mm_hora = por_hora.get(hora, 0.0)
        medible = mm_15 >= UMBRAL_LLUVIA_15_MIN or mm_hora >= UMBRAL_LLUVIA_HORA
        filas.append((cuando, max(mm_15, mm_hora / 4), medible))
    return filas


def periodos_lluvia(datos: dict[str, Any]) -> list[tuple[datetime, datetime, float]]:
    """Períodos canónicos de lluvia para hitos, sombreado del gráfico, pie y conclusión."""
    filas = _intervalos_lluvia(datos)
    episodios: list[tuple[datetime, datetime, float]] = []
    inicio: datetime | None = None
    acumulado = 0.0
    humedos = 0
    secos = 0
    primer_humedo: datetime | None = None
    primer_seco: datetime | None = None

    pendientes = 0.0
    for cuando, mm, medible in filas:
        if medible:
            if humedos == 0:
                primer_humedo = cuando
                pendientes = 0.0
            humedos += 1
            pendientes += mm
            secos = 0
            primer_seco = None
            if inicio is None and humedos >= CONFIRMACION_LLUVIA:
                inicio = primer_humedo
                acumulado += pendientes
            elif inicio is not None:
                acumulado += mm
        else:
            humedos = 0
            pendientes = 0.0
            primer_humedo = None
            if inicio is not None:
                if secos == 0:
                    primer_seco = cuando
                secos += 1
                if secos >= CONFIRMACION_SECO:
                    episodios.append((inicio, primer_seco or cuando, acumulado))
                    inicio = None
                    acumulado = 0.0
                    secos = 0
                    primer_seco = None

    if inicio is not None and filas:
        episodios.append((inicio, filas[-1][0] + timedelta(minutes=15), acumulado))
    return episodios


def _franjas(
    tiempos: list[datetime], valores: list[float], umbral: float
) -> list[tuple[datetime, datetime, float]]:
    """Agrupa horas consecutivas que superan un umbral."""
    franjas: list[tuple[datetime, datetime, float]] = []
    inicio: datetime | None = None
    fin: datetime | None = None
    maximo = 0.0
    for cuando, valor in zip(tiempos, valores):
        if valor >= umbral:
            if inicio is None:
                inicio = cuando
            fin = cuando + timedelta(hours=1)
            maximo = max(maximo, valor)
        elif inicio is not None:
            franjas.append((inicio, fin or inicio, maximo))
            inicio = fin = None
            maximo = 0.0
    if inicio is not None:
        franjas.append((inicio, fin or inicio, maximo))
    return franjas


def _agregar(candidatos: list[dict[str, Any]], cuando: datetime, tipo: str, frase: str,
             prioridad: int, fuerza: float = 0.0) -> None:
    candidatos.append({"cuando": cuando, "tipo": tipo, "frase": frase,
                       "_vigilia": 0 if 7 <= cuando.hour < 23 else 1,
                       "_prioridad": prioridad, "_fuerza": fuerza})


def eventos(datos: dict[str, Any], ahora: datetime) -> list[dict[str, Any]]:
    """Devuelve hasta tres hitos por día para las próximas 60 horas.

    Los eventos peligrosos o accionables ganan prioridad sobre los extremos diarios.
    """
    ahora = _local(ahora)
    limite = ahora + timedelta(hours=VENTANA_HORAS)
    candidatos: list[dict[str, Any]] = []

    periodos = periodos_lluvia(datos)

    # Lluvia: de cada episodio se conservan inicio y fin; el selector posterior
    # favorece los episodios con más agua cuando hay demasiados avisos en un día.
    for inicio, fin, mm in periodos:
        if ahora <= inicio <= limite:
            prioridad = 0 if 7 <= inicio.hour < 23 else 6
            _agregar(candidatos, inicio, "lluvia_inicio",
                     f"{_hora(inicio, aproximada=True).capitalize()} empieza a llover", prioridad, mm)
        if ahora <= fin <= limite:
            prioridad = 0 if 7 <= fin.hour < 23 else 6
            _agregar(candidatos, fin, "lluvia_fin",
                     f"{_hora(fin, aproximada=True).capitalize()} deja de llover", prioridad, mm)

    hourly = datos.get("hourly", {})
    columnas = _columnas(hourly, ("time", "temperature_2m", "wind_gusts_10m", "uv_index"))
    tiempos = [_dt(t) for t in columnas[0]]
    temperaturas = [float(v) for v in columnas[1]]
    rachas = [float(v or 0.0) for v in columnas[2]]
    uv = [float(v or 0.0) for v in columnas[3]]

    # Máxima y mínima por día, usando sólo puntos dentro de la ventana futura.
    por_dia: dict[Any, list[tuple[datetime, float]]] = defaultdict(list)
    for cuando, temperatura in zip(tiempos, temperaturas):
        if ahora <= cuando <= limite:
            por_dia[cuando.date()].append((cuando, temperatura))
    for filas in por_dia.values():
        cuando_max, maxima = max(filas, key=lambda fila: fila[1])
        cuando_min, minima = min(
            filas, key=lambda fila: (fila[1], 0 if 7 <= fila[0].hour < 23 else 1)
        )
        _agregar(candidatos, cuando_max, "temperatura_maxima",
                 f"Máxima de {_redondear(maxima)}° {_hora(cuando_max)}", 4, maxima)
        _agregar(candidatos, cuando_min, "temperatura_minima",
                 f"Mínima de {_redondear(minima)}° {_hora(cuando_min)}", 5, -minima)

    for inicio, fin, maximo in _franjas(tiempos, rachas, 40.0):
        if fin >= ahora and inicio <= limite:
            desde, hasta = max(inicio, ahora), min(fin, limite)
            _agregar(candidatos, desde, "racha_fuerte",
                     f"Rachas de hasta {_redondear(maximo)} km/h entre {desde.hour} y {hasta.hour} h",
                     1, maximo)

    # UV sólo es accionable aquí si coincide con horas secas. Si una hora se
    # solapa siquiera en parte con un período de lluvia, no se anuncia UV.
    uv_seco = [
        valor if not any(inicio < cuando + timedelta(hours=1) and fin > cuando
                         for inicio, fin, _ in periodos) else 0.0
        for cuando, valor in zip(tiempos, uv)
    ]
    for inicio, fin, maximo in _franjas(tiempos, uv_seco, 6.0):
        if fin >= ahora and inicio <= limite:
            desde, hasta = max(inicio, ahora), min(fin, limite)
            _agregar(candidatos, desde, "uv_alto",
                     f"UV alto entre {desde.hour} y {hasta.hour} h (máx. {str(round(maximo, 1)).replace('.', ',')})",
                     2, maximo)

    for indice in range(3, len(tiempos)):
        cuando = tiempos[indice]
        if not ahora <= cuando <= limite:
            continue
        cambio = temperaturas[indice] - temperaturas[indice - 3]
        if abs(cambio) >= 6.0:
            verbo = "Sube" if cambio > 0 else "Baja"
            _agregar(candidatos, cuando, "cambio_temperatura",
                     f"{verbo} {_redondear(abs(cambio))}° en 3 horas, hasta {_redondear(temperaturas[indice])}° {_hora(cuando)}",
                     1, abs(cambio))

    # Evita varios avisos solapados del mismo tipo (p. ej. el mismo ascenso
    # detectado a las 9 y a las 10). Se conserva el más intenso por día y tipo,
    # salvo lluvia, donde inicio y fin son categorías distintas.
    mejores: dict[tuple[Any, str], dict[str, Any]] = {}
    for evento in candidatos:
        clave = (evento["cuando"].date(), evento["tipo"])
        actual = mejores.get(clave)
        if actual is None or (evento["_vigilia"], evento["_prioridad"], -evento["_fuerza"], evento["cuando"]) < \
                (actual["_vigilia"], actual["_prioridad"], -actual["_fuerza"], actual["cuando"]):
            mejores[clave] = evento

    elegidos: list[dict[str, Any]] = []
    agrupados: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for evento in mejores.values():
        agrupados[evento["cuando"].date()].append(evento)
    for dia in sorted(agrupados):
        ordenados = sorted(
            agrupados[dia],
            key=lambda e: (e["_vigilia"], e["_prioridad"], -e["_fuerza"], e["cuando"]),
        )[:MAX_EVENTOS_POR_DIA]
        elegidos.extend(ordenados)

    elegidos.sort(key=lambda e: e["cuando"])
    return [{k: e[k] for k in ("cuando", "tipo", "frase")} for e in elegidos]


# ── Textos de la tarjeta, el pie y la conclusión (render_png.py del prototipo) ──

def _solapa(inicio: datetime, fin: datetime, periodos) -> bool:
    return any(a < fin and b > inicio for a, b, _ in periodos)


def _tramos_dia(datos: dict[str, Any], fecha: date) -> list[tuple[datetime, datetime]]:
    inicio_dia = datetime.combine(fecha, time.min)
    fin_dia = inicio_dia + timedelta(days=1)
    return [(max(a, inicio_dia), min(b, fin_dia)) for a, b, _ in periodos_lluvia(datos)
            if a < fin_dia and b > inicio_dia]


def _hora_breve(cuando: datetime) -> str:
    return f"{cuando.hour}:{cuando.minute:02d}" if cuando.minute else str(cuando.hour)


def titulo_fecha(fecha: date) -> str:
    dias = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
    return f"{dias[fecha.weekday()]} {fecha.day}"


def _nombre_dia(fecha: date) -> str:
    return ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")[fecha.weekday()]


def datos_tarjetas(datos: dict[str, Any]) -> list[dict[str, Any]]:
    """Contenido visible de las tarjetas; deliberadamente no incluye lluvia."""
    diario = datos["daily"]
    salida = []
    for indice, fecha_texto in enumerate(diario["time"][:3]):
        codigo = int(diario["weather_code"][indice])
        salida.append({
            "titulo": titulo_fecha(date.fromisoformat(fecha_texto)),
            "codigo": codigo,
            "cielo": WMO.get(codigo, "—"),
            "minimo": _redondear(float(diario["temperature_2m_min"][indice])),
            "maximo": _redondear(float(diario["temperature_2m_max"][indice])),
        })
    return salida


def resumen_lluvia_dia(
    datos: dict[str, Any], fecha: date, ahora: datetime | None = None
) -> tuple[str, str | None]:
    """Resumen de un día: madrugada 00–06, mañana 06–12, tarde 12–20 y noche 20–24."""
    tramos = _tramos_dia(datos, fecha)
    if ahora is not None:
        ahora = _local(ahora)
        if fecha == ahora.date():
            tramos = [(max(inicio, ahora), fin) for inicio, fin in tramos if fin > ahora]
    if not tramos:
        return "Sin lluvia", None
    inicio_dia = datetime.combine(fecha, time.min)
    fin_dia = inicio_dia + timedelta(days=1)
    if any(a <= inicio_dia and b >= fin_dia - timedelta(hours=1) for a, b in tramos):
        return "Todo el día", None
    seis = inicio_dia + timedelta(hours=6)
    diurnos = [(a, b) for a, b in tramos if b > seis]
    madrugada = any(a < seis for a, _ in tramos)
    if not diurnos:
        return "Madrugada", None
    inicio, fin = max(diurnos, key=lambda p: (p[1] - max(p[0], seis)).total_seconds())
    inicio_visible = max(inicio, seis)
    principal = (f"{_hora_breve(inicio_visible)} – noche" if fin >= fin_dia or fin.hour >= 20
                 else f"{_hora_breve(inicio_visible)}–{_hora_breve(fin)} h")
    return principal, "+ madrugada" if madrugada and inicio_visible >= seis else None


def _alertas_dia(datos: dict[str, Any], fecha: date) -> list[tuple[str, str]]:
    h, periodos = datos["hourly"], periodos_lluvia(datos)
    uv_seco, rachas = [], []
    for texto, uv, racha in zip(h["time"], h["uv_index"], h["wind_gusts_10m"]):
        cuando = datetime.fromisoformat(texto)
        if cuando.date() != fecha:
            continue
        if float(uv or 0) >= 8 and not _solapa(cuando, cuando + timedelta(hours=1), periodos):
            uv_seco.append(float(uv))
        if float(racha or 0) >= 40:
            rachas.append(float(racha))
    salida = []
    if uv_seco:
        salida.append(("uv", f"UV {_redondear(max(uv_seco))}"))
    if rachas:
        salida.append(("viento", f"Rachas {_redondear(max(rachas))}"))
    return salida


def hitos_dibujados(datos: dict[str, Any], ahora: datetime) -> list[dict[str, Any]]:
    """Hasta cuatro hitos de lluvia para la ventana desde ahora al fin de mañana."""
    ahora = _local(ahora)
    fin_ventana = datetime.combine(ahora.date() + timedelta(days=2), time.min)
    candidatos = []
    for inicio, fin, _ in periodos_lluvia(datos):
        if fin < ahora or inicio > fin_ventana:
            continue
        if inicio.date() == fin.date() and inicio.hour < 7 and fin.hour <= 7:
            candidatos.append({"cuando": inicio, "tipo": "lluvia_madrugada",
                               "texto": f"{_hora_breve(inicio)}–{_hora_breve(fin)} h", "prioridad": 2})
            continue
        if ahora <= inicio <= fin_ventana:
            candidatos.append({"cuando": inicio, "tipo": "lluvia_inicio",
                               "texto": f"~{_hora_breve(inicio)}", "prioridad": 0 if 7 <= inicio.hour < 23 else 2})
        if ahora <= fin <= fin_ventana:
            prioridad = 0 if fin.date() == ahora.date() else (0 if 7 <= fin.hour < 23 else 2)
            candidatos.append({"cuando": fin, "tipo": "lluvia_fin",
                               "texto": f"~{_hora_breve(fin)} h", "prioridad": prioridad})
    elegidos = sorted(candidatos, key=lambda e: (e["prioridad"], e["cuando"]))[:4]
    elegidos.sort(key=lambda e: e["cuando"])
    return [{k: e[k] for k in ("cuando", "tipo", "texto")} for e in elegidos]


def lluvia_de_hoy(datos: dict[str, Any], ahora: datetime) -> tuple[datetime, datetime, bool] | None:
    """El tramo de lluvia que importa hoy desde `ahora`: (inicio, fin, ya_llueve).

    Es el mismo que elige `resumen_lluvia_dia` (el de más horas después de las 6; si sólo
    queda madrugada, el primero), así el pie y la conclusión no se contradicen. El
    prototipo tomaba «el primero que empieza después de ahora»: a las 21:14, con lluvia
    hasta las 23, el pie decía «Mañana empieza cerca de las 2:15», y a la 1, la llovizna
    de las 4 en vez de la lluvia de las 12:15."""
    ahora = _local(ahora)
    inicio_dia = datetime.combine(ahora.date(), time.min)
    fin_dia, seis = inicio_dia + timedelta(days=1), inicio_dia + timedelta(hours=6)
    tramos = [(a, b) for a, b, _ in periodos_lluvia(datos) if b > ahora and a < fin_dia]
    if not tramos:
        return None
    diurnos = [(a, b) for a, b in tramos if b > seis]
    if diurnos:
        a, b = max(diurnos, key=lambda p: (min(p[1], fin_dia) - max(p[0], seis, ahora)).total_seconds())
    else:
        a, b = tramos[0]
    return max(a, ahora), b, a < ahora


def _hasta(fin: datetime, ahora: datetime) -> str:
    fin_hoy = datetime.combine(ahora.date() + timedelta(days=1), time.min)
    if fin >= fin_hoy - timedelta(hours=4) and ahora < fin_hoy - timedelta(hours=4):
        return "la noche"
    if fin >= fin_hoy:
        return "pasada la medianoche"  # de noche, «hasta la noche» ya no dice nada
    return f"cerca de las {_hora_breve(fin)}"


def pie(datos: dict[str, Any], ahora: datetime) -> str:
    """Pie de la foto: texto plano, una o dos líneas."""
    ahora = _local(ahora)
    datos = tres_dias(datos, ahora)
    periodos, hoy = periodos_lluvia(datos), ahora.date()
    principal = lluvia_de_hoy(datos, ahora)
    lineas = []
    if principal:
        inicio, fin, ya_llueve = principal
        if ya_llueve:
            lineas.append(f"☔ Hoy llueve hasta {_hasta(fin, ahora)}.")
        else:
            lineas.append(f"☔ Hoy llueve desde cerca de las {_hora_breve(inicio)} hasta {_hasta(fin, ahora)}.")
        regresos = [a for a, _, _ in periodos if a.date() == hoy + timedelta(days=1) and 7 <= a.hour < 23]
        if regresos:
            lineas.append(f"Mañana vuelve cerca de las {_hora_breve(regresos[0])}.")
    else:
        proximos = [(a, a.date()) for a, _, _ in periodos if a >= ahora and a.date() <= hoy + timedelta(days=2)]
        if proximos:
            a, fecha = proximos[0]
            nombre = "Mañana" if fecha == hoy + timedelta(days=1) else "Pasado mañana"
            lineas.append(f"☔ {nombre} empieza cerca de las {_hora_breve(a)}.")
        else:
            maxima = _redondear(float(datos["daily"]["temperature_2m_max"][0]))
            lineas.append(f"Hoy no se espera lluvia; máxima de {maxima}°.")
    return "\n".join(lineas[:2])


def conclusion(datos: dict[str, Any], ahora: datetime) -> str:
    """Resumen reglado de los tres días, coherente con ``periodos_lluvia``."""
    ahora = _local(ahora)
    datos = tres_dias(datos, ahora)
    hoy = ahora.date()
    partes: list[str] = []
    for desplazamiento in range(3):
        fecha = hoy + timedelta(days=desplazamiento)
        resumen, _ = resumen_lluvia_dia(datos, fecha, ahora if desplazamiento == 0 else None)
        if resumen == "Sin lluvia":
            continue
        nombre = "hoy" if desplazamiento == 0 else _nombre_dia(fecha)
        de_hoy = lluvia_de_hoy(datos, ahora) if desplazamiento == 0 else None
        if resumen not in ("Todo el día", "Madrugada") and de_hoy and de_hoy[2]:
            # Ya llueve: «hoy desde ~21:14» sería la hora de ahora; se dice hasta cuándo.
            fin = de_hoy[1]
            partes.append(f"hoy hasta ~{_hora_breve(fin)} h" if fin < datetime.combine(fecha, time.max)
                          else "hoy hasta pasada la medianoche")
        elif resumen == "Todo el día":
            partes.append(f"{nombre} todo el día")
        elif resumen == "Madrugada":
            partes.append(f"{nombre} de madrugada")
        else:
            inicio = resumen.split("–", 1)[0].strip().replace(" ", "")
            partes.append(f"{nombre} desde ~{inicio}")

    if partes:
        enlace = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]
        prefijo = "Llueve los tres días: " if len(partes) == 3 else "Lleva paraguas: "
        return prefijo + enlace + "."

    # Caso completamente seco: primero riesgos que cambian decisiones; luego la máxima.
    # El prototipo decía «el viernes» fijo (era miércoles): acá, el nombre de pasado mañana.
    hasta = f"Sin lluvia hasta el {_nombre_dia(hoy + timedelta(days=2))}."
    alertas = _alertas_dia(datos, hoy)
    if alertas:
        tipo, texto = alertas[0]
        detalle = f"{texto}." if tipo == "uv" else f"{texto} km/h."
        return f"{hasta} {detalle}"
    maxima = _redondear(float(datos["daily"]["temperature_2m_max"][0]))
    return f"{hasta} Hoy, máxima de {maxima}°."


# ── Dibujo ──

_FUENTES: dict[tuple[str, int, bool], Any] = {}
_AVISADO: set[str] = set()


def _carpeta_fuentes() -> Path:
    return Path(os.environ.get("BOTV3_CLIMA_FUENTES") or FUENTES_DIR)


def fuente(tamano: int, negrita: bool = False):
    """Lato del sistema; si falta, la de Pillow y una línea en el log (una vez por carpeta)."""
    from PIL import ImageFont

    carpeta = _carpeta_fuentes()
    clave = (str(carpeta), tamano, negrita)
    if clave not in _FUENTES:
        ruta = carpeta / ("Lato-Bold.ttf" if negrita else "Lato-Regular.ttf")
        try:
            # Sin el archivo, `truetype` buscaría el nombre en las carpetas del sistema y
            # la variable de entorno no redirigiría nada: se exige que esté ahí.
            if not ruta.is_file():
                raise OSError(f"no existe {ruta}")
            _FUENTES[clave] = ImageFont.truetype(str(ruta), tamano)
        except OSError:
            if str(carpeta) not in _AVISADO:
                _AVISADO.add(str(carpeta))
                LOG.warning("clima: no encontré Lato en %s; dibujo con la letra de Pillow", carpeta)
            try:
                _FUENTES[clave] = ImageFont.load_default(size=tamano)
            except TypeError:  # Pillow < 10.1 no acepta tamaño
                _FUENTES[clave] = ImageFont.load_default()
    return _FUENTES[clave]


def fuente_usada() -> str:
    ruta = _carpeta_fuentes() / "Lato-Regular.ttf"
    return ruta.name if ruta.is_file() else "letra de Pillow"


def _f(nombre: str):
    """F34…F52 regulares y B34…B56 negritas, como las constantes del prototipo."""
    return fuente(int(nombre[1:]), nombre[0] == "B")


def _centrar(draw, caja: tuple[float, float, float, float], texto: str, font, fill: str) -> None:
    x0, y0, x1, _ = caja
    bbox = draw.textbbox((0, 0), texto, font=font)
    draw.text(((x0 + x1 - (bbox[2] - bbox[0])) / 2, y0), texto, font=font, fill=fill)


def _caja_centrada(draw, x0: float, x1: float, y: float, texto: str, font):
    medida = draw.textbbox((0, 0), texto, font=font)
    x = (x0 + x1 - (medida[2] - medida[0])) / 2
    return draw.textbbox((x, y), texto, font=font), (x, y)


def cajas_tarjeta(draw, x0: float, x1: float, y0: float, tarjeta: dict[str, Any]) -> dict[str, Any]:
    """Geometría compartida por el render y las pruebas de separación."""
    centro_icono = ((x0 + x1) // 2, y0 + 102)
    codigo = tarjeta["codigo"]
    if codigo <= 1:
        caja_icono = (centro_icono[0] - 52, centro_icono[1] - 52,
                      centro_icono[0] + 52, centro_icono[1] + 52)
    elif codigo >= 95:
        caja_icono = (centro_icono[0] - 48, centro_icono[1] - 35,
                      centro_icono[0] + 38, centro_icono[1] + 73)
    elif codigo in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 96, 99}:
        caja_icono = (centro_icono[0] - 48, centro_icono[1] - 35,
                      centro_icono[0] + 38, centro_icono[1] + 62)
    else:
        caja_icono = (centro_icono[0] - 48, centro_icono[1] - 35,
                      centro_icono[0] + 38, centro_icono[1] + 34)
    texto_temp = f"{tarjeta['minimo']}° — {tarjeta['maximo']}°"
    caja_titulo, _ = _caja_centrada(draw, x0, x1, y0 + 6, tarjeta["titulo"], _f("B42"))
    caja_cielo, pos_cielo = _caja_centrada(draw, x0, x1, y0 + 187, tarjeta["cielo"], _f("F40"))
    caja_temp, pos_temp = _caja_centrada(draw, x0, x1, y0 + 241, texto_temp, _f("B46"))
    return {
        "centro_icono": centro_icono,
        "caja_icono": caja_icono,
        "caja_titulo": caja_titulo,
        "pos_cielo": pos_cielo,
        "caja_cielo": caja_cielo,
        "pos_temp": pos_temp,
        "caja_temp": caja_temp,
        "texto_temp": texto_temp,
    }


def cajas_alertas(draw, x0: float, x1: float, y0: float, alertas: list[tuple[str, str]],
                  caja_titulo) -> list[dict[str, Any]]:
    """Dónde va cada aviso de UV o rachas dentro de la tarjeta.

    El prototipo los ponía a `x1 - 94 - j * 105` sin medir: con Lato, «Rachas 45» se
    salía de la tarjeta (y de la imagen en la tercera) y pisaba el título. Se conserva el
    lugar —arriba a la derecha— y se omite el que no cabe, como los hitos de madrugada."""
    colocadas: list[dict[str, Any]] = []
    derecha = x1 - 12
    for tipo, texto in alertas[:2]:
        medida = draw.textbbox((0, 0), texto, font=_f("F40"))
        ancho = 44 + (medida[2] - medida[0])
        caja = (derecha - ancho, y0 + 8, derecha, y0 + 56)
        if caja[0] < x0 + 12 or _cajas_intersectan(caja, caja_titulo):
            continue
        colocadas.append({"tipo": tipo, "texto": texto, "caja": caja})
        derecha = caja[0] - 8
    return colocadas


def _icono_cielo(draw, centro: tuple[int, int], codigo: int) -> None:
    x, y = centro
    lluvia = codigo in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
    if codigo <= 1:
        draw.ellipse((x - 30, y - 30, x + 30, y + 30), fill=COLORES["amarillo"])
        for angulo in range(0, 360, 45):
            a = math.radians(angulo)
            draw.line((x + math.cos(a) * 40, y + math.sin(a) * 40,
                       x + math.cos(a) * 52, y + math.sin(a) * 52), fill=COLORES["amarillo"], width=6)
        return
    draw.ellipse((x - 48, y - 7, x + 38, y + 34), fill=COLORES["nube"])
    draw.ellipse((x - 23, y - 35, x + 34, y + 32), fill="#C5D3E1")
    if lluvia:
        for dx in (-26, 0, 26):
            draw.line((x + dx, y + 42, x + dx - 7, y + 62), fill=COLORES["azul"], width=7)
    if codigo >= 95:
        draw.line((x + 7, y + 35, x - 5, y + 55, x + 8, y + 55, x - 3, y + 73),
                  fill=COLORES["amarillo"], width=7, joint="curve")


def _icono_lluvia(draw, x: int, y: int, escala: float = 1.0) -> None:
    r = int(12 * escala)
    draw.ellipse((x - 2 * r, y - r, x + r, y + r), fill=COLORES["nube"])
    for dx in (-r, r):
        draw.line((x + dx, y + r + 5, x + dx - 4, y + r + 16),
                  fill=COLORES["azul"], width=max(3, int(5 * escala)))


def _icono_seco(draw, x: int, y: int) -> None:
    draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=COLORES["amarillo"])


def _icono_alerta(draw, x: int, y: int, tipo: str) -> None:
    if tipo == "uv":
        _icono_seco(draw, x, y)
    else:
        for dy in (-10, 0, 10):
            draw.arc((x - 18, y + dy - 8, x + 18, y + dy + 8), 190, 350,
                     fill=COLORES["secundario"], width=4)


def cajas_hitos(draw, hitos: list[dict[str, Any]], px, gx0: float, gx1: float) -> list[dict[str, Any]]:
    """Distribuye rótulos en dos alturas; omite madrugada si no encuentra espacio."""
    niveles = (598, 640)
    colocados: list[dict[str, Any]] = []
    # Lo diurno tiene prioridad para usar el espacio disponible.
    orden = sorted(hitos, key=lambda h: (h["tipo"] == "lluvia_madrugada", h["cuando"]))
    for hito in orden:
        bbox = draw.textbbox((0, 0), hito["texto"], font=_f("B40"))
        ancho = max(148, (bbox[2] - bbox[0]) + 63)
        x = px(hito["cuando"])
        x0 = min(max(x - ancho / 2, gx0), gx1 - ancho)
        # Aunque otra altura evite el choque de cajas, una madrugada muy cercana
        # haría que la guía de un hito diurno pase por detrás de su rótulo.
        if hito["tipo"] == "lluvia_madrugada" and any(
            x0 < otro["caja"][2] and x0 + ancho > otro["caja"][0]
            for otro in colocados
        ):
            continue
        elegido = None
        for y0 in niveles:
            caja = (x0, y0, x0 + ancho, y0 + 48)
            if not any(_cajas_intersectan(caja, otro["caja"]) for otro in colocados):
                elegido = caja
                break
        if elegido is None:
            # Con los cuatro hitos máximos sólo debiera ocurrir en datos atípicos.
            continue
        colocados.append({**hito, "x": x, "caja": elegido})
    return sorted(colocados, key=lambda h: h["cuando"])


def _cajas_intersectan(a, b) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def geometria_ahora(draw, gx0: float, gy0: float) -> dict[str, Any]:
    """Ubica el texto a la derecha de la raya, sin intersección geométrica."""
    posicion = (gx0 + 12, gy0 - 42)
    caja = draw.textbbox(posicion, "Ahora", font=_f("B34"))
    raya = (gx0, gy0 - 58, gx0, gy0 - 5)
    return {"posicion": posicion, "caja": caja, "raya": raya}


def fondo_ahora(caja) -> tuple[float, float, float, float]:
    """Recuadro del color de la tarjeta bajo el texto «Ahora».

    El prototipo sólo se miró a las 7:30. Entre las 7:45 y las 11:45 la guía del hito
    «~12:15», y de noche la de «~23 h» y la raya de medianoche, atravesaban el texto. Las
    líneas se dibujan antes y este recuadro las corta: pasan por detrás del rótulo."""
    return caja[0] - 3, caja[1] - 3, caja[2] + 3, caja[3] + 3


def texto_ahora_visible(caja, rotulos: list[dict[str, Any]]) -> bool:
    """El texto «Ahora» se omite (queda la raya verde) sólo si la caja de un hito lo pisa,
    como se omite un hito de madrugada sin espacio."""
    return not any(_cajas_intersectan(fondo_ahora(caja), r["caja"]) for r in rotulos)


def caja_ahora(draw, gy0: float) -> tuple[float, float, float, float]:
    return geometria_ahora(draw, 94, gy0)["caja"]


def _envolver(draw, texto: str, font, ancho_maximo: int) -> list[str]:
    palabras, lineas, actual = texto.split(), [], ""
    for palabra in palabras:
        intento = f"{actual} {palabra}".strip()
        bbox = draw.textbbox((0, 0), intento, font=font)
        if actual and bbox[2] - bbox[0] > ancho_maximo:
            lineas.append(actual)
            actual = palabra
        else:
            actual = intento
    if actual:
        lineas.append(actual)
    return lineas[:2]


def _titulo_lugar(draw, lugar: str, ancho_maximo: int):
    """El lugar en B56; si no cabe (hasta 40 letras), más chico y, al final, recortado."""
    for tamano in (56, 48, 42, 36):
        font = fuente(tamano, True)
        medida = draw.textbbox((0, 0), lugar, font=font)
        if medida[2] - medida[0] <= ancho_maximo:
            return lugar, font
    while len(lugar) > 1 and draw.textbbox((0, 0), lugar + "…", font=font)[2] > ancho_maximo:
        lugar = lugar[:-1]
    return lugar.rstrip() + "…", font


def _color_barra(mm: float) -> str:
    fraccion = min(max(mm / ESCALA_LLUVIA, 0.0), 1.0)
    rgb = tuple(round(a + (b - a) * fraccion) for a, b in zip((117, 199, 243), (7, 93, 173)))
    return "#%02x%02x%02x" % rgb


def _hhmm(cuando: datetime) -> str:
    return f"{cuando.hour}:{cuando.minute:02d}"


def tarjeta_png(datos: dict[str, Any], ahora: datetime, lugar: str,
                consultado: datetime | None = None) -> bytes:
    """PNG de 1080 × 1260 con las tres tarjetas, el gráfico de lluvia y la conclusión.

    `datos` es lo de `leer_series` (o la respuesta cruda de Open-Meteo con esa forma);
    `consultado`, la hora en que se pidió a Open-Meteo, para «datos de las HH:MM».
    Levanta ImportError sin Pillow y ValueError si los datos no alcanzan."""
    from PIL import Image, ImageDraw

    ahora = _local(ahora)
    consultado = _local(consultado) if consultado is not None else ahora
    datos = tres_dias(datos, ahora)
    imagen = Image.new("RGB", (ANCHO, ALTO), COLORES["fondo"])
    draw = ImageDraw.Draw(imagen)
    titulo, font_titulo = _titulo_lugar(draw, lugar, ANCHO - 96)
    draw.text((48, 24), titulo, font=font_titulo, fill=COLORES["texto"])
    draw.text((48, 86), f"Lluvia de hoy y mañana · {ahora.day} {_MESES[ahora.month - 1]} · {_hhmm(ahora)}",
              font=_f("F40"), fill=COLORES["secundario"])
    diario, tarjetas = datos["daily"], datos_tarjetas(datos)
    margen, separacion = 36, 16
    ancho_card = (ANCHO - 2 * margen - 2 * separacion) // 3
    for i, tarjeta in enumerate(tarjetas):
        x0 = margen + i * (ancho_card + separacion)
        x1 = x0 + ancho_card
        y0, y1 = 142, 452
        draw.rounded_rectangle((x0, y0, x1, y1), radius=25, fill=COLORES["tarjeta"], outline=COLORES["linea"], width=2)
        _centrar(draw, (x0, y0 + 6, x1, y1), tarjeta["titulo"], _f("B42"), COLORES["texto"])
        geometria = cajas_tarjeta(draw, x0, x1, y0, tarjeta)
        _icono_cielo(draw, geometria["centro_icono"], tarjeta["codigo"])
        draw.text(geometria["pos_cielo"], tarjeta["cielo"], font=_f("F40"), fill=COLORES["secundario"])
        draw.text(geometria["pos_temp"], geometria["texto_temp"], font=_f("B46"), fill=COLORES["texto"])
        alertas = _alertas_dia(datos, date.fromisoformat(diario["time"][i]))
        for alerta in cajas_alertas(draw, x0, x1, y0, alertas, geometria["caja_titulo"]):
            ax0, ay0, _, _ = alerta["caja"]
            _icono_alerta(draw, int(ax0 + 18), int(ay0 + 20), alerta["tipo"])
            draw.text((ax0 + 40, ay0), alerta["texto"], font=_f("F40"), fill=COLORES["secundario"])

    draw.rounded_rectangle((36, 472, 1044, 1056), radius=28, fill=COLORES["tarjeta"])
    draw.text((62, 486), "Lluvia por hora", font=_f("B46"), fill=COLORES["texto"])
    draw.text((62, 538), "Barras: lluvia · franja: puede llover", font=_f("F40"), fill=COLORES["secundario"])
    t0, t1 = ahora, datetime.combine(ahora.date() + timedelta(days=2), time.min)
    gx0, gx1, gy0, gy1 = 94, 1020, 694, 892

    def px(t: datetime) -> float:
        return gx0 + (t - t0).total_seconds() / (t1 - t0).total_seconds() * (gx1 - gx0)

    def py(mm: float) -> float:
        return gy1 - min(mm, ESCALA_LLUVIA) / ESCALA_LLUVIA * (gy1 - gy0)

    h = datos["hourly"]
    filas = [(datetime.fromisoformat(t), float(mm or 0), float(prob or 0), float(temp))
             for t, mm, prob, temp in zip(h["time"], h["precipitation"], h["precipitation_probability"],
                                          h["temperature_2m"])
             if datetime.fromisoformat(t) + timedelta(hours=1) > t0 and datetime.fromisoformat(t) < t1]
    for cuando, mm, prob, _ in filas:
        inicio, fin = max(cuando, t0), min(cuando + timedelta(hours=1), t1)
        if mm == 0 and prob >= 50:
            draw.rectangle((px(inicio), gy0, px(fin), gy1), fill=COLORES["probable"])
    for valor in range(5):
        y = py(valor)
        draw.line((gx0, y, gx1, y), fill=COLORES["linea"], width=2)
        draw.text((48, y - 22), str(valor), font=_f("F40"), fill=COLORES["secundario"])
    for cuando, mm, _, _ in filas:
        if mm <= 0:
            continue
        inicio, fin = max(cuando, t0), min(cuando + timedelta(hours=1), t1)
        x0, x1 = px(inicio) + 2, px(fin) - 2
        if x1 <= x0:  # la hora en curso ya casi pasó: no queda ancho para la barra
            continue
        draw.rounded_rectangle((x0, py(mm), x1, gy1), radius=min(5, (x1 - x0) / 2), fill=_color_barra(mm))
        if mm > ESCALA_LLUVIA:
            draw.line((x0, gy0 + 4, x1, gy0 + 4), fill=COLORES["texto"], width=5)
    medianoche = datetime.combine(ahora.date() + timedelta(days=1), time.min)
    draw.line((px(medianoche), 598, px(medianoche), gy1), fill="#9AABBE", width=4)
    draw.rounded_rectangle((px(medianoche) + 10, 810, px(medianoche) + 164, 858), radius=18, fill="white")
    draw.text((px(medianoche) + 18, 810), titulo_fecha(medianoche.date()), font=_f("B40"),
              fill=COLORES["secundario"])
    rotulos = cajas_hitos(draw, hitos_dibujados(datos, ahora), px, gx0, gx1)
    # Las guías van detrás de las cajas y bajan verticalmente hasta la barra exacta.
    for evento in rotulos:
        x, (_, y0, _, y1) = evento["x"], evento["caja"]
        draw.line((x, y1, x, gy0 - 4), fill="#9AABBE", width=2)
    # "Ahora" queda completamente sobre el eje: no atraviesa barras ni la franja probable,
    # y las guías y la medianoche pasan por detrás de su recuadro.
    ahora_geo = geometria_ahora(draw, gx0, gy0)
    if texto_ahora_visible(ahora_geo["caja"], rotulos):
        draw.rectangle(fondo_ahora(ahora_geo["caja"]), fill=COLORES["tarjeta"])
        draw.text(ahora_geo["posicion"], "Ahora", font=_f("B34"), fill=COLORES["verde"])
    draw.line(ahora_geo["raya"], fill=COLORES["verde"], width=5)
    for evento in rotulos:
        x0, y0, x1, y1 = evento["caja"]
        draw.rounded_rectangle((x0, y0, x1, y1), radius=20, fill="#EDF5FA",
                               outline=COLORES["linea"], width=2)
        (_icono_seco(draw, int(x0 + 24), int(y0 + 24)) if evento["tipo"] == "lluvia_fin"
         else _icono_lluvia(draw, int(x0 + 25), int(y0 + 20), .55))
        draw.text((x0 + 47, y0 + 1), evento["texto"], font=_f("B40"), fill=COLORES["texto"])

    temperaturas = {cuando: temp for cuando, _, _, temp in filas}
    marca = datetime.combine(t0.date(), time(9))
    while marca < t1:
        if marca >= t0 and marca in temperaturas:
            x = px(marca)
            hora_txt, temp_txt = marca.strftime("%H"), f"{_redondear(temperaturas[marca])}°"
            bbox_h = draw.textbbox((0, 0), hora_txt, font=_f("B34"))
            bbox_t = draw.textbbox((0, 0), temp_txt, font=_f("F34"))
            draw.text((x - (bbox_h[2] - bbox_h[0]) / 2, 910), hora_txt,
                      font=_f("B34"), fill=COLORES["texto"])
            draw.text((x - (bbox_t[2] - bbox_t[0]) / 2, 951), temp_txt,
                      font=_f("F34"), fill=COLORES["secundario"])
        marca += timedelta(hours=3)
    draw.text((52, 1004), "Hora / temperatura cada 3 h", font=_f("F40"), fill=COLORES["secundario"])
    draw.text((626, 1004), "Escala fija: 0–4 mm/h", font=_f("F40"), fill=COLORES["secundario"])

    for indice, linea in enumerate(_envolver(draw, conclusion(datos, ahora), _f("B40"), 988)):
        draw.text((46, 1076 + indice * 48), linea, font=_f("B40"), fill=COLORES["texto"])
    draw.text((46, 1206), f"Open-Meteo · datos de las {_hhmm(consultado)} · horarios aproximados",
              font=_f("F34"), fill=COLORES["secundario"])
    salida = BytesIO()
    imagen.save(salida, "PNG", optimize=True)
    return salida.getvalue()


# ── Herramienta de prueba sin Telegram ──

def _ubicacion_del_perfil(perfil: str) -> tuple[float, float, str]:
    """`clima = { lugar, lat, lon }` del perfil, con las mismas reglas que el bot."""
    import tomllib

    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", perfil):
        raise SystemExit(f"perfil inválido: {perfil!r}")
    ruta = Path(__file__).resolve().with_name("perfiles") / f"{perfil}.toml"
    clima = tomllib.loads(ruta.read_text(encoding="utf-8")).get("clima")
    if not isinstance(clima, dict):
        raise SystemExit(f"{ruta} no declara clima")
    lat, lon, lugar = clima.get("lat"), clima.get("lon"), clima.get("lugar")
    for valor, tope in ((lat, 90), (lon, 180)):
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not -tope <= valor <= tope:
            raise SystemExit(f"{ruta}: lat/lon fuera de rango")
    if not isinstance(lugar, str) or not lugar.strip():
        raise SystemExit(f"{ruta}: lugar vacío")
    return float(lat), float(lon), lugar.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dibuja la imagen del botón 🌦️ sin Telegram.")
    parser.add_argument("--png", required=True, help="dónde escribir el PNG")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--lugar")
    parser.add_argument("--json", help="usar una respuesta de Open-Meteo guardada en vez de consultar")
    parser.add_argument("--ahora", help="hora local ISO (por defecto, la de ahora en Santiago)")
    args = parser.parse_args(argv)

    perfil_lat = perfil_lon = None
    lugar = args.lugar
    if args.json is None and (args.lat is None or args.lon is None) or lugar is None:
        perfil_lat, perfil_lon, perfil_lugar = _ubicacion_del_perfil(os.environ.get("BOTV3_PERFIL") or "jaime")
        lugar = lugar or perfil_lugar
    lat = args.lat if args.lat is not None else perfil_lat
    lon = args.lon if args.lon is not None else perfil_lon
    if args.ahora:
        ahora = datetime.fromisoformat(args.ahora)
    elif TZ_LOCAL is not None:
        ahora = datetime.now(TZ_LOCAL)
    else:
        ahora = datetime.now()
    if args.json:
        cuerpo = json.loads(Path(args.json).read_text(encoding="utf-8"))
        consultado = ahora
    else:
        if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise SystemExit("lat/lon fuera de rango")
        import requests

        respuesta = requests.get(URL_OPEN_METEO, params=parametros_open_meteo(lat, lon), timeout=10)
        respuesta.raise_for_status()
        cuerpo = respuesta.json()
        consultado = ahora
    series = leer_series(cuerpo)
    png = tarjeta_png(series, ahora, lugar, consultado)
    Path(args.png).write_bytes(png)
    from PIL import Image

    with Image.open(BytesIO(png)) as imagen:
        medidas = f"{imagen.width}x{imagen.height}"
    print(f"{args.png}: {len(png)} bytes, PNG {medidas}, {lugar}, letra {fuente_usada()}, "
          f"hora {_hhmm(_local(ahora))}")
    print("Pie:", pie(series, ahora).replace("\n", " / "))
    print("Conclusión:", conclusion(series, ahora))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    sys.exit(main())
