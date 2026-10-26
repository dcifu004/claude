# Encargo 99b: PLAN de los arreglos del 95 y del 99

Rama `claude/encargo-99b-arreglos`, creada desde `base-99b`.

1. **Fixtures del 95.** Muevo `encargos-nube/95-fixtures/` a `pi/fixtures/encargos-95/` con `git mv` y cambio `FIX95`.
   Después de esto, `grep encargos-nube pi/test_cockpit_paginas.py` sólo puede dar comentarios.
2. **El C2 del 99.** Las cifras se fijan sólo con `pi/fixtures/proyectos/historial-98.jsonl`. Del historial vivo
   (`encargos/historial.jsonl`) sólo se comprueba lo que no cambia aunque crezca:
   - que sus filas comunes con el fixture sean iguales;
   - que el modelo arme sin caerse;
   - que el 19 y el 84a den lo mismo.
3. **Fijaciones de 🧵 Encargos.** Reviso en toda la suite las que fijan `data-p`, `<section data-panel>`, `<script>`,
   la cantidad de archivos JS y los `spawn`, partiendo por `RepartoYModelosTests`. Las pongo al día con `projects`, y la
   lista va en el RESULTADO.
4. **El 36.** Lo agrego a `encargos` de `seguridad` en `encargos/proyectos.json`. El «36» de los `docs` de `musica` se
   queda como está.
5. **El índice real.** Corro `proyectos_check.py --indice encargos-nube/99b-indice-pi.txt`. Para eso `--indice` tiene
   que aceptar también el formato de `find -printf "%T@ %f\n"`, no sólo JSON. Tiene que dar rc 0.
6. **El guardián.** Reviso que ninguna prueba del 95 o del 99 escriba los avisos reales o deje algo para el
   `tearDownModule`.

La suite, con la misma copia en el scratchpad (los `pi/fixtures/vivo/*.json` rellenos), da antes del cambio:
`Ran 202 tests … FAILED (failures=16, errors=58, skipped=1)`, con 74 fallas. La lista está en
`99b-fallas-antes.txt`.
