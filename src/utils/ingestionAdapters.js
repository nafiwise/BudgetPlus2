import { round } from './format.js';
// Replace these adapters with verified ingestion services in a future milestone.
export function importSample(data, source) {
 if (data.imports.includes(source)) return data;
 const next = { ...data, imports: [...data.imports,source] };
 if (source === 'bank') next.accounts = [...data.accounts, { id:'sample-bank', institution:'Demo Community Bank', name:'Imported checking', balance:150 }];
 if (source === 'history') {
  next.transactions = [{ id:'sample-history', date:data.asOf, merchant:'Sample campus grocery receipt', category:'Groceries', amount:8.5, type:'purchase', card:'Student checking' }, ...data.transactions];
  next.accounts = data.accounts.map((a,i) => i === 0 ? { ...a,balance:round(a.balance-8.5) } : a);
 }
 if (source === 'statement') next.recurring = [...data.recurring, { id:'sample-gym', merchant:'Sample fitness membership', amount:19, category:'Subscriptions', nextDate:'2026-10-26', flag:'Check whether your campus gym is already included in tuition' }];
 return next;
}
