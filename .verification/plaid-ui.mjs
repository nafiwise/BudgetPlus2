// Browser tests against intercepted built assets and synthetic APIs, with no app server or live Plaid calls.
import { chromium } from 'file:///C:/Users/swago/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const fixture = JSON.parse(await fs.readFile('.verification/plaid-fixtures.json', 'utf8'));
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
try {
 const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
 const errors = [], calls = [];
 let linked = false, failure = false, state = fixture.demo;
 const empty = { ...fixture.status, items: [], institutions: 0, accounts: 0, transactions: 0, monthsAnalyzed: 0, historyReady: false };
 page.on('pageerror', e => errors.push(e.message));
 await page.route('**/*', async route => {
   const url = new URL(route.request().url());
   if (url.hostname === 'cdn.plaid.com') return route.fulfill({ contentType: 'application/javascript', body: `window.Plaid={create:config=>({open:()=>setTimeout(()=>config.onSuccess('public-sandbox-fixture',{}),10),exit:()=>{},destroy:()=>{}})};` });
   if (url.hostname !== 'budgetplus.test') return route.abort();
   if (url.pathname.startsWith('/api/')) {
     calls.push(url.pathname);
     const json = body => route.fulfill({ json: body });
     if (url.pathname === '/api/state') return json(state);
     if (url.pathname === '/api/plaid/status') return json(linked ? fixture.status : empty);
     if (url.pathname === '/api/plaid/accounts') return json({ accounts: linked ? fixture.accounts : [] });
     if (url.pathname === '/api/plaid/link-token') return failure ? route.fulfill({ status: 503, json: { detail: 'Plaid is unavailable for this test.' } }) : json({ link_token: 'link-sandbox-fixture', updateMode: false });
     if (url.pathname === '/api/plaid/exchange-token') { linked = true; return json({ itemId: 'fixture-item' }); }
     if (url.pathname === '/api/plaid/sync') { state = fixture.personal; return json(state); }
     if (url.pathname === '/api/coach') return json({ answer: 'Sample Coffee spending is $12.50.', provider: 'Google Gemini', model: 'fixture-model', contextMode: 'MY DATA', contextSource: 'Plaid sandbox', contextRevision: state.revision, contextTransactions: 2, generatedAt: new Date().toISOString() });
     return route.fulfill({ status: 404, json: {} });
   }
   const path = url.pathname === '/' ? 'dist/index.html' : 'dist' + url.pathname;
   try { return route.fulfill({ body: await fs.readFile(path), contentType: path.endsWith('.js') ? 'application/javascript' : path.endsWith('.css') ? 'text/css' : 'text/html' }); }
   catch { return route.fulfill({ status: 404, body: '' }); }
 });
 await page.goto('http://budgetplus.test/');
 await page.getByRole('navigation').getByRole('button', { name: 'Money', exact: true }).click();
 await page.getByRole('button', { name: 'CONNECT MY ACCOUNTS', exact: true }).waitFor();
 failure = true;
 await page.getByRole('button', { name: 'CONNECT MY ACCOUNTS', exact: true }).click();
 await page.getByRole('alert').filter({ hasText: 'Plaid is unavailable' }).waitFor();
 assert.equal(state.data.mode, 'demo');
 failure = false;
 await page.getByRole('button', { name: 'CONNECT MY ACCOUNTS', exact: true }).click();
 await page.getByText('YOUR PROFILE IS READY', { exact: true }).waitFor();
 await page.getByRole('button', { name: 'CONNECT ANOTHER ACCOUNT', exact: true }).waitFor();
 assert(calls.includes('/api/plaid/exchange-token') && calls.includes('/api/plaid/sync'));
 await page.getByText('Connected institutions and accounts', { exact: true }).click();
 await page.getByText(/Everyday Checking.*1234/).waitFor();
 for (const width of [1440, 390]) {
   await page.setViewportSize({ width, height: 1000 });
   const dimensions = await page.evaluate(() => ({ inner: innerWidth, scroll: document.documentElement.scrollWidth }));
   assert(dimensions.scroll <= dimensions.inner + 1, `Overflow at ${width}: ${JSON.stringify(dimensions)}`);
   await page.screenshot({ path: `.verification/Plaid-Money-${width}.png`, fullPage: true });
 }
 await page.locator('summary').filter({ hasText: /^Recent activity$/ }).click();
 await page.getByText('Sample Coffee', { exact: true }).waitFor();
 await page.getByRole('navigation').getByRole('button', { name: 'AI Coach', exact: true }).click();
 await page.getByLabel('Your question').fill('Summarize my spending');
 await page.getByRole('button', { name: 'Ask BudgetPlus', exact: true }).click();
 await page.getByText('Response details', { exact: true }).click();
 await page.getByText(/MY DATA.*Plaid sandbox.*Google Gemini/).waitFor();
 assert.deepEqual(errors, []);
 console.log('PASS: failed Link fallback, Link exchange/sync, MY DATA, summary counts, linked account details, desktop/mobile layout, activity and Gemini source details. No app server or live bank calls used.');
} finally { await browser.close(); }
