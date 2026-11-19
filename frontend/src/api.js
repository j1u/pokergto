async function req(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = data.detail
    throw new Error(typeof d === 'string' ? d : d ? JSON.stringify(d) : `HTTP ${res.status}`)
  }
  return data
}

export const api = {
  meta: () => req('/api/meta'),
  preflop: (b) => req('/api/preflop', b),
  preset: (b) => req('/api/postflop/preset', b),
  solve: (b) => req('/api/postflop/solve', b),
  river: (b) => req('/api/postflop/river', b),
  equity: (b) => req('/api/equity', b),
  trainerSpot: (b) => req('/api/trainer/spot', b),
  parseRange: (text) => req('/api/range/parse', { text }),
  formatRange: (weights) => req('/api/range/format', { weights }),
}
