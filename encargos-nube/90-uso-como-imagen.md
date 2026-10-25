# Encargo 90: `/uso` como imagen (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `bot`. Idea de Diego del 23-10, aprobada el 25-10 para hacerla en la nube.

## Qué se pide

Que `/uso` en Jaime (y en Pilar, si hoy lo tiene) mande una **imagen** del bloque «⏳ ¿Quién tiene
margen?» de la página 💳 Cuentas de Cockpit, en vez del texto que manda hoy (`comando_uso` →
`uso-agentes --telegram`, en `botv3/botv3.py` ~7661; `uso-agentes` = `pi/uso.py`).

Referencia visual: `docs/08b - Referencia uso como imagen (panel margen).png`. La imagen tiene que mostrar:
- las tres cuentas (Codex, Claude (Cami), Claude (Diego)), cada una con la ventana de 5 h y la semanal;
- el % usado y el libre;
- la **capacidad = uso + carga comprometida**, contra el tope (en rojo si lo pasa);
- la barra con la carga rayada y la marca del tope;
- cuándo renueva cada ventana y qué colas comprometen carga;
- cuántos minutos tiene la medición y la etiqueta «la con más margen».

## Reglas

- **Una sola fuente de datos.** Los números salen del mismo cálculo que pinta Cockpit: `pi/bots-info.py`
  y `pi/cockpit-cuentas/cuentas.js`. La imagen no recalcula por su cuenta, porque si no el bot y el panel
  terminan discrepando. Si hace falta, expón ese cálculo como función o salida JSON y úsalo desde los dos lados.
- **Molde:** la imagen del botón 🌦️ Clima (`botv3/clima_imagen.py`, Pillow + Lato, y sus pruebas en
  `botv3/test_clima_imagen.py`). Reusa su manera de cargar la fuente y su respaldo sin Pillow.
- Si la imagen falla, se manda el texto de hoy, sin perder la respuesta. La frase libre «¿cuánta cuota
  queda?» tiene que dar lo mismo que `/uso`.
- Pruebas: con datos fijos (fixtures de `pi/fixtures/cuentas/`), la imagen se genera, tiene el tamaño
  esperado y los números coinciden con los del cálculo de Cockpit. Cubre el respaldo a texto y el rojo
  cuando se pasa el tope. Guarda en `encargos-nube/90-muestras/` dos PNG de muestra (normal y pasado del
  tope) para que Diego los vea.
- Suites que no pueden quedar con fallas nuevas: `botv3/test_botv3.py`, `botv3/test_clima_imagen.py`,
  `pi/test_cuentas_uso.py` y `pi/test_uso.py`.
- No actualices la guía (doc 35). Eso es del 93, que está aparte: anota en el RESULTADO qué habría que
  cambiar en ella.
