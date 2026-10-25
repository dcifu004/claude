# 88cr — revisión 1 de 88c

Sólo revisión: no se modificó código. El diff propio completo de la etapa
`cola88-88c-diff.txt` se leyó antes de revisar: comprende los cambios de autor y no trae
sección «Cambios ajenos». No existe `88c-PLAN.md`, `88c-decisiones.md`,
`88c-busquedas.jsonl` ni `encargos/manual-busquedas.jsonl`; por tanto no hay decisiones que
reabrir ni búsquedas que auditar. Sí existe solamente
`manual-busquedas-prueba-encargo32.jsonl`, que no corresponde a esta etapa.
No había informes `88cr*-RESULTADO.md` anteriores que cerrar.

Las reproducciones se hicieron en directorios creados con `mktemp -d`, con
`BOTV3_USO_CUENTAS`, `BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` apuntando allí. No se leyó ni
escribió ningún libro real.

## Cierre de la revisión anterior

Los ocho hallazgos de `88ar3-RESULTADO.md` quedaron cerrados.

| Hallazgo previo | Verificación independiente |
|---|---|
| 1. Fuente con `@` | `pi/nodo-desplegar.py:174,621-639`: `leer_fuente("pi/spotify/spotify@.service")` devolvió los bytes reales; las formas con `..` y absoluta se rechazaron. |
| 2. Bootstrap partido | `pi/spotify/LEEME.md:27`: `shlex.split()` dejó un único argumento después de `--`, con los cinco pasos. |
| 3. Binario y altas | El binario tiene modo `0755`, 17.491.240 B y SHA-256 `9130ee00613abeb9620cc06fe9bc7080eba73618d547b0c71ec991f3504dc5ff`; los cinco hashes documentados coinciden con los artefactos y el objetivo literal. |
| 4. Enlace repetido | `pi/nodo-desplegar.py:957-981,1314-1437`: un enlace igual produjo `sin cambios`; uno a otro objetivo se rechazó; el hash se valida antes de aceptarlo y el revert deja el respaldo del objetivo publicado. |
| 5. Fixture | El esquema mide 13.895 B y su SHA-256 es `e6a3cf037c27af877c35183b51e8df82c88ef0e2fb88ecd38ee2cca3a5ee50cc`. |
| 6–8. Documentación y detalles | `LEEME.md:50-56` explica la subida de versión; no hay nombres personales prohibidos nuevos; `limpiar_temporales()` borra sólo regulares de un enlace, con patrón exacto, en padres derivados del catálogo. El prefijo redundante y el `|| test` ya no están. |

La reproducción integrada dejó exactamente:

```text
{"fuente_real": true, "rechazos": ["pi/spotify/../spotify@.service", "/pi/spotify/spotify@.service"], "bootstrap_argumentos_post_guion": 1, "bootstrap_pasos": 5, "enlace_repetido": "sin cambios", "enlace_distinto_rechazado": true, "temporal_borrado": true, "archivo_parecido_conservado": "conservar"}
inicio_con_padre_enlace=ok
```

El segundo renglón corresponde al caso adversarial de un padre del perfil convertido en enlace:
la limpieza lo omite y el escucha sí inicia. No sigue el enlace ni borra fuera de la carpeta
permitida.

## Seguridad y regresiones

- `RE_FUENTE` sólo agregó `@`; conserva el rechazo de rutas absolutas y de `..`.
- La limpieza abre las carpetas tramo a tramo, sin seguir enlaces, y sólo elimina un archivo
  regular, de un enlace, cuyo nombre completo coincide con
  `.nombre.nodo-desplegar-<16 hex>` (`pi/nodo-desplegar.py:836-877`).
- El cambio no altera callbacks, lectura de vaults ajenos ni manejo de tokens. Los hashes y el
  binario se muestran como datos verificables, no como secretos.
- No hay JavaScript en el diff propio; no correspondía ejecutar un tokenizador JS.
- Las pruebas de `botv3` que cubren respuestas largas con fuentes, rutas y voz pasaron en la
  corrida final. Tampoco hay cambios de esas rutas en el diff.

## Suites ejecutadas

```text
$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK

$ python3 pi/test_nodo_desplegar.py
Ran 93 tests in 4.735s
OK

$ python3 botv3/test_botv3.py
Ran 490 tests in 16.450s
OK (skipped=4)

$ python3 botv3/test_temporizadores.py
✅ todo en verde

$ python3 botv3/test_compras.py
✅ todo en verde

$ python3 botv3/test_spotify.py
python3: can't open file '.../botv3/test_spotify.py': [Errno 2] No such file or directory

rc: plantillas=0 nodo=0 botv3=0 temporizadores=0 compras=0 spotify=2
```

La suite inexistente conserva el rc 2 anotado en la línea base
`cola88-base.json`, así que no es una falla nueva. En la primera corrida completa,
`botv3/test_botv3.py` tuvo una aserción intermitente de ventana temporal en
`test_70r1_cambiar_el_envio_mientras_espera_el_check_no_entrega`; la prueba aislada y una
segunda corrida completa pasaron. Su archivo no aparece en el diff de 88c, por lo que no se
atribuye a esta etapa.

## Hallazgos

No se identificaron hallazgos atribuibles a 88c.

## Veredicto

El arreglo cumple el encargo aprobado sin ampliar el alcance y no deja una regresión comprobable
en los flujos existentes. Está listo para el despliegue manual que documenta la etapa.

VEREDICTO: DESPLEGABLE
