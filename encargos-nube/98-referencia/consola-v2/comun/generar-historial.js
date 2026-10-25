"use strict";
const fs = require("node:fs");
const path = require("node:path");
const source = path.resolve(__dirname, "..", "datos-pi", "historial.jsonl");
const target = path.resolve(__dirname, "historial-data.js");
const rows = fs.readFileSync(source, "utf8").trim().split(/\r?\n/).map(JSON.parse).map(x => ({
  encargo: String(x.encargo), fase: x.fase, rol: x.rol, cuenta: x.cuenta,
  modelo: x.modelo || x.modelo_real || x.motor, esfuerzo: x.esfuerzo || "",
  naturaleza: x.naturaleza || "sin datos", inicio: x.inicio, min: x.min || 0,
  sin_cuota: x.sin_cuota === true, veredicto: x.veredicto || null
}));
fs.writeFileSync(target, `"use strict";\nwindow.HISTORIAL=${JSON.stringify(rows)};\n`, "utf8");
console.log(`historial-data.js: ${rows.length} fases`);
