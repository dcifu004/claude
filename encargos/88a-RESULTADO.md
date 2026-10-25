# 88a — resultado de autor (no desplegado)

## Estado

Quedaron escritas y probadas localmente las dos plantillas, la unidad de usuario y la extensión
mínima de `nodo-desplegar` que permite que **sólo** las dos configuraciones Spotify reciban dueño
`dcifu004:dcifu004`. No se instaló nada como root, no se creó nada bajo `/opt/nodo/datos/spotify`,
no se vinculó una cuenta y no se abrió un enlace de `device_auth`.

**No está listo para desplegar aún.** La shell de esta corrida no tiene salida DNS/red hacia
GitHub (`curl: (6) Could not resolve host: api.github.com`), por lo que no fue posible bajar el
asset ni calcular el SHA-256 del ejecutable extraído. Tampoco se puede afirmar C1, instalar el
binario, crear su enlace simbólico ni copiar la forma real de `/auth/code`. No se sustituye un
binario por una compilación: hay un asset arm64 publicado, por lo que el bloqueo es sólo de esta
sesión de autor.

## Release fijado

- Versión estable fijada: `v0.10.5` (última estable observada el 16-10-2026).
- Asset arm64: <https://github.com/devgianlu/go-librespot/releases/download/v0.10.5/go-librespot_linux_arm64.tar.gz>
- SHA-256 del tar.gz publicado por GitHub y reproducido por Claude (Diego):
  `35274c1d3576090096d3459ecf76ee9c025258d19dc76f0bf724f95c525467e1` (6.137.723 B).
- SHA-256 del ejecutable extraído, medido por Claude (Diego):
  `9130ee00613abeb9620cc06fe9bc7080eba73618d547b0c71ec991f3504dc5ff`
  (17.491.240 B). El asset no quedó disponible en esta shell sin DNS; no se inventó ni se
  reconstruyó. Por eso aún falta incorporarlo al vault antes de poder hacer su alta real.

Los nombres de configuración se comprobaron contra el `config_schema.json` **completo** de ese
tag, guardado como `fixtures/config_schema.v0.10.5.json` (13.895 B, sha256
`e6a3cf037c27af877c35183b51e8df82c88ef0e2fb88ecd38ee2cca3a5ee50cc`): son
`zeroconf_enabled`, `initial_volume`, `server.address`, `server.port`, `credentials.type` y
`audio_backend`. El fixture fue reemplazado por el archivo real descargado del tag v0.10.5; la
prueba de plantillas sigue validando contra ese esquema completo.

## Archivos creados o modificados

| Vault | Destino de despliegue | Dueño y modo finales |
|---|---|---|
| `pi/spotify/config-jaime.yml` | `/opt/nodo/datos/spotify/jaime/config.yml` | `dcifu004:dcifu004 0600`; carpeta `0700` |
| `pi/spotify/config-pilar.yml` | `/opt/nodo/datos/spotify/pilar/config.yml` | `dcifu004:dcifu004 0600`; carpeta `0700` |
| `pi/spotify/spotify@.service` | `/etc/systemd/user/spotify@.service` | `root:root 0644` |
| `pi/spotify/LEEME.md` | no se despliega | — |
| `pi/spotify/fixtures/config_schema.v0.10.5.json` | no se despliega | — |
| `pi/spotify/test_plantillas.py` | no se despliega | — |
| `pi/nodo-desplegar.py` | `/usr/local/bin/nodo-desplegar` (bootstrap excepcional) | `root:root 0755` |
| `pi/desplegar-escucha.service` | `/etc/systemd/system/desplegar-escucha.service` (bootstrap excepcional) | `root:root 0644` |

La extensión del catálogo admite sólo `root:root` y `dcifu004:dcifu004`; el segundo dueño está
cerrado a las dos rutas `.../spotify/{jaime,pilar}/config.yml`. La unidad de escucha también
recibe las tres rutas adicionales con `ReadWritePaths`.

Pendiente de materializar desde el release y dar de alta:

| Origen esperado | Destino | Dueño y modo |
|---|---|---|
| `pi/spotify/go-librespot-v0.10.5-linux-arm64` | `/usr/local/lib/go-librespot/v0.10.5/go-librespot` | `root:root 0755` |
| enlace a ese archivo | `/usr/local/bin/go-librespot` | `root:root` (enlace) |

El catálogo actual aún no crea enlaces simbólicos: es otro pendiente explícito; no se dejó un
wrapper que pareciera enlace. La 88b mantiene los nombres, rutas y puertos acordados:
`jaime`/3678 y `pilar`/3679.

## Pruebas locales

```
$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK

$ python3 pi/test_nodo_desplegar.py
Ran 80 tests in 4.434s
OK
```

La primera valida el YAML contra el fixture local, puertos distintos en loopback, zeroconf
apagado, `device_auth`, nombres distintos y `%i` + `ConditionPathExists` en la unidad. La
segunda incluye los dos casos nuevos: el dueño de usuario sólo es válido para las dos configs y
la aplicación deja archivo `0600` y carpeta `0700` del usuario.

`systemd-analyze verify` no se pudo usar dentro del sandbox: falla antes de leer las unidades con
`SO_PASSCRED failed: Operation not permitted`. No es una prueba de la Pi real ni se la cuenta como
verde.

## Verificaciones posteriores al despliegue

Primero, como `dcifu004`, habilitar las instancias una vez:

```bash
systemctl --user daemon-reload && systemctl --user enable --now spotify@jaime spotify@pilar
```

**C1 — binario y versión.** Una vez calculado y anotado el digest extraído:

```bash
sha256sum /usr/local/lib/go-librespot/v0.10.5/go-librespot && readlink -f /usr/local/bin/go-librespot && journalctl --user -u spotify@jaime -n 30 --no-pager -o cat | grep 'running go-librespot'
```

**C2 — ambas instancias activas:**

```bash
systemctl --user is-active spotify@jaime spotify@pilar
```

Salida esperada: `active` y `active`.

**C3 — sólo loopback y sin mDNS:**

```bash
ss -ltnp '( sport = :3678 or sport = :3679 )' && ss -lunp 'sport = :5353'
```

La primera salida debe mostrar únicamente `127.0.0.1:3678` y `127.0.0.1:3679`; la segunda no
debe atribuir 5353 a `go-librespot`.

**C4 — códigos, antes de vincular:**

```bash
curl -s 127.0.0.1:3678/auth/code; printf '\n'; curl -s 127.0.0.1:3679/auth/code; printf '\n'
```

Copiar literalmente ambas respuestas aquí al cerrar el encargo; deben traer URL/código distintos.

**C5 — permisos efectivos:**

```bash
stat -c '%U:%G %a %n' /opt/nodo/datos/spotify/jaime /opt/nodo/datos/spotify/jaime/config.yml /opt/nodo/datos/spotify/pilar /opt/nodo/datos/spotify/pilar/config.yml
```

Salida esperada, en orden: `dcifu004:dcifu004 700`, `dcifu004:dcifu004 600`,
`dcifu004:dcifu004 700`, `dcifu004:dcifu004 600`.

**C6 — condición al faltar `config.yml`; restaura al terminar:**

```bash
systemctl --user stop spotify@jaime
mv /opt/nodo/datos/spotify/jaime/config.yml /opt/nodo/datos/spotify/jaime/config.yml.c6
systemctl --user start spotify@jaime
systemctl --user show spotify@jaime -p ActiveState -p ConditionResult -p NRestarts
mv /opt/nodo/datos/spotify/jaime/config.yml.c6 /opt/nodo/datos/spotify/jaime/config.yml
systemctl --user start spotify@jaime && systemctl --user is-active spotify@jaime
```

La penúltima comprobación debe incluir `ActiveState=inactive`, `ConditionResult=no` y
`NRestarts=0`; la última debe devolver `active`.

## Pendientes para la corrección

1. Bajar el asset desde una sesión con red, verificar el SHA-256 publicado y extraer el binario
   al vault; calcular y registrar su SHA-256 final.
2. Incorporar el asset arm64 real de `v0.10.5` al vault y volver a correr la prueba contra sus
   bytes, sin sustituirlo por una compilación.
3. Incorporar al catálogo una operación de enlace simbólico, limitada al enlace
   `/usr/local/bin/go-librespot` → versión fijada, o aprobar otro mecanismo que mantenga el
   enlace literal exigido.
4. Actualizar de forma controlada el `nodo-desplegar` y su unidad antes de las altas Spotify;
   su sandbox actual no puede escribir estas rutas nuevas.
5. Sólo después: altas con hash de cada archivo, despliegue por botones y C1–C6. La vinculación
   queda fuera de 88a y se hace desde `/spotify` en 88b.

## Arreglos vuelta 1

**Estado conservador: sigue NO DESPLEGABLE.** No se desplegó, no se escribió bajo
`/opt/nodo/datos/spotify`, no se tocaron perfiles ni n8n. La corrección dejó resueltos los
hallazgos 1–4 y 8 en el vault; los 5–7 no se pueden cerrar honestamente sin el asset arm64 y su
esquema completo reales. Esta shell no resuelve DNS ni abre TCP a GitHub (`curl` devuelve
`Could not resolve host`); no se reemplazó el binario por una compilación ni por datos inventados.

1. **[Grave] Ruta inexistente del escucha.** `ReadWritePaths` usa ahora
   `-/usr/local/lib/go-librespot` y también hace opcional la carpeta de la unidad de usuario.
   La prueba `DuenosSpotifyTests.test_escucha_tolera_ruta_de_binario_aun_no_creada_y_no_lee_home`
   lee la forma real de `pi/desplegar-escucha.service` y exige ambos prefijos `-`.
2. **[Grave] Flag de la unidad.** `spotify@.service` cambió `-config_dir` por
   `--config_dir`; la prueba de plantilla exige literalmente la forma de dos guiones. Es la forma
   que `go-librespot --help` mostró en la reproducción de Claude (Diego).
3. **[Grave] Carrera de `chown` por enlace.** `nodo-desplegar` abre los directorios tramo a
   tramo con `O_DIRECTORY|O_NOFOLLOW`, opera sobre el descriptor y, para las carpetas privadas,
   crea el archivo bajo la identidad efectiva de `dcifu004`. Ya no hay `chown`/`chmod` por ruta
   dentro de un directorio que controla ese usuario. Las pruebas usan un perfil temporal
   escribible, prohíben `os.chown` por ruta y, en la forma exacta de la carrera, reemplazan el
   perfil por un enlace a una víctima durante `fchown`; verifican que la víctima no recibe ni
   `config.yml` ni cambio de modo.
4. **[Media] Tope del binario extraído.** `MAX_FUENTE` pasó de 8 a 24 MiB. La prueba llama la
   función real `leer_fuente` con 17.491.240 bytes, el tamaño real informado para el binario arm64
   extraído por Claude (Diego), no con el tamaño comprimido de 5,81 MB.
5. **[Media] Última versión estable.** Se fijó en el código de enlace la ruta objetivo de
   `v0.10.5`, que fue la última estable observada por Claude (Diego). Falta bajar y verificar su
   asset real; por eso no se anota un SHA-256 ni se declara cumplido este hallazgo.
6. **[Media] Forma real del esquema y C1.** La prueba de la unidad corrige el flag real, pero el
   fixture completo aún no podía ejecutarse contra el binario, ni C1 leer su
   línea `running go-librespot …` desde el journal. No se declara cubierto: requiere descargar el
   `config_schema.json` completo y el asset de `v0.10.5`.
7. **[Media] Binario, altas y enlace.** Se agregó `nodo-desplegar alta-enlace`, limitado a la
   única pareja exacta `/usr/local/bin/go-librespot` →
   `/usr/local/lib/go-librespot/v0.10.5/go-librespot`; una prueba rechaza cualquier otro objetivo.
   El binario, su SHA-256 y las altas reales siguen ausentes por el mismo bloqueo de red, de modo
   que no se afirma C1–C6.
8. **[Media] Lectura de todo `/home`.** La unidad cambió a `ProtectHome=tmpfs` y expone sólo
   `~/.config/systemd/user` mediante `BindPaths`; la misma prueba del punto 1 exige
   ambas directivas.

También se cerraron dos bajos sin ampliar alcance: `PERMITIDOS_EXACTOS` evita que
`spotify@.service` sea un prefijo para `spotify@.service.d`, y el comando de desvincular usa
`rm -f`. `LEEME.md` explica que, si LUKS se abre después del arranque, hay que iniciar las dos
instancias de usuario una vez.

### Suites ejecutadas (salida real, sin despliegue)

```text
$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK

$ python3 pi/test_nodo_desplegar.py
Ran 84 tests in 4.354s
OK

$ python3 botv3/test_botv3.py
Ran 490 tests in 16.495s
OK (skipped=4)

$ python3 botv3/test_temporizadores.py
✅ todo en verde

$ python3 botv3/test_compras.py
✅ todo en verde

$ python3 botv3/test_spotify.py
python3: can't open file '/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/botv3/test_spotify.py': [Errno 2] No such file or directory

rc: plantillas=0 nodo=0 botv3=0 temporizadores=0 compras=0 spotify=2
```

`systemd-analyze verify` tampoco puede ejecutarse en este sandbox: termina antes de leer la
unidad con `SO_PASSCRED failed: Operation not permitted` (rc 1). No se cuenta como prueba verde.

## Arreglos vuelta 2

**Estado conservador: el código y las plantillas quedaron corregidos, pero no se declara
desplegable hasta que el asset arm64 real quede en el vault.** No se usó `sudo`, no se desplegó,
no se escribió en `/opt/nodo/datos/spotify`, no se vinculó Spotify y no se tocó n8n ni perfiles.
La única ambigüedad fue el asset: esta shell sigue sin DNS para GitHub, así que se conserva como
pendiente explícito en vez de crear un ELF falso con el hash de Claude (Diego).

1. **[Media] La unidad no tenía dueño instalable.** Se mueve a
   `/etc/systemd/user/spotify@.service`, que es root:root 0755 y la leen los gestores de usuario.
   Se agregó ese prefijo cerrado al catálogo y al aislamiento del escucha; se retiró la exposición
   de `/home` y quedó `ProtectHome=yes`. Lo cubre
   `DuenosSpotifyTests.test_escucha_tolera_ruta_de_binario_aun_no_creada_y_no_lee_home`, que lee
   la unidad real y llama a `validar_destino()` para el destino real.
2. **[Media] La carpeta del binario no nacía bajo `ProtectSystem=strict`.** `LEEME.md` deja el
   único bootstrap, solicitado con `nodo-desplegar sugerir`, para crear
   `/usr/local/lib/go-librespot` root:root 0755 antes de reiniciar el escucha. No se ejecutó aquí.
   La misma prueba del punto 1 comprueba la ruta opcional real y la lista de escritura de la
   unidad; el comando documentado impide que la primera alta dependa de un directorio inexistente.
3. **[Media] Un FIFO podía colgar el escucha.** `leer_destino()` hace `stat(...,
   follow_symlinks=False)` y exige un regular de un solo enlace antes de abrirlo; la apertura
   restante usa `O_NONBLOCK` y compara dispositivo/inodo contra el `stat`. Lo cubre
   `DuenosSpotifyTests.test_fifo_del_perfil_se_rechaza_sin_esperar_un_escritor`, que crea con
   `os.mkfifo()` el `config.yml` en la carpeta de perfil y verifica el rechazo inmediato.
4. **[Media] Versiones mezcladas y etapa incompleta.** Plantillas, fixture y documentación ahora
   nombran v0.10.5; se registraron URL, tamaños y ambos SHA-256 medidos por Claude (Diego). El
   fixture es el esquema completo real de v0.10.5, no un extracto. Falta sólo el archivo binario
   real en el vault: por la falta de DNS de esta sesión, no hay alta real que probar ni se afirma
   C1--C6. Éste es el pendiente que todavía impide despliegue.
5. **[Media] Forma real del esquema y verificaciones.**
   `test_plantillas.py` carga `config_schema.v0.10.5.json` completo y entiende tanto `min` como
   `minimum`; además prueba que `initial_volume: -1` falla por el `min: 0` real. C1 debe comparar
   el SHA-256 anterior y obtener la versión desde `journalctl --user -u spotify@jaime` (v0.10.5 no
   acepta `--version`). Para C6, la comprobación correcta es `ActiveState=inactive`,
   `ConditionResult=no` y `NRestarts=0`, no `Result=condition-failed`.
6. **[Media] Tarjeta ciega para binarios.** Si la fuente contiene NUL, el diff ahora dice
   `binario: N bytes, sha256 …` en vez de decodificar un ELF; el enmascarado conserva ese SHA-256
   verificable. Lo cubre
   `DuenosSpotifyTests.test_tarjeta_de_un_elf_muestra_tamano_y_sha_sin_volcar_bytes`, que usa los
   bytes reales de `/usr/bin/true` (ELF con NUL), pasa por `preparar()` y comprueba la tarjeta que
   recibiría Telegram.
7. **[Media] El camino root:root no estaba protegido por suite.**
   `RootDespliegueTests.test_aplicar_y_revertir_root_por_descriptores_en_namespace_real` ejecuta
   el camino real bajo `unshare -r`: crea un destino previo, aplica por `Escucha.aplicar()`,
   verifica uid 0/modo 0755 y revierte desde el respaldo por descriptor. También conserva el
   rechazo de directorio root inseguro en `escribir_destino`.

### Verificaciones posteriores corregidas

Cuando el asset real esté en el vault, C1 se verifica así (la línea del journal reemplaza el flag
inexistente):

```bash
sha256sum /usr/local/lib/go-librespot/v0.10.5/go-librespot && readlink -f /usr/local/bin/go-librespot && journalctl --user -u spotify@jaime -n 30 --no-pager -o cat | grep 'running go-librespot'
```

C6 conserva el renombre/restauración de la sección anterior, pero después de `start` se consulta:

```bash
systemctl --user show spotify@jaime -p ActiveState -p ConditionResult -p NRestarts
```

La salida válida es `ActiveState=inactive`, `ConditionResult=no` y `NRestarts=0`; `start` puede
devolver 0 aunque la condición no se cumpla.

### Suites ejecutadas (salida real, sin despliegue)

```text
$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK

$ python3 pi/test_nodo_desplegar.py
Ran 87 tests in 4.455s
OK

$ python3 botv3/test_botv3.py
Ran 490 tests in 16.640s
OK (skipped=4)

$ python3 botv3/test_temporizadores.py
  ok  0660 tras deshacer
  ok  0660 tras marcar avisadas
✅ todo en verde

$ python3 botv3/test_compras.py
  ok  deja pasar «lava el carro»
  ok  deja pasar «saca el auto del carro»
✅ todo en verde

$ python3 botv3/test_spotify.py
python3: can't open file '/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/botv3/test_spotify.py': [Errno 2] No such file or directory

rc: plantillas=0 nodo=0 botv3=0 temporizadores=0 compras=0 spotify=2
```

`botv3/test_spotify.py` no existe en este árbol; conserva el rc 2 que ya constaba en la línea
base y no se simula una suite inexistente. Los cuatro skips de `test_botv3.py` corresponden a
sockets locales que el sandbox prohíbe, no a las rutas Spotify.
