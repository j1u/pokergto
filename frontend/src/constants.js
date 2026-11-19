export const RANKS = 'AKQJT98765432'
export const SUITS = ['s', 'h', 'd', 'c']
export const SUIT_SYMBOL = { s: '♠', h: '♥', d: '♦', c: '♣' }
export const POSITIONS = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB']

// grid order identical to backend: row = first rank (A..2), col = second rank; suited upper-right
export const HANDS = (() => {
  const out = []
  for (let i = 0; i < 13; i++) {
    for (let j = 0; j < 13; j++) {
      const a = RANKS[i], b = RANKS[j]
      if (i === j) out.push(a + b)
      else if (j > i) out.push(a + b + 's')
      else out.push(b + a + 'o')
    }
  }
  return out
})()
export const HAND_COMBOS = HANDS.map((h) => (h.length === 2 ? 6 : h.endsWith('s') ? 4 : 12))

const AGG = ['#f2a65a', '#e8724a', '#d94a3d', '#b52a35', '#8f1d33']
export const COLORS = {
  fold: '#4f73b3',
  call: '#3faa6b',
  check: '#3faa6b',
  allin: '#7d2a6a',
}

/** Color per action given the action list (keys/labels). */
export function actionColors(actions) {
  let k = 0
  const aggCount = actions.filter((a) => !['fold', 'call', 'check'].includes(a.key)).length
  return actions.map((a) => {
    if (a.key === 'fold') return COLORS.fold
    if (a.key === 'call' || a.key === 'check') return COLORS.call
    if ((a.label || '').startsWith('All-in')) { k++; return COLORS.allin }
    const idx = aggCount <= 1 ? 2 : Math.round((k++ / Math.max(1, aggCount - 1)) * (AGG.length - 1))
    return AGG[Math.min(idx, AGG.length - 1)]
  })
}

export const pct = (x, d = 1) => (x == null || isNaN(x) ? '–' : `${(x * 100).toFixed(d)}%`)
export const bb = (x, d = 2) => (x == null || isNaN(x) ? '–' : `${x >= 0 ? '' : ''}${Number(x).toFixed(d)}`)

export function comboToClass(combo) {
  // combo like "AhKd"
  const r1 = combo[0], s1 = combo[1], r2 = combo[2], s2 = combo[3]
  const i1 = RANKS.indexOf(r1), i2 = RANKS.indexOf(r2)
  const hi = i1 <= i2 ? r1 : r2, lo = i1 <= i2 ? r2 : r1
  if (r1 === r2) return r1 + r2
  return hi + lo + (s1 === s2 ? 's' : 'o')
}

export const ALL_CARDS = (() => {
  const out = []
  for (const s of SUITS) for (const r of RANKS) out.push(r + s)
  return out
})()

export function parseCardString(str) {
  const t = (str || '').replace(/[\s,]/g, '')
  const out = []
  for (let i = 0; i + 1 < t.length; i += 2) out.push(t[i].toUpperCase() + t[i + 1].toLowerCase())
  return out
}
