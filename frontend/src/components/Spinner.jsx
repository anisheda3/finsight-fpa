export default function Spinner({ size = 'md', label = 'Loading…' }) {
  const sz = size === 'sm' ? 'w-4 h-4' : size === 'lg' ? 'w-10 h-10' : 'w-6 h-6';
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8">
      <div className={`${sz} border-2 border-indigo-500/30 border-t-indigo-400 rounded-full animate-spin`} />
      {label && <p className="text-xs text-slate-500">{label}</p>}
    </div>
  );
}
