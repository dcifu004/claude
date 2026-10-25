# Encargo 87: cierre barato en la rev2 y la rev3 (Claude (Diego), 24-10-2026)

Naturaleza `seguridad`. Etapa con `plan = true`, el primer uso real de la fase plan del encargo 54.
**Alcance mínimo:** un campo opcional de etapa, `cierre_barato = true`. Sin el campo, la cola se
comporta exactamente como hoy.

## Valor y costo

Lo medido con `balance.py` el 24-10:

- Desde la 61, `seguridad` pasa la primera revisión en 1 de 6 encargos, con 35 % de los minutos en
  retrabajo, USD 6,87 de Claude y 365 k tokens de Codex en promedio por encargo.
- Los graves de la rev1 son de fondo (la 71: un pedido hostil filtra secretos; la 73: el servicio
  no habla con systemd; la 70: el ✅ no queda ligado al texto). Ésos los tiene que ver una revisión
  fuerte.
- La rev2 y la rev3, en cambio, casi siempre confirman arreglos. Igual corren al nivel `maximo`
  (Codex terra xhigh ~7,9 min y 227 k; Claude Opus high hasta ~29 min y USD 8,89 en xhigh).

Un cierre barato verifica hallazgo por hallazgo sobre el diff del arreglo, con el nivel `agil` del
revisor, y escala a la revisión completa ante cualquier señal de riesgo. Una vuelta rev+fix cuesta
~USD 3–5 de Claude o ~125–180 k tokens de Codex.

## Antecedentes

- **Plan de optimización del 12-10** (memoria `encargos-economia`, punto 4): «revisión escalonada (un
  filtro barato antes de la xhigh)», condicionada a que `balance.py` la justificara. Este encargo es
  esa línea.
- **El usuario eligió el 24-10, 18:26:**
  - el escalón va en la rev2 y la rev3, no antes de la rev1;
  - alcance mínimo;
  - Codex escribe y Claude (Cami) revisa;
  - fase plan activada.
- **54 (`54-fase-plan.md`, `54r-RESULTADO.md`, DESPLEGABLE):** `plan`/`revplan` existen en
  `cola-run.py`. Ningún manifiesto la había usado antes de éste. `revplan` ya corre con el modelo de
  `rev` a esfuerzo `medium`: es el precedente de una fase de revisión más barata.
- **53 (`53-RESULTADO.md`):** cada fase tiene foto git antes y después (`git_foto`, ~2577–2589), con
  la que se obtiene el diff propio de la fase.
- **51 (`consultar_o_seguir`):** después de un NO DESPLEGABLE con un arreglo pendiente puede haber
  una consulta al usuario. Debe seguir funcionando.
- **`modelos.toml`:** «la REVISIÓN nunca va por debajo del autor». Este encargo es una
  **excepción acotada y autorizada por el usuario** sólo para el cierre. Se cumple porque un cierre
  sólo puede aprobar lo que ya aprobó una revisión al nivel de la naturaleza, y escala ante la duda.
- No se encontró en `_descartados/` nada sobre revisiones escalonadas. Se buscó: escalonad,
  filtro barato, pre-revisión, triage.

## Leer primero

- `encargos/cola-run.py`:
  - `FASES` y `FASES_PLAN` (~2290);
  - `prompt_de()` (~2294–2370), la rama `rev` y la de arreglos;
  - el bucle de `etapa()` (~2509–2665): fotos `foto_antes`/`foto_despues`, `git_diff_etapa`, el
    `unlink` de `{i}r-RESULTADO.md` antes de revisar, el veredicto con `VEREDICTO_OK`, la copia a
    `{i}r{v}-RESULTADO.md` y `consultar_o_seguir`;
  - `modelo_de()` (~476), `exigir_candado`, `esfuerzo_incompatible`;
  - `pronostico()` y el factor 0,3 para fases sin historial (~1216–1240);
  - `restante()`, `fases_restantes()` y `fases_pendientes()`;
  - la salida de `--simular` (~4430–4460).
- `encargos/revision-plantilla-v2.md`: el formato de hallazgos y veredicto (**no se modifica**).
- `encargos/balance.py` y `encargos/test_balance.py`: cómo cuenta retrabajo.
- `encargos/test_fase_plan.py`: el lanzador falso que captura la instrucción. Reutilizarlo.
- `encargos/trampas.md`, sección «Cola y encargos».

**No hace falta leer** las páginas de Cockpit, el bot, `nodo-desplegar` ni PC-2503.

## Qué hacer

1. **Campo nuevo de etapa: `cierre_barato = true`.** Por defecto es `false`. No aplica a etapas
   remotas (PC-2503), que ya no tienen arreglos.
2. **Decisión determinista antes de cada `rev2`/`rev3`** de una etapa con el campo. La toma la cola
   desde sus fotos git y nunca desde archivos ni variables que escriba el autor (trampa 32b). Se usa
   la revisión **completa** (como hoy) si se cumple cualquiera de estas condiciones:
   - **E1.** El diff del `fixN` anterior (su foto antes → su foto después) toca un archivo que no
     estaba en el diff de la etapa antes de ese arreglo.
   - **E2.** Toca una ruta sensible. La lista es una constante `RUTAS_SENSIBLES` en `cola-run.py`, con
     al menos: `*.service`, `*.path`, `*.timer`, `*sudoers*`, `*nodo-desplegar*`, `secretos/`,
     `encargos/cola-run.py`, `encargos/revision-plantilla*`, `encargos/modelos.toml` y
     `botv3/cuentas.toml`.
   - **E3.** Cambia más de **150 líneas** (agregadas + borradas, `git diff --numstat`). Va como
     constante `CIERRE_MAX_LINEAS`.
   - **E4.** No hay un diff del arreglo verificable: falta una foto o git falla. Ante la duda, revisión
     completa.

   Si no se cumple ninguna, la fase corre como **`cierre`**.
3. **Fase `cierre`** (ocupa el lugar de `revN`; en `vivo` y en `historial.jsonl` el rol es `cierre`
   y la fase se sigue llamando `revN`, para no romper `--desde`):
   - **Modelo:** el nivel `agil` del motor del revisor (Codex → `gpt-reserve` medium; Claude →
     `claude-sonnet-5-5` medium), leído de `[niveles.*]` de `modelos.toml` y nunca escrito en el
     código. La etapa puede fijar `modelo_cierre`/`esfuerzo_cierre`. `exigir_candado` y
     `esfuerzo_incompatible` se aplican igual que en `rev`.
   - **Plantilla nueva:** `encargos/revision-cierre-plantilla.md`. Recibe:
     - el `{i}r{N-1}-RESULTADO.md` anterior;
     - **sólo** el diff del último `fixN`;
     - la sección «Arreglos vuelta N-1» de `{i}-RESULTADO.md`;
     - el plan aprobado, si existe.

     Pide, por cada hallazgo [Grave] y [Media], «cerrado» o «no cerrado», con evidencia: archivo,
     línea y la prueba que lo cubre, corrida con su salida. Exige además mirar si el arreglo agregó
     algo fuera de lo pedido (lección de la 47b y la 70r).
   - **Veredicto en `{i}r-RESULTADO.md`.** Las últimas líneas deben traer exactamente una de estas:
     - `VEREDICTO: DESPLEGABLE`: todos los hallazgos están cerrados y no hay nada nuevo;
     - `VEREDICTO: NO DESPLEGABLE`: hay un hallazgo sin cerrar; sigue el arreglo como hoy,
       consulta 51 incluida;
     - `VEREDICTO: ESCALAR`: hay algo nuevo, una duda o algo que no pudo verificar.
   - **Falla cerrada.** ESCALAR, ninguna de las tres líneas, rc ≠ 0, corte por tiempo o un
     `{i}r-RESULTADO.md` que no se escribió durante la fase (la cola lo borra antes, como hoy) llevan
     a la **revisión completa en la misma vuelta**. Una fase `cierre` nunca cuenta como revisión
     completa.
   - Un `cierre` sin cuota se pausa como cualquier fase. Al reanudar con `--desde`, la decisión E1–E4
     se recalcula.
4. **Pronóstico.** `--simular`, `restante()`, `fases_restantes` y `fases_pendientes` muestran la rev2
   y la rev3 de esas etapas como `cierre`, con `[débil, factor 0,3]` sobre `rev` mientras no haya 3
   filas propias (el mismo mecanismo de `plan`). El máximo de la ETA sigue suponiendo revisión
   completa en cada vuelta.
5. **`balance.py`:** cuenta las filas `cierre` como retrabajo, igual que una `rev2+`. No se agrega
   ninguna agrupación nueva.

## Criterios de aceptación

Cada criterio se prueba en `encargos/test_cierre_barato.py` (nuevo), con el lanzador falso de
`test_fase_plan.py`, fotos git en un temporal y `NODO_PRUEBAS=1`.

- **C1. Sin cambios por defecto.** Sin `cierre_barato`, `--simular` sobre copias de `cola-82.toml` y
  `cola-85.toml` da la misma salida byte a byte que el `cola-run.py` anterior (la copia de la foto
  base de la etapa). Una corrida falsa de 2 vueltas produce las mismas fases y roles en el
  historial temporal.
- **C2. Va al cierre.** Con el campo, un `fix1` que sólo cambia 20 líneas de un archivo que ya estaba
  en el diff de la etapa da `rev2` con rol `cierre`. El lanzador captura:
  - el modelo `agil` del revisor;
  - una instrucción que contiene el `r1` y el diff del fix, y **no** el diff completo de la etapa.
- **C3. Escala.** Un caso por cada condición: E1 (archivo nuevo para la etapa), E2 (toca
  `pi/x.service` y, en otro caso, `encargos/modelos.toml`), E3 (151 líneas) y E4 (sin foto previa).
  Cada uno da `rev2` completa al nivel `maximo`, sin ninguna fila `cierre`.
- **C4. Falla cerrada.** Seis casos, uno por salida: `ESCALAR`, ninguna línea de veredicto, rc 1, un
  `r-RESULTADO.md` con DESPLEGABLE que el fix dejó escrito antes, el texto `VEREDICTO: DESPLEGABLE`
  en la línea 10 de 40, y un veredicto con espacios o mayúsculas raras. Cada uno corre después la
  revisión completa en la misma vuelta; el historial muestra las dos filas en orden.
- **C5. NO DESPLEGABLE del cierre.** Sigue `fix2` y se llama a `consultar_o_seguir` igual que hoy. La
  `{i}r2-RESULTADO.md` se copia igual.
- **C6. Pronóstico, balance y suites.**
  - `--simular` de un manifiesto con el campo muestra `cierre` en la rev2 y la rev3 con
    `[débil, factor 0,3]`.
  - `balance.py --desde 47` sobre el historial real da los mismos totales antes y después del
    cambio (todavía no hay filas `cierre`).
  - Una fila `cierre` sintética cuenta como retrabajo en `test_balance.py`.
  - Pasan las suites del manifiesto.

## Invariantes

- **Archivos compartidos:** no hay archivos compartidos nuevos. `historial.jsonl` y `vivo/` se
  escriben por las funciones que ya existen (`anotar`, `vivo`). La plantilla nueva sólo se lee.
- **Dueño y modo:** la plantilla nueva es un archivo normal del vault (dcifu004, 644). No se crea
  nada fuera de `11-Pi5`.
- **Pruebas:** usan temporales, sin escritura en `/opt/nodo/datos`, sin avisos reales
  (`NODO_PRUEBAS=1`), sin `claude` ni `codex` reales y sin red.
- **Entradas hostiles:** el `{i}r-RESULTADO.md` del cierre lo escribe un agente. Sólo se aceptan sus
  últimas 3 líneas, con las regex exactas. Todo lo demás escala (C4). La decisión E1–E4 sale de git,
  nunca del informe.
- **Router del bot:** no aplica.
- **Root:** no aplica. Nada corre como root. Un arreglo que toca unidades, sudoers o
  `nodo-desplegar` escala siempre (E2).
- **Alta en `nodo-desplegar`:** no aplica. `cola-run.py` y la plantilla corren desde el vault.
- **Candado de modelos:** `modelo_cierre` pasa por `exigir_candado`. No se agrega ningún modelo
  nuevo.
- **La cola en caliente:** no se modifica `revision-plantilla-v2.md`, que la propia cola 87 lee en
  cada revisión.

## Fuera de alcance

- Un filtro barato **antes de la rev1**. El usuario lo descartó el 24-10.
- **Ampliación prevista:**
  - que `balance.py` agrupe por `cierre`/completa y por `alcance`;
  - que la skill `encargar` proponga `cierre_barato` en `seguridad`;
  - que pase a ser el defecto de una naturaleza (eso va por propuesta del panel, nunca a mano en
    `modelos.toml`).
  Para no rehacer después: el rol en el historial se llama `cierre` y el campo, `cierre_barato`.
- Tocar `modelos.toml`, `revision-plantilla-v2.md`, las páginas o el bot.
- **Un arreglo no agrega funciones nuevas.**

## Pruebas sobre la forma real

- Los manifiestos de C1 son copias de `cola-82.toml` y `cola-85.toml` reales, no inventados.
- Las filas sintéticas de historial copian la forma de una fila real de `historial.jsonl`: mismas
  claves, tipos y formato de hora.
- Las fotos se hacen con el mismo `git_foto` sobre un repositorio temporal, no con diffs escritos a
  mano.
- La salida literal de cada suite va en el RESULTADO.

## Reglas

- Sin sudo, sin desplegar y sin lanzar colas reales. LF y reemplazos puntuales.
- Sin buscador web: cero búsquedas.
- Las cuentas se nombran «Claude (Diego)», «Claude (Cami)» y «Codex». A la persona se le dice «el
  usuario».

## Resultado

Escribe `encargos/87-RESULTADO.md` con:

- los cambios;
- las decisiones tomadas;
- cada criterio C1…C6, cumplido o no, con su comando y la salida literal;
- lo pendiente.
