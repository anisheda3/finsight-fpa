import { useState } from 'react';
import { api } from '../api/client';
import HITLPanel from '../components/HITLPanel';

export default function HITLReview() {
  const [workflowId, setWorkflowId] = useState('');
  const [flagId, setFlagId] = useState('');
  const [decision, setDecision] = useState('APPROVED');
  const [reviewer, setReviewer] = useState('reviewer@example.com');
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState(null);

  async function send(method) {
    setStatus(null);
    const body = { workflow_id: workflowId, flag_id: flagId,
                   decision, reviewer_id: reviewer, notes };
    try {
      const res = method === 'override'
        ? await api.hitlOverride(flagId, body)
        : await api.hitlRespond(body);
      setStatus(res);
    } catch (err) {
      setStatus({ error: String(err) });
    }
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <h2 className="text-lg font-semibold mb-2">Human-in-the-loop review</h2>
        <p className="text-sm text-slate-500 mb-4">
          Each MATERIAL/CRITICAL variance or HIGH/CRITICAL anomaly triggers a Slack message
          to <code>#fpa-hitl</code>. The Temporal saga waits on <code>workflow.signal</code> until
          you respond here or via Slack.
        </p>

        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600">Workflow ID</label>
            <input value={workflowId} onChange={e => setWorkflowId(e.target.value)}
                   className="mt-1 w-full border border-slate-300 rounded px-2 py-1 text-sm font-mono" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600">Flag ID</label>
            <input value={flagId} onChange={e => setFlagId(e.target.value)}
                   placeholder="variance:rd:2024-09-01"
                   className="mt-1 w-full border border-slate-300 rounded px-2 py-1 text-sm font-mono" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600">Decision</label>
            <select value={decision} onChange={e => setDecision(e.target.value)}
                    className="mt-1 w-full border border-slate-300 rounded px-2 py-1 text-sm">
              <option>APPROVED</option><option>REJECTED</option><option>ADJUSTED</option><option>REQUESTED_INFO</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600">Reviewer ID</label>
            <input value={reviewer} onChange={e => setReviewer(e.target.value)}
                   className="mt-1 w-full border border-slate-300 rounded px-2 py-1 text-sm" />
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-slate-600">Notes</label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
                      className="mt-1 w-full border border-slate-300 rounded px-2 py-1 text-sm" />
          </div>
        </div>

        <div className="mt-3 flex gap-2">
          <button onClick={() => send('respond')}  className="btn-primary"
                  disabled={!workflowId || !flagId}>Respond (signal)</button>
          <button onClick={() => send('override')} className="btn-danger"
                  disabled={!workflowId || !flagId}>Manual override</button>
        </div>
        {status && (
          <pre className="mt-3 p-3 bg-slate-100 rounded text-xs overflow-auto">
            {JSON.stringify(status, null, 2)}
          </pre>
        )}
      </div>

      <HITLPanel />
    </div>
  );
}
