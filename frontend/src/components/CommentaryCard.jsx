export default function CommentaryCard({ commentary }) {
  if (!commentary) {
    return (
      <div className="card text-sm text-slate-500 text-center py-8">
        <span className="text-2xl mb-2 block">📝</span>
        No commentary available for this period.
      </div>
    );
  }

  return (
    <div className="card space-y-4 animate-fade-up">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-200">CFO Commentary</h3>
        {commentary.grounding_score != null && (
          <span className={`tag ${commentary.grounding_score >= 0.85 ? 'tag-strong' : 'tag-risk'}`}>
            Grounding {(commentary.grounding_score * 100).toFixed(0)}%
          </span>
        )}
      </div>
      <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
        {commentary.narrative}
      </p>
      {Array.isArray(commentary.key_insights) && commentary.key_insights.length > 0 && (
        <div>
          <p className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-2">Key Insights</p>
          <ul className="space-y-1.5">
            {commentary.key_insights.map((k, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                <span className="text-indigo-400 mt-0.5">›</span>
                {k}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
