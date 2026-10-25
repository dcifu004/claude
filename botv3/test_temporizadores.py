#!/usr/bin/env python3
"""Pruebas de los temporizadores y alarmas de la casa.

    python3 test_temporizadores.py

No toca Telegram, ni el parlante, ni la Pi: apunta `BOTV3_CASA_DIR` a un
temporal y fija el reloj. Las pruebas que importan son las de errores que se
cometen en silencio: la frase que se lee como temporizador sin serlo, la hora
ambigua que elige la equivocada, el perfil que ve los temporizadores del otro,
y el vencimiento con el nodo apagado que suena una hora tarde.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

TMP = tempfile.mkdtemp(prefix="test-temporizadores-")
os.environ["BOTV3_CASA_DIR"] = TMP
sys.path.insert(0, str(Path(__file__).resolve().parent))

import temporizadores as tz  # noqa: E402

FALLAS: list[str] = []


def check(nombre: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  ok  {nombre}")
    else:
        FALLAS.append(f"{nombre}{': ' + detalle if detalle else ''}")
        print(f"FALLA  {nombre} {detalle}")


def _rechaza(f) -> bool:
    """Si `f` termina en ValueError (el motivo hablable)."""
    try:
        f()
    except ValueError:
        return True
    return False


def limpiar() -> None:
    for f in Path(TMP).glob("temporizadores.*"):
        f.unlink()


# Jueves 15:00 en Santiago. Fijo, para que "a las 7" tenga una sola respuesta.
AHORA = datetime(2026, 10, 1, 15, 0, 0).astimezone()

print("— duraciones dichas —")
casos_dur = {
    "10 minutos": 600, "diez minutos": 600, "un minuto": 60,
    "una hora y media": 5400, "hora y media": 5400, "media hora": 1800,
    "1 hora 20 minutos": 4800, "una hora y veinte minutos": 4800,
    "un minuto y medio": 90, "90 segundos": 90, "cuarenta y cinco minutos": 2700,
    "un cuarto de hora": 900, "tres cuartos de hora": 2700, "hora y cuarto": 4500,
    "2 horas": 7200, "1,5 horas": 5400, "medio minuto": 30,
}
for frase, seg in casos_dur.items():
    d = tz.duracion(tz.normalizar(frase))
    check(f"«{frase}» = {seg} s", d is not None and d[0] == seg, str(d))

print("— horas dichas: la próxima, y dice cuál —")
def hora(frase: str) -> datetime | None:
    r = tz.hora_dicha(tz.normalizar(frase), AHORA)
    return r[0] if r else None
check("«a las 7» a las 15:00 → 19:00 de hoy", hora("a las 7") == AHORA.replace(hour=19))
check("«a las 7 de la mañana» → mañana 7:00",
      hora("a las 7 de la mañana") == (AHORA + timedelta(days=1)).replace(hour=7))
check("«a las 19:30» → hoy 19:30", hora("a las 19:30") == AHORA.replace(hour=19, minute=30))
check("«a las 7.30» de Whisper → 19:30", hora("a las 7.30") == AHORA.replace(hour=19, minute=30))
check("«mañana a las 7» → mañana 7:00 (no 19:00)",
      hora("mañana a las 7") == (AHORA + timedelta(days=1)).replace(hour=7))
check("«a las 8 menos cuarto» → 19:45", hora("a las 8 menos cuarto") == AHORA.replace(hour=19, minute=45))
check("«a las siete y media de la tarde» → 19:30",
      hora("a las siete y media de la tarde") == AHORA.replace(hour=19, minute=30))
check("«al mediodía» a las 15:00 → mañana 12:00",
      hora("al mediodia") == (AHORA + timedelta(days=1)).replace(hour=12))
check("«a las 3» a las 15:00 → 03:00 de mañana (15:00 ya pasó)",
      hora("a las 3") == (AHORA + timedelta(days=1)).replace(hour=3))
check("la ambigüedad se informa", tz.hora_dicha("a las 7", AHORA)[1] is True)
check("«a las 19» no es ambigua", tz.hora_dicha("a las 19", AHORA)[1] is False)

print("— interpretar: lo que SÍ es de temporizadores —")
def it(frase: str, sonando: bool = False):
    return tz.interpretar(frase, AHORA, sonando=sonando)
i = it("Hola Jaime, pon un temporizador de 10 minutos para los tallarines")
check("crear con nombre", i and i.accion == "crear" and i.segundos == 600
      and i.nombre == "los tallarines", str(i))
i = it("temporizador 3 minutos")
check("crear seco", i and i.accion == "crear" and i.segundos == 180, str(i))
i = it("avísame en 20 minutos")
check("«avísame en 20 minutos»", i and i.accion == "crear" and i.segundos == 1200, str(i))
i = it("ponme una alarma a las 7 de la mañana")
check("alarma", i and i.accion == "crear" and i.tipo == "alarma"
      and i.vence.hour == 7, str(i))
i = it("despiértame mañana a las 6 y media")
check("«despiértame mañana a las 6 y media»", i and i.tipo == "alarma"
      and i.vence == (AHORA + timedelta(days=1)).replace(hour=6, minute=30), str(i))
i = it("pon un temporizador")
check("sin duración pregunta", i and i.extra.get("falta") == "duracion", str(i))
i = it("cuánto le queda")
check("consultar", i and i.accion == "consultar", str(i))
i = it("cuánto falta para los tallarines")
check("consultar con nombre", i and i.accion == "consultar" and "tallarines" in i.nombre, str(i))
i = it("qué temporizadores hay")
check("listar", i and i.accion == "consultar", str(i))
i = it("cancela el temporizador de los huevos")
check("cancelar con nombre", i and i.accion == "cancelar" and "huevos" in i.nombre, str(i))
i = it("borra todas las alarmas")
check("cancelar todas", i and i.accion == "cancelar" and i.todos and i.tipo == "alarma", str(i))
i = it("agrega 5 minutos más")
check("agregar", i and i.accion == "agregar" and i.segundos == 300, str(i))
check("«para» con algo sonando = parar", (it("para", sonando=True) or tz.Intencion("x")).accion == "parar")
check("«ya, para» con algo sonando = parar", (it("ya para", sonando=True) or tz.Intencion("x")).accion == "parar")

print("— interpretar: lo que NO debe capturar —")
no_capturar = [
    "para", "ya", "listo",                       # sin nada sonando no son órdenes
    "pausa", "dale play", "sube el volumen",     # son del Roku y del mezclador
    "agrega tomates a la lista",                 # es de compras
    "qué hora es",
    "pon Netflix",
    "a qué hora juega Colo-Colo",
]
for frase in no_capturar:
    r = it(frase)
    check(f"deja pasar «{frase}»", r is None, str(r))

print("— crear, consultar y cancelar, por perfil —")
limpiar()
check("«cuánto falta para el 18 de septiembre» sin temporizadores sigue al router",
      tz.responder("cuánto falta para el 18 de septiembre", "jaime", AHORA, sonando=False) is None)
r = tz.responder("pon un temporizador de 10 minutos para los tallarines", "jaime", AHORA, sonando=False)
check("responde con nombre y duración", r == "Listo, 10 minutos para los tallarines.", r)
tz.responder("temporizador de 30 segundos", "pilar", AHORA, sonando=False)
check("Diego ve sólo el suyo", len(tz.activos("jaime")) == 1)
check("Camila ve sólo el suyo", len(tz.activos("pilar")) == 1)
r = tz.responder("cuánto le queda", "jaime", AHORA + timedelta(minutes=4, seconds=10), sonando=False)
check("cuenta lo que queda", r == "Al de los tallarines le quedan 5 minutos y 50 segundos.", r)
tz.responder("temporizador de 3 minutos para los huevos", "jaime", AHORA, sonando=False)
r = tz.responder("cancela el temporizador", "jaime", AHORA, sonando=False)
check("con dos activos y sin nombre, pregunta cuál", r and "¿Cuál cancelo?" in r, r)
check("y no canceló nada", len(tz.activos("jaime")) == 2)
r = tz.responder("cancela el temporizador de los huevos", "jaime", AHORA, sonando=False)
check("cancela el nombrado sin confirmar", r == "Cancelé el de huevos." or "huevos" in (r or ""), r)
check("queda uno", len(tz.activos("jaime")) == 1)
r = tz.responder("agrega 5 minutos al de los tallarines", "jaime", AHORA, sonando=False)
check("suma tiempo", r and "Sumé 5 minutos" in r, r)
check("Camila no puede cancelar el de Diego",
      tz.cancelar("pilar", "tallarines")[0] == [] and len(tz.activos("jaime")) == 1)

print("— límites —")
limpiar()
r = tz.responder("temporizador de 30 horas", "jaime", AHORA, sonando=False)
check("más de 24 h se rechaza con motivo", r == "Sólo puedo programar hasta 24 horas.", r)
for n in range(tz.MAX_ACTIVOS):
    tz.crear("jaime", "temporizador", AHORA + timedelta(minutes=n + 1), f"t{n}", ahora=AHORA)
r = tz.responder("temporizador de 2 minutos", "jaime", AHORA, sonando=False)
check("tope de activos por perfil", r and "cancela alguno" in r, r)

print("— vencer: sonar a tiempo, no sonar tarde —")
limpiar()
tz.crear("jaime", "temporizador", AHORA + timedelta(minutes=10), "tallarines", ahora=AHORA)
tz.crear("pilar", "temporizador", AHORA + timedelta(minutes=1), "té", ahora=AHORA)
sonar, avisar = tz.vencidos(AHORA + timedelta(minutes=5))
check("a los 5 min suena sólo el de 1 min", [i["nombre"] for i in sonar] == ["té"] and not avisar)
sonar2, _ = tz.vencidos(AHORA + timedelta(minutes=5, seconds=1))
check("no se devuelve dos veces", sonar2 == [])
check("hay algo sonando", tz.hay_sonando())
check("«para» sin wake word, con algo sonando, para",
      tz.responder("para", "jaime", AHORA, sonando=True) == "Listo.")
check("y ya no suena", not tz.hay_sonando())
sonar, avisar = tz.vencidos(AHORA + timedelta(hours=1))
check("vencido con el nodo apagado (50 min tarde) NO suena, sólo avisa",
      sonar == [] and [i["nombre"] for i in avisar] == ["tallarines"])
limpiar()
tz.crear("jaime", "temporizador", AHORA + timedelta(minutes=1), "pan", ahora=AHORA)
tz.crear("pilar", "temporizador", AHORA + timedelta(minutes=1), "té", ahora=AHORA)
sonar, _ = tz.vencidos(AHORA + timedelta(minutes=2), perfil="jaime")
check("con perfil, el bot de Diego sólo marca los suyos", [i["nombre"] for i in sonar] == ["pan"])
check("y el de Camila sigue activo para su propio bot",
      [i["nombre"] for i in tz.vencidos(AHORA + timedelta(minutes=2), perfil="pilar")[0]] == ["té"])
check("sonando() filtra por perfil", [i["nombre"] for i in tz.sonando("jaime")] == ["pan"])
item = {"tipo": "temporizador", "nombre": "", "duracion": 600}
check("frase de vencimiento lleva la persona",
      tz.frase_vencimiento(item, "Diego") == "Diego, terminó el temporizador de 10 minutos.")

check("aviso de Telegram con nombre",
      tz.frase_telegram({"tipo": "temporizador", "nombre": "los tallarines", "duracion": 600,
                         "vence": int(AHORA.timestamp())})
      == "⏰ Terminó el temporizador de los tallarines (10 minutos).")
check("aviso de uno perdido dice que no sonó",
      "No sonó." in tz.frase_telegram({"tipo": "alarma", "nombre": "", "duracion": 0,
                                         "vence": int(AHORA.timestamp())}, perdido=True))

print("— decir en voz alta —")
check("decir_duracion 3725", tz.decir_duracion(3725) == "1 hora y 2 minutos", tz.decir_duracion(3725))
check("decir_duracion 90", tz.decir_duracion(90) == "1 minuto y 30 segundos")
check("decir_hora 19:30 hoy", tz.decir_hora(AHORA.replace(hour=19, minute=30), AHORA)
      == "hoy a las 7 y media de la tarde", tz.decir_hora(AHORA.replace(hour=19, minute=30), AHORA))
check("decir_hora 1:00 mañana", tz.decir_hora((AHORA + timedelta(days=1)).replace(hour=1, minute=0), AHORA)
      == "mañana a la 1 de la madrugada")


# ===========================================================================
# Encargo 35: órdenes recurrentes
# ===========================================================================
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402


def stgo(a: int, m: int, d: int, h: int, mi: int, seg: int = 0) -> datetime:
    """Un instante con el reloj de pared de Santiago (con su cambio de hora)."""
    if tz.ZONA is None:
        return datetime(a, m, d, h, mi, seg).astimezone()
    return datetime(a, m, d, h, mi, seg, tzinfo=tz.ZONA)


def local(epoch: int) -> datetime:
    return tz._local(datetime.fromtimestamp(epoch, tz.timezone.utc))


def en_disco() -> list[dict]:
    try:
        return json.loads(tz.ARCHIVO.read_text(encoding="utf-8"))["items"]
    except FileNotFoundError:
        return []


LUNES = stgo(2026, 10, 5, 15, 0)       # lunes 15:00
VIERNES = stgo(2026, 10, 9, 23, 0)     # viernes 23:00
DOMINGO = stgo(2026, 10, 11, 10, 0, 30)  # domingo 10:00:30


def rec_de(frase: str, ahora: datetime = LUNES):
    i = tz.interpretar(frase, ahora)
    return i, (i.extra.get("recurrencia") if i else None)


print("— forma real: un temporizadores.json de antes del encargo 35 —")
limpiar()
e = int(LUNES.timestamp())
VIEJOS = [
    {"id": "a1b2c3d4", "perfil": "jaime", "tipo": "alarma", "nombre": "", "estado": "activo",
     "origen": "voz", "creado": e - 100, "vence": e + 4 * 3600, "duracion": 0},
    {"id": "9cb42f21", "perfil": "jaime", "tipo": "temporizador", "nombre": "tallarines", "estado": "activo",
     "origen": "voz", "creado": e - 100, "vence": e + 600, "duracion": 700},
    {"id": "aaaa1111", "perfil": "jaime", "tipo": "temporizador", "nombre": "pan", "estado": "pausado",
     "origen": "voz", "creado": e - 900, "vence": e - 300, "duracion": 900, "restante": 300},
    {"id": "14011faf", "perfil": "jaime", "tipo": "temporizador", "nombre": "cancelado", "estado": "cancelado",
     "origen": "voz", "creado": e - 100, "vence": e + 1800, "duracion": 1800, "cerrado": e - 50},
    {"id": "1e0ef0b1", "perfil": "pilar", "tipo": "alarma", "nombre": "despertar", "estado": "activo",
     "origen": "voz", "creado": e - 100, "vence": e + 3600, "duracion": 0},
]
tz.ARCHIVO.write_text(json.dumps({"version": 1, "items": VIEJOS}, indent=1), encoding="utf-8")
check("se leen los tres vivos de jaime", [i["id"] for i in tz.activos("jaime")] == ["aaaa1111", "9cb42f21", "a1b2c3d4"],
      str([i["id"] for i in tz.activos("jaime")]))
check("resumen igual que antes (alarma, temporizador y pausado con su restante)",
      tz.resumen("jaime", LUNES) == "⏲️ 15 minutos · pan — en pausa; quedan 5 minutos\n"
                                    "⏲️ 11 minutos y 40 segundos · tallarines — quedan 10 minutos\n"
                                    "⏰ alarma — hoy a las 7 de la tarde", tz.resumen("jaime", LUNES))
check("ninguno es una orden: /ordenes no los lista", tz.ordenes("jaime", LUNES) == []
      and tz.resumen_ordenes("jaime", LUNES) == "No tienes órdenes permanentes.")
sonar, avisar = tz.vencidos(LUNES + timedelta(minutes=11))
check("el temporizador viejo suena a su hora; el pausado y la alarma no",
      [i["id"] for i in sonar] == ["9cb42f21"] and avisar == [])
check("al sonar, el de una sola vez SÍ se cierra (terminado)",
      tz.parar("jaime", ahora=LUNES + timedelta(minutes=11))[0]["estado"] == "terminado")
disco = {i["id"]: i for i in en_disco()}
check("los ítems viejos no ganan campos nuevos al reescribirse",
      disco["a1b2c3d4"] == VIEJOS[0] and disco["aaaa1111"] == VIEJOS[2] and disco["1e0ef0b1"] == VIEJOS[4],
      str(disco["aaaa1111"]))
sonar, avisar = tz.vencidos(LUNES + timedelta(hours=9))
check("la alarma vieja perdida se cierra como `perdido`, como siempre",
      sonar == [] and sorted(i["id"] for i in avisar) == ["1e0ef0b1", "a1b2c3d4"]
      and {i["id"]: i for i in en_disco()}["a1b2c3d4"]["estado"] == "perdido")

print("— frases recurrentes, como las escribe Whisper en Chile —")
LV = {"dias": [0, 1, 2, 3, 4], "hora": "06:30"}
DIARIA7 = {"dias": [0, 1, 2, 3, 4, 5, 6], "hora": "07:00"}
DOSHORAS = {"cada_seg": 7200, "desde": "08:00", "hasta": "22:00"}
casos_rec = [
    ("despiértame de lunes a viernes a las 6:30", "alarma", "", LV),
    ("Despiertame de lunes a viernes a las 6.30.", "alarma", "", LV),
    ("despiertame lunes a viernes a las seis y media", "alarma", "", LV),
    ("Hola Jaime, despiértame los días de semana a las 6:30 de la mañana", "alarma", "", LV),
    ("alarma todos los días a las 7", "alarma", "", DIARIA7),
    ("alarma todos los dias a las 7", "alarma", "", DIARIA7),
    ("todos los dias pon una alarma a las siete", "alarma", "", DIARIA7),
    ("despiértame todas las mañanas a las 7", "alarma", "", DIARIA7),
    ("pon una alarma los sábados a las 9", "alarma", "", {"dias": [5], "hora": "09:00"}),
    ("pon una alarma los sabados a las 9", "alarma", "", {"dias": [5], "hora": "09:00"}),
    ("los fines de semana despiertame a las 9 y media", "alarma", "", {"dias": [5, 6], "hora": "09:30"}),
    ("alarma los lunes, miércoles y viernes a las 8 menos cuarto", "alarma", "",
     {"dias": [0, 2, 4], "hora": "07:45"}),
    ("alarma todos los días a las 7 de la tarde para el gimnasio", "alarma", "el gimnasio",
     {"dias": [0, 1, 2, 3, 4, 5, 6], "hora": "19:00"}),
    ("cada domingo a las 10 recuérdame regar", "recordatorio", "regar", {"dias": [6], "hora": "10:00"}),
    ("recuérdame todos los lunes a las 8 sacar la basura", "recordatorio", "sacar la basura",
     {"dias": [0], "hora": "08:00"}),
    ("recuerdame todos los lunes a las 8 sacar la basura", "recordatorio", "sacar la basura",
     {"dias": [0], "hora": "08:00"}),
    ("pon un recordatorio todos los días a las 9 para tomar la pastilla", "recordatorio",
     "tomar la pastilla", {"dias": [0, 1, 2, 3, 4, 5, 6], "hora": "09:00"}),
    ("todas las noches a las 12 recuérdame cerrar la reja", "recordatorio", "cerrar la reja",
     {"dias": [0, 1, 2, 3, 4, 5, 6], "hora": "00:00"}),
    ("cada 2 horas recuérdame tomar agua", "recordatorio", "tomar agua", DOSHORAS),
    ("cada dos horas recuerdame tomar agua", "recordatorio", "tomar agua", DOSHORAS),
    ("cada hora recuérdame estirar de las 9 a las 18", "recordatorio", "estirar",
     {"cada_seg": 3600, "desde": "09:00", "hasta": "18:00"}),
]
for frase, tipo, nombre, rec in casos_rec:
    i, r = rec_de(frase)
    check(f"«{frase}»", bool(i) and i.accion == "crear" and i.tipo == tipo and i.nombre == nombre and r == rec,
          str(i))
i, r = rec_de("recuérdame todos los días a las 3 tomar la pastilla")
check("recordatorio «a las 3» sin más = 15:00 (nadie lo pide de madrugada sin decirlo)",
      r == {"dias": list(range(7)), "hora": "15:00"}, str(r))
i, r = rec_de("alarma todos los días a las 5")
check("alarma «a las 5» sin más = 05:00", r and r["hora"] == "05:00", str(r))
i, r = rec_de("alarma de lunes a viernes a las 7 por 2 semanas")
check("«por 2 semanas» guarda el vencimiento a 14 días",
      i.extra["hasta_epoch"] == int((LUNES + timedelta(days=14)).timestamp()), str(i.extra))
i, r = rec_de("recuérdame los lunes y miércoles a las 8 regar hasta fin de mes")
check("«hasta fin de mes» = 31-10 a las 23:59:59, y no queda en el texto",
      local(i.extra["hasta_epoch"]).strftime("%d-%m %H:%M:%S") == "31-10 23:59:59" and i.nombre == "regar"
      and r == {"dias": [0, 2], "hora": "08:00"}, str(i))
i, r = rec_de("alarma todos los días a las 7 hasta el 15 de noviembre")
check("«hasta el 15 de noviembre»", local(i.extra["hasta_epoch"]).strftime("%d-%m") == "15-11", str(i.extra))
check("sin vencimiento dicho no hay `hasta_epoch`",
      rec_de("alarma todos los días a las 7")[0].extra["hasta_epoch"] is None)

print("— lo que una recurrente NO se traga —")
for frase, falta in [("alarma todos los días", "hora"), ("recuérdame todos los días regar", "hora"),
                     ("cada media hora recuérdame pararme", "intervalo"),
                     ("cada 20 minutos recuérdame tomar agua", "intervalo"),
                     ("recuérdame cada 2 días regar", "recurrencia"),
                     ("alarma cada 2 semanas a las 7", "recurrencia"),
                     ("todos los días a las 9 recuérdame", "texto")]:
    i = tz.interpretar(frase, LUNES)
    check(f"«{frase}» pregunta ({falta}) en vez de adivinar", bool(i) and i.extra.get("falta") == falta, str(i))
limpiar()
r = tz.responder("alarma cada 2 semanas a las 7", "jaime", LUNES, "telegram", sonando=False)
check("una repetición que no entiende NO crea una alarma de una sola vez",
      r and "no entiendo esa repetición" in r and en_disco() == [], r)
for frase in ["recuérdame comprar pan",                       # sin hora: no hay qué programar
              "recuérdame el lunes a las 8 llamar al médico",  # otro día: es de la agenda
              "recuérdame pasado mañana a las 8 llamar",
              "avísame si bajan las zapatillas Nike",          # vigilante: paso 3, fuera
              "todas las mañanas dime el clima y mis reuniones",  # rutina hablada: paso 4
              "apaga la tele todas las noches a las 12",       # acción física: paso 5
              "qué órdenes de compra hay en el proyecto",      # pregunta al vault
              "pausa", "pausa el temporizador", "reanuda", "reanuda la película",
              "cada cuánto hay que regar el helecho", "los lunes tengo reunión a las 8"]:
    r = tz.interpretar(frase, LUNES)
    check(f"deja pasar «{frase}»", r is None, str(r))

print("— las de una sola vez no cambian —")
i = tz.interpretar("pon una alarma a las 7", AHORA)
check("«pon una alarma a las 7» sigue siendo de una vez y la próxima de las dos",
      i.extra == {} and i.vence == AHORA.replace(hour=19), str(i))
i = tz.interpretar("recuérdame a las 8 llamar al médico", LUNES)
check("recordatorio de una sola vez", i and i.tipo == "recordatorio" and i.nombre == "llamar al medico"
      and i.extra == {} and i.vence == LUNES.replace(hour=20), str(i))
i = tz.interpretar("recuérdame en 20 minutos sacar el pan", LUNES)
check("«recuérdame en 20 minutos…»", i and i.tipo == "recordatorio" and i.nombre == "sacar el pan"
      and i.vence == LUNES + timedelta(minutes=20), str(i))
limpiar()
r = tz.responder("recuérdame a las 8 llamar al médico", "jaime", LUNES, "voz", sonando=False)
check("el de una vez se guarda sin confirmación, también por voz, y dice cuál eligió",
      r == "Recordatorio «llamar al medico» para hoy a las 8 de la noche." and len(en_disco()) == 1
      and "recurrencia" not in en_disco()[0], r)
sonar, _ = tz.vencidos(LUNES.replace(hour=20))
check("y suena como recordatorio", [tz.frase_vencimiento(x, "Diego") for x in sonar]
      == ["Diego, recuerda: llamar al medico."] and tz.frase_telegram(sonar[0]).startswith("🔔 Recordatorio: llamar al medico"))
check("y al pararlo se cierra", tz.parar("jaime", ahora=LUNES.replace(hour=20))[0]["estado"] == "terminado")

print("— reloj fijado: la próxima ocurrencia —")
check("viernes 23:00, «de lunes a viernes a las 6:30» → lunes 06:30",
      tz.proxima(LV, VIERNES) == stgo(2026, 10, 12, 6, 30), str(tz.proxima(LV, VIERNES)))
check("domingo 10:00:30, «cada domingo a las 10» → el domingo SIGUIENTE",
      tz.proxima({"dias": [6], "hora": "10:00"}, DOMINGO) == stgo(2026, 10, 18, 10, 0))
check("domingo 09:59, «cada domingo a las 10» → hoy",
      tz.proxima({"dias": [6], "hora": "10:00"}, stgo(2026, 10, 11, 9, 59)) == stgo(2026, 10, 11, 10, 0))
check("justo a la hora no se repite el mismo instante",
      tz.proxima(DIARIA7, stgo(2026, 10, 5, 7, 0)) == stgo(2026, 10, 6, 7, 0))
check("intervalo: lunes 15:00, cada 2 h → 17:00", tz.proxima(DOSHORAS, LUNES) == stgo(2026, 10, 5, 17, 0))
check("intervalo: después de las 22:00 no suena; salta a las 08:00",
      tz.proxima(DOSHORAS, stgo(2026, 10, 5, 21, 30)) == stgo(2026, 10, 6, 8, 0))
check("intervalo: las 22:00 en punto todavía entra",
      tz.proxima(DOSHORAS, stgo(2026, 10, 5, 20, 0), ancla=int(stgo(2026, 10, 5, 20, 0).timestamp()))
      == stgo(2026, 10, 5, 22, 0))
check("intervalo: cuenta desde la ocurrencia anterior, no desde el atraso",
      tz.proxima(DOSHORAS, stgo(2026, 10, 5, 12, 3), ancla=int(stgo(2026, 10, 5, 12, 0).timestamp()))
      == stgo(2026, 10, 5, 14, 0))

print("— crear: qué entendió, y quién confirma —")
limpiar()
r = tz.atender("despiértame de lunes a viernes a las 6:30", "jaime", LUNES, "voz", sonando=False)
check("por voz la respuesta dice qué entendió y pide el ✅",
      r.texto == "Alarma de lunes a viernes a las 6:30 de la mañana. La próxima sería mañana martes. "
                 "Para dejarla fija, confírmala en Telegram.", r.texto)
check("voz sin ✅: no queda NADA guardado", en_disco() == [] and r.propuesta is not None and r.deshacer is None,
      str(en_disco()))
check("`responder` por voz tampoco guarda",
      tz.responder("alarma todos los días a las 7", "jaime", LUNES, "voz", sonando=False) is not None
      and en_disco() == [])
item = tz.confirmar(r.propuesta, LUNES)
check("con el ✅ se guarda, marcada como dictada por voz",
      [(i["tipo"], i["origen"], i["recurrencia"], i["estado"]) for i in en_disco()]
      == [("alarma", "voz", LV, "activo")] and local(item["vence"]) == stgo(2026, 10, 6, 6, 30), str(en_disco()))
check("la forma de siempre más `recurrencia`, y sin `hasta_epoch` si no se dijo",
      set(item) == {"id", "perfil", "tipo", "nombre", "estado", "origen", "creado", "vence", "duracion",
                    "recurrencia"} and item["duracion"] == 0, str(sorted(item)))
limpiar()
antes = en_disco()
r = tz.atender("despiértame de lunes a viernes a las 6:30", "jaime", LUNES, "telegram", sonando=False)
check("escrita en Telegram se guarda directo y dice qué entendió",
      r.texto == "Alarma de lunes a viernes a las 6:30 de la mañana. La próxima es mañana martes."
      and len(en_disco()) == 1 and r.propuesta is None, r.texto)
check("y ofrece deshacer", r.deshacer is not None and r.deshacer[0] == "crear")
tz.deshacer("jaime", "crear", r.deshacer[1][0]["id"], LUNES + timedelta(minutes=5))
check("Telegram + «Deshacer»: vuelve al estado previo (no queda ni rastro)", en_disco() == antes, str(en_disco()))
r = tz.atender("cada domingo a las 10 recuérdame regar", "jaime", DOMINGO, "telegram", sonando=False)
check("«cada domingo a las 10» un domingo 10:00:30 → el domingo siguiente",
      r.texto == "Recordatorio «regar» los domingos a las 10 de la mañana. La próxima es el domingo 18."
      and local(en_disco()[0]["vence"]) == stgo(2026, 10, 18, 10, 0), r.texto)
limpiar()
r = tz.atender("cada 2 horas recuérdame tomar agua", "jaime", LUNES, "telegram", sonando=False)
check("intervalo: dice la ventana y la hora de la próxima",
      r.texto == "Recordatorio «tomar agua» cada 2 horas, entre las 08:00 y las 22:00. "
                 "La próxima es hoy a las 17:00.", r.texto)
check("`crear` rechaza un intervalo de menos de 1 h aunque se llame directo",
      any(True for _ in [0] if _rechaza(lambda: tz.crear("jaime", "recordatorio", None, "x", ahora=LUNES,
                                                        recurrencia={"cada_seg": 1800}))))

print("— topes —")
limpiar()
for n in range(tz.MAX_RECURRENTES):
    tz.crear("jaime", "alarma", None, f"r{n}", "telegram", LUNES, recurrencia={"dias": [n % 7], "hora": "07:00"})
r = tz.responder("alarma todos los días a las 8", "jaime", LUNES, "telegram", sonando=False)
check("máximo 10 recurrentes por perfil", r == "Ya tienes 10 órdenes recurrentes; borra alguna primero.", r)
r = tz.atender("alarma todos los días a las 8", "jaime", LUNES, "voz", sonando=False)
check("por voz el tope se dice antes de proponer", r.propuesta is None and "10 órdenes" in r.texto, r.texto)
r = tz.responder("temporizador de 5 minutos", "jaime", LUNES, "telegram", sonando=False)
check("y van aparte: con 10 recurrentes todavía se puede poner un temporizador",
      r == "Temporizador de 5 minutos, empezando ahora.", r)
check("las recurrentes de otro perfil no cuentan",
      "La próxima" in tz.responder("alarma todos los días a las 8", "pilar", LUNES, "telegram", sonando=False))
limpiar()
for n in range(tz.MAX_ACTIVOS):
    tz.crear("jaime", "temporizador", LUNES + timedelta(minutes=n + 1), f"t{n}", ahora=LUNES)
check("y al revés: 10 temporizadores no impiden una recurrente",
      "La próxima" in tz.responder("alarma todos los días a las 8", "jaime", LUNES, "telegram", sonando=False))
limpiar()
item = tz.crear("jaime", "alarma", None, "", "telegram", LUNES.replace(hour=10), recurrencia={"dias": [6], "hora": "09:00"})
check("una recurrente puede tener la próxima a 6 días (MAX_SEGUNDOS no le aplica)",
      local(item["vence"]) == stgo(2026, 10, 11, 9, 0))
check("pero una alarma de una sola vez sigue topada en 24 h",
      _rechaza(lambda: tz.crear("jaime", "alarma", LUNES + timedelta(hours=30), ahora=LUNES)))

print("— al sonar no se cierra: se reprograma —")
limpiar()
tz.crear("jaime", "alarma", None, "", "telegram", LUNES, recurrencia=LV)
sonar, avisar = tz.vencidos(stgo(2026, 10, 6, 6, 30, 2))
check("suena a su hora", len(sonar) == 1 and avisar == [] and en_disco()[0]["estado"] == "sonando")
check("no se devuelve dos veces mientras suena", tz.vencidos(stgo(2026, 10, 6, 6, 30, 4)) == ([], []))
check("el aviso lleva la hora que sonó", tz.frase_telegram(sonar[0]) == "⏰ Sonó tu alarma (06:30).",
      tz.frase_telegram(sonar[0]))
parado = tz.parar("jaime", ahora=stgo(2026, 10, 6, 6, 30, 5))
check("al pararla vuelve a `activo` para el miércoles, sin `cerrado`",
      en_disco()[0]["estado"] == "activo" and local(en_disco()[0]["vence"]) == stgo(2026, 10, 7, 6, 30)
      and "cerrado" not in en_disco()[0], str(en_disco()[0]))
tz.vencidos(stgo(2026, 10, 9, 6, 30))
tz.parar("jaime", ahora=stgo(2026, 10, 9, 6, 31))
check("el viernes, la próxima es el lunes", local(en_disco()[0]["vence"]) == stgo(2026, 10, 12, 6, 30))

print("— nodo apagado 3 días: UN aviso y la próxima futura —")
limpiar()
tz.crear("jaime", "alarma", None, "", "telegram", LUNES, recurrencia=DIARIA7)
tz.crear("jaime", "temporizador", LUNES + timedelta(minutes=10), "tallarines", ahora=LUNES)
vuelve = stgo(2026, 10, 8, 16, 0)  # jueves: se perdieron martes, miércoles y jueves a las 7
sonar, avisar = tz.vencidos(vuelve)
rec_av = [i for i in avisar if i.get("recurrencia")]
check("no suena nada tarde", sonar == [])
check("un solo aviso por la diaria, que cuenta las 3 que se saltaron",
      len(rec_av) == 1 and rec_av[0]["perdidas"] == 3, str(rec_av))
check("la diaria sigue viva y su próxima es la futura (viernes 07:00)",
      [(i["estado"], local(i["vence"])) for i in en_disco() if i.get("recurrencia")]
      == [("activo", stgo(2026, 10, 9, 7, 0))])
check("el de una sola vez sí queda `perdido`, como siempre",
      [i["estado"] for i in en_disco() if not i.get("recurrencia")] == ["perdido"])
check("en la vuelta siguiente no hay nada más que avisar", tz.vencidos(vuelve + timedelta(seconds=2)) == ([], []))
frase = tz.frase_telegram(rec_av[0], perdido=True, ahora=vuelve)
check("el aviso dice cuál, cuántas y cuándo es la próxima",
      frase == "⏰ Alarma todos los días a las 7 de la mañana: no sonó el martes 06-10 a las 07:00, porque el "
               "bot estaba detenido. Se saltaron 3 veces desde entonces. La próxima es mañana viernes.", frase)
limpiar()
tz.crear("jaime", "recordatorio", None, "tomar agua", "telegram", LUNES, recurrencia=DOSHORAS)
sonar, avisar = tz.vencidos(stgo(2026, 10, 6, 3, 0))
check("un intervalo perdido tampoco se dispara junto, y de madrugada espera a las 08:00",
      sonar == [] and len(avisar) == 1 and local(en_disco()[0]["vence"]) == stgo(2026, 10, 6, 8, 0), str(avisar))

print("— cambio de hora de Chile: a las 7 sigue siendo a las 7 —")
if tz.ZONA is None:
    print("  -- saltado: sin zoneinfo/tzdata (corre esto en la Pi)")
else:
    for nombre, desde in (("abril", stgo(2027, 3, 29, 12, 0)), ("septiembre", stgo(2027, 8, 30, 12, 0))):
        limpiar()
        tz.crear("jaime", "alarma", None, "", "telegram", desde, recurrencia=DIARIA7)
        ahora, horas, saltos = desde, [], set()
        for _ in range(14):
            vence = en_disco()[0]["vence"]
            ahora = datetime.fromtimestamp(vence + 1, tz.timezone.utc)
            sonar, avisar = tz.vencidos(ahora)
            tz.parar("jaime", ahora=ahora)
            horas.append(local(vence).strftime("%H:%M"))
            saltos.add(en_disco()[0]["vence"] - vence)
        check(f"{nombre}: 14 días seguidos suena a las 07:00 locales", horas == ["07:00"] * 14, str(horas))
        # Si esto falla, la prueba no está midiendo nada: no cruzó ningún cambio.
        check(f"{nombre}: el tramo cruza un cambio de hora (un día no dura 86 400 s)",
              len(saltos) == 2 and 86400 in saltos and (saltos - {86400}).pop() in (82800, 90000), str(saltos))
        offsets = {local(int(desde.timestamp()) + d * 86400).utcoffset() for d in range(15)}
        check(f"{nombre}: y el desfase de Santiago cambió en ese tramo", len(offsets) == 2, str(offsets))

print("— vencimiento de la orden y renovar —")
limpiar()
r = tz.atender("alarma todos los días a las 7 por 2 días", "jaime", LUNES, "telegram", sonando=False)
check("dice hasta cuándo", r.texto == "Alarma todos los días a las 7 de la mañana, hasta el 07-10. "
                                      "La próxima es mañana martes.", r.texto)
ident = en_disco()[0]["id"]
check("vence en menos de 7 días: /ordenes ofrece renovar", tz.renovable(tz.ordenes("jaime", LUNES)[0], LUNES))
for dia in (6, 7):
    tz.vencidos(stgo(2026, 10, dia, 7, 0, 1))
    tz.parar("jaime", ahora=stgo(2026, 10, dia, 7, 0, 2))
check("tras la última ocurrencia dentro del plazo pasa a `vencida`",
      en_disco()[0]["estado"] == "vencida" and "cerrado" in en_disco()[0], str(en_disco()[0]))
check("se avisa una vez, y sólo después de marcarla",
      [i["id"] for i in tz.vencidas_sin_avisar("jaime")] == [ident] and tz.vencidas_sin_avisar("pilar") == [])
tz.marcar_avisadas("jaime", [ident])
check("ya avisada no se repite", tz.vencidas_sin_avisar("jaime") == [])
check("vencida ya no suena", tz.vencidos(stgo(2026, 10, 8, 7, 0, 1)) == ([], []))
check("pero sigue en /ordenes, renovable",
      [i["estado"] for i in tz.ordenes("jaime", stgo(2026, 10, 8, 9, 0))] == ["vencida"]
      and "venció" in tz.resumen_ordenes("jaime", stgo(2026, 10, 8, 9, 0)))
check("otro perfil no la renueva", _rechaza(lambda: tz.renovar("pilar", ident, ahora=stgo(2026, 10, 8, 9, 0))))
nuevo = tz.renovar("jaime", ident, ahora=stgo(2026, 10, 8, 9, 0))
check("renovar 30 días: vuelve a `activo`, próxima futura y vence el 07-11",
      nuevo["estado"] == "activo" and local(nuevo["vence"]) == stgo(2026, 10, 9, 7, 0)
      and local(nuevo["hasta_epoch"]) == stgo(2026, 11, 7, 9, 0) and "cerrado" not in nuevo, str(nuevo))
limpiar()
tz.crear("jaime", "alarma", None, "", "telegram", LUNES, recurrencia=DIARIA7,
         hasta_epoch=int(stgo(2026, 10, 6, 12, 0).timestamp()))
tz.pausar("jaime", ahora=LUNES)
tz.vencidos(stgo(2026, 10, 6, 12, 0, 1))
check("una orden en pausa también vence al llegar su término", en_disco()[0]["estado"] == "vencida")
check("una indefinida no ofrece renovar",
      not tz.renovable(tz.crear("jaime", "alarma", None, "", "telegram", LUNES, recurrencia=DIARIA7), LUNES))

print("— 35r2, hallazgo 2: la caída pasa el término de la orden → sólo el aviso de vencimiento —")
limpiar()
r = tz.atender("alarma todos los días a las 7 por 2 días", "jaime", LUNES, "telegram", sonando=False)
ident = en_disco()[0]["id"]
check("la orden la guardó el bot: diaria, próxima el martes 07:00 y término el miércoles 15:00",
      r is not None and en_disco()[0]["recurrencia"] == DIARIA7 and local(en_disco()[0]["vence"]) == stgo(2026, 10, 6, 7, 0)
      and local(en_disco()[0]["hasta_epoch"]) == stgo(2026, 10, 7, 15, 0), str(en_disco()[0]))
vuelve = stgo(2026, 10, 9, 16, 0)      # viernes: se perdieron martes y miércoles, y el término pasó el miércoles
sonar, avisar = tz.vencidos(vuelve, perfil="jaime")
check("no suena tarde y NO sale el aviso de perdida", (sonar, avisar) == ([], []), f"{sonar} {avisar}")
check("queda `vencida` y con el aviso de vencimiento pendiente, uno solo",
      en_disco()[0]["estado"] == "vencida" and [i["id"] for i in tz.vencidas_sin_avisar("jaime")] == [ident],
      str(en_disco()[0]))
tz.marcar_avisadas("jaime", [ident])
check("en la vuelta siguiente no queda nada por avisar",
      tz.vencidos(vuelve + timedelta(seconds=2), perfil="jaime") == ([], []) and tz.vencidas_sin_avisar("jaime") == [])
limpiar()
tz.atender("alarma todos los días a las 7 por 2 semanas", "jaime", LUNES, "telegram", sonando=False)
sonar, avisar = tz.vencidos(vuelve, perfil="jaime")
check("la misma caída sin pasar el término sigue dando UN aviso de perdida y ninguno de vencimiento",
      sonar == [] and len(avisar) == 1 and avisar[0]["perdidas"] == 4 and tz.vencidas_sin_avisar("jaime") == []
      and en_disco()[0]["estado"] == "activo" and local(en_disco()[0]["vence"]) == stgo(2026, 10, 10, 7, 0), str(avisar))

print("— 35r2, hallazgo 1: las acciones de Cockpit van dentro de temporizadores.py —")
limpiar()
tz.atender("despiértame de lunes a viernes a las 6:30", "jaime", datetime.now().astimezone(), "telegram", sonando=False)
ident = en_disco()[0]["id"]
solo = tempfile.mkdtemp(prefix="test-temporizadores-solo-")        # como /opt/botv3 sin ningún script aparte
shutil.copy2(Path(__file__).resolve().parent / "temporizadores.py", solo)
def directo(*args: str) -> tuple[int, dict]:
    p = subprocess.run([sys.executable, str(Path(solo) / "temporizadores.py"), *args], capture_output=True, text=True,
                       env=dict(os.environ, BOTV3_CASA_DIR=TMP))
    return p.returncode, json.loads(p.stdout or "{}")
check("`temporizadores.py pausar <id>` pausa la alarma recurrente, sin temporizador-accion.py al lado",
      os.listdir(solo) == ["temporizadores.py"] and directo("pausar", ident) == (0, {"ok": True, "estado": "pausado"})
      and en_disco()[0]["estado"] == "pausado", str(en_disco()[0]))
check("y la reanuda a un día hábil a las 06:30", directo("reanudar", ident) == (0, {"ok": True, "estado": "activo"})
      and local(en_disco()[0]["vence"]).strftime("%H:%M") == "06:30" and local(en_disco()[0]["vence"]).weekday() < 5
      and "restante" not in en_disco()[0], str(en_disco()[0]))
antes = en_disco()
check("lo inválido contesta JSON con error, código 1 y no escribe",
      directo("borrar", ident)[0] == 1 and directo("pausar", "../x") == (1, {"ok": False, "error": "accion o id invalido"})
      and directo("pausar")[0] == 1 and directo("reanudar", ident)[1].get("ok") is False and en_disco() == antes)
check("0660 tras la acción directa", stat.S_IMODE(os.stat(tz.ARCHIVO).st_mode) == 0o660)
shutil.rmtree(solo, ignore_errors=True)

print("— /ordenes, pausar, reanudar y borrar, por perfil —")
limpiar()
for frase in ["despiértame de lunes a viernes a las 6:30", "cada domingo a las 10 recuérdame regar",
              "recuérdame todos los lunes a las 8 sacar la basura"]:
    tz.responder(frase, "jaime", LUNES, "telegram", sonando=False)
tz.responder("alarma los sábados a las 9", "pilar", LUNES, "telegram", sonando=False)
tz.responder("temporizador de 10 minutos para los tallarines", "jaime", LUNES, "telegram", sonando=False)
r = tz.responder("qué órdenes tengo", "jaime", LUNES, "voz", sonando=False)
check("«qué órdenes tengo» lista sólo las recurrentes del perfil, con su próxima",
      r == "1. 🔁 Alarma de lunes a viernes a las 6:30 de la mañana — próxima: mañana martes a las 06:30\n"
           "2. 🔁 Recordatorio «regar» los domingos a las 10 de la mañana — próxima: el domingo 11 a las 10:00\n"
           "3. 🔁 Recordatorio «sacar la basura» los lunes a las 8 de la mañana — próxima: el lunes 12 a las 08:00", r)
check("pilar ve sólo la suya", [i["perfil"] for i in tz.ordenes("pilar", LUNES)] == ["pilar"]
      and "sábados" in tz.resumen_ordenes("pilar", LUNES) and "regar" not in tz.resumen_ordenes("pilar", LUNES))
check("/temporizadores sigue mostrando todo lo vivo, recurrentes incluidas",
      tz.resumen("jaime", LUNES).count("\n") == 3 and "tallarines" in tz.resumen("jaime", LUNES))
previo = en_disco()
r = tz.atender("pausa la alarma de los lunes", "pilar", LUNES, "telegram", sonando=False)
check("pilar no pausa la de jaime", r.texto == "No encontré esa orden activa." and en_disco() == previo, r.texto)
check("ni la borra con el id", tz.borrar("pilar", [previo[0]["id"]], LUNES) == [] and en_disco() == previo)
check("ni la pausa con el id", tz.pausar("pilar", ids=[previo[0]["id"]], ahora=LUNES) == ([], []) and en_disco() == previo)
check("ni deshace sobre ella", _rechaza(lambda: tz.deshacer("pilar", "crear", previo[0]["id"], LUNES)) and en_disco() == previo)
r = tz.atender("pausa la alarma de los lunes", "jaime", LUNES, "voz", sonando=False)
check("«pausa la alarma de los lunes» no pide confirmación, tampoco por voz",
      r.texto == "Puse en pausa la alarma de lunes a viernes. No sonará hasta que la reanudes."
      and r.propuesta is None and r.deshacer[0] == "pausar", r.texto)
foto = tz.ARCHIVO.read_text(encoding="utf-8")
sonar, avisar = tz.vencidos(stgo(2026, 10, 6, 6, 30, 1), perfil="jaime")
check("en pausa no suena ni se pierde, y sigue en pausa",
      not [i for i in sonar + avisar if i.get("recurrencia")] and en_disco()[0]["estado"] == "pausado"
      and "en pausa" in tz.resumen_ordenes("jaime", LUNES), str(sonar + avisar))
tz.ARCHIVO.write_text(foto, encoding="utf-8")  # el martes simulado se llevó el temporizador; se devuelve el lunes
check("pausar dos veces no hace nada",
      tz.atender("pausa la alarma de los lunes", "jaime", LUNES, "voz", sonando=False).texto
      == "No encontré esa orden activa.")
tz.deshacer("jaime", "pausar", r.deshacer[1][0]["id"], LUNES + timedelta(minutes=30))
check("«Deshacer» la pausa: activa, con el mismo `vence` y sin restos de la pausa",
      en_disco() == previo, str(en_disco()[0]))
tz.responder("pausa el recordatorio de regar", "jaime", LUNES, "telegram", sonando=False)
r = tz.responder("reanuda el recordatorio de regar", "jaime", stgo(2026, 10, 14, 9, 0), "telegram", sonando=False)
check("«reanuda…» días después: la próxima es la futura, no la que pasó en pausa",
      r == "Reanudé el recordatorio de regar. La próxima es el domingo 18.", r)
r = tz.atender("borra el recordatorio de la basura", "jaime", LUNES, "voz", sonando=False)
borrado = next(i for i in en_disco() if i["nombre"] == "sacar la basura")
check("«borra el recordatorio de la basura»: queda `borrado` con `cerrado`, no desaparece",
      r.texto == "Borré el recordatorio de sacar la basura." and r.deshacer[0] == "borrar"
      and borrado["estado"] == "borrado" and borrado["cerrado"] == int(LUNES.timestamp()), r.texto)
foto = tz.ARCHIVO.read_text(encoding="utf-8")
sonar, avisar = tz.vencidos(stgo(2026, 10, 12, 8, 0, 1), perfil="jaime")
check("borrada no se lista, ni suena, ni se avisa como perdida", "basura" not in tz.resumen_ordenes("jaime", LUNES)
      and not [i for i in sonar + avisar if i["nombre"] == "sacar la basura"], str(sonar + avisar))
tz.ARCHIVO.write_text(foto, encoding="utf-8")
check("pasada la hora ya no se deshace",
      _rechaza(lambda: tz.deshacer("jaime", "borrar", borrado["id"], LUNES + timedelta(hours=1, seconds=1))))
vuelto = tz.deshacer("jaime", "borrar", borrado["id"], LUNES + timedelta(minutes=59))
check("dentro de la hora vuelve, activa y con su próxima",
      vuelto["estado"] == "activo" and local(vuelto["vence"]) == stgo(2026, 10, 12, 8, 0)
      and "cerrado" not in vuelto and "antes" not in vuelto, str(vuelto))
check("un «Deshacer» apretado dos veces no hace nada raro",
      _rechaza(lambda: tz.deshacer("jaime", "borrar", borrado["id"], LUNES + timedelta(minutes=59))))
r = tz.atender("cancela la alarma de lunes a viernes", "jaime", LUNES, "telegram", sonando=False)
check("«cancela la alarma…» sobre una recurrente también es un borrado recuperable",
      r.texto == "Borré la alarma de lunes a viernes." and r.deshacer is not None, r.texto)
r = tz.atender("cancela el temporizador de los tallarines", "jaime", LUNES, "telegram", sonando=False)
check("cancelar un temporizador sigue igual: `cancelado`, sin deshacer",
      r.texto == "Cancelé el de los tallarines." and r.deshacer is None
      and next(i for i in en_disco() if i["nombre"] == "los tallarines")["estado"] == "cancelado", r.texto)
check("«borra el recordatorio del dentista» sin ninguno así sigue al clasificador (puede ser de la agenda)",
      tz.responder("borra el recordatorio del dentista", "jaime", LUNES, "telegram", sonando=False) is None)
check("«qué recordatorios tengo» sin ninguno propio también sigue",
      tz.responder("qué recordatorios tengo", "pilar", LUNES, "telegram", sonando=False) is None)
check("un borrado se purga al día; una vencida, a la semana",
      not tz._guardado({"estado": "borrado", "cerrado": 0}, tz.RETENCION)
      and tz._guardado({"estado": "vencida", "cerrado": 0}, tz.RETENCION)
      and not tz._guardado({"estado": "vencida", "cerrado": 0}, tz.RETENCION_VENCIDA))

print("— Cockpit: pausar y reanudar con el temporizador-accion.py real —")
limpiar()
tz.crear("jaime", "recordatorio", None, "sacar la basura", "telegram", LUNES, recurrencia={"dias": [0], "hora": "08:00"})
ident = en_disco()[0]["id"]
accion = Path(__file__).resolve().parent / "temporizador-accion.py"
def cockpit(que: str) -> dict:
    p = subprocess.run([sys.executable, str(accion), que, ident], capture_output=True, text=True,
                       env=dict(os.environ, BOTV3_CASA_DIR=TMP))
    return json.loads(p.stdout or "{}")
check("Cockpit pausa un recordatorio recurrente", cockpit("pausar").get("estado") == "pausado"
      and en_disco()[0]["estado"] == "pausado", str(en_disco()))
check("y aparece en pausa en /ordenes", "en pausa" in tz.resumen_ordenes("jaime", LUNES))
check("Cockpit lo reanuda", cockpit("reanudar").get("estado") == "activo")
mal = en_disco()[0]["vence"]
real = datetime.now().astimezone()
tz.vencidos(real, perfil="jaime")
check("y el bot realinea el `vence` que dejó Cockpit a un lunes 08:00 real",
      local(en_disco()[0]["vence"]).strftime("%a %H:%M") == local(en_disco()[0]["vence"]).strftime("%a ") + "08:00"
      and local(en_disco()[0]["vence"]).weekday() == 0 and en_disco()[0]["vence"] == int(tz.proxima(
          {"dias": [0], "hora": "08:00"}, real).timestamp()), f"{mal} → {en_disco()[0]['vence']}")
check("Cockpit «correr ahora»: suena ya y queda programado para el lunes",
      cockpit("correr").get("ok") is True and len(tz.vencidos(datetime.now().astimezone(), perfil="jaime")[0]) == 1
      and tz.parar("jaime")[0]["estado"] == "activo" and local(en_disco()[0]["vence"]).weekday() == 0)

print("— Cockpit (35r1, hallazgo 1): una ALARMA recurrente se pausa y se reanuda con el script real —")
# El ítem lo escribe el bot (frase → `atender` → `crear`), con el reloj real: el script usa time.time().
REAL = datetime.now().astimezone()
r = tz.atender("despiértame de lunes a viernes a las 6:30", "jaime", REAL, "telegram", sonando=False)
alarma_lv = next(i for i in en_disco() if i["tipo"] == "alarma" and i.get("recurrencia") == LV)
ident = alarma_lv["id"]
def el_item() -> dict:
    return next(i for i in en_disco() if i["id"] == ident)
check("el bot guardó la alarma recurrente con la forma del encargo",
      r is not None and set(alarma_lv) == {"id", "perfil", "tipo", "nombre", "estado", "origen", "creado", "vence",
                                           "duracion", "recurrencia"} and alarma_lv["estado"] == "activo", str(alarma_lv))
check("Cockpit pausa la alarma recurrente", cockpit("pausar") == {"ok": True, "estado": "pausado"}, str(el_item()))
en_pausa = el_item()
check("queda como la deja `pausar` del bot: `pausado`, con `restante` y `pausado_en`",
      en_pausa["estado"] == "pausado" and en_pausa["restante"] == en_pausa["vence"] - en_pausa["pausado_en"]
      and en_pausa["recurrencia"] == LV, str(en_pausa))
check("y /ordenes la muestra en pausa",
      any("lunes a viernes" in l and "en pausa" in l for l in tz.resumen_ordenes("jaime", REAL).splitlines()),
      tz.resumen_ordenes("jaime", REAL))
check("en pausa no suena aunque llegue su hora",
      not [i for i in tz.vencidos(local(en_pausa["vence"]) + timedelta(seconds=1), perfil="jaime")[0] if i["id"] == ident]
      and el_item()["estado"] == "pausado")
check("pausarla dos veces se rechaza y no la toca", cockpit("pausar").get("ok") is False and el_item() == en_pausa)
# El caso que haría sonar una alarma a cualquier hora: pausada justo al vencer (`restante` 0, el
# valor que el propio script escribe en ese instante). Con `vence = ahora + restante` sonaría al reanudar.
datos = json.loads(tz.ARCHIVO.read_text(encoding="utf-8"))
next(i for i in datos["items"] if i["id"] == ident)["restante"] = 0
tz.ARCHIVO.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
check("Cockpit reanuda la alarma recurrente", cockpit("reanudar") == {"ok": True, "estado": "activo"}, str(el_item()))
de_vuelta, real = el_item(), datetime.now().astimezone()
check("vuelve a su próxima ocurrencia real (día hábil 06:30 de Santiago), no a `ahora + restante`",
      de_vuelta["vence"] == int(tz.proxima(LV, real).timestamp()) and local(de_vuelta["vence"]).weekday() < 5
      and local(de_vuelta["vence"]).strftime("%H:%M") == "06:30" and de_vuelta["vence"] > real.timestamp(),
      f"{local(de_vuelta['vence'])}")
check("sin restos de la pausa", "restante" not in de_vuelta and "pausado_en" not in de_vuelta, str(de_vuelta))
check("y no suena al reanudar", not tz.vencidos(datetime.now().astimezone(), perfil="jaime")[0])
check("reanudarla dos veces se rechaza", cockpit("reanudar").get("ok") is False and el_item() == de_vuelta)
unica = tz.crear("jaime", "alarma", REAL + timedelta(hours=1), "", "telegram", REAL)
ident = unica["id"]
check("una alarma de UNA vez sigue sin pausarse (le correría la hora)",
      "no se pueden pausar" in cockpit("pausar").get("error", "") and el_item() == unica, str(el_item()))
datos = json.loads(tz.ARCHIVO.read_text(encoding="utf-8"))
next(i for i in datos["items"] if i["id"] == ident).update(estado="pausado", restante=3600)
tz.ARCHIVO.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
check("ni se reanuda si figura pausada (estado armado a mano)",
      "no se pueden reanudar" in cockpit("reanudar").get("error", "") and el_item()["estado"] == "pausado")
tz.cancelar("jaime", tipo="alarma", ahora=REAL)       # no dejarla para las pruebas de permisos

print("— Cockpit (35r1, hallazgo 2): reanudar cuenta cada tope por separado —")
# Todo con otro perfil y escrito por el bot: diez temporizadores activos y una orden recurrente en pausa.
for n in range(tz.MAX_ACTIVOS):
    tz.crear("pilar", "temporizador", REAL + timedelta(minutes=30 + n), f"olla {n}", "telegram", REAL)
r = tz.atender("cada 2 horas recuérdame tomar agua", "pilar", REAL, "telegram", sonando=False)
pausadas, _ = tz.pausar("pilar", nombre="tomar agua", ahora=REAL)
ident = pausadas[0]["id"]
de_pilar = [i for i in en_disco() if i["perfil"] == "pilar"]
check("el estado de partida es el del hallazgo: 10 temporizadores activos + 1 recordatorio recurrente pausado",
      sum(i["tipo"] == "temporizador" and i["estado"] == "activo" for i in de_pilar) == 10
      and el_item()["estado"] == "pausado" and el_item()["tipo"] == "recordatorio"
      and el_item()["recurrencia"] == DOSHORAS and "restante" in el_item(), str(el_item()))
antes = datetime.now().astimezone()
check("con 10 temporizadores activos, la orden recurrente pausada SÍ se reanuda",
      cockpit("reanudar") == {"ok": True, "estado": "activo"} and el_item()["estado"] == "activo", str(el_item()))
# Un intervalo se alinea al minuto: vale el de antes o el de después de la llamada, por si cambió en medio.
check("y queda en una ocurrencia de su ventana, futura",
      el_item()["vence"] in {int(tz.proxima(DOSHORAS, m).timestamp()) for m in (antes, datetime.now().astimezone())}
      and tz._en_ventana(local(el_item()["vence"]), DOSHORAS) and el_item()["vence"] > antes.timestamp(),
      str(local(el_item()["vence"])))
check("los 10 temporizadores no se tocaron",
      [i for i in en_disco() if i["perfil"] == "pilar" and i["tipo"] == "temporizador"]
      == [i for i in de_pilar if i["tipo"] == "temporizador"])
# Los topes siguen existiendo, cada uno con los suyos. Un 11.º pausado no se alcanza por el bot
# (`crear` cuenta también los pausados), así que estos dos se arman a mano copiando un ítem real.
def con_extra(molde: dict, **cambios) -> str:
    datos = json.loads(tz.ARCHIVO.read_text(encoding="utf-8"))
    extra = dict(molde, id="extra" + uuid_corto(), estado="pausado", restante=600, **cambios)
    datos["items"].append(extra)
    tz.ARCHIVO.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return extra["id"]
def uuid_corto() -> str:
    return f"{len(en_disco()):03d}"
ident = con_extra(next(i for i in de_pilar if i["tipo"] == "temporizador"), nombre="olla de mas")
check("un temporizador pausado con 10 activos sigue sin reanudarse (tope de los de una vez)",
      cockpit("reanudar").get("error") == f"Ya tienes {tz.MAX_ACTIVOS} activos; cancela alguno primero."
      and el_item()["estado"] == "pausado", str(el_item()))
for n in range(tz.MAX_RECURRENTES):
    tz.crear("tope", "recordatorio", None, f"cosa {n}", "telegram", REAL, recurrencia={"dias": [n % 7], "hora": "09:00"})
ident = con_extra(next(i for i in en_disco() if i["perfil"] == "tope"), nombre="la once")
check("una orden recurrente pausada con 10 recurrentes activas no se reanuda (tope de recurrentes)",
      cockpit("reanudar").get("error") == f"Ya tienes {tz.MAX_RECURRENTES} órdenes recurrentes; borra alguna primero."
      and el_item()["estado"] == "pausado", str(el_item()))
ident = con_extra(next(i for i in de_pilar if i["tipo"] == "temporizador"), perfil="tope", nombre="olla")
check("y esas 10 recurrentes tampoco traban un temporizador pausado del mismo perfil",
      cockpit("reanudar") == {"ok": True, "estado": "activo"} and el_item()["estado"] == "activo"
      and "pausado_en" not in el_item(), str(el_item()))

print("— permisos, que es donde esto falla en silencio —")
if not tz.POSIX:
    print("  -- saltado: no es POSIX (corre esto en la Pi antes de desplegar)")
else:
    modo = stat.S_IMODE(os.stat(tz.ARCHIVO).st_mode)
    check("el JSON queda 0660 y no 0600", modo == 0o660, oct(modo))
    os.umask(0o077)
    tz.crear("jaime", "temporizador", AHORA + timedelta(minutes=3), "x", ahora=AHORA)
    modo = stat.S_IMODE(os.stat(tz.ARCHIVO).st_mode)
    check("sigue 0660 con UMask=0077 de la unidad", modo == 0o660, oct(modo))
    modo = stat.S_IMODE(os.stat(tz.LOCK).st_mode)
    check("el .lock también es 0660", modo == 0o660, oct(modo))
    # Encargo 35: cada escritura nueva pasa por la misma `_Sesion`; se comprueba una por una.
    r = tz.atender("alarma todos los días a las 7 por 2 días", "jaime", LUNES, "telegram", sonando=False)
    ident = r.deshacer[1][0]["id"]
    pasos = [("crear recurrente", lambda: None),
             ("pausar", lambda: tz.pausar("jaime", ids=[ident], ahora=LUNES)),
             ("reanudar", lambda: tz.reanudar("jaime", ids=[ident], ahora=LUNES)),
             ("vencidos (reprogramar)", lambda: tz.vencidos(stgo(2026, 10, 6, 7, 0, 1))),
             ("parar", lambda: tz.parar("jaime", ahora=stgo(2026, 10, 6, 7, 0, 2))),
             ("renovar", lambda: tz.renovar("jaime", ident, ahora=stgo(2026, 10, 6, 8, 0))),
             ("borrar", lambda: tz.borrar("jaime", [ident], stgo(2026, 10, 6, 8, 0))),
             ("deshacer", lambda: tz.deshacer("jaime", "borrar", ident, stgo(2026, 10, 6, 8, 5))),
             ("marcar avisadas", lambda: tz.marcar_avisadas("jaime", [ident]))]
    for nombre, paso in pasos:
        paso()
        modo = stat.S_IMODE(os.stat(tz.ARCHIVO).st_mode)
        check(f"0660 tras {nombre}", modo == 0o660, oct(modo))

print()
if FALLAS:
    print(f"❌ {len(FALLAS)} fallas:")
    for f in FALLAS:
        print(f"   · {f}")
    sys.exit(1)
print("✅ todo en verde")
