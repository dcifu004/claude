# Encargo 87 en la nube (Claude (Diego))

Esta es una copia parcial de `11-Pi5` (proyecto del nodo Pi5 de Diego), hecha solo para el
encargo 87. Fuera de este repositorio no hay nada: no hay Pi, ni `/opt/nodo`, ni Telegram, ni
secretos. Responde y escribe en español de Chile.

## Qué hacer

1. Lee `encargos/87-revision-escalonada.md` (el encargo), `encargos/87-PLAN.md` (el plan) y
   `encargos/87rplan-RESULTADO.md`. La revisión del plan lo **rechazó**.
2. Corrige el plan según los hallazgos H1–H4 y deja la versión nueva en `encargos/87-PLAN.md`. Al
   final, agrega una sección «Respuesta a 87rplan» que diga hallazgo por hallazgo qué se cambió.
3. Implementa el plan corregido: `cierre_barato = true`, con alcance mínimo. Sin ese campo, la cola
   tiene que portarse exactamente como hoy.
4. Corre las pruebas de `encargos/cola-87.toml` (`pruebas = [...]`) con `python3 -B -m unittest`,
   desde la raíz.
5. Escribe `encargos/87-RESULTADO.md` con lo hecho, los archivos tocados, la salida de las pruebas
   y los riesgos abiertos.

## Reglas

- **No se modifican** `encargos/revision-plantilla-v2.md`, `encargos/historial.jsonl` ni
  `encargos/modelos.toml` (salvo que el plan lo exija y lo justifique).
- Las pruebas usan `tempfile` y repos git temporales. Ninguna prueba escribe en rutas fijas
  (`/opt/nodo/...`) ni llama a la red.
- `despliegue = "nada"`: no se pide despliegue ni se agregan unidades systemd.
- Se quitó `test_buscar_web.py` porque tenía datos reales. No lo recrees.
- No inventes resultados: si una prueba falla, deja la salida tal cual en el RESULTADO.
- Después, la revisión cruzada (Codex o Claude (Cami)) corre en la Pi. Trabaja en una rama propia
  y deja todo commiteado.
