# Spotify con el reproductor web oficial (encargo 100, diseño 39)

`spotify-web@<perfil>` ocupa el puerto del receptor go-librespot de ese perfil (Jaime `127.0.0.1:3678`, Pilar
`127.0.0.1:3679`) y contesta el mismo API que usa el bot de la 88b:

| Ruta | Respuesta |
|---|---|
| `/status` | 204 sin sesión; con sesión, un JSON con la forma de go-librespot más `ultimo_error` |
| `/auth/code` | 204 |
| `/player/play` | 202, o 400 si la URI no es `spotify:track:<22>` o `spotify:artist:<22>` |
| `/player/pause` y `/player/resume` | 204 |
| `/player/volume` | 501 |

Por eso el bot no cambia ni una línea.

Reproduce con `open.spotify.com` dentro de un `chromium --headless=new`, hijo del controlador, que se maneja por el
DevTools Protocol **por pipe** (fds 3 y 4). No abre ningún puerto de depuración, salvo en `--vincular`. El audio sale
por `pipewire-pulse` al G2000.

- **Datos:** `/opt/nodo/datos/spotify/<perfil>/web/`, de `dcifu004`, con carpetas 0700 y archivos 0600. Los crea el
  propio controlador.
  - `chromium/`: la carpeta de usuario de Chromium, con la sesión de Spotify.
  - `cdm/<versión>/`: la CDM de Widevine copiada al formato de Chromium.
  - `estado.json`: la sesión y el último tema.
- **CDM:** al abrir el navegador, si falta o cambió (por SHA-256), se copia desde
  `/opt/WidevineCdm/gmp-widevinecdm/latest/` y se escribe el archivo de pista
  `chromium/WidevineCdm/latest-component-updated-widevine-cdm`. Todas las escrituras son atómicas.
- **Inactividad:** después de 15 min en pausa o detenido, se cierra Chromium, que ocupa unos 1,35 GB de PSS, y
  `/status` queda en `stopped: true`, con el último tema. `play` o `resume` lo vuelven a abrir; el arranque toma unos
  10 a 15 s, estimados y sin medir.
- **`ultimo_error`** en `/status` puede decir:
  - «Spotify cambió su página web (no encuentro ▶ del tema)»;
  - «Spotify está sonando en otro dispositivo»;
  - «Spotify no empezó a sonar en este navegador»;
  - «falta iniciar sesión en Spotify (spotify-web --vincular)»;
  - «no pude abrir el navegador: …».

  Lo va a leer la ampliación prevista de `/estado` y de los avisos.

## Altas en `nodo-desplegar`

Ninguna se ejecuta desde el encargo. Ambas llevan `--despues` vacío, porque `despues()` usa el systemctl del sistema
y esta es una unidad de usuario (trampa de la 88). Los dos destinos ya están en `PERMITIDOS`: no hay que tocar
`nodo-desplegar.py`.

```bash
nodo-desplegar alta spotify-web-script=6b28a5870a27669addf4b4780236aa6da82f2a1eaf0bf07fabaf70be5f859f9b 10-Proyectos/11-Pi5/pi/spotify-web/spotify-web.py /usr/local/bin/spotify-web --modo 0755 --dueno root:root --despues --motivo "Instalar controlador spotify-web (encargo 100)"
nodo-desplegar alta spotify-web-unidad=ec3295e260b5aa8cc42edf440aceb4800e32eed6ad408d6f0bf212bc62f42db2 10-Proyectos/11-Pi5/pi/spotify-web/spotify-web@.service /etc/systemd/user/spotify-web@.service --modo 0644 --dueno root:root --despues --motivo "Instalar unidad de usuario spotify-web@ (encargo 100)"
```

`chromium_falso.py`, `test_spotify_web.py` y `fixtures/` no se instalan.

## Migrar la sesión de la Prueba 0 (Jaime)

Con el servicio detenido, como `dcifu004`:

```bash
systemctl --user stop spotify-web@jaime; install -d -m 0700 /opt/nodo/datos/spotify/jaime/web/chromium && cp -a ~/spotify-web-prueba0/jaime/. /opt/nodo/datos/spotify/jaime/web/chromium/
```

Sin `estado.json`, el controlador da por iniciada la sesión si existe `chromium/Default`, que es lo que deja esta
copia. Así Jaime no tiene que volver a iniciar sesión. Si la cookie ya no sirve, el primer `play` lo detecta (aparece
`login-button`), `/status` pasa a 204 y el bot dice «Falta vincular tu Spotify».

## Cambio de receptor (lo corre `dcifu004`, sin root)

Después de las dos altas:

```bash
systemctl --user disable --now spotify@jaime spotify@pilar && systemctl --user daemon-reload && systemctl --user enable --now spotify-web@jaime spotify-web@pilar
```

**Vuelta atrás**, en el orden inverso (go-librespot queda instalado y deshabilitado):

```bash
systemctl --user disable --now spotify-web@jaime spotify-web@pilar && systemctl --user daemon-reload && systemctl --user enable --now spotify@jaime spotify@pilar
```

## Vincular un perfil (una vez por persona)

Con el servicio del perfil detenido. Si está activo, `--vincular` se niega, porque ve ocupado su puerto HTTP:

```bash
systemctl --user stop spotify-web@pilar; /usr/local/bin/spotify-web --perfil pilar --vincular; systemctl --user start spotify-web@pilar
```

1. Abre Chromium con `--remote-debugging-port=9222` **sólo en 127.0.0.1**, en el login de Spotify, e imprime la línea
   del túnel: `ssh -L 9222:127.0.0.1:9222 dcifu004@nodo.example`.
2. Desde el PC, con el túnel abierto: `chrome://inspect` → *Configure…* `127.0.0.1:9222` → *inspect*.
3. **La persona escribe su clave o el código del correo. La IA no.**
4. El controlador espera hasta 10 min a que la página vuelva a `open.spotify.com`. Después cierra el navegador, guarda
   la sesión en `estado.json` y sale con 0. Si no quedó sesión, sale con 1.

## Pruebas

```bash
python3 pi/spotify-web/test_spotify_web.py
```

Usan un Chromium falso (`chromium_falso.py`) que habla CDP por los fds 3 y 4 y contesta con el DOM real de
`fixtures/dom-tema-2026-10-25.json`. No escriben en `/opt/nodo/datos`, no abren puertos fuera de 127.0.0.1 y no lanzan
un Chromium real. C1 importa el `_spotify_suena` real de `botv3/botv3.py` (cargar `botv3.py` necesita `requests`).
