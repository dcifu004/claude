"""Lista de compras COMPARTIDA entre los perfiles de la casa.

Es el primer estado que jaime y pilar escriben los dos, y por eso vive fuera de
los dos `STATE_DIR`: los de perfil son hermanos y cada unidad pone el del otro en
`InaccessiblePaths` justamente para que no se vean. Meter la lista en uno de
ellos obligaría a abrir ese directorio entero —con `memoria.md`, `casa-*.md` y
sobre todo `claude-config`, que guarda una credencial—. Un directorio nuevo y
chico comparte SOLO esto.

    /opt/nodo/datos/casa/          2770 root:casa   (setgid)
    /opt/nodo/datos/casa/compras.json   0660 <dueño>:casa

Tres cosas que no se deducen del código y rompen si se olvidan:

1. **`UMask=0077` en la unidad gana sobre el grupo.** Un archivo creado por el
   servicio nace `0600` y el otro perfil no lo puede leer aunque esté en `casa`
   y el directorio sea setgid. Por eso cada escritura hace `chmod` explícito
   sobre el temporal ANTES del rename, en vez de confiar en la umask — que es
   ajustable por unidad y por lo tanto se puede perder en un despliegue.
2. **El setgid del directorio es lo que fija el grupo**, no el del proceso: sin
   él los archivos nacen con el grupo primario del usuario (`botpilar`) y jaime
   queda afuera de lo que escribió Camila.
3. **El lock es `flock` sobre un archivo aparte**, no sobre el JSON. Bloquear el
   propio archivo que después se reemplaza por rename deja a los dos procesos
   con el lock de inodos distintos, o sea sin exclusión: el segundo escribe
   encima y se pierde un ítem. Con `.lock` fijo el inodo no cambia nunca.

No usa SQLite a propósito: WAL crea `-wal` y `-shm` con la umask del que los
crea, así que el problema (1) volvería por dos archivos más, y para una lista de
compras de decenas de ítems un JSON con lock sobra.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

try:
    import fcntl
except ImportError:  # Windows: sólo el notebook, y sólo para correr las pruebas.
    # NO es un modo degradado tolerable en producción, y no hace falta que lo
    # sea: los dos servicios corren en la Pi, que es POSIX. Acá no hay un
    # segundo escritor con el que competir. Si algún día esto corriera de verdad
    # sobre Windows, el reemplazo es msvcrt.locking, no dejarlo sin lock.
    fcntl = None  # type: ignore[assignment]

POSIX = fcntl is not None

CASA_DIR = Path(os.environ.get("BOTV3_CASA_DIR", "/opt/nodo/datos/casa"))
LISTA = CASA_DIR / "compras.json"
LOCK = CASA_DIR / ".compras.lock"
MODO_ARCHIVO = 0o660

# Techos. No son de rendimiento: una lista de compras que crece sin tope deja de
# servir para comprar y pasa a ser un basurero de intenciones.
MAX_ITEMS = 60
MAX_LARGO_ITEM = 80
# Bajo este número de ítems la revisión por voz se recita; sobre él se manda
# escrita. Escuchar quince cosas seguidas no deja nada: para eso está la lista.
MAX_ITEMS_EN_VOZ = 5
# Un ítem que lleva dos semanas sin comprarse ya no es una compra pendiente: es
# ruido, y ensucia justo el checklist, que es donde hace falta claridad. NO se
# purga solo — se marca y se ofrece sacarlo, porque a veces sí era algo que
# llevas tiempo sin encontrar.
DIAS_VIEJO = 14

# Separadores de dictado. Whisper transcribe "tomates, aceite de oliva y queso"
# con comas, pero también manda "tomates aceite de oliva y queso" sin ninguna;
# no se intenta adivinar en ese caso — sin separador entra como UN ítem, que se
# ve raro en la lista y se corrige en un toque, mientras que partir por espacios
# convertiría "aceite de oliva" en tres compras.
SEPARADORES = re.compile(r"\s*(?:,|;|\by\b|\be\b|\n)\s*", re.IGNORECASE)


def _normalizar(texto: str) -> str:
    """Clave de comparación: sin tildes, sin mayúsculas, sin espacios de más.

    Sirve para no duplicar "Tomates" contra "tomates" y para que `eliminar`
    encuentre lo que la persona dictó. NO se guarda: lo que se muestra es
    siempre el texto original, porque "leche descremada 1L" dicho así importa.
    """
    plano = unicodedata.normalize("NFKD", texto.strip().lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return " ".join(plano.split())


def partir(texto: str) -> list[str]:
    """Divide un dictado en ítems, sin inventar cortes donde no hay separador."""
    # Las listas pegadas desde una nota llegan muy seguido con viñetas. Sólo se
    # limpia al comienzo de CADA línea: un guion en «sin azúcar» sí es texto.
    texto = re.sub(r"(?m)^\s*(?:(?:[-*•]|\d+[.)])\s+(?:(?:\[[ xX]\]|☐)\s*)?|(?:\[[ xX]\]|☐)\s+)", "", texto)
    crudos = (t.strip(" .:-") for t in SEPARADORES.split(texto))
    vistos, items = set(), []
    for crudo in crudos:
        limpio = " ".join(crudo.split())[:MAX_LARGO_ITEM]
        clave = _normalizar(limpio)
        if clave and clave not in vistos:
            vistos.add(clave)
            items.append(limpio)
    return items


def _ahora() -> str:
    return datetime.now(tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


class _Sesion:
    """Lee el JSON con el lock tomado y lo devuelve escrito al salir.

    Todo pasa por acá: no hay lectura sin lock. Leer sin él en medio de un
    rename da un archivo vacío o a medias, y el modo de falla sería "se borró la
    lista", que es el peor para algo que se llena durante la semana.
    """

    def __init__(self, escribe: bool) -> None:
        self.escribe = escribe
        self.datos: dict[str, Any] = {}

    def __enter__(self) -> "_Sesion":
        CASA_DIR.mkdir(parents=True, exist_ok=True)
        # El LOCK necesita el mismo chmod que el JSON, y es más fácil de olvidar
        # porque nadie lo lee: lo crea el primer perfil que escriba, nace 0600 por
        # la umask de la unidad, y el segundo ni siquiera lo puede ABRIR. El
        # síntoma sería un PermissionError en el bot de Camila sobre un archivo
        # que no aparece en ninguna parte del código de negocio.
        nuevo = not LOCK.exists()
        self._lock = LOCK.open("a+")
        if nuevo:
            try:
                os.chmod(LOCK, MODO_ARCHIVO)
            except OSError:
                pass  # el dueño original ya lo dejó compartido
        if POSIX:
            fcntl.flock(self._lock, fcntl.LOCK_EX)
        try:
            self.datos = json.loads(LISTA.read_text(encoding="utf-8"))
            if not isinstance(self.datos.get("items"), list):
                raise ValueError("estructura inesperada")
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            # Un archivo corrupto no se repara ni se borra: se empieza uno nuevo
            # en memoria y el viejo queda en disco hasta el próximo write, que lo
            # reemplaza. Perder la lista de la semana en silencio sería peor.
            self.datos = {"version": 1, "items": []}
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            if self.escribe and exc[0] is None:
                self._guardar()
        finally:
            if POSIX:
                fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()

    def _guardar(self) -> None:
        tmp = LISTA.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.datos, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        # El chmod va acá y no después del replace: entre rename y chmod hay una
        # ventana en la que el otro perfil abre el archivo y se lo encuentra 0600.
        os.chmod(tmp, MODO_ARCHIVO)
        os.replace(tmp, LISTA)

    @property
    def items(self) -> list[dict[str, Any]]:
        return self.datos["items"]


def leer() -> list[dict[str, Any]]:
    with _Sesion(escribe=False) as s:
        return list(s.items)


class ResultadoAgregar(NamedTuple):
    """Compatibilidad con los dos valores históricos, con ids para el deshacer."""
    agregados: list[str]
    repetidos: list[str]
    ids: list[str]
    def __iter__(self):
        return iter((self.agregados, self.repetidos))


def agregar(textos: list[str], quien: str) -> ResultadoAgregar:
    """Suma ítems. Devuelve (agregados, repetidos).

    Los repetidos se informan en vez de sumarse: dos personas que dicen "falta
    leche" el mismo día no quieren dos leches, quieren saber que ya estaba.
    """
    agregados, repetidos, ids = [], [], []
    with _Sesion(escribe=True) as s:
        presentes = {_normalizar(i["texto"]) for i in s.items}
        for texto in textos:
            clave = _normalizar(texto)
            if not clave:
                continue
            if clave in presentes:
                repetidos.append(texto)
                continue
            if len(s.items) >= MAX_ITEMS:
                repetidos.append(f"{texto} (lista llena, {MAX_ITEMS} máximo)")
                continue
            presentes.add(clave)
            # `epoch` además de `ts`: el texto es para leerlo y el número para
            # comparar. Parsear el string funciona hasta que alguien edita el
            # JSON a mano y deja una fecha con otro formato.
            ident = uuid.uuid4().hex[:8]
            s.items.append({"id": ident, "texto": texto,
                            "quien": quien, "ts": _ahora(),
                            "epoch": int(datetime.now(tz=timezone.utc).timestamp())})
            agregados.append(texto)
            ids.append(ident)
        if ids:
            s.datos.setdefault("ultima_accion", {})[quien] = {
                "tipo": "agregar", "ids": ids,
                "epoch": int(datetime.now(tz=timezone.utc).timestamp())}
    return ResultadoAgregar(agregados, repetidos, ids)


def buscar(patron: str) -> list[dict[str, Any]]:
    """Ítems que coinciden con lo dictado, por subcadena normalizada.

    Se busca y NO se borra: quien pide eliminar ve primero qué va a desaparecer.
    Dictar "leche" cuando hay "leche descremada" y "leche condensada" tiene que
    parar y preguntar, no llevarse las dos.
    """
    clave = _normalizar(re.sub(r"^(?:el|la|los|las)\s+", "", patron.strip(), flags=re.I))
    if not clave:
        return []
    return [i for i in leer() if clave in _normalizar(i["texto"])]


def eliminar(ids: list[str], perfil: str | None = None) -> list[str]:
    """Borra por id y devuelve los textos borrados. Por id y no por texto a
    propósito: entre que se muestra la confirmación y se aprieta el botón, el
    otro perfil pudo agregar algo que coincide con el mismo patrón."""
    quitados, completos = [], []
    with _Sesion(escribe=True) as s:
        quedan = []
        for item in s.items:
            if item["id"] in ids:
                quitados.append(item["texto"])
                completos.append(item)
            else:
                quedan.append(item)
        s.datos["items"] = quedan
        if perfil and completos:
            s.datos.setdefault("ultimo_sacado", {})[perfil] = {
                "items": completos, "epoch": int(datetime.now(tz=timezone.utc).timestamp())}
            s.datos.setdefault("ultima_accion", {})[perfil] = {
                "tipo": "sacar", "items": completos,
                "epoch": int(datetime.now(tz=timezone.utc).timestamp())}
    return quitados


def alternar(ident: str, quien: str) -> bool | None:
    with _Sesion(escribe=True) as s:
        for item in s.items:
            if item.get("id") == ident:
                if item.get("comprado"):
                    item.pop("comprado", None)
                    return False
                item["comprado"] = {"quien": quien, "epoch": int(datetime.now(tz=timezone.utc).timestamp())}
                return True
    return None


def buscar_varios(texto: str) -> dict[str, Any]:
    resultado: dict[str, Any] = {"unicos": [], "ambiguos": {}, "no_encontrados": []}
    for parte in partir(texto):
        encontrados = buscar(parte)
        if len(encontrados) == 1:
            resultado["unicos"].append(encontrados[0])
        elif encontrados:
            resultado["ambiguos"][parte] = encontrados
        else:
            resultado["no_encontrados"].append(parte)
    return resultado


def buscar_varios_voz(texto: str) -> dict[str, Any]:
    """Como buscar_varios, pero una palabra corta no puede borrar otra mayor.

    En voz, ``pan`` no puede sacar ``empanadas`` sólo porque el reconocimiento
    acertó una subcadena. Se aceptan palabras completas (por ejemplo, ``pan``
    en ``pan integral``); lo demás queda para la confirmación por chat.
    """
    resultado: dict[str, Any] = {"unicos": [], "ambiguos": {}, "no_encontrados": []}
    for parte in partir(texto):
        clave = _normalizar(re.sub(r"^(?:el|la|los|las)\s+", "", parte.strip(), flags=re.I))
        encontrados = [i for i in leer()
                       if clave and re.search(rf"\b{re.escape(clave)}\b", _normalizar(i["texto"]))]
        if len(encontrados) == 1:
            resultado["unicos"].append(encontrados[0])
        elif encontrados:
            resultado["ambiguos"][parte] = encontrados
        else:
            resultado["no_encontrados"].append(parte)
    return resultado


def marcar_comprados(textos: str | list[str], quien: str) -> dict[str, Any]:
    partes = partir(textos) if isinstance(textos, str) else textos
    marcados, no = [], []
    with _Sesion(escribe=True) as s:
        for parte in partes:
            clave = _normalizar(re.sub(r"^(?:el|la|los|las)\s+", "", parte.strip(), flags=re.I))
            encontrados = [i for i in s.items if clave in _normalizar(i["texto"])]
            if len(encontrados) == 1:
                item = encontrados[0]
                item["comprado"] = {"quien": quien, "epoch": int(datetime.now(tz=timezone.utc).timestamp())}
                marcados.append(dict(item))
            else:
                no.append(parte)
    return {"marcados": marcados, "no_encontrados": no}


def faltantes() -> list[dict[str, Any]]:
    return [i for i in leer() if not i.get("comprado")]


def esta(texto: str) -> dict[str, Any] | None:
    encontrados = buscar(texto)
    return encontrados[0] if len(encontrados) == 1 else None


def deshacer_agregado(ids: list[str]) -> list[str]:
    with _Sesion(escribe=True) as s:
        quitar = [i for i in s.items if i.get("id") in ids and not i.get("comprado")]
        s.datos["items"] = [i for i in s.items if i not in quitar]
        return [i["texto"] for i in quitar]


def restaurar(perfil: str, ventana: int = 120) -> list[str]:
    with _Sesion(escribe=True) as s:
        ultimo = s.datos.get("ultimo_sacado", {}).get(perfil, {})
        if int(datetime.now(tz=timezone.utc).timestamp()) - int(ultimo.get("epoch", 0)) > ventana:
            return []
        items = ultimo.get("items", [])
        presentes = {_normalizar(str(i.get("texto", ""))) for i in s.items}
        repuestos = [i for i in items if isinstance(i, dict)
                     and _normalizar(str(i.get("texto", ""))) not in presentes
                     and len(s.items) < MAX_ITEMS]
        s.items.extend(repuestos)
        s.datos.get("ultimo_sacado", {}).pop(perfil, None)
        return [i.get("texto", "") for i in repuestos]


def puede_deshacer(perfil: str, ventana: int = 120) -> bool:
    with _Sesion(escribe=False) as s:
        ultimo = s.datos.get("ultima_accion", {}).get(perfil, {})
        return bool(ultimo) and int(datetime.now(tz=timezone.utc).timestamp()) - int(ultimo.get("epoch", 0)) <= ventana


def deshacer(perfil: str, ventana: int = 120) -> list[str]:
    with _Sesion(escribe=True) as s:
        ultimo = s.datos.get("ultima_accion", {}).get(perfil, {})
        if not ultimo or int(datetime.now(tz=timezone.utc).timestamp()) - int(ultimo.get("epoch", 0)) > ventana:
            return []
        if ultimo.get("tipo") == "agregar":
            ids = set(ultimo.get("ids", []))
            quitar = [i for i in s.items if i.get("id") in ids and not i.get("comprado")]
            s.datos["items"] = [i for i in s.items if i not in quitar]
            resultado = [i["texto"] for i in quitar]
        else:
            presentes = {_normalizar(str(i.get("texto", ""))) for i in s.items}
            repuestos = [i for i in ultimo.get("items", []) if isinstance(i, dict)
                         and _normalizar(str(i.get("texto", ""))) not in presentes
                         and len(s.items) < MAX_ITEMS]
            s.items.extend(repuestos)
            resultado = [i.get("texto", "") for i in repuestos]
        s.datos.get("ultima_accion", {}).pop(perfil, None)
        return resultado


def terminar_compra() -> list[str]:
    with _Sesion(escribe=True) as s:
        comprados = [i for i in s.items if i.get("comprado")]
        s.datos["items"] = [i for i in s.items if not i.get("comprado")]
        historial = s.datos.setdefault("historial", [])
        historial.extend({"texto": i["texto"], "quien": (i.get("comprado") or {}).get("quien", "?"),
                          "epoch_comprado": (i.get("comprado") or {}).get("epoch", 0)} for i in comprados)
        s.datos["historial"] = historial[-30:]
        return [i["texto"] for i in comprados]


def vaciar() -> int:
    with _Sesion(escribe=True) as s:
        cuantos = len(s.items)
        s.datos["items"] = []
    return cuantos


def _edad_dias(item: dict[str, Any]) -> float:
    """Días desde que se anotó. 0 si no se puede saber.

    Los ítems anteriores al 20-09-2026 no tienen `epoch`; se cae al `ts`, y si
    tampoco se puede leer se devuelve 0 — o sea NUNCA se marca como viejo algo
    cuya edad no se conoce. Marcarlo por no poder medirlo llevaría a ofrecer
    borrar lo que se acaba de anotar.
    """
    ahora = datetime.now(tz=timezone.utc).timestamp()
    epoch = item.get("epoch")
    if not isinstance(epoch, (int, float)):
        try:
            epoch = datetime.strptime(
                str(item.get("ts", "")), "%Y-%m-%d %H:%M").astimezone().timestamp()
        except (ValueError, TypeError):
            return 0.0
    return max(0.0, (ahora - float(epoch)) / 86400)


def viejos(items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    items = leer() if items is None else items
    return [i for i in items if _edad_dias(i) >= DIAS_VIEJO]


def formatear(items: list[dict[str, Any]] | None = None) -> str:
    """La lista como texto para el chat, con quién pidió cada cosa.

    El autor se muestra porque es una lista compartida: "¿esto quién lo pidió?"
    es la pregunta que aparece sola en el pasillo del super.
    """
    items = leer() if items is None else items
    if not items:
        return "🛒 La lista de compras está vacía."
    hechos = sum(bool(i.get("comprado")) for i in items)
    lineas = [f"🛒 Lista de compras — {hechos} de {len(items)} en el carro", ""]
    for n, i in enumerate(items, 1):
        dias = _edad_dias(i)
        # El reloj va al final y con los días: "⏳ 21d" dice por qué está marcado,
        # mientras que un ícono solo obliga a adivinar qué significa.
        marca = f"  ⏳ {int(dias)}d" if dias >= DIAS_VIEJO else ""
        lineas.append(f"{'✅' if i.get('comprado') else '⬜'} {i['texto']}  · {i['quien']}{marca}")
    return "\n".join(lineas)


def para_recitar(items: list[dict[str, Any]] | None = None) -> str:
    """La misma lista dicha en voz alta: sin números, sin autores, sin emoji.

    Un texto pensado para leer no se escucha bien. "1. tomates · jaime" sale por
    el parlante como "uno punto tomates punto medio jaime".
    """
    items = leer() if items is None else items
    if not items:
        return "La lista de compras está vacía."
    textos = [i["texto"] for i in items]
    if len(textos) == 1:
        return f"En la lista hay una cosa: {textos[0]}."
    return (f"En la lista hay {len(textos)} cosas: "
            f"{', '.join(textos[:-1])} y {textos[-1]}.")


# --- Buzón entre perfiles -------------------------------------------------
# Un bot NO puede escribir en el chat de otro: son tokens distintos y el del
# otro vive en `secretos/`, que cada unidad tiene en InaccessiblePaths. Eso no
# es un obstáculo que convenga rodear —es el límite entre dos personas—, así que
# "mándale la lista a Camila" se resuelve al revés: Jaime deja un pedido en el
# directorio compartido y el bot de Camila lo recoge y se lo manda a SU chat con
# SU token. Nadie toca la credencial de nadie y el pedido queda en un archivo
# que se puede mirar.
#
# La latencia es el precio: hasta un ciclo de sondeo (~20 s). Para "te mando la
# lista al super" es irrelevante, y evita abrir un socket o un servicio nuevo.
BUZON = CASA_DIR / "buzon"
# Un pedido viejo no se entrega: si el bot de Camila estuvo caído dos días, que
# le llegue la lista de compras del martes al llegar el jueves es ruido, no
# servicio. Se descarta y se avisa en el log.
TTL_BUZON = 3600


def dejar_pedido(para: str, de: str, tipo: str = "lista",
                 texto: str = "") -> str:
    """Deja un pedido para otro perfil. Devuelve el id.

    `tipo` es "lista" (mándale la lista a su chat) o "aviso" (dile esto). El
    aviso existe para que el buzón funcione en las DOS direcciones: sin él, un
    pedido que no se pudo entregar moría en el journal y quien lo mandó se
    quedaba con el "le dejé la lista" que ya había leído.
    """
    BUZON.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(BUZON, 0o2770)
    except OSError:
        pass  # ya lo dejó el primero que pasó por acá
    pid = uuid.uuid4().hex[:12]
    destino = BUZON / f"{pid}.json"
    destino.write_text(json.dumps(
        {"para": para, "de": de, "tipo": tipo, "texto": texto,
         "ts": _ahora(),
         "epoch": int(datetime.now(tz=timezone.utc).timestamp())},
        ensure_ascii=False), encoding="utf-8")
    # Mismo chmod que todo lo demás acá: con UMask=0077 el destinatario no puede
    # leer el pedido que le dejaron.
    os.chmod(destino, MODO_ARCHIVO)
    return pid


def recoger_pedidos(perfil: str) -> list[dict[str, Any]]:
    """Saca del buzón los pedidos dirigidos a este perfil y los devuelve.

    Borra al leer, dentro del mismo lock que usa la lista: un pedido entregado
    dos veces manda dos encuestas, y el bot que las manda no tiene forma de
    saber que la primera ya salió.
    """
    if not BUZON.is_dir():
        return []
    ahora = int(datetime.now(tz=timezone.utc).timestamp())
    mios = []
    with _Sesion(escribe=False):  # se reutiliza el candado, no el archivo
        for archivo in sorted(BUZON.glob("*.json")):
            try:
                pedido = json.loads(archivo.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if pedido.get("para") != perfil:
                continue
            try:
                archivo.unlink()
            except OSError:
                continue
            if ahora - int(pedido.get("epoch", 0)) > TTL_BUZON:
                pedido["vencido"] = True
            mios.append(pedido)
    return mios
