# Encargo 88ar — Revisión 1 del 88a (Claude (Diego), 25-10-2026)

Sólo revisión: no se tocó código. Es la primera revisión (no hay `88ar*-RESULTADO.md` previos).
No hay `88a-PLAN.md`, `88a-decisiones.md` ni `88a-busquedas.jsonl`. Tampoco existe
`encargos/manual-busquedas.jsonl` (sólo `manual-busquedas-prueba-encargo32.jsonl`, de otro
encargo), así que no hay líneas dentro de la ventana de autor (25-10 11:10–11:21).

Leí primero el diff propio (`cola88-88a-diff.txt`, 10 archivos, sin «Cambios ajenos»). Las
reproducciones corrieron en directorios de `mktemp -d`, con `BOTV3_USO_CUENTAS`,
`BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` apuntando ahí. Desde esta shell **sí** hay salida a GitHub,
así que bajé el asset `v0.10.2` arm64 y su `config_schema.json` a un temporal y corrí el binario
real con un `HOME` temporal (sin vincular nada ni pedir códigos a Spotify).

## Pruebas (salida real)

```text
$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK
$ python3 pi/test_nodo_desplegar.py
Ran 80 tests in 4.360s
OK
$ python3 botv3/test_botv3.py
Ran 490 tests in 26.703s
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

`botv3/test_spotify.py` es de la 88b y ya figura en la línea base (`cola88-base.json`:
«no corrió (rc 2)»): no es falla de esta etapa. Todo en verde, pero ver hallazgos 2 y 6: dos de
las pruebas nuevas fijan comportamiento equivocado.

## Hallazgos, de más grave a menos grave

### 1. [Grave] La unidad nueva del escucha no arranca: `ReadWritePaths` apunta a una carpeta que no existe

`pi/desplegar-escucha.service:28` agrega `/usr/local/lib/go-librespot` **sin** el prefijo `-`.
Esa carpeta no existe en la Pi (`ls: cannot access '/usr/local/lib/go-librespot'`) y systemd no
puede montar en el espacio de nombres una ruta inexistente: la unidad muere con
`226/NAMESPACE` antes de ejecutar `nodo-desplegar escuchar`. Y la única que crearía esa carpeta
es justamente esa unidad, así que no se arregla sola: queda abajo el canal de despliegue entero
(todo lo que hoy se instala con ✅), no sólo Spotify. El resultado presenta este cambio como
«bootstrap excepcional» para desplegarlo primero.

Reproducción (unidad transitoria de usuario, mismas opciones):

```text
$ systemd-run --user --wait --collect -q -p PrivateUsers=yes -p ProtectSystem=strict -p ReadWritePaths=/no/existe/88ar /bin/true
rc=226
$ ... -p ReadWritePaths=-/no/existe/88ar /bin/true
rc=0
```

Arreglo: `-/usr/local/lib/go-librespot` (y, por la misma razón, `-~/.config/systemd/user`
en la línea 29, que hoy existe pero no tiene por qué existir siempre). Con el guión, la primera
instalación del binario necesita que la carpeta exista antes de arrancar el escucha o que caiga
bajo una ruta ya montada; hay que decidir cuál.

### 2. [Grave] `-config_dir` con un solo guión no sirve en v0.10.2: el servicio cae y reinicia cada 10 s para siempre

`pi/spotify/spotify@.service:15` usa `-config_dir`. El binario v0.10.2 usa `pflag`: `-config_dir`
se lee como el atajo `-c` (`--conf`) con valor `onfig_dir`. Con el binario real:

```text
$ go-librespot -config_dir $D/cfg
level=fatal msg="failed loading config" error="invalid config override format: onfig_dir (expected field=value)"
$ go-librespot --config_dir $D/cfg
level=fatal msg="failed loading config" error="failed reading configuration file: ..."   ← sí usa la carpeta
$ go-librespot --help
  -c, --conf stringArray    override config values ...
      --config_dir string   the configuration directory ...
```

Con `Restart=on-failure` y `RestartSec=10`, el límite por defecto (5 arranques en 10 s) nunca se
alcanza: las dos instancias quedan en bucle de fallo indefinido, justo lo que el encargo pedía
evitar, y C2 no se cumple nunca. El encargo dictó `-config_dir` (lo repite el README del
proyecto), pero también pidió confirmar contra la **versión fijada**; la prueba
`pi/spotify/test_plantillas.py:94` congela la cadena rota con `assertIn`. Arreglo:
`--config_dir` en la unidad y en la prueba, y anotarlo en el resultado porque la 88b hereda la
unidad.

### 3. [Grave] El `chown` a `dcifu004` como root sigue enlaces simbólicos: un proceso de `dcifu004` se adueña de `/usr/local/bin` o `/etc/systemd/system`

`pi/nodo-desplegar.py:1079-1080` y `:1087-1088` hacen `os.chown`/`os.chmod` **por ruta**, que
siguen enlaces. Con `dueno = dcifu004:dcifu004`, la carpeta del perfil queda de `dcifu004`
(0700), así que `dcifu004` controla los nombres dentro de ella. Entre el `os.open(... O_EXCL |
O_NOFOLLOW)` + `fsync` del temporal y el `os.chown(tmp, uid, gid)`, basta con borrar
`.config.yml.nodo-desplegar` y dejar en su lugar un enlace a `/usr/local/bin` (ruta escribible
dentro del espacio de nombres del escucha): root le entrega el directorio a `dcifu004`, que
después reemplaza `/usr/local/bin/nodo-desplegar` o deja una unidad en `/etc/systemd/system`.
Es escalar a root sin pasar por el ✅, que es la frontera que `nodo-desplegar` existe para
cuidar (no es el «límite aceptado del buscador», que habla de fabricar autorizaciones de
búsqueda). `validar_destino` sólo mira enlaces **antes**, y además `os.replace` termina dejando
el enlace como `config.yml` y el pedido sale `aplicado`.

Reproducción sin root (`carrera.py` en temporal; `os.fsync` y `shutil.copy2` envueltos para hacer
el cambio en el instante en que lo haría el atacante; `os.chown` espiado):

```text
A aplicar: ('aplicado', '1 archivo(s); respaldo en .../desplegar-a')
A chown sobre: [('.../spotify/jaime/.config.yml.nodo-desplegar', '.../victima')]
A modo victima: 0o600
B aplicar: ('aplicado', '1 archivo(s); respaldo en .../desplegar-b')
B chown sobre: [('.../spotify/jaime', '.../victima'), ...]
B modo victima: 0o700 contenido: ['config.yml']
```

El caso A sólo necesita que la carpeta del perfil sea de `dcifu004`, que es lo que este cambio
garantiza. El caso B (cambiar la carpeta del perfil por un enlace entre `validar_destino` y el
`chown`) requiere que `/opt/nodo/datos/spotify` sea de `dcifu004`; hoy no existe y
`/opt/nodo/datos` es de `dcifu004`, así que `dcifu004` puede crearla antes del primer
despliegue. Arreglo: abrir la carpeta con `O_DIRECTORY | O_NOFOLLOW`, crear el temporal con
`dir_fd`, y usar `os.fchown`/`os.fchmod` sobre los descriptores (o `follow_symlinks=False`
con `dir_fd`), más una prueba que haga este cambio en medio. Nota de contexto, no de esta
etapa: el `os.chown(tmp, 0, 0)` + `chmod` previo tiene el mismo patrón para destinos en carpetas
de `dcifu004`, pero entregaba a root, no a `dcifu004`.

### 4. [Media] `MAX_FUENTE` de 8 MB no deja pasar el binario: 5,81 MB era el `.tar.gz`

`pi/nodo-desplegar.py:122` sube el tope «porque go-librespot arm64 mide 5,81 MB». Ese es el
tamaño del **comprimido** (6 096 158 B). El ejecutable extraído mide **17 380 232 B**
(`sha256 8ae6c19adc4656126943d5b00d8397a70981197a66406482542952ae171c8c7c`, calculado en esta
revisión, no publicado por el autor). Con el `leer_fuente` real sobre un vault temporal:

```text
MAX_FUENTE 8388608
rechazo: fuente demasiado grande: pi/spotify/go-librespot-v0.10.2-linux-arm64
```

El camino previsto para C1 no funciona. Además, dejar 17 MB dentro del vault lo sincroniza
Syncthing a todos los equipos: conviene decidir antes si el binario viaja por el vault o se
baja con hash fijo en la propia Pi.

### 5. [Media] v0.10.2 no es la última estable

El encargo pedía «la última versión estable publicada». En la API de GitHub,
`releases/latest` es **v0.10.5 (16-10-2026)**, con v0.10.3 y v0.10.4 entre medio, ninguna marcada
como preliminar. La v0.10.2 y su hash del `.tar.gz` (`800b174f…a4d`) sí cuadran con lo
publicado. Al cambiar de versión hay que volver a revisar los flags (hallazgo 2) y el esquema.

### 6. [Media] Las pruebas no usan la forma real: el esquema es un «extracto» escrito a mano y el comando de C1 no existe

- `pi/spotify/fixtures/config_schema.v0.10.2.json` dice ser un «extracto fiel» pero se escribió
  sin red. Contra el real: las claves y los `enum` usados coinciden, pero `initial_volume` lleva
  `"min"` en el original y `"minimum"` en el extracto (`test_plantillas.py:66` valida una
  restricción que el esquema real no expresa así). El encargo pedía bajar el esquema y guardarlo.
  Hoy se puede: 13 834 bytes en `raw.githubusercontent.com/devgianlu/go-librespot/v0.10.2/config_schema.json`.
- C1 (`encargos/88a-RESULTADO.md:93`) usa `go-librespot --version`, que en v0.10.2 da
  `level=fatal ... error="unknown flag: --version"` (rc 1). La versión sólo aparece al arrancar
  (`level=info msg="running go-librespot 0.10.2"`): C1 debe leerla del journal
  (`journalctl --user -u spotify@jaime | grep 'running go-librespot'`).
- Ninguna prueba ejecuta el binario ni comprueba que la unidad arranque. Lo mínimo sería un
  `--help` del binario fijado mirando que exista `--config_dir`.
- La de `aplicar` comprueba `st_uid == os.getuid()`: corriendo como `dcifu004`, el `chown` a
  `dcifu004` no cambia nada, así que no distingue un `chown` correcto de uno ausente.

### 7. [Media] La etapa quedó incompleta: falta el binario, su alta y el enlace

Lo reconoce el propio resultado: no hay binario en el vault, ni SHA-256 del ejecutable, ni
alta en el catálogo, ni forma de crear `/usr/local/bin/go-librespot` como enlace. Tampoco hay
alta para las tres plantillas: sólo existe el soporte de `--dueno`. Sin eso, C1–C6 no se pueden
correr. No está mal haberse detenido sin red, pero el pendiente 3 (agregar enlaces al catálogo)
amplía otra vez el código de root y debería pasar por el mismo cuidado que el hallazgo 3.

### 8. [Media] `ProtectHome=read-only` le abre a root la lectura de todo `/home`

`pi/desplegar-escucha.service:34` pasa de `yes` a `read-only` sólo para escribir una unidad en
`~/.config/systemd/user`. Con eso, el proceso root del escucha puede leer `~/.ssh`, `~/.claude`,
`~/.codex` y todo lo demás de `/home`. Hoy ningún camino del código lee ahí (`leer_fuente` se
limita al vault, con `O_NOFOLLOW` y `readlink`), así que es una segunda capa que se pierde, no
una fuga. Alternativa: `ProtectHome=tmpfs` + `BindPaths=~/.config/systemd/user`.

### 9. [Baja] `PERMITIDOS` compara prefijos de texto y deja pasar `spotify@.service.d/…`

`pi/nodo-desplegar.py:148-150`: `"~/.config/systemd/user/spotify@.service"` como
prefijo también acepta `spotify@.service.d/override.conf` o `spotify@.servicefoo`. El dueño de
esa carpeta igual puede escribirlos él mismo, así que el impacto es bajo, pero va contra la idea
de una lista cerrada. `-/opt/nodo/datos/spotify` en `ReadWritePaths` (línea 29) sobra: ya está
bajo `/opt/nodo`.

### 10. [Baja] Con LUKS cerrado al arrancar, las unidades no vuelven solas

`ConditionPathExists` evita el bucle (bien), pero se evalúa una sola vez: al abrir el volumen
con `abrir-datos`, `spotify@jaime`/`@pilar` siguen inactivas hasta un `systemctl --user start`.
Conviene anotarlo en `LEEME.md` o sumarlo a lo que hace `abrir-datos`.

### 11. [Baja] El comando para desvincular no corre si no hay `state.json`

`pi/spotify/LEEME.md:45`: con `stop && rm … && start`, si `state.json` no existe el `rm` falla y
la instancia queda detenida. `rm -f` evita el caso.

## Lo que revisé y está bien

- Las claves de configuración (`zeroconf_enabled`, `credentials.type: device_auth`,
  `server.enabled/address/port`, `audio_backend: pulseaudio`, `initial_volume`, `bitrate`)
  existen con esos nombres en el esquema real de v0.10.2, que en la raíz tiene
  `additionalProperties: false`; las plantillas validan contra él. `initial_volume` va en
  pasos y `volume_steps` vale 100 por defecto, así que 40 = 40 %.
- El README de v0.10.2 confirma `device_auth` y `GET /auth/code` mientras se espera la
  aprobación.
- `validar_dueno` limita `dcifu004:dcifu004` a las dos rutas exactas y se aplica en el alta, al
  preparar el pedido y al aplicar. `revertir` restaura con `copy2` sobre el archivo existente y
  no le cambia el dueño.
- No se tocaron `botv3`, rutas, voz, fuentes ni respuestas largas; sus suites siguen en verde.
- No se imprimen tokens ni se leen los vaults fuera del camino de `leer_fuente`. Nada se
  escribió en `/opt/nodo/datos` y no se vinculó ninguna cuenta.

## Veredicto

No desplegable. El hallazgo 1 deja sin escucha a todo el canal de despliegue en cuanto se
instale la unidad nueva. El 3 le da a un proceso de `dcifu004` una forma de adueñarse de un
directorio de root durante un despliegue aprobado. El 2 deja los dos receptores en bucle de
fallo. Para la corrección hacen falta además el 4 y el 7 (binario, altas y enlace) y la forma
real del 6 (esquema completo descargado, C1 por el journal y una prueba que ejecute el binario
fijado). Los hallazgos 5 y 8 a 11 pueden ir en el mismo arreglo.

VEREDICTO: NO DESPLEGABLE
