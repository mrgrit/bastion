import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'

const statusColor: Record<string, string> = {
  healthy: '#3fb950', registered: '#d29922', bootstrapped: '#58a6ff', unreachable: '#f85149',
}

export default function Assets() {
  const [assets, setAssets] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ name: '', ip: '', role: '', ssh_user: 'opsclaw' })
  const [checking, setChecking] = useState<string | null>(null)

  const load = () => api('/assets').then(d => setAssets(d.assets)).catch(console.error)
  useEffect(() => { load() }, [])

  const addAsset = async () => {
    await api('/assets', { method: 'POST', body: JSON.stringify(form) })
    setForm({ name: '', ip: '', role: '', ssh_user: 'opsclaw' })
    setShowAdd(false)
    load()
  }

  const healthCheck = async (id: string) => {
    setChecking(id)
    try {
      const r = await api(`/assets/${id}/health`)
      alert(`${r.asset_id}: ${r.healthy ? 'Healthy' : 'Unreachable'}\n${JSON.stringify(r.detail, null, 2)}`)
    } catch (e: any) { alert(e.message) }
    setChecking(null)
    load()
  }

  const onboard = async (id: string) => {
    const r = await api(`/assets/${id}/onboard`, { method: 'POST', body: JSON.stringify({ auto_bootstrap: true }) })
    alert(`Onboard: ${r.status}\nSteps: ${r.steps?.join(', ')}`)
    load()
  }

  const deleteAsset = async (id: string, name: string) => {
    if (!confirm(`Delete ${name}?`)) return
    await api(`/assets/${id}`, { method: 'DELETE' })
    load()
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 style={{ fontSize: 22 }}>Assets</h2>
        <button onClick={() => setShowAdd(!showAdd)} style={btnStyle}>{showAdd ? 'Cancel' : '+ Add Asset'}</button>
      </div>

      {showAdd && (
        <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20, marginBottom: 24 }}>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <input placeholder="Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} style={inputStyle} />
            <input placeholder="IP" value={form.ip} onChange={e => setForm({ ...form, ip: e.target.value })} style={inputStyle} />
            <input placeholder="Role" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} style={inputStyle} />
            <input placeholder="SSH User" value={form.ssh_user} onChange={e => setForm({ ...form, ssh_user: e.target.value })} style={inputStyle} />
            <button onClick={addAsset} style={{ ...btnStyle, background: '#238636' }}>Register</button>
          </div>
        </div>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #30363d' }}>
            {['Name', 'IP', 'Role', 'Status', 'SubAgent', 'Actions'].map(h => (
              <th key={h} style={{ textAlign: 'left', padding: '10px 12px', fontSize: 12, color: '#8b949e' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {assets.map(a => (
            <tr key={a.id} style={{ borderBottom: '1px solid #21262d' }}>
              <td style={tdStyle}><strong>{a.name}</strong></td>
              <td style={tdStyle}><code>{a.ip}</code></td>
              <td style={tdStyle}>{a.role}</td>
              <td style={tdStyle}>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '2px 10px', borderRadius: 12, fontSize: 12,
                  background: `${statusColor[a.status] || '#484f58'}22`, color: statusColor[a.status] || '#8b949e',
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
                  {a.status}
                </span>
              </td>
              <td style={tdStyle}><code style={{ fontSize: 11, color: '#8b949e' }}>{a.subagent_url}</code></td>
              <td style={tdStyle}>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => healthCheck(a.id)} disabled={checking === a.id} style={smallBtn}>
                    {checking === a.id ? '...' : 'Health'}
                  </button>
                  <button onClick={() => onboard(a.id)} style={smallBtn}>Onboard</button>
                  <button onClick={() => deleteAsset(a.id, a.name)} style={{ ...smallBtn, color: '#f85149' }}>Del</button>
                </div>
              </td>
            </tr>
          ))}
          {assets.length === 0 && (
            <tr><td colSpan={6} style={{ ...tdStyle, color: '#8b949e', textAlign: 'center' }}>No assets</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

const btnStyle: React.CSSProperties = {
  background: '#21262d', color: '#e6edf3', border: '1px solid #30363d',
  borderRadius: 6, padding: '8px 16px', cursor: 'pointer', fontSize: 13,
}
const smallBtn: React.CSSProperties = {
  background: 'transparent', color: '#58a6ff', border: '1px solid #30363d',
  borderRadius: 4, padding: '4px 10px', cursor: 'pointer', fontSize: 11,
}
const inputStyle: React.CSSProperties = {
  background: '#0d1117', color: '#e6edf3', border: '1px solid #30363d',
  borderRadius: 6, padding: '8px 12px', fontSize: 13, flex: '1 1 150px',
}
const tdStyle: React.CSSProperties = { padding: '10px 12px', fontSize: 13 }
