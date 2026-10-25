# Resultado del encargo 87: cierre barato en rev2/rev3 (Claude (Diego), en la nube, 25-10-2026)

Hecho fuera de la Pi, en una copia parcial de 11-Pi5 (sin `/opt/nodo`, sin Telegram, sin secretos), en la
rama `claude/cool-cannon-ee8axd`. Falta la revisión cruzada en la Pi.

## Lo hecho

1. **Plan corregido** (`encargos/87-PLAN.md`, v2), con la sección «Respuesta a 87rplan» (H1–H4). Se commiteó
   y subió antes de implementar.
2. **`cierre_barato = true`** (opt-in; sólo el booleano `true`; nunca en etapas remotas). Antes de cada
   rev2+ la cola decide desde `GIT_BASE["<id>:fases"]` y git: revisión completa si E1 (archivo fuera del diff
   propio previo), E2 (`RUTAS_SENSIBLES` o `RE_SECRETO`), E3 (más de 150 líneas en `--numstat` o un binario)
   o E4 (falta una foto, git falla, hay `arboles_extra` o falta `<id>r<N-1>-RESULTADO.md`). Si no se cumple
   ninguna, corre `cierre`.
3. **Fase `cierre`**: nivel `agil` del revisor (o `modelo_cierre`/`esfuerzo_cierre`), con `exigir_candado`,
   `esfuerzo_incompatible` y `chequear_cuota`. Borra `<id>r-RESULTADO.md` antes de correr, se corta a los
   `CIERRE_MAX_MIN = 30` min y deja la fila `fase = revN`, `rol = cierre`. Sólo valen las últimas 3 líneas, con
   una única línea `VEREDICTO: …` exacta. ESCALAR, sin línea, rc ≠ 0, corte por tiempo o archivo no escrito
   llevan a la revisión completa en la misma vuelta. NO DESPLEGABLE copia `<id>r<N>-RESULTADO.md` y sigue a
   `consultar_o_seguir` y al arreglo, como hoy. Sin cuota: `Pausa` en `<id>:revN`, y al reanudar se
   recalcula E1–E4.
4. **Pronóstico**: `pronostico()` mapea `cierre → rev` y le aplica el factor 0,3 con menos de 3 filas propias.
   `fases_pendientes`, `fases_restantes` y `restante` usan `rol_de_fase()`. El máximo de la ETA suma la
   revisión completa además del cierre. `--simular` agrega la línea `cierre … [débil, factor 0,3]`.
5. **`balance.py` sin cambio**: `RETRABAJO` mira `fase` y el cierre se anota como `rev2`/`rev3`, así que ya
   cuenta como retrabajo (H2).

## Archivos tocados

- `encargos/cola-run.py` (+230 −19): constantes `PLANTILLA_CIERRE`, `RUTAS_SENSIBLES`, `CIERRE_MAX_LINEAS`,
  `CIERRE_MAX_MIN`, `VEREDICTO_CIERRE`. Funciones nuevas: `cierre_aplica`, `_numstat`, `_sensible`,
  `decidir_cierre`, `veredicto_cierre`, `_seccion_arreglos`, `prompt_cierre`, `correr_cierre` y `rol_de_fase`.
  Funciones cambiadas: `modelo_de`, `esfuerzo_incompatible`, `validar_esfuerzos`, `modelos_con_candado`,
  `exigir_candado`, `pronostico`, `restante`, `fases_pendientes`, `fases_restantes`, `correr`/`_correr`
  (`limite_s` opcional; con `None`, igual que hoy), `etapa` (un bloque previo a la `revN`, que queda intacta)
  y la salida de `--simular`.
- `encargos/revision-cierre-plantilla.md` (nueva, sólo se lee).
- `encargos/test_cierre_barato.py` (nueva, 33 pruebas).
- `encargos/87-fixtures/`: copias de `cola-82.toml`/`cola-85.toml`, `simular-antes-82.txt`/`-85.txt` y
  `genera-simular-antes.py`, que las generó con la foto base (`origin/main:encargos/cola-run.py`,
  sha256 `da22939d1e35827b88f96c9f6b17dbffd072719cc2ed0f2f574b90df90b914cb`).
- `encargos/87-PLAN.md` (v2).
- **No se tocaron** `revision-plantilla-v2.md`, `historial.jsonl`, `modelos.toml`, `balance.py` ni
  `test_balance.py` (`git diff --quiet HEAD -- …` → sin cambios).

## Decisiones

- Un archivo de otra cola viva que cae dentro del diff del arreglo escala por E1: ante la duda, completa.
- `encargos/revision-*plantilla*` se agregó a `RUTAS_SENSIBLES` para cubrir también la plantilla nueva.
  `RE_SECRETO` se reusa.
- El cierre aplica a toda revN con N ≥ 2. Con `vueltas = 2` eso es rev2 y rev3.
- La sección «Arreglos vuelta N» se pasa tal cual. Si falta, va un aviso y la plantilla pide ESCALAR.
- Un cierre que escala no guarda copia propia de su informe: la revisión completa lo borra antes de
  correr, como hoy.
- La fila sintética de balance va en `test_cierre_barato.py`, no en `test_balance.py`, para no tocar esa suite.

## Criterios

Comando: `NODO_PRUEBAS=1 python3 -B -m unittest encargos/test_cierre_barato.py`, desde la raíz.

- **C1. Cumplido.** `test_simular_igual_byte_a_byte_a_la_foto_base` compara contra
  `simular-antes-*.txt`, y `test_corrida_de_dos_vueltas_sin_campo` da `autor rev1 fix1 rev2 fix2 rev3` /
  `autor rev fix rev fix rev`, sin `limite_s` ni `rol` en vivo.
- **C2. Cumplido.** Con un `fix1` de 20 líneas, la fila `rev2` queda con rol `cierre` y `gpt-reserve medium`
  [agil]. La instrucción trae el `r1` y `+# cambiada 9`, y no trae `SOLO_DEL_AUTOR` (un archivo que sólo tocó
  el autor) ni el `-diff.txt` de la etapa.
- **C3. Cumplido.** E1, E2 (`pi/x.service` y `encargos/modelos.toml`), E3 (151 líneas; con 150 todavía es
  cierre) y E4 (sin foto previa, git que falla, `arboles_extra`) dan `rev2` completa `gpt-5.6-terra xhigh`
  [maximo], sin cierre. Además, un fix que deja su propio `87r-RESULTADO.md` escala por E1.
- **C4. Cumplido.** ESCALAR, sin veredicto, rc 1, un resultado previo no reescrito, DESPLEGABLE en la línea 10
  de 40, veredictos con espacios o mayúsculas raras y el corte por tiempo dan siempre `(rev2, cierre)` y luego
  `(rev2, rev)`. `_correr` corta de verdad un `claude` falso (`exec sleep 5`, `limite_s = 0,5`) con rc 124.
- **C5. Cumplido.** Con NO DESPLEGABLE del cierre se copia `87r2-RESULTADO.md`, `consultar_o_seguir` recibe
  `rev1` y `rev2`, y siguen `fix2` y el cierre de `rev3`.
- **C6. Cumplido.** `pronostico(cierre)` da rev × 0,3, `débil, factor 0,3`, sin `KeyError`.
  `fases_pendientes`/`fases_restantes` muestran `cierre` en rev2/rev3. `restante()` max = completa + 2 cierres.
  `--simular` muestra la línea `cierre`. `balance.py --desde 47` real da lo mismo con y sin filtrar `cierre`
  (hoy: «51 encargos, 203 fases · … · 884 de 1932 min en retrabajo»). Una fila real con `rol = cierre` en rev2
  suma a `min_ret`, y en rev1 no.
- **C7 (H4). Cumplido.** Un cierre sin cuota pausa en `87:rev2`. Después de `git_base_cargar()`, si E3 cambia,
  la reanudación corre la completa; si nada cambia, vuelve a cierre. La etapa remota no aplica. `vivo` trae
  `rol = "cierre"` sólo durante el cierre.

Mutaciones de control (se revirtieron): sin `"cierre": "rev"` en `pronostico()`, la suite da
`FAILED (errors=17)`; sin el `unlink` antes del cierre, falla
`test_resultado_que_ya_estaba_y_el_cierre_no_reescribe`.

## Salida de las suites del manifiesto (`NODO_PRUEBAS=1 python3 -B -m unittest encargos/<suite>.py`)

```
== test_cierre_barato
Ran 33 tests in 9.814s
OK
== test_fase_plan
Ran 8 tests in 0.867s
FAILED (errors=3)
== test_diff_propio
Ran 19 tests in 5.120s
OK
== test_balance
Ran 22 tests in 0.283s
OK
== test_pronostico
Ran 6 tests in 0.407s
OK
== test_consultas
Ran 80 tests in 29.641s
FAILED (errors=76, skipped=1)
== test_acciones_cola
Ran 41 tests in 8.586s
FAILED (errors=5)
```

## Fallas antes y después (lista exacta)

Son las mismas antes y después del cambio (`diff` de las listas `ERROR:/FAIL:` vacío en las 6 suites que ya
existían). Son del entorno, no de este encargo, y no se arreglaron:

- 74 por `/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/revision-plantilla-v2.md`
  (`PLANTILLA_REV` se fija al importar);
- 4 por `pi/nodo-desplegar.py`;
- 5 por `52br1`, `55r2`, `57br1` y `58r2-RESULTADO.md`, que faltan en la copia;
- 1 por el módulo `test_cockpit_paginas`.

Las suites `test_cierre_barato`, `test_diff_propio`, `test_balance` y `test_pronostico` no tienen fallas.
Las otras 7 suites de `encargos/` que no están en el manifiesto (`test_boletin_38`,
`test_capacidad_por_vencer`, `test_despachador`, `test_despacho`, `test_matriz_cuota`, `test_quema` y
`test_versiones`) también dan exactamente las mismas fallas con el `cola-run.py` anterior y con el nuevo
(fallas de entorno de la copia parcial).

### test_fase_plan
- `ERROR: test_c5_autor_recibe_el_plan_aprobado_y_revplan_es_medium`
- `ERROR: test_reanudar_main_desde_autor_no_repite_plan`
- `ERROR: test_reanudar_segunda_vuelta_no_se_salta`
### test_consultas
- `ERROR: test_aceptar_reanuda_sin_arreglo_y_anota_la_decision`
- `ERROR: test_al_vencer_la_ronda_se_vuelve_a_preguntar_hasta_el_plazo`
- `ERROR: test_arma_el_timer_antes_de_preguntar_y_lo_verifica`
- `ERROR: test_arreglar_reanuda_con_el_arreglo`
- `ERROR: test_c5_sin_consultar_cae_a_tres_sugerir_y_lo_anota`
- `ERROR: test_c5_una_sola_llamada_por_ronda_y_la_ronda_guarda_su_id`
- `ERROR: test_c6_aceptar_reanuda_sin_arreglo`
- `ERROR: test_c6_arreglar_reanuda_con_el_arreglo`
- `ERROR: test_c6_la_ronda_vieja_de_tres_ids_sigue_ignorando_lo_que_no_es_de_root`
- `ERROR: test_c6_saltar_deja_la_cola_estacionada`
- `ERROR: test_c6_un_resultado_que_no_es_de_root_se_ignora`
- `ERROR: test_c6_un_vivo_de_antes_se_resuelve_con_la_cola_nueva`
- `ERROR: test_c6_una_opcion_que_no_es_de_las_tres_se_ignora`
- `ERROR: test_cada_ronda_es_una_llamada_hasta_el_plazo`
- `ERROR: test_con_la_biblioteca_real_de_descanso_y_reloj_inyectado`
- `ERROR: test_con_la_consulta_abierta_el_timer_sigue`
- `ERROR: test_con_la_sesion_viva_no_se_toca`
- `ERROR: test_de_punta_a_punta_con_el_nodo_desplegar_de_antes_caen_tres_sugerir`
- `ERROR: test_de_punta_a_punta_consultar_un_mensaje_toque_b_y_la_cola_lo_lee`
- `ERROR: test_descanso_con_la_ronda_vencida_aplica_el_defecto_sin_preguntar`
- `ERROR: test_el_detector_no_es_vacuo_la_pregunta_vieja_si_se_habria_guardado`
- `ERROR: test_el_panel_ofrece_reanudar_a_una_cola_en_consulta`
- `ERROR: test_en_descanso_con_otras_esperando_salta_en_silencio`
- `ERROR: test_en_descanso_no_pregunta_y_si_es_la_ultima_se_arregla`
- `ERROR: test_falla_aceptar`
- `ERROR: test_falla_aceptar_arreglar`
- `ERROR: test_falla_aceptar_arreglar_con_otra_esperando`
- `ERROR: test_falla_aceptar_arreglar_saltar`
- `ERROR: test_falla_aceptar_arreglar_saltar_con_otra_esperando`
- `ERROR: test_falla_aceptar_con_otra_esperando`
- `ERROR: test_falla_aceptar_saltar`
- `ERROR: test_falla_aceptar_saltar_con_otra_esperando`
- `ERROR: test_falla_arreglar`
- `ERROR: test_falla_arreglar_con_otra_esperando`
- `ERROR: test_falla_arreglar_saltar`
- `ERROR: test_falla_arreglar_saltar_con_otra_esperando`
- `ERROR: test_falla_saltar`
- `ERROR: test_falla_saltar_con_otra_esperando`
- `ERROR: test_la_cola_que_parte_sin_consultas_ajenas_no_toca_systemd`
- `ERROR: test_la_consulta_no_lleva_titulos`
- `ERROR: test_la_consulta_no_lleva_titulos_y_el_escucha_real_no_los_guarda`
- `ERROR: test_la_orden_del_timer_procesa_un_resultado_del_escucha_y_lo_detiene`
- `ERROR: test_la_pregunta_hostil_sale_escapada_y_sugerir_real_la_acepta`
- `ERROR: test_la_ultima_revision_no_pregunta_no_hay_arreglo_detras`
- `ERROR: test_las_etiquetas_y_el_motivo_caben_y_pasan_la_validacion_real`
- `ERROR: test_las_rondas_siguientes_rehacen_el_resumen_y_no_copian_el_vivo`
- `ERROR: test_nombres_y_respuestas_hostiles`
- `ERROR: test_plazo_vencido_con_otras_colas_esperando_salta`
- `ERROR: test_plazo_vencido_siendo_la_ultima_va_al_arreglo`
- `ERROR: test_por_la_linea_de_comandos`
- `ERROR: test_rechazar_no_es_respuesta_y_el_primer_ok_gana`
- `ERROR: test_revisiones_reales_del_vault`
- `ERROR: test_revisiones_reales_del_vault`
- `ERROR: test_revisiones_reales_del_vault`
- `ERROR: test_revisiones_reales_del_vault`
- `ERROR: test_revisiones_reales_del_vault`
- `ERROR: test_saltar_deja_la_cola_estacionada_y_reanudar_la_retoma`
- `ERROR: test_si_consultar_falla_dos_veces_se_aplica_el_defecto_y_no_cae_a_sugerir`
- `ERROR: test_si_el_canal_no_vuelve_se_deja_de_reintentar_y_el_plazo_aplica_el_defecto`
- `ERROR: test_sin_timer_no_se_pregunta_y_se_aplica_el_defecto`
- `ERROR: test_sin_titulos_con_gravedad_es_como_antes`
- `ERROR: test_solo_medias_y_bajas_pregunta_y_la_cola_queda_estacionada`
- `ERROR: test_tercera_pregunta_en_la_misma_cola_no_se_hace`
- `ERROR: test_un_grave_no_pregunta_y_va_al_arreglo`
- `ERROR: test_un_reinicio_se_lleva_el_timer_y_la_proxima_cola_lo_rearma`
- `ERROR: test_un_resultado_con_otro_id_o_enlazado_se_ignora`
- `ERROR: test_un_resultado_que_no_es_del_escucha_root_se_ignora_y_se_anota`
- `ERROR: test_una_aceptacion_con_el_id_de_la_consulta_vale_solo_si_lo_elegido_fue_aceptar`
- `ERROR: test_una_aceptacion_fabricada_en_el_vivo_no_salta_el_arreglo`
- `ERROR: test_una_etiqueta_que_no_es_media_ni_baja_no_pregunta`
- `ERROR: test_una_falla_pasajera_se_reintenta_una_vez`
- `ERROR: test_una_falla_pasajera_se_reintenta_y_la_ronda_queda_completa`
- `ERROR: test_una_ronda_siguiente_a_medias_reintenta_lo_que_falta_con_el_mismo_plazo`
- `ERROR: test_una_ronda_siguiente_que_falla_se_vuelve_a_intentar_en_la_pasada_siguiente`
- `ERROR: test_una_ronda_vieja_a_medias_reintenta_por_sugerir_aunque_ya_haya_consultar`
- `ERROR: test_vencido_no_es_respuesta`
### test_acciones_cola
- `ERROR: setUpClass`
- `ERROR: test_con_la_marca_termina_la_fase_en_curso_y_no_empieza_la_siguiente`
- `ERROR: test_corta_deja_detenida_con_el_desde_de_la_fase_cortada_y_reanudar_retoma_ahi`
- `ERROR: test_entre_dos_etapas_deja_el_desde_de_la_etapa_siguiente`
- `ERROR: test_una_marca_que_sobro_no_pausa_a_la_corrida_siguiente_y_la_ultima_fase_la_suelta`

## Riesgos abiertos

- **No se corrió en la Pi.** Las fallas de entorno tapan, en esta copia, 3 pruebas de `test_fase_plan`, 76 de
  `test_consultas` y 5 de `test_acciones_cola`. En la Pi hay que confirmar que siguen verdes.
- El corte por tiempo mata sólo el proceso directo (`subprocess.run(timeout=…)`). Si `codex`/`claude` dejan
  hijos, pueden seguir vivos y, si la salida queda abierta, alargar la espera.
- Con otras colas vivas que escriben en el árbol durante el arreglo, el cierre casi siempre escala (E1). Es
  seguro, pero ahorra menos.
- E1–E4 se calculan sobre el árbol principal. Con `arboles_extra` se escala siempre.
- El revisor del cierre tiene las mismas herramientas que la `rev` (puede escribir archivos). Lo que cambie
  fuera de `<id>r-RESULTADO.md` no entra al diff de la revisión completa siguiente: es el mismo límite de hoy.
- `revision-cierre-plantilla.md` todavía no corrió con un modelo real. Su redacción se ajusta con las primeras
  filas `cierre`.

## Arreglos vuelta 1 (87b, 25-10-2026)

Rama `claude/encargo-87b-arreglos`, creada desde `base-87b`. Cierra los tres hallazgos de la revisión de Codex
(`encargos-nube/87nr-RESULTADO.md`, **NO DESPLEGABLE**). Archivos: `encargos/cola-run.py`,
`encargos/test_cierre_barato.py` (15 pruebas nuevas), `encargos/test_diff_propio.py` (una prueba adaptada) y
este informe. Las fallas antes y después están en `encargos-nube/87b-fallas-antes-despues.txt`.

### 1. [Grave] Enlaces simbólicos → cerrado

- `leer_informe(ruta)` nuevo: abre con `O_NOFOLLOW | O_NONBLOCK`, `fstat` de archivo regular con un solo nombre
  y hasta `CIERRE_MAX_BYTES` (512 KiB), UTF-8, y exige que su carpeta resuelta sea `encargos/`. Cualquier falla,
  también un archivo que falta, levanta `InformeInseguro`.
- Pasan por ahí todos los informes del cierre: `<id>r<N-1>-RESULTADO.md` y `<id>-RESULTADO.md` (en
  `decidir_cierre`, que da **E4** y la revisión completa), la revisión previa, la sección de arreglos y el plan
  en `prompt_cierre`, el informe final `<id>r-RESULTADO.md` en `correr_cierre`, y su copia y lectura en el camino
  NO DESPLEGABLE de `etapa()`. Ante cualquiera, ESCALAR.
- `correr_cierre` arma el prompt **antes** de pedir cuota. Así, un informe inseguro escala sin esperar cuota y
  sin llamar a `correr()`.
- Pruebas (`C8EnlacesSimbolicos`): `87-RESULTADO.md` cambiado por un enlace a un archivo de afuera con una
  sección «Arreglos vuelta 1» válida y un secreto (es la reproducción 1 de Codex): no se llama al cierre, no se
  pide cuota del cierre y el secreto no aparece en **ningún** prompt. También la revisión previa cambiada por un
  enlace entre la decisión y el prompt, el informe final del cierre como enlace (ESCALAR y revisión completa) y
  `leer_informe` contra enlace, archivo grande, binario, enlace duro, FIFO, carpeta, archivo que falta, `..` y
  subcarpeta.

### 2. [Grave] Procesos hijos, en TODAS las fases → cerrado

- `ejecutar_cli()` nuevo, usado por `_correr` en toda fase (autor, rev, fix, revplan, cierre). Lanza el CLI con
  `start_new_session=True` y espera con `communicate` en tramos de 0,5 s. Cuando vence el tiempo, o apenas el CLI
  sale (aunque un hijo retenga sus tuberías), `terminar_grupo()` manda TERM a todo el grupo, espera hasta 5 s,
  manda KILL y espera 2 s más. Después confirma por `/proc` que no quedó nadie vivo (los zombis no cuentan) y, si
  queda alguien, lo dice en stderr.
- **Arreglo que no estaba pedido, pero hace falta:** en su propia sesión, el CLI ya no recibía el SIGHUP de
  `tmux kill-session` (botón *detener*), así que habría seguido escribiendo después de detener la cola.
  Mientras corre un CLI, SIGHUP y SIGTERM a la cola matan primero el grupo y después la cola (código
  128 + señal). Ctrl-C o cualquier excepción también matan el grupo antes de subir.
- `_correr` conserva lo demás tal cual: mismo log, tokens, `modelo_real`, `sin_cuota` y la forma del corte
  (`rc 124`, `corte = "tiempo"`). `test_diff_propio` simulaba `subprocess.run` para ver los argumentos de Codex;
  ahora simula `ejecutar_cli` y afirma lo mismo.
- Pruebas (`C9GrupoDeProcesos`, con CLI falsos de verdad en el `PATH`): un CLI que lanza `sleep 30` en segundo
  plano y anota su PID. Con el corte a 1 s, el hijo no existe al volver (reproducción 2). En autor, rev1 y fix1
  normales, el hijo que deja el CLI muere y la salida JSON se lee igual. Un hijo que retiene stdout ya no cuelga
  la fase (antes esperaba sus 30 s). Un prompt de 300 KB llega entero y el `rc` se conserva. Y *detener*: SIGHUP
  a un proceso que corre `ejecutar_cli` mata al CLI y a su hijo. C1 (la salida de `--simular`, byte a byte) y
  el flujo de fases siguen en verde.

### 3. [Media] Colas vivas → cerrado

- El cruce por fase de `_propios_atribuidos()` pasó, sin cambiar su lógica, a `compartidos_de_fase(f, nombres)`.
  Lo usan el pedido de despliegue (como antes) y ahora también `decidir_cierre()`. Si la foto del arreglo
  registra otra cola viva y su registro falta, está abierto en el mismo tramo, no se lee o comparte una ruta con
  el arreglo, va revisión completa: «E1: fix1 comparte archivos con otra cola viva: <ruta> (<cola> [(registro
  abierto|dudoso)])».
- Pruebas (`C10ColasVivas`, con fotos git reales): cola ajena cerrada sin ruta en común (sigue el cierre),
  cerrada con `modulo.py` en común (escala, como la reproducción 3), abierta (escala), registro ilegible
  (escala), registro que falta (escala) y cerrada pero en otra hora (no cuenta, sigue el cierre).

### Pruebas (salida real, contenedor de la nube, `NODO_PRUEBAS=1` y estado en `mktemp`)

```
                antes del arreglo                               después
cierre_barato:  OK      Ran 33 tests                            OK      Ran 48 tests
fase_plan:      FAILED (errors=3)  Ran 8                        FAILED (errors=3)  Ran 8
diff_propio:    OK      Ran 19                                  OK      Ran 19
balance:        OK      Ran 22                                  OK      Ran 22
pronostico:     OK      Ran 6                                   OK      Ran 6
consultas:      FAILED (errors=76, skipped=1) Ran 80            FAILED (errors=76, skipped=1) Ran 80
acciones_cola:  FAILED (errors=5)  Ran 41                       FAILED (errors=5)  Ran 41

$ python3 encargos/test_cierre_barato.py      (como la cola)
Ran 48 tests in 11.591s
OK
```

La lista de las 84 fallas es **idéntica** antes y después (`diff` vacío). Son del entorno de esta copia: faltan
`/opt/nodo/.../revision-plantilla-v2.md`, `pi/nodo-desplegar.py` y algunos `NNr*-RESULTADO.md` viejos. En la Pi
las 7 suites pasaban. Las 14 pruebas nuevas de los tres hallazgos, corridas contra el `cola-run.py` **anterior**,
dan `FAILED (failures=10, errors=1)`. Las 3 que pasan con ambos son las de «sigue igual»: prompt entero y rc,
cola ajena sin ruta en común y cola ajena de otra hora. La de *detener* se agregó después.

### Riesgos abiertos

- Un nieto que haga `setsid` sale del grupo y no muere. Si además retiene las tuberías, la fase espera 10 s, las
  cierra y su salida se pierde (queda anotado en el log). Ningún CLI conocido lo hace.
- La espera en tramos de 0,5 s agrega como mucho medio segundo por fase.
- `procesos_del_grupo` lee `/proc` (la Pi es Linux). Sin `/proc` usa `killpg(pgid, 0)`, que cuenta los zombis
  como vivos.
- `leer_informe` también se exige al plan del prompt del cierre. El chequeo de plan aprobado e inmutable de
  `etapa()` (hash) sigue leyendo como antes.
- Los manejadores de SIGHUP/SIGTERM solo se instalan desde el hilo principal, que es donde corren las fases.
  Desde otro hilo queda el `finally` (Ctrl-C o excepción), pero no la señal.
