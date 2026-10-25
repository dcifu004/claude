# Encargo 95: PLAN del tooltip de las colas en 🧵 Encargos

Rama `claude/encargo-95-tooltip-colas`, creada desde `base-95`.

## Diseño

- **`mencionCola(nombre)`** (una sola función, en `encargos.js`): devuelve
  `<span class="mencion-cola" data-cola="…">nombre</span>`. Un nombre válido (`COLA_VALIDA`) se escribe tal cual;
  uno que no lo es pasa por `delPanel()`. Siempre con `textContent`, vía `el()`.
- **`lineasCola(nombre, extra = [])`**: la tarjeta, como una lista de pares `[etiqueta, texto]`, sólo con lo que
  `cargar()` ya dejó en `d`. `extra` deja lista la ampliación de una cuarta línea (el primer hallazgo grave).
  1. **Qué hace:** `resumenCola(nombre)` y, si existe, `resumenEtapa(...)` de la etapa actual de esa cola.
  2. **Última fase:** si hay `vivo/<cola>.json`, `etapa · fase · cuenta · estado · dd-mm HH:MM` (con `fin` o
     `escrito`). Si no, la última fila del historial de las etapas de la cola, **por `inicio`**.
  3. **Última revisión:** la última fila `rev*` con veredicto de esas etapas, por `inicio`:
     `etapa · fase · cuenta · N,N min · VEREDICTO`, o «sin revisión todavía».
  - Etapas de una cola = las `[[etapa]]` de su manifiesto ∪ `vivo.etapas`, nunca el número del nombre
    (`cola88` → 88a, 88b, 88c; `cola9092n` → 9092n).
  - Una cola sin manifiesto ni vivo da «sin datos de esta cola».
  - Las fechas van en hora de Chile (`Intl`, `America/Santiago`), `dd-mm HH:MM`; los minutos, con coma decimal.
  - Las claves se buscan con `propio()` (`hasOwnProperty`), y los textos pasan por `unaLinea()`/`delPanel()`.
- **Tooltip:** el mismo `#term-tooltip` y el mismo patrón que `activarGlosario`. Se agrega
  `activarMenciones(raiz)`, que `activarGlosario` llama al final, para los `[data-cola]`: `aria-describedby`,
  cursor, foco y presión sostenida. Si la mención está dentro de un botón, el foco y el tooltip son del botón,
  para no anidar un enfocable dentro de otro. No se crea un segundo componente.
- CSS local en `encargos.css` (sin CDN): subrayado punteado de la mención y una línea por renglón en el tooltip.

## Inventario (grep en `base-95`)

| Lugar | Archivo:línea | Hoy |
|---|---|---|
| Ahora · cola deducida («Cola viva: …») | `encargos.js:114` | `` `Cola viva: ${v.cola}` `` |
| Ahora · colas en espera (`n: espera a, b`) | `encargos.js:112` | `` `${x.n}: espera ${x.a.join(", ")}` `` |
| Ahora · tarjeta de cola («colaNN · …») | `encargos.js:168` | `` `${m.cola} · ${titulo}` `` |
| Carga vs. capacidad · cabeceras | `encargos.js:258` | `delPanel(c.cola)` |
| Carga vs. capacidad · leyenda de proyectadas | `encargos.js:274` | `proy.map(p => delPanel(p.cola))` |
| Carga vs. capacidad · `colas_fuera` | `encargos.js:283` | `el("strong", {}, delPanel(x.cola))` |
| Capacidad por vencer · «caben: …» | `encargos.js:294` | `x.colas_que_caben.map(delPanel)` |
| Despacho · autorizadas | `encargos.js:359` | `autorizadas.join(", ")` |
| Resultado de la acción | `encargos.js:466` | `` `${delPanel(r.cola)}: ` `` |
| Flow (red) · franja Ahora | `red.js:345-350` | botón con `` `${cola} · ${fase}` `` |

Fuera del inventario, con su motivo:

- **Historial/Traces** (`hist()`, `filaHistorial`) y **Timeline** (`tiempo()`): pintan el *encargo* (etapa), no
  el nombre de la cola.
- **Bitácora:** es el texto crudo de `COLA-ESTADO.md` en un `<pre>`. El nombre no es un dato aparte.
- **`confirm()`/`prompt()`** (`textoConfirmacion`, `textoAutorizar`): son diálogos nativos de texto, donde no
  cabe un tooltip.
- **Buscador Ctrl+K** (`encargos.js:928`): no está en la lista del encargo y ya muestra el resumen junto al
  nombre.
- **Red, `<title>`:** la red no tiene nodo de cola (sus capas son cuenta, modelo, naturaleza/rol, encargo y
  resultado). La cola sólo aparece en la franja Ahora, que entra al inventario.

## Pruebas

- En `pi/test_cockpit_paginas.py`, clase `ConsolaEncargosTests`:
  - espejo en Python de `lineasCola`, como las que ya hay;
  - fijación de la fuente (C2, C3 y C4);
  - una prueba que corre el JS real con `node` cuando está disponible (en la Pi se salta).
- Fixtures: `encargos-nube/95-fixtures/` (manifiestos e historial reales). **No trae `vivo/`**, así que el
  «detenida» del C1 sale de un vivo armado en la prueba con la forma del real `pi/fixtures/vivo-cola85-85b.json`,
  y queda anotado.
- Línea base: en esta copia la suite no se importa (falta `pi/fixtures/vivo/*.json`). Se corre en una copia del
  scratchpad con esos cuatro archivos rellenos (fuera del repo), y se compara la lista de fallas antes y después.
