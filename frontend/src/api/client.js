/**
 * API client with:
 *  - automatic retry on 503 (backend booting)
 *  - request deduplication (prevents duplicate in-flight requests)
 *  - AbortController support
 */

const BASE = import.meta.env.VITE_API_BASE || '';

// In-flight request dedup map
const _inflight = new Map();

async function request(path, opts = {}) {
  const key = `${opts.method || 'GET'}:${path}`;

  // For GET requests, deduplicate concurrent calls
  if (!opts.method || opts.method === 'GET') {
    if (_inflight.has(key)) return _inflight.get(key);
  }

  const promise = _doRequest(path, opts).finally(() => _inflight.delete(key));

  if (!opts.method || opts.method === 'GET') {
    _inflight.set(key, promise);
  }

  return promise;
}

async function _doRequest(path, opts = {}, attempt = 0) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);

  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(opts.headers || {}),
      },
      signal: controller.signal,
      ...opts,
    });
    clearTimeout(timeout);

    if (res.status === 503 && attempt < 2) {
      await new Promise(r => setTimeout(r, 800 * (attempt + 1)));
      return _doRequest(path, opts, attempt + 1);
    }

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status} ${res.statusText}${text ? ': ' + text : ''}`);
    }

    const ct = res.headers.get('content-type') || '';
    return ct.includes('application/json') ? res.json() : res.text();
  } catch (e) {
    clearTimeout(timeout);
    if (e.name === 'AbortError') throw new Error('Request timed out');
    throw e;
  }
}

export const api = {
  health: () => request('/api/v1/health'),

  uploadActuals: (companyId, file, fmt = 'csv') => {
    const fd = new FormData();
    fd.append('company_id', companyId);
    fd.append('file', file);
    fd.append('file_format', fmt);
    return _doRequest('/api/v1/actuals/upload', { method: 'POST', body: fd, headers: {} });
  },

  listActuals: (companyId, period, metric) => {
    const q = new URLSearchParams();
    if (period) q.set('period', period);
    if (metric) q.set('metric', metric);
    const qs = q.toString() ? `?${q}` : '';
    return request(`/api/v1/actuals/${companyId}${qs}`);
  },

  forecasts:     (companyId) => request(`/api/v1/forecasts/${companyId}`),
  rerunForecast: (body)       => request('/api/v1/forecasts/rerun', { method: 'POST', body: JSON.stringify(body) }),

  variances: (companyId, period, mat) => {
    const q = new URLSearchParams();
    if (period) q.set('period', period);
    if (mat)    q.set('materiality', mat);
    const qs = q.toString() ? `?${q}` : '';
    return request(`/api/v1/variances/${companyId}${qs}`);
  },

  scenarios:   (companyId) => request(`/api/v1/insights/scenarios/${companyId}`),
  runScenarios: (body)       => request('/api/v1/insights/scenarios/run', { method: 'POST', body: JSON.stringify(body) }),
  commentary:  (companyId, period) => request(`/api/v1/insights/commentary/${companyId}/${period}`),

  hitlRespond:  (body)         => request('/api/v1/hitl/respond', { method: 'POST', body: JSON.stringify(body) }),
  hitlOverride: (flagId, body) => request(`/api/v1/hitl/${flagId}/override`, { method: 'POST', body: JSON.stringify(body) }),
  hitlPending:  (companyId)     => request(`/api/v1/hitl/pending${companyId ? `?company_id=${companyId}` : ''}`),
};

export function openWorkflowSocket(workflowId, onMessage) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/workflow/${workflowId}`);
  ws.onmessage = ev => {
    try { onMessage(JSON.parse(ev.data)); }
    catch { onMessage({ raw: ev.data }); }
  };
  ws.onerror = () => {};
  return ws;
}
