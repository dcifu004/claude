# Encargo 88ar — Revisión 3 del 88a (Claude (Diego), 25-10-2026)

Sólo revisión: no se tocó código ni se agregó el binario al vault. Leí primero el diff propio
completo (`cola88-88a-diff.txt`: autor `14c5cef..5c2ae49`, fix1 `8b09dc6..8bd0f5f` y fix2
`8040e00..03425d4`); lo de «Cambios ajenos» no se juzga. No hay `88a-PLAN.md` ni
`88a-busquedas.jsonl`. `encargos/manual-busquedas.jsonl` no existe (sólo
`manual-busquedas-prueba-encargo32.jsonl`, de otro encargo), así que no hay líneas dentro de las
ventanas de autor (25-10 11:10–11:21, 11:27–11:42 y 11:58–12:08). `88a-decisiones.md` sólo
registra «que lo arregle» tras la rev2; no decide nada que aquí se vuelva a marcar.

Antes de juzgar regresiones comprobé que `/usr/local/bin/nodo-desplegar` (lo desplegado) es
**byte a byte** el `pi/nodo-desplegar.py` de la base: revertí los tres parches de la etapa sobre
el archivo actual y `cmp` da igual. Toda diferencia del script es de esta etapa.

Las reproducciones corrieron en `mktemp -d` (`/tmp/tmp.GuyhcCn56z`, `/tmp/tmp.RsLgD79RqJ`), con
`BOTV3_USO_CUENTAS`, `BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` apuntando ahí. El camino root se
reprodujo bajo `unshare -r`; el aislamiento del escucha, con `systemd-run --user`. Bajé el asset
v0.10.5 arm64 y su `config_schema.json`. El binario se ejecutó sólo dentro de `unshare -rn`
(sin red), así que no pidió ningún código a Spotify ni vinculó nada.

## Pruebas (salida real)

```text
$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK
$ python3 pi/test_nodo_desplegar.py
Ran 87 tests in 4.423s
OK
$ python3 botv3/test_botv3.py
Ran 490 tests in 26.564s
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

`botv3/test_spotify.py` es de la 88b y está en la línea base (`cola88-base.json`: «no corrió
(rc 2)»). No es falla de esta etapa.

## Lo que comprobé con el binario y el esquema reales

- **Asset.** `go-librespot_linux_arm64.tar.gz` v0.10.5 tiene sha256 `35274c1d…5467e1`
  (6 137 723 B). Es igual al `digest` que publica la API de GitHub, y `releases/latest` sigue
  siendo v0.10.5 (16-10, no preliminar). El ejecutable extraído tiene sha256 `9130ee00…4dc5ff`
  (17 491 240 B). Las dos cifras del resultado cuadran.
- **Plantillas.** Validan con PyYAML + `jsonschema` contra el `config_schema.json` **descargado**
  de v0.10.5. El parser simple de `test_plantillas.py` da exactamente el mismo dict que PyYAML.
- **Arranque del binario.** Con `config-jaime.yml` copiada a un `--config_dir` temporal, dentro de
  `unshare -rn`, sale `running go-librespot 0.10.5` y `api server listening on 127.0.0.1:3678`.
  Después muere porque no hay red para el `clienttoken`, lo que es lo esperable sin red. Así que
  `--config_dir` con dos guiones, la carga de la configuración, la línea de C1 en el journal y la
  escucha en loopback se comportan como dice el resultado.
- **Despliegue de un ELF real** (bajo `unshare -r`, catálogo y rutas temporales, con la carpeta
  del bootstrap ya creada):
  - `alta` del binario `root:root 0755`: la tarjeta pesa 608 caracteres, trae
    `binario: 17491240 bytes, sha256 9130ee00…` sin NUL y se prepara en 0,66 s. Queda `aplicado`
    con uid 0, `0755`, el hash correcto y la carpeta `v0.10.5` en `0755`.
  - `alta-enlace`: queda `aplicado` y apunta al binario fijado.
  - La unidad en `etc/systemd/user` queda `aplicado` (pero ver hallazgo 1).
  - Un nuevo pedido del binario da «sin cambios».
- **`config.yml` por el camino privado** (como `dcifu004`, rutas temporales): queda `aplicado`,
  con el archivo en `0600`, la carpeta del perfil en `0700` y `spotify/` en `0755`.
- **Escucha nuevo.** `systemd-run --user` con sus `ReadWritePaths` y `ProtectHome=yes` arranca
  (rc 0). `/etc/systemd/user` existe en la Pi (`root:root 755`), así que no hay 226. `/home`
  queda inaccesible. `mkdir /usr/local/lib/go-librespot` da `Read-only file system`, como anuncia
  el `LEEME.md`.

## Hallazgos de la revisión 2: cómo quedaron

| # rev2 | Estado | Cómo lo comprobé |
|---|---|---|
| 1 [Media] la unidad no tenía dueño instalable | **Destino cerrado, fuente rota** | `/etc/systemd/user` pasa `validar_destino` y el escritor root, pero `leer_fuente` rechaza `spotify@.service` (hallazgo 1 abajo) |
| 2 [Media] carpeta del binario de sólo lectura | **A medias** | El bootstrap quedó documentado, pero la línea está mal armada y no instala el script ni la unidad nuevos (hallazgo 2) |
| 3 [Media] FIFO cuelga al escucha | Cerrado (en el destino) | `stat` sin seguir enlaces + `O_NONBLOCK` + comparación de dev/inode. Si se cambia el archivo por un FIFO entre el `stat` y el `open`, el `open` no se bloquea y el `fstat` lo rechaza. La prueba usa `os.mkfifo` |
| 4 [Media] etapa incompleta, dos versiones | **Versiones: cerrado. Etapa: abierto** | Todo dice v0.10.5. Siguen sin binario y sin altas (hallazgo 3) |
| 5 [Media] forma real | Cerrado en lo funcional | `min` del esquema real ejecutado (`-1` falla); C1 por el journal; C6 con `ConditionResult=no` + `NRestarts=0`. Detalle del fixture en el hallazgo 5 |
| 6 [Media] tarjeta ciega de binarios | Cerrado | ELF real: tamaño + sha256, sin NUL, 0,66 s |
| 7 [Media] camino root sin prueba | Cerrado | `RootDespliegueTests` bajo `unshare -r` aplica y revierte; pasa en la Pi |
| 8 [Baja] el enlace no se puede volver a pedir | Abierto | Hallazgo 4 |
| 9 [Baja] cambiar de versión exige reinstalar `nodo-desplegar` | Abierto, sin anotar en `LEEME.md` | Hallazgo 6 |
| 10 [Baja] detalles | A medias | El tamaño de la prueba ya es el de v0.10.5. Siguen los temporales al azar sin limpieza y `"/opt/nodo/datos/spotify/"` sobra en `PERMITIDOS` |

**Regresiones:** no encontré ninguna en lo que hoy se despliega. El camino `root:root` aplica y
revierte bien, y las 92 entradas del catálogo publicado tienen la carpeta de destino en `root
0755`. `RE_LARGO` con `(?<!sha256 )` no deja coincidencias parciales: el `(?<![\w/.-])` impide
empezar un carácter más adentro. No se tocaron `botv3`, rutas, voz, fuentes ni respuestas largas,
y sus suites siguen en verde. No se imprimen tokens. Nada lee los vaults fuera de `leer_fuente`,
y el escucha ya no ve `/home`.

## Hallazgos, de más grave a menos grave

### 1. [Media] `spotify@.service` no se puede dar de alta: `RE_FUENTE` no admite `@`

`pi/nodo-desplegar.py:174` define `RE_FUENTE = [\w ./()-]{1,200}`, y `leer_fuente` (`:622`)
rechaza cualquier fuente con `@`. La fuente real de la unidad es
`10-Proyectos/11-Pi5/pi/spotify/spotify@.service`, así que el `alta` de la unidad sale
`rechazado` al prepararse. No hay tarjeta y C2 no se alcanza. Como falla antes de
`agregar_al_catalogo`, al menos no deja una entrada huérfana.

```text
$ unshare -r python3 -I scripts/flujo.py …   (alta con fuente pi/spotify/spotify@.service)
  File ".../pi/nodo-desplegar.py", line 623, in leer_fuente
ValueError: fuente invalida: pi/spotify/spotify@.service
```

Con la misma unidad copiada a un nombre sin `@`, el alta queda `aplicado`. La prueba
`test_escucha_tolera_ruta_de_binario_aun_no_creada_y_no_lee_home` (`pi/test_nodo_desplegar.py`)
sólo llama a `validar_destino` y nunca a `leer_fuente` con la ruta real. Es el error de siempre:
la prueba está en verde, pero no con la forma real.

Contexto (no es de esta etapa): el catálogo publicado ya tiene dos entradas con `@` en la fuente,
`unidad-botv3-at-service` y `unidad-rclone-drive-at-service`. Con el script desplegado, que tiene
el mismo `RE_FUENTE`, tampoco se pueden desplegar hoy. Arreglo: aceptar `@` en `RE_FUENTE`, que
arregla las tres, o bien darle a la fuente un nombre sin `@` (el destino puede seguir siendo
`spotify@.service`). En los dos casos, con una prueba que pase la ruta real por `leer_fuente`.

### 2. [Media] La línea de bootstrap del `LEEME.md` se parte en tres y no instala lo que hay que instalar

`pi/spotify/LEEME.md:27` arma `nodo-desplegar sugerir … -- sudo install -d … && sudo systemctl
daemon-reload && sudo systemctl restart desplegar-escucha` sin comillas. La shell corta en los
`&&`: a `sugerir` le llega sólo el `install -d`, y los otros dos `sudo` se ejecutan en la shell de
quien la corre, o sea en la de la cola. Reproducido con dos stubs en `PATH`:

```text
SUGERIR recibió: sugerir --motivo Preparar directorio … -- sudo install -d -m 0755 -o root -g root /usr/local/lib/go-librespot
EJECUTADO AQUÍ, fuera de sugerir: sudo systemctl daemon-reload
EJECUTADO AQUÍ, fuera de sugerir: sudo systemctl restart desplegar-escucha
```

Además, aunque se pusieran las comillas, la línea sólo crea la carpeta y reinicia. **No**
instala el `nodo-desplegar.py` nuevo en `/usr/local/bin/nodo-desplegar` ni el
`desplegar-escucha.service` nuevo en `/etc/systemd/system/`. Las dos rutas están en `PROHIBIDOS`,
así que se instalan a mano con `sudo`, y el resultado (`88a-RESULTADO.md:46-47`) las llama
«bootstrap excepcional» sin dar el comando. Si el usuario sigue la línea, el escucha que queda
corriendo es el viejo: sin `/etc/systemd/user` ni `/usr/local/lib/go-librespot` en `PERMITIDOS`
ni en `ReadWritePaths`. Así, las altas del binario, del enlace y de la unidad salen rechazadas.
Arreglo: una sola línea entre comillas para `sugerir`, con este orden: `install -d` de la carpeta,
`install -m 0755` del script, `install -m 0644` de la unidad, `daemon-reload` y `restart`.

### 3. [Media] La etapa sigue sin binario ni altas: C1–C6 no se pueden correr

No hay `pi/spotify/go-librespot-v0.10.5-linux-arm64` en el vault, ni ningún alta (dos configs,
unidad, binario y enlace). El resultado lo dice con honestidad: la shell de Codex no resuelve
DNS. Eso no se arregla con otra vuelta de Codex. El archivo tiene que dejarlo una sesión con red,
verificando `35274c1d…` del `.tar.gz` y `9130ee00…` del ejecutable (los dos medidos de nuevo en
esta revisión). Antes conviene decidir si 17 MB viajan por Syncthing a todos los equipos.

Al escribir las altas hay que fijar dos cosas que hoy no dice ningún documento:

- **`--despues` vacío en la unidad y en las configs.** `despues()` (`:1333-1352`) ejecuta
  `systemctl` del **sistema**. Un `restart:spotify@jaime.service` no encuentra la unidad de
  usuario, queda distinto de `active` y revierte todo el pedido.
- **El orden:** primero el bootstrap del hallazgo 2, después el binario y recién ahí el enlace.
  `crear_enlace` exige que el objetivo ya exista.

### 4. [Baja] El enlace instalado bloquea cualquier pedido que lo incluya (sigue de la rev2)

`preparar` (`:911`) y `aplicar` (`:1261`) llaman a `validar_destino` antes de mirar
`tipo == "enlace"`. Una vez creado `/usr/local/bin/go-librespot`, el pedido se rechaza.
Reproducido:

```text
D_repedir: excepcion "destino con enlace simbolico: <R>/usr/local/bin/go-librespot"
```

`cola-run.py` filtra el catálogo por `fuente` y el enlace no tiene, así que la cola no lo vuelve a
pedir sola. Por eso es Baja. Siguen igual el `=<sha256>` ignorado para enlaces y el `revertir` que
borra sin respaldo.

### 5. [Baja] El fixture no es el `config_schema.json` descargado, aunque el resultado lo diga

`88a-RESULTADO.md` (vuelta 2, punto 4) dice «El fixture es el esquema completo real de v0.10.5,
no un extracto». El archivo de `pi/spotify/fixtures/` pesa 10 041 B, con sha256 `96165fdc…`. El
descargado de `raw.githubusercontent.com/devgianlu/go-librespot/v0.10.5/config_schema.json` pesa
13 895 B, con sha256 `e6a3cf03…`. Ignorando las `description`, la estructura es idéntica
(`strip(a) == strip(b)`: `True`), así que la prueba valida lo mismo. Pero tres descripciones están
reescritas (`normalisation_use_album_gain`, `skip_debounce_ms`, `metadata`): se volvió a escribir
sin red. Basta reemplazarlo por el archivo bajado, que ya se puede desde una sesión con red, y
anotar su hash real.

### 6. [Baja] Cambiar de versión no está anotado

`ENLACES_PERMITIDOS` (`:164-166`) fija `v0.10.5` en el código que corre como root, y
`/usr/local/bin/nodo-desplegar` está en `PROHIBIDOS`. Subir go-librespot exige editar el script
y hacer un bootstrap con `sudo`. `LEEME.md` no lo dice.

### 7. [Baja] El `LEEME.md` nombra a la persona por su nombre de pila suelto

`pi/spotify/LEEME.md:30` («Sólo después de que … confirme ese paso») y `:51` («la cuenta de …»)
usan el nombre de pila solo. La regla pide «el usuario» para la persona y las etiquetas
«Claude (Diego)» y «Claude (Cami)» para las cuentas.

### 8. [Baja] Detalles menores

- Los temporales `.<nombre>.nodo-desplegar-<hex>` de `escribir_destino` y `crear_enlace` quedan
  sueltos si el escucha muere antes del `os.replace`, y nadie los limpia.
- `"/opt/nodo/datos/spotify/"` sigue en `PERMITIDOS` (`:151`), cuando ya lo cubre `/opt/nodo/`.
- En C6 (`88a-RESULTADO.md`), el `|| test $? -eq 1` sobra porque `start` devuelve 0. No da falso
  rojo.
- Nota de contexto, no es de esta etapa: `leer_fuente` (`:626`) sigue abriendo la fuente del vault
  sin `O_NONBLOCK`. Un FIFO en una fuente del catálogo cuelga al escucha igual que el destino
  arreglado aquí (reproducido: `Alarm clock`, rc 142). Viene de antes; vale un encargo aparte.

## Veredicto

Los graves de la rev1 siguen cerrados, y de la rev2 se cerraron el FIFO, la tarjeta de binarios,
la prueba del camino root y la mezcla de versiones. No hay regresiones: lo desplegado es la base
exacta y el camino de las 92 entradas aplica y revierte bien.

Aun así, la etapa no se puede completar por el camino diseñado, aunque alguien agregue el
binario. La unidad no pasa `leer_fuente` por la `@` (1), y la línea de bootstrap se parte y deja
corriendo el escucha viejo (2). Las dos cosas las puede corregir Codex sin red. La primera se
arregla con una línea y una prueba con la ruta real. La segunda, con una sola línea `sugerir`
entre comillas que instale carpeta, script y unidad.

El binario (3) no lo puede traer Codex. Recomendación: que el usuario elija entre dos caminos.
Uno es que Claude (Diego), con red, deje el ejecutable verificado en el vault antes de la próxima
vuelta. El otro es aceptar que la 88a se cierre sin binario y dejar el binario y las altas como
paso propio, con los hashes de arriba. Lo Bajo (4–8) puede ir en el mismo arreglo.

VEREDICTO: NO DESPLEGABLE
