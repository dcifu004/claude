# Encargo 54 — Revisión 1 (Claude (Cami), 13-10-2026)

Solo revisión: no se tocó código. La etapa 54 no trae `plan = true` (es la que crea la fase), así que
no hay `54-PLAN.md` contra el cual juzgar: se juzga contra `54-fase-plan.md`. No hay revisiones
anteriores.

Las reproducciones corrieron en temporales (`mktemp -d`), con `BOTV3_USO_CUENTAS`, `BOTV3_USO_RUTAS`,
`BOTV3_STATE_DIR`, `VERSIONES_REPO` y `VERSIONES_ARBOL` apuntados ahí, `env -u TMUX`, y con todo
`subprocess` de `cola-run.py` bloqueado: ningún motor, aviso, `tmux` ni `nodo-desplegar` salió del
arnés. Las suites corrieron dentro de la caja de solo lectura; después `avisos.jsonl` (91610 bytes) y
`avisos-salida.jsonl` (34786) quedaron iguales y la caja no dejó pedidos. Nunca más de dos corridas a
la vez.

**Resumen:** sin `plan`, la cola se comporta igual que antes (lo comprobé con los 47 manifiestos
reales). Con `plan = true`, la fase no funciona: el control del diff falla siempre con el historial
git real y detiene la etapa en su primera fase, y aun con eso arreglado, cualquier pausa de la cola
rehace el plan o mata la etapa al reanudar. Las cinco pruebas nuevas pasan en verde con los dos
defectos, porque reemplazan justo las piezas donde están.

## Pruebas (salida real, dentro de la caja, con `NODO_PRUEBAS=1`)

```text
$ python3 encargos/test_fase_plan.py
Ran 5 tests in 0.050s
OK
$ python3 encargos/test_diff_propio.py
Ran 9 tests in 0.785s
OK
$ python3 encargos/test_matriz_cuota.py
Ran 28 tests in 4.409s
OK
$ python3 encargos/test_acciones_cola.py
Ran 48 tests in 7.561s
OK
$ python3 pi/test_cockpit_paginas.py
FAIL: test_la_skill_ya_no_ofrece_el_experimento_para_menor (__main__.EsfuerzoQueElModeloNoAceptaTests...)
Ran 159 tests in 28.804s
FAILED (failures=1)
```

La falla de `pi/test_cockpit_paginas.py` **es previa**: está en `~/encargos-logs/cola54-base.json` y
compara la skill del proyecto con su copia instalada, que esta etapa no tocó. No cuenta.

Fuera de la lista de la cola corrí también las demás suites que cargan `cola-run.py`:
`test_balance.py` (22), `test_capacidad_por_vencer.py` (10), `test_despacho.py` (36),
`test_despachador.py` (21), `pi/test_avisos.py` (93) y `pi/test_cuentas_uso.py` (73), todas `OK`.
Dos tienen fallas **ajenas y previas**, que anoto para que no se atribuyan después:

- `encargos/test_pronostico.py`: 5 errores, `pronostico() takes from 2 to 4 positional arguments but
  5 were given`. La firma de 4 argumentos ya estaba en la foto anterior al autor (`e6f4148`).
- `encargos/test_versiones.py`: 1 falla, `test_el_arbol_real_no_tiene_git_dentro`. Hay una carpeta
  `.git` vacía en `10-Proyectos/11-Pi5` desde el 11-10 17:03. No la borré.

## Hallazgos, de más grave a menos grave

Los hallazgos 2 a 7 se reprodujeron sobre una **copia** de `cola-run.py` con una sola línea cambiada
(el `.decode()` que falta en el hallazgo 1), porque sin eso ninguna etapa pasa de la fase `plan`.

### 1. [Grave] Con el historial git real, toda fase `plan` termina en «violación de plan»
`encargos/cola-run.py:2424-2436`. El control hace
`_vers().abrir().git("diff", …).stdout.split("\0")`. `Repo.git()` de `versiones.py:155-158` corre
sin `text=True`: `stdout` es `bytes`, y `bytes.split("\0")` lanza
`TypeError: a bytes-like object is required, not 'str'`. El `except Exception` de la línea 2428 lo
convierte en `{"<diff propio no verificable>"}` y la etapa se detiene. Pasa siempre, también cuando
el autor escribió solo `<id>-PLAN.md`. (`git_diff_etapa`, líneas 1386-1387, sí decodifica.)

**Reproducción** (`cola-run.py` sin tocar, `versiones.py` real en un repositorio temporal, la fase
`plan` escribe únicamente `encargos/54-PLAN.md`):
```text
etapa() -> False
fases corridas: ['plan']
motivo_pausa: violación de plan: solo podía tocar encargos/54-PLAN.md; diff propio: <diff propio no verificable>
```
La prueba `test_c3_…` y las otras cuatro pasan porque `test_fase_plan.py:46-51` reemplaza el
repositorio por una clase cuyo `git()` devuelve un `str`. Es una forma inventada: el repositorio real
nunca devuelve texto. `git_foto` también está reemplazado (línea 40) por la cadena `"foto"`.
**Arreglo:** decodificar como en la línea 1387, y que la prueba de C3 use un repositorio de verdad
(como `test_diff_propio.py`, que crea uno en un temporal).

### 2. [Grave] Reanudar una etapa con plan la rehace desde cero o la mata
Una pausa es rutina en este nodo (esta misma cola esperó cuota entre las 06:36 y las 08:52). La
pausa deja `reanuda_desde` y la cola se relanza con ese `--desde`. Con `plan = true` hay tres casos,
los tres reproducidos por `main()` con un manifiesto en disco:

**a) `--desde 54:autor` vuelve a correr `plan` y `revplan`.** `cola-run.py:2350-2351` cambia
`desde_fase` de `autor` a `plan` sin mirar si es una reanudación.
```text
main() -> rc 3; fases corridas: ['plan', 'revplan', 'autor']
vivo: estado='pausada' reanuda_desde='54:autor' motivo_pausa='Codex se quedó sin cuota a mitad de autor (3.0 min)'
main(--desde 54:autor) -> rc 0; fases corridas: ['plan', 'revplan', 'autor', 'rev1']
¿el autor reanudado recibe «Una corrida anterior de este encargo se cortó»? False
¿qué plan recibe? el NUEVO
```
Se gasta de nuevo el plan y su revisión, el plan aprobado se reemplaza por otro escrito con el
código ya a medias, y el autor pierde el aviso de reanudación (línea 2413: `reanuda and fase ==
desde_fase`, y `desde_fase` ya vale `plan`), así que puede rehacer lo hecho. Si el plan nuevo se
rechaza dos veces, la etapa muere con código a medio escribir.

**b) `--desde 54:plan2` no corre nada y detiene la etapa.** `plan_rechazado` parte en `False`
(línea 2357), así que las líneas 2359-2360 saltan `plan2` y `revplan2`, y el freno de 2366-2374
encuentra el veredicto anterior.
```text
main() -> rc 3; fases corridas: ['plan', 'revplan']
vivo: estado='pausada_por_usuario' reanuda_desde='54:plan2'
main(--desde 54:plan2) -> rc 1; fases corridas: []
vivo: estado='detenida' motivo_pausa='no hay plan aprobado; la etapa no puede escribir código'
aviso: ⛔ La cola cola91 se detuvo: la etapa 54 quedó NO DESPLEGABLE. No se desplegó nada.
```

**c) `--desde 54:revplan2`** (la segunda revisión del plan se cortó por cuota): mismo resultado que
b), `fases corridas: []` y `detenida`.

**Arreglo:** el salto a `plan` solo cuando la etapa parte de cero (no con `reanuda`), y al entrar por
`plan2` o `revplan2` dar por rechazada la primera vuelta. Con una prueba que pase por `main()` con
cada `--desde` que una pausa puede dejar.

### 3. [Media] Un cambio de cualquier otro en el árbol cuenta como violación y detiene la etapa
`cola-run.py:2426-2431`. El control compara las fotos de antes y después de la fase, y todo lo que
cambió en `11-Pi5` en ese rato se le atribuye al autor del plan: la bitácora compartida
(`COLA-ESTADO.md`), `historial.jsonl`, un encargo o un manifiesto que alguien escribe mientras tanto.

**Reproducción** (el plan escribe solo `54-PLAN.md`; durante la fase se agrega una línea a
`encargos/COLA-ESTADO.md`, que es lo que hace `log()` de otra cola):
```text
main() -> rc 1; fases corridas: ['plan']
vivo: estado='detenida' motivo_pausa='violación de plan: solo podía tocar encargos/54-PLAN.md; diff propio: encargos/54-PLAN.md, encargos/COLA-ESTADO.md'
```
Medido en el historial real: en **19 de 58** tramos antes→después de fases de autor o arreglo de las
últimas colas hay archivos que el agente de la fase no escribió (por ejemplo `cola55 · 55 · autor`
trae `encargos/cola-50.toml`; `cola49 · 49 · autor` trae `COLA-ESTADO.md` e `historial.jsonl`). Una
fase `plan` dura menos, así que le tocará menos veces, pero cuando pase la etapa queda `detenida`
(no pausada: no se reanuda) por algo que el autor no hizo. La cola 54 se lanzó «cuando no haya colas
vivas»; con dos colas a la vez esto es lo esperable.
**Arreglo posible:** dejar fuera del control lo que la cola sabe que no es del agente (la bitácora,
el historial), y ante una violación pausar con el detalle en vez de detener.

### 4. [Media] El mínimo de la ETA de una etapa con plan deja fuera al autor y a la revisión
`cola-run.py:2249-2250`. `restante()` pone `aprobada_min = True` al pasar por `revplan`, así que el
camino mínimo termina ahí. Lo que publica `vivo` en `eta.min`, la línea «termina ~… (entre X y Y)»
de la bitácora y `--simular` salen con un mínimo imposible.

**Reproducción** (historial de `46-fixtures`):
```text
minutos por fase: {'plan': 1.7, 'revplan': 3.2, 'autor': 5.8, 'rev': 10.8}
restante(): {'esperado': 24.6, 'min': 5.9, 'max': 44.3}
camino más corto real (plan + revplan + autor + rev1 + 1): 22.5
```
Con el historial real y la fixture nueva, `--simular` dice «~36.1 min, entre 8.4 y 64.3»: el camino
más corto es 32,9 min. Además, en `fases_restantes` (línea 598) y `restante` (2251), partiendo desde
`plan2` (ya hubo un rechazo), `autor` sale con probabilidad `1 − p²` (0,5511 con p = 0,67) cuando
corresponde `1 − p` (0,33).

### 5. [Media] Las pruebas no ejercitan el camino real y dejan pasar defectos sembrados
`encargos/test_fase_plan.py:33-51` reemplaza `modelo_de`, `chequear_cuota`, `git_foto`, `anotar`,
`vivo`, `git_base_guardar` y el repositorio. Ninguna prueba pasa por `main()`, por `--desde` ni por
`--simular`. Sembré siete defectos en una copia aislada (sin red, `tmux` aparte) y corrí las cuatro
suites de `encargos/` de la cola; solo uno se detectó:

| Defecto sembrado | ¿Alguna suite lo nota? |
|---|---|
| El arreglo (`fixN`) ya no recibe el plan (C5 del encargo: «el autor y los `fixN`») | No |
| Sin el freno «no hay plan aprobado» antes de `autor`/`fix` | No |
| `--simular` no muestra `plan` ni `revplan` (C2) | No |
| El control acepta que falte `<id>-PLAN.md` | No |
| Un veredicto de plan no se anota en `historial.jsonl` | No |
| `revplan` sale con el esfuerzo de `rev` en `--simular` | No |
| La violación de plan solo avisa y la etapa sigue | Sí (`test_c3`) |

En la copia, `test_acciones_cola.py` da 1 error propio de la copia (`setUpClass (Pagina)`), también
sin defecto: lo descuento. La salida completa de cada siembra quedó revisada antes de borrar el
temporal.

Además: C1 solo comprueba las dos primeras fases de dos manifiestos, no «los mismos pronósticos y la
misma salida de `--simular`» (yo sí lo comprobé, ver más abajo); C4 no comprueba `detenida` en
`vivo`, que lo escribe `main()`; C6 usa filas con cuatro campos, no las que escribe `anotar()`.

### 6. [Media] El plan aprobado no queda fijado: puede cambiar después y nadie lo nota
`cola-run.py:2176-2178` y `2199-2200` leen `<id>-PLAN.md` del disco cada vez, y el control del
hallazgo 1 solo mira la fase `plan`.

- El autor reescribe el plan durante su fase y el arreglo recibe el plan cambiado:
  ```text
  fases corridas: ['plan', 'revplan', 'autor', 'rev1', 'fix1', 'rev2']
  el arreglo recibe: el plan CAMBIADO por el autor
  ```
  El revisor lo puede ver en el diff («Fase propia autor» trae `54-PLAN.md`), pero la plantilla le
  dice que juzgue contra «ese plan aprobado» y lo manda a leer el archivo tal como está.
- La fase `plan` toca código, se corta por cuota (la `Pausa` de la línea 2423 sale antes del
  control) y al reanudar escribe solo el plan: el control pasa y `pi/base.py` queda cambiado sin que
  la cola lo marque.
  ```text
  main(--desde 54:plan) -> rc 0; fases corridas: ['plan', 'revplan', 'autor', 'rev1']
  pi/base.py quedó: tocado por la fase plan
  ```
**Arreglo posible:** guardar el hash del plan al aprobarlo y compararlo antes de `autor`, `fixN` y
`revN`; y correr el control también cuando la fase se cortó.

### 7. [Media] El aviso de una etapa detenida por el plan dice «quedó NO DESPLEGABLE»
`cola-run.py:3525-3529`. Plan rechazado dos veces, violación de plan o «no hay plan aprobado»
terminan todos en el mismo texto de Telegram: «la etapa 54 quedó NO DESPLEGABLE. No se desplegó
nada». El motivo real solo queda en `motivo_pausa` de `vivo` y en la bitácora (se ve en las salidas
de los hallazgos 2 y 3). C4 pedía `detenida` en `vivo` y el motivo, y eso está; el aviso es el que
confunde, porque no hubo código que revisar.

### 8. [Baja] Sin `<id>-PLAN.md`, la cola se cae en vez de detenerse
`cola-run.py:2366-2374` solo mira el veredicto. Con el veredicto aprobado y el plan borrado,
`prompt_de` (2178 o 2200) lanza:
```text
main(--desde 54:fix1) -> FileNotFoundError [Errno 2] No such file or directory: '…/encargos/54-PLAN.md'
```

### 9. [Baja] Un plan aprobado se dibuja como rechazado, y `balance.py` lo cuenta como revisión
No lo ejecuté (en la Pi no hay node): lo leí. `pi/cockpit-comun/barra.js:187-191` toma por revisión
toda fase que empieza con `rev` y marca «mal» cualquier veredicto distinto de `DESPLEGABLE`;
`revplan` con `PLAN APROBADO` cae ahí. El estilo propio queda para la ampliación, pero esto no es
estilo: es un ❌ donde hubo un ✅. En `encargos/balance.py:175`, `revisiones` cuenta las fases que
empiezan con `rev`: con dos vueltas de plan y dos revisiones de código da `revisiones = 4`, y la
leyenda de la línea 261 sigue diciendo «ret = fix y rev2+».

### 10. [Baja] Otros
- **Buscador en la fase `plan`:** `cola-run.py:1619` abre el buzón de búsquedas para toda fase que no
  empiece con `rev`. En una etapa `investigacion` con plan, `plan` y `plan2` lo reciben abierto
  aunque su instrucción dice «no uses buscador web» (comprobado: `plan -> buzón ABIERTO`,
  `revplan -> sin buzón`). El muro, el tope y el registro siguen valiendo y la búsqueda queda a
  nombre del mismo encargo: no es grave.
- **`plan` que no es booleano:** `plan = "false"` o `plan = "no"` activan la fase (solo se mira
  `et.get("plan")`). Nada valida el tipo al lanzar.
- **Historial de otro modelo:** con 5 filas propias de `plan` de otro modelo, el pronóstico sigue en
  «débil, factor 0,3»; con 3 del mismo modelo sí pasa a la mediana (`min 5.0`, no débil). La etiqueta
  «factor 0,3» usa la misma palabra que el factor de modelo del encargo 24, y `por_factor = 0.3`
  queda así en `historial.jsonl`.
- `cola-run.py:2395`: `revplan` también borra `<id>r-RESULTADO.md`, que no es suyo.
- En `--simular`, `revplan` no cabe en la columna de 5 caracteres y desalinea su fila.

## Lo que revisé y está bien

- **C1, sin `plan` nada cambia.** Corrí el `cola-run.py` de la foto anterior al autor (`e6f4148`) y
  el de ahora con las mismas entradas (medición fija, mismo reloj) sobre los **47 manifiestos
  reales** (`encargos/cola-*.toml` y los de `46-fixtures/`): la salida de `--simular` por `main()`,
  `restante()`, `fases_restantes()` y `uso_de_cuentas()` son idénticas en los 47.
- **C5 por el camino real** (sobre la copia): el autor recibe el plan entero, `revplan` corre con el
  modelo de `rev` y esfuerzo `medium` (`claude-opus-5-5 medium`), y el arreglo también recibe el
  plan. Con el `modelos.toml` real, `medium` sirve con el modelo de revisión de todas las
  naturalezas y las tres cuentas.
- **C6 con filas reales** (escritas por `anotar()` en una etapa con dos vueltas de plan y un
  arreglo): `min_ret` = 12 de 24 min, que es `plan2 + revplan2 + fix1 + rev2`, y `balance.py` corre
  entero sobre ese historial (`rc 0`).
- **C4 en el camino sin pausas:** dos rechazos dejan `plan, revplan, plan2, revplan2`, `detenida` en
  `vivo` y el motivo «plan rechazado dos veces…».
- **Invariantes:** `vivo` sigue escribiéndose con temporal y `os.replace`; `historial.jsonl` solo por
  `anotar()`; `<cola>-git.json` por `git_base_guardar()` sin cambios. La pausa por cuota, el
  despacho, los botones de la 46c y `git_diff_etapa` no se tocaron. El diff que recibe el revisor
  trae «Fase propia plan» con el plan.
- **Seguridad:** no existe `encargos/54-busquedas.jsonl` ni `encargos/manual-busquedas.jsonl`; en el
  registro del autor no hay llamadas al buscador, a la red ni a una cola. En la ventana del autor
  (06:12–06:36) solo cambiaron en el vault los seis archivos del diff, más `historial.jsonl` y
  cachés de Python. El diff no agrega tokens ni rutas de los vaults a ninguna salida.
- **JS:** la etapa no cambió ningún archivo JS; no hubo nada que contar con el tokenizador.
- **Nombres:** en el diff y en `54-RESULTADO.md` las cuentas van como «Claude (Cami)» y «Codex».

## Arnés (para el arreglo y la próxima revisión)

El temporal se borró al terminar. Lo esencial para repetirlo:

```python
#!/usr/bin/env python3
"""Arnés de la revisión 1 del 54. Todo en un temporal: árbol, historial git (versiones.py real), vivo, logs.
No corre motores ni manda avisos: `correr` es falso y cualquier subprocess de cola-run.py se rechaza."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REAL = Path("/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5")
_N = 0


class SinProcesos:
    """Lo que cola-run.py ve como `subprocess`: nada sale del arnés (ni tmux, ni nodo-desplegar, ni claude)."""
    DEVNULL = -3
    CompletedProcess = __import__("subprocess").CompletedProcess

    def run(self, argv, *a, **k):
        raise OSError(f"arnés: subprocess bloqueado: {argv[:3]}")


class Mundo:
    def __init__(self, codigo: Path = REAL / "encargos/cola-run.py", plan=True, vueltas=1, naturaleza="seguridad"):
        global _N
        _N += 1
        self.raiz = Path(tempfile.mkdtemp(prefix="r54-"))
        self.arbol = self.raiz / "vault/10-Proyectos/11-Pi5"
        self.E, self.L = self.arbol / "encargos", self.raiz / "logs"
        self.E.mkdir(parents=True)
        self.L.mkdir()
        (self.arbol / "pi").mkdir()
        (self.arbol / "pi/base.py").write_text("base\n", encoding="utf-8")
        shutil.copy(REAL / "pi/aplicar-propuesta.py", self.arbol / "pi")
        (self.E / "54-fase-plan.md").write_text("# Encargo de prueba\n", encoding="utf-8")
        shutil.copy(REAL / "encargos/revision-plantilla-v2.md", self.E)
        shutil.copy(REAL / "encargos/46-fixtures/historial.jsonl", self.E / "historial.jsonl")
        shutil.copy(REAL / "encargos/46-fixtures/modelos.toml", self.E / "modelos.toml")
        os.environ.update(VERSIONES_REPO=str(self.raiz / "git"), VERSIONES_ARBOL=str(self.arbol),
                          BOTV3_USO_CUENTAS=str(self.raiz / "uso-cuentas.jsonl"),
                          BOTV3_USO_RUTAS=str(self.raiz / "uso-rutas.jsonl"), BOTV3_STATE_DIR=str(self.raiz))
        spec = importlib.util.spec_from_file_location(f"cola_run_r54_{_N}", codigo)
        cr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cr)
        self.cr = cr
        cr.VAULT, cr.D, cr.E, cr.L = self.raiz / "vault", self.arbol, self.E, self.L
        cr.ESTADO, cr.HISTORIAL, cr.MODELOS = self.E / "COLA-ESTADO.md", self.E / "historial.jsonl", self.E / "modelos.toml"
        cr.PLANTILLA_REV = self.E / "revision-plantilla-v2.md"
        cr.USO = self.raiz / "no-hay-uso.json"
        cr.subprocess = SinProcesos()
        cr.SIMULANDO = False
        self.reloj = datetime(2026, 10, 13, 12, tzinfo=timezone(timedelta(hours=-3)))
        cr.ahora = lambda: self.reloj
        self.avisos, self.bitacora, self.fases, self.prompts = [], [], [], {}
        cr.avisar = lambda *a, **k: self.avisos.append(a)
        cr.avisar_texto = lambda *a, **k: self.avisos.append(a)
        cr.registrar_aviso = lambda *a, **k: None
        cr.log = lambda t: self.bitacora.append(t)
        cr.sesion_viva = lambda n: False
        cr.pedir_autorizacion = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("arnés: pidió autorización"))
        # medir(): la forma real de una medición fresca (ver `medir()` y una fila de historial.jsonl)
        cr.medir = lambda cid: {"5h": 10.0, "sem": 5.0, "renueva_5h": None, "renueva_sem": None,
                                "momento": self.reloj.isoformat(timespec="seconds"), "fuente": "fresco"}
        self.et = {"id": "54", "encargo": "54-fase-plan.md", "autor": "codex", "revisor": "claude_cami",
                   "vueltas": vueltas, "naturaleza": naturaleza}
        if plan:
            self.et["plan"] = True
        cr.MANIFIESTO = {"nombre": "cola91", "motivo": "arnés", "pruebas": [], "etapa": [self.et], "paciencia_h": 1}
        cr.VIVO.clear()
        cr.GIT_BASE.clear()
        self.repo = cr._vers().abrir()
        self.repo.init()
        self.repo.foto("antes de cola91")
        self.guion = {}         # fase -> función(mundo) que hace lo que haría el agente
        cr.correr = self._correr

    def _correr(self, cid, prompt, nombre_log, mod=None, herramientas=""):
        fase = nombre_log.partition("-")[2]
        self.fases.append(fase)
        self.prompts[fase] = (prompt, dict(mod or {}))
        self.reloj += timedelta(minutes=3)
        r = {"rc": 0, "min": 3.0, "tokens": {"total": 1000}, "sin_cuota": False, "modelo_real": (mod or {}).get("modelo")}
        hecho = self.guion.get(fase, lambda m: None)(self)
        if isinstance(hecho, dict):
            r.update(hecho)
        return r

    def escribir(self, rel, texto):
        p = self.arbol / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")

    def correr_etapa(self, desde="autor", reanuda=False):
        try:
            return self.cr.etapa(self.et, desde, reanuda)
        except self.cr.Pausa as p:
            return f"Pausa({p.motivo!r}, desde={p.desde!r})"

    def resumen(self, titulo, r):
        print(f"--- {titulo}")
        print("  etapa() ->", r)
        print("  fases corridas:", self.fases)
        print("  motivo_pausa:", self.cr.VIVO.get("motivo_pausa"))
        for b in self.bitacora:
            print("  bitácora:", b)

    def cerrar(self):
        shutil.rmtree(self.raiz, ignore_errors=True)


PLAN = "# Plan 54\n\nEnfoque: X.\nArchivos: pi/x.py.\nPremisas: `ls` -> ok.\nC1: dato real.\n"


def guion_feliz(m: Mundo):
    m.guion = {
        "plan": lambda m: m.escribir("encargos/54-PLAN.md", PLAN),
        "revplan": lambda m: m.escribir("encargos/54rplan-RESULTADO.md", "Motivos: está completo.\n\nPLAN APROBADO\n"),
        "autor": lambda m: (m.escribir("pi/x.py", "x = 1\n"), m.escribir("encargos/54-RESULTADO.md", "hecho\n"))[0],
        "rev1": lambda m: m.escribir("encargos/54r-RESULTADO.md", "todo bien\n\nVEREDICTO: DESPLEGABLE\n"),
    }
```

Cada escenario corre `main()` de verdad con un manifiesto en disco, y vuelve a llamarlo con el
`--desde` que dejó la pausa:

```python
COPIA = Path("/tmp/r54/copia/cola-run.py")


def por_main(m: Mundo, *args):
    """main() real, con el manifiesto leído de un cola-91.toml: como lo lanza tmux."""
    cr = m.cr
    ruta = m.E / "cola-91.toml"
    ruta.write_text('nombre = "cola91"\nmotivo = "arnés"\nesperar = []\ndespliegue = "nada"\npruebas = []\n\n'
                    '[[etapa]]\nid = "54"\nencargo = "54-fase-plan.md"\nautor = "codex"\nrevisor = "claude_cami"\n'
                    'vueltas = 1\nnaturaleza = "seguridad"\nplan = true\n', encoding="utf-8")
    cr.pruebas = lambda: (set(), "")
    cr.foto = lambda: {}
    cr.desplegar = lambda *a: None
    cr.sys.argv = ["cola-run.py", str(ruta), *args]
    m.fases.clear()
    m.bitacora.clear()
    rc = cr.main()
    m.et = cr.MANIFIESTO["etapa"][0]
    v = json.loads((m.E / "vivo/cola91.json").read_text(encoding="utf-8"))
    print(f"  main({' '.join(args)}) -> rc {rc}; fases corridas: {m.fases}")
    print(f"  vivo: estado={v.get('estado')!r} reanuda_desde={v.get('reanuda_desde')!r} motivo_pausa={v.get('motivo_pausa')!r}")
    for a in m.avisos[-1:]:
        print("  aviso:", a[0][:150])
    return rc, v


def a_desde_autor():
    print("\n=== A. Plan aprobado, el autor se queda sin cuota, y se reanuda con el `--desde 54:autor` que deja la pausa")
    m = Mundo(COPIA)
    guion_feliz(m)
    m.guion["autor"] = lambda m: (m.escribir("pi/x.py", "a medias\n"), {"sin_cuota": True})[1]
    por_main(m)
    guion_feliz(m)
    plan2 = PLAN.replace("Enfoque: X", "Enfoque: OTRO, escrito con el código ya a medias")
    m.guion["plan"] = lambda m: m.escribir("encargos/54-PLAN.md", plan2)
    por_main(m, "--desde", "54:autor")
    p = m.prompts.get("autor", ("",))[0]
    print("  ¿el autor reanudado recibe «Una corrida anterior de este encargo se cortó»?", "corrida anterior" in p)
    print("  ¿qué plan recibe?", "el NUEVO" if "OTRO" in p else "el aprobado antes")
    m.cerrar()


def b_desde_plan2():
    print("\n=== B. Primer plan rechazado, pausa del usuario antes de plan2, y se reanuda con `--desde 54:plan2`")
    m = Mundo(COPIA)
    guion_feliz(m)
    def rechaza(m):
        m.escribir("encargos/54rplan-RESULTADO.md", "Falta C2.\n\nPLAN RECHAZADO\n")
        (m.E / "vivo/.cola91.pausar").touch() if False else None
    m.guion["revplan"] = rechaza
    real = m.cr.pausa_pedida
    m.cr.pausa_pedida = lambda nom, d=None: m.fases[-1:] == ["revplan"]
    por_main(m)
    m.cr.pausa_pedida = lambda nom, d=None: False
    m.guion["revplan2"] = lambda m: m.escribir("encargos/54rplan-RESULTADO.md", "Ahora sí.\n\nPLAN APROBADO\n")
    m.guion["plan2"] = lambda m: m.escribir("encargos/54-PLAN.md", PLAN + "C2: agregado.\n")
    por_main(m, "--desde", "54:plan2")
    m.cerrar()
```

## Veredicto

**No desplegable.** Sin `plan` no se rompe nada: eso está comprobado y es lo que protege a las colas
de hoy. Pero el encargo es la fase `plan`, y con el historial git real no pasa de su primera fase
(hallazgo 1); con eso corregido, una pausa por cuota o por el botón Pausar rehace el plan con el
código a medias o deja la etapa detenida sin correr nada (hallazgo 2). `cola-run.py` corre desde el
vault sin despliegue, así que la primera cola que traiga `plan = true` se encontraría con esto.

Pasa a desplegable con 1 y 2 corregidos y con pruebas sobre la forma real: un repositorio de
`versiones.py` en un temporal para C3, y `main()` con cada `--desde` (`autor`, `plan2`, `revplan2`).
Conviene cerrar en la misma vuelta 3, 4 y 7, que son chicos y tocan las mismas líneas. Los hallazgos
5 y 6 y los bajos pueden ir ahí o después.

VEREDICTO: NO DESPLEGABLE
