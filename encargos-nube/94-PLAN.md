# Encargo 94: PLAN del 🔎 auditor de rutas

Rama `claude/encargo-94-auditor-rutas`, creada desde `base-94`.

## Qué se hace

Una regla de alertas nueva, `alertas_rutas()`, en `pi/estado.py`, al lado de
`alertas_catalogo_modelos()`, y se llama en el mismo punto de `alertas(e)`. Llega a 🚩 por el
mismo canal que el centinela 80a: `estado --escribir` deja la alerta en `estado.json` y `avisos.py`
la manda. No hay timer propio: cabe en `estado` (lee dos archivos chicos por perfil y una cola
acotada del registro cada 5 min).

**No toca el bot.** Solo lee: `/opt/botv3/perfiles/*.toml`, `/opt/botv3/cuentas.toml`,
`/opt/botv3/recetas.py` (el desplegado, igual que `bots-info`), el `uso-cuentas.jsonl` y el
`modelos-catalogo.json` de cada perfil.

## Fuente

El `uso-cuentas.jsonl` de cada perfil, en el STATE_DIR que ya usa `CATALOGOS_MODELOS`
(`/opt/nodo/datos/botv3` para Jaime y `/opt/nodo/datos/botv3-pilar` para Pilar), con el mismo
cuidado que el catálogo porque `estado` corre como root: `O_NOFOLLOW`, archivo regular, del dueño
esperado y solo la **cola** del archivo (4 MB, se descarta la primera línea cortada). Se saltan
las líneas `tipo = "calificacion"`. El contador del 92 (`usos`) no se usa: no trae cuenta.

## Lista blanca (derivada, no escrita a mano)

Para cada perfil, en cada corrida:

- **perfil → ruta**: la ruta (normalizada con `recetas.ruta_interna`) está en `rutas` del TOML.
  Es lo mismo que hace el bot (`ALLOWED_AUTO_ROUTES = set(PERFIL_CFG["rutas"])`).
- **perfil → ruta → cuenta**: `recetas.cadena_efectiva(ruta, cuentas)`, la misma función que
  aplica los muros del bot (Codex fuera de `web`, `boleta`, `noticias` y `vision`; nada gratis en
  las rutas de vault; nada pagado en la general). Si la ruta tiene receta `automatico` (o es
  `vision` sin receta, que es automática por defecto), se suman `recetas.cuentas_del_automatico`.

Así, si una propuesta aprobada cambia el perfil, la lista cambia con él. Con lo desplegado hoy:

| perfil | ruta | cuentas autorizadas |
|---|---|---|
| Jaime | claude | Claude (Diego) |
| Jaime | codex | Codex |
| Jaime | web | Claude (Cami), Claude (Diego) — el `codex` declarado lo ignora el muro 11 |
| Jaime | boleta | Gemini, Claude (Cami), Claude (Diego) (por defecto) |
| Jaime | gpt | Groq (por defecto; sin cadena declarada el bot ni anota línea) |
| Pilar | claude | Claude (Cami) |
| Pilar | codex | Claude (Cami), Codex (AMPLIA del 10-10) |
| Pilar | web | Claude (Cami), Claude (Diego) (muro 11, por defecto) |
| Pilar | boleta | Gemini, Claude (Cami), Claude (Diego) (por defecto) |
| Pilar | gpt | Groq (por defecto) |

**`PERFILES_CON_CODEX` no entra.** No está en `botv3.py` sino en el clasificador de n8n
(`n8n-dcs-v3bot-router.workflow.json`), y no es un permiso: es una preferencia de clasificación
(a qué ruta manda n8n una pregunta técnica). El permiso lo da `rutas` del perfil, que el bot
intersecta. Las reglas del router que sí restringen viven en `recetas.py` y entran por
`cadena_efectiva`.

**Cuenta forzada** (`forzada = true`, «/codex», «/diego»): el bot deja forzar cualquier cuenta que
el muro permita y tenga login, aunque no esté en la cadena. El auditor la avisa igual si está
fuera de la lista (con la marca «forzada»): un login que no debería existir es justo la puerta de
atrás por la que Pilar llegó a Codex.

## Qué se avisa y umbrales propuestos

| hallazgo | condición | id (estable) |
|---|---|---|
| ruta no autorizada | ≥ 1 línea en 7 días con una ruta fuera de `rutas` | `rutas:ruta:<perfil>:<ruta>` |
| cuenta no autorizada | ≥ 1 línea (ok o no) en 7 días fuera de la cadena de esa ruta | `rutas:cuenta:<perfil>:<ruta>:<cuenta>` |
| ruta muerta tapada | ≥ 3 `ok=false` seguidos de la misma cuenta en la misma ruta en 24 h, sin un `ok=true` de esa cuenta después | `rutas:muerta:<perfil>:<ruta>:<cuenta>` |
| cuenta desconocida | la cuenta no es una sección de `cuentas.toml` | `rutas:desconocida:<cuenta>` |
| motor que no calza | el `motor` de la línea no es el de `cuentas.toml` | `rutas:motor:<cuenta>:<motor>` |
| modelo desconocido | proveedor gratis con un modelo que no está en el `modelos-catalogo.json` del perfil | `rutas:modelo:<perfil>:<cuenta>:<modelo>` |
| registro ausente o roto | el archivo no está, no se puede abrir con seguridad, o ≥ max(3, 10 %) de las líneas no se leen | `rutas:registro:<perfil>` |
| perfil o `cuentas.toml` ilegible, o sin `recetas.py` | no se puede juzgar | `rutas:perfil:<perfil>`, `rutas:cuentas_toml`, `rutas:recetas` |

**Sin duplicados.** `avisos.py` ya compara por `id` y guarda lo visto: un hallazgo se avisa una
vez, sigue activo mientras haya líneas dentro de la ventana (7 días, 24 h para la ruta muerta) y
se da por resuelto cuando sale de ella. Si vuelve a pasar después, es un aviso nuevo. Un cambio
(otra cuenta, otra ruta) es otro id y se avisa. El texto puede cambiar (cantidades, hora) sin
reavisar. No se guarda estado propio.

Modelos de Claude y Codex: no hay lista contra la cual compararlos (los nombra el CLI y
`cuentas.toml` no los declara), así que solo se revisa el motor. Queda como riesgo abierto.

## Texto de los avisos

Solo perfil, ruta, cuenta, modelo, cantidades y horas. Los de seguridad (ruta o cuenta no
autorizada, cuenta desconocida) empiezan con «🚩», que `avisos.py` sube a nivel `error`. Los demás,
con «🔎».

## Otros

- `botv3/perfiles/pilar.toml:21`: corregir el comentario «`codex` queda fuera» por lo que rige
  hoy, sin cambiar valores.
- Pruebas en `pi/test_auditor_rutas.py` con `tempfile` y fixtures inventados (los casos del
  encargo). Suites que no pueden sumar fallas: `botv3/test_botv3.py` y `pi/test_cuentas_uso.py`
  (no hay suite de `estado`).
- `RESULTADO` con la lista de fallas antes y después, y qué cambiaría en la guía (doc 35).
