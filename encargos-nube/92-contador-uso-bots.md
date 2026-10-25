# Encargo 92: contador de uso de los bots (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `bot`. La idea es del 19-10 y Diego la aprobó el 25-10. Va la **alternativa A**: un contador
propio y durable, no contar desde el journal.

## Hoy

`audit()` en `botv3/botv3.py` escribe `event=… adapter=… status=…` en el journal y lo manda a
`N8N_AUDIT_URL`. Eso tiene límites:
- `/menu`, `/gastos` manual, `/ayuda` y `/acciones` no dejan ningún evento;
- el journal rota (el 19-10 llegaba solo hasta el 10-10);
- no siempre se sabe de qué bot vino ni si fue por voz o por texto.

## Qué se pide

1. **Registro:** una línea por uso (fecha y hora, bot `jaime|pilar`, función o comando, canal
   `texto|voz|boton`, resultado `ok|error`) en un archivo JSONL. Su ruta sale del estado del bot
   (`BOTV3_STATE_DIR`), que en la Pi queda dentro del volumen cifrado. **No se guarda el texto del mensaje**:
   solo la función. El escritor no falla nunca: si no puede escribir, el bot contesta igual y se anota una
   advertencia una sola vez.
2. **Cobertura:** todos los comandos y botones, incluidos los que hoy no dejan evento. Para no repetir
   código, haz un solo punto de registro (por ejemplo, un decorador o el despachador de comandos).
3. **Resumen:** un comando `/usos` (o un botón en `/menu`; propón cuál y justifícalo) con el resumen de
   los últimos 7 días por bot y función, más lo que no se usó nunca. Pilar ve solo lo suyo y Jaime ve los dos.
4. **Para Cockpit:** expone el mismo resumen como JSON en `pi/bots-info.py`, para que después lo use una
   pestaña. La página no se hace en este encargo.
5. **Retención:** propón cuánto se guarda (por ejemplo, 180 días) y cómo se rota sin perder líneas.

## Reglas

- `botv3/botv3.py` también lo toca el encargo 90 (`/uso` como imagen). Cambia solo lo necesario, en
  bloques chicos.
- Pruebas en `botv3/test_botv3.py`, o en `botv3/test_contador.py` si queda más limpio:
  - cada comando deja una línea;
  - el canal sale bien para voz y para texto;
  - el texto del mensaje no queda guardado;
  - un archivo que no se puede escribir no rompe la respuesta;
  - el resumen cuenta bien y respeta Pilar frente a Jaime;
  - la rotación no pierde líneas.
- Suites que no pueden quedar con fallas nuevas: `botv3/test_botv3.py` y `pi/test_cuentas_uso.py`.
- Anota en el RESULTADO qué habría que cambiar en la guía (doc 35).
