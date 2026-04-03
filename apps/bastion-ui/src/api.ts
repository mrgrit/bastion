const BASE = ''
const API_KEY = 'bastion-api-key-2026'

export async function api<T = any>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json', ...opts?.headers },
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}
