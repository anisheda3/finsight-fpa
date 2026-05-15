const EVENT_STYLES = {
  tool_exec:      'text-sky-400',
  session_start:  'text-emerald-400',
  guardrail_fail: 'text-red-400',
  heartbeat:      'text-slate-600',
};

export default function AgentActivityFeed({ events }) {
  if (!events.length) {
    return (
      <div className="card text-center py-10">
        <div className="text-3xl mb-2">📡</div>
        <p className="text-sm text-slate-500">Listening for workflow events…</p>
        <p className="text-xs text-slate-600 mt-1">Events will appear here in real-time</p>
      </div>
    );
  }

  return (
    <div className="card overflow-x-auto">
      <table className="data-table font-mono text-xs">
        <thead>
          <tr>
            <th>Time</th>
            <th>Event</th>
            <th>Agent</th>
            <th>Tool</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={i}>
              <td className="text-slate-500 whitespace-nowrap">{e._ts || ''}</td>
              <td>
                <span className={EVENT_STYLES[e.event] || 'text-slate-400'}>
                  {e.event || '—'}
                </span>
              </td>
              <td className="text-slate-300">{e.agent_name || '—'}</td>
              <td className="text-slate-400">{e.tool_name  || '—'}</td>
              <td className="max-w-xs truncate text-slate-500">
                {e.result_summary || e.error || (e.period ? `period=${e.period}` : '')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
