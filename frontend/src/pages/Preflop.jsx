import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Collapsible, ErrorBox, Field, FreqBar, Segmented, Spinner } from '../components/Common'
import PokerTable from '../components/PokerTable'
import RangeGrid from '../components/RangeGrid'
import { HAND_COMBOS, HANDS, POSITIONS, actionColors, bb, comboToClass, pct } from '../constants'

const SCEN = [
  { value: 'rfi', label: 'Open (RFI)' },
  { value: 'vs_open', label: 'vs Open' },
  { value: 'vs_3bet', label: 'vs 3-Bet' },
  { value: 'vs_4bet', label: 'vs 4-Bet' },
  { value: 'vs_jam', label: 'vs All-in' },
  { value: 'vs_limp', label: 'vs Limpers' },
]

function limperChoices(hero, seats) {
  const hi = seats.indexOf(hero)
  if (hi < 0) return []
  return seats.slice(0, hi).filter((p) => p !== 'BB' && (p !== 'SB' || hero === 'BB'))
}

function validVillains(scenario, hero, seats) {
  const hi = seats.indexOf(hero)
  if (scenario === 'rfi' || hi < 0) return []
  if (scenario === 'vs_3bet') return hero === 'BB' ? [] : seats.slice(hi + 1)
  return seats.slice(0, hi)
}

function describe(res) {
  if (!res) return ''
  const a = res.actions.find((x) => x.key === 'agg')
  const sz = res.info?.size
  switch (res.scenario) {
    case 'rfi': return `${res.hero} first to act · everyone folded to you`
    case 'vs_open': return `${res.villain} opens · action on ${res.hero}`
    case 'vs_3bet': return `${res.hero} opened · ${res.villain} 3-bets · action on ${res.hero}`
    case 'vs_4bet': return `${res.villain} opened · ${res.hero} 3-bet · ${res.villain} 4-bets`
    case 'vs_jam': return `${res.villain} moves all-in for ${res.stack}bb · action on ${res.hero}`
    case 'vs_limp': {
      const l = (res.villain || '').split(',')
      return `${l.join(', ')} limp${l.length > 1 ? '' : 's'} · action on ${res.hero}`
    }
    default: return a ? `${a.label} ${sz}` : ''
  }
}

const RANGE_NAMES = {
  open: 'Open range', fourbet: '4-bet range', call_vs_3bet: 'Calls vs 3-bet', threebet: '3-bet range',
  fivebet_jam: '5-bet jams', call_vs_4bet: 'Calls vs 4-bet', call_vs_jam: 'Calls an all-in', jam: 'All-in range',
}
const rangeName = (k) => {
  const m = k.match(/^(limp_reraise|call_iso|limp)_(.+)$/)
  if (m) return `${m[2]} ${{ limp: 'limp range', call_iso: 'calls your iso-raise', limp_reraise: 'limp-reraises' }[m[1]]}`
  return RANGE_NAMES[k] || k
}

export default function Preflop({ meta }) {
  const [nPlayers, setNPlayers] = useState(6)
  const seats = meta.seats[String(nPlayers)]
  const [stack, setStack] = useState(100)
  const [ante, setAnte] = useState(0)
  const [scenario, setScenario] = useState('rfi')
  const [hero, setHero] = useState('BTN')
  const [villain, setVillain] = useState(null)
  const [profiles, setProfiles] = useState({})
  const [mode, setMode] = useState('gto')
  const [strength, setStrength] = useState(100)
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [hover, setHover] = useState(null)
  const [selected, setSelected] = useState(null)
  const [heroHand, setHeroHand] = useState('')
  const [showDiff, setShowDiff] = useState(false)

  const villains = validVillains(scenario, hero, seats)
  const [limpers, setLimpers] = useState(['UTG'])
  const limpChoices = limperChoices(hero, seats)
  const validLimpers = limpers.filter((l) => limpChoices.includes(l))
  useEffect(() => {
    if (scenario !== 'vs_limp') return
    if (validLimpers.length !== limpers.length || limpers.length === 0) {
      setLimpers(validLimpers.length ? validLimpers : limpChoices.slice(0, 1))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario, hero, nPlayers])
  useEffect(() => {
    if (!seats.includes(hero)) setHero(seats.includes('BTN') ? 'BTN' : seats[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nPlayers])
  useEffect(() => {
    if (scenario === 'rfi' || scenario === 'vs_limp') { if (villain !== null) setVillain(null); return }
    if (!villains.includes(villain)) setVillain(villains.length ? villains[villains.length - 1] : null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario, hero, nPlayers])

  useEffect(() => {
    if (!seats.includes(hero)) return
    const isLimp = scenario === 'vs_limp'
    if (isLimp && (validLimpers.length === 0 || validLimpers.length !== limpers.length)) {
      if (limpChoices.length === 0) { setErr('Nobody can limp in front of this seat — pick a later position.'); setRes(null) }
      return
    }
    if (!isLimp && scenario !== 'rfi' && !villain) { setRes(null); return }
    if (scenario === 'rfi' && hero === 'BB') { setErr('BB cannot open first in — pick another seat.'); setRes(null); return }
    if (!isLimp && scenario !== 'rfi' && !villains.includes(villain)) return
    const t = setTimeout(async () => {
      setLoading(true)
      setErr(null)
      try {
        const r = await api.preflop({
          scenario, hero, villain, stack: +stack, ante: +ante, villain_profiles: profiles,
          exploit_strength: strength / 100, n_players: nPlayers, limpers: isLimp ? limpers : [],
        })
        setRes(r)
      } catch (e) {
        setErr(e.message)
        setRes(null)
      } finally {
        setLoading(false)
      }
    }, 200)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario, hero, villain, stack, ante, profiles, strength, nPlayers, limpers])

  const exploitActive = Object.entries(profiles).some(([p, k]) => p !== hero && k !== 'gto')
  const view = mode === 'exploit' ? 'exploit' : 'gto'
  const colors = res ? actionColors(res.actions) : []

  const cells = useMemo(() => {
    if (!res) return null
    return res.hands.map((h) => {
      if (h.weight <= 0.001) return null
      const f = res.actions.map((a) => h[view][a.key])
      if (showDiff) {
        const g = res.actions.map((a) => h.gto[a.key])
        const d = f.reduce((s, x, k) => s + Math.abs(x - g[k]), 0) / 2
        return { w: d > 0.1 ? h.weight : h.weight * 0.15, f }
      }
      return { w: h.weight, f }
    })
  }, [res, view, showDiff])

  const heroClass = useMemo(() => {
    const t = heroHand.replace(/\s/g, '')
    if (t.length === 4) {
      try { return HANDS.indexOf(comboToClass(t[0].toUpperCase() + t[1].toLowerCase() + t[2].toUpperCase() + t[3].toLowerCase())) } catch { return -1 }
    }
    const k = HANDS.findIndex((h) => h.toLowerCase() === t.toLowerCase())
    return k
  }, [heroHand])

  const focus = hover ?? selected ?? (heroClass >= 0 ? heroClass : null)
  const fh = res && focus != null ? res.hands[focus] : null

  const statusOf = (p) => {
    if (!res) return ''
    const pi = seats.indexOf(p), hi = seats.indexOf(hero)
    if (p === hero) return ''
    if (scenario === 'vs_limp') return limpers.includes(p) ? 'limp' : pi < hi ? 'folded' : ''
    if (scenario === 'rfi') return pi < hi ? 'folded' : ''
    if (scenario === 'vs_3bet') return p === villain ? '3-bet' : 'folded'
    if (p === villain) return scenario === 'vs_open' ? 'open' : scenario === 'vs_4bet' ? '4-bet' : 'all-in'
    return pi < hi ? 'folded' : ''
  }

  return (
    <div className="page">
      <aside className="side">
        <Collapsible title="Spot">
          <Field label="Table size" hint="Fewer players = wider ranges: what matters is how many players are left to act behind you.">
            <select value={nPlayers} onChange={(e) => setNPlayers(+e.target.value)}>
              {Object.entries(meta.table_names).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Situation">
            <Segmented options={SCEN} value={scenario} onChange={setScenario} small />
          </Field>
          <div className="row2">
            <Field label="Hero position">
              <select value={hero} onChange={(e) => setHero(e.target.value)}>
                {seats.map((p) => <option key={p}>{p}</option>)}
              </select>
            </Field>
            {scenario === 'vs_limp' && (
              <Field label="Limpers (1-3)">
                <div className="chips">
                  {limpChoices.map((p) => {
                    const on = limpers.includes(p)
                    return (
                      <button key={p} className={on ? 'on' : ''}
                        onClick={() => {
                          if (on && limpers.length <= 1) return
                          if (!on && limpers.length >= 3) return
                          setLimpers(on ? limpers.filter((x) => x !== p) : seats.filter((x) => x === p || limpers.includes(x)))
                        }}>{p === 'SB' ? 'SB (completes)' : p}</button>
                    )
                  })}
                </div>
              </Field>
            )}
            {scenario !== 'rfi' && scenario !== 'vs_limp' && (
              <Field label={scenario === 'vs_3bet' ? '3-bettor' : scenario === 'vs_jam' ? 'All-in player' : scenario === 'vs_4bet' ? '4-bettor (opener)' : 'Opener'}>
                <select value={villain || ''} onChange={(e) => setVillain(e.target.value)}>
                  {villains.length === 0 && <option value="">—</option>}
                  {villains.map((p) => <option key={p}>{p}</option>)}
                </select>
              </Field>
            )}
          </div>
          <Field label={`Effective stack: ${stack} bb`} hint="Stack depth changes sizings, calling vs jamming, set-mining value and push/fold ranges (≤15bb).">
            <input type="range" min={8} max={200} step={1} value={stack} onChange={(e) => setStack(+e.target.value)} />
          </Field>
          <div className="row2">
            <Field label="Stack (bb)"><input type="number" value={stack} min={5} max={300} onChange={(e) => setStack(+e.target.value || 100)} /></Field>
            <Field label="Ante / player (bb)"><input type="number" value={ante} step={0.05} min={0} max={1} onChange={(e) => setAnte(+e.target.value || 0)} /></Field>
          </div>
          <Field label="My hand (optional)" hint="e.g. AhKd or AKs — highlights the hand and shows its strategy">
            <input value={heroHand} placeholder="e.g. AhQh or 76s" onChange={(e) => setHeroHand(e.target.value)} />
          </Field>
        </Collapsible>

        <Collapsible title="Players & tendencies">
          <PokerTable
            seats={seats}
            hero={hero}
            villain={villain}
            profiles={profiles}
            profileList={meta.profiles}
            onProfile={(p, k) => setProfiles({ ...profiles, [p]: k })}
            onSeatClick={(p) => setHero(p)}
            statusOf={statusOf}
            pot={res?.pot}
          />
          <div className="muted small">Set a player type for any opponent. Exploit mode shows how your optimal range shifts against them.</div>
        </Collapsible>

        <Collapsible title="Strategy mode">
          <Segmented
            options={[{ value: 'gto', label: 'GTO baseline' }, { value: 'exploit', label: 'Exploitative' }]}
            value={mode}
            onChange={setMode}
          />
          {mode === 'exploit' && (
            <>
              <Field label={`Exploit strength: ${strength}%`} hint="How hard to deviate toward the max-exploit strategy. Lower = safer vs players who adapt.">
                <input type="range" min={0} max={100} step={5} value={strength} onChange={(e) => setStrength(+e.target.value)} />
              </Field>
              {!exploitActive && <div className="hintbox">All opponents are set to GTO, so exploit = baseline. Set player types on the table above.</div>}
              <label className="check"><input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} /> Highlight hands that change vs GTO</label>
            </>
          )}
        </Collapsible>
      </aside>

      <main className="main">
        <div className="spot-head">
          <div>
            <h2>{res ? `${hero} · ${SCEN.find((s) => s.value === scenario).label}` : 'Preflop'} <span className="muted small">{meta.table_names[String(nPlayers)]}</span></h2>
            <div className="muted">{describe(res)} {res && `· ${res.stack}bb deep · pot ${res.pot}bb`}</div>
          </div>
          {loading && <Spinner text="calculating" />}
        </div>
        <ErrorBox error={err} />
        {res && (
          <div className="pf-layout">
            <div className="pf-grid">
              <div className="grid-head">
                <span className={`modetag ${view}`}>{view === 'gto' ? 'GTO baseline' : 'Exploitative'}</span>
                <span className="muted">Hero range: {pct(res.hero_range_pct)} of hands</span>
              </div>
              <RangeGrid cells={cells} colors={colors} onHover={setHover} onSelect={(i) => setSelected(i === selected ? null : i)} selected={selected} highlight={heroClass} />
              <FreqBar actions={res.actions} freqs={res.actions.map((a) => res.summary[view][a.key])} colors={colors} />
              {exploitActive && (
                <div className="compare-sum">
                  <span>GTO: {res.actions.map((a) => `${a.label} ${pct(res.summary.gto[a.key])}`).join(' · ')}</span>
                  <span>Exploit: {res.actions.map((a) => `${a.label} ${pct(res.summary.exploit[a.key])}`).join(' · ')}</span>
                </div>
              )}
            </div>
            <div className="pf-detail">
              <HandDetail res={res} h={fh} colors={colors} view={view} exploitActive={exploitActive} />
              <VillainRanges res={res} view={view} />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

function HandDetail({ res, h, colors, view, exploitActive }) {
  if (!h) return <div className="card-box muted">Hover or click a hand to see its frequencies, EVs and equity.</div>
  if (h.weight <= 0.001) return <div className="card-box"><h3>{h.hand}</h3><div className="muted">Not in hero's range at this node.</div></div>
  const best = (evs) => res.actions.reduce((b, a) => (evs[a.key] > evs[b.key] ? a : b), res.actions[0])
  const bx = best(h.ev_exploit), bg = best(h.ev_gto)
  return (
    <div className="card-box">
      <div className="hd-head">
        <h3>{h.hand}</h3>
        <span className="muted">{HAND_COMBOS[HANDS.indexOf(h.hand)]} combos{h.weight < 0.999 ? ` · ${pct(h.weight)} in range` : ''}</span>
      </div>
      <FreqBar actions={res.actions} freqs={res.actions.map((a) => h[view][a.key])} colors={colors} showLabels={false} height={20} />
      <table className="tbl">
        <thead>
          <tr><th>Action</th><th>GTO</th>{exploitActive && <th>Exploit</th>}<th title="EV vs GTO opponents (bb)">EV</th>{exploitActive && <th title="EV vs selected player types (bb)">EV vs pool</th>}</tr>
        </thead>
        <tbody>
          {res.actions.map((a, i) => (
            <tr key={a.key}>
              <td><i className="dot" style={{ background: colors[i] }} />{a.label}</td>
              <td>{pct(h.gto[a.key])}</td>
              {exploitActive && <td className={h.exploit[a.key] - h.gto[a.key] > 0.05 ? 'up' : h.exploit[a.key] - h.gto[a.key] < -0.05 ? 'down' : ''}>{pct(h.exploit[a.key])}</td>}
              <td>{bb(h.ev_gto[a.key])}</td>
              {exploitActive && <td>{bb(h.ev_exploit[a.key])}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="kv">
        {h.equity_gto != null && <span>Equity vs villain range: <b>{pct(h.equity_gto)}</b>{exploitActive && h.equity_exploit != null && <> (vs pool: <b>{pct(h.equity_exploit)}</b>)</>}</span>}
        <span>Highest model EV: <b>{bg.label}</b>{exploitActive && bx.key !== bg.key && <> → vs pool: <b>{bx.label}</b></>}</span>
      </div>
      <div className="muted small">EVs are in bb relative to folding, from the simplified preflop model (fold equity + realized equity). GTO frequencies are anchored to reference equilibrium widths.</div>
    </div>
  )
}

function VillainRanges({ res, view }) {
  const v = view === 'exploit' ? res.villains_exploit : res.villains_gto
  const [open, setOpen] = useState(null)
  if (!v) return null
  if (v.players) {
    const cols = ['#3faa6b', '#d94a3d']
    return (
      <div className="card-box">
        <h4>Players behind — defending ranges vs your open</h4>
        <div className="vr-list">
          {v.players.map((p) => (
            <div key={p.pos} className="vr-item">
              <div className="vr-title" onClick={() => setOpen(open === p.pos ? null : p.pos)}>
                <b>{p.pos}</b> <span className="muted">({p.profile})</span>
                <span>3-bet {pct(p.threebet_pct)} · call {pct(p.call_pct)}</span>
              </div>
              {open === p.pos && (
                <RangeGrid small cells={p.call.map((c, i) => (c + p.threebet[i] > 0.001 ? { w: Math.min(1, c + p.threebet[i]), f: [c / (c + p.threebet[i]), p.threebet[i] / (c + p.threebet[i])] } : null))} colors={cols} />
              )}
            </div>
          ))}
        </div>
        <div className="muted small">Click a seat to view its range. Green = call, red = 3-bet.</div>
      </div>
    )
  }
  return (
    <div className="card-box">
      <h4>Villain ranges ({res.villain})</h4>
      <div className="vr-grids">
        {Object.entries(v.ranges).map(([k, r]) => (
          <div key={k}>
            <div className="vr-title"><b>{rangeName(k)}</b> <span>{pct(r.pct)}</span></div>
            <RangeGrid small cells={r.weights.map((w) => (w > 0.001 ? { w, f: [1] } : null))} colors={['#d9a441']} />
          </div>
        ))}
      </div>
    </div>
  )
}
