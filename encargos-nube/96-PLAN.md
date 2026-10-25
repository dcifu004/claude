# Encargo 96: PLAN de los selectores dichos en voz y la cuenta de la ruta técnica

Rama `claude/encargo-96-selectores-voz`, creada desde `base-96`.

## A. Selectores

- `selector_dicho(texto) -> (selector | None, resto)` en `botv3.py`, con regex anclados sobre `_plano(texto)`
  (mismo largo que el original, así se corta el texto de verdad). Acepta un saludo y el vocativo delante («Hola
  Jaime,», «Oye Pilar»), «¿», «una», sin tilde y `,` `:` `.` `?` después:
  - «pregunta técnica» → `tecnica` (ruta `codex`);
  - «pregunta rápida» → `rapida` (ruta `gpt`);
  - «busca en internet», «búscame en internet» y «busca en la web» → `buscar`.

  Lo que no sea ese comienzo exacto no calza: «la pregunta técnica de ayer…» y «no busques en internet» siguen su
  camino.
- `atender_selector(chat_id, texto, en_voz) -> bool`, en los dos caminos de `handle_message`:
  - en voz, justo después de «🎤 Entendí», antes de la cuenta 06b y de todas las intenciones locales;
  - en texto, después de las respuestas a botones (que son el contexto explícito de un mensaje) y antes de
    `cuenta_pedida` y de las intenciones locales. Nunca se aplica a un `/comando`.

  Sin pregunta, pide la que falta. Si el perfil no tiene la ruta, contesta lo mismo que el comando. Con
  `cuenta_pedida(resto)` se respeta la 06b sin cambios. `tecnica` y `rapida` van a `submit_query(ruta, …,
  en_voz, cuenta, selector=…)`; `buscar`, a lo mismo que `comando_buscar`.
- Contador del 92: `atender_selector` entra a `MARCAS` como `selector:<s>` (condicional) y `usos.FUNCIONES` suma
  `selector:tecnica`, `selector:rapida` y `selector:buscar`. Es un solo punto de registro.

## B. Cuenta de la ruta técnica

- **Una sola implementación del margen** en `recetas.py`:
  - `libre_de(detalle)`: lo libre de la ventana más apretada, como `margen_de`;
  - `orden_por_margen(cuentas, detalle, base, fija=None)`: primero las que no están sobre el umbral, por más
    libre; después las sin dato; al final las sobre el umbral. El empate lo decide `base`.

  `pi/bots-info.py: margen_de` pasa a usar las dos.
- `orden_de_cuentas("codex")`, sin cuenta forzada:
  - elegibles = cadena del perfil, más `cuentas_del_automatico` si la receta es automática;
  - `elegir_orden` (con el automático encendido, sólo para medir) da la sesión, el detalle y el umbral, y después
    se ordena con `orden_por_margen`.

  Modos:
  - **Fija:** la de Telegram, o la cadena de una sola cuenta sin receta automática. Va primero si no está sobre el
    umbral, y si no, cae a la siguiente.
  - **Automático:** todo lo demás, incluida Pilar con sus 2 (C5).

  Las demás rutas no cambian.
- **Aviso:** si contestó otra que la primera ideal (la fija o la de más margen), una línea: «🔁 Claude (Cami) está
  sobre el umbral; contestó Codex» en fija, y «🔁 Contestó Codex: Claude (Cami) estaba sobre el umbral» en
  automático, o «falló» / «no tiene sesión» según el caso.
- **`/cuenta_tecnica`:** muestra el modo vigente y los botones `ct:auto` y `ct:<cuenta>` (sólo las elegibles). El
  estado va a `STATE_DIR/cuenta-tecnica.json`, con `flock` sobre un `.lock`, un `.tmp` único, `os.replace` y
  `0600`. Se lee con `O_NOFOLLOW`, archivo regular, propio y de tamaño acotado. Si es raro, se ignora, y se avisa
  una vez en el log.
- **Huella:** sha256 corto de la receta y la cadena de `codex`. Al arrancar, con huella distinta, se borra el
  estado, se anota en el log y se avisa una vez en el chat.
- `bots-info`: lectura `O_NOFOLLOW` de `cuenta-tecnica.json` por perfil, expuesta junto a lo de 💳 Cuentas.

## C. Libro

`anotar_uso_cuenta` y `registrar_busqueda` suman `selector` y `canal` **sólo cuando la consulta vino por un
selector**. Viajan en `_PEDIDO`. Nunca se guarda el texto.

## D. Ayuda y menú

`HELP` con 3–4 líneas. `/cuenta_tecnica` entra a `comandos()` sólo con la ruta `codex`, con su alias en el
contador.

## Pruebas

`botv3/test_selectores.py` (nueva, del C1 al C9), más una prueba de las líneas nuevas en
`pi/test_auditor_rutas.py`. Se comparan las fallas antes y después en las cuatro suites del C10.
