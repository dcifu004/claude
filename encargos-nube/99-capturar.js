// Encargo 99, C5 y C6: la consola instalada (pi/cockpit-encargos) con el cockpit falso de 99-cockpit-falso/, en 127.0.0.1.
//   node encargos-nube/99-capturar.js
// Falla si hay un error de consola, un pedido fuera de 127.0.0.1 o desborde horizontal; deja las capturas en 99-capturas/.
"use strict";
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const path = require("path"), fs = require("fs");
const PUERTO = 8099, BASE = `http://127.0.0.1:${PUERTO}/encargos/index.html`;
const SALIDA = path.join(__dirname, "99-capturas"), ANCHOS = [1280, 800, 375], TEMAS = ["light", "dark"];
const VISTAS = [["portada", "#/projects"], ["carriles", "#/projects?v=carriles"], ["proyecto-voz", "#/projects?v=board&p=voz"], ["conflicts", "#/projects?v=conflicts"], ["flow", "#/projects?v=flow"]];
const espera = ms => new Promise(r => setTimeout(r, ms));

(async () => {
    const servidor = spawn("python3", [path.join(__dirname, "99-cockpit-falso", "servidor.py"), String(PUERTO)], { stdio: "ignore" });
    await espera(800);
    fs.mkdirSync(SALIDA, { recursive: true });
    const browser = await chromium.launch(), problemas = [], notas = [];
    let n = 0;
    const abrir = async (ancho, tema) => {
        const page = await browser.newPage({ viewport: { width: ancho, height: 900 } });
        await page.addInitScript(t => { try { localStorage.setItem("shell:style", t); } catch (e) { /* sin storage */ } }, tema);
        page.on("console", m => { if (m.type() === "error" || m.type() === "warning") problemas.push(`${tema} ${ancho} consola ${m.type()}: ${m.text()}`); });
        page.on("pageerror", e => problemas.push(`${tema} ${ancho} pageerror: ${e.message}`));
        page.on("request", r => { if (!r.url().startsWith(`http://127.0.0.1:${PUERTO}/`)) problemas.push(`${tema} ${ancho} pedido fuera de 127.0.0.1: ${r.url()}`); });
        return page;
    };
    const desborde = async (page, que) => { const x = await page.evaluate(() => Math.max(document.documentElement.scrollWidth - document.documentElement.clientWidth, (document.querySelector(".consola-trabajo") || document.body).scrollWidth - (document.querySelector(".consola-trabajo") || document.body).clientWidth)); if (x > 0) problemas.push(`${que}: desborde horizontal de ${x}px`); };
    // Con las tres anchuras pesan más de 3 MB: se revisan las tres, pero sólo se guardan las de 1280 y 375 (como pide el encargo).
    const foto = async (page, nombre) => { if (/-800-/.test(nombre)) return; await page.mouse.move(2, 2); await page.screenshot({ path: path.join(SALIDA, `${nombre}.png`) }); n++; };
    for (const tema of TEMAS) for (const ancho of ANCHOS) {
        const page = await abrir(ancho, tema);
        for (const [nombre, hash] of VISTAS) {
            await page.goto(`${BASE}${hash}`); await page.waitForSelector("[data-panel=projects] .proy-kpis");
            await desborde(page, `${tema} ${ancho} ${nombre}`);
            await foto(page, `${nombre}-${ancho}-${tema}`);
        }
        // El panel de una tarjeta y su enlace a Flow (C6).
        await page.goto(`${BASE}#/projects?v=board&p=voz`); await page.waitForSelector(".proy-tarjeta");
        await page.click('.proy-tarjeta[data-encargo="96"]'); await page.waitForSelector(".proy-detalle");
        await desborde(page, `${tema} ${ancho} panel`); await foto(page, `panel-96-${ancho}-${tema}`);
        await page.goto(`${BASE}#/projects?v=board&p=consola`); await page.waitForSelector(".proy-tarjeta");
        await page.click('.proy-tarjeta[data-encargo="86"]'); await page.waitForSelector(".proy-detalle a");
        await page.click('.proy-detalle a[href^="#/flujo"]');
        await page.waitForFunction(() => location.hash.startsWith("#/flujo") && /Pipeline · encargo 86/.test(document.querySelector("[data-panel=flujo]").textContent || ""), null, { timeout: 8000 })
            .then(() => notas.push(`${tema} ${ancho}: C6 ok, ${"«Ver en Flow»"} abre ${"#/flujo?e=86"} con «Pipeline · encargo 86»`))
            .catch(async () => problemas.push(`${tema} ${ancho}: el enlace a Flow no abrió la red filtrada (hash ${await page.evaluate(() => location.hash)})`));
        if (ancho === 1280) await foto(page, `flow-desde-tarjeta-86-${ancho}-${tema}`);
        await page.close();
    }
    // proyectos.json ausente, roto, enorme u hostil: la pestaña lo dice y Flow sigue igual. Y una cola viva (C3, a la vista).
    for (const caso of ["ausente", "roto", "grande", "hostil", "vivo"]) {
        const page = await abrir(1280, "light");
        await page.goto(`${BASE.replace("index.html", `index.html?caso=${caso}`)}#/projects`); await page.waitForSelector("[data-panel=projects] > *");
        await espera(400);
        const texto = await page.evaluate(() => document.querySelector("[data-panel=projects]").textContent);
        notas.push(`caso ${caso}: ${texto.slice(0, 110).replace(/\s+/g, " ")}`);
        if (caso === "hostil" && await page.evaluate(() => !!document.querySelector("[data-panel=projects] img"))) problemas.push("caso hostil: apareció un <img> armado con datos");
        await foto(page, `caso-${caso}-1280-light`);
        await page.goto(`${BASE.replace("index.html", `index.html?caso=${caso}`)}#/flujo`); await page.waitForSelector("[data-panel=flujo] svg", { timeout: 8000 }).catch(() => problemas.push(`caso ${caso}: Flow no se dibujó`));
        await page.close();
    }
    await browser.close(); servidor.kill();
    const peso = fs.readdirSync(SALIDA).reduce((a, f) => a + fs.statSync(path.join(SALIDA, f)).size, 0);
    console.log(`${n} capturas en encargos-nube/99-capturas/ (${(peso / 1048576).toFixed(1)} MB)`);
    console.log(notas.join("\n"));
    if (problemas.length) { console.log("PROBLEMAS:\n" + problemas.join("\n")); process.exit(1); }
    console.log("sin errores de consola, sin pedidos fuera de 127.0.0.1 y sin desborde horizontal");
})();
