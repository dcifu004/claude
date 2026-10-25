/* Adaptación para la maqueta del motor instalado cockpit-encargos/red.js.
 * Conserva su red de cinco capas, arco de retrabajo, foco, luces con tope y layout sin cruces.
 */
"use strict";
(function(){
  const NS="http://www.w3.org/2000/svg",MAX_LIGHTS=120,REWORK=/^(fix\d*|rev([2-9]|\d{2,})|plan2|revplan2)$/;
  const LAYERS=["Cuenta","Modelo · esfuerzo","Naturaleza · rol","Encargo","Resultado"];
  const W=[136,154,204,136,168],H=[38,38,26,38,38],GAP=9,MARGIN_Y=36,MARGIN_X=104,ARC=68,SAMPLES=64;
  const COLORS={claude_diego:"c-claude_diego",claude_cami:"c-claude_cami",codex:"c-codex"};
  const state={svg:null,rows:[],graph:null,particles:[],raf:0,lights:true,visible:true,mode:"ambient",focus:null,observer:null};
  const svg=(tag,attrs={})=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));return n};
  const clean=v=>String(v??"").trim()||"sin datos";
  const short=(s,n)=>s.length>n?`${s.slice(0,n-1)}…`:s;
  const account=id=>({claude_diego:"Claude (Diego)",claude_cami:"Claude (Cami)",codex:"Codex"}[id]||clean(id));
  const model=x=>{const raw=clean(x.modelo).replace(/^claude-/,"").replace(/^gpt-/,"GPT ").replace(/(\d+)-(\d+)/g,"$1.$2");const name=raw.split("-").map(p=>p?`${p[0].toUpperCase()}${p.slice(1)}`:p).join(" ");return x.esfuerzo?`${name} · ${x.esfuerzo}`:name};
  const role=x=>{const r=x.rol||((/^(autor|rev|fix)/.exec(clean(x.fase))||[])[1]);return `${clean(x.naturaleza)} · ${{autor:"autor",rev:"revisión",fix:"arreglo"}[r]||r||clean(x.fase).replace(/\d+$/,"")}`};
  const result=(rows,live)=>live?"En curso":rows.some(x=>x.sin_cuota)?"Pausa por falta de cuota":rows.some(x=>REWORK.test(clean(x.fase)))?"Retrabajo":rows.some(x=>x.fase==="rev1"&&String(x.veredicto).toUpperCase()==="DESPLEGABLE")?"Verde a la primera":"Detenido o rechazado";
  function build(rows){
    const byTask=new Map();rows.forEach(x=>{const k=clean(x.encargo);if(!byTask.has(k))byTask.set(k,[]);byTask.get(k).push(x)});
    const ordered=[...byTask].sort((a,b)=>Date.parse(b[1].at(-1)?.inicio||0)-Date.parse(a[1].at(-1)?.inicio||0));
    const keep=new Set(ordered.length>12?ordered.slice(0,11).map(x=>x[0]):ordered.map(x=>x[0])),others=Math.max(0,ordered.length-keep.size);
    const outcomes=new Map([...byTask].map(([k,v])=>[k,result(v,v.some(x=>x._live))]));
    const layers=LAYERS.map(()=>new Map()),links=new Map();
    const node=(layer,key,label,cls="")=>{if(!layers[layer].has(key))layers[layer].set(key,{id:`${layer}:${key}`,layer,label,cls,total:0,rows:new Set(),live:false});return layers[layer].get(key)};
    rows.forEach((x,i)=>{
      const task=clean(x.encargo),nodes=[node(0,clean(x.cuenta),account(x.cuenta),COLORS[x.cuenta]||"c-other"),node(1,model(x),model(x)),node(2,role(x),role(x)),keep.has(task)?node(3,task,`Encargo ${task}`):node(3," others",`Otros (${others} encargos)`),node(4,outcomes.get(task),outcomes.get(task),outcomes.get(task)==="Retrabajo"?"rework":"")];
      const value=Math.max(.1,Number(x.min)||0);nodes.forEach(n=>{n.total+=value;n.rows.add(i);n.live||=!!x._live});
      for(let c=0;c<4;c++){const k=`${nodes[c].id}>${nodes[c+1].id}`;if(!links.has(k))links.set(k,{id:k,a:nodes[c],b:nodes[c+1],value:0,rows:new Set(),cls:COLORS[x.cuenta]||"c-other",live:false});const e=links.get(k);e.value+=value;e.rows.add(i);e.live||=!!x._live}
    });
    const retried=rows.map((x,i)=>[x,i]).filter(([x])=>REWORK.test(clean(x.fase)));let back=null;
    if(retried.length&&layers[4].has("Retrabajo")){const counts=new Map();retried.forEach(([x])=>counts.set(role(x),(counts.get(role(x))||0)+(Number(x.min)||.1)));const target=layers[2].get([...counts].sort((a,b)=>b[1]-a[1])[0][0]);back={id:"back",a:layers[4].get("Retrabajo"),b:target,value:retried.reduce((n,[x])=>n+(Number(x.min)||0),0),rows:new Set(retried.map(([,i])=>i)),cls:"rework",live:false}}
    return{rows,layers,links:[...links.values()],back};
  }
  function layout(g,width){const need=Math.max(...g.layers.map((m,c)=>m.size*H[c]+Math.max(0,m.size-1)*GAP));const height=MARGIN_Y*2+Math.max(need,310)+ARC,step=(width-MARGIN_X*2)/4;g.layers.forEach((m,c)=>{const ns=[...m.values()].sort((a,b)=>b.total-a.total||a.label.localeCompare(b.label,"es",{numeric:true})),free=height-ARC-MARGIN_Y*2-H[c],jump=ns.length>1?free/(ns.length-1):0;ns.forEach((n,i)=>Object.assign(n,{w:W[c],h:H[c],x:MARGIN_X+c*step,y:MARGIN_Y+H[c]/2+(ns.length>1?i*jump:free/2)}))});return height}
  function curve(p0,p1,p2,p3){const at=t=>{const u=1-t;return[u*u*u*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t*t*t*p3[0],u*u*u*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t*t*t*p3[1]]};return{d:`M${p0} C${p1} ${p2} ${p3}`,samples:Array.from({length:SAMPLES+1},(_,i)=>at(i/SAMPLES))}}
  function pathFor(e,height){if(e.id==="back"){const a=[e.a.x-e.a.w/2+18,e.a.y+e.a.h/2],b=[e.b.x,e.b.y+e.b.h/2];return curve(a,[a[0]-30,height-30],[b[0]+60,height-30],b)}const x1=e.a.x+e.a.w/2,x2=e.b.x-e.b.w/2,c=(x2-x1)*.5;return curve([x1,e.a.y],[x1+c,e.a.y],[x2-c,e.b.y],[x2,e.b.y])}
  const intersects=(a,b)=>{for(const x of a)if(b.has(x))return true;return false};
  function draw(){
    cancelAnimationFrame(state.raf);state.raf=0;state.particles=[];const root=state.svg;if(!root)return;root.replaceChildren();const width=Math.max(1160,Math.floor(root.parentElement?.clientWidth||1160)),g=build(state.rows),height=layout(g,width);state.graph=g;root.setAttribute("viewBox",`0 0 ${width} ${height}`);root.setAttribute("width",width);root.setAttribute("height",height);
    const defs=svg("defs"),marker=svg("marker",{id:"network-arrow",viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:6,markerHeight:6,orient:"auto"});marker.append(svg("path",{d:"M0 0L10 5L0 10z",class:"network-arrow"}));defs.append(marker);const heads=svg("g"),linkLayer=svg("g"),lightLayer=svg("g",{class:"network-lights","aria-hidden":"true"}),nodeLayer=svg("g");root.append(defs,heads,linkLayer,lightLayer,nodeLayer);
    g.layers.forEach((m,c)=>{const first=[...m.values()][0],t=svg("text",{x:first?first.x:MARGIN_X,y:16,class:"network-layer","text-anchor":"middle"});t.textContent=LAYERS[c];heads.append(t)});
    const max=Math.max(1,...g.links.map(e=>e.value)),all=[...g.links,...(g.back?[g.back]:[])];
    all.sort((a,b)=>b.value-a.value).forEach(e=>{const p=pathFor(e,height);e.samples=p.samples;e.path=svg("path",{d:p.d,class:`network-link ${e.cls}${e.live?" live":""}`,"stroke-width":e.id==="back"?2:(1.2+6*Math.sqrt(e.value/max)).toFixed(2),"stroke-opacity":e.id==="back"?.85:.46,"marker-end":"url(#network-arrow)"});const hit=svg("path",{d:p.d,class:"network-hit",tabindex:0,role:"button","aria-label":e.id==="back"?`Retrabajo hacia ${e.b.label}`:`${e.a.label} a ${e.b.label}`});const choose=()=>{state.focus=state.focus?.id===e.id?null:e;state.mode=state.focus?"focus":state.mode==="focus"?"ambient":state.mode;applyFocus()};hit.addEventListener("click",choose);hit.addEventListener("keydown",ev=>{if(ev.key==="Enter"||ev.key===" "){ev.preventDefault();choose()}});linkLayer.append(e.path,hit)});
    if(g.back){const t=svg("text",{x:(g.back.a.x+g.back.b.x)/2,y:height-7,class:"network-back-label","text-anchor":"middle"});t.textContent="↺ retrabajo vuelve a arreglo y revisión";linkLayer.append(t)}
    g.layers.flatMap(m=>[...m.values()]).forEach(n=>{const group=svg("g",{class:`node network-node ${n.cls}${n.live?" live":""}`,transform:`translate(${(n.x-n.w/2).toFixed(1)} ${(n.y-n.h/2).toFixed(1)})`,tabindex:0,role:"button","data-node":n.id,"data-layer":n.layer,"aria-label":`${n.label}, ${n.rows.size} fases, ${Math.round(n.total)} minutos`});group.append(svg("rect",{width:n.w,height:n.h,rx:7}));const main=svg("text",{x:8,y:n.layer===2?17:16,class:"node-main"});main.textContent=short(n.label,Math.floor((n.w-16)/6.2));group.append(main);if(n.layer!==2){const sub=svg("text",{x:8,y:n.h-7,class:"node-sub"});sub.textContent=`${n.rows.size} fases · ${Math.round(n.total)} min`;group.append(sub)}const choose=()=>{state.focus=state.focus?.id===n.id?null:n;state.mode=state.focus?"focus":state.mode==="focus"?"ambient":state.mode;applyFocus()};group.addEventListener("click",choose);group.addEventListener("keydown",ev=>{if(ev.key==="Enter"||ev.key===" "){ev.preventDefault();choose()}});n.el=group;nodeLayer.append(group)});
    state.lightLayer=lightLayer;applyFocus();
  }
  function activeRows(){if(state.mode==="focus"&&state.focus)return state.focus.rows;if(state.mode==="live")return new Set(state.rows.map((x,i)=>x._live?i:-1).filter(i=>i>=0));return null}
  function applyFocus(){const selected=activeRows(),g=state.graph;if(!g)return;g.layers.flatMap(m=>[...m.values()]).forEach(n=>{n.el.classList.toggle("dim",!!selected&&!intersects(n.rows,selected));n.el.classList.toggle("selected",state.focus?.id===n.id)});[...g.links,...(g.back?[g.back]:[])].forEach(e=>{e.path.classList.toggle("dim",!!selected&&!intersects(e.rows,selected));e.path.classList.toggle("selected",!!selected&&intersects(e.rows,selected))});makeLights();window.dispatchEvent(new CustomEvent("flowmode",{detail:{mode:state.mode}}))}
  function makeLights(){state.particles=[];if(!state.lightLayer)return;state.lightLayer.replaceChildren();if(!state.lights||matchMedia("(prefers-reduced-motion: reduce)").matches)return;const chosen=activeRows(),links=[...state.graph.links,...(state.graph.back?[state.graph.back]:[])].filter(e=>!chosen||intersects(e.rows,chosen));const cand=[];links.sort((a,b)=>b.value-a.value).forEach((e,k)=>{const count=e.live&&state.mode==="live"?7:Math.min(6,Math.max(1,Math.round(1+4*Math.sqrt(e.value/Math.max(1,...state.graph.links.map(x=>x.value))))));for(let i=0;i<count;i++)cand.push({e,phase:(i/count+(k*.137)%1)%1})});cand.slice(0,MAX_LIGHTS).forEach(c=>{const halo=svg("circle",{r:5,class:`network-halo ${c.e.cls}`}),dot=svg("circle",{r:2.3,class:`network-light ${c.e.cls}`});state.lightLayer.append(halo,dot);state.particles.push({...c,halo,dot})});animate(performance.now())}
  function animate(now){state.raf=0;if(!state.lights||!state.visible||document.hidden||matchMedia("(prefers-reduced-motion: reduce)").matches)return;const base=(now%2200)/2200;state.particles.forEach(p=>{const q=p.e.samples[Math.min(SAMPLES,Math.floor(((p.phase+base)%1)*SAMPLES))];p.halo.setAttribute("cx",q[0].toFixed(1));p.halo.setAttribute("cy",q[1].toFixed(1));p.dot.setAttribute("cx",q[0].toFixed(1));p.dot.setAttribute("cy",q[1].toFixed(1))});state.raf=requestAnimationFrame(animate)}
  function init(root,rows=[]){state.svg=root;state.rows=rows;state.lights=localStorage.getItem("consola-v2-lights")!=="off";state.focus=null;draw();state.observer?.disconnect();state.observer=new IntersectionObserver(([x])=>{state.visible=x.isIntersecting;if(state.visible&&!state.raf)animate(performance.now())});state.observer.observe(root)}
  function setRows(rows){state.rows=rows;state.focus=null;draw()}
  function setMode(mode){state.mode=mode;state.focus=mode==="focus"?state.focus:null;applyFocus()}
  function toggleLights(){state.lights=!state.lights;localStorage.setItem("consola-v2-lights",state.lights?"on":"off");makeLights();return state.lights}
  document.addEventListener("visibilitychange",()=>{if(!document.hidden&&!state.raf)animate(performance.now())});
  window.NodeFlow={init,setRows,setMode,toggleLights,state,MAX_LIGHTS};
})();
