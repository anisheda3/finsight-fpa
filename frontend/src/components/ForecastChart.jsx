import { Area, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export default function ForecastChart({ points }) {
  if (!points || points.length === 0) {
    return <div className="text-sm text-slate-500 h-64 grid place-items-center">No forecast data.</div>;
  }
  const data = points
    .map(p => ({
      period: typeof p.forecast_period === 'string' ? p.forecast_period.slice(0, 10) : p.forecast_period,
      point: Number(p.point_forecast),
      lo80: Number(p.lower_bound_80),
      hi80: Number(p.upper_bound_80),
      lo95: Number(p.lower_bound_95),
      hi95: Number(p.upper_bound_95),
      band95: Number(p.upper_bound_95) - Number(p.lower_bound_95),
      band80: Number(p.upper_bound_80) - Number(p.lower_bound_80),
    }))
    .sort((a, b) => a.period.localeCompare(b.period));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data}>
        <XAxis dataKey="period" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `₹${(v / 1e6).toFixed(1)}M`} />
        <Tooltip formatter={v => `₹${Number(v).toLocaleString()}`} />
        <Legend />
        <Area type="monotone" dataKey="hi95" stackId="95" stroke="none" fill="#bfdbfe" name="95% CI" />
        <Area type="monotone" dataKey="lo95" stackId="95" stroke="none" fill="#ffffff" />
        <Area type="monotone" dataKey="hi80" stackId="80" stroke="none" fill="#60a5fa" name="80% CI" />
        <Area type="monotone" dataKey="lo80" stackId="80" stroke="none" fill="#ffffff" />
        <Line type="monotone" dataKey="point" stroke="#1d4ed8" strokeWidth={2.5} dot name="Point forecast" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
