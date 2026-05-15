import {
  Area, ComposedChart, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid,
} from 'recharts';

const fmt = v => `₹${(v / 1e6).toFixed(2)}M`;

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 text-xs shadow-xl">
      <p className="text-slate-400 mb-2 font-medium">{label}</p>
      {payload.map(p => (
        <p key={p.dataKey} style={{ color: p.color }} className="flex justify-between gap-4">
          <span>{p.name}</span>
          <span className="font-mono">{fmt(p.value)}</span>
        </p>
      ))}
    </div>
  );
};

export default function ForecastChart({ points }) {
  if (!points?.length) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
        No forecast data available.
      </div>
    );
  }

  const data = points
    .map(p => ({
      period:  (typeof p.forecast_period === 'string' ? p.forecast_period : String(p.forecast_period || p.period || '')).slice(0, 10),
      point:   Number(p.point_forecast),
      lo80:    Number(p.lower_bound_80),
      hi80:    Number(p.upper_bound_80),
      lo95:    Number(p.lower_bound_95),
      hi95:    Number(p.upper_bound_95),
      band95:  Number(p.upper_bound_95) - Number(p.lower_bound_95),
      band80:  Number(p.upper_bound_80) - Number(p.lower_bound_80),
    }))
    .sort((a, b) => a.period.localeCompare(b.period));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="ci95" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="ci80" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#8b5cf6" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="period" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: '#64748b' }} tickFormatter={fmt} axisLine={false} tickLine={false} width={65} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
        <Area type="monotone" dataKey="hi95" stackId="95" stroke="none" fill="url(#ci95)" name="95% CI" legendType="none" />
        <Area type="monotone" dataKey="lo95" stackId="95" stroke="none" fill="#0f172a"    name="95% CI lower" legendType="none" />
        <Area type="monotone" dataKey="hi80" stackId="80" stroke="none" fill="url(#ci80)" name="80% CI" />
        <Area type="monotone" dataKey="lo80" stackId="80" stroke="none" fill="#0f172a"    name="80% CI lower" legendType="none" />
        <Line
          type="monotone" dataKey="point" stroke="#818cf8" strokeWidth={2.5}
          dot={{ r: 3, fill: '#818cf8', strokeWidth: 0 }}
          activeDot={{ r: 5, fill: '#c4b5fd' }}
          name="Point forecast"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
