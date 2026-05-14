import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

// EBITDA contribution sign: revenue+, cost-lines invert.
const SIGN = { revenue: +1, cogs: -1, rd: -1, sm: -1, ga: -1 };

export default function WaterfallChart({ variances }) {
  if (!variances || !variances.length) {
    return <div className="text-sm text-slate-500 h-64 grid place-items-center">No variance data.</div>;
  }
  const items = variances
    .filter(v => v.metric_name in SIGN)
    .map(v => ({
      metric: v.metric_name,
      contribution: SIGN[v.metric_name] * Number(v.variance_amount || 0),
    }))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 6);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={items} layout="vertical" margin={{ left: 30 }}>
        <XAxis type="number" tickFormatter={v => `₹${(v / 1e6).toFixed(1)}M`} tick={{ fontSize: 11 }} />
        <YAxis dataKey="metric" type="category" tick={{ fontSize: 11 }} width={90} />
        <Tooltip formatter={v => `₹${Number(v).toLocaleString()}`} />
        <Bar dataKey="contribution">
          {items.map((it, i) => (
            <Cell key={i} fill={it.contribution >= 0 ? '#10b981' : '#ef4444'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
