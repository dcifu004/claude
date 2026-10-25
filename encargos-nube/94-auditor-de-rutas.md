# Encargo 94: 🔎 auditor de rutas de Jaime y Pilar (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `seguridad`. La idea es del 24-10 («Sólo el auditor») y Diego la aprobó el 25-10 para la nube.
**Rama base: `base-94`**, que ya trae el 90 y el 92 mezclados sobre la 88b. Parte de ella.

## Para qué

Las fallas del bot que más costaron fueron silenciosas:
- la ruta `web` por Codex estaba muerta y el respaldo lo tapaba;
- Pilar llegó a Codex por una puerta de atrás;
- `groq/compound` desapareció del catálogo (404).

El auditor vigila **perfil → ruta → cuenta** y avisa a 🚩 cuando aparece una combinación que no está
autorizada. **No cambia nada del bot:** solo lee y avisa.

## Qué se pide

1. **Fuente:** el registro `uso-cuentas.jsonl` de cada perfil, que `pi/bots-info.py` ya lee (`uso_cuentas()`
   ~1236, `por_ruta`). Cada intento deja una línea con `ts, id, perfil, ruta, ruta_nombre, cuenta, motor, modelo,
   ok, s, tokens, forzada`. Un respaldo deja una línea `ok=false` y después otra `ok=true`. **No guarda
   texto.** Si el contador del 92 (`usos`) sirve para algo más, úsalo, pero sin depender de él.
2. **Lista blanca = lo desplegado hoy**, por decisión de Diego del 24-10. Eso incluye el `codex` de Pilar, que
   aplicaron las propuestas AMPLIA del 10-10 desde 🤖. Se obtiene de lo que ya declara cada perfil
   (`botv3/perfiles/*.toml`: `rutas` y `cuentas`), más las reglas del router (por ejemplo,
   `PERFILES_CON_CODEX` en `botv3/botv3.py`). No se mantiene una segunda lista a mano: si el perfil cambia
   por una propuesta aprobada, la lista cambia con él.
3. **Qué se avisa:**
   - una línea perfil → ruta o perfil → ruta → cuenta fuera de la lista;
   - un respaldo que se repite en la misma ruta (por ejemplo, ≥ 3 `ok=false` seguidos en 24 h: una ruta
     muerta que el respaldo tapa);
   - una cuenta o un modelo que aparece y no existe en `cuentas.toml`.

   Propón los umbrales en el PLAN. Sin duplicados: el mismo hallazgo no se avisa de nuevo hasta que
   cambie o pase un plazo.
4. **Dónde corre: igual que el centinela de catálogos (encargo 80a).** Como regla de alertas en
   `pi/estado.py`, al lado de `alertas_catalogo_modelos()` (~112), con 👾/`estado` y su mismo canal hacia 🚩.
   No va un timer propio salvo que el PLAN muestre que no cabe ahí.
5. **Arreglo del comentario:** `botv3/perfiles/pilar.toml:21` dice «`codex` queda fuera» y ya no es cierto.
   Corrígelo para que diga lo que rige hoy, sin cambiar ningún valor.

## Reglas

- Solo lectura: no toca el bot, ni los perfiles (salvo el comentario), ni las cuentas.
- Nada de texto de mensajes en los avisos ni en el estado del auditor ([[que-sale-de-luks-en-la-pi]]): solo
  perfil, ruta, cuenta, modelo, cantidades y horas.
- Pruebas en `pi/test_auditor_rutas.py` (o dentro de las de `estado`), con fixtures inventados de
  `uso-cuentas.jsonl`. Cubren:
  - todo autorizado (no avisa);
  - Pilar → `web` → Codex (avisa);
  - una ruta muerta tapada por el respaldo;
  - una cuenta desconocida;
  - un perfil que cambia por propuesta (la lista lo sigue);
  - el dedup;
  - un registro roto o ausente (no se cae y lo dice una sola vez).
- Suites que no pueden quedar con fallas nuevas: `botv3/test_botv3.py`, `pi/test_cuentas_uso.py` y la de
  `estado`, si existe. Corre las pruebas **como la cola: `python3 botv3/test_botv3.py`**, desde la raíz (no
  `-m unittest`, que deja `botv3/` fuera del `sys.path`).
- Anota en el RESULTADO qué habría que cambiar en la guía (doc 35), si algo.
