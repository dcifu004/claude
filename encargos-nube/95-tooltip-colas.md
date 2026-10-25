# Encargo 95: tooltip de las colas en 🧵 Encargos (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `pagina`. Lo pidió Diego el 25-10. **Rama base: `base-95`.** Parte de ella.

## Para qué

En la consola de 🧵 Encargos (`pi/cockpit-encargos/`, la consola C de los encargos 84–86), los nombres
de cola (`cola88`, `cola91n`…) aparecen en muchos lugares, pero para saber qué hace una cola y en qué quedó
hay que buscar su tarjeta. La idea: **al pasar el cursor por cualquier mención de una `colaNN`** sale una
tarjeta chica con:

1. **qué hace:** el resumen de la cola (`resumenCola(nombre)`, encargo 34: `resumen` o `motivo` de la raíz
   del manifiesto) y, si lo hay, el resumen de su etapa actual (`resumenEtapa(etapaDe(id))`);
2. **la última etapa y fase:** etapa, fase, cuenta y estado, por ejemplo
   «`91n:rev1` · Codex · detenida · 25-10 17:06»;
3. **la última revisión:** la última fila `rev*` de esa cola en el historial, con su `veredicto`, su
   cuenta y sus minutos, por ejemplo «rev1 · Codex · 5,7 min · NO DESPLEGABLE». Si ninguna revisión
   trae veredicto: «sin revisión todavía».

## Antecedentes

- Encargo 34 (`encargos.js` ~15–95): `resumenes()`, `resumenCola()`, `etapaDe()`, `resumenEtapa()`,
  `seguro()` y `unaLinea()`. Hoy el resumen sólo sale en la línea de cada tarjeta (con `title=`).
- Encargo 85a: hay **un solo componente de tooltip**, accesible, en `glosario.js` (`aria-describedby`,
  con el cursor, el foco y al mantener presionado, `activarGlosario(raiz)`). Hay que reutilizarlo o
  extenderlo. No se hace un segundo componente.
- Encargo 84b: en la red (`red.js`) los tooltips son `<title>` de SVG con `textContent`, y el mismo texto
  va en `aria-label`.
- Decisiones de Diego (25-10): **sólo 🧵 Encargos** (no las otras páginas). Para la revisión, **sólo el
  veredicto y la fase**, sin abrir ningún `NNr*-RESULTADO.md`.

## Qué se pide

1. **Sin lecturas nuevas.** Todo sale de lo que `cargar()` ya deja en `d`:
   - `d.resumenes` y `d.etapas`, de los manifiestos;
   - `d.vivos`, de `vivo/<cola>.json`: `estado`, `etapa`, `fase`, `cuenta`, `escrito`/`fin`, `fases_hechas`;
   - `d.h`, del historial: filas con `encargo`, `fase`, `rol`, `cuenta`, `min`, `inicio` y `veredicto`.

   La relación cola ↔ filas del historial pasa por las etapas del manifiesto o por `vivo.etapas`, no por el
   número del nombre: `cola9092n` tiene la etapa `9092n`, y `cola88` tiene las etapas `88a`, `88b` y `88c`.
2. **Una sola función** construye la mención (por ejemplo, `mencionCola(nombre)`, que devuelve el nodo
   con su tooltip). Se usa en **todos** los lugares donde la consola pinta el nombre de una cola:
   - las tarjetas («Cola viva: …», «`colaNN` · …»);
   - la franja Ahora;
   - la matriz «Carga vs. capacidad» (cabeceras y `colas_fuera`);
   - el resultado de las acciones;
   - las autorizadas del despacho;
   - el historial/Traces;
   - la bitácora, si ahí se pinta el nombre como dato aparte.

   En la red, el `<title>` del nodo de una cola suma las mismas tres líneas. Haz un inventario en el PLAN
   (`grep` de dónde sale cada nombre) y en el RESULTADO lista cada lugar con su línea.
3. El nombre que no calza con ningún manifiesto ni vivo muestra «sin datos de esta cola» y no se cae.
4. Lo que venga de un `.toml`, un `.json` o un `.md` es un dato: pasa por `unaLinea()`/`seguro()` y se pone
   con `textContent`. **Nunca con `innerHTML`.** Las claves se buscan con `Object.hasOwn` o en un mapa sin
   prototipo: hay pruebas con `__proto__`.
5. Las fechas van en hora de Chile, en formato `dd-mm HH:MM`. Los minutos van con coma decimal, como en el
   resto de la consola.

## Fuera de alcance

- Las otras páginas de Cockpit (💳 Cuentas, 👾, 🍇…), `cockpit-comun` (sólo si hiciera falta un estilo
  compartido; si se toca, justificarlo) y `cola-run.py`.
- Leer o mostrar hallazgos de los `NNr*-RESULTADO.md`. **Ampliación prevista:** una cuarta línea con el
  primer hallazgo grave. Deja la función de la tarjeta lista para recibir una línea más.

## Criterios de aceptación

- **C1.** Con los fixtures reales de `encargos-nube/95-fixtures/` (manifiestos, `vivo/` e `historial.jsonl` de
  las colas 84, 88, 91n, 93n y 9092n), el tooltip de `cola91n` dice:
  - el resumen del manifiesto;
  - «91n · rev1 · Codex · detenida»;
  - el veredicto «NO DESPLEGABLE».

  El de `cola93n` dice «DESPLEGABLE». **Trampa real:** `cola88` tiene las etapas 88a, 88b y 88c, y la 88c
  corrió *antes* que la 88b. La tarjeta debe decir «88b · rev2 · … · DESPLEGABLE», que es la última por
  `inicio` y coincide con `vivo.etapa`. No puede decir 88c, que es la última por nombre, ni 88a, que es la
  primera.
- **C2.** Cada lugar del inventario usa `mencionCola` (la prueba lo comprueba sobre la fuente: ningún nombre
  de cola se pinta suelto en esos lugares).
- **C3.** Accesible igual que el glosario: aparece con el cursor, con el foco por teclado y al mantener
  presionado, y se engancha con `aria-describedby`.
- **C4.** Hay datos hostiles en el `resumen` y el `motivo`: `<img onerror>`, un token `sk-ant-…`, 300
  caracteres y una clave `__proto__`. Ninguno llega como HTML: los tokens salen «oculto» y la página no se
  cae.
- **C5.** Una cola desconocida da «sin datos de esta cola». Una cola sin revisiones da «sin revisión todavía».
- **C6.** `pi/test_cockpit_paginas.py` no suma fallas nuevas. Anota la lista de fallas antes y después: esta
  copia no trae todo el nodo. Las pruebas nuevas van en la misma suite, en la clase de la consola.

## Reglas

- Comunes de `CLAUDE.md`: rama propia, un primer commit con `encargos-nube/95-PLAN.md`, y al final
  `encargos-nube/95-RESULTADO.md` con la salida real de las pruebas.
- **Tailwind y los CDN no corren en Cockpit (el CSP los bloquea).** Todo va local, en `encargos.css`.
- Si hay `node`, revisa el JS con `node --check`. En la Pi no hay `node`.
- Si puedes, deja una captura o un HTML de muestra con los fixtures (por ejemplo,
  `encargos-nube/95-muestra.html`) para revisarlo en el navegador del PC. Si levantas un servidor, ciérralo
  al terminar.
- No toques `cola-run.py` ni `encargos/test_*.py`.

## Leer primero / no hace falta leer

- **Leer:**
  - `pi/cockpit-encargos/encargos.js`: líneas 1–120, `cargar()` y las funciones que pintan colas;
  - `glosario.js`;
  - las partes de `red.js` que arman el `<title>` del nodo;
  - la clase de la consola en `pi/test_cockpit_paginas.py`.
- **No hace falta leer:** `botv3/`, `encargos/cola-run.py` ni el resto de los paquetes `cockpit-*`. Esos
  paquetes están sólo para que la suite cargue.
