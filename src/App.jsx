import { useEffect, useState, useCallback } from 'react';
import { Plus, Home, Wallet, ChartNoAxesCombined, Sparkles, ArrowUpRight } from 'lucide-react';
import MerchantDemo from './components/MerchantDemo.jsx';
import BudgetPlusWallet from './components/BudgetPlusWallet.jsx';
import HomePage from './components/Home.jsx';

import AICoach from './components/AICoach.jsx';
import Money from './components/Money.jsx';
import { usePlaidConnection } from './components/PlaidConnect.jsx';
import { api, settingsFrom } from './utils/api.js';


export default function App() {
  const [snapshot, setSnapshot] = useState(null);
  const [view, setView] = useState('home');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [lastSync, setLastSync] = useState(null);
  const merchant = /^\/(merchant|tap)(\/|$)/.test(window.location.pathname);
  const accept = useCallback(next => { setSnapshot(old => !old || next.revision >= old.revision ? next : old); setLastSync(new Date()); }, []);
  const plaid = usePlaidConnection(snapshot, accept, !merchant);
  useEffect(() => {
    if (merchant) return;
    let stopped = false, timer;
    async function poll() {
      try { const next = await api('/state'); if (!stopped) { accept(next); setError(''); } }
      catch (e) { if (!stopped) setError(e.message); }
      finally { if (!stopped) timer = setTimeout(poll, 2500); }
    }
    poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [merchant, accept]);
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }); }, [view]);
  if (merchant) return <MerchantDemo/>;
  async function update(next) {
    setBusy(true);
    try { accept(await api('/settings', { method:'PUT', body:JSON.stringify({ ...settingsFrom(next), revision:snapshot.revision }) })); setNotice('Saved.'); }
    catch (e) { setNotice(e.message); }
    finally { setBusy(false); }
  }
  async function reset() {
    if (!window.confirm('Replace all imported history, settings and authorization records with the original demo?')) return;
    setBusy(true);
    try { accept(await api('/reset', {method:'POST'})); setNotice('Demo restored.'); }
    catch (e) { setNotice(e.message); }
    finally { setBusy(false); }
  }
  async function randomize() {
    if (busy || snapshot?.data.mode !== 'demo') return;
    setBusy(true);
    try {
      const next = await api('/randomize', {method:'POST', body:JSON.stringify({revision:snapshot.revision})});
      accept(next);
      setNotice(`Demo ready: ${next.data.demoScenario.label}. Score, categories, and routing updated.`);
    } catch (e) { setNotice(e.message); }
    finally { setBusy(false); }
  }
  const data = snapshot?.data, analysis = snapshot?.analysis;
  return <div className={`app-shell view-${view}`}><a className="skip-link" href="#main">Skip to content</a>
    <header className="site-header"><div className="header-inner"><a href="/" className="brand"><span className="brand-icon"><Plus size={24}/></span>BudgetPlus</a>
      <nav aria-label="Main navigation">{[['home','Home',Home],['money','Money',ChartNoAxesCombined],['wallet','Wallet',Wallet],['coach','AI Coach',Sparkles]].map(([id,label,Icon]) => <button key={id} aria-current={view===id?'page':undefined} className={`nav-link ${view===id?'active':''}`} onClick={() => setView(id)}><Icon size={16}/>{label}</button>)}</nav>
      <a className="header-demo" href="/merchant" target="_blank" rel="noreferrer">Try the card <ArrowUpRight size={16}/></a>
    </div></header>
    <div className="main-shell">{error && <div className="notice" role="alert">Connection interrupted: {error} Retrying automatically.</div>}{notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss">&times;</button></div>}
    <main id="main" tabIndex={-1}>{!snapshot ? <div className="loading-state"><span className="loading-orbit"/><p>Connecting your financial world...</p></div> : <>
  {view==='home' && <HomePage data={data} analysis={analysis} navigate={setView}/>}
  {view==='money' && <Money snapshot={snapshot} accept={accept} setNotice={setNotice} plaid={plaid}/>}
  {view==='wallet' && <BudgetPlusWallet data={data} analysis={analysis} decisions={snapshot.decisions} update={update} busy={busy}/>}
  {view==='coach' && <AICoach revision={snapshot.revision} data={data} analysis={analysis}/>}
  </>}</main><footer className="site-footer"><div className="footer-top"><a href="/" className="brand"><span className="brand-icon"><Plus size={20}/></span>BudgetPlus</a><span>One card. No decisions.</span><a href="/merchant" target="_blank" rel="noreferrer">Open merchant demo <ArrowUpRight size={14}/></a></div><div className="footer-bottom"><p>Prototype. No real charges. BudgetPlus Score measures financial health, not creditworthiness.</p><div className="workspace-tools"><span>{data?.mode==='personal'?'MY DATA':(data?.demoScenario?.label ? `Demo: ${data.demoScenario.label}` : 'Demo workspace')}{lastSync?' / Connected':''}</span><button className="text-button" disabled={busy||data?.mode!=='demo'} title={data?.mode==='personal'?'Available in Demo Mode only; imported data is protected.':'Generate a new synthetic financial situation'} onClick={randomize}>RANDOMIZE FINANCIAL SNAPSHOT</button><button className="text-button" disabled={busy||!snapshot} onClick={reset}>Reset demo</button></div></div></footer></div></div>;
}
