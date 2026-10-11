import { chromium } from 'file:///C:/Users/swago/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
const browser = await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page = await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
const errors=[];
page.on('pageerror', e=>errors.push(e.message));
await page.route('**/api/**',async route=>{const response=await route.fetch({url:route.request().url().replace(/https?:\/\/[^/]+/,'http://127.0.0.1:8181')});await route.fulfill({response});});
await page.goto('http://127.0.0.1:5173');
await page.getByRole('heading',{name:'ONE CARD. NO DECISIONS.'}).waitFor();
for(const width of [1440,768,390,320]){
 await page.setViewportSize({width,height:950});
 for(const [nav,heading] of [['Home','ONE CARD. NO DECISIONS.'],['Money','Money, in order.'],['Wallet','One card. No decisions.'],['AI Coach','Your pocket accountant.']]){
  await page.getByRole('navigation').getByRole('button',{name:nav,exact:true}).click();
  await page.getByRole('heading',{name:heading,exact:true}).waitFor();
  const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,items:[...document.querySelectorAll('main *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(e).position!=='absolute').slice(0,6).map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right}))}));
  console.log(nav,width,JSON.stringify(overflow));
  if(width===1440||width===390)await page.screenshot({path:'.verification/'+nav.replace(' ','-')+'-'+width+'.png',fullPage:true});
 }
}
console.log('JS errors',JSON.stringify(errors));
await browser.close();

