import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts';

const SIGN = { revenue: +1, cogs: -1, gross_profit: +1, rd: -1, sm: -1, ga: -1 };

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 text-xs shadow-xl">
      <p className="text-slate-400">{payload[0].payload.metric}</p>
      <p className={`font-mono font-bold ${v >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
        {v >= 0 ? '+' : ''}₹{Math.abs(v).toLocaleString()}
      </p>
    </div>
  );
};

export default function WaterfallChart({ variances }) {
  if (!variances?.length) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
        No variance data available.
      </div>
    );
  }

  const items = variances
    .filter(v => v.metric_name in SIGN)
    .map(v => ({
      metric:       v.metric_name,
      contribution: SIGN[v.metric_name] * Number(v.variance_amount || 0),
    }))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 6);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={items} layout="vertical" margin={{ left: 10, right: 10, top: 4, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
        <XAxis type="number" tickFormatter={v => `₹${(v / 1e6).toFixed(1)}M`} tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <YAxis dataKey="metric" type="category" tick={{ fontSize: 11, fill: '#94a3b8' }} width={80} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: '#1e293b' }} />
        <Bar dataKey="contribution" radius={[0, 4, 4, 0]}>
          {items.map((it, i) => (
            <Cell key={i} fill={it.contribution >= 0 ? '#10b981' : '#f43f5e'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
