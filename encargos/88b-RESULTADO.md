---
tipo: resultado
encargo: 88b
fecha: 2026-10-25
estado: LISTO PARA REVISIÓN Y DESPLIEGUE (sin Spotify ni Telegram reales)
---

# 88b — Spotify por perfil en Jaime y Pilar

## Cambios

| Archivo | Cambio |
|---|---|
| `botv3/spotify.py` | Nuevo módulo puro: frases ancladas, búsqueda Web API con Client Credentials en memoria, elección con `rapidfuzz` y cliente loopback de go-librespot (`/status`, `/auth/code`, play, pause, resume y volumen reservado). |
| `botv3/botv3.py` | Valida `spotify` en el perfil; atiende música después de temporizadores y antes de hora/clima, tanto escrita como dictada; agrega `/spotify`. No verbaliza órdenes multimedia. |
| `botv3/perfiles/{jaime,pilar}.toml` | Receptores simétricos: Jaime `127.0.0.1:3678`, Pilar `127.0.0.1:3679`. |
| `botv3/update_telegram_commands.py` | Registra `/spotify` sólo para perfiles que declaran receptor. |
| `botv3/fixtures/spotify-search-oxytocin.json`, `botv3/test_spotify.py` | Fixture y pruebas de frases, fuzzy matching, receptor falso, perfil, errores y secreto. |
| `pi/cargar-clave.py` | Acepta `SPOTIFY_CLIENT_ID` y `SPOTIFY_CLIENT_SECRET`, sin prefijo exigido. |
| `35 - Guía de uso de Jaime y Pilar.{md,html}` | Sección Música (Spotify), frases, `/spotify` y vinculación. |

El cliente usa la especificación oficial de go-librespot v0.10.5: `/status` entrega `stopped`,
`paused` y `track`; sin sesión devuelve 204. `/auth/code` devuelve `url`, `code` y `expires_at`,
o 204 si no hay una autorización pendiente. La 88a no pudo observar estas respuestas en una
instancia real porque no instaló los receptores; se confirmó contra el OpenAPI del mismo release.

## C1 y C2

| Frase | Resultado |
|---|---|
| Hola Jaime. Reproducir oxitocina de Billie Eilish en Spotify. | `cancion` |
| reproduce Oxytocin de Billie Eilish | `cancion` |
| Pon Oxytocin en Spotify | `cancion` |
| tócame Bad Guy de Billie Eilish en spotify | `cancion` |
| Reproduce música de Billie Eilish. | `artista` |
| reproduce a Billie Eilish en Spotify | `artista` |
| Pausa la música. / pausa Spotify / pausa con música sonando | `pausa` |
| sigue con la música | `sigue` |
| pon una alarma a las 7; pon un temporizador de 5 minutos; pausa sin música; pon pausa; agrega leche a la lista; ¿quién canta Oxytocin?; reproducir la última nota; compré pan | `None` |

Al reproducir desde Pilar, la prueba local comprueba que el `POST /player/pause` de Jaime ocurre
antes del `POST /player/play` de Pilar. Este sandbox no permite abrir puertos loopback, por lo
que esa única prueba queda marcada `skipped=1` aquí; en la Pi usa un puerto efímero y se ejecuta.

## Fixture

No había `SPOTIFY_CLIENT_ID` ni `SPOTIFY_CLIENT_SECRET` en este entorno, así que no se llamó a
Spotify ni se guardó una respuesta real. El fixture es una respuesta recortada con los campos de
`/search` documentados por Spotify y el URI público de *Oxytocin*. La prueba confirma que
«oxitocina» + «billi eilish» elige *Oxytocin — Billie Eilish*.

## Claves y despliegue

Pedir por separado, para no escribir valores sensibles en el historial:

```text
nodo-desplegar sugerir --motivo "88b: cargar Client ID de Spotify en ambos perfiles" -- sudo cargar-clave SPOTIFY_CLIENT_ID jaime pilar
nodo-desplegar sugerir --motivo "88b: cargar Client Secret de Spotify en ambos perfiles" -- sudo cargar-clave SPOTIFY_CLIENT_SECRET jaime pilar
```

También faltan las altas de `spotify.py`, su fixture y `cargar-clave.py` modificado, además de
las versiones actualizadas de `botv3.py`, perfiles y menú. Hashes relevantes: `spotify.py`
`bfdae1a6ce28`, fixture `479d740d0c38`, `cargar-clave.py` `eaf59c8e57f5` y `botv3.py`
`09e8db58ff61`. Deben desplegarse juntos y reiniciar `botv3@jaime.service` y
`botv3@pilar.service` sólo después de que 88a esté instalada.

Se revisó la unidad plantilla: permite `AF_INET` y el drop-in de Pilar no declara
`IPAddressDeny`, por lo que no bloquea `127.0.0.1`.

## Verificación

```text
python3 -m py_compile botv3/spotify.py botv3/botv3.py botv3/test_spotify.py pi/cargar-clave.py  → 0
python3 pi/spotify/test_plantillas.py → Ran 3 tests, OK
python3 pi/test_nodo_desplegar.py    → Ran 93 tests, OK
python3 botv3/test_botv3.py          → Ran 490 tests, OK (skipped=4)
python3 botv3/test_temporizadores.py → ✅ todo en verde
python3 botv3/test_compras.py        → ✅ todo en verde
python3 botv3/test_spotify.py        → Ran 6 tests, OK (skipped=1: bind loopback del sandbox)
```

## Pendientes

1. Desplegar 88a y sus receptores, luego las altas 88b y las dos claves.
2. Ejecutar `botv3/test_spotify.py` en la Pi para que C4 abra su servidor loopback sin el salto
   del sandbox.
3. Vincular cada cuenta desde `/spotify`; recién ahí probar reproducción real y confirmar que
   el audio llega al G2000.

## Arreglos vuelta 1

Se eligió el criterio conservador cuando había ambigüedad: una frase dirigida explícitamente al
otro asistente no se interpreta como música en el perfil que la recibió. El fixture del receptor
no se presenta como captura: 88a no instaló los receptores, por lo que su origen es el contrato
OpenAPI oficial v0.10.5. Contiene literalmente todos los campos obligatorios que ese receptor
emitirá; queda pendiente sustituirlo por una captura una vez desplegada 88a.

| Hallazgo | Cambio puntual | Prueba sobre la forma usada realmente |
|---|---|---|
| Grave: frases ajenas hacían `GET /status` antes de decidir | `atender_spotify` interpreta primero y retorna sin construir bases ni consultar un receptor para C2. Sólo `pausa` sola conserva la consulta, porque necesita conocer si algo suena. | `test_c2_no_consulta_receptor_y_vocativo_ajeno_no_activa`: sobre las frases C2 no ambiguas cuenta **0** llamadas a `estado()` y `buscar()`; para `pausa` con los dos `status_detenido` del fixture cuenta exactamente **2** y retorna `False`. |
| Media: el vocativo del otro perfil podía activar el receptor propio | `spotify.vocativo_ajeno(texto, NOMBRE)` rechaza antes de `sin_vocativo()` e `interpretar()`. El parser sigue aceptando «Hola Jaime…» de Whisper, pero la atención del perfil Jaime deja pasar «Hola Pilar…». | La misma prueba usa la transcripción realista «Hola Pilar. reproduce Oxytocin de Billie Eilish»: retorna `False`, y mantiene los contadores de `estado()` y `buscar()` en **0**. C1 sigue probado directamente con «Hola Jaime. Reproducir oxitocina de Billie Eilish en Spotify.». |
| Media: C4/C7 usaban objetos reducidos, no el contrato del receptor | Se agregó `botv3/fixtures/spotify-receptor-v0.10.5.json` y el servidor HTTP falso lo entrega para `/status`; C7 usa su `auth_code`. Incluye los 17 campos obligatorios de `status`, los 17 de `track` si existe, y `url`, `code`, `expires_at` para `/auth/code`. | `test_fixture_receptor_respeta_forma_openapi_v0105` exige esos conjuntos exactos de claves y C4/C7 consumen esas estructuras. Origen: [OpenAPI oficial go-librespot v0.10.5](https://raw.githubusercontent.com/devgianlu/go-librespot/v0.10.5/api-spec.yml), no una respuesta inventada ni una captura inexistente. El bind loopback de C4 sigue saltado en este sandbox; la prueba queda preparada para ejecutarse sin salto en la Pi. |

Salida real de las suites después de los cambios:

```text
$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK

$ python3 pi/test_nodo_desplegar.py
Ran 93 tests in 4.903s
OK

$ python3 botv3/test_botv3.py
Ran 490 tests in 16.577s
OK (skipped=4)

$ python3 botv3/test_temporizadores.py
✅ todo en verde

$ python3 botv3/test_compras.py
✅ todo en verde

$ python3 botv3/test_spotify.py
Ran 8 tests in 0.092s
OK (skipped=1)
```

El único salto de Spotify es el servidor HTTP loopback efímero de C4: este sandbox no permite
`bind(127.0.0.1)`. No se reemplazó por una falsa prueba de red; las comprobaciones de forma del
fixture, de frases y de cero llamadas sí corrieron aquí. No se usó Spotify, Telegram, n8n, perfiles
desplegados ni `sudo`.
