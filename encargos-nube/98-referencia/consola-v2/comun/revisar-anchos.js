/* Auditoría repetible de recortes. La red se excluye porque tiene scroll propio. */
"use strict";
(function(){
  const OBJETIVOS=[1280,1024,800,720,375];
  const nombre=el=>el.tagName.toLowerCase()+(el.id?`#${el.id}`:"")+[...el.classList].slice(0,2).map(x=>`.${x}`).join("");
  function revisarAnchos(){
    const limite=innerWidth+.5,els=[...document.querySelectorAll(".topbar,.topbar *,main,main *,.mock-controls,.mock-controls *")];
    const fuera=els.filter(el=>{if(el.closest(".network-wrap")&&el!==el.closest(".network-wrap"))return false;if(el.closest(".tabs")&&el!==el.closest(".tabs"))return false;const s=getComputedStyle(el),r=el.getBoundingClientRect();if(s.display==="none"||s.visibility==="hidden"||r.width===0||r.height===0)return false;return r.right>limite||r.left<-.5}).map(el=>{const r=el.getBoundingClientRect();return{elemento:nombre(el),izquierda:+r.left.toFixed(1),derecha:+r.right.toFixed(1),exceso:+Math.max(r.right-innerWidth,-r.left).toFixed(1)}});
    const out={alternativa:"V2",ancho:innerWidth,objetivo:OBJETIVOS.includes(innerWidth),estado:fuera.length?"FALLA":"OK",fuera};if(fuera.length)console.table(fuera);console.log(`[anchos] V2 · ${innerWidth}px · ${out.estado} · ${fuera.length} fuera`);return out;
  }
  window.revisarAnchos=revisarAnchos;window.ANCHOS_OBJETIVO=OBJETIVOS;
})();
