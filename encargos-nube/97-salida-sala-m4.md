# Encargo 97: una sola salida con canal (M2) y «qué puedes hacer» (M4) (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `bot`. Afinado completo. **Parte de la rama del encargo 96** (no de `base-96`): los dos tocan
`handle_message`, y así se mezclan sin conflicto.

## Para qué

Llegó el parlante (Edifier G2000). Antes de que exista el micrófono de la sala, el bot tiene que saber contestar
por tres canales con una sola salida: **texto de Telegram**, **nota de voz de Telegram** y **sala** (el parlante
de la Pi). Así, cuando lleguen `escucha.service` y `parlante.service`, no hay que tocar cada intención otra vez.

## Antecedentes (leídos el 25-10)

- **Doc 34** (`34 - Comandos del bot y voz de sala (plan).md`, §3 Bloques): M2 y M4 aprobados por Diego el 19-10, «con
  el parlante». **El encabezado del doc está viejo:** M1 y los encargos 66 a 69 ya están desplegados.
- **Nota 25 §2**: `parlante.service` es el único dueño del parlante. El bot deja un JSON
  `{perfil, texto, voz, prioridad}` en `/opt/nodo/datos/voz/parlante/` y `parlante` lo sintetiza. No abre sockets.
  Las rutas lentas o gobernadas dicen «te lo mando al chat».
- **Ya existe:** `decidir_voz()`, `sintetizar()`, `send_voice()` y `RUTAS_GOBERNADAS` (`google` y `boleta` nunca se
  dicen en voz alta). Las intenciones del 67, el 68 y el 69 ya devuelven `(texto_chat, frase_hablada)`.
  `voz_habla_agenda` en el perfil apaga la agenda hablada. El contador del 92 anota el canal
  `texto|voz|boton`.
- **La 88 (Spotify)** usa el mismo parlante. No toques sus unidades ni su `spotify.py`.

## Qué se pide

### M2: una sola salida con canal

1. Una función `responder(origen, chat_id, texto_chat, frase=None, botones=None, ruta=None, prioridad="normal")`
   que reparte:
   - `telegram`: el texto (y los botones) como hoy;
   - `voz_telegram`: el texto y, si `decidir_voz()` lo permite y hay frase, la nota de voz;
   - `sala`: escribe la frase en `VOZ_PARLANTE_DIR` (por entorno; por defecto `/opt/nodo/datos/voz/parlante/`) como
     un JSON `{perfil, texto, voz, prioridad, ts, id}`, con escritura atómica (`.tmp` único en la misma carpeta y
     `os.replace`, `0640`). Si la respuesta no se puede decir (ruta gobernada, sin frase o larga), la sala dice
     **«Te lo mando al chat»** y el texto va a Telegram.
2. Pasa por `responder()` las intenciones locales que ya devuelven `(texto_chat, frase)`: hora y clima, gastos,
   agenda y correo, temporizadores y órdenes, compras, nodo y Spotify, y la respuesta de las rutas. Hazlo en
   bloques chicos. Lo que no alcances a migrar sin riesgo queda listado en el RESULTADO, no a medias.
3. **Entrada de la sala para pruebas:** `atender_dicho(texto, origen="sala")` corre el mismo camino que una nota de
   voz ya transcrita, sin Whisper. Ningún lector de cola de `escucha` se hace en este encargo.
4. Intenciones que **sólo valen en la sala**: «repite» (la última frase del perfil), «cancela» u «olvídalo» (corta
   sin responder) y «estás ahí» («Sí.»). En Telegram siguen su camino de hoy.
5. El contador del 92 anota `canal = "sala"` y el libro (encargo 96) anota `canal = "sala"`.
6. Reglas que se respetan: `RUTAS_GOBERNADAS` nunca se dice; de la agenda se dice sólo la hora y el título, salvo que
   `voz_habla_agenda = false`; montos y saldo de gastos nunca se dicen; el correo, sólo cuántos.

### M4: «qué puedes hacer»

- Frases (ancladas, enteras): «qué puedes hacer», «qué sabes hacer», «para qué sirves», «qué haces», «ayuda»
  (sólo sola, nunca dentro de otra frase).
- Respuesta en dos partes, **armada con lo que el perfil tiene activo** (rutas y funciones). Nunca nombra algo que
  ese bot no puede hacer.
- **Texto exacto: el de la sección «Texto de M4» de abajo, aprobado por Diego.** Las líneas entre corchetes salen
  sólo si su condición se cumple.

## Texto de M4

> Pendiente de la revisión de Diego. Si cambia, se reemplaza aquí antes de lanzar.

**Hablado** (sala y nota de voz; máximo 2 frases):

- Jaime: «Puedo poner temporizadores y alarmas, anotar en la lista de compras, decirte la hora, el clima y tu
  agenda, y contestar preguntas. Te dejé la lista completa en el chat.»
- Pilar: «Puedo poner temporizadores y alarmas, anotar compras y gastos, decirte la hora y el clima, y contestar
  preguntas. Te dejé la lista completa en el chat.»
- Regla para armarla: «Puedo» + las 3–4 primeras funciones activas en este orden: temporizadores y alarmas →
  compras [y gastos] → hora y clima [y agenda] → «y contestar preguntas». Cierra con «Te dejé la lista completa en el
  chat.»

**Chat:**

```text
Esto puedo hacer, escrito o por voz:

⏰ Temporizadores y alarmas — «temporizador de 10 minutos para los tallarines»
🔁 Órdenes que se repiten — «despiértame de lunes a viernes a las 6:30»
🛒 Compras — «falta leche», «qué hay en la lista»
[💳 Gastos — «anota un gasto de 15 lucas en la feria» (se confirma acá)]
[📅 Agenda y correo — «qué tengo mañana», «tengo correos nuevos»]
🌦️ Clima y hora — «va a llover hoy», «qué hora es»
[🎵 Spotify — «pon música»]
🩺 El nodo — «cómo está la Pi»

Para elegir quién contesta, empieza con:
🧠 «pregunta técnica: …» — la cuenta con más margen
🔎 «busca en internet: …» — hasta 5 enlaces
⚡ «pregunta rápida: …» — respuesta corta

Todo con botones: /menu · Detalle: /ayuda
```

Condiciones: Gastos con la ruta `boleta`; Agenda con la ruta `google`; Spotify con `spotify` en el perfil y el
módulo cargado; cada selector sólo si su ruta está en el perfil.

## Criterios de aceptación (pruebas en `botv3/test_botv3.py` o `botv3/test_sala.py`)

- **C1 Canales:** la misma intención (hora) por `telegram`, `voz_telegram` y `sala` da: sólo texto; texto y nota de
  voz; y un JSON en la carpeta de la sala con `perfil`, `texto`, `voz` y `prioridad`, más el texto en el chat sólo si
  corresponde.
- **C2 Gobernadas:** una respuesta de `google` y otra de `boleta` por `sala` no escriben su contenido en el JSON:
  la sala dice «Te lo mando al chat» y el texto va a Telegram. La agenda por sala dice sólo hora y título, y nada con
  `voz_habla_agenda = false`. Un gasto por sala no dice el monto.
- **C3 JSON atómico:** dos escrituras simultáneas no se pisan (ids distintos, sin `.tmp` sueltos); un directorio que
  no se puede escribir no tumba la respuesta de Telegram y se anota una sola vez.
- **C4 Sólo sala:** «repite», «cancela» y «estás ahí» funcionan por `sala` y por Telegram siguen su camino de hoy
  («cancela el de los tallarines» sigue cancelando el temporizador).
- **C5 M4:** «qué puedes hacer» en Jaime y en Pilar da el texto de arriba con sus condiciones; un perfil sin `boleta`
  no nombra gastos. «ayuda con la lista» no dispara M4.
- **C6 Canal en los registros:** una consulta por sala deja `canal = "sala"` en el contador y en el libro.
- **C7 Suites:** `botv3/test_botv3.py`, `botv3/test_contador.py`, `botv3/test_spotify.py`, `pi/test_cuentas_uso.py`,
  `pi/test_auditor_rutas.py` y las pruebas del 96, sin fallas nuevas (lista antes y después).

## Invariantes

- **Archivos compartidos:** la carpeta de la sala la escriben los dos bots y la leerá `parlante`. Por eso: un `.tmp`
  único por proceso en la misma carpeta, `os.replace` y un nombre `<ts>-<perfil>-<id>.json` que ordena por hora.
- **Dueño y modo:** el JSON se crea `0640`. **Supuesto sin comprobar:** el grupo común de la carpeta entre
  `botv3@jaime`, `botv3@pilar` y el futuro `parlante`. Si el bot no puede escribir ahí, se degrada a Telegram y lo
  dice una vez. El RESULTADO propone la unidad o drop-in (`ReadWritePaths`, grupo) como archivo, sin activarlo.
- **Pruebas:** `VOZ_PARLANTE_DIR` en `tempfile`, fijado antes de importar; sin Piper real (`sintetizar` reemplazado);
  sin red ni Telegram real.
- **Entradas hostiles:** texto con saltos de línea, comillas o 4000 caracteres en el JSON (se recorta la frase
  hablada a un máximo razonable y se escapa con `json.dumps`).
- **Choques de frases:** los de C4 y C5, más todas las pruebas de intenciones que ya existen.
- **Root:** ninguno. **`nodo-desplegar`:** si nace un módulo nuevo, el RESULTADO lo dice.

## Leer primero

`CLAUDE.md`, `encargos-nube/96-RESULTADO.md`; en `botv3/botv3.py`: `handle_message`, `decidir_voz`, `sintetizar`,
`send_voice`, `RUTAS_GOBERNADAS`, `atender_hora_o_clima`, `atender_gasto_dicho`, `atender_frase_google`,
`atender_temporizador`, `atender_nodo`, `atender_compras`, `atender_spotify`, `process_query`, `HELP` y el contador del
92.

## No hace falta leer

`pi/cockpit-*`, `pi/estado.py` por dentro, `recetas.py` (salvo lo que dejó el 96), `agenda_correo.py` por dentro y
`encargos/`.

## Fuera de alcance

- **G4** (avisos de eventos como orden permanente): va después, cuando M2 esté desplegado.
- `escucha.service`, `parlante.service`, wake word, barge-in, sonidos de estado y modo invitado.
- Cambiar textos de las intenciones existentes, salvo pasarlos por `responder()`.

## Entrega

Rama propia, con el primer commit `encargos-nube/97-PLAN.md`. Al final, `encargos-nube/97-RESULTADO.md` con: lo
hecho, lo que quedó sin migrar a `responder()` y por qué, los archivos tocados, la salida real de las pruebas, la unidad o
drop-in propuesta para la carpeta de la sala y lo que cambia en la guía 35.
