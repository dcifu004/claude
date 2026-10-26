# Encargo 100: PLAN del controlador `spotify-web@`

Rama `claude/encargo-100-spotify-web`, creada desde `base-100`. Todo lo nuevo va en `pi/spotify-web/`.
`botv3/botv3.py` y `botv3/spotify.py` son de sólo lectura en este encargo.

## Archivos

- `spotify-web.py`, sólo con la biblioteca estándar.
  - `Controlador`: la caché de `/status`, los hilos, Chromium y la CDM. Todo lo de afuera se le inyecta:
    - la carpeta de datos;
    - el origen de la CDM;
    - el argv de Chromium (el real o el falso);
    - el reloj;
    - los plazos.
  - `Servidor HTTP` (`ThreadingHTTPServer` en 127.0.0.1). Sólo lee la caché y lanza hilos, así que siempre contesta en
    menos de 500 ms.
  - `Cdp`: el protocolo de DevTools por pipe.
    - Chromium recibe los fds 3 y 4 con `pass_fds`. En el hijo se acomodan con `F_DUPFD` (≥ 10) y después `dup2`.
    - Los mensajes van separados por `\0`.
    - Un hilo lector reparte las respuestas por `id`.
  - El JavaScript es fijo: lee el DOM (`leer`, `botones`) y aprieta por índice entero. La URI nunca entra en el JS: se
    navega con `Page.navigate` a `https://open.spotify.com/{track|artist}/<id validado>`.
  - La elección del botón y la lectura de la barra (`Now playing: X by Y`, `Playing on …`) se hacen en Python, con
    funciones puras que se prueban con el fixture DOM real.
  - **CDM:** compara el SHA-256 del `.so` y del `manifest.json` antes de copiar. Escribe de forma atómica (`.tmp` +
    `os.replace`), con carpetas 0700 y archivos 0600, y el archivo de pista sólo si cambia.
  - **`estado.json`:** guarda la sesión y el último tema, escrito de forma atómica y con modo 0600.
  - **`--vincular`:** se niega si el puerto del perfil está ocupado. Levanta Chromium con `--remote-debugging-port=9222`
    en 127.0.0.1, imprime la línea del túnel y espera la sesión, como máximo 10 min, mirando la URL de la página en
    `/json`. Sale 0 o 1.
- `spotify-web@.service`: la unidad de usuario que pide el encargo.
- `chromium_falso.py`: el Chromium falso de las pruebas. Habla CDP por los fds 3 y 4 y contesta con datos sacados de
  `fixtures/dom-tema-2026-10-25.json`, según un escenario JSON: la demora de arranque, la sesión, los botones, otro
  dispositivo y un registro de lo recibido.
- `test_spotify_web.py`: cubre C1 a C8. C1 importa el `_spotify_suena` real de `botv3.py`.
- `LEEME.md`: las altas, el cambio de receptor, la vuelta atrás, `--vincular` y la migración de la sesión de la
  Prueba 0.

## Decisiones previstas

- Sesión desconocida (el servicio recién arrancado, antes de abrir Chromium): si `estado.json` no la dice, se toma como
  iniciada cuando existe la carpeta `chromium/Default` del perfil. Si no, `/status` da 204. Así, después de migrar la
  sesión de la Prueba 0, el bot no dice «falta vincular» antes del primer play.
- `spotify:artist:<id>` también se acepta, porque la 88b manda la URI del artista cuando busca un artista. Se navega a
  `/artist/<id>` y se usa el mismo selector: `aria-label="Play"` en el `action-bar` o en el `entity-header`. No hay
  fixture de la página de artista, así que eso queda anotado como riesgo.

## Línea base

- `pi/test_nodo_desplegar.py`: `Ran 93 tests … FAILED (failures=2, errors=2)`, del entorno. La lista está en
  `100-nodo-desplegar-fallas-antes.txt`.
- `botv3/test_spotify.py`: aquí no se importa sin `rapidfuzz`. Con la copia del scratchpad (`PYTHONPATH`) da
  `Ran 8 tests … OK`.
