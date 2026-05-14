import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, openWorkflowSocket } from '../api/client';
import ForecastChart from '../components/ForecastChart';
import WaterfallChart from '../components/WaterfallChart';
import CommentaryCard from '../components/CommentaryCard';

export default function Dashboard() {
  const [params] = useSearchParams();
  const workflowId = params.get('workflow');
  const [companyId, setCompanyId] = useState(localStorage.getItem('companyId') || '');
  const [period, setPeriod] = useState('2024-09-01');
  const [forecasts, setForecasts] = useState([]);
  const [variances, setVariances] = useState([]);
  const [commentary, setCommentary] = useState(null);
  const [wsEvents, setWsEvents] = useState([]);

  // Workflow live status
  useEffect(() => {
    if (!workflowId) return;
    const ws = openWorkflowSocket(workflowId, ev => {
      setWsEvents(prev => [ev, ...prev].slice(0, 50));
    });
    return () => ws.close();
  }, [workflowId]);

  async function loadAll() {
    if (!companyId) return;
    try { setForecasts(await api.forecasts(companyId)); } catch {}
    try { setVariances(await api.variances(companyId, period)); } catch {}
    try { setCommentary(await api.commentary(companyId, period)); }
    catch { setCommentary(null); }
  }

  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, [companyId, period]);

  // Group forecasts by metric for chart picker
  const byMetric = useMemo(() => {
    const m = {};
    for (const f of forecasts) (m[f.metric_name] ??= []).push(f);
    return m;
  }, [forecasts]);
  const [pickedMetric, setPickedMetric] = useState(null);
  useEffect(() => {
    if (!pickedMetric && Object.keys(byMetric).length) {
      setPickedMetric(Object.keys(byMetric)[0]);
    }
  }, [byMetric, pickedMetric]);

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="card flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600">Company ID</label>
          <input
            value={companyId}
            onChange={e => { setCompanyId(e.target.value); localStorage.setItem('companyId', e.target.value); }}
            className="mt-1 border border-slate-300 rounded px-2 py-1 text-sm font-mono w-72"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600">Period</label>
          <input
            type="date" value={period}
            onChange={e => setPeriod(e.target.value)}
            className="mt-1 border border-slate-300 rounded px-2 py-1 text-sm"
          />
        </div>
        <button onClick={loadAll} className="btn-primary">Refresh</button>
        {workflowId && (
          <span className="text-xs text-slate-500 ml-auto">Workflow: <code>{workflowId}</code></span>
        )}
      </div>

      {/* Forecast + Waterfall side by side */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold">Forecast (next 6 months)</h3>
            <select
              value={pickedMetric || ''}
              onChange={e => setPickedMetric(e.target.value)}
              className="text-sm border border-slate-300 rounded px-2 py-1"
            >
              {Object.keys(byMetric).map(m => <option key={m}>{m}</option>)}
            </select>
          </div>
          <ForecastChart points={byMetric[pickedMetric] || []} />
        </div>
        <div className="card">
          <h3 className="font-semibold mb-2">EBITDA waterfall (top variance drivers)</h3>
          <WaterfallChart variances={variances} />
        </div>
      </div>

      {/* Variance table + Commentary + Live activity */}
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="card lg:col-span-2 overflow-x-auto">
          <h3 className="font-semibold mb-2">Variance records — {period}</h3>
          <table className="min-w-full text-sm">
            <thead className="text-left text-slate-500 border-b">
              <tr>
                <th className="py-2 pr-3">Metric</th>
                <th className="py-2 pr-3 text-right">Actual</th>
                <th className="py-2 pr-3 text-right">Budget</th>
                <th className="py-2 pr-3 text-right">Δ %</th>
                <th className="py-2 pr-3">Materiality</th>
                <th className="py-2 pr-3">Fav?</th>
              </tr>
            </thead>
            <tbody>
              {variances.map((v, i) => (
                <tr key={i} className="border-b hover:bg-slate-50">
                  <td className="py-2 pr-3 font-mono">{v.metric_name}</td>
                  <td className="py-2 pr-3 text-right">{Number(v.actual_amount).toLocaleString()}</td>
                  <td className="py-2 pr-3 text-right">{Number(v.budget_amount).toLocaleString()}</td>
                  <td className={`py-2 pr-3 text-right ${v.is_favorable ? 'text-emerald-700' : 'text-red-700'}`}>
                    {Number(v.variance_pct).toFixed(1)}%
                  </td>
                  <td className="py-2 pr-3">
                    <span className={
                      v.materiality === 'CRITICAL' ? 'tag-crit' :
                      v.materiality === 'MATERIAL' ? 'tag-risk' :
                      v.materiality === 'NOTABLE'  ? 'tag-ok' : 'tag-strong'
                    }>{v.materiality}</span>
                  </td>
                  <td className="py-2 pr-3">{v.is_favorable ? '✓' : '✗'}</td>
                </tr>
              ))}
              {!variances.length && (
                <tr><td className="py-3 text-slate-500" colSpan={6}>No variances loaded.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="space-y-4">
          <CommentaryCard commentary={commentary} />
          <div className="card">
            <h3 className="font-semibold mb-2">Live workflow events</h3>
            {!workflowId && <p className="text-xs text-slate-500">Add ?workflow=ID to URL to subscribe.</p>}
            <ul className="text-xs space-y-1 max-h-64 overflow-auto">
              {wsEvents.map((ev, i) => (
                <li key={i} className="font-mono text-slate-700 truncate">
                  {ev.event || 'event'}: {ev.agent_name || ev.tool_name || ''}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
