# Encargo 54: fase `plan` antes del código (Claude (Diego), 12-10-2026)

Naturaleza `seguridad`. **Alcance mínimo:** la fase existe y la cola la respeta. Que la skill la
proponga y el panel la dibuje con un estilo propio queda como ampliación prevista.

## Valor y costo

La 43b se escribió sobre una premisa falsa y un diseño del vigilante que chocaba con `/estado`.
Le costó 3 revisiones, con 14 hallazgos en la primera. Un plan de una página, revisado antes de
escribir código, se aprueba o rechaza en minutos y cuesta una fracción de una vuelta de código.

## Leer primero

- `encargos/cola-run.py`:
  - el bucle de fases de `etapa()` (~1687) y cómo se nombran las fases (`autor`, `revN`,
    `fixN`);
  - `pronostico()` y la ponderación por rechazo;
  - `fases_restantes` (46a);
  - la marca `.pausar` de la 46c;
  - el diff propio de la 53 (`53-RESULTADO.md`);
  - el registro en `historial.jsonl`.
- `encargos/revision-plantilla-v2.md`.
- `encargos/balance.py`: cómo cuenta las fases (no se debe romper).
- `encargos/trampas.md`: «Cola y encargos».

**No hace falta leer** las páginas ni el bot.

## Qué hacer

1. **Campo nuevo de etapa:** `plan = true`. Por defecto es `false`, y sin el campo la cola se
   comporta exactamente como hoy.
2. **Con `plan = true`, antes de `autor`:**
   - **`plan`:** el autor escribe **sólo** `encargos/<id>-PLAN.md`, de una página como máximo,
     con:
     - el enfoque;
     - los archivos y funciones que tocará;
     - las premisas que comprobó, con su comando y su salida;
     - las pruebas de aceptación por criterio `C1…Cn`, con el dato real que usan.
     No toca código.
   - **`revplan`:** el revisor aprueba o rechaza el plan, con el veredicto en
     `<id>rplan-RESULTADO.md` (`PLAN APROBADO` o `PLAN RECHAZADO` más sus motivos). Va con el
     **mismo modelo del rol `rev`, pero con esfuerzo `medium`**, porque es texto corto.
   - Hay como máximo **una** vuelta de plan: si el plan se rechaza, el autor lo corrige una vez y
     se revisa de nuevo. Si vuelve a rechazarse, la etapa se detiene (se gastó poco).
3. **Fases siguientes:**
   - el `autor` y los `fixN` reciben el plan aprobado como parte de su instrucción;
   - la plantilla de revisión gana una regla: «el código se juzga contra el plan aprobado; lo que
     el plan no contemplaba y el código agrega es fuera de alcance».
4. **`fases_restantes`, el pronóstico y `historial.jsonl`** cuentan `plan` y `revplan` como fases
   más. El pronóstico usa un factor de 0,3 sobre `autor` y `rev` mientras no haya historial
   propio, y lo marca `débil`.

## Criterios de aceptación

- C1. Sin `plan`, una etapa da las mismas fases, los mismos pronósticos y la misma salida de
  `--simular` que antes. Se prueba con `46-fixtures/` y un manifiesto real.
- C2. Con `plan = true`, `--simular` muestra `plan` y `revplan` (débiles) antes de `autor`, y
  `fases_restantes` las incluye.
- C3. Si la fase `plan` toca un archivo distinto de `<id>-PLAN.md`, la cola la marca como
  violación y no sigue (se comprueba con el diff propio de la 53).
- C4. Plan rechazado dos veces → la etapa se detiene, con `detenida` en `vivo` y el motivo.
- C5. El autor recibe el plan aprobado (se prueba con un lanzador falso que captura la
  instrucción).
- C6. `balance.py` no se rompe con las fases nuevas y las cuenta como retrabajo sólo si son
  segunda vuelta de plan.
- C7. `encargos/test_fase_plan.py` (nuevo) y las suites del manifiesto pasan. El RESULTADO dice
  cada criterio cumplido o no, con su salida.

## Invariantes

- **Archivos compartidos:** `vivo`, `historial.jsonl` y `<cola>-git.json` se escriben igual que
  hoy (atómico o bajo `flock`).
- **Pruebas:** lanzador falso, `tmp_path`, sin colas reales, sin `/opt/nodo/datos` y sin avisos.
- **Root, router y catálogo:** no aplican.

## Reglas

- **Un arreglo no agrega funciones nuevas.**
- No cambies la pausa por cuota, el despacho, los botones de la 46c ni el diff de la 53.
- Cuentas siempre como «Claude (Diego)», «Claude (Cami)» y «Codex». Sin buscador web.

## Fuera de alcance

Que la skill proponga `plan = true` por su cuenta y el estilo propio en el panel (ampliación
prevista). Cambiar `modelos.toml`.

## Resultado

`encargos/54-RESULTADO.md` con los cambios, la forma de `<id>-PLAN.md` y de su veredicto, y
C1–C7 uno por uno.
