# Plan 92: contador de uso de los bots (alternativa A)

## Enfoque

- **Un solo punto de registro: `handle_update()`**, la puerta única de cada mensaje y cada botón
  (`botv3/botv3.py` ~8166). Abre un contexto del uso (bot, canal y función) y, al terminar, escribe **una**
  línea, con resultado `error` si hubo una excepción o algún error. No se toca ninguna rama del
  despachador. Así queda en bloques chicos que no chocan con el 90, que cambia `comando_uso`.
  - **Canal:** `voz` si el mensaje trae `voice`/`audio`, `boton` si es un `callback_query`, y `texto` en los
    demás casos (también los adjuntos).
  - **Función:**
    - **comando:** sale del nombre, con una tabla de alias a la función canónica (`/timer` → `temporizadores`,
      `/start` → `menu`…). Un comando desconocido queda como `desconocido`, sin guardar lo escrito;
    - **botón:** sale del prefijo de `callback_data` (`menu:clima` → `clima`, `cmp:…` → `compras`…);
    - **frase o voz:** la pone el primer manejador que la toma. Es una tabla `MARCAS` aplicada al final del
      módulo, que envuelve por nombre `proponer_memoria`, `atender_temporizador`, `atender_hora`,
      `atender_comuna`, `atender_clima`, `atender_gasto_dicho`, `atender_frase_google`, `atender_nodo`,
      `atender_compras`, `submit_query` (→ `consulta:<ruta>`)… Las que devuelven bool marcan sólo si
      devuelven verdadero.
  - **Resultado:** `error` si el manejador lanzó, si `audit` se llamó con `status="error"` o si se mandó un
    texto que parte con «❌».
- **Nunca se guarda el texto del mensaje**: sólo `{t, bot, funcion, canal, resultado}`, con las funciones de
  una lista cerrada. Un mensaje no autorizado no se cuenta.
- **Escritor que no falla nunca:** `botv3/usos.py` (módulo puro, que también usa `bots-info`).
  - Agrega con `O_APPEND`, en una sola escritura.
  - Ante cualquier `OSError` el bot contesta igual y queda **una** advertencia en el log.
- **Archivo y retención:**
  - un archivo por mes, `STATE_DIR/usos/usos-AAAA-MM.jsonl` (ruta configurable con `BOTV3_USOS_DIR`), dentro
    del volumen cifrado;
  - se guardan **180 días**: medio año alcanza para ver si una función se dejó de usar en una temporada, y una
    línea pesa ~90 bytes;
  - **rotación sin perder líneas:** nunca se renombra ni se reescribe un archivo. Cada línea va al archivo de su
    mes, y sólo se borra un archivo cuyo mes terminó hace más de 180 días.
- **Resumen: `/usos`** (y no un botón en `/menu`). Es una consulta de mantenimiento que se usa poco; `/menu`
  es para lo de todos los días y Pilar lo quiere corto (decisión del 19-10 sobre la lista de comandos).
  - Muestra los últimos 7 días por bot y función, con el desglose por canal y los errores, y lo que **nunca**
    se usó en los 180 días de entre lo que ese bot tiene.
  - **Pilar** ve sólo lo suyo. **Jaime** ve los dos si puede leer el registro de Pilar (`BOTV3_USOS_OTROS`);
    si no, lo dice.
  - Jaime hoy tiene `botv3-pilar` en `InaccessiblePaths`. Se deja como **propuesta** un drop-in con un
    `BindReadOnlyPaths` sólo de `botv3-pilar/usos` (`encargos-nube/92-propuesta-jaime-usos-pilar.conf`), sin
    instalar.
- **Cockpit:** `bots-info` agrega `usos_bots`, el mismo resumen como JSON, leyendo el `usos/` de cada perfil
  con el `usos.py` desplegado. La página no se hace.

## Pruebas (`botv3/test_contador.py`)

Cubren:
- cada comando de `update_telegram_commands.py` y de `/ayuda`, y cada botón de `/menu`, dejan una línea;
- el canal sale bien para voz, texto y botón;
- el texto del mensaje nunca está en el archivo;
- un directorio que no se puede escribir no rompe la respuesta y avisa una sola vez;
- el resumen cuenta bien y respeta Pilar frente a Jaime;
- la rotación a través de meses no pierde líneas y borra sólo lo de más de 180 días.

`bots-info` `usos_bots` se prueba con temporales. Sin fallas nuevas en `botv3/test_botv3.py` ni en
`pi/test_cuentas_uso.py`. Línea base, la misma de `origin/main`: `test_botv3` 49 F + 156 E y `test_cuentas_uso`
1 F + 9 E.
