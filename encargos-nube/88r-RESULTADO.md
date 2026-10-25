# Revisión 88r: Spotify por perfil (88a + 88b + 88c), revisión cruzada de Claude (Diego), 25-10-2026

Revisión sin cambios de código. La 88 la escribió Codex en la Pi; la 88b y la 88c se las revisó él mismo. Leí el
encargo de cada etapa, sus resultados, las revisiones `88ar1–3`, `88br`, `88br1` y `88cr`, los tres diffs reales
de `encargos-nube/88r-diffs/` y el código vigente de `base-88r`: `pi/spotify/`, `pi/nodo-desplegar.py`,
`pi/desplegar-escucha.service`, `pi/cargar-clave.py`, `botv3/spotify.py`, la parte de Spotify de `botv3/botv3.py`,
`botv3/update_telegram_commands.py` y el bloque `spotify` de los dos perfiles.

**Contra lo publicado** (la red de esta sesión dejó bajar la release, el esquema y archivos sueltos del tag,
no el tar del código fuente):

- `go-librespot_linux_arm64.tar.gz` de la release v0.10.5: sha256
  `35274c1d3576090096d3459ecf76ee9c025258d19dc76f0bf724f95c525467e1` (6.137.723 B). El ejecutable extraído
  da `9130ee00613abeb9620cc06fe9bc7080eba73618d547b0c71ec991f3504dc5ff`. **Los dos coinciden** con lo anotado
  en `88a-RESULTADO.md`/`88c-RESULTADO.md` y con el hash de la alta en `pi/spotify/LEEME.md`.
- `config_schema.json` del tag v0.10.5: sha256 `e6a3cf03…50cc`, **idéntico** a
  `pi/spotify/fixtures/config_schema.v0.10.5.json`. Las claves de las plantillas existen. `zeroconf_enabled`,
  `mpris_enabled` y `cache.enabled` valen `false` por defecto.
- `daemon/api_server.go`, `daemon/player.go` y `api-spec.yml` del tag v0.10.5, para ver qué expone la API local
  (hallazgo 2) y qué devuelve `/status` sin sesión (`204`, `ErrNoSession`).

## Pruebas (salida real, como la cola, desde la raíz, con `NODO_PRUEBAS=1` y estado en `mktemp`)

```text
$ python3 -B botv3/test_spotify.py
ModuleNotFoundError: No module named 'rapidfuzz'                ← entorno: esta copia no lo trae

$ PYTHONPATH=<scratchpad>/py python3 -B botv3/test_spotify.py    (rapidfuzz instalado sólo en el scratchpad)
Ran 8 tests in 1.289s
OK

$ python3 -B botv3/test_botv3.py
Ran 490 tests in 44.377s
FAILED (failures=7, errors=34)

$ python3 -B pi/test_nodo_desplegar.py                           (sin usuario dcifu004)
Ran 93 tests in 14.393s
FAILED (failures=2, errors=1)

$ python3 -B pi/test_nodo_desplegar.py                           (con dcifu004 creado en el contenedor)
Ran 93 tests in 16.718s
FAILED (errors=1)

$ python3 -B pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK
```

**Todas las fallas son del entorno, ninguna es de Spotify:**

- `test_botv3.py`: la lista es la misma con o sin `rapidfuzz`. Faltan `/opt/botv3/proposal.schema.json`
  (24), `pi/google_puente.py` (9) y `pi/remoto.py` (1). Dos pruebas se niegan a correr como root («modo 000»).
  Cinco de clima/para-pilar fallan porque el contenedor está en UTC (`10:30` en vez de `07:30`). Ninguna prueba
  de Spotify falla.
- `test_nodo_desplegar.py`: las dos fallas de `DuenosSpotifyTests` son `getpwnam(): name not found: 'dcifu004'`
  y desaparecen al crear el usuario. El error que queda (`test_la_documentacion_del_nodo_describe_enviar`) es un
  archivo de documentación de la Pi que no está en esta copia.

## Hallazgos, de más grave a menos grave

### 1. [Media] `spotify@.service` no aísla nada: cada receptor ve la credencial del otro y todo lo de `dcifu004`

`pi/spotify/spotify@.service:13-17` sólo trae `ExecStart`, `Restart` y `RestartSec`. Las dos instancias corren
como `dcifu004`, sin `PrivateUsers`, `ProtectSystem`, `ProtectHome`, `ReadWritePaths` ni filtro de familias o
syscalls. Las dos carpetas de perfil son `dcifu004:dcifu004 0700` y su `state.json` (la credencial de Spotify)
`0600` del mismo usuario. Por eso el proceso de Jaime puede leer la credencial de Camila
(`/opt/nodo/datos/spotify/pilar/state.json`), y al revés. Además alcanza todo lo que alcanza `dcifu004`: los
vaults, `~/.ssh`, el árbol de las colas. Es un binario de terceros que habla con los servidores de Spotify y
decodifica audio remoto. El encargo pide revisar que «cada instancia sólo vea lo de su perfil», y hoy no se
cumple. La 88a no lo exigía y ninguna de las tres revisiones lo miró.

**Cómo verlo (después del despliegue):**
`systemctl --user show spotify@jaime -p PrivateUsers -p ProtectSystem -p ProtectHome -p ReadWritePaths` da
los valores por defecto (`no`, `no`, `no`, vacío). Como `dcifu004`,
`cat /opt/nodo/datos/spotify/pilar/state.json` funciona: es el mismo usuario que corre `spotify@jaime`.

**Arreglo propuesto:** endurecer la unidad de usuario y verificarla en la Pi con `systemd-run --user`, como hizo
la 88ar1 (allí `PrivateUsers=yes` + `ProtectSystem=strict` arrancó). Algo como:

```ini
PrivateUsers=yes
ProtectSystem=strict
ProtectHome=tmpfs
TemporaryFileSystem=/opt/nodo/datos
BindPaths=/opt/nodo/datos/spotify/%i
PrivateTmp=yes
NoNewPrivileges=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
LockPersonality=yes
SystemCallFilter=@system-service
```

El socket de PipeWire vive en `$XDG_RUNTIME_DIR` (`/run/user/<uid>`), que `ProtectHome` no tapa. Comprobar en la
Pi que suene y que `state.json` y el lockfile se escriban. Si `TemporaryFileSystem`/`BindPaths` no funcionan en
la unidad de usuario, la alternativa es un usuario de sistema por perfil (unidad de sistema con `User=`), a
costa de reubicar el socket de PipeWire.

### 2. [Media] La API local sin autenticación entrega el token de Spotify y escribe la biblioteca a cualquier usuario de la Pi, también a `botpilar`

El diseño 36 §5 aceptó una API sin autenticación «siempre que escuche sólo en loopback» (C3). Pero en v0.10.5 esa
API hace más que reproducir y pausar. `api-spec.yml:626` define `POST /token`, «Returns a Spotify access token
for the active session», que `daemon/player.go:862-873` responde con `GetAccessToken`. Hay además
`/library/playlists/add_tracks` y `remove_track` (`:810`, `:839`), `/library/liked`, `/events`, entre otros.
Loopback no separa usuarios Unix. El bot de Pilar corre como `botpilar`, un usuario aparte justamente porque está
expuesto a internet y ejecuta agentes; aun así puede pedir `POST 127.0.0.1:3678/token` y obtener un token de la
cuenta de Diego, o tocar su biblioteca. Al revés, Jaime obtiene el de Camila. El código del bot respeta «sólo
pausar el otro», pero el sistema no lo hace cumplir. `botv3@.service:62` permite `AF_INET`, y debe permitirlo
para que Pilar llegue a su propio receptor.

**Cómo verlo (después del despliegue, con Jaime vinculado):**
`sudo -u botpilar curl -s -X POST 127.0.0.1:3678/token` devuelve `{"token":"…"}`.

**Arreglo propuesto (lo decide Diego, porque reabre el §5 del diseño):** un proxy local mínimo por perfil
delante de go-librespot, con lista cerrada de rutas (`GET /status`, `GET /auth/code`, `POST /player/play`,
`/pause`, `/resume`) y sin `/token` ni `/library`. Que escuche en un socket Unix con permisos de grupo, o en
loopback con nftables por `meta skuid` (Pilar sólo a su puerto y al `/player/pause` del otro vía el proxy).
Como mínimo, documentarlo en el diseño y en el LEEME como riesgo aceptado, con `/token` nombrado.

### 3. [Media] «toca … de …» y «reproduce … de mi …» se los queda Spotify y suena música

`botv3/spotify.py:66` incluye `toca` entre los verbos, y la rama `:77` (`{verbo} X de Y`) no exige decir
«Spotify». En Chile «toca …» también significa «es hora de …». Como `atender_spotify` corre antes que hora y
clima, gastos, agenda, nodo y compras (`botv3.py:8182`, `:8260`), estas frases ya no llegan al router: el bot
busca en Spotify y **reproduce lo que encuentre** en la cuenta de la persona. Reproducido con
`spotify.interpretar` (las mismas salidas con `sonando=False` y `True`):

```text
'toca sacar la basura de la cocina'           -> cancion  titulo='sacar la basura'   artista='la cocina'
'toca pagar la cuenta de la luz'              -> cancion  titulo='pagar la cuenta'   artista='la luz'
'Jaime, toca pagar el arriendo de noviembre'  -> cancion  titulo='pagar el arriendo' artista='noviembre'
'toca comprar leche de almendras'             -> cancion  (intencion_compras da None: iba al router)
'reproduce la última nota de mi proyecto'     -> cancion  titulo='la ultima nota'    artista='mi proyecto'
'toca a la puerta'                            -> artista  'la puerta'
```

El C1 de la 88b sólo pide «tócame … en spotify» (con la palabra Spotify) y «reproduce Oxytocin de Billie
Eilish». El C2 cubre «reproducir la última nota», pero no la forma con «de». La 88br1 revisó el costo de
consultar los receptores, no estas colisiones.

**Arreglo propuesto:** tratar `toca` como ya se trata `pon` (`:69`): sin «en Spotify» no es música
(`tócame`/`tócate` pueden quedar). Rechazar un «artista» que empiece con posesivo o artículo de cosa
(`mi`, `mis`, `tu`, `nuestro`, `la`, `el`) cuando no se dijo Spotify. Sumar al C2 las frases de arriba.

### 4. [Media] Si el receptor del otro perfil está caído, el propio deja de funcionar

`botv3.py:6777-6784` consulta `/status` de **todos** los receptores (el propio y `otros`) antes de actuar. Si
cualquiera no contesta, responde «No pude usar Spotify ahora.» y no reproduce en el propio, aunque esté sano. Lo
reproduje con un receptor falso en loopback como propio y un puerto cerrado como «otro»:

```text
'sigue con la música'                  -> True ['No pude usar Spotify ahora.'] [('GET', '/status')]
'reproduce Oxytocin de Billie Eilish'  -> True ['No pude usar Spotify ahora.'] [('GET', '/status')]
```

Pasa, por ejemplo, si `spotify@pilar` no arrancó tras abrir LUKS (el LEEME pide arrancarlo a mano), si su
`config.yml` falta (`ConditionPathExists`) o si Camila nunca lo instaló: Jaime se queda sin Spotify. Contradice
el «uno por perfil» del diseño.

**Arreglo propuesto:** el `/status` del otro sólo sirve para decidir si hay que pausarlo. Que su falla se trate
como «no suena» (y quede en el log, sin URL), y que sólo la falla del receptor propio responda «No pude usar
Spotify ahora.». Agregar una prueba con el otro puerto cerrado.

### 5. [Menor] «sigue» a secas reanuda Spotify aunque no haya nada en pausa

`botv3/spotify.py:63` acepta `sigue`, `continua` y `reanuda` solos, y devuelve `{"accion": "sigue"}` sin mirar
`sonando`. Un «sigue» de conversación (dictado para que el bot continúe) termina en «▶️ Spotify de … sigue.» o en
«Falta vincular tu Spotify: /spotify». El C1 sólo pedía «sigue con la música».

**Arreglo propuesto:** como con «pausa» sola, aceptar el verbo solo únicamente si el receptor propio está en
pausa (`paused: true` en `/status`). Si no, que la frase siga su camino.

### 6. [Menor] Sin `rapidfuzz`, Spotify se apaga en silencio

`botv3/spotify.py:16` importa `rapidfuzz` en el nivel superior, y `botv3.py:102-105` traga el `ImportError` y deja
`spotify_mod = None`. En una Pi sin el paquete, `/spotify` y las frases contestan «Spotify no está configurado
para Jaime», que es falso, y nada queda en el log. Esta copia no lo trae (por eso falló `test_spotify.py` sin el
`PYTHONPATH`).

**Arreglo propuesto:** comprobar `python3 -c "import rapidfuzz"` en la Pi antes de desplegar (paquete Debian
`python3-rapidfuzz`, sin `pip`, por PEP 668). Dejar un `LOG.warning` cuando el import falla con el perfil
configurado, y que el mensaje diga «falta el módulo» en vez de «no está configurado».

### 7. [Menor] Sigue abierto: `leer_fuente` abre la fuente del vault sin `O_NONBLOCK`

`pi/nodo-desplegar.py:628` sigue igual que en la nota de contexto de la 88ar3 (hallazgo 8): un FIFO puesto como
fuente de una alta cuelga al escucha. No es de la 88 y la 88c no lo tenía que arreglar; lo anoto porque la 88cr
dice «los ocho hallazgos quedaron cerrados» y esa nota no se cerró. El mismo patrón de `leer_destino` (`lstat` →
`O_NONBLOCK` → `fstat` del mismo inodo) sirve aquí.

## Lo que revisé y está bien

- **Binario y esquema:** los hashes y el esquema coinciden con la release y el tag oficiales (arriba). El flag
  `--config_dir` lo acepta el paquete `flag` de Go con un guion o con dos.
- **`nodo-desplegar`:**
  - `RE_FUENTE` sólo sumó `@`, y siguen rechazados la fuente absoluta, `..` y lo que, resuelto por
    `/proc/self/fd`, quede fuera del vault o en `secretos`.
  - `alta-enlace` sólo acepta el par fijo de `ENLACES_PERMITIDOS`, y el hash que se aprueba es el del objetivo
    literal. Un enlace igual queda «sin cambios» y uno a otro objetivo se rechaza (`:957-981`). `crear_enlace`
    exige que el binario exista y que `/usr/local/bin` sea de root y no escribible, y publica por temporal más
    `os.replace` con `dir_fd`.
  - El tope de 24 MiB sólo agranda la lectura en memoria. Un binario no se muestra como diff: sale con tamaño y
    sha256.
  - Lo que se aprueba queda ligado a lo que se instala: el staging se escribe al preparar y `aplicar` vuelve a
    comprobar su sha256 (`:1325-1327`).
  - El dueño `dcifu004` sólo se acepta para las dos configs (`RUTAS_DUEÑO_USUARIO`), y su escritura se hace con
    `seteuid` del usuario dentro de una carpeta anclada por descriptor. Un cambio de nombre o un enlace no deja
    un escritor root fuera de lugar.
  - `limpiar_temporales` sólo borra regulares de un nombre con el patrón exacto, en carpetas derivadas del
    catálogo. Un tramo enlace da `NotADirectoryError` y se salta (lo comprobé).
  - El escucha sólo suma `-/usr/local/lib/go-librespot` y `/etc/systemd/user` a `ReadWritePaths`, y deja
    `ProtectHome=yes`.
- **Bootstrap del LEEME:** es una sola línea para `sugerir`, con los cinco pasos en orden (crear la carpeta,
  instalar `nodo-desplegar`, instalar la unidad del escucha, `daemon-reload`, `restart`). Después vienen las
  altas en orden (binario, enlace, unidad, configs) y el arranque de usuario. Está completo.
- **Plantillas:** sólo `127.0.0.1:3678/3679`, `zeroconf_enabled: false`, `device_auth`, `pulseaudio`, 40 % y
  160. `ConditionPathExists` evita el bucle con LUKS cerrado.
- **Perfil:** `cargar_perfil` sólo acepta `http://127.0.0.1:<1-65535>` en `api` y `otros`. Lo que no sea eso
  tumba el arranque.
- **Bot:**
  - `atender_spotify` sólo consulta receptores si la frase es de música o es «pausa» sola (cierra 88br1 #1).
  - Un vocativo al otro asistente no activa Spotify (cierra 88br1 #2).
  - Al reproducir, pausa primero el otro receptor y después hace el play propio.
  - El `/spotify` de cada perfil sólo mira su propio receptor.
  - `SpotifyError` tiene textos fijos, sin URL ni token. La búsqueda va por `params=` y cortada a 120
    caracteres, y el token Client Credentials vive sólo en memoria.
  - Los campos que usa el bot (`stopped`, `paused`, `track.name`, `track.artist_names`; y `url`, `code`,
    `expires_at` de `/auth/code`) existen en el `api-spec.yml` de v0.10.5, y `/status` sin sesión responde
    `204`, que el bot trata como «falta vincular».
- **`/spotify` en el menú:** sólo aparece en los perfiles con `spotify` (`update_telegram_commands.py` y la
  sincronización de `botv3.py:8651`, que es la misma lista).
- **`cargar-clave`:** sólo suma las dos variables a la lista cerrada; la forma y la escritura no cambian.

## Veredicto

Las dos medias de seguridad (1 y 2) no son vulnerabilidades explotables desde afuera. Rompen, eso sí, el
aislamiento que el resto del nodo se esfuerza en mantener: usuario propio para Pilar e `InaccessiblePaths`. La 2
además reabre una decisión de diseño con un dato que no estaba (`/token`). La 3 y la 4 se van a notar en el uso
diario: suena música cuando se dicta una tarea, y Spotify de un perfil se cae por el otro. Los arreglos de 3, 4 y
5 son chicos y en `spotify.py`/`botv3.py`. El 1 es endurecer la unidad y probarla en la Pi. El 2 lo decide Diego.

VEREDICTO: NO DESPLEGABLE
