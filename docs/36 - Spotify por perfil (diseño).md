---
tipo: diseño
proyecto: ProyectoPi5
actualizado: 2026-10-25
estado: DISEÑO 25-10 (Claude (Diego)); encargo 88 (88a instalación + 88b intención del bot) escrito, sin lanzar (cola en pausa general desde el 23-10)
---

# 36 — Spotify por perfil: «Hola Jaime, reproduce Oxytocin de Billie Eilish en Spotify»

> Complementa a [[25 - Asistente de voz (funcionamiento y frases)]] (sección «Música y tele»)
> y a [[15 - Asistente de voz de la casa (diseño)]], que siguen mandando en identidades,
> permisos y el parlante. Reabre el ítem **Spotify** del [[08 - Backlog de evolución del nodo]]
> con motivo nuevo: el parlante ya no es el de 5 W sólo para voz, sino un **Edifier G2000**
> conectado por **USB de audio** (llegó el 25-10, nota 24), y las dos cuentas son **Premium**
> (el usuario lo confirmó el 25-10).

## 1. Lo que se quiere

- «Hola Jaime, reproduce Oxytocin de Billie Eilish en Spotify» → suena en el parlante de la
  casa **con la cuenta de Spotify de Diego** (su historial, sus recomendaciones).
- «Hola Pilar, …» → lo mismo con **la cuenta de Camila**.
- Mientras no exista `escucha.service` (no hay wake word todavía), la misma frase funciona
  **por Telegram**, escrita o como nota de voz, en el chat de cada bot. Es la puerta de la
  Fase 2 → 3 del diseño 15: primero se usa por Telegram.

## 2. Decisión: dos receptores Spotify Connect en la Pi + API local

```text
«reproduce Oxytocin de Billie Eilish»  (Telegram o, más adelante, escucha.service)
        │
botv3@jaime / botv3@pilar ── intención local `spotify` (antes de compras y del router)
        │ 1) busca la canción: Web API /search con Client Credentials (app de Diego)
        │ 2) pausa el OTRO receptor si está sonando
        │ 3) POST /player/play {uri} al receptor DE SU perfil
        ▼
spotify@jaime  (go-librespot, cuenta de Diego, 127.0.0.1:3678, dispositivo «Casa · Jaime»)
spotify@pilar  (go-librespot, cuenta de Camila, 127.0.0.1:3679, dispositivo «Casa · Pilar»)
        │ audio por pipewire-pulse
        ▼
PipeWire (dcifu004) → sink por defecto → USB → Edifier G2000 (estéreo, 48 kHz)
                   └→ copia mono 16 kHz → XVF3800 (sólo referencia del AEC)
```

**Por qué así:**

- **Spotify no reproduce en la Pi por sí solo** (backlog 12-09): hace falta un receptor
  Connect. `librespot` no viene por apt en Debian 13 (verificado el 25-10). Se usa
  **`go-librespot`** (devgianlu) con binario publicado: trae una **API HTTP local**
  (`POST /player/play {"uri": …}`, `pause`, `resume`, `volume`, `status`). Con eso el bot
  manda la canción **sin pedirle a cada cuenta permisos de la Web API**.
- **Cada cuenta, su receptor:** la identidad la da el perfil del bot, que ya es la identidad
  del wake word (diseño 15). Jaime nunca toca la cuenta de Camila ni al revés, salvo para
  **pausar** al otro y que no suenen dos canciones encima.
- **Vinculación por `device_auth`:** cada receptor muestra un enlace y un código. Cada
  persona lo aprueba **desde su propio teléfono**, con su cuenta. Nadie escribe contraseñas
  en la Pi, ni la IA tampoco. Sin zeroconf, para que un invitado en la red no tome el receptor.
- **Búsqueda con Client Credentials:** `/search` no necesita usuario. La app de
  desarrollador es **una sola, de Diego** (Premium, requisito de Spotify desde el 11-02-2026)
  y no gasta el cupo de 5 usuarios del modo desarrollo.
- **De regalo:** los dos receptores aparecen en la app de Spotify del teléfono como
  dispositivos «Casa · Jaime» y «Casa · Pilar», y se puede tirar música desde ahí.

**Descartado:** la integración de Home Assistant (diseño 25, decisión 1: HA no se mete en el
audio); Web API de reproducción por usuario (dos OAuth, tokens que caducan a los 6 meses y
el cupo de 5 usuarios); `raspotify` (un solo receptor y repositorio apt de terceros).

## 3. Frases (v1)

| Se dice | Hace |
|---|---|
| «reproduce Oxytocin de Billie Eilish (en Spotify)» · «reproducir …» · «pon … en Spotify» · «toca … en Spotify» | busca la canción, toma la mejor coincidencia y suena |
| «reproduce música de Billie Eilish» · «reproduce a Billie Eilish» | suena el artista |
| «pausa la música» · «pausa Spotify» · «para la música» | pausa el receptor que esté sonando |
| «sigue con la música» · «continúa Spotify» | reanuda |
| «pausa» (sola) | pausa Spotify **sólo si está sonando**; si no, no la toma (queda para el Roku) |
| `/spotify` | estado del receptor de ese perfil y, si falta vincular, el enlace |

«pon X» **sin** la palabra Spotify no se toma, porque «pon una alarma» y «pon pausa» ya
tienen dueño. Por voz se responde con un «tin» (nota 25: multimedia no habla). Por Telegram:
«▶️ Oxytocin — Billie Eilish · Spotify de Diego».

## 4. Lo que hace cada persona

**Diego, hoy (sin esperar al encargo):**
1. Crear la app en <https://developer.spotify.com/dashboard> con su cuenta Premium: nombre
   «Casa», API **Web API**, redirect URI `http://127.0.0.1:8888/callback` (el formulario lo
   exige, no se usa). Guardar Client ID y Client Secret en su gestor de claves. **No pegarlos
   en un chat.** El despliegue de la 88b los pide con una línea de `nodo-desplegar sugerir`.
2. Lo del día de llegada de la nota 25 §8 (flashear el XVF3800, canal ASR, volumen límite).
   No depende de esto.

**Diego y Camila, después del despliegue de la 88a:** `/spotify` en su bot → abrir el enlace
en su teléfono → aprobar con su cuenta. Una vez por persona.

## 5. Riesgos y supuestos

- **La API local de go-librespot no tiene autenticación.** Escucha sólo en `127.0.0.1`.
  Cualquier proceso de la Pi podría poner música en cualquiera de las dos cuentas.
  **Aceptado:** el daño posible es una canción, y el bot de Pilar ya necesita llegar al
  receptor de Jaime para pausarlo.
- **Supuesto:** `device_auth` guarda la credencial y sobrevive a reinicios. Si no, la 88a lo
  reporta y se cambia a `interactive` con un túnel SSH una sola vez.
- **Supuesto:** hay binario linux-arm64 publicado. Si no, la 88a se detiene y avisa: no se
  compila Go en la Pi dentro del encargo.
- **Calidad:** con el G2000 por USB, la música sale completa: estéreo y 48 kHz. El límite de
  16 kHz mono era del jack del XVF3800, que ya no se usa. Riesgo pendiente: el *clock drift*
  entre las dos tarjetas USB, que podría degradar el AEC en sesiones largas (se mide el día de
  llegada).
- **Wake word:** «Hola Jaime» no existe todavía. Primero viene la Fase 3 con preentrenados
  («hey jarvis» → Jaime, «alexa» → Pilar) y después la Fase 4. La intención de Spotify es la
  misma en los tres casos.

## 6. Ampliaciones previstas (fuera de la v1)

Playlists propias y «mis me gusta» (piden OAuth por usuario); «siguiente», «qué suena»,
volumen de Spotify por voz (va con `multimedia.py` y el ducking de `parlante.service`);
receptores en `/estado`; que la música iniciada desde el teléfono también pause al otro
receptor.
