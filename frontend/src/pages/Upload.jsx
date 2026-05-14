import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';

export default function Upload() {
  const [companyId, setCompanyId] = useState(localStorage.getItem('companyId') || '');
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState(null);
  const navigate = useNavigate();

  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)); }, []);

  async function onSubmit(e) {
    e.preventDefault();
    if (!companyId || !file) return;
    setBusy(true);
    setStatus(null);
    try {
      localStorage.setItem('companyId', companyId);
      const res = await api.uploadActuals(companyId, file);
      setStatus(res);
      if (res.workflow_id) {
        setTimeout(() => navigate(`/dashboard?workflow=${res.workflow_id}`), 1500);
      }
    } catch (err) {
      setStatus({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="card">
        <h2 className="text-lg font-semibold mb-2">Upload monthly actuals</h2>
        <p className="text-sm text-slate-500 mb-4">
          CSV with columns: <code>period, department, metric_name, amount</code>.
          A Temporal MonthEndAnalysisSaga is started on submit.
        </p>
        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-slate-700">Company ID (UUID)</label>
            <input
              value={companyId}
              onChange={e => setCompanyId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="mt-1 w-full border border-slate-300 rounded-md px-3 py-2 text-sm font-mono"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Actuals CSV</label>
            <input
              type="file" accept=".csv,.json"
              onChange={e => setFile(e.target.files?.[0] || null)}
              className="mt-1 block w-full text-sm"
            />
          </div>
          <button disabled={busy || !companyId || !file} className="btn-primary disabled:opacity-50">
            {busy ? 'Uploading…' : 'Upload & start workflow'}
          </button>
        </form>

        {status && (
          <pre className="mt-4 p-3 bg-slate-100 rounded text-xs overflow-auto">
            {JSON.stringify(status, null, 2)}
          </pre>
        )}
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold mb-2">System health</h2>
        {health ? (
          <ul className="text-sm space-y-1">
            <li>API status: <span className="font-mono">{health.status}</span></li>
            <li>Environment: <span className="font-mono">{health.env}</span></li>
            <li>Database: {health.db
              ? <span className="text-emerald-700 font-mono">connected</span>
              : <span className="text-red-700 font-mono">unreachable</span>}</li>
            <li>Temporal: <span className="font-mono">{health.temporal}</span></li>
            <li>Redis: <span className="font-mono">{health.redis}</span></li>
          </ul>
        ) : <p className="text-sm text-red-700">API not reachable on /api/v1/health</p>}

        <hr className="my-4" />
        <h3 className="text-md font-semibold mb-2">Sample data</h3>
        <p className="text-sm text-slate-600">
          Use <code>sample_data/FTPL-001_Q3_2024_Actuals.csv</code> from the repo for a quick demo.
          Get a real <code>company_id</code> from a fresh seed run:
        </p>
        <pre className="text-xs bg-slate-100 p-2 rounded mt-2 overflow-auto">
{`psql "$POSTGRES_URL" -c "SELECT id, erp_code FROM companies;"`}
        </pre>
      </div>
    </div>
  );
}
