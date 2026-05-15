import { NavLink, Route, Routes, Navigate } from 'react-router-dom';
import Upload from './pages/Upload';
import Dashboard from './pages/Dashboard';
import ScenarioPlanner from './pages/ScenarioPlanner';
import ActivityLog from './pages/ActivityLog';
import HITLReview from './pages/HITLReview';

const NAV = [
  { to: '/upload',    label: 'Upload',    icon: '↑' },
  { to: '/dashboard', label: 'Dashboard', icon: '◈' },
  { to: '/scenarios', label: 'Scenarios', icon: '◎' },
  { to: '/hitl',      label: 'HITL',      icon: '⚑' },
  { to: '/activity',  label: 'Activity',  icon: '≋' },
];

export default function App() {
  return (
    <div className="min-h-screen flex flex-col bg-slate-950">
      {/* ── Top bar ── */}
      <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="relative w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/30 animate-glow">
              <span className="text-white font-bold text-lg leading-none">F</span>
            </div>
            <div>
              <h1 className="text-sm font-bold gradient-text">FinSight</h1>
              <p className="text-[10px] text-slate-500 tracking-widest uppercase">FP&A Intelligence</p>
            </div>
          </div>

          {/* Nav */}
          <nav className="flex items-center gap-1">
            {NAV.map(({ to, label, icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150
                   ${isActive
                     ? 'bg-indigo-600/20 text-indigo-300 ring-1 ring-indigo-500/40'
                     : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'}`
                }
              >
                <span className="text-sm">{icon}</span>
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6 animate-fade-up">
        <Routes>
          <Route path="/" element={<Navigate to="/upload" replace />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/scenarios" element={<ScenarioPlanner />} />
          <Route path="/hitl" element={<HITLReview />} />
          <Route path="/activity" element={<ActivityLog />} />
        </Routes>
      </main>

      {/* ── Footer ── */}
      <footer className="text-center text-[11px] text-slate-600 py-3 border-t border-slate-800/40">
        FinSight FP&A AI · Powered by Gemini · Temporal Sagas
      </footer>
    </div>
  );
}
