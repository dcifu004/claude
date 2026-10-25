/* Encargo 99: el modelo de la pestaña Projects (el de la maqueta 98, adaptado). Sin DOM y sin cockpit: recibe lo que
   encargos.js ya leyó (proyectos.json, historial, el índice de NN-*.md y vivo/) y devuelve tarjetas, métricas, el flujo
   acumulado, el pronóstico y los choques. No lee ni escribe nada. Corre igual en node (pruebas). */
"use strict";
const modeloProyectos = (() => {
    const COLUMNAS = ["Idea", "Ready", "In progress", "Review", "Done"];
    const RANGO = { Review: 0, "In progress": 1, Ready: 2, Idea: 3, Done: 4 };
    const DIA = 864e5, VENTANA = 8, MIN_HECHOS = 3, CORRIDAS = 10000, SEMILLA = 98, MAX_TEXTO = 200, MAX_LISTA = 2000;
    const RE_ID = /^[0-9]{2}[a-z0-9]{0,8}$/, RE_PROYECTO = /^[a-z0-9_-]{1,32}$/;
    const RETRABAJO = /^(fix\d*|rev([2-9]|\d{2,}))$/;                 // el criterio de balance.py
    const CUENTAS = { claude_diego: "Claude (Diego)", claude_cami: "Claude (Cami)", codex: "Codex" };
    const VIVA = /^(corriendo|pausada.*)$/;                            // cola en curso o pausada
    const propio = (o, k) => (o && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined);
    const texto = x => (typeof x === "string" ? x.replace(/\s+/g, " ").trim().slice(0, MAX_TEXTO) : "");
    const ids = xs => (Array.isArray(xs) ? xs.slice(0, MAX_LISTA).filter(x => typeof x === "string" && RE_ID.test(x)) : []);
    const num = id => (String(id).match(/^\d+/) || [""])[0];
    const porId = (a, b) => String(a).localeCompare(String(b), "es", { numeric: true });

    // proyectos.json es un dato: se copia a estructuras sin prototipo y se descarta lo que no tiene la forma esperada.
    function normalizar(pj) {
        const errores = [];
        if (!pj || typeof pj !== "object" || Array.isArray(pj)) return { proyectos: [], archivos: [], tope: Object.create(null), aging: 7, errores: ["proyectos.json no es un objeto"] };
        const tope = Object.create(null), tw = propio(pj, "tope_wip");
        for (const c of COLUMNAS) { const v = propio(tw, c); if (Number.isInteger(v) && v > 0) tope[c] = v; }
        const ag = propio(pj, "aging_dias"), aging = Number.isInteger(ag) && ag > 0 && ag < 366 ? ag : 7;
        const proyectos = [], vistos = new Set();
        for (const p of Array.isArray(propio(pj, "proyectos")) ? propio(pj, "proyectos").slice(0, 200) : []) {
            const id = propio(p, "id");
            if (typeof id !== "string" || !RE_PROYECTO.test(id) || vistos.has(id)) { errores.push(`proyecto sin id válido o repetido: ${texto(String(id))}`); continue; }
            vistos.add(id);
            const abiertos = new Map(), ab = propio(p, "abiertos");
            if (ab && typeof ab === "object" && !Array.isArray(ab)) for (const [k, v] of Object.entries(ab).slice(0, MAX_LISTA)) {
                if (RE_ID.test(k) && COLUMNAS.includes(v)) abiertos.set(k, v); else errores.push(`${id}: «abiertos» con ${texto(k)} → ${texto(String(v))} no vale`);
            }
            proyectos.push({ id, nombre: texto(propio(p, "nombre")) || id, resultado: texto(propio(p, "resultado")), encargos: ids(propio(p, "encargos")), abiertos,
                ideas: (Array.isArray(propio(p, "ideas")) ? propio(p, "ideas") : []).slice(0, 50).map(texto).filter(Boolean), bloqueo: texto(propio(p, "bloqueo")) });
        }
        if (!proyectos.some(p => p.id === "otros")) proyectos.push({ id: "otros", nombre: "Sueltos", resultado: "Encargos sin proyecto", encargos: [], abiertos: new Map(), ideas: [], bloqueo: "" });
        const ac = propio(pj, "archivos_compartidos"), archivos = [];
        if (ac && typeof ac === "object" && !Array.isArray(ac)) for (const [ruta, xs] of Object.entries(ac).slice(0, 200)) if (!ruta.startsWith("_") && Array.isArray(xs)) archivos.push([texto(ruta), ids(xs)]);
        return { proyectos, archivos, tope, aging, errores };
    }

    // Hora de Chile para las semanas (lunes a domingo) y las fechas. La clave de semana es la fecha del lunes, AAAA-MM-DD.
    const PARTES = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Santiago", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", weekday: "short", hourCycle: "h23" });
    const DIAS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    function partes(t) { return Object.fromEntries(PARTES.formatToParts(new Date(t)).map(x => [x.type, x.value])); }
    function semana(t) { const p = partes(t); return new Date(Date.UTC(+p.year, +p.month - 1, +p.day - DIAS.indexOf(p.weekday))).toISOString().slice(0, 10); }
    const masSemanas = (s, n) => new Date(Date.parse(`${s}T00:00:00Z`) + n * 7 * DIA).toISOString().slice(0, 10);
    const ddmm = s => `${s.slice(8, 10)}-${s.slice(5, 7)}`;
    function fecha(t) { if (!Number.isFinite(t)) return "sin fecha"; const p = partes(t); return `${p.day}-${p.month} ${p.hour}:${p.minute}`; }

    function tituloCorto(t) {
        let s = texto(t).replace(/^#\s*/, "").replace(/^Encargo\s+\S+?\s*[—–:-]\s*/, "").replace(/\s+[—–-]\s+\d{2}-\d{2}-\d{4}$/, "");
        if (s.endsWith(")")) { let n = 0; for (let i = s.length - 1; i >= 0; i--) { if (s[i] === ")") n++; else if (s[i] === "(" && --n === 0) { if (i > 0) s = s.slice(0, i).trim(); break; } } }
        return s.replace(/\s+\((Claude|Codex)\b.*$/, "");               // títulos cortados, con el paréntesis sin cerrar
    }

    // Monte Carlo con semilla fija: la misma página muestra siempre lo mismo con los mismos datos.
    function azar(semilla) { let a = semilla >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
    const cuantil = (xs, q) => (xs.length ? xs[Math.min(xs.length - 1, Math.ceil(q * xs.length) - 1)] : null);

    function armar({ proyectos: pj, historial, indice, vivos, ahora }) {
        const P = normalizar(pj), sueltos = P.proyectos.find(p => p.id === "otros"), deProyecto = Object.create(null);
        for (const p of P.proyectos) deProyecto[p.id] = p;
        const fases = new Map();
        for (const f of Array.isArray(historial) ? historial : []) {
            if (!f || typeof f !== "object" || typeof f.encargo !== "string" && typeof f.encargo !== "number") continue;
            const id = String(f.encargo), ini = Date.parse(f.inicio), min = Number.isFinite(f.min) ? f.min : 0;
            if (!RE_ID.test(id) || Number.isNaN(ini)) continue;
            if (!fases.has(id)) fases.set(id, []);
            fases.get(id).push({ fase: texto(f.fase), rol: texto(f.rol), cuenta: CUENTAS[f.cuenta] || "otra cuenta", ini, fin: ini + min * 6e4, min,
                veredicto: f.veredicto === "DESPLEGABLE" || f.veredicto === "NO DESPLEGABLE" || f.veredicto === "PLAN RECHAZADO" ? f.veredicto : null });
        }
        for (const xs of fases.values()) xs.sort((a, b) => a.ini - b.ini);
        const ix = new Map();
        for (const x of Array.isArray(indice) ? indice : []) if (x && RE_ID.test(x.id) && !ix.has(x.id)) ix.set(x.id, x);
        const abiertoEn = new Map();
        for (const p of P.proyectos) for (const [id] of p.abiertos) if (!abiertoEn.has(id)) abiertoEn.set(id, p);
        // La cola viva manda sobre el historial: su etapa en autor o fix está In progress; en rev, en Review.
        const enCola = new Map();
        for (const v of Array.isArray(vivos) ? vivos : []) {
            if (!v || typeof v !== "object" || !VIVA.test(String(v.estado || "")) || !RE_ID.test(String(v.etapa ?? "")) || typeof v.fase !== "string") continue;
            const col = /^rev/.test(v.fase) ? "Review" : /^(autor|fix|plan)/.test(v.fase) ? "In progress" : null;
            if (col) enCola.set(String(v.etapa), { columna: col, cola: typeof v.nombre === "string" ? v.nombre : "", fase: v.fase });
        }
        const universo = [...new Set([...ix.keys(), ...fases.keys(), ...abiertoEn.keys(), ...enCola.keys()])];
        const asignar = id => {
            const exactos = P.proyectos.filter(p => p.encargos.includes(id) || p.abiertos.has(id));
            if (exactos.length) return { p: exactos[0], como: "exacto", otros: exactos.slice(1) };
            const n = num(id), porNum = P.proyectos.filter(p => p.encargos.includes(n) || p.abiertos.has(n));
            if (n && porNum.length) return { p: porNum[0], como: "número", otros: porNum.slice(1) };
            return { p: sueltos, como: "sin proyecto", otros: [] };
        };
        const tarjetas = universo.map(id => {
            const x = ix.get(id), fs = fases.get(id) || [], a = asignar(id), revs = fs.filter(f => f.veredicto), ultimaRev = revs.at(-1) || null;
            const t = { id, titulo: x ? tituloCorto(x.titulo) : "", proyecto: a.p.id, asignacion: a.como, fases: fs, resultados: x && Array.isArray(x.resultados) ? x.resultados.length : 0,
                dudas: a.otros.length ? [`También aparece en ${a.otros.map(p => p.nombre).join(", ")}.`] : [], origen: "" };
            if (a.como === "sin proyecto") t.dudas.push("No está en ningún proyecto de proyectos.json: queda en Sueltos.");
            t.inicio = fs.length ? fs[0].ini : null;
            t.ultima = fs.length ? Math.max(...fs.map(f => f.fin)) : null;
            t.escrito = x && Number.isFinite(x.mtime) ? (t.inicio != null ? Math.min(x.mtime, t.inicio) : x.mtime) : t.inicio;
            const ab = abiertoEn.get(id), viva = enCola.get(id);
            if (ab) { t.columna = ab.abiertos.get(id); t.origen = "abiertos"; }
            else if (viva) { t.columna = viva.columna; t.origen = `cola viva ${viva.cola} · ${viva.fase}`; }
            else if (ultimaRev && ultimaRev.veredicto === "DESPLEGABLE") { t.columna = "Done"; t.origen = "DESPLEGABLE"; }
            else if (!fs.length && x && !t.resultados) { t.columna = "Ready"; t.origen = "escrito, sin fases"; }
            else if (fs.length) { t.columna = "Done"; t.sinDesplegable = true; t.origen = "sin DESPLEGABLE"; }
            else if (t.resultados) { t.columna = "Done"; t.sinFechas = true; t.origen = "anterior al historial"; }
            else { t.columna = "Idea"; t.origen = "sin datos"; }
            if (ultimaRev && ultimaRev.veredicto === "DESPLEGABLE") { t.fin = ultimaRev.fin; t.cycle = (t.fin - t.inicio) / DIA; t.lead = (t.fin - t.escrito) / DIA; }
            if (t.columna !== "Done") { t.fin = undefined; t.cycle = undefined; t.lead = undefined; }
            t.abierto = t.columna !== "Done";
            if (t.abierto && t.ultima != null) t.aging = Math.max(0, Math.floor((ahora - t.ultima) / DIA));
            t.nube = /^\d+n$/.test(id) || !!(x && /en la nube/.test(texto(x.titulo)));
            t.bloqueado = t.abierto && new RegExp(`(^|[^\\w])${id}([^\\w]|$)`).test(deProyecto[t.proyecto].bloqueo);
            if (!t.titulo) t.titulo = fs.length ? "sin ficha (sólo historial)" : "sin ficha (sólo proyectos.json)";
            return t;
        });
        const tarjeta = new Map(tarjetas.map(t => [t.id, t]));
        for (const t of tarjetas) if (!ix.has(t.id) && t.id === num(t.id)) { const v = tarjetas.filter(x => x !== t && num(x.id) === t.id).map(x => x.id); if (v.length) t.titulo = `familia ${t.id} (${v.join(", ")})`; }

        // Semanas desde la primera fase hasta ahora.
        const inicios = tarjetas.filter(t => t.inicio != null).map(t => t.inicio), semanas = [];
        if (inicios.length) for (let s = semana(Math.min(...inicios)), fin = semana(ahora); s <= fin && semanas.length < 520; s = masSemanas(s, 1)) semanas.push(s);
        function metricas(ts) {
            const hechas = ts.filter(t => t.fin != null), porSemana = semanas.map(s => hechas.filter(t => semana(t.fin) === s).length);
            const ciclos = hechas.map(t => t.cycle).sort((a, b) => a - b), leads = hechas.map(t => t.lead).sort((a, b) => a - b);
            const fs = ts.flatMap(t => t.fases), total = fs.reduce((n, f) => n + f.min, 0), re = fs.filter(f => RETRABAJO.test(f.fase)).reduce((n, f) => n + f.min, 0);
            const ventana = porSemana.slice(-VENTANA);
            return { hechas: hechas.length, porSemana, ventana, throughput: ventana.length ? ventana.reduce((a, b) => a + b, 0) / ventana.length : 0, ultimaSemana: porSemana.at(-1) ?? 0,
                cycleMediana: cuantil(ciclos, 0.5), cycleP85: cuantil(ciclos, 0.85), leadMediana: cuantil(leads, 0.5), leadP85: cuantil(leads, 0.85), minutos: total, minRetrabajo: re, retrabajo: total ? re / total : null };
        }
        function pronostico(ts, m) {
            const falta = ts.filter(t => t.columna === "Ready" || t.columna === "In progress" || t.columna === "Review").length, hechos = m.ventana.reduce((a, b) => a + b, 0);
            const base = { falta, hechos, semanasVentana: m.ventana.length, muestras: m.ventana };
            if (!falta) return { ...base, estado: "nada" };
            if (hechos < MIN_HECHOS) return { ...base, estado: "insuficiente" };
            const r = azar(SEMILLA), res = [];
            for (let i = 0; i < CORRIDAS; i++) { let s = 0, w = 0; while (s < falta && w < 52) { s += m.ventana[Math.floor(r() * m.ventana.length)]; w++; } res.push(w); }
            res.sort((a, b) => a - b);
            const p80 = cuantil(res, 0.8);
            return { ...base, estado: "ok", p50: cuantil(res, 0.5), p80, p95: cuantil(res, 0.95), semana80: masSemanas(semana(ahora), p80) };
        }
        // Flujo acumulado al cierre de cada semana: el estado de cada tarjeta con lo que pasó hasta esa semana.
        const cfd = semanas.map(s => {
            const c = { semana: s, "In progress": 0, Review: 0, Done: 0, Cerrado: 0 };
            for (const t of tarjetas) {
                if (!t.fases.length || semana(t.inicio) > s) continue;
                if (t.fin != null && semana(t.fin) <= s) c.Done++;
                else if (t.sinDesplegable && semana(t.ultima) <= s) c.Cerrado++;
                else { const u = t.fases.filter(f => semana(f.ini) <= s).at(-1); if (/^rev/.test(u.rol)) c.Review++; else c["In progress"]++; }
            }
            return c;
        });
        const proyectos = P.proyectos.map(p => {
            const ts = tarjetas.filter(t => t.proyecto === p.id).sort((a, b) => RANGO[a.columna] - RANGO[b.columna] || porId(a.id, b.id)), m = metricas(ts);
            const conteo = Object.create(null); for (const c of COLUMNAS) conteo[c] = ts.filter(t => t.columna === c).length;
            return { ...p, tarjetas: ts, metricas: m, pronostico: pronostico(ts, m), conteo, abiertas: ts.filter(t => t.abierto).length };
        }).sort((a, b) => (a.id === "otros") - (b.id === "otros") || b.abiertas - a.abiertas || b.tarjetas.length - a.tarjetas.length);
        const archivos = P.archivos.map(([ruta, encs]) => {
            const abiertos = encs.filter(id => tarjeta.has(id) && tarjeta.get(id).abierto).sort((a, b) => RANGO[tarjeta.get(a).columna] - RANGO[tarjeta.get(b).columna] || porId(a, b));
            return { ruta, corto: ruta.replace(/\/$/, "").split("/").pop() + (ruta.endsWith("/") ? "/" : ""), encargos: encs, abiertos, choque: abiertos.length >= 2 };
        });
        const ordenGlobal = [...new Set(archivos.filter(a => a.choque).flatMap(a => a.abiertos))].sort((a, b) => RANGO[tarjeta.get(a).columna] - RANGO[tarjeta.get(b).columna] || porId(a, b));
        const familias = new Map(); for (const t of tarjetas) { const n = num(t.id); if (!familias.has(n)) familias.set(n, []); familias.get(n).push(t); }
        const repartidas = [...familias].filter(([, ts]) => new Set(ts.map(t => t.proyecto)).size > 1).map(([n, ts]) => ({ numero: n, partes: ts.map(t => [t.id, t.proyecto]) })).sort((a, b) => porId(a.numero, b.numero));
        const conteo = Object.create(null); for (const c of COLUMNAS) conteo[c] = tarjetas.filter(t => t.columna === c).length;
        const enIndice = [...ix.keys()];
        return { COLUMNAS, tope: P.tope, aging: P.aging, errores: P.errores, semanas, tarjetas, tarjeta, proyectos, global: metricas(tarjetas), cfd, archivos, ordenGlobal, repartidas, conteo,
            cobertura: { indice: enIndice.length, enSueltos: enIndice.filter(id => tarjeta.get(id).proyecto === "otros").length, perdidos: enIndice.filter(id => !tarjeta.has(id)) } };
    }

    // El índice de encargos sale de dos `find` de argumentos fijos (ver encargos.js): «mtime nombre» por línea y
    // «ruta:# título» por línea. Un nombre que no calza con NN-slug.md se ignora; nada de esto se ejecuta.
    function indiceDe(listado, titulos) {
        const RE_MD = /^([0-9]{2}[a-z0-9]{0,8})-([A-Za-z0-9._-]{1,120})\.md$/, porArchivo = new Map(), resultados = [];
        for (const l of String(titulos || "").split("\n").slice(0, 5000)) { const m = l.match(/^(?:.*\/)?([^/:]+\.md):(# .*)$/); if (m) porArchivo.set(m[1], m[2]); }
        const encargos = new Map();
        for (const l of String(listado || "").split("\n").slice(0, 5000)) {
            const m = l.match(/^([0-9]+(?:\.[0-9]+)?) (\S+)$/), f = m && m[2].match(RE_MD);
            if (!f) continue;
            if (f[2] === "RESULTADO") { resultados.push(f[1]); continue; }
            if (/^[A-Z]+$/.test(f[2]) || encargos.has(f[1])) continue;              // PLAN y otros en mayúsculas no son encargos
            encargos.set(f[1], { id: f[1], slug: f[2], titulo: porArchivo.get(m[2]) || "", mtime: Math.round(Number(m[1]) * 1000), resultados: [] });
        }
        for (const x of encargos.values()) x.resultados = resultados.filter(r => r.startsWith(x.id));
        return [...encargos.values()];
    }

    return { armar, indiceDe, normalizar, tituloCorto, semana, fecha, ddmm, COLUMNAS, VENTANA, MIN_HECHOS, CORRIDAS };
})();
if (typeof module === "object" && module && module.exports) module.exports = modeloProyectos;
