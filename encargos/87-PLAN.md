# Plan 87 — cierre barato en rev2/rev3 (v2, corrige 87rplan)

## Enfoque

`cierre_barato = true` es opt-in (sólo `is True`, nunca en etapas remotas). Antes de cada `rev2`/`rev3` la
cola decide desde `GIT_BASE["<id>:fases"]` (fotos `git_foto` de cada fase propia), nunca desde informes:
revisión **completa** si **E1** el `fixN-1` toca un archivo fuera del diff propio previo de la etapa, **E2**
toca `RUTAS_SENSIBLES` (las del encargo, más `encargos/revision-*plantilla*` y `RE_SECRETO`), **E3** suma
más de `CIERRE_MAX_LINEAS = 150` en `--numstat` (un binario `-` también escala) o **E4** falta una foto,
git falla, hay `arboles_extra`, falta `{i}r{N-1}-RESULTADO.md` o el nivel `agil`. Si no, corre `cierre`.
Archivos de otras colas vivas dentro del diff del fix escalan por E1 (ante la duda, completa).

El `cierre` es un bloque previo a la `revN` normal, que queda intacta: modelo `agil` del **revisor** (o
`modelo_cierre`/`esfuerzo_cierre`), `exigir_candado`/`esfuerzo_incompatible` iguales, `chequear_cuota`,
`unlink` de `{i}r-RESULTADO.md`, fila `rol = "cierre"` con `fase = "revN"`. Veredicto: sólo las últimas 3
líneas con `^VEREDICTO: (DESPLEGABLE|NO DESPLEGABLE|ESCALAR)$` exacto y una sola línea `VEREDICTO`;
DESPLEGABLE termina la etapa; NO DESPLEGABLE copia `r{N}` y llama a `consultar_o_seguir` como hoy;
cualquier otra cosa (ESCALAR, sin línea, rc ≠ 0, corte por tiempo `CIERRE_MAX_MIN = 30` → rc 124,
archivo no escrito) sigue a la revisión completa en la misma vuelta. Sin cuota: `Pausa` con
`desde = <id>:revN`; al reanudar se recalcula E1–E4.

## Archivos y funciones

- `encargos/cola-run.py`: constantes `RUTAS_SENSIBLES`, `CIERRE_MAX_LINEAS`, `CIERRE_MAX_MIN`,
  `PLANTILLA_CIERRE`, `VEREDICTO_CIERRE`; nuevas `cierre_aplica`, `decidir_cierre`, `veredicto_cierre`,
  `prompt_cierre`, `correr_cierre`; cambios en `modelo_de()`, `esfuerzo_incompatible()`,
  `validar_esfuerzos()`, `modelos_con_candado()`, `exigir_candado()`, **`pronostico()`**, `rol_de_fase()`
  (nueva, la usan `restante()` y `fases_pendientes()`), `fases_restantes()`, `etapa()`, `_correr()`
  (`limite_s` opcional, por defecto `None` = como hoy) y la salida de `--simular`.
- `pronostico()`: `rol_base` mapea `"cierre" → "rev"` y el factor 0,3 se aplica a
  `rol in ("plan", "revplan", "cierre")` con menos de 3 filas propias (evita `KeyError` en `BASE`).
- Nueva `encargos/revision-cierre-plantilla.md`. `balance.py`: **sin cambio** (ver H2).
- Nuevo `encargos/test_cierre_barato.py` y `encargos/87-fixtures/` (manifiestos copiados, salidas base,
  generador). `test_balance.py` sin cambio: la fila sintética va en la suite nueva.

## Premisas comprobadas

| Comando | Salida relevante (copiada) |
|---|---|
| `sed -n 1216p;1235p encargos/cola-run.py` | `rol_base = {"plan": "autor", "revplan": "rev"}.get(rol, rol)` · `if rol in ("plan", "revplan") and len(mismo) < 3:` |
| `sed -n 180,187p encargos/cola-run.py` | claves `("claude"\|"codex", "autor"\|"fix"\|"rev")`: sin `cierre` |
| `sed -n 36p;187p encargos/balance.py` | `RETRABAJO = re.compile(r"(fix\d*\|rev([2-9]\|\d{2,})\|plan2\|revplan2)$")` · `ret = bool(RETRABAJO.fullmatch(_texto(f["fase"])))` |
| `python3 -B encargos/balance.py --desde 47` (historial real, 25-10) | `Balance de encargos 47a–88a: 51 encargos, 203 fases` · `TOTAL: 51 enc · 1ª 12/50 · ret min 46 % · … · 884 de 1932 min en retrabajo` |
| `grep -c '"rol": "cierre"' encargos/historial.jsonl` | `0` |
| `git show origin/main:encargos/cola-run.py \| sha256sum` | `da22939d…b914cb` (foto base) |
| `python3 -B encargos/87-fixtures/genera-simular-antes.py <base>` | `simular-antes-82.txt: 611 bytes`, `simular-antes-85.txt: 1119 bytes`; 1.ª línea `82 · naturaleza: seguridad` |

## Pruebas de aceptación (`test_cierre_barato.py`, temporales y `NODO_PRUEBAS=1`)

- **C1.** `--simular` del `cola-run.py` nuevo sobre `87-fixtures/cola-82.toml` y `cola-85.toml` con las
  entradas del generador da byte a byte `simular-antes-82.txt`/`-85.txt`. Corrida falsa de 2 vueltas sin
  el campo: fases `autor rev1 fix1 rev2 fix2 rev3`, roles `autor rev fix rev fix rev`.
- **C2.** Repo temporal con `git_foto` real: `fix1` de 20 líneas sobre un archivo del `autor` → fila
  `rev2`/`cierre`, modelo `gpt-reserve medium`; la instrucción trae el `r1` y el diff del fix, no el del autor.
- **C3.** E1 archivo nuevo, E2 `pi/x.service` y `encargos/modelos.toml`, E3 151 líneas, E4 sin foto del
  fix: `rev2` completa `gpt-5.6-terra xhigh` [maximo], sin fila `cierre`.
- **C4.** ESCALAR; sin veredicto; rc 1; `87r-RESULTADO.md` DESPLEGABLE dejado por el fix y no reescrito;
  DESPLEGABLE en la línea 10 de 40; ` veredicto: Desplegable `; corte por tiempo: historial `cierre`, `rev`.
- **C5.** `VEREDICTO: NO DESPLEGABLE` del cierre: se copia `87r2-RESULTADO.md`, `consultar_o_seguir`
  recibe `rev2` y corre `fix2`.
- **C6.** `--simular` con el campo muestra `cierre … [débil, factor 0,3]`; `fases_restantes`/
  `fases_pendientes` dan `cierre` en rev2/rev3; `pronostico("codex", "cierre", …)` = rev × 0,3 sin
  `KeyError`; `restante()` max = completa + cierre. Balance real `--desde 47` igual con y sin filtrar
  `cierre`; una fila real copiada con `fase = "rev2"`, `rol = "cierre"` suma a `min_ret`.
- **C7 (H4).** `--desde 87:rev2` tras un cierre sin cuota recalcula E1–E4 (si el fix quedó sensible,
  completa); etapa remota con el campo no corre cierre; `vivo` muestra `rol = "cierre"` durante el cierre.

## Respuesta a 87rplan

- **H1 [Grave].** `pronostico()` entra en la lista: `rol_base` mapea `cierre → rev` y el factor 0,3 incluye
  `cierre`. C6 prueba `pronostico("codex", "cierre", …)` sin historial propio (el caso del `KeyError`).
- **H2 [Media].** Corregida la premisa: `RETRABAJO` se aplica a `fase`, y el cierre se anota como
  `fase = revN`, así que `balance.py` **no cambia**. La prueba de C6 fija ese comportamiento con
  `fase = rev2`/`rol = cierre`; nunca se anota `fase = "cierre"`.
- **H3 [Media].** C1 compara contra `87-fixtures/simular-antes-*.txt`, generadas con la foto base
  (`da22939d…`) por `genera-simular-antes.py` con entradas congeladas. C6 trae los totales actuales.
- **H4 [Baja].** Agregados al enfoque y a C7: pausa y `--desde` recalcula, remotas excluidas, `rol` en
  `vivo` y el corte por tiempo como falla cerrada explícita (`CIERRE_MAX_MIN`).
