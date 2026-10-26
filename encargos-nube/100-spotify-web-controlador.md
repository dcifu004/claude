> **Nube (Claude (Diego)), rama base `base-100`.** En este repositorio el diseño 39 está en
> `docs/39 - Spotify con el reproductor web oficial (diseño).md` y el 36 en `docs/36 - …`. No hay
> Pi, ni Chromium, ni `/opt`: todo se prueba con el Chromium falso y los fixtures. El resultado va en
> `encargos-nube/100-RESULTADO.md` (no en `encargos/`), y el plan, primero, en
> `encargos-nube/100-PLAN.md`. `botv3/botv3.py` y `botv3/spotify.py` son de **sólo lectura** en
> este encargo. La revisión cruzada la hace Codex en la Pi.

# Encargo 100: controlador `spotify-web@` (reproductor web oficial en lugar de go-librespot) (Claude (Diego), 25-10-2026)

## Leer primero

- `10-Proyectos/11-Pi5/39 - Spotify con el reproductor web oficial (diseño).md`: **§4 y §5b
  completos**. §5b trae lo medido en la Pi y las trampas que ya aparecieron.
- `botv3/spotify.py`, funciones `_peticion`, `estado`, `codigo`, `reproducir`, `pausar`,
  `reanudar` y `volumen`: es el contrato que hay que cumplir. Fíjate en `TIMEOUT = 3`.
- `botv3/botv3.py`, de `_spotify_suena` a `/spotify` (desde la línea ~6743): qué campos de
  `/status` lee el bot.
- `botv3/fixtures/spotify-receptor-v0.10.5.json`: la forma de `/status` en go-librespot.
- `pi/spotify-web/fixtures/dom-tema-2026-10-25.json`: **DOM real** de
  `open.spotify.com/track/<id>`, capturado en la Pi con la cuenta del usuario (con los
  nombres de su biblioteca reemplazados).
- `pi/spotify/spotify@.service` y `pi/nodo-desplegar.py` (`PERMITIDOS`,
  `RUTAS_DUEÑO_USUARIO`, `validar_dueno`).
- `encargos/trampas.md`: sólo las secciones de systemd y `nodo-desplegar`.

**No hace falta leer:** el resto de `botv3.py`, las etapas 88a/88c (ya desplegadas), Cockpit
ni el router de frases.

## Antecedentes

- **Diseño 36 + encargo 88** (88a/88c desplegados el 25-10 a las 21:07; la 88b está revisada
  como DESPLEGABLE, sin desplegar, y sus hashes cambiaron después): dos receptores
  go-librespot en `127.0.0.1:3678` (Jaime) y `:3679` (Pilar). **No suenan:** Spotify rechaza
  la llave AES de todos los temas en las dos cuentas (librespot #1649, go-librespot
  #279/#317, sin arreglo).
- **Diseño 39, Prueba 0 PASADA (25-10 21:45):** `chromium --headless=new` +
  `libwidevinecdm0` reprodujo «Oxytocin» en el G2000 con la cuenta del usuario. El paquete
  de Raspberry Pi **no** registra la CDM en Chromium: hay que copiarla al formato de Chromium
  y apuntar con un archivo de pista (§5b). Medido: ~54 % de CPU sonando, < 1 % en pausa y
  ~1,35 GB de PSS por navegador.
- No hay encargos descartados sobre esto. Se buscó «chromium», «widevine», «headless» y
  «open.spotify» en `encargos/` y en la memoria.

## Contexto

El bot de la 88b habla HTTP con `:3678` y `:3679`, siguiendo el API de go-librespot. Este
encargo escribe un **controlador** que ocupa esos mismos puertos y cumple ese mismo
contrato, pero reproduce con el reproductor web oficial dentro de un Chromium sin pantalla.
Así la 88b no cambia ni una línea. Se instala **una instancia por perfil**
(`spotify-web@jaime`, `spotify-web@pilar`).

## Qué hacer

1. **`pi/spotify-web/spotify-web.py`** (sólo biblioteca estándar; se instala en
   `/usr/local/bin/spotify-web`):
   - Argumentos: `--perfil {jaime,pilar}` (el puerto sale de una tabla fija:
     jaime → 3678, pilar → 3679) y `--vincular`.
   - **Datos:** `/opt/nodo/datos/spotify/<perfil>/web/`, con modo 0700, creada por el propio
     controlador. Adentro van `chromium/` (`--user-data-dir`), `cdm/` y `estado.json`. Esa
     carpeta padre ya existe y es de `dcifu004` (88c).
   - **CDM:** al arrancar, si falta o cambió (se compara SHA-256 con el de
     `/opt/WidevineCdm/gmp-widevinecdm/latest/libwidevinecdm.so`), se copia al formato de
     Chromium: `cdm/<versión>/manifest.json` y
     `cdm/<versión>/_platform_specific/linux_arm64/libwidevinecdm.so`. Después se escribe
     `{"Path": ".../cdm/<versión>"}` en `chromium/WidevineCdm/latest-component-updated-widevine-cdm`.
     La versión sale del `manifest.json` de `/opt/WidevineCdm`. Las escrituras son atómicas
     (`.tmp` + `os.replace`).
   - **Chromium:** se lanza como hijo con `chromium --headless=new --remote-debugging-pipe
     --user-data-dir=... --autoplay-policy=no-user-gesture-required --no-first-run
     --window-size=1280,800`. Los fds 3 y 4 van por `pass_fds` y los mensajes CDP se
     delimitan con `\0`. **Nunca** se usa `--remote-debugging-port`, salvo en `--vincular`.
   - **HTTP** en `127.0.0.1:<puerto>` (`ThreadingHTTPServer`):
     - `GET /status` → **204** si no hay sesión iniciada (el bot lo entiende como «falta
       vincular»). Si hay sesión, responde un JSON con la forma del fixture de go-librespot:
       como mínimo `stopped`, `paused`, `buffering`, `device_name` («Casa · Jaime» /
       «Casa · Pilar»), `track{uri,name,artist_names,position,duration}` (o `null`), más
       un campo extra `ultimo_error` (texto o `null`). **Siempre responde en < 500 ms
       desde caché**: nunca espera a Chromium ni lo arranca.
     - `GET /auth/code` → 204 (no hay código: la vinculación es manual, decisión 5).
     - `POST /player/play {"uri":"spotify:track:<22 base62>"}` → valida la URI (sólo
       `track`, y `artist` si la 88b la manda; mirar `buscar`), responde **202 en < 500 ms** y
       sigue en un hilo: arranca Chromium si está cerrado, navega a
       `https://open.spotify.com/track/<id>` y aprieta el botón del tema. Las URI inválidas
       dan 400.
     - `POST /player/pause` y `/player/resume` → 204. Si el navegador está cerrado, `pause`
       no hace nada y `resume` lo abre y vuelve a poner el último tema.
     - `POST /player/volume` → 501 (está reservado en la 88b).
   - **El botón correcto** (§5b): la página trae ~65 `[data-testid=play-button]`, y el
     primero es «Play Liked Songs». Se usa el que tiene `aria-label` exactamente igual a
     `"Play"`, dentro de la cabecera del tema. Si no aparece en 15 s:
     `ultimo_error = "Spotify cambió su página web (no encuentro ▶ del tema)"`.
   - **Verificación de que suena aquí:** a los ≤ 15 s, `now-playing-bar` debe mostrar el
     tema y `control-button-playpause` tiene que tener `aria-label="Pause"`. Si la barra dice
     «Playing on …» (otro dispositivo Connect), se pausa y se guarda
     `ultimo_error = "Spotify está sonando en otro dispositivo"`.
   - **Sondeo de estado:** mientras el navegador está abierto, cada 2 s se lee por CDP
     (`Runtime.evaluate`) el tema, la posición, la duración y el play/pausa, y se actualiza la
     caché. Si aparece `login-button` y no `user-widget-link`, se marca «sin sesión» y
     `/status` da 204.
   - **Cierre por inactividad:** si pasan **15 min** en pausa o detenido, se cierra Chromium
     (primero SIGTERM; si a los 10 s sigue vivo, SIGKILL) y `/status` pasa a
     `stopped: true`, con el último tema.
   - **`--vincular`:** se niega si el servicio del mismo perfil está activo (lo detecta
     porque el puerto HTTP está ocupado). Levanta Chromium con
     `--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222` en
     `accounts.spotify.com/login?continue=https%3A%2F%2Fopen.spotify.com%2F`. Imprime la línea
     del túnel (`ssh -L 9222:127.0.0.1:9222 …`) y espera hasta que haya sesión (como
     máximo 10 min). Después cierra y sale 0 si hay sesión, o 1 si no.
2. **`pi/spotify-web/spotify-web@.service`**, una unidad de usuario en
   `/etc/systemd/user/`:
   `Conflicts=spotify@%i.service`, `After/Wants=pipewire-pulse.service`,
   `ConditionPathIsDirectory=/opt/nodo/datos/spotify/%i`,
   `ExecStart=/usr/local/bin/spotify-web --perfil %i`, `Restart=on-failure`,
   `RestartSec=10`, `MemoryMax=1800M`, `NoNewPrivileges=yes` y
   `WantedBy=default.target`. **No** uses `PrivateNetwork`, `RestrictNamespaces` ni
   `ProtectHome=yes`: el sandbox de Chromium necesita espacios de nombres de usuario.
3. **`pi/spotify-web/test_spotify_web.py`**: pruebas con un **Chromium falso**, un script
   que habla CDP por los fds 3/4 y responde con datos sacados del fixture DOM real.
4. **`pi/spotify-web/LEEME.md`**: las altas de `nodo-desplegar` (script y unidad, root:root)
   y la **secuencia de cambio de receptor**, que corre `dcifu004` sin root:
   `systemctl --user disable --now spotify@jaime spotify@pilar && systemctl --user
   daemon-reload && systemctl --user enable --now spotify-web@jaime spotify-web@pilar`.
   También la vuelta atrás (el orden inverso), y cómo vincular cada perfil con `--vincular`.
   **Migrar la sesión de la Prueba 0:** con el servicio detenido,
   `cp -a ~/spotify-web-prueba0/jaime/. /opt/nodo/datos/spotify/jaime/web/chromium/`. Así
   Jaime no tiene que volver a iniciar sesión.

## Criterios de aceptación

- **C1** `/status` sin sesión → 204. Con sesión y el tema sonando (fixture DOM) →
  200, con `stopped=false`, `paused=false`, `track.name="Oxytocin"` y
  `track.artist_names=["Billie Eilish"]`. **`botv3._spotify_suena` aplicado a esa respuesta
  da `True`**: la prueba importa la función real, no una copia.
- **C2** `/status`, `/player/play` y `/player/pause` responden en **< 500 ms** aunque el
  Chromium falso tarde 20 s en arrancar. Se mide en la prueba.
- **C3** Elección del botón: con el fixture DOM real (65 botones, el primero «Play Liked
  Songs»), el selector elige el de `aria-label="Play"`. Si sólo están «Play Liked Songs» y
  otros, no aprieta ninguno y guarda el `ultimo_error` de «Spotify cambió su página web».
- **C4** «Playing on <dispositivo>» en la barra → pausa + `ultimo_error` de otro dispositivo.
- **C5** CDM: con un `/opt/WidevineCdm` falso (carpeta temporal), arma la estructura de
  Chromium con hashes iguales y un archivo de pista JSON válido. Es idempotente: una segunda
  corrida no reescribe nada. Si cambia el `.so`, recopia.
- **C6** El cierre por inactividad, con el reloj inyectado (sin dormir 15 min), cierra el hijo
  y deja `stopped=true` con el último tema. `resume` lo vuelve a abrir.
- **C7** URI hostil (`spotify:track:../../x`, de 23 caracteres, `javascript:`, JSON
  inválido o un cuerpo de más de 4 KB) → 400, sin navegar.
- **C8** Ninguna prueba escribe en `/opt/nodo/datos`, abre puertos fuera de 127.0.0.1 ni
  lanza un Chromium real. La ruta de datos se inyecta.

## Invariantes

- **Archivos compartidos:** `estado.json` y el archivo de pista de la CDM se escriben de forma
  atómica. Un solo proceso por perfil, garantizado por el puerto HTTP y por `Conflicts=`.
- **Dueño, modo y usuario:** todo lo que crea el controlador queda como `dcifu004`, 0700/0600,
  bajo `/opt/nodo/datos/spotify/<perfil>/web/`. Nada nuevo es de `dcifu004` fuera de ahí.
- **Pruebas:** sin escribir en `/opt/nodo/datos` y sin avisos reales (C8).
- **Entradas hostiles:** C7. Además, la URI nunca se interpola en JavaScript: se navega
  con `Page.navigate` y una URL armada a partir del id ya validado.
- **Choques de frases del router:** no aplica, porque el bot no cambia.
- **Qué corre como root:** nada en ejecución. Sólo las altas (script en `/usr/local/bin`, unidad
  en `/etc/systemd/user`), por `nodo-desplegar alta`, ambas root:root 0755/0644. Las dos
  rutas ya están en `PERMITIDOS`, así que **no hay que tocar `nodo-desplegar.py`**.
- **Alta en `nodo-desplegar`:** dos entradas nuevas (`spotify-web-script` y
  `spotify-web-unidad`), con `--despues` vacío (trampa de la 88: `despues()` usa el
  systemctl del sistema).

## Fuera de alcance

- Cambiar la 88b o `botv3.py`. Si el contrato no alcanza, se anota en el RESULTADO; no se
  toca el bot.
- Volumen (501), «siguiente», «qué suena», cola de reproducción y playlists.
- `/estado`, Cockpit y avisos 🚩 cuando aparece «Spotify cambió su página web». Es una
  **ampliación prevista** que leerá el campo `ultimo_error` de `/status`, que esta etapa ya
  deja fijo.
- Ejecutar el cambio de receptor o vincular a Camila: eso es despliegue, lo hace Claude (Diego)
  con el usuario después de la revisión.
- Desinstalar go-librespot: queda instalado y deshabilitado, para volver atrás.

## Pruebas sobre la forma real

- El DOM sale de `pi/spotify-web/fixtures/dom-tema-2026-10-25.json` y no se inventa.
- La forma de `/status` sale de `botv3/fixtures/spotify-receptor-v0.10.5.json`.
- `python3 pi/spotify-web/test_spotify_web.py`, `python3 botv3/test_spotify.py` y
  `python3 pi/test_nodo_desplegar.py`.

## Reglas

- Sólo biblioteca estándar (la Pi no tiene `websockets` ni Playwright).
- Sin red en las pruebas: en el sandbox de Codex no hay DNS.
- No escribir fuera de `pi/spotify-web/` ni crear archivos en otras carpetas del vault.
- Las etiquetas de cuenta van como «Claude (Diego)», «Claude (Cami)» y «Codex».

## Resultado

Escribe `encargos/100-RESULTADO.md` con:
- los cambios y las decisiones;
- la salida de las tres suites;
- los SHA-256 completos del script y de la unidad, con las líneas `nodo-desplegar alta`
  listas para copiar;
- la secuencia de cambio de receptor y su vuelta atrás;
- los pendientes.
