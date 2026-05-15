export default function SkeletonTable({ rows = 5, cols = 5 }) {
  return (
    <div className="animate-pulse space-y-3">
      {[...Array(rows)].map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-3">
          {[...Array(cols)].map((_, colIndex) => (
            <div key={colIndex} className="h-4 bg-slate-200 rounded-full flex-1"></div>
          ))}
        </div>
      ))}
    </div>
  );
}
