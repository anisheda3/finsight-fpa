import { NavLink, Route, Routes, Navigate } from 'react-router-dom';
import Upload from './pages/Upload';
import Dashboard from './pages/Dashboard';
import ScenarioPlanner from './pages/ScenarioPlanner';
import ActivityLog from './pages/ActivityLog';
import HITLReview from './pages/HITLReview';

const navItem = ({ isActive }) =>
  `px-3 py-2 rounded-md text-sm font-medium ${
    isActive ? 'bg-brand-600 text-white' : 'text-slate-700 hover:bg-slate-200'
  }`;

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-brand-600 text-white grid place-items-center font-bold">F</div>
            <h1 className="text-lg font-semibold text-slate-800">FinSight FP&amp;A AI</h1>
          </div>
          <nav className="flex items-center gap-2">
            <NavLink to="/upload"    className={navItem}>Upload</NavLink>
            <NavLink to="/dashboard" className={navItem}>Dashboard</NavLink>
            <NavLink to="/scenarios" className={navItem}>Scenarios</NavLink>
            <NavLink to="/hitl"      className={navItem}>HITL</NavLink>
            <NavLink to="/activity"  className={navItem}>Activity</NavLink>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto p-4">
        <Routes>
          <Route path="/" element={<Navigate to="/upload" replace />} />
          <Route path="/upload"    element={<Upload />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/scenarios" element={<ScenarioPlanner />} />
          <Route path="/hitl"      element={<HITLReview />} />
          <Route path="/activity"  element={<ActivityLog />} />
        </Routes>
      </main>
      <footer className="text-center text-xs text-slate-500 py-3">
        FinSight FP&amp;A AI · Fyntwin Assignment #2
      </footer>
    </div>
  );
}
