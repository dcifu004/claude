# Plan 90: `/uso` como imagen

## Enfoque

Una sola fuente de datos. `bots-info` ya calcula el margen por cuenta (`margen_de`, con la misma
`recetas.elegir_orden` del bot). Lo que la página suma encima, la carga comprometida de las colas, hoy vive sólo
en `cuentas.js` (`cargaDe`/`barraVentana`). Ese cálculo pasa a `pi/bots-info.py` como función pura, y el bot
pinta lo que devuelve, sin recalcular nada:

- `capacidad_de(reglas, cid)`: port de `cargaDe` (uso, carga, tramos por cola, «↻ desde las HH:MM»).
- `panel_margen(margen, reglas, ahora)`: todo lo que pinta «⏳ ¿Quién tiene margen?», ya resuelto. Por cuenta y
  ventana trae: % usado y libre, renovación («sáb 24-10 02:32 (en 4 h 12 min)»), capacidad = uso + carga, tope,
  `sobre_tope` (el rojo), los tramos para la barra, las colas de la leyenda, «medido hace N min» y la cuenta
  con más margen. Los textos usan los mismos formatos que `comun.js` (`cuando`, `faltan`, `hace`, `pct`, `n1`).
- `bots-info --margen`: imprime `{momento, panel}` en JSON. No pide root, porque sólo lee `cuentas.toml`,
  `uso.json` y `recetas.py`. Así lo puede llamar el bot.

**Por qué no se cambia `cuentas.js`:** la página saca la carga con `cola-run.py --panel` como dcifu004. Si
`bots-info` (root) o el bot ejecutaran `cola-run.py`, estarían corriendo código del vault, que escriben los
agentes. En su lugar:
- una prueba fija que el port en Python da **lo mismo** que `cargaDe` de `cuentas.js`, corrido con node sobre
  los mismos fixtures (la salida de node queda guardada como fixture, porque en la Pi no hay node);
- el bot lee `reglas` de un caché, `/opt/nodo/datos/encargos-panel.json`, que escribe `pi/panel-cache.py`
  como dcifu004 con el mismo comando de la página. Lo programan `pi/encargos-panel.service` y
  `pi/encargos-panel.timer`, cada 5 min, que quedan como archivos sin instalar.
- Si el caché falta, está roto o tiene más de 15 min, la imagen sale sin carga, como la página cuando
  `--panel` falla.

## Bot

- Nuevo `botv3/uso_imagen.py`, siguiendo el molde de `clima_imagen.py`: puro, Pillow importado adentro y
  `clima_imagen.fuente()` para Lato y su respaldo. `tarjeta_png(panel) -> bytes`, en tema oscuro como la
  referencia: tres tarjetas, cada una con 5 h y semana, barra con la carga rayada y la marca del tope, y en
  rojo si pasa el tope.
- En `botv3.py`, en bloques chicos:
  - `safe_command` acepta `("/usr/local/bin/bots-info", "--margen")`;
  - `enviar_uso(chat_id)` manda la foto con un pie de una línea («Codex es la que tiene más margen…»). Ante
    cualquier falla (sin módulo, sin Pillow, JSON roto, sendPhoto rechazado) manda el texto de hoy. Si la
    foto pudo haber llegado, no manda nada más, igual que `enviar_clima`;
  - `comando_uso` y `atender_nodo("uso")` usan `enviar_uso`. Así `/uso`, el botón 💳 Uso y «¿cuánta cuota
    queda?» dan lo mismo.

## Pruebas (`pi/test_margen_panel.py` y `botv3/test_uso_imagen.py`)

Fixtures nuevos en `pi/fixtures/cuentas/`:
- `margen-normal.json`: `limites` del `uso.json` real (`pi/fixtures/avisos/uso-real.json`) y `reglas` del panel
  real (`pi/fixtures/encargos/panel-46a-56b.json`);
- `margen-pasado.json`: el mismo caso, con una cuenta sobre el tope;
- `cargaDe-js.json`: la salida de node con el `cuentas.js` real.

Qué cubren:
- el port coincide con `cargaDe` (y, si hay node, se vuelve a correr en vivo);
- los números de `panel_margen` coinciden con `margen_de`;
- la imagen es un PNG de 1080 px de ancho y alto según el contenido;
- el rojo aparece cuando la capacidad pasa el tope y no aparece cuando no;
- sin Pillow, con JSON roto o con sendPhoto rechazado, sale el texto de hoy;
- la frase «¿cuánta cuota queda?» manda lo mismo que `/uso`;
- un caché viejo o roto da una imagen sin carga.

Muestras: `encargos-nube/90-muestras/uso-normal.png` y `uso-pasado-del-tope.png`. Sin fallas nuevas en
`botv3/test_botv3.py`, `botv3/test_clima_imagen.py`, `pi/test_cuentas_uso.py` y `pi/test_uso.py`. Línea base:
`test_botv3` 49 F + 156 E, `test_clima_imagen` OK, `test_cuentas_uso` 1 F + 9 E, `test_uso` OK.

## Riesgos que se anotarán

- En la Pi hay que instalar `bots-info` con `--margen` y el timer del caché.
- Falta confirmar que el usuario de cada bot lee `uso.json` y el caché (Pilar no ve el vault, pero el caché va
  en `/opt/nodo/datos`).
- La guía (doc 35) se actualiza en el 93.
