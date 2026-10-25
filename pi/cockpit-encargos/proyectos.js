/* Encargo 99: la pestaña Projects (la maqueta 98 en la consola). Sólo dibuja lo que armó modeloProyectos con lo que
   encargos.js ya leyó: no lee, no ejecuta y no escribe. Todo va por el() y svg() (nodos y textContent); los anchos, por
   CSSOM. Los títulos de los .md pasan por la limpieza de la página (ctx.limpiar, la lista blanca de delPanel()). */
"use strict";
const vistaProyectos = (() => {
    const VISTAS = ["board", "carriles", "conflicts", "flow"];
    const BANDAS = [["Done", "Done", "cfd-done"], ["Cerrado", "Cerrado sin DESPLEGABLE", "cfd-cerrado"], ["Review", "Review", "cfd-rev"], ["In progress", "In progress", "cfd-prog"]];
    const estado = { soloAbiertos: true, detalle: null, doneAbierto: new Set() };
    let ctx = null;
    const n1 = (x, d = 1) => Number(x).toLocaleString("es-CL", { maximumFractionDigits: d });
    const pct = x => (x == null ? "—" : `${Math.round(x * 100)} %`);
    const dur = d => (d == null ? "—" : d < 1 / 24 ? `${n1(d * 1440, 0)} min` : d < 1 ? `${n1(d * 24)} h` : `${n1(d)} d`);
    const ancho = (nodo, v) => { nodo.style.setProperty("--w", `${Math.max(0, Math.min(100, Math.round(v * 1000) / 10))}%`); return nodo; };
    const nombre = id => { const p = ctx.m.proyectos.find(x => x.id === id); return p ? p.nombre : id; };
    const titulo = t => ctx.limpiar(t.titulo);

    // La URL: #/projects?v=<vista>&p=<proyecto>. Lo que no calza con una vista o un proyecto conocido se ignora.
    function ruta(q) {
        const v = q.get("v"), p = q.get("p");
        return { v: VISTAS.includes(v) ? v : "board", p: p && ctx.m.proyectos.some(x => x.id === p) ? p : null };
    }
    function boton(texto, activo, alTocar, extra = {}) { return el("button", { class: `mini proy-boton${activo ? " activa" : ""}`, "aria-pressed": activo ? "true" : "false", onclick: alTocar, ...extra }, texto); }

    function kpis() {
        const g = ctx.m.global, rev = ctx.m.conteo.Review, tope = ctx.m.tope.Review;
        const item = (term, valor, nota, mal) => el("div", { class: `proy-kpi${mal ? " mal" : ""}` }, el("span", { class: "proy-kpi-nombre", "data-term": term }, term), el("strong", {}, valor), el("small", { class: "tenue" }, nota));
        return el("div", { class: "proy-kpis" },
            item("Throughput", `${n1(g.throughput)}/sem`, `media de ${g.ventana.length} semanas · ésta: ${g.ultimaSemana}`),
            item("Lead time", dur(g.leadMediana), `mediana, escrito → DESPLEGABLE · p85 ${dur(g.leadP85)}`),
            item("Cycle time", dur(g.cycleMediana), `mediana, 1.ª fase → DESPLEGABLE · p85 ${dur(g.cycleP85)}`),
            item("Rework rate", pct(g.retrabajo), `${n1(g.minRetrabajo, 0)} de ${n1(g.minutos, 0)} min en fix y rev2+`),
            item("WIP limit", tope ? `${rev}/${tope}` : String(rev), "en Review", tope && rev > tope));
    }
    function wip() {
        return el("div", { class: "proy-wip" }, ctx.m.COLUMNAS.map(c => { const n = ctx.m.conteo[c], t = ctx.m.tope[c];
            return el("span", { class: `chip proy-chip-wip${t && n > t ? " mal" : ""}`, "data-term": t ? "WIP limit" : null }, `${c} `, el("strong", {}, t ? `${n}/${t}` : String(n))); }));
    }
    function insignias(t) {
        const xs = [];
        if (t.nube) xs.push(el("span", { class: "insignia" }, "nube"));
        if (t.bloqueado) xs.push(el("span", { class: "insignia mal" }, "bloqueado"));
        if (t.aging != null) xs.push(el("span", { class: `insignia${t.aging >= ctx.m.aging ? " mal" : ""}`, "data-term": "Aging" }, `${t.aging} d`));
        if (t.sinDesplegable) xs.push(el("span", { class: "insignia ojo", title: "No está en «abiertos» y su última revisión no fue DESPLEGABLE." }, "sin DESPL."));
        if (t.dudas.length) xs.push(el("span", { class: "insignia ojo", title: t.dudas.join(" ") }, "duda"));
        return xs;
    }
    function tarjeta(t) {
        return el("button", { class: `proy-tarjeta col-${t.columna.replace(" ", "-").toLowerCase()}`, "data-encargo": t.id, onclick: () => { estado.detalle = t.id; dibujar(); }, "aria-label": `Encargo ${t.id}: ${titulo(t)}` },
            el("span", { class: "proy-tarjeta-cabeza" }, el("strong", {}, t.id), insignias(t)),
            el("span", { class: "proy-tarjeta-titulo" }, titulo(t)),
            t.abierto ? null : el("small", { class: "tenue" }, t.fin != null ? `✓ ${modeloProyectos.fecha(t.fin).slice(0, 5)}` : t.sinDesplegable ? `última fase ${modeloProyectos.fecha(t.ultima).slice(0, 5)}` : "sin fases en el historial"));
    }

    // Board B: una tarjeta por proyecto. Al tocarla se abre su carril (A).
    function portada() {
        const ps = ctx.m.proyectos;
        return [wip(), el("div", { class: "proy-acciones" }, boton("Ver todos los carriles", false, () => ctx.ir({ v: "carriles", p: null }))),
            el("div", { class: "proy-portada" }, ps.map(p => {
                const total = p.tarjetas.length, done = p.conteo.Done, pr = p.pronostico;
                return el("section", { class: "tarjeta proy-proyecto" },
                    el("div", { class: "proy-fila" }, el("h2", {}, el("button", { class: "proy-enlace", onclick: () => ctx.ir({ v: "board", p: p.id }) }, p.nombre)), el("span", { class: `insignia${p.abiertas ? "" : " tenue"}` }, `${p.abiertas} abiertos`)),
                    el("p", { class: "tenue proy-resultado" }, p.resultado || "sin resultado"),
                    el("div", { class: "proy-mini", "aria-label": "Tarjetas por columna" }, ctx.m.COLUMNAS.map(c => el("span", { class: `proy-mini-col${p.conteo[c] ? " con" : ""} col-${c.replace(" ", "-").toLowerCase()}` }, el("small", {}, c), el("strong", {}, String(p.conteo[c]))))),
                    ancho(el("div", { class: "proy-avance", role: "img", "aria-label": `${done} de ${total} en Done` }), total ? done / total : 0),
                    el("small", { class: "tenue" }, `${done} de ${total} en Done · rework ${pct(p.metricas.retrabajo)}`),
                    p.abiertas ? el("div", { class: "proy-tarjetas" }, p.tarjetas.filter(t => t.abierto).map(tarjeta)) : null,
                    p.bloqueo ? el("p", { class: "aviso rojo proy-bloqueo" }, "⛔ ", p.bloqueo) : null,
                    el("p", { class: "tenue proy-pie" }, el("span", { "data-term": "Forecast" }, "Forecast"), ": ", pr.estado === "ok" ? `80 % en ≤ ${pr.p80} sem` : pr.estado === "nada" ? "nada pendiente" : "datos insuficientes"));
            }))];
    }
    // Board A: carriles × columnas. Con p, sólo ese proyecto y todo su Done; sin p, todos, con el filtro.
    function carriles(p) {
        const ps = p ? ctx.m.proyectos.filter(x => x.id === p) : ctx.m.proyectos.filter(x => !estado.soloAbiertos || x.abiertas);
        const solo = !p && estado.soloAbiertos, ocultos = p ? [] : ctx.m.proyectos.filter(x => estado.soloAbiertos && !x.abiertas);
        const cabeza = el("div", { class: "proy-cabeza" }, el("div", { class: "proy-esquina" }, "Proyecto"), ctx.m.COLUMNAS.map(c => { const n = ctx.m.conteo[c], t = ctx.m.tope[c];
            return el("div", {}, c, el("span", { class: `proy-tope${t && n > t ? " mal" : ""}`, "data-term": t ? "WIP limit" : null }, t ? `${n}/${t}` : String(n))); }));
        const filas = ps.map(x => el("section", { class: "proy-carril", "aria-label": x.nombre },
            el("div", { class: "proy-carril-cabeza" }, el("h3", {}, p ? x.nombre : el("button", { class: "proy-enlace", onclick: () => ctx.ir({ v: "board", p: x.id }) }, x.nombre)),
                el("p", { class: "tenue proy-resultado" }, x.resultado), x.bloqueo ? el("span", { class: "insignia mal", title: x.bloqueo }, "⛔ bloqueo") : null),
            ctx.m.COLUMNAS.map(c => {
                const ts = x.tarjetas.filter(t => t.columna === c), celda = el("div", { class: `proy-celda${ts.length ? "" : " vacia"}` }, el("span", { class: "proy-celda-nombre" }, `${c} · ${ts.length}`));
                if (c === "Done" && solo) { if (ts.length) celda.append(el("span", { class: "proy-hechos" }, `✓ ${ts.length}`)); return celda; }
                if (c === "Done") {
                    const orden = [...ts].sort((a, b) => (b.fin ?? b.ultima ?? 0) - (a.fin ?? a.ultima ?? 0)), todo = p || estado.doneAbierto.has(x.id);
                    celda.append(...(todo ? orden : orden.slice(0, 4)).map(tarjeta));
                    if (!p && orden.length > 4) celda.append(boton(todo ? "mostrar menos" : `+${orden.length - 4} más`, false, () => { if (todo) estado.doneAbierto.delete(x.id); else estado.doneAbierto.add(x.id); dibujar(); }));
                    return celda;
                }
                celda.append(...ts.map(tarjeta)); return celda;
            })));
        return [wip(), el("div", { class: "proy-acciones" }, p ? boton("← Todos los proyectos", false, () => ctx.ir({ v: "board", p: null })) : boton("← Proyectos", false, () => ctx.ir({ v: "board", p: null })),
                p ? boton("Ver todos los carriles", false, () => ctx.ir({ v: "carriles", p: null })) : el("span", { class: "proy-filtro" }, boton("Sólo abiertos", estado.soloAbiertos, () => { estado.soloAbiertos = true; dibujar(); }), boton("Todo", !estado.soloAbiertos, () => { estado.soloAbiertos = false; dibujar(); }))),
            el("div", { class: "proy-carriles" }, cabeza, filas),
            ocultos.length ? el("p", { class: "tenue" }, `Sin abiertos: ${ocultos.map(x => `${x.nombre} (${x.conteo.Done})`).join(" · ")}.`) : null];
    }

    // Conflicts: matriz encargo × archivo, agrupada por proyecto, y el orden de a uno.
    function conflictos() {
        const A = ctx.m.archivos, orden = ctx.m.proyectos.map(p => p.id), rango = { Review: 0, "In progress": 1, Ready: 2, Idea: 3, Done: 4 };
        const ids = [...new Set(A.flatMap(a => a.encargos))], filas = ids.map(id => ctx.m.tarjeta.get(id)).filter(Boolean).sort((a, b) => orden.indexOf(a.proyecto) - orden.indexOf(b.proyecto) || rango[a.columna] - rango[b.columna]);
        const faltan = ids.filter(id => !ctx.m.tarjeta.has(id));
        if (!A.length) return [el("p", { class: "tenue" }, "proyectos.json no trae archivos_compartidos.")];
        let previo = null;
        const tabla = el("table", { class: "proy-matriz" }, el("thead", {}, el("tr", {}, el("th", {}, "Proyecto → encargo"), A.map(a => el("th", { class: a.choque ? "choque" : "", title: `${a.ruta}: ${a.abiertos.length} abiertos` }, el("code", {}, a.corto), a.choque ? el("span", { class: "insignia mal" }, `${a.abiertos.length} abiertos`) : null)))),
            el("tbody", {}, filas.map(t => { const nuevo = t.proyecto !== previo; previo = t.proyecto;
                return el("tr", { class: nuevo ? "grupo" : "" }, el("th", {}, nuevo ? el("small", { class: "tenue proy-grupo" }, nombre(t.proyecto)) : null,
                        el("button", { class: "proy-enlace", onclick: () => { estado.detalle = t.id; dibujar(); } }, t.id), " ", el("span", { class: `insignia${t.abierto ? " ojo" : ""}` }, t.columna)),
                    A.map(a => { const toca = a.encargos.includes(t.id); return el("td", { class: toca && a.choque && t.abierto ? "choque" : "" }, toca ? (t.abierto ? "●" : "✓") : ""); })); })));
        const choques = A.filter(a => a.choque), sin = A.filter(a => !a.choque);
        return [el("div", { class: "proy-conflictos" },
            el("section", { class: "tarjeta" }, el("h2", {}, el("span", { "data-term": "Conflicts" }, "Conflicts"), " · encargo × archivo"),
                el("p", { class: "tenue" }, "Columnas: los archivos_compartidos de proyectos.json. ● abierto · ✓ en Done. En rojo, los archivos que tocan dos o más encargos abiertos."),
                el("div", { class: "config-ancho" }, tabla), faltan.length ? el("p", { class: "tenue" }, `En la lista pero sin tarjeta: ${faltan.join(", ")}.`) : null),
            el("section", { class: "tarjeta" }, el("h2", {}, "Qué hacer"),
                choques.length ? el("ol", { class: "proy-hacer" }, choques.map(a => el("li", {}, el("code", {}, a.ruta), " — traer de a uno: ", el("strong", {}, a.abiertos.join(" → "))))) : el("p", {}, "Ningún archivo lo tocan dos encargos abiertos."),
                ctx.m.ordenGlobal.length ? el("p", {}, "Orden sugerido para todo: ", el("strong", {}, ctx.m.ordenGlobal.join(" → "))) : null,
                el("p", { class: "tenue" }, "Regla: primero lo que está en Review, después In progress, Ready e Idea; a igual columna, por número. Cada uno se mezcla y se prueba antes de traer el siguiente."),
                sin.length ? el("p", { class: "tenue" }, "Sin choque: ", sin.map(a => `${a.ruta} (${a.abiertos.join(", ") || "nada abierto"})`).join(" · "), ".") : null))];
    }

    // Flow over time: el flujo acumulado (columnas apiladas por semana), Now · Next · Later y el pronóstico.
    function cfd() {
        const ds = ctx.m.cfd;
        if (!ds.length) return el("p", { class: "tenue" }, "El historial no tiene fases todavía.");
        const W = 640, H = 270, ml = 34, mr = 130, mt = 12, mb = 30, iw = W - ml - mr, ih = H - mt - mb;
        const total = x => BANDAS.reduce((n, [k]) => n + x[k], 0), max = Math.max(1, ...ds.map(total)), paso = max > 60 ? 20 : max > 20 ? 10 : 5, tope = Math.ceil(max / paso) * paso;
        const y = v => mt + ih - v / tope * ih, banda = iw / ds.length, bw = Math.min(64, banda * 0.62);
        const s = svg("svg", { class: "proy-cfd", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Flujo acumulado por semana" });
        for (let v = 0; v <= tope; v += paso) { s.append(svg("line", { x1: ml, x2: ml + iw, y1: y(v), y2: y(v), class: "cfd-grilla" })); const tx = svg("text", { x: ml - 6, y: y(v) + 3, class: "cfd-eje", "text-anchor": "end" }); tx.textContent = String(v); s.append(tx); }
        ds.forEach((x, i) => {
            const cx = ml + banda * i + (banda - bw) / 2; let acc = 0;
            for (const [k, etiqueta, clase] of BANDAS) {
                const v = x[k]; if (!v) continue;
                const y0 = y(acc), y1 = y(acc + v); acc += v;
                const r = svg("rect", { x: cx, y: y1 + 1, width: bw, height: Math.max(0, y0 - y1 - 2), rx: 2, class: `cfd-tramo ${clase}` });
                const tt = svg("title", {}); tt.textContent = `Semana del ${modeloProyectos.ddmm(x.semana)} · ${etiqueta}: ${v}`; r.append(tt); s.append(r);
            }
            const et = svg("text", { x: cx + bw / 2, y: H - mb + 16, class: "cfd-eje", "text-anchor": "middle" }); et.textContent = modeloProyectos.ddmm(x.semana);
            const tot = svg("text", { x: cx + bw / 2, y: y(total(x)) - 4, class: "cfd-eje cfd-total", "text-anchor": "middle" }); tot.textContent = String(total(x));
            s.append(et, tot);
        });
        const u = ds.at(-1), xl = ml + banda * (ds.length - 1) + (banda + bw) / 2 + 8; let acc = 0, previo = Infinity;
        for (const [k, etiqueta] of BANDAS) { const v = u[k]; if (!v) continue; const yc = Math.min(previo - 12, y(acc + v / 2) + 3); previo = yc; acc += v; const tx = svg("text", { x: xl, y: yc, class: "cfd-directa" }); tx.textContent = `${etiqueta} ${v}`; s.append(tx); }
        return s;
    }
    function tablaCfd() {
        return el("details", { class: "proy-tabla" }, el("summary", {}, "Ver como tabla"), el("div", { class: "config-ancho" }, el("table", {},
            el("thead", {}, el("tr", {}, el("th", {}, "Semana"), BANDAS.map(([, e]) => el("th", {}, e)), el("th", { "data-term": "Throughput" }, "Throughput"))),
            el("tbody", {}, ctx.m.cfd.map((x, i) => el("tr", {}, el("td", {}, modeloProyectos.ddmm(x.semana)), BANDAS.map(([k]) => el("td", {}, String(x[k]))), el("td", {}, String(ctx.m.global.porSemana[i]))))))));
    }
    function ahoraLuego() {
        const ps = ctx.m.proyectos.filter(p => p.abiertas || p.ideas.length);
        const chip = t => el("button", { class: "chip proy-chip", onclick: () => { estado.detalle = t.id; dibujar(); } }, el("strong", {}, t.id), ` ${t.columna}`);
        const col = (nombreCol, xs, extra = []) => el("div", {}, el("small", { class: "proy-col-nombre" }, nombreCol), xs.map(chip), extra, !xs.length && !extra.length ? el("span", { class: "tenue" }, "—") : null);
        return el("div", { class: "proy-rejilla" }, ps.map(p => el("section", { class: "tarjeta" }, el("h3", {}, p.nombre), el("div", { class: "proy-nnl" },
            col("Now", p.tarjetas.filter(t => t.columna === "In progress" || t.columna === "Review")), col("Next", p.tarjetas.filter(t => t.columna === "Ready")),
            col("Later", p.tarjetas.filter(t => t.columna === "Idea"), p.ideas.map(i => el("span", { class: "tenue proy-idea" }, i)))))));
    }
    function pronosticos() {
        const ps = ctx.m.proyectos.filter(p => p.pronostico.estado !== "nada"), nada = ctx.m.proyectos.filter(p => p.pronostico.estado === "nada");
        const metodo = pr => `Monte Carlo: ${modeloProyectos.CORRIDAS.toLocaleString("es-CL")} corridas con semilla fija. Cada semana futura toma al azar una de las últimas ${pr.semanasVentana} semanas reales del proyecto (${pr.muestras.join(", ")} terminados) hasta cubrir lo que falta (${pr.falta}: Ready + In progress + Review). Con menos de ${modeloProyectos.MIN_HECHOS} terminados no se pronostica.`;
        return el("div", { class: "proy-rejilla" }, ps.map(p => { const pr = p.pronostico;
            return el("section", { class: "tarjeta proy-pronostico" }, el("div", { class: "proy-fila" }, el("h3", {}, p.nombre), el("span", { class: "proy-metodo", tabindex: "0", title: metodo(pr), "aria-label": `Método: ${metodo(pr)}` }, "ⓘ método")),
                el("small", { class: "tenue" }, `Falta ${pr.falta} · ${pr.hechos} terminados en ${pr.semanasVentana} semanas`),
                pr.estado === "ok" ? [el("div", { class: "proy-barras" }, [[50, pr.p50], [80, pr.p80], [95, pr.p95]].map(([q, n]) => el("div", { class: "proy-barra" }, el("span", {}, `${q} %`), ancho(el("i", {}), n / Math.max(4, pr.p95)), el("strong", {}, `≤ ${n} sem`)))),
                    el("p", { class: "tenue" }, `80 %: terminado antes del fin de la semana del ${modeloProyectos.ddmm(pr.semana80)}.`)]
                    : el("p", { class: "aviso ojo" }, `Datos insuficientes: ${pr.hechos} terminado${pr.hechos === 1 ? "" : "s"} en la ventana (mínimo ${modeloProyectos.MIN_HECHOS}). Sin fechas.`)); }),
            nada.length ? el("p", { class: "tenue proy-nada" }, `Sin pendientes que pronosticar: ${nada.map(p => p.nombre).join(" · ")}.`) : null);
    }
    function flujoTiempo() {
        return [el("section", { class: "tarjeta" }, el("h2", {}, el("span", { "data-term": "Cumulative flow" }, "Cumulative flow"), " por semana"),
                el("p", { class: "tenue" }, `${ctx.m.tarjetas.filter(t => t.fases.length).length} encargos con fases en el historial; cada columna es el cierre del domingo (la semana en curso, hasta ahora). Las tarjetas sin fases no entran.`),
                el("div", { class: "proy-leyenda" }, BANDAS.slice().reverse().map(([, e, c]) => el("span", {}, el("i", { class: `proy-muestra ${c}` }), e))),
                el("div", { class: "config-ancho" }, cfd()), tablaCfd()),
            el("h2", { class: "proy-seccion", "data-term": "Now/Next/Later" }, "Now/Next/Later"), ahoraLuego(),
            el("h2", { class: "proy-seccion" }, el("span", { "data-term": "Forecast" }, "Forecast"), " por proyecto"), pronosticos()];
    }

    // El panel de una tarjeta: sus fases reales y los enlaces a Flow (la red filtrada) y a Traces.
    function detalle() {
        const t = ctx.m.tarjeta.get(estado.detalle);
        if (!t) return null;
        const filas = t.fases.map(f => el("tr", {}, el("td", {}, f.fase), el("td", {}, f.cuenta), el("td", {}, modeloProyectos.fecha(f.ini)), el("td", {}, n1(f.min)), el("td", {}, f.veredicto ? el("span", { class: `insignia${f.veredicto === "DESPLEGABLE" ? " ok" : " mal"}` }, f.veredicto) : "—")));
        const dato = (k, v) => [el("dt", {}, k), el("dd", {}, v)];
        const e = encodeURIComponent(t.id);
        return el("section", { class: "tarjeta proy-detalle", "aria-label": `Encargo ${t.id}` },
            el("div", { class: "proy-fila" }, el("h2", {}, `Encargo ${t.id}`), el("button", { class: "mini", "aria-label": "Cerrar", onclick: () => { estado.detalle = null; dibujar(); } }, "×")),
            el("p", {}, titulo(t)), el("div", { class: "proy-tarjeta-cabeza" }, insignias(t)),
            el("dl", { class: "proy-datos" }, dato("Proyecto", nombre(t.proyecto)), dato("Columna", `${t.columna} (${t.origen})`),
                t.escrito != null ? dato("Escrito", modeloProyectos.fecha(t.escrito)) : null, t.inicio != null ? dato("Primera fase", modeloProyectos.fecha(t.inicio)) : null,
                t.fin != null ? dato("DESPLEGABLE", modeloProyectos.fecha(t.fin)) : null, t.lead != null ? [el("dt", { "data-term": "Lead time" }, "Lead time"), el("dd", {}, dur(t.lead))] : null,
                t.cycle != null ? [el("dt", { "data-term": "Cycle time" }, "Cycle time"), el("dd", {}, dur(t.cycle))] : null, t.aging != null ? [el("dt", { "data-term": "Aging" }, "Aging"), el("dd", {}, `${t.aging} días sin fases`)] : null),
            t.dudas.length ? el("p", { class: "aviso ojo" }, t.dudas.join(" ")) : null,
            t.fases.length ? el("div", { class: "config-ancho" }, el("table", {}, el("thead", {}, el("tr", {}, ["Fase", "Cuenta", "Inicio", "Min", "Veredicto"].map(x => el("th", {}, x)))), el("tbody", {}, filas))) : el("p", { class: "tenue" }, "Sin fases en el historial."),
            el("p", { class: "proy-enlaces" }, el("a", { href: `#/flujo?e=${e}` }, `Ver en Flow · encargo ${t.id} ›`), t.fases.length ? el("a", { href: `#/historial?e=${e}` }, "Ver en Traces ›") : null));
    }

    let nodo = null, q = null;
    function dibujar() {
        if (!nodo) return;
        if (!ctx.m) { nodo.replaceChildren(el("p", { class: "aviso ojo" }, ctx.error || "Projects: sin datos de proyectos.")); return; }
        const r = ruta(q), v = r.v === "board" && r.p ? "detalle" : r.v;
        const vistas = el("div", { class: "proy-vistas", role: "group", "aria-label": "Vista de Projects" },
            boton("Board", r.v === "board" || r.v === "carriles", () => ctx.ir({ v: "board", p: null })), boton("Conflicts", r.v === "conflicts", () => ctx.ir({ v: "conflicts", p: null })), boton("Flow over time", r.v === "flow", () => ctx.ir({ v: "flow", p: null })));
        const cuerpo = v === "conflicts" ? conflictos() : v === "flow" ? flujoTiempo() : v === "carriles" ? carriles(null) : v === "detalle" ? carriles(r.p) : portada();
        const avisos = ctx.m.errores.length ? el("details", { class: "aviso ojo" }, el("summary", {}, `proyectos.json: ${ctx.m.errores.length} entrada(s) ignorada(s)`), el("ul", {}, ctx.m.errores.slice(0, 20).map(x => el("li", {}, x)))) : null;
        nodo.replaceChildren(...[ctx.error ? el("p", { class: "aviso ojo" }, ctx.error) : null, avisos, kpis(), vistas, detalle(), ...[cuerpo].flat()].filter(Boolean));
        if (ctx.alDibujar) ctx.alDibujar(nodo);
        if (estado.detalle) { const x = nodo.querySelector(".proy-detalle"); if (x && x.scrollIntoView) x.scrollIntoView({ block: "nearest" }); }
    }
    function pintar(destino, contexto, consulta) { nodo = destino; ctx = contexto; q = consulta; if (ctx.m && estado.detalle && !ctx.m.tarjeta.has(estado.detalle)) estado.detalle = null; dibujar(); }
    return { pintar, VISTAS };
})();
