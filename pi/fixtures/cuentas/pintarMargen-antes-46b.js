function pintarMargen() {
    const cont = document.getElementById("margen");
    const titulo = el("h2", {}, "⏳ ¿Quién tiene margen?");
    const m = info.margen;
    if (!m) {
        cont.replaceChildren(titulo, el("div", { class: "aviso ojo" },
            "bots-info no trae el margen por cuenta: falta desplegar su versión del encargo 13."));
        return;
    }
    const ventana = (etiqueta, v, umbral) => {
        if (!v) return el("div", { class: "margen-ventana tenue" }, `${etiqueta}: sin dato`);
        const renueva = v.renueva ? cuando(v.renueva) : "";
        if (v.renovada) {
            return el("div", { class: "margen-ventana" },
                el("div", {}, el("strong", {}, etiqueta), ": ya se renovó",
                   renueva ? el("span", { class: "tenue" }, ` (${renueva}) y no se midió desde entonces`) : null),
                barraUso(0, `${etiqueta}: sin medir desde la renovación`));
        }
        const en = v.renueva ? faltan(v.renueva) : "";
        return el("div", { class: "margen-ventana" },
            el("div", {}, el("strong", {}, etiqueta), `: ${pct(v.usado_pct)} usado · `,
               el("strong", {}, `${pct(v.libre_pct)} libre`),
               umbral != null && v.usado_pct >= umbral
                   ? el("span", { class: "estado mal" }, ` · sobre el umbral (${umbral} %)`) : null),
            barraUso(v.usado_pct, `${etiqueta}: ${pct(v.usado_pct)} usado`),
            el("div", { class: "tenue" }, renueva ? `se renueva ${renueva}${en ? ` (${en})` : ""}`
                : "sin ventana abierta: empieza con el próximo uso"));
    };
    // Los proveedores sin cuenta pagada no tienen límite semanal: van en una línea, abajo.
    const gratis = [];
    const tarjetas = m.orden.map(cid => {
        const c = m.cuentas[cid];
        if (!c.pagada) {
            gratis.push(c.nombre);
            return null;
        }
        const rs = c.renueva_semana;
        return el("div", { class: "cuenta-uso margen-cuenta" + (c.sobre ? " sobre" : "") },
            el("h3", {}, c.nombre,
               cid === m.con_margen ? el("span", { class: "insignia ok" }, "la con más margen") : null,
               c.sobre ? el("span", { class: "insignia", title: "Pasó el umbral: el bot la salta y usa la siguiente de la cadena" },
                   "el bot la salta") : null),
            ventana("5 h", c.ventana_5h, c.umbral_5h),
            ventana("Semana", c.semanal, c.umbral_semanal),
            // Sin límite semanal medido, la renovación sale del ciclo con que se reparte el precio.
            rs && rs.origen !== "medido" ? el("div", { class: "tenue" },
                `semana: próxima renovación ${cuando(rs.cuando)} `,
                el("span", { class: "insignia" }, rs.origen === "registro" ? "del registro" : "supuesta")) : null,
            el("div", { class: "tenue" }, c.momento ? `medido ${hace(c.momento)}` : "sin medición",
               c.viejo ? " · dato viejo" : ""));
    });
    const mejor = m.con_margen && m.cuentas[m.con_margen];
    cont.replaceChildren(titulo,
        el("p", { class: mejor ? "" : "tenue" }, mejor
            ? [el("strong", {}, mejor.nombre), ` es la que tiene más margen: ${pct(mejor.libre_pct)} libre `,
               "en su ventana más apretada."]
            : "Ninguna cuenta pagada tiene margen medido bajo el umbral."),
        el("div", { class: "rejilla tres" }, tarjetas),
        gratis.length ? el("p", { class: "tenue" }, `Sin cuenta pagada (no tienen límite semanal ni renovación): ${gratis.join(", ")}. `,
            "Su límite es el gratis de cada proveedor, por minuto o por día; al llegar, el bot pasa al siguiente de la cadena.") : null,
        el("p", { class: "tenue" }, "El % es del límite de la cuenta entera (bots, sesiones de la Pi y los PC ",
           "que reportan), leído de uso.json. «El bot la salta» usa el umbral global de la cuenta; una ",
           "receta de ruta puede ponerle excepción (abajo)."));
    aplicarAnchos(cont);
}

