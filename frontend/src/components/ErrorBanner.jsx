export default function ErrorBanner({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400">
      <span className="text-lg">⚠</span>
      <span className="flex-1">{error}</span>
      {onRetry && (
        <button onClick={onRetry} className="text-xs underline hover:text-red-300">
          Retry
        </button>
      )}
    </div>
  );
}
