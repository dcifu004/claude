---
tipo: diseño
proyecto: ProyectoPi5
actualizado: 2026-10-25
estado: DISEÑO 25-10 (Claude (Diego)); **Prueba 0 PASADA el 25-10 21:45** con la cuenta de Diego (§5b); encargo **100** preparado sin lanzar (el 89 está reservado para la A de la nube).
---

# 39 — Spotify con el reproductor web oficial (Chromium + Widevine)

> Plan B de [[36 - Spotify por perfil (diseño)]]. Mantiene todo lo que la 36 decidió de
> identidades, frases y búsqueda. Sólo cambia **quién reproduce**: en vez de `go-librespot`,
> el reproductor web oficial de Spotify (`open.spotify.com`) dentro de un Chromium sin
> pantalla, uno por perfil.

## 1. Por qué

El 25-10 a las 21:13 los dos receptores de la 88 quedaron vinculados, pero **no suena nada**:
Spotify rechaza la llave de audio de todos los temas (`failed retrieving aes key with code 1`).
Pasó 38 de 38 veces con la cuenta de Diego y 64 de 64 con la de Camila. No es la Pi ni la
cuenta: Spotify dejó de entregar las llaves AES antiguas a los clientes libres (librespot
#1649, go-librespot #279/#317, con reportes de octubre de 2026) y todavía no hay arreglo.
Un cliente oficial usa Widevine, que es justo lo que Spotify exige ahora.

## 2. Opciones con cliente oficial

| Opción | Veredicto |
|---|---|
| **A. Reproductor web en Chromium + Widevine, en la Pi** | **Elegida.** El audio sale por PipeWire al G2000, igual que en la 36. |
| B. App de escritorio de Spotify para Linux | Descartada: sólo existe para x86-64. No hay versión arm64. |
| C. App de Spotify en el Roku o en la LG | Descartada como principal: suena por la tele y no por el G2000, sin AEC ni ducking. Sirve de último recurso. |
| D. Teléfono → G2000 por Bluetooth | Es lo que se usa **hoy**, a mano. El bot no lo controla. |
| E. Android (Waydroid) con la app oficial | Descartada: es pesada, frágil en la Pi 5 y necesitaría otra capa de control. |

## 3. Lo que ya está verificado (25-10)

- La Pi corre **Debian 13 con el repositorio de Raspberry Pi**, kernel `6.18.39+rpt-rpi-2712`
  con **páginas de 16 KB**. Tiene 7,9 GB de RAM y ~5,2 GB disponibles.
- **Chromium 154** está como candidato en apt (`1:154.0.8037.92-1~deb13u1+rpt1`) y no está
  instalado.
- **`libwidevinecdm0` 4.10.2662.3** está como candidato en apt (de 2023). Bajé el `.deb` sin
  instalarlo y revisé el `.so`: es aarch64 y **sus segmentos están alineados a 64 KB**
  (`Align 0x10000`), así que **carga con el kernel de 16 KB**. Lo que no sé es si Spotify
  acepta una versión tan vieja (Google revoca las CDM antiguas).
- Según el bug 1612995 de Mozilla (agosto–septiembre de 2026), **Google ya publica la CDM de
  Widevine para Linux aarch64**, y Chromium la baja sola por el actualizador de componentes
  (versión 4.10.3057 o posterior). Un desarrollador de Raspberry Pi la hizo andar en una
  **Pi 5 con Raspberry Pi OS de 64 bits**. Si la de apt queda vieja, esta es la vía.

## 4. Diseño

```text
«reproduce Oxytocin de Billie Eilish»   (Telegram; después, escucha.service)
        │
botv3@jaime / botv3@pilar ── intención `spotify` de la 88b, SIN CAMBIOS
        │ 1) /search con Client Credentials (app de Camila)          ← igual que la 36
        │ 2) pausa el receptor del otro perfil
        │ 3) POST /player/play {uri}  a 127.0.0.1:3678 (Jaime) / :3679 (Pilar)
        ▼
spotify-web@jaime / spotify-web@pilar   (unidad de usuario de dcifu004, una por perfil)
   controlador Python (sólo biblioteca estándar)
     ├─ arranca su Chromium como hijo con --remote-debugging-pipe (sin puerto abierto)
     ├─ expone el MISMO subconjunto de API que go-librespot: /status, /player/play,
     │  /player/pause, /player/resume, /player/volume
     └─ traduce: play {uri} → navega a open.spotify.com/track/<id> y aprieta ▶
        ▼
Chromium (perfil propio: /opt/nodo/datos/spotify-web/<perfil>/, sesión de esa cuenta)
   + Widevine → audio por pipewire-pulse → G2000 (copia mono al XVF3800 para el AEC)
```

**Decisiones:**

1. **El controlador imita la API de go-librespot.** El bot de la 88b no cambia ni una línea:
   sigue hablando con `:3678` y `:3679`. Las unidades `spotify@` se detienen y el puerto lo
   toma `spotify-web@`. El día que librespot se arregle, se vuelve atrás cambiando qué unidad
   está habilitada.
2. **Sin Web API por usuario.** El control va por el DevTools Protocol, **por pipe y no por
   puerto**: ningún otro proceso de la Pi puede tomar la sesión del navegador. Así se mantiene
   el descarte de la 36: no hay dos OAuth ni tokens que caduquen.
3. **Un navegador por perfil, cada uno con su carpeta de usuario.** La sesión de Diego y la de
   Camila nunca se cruzan. Ninguna clave pasa por la Pi: cada uno inicia sesión una vez
   (punto 5).
4. **Sin pantalla.** Primero se prueba `chromium --headless=new`. Si el modo headless no carga
   Widevine o no saca audio, se usa `cage` (compositor Wayland de kiosco) con
   `WLR_BACKENDS=headless`. La Prueba 0 decide cuál.
5. **Inicio de sesión, una vez por persona:** el controlador tiene un modo `vincular` que
   levanta ese Chromium con `--remote-debugging-port` **sólo en 127.0.0.1** y por 10 minutos.
   Desde el PC: `ssh -L 9222:127.0.0.1:9222 usuario@nodo.example`, luego `chrome://inspect`
   → *inspect*. El *screencast* deja ver la página y escribir. **Diego (o Camila) escribe
   su clave o el código que Spotify manda por correo; la IA no.** Después el modo se cierra
   solo. La cookie de sesión del reproductor dura del orden de un año.
6. **Selectores estables:** el controlador usa los `data-testid` de la página
   (`play-button`, `control-button-playpause`), no textos ni posiciones, y si no los
   encuentra responde `503` con el motivo. Así, cuando Spotify cambie la página, el bot dice
   «Spotify cambió su página web» en vez de quedar mudo.

## 5. Prueba 0 (la compuerta: si falla, no hay encargo)

Es manual, de unos 30 a 45 minutos, con Claude (Diego) y Diego.

1. **Instalar**, con una línea de `nodo-desplegar sugerir` (✅):
   `sudo apt install -y chromium cage libwidevinecdm0`. La CDM de apt queda de respaldo. Antes
   se revisa con `apt-get -s` qué arrastra la instalación.
2. Levantar un Chromium de prueba con una carpeta de usuario temporal y el modo `vincular`
   a mano. **Diego inicia sesión** en `open.spotify.com` con su cuenta.
3. Revisar en `chrome://components` la versión de Widevine que quedó (apt o la del
   componente de Google).
4. Reproducir «Oxytocin». **Pasa si se cumple todo esto:**
   - Suena en el G2000 (Diego lo confirma de oído).
   - `wpctl status` muestra el stream de Chromium.
   - En la app del teléfono aparece el dispositivo «Web Player (Chromium)» y se puede
     controlar desde ahí.
5. Medirlo en `headless=new` y, si hace falta, en `cage`: RAM y CPU en reposo y sonando, y
   tiempo de arranque.
6. Sólo si pasó, se repite con Camila para Pilar, en otra carpeta de usuario.

**Si falla:** quedan la opción D (Bluetooth) y esperar el arreglo de librespot. Los
receptores `spotify@` siguen vinculados y en pausa.

## 5b. Resultado de la Prueba 0 (25-10, 21:30–21:47)

**PASÓ.** «Oxytocin» sonó en el G2000 desde `open.spotify.com` con la cuenta de Diego, en
`chromium --headless=new`. Diego lo confirmó de oído y `wpctl` mostró el stream `Chromium` en
`EDIFIER G2000:playback_FL/FR`. No hizo falta `cage`.

- **Instalado:** `chromium 154.0.8037.92`, `cage 0.3.1` y `libwidevinecdm0 4.10.2662.3`. Con
  `--no-install-recommends` fueron 81 paquetes; sin esa opción habrían sido 163.
- **Widevine no se detecta solo.** El paquete de Raspberry Pi deja la CDM en el formato de
  Firefox (`/opt/WidevineCdm/gmp-widevinecdm/latest/`), y con eso Chromium responde
  `NotSupportedError`. **Arreglo, sin root:** copiar `manifest.json` y el `.so` a
  `<dir>/4.10.2662.3/_platform_specific/linux_arm64/libwidevinecdm.so`, y escribir
  `{"Path":"<dir>/4.10.2662.3"}` en `<user-data-dir>/WidevineCdm/latest-component-updated-widevine-cdm`.
  Con eso, `requestMediaKeySystemAccess("com.widevine.alpha")` responde OK y Spotify acepta la
  CDM de 2023.
- **Inicio de sesión:** por túnel SSH y `chrome://inspect` → *inspect* desde el PC, como en la
  decisión 5. Funcionó a la primera. La sesión quedó guardada en
  `~/spotify-web-prueba0/jaime` (218 MB).
- **El botón correcto:** la página de un tema tiene **63** `[data-testid=play-button]`, y el
  primero es «Play Liked Songs». El controlador tiene que elegir el de `aria-label="Play"`
  del encabezado del tema. **Si hay otro dispositivo Connect vinculado y activo** (los
  receptores `spotify@`), la página manda la música a ese («Playing on Casa · Jaime»). Por
  eso `spotify@` se detiene antes, y el controlador debe verificar que suene en su propio
  navegador.
- **Consumo:**

  | Estado | CPU | RAM |
  |---|---|---|
  | Sonando con el screencast de DevTools abierto | 125–200 % | — |
  | **Sonando, sin DevTools** | **~54 %** (renderer ~50 %, GPU ~2 %) | **PSS ~1,35 GB** |
  | **En pausa** | **< 1 %** | igual |

  La RAM es el costo real: dos perfiles abiertos ocuparían ~2,7 GB de los ~5,3 GB libres. Por
  eso **el cierre tras 30 min en pausa (§7) pasa de opcional a obligatorio**, y conviene que
  sólo haya un navegador abierto a la vez (al pedir música en un perfil, el otro se cierra en
  vez de sólo pausarse).
- **Queda para el encargo:** el arranque en frío hasta que suena (~10–15 s estimado, sin
  medir); la sesión de Camila (no se probó); verificar que el dispositivo «Web Player» aparece
  en el teléfono. Pasar la pestaña a segundo plano (`visibilityState=hidden`) no bajó la CPU
  mientras el screencast seguía abierto. Sin el screencast no se volvió a medir en primer
  plano.
- **Cómo quedó la Pi:** `prueba0-chromium-jaime` detenido, con la sesión guardada.
  `spotify@jaime` y `spotify@pilar` quedaron **detenidos pero habilitados**: vuelven a arrancar
  al reiniciar la Pi. Hay que deshabilitarlos al desplegar el 100.

## 6. Encargo (sólo si pasa la Prueba 0)

- **100 (antes «89a») — `spotify-web@.service` + controlador** (`pi/spotify-web/`): el controlador con API
  compatible, el modo `vincular`, la unidad con endurecimiento (sin `PrivateNetwork`: necesita
  red; `ReadWritePaths` sólo para su carpeta) y pruebas con un Chromium falso por pipe. Altas
  por `nodo-desplegar`. La 88b no se toca.
- **Cambio de receptor (antes «89b»; ahora es un paso de despliegue del 100, no una etapa):** `disable --now spotify@{jaime,pilar}` y
  `enable --now spotify-web@{jaime,pilar}`, más una línea en `/estado`. Se vuelve atrás con
  las dos órdenes al revés.
- Antes de lanzar, se pasa por `encargar` (Fase 0 y presupuesto). Va **después** de que
  terminen las colas 91b/92b/94 y de re-revisar la 88b (sus hashes cambiaron).

## 7. Riesgos y supuestos

- **Versión de Widevine:** la CDM de apt es de 2023 y Spotify podría rechazarla. Mitigación:
  la del componente de Google (§3). La Prueba 0 lo resuelve.
- **Recursos:** se estiman de 300 a 500 MB de RAM por navegador. Con dos navegadores entra
  holgado en los 5,2 GB libres, pero se mide en la Prueba 0. Si pesa mucho, el controlador
  cierra Chromium tras 30 minutos en pausa y lo abre al pedir música (~10 s de arranque).
- **Términos de Spotify:** se usa el reproductor oficial con su DRM, sin saltarse nada, y se
  controla la reproducción propia. Automatizar la página web es una zona gris de los
  términos: el riesgo realista es que cambie la página y se rompa, no que suspendan la
  cuenta. Nunca se usa para inflar reproducciones.
- **Fragilidad:** Spotify cambia su web sin avisar. El `503` con motivo (decisión 6) hace que
  se note de inmediato.
- **Seguridad:** la sesión de cada cuenta vive en una carpeta `0700` de `dcifu004`, igual que
  el `state.json` de go-librespot. El puerto de depuración existe sólo en el modo `vincular`,
  en loopback y por 10 minutos.
- **Supuesto:** el reproductor web acepta `navegar a /track/<id>` + ▶ y empieza a sonar sin un
  gesto del usuario. Chromium bloquea el autoplay, así que el controlador lo arranca con
  `--autoplay-policy=no-user-gesture-required`.

## Fuentes

- go-librespot [#279](https://github.com/devgianlu/go-librespot/issues/279) y librespot
  [#1649](https://github.com/librespot-org/librespot/issues/1649): el rechazo de las llaves.
- Mozilla [bug 1612995](https://bugzilla.mozilla.org/show_bug.cgi?id=1612995): Widevine
  aarch64 de Google, probado en una Pi 5.
- Spotify, [ayuda del reproductor web](https://support.spotify.com/mk/article/web-player-help/):
  requisito de Widevine.
