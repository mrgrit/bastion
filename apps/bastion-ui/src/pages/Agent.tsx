import React, { useState } from 'react'
import { api } from '../api.ts'

export default function Agent() {
  const [instruction, setInstruction] = useState('')
  const [risk, setRisk] = useState('low')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<any[]>([])

  const submit = async () => {
    if (!instruction.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const r = await api('/agent/task', {
        method: 'POST',
        body: JSON.stringify({ instruction, risk_level: risk }),
      })
      setResult(r)
      setHistory(prev => [{ instruction, risk, result: r, time: new Date().toLocaleTimeString() }, ...prev])
    } catch (e: any) {
      setResult({ error: e.message })
    }
    setLoading(false)
    setInstruction('')
  }

  return (
    <div>
      <h2 style={{ fontSize: 22, marginBottom: 24 }}>AI Agent</h2>

      {/* Task input */}
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 24, marginBottom: 24 }}>
        <div style={{ fontSize: 14, color: '#8b949e', marginBottom: 12 }}>자연어로 작업을 요청하세요</div>
        <div style={{ display: 'flex', gap: 12 }}>
          <input
            placeholder="예: secu 서버에 Suricata 룰 업데이트해줘"
            value={instruction}
            onChange={e => setInstruction(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            style={{
              flex: 1, background: '#0d1117', color: '#e6edf3', border: '1px solid #30363d',
              borderRadius: 6, padding: '10px 14px', fontSize: 14,
            }}
          />
          <select value={risk} onChange={e => setRisk(e.target.value)} style={{
            background: '#0d1117', color: '#e6edf3', border: '1px solid #30363d',
            borderRadius: 6, padding: '8px 12px', fontSize: 13,
          }}>
            <option value="low">Low Risk</option>
            <option value="medium">Medium Risk</option>
            <option value="high">High Risk</option>
            <option value="critical">Critical</option>
          </select>
          <button onClick={submit} disabled={loading} style={{
            background: '#238636', color: '#fff', border: 'none',
            borderRadius: 6, padding: '10px 20px', cursor: 'pointer', fontSize: 14,
          }}>
            {loading ? 'Running...' : 'Execute'}
          </button>
        </div>
      </div>

      {/* Result */}
      {result && (
        <div style={{
          background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
          padding: 20, marginBottom: 24,
        }}>
          <h3 style={{ fontSize: 14, marginBottom: 12, color: result.error ? '#f85149' : '#3fb950' }}>
            {result.error ? 'Error' : 'Result'}
          </h3>
          <pre style={{
            background: '#0d1117', padding: 16, borderRadius: 6, fontSize: 12,
            overflow: 'auto', maxHeight: 400, color: '#e6edf3',
          }}>
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}

      {/* Stub notice */}
      <div style={{
        background: '#1c1917', border: '1px solid #78350f', borderRadius: 8, padding: 16, marginBottom: 24,
      }}>
        <span style={{ color: '#fbbf24' }}>M5 구현 후 활성화됩니다</span>
        <span style={{ color: '#8b949e', marginLeft: 8 }}>— LLM 연동, 실행 계획 생성, SubAgent 실행</span>
      </div>

      {/* History */}
      {history.length > 0 && (
        <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 }}>
          <h3 style={{ fontSize: 14, marginBottom: 12 }}>Recent Tasks</h3>
          {history.map((h, i) => (
            <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid #21262d', fontSize: 13 }}>
              <span style={{ color: '#8b949e', marginRight: 8 }}>{h.time}</span>
              <span style={{ color: '#58a6ff' }}>[{h.risk}]</span>{' '}
              <span>{h.instruction}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
