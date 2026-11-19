import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Card, Collapsible, ErrorBox, Field, Segmented, Spinner } from '../components/Common'
import RangeGrid from '../components/RangeGrid'
import { POSITIONS, actionColors, bb, pct } from '../constants'

const STREETS = [['preflop', 'Preflop'], ['flop', 'Flop'], ['turn', 'Turn'], ['river', 'River']]
const SCENARIOS = [['rfi', 'Open'], ['vs_open', 'vs Open'], ['vs_3bet', 'vs 3-Bet'], ['vs_4bet', 'vs 4-Bet'], ['vs_jam', 'vs All-in'], ['vs_limp', 'vs Limpers']]
const POT_TYPES = [['srp', 'Single raised'], ['3bp', '3-bet pot']]
const STACKS = [40, 60, 100, 150]

export const DEFAULTS = {
  streets: ['preflop', 'flop', 'turn', 'river'],
  positions: [...POSITIONS],
  scenarios: ['rfi', 'vs_open', 'vs_3bet'],
  pot_types: ['srp', '3bp'],
  stacks: [100],
  profile: 'gto',
  tricky: false,
  n_players: 6,
}
const EMPTY_STATS = { n: 0, best: 0, correct: 0, inacc: 0, mistake: 0, blunder: 0, evLoss: 0, streak: 0, bestStreak: 0, byStreet: {}, log: [] }

const VERDICTS = {
  best: { label: 'Best move', cls: 'v-best', icon: '★' },
  correct: { label: 'Correct (mixed)', cls: 'v-correct', icon: '✓' },
  inacc: { label: 'Inaccuracy', cls: 'v-inacc', icon: '?!' },
  mistake: { label: 'Mistake', cls: 'v-mistake', icon: '?' },
  blunder: { label: 'Blunder', cls: 'v-blunder', icon: '??' },
}

function load(key, dflt) {
  try { const v = JSON.parse(localStorage.getItem(key)); return v ? { ...dflt, ...v } : dflt } catch { return dflt }
}
function save(key, v) {
  try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* ignore */ }
}

const OPP_COLORS_POST = ['#b52a35', '#e8724a', '#e0b84a', '#4f9fd8', '#4a5368']

function oppColors(legend, street) {
  if (street !== 'preflop') return OPP_COLORS_POST
  const n = legend.length
  if (n === 1) return ['#b52a35']
  return legend.map((l, i) => (/^Fold/.test(l) ? '#4a5368' : i === 0 && n > 2 ? '#b52a35' : /3-bets|Jams|reraise/.test(l) ? '#b52a35' : '#3faa6b'))
}

function OpponentRange({ opps, idx, setIdx, street, hand }) {
  if (!opps || !opps.length) {
    return <div className="card-box"><h4>Opponent range</h4><div className="muted small">No opponent range for this spot.</div></div>
  }
  const o = opps[Math.min(idx, opps.length - 1)]
  const colors = oppColors(o.legend, street)
  const size = o.pct != null ? `${pct(o.pct)} of hands` : `≈${Math.round(o.combos)} combos`
  return (
    <div className="card-box">
      <div className="hd-head">
        <h4>{opps.length === 1 ? o.title : 'Opponent ranges'} <span className="muted small">{size}</span></h4>
      </div>
      {opps.length > 1 && (
        <div className="chips" style={{ marginBottom: 6 }}>
          {opps.map((x, i) => <button key={i} className={i === idx ? 'on' : ''} onClick={() => setIdx(i)}>{x.title}</button>)}
        </div>
      )}
      <RangeGrid small={false} cells={o.grid} colors={colors} />
      <div className="legend">
        {o.legend.map((l, i) => (o.summary[i] > 0.0005 || street === 'preflop')
          ? <span key={i}><i style={{ background: colors[i] }} />{l} {pct(o.summary[i])}</span> : null)}
      </div>
      <div className="muted small">
        {street === 'preflop'
          ? `The hands they hold at this point, split by how they respond if you raise. Cell height = share of that hand's combos in the range.`
          : `The hands they still hold after the line so far (your ${hand} blocks some combos), coloured by hand strength on this board.`}
      </div>
    </div>
  )
}

export function grade(freqs, evs, chosen, pot) {
  const best = evs.indexOf(Math.max(...evs))
  const top = freqs.indexOf(Math.max(...freqs))
  const loss = Math.max(0, evs[best] - evs[chosen])
  const lossPct = (loss / Math.max(pot, 0.5)) * 100
  const f = freqs[chosen]
  let v
  if (chosen === top || f >= 0.5) v = 'best'
  else if (f >= 0.2 || lossPct < 1.5) v = 'correct'
  else if (f >= 0.05 || lossPct < 4) v = 'inacc'
  else if (lossPct < 12) v = 'mistake'
  else v = 'blunder'
  return { verdict: v, loss, lossPct, best, top }
}

function Chips({ options, value, onChange, min = 1 }) {
  return (
    <div className="chips">
      {options.map(([k, l]) => {
        const on = value.includes(k)
        return (
          <button key={k} className={on ? 'on' : ''}
            onClick={() => {
              if (on && value.length <= min) return
              onChange(on ? value.filter((x) => x !== k) : [...value, k])
            }}>
            {l}
          </button>
        )
      })}
    </div>
  )
}

export default function Trainer({ meta, modeSwitch }) {
  const [cfg, setCfg] = useState(() => load('pgto_trainer_cfg', DEFAULTS))
  const [stats, setStats] = useState(() => load('pgto_trainer_stats', EMPTY_STATS))
  const [spot, setSpot] = useState(null)
  const [chosen, setChosen] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [gridView, setGridView] = useState('main')
  const [oppIdx, setOppIdx] = useState(0)
  useEffect(() => setOppIdx(0), [spot])
  const nextRef = useRef(null)
  const genRef = useRef(0)

  useEffect(() => save('pgto_trainer_cfg', cfg), [cfg])
  useEffect(() => save('pgto_trainer_stats', stats), [stats])

  const request = useCallback(() => {
    const p = api.trainerSpot(cfg)
    p.catch(() => {}) // handled by consumer
    return p
  }, [cfg])

  const showNext = useCallback(async () => {
    const gen = genRef.current
    setErr(null)
    setChosen(null)
    setGridView('main')
    let p = nextRef.current
    nextRef.current = null
    if (!p) p = request()
    setLoading(true)
    try {
      const s = await p
      if (gen !== genRef.current) return
      setSpot(s)
      nextRef.current = request() // prefetch while the user thinks
    } catch (e) {
      if (gen === genRef.current) { setErr(e.message); setSpot(null) }
    } finally {
      if (gen === genRef.current) setLoading(false)
    }
  }, [request])

  // new settings -> drop the prefetched spot and deal a fresh one
  useEffect(() => {
    genRef.current += 1
    nextRef.current = null
    showNext()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg])

  const answer = useCallback((i) => {
    if (!spot || chosen != null) return
    setChosen(i)
    const a = spot.answer
    const g = grade(a.freqs, a.evs, i, spot.pot)
    setStats((s) => {
      const ok = g.verdict === 'best' || g.verdict === 'correct'
      const bs = { ...(s.byStreet || {}) }
      const cur = bs[spot.street] || { n: 0, ok: 0 }
      bs[spot.street] = { n: cur.n + 1, ok: cur.ok + (ok ? 1 : 0) }
      const streak = ok ? s.streak + 1 : 0
      const entry = {
        t: Date.now(), street: spot.street, pos: spot.hero_pos, hand: spot.hand.join(''), board: spot.board.join(''),
        chose: spot.actions[i].label, best: spot.actions[g.top].label, verdict: g.verdict, loss: +g.loss.toFixed(2),
      }
      return {
        ...s, n: s.n + 1, [g.verdict]: (s[g.verdict] || 0) + 1, evLoss: s.evLoss + g.loss, streak,
        bestStreak: Math.max(s.bestStreak, streak), byStreet: bs, log: [entry, ...(s.log || [])].slice(0, 30),
      }
    })
  }, [spot, chosen])

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return
      if (!spot) return
      if (chosen == null) {
        const k = parseInt(e.key, 10)
        if (k >= 1 && k <= spot.actions.length) answer(k - 1)
      } else if (e.key === 'Enter' || e.key === ' ' || e.key.toLowerCase() === 'n') {
        e.preventDefault()
        showNext()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [spot, chosen, answer, showNext])

  const set = (k) => (v) => setCfg({ ...cfg, [k]: v })
  const tableSeats = meta.seats[String(cfg.n_players || 6)]
  const setTable = (n) => setCfg({ ...cfg, n_players: n, positions: [...meta.seats[String(n)]] })
  const colors = spot ? actionColors(spot.actions) : []
  const g = spot && chosen != null ? grade(spot.answer.freqs, spot.answer.evs, chosen, spot.pot) : null
  const acc = stats.n ? (stats.best + stats.correct) / stats.n : 0
  const profName = meta.profiles.find((p) => p.key === cfg.profile)?.name

  return (
    <div className="page">
      <aside className="side">
        {modeSwitch}
        <Collapsible title="What to practice">
          <Field label="Streets"><Chips options={STREETS} value={cfg.streets} onChange={set('streets')} /></Field>
          <Field label="Table size">
            <select value={cfg.n_players || 6} onChange={(e) => setTable(+e.target.value)}>
              {Object.entries(meta.table_names).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="My positions"><Chips options={tableSeats.map((p) => [p, p])} value={cfg.positions.filter((p) => tableSeats.includes(p))} onChange={set('positions')} /></Field>
          {cfg.streets.includes('preflop') && (
            <Field label="Preflop situations"><Chips options={SCENARIOS} value={cfg.scenarios} onChange={set('scenarios')} /></Field>
          )}
          {cfg.streets.some((s) => s !== 'preflop') && (
            <Field label="Postflop pot types"><Chips options={POT_TYPES} value={cfg.pot_types} onChange={set('pot_types')} /></Field>
          )}
          <Field label="Stack depths (bb)"><Chips options={STACKS.map((s) => [s, `${s}`])} value={cfg.stacks} onChange={set('stacks')} /></Field>
          <Field label="Opponent" hint="GTO grades you against equilibrium. A player type grades you against the best exploitative play vs that opponent.">
            <select value={cfg.profile} onChange={(e) => set('profile')(e.target.value)}>
              {meta.profiles.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="Hands dealt">
            <Segmented small value={cfg.tricky ? 'tricky' : 'all'} onChange={(v) => set('tricky')(v === 'tricky')}
              options={[{ value: 'all', label: 'Realistic mix' }, { value: 'tricky', label: 'Tricky spots' }]} />
          </Field>
          <div className="muted small">Turn spots are solved exactly (turn + every river) and take a few seconds; the next spot is prepared in the background while you answer.</div>
        </Collapsible>
        <Collapsible title="Session stats" right={<button className="btn tiny ghost" onClick={(e) => { e.stopPropagation(); setStats(EMPTY_STATS) }}>Reset</button>}>
          <div className="statgrid">
            <div><b>{stats.n}</b><span>answered</span></div>
            <div><b>{pct(acc, 0)}</b><span>accuracy</span></div>
            <div><b>{stats.n ? bb(stats.evLoss / stats.n) : '–'}</b><span>avg EV loss (bb)</span></div>
            <div><b>{stats.streak}</b><span>streak (best {stats.bestStreak})</span></div>
          </div>
          <div className="verdict-counts">
            {Object.entries(VERDICTS).map(([k, v]) => <span key={k} className={v.cls}>{v.icon} {stats[k] || 0}</span>)}
          </div>
          {Object.keys(stats.byStreet || {}).length > 0 && (
            <table className="tbl small">
              <tbody>
                {STREETS.filter(([k]) => stats.byStreet[k]).map(([k, l]) => (
                  <tr key={k}><td>{l}</td><td>{stats.byStreet[k].ok}/{stats.byStreet[k].n}</td><td>{pct(stats.byStreet[k].ok / stats.byStreet[k].n, 0)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {stats.log?.length > 0 && (
            <div className="trainer-log">
              {stats.log.slice(0, 12).map((e) => (
                <div key={e.t} className="logrow">
                  <span className={VERDICTS[e.verdict].cls}>{VERDICTS[e.verdict].icon}</span>
                  <span className="mono">{e.hand}</span>
                  <span className="muted">{e.pos} · {e.street}</span>
                  <span className="muted small">{e.chose}{e.verdict !== 'best' ? ` (best: ${e.best})` : ''}</span>
                </div>
              ))}
            </div>
          )}
        </Collapsible>
      </aside>

      <main className="main">
        <ErrorBox error={err} />
        {loading && !spot && <Spinner text="Dealing a spot…" />}
        {err && <button className="btn" onClick={showNext}>Try again</button>}
        {spot && (
          <div className={`trainer ${loading ? 'dim' : ''}`}>
            <div className="spot-chips">
              <span className="tag street">{spot.street.toUpperCase()}</span>
              <span className="tag">{meta.table_names[String(spot.n_players || 6)]}</span>
              <span className="tag">You: <b>{spot.hero_pos}</b>{spot.hero_side ? ` (${spot.hero_side})` : ''}</span>
              {spot.villain_pos && <span className="tag">Villain: <b>{spot.villain_pos}</b> · {meta.profiles.find((p) => p.key === spot.profile)?.name}</span>}
              <span className="tag">{spot.stack}bb behind</span>
              <span className="tag">Pot {spot.pot}bb</span>
              {loading && <Spinner text="next spot…" />}
            </div>

            <div className="felt-box">
              <div className="hero-hand">
                <span className="muted small">Your hand</span>
                <div>{spot.hand.map((c) => <Card key={c} c={c} />)}</div>
              </div>
              {spot.board.length > 0 && (
                <div className="hero-hand">
                  <span className="muted small">Board</span>
                  <div>{spot.board.map((c) => <Card key={c} c={c} />)}</div>
                </div>
              )}
            </div>

            <div className="history">
              {spot.history.map((h, i) => (
                <div key={i} className="hrow">
                  <b>{h.street}</b>
                  {h.cards && <span className="hcards">{h.cards.map((c) => <Card key={c} c={c} size="xs" />)}</span>}
                  <span>{h.text}</span>
                </div>
              ))}
            </div>

            <h3 className="question">{spot.question}{spot.to_call ? ` (${spot.to_call}bb to call)` : ''}</h3>
            <div className="answer-btns">
              {spot.actions.map((a, i) => {
                const isChosen = chosen === i
                const isTop = chosen != null && g.top === i
                return (
                  <button key={a.key + i} className={`ansbtn ${isChosen ? 'chosen' : ''} ${isTop ? 'top' : ''}`}
                    style={{ borderColor: colors[i], '--c': colors[i] }} disabled={chosen != null} onClick={() => answer(i)}>
                    <span className="kbd">{i + 1}</span>{a.label}
                    {chosen != null && <span className="ansfreq">{pct(spot.answer.freqs[i], 0)}</span>}
                  </button>
                )
              })}
            </div>

            {g && (
              <div className="result">
                <div className={`verdict ${VERDICTS[g.verdict].cls}`}>
                  <span className="vicon">{VERDICTS[g.verdict].icon}</span>
                  <div>
                    <b>{VERDICTS[g.verdict].label}</b>
                    <div className="small">
                      You chose <b>{spot.actions[chosen].label}</b> ({pct(spot.answer.freqs[chosen], 0)} solver frequency)
                      {g.loss > 0.005 ? ` · EV loss ${bb(g.loss)}bb (${g.lossPct.toFixed(1)}% pot)` : ' · no EV loss'}
                      {g.verdict !== 'best' && <> · solver's main play: <b>{spot.actions[g.top].label}</b></>}
                    </div>
                  </div>
                  <button className="btn primary" onClick={showNext} disabled={loading && !nextRef.current}>Next spot ↵</button>
                </div>

                <div className="result-stack">
                  <div className="card-box">
                    <h4>Solver answer{spot.answer.mode === 'exploit' ? ` (exploit vs ${profName})` : ' (GTO)'}</h4>
                    <table className="tbl">
                      <thead><tr><th>Action</th><th>Frequency</th>{spot.answer.mode === 'exploit' && <th>GTO</th>}<th>EV (bb)</th><th>vs best</th></tr></thead>
                      <tbody>
                        {spot.actions.map((a, i) => (
                          <tr key={i} className={i === chosen ? 'herorow' : ''}>
                            <td><i className="dot" style={{ background: colors[i] }} />{a.label}</td>
                            <td><div className="eqcell"><div style={{ width: `${spot.answer.freqs[i] * 100}%`, background: colors[i] }} /><span>{pct(spot.answer.freqs[i], 0)}</span></div></td>
                            {spot.answer.mode === 'exploit' && <td>{pct(spot.answer.gto_freqs[i], 0)}</td>}
                            <td>{bb(spot.answer.evs[i])}</td>
                            <td className={spot.answer.evs[g.best] - spot.answer.evs[i] > 0.01 ? 'down' : ''}>{i === g.best ? 'best' : `-${bb(spot.answer.evs[g.best] - spot.answer.evs[i])}`}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <h4 style={{ marginTop: 12 }}>Why</h4>
                    <ul className="explain">{spot.answer.explanation.map((l, i) => <li key={i}>{l}</li>)}</ul>
                    {spot.street !== 'preflop' && <div className="muted small">Postflop EV = expected share of the pot at the end of the street minus chips invested on it. Preflop EVs are relative to folding.</div>}
                  </div>
                  <div className="range-compare">
                  <div className="card-box">
                    <div className="hd-head">
                      <h4>Your range ({spot.hero_pos})</h4>
                      {spot.answer.mode === 'exploit' && (
                        <Segmented small value={gridView} onChange={setGridView} options={[{ value: 'main', label: 'Exploit' }, { value: 'gto', label: 'GTO' }]} />
                      )}
                    </div>
                    <RangeGrid small={false} cells={gridView === 'gto' ? spot.answer.grid_gto : spot.answer.grid} colors={colors} highlight={spot.answer.hand_index} />
                    <div className="legend">
                      {spot.actions.map((a, i) => <span key={i}><i style={{ background: colors[i] }} />{a.label} {pct(spot.answer.range_summary[i])}</span>)}
                    </div>
                    <div className="muted small">Dashed cell = your hand ({spot.hand_class}). Coloured by the solver's action.</div>
                  </div>
                  <OpponentRange opps={spot.answer.opponents} idx={oppIdx} setIdx={setOppIdx} street={spot.street} hand={spot.hand_class} />
                  </div>
                </div>
              </div>
            )}
            {chosen == null && <div className="muted small">Tip: press 1–{spot.actions.length} to answer, Enter for the next spot.</div>}
          </div>
        )}
      </main>
    </div>
  )
}
