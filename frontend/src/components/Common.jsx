import { useState } from 'react'
import { ALL_CARDS, RANKS, SUITS, SUIT_SYMBOL, pct } from '../constants'

export function FreqBar({ actions, freqs, colors, showLabels = true, height = 26 }) {
  return (
    <div>
      <div className="freqbar" style={{ height }}>
        {freqs.map((f, i) =>
          f > 0.0005 ? (
            <div key={i} style={{ width: `${f * 100}%`, background: colors[i] }} title={`${actions[i].label}: ${pct(f)}`}>
              {f > 0.08 && <span>{pct(f, 0)}</span>}
            </div>
          ) : null,
        )}
      </div>
      {showLabels && (
        <div className="legend">
          {actions.map((a, i) => (
            <span key={a.key + i}>
              <i style={{ background: colors[i] }} /> {a.label} <b>{pct(freqs[i])}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export function Card({ c, size = 'md', onClick }) {
  if (!c) return <span className={`pcard ${size} blank`} onClick={onClick}>?</span>
  const r = c[0].toUpperCase(), s = c[1].toLowerCase()
  return (
    <span className={`pcard ${size} suit-${s}`} onClick={onClick}>
      {r === 'T' ? '10' : r}
      <small>{SUIT_SYMBOL[s]}</small>
    </span>
  )
}

export function CardPicker({ selected, onChange, max = 5, disabled = [] }) {
  const toggle = (c) => {
    if (selected.includes(c)) onChange(selected.filter((x) => x !== c))
    else if (selected.length < max) onChange([...selected, c])
  }
  return (
    <div className="cardpicker">
      {SUITS.map((s) => (
        <div key={s} className="row">
          {RANKS.split('').map((r) => {
            const c = r + s
            const sel = selected.includes(c)
            const dis = disabled.includes(c)
            return (
              <button
                key={c}
                className={`pc suit-${s} ${sel ? 'sel' : ''}`}
                disabled={dis && !sel}
                onClick={() => toggle(c)}
              >
                {r}
                <small>{SUIT_SYMBOL[s]}</small>
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}

export function randomCards(n, exclude = []) {
  const pool = ALL_CARDS.filter((c) => !exclude.includes(c))
  const out = []
  while (out.length < n && pool.length) {
    const k = Math.floor(Math.random() * pool.length)
    out.push(pool.splice(k, 1)[0])
  }
  return out
}

export function Segmented({ options, value, onChange, small }) {
  return (
    <div className={`seg ${small ? 'small' : ''}`}>
      {options.map((o) => {
        const v = typeof o === 'string' ? o : o.value
        const l = typeof o === 'string' ? o : o.label
        return (
          <button key={v} className={value === v ? 'on' : ''} onClick={() => onChange(v)} disabled={o.disabled}>
            {l}
          </button>
        )
      })}
    </div>
  )
}

export function Field({ label, children, hint }) {
  return (
    <label className="field">
      <span className="flabel">
        {label}
        {hint && <em title={hint}> ⓘ</em>}
      </span>
      {children}
    </label>
  )
}

export function Collapsible({ title, children, defaultOpen = true, right }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="panel-section">
      <div className="psh" onClick={() => setOpen(!open)}>
        <span>{open ? '▾' : '▸'} {title}</span>
        {right}
      </div>
      {open && <div className="psb">{children}</div>}
    </div>
  )
}

export function ErrorBox({ error }) {
  if (!error) return null
  return <div className="error">⚠ {error}</div>
}

export function Spinner({ text }) {
  return (
    <div className="spinner-wrap">
      <div className="spinner" />
      {text && <span>{text}</span>}
    </div>
  )
}

export function MiniBars({ rows, colors, actions }) {
  // rows: [{name, pct, f:[...]}]
  return (
    <table className="minibars">
      <tbody>
        {rows.map((r) => (
          <tr key={r.name}>
            <td className="nm">{r.name}</td>
            <td className="pc">{pct(r.pct)}</td>
            <td className="bar">
              <div className="freqbar thin">
                {r.f.map((f, i) => (f > 0.001 ? <div key={i} style={{ width: `${f * 100}%`, background: colors[i] }} title={`${actions[i].label} ${pct(f)}`} /> : null))}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
