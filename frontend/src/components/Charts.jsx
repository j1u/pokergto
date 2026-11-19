import { pct } from '../constants'

/** Equity distribution curves (x = percentile of range, y = equity). */
export function EquityCurve({ series, height = 180 }) {
  const W = 420, H = height, pad = 28
  const x = (i, n) => pad + (i / (n - 1)) * (W - pad - 8)
  const y = (v) => H - pad - v * (H - pad - 10)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart">
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}>
          <line x1={pad} x2={W - 8} y1={y(g)} y2={y(g)} className="gridline" />
          <text x={4} y={y(g) + 4} className="axis">{g * 100}%</text>
        </g>
      ))}
      <text x={W / 2} y={H - 6} className="axis" textAnchor="middle">percentile of range (weakest → strongest)</text>
      {series.map((s) => (
        <polyline
          key={s.name}
          fill="none"
          stroke={s.color}
          strokeWidth={2.5}
          points={s.data.map((v, i) => `${x(i, s.data.length)},${y(v)}`).join(' ')}
        />
      ))}
      {series.map((s, k) => (
        <g key={s.name + 'l'} transform={`translate(${pad + 10 + k * 130}, 14)`}>
          <rect width={10} height={10} fill={s.color} rx={2} />
          <text x={14} y={9} className="axis">{s.name}</text>
        </g>
      ))}
    </svg>
  )
}

/** Grouped horizontal bars comparing two distributions by category. */
export function CompareBars({ rows, colors, names }) {
  const max = Math.max(0.01, ...rows.flatMap((r) => r.values))
  return (
    <div className="comparebars">
      <div className="legend">
        {names.map((n, i) => (
          <span key={n}><i style={{ background: colors[i] }} /> {n}</span>
        ))}
      </div>
      {rows.map((r) => (
        <div key={r.name} className="cbrow">
          <div className="nm">{r.name}</div>
          <div className="bars">
            {r.values.map((v, i) => (
              <div key={i} className="b">
                <div style={{ width: `${(v / max) * 100}%`, background: colors[i] }} />
                <span>{pct(v)}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function EquityBar({ a, b, labelA, labelB, colorA = '#d9a441', colorB = '#5b8def' }) {
  return (
    <div className="eqbar">
      <div style={{ width: `${a * 100}%`, background: colorA }}>
        <span>{labelA} {pct(a)}</span>
      </div>
      <div style={{ width: `${b * 100}%`, background: colorB }}>
        <span>{labelB} {pct(b)}</span>
      </div>
    </div>
  )
}
