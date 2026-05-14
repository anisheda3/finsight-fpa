import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const ORDER = ['BASE', 'BULL', 'BEAR'];
const COLOR = { BASE: '#2563eb', BULL: '#10b981', BEAR: '#ef4444' };

export default function ScenarioComparison({ scenarios }) {
  if (!scenarios || !scenarios.length) {
    return <div className="text-sm text-slate-500">No scenarios persisted yet. Click "Run BASE / BULL / BEAR".</div>;
  }
  // Take latest one of each type
  const latest = {};
  for (const s of scenarios) {
    if (!latest[s.scenario_type] ||
        new Date(s.created_at) > new Date(latest[s.scenario_type].created_at)) {
      latest[s.scenario_type] = s;
    }
  }
  const data = ORDER.filter(t => latest[t]).map(t => ({
    scenario: t,
    Revenue:     Number(latest[t].projected_revenue),
    GrossProfit: Number(latest[t].projected_gross_profit),
    EBITDA:      Number(latest[t].projected_ebitda),
    Margin:      Number(latest[t].projected_revenue) > 0
                  ? (Number(latest[t].projected_ebitda) / Number(latest[t].projected_revenue) * 100).toFixed(1) + '%'
                  : '—',
  }));

  return (
    <div className="space-y-4">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="scenario" tick={{ fontSize: 12 }} />
          <YAxis tickFormatter={v => `₹${(v / 1e7).toFixed(1)}Cr`} tick={{ fontSize: 11 }} />
          <Tooltip formatter={v => `₹${Number(v).toLocaleString()}`} />
          <Legend />
          <Bar dataKey="Revenue"     fill="#60a5fa" />
          <Bar dataKey="GrossProfit" fill="#34d399" />
          <Bar dataKey="EBITDA"      fill="#a78bfa" />
        </BarChart>
      </ResponsiveContainer>

      <table className="w-full text-sm">
        <thead className="text-left text-slate-500 border-b">
          <tr>
            <th className="py-2">Scenario</th>
            <th className="py-2 text-right">Revenue (₹)</th>
            <th className="py-2 text-right">Gross profit (₹)</th>
            <th className="py-2 text-right">EBITDA (₹)</th>
            <th className="py-2 text-right">EBITDA margin</th>
          </tr>
        </thead>
        <tbody>
          {data.map(d => (
            <tr key={d.scenario} className="border-b">
              <td className="py-2 font-semibold" style={{ color: COLOR[d.scenario] }}>{d.scenario}</td>
              <td className="py-2 text-right">{Number(d.Revenue).toLocaleString()}</td>
              <td className="py-2 text-right">{Number(d.GrossProfit).toLocaleString()}</td>
              <td className="py-2 text-right">{Number(d.EBITDA).toLocaleString()}</td>
              <td className="py-2 text-right">{d.Margin}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
