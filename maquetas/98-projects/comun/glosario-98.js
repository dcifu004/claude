"use strict";
// Términos de la pestaña Projects (encargo 98). Mismo formato que glosario.js: se suman a window.GLOSARIO.
Object.assign(window.GLOSARIO, {
  "Projects":"Encargos agrupados por proyecto, con su tablero, sus choques de archivos y su flujo en el tiempo.",
  "Board":"Tablero Kanban: una columna por etapa (Idea → Ready → In progress → Review → Done) y una tarjeta por encargo.",
  "WIP limit":"Tope de trabajo en curso de una columna (In progress 2, Review 3). Si se pasa, la cabecera se pone roja.",
  "Cycle time":"Días desde la primera fase de un encargo hasta la revisión que lo dejó DESPLEGABLE.",
  "Throughput":"Encargos que llegan a Done por semana (lunes a domingo, hora de Chile).",
  "Aging":"Días que lleva quieta una tarjeta abierta desde su última fase. Pasado el umbral (7 días) se marca en rojo.",
  "Cumulative flow":"Diagrama de flujo acumulado: cuántos encargos hay en cada etapa al cierre de cada semana.",
  "Now/Next/Later":"Plan sin fechas: lo que se hace ahora, lo que sigue y lo que viene después.",
  "Forecast":"Pronóstico probabilístico: Monte Carlo con el throughput semanal real del proyecto, sobre lo que le falta. Sin datos suficientes no da fechas.",
  "Conflicts":"Mapa proyecto → encargo → archivo: qué encargos abiertos tocan los mismos archivos y en qué orden traerlos."
});
window.GLOSARIO_MAPEO.push(
  ["proyecto (doc + encargos)","Projects","Agrupa encargos por un resultado"],
  ["semana de la cuota","Throughput","Ritmo semanal de encargos terminados"]
);
