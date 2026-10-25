# Encargo 88r: revisión cruzada de la 88 (Spotify por perfil), escrita por Codex (Claude (Diego) en la nube, 25-10-2026)

**Aquí no se escribe código.** Eres el **revisor**. La 88 la escribió Codex en la Pi, y la 88b y la 88c se las
revisó el mismo Codex (autorrevisión). Esta es la primera revisión de **otro motor** antes de desplegarla. La
pidió Diego el 25-10. Rama base: `base-88r`.

## Qué es la 88

Dos receptores Spotify Connect (`go-librespot` v0.10.5), uno por perfil (Jaime = cuenta de Diego, Pilar =
cuenta de Camila), y el bot que entiende frases de música y controla el receptor de su perfil.

- **88a** (receptores, unidad, plantillas, cambios a `nodo-desplegar`): `encargos/88a-spotify-receptores.md`,
  `88a-decisiones.md`, `88a-RESULTADO.md`. Tuvo tres revisiones de Claude (Diego), `88ar1–3-RESULTADO.md`, y
  quedó NO DESPLEGABLE.
- **88c** (arreglo de lo que dejó la rev3 de la 88a): `encargos/88c-spotify-arreglo-rev3.md`,
  `88c-RESULTADO.md`, `88cr-RESULTADO.md` (Codex se autorrevisó: DESPLEGABLE).
- **88b** (intención en el bot): `encargos/88b-spotify-intencion-bot.md`, `88b-RESULTADO.md`, `88br*-RESULTADO.md`
  (Codex se autorrevisó: DESPLEGABLE en la rev2).
- **Diffs reales de cada etapa:** `encargos-nube/88r-diffs/cola88-88a-diff.txt`, `-88b-` y `-88c-`.
- **Código:** `pi/spotify/` (LEEME, `spotify@.service`, `config-*.yml`, `test_plantillas.py`, fixtures de esquema),
  `pi/nodo-desplegar.py` + `pi/test_nodo_desplegar.py` + `pi/desplegar-escucha.service` (cambios de la 88a y la 88c),
  `pi/cargar-clave.py`, `botv3/spotify.py` + `botv3/test_spotify.py`, la parte de Spotify de `botv3/botv3.py`,
  `botv3/update_telegram_commands.py` y el bloque `spotify` de `botv3/perfiles/*.toml`.
- El binario (`go-librespot-v0.10.5-linux-arm64`, 17 MB) **no se subió**. Su SHA-256 está en `88c-RESULTADO.md`.
  Si quieres, compáralo con el de la release oficial (la red de esta sesión puede estar limitada).

## Qué mirar (sobre todo seguridad: corre como servicio y toca `nodo-desplegar`, que es root)

1. **`nodo-desplegar`:** cada cambio de la 88a y la 88c (`RE_FUENTE` con `@`, `alta-enlace`, el tope de tamaño
   por el binario). Que no abran rutas absolutas, `..`, enlaces simbólicos ni escritura fuera de lo previsto, y que
   el ✅ siga ligado al texto exacto.
2. **La unidad `spotify@.service`:** el aislamiento (usuario, `ReadWritePaths`, `ProtectSystem`, red), que cada
   instancia solo vea lo de su perfil, y que el bootstrap del LEEME sea correcto y completo. Ya falló una vez.
3. **El bot (`spotify.py` y `botv3.py`):** que la API sea solo `127.0.0.1` y el puerto propio, que Pilar no
   pueda controlar el receptor de Jaime (solo «pausar el otro»), que las frases no le roben intenciones a otras
   funciones y que no se filtren tokens ni textos en logs y errores.
4. **Las autorrevisiones:** relee `88cr` y `88br*`. ¿Hay algo que Codex dio por bueno y no lo está? ¿Algún
   hallazgo de la 88ar3 quedó sin cerrar de verdad?
5. **Pruebas:** corre desde la raíz, como la cola: `python3 botv3/test_spotify.py`, `python3 botv3/test_botv3.py`,
   `python3 pi/test_nodo_desplegar.py` y `python3 pi/spotify/test_plantillas.py`. Anota qué falla por el entorno
   (sin systemd ni `/opt/nodo`) y qué falla de verdad.

## Entrega

`encargos-nube/88r-RESULTADO.md` en el formato de las revisiones de la cola:
- hallazgos de más grave a menos grave, **[Grave] / [Media] / [Menor]**, cada uno con archivo:línea, cómo
  reproducirlo y el arreglo propuesto;
- «Lo que revisé y está bien»;
- una última línea exacta: `VEREDICTO: DESPLEGABLE` o `VEREDICTO: NO DESPLEGABLE`.

No cambies código: si ves un arreglo, descríbelo. Commit y push en una rama nueva creada desde `base-88r`.
