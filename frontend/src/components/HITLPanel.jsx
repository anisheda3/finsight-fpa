import { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function HITLPanel() {
  const [pending, setPending] = useState([]);

  useEffect(() => {
    api.hitlPending().then(setPending).catch(() => setPending([]));
  }, []);

  return (
    <div className="card">
      <h3 className="font-semibold mb-2">Pending HITL flags</h3>
      {pending.length === 0
        ? <p className="text-sm text-slate-500">No pending flags.</p>
        : (
          <table className="min-w-full text-sm">
            <thead className="text-left text-slate-500 border-b">
              <tr>
                <th className="py-2">Flag</th><th>Type</th><th>Workflow</th><th>Created</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((p, i) => (
                <tr key={i} className="border-b">
                  <td className="py-2 font-mono">{p.flag_id}</td>
                  <td>{p.flag_type}</td>
                  <td className="font-mono">{p.temporal_workflow_id}</td>
                  <td>{p.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      }
    </div>
  );
}
