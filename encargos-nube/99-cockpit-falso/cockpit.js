/* cockpit falso (encargo 99): file().read() y spawn() se contestan desde servidor.py, en el mismo 127.0.0.1. */
"use strict";
(function () {
    const caso = new URLSearchParams(location.search).get("caso") || "normal";
    const pedir = (ruta, cuerpo) => fetch(ruta, { method: "POST", body: JSON.stringify({ ...cuerpo, caso }) }).then(async r => { const x = await r.json(); if (x.error) throw new Error(x.error); return x.texto; });
    window.cockpit = {
        // Como Cockpit: un archivo que no existe se lee como null.
        file: ruta => ({ read: () => pedir("/_falso/file", { ruta }) }),
        spawn: (argv) => { const p = pedir("/_falso/spawn", { argv }); p.input = () => p; p.stream = () => p; return p; },
        jump: destino => { window.ultimoSalto = destino; },
        transport: { wait: f => setTimeout(f, 0) },
    };
})();
