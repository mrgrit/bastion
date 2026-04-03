import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'

const card = (label: string, value: string | number, color = '#58a6ff') => (
  <div style={{
    background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
    padding: '20px 24px', flex: '1 1 200px', minWidth: 180,
  }}>
    <div style={{ fontSize: 12, color: '#8b949e', marginBottom: 8 }}>{label}</div>
    <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
  </div>
)

export default function Dashboard() {
  const [data, setData] = useState<any>(null)

  useEffect(() => {
    api('/dashboard/summary').then(setData).catch(console.error)
  }, [])

  if (!data) return <div style={{ color: '#8b949e' }}>Loading...</div>

  const a = data.assets
  return (
    <div>
      <h2 style={{ fontSize: 22, marginBottom: 24 }}>Dashboard</h2>

      {/* Stats */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 32 }}>
        {card('Total Assets', a.total)}
        {card('Healthy', a.by_status?.healthy || 0, '#3fb950')}
        {card('Registered', a.by_status?.registered || 0, '#d29922')}
        {card('Operations', data.operations.total, '#bc8cff')}
        {card('PoW Blocks', data.blockchain.blocks, '#f0883e')}
      </div>

      {/* Status breakdown */}
      <div style={{
        background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 24,
      }}>
        <h3 style={{ fontSize: 16, marginBottom: 16 }}>Asset Status</h3>
        {Object.entries(a.by_status || {}).map(([status, count]) => (
          <div key={status} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <span style={{
              width: 10, height: 10, borderRadius: '50%',
              background: status === 'healthy' ? '#3fb950' : status === 'registered' ? '#d29922' : '#f85149',
            }} />
            <span style={{ flex: 1, color: '#e6edf3' }}>{status}</span>
            <span style={{ fontWeight: 600 }}>{String(count)}</span>
          </div>
        ))}
        {Object.keys(a.by_status || {}).length === 0 && (
          <div style={{ color: '#8b949e' }}>No assets registered yet</div>
        )}
      </div>
    </div>
  )
}
