"use strict";

const assert = require("node:assert/strict");
const nexus = require("./nexus-logic.js");

function info(rutas = ["claude", "codex", "web", "gpt"], extras = {}) {
    return { perfiles: { jaime: {
        toml: { rutas, web_codex: true, nombre: "Jaime", ...(extras.toml || {}) },
        servicio: { ActiveState: "active", ...(extras.servicio || {}) },
        cuentas: { claude: "cuenta", claude_web: "cuenta", codex: true, ...(extras.cuentas || {}) },
        uso_hoy: extras.uso_hoy || {},
    } } };
}

{
    const r = nexus.recomendar({ perfil: "jaime", tarea: "programacion", prioridad: "equilibrio", datos: "vault" }, info());
    assert.equal(r.posible, true);
    assert.equal(r.ruta, "codex");
    assert.equal(r.alternativa.ruta, "claude");
}

{
    const r = nexus.recomendar({ perfil: "jaime", tarea: "programacion", prioridad: "equilibrio", datos: "vault" }, info(["claude"]));
    assert.equal(r.ruta, "claude");
}

{
    const r = nexus.recomendar({ perfil: "jaime", tarea: "investigacion", prioridad: "calidad", datos: "sin_vault" }, info());
    assert.equal(r.ruta, "web");
    assert.match(r.foco, /investigación/);
}

{
    const r = nexus.recomendar({ perfil: "jaime", tarea: "automatizacion", prioridad: "velocidad", datos: "sin_vault" }, info());
    assert.equal(r.ruta, "gpt");
}

{
    const r = nexus.recomendar({ perfil: "jaime", tarea: "programacion", prioridad: "calidad", datos: "local" }, info());
    assert.equal(r.posible, false);
    assert.match(r.titulo, /local/);
}

{
    const d = info();
    d.perfiles.jaime.uso_hoy = { codex: 2, claude: 1 };
    d.perfiles.pilar = { uso_hoy: { claude: 3 }, toml: {}, servicio: {}, cuentas: {} };
    assert.deepEqual(nexus.usoPorRuta(d), [
        { ruta: "claude", cantidad: 4 },
        { ruta: "codex", cantidad: 2 },
    ]);
}

console.log("Nexus logic: 6 pruebas correctas");
