# Encargo 93: guía de uso de Jaime y Pilar al día (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `documentación`. Diego lo aprobó el 25-10.

## Qué se pide

La guía `docs/35 - Guía de uso de Jaime y Pilar.md` (y su `.html`) es lo que Diego y Camila leen para
saber qué hacen los bots. Se quedó atrás. Hay que ponerla al día **contra el código**, no contra la memoria:

1. **Inventario** de lo que hacen hoy los bots, sacado de `botv3/botv3.py`,
   `botv3/update_telegram_commands.py`, `botv3/perfiles/*.toml`, `botv3/compras.py`,
   `botv3/temporizadores.py`, `botv3/agenda_correo.py`, `botv3/boleta.py`, `botv3/clima_imagen.py` y
   `botv3/recetas.py`: comandos, botones de `/menu`, frases libres que se entienden, voz, qué tiene
   Jaime y no Pilar (y al revés) y qué pide confirmación ✅.
2. **Diferencias:** una tabla en `encargos-nube/93-RESULTADO.md` con lo que la guía dice y ya no es así, lo
   que falta en la guía y lo que la guía describe y el código no tiene. Cada fila lleva archivo:línea.
3. **Guía nueva:** reescribe el `.md` y regenera el `.html`. Mantén el estilo y el tono de la guía actual:
   para una persona que no programa, con ejemplos de frases reales y sin rutas internas ni nombres de
   archivos. Separa lo que es de Pilar (Camila).
4. Lo que está a medias o apagado (por ejemplo, Spotify o Mercado Libre) va en «Próximamente» o no va. No
   lo prometas como si ya funcionara. Lo dudoso lo marcas en el RESULTADO para que Diego decida.

## Reglas

- No cambies código. Si encuentras un error en el bot, anótalo en el RESULTADO y nada más.
- Los encargos 90 (`/uso` como imagen) y 92 (contador) van en paralelo: describe el comportamiento de
  **hoy**, porque después ellos agregan su parte.
- El `.html` es autocontenido (sin CDN) y se ve bien en el celular a 375 px.
