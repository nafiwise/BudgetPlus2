export async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), path === '/state' ? 15000 : path === '/plaid/sync' ? 300000 : 60000);
  try {
    const response = await fetch(`/api${path}`, { ...options, signal:controller.signal, headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(e => `${e.loc.join('.')}: ${e.msg}`).join('; ') : `Backend unavailable (${response.status}). Start FastAPI on port 8000.`);
    }
    return payload;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Backend request timed out. Check the connection.');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
export const settingsKeys = ['accounts','cards','goals','debts','upcoming','recurring','buffer','guardrail','balancesConfirmed','categoryImportance'];
export const settingsFrom = data => Object.fromEntries(settingsKeys.map(key => [key, data[key]]));
