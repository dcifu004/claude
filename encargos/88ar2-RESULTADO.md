# Encargo 88ar — Revisión 2 del 88a (Claude (Diego), 25-10-2026)

Sólo revisión: no se tocó código. Revisé el diff propio completo (`cola88-88a-diff.txt`: autor
`14c5cef..5c2ae49` y fix1 `8b09dc6..8bd0f5f`); lo de «Cambios ajenos» no se juzga. No hay
`88a-PLAN.md`, `88a-decisiones.md` ni `88a-busquedas.jsonl`. `encargos/manual-busquedas.jsonl` no
existe (sólo `manual-busquedas-prueba-encargo32.jsonl`, de otro encargo): no hay líneas dentro de
las ventanas de autor (25-10 11:10–11:21 y 11:27–11:42).

Las reproducciones corrieron en `mktemp -d` (`/tmp/tmp.whJpDV4IRn`) con `BOTV3_USO_CUENTAS`,
`BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` apuntando ahí. Para el camino root usé `unshare -r` (el uid
propio se ve como 0 dentro de un espacio de usuarios) y para el aislamiento del escucha,
`systemd-run --user` con las mismas opciones de la unidad. Bajé v0.10.2 y v0.10.5 arm64 y sus
`config_schema.json` a un temporal; corrí el binario sólo con `--help` y un `HOME` temporal, sin
pedir códigos a Spotify ni vincular nada.

## Pruebas (salida real)

```text
$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK
$ python3 pi/test_nodo_desplegar.py
Ran 84 tests in 4.383s
OK
$ python3 botv3/test_botv3.py
Ran 490 tests in 26.708s
OK
$ python3 botv3/test_temporizadores.py
  ok  0660 tras deshacer
  ok  0660 tras marcar avisadas
✅ todo en verde
$ python3 botv3/test_compras.py
  ok  deja pasar «lava el carro»
  ok  deja pasar «saca el auto del carro»
✅ todo en verde
$ python3 botv3/test_spotify.py
python3: can't open file '.../botv3/test_spotify.py': [Errno 2] No such file or directory   (rc 2)
```

`botv3/test_spotify.py` es de la 88b y figura en la línea base (`cola88-base.json`: «no corrió
(rc 2)»): no es falla de esta etapa. `test_plantillas.py` también estaba en la base como «no
corrió»; ahora corre en verde.

## Hallazgos de la revisión 1: cómo quedaron

| # rev1 | Estado | Cómo lo comprobé |
|---|---|---|
| 1 [Grave] `ReadWritePaths` inexistente → 226 | **Cerrado el 226**; queda abierto lo que la rev1 pedía decidir (ver hallazgo 2 abajo) | `systemd-run --user` con las opciones nuevas arranca; `mkdir /usr/local/lib/go-librespot` da `Read-only file system` |
| 2 [Grave] `-config_dir` | Cerrado | v0.10.5 `--help` muestra `--config_dir`; `-config_dir` sigue dando `onfig_dir (expected field=value)` |
| 3 [Grave] `chown` por ruta sigue enlaces | Cerrado | Perfil cambiado por enlace antes de abrir → `NotADirectoryError`, víctima vacía y `0755`; la prueba nueva cubre el cambio después del `fchown`. No hay `threading` en el script, así que el `seteuid` temporal no alcanza a otro hilo |
| 4 [Media] `MAX_FUENTE` | Cerrado | 24 MiB > 17 491 240 B (v0.10.5 extraído) |
| 5 [Media] última estable | A medias | El código apunta a v0.10.5; el resultado, el fixture y las plantillas siguen en v0.10.2 (hallazgo 4) |
| 6 [Media] forma real | Abierto | Hallazgo 5 |
| 7 [Media] binario, altas, enlace | Abierto | Hallazgo 4 |
| 8 [Media] `ProtectHome=read-only` | Cerrado | En el espacio de nombres sólo se ve `~/.config/systemd`; `~/.ssh` no existe |
| 9 [Baja] prefijo `spotify@.service` | Cerrado | `PERMITIDOS_EXACTOS`; `-/opt/nodo/datos/spotify` salió de `ReadWritePaths` |
| 10 [Baja] LUKS cerrado al arrancar | Cerrado (documentado en `LEEME.md`) | — |
| 11 [Baja] `rm` sin `-f` | Cerrado | — |

Regresiones: ninguna en lo que ya se despliega. Las 92 entradas del catálogo tienen la carpeta de
destino en `root 0755` y el destino es un archivo regular con un solo enlace, así que pasan los
chequeos nuevos de `escribir_destino` y `leer_destino`. Bajo `unshare -r` un despliegue `root:root`
aplica (contenido y modo `0755` correctos, sin temporales sobrantes), un `restart:` fallido revierte
al contenido anterior, y una carpeta nueva bajo un permitido queda en `0755`. `cola-run.py` filtra
el catálogo con `v.get("fuente", "")`, así que una entrada de enlace sin `fuente` no lo rompe. No
se tocaron `botv3`, rutas, voz, fuentes ni respuestas largas. No se imprimen tokens.

## Hallazgos nuevos, de más grave a menos grave

### 1. [Media] `spotify@.service` no se puede instalar por el catálogo con ningún dueño

`pi/nodo-desplegar.py:550-553` (`escribir_destino`, camino no privado) exige que la carpeta de
destino sea de root y no escribible por grupo u otros. El destino de la unidad,
`~/.config/systemd/user`, es `dcifu004:dcifu004 755` en la Pi. Y `validar_dueno`
(`:450-455`) sólo deja `dcifu004:dcifu004` para las dos `config.yml`. O sea: con `root:root`
el escritor la rechaza, y con `dcifu004` la rechaza el validador. El chequeo de root es correcto
(es lo que cierra el hallazgo 3 de la rev1), pero deja la unidad sin camino. C2 no se puede
cumplir.

```text
carpeta prueba uid/modo: 1000 0o755 | real: 1000
1) escribir_destino root:root en carpeta de dcifu004 -> ValueError directorio root no seguro: ...~/.config/systemd/user
1b) validar_dueno acepta root:root para la unidad: True
```

Peor: en `aplicar` (`:1239-1240`) el alta se agrega al catálogo **antes** de escribir y no se
deshace si falla la escritura (ese orden ya venía de antes). El primer `alta spotify-unidad`
dejaría la entrada en el catálogo para siempre (`'…' ya existe en el catálogo` al reintentar), y
corregirla exigiría editar `/etc/nodo/desplegar/catalogo.toml` con `sudo`.

Arreglo sugerido: instalar la unidad en `/etc/systemd/user/spotify@.service` (`root:root 755`
en la Pi, la leen todos los gestores de usuario). Así no hace falta tocar `/home` y se pueden
volver a dejar `ProtectHome=yes` y sacar `BindPaths`/`ReadWritePaths` de `~/.config/systemd/user`.

### 2. [Media] El binario tampoco se puede instalar: `/usr/local/lib/go-librespot` queda de sólo lectura

`pi/desplegar-escucha.service:28` usa `-/usr/local/lib/go-librespot`. Con el guión, la unidad ya
no muere con 226. Pero como la carpeta no existe, systemd no la monta escribible, y
`abrir_directorio(..., crear=True)` (`pi/nodo-desplegar.py:471-497`) no puede crearla bajo
`ProtectSystem=strict`. Era la decisión que la rev1 dejó planteada («la primera instalación del
binario necesita que la carpeta exista antes de arrancar el escucha… hay que decidir cuál»). Quedó
sin tomar.

```text
$ systemd-run --user --wait --collect -q --pipe -p PrivateUsers=yes -p ProtectSystem=strict \
    -p ReadWritePaths=/usr/local/bin -p ReadWritePaths=-/usr/local/lib/go-librespot ... /usr/bin/mkdir /usr/local/lib/go-librespot
mkdir: cannot create directory '/usr/local/lib/go-librespot': Read-only file system
(control sin ProtectSystem: Permission denied — o sea, el EROFS lo pone el espacio de nombres)
```

La prueba `test_escucha_tolera_ruta_de_binario_aun_no_creada_y_no_lee_home`
(`pi/test_nodo_desplegar.py:435-440`) sólo busca textos en la unidad y no detecta esto. Arreglo
sugerido: sumar `sudo install -d -m 0755 -o root -g root /usr/local/lib/go-librespot` a la misma
línea de bootstrap (por `nodo-desplegar sugerir`), antes de reiniciar el escucha, y dejarlo
escrito en el resultado.

### 3. [Media] Un FIFO en la carpeta del perfil cuelga al escucha entero

Esta etapa crea la primera carpeta de destino que controla `dcifu004` (el perfil, `0700`).
`leer_destino` (`pi/nodo-desplegar.py:500-520`) abre el destino con `O_RDONLY | O_NOFOLLOW`
**antes** del `fstat`. Si en vez de `config.yml` hay un FIFO, `open` se bloquea hasta que aparezca
un escritor. El escucha es un solo proceso sin hilos, así que se detiene todo el canal de
despliegue. `Restart=always` no lo salva porque el proceso no muere. Lo puede provocar cualquier
proceso de `dcifu004`, por ejemplo un agente de la cola: basta un `mkfifo` y luego un
`pedir spotify-jaime` (o el propio despliegue siguiente). No da privilegios, pero sí deja sin
servicio lo que hoy funciona.

```text
F) leer_destino sobre un FIFO: colgado hasta la alarma de 5 s (rc 142)
```

Arreglo: abrir con `O_NONBLOCK` (y quitarlo después, o leer con el `fstat` ya hecho), o hacer el
`fstat` con `os.stat(name, dir_fd=…, follow_symlinks=False)` y rechazar lo que no sea regular antes
de abrir. Falta una prueba con `os.mkfifo`.

### 4. [Media] La etapa sigue incompleta y con dos versiones a la vez

- No hay binario en el vault, ni SHA-256 del ejecutable, ni ninguna alta (configs, unidad,
  binario, enlace). C1–C6 no se pueden correr.
- `ENLACES_PERMITIDOS` (`pi/nodo-desplegar.py:163-165`) y `LEEME.md` dicen **v0.10.5**. Pero la
  sección «Release fijado» de `88a-RESULTADO.md:17-25` (URL, hash del `.tar.gz` y comando de C1),
  el fixture `config_schema.v0.10.2.json` y el comentario de las dos plantillas siguen en
  **v0.10.2**. La 88b hereda esto.
- Datos para la corrección, calculados en esta revisión (son míos, no los firma el autor):
  v0.10.5 `go-librespot_linux_arm64.tar.gz` = `35274c1d3576090096d3459ecf76ee9c025258d19dc76f0bf724f95c525467e1`
  (coincide con el digest que publica GitHub), 6 137 723 B. El ejecutable extraído pesa
  17 491 240 B, con sha256 `9130ee00613abeb9620cc06fe9bc7080eba73618d547b0c71ec991f3504dc5ff`.
  `releases/latest` sigue siendo v0.10.5 (16-10, no preliminar).
- El esquema de v0.10.5 sólo difiere del de v0.10.2 en una `description` (MPRIS). Las dos
  plantillas validan con `jsonschema` contra el esquema **real** de ambas versiones.

### 5. [Media] Las pruebas y los comandos de verificación todavía no usan la forma real

- `pi/spotify/fixtures/config_schema.v0.10.2.json` sigue siendo el extracto escrito sin red (hallazgo 6 de
  la rev1). `test_plantillas.py:66` valida `"minimum"`, que el esquema real no tiene (usa
  `"min"`, que JSON Schema ignora). Con `initial_volume: 400` pasan tanto el extracto como el
  esquema real. La restricción que la prueba dice comprobar no existe en la fuente. Basta guardar
  el `config_schema.json` real de v0.10.5 y validar contra él.
- C1 (`88a-RESULTADO.md:93`) sigue usando `go-librespot --version`, y en v0.10.5 también da
  `level=fatal … error="unknown flag: --version"`. La versión se lee del journal
  (`running go-librespot …`). Ninguna prueba ejecuta el binario fijado (`--help` con
  `--config_dir` sería lo mínimo).
- C6 (`88a-RESULTADO.md:141-142`) espera `Result=condition-failed`. Con una unidad real de usuario
  y la misma condición, systemd devuelve otra cosa, así que el comando daría un falso rojo:

  ```text
  $ systemd-run --user --unit=r88ar2-c6 -p ConditionPathExists=/no/existe/config.yml -p Restart=on-failure -p RestartSec=10 /bin/true
  rc start=0
  Result=success   NRestarts=0   ActiveState=inactive   ConditionResult=no
  ```

  Lo que hay que mirar es `ConditionResult=no` + `NRestarts=0`. El `|| test $? -eq 1` sobra:
  `start` devuelve 0.

### 6. [Media] La tarjeta de aprobación de un binario no muestra nada verificable

Con `MAX_FUENTE` de 24 MiB, un alta del binario arma su diff con `difflib` sobre el ELF
decodificado (`pi/nodo-desplegar.py:935-938`). Con el binario real v0.10.5, `texto()` tarda 3,1 s
y lo que llega a la tarjeta es `@@ -0,0 +1,465421 @@\n+\x7fELF\x02\x01…`: bytes nulos y basura,
sin tamaño ni sha256. Así, el ✅ que instala un ejecutable como root se da a ciegas. No verifiqué si
Telegram acepta el texto con NUL. Si lo rechaza, `preparar` falla y el binario ni siquiera llega a
la tarjeta. Arreglo: si la fuente trae `\0`, que el diff sea `binario: N bytes, sha256 …` (contra
el anotado en el resultado).

### 7. [Media] El camino `root:root` reescrito no tiene ninguna prueba

`aplicar` y `revertir` pasaron de `copy2`/`os.replace` por ruta a `escribir_destino` por
descriptores. Ése es el camino de las 92 entradas que hoy se despliegan. Las dos únicas pruebas que
llaman a `aplicar` (`pi/test_nodo_desplegar.py:366` y `:409`) usan `dcifu004:dcifu004`. Tampoco hay
prueba de `revertir` con archivo previo ni del rechazo «directorio root no seguro». Mi
reproducción bajo `unshare -r` (más arriba) muestra que funciona, pero la suite no lo protege.
Falta una prueba bajo `unshare -r`, o con `os.fstat` simulado, que cubra aplicar, revertir y la
carpeta nueva.

### 8. [Baja] El enlace no se puede volver a pedir una vez instalado, y su revertir borra sin respaldo

- `preparar` y `aplicar` llaman a `validar_destino` (`:899`, `:1245`) antes de mirar `tipo ==
  "enlace"`. Si `/usr/local/bin/go-librespot` ya es un enlace, se rechaza con `destino con enlace
  simbolico` (reproducido). Cualquier pedido posterior que incluya esa entrada falla, aunque
  `leer_enlace` diga que está igual.
- Para los enlaces se ignora el `=<sha256>` del pedido (`:900-913`).
- `revertir` (`:1349-1360`) borra el enlace sin mirar si antes había un archivo en ese nombre, y
  `crear_enlace` lo pisa con `os.replace` sin respaldo.

### 9. [Baja] Cada cambio de versión exige reinstalar `nodo-desplegar` a mano

`ENLACES_PERMITIDOS` fija `v0.10.5` en el código de root, y `/usr/local/bin/nodo-desplegar` está en
`PROHIBIDOS`. Subir de versión pide editar el script y hacer un bootstrap con `sudo`. Conviene
anotarlo en `LEEME.md`. Además, si alguien redespliega otro binario sobre el **mismo** destino, el
`difflib` entre dos ELF tarda **95 s** (medido con v0.10.2 → v0.10.5), y en ese tiempo el escucha
no atiende a nadie. Con destino por versión no debería pasar, pero nada lo impide.

### 10. [Baja] Detalles de forma

- `test_fuente_del_tamano_real_del_binario_arm64_pasa_el_tope` usa el tamaño de v0.10.2
  (17 380 232) con un nombre de archivo de v0.10.5 (17 491 240). Las dos cifras pasan.
- Los temporales de `escribir_destino` y `crear_enlace` ahora llevan nombre al azar. Si el escucha
  muere entre crearlos y el `os.replace`, quedan `.config.yml.nodo-desplegar-<hex>` sueltos, y
  nadie los limpia.
- `"/opt/nodo/datos/spotify/"` en `PERMITIDOS` sobra (ya lo cubre `/opt/nodo/`).

## Veredicto

No hay regresiones en lo que ya funciona: el camino `root:root` de las 92 entradas aplica y
revierte bien, y los hallazgos graves de la rev1 están cerrados. Aun así, la etapa no entrega lo
que promete. La unidad no tiene ningún dueño posible en el catálogo (1) y la carpeta del binario
es de sólo lectura para el escucha (2), así que ni C1 ni C2 se pueden alcanzar por el camino
diseñado. Falta además el binario con su hash y sus altas, y las versiones están mezcladas (4). Por
otro lado, la primera carpeta escribible por `dcifu004` abre un cuelgue del escucha (3). No son
mejoras pendientes: son las piezas que hacen funcionar la etapa. Para la corrección: 1 (mover la
unidad a `/etc/systemd/user`), 2 (crear la carpeta en el bootstrap), 3 (`O_NONBLOCK` + prueba con
FIFO), 4 y 5 (binario v0.10.5 con su hash, esquema real, C1 por el journal y C6 con
`ConditionResult`), 6 (tarjeta con sha256 para binarios) y 7 (prueba del camino root). Lo de 8 a
10 puede ir en el mismo arreglo.

VEREDICTO: NO DESPLEGABLE
