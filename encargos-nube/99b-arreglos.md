# Encargo 99b: arreglos del 95 + 99 antes de la revisión cruzada (Claude (Diego), 25-10-2026)

Rama `base-99b`, creada desde `claude/encargo-99-pestana-projects` (`e0c87d7`). Trabaja en una rama nueva
`claude/encargo-99b-arreglos` y deja `encargos-nube/99b-RESULTADO.md`.

## Contexto

El 25-10 a las ~21:35, Claude (Diego) corrió `python3 pi/test_cockpit_paginas.py` en la Pi, en una copia temporal
con `pi/`, `botv3/` y `encargos/` del vault reales, antes y después de aplicar el 95 + 99. En la Pi corren las
pruebas que aquí se caían por falta de fixtures, y aparecieron fallas nuevas que la nube no podía ver:

```
antes:   Ran 184 tests  FAILED (failures=2, errors=36)        ← del entorno de la copia
después: Ran 202 tests  FAILED (failures=5, errors=41, skipped=3)
nuevas:
  ERROR test_95_c1_las_tres_lineas_con_los_fixtures_reales
  ERROR test_95_c1_trampa_88_la_ultima_es_por_inicio_no_por_nombre
  ERROR test_95_c4_datos_hostiles_no_llegan_como_html
  ERROR test_95_c5_desconocida_y_sin_revision
        → FileNotFoundError: …/encargos-nube/95-fixtures/historial.jsonl
  FAIL  test_99_c2_las_cifras_del_98_con_el_espejo
        → self.assertEqual(rama, self.h98[:len(rama)]): el historial vivo ya tiene 399 filas (91bn y 92bn)
  FAIL  RepartoYModelosTests.test_la_pestana_existe_y_solo_usa_comandos_fijos
        → ['flujo','ahora','projects','tiempo',…] != ['flujo','ahora','tiempo',…]
  FAIL  GuardianDelNodoTests.test_los_avisos_reales_no_cambiaron_y_las_cargas_estan_aisladas + ERROR tearDownModule
        → probablemente del entorno: en ese momento la cola94n escribía avisos reales
```

Y `python3 encargos/proyectos_check.py` con el índice real dio rc 1:
`encargos del índice sin proyecto: 36`.

## Qué hacer

1. **Fixtures del 95 en su lugar.** En el vault no existe `encargos-nube/`. Mueve `encargos-nube/95-fixtures/` a
   `pi/fixtures/encargos-95/` (o a un nombre parecido bajo `pi/fixtures/`) y cambia `FIX95`. Ninguna prueba debe
   leer nada bajo `encargos-nube/` (`grep -n "encargos-nube" pi/test_cockpit_paginas.py` sólo puede dar comentarios).
2. **`test_99_c2` y `test_99_c2_el_modelo_de_la_pagina…` no pueden depender del largo del historial vivo.** El libro
   crece con cada fase. Las cifras se fijan sólo con `pi/fixtures/proyectos/historial-98.jsonl`. Si quieres que se
   siga leyendo el vivo (como hace `FlujoEncargosTests`, sólo para leer), compara sólo lo que no cambia: por ejemplo,
   que las primeras 397 filas coincidan con el fixture y que el modelo no se caiga con el resto.
3. **Las fijaciones que aquí no corrían.** `RepartoYModelosTests` fija los botones `data-p` sin `projects`. Busca en
   toda la suite las demás fijaciones de pestañas, botones, `<script>`, archivos y `spawn` de 🧵 Encargos, incluidas
   las de las clases que aquí fallaban por el entorno, y ponlas al día con la pestaña nueva. Haz la lista en el
   RESULTADO.
4. **El 36 (el túnel, `36-tunel-panel-revision.md`) va en el mismo proyecto que el 36b** (`seguridad`), en
   `encargos/proyectos.json`. El `"36"` de los `docs` de `musica` es el doc 36 de Spotify, no el encargo: déjalo.
   Después corre `python3 encargos/proyectos_check.py --indice <el de abajo>` y que dé rc 0.
5. **El índice real de la Pi** (25-10 21:40) está en `encargos-nube/99b-indice-pi.txt`, con el formato de
   `find -printf "%T@ %f\n"`: 529 archivos. Úsalo para el check del punto 4 y, si te sirve, para un fixture de
   cobertura. No lo copies a `pi/fixtures/` entero si no hace falta.
6. **El guardián.** Comprueba que ninguna prueba del 95 o del 99 pueda tocar los avisos reales ni dejar algo para el
   `tearDownModule`. Si no encuentras nada, dilo; se volverá a correr en la Pi con las colas quietas.

## Fuera de alcance

- No cambies el comportamiento de la página ni la asignación de proyectos, salvo el 36.
- No toques `cola-run.py`, `botv3/` ni el tooltip del 95 (salvo las rutas de sus fixtures).
- La línea del token de Slack falso (~4860) sigue partida, como está.

## Resultado

`encargos-nube/99b-RESULTADO.md`: los cambios, la lista de fijaciones del punto 3 y la salida real de
`pi/test_cockpit_paginas.py` y de `proyectos_check.py`. Después, Claude (Diego) lo escribe en el vault y lo revisa Codex
(cola9599n), con la suite entera corriendo en la Pi.
