import { money } from '../utils/format.js';
export default function RecurringExpenses({ data }) {
 return <section className="panel" id="recurring"><div className="section-heading"><div><h2>Recurring expenses</h2><p>Protect the essentials. Reconsider the rest.</p></div></div>{data.recurring.map(r => <div className="bill-row" key={r.id}><div><strong>{r.merchant}</strong><p>{r.nextDate} · {money(r.amount*12)} / year</p>{r.flag && <p className="warning-text">{r.flag}</p>}</div><strong>{money(r.amount)}<small> / month</small></strong></div>)}</section>;
}
