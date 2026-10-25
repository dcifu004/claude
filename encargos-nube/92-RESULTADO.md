# Resultado 92: contador de uso de los bots (Claude (Diego), en la nube, 25-10-2026)

Rama `claude/cool-cannon-ee8axd-92`, alternativa A. Plan en `encargos-nube/92-PLAN.md` (primer commit). Falta la
revisión cruzada (Codex) y el despliegue en la Pi.

## Lo hecho

- **Registro:**
  - una línea por uso, `{"t", "bot", "funcion", "canal", "resultado"}`, en
    `STATE_DIR/usos/usos-AAAA-MM.jsonl`, que se puede cambiar con `BOTV3_USOS_DIR`;
  - `funcion` sale de una lista cerrada: las funciones canónicas o `consulta:<ruta>`. Lo demás queda como
    `desconocido`, así que **el texto del mensaje nunca se guarda**;
  - el escritor (`botv3/usos.py`) no lanza nunca: si no puede escribir, el bot contesta igual y queda una sola
    advertencia en el log.
- **Un solo punto de registro: `handle_update()`**, que ahora es `with contando_uso(update):`.
  - **Comandos y botones:** el canal y la función salen de la actualización (alias de comandos y prefijos de
    `callback_data`).
  - **Frases y voz:** la función la pone el primer manejador que la toma. Es la tabla `MARCAS`, aplicada por
    nombre al final del bloque, **sin tocar ninguna rama del despachador**.
  - **Errores:** una excepción, un `audit(status="error")` o un texto que parte con «❌»/«No pude».
  - Un mensaje no autorizado no se cuenta.
  - Hoy no dejan evento y ahora sí se cuentan: `/menu`, `/gastos` manual, `/ayuda`, `/acciones`, `/olvidar`
    y el resto de los comandos.
- **Resumen: `/usos`**, un comando y no un botón de `/menu`. Es de mantenimiento y se usa poco, y `/menu` y la
  lista corta de comandos son para lo de todos los días (decisión del 19-10).
  - Muestra los últimos 7 días por bot y función, con texto/voz/botón y los errores, y lo que **nunca** se usó
    en 180 días de entre lo que ese bot tiene (`catalogo.json`, que cada bot deja al arrancar).
  - **Pilar** ve sólo lo suyo; ignora `BOTV3_USOS_OTROS`.
  - **Jaime** ve los dos si tiene montada la carpeta de Pilar (`BOTV3_USOS_OTROS="pilar=/run/usos-pilar"`). Si
    no, dice «Pilar: sin dato».
- **Para Cockpit:** `bots-info` agrega `usos_bots`, el mismo `usos.resumen`, con el `usos.py` desplegado y la
  carpeta `usos/` de cada perfil. La página no se hizo.
- **Retención: 180 días**, para ver estacionalidad con un costo de ~90 B por línea.
  - Rotación sin perder líneas: cada línea va al archivo de su mes y nunca se renombra ni se reescribe nada.
  - Sólo se borra un archivo cuyo mes terminó hace más de 180 días. Se revisa una vez por mes, al escribir.

## Archivos tocados

- `botv3/botv3.py` (+172 −6):
  - los imports `contextlib` y `functools`;
  - el `elif command == "/usos"` en el despachador;
  - `handle_update` dentro de `contando_uso`;
  - el bloque nuevo del contador después de `handle_update`;
  - `publicar_catalogo` en `main()`.

  No se cambió ningún manejador. `comando_uso`, que toca el 90, queda igual.
- `pi/bots-info.py` (+24): `_cargar_usos`, `usos_bots` y la clave `usos_bots` en `reunir()`.
- Nuevos:
  - `botv3/usos.py` y `botv3/test_contador.py`;
  - `encargos-nube/92-propuesta-jaime-usos-pilar.conf`: drop-in **sin instalar** con un `BindReadOnlyPaths` sólo
    de `botv3-pilar/usos`;
  - `encargos-nube/92-fallas-antes-despues.txt`.

## Pruebas

Desde la raíz, `NODO_PRUEBAS=1 python3 -B -m unittest -v botv3/test_contador.py`. Salida real, sin las líneas de
log del bot:

```
test_cada_boton_del_menu_y_los_prefijos ... ok
test_cada_comando ... ok
test_frases_marcadas_por_su_manejador ... ok
test_los_comandos_publicados_estan_cubiertos ... ok
test_no_autorizado_no_se_cuenta ... ok
test_voz_que_no_se_entiende ... ok
test_voz_y_texto ... ok
test_carpeta_que_no_se_puede_escribir ... ok
test_error_contestado_cuenta_como_error ... ok
test_error_del_manejador_se_anota_y_se_relanza ... ok
test_bots_info_expone_el_mismo_resumen ... ok
test_cuenta_por_funcion_canal_y_errores_y_lo_nunca_usado ... ok
test_pilar_ve_solo_lo_suyo_y_jaime_los_dos ... ok
test_rotar_ignora_lo_que_no_es_suyo ... ok
test_rotar_no_pierde_lineas_y_borra_solo_lo_vencido ... ok
test_el_texto_del_mensaje_no_queda ... ok
test_una_funcion_fuera_de_la_lista_queda_desconocida ... ok
Ran 17 tests in 2.105s
OK
```

Suites que no podían quedar con fallas nuevas:

```
botv3/test_botv3   Ran 490 tests · FAILED (failures=49, errors=156, skipped=113)   — mismas fallas que antes
pi/test_cuentas_uso Ran 74 tests · FAILED (failures=1, errors=9, skipped=4)        — mismas fallas que antes
```

- **Desde la raíz** no se importan `usos.py`, `compras.py`, `temporizadores.py` y otros, porque `botv3/` no está
  en `sys.path`. Por eso hay tantas fallas previas, y por eso ahí el contador queda apagado.
- **Corrida desde `botv3/`** (`cd botv3 && python3 -B -m unittest test_botv3`), con `usos.py` cargado y el
  contador activo: `FAILED (failures=7, errors=34)` antes y después, con las mismas fallas.
- Las listas exactas están en `encargos-nube/92-fallas-antes-despues.txt`.

## Decisiones

- El canal de un adjunto (foto o PDF) es `texto`: el encargo fija `texto|voz|boton`.
- Una consulta que va a un motor se cuenta como `ok` al **enviarla**: el resultado llega después, en otro hilo.
  Si se quiere el resultado real de la consulta, hay que anotarlo en el trabajador. Eso queda para después.
- Una frase la marca el primer manejador que la toma. `atender_hora_o_clima` no se marca; se marcan los tres
  de adentro (`atender_hora`, `atender_comuna`, `atender_clima`), así «qué hora es» cuenta como `hora`.

## Riesgos abiertos

- **Despliegue:**
  - `usos.py` va junto a `botv3.py` en `/opt/botv3`;
  - `bots-info` nuevo;
  - para que Jaime vea a Pilar, revisar e instalar el drop-in propuesto. Falta verificar en la Pi que un bind de
    sólo lectura de una subcarpeta de una ruta en `InaccessiblePaths` quede visible.
- Los archivos son 0644 en una carpeta 0755 dentro del estado de cada bot. No traen texto, pero sí cuándo y qué
  se usó. Si eso se considera sensible, bajar a 0640 con un grupo compartido.
- Los envoltorios de `MARCAS` y de `audit`/`send_text` se aplican por nombre al final del bloque. Si alguien
  renombra un manejador de la tabla, el bot falla al importarse (`KeyError` en `globals()`), así que no queda
  en silencio: lo pilla cualquier prueba. Un manejador nuevo que no esté en la tabla cuenta sus frases como
  `desconocido` (o `consulta:auto`) hasta que se agregue.

## Qué cambiar en la guía (doc 35, lo hace el 93)

- Agregar `/usos`: «📊 cuánto se usó cada función en los últimos 7 días y qué no se usó nunca». En Pilar sólo lo
  suyo; en Jaime, los dos bots.
- Decir que el bot anota qué función se usó, por dónde (texto, voz o botón) y si salió bien, **nunca** lo que se
  escribió o se dijo, y que se guarda 180 días.

## Arreglos vuelta 1 (92b, 25-10-2026)

Rama `claude/encargo-92b-arreglos`, creada desde `base-92b`. Cierra las dos medias de la revisión de Codex
(`9092nr-RESULTADO.md`). Archivos tocados: `botv3/test_contador.py` y el bloque de `catalogo_usos()` en
`botv3/botv3.py` (+5 líneas, nada más).

### 1. [Media] `test_contador.py` salía a la red → cerrado

- **Guarda que hace fallar la suite.** Al importar, la suite reemplaza `socket.socket.connect` (solo para
  AF_INET/AF_INET6: los sockets Unix del temporal siguen funcionando), `socket.create_connection`,
  `socket.getaddrinfo` y `urllib.request.urlopen`. Cada intento se anota, y todas las clases heredan de
  `SinRed`, que en su `addCleanup` **falla** la prueba si quedó algún intento, aunque el bot haya atrapado el
  error y seguido.
- **En el `setUp`** se reemplazan `datos_clima` (con la respuesta real guardada de open-meteo, con las fechas
  corridas a hoy), `send_voice`, `sintetizar` (sin Piper esta copia nunca llegaba a la voz; en la Pi sí),
  `buscar_searxng`, `send_photo` y `send_document`. Además, `SES_TELEGRAM`, `SES_GROQ`, `SES_SEARXNG`,
  `SES_CLIMA` y `SES_PROVEEDOR` pasan a ser sesiones que fallan y anotan el intento.
- **Se afirman las llamadas simuladas**: el botón `menu:clima` pide el clima una vez y manda la foto, el caso de
  voz contesta con una nota de voz simulada (`voces == [7]`) y `/buscar` usa el buscador simulado una vez.
- **Reproducción antes del arreglo** (solo con la guarda puesta, salida real):

  ```
  FAIL: test_cada_boton_del_menu_y_los_prefijos  → socket.getaddrinfo ('127.0.0.1', 39965)  [proxy]
        traza: callback_menu → comando_clima → enviar_clima → datos_clima → _consultar_open_meteo
  FAIL: test_el_texto_del_mensaje_no_queda       → socket.getaddrinfo ('127.0.0.1', 8888)
        traza: handle_message → comando_buscar → buscar_searxng
  Ran 17 tests — FAILED (failures=2)
  ```

  Con `datos_clima` simulado apareció **una tercera fuga que la revisión no nombraba**: la imagen del clima sale
  por `send_photo` → `SES_TELEGRAM.post(.../sendPhoto)`, no por `telegram()`. La guarda la cazó y también quedó
  simulada.

### 2. [Media] `/usos` dejaba fuera `spotify` y `boleta` → cerrado

`catalogo_usos()` suma `boleta` cuando la ruta `boleta` está en las rutas del perfil (`ALLOWED_AUTO_ROUTES`), y
`spotify` cuando `spotify.py` está desplegado y el perfil tiene `spotify` configurado. Es la misma condición
con la que `comando_spotify` deja de contestar «Spotify no está configurado». Pruebas nuevas
(`CatalogoSinUsar`): con y sin la ruta `boleta`; sin `spotify`, con `spotify` y con `spotify` configurado pero
sin el módulo; y una de punta a punta por `/usos`, donde los dos aparecen en «Sin usar nunca» y dejan de
aparecer en cuanto se usan.

### Pruebas (salida real, como la cola, desde la raíz)

```
$ python3 botv3/test_contador.py
Ran 20 tests in 0.628s
OK

$ python3 botv3/test_botv3.py
antes:   Ran 490 tests — FAILED (failures=9, errors=36)
después: Ran 490 tests — FAILED (failures=9, errors=36)
diff de la lista de fallas antes/después: vacío (las mismas 45, del entorno de esta copia)

$ python3 botv3/test_spotify.py
python3: can't open file '/home/user/claude/botv3/test_spotify.py': [Errno 2] No such file or directory
```

**`test_spotify.py` no existe en esta copia** (tampoco `botv3/spotify.py`: la 88b no trajo esos dos archivos a
`base-92b`). No se pudo correr. Hay que correrlo en la Pi antes de desplegar. Por lo mismo, la prueba «con
spotify» reemplaza `spotify_mod` por un objeto vacío: `catalogo_usos()` solo mira que exista.

### Riesgos abiertos

- La guarda de red reemplaza funciones de `socket` y `urllib` para todo el proceso de la suite. Si un día se
  corre `test_contador.py` junto con otras suites en el mismo proceso (`-m unittest discover`), esas suites
  también quedan sin red. Es lo deseable, pero podría sorprender.
- `boleta` entra al catálogo por la ruta, aunque `boleta.py` falte. En ese caso `correccion_boleta` no toma nada
  y la función figuraría «sin usar» sin poder usarse. Hoy `boleta.py` está desplegado.
