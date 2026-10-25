# Maqueta 98: pestaña Projects de 🏭 AI Ops

Hecha por Claude (Diego) en la nube el 25-10-2026, sobre el marco de la consola v2.

Abre `index.html` con doble clic. Funciona con `file://`, sin servidor y sin nada de internet. La pestaña
**Projects** queda entre Runs y Approvals. Las demás pestañas de la barra son marcadores: el resto de la consola está
en la maqueta v2.

## Qué hace cada vista

Arriba de todas las vistas va la **franja de KPI**:

- **Throughput:** encargos terminados por semana.
- **Cycle time:** mediana y p85.
- **Rework rate:** el criterio de `balance.py`.
- **WIP limit:** cuántas tarjetas hay en Review contra su tope; se pone en rojo si se pasa.

Más abajo hay un selector de tres vistas.

1. **Board**, con dos alternativas (A y B) y el filtro **Sólo abiertos / Todo**:
   - Las cabeceras muestran `n/tope` en rojo cuando se pasa el tope: hoy In progress está en 4/2 y Review en 6/3.
   - Las tarjetas llevan su número, el título corto y estas marcas:
     - «nube»;
     - «bloqueado», cuando el bloqueo del proyecto nombra la tarjeta;
     - aging en días, en rojo desde **7 días**, que es una semana de cuota;
     - «duda»;
     - «sin DESPL.».
   - Al tocar una tarjeta se abre el panel con sus fases reales (fecha, cuenta, minutos y veredicto) y el enlace
     simulado «Ver en Flow · encargo N».
   - Debajo del tablero va el plegable **Dudas sobre el borrador**.
2. **Conflicts:** una **matriz encargo × archivo**, con las filas agrupadas por proyecto (proyecto → encargo → archivo).
   - Los archivos que tocan dos o más encargos abiertos quedan en rojo.
   - Al lado va «Qué hacer»: el orden de a uno por archivo y un orden para todo.
   - La regla del orden: primero Review, después In progress, Ready e Idea; a igual columna, por número.
3. **Flow over time:**
   - El **CFD** semanal: columnas apiladas con In progress, Review, Done y «Cerrado sin DESPLEGABLE» (rayado). Tiene
     tooltip por tramo, etiquetas directas en la última semana y una tabla.
   - **Now · Next · Later** por proyecto. Later suma las ideas del borrador.
   - El **pronóstico Monte Carlo** por proyecto: «50 % / 80 % / 95 % → N semanas», con el método en el tooltip «ⓘ
     método». Si un proyecto no tiene datos suficientes, lo dice y no da fechas.

Al final de la página va la **baldosa «Projects · Now»** para 🏠 Home. Es un ejemplo.

El **glosario** (`comun/glosario-98.js`) suma estos términos al de la v2, que se copió tal cual:

- Projects;
- Board;
- WIP limit;
- Cycle time;
- Throughput;
- Aging;
- Cumulative flow;
- Now/Next/Later;
- Forecast;
- Conflicts.

## Las dos alternativas del Board

- **A · carriles:** un carril por proyecto, con su nombre y su resultado en una línea, cruzado con las cinco
  columnas. Es el tablero clásico: sirve para ver el WIP y las tarjetas atascadas.
  - Bajo 1100 px, el nombre del proyecto sube sobre las columnas.
  - Bajo 720 px, cada carril se apila: sólo aparecen las columnas con tarjetas, cada una con su rótulo.
  - Con «Todo», el Done muestra las 4 más recientes y un botón «+N más».
- **B · proyectos:** una tarjeta por proyecto, con su resultado, un mini-tablero (el conteo por columna), una barra de
  avance (Done sobre el total), el rework y las tarjetas abiertas. También muestra el bloqueo y el pronóstico al 80 %.
  Sirve para ver el **portafolio**: qué proyecto avanza, cuál está bloqueado y cuál está quieto.

Mi recomendación: **B como portada y A como detalle**. Con 12 proyectos y sólo 13 tarjetas abiertas, A es casi todo
celdas vacías; B se lee en una pantalla.

## Datos reales y datos de ejemplo

- **Reales** (`encargos-nube/98-datos/`, copiados a `datos/datos-98.js` por `generar-datos.py`, sin cambiar números):
  - las fases, fechas, minutos, cuentas y veredictos de `historial.jsonl`;
  - el id, el título y la cantidad de RESULTADO de `encargos-index.json`; nada de adentro de los RESULTADO;
  - los proyectos, resultados, columnas abiertas, ideas, bloqueos y archivos compartidos del **borrador**.

  Todos los cálculos se hacen en `modelo.js`, en el navegador.
- **De ejemplo o simulado:**
  - el enlace a Flow;
  - la baldosa de Home;
  - las demás pestañas de la barra.
- **Reloj:** «ahora» es la última fase del historial (25-10 17:36), para que la maqueta muestre siempre lo mismo.

## Reglas del modelo

- **Proyecto**, en este orden:
  1. el id exacto en `encargos` o `abiertos` del borrador;
  2. su número sin letra («un número sin letra cubre sus variantes»);
  3. si no calza, Sueltos.

  No se reasigna nada: lo dudoso lleva la marca «duda».
- **Universo:** hay **142 tarjetas**:
  - los 124 del índice;
  - 12 que sólo están en el historial: 36, 40, 53, 60, 87, 47b, 48b, 57b, 87n, 91n, 93n y 9092n;
  - 6 que sólo están en el borrador: 88, 95, 96, 97, 98 y 87b.
- **Columna:**
  - manda la de `abiertos`;
  - si no está ahí y su última revisión fue DESPLEGABLE, va a Done con fecha;
  - si no está en `abiertos` pero su última revisión no fue DESPLEGABLE, va a Done con la marca **«sin DESPLEGABLE»**
    y queda fuera del throughput y del cycle time;
  - si no tiene fases pero sí RESULTADO, va a Done «sin fechas»: son los anteriores al historial y algunos de la
    nube.
- **Cycle time:** de la primera fase al fin de la revisión DESPLEGABLE. **Throughput:** semanas de lunes a domingo en
  hora de Chile, contadas por el fin de esa revisión.
- **Rework:** minutos de `fix*` y de `rev2` en adelante, sobre el total.
- **Pronóstico:**
  - 10.000 corridas con la semilla fija 98;
  - cada semana futura toma al azar una de las últimas semanas reales del proyecto (como máximo 8; hoy hay 4);
  - corre hasta cubrir Ready + In progress + Review;
  - si el proyecto tiene menos de 3 encargos terminados en la ventana, dice «datos insuficientes» y no da fechas.

## Lo que hay que saber de los números

- **El cycle time mide la cola, no el encargo.** Cada encargo corre de una vez (autor → rev → fix), así que la mediana
  da **29 min** y el p85 **3,5 h**. Para que sirva como métrica ágil, el inicio tendría que ser la fecha en que se
  escribió el encargo. Hoy esa fecha sólo está dentro del título; el `proyectos.toml` real podría traerla como campo.
- **El historial parte el 03-10.** Por eso la primera semana (28-09) tiene sólo dos días, la ventana del pronóstico
  es de 4 semanas y no de 8, y 33 encargos quedan en Done «sin fechas».
- **20 encargos están cerrados sin DESPLEGABLE.** Agotaron sus 3 revisiones o los cerró otro encargo (22 → 22b y 22c,
  33 → 33b → 82). El borrador no lo dice. Se muestran rayados en el CFD.

## Dudas sobre la asignación del borrador

Las marco en la maqueta; ninguna se movió.

1. **Sin proyecto:** 75 (el aviso programado del clima, que va con 69, 74 y 76 en bot) y 78a (changedetection y
   SearXNG; 78b está en bot). También 36, 40 y 60, que no tienen ficha en el índice.
2. **Parecen mal puestos, a juzgar por el título:**
   - 07 (ruta `noticias`) y 39b (mandar un archivo por Telegram), que están en Sueltos: ¿van a bot?
   - 90 (`/uso` como imagen), que está en cuentas: ¿va a bot, junto con su revisión 9092n?
   - 80b (la ruta web del bot), que está en cuentas: ¿va a bot?
   - 83 (aviso de quema de cupo), que está en encargos: ¿va a cuentas?
   - 20, 31 y 34 (páginas de 🧵 Encargos), que están en encargos o cuentas: ¿van a consola?
3. **Familias repartidas entre proyectos (puede estar bien):**
   - 06 en cuentas, voz y seguridad;
   - 22 en consola y seguridad;
   - 23 en encargos y consola;
   - 27 en seguridad y encargos;
   - 36 en seguridad y Sueltos;
   - 39 en huerta y Sueltos;
   - 48 en cuentas y encargos;
   - 78 en Sueltos y bot;
   - 80 en seguridad y cuentas.
4. **87 queda en Done (rayado)** porque su último veredicto fue PLAN RECHAZADO y no está en `abiertos`. Su trabajo
   sigue en 87b (Review). ¿Hay que poner `"87": "Review"` en `abiertos`?
5. **88 en Review** es una tarjeta de familia sin ficha. 88a quedó NO DESPLEGABLE y 88b y 88c en Done.
6. **Ids del borrador sin ninguna fila de datos:** 95, 96, 97, 98 y 87b sólo existen en `abiertos`. Además, el borrador
   de luces lista «57», que no existe pelado: cubre 57a y 57b.
7. **83 está en Ready**, aunque el historial lo muestra con un fix2 corriendo. Gana el borrador, como pide su nota.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | El marco de la consola y la pestaña. |
| `projects.css` | Lo nuevo. Los colores del CFD se validaron para daltonismo en claro y en oscuro. |
| `comun/` | `tokens.css`, `app.css` y `glosario.js` de la v2, sin cambios, más `glosario-98.js`. |
| `modelo.js` | El modelo, sin DOM. |
| `projects.js` | Las vistas, armadas con nodos y `textContent`, sin `innerHTML` (para el CSP de Cockpit). |
| `datos/datos-98.js` | Generado por `generar-datos.py`. |
| `verificar.py` | Recalcula C2 y C3 en Python y los compara con `modelo.js`. |
| `capturar.js` | Saca las 42 capturas de `capturas/` y falla si hay un error de consola, un pedido de red o desborde horizontal. |

## Para llevarlo a Cockpit

- Leer un `proyectos.toml` del vault con la forma del borrador, en vez de `datos-98.js`.
- El historial y el índice salen de la API de la Pi.
- Agregar la fecha de creación del encargo, para que el cycle time sea útil.
- Completar `archivos_compartidos` con los diffs reales.
