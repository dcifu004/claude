/*
 * 🧠 Memoria (encargo 26, documento 30, Fase 2): la memoria de los asistentes de un vistazo.
 *
 * Sólo lectura. Todo sale de memoria-cockpit.py (encargo 25), que se llama con cockpit.spawn:
 * comando fijo, sin argumentos, sin sudo, como el usuario de la sesión. El script se instala
 * JUNTO a la página (~/.local/share/cockpit/memoria/), fuera del volumen cifrado: así, con el
 * volumen cerrado, igual corre y puede decir «volumen_cerrado» (el canónico vive dentro del vault).
 *
 * Regla de la página: si `estado` no es "ok" no se dibuja NINGUNA pestaña ni cifra. Con el volumen
 * cerrado dice «🔒 volumen cerrado»; jamás «0 notas».
 *
 * 🌌 Campo es la maqueta aprobada (maqueta-campo.html) con los datos del lector: d3 va en vendor/
 * (el CSP de Cockpit no deja cargar nada de afuera) y los colores van por clases de memoria.css.
 */
"use strict";
const LECTOR = ["python3", "/home/dcifu004/.local/share/cockpit/memoria/memoria-cockpit.py"];
const TIPOS = ["user", "feedback", "project", "reference"];
const REFRESCO_MS = 5 * 60 * 1000;
const ROTULOS = 12;          // cuántas notas llevan el nombre escrito sin tocarlas: las más enlazadas

/* Ajustes del campo 🌌. Todo lo que se toca para que el grafo respire está acá. Las fuerzas son las de
   d3-force; el alto del lienzo va en memoria.css (--mem-alto-*). test_memoria_campo.py corre un espejo
   de la simulación con ESTOS valores y mide la distancia entre vecinos. */
const ENLACE_DISTANCIA = 90;          // largo que busca cada enlace (era 42)
const ENLACE_FUERZA = 0.4;            // qué tan fuerte tira un enlace entre notas
const ENLACE_FUERZA_HUERFANO = 0.08;  // ídem cuando la punta que enlaza es una nota sin entrantes
const REPULSION = -320;               // cada punto empuja a los demás (era -70); más negativo = más separados
const REPULSION_ALCANCE = 900;        // más lejos que esto ya no se empujan
const CENTRO_X = 0.02;                // atracción al centro, horizontal (era 0,06)
const CENTRO_Y = 0.03;                // ídem vertical (era 0,08)
const CENTRO_HUERFANO = 0.004;        // los sin entrantes casi no sienten el centro
const BORDE_FUERZA_ENLAZA = 0.1;      // anillo de huérfanos: los que al menos enlazan a alguien
const BORDE_FUERZA_SOLA = 0.3;        // ídem los que ni enlazan ni los enlazan
const BORDE_RADIO_BASE = 120;         // anillo de huérfanos: radio = base + raíz(puntos) * esto, en px
const BORDE_RADIO_RAIZ = 22;
const ROTULOS_BUSQUEDA = 15;          // con filtro o búsqueda, hasta cuántos puntos llevan el nombre escrito
const COLISION_HOLGURA = 9;           // aire mínimo entre dos puntos, en px (era 2)
const TICKS_PREVIOS = 300;            // la simulación se acomoda antes de mostrarse, así el encuadre es el final
const AJUSTE_MARGEN = 28;             // borde libre alrededor del grafo al encuadrar, en px
const AJUSTE_ZOOM_MAX = 1.5;          // encuadrar nunca acerca más que esto (un grafo chico no se infla)
const ZOOM_MIN = 0.2, ZOOM_MAX = 5;   // límites del zoom manual
const ESCALA_REFERENCIA = 800;        // lado (raíz del área) del lienzo para el que están pensadas las distancias de arriba
const ESCALA_MIN = 0.55, ESCALA_MAX = 1.4;   // en un teléfono el dibujo se hace más chico; en un monitor grande, más holgado
const ROTULO_PX = 11;                 // tamaño del nombre escrito, SIEMPRE en pantalla (se compensa el zoom)
const TOQUE_PX = 11;                  // radio mínimo de la zona de toque, también en pantalla
const ZOOM_PASO = 1.35;               // lo que acercan las teclas + y -
const TECLA_CONO = 0.5;               // teclado: coseno mínimo para contar como «hacia ahí» (0,5 = 60° de abertura)
const $ = s => document.querySelector(s);
let d = null, firma = "", panel = "campo", campo = null, elegido = null;
const filtro = { tipo: "", texto: "", edad: "", col: "", baja: false };
const vista = { tipo: "", texto: "" };       // filtro y buscador del campo: sobreviven a las relecturas

/* ---------- utilidades ---------- */

const nombre = archivo => (archivo.endsWith(".md") ? archivo.slice(0, -3) : archivo);
const claseTipo = t => (t == null ? "tipo-sin" : TIPOS.includes(t) ? "tipo-" + t : "tipo-otro");
const etiquetaTipo = t => (t == null ? "sin tipo" : t);
const kb = bytes => `${(Math.round(bytes / 102.4) / 10).toLocaleString("es-CL")} KB`;
const dias = n => (n == null ? "sin fecha" : n === 0 ? "hoy" : n === 1 ? "hace 1 día" : `hace ${n} días`);
const plano = x => String(x || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
function fecha(iso) {
    const f = new Date(iso);
    return Number.isNaN(f.getTime()) ? "sin fecha" : f.toLocaleString("es-CL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}
// replaceChildren escribe «null» si le llega un null: acá se descartan, como hace el().
function poner(caja, ...hijos) { caja.replaceChildren(...hijos.flat().filter(h => h != null && h !== false)); }
function aviso(x) { $("#error").hidden = !x; $("#error").textContent = x || ""; }
const punto = t => el("span", { class: "mem-punto " + claseTipo(t), "aria-hidden": "true" });
const chipTipo = t => el("span", { class: "chip dato" }, punto(t), etiquetaTipo(t));
const notaDe = archivo => d.notas.find(n => n.archivo === archivo);
// El nombre de una nota, como botón que la abre en 🌌 Campo. Lo que no es nota va como texto.
function enlaceNota(archivo) {
    return notaDe(archivo) ? el("button", { class: "mini mem-vecino", onclick: () => irANota(archivo) }, nombre(archivo))
                           : el("span", {}, archivo);
}
// Un enlace roto que el lector ubicó en otra parte del vault (en_vault) no es un error de verdad: la
// nota existe, sólo que fuera de la memoria. null = no se buscó, y se trata como roto.
const fueraDeMemoria = x => x.en_vault === true;
const rotosReales = () => d.salud.enlaces_rotos.unicos.filter(x => !fueraDeMemoria(x));
const infoRoto = destino => d.salud.enlaces_rotos.unicos.find(x => x.destino === destino);
function irANota(archivo) { mostrar("campo"); elegir(archivo); }

/* ---------- el modelo del campo: nodos, enlaces y fantasmas ---------- */

// nodos = notas; enlaces = salientes que resuelven a otra nota; fantasma = destino de un enlace roto.
function modeloCampo(datos) {
    const nodos = datos.notas.map(n => ({ id: n.archivo, nota: n, roto: false, entrantes: n.entrantes.cuenta, salientes: 0 }));
    const porId = new Map(nodos.map(n => [n.id, n]));
    const enlaces = [], vistos = new Set();
    for (const n of datos.notas) {
        for (const s of n.salientes) {
            const clave = n.archivo + "\n" + s.nota;
            if (!s.nota || s.nota === n.archivo || !porId.has(s.nota) || vistos.has(clave)) continue;
            vistos.add(clave);
            enlaces.push({ source: n.archivo, target: s.nota, roto: false });
            porId.get(n.archivo).salientes++;
        }
    }
    for (const r of datos.salud.enlaces_rotos.unicos) {
        if (!porId.has(r.origen)) continue;
        const id = "roto:" + r.destino;
        if (!porId.has(id)) {
            const f = { id, roto: true, destino: r.destino, origenes: [], en_codigo: true, entrantes: 0, salientes: 0,
                        fuera: fueraDeMemoria(r), rutas: r.rutas_vault || [] };
            porId.set(id, f); nodos.push(f);
        }
        const f = porId.get(id);
        f.origenes.push(r.origen); f.entrantes++; f.en_codigo = f.en_codigo && r.en_codigo;
        enlaces.push({ source: r.origen, target: id, roto: true, fuera: fueraDeMemoria(r) });
    }
    const tope = nodos.filter(n => !n.roto && n.entrantes > 0).sort((a, b) => b.entrantes - a.entrantes).slice(0, ROTULOS);
    for (const n of tope) n.rotulo = true;
    return { nodos, enlaces, porId };
}
const radio = n => (n.roto ? 4 : 4 + Math.sqrt(n.entrantes) * 2.6);
const brillo = n => Math.max(0.3, 1 - (n.nota.dias_sin_cambio || 0) / 45);      // lo viejo se apaga
const huerfano = n => !n.roto && n.entrantes === 0;                              // nadie la enlaza: va al borde

/* ---------- 🌌 Campo ---------- */

const claveTipo = nota => (nota.type == null ? "sin_type" : nota.type);       // la misma clave que resumen.por_tipo
// ¿Pasa una nota el filtro de tipo y el buscador del campo? El buscador mira nombre de archivo y name.
function pasaVista(nota) {
    const q = plano(vista.texto).trim();
    return (!vista.tipo || claveTipo(nota) === vista.tipo) && (!q || plano(`${nota.archivo} ${nota.name}`).includes(q));
}
function esVisible(n) {
    if (!n.roto) return pasaVista(n.nota);
    const q = plano(vista.texto).trim();
    return (!q || plano(n.destino).includes(q)) && n.origenes.some(o => !vista.tipo || (notaDe(o) && claveTipo(notaDe(o)) === vista.tipo));
}
// Teclado: de entre los puntos visibles, el más cercano que cae dentro del cono (dx, dy). Sin ninguno
// en el cono, el más cercano que al menos queda de ese lado; si tampoco, null (se queda donde está).
function haciaDonde(nodos, actual, dx, dy) {
    for (const minimo of [TECLA_CONO, 0.01]) {
        let mejor = null, puntaje = Infinity;
        for (const n of nodos) {
            if (n === actual || !n.vis) continue;
            const vx = n.x - actual.x, vy = n.y - actual.y, dist = Math.hypot(vx, vy), cos = dist ? (vx * dx + vy * dy) / dist : 0;
            if (cos >= minimo && dist / cos < puntaje) { mejor = n; puntaje = dist / cos; }
        }
        if (mejor) return mejor;
    }
    return null;
}

function dibujarCampo(ajustar) {
    const svg = d3.select("#grafo"), caja = svg.node().getBoundingClientRect();
    const W = caja.width || 600, H = caja.height || 460;
    const previo = campo ? campo.porId : new Map();
    if (campo) campo.sim.stop();
    const m = modeloCampo(d);
    for (const n of m.nodos) { const p = previo.get(n.id); if (p && p.x != null) { n.x = p.x; n.y = p.y; } }
    if (elegido && !m.porId.has(elegido)) elegido = null;
    if (ajustar == null) ajustar = !previo.size;      // la primera vez se encuadra; una relectura respeta la vista del usuario

    svg.selectAll("*").remove();
    const z = svg.append("g");

    const lk = z.append("g").selectAll("line").data(m.enlaces).join("line")
        .attr("class", e => (e.roto ? "mem-enlace roto" + (e.fuera ? " fuera" : "") : "mem-enlace"));
    const nd = z.append("g").selectAll("circle").data(m.nodos).join("circle")
        .attr("class", n => (n.roto ? "mem-nodo roto" + (n.fuera ? " fuera" : "") : "mem-nodo " + claseTipo(n.nota.type)))
        .attr("r", radio).attr("fill-opacity", n => (n.roto ? 0 : brillo(n)));
    const lb = z.append("g").selectAll("text").data(m.nodos).join("text")
        .attr("class", "mem-rotulo").attr("text-anchor", "middle").text(n => (n.roto ? n.destino : nombre(n.id)));
    // Encima de todo, un círculo invisible más grande por nodo: es lo que se toca con el dedo.
    const tq = z.append("g").selectAll("circle").data(m.nodos).join("circle")
        .attr("class", "mem-toque");
    // Con el zoom los rótulos y la zona de toque se compensan: lo que cambia es la distancia, no la letra ni el dedo.
    const compensar = k => {
        lb.attr("font-size", ROTULO_PX / k);
        tq.attr("r", n => Math.max(radio(n) + 5, TOQUE_PX / k));
    };
    const zoom = d3.zoom().scaleExtent([ZOOM_MIN, ZOOM_MAX]).on("zoom", e => { z.attr("transform", e.transform); compensar(e.transform.k); });
    svg.call(zoom).on("dblclick.zoom", null);
    z.attr("transform", d3.zoomTransform(svg.node()));
    compensar(d3.zoomTransform(svg.node()).k);
    tq.append("title").text(n => (n.roto ? (n.fuera ? "existe en el vault, fuera de la memoria: " : "enlace roto: ") + n.destino : nombre(n.id)));

    // El anillo de huérfanos crece con la raíz de la cantidad de puntos. Todas las distancias van
    // multiplicadas por `escala`, que sigue al lienzo: en el S22 el dibujo nace más chico y el encuadre
    // no tiene que achicarlo hasta volver ilegible la letra.
    const escala = Math.max(ESCALA_MIN, Math.min(ESCALA_MAX, Math.sqrt(W * H) / ESCALA_REFERENCIA));
    const borde = (BORDE_RADIO_BASE + BORDE_RADIO_RAIZ * Math.sqrt(m.nodos.length)) * escala;
    // En un lienzo ancho el centro suelta más en horizontal; en uno alto, en vertical: así el dibujo llena la caja.
    const sueltoX = Math.min(1, H / W), sueltoY = Math.min(1, W / H);
    const colocar = () => {
        lk.attr("x1", e => e.source.x).attr("y1", e => e.source.y).attr("x2", e => e.target.x).attr("y2", e => e.target.y);
        nd.attr("cx", n => n.x).attr("cy", n => n.y);
        tq.attr("cx", n => n.x).attr("cy", n => n.y);
        lb.attr("x", n => n.x).attr("y", n => n.y - radio(n) - 4);
    };
    const sim = d3.forceSimulation(m.nodos)
        .force("link", d3.forceLink(m.enlaces).id(n => n.id).distance(ENLACE_DISTANCIA * escala).strength(e => (huerfano(e.source) ? ENLACE_FUERZA_HUERFANO : ENLACE_FUERZA)))
        .force("charge", d3.forceManyBody().strength(REPULSION * escala * escala).distanceMax(REPULSION_ALCANCE * escala))
        .force("center", d3.forceCenter(W / 2, H / 2))
        .force("x", d3.forceX(W / 2).strength(n => (huerfano(n) ? CENTRO_HUERFANO : CENTRO_X * sueltoX)))
        .force("y", d3.forceY(H / 2).strength(n => (huerfano(n) ? CENTRO_HUERFANO : CENTRO_Y * sueltoY)))
        .force("borde", d3.forceRadial(borde, W / 2, H / 2).strength(n => (huerfano(n) ? (n.salientes ? BORDE_FUERZA_ENLAZA : BORDE_FUERZA_SOLA) : 0)))
        .force("col", d3.forceCollide().radius(n => radio(n) + COLISION_HOLGURA))
        .on("tick", colocar);

    // Arrastrar mueve el punto; soltarlo sin haberlo movido es un toque y abre la ficha.
    let inicio = null;
    tq.call(d3.drag()
        .on("start", (e, n) => { inicio = [e.x, e.y]; if (!e.active) sim.alphaTarget(0.3).restart(); n.fx = n.x; n.fy = n.y; })
        .on("drag", (e, n) => { n.fx = e.x; n.fy = e.y; })
        .on("end", (e, n) => {
            if (!e.active) sim.alphaTarget(0);
            n.fx = null; n.fy = null;
            if (inicio && Math.hypot(e.x - inicio[0], e.y - inicio[1]) < 6) elegir(n.id);
            inicio = null;
        }));
    tq.on("click", (e, n) => { e.stopPropagation(); elegir(n.id); });
    svg.on("click", () => elegir(null));

    // Filtro por tipo, buscador y selección en un solo lugar: cada punto queda visible/filtrado y
    // apagado/elegido. El buscador, si hay pocas coincidencias, escribe también sus nombres.
    function resaltar() {
        const vecinos = new Set(elegido ? [elegido] : []);
        for (const e of m.enlaces) {
            if (e.source.id === elegido) vecinos.add(e.target.id);
            if (e.target.id === elegido) vecinos.add(e.source.id);
        }
        for (const n of m.nodos) n.vis = esVisible(n);
        const q = plano(vista.texto).trim(), pocas = m.nodos.filter(n => n.vis).length <= ROTULOS_BUSQUEDA;
        nd.classed("filtrado", n => !n.vis).classed("apagado", n => n.vis && Boolean(elegido) && !vecinos.has(n.id)).classed("elegido", n => n.id === elegido);
        tq.classed("filtrado", n => !n.vis);
        lk.classed("filtrado", e => !e.source.vis || !e.target.vis).classed("apagado", e => Boolean(elegido) && e.source.id !== elegido && e.target.id !== elegido);
        lb.classed("oculta", n => !n.vis || (elegido ? !vecinos.has(n.id) : !(n.rotulo || ((q || vista.tipo) && pocas))));
        const total = m.nodos.filter(n => !n.roto).length, visibles = m.nodos.filter(n => !n.roto && n.vis).length;
        const cuenta = $("#campo-cuenta");
        if (cuenta) cuenta.textContent = q || vista.tipo ? `${visibles} de ${total} notas` : "";
    }
    // Encuadra a la vista el grafo (lo visible; si el filtro no deja nada, todo) con el zoom justo.
    function encuadrar(suave) {
        const r = svg.node().getBoundingClientRect(), w = r.width || W, h = r.height || H;
        const vis = m.nodos.filter(n => n.vis && n.x != null), pts = vis.length ? vis : m.nodos.filter(n => n.x != null);
        if (!pts.length) return;
        const x0 = Math.min(...pts.map(n => n.x - radio(n))), x1 = Math.max(...pts.map(n => n.x + radio(n)));
        const y0 = Math.min(...pts.map(n => n.y - radio(n) - 14)), y1 = Math.max(...pts.map(n => n.y + radio(n)));   // 14 = lo que ocupa un rótulo
        const k = Math.max(ZOOM_MIN, Math.min(AJUSTE_ZOOM_MAX, (w - 2 * AJUSTE_MARGEN) / Math.max(1, x1 - x0), (h - 2 * AJUSTE_MARGEN) / Math.max(1, y1 - y0)));
        const t = d3.zoomIdentity.translate(w / 2, h / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
        (suave ? svg.transition().duration(300) : svg).call(zoom.transform, t);
    }
    // Lleva la vista a un punto sin cambiar el zoom (o, si está muy lejos, acercando hasta 1).
    function irA(n, suave) {
        const r = svg.node().getBoundingClientRect(), k = Math.max(1, d3.zoomTransform(svg.node()).k);
        const t = d3.zoomIdentity.translate((r.width || W) / 2, (r.height || H) / 2).scale(k).translate(-n.x, -n.y);
        (suave ? svg.transition().duration(300) : svg).call(zoom.transform, t);
    }
    // Si el punto quedó fuera de la vista (o pegado al borde), se trae al centro; si no, no se mueve nada.
    function traer(n) {
        const r = svg.node().getBoundingClientRect(), t = d3.zoomTransform(svg.node()), [px, py] = t.apply([n.x, n.y]);
        if (px < AJUSTE_MARGEN || py < AJUSTE_MARGEN || px > r.width - AJUSTE_MARGEN || py > r.height - AJUSTE_MARGEN) irA(n, true);
    }

    svg.on("keydown", e => {
        const dir = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] }[e.key];
        const actual = elegido ? m.porId.get(elegido) : null;
        let destino = null;
        if (dir) {
            // Arriba del campo es y menor: las coordenadas del dibujo ya son las de pantalla (y crece hacia abajo).
            destino = actual ? haciaDonde(m.nodos, actual, dir[0], dir[1]) : mayorNodo(m.nodos);
        } else if (e.key === "]" || e.key === "[") {
            const orden = m.nodos.filter(n => n.vis).sort((a, b) => (plano(a.id) < plano(b.id) ? -1 : 1));
            const i = orden.indexOf(actual);
            destino = orden.length ? orden[(i + (e.key === "]" ? 1 : -1) + orden.length) % orden.length] : null;
        } else if (e.key === "Enter" || e.key === " ") {
            if (actual) irA(actual, true);
        } else if (e.key === "Escape") {
            elegir(null);
        } else if (e.key === "+" || e.key === "=") {
            svg.transition().duration(150).call(zoom.scaleBy, ZOOM_PASO);
        } else if (e.key === "-" || e.key === "_") {
            svg.transition().duration(150).call(zoom.scaleBy, 1 / ZOOM_PASO);
        } else if (e.key === "0") {
            encuadrar(true);
        } else return;
        e.preventDefault();
        if (destino) { elegir(destino.id, false); traer(destino); }
    });

    if (previo.size) sim.alpha(0.3);      // relectura: los puntos ya estaban en su sitio
    campo = { datos: d, ancho: caja.width, sim, porId: m.porId, resaltar, encuadrar, irA, nodos: m.nodos,
              centrar: () => encuadrar(true) };
    resaltar();
    if (!previo.size) {
        // Primera vez: se deja que la simulación se acomode ANTES de mostrar nada, y se encuadra el resultado.
        sim.stop();
        for (let i = 0; i < TICKS_PREVIOS; i++) sim.tick();
        colocar();
    } else colocar();
    if (ajustar) encuadrar(false);
}
// El punto con más entrantes: por dónde empieza el teclado cuando no hay nada elegido.
const mayorNodo = nodos => nodos.filter(n => n.vis && !n.roto).sort((a, b) => b.entrantes - a.entrantes || (plano(a.id) < plano(b.id) ? -1 : 1))[0] || null;

function elegir(id, desplazar = true) {
    elegido = id;
    if (campo) campo.resaltar();
    pintarFicha();
    if (id && desplazar) $("#ficha").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

// Filtro por tipo y buscador, sobre los controles fijos de index.html. Se rellenan en cada pintado.
function controlesCampo() {
    const tipo = $("#campo-tipo"), texto = $("#campo-buscar"), lista = $("#campo-notas");
    tipo.replaceChildren(el("option", { value: "" }, "Todos los tipos"),
        ...Object.entries(d.resumen.por_tipo).map(([k, v]) => el("option", { value: k }, `${k === "sin_type" ? "sin tipo" : k} (${v})`)));
    tipo.value = Object.keys(d.resumen.por_tipo).includes(vista.tipo) ? vista.tipo : "";
    vista.tipo = tipo.value; texto.value = vista.texto;
    lista.replaceChildren(...d.notas.map(n => el("option", { value: nombre(n.archivo) })));
}
function aplicarVista() {
    vista.tipo = $("#campo-tipo").value; vista.texto = $("#campo-buscar").value;
    if (campo) campo.resaltar();
}
// Enter en el buscador: elige la mejor coincidencia (nombre exacto primero) y la trae al centro.
function buscarYIr() {
    const q = plano(vista.texto).trim();
    if (!q || !campo) return;
    const hay = campo.nodos.filter(n => !n.roto && n.vis);
    const exacta = hay.find(n => plano(nombre(n.id)) === q || plano(n.nota.name) === q);
    const mejor = exacta || hay.sort((a, b) => (plano(a.id) < plano(b.id) ? -1 : 1))[0];
    if (!mejor) return;
    elegir(mejor.id);
    campo.irA(mejor, true);
}

function listaVecinos(titulo, archivos) {
    return archivos.length ? [el("h3", {}, `${titulo} (${archivos.length})`), el("div", { class: "mem-vecinos" }, archivos.map(enlaceNota))] : [];
}
function pintarFicha() {
    const caja = $("#ficha"), nodo = campo && elegido ? campo.porId.get(elegido) : null;
    if (!nodo) {
        caja.replaceChildren(el("p", { class: "tenue" }, "Toca un punto para ver la nota y sus vecinos. Arrastra un punto para moverlo; con dos dedos se acerca o se aleja."));
        return;
    }
    if (nodo.roto) {
        poner(caja, el("h2", { class: "mem-nombre" }, nodo.destino),
            el("p", {}, nodo.fuera ? el("span", { class: "chip dato ojo" }, "fuera de la memoria") : el("span", { class: "chip dato mal" }, "enlace roto")),
            el("p", {}, nodo.fuera ? "Ninguna nota de la memoria se llama así, pero sí existe en el vault:" : "Ninguna nota de la memoria se llama así."),
            nodo.fuera ? el("ul", { class: "mem-lista" }, nodo.rutas.map(r => el("li", {}, r))) : null,
            nodo.en_codigo ? el("p", { class: "tenue" }, "Aparece sólo dentro de código: probablemente es un ejemplo y no un enlace de verdad.") : null,
            listaVecinos("La nombran", nodo.origenes));
        return;
    }
    const n = nodo.nota;
    const destinos = [...new Set(n.salientes.filter(s => s.nota && s.nota !== n.archivo).map(s => s.nota))];
    const rotos = n.salientes.filter(s => !s.nota).map(s => s.destino);
    const sinMemoria = x => Boolean(infoRoto(x) && fueraDeMemoria(infoRoto(x)));
    poner(caja, el("h2", { class: "mem-nombre" }, n.name || nombre(n.archivo)),
        el("p", { class: "chips" }, chipTipo(n.type),
            n.en_indice ? null : el("span", { class: "chip dato ojo" }, "fuera del índice"),
            n.entrantes.cuenta ? null : el("span", { class: "chip dato ojo" }, "sin entrantes"),
            n.error ? el("span", { class: "chip dato mal" }, "no se pudo leer") : null),
        el("p", {}, n.description || el("span", { class: "tenue" }, "sin descripción")),
        el("p", { class: "tenue" }, `${n.archivo} · cambió ${dias(n.dias_sin_cambio)} · ${kb(n.bytes)}`),
        el("p", { class: "tenue" }, `${n.entrantes.cuenta} entrantes · ${destinos.length} salientes`),
        listaVecinos("La enlazan", n.entrantes.notas), listaVecinos("Enlaza a", destinos),
        rotos.length ? el("h3", {}, `Enlaces rotos (${rotos.length})`) : null,
        rotos.length ? el("ul", { class: "mem-lista" }, rotos.map(x => el("li", { class: sinMemoria(x) ? "mem-ojo" : "mem-mal" },
            sinMemoria(x) ? `${x} — existe en el vault, fuera de la memoria` : x))) : null);
}

function cifras() {
    const r = d.resumen, una = (titulo, valor, clase) => el("div", { class: "mem-cifra " + (valor ? clase : "") }, el("p", {}, titulo), el("b", { class: "num" }, valor));
    return [una("Notas", r.notas, ""), una("Enlaces", r.wikilinks, ""), una("Rotos", rotosReales().length, "mal"), una("Sin entrantes", r.sin_entrantes, "ojo")];
}
function leyenda() {
    const tipos = Object.keys(d.resumen.por_tipo).map(k => (k === "sin_type" ? null : k));
    return [...tipos.map(t => el("span", { class: "mem-clave" }, punto(t), `${etiquetaTipo(t)} (${d.resumen.por_tipo[t == null ? "sin_type" : t]})`)),
        el("span", { class: "mem-clave" }, el("span", { class: "mem-raya", "aria-hidden": "true" }), "roto"),
        el("span", { class: "mem-clave" }, el("span", { class: "mem-raya fuera", "aria-hidden": "true" }), "existe fuera de la memoria"),
        el("span", { class: "mem-clave tenue" }, "tamaño = entrantes · apagado = sin cambios hace tiempo · sin entrantes, al borde")];
}
function pintarCampo() {
    $("#cifras").replaceChildren(...cifras());
    $("#leyenda").replaceChildren(...leyenda());
    controlesCampo();
    if (!campo || campo.datos !== d) dibujarCampo();
    else campo.resaltar();
    pintarFicha();
}

/* ---------- 🩺 Salud ---------- */

function tarjetaSalud(titulo, clase, filas, nota) {
    return el("section", { class: "tarjeta" },
        el("h2", {}, titulo, " ", el("span", { class: "chip dato " + (filas.length ? clase : "") }, filas.length)),
        nota ? el("p", { class: "tenue" }, nota) : null,
        filas.length ? el("ul", { class: "mem-lista" }, filas.map(f => el("li", {}, f))) : el("p", { class: "tenue" }, "✅ nada que revisar"));
}
function salud() {
    const s = d.salud, r = d.resumen, i = d.indice || {};
    const porTipo = Object.entries(r.por_tipo).map(([k, v]) => `${k === "sin_type" ? "sin tipo" : k}: ${v}`).join(" · ");
    const ajenos = el("details", {}, el("summary", {}, `Ver los ${s.ajenos.length}`),
        el("ul", { class: "mem-lista" }, s.ajenos.map(a => el("li", {}, `${a.nombre} (${a.tipo})`))));
    $("[data-panel=salud]").replaceChildren(
        el("div", { class: "mem-cifras" }, cifras()),
        el("section", { class: "tarjeta" }, el("h2", {}, "Resumen"), el("dl", { class: "dato" },
            el("dt", {}, "Carpeta"), el("dd", {}, d.carpeta),
            el("dt", {}, "Notas"), el("dd", {}, `${r.notas} (${kb(r.bytes)}) · ${r.archivos_md} archivos .md en total`),
            el("dt", {}, "Por tipo"), el("dd", {}, porTipo),
            el("dt", {}, "Enlaces"), el("dd", {}, `${r.wikilinks} wikilinks · ${r.rotos_unicos} sin resolver en la memoria: ${rotosReales().length} rotos de verdad y ${r.rotos_en_vault || 0} que existen en el vault, fuera de la memoria (${r.rotos_total} contando repetidos, ${r.rotos_en_codigo} sólo dentro de código)`),
            el("dt", {}, "Índice"), el("dd", {}, i.existe ? `${i.archivo}: ${i.entradas} entradas, ${i.lineas} líneas, ${kb(i.bytes)}` : "⚠️ no hay MEMORY.md"))),
        tarjetaSalud("🔀 Conflictos de Syncthing", "mal", s.conflictos.map(c => [el("strong", {}, c.archivo), " — copia de ", enlaceNota(c.original), ` · equipo ${c.equipo} · ${dias(c.dias)}`]),
            "Dos equipos cambiaron el mismo archivo y Syncthing guardó las dos versiones. Hay que mirar la copia y borrarla."),
        tarjetaSalud("⛓️ Enlaces rotos", "mal", rotosReales().map(x => [enlaceNota(x.origen), ` → «${x.destino}»`, x.veces > 1 ? ` ×${x.veces}` : "",
            x.en_codigo ? el("span", { class: "chip dato mem-al-lado" }, "dentro de código") : null]),
            "Wikilinks que no llegan a ninguna nota de la memoria ni existen en ninguna otra parte del vault."),
        tarjetaSalud("📎 El destino existe, pero fuera de la memoria", "ojo", s.enlaces_rotos.unicos.filter(fueraDeMemoria).map(x => [enlaceNota(x.origen), ` → «${x.destino}»`,
            x.veces > 1 ? ` ×${x.veces}` : "", el("div", { class: "tenue" }, `Está en el vault: ${x.rutas_vault.join(" · ")}`)]),
            "En Obsidian el enlace funciona, pero un asistente que lee sólo la memoria no puede abrirlo: conviene copiar el dato a la memoria o dejar de enlazarlo."),
        tarjetaSalud("📑 El índice nombra un archivo que no existe", "mal", s.indice_sin_archivo.map(x => `línea ${x.linea}: ${x.destino}`)),
        tarjetaSalud("📭 Notas fuera del índice", "ojo", s.fuera_de_indice.map(enlaceNota), "No figuran en MEMORY.md: los asistentes no las encuentran al empezar."),
        tarjetaSalud("🏷️ Archivos sin type", "ojo", s.sin_type.map(enlaceNota), "No tienen type en el frontmatter: probablemente no son memorias."),
        tarjetaSalud("🪪 El name no coincide con el archivo", "ojo", s.name_distinto.map(x => [enlaceNota(x.archivo), ` — name: «${x.name}»`])),
        tarjetaSalud("🐘 Notas grandes", "ojo", s.sobre_umbral.map(x => [enlaceNota(x.archivo), ` — ${kb(x.bytes)}`]), `Pesan más de ${kb(d.umbral_bytes)}: conviene partirlas.`),
        tarjetaSalud("🕸️ Notas antiguas", "", s.antiguas.map(x => [enlaceNota(x.archivo), ` — ${dias(x.dias_sin_cambio)}`]), `Sin cambios hace más de ${d.dias_antigua} días.`),
        tarjetaSalud("🏝️ Notas sin entrantes", "", s.sin_entrantes.map(enlaceNota), "Ninguna otra nota las enlaza."),
        el("section", { class: "tarjeta" }, el("h2", {}, "📦 Cosas que no son memoria ", el("span", { class: "chip dato " + (s.ajenos.length ? "ojo" : "") }, s.ajenos.length)),
            el("p", { class: "tenue" }, "Archivos y carpetas del primer nivel que no son notas. Viajan por Syncthing a todos los equipos."),
            s.ajenos.length ? ajenos : el("p", { class: "tenue" }, "✅ nada que revisar")));
}

/* ---------- 📋 Notas ---------- */

function filaNota(n) {
    return el("tr", {},
        el("td", {}, enlaceNota(n.archivo), n.en_indice ? null : el("span", { class: "chip dato ojo mem-al-lado" }, "fuera del índice"),
            el("div", { class: "tenue" }, n.description || "sin descripción")),
        el("td", {}, chipTipo(n.type)), el("td", { class: "num" }, n.entrantes.cuenta), el("td", { class: "num" }, dias(n.dias_sin_cambio)));
}
const EDADES = [["", "Cualquier antigüedad"], ["7", "Cambiadas en los últimos 7 días"], ["30", "Cambiadas en los últimos 30 días"], ["viejas", "Antiguas (sin cambios hace tiempo)"]];
// Cada columna ordena por su valor; lo que no tiene fecha va siempre al final.
const COLUMNAS = [["archivo", "Nota", n => plano(n.archivo)], ["type", "Tipo", n => plano(n.type || "~")],
    ["entrantes", "Entrantes", n => n.entrantes.cuenta], ["cambio", "Último cambio", n => (n.dias_sin_cambio == null ? null : new Date(n.ultimo_cambio).getTime())]];
function pasaEdad(n, edad) {
    if (!edad) return true;
    if (n.dias_sin_cambio == null) return false;
    return edad === "viejas" ? n.dias_sin_cambio > d.dias_antigua : n.dias_sin_cambio <= Number(edad);
}
function ordenar(fs, col, baja) {
    const c = COLUMNAS.find(x => x[0] === col);
    if (!c) return fs;
    const v = c[2], sentido = baja ? -1 : 1;
    return [...fs].sort((a, b) => {
        const x = v(a), y = v(b);
        if (x == null || y == null) return (x == null) - (y == null);
        return (x < y ? -1 : x > y ? 1 : 0) * sentido || (plano(a.archivo) < plano(b.archivo) ? -1 : 1);
    });
}
function notas() {
    const tipo = el("select", { "aria-label": "Tipo" }, el("option", { value: "" }, "Todos los tipos"),
        Object.entries(d.resumen.por_tipo).map(([k, v]) => el("option", { value: k }, `${k === "sin_type" ? "sin tipo" : k} (${v})`)));
    const edad = el("select", { "aria-label": "Antigüedad" }, EDADES.map(([v, t]) => el("option", { value: v }, t)));
    const texto = el("input", { type: "text", placeholder: "Buscar en el nombre o la descripción", "aria-label": "Buscar" });
    const cuenta = el("p", { class: "tenue" }), cuerpo = el("tbody", {});
    tipo.value = Object.keys(d.resumen.por_tipo).includes(filtro.tipo) ? filtro.tipo : ""; texto.value = filtro.texto;
    edad.value = EDADES.some(e => e[0] === filtro.edad) ? filtro.edad : "";
    const cabezas = COLUMNAS.map(([clave, titulo]) => {
        const boton = el("button", { class: "mem-orden", type: "button", onclick: () => {
            filtro.baja = filtro.col === clave ? !filtro.baja : false; filtro.col = clave; dib();
        } });
        return { clave, titulo, boton, th: el("th", {}, boton) };
    });
    const dib = () => {
        filtro.tipo = tipo.value; filtro.texto = texto.value; filtro.edad = edad.value;
        const q = plano(filtro.texto).trim();
        const fs = d.notas.filter(n => (!filtro.tipo || (n.type == null ? "sin_type" : n.type) === filtro.tipo)
            && pasaEdad(n, filtro.edad) && (!q || plano(`${n.archivo} ${n.name} ${n.description}`).includes(q)));
        cuenta.textContent = `${fs.length} de ${d.notas.length} notas`;
        cuerpo.replaceChildren(...ordenar(fs, filtro.col, filtro.baja).map(filaNota));
        for (const c of cabezas) {
            const activa = c.clave === filtro.col;
            c.boton.textContent = c.titulo + (activa ? (filtro.baja ? " ▼" : " ▲") : "");
            c.th.setAttribute("aria-sort", activa ? (filtro.baja ? "descending" : "ascending") : "none");
        }
    };
    tipo.onchange = dib; edad.onchange = dib; texto.oninput = dib; dib();
    $("[data-panel=notas]").replaceChildren(el("section", { class: "tarjeta" }, el("div", { class: "mem-filtros" }, tipo, edad, texto), cuenta,
        el("div", { class: "mem-ancho" }, el("table", {}, el("thead", {}, el("tr", {}, ...cabezas.map(c => c.th))), cuerpo))));
}

/* ---------- 🕒 Actividad ---------- */

// El lector toma la fecha más nueva entre el modified del frontmatter y la del archivo: si la que
// manda es posterior a la del archivo, salió del frontmatter.
const origenFecha = n => (new Date(n.ultimo_cambio).getTime() > new Date(n.mtime).getTime() ? "frontmatter" : "archivo");
function actividad() {
    const orden = (a, b) => new Date(b.ultimo_cambio).getTime() - new Date(a.ultimo_cambio).getTime();
    const con = d.notas.filter(n => n.dias_sin_cambio != null);
    const semana = con.filter(n => n.dias_sin_cambio <= 7).sort(orden), mes = con.filter(n => n.dias_sin_cambio > 7 && n.dias_sin_cambio <= 30).sort(orden);
    const tabla = fs => (fs.length ? el("div", { class: "mem-ancho" }, el("table", {}, el("tbody", {}, fs.map(n => el("tr", {},
        el("td", { class: "num mem-fecha" }, fecha(n.ultimo_cambio), el("div", { class: "tenue" }, origenFecha(n))), el("td", {}, enlaceNota(n.archivo), el("div", { class: "tenue" }, n.description || "")),
        el("td", {}, chipTipo(n.type))))))) : el("p", { class: "tenue" }, "Ninguna nota cambió en este tramo."));
    $("[data-panel=actividad]").replaceChildren(
        el("p", { class: "tenue" }, `Cambiaron ${semana.length} notas en los últimos 7 días y ${semana.length + mes.length} en los últimos 30, de ${d.notas.length}. La fecha es la más nueva entre el modified del frontmatter y la del archivo; debajo de cada una se dice de cuál salió.`),
        el("section", { class: "tarjeta" }, el("h2", {}, `Últimos 7 días (${semana.length})`), tabla(semana)),
        el("section", { class: "tarjeta" }, el("h2", {}, `De 8 a 30 días (${mes.length})`), tabla(mes)));
}

/* ---------- pestañas, lectura y arranque ---------- */

const PINTORES = { campo: pintarCampo, salud, notas, actividad };
function pintar() { if (d && d.estado === "ok") PINTORES[panel](); }
function mostrar(p) {
    panel = p;
    for (const b of document.querySelectorAll("#pestanas button")) b.classList.toggle("activa", b.dataset.p === p);
    for (const s of document.querySelectorAll("section[data-panel]")) s.hidden = s.dataset.panel !== p;
    pintar();
}
// Sin datos no hay pestañas: sólo el motivo. Es lo que impide dibujar «0 notas».
function sinDatos(titulo, lineas) {
    $("#pestanas").hidden = true;
    for (const s of document.querySelectorAll("section[data-panel]")) s.hidden = true;
    $("#sin-datos").hidden = false;
    poner($("#sin-datos"), el("h2", {}, titulo), lineas.filter(Boolean).map(x => el("p", {}, x)));
}
// cockpit.spawn entrega la salida también cuando el comando termina con error: se intenta leer igual.
function correrLector() {
    return new Promise(listo => cockpit.spawn(LECTOR, { err: "message" }).then(salida => listo({ salida }), (error, salida) => listo({ error, salida })));
}
async function leer() {
    const r = await correrLector();
    let datos = null;
    try { datos = JSON.parse(r.salida); } catch (e) { datos = null; }
    aviso("");
    if (!datos || typeof datos !== "object" || !datos.estado) {
        d = null; firma = "";
        sinDatos("⚠️ No se pudo leer la memoria", ["El lector no contestó: " + (r.error ? r.error.message || String(r.error) : "la salida no es un JSON") + ".",
            "¿Está memoria-cockpit.py instalado junto a la página (~/.local/share/cockpit/memoria)?"]);
        return;
    }
    // Si nada cambió desde la lectura anterior no se redibuja: el campo no salta ni se pierde el foco.
    const nueva = JSON.stringify({ ...datos, generado: null });
    barraNodo.leido(datos.generado);
    if (d && nueva === firma && datos.estado === "ok") return;
    d = datos; firma = nueva;
    if (d.estado === "volumen_cerrado") {
        sinDatos("🔒 volumen cerrado", ["La memoria vive dentro del volumen cifrado y está cerrado: no hay nada que mostrar hasta abrirlo.",
            el("span", {}, "Se abre por SSH con ", el("code", {}, "sudo abrir-datos"), " y después Actualizar."), d.detalle]);
    } else if (d.estado !== "ok" || !Array.isArray(d.notas) || !d.notas.length || !d.salud || !d.resumen) {
        sinDatos("⚠️ La memoria no se pudo leer", [d.detalle || d.motivo || "El lector no entregó notas.", d.carpeta]);
    } else {
        $("#sin-datos").hidden = true; $("#pestanas").hidden = false;
        mostrar(panel);
    }
}
const leerSeguro = () => leer().catch(e => aviso(e.message || String(e)));

for (const b of document.querySelectorAll("#pestanas button")) b.addEventListener("click", () => mostrar(b.dataset.p));
$("#centrar").addEventListener("click", () => { if (campo) campo.centrar(); });
$("#campo-tipo").addEventListener("change", aplicarVista);
$("#campo-buscar").addEventListener("input", aplicarVista);
$("#campo-buscar").addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); buscarYIr(); }
    else if (e.key === "Escape") { $("#campo-buscar").value = ""; aplicarVista(); }
});
// Si cambia el ancho (girar el teléfono), el campo se vuelve a centrar; las posiciones se conservan.
window.addEventListener("resize", () => {
    if (campo && panel === "campo" && d && d.estado === "ok" && $("#grafo").getBoundingClientRect().width !== campo.ancho) dibujarCampo(true);
});
barraNodo.alActualizar(leerSeguro);
cockpit.transport.wait(leerSeguro);
setInterval(() => { if (!document.hidden) leerSeguro(); }, REFRESCO_MS);
