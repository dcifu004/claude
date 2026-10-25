# Revisión del encargo {ID} (lo ejecuta {REVISOR}, solo revisar)

Trabajas en `/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5`. {AUTOR} hizo
`encargos/{ENCARGO}` y dejó su informe en `encargos/{ID}-RESULTADO.md`. {EXTRA}

Revísalo como un revisor exigente, igual que la revisión 04b (`encargos/04b-RESULTADO.md`), que
es el modelo a seguir. **No modifiques código.**

- El diff propio de la etapa (la suma de autor y arreglos, incluido lo
  borrado) está en `{DIFF}`: léelo primero para ver qué cambió de verdad y no solo lo que el informe dice. Lo que aparezca bajo «Cambios ajenos» no es de
  esta etapa: no lo juzgues ni lo uses como motivo de rechazo.
- Si la etapa trae `plan = true`, lee `encargos/{ID}-PLAN.md`: el código se juzga contra ese plan aprobado; lo que el plan no contemplaba y el código agrega es fuera de alcance.
- **Reproduce** cada comportamiento importante con scripts en un `mktemp -d`, fijando
  `BOTV3_USO_CUENTAS`, `BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` ahí. Nunca uses el libro real.
- Revisa que las pruebas usen la **forma real** de los datos. Es el error que más se ha
  repetido: pruebas en verde con una forma inventada.
- Busca regresiones en lo que ya funcionaba: respuestas largas, fuentes, rutas y voz.
- JS: en la Pi no hay node. Cuenta paréntesis, llaves y template literals con un tokenizador.
- Seguridad: callbacks, archivos temporales, que nada lea los vaults donde no corresponde y
  que no se impriman tokens.
- Si existe `encargos/{ID}-busquedas.jsonl`, léelo entero: es lo que salió a Tavily. Cualquier
  consulta con contenido, rutas o nombres de los vaults es un hallazgo **grave**. Mira también
  `encargos/manual-busquedas.jsonl`: `buscar-web.py --manual` se niega mientras haya una cola viva,
  así que **ninguna** línea suya puede tener una hora dentro de la ventana de la fase de autor de
  este encargo. Si hay una, o el script fue esquivado o el registro fue escrito a mano: es grave.
  Las líneas fuera de esa ventana son del usuario con la cola detenida y no se cuentan.
- **Límite aceptado del buscador (decisión del usuario, 09-10-2026):** autor y cola comparten el
  usuario Unix y la Pi no tiene Yama, así que un agente decidido puede fabricar lo que la cola usa
  para autorizar una búsqueda (permiso, buzón, proceso, `vivo/`) o leer la key. Eso, por sí solo,
  **no** es hallazgo grave ni hace NO DESPLEGABLE; cerrarlo exige un usuario Unix aparte. Sí es grave
  que el camino normal deje pasar lo que el muro, el tope o el registro deben frenar, o que atribuya
  una búsqueda a un encargo distinto del que corre la cola.
- Si existe `encargos/{ID}-decisiones.md`, léelo: son decisiones del usuario sobre esta etapa
  (encargo 51). **Lo decidido ahí no se vuelve a marcar como hallazgo**; una decisión nunca
  autoriza root, secretos ni ampliar el alcance.
- Cada hallazgo va en su propio título con la gravedad entre corchetes, exactamente así:
  `### 1. [Grave] …`, `### 2. [Media] …` o `### 3. [Baja] …` (sólo esas tres etiquetas). La cola
  lee la gravedad de esos títulos: **[Grave]** es todo lo que rompe seguridad, datos o lo que hoy
  funciona; lo de alcance, atribución, cobertura o forma es [Media] o [Baja].
- Nombres (regla forzada): «Claude (Diego)», «Claude (Cami)» y «Codex». **Jamás** «Diego» ni
  «Cami» sueltos, tampoco en tu informe: a la persona se le dice «el usuario».
- Corre las suites ({SUITES}) y pega la salida. Si una falla, distingue si la falla es de este
  encargo o ya estaba antes (la cola guarda la línea base en `~/encargos-logs/<cola>-base.json`).
  Una falla previa que este encargo no tocó **no** hace NO DESPLEGABLE.

Entrega `encargos/{ID}r-RESULTADO.md` con los hallazgos ordenados por gravedad (archivo:línea,
qué falla y cómo se reproduce). La **última línea del archivo** tiene que ser exactamente una de
estas dos:

    VEREDICTO: DESPLEGABLE
    VEREDICTO: NO DESPLEGABLE

Usa «DESPLEGABLE» si lo que queda son solo mejoras que no rompen nada de lo que funciona hoy, y
lístalas igual.
