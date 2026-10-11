import { freshDemo } from '../data/mockFinancialData.js';
import { analyze } from './financialState.js';
const KEY = 'budgetplus-milestone-2';
export function loadDemo() {
 try {
  const raw = localStorage.getItem(KEY);
  if (!raw) return { data:freshDemo(), notice:'' };
  const data = JSON.parse(raw);
  const validDate = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value));
  if (data.version !== 2 || !['balanced','strict'].includes(data.guardrail) || !validDate(data.asOf)) throw new Error('Invalid snapshot');
  for (const key of ['accounts','cards','transactions','recurring','upcoming','debts','goals','imports']) {
   if (!Array.isArray(data[key])) throw new Error('Invalid data');
   if (key !== 'imports' && data[key].some(x => !x || typeof x !== 'object')) throw new Error('Invalid record');
  }
  const checks = [['accounts','balance'],['cards','balance'],['cards','limit'],['transactions','amount'],['recurring','amount'],['upcoming','amount'],['goals','protected'],['goals','saved'],['goals','target'],['debts','balance']];
  for (const [key,field] of checks) if (data[key].some(x => !Number.isFinite(x[field]) || x[field] < 0)) throw new Error('Invalid amount');
  if (!data.accounts.length || !data.cards.length || !Number.isFinite(data.buffer) || data.buffer < 0) throw new Error('Invalid resources');
  const strings = [['accounts',['id','institution','name']],['cards',['id','name','last4']],['transactions',['id','merchant','category']],['recurring',['id','merchant','category']],['upcoming',['id','merchant','category']],['goals',['id','name']]];
  for (const [key,fields] of strings) if (data[key].some(x => fields.some(field => typeof x[field] !== 'string' || !x[field].trim()))) throw new Error('Invalid labels');
  if (data.cards.some(c => !['active','locked'].includes(c.status) || c.limit <= 0 || c.balance > c.limit || !c.rewards || !Number.isFinite(c.rewards.default) || Object.values(c.rewards).some(rate => !Number.isFinite(rate) || rate < 0))) throw new Error('Invalid card');
  if (data.transactions.some(t => !validDate(t.date) || !['purchase','deposit'].includes(t.type)) || data.recurring.some(r => !validDate(r.nextDate)) || data.upcoming.some(r => !validDate(r.date))) throw new Error('Invalid history');
  for (const key of ['accounts','cards','transactions','recurring','upcoming','goals']) if (new Set(data[key].map(x => x.id)).size !== data[key].length) throw new Error('Duplicate records');
  const a = analyze(data);
  if (![a.score.value,a.budget.safeToSpend,a.budget.projectedEndMonth,a.budget.runway].every(Number.isFinite)) throw new Error('Invalid analysis');
  return { data, notice:'' };
 } catch { return { data:freshDemo(), notice:'Saved demo data was unavailable or invalid. The original demo has been restored.' }; }
}
export function saveDemo(data) { localStorage.setItem(KEY,JSON.stringify(data)); }

export function getPreference(key, defaultValue = null) {
  try {
    const val = localStorage.getItem(key);
    return val !== null ? val : defaultValue;
  } catch {
    return defaultValue;
  }
}

export function setPreference(key, value) {
  try {
    if (value === null || value === undefined) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, String(value));
    }
  } catch {}
}

