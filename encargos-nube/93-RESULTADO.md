# Resultado 93: guía de uso de Jaime y Pilar al día (Claude (Diego), en la nube, 25-10-2026)

Rama `claude/cool-cannon-ee8axd-93`. Naturaleza documentación: **no se cambió código**.

**Desvío de la regla del plan:** `encargos-nube/93-PLAN.md` va en el primer commit de la rama, pero lo escribí
después de hacer el inventario y la guía, no antes. El contenido del plan es el que se siguió.

## Lo hecho

- **Inventario contra el código** (no contra la memoria). Fuentes:
  - `botv3/botv3.py`: el despachador `handle_message`/`handle_callback`, `AREAS_MENU`, `HELP` y sus bloques
    condicionales;
  - `botv3/update_telegram_commands.py`;
  - los dos perfiles;
  - `compras.py`, `temporizadores.py`, `boleta.py`, `clima_imagen.py`, `recetas.py`, `agenda_correo.py`;
  - la tabla de diferencias de abajo, fila por fila.
- **Guía nueva:** `docs/35 - Guía de uso de Jaime y Pilar.md` y su `.html`, regenerados desde una sola lista de
  filas para que no vuelvan a diferir (la versión anterior del `.html` y la del `.md` ya decían cosas distintas
  sobre Buscar).
  - Mantiene el estilo, la tabla y el tono para alguien que no programa, con frases reales.
  - Saca los nombres internos (`voz_habla_agenda`, `acceptEdits`, `mensaje`, `vault_personal`, SearXNG,
    Open-Meteo).
  - Agrega un bloque «Lo que pide ✅», la sección **Pilar (Camila)** y **Próximamente**.
- **Comportamiento de hoy:** `/uso` sigue en texto y no hay `/usos`. Los encargos 90 y 92 agregan su parte
  después; sus RESULTADOS dicen qué cambiar.
- **HTML:** es autocontenido (0 recursos externos). Revisado con Chromium a 375 px en tema claro y oscuro:
  `scrollWidth = 375`, sin scroll horizontal y con 20 tarjetas.

## Diferencias entre la guía anterior y el código

| # | Tipo | La guía decía / no decía | Lo que hace el código | Archivo:línea |
|---|---|---|---|---|
| 1 | Falta en la guía | Nada sobre mandar la foto de una boleta | Con la ruta `boleta` (los dos bots), una foto o PDF sin pie o con «boleta» prepara el gasto y se anota con ✅; se corrigen fecha y monto antes | `botv3/botv3.py:1742`, `:7956`, `:3184` |
| 2 | Falta en la guía | No mencionaba el hilo ni `/olvidar` | Recuerda 10 turnos y corta tras 15 min sin hablar; `/olvidar` y `/nuevo` lo cortan | `botv3/botv3.py:1387`, `:1391`, `:8115` |
| 3 | Falta en la guía | No mencionaba 👍 / 👎 | Las respuestas de rutas con cuenta traen botones para calificar | `botv3/botv3.py:4929` |
| 4 | Falta en la guía | No decía que muestra lo entendido | Toda nota de voz muestra «🎤 Entendí: …» antes de contestar | `botv3/botv3.py:7992` |
| 5 | Falta en la guía | Compras sin verbo | `/compras leche, pan y huevos` pregunta antes de anotar | `botv3/botv3.py:1789` |
| 6 | Falta en la guía | Órdenes sin límites | Hasta 10 por bot, como mucho una cada hora; pausar, reanudar y borrar no piden confirmación y se deshacen en 1 h | `botv3/temporizadores.py:118-120`, `botv3/botv3.py:1806` |
| 7 | Falta en la guía | Memoria: «se guarda sólo con ✅» | Los botones son 🏠 De la casa · 👤 Mía · ✖️ Descartar y la propuesta vence a los 10 min | `botv3/botv3.py:5310`, `:1211` |
| 8 | Falta en la guía | Qué lee cada bot | Jaime lee los vaults personal y de trabajo y el Drive personal; Pilar, ninguno | `botv3/perfiles/jaime.toml:20`, `:36`; `botv3/perfiles/pilar.toml:15` |
| 9 | Falta en la guía | Foto con otro pie | Ninguno de los dos tiene la ruta `vision`: contesta «La ruta vision no está activa en este perfil» | `botv3/perfiles/*.toml:62/25`, `botv3/botv3.py:7967` |
| 10 | Guía con nombres internos | Agenda: «se apaga con `voz_habla_agenda`» | Es una clave del perfil, no algo que se pida al bot | `botv3/botv3.py:3895` |
| 11 | Guía con nombres internos | Remote Control: «permiso `acceptEdits`» | Se cambió por «puede editar archivos sin preguntar cada vez» | — |
| 12 | Guía con nombres internos | Mensajes de las IA: `mensaje`, `vault_personal` | Se cambió por «los manda Claude o Codex» y «archivos personales» | — |
| 13 | Guía incoherente | `.md`: «no envía la consulta a ningún contador»; `.html`: «el contador no guarda la consulta» | `/buscar` no guarda ni registra lo buscado (en el log sólo va el tipo de error) | `botv3/botv3.py:2071`, `:2095` |
| 14 | En código, no prometido | Mercado Libre no aparecía | `/vigilar`, `/vigilados`, `/dejar` y `/cotizar` existen, pero sólo si el bot conecta con su puente (`ml_falta()`). Va a **Próximamente** | `botv3/botv3.py:4715`, `:4730` |
| 15 | En código, no prometido | Comandos de diagnóstico no aparecían | `/claude`, `/codex`, `/gpt`, `/web`, `/sql`, `/ha` y los alias `/archivos`, `/tecnica`, `/general`, `/casa`, `/agenda` existen «sólo como diagnóstico y compatibilidad» (dice la ayuda). **No se agregaron**, para no confundir | `botv3/botv3.py:8138`, `botv3/recetas.py:27` |
| 16 | Sigue bien | Menú, gastos (tope, voz), agenda, correo, clima (345 comunas, 6 opciones, ubicación de 10 min, caché de 30 min), hora, temporizadores (10 activos, 5 s a 24 h), estado, uso por escrito, Remote Control (8 h), mensajes a Pilar con ✅ | Coincide | `botv3/botv3.py:7776-7790`, `:3310`, `:3940`, `:4019`, `:4020`; `botv3/temporizadores.py:107-109`; `botv3/boleta.py:19`; `botv3/comunas-cl.json` |
| 17 | Lo que la guía describe y el código no tiene | No encontré ninguna función prometida que falte. Lo de «Lo que no está todavía» sigue sin estar (agenda en Pilar, mover o borrar eventos, avisos antes de una reunión, voz de sala) | — | — |

Spotify: **no hay nada** en `botv3/` (`grep -i spotify` vacío), así que no va ni en Próximamente.

## Para que Diego decida (dudoso)

- **Mercado Libre:** el código está, pero depende de que el bot pueda conectarse a su puente. Lo dejé en
  «Próximamente» con «todavía no consta encendido». Si ya funciona en Jaime, se pasa a la tabla.
- **Jaime lee también los archivos del trabajo.** Lo puse porque es lo que hace el código, pero Camila lee la
  guía. ¿Va así o se dice sólo «tus archivos»?
- **`/cami`, `/codex`, `/diego` en Pilar:** existen en los dos bots. En Pilar, `/diego` cae a la cuenta de siempre
  porque no tiene esa sesión. Lo dejé como fila común.
- **«temperatura del living»:** escribí «sigue yendo a la casa (sensores)», en vez de nombrar Home Assistant.

## Errores encontrados en el bot

Ninguno que cambie lo que la guía promete. Una observación: los envíos de foto se llaman siempre `clima.png`
(`send_photo`, `botv3/botv3.py:6120`). No se nota en el chat; cuando el 90 mande `/uso` como imagen, el archivo
también se va a llamar así.

## Archivos tocados

- `docs/35 - Guía de uso de Jaime y Pilar.md` (reescrito)
- `docs/35 - Guía de uso de Jaime y Pilar.html` (regenerado)
- `encargos-nube/93-PLAN.md`
- `encargos-nube/93-RESULTADO.md`

## Pruebas

No hay suite para la guía. La comprobación del HTML, con el Chromium del contenedor, a 375 × 800 px:

```
light {"scroll":375,"ancho":375,"externos":0,"cards":20}
dark {"scroll":375,"ancho":375,"externos":0,"cards":20}
```

No se tocó código, así que ninguna suite puede cambiar.

## Riesgos abiertos

- La guía describe lo de hoy. Al mezclar el 90 y el 92 hay que aplicar lo que dicen sus RESULTADOS:
  - la fila 💳 *Uso de cuotas* pasa a imagen;
  - entra la fila de `/usos`.
- El generador que usé para que el `.md` y el `.html` salgan iguales quedó fuera del repositorio (scratchpad). Si
  se quiere, se puede guardar en `docs/` como herramienta.
