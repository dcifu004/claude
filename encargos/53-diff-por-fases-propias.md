# Encargo 53: el diff de cada etapa sólo con lo que hicieron sus fases (Claude (Diego), 12-10-2026)

Naturaleza `seguridad`. **Alcance mínimo**, elegido por el usuario el 12-10. La ampliación prevista
es una copia de trabajo separada por cola (`git worktree`), que queda fuera de este encargo.

## Valor y costo

Tres veces en dos días, cambios ajenos entraron al diff de una etapa:

- la 46a se detuvo dos veces por encargos que escribió Claude (Diego) entre sus fases;
- la 46 no pidió su despliegue por `pi/luces-senales.py`, que era de la 43b;
- la 41 y la 42 revisan contra una foto del 10-10.

Cada rechazo así cuesta una vuelta de revisión y arreglo (~17 % de la ventana de 5 h de
Claude (Cami)) y horas de espera. Este encargo se pronosticó en ~45 min y +4 % semanal.

## Leer primero

- `encargos/cola-run.py`:
  - el docstring «Historial de versiones» (~38–52);
  - `versiones()` (~1151);
  - `git_foto()` (~1192);
  - `git_base_guardar()` y `git_base_cargar()` (~1217–1238);
  - `git_diff_etapa()` (~1240);
  - dónde se toman las fotos «(antes)» y después de cada fase;
  - el chequeo «Archivos nuevos sin entrada en el catálogo».
- `encargos/versiones.py`, entero: es corto.
- `encargos/revision-plantilla-v2.md`: dónde recibe `{DIFF}`.
- `encargos/46ar2-RESULTADO.md` y `46ar3-RESULTADO.md`: los rechazos por atribución.
- `encargos/trampas.md`: «Cola y encargos».

**No hace falta leer** las páginas ni el bot.

## Premisa comprobada (Fase 0)

La cola ya hace un commit «antes» y otro «después» de cada fase en un repositorio separado
(`/opt/nodo/datos/git/11-Pi5.git`). Hoy el diff de la etapa va desde la foto previa al autor
hasta ahora, y por eso incluye todo lo que otros escribieron entre medio.

## Qué hacer

1. **Diff propio.** El diff de la etapa es la suma de los diffs «antes → después» de **sus
   propias fases**: autor, fix1 y fix2. Los commits de cada fase se guardan en
   `~/encargos-logs/<cola>-git.json`, para que un `--desde` los encuentre.
2. **Cambios ajenos.**
   - Los archivos que cambiaron **entre** fases de la etapa, fuera de sus fases, van al final
     del diff en la sección «Cambios ajenos (no son de esta etapa: no los revises)», **sólo con
     el nombre del archivo**, sin contenido.
   - La plantilla de revisión gana una regla: lo listado como ajeno no se juzga ni es motivo de
     rechazo.
3. **Despliegue.** El chequeo de archivos nuevos sin catálogo y la lista del pedido usan **sólo
   los archivos del diff propio**.
4. **Lo que queda fuera.** Si otra cola escribe **durante** la misma fase, sus cambios siguen
   entrando, porque comparten árbol. Eso es la ampliación prevista. Hay que documentarlo en el
   docstring y anotar en el diff «hubo otras colas vivas durante la fase X: <nombres>», a partir
   de los `vivo` de ese momento.
5. **Si git falla:** la cola sigue, igual que hoy.

## Criterios de aceptación (con pruebas sobre un repositorio git temporal)

- C1. Con foto, autor que escribe `A`, escritura externa de `B` entre fases y fix que escribe
  `C`: el diff contiene `A` y `C`; `B` aparece **sólo por nombre** en «Cambios ajenos».
- C2. Con un `--desde 53:rev2` después de reiniciar, el diff sale idéntico al de C1.
- C3. Despliegue: el caso real de la 46 (un archivo nuevo de otra cola que aparece entre
  fases) ya no bloquea el pedido, y un archivo nuevo propio sin catálogo sí lo bloquea.
- C4. Con otra cola viva durante la fase (un `vivo` falso), el diff trae el aviso de C… punto 4.
- C5. Sin git o con git roto, la cola sigue y lo anota, igual que hoy.
- C6. `encargos/test_diff_propio.py` (nuevo), `encargos/test_matriz_cuota.py`,
  `encargos/test_acciones_cola.py` y `pi/test_cockpit_paginas.py` pasan. El RESULTADO dice
  cada criterio cumplido o no, con su comando y su salida.

## Invariantes

- **Archivos compartidos:** `<cola>-git.json` se escribe de forma atómica; el repositorio git
  lo comparten todas las colas, y sus commits ya van serializados por cola.
- **Pruebas:** un repositorio y un árbol en `tmp_path`. Ninguna toca `/opt/nodo/datos/git` ni
  `~/encargos-logs`, y no mandan avisos.
- **Entradas hostiles:** los nombres de archivo ajenos se muestran escapados, sin contenido.
- **Root, router y catálogo:** no aplican, salvo el chequeo del punto 3, que sólo cambia la
  lista que recibe.

## Reglas

- **Un arreglo no agrega funciones nuevas.**
- No cambies las fotos (cuándo se toman ni sus mensajes), `arboles_extra`, la suma de la 46a ni
  los botones de la 46c.
- Cuentas siempre como «Claude (Diego)», «Claude (Cami)» y «Codex». Sin buscador web.

## Fuera de alcance

La copia de trabajo por cola (ampliación prevista) y cualquier cambio en Syncthing.

## Resultado

`encargos/53-RESULTADO.md` con el diff de `cola-run.py` y de la plantilla, y C1–C6 uno por uno,
con su salida.
