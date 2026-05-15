export default function StatCard({ label, value, sub, accent = 'indigo', trend }) {
  const accents = {
    indigo:  'from-indigo-500/20 to-violet-500/10 border-indigo-500/20',
    emerald: 'from-emerald-500/20 to-teal-500/10 border-emerald-500/20',
    amber:   'from-amber-500/20 to-orange-500/10 border-amber-500/20',
    red:     'from-red-500/20 to-rose-500/10 border-red-500/20',
  };
  return (
    <div className={`card bg-gradient-to-br ${accents[accent] || accents.indigo}`}>
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value ?? '—'}</p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
      {trend != null && (
        <p className={`text-xs font-medium mt-1 ${trend >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          {trend >= 0 ? '▲' : '▼'} {Math.abs(trend).toFixed(1)}%
        </p>
      )}
    </div>
  );
}
