# Encargos en la nube (Claude (Diego))

Este repositorio es una **copia parcial** de `11-Pi5`, el proyecto del nodo Pi5 de Diego. Se armó para
trabajar encargos en la nube con el crédito de sesiones de claude.ai. Fuera de este repositorio no hay
nada: no hay Pi, ni `/opt/nodo`, ni Telegram, ni secretos. Los correos están redactados
(`diego@example.com`, `camila@example.com`). Responde y escribe en español de Chile.

## Qué encargo hacer

El usuario dice cuál. Cada uno tiene su archivo:

| Encargo | Archivo |
|---|---|
| 87, cierre barato (y sus arreglos) | `encargos/87-revision-escalonada.md` + `encargos/87-PLAN.md` |
| 90, `/uso` como imagen | `encargos-nube/90-uso-como-imagen.md` |
| 91, temblores | `encargos-nube/91-temblores.md` |
| 92, contador de uso de los bots | `encargos-nube/92-contador-uso-bots.md` |
| 93, guía de Jaime y Pilar al día | `encargos-nube/93-guia-jaime-pilar.md` |
| 94, 🔎 auditor de rutas (rama base `base-94`) | `encargos-nube/94-auditor-de-rutas.md` |
| 88r, revisión cruzada de Spotify (rama base `base-88r`) | `encargos-nube/88r-revision-spotify.md` |

## Reglas comunes

- **Una rama por encargo**, con commit y push al terminar. Antes de implementar, sube un primer commit
  con el plan (`encargos-nube/<id>-PLAN.md`), porque el contenedor se libera si queda inactivo.
- Al final, deja `encargos-nube/<id>-RESULTADO.md`: lo hecho, los archivos tocados, la salida real de las
  pruebas, las decisiones y los riesgos abiertos. **No inventes resultados**: si una prueba falla, va su
  salida tal cual.
- Las pruebas usan `tempfile` y datos de prueba. Ninguna escribe en `/opt/nodo/...` ni llama a la red
  (la red sirve para **investigar** y para **guardar fixtures reales**, no dentro de las pruebas).
- No se despliega nada: no hay `sudo`, ni `nodo-desplegar`, ni unidades activas. Las unidades systemd nuevas
  quedan como archivos para que se revisen después.
- **No toques** `encargos/cola-run.py` ni `encargos/test_*.py` salvo en el encargo 87.
  `botv3/botv3.py` lo tocan el 90 y el 92: cambia solo lo necesario, en bloques chicos, para que se pueda
  mezclar después.
- Los bots se llaman Jaime (Diego) y Pilar (Camila). Las cuentas se escriben «Claude (Diego)»,
  «Claude (Cami)» y «Codex».
- Cuando el encargo termine, la revisión cruzada (Codex) y el despliegue se hacen en la Pi.

## Cómo correr las pruebas

Desde la raíz, **como las corre la cola**: `NODO_PRUEBAS=1 python3 -B botv3/test_botv3.py` (o la suite que
corresponda). Con `-m unittest`, `botv3/` queda fuera del `sys.path` y salen cientos de errores falsos. Algunas suites fallan por cosas del entorno de esta copia (faltan archivos de la Pi).
Anota la lista de fallas **antes y después** del cambio: tu cambio no puede agregar ninguna.
