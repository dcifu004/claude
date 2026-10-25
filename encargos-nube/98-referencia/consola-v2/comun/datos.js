"use strict";
window.DATOS = {
  generado:"2026-10-24T14:49:42-03:00",
  fuentes:{historial:"360 fases",panel:"panel.json · salida real",memoria:"lectura local · sólo nombres y conteos"},
  total:{tasks:87,steps:360,min:3428,rework:45,usdTask:6.27,tokensTask:330000,estimationError:40},
  trace84:[
    {task:"84a",step:"autor",role:"autor",account:"Claude (Cami)",model:"claude-opus-5-5",nature:"pagina",start:"2026-10-24T11:57:29-03:00",min:18.7,predicted:12.3,usd:5.8146,tokens:null,verdict:null},
    {task:"84a",step:"rev1",role:"rev",account:"Codex",model:"gpt-5.6-terra",nature:"pagina",start:"2026-10-24T12:16:12-03:00",min:5.4,predicted:5.4,usd:null,tokens:176401,verdict:"NO DESPLEGABLE"},
    {task:"84a",step:"fix1",role:"fix",account:"Claude (Cami)",model:"claude-sonnet-5-5",nature:"pagina",start:"2026-10-24T12:21:39-03:00",min:2.6,predicted:3.4,usd:.2477,tokens:null,verdict:null},
    {task:"84a",step:"rev2",role:"rev",account:"Codex",model:"gpt-5.6-terra",nature:"pagina",start:"2026-10-24T12:24:19-03:00",min:3.9,predicted:5.2,usd:null,tokens:102696,verdict:"DESPLEGABLE"},
    {task:"84b",step:"autor",role:"autor",account:"Claude (Cami)",model:"claude-opus-5-5",nature:"pagina",start:"2026-10-24T12:28:14-03:00",min:15.5,predicted:15,usd:5.785,tokens:null,verdict:null},
    {task:"84b",step:"rev1",role:"rev",account:"Codex",model:"gpt-5.6-terra",nature:"pagina",start:"2026-10-24T12:43:49-03:00",min:4.1,predicted:4.9,usd:null,tokens:149926,verdict:"DESPLEGABLE"}
  ],
  activeRun:{
    queue:"cola84",task:"84a",state:"corriendo",current:"rev1",simulated:true,
    done:[{etapa:"84a",fase:"autor",rol:"autor",cuenta:"claude_cami",modelo:"claude-opus-5-5",min:18.7,prob:1}],
    currentStep:{etapa:"84a",fase:"rev1",rol:"rev",cuenta:"codex",modelo:"gpt-5.6-terra",min:5.4,pct_5h:6.5,pct_sem:1,prob:1,inicio_esperado:"2026-10-24T15:08:25-03:00",debil:false},
    fases_restantes:[
      {etapa:"84a",fase:"fix1",rol:"fix",cuenta:"claude_cami",modelo:"claude-sonnet-5-5",min:3.4,pct_5h:2,pct_sem:0,prob:.61,inicio_esperado:"2026-10-24T15:13:49-03:00",debil:false},
      {etapa:"84a",fase:"rev2",rol:"rev",cuenta:"codex",modelo:"gpt-5.6-terra",min:5.2,pct_5h:6.5,pct_sem:1,prob:.61,inicio_esperado:"2026-10-24T15:15:54-03:00",debil:false},
      {etapa:"84a",fase:"fix2",rol:"fix",cuenta:"claude_cami",modelo:"claude-sonnet-5-5",min:3.4,pct_5h:2,pct_sem:0,prob:.3721,inicio_esperado:"2026-10-24T15:19:04-03:00",debil:false},
      {etapa:"84a",fase:"rev3",rol:"rev",cuenta:"codex",modelo:"gpt-5.6-terra",min:5.2,pct_5h:6.5,pct_sem:1,prob:.3721,inicio_esperado:"2026-10-24T15:20:20-03:00",debil:false}
    ]
  },
  scorecard:[
    {model:"gpt-5.6-terra",type:"bot",tasks:35,first:32,rework:78,cost:"318 k tok",error:33},
    {model:"claude-opus-5-5",type:"bot",tasks:32,first:8,rework:66,cost:"US$ 7,55",error:51},
    {model:"gpt-5.6-terra",type:"seguridad",tasks:21,first:38,rework:70,cost:"414 k tok",error:58},
    {model:"claude-opus-5-5",type:"seguridad",tasks:19,first:0,rework:61,cost:"US$ 10,50",error:67},
    {model:"gpt-5.6-terra",type:"pagina",tasks:10,first:33,rework:74,cost:"307 k tok",error:44},
    {model:"claude-sonnet-5-5",type:"pagina",tasks:7,first:null,rework:33,cost:"US$ 1,21",error:42},
    {model:"gpt-reserve",type:"pagina",tasks:7,first:50,rework:100,cost:"216 k tok",error:37},
    {model:"claude-opus-5-5",type:"pagina",tasks:6,first:0,rework:20,cost:"US$ 5,49",error:29}
  ],
  providers:[
    {id:"claude_diego",name:"Claude (Diego)",capacity:69,window:276.6,renews:"31 oct · 04:00",fits:["cola36b","cola44"]},
    {id:"claude_cami",name:"Claude (Cami)",capacity:10,window:72.7,renews:"25 oct · 21:59",fits:[]},
    {id:"codex",name:"Codex",capacity:71,window:520.2,renews:"30 oct · 21:32",fits:["cola36b","cola44"]}
  ],
  memory:{
    total:107,totalMd:114,conflicts:5,broken:2,missing:2,surplus:0,noDescription:0,
    brokenItems:[{file:"reorden-vault-personal.md",target:"03 - Cronograma",count:2}],
    missingItems:["avance-colas-por-telegram.md","prueba-changedetection-searxng.md"],
    oldest:[
      {file:"adjuntos-gmail-via-raw.md",modified:null},{file:"archify-controles-manuales.md",modified:null},
      {file:"conector-google-slides.md",modified:null},{file:"copias-muertas-tras-mover-carpetas.md",modified:null},
      {file:"pi5-hardware-almacenamiento.md",modified:null},{file:"transcribir-audio-con-groq.md",modified:"2026-08-15"}
    ]
  },
  approvals:[
    {kind:"Release gate",title:"Desplegar consola de encargos",detail:"Validación final del paquete 84b.",account:"Claude (Diego)",minutes:18,priority:"alta"},
    {kind:"HITL · A/B/C",title:"Elegir ventana para reanudar cola36b",detail:"A: hoy · B: mañana · C: mantener pausada.",account:"Claude (Diego)",minutes:47,priority:"media"},
    {kind:"Model authorization",title:"Autorizar modelo fuera de política",detail:"La ruta propuesta requiere autorización explícita.",account:"Codex",minutes:95,priority:"media"},
    {kind:"Change request",title:"Aplicar propuesta de asistente",detail:"Cambio de herramientas permitido sólo después de revisión.",account:"Claude (Cami)",minutes:180,priority:"baja"}
  ]
};
