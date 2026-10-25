# Encargo 88b: «reproduce Oxytocin de Billie Eilish en Spotify» en Jaime y Pilar (Claude (Diego), 25-10-2026)

Segunda etapa. **Depende de la 88a**: usa sus receptores `spotify@jaime` (`127.0.0.1:3678`) y
`spotify@pilar` (`127.0.0.1:3679`). Lee `88a-RESULTADO.md` antes de empezar. Si la 88a cambió
puertos o nombres, manda lo que dice ese resultado.

## Leer primero

- `36 - Spotify por perfil (diseño).md` §2 y §3: **arquitectura y frases aprobadas**.
- `88a-RESULTADO.md`: versión de go-librespot, la forma real de `/status` y de `/auth/code`.
- `botv3/botv3.py`:
  - el encadenado de intenciones locales en texto (~8083–8104) y en voz (~8009–8030);
  - `sin_vocativo` (~1221) y `atender_hora_o_clima`, molde de una intención con `en_voz`;
  - `atender_frase_google` (~3904), molde de una intención que devuelve `bool`;
  - cómo se carga un módulo opcional (`clima_imagen`, ~96).
- `botv3/perfiles/jaime.toml` y `pilar.toml`.
- `pi/cargar-clave.py`: la lista `VARIABLES`.
- `encargos/trampas.md`, sección «botv3».

## No hace falta leer

El router de n8n, Cockpit, `temporizadores.py` por dentro, ni las demás notas numeradas.

## Antecedentes

Ninguna intención de música existe hoy. La nota 25 tiene la tabla «Música y tele» con «pausa»
para el Roku por ECP, que **no está construida** (paso 3 de su §7). Ningún encargo ni descarte
previo trata Spotify. Por la memoria del proyecto, todo encargo que toca funciones del bot
actualiza la guía `35 - Guía de uso de Jaime y Pilar.md` (y su `.html`).

## Qué hacer

1. **`botv3/spotify.py`** (nuevo, sin Telegram). Contiene:
   - `interpretar(texto, sonando: bool) -> dict | None`, una función pura. Devuelve
     `{"accion": "cancion", "titulo": "oxytocin", "artista": "billie eilish"}`,
     `{"accion": "artista", "artista": …}`, `{"accion": "pausa"}`, `{"accion": "sigue"}` o
     `None`;
   - `buscar(consulta, sesion)`: Web API `GET /v1/search` con un token de **Client
     Credentials** (`SPOTIFY_CLIENT_ID` y `SPOTIFY_CLIENT_SECRET` del entorno). El token queda
     en memoria hasta su `expires_in` menos 60 s. Usa `market=CL` y `limit=5`. Primero prueba
     la búsqueda con campos (`track:… artist:…`); si da cero resultados, hace la búsqueda libre;
   - `elegir(resultados, titulo, artista)`: elige la mejor coincidencia con `rapidfuzz`, sin
     tildes y en minúsculas. «oxitocina» / «billi eilish», como lo transcribe Whisper, tiene
     que caer en *Oxytocin — Billie Eilish*;
   - un cliente del receptor: `estado(base)`, `reproducir(base, uri)`, `pausar(base)` y
     `reanudar(base)` sobre la API de go-librespot, con timeout de 3 s.
2. **Perfil:** una clave nueva `spotify = { api = "http://127.0.0.1:3678", otros = ["http://127.0.0.1:3679"] }`
   en `jaime.toml`, y la simétrica en `pilar.toml`. `cargar_perfil` la valida: sólo
   `http://127.0.0.1:<puerto>`. Sin la clave, la intención responde «Spotify no está
   configurado para <Nombre>» y no llama a nada.
3. **Intención en `botv3.py`**, en texto y en voz, **después de `atender_temporizador` y
   antes de `atender_hora_o_clima`**: `atender_spotify(chat_id, texto, en_voz) -> bool`.
   - **Al reproducir:** primero pausa los receptores `otros` que estén sonando, después
     `POST /player/play` en el suyo. Por Telegram responde
     `▶️ Oxytocin — Billie Eilish · Spotify de <persona>`. Por voz no habla: deja la misma
     línea en el chat (nota 25: multimedia responde con un «tin», y el parlante aún no existe).
   - **«pausa» sola** se toma sólo si **alguno** de los receptores está sonando (`/status`).
     Si no hay nada sonando, devuelve `False` y la frase sigue su camino.
   - **Si el receptor no está vinculado:** «Falta vincular tu Spotify: /spotify».
4. **`/spotify`**: muestra el estado del receptor del perfil (vinculado o no, qué suena). Si
   `/auth/code` trae un código pendiente, manda el enlace y el código para aprobarlo desde el
   teléfono. Registra el comando en `update_telegram_commands.py`.
5. **Claves:** suma `SPOTIFY_CLIENT_ID` y `SPOTIFY_CLIENT_SECRET` a `VARIABLES` de
   `pi/cargar-clave.py`, sin prefijo. En el resultado deja la línea para el usuario por
   `nodo-desplegar sugerir`, una por variable y para los dos perfiles:
   `sudo cargar-clave SPOTIFY_CLIENT_ID jaime pilar`.
6. **Guía 35:** una sección corta «Música (Spotify)» con las frases, `/spotify` y la
   vinculación. Vale para los dos bots.

## Criterios de aceptación

- **C1. Frases que captura** (pruebas con la forma real de Whisper: `¿`, punto final,
  mayúsculas, vocativo):
  - «Hola Jaime. Reproducir oxitocina de Billie Eilish en Spotify.» → `cancion`
  - «reproduce Oxytocin de Billie Eilish» → `cancion`
  - «Pon Oxytocin en Spotify» → `cancion`, sin artista
  - «tócame Bad Guy de Billie Eilish en spotify» → `cancion`
  - «Reproduce música de Billie Eilish.» → `artista`
  - «reproduce a Billie Eilish en Spotify» → `artista`
  - «Pausa la música.» → `pausa`
  - «pausa Spotify» → `pausa`
  - «sigue con la música» → `sigue`
  - «pausa» con `sonando=True` → `pausa`
- **C2. Frases que NO captura** (devuelven `None`):
  - «pon una alarma a las 7»
  - «pon un temporizador de 5 minutos»
  - «pausa» con `sonando=False`
  - «pon pausa» con `sonando=False`
  - «agrega leche a la lista»
  - «¿quién canta Oxytocin?»
  - «reproducir la última nota» (sin la palabra Spotify, y «la última nota» no es una canción
    con artista)
  - «compré pan»

  Ninguna prueba existente de `test_botv3.py`, `test_temporizadores.py` ni `test_compras.py`
  cambia de resultado.
- **C3.** `elegir` toma *Oxytocin — Billie Eilish* entre los resultados de la **respuesta real**
  guardada en `botv3/fixtures/spotify-search-oxytocin.json`, buscando con «oxitocina» y «billi
  eilish».
- **C4.** Con dos receptores falsos (servidor HTTP local en un puerto efímero, dentro de la
  prueba), reproducir en el perfil `pilar` pausa primero el receptor de `jaime` que suena y
  después reproduce en el de `pilar`. Se comprueba el orden de las llamadas.
- **C5.** Sin `SPOTIFY_CLIENT_SECRET`, sin red o con un 401, la respuesta es de una línea y
  nada se cae. Con un secreto falso `sk-PRUEBA-NO-DEBE-SALIR`, ese texto no aparece ni en el
  log ni en la respuesta (prueba).
- **C6.** Un perfil con `api = "http://10.0.0.5:3678"` o con `https://…` se rechaza al cargar.
- **C7.** `/spotify` con `/auth/code` pendiente (forma real de `88a-RESULTADO.md`) manda el
  enlace. Si ya está vinculado, muestra «vinculado» y lo que suena.
- **C8.** `python3 -m py_compile` limpio y todas las suites del manifiesto en verde, en la Pi.

## Invariantes

- **Archivos compartidos:** ninguno. El token vive en memoria, no se escribe.
- **Dueño y modo:** `spotify.py` y el fixture, como los demás módulos del bot (mira cómo se dio
  de alta `clima_imagen.py` en la 74).
- **Pruebas sin escribir en `/opt/nodo/datos` ni avisos reales:** el servidor falso va en
  loopback y en un puerto efímero. Ni Telegram ni Spotify reales.
- **Entradas hostiles:** el título dictado va como parámetro de consulta (`params=`), nunca
  pegado en la URL. Largo máximo de 120 caracteres.
- **Choques de frases:** C1 y C2. Va antes de `atender_hora_o_clima` y después de los
  temporizadores.
- **Root:** sólo `cargar-clave` (ya instalado por el catálogo) cambia. Se pide con el despliegue.
- **Alta en `nodo-desplegar`:** `spotify.py`, el fixture y `cargar-clave.py` modificado.
- **Red del bot:** `RestrictAddressFamilies` ya permite `AF_INET`, y loopback no está bloqueado.
  Verifica que ningún `IPAddressDeny` del drop-in de `pilar` corte `127.0.0.1`.

## Fuera de alcance

Playlists propias y «mis me gusta» (piden OAuth por usuario), «siguiente», «qué suena», volumen
de Spotify por voz, el ducking, el Roku y `/estado`: son ampliaciones previstas (diseño 36 §6).
El cliente del receptor deja `volumen(base, valor)` sin usar, para la ampliación.

## Pruebas sobre la forma real

- **Fixture real de `/search`:** si en el entorno de la cola están `SPOTIFY_CLIENT_ID` y
  `SPOTIFY_CLIENT_SECRET`, captura **una** respuesta real
  (`q=track:oxytocin artist:billie eilish`, `type=track`, `market=CL`, `limit=5`) con `curl`
  y guárdala recortada a los campos que se usan. Si no están, usa el ejemplo de respuesta de la
  documentación oficial de `/search` y marca en el resultado «fixture de la documentación, no
  capturado»: la revisión lo vuelve a comprobar.
- **`/status` y `/auth/code`:** la forma la saca la prueba del resultado de la 88a, no la
  inventa.

## Reglas

- No llames a la API real de Spotify desde las pruebas automáticas.
- No escribas el Client Secret en ningún archivo del vault.
- Regex anclados y probados con transcripciones reales (trampa 41r1).

## Resultado

Escribe `encargos/88b-RESULTADO.md` con: cambios por archivo; la tabla C1/C2 con lo que dio
cada frase; el origen del fixture; las líneas de `nodo-desplegar sugerir` para cargar las
claves; la salida de las suites; y los pendientes.
