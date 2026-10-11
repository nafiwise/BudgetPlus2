import { useEffect, useState } from 'react';
import { api } from '../utils/api.js';

export default function LithicControls() {
  const [status, setStatus] = useState(null), [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  useEffect(() => { api('/lithic/status').then(setStatus).catch(e => setMessage(e.message)); }, []);
  async function action(path, method = 'POST') {
    setBusy(true); setMessage('');
    try {
      const result = await api(path, { method });
      setStatus(await api('/lithic/status'));
      setMessage(result.notice || (path.includes('create-card') ? 'Mastercard Sandbox card is ready.' : path.includes('pause') ? 'Card state updated.' : 'ASA status checked.'));
    } catch (e) { setMessage(e.message); }
    finally { setBusy(false); }
  }
  return <details className="panel compact-section"><summary>Lithic Sandbox card &amp; ASA</summary>
    {!status?.enabled && <p>Add LITHIC_API_KEY to backend/.env and restart BudgetPlus to enable Lithic Sandbox.</p>}
    <p>{status?.card ? `Mastercard ending ${status.card.last_four} / ${status.card.state}` : 'Create a virtual Mastercard test card for BudgetPlus.'}</p>
    <div className="action-row">
      {!status?.card && <button className="primary-button" disabled={busy || !status?.enabled} onClick={() => action('/lithic/create-card')}>Create Mastercard Sandbox card</button>}
      {status?.card && <button className="secondary-button" disabled={busy || !status.enabled} onClick={() => action(status.card.state === 'OPEN' ? '/lithic/card/pause' : '/lithic/card/unpause')}>{status.card.state === 'OPEN' ? 'Pause Sandbox card' : 'Unpause Sandbox card'}</button>}
      <button className="secondary-button" disabled={busy || !status?.enabled} onClick={() => action('/lithic/responder/enroll')}>Enroll ASA</button>
      <button className="text-button" disabled={busy || !status?.enabled} onClick={() => action('/lithic/responder/status', 'GET')}>Check ASA connection</button>
    </div>
    <p>ASA: {status?.responder?.matches ? 'Enrolled at the configured URL' : 'Not enrolled at the configured URL'}. Signature verification: {status?.signatureReady ? 'Ready' : 'Not configured'}.</p>
    {status?.lastVerifiedAuthorizationAt && <p>Last verified ASA authorization: {new Date(status.lastVerifiedAuthorizationAt).toLocaleString()}</p>}
    <p className="category-advice">Set PUBLIC_BACKEND_URL to your temporary HTTPS tunnel before enrolling. The tunnel and BudgetPlus must stay running. Signature headers can take a few minutes to activate after enrollment.</p>
    {busy && <p role="status">Contacting Lithic Sandbox...</p>}{message && <p className="notice" role="status">{message}</p>}
  </details>;
}
