# Encargo 99: la pestaña Projects de 🏭 AI Ops, de verdad (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `pagina`. Afinado completo. **Rama base: `base-99`** = la rama del 95 (tooltip de las colas, que también
toca `pi/cockpit-encargos/`) + la maqueta del 98 + `encargos/proyectos.json`. Parte de ella.

## Para qué

Diego vio la maqueta del 98 (`maquetas/98-projects/`) y le gustó: **ahora va a la consola instalada**
(`pi/cockpit-encargos/`, la 🧵 Encargos que hoy se ve como 🏭 AI Ops). Los encargos dejan de ser sueltos: se agrupan
por proyecto, con tablero, choques y flujo en el tiempo.

## Antecedentes (leer)

- `encargos-nube/98-proyectos-maqueta.md` (las decisiones de Diego: Kanban, topes WIP, resultado por proyecto,
  Now/Next/Later, Monte Carlo, choques, etiquetas en inglés con tooltip en español) y `encargos-nube/98-RESULTADO.md`
  (lo que salió, las dudas y los riesgos). **Esas decisiones no se reabren.**
- `maquetas/98-projects/`: `modelo.js` (asignación, columnas, métricas, CFD y Monte Carlo), `projects.js`,
  `projects.css`, `NOTAS.md` y `verificar.py`. Es el punto de partida: **reúsalo, no lo reescribas**.
- `pi/cockpit-encargos/`: la página instalada. Lee `historial.jsonl` con `cockpit.file` y el panel con
  `cockpit.spawn([... "cola-run.py", "--panel"])`, con rutas y argumentos fijos (comentario de la línea 1 de
  `encargos.js`). Tiene `glosario.js`, `red.js` y `revisar-anchos.js`. El 95 le sumó el tooltip de las colas.
- `pi/test_cockpit_paginas.py`: la suite de las páginas (tokens en un solo lugar, JS balanceado con el tokenizador,
  un solo ancho máximo, orden del menú, etc.). En la Pi no hay `node`: el JS lo revisa el tokenizador de esa suite.

## Decisiones de Diego (25-10)

1. **Board: B como portada y A como detalle**, como recomendó la maqueta. La portada son las tarjetas de proyecto
   (resultado, mini-tablero, avance, rework, abiertas, bloqueo y pronóstico al 80 %). Al tocar un proyecto se abre su
   carril A (las cinco columnas). Arriba, un conmutador para ver todos los carriles A juntos.
2. **Las dudas de asignación del 98 se resolvieron con lo que propuso la maqueta**, y ya están en
   `encargos/proyectos.json`: 07, 39b, 75, 78a, 80b y 90 → bot; 83 → cuentas; 20, 31 y 34 → consola; «57» → 57a y 57b.
   Las familias repartidas entre proyectos se dejan así. Los cerrados sin DESPLEGABLE se tratan como en la maqueta
   (Done con marca, fuera de throughput y cycle time).
3. **Fuente de datos: `encargos/proyectos.json`** (JSON y no TOML, porque la página lo lee sin parser). Lo mantiene
   Claude (Diego) al preparar cada encargo. **`abiertos` pasa a ser un override**: la columna normal se deduce sola
   (ver abajo).

## Qué se pide

### A. Pestaña Projects en `pi/cockpit-encargos/`

- Pestaña **Projects** entre la de las colas vivas («Ahora» / Runs) y la siguiente, con su badge (cuántos en Review
  sobre el tope). Mismo patrón de pestañas que las demás; va en la URL (`#/projects`, `#/projects?p=voz`).
- Tres vistas en un selector: **Board** (B con detalle A), **Conflicts** (matriz encargo × archivo + «Qué hacer») y
  **Flow over time** (CFD semanal, Now · Next · Later y pronóstico Monte Carlo con su tooltip de método).
- Al tocar una tarjeta de encargo: el panel con sus fases reales y un enlace que **sí funciona** a la red (Flow)
  filtrada por ese encargo (`#/flujo?e=<id>`, el filtro de la 85b), y a Traces si existe.
- Términos nuevos en `glosario.js` (los 10 de `comun/glosario-98.js`), en el mismo formato.
- El código de la maqueta se adapta al estilo de la página: nodos con `textContent` (sin `innerHTML`), tokens del
  `cockpit-comun`, sin estilos sueltos que rompan «los tokens viven en un solo lugar». Si conviene, `modelo.js` queda
  como archivo propio del paquete, con pruebas.

### B. Datos

- `proyectos.json` se lee con `cockpit.file(`${DIR}/proyectos.json`)`. Si falta o está roto, la pestaña lo dice en una
  línea y el resto de la página sigue igual.
- **Índice de encargos sin tocar el disco por escrito:** la lista de `NN-*.md` (id, slug, título de la primera línea
  `#` y fecha de modificación) con un `cockpit.spawn` de argumentos fijos (por ejemplo `find DIR -maxdepth 1 -name
  '[0-9]*-*.md' -printf …`, más la lectura del título). Si leer los títulos de 124 archivos es lento, propón un
  script fijo y de sólo lectura, como `noticias-cockpit`, que entregue el índice en JSON. Sin `sudo`.
- **Columna deducida** (y `abiertos` sólo la corrige):
  - una cola viva (`vivo/<cola>.json` en curso o pausada) en fase autor o fix → **In progress**; en fase rev → **Review**;
  - última revisión DESPLEGABLE → **Done**;
  - un `NN-*.md` sin historial y sin RESULTADO → **Ready**;
  - lo demás, como la maqueta.
  - Los encargos «nube» (aún no tienen historial en la Pi) sólo se ven si están en `abiertos`.
- **Cycle time desde que se escribió el encargo** (el riesgo 1 del 98): inicio = fecha de modificación más antigua
  conocida del `NN-*.md` o la primera fase, la que sea anterior. Se muestran las dos medidas: **lead time** (escrito →
  DESPLEGABLE) y **cycle time** (primera fase → DESPLEGABLE). Agregar «Lead time» al glosario.
- `archivos_compartidos` sigue siendo la lista de `proyectos.json`; **además**, si existe `encargos/<id>n-diff-nube.txt`
  o los diffs de la cola, propón cómo sumar los archivos de un diff sin leer su contenido (sólo los nombres de archivo
  de las cabeceras `diff --git`). Si no cabe, queda para después y lo dices.

### C. Mantenimiento de `proyectos.json`

- En `encargos/proyectos.json`, un ejemplo y las reglas en un `encargos/PROYECTOS.md` corto: cómo agregar un encargo,
  cómo moverlo, qué es `abiertos` y cuándo se borra de ahí.
- Una validación de sólo lectura (en Python, por ejemplo `encargos/proyectos_check.py`): ids repetidos entre
  proyectos, columnas que no existen, encargos del índice sin proyecto, topes WIP. Sale con rc ≠ 0 si algo está mal.
  La skill `encargar` lo va a llamar (ese cambio de la skill lo hace Claude (Diego) aparte, fuera de este encargo).

## Criterios de aceptación

- **C1** `pi/test_cockpit_paginas.py` sin fallas nuevas y con pruebas nuevas para la pestaña: el JS balanceado, los
  tokens en un solo lugar, la pestaña en la URL y que un `proyectos.json` ausente o roto no rompa la página.
- **C2** Pruebas del modelo con el `historial.jsonl` y el `proyectos.json` reales de la rama: las cifras del 98
  (throughput 7/22/19/28; encargo 19, cycle time 7,8 min; 84a, 30,7 min) salen igual. `verificar.py` (adaptado)
  compara Python contra el modelo de la página y da OK.
- **C3** La columna deducida: con un `vivo/` de prueba (una cola en rev y otra en autor), las tarjetas caen en Review
  e In progress sin estar en `abiertos`; un override en `abiertos` gana.
- **C4** `proyectos_check.py` da rc 0 con el `proyectos.json` de la rama y rc ≠ 0 con tres fixtures rotos (id
  repetido, columna inventada, JSON inválido).
- **C5** La página abierta con un `cockpit` falso (el método de siempre: `spawn` y `file` que devuelven los archivos
  reales de la rama, servido en `127.0.0.1`) se ve a 1280, 800 y 375 px, en claro y oscuro, sin desborde horizontal,
  sin errores de consola y sin pedidos fuera de `127.0.0.1`. Capturas en `encargos-nube/99-capturas/` (si pesan más de
  3 MB, sólo las de 1280 y 375).
- **C6** El enlace de una tarjeta a Flow abre la red filtrada por ese encargo.

## Invariantes

- **Root y escrituras:** la pestaña **sólo lee**. Ningún `spawn` con argumentos armados con datos; ninguna escritura
  a disco. Ningún script nuevo con `sudo`.
- **Datos hostiles:** títulos de encargos y nombres de proyecto son datos: van por `textContent`. Un `proyectos.json`
  enorme (> 1 MB), con prototipos (`__proto__`) o con tipos raros no rompe nada (objetos sin prototipo, como hace la
  página con el panel).
- **Sin red:** nada por CDN (el CSP de Cockpit lo bloquea). Una librería, si hace falta, copiada al paquete con licencia.
- **Cuentas** sólo como «Claude (Diego)», «Claude (Cami)» y «Codex».
- **El 95:** no deshagas su tooltip; si chocan, mezcla y dilo en el RESULTADO.
- **`nodo-desplegar`:** los archivos nuevos del paquete (por ejemplo `modelo.js`) y el script de índice, si nace,
  necesitan alta en el catálogo: lístalos en el RESULTADO.

## Leer primero

`CLAUDE.md`, `encargos-nube/98-proyectos-maqueta.md`, `encargos-nube/98-RESULTADO.md`, `maquetas/98-projects/NOTAS.md`
y `modelo.js`, `pi/cockpit-encargos/encargos.js` (lectura de datos, pestañas, filtro de Flow), `pi/cockpit-encargos/
glosario.js`, `pi/test_cockpit_paginas.py`, `encargos/proyectos.json`.

## No hace falta leer

`botv3/`, `encargos/cola-run.py` por dentro (sólo la forma de `--panel` y de `vivo/<cola>.json`), las otras páginas de
Cockpit salvo `cockpit-comun`.

## Fuera de alcance

- La baldosa «Projects · Now» en 🏠 Inicio (ampliación prevista: lee el mismo `proyectos.json`).
- El cambio de la skill `encargar` (lo hace Claude (Diego)).
- Instalar en la Pi, el catálogo de `nodo-desplegar` y la revisión cruzada (van en la Pi, como `cola99n`).

## Entrega

Rama propia, con el primer commit `encargos-nube/99-PLAN.md`. Al final, `encargos-nube/99-RESULTADO.md` con: lo hecho,
los archivos tocados, la salida real de las pruebas (fallas antes y después de `pi/test_cockpit_paginas.py`), las
verificaciones de C2, las capturas, los archivos que necesitan alta en el catálogo y los riesgos abiertos.
