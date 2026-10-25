# Encargo 98: RESULTADO (maqueta de la pestaña Projects)

Hecho por Claude (Diego) en la nube el 25-10-2026, en la rama `claude/encargo-98-proyectos-maqueta`, creada desde
`base-98`.

## Lo hecho

La carpeta `maquetas/98-projects/` trae la pestaña **Projects** de 🏭 AI Ops, entre Runs y Approvals, dentro del marco
de la consola v2: el mismo riel, la misma barra, los mismos tokens, «Ir a», el glosario, el tema claro u oscuro y el
comportamiento por ancho. Abre con doble clic. Qué hace cada vista y las reglas del modelo están en
`maquetas/98-projects/NOTAS.md`.

- **Board** en dos alternativas, con la franja de KPI, los topes de WIP y las marcas de las tarjetas. Al tocar una
  tarjeta se abre el panel con sus fases reales y el enlace simulado a Flow. Tiene el filtro «Sólo abiertos / Todo».
- **Conflicts:** la matriz encargo × archivo y «Qué hacer», con el orden de a uno.
- **Flow over time:** el CFD semanal, Now · Next · Later y el pronóstico Monte Carlo por proyecto.
- La baldosa «Projects · Now» para 🏠 Home, al final de la página, y 10 términos nuevos en el glosario.

## Archivos

Todo lo nuevo está en `maquetas/98-projects/`, más este RESULTADO y el PLAN:

- `index.html`;
- `projects.css`;
- `projects.js`;
- `modelo.js`;
- `comun/` (tokens, `app.css` y glosario de la v2 copiados sin cambios, más `comun/glosario-98.js`);
- `datos/datos-98.js` y `generar-datos.py`;
- `verificar.py`;
- `capturar.js`;
- `NOTAS.md`;
- `capturas/` (42 PNG).

No toqué `pi/cockpit-encargos/`, `encargos/` ni `botv3/`. `git diff --stat origin/base-98`, sin contar `maquetas/` y
el PLAN, sale vacío.

## Las dos alternativas del Board

- **A · carriles:** un carril por proyecto cruzado con Idea → Ready → In progress → Review → Done. La cabecera muestra
  `n/tope`, en rojo cuando se pasa: hoy In progress está en **4/2** y Review en **6/3**. En el teléfono, cada carril se
  apila y muestra sólo las columnas que tienen tarjetas.
- **B · proyectos:** una tarjeta por proyecto con su resultado, un mini-tablero de cinco conteos, la barra de avance, el
  rework, las tarjetas abiertas, el bloqueo y el pronóstico al 80 %.
- **Recomendación:** B como portada y A como detalle. Con 12 proyectos y 13 tarjetas abiertas, A es casi todo celdas
  vacías.

**Por qué una matriz en Conflicts:** hay 5 archivos y 12 encargos. La matriz muestra el cruce de un vistazo. La red
de tres capas cruzaría líneas sin aportar nada, y una lista pierde la vista del cruce. La lista igual está al lado, en
«Qué hacer», que es lo que se lee en el teléfono (ahí la matriz tiene scroll propio).

## C1: abre con file://, sin errores y sin red

`node maquetas/98-projects/capturar.js` abre la página por `file://` en Chromium y recorre 5 vistas, el panel de una
tarjeta y el tooltip del pronóstico, a 3 anchos y en los 2 temas. Falla si hay un error o advertencia de consola, un
pedido que no sea `file://` o desborde horizontal. Salida real:

```
42 capturas en capturas/
sin errores de consola, sin pedidos de red y sin desborde horizontal
```

No hay CDN ni dependencias. Tampoco hay `innerHTML` ni estilos inline: los estilos van por CSSOM.

## C2: los números salen del historial

`python3 maquetas/98-projects/verificar.py` recalcula todo en Python, sin `modelo.js`, y lo compara con lo que calcula
la página. Salida real:

```
== C2: dos encargos a mano ==
  19 autor inicio 2026-10-03T18:20:35-03:00    4.5 min  —
  19 rev1  inicio 2026-10-03T18:25:02-03:00    3.3 min  DESPLEGABLE
  → primera fase 03-10 18:20, DESPLEGABLE termina 03-10 18:28, cycle time 7.8 min, cuenta en la semana del 28-09
  84a autor inicio 2026-10-24T11:57:29-03:00   18.7 min  —
  84a rev1  inicio 2026-10-24T12:16:12-03:00    5.4 min  NO DESPLEGABLE
  84a fix1  inicio 2026-10-24T12:21:39-03:00    2.6 min  —
  84a rev2  inicio 2026-10-24T12:24:19-03:00    3.9 min  DESPLEGABLE
  → primera fase 24-10 11:57, DESPLEGABLE termina 24-10 12:28, cycle time 30.7 min, cuenta en la semana del 19-10
== C2: throughput por semana (lunes, hora de Chile) ==
  28-09: 7
  05-10: 22
  12-10: 19
  19-10: 28
  76 encargos terminados · media 19.00/sem · cycle time mediana 29.5 min
== C3: cobertura del índice ==
  índice 124 · con proyecto 115 · en Sueltos 9 · perdidos 0
== Página (modelo.js) ==
  semanas ['28-09', '05-10', '12-10', '19-10'] · throughput [7, 22, 19, 28] · c3 124/124, en Sueltos 9
OK: Python y la página dan lo mismo
```

Las dos verificaciones a mano:

- **Encargo 19.** 18:25:02 + 3,3 min = 18:28:20 del 03-10, que cae en la semana del 28-09. Cycle time: 18:20:35 →
  18:28:20, o sea **7,8 min**.
- **Encargo 84a.** 12:24:19 + 3,9 min = 12:28:13 del 24-10, en la semana del 19-10. Cycle time: 11:57:29 → 12:28:13, o
  sea **30,7 min**. Su rework es fix1 + rev2: 6,5 de 30,6 min.

La página muestra en el KPI **19/sem** (media de 4 semanas; esta semana, 28) y **29 min** de mediana. El panel de cada
tarjeta da las mismas fechas.

## C3: ningún encargo se pierde

Los **124 del índice** aparecen: 115 en un proyecto y 9 en Sueltos. La maqueta suma **18 tarjetas** que no están en el
índice:

- 12 que sólo están en el historial: 36, 40, 53, 60, 87, 47b, 48b, 57b, 87n, 91n, 93n y 9092n;
- 6 que sólo están en `abiertos`: 88, 95, 96, 97, 98 y 87b.

En total son **142 tarjetas**.

## C4: anchos y temas

En `maquetas/98-projects/capturas/` quedaron **42 capturas**:

- `{board-a, board-a-todo, board-b, conflicts, flow, panel, forecast-tooltip}-{1280, 800, 375}-{light, dark}.png`;
- todas sin desborde horizontal de la página;
- la matriz de Conflicts y el CFD tienen scroll propio en el teléfono.

Las revisé a ojo. En la primera tanda encontré tres problemas y los arreglé:

- el riel aparecía abierto, porque la transición del hover seguía activa al capturar;
- en el panel salía «nullnull»;
- la columna Veredicto quedaba angosta a 375 px.

Los colores del CFD pasaron el validador de daltonismo. En claro pasa entero. En oscuro queda un aviso en el par Done ↔
Review (ΔE 7,1, en la banda 6 a 8). Esa banda se permite con codificación secundaria, y el CFD la tiene: leyenda,
etiquetas directas, tabla y separación entre tramos.

## C5: el pronóstico explica su método

El «ⓘ método» de cada tarjeta abre un tooltip con el método: Monte Carlo, 10.000 corridas con semilla fija, las semanas
reales que usa, lo que falta, y que con menos de 3 terminados no pronostica. `capturar.js` comprueba que el tooltip diga
«Monte Carlo».

| Proyecto | Pronóstico (50 / 80 / 95 %) |
|---|---|
| Encargos y cola | 1 / 1 / 1 semanas |
| Consola de Cockpit | 1 / 2 / 4 |
| Bot y comandos | 1 / 3 / 5 |
| Seguridad y acceso | 2 / 2 / 4 |
| Asistente de voz | datos insuficientes, sin fechas (2 terminados) |
| Música (Spotify) | datos insuficientes, sin fechas (2 terminados) |
| Temblores | datos insuficientes, sin fechas (0 terminados) |

## C6: NOTAS.md

`maquetas/98-projects/NOTAS.md` explica qué hace cada vista, qué datos son reales y cuáles de ejemplo, las dos
alternativas del Board, las reglas del modelo y las dudas sobre el borrador.

## Dudas sobre la asignación del borrador

En la maqueta van con la marca «duda» y no se reasignaron.

1. **Sin proyecto:** 75 (aviso programado del clima: ¿va a bot, con 69, 74 y 76?) y 78a (changedetection y SearXNG; 78b
   está en bot). También 36, 40 y 60, que no tienen ficha en el índice.
2. **Parecen mal puestos:**

   | Encargo | Está en | ¿Debería ir en? |
   |---|---|---|
   | 07, 39b | Sueltos | bot |
   | 90 | cuentas | bot (su revisión 9092n está en bot) |
   | 80b | cuentas | bot |
   | 83 | encargos | cuentas |
   | 20, 31, 34 | encargos o cuentas | consola (son páginas de 🧵 Encargos) |

3. **Familias repartidas entre proyectos.** Pueden estar bien:
   - 06 en cuentas, voz y seguridad;
   - 22 en consola y seguridad;
   - 23 en encargos y consola;
   - 27 en seguridad y encargos;
   - 36 en seguridad y Sueltos;
   - 39 en huerta y Sueltos;
   - 48 en cuentas y encargos;
   - 78 en Sueltos y bot;
   - 80 en seguridad y cuentas.
4. **87 queda en Done con la marca «sin DESPLEGABLE»:** su último veredicto fue PLAN RECHAZADO y no está en
   `abiertos`, aunque sigue vivo en 87b. ¿Agregar `"87"` a `abiertos`?
5. **20 encargos están cerrados sin DESPLEGABLE:** no están en `abiertos` y su última revisión fue NO DESPLEGABLE,
   PLAN RECHAZADO en el caso de 87. Son 22, 23c, 23d, 27, 32b, 33, 33b, 36, 46a, 47b, 48, 51, 52, 56, 57b, 60, 87,
   87n, 88a y 91n. La nota del borrador no dice qué hacer con ellos. Los dejé en Done con esa marca, fuera del
   throughput y del cycle time, y rayados en el CFD.
6. **Ids del borrador sin datos:** 95, 96, 97, 98 y 87b sólo existen en `abiertos`. «57» en luces no existe pelado;
   cubre 57a y 57b. 83 está en Ready aunque el historial lo muestra con fix2: gana el borrador.

## Decisiones

- **«Ahora» = la última fase del historial** (25-10 17:36), para que la maqueta sea reproducible.
- **Umbral de aging: 7 días**, una semana de cuota. Hoy ninguna tarjeta abierta lo pasa: la más quieta es 36b, con 1
  día.
- **«nube»** se marca cuando el título dice «en la nube» o el id termina en `n`. Para 95, 96, 97, 98 y 87b los datos
  no lo dicen, así que no llevan la marca.
- **Cerrados sin DESPLEGABLE:** van a Done marcados y no a Review, porque el borrador dice que `abiertos` fija lo que no
  está desplegado. Si fueran a Review, la columna se iría a 26/3 y taparía lo que de verdad está abierto.
- **Títulos cortos:** se quitan «Encargo N —», la fecha y el paréntesis del autor, así las cuentas no aparecen en las
  tarjetas. En el panel, las cuentas van sólo como «Claude (Diego)», «Claude (Cami)» y «Codex».

## Riesgos abiertos

- **El cycle time mide la cola, no el encargo.** La mediana da 29 min, porque cada encargo corre de una vez. Para que
  sea útil, el `proyectos.toml` real tendría que traer la fecha en que se escribió el encargo.
- **El historial parte el 03-10.** La ventana del pronóstico es de 4 semanas y no de 8, y la primera semana tiene sólo
  2 días. Con más historia, los pronósticos cambian.
- **`archivos_compartidos` es la lista a mano del borrador.** No leí diffs, así que puede faltar algún choque.
- **Pruebas del repo:** este encargo no toca código con suite (`botv3/`, `pi/` ni `encargos/`), así que no hay
  fallas que comparar antes y después. Las verificaciones son `verificar.py` y `capturar.js`, con la salida de arriba.
- **Las capturas pesan 9,4 MB.** Si estorban en el repo, se pueden regenerar con `capturar.js`.
