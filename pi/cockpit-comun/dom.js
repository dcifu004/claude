/*
 * `el()`: arma un elemento del DOM nodo por nodo, sin HTML en texto ni estilos en línea
 * (el CSP de Cockpit los bloquea). ÚNICA copia (encargo 18): antes estaba repetida en
 * sistema.js, noticias.js y bots/comun.js. La cargan las seis páginas, antes que barra.js.
 */
"use strict";

function el(tag, attrs = {}, ...hijos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") e.className = v;
        else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
        else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
    }
    for (const h of hijos.flat()) {
        if (h == null || h === false) continue;
        e.append(h instanceof Node ? h : document.createTextNode(String(h)));
    }
    return e;
}
