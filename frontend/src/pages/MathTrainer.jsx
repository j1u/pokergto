import { useCallback, useEffect, useRef, useState } from 'react'
import { Card, Collapsible, Field } from '../components/Common'
import { DRILLS, gradeMath } from '../mathDrills'

const ALL = Object.keys(DRILLS)
const EMPTY = { n: 0, right: 0, close: 0, streak: 0, best: 0, by: {} }

function load(key, dflt) {
  try { const v = JSON.parse(localStorage.getItem(key)); return v ? { ...dflt, ...v } : dflt } catch { return dflt }
}
function save(key, v) {
  try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* ignore */ }
}

function rich(s) {
  return s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith('**') && p.endsWith('**') ? <b key={i}>{p.slice(2, -2)}</b> : p))
}

const VERDICT = {
  right: { label: 'Correct', cls: 'v-best', icon: '★' },
  close: { label: 'Close', cls: 'v-inacc', icon: '≈' },
  wrong: { label: 'Not quite', cls: 'v-mistake', icon: '✗' },
}

export default function MathTrainer({ modeSwitch }) {
  const [cfg, setCfg] = useState(() => {
    const c = load('pgto_math_cfg', { drills: ALL })
    const drills = (c.drills || []).filter((d) => DRILLS[d])
    return { ...c, drills: drills.length ? drills : ALL }
  })
  const [stats, setStats] = useState(() => load('pgto_math_stats', EMPTY))
  const [drill, setDrill] = useState(null)
  const [type, setType] = useState(null)
  const [value, setValue] = useState('')
  const [result, setResult] = useState(null) // { verdict, given }
  const inputRef = useRef(null)

  useEffect(() => save('pgto_math_cfg', cfg), [cfg])
  useEffect(() => save('pgto_math_stats', stats), [stats])

  const next = useCallback(() => {
    const t = cfg.drills[Math.floor(Math.random() * cfg.drills.length)]
    setType(t)
    setDrill(DRILLS[t].gen())
    setValue('')
    setResult(null)
  }, [cfg])

  useEffect(() => { next() }, [next])
  useEffect(() => { if (!result) inputRef.current?.focus() }, [drill, result])

  const submit = useCallback((given) => {
    if (!drill || result) return
    if (drill.input === 'number' && (given === '' || Number.isNaN(Number(given)))) return
    const g = drill.input === 'number' ? Number(given) : given
    const verdict = gradeMath(drill, g)
    setResult({ verdict, given: g })
    setStats((s) => {
      const b = s.by[type] || { n: 0, right: 0 }
      const streak = verdict === 'right' ? s.streak + 1 : 0
      return {
        ...s, n: s.n + 1, right: s.right + (verdict === 'right'), close: s.close + (verdict === 'close'),
        streak, best: Math.max(s.best, streak),
        by: { ...s.by, [type]: { n: b.n + 1, right: b.right + (verdict === 'right') } },
      }
    })
  }, [drill, result, type])

  useEffect(() => {
    const onKey = (e) => {
      if (!drill) return
      if (result && (e.key === 'Enter' || e.key.toLowerCase() === 'n')) { e.preventDefault(); next(); return }
      if (!result && drill.input === 'choice' && e.target.tagName !== 'INPUT') {
        const k = parseInt(e.key, 10)
        if (k >= 1 && k <= drill.choices.length) submit(k - 1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drill, result, next, submit])

  const toggle = (d) => setCfg((c) => {
    const on = c.drills.includes(d)
    if (on && c.drills.length <= 1) return c
    return { ...c, drills: on ? c.drills.filter((x) => x !== d) : ALL.filter((x) => x === d || c.drills.includes(x)) }
  })

  const fmtAns = (d) => (d.input === 'choice' ? d.choices[d.answer] : `${d.answer}${d.unit === '%' ? '%' : ` ${d.unit}`}`)
  const acc = stats.n ? stats.right / stats.n : 0

  return (
    <div className="page">
      <aside className="side">
        {modeSwitch}
        <Collapsible title="Drills">
          <div className="math-drill-list">
            {ALL.map((d) => (
              <button key={d} className={`math-drill ${cfg.drills.includes(d) ? 'on' : ''}`} onClick={() => toggle(d)}>
                <i className={cfg.drills.includes(d) ? 'tick on' : 'tick'}>{cfg.drills.includes(d) ? '✓' : ''}</i>
                <span><b>{DRILLS[d].label}</b><small>{DRILLS[d].blurb}</small></span>
              </button>
            ))}
          </div>
          <div className="chips" style={{ marginTop: 6 }}>
            <button onClick={() => setCfg({ ...cfg, drills: ALL })}>All</button>
          </div>
        </Collapsible>
        <Collapsible title="Session stats" right={<button className="btn tiny ghost" onClick={(e) => { e.stopPropagation(); setStats(EMPTY) }}>Reset</button>}>
          <div className="statgrid">
            <div><b>{stats.n}</b><span>answered</span></div>
            <div><b>{stats.n ? `${Math.round(acc * 100)}%` : '–'}</b><span>correct</span></div>
            <div><b>{stats.close}</b><span>close</span></div>
            <div><b>{stats.streak}</b><span>streak (best {stats.best})</span></div>
          </div>
          {Object.keys(stats.by).length > 0 && (
            <table className="tbl small">
              <tbody>
                {ALL.filter((d) => stats.by[d]).map((d) => (
                  <tr key={d}><td>{DRILLS[d].label}</td><td>{stats.by[d].right}/{stats.by[d].n}</td>
                    <td>{Math.round((100 * stats.by[d].right) / stats.by[d].n)}%</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </Collapsible>
      </aside>

      <main className="main">
        {drill && (
          <div className="trainer math-trainer">
            <div className="spot-chips">
              <span className="tag street">{DRILLS[type].label.toUpperCase()}</span>
              <span className="muted small">{DRILLS[type].blurb}</span>
            </div>

            {(drill.hero || drill.board) && (
              <div className="felt-box">
                {drill.hero && (
                  <div className="hero-hand"><span className="muted small">Your hand</span>
                    <div>{drill.hero.map((c) => <Card key={c} c={c} />)}</div></div>
                )}
                {drill.board && (
                  <div className="hero-hand"><span className="muted small">Board</span>
                    <div>{drill.board.map((c) => <Card key={c} c={c} />)}</div></div>
                )}
                {drill.villain && (
                  <div className="hero-hand"><span className="muted small">Villain shows</span>
                    <div>{drill.villain.map((c) => <Card key={c} c={c} />)}</div></div>
                )}
              </div>
            )}

            <div className="history">
              {drill.lines.map((l, i) => <div key={i} className="hrow"><span>{rich(l)}</span></div>)}
            </div>

            <h3 className="question">{drill.question}</h3>

            {drill.input === 'choice' ? (
              <div className="answer-btns">
                {drill.choices.map((c, i) => {
                  const chosen = result && result.given === i
                  const correct = result && drill.answer === i
                  return (
                    <button key={c} className={`ansbtn ${chosen ? 'chosen' : ''} ${correct ? 'top' : ''}`}
                      style={{ '--c': i === 0 ? '#3faa6b' : '#4f73b3', borderColor: i === 0 ? '#3faa6b' : '#4f73b3' }}
                      disabled={!!result} onClick={() => submit(i)}>
                      <span className="kbd">{i + 1}</span>{c}
                    </button>
                  )
                })}
              </div>
            ) : (
              <form className="math-input" onSubmit={(e) => { e.preventDefault(); submit(value) }}>
                <input ref={inputRef} type="number" step="any" inputMode="decimal" value={value} disabled={!!result}
                  onChange={(e) => setValue(e.target.value)} placeholder="Your answer" />
                <span className="muted">{drill.unit}</span>
                {!result && <button className="btn primary" type="submit" disabled={value === ''}>Check ↵</button>}
              </form>
            )}

            {result && (
              <div className="result">
                <div className={`verdict ${VERDICT[result.verdict].cls}`}>
                  <span className="vicon">{VERDICT[result.verdict].icon}</span>
                  <div>
                    <b>{VERDICT[result.verdict].label}</b>
                    <div className="small">
                      {drill.input === 'number' && <>You said <b>{result.given}{drill.unit === '%' ? '%' : ''}</b> · </>}
                      Answer: <b>{fmtAns(drill)}</b>
                      {drill.input === 'number' && drill.tol > 0 && <span className="muted"> (±{Math.round(drill.tol * 10) / 10} counts as correct)</span>}
                    </div>
                  </div>
                  <button className="btn primary" onClick={next}>Next ↵</button>
                </div>
                <div className="card-box" style={{ marginTop: 10 }}>
                  <h4>How to work it out</h4>
                  <ul className="explain">{drill.explain.map((l, i) => <li key={i}>{rich(l)}</li>)}</ul>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
