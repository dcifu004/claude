# Resultado — Encargo 53: diff propio por etapa

Ejecutó: Codex. Revisión prevista: Claude (Cami). No se usó buscador web.

## Cambios aplicados

El registro `~/encargos-logs/<cola>-git.json` conserva ahora, mediante temporal y
`os.replace()`, el commit de antes y después de cada fase propia (`autor`, `fix1`,
`fix2`). También guarda los nombres de las otras colas activas que había al inicio de
esa fase. Un relanzamiento con `--desde` vuelve a cargar esas listas.

El diff de revisión concatena exclusivamente esos tramos. Al haber una brecha entre
dos fases propias, calcula sus nombres con `git diff --name-only -z` y los muestra con
`json.dumps`, por lo que una ruta hostil queda escapada y nunca se incorpora contenido.
El despliegue obtiene la lista de archivos propios desde los mismos tramos; por eso el
catálogo y el chequeo de archivos nuevos no ven cambios ajenos. Si el historial falla,
se registra el aviso y se mantiene el comportamiento previo de seguir la cola.

## Diff relevante

```diff
--- a/encargos/cola-run.py
+++ b/encargos/cola-run.py
@@ historial de versiones
- el diff iba desde antes del autor hasta ahora
+ el diff suma cada tramo antes→después de autor/arreglos; los cambios entre tramos
+ se listan como ajenos y se avisa qué otras colas estaban vivas al iniciar la fase.
@@ git_base_guardar / git_base_cargar
- GIT_BASE[etapa] = commit; write_text(...)
+ se persisten `etapa:fases` y `etapa@arbol:fases`, con antes/después y vivos;
+ el JSON se escribe en temporal propio y se publica con os.replace().
@@ git_diff_etapa
- cuerpo = versiones.diff(base, hasta)
+ por cada fase propia: versiones.diff(antes, despues)
+ entre fases: git diff --name-only -z despues_previa antes_siguiente
+ sección: «Cambios ajenos (no son de esta etapa: no los revises)».
@@ etapa
- solo guardaba la base previa al autor
+ guarda los límites antes/después de toda fase no revisora.
@@ foto / desplegar
+ foto conserva la ruta relativa de cada entrada de catálogo; desplegar filtra pedido,
+ páginas y nuevos sin catálogo por los archivos de los tramos propios.
```

```diff
--- a/encargos/revision-plantilla-v2.md
+++ b/encargos/revision-plantilla-v2.md
- El diff exacto de la etapa (todo lo que cambió desde antes del autor hasta ahora...)
+ El diff propio de la etapa (la suma de autor y arreglos, incluido lo borrado...)
+ Lo que aparezca bajo «Cambios ajenos» no es de esta etapa: no lo juzgues ni lo uses
+ como motivo de rechazo.
```

También se añadió `encargos/test_diff_propio.py`; usa sólo `TemporaryDirectory`, un
repositorio separado, vivos y logs temporales, y no manda avisos.

## Criterios de aceptación

### C1 — Cumplido

`test_c1_c2_c4_diff_propio_sobrevive_reinicio_y_anota_vivas` escribe `pi/A.py` en
autor, `pi/B.py` externamente entre fases y `pi/C.py` en fix. Comprueba que A y C son
contenido del diff propio y que B aparece únicamente como `"pi/B.py"` bajo cambios
ajenos.

### C2 — Cumplido

La misma prueba vuelve a cargar el módulo y ejecuta `git_base_cargar()`; compara el
archivo de diff reconstruido byte a byte con el generado antes del reinicio.

### C3 — Cumplido

`test_c3_despliegue_ignora_ajeno_y_bloquea_nuevo_propio` demuestra que una entrada y
un archivo nuevo ajenos entre fases no entran al pedido ni bloquean. Luego crea
`pi/propio_nuevo.py` en `fix1` y comprueba el bloqueo «Archivos nuevos sin entrada en
el catálogo».

### C4 — Cumplido

La prueba deja un `vivo/cola99.json` temporal con estado `corriendo` antes de `fix1` y
comprueba el aviso: `hubo otras colas vivas durante la fase fix1: "cola99"`.

### C5 — Cumplido

`test_c5_git_roto_no_detiene_la_cola_y_desplegar_vuelve_al_control_amplio` fuerza un
error de `foto` y deja en el registro temporal la forma real de un tramo incompleto
(`antes` y `despues` en `null`). Comprueba que `desplegar()` vuelve al control amplio:
el archivo nuevo sin catálogo bloquea y nunca comunica «no cambió nada».

### C6 — Tres suites cumplidas; una falla previa ajena

Comandos y salida:

```text
$ python3 -m py_compile encargos/cola-run.py encargos/test_diff_propio.py
$ NODO_PRUEBAS=1 python3 encargos/test_diff_propio.py
Ran 7 tests in 0.832s
OK

$ NODO_PRUEBAS=1 python3 encargos/test_matriz_cuota.py
Ran 28 tests in 5.167s
OK

$ NODO_PRUEBAS=1 python3 encargos/test_acciones_cola.py
Ran 48 tests in 8.066s
OK (skipped=1)

$ NODO_PRUEBAS=1 python3 pi/test_cockpit_paginas.py
FAIL: test_la_skill_ya_no_ofrece_el_experimento_para_menor (__main__.EsfuerzoQueElModeloNoAceptaTests.test_la_skill_ya_no_ofrece_el_experimento_para_menor)
Ran 159 tests in 28.415s
FAILED (failures=1)
```

La única falla de Cockpit no es causada por este cambio: compara
`encargos/skill-encargar/SKILL.md` con
`90-Referencia/01-SkillsIA/encargar/SKILL.md`, que ya difieren (la segunda fue
actualizada después). Reparar o copiar esa skill es ajeno al alcance mínimo y tocaría
contenido compartido de otro encargo, por lo que se deja intacto.

Como control adicional, `python3 encargos/test_versiones.py` conserva una falla previa:
detecta el directorio `.git` existente dentro del árbol real. No se borró por ser una
operación destructiva fuera del alcance.

## Arreglos vuelta 1

Decisión conservadora ante una foto incompleta: el diff muestra todo tramo que puede
cerrar con una foto posterior y lo advierte; si el despliegue no puede determinar sus
tramos propios, recupera el control amplio anterior. Nunca interpreta la ausencia de
datos como ausencia de cambios.

1. **[Grave] Git roto apagaba el control de catálogo y podía decir «no cambió nada».**
   `desplegar()` ahora invalida el filtro propio si falta cualquier par de fotos o no
   hay fases registradas. La prueba `test_c5_git_roto_no_detiene_la_cola_y_desplegar_vuelve_al_control_amplio`
   usa el registro real de fase (`{"fase", "antes", "despues", "vivas"}`) con ambas
   fotos `null`: el nuevo archivo propio sin catálogo bloquea el flujo.

2. **[Grave] Una fase cortada ocultaba lo que ya había escrito.** `git_diff_etapa()`
   cierra un tramo sin `despues` en la siguiente foto inicial o en la foto `hasta` de
   la revisión y lo marca como interrupción. La prueba
   `test_fase_interrumpida_y_registro_viejo_no_ocultan_el_trabajo` deja
   `pi/medio_arreglo.py` con `peligroso`, simula la detención y confirma que tanto la
   revisión inmediata como el relanzamiento lo muestran con contenido.

3. **[Media] El registro antiguo (`{"53": "<commit>"}`) perdía al autor al crear el
   primer arreglo.** Si no existe un tramo `autor`, se antepone `base → antes del
   primer tramo`. La misma prueba escribe `pi/autor_antiguo.py` antes de cargar ese
   JSON antiguo y `pi/fix_nuevo.py` después: ambos aparecen en el diff.

4. **[Media] Una sola foto fallida omitía una fase sin aviso.** Los tramos sin foto
   inicial o de cierre dejan una advertencia explícita para revisar los archivos; el
   caso `fix1` con `antes: null` se verifica en
   `test_fase_interrumpida_y_registro_viejo_no_ocultan_el_trabajo`.

5. **[Media] Las colas muertas contaban como vivas y sólo se miraba al inicio.** La
   captura usa ahora la misma regla de actividad real de la matriz: sesión tmux viva o
   señal de menos de `ACTIVA_FRESCA_S`; al cerrar la fase incorpora también las que
   llegaron durante ella. `test_vivas_frescas_y_archivo_compartido_entre_fases` usa
   vivos con la forma real: excluye `cola_muerta` y la propia `cola53`, e incluye
   `cola_fresca` y `cola_llego_despues`.

6. **[Media] Un archivo propio y ajeno a la vez aparecía como puramente ajeno.** La
   lista conserva el nombre sin contenido, pero agrega «también lo cambió esta etapa:
   lo que se despliegue lo incluye». La misma prueba modifica `pi/A.py` entre fases y
   de nuevo en `fix1`; comprueba esa marca literal.

7. **[Media] Las pruebas no pasaban por el cableado ni cubrían invariantes.**
   `test_etapa_real_guarda_antes_y_despues_con_git_temporal` ejecuta `etapa()` con git
   temporal y un `correr` falso que escribe un archivo; la suite también cubre el
   temporal con PID más `os.replace()`, nombres ajenos con salto de línea y título
   falso, catálogo de forma real (`fuente`, `destino`, `despues`) y páginas propias
   frente a ajenas. Todo queda dentro de `TemporaryDirectory`.

Las salidas literales de las cuatro suites son las de C6. La única falla restante de
Cockpit compara dos copias preexistentes de `skill-encargar`; no toca estos archivos y
se mantuvo intacta. No se desplegó nada.

## Arreglos vuelta 2

Decisión conservadora ante fotos incompletas: si no se puede separar con certeza un
cambio ajeno, se lo muestra como parte de la etapa o se vuelve al control amplio. Nunca
se lo esconde ni se lo rotula como ajeno.

1. **[Grave] `arboles_extra` podía ocultar trabajo cortado o previo al formato de fases.**
   Se restableció para cada carpeta hermana el diff completo entre su base persistida
   (`<etapa>@<carpeta>`) y su `HEAD`, tal como era antes de este encargo. Así no depende
   de que los tramos de la hermana tengan ambas fotos. La prueba real
   `test_arbol_extra_con_corte_y_registro_viejo_muestra_toda_la_etapa` crea la carpeta
   hermana temporal `13-Agente-Noticias`, su repositorio separado, un `fix1` cortado con
   `medio.py`/`peligroso` y luego el JSON antiguo
   `{"53": "<commit>", "53@13-Agente-Noticias": "<commit>"}`. Comprueba que el diff
   contiene tanto ese corte como `autor_viejo.py` y `fix_nuevo.py`.

2. **[Media] Una foto inicial fallida podía dejar el cambio de `fix1` bajo «Cambios ajenos».**
   Si existe el cierre de la fase pero no su inicio, `git_diff_etapa()` abre el tramo desde
   el cierre propio anterior y lo advierte explícitamente; puede incluir cambios ajenos,
   pero no excluye ni desacredita el trabajo de la etapa. La prueba
   `test_fase_interrumpida_y_registro_viejo_no_ocultan_el_trabajo` crea con git temporal
   `autor → fix1(sin antes, C peligroso) → fix2`; comprueba que `C peligroso` está en el
   cuerpo propio y que `C54.py` no queda en la sección ajena.

3. **[Media] Faltaba cobertura contra seis regresiones del cableado y de la forma real.**
   - `test_etapa_real_guarda_antes_y_despues_con_git_temporal` ejecuta `etapa()` con
     `autor`, `rev1`, `fix1` y `rev2`, y exige fotos inicial y final para ambas fases no
     revisoras.
   - `test_vivas_frescas_y_archivo_compartido_entre_fases` usa JSON de `vivo/` con la
     forma real e incorpora `cola_terminada` con señal fresca; confirma que no se anota
     como viva.
   - `test_c5_git_roto_no_detiene_la_cola_y_desplegar_vuelve_al_control_amplio` ahora
     prueba también un `GIT_BASE` vacío: un archivo nuevo sin catálogo sigue bloqueando.
   - `test_foto_real_entrega_fuentes_relativas_y_desplegar_filtra_con_ellas` invoca
     `foto()` real contra un catálogo con `fuente`, `destino` y `despues`, dentro de un
     vault temporal. Confirma que entrega `pi/propio.py` (no la ruta absoluta) y que
     `desplegar()` pide sólo la entrada propia, no la ajena.
   - El primer punto cubre además que una regresión a tramos filtrados en árbol extra
     no pase inadvertida.

### Salida real de las suites

```text
$ NODO_PRUEBAS=1 python3 encargos/test_diff_propio.py
Ran 9 tests in 0.816s
OK

$ NODO_PRUEBAS=1 python3 encargos/test_matriz_cuota.py
Ran 28 tests in 3.946s
OK

$ NODO_PRUEBAS=1 python3 encargos/test_acciones_cola.py
Ran 48 tests in 7.128s
OK (skipped=1)

$ NODO_PRUEBAS=1 python3 pi/test_cockpit_paginas.py
FAIL: test_la_skill_ya_no_ofrece_el_experimento_para_menor
Ran 159 tests in 27.726s
FAILED (failures=1)
```

La falla de Cockpit no depende de estos cambios: compara byte a byte
`encargos/skill-encargar/SKILL.md` con la copia instalada de esa skill, que ya difieren.
No se reemplazó esa skill fuera del alcance de este encargo. No se desplegó nada.

El veredicto corresponde a Claude (Cami), no al informe de Codex.
