# Plan 93: guía de uso de Jaime y Pilar al día

> Nota: este plan se escribió y se subió **después** de hacer el inventario, aunque va en el primer commit de la
> rama. Lo dice también el RESULTADO.

## Enfoque

1. **Inventario contra el código.** Lo que hace cada bot hoy:
   - del despachador (`handle_message`/`handle_callback`), `AREAS_MENU`, `HELP` y sus bloques condicionales en
     `botv3/botv3.py`;
   - de los comandos publicados (`update_telegram_commands.py`) y los perfiles (rutas, vaults, Drive, clima);
   - de las constantes de `temporizadores.py`, `boleta.py` y la tabla de comunas.
   - De ahí salen los comandos, los botones, las frases, la voz, lo que pide ✅ y las diferencias entre Jaime y
     Pilar.
2. **Diferencias:** una tabla en `93-RESULTADO.md` con lo que la guía dice y ya no es así, lo que falta y lo que
   describe sin que el código lo tenga, cada fila con archivo:línea.
3. **Guía nueva:** se reescribe el `.md` y se regenera el `.html` **desde una sola lista de filas**, para que no
   diverjan (hoy ya discrepan en Buscar).
   - Mismo estilo y tono, sin rutas internas ni nombres de archivos.
   - Una sección «Pilar (Camila)».
   - Lo apagado o a medias (Mercado Libre; Spotify no existe) va a «Próximamente» o no va.
4. Se describe **lo de hoy**: `/uso` en texto y sin `/usos`. El 90 y el 92 agregan lo suyo después.
5. **Verificación:** el `.html` sin CDN y sin scroll horizontal a 375 px (Chromium, tema claro y oscuro).

No se toca código. Si aparece un error en el bot, se anota en el RESULTADO.
