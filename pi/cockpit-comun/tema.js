/*
 * El tema de las páginas propias sigue al de Cockpit (encargo 18). ÚNICA copia de
 * `aplicarTema()`: antes estaba repetida en sistema.js, luces.js, noticias.js y
 * bots/comun.js. Se carga en el <head> de las seis páginas, antes de pintar nada, y deja
 * data-theme en <html>; los colores de cada tema están en tokens.css.
 */
"use strict";

function aplicarTema() {
    let estilo = null;
    try { estilo = localStorage.getItem("shell:style"); } catch (e) { /* sin storage */ }
    const oscuro = estilo === "dark" ||
        ((!estilo || estilo === "auto") && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = oscuro ? "dark" : "light";
}
window.addEventListener("storage", aplicarTema);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", aplicarTema);
aplicarTema();
