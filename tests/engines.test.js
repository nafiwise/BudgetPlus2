import test from 'node:test';
import assert from 'node:assert/strict';
import { freshDemo } from '../src/data/mockFinancialData.js';
import { analyze, applyPurchase } from '../src/utils/financialState.js';
import { routeTransaction } from '../src/utils/routingEngine.js';
import { importSample } from '../src/utils/ingestionAdapters.js';
import { loadDemo, saveDemo } from '../src/utils/persistence.js';
const tx = (overrides={}) => ({ id:'test',merchant:'Chipotle',amount:18.42,category:'Dining', ...overrides });
test('finite aid is not salary; reserves reconcile exactly', () => {
 const a=analyze(freshDemo());
 assert.equal(a.profile.cashPreservation,true);assert.equal(a.profile.incomeType,'variable');
 assert.equal(a.budget.safeToSpend,460.03);assert.equal(a.score.value,756);
 assert.equal(a.budget.categories.length,7);
});
test('dining warns without mutating any financial state', () => {
 const d=freshDemo(),snapshot=structuredClone(d);const r=routeTransaction(tx(),d);
 assert.equal(r.status,'warning');assert.equal(r.selectedCard,'Amex Gold');assert.equal(r.estimatedReward,.74);assert.deepEqual(d,snapshot);
});
test('purchase posts once to ledger and reserves card debt without deducting cash twice', () => {
 const d=freshDemo(), r=routeTransaction(tx(),d), after=applyPurchase(d,tx(),r.cardId), a=analyze(after);
 assert.equal(after.transactions.length,d.transactions.length+1);assert.equal(after.cards[0].balance,358.42);assert.deepEqual(after.accounts,d.accounts);
 assert.equal(a.budget.safeToSpend,441.61);assert.equal(a.score.value,752);assert.equal(r.scoreImpact,-4);
 assert.equal(a.budget.categories.find(c=>c.name==='Dining').spent,144.42);
 assert.ok(a.budget.runway<analyze(d).budget.runway);
});
test('an on-pace transportation purchase is approved', () => {
 assert.equal(routeTransaction(tx({merchant:'Metro',amount:5,category:'Transportation'}),freshDemo()).status,'approved');
});
test('strict guardrails block dining warnings', () => {
 const d=freshDemo();d.guardrail='strict';assert.equal(routeTransaction(tx(),d).status,'blocked');
});
test('protected money cannot be overridden', () => {
 assert.equal(routeTransaction(tx({amount:500}),freshDemo()).status,'blocked');
});
test('all locked cards block and never mutate', () => {
 const d=freshDemo();d.cards.forEach(c=>c.status='locked');const copy=structuredClone(d);
 assert.equal(routeTransaction(tx(),d).status,'blocked');assert.deepEqual(d,copy);
});
test('debt concentration outweighs higher rewards', () => {
 const d=freshDemo();d.cards[0].balance=980;d.accounts[0].balance+=640;
 const r=routeTransaction(tx(),d);assert.equal(r.selectedCard,'Chase Freedom');
});
test('eligible credit is checked before reward optimization', () => {
 const d=freshDemo();d.cards[0].balance=1990;d.accounts[0].balance+=1650;
 assert.equal(routeTransaction(tx(),d).selectedCard,'Chase Freedom');
});
test('invalid amounts, merchant and category cannot be routed', () => {
 for(const amount of [0,-10,NaN,Infinity,1.001]) assert.equal(routeTransaction(tx({amount}),freshDemo()).status,'blocked');
 assert.equal(routeTransaction(tx({merchant:'  '}),freshDemo()).status,'blocked');
 assert.equal(routeTransaction(tx({category:'Unknown'}),freshDemo()).status,'blocked');
});
test('category targets do not increase after a simulated purchase', () => {
 const d=freshDemo(), after=applyPurchase(d,tx({category:'School'}),'chase');
 assert.equal(analyze(after).budget.categories.find(c=>c.name==='School').target,analyze(d).budget.categories.find(c=>c.name==='School').target);
});
test('imports reconcile and cannot duplicate', () => {
 const d=freshDemo();for(const source of ['bank','history','statement']) { const next=importSample(d,source);assert.equal(importSample(next,source),next);assert.notDeepEqual(next,d); }
 const h=importSample(d,'history');assert.equal(h.accounts[0].balance,2841.5);assert.equal(analyze(h).budget.categories.find(c=>c.name==='Groceries').spent,94.5);
 assert.equal(analyze(importSample(d,'statement')).budget.safeToSpend,441.03);
});
test('score is bounded; an absent salary alone is not a penalty', () => {
 const d=freshDemo();d.transactions=d.transactions.filter(t=>t.source!=='irregular');assert.equal(analyze(d).score.value,756);
 d.cards.forEach(c=>c.balance=c.limit);d.accounts.forEach(a=>a.balance=0);const a=analyze(d);assert.ok(a.score.value>=300 && a.score.value<=850);assert.equal(a.budget.safeToSpend,0);
});
test('saved demo round trips; malformed or unavailable storage recovers', () => {
 let value=null;globalThis.localStorage={getItem:()=>value,setItem:(k,v)=>{value=v;}};
 const d=applyPurchase(freshDemo(),tx(),'amex');saveDemo(d);assert.deepEqual(loadDemo().data,d);
 value='{broken';assert.equal(loadDemo().data.cards[0].balance,340);assert.ok(loadDemo().notice);
 value=JSON.stringify({version:2});assert.ok(loadDemo().notice);
 globalThis.localStorage={getItem:()=>{throw new Error('Unavailable');}};assert.ok(loadDemo().notice);
 delete globalThis.localStorage;
});
test('reset fixture is isolated from mutations', () => {
 const d=freshDemo();d.cards[0].balance=1000;d.imports.push('bank');assert.equal(freshDemo().cards[0].balance,340);assert.deepEqual(freshDemo().imports,[]);
});
