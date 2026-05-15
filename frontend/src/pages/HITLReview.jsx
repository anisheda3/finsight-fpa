import { useState } from 'react';
import { api } from '../api/client';
import { getCompanyId } from '../store';
import HITLPanel from '../components/HITLPanel';

export default function HITLReview() {
  const companyId = getCompanyId();
  const [workflowId, setWorkflowId] = useState('');
  const [flagId, setFlagId] = useState('');
  const [decision, setDecision] = useState('APPROVED');
  const [reviewer, setReviewer] = useState('reviewer@example.com');
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  async function send(method) {
    setBusy(true); setStatus(null);
    const body = { workflow_id: workflowId, flag_id: flagId, decision, reviewer_id: reviewer, notes };
    try {
      const res = method === 'override'
        ? await api.hitlOverride(flagId, body)
        : await api.hitlRespond(body);
      setStatus(res);
    } catch (err) {
      setStatus({ error: String(err) });
    } finally {
      setBusy(false);
    }
  }

  const DECISIONS = ['APPROVED', 'REJECTED', 'ADJUSTED', 'REQUESTED_INFO'];

  return (
    <div className="space-y-5 animate-fade-up">
      <div className="card">
        <div className="mb-5">
          <h2 className="text-lg font-bold text-slate-100">Human-in-the-Loop Review</h2>
          <p className="text-sm text-slate-400 mt-1">
            MATERIAL/CRITICAL variances and HIGH/CRITICAL anomalies are sent to{' '}
            <code className="text-indigo-400">#fpa-hitl</code>. Respond here or via Slack.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="label">Workflow ID</label>
            <input value={workflowId} onChange={e => setWorkflowId(e.target.value)} className="input font-mono" />
          </div>
          <div>
            <label className="label">Flag ID</label>
            <input
              value={flagId} onChange={e => setFlagId(e.target.value)}
              placeholder="variance:rd:2024-09-01"
              className="input font-mono"
            />
          </div>
          <div>
            <label className="label">Decision</label>
            <select value={decision} onChange={e => setDecision(e.target.value)} className="input">
              {DECISIONS.map(d => <option key={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Reviewer ID</label>
            <input value={reviewer} onChange={e => setReviewer(e.target.value)} className="input" />
          </div>
          <div className="md:col-span-2">
            <label className="label">Notes</label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} className="input resize-none" />
          </div>
        </div>

        <div className="flex gap-3 mt-5">
          <button
            onClick={() => send('respond')} disabled={busy || !workflowId || !flagId}
            className="btn-primary"
          >
            {busy ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : null}
            Signal Workflow
          </button>
          <button
            onClick={() => send('override')} disabled={busy || !workflowId || !flagId}
            className="btn-danger"
          >
            Manual Override
          </button>
        </div>

        {status && (
          <div className={`mt-4 rounded-lg p-3 text-xs font-mono ${
            status.error
              ? 'bg-red-500/10 text-red-400 border border-red-500/20'
              : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
          }`}>
            {status.error ? `Error: ${status.error}` : `✓ ${JSON.stringify(status)}`}
          </div>
        )}
      </div>

      <HITLPanel companyId={companyId} />
    </div>
  );
}
