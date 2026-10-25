# Dcs_v3bot — consultas de solo lectura

## Alcance vigente

Dcs_v3bot es una interfaz privada de consulta. Lee los vaults autorizados, puede consultar
adaptadores acotados mediante n8n y puede sugerir un comando para que Diego lo copie a
Termux. **Nunca ejecuta el comando sugerido ni modifica archivos.**

Diego autorizó el envío de los fragmentos necesarios de `vault_trabajo` a Claude,
Codex u OpenAI para responder consultas. El 12-09-2026 se habilitó en la Pi
`BOTV3_ALLOW_WORK_VAULT=1` y se montó el vault laboral como sólo lectura. El ejemplo de
configuración conserva el valor 0 para instalaciones nuevas. OpenAI sigue pendiente de
configuración; esta autorización no implica que su adaptador esté activo.

`@Dcs_v2bot` no cambia: sigue capturando notas y adjuntos. Termux + SSH sigue siendo la
única interfaz con poder para ejecutar trabajo real.

## Comandos

- Una pregunta sin `/` entra al clasificador de n8n y muestra la ruta elegida.
- **Una nota de voz** se transcribe con Whisper en Groq y entra por el mismo camino.
  El bot muestra `🎤 Entendí: …` antes de consultar, porque Whisper se equivoca con
  nombres propios y hay que poder ver de qué texto partió la respuesta. **Una
  transcripción nunca se ejecuta como comando**, aunque empiece con `/`: un comando se
  escribe, no se dicta. El audio no se guarda en ningún lado — archivar notas de voz es
  tarea de `@Dcs_v2bot`. La transcripción va directo a Groq, sin pasar por n8n: es la
  misma llamada que ya hace el bot de captura y meter n8n en el medio sólo agregaría un
  punto de falla. Requiere `GROQ_API_KEY` en `botv3.env`, **duplicada a propósito**
  desde `captura.env`: `secretos/` está en `InaccessiblePaths` y este servicio no puede
  leer la otra copia.
- **Si preguntaste hablando, te contesta hablando.** Una consulta que llegó por voz se
  responde con **texto + nota de voz**; una escrita, sólo con texto. El texto va siempre:
  las respuestas traen rutas, fuentes y URLs que escuchadas no sirven. Sobre 1200
  caracteres no sintetiza —escuchar cinco minutos es peor que leer— y un fallo del TTS
  nunca rompe la respuesta, sólo la deja sin audio. **Piper corre local y el texto no sale
  del nodo**: ésa es la razón de elegirlo sobre un TTS en la nube, que recibiría contenido
  de los vaults. Binario en `/opt/piper`, voz `es_AR-daniela-high`, y `opusenc` para
  convertir a lo único que Telegram acepta en `sendVoice`.
- `/claude <pregunta>`: acceso directo de diagnóstico a la ruta que lee archivos
  (los dos vaults y, desde el 19-09-2026, los dos Drive montados).
- `/web <pregunta>`: fuerza la búsqueda en internet. La resuelve **Codex** en el perfil
  que lo declara (`web_codex = true`), con Claude de respaldo cuando falla o se agota.
- `/codex` **ya no existe como ruta**: Codex dejó de leer vaults el 19-09-2026 y quedó
  sólo como motor de `/web`. El binario sigue ahí para `--test-agent codex` y para la
  verificación del vault laboral. Pedirlo responde «no corresponde a este bot».
- `/sql <pregunta>`: PostgreSQL mediante n8n y un rol de sólo lectura.
- `/ha <pregunta>`: Home Assistant mediante n8n, sin llamadas de servicio.
- `/gpt <pregunta>`: API de OpenAI mediante n8n, cuando exista una API key propia.
- **`/compras` — lista de compras de la casa, y la única cosa que este bot
  escribe.** No contradice "sólo lectura": no toca ningún vault ni ejecuta nada,
  edita un archivo de estado en `/opt/nodo/datos/casa`. Se maneja escrito
  (`/compras agregar pan, leche`, `/compras sacar pan`, `/compras enviar`) o
  hablando («Jaime, agrega tomates y queso a la lista», «revisa la lista»,
  «manda la lista»). El checklist inline compartido (detrás de «🛒 Ir a
  comprar»): marcar persiste en el JSON, se ve en ambos perfiles y «Terminar
  compra» guarda hasta 30 compras en historial antes de sacar sólo lo marcado.
  Ya no usa encuestas.
  - **`/compras` sin nada abre el menú (encargo 65, 19-10-2026)**: la lista
    arriba y botones abajo. Lo mismo mandan «muéstrame la lista», `enviar` a uno
    mismo y la lista que llega por el buzón. Un botón que no aplica no aparece:
    - `➕ Agregar` (`cmp:m:agr`) — pide «🛒 Una cosa por línea…» con
      `force_reply`; la respuesta se anota como siempre.
    - `🗑 Quitar` (`cmp:m:qui`, sólo con ítems) — «🗑 ¿Qué saco? Toca los
      productos.»: todos sin marcar; nada se borra hasta `🗑 Sacar N`.
    - `🛒 Ir a comprar` (`cmp:m:ir`, sólo con ítems) — el checklist ⬜/✅.
    - `📤 Enviar a…` (`cmp:m:env`, con ítems y otro perfil en `perfiles/`) — un
      botón por perfil (`cmp:env:<perfil>`), revalidado contra los TOML al tocar.
    - `↩️ Deshacer` (`cmp:m:undo`) — lo mismo que «deshaz eso».
    - `🧹 Vaciar comprados (N)` (`cmp:m:vac`, sólo si N > 0) — pide confirmar;
      `✖️ No` vuelve al menú.
    - `⬅️ Menú` y `📋 Ver lista` (`cmp:menu:x`) vuelven al menú en el mismo
      mensaje. Cada botón lee la lista al tocar, no la del momento del dibujo.
  - **Agregar no pide permiso; sacar por chat sí, con un botón.**
    La asimetría es a propósito: un ítem de más se ve en la lista y se borra en
    un toque, uno de menos se descubre en la casa sin la cosa.
    Por voz tampoco se saca nada sin botón (67, revisión 1): las coincidencias
    únicas llegan marcadas a la misma propuesta 🗑 del chat y las ambiguas, sin
    marcar. «deshaz eso» dictado también pide el ↩️.
  - «Ya compré…», «qué falta por comprar», «está X en la lista» y «cuántas
    cosas hay» se resuelven localmente. Los ítems marcados quedan en el JSON y
    `ultima_accion` registra agregar o sacar por perfil para que el deshacer no
    cruce entre personas ni procesos.
  - **Se reconoce con expresiones regulares locales y NUNCA pasa por n8n.** La
    ruta general va a Groq, que no está cubierto por la autorización, y una
    lista de compras dice qué se consume en la casa y cuántos son. Además un
    regex es determinista: «agregar tomates» no puede clasificarse distinto
    según el día.
  - **La lista es compartida entre los perfiles**: lo que anota Camila lo ve
    Diego. Ver más abajo.
  - **No hace falta nombrar la lista.** «falta leche», «se acabó el café»,
    «necesitamos papel higiénico», «hay que comprar tomates» anotan igual. Esas
    formas llevan una guarda: **un complemento que empieza con infinitivo es una
    tarea, no una compra**, así que «falta terminar el informe» y «necesito
    revisar el contrato» siguen yendo a su ruta. Sin la guarda el modo de falla
    es doble — la consulta sin responder Y basura en la lista.
  - **`/compras enviar a pilar`** (o «manda la lista a Camila») se la deja al
    otro bot de la casa. Ver el buzón, más abajo.
  - **Frases libres (encargo 61, 18-10-2026).** Se escribe como se diría, con
    el comando o sin él: «muéstrame el carrito», «agrégame leche y pan porfa»,
    «sácame el pan de la lista», «qué hay que comprar», «mándamela». Los verbos
    aceptan el pronombre pegado (agrégame, añádeme, anótame, ponme, súmame,
    mételo; sácame, quítame, bórrame, elimíname; muéstrame, enséñame, ábreme;
    mándamela, envíamela, pásamela) y se comparan sin tildes. Sinónimos de la
    lista: «el carrito», «el carro de (las) compras», «la lista del
    súper/supermercado», «mis compras». **«el carro» a secas NO es la lista**:
    en Chile es el auto, y «muéstrame el carro» puede ser una foto del auto. Al
    argumento se le quita el relleno («varias cosas:», «lo siguiente:», «a la
    lista», «porfa», «gracias»); eso vive en `_limpiar_argumento` de `botv3.py`,
    no en `partir()`, que también parte la voz y el pegado de notas.
  - **Cómo se resuelve `/compras <texto>`** (`intencion_comando_compras`; gana
    el primero que calza): (1) primera palabra en `VERBOS_COMPRAS`; (2) lo que
    entiende el chat sin comando (`intencion_compras`); (3) frases que sólo
    valen dentro del comando: «qué hay», «qué falta», «listo» (la confirmación
    de 🏁), «deshacer»; (4) un error de tipeo en la primera palabra
    («agrgar», «mostar», «sacr»), con `difflib` y sólo si es un error de dedo
    —letras de menos, dos cambiadas de lugar o una repetida—: «manjar» no se
    corrige a «mandar» ni «salame» a «sácame»; (5) productos sueltos
    («/compras leche, pan y huevos») → **no se anotan solos**: se muestra cómo
    se partió con «✅ Anotar N» / «✖️ No»; (6) lo demás (una pregunta, más de
    120 caracteres sin verbo, sólo signos o emoji, más de 1000 caracteres) → una
    ayuda corta con ejemplos. Sacar sigue pidiendo el botón aunque el verbo
    venga corregido.
  - **Todo es local**: regex, `difflib` y aritmética en la Pi. Ninguna frase
    de compras va a n8n, a Groq ni a ningún modelo; «predictivo» acá es
    tolerante y determinista, no probabilístico.
  - **Los ítems de más de 14 días se marcan con `⏳`** al ver la lista, y un
    botón ofrece sacarlos todos. No se purgan solos: a veces sí era algo que
    llevas semanas sin encontrar. Una edad que no se puede medir no cuenta como
    vieja.

### El buzón entre bots

Un bot **no puede escribir en el chat de otro**: son tokens distintos y el ajeno
vive en `secretos/`, inaccesible para el servicio. Eso no es un obstáculo que
convenga rodear — es el límite entre dos personas. Así que el emisor deja un
archivo en `casa/buzon/` y el receptor lo recoge en su propio ciclo (cada 20 s,
en un hilo aparte del `getUpdates`, que bloquea 30 s por vuelta) y manda el
mensaje con **su** token:

```json
{"para":"pilar","de":"jaime","tipo":"lista","texto":"",
 "ts":"2026-09-20 16:19","epoch":1789931964}
```

Se borra al leerlo y dentro del lock: entregarlo dos veces manda dos checklists y
el receptor no puede saber que la primera salió. Vence a la hora, y al vencer
**contesta** — deja un pedido `tipo: "aviso"` de vuelta, porque quien lo mandó ya
leyó «le dejé la lista» y sin eso se queda creyendo que llegó.

Es simétrico: los dos servicios corren el mismo binario, así que la dirección la
decide el campo `para`. Los destinatarios salen de los TOML de perfil, por nombre
de perfil (`pilar`) o de persona (`Camila`); no hay lista cableada.
- `/estado`, `/uso`, `/acciones`, `/ayuda`.

Los adaptadores `/sql`, `/ha` y `/gpt` permanecen cerrados mientras
`BOTV3_N8N_QUERY_URL` esté vacío. Fallan de forma explícita; no degradan a shell.

La conversación sin `/` se activa sólo al publicar el webhook autenticado y configurar
`BOTV3_N8N_QUERY_URL`. Hasta entonces, el servicio desplegado conserva los comandos
directos para no dejar la interfaz normal apuntando a una dependencia incompleta.

## El canal compartido de la casa (20-09-2026)

Hasta esta fecha la "memoria de hogar" era compartida **sólo de nombre**:
`guardar_memoria()` escribía en `casa-<perfil>.md` dentro del `STATE_DIR` de cada
perfil, y cada unidad tiene el directorio del otro en `InaccessiblePaths`. Lo que
Camila guardaba "de la casa" Diego no lo veía nunca. El único archivo común,
`nodo-memoria/casa.md`, está montado `ReadOnlyPaths` y lo edita Diego a mano.

Ahora existe `/opt/nodo/datos/casa` (`2770 root:casa`, setgid), escribible por
las dos instancias, con la lista de compras y los appends de memoria de hogar.
`leer_memoria()` lee los `casa-*.md` de **todos** los perfiles.

Lo que se comparte es sólo ese directorio. Los `STATE_DIR` siguen tapados entre
sí, con `memoria.md` y `claude-config` —que guarda una credencial— adentro.

Se instala y se verifica con `sudo bash instalar-casa.sh`. Tres cosas que
rompen en silencio si faltan, y por eso el script las comprueba:

- **`UMask=0077` gana sobre el grupo.** Un archivo creado por el servicio nace
  `0600` y el otro perfil no lo lee aunque esté en `casa`. Por eso el código
  hace `chmod` explícito sobre cada archivo compartido, incluido
  `.compras.lock` — que nadie lee y es el más fácil de olvidar: sin él el
  segundo bot falla al ABRIR un archivo que no aparece en el código de negocio.
- **El setgid del directorio es lo que fija el grupo**, no el del proceso. Sin
  el `2` de `2770` los archivos nacen con grupo `botpilar`.
- **`SupplementaryGroups` se toma al arrancar el proceso.** Sin `restart` el bot
  sigue sin el grupo y escribir falla con `EACCES` sobre un directorio que en el
  disco se ve perfecto.

La prueba que concluye no es ninguna de ésas por separado: es agregar algo desde
un bot y verlo aparecer en el otro.

**El respaldo**: `casa/` entró a `RUTAS` de `respaldo.sh` el 20-09-2026. No está
en Syncthing a propósito —dos escritores en una carpeta sincronizada producen
`.sync-conflict`—, así que restic es su única copia. Dos trampas al verificarlo,
las dos dan falso negativo: `restic ls latest` apunta al snapshot de **Postgres**
(hay dos por corrida, hace falta `--tag archivos`), y un `2>/dev/null` se traga
el error de repositorio mal configurado y devuelve vacío, que se lee igual que
"no está respaldado".

## Límites efectivos

- Los dos agentes trabajan con sandbox/herramientas de lectura.
- systemd monta ambos vaults como `ReadOnlyPaths` y sólo permite escritura en el estado
  operativo de Bot V3.
- `/home`, secretos y sockets Docker son inaccesibles para el servicio.
- No existen propuestas, aprobaciones, movimientos ni escrituras **sobre los
  vaults ni sobre el sistema**. La única escritura del bot es su propio estado:
  los appends de memoria aprobados con un botón y la lista de compras.
- Los únicos procesos auxiliares del panel son rutas y argumentos fijados en una lista
  interna. Ningún texto de Telegram entra en `subprocess`.

## Archivos operativos

- Código: `/opt/botv3`.
- Ejecutables aislados: `/opt/botv3/bin/claude` y `/opt/botv3/bin/codex`. Se copian
  durante el despliegue; deben actualizarse al actualizar los agentes del sistema.
- Estado: `/opt/nodo/datos/botv3`.
- Secreto: `/opt/nodo/datos/secretos/botv3.env`.
- Unidad: `/etc/systemd/system/botv3.service`.

## Verificación

```bash
python3 /opt/botv3/test_botv3.py
python3 /opt/botv3/test_compras.py
sudo bash /opt/botv3/instalar-casa.sh --verificar
node /opt/botv3/test_n8n_classifier.mjs
sudo systemd-analyze verify /etc/systemd/system/botv3.service
sudo -u dcifu004 /usr/bin/python3 /opt/botv3/botv3.py --check
sudo -u dcifu004 /usr/bin/python3 /opt/botv3/botv3.py --test-agent codex
sudo -u dcifu004 /usr/bin/python3 /opt/botv3/botv3.py --test-agent claude
```

Pruebas negativas obligatorias: propuesta de escritura, comando multilínea, posible
secreto, adaptador desconocido y proceso fuera de la lista fija.
