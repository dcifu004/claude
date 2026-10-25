# Resultado 90: `/uso` como imagen (Claude (Diego), en la nube, 25-10-2026)

Rama `claude/cool-cannon-ee8axd-90`. Plan en `encargos-nube/90-PLAN.md` (primer commit). Falta la revisión
cruzada (Codex) y el despliegue en la Pi.

## Lo hecho

- **Una sola fuente de datos.** `pi/bots-info.py` ahora deja resuelto todo lo que pinta «⏳ ¿Quién tiene
  margen?»:
  - `capacidad_de(reglas, cid)`: port línea a línea de `cargaDe` de `cuentas.js`;
  - `panel_margen(margen, reglas, ahora)`: con `margen_de` (el de siempre), da por cuenta y ventana el % usado
    y libre, la renovación, la capacidad = uso + carga contra el tope, `sobre_tope` (el rojo), los tramos de
    la barra, la leyenda de colas, «medido hace N min» y «la con más margen». Los textos salen con los mismos
    formatos de `comun.js` (`cuando`, `faltan`, `hace`, `pct`, `n1`), incluido el redondeo de JS;
  - `bots-info --margen`: imprime `{momento, margen, panel, carga_motivo}` y no pide root.
- **Bot.** `botv3/uso_imagen.py` dibuja el panel **sin recalcular**, en el molde de `clima_imagen.py`: puro,
  Pillow adentro y la Lato de `clima_imagen.fuente()` con su respaldo. Usa el tema oscuro de Cockpit, a
  1080 px de ancho, con las tarjetas apiladas para el celular. En `botv3/botv3.py`, en bloques chicos:
  - el import opcional de `uso_imagen`;
  - `("/usr/local/bin/bots-info", "--margen")` en la lista de `safe_command`;
  - `enviar_uso()`: manda la foto con el pie «X es la que tiene más margen…». Si algo falla, manda el texto
    de `uso-agentes --telegram`. Si la foto pudo haber llegado, no manda nada más, como `enviar_clima`;
  - `comando_uso` (y con él `/uso` y el botón 💳 Uso) y `atender_nodo("uso")` («¿cuánta cuota queda?»)
    usan `enviar_uso`.
- **Carga sin ejecutar código del vault.**
  - `pi/panel-cache.py` corre `cola-run.py --panel` como dcifu004, el mismo comando y el mismo usuario que la
    página, y guarda sólo `reglas` en `/opt/nodo/datos/encargos-panel.json`, de forma atómica y con 0644.
  - Lo programan `pi/encargos-panel.service` y `pi/encargos-panel.timer`, unidades de **usuario**, cada 5 min.
    Quedan como archivos sin instalar.
  - `bots-info --margen` da el caché por vencido a los 15 min. Sin caché válido, la imagen sale sin carga y
    lo dice, igual que la página cuando `--panel` falla.

## Archivos tocados

- Modificados: `pi/bots-info.py` (+257) y `botv3/botv3.py` (+42 −1, 4 bloques).
- Nuevos:
  - código: `botv3/uso_imagen.py`, `pi/panel-cache.py`, `pi/encargos-panel.service` y `pi/encargos-panel.timer`;
  - pruebas: `botv3/test_uso_imagen.py` y `pi/test_margen_panel.py`;
  - fixtures en `pi/fixtures/cuentas/`: `margen-normal.json`, `margen-pasado.json`, `cargaDe-js.json` y
    `genera-cargaDe-js.mjs`;
  - muestras: `encargos-nube/90-muestras/` (`uso-normal.png`, `uso-pasado-del-tope.png` y `genera.py`);
  - `encargos-nube/90-fallas-antes-despues.txt`.

## Decisiones

- **No se cambió `cuentas.js`.** Para que la página usara el cálculo de Python, `bots-info`, que es root,
  tendría que correr `cola-run.py`, y eso es código del vault que escriben los agentes. En vez de eso, el
  port se prueba contra el `cargaDe` de verdad:
  - `genera-cargaDe-js.mjs` corre `cuentas.js` con node (en un `vm`) sobre los mismos fixtures;
  - la prueba compara contra `cargaDe-js.json` y, si hay node, vuelve a correrlo en vivo y falla si
    `cuentas.js` cambió.

  En la Pi no hay node, así que ahí vale la salida guardada.
- **Fixtures:**
  - `uso` son los límites del `uso.json` real (`pi/fixtures/avisos/uso-real.json`);
  - `reglas` tienen la forma real de `--panel` (copiada de `pi/fixtures/encargos/panel-46a-56b.json`), con
    `actual` igual al uso medido para que la imagen sea coherente;
  - en «pasado», Claude (Diego) pasa el tope en las dos ventanas.
- **Formato de la imagen:** tarjetas apiladas, una por cuenta, y no tres columnas como el escritorio, porque
  en el teléfono se leen mejor. Se ordenan como la página (`margen.orden`).
  - El título va sin «⏳», porque Lato no trae emojis.
  - «↻ desde las HH:MM» se dibuja como «Desde las HH:MM».
- Por voz, «¿cuánta cuota queda?» deja la imagen en el chat y no habla, como antes con el texto («sólo
  escrito», decisión del 19-10).

## Pruebas

Comando: `NODO_PRUEBAS=1 python3 -B -m unittest <suite>.py`, desde la raíz. Salida real:

```
== botv3/test_uso_imagen
Ran 13 tests in 5.706s
OK
== pi/test_margen_panel
Ran 14 tests in 0.131s
OK (skipped=1)
== botv3/test_botv3
Ran 490 tests in 15.996s
FAILED (failures=49, errors=156, skipped=113)
== botv3/test_clima_imagen
Ran 45 tests in 4.114s
OK (skipped=1)
== pi/test_cuentas_uso
Ran 74 tests in 1.486s
FAILED (failures=1, errors=9, skipped=4)
== pi/test_uso
Ran 7 tests in 0.129s
OK
```

- **Sin fallas nuevas.** Las listas `ERROR:`/`FAIL:` de las 4 suites obligatorias son idénticas antes y
  después (`diff` vacío). La lista exacta está en `encargos-nube/90-fallas-antes-despues.txt`: 205 de
  `test_botv3` y 10 de `test_cuentas_uso`.
- **Las fallas previas son del entorno de esta copia.**
  - En `test_botv3`, 47 por `CASA_DIR` de `compras` en `None`, 42 por «temporizadores.py no se pudo
    importar», 34 por `puente` de Mercado Libre, 10 por `tiene_sesion` y 13 por archivos de la Pi que faltan.
    Desde la raíz, `botv3/` no está en `sys.path`, así que esos módulos no cargan.
  - En `test_cuentas_uso`, 9 por archivos que faltan y una aserción `95 != 90`, que también falla en la línea
    base.
- **Qué cubren las nuevas:**
  - el port es igual a `cargaDe` (guardado y en vivo con node);
  - los números del panel coinciden con `margen_de` y con la carga (71,2 = 41 + 30,2; 95,1 > 90 en rojo);
  - redondeo de JS, barra de siempre sin carga y cola con nombre raro → «oculto»;
  - caché fresco, vencido, roto o ausente;
  - `--margen` entrega JSON sin escribir nada;
  - `panel-cache` es atómico, deja 0644 y no toca el caché si `--panel` falla;
  - PNG de 1080 px de ancho, con más rojo cuando se pasa el tope;
  - la imagen no recalcula;
  - sin Lato usa la letra de Pillow;
  - el respaldo a texto (sin módulo, sin Pillow, bots-info que falla, JSON roto, sin panel, sendPhoto 400),
    la foto ambigua que no se duplica, «¿cuánta cuota queda?» igual a `/uso` y el `safe_command` estricto.
- La prueba «`--margen` no pide root» se salta aquí porque el contenedor corre como root. En la Pi corre.

## Riesgos abiertos

- **Despliegue (en la Pi):**
  - instalar `bots-info` nuevo y `uso_imagen.py` en `/opt/botv3`;
  - instalar `panel-cache.py` y su timer de usuario, que necesita linger, como los timers de las colas.
- **Permisos por confirmar:**
  - que `botjaime` y `botpilar` puedan ejecutar `/usr/local/bin/bots-info --margen` y leer `uso.json`,
    `/opt/botv3/cuentas.toml` y `encargos-panel.json`;
  - Pilar no ve el vault, pero el caché vive en `/opt/nodo/datos`;
  - si algo de eso falla, `/uso` manda el texto de hoy.
- `cola-run.py --panel` corrido desde una unidad de usuario usa el bus de usuario para los timers. Si el bus
  no está, la matriz igual sale, pero conviene mirarlo en el journal la primera vez.
- Las muestras se dibujaron con Lato sacada de npm (`lato-font`), sólo en este contenedor. En la Pi se usa la
  del sistema (`/usr/share/fonts/truetype/lato`).

## Qué cambiar en la guía (doc 35, lo hace el 93)

- Fila «💳 Uso de cuotas»: `/uso`, el botón 💳 Uso y la frase «¿cuánta cuota queda?» ahora mandan una
  **imagen** de «¿Quién tiene margen?» (las tres cuentas, 5 h y semana, la capacidad con la carga de las colas
  y el tope en rojo si se pasa), con una línea que dice cuál tiene más margen. Si la imagen no sale, llega el
  texto de antes.
- Agregar que es la misma información de la página 💳 Cuentas de Cockpit y que por voz no se lee en voz alta.
