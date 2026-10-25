"use strict";
// Modelo de la pestaña Projects (encargo 98). Sin DOM: lee window.DATOS98 y deja window.MODELO98.
// Todo sale de encargos-nube/98-datos/ (historial.jsonl, encargos-index.json, proyectos-borrador.json).
(function(raiz){
  const D=raiz.DATOS98,B=D.borrador;
  const COLS=B.columnas,WIP=B.tope_wip,DIA=864e5,SEMANA=7*DIA;
  const CHILE=-3*3600e3;           // todo el historial viene con -03:00 (horario de verano de Chile)
  const UMBRAL_AGING=7;            // días: una semana de cuota sin moverse
  const VENTANA=8;                 // semanas de throughput para el pronóstico
  const MIN_DONE=3;                // menos que esto en la ventana = datos insuficientes
  const CUENTAS={claude_diego:"Claude (Diego)",claude_cami:"Claude (Cami)",codex:"Codex"};
  const RANGO={"Review":0,"In progress":1,"Ready":2,"Idea":3,"Done":4};
  const RETRABAJO=/^(fix\d*|rev([2-9]|\d{2,}))$/;   // criterio de balance.py

  // Dudas de asignación que no salen de una regla: juicio sobre el título, para que Diego decida.
  // No mueven nada: la tarjeta se queda donde la puso el borrador y lleva la marca.
  const DUDAS_MANUALES={
    "75":["bot","Aviso programado del clima: va con 69, 74 y 76 (clima en el bot)."],
    "78a":["bot","changedetection.io y SearXNG: 78b (/buscar en los bots) está en bot."],
    "07":["bot","Ruta `noticias` en el bot."],
    "39b":["bot","Mandar un archivo del vault por Telegram."],
    "90":["bot","`/uso` como imagen es un comando del bot, y su revisión conjunta (9092n) está en bot."],
    "80b":["bot","La ruta web del bot pasa a otro modelo."],
    "83":["cuentas","Aviso de quema de cupo antes de la renovación: es de cuota."],
    "34":["consola","Resumen y barra de uso dentro de 🧵 Encargos (una página de Cockpit)."],
    "20":["consola","🧵 Encargos, la ventana de las colas en Cockpit."],
    "31":["consola","🧵 Encargos → Historial: es una página de Cockpit."]
  };

  const num=id=>(String(id).match(/^\d+/)||[""])[0];
  const proyectos=B.proyectos.map(p=>({...p,encargos:p.encargos||[],abiertos:p.abiertos||{},ideas:p.ideas||[]}));
  const porId=Object.fromEntries(proyectos.map(p=>[p.id,p]));
  const SUELTOS=proyectos.find(p=>p.id==="otros");

  // Fechas: ms absolutos; para semanas y etiquetas se pasa a la hora de Chile.
  const ms=s=>Date.parse(s);
  const chile=t=>new Date(t+CHILE);
  const lunes=t=>{const d=chile(t),dia=(d.getUTCDay()+6)%7;return Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate()-dia)-CHILE};
  const ddmm=t=>{const d=chile(t);return `${String(d.getUTCDate()).padStart(2,"0")}-${String(d.getUTCMonth()+1).padStart(2,"0")}`};
  const hhmm=t=>{const d=chile(t);return `${String(d.getUTCHours()).padStart(2,"0")}:${String(d.getUTCMinutes()).padStart(2,"0")}`};

  function tituloCorto(t){
    if(!t)return "";
    let s=t.replace(/^Encargo\s+\S+?\s*[—–:-]\s*/,"").trim();
    s=s.replace(/\s+[—–-]\s+\d{2}-\d{2}-\d{4}$/,"");
    if(s.endsWith(")")){let n=0;for(let i=s.length-1;i>=0;i--){if(s[i]===")")n++;else if(s[i]==="("&&--n===0){if(i>0)s=s.slice(0,i).trim();break}}}
    s=s.replace(/\s+\((Claude|Codex)\b.*$/,"");   // títulos cortados en el índice, con el paréntesis sin cerrar
    return s;
  }

  // Fases por encargo, en orden.
  const fasesDe={};
  for(const f of D.historial){const ini=ms(f.inicio),fin=ini+(Number(f.min)||0)*60e3;(fasesDe[f.encargo]=fasesDe[f.encargo]||[]).push({...f,ini,fin,cuentaNombre:CUENTAS[f.cuenta]||"otra"})}
  for(const k in fasesDe)fasesDe[k].sort((a,b)=>a.ini-b.ini);
  const AHORA=Math.max(...D.historial.map(f=>ms(f.inicio)+(Number(f.min)||0)*60e3));

  const indice=Object.fromEntries(D.indice.map(x=>[x.id,x]));
  const abiertoEn={};for(const p of proyectos)for(const id of Object.keys(p.abiertos))abiertoEn[id]=p;

  // Universo: índice + sólo-historial + sólo-abiertos del borrador.
  const ids=[...new Set([...D.indice.map(x=>x.id),...Object.keys(fasesDe),...Object.keys(abiertoEn)])];

  function asignar(id){
    const exactos=proyectos.filter(p=>p.encargos.includes(id)||id in p.abiertos);
    if(exactos.length)return {p:exactos[0],como:"exacto",otros:exactos.slice(1)};
    const n=num(id),porNum=proyectos.filter(p=>p.encargos.includes(n)||n in p.abiertos);
    if(n&&porNum.length)return {p:porNum[0],como:"número",otros:porNum.slice(1)};
    return {p:SUELTOS,como:"sin proyecto",otros:[]};
  }

  const tarjetas=ids.map(id=>{
    const ix=indice[id],fases=fasesDe[id]||[],a=asignar(id);
    const revs=fases.filter(f=>f.veredicto),ultimaRev=revs[revs.length-1]||null;
    const desp=[...fases].reverse().find(f=>f.veredicto==="DESPLEGABLE")||null;
    const t={id,titulo:ix?tituloCorto(ix.titulo):"",fuente:ix?(fases.length?"índice + historial":"índice"):(fases.length?"sólo historial":"sólo borrador"),
      proyecto:a.p.id,asignacion:a.como,fases,resultados:ix?ix.resultados.length:0,dudas:[],marcas:[]};
    t.inicio=fases.length?fases[0].ini:null;
    t.ultima=fases.length?Math.max(...fases.map(f=>f.fin)):null;
    if(a.otros.length)t.dudas.push(`También aparece en ${a.otros.map(p=>p.nombre).join(", ")}.`);
    if(a.como==="sin proyecto")t.dudas.push(ix?"No calza con ningún proyecto del borrador: queda en Sueltos.":"Sin ficha en el índice y sin proyecto: queda en Sueltos.");
    if(DUDAS_MANUALES[id]){const [sug,motivo]=DUDAS_MANUALES[id];t.sugerido=sug;t.dudas.push(`¿${porId[sug].nombre}? ${motivo}`)}
    // Columna: la de `abiertos` manda; si no, el historial.
    const ab=abiertoEn[id];
    if(ab){t.columna=ab.abiertos[id];if(ab.id!==t.proyecto)t.dudas.push(`Su columna viene de ${ab.nombre}.`)}
    else if(desp&&ultimaRev===desp){t.columna="Done";t.fin=desp.fin;t.cycle=(desp.fin-t.inicio)/DIA}
    else if(fases.length){t.columna="Done";t.sinDesplegable=true;t.marcas.push("sin DESPLEGABLE");
      t.dudas.push(`No está en «abiertos» y su última revisión fue ${ultimaRev?ultimaRev.veredicto:"ninguna"}: se da por cerrada (¿la cerró otro encargo?).`)}
    else if(t.resultados){t.columna="Done";t.sinFechas=true}
    else{t.columna="Idea";t.dudas.push("Sin fases, sin RESULTADO y sin columna en el borrador.")}
    t.abierto=t.columna!=="Done";
    if(t.abierto&&t.ultima!=null)t.aging=Math.floor((AHORA-t.ultima)/DIA);
    t.nube=/^\d+n$/.test(id)||!!(ix&&/en la nube/.test(ix.titulo));
    const bloq=(porId[t.proyecto].bloqueo||"");t.bloqueado=t.abierto&&new RegExp(`(^|[^\\w])${id}([^\\w]|$)`).test(bloq);
    if(!t.titulo)t.titulo=fases.length?"Sin ficha en el índice (sólo historial)":"Sin ficha en el índice (sólo borrador)";
    return t;
  });
  // Un número pelado que cubre variantes con ficha (88 → 88a, 88b, 88c) se nombra como familia.
  for(const t of tarjetas)if(!indice[t.id]&&t.id===num(t.id)){const v=tarjetas.filter(x=>x!==t&&num(x.id)===t.id).map(x=>x.id);if(v.length)t.titulo=`Familia ${t.id} (${v.join(", ")}): sin ficha propia en el índice`}
  const tarjeta=Object.fromEntries(tarjetas.map(t=>[t.id,t]));

  // Referencias del borrador que no son ningún encargo y familias repartidas entre proyectos.
  const referenciasHuerfanas=[];
  for(const p of proyectos)for(const id of p.encargos)if(!tarjeta[id]&&!tarjetas.some(t=>num(t.id)===id&&t.proyecto===p.id))referenciasHuerfanas.push([p.id,id]);
  const familias={};for(const t of tarjetas){const n=num(t.id);(familias[n]=familias[n]||[]).push(t)}
  const familiasRepartidas=Object.entries(familias).filter(([,ts])=>new Set(ts.map(t=>t.proyecto)).size>1)
    .map(([n,ts])=>({numero:n,partes:ts.map(t=>[t.id,t.proyecto])})).sort((a,b)=>Number(a.numero)-Number(b.numero));
  for(const f of familiasRepartidas)for(const [id] of f.partes)tarjeta[id].familiaRepartida=f;

  // Semanas (lunes a domingo, hora de Chile) desde la primera fase hasta AHORA.
  const primera=Math.min(...D.historial.map(f=>ms(f.inicio)));
  const semanas=[];for(let s=lunes(primera);s<=AHORA;s+=SEMANA)semanas.push(s);
  const semanaDe=t=>lunes(t);

  function metricas(ts){
    const hechas=ts.filter(t=>t.fin!=null),porSemana=semanas.map(s=>hechas.filter(t=>semanaDe(t.fin)===s).length);
    const ciclos=hechas.map(t=>t.cycle).sort((a,b)=>a-b);
    const pct=(arr,q)=>arr.length?arr[Math.min(arr.length-1,Math.ceil(q*arr.length)-1)]:null;
    const fases=ts.flatMap(t=>t.fases),total=fases.reduce((n,f)=>n+(Number(f.min)||0),0),re=fases.filter(f=>RETRABAJO.test(f.fase)).reduce((n,f)=>n+(Number(f.min)||0),0);
    const ventana=porSemana.slice(-VENTANA);
    return {hechas:hechas.length,porSemana,ventana,throughput:ventana.reduce((a,b)=>a+b,0)/ventana.length,
      ultimaSemana:porSemana[porSemana.length-1],cycleMediana:pct(ciclos,.5),cycleP85:pct(ciclos,.85),
      minutos:total,minRetrabajo:re,retrabajo:total?re/total:null};
  }

  // Monte Carlo: semilla fija para que la maqueta muestre siempre lo mismo.
  function azar(semilla){let a=semilla>>>0;return()=>{a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296}}
  function pronostico(p,ts,m){
    const falta=ts.filter(t=>["Ready","In progress","Review"].includes(t.columna)).length,hechasVentana=m.ventana.reduce((a,b)=>a+b,0);
    const base={falta,hechasVentana,semanasVentana:m.ventana.length,muestras:m.ventana};
    if(!falta)return {...base,estado:"nada"};
    if(hechasVentana<MIN_DONE)return {...base,estado:"insuficiente"};
    const r=azar(98),N=10000,res=[];
    for(let i=0;i<N;i++){let s=0,w=0;while(s<falta&&w<52){s+=m.ventana[Math.floor(r()*m.ventana.length)];w++}res.push(w)}
    res.sort((a,b)=>a-b);const q=x=>res[Math.ceil(x*N)-1];
    const proximoLunes=lunes(AHORA)+SEMANA,hasta=n=>proximoLunes+(n-1)*SEMANA;
    return {...base,estado:"ok",p50:q(.5),p80:q(.8),p95:q(.95),desde:proximoLunes,hasta80:hasta(q(.8)),hasta:hasta};
  }

  // Flujo acumulado al cierre de cada semana (domingo 23:59 o AHORA en la semana en curso).
  function cfd(ts){
    return semanas.map(s=>{const corte=Math.min(s+SEMANA-1,AHORA),c={"In progress":0,"Review":0,"Done":0,"Cerrado":0};
      for(const t of ts){if(!t.fases.length||t.inicio>corte)continue;
        if(t.fin!=null&&t.fin<=corte)c.Done++;
        else if(t.sinDesplegable&&t.ultima<=corte)c.Cerrado++;
        else{const ult=t.fases.filter(f=>f.ini<=corte).pop();if(/^rev/.test(ult.rol))c.Review++;else c["In progress"]++}}
      return {semana:s,corte,...c}});
  }

  const porProyecto=proyectos.map(p=>{
    const ts=tarjetas.filter(t=>t.proyecto===p.id).sort((a,b)=>(RANGO[a.columna]-RANGO[b.columna])||String(a.id).localeCompare(String(b.id),"es",{numeric:true}));
    const m=metricas(ts);return {...p,tarjetas:ts,metricas:m,pronostico:pronostico(p,ts,m),
      conteo:Object.fromEntries(COLS.map(c=>[c,ts.filter(t=>t.columna===c).length])),abiertas:ts.filter(t=>t.abierto).length};
  });
  porProyecto.sort((a,b)=>(a.id==="otros")-(b.id==="otros")||b.abiertas-a.abiertas||b.tarjetas.length-a.tarjetas.length);

  // Choques: archivos compartidos × encargos.
  const archivos=Object.entries(B.archivos_compartidos||{}).filter(([k])=>!k.startsWith("_")).map(([ruta,encs])=>{
    const filas=encs.map(id=>({id,t:tarjeta[id]||null})),abiertos=filas.filter(x=>x.t&&x.t.abierto);
    abiertos.sort((a,b)=>RANGO[a.t.columna]-RANGO[b.t.columna]||String(a.id).localeCompare(String(b.id),"es",{numeric:true}));
    return {ruta,corto:ruta.replace(/\/$/,"").split("/").pop()+(ruta.endsWith("/")?"/":""),encargos:encs,abiertos:abiertos.map(x=>x.id),choque:abiertos.length>=2};
  });
  const encargosConArchivo=[...new Set(archivos.flatMap(a=>a.encargos))];
  const ordenGlobal=[...new Set(archivos.filter(a=>a.choque).flatMap(a=>a.abiertos))].sort((a,b)=>RANGO[tarjeta[a].columna]-RANGO[tarjeta[b].columna]||String(a).localeCompare(String(b),"es",{numeric:true}));

  const indiceIds=D.indice.map(x=>x.id),cubiertos=indiceIds.filter(id=>tarjeta[id]&&porId[tarjeta[id].proyecto]);

  raiz.MODELO98={COLS,WIP,UMBRAL_AGING,VENTANA,MIN_DONE,CUENTAS,AHORA,semanas,proyectos:porProyecto,porId,tarjetas,tarjeta,
    global:metricas(tarjetas),cfd:cfd(tarjetas),archivos,encargosConArchivo,ordenGlobal,referenciasHuerfanas,familiasRepartidas,
    conteoColumnas:Object.fromEntries(COLS.map(c=>[c,tarjetas.filter(t=>t.columna===c).length])),
    c3:{indice:indiceIds.length,cubiertos:cubiertos.length,enSueltos:indiceIds.filter(id=>tarjeta[id].proyecto==="otros").length,perdidos:indiceIds.filter(id=>!cubiertos.includes(id))},
    fmt:{ddmm,hhmm,lunes,tituloCorto}};
})(typeof window!=="undefined"?window:globalThis);
