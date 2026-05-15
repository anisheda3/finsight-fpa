import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { getCompanyId, setCompanyId } from '../store';

export default function Upload() {
  const [companyId, _setCompanyId] = useState(getCompanyId());
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState(null);
  const navigate = useNavigate();

  const updateCompanyId = v => { _setCompanyId(v); setCompanyId(v); };

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    if (!companyId || !file) return;
    setBusy(true);
    setStatus(null);
    try {
      const res = await api.uploadActuals(companyId, file);
      setStatus(res);
      if (res.workflow_id) {
        setTimeout(() => navigate(`/dashboard?workflow=${res.workflow_id}`), 1600);
      }
    } catch (err) {
      setStatus({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  const HealthDot = ({ ok }) => (
    <span className={`dot ${ok ? 'dot-green' : 'dot-red'}`} />
  );

  return (
    <div className="grid lg:grid-cols-2 gap-6 animate-fade-up">
      {/* Upload card */}
      <div className="card space-y-5">
        <div>
          <h2 className="text-lg font-bold text-slate-100">Upload Monthly Actuals</h2>
          <p className="text-sm text-slate-400 mt-1">
            Upload a CSV with columns: <code className="text-indigo-400">period, metric_name, amount</code>.
            A Temporal saga will run automatically.
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="label">Company ID (UUID)</label>
            <input
              value={companyId}
              onChange={e => updateCompanyId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="input font-mono"
            />
          </div>

          <div>
            <label className="label">Actuals File</label>
            <div className={`relative border-2 border-dashed rounded-xl p-6 text-center transition-all cursor-pointer
              ${file ? 'border-indigo-500/60 bg-indigo-500/5' : 'border-slate-700 hover:border-slate-600'}`}>
              <input
                type="file"
                accept=".csv,.json"
                onChange={e => setFile(e.target.files?.[0] || null)}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
              {file ? (
                <div className="text-sm">
                  <span className="text-2xl">📄</span>
                  <p className="text-indigo-400 font-medium mt-1">{file.name}</p>
                  <p className="text-slate-500 text-xs">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
              ) : (
                <div className="text-slate-500 text-sm">
                  <span className="text-3xl">↑</span>
                  <p className="mt-1">Drop your CSV here or click to browse</p>
                </div>
              )}
            </div>
          </div>

          <button
            type="submit"
            disabled={busy || !companyId || !file}
            className="btn-primary w-full justify-center py-2.5"
          >
            {busy ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Uploading & starting workflow…
              </>
            ) : (
              'Upload & Start Workflow'
            )}
          </button>
        </form>

        {status && (
          <div className={`rounded-lg p-4 text-xs font-mono ${status.error ? 'bg-red-500/10 text-red-400 border border-red-500/20' : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'}`}>
            {status.error
              ? `Error: ${status.error}`
              : (
                <>
                  <p className="font-semibold text-sm mb-1">✓ Workflow started!</p>
                  <p>workflow_id: {status.workflow_id}</p>
                  <p className="text-slate-500 mt-1">Redirecting to dashboard…</p>
                </>
              )
            }
          </div>
        )}
      </div>

      {/* Status / info card */}
      <div className="space-y-4">
        <div className="card">
          <h3 className="font-semibold text-slate-200 mb-4">System Status</h3>
          {health ? (
            <div className="space-y-3">
              {[
                { label: 'API',      ok: health.status === 'ok',   val: health.env },
                { label: 'Database', ok: health.db,                val: health.db ? 'Connected' : 'Unreachable' },
                { label: 'Temporal', ok: !!health.temporal,        val: health.temporal },
                { label: 'Redis',    ok: !!health.redis,           val: health.redis },
              ].map(({ label, ok, val }) => (
                <div key={label} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <HealthDot ok={ok} />
                    <span className="text-slate-400">{label}</span>
                  </div>
                  <span className="font-mono text-xs text-slate-500">{val}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-red-400">⚠ API not reachable at /api/v1/health</p>
          )}
        </div>

        <div className="card">
          <h3 className="font-semibold text-slate-200 mb-3">Quick Start</h3>
          <div className="space-y-2 text-sm text-slate-400">
            <p>1. Get your company UUID:</p>
            <pre className="bg-slate-900 rounded-lg p-2 text-xs text-slate-300 overflow-auto">
{`psql "$POSTGRES_URL" -c \\\n  "SELECT id, erp_code FROM companies;"`}
            </pre>
            <p className="mt-2">2. Upload <code className="text-indigo-400">FTPL-001_Q3_2024_Actuals.csv</code></p>
            <p>3. Watch the pipeline run in Dashboard & Temporal UI</p>
          </div>
        </div>
      </div>
    </div>
  );
}
