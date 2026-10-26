# Encargo 88e + 92c: cerrar las revisiones rechazadas de Spotify (88dn) y del contador (92bn) (Claude (Diego) en la nube, 26-10-2026)

Esta rama (`base-88e`) parte del 88d y trae el `botv3/` **tal como está hoy en el vault** (con 96, 97 y 101 encima),
más `pi/spotify-web/` (encargo 100, aprobado). Los correos van tapados (`<correo-…>`): no los toques.

Lee enteras, antes de tocar nada, las dos revisiones:

- `encargos-nube/88dnr1-RESULTADO.md` (Claude (Cami), NO DESPLEGABLE);
- `encargos-nube/92bnr1-RESULTADO.md` (Codex, NO DESPLEGABLE).

**Los números de línea de las revisiones son del 25-10: `botv3.py` cambió desde entonces. Ubica cada punto por
nombre de función o por el texto citado, no por línea.**

## Alcance cerrado: cuatro arreglos, nada más

1. **88dn hallazgo 1 [Media], la unidad propuesta:** en `encargos-nube/88d-spotify@.service.propuesta`, mantener
   `ProtectHome=tmpfs`, agregar `BindReadOnlyPaths=%t/pulse` y corregir el comentario falso (`ProtectHome` **sí**
   tapa `/run/user`). Sólo el archivo de propuesta; no se activa nada.
2. **88dn hallazgo 2 [Media], «sigue» a secas con el receptor propio caído:** en `atender_spotify`, la rama de error
   del `/status` propio debe devolver `False` (la frase sigue como conversación) cuando `inicial` viene con `sola`,
   igual que hoy pasa con «pausa» a secas. Suma el caso a `test_hallazgo_5_sigue_a_secas_solo_en_pausa` o a una
   prueba vecina en `botv3/test_spotify.py`, incluida la variante «Jaime, continúa».
3. **88dn hallazgo 3 [Media], posesivos después del segundo «de»:** en `botv3/spotify.py`, buscar el posesivo (y
   las palabras de tiempo, sumando «anoche» y «recién») en **cualquier** « de <palabra> » de la frase, no sólo al
   comienzo de `group(2)`. Suma a `NO_88D` «reproduce la nota de voz de mi mamá», «reproduce la canción de cuna de
   mi hija» y «reproduce la grabación de anoche». Las canciones que hoy pasan tienen que seguir pasando
   («Tren al sur de Los Prisioneros», «Mentira de La Ley», «Mi Gente de J Balvin», «Hoy de Gloria Trevi»).
4. **92bn hallazgo 1 [Grave], `test_contador.py` en rojo con Spotify presente:** en el `setUp` de
   `botv3/test_contador.py`, simular las funciones de `spotify_mod` que usa `/spotify` (como mínimo `estado`, y
   `codigo` si el camino lo toca) y afirmar la llamada. **La guarda de red se queda** como última barrera. La suite
   tiene que quedar verde **con `botv3/spotify.py` importable y el bloque `spotify` de los perfiles**, que es la
   forma real (en esta rama lo están).

**Fuera de alcance:** los hallazgos 4 y 5 de la 88dn ([Baja]: artículos, y «sigue» sin pausar el otro). No los
toques; anótalos como pendientes. No refactorices, no cambies nombres, no toques `cola-run.py`, `pi/` (salvo leer)
ni nada de 96, 97 o 101. Cambios en bloques chicos.

## Pruebas (desde la raíz, como la cola)

Antes y después de los cambios, guarda la salida en `encargos-nube/88e-fallas-antes-despues.txt`:

```bash
python3 botv3/test_spotify.py
python3 botv3/test_contador.py
python3 botv3/test_botv3.py
python3 botv3/test_sala.py
python3 botv3/test_selectores.py
python3 botv3/test_bluetooth.py
python3 pi/spotify-web/test_spotify_web.py
```

Las fallas que ya estaban antes por el entorno de la nube no cuentan; una falla **nueva** sí. Para el hallazgo 3,
pasa también por `interpretar(…, False)` y `interpretar(…, True)` las cadenas literales de las suites de `botv3/`,
como hizo la revisión: **0 capturas nuevas**.

## Entrega

- `encargos-nube/88e-RESULTADO.md`: qué cambió por cada uno de los 4 puntos (archivo y función), las pruebas
  nuevas, el antes y después de las suites y los pendientes (4 y 5 de la 88dn).
- Commit y push en una rama nueva creada desde `base-88e`.
- La revisión cruzada y el despliegue los hace la Pi; tú no despliegas nada.
