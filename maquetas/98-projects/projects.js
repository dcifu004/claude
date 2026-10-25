"use strict";
// Pestaña Projects (encargo 98): marco de la consola v2 + las vistas Board (A y B), Conflicts y Flow over time.
// Todo se arma con nodos y textContent (sin innerHTML), para que se pueda llevar a Cockpit con su CSP.
(function(){
  const M=window.MODELO98,F=M.fmt;
  const TOOLS={
    home:{label:"Home",icon:"🏠",tabs:[["state","State"],["inbox","Inbox"],["shortcuts","Shortcuts"]]},
    aiops:{label:"AI Ops",icon:"🏭",tabs:[["flow","Flow"],["runs","Runs"],["projects","Projects"],["approvals","Approvals (HITL)"],["timeline","Timeline"],["traces","Traces"],["scorecard","Scorecard"],["logs","Logs"],["policies","Policies"]]},
    providers:{label:"Providers",icon:"⛽",tabs:[["usage","Usage & Limits"],["capacity","Capacity"],["routing","Model Routing"],["burn","Quota Burn-down"]]},
    agents:{label:"Agents",icon:"👷",tabs:[["registry","Registry"],["sessions","Sessions"],["assistants","Assistants"],["changes","Change Requests"],["memory","Memory health"]]},
    infrastructure:{label:"Infrastructure",icon:"🍇",tabs:[["services","Services"],["backups","Backups"],["schedules","Schedules"],["signals","Signals"]]},
    news:{label:"News",icon:"📰",tabs:[["digest","Digest"],["sources","Sources"],["delivery","Delivery"]]}
  };
  const NATIVE=[["◉","System"],["≡","Logs"],["⚙","Services"],[">_","Terminal"],["▣","Storage"],["⇄","Networking"]];
  const DEFAULT={home:"state",aiops:"projects",providers:"usage",agents:"registry",infrastructure:"services",news:"digest"};
  const main=document.querySelector("#main"),tabs=document.querySelector("#tabs"),tabSelect=document.querySelector("#tab-select"),title=document.querySelector("#tool-title");
  let currentTool="aiops",currentTab="projects",toastTimer=0;
  const abiertosDone=new Set();   // carriles con el Done desplegado

  const h=(tag,attrs={},...children)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs||{})){if(k==="class")n.className=v;else if(k==="style")n.style.cssText=v;else if(k.startsWith("on"))n.addEventListener(k.slice(2),v);else if(v!==false&&v!=null)n.setAttribute(k,String(v))}for(const c of children.flat(Infinity))if(c!=null&&c!==false)n.append(c instanceof Node?c:document.createTextNode(String(c)));return n};
  const SVG="http://www.w3.org/2000/svg";
  const s=(tag,attrs={},...children)=>{const n=document.createElementNS(SVG,tag);for(const [k,v] of Object.entries(attrs||{}))if(v!=null)n.setAttribute(k,String(v));for(const c of children.flat(Infinity))if(c!=null)n.append(c instanceof Node?c:document.createTextNode(String(c)));return n};
  const term=(t,label=t)=>h("span",{"data-term":t},label);
  const fmt=(n,d=1)=>Number(n).toLocaleString("es-CL",{maximumFractionDigits:d});
  const pct=x=>x==null?"—":`${Math.round(x*100)}%`;
  const dur=d=>d==null?"—":d<1/24?`${fmt(d*1440,0)} min`:d<1?`${fmt(d*24)} h`:`${fmt(d)} d`;
  const nombre=id=>M.porId[id]?M.porId[id].nombre:id;

  // ---------- estado de la vista (en el hash) ----------
  function params(){const q=new URLSearchParams(location.hash.split("?")[1]||"");return {v:q.get("v")||"board",b:q.get("b")||"a",f:q.get("f")||"abiertos"}}
  function setParams(cambio){const p={...params(),...cambio};const hash=`#/projects?v=${p.v}&b=${p.b}&f=${p.f}`;if(location.hash!==hash)history.replaceState(null,"",hash);renderProjects()}

  // ---------- marco ----------
  function route(){const raw=location.hash.slice(2)||"projects",[path]=raw.split("?");for(const [tool,def] of Object.entries(TOOLS))if(def.tabs.some(x=>x[0]===path)){currentTool=tool;currentTab=path;return}currentTool="aiops";currentTab="projects"}
  function go(tool,tab=DEFAULT[tool]){location.hash=`#/${tab}`;if(location.hash===`#/${tab}`)render()}
  function buildNav(){
    document.querySelector("#tool-nav").replaceChildren(...Object.entries(TOOLS).map(([id,x])=>h("button",{class:"rail-link",type:"button","data-tool":id,"data-term":x.label,onclick:()=>go(id)},h("span",{class:"rail-icon","aria-hidden":"true"},x.icon),h("span",{class:"rail-label"},x.label))));
    document.querySelector("#native-nav").replaceChildren(...NATIVE.map(([icon,label])=>h("button",{class:"rail-link",type:"button",onclick:()=>toast(`${label}: entrada nativa simulada, sólo lectura.`)},h("span",{class:"rail-icon","aria-hidden":"true"},icon),h("span",{class:"rail-label"},label))));
  }
  function buildTabs(){
    const defs=TOOLS[currentTool].tabs;
    tabs.replaceChildren(...defs.map(([id,label])=>h("button",{class:`tab-button${id===currentTab?" active":""}`,type:"button","data-term":label,onclick:()=>go(currentTool,id)},label,id==="projects"?h("span",{class:"badge"},M.tarjetas.filter(t=>t.abierto).length):null)));
    tabSelect.replaceChildren(...defs.map(([id,label])=>h("option",{value:id},label)));tabSelect.value=currentTab;
    title.textContent=`${TOOLS[currentTool].icon} ${TOOLS[currentTool].label}`;title.dataset.term=TOOLS[currentTool].label;
    document.querySelectorAll("[data-tool]").forEach(x=>x.classList.toggle("active",x.dataset.tool===currentTool));
  }
  function head(kicker,titulo,desc,pill){return h("header",{class:"page-head"},h("div",{},h("p",{class:"eyebrow"},kicker),h("h1",{},term(titulo)),h("p",{},desc)),h("span",{class:"source-pill"},pill))}
  function renderPlaceholder(){const def=TOOLS[currentTool].tabs.find(x=>x[0]===currentTab)||[currentTab,currentTab];
    main.replaceChildren(head(TOOLS[currentTool].label,def[1],"Esta maqueta sólo trae la pestaña Projects; el resto de la consola está en la maqueta v2.","◇ fuera de esta maqueta"),
      h("section",{class:"card placeholder"},h("div",{},h("strong",{},def[1]),h("p",{},"Vuelve a ",h("a",{href:"#/projects"},"🏭 AI Ops → Projects"),"."))))}
  function render(){route();buildTabs();if(currentTab==="projects")renderProjects();else renderPlaceholder();bindTerms();main.focus({preventScroll:true})}

  // ---------- piezas comunes ----------
  function kpis(){
    const g=M.global,rev=M.conteoColumnas.Review,topeRev=M.WIP.Review;
    const item=(label,valor,nota,clase="")=>h("article",{class:`card kpi ${clase}`},h("span",{class:"kpi-label"},term(label)),h("strong",{class:"kpi-value"},valor),h("span",{class:"kpi-note"},nota));
    return h("section",{class:"grid cols-4 kpi-strip","aria-label":"Indicadores de flujo"},
      item("Throughput",`${fmt(g.throughput)}/sem`,`media de ${g.ventana.length} semanas · ésta: ${g.ultimaSemana}`),
      item("Cycle time",dur(g.cycleMediana),`mediana · p85 ${dur(g.cycleP85)} · ${g.hechas} encargos`),
      item("Rework rate",pct(g.retrabajo),`${fmt(g.minRetrabajo,0)} de ${fmt(g.minutos,0)} min en fix y rev2+`),
      item("WIP limit",`${rev}/${topeRev}`,`en Review · tope ${topeRev}`,rev>topeRev?"over":""));
  }
  function seg(label,opciones,actual,onpick){return h("div",{class:"seg",role:"group","aria-label":label},opciones.map(([v,t])=>h("button",{type:"button","aria-pressed":v===actual?"true":"false",onclick:()=>onpick(v)},t)))}
  function badges(t){
    const out=[];
    if(t.nube)out.push(h("span",{class:"badge mini"},"nube"));
    if(t.bloqueado)out.push(h("span",{class:"badge danger mini"},"bloqueado"));
    if(t.aging!=null)out.push(h("span",{class:`badge mini${t.aging>=M.UMBRAL_AGING?" danger":" quiet"}`,"data-term":"Aging"},`${t.aging} d`));
    if(t.sinDesplegable)out.push(h("span",{class:"badge warn mini","data-tip":"Cerrada sin DESPLEGABLE|No está en «abiertos» y su última revisión no fue DESPLEGABLE."},"sin DESPL."));
    if(t.dudas.length)out.push(h("span",{class:"badge warn mini","data-tip":`Duda de asignación|${t.dudas.join(" ")}`},"duda"));
    return out;
  }
  function tarjetaBtn(t){
    return h("button",{class:`pcard${t.abierto?"":" done"}`,type:"button","data-id":t.id,"data-col":t.columna,onclick:()=>abrirTarjeta(t.id),"aria-label":`Encargo ${t.id}: ${t.titulo}`},
      h("span",{class:"pcard-top"},h("strong",{},t.id),badges(t)),
      h("span",{class:"t"},t.titulo),
      t.abierto?null:h("small",{class:"when"},t.fin!=null?`✓ ${F.ddmm(t.fin)}`:t.sinDesplegable?`última fase ${F.ddmm(t.ultima)}`:"sin fases en el historial"));
  }
  function wipRow(){
    return h("div",{class:"wip-row"},M.COLS.map(c=>{const n=M.conteoColumnas[c],tope=M.WIP[c],over=tope!=null&&n>tope;
      return h("span",{class:`wip-chip${over?" over":""}`,"data-term":tope!=null?"WIP limit":null},c," ",h("strong",{},tope!=null?`${n}/${tope}`:n))}));
  }

  // ---------- Board A: carriles por proyecto × columnas ----------
  function boardA(soloAbiertos){
    const cab=h("div",{class:"board-head",role:"row"},h("div",{class:"corner"},"Proyecto · resultado"),M.COLS.map(c=>{const n=M.conteoColumnas[c],tope=M.WIP[c];
      return h("div",{class:"col-head"},c,tope!=null?h("span",{class:`tope${n>tope?" over":""}`,"data-term":"WIP limit"},`${n}/${tope}`):h("span",{class:"tope quiet"},n))}));
    const visibles=M.proyectos.filter(p=>!soloAbiertos||p.abiertas),ocultos=M.proyectos.filter(p=>soloAbiertos&&!p.abiertas);
    const carriles=visibles.map(p=>h("section",{class:"lane","aria-label":p.nombre},
      h("div",{class:"lane-head"},h("h3",{},p.nombre),h("p",{class:"resultado",title:p.resultado},p.resultado),
        h("div",{class:"lane-meta"},h("span",{class:"kpi-note"},`${p.abiertas} abiertos · ${p.conteo.Done} en Done`),p.bloqueo?h("span",{class:"badge danger mini","data-tip":`Bloqueo|${p.bloqueo}`},"⛔ bloqueo"):null)),
      M.COLS.map(c=>{const ts=p.tarjetas.filter(t=>t.columna===c);
        const cell=h("div",{class:`lane-cell${ts.length?"":" vacia"}`,"data-col":c},h("span",{class:"cell-label"},c," · ",ts.length));
        if(c==="Done"&&soloAbiertos){if(ts.length)cell.append(h("span",{class:"done-count"},`✓ ${ts.length}`));return cell}
        if(c==="Done"){const orden=[...ts].sort((a,b)=>(b.fin??b.ultima??0)-(a.fin??a.ultima??0)),abierto=abiertosDone.has(p.id),mostrar=abierto?orden:orden.slice(0,4);
          cell.append(...mostrar.map(tarjetaBtn));if(orden.length>4)cell.append(h("button",{class:"mini-button more",type:"button",onclick:()=>{abierto?abiertosDone.delete(p.id):abiertosDone.add(p.id);renderProjects()}},abierto?"mostrar menos":`+${orden.length-4} más`));return cell}
        cell.append(...ts.map(tarjetaBtn));return cell})));
    return h("section",{class:"card board-card"},wipRow(),h("div",{class:"board-a"},cab,carriles),
      ocultos.length?h("p",{class:"kpi-note"},`Sin abiertos (ocultos con «Sólo abiertos»): ${ocultos.map(p=>`${p.nombre} (${p.conteo.Done})`).join(" · ")}.`):null);
  }

  // ---------- Board B: tarjetas de proyecto con mini-tablero y avance ----------
  function boardB(soloAbiertos){
    const ps=M.proyectos.filter(p=>!soloAbiertos||p.abiertas),ocultos=M.proyectos.filter(p=>soloAbiertos&&!p.abiertas);
    return h("section",{},wipRow(),h("div",{class:"board-b"},ps.map(p=>{
      const total=p.tarjetas.length,done=p.conteo.Done,pr=p.pronostico;
      return h("article",{class:"card proj-card"},
        h("div",{class:"proj-head"},h("h3",{},p.nombre),h("span",{class:`badge${p.abiertas?"":" quiet"}`},`${p.abiertas} abiertos`)),
        h("p",{class:"resultado"},p.resultado),
        h("div",{class:"mini-board","aria-label":"Tarjetas por columna"},M.COLS.map(c=>h("span",{class:`mb${p.conteo[c]?" on":""}`,"data-col":c},h("small",{},c),h("strong",{},p.conteo[c])))),
        h("div",{class:"progress",role:"img","aria-label":`${done} de ${total} en Done`},h("i",{style:`width:${total?Math.round(done/total*100):0}%`})),
        h("span",{class:"kpi-note"},`${done} de ${total} en Done · rework ${pct(p.metricas.retrabajo)}`),
        p.abiertas?h("div",{class:"chips"},p.tarjetas.filter(t=>t.abierto).map(tarjetaBtn)):null,
        p.bloqueo?h("p",{class:"bloqueo"},"⛔ ",p.bloqueo):null,
        h("p",{class:"forecast-line"},term("Forecast"),": ",pr.estado==="ok"?`80 % en ≤ ${pr.p80} sem`:pr.estado==="nada"?"nada pendiente":"datos insuficientes"));
    })),ocultos.length?h("p",{class:"kpi-note"},`Sin abiertos: ${ocultos.map(p=>p.nombre).join(" · ")}.`):null);
  }

  // ---------- Dudas del borrador ----------
  function dudas(){
    const propias=t=>t.dudas.filter(d=>!d.startsWith("No está en «abiertos»"));
    const conDuda=M.tarjetas.filter(t=>propias(t).length),sinDesp=M.tarjetas.filter(t=>t.sinDesplegable);
    const fila=t=>h("li",{},h("button",{class:"link-button",type:"button",onclick:()=>abrirTarjeta(t.id)},t.id)," · ",nombre(t.proyecto),": ",propias(t).join(" "));
    return h("details",{class:"card dudas"},h("summary",{},h("strong",{},"Dudas sobre el borrador"),h("span",{class:"kpi-note"},` · ${conDuda.length} tarjetas marcadas, ${M.familiasRepartidas.length} familias repartidas, ${sinDesp.length} cerradas sin DESPLEGABLE`)),
      h("p",{class:"kpi-note"},"Nada se reasignó: cada tarjeta queda donde la puso el borrador, con la marca «duda». Diego decide."),
      h("h3",{},"Asignación"),h("ul",{},conDuda.map(fila)),
      h("h3",{},"Familias repartidas entre proyectos (puede estar bien)"),h("ul",{},M.familiasRepartidas.map(f=>h("li",{},`${f.numero}: `,f.partes.map(([id,p])=>`${id} → ${nombre(p)}`).join(" · ")))),
      h("h3",{},"Cerradas sin DESPLEGABLE (Done por no estar en «abiertos»)"),h("p",{class:"kpi-note"},sinDesp.map(t=>t.id).join(" · ")));
  }

  // ---------- Conflicts: matriz encargo × archivo ----------
  function conflicts(){
    const A=M.archivos,rango={"Review":0,"In progress":1,"Ready":2,"Idea":3,"Done":4},orden=M.proyectos.map(p=>p.id);
    const filas=M.encargosConArchivo.map(id=>M.tarjeta[id]).filter(Boolean).sort((a,b)=>orden.indexOf(a.proyecto)-orden.indexOf(b.proyecto)||rango[a.columna]-rango[b.columna]);
    const faltan=M.encargosConArchivo.filter(id=>!M.tarjeta[id]);
    let ultimoProyecto=null;
    const tabla=h("table",{class:"matrix"},h("thead",{},h("tr",{},h("th",{scope:"col"},"Proyecto → encargo"),A.map(a=>h("th",{scope:"col",class:a.choque?"hot":"","data-tip":`${a.ruta}|${a.abiertos.length} abiertos lo tocan${a.choque?": choque":""}.`},h("code",{},a.corto),a.choque?h("span",{class:"badge danger mini"},`${a.abiertos.length} abiertos`):null)))),
      h("tbody",{},filas.map(t=>{const nuevo=t.proyecto!==ultimoProyecto;ultimoProyecto=t.proyecto;
        return h("tr",{class:`${nuevo?"grupo ":""}${t.abierto?"":"cerrado"}`},
          h("th",{scope:"row"},nuevo?h("small",{class:"proj-name"},nombre(t.proyecto)):null,h("button",{class:"link-button",type:"button",onclick:()=>abrirTarjeta(t.id)},t.id),h("span",{class:`status mini ${t.abierto?"warn":""}`},t.columna)),
          A.map(a=>{const toca=a.encargos.includes(t.id),hot=toca&&a.choque&&t.abierto;
            return h("td",{class:hot?"hot":""},toca?h("span",{class:`dot${t.abierto?"":" hollow"}`,"aria-label":`${t.id} toca ${a.ruta}`},t.abierto?"●":"✓"):"")}))})));
    const choques=A.filter(a=>a.choque),sinChoque=A.filter(a=>!a.choque);
    return h("section",{class:"grid conflicts"},
      h("article",{class:"card"},h("h2",{},term("Conflicts")," · encargo × archivo"),
        h("p",{class:"kpi-note"},"Filas agrupadas por proyecto; columnas = archivos compartidos conocidos (borrador). ● abierto · ✓ ya en Done. En rojo, los archivos que tocan dos o más encargos abiertos."),
        h("p",{class:"kpi-note matrix-hint"},"La matriz se desliza hacia el lado →"),h("div",{class:"matrix-wrap"},tabla),faltan.length?h("p",{class:"kpi-note"},`En la lista pero sin tarjeta: ${faltan.join(", ")}.`):null),
      h("article",{class:"card"},h("h2",{},"Qué hacer"),
        h("ol",{class:"todo"},choques.map(a=>h("li",{},h("code",{},a.ruta),h("span",{}," — traer de a uno: "),h("strong",{},a.abiertos.join(" → "))))),
        h("p",{},"Orden sugerido para todo: ",h("strong",{},M.ordenGlobal.join(" → "))),
        h("p",{class:"kpi-note"},"Regla: primero lo que está en Review (más cerca de mezclarse), después In progress, Ready e Idea; a igual columna, por número. Cada uno se mezcla y se prueba antes de traer el siguiente."),
        sinChoque.length?h("p",{class:"kpi-note"},"Sin choque: ",sinChoque.map(a=>`${a.ruta} (${a.abiertos.join(", ")||"nada abierto"})`).join(" · "),"."):null));
  }

  // ---------- Flow over time ----------
  const BANDAS=[["Done","Done","cfd-done"],["Cerrado","Cerrado sin DESPLEGABLE","cfd-closed"],["Review","Review","cfd-rev"],["In progress","In progress","cfd-prog"]];
  function cfdSvg(){
    const datos=M.cfd,W=640,H=270,ml=34,mr=118,mt=12,mb=30,iw=W-ml-mr,ih=H-mt-mb;
    const total=d=>BANDAS.reduce((n,[k])=>n+d[k],0),max=Math.max(...datos.map(total)),paso=max>60?20:10,tope=Math.ceil(max/paso)*paso;
    const y=v=>mt+ih-v/tope*ih,band=iw/datos.length,bw=Math.min(64,band*.62);
    const svg=s("svg",{class:"cfd-svg",viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":"Flujo acumulado por semana"},
      s("defs",{},s("pattern",{id:"rayado",width:6,height:6,patternUnits:"userSpaceOnUse",patternTransform:"rotate(45)"},s("rect",{width:6,height:6,class:"cfd-closed-bg"}),s("line",{x1:0,y1:0,x2:0,y2:6,class:"cfd-closed-line"}))));
    for(let v=0;v<=tope;v+=paso)svg.append(s("line",{x1:ml,x2:ml+iw,y1:y(v),y2:y(v),class:"grid-line"}),s("text",{x:ml-6,y:y(v)+3,class:"axis","text-anchor":"end"},v));
    datos.forEach((d,i)=>{const x=ml+band*i+(band-bw)/2;let acc=0;
      for(const [k,label,cls] of BANDAS){const v=d[k];if(!v)continue;const y0=y(acc),y1=y(acc+v);acc+=v;
        svg.append(s("rect",{x,y:y1+1,width:bw,height:Math.max(0,y0-y1-2),rx:2,class:`seg ${cls}`,tabindex:0,"data-tip":`Semana del ${F.ddmm(d.semana)}|${label}: ${v} encargos al ${F.ddmm(d.corte)} ${F.hhmm(d.corte)}`}))}
      svg.append(s("text",{x:x+bw/2,y:H-mb+16,class:"axis","text-anchor":"middle"},F.ddmm(d.semana)),s("text",{x:x+bw/2,y:y(total(d))-4,class:"axis total","text-anchor":"middle"},total(d)))});
    // Etiquetas directas en la última semana.
    const ult=datos[datos.length-1],xl=ml+band*(datos.length-1)+(band+bw)/2+8;let acc=0,ultimoY=Infinity;
    for(const [k,label] of BANDAS){const v=ult[k];if(!v){continue}const yc=Math.min(ultimoY-12,y(acc+v/2)+3);ultimoY=yc;acc+=v;svg.append(s("text",{x:xl,y:yc,class:"direct"},`${label} ${v}`))}
    return svg;
  }
  function cfdTabla(){
    return h("details",{class:"tabla-cfd"},h("summary",{},"Ver como tabla"),h("div",{class:"table-wrap"},h("table",{class:"data-table"},
      h("thead",{},h("tr",{},h("th",{},"Semana"),BANDAS.map(([,l])=>h("th",{},l)),h("th",{},term("Throughput")))),
      h("tbody",{},M.cfd.map((d,i)=>h("tr",{},h("td",{},F.ddmm(d.semana)),BANDAS.map(([k])=>h("td",{},d[k])),h("td",{},M.global.porSemana[i])))))));
  }
  function nowNextLater(){
    const ps=M.proyectos.filter(p=>p.abiertas||p.ideas.length);
    const chip=t=>h("button",{class:"nnl-chip",type:"button",onclick:()=>abrirTarjeta(t.id),"data-col":t.columna},h("strong",{},t.id),` ${t.columna}`);
    return h("div",{class:"nnl-grid"},ps.map(p=>{const now=p.tarjetas.filter(t=>["In progress","Review"].includes(t.columna)),next=p.tarjetas.filter(t=>t.columna==="Ready"),later=p.tarjetas.filter(t=>t.columna==="Idea");
      return h("article",{class:"card nnl"},h("h3",{},p.nombre),h("div",{class:"nnl-cols"},
        h("div",{},h("small",{},"Now"),now.length?now.map(chip):h("span",{class:"kpi-note"},"—")),
        h("div",{},h("small",{},"Next"),next.length?next.map(chip):h("span",{class:"kpi-note"},"—")),
        h("div",{},h("small",{},"Later"),later.map(chip),p.ideas.map(i=>h("span",{class:"idea"},i)),!later.length&&!p.ideas.length?h("span",{class:"kpi-note"},"—"):null)))}));
  }
  function forecast(){
    const ps=M.proyectos.filter(p=>p.pronostico.estado!=="nada"),nada=M.proyectos.filter(p=>p.pronostico.estado==="nada");
    const metodo=pr=>`Método|Monte Carlo, 10.000 corridas con semilla fija: cada semana futura toma al azar una de las últimas ${pr.semanasVentana} semanas reales del proyecto (${pr.muestras.join(", ")} terminados) hasta cubrir lo que falta (${pr.falta}: Ready + In progress + Review). Las ideas no cuentan. Con menos de ${M.MIN_DONE} terminados en la ventana no se pronostica.`;
    return h("div",{class:"forecast-grid"},ps.map(p=>{const pr=p.pronostico;
      return h("article",{class:`card fc ${pr.estado}`},h("div",{class:"proj-head"},h("h3",{},p.nombre),h("span",{class:"info","data-tip":metodo(pr),tabindex:0,"aria-label":"Cómo se calcula"},"ⓘ método")),
        h("span",{class:"kpi-note"},`Falta ${pr.falta} · ${pr.hechasVentana} terminados en ${pr.semanasVentana} semanas`),
        pr.estado==="ok"?h("div",{class:"fc-bars"},[[50,pr.p50],[80,pr.p80],[95,pr.p95]].map(([q,n])=>h("div",{class:"fc-row"},h("span",{},`${q} %`),h("i",{style:`--w:${Math.min(100,n/Math.max(4,pr.p95)*100)}%`}),h("strong",{},`≤ ${n} sem`))),
          h("p",{class:"kpi-note"},`80 %: terminado antes del fin de la semana del ${F.ddmm(pr.hasta80)}.`))
        :h("p",{class:"notice"},`Datos insuficientes: ${pr.hechasVentana} encargo${pr.hechasVentana===1?"":"s"} terminado${pr.hechasVentana===1?"":"s"} en la ventana (mínimo ${M.MIN_DONE}). Sin fechas.`))}),
      nada.length?h("p",{class:"kpi-note nada"},`Sin pendientes que pronosticar: ${nada.map(p=>p.nombre).join(" · ")}.`):null);
  }
  function flowOverTime(){
    const conFases=M.tarjetas.filter(t=>t.fases.length).length;
    return h("section",{class:"flow-time"},
      h("article",{class:"card"},h("div",{class:"network-head"},h("div",{},h("h2",{},term("Cumulative flow")," por semana"),h("span",{class:"kpi-note"},`${conFases} encargos con fases en historial.jsonl · corte el domingo 23:59 (la semana en curso, al ${F.ddmm(M.AHORA)} ${F.hhmm(M.AHORA)}).`)),h("span",{class:"source-pill"},"● historial real")),
        h("div",{class:"legend cfd-legend"},BANDAS.slice().reverse().map(([,l,c])=>h("span",{},h("b",{class:`sw ${c}`}),l))),
        h("div",{class:"cfd-wrap"},cfdSvg()),
        h("p",{class:"kpi-note"},"La semana del 28-09 sólo tiene el 03 y el 04-10 (el historial parte ahí). Las tarjetas sin fases (las de «abiertos» del borrador y las anteriores al historial) no entran al diagrama."),cfdTabla()),
      h("h2",{class:"sec"},term("Now/Next/Later")),nowNextLater(),
      h("h2",{class:"sec"},term("Forecast")," por proyecto"),forecast());
  }

  // ---------- Baldosa de Home (ejemplo) ----------
  function baldosaHome(){
    const now=M.tarjetas.filter(t=>["In progress","Review"].includes(t.columna)),ip=M.conteoColumnas["In progress"],rv=M.conteoColumnas.Review;
    const porP=M.proyectos.filter(p=>p.tarjetas.some(t=>now.includes(t))).slice(0,4);
    return h("section",{class:"home-tile-wrap"},h("h2",{class:"sec"},"Baldosa para 🏠 Home ",h("span",{class:"example-label"},"EJEMPLO")),
      h("article",{class:"card accent home-tile"},h("div",{class:"proj-head"},h("h3",{},term("Projects")," · Now"),h("span",{class:"simulated"},"propuesta")),
        h("p",{class:"tile-wip"},h("span",{class:ip>M.WIP["In progress"]?"over":""},`In progress ${ip}/${M.WIP["In progress"]}`)," · ",h("span",{class:rv>M.WIP.Review?"over":""},`Review ${rv}/${M.WIP.Review}`)),
        h("ul",{},porP.map(p=>h("li",{},h("strong",{},p.nombre),": ",p.tarjetas.filter(t=>now.includes(t)).map(t=>`${t.id} (${t.columna})`).join(", ")))),
        h("button",{class:"primary-button",type:"button",onclick:()=>{setParams({v:"board"});scrollTo({top:0})}},"Ver Projects")));
  }

  // ---------- página ----------
  function renderProjects(){
    const p=params(),solo=p.f==="abiertos";
    const barra=h("div",{class:"view-bar"},
      seg("Vista",[["board","Board"],["conflicts","Conflicts"],["flow","Flow over time"]],p.v,v=>setParams({v})),
      p.v==="board"?h("div",{class:"view-opts"},seg("Alternativa del Board",[["a","A · carriles"],["b","B · proyectos"]],p.b,b=>setParams({b})),seg("Filtro",[["abiertos","Sólo abiertos"],["todo","Todo"]],p.f,f=>setParams({f}))):null);
    const vista=p.v==="conflicts"?conflicts():p.v==="flow"?flowOverTime():[p.b==="b"?boardB(solo):boardA(solo),dudas()];
    main.replaceChildren(
      head("AI Ops · planning","Projects",`${M.tarjetas.length} tarjetas en ${M.proyectos.length} proyectos (los ${M.c3.indice} del índice, ninguno perdido). Columnas y proyectos según el borrador de la Fase 0; fechas y métricas desde historial.jsonl.`,"● datos reales · borrador"),
      kpis(),barra,...[vista].flat(),baldosaHome());
    bindTerms();
  }

  // ---------- panel de una tarjeta ----------
  function abrirTarjeta(id){
    const t=M.tarjeta[id],dlg=document.querySelector("#card-dialog");
    document.querySelector("#card-dialog-title").textContent=`Encargo ${t.id}`;
    document.querySelector("#card-dialog-sub").textContent=`${nombre(t.proyecto)} · ${t.columna}`;
    const dl=(pares)=>h("dl",{class:"facts"},pares.filter(Boolean).map(([k,v])=>[h("dt",{},k),h("dd",{},v)]));
    const fases=t.fases.length?h("div",{class:"table-wrap"},h("table",{class:"data-table fases"},h("thead",{},h("tr",{},["Fase","Cuenta","Inicio","Min","Veredicto"].map(x=>h("th",{},x)))),
      h("tbody",{},t.fases.map(f=>h("tr",{},h("td",{},f.fase),h("td",{},f.cuentaNombre),h("td",{},`${F.ddmm(f.ini)} ${F.hhmm(f.ini)}`),h("td",{},fmt(f.min)),h("td",{},f.veredicto?h("span",{class:`status mini ${f.veredicto==="DESPLEGABLE"?"":"danger"}`},f.veredicto):"—")))))):h("p",{class:"kpi-note"},"Sin fases en historial.jsonl.");
    document.querySelector("#card-dialog-body").replaceChildren(...[
      h("p",{class:"card-title"},t.titulo),h("div",{class:"pcard-top"},badges(t)),
      dl([["Fuente",t.fuente],["Asignación",t.asignacion==="exacto"?"por su id en el borrador":t.asignacion==="número"?"por su número (cubre variantes)":"sin proyecto → Sueltos"],
        t.inicio!=null&&["Primera fase",`${F.ddmm(t.inicio)} ${F.hhmm(t.inicio)}`],t.fin!=null&&["DESPLEGABLE",`${F.ddmm(t.fin)} ${F.hhmm(t.fin)}`],
        t.cycle!=null&&[term("Cycle time"),dur(t.cycle)],t.aging!=null&&[term("Aging"),`${t.aging} días sin fases`]]),
      t.dudas.length?h("div",{class:"finding"},h("strong",{},"Dudas: "),t.dudas.join(" ")):null,
      t.familiaRepartida?h("p",{class:"kpi-note"},`Familia ${t.familiaRepartida.numero}: `,t.familiaRepartida.partes.map(([i,p])=>`${i} → ${nombre(p)}`).join(" · ")):null,
      h("h3",{},"Fases reales"),fases,
      h("p",{class:"flow-link"},h("a",{href:`#/flow?e=${encodeURIComponent(t.id)}`,onclick:e=>{e.preventDefault();toast(`Enlace simulado: en la consola abre Flow con alcance Encargo ${t.id}.`)}},`Ver en Flow · encargo ${t.id} ›`)," ",h("span",{class:"simulated"},"simulado"))].filter(Boolean));
    if(!dlg.open)dlg.showModal();bindTerms();
  }

  // ---------- tooltip, glosario, comandos, tema ----------
  function bindTerms(){document.querySelectorAll("[data-term],[data-tip]").forEach(x=>{if(x.dataset.term&&!GLOSARIO[x.dataset.term]&&!x.dataset.tip)return;x.setAttribute("aria-describedby","term-tooltip");if(x.dataset.tipBound)return;x.dataset.tipBound="1";
    x.addEventListener("pointerenter",showTip);x.addEventListener("pointerleave",hideTip);x.addEventListener("focus",showTip);x.addEventListener("blur",hideTip);
    let hold;x.addEventListener("pointerdown",e=>{if(e.pointerType!=="mouse")hold=setTimeout(()=>showTip(e),450)});x.addEventListener("pointerup",()=>clearTimeout(hold));x.addEventListener("pointercancel",()=>clearTimeout(hold))})}
  function showTip(e){const el=e.currentTarget,rail=el.closest(".cockpit-rail");if(rail&&rail.matches(":hover,:focus-within"))return hideTip();
    const t=document.querySelector("#term-tooltip"),r=el.getBoundingClientRect();let nombreT,texto;
    if(el.dataset.tip){[nombreT,...texto]=el.dataset.tip.split("|");texto=texto.join("|")}else{nombreT=el.dataset.term;texto=GLOSARIO[nombreT]}
    t.replaceChildren(h("strong",{},nombreT),h("span",{},texto));t.hidden=false;const w=Math.min(300,innerWidth-24),left=Math.min(innerWidth-w-12,Math.max(12,r.left));
    t.style.left=`${left}px`;const alto=t.offsetHeight||86;t.style.top=`${r.bottom+8+alto>innerHeight?Math.max(8,r.top-alto-8):r.bottom+8}px`}
  function hideTip(){document.querySelector("#term-tooltip").hidden=true}
  function toast(text){const t=document.querySelector("#toast");clearTimeout(toastTimer);t.textContent=text;t.hidden=false;toastTimer=setTimeout(()=>t.hidden=true,2800)}
  function buildGlossary(){const icons=Object.fromEntries(Object.values(TOOLS).map(x=>[x.label,x.icon]));
    document.querySelector("#glossary-content").replaceChildren(
      h("div",{class:"glossary-list"},Object.entries(GLOSARIO).sort((a,b)=>a[0].localeCompare(b[0])).map(([k,v])=>h("div",{class:"glossary-item"},h("strong",{},icons[k]?`${icons[k]} ${k}`:k),h("span",{},v)))),
      h("h2",{},"Nombres de hoy → industria"),h("div",{class:"table-wrap"},h("table",{class:"data-table"},h("thead",{},h("tr",{},h("th",{},"Hoy"),h("th",{},"Industria"),h("th",{},"Definición"))),h("tbody",{},GLOSARIO_MAPEO.map(x=>h("tr",{},h("td",{},x[0]),h("td",{},h("strong",{},x[1])),h("td",{},x[2])))))))}
  function buildCommands(query=""){const q=query.toLowerCase(),out=[];for(const [tool,d] of Object.entries(TOOLS)){out.push({tool,tab:DEFAULT[tool],label:d.label,sub:"herramienta"});for(const [tab,label] of d.tabs)out.push({tool,tab,label,sub:d.label})}
    document.querySelector("#command-results").replaceChildren(...out.filter(x=>(x.label+" "+x.sub).toLowerCase().includes(q)).slice(0,12).map(x=>h("button",{class:"command-result",type:"button",onclick:()=>{document.querySelector("#command-dialog").close();go(x.tool,x.tab)}},h("strong",{},x.label),h("span",{class:"kpi-note"},x.sub))))}
  function leerTema(){try{return localStorage.getItem("consola-v2-theme")}catch{return null}}
  function guardarTema(v){try{localStorage.setItem("consola-v2-theme",v)}catch{}}

  buildNav();buildGlossary();
  document.documentElement.dataset.theme=new URLSearchParams(location.search).get("tema")||leerTema()||"light";
  document.querySelector("#theme-button").addEventListener("click",()=>{const dark=document.documentElement.dataset.theme==="dark";document.documentElement.dataset.theme=dark?"light":"dark";guardarTema(dark?"light":"dark")});
  tabSelect.addEventListener("change",()=>go(currentTool,tabSelect.value));
  const command=document.querySelector("#command-dialog"),search=document.querySelector("#command-search");
  const abrirComandos=()=>{buildCommands();command.showModal();setTimeout(()=>search.focus(),0)};
  document.querySelector("#command-button").addEventListener("click",abrirComandos);search.addEventListener("input",()=>buildCommands(search.value));
  document.addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"){e.preventDefault();abrirComandos()}});
  document.querySelector("#glossary-button").addEventListener("click",()=>document.querySelector("#glossary-dialog").showModal());
  window.addEventListener("hashchange",render);render();
  window.PROJECTS98={abrirTarjeta,setParams};
})();
