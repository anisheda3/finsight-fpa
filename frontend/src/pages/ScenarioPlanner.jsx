import { useEffect, useState } from 'react';
import { api } from '../api/client';
import ScenarioComparison from '../components/ScenarioComparison';

const PRESETS = {
  BASE: { revenue_growth_qoq: 0.04, cogs_ratio: 0.40, rd_ratio: 0.10, sm_ratio: 0.13, ga_ratio: 0.06, macro_adjustment_pct: 0.0 },
  BULL: { revenue_growth_qoq: 0.08, cogs_ratio: 0.38, rd_ratio: 0.09, sm_ratio: 0.12, ga_ratio: 0.05, macro_adjustment_pct: 0.02 },
  BEAR: { revenue_growth_qoq: -0.02, cogs_ratio: 0.45, rd_ratio: 0.11, sm_ratio: 0.14, ga_ratio: 0.07, macro_adjustment_pct: -0.03 },
};

function Slider({ label, value, onChange, min, max, step = 0.01 }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-600">
        <span>{label}</span><span className="font-mono">{(value * 100).toFixed(1)}%</span>
      </div>
      <input type="range" min={min} max={max} step={step}
             value={value} onChange={e => onChange(parseFloat(e.target.value))}
             className="w-full" />
    </div>
  );
}

function AssumptionEditor({ stype, assumptions, setAssumptions }) {
  const a = assumptions[stype];
  const set = (k, v) => setAssumptions({ ...assumptions, [stype]: { ...a, [k]: v } });
  return (
    <div className="space-y-2">
      <h4 className="font-semibold">{stype}</h4>
      <Slider label="Revenue growth (QoQ)"  value={a.revenue_growth_qoq} onChange={v => set('revenue_growth_qoq', v)} min={-0.10} max={0.20} />
      <Slider label="COGS %"                value={a.cogs_ratio}         onChange={v => set('cogs_ratio', v)}         min={0.20}  max={0.70} />
      <Slider label="R&D %"                 value={a.rd_ratio}           onChange={v => set('rd_ratio', v)}           min={0.0}   max={0.30} />
      <Slider label="S&M %"                 value={a.sm_ratio}           onChange={v => set('sm_ratio', v)}           min={0.0}   max={0.30} />
      <Slider label="G&A %"                 value={a.ga_ratio}           onChange={v => set('ga_ratio', v)}           min={0.0}   max={0.20} />
      <Slider label="Macro adjustment"      value={a.macro_adjustment_pct} onChange={v => set('macro_adjustment_pct', v)} min={-0.10} max={0.10} />
    </div>
  );
}

export default function ScenarioPlanner() {
  const [companyId, setCompanyId] = useState(localStorage.getItem('companyId') || '');
  const [anchorRevenue, setAnchorRevenue] = useState(8500000);
  const [assumptions, setAssumptions] = useState(PRESETS);
  const [scenarios, setScenarios] = useState([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);

  async function loadScenarios() {
    if (!companyId) return;
    try { setScenarios(await api.scenarios(companyId)); } catch (e) { console.warn(e); }
  }
  useEffect(() => { loadScenarios(); /* eslint-disable-next-line */ }, [companyId]);

  async function runScenarios() {
    setBusy(true);
    setStatus(null);
    try {
      const res = await api.runScenarios({
        company_id: companyId,
        anchor_quarter_revenue: anchorRevenue,
        assumptions,
        n_quarters: 4,
      });
      setStatus(res);
      // Allow worker time to write rows, then refresh
      setTimeout(loadScenarios, 4000);
    } catch (err) {
      setStatus({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600">Company ID</label>
          <input value={companyId} onChange={e => setCompanyId(e.target.value)}
                 className="mt-1 border border-slate-300 rounded px-2 py-1 text-sm font-mono w-72" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600">Anchor quarterly revenue (₹)</label>
          <input type="number" value={anchorRevenue}
                 onChange={e => setAnchorRevenue(Number(e.target.value))}
                 className="mt-1 border border-slate-300 rounded px-2 py-1 text-sm w-48" />
        </div>
        <button onClick={runScenarios} disabled={busy} className="btn-primary disabled:opacity-50">
          {busy ? 'Starting saga…' : 'Run BASE / BULL / BEAR'}
        </button>
        {status && <span className="text-xs text-slate-500 ml-2">workflow_id: <code>{status.workflow_id || '—'}</code></span>}
      </div>

      <div className="card grid md:grid-cols-3 gap-6">
        {['BASE', 'BULL', 'BEAR'].map(s =>
          <AssumptionEditor key={s} stype={s} assumptions={assumptions} setAssumptions={setAssumptions} />
        )}
      </div>

      <div className="card">
        <h3 className="font-semibold mb-3">Scenario comparison (latest persisted)</h3>
        <ScenarioComparison scenarios={scenarios} />
      </div>
    </div>
  );
}
