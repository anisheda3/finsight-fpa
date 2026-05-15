import { useCallback } from 'react';
import { api } from '../api/client';
import { usePersistedData } from '../hooks/usePersistedData';
import Spinner from './Spinner';

export default function HITLPanel({ companyId }) {
  const fetchFn = useCallback(
    () => api.hitlPending(companyId),
    [companyId]
  );
  const { data: pending, loading, error, refresh } = usePersistedData(
    `hitl-pending-${companyId}`,
    fetchFn,
    { ttlMs: 30_000 }
  );

  if (loading) return <Spinner label="Loading pending flags…" />;

  const items = pending || [];

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-slate-200">Pending HITL Flags</h3>
        <div className="flex items-center gap-2">
          {items.length > 0 && (
            <span className="tag tag-risk">{items.length} pending</span>
          )}
          <button onClick={refresh} className="btn-ghost text-xs py-1 px-2">↻ Refresh</button>
        </div>
      </div>

      {error && <p className="text-xs text-red-400 mb-3">Error: {error}</p>}

      {items.length === 0 ? (
        <div className="text-center py-6">
          <span className="text-2xl">✓</span>
          <p className="text-sm text-slate-500 mt-2">No pending flags</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="data-table text-xs">
            <thead>
              <tr>
                <th>Flag ID</th>
                <th>Type</th>
                <th>Metric</th>
                <th>Severity</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p, i) => (
                <tr key={i}>
                  <td className="font-mono text-slate-400">{p.flag_id}</td>
                  <td><span className="tag tag-risk">{p.flag_type}</span></td>
                  <td className="text-slate-300">{p.metric_name || '—'}</td>
                  <td>
                    {p.severity && (
                      <span className={`tag ${p.severity === 'CRITICAL' ? 'tag-crit' : 'tag-risk'}`}>
                        {p.severity}
                      </span>
                    )}
                  </td>
                  <td className="text-slate-500">{p.created_at?.slice(0, 16) || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
