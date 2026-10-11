import { useState } from 'react';
import { ArrowUpRight, Send, ShieldCheck, Sparkles } from 'lucide-react';
import { priority } from './Home.jsx';
import { api } from '../utils/api.js';
import { ScoreRing } from './Visuals.jsx';

export default function AICoach({ revision, data, analysis }) {
  const [question,setQuestion] = useState('');
  const [asked,setAsked] = useState('');
  const [busy,setBusy] = useState(false);
  const [result,setResult] = useState(null);
  const [error,setError] = useState('');
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setResult(null); setAsked(question);
    try { setResult(await api('/coach',{method:'POST',body:JSON.stringify({question})})); }
    catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div className="coach-page"><div className="page-heading"><div><div className="eyebrow"><Sparkles size={14}/>BUDGETPLUS × GEMINI</div><h1>Your pocket<br/><span>accountant.</span></h1><p>A clear next step. A little more peace of mind.</p></div><span className="assistant-emblem" aria-hidden="true"><Sparkles size={48}/></span></div>
    <div className="coach-layout"><section className="panel coach-panel"><div className="assistant-identity"><span className="assistant-avatar"><Sparkles size={20}/></span><div><strong>Ask BudgetPlus</strong><small>Your money. In plain language.</small></div></div>
      <div className="suggested-questions">{['Can I afford this?','Where should I cut spending?','Why did my score change?'].map(q=><button className="suggested-prompt" key={q} disabled={busy} onClick={()=>setQuestion(q)}>{q}<ArrowUpRight size={14}/></button>)}</div>
      {asked&&<div className="user-message">{asked}</div>}{busy&&<div className="assistant-message thinking" role="status"><span/><span/><span/><small>Looking at the whole picture…</small></div>}
      {error&&<p role="alert" className="notice">{error}</p>}
      {result&&<div className="assistant-message" aria-live="polite"><span className="eyebrow"><Sparkles size={14}/>BUDGETPLUS</span><div className="coach-answer">{result.answer}</div>{result.contextRevision!==revision&&<p className="warning-text">Your finances changed since this answer. Ask again for current context.</p>}<details><summary>Response details</summary><p>{result.contextMode} &middot; {result.contextSource} &middot; {result.provider} · {result.model} · {new Date(result.generatedAt).toLocaleString()} · {result.contextTransactions} transactions · Response {result.responseId||'ID not supplied'}</p></details></div>}
      <form onSubmit={submit}><label htmlFor="coach-question" className="sr-only">Your question</label><div className="composer"><textarea id="coach-question" required maxLength={2000} rows={3} placeholder="Ask anything about your money…" disabled={busy} value={question} onChange={e=>setQuestion(e.target.value)}/><div className="composer-bottom"><span><Sparkles size={13}/>Powered by Gemini</span><button className="primary-button" disabled={busy||!question.trim()}>{busy?'Asking…':'Ask BudgetPlus'}<Send size={15}/></button></div></div></form>
      <details className="privacy-details"><summary>Privacy &amp; AI details</summary><p>Questions automatically include your current financial profile, balances, categories, score, goals, card rules, obligations, recent routing decisions, and up to 1,000 normalized transactions. No raw files, bank credentials, or full card numbers. Avoid sensitive credentials in questions or transaction labels.</p><p>Gemini suggestions do not change settings or approve purchases. Apply changes in Money. No simulated fallback answers.</p></details>
    </section><aside className="coach-context"><section className="panel"><span className="eyebrow"><ShieldCheck size={14}/>YOUR FINANCIAL HEALTH</span><ScoreRing value={analysis.score.value} compact/><p className="context-rating">{analysis.score.rating}{analysis.score.provisional?' · Provisional':''}</p></section><section className="panel coach-priority"><span className="eyebrow"><span className="orange-dash"/>TOP PRIORITY</span><p>{priority(data,analysis)}</p><span className="tiny-label">FROM YOUR FINANCIAL PLAN</span></section></aside></div>
  </div>;
}
