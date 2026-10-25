# Plan 87 — cierre barato en rev2/rev3

## Enfoque

Agregar `cierre_barato = true` como opt-in. Antes de cada `rev2`/`rev3`, decidir desde las
fotos git del último `fixN`: cierre ágil sólo con diff verificable, sin rutas nuevas respecto de
la etapa, sin `RUTAS_SENSIBLES` y con hasta `CIERRE_MAX_LINEAS = 150`. Toda duda conserva la
revisión completa. El cierre se anota como `cierre`; `ESCALAR`, rc/error, archivo ausente o
veredicto final no exacto ejecuta de inmediato la revisión completa de esa misma `revN`.
`NO DESPLEGABLE` conserva `rN` y sigue a `fixN+1`/`consultar_o_seguir`.

Resolver `modelo_cierre`/`esfuerzo_cierre`, o el nivel `agil` del **revisor**, con los mismos
controles de candado/esfuerzo. Sin editar `modelos.toml`. El pronóstico nombra cierre en
rev2/rev3, usa base `rev` × 0,3 hasta tres filas propias; su ETA máxima sigue siendo completa.

## Archivos y funciones

- `encargos/cola-run.py`: constantes y ayudantes puros E1–E4 (foto `fixN`, rutas, `--numstat`);
  ajustar `modelo_de()`, `prompt_de()`, `etapa()`, `restante()`, `fases_restantes()` y
  `fases_pendientes()`. Reusar `GIT_BASE`/`git_base_guardar()`; nunca decidir desde informes.
- Nueva `encargos/revision-cierre-plantilla.md`: `r(N-1)`, sólo diff `fixN`, «Arreglos vuelta» y
  plan; evidencia archivo:línea+prueba por [Grave]/[Media], una línea final exacta.
- `encargos/balance.py`: `cierre` cuenta retrabajo. Nuevo `test_cierre_barato.py` reutiliza el
  lanzador/repositorio temporal de `test_fase_plan.py`; ampliar `test_balance.py`.

## Premisas comprobadas

| Comando | Salida relevante |
|---|---|
| `rg -n 'FASES|def (modelo_de|prompt_de|etapa|git_foto|git_diff_etapa)' encargos/cola-run.py` | `FASES = ["autor", "rev1", "fix1", "rev2", "fix2", "rev3"]`; funciones en 476, 1340, 1480, 2293 y 2507. |
| `sed -n '1400,1455p' encargos/cola-run.py` | `git_base_guardar()` persiste `{fase, antes, despues, vivas}`: hay límites reales de `fix1`/`fix2`. |
| `sed -n '1,80p' encargos/modelos.toml` | ágil: Codex `gpt-reserve`/`medium`; Claude `claude-sonnet-5-5`/`medium`; seguridad: `fuerte/maximo/fuerte`. |
| `rg -n RETRABAJO encargos/balance.py` | Regex `fix*|rev2+|plan2|revplan2`: hoy omite `cierre`. |
| `sed -n '1,90p' encargos/test_fase_plan.py` | `TemporaryDirectory`, lanzador falso y git temporal, sin cola real. |

## Pruebas de aceptación

- **C1.** Copias reales `cola-82.toml` y `cola-85.toml`, sin campo: salida `--simular` previa
  byte a byte y corrida falsa de dos vueltas conservan `autor, rev1, fix1, rev2, fix2, rev3`.
- **C2.** Fotos `git_foto`; `fix1` de 20 líneas sobre archivo de `autor`: `rev2` es `cierre`,
  usa ágil del revisor e incluye `r1`+sólo diff `fix1`.
- **C3.** Repo temporal: archivo nuevo (E1), `pi/x.service` y `encargos/modelos.toml` (E2), 151
  líneas (E3), foto ausente (E4): cada uno hace `rev2` `maximo`, sin fila cierre.
- **C4.** `ESCALAR`, sin veredicto, rc 1, resultado heredado, DESPLEGABLE en línea 10/40 y formato
  alterado: historial ordenado `cierre`, `rev` para `rev2`.
- **C5.** `VEREDICTO: NO DESPLEGABLE` exacto copia `87r2-RESULTADO.md`, llama el doble de
  `consultar_o_seguir` y llega a `fix2`.
- **C6.** Manifiesto opt-in: rev2/rev3 `cierre [débil, factor 0,3]`. Copia del historial real con
  `balance.py --desde 47` no cambia sin cierres; una fila real con rol cambiado a `cierre` sí es
  retrabajo. Con `NODO_PRUEBAS=1`: nueva suite y `test_fase_plan`, `test_diff_propio`,
  `test_balance`, `test_pronostico`, `test_consultas`, `test_acciones_cola`.
