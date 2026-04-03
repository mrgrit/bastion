import React from 'react'
import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard.tsx'
import Assets from './pages/Assets.tsx'
import Blockchain from './pages/Blockchain.tsx'
import Agent from './pages/Agent.tsx'
import Settings from './pages/Settings.tsx'

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: '📊' },
  { to: '/assets', label: 'Assets', icon: '🖥️' },
  { to: '/agent', label: 'AI Agent', icon: '🤖' },
  { to: '/blockchain', label: 'Blockchain', icon: '⛓️' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function App() {
  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Sidebar */}
      <nav style={{
        width: 220, background: '#161b22', borderRight: '1px solid #30363d',
        padding: '20px 0', display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ padding: '0 20px 24px', borderBottom: '1px solid #30363d' }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: '#58a6ff' }}>Bastion</h1>
          <div style={{ fontSize: 12, color: '#8b949e', marginTop: 4 }}>실무 운영/보안 에이전트</div>
        </div>
        <div style={{ marginTop: 16, flex: 1 }}>
          {navItems.map(n => (
            <NavLink key={n.to} to={n.to} style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 20px', color: isActive ? '#58a6ff' : '#8b949e',
              background: isActive ? '#1f2937' : 'transparent',
              textDecoration: 'none', fontSize: 14, borderLeft: isActive ? '3px solid #58a6ff' : '3px solid transparent',
            })}>
              <span>{n.icon}</span><span>{n.label}</span>
            </NavLink>
          ))}
        </div>
        <div style={{ padding: '12px 20px', fontSize: 11, color: '#484f58', borderTop: '1px solid #30363d' }}>
          v0.1.0 — :9000
        </div>
      </nav>

      {/* Main */}
      <main style={{ flex: 1, padding: 32, overflow: 'auto' }}>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/assets" element={<Assets />} />
          <Route path="/agent" element={<Agent />} />
          <Route path="/blockchain" element={<Blockchain />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
