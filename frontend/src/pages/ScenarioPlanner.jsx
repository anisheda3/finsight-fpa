import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { getCompanyId } from '../store';
import { usePersistedData } from '../hooks/usePersistedData';
import ScenarioComparison from '../components/ScenarioComparison';
import Spinner from '../components/Spinner';

const PRESETS = {
  BASE: { revenue_growth_qoq: 0.04, cogs_ratio: 0.40, rd_ratio: 0.10, sm_ratio: 0.13, ga_ratio: 0.06, macro_adjustment_pct: 0.0 },
  BULL: { revenue_growth_qoq: 0.08, cogs_ratio: 0.38, rd_ratio: 0.09, sm_ratio: 0.12, ga_ratio: 0.05, macro_adjustment_pct: 0.02 },
  BEAR: { revenue_growth_qoq: -0.02, cogs_ratio: 0.45, rd_ratio: 0.11, sm_ratio: 0.14, ga_ratio: 0.07, macro_adjustment_pct: -0.03 },
};

const SCENARIO_ACCENT = { BASE: 'indigo', BULL: 'emerald', BEAR: 'red' };
const SCENARIO_LABEL = { BASE: '📊 Base Case', BULL: '🚀 Bull Case', BEAR: '🐻 Bear Case' };

function Slider({ label, value, onChange, min, max, step = 0.01 }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="font-mono text-slate-300">{(value * 100).toFixed(1)}%</span>
      </div>
      <input
        type="range" min={min} max={max} step={step}
        value={value} onChange={e => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 appearance-none rounded-full bg-slate-700
                   [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5
                   [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full
                   [&::-webkit-slider-thumb]:bg-indigo-400 [&::-webkit-slider-thumb]:cursor-pointer"
      />
    </div>
  );
}

function AssumptionEditor({ stype, assumptions, setAssumptions }) {
  const a = assumptions[stype];
  const set = (k, v) => setAssumptions({ ...assumptions, [stype]: { ...a, [k]: v } });

  const accents = { BASE: 'border-indigo-500/30', BULL: 'border-emerald-500/30', BEAR: 'border-red-500/30' };

  return (
    <div className={`card border ${accents[stype]} space-y-3`}>
      <h4 className="font-semibold text-slate-200">{SCENARIO_LABEL[stype]}</h4>
      <Slider label="Revenue Growth (QoQ)" value={a.revenue_growth_qoq} onChange={v => set('revenue_growth_qoq', v)} min={-0.10} max={0.20} />
      <Slider label="COGS %" value={a.cogs_ratio} onChange={v => set('cogs_ratio', v)} min={0.20} max={0.70} />
      <Slider label="R&D %" value={a.rd_ratio} onChange={v => set('rd_ratio', v)} min={0.0} max={0.30} />
      <Slider label="S&M %" value={a.sm_ratio} onChange={v => set('sm_ratio', v)} min={0.0} max={0.30} />
      <Slider label="G&A %" value={a.ga_ratio} onChange={v => set('ga_ratio', v)} min={0.0} max={0.20} />
      <Slider label="Macro Adj" value={a.macro_adjustment_pct} onChange={v => set('macro_adjustment_pct', v)} min={-0.10} max={0.10} />
    </div>
  );
}

export default function ScenarioPlanner() {
  const [companyId] = useState(getCompanyId);
  const [anchor, setAnchor] = useState(8_500_000);
  const [assumptions, setAssumptions] = useState(PRESETS);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);

  const fetchScenarios = useCallback(
    () => companyId ? api.scenarios(companyId) : Promise.resolve([]),
    [companyId]
  );
  const { data: scenarios, loading, refresh } = usePersistedData(
    `scenarios-${companyId}`, fetchScenarios, { ttlMs: 120_000 }
  );

  async function runScenarios() {
    setBusy(true); setStatus(null);
    try {
      const res = await api.runScenarios({
        company_id: companyId,
        anchor_quarter_revenue: anchor,
        assumptions,
        n_quarters: 4,
      });
      setStatus(res);
      setTimeout(refresh, 4000);
    } catch (err) {
      setStatus({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Controls */}
      <div className="card flex flex-wrap items-end gap-4">
        <div className="flex-1 min-w-48">
          <label className="label">Company ID</label>
          <input value={companyId} readOnly className="input font-mono opacity-60" />
        </div>
        <div>
          <label className="label">Anchor Revenue (₹)</label>
          <input
            type="number" value={anchor}
            onChange={e => setAnchor(Number(e.target.value))}
            className="input w-40"
          />
        </div>
        <button onClick={runScenarios} disabled={busy || !companyId} className="btn-primary">
          {busy ? (
            <>
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Running scenarios…
            </>
          ) : '▶ Run BASE / BULL / BEAR'}
        </button>
        {status && !status.error && (
          <span className="text-xs text-emerald-400">
            ✓ Saga started · <code>{status.workflow_id}</code>
          </span>
        )}
        {status?.error && (
          <span className="text-xs text-red-400">Error: {status.error}</span>
        )}
      </div>

      {/* Assumption editors */}
      <div className="grid md:grid-cols-3 gap-4">
        {['BASE', 'BULL', 'BEAR'].map(s => (
          <AssumptionEditor key={s} stype={s} assumptions={assumptions} setAssumptions={setAssumptions} />
        ))}
      </div>

      {/* Comparison */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-slate-200">Scenario Comparison</h3>
          <button onClick={refresh} className="btn-ghost text-xs py-1 px-2">↻ Refresh</button>
        </div>
        {loading
          ? <Spinner label="Loading scenarios…" />
          : <ScenarioComparison scenarios={scenarios || []} />
        }
      </div>
    </div>
  );
}

