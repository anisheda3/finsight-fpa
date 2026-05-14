// Thin fetch client.  Uses Vite proxy in dev (so just /api works).
const BASE = import.meta.env.VITE_API_BASE || '';

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

export const api = {
  health:        ()                              => request('/api/v1/health'),
  uploadActuals: (companyId, file, fmt = 'csv') => {
    const fd = new FormData();
    fd.append('company_id', companyId);
    fd.append('file', file);
    fd.append('file_format', fmt);
    return fetch('/api/v1/actuals/upload', { method: 'POST', body: fd })
      .then(r => r.json());
  },
  listActuals:   (companyId, period, metric)   => {
    const q = new URLSearchParams();
    if (period) q.set('period', period);
    if (metric) q.set('metric', metric);
    const qs = q.toString() ? `?${q}` : '';
    return request(`/api/v1/actuals/${companyId}${qs}`);
  },
  forecasts:     (companyId)                    => request(`/api/v1/forecasts/${companyId}`),
  rerunForecast: (body)                         => request('/api/v1/forecasts/rerun',
                                                           { method: 'POST', body: JSON.stringify(body) }),
  variances:     (companyId, period, mat)       => {
    const q = new URLSearchParams();
    if (period) q.set('period', period);
    if (mat)    q.set('materiality', mat);
    const qs = q.toString() ? `?${q}` : '';
    return request(`/api/v1/variances/${companyId}${qs}`);
  },
  scenarios:     (companyId)                    => request(`/api/v1/insights/scenarios/${companyId}`),
  runScenarios:  (body)                         => request('/api/v1/insights/scenarios/run',
                                                           { method: 'POST', body: JSON.stringify(body) }),
  commentary:    (companyId, period)            => request(`/api/v1/insights/commentary/${companyId}/${period}`),
  hitlRespond:   (body)                         => request('/api/v1/hitl/respond',
                                                           { method: 'POST', body: JSON.stringify(body) }),
  hitlOverride:  (flagId, body)                 => request(`/api/v1/hitl/${flagId}/override`,
                                                           { method: 'POST', body: JSON.stringify(body) }),
  hitlPending:   ()                             => request('/api/v1/hitl/pending'),
};

export function openWorkflowSocket(workflowId, onMessage) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/workflow/${workflowId}`);
  ws.onmessage = ev => {
    try { onMessage(JSON.parse(ev.data)); }
    catch { onMessage({ raw: ev.data }); }
  };
  return ws;
}
