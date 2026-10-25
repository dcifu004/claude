# Encargo 95: RESULTADO del tooltip de las colas en 🧵 Encargos

Rama `claude/encargo-95-tooltip-colas`, creada desde `base-95`. Plan en `95-PLAN.md`.

## Lo hecho

- **`mencionCola(nombre)`** (`pi/cockpit-encargos/encargos.js:98`): la única función que pinta el nombre de una
  cola. Devuelve un `<span class="mencion-cola" data-cola="…">` armado con `el()`, es decir con `textContent`. Un
  nombre válido (`COLA_VALIDA`) va tal cual; uno que no lo es pasa por `delPanel()`.
- **`lineasCola(nombre, extra = [])`** (`encargos.js:116`): la tarjeta como pares `[etiqueta, texto]`. Usa sólo
  lo que `cargar()` ya deja en `d` (no hay lecturas nuevas):
  1. **Qué hace:** `resumenCola()` y, si existe, ` · etapa <id>: ` con el `resumenEtapa()` de la etapa actual.
  2. **Última fase:** con vivo, `etapa · fase · cuenta · estado · dd-mm HH:MM` (`fin` o `escrito`). Sin vivo, la
     última fila del historial de esas etapas, **por `inicio`**.
  3. **Última revisión:** la última fila `rev` con veredicto, por `inicio`:
     `etapa · fase · cuenta · N,N min · VEREDICTO`, o «sin revisión todavía».

  Las etapas de una cola son las `[[etapa]]` de su manifiesto más `vivo.etapas`, nunca el número del nombre. Una
  cola sin manifiesto ni vivo da «sin datos de esta cola». Las fechas van en hora de Chile
  (`Intl.DateTimeFormat`, `America/Santiago`) y los minutos con coma. Las claves se buscan con `propio()`, y cada
  línea se corta en 180 caracteres. `extra` deja lista la cuarta línea de la ampliación (el primer hallazgo
  grave), sin otro cambio.
- **Tooltip:** es el mismo `#term-tooltip` del glosario y el mismo patrón. `activarGlosario` termina llamando a
  `activarMenciones(raiz)` (`encargos.js:1024`, `:1033`): `aria-describedby="term-tooltip"`, cursor, foco y
  presión sostenida de 450 ms. `mostrarCola` (`:1028`) llena el tooltip con `el()`. Si la mención está dentro de
  un botón (la franja de Flow), el foco y el tooltip son del botón, para no anidar un enfocable en otro. **No hay un
  segundo componente.** La definición vive en `encargos.js`, junto a `activarGlosario`, que es donde ya estaba el
  componente; `glosario.js` sólo trae los términos.
- **CSS local** (`encargos.css`): una línea por renglón en el tooltip y el subrayado punteado de la mención. No hay
  CDN ni estilos en línea, y no se tocó `cockpit-comun`.

## Inventario: cada lugar con su línea

| Lugar | Línea |
|---|---|
| Ahora · cola deducida («Cola viva: …») | `encargos.js:152` |
| Ahora · colas en espera («colaNN: espera colaMM») | `encargos.js:150` |
| Ahora · tarjeta de cola («colaNN · …») | `encargos.js:206` |
| Carga vs. capacidad · cabeceras de la matriz | `encargos.js:296` |
| Carga vs. capacidad · leyenda «incluye carga proyectada» | `encargos.js:312` |
| Carga vs. capacidad · `colas_fuera` | `encargos.js:321` |
| Capacidad por vencer · «caben: …» | `encargos.js:332` |
| Despacho · autorizadas | `encargos.js:400` |
| Resultado de las acciones | `encargos.js:505` (Despacho no es una cola: queda como texto) |
| Flow (red) · franja Ahora | `red.js:351` y `activarGlosario(S.franja)` en `:355` |

Fuera del inventario, con su motivo (detalle en el PLAN):

- **Historial/Traces y Timeline:** pintan el encargo, no la cola.
- **Bitácora:** texto crudo de `COLA-ESTADO.md`; el nombre no es un dato aparte.
- **`confirm()`/`prompt()`:** diálogos nativos, donde no cabe un tooltip.
- **Buscador Ctrl+K:** no estaba en la lista y ya muestra el resumen junto al nombre.
- **Red, `<title>` de un nodo de cola:** la red no tiene nodos de cola (sus capas son cuenta, modelo,
  naturaleza/rol, encargo y resultado). La cola sólo aparece en la franja, que sí está cubierta.

La pastilla de la franja perdió su `title="Elegir este encargo"`: con el tooltip nuevo habrían salido dos encima.
La nota de la franja («Toca una cola para ver su camino.») sigue diciendo para qué sirve.

`ahora()` ahora llama a `activarGlosario(p)`: la casilla «¿y si la reanudo?» redibuja sin pasar por `pintar()`, y
sin esa llamada sus menciones quedaban sin tooltip.

## Archivos tocados

- `pi/cockpit-encargos/encargos.js`, `pi/cockpit-encargos/red.js` y `pi/cockpit-encargos/encargos.css`.
- `pi/test_cockpit_paginas.py`:
  - 7 pruebas nuevas en `ConsolaEncargosTests`;
  - 6 fijaciones de fuente actualizadas a la forma nueva: las dos `h2` de Ahora, la leyenda, el `<strong>` de
    `colas_fuera`, la pastilla de la red y el conteo de envoltorios de `test_c4_todo_texto_del_panel…`, que ahora
    acepta `mencionCola()` además de `delPanel()` y descuenta aparte el `mencionCola(c)` de «caben».
- `encargos-nube/95-PLAN.md`, `95-RESULTADO.md`, `95-fallas-antes-despues.txt`, `95-muestra.html` y
  `95-muestras/*.png`.

## Pruebas (salida real)

**En esta copia, `pi/test_cockpit_paginas.py` no se importa**, ni antes ni después: falta
`pi/fixtures/vivo/corriendo-rev1.json` (y `pausada`, `terminada` y `esperando`).

```
$ NODO_PRUEBAS=1 python3 -B pi/test_cockpit_paginas.py
FileNotFoundError: [Errno 2] No such file or directory: '/home/user/claude/pi/fixtures/vivo/corriendo-rev1.json'
```

Para correrla igual, la copié al scratchpad y llené esos cuatro archivos con `{"escrito": …}`, **fuera del repo**:

```
antes:   Ran 184 tests in 23.519s   FAILED (failures=14, errors=60, skipped=1)
después: Ran 191 tests in 26.115s   FAILED (failures=14, errors=60, skipped=1)
```

La lista de fallas es **idéntica** antes y después (`diff` vacío; está en `95-fallas-antes-despues.txt`). Son de
clases que no se tocaron (Avisos, Esfuerzo, Reparto, ColasVivas…) y vienen del relleno o de archivos de la Pi que
faltan. `EncargosTests` y `ConsolaEncargosTests` quedan enteras en verde.

Las 7 pruebas nuevas:

```
$ NODO_PRUEBAS=1 python3 -B pi/test_cockpit_paginas.py -k test_95 -v
test_95_c1_las_tres_lineas_con_los_fixtures_reales ... ok
test_95_c1_trampa_88_la_ultima_es_por_inicio_no_por_nombre ... ok
test_95_c2_cada_lugar_del_inventario_usa_mencionCola ... ok
test_95_c3_accesible_igual_que_el_glosario ... ok
test_95_c4_datos_hostiles_no_llegan_como_html ... ok
test_95_c5_desconocida_y_sin_revision ... ok
test_95_el_js_real_con_node ... ok
Ran 7 tests in 0.122s
OK

$ node --check pi/cockpit-encargos/encargos.js && node --check pi/cockpit-encargos/red.js     → sin errores
```

- **Cómo se prueba:** como la suite no tiene motor de JS en la Pi, las pruebas C1, C4 y C5 usan un espejo en
  Python de `lineasCola`, igual que las demás de la clase. `test_95_el_js_real_con_node` corre **el JS real**
  (los tramos de `encargos.js`) con `node`, compara su salida con el espejo y se salta donde no hay `node`.
- **C1** (fixtures reales): `cola91n` dice el resumen del manifiesto, «91n · rev1 · Codex · detenida · 25-10 17:06»
  y «91n · rev1 · Codex · 5,7 min · NO DESPLEGABLE»; `cola93n`, «DESPLEGABLE». En la trampa de `cola88`, con vivo y
  sin él, la tarjeta dice «88b · rev2 · Codex · 6,3 min · DESPLEGABLE», ni 88c ni 88a.
- **C2:** se comprueba sobre la fuente que cada lugar del inventario usa `mencionCola` y que no queda ningún
  `${x.cola}`, `delPanel(x.cola)`, `colas_que_caben.map(delPanel)` ni `autorizadas.join(`.
- **C3:** la fuente tiene `aria-describedby`, foco, cursor y presión sostenida, un solo `#term-tooltip`, y la
  franja activa sus tooltips.
- **C4:** con `<img onerror>`, `<script>`, `sk-ant-…`, más de 300 caracteres y `__proto__` como cuenta, el token
  sale «oculto», cada línea mide 180 caracteres o menos y todo va por `el()`.
- **C5:** «sin datos de esta cola» (también para `__proto__`, `constructor`, `""` y `null`) y «sin revisión
  todavía».

**En el navegador** (Chromium con Playwright, sobre `95-muestra.html`):

- con el cursor sobre `cola88` aparece la tarjeta de 88b;
- al salir, se oculta;
- con Tab hasta `cola91n`, el foco tiene `aria-describedby="term-tooltip"` y muestra «detenida»;
- `cola00z` da «sin datos de esta cola»;
- dentro del botón, el foco es del `BUTTON` y el `span` no recibe `tabindex`;
- no hubo errores de consola.

Las capturas están en `95-muestras/`. No quedó ningún servidor levantado: la muestra se abre como archivo.

## Decisiones

- **Los fixtures no traen `vivo/`**, aunque el encargo los nombra. El «detenida» del C1 sale de un vivo armado en
  la prueba (`VIVO_91N`, y `VIVO_88` para la trampa) con la forma del real `pi/fixtures/vivo-cola85-85b.json`.
  Sin vivo, la línea 2 sale del historial y no dice el estado (el historial no lo trae).
- La línea 3 empieza con la etapa («88b · rev2 · …»), como pide el C1. El ejemplo del punto 3 del encargo
  («rev1 · Codex · 5,7 min · NO DESPLEGABLE») queda incluido tal cual.
- La cuenta de la línea 2 sale de `vivo.cuenta`, que ya trae el nombre («Codex»). La del historial es un id, y
  se traduce con `cuentas.toml` (`d.nombres`).
- «Qué hace» repite lo que filtra `seguro()`: una ruta con comas, como la del resumen de la etapa 91n, sale
  «oculto», igual que en el resto de la consola.

## Riesgos abiertos

- No se probó dentro de Cockpit en la Pi (aquí no hay Cockpit). La muestra usa las funciones reales con `el()` y
  los CSS reales, pero no el CSP ni `cockpit.js`.
- `Intl.DateTimeFormat` con `America/Santiago` depende de los datos de zona horaria del navegador del PC; son
  estándar en Chrome y Firefox.
- Al quitar el `title` de la pastilla, el lector de pantalla ya no lee «Elegir este encargo». Lee el nombre, la
  fase y la tarjeta.
- Si se agrega una mención nueva sin `mencionCola`, la prueba C2 sólo la detecta si sigue alguna de las formas
  buscadas (`${x.cola}`, `delPanel(x.cola)`…).
