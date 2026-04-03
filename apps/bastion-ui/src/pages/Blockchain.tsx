import React, { useEffect, useState } from 'react'
import { api } from '../api.ts'

export default function Blockchain() {
  const [blocks, setBlocks] = useState<any[]>([])
  const [verify, setVerify] = useState<any>(null)
  const [leaders, setLeaders] = useState<any[]>([])

  useEffect(() => {
    api('/blockchain/blocks').then(d => setBlocks(d.blocks)).catch(console.error)
    api('/blockchain/verify').then(setVerify).catch(console.error)
    api('/blockchain/leaderboard').then(d => setLeaders(d.leaderboard)).catch(console.error)
  }, [])

  return (
    <div>
      <h2 style={{ fontSize: 22, marginBottom: 24 }}>Blockchain</h2>

      {/* Verification */}
      <div style={{
        background: verify?.valid ? '#0d1f0d' : '#1f0d0d',
        border: `1px solid ${verify?.valid ? '#238636' : '#da3633'}`,
        borderRadius: 8, padding: 16, marginBottom: 24, display: 'flex', gap: 16, alignItems: 'center',
      }}>
        <span style={{ fontSize: 24 }}>{verify?.valid ? '✅' : '⚠️'}</span>
        <div>
          <div style={{ fontWeight: 600 }}>Chain {verify?.valid ? 'Valid' : 'Invalid'}</div>
          <div style={{ fontSize: 12, color: '#8b949e' }}>
            {verify?.blocks || 0} blocks{verify?.tampered?.length > 0 && `, ${verify.tampered.length} tampered`}
          </div>
        </div>
      </div>

      {/* Leaderboard */}
      {leaders.length > 0 && (
        <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20, marginBottom: 24 }}>
          <h3 style={{ fontSize: 16, marginBottom: 12 }}>Leaderboard</h3>
          {leaders.map((l, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, padding: '8px 0', borderBottom: '1px solid #21262d' }}>
              <span style={{ width: 24, color: '#8b949e' }}>#{i + 1}</span>
              <span style={{ flex: 1 }}><code>{l.agent_id}</code></span>
              <span style={{ color: '#3fb950' }}>{l.blocks} blocks</span>
              <span style={{ color: '#f0883e', fontWeight: 600 }}>{l.total_reward?.toFixed(1)} pts</span>
            </div>
          ))}
        </div>
      )}

      {/* Blocks */}
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 }}>
        <h3 style={{ fontSize: 16, marginBottom: 12 }}>Recent Blocks</h3>
        {blocks.length === 0 && <div style={{ color: '#8b949e' }}>No blocks yet</div>}
        {blocks.map((b, i) => (
          <div key={i} style={{
            display: 'flex', gap: 12, padding: '10px 0', borderBottom: '1px solid #21262d',
            fontSize: 13, alignItems: 'center',
          }}>
            <span style={{
              background: '#21262d', borderRadius: 4, padding: '2px 8px',
              fontFamily: 'monospace', fontSize: 11, color: '#58a6ff',
            }}>#{b.block_index}</span>
            <code style={{ color: '#8b949e', fontSize: 11 }}>{b.block_hash?.slice(0, 20)}...</code>
            <span style={{ flex: 1 }}><code>{b.agent_id}</code></span>
            <span style={{ color: '#f0883e' }}>{b.reward_amount} pts</span>
          </div>
        ))}
      </div>
    </div>
  )
}
