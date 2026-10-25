/* Auditoría del layout SVG: cruces y margen mínimo por capa. */
"use strict";
(function(){
  const cruza=(a,b)=>a.left<b.right-.25&&a.right>b.left+.25&&a.top<b.bottom-.25&&a.bottom>b.top+.25;
  function revisarNodos(){
    const xs=[...document.querySelectorAll("#network .node rect")].map(el=>({el,nodo:el.closest(".node")?.dataset.node||"nodo",capa:el.closest(".node")?.dataset.layer||"?",caja:el.getBoundingClientRect()})),cruces=[],margenesMenoresA8=[];
    for(let i=0;i<xs.length;i++)for(let j=i+1;j<xs.length;j++)if(cruza(xs[i].caja,xs[j].caja))cruces.push([xs[i].nodo,xs[j].nodo]);
    for(const capa of new Set(xs.map(x=>x.capa))){const ns=xs.filter(x=>x.capa===capa).sort((a,b)=>a.caja.top-b.caja.top);for(let i=1;i<ns.length;i++){const margen=ns[i].caja.top-ns[i-1].caja.bottom;if(margen<7.9)margenesMenoresA8.push([ns[i-1].nodo,ns[i].nodo,+margen.toFixed(1)])}}
    const out={alternativa:"V2",ancho:innerWidth,nodos:xs.length,cruces,margenesMenoresA8,estado:cruces.length||margenesMenoresA8.length?"FALLA":"OK"};if(cruces.length)console.table(cruces);if(margenesMenoresA8.length)console.table(margenesMenoresA8);console.log(`[nodos] V2 · ${innerWidth}px · ${out.estado} · ${xs.length} nodos · ${cruces.length} cruces · ${margenesMenoresA8.length} márgenes < 8 px`);return out;
  }
  window.revisarNodos=revisarNodos;
})();
