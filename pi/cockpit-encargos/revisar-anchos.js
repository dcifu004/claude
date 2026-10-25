/*
 * Auditoría repetible de recortes horizontales. SÓLO PARA QA (encargo 84a): copia de
 * encargos/84-maqueta/comun/revisar-anchos.js; index.html no la carga. Pegue este archivo
 * en la consola del navegador con 🧵 Encargos abierta, ajuste el viewport a 1280, 1024,
 * 800, 720 o 375 px y ejecute revisarAnchos(). Cambio respecto de la maqueta: también
 * revisa el riel (aside); el cajón cerrado del teléfono está oculto y no cuenta.
 * El contenido interno de .network-wrap se omite porque ese lienzo tiene desplazamiento
 * horizontal propio (la red llega en la 84b).
 */
"use strict";
(function(){
  const ANCHOS_OBJETIVO=[1280,1024,800,720,375];
  function descriptor(el){
    const id=el.id?`#${el.id}`:"";
    const classes=[...el.classList].slice(0,3).map(c=>`.${c}`).join("");
    return `${el.tagName.toLowerCase()}${id}${classes}`;
  }
  function revisarAnchos(){
    const limite=window.innerWidth+.5;
    const candidatos=[...document.querySelectorAll("header, header *, aside, aside *, main, main *")];
    const fuera=candidatos.filter(el=>{
      if(el.closest(".network-wrap")&&el!==el.closest(".network-wrap"))return false;
      const estilo=getComputedStyle(el),rect=el.getBoundingClientRect();
      if(estilo.display==="none"||estilo.visibility==="hidden"||rect.width===0||rect.height===0)return false;
      return rect.right>limite||rect.left<-.5;
    }).map(el=>{
      const rect=el.getBoundingClientRect();
      return {elemento:descriptor(el),izquierda:Number(rect.left.toFixed(1)),derecha:Number(rect.right.toFixed(1)),exceso:Number(Math.max(rect.right-window.innerWidth,-rect.left).toFixed(1))};
    });
    const resultado={alternativa:document.body.dataset.alt||"—",ancho:window.innerWidth,objetivo:ANCHOS_OBJETIVO.includes(window.innerWidth),estado:fuera.length?"FALLA":"OK",fuera};
    if(fuera.length)console.table(fuera);
    console.log(`[anchos] ${resultado.alternativa.toUpperCase()} · ${resultado.ancho}px · ${resultado.estado} · ${fuera.length} fuera`);
    return resultado;
  }
  window.revisarAnchos=revisarAnchos;
  window.ANCHOS_OBJETIVO=ANCHOS_OBJETIVO;
})();
