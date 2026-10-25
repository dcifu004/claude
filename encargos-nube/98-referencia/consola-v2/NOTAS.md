# Consola v2 — notas de la maqueta (ronda 2)

## Qué se ve

- **🏠 Home:** estado del nodo e Inbox resumida. **🏭 AI Ops:** Flow, Runs, Approvals (HITL), Timeline, Traces, Scorecard, Logs y Policies.
- **Flow:** abre en Todo con la red completa de cinco capas (cuenta → modelo · esfuerzo → naturaleza · rol → encargo → resultado). Los alcances En curso, Encargo, Naturaleza y Cuenta actualizan red, KPI y hash. Encargo agrega arriba el pipeline hecho/corriendo/pronosticado.
- **⛽ Providers:** Usage & Limits y Capacity con datos del panel; Model Routing y Quota Burn-down livianos.
- **👷 Agents:** Registry primero, con 24 fichas de ejemplo filtrables por familia y estado; además Sessions, Assistants, Change Requests y Memory health.
- **🍇 Infrastructure:** Services, Backups, Schedules y Signals. **📰 News:** Digest, Sources y Delivery. El riel de Cockpit se expande a 200 px sobre el contenido con hover o foco; también permite comparar modo fijo.

## Vocabulario

| Hoy | Industria | Definición corta |
|---|---|---|
| encargo | Task | Especificación de una tarea |
| cola | Run | Corrida concreta del pipeline |
| autor → rev → fix | Steps | Pasos del workflow de agentes |
| revisión cruzada | Cross-model review | Otro modelo evalúa al autor |
| pedido de despliegue | Release gate | Compuerta antes de producción |
| avisos | Inbox | Bandeja que requiere atención |
| retrabajo | Rework rate | Minutos en arreglar y revisar de nuevo |
| precisión del pronóstico | Estimation error | Desvío entre pronóstico y realidad |
| reparto | Model Routing | Selección de cuenta y modelo |
| Memoria | Memory health | Salud de índice, enlaces y vigencia |

Las definiciones, incluidas Worker y Orchestrator, viven sólo en `comun/glosario.js` y aparecen en el panel Glosario y en el tooltip accesible.

## Datos reales y ejemplos

- **Reales:** las 360 fases completas de `datos-pi/historial.jsonl`, transformadas sin texto libre a `comun/historial-data.js`; Traces 84; Scorecard; cuentas y capacidad de `panel.json`; Memory health sólo con nombres y conteos.
- **Simulados / ejemplo:** `cola84` activa con `fases_restantes`, Approvals, Registry y los paneles livianos. Todo está rotulado como simulado, ejemplo o propuesta visual.
- La red conserva el arco ámbar de retrabajo, modos Ambiente/Foco/En vivo, pausa de luces, tope de 120 y `prefers-reduced-motion`.

## Para llevarlo a Cockpit

- Integrar la barra y el riel con el shell real; reemplazar `datos.js` y `historial-data.js` por endpoints autenticados.
- Pasar a la adaptación los vivos y sesiones reales, manteniendo hash, foco, límites de luces y scroll propio.
- Conectar Traces con RESULTADO/COLA-ESTADO, Registry con una fuente canónica de configuración y Approvals sólo con enlaces profundos, nunca acciones directas.
- Ejecutar Memory health en la Pi sólo con LUKS abierto y probar `obsidian://… target="_top"` dentro del iframe real.

## Dudas abiertas

- Confirmar si el chip superior debe mostrar capacidad disponible (usada aquí) o consumo.
- Definir la fuente canónica del Registry y de los hallazgos de Traces.
- Confirmar si los asistentes de casa identificados por nombre deben seguir visibles en el catálogo real o reemplazarse por roles.
