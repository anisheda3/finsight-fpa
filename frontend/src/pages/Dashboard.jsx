import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, openWorkflowSocket } from '../api/client';
import { getCompanyId, getCache, setCache, setCompanyId } from '../store';
import { usePersistedData } from '../hooks/usePersistedData';
import ForecastChart from '../components/ForecastChart';
import WaterfallChart from '../components/WaterfallChart';
import CommentaryCard from '../components/CommentaryCard';
import StatCard from '../components/StatCard';
import Spinner from '../components/Spinner';
import ErrorBanner from '../components/ErrorBanner';

const fmt = v => `₹${(Number(v) / 1e7).toFixed(2)}Cr`;
const pct = v => `${Number(v).toFixed(1)}%`;

export default function Dashboard() {
  const [params] = useSearchParams();
  const workflowId = params.get('workflow');
  const [companyId, setLocalCid] = useState(getCompanyId());
  const [period, setPeriod] = useState(() => getCache('dashboard-period') || '2024-09-01');
  const [wsEvents, setWsEvents] = useState([]);
  const [pickedMetric, setPickedMetric] = useState(null);

  const savePeriod = v => { setPeriod(v); setCache('dashboard-period', v); };

  // ── Data fetching with persistence ──────────────────────────────────
  const fetchForecasts = useCallback(
    () => companyId ? api.forecasts(companyId) : Promise.resolve([]),
    [companyId]
  );
  const fetchVariances = useCallback(
    () => companyId && period ? api.variances(companyId, period) : Promise.resolve([]),
    [companyId, period]
  );
  const fetchCommentary = useCallback(
    () => companyId && period ? api.commentary(companyId, period).catch(() => null) : Promise.resolve(null),
    [companyId, period]
  );

  const { data: forecasts, loading: fcLoading, error: fcError, refresh: fcRefresh } =
    usePersistedData(`forecasts-${companyId}`, fetchForecasts, { ttlMs: 120_000 });
  const { data: variances, loading: vrLoading, error: vrError, refresh: vrRefresh } =
    usePersistedData(`variances-${companyId}-${period}`, fetchVariances, { ttlMs: 90_000 });
  const { data: commentary, loading: cmLoading, refresh: cmRefresh } =
    usePersistedData(`commentary-${companyId}-${period}`, fetchCommentary, { ttlMs: 300_000 });

  // ── WebSocket ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!workflowId) return;
    const ws = openWorkflowSocket(workflowId, ev => {
      setWsEvents(prev => [{ ...ev, _ts: new Date().toLocaleTimeString() }, ...prev].slice(0, 50));
    });
    return () => ws.close();
  }, [workflowId]);

  // ── Derived ──────────────────────────────────────────────────────────
  const byMetric = useMemo(() => {
    const m = {};
    for (const f of (forecasts || [])) (m[f.metric_name] ??= []).push(f);
    return m;
  }, [forecasts]);

  useEffect(() => {
    if (!pickedMetric && Object.keys(byMetric).length) {
      setPickedMetric(Object.keys(byMetric)[0]);
    }
  }, [byMetric, pickedMetric]);

  const ebitdaVar = variances?.find(v => v.metric_name === 'ebitda');
  const revenueVar = variances?.find(v => v.metric_name === 'revenue');
  const refreshAll = () => { fcRefresh(); vrRefresh(); cmRefresh(); };
  const loading = fcLoading || vrLoading || cmLoading;

  return (
    <div className="space-y-5 animate-fade-up">
      {/* ── Filter bar ── */}
      <div className="card flex flex-wrap items-end gap-4">
        <div className="flex-1 min-w-48">
          <label className="label">Company ID</label>
          <input
            value={companyId}
            onChange={e => { setLocalCid(e.target.value); }}
            onBlur={e => { setCompanyId(e.target.value); }}
            className="input font-mono"
            placeholder="UUID"
          />
        </div>
        <div>
          <label className="label">Period</label>
          <input type="date" value={period} onChange={e => savePeriod(e.target.value)} className="input" />
        </div>
        <button onClick={refreshAll} disabled={loading} className="btn-primary">
          {loading
            ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            : '↻'} Refresh
        </button>
        {workflowId && (
          <span className="ml-auto text-xs text-slate-500">
            Workflow: <code className="text-indigo-400">{workflowId}</code>
          </span>
        )}
      </div>

      <ErrorBanner error={fcError || vrError} onRetry={refreshAll} />

      {/* ── KPI stats ── */}
      {variances?.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Revenue"
            value={revenueVar ? fmt(revenueVar.actual_amount) : '—'}
            sub={revenueVar ? `Budget: ${fmt(revenueVar.budget_amount)}` : undefined}
            accent={revenueVar?.is_favorable ? 'emerald' : 'red'}
            trend={revenueVar?.variance_pct}
          />
          <StatCard
            label="EBITDA"
            value={ebitdaVar ? fmt(ebitdaVar.actual_amount) : '—'}
            sub={ebitdaVar ? `Variance: ${pct(ebitdaVar.variance_pct)}` : undefined}
            accent={ebitdaVar?.is_favorable ? 'emerald' : 'amber'}
          />
          <StatCard
            label="Material Variances"
            value={variances.filter(v => ['MATERIAL','CRITICAL'].includes(v.materiality)).length}
            sub="Require HITL review"
            accent="amber"
          />
          <StatCard
            label="Forecast Models"
            value={Object.keys(byMetric).length}
            sub="Metrics forecasted"
            accent="indigo"
          />
        </div>
      )}

      {/* ── Charts ── */}
      <div className="grid lg:grid-cols-2 gap-5">
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-slate-200">Forecast · 6 Months</h3>
            <select
              value={pickedMetric || ''}
              onChange={e => setPickedMetric(e.target.value)}
              className="input text-xs py-1 w-36"
            >
              {Object.keys(byMetric).map(m => <option key={m}>{m}</option>)}
            </select>
          </div>
          {fcLoading
            ? <Spinner label="Loading forecasts…" />
            : <ForecastChart points={byMetric[pickedMetric] || []} />
          }
        </div>

        <div className="card">
          <h3 className="font-semibold text-slate-200 mb-4">EBITDA Waterfall</h3>
          {vrLoading
            ? <Spinner label="Loading variances…" />
            : <WaterfallChart variances={variances || []} />
          }
        </div>
      </div>

      {/* ── Variance table + Commentary + Live events ── */}
      <div className="grid lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 card overflow-x-auto">
          <h3 className="font-semibold text-slate-200 mb-4">
            Variance Records
            <span className="ml-2 text-slate-500 text-sm font-normal">{period}</span>
          </h3>
          {vrLoading ? <Spinner label="Loading…" /> : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th className="text-right">Actual</th>
                  <th className="text-right">Budget</th>
                  <th className="text-right">Δ %</th>
                  <th>Materiality</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {(variances || []).map((v, i) => (
                  <tr key={i}>
                    <td className="font-mono">{v.metric_name}</td>
                    <td className="text-right font-mono">{fmt(v.actual_amount)}</td>
                    <td className="text-right font-mono text-slate-500">{fmt(v.budget_amount)}</td>
                    <td className={`text-right font-semibold ${v.is_favorable ? 'text-emerald-400' : 'text-red-400'}`}>
                      {v.is_favorable ? '+' : ''}{pct(v.variance_pct)}
                    </td>
                    <td>
                      <span className={`tag ${
                        v.materiality === 'CRITICAL'    ? 'tag-crit'   :
                        v.materiality === 'MATERIAL'    ? 'tag-risk'   :
                        v.materiality === 'NOTABLE'     ? 'tag-ok'     : 'tag-strong'
                      }`}>{v.materiality}</span>
                    </td>
                    <td>{v.is_favorable ? '✓' : '✗'}</td>
                  </tr>
                ))}
                {!(variances?.length) && (
                  <tr><td colSpan={6} className="text-center py-6 text-slate-500">No variances for this period.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        <div className="space-y-4">
          <CommentaryCard commentary={commentary} />
          <div className="card">
            <h3 className="font-semibold text-slate-200 mb-3">Live Events</h3>
            {!workflowId
              ? <p className="text-xs text-slate-500">Add <code>?workflow=ID</code> to URL to subscribe.</p>
              : wsEvents.length === 0
                ? <p className="text-xs text-slate-500">Waiting for events…</p>
                : (
                  <ul className="space-y-1 max-h-52 overflow-y-auto">
                    {wsEvents.map((ev, i) => (
                      <li key={i} className="text-xs font-mono text-slate-400 truncate">
                        <span className="text-slate-600">{ev._ts}</span>{' '}
                        <span className="text-indigo-400">{ev.event}</span>
                        {ev.agent_name && ` · ${ev.agent_name}`}
                      </li>
                    ))}
                  </ul>
                )
            }
          </div>
        </div>
      </div>
    </div>
  );
}
