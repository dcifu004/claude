# Encargo 9092n — Revisión 1 de 90 + 92 (Codex, 25-10-2026)

Solo revisión: no se modificó código. El diff propio pedido en
`~/encargos-logs/cola9092n-9092n-diff.txt` no existe porque la cola no logró
reconstruir fotos de fases propias; revisé su salida primero y, para no sustituirla por el
relato del autor, revisé completo el diff integrado `encargos/9092n-diff-nube.txt` (2.653
líneas), incluidos archivos nuevos y modificaciones. No hay sección «Cambios ajenos» en ese
artefacto. Los cambios corresponden a los planes 90 y 92; la integración adicional de Spotify
queda dentro del encargo explícito de revisión.

No hay resultados anteriores `9092nr*-RESULTADO.md` que cerrar. Tampoco existen
`9092n-decisiones.md`, `9092n-busquedas.jsonl` ni `manual-busquedas.jsonl`; por tanto no hubo
búsqueda Tavily ni manual atribuible a la ventana de esta fase.

Todas las ejecuciones usaron un `mktemp -d` y fijaron `BOTV3_USO_CUENTAS`,
`BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` dentro de él. La reproducción de `/uso` tomó la fixture
de forma real `margen-normal.json` mediante `panel_de`: devolvió `imagen`, hizo exactamente un
envío de foto PNG y cero textos. La reproducción del contador dejó `consulta:auto` para
«cuéntame un chiste» y `spotify` para una orden que el manejador sí tomó; por tanto la marca
condicional de Spotify es correcta.

## Pruebas (salida real)

```text
$ NODO_PRUEBAS=1 BOTV3_USO_CUENTAS=<tmp>/uso-cuentas.jsonl BOTV3_USO_RUTAS=<tmp>/uso-rutas.json BOTV3_STATE_DIR=<tmp>/state python3 -B -m unittest -v botv3/test_botv3.py
Ran 490 tests in 9.260s
FAILED (failures=49, errors=143, skipped=113)

$ ... python3 -B -m unittest -v botv3/test_contador.py
Ran 17 tests in 1.822s
OK

$ ... python3 -B -m unittest -v botv3/test_uso_imagen.py
Ran 13 tests in 7.838s
OK

$ ... python3 -B -m unittest -v botv3/test_spotify.py
Ran 8 tests in 0.081s
OK (skipped=1)

$ ... python3 -B -m unittest -v botv3/test_clima_imagen.py
Ran 45 tests in 5.615s
OK

$ ... python3 -B -m unittest -v pi/test_margen_panel.py
Ran 14 tests in 0.300s
OK

$ ... python3 -B -m unittest -v pi/test_uso.py
Ran 7 tests in 0.100s
OK

$ ... python3 -B -m unittest -v pi/test_cuentas_uso.py
Ran 74 tests in 1.035s
FAILED (failures=1)
```

La falla de `pi/test_cuentas_uso.py` es la aserción de tope real (`95 != 90`), la única que guarda la línea base
`~/encargos-logs/cola9092n-base.json`; es previa. Las 49 fallas y 143 errores de
`test_botv3.py` son de módulos opcionales que esta copia no importa (por ejemplo, compras,
boleta y temporizadores). El antes/después entregado por el autor ya los registra como fallas
previas; no están en el diff de 90/92 ni los introduce el envoltorio. La cuenta local difiere
del antes/después porque aquí hay menos dependencias ausentes, no porque aparezcan fallas nuevas.

## Hallazgos, de más grave a menos grave

### 1. [Media] `test_contador.py` sale a la red y puede enviar una nota de voz real

`botv3/test_contador.py:121-130` toca todos los botones del menú, incluido `menu:clima`, sin
reemplazar `datos_clima`; éste termina en la consulta externa de
`botv3/botv3.py:4507-4526`. Además, `test_contador.py:153-157` ejercita voz sin reemplazar
`send_voice`, que llama directamente a `SES_TELEGRAM.post` en `botv3/botv3.py:5205-5214`.
Esto contradice el encabezado de la prueba («Nada sale a la red») y el aislamiento exigido para
la revisión. Con un entorno que tenga conectividad y token, la segunda rama puede enviar el
audio de prueba al chat 7; el resultado queda además dependiente de la red.

**Reproducción:** la suite aislada anterior quedó verde, pero su salida contiene llamadas reales
a `api.open-meteo.com`, `api.telegram.org/bot/sendVoice` y al buscador. No se concretaron por
fallar DNS en este entorno. El contador de errores pasó igual, por lo que la suite no detecta
la fuga.

**Arreglo:** en el `setUp` reemplazar `datos_clima`, `send_voice` y cualquier transporte que
pueda alcanzar red; luego afirmar los llamados simulados. Así cada caso se mantiene dentro de
su temporal y es determinista.

### 2. [Media] `/usos` omite Spotify y boleta de «Sin usar nunca» aunque sí los registra

`botv3/botv3.py:8489-8498` arma el catálogo que se entrega a
`usos.resumen()`, pero no añade `spotify` ni `boleta`. Ambos son funciones canónicas de
`botv3/usos.py:44-52`, y el propio bloque de marcas registra `atender_spotify` como
`spotify` (`botv3/botv3.py:8460-8469`) y `correccion_boleta` como `boleta`. Por tanto, si no
se han usado, el resumen no las muestra; si se usan, aparecen en el histórico, pero nunca
figurarán como pendientes. Incumple el plan 92: informar lo nunca usado «de entre lo que ese
bot tiene».

**Reproducción:** con un bot aislado, una frase no tomada por Spotify dejó
`consulta:auto` y una pausa reconocida dejó `spotify`, confirmando la marca correcta. En el
mismo proceso, `sorted({'boleta', 'spotify'} - catalogo_usos())` devolvió
`['boleta', 'spotify']`.

**Arreglo:** incluir `boleta` cuando esa ruta está activa y `spotify` cuando el perfil lo
tiene configurado (o derivar el catálogo, con esas condiciones, desde las funciones realmente
alcanzables). Agregar una prueba de ambos casos antes de publicar `catalogo.json`.

## Verificaciones sin hallazgo

- `/uso` no recalcula: toma sólo `panel` de `bots-info --margen`, tiene lista blanca estricta
  y conserva el respaldo a `uso-agentes`; la foto ambigua no duplica texto. Las pruebas de la
  forma real de `uso.json`, reglas de `--panel` y PNG pasaron.
- El registro no conserva texto: sólo escribe las cinco claves cerradas, con `O_APPEND`; los
  casos no autorizados no anotan. La excepción de escritura conserva la respuesta del bot.
- El callback valida chat y usuario antes de procesar datos. El drop-in propuesto es sólo
  lectura y no está instalado; no se observaron rutas a vaults fuera de los usos previstos ni
  impresión de tokens en lo nuevo.
- Respuestas largas, fuentes, rutas y voz se ejercitaron en `test_botv3.py`; los casos nuevos
  de respuesta larga con fuentes y sin vista previa pasaron. La marca de Spotify no secuestra
  frases que no toma el manejador.
- Sin ejecutar JavaScript, el tokenizador de `pi/test_cuentas_uso.py` validó paréntesis,
  corchetes, llaves, comentarios, regex y template literals de los cuatro JS de Cockpit y del
  nuevo `genera-cargaDe-js.mjs`: todos balanceados.

VEREDICTO: DESPLEGABLE
