# Encargo 100: RESULTADO (controlador `spotify-web@`)

Hecho por Claude (Diego) en la nube el 26-10-2026, en la rama `claude/encargo-100-spotify-web`, creada desde `base-100`.
El primer commit es el PLAN.

El encabezado del encargo pide el RESULTADO en `encargos-nube/` y su última sección dice `encargos/100-RESULTADO.md`.
Seguí el encabezado: «no en `encargos/`», y además la regla «no escribir fuera de `pi/spotify-web/`».

## Lo hecho

Todo lo nuevo está en `pi/spotify-web/`. `botv3/botv3.py`, `botv3/spotify.py` y `pi/nodo-desplegar.py` no se tocaron.

- **`spotify-web.py`**: sólo biblioteca estándar; se instala en `/usr/local/bin/spotify-web`.
  - Recibe `--perfil {jaime,pilar}` (los puertos 3678 y 3679 salen de una tabla fija) y `--vincular`.
  - **HTTP** en `127.0.0.1:<puerto>` (`ThreadingHTTPServer`):

    | Ruta | Respuesta |
    |---|---|
    | `/status` | 204 sin sesión; con sesión, un JSON con **todas** las claves de `status_sonando` del fixture de go-librespot (y las de `track`), más `ultimo_error`. Se responde siempre **desde la caché**: nunca espera a Chromium ni lo arranca. |
    | `/auth/code` | 204 |
    | `/player/play` | **202** de inmediato; el trabajo sigue en un hilo. 400 si la URI no es exactamente `spotify:(track\|artist):[0-9A-Za-z]{22}`, si el JSON no es válido o si el cuerpo pasa de 4 KB. |
    | `/player/pause` y `/player/resume` | 204 |
    | `/player/volume` | 501 |
    | otras rutas | 404 |

    Con el navegador cerrado, `pause` no hace nada y `resume` lo abre y vuelve a poner el último tema.
  - **Chromium** se lanza como hijo con:

    ```
    --headless=new --remote-debugging-pipe --user-data-dir=… --autoplay-policy=no-user-gesture-required --no-first-run --window-size=1280,800
    ```

    Los fds 3 y 4 van por `pass_fds`. En el hijo, `preexec_fn` los acomoda con `F_DUPFD` (≥ 10) y después `dup2`, así
    no se pisan entre sí. Los mensajes CDP van separados por `\0`. Nunca se usa `--remote-debugging-port`, salvo en
    `--vincular`.
  - **JavaScript fijo.** Sólo lee el DOM (`leer`, `botones`) y aprieta por un índice entero elegido en Python. La URI
    nunca entra en el JS: se navega con `Page.navigate` a `https://open.spotify.com/{track|artist}/<id validado>`.
  - **El botón** (`elegir_boton`) es el `[data-testid=play-button]` con `aria-label` exactamente «Play», dentro del
    `action-bar` o del `entity-header` del tema. Si no aparece en 15 s, `ultimo_error` dice «Spotify cambió su página
    web (no encuentro ▶ del tema)».
  - **Verificación**, como máximo 15 s:
    - la barra tiene que decir «Now playing: <tema> by <artistas>» y `control-button-playpause` tiene que tener
      `aria-label="Pause"`;
    - si la barra dice «Playing on …», se pausa y queda `ultimo_error = "Spotify está sonando en otro dispositivo"`;
    - si no suena en el plazo, `ultimo_error` dice «Spotify no empezó a sonar en este navegador».
  - **Sondeo:** cada 2 s, por `Runtime.evaluate`, se leen el tema, los artistas, la posición, la duración y el
    play/pausa. Si aparece `login-button` y no `user-widget-link`, la sesión queda marcada como perdida y `/status` da
    204.
  - **Cierre por inactividad:** a los 15 min en pausa o detenido se manda SIGTERM, y SIGKILL si a los 10 s sigue vivo.
    `/status` queda en `stopped: true`, con el último tema.
  - **CDM** (`preparar_cdm`):
    - lee la versión del `manifest.json` de `/opt/WidevineCdm/…` y la valida con una expresión regular, así que no
      arma rutas con `..`;
    - compara SHA-256 y copia a `cdm/<versión>/manifest.json` y a
      `cdm/<versión>/_platform_specific/linux_arm64/libwidevinecdm.so`;
    - escribe `{"Path": …}` en `chromium/WidevineCdm/latest-component-updated-widevine-cdm`;
    - todo de forma atómica (`.tmp` + `os.replace`), con carpetas 0700 y archivos 0600;
    - una segunda corrida no reescribe nada.
  - **`estado.json`**, atómico y 0600, guarda la sesión y el último tema.
  - **`--vincular`:**
    - se niega (rc 2) si el puerto HTTP del perfil está ocupado;
    - si no, levanta Chromium con `--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222` en el login de
      Spotify e imprime la línea del túnel;
    - espera hasta 10 min a que la página vuelva a `open.spotify.com` (lo mira en `http://127.0.0.1:9222/json`);
    - cierra y sale 0 si quedó sesión, o 1 si no.
- **`spotify-web@.service`**: la unidad de usuario tal como la pide el encargo:
  - `Conflicts=spotify@%i.service`;
  - `After=` y `Wants=pipewire-pulse.service`;
  - `ConditionPathIsDirectory=/opt/nodo/datos/spotify/%i`;
  - `Restart=on-failure`, `RestartSec=10`, `MemoryMax=1800M`, `NoNewPrivileges=yes`, `WantedBy=default.target`;
  - sin `PrivateNetwork`, `RestrictNamespaces` ni `ProtectHome=yes`.
- **`chromium_falso.py`**: el Chromium falso, que no se instala. Habla CDP por los fds 3 y 4 y contesta con lo que el JS
  leería de `fixtures/dom-tema-2026-10-25.json`:
  - los 65 botones, con «Play Liked Songs» primero y el ▶ del tema en `play_button_tema`;
  - la barra «Now playing: Oxytocin by Billie Eilish»;
  - `aria-label="Pause"` y `user_widget`.

  Un escenario JSON fija la demora de arranque, la sesión, si falta el botón del tema y si suena en otro dispositivo,
  y anota todo lo recibido.
- **`test_spotify_web.py`**: 20 pruebas, de C1 a C8.
- **`LEEME.md`**: las altas, la migración de la sesión de la Prueba 0, el cambio de receptor, la vuelta atrás y
  `--vincular`.

## Decisiones

- **Sesión desconocida.** Al arrancar el servicio, antes de abrir Chromium, `estado.json` puede no decir nada; pasa
  justo después de migrar la sesión de la Prueba 0. En ese caso, la sesión se da por iniciada si existe
  `chromium/Default`. Si no, `/status` daría 204 y el bot contestaría «Falta vincular» **antes de intentar el play**,
  porque mira `/status` primero. Si la cookie ya no sirve, el primer `play` lo detecta y `/status` pasa a 204.
- **`spotify:artist:<id>`** también se acepta, porque la 88b manda la URI del artista cuando la búsqueda es por
  artista. Se navega a `/artist/<id>` con el mismo selector. Sólo hay fixture de la página de un tema: ver riesgos.
- **La lectura de la página se hace en Python** (`elegir_boton`, `parsear_ahora`, `otro_dispositivo`, `a_ms`), con
  funciones puras probadas sobre el DOM real. El JS sólo recoge atributos y textos.
- **Una orden del navegador a la vez** (`orden`). El sondeo se salta un ciclo si hay una orden en curso.
  `cerrar_navegador` también cierra un Chromium que todavía arranca (`arrancando`), para que no quede huérfano.
- **Reserva de los fds 3 y 4.** Con `pass_fds=(3, 4)`, el hijo marca esos fds como heredables **antes** de
  `preexec_fn`. Si en el padre no hay nada abierto en esos números, el `exec` falla con EBADF. Por eso, si están
  libres, se ocupan con `/dev/null` (no heredable). En el servicio real casi siempre están ocupados por el socket
  HTTP.
- **Sin root en ejecución.** Lo único root:root son las dos altas.

## Pruebas (salida real)

```
$ python3 pi/spotify-web/test_spotify_web.py -v
test_sesion_desconocida_sale_del_perfil_de_chromium ... ok
test_sin_sesion_204_y_auth_code_204 ... ok
test_sonando_con_la_forma_de_go_librespot_y_spotify_suena_real ... ok        (C1, importa botv3._spotify_suena real)
test_volumen_501_y_rutas_desconocidas_404 ... ok
test_responde_en_menos_de_500_ms_con_un_chromium_que_tarda_20_s ... ok       (C2)
    C2 (Chromium falso con 20 s de arranque): status 2 ms, play 2 ms, status-2 2 ms, pause 2 ms, resume 2 ms, status-3 1 ms
test_de_punta_a_punta_aprieta_el_del_tema ... ok                              (C3)
test_elige_el_play_exacto_de_la_cabecera_y_no_play_liked_songs ... ok        (C3)
test_sin_el_boton_del_tema_no_aprieta_nada ... ok                             (C3)
test_playing_on_otro_pausa_y_lo_dice ... ok                                   (C4)
test_arma_la_estructura_de_chromium_y_es_idempotente ... ok                   (C5)
test_version_hostil_no_arma_rutas ... ok                                      (C5)
test_cierra_tras_15_min_en_pausa_y_resume_lo_reabre ... ok                    (C6, reloj inyectado)
test_pause_con_el_navegador_cerrado_no_lo_abre ... ok
test_la_uri_nunca_entra_al_javascript ... ok                                  (C7)
test_uris_y_cuerpos_hostiles_dan_400_sin_navegar ... ok                       (C7)
test_datos_inyectados_loopback_y_chromium_falso_por_pipe ... ok              (C8)
test_hay_sesion_cuando_la_pagina_volvio_a_open_spotify ... ok
test_vincular_se_niega_si_el_servicio_esta_activo ... ok
test_la_unidad ... ok
test_parsear_ahora_y_tiempos ... ok
Ran 20 tests in 2.102s
OK
```

(Los nombres van sin el sufijo `(__main__.Clase…)` y la anotación entre paréntesis es mía.)

- La corrí tres veces seguidas y salió OK las tres.
- Después no quedó ningún proceso `chromium_falso` vivo, ni siquiera el de C2, que arranca en 20 s.
- No se creó `/opt/nodo` en el contenedor.
- Las líneas de `stderr` que se ven entre las pruebas son los avisos esperados del controlador («Spotify cambió su
  página web…», «15 min sin sonar…») y uno de `botv3.py` al cargarse («cuentas.web: 'codex' no puede usarse…»).

```
$ python3 botv3/test_spotify.py             (con rapidfuzz: aquí no está instalado y lo tomé del scratchpad)
Ran 8 tests in 1.071s
OK
```

Sin `rapidfuzz`, en esta copia `botv3/test_spotify.py` no se importa, ni antes ni después: `ModuleNotFoundError:
No module named 'rapidfuzz'`. `test_spotify_web.py` no lo necesita, porque `botv3.py` carga igual sin él.

```
$ python3 pi/test_nodo_desplegar.py
Ran 93 tests in 12.960s
FAILED (failures=2, errors=2)
```

Son las mismas 4 que antes del cambio (lista idéntica, en `100-nodo-desplegar-fallas-antes.txt`). Son del entorno de
esta copia: `DuenosSpotifyTests` ×3 y `LadoIATests.test_la_documentacion_del_nodo_describe_enviar`. No toqué
`nodo-desplegar.py`.

## SHA-256 y altas

```
6b28a5870a27669addf4b4780236aa6da82f2a1eaf0bf07fabaf70be5f859f9b  pi/spotify-web/spotify-web.py
ec3295e260b5aa8cc42edf440aceb4800e32eed6ad408d6f0bf212bc62f42db2  pi/spotify-web/spotify-web@.service
```

```bash
nodo-desplegar alta spotify-web-script=6b28a5870a27669addf4b4780236aa6da82f2a1eaf0bf07fabaf70be5f859f9b 10-Proyectos/11-Pi5/pi/spotify-web/spotify-web.py /usr/local/bin/spotify-web --modo 0755 --dueno root:root --despues --motivo "Instalar controlador spotify-web (encargo 100)"
nodo-desplegar alta spotify-web-unidad=ec3295e260b5aa8cc42edf440aceb4800e32eed6ad408d6f0bf212bc62f42db2 10-Proyectos/11-Pi5/pi/spotify-web/spotify-web@.service /etc/systemd/user/spotify-web@.service --modo 0644 --dueno root:root --despues --motivo "Instalar unidad de usuario spotify-web@ (encargo 100)"
```

Los dos destinos ya están en `PERMITIDOS`. `--despues` va vacío por la trampa de la 88: `despues()` usa el systemctl
del sistema.

## Cambio de receptor y vuelta atrás

Lo corre `dcifu004`, sin root, después de las altas y de migrar la sesión.

```bash
# migrar la sesión de la Prueba 0 (Jaime), con el servicio detenido
systemctl --user stop spotify-web@jaime; install -d -m 0700 /opt/nodo/datos/spotify/jaime/web/chromium && cp -a ~/spotify-web-prueba0/jaime/. /opt/nodo/datos/spotify/jaime/web/chromium/

# cambio
systemctl --user disable --now spotify@jaime spotify@pilar && systemctl --user daemon-reload && systemctl --user enable --now spotify-web@jaime spotify-web@pilar

# vuelta atrás
systemctl --user disable --now spotify-web@jaime spotify-web@pilar && systemctl --user daemon-reload && systemctl --user enable --now spotify@jaime spotify@pilar
```

Pilar se vincula con el servicio detenido:
`systemctl --user stop spotify-web@pilar; /usr/local/bin/spotify-web --perfil pilar --vincular; systemctl --user start spotify-web@pilar`.
Camila escribe su clave por el túnel; la IA no. El detalle está en `pi/spotify-web/LEEME.md`.

## Pendientes y riesgos

- **Nada de esto corrió con un Chromium real.**
  - Los selectores salen del DOM real del fixture, pero falta probar en la Pi el arranque en frío, el clic y la
    verificación con `chromium --headless=new`.
  - Falta medir el tiempo hasta que suena.
  - El fixture no trae `playback-position` ni `playback-duration`, porque la barra viene recortada a 1.500
    caracteres. Por eso `position` y `duration` dan 0 hasta confirmar esos `data-testid` en la página real.
- **La página de artista** (`spotify:artist:`) no tiene fixture. Supuse que su ▶ también es `aria-label="Play"` en el
  `action-bar`. Si no, ese caso devuelve «Spotify cambió su página web» y el bot igual responde. Conviene capturar ese
  DOM en la Pi.
- **El modo `--vincular` detecta la sesión por la URL** (la página vuelve a `open.spotify.com`), no por el DOM. El
  puerto 9222 sólo da HTTP y no hay `websockets` en la biblioteca estándar. Si Spotify cambia el flujo de login, puede
  hacer falta otro criterio.
- **Un solo navegador a la vez entre perfiles** (sugerido en §5b del diseño): no está. Cada perfil cierra el suyo tras
  15 min. Con los dos abiertos son ~2,7 GB. El bot ya pausa el otro receptor antes del play, pero no lo cierra. Queda
  como posible ampliación.
- La 88b tiene que volver a revisarse (sus hashes cambiaron, según los antecedentes), antes o junto con este cambio de
  receptor.
- El hallazgo 2 de la 88r (`POST /token` sin autenticación en el receptor go-librespot) queda sin efecto mientras
  `spotify@` esté deshabilitado. Si se vuelve atrás, vuelve a aplicar.
- `/estado`, Cockpit y el aviso 🚩 que lee `ultimo_error` quedan fuera de alcance, como dice el encargo.
