export default function CommentaryCard({ commentary }) {
  return (
    <div className="card">
      <h3 className="font-semibold mb-2">CFO commentary</h3>
      {!commentary
        ? <p className="text-sm text-slate-500">No commentary persisted yet for this period.</p>
        : (
          <>
            <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
              {commentary.narrative}
            </p>
            {Array.isArray(commentary.key_insights) && commentary.key_insights.length > 0 && (
              <ul className="mt-3 text-sm list-disc list-inside text-slate-600">
                {commentary.key_insights.map((k, i) => <li key={i}>{k}</li>)}
              </ul>
            )}
            {commentary.grounding_score != null && (
              <p className="mt-3 text-xs text-slate-500">
                Grounding score: <span className="font-mono">{Number(commentary.grounding_score).toFixed(2)}</span>
              </p>
            )}
          </>
        )
      }
    </div>
  );
}
