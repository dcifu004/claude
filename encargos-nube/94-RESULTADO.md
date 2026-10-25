# Encargo 94: RESULTADO del 🔎 auditor de rutas

Rama `claude/encargo-94-auditor-rutas`, creada desde `base-94`. Plan en `94-PLAN.md`.

## Lo hecho

- **`pi/estado.py`**: regla nueva `alertas_rutas()`, al lado de `alertas_catalogo_modelos()`.
  Se llama desde `alertas(e)` dentro de un `try` que, si el auditor revienta, deja una alerta
  `rutas:fallo` en vez de tumbar el estado. Llega a 🚩 por el mismo camino que el centinela 80a:
  `estado --escribir` → `estado.json` → `avisos.py`. No lleva timer propio.
- **Fuente**: el `uso-cuentas.jsonl` de cada perfil, ubicado junto al `modelos-catalogo.json` de
  `CATALOGOS_MODELOS` (mismo dueño). Se lee como el catálogo, porque corre como root:
  `O_NOFOLLOW`, archivo regular, `nlink == 1`, dueño esperado. Solo se lee la **cola** de 4 MB y,
  si se cortó, se descarta su primera línea. Las líneas `tipo = "calificacion"` se saltan. El
  contador `usos` del 92 no se usa porque no trae la cuenta.
- **Lista blanca derivada**: en cada corrida se lee `rutas` del perfil desplegado
  (`/opt/botv3/perfiles/*.toml`) y las cuentas de `recetas.cadena_efectiva()` del `recetas.py`
  desplegado, más `cuentas_del_automatico()` cuando hay receta automática (o en `vision` sin
  receta). Son los mismos muros que aplica el bot, así que una propuesta aprobada mueve la lista
  sola.
- **Avisos** (ids estables; los de seguridad empiezan con 🚩 y los demás con 🔎):
  - `rutas:ruta:<perfil>:<ruta>`: una ruta fuera de `rutas` en los últimos 7 días.
  - `rutas:cuenta:<perfil>:<ruta>:<cuenta>`: una cuenta fuera de la cadena (ok o no) en 7 días.
    Si fue forzada, lo dice.
  - `rutas:muerta:<perfil>:<ruta>:<cuenta>`: ≥ 3 `ok=false` seguidos en 24 h sin un `ok` de esa
    cuenta después. Dice cuántas veces contestó el respaldo.
  - `rutas:desconocida:<cuenta>`: la cuenta no está en `cuentas.toml`.
  - `rutas:motor:<cuenta>:<motor>`: el motor de la línea no es el que dice `cuentas.toml`.
  - `rutas:modelo:<perfil>:<cuenta>:<modelo>`: un proveedor gratis (Groq, Gemini u OpenRouter)
    usó un modelo que no está en el catálogo del perfil.
  - `rutas:registro:<perfil>`: el registro falta, no se puede abrir con seguridad o trae
    ≥ max(3, 10 %) de líneas ilegibles. Una sola línea cortada no avisa.
  - `rutas:perfil:<perfil>`, `rutas:cuentas_toml` y `rutas:recetas`: no se puede juzgar.
- **Dedup**: no guarda estado propio. `avisos.py` compara por id y no repite lo que ya avisó. El
  texto, con cantidades y hora, puede cambiar sin generar otro aviso. El hallazgo se resuelve solo
  cuando sus líneas salen de la ventana; si vuelve a pasar después, es un aviso nuevo.
- **`botv3/perfiles/pilar.toml`**: el comentario de `rutas` ya no dice «`codex` queda fuera».
  Ahora dice lo que rige: `codex` entró el 10-10 por las AMPLIA (Claude (Cami) primero, Codex de
  respaldo) y su `web` no pasa por Codex por el muro 11. No cambió ningún valor: `rutas` y
  `cuentas` cargan igual que antes.
- **`pi/test_auditor_rutas.py`**: 22 pruebas con `tempfile`, un `/opt/botv3` de mentira (perfiles,
  `cuentas.toml` y el `recetas.py` reales del repo) y registros inventados.

## Archivos tocados

- `pi/estado.py` (+237 / −0 en el código; un solo bloque nuevo y 7 líneas en `alertas`)
- `botv3/perfiles/pilar.toml` (solo el comentario)
- `pi/test_auditor_rutas.py` (nuevo)
- `encargos-nube/94-PLAN.md`, `94-RESULTADO.md` y `94-fallas-antes-despues.txt`

## Pruebas (salida real)

```
$ python3 pi/test_auditor_rutas.py
... (22 pruebas, todas «ok»)
Ran 22 tests in 0.256s
OK
```

Cubren lo pedido: todo autorizado (no avisa), Pilar → web → Codex (avisa), ruta muerta tapada por
el respaldo, cuenta desconocida, perfil que cambia por propuesta (la lista lo sigue en ambos
sentidos), dedup (mismo id; se resuelve a los 7 días) y registro roto o ausente (no se cae y deja
un solo id). Además: Jaime → web → Codex (el muro 11 lo ignora aunque el perfil lo declare), ruta
fuera del perfil, cuenta forzada, dos fallas o un ok en medio (no es ruta muerta), fallas de más
de 24 h, motor que no calza, modelo fuera del catálogo, enlace simbólico, cola acotada, perfil y
`cuentas.toml` ilegibles, falta de `recetas.py`, que no se filtre texto de mensajes, y que
`alertas()` no se caiga si el auditor revienta.

Suites que no podían sumar fallas, corridas como la cola desde la raíz:

```
$ python3 botv3/test_botv3.py      → antes: FAILED (failures=9, errors=36)   después: FAILED (failures=9, errors=36)
$ python3 pi/test_cuentas_uso.py   → antes: FAILED (failures=1, errors=9, skipped=4)   después: igual
```

La lista de fallas es **idéntica** antes y después (`diff` vacío). Está completa en
`94-fallas-antes-despues.txt`. Son fallas del entorno de esta copia: corre como root, faltan
archivos de la Pi y `cuentas.toml` trae umbrales distintos a los que espera una prueba. No hay
suite de `estado`.

## Decisiones

1. **`PERFILES_CON_CODEX` no entra en la lista blanca.** No vive en `botv3.py` sino en el
   clasificador de n8n, y es una preferencia de clasificación, no un permiso. Las reglas del
   router que sí restringen (muro 11, `vision`, la general sin cuentas pagadas, el automático)
   están en `recetas.py` y entran por `cadena_efectiva`.
2. **Lo desplegado hoy autoriza también a Claude (Diego) como respaldo de `web` y `boleta` de
   Pilar.** Es la cadena por defecto que aplica el bot cuando el perfil no declara un proveedor
   gratis. El auditor no avisa por eso, porque es lo que rige. Si Diego no lo quiere, se arregla
   en el perfil, no en el auditor.
3. **La cuenta forzada fuera de la cadena avisa.** El bot la permite si hay login y el muro no la
   prohíbe, pero un login que no debería existir es la puerta de atrás que se quiere ver.
4. **Se atribuye al perfil dueño del directorio**, no al campo `perfil` de la línea.
5. Sin plazo de re-aviso para un hallazgo que sigue ocurriendo: queda activo en `/estado` y
   `avisos.py` no lo repite. Volver a avisar cada N días significaría mandar un «Resuelto» falso.

## Riesgos abiertos

- **No se revisan los modelos de Claude y Codex**: los nombra el CLI y `cuentas.toml` no los
  declara, así que solo se revisa el motor.
- Un registro de un perfil que todavía no usó ninguna ruta con cuenta deja `rutas:registro:<perfil>`
  activo en `/estado` (avisos lo manda una sola vez). Hoy los dos bots tienen registro.
- El dueño del registro se toma de `CATALOGOS_MODELOS`. Un perfil nuevo tiene que entrar ahí, o el
  auditor dirá que no sabe dónde está su registro, que es lo correcto pero obliga a tocarlo.
- `estado` carga `/opt/botv3/recetas.py` como root, igual que `bots-info`. Si un día ese archivo
  deja de ser de root, ambos quedan expuestos por igual.
- No se probó en la Pi (no hay Pi acá). La primera corrida real puede encontrar hallazgos
  verdaderos en el historial de la semana, por ejemplo líneas viejas de `web` por Codex anteriores
  al muro 11 si todavía caen en la ventana.

## Guía (doc 35)

La guía no habla de rutas ni de cuentas por dentro. Bastaría una línea en la fila 🩺 **Estado del
nodo**: «Incluye el auditor de rutas: avisa si un bot usó una ruta o una cuenta que su perfil no
autoriza, o si una ruta falla y el respaldo la tapa». Nada más cambia para Diego ni para Camila.
