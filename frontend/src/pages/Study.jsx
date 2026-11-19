import { useEffect, useRef, useState } from 'react'
import { ALL_LESSONS, LEVELS } from '../studyGuide'
import { DEFAULTS as TRAINER_DEFAULTS } from './Trainer'

function load(key, dflt) {
  try { const v = JSON.parse(localStorage.getItem(key)); return v ?? dflt } catch { return dflt }
}
function save(key, v) {
  try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* ignore */ }
}

/** Render **bold** markup. */
function rich(s) {
  return s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? <b key={i}>{part.slice(2, -2)}</b> : part,
  )
}

export default function Study({ meta, setTab }) {
  const [cur, setCur] = useState(() => {
    const id = load('pgto_study_cur', ALL_LESSONS[0].id)
    return ALL_LESSONS.some((l) => l.id === id) ? id : ALL_LESSONS[0].id
  })
  const [done, setDone] = useState(() => new Set(load('pgto_study_done', [])))
  const [reveal, setReveal] = useState(false)
  const mainRef = useRef(null)

  useEffect(() => save('pgto_study_cur', cur), [cur])
  useEffect(() => save('pgto_study_done', [...done]), [done])
  useEffect(() => {
    setReveal(false)
    mainRef.current?.scrollTo({ top: 0 })
  }, [cur])

  const idx = ALL_LESSONS.findIndex((l) => l.id === cur)
  const lesson = ALL_LESSONS[idx]
  const level = LEVELS.find((lv) => lv.id === lesson.level)
  const prev = ALL_LESSONS[idx - 1]
  const next = ALL_LESSONS[idx + 1]
  const isDone = done.has(cur)
  const progress = done.size / ALL_LESSONS.length

  const toggleDone = (id, value) => {
    setDone((d) => {
      const n = new Set(d)
      if (value ?? !n.has(id)) n.add(id)
      else n.delete(id)
      return n
    })
  }

  const practice = (p) => {
    if (p.math) {
      save('pgto_trainer_mode', 'math')
      save('pgto_math_cfg', { drills: p.math })
    }
    if (p.trainer) {
      save('pgto_trainer_mode', 'spots')
      const old = load('pgto_trainer_cfg', {}) || {}
      const n = old.n_players || TRAINER_DEFAULTS.n_players
      const seats = meta?.seats?.[n] || meta?.seats?.[String(n)] || TRAINER_DEFAULTS.positions
      // start from defaults so leftover filters from earlier drills don't block the topic
      save('pgto_trainer_cfg', { ...TRAINER_DEFAULTS, positions: seats, profile: old.profile || 'gto',
                                 stacks: old.stacks || TRAINER_DEFAULTS.stacks, n_players: n, ...p.trainer })
    }
    setTab(p.tab)
  }

  return (
    <div className="page study">
      <aside className="side study-side">
        <div className="study-progress">
          <div className="hd-head"><b>Study guide</b><span className="muted small">{done.size}/{ALL_LESSONS.length} done</span></div>
          <div className="pbar"><div style={{ width: `${progress * 100}%` }} /></div>
        </div>
        {LEVELS.map((lv) => {
          const n = lv.lessons.filter((l) => done.has(l.id)).length
          return (
            <div key={lv.id} className="study-level">
              <div className="study-level-title">
                <span>{lv.title}</span>
                <span className="muted small">{n}/{lv.lessons.length}</span>
              </div>
              {lv.lessons.map((l) => (
                <button key={l.id} className={`study-item ${l.id === cur ? 'on' : ''}`} onClick={() => setCur(l.id)}>
                  <i className={done.has(l.id) ? 'tick on' : 'tick'}>{done.has(l.id) ? '✓' : ''}</i>
                  {l.title}
                </button>
              ))}
            </div>
          )
        })}
      </aside>

      <main className="main" ref={mainRef}>
        <div className="narrow study-main">
          <div className="muted small study-crumb">{level.title} · lesson {idx + 1} of {ALL_LESSONS.length}</div>
          <h2 className="study-title">{lesson.title}</h2>
          <p className="study-summary">{lesson.summary}</p>
          {lesson.id === level.lessons[0].id && <div className="card-box study-blurb">{level.blurb}</div>}

          <div className="card-box study-card">
            <h4>Key ideas</h4>
            <ul className="study-points">{lesson.points.map((p, i) => <li key={i}>{rich(p)}</li>)}</ul>
          </div>

          {lesson.math && (
            <div className="card-box study-card">
              <h4>Worked examples</h4>
              <ul className="study-points math">{lesson.math.map((p, i) => <li key={i}>{rich(p)}</li>)}</ul>
            </div>
          )}

          {lesson.mistakes && (
            <div className="card-box study-card warn">
              <h4>Common mistakes</h4>
              <ul className="study-points">{lesson.mistakes.map((p, i) => <li key={i}>{rich(p)}</li>)}</ul>
            </div>
          )}

          {lesson.check && (
            <div className="card-box study-card quiz">
              <h4>Check yourself</h4>
              <p>{rich(lesson.check.q)}</p>
              {reveal
                ? <p className="study-answer">{rich(lesson.check.a)}</p>
                : <button className="btn" onClick={() => setReveal(true)}>Show answer</button>}
            </div>
          )}

          <div className="study-actions">
            {lesson.practice && (
              <button className="btn primary" onClick={() => practice(lesson.practice)}>▶ {lesson.practice.label}</button>
            )}
            <button className={`btn ${isDone ? 'done' : ''}`} onClick={() => toggleDone(cur)}>
              {isDone ? '✓ Completed' : 'Mark as complete'}
            </button>
          </div>

          <div className="study-nav">
            {prev ? <button className="btn" onClick={() => setCur(prev.id)}>← {prev.title}</button> : <span />}
            {next && (
              <button className="btn primary" onClick={() => { toggleDone(cur, true); setCur(next.id) }}>
                Next: {next.title} →
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
