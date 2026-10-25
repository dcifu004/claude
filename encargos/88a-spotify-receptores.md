# Encargo 88a: dos receptores Spotify Connect en la Pi, uno por perfil (Claude (Diego), 25-10-2026)

Primera de dos etapas: **88a receptores** → 88b intención del bot. La 88b usa los puertos,
rutas y nombres que esta etapa fija; no los cambies sin anotarlo en el resultado.

## Leer primero

- `36 - Spotify por perfil (diseño).md`: **el diseño aprobado**. Se implementa, no se rediseña.
- `pi/luces.service` y su comentario: molde de unidad que depende del systemd de usuario de
  `dcifu004` (linger activo).
- `pi/nodo-desplegar.py`, sólo la parte del catálogo y de `alta`: cómo se da de alta un archivo
  nuevo, con su ruta de destino, dueño, modo y hash.
- `encargos/trampas.md`, sección «Root, systemd y despliegue».

## No hace falta leer

`botv3/botv3.py` (eso es la 88b), las páginas de Cockpit, `parlante`/`escucha` (no existen) ni
el resto de las notas numeradas.

## Antecedentes

- Backlog 08 (12-09) y diseño 15: Spotify quedó después del Roku por tres condiciones: Premium,
  un receptor en la Pi y el parlante de 5 W sólo para voz. Hoy las tres están resueltas:
  las dos cuentas son Premium (el usuario lo confirmó el 25-10), el receptor lo pone esta etapa
  y el parlante es un Edifier G2000 por USB de audio (nota 24, 25-10). go-librespot sale por
  el sink por defecto: no elijas un sink a mano.
- Verificado el 25-10: `apt-cache policy librespot spotifyd` en la Pi no devuelve nada (Debian 13
  no los trae). PipeWire 1.4.2 corre como `dcifu004` con `pipewire-pulse` (linger=yes). No hay
  encargos ni descartes previos sobre Spotify.

## Contexto

El usuario quiere decir «reproduce Oxytocin de Billie Eilish en Spotify» y que suene **con su
cuenta**; el perfil `pilar`, con **la de Camila**. Se usa `go-librespot`
(<https://github.com/devgianlu/go-librespot>), que trae una API HTTP local
(`POST /player/play {"uri": …}`, `/player/pause`, `/player/resume`, `/status`, `/auth/code`).

## Qué hacer

1. **Binario fijado.** Toma la última versión estable publicada de `go-librespot` con un asset
   **linux arm64** ya compilado. Anota en el resultado la versión, la URL y el SHA-256. El
   catálogo de `nodo-desplegar` lo instala como root en
   `/usr/local/lib/go-librespot/<versión>/go-librespot` (`root:root 0755`), con el enlace
   `/usr/local/bin/go-librespot`. **Si no hay asset arm64, te detienes y lo reportas**: no
   compiles Go en la Pi.
2. **Unidad de usuario `spotify@.service`** para `dcifu004` (`~/.config/systemd/user/`, dada de
   alta en el catálogo). Instancias `jaime` y `pilar`:
   `ExecStart=/usr/local/bin/go-librespot -config_dir /opt/nodo/datos/spotify/%i`,
   `ConditionPathExists=/opt/nodo/datos/spotify/%i/config.yml`, `Restart=on-failure`,
   `RestartSec=10`. Con LUKS cerrado, la unidad no arranca y no deja error en bucle.
3. **Configuración por perfil** en `/opt/nodo/datos/spotify/<perfil>/config.yml`. La carpeta va
   en `dcifu004:dcifu004 0700` y el archivo en `0600`, porque ahí queda la credencial guardada,
   dentro de LUKS:

   | clave | jaime | pilar |
   |---|---|---|
   | `device_name` | `Casa · Jaime` | `Casa · Pilar` |
   | `credentials.type` | `device_auth` | `device_auth` |
   | `zeroconf` | apagado (que nadie de la red tome el receptor) | ídem |
   | `server` | habilitado, `127.0.0.1:3678` | habilitado, `127.0.0.1:3679` |
   | `audio_backend` | `pulseaudio` (pipewire-pulse) | ídem |
   | volumen inicial | 40 % | 40 % |
   | `bitrate` | 160 | 160 |

   Confirma los nombres exactos de las claves en el `config_schema.json` o el README de la
   **versión fijada**, no de memoria.
4. **Plantillas en el vault:** `pi/spotify/config-jaime.yml`, `pi/spotify/config-pilar.yml` y
   `pi/spotify/spotify@.service`. Más `pi/spotify/LEEME.md` con la instalación, cómo se ve el
   código de vinculación (`curl -s 127.0.0.1:3678/auth/code`) y cómo se desvincula una cuenta
   (borrar la credencial guardada en la carpeta del perfil).
5. **Alta en `nodo-desplegar`** de cada archivo nuevo, con destino, dueño, modo y hash. El
   despliegue lo pide la cola con botones. Tú no instalas nada como root.

## Criterios de aceptación

- **C1.** El binario instalado coincide con el SHA-256 anotado.
  `go-librespot --version` (o el flag equivalente de esa versión) corre en la Pi y muestra la
  versión fijada.
- **C2.** Tras el despliegue, `systemctl --user is-active spotify@jaime spotify@pilar` da
  `active active`.
- **C3.** `ss -ltnp` muestra 3678 y 3679 **sólo** en `127.0.0.1`. Nada de go-librespot escucha
  en `0.0.0.0`, en `::` ni en mDNS (5353).
- **C4.** Sin vincular, `curl -s 127.0.0.1:3678/auth/code` devuelve una URL y un código (forma
  real copiada en el resultado), y lo mismo en 3679 con un código distinto.
- **C5.** La carpeta y el archivo de cada perfil tienen exactamente el dueño y el modo de la
  tabla (`stat -c '%U:%G %a'`).
- **C6.** Con `/opt/nodo/datos/spotify/jaime/config.yml` renombrado a propósito, la unidad
  queda `inactive (condition failed)` y no reinicia en bucle. Restaura el archivo al terminar.

C2 a C6 sólo se pueden comprobar tras el despliegue. Deja en el resultado los comandos exactos
para que la revisión y el usuario los corran. La vinculación real (aprobar con cada cuenta)
**no** es parte de esta etapa: la hace cada persona desde `/spotify` (88b).

## Invariantes

- **Archivos compartidos:** no aplica. Cada instancia tiene su carpeta y su lockfile (go-librespot
  rechaza dos instancias sobre la misma carpeta).
- **Dueño y modo:** en la tabla del paso 3 y en el paso 1.
- **Pruebas sin escritura en `/opt/nodo/datos` ni avisos reales:** las pruebas del vault no
  escriben ahí. C2 a C6 son verificaciones después del despliegue, no pruebas automáticas.
- **Entradas hostiles:** la API local no tiene autenticación. Riesgo aceptado en el diseño 36
  §5, siempre que escuche sólo en loopback (C3).
- **Choques de frases del router:** no aplica en esta etapa.
- **Qué corre como root:** sólo la instalación del binario y de los archivos, por el catálogo de
  `nodo-desplegar` con hash. El servicio corre como `dcifu004`, unidad de usuario.
- **Alta en `nodo-desplegar`:** obligatoria para cada archivo (paso 5).
- **Rutas nuevas fuera de LUKS:** sólo el binario y la unidad. La credencial y la configuración
  quedan bajo `/opt/nodo/datos`.

## Fuera de alcance

- Todo lo del bot (intención, `/spotify`, búsqueda, claves de la Web API): **88b**.
- Agregar los receptores a `/estado` y a Cockpit, el volumen por voz y el ducking
  (ampliaciones previstas, diseño 36 §6).
- Cambiar el sink por defecto o tocar WirePlumber: el día de llegada del parlante lo decide
  la nota 25 §8.

## Pruebas sobre la forma real

- Valida las dos plantillas YAML contra el esquema de la **versión fijada** (descárgalo y
  guárdalo en `pi/spotify/fixtures/`).
- Una prueba `pi/spotify/test_plantillas.py` (stdlib, sin red) que compruebe:
  - puertos distintos y en loopback;
  - zeroconf apagado y `device_auth` en las dos;
  - `device_name` distinto en cada una;
  - que la unidad referencia `%i` y `ConditionPathExists`.

## Reglas

- No escribas en `/opt/nodo/datos` desde las pruebas.
- No vincules ninguna cuenta ni abras el enlace de `device_auth`.
- Al bajar el binario, verifica el hash. Si el release no publica checksums, calcúlalo tú y
  anota que el hash es tuyo y no del autor.

## Resultado

Escribe `encargos/88a-RESULTADO.md` con: versión, URL y hash; archivos creados con
destino, dueño y modo; salida de las pruebas; comandos de verificación de C2 a C6; y
pendientes.
