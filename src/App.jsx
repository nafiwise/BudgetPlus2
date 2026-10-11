import { useEffect, useState, useCallback } from 'react';
import { Plus, Home, Wallet, ChartNoAxesCombined, Sparkles, ArrowUpRight, Settings as SettingsIcon, Wifi, WifiOff } from 'lucide-react';
import { App as CapApp } from '@capacitor/app';
import { StatusBar, Style } from '@capacitor/status-bar';
import MerchantDemo from './components/MerchantDemo.jsx';
import BudgetPlusWallet from './components/BudgetPlusWallet.jsx';
import HomePage from './components/Home.jsx';
import AICoach from './components/AICoach.jsx';
import Money from './components/Money.jsx';
import { usePlaidConnection } from './components/PlaidConnect.jsx';
import { api, settingsFrom } from './utils/api.js';
import { isNativePlatform, getApiBaseUrl, setCustomApiBase, getCustomApiBase } from './utils/config.js';
import { getPreference, setPreference } from './utils/persistence.js';

export default function App() {
  const [snapshot, setSnapshot] = useState(null);
  const [view, setView] = useState(() => getPreference('budgetplus_view', 'home'));
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [lastSync, setLastSync] = useState(null);
  const [showConfig, setShowConfig] = useState(false);
  const [customUrl, setCustomUrl] = useState(getCustomApiBase());

  const merchantUrl = /^\/(merchant|tap)(\/|$)/.test(window.location.pathname);
  const isMerchant = merchantUrl || view === 'merchant';

  const accept = useCallback(next => {
    setSnapshot(old => !old || next.revision >= old.revision ? next : old);
    setLastSync(new Date());
  }, []);

  const changeView = useCallback(nextView => {
    setView(nextView);
    setPreference('budgetplus_view', nextView);
  }, []);

  const plaid = usePlaidConnection(snapshot, accept, !isMerchant);

  // Setup Capacitor native plugins
  useEffect(() => {
    if (isNativePlatform()) {
      try {
        StatusBar.setStyle({ style: Style.Dark });
        StatusBar.setBackgroundColor({ color: '#0c0f0d' });
      } catch {}
      try {
        const sub = CapApp.addListener('appUrlOpen', event => {
          if (event?.url) {
            try {
              const u = new URL(event.url);
              if (u.pathname.includes('merchant') || u.pathname.includes('tap') || u.search.includes('tap')) {
                changeView('merchant');
              }
            } catch {}
          }
        });
        return () => { sub.then(h => h.remove()).catch(() => {}); };
      } catch {}
    }
  }, [changeView]);

  // Polling backend state
  useEffect(() => {
    if (isMerchant) return;
    let stopped = false, timer;
    async function poll() {
      try {
        const next = await api('/state');
        if (!stopped) {
          accept(next);
          setError('');
        }
      } catch (e) {
        if (!stopped) setError(e.message);
      } finally {
        if (!stopped) timer = setTimeout(poll, 2500);
      }
    }
    poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [isMerchant, accept]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [view]);

  if (isMerchant) {
    return <MerchantDemo onBack={() => changeView('wallet')} />;
  }

  async function update(next) {
    setBusy(true);
    try {
      accept(await api('/settings', { method: 'PUT', body: JSON.stringify({ ...settingsFrom(next), revision: snapshot.revision }) }));
      setNotice('Saved.');
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    if (!window.confirm('Replace all imported history, settings and authorization records with the original demo?')) return;
    setBusy(true);
    try {
      accept(await api('/reset', { method: 'POST' }));
      setNotice('Demo restored.');
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function randomize() {
    if (busy || snapshot?.data.mode !== 'demo') return;
    setBusy(true);
    try {
      const next = await api('/randomize', { method: 'POST', body: JSON.stringify({ revision: snapshot.revision }) });
      accept(next);
      setNotice(`Demo ready: ${next.data.demoScenario.label}. Score, categories, and routing updated.`);
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  function handleSaveUrl(e) {
    e.preventDefault();
    setCustomApiBase(customUrl);
    setShowConfig(false);
    setError('');
    setNotice('Backend URL updated. Reconnecting...');
    api('/state').then(accept).catch(err => setError(err.message));
  }

  const data = snapshot?.data, analysis = snapshot?.analysis;
  const currentBase = getApiBaseUrl() || (isNativePlatform() ? 'Not configured' : 'Local proxy');

  return (
    <div className={`app-shell view-${view}`}>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="site-header">
        <div className="header-inner">
          <a href="/" className="brand" onClick={e => { e.preventDefault(); changeView('home'); }}>
            <span className="brand-icon"><Plus size={24}/></span>BudgetPlus
          </a>
          <nav aria-label="Main navigation">
            {[
              ['home', 'Home', Home],
              ['money', 'Money', ChartNoAxesCombined],
              ['wallet', 'Wallet', Wallet],
              ['coach', 'AI Coach', Sparkles]
            ].map(([id, label, Icon]) => (
              <button
                key={id}
                aria-current={view === id ? 'page' : undefined}
                className={`nav-link ${view === id ? 'active' : ''}`}
                onClick={() => changeView(id)}
              >
                <Icon size={16}/>{label}
              </button>
            ))}
          </nav>
          <div className="header-actions">
            <button
              type="button"
              className="connection-pill"
              title={`Backend: ${currentBase}`}
              onClick={() => setShowConfig(true)}
              aria-label="Server connection settings"
            >
              {error ? <WifiOff size={14} className="conn-off"/> : <Wifi size={14} className="conn-on"/>}
              <span className="conn-label">{isNativePlatform() ? 'App' : 'Web'}</span>
            </button>
            <button
              type="button"
              className="header-demo"
              onClick={() => changeView('merchant')}
            >
              Try the card <ArrowUpRight size={16}/>
            </button>
          </div>
        </div>
      </header>

      {/* Connection configuration modal for mobile / remote debugging */}
      {showConfig && (
        <div className="modal-backdrop" onClick={() => setShowConfig(false)}>
          <div className="modal-sheet" onClick={e => e.stopPropagation()}>
            <div className="section-heading">
              <div>
                <span className="eyebrow">MOBILE CONFIGURATION</span>
                <h3>Backend Server Connection</h3>
              </div>
              <button className="text-button" onClick={() => setShowConfig(false)}>✕</button>
            </div>
            <p className="category-advice">
              Platform: <strong>{isNativePlatform() ? 'iOS Native App (Capacitor)' : 'Web Browser'}</strong>
            </p>
            <form onSubmit={handleSaveUrl}>
              <label>
                FastAPI Base URL
                <input
                  type="url"
                  placeholder="e.g. https://xxxx.trycloudflare.com or https://api.example.com"
                  value={customUrl}
                  onChange={e => setCustomUrl(e.target.value)}
                />
              </label>
              <p className="category-advice">Leave blank to use default (local proxy in browser, or build-time URL).</p>
              <div className="action-row">
                <button type="submit" className="primary-button">Save &amp; Reconnect</button>
                <button type="button" className="secondary-button" onClick={() => { setCustomUrl(''); setCustomApiBase(''); setShowConfig(false); }}>Reset Default</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="main-shell">
        {error && (
          <div className="notice" role="alert">
            <span>Connection issue: {error}</span>
            <button type="button" className="text-button" onClick={() => setShowConfig(true)}>Configure Server</button>
          </div>
        )}
        {notice && (
          <div className="notice" role="status">
            {notice}
            <button onClick={() => setNotice('')} aria-label="Dismiss">&times;</button>
          </div>
        )}
        <main id="main" tabIndex={-1}>
          {!snapshot ? (
            <div className="loading-state">
              <span className="loading-orbit"/>
              <p>Connecting your financial world...</p>
              {error && (
                <button type="button" className="secondary-button" onClick={() => setShowConfig(true)}>
                  <SettingsIcon size={16}/> Configure Server URL
                </button>
              )}
            </div>
          ) : (
            <>
              {view === 'home' && <HomePage data={data} analysis={analysis} navigate={changeView}/>}
              {view === 'money' && <Money snapshot={snapshot} accept={accept} setNotice={setNotice} plaid={plaid}/>}
              {view === 'wallet' && <BudgetPlusWallet data={data} analysis={analysis} decisions={snapshot.decisions} update={update} busy={busy} navigate={changeView}/>}
              {view === 'coach' && <AICoach revision={snapshot.revision} data={data} analysis={analysis}/>}
            </>
          )}
        </main>
        <footer className="site-footer">
          <div className="footer-top">
            <a href="/" className="brand" onClick={e => { e.preventDefault(); changeView('home'); }}>
              <span className="brand-icon"><Plus size={20}/></span>BudgetPlus
            </a>
            <span>One card. No decisions.</span>
            <button type="button" className="text-button" onClick={() => changeView('merchant')}>
              Open merchant demo <ArrowUpRight size={14}/>
            </button>
          </div>
          <div className="footer-bottom">
            <p>Prototype. No real charges. BudgetPlus Score measures financial health, not creditworthiness.</p>
            <div className="workspace-tools">
              <span>{data?.mode === 'personal' ? 'MY DATA' : (data?.demoScenario?.label ? `Demo: ${data.demoScenario.label}` : 'Demo workspace')}{lastSync ? ' / Connected' : ''}</span>
              <button
                className="text-button"
                disabled={busy || data?.mode !== 'demo'}
                title={data?.mode === 'personal' ? 'Available in Demo Mode only; imported data is protected.' : 'Generate a new synthetic financial situation'}
                onClick={randomize}
              >
                RANDOMIZE FINANCIAL SNAPSHOT
              </button>
              <button className="text-button" disabled={busy || !snapshot} onClick={reset}>Reset demo</button>
            </div>
          </div>
        </footer>
      </div>

      {/* Polished Native Mobile Bottom Tab Bar */}
      <nav className="mobile-bottom-nav" aria-label="Mobile Navigation">
        {[
          ['home', 'Home', Home],
          ['money', 'Money', ChartNoAxesCombined],
          ['wallet', 'Wallet', Wallet],
          ['coach', 'AI Coach', Sparkles]
        ].map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            aria-current={view === id ? 'page' : undefined}
            className={`mobile-nav-link ${view === id ? 'active' : ''}`}
            onClick={() => changeView(id)}
          >
            <Icon size={20}/>
            <span>{label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
