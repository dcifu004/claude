# Encargo 99: RESULTADO (la pestaña Projects de 🏭 AI Ops, de verdad)

Hecho por Claude (Diego) en la nube el 25-10-2026, en la rama `claude/encargo-99-pestana-projects`, creada desde
`base-99`. El primer commit es el PLAN.

## Lo hecho

La maqueta del 98 pasó a la consola instalada (`pi/cockpit-encargos/`), reusando su modelo y sus vistas.

- **Pestaña Projects**, entre Runs y Timeline. Tiene su badge «en Review / tope» (hoy `7/3`, en rojo) y va en la URL:
  `#/projects`, `#/projects?p=voz`, `#/projects?v=carriles|conflicts|flow`.
- **Board.**
  - **Portada B:** las tarjetas de proyecto, con resultado, mini-tablero, avance, rework, abiertas, bloqueo y pronóstico
    al 80 %.
  - **Detalle A:** al tocar un proyecto se abre su carril, con las cinco columnas.
  - El botón **«Ver todos los carriles»** los muestra juntos, con el filtro «Sólo abiertos / Todo».
- **Conflicts:** la matriz encargo × archivo, agrupada por proyecto, y «Qué hacer», con el orden de a uno.
- **Flow over time:** el CFD semanal en SVG (con tabla), Now · Next · Later y el pronóstico Monte Carlo por proyecto.
  El método va en el «ⓘ método» y en la definición de Forecast del glosario.
- **Panel de una tarjeta:**
  - sus fases reales y las fechas (escrito, primera fase y DESPLEGABLE);
  - lead time, cycle time y aging;
  - **«Ver en Flow · encargo N»**, que abre `#/flujo?e=N` con el filtro de la 85b;
  - **«Ver en Traces»**, que abre `#/historial?e=N`: Traces ahora preselecciona ese encargo.
- **Glosario:** los 10 términos del 98 más **Lead time**, y una entrada en el mapeo («proyecto» → Projects).
  - Forecast ya existía con el sentido de la cola; ahora la definición cubre los dos usos.
- **Datos:**
  - `proyectos.json` se lee con `cockpit.file` y se parsea en la página. Si falta, pesa más de 1 MB o no es JSON, la
    pestaña lo dice en una línea y el resto de la página sigue igual.
  - Para el índice de `NN-*.md` hay **dos `find` de argumentos fijos** (sin shell, sin `sudo`, sin datos en el argv):
    - `find DIR -maxdepth 1 -name MD_ENCARGOS -printf "%T@ %f\n"` entrega la fecha y el nombre;
    - `find DIR -maxdepth 1 -name MD_ENCARGOS -exec grep -m1 -H "^# " {} +` entrega el título, en un solo proceso para
      todos los archivos;
    - `MD_ENCARGOS = "[0-9]*-*.md"`.
  - No hizo falta un script de índice.
- **Columna deducida.** `abiertos` es un override.
  1. Una cola viva (`vivo/<cola>.json`, corriendo o pausada): en autor o fix va a In progress; en rev, a Review.
  2. Si la última revisión fue DESPLEGABLE, Done.
  3. Un `NN-*.md` sin historial y sin RESULTADO va a Ready.
  4. Lo demás, como la maqueta: «sin DESPLEGABLE» o «sin fechas».
- **Lead time y cycle time:**
  - **lead time** va de la fecha más antigua entre el `.md` y la primera fase hasta el DESPLEGABLE;
  - **cycle time** va de la primera fase al DESPLEGABLE.
- `encargos/PROYECTOS.md` trae las reglas y un ejemplo. `encargos/proyectos_check.py` es la validación de sólo lectura.
- Las semanas van en hora de Chile con `Intl` (`America/Santiago`), no con -03 fijo.

## Archivos tocados

Nuevos en el paquete:
- `pi/cockpit-encargos/modelo.js`: el modelo de la maqueta adaptado. Sólo declara `modeloProyectos`, no toca el DOM y
  corre en node.
- `pi/cockpit-encargos/proyectos.js`: las vistas, en `vistaProyectos`.

Cambiados en el paquete:
- `pi/cockpit-encargos/encargos.js`: la lectura, los dos `find`, `projects()`, el badge, `RUTA` con `p` y `v`,
  `nombreSub` sin «n/tope» y Traces con `?e=`.
- `pi/cockpit-encargos/encargos.css`: un bloque al final. Usa los tokens del cockpit-comun; sólo los tres colores del
  CFD son propios, con su variante oscura.
- `pi/cockpit-encargos/index.html`: el botón, la sección y los dos scripts antes de `encargos.js`.
- `pi/cockpit-encargos/glosario.js`.

Datos y validación:
- `encargos/PROYECTOS.md` y `encargos/proyectos_check.py` (nuevos). No se tocó `encargos/proyectos.json`.

Pruebas:
- `pi/test_cockpit_paginas.py`:
  - la clase nueva `ProyectosTests`, con 11 pruebas;
  - las fijaciones que cuentan pestañas, archivos y `spawn`:
    - 15→17 scripts y 25→27 archivos;
    - `SPAWN_99` con los dos `find`;
    - 8→10 `spawn`;
    - la pestaña en `SUBMODULOS` y en el despacho de `pintar()`;
    - `PROYECTOS_JSON` en las lecturas;
    - el orden de los `<script>`.
- `pi/fixtures/proyectos/`:
  - `historial-98.jsonl` e `indice-98.json` (copias de `98-datos`);
  - los tres JSON rotos de C4.

Verificación en la nube:
- `encargos-nube/99-cockpit-falso/`: `servidor.py` y `cockpit.js`.
- `encargos-nube/99-capturar.js`.
- `encargos-nube/99-verificar.py`.
- `encargos-nube/99-capturas/`.
- `encargos-nube/99-fallas-antes.txt` y `99-fallas-despues.txt`.

No se tocaron `encargos/cola-run.py`, `encargos/test_*.py` ni `botv3/`. El tooltip del 95 (`mencionCola`,
`lineasCola`) quedó igual: no hubo choque.

## Pruebas (salida real)

### `pi/test_cockpit_paginas.py`, antes y después

En esta copia la suite no se importa: faltan `pi/fixtures/vivo/*.json`, igual que en el 95. La corrí desde una copia en
el scratchpad, con esos seis archivos rellenos con `{"escrito": …}`, fuera del repo:

```
antes:   Ran 191 tests in 24.142s   FAILED (failures=16, errors=58, skipped=1)
después: Ran 202 tests in 23.577s   FAILED (failures=16, errors=58, skipped=1)
diff 99-fallas-antes.txt 99-fallas-despues.txt   → sin diferencias (LISTA IDENTICA)
```

Las 74 fallas son las mismas, de clases que no toqué y que dependen de archivos de la Pi. Las 11 nuevas:

```
test_99_c2_el_modelo_de_la_pagina_da_lo_mismo_que_el_espejo ... ok
test_99_c2_las_cifras_del_98_con_el_espejo ... ok
test_99_c3_columna_deducida_con_colas_vivas ... ok
test_99_c4_proyectos_check ... ok
test_99_enlaces_a_flow_y_traces ... ok
test_99_js_balanceado_un_nombre_y_sin_ejecutar_nada ... ok
test_99_la_pestana_va_en_la_url ... ok
test_99_los_datos_van_como_texto ... ok
test_99_modelo_real_con_datos_hostiles ... ok
test_99_proyectos_json_ausente_roto_o_enorme_no_rompe_la_pagina ... ok
test_99_tokens_en_un_solo_lugar_y_colores_propios_con_tema ... ok
Ran 11 tests in 0.518s
OK
```

En la Pi no hay `node`, así que las dos pruebas que corren `modelo.js` de verdad se saltan solas. El espejo en Python
(`modelo_99`) cubre C2 y C3 igual.

### C2: las cifras del 98

`python3 encargos-nube/99-verificar.py` (el `verificar.py` del 98 adaptado) recalcula en Python y compara con
`pi/cockpit-encargos/modelo.js` corriendo en node:

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
  índice 124 · con proyecto 119 · en Sueltos 5 · perdidos 0
== Página (modelo.js) ==
  semanas ['28-09', '05-10', '12-10', '19-10'] · throughput [7, 22, 19, 28] · c3 124/124, en Sueltos 5
OK: Python y la página dan lo mismo
```

**Ojo con el historial de la rama.** `encargos/historial.jsonl` de `base-99` es una copia más corta: tiene 387 de las 397
fases, y sus 387 líneas son idénticas a las primeras del historial del 98. Con él, las cifras son **7 / 22 / 19 / 25**:
la última semana todavía no tiene las 10 fases del final. El 19 y el 84a dan igual (7,8 y 30,7 min). La prueba
`test_99_c2_las_cifras_del_98_con_el_espejo` fija las dos cosas. `99-verificar.py encargos/historial.jsonl` también da
OK.

Con `proyectos.json`, la cobertura queda en **5 en Sueltos**, contra 9 en el 98, porque 07, 39b, 75 y 78a pasaron a
bot. Los cinco son 09, 52, 52b, 59 y 62.

### C3: la columna deducida

Con un `vivo/` de prueba, 86 está en rev2 (corriendo) y 77 en autor (pausada); ninguno está en `abiertos`. Caen en
**Review** y en **In progress**. 83 está en rev1, pero queda en **Ready** porque está en `abiertos` y el override gana. 61,
con su cola terminada, queda en Done. Lo comprueban el espejo en Python y el `modelo.js` real con node; en la página, el
caso `vivo` del cockpit falso.

### C4: `proyectos_check.py`

| Archivo | Resultado |
|---|---|
| `encargos/proyectos.json` de la rama | **rc 0**, con dos avisos: In progress 3/2 y Review 7/3 en `abiertos`. Pasarse del tope es un aviso, no un error. |
| `id-repetido.json` | rc 1: «el encargo 41 está en dos proyectos: bot y cuentas» |
| `columna-inventada.json` | rc 1: «voz: «abiertos» pone 97 en «Testing», que no es una columna» |
| `json-invalido.json` | rc 1: «JSON inválido: Expecting property name enclosed in double quotes: line 11 column 15» |

Por omisión, el índice son los `NN-*.md` de la carpeta (en esta copia hay 4). Con `--indice` se le pasa otro: la prueba
usa el de 124.

### C5 y C6: la página con el cockpit falso

`node encargos-nube/99-capturar.js` levanta `99-cockpit-falso/servidor.py` en `127.0.0.1:8099`. Ese servidor sirve
`pi/cockpit-encargos` y `pi/cockpit-comun` tal cual, y contesta `cockpit.file` y `cockpit.spawn` con los archivos de la
rama:

- `encargos/historial.jsonl` y `encargos/proyectos.json`;
- los 114 `cola-*.toml`;
- el panel de `pi/fixtures/encargos/`.

Recorre 1280, 800 y 375 px, en claro y en oscuro, por la portada, los carriles, el proyecto voz, Conflicts, Flow over
time, el panel de una tarjeta y el enlace a Flow. Además prueba cinco casos de `proyectos.json`: ausente, roto, de más de
1 MB, hostil y con colas vivas. Salida real:

```
31 capturas en encargos-nube/99-capturas/ (2.9 MB)
light 1280: C6 ok, «Ver en Flow» abre #/flujo?e=86 con «Pipeline · encargo 86»
… (lo mismo en light 800, light 375, dark 1280, dark 800 y dark 375)
caso ausente: Projects: no se pudo leer encargos/proyectos.json.
caso roto: Projects: encargos/proyectos.json no es un JSON válido.
caso grande: Projects: encargos/proyectos.json pesa más de 1 MB y no se lee.
caso hostil: proyectos.json: 5 entrada(s) ignorada(s)…
caso vivo: Throughput17,8/sem…
sin errores de consola, sin pedidos fuera de 127.0.0.1 y sin desborde horizontal
```

- **Peso:** con las tres anchuras, las capturas pesaban 4,0 MB. Por eso, como pide el encargo, sólo se guardan las de
  1280 y 375; los 800 px se revisan igual.
- **Problemas que encontré y arreglé:**
  - Conflicts se desbordaba 342 px a 375 px, porque la rejilla `1fr` crecía con la matriz. Ahora es
    `minmax(0, 1fr)` y la matriz tiene scroll propio.
  - Los chips del WIP salían anchos porque `.dato` de `base.css` es una rejilla de 150 px. Ahora usan su propia clase.
- **Caso hostil:** el nombre `<img src=x onerror=alert(1)>` sale como texto y no aparece ningún `<img>`. `__proto__` en
  `abiertos` y en `archivos_compartidos` se descarta con su aviso.

## Archivos que necesitan alta en el catálogo de `nodo-desplegar`

- `pi/cockpit-encargos/modelo.js` y `pi/cockpit-encargos/proyectos.js`. Van al paquete `encargos` de Cockpit, junto a
  `red.js`.
- No hay script de índice nuevo: el índice sale de los dos `find`.
- `encargos/proyectos_check.py` y `encargos/PROYECTOS.md` viven en la carpeta de encargos del vault, que la página lee
  directo (`DIR`). Si el catálogo cubre esa carpeta, también van.

## Decisiones

- **El modelo es un archivo propio** (`modelo.js`), como pedía el encargo, y la vista va en `proyectos.js`, como
  `red.js`. Cada uno declara un solo nombre global, así que no chocan con `encargos.js`; los dos se cargan antes que
  ella.
- **Dos `find`** en vez de 124 lecturas o un script nuevo. Los argumentos son fijos y van en constantes (`MD_ENCARGOS`),
  para que la prueba de `spawn` siga leyéndolos literal.
- **El panel de la tarjeta va dentro de la pestaña**, arriba de la vista, y no en un `<dialog>`. Así se mantiene el
  patrón de la página, que no tiene diálogos (el buscador es una capa propia).
- **Los títulos de los `.md` pasan por `delPanel()`**, la lista blanca de la página: un título con un token raro sale
  «oculto», como en el resto de AI Ops. Los nombres y resultados de `proyectos.json` van como texto plano, recortados a
  200 caracteres.
- **Pronóstico:** se mantienen la semilla fija 98, la ventana de 8 semanas como máximo (hoy hay 4) y el mínimo de 3
  terminados. Hoy hay datos insuficientes para voz, música y temblores.
- **Encargos «nube»:** no tienen historial en la Pi y sólo aparecen si están en `abiertos` (95, 96, 97, 87b, 88, 91b y
  92b). Es lo que sale solo de la regla de universo.

## Riesgos abiertos

- **El lead time de las capturas es aproximado.** Esta copia no trae los 124 `.md`, así que el cockpit falso usa la
  fecha del título (a las 12:00) como fecha de modificación. En la Pi es la `mtime` real del archivo, y si un `.md` se
  edita después, la fecha es más nueva que la de escritura. «La más antigua conocida» toma la menor entre esa fecha y la
  primera fase. Para un dato fiel haría falta un campo `escrito` en el índice (por ejemplo, el de `git log`).
- **Sumar archivos desde los diffs: queda para después.** En esta copia no hay ningún `encargos/<id>n-diff-nube.txt` ni
  diffs de cola, así que no pude probarlo. La propuesta: un tercer `find` fijo,
  `find DIR -maxdepth 1 -name "*-diff-nube.txt" -exec grep -h -H "^diff --git " {} +`, que devuelve sólo las cabeceras
  `diff --git a/X b/X` y nunca el contenido. Con eso, `modelo.js` sumaría X → id a `archivos_compartidos`, sólo para
  los encargos abiertos, para que la matriz no se llene de pruebas ya cerradas.
- **El historial de la rama es más corto que el del 98**, como se explicó en C2. En la Pi se lee el vivo.
- **La suite no corre entera en esta copia** (faltan `pi/fixtures/vivo/*.json`). Hay que correrla otra vez en la Pi,
  donde están esos fixtures.
- **El pronóstico es frágil:** con 4 semanas de historia y una primera semana de 2 días, va a cambiar bastante con cada
  semana nueva.
