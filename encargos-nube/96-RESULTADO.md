# Encargo 96: RESULTADO de los selectores dichos y la cuenta de la ruta técnica

Rama `claude/encargo-96-selectores-voz`, creada desde `base-96`. Plan en `96-PLAN.md`.

## Lo hecho

### A. Selectores

- `selector_dicho(texto)` (`botv3.py:5667`): regex anclados sobre `_plano()`, que tiene el mismo largo que el
  texto, así el corte se hace sobre el texto de verdad. Reusa el prefijo de la 06b (`_ANTES_DE_LA_FRASE`): saludo,
  vocativo propio, «¿» y «por favor». Acepta:
  - «pregunta técnica» / «pregunta tecnica» → `tecnica`;
  - «pregunta rápida» → `rapida`;
  - «busca(me) en internet» y «busca en la web» → `buscar`.

  También acepta «una» delante, y `,` `:` `.` `?` después. El «¿» que abre la pregunta se queda con ella. Cualquier
  otra forma no calza (`(?![a-z0-9])`): «pregunta tecnicamente…» no es un selector.
- `atender_selector()` (`:5679`) va en los dos caminos de `handle_message`:
  - **voz:** justo después de «🎤 Entendí», antes de la 06b y de todas las intenciones locales;
  - **texto:** después de las respuestas a botones, que son el contexto explícito del mensaje, y antes de
    `cuenta_pedida` y las intenciones. Nunca con un `/comando`.

  Sin pregunta, pide la que falta. Sin la ruta en el perfil, contesta «La ruta técnica no corresponde a este bot.».
  El resto pasa por `cuenta_pedida`, así que la 06b no cambia: va sola y sin respaldo. «busca en internet» llama a
  `buscar_searxng`, igual que `/buscar`. El texto se corta en 4000 caracteres.

### B. Cuenta de la ruta técnica

- **Una sola implementación del margen** en `recetas.py`, que usan el bot y `bots-info`:
  - `libre_de()` (`:687`): lo libre de la ventana más apretada;
  - `orden_por_margen()` (`:696`): las que no están sobre el umbral, por más libre; después las sin dato; al
    final, de respaldo, las sobre el umbral; el empate lo decide la cadena.

  `pi/bots-info.py: margen_de` ahora las llama, en vez de calcular por su cuenta.
- `orden_de_cuentas("codex")` → `_orden_tecnica()` (`botv3.py:1132`), sólo para la ruta técnica y sin cuenta
  forzada. Así vale igual entrando por el selector, por `/tecnica` o por el clasificador.
  - Elegibles: la cadena del perfil, más `cuentas_del_automatico` con receta automática.
  - `elegir_orden` mide la sesión, el % y el umbral, y `orden_por_margen` ordena.
  - **Modo fijo:** la cuenta de Telegram, o la cadena de una sola cuenta sin receta automática (💳 Cuentas →
    Fija). Va primero si no está sobre el umbral.
  - **Modo automático:** todo lo demás. Por eso **Pilar, sin receta, ordena sus 2 por margen** (C5).
- **Aviso** (`aviso_tecnica`, `:1148`): si contestó otra cuenta que la primera elegida, sale una línea, sin pisar
  el aviso de «todas sobre el umbral»:
  - modo fijo: «🔁 Claude (Cami) está sobre el umbral; contestó Codex», «🔁 Claude (Cami) falló; contestó Codex»;
  - modo automático: «🔁 Contestó Codex: Claude (Cami) estaba sobre el umbral»;
  - en los dos, también «no tiene sesión en este bot».
- **`/cuenta_tecnica`** (`:8208`, `:8223`): muestra el modo vigente y desde dónde se eligió (Telegram o el perfil),
  con un botón `🤖 Automático` y uno por cada elegible del perfil. Pilar no ve Claude (Diego). Una cuenta no
  elegible se rechaza y se dice por qué.
- **Estado:** `STATE_DIR/cuenta-tecnica.json`.
  - Se escribe con `flock` sobre `.cuenta-tecnica.lock`, un `.tmp` único (pid más uuid) con `O_EXCL`, `fsync`,
    `os.replace` y `0600`.
  - Se lee con `O_NOFOLLOW`, y sólo si es regular, propio, de 4 KiB o menos y con la forma conocida. Si no, se
    ignora y se dice una vez en el log por motivo.
- **Gana el último cambio:** `perfil_visto` es el sha256 corto (16) de la receta y la cadena de `codex`.
  `revisar_cuenta_tecnica_al_arrancar()` (`:1094`) corre en `main()`. Si la huella cambió, borra el estado, lo
  anota en el log y avisa una sola vez: «La cuenta técnica la cambiaste desde 💳 Cuentas; dejé sin efecto la de
  Telegram.».
- **`bots-info`:** `cuenta_tecnica_de(perfil)` expone, de sólo lectura y con `O_NOFOLLOW`, `modo`, `cuenta`, `ts`
  y `desde` de cada perfil, en `perfiles[<p>]["cuenta_tecnica"]`. La página no se tocó.

### C. Libro y contador

- `anotar_uso_cuenta` suma `selector` y `canal` **sólo cuando la consulta vino por un selector**. Viajan en
  `_PEDIDO`, que `process_query` llena siempre: así una consulta sin selector no hereda los del hilo anterior.
- `registrar_busqueda` suma lo mismo. La búsqueda **no** va a `uso-cuentas.jsonl`.
- Contador del 92: `atender_selector` entra a `MARCAS` como `selector:<s>`, condicional, en su punto único.
  `usos.FUNCIONES` suma `selector:tecnica`, `selector:rapida`, `selector:buscar` y `cuenta_tecnica`, y
  `catalogo_usos()` los incluye según las rutas del perfil. `/cuenta_tecnica` va en `ALIAS_COMANDOS` y `ct` en
  `PREFIJOS_BOTON`.
- Lectores: el auditor 94 ignora las claves nuevas, y `bots-info` (`eventos_de_uso`, `_libro_rendimiento`) lee las
  líneas sin problema. Los dos tienen prueba.

### D. Ayuda y menú

- `HELP` suma tres líneas sobre los selectores, la cuenta con más margen, `/cuenta_tecnica` y «pregunta técnica
  con Codex: …».
- `update_telegram_commands.comandos()` suma `cuenta_tecnica` sólo con la ruta `codex`. La prueba del menú de
  `test_botv3.py` (`test_c6_menu_de_telegram_corto`) quedó con la lista nueva de Jaime.

## Archivos tocados

- `botv3/botv3.py`, `botv3/recetas.py`, `botv3/usos.py` y `botv3/update_telegram_commands.py`.
- `pi/bots-info.py`: `margen_de` usa `recetas`, y suma `cuenta_tecnica_de` e `import stat`.
- `botv3/test_selectores.py` (nuevo, 31 pruebas), `pi/test_auditor_rutas.py` (+1) y `botv3/test_botv3.py` (la
  lista esperada del menú).
- `encargos-nube/96-PLAN.md`, `96-RESULTADO.md` y `96-fallas-antes-despues.txt`.

**No nace ningún módulo nuevo**: no hay alta en el catálogo de `nodo-desplegar`. Lo que sí importa es el orden de
despliegue: `recetas.py` (que trae `libre_de` y `orden_por_margen`) tiene que ir **antes o junto con** `bots-info.py`
y `botv3.py`. Un `bots-info` nuevo con un `recetas.py` viejo rompe «¿Quién tiene margen?».

## Pruebas (salida real, como la cola, desde la raíz)

```
                              antes (base-96)                          después
botv3/test_botv3.py           FAILED (failures=7, errors=34) Ran 490   FAILED (failures=7, errors=34) Ran 490
botv3/test_contador.py        OK  Ran 20                               OK  Ran 20
pi/test_cuentas_uso.py        FAILED (failures=1, errors=9, skipped=4) Ran 74   igual
pi/test_auditor_rutas.py      OK  Ran 22                               OK  Ran 23
botv3/test_selectores.py      (no existía)                             OK  Ran 31 tests in 0.672s
```

La lista de fallas es **idéntica** antes y después (`diff` vacío; está en `96-fallas-antes-despues.txt`). Son del
entorno de esta copia: faltan archivos de la Pi, se corre como root y el huso horario es UTC. Por los choques de
frases corrí además `test_compras` (rc 0 antes y después), `test_temporizadores` y `test_spotify`. Estas dos dan rc 1
en `base-96` y también después, por fixtures que faltan en esta copia (`spotify-receptor-v0.10.5.json`).

`test_selectores.py` cubre:

| Criterio | Qué se prueba |
|---|---|
| C1 | Las 9 frases, más «Oye Pilar, …» en Pilar |
| C2 | Las 8 frases que no, que siguen su camino (compras, 06b); el selector solo pide la pregunta y no consulta |
| C3 | «pregunta rápida: pon un temporizador de 5 minutos» va a `gpt`, por texto y voz, sin crear un temporizador |
| C4 | «pregunta técnica con Codex: …» y «…, pregúntale a Claude (Cami) …» son la 06b, sola |
| C5 | Jaime con receta: Codex → Claude (Diego) → Claude (Cami). Pilar: Codex → Claude (Cami). `margen_de` da el mismo orden y libres 70/60/20 |
| C6 | Automático con la primera sobre el umbral; fija que falla; fija sobre el umbral; sin aviso si contesta la primera |
| C7 | Pilar no ve Claude (Diego); rechaza `ct:claude_diego`; fijar Codex deja `0600`, sin `.tmp`, y la consulta siguiente parte por Codex |
| C8 | Huella vieja: se descarta, avisa una vez y rige el perfil; huella igual: no se toca; Jaime sin receta es fija Codex |
| C9 | Una consulta y una búsqueda por selector dejan `selector`/`canal`; la pregunta centinela no aparece en **ningún** archivo del temporal; sin selector, la línea no suma claves |
| Hostiles | 5000 caracteres, `/estado`, «pregúntale a» sin cuenta, `cuenta-tecnica.json` roto, con cuenta inventada o enlace simbólico |

Todo corre sin red: la guarda de `test_contador.py` del 92b, que falla si algo intenta conectarse.

## La propuesta de la receta para Jaime (la aplica Diego)

En **💳 Cuentas → Jaime → ruta técnica → Automático**. Queda como propuesta `recetas` del perfil `jaime`:

```json
{"tipo": "recetas", "perfil": "jaime", "valor": {"tecnica": {"automatico": true}}}
```

Al aplicarla con `sudo aplicar-propuesta <id>`, `jaime.toml` queda con:

```toml
recetas = { tecnica = { automatico = true } }
```

`aplicar-propuesta` la marca **AMPLIA**, porque la técnica pasa a poder gastar Claude (Diego) y Claude (Cami), y
reinicia el bot. Hasta que se aplique, Jaime queda en **fija: Codex**, que es su cadena de hoy (`["codex"]`).

## Qué cambiar en la guía (doc 35)

- Una fila **«🧭 Elegir la ruta»**: «pregunta técnica: …», «pregunta rápida: …» y «busca en internet …», dichas o
  escritas al inicio. La técnica la contesta la cuenta con más margen, la misma que encabeza «¿Quién tiene
  margen?», y si contesta otra se avisa con 🔁. También vale «pregunta técnica con Codex: …», sólo para esa
  pregunta.
- **`/cuenta_tecnica`**: elegir Automático o una cuenta fija. Si después se cambia desde 💳 Cuentas, gana ese
  cambio, y el bot lo avisa una vez.
- En Pilar no aparece Claude (Diego).

## Decisiones

- `selector` y `canal` van sólo con selector. `canal` siempre existe, pero el encargo pide «sólo cuando hay dato»,
  igual que `forzada`, y así las líneas de hoy no cambian.
- El selector escrito va después de las respuestas a botones (✏️ boleta, ➕ gasto, 🛒, agenda). Esas respuestas
  son un contexto explícito del mensaje anterior. El encargo pide «después de la ubicación y los adjuntos», y los
  botones no están en su lista de intenciones locales.
- La **primera ideal** del aviso, en automático, es la de más margen sin mirar el umbral. Así «estaba sobre el
  umbral» se dice cuando de verdad le tocaba a esa.
- Los botones de `/cuenta_tecnica` muestran las elegibles aunque una no tenga sesión. La sesión se mira al
  consultar, y si falta, el aviso lo dice.

## Riesgos abiertos

- **Orden de despliegue:** `recetas.py` antes que `bots-info.py` y `botv3.py` (ver arriba).
- Al aplicar la receta de Jaime, cambia la huella y se descarta cualquier `/cuenta_tecnica` anterior. Es lo que se
  pidió: gana el último cambio.
- El aviso «La cuenta técnica la cambiaste desde 💳 Cuentas…» sale al arrancar por cualquier cambio de la receta o
  la cadena de la técnica, también si lo hizo otra persona en la Pi.
- No se probó en la Pi con Whisper real. Las formas de la transcripción son las del encargo y las de la 06b.
