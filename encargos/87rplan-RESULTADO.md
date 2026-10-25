# Revisión del plan 87 (Claude (Cami), 24-10-2026)

Revisé `87-PLAN.md` contra `87-revision-escalonada.md` y comprobé cada premisa en el código. No
modifiqué código ni el plan.

## Forma

- **Cabe en una página:** sí. `wc -l -w 87-PLAN.md` → `51  446`.
- **Enfoque:** sí, explícito (opt-in, E1–E4 desde fotos git, falla cerrada, modelo `agil` del
  revisor, pronóstico con factor 0,3).
- **Archivos y funciones:** listados, **pero falta `pronostico()`** (ver H1).
- **Premisas con comando y salida:** las hay, pero la salida está parafraseada, no copiada, y una
  conclusión está mal (H2).
- **Criterios C1…C6 con dato real:** C2–C5 traen datos concretos (20 líneas, 151 líneas,
  `pi/x.service`, `encargos/modelos.toml`, línea 10 de 40). A C1 y a C6 les falta el dato base
  (H3).

## Premisas que verifiqué y se sostienen

- `rg -n 'FASES|def (modelo_de|…)' cola-run.py` → `2289:FASES = ["autor", "rev1", "fix1", "rev2",
  "fix2", "rev3"]`, `476:def modelo_de`, `1340:def git_foto`, `1480:def git_diff_etapa`,
  `2293:def prompt_de`, `2507:def etapa`. Coincide.
- `sed -n '1400,1455p' cola-run.py` → `git_base_guardar()` agrega `{"fase", "antes", "vivas",
  "inicio"}` y después `despues`/`fin` en `GIT_BASE["<etapa>:fases"]`. Hay límites por `fixN`.
  Coincide.
- `modelos.toml` → `agil = { modelo = "claude-sonnet-5-5", esfuerzo = "medium" }` (l. 23),
  `agil = { modelo = "gpt-reserve", esfuerzo = "medium" }` (l. 30), `[naturaleza.seguridad]
  autor = "fuerte" / rev = "maximo" / fix = "fuerte"`. Coincide.
- Existen `cola-82.toml`, `cola-85.toml`, `historial.jsonl` y las seis suites que nombra C6.
  `revision-cierre-plantilla.md` y `test_cierre_barato.py` todavía no existen, como corresponde.

## Hallazgos

### H1 [Grave] `pronostico()` no figura entre las funciones a cambiar, y sin cambiarla el rol `cierre` rompe
`cola-run.py:1216` hace `rol_base = {"plan": "autor", "revplan": "rev"}.get(rol, rol)` y
`cola-run.py:1235` hace `base = BASE[(motor, rol_base)]`. `BASE` (l. 180–187) sólo tiene las claves
`autor`/`fix`/`rev`. El factor 0,3 sólo se aplica a `rol in ("plan", "revplan")` (l. 1235–1240).
Si `fases_restantes()` (l. 647) o `restante()` llaman a `pronostico(cid, "cierre", …)` como pide el
punto 4, el resultado es `KeyError: ('codex', 'cierre')`. Si no lo llaman, no hay `[débil, factor
0,3]`. El plan nombra `restante()`, `fases_restantes()` y `fases_pendientes()`, pero no la función
donde vive el mecanismo que dice reutilizar. Además, C6 no prueba el pronóstico de `cierre` sin
historial propio, el caso en que aparece el `KeyError`.

### H2 [Media] Premisa equivocada sobre `balance.py`; la prueba de C6 no distingue nada
La premisa dice «Regex `fix*|rev2+|plan2|revplan2`: hoy omite `cierre`». Pero `balance.py:187`
aplica `RETRABAJO` a `f["fase"]`, no a `rol`. El encargo (punto 3) manda que la fase siga llamándose
`revN` y que sólo el rol sea `cierre`. Una fila `{"fase": "rev2", "rol": "cierre"}` **ya** cuenta como
retrabajo hoy. La prueba de C6, «una fila real con rol cambiado a `cierre` sí es retrabajo», pasa
igual sin ningún cambio, así que no detecta nada. El plan tiene que decir una de dos cosas:
- que `balance.py` no necesita cambio, y entonces la prueba fija ese comportamiento con
  `fase = rev2`/`rev3` y `rol = cierre`;
- o qué cambia exactamente, sin pasar a anotar `fase = "cierre"`, que rompería `--desde`.

### H3 [Media] C1 y C6 sin su dato real
- **C1:** no dice contra qué se compara «byte a byte» (qué copia del `cola-run.py` anterior, ni cómo
  se guarda la salida de `--simular` antes del cambio), ni muestra esa salida base.
- **C6:** no da los totales actuales de `balance.py --desde 47`, que son la referencia de «no
  cambia».

Los dos datos se pueden obtener hoy, antes de tocar el código, y deberían estar en el plan.

### H4 [Baja] Puntos del encargo que el plan no menciona
- Un `cierre` sin cuota se pausa y, al reanudar con `--desde`, E1–E4 se **recalcula**.
- No aplica a etapas remotas (PC-2503).
- En `vivo` el rol también es `cierre`.
- El corte por tiempo cuenta explícitamente como falla cerrada (el plan sólo dice «rc/error»).

Ninguno tiene un criterio propio en el plan. Habría que agregar al menos una prueba de `--desde rev2`
con un `cierre` pausado.

## Veredicto

La forma y la mayoría de las premisas están bien. Pero H1 deja fuera del plan la función donde vive
el mecanismo de pronóstico que se reutiliza, y tal como está escrito llevaría a un `KeyError`. H2
parte de una lectura equivocada de `balance.py` y hace que una prueba de C6 sea vacía. Hay que
corregir H1–H3 y agregar a la lista los puntos de H4.

PLAN RECHAZADO
