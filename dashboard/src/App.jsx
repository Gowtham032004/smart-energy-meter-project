import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, BarChart2, Bot, AlertTriangle,
  Zap, Settings, ChevronRight
} from 'lucide-react'
import Dashboard from './pages/Dashboard.jsx'
import Analytics from './pages/Analytics.jsx'
import AgentPage from './pages/AgentPage.jsx'

const NAV = [
  { to: '/',          icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/analytics', icon: BarChart2,       label: 'Analytics' },
  { to: '/agent',     icon: Bot,             label: 'AI Agent' },
]

export default function App() {
  return (
    <div className="app-layout">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">⚡</div>
          <div>
            <h2>Energy AI</h2>
            <span>Smart Meter v2.0</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to} to={to} end={to === '/'}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Device status footer */}
        <div style={{ padding: '0 20px', borderTop: '1px solid var(--border)', paddingTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-muted)' }}>
            <span className="live-dot" />
            <span>METER_001 · Live</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            IST · Auto-refresh 5s
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="main-content">
        <Routes>
          <Route path="/"          element={<Dashboard />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/agent"     element={<AgentPage />} />
        </Routes>
      </main>
    </div>
  )
}
