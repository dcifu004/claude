# Revisión 88dnr: los arreglos 88d (Spotify en el bot) hechos en la nube (Claude (Cami), 25-10-2026)

Revisión sin cambios de código. Es la primera del 88dn y no hay `88dnr*-RESULTADO.md` anteriores. Leí
`88dn-revision.md`, `88r-RESULTADO.md`, `88d-PLAN.md`, `88d-RESULTADO.md`, la propuesta
`88d-spotify@.service.propuesta`, `88dn-diff-nube.txt` y el código vigente de `botv3/spotify.py`,
`botv3/botv3.py` (`atender_spotify` y el router) y `botv3/test_spotify.py`.

No hay `88dn-RESULTADO.md`: este encargo es la revisión del 88d y su informe es `88d-RESULTADO.md`. Tampoco existen
`88dn-decisiones.md`, `88dn-busquedas.jsonl` ni `encargos/manual-busquedas.jsonl`, así que no hay búsquedas que
revisar.

**El diff de la cola no existe** (`cola88dn-88dn-diff.txt`: «el historial git falló … no hay fotos completas de
fases propias»), y la línea base quedó vacía (`cola88dn-base.json` = `[]`, «Línea base no persistida»). Por eso
armé las dos cosas a mano:

- **Diff:** `diff -u` de los tres `*.antes-88dn` contra los vigentes. Las 124 líneas `+`/`-` son **idénticas**, en
  el mismo orden, a las de `88dn-diff-nube.txt`. En `botv3.py` el único hunk es `@@ -6774,18 +6774,27 @@`, dentro
  de `atender_spotify`. Un `ast` de los dos `botv3.py` da 316 definiciones de nivel superior, ninguna duplicada, y
  los conteos de `contador` (6) y de `def` (313) son iguales antes y después. La mezcla en 3 vías no perdió ni
  duplicó nada fuera de esa función.
- **Línea base:** una copia del árbol con los tres `antes-88dn` en su lugar, corrida igual que la vigente.

Los hashes de `botv3.py`, `spotify.py`, `test_spotify.py`, `test_botv3.py` y `test_plantillas.py` son los mismos
al empezar y al terminar (`sha256sum -c`), aunque la cola 87bn corría al lado en el mismo árbol.

## Pruebas (salida real)

Desde la raíz del proyecto, con `NODO_PRUEBAS=1` y `BOTV3_STATE_DIR`, `BOTV3_USO_CUENTAS` y `BOTV3_USO_RUTAS` en un
`mktemp -d`:

```text
árbol vigente (después)                         copia con los *.antes-88dn (antes)
$ python3 -B botv3/test_spotify.py              $ python3 -B botv3/test_spotify.py
Ran 13 tests in 1.119s                          Ran 8 tests in 1.449s
OK                                              OK
$ python3 -B botv3/test_botv3.py                $ python3 -B botv3/test_botv3.py
Ran 490 tests in 28.245s                        Ran 490 tests in 46.020s
OK                                              OK
$ python3 -B pi/spotify/test_plantillas.py      $ python3 -B pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s                           Ran 3 tests in 0.001s
OK                                              OK
```

En la Pi `rapidfuzz` está (`python3 -c "import rapidfuzz"` da 3.12.2), así que `test_spotify.py` corre sin
`PYTHONPATH`. Eso cierra la comprobación pendiente del hallazgo 6 de la 88r. No hay fallas antes ni después.

**Las pruebas nuevas contra el código anterior** (el `test_spotify.py` nuevo con `botv3.py` y `spotify.py` de
`antes-88dn`): `Ran 13 tests … FAILED (failures=21)`. Fallan las 18 comprobaciones de frases, la marca de «sigue» a
secas, «el otro caído» y «sigue sin pausa». Es lo mismo que dice `88d-RESULTADO.md`, y muestra que las pruebas
muerden de verdad.

## Hallazgos, de más grave a menos grave

### 1. [Media] La unidad propuesta deja a go-librespot sin audio: `ProtectHome=tmpfs` vacía `/run/user`

`encargos/88d-spotify@.service.propuesta:21-22`. El comentario dice que el socket de PipeWire vive en
`$XDG_RUNTIME_DIR` (`/run/user/<uid>`), «que no se tapa». Es falso: `ProtectHome=` cubre `/home`, `/root` **y
`/run/user`**. La 88r cometió el mismo error en su arreglo propuesto, y el 88d lo copió. C5 pide que la propuesta
cierre el hallazgo 1 «sin romper el audio (PulseAudio del usuario)», y no lo cumple. Las plantillas usan
`audio_backend: pulseaudio` (`pi/spotify/config-jaime.yml:4`, `config-pilar.yml:4`).

**Reproducción** en la Pi, como `dcifu004` y sin root (systemd 257, `pipewire-pulse` activo):

```text
$ systemd-run --user --wait --collect --pipe -p PrivateUsers=yes -p ProtectHome=tmpfs /bin/sh -c 'ls -la /run/user/; ls -la $XDG_RUNTIME_DIR/pulse/native'
drwxr-xr-x  2 dcifu004 dcifu004   40 Oct 25 23:02 .          ← /run/user vacío
ls: cannot access '/run/user/1000/pulse/native': No such file or directory

$ systemd-run … -p PrivateUsers=yes -p ProtectSystem=strict -p NoNewPrivileges=yes \
    -p "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" -p SystemCallFilter=@system-service -p ProtectHome=tmpfs \
    /usr/bin/python3 -I -c '…socket.connect($XDG_RUNTIME_DIR+"/pulse/native")…'
FileNotFoundError: [Errno 2] No such file or directory

  mismo comando + -p BindReadOnlyPaths=/run/user/1000/pulse
conecta a PulseAudio
```

`ProtectHome=yes` da `Permission denied` sobre `/run/user/1000`. `read-only` deja ver todo `/run/user/1000`: `bus`,
`gnupg`, `openssh_agent`, `credentials`. Lo correcto es `tmpfs` más la carpeta de pulse expuesta sola.

**Lo que sí funciona de la propuesta** (probado con un árbol de sonda en `/dev/shm`, no con las carpetas reales de
Spotify):

- `TemporaryFileSystem` + `BindPaths` funcionan en una unidad de usuario: la instancia sólo ve su carpeta y escribe
  en ella, y la carpeta del otro da «No such file».
- Cruzar por `/proc/<pid del otro>/root/…` da `Permission denied`, tanto hacia la otra instancia como hacia un
  proceso del anfitrión (el shell). `PrivateUsers=yes` lo impide.
- `/etc/resolv.conf` se lee y `apresolve.spotify.com` resuelve con `RestrictAddressFamilies`.

**Arreglo:** cambiar el comentario y agregar `BindReadOnlyPaths=%t/pulse` (o `%t/pulse/native`). Conectar a un
socket Unix sobre un montaje de sólo lectura funciona, como se ve arriba. El paso de prueba de
`88d-RESULTADO.md:54-58` lo habría detectado (espera «`pulse/native` está»), pero sólo si se corre antes de dar el
alta. Con el `BindReadOnlyPaths` sumado, falta lo que la propuesta ya pide: arrancar el go-librespot real con esa
línea, oírlo sonar y ver que `state.json` y el lockfile se escriban.

### 2. [Media] «sigue», «continúa» o «reanuda» a secas, con el receptor propio caído, siguen contestando «No pude usar Spotify ahora.»

`botv3/botv3.py:6778-6786` y `:6796`. `interpretar(limpio, sonando=False)` devuelve `{"accion": "sigue", "sola":
True}` para «sigue» a secas, así que `inicial` es verdadero. Si el `/status` propio falla, la función responde
«No pude usar Spotify ahora.» y devuelve `True` **antes** de llegar a la comprobación nueva de `paused` (`:6796`).
La frase no sigue su camino. C3 pide que «sigue» a secas se tome sólo si el receptor propio está en pausa y que, si
no, siga como conversación. Un receptor que no contesta no está en pausa. En cambio «pausa» a secas, el otro caso
ambiguo, sí devuelve `False` con el receptor propio caído, porque su `inicial` es `None`.

Este caso se da en la práctica. Hoy `spotify@jaime` y `spotify@pilar` están instalados pero `inactive (dead)` (el de
Jaime desde las 21:43), los dos perfiles ya traen el bloque `spotify` y el LEEME pide arrancar las unidades a mano
tras abrir LUKS. Con el 88b + 88d desplegados así, cada «sigue» dictado para que el bot continúe recibe un error de
Spotify. El bot desplegado hoy (`/opt/botv3/botv3.py`, sin `atender_spotify`) lo manda a la conversación. No lo
empeora el 88d (antes pasaba igual), pero el arreglo del hallazgo 5 queda incompleto.

**Reproducción** con receptores HTTP reales en loopback (no mocks de `estado`). El propio es un puerto cerrado y el
otro responde `status_detenido`:

```text
propio caído, 'sigue' a secas       -> True ['No pude usar Spotify ahora.']
propio caído, 'Jaime, continúa'     -> True ['No pude usar Spotify ahora.']
propio caído, 'pausa' sola          -> False []
propio sonando, 'sigue'             -> False []        (bien: antes reanudaba)
propio sin vincular (204), 'sigue'  -> False []        (bien: antes decía «Falta vincular»)
```

`test_hallazgo_5_sigue_a_secas_solo_en_pausa` (`botv3/test_spotify.py:250`) cubre «detenido», «sin vincular» y «en
pausa», pero no el receptor propio caído.

**Arreglo:** en la rama de error del receptor propio, `if inicial and not inicial.get("sola")`. Así «sigue» a secas
devuelve `False` igual que «pausa» a secas. Hay que sumar el caso a la prueba.

### 3. [Media] El filtro de posesivos mira sólo lo que sigue al **primer** «de»: «reproduce la nota de voz de mi mamá» todavía pone música

`botv3/spotify.py:81-84`. `re.fullmatch(rf"{verbo}\s+(.+?)\s+de\s+(.+?)", frase)` corta con el primer grupo
perezoso, así que `group(2)` empieza después del primer « de ». El filtro nuevo sólo mira el comienzo de
`group(2)`, y un posesivo que viene después de un segundo «de» pasa. C1 pide que «… de mi …» ya no ponga música.
Antes y después del 88d (`interpretar(…, False)`):

```text
'reproduce la nota de voz de mi mamá'        -> cancion titulo='la nota'    artista='voz de mi mama'   (igual que antes)
'reproduce la canción de cuna de mi hija'    -> cancion titulo='la cancion' artista='cuna de mi hija'  (igual que antes)
'reproducir la clase de hoy de mi hijo'      -> None    (cerrado, porque «hoy» quedó primero)
```

La lista de palabras tampoco trae «anoche» ni «recién»: `'reproduce la grabación de anoche'` da `cancion`
`artista='anoche'`. Como `atender_spotify` corre antes que hora y clima, gastos, agenda, nodo y compras, estas
frases buscan en Spotify y reproducen lo que encuentren en la cuenta de la persona.

**Arreglo:** buscar el posesivo en cualquier « de <posesivo> » de la frase (por ejemplo
`re.search(r"\bde\s+(?:mis?|tus?|…|anoche)\b", frase)`), no sólo al comienzo de `group(2)`. Hay que sumar las dos
frases de arriba a `NO_88D`.

### 4. [Baja] Los artículos quedaron fuera del filtro, contra el plan: «reproduce el audio de la reunión» sigue poniendo música

`88d-PLAN.md`, punto 1, lista «posesivo o artículo de cosa (`mi`, `mis`, `tu`, `nuestro`, `la`, `el`…)». El código
(`spotify.py:84`) deja los artículos fuera a propósito, y `88d-RESULTADO.md` lo justifica con «Tren al sur de Los
Prisioneros» y «Mentira de La Ley». La razón es buena: muchos artistas en español empiezan con artículo. Pero el
plan aprobado decía otra cosa, y quedan abiertas frases del mismo tipo que el hallazgo 3 de la 88r:

```text
'reproduce el audio de la reunión'           -> cancion artista='la reunion'
'reproduce la última nota de la reunión'     -> cancion artista='la reunion'
'reproduce el resumen de la semana'          -> cancion artista='la semana'
'reproduce el video de los niños'            -> cancion artista='los ninos'
'reproduce el podcast de economía'           -> cancion artista='economia'
```

El usuario debería decidir si acepta este costo, o si un título que empieza con artículo de cosa (`el audio`,
`la nota`, `el video`, `la grabación`, `el resumen`) también exige «en Spotify». Esa variante no choca con «Tren al
sur» ni con «Mentira». No lo marco Media porque el 88d lo dejó escrito como riesgo y no es nuevo.

### 5. [Baja] «sigue» reanuda el propio sin pausar el otro, y los dos suenan por el mismo PulseAudio (viene del 88b)

`botv3/botv3.py:6808-6811`. La rama `sigue` llama a `reanudar(cfg["api"])` sin pausar los receptores de `otros`
que suenan. La rama de reproducir sí lo hace (`:6818-6821`, «siempre en ese orden»). Con los dos receptores sobre el
mismo `pulseaudio` del usuario, quedan dos músicas a la vez. Reproducido con receptores reales en loopback: el
propio en pausa y el otro con `status_sonando`, «sigue» da `propio=[GET /status, POST /player/resume]` y
`otro=[GET /status]`, sin pausa. No lo introduce el 88d: con los `antes-88dn` pasa igual. Lo anoto porque el 88d
tocó esta rama y ni la 88r ni sus pruebas lo vieron. Arreglo: el mismo bucle de pausa del otro antes del
`reanudar`.

## Lo que revisé y está bien

- **C1, sin choques nuevos:**
  - Pasé por `interpretar` (antes y después, con `sonando` en `False` y `True`) las 2.208 cadenas literales de las
    suites de `botv3/`: temporizadores, compras, clima, voz, gastos, etc. Resultado: **0 capturas nuevas** y 20
    frases que dejan de capturarse, todas del tipo «toca …» o «… de mi/esta/ayer …». Por construcción no puede haber
    capturas nuevas: el diff sólo suma `return None` y la clave `sola`.
  - Fuera de `test_spotify.py`, lo único que Spotify todavía toma de esas suites es «pausa» y «reanuda» a secas, y
    esos llegan antes a temporizadores en el router (`botv3.py:8189`, `:8267`).
  - «tócame …» sigue siendo música (`\b` no corta `tocame`).
  - «toca Bad Guy en Spotify», «Tren al sur de Los Prisioneros», «Mi Gente de J Balvin» y «Hoy de Gloria Trevi»
    siguen siendo canciones.
- **C2 (hallazgo 4):**
  - Con receptores reales en loopback, propio sano y otro en un puerto cerrado: «reproduce Oxytocin de Billie
    Eilish» da `GET /status` + `POST /player/play` en el propio y el aviso con la canción, y «pausa» a secas con el
    propio sonando lo pausa. Con los `antes-88dn`, las dos frases daban «No pude usar Spotify ahora.».
  - El `LOG.warning` no lleva URL ni puerto. Busqué `127.0.0.1` en las líneas WARNING con un handler raíz en DEBUG
    y no aparece. No hay `exc_info`, así que tampoco sale la excepción encadenada de `requests`.
  - El receptor propio caído sigue respondiendo «No pude usar Spotify ahora.» para las frases de música.
- **C3, salvo el hallazgo 2:** «sigue», «Sigue.», «Jaime, sigue», «continúa» y «reanuda» quedan marcados `sola`.
  «sigue con la música» no cambia. «sigue así» y «sigue con eso» siguen sin ser música. Por voz (`en_voz=True`), el
  `False` deja pasar la frase a hora y clima y a lo que viene después, igual que por texto.
- **C4:** las pruebas nuevas simulan `estado`, `reproducir`, `reanudar`, `pausar`, `buscar` y `send_text`. Con
  `strace -f -e connect,openat,mkdir,rename,unlink` sobre `FrasesTests` y `OtroReceptorYSigue88dTests` no hay
  ningún `connect()`. Sólo se crean y borran temporales de `/tmp` (`TemporaryDirectory`), y no se abre nada de
  secretos ni de los vaults. Usan la forma real: `status_detenido` del fixture del `api-spec` v0.10.5, `None` para
  el `204` sin vincular y `paused: true` para la pausa.
- **Seguridad del cambio:** no hay callbacks nuevos ni archivos nuevos, y no se imprime ningún token. La búsqueda
  sigue por `params=`.
- **Regresiones:** las respuestas largas, las fuentes, las rutas y la voz no se tocan; el diff está sólo en
  `atender_spotify` e `interpretar`. `test_botv3.py` da 490 OK antes y después.

## Qué falta para desplegar el 88b + 88d

1. Hallazgos 2 y 3: dos cambios chicos en `botv3.py:6782-6786` y `spotify.py:84`, con sus casos de prueba.
2. Hallazgo 1: sumar `BindReadOnlyPaths=%t/pulse` a la propuesta, corregir su comentario y probarla en la Pi con el
   go-librespot real (que suene y escriba `state.json`). Recién entonces se reemplaza `pi/spotify/spotify@.service`,
   se recalcula su hash en el LEEME y se pide el alta. La sonda de arriba muestra que el resto del aislamiento
   funciona en una unidad de usuario.
3. La decisión del usuario sobre el hallazgo 2 de la 88r (`POST /token`). No se reabre acá, pero sigue pendiente
   para desplegar.
4. Las bajas 4 y 5: decidir los artículos y pausar el otro en «sigue». Ninguna de las dos bloquea por sí sola.

## Veredicto

El 88d cierra bien el hallazgo 4 de la 88r, el «toca» y la forma simple de «… de mi …». No rompe nada fuera de
`atender_spotify` e `interpretar`, y las suites quedan en verde. Pero dos de los cinco criterios de este encargo no
se cumplen. C5: la unidad propuesta dejaría a los receptores sin audio. C3: con el receptor propio caído, que es como
están hoy las dos unidades, «sigue» a secas todavía se lo queda Spotify con un error en vez de seguir como
conversación. Así desplegado, eso cambiaría algo que el bot de hoy hace bien. A eso se suma que el filtro de
posesivos se salta con un segundo «de». Los tres arreglos son chicos.

VEREDICTO: NO DESPLEGABLE
