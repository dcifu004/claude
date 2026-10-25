#!/usr/bin/env python3
"""Cola nueva de encargos (doc 27, 03-10-2026). Un solo motor que lee un manifiesto TOML, en vez
de copiar un cola-NN.sh por encargo.

    python3 cola-run.py <manifiesto.toml> [--desde ETAPA:FASE] [--simular [--con-cambios]]
    python3 cola-run.py --panel
    python3 cola-run.py --accion {reanudar|pausar|detener} <cola> [--simular]
    python3 cola-run.py --despacho {abrir|pausar} [--motivo T] [--por T] [--autorizar colaNN ...]

FASE es autor, rev1, fix1, rev2, fix2 o rev3; con `plan = true` también plan, revplan, plan2 y
revplan2. Con --simular se imprime el plan y el pronóstico y no se corre nada. `--panel` y `--con-cambios` son de la pestaña «⚙️ Reparto y modelos» de
🧵 Encargos (encargo 23a): el primero imprime en JSON lo que la pestaña dibuja; el segundo simula
con una propuesta `encargos_config` todavía sin aplicar, que llega por la entrada estándar.

Qué cambia frente a las colas copiadas:
- Las cuentas se nombran por su clave de cuentas.toml (claude_cami, codex, claude_diego) y el
  prompt recibe {AUTOR} y {REVISOR}: se acaban el `sed` y el «aunque el título diga otro motor».
- Antes de CADA fase se compara el % actual + el pronóstico de la fase con el tope de la cuenta
  (cuentas.toml; 75 % semanal y 90 % de 5 h desde el 03-10). Si no alcanza: si la ventana de 5 h
  se renueva en menos de una hora, espera; si no, PAUSA y avisa con la línea para reanudar.
- Si un motor se corta por límite a mitad de fase, la fase queda SIN-CUOTA. No se gastan
  revisiones sobre código a medias (encargo 10: 457 k tokens de Codex para nada).
- Cada corrida deja una línea en encargos/historial.jsonl con minutos, tokens y % antes/después,
  al lado del pronóstico.
- Pruebas: se toma una línea base al empezar. La cola falla solo si aparecen fallas NUEVAS.
- El pedido de despliegue sale del catálogo de nodo-desplegar: conserva la foto del catálogo de la
  corrida original para que un `--desde` incluya lo ya revisado, y sólo pide archivos atribuidos a
  esta cola que aún difieren de lo instalado. Un archivo nuevo sin entrada en el catálogo detiene
  el despliegue (recetas.py, 30-09).
- La espera de cuota se ve, se avisa y se anticipa (encargo 24): `vivo/<cola>.json` pasa a
  `esperando_cuota` con el cálculo («5 h 74 % + 25 % > tope 90 %»), la hora en que sigue y la ETA corrida
  por la espera; late cada 5 min y vuelve a medir cada 10. Espera, pausa y fin avisan en TEXTO SIMPLE por la
  bandeja de salida (avisos.py la envía; ver `avisar_texto`). Sin 3 filas del mismo modelo el pronóstico
  usa `[factor_modelo]` de modelos.toml. `--desde` conserva `lanzada` y `fases_hechas` y deja un encabezado
  «Reanudación desde …» en la bitácora, que solo se agrega.
- Una etapa con `donde = "pc2503"` (encargo 23d) no se escribe en la Pi: va por el buzón de
  Syncthing a PC-2503 y acá solo se revisa su RESULTADO. Ver «buzón de PC-2503» más abajo y
  pc2503/BUZON.md.

Historial de versiones (encargos 33 y 53; encargos/versiones.py):
- Al empezar la cola, una foto «antes de <cola>» (queda registrado lo que cambió fuera de las colas);
  antes y después de cada fase, otra: «<cola> · <etapa> · <fase> (antes)» y «<cola> · <etapa> · <fase>».
  Sin cambios no hay commit. El repositorio vive fuera del vault (/opt/nodo/datos/git/11-Pi5.git).
- Al empezar cada revisión, el diff suma solo los tramos «antes → después» de las fases de autor y arreglo.
  Sus límites se guardan atómicamente en ~/encargos-logs/<cola>-git.json para que un `--desde` los recupere.
  Los archivos que otra cola cambió entre esos tramos se nombran aparte, sin contenido y sin revisión. Si había
  otras colas vivas al empezar una fase propia, el diff lo advierte. Al pedir el despliegue se leen sus fotos:
  todo archivo coincidente (o con foto ajena ausente o ilegible) queda compartido, se anota y no se pide solo.
- Si git falla, la cola SIGUE y lo anota en la bitácora: el historial ayuda, no bloquea.
- `arboles_extra = ["13-Agente-Noticias"]` en el manifiesto (encargo 38): carpetas HERMANAS de 11-Pi5 que la
  cola también escribe. Cada una tiene su historial al lado del principal (/opt/nodo/datos/git/<carpeta>.git),
  recibe las mismas fotos y su diff se agrega al final del diff de la etapa. Sin esa clave el diff solo ve
  11-Pi5, y lo escrito en otro proyecto no se puede revisar ni revertir. El historial de la hermana se crea
  una vez a mano (`versiones.py --repo … --arbol … init`); si falta, la cola lo anota y sigue.
  La carpeta y su historial tienen que ser directorios de verdad: un enlace simbólico, o una ruta que
  resuelva fuera de la carpeta padre, se anota y se salta (encargo 38, revisión 2).

Búsqueda web en encargos (encargos 32 y 32c):
- Solo el autor de una etapa `investigacion` puede buscar, con `python3 encargos/buscar-web.py "consulta"`
  (Tavily), y la búsqueda la hace ESTA cola, no el autor (32c). `correr()` abre para las fases de autor
  (autor, fixN) de una etapa `investigacion` un buzón nuevo en vivo/buzon/<al azar>/ (0700), pasa su ruta
  en ENCARGO_BUZON y levanta un hilo (`BuzonBusquedas`) que atiende cada `pedido-<id>.json` con `atender()`
  de buscar-web.py y deja `respuesta-<id>.json`. Al terminar la fase para el hilo, contesta «fase
  terminada» a lo pendiente y borra la carpeta. Revisores y otras naturalezas no reciben buzón.
- La atribución sale de la memoria de esta cola: el encargo y la fase de esa llamada a `correr()`. Lo que
  diga el pedido se ignora, y ENCARGO_NATURALEZA/ENCARGO_ID son solo información: no autorizan nada.
- Solo sale la pregunta pública. El muro del script (rutas, nombres propios y laborales, secretos, datos
  personales, 400 caracteres) rechaza con exit 3 antes de abrir la conexión. Salidas: 0 bien, 2 uso o
  configuración, 3 muro, 4 tope, 5 error de Tavily.
- Cada pedido queda en encargos/<ID>-busquedas.jsonl (nunca la key) con `via: cola`, el nombre de la cola y
  la fase; la revisión lo lee entero y una consulta con contenido del vault es un hallazgo grave.
- Tope: `busquedas_max_encargo` en [tavily] de cuentas.toml (30 por defecto y techo del código). Se cuenta
  bajo flock y se mantiene durante la llamada: no se supera con pedidos simultáneos.
- La carpeta del registro, la key y el tope NO se cambian por entorno. `--manual` (el usuario, fuera de la
  cola) se niega mientras viva cualquier cola-run.py, así que una búsqueda manual hecha con la cola
  detenida va a manual-busquedas.jsonl y una con la cola viva no existe.
- Un solo usuario Unix para la cola y el autor es un límite ACEPTADO por el usuario (09-10-2026). Está
  escrito en un solo lugar: el bloque «Límite aceptado» del docstring de buscar-web.py.

Matriz de cuota (encargo 46a):
- Cada cola publica en su vivo/<cola>.json `fases_restantes`: todas las fases que le faltan, con el pronóstico
  de `pronostico()`, la probabilidad de llegar a cada una (`prob`, la ponderación de la ETA esperada) y su
  `inicio_esperado`. También mientras espera a otra cola (se encadena con el fin esperado de esa otra y se
  refresca en cada vuelta de la espera), mientras espera cuota y antes de su primera fase.
- `--panel` SUMA por cuenta lo que falta de las colas que van a correr solas (la viva, la que espera a otra y
  la pausada por cuota con reanudación programada), separado por ventana: lo que parte después de la
  renovación de 5 h va a `proxima_5h` y lo que parte después de la renovación semanal no suma a la semana.
  Las demás (detenida, pausada sin timer, en candado…) salen en `colas_fuera` con sus fases, sin sumar.
- La matriz informa; no frena colas. La pausa de cada fase sigue siendo `chequear_cuota` sobre la fase propia.

Botones de 🧵 Encargos (encargo 46c): `--accion {reanudar|pausar|detener} <cola>`, sin sudo y sin root.
- `<cola>` es un nombre (`cola46`), nunca una ruta: tiene que calzar entero con `cola`, dos dígitos y letras
  minúsculas o dígitos, y tener un manifiesto `cola-*.toml` con ese `nombre` dentro de encargos/.
- reanudar: solo una cola sin sesión que quedó pausada por cuota, `pausada_por_usuario` o detenida con un
  `--desde` en su vivo (o sin señal hace 2 h, que el panel también llama detenida). Lanza la misma línea
  `relanzar` que manda la pausa, con el `--desde` que dejó el vivo. Con la sesión `=<cola>` viva se niega.
- pausar: deja la marca `vivo/<cola>.pausar` (creación exclusiva). `etapa()` la mira antes de cada fase y al
  salir de una espera de cuota: la fase en curso termina, la siguiente no empieza, y la cola queda en
  `pausada_por_usuario` con el `--desde` de esa fase siguiente. La marca se borra al atenderla y al terminar.
- detener: `tmux kill-session -t =<cola>` y, DESPUÉS, `detenida` en el vivo con el `--desde` de la fase
  cortada y una línea en la bitácora. Vuelve a leer la sesión y el vivo y eso es lo que informa.
- Con `--simular` no escribe nada (ni marca, ni registro, ni vivo): `reanudar` imprime la carga proyectada
  en JSON, que es lo que la página muestra antes de confirmar.
- Cada acción de verdad deja una línea en `vivo/acciones.jsonl` (0600) y corre entera bajo su `flock`: dos
  clics a la vez no lanzan dos veces. La salida es siempre un JSON de una línea; código 0 si se hizo.
- `--panel` publica en `colas` qué botones valen para cada cola y los timers de usuario que la nombran. Los
  timers no se accionan desde acá: eso es de ⏰ Programados.

Despacho y mirada de pasado (encargo 50a):
- `vivo/despacho.json` (0600) dice si el despacho está abierto o en pausa:
  `{estado: "abierto"|"pausa", desde, motivo, autorizadas: [colas], por}`. Si falta, está abierto. Si no se
  puede leer (JSON a medias, otra forma, un enlace), también se trata como abierto y queda un aviso.
- Se cambia solo con `--despacho {abrir|pausar}`: valida los nombres de `--autorizar` con el patrón de
  `--accion`, corre bajo el `flock` de `vivo/acciones.jsonl`, reemplaza el archivo de forma atómica (`.tmp`
  propio + `rename`) y deja su línea en ese registro. `pausar` sobre una pausa conserva `desde` y suma las
  autorizadas; `abrir` las borra. La salida es un JSON de una línea; código 0 si se hizo.
- Al arrancar (también con `--desde`), una cola que no está en `autorizadas` se niega a correr con el
  despacho en pausa: deja `retenida_por_despacho` en su vivo, con `reanuda_desde`, avisa y sale con código 5
  antes de pedir autorizaciones, esperar a otra cola o correr una fase. `--simular` y `--panel` no lo miran.
- `--accion reanudar <cola>` con el despacho en pausa se niega si la cola no está autorizada; con
  `--autorizar <cola>` (la confirmación extra de la página) la agrega a `autorizadas` y la lanza. Una cola
  `retenida_por_despacho` se reanuda igual que una pausada por el usuario.
- `--panel` publica `despacho` (el estado y, si el archivo no se pudo leer, `aviso`) y `pasado`: lo que
  calcula encargos/balance.py (`datos()`, lo mismo que su `--json`) sobre el historial.
"""
from __future__ import annotations

import argparse
import fcntl
import fnmatch
import glob
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import stat
import statistics
import subprocess
import sys
import threading
import time
import tomllib
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

VAULT = Path("/opt/nodo/datos/srv/vault_personal")
D = VAULT / "10-Proyectos/11-Pi5"
E = D / "encargos"
L = Path.home() / "encargos-logs"
ESTADO = E / "COLA-ESTADO.md"
HISTORIAL = E / "historial.jsonl"
USO = Path("/opt/nodo/datos/uso.json")
REGISTROS = (Path("/opt/botv3/cuentas.toml"), D / "botv3/cuentas.toml")
PLANTILLA_REV = E / "revision-plantilla-v2.md"
MODELOS = E / "modelos.toml"
TOPE_SEM, TOPE_5H = 75, 90  # si cuentas.toml no dice nada
HERRAMIENTAS = "Read,Grep,Glob,Write,Edit,Bash"
# Buzón de PC-2503 (encargo 23d): una carpeta de Syncthing compartida solo con ese equipo.
BUZON = Path("/opt/nodo/datos/srv/encargos-buzon")
VAULT_TRABAJO = Path("/opt/nodo/datos/srv/vault_trabajo")
PLANTILLA_REV_PC2503 = E / "revision-plantilla-pc2503.md"
HERRAMIENTAS_REV_PC2503 = "Read,Grep,Glob,Write"   # revisa un informe de otro equipo: sin Bash ni Edit
BUZON_SONDEO_S = 30
TOPE_ESTADO = 256 * 1024        # un estado/<id>.json más grande no se lee
MARGEN_RELOJ_S = 600            # cuánto pueden diferir los relojes de la Pi y de PC-2503

MOTORES = {  # clave de cuentas.toml -> cómo se corre en la Pi
    "claude_cami": {"motor": "claude", "env": {"CLAUDE_CONFIG_DIR": str(Path.home() / ".config/claude-cami")}},
    "claude_diego": {"motor": "claude", "env": {}},
    "codex": {"motor": "codex", "env": {}},
}

# Pronóstico de arranque (doc 27, sección 2) para cuando el historial no tiene 3 datos.
# Los % son supuestos conservadores: hasta el 03-10 no se medía el delta de cuota.
BASE = {
    ("claude", "autor"): {"min": 12, "pct_5h": 25, "pct_sem": 5},
    ("claude", "fix"): {"min": 4, "pct_5h": 10, "pct_sem": 2},
    ("claude", "rev"): {"min": 5, "pct_5h": 10, "pct_sem": 2},
    ("codex", "autor"): {"min": 6, "pct_5h": 15, "pct_sem": 3},
    ("codex", "fix"): {"min": 7, "pct_5h": 15, "pct_sem": 3},
    ("codex", "rev"): {"min": 4, "pct_5h": 15, "pct_sem": 3},
}
BASE_PC2503 = {"min": 30, "pct_5h": 0, "pct_sem": 0}   # doc 27, 5.6: un encargo laboral dura 15 a 45 min
LIMITE = re.compile(r"hit your (session|usage|weekly) limit|usage limit|rate.?limit(ed)? reached"
                    r"|limit reached|try again (at|in)", re.I)
FALLA = re.compile(r"^(FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)
VEREDICTO_OK = re.compile(r"^ *VEREDICTO: DESPLEGABLE *$", re.M)
# Encargo 87: cierre barato de la rev2/rev3 (`cierre_barato = true` en la etapa). La decisión sale de las fotos
# git del último arreglo; cualquier duda corre la revisión completa.
PLANTILLA_CIERRE = E / "revision-cierre-plantilla.md"
RUTAS_SENSIBLES = ("*.service", "*.path", "*.timer", "*sudoers*", "*nodo-desplegar*", "secretos/*", "*/secretos/*",
                   "encargos/cola-run.py", "encargos/revision-plantilla*", "encargos/revision-*plantilla*",
                   "encargos/modelos.toml", "botv3/cuentas.toml")
CIERRE_MAX_LINEAS = 150         # agregadas + borradas del arreglo (git diff --numstat)
CIERRE_MAX_MIN = 30             # un cierre que pasa de esto se corta y se escala (falla cerrada)
CIERRE_MAX_BYTES = 512 * 1024   # 87b: un informe que el cierre lee (o pega en su prompt) no pasa de esto
VEREDICTO_CIERRE = re.compile(r"VEREDICTO: (DESPLEGABLE|NO DESPLEGABLE|ESCALAR)")   # con fullmatch, sin espacios


class Pausa(Exception):
    def __init__(self, motivo: str, desde: str):
        super().__init__(motivo)
        self.motivo, self.desde = motivo, desde


# ---------------------------------------------------------------- utilidades

def ahora() -> datetime:
    return datetime.now(timezone.utc).astimezone()


DORMIR = time.sleep
_DESCANSO_MOD = None


def _descanso():
    """Carga la misma biblioteca que usa avisos.py, sin duplicar el horario."""
    global _DESCANSO_MOD
    if _DESCANSO_MOD is None:
        spec = importlib.util.spec_from_file_location("descanso", Path(__file__).resolve().parents[1] / "pi" / "descanso.py")
        _DESCANSO_MOD = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(_DESCANSO_MOD)
    return _DESCANSO_MOD


def posponer_si_descanso(estado: str = "esperando autorización") -> None:
    momento = ahora()
    # Falla abierto, como el emisor: si el descanso no se puede consultar, la cola sigue y lo anota.
    try:
        descanso = _descanso()
        nocturno = descanso.en_descanso(momento)
        fin = descanso.fin_descanso(momento) if nocturno else None
    except Exception as e:
        log(f"⚠️ modo descanso no disponible ({type(e).__name__}); la cola sigue")
        return
    if nocturno:
        segundos = max(0.0, (fin - momento).total_seconds())
        if os.environ.get("NODO_PRUEBAS") == "1":
            return
        log(f"🔕 Acción pospuesta por descanso hasta {fin:%d-%m %H:%M}")
        # Las suites nunca esperan ni escriben la bitácora real; en vivo renueva
        # la señal cada minuto para que una espera nocturna no parezca caída.
        while segundos > 0:
            tramo = min(60.0, segundos)
            vivo(estado=estado, espera_descanso_hasta=fin.isoformat())
            DORMIR(tramo)
            segundos -= tramo


SIMULANDO = False   # --simular y --panel: solo imprimen; ni bitácora, ni avisos, ni vivo/ (23h)


def log(texto: str) -> None:
    linea = f"- {ahora():%d-%m %H:%M} · {texto}"
    print(linea, flush=True)
    if SIMULANDO:
        return
    with ESTADO.open("a", encoding="utf-8") as fh:
        fh.write(linea + "\n")


_RA_MOD = None


def registrar_aviso(texto: str, linea: str | None, p: subprocess.CompletedProcess) -> None:
    """Deja el aviso en el registro único (encargo 23b; encargos/registro_avisos.py), con el id
    que devolvió nodo-desplegar. No cambia cómo se envía y nunca detiene la cola."""
    try:
        ra = _ra()
        ra.registrar("cola", texto, linea, ra.id_de(p.stdout or ""), None if p.returncode == 0 else "no enviado")
    except Exception as e:  # el registro es secundario: el aviso ya salió
        print(f"⚠️ no se pudo registrar el aviso ({type(e).__name__}: {e})", flush=True)


def avisar(motivo: str, linea: str, aplazar_por_descanso: bool = False) -> None:
    if SIMULANDO:
        return
    # Un agente de una cola recibe NODO_PRUEBAS=1. Sus rutas y el log son los de producción,
    # por lo que no puede caer al aviso con botón de nodo-desplegar si la bandeja se descarta.
    # Las suites reemplazan L por un temporal y conservan la cobertura del camino normal.
    if os.environ.get("NODO_PRUEBAS") == "1" and L == Path.home() / "encargos-logs":
        return
    # Sólo una línea que instala o pide algo requiere atención del usuario. Los
    # avisos informativos (incluido el respaldo de avisar_texto) no detienen la
    # cola ni cambian el estado que ésta ya está publicando.
    if aplazar_por_descanso:
        posponer_si_descanso("desplegando")
    with (L / "avisos.log").open("a", encoding="utf-8") as fh:
        p = subprocess.run(["nodo-desplegar", "sugerir", "--motivo", motivo, "--", linea],
                           capture_output=True, text=True)
        fh.write(p.stdout + p.stderr)
    registrar_aviso(motivo, linea, p)


def _ra():
    """encargos/registro_avisos.py (el registro único, la bandeja de salida y su estado)."""
    global _RA_MOD
    if _RA_MOD is None:
        spec = importlib.util.spec_from_file_location(
            "registro_avisos", Path(__file__).resolve().parent / "registro_avisos.py")
        _RA_MOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_RA_MOD)
    return _RA_MOD


def avisar_texto(texto: str, linea: str | None = None, viejo: tuple[str, str] | None = None) -> None:
    """Aviso de espera, pausa o fin (encargo 24): TEXTO SIMPLE, sin línea de comando en el mensaje.
    Información no es una tarea, y `nodo-desplegar sugerir` lo manda como «comando para copiar».
    - Con el lado nuevo de avisos.py activo (`bandeja_activa()`): una línea en el registro único
      —con `linea` si hay algo que copiar, que nunca va en el mensaje— y una en la bandeja de salida,
      que avisos.py envía a Telegram en su próximo ciclo (hasta 10 min).
    - Si no está activo, o la bandeja no se pudo escribir: `avisar()` de siempre con `viejo`
      (motivo, línea); nada queda sin aviso. Cada aviso sale por UN solo camino: por eso el
      registro se escribe después de que la bandeja lo aceptó."""
    if SIMULANDO:
        return
    ra = _ra()
    if ra.bandeja_activa() and ra.a_la_bandeja(texto):
        ra.registrar("cola", texto, linea)
        return
    if os.environ.get("NODO_PRUEBAS") == "1" and L == Path.home() / "encargos-logs":
        return
    avisar(*(viejo or (texto, f"cat {ESTADO}")))


def sha(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def sha_dir(p: Path) -> str | None:
    if not p.is_dir():
        return None
    h = hashlib.sha256()
    for f in sorted(x for x in p.rglob("*") if x.is_file()):
        h.update(str(f.relative_to(p)).encode() + b"\0" + f.read_bytes())
    return h.hexdigest()[:12]


def registro() -> dict:
    for r in REGISTROS:
        try:
            return tomllib.loads(r.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
    return {}


def nombre(cid: str) -> str:
    return (registro().get(cid) or {}).get("nombre") or cid


def quema(cid: str, u: dict | None = None, momento: datetime | None = None) -> dict:
    """Estado de la regla temporal que sube sólo el tope semanal de encargos."""
    r = registro().get(cid) or {}
    ok = lambda x: isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 100
    horas = r.get("quemar_horas")
    if not isinstance(horas, int) or isinstance(horas, bool) or not 0 <= horas <= 48 or horas == 0:
        return {"activa": False, "hasta": None, "debil": False}
    renueva = (u or {}).get("renueva_sem")
    momento = momento or ahora()
    if not isinstance(renueva, datetime) or renueva <= momento or not ok(r.get("quemar_tope")):
        return {"activa": False, "hasta": renueva if isinstance(renueva, datetime) else None, "debil": True}
    return {"activa": renueva - timedelta(hours=horas) <= momento < renueva,
            "hasta": renueva, "debil": False}


def topes(cid: str, u: dict | None = None, momento: datetime | None = None) -> tuple[int, int]:
    r = registro().get(cid) or {}
    ok = lambda x: isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 100
    sem = r.get("tope_encargos_semanal") if ok(r.get("tope_encargos_semanal")) else r.get("umbral_semanal")
    h5 = r.get("tope_encargos_5h") if ok(r.get("tope_encargos_5h")) else r.get("umbral_5h")
    if quema(cid, u, momento)["activa"]:
        sem = r["quemar_tope"]
    return (sem if ok(sem) else TOPE_SEM, h5 if ok(h5) else TOPE_5H)


def uso(cid: str, ruta: Path | None = None, momento: datetime | None = None) -> dict:
    """Lo que dice uso.json (se refresca cada 15 min). Solo de respaldo: ver medir().
    `ruta` y `momento` son para la matriz de cuota y sus pruebas (otro archivo, otra hora de corte)."""
    try:
        d = json.loads((ruta or USO).read_text(encoding="utf-8"))["cuentas_interactivo"][cid]["limites"]
    except (OSError, KeyError, TypeError, ValueError):
        return {"5h": None, "sem": None, "renueva_5h": None, "renueva_sem": None, "momento": None, "fuente": "sin dato"}
    return dict(_normalizar(d, momento), fuente="uso.json")


_USO_MOD = None


def _uso_mod():
    """pi/uso.py del vault: se reusan sus lectores para no tener una segunda versión."""
    global _USO_MOD
    if _USO_MOD is None:
        spec = importlib.util.spec_from_file_location("uso_nodo", D / "pi/uso.py")
        _USO_MOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_USO_MOD)
    return _USO_MOD


def medir(cid: str) -> dict:
    """% de cuota AHORA, sin esperar el timer de uso.json (03-10: con el refresco de 15 min,
    5 de las 6 primeras corridas anotaron el mismo % antes y después).
    - Claude: `claude -p /usage` refresca la caché del CLI (USD 0, ~2-4 s) y se lee con el mismo
      normalizador que usa `uso`.
    - Codex: el último `rate_limits` del rollout más nuevo; cada `codex exec` deja el suyo.
    Si algo falla, cae a uso.json y lo deja dicho en `fuente`."""
    try:
        u = _uso_mod()
        if MOTORES[cid]["motor"] == "claude":
            cfg = u.CLAUDE_LIMITES[cid]
            env = dict(os.environ, **MOTORES[cid]["env"])
            subprocess.run(["claude", "-p", "/usage", "--no-session-persistence", "--output-format", "json"],
                           env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=40, check=False)
            lim = u.limites_claude_cache(u._leer_json(cfg["archivo"]))
        else:
            rollouts = sorted((f for d in u.CODEX_SESIONES
                               for f in glob.glob(os.path.join(d, "**", "rollout-*.jsonl"), recursive=True)),
                              key=os.path.getmtime)
            lim = None
            for ruta in reversed(rollouts[-3:]):
                for ln in open(ruta, encoding="utf-8", errors="replace"):
                    if '"rate_limits"' not in ln:
                        continue
                    try:
                        d = json.loads(ln)
                        rl = (d.get("payload") or {}).get("rate_limits")
                        if isinstance(rl, dict):
                            momento = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).astimezone(u.TZ)
                            lim = u._limites_codex(rl, momento)
                    except (ValueError, KeyError, TypeError):
                        continue
                if lim:
                    break
        if lim and isinstance(lim.get("semanal"), dict):
            return dict(_normalizar(lim), fuente="fresco")
    except Exception as e:  # nunca frena la cola: cae al respaldo
        log(f"⚠️ medición fresca de {nombre(cid)} falló ({type(e).__name__}); se usa uso.json")
    return uso(cid)


def _normalizar(d: dict, momento: datetime | None = None) -> dict:
    """{'5h', 'sem', 'renueva_5h', 'renueva_sem', 'momento'} desde la forma de límites de uso.py."""
    def pct(k):
        v = d.get(k) or {}
        ren = None
        try:
            ren = datetime.fromisoformat(str(v.get("renueva")))
            if ren < (momento or datetime.now(timezone.utc)):
                return 0.0, None  # la ventana ya se renovó: el dato es viejo
        except ValueError:
            pass
        p = v.get("usado_pct")
        return (float(p) if isinstance(p, (int, float)) else None), ren

    p5, ren5 = pct("ventana_5h")
    psem, rensem = pct("semanal")
    if p5 is None and (d.get("ventana_5h") or {}).get("renueva") is None:
        p5 = 0.0  # sin ventana abierta
    return {"5h": p5, "sem": psem, "renueva_5h": ren5, "renueva_sem": rensem, "momento": d.get("momento")}


def historial() -> list[dict]:
    try:
        filas = []
        for x in HISTORIAL.read_text(encoding="utf-8").splitlines():
            try:
                fila = json.loads(x)
            except json.JSONDecodeError:
                continue
            if isinstance(fila, dict):
                filas.append(fila)
        return filas
    except OSError:
        return []


def modelo_de(et: dict, rol: str) -> dict:
    """{'modelo', 'esfuerzo', 'nivel'} para el rol (autor/rev/fix) de la etapa. Vacío = default
    del CLI. Orden: lo fijado en la etapa, la naturaleza en modelos.toml, nada. Un `esfuerzo_<rol>`
    sin `modelo_<rol>` solo cambia el esfuerzo: el modelo y el nivel siguen siendo los de la
    naturaleza (encargo 48)."""
    cid = et["revisor"] if rol in ("rev", "cierre") else et["autor"]
    motor = MOTORES[cid]["motor"]
    if et.get(f"modelo_{rol}"):
        return {"modelo": et[f"modelo_{rol}"], "esfuerzo": et.get(f"esfuerzo_{rol}", ""), "nivel": "fijado"}
    declarado = et.get(f"esfuerzo_{rol}")
    cfg = _cfg_modelos()
    # El cierre (encargo 87) va siempre al nivel `agil` del revisor, no al de la naturaleza.
    nivel = "agil" if rol == "cierre" else ((cfg.get("naturaleza") or {}).get(et.get("naturaleza", "")) or {}).get(rol)
    elegido = ((cfg.get("niveles") or {}).get(motor) or {}).get(nivel or "")
    if not elegido:
        return {"modelo": "", "esfuerzo": declarado or "", "nivel": "default del CLI"}
    return {"modelo": elegido.get("modelo", ""), "esfuerzo": declarado or elegido.get("esfuerzo", ""), "nivel": nivel}


CFG_SIMULADA: dict | None = None   # solo con --simular --con-cambios: nunca en una cola real


def _cfg_modelos() -> dict:
    if CFG_SIMULADA is not None:
        return CFG_SIMULADA
    # Sin archivo: sin configuracion (como antes). Un archivo que existe pero esta vacio o no
    # parsea NO es "sin configuracion": una fase correria con el default del CLI sin que nadie lo
    # haya decidido. Se reintenta un instante (una escritura en curso) y despues se detiene la cola.
    ultimo = None
    for intento in range(5):
        try:
            texto = MODELOS.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as e:
            ultimo = e
        else:
            try:
                if texto.strip():
                    return tomllib.loads(texto)
                ultimo = ValueError("esta vacio")
            except tomllib.TOMLDecodeError as e:
                ultimo = e
        time.sleep(0.05 * (intento + 1))
    raise RuntimeError(f"{MODELOS} no se puede leer ({ultimo}); no corro con el modelo por defecto")


def repartir(etapas: list[dict]) -> None:
    """Completa el `autor` o el `revisor` que le falte a una etapa con la sugerencia de
    [reparto.<naturaleza>] de modelos.toml (doc 27, 5.7; encargo 23a). Una etapa que ya trae los
    dos queda como está. El reparto sugerido nunca deja autor igual a revisor: esa excepción solo
    existe escrita en el manifiesto, con los dos nombres y `autorrevision`."""
    reparto = _cfg_modelos().get("reparto") or {}
    for et in etapas:
        nat = et.get("naturaleza") or ""
        sugerido = reparto.get(nat) if isinstance(reparto.get(nat), dict) else {}
        faltan = [k for k in ("autor", "revisor") if not et.get(k)]
        for k in faltan:
            if sugerido.get(k) not in MOTORES:
                raise ValueError(f"etapa {et.get('id', '?')}: el manifiesto no trae `{k}` y modelos.toml no "
                                 f"lo sugiere en [reparto.{nat or '(sin naturaleza)'}]")
            et[k] = sugerido[k]
        if faltan and et["autor"] == et["revisor"]:
            raise ValueError(f"etapa {et.get('id', '?')}: con el reparto de [reparto.{nat}] autor y revisor "
                             f"serían la misma cuenta ({et['autor']}); el reparto sugerido nunca lo acepta")
        if faltan:
            et["reparto_sugerido"] = faltan


_AP_MOD = None


def _ap_mod():
    """pi/aplicar-propuesta.py del vault: de ahí salen el catálogo de modelos y la validación de
    `encargos_config`, para que la página simule con las mismas reglas con que después se aplica."""
    global _AP_MOD
    if _AP_MOD is None:
        spec = importlib.util.spec_from_file_location("aplicar_propuesta", D / "pi/aplicar-propuesta.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _AP_MOD = mod       # solo si cargó entero: una carga a medias no queda como si sirviera (48r2-1)
    return _AP_MOD


def esfuerzo_incompatible(et: dict, rol: str, mod: dict | None = None) -> str:
    """Motivo si la etapa declara `esfuerzo_<rol>` y el modelo ya resuelto no lo acepta (48r1-1:
    `menor` resuelve a Haiku, que no acepta `--effort`, y el CLI lo rechazaba con la cola andando).
    Mira el mismo catálogo con que `encargos_config` valida los niveles. '' si calza, si la etapa no
    declara esfuerzo, si no hay modelo que verificar (C4: sin naturaleza, default del CLI) o si el
    catálogo cargó y no conoce ese modelo. Si el catálogo no carga, o no trae los modelos de ese
    motor, también es motivo (48r2-1): sin la comprobación la cola no corre, no queda autorizada."""
    declarado = et.get(f"esfuerzo_{rol}")
    if not declarado:
        return ""
    mod = mod or modelo_de(et, rol)
    if not mod["modelo"]:
        return ""
    motor = MOTORES[et["revisor"] if rol in ("rev", "cierre") else et["autor"]]["motor"]
    sin_verificar = (f"etapa {et.get('id', '?')}: `esfuerzo_{rol} = \"{declarado}\"` no se pudo verificar con "
                     f"{mod['modelo']} [{mod['nivel']}]: ")
    try:
        del_motor = _ap_mod().catalogo_modelos(_cfg_modelos()).get(motor)
    except Exception as e:
        return sin_verificar + f"no cargó el catálogo de modelos ({type(e).__name__}: {e}); la cola no corre sin esa comprobación"
    if not isinstance(del_motor, dict):
        return sin_verificar + f"el catálogo no trae los modelos de {motor}; la cola no corre sin esa comprobación"
    acepta = del_motor.get(mod["modelo"])
    if acepta is None or declarado in acepta:
        return ""
    return (f"etapa {et.get('id', '?')}: `esfuerzo_{rol} = \"{declarado}\"` no sirve con {mod['modelo']} "
            f"[{mod['nivel']}], que " + (f"acepta {', '.join(acepta)}" if acepta else "no acepta esfuerzo")
            + f"; quita `esfuerzo_{rol}` o fija un `modelo_{rol}` que lo acepte")


def validar_esfuerzos(etapas: list[dict]) -> None:
    """Antes de correr nada: ningún `esfuerzo_<rol>` declarado con un modelo que no lo acepta, ni
    sin poder comprobarlo. ValueError con el motivo, como `validar_remotas`."""
    for et in etapas:
        for rol in ("autor", "rev", "fix", *(("cierre",) if cierre_aplica(et) else ())):
            motivo = esfuerzo_incompatible(et, rol)
            if motivo:
                raise ValueError(motivo)


ESTADOS_ACTIVOS = ("partiendo", "esperando autorización", "esperando", "línea base de pruebas", "corriendo",
                   "esperando_cuota", "pruebas finales", "desplegando")
ACTIVA_FRESCA_S = 2 * 3600       # lo mismo que SIN_SENAL_MS de barra.js

# ---------------------------------------------------------------- matriz de cuota (encargo 46a)

ANTES_DE_PARTIR = ("partiendo", "esperando autorización", "esperando", "línea base de pruebas")
MEDICION_VIEJA_S = 2 * 3600      # límites medidos hace más que esto: la cuenta sale débil
PAUSA_POR_CUOTA = re.compile(r"sin margen|sin cuota")       # los motivos de Pausa de chequear_cuota y de etapa()
RE_NOMBRE = re.compile(r"[\w][\w .-]*")     # un nombre que sirve de archivo: colas (vivo/<cola>.json) y `arboles_extra`
ESTADOS_FUERA = {"caída": "caida", "sin autorización": "sin_autorizacion"}
CLAVES_CELDA = ("pct_5h", "pct_5h_min", "pct_5h_max", "pct_sem", "pct_sem_min", "pct_sem_max", "proxima_5h")
PARTIDA: tuple[str, str] | None = None      # (etapa, fase) desde donde parte ESTA cola; lo fija main()


def sesion_viva(nom: str) -> bool:
    try:
        return subprocess.run(["tmux", "has-session", "-t", f"={nom}"], capture_output=True).returncode == 0
    except OSError:
        return False


def _hora(x) -> datetime | None:
    """Una hora ISO con zona horaria, o None."""
    try:
        d = datetime.fromisoformat(str(x))
    except ValueError:
        return None
    return d if d.tzinfo else None


def fases_restantes(etapas: list[dict], et_actual: str, fase_actual: str, inicio: datetime,
                    transcurrido: float = 0.0, debil: bool = False) -> list[dict]:
    """Lo que publica cada cola en `fases_restantes`: todas las fases que faltan desde la actual (incluida), con
    el pronóstico de `pronostico()`. `prob` es la probabilidad de llegar a la fase y `inicio_esperado` es
    `inicio` más el avance esperado de las anteriores: la misma ponderación de `restante()` (cada revisión
    rechaza con `prob_rechazo()`, cada etapa vuelve a partir en 1, y a la primera fase se le descuenta lo
    transcurrido). `debil` marca todas las fases: el inicio no se pudo calcular con dato."""
    p = prob_rechazo()
    segunda_vuelta_plan = fase_actual in ("plan2", "revplan2")
    out, avance, alcance, etapa_previa = [], 0.0, 1.0, None
    for k, (et, fase, rol, cid) in enumerate(fases_pendientes(etapas, et_actual, fase_actual)):
        if et["id"] != etapa_previa:
            alcance, etapa_previa = 1.0, et["id"]
        donde = donde_fase(et, rol)
        modelo_rol = "autor" if rol == "plan" else "rev" if rol == "revplan" else rol
        mod = modelo_de(et, modelo_rol)
        modelo = mod["modelo"]
        f = pronostico(cid, rol, modelo, donde, mod["esfuerzo"])
        fila = {"etapa": et["id"], "fase": fase, "rol": rol, "cuenta": cid, "modelo": modelo, "min": f["min"],
                # La matriz es una decisión de margen, no una ETA: siempre publica el p75.
                # Mantener sólo las claves históricas conserva la forma que leen Cockpit y avisos.
                "pct_5h": f["pct_5h_p75"], "pct_sem": f["pct_sem_p75"], "prob": round(alcance, 4),
                "inicio_esperado": (inicio + timedelta(minutes=avance)).isoformat(timespec="seconds"),
                "debil": bool(f["debil"]) or debil}
        if donde:
            fila["donde"] = donde       # corre en otro equipo: ocupa tiempo, pero no gasta cuota de la Pi
        out.append(fila)
        avance += alcance * (max(0.5, f["min"] - transcurrido) if k == 0 else f["min"])
        if rol == "revplan":
            alcance = p if fase == "revplan" else (1 - p if segunda_vuelta_plan else 1 - p * p)
        elif rol in ("rev", "cierre"):
            alcance *= p
    return out


def fin_esperado(v: dict) -> datetime | None:
    """Cuándo terminaría la cola de ese vivo: su `eta.esperado` si corre o espera cuota; si no, el fin de la
    última de sus `fases_restantes` (una cola que todavía no parte no tiene `eta`). None si no publica nada."""
    eta = v.get("eta")
    if v.get("estado") in ("corriendo", "esperando_cuota") and isinstance(eta, dict) and _hora(eta.get("esperado")):
        return _hora(eta["esperado"])
    fin = None
    for f in v.get("fases_restantes") if isinstance(v.get("fases_restantes"), list) else []:
        ini = _hora(f.get("inicio_esperado")) if isinstance(f, dict) else None
        if ini and _num(f.get("min")) and _num(f.get("prob")):
            t = ini + timedelta(minutes=f["prob"] * f["min"] + 1)
            fin = t if fin is None or t > fin else fin
    return fin


def _leer_vivo(ruta: Path):
    """El JSON de un vivo/<cola>.json, leído sin seguir un enlace simbólico: un enlace en `vivo/` no hace leer
    ni publicar un archivo de fuera de la carpeta. OSError si es un enlace o no es un archivo corriente (un
    directorio, un FIFO: no se queda esperando al que escribe)."""
    fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("no es un archivo corriente")
        f = os.fdopen(fd, encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise
    with f:
        return json.loads(f.read())


def _inicio_tras_espera(esperada, momento: datetime, vivos_dir: Path) -> tuple[datetime, bool]:
    """(inicio, débil) de una cola que espera a la sesión `esperada`: el fin esperado de esa cola, leído de su
    vivo. Sin dato (no es una cola, su vivo no está o llegó a medias, no publica fin): «ahora» y débil."""
    if not (isinstance(esperada, str) and RE_NOMBRE.fullmatch(esperada)):
        return momento, True
    try:
        otra = _leer_vivo(vivos_dir / f"{esperada}.json")
        fin = fin_esperado(otra) if isinstance(otra, dict) else None
    except (OSError, ValueError, RecursionError):
        fin = None
    return (max(fin, momento), False) if fin else (momento, True)


def _punto_de_reanudacion(v: dict, etapas: list[dict]) -> tuple[str, str] | None:
    """(etapa, fase) desde donde seguiría la cola de ese vivo: el `--desde` que dejó su pausa; si no, la fase
    en que estaba; y si nunca empezó una, su punto de partida. None si estaba entre fases (pruebas finales)."""
    if isinstance(v.get("reanuda_desde"), str) and v.get("estado") not in ESTADOS_ACTIVOS:
        et, fase = _etapa_fase(v["reanuda_desde"])
        return et, fase or "autor"
    if v.get("etapa") is None:
        rel = v.get("relanzamientos")
        if isinstance(rel, list) and rel and isinstance(rel[-1], dict) and isinstance(rel[-1].get("desde"), str):
            et, fase = _etapa_fase(rel[-1]["desde"])
            return et, fase or "autor"
        return etapas[0]["id"], "autor"
    return (v["etapa"], v["fase"]) if isinstance(v.get("fase"), str) else None


def plan_de_vivo(v: dict, etapas: list[dict], momento: datetime, vivos_dir: Path,
                 reanudar_en: datetime | None = None, partida: tuple[str, str] | None = None) -> list[dict]:
    """Las `fases_restantes` de la cola cuyo vivo es `v` y cuyas etapas (del manifiesto) son `etapas`.
    - Sin `reanudar_en`, según su estado: corriendo, desde su fase y desde «ahora»; esperando cuota, desde la
      hora en que sigue; antes de su primera fase, desde `partida` y desde «ahora», o desde el fin esperado
      de la cola que espera; en cualquier otro estado, nada.
    - Con `reanudar_en` (una cola que no corre: «¿y si se reanuda a esa hora?»): desde su punto de reanudación.
    ValueError si el vivo y el manifiesto no calzan (una etapa o una fase que el manifiesto no tiene)."""
    estado, transcurrido, debil = v.get("estado"), 0.0, False
    if reanudar_en is not None:
        punto, inicio = _punto_de_reanudacion(v, etapas), reanudar_en
    elif estado == "corriendo" and v.get("fase"):
        punto, inicio = (v["etapa"], v["fase"]), momento
        transcurrido = (momento - datetime.fromisoformat(v["inicio_fase"])).total_seconds() / 60
    elif estado == "esperando_cuota" and v.get("fase"):
        punto, inicio = (v["etapa"], v["fase"]), max(momento, _hora(v.get("reanuda")) or momento)
    elif estado in ANTES_DE_PARTIR:
        punto, inicio = partida or _punto_de_reanudacion(v, etapas), momento
        if estado == "esperando":
            inicio, debil = _inicio_tras_espera(v.get("esperando"), momento, vivos_dir)
    else:
        return []
    if punto is None:
        return []
    if not any(et["id"] == punto[0] for et in etapas):
        raise ValueError(f"la etapa {punto[0]} no está en el manifiesto")
    return fases_restantes(etapas, punto[0], punto[1], inicio, transcurrido, debil)


def leer_vivos(vivos_dir: Path) -> tuple[list[dict], list[str]]:
    """(los vivo/<cola>.json que se pueden leer, los nombres de archivo de los que no). Otra cola puede estar
    escribiendo el suyo: un JSON a medias o sin la forma esperada se salta, nunca tira al que lee.
    `despacho.json` vive en la misma carpeta y no es de ninguna cola (encargo 50a): no se cuenta."""
    buenos, malos = [], []
    for ruta in sorted(vivos_dir.glob("*.json")):
        if ruta.name == "despacho.json":
            continue
        try:
            v = _leer_vivo(ruta)
            if not (isinstance(v, dict) and v.get("nombre") == ruta.stem and RE_NOMBRE.fullmatch(ruta.stem)
                    and isinstance(v.get("estado"), str) and _hora(v.get("escrito"))):
                raise ValueError("no tiene la forma de un vivo")
        except (OSError, ValueError, RecursionError):
            malos.append(ruta.stem if RE_NOMBRE.fullmatch(ruta.stem) else "?")
            continue
        buenos.append(v)
    return buenos, malos


def manifiestos_por_cola(carpeta: Path) -> dict[str, dict]:
    """{nombre de la cola: su manifiesto} de los cola-*.toml de la carpeta. Si dos traen el mismo nombre vale
    el primero por orden de archivo, como en reanudar-en-orden.sh."""
    out: dict[str, dict] = {}
    for ruta in sorted(carpeta.glob("cola-*.toml")):
        try:
            man = tomllib.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(man.get("nombre"), str) and isinstance(man.get("etapa"), list) and man["etapa"]:
            out.setdefault(man["nombre"], man)
    return out


def timers_reanudacion(correr=None) -> list[tuple[datetime, str]]:
    """(próximo disparo, ExecStart de lo que activa) de cada timer de usuario que todavía va a disparar. Un
    timer que ya disparó sigue «activo» pero sin `next`: no reanuda nada. Si systemd no contesta, ninguno."""
    correr = correr or subprocess.run
    try:
        filas = json.loads(correr(["systemctl", "--user", "list-timers", "--all", "--output=json"],
                                  capture_output=True, text=True, timeout=15).stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    out = []
    for t in filas if isinstance(filas, list) else []:
        if not (isinstance(t, dict) and _num(t.get("next")) and t["next"] > 0 and isinstance(t.get("activates"), str)):
            continue
        try:
            orden = correr(["systemctl", "--user", "show", t["activates"], "-p", "ExecStart", "--value"],
                           capture_output=True, text=True, timeout=15).stdout or ""
            out.append((datetime.fromtimestamp(t["next"] / 1e6).astimezone(), orden))
        except (OSError, ValueError, OverflowError, subprocess.SubprocessError):
            continue
    return out


def _fases_validas(fases) -> tuple[list[tuple[datetime, dict]], bool]:
    """((inicio, fase) de las fases bien formadas, si hubo que saltarse alguna). Lo que publica otra cola se
    lee con desconfianza: una fase sin cuenta conocida, sin números o sin hora no se suma."""
    buenas, salto = [], False
    for f in fases:
        ini = _hora(f.get("inicio_esperado")) if isinstance(f, dict) else None
        if (ini and f.get("cuenta") in MOTORES and all(_num(f.get(k)) and f[k] >= 0 for k in ("pct_5h", "pct_sem", "min"))
                and _num(f.get("prob")) and 0 <= f["prob"] <= 1):
            buenas.append((ini, f))
        else:
            salto = True
    return buenas, salto


def _texto_ventana(w: dict) -> str:
    ok = _alcanza(w)
    hasta = _hora(w.get("quemar_hasta"))
    quemando = f" (quemando hasta {hasta.astimezone():%H:%M})" if w.get("quemando") and hasta else ""
    return (f"{'5 h' if w['ventana'] == '5h' else 'sem'} ahora {num_es(w['actual'])} % + {num_es(w['pronostico'])} % = "
            f"{num_es(w['actual'] + w['pronostico'])} % {'≤' if ok else '>'} tope {w['tope']} %: "
            f"{'alcanza' if ok else 'no alcanza'}{quemando}")


def _razon_sem_por_5h(cid: str) -> float:
    """Puntos semanales que representó un punto de 5 h, medidos en fresco para esta cuenta.

    Un porcentaje de la ventana de 5 h no es intercambiable uno a uno con el semanal. Se usa la
    razón acumulada de al menos tres mediciones con un delta de 5 h útil; antes de eso, la BASE del
    motor conserva una estimación conservadora y explícita.
    """
    deltas = []
    for h in historial():
        if h.get("cuenta") != cid or h.get("medicion") != "fresco":
            continue
        h5, sem = h.get("pct_5h"), h.get("pct_sem")
        if not (isinstance(h5, list) and isinstance(sem, list) and len(h5) == len(sem) == 2
                and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in h5 + sem)):
            continue
        d5, dsem = h5[1] - h5[0], sem[1] - sem[0]
        if d5 >= 5 and dsem >= 0:
            deltas.append((d5, dsem))
    if len(deltas) >= 3 and sum(d5 for d5, _ in deltas) > 0:
        return sum(dsem for _, dsem in deltas) / sum(d5 for d5, _ in deltas)
    base = [v for (motor, _), v in BASE.items() if motor == MOTORES[cid]["motor"] and v["pct_5h"] > 0]
    return sum(v["pct_sem"] for v in base) / sum(v["pct_5h"] for v in base)


def capacidad_por_vencer(cid: str, u: dict, momento: datetime) -> dict:
    """Capacidad semanal que aún cabe antes de renovar, respetando la cadencia de 5 h."""
    sem, h5 = topes(cid, u, momento)
    ren_sem, ren_5h = u.get("renueva_sem"), u.get("renueva_5h")
    invalida = (not isinstance(ren_sem, datetime)
                or not isinstance(u.get("sem"), (int, float)) or not isinstance(u.get("5h"), (int, float))
                or ren_sem <= momento)
    base = {"cuenta": cid, "nombre": nombre(cid), "capacidad": None, "por_ventanas": None,
            "renueva": ren_sem, "debil": invalida or quema(cid, u, momento)["debil"], "colas_que_caben": []}
    if invalida:
        return base
    # El tramo abierto cabe entero antes de su renovación; los posteriores se prorratean sólo si
    # la renovación semanal los corta. Sin ventana abierta, desde ahora parte una limpia.
    if isinstance(ren_5h, datetime) and ren_5h > momento:
        cursor, disponible = ren_5h, max(0.0, h5 - float(u["5h"]))
    else:
        cursor, disponible = momento + timedelta(hours=5), float(h5)
    while cursor < ren_sem:
        fin = min(cursor + timedelta(hours=5), ren_sem)
        disponible += h5 * (fin - cursor).total_seconds() / (5 * 3600)
        cursor = fin
    por_ventanas = disponible * _razon_sem_por_5h(cid)
    base["por_ventanas"] = round(por_ventanas, 1)
    base["capacidad"] = round(max(0.0, min(por_ventanas, sem - float(u["sem"]))), 1)
    return base


def matriz_cuota(vivos_dir: Path | None = None, uso_de=None, momento: datetime | None = None, viva=None,
                 timers: list[tuple[datetime, str]] | None = None, manifiestos_dir: Path | None = None) -> dict:
    """La matriz cuentas × colas (encargo 46a): {'momento', 'reglas', 'colas_fuera', 'cuentas'}.

    Cuentan solo las colas que van a correr solas: la viva (sesión tmux, o vivo escrito hace menos de 2 h), la
    que espera a otra, y la pausada por cuota con una reanudación programada (`reanuda` en su vivo, o un timer
    de usuario que todavía va a disparar y la nombra). De esas se suma, por cuenta, `prob × pct` de todas sus
    `fases_restantes`, separado por ventana: el 5 h de una fase cuenta ahora si parte antes de la renovación
    de 5 h de la cuenta (si no, va a `proxima_5h`) y el semanal cuenta si parte antes de la renovación
    semanal. Sin hora de renovación se cuenta todo en la ventana actual y la cuenta sale débil.

    Las demás (detenida, pausada sin timer, en candado, caída…) van a `colas_fuera` con las fases que
    correrían si se reanudaran ahora; no suman. Las terminadas no se publican: no les queda nada.

    Todo lo que depende del nodo entra por parámetro: la carpeta de los vivos, `uso_de(cid)` (la forma de
    `uso()`), la hora, `viva(nombre)`, los timers (la forma de `timers_reanudacion()`) y la carpeta de los
    manifiestos. La página solo dibuja lo que sale de acá. No escribe nada."""
    momento = momento or ahora()
    vivos_dir, uso_de, viva = vivos_dir or E / "vivo", uso_de or uso, viva or sesion_viva
    perezoso: dict = {}

    def manifiesto_de(nom: str) -> dict:
        if "manifiestos" not in perezoso:
            perezoso["manifiestos"] = manifiestos_por_cola(manifiestos_dir or E)
        man = perezoso["manifiestos"].get(nom)
        if man is None:
            raise ValueError("no se encontró su manifiesto")
        if not man.get("_listo"):
            repartir(man["etapa"])
            for et in man["etapa"]:
                if remota(et):
                    et["vueltas"] = 0       # como validar_remotas: una etapa en PC-2503 no tiene arreglos
            man["_listo"] = True
        return man

    def timer_de(nom: str) -> datetime | None:
        if "timers" not in perezoso:
            perezoso["timers"] = timers_reanudacion() if timers is None else timers
        horas = [t for t, orden in perezoso["timers"] if re.search(rf"(?<![\w.-]){re.escape(nom)}(?![\w.-])", orden)]
        return min(horas) if horas else None

    vivos, ilegibles = leer_vivos(vivos_dir)
    fuera = [{"cola": n, "estado": "ilegible", "motivo": "su vivo no se pudo leer (a medio escribir o sin la forma esperada)",
              "fase": None, "fases_restantes": [], "debil": True} for n in ilegibles]
    activas: list[tuple[str, list]] = []
    incompleta = bool(ilegibles)        # falta lo de alguna cola que podría contar: toda la suma es débil
    for v in vivos:
        nom, estado = v["nombre"], v["estado"]
        if estado == "terminada":
            continue
        escrito = _hora(v["escrito"])
        en_marcha = estado in ESTADOS_ACTIVOS and (viva(nom) or (momento - escrito).total_seconds() < ACTIVA_FRESCA_S)
        fuera_por, motivo, reanudar_en = "", "", None
        if estado == "pausada":
            motivo = _una_linea(v.get("motivo_pausa"))
            cuando = (_hora(v.get("reanuda")) or timer_de(nom)) if PAUSA_POR_CUOTA.search(motivo) else None
            if cuando and cuando > momento:
                reanudar_en = cuando
            else:       # sin reanudación programada, o una pausa que no es por cuota: la decide el usuario
                fuera_por = "pausada_sin_timer"
        elif en_marcha and estado == "esperando autorización":
            fuera_por = "en_candado"
            motivo = _una_linea("espera la autorización de " + ", ".join(str(m) for m in v.get("candado") or []))
        elif not en_marcha and estado in ESTADOS_ACTIVOS:
            fuera_por = "detenida"
            motivo = f"sin sesión y sin señal desde el {escrito.astimezone():%d-%m %H:%M} (quedó en «{estado}»)"
        elif not en_marcha:
            fuera_por = ESTADOS_FUERA.get(estado) or re.sub(r"\W+", "_", estado)[:40]
            motivo = _una_linea(v.get("error") or v.get("motivo_pausa")) or (
                "una etapa quedó NO DESPLEGABLE o fallaron las pruebas finales" if estado == "detenida" else "")
        problema = ""
        try:
            if en_marcha and isinstance(v.get("fases_restantes"), list):
                fases = v["fases_restantes"]       # lo que publica la propia cola
            elif estado == "detenida" and not isinstance(v.get("reanuda_desde"), str):
                fases = []      # agotó sus vueltas o falló en las pruebas finales: desde dónde sigue lo decide una persona
            else:       # una cola que no corre, o una viva anterior al encargo 46: sale de su manifiesto
                fases = plan_de_vivo(v, manifiesto_de(nom)["etapa"], momento, vivos_dir,
                                     None if en_marcha else reanudar_en or momento)
            validas, salto = _fases_validas(fases)
            if salto:
                problema = "alguna de sus fases no tiene la forma esperada"
        except (KeyError, ValueError, TypeError, RuntimeError) as e:
            fases, validas, problema = [], [], str(e) or type(e).__name__
        if fuera_por:
            fase = f"{fases[0]['etapa']}:{fases[0]['fase']}" if validas and validas[0][1] is fases[0] else (
                v["reanuda_desde"] if isinstance(v.get("reanuda_desde"), str) else None)
            fuera.append({"cola": nom, "estado": fuera_por,
                          "motivo": motivo + (f" (no se pudo proyectar: {_una_linea(problema)})" if problema else ""),
                          "fase": fase, "fases_restantes": [f for _, f in validas], "debil": bool(problema)})
        else:
            incompleta = incompleta or bool(problema)
            activas.append((nom, validas))

    usos = {cid: uso_de(cid) for cid in MOTORES}
    iso = lambda d: d.isoformat(timespec="seconds") if d else None
    por_cuenta: dict[str, dict[str, list]] = {}
    for nom, validas in activas:
        for ini, f in validas:
            if not f.get("donde"):
                por_cuenta.setdefault(f["cuenta"], {}).setdefault(nom, []).append((ini, f))
    reglas = []
    for cid in (c for c in MOTORES if c in por_cuenta):     # filas en el orden fijo de las cuentas: no saltan al avanzar las fases
        colas, u = por_cuenta[cid], usos[cid]
        ren = {"pct_5h": u.get("renueva_5h"), "pct_sem": u.get("renueva_sem")}
        fuente, debil = u["fuente"], incompleta or None in ren.values() or quema(cid, u, momento)["debil"]
        medido = _hora(u.get("momento"))
        if medido and (momento - medido).total_seconds() > MEDICION_VIEJA_S:
            fuente, debil = f"medido hace {int((momento - medido).total_seconds() // 3600)} h", True
        celdas, total = {}, dict.fromkeys(CLAVES_CELDA, 0.0)
        for nom, fases in colas.items():
            c = dict.fromkeys(CLAVES_CELDA, 0.0)
            for ini, f in fases:
                for k in ("pct_5h", "pct_sem"):
                    if ren[k] is None or ini < ren[k]:
                        c[k] += f["prob"] * f[k]
                        c[k + "_max"] += f[k]
                        c[k + "_min"] += f[k] if f["prob"] >= 1 else 0
                    elif k == "pct_5h":
                        c["proxima_5h"] += f["prob"] * f[k]
            for k in CLAVES_CELDA:
                total[k] += c[k]
            celdas[nom] = {k: round(x, 1) for k, x in c.items()} | {"debil": any(bool(f.get("debil")) for _, f in fases)}
        item = {"cuenta": cid, "nombre": nombre(cid), "colas": list(colas), "fuente": fuente,
                "debil": debil or any(c["debil"] for c in celdas.values()),
                "ventanas": [], "alcanza": None, "texto": f"{nombre(cid)}: sin dato de cuota ({fuente})",
                "celdas": celdas, "proxima_5h": round(total["proxima_5h"], 1),
                "renueva_5h": iso(ren["pct_5h"]), "renueva_sem": iso(ren["pct_sem"])}
        if u["sem"] is not None:
            for w in ventanas_cuota(cid, {k: round(total[k], 1) for k in ("pct_sem", "pct_5h")}, u, momento):
                item["ventanas"].append({k: w[k] for k in ("ventana", "actual", "pronostico", "tope")} |
                                        {k: (iso(w[k]) if k == "quemar_hasta" else w[k])
                                         for k in ("quemando", "quemar_hasta", "debil") if k in w} |
                                        {"alcanza": _alcanza(w)})
            item["alcanza"] = all(w["alcanza"] for w in item["ventanas"])
            partes = [_texto_ventana(w) for w in sorted(item["ventanas"], key=lambda w: w["ventana"] != "5h")]
            if item["proxima_5h"]:
                partes.append(f"↻ {num_es(item['proxima_5h'])} % en la próxima ventana")
            item["texto"] = f"{nombre(cid)} ({', '.join(colas)}): " + " · ".join(partes)
        reglas.append(item)
    capacidad = {cid: capacidad_por_vencer(cid, u, momento) for cid, u in usos.items()}
    salida = {"momento": iso(momento), "reglas": reglas, "colas_fuera": fuera,
              "cuentas": {cid: {"renueva_5h": iso(u.get("renueva_5h")), "renueva_sem": iso(u.get("renueva_sem"))}
                          for cid, u in usos.items()}, "capacidad_por_vencer": capacidad}
    for cid, dato in capacidad.items():
        if dato["capacidad"] is None:
            continue
        for fila in fuera:
            try:
                cargas, _ = carga_proyectada(fila["cola"], salida, uso_de)
                carga = next(x for x in cargas if x["cuenta"] == cid)
            except (KeyError, StopIteration, TypeError, ValueError):
                continue
            cabe_5h = all(w["holgura"] >= 0 for w in carga["ventanas"] if w["ventana"] == "5h")
            if carga["pct_sem"] <= dato["capacidad"] and cabe_5h:
                dato["colas_que_caben"].append(fila["cola"])
    for dato in capacidad.values():
        dato["renueva"] = iso(dato["renueva"])
    return salida


def reglas_cuota(**entradas) -> list[dict]:
    """La regla de las colas, a la vista (encargos 24 y 46a): por cada cuenta que usan las colas activas,
    «ahora X % + lo que falta Y % = Z % ≤ tope: alcanza / no alcanza» por ventana, con una celda por cola.
    Es `matriz_cuota()['reglas']` y recibe sus mismas entradas."""
    return matriz_cuota(**entradas)["reglas"]


def pronosticos_por_modelo(catalogo: dict) -> dict:
    """Lo que diría un pronóstico de autor para cada modelo del catálogo, con la primera cuenta de su
    motor: es lo que muestra «⚙️ Reparto y modelos» junto al factor («[débil, factor 0,61]»)."""
    cuenta_de = {}
    for cid, m in MOTORES.items():
        cuenta_de.setdefault(m["motor"], cid)
    out = {}
    for motor, modelos in catalogo.items():
        for modelo in (modelos or {}):
            f = pronostico(cuenta_de[motor], "autor", modelo)
            out[modelo] = {"cuenta": cuenta_de[motor], "rol": "autor", "pct_5h": f["pct_5h"], "pct_sem": f["pct_sem"],
                           "min": f["min"], "debil": f["debil"], "por_factor": f["por_factor"],
                           "etiqueta": etiqueta_pronostico(f)}
    return out


def panel(timers_todos: list[dict] | None = None, **entradas) -> dict:
    """Lo que dibuja «⚙️ Reparto y modelos» y la matriz de 🧵 Encargos: modelos.toml tal como se lee,
    los modelos que existen (con sus esfuerzos), el pronóstico de cada uno, las cuentas con el nombre
    que se muestra y sus renovaciones, y la matriz de cuota (`reglas`, `colas_fuera` y el `momento` del
    cálculo). `entradas` son las de `matriz_cuota()`.
    Encargo 46c: `colas` trae, por cola, los botones que valen y los timers que la nombran (`botones_colas()`).
    Encargo 50a: `despacho` es el estado de `leer_despacho()` más su `aviso`, y `pasado`, el balance de `pasado()`.
    `timers_todos` tiene la forma de `timers_usuario()`; si no viene y el que llama inyectó los `timers` de la
    matriz, salen de esos (ya decidió no preguntarle a systemd)."""
    cfg = _cfg_modelos()
    catalogo = _ap_mod().catalogo_modelos(cfg)
    matriz = matriz_cuota(**entradas)
    if timers_todos is None and entradas.get("timers") is not None:
        timers_todos = [{"unidad": "", "proxima": t, "ultima": None, "orden": orden} for t, orden in entradas["timers"]]
    colas = botones_colas(entradas.get("vivos_dir"), entradas.get("viva"), entradas.get("manifiestos_dir"),
                          _hora(matriz["momento"]), timers_todos)
    despacho, aviso_despacho = leer_despacho(entradas.get("vivos_dir"))
    return {"despacho": despacho | {"aviso": aviso_despacho}, "pasado": pasado(entradas.get("manifiestos_dir")),
            "modelos": {k: cfg.get(k) or {} for k in ("niveles", "naturaleza", "reparto", "autorizacion", "factor_modelo")},
            "catalogo": catalogo, "pronosticos": pronosticos_por_modelo(catalogo), "reglas": matriz["reglas"],
            "colas_fuera": matriz["colas_fuera"], "capacidad_por_vencer": matriz["capacidad_por_vencer"],
            "momento": matriz["momento"], "colas": colas,
            "cuentas": {cid: {"nombre": nombre(cid), "motor": m["motor"]} | matriz["cuentas"][cid]
                        for cid, m in MOTORES.items()}}


_BAL_MOD = None


def _bal_mod():
    """encargos/balance.py (el balance de los encargos; solo lee)."""
    global _BAL_MOD
    if _BAL_MOD is None:
        spec = importlib.util.spec_from_file_location("balance", Path(__file__).resolve().parent / "balance.py")
        _BAL_MOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_BAL_MOD)
    return _BAL_MOD


def pasado(manifiestos_dir: Path | None = None) -> dict | None:
    """La mirada de pasado de «Capacidad» (encargo 50a): lo que calcula balance.py sobre el historial y los
    manifiestos, con sus propias funciones (`datos()`, lo mismo que imprime `balance.py --json`). Acá no se
    calcula nada. None si no se pudo leer: el panel sale igual."""
    try:
        bal = _bal_mod()
        filas, saltadas = bal.leer_historial(HISTORIAL)
        etapas, ilegibles = bal.leer_manifiestos(manifiestos_dir or E)
        return bal.datos(filas, etapas, saltadas, ilegibles)
    except Exception:       # noqa: BLE001 — el balance es de lectura: si falla, la matriz y los botones se publican igual
        return None


def modelos_con_candado(etapas: list[dict]) -> dict[str, list[str]]:
    """{modelo: ['21 autor', ...]} de los modelos que piden autorización y que esta cola usaría
    en algún rol (autor, revisión o arreglo, aunque el arreglo no llegue a correr)."""
    aut = _cfg_modelos().get("autorizacion") or {}
    candado = {str(x).lower() for x in aut.get("modelos") or []}
    # Por trozo y no solo por nombre exacto: `--model fable` o `gpt-6-astra-…` también son
    # esos modelos (hallazgo 6 de la revisión 21r, 03-10).
    patrones = [str(x).lower() for x in aut.get("patrones") or []]
    usos: dict[str, list[str]] = {}
    for et in etapas:
        for rol in ("autor", "rev", "fix", *(("cierre",) if cierre_aplica(et) else ())):
            m = modelo_de(et, rol)["modelo"]
            if m and (m.lower() in candado or any(p in m.lower() for p in patrones)):
                usos.setdefault(m, []).append(f"{et['id']} {rol}")
    return usos


AUTORIZADOS: set[str] = set()   # modelos con candado que el usuario aprobó al lanzar esta cola


def exigir_candado(et: dict, rol: str, mod: dict, desde: str) -> None:
    """23a-1: el modelo de la fase se relee del archivo, así que un candado puesto a mitad de cola
    (propuesta desde ⚙️) llegaría sin autorización. Si el modelo tiene candado y no se aprobó al
    lanzar, se pide ahora; sin ✅ la cola se pausa antes de gastar nada."""
    m = mod.get("modelo") or ""
    if not m or m.lower() in AUTORIZADOS:
        return
    nuevo = modelos_con_candado([dict(et, modelo_autor=m, modelo_rev=m, modelo_fix=m, modelo_cierre=m)]).get(m)
    if not nuevo:
        return
    uso = [f"{et['id']} {rol}"]
    log(f"🔒 {et['id']}: {m} tiene candado y no estaba autorizado al lanzar (cambió la configuración a mitad de cola)")
    if not pedir_autorizacion(MANIFIESTO["nombre"], {m: uso}):
        raise Pausa(f"{m} pide autorización y no se dio. Cambia el nivel o fija otro modelo, y reanuda", desde)
    AUTORIZADOS.add(m.lower())


def pedir_autorizacion(nom: str, usos: dict[str, list[str]]) -> bool:
    """Manda la petición por Telegram y espera el ✅ (solo el usuario puede darlo). True si llegó."""
    posponer_si_descanso()
    espera = int((_cfg_modelos().get("autorizacion") or {}).get("espera_max_min") or 30)
    detalle = "; ".join(f"{m} ({', '.join(r)})" for m, r in usos.items())
    linea = f"echo 'Autorizo {', '.join(usos)} para la cola {nom}'"
    log(f"🔒 Pide autorización por Telegram para {detalle}; espera hasta {espera} min")
    with (L / "avisos.log").open("a", encoding="utf-8") as fh:
        motivo = (f"🔒 La cola {nom} quiere usar modelos que requieren tu autorización: {detalle}. "
                  f"Gastan bastante más cuota. ✅ = autorizo. Si no, ignóralo: a los {espera} min "
                  "vence y la cola no corre nada.")
        p = subprocess.run(["nodo-desplegar", "sugerir", "--motivo", motivo, "--", linea],
                           capture_output=True, text=True)
        fh.write(p.stdout + p.stderr)
        registrar_aviso(motivo, linea, p)
        pid = (p.stdout.strip().splitlines() or [""])[-1]
        ok = bool(pid) and subprocess.run(["nodo-desplegar", "esperar", pid, "--max", str(espera * 60)],
                                          stdout=fh, stderr=fh).returncode == 0
    log(f"🔓 Autorizado ({pid})" if ok else f"⛔ Sin autorización ({pid or 'no se pudo pedir'}): la cola no corre")
    return ok


def factores() -> dict[str, float]:
    """[factor_modelo] de modelos.toml (encargo 24): cuánto cuota gasta cada modelo relativo al de
    referencia de su motor (Claude Opus 5.5 = 1,0). Solo entran números positivos de verdad: algo
    roto vale «sin factor», no 0 (un factor 0 haría pronosticar que la fase no cuesta nada)."""
    tabla = _cfg_modelos().get("factor_modelo") or {}
    return {str(k): float(v) for k, v in tabla.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and 0 < v < float("inf")}


def num_es(x: float) -> str:
    """0.61 -> «0,61»; 1.0 -> «1»."""
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def etiqueta_pronostico(f: dict) -> str:
    """Lo que dice un pronóstico flojo: «débil, factor 0,61», «débil, sin factor», «débil» o vacío.
    Solo habla de factor cuando el pronóstico NO sale de filas del mismo modelo."""
    partes = ["débil"] if f["debil"] else []
    if f.get("por_factor") not in (None, 1.0):
        partes.append(f"factor {num_es(f['por_factor'])}")
    elif f.get("sin_factor") and not f.get("por_modelo"):
        partes.append("sin factor")
    return ", ".join(partes)


def pronostico(cid: str, rol: str, modelo: str = "", donde: str = "", esfuerzo: str = "") -> dict:
    """ETA por mediana y margen por p75, primero por cuenta+rol+modelo+esfuerzo,
    luego por modelo y finalmente por cuenta+rol. Las doce filas terminadas más recientes
    forman la ETA; las filas cortadas son cotas inferiores del p75. `debil` dice que no
    hay tres terminadas comparables con delta de cuota.
    `donde` separa lo que corrió en otro equipo ("pc2503"): un arnés laboral no dura lo que un
    encargo de la Pi, y su cuota no se mide acá (sus % quedan siempre en la base, 0).

    Encargo 24: sin 3 filas del mismo modelo, los % de cuota salen de las filas de la cuenta y el rol
    NORMALIZADAS por el factor de su modelo (cada delta ÷ factor, mediana, × factor del modelo
    pedido); sin filas, BASE × factor. Los minutos no se escalan: el costo no mide el tiempo. Con
    factor el pronóstico es siempre `debil` y trae `por_factor`. Un modelo sin factor (los de Codex:
    no tienen medida) vale 1,0, sale como siempre y trae `sin_factor`. El esfuerzo no entra al factor."""
    rol_base = {"plan": "autor", "revplan": "rev", "cierre": "rev"}.get(rol, rol)
    motor = MOTORES[cid]["motor"]
    candidatas = [h for h in historial() if h.get("cuenta") == cid and h.get("rol") == rol
                   and (h.get("donde") or "") == donde]
    mismo = [h for h in candidatas if (h.get("modelo") or "") == modelo]
    exactas = [h for h in mismo if h.get("esfuerzo") == esfuerzo]
    # Una cortada no es una observación terminada: no puede impedir bajar al nivel que sí tiene
    # tres terminadas ni devolver una BASE optimista. Sus cotas se conservan más abajo.
    hechas = lambda xs: [h for h in xs if not h.get("sin_cuota")]
    comparables = exactas if len(hechas(exactas)) >= 3 else mismo if len(hechas(mismo)) >= 3 else candidatas
    # Las doce son terminadas: un corte no desplaza una medición completa ni altera la ETA.
    terminadas = [h for h in comparables if not h.get("sin_cuota")]
    ultimas = terminadas[-12:]
    primera = comparables.index(ultimas[0]) if len(terminadas) > 12 else 0
    filas = [h for h in comparables[primera:] if not h.get("sin_cuota")]
    cortes = [h for h in comparables[primera:] if h.get("sin_cuota")]
    # Si hubo pocas filas del esfuerzo pedido, la mediana baja al modelo; sus cortes no se pierden.
    cortes += [h for h in exactas if h.get("sin_cuota") and h not in cortes]
    base = BASE_PC2503 if donde else BASE[(motor, rol_base)]
    if rol in ("plan", "revplan", "cierre") and len(mismo) < 3:
        referencia = pronostico(cid, rol_base, modelo, donde, esfuerzo)
        return dict(referencia, min=round(referencia["min"] * 0.3, 1),
                    pct_5h=round(referencia["pct_5h"] * 0.3, 2),
                    pct_sem=round(referencia["pct_sem"] * 0.3, 2),
                    pct_5h_p75=round(referencia["pct_5h_p75"] * 0.3, 2),
                    pct_sem_p75=round(referencia["pct_sem_p75"] * 0.3, 2), debil=True, n=len(mismo),
                    por_modelo=False, por_factor=0.3, sin_factor=False)
    out = dict(base, pct_5h_p75=base["pct_5h"], pct_sem_p75=base["pct_sem"], debil=True, n=len(filas),
               por_modelo=len(hechas(mismo)) >= 3, por_factor=None, sin_factor=False)
    tabla = {} if donde else factores()
    pedido = tabla.get(modelo)
    # Con factor solo si hay algo que normalizar: el modelo pedido o alguna fila tiene el suyo.
    con_factor = (not out["por_modelo"]) and (pedido is not None or any((h.get("modelo") or "") in tabla for h in filas))
    out["sin_factor"] = not donde and pedido is None
    if con_factor:
        k_pedido = pedido if pedido is not None else 1.0
        out["por_factor"] = k_pedido
        for k in ("pct_5h", "pct_sem"):
            out[k] = base[k] if k_pedido == 1.0 else round(base[k] * k_pedido, 2)
            out[k + "_p75"] = out[k]
    # Una cortada es una cota aunque aún no haya tres terminadas: también protege la BASE.
    # Se calcula fuera del bloque de medianas para que C, CC y CCC no queden en +10 % por defecto.
    cotas_por_ventana = {}
    for k in ("pct_5h", "pct_sem"):
        cotas = [(h[k][1] - h[k][0]) / (tabla.get(h.get("modelo") or "", 1.0) if con_factor else 1.0)
                 for h in cortes if isinstance(h.get(k), list) and len(h[k]) == 2
                 and all(_num(x) for x in h[k]) and h[k][1] >= h[k][0]]
        cotas_por_ventana[k] = cotas
        if cotas:
            out[k + "_p75"] = max(out[k + "_p75"], round(max(cotas) * (out["por_factor"] if con_factor else 1.0), 1))
    if len(filas) >= 3:
        out["min"] = round(statistics.median(h["min"] for h in filas), 1)
        # Solo cuentan los deltas medidos en fresco: los de uso.json anteriores al 03-10 21:50
        # salían 0 por el refresco de 15 min y bajarían el pronóstico a mentira.
        medidas = 0
        for k in ("pct_5h", "pct_sem"):
            cotas = cotas_por_ventana[k]
            deltas = [(h[k][1] - h[k][0]) / (tabla.get(h.get("modelo") or "", 1.0) if con_factor else 1.0)
                      for h in filas if h.get("medicion") == "fresco"
                      and isinstance(h.get(k), list) and len(h[k]) == 2 and all(_num(x) for x in h[k]) and h[k][1] >= h[k][0]]
            if len(deltas) >= 3:
                out[k] = round(statistics.median(deltas) * (out["por_factor"] if con_factor else 1.0), 1)
                p75_de = lambda xs: sorted(xs)[max(0, (3 * len(xs) + 3) // 4 - 1)]
                base_p75 = p75_de(deltas)
                con_cortes = deltas + [max(cota, statistics.median(deltas)) for cota in cotas]
                # Una fase cortada ya consumió su cota: no puede hacer que el p75 quede bajo ella.
                p75 = max(base_p75, p75_de(con_cortes), *(cotas or [0.0]))
                out[k + "_p75"] = round(p75 * (out["por_factor"] if con_factor else 1.0), 1)
                medidas += 1
        out["debil"] = True if con_factor or (bool(esfuerzo) and len(hechas(exactas)) < 3) else medidas < 2
    return out


# ---------------------------------------------------------------- historial de versiones (encargo 33)

_VERS_MOD = None
GIT_BASE: dict[str, object] = {}   # bases heredadas y «<etapa>[:@árbol]:fases»; None: git falló
CATALOGO_BASE = "__catalogo_base"  # foto del catálogo de la corrida original; vive con las fotos git
RE_COLA_GIT = re.compile(r"cola[0-9]{2}[a-z0-9]*")
RE_HASH_GIT = re.compile(r"[0-9a-f]{40,64}")


def _vers():
    """encargos/versiones.py (git separado fuera del vault)."""
    global _VERS_MOD
    if _VERS_MOD is None:
        spec = importlib.util.spec_from_file_location("versiones", Path(__file__).resolve().parent / "versiones.py")
        _VERS_MOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_VERS_MOD)
    return _VERS_MOD


def _repos_extra() -> list[tuple[str, object]]:
    """(carpeta, Repo) por cada `arboles_extra` del manifiesto: carpetas hermanas de 11-Pi5, cada una con su
    historial al lado del principal. Un nombre que no sea una carpeta hermana simple se anota y se salta.
    Un enlace simbólico tampoco vale (encargo 38, revisión 2): `is_dir()` lo sigue, y la cola fotografiaría
    y dejaría recuperar un árbol que puede estar fuera de 10-Proyectos. Ni la carpeta ni su historial."""
    nombres = MANIFIESTO.get("arboles_extra") or []
    if SIMULANDO or not nombres:
        return []
    out = []
    try:
        v = _vers()
        principal = v.abrir()
        padre, git_padre = principal.arbol.parent, principal.git_dir.parent
        for n in nombres:
            if (not isinstance(n, str) or not RE_NOMBRE.fullmatch(n) or n == principal.arbol.name
                    or not (padre / n).is_dir()):
                log(f"⚠️ historial git: `arboles_extra` trae {n!r}, que no es una carpeta hermana de "
                    f"{principal.arbol.name}; se salta y la cola sigue")
                continue
            hermana, historial = padre / n, git_padre / f"{n}.git"
            if (hermana.is_symlink() or Path(os.path.realpath(hermana)) != Path(os.path.realpath(padre)) / n
                    or historial.is_symlink()
                    or Path(os.path.realpath(historial)) != Path(os.path.realpath(git_padre)) / f"{n}.git"):
                log(f"⚠️ historial git: `arboles_extra` trae {n!r}, que es (o cuyo historial es) un enlace "
                    f"simbólico o resuelve fuera de {padre}; se salta y la cola sigue")
                continue
            out.append((n, v.abrir(historial, hermana)))
    except Exception as e:  # el historial ayuda, no bloquea
        log(f"⚠️ historial git: no se pudieron abrir los árboles extra ({type(e).__name__}: {e}); la cola sigue")
    return out


def git_foto(mensaje: str) -> str | None:
    """Foto del árbol (y de los `arboles_extra`). Devuelve el commit actual del árbol principal, o None si
    git falló: NUNCA lanza, la cola sigue."""
    if SIMULANDO:
        return None
    for n, repo in _repos_extra():
        try:
            for aviso in repo.foto(mensaje).avisos:
                log(f"⚠️ historial git ({n}): {aviso}")
        except Exception as e:
            log(f"⚠️ historial git: no se pudo guardar «{mensaje}» en {n} ({type(e).__name__}: {e}); la cola sigue")
    try:
        f = _vers().foto(mensaje)
        for aviso in f.avisos:
            log(f"⚠️ historial git: {aviso}")
        return f.hash
    except Exception as e:  # el historial ayuda, no bloquea
        log(f"⚠️ historial git: no se pudo guardar «{mensaje}» ({type(e).__name__}: {e}); la cola sigue")
        return None


def _git_base_ruta() -> Path:
    return L / f"{MANIFIESTO['nombre']}-git.json"


def _git_base_escribir() -> None:
    """Publica el registro entero de una vez. Otra cola puede leerlo justo ahora."""
    ruta = _git_base_ruta()
    tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(GIT_BASE, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ruta)


def catalogo_base_guardar(foto_catalogo: dict) -> None:
    """Guarda la única foto del catálogo que delimita una corrida, incluso tras --desde."""
    # `foto()` usa un set para los sueltos; el registro compartido sólo puede llevar JSON.
    base = dict(foto_catalogo)
    if isinstance(base.get("sin_catalogo"), set):
        base["sin_catalogo"] = sorted(base["sin_catalogo"])
    GIT_BASE[CATALOGO_BASE] = base
    try:
        _git_base_escribir()
    except OSError as e:
        log(f"⚠️ historial git: no se pudo guardar la línea base del catálogo ({e})")


def catalogo_base_cargar() -> dict | None:
    base = GIT_BASE.get(CATALOGO_BASE)
    # No basta que sea un dict: una base truncada se lee al reanudar y `desplegar()`
    # necesita todas estas piezas. Volver a la ruta antigua con aviso es más seguro que
    # dejar que una KeyError corte una cola.
    if not (isinstance(base, dict)
            and all(isinstance(base.get(k), dict) for k in ("entradas", "fuentes", "destinos", "paginas"))
            and isinstance(base.get("sin_catalogo"), list)):
        return None
    base = dict(base)
    base["sin_catalogo"] = set(x for x in base["sin_catalogo"] if isinstance(x, str))
    return base


def git_base_guardar(etapa_id: str, commit: str | None, fase: str | None = None, despues: bool = False) -> None:
    """Persiste atómicamente las fotos propias. La base simple se conserva para relanzamientos anteriores;
    `fase` agrega los límites antes/después que forman el diff propio."""
    if fase is None:
        GIT_BASE[etapa_id] = commit
    elif not despues:
        if fase == "autor" and etapa_id not in GIT_BASE:
            GIT_BASE[etapa_id] = commit
        try:
            momento = ahora()
            vivos, _ = leer_vivos(E / "vivo")
            # Una cola encadenada en ANTES_DE_PARTIR todavía no pudo escribir en el
            # árbol ni publicar su -git.json. No es una competidora de esta fase.
            otras = sorted(v["nombre"] for v in vivos if v.get("nombre") != MANIFIESTO["nombre"]
                           and v.get("estado") in ESTADOS_ACTIVOS and v.get("estado") not in ANTES_DE_PARTIR
                           and (sesion_viva(v["nombre"])
                                or (momento - _hora(v["escrito"])).total_seconds() < ACTIVA_FRESCA_S))
        except (OSError, ValueError, TypeError, KeyError):
            otras = []
        if not isinstance(GIT_BASE.get(f"{etapa_id}:fases"), list):
            GIT_BASE[f"{etapa_id}:fases"] = []
        GIT_BASE[f"{etapa_id}:fases"].append({"fase": fase, "antes": commit, "vivas": otras,
                                                 "inicio": ahora().isoformat(timespec="seconds")})
    else:
        fases = GIT_BASE.get(f"{etapa_id}:fases", [])
        if isinstance(fases, list):
            for f in reversed(fases):
                if isinstance(f, dict) and f.get("fase") == fase and "despues" not in f:
                    f["despues"] = commit
                    f["fin"] = ahora().isoformat(timespec="seconds")
                    try:
                        momento = ahora()
                        vivos, _ = leer_vivos(E / "vivo")
                        otras = {v["nombre"] for v in vivos if v.get("nombre") != MANIFIESTO["nombre"]
                                  and v.get("estado") in ESTADOS_ACTIVOS and v.get("estado") not in ANTES_DE_PARTIR
                                  and (sesion_viva(v["nombre"])
                                       or (momento - _hora(v["escrito"])).total_seconds() < ACTIVA_FRESCA_S)}
                        f["vivas"] = sorted(set(f.get("vivas", [])) | otras)
                    except (OSError, ValueError, TypeError, KeyError):
                        pass
                    break
    for n, repo in _repos_extra():      # la base de cada árbol extra va en el mismo archivo, como «etapa@carpeta»
        try:
            clave, foto = f"{etapa_id}@{n}", repo.head()
            if fase is None:
                GIT_BASE[clave] = foto
            elif not despues:
                if fase == "autor" and clave not in GIT_BASE:
                    GIT_BASE[clave] = foto
                if not isinstance(GIT_BASE.get(f"{clave}:fases"), list):
                    GIT_BASE[f"{clave}:fases"] = []
                GIT_BASE[f"{clave}:fases"].append({"fase": fase, "antes": foto})
            else:
                fases = GIT_BASE.get(f"{clave}:fases", [])
                if isinstance(fases, list):
                    for f in reversed(fases):
                        if isinstance(f, dict) and f.get("fase") == fase and "despues" not in f:
                            f["despues"] = foto
                            break
        except Exception as e:
            log(f"⚠️ historial git: no se pudo leer la foto base de {n} ({type(e).__name__}: {e}); la cola sigue")
    try:
        _git_base_escribir()
    except OSError as e:
        log(f"⚠️ historial git: no se pudo guardar la foto base de {etapa_id} ({e})")


def git_base_cargar() -> None:
    """Un `--desde` recupera las fotos propias de la corrida anterior."""
    GIT_BASE.clear()
    try:
        d = json.loads(_git_base_ruta().read_text(encoding="utf-8"))
        if isinstance(d, dict):
            GIT_BASE.update({str(k): v for k, v in d.items()
                             if isinstance(v, str) or (str(k).endswith(":fases") and isinstance(v, list))
                             or (k == CATALOGO_BASE and isinstance(v, dict))})
    except (OSError, ValueError, AttributeError):
        pass


def git_diff_etapa(etapa_id: str, hasta: str | None) -> str:
    """Escribe ~/encargos-logs/<cola>-<etapa>-diff.txt y devuelve su ruta. Siempre hay archivo: si git no
    pudo, dice por qué, y el revisor sigue con lo que hay."""
    ruta = L / f"{MANIFIESTO['nombre']}-{etapa_id}-diff.txt"
    base = GIT_BASE.get(etapa_id)
    try:
        fases = GIT_BASE.get(f"{etapa_id}:fases", [])
        fases = [f for f in fases if isinstance(f, dict)] if isinstance(fases, list) else []
        propias, avisos = [], []
        limite_anterior = base if isinstance(base, str) else None
        for pos, f in enumerate(fases):
            antes, despues = f.get("antes"), f.get("despues")
            if not isinstance(antes, str):
                if isinstance(limite_anterior, str) and isinstance(despues, str):
                    antes = limite_anterior
                    avisos.append(f"la fase {f.get('fase', '?')} no tiene foto inicial; se abre desde el cierre previo y puede incluir cambios ajenos")
                else:
                    avisos.append(f"la fase {f.get('fase', '?')} no tiene foto inicial; revisa los archivos directamente")
                    if isinstance(despues, str):
                        limite_anterior = despues
                    continue
            if not isinstance(despues, str):
                despues = next((siguiente.get("antes") for siguiente in fases[pos + 1:]
                                if isinstance(siguiente.get("antes"), str)), hasta)
                if not isinstance(despues, str):
                    avisos.append(f"la fase {f.get('fase', '?')} no tiene foto de cierre; revisa los archivos directamente")
                    continue
                avisos.append(f"la fase {f.get('fase', '?')} se cerró con una foto posterior tras una interrupción")
            propias.append(dict(f, antes=antes, despues=despues))
            limite_anterior = despues
        if isinstance(base, str) and not any(f.get("fase") == "autor" for f in fases) and propias:
            propias.insert(0, {"fase": "autor (registro anterior)", "antes": base,
                               "despues": propias[0]["antes"], "vivas": []})
        if not propias:
            if not (isinstance(base, str) and hasta):
                raise RuntimeError("no hay fotos completas de fases propias")
            propias = [{"fase": "autor", "antes": base, "despues": hasta, "vivas": []}]
        texto = f"# Diff propio de la etapa {etapa_id} (cola {MANIFIESTO['nombre']})\n\n"
        if avisos:
            texto += "".join(f"> ⚠️ {aviso}.\n" for aviso in avisos) + "\n"
        propios_nombres = set()
        for f in propias:
            cuerpo = _vers().diff(f["antes"], f["despues"])
            propios_nombres.update(_nombres_cambio(f["antes"], f["despues"]))
            texto += (f"## Fase propia {f.get('fase', '?')}: {f['antes'][:7]}..{f['despues'][:7]}\n\n"
                      f"{cuerpo if cuerpo.strip() else '(la etapa no cambió ningún archivo)' + chr(10)}")
            vivas = f.get("vivas", [])
            if isinstance(vivas, list) and vivas:
                texto += f"\n> hubo otras colas vivas durante la fase {f.get('fase', '?')}: {', '.join(json.dumps(x, ensure_ascii=False) for x in vivas if isinstance(x, str))}\n"
        ajenos = set()
        for previa, siguiente in zip(propias, propias[1:]):
            ajenos.update(_nombres_cambio(previa["despues"], siguiente["antes"]))
        if ajenos:
            texto += "\n## Cambios ajenos (no son de esta etapa: no los revises)\n\n" + "".join(
                f"- {json.dumps(x, ensure_ascii=False)}"
                + (" (también lo cambió esta etapa: lo que se despliegue lo incluye)" if x in propios_nombres else "")
                + "\n" for x in sorted(ajenos))
    except Exception as e:
        log(f"⚠️ historial git: no se pudo armar el diff de {etapa_id} ({type(e).__name__}: {e}); la revisión sigue sin él")
        texto = (f"No hay diff de la etapa {etapa_id}: el historial git falló ({type(e).__name__}: {e}).\n"
                 "Revisa los archivos directamente.\n")
    for n, repo in _repos_extra():
        try:
            clave, b = f"{etapa_id}@{n}", GIT_BASE.get(f"{etapa_id}@{n}")
            if not isinstance(b, str):
                raise RuntimeError("no hay foto base de la etapa")
            texto += f"\n# Árbol extra {n} (carpeta hermana, rutas relativas a ella)\n"
            hasta_extra = repo.head()
            cuerpo = repo.diff(b, hasta_extra, _vers().TOPE_DIFF_BYTES)
            texto += (f"\n## Cambios de la etapa: {b[:7]}..{hasta_extra[:7]}\n\n"
                      f"{cuerpo if cuerpo.strip() else '(la etapa no cambió ningún archivo)' + chr(10)}")
        except Exception as e:
            log(f"⚠️ historial git: no se pudo armar el diff de {etapa_id} en {n} ({type(e).__name__}: {e}); "
                "la revisión sigue sin él")
            texto += (f"\n# Árbol extra {n}: no hay diff, el historial git falló ({type(e).__name__}: {e}).\n"
                      "Revisa los archivos directamente.\n")
    try:
        ruta.write_text(texto, encoding="utf-8")
    except OSError as e:
        log(f"⚠️ historial git: no se pudo escribir {ruta} ({e})")
    return str(ruta)


# ---------------------------------------------------------------- motores

def correr(cid: str, prompt: str, nombre_log: str, mod: dict | None = None,
           herramientas: str = HERRAMIENTAS, limite_s: float | None = None) -> dict:
    """Corre un motor con el prompt. Devuelve {rc, min, tokens, sin_cuota, modelo_real}."""
    m = MOTORES[cid]
    mod = mod or {}
    env = dict(os.environ, **m["env"])
    env["NODO_PRUEBAS"] = "1"
    # Solo información para el autor: no autorizan nada. Quien busca es esta cola, por el buzón (32c).
    env["ENCARGO_NATURALEZA"] = str(mod.get("naturaleza") or "")
    env["ENCARGO_ID"] = str(mod.get("encargo_id") or "")
    env.pop("ENCARGO_BUZON", None)
    buzon = abrir_buzon_busquedas(mod, nombre_log)
    if buzon:
        env["ENCARGO_BUZON"] = str(buzon.carpeta)
    try:
        return _correr(m, cid, prompt, nombre_log, mod, herramientas, env, limite_s)
    finally:
        if buzon:
            buzon.cerrar()


# ---------------------------------------------------------------- buzón de búsquedas (encargo 32c)

BUSQUEDA_SONDEO_S = 0.2     # cada cuánto mira el hilo si llegó un pedido
BUSQUEDA_CIERRE_S = 40      # al cerrar, lo que se espera a una búsqueda en vuelo (Tavily corta a los 30 s)
BUSQUEDA_GRACIA_S = 2       # y lo que se deja a los autores para leer su respuesta antes de borrar la carpeta
_BW_MOD = None


def _bw():
    """encargos/buscar-web.py: el muro, el tope, el registro y la llamada a Tavily se importan, no se copian."""
    global _BW_MOD
    if _BW_MOD is None:
        spec = importlib.util.spec_from_file_location(
            "buscar_web", Path(__file__).resolve().parent / "buscar-web.py")
        _BW_MOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_BW_MOD)
    return _BW_MOD


class BuzonBusquedas:
    """El buzón de UNA fase: una carpeta donde el autor deja `pedido-<id>.json` y un hilo que los
    atiende de a uno con `atender()` de buscar-web.py y deja `respuesta-<id>.json`.

    `eid`, `fase` y `cola` se fijan al abrirlo, desde la memoria de la cola, y son lo único que llega
    al registro: del pedido solo se leen `consulta`, `noticias` y `semana`. `cfg` lo pasan las
    pruebas; en la cola es `config()` de buscar-web.py, leído en cada pedido (el tope puede cambiar).
    Nada de lo que traiga un pedido puede tirar el hilo: lo malformado se rechaza y se sigue."""

    def __init__(self, carpeta: Path, eid: str, fase: str, cola: str, cfg: dict | None = None):
        self.carpeta, self.eid, self.cfg = carpeta, eid, cfg
        self.origen = {"via": "cola", "cola": cola, "fase": fase}
        self.bw = _bw()
        self._hechos: set[str] = set()      # ids y nombres ya tomados: ninguno se atiende dos veces
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._servir, name=f"buzon-{eid}-{fase}", daemon=True)
        self._hilo.start()

    def _pendientes(self) -> tuple[list[str], list[str]]:
        """(ids de los pedidos bien nombrados, del más viejo al más nuevo; nombres `pedido-*` que no sirven)."""
        buenos, malos = [], []
        with os.scandir(self.carpeta) as it:
            for e in it:
                m = self.bw.PEDIDO.fullmatch(e.name)
                if e.name in self._hechos or (m and m[1] in self._hechos):
                    continue
                if m:
                    try:
                        buenos.append((e.stat(follow_symlinks=False).st_mtime_ns, m[1]))
                    except OSError:
                        continue
                elif e.name.startswith("pedido-"):
                    malos.append(e.name)
        return [pid for _, pid in sorted(buenos)], malos

    def _responder(self, pid: str, rc: int, texto: str) -> None:
        try:
            self.bw.escribir_atomico(self.carpeta / f"respuesta-{pid}.json",
                                     json.dumps({"rc": rc, "texto": texto}, ensure_ascii=False).encode("utf-8"))
        except OSError as e:    # la carpeta ya no está, o el autor dejó algo con ese nombre
            print(f"⚠️ buzón de búsquedas: no se pudo dejar la respuesta ({type(e).__name__})", flush=True)

    def _leer(self, pid: str) -> tuple[dict | None, int, str]:
        """(pedido, 0, "") o (None, código, motivo). Antes de leerlo se toma con un rename: si el
        autor ya lo retiró (venció su espera) no se busca nada, y si el autor ya no lo encuentra sabe
        que la cola lo tomó."""
        self._hechos.add(pid)
        ruta = self.carpeta / f".tomado-{pid}.json"
        try:
            os.rename(self.carpeta / f"pedido-{pid}.json", ruta)
        except FileNotFoundError:
            return None, 0, ""
        except OSError:
            return None, 2, "el pedido no se pudo tomar"
        try:
            st = ruta.lstat()
            if stat.S_ISREG(st.st_mode) and st.st_size > self.bw.MAX_PEDIDO:
                return None, 3, f"el pedido pasa de {self.bw.MAX_PEDIDO} bytes"
            crudo = _leer_del_buzon(ruta, self.bw.MAX_PEDIDO)
        except OSError:
            return None, 2, "el pedido no es un archivo corriente que se pueda leer"
        finally:
            try:
                ruta.unlink()
            except OSError:
                pass
        try:
            d = json.loads(crudo.decode("utf-8"))
        except (ValueError, RecursionError):
            return None, 2, "el pedido no es JSON"
        if not isinstance(d, dict) or not isinstance(d.get("consulta"), str):
            return None, 2, "el pedido no trae una consulta de texto"
        if not all(isinstance(d.get(k, False), bool) for k in ("noticias", "semana")):
            return None, 2, "`noticias` y `semana` tienen que ser true o false"
        return d, 0, ""

    def _uno(self, pid: str) -> None:
        d, rc, motivo = self._leer(pid)
        if d is None and not rc:
            return
        try:
            cfg = self.cfg or self.bw.config()
        except ValueError as e:
            self._responder(pid, 2, f"⛔ {e}")
            return
        if d is None:
            self.bw.anotar_rechazo(self.eid, cfg, self.origen, f"pedido malformado: {motivo}")
            self._responder(pid, rc, f"⛔ pedido rechazado: {motivo}.")
            return
        rc, texto = self.bw.atender(d["consulta"], {"noticias": d.get("noticias", False),
                                                    "semana": d.get("semana", False)},
                                    self.eid, cfg, self.origen)
        self._responder(pid, rc, texto)

    def _servir(self) -> None:
        while not self._parar.is_set():
            try:
                buenos, malos = self._pendientes()
            except OSError:
                buenos, malos = [], []          # la carpeta no está: se sigue hasta que la fase cierre
            for nombre_malo in malos:           # no hay un id válido al que contestarle
                self._hechos.add(nombre_malo)
                try:
                    self.bw.anotar_rechazo(self.eid, self.cfg or self.bw.config(), self.origen,
                                           "pedido malformado: nombre de archivo inválido")
                    (self.carpeta / nombre_malo).unlink()
                except Exception as e:
                    print(f"⚠️ buzón de búsquedas: {type(e).__name__} con un pedido mal nombrado", flush=True)
            for pid in buenos:
                if self._parar.is_set():
                    break
                try:
                    self._uno(pid)
                except Exception as e:          # nada de un pedido puede tirar el hilo; el texto no lleva str(e)
                    print(f"⚠️ buzón de búsquedas: {type(e).__name__} al atender un pedido", flush=True)
                    self._responder(pid, 5, f"⛔ error interno de la cola al buscar ({type(e).__name__}).")
            self._parar.wait(BUSQUEDA_SONDEO_S)

    def cerrar(self) -> None:
        """Fin de la fase: para el hilo (deja terminar la búsqueda en vuelo, que ya salió), contesta
        «fase terminada» a lo que quedó sin atender y borra la carpeta."""
        self._parar.set()
        self._hilo.join(BUSQUEDA_CIERRE_S)
        try:
            for pid in self._pendientes()[0]:
                self._hechos.add(pid)
                try:
                    (self.carpeta / f"pedido-{pid}.json").unlink()
                except OSError:
                    continue
                self._responder(pid, 2, self.bw.FASE_TERMINADA)
            limite = time.monotonic() + BUSQUEDA_GRACIA_S
            while time.monotonic() < limite and any(n.startswith("respuesta-") for n in os.listdir(self.carpeta)):
                time.sleep(0.05)
        except OSError:
            pass
        if self.carpeta.is_symlink():
            self.carpeta.unlink(missing_ok=True)
        else:
            shutil.rmtree(self.carpeta, ignore_errors=True)


def abrir_buzon_busquedas(mod: dict, nombre_log: str) -> BuzonBusquedas | None:
    """Buzón de búsquedas (32c) para las fases de autor (autor, fix1, fix2…) de una etapa
    `investigacion`, y solo si esta cola tiene nombre. Una carpeta nueva e impredecible (0700) bajo
    vivo/buzon/ y un hilo que la atiende hasta `cerrar()`. Revisores y otras naturalezas: None, y el
    script les contesta «solo la cola busca». Si no se puede abrir, la cola sigue sin buscador."""
    eid, fase = str(mod.get("encargo_id") or ""), nombre_log.partition("-")[2]
    cola = (MANIFIESTO or {}).get("nombre")
    if (mod.get("naturaleza") != "investigacion" or not eid or not fase or fase.startswith("rev")
            or not isinstance(cola, str) or not cola or SIMULANDO):
        return None
    carpeta = None
    try:
        raiz = E / "vivo" / "buzon"
        raiz.mkdir(parents=True, exist_ok=True)
        os.chmod(raiz, 0o700)
        carpeta = raiz / secrets.token_hex(16)
        os.mkdir(carpeta, 0o700)
        os.chmod(carpeta, 0o700)
        return BuzonBusquedas(carpeta, eid, fase, cola)
    except Exception as e:      # el buscador ayuda, no bloquea: sin buzón el autor no busca y la fase corre igual
        if carpeta:
            shutil.rmtree(carpeta, ignore_errors=True)
        print(f"⚠️ no se pudo abrir el buzón de búsquedas ({type(e).__name__}: {e}): esta fase corre sin buscador",
              flush=True)
        return None


GRUPO_TERM_S = 5.0          # 87b: tras TERM al grupo del CLI se espera esto antes del KILL
GRUPO_TUBERIAS_S = 10.0     # y, ya muerto el grupo, esto para vaciar sus tuberías


def procesos_del_grupo(pgid: int) -> list[int]:
    """Los PID vivos (no zombis) del grupo `pgid`, leídos de /proc. Sin /proc, lo que diga killpg(pgid, 0)."""
    try:
        entradas = os.listdir("/proc")
    except OSError:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return []
        except PermissionError:
            pass
        return [pgid]
    vivos = []
    for n in entradas:
        if not n.isdigit():
            continue
        try:
            with open(f"/proc/{n}/stat", "rb") as fh:
                campos = fh.read().decode("ascii", "replace").rsplit(")", 1)[-1].split()
        except OSError:
            continue
        # Tras el nombre entre paréntesis: estado, ppid, pgrp…
        if len(campos) > 2 and campos[2] == str(pgid) and campos[0] not in ("Z", "X"):
            vivos.append(int(n))
    return vivos


def terminar_grupo(pgid: int) -> list[int]:
    """TERM a todo el grupo, espera acotada, KILL y otra espera. Devuelve lo que siguió vivo (lo normal: [])."""
    for senal, espera in ((signal.SIGTERM, GRUPO_TERM_S), (signal.SIGKILL, 2.0)):
        if not procesos_del_grupo(pgid):
            return []
        try:
            os.killpg(pgid, senal)
        except ProcessLookupError:
            return []
        except PermissionError:
            pass
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            if not procesos_del_grupo(pgid):
                return []
            time.sleep(0.05)
    return procesos_del_grupo(pgid)


def ejecutar_cli(cmd: list[str], prompt: str, env: dict, limite_s: float | None = None) -> tuple[int, str, str, bool]:
    """(rc, stdout, stderr, cortado) del CLI de una fase, en TODAS las fases (87b, decisión de Diego).

    El CLI corre en una sesión propia, así que él y todo lo que lance comparten un grupo de procesos. Al vencer
    `limite_s`, o apenas el CLI termina, se mata el grupo entero (TERM, espera, KILL) y se comprueba que no
    quede nadie: un hijo suelto del revisor podría seguir escribiendo el árbol mientras corre la fase siguiente.
    `subprocess.run(timeout=…)` sólo mataba al proceso principal."""
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         cwd=D, env=env, start_new_session=True)
    # En su propia sesión el CLI ya no recibe el SIGHUP de `tmux kill-session` (detener) ni la señal que mate a
    # la cola: mientras corre, esas señales terminan primero su grupo y después la cola, como antes.
    previas = {}

    def morir(senal, _marco):
        terminar_grupo(p.pid)
        raise SystemExit(128 + senal)
    for senal in (signal.SIGHUP, signal.SIGTERM):
        try:
            previas[senal] = signal.signal(senal, morir)
        except ValueError:      # fuera del hilo principal no se pueden poner: queda el finally
            pass
    try:
        return _esperar_cli(p, prompt, limite_s)
    except BaseException:
        terminar_grupo(p.pid)   # Ctrl-C, SystemExit o un error: el grupo no queda corriendo
        raise
    finally:
        for senal, previa in previas.items():
            signal.signal(senal, previa)


def _esperar_cli(p: subprocess.Popen, prompt: str, limite_s: float | None) -> tuple[int, str, str, bool]:
    fin = None if limite_s is None else time.monotonic() + limite_s
    cortado, quedan, entrada = False, None, prompt
    while True:
        espera = 0.5 if fin is None else max(0.0, min(0.5, fin - time.monotonic()))
        try:
            out, err = p.communicate(entrada, timeout=espera)
            break
        except subprocess.TimeoutExpired:
            entrada = None          # communicate() ya tiene la entrada; reintentar no pierde salida
            if fin is not None and time.monotonic() >= fin:
                cortado = True
            # Corte por tiempo, o el CLI ya salió pero un hijo retiene sus tuberías: se mata el grupo.
            if cortado or p.poll() is not None:
                quedan = terminar_grupo(p.pid)
                try:
                    out, err = p.communicate(timeout=GRUPO_TUBERIAS_S)
                except subprocess.TimeoutExpired:   # alguien fuera del grupo (setsid) sigue con las tuberías
                    p.kill()
                    for tubo in (p.stdin, p.stdout, p.stderr):
                        if tubo:
                            tubo.close()
                    p.wait()
                    out, err = "", "[la salida quedó retenida por un proceso fuera del grupo]\n"
                break
    if quedan is None:
        quedan = terminar_grupo(p.pid)      # lo que el CLI dejó vivo al terminar
    if quedan:
        print(f"⚠️ quedaron procesos del CLI después del KILL: {quedan}", file=sys.stderr, flush=True)
    return p.returncode, out or "", err or "", cortado


def _correr(m: dict, cid: str, prompt: str, nombre_log: str, mod: dict, herramientas: str, env: dict,
            limite_s: float | None = None) -> dict:
    t0 = time.monotonic()
    if m["motor"] == "codex":
        cmd = ["codex", "exec", "--cd", str(D), "-s", "workspace-write", "--skip-git-repo-check",
               "--color", "never"]
        # El sandbox de Codex sólo escribe en --cd: las carpetas hermanas de `arboles_extra` se abren aparte,
        # y sólo las que pasan la validación de _repos_extra (con historial, sin enlaces), para que su diff se
        # revise (cola 59: sin esto, Codex no podía escribir en 14-App-Matrimonio).
        for n, _ in _repos_extra():
            cmd += ["--add-dir", str(D.parent / n)]
        if mod.get("modelo"):
            cmd += ["-m", mod["modelo"]]
        if mod.get("esfuerzo"):
            cmd += ["-c", f'model_reasoning_effort="{mod["esfuerzo"]}"']
        cmd.append("-")
    else:
        cmd = ["claude", "-p", "--output-format", "json", "--permission-mode", "acceptEdits",
               "--allowedTools", herramientas]
        if mod.get("modelo"):
            cmd += ["--model", mod["modelo"]]
        if mod.get("esfuerzo"):
            cmd += ["--effort", mod["esfuerzo"]]
    # Encargo 87: sólo el cierre pasa un límite. Un corte por tiempo no es un veredicto (escala). 87b: en toda
    # fase el CLI corre en su propio grupo de procesos y el grupo entero muere al cortar o al terminar.
    rc, stdout, stderr, cortado = ejecutar_cli(cmd, prompt, env, limite_s)
    if cortado:
        (L / f"{nombre_log}.log").write_text(stdout + f"\n[cortado a los {limite_s:.0f} s]\n", encoding="utf-8")
        return {"rc": 124, "min": round((time.monotonic() - t0) / 60, 1), "tokens": None, "sin_cuota": False,
                "modelo_real": None, "corte": "tiempo"}
    p = subprocess.CompletedProcess(cmd, rc, stdout, stderr)
    minutos = round((time.monotonic() - t0) / 60, 1)
    salida = (p.stdout or "") + (p.stderr or "")
    tokens, es_error, modelo_real = None, p.returncode != 0, None
    if m["motor"] == "claude":
        try:
            j = json.loads(p.stdout)
            modelo_real = ",".join((j.get("modelUsage") or {}).keys()) or None
            u = j.get("usage") or {}
            tokens = {"entrada": u.get("input_tokens"), "salida": u.get("output_tokens"),
                      "cache_lectura": u.get("cache_read_input_tokens"),
                      "cache_escritura": u.get("cache_creation_input_tokens"),
                      "usd": j.get("total_cost_usd")}
            es_error = es_error or bool(j.get("is_error"))
            (L / f"{nombre_log}.json").write_text(p.stdout, encoding="utf-8")
            salida = str(j.get("result") or "") + "\n" + (p.stderr or "")
        except (ValueError, TypeError):
            pass
    else:
        hallados = re.findall(r"tokens used\s*:?\s*([\d][\d,.]*)", salida)
        if hallados:
            tokens = {"total": int(re.sub(r"\D", "", hallados[-1]))}
        hallado = re.search(r"^model:\s*(\S+)", salida, re.M)
        modelo_real = hallado.group(1) if hallado else None
    (L / f"{nombre_log}.log").write_text(salida, encoding="utf-8")
    # Solo se mira el final y solo si algo salió mal: un log de Codex trae archivos enteros
    # y puede nombrar «usage limit» sin estar limitado.
    cola = "\n".join(salida.strip().splitlines()[-30:])
    sin_cuota = (es_error or len(salida) < 400) and bool(LIMITE.search(cola))
    return {"rc": p.returncode, "min": minutos, "tokens": tokens, "sin_cuota": sin_cuota,
            "modelo_real": modelo_real}


# ---------------------------------------------------------------- cuota

TRAMO_ESPERA_S = 300        # la espera duerme de a 5 min y en cada tramo deja latir vivo/<cola>.json
REMEDIR_S = 600             # y cada 10 min vuelve a medir: si ya alcanza, la cola sigue sin esperar la hora
CAMPOS_ESPERA = ("cuenta_clave", "calculo", "calculo_texto", "espera_desde", "reanuda", "pronostico_debil")


def ventanas_cuota(cid: str, f: dict, u: dict, momento: datetime | None = None) -> list[dict]:
    """La regla de la cola, como datos: por ventana, el % de ahora + el pronóstico de la fase contra
    el tope de la cuenta. Alcanza si `actual + pronostico <= tope`. Es lo que chequear_cuota decide,
    lo que muestra 🧵 Encargos y lo que lee la regla de aviso previo de avisos.py."""
    q = quema(cid, u, momento)
    tsem, t5 = topes(cid, u, momento)
    sem = {"ventana": "semanal", "etiqueta": "semanal", "actual": u["sem"], "pronostico": f["pct_sem"],
           "tope": tsem, "renueva": u.get("renueva_sem")}
    if q["activa"] or q["debil"]:
        sem.update(quemando=q["activa"], quemar_hasta=q["hasta"], debil=q["debil"])
    return [sem, {"ventana": "5h", "etiqueta": "5 h", "actual": u["5h"] or 0, "pronostico": f["pct_5h"],
                  "tope": t5, "renueva": u.get("renueva_5h")}]


def _alcanza(v: dict) -> bool:
    return v["actual"] + v["pronostico"] <= v["tope"]


def _texto_calculo(v: dict) -> str:
    hasta = _hora(v.get("quemar_hasta"))
    quemando = f" (quemando hasta {hasta.astimezone():%H:%M})" if v.get("quemando") and hasta else ""
    return f"{v['etiqueta']} {v['actual']:.0f} % + {v['pronostico']} % > tope {v['tope']} %{quemando}"


def _etapa_fase(desde: str) -> tuple[str, str]:
    et, _, fase = desde.partition(":")
    return et, fase


def _entrar_en_espera(cid: str, f: dict, malos: list[dict], desde: str, desde_ts: float, hasta: float, modelo: str = "") -> None:
    et, fase = _etapa_fase(desde)
    vivo(estado="esperando_cuota", etapa=et, fase=fase, cuenta=nombre(cid), cuenta_clave=cid, modelo=modelo or None,
         calculo=[{k: v[k] for k in ("ventana", "actual", "pronostico", "tope")} for v in malos],
         calculo_texto="; ".join(_texto_calculo(v) for v in malos),
         espera_desde=datetime.fromtimestamp(desde_ts).astimezone().isoformat(timespec="seconds"),
         reanuda=datetime.fromtimestamp(hasta).astimezone().isoformat(timespec="seconds"),
         pronostico_debil=bool(f["debil"]))


def _salir_de_espera(desde_ts: float, vuelve: bool) -> None:
    """Quita los campos de la espera y corre `inicio_trabajo` por el tiempo muerto, para que la barra
    no cuente la espera como trabajo hecho (barra.js no necesita otro cálculo)."""
    muerto = max(0.0, ahora().timestamp() - desde_ts)
    for k in CAMPOS_ESPERA:
        VIVO.pop(k, None)
    cambios = {"tiempo_muerto_min": round(VIVO.get("tiempo_muerto_min", 0) + muerto / 60, 1)}
    if VIVO.get("inicio_trabajo"):
        cambios["inicio_trabajo"] = (datetime.fromisoformat(VIVO["inicio_trabajo"])
                                     + timedelta(seconds=muerto)).isoformat(timespec="seconds")
    if vuelve:
        # Sin fase anterior (la primera de la cola) todavía no hay `inicio_fase`: etapa() fija «corriendo» enseguida.
        cambios["estado"] = "corriendo" if VIVO.get("inicio_fase") else "partiendo"
    vivo(**cambios)


def _dormir_hasta(hasta: float, cid: str, rol: str, modelo: str, esfuerzo: str = "") -> None:
    """Duerme hasta `hasta` en tramos de 5 min. En cada tramo refresca `escrito` (vivo()); cada 10 min
    vuelve a medir y, si la cuenta ya alcanza (el usuario gastó menos, o la ventana se renovó antes),
    deja de esperar. El que llama vuelve a medir antes de seguir."""
    ultima = ahora().timestamp()
    while True:
        resto = hasta - ahora().timestamp()
        if resto <= 0:
            return
        time.sleep(min(TRAMO_ESPERA_S, max(1.0, resto)))
        vivo()
        if ahora().timestamp() - ultima >= REMEDIR_S:
            ultima = ahora().timestamp()
            u = medir(cid)
            f = pronostico(cid, rol, modelo, "", esfuerzo)
            cuota = dict(f, pct_5h=f["pct_5h_p75"], pct_sem=f["pct_sem_p75"])
            if u["sem"] is not None and all(_alcanza(v) for v in ventanas_cuota(cid, cuota, u)):
                return


def chequear_cuota(cid: str, rol: str, desde: str, modelo: str = "", esfuerzo: str = "") -> tuple[dict, dict]:
    """Si cid no alcanza para la fase: espera la renovación (si cae dentro de la paciencia) o
    lanza Pausa. Devuelve (pronóstico, medición de antes) para no medir dos veces.
    Paciencia: `paciencia_h` del manifiesto (por defecto 1 h). Una cola que «puede correr de
    noche» lleva 10 o 12 y espera las renovaciones que hagan falta en vez de pausarse (03-10).
    Encargo 24: la espera se VE. vivo/<cola>.json pasa a `esperando_cuota` con el cálculo, la hora de
    reanudación y la ETA corrida; late cada 5 min; y avisa por texto simple, no por una línea."""
    limite = ahora().timestamp() + float(MANIFIESTO.get("paciencia_h", 1)) * 3600
    espera_desde = anunciado = None
    try:
        while True:
            f, u = pronostico(cid, rol, modelo, "", esfuerzo), medir(cid)
            if u["sem"] is None:
                raise Pausa(f"no hay dato de cuota semanal de {nombre(cid)} ({u['fuente']})", desde)
            cuota = dict(f, pct_5h=f["pct_5h_p75"], pct_sem=f["pct_sem_p75"])
            malos = [v for v in ventanas_cuota(cid, cuota, u) if not _alcanza(v)]
            if not malos:
                if espera_desde is not None:
                    log(f"▶️ {nombre(cid)} ya alcanza para {rol}: la cola sigue")
                    ts, espera_desde = espera_desde, None
                    _salir_de_espera(ts, vuelve=True)
                return f, u
            calculo = "; ".join(_texto_calculo(v) for v in malos)
            motivo = f"{nombre(cid)} sin margen para {rol}: {calculo}"
            # Hay que esperar a que se renueven TODAS las ventanas que no alcanzan.
            rens = [v["renueva"] for v in malos]
            if all(rens):
                hasta = max(rens).timestamp() + 120
                if hasta <= limite:
                    if espera_desde is None:
                        espera_desde = ahora().timestamp()
                    _entrar_en_espera(cid, f, malos, desde, espera_desde, hasta, modelo)
                    if anunciado != hasta:
                        log(f"⏳ {motivo}. Se renueva a las {max(rens).astimezone():%d-%m %H:%M}: la cola espera "
                            f"(paciencia hasta las {datetime.fromtimestamp(limite).astimezone():%d-%m %H:%M})")
                        if hasta - ahora().timestamp() > 15 * 60:
                            sigue = datetime.fromtimestamp(hasta).astimezone()
                            cuando = f"{sigue:%H:%M}" + (f" del {sigue:%d-%m}" if sigue.date() != ahora().date() else "")
                            avisar_texto(f"⏳ La cola {MANIFIESTO['nombre']} espera la cuota de {nombre(cid)}: {calculo}. "
                                         f"Sigue sola a las {cuando}; no hay que hacer nada.",
                                         viejo=(f"⏳ Cola {MANIFIESTO['nombre']} en espera: {motivo}. Sigue sola a las "
                                                f"{max(rens).astimezone():%H:%M} del {max(rens).astimezone():%d-%m}; no hay que hacer nada. "
                                                "Esta línea muestra el estado.", f"cat {ESTADO}"))
                        anunciado = hasta
                    _dormir_hasta(hasta, cid, rol, modelo, esfuerzo)
                    continue
            raise Pausa(motivo, desde)
    finally:
        if espera_desde is not None:      # salió por una Pausa o por un error: el que llama fija su estado
            _salir_de_espera(espera_desde, vuelve=False)


def anotar(enc_id: str, fase: str, cid: str, rol: str, f: dict, antes: dict, r: dict,
           mod: dict, veredicto=None, donde: str = ""):
    despues = dict(SIN_MEDIR) if donde else medir(cid)   # la cuota de otro equipo no se ve desde acá
    fresco = antes.get("fuente") == "fresco" and despues.get("fuente") == "fresco"
    fila = {"encargo": enc_id, "fase": fase, "rol": rol, "cuenta": cid, "motor": MOTORES[cid]["motor"],
            "modelo": mod.get("modelo", ""), "esfuerzo": mod.get("esfuerzo", ""), "nivel": mod.get("nivel"),
            "naturaleza": mod.get("naturaleza"), "modelo_real": r.get("modelo_real"),
            "inicio": r["inicio"], "min": r["min"], "tokens": r["tokens"], "sin_cuota": r["sin_cuota"],
            "pct_5h": [antes["5h"], despues["5h"]], "pct_sem": [antes["sem"], despues["sem"]],
            "uso_momento": [antes["momento"], despues["momento"]],
            "medicion": "no medido" if donde else "fresco" if fresco else "uso.json", "veredicto": veredicto,
            "pronostico": {k: f[k] for k in ("min", "pct_5h", "pct_sem", "debil", "por_factor")}}
    if donde:
        fila.update(donde=donde, min_motor=r.get("min_motor"))
    with HISTORIAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fila, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- buzón de PC-2503 (encargo 23d)
# Una etapa con `donde = "pc2503"` corre un arnés laboral en ese equipo. La Pi no lo alcanza por
# red (Tailscale tiene los relays cortados), así que el pedido viaja por una carpeta de Syncthing:
#   pendientes/<id>.toml   lo escribe SOLO la Pi (este archivo)
#   estado/<id>.json       lo escribe SOLO PC-2503 (pc2503/trabajador.py), con el informe al lado
# Los datos de CyD no pasan por acá: del trabajo solo vuelve estado/<id>-RESULTADO.md.

SIN_MEDIR = {"5h": None, "sem": None, "renueva_5h": None, "renueva_sem": None, "momento": None,
             "fuente": "no medido"}
_TR_MOD = None


def _tr_mod():
    """pc2503/trabajador.py del vault: la lista fija de arneses y la validación son las del
    trabajador, para no escribir un pendiente que allá se rechazaría."""
    global _TR_MOD
    if _TR_MOD is None:
        spec = importlib.util.spec_from_file_location("trabajador_pc2503", D / "pc2503/trabajador.py")
        _TR_MOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_TR_MOD)
    return _TR_MOD


def remota(et: dict) -> bool:
    return et.get("donde", "pi") == "pc2503"


def donde_fase(et: dict, rol: str) -> str:
    """"pc2503" si ese rol de la etapa corre allá. La revisión corre siempre en la Pi."""
    return "pc2503" if remota(et) and rol != "rev" else ""


def id_remoto(et: dict) -> str:
    return f"{MANIFIESTO['nombre']}-{et['id']}".lower()


def buzon_dir() -> Path:
    return Path(MANIFIESTO.get("buzon") or BUZON)


def _abrir_carpeta(carpeta: Path, crear: bool = False) -> int:
    """Descriptor de una subcarpeta del buzón, abierta UNA vez y sin seguir enlaces. Lo que se lea
    o escriba después va con `dir_fd` a ESA carpeta: mirar si es un enlace y después operar por la
    ruta deja una ventana, y si Syncthing cambia la carpeta por un enlace justo ahí la Pi termina
    fuera del buzón. OSError si es un enlace o no es una carpeta."""
    raiz = os.open(carpeta.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if crear:
            try:
                os.mkdir(carpeta.name, dir_fd=raiz)
            except FileExistsError:
                pass
        try:
            return os.open(carpeta.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=raiz)
        except FileNotFoundError:
            raise
        except OSError as e:
            raise OSError(f"{carpeta} es un enlace simbólico o no es una carpeta: no se toca") from e
    finally:
        os.close(raiz)


def _leer_del_buzon(ruta: Path, tope: int | None = None) -> bytes:
    """Los bytes de un archivo del buzón, sin seguir enlaces ni en su carpeta ni en el archivo, y
    midiendo el mismo archivo que se lee. OSError si no está, si no es un archivo corriente o si
    pesa más que `tope`."""
    carpeta = _abrir_carpeta(ruta.parent)
    try:
        fd = os.open(ruta.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=carpeta)
    finally:
        os.close(carpeta)
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError(f"{ruta} no es un archivo corriente")
        datos = fh.read() if tope is None else fh.read(tope + 1)
    if tope is not None and (st.st_size > tope or len(datos) > tope):
        raise OSError(f"{ruta} pesa más de {tope} bytes")
    return datos


def _escribir_pendiente(pend: Path, datos: bytes) -> None:
    """Entero o nada, y sin seguir enlaces: Syncthing trae enlaces simbólicos, y uno puesto en
    `pendientes/` desde el otro equipo haría que la Pi escribiera fuera del buzón. El temporal y
    el reemplazo se hacen dentro de la carpeta ya abierta, no por la ruta."""
    carpeta = _abrir_carpeta(pend.parent, crear=True)
    tmp = f".{pend.name}.tmp"
    try:
        try:
            os.unlink(tmp, dir_fd=carpeta)       # borra el nombre: si era un enlace, no su destino
        except FileNotFoundError:
            pass
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=carpeta)
        with os.fdopen(fd, "wb") as fh:
            fh.write(datos)
        # Reemplaza el nombre: si era un enlace, no escribe en su destino.
        os.replace(tmp, pend.name, src_dir_fd=carpeta, dst_dir_fd=carpeta)
    finally:
        os.close(carpeta)


def _num(x) -> bool:
    """Un número de verdad: ni bool, ni NaN, ni infinito (json.loads los acepta y después
    historial.jsonl dejaría de ser JSON para la página)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def _limpio_remoto(est: dict) -> dict:
    """Lo que la Pi guarda de un estado de PC-2503: números y textos cortos, nada más."""
    tokens = est.get("tokens")
    if isinstance(tokens, dict):
        tokens = {str(k)[:30]: v for k, v in list(tokens.items())[:12] if v is None or _num(v)}
    veredicto = est.get("veredicto") if est.get("veredicto") in ("DESPLEGABLE", "NO DESPLEGABLE") else None
    modelo = _una_linea(est.get("modelo_real"), 80) if isinstance(est.get("modelo_real"), str) else None
    return {"tokens": tokens, "veredicto": veredicto, "modelo_real": modelo or None,
            "rc": est.get("rc") if _num(est.get("rc")) else None}


def validar_remotas(etapas: list[dict]) -> None:
    """Revisa las etapas `donde = "pc2503"` antes de correr nada. ValueError con el motivo."""
    for et in etapas:
        i = et.get("id", "?")
        if et.get("donde", "pi") not in ("pi", "pc2503"):
            raise ValueError(f"etapa {i}: donde = «{et['donde']}» no existe (pi | pc2503)")
        if not remota(et):
            continue
        tr = _tr_mod()
        for k in ("arnes", "prompt"):
            if not isinstance(et.get(k), str) or not et[k]:
                raise ValueError(f"etapa {i}: con donde = \"pc2503\" falta `{k}` (el arnés de la lista fija "
                                 "y su prompt en vault_trabajo; ver pc2503/BUZON.md)")
        if not tr.RE_ID.fullmatch(id_remoto(et)):
            raise ValueError(f"etapa {i}: «{id_remoto(et)}» no sirve como id del buzón (minúsculas, números "
                             "y guiones; hasta 63 caracteres)")
        # Los arreglos no se despachan: llevarían a un motor de PC-2503 un texto escrito en la Pi,
        # que es justo lo que el buzón no admite. Si la revisión rechaza, la cola se detiene.
        if int(et.get("vueltas", 0)) != 0:
            raise ValueError(f"etapa {i}: una etapa en PC-2503 no admite arreglos automáticos; quita "
                             "`vueltas` o déjalo en 0")
        et["vueltas"] = 0
        _, motivo = tr.validar(pedido_remoto(et, modelo_de(et, "autor"), {"min": 1}), id_remoto(et), VAULT_TRABAJO)
        if motivo:
            raise ValueError(f"etapa {i}: el trabajador de PC-2503 rechazaría el pendiente: {motivo}")


def pedido_remoto(et: dict, mod: dict, f: dict) -> dict:
    """El manifiesto del pendiente, con el sha256 del prompt tal como está AHORA en la copia de
    vault_trabajo de la Pi. Si en PC-2503 hay otra versión, el trabajador lo rechaza."""
    tr = _tr_mod()
    carpeta = (tr.ARNESES.get(et["arnes"]) or {}).get("carpeta", "")
    try:
        sha_prompt = hashlib.sha256((VAULT_TRABAJO / carpeta / et["prompt"]).read_bytes()).hexdigest()
    except (OSError, ValueError):
        sha_prompt = "0" * 64      # no existe o no se puede leer: validar() dice cuál de las dos
    emitido = ahora()
    vence = emitido + timedelta(hours=float(MANIFIESTO.get("paciencia_h", 1)))
    return {"version": tr.VERSION, "id": id_remoto(et), "cola": MANIFIESTO["nombre"], "etapa": str(et["id"]),
            "fase": "autor", "arnes": et["arnes"], "prompt": et["prompt"], "prompt_sha256": sha_prompt,
            "motor": MOTORES[et["autor"]]["motor"], "modelo": mod.get("modelo") or "",
            "esfuerzo": mod.get("esfuerzo") or "", "cuenta": nombre(et["autor"])[:40],
            "pronostico_min": f["min"], "emitido": emitido.isoformat(timespec="seconds"),
            "vence": vence.isoformat(timespec="seconds"), "nonce": secrets.token_hex(8),
            "motivo": " ".join(str(MANIFIESTO.get("motivo", "")).split())[:400]}


PEDIDO_IGUAL = ("arnes", "prompt", "prompt_sha256", "motor", "modelo", "esfuerzo")   # lo que define el trabajo


def _toml(pedido: dict) -> bytes:
    """El pendiente como TOML plano. json.dumps da cadenas que TOML lee igual (comillas dobles y
    los mismos escapes); ensure_ascii evita cualquier carácter de control suelto."""
    cab = ("# Pendiente del buzón de encargos (pc2503/BUZON.md). Lo escribe la Pi; PC-2503 solo lo lee.\n"
           "# No lleva comandos: el trabajador rechaza cualquier campo que no conozca.\n")
    return (cab + "".join(f"{k} = {json.dumps(v, ensure_ascii=True)}\n" for k, v in pedido.items())).encode("utf-8")


def _leer_pendiente(ruta: Path) -> tuple[str, dict] | None:
    try:
        datos = _leer_del_buzon(ruta, _tr_mod().TOPE_MANIFIESTO)
        return hashlib.sha256(datos).hexdigest(), tomllib.loads(datos.decode("utf-8"))
    except (OSError, ValueError):
        return None


def leer_estado_remoto(pid: str, sha_pend: str) -> dict | None:
    """estado/<pid>.json si es de ESTE pendiente (mismo sha256) y tiene la forma esperada. Un
    estado de un envío anterior con el mismo id, o uno a medio llegar, es como si no hubiera."""
    try:
        d = json.loads(_leer_del_buzon(buzon_dir() / "estado" / f"{pid}.json", TOPE_ESTADO).decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not (isinstance(d, dict) and d.get("id") == pid and d.get("manifiesto_sha") == sha_pend
            and d.get("estado") in ("corriendo", *_tr_mod().FINALES) and _num(d.get("minutos"))
            and 0 <= d["minutos"] < 100000
            and isinstance(d.get("tokens"), (dict, type(None))) and isinstance(d.get("vivo"), dict)):
        return None
    return d


def _informe(pid: str, est: dict) -> str | None:
    """El RESULTADO que PC-2503 copió al buzón, solo si es exactamente el que anuncia su estado
    (Syncthing puede traer el .json antes que el .md, o quedar el informe de un envío anterior).
    La ruta la arma la Pi: del estado solo se usa el sha256."""
    tr = _tr_mod()
    if est.get("estado") != "terminado" or est.get("resultado") != f"{pid}-RESULTADO.md":
        return None
    try:
        datos = _leer_del_buzon(buzon_dir() / "estado" / f"{pid}-RESULTADO.md", tr.TOPE_RESULTADO)
        return datos.decode("utf-8") if hashlib.sha256(datos).hexdigest() == est.get("resultado_sha256") else None
    except (OSError, ValueError):
        return None


def _una_linea(texto, tope: int = 300) -> str:
    return " ".join(str(texto or "").split())[:tope]


def despachar(et: dict, fase: str, mod: dict, f: dict, desde: str, reanuda: bool) -> dict:
    """Escribe pendientes/<id>.toml y espera el estado final de PC-2503, hasta `paciencia_h`.
    Devuelve lo mismo que correr(), más `min_motor`, `veredicto` y `problema` (por qué no sirve,
    o ""). Lanza Pausa si no se puede despachar o si se acaba la paciencia."""
    tr = _tr_mod()
    buzon, pid = buzon_dir(), id_remoto(et)
    if not (buzon / ".stfolder").exists():
        raise Pausa(f"el buzón {buzon} no existe o Syncthing no lo lleva (falta .stfolder): hay que "
                    "emparejar la Pi con PC-2503 (pc2503/EMPAREJAR.md)", desde)
    pedido = pedido_remoto(et, mod, f)
    _, motivo = tr.validar(pedido, pid, VAULT_TRABAJO)
    if motivo:
        raise Pausa(f"no se escribe el pendiente {pid}: el trabajador de PC-2503 lo rechazaría ({motivo})", desde)
    pend = buzon / "pendientes" / f"{pid}.toml"
    sha_pend, t0 = None, time.monotonic()
    previo = _leer_pendiente(pend)
    if previo:
        sha_prev, man = previo
        est = leer_estado_remoto(pid, sha_prev)
        mismo = all(man.get(k) == pedido[k] for k in PEDIDO_IGUAL)
        try:
            vencido = time.time() > datetime.fromisoformat(man["vence"]).timestamp() + MARGEN_RELOJ_S
        except (KeyError, TypeError, ValueError):
            vencido = False
        if est and est["estado"] in tr.FINALES:
            if reanuda and mismo and _informe(pid, est) is not None:
                log(f"{et['id']}: PC-2503 ya había terminado {pid}; se usa ese resultado")
                sha_pend = sha_prev
        elif est is None and vencido:
            log(f"{et['id']}: el pendiente {pid} venció sin que PC-2503 lo tomara; se emite de nuevo")
        elif mismo:
            log(f"{et['id']}: el pendiente {pid} ya estaba en vuelo; se sigue esperando el mismo")
            sha_pend = sha_prev
        else:
            # No se pisa: el trabajador puede estar corriéndolo, y pisarlo corre el arnés dos veces.
            raise Pausa(f"en el buzón hay otro pedido en vuelo con el id {pid} (otro prompt o modelo). "
                        f"Espera a que PC-2503 lo termine o borra {pend}", desde)
    if sha_pend is None:
        datos = _toml(pedido)
        try:
            _escribir_pendiente(pend, datos)
        except OSError as e:
            raise Pausa(f"no se pudo escribir el pendiente {pid} en el buzón ({type(e).__name__}: {e})", desde)
        sha_pend = hashlib.sha256(datos).hexdigest()
        log(f"{et['id']}: pendiente {pid} escrito en el buzón ({et['arnes']} · {et['prompt']}); "
            "PC-2503 lo toma en su próxima pasada (cada 5 min)")
    limite = time.time() + float(MANIFIESTO.get("paciencia_h", 1)) * 3600
    tomado, est = False, None
    while True:
        est = leer_estado_remoto(pid, sha_pend)
        if est and not tomado:
            tomado = True
            if est["estado"] == "corriendo":
                log(f"{et['id']}: {_una_linea(est.get('equipo'), 40) or 'PC-2503'} tomó el pendiente")
        if est and est["estado"] in tr.FINALES and (est["estado"] != "terminado" or not est.get("resultado")
                                                    or _informe(pid, est) is not None):
            break
        if time.time() >= limite:
            que = (f"seguía corriendo (última señal a las {str((est or {}).get('escrito', ''))[11:16]})" if tomado
                   else "nunca lo tomó (¿equipo apagado, sin la tarea programada o sin sincronizar?)")
            raise Pausa(f"PC-2503 no terminó {pid} en {MANIFIESTO.get('paciencia_h', 1)} h: {que}", desde)
        if est:
            vivo(remoto={"estado": est["estado"], "minutos": est["minutos"], "escrito": _una_linea(est.get("escrito"), 40)})
        time.sleep(BUZON_SONDEO_S)
    vivo(remoto={"estado": est["estado"], "minutos": est["minutos"], "escrito": _una_linea(est.get("escrito"), 40)})
    problema = ""
    if est["estado"] in ("rechazado", "error", "cortado"):
        problema = f"PC-2503 no corrió {pid} ({est['estado']}): {_una_linea(est.get('motivo')) or 'sin motivo'}"
    elif est["estado"] == "terminado" and not est.get("resultado"):
        problema = (f"PC-2503 terminó {pid} sin dejar RESULTADO en el buzón "
                    f"({_una_linea(est.get('motivo')) or 'sin motivo'}): no hay qué revisar")
    limpio = _limpio_remoto(est)
    return {"rc": limpio["rc"], "min": round((time.monotonic() - t0) / 60, 1), "min_motor": est["minutos"],
            "tokens": limpio["tokens"], "sin_cuota": est["estado"] == "sin-cuota",
            "modelo_real": limpio["modelo_real"], "veredicto": limpio["veredicto"], "problema": problema}


def informe_remoto(et: dict, desde: str) -> str:
    """El RESULTADO de PC-2503 para la revisión en la Pi. Pausa si no está el que corresponde."""
    pid = id_remoto(et)
    previo = _leer_pendiente(buzon_dir() / "pendientes" / f"{pid}.toml")
    est = leer_estado_remoto(pid, previo[0]) if previo else None
    informe = _informe(pid, est) if est else None
    if informe is None:
        raise Pausa(f"no está en el buzón el RESULTADO de {pid} que corresponde al pendiente: no hay qué "
                    f"revisar. Vuelve a despachar desde {et['id']}:autor", desde)
    return informe


# ---------------------------------------------------------------- etapa

FASES = ["autor", "rev1", "fix1", "rev2", "fix2", "rev3"]
FASES_PLAN = ["plan", "revplan", "plan2", "revplan2"]


def prompt_de(fase: str, et: dict, reanuda: bool, informe: str = "", diff: str = "") -> str:
    autor, revisor, enc, i = nombre(et["autor"]), nombre(et["revisor"]), et.get("encargo", ""), et["id"]
    if remota(et):
        # Solo existe la revisión: el autor corre en PC-2503 y los arreglos no se despachan.
        txt = PLANTILLA_REV_PC2503.read_text(encoding="utf-8")
        for k, val in {"{ID}": i, "{ARNES}": et["arnes"], "{PROMPT}": et["prompt"], "{REVISOR}": revisor,
                       "{AUTOR}": f"{autor} en PC-2503", "{DIR}": str(D)}.items():
            txt = txt.replace(k, val)
        return txt.replace("{INFORME}", informe)   # al final: el informe no pasa por los reemplazos
    if fase.startswith("plan"):
        vuelta = "corrige" if fase == "plan2" else "escribe"
        previo = (f" Lee el rechazo anterior en encargos/{i}rplan-RESULTADO.md y" if fase == "plan2" else "")
        return (f"# Plan del encargo {i} (lo ejecuta {autor})\n\nTrabajas en {D}. Lee encargos/{enc}.{previo} "
                f"{vuelta.capitalize()} solamente encargos/{i}-PLAN.md; no toques código ni ningún otro archivo. "
                "El plan debe caber en una página e incluir: enfoque; archivos y funciones que tocará; premisas "
                "comprobadas con comando y salida; y pruebas de aceptación C1…Cn con el dato real que usan. "
                "No ejecutes ni lances una cola, no uses buscador web y no modifiques el encargo.\n")
    if fase.startswith("revplan"):
        return (f"# Revisión del plan del encargo {i} (la ejecuta {revisor})\n\nTrabajas en {D}. Lee encargos/{enc} "
                f"y encargos/{i}-PLAN.md. No modifiques código ni el plan. Comprueba que cabe en una página y que "
                "explicita enfoque, archivos y funciones, premisas verificadas con comando y salida, y cada criterio "
                "C1…Cn con su dato real. Escribe encargos/"
                f"{i}rplan-RESULTADO.md con los motivos. La última línea debe ser exactamente PLAN APROBADO o PLAN RECHAZADO.\n")
    if fase == "autor":
        cuerpo = (E / enc).read_text(encoding="utf-8")
        cab = f"Lo ejecuta {autor}. Lo va a revisar {revisor}.\n\n"
        if et.get("plan"):
            cab += (f"El plan aprobado es parte obligatoria de esta instrucción:\n\n"
                    f"--- encargos/{i}-PLAN.md ---\n{(E / f'{i}-PLAN.md').read_text(encoding='utf-8')}\n--- fin del plan ---\n\n")
        if et.get("naturaleza") == "investigacion":
            cab += (f"Para buscar en la web tienes `python3 {E}/buscar-web.py \"consulta\"` (Tavily; "
                    "`--noticias` y `--semana` opcionales). Mándale SOLO la pregunta pública, nunca "
                    "contenido, rutas ni nombres del vault: el script rechaza lo que lo parezca, y "
                    f"cada consulta queda en encargos/{i}-busquedas.jsonl, que lee {revisor}.\n\n")
        if reanuda:
            cab += ("Una corrida anterior de este encargo se cortó por cuota. Antes de seguir, mira "
                    f"qué quedó hecho en el vault y en encargos/{i}-RESULTADO.md (si existe) y termina "
                    "lo que falte; no rehagas lo que ya está bien.\n\n")
        return cab + cuerpo
    v = int(fase[-1])
    if fase.startswith("rev"):
        extra = (f"Esta es la revisión número {v}; si hay revisiones anteriores "
                 f"(encargos/{i}r*-RESULTADO.md), verifica que sus hallazgos quedaron cerrados.")
        txt = PLANTILLA_REV.read_text(encoding="utf-8")
        for k, val in {"{ID}": i, "{ENCARGO}": enc, "{AUTOR}": autor, "{REVISOR}": revisor,
                       "{EXTRA}": extra, "{SUITES}": ", ".join(MANIFIESTO["pruebas"]),
                       "{DIFF}": diff or "(no hay diff de esta etapa: el historial git no estaba disponible)"}.items():
            txt = txt.replace(k, val)
        return txt
    plan_aprobado = (f"\nPlan aprobado que también debes respetar:\n\n--- encargos/{i}-PLAN.md ---\n"
                     f"{(E / f'{i}-PLAN.md').read_text(encoding='utf-8')}\n--- fin del plan ---\n" if et.get("plan") else "")
    return (f"# Arreglos del encargo {i}, vuelta {v} (lo ejecuta {autor})\n"
            f"Trabajas en {D}. Lee encargos/{enc} (el encargo) y encargos/{i}r{v}-RESULTADO.md (la "
            f"revisión de {revisor}, que lo declaró NO DESPLEGABLE). Corrige TODOS los hallazgos "
            "graves y medios, cada uno con una prueba sobre la forma REAL de los datos. No hagas "
            f"trampa con las pruebas. Agrega a encargos/{i}-RESULTADO.md una sección «Arreglos "
            f"vuelta {v}» que diga, por hallazgo, qué cambió y qué prueba lo cubre, con la salida "
            f"real de las suites ({', '.join(MANIFIESTO['pruebas'])}). Reglas: sin sudo, sin "
            "desplegar, sin tocar n8n en vivo ni los perfiles, LF, reemplazos puntuales. Las cuentas "
            "se nombran «Claude (Diego)», «Claude (Cami)» y «Codex». Nadie está mirando: si algo es "
            "ambiguo, elige lo más conservador y anótalo.\n" + plan_aprobado
            + (f"\nLee también encargos/{i}-decisiones.md: son decisiones del usuario sobre esta etapa (encargo 51). Lo "
               "que el usuario aceptó ahí no se arregla ni se vuelve a discutir; una decisión nunca autoriza root, "
               "secretos ni ampliar el alcance.\n" if (E / f"{i}-decisiones.md").is_file() else ""))


# ---------------------------------------------------------------- cierre barato (encargo 87)

def cierre_aplica(et: dict, fase: str | None = None) -> bool:
    """La etapa pidió `cierre_barato = true` (sólo el booleano verdadero) y no es remota; con `fase`, además
    es una revisión desde la segunda (rev2, rev3…). Sin el campo, nada del cierre corre ni se pronostica."""
    if et.get("cierre_barato") is not True or remota(et):
        return False
    return fase is None or (fase.startswith("rev") and fase[3:].isdigit() and int(fase[3:]) >= 2)


def _numstat(antes: str, despues: str) -> list[tuple[str, str, str]]:
    """(agregadas, borradas, ruta) de cada archivo entre dos fotos; un binario trae «-». Sin renombres: un
    archivo movido aparece con sus dos rutas."""
    salida = _vers().abrir().git("diff", "--no-color", "--no-renames", "--numstat", "-z", antes, despues, "--").stdout
    out = []
    for x in salida.decode("utf-8", "replace").split("\0"):
        if x:
            mas, menos, ruta = x.split("\t", 2)
            out.append((mas, menos, ruta))
    return out


def _sensible(ruta: str) -> bool:
    return any(fnmatch.fnmatchcase(ruta, patron) for patron in RUTAS_SENSIBLES) or bool(RE_SECRETO.search(ruta))


class InformeInseguro(ValueError):
    """87b: un informe del cierre que no se puede leer con seguridad. Siempre escala a la revisión completa."""


def leer_informe(ruta: Path) -> str:
    """El texto de un informe de encargos/ que lee el cierre, sin seguir enlaces: O_NOFOLLOW, archivo regular de
    un solo nombre, acotado a CIERRE_MAX_BYTES, UTF-8 y con su carpeta resuelta igual a encargos/. Un arreglo
    puede reemplazar <id>-RESULTADO.md por un enlace a algo de afuera y E1 no lo ve (sólo compara nombres): lo
    que no pasa esto no llega al prompt. Cualquier falla, también un archivo que falta, es InformeInseguro."""
    try:
        if ruta.parent.resolve(strict=True) != E.resolve(strict=True) or "/" in ruta.name:
            raise InformeInseguro(f"encargos/{ruta.name} no queda bajo encargos/")
        fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except InformeInseguro:
        raise
    except OSError as e:
        raise InformeInseguro(f"encargos/{ruta.name} no se puede abrir sin seguir enlaces ({type(e).__name__})") from e
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise InformeInseguro(f"encargos/{ruta.name} no es un archivo regular de un solo nombre")
        if st.st_size > CIERRE_MAX_BYTES:
            raise InformeInseguro(f"encargos/{ruta.name} pasa de {CIERRE_MAX_BYTES // 1024} KiB")
        with os.fdopen(fd, "rb", closefd=False) as fh:
            crudo = fh.read(CIERRE_MAX_BYTES + 1)
        if len(crudo) > CIERRE_MAX_BYTES:
            raise InformeInseguro(f"encargos/{ruta.name} pasa de {CIERRE_MAX_BYTES // 1024} KiB")
        return crudo.decode("utf-8")
    except UnicodeDecodeError as e:
        raise InformeInseguro(f"encargos/{ruta.name} no es UTF-8") from e
    except OSError as e:
        raise InformeInseguro(f"encargos/{ruta.name} no se pudo leer ({type(e).__name__})") from e
    finally:
        os.close(fd)


def decidir_cierre(et: dict, fase: str) -> tuple[bool, str, list[tuple[str, str]]]:
    """(cierre, motivo, [(antes, despues)] del arreglo) para la `fase` (rev2, rev3…). Sólo mira las fotos git
    propias de la etapa (GIT_BASE) y git: nunca un archivo que escriba el autor (trampa 32b). Ante cualquier
    duda devuelve False y la revisión es la completa (E1–E4 del encargo 87)."""
    i, fix = et["id"], f"fix{int(fase[3:]) - 1}"
    try:
        if MANIFIESTO.get("arboles_extra"):
            return False, "E4: la cola tiene `arboles_extra` y el diff del arreglo no se verifica entero", []
        if not (E / f"{i}r{int(fase[3:]) - 1}-RESULTADO.md").is_file():
            return False, f"E4: falta encargos/{i}r{int(fase[3:]) - 1}-RESULTADO.md", []
        # 87b: lo que el cierre va a pegar en su prompt se valida antes de decidir (y se vuelve a leer igual).
        for informe in (f"{i}r{int(fase[3:]) - 1}-RESULTADO.md", f"{i}-RESULTADO.md"):
            leer_informe(E / informe)
        fases = GIT_BASE.get(f"{i}:fases")
        fases = [f for f in fases if isinstance(f, dict)] if isinstance(fases, list) else []
        pos = [k for k, f in enumerate(fases) if f.get("fase") == fix]
        if not pos:
            return False, f"E4: no hay foto de {fix}", []
        if not any(f.get("fase") == "autor" for f in fases[:pos[0]]):
            return False, "E4: no hay foto del autor", []
        for f in fases[:pos[-1] + 1]:
            if not all(isinstance(f.get(k), str) and RE_HASH_GIT.fullmatch(f[k]) for k in ("antes", "despues")):
                return False, f"E4: la fase {f.get('fase', '?')} no tiene foto antes y después", []
        previos = {ruta for f in fases[:pos[0]] if f.get("fase") != fix
                   for _, _, ruta in _numstat(f["antes"], f["despues"])}
        pares = [(fases[k]["antes"], fases[k]["despues"]) for k in pos]
        cambios = [c for a, d in pares for c in _numstat(a, d)]
        # 87b: si la foto del arreglo registra otra cola viva, se cruza su atribución como en el despliegue.
        # Registro que falta, abierto, ilegible o con una ruta en común con el arreglo: revisión completa.
        ajenas = {}
        for k in pos:
            for nombre, quienes in compartidos_de_fase(fases[k], _nombres_cambio(fases[k]["antes"], fases[k]["despues"])).items():
                ajenas.setdefault(nombre, set()).update(quienes)
        if ajenas:
            return False, (f"E1: {fix} comparte archivos con otra cola viva: "
                           + "; ".join(f"{n} ({', '.join(sorted(q))})" for n, q in sorted(ajenas.items()))), []
    except InformeInseguro as e:
        return False, f"E4: {e}", []
    except Exception as e:      # noqa: BLE001 — git que falla es duda: revisión completa
        return False, f"E4: git falló ({type(e).__name__}: {e})", []
    rutas = sorted({ruta for _, _, ruta in cambios})
    if nuevos := [x for x in rutas if x not in previos]:
        return False, f"E1: {fix} toca archivos que no estaban en el diff de la etapa: {', '.join(nuevos)}", []
    if sensibles := [x for x in rutas if _sensible(x)]:
        return False, f"E2: {fix} toca rutas sensibles: {', '.join(sensibles)}", []
    if binarios := sorted({ruta for mas, menos, ruta in cambios if not (mas.isdigit() and menos.isdigit())}):
        return False, f"E3: {fix} cambia binarios: {', '.join(binarios)}", []
    lineas = sum(int(mas) + int(menos) for mas, menos, _ in cambios)
    if lineas > CIERRE_MAX_LINEAS:
        return False, f"E3: {fix} cambia {lineas} líneas (máximo {CIERRE_MAX_LINEAS})", []
    return True, f"{fix} cambia {lineas} línea(s) en {len(rutas)} archivo(s) ya revisados", pares


def veredicto_cierre(texto: str) -> str:
    """DESPLEGABLE, NO DESPLEGABLE o ESCALAR si las últimas 3 líneas traen exactamente una línea de veredicto
    y es una de las tres, escrita tal cual; '' en cualquier otro caso (que también escala)."""
    ultimas = texto.splitlines()[-3:]
    hallados = [m.group(1) for x in ultimas if (m := VEREDICTO_CIERRE.fullmatch(x))]
    if len(hallados) != 1 or sum("veredicto" in x.lower() for x in ultimas) != 1:
        return ""
    return hallados[0]


def _seccion_arreglos(i: str, vuelta: int) -> str:
    """La sección «Arreglos vuelta N» de encargos/<id>-RESULTADO.md, hasta el próximo título de su nivel.
    Levanta InformeInseguro si el archivo no se puede leer con seguridad."""
    texto = leer_informe(E / f"{i}-RESULTADO.md")      # 87b: InformeInseguro sube y el cierre escala
    m = re.search(rf"^(#+)[ \t].*Arreglos vuelta {vuelta}\b.*$", texto, re.M)
    if not m:
        return f"(encargos/{i}-RESULTADO.md no trae la sección «Arreglos vuelta {vuelta}»)"
    fin = re.compile(rf"^#{{1,{len(m.group(1))}}}[ \t]", re.M).search(texto, m.end())
    return texto[m.start():fin.start() if fin else len(texto)].rstrip() + "\n"


def prompt_cierre(et: dict, fase: str, diff_fix: str) -> str:
    """La instrucción del cierre: la plantilla con la revisión anterior, sólo el diff del último arreglo, su
    sección «Arreglos vuelta» y el plan aprobado. Un solo reemplazo: lo pegado no pasa por los demás. Cada
    informe pasa por leer_informe (87b): si uno no es seguro, levanta InformeInseguro."""
    i, n = et["id"], int(fase[3:])
    plan = E / f"{i}-PLAN.md"
    valores = {"ID": i, "ENCARGO": et.get("encargo", ""), "AUTOR": nombre(et["autor"]), "REVISOR": nombre(et["revisor"]),
               "N": str(n), "PREVIA": str(n - 1), "SUITES": ", ".join(MANIFIESTO["pruebas"]),
               "REVISION_PREVIA": leer_informe(E / f"{i}r{n - 1}-RESULTADO.md"),
               "ARREGLOS": _seccion_arreglos(i, n - 1),
               "DIFF_FIX": diff_fix if diff_fix.strip() else "(el arreglo no cambió ningún archivo)\n",
               "PLAN": leer_informe(plan) if et.get("plan") and (plan.is_file() or plan.is_symlink())
               else "(esta etapa no tiene plan)\n"}
    return re.sub(r"\{(" + "|".join(valores) + r")\}", lambda m: valores[m.group(1)],
                  PLANTILLA_CIERRE.read_text(encoding="utf-8"))


def correr_cierre(et: dict, fase: str, desde: str, pares: list[tuple[str, str]]) -> tuple[str, str]:
    """Corre el cierre en lugar de la `fase` y devuelve (veredicto, motivo). Sólo DESPLEGABLE y NO DESPLEGABLE
    valen; todo lo demás es ESCALAR y la cola corre la revisión completa en la misma vuelta. Sin cuota: Pausa."""
    i, cid = et["id"], et["revisor"]
    mod = dict(modelo_de(et, "cierre"), naturaleza=et.get("naturaleza"), encargo_id=i)
    if not mod["modelo"]:
        return "ESCALAR", "modelos.toml no trae el nivel agil del revisor"
    exigir_candado(et, "cierre", mod, desde)
    if motivo := esfuerzo_incompatible(et, "cierre", mod):
        raise Pausa(motivo, desde)
    try:
        diff = "".join(f"## {a[:7]}..{d[:7]}\n\n{_vers().diff(a, d)}" for a, d in pares)
    except Exception as e:      # noqa: BLE001
        return "ESCALAR", f"no se pudo leer el diff del arreglo ({type(e).__name__}: {e})"
    try:
        prompt = prompt_cierre(et, fase, diff)      # 87b: antes de gastar cuota; un informe inseguro escala
    except InformeInseguro as e:
        return "ESCALAR", str(e)
    f, antes = chequear_cuota(cid, "cierre", desde, mod["modelo"], mod["esfuerzo"])
    atender_pausa(desde)
    res = E / f"{i}r-RESULTADO.md"
    res.unlink(missing_ok=True)     # lo que haya dejado el arreglo no es el veredicto del cierre
    quien = mod["modelo"] + (f" {mod['esfuerzo']}" if mod["esfuerzo"] else "")
    inicio = ahora().isoformat(timespec="seconds")
    VIVO.setdefault("inicio_trabajo", inicio)
    vivo(estado="corriendo", etapa=i, fase=fase, rol="cierre", cuenta=nombre(cid), modelo=quien,
         inicio_fase=inicio, pronostico_fase_min=f["min"], remoto=None)
    log(f"{i}: {fase} como cierre con {nombre(cid)} · {quien} (pronóstico {f['min']} min"
        f"{', ' + etiqueta_pronostico(f) if etiqueta_pronostico(f) else ''})")
    git_foto(f"{MANIFIESTO['nombre']} · {i} · {fase} cierre (antes)")
    r = correr(cid, prompt, f"{i}-{fase}-cierre", mod, HERRAMIENTAS, limite_s=CIERRE_MAX_MIN * 60)
    r["inicio"] = inicio
    git_foto(f"{MANIFIESTO['nombre']} · {i} · {fase} cierre")
    VIVO.pop("rol", None)
    VIVO.setdefault("fases_hechas", []).append({"etapa": i, "fase": fase, "rol": "cierre", "cuenta": nombre(cid),
                                                "min": r["min"], "pronostico_min": f["min"]})
    if r["sin_cuota"]:
        anotar(i, fase, cid, "cierre", f, antes, r, mod)
        raise Pausa(f"{nombre(cid)} se quedó sin cuota a mitad del cierre de {fase} ({r['min']} min)", desde)
    inseguro = ""
    try:
        texto = leer_informe(res) if res.is_file() or res.is_symlink() else None
    except InformeInseguro as e:        # 87b: un enlace o algo raro en el informe final no es un veredicto
        texto, inseguro = None, str(e)
    v = veredicto_cierre(texto) if texto is not None and r["rc"] == 0 and not r.get("corte") else ""
    motivo = ("corte por tiempo" if r.get("corte") else f"rc {r['rc']}" if r["rc"] != 0
              else inseguro if inseguro
              else f"no escribió encargos/{i}r-RESULTADO.md" if texto is None
              else "sin una línea de veredicto exacta en las últimas 3" if not v
              else "el cierre pidió escalar" if v == "ESCALAR" else v)
    v = v if v in ("DESPLEGABLE", "NO DESPLEGABLE") else "ESCALAR"
    anotar(i, fase, cid, "cierre", f, antes, r, mod, v)
    return v, motivo


# ---------------------------------------------------------------- estado en vivo y ETA

VIVO: dict = {}


def prob_rechazo() -> float:
    """Fracción de revisiones NO DESPLEGABLE en el historial (0,5 si hay menos de 4)."""
    revs = [h.get("veredicto") for h in historial() if h.get("rol") == "rev" and h.get("veredicto")]
    return round(revs.count("NO DESPLEGABLE") / len(revs), 2) if len(revs) >= 4 else 0.5


def restante(etapas: list[dict], et_actual: str, fase_actual: str, transcurrido_fase: float) -> dict:
    """Minutos que faltan: {'esperado', 'min', 'max'}. Esperado pondera cada fase futura por la
    probabilidad de llegar a ella (cada revisión rechaza con p); min = la próxima revisión aprueba;
    max = se gastan todas las vueltas. Suma 1 min de pruebas finales."""
    p = prob_rechazo()
    esp = mn = mx = 1.0
    empezado = False
    for et in etapas:
        if not empezado and et["id"] != et_actual:
            continue
        vueltas = int(et.get("vueltas", 2))
        fases = [*(FASES_PLAN if et.get("plan") else ()), *FASES[: 1 + 2 * vueltas + 1]]
        ini = fases.index(fase_actual) if not empezado else 0
        alcance, sigue_min = 1.0, True
        # Si se reanuda desde la segunda vuelta de plan, el rechazo de la primera ya ocurrió.
        # Las probabilidades que siguen son condicionales a ese hecho, no las de una etapa nueva.
        segunda_vuelta_plan = fase_actual in ("plan2", "revplan2")
        salta_segunda_vuelta_en_min = False
        for k, fase in enumerate(fases[ini:]):
            rol = rol_de_fase(et, fase)
            cid = et["revisor"] if rol in ("rev", "revplan", "cierre") else et["autor"]
            modelo_rol = "autor" if rol == "plan" else "rev" if rol == "revplan" else rol
            mod = modelo_de(et, modelo_rol)
            dur = pronostico(cid, rol, mod["modelo"], donde_fase(et, rol), mod["esfuerzo"])["min"]
            if not empezado and k == 0:
                dur = max(0.5, dur - transcurrido_fase)
            esp += alcance * dur
            mx += dur
            if rol == "cierre":
                # Encargo 87: el máximo supone que el cierre escala y corre además la revisión completa.
                completa = modelo_de(et, "rev")
                mx += pronostico(cid, "rev", completa["modelo"], "", completa["esfuerzo"])["min"]
            if sigue_min and not salta_segunda_vuelta_en_min:
                mn += dur
            if rol == "revplan":
                if fase == "revplan":
                    # El camino mínimo aprueba aquí y salta plan2/revplan2, pero aún debe
                    # incluir autor y su primera revisión.
                    salta_segunda_vuelta_en_min = True
                    alcance = p
                else:
                    salta_segunda_vuelta_en_min = False
                    alcance = 1 - p if segunda_vuelta_plan else 1 - p * p
            elif rol in ("rev", "cierre"):
                sigue_min = False
                alcance *= p
        empezado = True
    return {"esperado": round(esp, 1), "min": round(mn, 1), "max": round(mx, 1)}


def rol_de_fase(et: dict, fase: str) -> str:
    """El rol con que se pronostica y publica una fase. La rev2+ de una etapa con `cierre_barato` se
    pronostica como `cierre` (encargo 87): lo que corre de verdad lo decide `decidir_cierre()` al llegar."""
    rol = "plan" if fase.startswith("plan") else "revplan" if fase.startswith("revplan") else "autor" if fase == "autor" else fase[:3]
    return "cierre" if rol == "rev" and cierre_aplica(et, fase) else rol


def fases_pendientes(etapas: list[dict], et_actual: str, fase_actual: str):
    """(etapa, fase, rol, cuenta) de lo que falta desde la fase actual (incluida), en orden: las
    vueltas de arreglo que todavía podrían correr cuentan, porque gastarían cuota."""
    empezado = False
    for et in etapas:
        if not empezado and et["id"] != et_actual:
            continue
        fases = [*(FASES_PLAN if et.get("plan") else ()), *FASES[: 1 + 2 * int(et.get("vueltas", 2)) + 1]]
        for fase in fases[fases.index(fase_actual) if not empezado else 0:]:
            rol = rol_de_fase(et, fase)
            yield et, fase, rol, et["revisor"] if rol in ("rev", "revplan", "cierre") else et["autor"]
        empezado = True


def uso_de_cuentas(et_actual: str, fase_actual: str, incluye_actual: bool) -> dict:
    """Lo que lee la regla de aviso previo de avisos.py y la línea «alcanza / no alcanza» de 🧵 Encargos:
    `cuentas_en_uso` (claves de las fases que faltan; una fase de PC-2503 no gasta cuota de la Pi),
    `proximo` (pronóstico de la próxima fase) y `proximo_por_cuenta` (el de la primera fase pendiente
    de cada cuenta). La próxima fase es la actual si la cola espera por ella, y la siguiente si corre."""
    pend = list(fases_pendientes(MANIFIESTO["etapa"], et_actual, fase_actual))
    if not incluye_actual:
        pend = pend[1:]
    por_cuenta, en_uso = {}, []
    for et, fase, rol, cid in pend:
        donde = donde_fase(et, rol)
        if donde:
            continue
        if cid not in en_uso:
            en_uso.append(cid)
        if cid not in por_cuenta:
            modelo_rol = "autor" if rol == "plan" else "rev" if rol == "revplan" else rol
            mod = modelo_de(et, modelo_rol)
            f = pronostico(cid, rol, mod["modelo"], "", mod["esfuerzo"])
            # Avisos y el panel anuncian el mismo margen que usa chequear_cuota().
            por_cuenta[cid] = {"cuenta": cid, "etapa": et["id"], "fase": fase, "pct_5h": f["pct_5h_p75"],
                               "pct_sem": f["pct_sem_p75"], "debil": bool(f["debil"])}
    proximo = next((por_cuenta[cid] for et, fase, rol, cid in pend
                    if cid in por_cuenta and por_cuenta[cid]["fase"] == fase and por_cuenta[cid]["etapa"] == et["id"]), None)
    return {"cuentas_en_uso": en_uso, "proximo": proximo, "proximo_por_cuenta": por_cuenta}


def vivo(**cambios) -> None:
    """encargos/vivo/<cola>.json: lo que lee 🧵 Encargos para la barra de progreso (doc 28).
    Se reescribe al empezar y terminar cada fase, en cada cambio de estado y, durante una espera de
    cuota, cada 5 min (encargo 24: la ficha no puede quedar con el `escrito` de hace horas)."""
    if SIMULANDO:
        return
    VIVO.update(cambios)
    ahora_ts = ahora()
    VIVO["escrito"] = ahora_ts.isoformat(timespec="seconds")
    try:
        if VIVO.get("estado") == "corriendo" and VIVO.get("fase"):
            trans = (ahora_ts - datetime.fromisoformat(VIVO["inicio_fase"])).total_seconds() / 60
            r = restante(MANIFIESTO["etapa"], VIVO["etapa"], VIVO["fase"], trans)
            hecho = (ahora_ts - datetime.fromisoformat(VIVO["inicio_trabajo"])).total_seconds() / 60
            VIVO.update(restante_min=r, prob_rechazo=prob_rechazo(),
                        progreso_pct=round(100 * hecho / (hecho + r["esperado"]), 1),
                        eta={k: (ahora_ts + timedelta(minutes=v)).isoformat(timespec="minutes") for k, v in r.items()})
            VIVO.update(uso_de_cuentas(VIVO["etapa"], VIVO["fase"], incluye_actual=False))
        elif VIVO.get("estado") == "esperando_cuota" and VIVO.get("fase"):
            # La ETA corre con la espera: hora de reanudación + lo que falte (desde la fase pendiente,
            # sin descontar tiempo transcurrido).
            r = restante(MANIFIESTO["etapa"], VIVO["etapa"], VIVO["fase"], 0)
            base = datetime.fromisoformat(VIVO["reanuda"]) if VIVO.get("reanuda") else ahora_ts
            VIVO.update(restante_min=r, prob_rechazo=prob_rechazo(),
                        eta={k: (base + timedelta(minutes=v)).isoformat(timespec="minutes") for k, v in r.items()})
            if VIVO.get("inicio_trabajo") and VIVO.get("espera_desde"):    # lo hecho llega hasta que empezó a esperar
                hecho = (datetime.fromisoformat(VIVO["espera_desde"]) - datetime.fromisoformat(VIVO["inicio_trabajo"])).total_seconds() / 60
                VIVO["progreso_pct"] = round(100 * hecho / (hecho + r["esperado"]), 1)
            VIVO.update(uso_de_cuentas(VIVO["etapa"], VIVO["fase"], incluye_actual=True))
    except (KeyError, ValueError, TypeError, RuntimeError) as e:
        # El avance y el pronóstico son adorno: no pueden tirar la cola (p. ej. modelos.toml a medio escribir).
        print(f"⚠️ vivo(): no se pudo calcular el avance ({type(e).__name__}: {e})", flush=True)
    # Encargo 46a: todo lo que falta, para la matriz de cuota. Aparte de lo de arriba: si esto falla, lo que
    # leen avisos.py y las páginas (`proximo`, `eta`…) queda igual. Una cola que ya no corre no lo publica.
    VIVO.pop("fases_restantes", None)
    try:
        if VIVO.get("estado") in ESTADOS_ACTIVOS:
            VIVO["fases_restantes"] = plan_de_vivo(VIVO, MANIFIESTO["etapa"], ahora_ts, E / "vivo", partida=PARTIDA)
    except (KeyError, ValueError, TypeError, RuntimeError) as e:
        print(f"⚠️ vivo(): no se pudieron calcular las fases restantes ({type(e).__name__}: {e})", flush=True)
    try:
        d = E / "vivo"
        d.mkdir(exist_ok=True)
        tmp = d / f".{MANIFIESTO['nombre']}.json.tmp"
        tmp.write_text(json.dumps(VIVO, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, d / f"{MANIFIESTO['nombre']}.json")
    except OSError:
        pass


def etapa(et: dict, desde_fase: str = "autor", reanuda: bool = False) -> bool:
    i = et["id"]
    if desde_fase == "autor" and et.get("plan") and not reanuda:
        desde_fase = "plan"
    if et["autor"] == et["revisor"] and not et.get("autorrevision"):
        raise SystemExit(f"etapa {i}: autor y revisor son la misma cuenta y el manifiesto no trae "
                         "`autorrevision` (quién lo aceptó y cuándo)")
    vueltas = int(et.get("vueltas", 2))
    if reanuda and (acept := _aceptada(i, desde_fase)):
        # Encargo 51: el usuario aceptó la revisión tras la que venía este arreglo. La etapa sigue sin arreglar; el
        # despliegue igual pasa por desplegar(), que pide su ✅ (y no lo pide si la etapa tocó root o secretos).
        log(f"{i}: ✅ aceptada por el usuario tras {acept['tras']} (pedido {acept.get('pedido')}); no se corre {desde_fase}")
        return True
    fases = [*(FASES_PLAN if et.get("plan") else ()), *FASES[: 1 + 2 * vueltas + 1]]
    # Al reanudar desde plan2 o revplan2, el primer rechazo ya consta en el vivo que dejó
    # la pausa. No se puede volver a inferir desde el archivo, porque revplan2 lo reemplaza.
    plan_rechazado = desde_fase in ("plan2", "revplan2")
    for fase in fases[fases.index(desde_fase):]:
        if fase in ("plan2", "revplan2") and not plan_rechazado:
            continue
        rol = "plan" if fase.startswith("plan") else "revplan" if fase.startswith("revplan") else "autor" if fase == "autor" else fase[:3]
        modelo_rol = "autor" if rol == "plan" else "rev" if rol == "revplan" else rol
        cid = et["revisor"] if rol in ("rev", "revplan") else et["autor"]
        desde = f"{i}:{fase}"
        atender_pausa(desde)        # encargo 46c: entre fases; la que estaba en curso ya terminó
        if et.get("plan") and rol in ("autor", "fix", "rev"):
            veredicto_plan = E / f"{i}rplan-RESULTADO.md"
            plan = E / f"{i}-PLAN.md"
            try:
                aprobado = veredicto_plan.exists() and bool(re.search(
                    r"^ *PLAN APROBADO *$", "\n".join(veredicto_plan.read_text(encoding="utf-8").splitlines()[-3:]), re.M))
                hash_plan = hashlib.sha256(plan.read_bytes()).hexdigest()
            except OSError:
                aprobado, hash_plan = False, None
            if not aprobado or hash_plan != GIT_BASE.get(f"{i}:plan_sha256"):
                motivo = "no hay plan aprobado e inmutable; la etapa no puede escribir código ni revisarlo"
                vivo(motivo_pausa=motivo)
                log(f"{i}: ⛔ {motivo}")
                return False
        if rol == "rev" and cierre_aplica(et, fase):
            # Encargo 87: la decisión se recalcula cada vez que se llega a esta fase, también tras --desde.
            usar, motivo_cierre, pares = decidir_cierre(et, fase)
            veredicto = "ESCALAR"
            if usar:
                log(f"{i}: {fase} va como cierre: {motivo_cierre}")
                veredicto, motivo_cierre = correr_cierre(et, fase, desde, pares)
            if veredicto == "DESPLEGABLE":
                log(f"{i}: ✅ DESPLEGABLE ({fase}, cierre)")
                return True
            if veredicto == "NO DESPLEGABLE":
                res = E / f"{i}r-RESULTADO.md"
                try:
                    texto_rev = leer_informe(res)       # 87b: sin seguir enlaces, también al copiarlo
                except InformeInseguro as e:
                    veredicto, motivo_cierre = "ESCALAR", str(e)
            if veredicto == "NO DESPLEGABLE":
                (E / f"{i}r{fase[-1]}-RESULTADO.md").write_text(texto_rev, encoding="utf-8")
                log(f"{i}: ❌ no desplegable ({fase}, cierre)")
                if int(fase[3:]) <= vueltas:
                    consultar_o_seguir(et, fase, texto_rev)
                continue
            log(f"{i}: {fase} con la revisión completa: {motivo_cierre}")
        et_modelo = dict(et, esfuerzo_rev="medium") if rol == "revplan" else et
        mod = dict(modelo_de(et_modelo, modelo_rol), naturaleza=et.get("naturaleza"), encargo_id=i)
        exigir_candado(et, rol, mod, desde)
        # El modelo se relee en cada fase: un nivel cambiado a mitad de cola puede dejar de aceptar
        # el esfuerzo que el manifiesto declaró, o el catálogo puede dejar de leerse. Se pausa antes
        # de gastar, no se le pasa al CLI.
        if motivo := esfuerzo_incompatible(et_modelo, modelo_rol, mod):
            raise Pausa(motivo, desde)
        donde = donde_fase(et, rol)
        quien_corre = nombre(cid) + (" en PC-2503" if donde else "")
        # El informe de PC-2503 se busca ANTES de esperar cuota: si no está, no hay qué revisar.
        informe = informe_remoto(et, desde) if remota(et) and rol == "rev" else ""
        if donde:
            f, antes = pronostico(cid, rol, mod["modelo"], donde, mod["esfuerzo"]), dict(SIN_MEDIR)
        else:
            f, antes = chequear_cuota(cid, rol, desde, mod["modelo"], mod["esfuerzo"])
        atender_pausa(desde)        # una espera de cuota dura horas: si entretanto se pidió pausar, la fase no empieza
        if rol in ("rev", "revplan"):
            if rol == "revplan":
                (E / f"{i}rplan-RESULTADO.md").unlink(missing_ok=True)
            (E / f"{i}r-RESULTADO.md").unlink(missing_ok=True)
        quien = mod["modelo"] + (f" {mod['esfuerzo']}" if mod["esfuerzo"] else "") if mod["modelo"] else mod["nivel"]
        inicio = ahora().isoformat(timespec="seconds")
        VIVO.setdefault("inicio_trabajo", inicio)
        vivo(estado="corriendo", etapa=i, fase=fase, cuenta=quien_corre, modelo=quien,
             inicio_fase=inicio, pronostico_fase_min=f["min"], remoto=None)
        cuota = "su cuota no se mide desde la Pi" if donde else f"ahora {antes['5h']:.0f} % 5 h, {antes['fuente']}"
        log(f"{i}: {fase} con {quien_corre} · {quien} (pronóstico {f['min']} min, +{f['pct_5h']} % 5 h"
            f"{', ' + etiqueta_pronostico(f) if etiqueta_pronostico(f) else ''}; {cuota}) · "
            f"termina ~{VIVO['eta']['esperado'][11:16]} (entre {VIVO['eta']['min'][11:16]} y {VIVO['eta']['max'][11:16]})")
        nom_cola = MANIFIESTO["nombre"]
        foto_antes = git_foto(f"{nom_cola} · {i} · {fase} (antes)")
        if rol not in ("rev", "revplan") and not remota(et):
            git_base_guardar(i, foto_antes, fase)
        diff_ruta = git_diff_etapa(i, foto_antes) if rol == "rev" and not remota(et) else ""
        if donde:
            r = despachar(et, fase, mod, f, desde, reanuda and fase == desde_fase)
        else:
            r = correr(cid, prompt_de(fase, et, reanuda and fase == desde_fase, informe, diff_ruta), f"{i}-{fase}", mod,
                       HERRAMIENTAS_REV_PC2503 if remota(et) else HERRAMIENTAS)
        r["inicio"] = inicio
        foto_despues = git_foto(f"{nom_cola} · {i} · {fase}")  # también si la fase se cortó por cuota: lo hecho queda guardado
        if rol not in ("rev", "revplan") and not remota(et):
            git_base_guardar(i, foto_despues, fase, despues=True)
        VIVO.setdefault("fases_hechas", []).append({"etapa": i, "fase": fase, "cuenta": quien_corre,
                                                    "min": r["min"], "pronostico_min": f["min"]})
        if rol == "plan":
            try:
                salida = _vers().abrir().git("diff", "--no-color", "--name-only", "-z", foto_antes,
                                              foto_despues, "--").stdout
                propios = set(salida.decode("utf-8", "replace").split("\0")) - {""}
            except Exception:
                propios = {"<diff propio no verificable>"}
            esperado = f"encargos/{i}-PLAN.md"
            # Estos archivos los escribe la infraestructura de la cola, incluso cuando otra cola
            # está viva. No son prueba de que el autor del plan haya tocado algo fuera de alcance.
            compartidos = {"encargos/COLA-ESTADO.md", "encargos/historial.jsonl"}
            externos = {p for p in propios if p in compartidos or p.startswith("encargos/vivo/")
                         or (p.startswith("encargos/cola-") and p.endswith(".toml"))}
            prohibidos = propios - {esperado} - externos
            if prohibidos or not (E / f"{i}-PLAN.md").is_file():
                anotar(i, fase, cid, rol, f, antes, r, mod)
                motivo = f"violación de plan: solo podía tocar {esperado}; diff propio: {', '.join(sorted(prohibidos or propios)) or 'sin plan'}"
                vivo(motivo_pausa=motivo)
                log(f"{i}: ⛔ {motivo}")
                # Con una cola ajena viva no se puede demostrar quién escribió el archivo extra.
                # Se pausa antes del código para conservar el detalle y permitir que se revise o reanude.
                if prohibidos:
                    raise Pausa(motivo, desde)
                return False
        if r["sin_cuota"]:
            anotar(i, fase, cid, rol, f, antes, r, mod, donde=donde)
            raise Pausa(f"{quien_corre} se quedó sin cuota a mitad de {fase} ({r['min']} min)", desde)
        if donde:
            if r["problema"]:       # rechazado, error o cortado: no es una medición de nada
                raise Pausa(r["problema"], desde)
            anotar(i, fase, cid, rol, f, antes, r, mod, r["veredicto"], donde=donde)
            log(f"{i}: {fase} terminó en PC-2503 en {r['min']} min ({r['min_motor']} min de motor)")
            continue
        if rol in ("rev", "revplan"):
            if rol == "revplan":
                res = E / f"{i}rplan-RESULTADO.md"
                ok = res.exists() and bool(re.search(r"^ *PLAN APROBADO *$", "\n".join(res.read_text(encoding="utf-8").splitlines()[-3:]), re.M))
                anotar(i, fase, cid, rol, f, antes, r, mod, "PLAN APROBADO" if ok else "PLAN RECHAZADO")
                if ok:
                    # Queda en el mismo estado atómico de fotos que se recupera con --desde.
                    # El autor, arreglos y revisiones posteriores sólo avanzan si el archivo sigue igual.
                    res_plan = E / f"{i}-PLAN.md"
                    GIT_BASE[f"{i}:plan_sha256"] = hashlib.sha256(res_plan.read_bytes()).hexdigest() if res_plan.is_file() else ""
                    git_base_guardar(i, GIT_BASE.get(i))
                    log(f"{i}: ✅ PLAN APROBADO ({fase}, {r['min']} min)")
                    continue
                if fase == "revplan2":
                    motivo = "plan rechazado dos veces; la etapa se detiene antes del código"
                    vivo(motivo_pausa=motivo)
                    log(f"{i}: ⛔ {motivo}")
                    return False
                plan_rechazado = True
                log(f"{i}: ❌ PLAN RECHAZADO ({fase}, {r['min']} min)")
                continue
            res = E / f"{i}r-RESULTADO.md"
            ok = res.exists() and bool(VEREDICTO_OK.search("\n".join(res.read_text(encoding="utf-8").splitlines()[-3:])))
            anotar(i, fase, cid, rol, f, antes, r, mod, "DESPLEGABLE" if ok else "NO DESPLEGABLE")
            if ok:
                log(f"{i}: ✅ DESPLEGABLE ({fase}, {r['min']} min)")
                return True
            if res.exists():
                (E / f"{i}r{fase[-1]}-RESULTADO.md").write_bytes(res.read_bytes())
            log(f"{i}: ❌ no desplegable ({fase}, {r['min']} min)")
            if int(fase[3:]) <= vueltas and not remota(et):     # encargo 51: le sigue un arreglo, cabe una consulta
                try:
                    texto_rev = res.read_text(encoding="utf-8") if res.exists() else ""
                except (OSError, UnicodeDecodeError):
                    texto_rev = ""
                consultar_o_seguir(et, fase, texto_rev)
        else:
            anotar(i, fase, cid, rol, f, antes, r, mod)
            log(f"{i}: {fase} terminó en {r['min']} min (rc {r['rc']})")
    log(f"{i}: ⛔ sigue NO DESPLEGABLE después de {vueltas} arreglos")
    return False


# ---------------------------------------------------------------- pruebas y despliegue

def pruebas() -> tuple[set[str], str]:
    fallas, resumen = set(), []
    for s in MANIFIESTO["pruebas"]:
        p = subprocess.run(["python3", s], cwd=D, capture_output=True, text=True,
                           env=dict(os.environ, NODO_PRUEBAS="1"))
        out = p.stdout + p.stderr
        ids = {f"{s}::{m[1]} {m[2]}" for m in FALLA.finditer(out)}
        if p.returncode != 0 and not ids:
            ids = {f"{s}::no corrió (rc {p.returncode})"}
        fallas |= ids
        fin = [x for x in out.splitlines() if re.match(r"^(Ran|OK|FAILED)", x)]
        resumen.append(f"    {s}: {' · '.join(fin) or 'sin resumen'}")
    return fallas, "\n".join(resumen)


def foto() -> dict:
    """Hash de cada entrada del catálogo (lado vault), de cada página y de los archivos sueltos."""
    cat = json.loads(subprocess.run(["nodo-desplegar", "catalogo"], capture_output=True, text=True).stdout or "{}")
    # Solo lo de este proyecto: lo que otros cambien en otras carpetas no entra al pedido.
    cat = {k: v for k, v in cat.items() if str(v.get("fuente", "")).startswith("10-Proyectos/11-Pi5/")}
    entradas = {k: sha(VAULT / v["fuente"]) for k, v in cat.items()}
    rutas_catalogo = {k: str(v["fuente"]).split("10-Proyectos/11-Pi5/", 1)[1] for k, v in cat.items()}
    destinos = {k: str(v.get("destino", "")) for k, v in cat.items()}
    fuentes = {str(VAULT / v["fuente"]) for v in cat.values()}
    paginas = {n: sha_dir(D / "pi" / c) for n, c in MANIFIESTO.get("paginas", {}).items()}
    sueltos = {str(p) for base in ("botv3", "pi") for p in (D / base).glob("*")
               if p.is_file() and p.suffix in (".py", ".toml", ".sh", "") and not p.name.startswith("test_")}
    return {"entradas": entradas, "fuentes": rutas_catalogo, "destinos": destinos,
            "paginas": paginas, "sin_catalogo": sueltos - fuentes}


def tomar_linea_base_catalogo(reanuda: bool, nombre_cola: str) -> dict:
    """Toma una foto sólo al iniciar la corrida original; --desde recupera exactamente ésa."""
    if reanuda:
        git_base_cargar()
        base = catalogo_base_cargar()
        if base is not None:
            return base
        # Una cola anterior a este formato no tiene cómo recuperar lo escrito antes de --desde.
        base = foto()
        aviso = "⚠️ Línea base no persistida: el pedido puede quedar corto; revisa con `cmp` antes de aprobarlo."
        log(aviso)
        avisar_texto(f"⚠️ La cola {nombre_cola} se reanudó sin línea base persistida: el pedido puede quedar corto; "
                     "revisa con `cmp` antes de aprobarlo.",
                     viejo=(f"⚠️ Cola {nombre_cola}: línea base no persistida; el pedido puede quedar corto. Revisa con `cmp`.",
                            f"cat {ESTADO}"))
        return base
    GIT_BASE.clear()
    _git_base_ruta().unlink(missing_ok=True)
    base = foto()
    catalogo_base_guardar(base)
    return base


def _nombres_cambio(antes: str, despues: str) -> set[str]:
    nombres = _vers().abrir().git("diff", "--no-color", "--name-only", "-z", antes, despues, "--").stdout
    return {x for x in nombres.decode("utf-8", "replace").split("\0") if x}


def _fases_ajenas(nombre: str) -> list[dict] | None:
    """Lee la foto atómica de otra cola. None es duda, nunca permiso para instalar.

    Una fase con ``antes`` pero sin ``despues`` sigue abierta. No sabemos todavía qué
    escribió, por lo que se devuelve marcada y el tramo propio que coincide en tiempo
    se retiene completo. Una foto abierta no se descarta por tener otra ya cerrada.
    """
    try:
        if not RE_COLA_GIT.fullmatch(nombre):
            return None
        d = json.loads((L / f"{nombre}-git.json").read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return None
        fases = []
        for k, valor in d.items():
            if not (str(k).endswith(":fases") and "@" not in str(k) and isinstance(valor, list)):
                continue
            for f in valor:
                if not (isinstance(f, dict) and isinstance(f.get("antes"), str)
                        and RE_HASH_GIT.fullmatch(f["antes"])):
                    return None
                if "despues" not in f:
                    fases.append(dict(f, _abierta=True))
                elif isinstance(f.get("despues"), str) and RE_HASH_GIT.fullmatch(f["despues"]):
                    fases.append(f)
                else:
                    return None
        return fases or None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _se_solapan(propia: dict, ajena: dict) -> bool:
    """Con marcas nuevas filtra a la fase ajena simultánea; los registros antiguos son conservadores."""
    try:
        inicio, fin = _hora(propia["inicio"]), _hora(propia["fin"])
        otro_inicio, otro_fin = _hora(ajena["inicio"]), _hora(ajena["fin"])
        return inicio <= otro_fin and otro_inicio <= fin
    except (KeyError, TypeError, ValueError):
        return True


def _se_solapan_abierta(propia: dict, ajena: dict) -> bool:
    """Una fase ajena abierta alcanza hasta ahora; sin hora legible se retiene por seguridad."""
    try:
        return _hora(ajena["inicio"]) <= _hora(propia["fin"])
    except (KeyError, TypeError, ValueError):
        return True


def compartidos_de_fase(f: dict, nombres: set[str]) -> dict[str, set[str]]:
    """{archivo: colas} de los `nombres` que cambió la fase propia `f` y que una cola viva en ella (`f['vivas']`)
    pudo haber tocado también. Sin foto legible de la otra, o con su fase abierta y simultánea, todos los
    archivos de `f` quedan compartidos (dudoso / abierto). Lo usan el pedido de despliegue y, desde el 87b, la
    decisión del cierre barato."""
    compartidos: dict[str, set[str]] = {}
    vivas = [n for n in f.get("vivas", []) if isinstance(n, str)] if isinstance(f.get("vivas", []), list) else []
    for otra in vivas:
        fases_otra = _fases_ajenas(otra)
        if fases_otra is None:
            for nombre in nombres:
                compartidos.setdefault(nombre, set()).add(f"{otra} (registro dudoso)")
            continue
        otros = set()
        try:
            for ajena in fases_otra:
                if ajena.get("_abierta"):
                    if _se_solapan_abierta(f, ajena):
                        for nombre in nombres:
                            compartidos.setdefault(nombre, set()).add(f"{otra} (registro abierto)")
                    continue
                if _se_solapan(f, ajena):
                    otros.update(_nombres_cambio(ajena["antes"], ajena["despues"]))
        except Exception:  # un hash ajeno válido en forma pero inexistente tampoco autoriza a pedir
            for nombre in nombres:
                compartidos.setdefault(nombre, set()).add(f"{otra} (registro dudoso)")
            continue
        for nombre in nombres & otros:
            compartidos.setdefault(nombre, set()).add(otra)
    return compartidos


def _propios_atribuidos() -> tuple[set[str], dict[str, set[str]]]:
    """Archivos de nuestras fases que ninguna cola viva cambió también.

    Las fotos de las otras colas se publican con replace. Si no hay una foto legible, se
    conserva la seguridad: todo archivo de ese tramo queda compartido *dudoso* y no entra al pedido.
    """
    propios, compartidos, hay_fases = set(), {}, False
    for clave, fases in GIT_BASE.items():
        if not (clave.endswith(":fases") and "@" not in clave and isinstance(fases, list)):
            continue
        hay_fases = True
        for f in fases:
            if not (isinstance(f, dict) and isinstance(f.get("antes"), str) and isinstance(f.get("despues"), str)):
                raise RuntimeError("hay una fase propia sin sus dos fotos")
            nombres = _nombres_cambio(f["antes"], f["despues"])
            propios.update(nombres)
            for nombre, quienes in compartidos_de_fase(f, nombres).items():
                compartidos.setdefault(nombre, set()).update(quienes)
    if not hay_fases:
        raise RuntimeError("no hay fases propias completas")
    return propios - set(compartidos), compartidos


def _entrada_pendiente(nombre: str, hash_vault: str, antes: dict, despues: dict) -> bool:
    """Prefiere la verdad instalada; si root no deja leerla, conserva la comparación histórica.

    El escucha instala texto con LF, así que CRLF y LF equivalentes no quedan pendientes
    para siempre sólo por la representación de saltos de línea.
    """
    destino = str(despues.get("destinos", {}).get(nombre, ""))
    fuente = despues.get("fuentes", {}).get(nombre)
    try:
        if destino and isinstance(fuente, str):
            vault = (D / fuente).read_bytes().replace(b"\r\n", b"\n")
            instalado = Path(destino).read_bytes().replace(b"\r\n", b"\n")
            return vault != instalado
    except OSError:
        pass
    instalado = sha(Path(destino)) if destino else None
    if instalado is not None:
        return hash_vault != instalado
    return hash_vault != antes.get("entradas", {}).get(nombre)


def desplegar(antes: dict, despues: dict) -> None:
    propios = set()
    compartidos: dict[str, set[str]] = {}
    git_ok = True
    try:
        propios, compartidos = _propios_atribuidos()
    except Exception as e:
        log(f"⚠️ historial git: no se pudo limitar el despliegue al diff propio ({type(e).__name__}: {e}); la cola sigue")
        git_ok = False
    if compartidos:
        # Las fotos delimitan una ventana, no demuestran quién escribió dentro de ella.
        # El texto no atribuye el archivo a la otra cola; sólo explica por qué se retuvo.
        detalle = "; ".join(f"{ruta} cambiado en la ventana de {', '.join(sorted(colas))}, sin pedir"
                             for ruta, colas in sorted(compartidos.items()))
        log(f"⚠️ Despliegue manual conjunto: {detalle}")
        avisar_texto(f"⚠️ La cola {MANIFIESTO['nombre']} no pidió archivos compartidos: {detalle}. "
                     "Hay que desplegarlos juntos tras revisión manual.",
                     viejo=(f"⚠️ Cola {MANIFIESTO['nombre']}: {detalle}. Revisión manual conjunta.", f"cat {ESTADO}"))
    nuevos = sorted(p for p in despues["sin_catalogo"] - antes["sin_catalogo"]
                    if not git_ok or str(Path(p).relative_to(D).as_posix()) in propios)
    pedido = [f"{k}={h}" for k, h in despues["entradas"].items() if h and _entrada_pendiente(k, h, antes, despues)]
    if git_ok and "fuentes" in despues:
        pedido = [f"{k}={h}" for k, h in despues["entradas"].items()
                  if h and _entrada_pendiente(k, h, antes, despues)
                  and despues.get("fuentes", {}).get(k) in propios]
    elif not git_ok:
        # Sin diff propio no se gana permiso para pedir todo lo pendiente del proyecto:
        # se conserva el límite histórico de lo que cambió en esta corrida.
        pedido = [f"{k}={h}" for k, h in despues["entradas"].items()
                  if h and _entrada_pendiente(k, h, antes, despues)
                  and h != antes.get("entradas", {}).get(k)]
    paginas = [n for n, h in despues["paginas"].items() if h and h != antes["paginas"].get(n)
               and (not git_ok or any(x.startswith(f"pi/{MANIFIESTO.get('paginas', {}).get(n, '')}/") for x in propios))
               and not any(x.startswith(f"pi/{MANIFIESTO.get('paginas', {}).get(n, '')}/") for x in compartidos)]
    estado = f"cat {ESTADO}"
    if nuevos:
        log("⛔ Archivos nuevos sin entrada en el catálogo: " + ", ".join(nuevos))
        avisar_texto(f"⛔ La cola {MANIFIESTO['nombre']} quedó revisada, pero hay archivos nuevos sin entrada en el "
                     "catálogo de nodo-desplegar. No se pidió nada; hay que darles de alta primero.",
                     viejo=(f"⛔ Cola {MANIFIESTO['nombre']}: quedó revisada, pero hay archivos nuevos sin entrada en el "
                            "catálogo de nodo-desplegar (van con `nodo-desplegar alta`). No se pidió nada.", estado))
        return
    pags = MANIFIESTO.get("paginas", {})
    # Se instala desde una COPIA hecha ahora, no desde el vault: el 03-10 la línea de la cola 18
    # se pegó a las 18:27 y copió también lo que la cola 19 ya había escrito, sin revisar, en la
    # misma página. La línea instala exactamente lo que se revisó.
    foto_pags = L / f"{MANIFIESTO['nombre']}-paginas-{ahora():%Y%m%d-%H%M}"
    if paginas:
        foto_pags.mkdir(parents=True, exist_ok=True)
    for n in paginas:
        subprocess.run(["cp", "-r", str(D / "pi" / pags[n]), str(foto_pags / n)], check=False)
    instalar = " && ".join(f"mkdir -p ~/.local/share/cockpit/{n} && cp -r {foto_pags}/{n}/. "
                           f"~/.local/share/cockpit/{n}/" for n in paginas)
    modo = MANIFIESTO.get("despliegue", "pedir")
    if modo not in ("pedir", "solo-avisar", "nada"):
        log(f"⛔ despliegue «{modo}» no existe (pedir | solo-avisar | nada): no se manda nada")
        avisar_texto(f"⛔ La cola {MANIFIESTO['nombre']}: el manifiesto dice despliegue «{modo}», que no existe. "
                     "Quedó revisada pero no se desplegó nada.",
                     viejo=(f"⛔ Cola {MANIFIESTO['nombre']}: el manifiesto dice despliegue «{modo}», que no existe. "
                            "Quedó revisada pero no se desplegó nada.", estado))
        return
    aceptadas = [x for x in VIVO.get("aceptadas_usuario") or [] if isinstance(x, dict)]
    if aceptadas and (pedido or not git_ok or any(RE_SECRETO.search(x) for x in propios)):
        # Encargo 51: una aceptación del usuario es sobre hallazgos medios o bajos; nunca autoriza root ni secretos.
        # Si la cola instala algo como root (entradas del catálogo) o tocó secretos, no se pide ni se manda la línea.
        etapas_ac = ", ".join(sorted({str(x.get("etapa")) for x in aceptadas}))
        log(f"⛔ Hay etapas aceptadas por el usuario con hallazgos ({etapas_ac}) y la cola toca root o secretos: "
            f"no se pide el despliegue ({' '.join(pedido) or 'sin diff propio verificable'})")
        avisar_texto(f"⛔ La cola {MANIFIESTO['nombre']} terminó con etapas aceptadas por ti con hallazgos ({etapas_ac}). "
                     "Lo que cambió se instala como root o toca secretos, y una aceptación no autoriza eso: no se pidió "
                     "el despliegue. Hace falta una revisión DESPLEGABLE.",
                     viejo=(f"⛔ Cola {MANIFIESTO['nombre']}: etapas aceptadas con hallazgos ({etapas_ac}) que tocan root "
                            "o secretos. No se pidió el despliegue.", estado))
        return
    if not pedido and not paginas:
        if compartidos:
            log("⚠️ Revisado; quedaron cambios compartidos pendientes de despliegue conjunto")
            avisar_texto(f"⚠️ La cola {MANIFIESTO['nombre']} terminó: revisada, pero quedaron cambios compartidos "
                         "pendientes de despliegue conjunto.",
                         viejo=(f"⚠️ Cola {MANIFIESTO['nombre']} revisada; quedaron cambios compartidos pendientes de "
                                f"despliegue conjunto. Esta línea muestra el estado.", estado))
        else:
            log("✅ Revisado; no cambió nada desplegable")
            avisar_texto(f"✅ La cola {MANIFIESTO['nombre']} terminó: revisada, y no cambió nada que desplegar.",
                         viejo=(f"✅ Cola {MANIFIESTO['nombre']} revisada; no cambió nada que desplegar. Esta línea muestra el estado.", estado))
        return
    if modo == "nada":
        # Ni pedido ni línea: el que encargó instala a mano después de leer (como la skill, 21).
        log(f"✅ Revisado y en verde; despliegue «nada»: no se pide ni se manda línea "
            f"(cambió: {' '.join(pedido) or 'solo páginas'})")
        avisar_texto(f"✅ La cola {MANIFIESTO['nombre']} terminó: revisada y en verde. No se despliega nada (modo «nada»).",
                     viejo=(f"✅ Cola {MANIFIESTO['nombre']} revisada y en verde. No se despliega nada (modo «nada»). "
                            "Esta línea muestra el estado.", estado))
        return
    if modo != "pedir":
        linea = " && ".join(x for x in ([f"nodo-desplegar pedir {' '.join(pedido)} --motivo \"Cola {MANIFIESTO['nombre']}\""] if pedido else []) + ([instalar] if instalar else []))
        log(f"✅ Revisado y en verde; despliegue en modo «{modo}»: se manda la línea")
        avisar(f"✅ Cola {MANIFIESTO['nombre']} revisada y en verde. Esta línea despliega: {' '.join(pedido) or 'solo páginas'}.", linea,
               aplazar_por_descanso=True)
        return
    if not pedido:
        log("✅ Revisado y en verde (solo páginas); se manda la línea para instalarlas")
        avisar(f"✅ Cola {MANIFIESTO['nombre']}: {MANIFIESTO.get('motivo', '')} Solo cambian páginas ({', '.join(paginas)}); esta línea las instala.", instalar,
               aplazar_por_descanso=True)
        return
    posponer_si_descanso("desplegando")
    log(f"✅ Revisado y en verde; se pide el despliegue: {' '.join(pedido)}")
    p = subprocess.run(["nodo-desplegar", "pedir", *pedido, "--motivo",
                        f"Cola {MANIFIESTO['nombre']}: {MANIFIESTO.get('motivo', '')}"], capture_output=True, text=True)
    registrar_aviso(f"🚀 Pedido de despliegue de la cola {MANIFIESTO['nombre']} ({' '.join(pedido)}): "
                    f"{MANIFIESTO.get('motivo', '')}", None, p)
    pid = (p.stdout.strip().splitlines() or [""])[-1]
    log(f"pedido: {pid}")
    with (L / "avisos.log").open("a", encoding="utf-8") as fh:
        ok = bool(pid) and subprocess.run(["nodo-desplegar", "esperar", pid], stdout=fh, stderr=fh).returncode == 0
    if ok:
        if instalar:
            subprocess.run(instalar.replace("~", str(Path.home())), shell=True, check=False)
        log("✅ DESPLEGADO" + (f" y páginas instaladas ({', '.join(paginas)})" if paginas else ""))
        avisar_texto(f"✅ La cola {MANIFIESTO['nombre']} terminó y quedó DESPLEGADA"
                     + (f" (páginas instaladas: {', '.join(paginas)})" if paginas else "") + ".",
                     viejo=(f"✅ Cola {MANIFIESTO['nombre']} DESPLEGADA. Esta línea muestra el resumen.", estado))
    else:
        linea = f"nodo-desplegar pedir {' '.join(pedido)} --motivo \"Cola {MANIFIESTO['nombre']}, reintento\"" + (f" && {instalar}" if instalar else "")
        log("⏳ El pedido no se aprobó a tiempo; se manda la línea para pedirlo de nuevo")
        avisar(f"⏳ Cola {MANIFIESTO['nombre']} en verde, pero el pedido venció sin aprobar. Esta línea lo pide de nuevo.", linea,
               aplazar_por_descanso=True)


# ---------------------------------------------------------------- consultas entre fases (encargo 51)
#
# Una revisión NO DESPLEGABLE cuyos hallazgos son todos [Media] o [Baja] (ningún [Grave]) y a la que todavía le
# sigue un arreglo le pregunta al usuario «Aceptar y seguir», «Que lo arregle» o «Saltar». La cola queda
# estacionada en `en_consulta` apenas pregunta y termina: la cadena sigue con la siguiente.
# El canal son los botones de `nodo-desplegar`, que atiende SOLO el escucha root: valida que el toque
# venga del chat del usuario (from.id, que firma Telegram) y del nonce del pedido, y deja el resultado en
# /var/spool/nodo-desplegar/resultados, de root y 644: este usuario lo lee pero no lo puede fabricar. Desde la
# 71, una ronda es UN `nodo-desplegar consultar`: un mensaje con A, B y C, un botón por alternativa, que el
# escucha cierra al primer toque y deja sin teclado; el resultado trae la clave en `opcion`. Antes eran tres
# `sugerir` con su ✅ cada uno y el usuario tocó los tres (cola66, 19-10). Si el `nodo-desplegar` instalado no
# conoce `consultar`, la ronda vuelve a ser la de antes: tres `sugerir`, uno por opción, y la respuesta es el
# primero que quedó «hecho» (✅); ❌ no es respuesta. Cada ronda vence a los 30 min (VENCE_S de nodo-desplegar): al vencer se manda otra, hasta el plazo
# de 2 h; vencido el plazo se aplica el defecto. Lo recoge `cola-run.py --consultas`, que corre un timer
# TRANSITORIO de usuario (`systemd-run --user`): lo arma la cola antes de preguntar y lo detiene la última pasada
# que ya no encuentra consultas abiertas; no hay unidad que instalar (51r1, hallazgo 2). El texto por el bot de
# captura se descartó: corre con este mismo usuario y cualquier agente fabricaría ahí una respuesta.
# Lo que viaja por `sugerir` queda en el spool, en /var/lib/nodo-desplegar/pendientes.json y en el journal, fuera
# del volumen cifrado (51r1, hallazgo 1): por eso no lleva texto de la revisión, solo nombres validados, cuántos
# hallazgos hay de cada gravedad y el archivo donde leerlos. La pregunta con los títulos queda en el vivo y en
# <etapa>-decisiones.md, dentro del volumen.

RESULTADOS_DESPLEGAR = Path("/var/spool/nodo-desplegar/resultados")
DUENO_RESULTADOS = 0            # los escribe el escucha root: un resultado de otro dueño no es una respuesta
RE_ID_DESPLEGAR = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}")      # el RE_ID de nodo-desplegar
RE_ETAPA = re.compile(r"[0-9]{2}[a-z0-9]*")                         # un id de etapa: también nombra <id>-decisiones.md
RE_HALLAZGO = re.compile(r"^#{2,4}[ \t]+(?:\d+[.)][ \t]*)?\[([^\]\n]{1,40})\][ \t]*(.*)$", re.M)
RE_SECRETO = re.compile(r"(^|/)(secretos?|credenciales)(/|$)|\.env$", re.I)


class Respuesta(NamedTuple):
    letra: str
    etiqueta: str
    despues: str        # lo que pasa después, en el mensaje: vocabulario cerrado, nunca texto del agente


RESPUESTAS = {"aceptar": Respuesta("A", "Aceptar y seguir", "la etapa se da por buena con esos hallazgos y la cola sigue"),
              "arreglar": Respuesta("B", "Que lo arregle", "corre el arreglo y otra revisión"),
              "saltar": Respuesta("C", "Saltar", "la cola queda pausada; se retoma con Reanudar")}
ORDEN_EMPATE = ("arreglar", "saltar", "aceptar")      # dos ✅ en el mismo segundo: gana lo más conservador
CONSULTA_TOPE = 2               # preguntas por cola
CONSULTA_PLAZO_S = 2 * 3600
CONSULTA_RONDA_S = 30 * 60      # lo que dura un botón de `sugerir` (VENCE_S de nodo-desplegar)
CONSULTA_REINTENTOS = 3         # pasadas que reintentan las opciones que le faltaron a una ronda
CONSULTA_MAX = 600              # caracteres de la pregunta
CODIGO_EN_CONSULTA = 6          # con lo que sale una cola que quedó estacionada en consulta
TOPE_RESULTADO = 16 * 1024
EN_DESCANSO = None              # (momento) -> bool; None: pi/descanso.py, como posponer_si_descanso()
VIGILANTE = "encargos-consultas"        # prefijo del timer transitorio de usuario que corre `--consultas`
VIGILANTE_CADA_S = 5 * 60


def _es_cola(n) -> bool:
    """El nombre de una cola con el mismo patrón que `--accion` (46c), siempre con fullmatch."""
    return isinstance(n, str) and RE_COLA.fullmatch(n) is not None


class Consulta(Exception):
    """La etapa quedó estacionada en `en_consulta`: la cola termina sin desplegar y la cadena sigue."""

    def __init__(self, desde: str, motivo: str):
        super().__init__(motivo)
        self.desde, self.motivo = desde, motivo


def _texto_seguro(t, tope: int) -> str:
    """Un título de la revisión, listo para ir en la línea de `sugerir`: una línea, sin caracteres de control ni
    de dirección, sin `<…>` (sugerir lo toma por un placeholder y rechaza el pedido) y recortado."""
    t = "".join(c if c.isprintable() else " " for c in str(t))
    t = re.sub(r"\s+", " ", t).strip().replace("<", "‹").replace(">", "›").replace("`", "").replace("'", "’")
    t = re.sub(r"\b(XXX|TODO)\b", lambda m: m[1].capitalize(), t)
    return t if len(t) <= tope else t[:tope - 1].rstrip() + "…"


def _gravedad(etiqueta: str) -> str:
    """La primera palabra de la etiqueta: «[Media, y es lo que impide el veredicto]» (58r2) es media."""
    e = unicodedata.normalize("NFKD", etiqueta).encode("ascii", "ignore").decode().strip().lower()
    e = re.split(r"[\s,;:(]", e, maxsplit=1)[0]
    return {"grave": "grave", "critico": "grave", "critica": "grave", "media": "media", "medio": "media",
            "baja": "baja", "bajo": "baja", "menor": "baja"}.get(e, "otra")


def hallazgos(texto: str) -> list[tuple[str, str]]:
    """[(gravedad, título)] de los títulos `### N. [Grave|Media|Baja] …` de una revisión. Una etiqueta que no es
    ninguna de esas tres («[Importante, pide decisión]») queda como «otra»."""
    return [(_gravedad(m[1]), _texto_seguro(m[2], 160)) for m in RE_HALLAZGO.finditer(texto)]


def disparador(texto: str) -> tuple[bool, str, list[tuple[str, str]]]:
    """(se pregunta, por qué no, hallazgos). Se pregunta solo si hay hallazgos y todos son [Media] o [Baja]."""
    h = hallazgos(texto)
    if not h:
        return False, "la revisión no trae títulos [Grave], [Media] o [Baja]: va al arreglo, sin consulta", h
    if any(g == "grave" for g, _ in h):
        return False, "la revisión trae un [Grave]: va al arreglo, sin consulta", h
    if any(g == "otra" for g, _ in h):
        return False, "la revisión trae una gravedad que no es [Media] ni [Baja]: va al arreglo, sin consulta", h
    return True, "", h


def armar_pregunta(cola: str, et_id: str, fase: str, n: int, hallado: list[tuple[str, str]]) -> str:
    """La pregunta, armada por la cola con los títulos (nunca por el agente), de hasta CONSULTA_MAX caracteres."""
    cab = f"{_texto_seguro(cola, 20)} #{n} · etapa {_texto_seguro(et_id, 12)}, {_texto_seguro(fase, 6)} NO DESPLEGABLE sin graves. Hallazgos: "
    pie = (f" ¿{RESPUESTAS['aceptar'].etiqueta}, {RESPUESTAS['arreglar'].etiqueta} o {RESPUESTAS['saltar'].etiqueta}? Sin respuesta en 2 h: "
           "saltar si hay otras colas esperando; si no, que lo arregle.")
    cabida, items = CONSULTA_MAX - len(cab) - len(pie), []
    for k, (g, t) in enumerate(hallado):
        item = f"[{g.capitalize()}] {t}"
        resto = len(hallado) - k - 1
        cola_txt = f"; … (+{resto})" if resto else ""
        if len("; ".join(items + [item])) + len(cola_txt) > cabida:
            item = _texto_seguro(item, max(12, cabida - len("; ".join(items)) - len(cola_txt) - 2))
            if len("; ".join(items + [item])) + len(cola_txt) > cabida:
                items.append(f"… (+{len(hallado) - k})")
                break
        items.append(item)
    return (cab + "; ".join(items) + pie)[:CONSULTA_MAX]


def conteo(hallado) -> dict[str, int]:
    """{'media': n, 'baja': n} de los hallazgos: [(gravedad, título)] o los «[Media] …» que guarda el vivo."""
    gs = [h[0] if isinstance(h, (tuple, list)) else _gravedad(str(h)[1:].split("]", 1)[0]) for h in hallado or []]
    return {"media": gs.count("media"), "baja": gs.count("baja")}


def resumen_canal(et_id: str, fase: str, cuenta: dict[str, int]) -> str:
    """Lo que dice la consulta en Telegram. Sale de un vocabulario cerrado —el id de la etapa y la fase, ya
    validados, y dos enteros—, nunca de los títulos: lo que pasa por `sugerir` queda fuera del volumen cifrado."""
    if not (RE_ETAPA.fullmatch(str(et_id)) and re.fullmatch(r"rev[0-9]", str(fase))):
        raise ValueError("etapa o fase inválida para la consulta")
    partes = [f"{int(cuenta.get(g, 0))} [{g.capitalize()}]" for g in ("media", "baja") if int(cuenta.get(g, 0)) > 0]
    return (f"etapa {et_id}, {fase} NO DESPLEGABLE sin graves: {' y '.join(partes) or 'sin títulos'}. Los títulos están "
            f"en encargos/{et_id}r{fase[3:]}-RESULTADO.md (no salen del volumen cifrado). Sin respuesta en 2 h: saltar "
            "si hay otras colas esperando; si no, que lo arregle.")


def lineas_consulta(cola: str, n: int, resumen: str) -> dict[str, tuple[str, str]]:
    """{opción: (motivo, línea)} de los tres `sugerir`. La línea es inofensiva: un `echo` que nombra la opción.
    El resumen (resumen_canal) viaja en la línea de «Aceptar y seguir», el único campo con lugar (el motivo se
    corta en 200)."""
    if not (_es_cola(cola) and isinstance(n, int) and not isinstance(n, bool) and 0 < n <= CONSULTA_TOPE):
        raise ValueError("cola o número de consulta inválido")
    out = {}
    for op, txt in ((o, r.etiqueta) for o, r in RESPUESTAS.items()):
        motivo = (f"❓ Consulta {cola} #{n}: tocar ✅ en ESTE mensaje = «{txt}». ❌ no cuenta como respuesta."
                  + ("" if op == "aceptar" else f" El resumen va en el mensaje de «{RESPUESTAS['aceptar'].etiqueta}»."))
        eco = f"consulta {cola} #{n}: {op}" + (f" · {resumen}" if op == "aceptar" else "")
        out[op] = (motivo[:200], "echo " + shlex.quote(eco))
    return out


def _sugerir_real(motivo: str, linea: str) -> str | None:
    """Un `nodo-desplegar sugerir`; el id del pedido o None. Un agente (NODO_PRUEBAS=1 con las rutas reales) no
    manda nada."""
    if os.environ.get("NODO_PRUEBAS") == "1" and L == Path.home() / "encargos-logs":
        return None
    try:
        p = subprocess.run(["nodo-desplegar", "sugerir", "--motivo", motivo, "--", linea],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        with (L / "avisos.log").open("a", encoding="utf-8") as fh:
            fh.write(p.stdout + p.stderr)
    except OSError:
        pass
    registrar_aviso(motivo, linea, p)
    pid = (p.stdout.strip().splitlines() or [""])[-1]
    return pid if p.returncode == 0 and RE_ID_DESPLEGAR.fullmatch(pid) else None


SUGERIR_CONSULTA = _sugerir_real        # las pruebas lo reemplazan: nunca llaman a nodo-desplegar


def motivo_consulta(cola: str, n: int, et_id: str, fase: str, cuenta: dict[str, int]) -> str:
    """La pregunta de `consultar`, de hasta 200 caracteres (el tope del motivo en nodo-desplegar, que corta sin
    avisar): el mismo vocabulario cerrado que resumen_canal() y el defecto dicho con las letras."""
    if not (_es_cola(cola) and isinstance(n, int) and not isinstance(n, bool) and 0 < n <= CONSULTA_TOPE):
        raise ValueError("cola o número de consulta inválido")
    resumen_canal(et_id, fase, cuenta)                  # valida etapa y fase
    partes = [f"{int(cuenta.get(g, 0))} [{g.capitalize()}]" for g in ("media", "baja") if int(cuenta.get(g, 0)) > 0]
    cab = f"❓ {cola} #{n} · etapa {et_id}, {fase} NO DESPLEGABLE sin graves: {' y '.join(partes) or 'sin títulos'}"
    titulos = f" (títulos en encargos/{et_id}r{fase[3:]}-RESULTADO.md)"
    pie = (f". Sin respuesta en 2 h: {RESPUESTAS['saltar'].letra} si hay otras colas esperando; si no, "
           f"{RESPUESTAS['arreglar'].letra}.")
    motivo = cab + titulos + pie if len(cab + titulos + pie) <= 200 else cab + pie
    if len(motivo) > 200:
        raise ValueError("la pregunta no cabe en el motivo de nodo-desplegar")
    return motivo


def opciones_consulta() -> list[tuple[str, str]]:
    """[(clave, etiqueta)] de `consultar`, en el orden de las letras: constantes de este archivo."""
    return [(op, f"{r.etiqueta}: {r.despues}") for op, r in sorted(RESPUESTAS.items(), key=lambda x: x[1].letra)]


SIN_CONSULTAR = "sin consultar"     # lo que devuelve el canal si el nodo-desplegar instalado no conoce `consultar`


def _consultar_real(motivo: str, opciones: list[tuple[str, str]]) -> str | None:
    """Un `nodo-desplegar consultar`; el id del pedido, None o SIN_CONSULTAR. El instalado antes de la 71 contesta a
    un subcomando que no conoce con rc 2 y su ayuda, que no nombra `consultar`; el nuevo, cuando rechaza, siempre lo
    nombra. Un agente (NODO_PRUEBAS=1 con las rutas reales) no manda nada."""
    if os.environ.get("NODO_PRUEBAS") == "1" and L == Path.home() / "encargos-logs":
        return None
    argv = ["nodo-desplegar", "consultar", "--motivo", motivo]
    for clave, etiqueta in opciones:
        argv += ["--opcion", f"{clave}={etiqueta}"]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0 and "consultar" not in (p.stdout or "") + (p.stderr or ""):
        return SIN_CONSULTAR
    try:
        with (L / "avisos.log").open("a", encoding="utf-8") as fh:
            fh.write(p.stdout + p.stderr)
    except OSError:
        pass
    registrar_aviso(motivo, None, p)
    pid = (p.stdout.strip().splitlines() or [""])[-1]
    return pid if p.returncode == 0 and RE_ID_DESPLEGAR.fullmatch(pid) else None


CONSULTAR_CONSULTA = _consultar_real    # las pruebas lo reemplazan: nunca llaman a nodo-desplegar


def enviar_ronda(cola: str, n: int, et_id: str, fase: str, cuenta: dict[str, int], momento: datetime,
                 solo=None) -> tuple[dict, list[str]]:
    """Una ronda: UN `consultar` y, si el canal no lo aceptó, un reintento. (ronda, faltan): la ronda vale solo
    con faltan == [] (51r1, hallazgo 3). La de `consultar` es {'enviada', 'id', 'canal': 'consultar'}.
    Si el nodo-desplegar instalado no conoce `consultar`, la de antes: un `sugerir` por opción, {'enviada', 'ids'}.
    Con `solo` (las opciones que le faltaron a una ronda de `sugerir`), solo esas, por `sugerir`."""
    lineas, ids = lineas_consulta(cola, n, resumen_canal(et_id, fase, cuenta)), {}
    enviada = momento.isoformat(timespec="seconds")
    if solo is None:
        pregunta = (motivo_consulta(cola, n, et_id, fase, cuenta), opciones_consulta())
        for _ in range(2):
            try:
                pid = CONSULTAR_CONSULTA(*pregunta)
            except Exception:       # noqa: BLE001 — un canal caído no tira la cola: se aplica el defecto
                pid = None
            if isinstance(pid, str) and RE_ID_DESPLEGAR.fullmatch(pid):
                return {"enviada": enviada, "id": pid, "canal": "consultar"}, []
            if pid == SIN_CONSULTAR:
                break
        else:
            return {"enviada": enviada, "ids": {}}, list(RESPUESTAS)
        log(f"{cola}: el nodo-desplegar instalado no conoce `consultar` (es anterior a la 71): la consulta #{n} va "
            "en tres `sugerir`, como antes")
    for op in [o for o in RESPUESTAS if solo is None or o in solo]:
        for _ in range(2):
            try:
                pid = SUGERIR_CONSULTA(*lineas[op])
            except Exception:       # noqa: BLE001 — un canal caído no tira la cola: se aplica el defecto
                pid = None
            if isinstance(pid, str) and RE_ID_DESPLEGAR.fullmatch(pid):
                ids[op] = pid
                break
    faltan = [o for o in RESPUESTAS if (solo is None or o in solo) and o not in ids]
    return {"enviada": enviada, "ids": ids}, faltan


def mensajes_de(ronda: dict) -> int:
    """Cuántos mensajes le llegaron al usuario en esa ronda."""
    return 1 if ronda.get("canal") == "consultar" and ronda.get("id") else len(ronda.get("ids") or {})


def _systemd_real(argv: list[str]) -> subprocess.CompletedProcess | None:
    """`systemctl --user` o `systemd-run --user`; None si no se pudo correr. Un agente (NODO_PRUEBAS=1 con las rutas
    reales) no arma ni detiene nada."""
    if os.environ.get("NODO_PRUEBAS") == "1" and L == Path.home() / "encargos-logs":
        return None
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None


SYSTEMD = _systemd_real                 # las pruebas lo reemplazan: nunca tocan el systemd del usuario


def vigilantes() -> list[str] | None:
    """Los timers transitorios `encargos-consultas-*` activos; None si systemd no contestó."""
    p = SYSTEMD(["systemctl", "--user", "list-timers", "--output=json", f"{VIGILANTE}-*"])
    try:
        filas = json.loads(p.stdout or "[]") if p is not None and p.returncode == 0 else None
    except ValueError:
        filas = None
    if not isinstance(filas, list):
        return None
    return [t["unit"] for t in filas if isinstance(t, dict) and isinstance(t.get("unit"), str)
            and re.fullmatch(rf"{VIGILANTE}-[0-9]{{8}}-[0-9]{{6}}-[0-9a-f]{{4}}\.timer", t["unit"])]


def argv_vigilante(momento: datetime) -> list[str]:
    """El timer transitorio: corre `cola-run.py --consultas` cada 5 min hasta que alguien lo detenga (o un reinicio).
    Las propiedades son las de la unidad que no se llegó a instalar: oneshot y KillMode=process, porque «aceptar» y
    «arreglar» relanzan la cola en tmux y, si no había servidor, nace hijo de esta unidad (55r1, hallazgo 1)."""
    unidad = f"{VIGILANTE}-{momento:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    return ["systemd-run", "--user", f"--unit={unidad}", "--description=Consultas entre fases (encargo 51)",
            f"--on-active={VIGILANTE_CADA_S}s", f"--on-unit-active={VIGILANTE_CADA_S}s", "--timer-property=AccuracySec=30s",
            "-p", "Type=oneshot", "-p", "KillMode=process", "-p", "TimeoutStartSec=3min",
            "--", "/usr/bin/python3", str(Path(__file__).resolve()), "--consultas"]


def armar_vigilante(momento: datetime) -> bool:
    """Que haya un timer que recoja la respuesta y aplique el defecto. True solo si, después, systemd lo lista activo."""
    if vigilantes():
        return True
    p = SYSTEMD(argv_vigilante(momento))
    if p is None or p.returncode != 0:
        log(f"⚠️ no se pudo armar el timer de las consultas (rc {None if p is None else p.returncode})")
        return False
    return bool(vigilantes())


def _abierta(v: dict) -> bool:
    """Si la consulta de ese vivo espera respuesta: sin contestar y con la cola estacionada o todavía escribiendo
    el `en_consulta` (la cola arma el timer y suelta el candado antes de que main() lo anote)."""
    c = v.get("consulta")
    return (_consulta_valida(c) and not c.get("respuesta")
            and v.get("estado") in ("en_consulta", *ESTADOS_ACTIVOS))


def rearmar_vigilante(nom: str, vivos_dir: Path | None = None) -> None:
    """Al partir una cola: si otra quedó en consulta y no hay timer (un reinicio se lo lleva), se vuelve a armar."""
    vivos_dir = Path(vivos_dir or E / "vivo")
    if any(v["nombre"] != nom and _abierta(v) for v in leer_vivos(vivos_dir)[0]):
        armar_vigilante(ahora())


def en_descanso(momento: datetime) -> bool:
    if EN_DESCANSO is not None:
        return bool(EN_DESCANSO(momento))
    try:
        return bool(_descanso().en_descanso(momento))
    except Exception as e:      # noqa: BLE001 — falla abierto, como el emisor
        log(f"⚠️ modo descanso no disponible ({type(e).__name__}); la consulta se hace igual")
        return False


def leer_resultado(pid: str, resultados_dir: Path | None = None, dueno: int | None = None) -> tuple[dict | None, str]:
    """(resultado, problema) de /var/spool/nodo-desplegar/resultados/<id>.json. Sin el archivo: (None, "").
    Vale solo un archivo corriente, sin enlaces, del dueño del escucha (root): si no, `problema` dice por qué."""
    if not (isinstance(pid, str) and RE_ID_DESPLEGAR.fullmatch(pid)):
        return None, "el id no tiene la forma de un pedido de nodo-desplegar"
    ruta = (resultados_dir or RESULTADOS_DESPLEGAR) / f"{pid}.json"
    try:
        fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return None, ""
    except OSError as e:
        return None, f"el resultado no se pudo abrir ({type(e).__name__})"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None, "el resultado no es un archivo corriente"
        if st.st_uid != (DUENO_RESULTADOS if dueno is None else dueno):
            return None, "el resultado no lo escribió el escucha de nodo-desplegar (no es de root)"
        crudo = os.read(fd, TOPE_RESULTADO + 1)
    finally:
        os.close(fd)
    try:
        r = json.loads(crudo.decode("utf-8")) if len(crudo) <= TOPE_RESULTADO else None
    except (ValueError, UnicodeDecodeError):
        r = None
    if not (isinstance(r, dict) and r.get("id") == pid and isinstance(r.get("estado"), str)):
        return None, "el resultado no tiene la forma que deja nodo-desplegar"
    return r, ""


def respuesta_de(c: dict, resultados_dir: Path | None = None, dueno: int | None = None) -> tuple[tuple[str, str] | None, list[str]]:
    """((opción, id) de la respuesta, o None; los resultados ignorados). La respuesta es la primera elegida
    («hecho») de cualquier ronda: en una de `consultar`, la `opcion` que anotó el escucha; en una de tres `sugerir`
    (antes de la 71, o con el nodo-desplegar viejo), el ✅ de ese mensaje. ❌ («rechazado») y «vencido» no son
    respuesta."""
    hechos, ignoradas = [], []
    for ronda in c.get("rondas") if isinstance(c.get("rondas"), list) else []:
        if isinstance(ronda, dict) and ronda.get("canal") == "consultar":
            pid = ronda.get("id")
            r, problema = leer_resultado(pid, resultados_dir, dueno)
            op = r.get("opcion") if r else None
            if problema:
                ignoradas.append(f"consulta ({_texto_seguro(pid, 30)}): {problema}")
            elif r and r["estado"] == "hecho" and not (isinstance(op, str) and op in RESPUESTAS):
                ignoradas.append(f"{_texto_seguro(op, 20)} ({_texto_seguro(pid, 30)}): no es una de las tres respuestas")
            elif r and r["estado"] == "hecho":
                hechos.append((str(r.get("hora", "")), ORDEN_EMPATE.index(op), op, pid))
            continue
        ids = ronda.get("ids") if isinstance(ronda, dict) else None
        for op, pid in (ids.items() if isinstance(ids, dict) else ()):
            if op not in RESPUESTAS:
                ignoradas.append(f"{_texto_seguro(op, 20)}: no es una de las tres respuestas")
                continue
            r, problema = leer_resultado(pid, resultados_dir, dueno)
            if problema:
                ignoradas.append(f"{op} ({_texto_seguro(pid, 30)}): {problema}")
            elif r and r["estado"] == "hecho":
                hechos.append((str(r.get("hora", "")), ORDEN_EMPATE.index(op), op, pid))
    if not hechos:
        return None, ignoradas
    _, _, op, pid = min(hechos)
    return (op, pid), ignoradas


def otras_esperando(nom: str, vivos_dir: Path, momento: datetime, prioridad: Path | None = None) -> list[str]:
    """Las otras colas que esperan turno: con un vivo activo y fresco, pausadas por cuota (las relanza el
    despachador) o en prioridad.txt sin haber partido nunca."""
    out = []
    for v in leer_vivos(vivos_dir)[0]:
        n = v["nombre"]
        if n == nom or not _es_cola(n):
            continue
        escrito = _hora(v.get("escrito"))
        if v["estado"] in ESTADOS_ACTIVOS and escrito and (momento - escrito).total_seconds() < ACTIVA_FRESCA_S:
            out.append(n)
        elif v["estado"] == "pausada" and PAUSA_POR_CUOTA.search(_una_linea(v.get("motivo_pausa"))):
            out.append(n)
    try:
        lineas = (prioridad or vivos_dir.parent / "prioridad.txt").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        lineas = []
    for linea in lineas:
        n = linea.strip()
        if _es_cola(n) and n != nom and n not in out and _vivo_de(n, vivos_dir) is None:
            out.append(n)
    return out


def anotar_decision(et_id: str, linea: str, carpeta: Path | None = None) -> None:
    """Agrega una línea a encargos/<etapa>-decisiones.md, con `flock`. Lo leen el arreglo y la revisión siguientes."""
    if not RE_ETAPA.fullmatch(str(et_id)):
        raise ValueError("id de etapa inválido para decisiones.md")
    fd = _abrir_para_agregar((carpeta or E) / f"{et_id}-decisiones.md", 0o644)
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, (f"# Decisiones del usuario — etapa {et_id}\n\nLas anota cola-run.py (encargo 51): quién, cuándo "
                          "y qué. Lo decidido aquí no se vuelve a marcar como hallazgo.\n\n").encode("utf-8"))
        os.write(fd, (_texto_seguro(linea, 1200) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def _linea_decision(momento: datetime, cola: str, c: dict, op: str, por: str) -> str:
    return (f"- {momento.astimezone():%Y-%m-%d %H:%M} · {cola} · etapa {c['etapa']} tras {c['fase']} · consulta #{c['n']} · "
            f"{op} («{RESPUESTAS[op].etiqueta}») · quién: {por} · pregunta: {c.get('pregunta', '')}")


def _aceptada(et_id: str, desde_fase: str) -> dict | None:
    """La aceptación del usuario que deja saltar el arreglo `desde_fase` de esa etapa, o None. Se vuelve a leer
    del escucha root: una aceptación sin su ✅ verificable (o de otro dueño) no salta nada y la etapa se arregla."""
    if not desde_fase.startswith("fix"):
        return None
    for a in VIVO.get("aceptadas_usuario") or []:
        if isinstance(a, dict) and a.get("etapa") == et_id and a.get("tras") == f"rev{desde_fase[3:]}":
            r, problema = leer_resultado(a.get("pedido"))
            # Un pedido de `consultar` vale solo si lo elegido fue «aceptar»: el mismo id resuelve las tres.
            if r and r["estado"] == "hecho" and r.get("opcion", "aceptar") == "aceptar":
                return a
            log(f"{et_id}: la aceptación anotada no se pudo verificar ({problema or 'sin ✅ del usuario'}): se arregla")
    return None


def consultar_o_seguir(et: dict, fase: str, texto: str) -> None:
    """Tras una revisión NO DESPLEGABLE a la que le sigue un arreglo. Vuelve si la etapa sigue con el arreglo,
    como siempre; lanza Consulta si la cola queda estacionada en `en_consulta`."""
    i, nom = et["id"], MANIFIESTO["nombre"]
    desde = f"{i}:fix{fase[3:]}"
    pregunta_ok, razon, hallado = disparador(texto)
    if not pregunta_ok:
        log(f"{i}: {razon}")
        return
    previas = VIVO.get("consultas_n", 0)
    n = previas if isinstance(previas, int) and not isinstance(previas, bool) and previas >= 0 else CONSULTA_TOPE
    if n >= CONSULTA_TOPE:
        log(f"{i}: esta cola ya hizo {n} consultas (tope {CONSULTA_TOPE}): va al arreglo, sin consulta")
        return
    momento = ahora()
    otras = otras_esperando(nom, E / "vivo", momento)
    defecto = "saltar" if otras else "arreglar"
    c = {"n": n + 1, "etapa": i, "fase": fase, "pregunta": armar_pregunta(nom, i, fase, n + 1, hallado),
         "hallazgos": [f"[{g.capitalize()}] {t}" for g, t in hallado], "desde": momento.isoformat(timespec="seconds"),
         "plazo": (momento + timedelta(seconds=CONSULTA_PLAZO_S)).isoformat(timespec="seconds"),
         "defecto": defecto, "otras_esperando": otras, "rondas": []}
    parcial = False
    if en_descanso(momento):
        por = "defecto, en silencio: modo descanso (no se pregunta)"
    else:
        # Bajo el candado de `--consultas`: una pasada que no ve consultas abiertas detiene el timer, y no puede
        # hacerlo entre que este lo arma y el vivo anota la consulta.
        candado = _abrir_para_agregar(E / "vivo" / "consultas.lock", 0o600)
        try:
            if not armar_vigilante(momento):
                por = "defecto: no se pudo armar el timer que recoge la respuesta (no se preguntó)"
            else:
                ronda, faltan = enviar_ronda(nom, n + 1, i, fase, conteo(hallado), momento)
                if not faltan:
                    c["rondas"].append(ronda)
                    vivo(consulta=c, consultas_n=n + 1)
                    log(f"{i}: ❓ consulta #{n + 1} al usuario ({mensajes_de(ronda)} mensaje{'s' if mensajes_de(ronda) != 1 else ''}); plazo hasta "
                        f"{momento + timedelta(seconds=CONSULTA_PLAZO_S):%H:%M}. La cola queda estacionada y la cadena sigue")
                    raise Consulta(desde, f"en consulta al usuario: {i} {fase} sin graves; plazo hasta "
                                          f"{momento + timedelta(seconds=CONSULTA_PLAZO_S):%H:%M}")
                if ronda["ids"]:
                    # Una ronda a medias no se estaciona: el usuario no tendría las tres respuestas (51r1, hallazgo 3).
                    parcial = True
                    por = (f"defecto: nodo-desplegar no aceptó la consulta completa (faltan: {', '.join(faltan)}); "
                           "los botones que llegaron no cuentan")
                else:
                    por = "defecto: nodo-desplegar no aceptó ningún mensaje de la consulta"
        finally:
            os.close(candado)
    # Sin pregunta: el defecto, en el momento. No cuenta para el tope, salvo que algún mensaje haya llegado.
    c.update(respuesta=defecto, por=por, respondida=c["desde"])
    anotar_decision(i, _linea_decision(momento, nom, c, defecto, por))
    log(f"{i}: {por} → {defecto}")
    if parcial:
        vivo(consultas_n=n + 1)
        avisar_texto(f"⚠️ La consulta {nom} #{n + 1} (etapa {i}) no se pudo mandar completa: llegaron "
                     f"{3 - len(faltan)} de 3 botones y no cuentan. Se aplicó el defecto: «{RESPUESTAS[defecto].etiqueta}».")
    if defecto == "arreglar":
        return
    vivo(consulta=c)
    raise Consulta(desde, f"saltada sin preguntar ({por}); se retoma con Reanudar")


def _consulta_valida(c) -> bool:
    return (isinstance(c, dict) and isinstance(c.get("n"), int) and isinstance(c.get("etapa"), str)
            and RE_ETAPA.fullmatch(c["etapa"]) is not None and isinstance(c.get("fase"), str)
            and re.fullmatch(r"rev[0-9]", c["fase"]) is not None and _hora(c.get("plazo")) is not None
            and isinstance(c.get("rondas"), list))


def _atender(v: dict, c: dict, momento: datetime, vivos_dir: Path, carpeta: Path, tmux: tuple, lanzar,
             resultados_dir: Path | None, dueno: int | None, carpeta_decisiones: Path | None) -> dict:
    nom = v["nombre"]
    res = {"cola": nom, "accion": "nada"}
    if _sesion(tmux, nom) is not False:
        res["detalle"] = "su sesión está viva o tmux no contestó: no se toca"
        return res
    if not _consulta_valida(c):
        res["detalle"] = "la consulta del vivo no tiene la forma que deja la cola: lo decide el usuario"
        return res
    resp, ignoradas = respuesta_de(c, resultados_dir, dueno)
    nuevas = [x for x in ignoradas if x not in (c.get("ignoradas") or [])]
    for x in nuevas:
        anotar_decision(c["etapa"], f"- {momento.astimezone():%Y-%m-%d %H:%M} · {nom} · consulta #{c['n']} · respuesta "
                                    f"IGNORADA (no viene del chat del usuario): {x}", carpeta_decisiones)
    c["ignoradas"] = list(c.get("ignoradas") or []) + nuevas
    rondas = [r for r in c["rondas"] if isinstance(r, dict) and _hora(r.get("enviada"))]
    ultima = max((_hora(r.get("completada")) or _hora(r["enviada"]) for r in rondas), default=None)
    viva_ronda = ultima is not None and (momento - ultima).total_seconds() < CONSULTA_RONDA_S
    pid = None
    if resp:
        op, pid = resp
        por = f"el usuario (✅ en Telegram, pedido {pid})"
    elif momento >= _hora(c["plazo"]) or (not viva_ronda and en_descanso(momento)):
        otras = otras_esperando(nom, vivos_dir, momento)
        op = "saltar" if otras else "arreglar"
        por = ("defecto: venció el plazo de 2 h" if momento >= _hora(c["plazo"]) else "defecto, en silencio: modo descanso")
        por += f"; hay otras colas esperando ({', '.join(otras)})" if otras else "; no hay otras colas esperando"
    else:
        # El resumen se rehace con lo validado (etapa, fase y cuántos hay de cada gravedad), no se copia del vivo.
        cuenta = conteo(c.get("hallazgos"))
        incompleta = rondas[-1] if rondas and rondas[-1].get("faltan") else None
        if incompleta is not None and int(incompleta.get("reintentos") or 0) < CONSULTA_REINTENTOS:
            # 51r1, hallazgo 3: a una ronda le faltaron opciones; se reintentan solo esas, con el mismo plazo.
            faltaban = [o for o in incompleta["faltan"] if o in RESPUESTAS]
            ronda, faltan = enviar_ronda(nom, c["n"], c["etapa"], c["fase"], cuenta, momento, solo=faltaban)
            incompleta.update(ids=dict(incompleta.get("ids") or {}, **ronda["ids"]), faltan=faltan,
                              reintentos=int(incompleta.get("reintentos") or 0) + 1)
            if ronda["ids"]:
                incompleta["completada"] = momento.isoformat(timespec="seconds")
            res.update(accion="ronda", detalle=f"ronda {len(rondas)}: se reintentó lo que faltaba ({', '.join(faltaban)}); "
                                               f"falta: {', '.join(faltan) or 'nada'}")
        elif not viva_ronda and len(rondas) < CONSULTA_PLAZO_S // CONSULTA_RONDA_S:
            ronda, faltan = enviar_ronda(nom, c["n"], c["etapa"], c["fase"], cuenta, momento)
            if mensajes_de(ronda):
                c["rondas"].append(ronda | ({"faltan": faltan} if faltan else {}))
                res.update(accion="ronda", detalle=f"ronda {len(c['rondas'])}: se volvió a preguntar ({mensajes_de(ronda)} mensajes"
                                                   + (f"; falta: {', '.join(faltan)}" if faltan else "") + ")")
        if res["accion"] == "nada":
            res["detalle"] = "sin respuesta todavía"
        if nuevas or res["accion"] == "ronda":
            _escribir_vivo(vivos_dir / f"{nom}.json", dict(v, consulta=c))
        return res
    c.update(respuesta=op, por=por, respondida=momento.isoformat(timespec="seconds"))
    nv = dict(v, consulta=c)
    if op == "aceptar":
        nv["aceptadas_usuario"] = [a for a in (v.get("aceptadas_usuario") or []) if isinstance(a, dict)] + [
            {"etapa": c["etapa"], "tras": c["fase"], "pedido": pid, "momento": momento.isoformat(timespec="seconds")}]
    elif op == "saltar":
        nv["motivo_pausa"] = f"en consulta: «{RESPUESTAS['saltar'].etiqueta}» ({por}); se retoma con Reanudar"
    _escribir_vivo(vivos_dir / f"{nom}.json", nv)
    anotar_decision(c["etapa"], _linea_decision(momento, nom, c, op, por), carpeta_decisiones)
    res.update(accion=op, por=por)
    if op in ("aceptar", "arreglar"):
        # Por el mismo camino que el botón Reanudar (46c): respeta el despacho y deja su línea en acciones.jsonl.
        r = accion_cola("reanudar", nom, vivos_dir=vivos_dir, manifiestos_dir=carpeta, tmux=tmux, lanzar=lanzar,
                        momento=momento)
        res["reanudar"] = {k: r.get(k) for k in ("ok", "desde", "mensaje", "error")}
    return res


def atender_consultas(*, vivos_dir: Path | None = None, manifiestos_dir: Path | None = None, momento: datetime | None = None,
                      tmux: tuple | None = None, lanzar=None, resultados_dir: Path | None = None, dueno: int | None = None,
                      carpeta_decisiones: Path | None = None) -> list[dict]:
    """`cola-run.py --consultas` (el timer transitorio `encargos-consultas-*`): por cada cola en `en_consulta` con la
    consulta abierta, recoge la respuesta, vuelve a preguntar si venció la ronda (o reintenta lo que le faltó) o
    aplica el defecto si venció el plazo. Si ya no queda ninguna abierta, detiene el timer. Corre entero bajo el
    `flock` de vivo/consultas.lock; nunca lanza."""
    momento, tmux = momento or ahora(), tuple(tmux or TMUX)
    vivos_dir, carpeta = Path(vivos_dir or E / "vivo"), Path(manifiestos_dir or E)
    out: list[dict] = []
    try:
        candado = _abrir_para_agregar(vivos_dir / "consultas.lock", 0o600)
    except OSError as e:
        return [{"cola": None, "accion": "nada", "detalle": f"no se pudo tomar el candado ({type(e).__name__})"}]
    try:
        for v in leer_vivos(vivos_dir)[0]:
            c = v.get("consulta")
            if v.get("estado") != "en_consulta" or not _es_cola(v["nombre"]) or not isinstance(c, dict) or c.get("respuesta"):
                continue
            try:
                out.append(_atender(v, c, momento, vivos_dir, carpeta, tmux, lanzar, resultados_dir, dueno, carpeta_decisiones))
            except Exception as e:      # noqa: BLE001 — una cola rara no deja sin atender a las demás
                out.append({"cola": v["nombre"], "accion": "nada", "detalle": f"falló ({type(e).__name__})"})
        # Sin consultas abiertas, el timer transitorio ya no tiene qué hacer: se detiene (y systemd lo olvida).
        if not any(_abierta(v) for v in leer_vivos(vivos_dir)[0]) and (armados := vigilantes()):
            SYSTEMD(["systemctl", "--user", "stop", *armados])
    finally:
        os.close(candado)
    return out


# ---------------------------------------------------------------- botones de 🧵 Encargos (encargo 46c)

RE_COLA = re.compile(r"cola[0-9]{2}[a-z0-9]*")      # el nombre que acepta --accion: siempre con fullmatch (un `$` deja pasar «cola46\n»)
ACCIONES = ("reanudar", "pausar", "detener")
PAUSABLES = ANTES_DE_PARTIR + ("corriendo", "esperando_cuota")      # estados en que todavía queda una fase por empezar
MOTIVO_PAUSA_USUARIO = "pausada por el usuario desde 🧵 Encargos"
MOTIVO_DETENIDA_USUARIO = "detenida por el usuario desde 🧵 Encargos"
TMUX = ("tmux",)
CORTE_ESPERA_S = 0.3        # cada cuánto se vuelve a mirar, después de cortar una sesión
CORTE_VUELTAS = 10          # y cuántas veces: 3 s para que tmux cierre la sesión
COLA_EN_MARCHA: str | None = None       # el nombre de la cola que partió en ESTE proceso; lo fija main()


class PausaUsuario(Pausa):
    """La pausa que pidió el usuario con el botón Pausar: no es un problema de la cola."""

    def __init__(self, desde: str):
        super().__init__(MOTIVO_PAUSA_USUARIO, desde)


def _marca_pausa(nom: str, vivos_dir: Path | None = None) -> Path:
    return (vivos_dir or E / "vivo") / f"{nom}.pausar"


def pausa_pedida(nom: str, vivos_dir: Path | None = None) -> bool:
    """Si está la marca vivo/<cola>.pausar que deja `--accion pausar`. Solo cuenta un archivo corriente: un
    enlace simbólico o una carpeta con ese nombre no pausan nada."""
    try:
        return stat.S_ISREG(os.lstat(_marca_pausa(nom, vivos_dir)).st_mode)
    except OSError:
        return False


def soltar_pausa(nom: str, vivos_dir: Path | None = None) -> None:
    try:
        os.unlink(_marca_pausa(nom, vivos_dir))     # unlink no sigue un enlace: borra el nombre, no su destino
    except OSError:
        pass


def atender_pausa(desde: str) -> None:
    """El punto de pausa de etapa(): si el usuario pidió pausar, la fase `desde` no empieza."""
    if pausa_pedida(MANIFIESTO["nombre"]):
        raise PausaUsuario(desde)


def argv_relanzar(nom: str, ruta: Path, desde: str) -> list[str]:
    """La línea que relanza una cola desde `desde`, como argv: es la que manda la pausa (unida con espacios, para
    copiar) y la que ejecuta `--accion reanudar`, sin shell."""
    return ["tmux", "new-session", "-d", "-s", nom, "python3", str(Path(__file__).resolve()), str(ruta), "--desde", desde]


def manifiestos_con_ruta(carpeta: Path) -> dict[str, tuple[Path, dict] | None]:
    """{nombre: (ruta, manifiesto)} de `carpeta`.
    El primer nombre gana. Cada manifiesto debe ser un archivo corriente dentro de su propio
    directorio; un enlace, ejemplo `solo_simular` o etapa sin `id` no se puede lanzar."""
    out = {}
    for raiz in (Path(carpeta),):
        base = raiz.resolve()
        for ruta in sorted(raiz.glob("cola-*.toml")):
            try:
                man = tomllib.loads(ruta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not (isinstance(man.get("nombre"), str) and isinstance(man.get("etapa"), list) and man["etapa"]) or man["nombre"] in out:
                continue
            real = ruta.resolve()
            bien = (not ruta.is_symlink() and real.parent == base and real.is_file() and not man.get("solo_simular")
                    and all(isinstance(et, dict) and isinstance(et.get("id"), str) for et in man["etapa"]))
            out[man["nombre"]] = (real, man) if bien else None
    return out


def _desde_valido(desde, etapas: list[dict]) -> bool:
    """Si `desde` («46b:rev2») nombra una etapa del manifiesto y una fase que esa etapa tiene. Un `--desde` con
    una etapa que no existe haría que la cola se saltara todo y fuera directo a las pruebas finales."""
    if not isinstance(desde, str):
        return False
    et_id, fase = _etapa_fase(desde)
    et = next((e for e in etapas if e["id"] == et_id), None)
    try:
        return et is not None and fase in [*(FASES_PLAN if et.get("plan") else ()), *FASES[: 1 + 2 * (0 if remota(et) else int(et.get("vueltas", 2))) + 1]]
    except (TypeError, ValueError):
        return False


def _desde_del_vivo(v: dict | None, etapas: list[dict]) -> str | None:
    """El `--desde` que deja ese vivo, o None: `reanuda_desde` si la cola terminó en pausa o detenida, y la fase
    en que estaba (o su punto de partida, si no alcanzó a empezar una) si quedó en un estado activo. Sale
    siempre del vivo, nunca de quien llama, y tiene que nombrar una fase que el manifiesto tenga."""
    if not v or not (v.get("estado") in ESTADOS_ACTIVOS or isinstance(v.get("reanuda_desde"), str)):
        return None
    try:
        punto = _punto_de_reanudacion(v, etapas)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    desde = f"{punto[0]}:{punto[1]}" if punto else None
    return desde if _desde_valido(desde, etapas) else None


def timers_usuario(correr=None) -> list[dict]:
    """Todos los timers de usuario, también los que ya dispararon: [{'unidad', 'proxima', 'ultima', 'orden'}].
    `proxima` y `ultima` son horas o None y `orden` es el ExecStart de lo que activa. 🧵 Encargos los muestra en
    modo solo lectura (46c); accionarlos es de ⏰ Programados. Si systemd no contesta, ninguno."""
    correr = correr or subprocess.run
    hora = lambda x: datetime.fromtimestamp(x / 1e6).astimezone() if _num(x) and x > 0 else None
    try:
        filas = json.loads(correr(["systemctl", "--user", "list-timers", "--all", "--output=json"],
                                  capture_output=True, text=True, timeout=15).stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    out = []
    for t in filas if isinstance(filas, list) else []:
        if not (isinstance(t, dict) and isinstance(t.get("unit"), str) and isinstance(t.get("activates"), str)):
            continue
        try:
            orden = correr(["systemctl", "--user", "show", t["activates"], "-p", "ExecStart", "--value"],
                           capture_output=True, text=True, timeout=15).stdout or ""
            out.append({"unidad": t["unit"], "proxima": hora(t.get("next")), "ultima": hora(t.get("last")), "orden": orden})
        except (OSError, ValueError, OverflowError, subprocess.SubprocessError):
            continue
    return out


def _nombra(orden: str, nom: str) -> bool:
    """Si el ExecStart de un timer nombra a esa cola: la regla con que matriz_cuota() busca su reanudación."""
    return bool(re.search(rf"(?<![\w.-]){re.escape(nom)}(?![\w.-])", orden))


def _puede(accion: str, v: dict | None, etapas: list[dict], viva: bool | None, momento: datetime) -> tuple[bool, str, str | None]:
    """(se puede, por qué no, --desde): la única regla de qué acción vale para una cola. La usan `--accion`, al
    momento de actuar, y `--panel`, para que la página ofrezca solo los botones que van a funcionar.
    `viva` es si existe la sesión tmux `=<cola>` (None: no se pudo consultar) y `v`, su vivo (None: no se leyó).
    El `--desde` es el de `_desde_del_vivo()`."""
    estado = v.get("estado") if v else None
    if viva is None:
        return False, "no se pudo consultar tmux", None
    if accion == "pausar":
        if not viva:
            return False, "no tiene una sesión viva: no hay nada que pausar", None
        if estado not in PAUSABLES:
            return False, f"está en «{_una_linea(estado, 40) or 'sin vivo'}»: ya no le queda una fase por empezar", None
        return True, "", None
    activa, desde = estado in ESTADOS_ACTIVOS, _desde_del_vivo(v, etapas)
    if accion == "detener":
        if not viva and not activa:
            return False, "no tiene una sesión viva ni quedó a medias: no hay nada que detener", None
        return True, "", desde if activa else None
    if viva:
        return False, "su sesión ya está viva", None
    if v is None:
        return False, "no tiene un vivo legible: no se sabe desde dónde seguiría", None
    if estado == "pausada":
        if not PAUSA_POR_CUOTA.search(_una_linea(v.get("motivo_pausa"))):
            return False, "está en pausa por un motivo que no es la cuota: eso se decide a mano", None
    elif estado == "detenida":
        if not isinstance(v.get("reanuda_desde"), str):
            return False, "se detuvo sin dejar desde dónde seguir (una etapa quedó NO DESPLEGABLE o fallaron las pruebas finales)", None
    elif activa:
        escrito = _hora(v.get("escrito"))
        if not escrito or (momento - escrito).total_seconds() < ACTIVA_FRESCA_S:
            return False, f"su vivo dice «{estado}» hace menos de 2 h y no hay sesión: si se cortó, primero Detener", None
    elif estado not in ("pausada_por_usuario", "retenida_por_despacho", "en_consulta"):
        return False, f"está en «{_una_linea(estado, 40)}»: no se reanuda desde acá", None
    if desde is None:
        return False, "su vivo no deja una fase del manifiesto desde donde seguir", None
    return True, "", desde


def botones_colas(vivos_dir: Path | None = None, viva=None, manifiestos_dir: Path | None = None,
                  momento: datetime | None = None, timers_todos: list[dict] | None = None) -> dict[str, dict]:
    """Lo que `--panel` publica en `colas` (46c), por cada cola con un vivo legible que no terminó:
    `acciones` (los botones que valen ahora, según `_puede()`), `pausa_pedida` (está la marca), `no_reanuda` (por
    qué no se ofrece Reanudar a una cola que no corre) y `timers` (los de usuario que la nombran: unidad,
    próxima hora y si ya venció). Solo informa: la acción vuelve a decidir todo cuando se la llama."""
    momento = momento or ahora()
    vivos_dir, viva, carpeta = vivos_dir or E / "vivo", viva or sesion_viva, manifiestos_dir or E
    vivos = [v for v in leer_vivos(vivos_dir)[0] if v["estado"] != "terminada" and RE_COLA.fullmatch(v["nombre"])]
    if not vivos:
        return {}       # sin colas que mostrar no se le pregunta nada a systemd ni a tmux
    filas = timers_usuario() if timers_todos is None else timers_todos
    manifiestos = manifiestos_con_ruta(carpeta)
    out: dict[str, dict] = {}
    for v in vivos:
        nom = v["nombre"]
        hallado = manifiestos.get(nom)
        sesion = bool(viva(nom))
        acciones, no_reanuda = [], "no hay un manifiesto con ese nombre"
        if hallado:
            puede = {a: _puede(a, v, hallado[1]["etapa"], sesion, momento) for a in ACCIONES}
            acciones, no_reanuda = [a for a in ACCIONES if puede[a][0]], puede["reanudar"][1]
        out[nom] = {"acciones": acciones, "pausa_pedida": sesion and pausa_pedida(nom, vivos_dir),
                    "no_reanuda": "" if sesion or "reanudar" in acciones else no_reanuda,
                    "timers": [{"unidad": _una_linea(t["unidad"], 80),
                                "proxima": t["proxima"].isoformat(timespec="seconds") if t["proxima"] else None,
                                "vencido": not (t["proxima"] and t["proxima"] > momento)}
                               for t in filas if _nombra(t["orden"], nom)]}
    return out


def _sesion(tmux: tuple, nom: str) -> bool | None:
    """Si existe la sesión tmux `=<nom>` (el `=` exige el nombre entero: sin él, `cola4` calzaría con `cola46`).
    None si no se pudo preguntar."""
    try:
        return subprocess.run([*tmux, "has-session", "-t", f"={nom}"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return None


def _lanzar(argv: list[str]) -> int:
    """El lanzador de verdad: corre la línea `relanzar` tal cual, sin shell."""
    return subprocess.run(argv, capture_output=True, timeout=30).returncode


def _vivo_de(nom: str, vivos_dir: Path) -> dict | None:
    """El vivo de esa cola, o None si no está, es un enlace o llegó a medias (otro lo está escribiendo)."""
    try:
        v = _leer_vivo(vivos_dir / f"{nom}.json")
    except (OSError, ValueError, RecursionError):
        return None
    return v if isinstance(v, dict) and v.get("nombre") == nom and isinstance(v.get("estado"), str) else None


def _abrir_para_agregar(ruta: Path, modo: int) -> int:
    """Abre para agregar un archivo compartido (la bitácora, el registro de acciones) y toma su `flock`: sin
    seguir un enlace, sin colgarse de un FIFO y solo si es un archivo corriente."""
    fd = os.open(ruta, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, modo)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"{ruta.name} no es un archivo corriente")
        fcntl.flock(fd, fcntl.LOCK_EX)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _escribir_vivo(ruta: Path, v: dict, modo: int | None = None) -> None:
    """Reemplaza vivo/<cola>.json de forma atómica, con un .tmp PROPIO de este proceso: la cola usa
    `.<cola>.json.tmp`, y dos escritores con el mismo temporal se pisan. El modo es el de cualquier archivo que
    crea este usuario, como los que escribe vivo(); con `modo` (el 0600 de vivo/despacho.json) queda ese, exacto."""
    tmp = ruta.with_name(f".{ruta.name}.accion-{os.getpid()}-{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o666 if modo is None else modo)
    try:
        if modo is not None:
            os.fchmod(fd, modo)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(v, ensure_ascii=False, indent=1))
        os.replace(tmp, ruta)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- despacho (encargo 50a)

DESPACHO_ORDENES = ("abrir", "pausar")
TOPE_DESPACHO = 64 * 1024       # un despacho.json más grande no se lee
CODIGO_RETENIDA = 5             # con lo que sale una cola que no partió por el despacho en pausa


def _despacho_abierto() -> dict:
    return {"estado": "abierto", "desde": None, "motivo": "", "autorizadas": [], "por": ""}


def leer_despacho(vivos_dir: Path | None = None) -> tuple[dict, str]:
    """(despacho, aviso) de vivo/despacho.json: `{estado: "abierto"|"pausa", desde, motivo, autorizadas, por}`.
    Si el archivo falta, el despacho está abierto, que es la conducta de antes del encargo 50a, y no hay aviso.
    Si está pero no sirve (JSON a medias, otra forma, un enlace, un FIFO, demasiado grande) también se trata
    como abierto, y `aviso` dice por qué: el que arranca lo deja en la bitácora y el panel lo publica.
    Se lee sin candado: el que escribe reemplaza el archivo entero con `rename`."""
    ruta = (vivos_dir or E / "vivo") / "despacho.json"
    try:
        fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return _despacho_abierto(), ""
    except OSError as e:
        return _despacho_abierto(), f"despacho.json no se pudo abrir ({type(e).__name__}): el despacho se trata como abierto"
    try:
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("no es un archivo corriente")
            crudo = b""
            while len(crudo) <= TOPE_DESPACHO and (trozo := os.read(fd, TOPE_DESPACHO + 1 - len(crudo))):
                crudo += trozo
        finally:
            os.close(fd)
        if len(crudo) > TOPE_DESPACHO:
            raise ValueError("es demasiado grande")
        d = json.loads(crudo.decode("utf-8"))
        if not (isinstance(d, dict) and d.get("estado") in ("abierto", "pausa")):
            raise ValueError("no trae un estado «abierto» o «pausa»")
        autorizadas = d.get("autorizadas", [])
        if not (isinstance(autorizadas, list) and all(isinstance(c, str) and RE_COLA.fullmatch(c) for c in autorizadas)):
            raise ValueError("`autorizadas` no es una lista de nombres de cola")
        if d.get("desde") is not None and _hora(d["desde"]) is None:
            raise ValueError("`desde` no es una hora")
    except (OSError, ValueError, RecursionError) as e:
        detalle = "el JSON está a medias o roto" if isinstance(e, json.JSONDecodeError) else _una_linea(e, 80) or type(e).__name__
        return _despacho_abierto(), f"despacho.json no se pudo leer ({detalle}): el despacho se trata como abierto"
    return {"estado": d["estado"], "desde": d.get("desde"), "motivo": _una_linea(d.get("motivo"), 200),
            "autorizadas": list(dict.fromkeys(autorizadas)), "por": _una_linea(d.get("por"), 60)}, ""


def _escribir_despacho(vivos_dir: Path, nuevo: dict) -> None:
    """Deja `nuevo` en vivo/despacho.json (0600) de forma atómica y lo vuelve a leer. Quien llama tiene el
    `flock` de vivo/acciones.jsonl: es el candado de todo el que escribe el despacho. OSError si no quedó."""
    _escribir_vivo(vivos_dir / "despacho.json", nuevo, 0o600)
    if leer_despacho(vivos_dir)[0] != nuevo:
        raise OSError("despacho.json no quedó como se escribió")


def _hora_despacho(d: dict, momento: datetime | None = None) -> str:
    """«las 16:55» si el despacho cambió hoy y «el 11-10 a las 16:55» si no: como lo dice la página."""
    desde = _hora(d.get("desde"))
    if not desde:
        return "una hora sin datos"
    desde = desde.astimezone()
    hoy = (momento or ahora()).astimezone().date()
    return f"las {desde:%H:%M}" if desde.date() == hoy else f"el {desde:%d-%m} a las {desde:%H:%M}"


def cambiar_despacho(orden: str, motivo: str | None = None, autorizar=(), por: str | None = None, *,
                     vivos_dir: Path | None = None, momento: datetime | None = None) -> dict:
    """`--despacho {abrir|pausar} [--motivo T] [--por T] [--autorizar colaNN ...]`: el único que cambia el
    estado del despacho (además del Reanudar de `--accion`, que solo agrega su cola a `autorizadas`).
    Devuelve {'ok', 'accion': 'despacho', 'orden', 'despacho', 'mensaje' o 'error'} y nunca lanza.

    - pausar: deja «pausa» desde ahora. Si ya estaba en pausa conserva `desde` (y `motivo` y `por`, si no
      vienen otros) y suma las colas de `autorizar` a las que ya estaban.
    - abrir: deja «abierto» desde ahora y sin autorizadas. No lleva `autorizar`. Si ya estaba abierto por una
      orden anterior, conserva su `desde`, igual que pausar.
    Los nombres de `autorizar` son datos hostiles: cada uno calza entero con RE_COLA, el patrón de `--accion`,
    o no se escribe nada. `motivo` y `por` son texto libre de una línea, recortado. Corre entero bajo el
    `flock` de vivo/acciones.jsonl (leer, decidir, reemplazar y releer) y termina agregándole una línea."""
    momento, vivos_dir = momento or ahora(), Path(vivos_dir or E / "vivo")
    autorizar = [autorizar] if isinstance(autorizar, str) else list(autorizar or [])
    res: dict = {"ok": False, "accion": "despacho", "orden": orden}
    registro, actuo = None, False
    try:
        if orden not in DESPACHO_ORDENES:
            res["error"] = "orden de despacho desconocida"
            return res
        registro = _abrir_para_agregar(vivos_dir / "acciones.jsonl", 0o600)
        os.fchmod(registro, 0o600)
        if not all(isinstance(c, str) and RE_COLA.fullmatch(c) for c in autorizar):
            res["error"] = "nombre de cola inválido en las autorizadas: «cola», dos dígitos y, si sigue algo, letras minúsculas o dígitos"
            return res
        if orden == "abrir" and autorizar:
            res["error"] = "abrir el despacho no lleva colas autorizadas: con el despacho abierto corren todas"
            return res
        previo, aviso = leer_despacho(vivos_dir)
        estado = "pausa" if orden == "pausar" else "abierto"
        sigue = previo["estado"] == estado and previo["desde"] is not None        # ya estaba así, por una orden anterior
        nuevo = {"estado": estado, "desde": previo["desde"] if sigue else momento.isoformat(timespec="seconds"),
                 "motivo": _una_linea(motivo, 200) if motivo is not None else previo["motivo"] if sigue else "",
                 "autorizadas": list(dict.fromkeys((previo["autorizadas"] if sigue else []) + autorizar)) if estado == "pausa" else [],
                 "por": _una_linea(por, 60) or (previo["por"] if sigue else "") or "la terminal"}
        actuo = True
        _escribir_despacho(vivos_dir, nuevo)
        res.update(ok=True, despacho=nuevo)
        con = f" Colas autorizadas: {', '.join(nuevo['autorizadas'])}." if nuevo["autorizadas"] else ""
        if orden == "abrir":
            res["mensaje"] = ("El despacho ya estaba abierto." if sigue else
                              "El despacho quedó abierto. Una cola retenida no parte sola: se reanuda con el botón Reanudar.")
        elif sigue:
            res["mensaje"] = f"El despacho ya estaba en pausa desde {_hora_despacho(nuevo, momento)}; sigue en pausa.{con}"
        else:
            res["mensaje"] = (f"El despacho quedó en pausa desde {_hora_despacho(nuevo, momento)}. Una cola que arranque queda "
                              f"retenida, salvo las autorizadas.{con}")
        if aviso:
            res["aviso"] = aviso
    except Exception as e:      # noqa: BLE001 — pase lo que pase, la página recibe un JSON y el registro, su línea
        res.update(ok=False, error=f"el despacho no se pudo cambiar ({type(e).__name__})")
        res.pop("mensaje", None)
    finally:
        if registro is not None:
            try:
                fila = {"momento": momento.isoformat(timespec="seconds"), "accion": "despacho", "cola": None,
                        "resultado": "hecho" if res["ok"] else "fallida" if actuo else "rechazada",
                        "detalle": res.get("mensaje") or res.get("error"), "desde": None, "orden": orden,
                        "autorizadas": res["despacho"]["autorizadas"] if res["ok"] else None}
                os.write(registro, (json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8"))
            except OSError:
                pass
            finally:
                os.close(registro)
    return res


def _fase_texto(desde: str | None) -> str:
    """«43a:rev2» → «la etapa 43a, fase rev2»: así pasa entero por la lista blanca de textos de la página."""
    et, fase = _etapa_fase(desde or "")
    return f"la etapa {et}, fase {fase}" if et and fase else "una fase sin datos"


def _n1(x: float) -> str:
    """Un decimal, con coma y con el signo menos tipográfico: como los números de la matriz de la página."""
    return num_es(round(x, 1)).replace("-", "−")


def carga_proyectada(cola: str, matriz: dict, uso_de) -> tuple[list[dict], bool]:
    """(carga por cuenta, si ya estaba comprometida) de reanudar ahora la cola `cola`, sobre lo que entrega
    matriz_cuota(). Si está en `colas_fuera`, sus fases se suman como suma matriz_cuota() las de una cola
    activa: `prob × pct` por ventana, lo que parte después de la renovación de 5 h va a `proxima_5h` y lo que
    parte después de la semanal no suma a la semana (una prueba ata las dos sumas). Si ya cuenta como carga
    comprometida (pausada por cuota con una reanudación programada), es su celda de `reglas`. La Holgura es
    `tope − uso − carga comprometida de las demás − carga proyectada`."""
    reglas = {r["cuenta"]: r for r in matriz["reglas"]}
    fila = next((x for x in matriz["colas_fuera"] if x["cola"] == cola), None)
    celdas: dict[str, dict] = {}
    if fila is None:
        celdas = {cid: dict(r["celdas"][cola]) for cid, r in reglas.items() if cola in r["celdas"]}
    else:
        por_cuenta: dict[str, list] = {}
        for ini, f in _fases_validas(fila["fases_restantes"])[0]:
            if not f.get("donde"):
                por_cuenta.setdefault(f["cuenta"], []).append((ini, f))
        for cid, fases in por_cuenta.items():
            u = uso_de(cid)
            ren = {"pct_5h": u.get("renueva_5h"), "pct_sem": u.get("renueva_sem")}
            c = dict.fromkeys(CLAVES_CELDA, 0.0)
            for ini, f in fases:
                for k in ("pct_5h", "pct_sem"):
                    if ren[k] is None or ini < ren[k]:
                        c[k] += f["prob"] * f[k]
                        c[k + "_max"] += f[k]
                        c[k + "_min"] += f[k] if f["prob"] >= 1 else 0
                    elif k == "pct_5h":
                        c["proxima_5h"] += f["prob"] * f[k]
            celdas[cid] = {k: round(x, 1) for k, x in c.items()} | {
                "debil": bool(fila["debil"]) or None in ren.values() or any(bool(f.get("debil")) for _, f in fases)}
    out = []
    for cid in (c for c in MOTORES if c in celdas):
        celda, u, ventanas = celdas[cid], uso_de(cid), []
        if u["sem"] is not None:
            comprometida = {w["ventana"]: w["pronostico"] for w in reglas.get(cid, {}).get("ventanas", [])}
            for w in sorted(ventanas_cuota(cid, {"pct_sem": 0.0, "pct_5h": 0.0}, u,
                                            _hora(matriz.get("momento"))), key=lambda w: w["ventana"] != "5h"):
                suya = celda["pct_5h" if w["ventana"] == "5h" else "pct_sem"]
                otras = round(comprometida.get(w["ventana"], 0.0) - (suya if fila is None else 0.0), 1)
                ventanas.append({"ventana": w["ventana"], "actual": w["actual"], "comprometida": otras, "proyectada": suya,
                                 "tope": w["tope"], "holgura": round(w["tope"] - w["actual"] - otras - suya, 1)})
        out.append({"cuenta": cid, "nombre": nombre(cid)} | celda | {"ventanas": ventanas})
    return out, fila is None


def _texto_carga(c: dict) -> str:
    """Una línea por cuenta para la confirmación de Reanudar, con los términos de la página."""
    partes = []
    if c["pct_5h"] > 0:
        partes.append(f"+{_n1(c['pct_5h'])} % 5 h (entre {_n1(c['pct_5h_min'])} y {_n1(c['pct_5h_max'])})")
    partes.append(f"+{_n1(c['pct_sem'])} % sem (entre {_n1(c['pct_sem_min'])} y {_n1(c['pct_sem_max'])})")
    if c["proxima_5h"] > 0:
        partes.append(f"↻ {_n1(c['proxima_5h'])} % en la próxima ventana de 5 h")
    holgura = " · ".join(f"{'5 h' if w['ventana'] == '5h' else 'sem'} {_n1(w['holgura'])} %" for w in c["ventanas"])
    partes.append(f"holgura con esta carga: {holgura}" if holgura else "holgura: sin datos de cuota")
    return f"{c['nombre']}: " + " · ".join(partes) + (" [débil]" if c["debil"] else "")


def _reanudar(res: dict, cola: str, ruta: Path, desde: str, tmux: tuple, lanzar, vivos_dir: Path) -> None:
    argv = argv_relanzar(cola, ruta, desde)
    res.update(desde=desde, linea=" ".join(argv))
    rc = (lanzar or _lanzar)(argv)
    if rc != 0:
        res["error"] = f"tmux no pudo crear la sesión de {cola} (código {rc}): no se lanzó nada"
        return
    # Leer después de actuar: la sesión tiene que existir. El vivo cambia cuando la cola publica «partiendo».
    res["sesion"] = _sesion(tmux, cola)
    res["estado"] = (_vivo_de(cola, vivos_dir) or {}).get("estado")
    if res["sesion"]:
        res.update(ok=True, mensaje=f"{cola} se lanzó desde {_fase_texto(desde)}. Su sesión está viva; el estado cambia en unos segundos.")
    else:
        res["error"] = f"{cola} se lanzó, pero su sesión ya no está: mira la bitácora"


def _pausar(res: dict, cola: str, tmux: tuple, vivos_dir: Path, momento: datetime) -> None:
    try:
        fd = os.open(_marca_pausa(cola, vivos_dir), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o666)
    except FileExistsError:
        res["ya_pedida"] = True
    else:
        res["ya_pedida"] = False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"momento": momento.isoformat(timespec="seconds"), "cola": cola}, ensure_ascii=False) + "\n")
    # Leer después de actuar: si la cola terminó justo antes de ver la marca, no queda nada pausado.
    res.update(sesion=_sesion(tmux, cola), estado=(_vivo_de(cola, vivos_dir) or {}).get("estado"))
    if res["sesion"] is False:
        soltar_pausa(cola, vivos_dir)
        res.update(pausa_pedida=False, error=f"{cola} terminó antes de ver la pausa: no quedó nada pausado")
        return
    res["pausa_pedida"] = pausa_pedida(cola, vivos_dir)
    if not res["pausa_pedida"]:
        res["error"] = f"la marca de pausa de {cola} no quedó escrita"
    elif res["ya_pedida"]:
        res.update(ok=True, mensaje=f"{cola} ya tenía una pausa pedida: se detiene cuando termine la fase en curso.")
    else:
        res.update(ok=True, mensaje=f"Pausa pedida para {cola}: termina la fase en curso y no empieza la siguiente.")


def _detener(res: dict, cola: str, v: dict | None, etapas: list[dict], viva: bool, tmux: tuple, vivos_dir: Path,
             estado_md: Path, momento: datetime, dormir) -> None:
    if viva:
        try:
            subprocess.run([*tmux, "kill-session", "-t", f"={cola}"], capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass        # lo que cuenta es lo que se lee después
        for _ in range(CORTE_VUELTAS):
            if _sesion(tmux, cola) is False:
                break
            dormir(CORTE_ESPERA_S)
    res["sesion"] = _sesion(tmux, cola)
    if res["sesion"] is not False:
        res.update(estado=(_vivo_de(cola, vivos_dir) or {}).get("estado"),
                   error=f"no se pudo cortar la sesión de {cola}: sigue viva o tmux no contesta. No se cambió su estado")
        return
    soltar_pausa(cola, vivos_dir)       # una pausa pedida a una cola que ya no corre no es para la próxima corrida
    # El vivo se vuelve a leer con la sesión ya cortada: entre la primera lectura y el corte la cola pudo
    # cambiar de fase, o terminar. La fase cortada es la que dice ahora.
    v = _vivo_de(cola, vivos_dir) or v
    corte, desde = v["estado"] if v else None, _desde_del_vivo(v, etapas)
    if v and corte in ESTADOS_ACTIVOS:
        # Lo que la cola no alcanzó a hacer al irse: quedar en un estado final, sin los campos de una espera, y
        # sin que el tiempo en que nadie trabajó (la espera de cuota, o desde que se quedó sin sesión) cuente
        # como trabajo en la barra al reanudar (heredar_vivo() mide hasta `escrito`).
        en_fase = desde if isinstance(v.get("fase"), str) else None
        motivo = MOTIVO_DETENIDA_USUARIO + (f" (cortada en {en_fase})" if en_fase else f" (estaba en «{corte}»)")
        nuevo = {k: x for k, x in v.items() if k not in CAMPOS_ESPERA and k != "fases_restantes"}
        nuevo.update(estado="detenida", motivo_pausa=motivo, fin=momento.isoformat(timespec="seconds"),
                     escrito=momento.isoformat(timespec="seconds"))
        nuevo.pop("reanuda_desde", None)
        if desde:
            nuevo["reanuda_desde"] = desde
        parado = _hora(v.get("espera_desde")) if corte == "esperando_cuota" else None if viva else _hora(v.get("escrito"))
        inicio = _hora(v.get("inicio_trabajo"))
        if parado and inicio:
            muerto = max(0.0, (momento - parado).total_seconds())
            nuevo["inicio_trabajo"] = (inicio + timedelta(seconds=muerto)).isoformat(timespec="seconds")
            previo = v.get("tiempo_muerto_min")
            nuevo["tiempo_muerto_min"] = round((previo if _num(previo) else 0) + muerto / 60, 1)
        ruta = vivos_dir / f"{cola}.json"
        for _ in range(3):
            _escribir_vivo(ruta, nuevo)
            dormir(CORTE_ESPERA_S)      # si la cola alcanzó a escribir su vivo mientras moría, se vuelve a dejar
            if (_vivo_de(cola, vivos_dir) or {}).get("escrito") == nuevo["escrito"]:
                break
        fd = _abrir_para_agregar(estado_md, 0o666)
        try:
            os.write(fd, (f"- {momento:%d-%m %H:%M} · ⏹️ {cola}: {motivo}. "
                          + (f"Se reanuda desde {desde}" if desde else "No queda una fase desde donde reanudar") + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    res["estado"] = (_vivo_de(cola, vivos_dir) or {}).get("estado")
    res["desde"] = desde if res["estado"] == "detenida" and corte in ESTADOS_ACTIVOS else None
    if corte in ESTADOS_ACTIVOS and res["estado"] != "detenida":
        res["error"] = f"la sesión de {cola} se cortó, pero su vivo no quedó en «detenida»: vuelve a intentar Detener"
        return
    hecho = f"Se cortó la sesión de {cola}" if viva else f"{cola} ya no tenía sesión"
    if corte not in ESTADOS_ACTIVOS:
        res.update(ok=True, mensaje=f"{hecho}. Su estado no cambió: no estaba corriendo fases.")
    elif res["desde"]:
        res.update(ok=True, mensaje=f"{hecho}. Quedó detenida; se reanuda desde {_fase_texto(desde)}.")
    else:
        res.update(ok=True, mensaje=f"{hecho}. Quedó detenida y no deja una fase desde donde reanudar.")


def accion_cola(accion: str, cola: str, simular: bool = False, *, vivos_dir: Path | None = None,
                manifiestos_dir: Path | None = None, tmux: tuple | None = None, lanzar=None, estado_md: Path | None = None,
                momento: datetime | None = None, dormir=None, uso_de=None, timers=None, autorizar: bool = False) -> dict:
    """`--accion {reanudar|pausar|detener} <cola>`: el único punto de entrada de los botones de 🧵 Encargos.
    Devuelve {'ok', 'accion', 'cola', 'simulado', 'mensaje' o 'error', …} y nunca lanza: la página siempre
    recibe un JSON. Corre como el usuario de la sesión, sin sudo.

    Todo lo que toca el nodo entra por parámetro: la carpeta de los vivos (ahí van también la marca y el
    registro), la de los manifiestos, el comando tmux, el lanzador (recibe la línea `relanzar` como argv), la
    bitácora, la hora, el `dormir` de la espera tras cortar y, para la simulación, `uso_de` y `timers` de
    matriz_cuota(). `cola` es un dato hostil: se valida entera antes de tocar nada y nunca arma un comando de
    shell ni una ruta fuera de las dos carpetas.

    Sin `simular`, la acción corre entera bajo el `flock` de vivo/acciones.jsonl y termina agregándole una
    línea, también si se rechazó. Con `simular` no abre ni crea ningún archivo.

    Encargo 50a: con el despacho en pausa, `reanudar` trae `despacho` ({estado, desde, motivo, autorizada}) y,
    si la cola no está en `autorizadas`, se niega salvo con `autorizar` (la confirmación extra de la página):
    ahí la agrega a vivo/despacho.json, bajo el mismo `flock`, justo antes de lanzarla."""
    momento, tmux = momento or ahora(), tuple(tmux or TMUX)
    vivos_dir, carpeta = Path(vivos_dir or E / "vivo"), Path(manifiestos_dir or E)
    res: dict = {"ok": False, "accion": accion, "cola": None, "simulado": bool(simular)}
    registro, actuo = None, False
    try:
        if accion not in ACCIONES:
            res["error"] = "acción desconocida"
            return res
        if not simular:
            registro = _abrir_para_agregar(vivos_dir / "acciones.jsonl", 0o600)
            os.fchmod(registro, 0o600)
        if not (isinstance(cola, str) and RE_COLA.fullmatch(cola)):
            res["error"] = "nombre de cola inválido: «cola», dos dígitos y, si sigue algo, letras minúsculas o dígitos"
            return res
        res["cola"] = cola
        hallado = manifiestos_con_ruta(carpeta).get(cola)
        if hallado is None:
            res["error"] = f"no hay un manifiesto válido con el nombre {cola}"
            return res
        ruta, man = hallado
        v, viva = _vivo_de(cola, vivos_dir), _sesion(tmux, cola)
        se_puede, motivo, desde = _puede(accion, v, man["etapa"], viva, momento)
        res.update(estado=v["estado"] if v else None, sesion=viva)
        if not se_puede:
            res["error"] = f"no se puede {accion} {cola}: {motivo}"
            return res
        despacho, retiene = None, False
        if accion == "reanudar":
            despacho = leer_despacho(vivos_dir)[0]
            if despacho["estado"] == "pausa":
                retiene = cola not in despacho["autorizadas"]
                res["despacho"] = {"estado": "pausa", "desde": despacho["desde"], "motivo": despacho["motivo"], "autorizada": not retiene}
        if simular:
            res.update(ok=True, desde=desde)
            if accion == "reanudar":
                matriz = matriz_cuota(vivos_dir=vivos_dir, uso_de=uso_de, momento=momento, timers=timers,
                                      viva=lambda nom: _sesion(tmux, nom) is True, manifiestos_dir=carpeta)
                carga, ya = carga_proyectada(cola, matriz, uso_de or uso)
                res.update(linea=" ".join(argv_relanzar(cola, ruta, desde)), carga=carga, ya_comprometida=ya,
                           texto=[_texto_carga(c) for c in carga] or ["sin fases que gasten cuota en este equipo"],
                           mensaje=f"Reanudar {cola} la lanzaría desde {_fase_texto(desde)}. No se lanzó nada.")
                if ya:
                    res["texto"].append("ya cuenta como carga comprometida: tiene una reanudación programada")
            elif accion == "pausar":
                res["mensaje"] = f"Pausar {cola} dejaría la marca de pausa. No se escribió nada."
            else:
                res["mensaje"] = f"Detener {cola} cortaría su sesión" + (f" en {_fase_texto(desde)}" if desde else "") + ". No se cortó nada."
        elif accion == "reanudar":
            if retiene and not autorizar:
                res["error"] = (f"no se puede reanudar {cola}: el despacho está en pausa desde {_hora_despacho(despacho, momento)} y la cola "
                                "no está autorizada. El botón Reanudar pide la confirmación que la autoriza")
                return res
            actuo = True
            if retiene:
                _escribir_despacho(vivos_dir, despacho | {"autorizadas": despacho["autorizadas"] + [cola]})
                res["despacho"]["autorizada"] = True
            _reanudar(res, cola, ruta, desde, tmux, lanzar, vivos_dir)
            if retiene and res["ok"]:
                res["mensaje"] += " Quedó autorizada mientras dure la pausa del despacho."
            elif retiene:
                res["error"] += ". Quedó autorizada mientras dure la pausa del despacho"
        elif accion == "pausar":
            actuo = True
            _pausar(res, cola, tmux, vivos_dir, momento)
        else:
            actuo = True
            _detener(res, cola, v, man["etapa"], viva, tmux, vivos_dir, estado_md or ESTADO, momento, dormir or time.sleep)
    except Exception as e:      # noqa: BLE001 — pase lo que pase, la página recibe un JSON y el registro, su línea
        res.update(ok=False, error=f"la acción no se pudo completar ({type(e).__name__})")
        res.pop("mensaje", None)
    finally:
        if registro is not None:
            try:
                fila = {"momento": momento.isoformat(timespec="seconds"), "accion": accion, "cola": res["cola"],
                        "resultado": "hecho" if res["ok"] else "fallida" if actuo else "rechazada",
                        "detalle": res.get("mensaje") or res.get("error"), "desde": res.get("desde")}
                if (res.get("despacho") or {}).get("autorizada") and actuo and autorizar:
                    fila["autorizada_en_despacho"] = True
                os.write(registro, (json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8"))
            except OSError:
                pass
            finally:
                os.close(registro)
    return res


# ---------------------------------------------------------------- principal

MANIFIESTO: dict = {}


def esperar_sesion(s: str, viva=None, dormir=None) -> None:
    """Espera a que termine la sesión tmux `s` (el `esperar` del manifiesto). El vivo queda en `esperando`
    con sus `fases_restantes` antes de la primera espera y se refresca en cada vuelta (encargo 46a): el fin
    esperado de la cola de la que depende cambia mientras corre."""
    viva, dormir = viva or sesion_viva, dormir or time.sleep
    if not viva(s):
        return
    log(f"⏳ Se espera a que termine la sesión «{s}»")
    vivo(estado="esperando", esperando=s)
    while viva(s):
        dormir(60)
        vivo()
    log(f"«{s}» terminó")


def vivo_anterior(nom: str) -> dict | None:
    """vivo/<cola>.json de la corrida anterior, si existe y es un objeto. Lo lee solo un `--desde`."""
    try:
        d = json.loads((E / "vivo" / f"{nom}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def heredar_vivo(previo: dict, desde: str) -> dict:
    """Lo que un relanzamiento conserva de la corrida anterior (encargo 24): `lanzada`, `fases_hechas`
    (las nuevas se agregan) y los `relanzamientos` previos más este. `inicio_trabajo` se corre para que
    la barra no cuente como trabajo el hueco entre lanzamientos: parte de lo que ya llevaba hecho (hasta
    donde escribió, o hasta que empezó a esperar la cuota) y vuelve a contar desde ahora. Una barra
    que baja a 0 % al relanzar es una barra que miente."""
    out = {"relanzamientos": list(previo.get("relanzamientos") or []) + [
        {"momento": ahora().isoformat(timespec="seconds"), "desde": desde}]}
    if previo.get("lanzada"):
        out["lanzada"] = previo["lanzada"]
    if isinstance(previo.get("fases_hechas"), list):
        out["fases_hechas"] = list(previo["fases_hechas"])
    if previo.get("tiempo_muerto_min"):
        out["tiempo_muerto_min"] = previo["tiempo_muerto_min"]
    # Encargo 51: el tope de consultas es por cola, y una aceptación del usuario vale al relanzar.
    if isinstance(previo.get("consultas_n"), int) and not isinstance(previo["consultas_n"], bool):
        out["consultas_n"] = previo["consultas_n"]
    if isinstance(previo.get("aceptadas_usuario"), list):
        out["aceptadas_usuario"] = [x for x in previo["aceptadas_usuario"] if isinstance(x, dict)]
    try:
        corte = previo["espera_desde"] if previo.get("estado") == "esperando_cuota" and previo.get("espera_desde") else previo["escrito"]
        hecho = max(0.0, (datetime.fromisoformat(corte) - datetime.fromisoformat(previo["inicio_trabajo"])).total_seconds())
        out["inicio_trabajo"] = (ahora() - timedelta(seconds=hecho)).isoformat(timespec="seconds")
        out["tiempo_muerto_min"] = round(out.get("tiempo_muerto_min", 0) + max(
            0.0, (ahora() - datetime.fromisoformat(corte)).total_seconds()) / 60, 1)
    except (KeyError, ValueError, TypeError):
        pass       # sin inicio_trabajo en el archivo anterior: la barra parte cuando empiece a trabajar
    return out


def main() -> int:
    global MANIFIESTO
    ap = argparse.ArgumentParser()
    ap.add_argument("manifiesto", nargs="?")
    ap.add_argument("--desde", default="")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--con-cambios", action="store_true")
    ap.add_argument("--panel", action="store_true")
    ap.add_argument("--accion", choices=ACCIONES)
    ap.add_argument("--despacho", choices=DESPACHO_ORDENES)
    ap.add_argument("--motivo")
    ap.add_argument("--por")
    ap.add_argument("--autorizar", nargs="*", metavar="COLA")
    ap.add_argument("--consultas", action="store_true")
    a = ap.parse_args()
    global SIMULANDO, COLA_EN_MARCHA
    SIMULANDO = a.simular or a.panel or bool(a.accion) or bool(a.despacho) or a.consultas
    if a.consultas:
        # Encargo 51 (el timer transitorio que arma la cola): recoge respuestas y aplica defectos. Usa sus propios escritores.
        if a.accion or a.despacho or a.panel or a.simular or a.desde or a.con_cambios or a.manifiesto is not None \
                or a.motivo is not None or a.por is not None or a.autorizar is not None:
            ap.error("--consultas va solo")
        print(json.dumps(atender_consultas(), ensure_ascii=False))
        return 0
    COLA_EN_MARCHA = None       # hasta que una cola parta de verdad, este proceso no suelta ninguna marca de pausa
    if a.despacho:
        # El estado del despacho (50a). No lleva manifiesto ni cola: las autorizadas van en --autorizar.
        if a.accion or a.panel or a.simular or a.desde or a.con_cambios or a.manifiesto is not None:
            ap.error("--despacho lleva solo --motivo, --por y --autorizar")
        r = cambiar_despacho(a.despacho, a.motivo, a.autorizar or [], a.por)
        salida = json.dumps(r, ensure_ascii=False)
        print(salida)
        if not r["ok"]:
            print(salida, file=sys.stderr)      # cockpit.spawn entrega stderr cuando el código no es 0
        return 0 if r["ok"] else 1
    if a.motivo is not None or a.por is not None:
        ap.error("--motivo y --por solo van con --despacho")
    if a.autorizar is not None and not (a.accion == "reanudar" and a.autorizar == [a.manifiesto] and not a.simular):
        ap.error("--autorizar va con --despacho pausar, o con --accion reanudar <cola> --autorizar <la misma cola>")
    if a.accion:
        # Los botones de 🧵 Encargos (46c). El argumento es el NOMBRE de una cola, no una ruta. Con SIMULANDO
        # puesto, nada de lo de una cola en marcha (bitácora, avisos, vivo()) escribe por error: la acción
        # usa sus propios escritores.
        if a.panel or a.desde or a.con_cambios or a.manifiesto is None:
            ap.error("--accion lleva el nombre de una cola y, si acaso, --simular")
        r = accion_cola(a.accion, a.manifiesto, a.simular, autorizar=a.autorizar is not None)
        salida = json.dumps(r, ensure_ascii=False)
        print(salida)
        if not r["ok"]:
            print(salida, file=sys.stderr)      # cockpit.spawn entrega stderr cuando el código no es 0
        return 0 if r["ok"] else 1
    if a.panel:
        print(json.dumps(panel(), ensure_ascii=False))
        return 0
    if not a.manifiesto:
        ap.error("falta el manifiesto")
    if a.con_cambios and not a.simular:
        ap.error("--con-cambios solo va con --simular")
    ruta = Path(a.manifiesto).resolve()
    MANIFIESTO = tomllib.loads(ruta.read_text(encoding="utf-8"))
    MANIFIESTO.setdefault("pruebas", ["botv3/test_botv3.py", "pi/test_cuentas_uso.py", "pi/test_uso.py"])
    nom = MANIFIESTO["nombre"]
    etapas = MANIFIESTO["etapa"]
    cambios: list[str] = []
    if a.con_cambios:
        # La propuesta sin aplicar pasa por la validación de aplicar-propuesta: si no calza, sale
        # con el mismo mensaje con que después se rechazaría (por stderr, código 1).
        global CFG_SIMULADA
        cfg = _cfg_modelos()
        CFG_SIMULADA, cambios, avisos_cfg = _ap_mod().cambios_encargos(
            cfg, json.loads(sys.stdin.read() or "{}"), _ap_mod().catalogo_modelos(cfg))
        cambios += avisos_cfg
    try:
        repartir(etapas)
        validar_remotas(etapas)
        validar_esfuerzos(etapas)
    except ValueError as e:
        if a.simular:       # simular nunca avisa por Telegram
            print(f"⛔ {e}", file=sys.stderr)
            return 2
        raise SystemExit(str(e))
    if MANIFIESTO.get("solo_simular") and not a.simular:
        print(f"⛔ {ruta.name} es un manifiesto de ejemplo (`solo_simular`): solo corre con --simular",
              file=sys.stderr)
        return 2
    relanzar = lambda desde: " ".join(argv_relanzar(nom, ruta, desde))

    if a.simular:
        medidas: dict[str, dict] = {}   # una medición por cuenta, no una por rol (cada una tarda 2-4 s)
        for et in etapas:
            print(f"{et['id']} · naturaleza: {et.get('naturaleza') or '(sin naturaleza: default del CLI)'}"
                  + (f" · {' y '.join(et['reparto_sugerido'])} por [reparto.{et.get('naturaleza')}]"
                     if et.get("reparto_sugerido") else ""))
            if remota(et):
                print(f"  en PC-2503 por el buzón · arnés {et['arnes']} · prompt {et['prompt']} · sin arreglos "
                      "automáticos; la revisión corre en la Pi sobre el RESULTADO")
            roles = ([('plan', 'autor', et['autor']), ('revplan', 'rev', et['revisor'])] if et.get('plan') else []) + [("autor", "autor", et["autor"]), ("rev", "rev", et["revisor"]), ("fix", "fix", et["autor"])]
            if cierre_aplica(et):       # encargo 87: la rev2+ se pronostica como cierre
                roles.append(("cierre", "cierre", et["revisor"]))
            for etiqueta, rol_modelo, cid in roles:
                mod = modelo_de(dict(et, esfuerzo_rev="medium") if etiqueta == "revplan" else et, rol_modelo)
                if remota(et) and rol_modelo != "rev":
                    if rol_modelo == "autor":
                        f = pronostico(cid, rol_modelo, mod["modelo"], "pc2503")
                        quien = f"{mod['modelo'] or '-'} {mod['esfuerzo']}".strip()
                        print(f"  {rol_modelo:5} {nombre(cid) + ' en PC-2503':27} {quien:24} "
                              f"[{mod['nivel']}]  {f['min']:>5} min  su cuota no se mide desde la Pi"
                              f"{'  [' + etiqueta_pronostico(f) + ']' if etiqueta_pronostico(f) else ''}")
                    continue
                if cid not in medidas:
                    medidas[cid] = medir(cid)
                rol = "plan" if etiqueta == "plan" else "revplan" if etiqueta == "revplan" else rol_modelo
                f, u = pronostico(cid, rol, mod["modelo"], "", mod["esfuerzo"]), medidas[cid]
                ts, t5 = topes(cid, u)
                q = quema(cid, u)
                quien = f"{mod['modelo'] or '-'} {mod['esfuerzo']}".strip()
                print(f"  {etiqueta if etiqueta in ('plan', 'revplan', 'cierre') else rol_modelo:5} {nombre(cid):15} {quien:24} [{mod['nivel']}]  {f['min']:>5} min  "
                      f"+{f['pct_5h']} % 5 h (p75 {f['pct_5h_p75']} %; ahora {u['5h']}, tope {t5})  +{f['pct_sem']} % sem "
                      f"(ahora {u['sem']}, tope {ts})  {u['fuente']}"
                      f"{'  [quemando hasta ' + q['hasta'].astimezone().strftime('%H:%M') + ']' if q['activa'] else ''}"
                      f"{'  [' + etiqueta_pronostico(f) + ']' if etiqueta_pronostico(f) else ''}")
            if cierre_aplica(et):
                print("  cierre: rev2+ si el arreglo pasa E1–E4 (si no, rev completa); el máximo de la ETA supone ambas")
        for m, r in modelos_con_candado(etapas).items():
            print(f"🔒 {m} pide autorización por Telegram al lanzar ({', '.join(r)})")
        r = restante(etapas, etapas[0]["id"], "plan" if etapas[0].get("plan") else "autor", 0)
        print(f"⏱️ Duración de la cola (sin contar esperas): ~{r['esperado']} min, entre {r['min']} y "
              f"{r['max']} (rechazo por revisión: {prob_rechazo():.0%})")
        for c in cambios:
            print(f"✏️ sin aplicar · {c}")
        return 0

    L.mkdir(parents=True, exist_ok=True)
    global PARTIDA
    PARTIDA = tuple((a.desde.split(":") + ["autor"])[:2]) if a.desde else (etapas[0]["id"], "plan" if etapas[0].get("plan") else "autor")
    previo = vivo_anterior(nom) if a.desde else None
    with ESTADO.open("a", encoding="utf-8") as fh:     # solo se agrega: la bitácora nunca se reescribe
        if a.desde:
            fh.write(f"\n## Reanudación desde {a.desde} · cola {nom} · {ahora():%d-%m %H:%M}\n\n"
                     f"Motivo de la cola: {MANIFIESTO.get('motivo', '')}\n")
            if previo and previo.get("motivo_pausa"):
                fh.write(f"Se había pausado por: {previo['motivo_pausa']}\n")
            fh.write("\n")
        else:
            fh.write(f"\n## Cola {nom} (cola-run): {MANIFIESTO.get('motivo', '')}\n\n")
    # Una marca de pausa que quedó de antes no es para esta corrida (46c): se quita antes de publicar «partiendo»,
    # que es desde cuando `--accion pausar` acepta dejar otra.
    soltar_pausa(nom)
    COLA_EN_MARCHA = nom
    # Relanzar con --desde no borra lo andado: VIVO parte del archivo anterior de la misma cola.
    VIVO.clear()
    if previo:
        VIVO.update(heredar_vivo(previo, a.desde))
    # Encargo 51: un reinicio se lleva el timer transitorio de las consultas; la próxima cola que parte lo rearma.
    try:
        rearmar_vigilante(nom)
    except Exception as e:      # noqa: BLE001 — nunca detiene a la cola que parte
        log(f"⚠️ no se pudo revisar el timer de las consultas ({type(e).__name__})")
    # Encargo 50a: con el despacho en pausa, una cola que no está autorizada no parte. Va antes de «partiendo»,
    # de pedir autorizaciones, de esperar a otra cola y de la línea base: no corre ni gasta nada.
    despacho, aviso_despacho = leer_despacho()
    if aviso_despacho:
        log(f"⚠️ {aviso_despacho}")
    if despacho["estado"] == "pausa" and nom not in despacho["autorizadas"]:
        desde = ":".join(PARTIDA)
        motivo = (f"retenida por el despacho, en pausa desde {_hora_despacho(despacho)}"
                  + (f" ({despacho['motivo']})" if despacho["motivo"] else ""))
        vivo(nombre=nom, motivo=MANIFIESTO.get("motivo", ""), estado="retenida_por_despacho", etapas=[e["id"] for e in etapas],
             motivo_pausa=motivo, reanuda_desde=desde, fin=ahora().isoformat(timespec="seconds"))
        log(f"⏸️ {nom} no partió: {motivo}. No corrió ninguna fase. Se reanuda desde {desde}")
        texto = (f"⏸️ La cola {nom} no partió: {motivo}. No corrió ninguna fase ni gastó cuota. Se reanuda desde {desde} "
                 "con el botón Reanudar de 🧵 Encargos, que durante la pausa pide autorizarla.")
        avisar_texto(texto, viejo=(texto, f"cat {ESTADO}"))
        return CODIGO_RETENIDA
    vivo(nombre=nom, motivo=MANIFIESTO.get("motivo", ""), estado="partiendo",
         lanzada=VIVO.get("lanzada") or ahora().isoformat(timespec="seconds"), etapas=[e["id"] for e in etapas])
    # Antes de esperar a nadie: así la pregunta llega cuando se lanza, no horas después.
    usos = modelos_con_candado(etapas)
    AUTORIZADOS.clear()
    if usos:
        vivo(estado="esperando autorización", candado=list(usos))
    if usos and not pedir_autorizacion(nom, usos):
        vivo(estado="sin autorización", fin=ahora().isoformat(timespec="seconds"))
        avisar_texto(f"⛔ La cola {nom} no corrió: no se autorizó {', '.join(usos)}. Para lanzarla sin esos "
                     "modelos, cambia la naturaleza o fija otro modelo en el manifiesto.",
                     viejo=(f"⛔ Cola {nom}: no se autorizó {', '.join(usos)}. No corrió nada. Para lanzarla sin esos "
                            "modelos, cambia la naturaleza o fija otro modelo en el manifiesto.", f"cat {ESTADO}"))
        return 4
    AUTORIZADOS.update(m.lower() for m in usos)
    for s in MANIFIESTO.get("esperar", []):
        esperar_sesion(s)

    vivo(estado="línea base de pruebas", esperando=None)
    base, resumen = pruebas()
    log(f"Línea base de pruebas: {len(base)} fallas previas" + (" (no son de esta cola)" if base else ""))
    (L / f"{nom}-base.json").write_text(json.dumps(sorted(base), ensure_ascii=False, indent=1), encoding="utf-8")
    antes = tomar_linea_base_catalogo(bool(a.desde), nom)
    git_foto(f"antes de {nom}")

    ini_et, ini_fase = PARTIDA
    empezar = False
    try:
        for et in etapas:
            if not empezar and et["id"] != ini_et:
                continue
            fase = ini_fase if not empezar else ("plan" if et.get("plan") else "autor")
            reanuda = bool(a.desde) and not empezar
            empezar = True
            if not etapa(et, fase, reanuda):
                vivo(estado="detenida", fin=ahora().isoformat(timespec="seconds"), progreso_pct=100)
                log("⛔ La cola se detuvo; no se pide ningún despliegue")
                motivo = VIVO.get("motivo_pausa")
                texto = (f"⛔ La cola {nom} se detuvo antes de completar la etapa {et['id']}: {motivo}. No se desplegó nada."
                         if motivo else f"⛔ La cola {nom} se detuvo: la etapa {et['id']} quedó NO DESPLEGABLE. No se desplegó nada.")
                viejo = (f"⛔ Cola {nom}: {et['id']} se detuvo: {motivo}. No se desplegó nada. Esta línea muestra el estado."
                         if motivo else f"⛔ Cola {nom}: {et['id']} quedó NO DESPLEGABLE. No se desplegó nada. Esta línea muestra el estado.")
                avisar_texto(texto, viejo=(viejo, f"cat {ESTADO}"))
                return 1
    except Consulta as c:
        # Encargo 51: estacionada mientras el usuario contesta; la cadena sigue. La respuesta (o el defecto al vencer
        # el plazo) la aplica `cola-run.py --consultas`, que la reanuda por el mismo camino del botón Reanudar.
        vivo(estado="en_consulta", motivo_pausa=c.motivo, reanuda_desde=c.desde, fin=ahora().isoformat(timespec="seconds"))
        log(f"❓ {nom} quedó estacionada: {c.motivo}. Se reanuda desde {c.desde}")
        return CODIGO_EN_CONSULTA
    except Pausa as p:
        if isinstance(p, PausaUsuario) or pausa_pedida(nom):
            # El usuario pidió pausar (46c). Si justo se cruzó otra pausa, gana la del usuario: una cola
            # «pausada» por cuota la puede relanzar sola un timer, y pidió que no siguiera.
            motivo = MOTIVO_PAUSA_USUARIO + ("" if isinstance(p, PausaUsuario) else f" (además: {p.motivo})")
            vivo(estado="pausada_por_usuario", motivo_pausa=motivo, reanuda_desde=p.desde,
                 fin=ahora().isoformat(timespec="seconds"))
            soltar_pausa(nom)
            log(f"⏸️ PAUSA pedida desde 🧵 Encargos: {motivo}. Se reanuda desde {p.desde}")
            avisar_texto(f"⏸️ La cola {nom} quedó en pausa, como pediste en 🧵 Encargos. Nada quedó desplegado. Se reanuda "
                         f"desde {p.desde} con el botón Reanudar.", relanzar(p.desde),
                         viejo=(f"⏸️ Cola {nom} en pausa, como pediste en 🧵 Encargos. Nada quedó desplegado. Esta línea la "
                                f"reanuda desde {p.desde}.", relanzar(p.desde)))
            return 3
        vivo(estado="pausada", motivo_pausa=p.motivo, reanuda_desde=p.desde,
             fin=ahora().isoformat(timespec="seconds"))
        log(f"⏸️ PAUSA: {p.motivo}. Se reanuda desde {p.desde}")
        avisar_texto(f"⏸️ La cola {nom} está en pausa: {p.motivo}. Nada quedó desplegado. Se reanuda desde {p.desde} "
                     "con la línea que muestra 🔔 Avisos, en 🧵 Encargos.", relanzar(p.desde),
                     viejo=(f"⏸️ Cola {nom} en pausa: {p.motivo}. Nada quedó desplegado. Esta línea la reanuda desde {p.desde}.", relanzar(p.desde)))
        return 3

    vivo(estado="pruebas finales", fase=None)
    final, resumen = pruebas()
    nuevas = sorted(final - base)
    with ESTADO.open("a", encoding="utf-8") as fh:
        fh.write(resumen + "\n")
    if nuevas:
        vivo(estado="detenida", fin=ahora().isoformat(timespec="seconds"), progreso_pct=100)
        log("⛔ Las pruebas tienen fallas nuevas: " + "; ".join(nuevas[:5]))
        avisar_texto(f"⛔ La cola {nom} quedó revisada, pero dejó {len(nuevas)} fallas nuevas en las pruebas. No se desplegó nada.",
                     viejo=(f"⛔ Cola {nom}: revisada, pero dejó {len(nuevas)} fallas nuevas en las pruebas. No se desplegó nada.", f"cat {ESTADO}"))
        return 1
    log(f"Pruebas: sin fallas nuevas ({len(final)} fallas que ya estaban)" if final else "Pruebas: todo en verde")
    vivo(estado="desplegando")
    desplegar(antes, foto())
    vivo(estado="terminada", fin=ahora().isoformat(timespec="seconds"), progreso_pct=100)
    return 0


def principal() -> int:
    """Toda cola termina con un aviso por Telegram, también si el script se cae (03-10)."""
    try:
        return main()
    except SystemExit as e:
        if isinstance(e.code, str) and not SIMULANDO:  # un manifiesto inválido (p. ej. autor = revisor) también avisa
            avisar_texto(f"⛔ La cola {MANIFIESTO.get('nombre', '?')} no partió: {e.code}",
                         viejo=(f"⛔ Cola {MANIFIESTO.get('nombre', '?')} no partió: {e.code}", f"cat {ESTADO}"))
        raise
    except BaseException as e:
        if SIMULANDO and isinstance(e, Exception):   # simular = solo imprimir: ni vivo/, ni bitácora, ni Telegram
            print(f"⛔ {type(e).__name__}: {e}", file=sys.stderr)
            return 2
        nom = MANIFIESTO.get("nombre", "?")
        try:
            vivo(estado="caída", error=f"{type(e).__name__}: {e}", fin=ahora().isoformat(timespec="seconds"))
            log(f"💥 La cola se cayó: {type(e).__name__}: {e}")
            avisar_texto(f"💥 La cola {nom} se cayó por un error inesperado ({type(e).__name__}). Lo que estaba "
                         "a medias no se desplegó. El final del registro está en la bitácora de 🧵 Encargos.",
                         viejo=(f"💥 Cola {nom} se cayó por un error inesperado ({type(e).__name__}). Lo que estaba "
                                "a medias no se desplegó. Esta línea muestra el final del registro.",
                                f"tail -n 40 ~/encargos-logs/{nom}.out"))
        finally:
            raise
    finally:
        # Como sea que termine (terminada, detenida, pausada, caída): la marca de pausa de una cola que ya no
        # corre no puede pausar a la próxima. Solo la suelta la cola que partió de verdad (no --accion ni --simular).
        if COLA_EN_MARCHA:
            soltar_pausa(COLA_EN_MARCHA)


if __name__ == "__main__":
    sys.exit(principal())
