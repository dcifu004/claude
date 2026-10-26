# Encargo 88e + 92c: PLAN

Rama `claude/encargo-88e-92c-arreglos`, creada desde `base-88e` (`a23ea8e`). El alcance está cerrado: son cuatro
arreglos, en bloques chicos.

1. **88dn h1:** en `encargos-nube/88d-spotify@.service.propuesta`, mantener `ProtectHome=tmpfs`, agregar
   `BindReadOnlyPaths=%t/pulse` y corregir el comentario: `ProtectHome` sí tapa `/run/user`.
2. **88dn h2:** en `botv3/botv3.py`, `atender_spotify`. En la rama de error del `/status` propio, devolver `False`
   cuando `inicial` viene con `sola`. La prueba va en `botv3/test_spotify.py`, junto a
   `test_hallazgo_5_sigue_a_secas_solo_en_pausa`, con «sigue», «continúa», «reanuda» y «Jaime, continúa».
3. **88dn h3:** en `botv3/spotify.py`, `interpretar`. Buscar el posesivo y las palabras de tiempo (sumando «anoche» y
   «recién») en cualquier « de <palabra> » de la frase. Sumar las tres frases de la revisión a `NO_88D`. Pasar las
   cadenas literales de las suites de `botv3/` por `interpretar(…, False/True)` antes y después: tiene que dar 0
   capturas nuevas.
4. **92bn h1:** en `botv3/test_contador.py`, que el `setUp` simule `spotify_mod.estado` y `spotify_mod.codigo` y
   que la prueba afirme la llamada desde `/spotify`. La guarda de red se queda.

## Línea base

Las 7 suites, desde la raíz y con `NODO_PRUEBAS=1` y el estado en un `mktemp -d`. Aquí no está `rapidfuzz`, así que
las corro de dos formas: con la copia del scratchpad (`PYTHONPATH`), que deja `spotify.py` importable y es la forma
real, y sin ella. La salida va en `88e-fallas-antes-despues.txt`.

- **Con `rapidfuzz`:** `test_contador` FAILED (1), por `socket.getaddrinfo ('127.0.0.1', 3678)`. Es el hallazgo 4.
- **Del entorno, igual con y sin `rapidfuzz`:**
  - `test_botv3`: 7 fallas y 34 errores (root, credenciales, fixtures de la Pi);
  - `test_selectores`: 1 error (`bots_info` viejo);
  - `test_bluetooth`: no se importa (falta `encargos/fixtures/101`).
- **OK:** `test_spotify`, `test_sala` y `test_spotify_web`.
