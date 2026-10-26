# Encargo 92bn — Revisión 1 de los arreglos 92b (Codex, 25-10-2026)

Solo revisión: no se modificó código. Leí primero
`/home/dcifu004/encargos-logs/cola92bn-92bn-diff.txt`; no contiene diff porque
la reconstrucción del historial falló. Como contraste disponible, revisé completo
`encargos/92bn-diff-nube.txt` y comparé los dos archivos vigentes contra
`botv3/botv3.py.antes-nube2` y `botv3/test_contador.py.antes-nube2`: son los
mismos dos cambios, sin bloque «Cambios ajenos» (cinco líneas funcionales en el
catálogo y el aislamiento/pruebas del contador).

No existe `92bn-PLAN.md` ni la cola declara `plan = true`; tampoco existen
`92bn-decisiones.md`, `92bn-busquedas.jsonl`, `manual-busquedas.jsonl`,
`92bn-RESULTADO.md` ni una revisión anterior `92bnr*-RESULTADO.md`. Para el
informe de autor disponible usé la sección «Arreglos vuelta 1» de
`92-RESULTADO.md`. No hubo búsquedas Tavily o manuales que auditar. El único
archivo parecido, `manual-busquedas-prueba-encargo32.jsonl`, es de otro encargo.

Todas las ejecuciones y reproducciones usaron un `mktemp -d`, con
`BOTV3_USO_CUENTAS`, `BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` dentro de él. No se
leyó ni escribió ningún libro real.

## Cierre de la revisión anterior

No hay una revisión `92bnr` previa. Las dos medias de `9092nr-RESULTADO.md` son
el antecedente material: la de catálogo queda cerrada (con los perfiles reales
Jaime y Pilar, `boleta=True` y `spotify=True` cuando están habilitados); la de
red no queda cerrada, por el hallazgo 1.

## Pruebas (salida real)

```text
$ NODO_PRUEBAS=1 BOTV3_USO_CUENTAS=<tmp>/uso-cuentas.jsonl BOTV3_USO_RUTAS=<tmp>/uso-rutas.json BOTV3_STATE_DIR=<tmp>/state python3 -B botv3/test_botv3.py
Ran 490 tests in 17.150s
OK (skipped=4)

$ NODO_PRUEBAS=1 BOTV3_USO_CUENTAS=<tmp>/uso-cuentas.jsonl BOTV3_USO_RUTAS=<tmp>/uso-rutas.json BOTV3_STATE_DIR=<tmp>/state python3 -B botv3/test_contador.py
FAIL: test_cada_comando (__main__.CadaUsoDejaUnaLinea.test_cada_comando)
AssertionError: ["socket.getaddrinfo ('127.0.0.1', 3678)"] != [] : la prueba intentó salir a la red
Ran 20 tests in 0.833s
FAILED (failures=1)

$ NODO_PRUEBAS=1 BOTV3_USO_CUENTAS=<tmp>/uso-cuentas.jsonl BOTV3_USO_RUTAS=<tmp>/uso-rutas.json BOTV3_STATE_DIR=<tmp>/state python3 -B botv3/test_spotify.py
Ran 8 tests in 0.081s
OK (skipped=1)

$ NODO_PRUEBAS=1 BOTV3_USO_CUENTAS=<tmp>/uso-cuentas.jsonl BOTV3_USO_RUTAS=<tmp>/uso-rutas.json BOTV3_STATE_DIR=<tmp>/state python3 -B botv3/test_uso_imagen.py
Ran 13 tests in 7.844s
OK
```

La línea base `cola92bn-base.json` anota un fallo previo con el mismo nombre.
Pero la reproducción inmediata con `test_contador.py.antes-nube2`, el código
vigente y el mismo entorno temporal dio `Ran 17 tests ... OK` (intentando red de
verdad). Por tanto el cambio de esta etapa es el que transforma ese recorrido
en una falla visible en el árbol integrado; no es posible atribuir esta falla
nueva sólo a la línea base.

También forcé un `socket.getaddrinfo()` atrapado dentro de una subclase de
`SinRed`: la guarda lo bloqueó y el `addCleanup` hizo fallar el caso. Es decir,
la guarda cumple su mecanismo; el defecto es que un camino real de la propia
suite no fue sustituido. La reproducción del catálogo cargó `botv3.py` y los
TOML reales: Jaime y Pilar tienen ruta `boleta`, configuración Spotify y módulo
Spotify disponibles, y ambos incluyen las dos funciones en `catalogo_usos()`.

## Hallazgos, de más grave a menos grave

### 1. [Grave] La nueva guarda deja roja `test_contador.py` cuando Spotify está desplegado

`botv3/test_contador.py:171-180` recorre todos los alias, incluido `/spotify`,
pero su aislamiento en `:143-145` sólo sustituye las sesiones propias de
`botv3.py`; no sustituye `spotify_mod`. El comando real llega a
`botv3/botv3.py:6825-6846`, que llama `spotify.estado()`, y éste usa
`requests.request()` en `botv3/spotify.py:164-172`. La guarda global de
`test_contador.py:59-62` bloquea correctamente la resolución de
`127.0.0.1:3678`, pero el `addCleanup` de `:104-106` transforma el intento en
la falla mostrada arriba.

Esto ocurre con la forma real de esta copia: `spotify.py` importable y el bloque
`spotify = { api = "http://127.0.0.1:3678", ... }` del perfil Jaime. La prueba
nueva usa en cambio `types.SimpleNamespace()` para sólo el catálogo
(`test_contador.py:305-327`), forma suficiente para una pertenencia pero que no
ejercita el comando real que el mismo `test_cada_comando` invoca. Así, el informe
de Claude (Diego), que venía de una copia sin `spotify.py`, quedó verde sin
cubrir la integración presente.

**Cómo reproducir:** ejecutar la segunda orden de la sección anterior en un
temporal. Da `socket.getaddrinfo ('127.0.0.1', 3678)` y `FAILED (failures=1)`;
no abre la conexión porque la guarda la intercepta. Para cerrar, el `setUp` debe
simular explícitamente las operaciones de `spotify_mod` que usa `/spotify`
(como mínimo `estado` y, si corresponde, `codigo`) y afirmar la llamada, o
sustituir el transporte de `spotify.py`; se debe conservar la guarda como última
barrera. Después la suite tiene que volver a verde con el módulo real presente.

## Verificaciones sin hallazgo

- `catalogo_usos()` añade `boleta` sólo con la ruta activa y `spotify` sólo con
  módulo y configuración (`botv3/botv3.py:8489-8503`). La reproducción con los
  perfiles reales confirmó ambas inclusiones; las pruebas nuevas también cubren
  la ausencia de ruta, configuración y módulo.
- La guarda no permite una fuga silenciada: una llamada de resolución atrapada
  produjo igualmente una falla al limpiar el caso. No se observaron tokens en
  la salida ni cambios de callbacks, vaults o archivos temporales del producto.
- `test_botv3.py` pasó completo, incluido
  `test_respuesta_larga_con_cuenta_llega_entera_con_fuentes_y_sin_preview`
  (`botv3/test_botv3.py:974-993`) y las pruebas de voz por ruta. Por tanto no
  apareció regresión en respuestas largas, fuentes, rutas o voz fuera de la
  falla de aislamiento indicada.
- El alcance contrastado sólo modifica Python; no hay JavaScript nuevo que
  tokenizar.

VEREDICTO: NO DESPLEGABLE
