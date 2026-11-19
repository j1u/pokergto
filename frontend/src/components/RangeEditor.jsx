import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { HAND_COMBOS, HANDS } from '../constants'
import RangeGrid from './RangeGrid'

const PRESETS = {
  'Premium (QQ+, AK)': 'QQ+,AKs,AKo',
  'Tight 12%': '77+,A9s+,KTs+,QTs+,JTs,ATo+,KJo+',
  'Medium 25%': '44+,A2s+,K8s+,Q9s+,J9s+,T8s+,97s+,86s+,76s,65s,A9o+,KTo+,QTo+,JTo',
  'Wide 45%': '22+,A2s+,K2s+,Q5s+,J7s+,T7s+,96s+,85s+,74s+,63s+,53s+,43s,A2o+,K8o+,Q9o+,J9o+,T8o+,98o',
  'Any two': '22+,A2s+,K2s+,Q2s+,J2s+,T2s+,92s+,82s+,72s+,62s+,52s+,42s+,32s,A2o+,K2o+,Q2o+,J2o+,T2o+,92o+,82o+,72o+,62o+,52o+,42o+,32o',
}

export default function RangeEditor({ title, weights, onApply, onClose }) {
  const [w, setW] = useState(() => (weights ? [...weights] : new Array(169).fill(0)))
  const [paintW, setPaintW] = useState(100)
  const [text, setText] = useState('')
  const [err, setErr] = useState(null)
  const eraseRef = useRef(false)

  useEffect(() => {
    const t = setTimeout(() => {
      api.formatRange(w).then((r) => setText(r.text)).catch(() => {})
    }, 250)
    return () => clearTimeout(t)
  }, [w])

  const combos = w.reduce((s, x, i) => s + x * HAND_COMBOS[i], 0)
  const paint = (i, start) => {
    const target = paintW / 100
    if (start) eraseRef.current = w[i] >= target - 1e-6 && w[i] > 0
    const val = eraseRef.current ? 0 : target
    setW((prev) => {
      const n = [...prev]
      n[i] = val
      return n
    })
  }
  const importText = async (t) => {
    try {
      setErr(null)
      const r = await api.parseRange(t)
      setW(r.weights)
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <div className="modal-back" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title || 'Edit range'}</h3>
          <span className="muted">
            {combos.toFixed(1)} combos · {((combos / 1326) * 100).toFixed(1)}%
          </span>
        </div>
        <div className="editor-body">
          <div style={{ userSelect: 'none' }}>
            <RangeGrid
              cells={w.map((x) => ({ w: x, f: [1] }))}
              colors={['#d9a441']}
              onPaint={paint}
              paintMode
            />
            <div className="muted small">Click / drag to paint. Clicking a painted cell erases.</div>
          </div>
          <div className="editor-side">
            <label className="field">
              <span className="flabel">Paint weight: {paintW}%</span>
              <input type="range" min={5} max={100} step={5} value={paintW} onChange={(e) => setPaintW(+e.target.value)} />
            </label>
            <div className="btnrow wrap">
              {Object.entries(PRESETS).map(([k, v]) => (
                <button key={k} className="btn small ghost" onClick={() => importText(v)}>{k}</button>
              ))}
            </div>
            <label className="field">
              <span className="flabel">Range text (e.g. <code>TT+,AQs+,KQo,T9s-76s,A5s:0.5</code>)</span>
              <textarea rows={7} value={text} onChange={(e) => setText(e.target.value)} />
            </label>
            {err && <div className="error">{err}</div>}
            <div className="btnrow">
              <button className="btn small" onClick={() => importText(text)}>Import text</button>
              <button className="btn small ghost" onClick={() => setW(new Array(169).fill(0))}>Clear</button>
            </div>
            <div className="btnrow" style={{ marginTop: 'auto' }}>
              <button className="btn primary" onClick={() => onApply(w)}>Apply</button>
              <button className="btn ghost" onClick={onClose}>Cancel</button>
            </div>
          </div>
        </div>
        <div className="muted small">{HANDS.length} classes</div>
      </div>
    </div>
  )
}
