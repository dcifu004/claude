// Capturas y chequeos de C1/C4 con Chromium (Playwright): node maquetas/98-projects/capturar.js
// Abre index.html por file://, falla si hay errores de consola, pedidos que no sean file:// o desborde horizontal.
"use strict";
const {chromium}=require("playwright");
const path=require("path");
const AQUI=__dirname,URL_BASE="file://"+path.join(AQUI,"index.html");
const ANCHOS=[1280,800,375],TEMAS=["light","dark"];
const VISTAS=[["board-a","#/projects?v=board&b=a&f=abiertos"],["board-a-todo","#/projects?v=board&b=a&f=todo"],["board-b","#/projects?v=board&b=b&f=abiertos"],["conflicts","#/projects?v=conflicts&b=a&f=abiertos"],["flow","#/projects?v=flow&b=a&f=abiertos"]];
(async()=>{
  const browser=await chromium.launch(),problemas=[];let n=0;
  for(const tema of TEMAS)for(const ancho of ANCHOS){
    const page=await browser.newPage({viewport:{width:ancho,height:900}});await page.mouse.move(ancho-2,898);
    page.on("console",m=>{if(m.type()==="error"||m.type()==="warning")problemas.push(`${tema} ${ancho} consola ${m.type()}: ${m.text()}`)});
    page.on("pageerror",e=>problemas.push(`${tema} ${ancho} pageerror: ${e.message}`));
    page.on("request",r=>{if(!r.url().startsWith("file://"))problemas.push(`${tema} ${ancho} red: ${r.url()}`)});
    for(const [nombre,hash] of VISTAS){
      await page.goto(`${URL_BASE}?tema=${tema}${hash}`);await page.waitForSelector(".kpi-strip");await page.mouse.move(ancho-3,897);await page.evaluate(()=>document.activeElement&&document.activeElement.blur());await page.waitForTimeout(300);
      const desborde=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
      if(desborde>0)problemas.push(`${tema} ${ancho} ${nombre}: desborde horizontal de ${desborde}px`);
      await page.screenshot({path:path.join(AQUI,"capturas",`${nombre}-${ancho}-${tema}.png`),fullPage:nombre!=="board-a-todo"});n++;
    }
    // Panel de una tarjeta y tooltip del pronóstico.
    await page.goto(`${URL_BASE}?tema=${tema}#/projects?v=board&b=a&f=abiertos`);await page.waitForSelector(".pcard");
    await page.click('.pcard[data-id="9092n"]');await page.waitForSelector("#card-dialog[open]");
    await page.screenshot({path:path.join(AQUI,"capturas",`panel-${ancho}-${tema}.png`)});n++;
    await page.keyboard.press("Escape");
    await page.goto(`${URL_BASE}?tema=${tema}#/projects?v=flow&b=a&f=abiertos`);await page.waitForSelector(".fc .info");
    await page.locator(".fc .info").first().focus();await page.waitForSelector("#term-tooltip:not([hidden])");
    const tip=await page.textContent("#term-tooltip");if(!/Monte Carlo/.test(tip))problemas.push(`${tema} ${ancho}: el tooltip del pronóstico no explica el método`);
    await page.locator(".fc .info").first().scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(AQUI,"capturas",`forecast-tooltip-${ancho}-${tema}.png`)});n++;
    await page.close();
  }
  await browser.close();
  console.log(`${n} capturas en capturas/`);
  if(problemas.length){console.log("PROBLEMAS:\n"+problemas.join("\n"));process.exit(1)}
  console.log("sin errores de consola, sin pedidos de red y sin desborde horizontal");
})();
