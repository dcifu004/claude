/* Lógica pura de recomendación de Nexus. Sin red, DOM ni efectos secundarios. */
(function (root, factory) {
    "use strict";
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    root.NexusLogic = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const RUTAS = {
        claude: { nombre: "Claude", proveedor: "Anthropic", foco: "razonamiento y trabajo con vault autorizado", salida: "externa autorizada" },
        codex: { nombre: "Codex", proveedor: "OpenAI", foco: "programación, mantenimiento y razonamiento técnico", salida: "externa autorizada" },
        web: { nombre: "Ruta web", proveedor: "Codex o Claude", foco: "investigación con acceso web y fallback controlado", salida: "externa, sin memoria personal" },
        gpt: { nombre: "Groq", proveedor: "Groq", foco: "respuesta general rápida y tareas sin vault", salida: "externa, sin vault" },
        sql: { nombre: "SQL", proveedor: "Nodo PI", foco: "consultas estructuradas autorizadas", salida: "local" },
        ha: { nombre: "Home Assistant", proveedor: "Nodo PI", foco: "estado y acciones del hogar", salida: "local" },
    };

    function perfil(info, id) {
        return info && info.perfiles && info.perfiles[id] ? info.perfiles[id] : { toml: {}, servicio: {}, cuentas: {} };
    }

    function permitida(p, ruta) {
        return Array.isArray(p.toml && p.toml.rutas) && p.toml.rutas.includes(ruta);
    }

    function disponible(p, ruta) {
        if (!permitida(p, ruta)) return { estado: "bloqueada", detalle: "la ruta no está autorizada para este perfil" };
        if ((p.servicio || {}).ActiveState && p.servicio.ActiveState !== "active") {
            return { estado: "caida", detalle: "el servicio del perfil no está activo" };
        }
        if (ruta === "claude" && !(p.cuentas || {}).claude) return { estado: "no_verificada", detalle: "cuenta Claude no verificada" };
        if (ruta === "codex" && !(p.cuentas || {}).codex) return { estado: "no_verificada", detalle: "codex-home no verificado" };
        if (ruta === "web") {
            if ((p.toml || {}).web_codex && (p.cuentas || {}).codex) return { estado: "disponible", detalle: "Codex con fallback a Claude" };
            if ((p.cuentas || {}).claude_web || (p.cuentas || {}).claude) return { estado: "disponible", detalle: "Claude para búsqueda web" };
            return { estado: "no_verificada", detalle: "cuenta web no verificada" };
        }
        if (ruta === "gpt") return { estado: "configurada", detalle: "Groq detrás del router n8n; salud directa pendiente" };
        return { estado: "disponible", detalle: "ruta autorizada" };
    }

    function candidatos(tarea, prioridad, datos) {
        if (datos === "local") return [];
        if (tarea === "investigacion") return ["web", "claude"];
        if (tarea === "automatizacion" && prioridad === "velocidad" && datos === "sin_vault") {
            return ["gpt", "codex", "claude"];
        }
        if (tarea === "automatizacion") return prioridad === "calidad"
            ? ["claude", "codex", "gpt"] : ["codex", "claude", "gpt"];
        if (prioridad === "calidad") return ["claude", "codex"];
        return ["codex", "claude"];
    }

    function razones(entrada, ruta, estado) {
        const r = [];
        if (entrada.tarea === "programacion") r.push(ruta === "codex" ? "Especializado en programación y mantenimiento." : "Buen razonamiento para revisar decisiones técnicas.");
        if (entrada.tarea === "investigacion") r.push("Usa la ruta web gobernada y conserva el fallback existente.");
        if (entrada.tarea === "automatizacion") r.push(ruta === "gpt" ? "Prioriza baja latencia para una tarea sin vault." : "Favorece razonamiento y cambios técnicos trazables.");
        r.push(`Prioridad seleccionada: ${entrada.prioridad}.`);
        r.push(`Estado observado: ${estado.detalle}.`);
        if (entrada.datos === "vault") r.push("Sólo considera rutas autorizadas para trabajar con el vault del perfil.");
        if (entrada.datos === "sin_vault") r.push("La recomendación asume que no se enviará contenido del vault.");
        return r;
    }

    function recomendar(entrada, info) {
        const p = perfil(info, entrada.perfil);
        if (entrada.datos === "local") {
            return {
                posible: false,
                titulo: "Sin ruta de modelo completamente local",
                explicacion: "Claude, Codex y Groq requieren salida a un proveedor. Nexus no debe relajar esta condición.",
                advertencia: "Mantén la tarea local o incorpora en otra etapa un modelo local aprobado.",
                razones: ["La política elegida prohíbe que los datos salgan del nodo."],
            };
        }
        const lista = candidatos(entrada.tarea, entrada.prioridad, entrada.datos);
        const evaluados = lista.map(ruta => ({ ruta, estado: disponible(p, ruta) }));
        const aptos = evaluados.filter(x => !["bloqueada", "caida"].includes(x.estado.estado));
        if (!aptos.length) {
            return {
                posible: false,
                titulo: "No hay una ruta autorizada disponible",
                explicacion: "El perfil o su servicio no permite las rutas adecuadas para esta tarea.",
                advertencia: "Nexus sólo informa; cualquier ampliación debe tramitarse como propuesta confirmada.",
                razones: evaluados.map(x => `${RUTAS[x.ruta].nombre}: ${x.estado.detalle}.`),
            };
        }
        const principal = aptos[0];
        const alternativa = aptos[1] || null;
        const meta = RUTAS[principal.ruta];
        return {
            posible: true,
            ruta: principal.ruta,
            titulo: meta.nombre,
            proveedor: meta.proveedor,
            foco: meta.foco,
            salida: meta.salida,
            estado: principal.estado,
            alternativa: alternativa ? {
                ruta: alternativa.ruta,
                titulo: RUTAS[alternativa.ruta].nombre,
                estado: alternativa.estado,
            } : null,
            razones: razones(entrada, principal.ruta, principal.estado),
            advertencia: principal.estado.estado === "no_verificada"
                ? "La ruta está permitida, pero su disponibilidad no pudo verificarse."
                : null,
        };
    }

    function usoPorRuta(info) {
        const total = {};
        for (const p of Object.values((info && info.perfiles) || {})) {
            for (const [ruta, cantidad] of Object.entries(p.uso_hoy || {})) {
                total[ruta] = (total[ruta] || 0) + Number(cantidad || 0);
            }
        }
        return Object.entries(total).map(([ruta, cantidad]) => ({ ruta, cantidad }))
            .sort((a, b) => b.cantidad - a.cantidad || a.ruta.localeCompare(b.ruta));
    }

    return { RUTAS, perfil, permitida, disponible, candidatos, recomendar, usoPorRuta };
}));
