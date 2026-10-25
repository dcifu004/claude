// Corre `cargaDe` del cuentas.js REAL sobre las `reglas` de margen-*.json y guarda la salida en
// cargaDe-js.json (encargo 90). En la Pi no hay node: test_margen_panel.py compara el port en Python
// contra este archivo y, si encuentra node, lo vuelve a correr en vivo.
//
//     node pi/fixtures/cuentas/genera-cargaDe-js.mjs            # escribe cargaDe-js.json
//     node pi/fixtures/cuentas/genera-cargaDe-js.mjs --stdout   # solo imprime
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const aqui = path.dirname(fileURLToPath(import.meta.url));
const js = fs.readFileSync(path.join(aqui, "..", "..", "cockpit-cuentas", "cuentas.js"), "utf8");
const nodo = () => ({ addEventListener() {}, replaceChildren() {}, querySelectorAll: () => [] });
const contexto = vm.createContext({
    document: { getElementById: nodo, querySelectorAll: () => [], addEventListener() {} },
    cockpit: { transport: { wait() {} }, spawn: async () => "{}" },
    console,
});
vm.runInContext(js, contexto, { filename: "cuentas.js" });
const salida = {};
for (const caso of ["normal", "pasado"]) {
    const f = JSON.parse(fs.readFileSync(path.join(aqui, `margen-${caso}.json`), "utf8"));
    contexto.__reglas = f.reglas;
    salida[caso] = vm.runInContext(
        "cargaColas = __reglas; Object.fromEntries(['codex', 'claude_cami', 'claude_diego', 'otra'].map(c => [c, cargaDe(c)]))",
        contexto);
}
const texto = JSON.stringify(salida, null, 1) + "\n";
if (process.argv.includes("--stdout")) process.stdout.write(texto);
else fs.writeFileSync(path.join(aqui, "cargaDe-js.json"), texto);
