import { HANDS } from '../constants'

/**
 * 13x13 strategy grid.
 * cells: array(169) of null | { w: 0..1 weight, f: [freqs per action] }
 * colors: array of colors per action
 */
export default function RangeGrid({ cells, colors, onHover, onSelect, selected, highlight, small, onPaint, paintMode, dimLabel }) {
  return (
    <div className={`grid13 ${small ? 'small' : ''}`} onMouseLeave={() => onHover && onHover(null)}>
      {HANDS.map((h, i) => {
        const c = cells ? cells[i] : null
        const w = c ? Math.max(0, Math.min(1, c.w ?? 1)) : 0
        const isSel = selected === i
        const isHi = highlight === i
        return (
          <div
            key={h}
            className={`cell ${isSel ? 'sel' : ''} ${isHi ? 'hi' : ''} ${w <= 0.001 ? 'empty' : ''}`}
            onMouseEnter={(e) => {
              onHover && onHover(i)
              if (paintMode && e.buttons === 1 && onPaint) onPaint(i)
            }}
            onMouseDown={(e) => {
              if (onPaint) { e.preventDefault(); onPaint(i, true) }
            }}
            onClick={() => onSelect && onSelect(i)}
          >
            {c && w > 0.001 && (
              <div className="fill" style={{ height: `${Math.max(8, w * 100)}%` }}>
                {(c.f || [1]).map((f, k) =>
                  f > 0.001 ? (
                    <div key={k} style={{ width: `${f * 100}%`, background: colors ? colors[k] : '#3faa6b' }} />
                  ) : null,
                )}
              </div>
            )}
            <span className="lbl">{h}</span>
            {dimLabel && c && c.label != null && <span className="sub">{c.label}</span>}
          </div>
        )
      })}
    </div>
  )
}
