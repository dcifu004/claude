# Encargo 54 — Revisión 2 (Claude (Cami), 13-10-2026)

Solo revisión: no se tocó código. La etapa 54 no trae `plan = true` (es la que crea la fase), así que
no hay `54-PLAN.md`: se juzga contra `54-fase-plan.md` y contra los hallazgos de la revisión 1
(`54r1-RESULTADO.md`).

Las reproducciones corrieron en un `mktemp -d`, con `BOTV3_USO_CUENTAS`, `BOTV3_USO_RUTAS`,
`BOTV3_STATE_DIR`, `VERSIONES_REPO` y `VERSIONES_ARBOL` apuntados ahí, `env -u TMUX`, y con todo
`subprocess` de `cola-run.py` bloqueado. Esta vez **cada `main()` corre en un módulo recién cargado**,
como un relanzamiento real con `tmux`: `GIT_BASE` y `VIVO` parten vacíos y se recuperan del disco.
Las suites y la siembra corrieron dentro de la caja de solo lectura; después `avisos.jsonl` (91610
bytes) y `avisos-salida.jsonl` (34786) quedaron iguales y la caja no dejó pedidos. Nunca más de dos
corridas a la vez.

**Resumen:** los dos graves de la revisión 1 están cerrados y los comprobé por `main()` con el
`versiones.py` real: una etapa con plan corre entera y se reanuda bien desde `autor`, `plan`,
`revplan`, `plan2`, `revplan2`, `fix1` y `rev2`. Sin `plan` nada cambió (44 manifiestos y cinco
corridas completas, código de antes contra el de ahora). Los arreglos dejaron tres defectos nuevos en
el camino con `plan = true`; dos detienen la cola con un motivo falso y el tercero es un hueco del
control. Ninguno toca lo que funciona hoy.

## Pruebas (salida real, dentro de la caja, con `NODO_PRUEBAS=1`)

```text
$ python3 encargos/test_fase_plan.py
Ran 8 tests in 0.248s
OK
$ python3 encargos/test_diff_propio.py
Ran 9 tests in 0.790s
OK
$ python3 encargos/test_matriz_cuota.py
Ran 28 tests in 4.023s
OK
$ python3 encargos/test_acciones_cola.py
Ran 48 tests in 7.614s
OK
$ python3 pi/test_cockpit_paginas.py
FAIL: test_la_skill_ya_no_ofrece_el_experimento_para_menor (__main__.EsfuerzoQueElModeloNoAceptaTests...)
Ran 159 tests in 28.296s
FAILED (failures=1)
```

La falla de `pi/test_cockpit_paginas.py` **es previa**: está en `~/encargos-logs/cola54-base.json` y
compara la skill del proyecto con su copia instalada, que esta etapa no tocó. No cuenta. La otra
línea de esa base (`test_fase_plan.py::no corrió`) es de cuando el archivo todavía no existía.
`test_fase_plan.py` también pasa sin `NODO_PRUEBAS` (8, `OK`).

Fuera de la lista de la cola, las demás suites que cargan `cola-run.py`: `test_balance.py` (22),
`test_capacidad_por_vencer.py` (10), `test_despacho.py` (36), `test_despachador.py` (21),
`pi/test_avisos.py` (93) y `pi/test_cuentas_uso.py` (73), todas `OK`. `test_pronostico.py` sigue con
sus errores **previos y ajenos** (`pronostico() takes from 2 to 4 positional arguments but 5 were
given`, ya anotados en la revisión 1).

## Hallazgos de la revisión 1: cómo quedaron

| # | Hallazgo | Estado | Cómo lo comprobé |
|---|---|---|---|
| 1 | Grave: `bytes.split("\0")`, toda fase `plan` era violación | **Cerrado** | `main()` con repositorio real: `plan, revplan, autor, rev1`, `rc 0` |
| 2 | Grave: reanudar rehacía el plan o mataba la etapa | **Cerrado** (a, b y c) | Proceso nuevo con `--desde 54:autor`, `54:plan2` y `54:revplan2`: ver abajo. Deja el hallazgo 2 de esta revisión |
| 3 | Media: un cambio de otro contaba como violación | **Cerrado** para lo que escribe la cola | `COLA-ESTADO.md`, `historial.jsonl` y un `cola-92.toml` cambiados durante `plan`: `rc 0` |
| 4 | Media: mínimo de la ETA sin autor ni revisión | **Cerrado** desde `plan` (22,5 min); deja el hallazgo 4 | `restante()` con `46-fixtures` |
| 5 | Media: las pruebas no ejercitaban el camino real | **A medias** | Siembra: hallazgo 5 |
| 6 | Media: el plan aprobado podía cambiar | **Cerrado** | El autor o el arreglo cambian el plan: la etapa se detiene antes de la revisión siguiente. El hash sobrevive al relanzamiento |
| 7 | Media: el aviso decía «quedó NO DESPLEGABLE» | **Cerrado** | El aviso trae el motivo; una etapa sin plan rechazada hasta agotar vueltas conserva el texto de antes |
| 8 | Baja: sin `<id>-PLAN.md` la cola se caía | **Cerrado** | Ahora se detiene con «no hay plan aprobado e inmutable» |
| 9 | Baja: plan aprobado dibujado como ❌; `balance.py` lo cuenta como revisión | Abierto | `barra.js:187-191` y `balance.py:175` no cambiaron |
| 10 | Baja: buzón abierto en `plan`, `plan = "false"` activa la fase, columna de `revplan` | Abierto | No cambiaron |

Salidas del hallazgo 2 de la revisión 1, ahora con un proceso nuevo en cada relanzamiento:

```text
main() -> rc 3; fases corridas: ['plan', 'revplan', 'autor']
vivo: estado='pausada' reanuda_desde='54:autor' motivo_pausa='Codex se quedó sin cuota a mitad de autor (3.0 min)'
main(--desde 54:autor) -> rc 0; fases corridas: ['autor', 'rev1']
¿«corrida anterior»? True | plan: el aprobado

main() -> rc 3; fases corridas: ['plan', 'revplan']
vivo: estado='pausada_por_usuario' reanuda_desde='54:plan2'
main(--desde 54:plan2) -> rc 0; fases corridas: ['plan2', 'revplan2', 'autor', 'rev1']

main() -> rc 3; fases corridas: ['plan', 'revplan', 'plan2', 'revplan2']
vivo: estado='pausada' reanuda_desde='54:revplan2' motivo_pausa='Claude (Cami) se quedó sin cuota a mitad de revplan2 (3.0 min)'
main(--desde 54:revplan2) -> rc 0; fases corridas: ['revplan2', 'autor', 'rev1']
```

## Hallazgos de esta revisión, de más grave a menos grave

Todos están en el camino con `plan = true`, que hoy no usa ninguna cola (solo la fixture).

### 1. [Media] Si la fase `plan` se corta por cuota antes de escribir el plan, la etapa queda «detenida» como violación
`encargos/cola-run.py:2439-2465`. El arreglo del hallazgo 6 puso el control del plan **antes** de
mirar `r["sin_cuota"]`. Si el agente se queda sin cuota antes de escribir `<id>-PLAN.md` (lo normal:
el plan se escribe al final), no hay archivos prohibidos pero tampoco hay plan, y la línea 2462 hace
`return False`. La cola termina `detenida`, sin `reanuda_desde`, con un motivo que no es cierto.

**Reproducción** (`main()`, la fase `plan` devuelve `sin_cuota` sin escribir nada):
```text
main() -> rc 1; fases corridas: ['plan']
vivo: estado='detenida' reanuda_desde=None motivo_pausa='violación de plan: solo podía tocar encargos/54-PLAN.md; diff propio: sin plan'
aviso: ⛔ La cola cola91 se detuvo antes de completar la etapa 54: violación de plan: solo podía tocar encargos/54-PLAN.md; diff propio: sin plan. No se desplegó nada.
última fila del historial: {'fase': 'plan', 'min': 3.0, 'sin_cuota': True}
_desde_del_vivo (lo que usaría Reanudar): None
```
Con el plan ya escrito al cortarse, sí pausa bien (`pausada`, `54:plan`, y al relanzar termina). El
botón Reanudar no sirve en el caso malo; relanzar a mano con `--desde 54:plan` sí (`rc 0`, comprobado).
En el historial real hay 2 cortes a mitad de fase en 229 filas, pero el pronóstico de `plan` es un
factor sin historial, así que aquí el tope puede fallar más. **Arreglo:** si `sin_cuota` y no hay
archivos prohibidos, lanzar la `Pausa` de cuota de siempre.

### 2. [Media] Reanudar una cola con plan que no alcanzó a empezar su primera fase la detiene
`cola-run.py:2361` junto con `:660` y `:3485`. El arreglo del hallazgo 2a deja de pasar de `autor` a
`plan` cuando hay `--desde`. Pero `autor` sigue siendo el punto de partida que el resto del archivo
da por defecto: `_punto_de_reanudacion()` cuando el vivo no tiene etapa, y `PARTIDA` cuando
`--desde` no trae fase. En los dos casos la etapa salta el plan, no encuentra uno aprobado y se
detiene.

**Reproducción:**
```text
(la sesión muere en «línea base de pruebas»; lo mismo vale para «esperando» a otra cola)
vivo: estado línea base de pruebas etapa None -> _desde_del_vivo: 54:autor
main(--desde 54:autor) -> rc 1; fases corridas: []
vivo: estado='detenida' motivo_pausa='no hay plan aprobado e inmutable; la etapa no puede escribir código ni revisarlo'

main(--desde 54) -> rc 1; fases corridas: []
vivo: estado='detenida' motivo_pausa='no hay plan aprobado e inmutable; la etapa no puede escribir código ni revisarlo'
```
Es lo que pasa con Detener y después Reanudar antes de la primera fase, o tras un reinicio de la Pi
con la cola esperando. Falla cerrado (no escribe código sin plan), pero el botón no la saca de ahí.
Sin `plan`, `--desde 54` se porta igual que antes. **Arreglo:** que el punto de partida por defecto
de una etapa con plan sea `plan`, o que `etapa()` parta de `plan` al reanudar desde `autor` cuando
todavía no hay ni veredicto ni hash guardado.

### 3. [Media] Con `arboles_extra`, lo que la fase `plan` escribe en la carpeta hermana no se detecta ni llega al revisor
`cola-run.py:2441-2452` y `:1303-1313`. El control solo compara las fotos del árbol principal. Además
la base de la carpeta hermana se fija al aprobar el plan (línea 2482, que entra por `fase is None`) o
al empezar `autor`: en los dos casos después de la fase `plan`.

**Reproducción** (manifiesto con `arboles_extra = ["13-Hermana"]`; `plan` cambia `13-Hermana/nota.md`,
`autor` crea `13-Hermana/otra.md`):
```text
main() -> rc 0; fases corridas: ['plan', 'revplan', 'autor', 'rev1']
diff: … '# Árbol extra 13-Hermana (carpeta hermana, rutas relativas a ella)', '## Cambios de la etapa: 32c71d0..818f928', '+++ b/otra.md'
```
`nota.md` quedó cambiada, la cola no la marcó y el diff del revisor no la trae. C3 pide que cualquier
archivo distinto del plan sea violación. Hoy 2 de los 39 manifiestos reales usan `arboles_extra`.

### 4. [Baja] Desde `plan2` o `revplan2`, la ETA publica un mínimo posterior al esperado
`cola-run.py:2252-2264`. Después de un primer rechazo, el esperado pesa `autor` con `1 − p`, pero el
mínimo supone que el plan se aprueba. Queda `esperado < min`:
```text
plan2     restante={'esperado': 15.1, 'min': 22.5, 'max': 39.4}
bitácora: 54: plan2 con Codex · … · termina ~12:21 (entre 12:28 y 12:45)
```
Además `segunda_vuelta_plan` (`:581` y `:2241`) se calcula con la fase actual y se aplica a todas las
etapas: con dos etapas con plan y la primera en `plan2`, el `autor` de la segunda sale con `0.33` en
vez de `0.5511`.

### 5. [Media] Los arreglos 3, 4 y 7 no tienen prueba, y la suite deja pasar ocho defectos sembrados
El encargo de arreglos pedía una prueba por hallazgo. Sembré defectos, uno por vez, en una copia
aislada y corrí las cuatro suites de `encargos/` de la cola. La copia sin defecto da todo `OK`. De
los 20 que sembré valen 18: descarté dos míos que no cambiaban nada en el camino que las pruebas
recorren (quitar el guardado explícito del hash, que igual se guarda con la foto siguiente, y una
variante de `fases_pendientes` que resultó equivalente).

| Defecto sembrado | ¿Lo nota alguna suite? |
|---|---|
| El control no decodifica los `bytes` de git (grave 1 de antes) | Sí |
| `--desde autor` vuelve a `plan` (2a) | Sí |
| `plan2`/`revplan2` no dan por rechazada la primera vuelta (2b, 2c) | Sí |
| Sin el freno antes de `autor`/`fix`/`rev` | Sí |
| `revplan` corre con el esfuerzo de `rev` | Sí |
| La violación solo avisa y la etapa sigue | Sí |
| El hash del plan no se compara | Sí |
| La revisión de código no exige el plan intacto | Sí |
| El autor no recibe el plan | Sí |
| `plan`/`revplan` sin el factor 0,3 | Sí |
| El arreglo (`fixN`) no recibe el plan (C5) | **No** |
| `--simular` no muestra `plan` ni `revplan` (C2) | **No** |
| El control acepta que falte `<id>-PLAN.md` | **No** |
| El veredicto del plan no se anota en `historial.jsonl` | **No** |
| Sin la lista de archivos compartidos (arreglo 3) | **No** |
| El mínimo de la ETA vuelve a cortar en `revplan` (arreglo 4) | **No** |
| Desde `plan2`, `autor` vuelve a `1 − p²` (arreglo 4) | **No** |
| El aviso vuelve a decir siempre «NO DESPLEGABLE» (arreglo 7) | **No** |

Mejoró mucho respecto de la revisión 1 (1 de 7). Lo que falta, además de esas ocho:
- `main()` solo se prueba con `--desde 54:autor`. `plan2` y `revplan2` van por `etapa()` con el
  repositorio falso (`test_fase_plan.py:213-230`). Ninguna prueba corta la fase `plan` por cuota, que
  es donde está el hallazgo 1.
- `test_c3` (`:125-144`) pone `E = D`, así que el plan queda en git como `54-PLAN.md` y no como
  `encargos/54-PLAN.md`: el propio plan cuenta como prohibido. Pasa, pero no es la forma real.
- C1 sigue mirando solo las dos primeras fases de dos manifiestos.

La salida completa de la siembra quedó en `~/encargos-logs/cola54-54r2-sembrados.txt`.

### 6. [Baja] `test_fase_plan.py` deja carpetas en `/tmp` con nombre fijo
`test_fase_plan.py:69`, `:76` y `:127`. Usa `self.e.parent`, que es `/tmp`: cada corrida deja
`/tmp/tmpXXXXXXXX-logs`, y `/tmp/git-main` y `/tmp/git-real` son repositorios compartidos por todas
las corridas, que crecen (86 y 30 commits al revisarlos). El invariante pedía `tmp_path`. Corrí dos
copias de la suite a la vez, ocho veces, y no falló ninguna; el riesgo es el candado de git si la
línea base de una cola coincide con otra corrida. Borré las 39 carpetas `-logs` que dejaron mis
corridas; las seis anteriores y los dos repositorios siguen ahí.

### 7. [Baja] Otros
- **`"54": null` en `<cola>-git.json`.** `cola-run.py:2482` llama a `git_base_guardar(i,
  GIT_BASE.get(i))` cuando la base todavía no existe (la fase `plan` no la fija), y después `autor`
  ya no la pone porque la clave está. Visto en el archivo: `{"54:fases": ["plan", "autor"],
  "54:plan_sha256": "cf4c…", "54": null}`. El diff del revisor sale bien por las fotos de cada fase;
  se pierde solo el respaldo de `git_diff_etapa` cuando falta una foto.
- **Git caído durante `plan` se llama «violación».** `:2444-2445`. Con el historial sin responder, la
  etapa con plan se pausa con «violación de plan… `<diff propio no verificable>`»; la misma falla sin
  plan deja seguir la cola (`rc 0`), que es la regla de siempre («el historial ayuda, no bloquea»).
  Es conservador, pero el motivo confunde y cada relanzamiento vuelve a correr `plan`.
- **Un archivo que escribió otro durante `plan` pausa la cola y queda como propio.** Fuera de la lista
  de compartidos (por ejemplo `encargos/55-otro.md`, un encargo nuevo), la cola se pausa con el
  detalle; Reanudar se niega («eso se decide a mano») y al relanzar con `--desde 54:plan` la fase
  corre de nuevo. El archivo sale bajo «Fase propia plan» en el diff. Lo mismo si el agente tocó
  código de verdad: `pi/base.py` queda cambiado y el revisor lo ve ahí. Es la decisión que anotó el
  autor y me parece razonable; lo dejo escrito para que no sorprenda.
- Siguen abiertos los bajos 9 y 10 de la revisión 1.

## Lo que revisé y está bien

- **C1, sin `plan` nada cambia.** Código de la foto anterior al autor (`e6f4148`) contra el de ahora,
  mismas entradas: `--simular` por `main()`, `restante()`, `fases_restantes()` y `uso_de_cuentas()`
  desde cada fase son **idénticos en los 44 manifiestos sin `plan`** (los `cola-*.toml` reales y los
  de `46-fixtures/` y `56-fixtures/`). Y por `main()` completo,
  cinco corridas (feliz, rechazada hasta agotar vueltas, autor sin cuota y `--desde`, pausa del
  usuario y `--desde 54:fix1`, `--desde 54`): fases, `vivo`, bitácora, filas del historial, forma de
  `<cola>-git.json`, diff y prompts iguales. Lo único distinto es la ruta del script en la línea de
  relanzar, que es de mi copia.
- **C2.** `--simular` de la fixture: `plan` 1,7 min y `revplan` 3,2 min con `medium`, los dos
  «débil, factor 0,3», antes de `autor`; duración «~24.6 min, entre 22.5 y 44.3».
- **C3.** El agente toca `pi/base.py`: `pausada`, «violación de plan… diff propio: pi/base.py», no
  corre ninguna fase más. También si además se corta por cuota.
- **C4.** Dos rechazos: `plan, revplan, plan2, revplan2`, `detenida`, y el aviso dice «plan rechazado
  dos veces; la etapa se detiene antes del código».
- **C5.** `autor` y `fix1` reciben el plan entero; `revplan` va con `claude-opus-5-5 medium` y `rev1`
  con el esfuerzo de siempre; la plantilla de revisión trae la regla.
- **C6.** Con las filas que escribe `anotar()` (dos vueltas de plan y un arreglo): `min_ret` 12 de 24
  min, y `balance.datos()` corre entero.
- **Plan fijado.** Aprobado y pausado antes del autor: `--desde 54:autor` en proceso nuevo sigue bien.
  Si se pierde `<cola>-git.json`, se detiene con «no hay plan aprobado e inmutable».
- **Reglas del encargo.** El arreglo no agregó funciones a `cola-run.py`. La pausa por cuota de las
  fases que ya existían, el despacho, los botones y `git_diff_etapa` no cambiaron. `vivo`,
  `historial.jsonl` y `<cola>-git.json` se escriben como antes.
- **Seguridad.** No existen `encargos/54-busquedas.jsonl` ni `encargos/manual-busquedas.jsonl`. En el
  registro de `fix1` hay 41 comandos: lecturas, `py_compile` y las suites; ninguno llama al buscador,
  a la red, a `tmux`, a `nodo-desplegar` ni a una cola. En la ventana de `fix1` (09:04–09:22) cambiaron
  en el vault los tres archivos del diff y `historial.jsonl`; una nota de `00-MemoriaIA` cambió a las
  09:08, pero Codex corre en un entorno que no puede escribir ahí y su registro solo la nombra al leer
  el índice. El diff no agrega tokens ni rutas de los vaults a ninguna salida.
- **JS.** La etapa no cambió ningún archivo JS.
- **Nombres.** En el diff y en `54-RESULTADO.md` las cuentas van como «Claude (Cami)» y «Codex».

## Arnés (para quien arregle y para la próxima revisión)

Es el de `54r1-RESULTADO.md` con dos cambios: `VERSIONES_REPO` va a `<raíz>/git/11-Pi5.git` (para
que la carpeta hermana tenga su historial al lado) y cada `main()` recarga el módulo. El temporal se
borró al terminar.

```python
class Mundo:                       # __init__ como en 54r1, sin cargar el módulo; al final self.proceso()
    def proceso(self):
        """Módulo nuevo: lo que ve un relanzamiento con tmux."""
        global _N
        _N += 1
        spec = importlib.util.spec_from_file_location(f"cola_run_r54b_{_N}", self.codigo)
        cr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cr)
        self.cr = cr
        cr.VAULT, cr.D, cr.E, cr.L = self.raiz / "vault", self.arbol, self.E, self.L
        cr.ESTADO, cr.HISTORIAL, cr.MODELOS = self.E / "COLA-ESTADO.md", self.E / "historial.jsonl", self.E / "modelos.toml"
        cr.PLANTILLA_REV, cr.USO = self.E / "revision-plantilla-v2.md", self.raiz / "no-hay-uso.json"
        cr.subprocess, cr.SIMULANDO = SinProcesos(), False
        cr.ahora = lambda: self.reloj
        cr.avisar = cr.avisar_texto = lambda *a, **k: self.avisos.append(a)
        cr.registrar_aviso = lambda *a, **k: None
        cr.log = lambda t: self.bitacora.append(t)
        cr.sesion_viva = lambda n: False
        cr.medir = lambda cid: {"5h": 10.0, "sem": 5.0, "renueva_5h": None, "renueva_sem": None,
                                "momento": self.reloj.isoformat(timespec="seconds"), "fuente": "fresco"}
        class Reloj:               # NO parchar time.sleep del módulo real: versiones.py espera a git con él
            def __getattr__(self, n): return getattr(time, n)
            def sleep(self, s): raise RuntimeError("arnés: quiso dormir")
        cr.time = Reloj()
        cr.correr, cr.pruebas, cr.foto = self._correr, (lambda: (set(), "")), (lambda: {})
        cr.desplegar = lambda *a: None
        cr.pausa_pedida = lambda nom, d=None: self.pausar_tras is not None and self.fases[-1:] == [self.pausar_tras]

    def main(self, *args, nuevo=True):
        if nuevo:
            self.proceso()
        self.cr.sys.argv = ["cola-run.py", str(self.manifiesto()), *args]    # cola-91.toml en disco
        self.fases.clear(); self.bitacora.clear(); self.avisos.clear()
        try:
            rc = self.cr.main()
        except BaseException as e:
            rc = f"{type(e).__name__}: {e}"
        return rc, json.loads((self.E / "vivo/cola91.json").read_text(encoding="utf-8"))


# Hallazgo 1: la fase plan se corta por cuota sin escribir nada
m = Mundo(); guion_feliz(m)
m.guion["plan"] = lambda m: {"sin_cuota": True}
m.main()

# Hallazgo 2: la sesión muere antes de la primera fase y se reanuda con lo que da el vivo
class Muerte(BaseException): pass
m = Mundo(); guion_feliz(m); m.proceso()
def muere(): raise Muerte("kill -9")
m.cr.pruebas = muere
m.main(nuevo=False)
v = json.loads((m.E / "vivo/cola91.json").read_text())
m.main("--desde", m.cr._desde_del_vivo(v, tomllib.loads(m.manifiesto().read_text())["etapa"]))

# Hallazgo 3: carpeta hermana (hay que crearla y hacer init() de <raíz>/git/13-Hermana.git antes)
m = Mundo(extra="13-Hermana"); guion_feliz(m)
m.guion["plan"] = lambda m: (m.escribir("encargos/54-PLAN.md", PLAN),
                             (m.arbol.parent / "13-Hermana/nota.md").write_text("tocada por el plan\n"))[0]
m.main()
```

## Veredicto

**Desplegable.** Lo que pedía el encargo está y funciona por el camino real: C1 a C7 se cumplen con
`main()`, el `versiones.py` real y relanzamientos en proceso nuevo; los dos graves de la revisión 1
quedaron cerrados; y una cola sin `plan` se comporta exactamente igual que antes. Lo que queda no
rompe nada de lo que funciona hoy: está todo detrás de `plan = true`, que ninguna cola usa todavía.

Pendientes, en este orden. **Los tres primeros conviene cerrarlos antes de lanzar la primera cola
real con `plan = true` sin nadie mirando**, porque los hallazgos 1 y 2 la dejan detenida con un
motivo que no es cierto y el botón Reanudar no la saca:

1. Fase `plan` cortada por cuota sin plan escrito: pausar por cuota, no detener (hallazgo 1).
2. Punto de partida `plan` al reanudar una etapa con plan que no empezó (hallazgo 2).
3. Control y diff de la carpeta hermana, antes de combinar `plan` con `arboles_extra` (hallazgo 3).
4. Pruebas para los arreglos 3, 4 y 7, para `fixN` con plan y para el corte por cuota en `plan`;
   `main()` con `--desde 54:plan2` y `54:revplan2` (hallazgo 5).
5. ETA desde `plan2` (hallazgo 4), carpetas en `/tmp` (hallazgo 6) y los bajos del hallazgo 7,
   incluidos el 9 y el 10 de la revisión 1.

Mientras tanto, si una cola con plan queda detenida por 1 o 2, se recupera a mano con
`--desde <etapa>:plan`.

VEREDICTO: DESPLEGABLE
