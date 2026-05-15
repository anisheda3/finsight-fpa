import { useEffect, useRef, useState } from 'react';
import { openWorkflowSocket } from '../api/client';
import AgentActivityFeed from '../components/AgentActivityFeed';

export default function ActivityLog() {
  const [workflowId, setWorkflowId] = useState('all');
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    if (wsRef.current) wsRef.current.close();
    setConnected(false);
    const ws = openWorkflowSocket(workflowId, ev => {
      if (ev.event === 'subscribed') { setConnected(true); return; }
      setEvents(prev => [{ ...ev, _ts: new Date().toLocaleTimeString() }, ...prev].slice(0, 300));
    });
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    wsRef.current = ws;
    return () => ws.close();
  }, [workflowId]);

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="card flex items-end gap-4">
        <div className="flex-1">
          <label className="label">Subscribe to Workflow</label>
          <input
            value={workflowId}
            onChange={e => setWorkflowId(e.target.value)}
            placeholder="workflow_id or 'all'"
            className="input font-mono"
          />
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs">
            <span className={`dot ${connected ? 'dot-green' : 'dot-amber'}`} />
            <span className={connected ? 'text-emerald-400' : 'text-amber-400'}>
              {connected ? 'Live' : 'Connecting…'}
            </span>
          </div>
          <button onClick={() => setEvents([])} className="btn-ghost text-xs py-1.5">Clear</button>
          <span className="text-xs text-slate-500">{events.length} events</span>
        </div>
      </div>

      <AgentActivityFeed events={events} />
    </div>
  );
}
