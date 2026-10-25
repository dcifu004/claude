# Encargo 98: maqueta de la pestaña Projects de 🏭 AI Ops (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `pagina` (maqueta, no se instala). **Rama base: `base-98`.** Es una **maqueta estática** para que Diego
elija, como las maquetas A/B/C y v2 de la consola. No toca `pi/cockpit-encargos/`.

## Para qué

Los encargos viven sueltos: hay 124 en `encargos/` y el historial no tiene un campo de proyecto. Lo que los une
(doc 34 → 66 a 69, nota 25 → 35, 75, 96 y 97) sólo está en los documentos. Diego quiere una vista que **agrupe los
encargos por proyecto** y les dé **orden y cronograma**, para que no sean encargos sueltos.

## Decisiones de Diego (25-10, cerradas)

Diego tomó las recomendaciones de un experto en IA y de uno en proyectos ágiles:

1. **Primero los datos, después el dibujo.** Tres niveles: proyecto → plan o doc → encargo.
2. **Kanban, no Scrum**, con la semana de la cuota como ciclo. Un solo tablero con columnas
   **Idea → Ready → In progress → Review → Done** y **tope de trabajo en curso** (In progress 2, Review 3).
3. **Cada proyecto se define por su resultado** en una frase, no por su lista de tareas.
4. **No hay Gantt con fechas futuras**: el pasado va con fechas reales del historial; el futuro va como
   **Now · Next · Later** y con un **pronóstico probabilístico** basado en el rendimiento real («80 % de probabilidad
   de terminar en N semanas»). Las duraciones del `--simular` no distinguen el tamaño de un encargo: no se usan para
   fechar.
5. **Mapa de choques:** proyecto → encargo → archivos tocados, para ver qué encargos se pisan antes de lanzar.
6. **Métricas de flujo:** throughput semanal, cycle time, aging (lo quieto en rojo) y rework (ya existe en
   `balance.py`).
7. **Vive en la consola**, como pestaña **Projects** de 🏭 AI Ops, entre Runs y Approvals, con la barra única de la
   consola v2. Etiquetas en inglés con tooltip en español y en el glosario (D5 del plan de la consola v2).

## Datos (en `encargos-nube/98-datos/`)

- `historial.jsonl`: las 397 fases reales, con encargo, fase, rol, cuenta, modelo, inicio, minutos, veredicto,
  % de cuota y pronóstico. Sin texto libre.
- `encargos-index.json`: los 124 encargos con su número, slug, título y los `RESULTADO` que existen.
- `proyectos-borrador.json`: **el borrador de la Fase 0**. 12 proyectos con resultado, docs, encargos, la columna de
  lo abierto, ideas, bloqueos y archivos compartidos conocidos. **Es un borrador para que Diego lo revise sobre la
  maqueta**: no lo trates como verdad. Si ves un encargo que parece mal asignado, márcalo en la maqueta y anótalo en
  el RESULTADO; no lo reasignes en silencio.

## Referencia visual (en `encargos-nube/98-referencia/consola-v2/`)

La maqueta v2 de la consola (Codex, 24-10), con su `comun/` (estilo, `glosario.js`, datos) y sus `NOTAS.md`. **La
pestaña Projects tiene que verse como parte de esa consola:** la misma barra, la misma tipografía, los mismos tokens
de color, el modo claro y oscuro y el mismo comportamiento por ancho. También sirve mirar
`pi/cockpit-encargos/` (la consola instalada, la 84), sin modificarla.

## Qué se pide

Una carpeta `maquetas/98-projects/` con un `index.html` que abre directo (sin servidor; si hace falta, los datos van
transformados a un `.js`). Dentro de la barra de AI Ops, la pestaña Projects con un selector de tres vistas.

1. **Board.** Kanban con un carril por proyecto (nombre + resultado en una línea) y las cinco columnas. La cabecera de
   cada columna muestra el tope (`6/3` en rojo si se pasa). Las tarjetas muestran el número, el título corto y,
   si aplica, «nube», «bloqueado» o los días sin moverse (aging, en rojo pasado un umbral que propongas). Al tocar
   una tarjeta, se abre un panel con sus fases reales del historial (fechas, minutos, veredictos) y un enlace
   simulado a Flow filtrado por ese encargo. Arriba, la franja de KPI: throughput por semana, cycle time, rework y
   cuántos están en Review. Un filtro «Sólo abiertos / Todo».
2. **Conflicts.** El mapa proyecto → encargo → archivo, con los archivos que tocan dos o más encargos abiertos
   resaltados y una línea de qué hacer («traer de a uno: 96 → 97»). Propón la forma: red de tres capas como la de
   Flow, matriz encargo × archivo o lista. Explica en el RESULTADO por qué elegiste esa.
3. **Flow over time.** Diagrama de flujo acumulado por semana (columnas apiladas en el tiempo), construido con el
   historial. Debajo, **Now · Next · Later** por proyecto y el **pronóstico probabilístico** por proyecto (Monte Carlo
   con el throughput de las últimas semanas sobre lo que falta de cada proyecto), mostrado como «50 % / 80 % / 95 %
   → N semanas». Si los datos no alcanzan para un proyecto, dilo en la tarjeta en vez de inventar.

**Dos alternativas de Board**: (A) carriles por proyecto con columnas (el tablero clásico) y (B) lo que propongas
(por ejemplo, tarjetas de proyecto con su mini-tablero y su barra de avance). Diego elige al verlas.

Además:
- **Home:** una baldosa de ejemplo «Projects · Now» para 🏠 Inicio, en la misma página de la maqueta, al final.
- **Glosario:** Board, WIP limit, Cycle time, Throughput, Aging, Cumulative flow, Now/Next/Later y Forecast, con una
  definición corta en español, en el mismo formato que `glosario.js`.

## Criterios de aceptación

- **C1** Se abre con doble clic (`file://`), sin errores en la consola del navegador y sin pedir nada a internet
  (todo local, nada por CDN: en Cockpit el CSP lo bloquea).
- **C2** Los números salen de `98-datos/`: el throughput, el cycle time y las fechas de las tarjetas coinciden con
  `historial.jsonl` (deja en el RESULTADO dos verificaciones a mano, con el encargo y la cifra).
- **C3** Todos los encargos del índice aparecen en algún proyecto o en «Sueltos»: ninguno se pierde (comprueba el
  conteo y anótalo).
- **C4** Se ve bien a 1280, 800 y 375 px, en modo claro y oscuro, sin desborde horizontal de la página. Deja capturas en
  `maquetas/98-projects/capturas/` si puedes generarlas; si no, dilo.
- **C5** El pronóstico probabilístico explica su método en un tooltip y no muestra fechas para proyectos sin datos
  suficientes.
- **C6** `NOTAS.md` en la carpeta: qué hace cada vista, qué datos son reales y cuáles de ejemplo, las dos
  alternativas del Board y **las dudas sobre la asignación del borrador** (encargos que parecen mal puestos).

## Reglas

- **No tocar** `pi/cockpit-encargos/`, `encargos/` ni `botv3/`. Todo lo nuevo va en `maquetas/98-projects/`.
- Sin texto libre de los encargos más allá del título (nada de los `RESULTADO` por dentro).
- Sin dependencias externas; si usas una librería, va copiada en `maquetas/98-projects/vendor/` con su licencia.
- Mostrar las cuentas sólo como «Claude (Diego)», «Claude (Cami)» y «Codex».

## Fuera de alcance

- Instalar en Cockpit, el adaptador `fuente.js` y la API de la Pi (ampliación prevista: la pestaña real leerá un
  `proyectos.toml` del vault, con la misma forma que `proyectos-borrador.json`).
- Que la skill `encargar` pida el proyecto de cada encargo nuevo.
- Cambiar el historial o `cola-run.py`.

## Entrega

Rama propia, con el primer commit `encargos-nube/98-PLAN.md`. Al final, `encargos-nube/98-RESULTADO.md` con: lo hecho,
las dos alternativas del Board, las verificaciones de C2 y C3, el estado de C4 y las dudas sobre la asignación del
borrador.
