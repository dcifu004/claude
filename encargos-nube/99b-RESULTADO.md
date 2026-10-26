# Encargo 99b: RESULTADO (arreglos del 95 y del 99 antes de la revisión cruzada)

Hecho por Claude (Diego) en la nube el 26-10-2026, en la rama `claude/encargo-99b-arreglos`, creada desde
`base-99b` (`682e7b0`). El primer commit es el PLAN.

No cambié el comportamiento de la página, `cola-run.py`, `botv3/` ni el tooltip del 95. La línea del token de Slack
falso (~4860) sigue partida y no está en el diff.

## Cambios

1. **Fixtures del 95:** `git mv encargos-nube/95-fixtures pi/fixtures/encargos-95`, y `FIX95 = PI / "fixtures" /
   "encargos-95"`.
   - `grep -n "encargos-nube" pi/test_cockpit_paginas.py` da sólo el docstring de `ProyectosTests`, que nombra
     `99-capturar.js` como herramienta de la nube.
2. **El C2 del 99 ya no depende del largo del historial vivo.**
   - Las cifras (7/22/19/28; 19 → 7,8 min; 84a → 30,7 min) se fijan sólo con `pi/fixtures/proyectos/historial-98.jsonl`
     y con una copia nueva de `proyectos.json`, `pi/fixtures/proyectos/proyectos-99b.json`.
   - Tampoco puede depender del `proyectos.json` vivo, porque su `abiertos` cambia con cada encargo y eso mueve el
     throughput.
   - Del historial vivo, la prueba nueva `test_99_c2_el_historial_vivo_sigue_al_fixture` compara sólo lo que no cambia
     cuando crece:
     - las filas que comparte con el fixture son iguales;
     - el espejo arma con el `proyectos.json` vivo;
     - el 19 y el 84a siguen en 7,8 y 30,7 min;
     - las tres primeras semanas son las mismas.
   - `test_99_c2_el_modelo_de_la_pagina…` compara el JS con el espejo con los fixtures y con los archivos vivos; que
     coincidan no depende del largo.
   - Lo probé con un historial vivo simulado de **399 filas** (las 397 del fixture más una fase del 91bn y otra del
     92bn), como el de la Pi: `ProyectosTests` da `Ran 12 tests … OK`. La versión anterior caía en
     `assertEqual(rama, self.h98[:len(rama)])`.
3. **Fijaciones de 🧵 Encargos** puestas al día. La lista completa va abajo.
4. **El 36** está en `encargos` de `seguridad`, en `encargos/proyectos.json` (una línea, antes del 36b). El `"36"` de
   los `docs` de `musica` (el doc 36 de Spotify) quedó igual.
5. **`proyectos_check.py --indice`** ahora acepta, además del JSON, la salida de `find -printf "%T@ %f\n"`: la de
   `encargos-nube/99b-indice-pi.txt` y la que lee la página.
   - La regla es la misma que la de la pestaña: los `NN-slug.md`, sin RESULTADO ni PLAN.
   - Con el índice real da **rc 0**: 137 encargos.
   - Para la suite dejé `pi/fixtures/proyectos/indice-pi-25-10.txt`, que tiene sólo las 146 líneas `NN-slug.md` del
     índice real, no los 529 archivos. `test_99_c4_proyectos_check` comprueba dos cosas con él: que da rc 0 con el
     `proyectos.json` vivo, y que sin el 36 da rc 1 con «sin proyecto: 36».
6. **El guardián.** Revisé el código de las pruebas del 95 y del 99 (`ConsolaEncargosTests.test_95_*` y
   `ProyectosTests`):
   - ninguna llama a `previas._cargar(...)`, a `cola-run.py`, a `registro_avisos.py`, a `registrar()` ni a `avisar*`;
   - ninguna nombra `/opt/nodo` ni `AVISOS_REALES`;
   - sólo escriben en un `tempfile.TemporaryDirectory()` (un `proyectos.json` sin el 36), que se borra solo;
   - corren `node` sobre el modelo puro y `proyectos_check.py`, que sólo lee (la misma prueba fija que no tiene
     `"w"`, `write_text`, `subprocess` ni `unlink`);
   - no dejan nada para el `tearDownModule`.

   **No encontré nada.** El FAIL del guardián y el ERROR de `tearDownModule` de la corrida en la Pi miden la huella de
   `avisos.jsonl` y `avisos-salida.jsonl` durante toda la corrida, así que calza con la cola94n escribiendo avisos en
   ese momento. Hay que volver a correr la suite en la Pi con las colas quietas.

## Lista de fijaciones (punto 3)

Busqué en toda la suite las fijaciones de `data-p`, `<section data-panel>`, el despacho de `pintar()`, los `<script>`,
la cantidad de archivos JS y los `spawn` de 🧵 Encargos, incluidas las de clases que aquí no corren por el entorno.

| Clase y prueba | Qué fija | Estado |
|---|---|---|
| `RepartoYModelosTests.test_la_pestana_existe_y_solo_usa_comandos_fijos` | los `data-p` | **arreglada en el 99b**: suma `projects` |
| ídem | los `<script>` | **arreglada en el 99b**: suma `modelo.js` y `proyectos.js` |
| ídem | el despacho `({ … })[panel]()` | **arreglada en el 99b**: con `projects` |
| ídem | los `spawn` | **arreglada en el 99b**: 8 → 10 |
| `AvisosTests.test_la_pestana_dibuja_lo_que_el_panel_publica` | el despacho `({ … })[panel]()` | **arreglada en el 99b**: con `projects`. Aquí cae antes, en el `setUp`, porque falta `13-Agente-Not…`; por eso no se veía. |
| `ComunTests.test_aplicar_tema_y_el_estan_una_sola_vez` | scripts vistos | ya en el 99: 15 → 17 |
| `ComunTests.test_js_balanceado_con_el_tokenizador` | lista de `.js` | ya en el 99: suma `modelo.js` y `proyectos.js` |
| `ComunTests.test_no_hay_style_en_linea` | archivos `.html`/`.js` | ya en el 99: 25 → 27 |
| `ResumenYUsoTests.test_la_pagina_sigue_sin_escribir_y_sin_comandos_nuevos` | `spawn` | ya en el 99: 8 → 10 |
| `CargaVsCapacidadTests.test_c2_la_casilla_no_escribe_en_ninguna_parte` | `spawn` | ya en el 99: 8 → 10 |
| `ConsolaEncargosTests.test_c3_sin_ejecucion_nueva` | `spawn` | ya en el 99: `SPAWN_ANTES \| SPAWN_99`, 10 |
| `ConsolaEncargosTests.test_c5_cada_submodulo_tiene_su_ruta` | pestañas y paneles | ya en el 99: `SUBMODULOS` con `projects`, 7 paneles ocultos, despacho |
| `FlujoEncargosTests.test_c2_sin_lectura_ni_ejecucion_nueva` | `spawn` y lecturas | ya en el 99: `SPAWN_99`, 10, `ARCHIVOS_ANTES` con `PROYECTOS_JSON` |
| `FlujoEncargosTests.test_c3_csp_y_accesibilidad` | el orden de los `<script>` | ya en el 99 |

Revisé y no cambian, porque no dependen de la pestaña nueva:
- `ConsolaEncargosTests` (`test_c6_anchos`, el badge de avisos en `pintarConsola`);
- `FlujoEncargosTests.test_portada_modos_y_ahora` (`flujo` primero y `ahora` segundo, que se mantienen);
- `HistorialOrdenTests`, que corre `cambiarOrden` con node, sin cargar la página;
- `ColasVivasTests` y `EsperaDeCuota`, `Reanudacion` y `AvisosDeLaCola` (no fijan pestañas ni `spawn`).

**Por qué el 99 no las vio.** En la corrida del 99, `RepartoYModelosTests.test_la_pestana_existe…` ya estaba en la
lista de fallas de antes: aquí cae por el entorno, porque falta `encargos/ejemplo-reparto.toml`. Por eso la fijación
de `projects` quedó tapada y la lista salió «idéntica». Ahora pasa las fijaciones y sólo cae en la línea 2798, la de
`ejemplo-reparto.toml`:

```
antes:   AssertionError: Lists differ: ['flujo', 'ahora', 'projects', 'tiempo', …] != ['flujo', 'ahora', 'tiempo', …]   (línea 2789)
después: AssertionError: False is not true                                                                         (línea 2798: (ENCARGOS_DIR / "ejemplo-reparto.toml").is_file())
```

En la Pi, donde ese archivo existe, tiene que pasar entera.

## Archivos tocados

- `pi/test_cockpit_paginas.py`:
  - `import tempfile` arriba;
  - `FIX95`;
  - `RepartoYModelosTests` y `AvisosTests` (las fijaciones de arriba);
  - en `ProyectosTests`: los fixtures de proyectos, la prueba nueva del historial vivo, el C2 sin largo y el C4 con el
    índice real.
- `pi/fixtures/encargos-95/` (movido desde `encargos-nube/95-fixtures/`).
- `pi/fixtures/proyectos/proyectos-99b.json` y `pi/fixtures/proyectos/indice-pi-25-10.txt` (nuevos).
- `encargos/proyectos.json` (el 36).
- `encargos/proyectos_check.py` (`--indice` con el formato de `find`).
- `encargos-nube/99b-PLAN.md`, `99b-fallas-antes.txt`, `99b-fallas-despues.txt` y este RESULTADO.

## Pruebas (salida real)

### `python3 pi/test_cockpit_paginas.py`, como la cola

En esta copia no se importa: faltan los `pi/fixtures/vivo/*.json`, que están en la Pi.

```
$ python3 pi/test_cockpit_paginas.py
…
FileNotFoundError: [Errno 2] No such file or directory: '/home/user/claude/pi/fixtures/vivo/corriendo-rev1.json'
```

Por eso, igual que en el 95 y el 99, la corrí desde una copia en el scratchpad con esos seis archivos rellenos con
`{"escrito": …}`, fuera del repo, con el mismo comando `python3 pi/test_cockpit_paginas.py`:

```
antes  (base-99b):  Ran 202 tests in 25.875s   FAILED (failures=16, errors=58, skipped=1)
después:            Ran 203 tests in 27.500s   FAILED (failures=16, errors=58, skipped=1)
diff 99b-fallas-antes.txt 99b-fallas-despues.txt   → sin diferencias (LISTA IDENTICA)
```

Las 74 fallas son del entorno de esta copia:
- `13-Agente-Not…`, `90-Referencia/…`, `ejemplo-reparto.toml`, `sudoers` y `luces`, que faltan;
- los `vivo/` rellenos (los `KeyError: 'estado'`);
- `node` con argumentos demasiado largos.

Las pruebas del 95 y del 99:

```
test_95_c1_las_tres_lineas_con_los_fixtures_reales ... ok
test_95_c1_trampa_88_la_ultima_es_por_inicio_no_por_nombre ... ok
test_95_c2_cada_lugar_del_inventario_usa_mencionCola ... ok
test_95_c3_accesible_igual_que_el_glosario ... ok
test_95_c4_datos_hostiles_no_llegan_como_html ... ok
test_95_c5_desconocida_y_sin_revision ... ok
test_95_el_js_real_con_node ... ok
test_99_c2_el_historial_vivo_sigue_al_fixture ... ok
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
Ran 19 tests in 0.787s
OK
```

En la Pi no hay `node`, así que `test_99_c2_el_modelo_de_la_pagina…` y `test_99_modelo_real_con_datos_hostiles` se
saltan. `test_95_el_js_real_con_node` no tiene ese salto; es del 95 y no lo toqué.

### `proyectos_check.py`

```
$ python3 encargos/proyectos_check.py --indice encargos-nube/99b-indice-pi.txt
AVISO: In progress: 3 en «abiertos», tope 2 (97, 95, 36b)
AVISO: Review: 7 en «abiertos», tope 3 (96, 9092n, 92b, 87b, 94, 88, 91b)
proyectos.json: 0 error(es), 2 aviso(s); índice de 137 encargos
rc=0

$ python3 encargos/proyectos_check.py          # sin --indice: los NN-*.md de esta copia
proyectos.json: 0 error(es), 2 aviso(s); índice de 4 encargos
rc=0

# el proyectos.json de base-99b (sin el 36), con el mismo índice real: el error que vio la Pi
ERROR: encargos del índice sin proyecto: 36 (agrégalos a un proyecto, aunque sea a «otros»)
proyectos-sin36.json: 1 error(es), 2 aviso(s); índice de 137 encargos
rc=1
```

Los dos avisos son los topes de WIP pasados en `abiertos`. Son avisos y no errores, a propósito, como en el 99.

## Riesgos abiertos

- Falta correr la suite entera en la Pi con las colas quietas para cerrar el guardián (punto 6). También para ver
  pasar las clases que aquí caen por el entorno (`AvisosTests`, `RepartoYModelosTests`, `ColasVivasTests`), ya con sus
  fijaciones al día.
- `test_99_c4_proyectos_check` corre el `proyectos.json` **vivo** contra el índice real del 25-10. Si alguien borra un
  encargo de ese índice de `proyectos.json`, la prueba falla. Es a propósito: es el mismo control que hace la skill
  `encargar`.
- `indice-pi-25-10.txt` es una foto del 25-10. Los encargos nuevos los cubre `proyectos_check.py` sin `--indice` en la
  Pi, no esta prueba.
