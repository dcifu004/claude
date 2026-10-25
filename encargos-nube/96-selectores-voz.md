# Encargo 96: selectores dichos en voz y cuenta de la ruta técnica (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `bot`. Afinado completo. **Rama base: `base-96`** (el `botv3.py` vigente del vault, con el 90, el 92, el
92b, la 88 y el 94). Parte de ella. El 97 (M2 + M4) va **después**, sobre la rama de este encargo.

## Para qué

Hoy, para que una pregunta vaya a una ruta concreta hay que escribir un comando (`/tecnica …`, `/buscar …`) o
dejar que decida el clasificador de n8n. Por voz no se puede dictar un comando: las notas de voz nunca se ejecutan
como comando. Diego quiere decir **«pregunta técnica: …»** y que vaya directo a la ruta técnica, con la cuenta que
tenga más margen. Es la decisión ya tomada de «un wake word y la primera frase como selector» (nota 13, nota 25
§«Frase con selector»).

## Antecedentes (leídos el 25-10; el autor y el revisor no ven la memoria de la IA)

- **Nota 25** (`25 - Asistente de voz (funcionamiento y frases).md`, §«Frase con selector + vigilantes», 07-10):
  define el selector como una intención local en `botv3.py`, antes de n8n. Si va a una ruta lenta, por voz contesta
  «te lo mando al chat». Si la cuenta asignada está agotada, eso se dice y no queda mudo. Es una lista cerrada en regex.
- **Ya existe** (no reconstruir):
  - comandos de ruta: `/tecnica <pregunta>` (alias de la ruta interna `codex`, `recetas.ALIAS_RUTA`), `/general`
    (`gpt`) y `/buscar <consulta>` (`comando_buscar`, buscador local, hasta 5 enlaces; mide en
    `registrar_busqueda` → `buscar-uso.jsonl`);
  - **cuenta forzada (06b)**: «pregúntale a Codex …», «con Claude (Diego) …», `/cami` `/codex` `/diego`
    (`extraer_cuenta`, `cuenta_pedida`, `cuenta_forzada`). **Va sola y sin respaldo, a propósito**: si falla, se
    le dice a quien preguntó;
  - **receta automática por ruta** (`recetas.elegir_orden`, `orden_de_cuentas`): con `automatico = true` suma
    cualquier cuenta pagada que el muro permita (`cuentas_del_automatico`) y ordena por **% semanal**. Se cambia
    desde 💳 Cuentas con la propuesta `recetas`, que valida `pi/aplicar-propuesta.py` (root) y **sólo acepta**
    `automatico`, `umbral_semanal` y `umbral_5h`;
  - **«¿Quién tiene margen?»** (`pi/bots-info.py: margen_de`, y `bots-info --margen`, que el bot ya llama para
    `/uso`): por cuenta, `libre_pct = min(libre de 5 h, libre semanal)`, la ventana más apretada. Usa
    `recetas.elegir_orden` para el % y el «sobre el umbral»;
  - el libro `uso-cuentas.jsonl` (`anotar_uso_cuenta`) y el contador del 92 (`usos.py`, `contando_uso`);
  - el auditor 94 (`pi/estado.py`): su lista blanca sale de `rutas` y `cuentas` del perfil desplegado, más
    `cuentas_del_automatico()` cuando la ruta tiene receta automática.
- La ruta técnica (`codex`) acepta los dos motores (`invoke_agent`: `codex` y `claude`).
- Perfiles hoy: Jaime `cuentas.codex = ["codex"]`, sin receta; Pilar `cuentas.codex = ["claude_cami", "codex"]`.

## Decisiones de Diego (25-10, cerradas; no se reabren)

1. **Tres selectores**: «pregunta técnica» → ruta `codex`; «busca en internet» → el buscador local (lo mismo que
   `/buscar`); «pregunta rápida» → ruta `gpt`. «Pregunta a Claude» **no** entra.
2. Valen **por voz y por escrito**, al inicio del mensaje.
3. **Cuenta automática de la técnica con el criterio de «¿Quién tiene margen?»**: gana la cuenta con más
   `libre_pct` (la ventana más apretada), para que el bot y 💳 Cuentas coincidan. **Jaime elige entre las 3**
   (Claude (Cami), Claude (Diego) y Codex). **Pilar elige sólo entre sus 2** (Claude (Cami) y Codex).
4. Cambio a mano de tres formas: desde **💳 Cuentas** (Automático / Fija), desde **Telegram** y **dicha en la frase**
   (sólo para esa pregunta). Entre Cockpit y Telegram, **gana el último cambio**.
5. Si la cuenta elegida (automática o fija) está agotada o sobre el umbral, **cae a la siguiente y avisa cuál
   contestó**.
6. El libro suma **`selector` y `canal`**, para la futura red de rutas. Nunca el texto del mensaje.

## Qué se pide

### A. Selectores (intención local, en `handle_message`)

- Una función `selector_dicho(texto) -> (selector | None, resto)` con regex **anclados al inicio**, sobre el texto
  normalizado (`_plano`). Acepta las formas reales de Whisper: mayúscula inicial, «¿», coma, dos puntos o punto
  después del selector, sin tilde («tecnica», «rapida»), un saludo opcional delante («Hola Jaime,», «Oye Pilar»)
  y «una pregunta técnica». Para la búsqueda acepta además «búscame en internet» y «busca en la web».
- Si después del selector no queda pregunta, contesta qué falta («¿Qué quieres que busque?») y no consulta.
- **Orden:** va **antes** de las intenciones locales (temporizadores, Spotify, hora y clima, gastos, Google, nodo y
  compras), en los dos caminos (voz y texto), después de la ubicación y los adjuntos. Quien dice el selector eligió
  la ruta: «pregunta rápida: pon un temporizador» va a `gpt`.
- **Cuenta en la frase:** al resto se le aplica `cuenta_pedida`, así que «pregunta técnica con Codex: …» y
  «pregunta técnica, pregúntale a Claude (Cami) …» fuerzan la cuenta **con la regla 06b de siempre** (sola, sin
  respaldo). Esa regla no se cambia.
- Si la ruta no está en `ALLOWED_AUTO_ROUTES` del perfil, contesta lo mismo que el comando
  («La ruta técnica no corresponde a este bot.»).
- «busca en internet» llama a lo mismo que `comando_buscar`; «pregunta rápida» y «pregunta técnica», a lo mismo que
  `/general` y `/tecnica` (`submit_query`), con `en_voz` cuando vino por voz.

### B. Cuenta de la ruta técnica

- **Elegibles:** la cadena del perfil para `codex` más, si la receta de `codex` es automática,
  `cuentas_del_automatico("codex")`, siempre con sesión y permitidas por el muro. Con eso, **Jaime necesita la
  receta automática en la técnica** para llegar a las 3. No la escribas en `jaime.toml`: es una propuesta que Diego
  aplica desde 💳 Cuentas (deja en el RESULTADO la línea exacta de la propuesta). Pilar queda sin receta
  automática, con sus 2.
- **Orden en modo automático:** por `libre_pct` de mayor a menor, calculado igual que `margen_de` (reúsalo o saca
  la función a `recetas.py` para que la usen el bot y `bots-info`; **una sola implementación**). Las cuentas sobre
  el umbral quedan al final, de respaldo, como hoy. Sin dato, después de las con dato. El empate lo decide el
  orden de la cadena. Este orden vale **para la ruta `codex`**, entre por el selector, por `/tecnica` o por el
  clasificador, para que la ruta se comporte igual siempre. Las demás rutas no cambian.
- **Modo fijo:** una sola cuenta elegida primero. Si está sobre el umbral o falla, cae a la siguiente elegible
  y avisa («🔁 Claude (Cami) está sobre el umbral; contestó Codex»). Esto es distinto de la cuenta forzada 06b.
- **Desde Cockpit (sin tocar `aplicar-propuesta` ni la página):** Automático = receta `automatico = true` en
  `codex`. Fija = la cadena de `codex` con una sola cuenta y sin receta automática. Las dos ya se proponen desde
  💳 Cuentas.
- **Desde Telegram:** el comando **`/cuenta_tecnica`** (`/tecnica` ya es el comando de la ruta) muestra el modo
  vigente y botones `🤖 Automático` + una por cada cuenta elegible del perfil (Pilar no ve Claude (Diego)). Queda
  guardado como estado en `STATE_DIR/cuenta-tecnica.json`:
  `{"modo": "auto"|"fija", "cuenta": …, "ts": …, "desde": "telegram", "perfil_visto": <huella>}`.
  Una cuenta que no es elegible se rechaza y se dice por qué.
- **Gana el último cambio:** `perfil_visto` es la huella (por ejemplo, sha256 corto) de la receta y la cadena de
  `codex` del perfil cargado cuando se tocó el botón. Al arrancar el bot (cada propuesta aplicada lo reinicia), si
  la huella actual difiere, el cambio de Cockpit es posterior: se descarta el estado de Telegram, se anota en el log y
  se avisa una vez en el chat del perfil («La cuenta técnica la cambiaste desde 💳 Cuentas; dejé sin efecto la de
  Telegram»).
- **Para que Cockpit muestre quién la cambió:** `pi/bots-info.py` expone, de sólo lectura, el estado de
  `cuenta-tecnica.json` de cada perfil (modo, cuenta, hora y desde dónde) junto a lo de 💳 Cuentas. La página no
  se cambia en este encargo (ver «Fuera de alcance»).
- Avisos al chat: el de siempre de la cuenta forzada se mantiene; en modo automático, si contestó una cuenta que no
  era la primera, una línea («🔁 Contestó Codex: Claude (Cami) estaba sobre el umbral»).

### C. Libro y contador

- `anotar_uso_cuenta` suma `selector` (`"tecnica"`, `"rapida"`) y `canal` (`"texto"`, `"voz"`), **sólo cuando
  hay dato**, igual que `forzada`. Viajan en `_PEDIDO`, como la cuenta forzada.
- `registrar_busqueda` suma los mismos campos. **No escribas la búsqueda en `uso-cuentas.jsonl`**: el buscador no
  es una cuenta y el auditor 94 lo marcaría como «cuenta desconocida».
- El contador del 92 registra el selector como función (por ejemplo, `selector:tecnica`) por su punto único
  (`contando_uso`), sin un segundo punto de registro.
- Comprueba que `pi/bots-info.py` y el auditor 94 lean las líneas nuevas sin romperse (las claves nuevas se
  ignoran o se cuentan, nunca tumban la lectura).

### D. Ayuda y menú

- `HELP` explica los tres selectores en 3–4 líneas, junto a lo de la cuenta en la frase.
- `/cuenta_tecnica` entra a `update_telegram_commands.comandos()` **sólo si** el perfil tiene la ruta `codex`, y
  la prueba del menú lo cubre.
- Anota en el RESULTADO qué cambiar en la guía (doc 35).

## Criterios de aceptación (cada uno con su prueba en `botv3/test_botv3.py` o `botv3/test_selectores.py`)

- **C1 Frases que sí:** «Pregunta técnica: ¿por qué falla el cron?», «pregunta tecnica, revisa…»,
  «Hola Jaime, pregunta técnica: …», «¿Pregunta rápida? cuánto es 15 % de 2300», «Busca en internet precios del
  G2000», «búscame en internet …», «busca en la web …», «una pregunta técnica: …» → selector y resto correctos.
- **C2 Frases que no** (siguen su camino de hoy): «la pregunta técnica de ayer era otra», «no busques en internet»,
  «falta leche», «temporizador de 10 minutos», «pregúntale a Codex qué hora es» (06b, sin selector),
  «pregunta técnica» sola (pide la pregunta y no consulta).
- **C3 Orden:** «pregunta rápida: pon un temporizador de 5 minutos» va a `gpt` y no crea un temporizador, por voz
  y por texto.
- **C4 Cuenta en la frase:** «pregunta técnica con Codex: …» fuerza Codex sin respaldo (06b intacta).
- **C5 Margen:** con un `uso.json` de prueba (Claude (Cami) 5 h 80 % / sem 10 %; Claude (Diego) 5 h 20 % / sem 40 %;
  Codex 5 h 30 % / sem 30 %), Jaime con receta automática ordena Codex (libre 70) → Claude (Diego) (60) →
  Claude (Cami) (20). Pilar, con los mismos datos, elige sólo entre Codex y Claude (Cami): Codex → Claude (Cami).
  El mismo fixture en `margen_de` da el mismo orden por `libre_pct`.
- **C6 Agotada:** con la primera sobre el umbral, contesta la siguiente y el aviso nombra a las dos.
- **C7 Telegram:** `/cuenta_tecnica` en Pilar no ofrece Claude (Diego); fijar Codex escribe el estado con
  escritura atómica (`.tmp` único y `os.replace`) y `0600`; la consulta siguiente parte por Codex.
- **C8 Último cambio:** estado de Telegram con una huella vieja + perfil cambiado → al cargar se descarta, se avisa
  una sola vez y rige el perfil.
- **C9 Libro:** una consulta por selector deja `selector` y `canal` en `uso-cuentas.jsonl`, y una búsqueda los deja
  en `buscar-uso.jsonl`. Ninguna línea trae el texto de la pregunta (prueba con una pregunta centinela que no debe
  aparecer en ningún archivo). El auditor 94 (`pi/test_auditor_rutas.py`) y `bots-info` leen las líneas nuevas sin
  avisos falsos.
- **C10 Suites:** `botv3/test_botv3.py`, `botv3/test_contador.py`, `pi/test_cuentas_uso.py` y
  `pi/test_auditor_rutas.py`, sin fallas nuevas (lista antes y después en el RESULTADO).

## Invariantes

- **Archivos compartidos:** `cuenta-tecnica.json` lo escribe sólo el bot de su perfil. Usa `flock` y un `.tmp`
  único por proceso. El libro y `buscar-uso.jsonl` siguen con su candado actual.
- **Dueño y modo:** lo crea el usuario del bot dentro de su `STATE_DIR` (en la Pi, en el LUKS), con `0600`.
  `bots-info` (root) sólo lo lee, sin seguir symlinks (`O_NOFOLLOW`, como el resto de sus lecturas).
- **Pruebas:** con `tempfile` y variables de entorno fijadas **antes** de importar el módulo (`BOTV3_USO_CUENTAS`,
  `BOTV3_BUSCAR_USO`, `BOTV3_STATE_DIR`, `BOTV3_USO_JSON`). Sin red ni Telegram real (el bloqueo de red del
  `test_contador.py` del 92b es el modelo). Nada en `/opt/nodo/datos`.
- **Entradas hostiles:** un selector seguido de 4000 caracteres, de `/comando`, o de «pregúntale a» sin cuenta, y un
  `cuenta-tecnica.json` roto, ajeno, symlink o con una cuenta inventada: no rompen nada; lo raro se ignora y se
  dice una vez.
- **Choques de frases:** los de C2, más las frases de compras, temporizadores, gastos, clima y Google que ya tienen
  pruebas: ninguna cambia de destino.
- **Root:** no se toca `aplicar-propuesta`. `bots-info` gana una lectura más y nada de escritura.
- **`nodo-desplegar`:** si nace un módulo nuevo (por ejemplo, `selectores.py`), el RESULTADO lo dice para darlo de
  alta en el catálogo y sumarlo a la lista de deriva de `bots-info`.

## Leer primero

`CLAUDE.md`; en `botv3/botv3.py`: `handle_message`, `cuenta_pedida`/`extraer_cuenta`, `orden_de_cuentas`,
`_correr_cadena`, `anotar_uso_cuenta`, `registrar_busqueda`, `comando_buscar`, `submit_query`, `HELP` y
`contando_uso`; `botv3/recetas.py` (`elegir_orden`, `cuentas_del_automatico`); `pi/bots-info.py` (`margen_de` y
la lectura de `uso-cuentas.jsonl`); `pi/estado.py` (auditor 94); `botv3/update_telegram_commands.py`;
`botv3/perfiles/*.toml`.

## No hace falta leer

`pi/cockpit-*` (la página no cambia), `spotify.py`, `temporizadores.py` por dentro, `agenda_correo.py`, `boleta.py`,
`mercadolibre.py` y `encargos/`.

## Fuera de alcance

- Mostrar el modo y quién lo cambió en la página 💳 Cuentas (ampliación prevista: lee el campo que deja `bots-info`).
- Aplicar la receta automática en `jaime.toml` (lo hace Diego con la propuesta).
- M2, M4 y la sala (encargo 97); `escucha.service` y `parlante.service`.
- Cambiar la regla 06b de la cuenta forzada, el muro de `recetas.py` o `aplicar-propuesta`.
- «Pregunta a Claude» y otros selectores.

## Entrega

Rama propia, con el primer commit `encargos-nube/96-PLAN.md`. Al final, `encargos-nube/96-RESULTADO.md` con: lo
hecho, los archivos tocados, la salida real de las pruebas (fallas antes y después), la línea de la propuesta de
receta para Jaime, lo que cambia en la guía 35 y los riesgos abiertos.
