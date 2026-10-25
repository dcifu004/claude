# Encargo 99: PLAN de la pestaña Projects en `pi/cockpit-encargos/`

Rama `claude/encargo-99-pestana-projects`, creada desde `base-99`. Se parte de `maquetas/98-projects/`
(`modelo.js`, `projects.js`, `projects.css`, `verificar.py`); las decisiones del 98 no se reabren.

## Archivos

- `pi/cockpit-encargos/modelo.js` (nuevo): el modelo de la maqueta, sin DOM, adaptado.
  - Un solo nombre arriba (`modeloProyectos`), para no chocar con los demás scripts de la página.
  - Lee `proyectos.json`, el historial, el índice de `NN-*.md` y `vivo/`.
  - Entrega lo mismo que la maqueta: tarjetas, métricas, CFD, Monte Carlo y choques.
  - Suma la columna deducida y el lead time.
  - Las semanas van en hora de Chile con `Intl` (`America/Santiago`), no con -03 fijo.
- `pi/cockpit-encargos/proyectos.js` (nuevo): las vistas, en `vistaProyectos`, como `red.js` es `redEncargos`.
  - Board B como portada; al tocar un proyecto se abre su carril A; un conmutador muestra todos los carriles.
  - Conflicts.
  - Flow over time.
  - El panel de una tarjeta, con enlaces a `#/flujo?e=<id>` y a Traces (`#/historial?e=<id>`).
  - Todo con `el()` y `textContent`.
- `encargos.js`:
  - la pestaña `projects` (botón, sección, `pintar()`, `RUTA` con `p` y `v`);
  - la lectura de `proyectos.json` (tope de 1 MB y objetos sin prototipo);
  - dos `spawn` fijos para el índice:
    - `find DIR -maxdepth 1 -name "[0-9]*-*.md" -printf "%T@ %f\n"`;
    - `find DIR -maxdepth 1 -name "[0-9]*-*.md" -exec grep -m1 -H "^# " {} +`;
  - el badge `Review n/tope`;
  - Traces preselecciona `?e=`.
- `encargos.css`: lo nuevo, con los tokens del `cockpit-comun`. Los colores propios (el CFD) van con nombres que no
  son tokens comunes y con su variante oscura, como `.uso-m*`.
- `glosario.js`: los 10 términos del 98, más «Lead time».
- `encargos/PROYECTOS.md` y `encargos/proyectos_check.py`: las reglas y la validación de sólo lectura, con rc ≠ 0 si
  algo está mal. Va con su suite `encargos/test_proyectos_check.py` y los fixtures rotos.
- `pi/test_cockpit_paginas.py`:
  - pruebas nuevas en una clase `ProyectosTests`:
    - JS balanceado;
    - tokens;
    - la ruta;
    - un `proyectos.json` ausente o roto;
    - la columna deducida con `vivo/` de prueba;
    - un espejo en Python del modelo con las cifras del 98;
    - el modelo real con node, si hay node;
  - las fijaciones que cambian porque se suma una pestaña y dos archivos JS.
- `maquetas/98-projects/verificar.py` pasa a `encargos-nube/99-verificar.py`, que compara Python contra `modelo.js`
  del paquete.
- Capturas con un `cockpit` falso, servido en `127.0.0.1`, en `encargos-nube/99-capturas/`.

## Columna deducida (orden)

1. `abiertos` del proyecto (override).
2. Cola viva (`vivo/<cola>.json`, corriendo o pausada) con esa etapa: en fase autor o fix va a In progress; en fase rev
   va a Review.
3. Si la última revisión fue DESPLEGABLE, Done.
4. Un `NN-*.md` sin historial y sin RESULTADO va a Ready.
5. Lo demás, como la maqueta:
   - con historial y sin DESPLEGABLE, Done «sin DESPLEGABLE» (fuera de throughput y cycle time);
   - sin historial y con RESULTADO, Done «sin fechas».

## Fallas de la suite antes del cambio

En esta copia la suite no importa: faltan `pi/fixtures/vivo/*.json`, como en el 95. Se corre desde una copia en el
scratchpad con esos seis archivos rellenos, y da `Ran 191 tests … FAILED (failures=16, errors=58, skipped=1)`, con 74
fallas. La lista se compara antes y después.
