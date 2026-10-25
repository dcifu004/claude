# Encargo 98: PLAN de la maqueta de la pestaña Projects

Rama `claude/encargo-98-proyectos-maqueta`, creada desde `base-98`. Todo lo nuevo va en `maquetas/98-projects/`;
no se tocan `pi/cockpit-encargos/`, `encargos/` ni `botv3/`.

## Estructura

- `index.html`: el marco de la consola v2 (riel, barra, pestañas de AI Ops con **Projects entre Runs y
  Approvals**, el mismo «Ir a», el glosario, el tema claro/oscuro y el tooltip). Se abre con `file://`.
- `comun/tokens.css` y `comun/app.css`: copiados tal cual de `98-referencia/consola-v2`. `projects.css` trae lo
  nuevo.
- `comun/glosario.js`: el de la v2, más `glosario-98.js` con Board, WIP limit, Cycle time, Throughput, Aging,
  Cumulative flow, Now/Next/Later y Forecast, en el mismo formato.
- `datos/datos-98.js`: generado por `generar-datos.py` a partir de `encargos-nube/98-datos/`, sin transformar los
  números, sólo para poder abrirlo sin servidor. Todos los cálculos se hacen en el navegador.
- `projects.js`: el modelo (asignación, columna, fechas, métricas, CFD y Monte Carlo) y las vistas. Todo con un
  constructor de nodos (`textContent`), sin `innerHTML`, para que se pueda llevar a Cockpit.
- `verificar.py`: recalcula en Python las cifras de C2 (throughput y cycle time de dos encargos) y el conteo de C3,
  y las compara con lo que muestra la página (por Playwright, si está).

## Modelo

- **Asignación** a un proyecto, en este orden:
  1. el id exacto en `encargos` o en `abiertos` del borrador;
  2. su número sin letra (`23` cubre `23a…23h`; `87n` → `87`);
  3. si no calza, Sueltos.

  Lo que calza en más de un proyecto o sólo por el número queda marcado como duda.
- **Universo de tarjetas:** los 124 del índice, más los que sólo están en el historial o en `abiertos` del
  borrador, marcados como tales.
- **Columna:** la de `abiertos` si está ahí. Si no, Done cuando la última revisión fue DESPLEGABLE. Sin historial y
  con RESULTADO, Done «anterior al historial». Lo que no calza con ninguna regla, Review con marca de duda.
- **Fechas** reales del historial: inicio = primera fase, fin = la revisión DESPLEGABLE (inicio + minutos).
  **Aging** = días desde la última fase. El umbral propuesto es 7 días (una semana de cuota).
- **Métricas:**
  - throughput: encargos que llegan a Done por semana (lunes a domingo, hora de Chile);
  - cycle time: mediana y p85 del inicio al fin;
  - rework: el criterio de `balance.py` (minutos de los fix y de las revisiones desde la segunda, sobre el total);
  - cuántos hay en Review.
- **CFD:** por semana, las tarjetas en In progress, Review y Done según las fechas del historial.
- **Pronóstico:** Monte Carlo con semilla fija, con el throughput semanal del proyecto en las últimas 8 semanas,
  sobre lo que le falta. Da 50 / 80 / 95 %. Si el proyecto tiene menos de 3 encargos terminados en esa ventana, se
  dice «datos insuficientes» y no se muestran fechas.

## Vistas

1. **Board A:** carriles por proyecto × cinco columnas, con el tope de WIP en la cabecera.
2. **Board B:** una tarjeta por proyecto con su mini-tablero (conteo por columna), una barra de avance y las
   tarjetas abiertas.
3. **Conflicts:** matriz encargo abierto × archivo compartido. Resalta los archivos con dos o más encargos
   abiertos y propone un orden de a uno.
4. **Flow over time:** el CFD en SVG propio, Now · Next · Later por proyecto y el pronóstico con su método en un
   tooltip.
5. Una baldosa **Projects · Now** para 🏠 Inicio, al final.

## Verificación

- Capturas con Chromium (Playwright) a 1280, 800 y 375 px, en claro y en oscuro, comprobando que no haya desborde
  horizontal ni errores de consola.
- `NOTAS.md` y `encargos-nube/98-RESULTADO.md`.
