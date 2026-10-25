#!/usr/bin/env python3
"""Empuja las alertas del nodo a Telegram. El complemento de /estado, que es pull.

DOCTRINA, que es lo que no se deduce leyendo el codigo:

1. ESTE SCRIPT VIVE FUERA DEL CIFRADO Y ESO ES TODO EL PUNTO. La alerta que mas
   importa es "el volumen LUKS esta cerrado", y esa ocurre justo cuando
   /opt/nodo/datos no se puede leer: ni estado.service arranca (tiene
   RequiresMountsFor), ni n8n corre (su data-root vive adentro), ni se pueden
   leer los secretos. Un emisor que viva adentro jamas puede avisar del unico
   escenario en que hace falta que avise. Por eso el token esta en
   /etc/nodo/avisos.env y la memoria en /var/lib/nodo/, los dos afuera.

   EL BOT ES @Dcs_v5bot. Esta linea existe porque su antecesor, @Dcs_v4bot, no
   tenia el nombre escrito en NINGUNA parte —figuraba solo como "bot dedicado"—
   y el 19-09-2026 se borro en BotFather creyendolo un bot huerfano. El nodo
   quedo nueve horas sin canal de avisos y nadie se entero, porque el unico que
   podia avisarlo era el que se habia caido. Son cinco bots cuyos nombres se
   diferencian en un caracter: el username va escrito en el codigo, en la unidad
   y en IA_INSTRUCCIONES a proposito. El token NO, ese vive en el .env.

2. AVISA CUANDO ALGO CAMBIA, NO MIENTRAS PASA. Se compara por el `id` de la
   alerta, que es estable, y no por su texto, que no lo es: "respaldo hace 37 h"
   y "hace 38 h" son la MISMA alerta. Comparando por texto avisaria cada 10
   minutos hasta que dejes de leerlo, que es como se rompe un sistema de avisos.
   El criterio es el mismo que ya fija estado.py: una alerta que suena sin
   motivo se ignora, incluida la vez que si importa.

3. EL SILENCIO ES LA SEÑAL DE QUE TODO ESTA BIEN. No manda "todo ok" cada
   ciclo. Un resumen periodico entrena a ignorar los mensajes del bot.

4. SI NO SE PUDO ENVIAR, NO SE MARCA COMO AVISADO. Sin esto, un corte de red de
   un minuto se come la alerta para siempre: quedaria registrada como vista sin
   que nadie la haya visto. Esto vale IGUAL para los fallos permanentes: un
   token muerto tampoco consume la alerta, solo cambia lo que dice el log.

5. NO DECIDE NADA POR SU CUENTA. Las alertas y sus umbrales los calcula
   estado.py, que es la unica fuente de verdad. Este script es el cartero.

6. UN 401 NO ES UN CORTE DE RED, Y CONFUNDIRLOS CUESTA NUEVE HORAS. El 19-09-2026
   el token de este bot murio (se borro el bot en BotFather por colision de
   nombres) y el log dijo lo mismo que dice cuando se cae el WiFi: "no se pudo
   enviar el aviso". Son dos acciones opuestas — una es esperar, la otra es ir a
   BotFather — asi que ahora se separan y se loguea la `description` que manda
   el propio Telegram.

7. EL EMISOR DEJA REGISTRO DE SU PROPIA SALUD, PORQUE NO PUEDE CONTAR QUE MURIO.
   Cuando este canal falla, el aviso de que fallo tendria que salir por este
   mismo canal: no hay a quien avisarle. Por eso cada corrida escribe SALUD
   —fuera del cifrado, igual que la memoria— y estado.py lo levanta como una
   alerta mas. Eso NO es un segundo push: es un segundo CAMINO, que se lee con
   /estado desde el bot de consultas, que tiene otro token y otro proceso.

8. CADA AVISO ENVIADO DEJA UNA LINEA EN EL REGISTRO UNICO (encargo 23b, 04-10-2026),
   /opt/nodo/datos/avisos.jsonl, el mismo donde escriben las colas y que muestra la
   pestaña 🔔 Avisos de Cockpit. El registro vive DENTRO del cifrado y este script
   no: por eso registrar NUNCA decide si se avisa. Si no puede escribir —volumen
   cerrado, o la unidad sin permiso sobre el archivo— deja la linea en
   /var/lib/nodo/avisos-registro-pendiente.jsonl, afuera como la memoria, y la
   vuelca en el primer ciclo en que pueda. Este script no crea el registro: solo
   agrega a uno que ya existe (lo crean las colas o la pestaña, con grupo
   dcifu004; la unidad entra con SupplementaryGroups). Nunca se escribe el token
   ni el CHAT_ID. La forma de la linea es la de encargos/registro_avisos.py, que
   no se puede importar desde aca justamente porque vive adentro.

9. LA ALARMA DE CUOTA ES LA UNICA REGLA QUE ESTE SCRIPT CALCULA, y aun asi no
   inventa el umbral: lo lee de /opt/botv3/cuentas.toml como «tope − 5»
   (umbral_semanal y umbral_5h, los mismos que edita 💳 Cuentas y que frenan las
   colas). Avisa UNA vez por ventana: lo avisado se recuerda por la fecha en que
   la ventana se renueva, no por el porcentaje, y no hay mensaje de «resuelto»
   cuando se renueva. Si uso.json no se puede leer —volumen cerrado— no hay
   alarma de cuota y el resto del ciclo sigue igual.

10. EL TEXTO DE UN ERROR DE ENVIO PUEDE TRAER EL TOKEN, porque la URL de Telegram lo
    lleva en la ruta (trampa 17 de IA_INSTRUCCIONES). Ese texto va a stderr —el
    journal— y a SALUD, los dos fuera del cifrado. Por eso `enviar` limpia el
    detalle ANTES de armar el Envio, con el token y el CHAT_ID exactos, y
    registrar_salud y cada print lo vuelven a limpiar por la forma, sin confiar en
    que quien armo el Envio lo haya hecho. Ningun error se imprime crudo.

11. LA BANDEJA DE SALIDA (encargo 24) ES COMO LAS COLAS MANDAN TEXTO SIN TENER EL TOKEN. cola-run.py
    corre sin privilegios y no puede leer /etc/nodo/avisos.env; este script si. La cola deja una linea
    {id, momento, texto} en /opt/nodo/datos/avisos-salida.jsonl (de dcifu004, dentro del cifrado) y
    este script la manda en su proximo ciclo. Reglas:
    - COMO MAXIMO UNA VEZ: antes de enviar marca el id como «intento» en /var/lib/nodo/avisos-bandeja-vista.json
      (afuera del cifrado) y, si el envio sale bien, como «enviado». Un envio que FALLO se desmarca y se
      reintenta al ciclo siguiente (doctrina 4); un ciclo que muere entre la marca y el envio deja el
      «intento» y ese aviso no se manda otra vez: se prefiere perder uno a mandarlo dos veces.
      El registro (avisos.jsonl) lo escribio la cola y ya tiene el aviso: este script NO registra.
    - No crea ni escribe nada en /opt/nodo/datos: la unidad no tiene mas permisos que antes. La abre
      sin seguir symlinks y solo si es un archivo comun, con un nombre y de dcifu004: lo que manda es
      texto que escribio la cuenta sin privilegios.
    - Un texto mas viejo que 24 h no se manda (nadie quiere enterarse hoy de lo de ayer), y a lo mas 5 por ciclo.
    - Con el volumen cerrado no hay archivo, no pasa nada y el resto del ciclo sigue igual.
    - CADA CICLO publica /var/lib/nodo/avisos-bandeja.json (0644, sin secretos: version, ultimo_ciclo y
      si pudo leer la bandeja). Es lo que mira cola-run.py para saber si este lado esta activo, en vez de
      un interruptor que alguien edite: sin archivo, viejo (> 25 min) o con ok=false la cola avisa por
      `nodo-desplegar sugerir`, como antes.

12. EL AVISO PREVIO (encargo 24) ES UNA SEGUNDA REGLA DE CUOTA, APARTE DE LA ALARMA (doctrina 9). La alarma
    avisa por cuenta al llegar a «tope − 5»; esta avisa solo si una cola activa (vivo/*.json no finales
    y escritos hace menos de 2 h) USA esa cuenta, al cruzar el % `aviso_5h` / `aviso_semanal` que el
    usuario puso para ella en cuentas.toml desde el panel (sin valor: no avisa). Una vez por ventana, con
    la misma memoria por fecha de renovacion. No calcula el pronostico: lo publica la cola en su vivo.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import http.client
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import time
from typing import NamedTuple
import urllib.error
import urllib.parse
import urllib.request


# Las dos fuentes. La de HA sobrevive al volumen cerrado (estado-nodo.service no
# tiene RequiresMountsFor); la completa no, y esa ausencia es informacion.
ESTADO_COMPLETO = Path("/opt/nodo/datos/estado.json")
ESTADO_MINIMO = Path("/opt/nodo/ha/estado/nodo_estado.json")

MEMORIA = Path("/var/lib/nodo/avisos-vistos.json")
CONFIG = Path("/etc/nodo/avisos.env")

# La salud del propio emisor, tambien fuera del cifrado: la lee estado.py para
# poder decir por OTRO canal que este murio. Ver punto 7 de la doctrina.
SALUD = Path("/var/lib/nodo/avisos-salud.json")

# Si el JSON completo quedo viejo, el recolector no esta corriendo. Se mira la
# antiguedad y no solo la existencia: un archivo de ayer miente peor que uno que
# falta, porque parece que todo esta bien.
MAX_ANTIGUEDAD_S = 20 * 60

# El registro unico de avisos (doctrina 8). REGISTRO vive dentro del cifrado; lo
# que no se pudo escribir ahi espera afuera, con tope para que no crezca solo.
REGISTRO = Path("/opt/nodo/datos/avisos.jsonl")
REGISTRO_PENDIENTE = Path("/var/lib/nodo/avisos-registro-pendiente.jsonl")
# Dueño esperado del registro: la carpeta es de esta cuenta sin privilegios y root escribe ahi.
DUENO_REGISTRO = "dcifu004"
MAX_PENDIENTES = 200

# La alarma de cuota (doctrina 9). El tope sale de cuentas.toml; los dos de aca
# abajo son los de cola-run.py para una cuenta que no lo trae escrito.
USO = Path("/opt/nodo/datos/uso.json")
CUENTAS = Path("/opt/botv3/cuentas.toml")
CUOTA_VISTA = Path("/var/lib/nodo/avisos-cuota.json")
MARGEN_CUOTA = 5
TOPE_SEMANAL, TOPE_5H = 75, 90
# `renueva` trae microsegundos que cambian entre lecturas de la MISMA ventana.
# Una ventana nueva se renueva horas o dias despues, nunca dentro de este margen.
MISMA_VENTANA_S = 15 * 60

# La bandeja de salida (doctrina 11) y el aviso previo (doctrina 12).
BANDEJA = Path("/opt/nodo/datos/avisos-salida.jsonl")
BANDEJA_VISTA = Path("/var/lib/nodo/avisos-bandeja-vista.json")
BANDEJA_ESTADO = Path("/var/lib/nodo/avisos-bandeja.json")
BANDEJA_VERSION = 1
BANDEJA_MAX_BYTES = 256 * 1024
BANDEJA_VIEJA_S = 24 * 3600
BANDEJA_VISTA_S = 3 * 24 * 3600
BANDEJA_POR_CICLO = 5
RE_ID_BANDEJA = re.compile(r"s-\d{8}-\d{6}-[0-9a-f]{8}")
VIVOS = Path("/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/vivo")
PREVIO_VISTO = Path("/var/lib/nodo/avisos-previo.json")
VIVO_FRESCO_S = 2 * 3600
ESTADOS_ACTIVOS = ("partiendo", "esperando autorización", "esperando", "línea base de pruebas", "corriendo",
                   "esperando_cuota", "pruebas finales", "desplegando")
RE_COLA = re.compile(r"[A-Za-z0-9_-]{1,40}")


def cargar_config() -> dict[str, str]:
    datos: dict[str, str] = {}
    if CONFIG.exists():
        for linea in CONFIG.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            datos[clave.strip()] = valor.strip()
    for clave in ("TELEGRAM_TOKEN", "CHAT_ID"):
        datos.setdefault(clave, os.environ.get(clave, ""))
    return datos


class Envio(NamedTuple):
    """Resultado de un envio. `permanente` es la unica parte que importa de
    verdad: dice si tiene sentido reintentar dentro de 10 minutos o si hay que
    ir a tocar algo a mano."""

    ok: bool
    detalle: str
    permanente: bool
    estado: str = "enviado"  # enviado | encolado; compatible con dobles antiguos


def _descanso():
    # Va instalado junto a este emisor fuera del cifrado. Se carga tarde para que
    # una alerta LUKS siga saliendo aun si una actualización quedó incompleta.
    return __import__("descanso")


def enviar_respetando_descanso(token: str, chat_id: str, texto: str, ahora: datetime | None = None,
                               alerta_id: str | None = None, nivel: str | None = None) -> Envio:
    """Los urgentes siguen saliendo; lo demás queda para un único resumen."""
    momento = ahora or _ahora().astimezone()
    # Las suites normales no dependen del reloj. La reproducción de instalación
    # usa ambas variables y rutas temporales para ejercitar este camino real.
    if os.environ.get("NODO_PRUEBAS") == "1" and os.environ.get("NODO_DESCANSO_PRUEBA_REAL") != "1":
        return enviar(token, chat_id, texto)
    try:
        descanso = _descanso()
        if descanso.en_descanso(momento) and not descanso.es_urgente(texto, alerta_id, nivel):
            descanso.encolar(texto, momento)
            return Envio(True, "encolado por descanso", False, "encolado")
    except Exception as err:  # una actualización incompleta jamás silencia LUKS
        print(f"modo descanso no disponible ({type(err).__name__}); se envía igual", file=sys.stderr)
    return enviar(token, chat_id, texto)


def enviar_resumen_descanso(token: str, chat_id: str) -> int:
    """Lo invoca descanso-resumen.service al terminar la ventana."""
    try:
        descanso = _descanso()
    except Exception as err:
        print(f"modo descanso no disponible ({type(err).__name__})", file=sys.stderr)
        return 1
    if descanso.en_descanso(_ahora()):
        return 0
    items = descanso.sacar_resumen()
    if not items:
        return 0
    partes, actual = [], "🔕 Resumen del descanso\n"
    for item in items:
        linea = "• " + sin_secretos(item["texto"], token, chat_id) + "\n"
        if len(actual) + len(linea) > 4000 and actual:
            partes.append(actual); actual = "🔕 Resumen del descanso\n"
        actual += linea
    if actual: partes.append(actual)
    envio = Envio(True, "", False)
    for texto in partes:
        envio = enviar(token, chat_id, texto)
        if not envio.ok: break
    if not envio.ok:
        return 1
    descanso.confirmar_resumen(items)
    registrar_salud(envio, hubo_mensaje=True)
    registrar("descanso", "info", "\n".join(partes), (token, chat_id))
    return 0


# Codigos que NO se arreglan reintentando: el problema es la credencial o el
# destinatario, no el camino. 401 es token invalido o bot borrado; 403 es que el
# bot esta bloqueado o nunca recibio un /start; 404 sale con un token mal
# formado (la URL lleva el token adentro); 400 suele ser un chat_id que no
# existe. El 429 queda AFUERA a proposito —es literalmente "espera y reintenta"—
# y los 5xx tambien, porque esos son de Telegram y se pasan solos.
PERMANENTES = frozenset({400, 401, 403, 404})


def _describir(cuerpo: bytes) -> str:
    """La `description` que manda el propio Telegram ("Unauthorized", "chat not
    found"). Es el dato que hubo que sacar a mano con un getMe el 19-09."""
    try:
        datos = json.loads(cuerpo.decode("utf-8", "replace"))
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return ""
    return str(datos.get("description") or "")


def enviar(token: str, chat_id: str, texto: str) -> Envio:
    cuerpo = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": texto,
        "disable_web_page_preview": "true",
    }).encode()
    peticion = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=cuerpo,
    )
    try:
        with urllib.request.urlopen(peticion, timeout=20) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8", "replace"))
        if datos.get("ok"):
            return Envio(True, "", False)
        # 200 con ok=false no deberia pasar, pero si pasa no es de red.
        return Envio(False, sin_secretos(str(datos.get("description")
                                             or "Telegram respondio ok=false"),
                                         token, chat_id), False)
    # OJO AL ORDEN: HTTPError hereda de URLError y de OSError. Si se atrapa
    # despues, un 401 cae en la rama de red y volvemos justo al bug que esto
    # arregla. Tiene que ir PRIMERO.
    except urllib.error.HTTPError as err:
        try:
            desc = _describir(err.read())
        except OSError:
            desc = ""
        detalle = f"HTTP {err.code}" + (f": {desc}" if desc else "")
        return Envio(False, sin_secretos(detalle, token, chat_id), err.code in PERMANENTES)
    except http.client.InvalidURL as err:
        # Un token con espacios o caracteres de control: http.client rechaza la URL
        # antes de salir a la red y la cita ENTERA, token incluido. No hereda de
        # OSError, asi que sin esta rama terminaba en un traceback. Es permanente
        # igual que el 404 del token mal formado: reintentar no lo arregla.
        return Envio(False, sin_secretos(f"URL invalida: {err}", token, chat_id), True)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as err:
        return Envio(False, sin_secretos(f"error de red: {err}", token, chat_id), False)


def registrar_salud(envio: Envio, hubo_mensaje: bool) -> None:
    """Deja constancia de si este emisor sigue vivo. Lo lee estado.py.

    `ultimo_ciclo` se toca en TODA corrida, incluidas las que no tenian nada que
    mandar. Esa es la parte que permite detectar un timer detenido: el silencio
    es normal —doctrina 3—, asi que "hace horas que no manda nada" no prueba
    nada, y "hace horas que no COMPLETA un ciclo" si.
    """
    ahora = time.time()
    previo = leer_json(SALUD) or {}
    datos = {
        "ultimo_ciclo": ahora,
        "ultimo_ok": ahora if envio.ok else previo.get("ultimo_ok"),
        "ultimo_envio": (ahora if (envio.ok and hubo_mensaje)
                         else previo.get("ultimo_envio")),
        # Fuera del cifrado: limpio aunque `enviar` ya lo haya limpiado (doctrina 10).
        "ultimo_error": None if envio.ok else sin_secretos(str(envio.detalle)),
        "permanente": bool(not envio.ok and envio.permanente),
    }
    try:
        SALUD.parent.mkdir(parents=True, exist_ok=True)
        SALUD.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    except OSError as err:
        # Que no se pueda registrar la salud NO puede voltear el envio, que es el
        # trabajo real. Se avisa por el log y se sigue.
        print(f"no se pudo escribir {SALUD}: {err}", file=sys.stderr)


def leer_json(ruta: Path) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ----------------------------------------------------------- registro unico

_SECRETOS = (
    # Sin \b al inicio: en la URL el token va pegado a «bot» (…/bot123456:AA…/sendMessage).
    (re.compile(r"(?<!\d)\d{6,}:[A-Za-z0-9_-]{30,}"), "[token]"),
    (re.compile(r"(?i)\b(chat_?id\s*[=:]\s*)-?\d+"), r"\1[oculto]"),
    (re.compile(r"(?i)((?:token|key|secret|password|passwd|api)[\w-]*\s*[=:]\s*)\S+"),
     r"\1[oculto]"),
)


def sin_secretos(texto: str, *exactos: str) -> str:
    """El texto sin el token ni el CHAT_ID: ni los de este emisor (`exactos`), ni
    nada con forma de token que venga dentro de una alerta."""
    for valor in exactos:
        if valor:
            texto = texto.replace(str(valor), "[oculto]")
    for patron, cambio in _SECRETOS:
        texto = patron.sub(cambio, texto)
    return texto


def _abrir_carpeta(carpeta: Path) -> int:
    """fd de `carpeta` recorriendola desde / con O_NOFOLLOW en CADA componente (misma
    regla que _dir_seguro de aplicar-propuesta.py): root no sigue un symlink puesto
    por la cuenta sin privilegios en ninguna parte del camino."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for parte in [p for p in str(carpeta).split("/") if p]:
            if parte in (".", ".."):
                raise OSError(f"ruta con {parte!r}: {carpeta}")
            sig = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = sig
        return fd
    except BaseException:
        os.close(fd)
        raise


def _agregar(ruta: Path, cuerpo: str, crear: bool, uid_dueno: int) -> bool:
    """Agrega al final de `ruta` solo si es un archivo regular, con un solo nombre y de
    `uid_dueno`, abierto sin seguir symlinks. Si no cumple, no escribe y lo deja en el
    log (stderr). Que no exista (volumen cerrado) no es un fallo y no dice nada."""
    try:
        dfd = _abrir_carpeta(ruta.parent)
    except FileNotFoundError:
        return False
    except OSError as err:
        print(f"no escribo en {ruta}: {err}", file=sys.stderr)
        return False
    try:
        # O_NONBLOCK: un FIFO puesto en su lugar no debe dejar a root esperando un lector
        # (sin lector el open falla con ENXIO; con lector lo rechaza S_ISREG de abajo).
        fd = os.open(ruta.name, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK
                     | (os.O_CREAT if crear else 0), 0o644, dir_fd=dfd)
    except FileNotFoundError:
        return False
    except OSError as err:
        print(f"no escribo en {ruta}: {err}", file=sys.stderr)
        return False
    finally:
        os.close(dfd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != uid_dueno:
            print(f"no escribo en {ruta}: no es un archivo comun, tiene otros enlaces "
                  f"o no es del dueno esperado (uid {uid_dueno})", file=sys.stderr)
            return False
        if crear:
            os.fchmod(fd, 0o644)   # la unidad corre con UMask=0077 y la pestaña lo lee
        os.write(fd, cuerpo.encode("utf-8"))
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def _escribir_registro(cuerpo: str) -> bool:
    try:
        uid = pwd.getpwnam(DUENO_REGISTRO).pw_uid
    except KeyError:
        print(f"no escribo en {REGISTRO}: no existe el usuario {DUENO_REGISTRO}", file=sys.stderr)
        return False
    return _agregar(REGISTRO, cuerpo, crear=False, uid_dueno=uid)


def _escribir_pendiente(cuerpo: str) -> bool:
    return _agregar(REGISTRO_PENDIENTE, cuerpo, crear=True, uid_dueno=os.geteuid())


def volcar_pendientes() -> None:
    """Pasa al registro lo que quedo afuera esperando. Si no puede, lo deja donde esta."""
    try:
        crudo = REGISTRO_PENDIENTE.read_text(encoding="utf-8")
    except OSError:
        return
    if not crudo.strip():
        return
    if _escribir_registro(crudo if crudo.endswith("\n") else crudo + "\n"):
        try:
            REGISTRO_PENDIENTE.unlink()
        except OSError as err:
            print(f"no se pudo vaciar {REGISTRO_PENDIENTE}: {err}", file=sys.stderr)


def registrar(origen: str, nivel: str, texto: str, secretos: tuple[str, ...] = ()) -> None:
    """Una linea por aviso ENVIADO. Nunca lanza y nunca cambia el resultado del
    ciclo: el trabajo real es avisar, y ya se hizo cuando se llega aca."""
    try:
        linea = json.dumps({
            "momento": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "origen": origen, "nivel": nivel,
            "texto": sin_secretos(texto, *secretos)[:4000],
            "linea": None, "id": None, "estado": None,
        }, ensure_ascii=False) + "\n"
        volcar_pendientes()   # primero lo viejo, para que el registro quede en orden
        if REGISTRO_PENDIENTE.exists() or not _escribir_registro(linea):
            if not _escribir_pendiente(linea):
                print(f"no se pudo registrar el aviso ni en {REGISTRO} ni en "
                      f"{REGISTRO_PENDIENTE}", file=sys.stderr)
                return
            lineas = REGISTRO_PENDIENTE.read_text(encoding="utf-8").splitlines()
            if len(lineas) > MAX_PENDIENTES:
                REGISTRO_PENDIENTE.write_text(
                    "\n".join(lineas[-MAX_PENDIENTES:]) + "\n", encoding="utf-8")
    except Exception as err:  # noqa: BLE001 — ver docstring
        print(f"no se pudo registrar el aviso: {type(err).__name__}: {err}", file=sys.stderr)


# ----------------------------------------------------------- alarma de cuota

def _fecha(iso) -> datetime | None:
    try:
        f = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    return f if f.tzinfo else f.astimezone()


def _registro_cuentas() -> dict:
    try:
        import tomllib
        datos = tomllib.loads(CUENTAS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — sin cuentas.toml quedan los topes por defecto
        return {}
    return datos if isinstance(datos, dict) else {}


def cuotas_cruzadas(ahora: datetime) -> list[dict]:
    """Las ventanas ABIERTAS que ya pasaron su «tope − 5»: [{clave, renueva, texto}].

    Una ventana cuyo `renueva` ya paso no cuenta: ese porcentaje es de la ventana
    anterior y uso.json todavia no se entero.
    """
    uso = leer_json(USO)
    cuentas = uso.get("cuentas_interactivo") if isinstance(uso, dict) else None
    if not isinstance(cuentas, dict):
        return []
    registro = _registro_cuentas()
    cruzadas = []
    for cid in sorted(cuentas):
        limites = cuentas[cid].get("limites") if isinstance(cuentas[cid], dict) else None
        if not isinstance(limites, dict):
            continue
        ficha = registro.get(cid) if isinstance(registro.get(cid), dict) else {}
        for ventana, campo, defecto, nombre in (
                ("semanal", "umbral_semanal", TOPE_SEMANAL, "semanal"),
                ("ventana_5h", "umbral_5h", TOPE_5H, "de la ventana de 5 h")):
            dato = limites.get(ventana)
            if not isinstance(dato, dict):
                continue
            pct, renueva = dato.get("usado_pct"), _fecha(dato.get("renueva"))
            if (isinstance(pct, bool) or not isinstance(pct, (int, float))
                    or renueva is None or renueva <= ahora):
                continue
            tope = ficha.get(campo)
            if isinstance(tope, bool) or not isinstance(tope, int) or not 1 <= tope <= 100:
                tope = defecto
            umbral = tope - MARGEN_CUOTA
            if pct < umbral:
                continue
            cruzadas.append({
                "clave": f"{cid}:{ventana}", "renueva": renueva,
                "texto": f"{ficha.get('nombre') or cid} llegó al {pct:.0f} % {nombre} "
                         f"(aviso al {umbral} %). Desde el {tope} % las colas esperan o se "
                         f"pausan. Se renueva el {renueva.astimezone():%d-%m a las %H:%M}.",
            })
    return cruzadas


def _ya_avisada(guardado, renueva: datetime, ahora: datetime) -> bool:
    """True si esa ventana ya tuvo su aviso. Se compara por la fecha de renovacion
    guardada: mientras no pase, es la misma ventana, diga lo que diga la lectura
    de ahora. Si el proveedor reinicia el limite antes de tiempo, el aviso de la
    ventana nueva sale recien cuando pasa esa fecha: se prefiere avisar tarde a
    avisar dos veces."""
    vista = _fecha(guardado)
    return vista is not None and (
        ahora < vista or renueva <= vista + timedelta(seconds=MISMA_VENTANA_S))


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def avisar_cuota(token: str, chat_id: str) -> int:
    ahora = _ahora()
    previo = leer_json(CUOTA_VISTA)
    vistas = previo if isinstance(previo, dict) else {}
    nuevas = [c for c in cuotas_cruzadas(ahora)
              if not _ya_avisada(vistas.get(c["clave"]), c["renueva"], ahora)]
    if not nuevas:
        return 0
    texto = "\n".join(["🟡 Cuota"] + [f"• {c['texto']}" for c in nuevas])
    envio = enviar_respetando_descanso(token, chat_id, texto, ahora)
    if envio.estado == "enviado":
        registrar_salud(envio, hubo_mensaje=True)
    if not envio.ok:
        # Doctrina 4: sin envio no se marca la ventana; se reintenta al proximo ciclo.
        print(f"no se pudo enviar la alarma de cuota ({sin_secretos(envio.detalle)}); se reintenta "
              "al proximo ciclo", file=sys.stderr)
        return 1
    vigentes = {k: v for k, v in vistas.items()
                if (_fecha(v) or ahora) > ahora}
    if envio.estado in ("enviado", "encolado"):
        vigentes.update({c["clave"]: c["renueva"].isoformat() for c in nuevas})
    CUOTA_VISTA.parent.mkdir(parents=True, exist_ok=True)
    CUOTA_VISTA.write_text(json.dumps(vigentes, ensure_ascii=False), encoding="utf-8")
    if envio.estado == "enviado": registrar("cuota", "alerta", texto, (token, chat_id))
    return 0


# ----------------------------------------------------------- bandeja de salida

def _leer_del_dueno(ruta: Path, tope: int) -> tuple[bytes | None, bool]:
    """(bytes, True) si `ruta` es un archivo comun, con un solo nombre y de dcifu004, abierto sin seguir
    symlinks. (None, True) si no existe (volumen cerrado o nada que leer). (None, False) si existe y
    no se pudo o no se debio leer: eso se publica como ok=false, no se traga."""
    try:
        uid = pwd.getpwnam(DUENO_REGISTRO).pw_uid
        dfd = _abrir_carpeta(ruta.parent)
    except FileNotFoundError:
        return None, True
    except (KeyError, OSError) as err:
        print(f"no leo {ruta}: {sin_secretos(str(err))}", file=sys.stderr)
        return None, False
    try:
        fd = os.open(ruta.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    except FileNotFoundError:
        return None, True
    except OSError as err:
        print(f"no leo {ruta}: {err}", file=sys.stderr)
        return None, False
    finally:
        os.close(dfd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != uid or st.st_size > tope:
            print(f"no leo {ruta}: no es un archivo comun, tiene otros enlaces, no es del dueno esperado "
                  f"(uid {uid}) o pesa mas de {tope} bytes", file=sys.stderr)
            return None, False
        with os.fdopen(fd, "rb", closefd=False) as fh:
            return fh.read(tope + 1), True
    except OSError as err:
        print(f"no leo {ruta}: {err}", file=sys.stderr)
        return None, False
    finally:
        os.close(fd)


def _guardar_json(ruta: Path, datos: dict, modo: int) -> bool:
    """Escribe `datos` entero o nada (temporal + os.replace en la misma carpeta) con el modo dado.
    La unidad corre con UMask=0077: el modo se fija explicito."""
    tmp = ruta.with_name(f".{ruta.name}.nuevo")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, modo)
        try:
            os.fchmod(fd, modo)
            os.write(fd, json.dumps(datos, ensure_ascii=False).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, ruta)
        return True
    except OSError as err:
        print(f"no se pudo escribir {ruta}: {err}", file=sys.stderr)
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def pendientes_bandeja(crudo: bytes, vistos: dict, ahora: float) -> list[dict]:
    """Las lineas validas de la bandeja que todavia no se tocaron: forma {id, momento, texto}, id con
    el formato que arma la cola, texto no vacio, y ni de hace mas de 24 h ni del futuro."""
    out = []
    for linea in crudo.decode("utf-8", "replace").splitlines():
        try:
            d = json.loads(linea)
            f = _fecha(d["momento"])
        except (ValueError, KeyError, TypeError):
            continue
        if (not isinstance(d, dict) or not isinstance(d.get("id"), str) or not RE_ID_BANDEJA.fullmatch(d["id"])
                or not isinstance(d.get("texto"), str) or not d["texto"].strip() or f is None
                or d["id"] in vistos or not -300 <= ahora - f.timestamp() <= BANDEJA_VIEJA_S):
            continue
        out.append({"id": d["id"], "texto": d["texto"]})
    return out


def enviar_bandeja(token: str, chat_id: str) -> tuple[bool, int]:
    """Manda lo que la cola dejo en la bandeja (doctrina 11). Devuelve (pudo_leer, rc)."""
    crudo, leyo = _leer_del_dueno(BANDEJA, BANDEJA_MAX_BYTES)
    if crudo is None:
        return leyo, 0
    ahora = time.time()
    previo = leer_json(BANDEJA_VISTA)
    vistos = {k: v for k, v in (previo.items() if isinstance(previo, dict) else [])
              if isinstance(v, dict) and ahora - float(v.get("t") or 0) < BANDEJA_VISTA_S}
    for item in pendientes_bandeja(crudo, vistos, ahora)[:BANDEJA_POR_CICLO]:
        vistos[item["id"]] = {"estado": "intento", "t": ahora}
        if not _guardar_json(BANDEJA_VISTA, vistos, 0o600):
            return True, 1      # sin memoria no se manda: se arriesgaria duplicar
        texto = sin_secretos(item["texto"], token, chat_id)
        nivel = "error" if texto.startswith(("⛔", "💥", "❌")) else None
        envio = enviar_respetando_descanso(token, chat_id, texto, nivel=nivel)
        if not envio.ok:
            del vistos[item["id"]]     # doctrina 4: un envio que fallo no se marca y se reintenta
            _guardar_json(BANDEJA_VISTA, vistos, 0o600)
            registrar_salud(envio, hubo_mensaje=True)
            print(f"no se pudo enviar el aviso de la bandeja ({sin_secretos(envio.detalle)}); se reintenta "
                  "al proximo ciclo", file=sys.stderr)
            return True, 1
        vistos[item["id"]] = {"estado": "encolado" if envio.estado == "encolado" else "enviado", "t": ahora}
        _guardar_json(BANDEJA_VISTA, vistos, 0o600)
        if envio.estado == "enviado": registrar_salud(envio, hubo_mensaje=True)
    return True, 0


def publicar_estado_bandeja(leyo: bool) -> None:
    """Lo que mira cola-run.py para saber si este lado esta activo (doctrina 11). 0644, sin secretos."""
    _guardar_json(BANDEJA_ESTADO, {"version": BANDEJA_VERSION, "ultimo_ciclo": time.time(), "ok": bool(leyo)}, 0o644)


# ----------------------------------------------------------- aviso previo

def _colas_activas(ahora: float) -> list[dict]:
    """vivo/*.json de colas no finales y escritos hace poco. Sin carpeta (volumen cerrado) o sin
    ninguno: lista vacia, y la regla no hace nada."""
    try:
        nombres = sorted(n for n in os.listdir(VIVOS) if n.endswith(".json") and not n.startswith("."))
    except OSError:
        return []
    out = []
    for n in nombres:
        crudo, _ = _leer_del_dueno(VIVOS / n, BANDEJA_MAX_BYTES)
        try:
            v = json.loads(crudo) if crudo else None
            edad = ahora - _fecha(v["escrito"]).timestamp()
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        if (isinstance(v, dict) and v.get("estado") in ESTADOS_ACTIVOS and isinstance(v.get("nombre"), str)
                and RE_COLA.fullmatch(v["nombre"]) and edad < VIVO_FRESCO_S):
            out.append(v)
    return out


def _numero(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and 0 <= x <= 1000 else None


def previos_cruzados(ahora: datetime) -> list[dict]:
    """Las ventanas abiertas de cuentas que USA una cola activa y que ya pasaron su `aviso_*`:
    [{clave, renueva, texto}]. Sin `aviso_*` en cuentas.toml (o no menor que el tope) no hay aviso."""
    uso = leer_json(USO)
    cuentas = uso.get("cuentas_interactivo") if isinstance(uso, dict) else None
    if not isinstance(cuentas, dict):
        return []
    colas, registro = _colas_activas(ahora.timestamp()), _registro_cuentas()
    cruzadas = []
    for cid in sorted({c for v in colas for c in (v.get("cuentas_en_uso") or []) if isinstance(c, str)}):
        limites = (cuentas.get(cid) or {}).get("limites") if isinstance(cuentas.get(cid), dict) else None
        ficha = registro.get(cid) if isinstance(registro.get(cid), dict) else {}
        if not isinstance(limites, dict):
            continue
        propias = [v for v in colas if cid in (v.get("cuentas_en_uso") or [])]
        nombres = [v["nombre"] for v in propias]
        quien = f"la cola {nombres[0]} la usa" if len(nombres) == 1 else f"las colas {', '.join(nombres)} la usan"
        for ventana, campo, tope_campo, defecto, etiqueta, pct_clave in (
                ("semanal", "aviso_semanal", "umbral_semanal", TOPE_SEMANAL, "de la semana", "pct_sem"),
                ("ventana_5h", "aviso_5h", "umbral_5h", TOPE_5H, "de 5 h", "pct_5h")):
            dato = limites.get(ventana)
            if not isinstance(dato, dict):
                continue
            tope = ficha.get(tope_campo)
            if isinstance(tope, bool) or not isinstance(tope, int) or not 1 <= tope <= 100:
                tope = defecto
            aviso = ficha.get(campo)
            if isinstance(aviso, bool) or not isinstance(aviso, int) or not 1 <= aviso < tope:
                continue
            pct, renueva = dato.get("usado_pct"), _fecha(dato.get("renueva"))
            if (isinstance(pct, bool) or not isinstance(pct, (int, float))
                    or renueva is None or renueva <= ahora or pct < aviso):
                continue
            proximos = [p for v in propias for p in [(v.get("proximo_por_cuenta") or {}).get(cid)] if isinstance(p, dict)]
            pron = max((n for n in (_numero(p.get(pct_clave)) for p in proximos) if n is not None), default=None)
            sigue = renueva.astimezone()
            cuando = f"{sigue:%H:%M}" + (f" del {sigue:%d-%m}" if sigue.date() != ahora.astimezone().date() else "")
            texto = f"{ficha.get('nombre') or cid} va en {pct:.0f} % {etiqueta} y {quien}."
            if pron is not None:
                texto += (f" Su próxima fase pronostica +{pron:g} %: con más de {tope - pron:g} % la cola esperaría "
                          f"(tope {tope} %).")
            texto += f" Se renueva a las {cuando}."
            cruzadas.append({"clave": f"previo:{cid}:{ventana}", "renueva": renueva, "texto": texto})
    return cruzadas


def avisar_previo(token: str, chat_id: str) -> int:
    ahora = _ahora()
    previo = leer_json(PREVIO_VISTO)
    vistas = previo if isinstance(previo, dict) else {}
    nuevas = [c for c in previos_cruzados(ahora) if not _ya_avisada(vistas.get(c["clave"]), c["renueva"], ahora)]
    if not nuevas:
        return 0
    texto = "\n".join(["🟡 Cuota"] + [f"• {c['texto']}" for c in nuevas])
    envio = enviar_respetando_descanso(token, chat_id, texto, ahora)
    if envio.estado == "enviado": registrar_salud(envio, hubo_mensaje=True)
    if not envio.ok:
        print(f"no se pudo enviar el aviso previo de cuota ({sin_secretos(envio.detalle)}); se reintenta "
              "al proximo ciclo", file=sys.stderr)
        return 1
    vigentes = {k: v for k, v in vistas.items() if (_fecha(v) or ahora) > ahora}
    if envio.estado in ("enviado", "encolado"):
        vigentes.update({c["clave"]: c["renueva"].isoformat() for c in nuevas})
    PREVIO_VISTO.parent.mkdir(parents=True, exist_ok=True)
    PREVIO_VISTO.write_text(json.dumps(vigentes, ensure_ascii=False), encoding="utf-8")
    registrar("cuota", "alerta", texto, (token, chat_id))
    return 0


def alertas_actuales() -> tuple[list[dict], bool]:
    """Devuelve (alertas, completo). `completo` es False cuando solo se pudo
    mirar el JSON minimo, o sea cuando el volumen esta cerrado."""
    completo = leer_json(ESTADO_COMPLETO)
    if completo is not None:
        try:
            edad = time.time() - ESTADO_COMPLETO.stat().st_mtime
        except OSError:
            edad = MAX_ANTIGUEDAD_S + 1
        if edad <= MAX_ANTIGUEDAD_S:
            return list(completo.get("alertas", [])), True
        return ([{
            "id": "recolector:detenido",
            "texto": f"estado.json sin actualizar hace {edad / 60:.0f} min: "
                     "revisa estado.timer",
        }], False)

    # Sin el JSON completo: se cae al minimo, que vive fuera del cifrado.
    minimo = leer_json(ESTADO_MINIMO)
    if minimo is None:
        return ([{
            "id": "nodo:ciego",
            "texto": "no se pudo leer ningun estado del nodo; revisa "
                     "estado-nodo.timer por SSH",
        }], False)

    alertas = []
    if minimo.get("luks") != "abierto":
        alertas.append({
            "id": "luks",
            "texto": "volumen cifrado CERRADO: entra por SSH y corre "
                     "sudo abrir-datos. Hasta entonces no hay Docker, ni n8n, "
                     "ni bots, ni respaldos.",
        })
    else:
        # LUKS abierto pero sin estado.json: el recolector completo no corre.
        alertas.append({
            "id": "recolector:ausente",
            "texto": "el volumen esta abierto pero falta estado.json: revisa "
                     "estado.timer",
        })
    if minimo.get("disco_respaldo") != "presente":
        alertas.append({
            "id": "respaldo:disco",
            "texto": "disco de respaldo NO montado",
        })
    return alertas, False


def main() -> int:
    config = cargar_config()
    token, chat_id = config.get("TELEGRAM_TOKEN", ""), config.get("CHAT_ID", "")
    if not token or not chat_id:
        # Tambien es un fallo permanente, y del mismo tipo: nadie va a enterarse
        # por este canal. Se registra para que /estado pueda decirlo.
        registrar_salud(
            Envio(False, f"faltan TELEGRAM_TOKEN o CHAT_ID en {CONFIG}", True),
            hubo_mensaje=False)
        print(f"faltan TELEGRAM_TOKEN o CHAT_ID en {CONFIG}", file=sys.stderr)
        return 1

    if sys.argv[1:] == ["--resumen-descanso"]:
        return enviar_resumen_descanso(token, chat_id)

    rc = avisar_nodo(token, chat_id)
    if rc == 0:
        # Solo con el canal andando. Y nunca puede voltear el ciclo del nodo, que
        # ya se completo: una regla nueva no rompe la que avisa del volumen cerrado.
        for nombre, regla in (("la alarma de cuota", avisar_cuota), ("el aviso previo de cuota", avisar_previo)):
            try:
                rc = rc or regla(token, chat_id)
            except Exception as err:  # noqa: BLE001
                print(f"{nombre} fallo: "
                      f"{type(err).__name__}: {sin_secretos(str(err), token, chat_id)}", file=sys.stderr)
                rc = 1
    # La bandeja de las colas (doctrina 11) sale aunque el nodo tenga algo pendiente: es otro camino.
    leyo = False
    try:
        leyo, rc_bandeja = enviar_bandeja(token, chat_id)
        rc = rc or rc_bandeja
    except Exception as err:  # noqa: BLE001
        print(f"la bandeja de salida fallo: {type(err).__name__}: {sin_secretos(str(err), token, chat_id)}",
              file=sys.stderr)
        rc = 1
    publicar_estado_bandeja(leyo)
    volcar_pendientes()
    return rc


def avisar_nodo(token: str, chat_id: str) -> int:
    alertas, completo = alertas_actuales()
    ahora = {a["id"]: a["texto"] for a in alertas if a.get("id")}

    # La memoria guarda {id: texto} para poder decir QUE se resolvió y no sólo su
    # id: "Resuelto: unidades" no le sirve a nadie leyéndolo desde el celular.
    # Se acepta la lista del formato viejo para no perder el estado al actualizar.
    previo = leer_json(MEMORIA)
    vistas: dict[str, str] = {}
    if isinstance(previo, dict):
        vistas = {k: str(v) for k, v in previo.items()}
    elif isinstance(previo, list):
        vistas = {str(i): str(i) for i in previo}

    nuevas = [i for i in ahora if i not in vistas]
    resueltas = [i for i in vistas if i not in ahora]
    if not nuevas and not resueltas:
        # Ciclo completo sin nada que decir: el caso normal. Se registra igual,
        # porque es lo unico que distingue "todo bien" de "el timer murio".
        registrar_salud(Envio(True, "", False), hubo_mensaje=False)
        return 0

    lineas = []
    if nuevas:
        cabecera = "🔴 Nodo Pi5" if completo else "🔴 Nodo Pi5 (visibilidad reducida)"
        lineas.append(cabecera)
        lineas += [f"• {ahora[i]}" for i in nuevas]
    if resueltas:
        if lineas:
            lineas.append("")
        lineas.append("🟢 Resuelto:")
        lineas += [f"• {vistas.get(i, i)}" for i in resueltas]

    texto = "\n".join(lineas)
    urgente_id = next((i for i in nuevas if i in {"luks", "medidor:temp_soc"}), None)
    nivel = "error" if any(ahora[i].startswith(("⛔", "💥", "❌", "🚩")) for i in nuevas) else None
    envio = enviar_respetando_descanso(token, chat_id, texto, alerta_id=urgente_id, nivel=nivel)
    registrar_salud(envio, hubo_mensaje=envio.estado == "enviado")
    if not envio.ok:
        # Punto 4 de la doctrina: no se toca la memoria, se reintenta al
        # proximo ciclo. Es preferible avisar tarde que no avisar nunca. Eso no
        # cambia con un fallo permanente; lo que cambia es que el log deje de
        # mandar a esperar a que "vuelva la red".
        if envio.permanente:
            print(f"el token de {CONFIG} NO sirve ({sin_secretos(envio.detalle)}). Reintentar no "
                  "lo arregla: hay que regenerar el token en BotFather —o crear el "
                  f"bot de nuevo— y escribirlo en {CONFIG}. Mientras tanto el nodo "
                  "NO tiene canal de avisos; /estado lo dice desde el bot de "
                  "consultas.", file=sys.stderr)
        else:
            print(f"no se pudo enviar el aviso ({sin_secretos(envio.detalle)}); se reintenta al "
                  "proximo ciclo", file=sys.stderr)
        return 1

    MEMORIA.parent.mkdir(parents=True, exist_ok=True)
    MEMORIA.write_text(json.dumps(ahora, ensure_ascii=False), encoding="utf-8")
    if envio.estado == "enviado":
        registrar("nodo", "alerta" if nuevas else "ok", texto, (token, chat_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
