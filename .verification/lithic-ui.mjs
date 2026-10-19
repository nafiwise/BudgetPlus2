import { chromium } from 'file:///C:/Users/swago/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';

const f = JSON.parse(await fs.readFile('.verification/lithic-fixtures.json', 'utf8'));
const browser = await chromium.launch({ executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', headless:true });
try {
 const context = await browser.newContext({ viewport:{width:1440,height:1000}, reducedMotion:'reduce' });
 let state=f.before, status=f.initialStatus, count=0, legacyCalls=0;
 const errors=[];
 await context.route('**/*', async route => {
   const url=new URL(route.request().url());
   if(url.hostname!=='budgetplus.test') return route.abort();
   const json=body=>route.fulfill({json:body});
   if(url.pathname.startsWith('/api/')) {
     switch(url.pathname) {
       case '/api/state': return json(state);
       case '/api/lithic/status': return json(status);
       case '/api/plaid/status': return json({configured:false,environment:'production',items:[]});
       case '/api/lithic/create-card': state=f.afterCreate;status={...status,card:f.created.card};return json(f.created);
       case '/api/lithic/responder/enroll': status=f.readyStatus;return json(status);
       case '/api/lithic/responder/status': return json(status);
       case '/api/lithic/card/pause': status={...status,card:{...status.card,state:'PAUSED'}};return json({card:status.card});
       case '/api/lithic/card/unpause': status={...status,card:{...status.card,state:'OPEN'}};return json({card:status.card});
       case '/api/lithic/simulate': {
         const body=route.request().postDataJSON();assert.equal(body.amount,10);assert.equal(body.category,'Dining');
         count++;state=count===1?f.afterApprove:f.afterDecline;return json(count===1?f.approved:f.declined);
       }
       case '/api/categories': assert.equal(route.request().postDataJSON().limit,15);state=f.limited;return json(state);
       case '/api/authorize': legacyCalls++;return route.fulfill({status:500,json:{detail:'Must not bypass Lithic'}});
       default: return route.fulfill({status:404,json:{}});
     }
   }
   const path=url.pathname.startsWith('/assets/')?'dist'+url.pathname:'dist/index.html';
   return route.fulfill({body:await fs.readFile(path),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://budgetplus.test/');
 await page.getByRole('navigation').getByRole('button',{name:'Wallet',exact:true}).click();
 await page.getByText('Lithic Sandbox card & ASA',{exact:true}).click();
 await page.getByRole('button',{name:'Create Mastercard Sandbox card',exact:true}).click();
 await page.getByRole('button',{name:'Pause Sandbox card',exact:true}).waitFor();
 await page.getByRole('button',{name:'Enroll ASA',exact:true}).click();
 await page.getByText(/ASA: Enrolled at the configured URL/).waitFor();
 await page.getByRole('button',{name:'Pause Sandbox card',exact:true}).click();
 await page.getByRole('button',{name:'Unpause Sandbox card',exact:true}).click();
 await page.getByLabel('BudgetPlus Card ending in 1111',{exact:true}).waitFor();
 for(const width of [1440,390]) {
   await page.setViewportSize({width,height:1000});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:`.verification/Lithic-Wallet-${width}.png`,fullPage:true});
 }
 const merchant=await context.newPage();merchant.on('pageerror',e=>errors.push(e.message));
 await merchant.goto('http://budgetplus.test/merchant');
 await merchant.getByText('Configure demo purchase',{exact:true}).click();
 await merchant.getByLabel('Amount ($)',{exact:true}).fill('10');
 await merchant.getByRole('button',{name:'Tap / Simulate BudgetPlus Card',exact:true}).click();
 await merchant.getByRole('heading',{name:'APPROVED',exact:true}).waitFor();
 await merchant.getByText('View decision',{exact:true}).click();
 await merchant.getByText('Provider: Lithic Sandbox / Verified ASA: Yes',{exact:true}).waitFor();
 await merchant.getByText('Lithic result: APPROVED / PENDING',{exact:true}).waitFor();
 await merchant.screenshot({path:'.verification/Lithic-Merchant-approved.png',fullPage:true});
 await page.getByRole('navigation').getByRole('button',{name:'Money',exact:true}).click();
 await page.getByText('Personalize categories',{exact:true}).click();
 await page.getByRole('combobox',{name:/Refine existing category or create one/}).selectOption('Dining');
 await page.getByLabel('Monthly spending limit ($)',{exact:true}).fill('15');
 await page.getByRole('button',{name:'Save category',exact:true}).click();
 await page.getByText('Category and importance updated.',{exact:false}).waitFor();
 await merchant.getByRole('button',{name:'Start another purchase',exact:true}).click();
 await merchant.getByRole('button',{name:'Tap / Simulate BudgetPlus Card',exact:true}).click();
 await merchant.getByRole('heading',{name:'DECLINED',exact:true}).waitFor();
 await merchant.getByText('View decision',{exact:true}).click();
 await merchant.getByText(/ASA response: VELOCITY_EXCEEDED/).waitFor();
 await merchant.setViewportSize({width:390,height:1000});
 assert(await merchant.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await merchant.screenshot({path:'.verification/Lithic-Merchant-declined-390.png',fullPage:true});
 assert.equal(count,2);assert.equal(legacyCalls,0);assert.deepEqual(errors,[]);
 console.log('PASS: Wallet creation/enrollment/pause controls; signed-ASA fixture approval; category limit edit; decline; no local authorization bypass; desktop/mobile layouts. Synthetic assets only, no app server or live Lithic calls.');
} finally { await browser.close(); }
