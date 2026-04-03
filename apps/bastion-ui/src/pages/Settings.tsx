import React from 'react'

export default function Settings() {
  return (
    <div>
      <h2 style={{ fontSize: 22, marginBottom: 24 }}>Settings</h2>

      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 24 }}>
        <h3 style={{ fontSize: 16, marginBottom: 16 }}>Instance Info</h3>
        <table style={{ width: '100%' }}>
          <tbody>
            {[
              ['Service', 'bastion-api'],
              ['Port', ':9000'],
              ['Version', '0.1.0'],
              ['API Key', 'bastion-api-key-2026'],
              ['Central Server', 'http://localhost:7000 (M6)'],
              ['LLM Endpoint', 'http://192.168.0.105:11434/v1 (M5)'],
            ].map(([k, v]) => (
              <tr key={k} style={{ borderBottom: '1px solid #21262d' }}>
                <td style={{ padding: '10px 0', color: '#8b949e', width: 160, fontSize: 13 }}>{k}</td>
                <td style={{ padding: '10px 0', fontSize: 13 }}><code>{v}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
