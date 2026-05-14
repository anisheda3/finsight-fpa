export default function AgentActivityFeed({ events }) {
  if (!events.length) {
    return <div className="card text-sm text-slate-500">Listening… no events yet.</div>;
  }
  return (
    <div className="card overflow-x-auto">
      <table className="min-w-full text-xs font-mono">
        <thead className="text-left text-slate-500 border-b">
          <tr>
            <th className="py-2 pr-3">Time</th>
            <th className="py-2 pr-3">Event</th>
            <th className="py-2 pr-3">Agent</th>
            <th className="py-2 pr-3">Tool</th>
            <th className="py-2 pr-3">Detail</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={i} className="border-b align-top">
              <td className="py-1 pr-3 text-slate-500">{e._ts || ''}</td>
              <td className="py-1 pr-3">
                <span className={
                  e.event === 'tool_exec'      ? 'text-sky-700' :
                  e.event === 'session_start'  ? 'text-emerald-700' :
                  e.event === 'guardrail_fail' ? 'text-red-700'  : 'text-slate-700'
                }>{e.event || '—'}</span>
              </td>
              <td className="py-1 pr-3">{e.agent_name || '—'}</td>
              <td className="py-1 pr-3">{e.tool_name || '—'}</td>
              <td className="py-1 pr-3 max-w-md truncate">
                {e.result_summary || e.error || (e.period ? `period=${e.period}` : '')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
