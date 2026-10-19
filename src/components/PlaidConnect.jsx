import { useCallback, useEffect, useRef, useState } from 'react';
import { usePlaidLink } from 'react-plaid-link';
import { api } from '../utils/api.js';
import { money } from '../utils/format.js';

// Kept at App level so importing continues while the user visits Home or AI Coach.
export function usePlaidConnection(snapshot, accept, enabled = true) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false), importing = useRef(false), nextSync = useRef(0);
  const current = useRef(snapshot);
  useEffect(() => {
    if (current.current?.data.mode === 'personal' && snapshot?.data.mode === 'demo') importing.current = false;
    current.current = snapshot;
  }, [snapshot]);
  const refresh = useCallback(async () => {
    const next = await api('/plaid/status');
    setStatus(next);
    return next;
  }, []);
  const sync = useCallback(async (manual = true) => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    if (manual) importing.current = true;
    try {
      const next = await api('/plaid/sync', { method: 'POST', body: JSON.stringify({ background: !importing.current }) });
      accept(next); setStatus(next.plaidStatus);
      if (next.plaidStatus.historyReady) importing.current = false;
      const failures = next.plaidStatus.items.filter(i => i.error);
      if (failures.length) setError(failures.map(i => `${i.institution}: ${i.error}`).join(' '));
      nextSync.current = Date.now() + (next.plaidStatus.historyReady ? 300000 : 15000);
    } catch (e) {
      setError(e.message); nextSync.current = Date.now() + 30000;
      try { await refresh(); } catch { /* Preserve the last good summary. */ }
    } finally { inFlight.current = false; setBusy(false); }
  }, [accept, refresh]);
  useEffect(() => {
    if (!enabled) return;
    let stopped = false, timer;
    async function poll() {
      try {
        const next = await refresh();
        if (!stopped && next.configured && next.items.length && Date.now() >= nextSync.current &&
            (importing.current || (current.current?.data.mode === 'personal' && current.current?.data.plaid?.environment === next.environment))) {
          await sync(false);
        }
      } catch { /* A missing Plaid service must never interrupt the workspace. */ }
      if (!stopped) timer = setTimeout(poll, 10000);
    }
    poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [refresh, sync, enabled]);
  return { status, busy, error, sync, refresh };
}

function LinkSession({ token, updateMode, onDone, onClose }) {
  const launched = useRef(false);
  const onSuccess = useCallback(async publicToken => {
    try {
      if (!updateMode) await api('/plaid/exchange-token', { method: 'POST', body: JSON.stringify({ public_token: publicToken }) });
      onDone();
    } catch (e) { onClose(e.message); }
  }, [updateMode, onDone, onClose]);
  const { open, ready, error } = usePlaidLink({ token, onSuccess,
    onExit: err => onClose(err ? 'The connection was not completed. Please try again or check your Plaid setup.' : '') });
  useEffect(() => {
    if (ready && !launched.current) { launched.current = true; open(); }
  }, [ready, open]);
  useEffect(() => {
    if (error) onClose('Plaid Link could not load. Check your connection and try again.');
  }, [error, onClose]);
  useEffect(() => {
    if (ready) return;
    const timer = setTimeout(() => onClose('Plaid Link did not load. Check your connection or browser content blocker and try again.'), 30000);
    return () => clearTimeout(timer);
  }, [ready, onClose]);
  return null;
}

export default function PlaidConnect({ connection, data }) {
  const { status, busy, error, sync, refresh } = connection;
  const [session, setSession] = useState(null), [connecting, setConnecting] = useState(false);
  const [linkError, setLinkError] = useState(''), [accounts, setAccounts] = useState([]);
  const close = useCallback(message => { setSession(null); setConnecting(false); setLinkError(message); }, []);
  const done = useCallback(() => { close(''); sync(); }, [close, sync]);
  async function connect(itemId) {
    setConnecting(true); setLinkError('');
    try { setSession(await api('/plaid/link-token', { method: 'POST', body: JSON.stringify(itemId ? { itemId } : {}) })); }
    catch (e) { close(e.message); }
  }
  useEffect(() => {
    if (!status?.items.length) { setAccounts([]); return; }
    let stopped = false;
    api('/plaid/accounts').then(result => { if (!stopped) setAccounts(result.accounts); }).catch(() => {});
    return () => { stopped = true; };
  }, [status]);
  const active = data.mode === 'personal' && data.plaid?.environment === status?.environment;
  const ready = active && status?.historyReady;
  return <div className="plaid-connection">
    <div className="action-row"><button className="primary-button" disabled={busy || connecting} onClick={() => connect()}>{status?.items.length ? 'CONNECT ANOTHER ACCOUNT' : 'CONNECT MY ACCOUNTS'}</button>
      {!!status?.items.length && <button className="secondary-button" disabled={busy || connecting} onClick={() => sync()}>{busy ? 'Importing history...' : active ? 'Sync accounts' : 'Use MY DATA'}</button>}</div>
    {status?.environment === 'sandbox' && <p className="category-advice">Plaid Sandbox uses test accounts, not your real bank data.</p>}
    {connecting && <p role="status">Connecting accounts</p>}
    {session && <LinkSession token={session.link_token} updateMode={session.updateMode} onDone={done} onClose={close}/>}
    {(busy || (active && !ready)) && <p role="status">Importing history. Your institution may take a few minutes to prepare it; BudgetPlus checks automatically while this app is open.</p>}
    {ready && <div role="status"><p className="category-advice">Connecting accounts ✓ · Importing history ✓ · Understanding your spending ✓ · Building your profile ✓ · Calculating your BudgetPlus Score ✓</p><strong>YOUR PROFILE IS READY</strong></div>}
    {!!status?.items.length && <p>{status.institutions} institutions · {status.accounts} accounts · {status.transactions} transactions · {status.monthsAnalyzed} months analyzed</p>}
    {status?.excludedAccounts > 0 && <p className="category-advice">{status.excludedAccounts} accounts are outside this USD checking, savings and credit-card profile. They are listed below but excluded from its totals.</p>}
    {(linkError || error) && <p className="notice" role="alert">{linkError || error} Demo profiles and file uploads remain available.</p>}
    {!!status?.items.length && <details><summary>Connected institutions and accounts</summary>
      {status.items.map(item => <div key={item.item_id}><p><strong>{item.institution}</strong> · {item.last_sync ? `Last synced ${new Date(item.last_sync).toLocaleString()}` : 'Waiting for first import'}</p>
        {item.error && <p className="warning-text">{item.error}</p>}
        <button className="text-button" disabled={busy || connecting} onClick={() => connect(item.item_id)}>Repair connection</button>
        {accounts.filter(a => a.plaidItemId === item.item_id).map(a => <p key={a.id}>{a.name} {a.last4 ? `•••• ${a.last4}` : ''} · {a.subtype || a.type} · {a.currency || 'Unknown currency'} · Current {a.current == null ? 'unavailable' : money(a.current)} · Available {a.available == null ? 'unavailable' : money(a.available)}{a.type === 'credit' ? ` · Limit ${a.creditLimit == null ? 'unavailable' : money(a.creditLimit)}` : ''}</p>)}</div>)}
      <button className="text-button" onClick={() => refresh().catch(e => setLinkError(e.message))}>Refresh connection status</button>
    </details>}
  </div>;
}
