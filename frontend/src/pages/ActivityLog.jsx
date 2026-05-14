import { useEffect, useState } from 'react';
import { openWorkflowSocket } from '../api/client';
import AgentActivityFeed from '../components/AgentActivityFeed';

export default function ActivityLog() {
  const [workflowId, setWorkflowId] = useState('all');
  const [events, setEvents] = useState([]);

  useEffect(() => {
    const ws = openWorkflowSocket(workflowId, ev => {
      setEvents(prev => [{ ...ev, _ts: new Date().toLocaleTimeString() }, ...prev].slice(0, 200));
    });
    return () => ws.close();
  }, [workflowId]);

  return (
    <div className="space-y-4">
      <div className="card flex items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600">Subscribe to workflow</label>
          <input value={workflowId} onChange={e => setWorkflowId(e.target.value)}
                 placeholder="workflow_id or 'all'"
                 className="mt-1 border border-slate-300 rounded px-2 py-1 text-sm font-mono w-96" />
        </div>
        <button onClick={() => setEvents([])} className="btn-ghost">Clear</button>
        <span className="text-xs text-slate-500 ml-auto">{events.length} events</span>
      </div>
      <AgentActivityFeed events={events} />
    </div>
  );
}
