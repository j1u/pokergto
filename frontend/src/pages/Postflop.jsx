import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { CompareBars, EquityBar, EquityCurve } from '../components/Charts'
import { Card, CardPicker, Collapsible, ErrorBox, Field, FreqBar, MiniBars, Segmented, Spinner, randomCards } from '../components/Common'
import RangeEditor from '../components/RangeEditor'
import RangeGrid from '../components/RangeGrid'
import { HAND_COMBOS, HANDS, POSITIONS, actionColors, bb, comboToClass, pct } from '../constants'

const POT_TYPES = [
  { value: 'srp', label: 'Single raised' },
  { value: '3bp', label: '3-bet pot' },
  { value: '4bp', label: '4-bet pot' },
]
const ORANGE = '#d9a441', BLUE = '#5b8def'

const parseSizes = (s) =>
  s.split(/[,\s]+/).map((x) => parseFloat(x)).filter((x) => x > 0 && x <= 500).map((x) => x / 100)

export default function Postflop({ meta }) {
  const [nPlayers, setNPlayers] = useState(6)
  const seats = meta.seats[String(nPlayers)]
  // preflop line
  const [potType, setPotType] = useState('srp')
  const [opener, setOpener] = useState('BTN')
  const [defender, setDefender] = useState('BB')
  const [heroSeat, setHeroSeat] = useState('BTN')
  const [stack, setStack] = useState(100)
  const [villainProfile, setVillainProfile] = useState('gto')
  const [preset, setPreset] = useState(null)
  const [ranges, setRanges] = useState(null) // {oop:{pos,weights}, ip:{pos,weights}}
  const [pot, setPot] = useState(5.5)
  const [eff, setEff] = useState(97.5)
  // board
  const [board, setBoard] = useState(['Ks', '7d', '2c'])
  const [heroHand, setHeroHand] = useState([])
  const [pickTarget, setPickTarget] = useState('board')
  // tree
  const [oopBets, setOopBets] = useState('33, 75')
  const [ipBets, setIpBets] = useState('33, 75')
  const [raiseMult, setRaiseMult] = useState(3)
  const [allowRaise, setAllowRaise] = useState(true)
  const [addAllin, setAddAllin] = useState(false)
  const [iters, setIters] = useState(300)
  const [exactRiver, setExactRiver] = useState(true)
  const [turnIters, setTurnIters] = useState(120)
  const [riverOop, setRiverOop] = useState('75')
  const [riverIp, setRiverIp] = useState('75')
  const [riverNodes, setRiverNodes] = useState({})
  const [riverHero, setRiverHero] = useState({})
  const [riverPick, setRiverPick] = useState(null)
  const [riverLoading, setRiverLoading] = useState(false)
  const [strength, setStrength] = useState(100)
  // results
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [path, setPath] = useState(['0'])
  const [view, setView] = useState('gto')
  const [hover, setHover] = useState(null)
  const [selected, setSelected] = useState(null)
  const [tab, setTab] = useState('strategy')
  const [editing, setEditing] = useState(null)

  const villainSeat = heroSeat === opener ? defender : opener
  const openerChoices = seats.slice(0, -1)
  const defenderChoices = seats.slice(Math.max(0, seats.indexOf(opener)) + 1)
  const seatsOk = seats.includes(opener) && defenderChoices.includes(defender)

  useEffect(() => {
    if (!seats.includes(opener)) { setOpener(seats.includes('BTN') ? 'BTN' : seats[0]); return }
    if (!defenderChoices.includes(defender)) { setDefender(defenderChoices[defenderChoices.length - 1]); return }
    if (heroSeat !== opener && heroSeat !== defender) setHeroSeat(opener)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opener, defender, nPlayers])

  const loadPreset = async () => {
    if (!seatsOk || (heroSeat !== opener && heroSeat !== defender)) return
    try {
      setErr(null)
      const p = await api.preset({
        pot_type: potType, opener, defender, stack: +stack, hero: heroSeat, n_players: nPlayers,
        profiles: { [villainSeat]: villainProfile },
      })
      setPreset(p)
      setRanges({ oop: p.oop, ip: p.ip })
      setPot(p.pot)
      setEff(p.stack)
    } catch (e) {
      setErr(e.message)
    }
  }
  useEffect(() => { loadPreset() /* eslint-disable-next-line */ }, [potType, opener, defender, heroSeat, stack, villainProfile, nPlayers])

  const heroSide = ranges ? (ranges.ip.pos === heroSeat ? 'IP' : 'OOP') : 'IP'

  const solve = async () => {
    if (!ranges) return
    if (board.length < 3) { setErr('Pick at least 3 board cards (flop).'); return }
    setLoading(true)
    setErr(null)
    try {
      const r = await api.solve({
        board: board.join(''),
        oop_range: ranges.oop.weights,
        ip_range: ranges.ip.weights,
        pot: +pot, stack: +eff,
        oop_bets: parseSizes(oopBets), ip_bets: parseSizes(ipBets),
        raise_mult: +raiseMult, allow_raise: allowRaise, add_allin: addAllin,
        iterations: board.length === 4 && exactRiver ? +turnIters : +iters,
        exact_river: exactRiver, river_oop_bets: parseSizes(riverOop), river_ip_bets: parseSizes(riverIp),
        hero: heroSide, villain_profile: villainProfile,
        hero_hand: heroHand.length === 2 ? heroHand.join('') : null,
        exploit_strength: strength / 100,
      })
      setRes(r)
      setPath(['0'])
      setSelected(null)
      setRiverNodes({})
      setRiverHero({})
      setRiverPick(null)
      if (!r.exploit_info) setView('gto')
    } catch (e) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }

  const nodes = useMemo(() => {
    const m = {}
    if (res) res.nodes.forEach((n) => (m[String(n.id)] = n))
    return { ...m, ...riverNodes }
  }, [res, riverNodes])
  const childKey = (n, c) => (c == null || typeof c === 'object' ? null : n._river ? `${c}@${n._river}` : String(c))

  const loadRiver = async (card) => {
    const pick = riverPick
    if (!pick || !res) return
    const rootKey = `${pick.root}@${card}`
    if (!nodes[rootKey]) {
      setRiverLoading(true)
      try {
        const rv = await api.river({ solve_id: res.solve_id, chance: pick.chance, river: card })
        const add = {}
        rv.nodes.forEach((n) => {
          add[`${n.id}@${card}`] = { ...n, _river: card, _texture: rv.texture, _req: rv.range_equity, _parent: n.id === rv.root ? pick.from : undefined }
        })
        setRiverNodes((prev) => ({ ...prev, ...add }))
        if (rv.hero_hand) {
          const hh = {}
          Object.entries(rv.hero_hand.nodes).forEach(([id, d]) => (hh[`${id}@${card}`] = d))
          setRiverHero((prev) => ({ ...prev, ...hh }))
        }
      } catch (e) {
        setErr(e.message)
        setRiverLoading(false)
        return
      }
      setRiverLoading(false)
    }
    setPath([...path, rootKey])
    setRiverPick(null)
  }
  const node = res ? nodes[path[path.length - 1]] : null
  const nv = node ? (view === 'exploit' && node.exploit ? node.exploit : node.gto) : null
  const colors = node ? actionColors(node.actions) : []
  const cells = nv ? nv.grid.map((g) => (g ? { w: g.w, f: g.f } : null)) : null
  const heroClass = heroHand.length === 2 ? HANDS.indexOf(comboToClass(heroHand.join(''))) : null
  const focus = hover ?? selected ?? heroClass
  const usedCards = [...board, ...heroHand]

  const ex = res?.exploit_info

  return (
    <div className="page">
      <aside className="side">
        <Collapsible title="Preflop action → ranges">
          <Field label="Table size">
            <select value={nPlayers} onChange={(e) => setNPlayers(+e.target.value)}>
              {Object.entries(meta.table_names).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Pot type"><Segmented options={POT_TYPES} value={potType} onChange={setPotType} small /></Field>
          <div className="row2">
            <Field label={potType === 'srp' ? 'Opener' : 'Opener (raiser)'}>
              <select value={opener} onChange={(e) => setOpener(e.target.value)}>{openerChoices.map((p) => <option key={p}>{p}</option>)}</select>
            </Field>
            <Field label={potType === 'srp' ? 'Caller' : potType === '3bp' ? '3-bettor' : '3-bettor (calls 4-bet)'}>
              <select value={defender} onChange={(e) => setDefender(e.target.value)}>{defenderChoices.map((p) => <option key={p}>{p}</option>)}</select>
            </Field>
          </div>
          <div className="row2">
            <Field label="I am">
              <Segmented options={[opener, defender]} value={heroSeat} onChange={setHeroSeat} small />
            </Field>
            <Field label="Start stack (bb)"><input type="number" value={stack} min={10} max={300} onChange={(e) => setStack(+e.target.value || 100)} /></Field>
          </div>
          <Field label={`Villain (${villainSeat}) player type`} hint="Shapes villain's preflop range and his postflop tendencies (node-locked in exploit mode).">
            <select value={villainProfile} onChange={(e) => setVillainProfile(e.target.value)}>
              {meta.profiles.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
            </select>
          </Field>
          {ranges && (
            <div className="ranges-mini">
              {['oop', 'ip'].map((side) => (
                <div key={side}>
                  <div className="vr-title">
                    <b>{side.toUpperCase()} · {ranges[side].pos}{ranges[side].pos === heroSeat ? ' (you)' : ''}</b>
                    <button className="btn tiny ghost" onClick={() => setEditing(side)}>Edit</button>
                  </div>
                  <RangeGrid small cells={ranges[side].weights.map((w) => (w > 0.001 ? { w, f: [1] } : null))} colors={[side === 'oop' ? BLUE : ORANGE]} />
                  <div className="muted small">{pct(ranges[side].weights.reduce((s, x, i) => s + x * HAND_COMBOS[i], 0) / 1326)} of hands</div>
                </div>
              ))}
            </div>
          )}
          <div className="row2">
            <Field label="Pot (bb)"><input type="number" value={pot} step={0.5} onChange={(e) => setPot(+e.target.value)} /></Field>
            <Field label="Eff. stack (bb)"><input type="number" value={eff} step={0.5} onChange={(e) => setEff(+e.target.value)} /></Field>
          </div>
          <div className="muted small">SPR {(eff / Math.max(pot, 0.01)).toFixed(1)} {preset && `· preset pot ${preset.pot} / stack ${preset.stack}`}</div>
        </Collapsible>

        <Collapsible title="Board & my hand">
          <div className="board-row">
            <Segmented small options={[{ value: 'board', label: 'Board' }, { value: 'hand', label: 'My hand' }]} value={pickTarget} onChange={setPickTarget} />
            <button className="btn tiny ghost" onClick={() => setBoard(randomCards(3, heroHand))}>Random flop</button>
            <button className="btn tiny ghost" onClick={() => (pickTarget === 'board' ? setBoard([]) : setHeroHand([]))}>Clear</button>
          </div>
          <div className="board-show">
            <span className="muted small">Board</span>
            {[0, 1, 2, 3, 4].map((i) => <Card key={i} c={board[i]} size="sm" onClick={() => setPickTarget('board')} />)}
            <span className="muted small" style={{ marginLeft: 8 }}>Hand</span>
            {[0, 1].map((i) => <Card key={i} c={heroHand[i]} size="sm" onClick={() => setPickTarget('hand')} />)}
          </div>
          {pickTarget === 'board' ? (
            <CardPicker selected={board} max={5} onChange={setBoard} disabled={heroHand} />
          ) : (
            <CardPicker selected={heroHand} max={2} onChange={setHeroHand} disabled={board} />
          )}
        </Collapsible>

        <Collapsible title="Bet sizes & solver" defaultOpen={false}>
          <div className="row2">
            <Field label="OOP bets (% pot)"><input value={oopBets} onChange={(e) => setOopBets(e.target.value)} /></Field>
            <Field label="IP bets (% pot)"><input value={ipBets} onChange={(e) => setIpBets(e.target.value)} /></Field>
          </div>
          <div className="row2">
            <Field label="Raise size (x bet)"><input type="number" step={0.5} min={2} value={raiseMult} onChange={(e) => setRaiseMult(+e.target.value)} /></Field>
            <Field label="Iterations"><input type="number" step={50} min={50} max={2000} value={iters} onChange={(e) => setIters(+e.target.value)} /></Field>
          </div>
          {board.length === 4 && (
            <div className="turnbox">
              <label className="check"><input type="checkbox" checked={exactRiver} onChange={(e) => setExactRiver(e.target.checked)} /> <b>Solve turn + river exactly</b></label>
              {exactRiver && (
                <>
                  <div className="row2">
                    <Field label="OOP river bets (%)"><input value={riverOop} onChange={(e) => setRiverOop(e.target.value)} /></Field>
                    <Field label="IP river bets (%)"><input value={riverIp} onChange={(e) => setRiverIp(e.target.value)} /></Field>
                  </div>
                  <Field label="Iterations (turn+river)" hint="~0.2-0.3 s per iteration for typical ranges; 100+ gets under ~1% pot exploitability">
                    <input type="number" step={10} min={30} max={1000} value={turnIters} onChange={(e) => setTurnIters(+e.target.value)} />
                  </Field>
                  <div className="muted small">The bet sizes above apply to the turn. Every river card is solved; after a turn line ends you can deal any river and keep browsing.</div>
                </>
              )}
            </div>
          )}
          <label className="check"><input type="checkbox" checked={allowRaise} onChange={(e) => setAllowRaise(e.target.checked)} /> Allow raises</label>
          <label className="check"><input type="checkbox" checked={addAllin} onChange={(e) => setAddAllin(e.target.checked)} /> Add all-in bet option</label>
        </Collapsible>

        {villainProfile !== 'gto' && (
          <Collapsible title="Exploit">
            <Field label={`Exploit strength: ${strength}%`} hint="Scales how strongly villain's leaks are assumed (node-lock size).">
              <input type="range" min={0} max={100} step={5} value={strength} onChange={(e) => setStrength(+e.target.value)} />
            </Field>
          </Collapsible>
        )}

        <div className="solve-bar">
          <button className="btn primary big" onClick={solve} disabled={loading || !ranges}>
            {loading ? 'Solving…' : 'Solve spot'}
          </button>
        </div>
      </aside>

      <main className="main">
        <ErrorBox error={err} />
        {loading && <Spinner text={board.length === 4 && exactRiver ? 'Solving the turn and all 48 rivers… (typically 20-60s)' : 'Running CFR+ solver…'} />}
        {!res && !loading && (
          <div className="empty-state">
            <h2>Postflop solver</h2>
            <p>Choose the preflop line (ranges are generated from the preflop engine — edit them freely), pick a board and optionally your exact hand, then hit <b>Solve spot</b>.</p>
            <p className="muted">The solver plays the current street exactly with CFR+ and values the end of the street by equity over all runouts. Pick a villain player type to see the exploitative adjustments side-by-side.</p>
          </div>
        )}
        {res && node && (
          <>
            <div className="spot-head">
              <div className="board-big">
                {res.board.map((c, i) => <Card key={i} c={['2','3','4','5','6','7','8','9','T','J','Q','K','A'][Math.floor(c / 4)] + 'cdhs'[c % 4]} />)}
                {node._river && <Card c={node._river} />}
                <div className="tags">
                  {res.mode === 'turn_river' && <span className="tag exact">Exact turn + river</span>}
                  {(node._texture || res.texture).tags.map((t) => <span key={t} className="tag">{t}</span>)}
                </div>
              </div>
              <div className="head-stats">
                <div><span className="muted">Pot</span> <b>{res.pot}</b></div>
                <div><span className="muted">Stack</span> <b>{res.stack}</b></div>
                <div><span className="muted">SPR</span> <b>{(res.stack / res.pot).toFixed(1)}</b></div>
                <div title="Nash distance: how much a perfect opponent could gain vs this solution (lower is better)"><span className="muted">Exploitability</span> <b>{res.exploitability_pct_pot}% pot</b></div>
                <div><span className="muted">Solve</span> <b>{res.elapsed}s</b></div>
              </div>
            </div>
            <EquityBar a={(node._req || res.range_equity).OOP} b={(node._req || res.range_equity).IP} labelA={`OOP ${ranges.oop.pos} equity`} labelB={`IP ${ranges.ip.pos}`} colorA={BLUE} colorB={ORANGE} />
            <div className="ev-row muted small">
              EV (share of pot): OOP {bb(res.ev.OOP)}bb · IP {bb(res.ev.IP)}bb
              {ex && (
                <span className="exgain">
                  {' '}· vs {meta.profiles.find((p) => p.key === villainProfile)?.name}: GTO strategy earns {bb(ex.hero_ev_gto_vs_profile)}bb, exploit earns <b>{bb(ex.hero_ev_exploit)}bb</b> (+{bb(ex.hero_ev_exploit - ex.hero_ev_gto_vs_profile)})
                </span>
              )}
            </div>

            <div className="treenav">
              <div className="crumbs">
                <button className={`crumb ${path.length === 1 ? 'on' : ''}`} onClick={() => { setPath(['0']); setRiverPick(null) }}>Start</button>
                {path.slice(1).map((id, k) => {
                  const n = nodes[id]
                  const last = n.path[n.path.length - 1]
                  return (
                    <button key={id} className={`crumb ${k === path.length - 2 ? 'on' : ''}`} onClick={() => { setPath(path.slice(0, k + 2)); setRiverPick(null) }}>
                      {last === 'River' ? <>River <Card c={n._river} size="xs" /></> : last}
                    </button>
                  )
                })}
              </div>
              <div className="actor">
                <span className={`badge ${node.is_hero ? 'hero' : 'villain'}`}>{node.player} {node.is_hero ? '(you)' : '(villain)'}</span>
                <span className="muted">to act · pot {node.pot}{node.to_call ? ` · to call ${node.to_call}` : ''}</span>
              </div>
              <div className="next-actions">
                {node.actions.map((a, i) => {
                  const c = node.children[i]
                  const isChance = c != null && typeof c === 'object'
                  return (
                    <button key={a.key + i} className={`actbtn ${isChance && riverPick?.chance === c.chance ? 'picking' : ''}`} style={{ borderColor: colors[i] }} disabled={c == null}
                      onClick={() => {
                        if (isChance) setRiverPick({ chance: c.chance, root: c.river_root, from: path[path.length - 1] })
                        else if (c != null) { setPath([...path, childKey(node, c)]); setRiverPick(null) }
                      }}
                      title={c == null ? 'Ends the hand' : isChance ? 'Deal a river card' : 'Go to this line'}>
                      <i style={{ background: colors[i] }} />{a.label} <b>{pct(nv.summary[i])}</b>{isChance && <span className="muted"> → river</span>}
                    </button>
                  )
                })}
              </div>
              {riverPick && (
                <div className="riverpick">
                  <span className="muted small">Deal the river:</span>
                  {riverLoading && <Spinner />}
                  <div className="rivercards">
                    {['s', 'h', 'd', 'c'].map((su) => (
                      <div key={su} className="row">
                        {'AKQJT98765432'.split('').map((r) => {
                          const card = r + su
                          const ok = res.rivers && res.rivers.includes(card)
                          return <button key={card} className={`pc suit-${su}`} disabled={!ok || riverLoading} onClick={() => loadRiver(card)}>{r}<small>{SUIT_SYM[su]}</small></button>
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="tabs">
              {[['strategy', 'Strategy'], ['equity', 'Ranges & equity'], ['combos', 'Combos'], ['hand', 'My hand']].map(([k, l]) => (
                <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
              ))}
              {ex && (
                <div style={{ marginLeft: 'auto' }}>
                  <Segmented small options={[{ value: 'gto', label: 'GTO' }, { value: 'exploit', label: 'Exploit' }]} value={view} onChange={setView} />
                </div>
              )}
            </div>

            {tab === 'strategy' && (
              <div className="pf-layout">
                <div className="pf-grid">
                  <div className="grid-head">
                    <span className={`modetag ${view}`}>{view === 'gto' ? 'GTO' : node.locked ? `Villain as ${villainProfile} (node-locked)` : 'Your exploitative response'}</span>
                    <span className="muted">{nv.range_combos} combos reach this node</span>
                  </div>
                  <RangeGrid cells={cells} colors={colors} onHover={setHover} onSelect={(i) => setSelected(i === selected ? null : i)} selected={selected} highlight={heroClass} />
                  <FreqBar actions={node.actions} freqs={nv.summary} colors={colors} />
                </div>
                <div className="pf-detail">
                  <ComboDetail nv={nv} node={node} cls={focus} colors={colors} heroHand={heroHand} />
                  <div className="card-box">
                    <h4>Strategy by hand category</h4>
                    <MiniBars rows={nv.categories.filter((c) => c.kind === 'made')} colors={colors} actions={node.actions} />
                    <h4 style={{ marginTop: 10 }}>Draws</h4>
                    <MiniBars rows={nv.categories.filter((c) => c.kind === 'draw')} colors={colors} actions={node.actions} />
                  </div>
                </div>
              </div>
            )}
            {tab === 'equity' && <EquityTab res={res} ranges={ranges} />}
            {tab === 'combos' && <CombosTable nv={nv} node={node} colors={colors} />}
            {tab === 'hand' && <HeroHandTab res={res} nodes={nodes} riverHero={riverHero} childKey={childKey} heroHand={heroHand} setPath={setPath} view={view} />}
          </>
        )}
      </main>
      {editing && ranges && (
        <RangeEditor
          title={`Edit ${editing.toUpperCase()} (${ranges[editing].pos}) range`}
          weights={ranges[editing].weights}
          onClose={() => setEditing(null)}
          onApply={(w) => { setRanges({ ...ranges, [editing]: { ...ranges[editing], weights: w } }); setEditing(null) }}
        />
      )}
    </div>
  )
}

function ComboDetail({ nv, node, cls, colors, heroHand }) {
  if (cls == null || cls < 0) return <div className="card-box muted">Hover a hand in the grid to see each combo's strategy, EV and equity.</div>
  const rows = nv.combos.filter((r) => r[7] === HANDS_INDEX_MAP[cls])
  const name = HANDS[cls]
  if (!rows.length) return <div className="card-box"><h3>{name}</h3><div className="muted">No combos of this hand reach this node.</div></div>
  const hh = heroHand.length === 2 ? heroHand.join('') : null
  return (
    <div className="card-box">
      <div className="hd-head"><h3>{name}</h3><span className="muted">{rows.length} combos</span></div>
      <table className="tbl combos">
        <thead>
          <tr><th>Combo</th><th>Hand</th><th>Eq</th>{node.actions.map((a, i) => <th key={i} style={{ color: colors[i] }}>{a.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const isHero = hh && sameCombo(r[0], hh)
            return (
              <tr key={r[0]} className={isHero ? 'herorow' : ''}>
                <td className="mono">{prettyCombo(r[0])}</td>
                <td className="small">{r[5]}{r[6] !== 'No draw' ? ` + ${r[6]}` : ''}</td>
                <td>{pct(r[4], 0)}</td>
                {r[2].map((f, i) => (
                  <td key={i}><div className="fcell"><span>{pct(f, 0)}</span><small>{bb(r[3][i], 2)}</small></div></td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="muted small">Each action cell: frequency and EV (bb, expected share of pot at street end minus chips invested this street).</div>
    </div>
  )
}

// backend class indices (row 7) use the same grid order as HANDS
const HANDS_INDEX_MAP = HANDS.map((_, i) => i)
const sameCombo = (a, b) => a === b || a === b.slice(2) + b.slice(0, 2)
const SUIT_SYM = { s: '♠', h: '♥', d: '♦', c: '♣' }
function prettyCombo(c) {
  return (
    <span>
      {[0, 2].map((k) => (
        <span key={k} className={`suit-${c[k + 1]}`}>{c[k]}{SUIT_SYM[c[k + 1]]}</span>
      ))}
    </span>
  )
}

function EquityTab({ res, ranges }) {
  const [o, i] = res.ranges
  const names = [`OOP ${ranges.oop.pos}`, `IP ${ranges.ip.pos}`]
  const cats = Array.from(new Set([...o.made.map((m) => m.name), ...i.made.map((m) => m.name)]))
  const getp = (arr, n) => arr.find((m) => m.name === n)?.pct || 0
  const bucketNames = ['0-10%', '10-20%', '20-30%', '30-40%', '40-50%', '50-60%', '60-70%', '70-80%', '80-90%', '90-100%']
  return (
    <div className="eq-layout">
      <div className="card-box">
        <h4>Equity distribution</h4>
        <EquityCurve series={[{ name: names[0], color: BLUE, data: o.equity_curve }, { name: names[1], color: ORANGE, data: i.equity_curve }]} />
        <div className="kv">
          <span>Range equity: {names[0]} <b>{pct(res.range_equity.OOP)}</b> · {names[1]} <b>{pct(res.range_equity.IP)}</b></span>
          <span>Nut advantage (≥80% equity): {names[0]} <b>{pct(o.nut_share)}</b> · {names[1]} <b>{pct(i.nut_share)}</b></span>
          <span>Combos on this board: {o.combos} vs {i.combos}</span>
        </div>
        <div className="muted small">Who has the range advantage (higher curve) and the nut advantage (more hands at the top) drives who bets, how often and how big.</div>
      </div>
      <div className="card-box">
        <h4>Made-hand distribution</h4>
        <CompareBars names={names} colors={[BLUE, ORANGE]} rows={cats.map((n) => ({ name: n, values: [getp(o.made, n), getp(i.made, n)] }))} />
      </div>
      <div className="card-box">
        <h4>Equity buckets</h4>
        <CompareBars names={names} colors={[BLUE, ORANGE]} rows={bucketNames.map((n, k) => ({ name: n, values: [o.equity_buckets[k], i.equity_buckets[k]] })).reverse()} />
      </div>
    </div>
  )
}

function CombosTable({ nv, node, colors }) {
  const [sort, setSort] = useState('eq')
  const [q, setQ] = useState('')
  const rows = useMemo(() => {
    let r = nv.combos.filter((x) => !q || x[0].toLowerCase().includes(q.toLowerCase()) || x[5].toLowerCase().includes(q.toLowerCase()) || HANDS[x[7]].toLowerCase() === q.toLowerCase())
    if (sort === 'eq') r = [...r].sort((a, b) => b[4] - a[4])
    else if (sort === 'ev') r = [...r].sort((a, b) => Math.max(...b[3]) - Math.max(...a[3]))
    else r = [...r].sort((a, b) => b[2][+sort] - a[2][+sort])
    return r.slice(0, 400)
  }, [nv, sort, q])
  return (
    <div className="card-box">
      <div className="btnrow">
        <input placeholder="filter: AK, AhKh, 'Top pair'…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 260 }} />
        <span className="muted small">sort:</span>
        <Segmented small value={sort} onChange={setSort} options={[{ value: 'eq', label: 'Equity' }, { value: 'ev', label: 'EV' }, ...node.actions.map((a, i) => ({ value: String(i), label: a.label }))]} />
      </div>
      <div className="scroll">
        <table className="tbl combos">
          <thead><tr><th>Combo</th><th>Weight</th><th>Hand</th><th>Draw</th><th>Equity</th>{node.actions.map((a, i) => <th key={i} style={{ color: colors[i] }}>{a.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r[0]}>
                <td className="mono">{prettyCombo(r[0])}</td><td>{pct(r[1], 0)}</td><td className="small">{r[5]}</td><td className="small">{r[6]}</td><td>{pct(r[4], 1)}</td>
                {r[2].map((f, i) => <td key={i}><div className="fcell"><span>{pct(f, 0)}</span><small>{bb(r[3][i])}</small></div></td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function HeroHandTab({ res, nodes, riverHero, childKey, heroHand, setPath, view }) {
  const h = res.hero_hand
  if (!h) return <div className="card-box muted">{heroHand.length === 2 ? 'Your hand is not available in this solve (blocked by the board?).' : 'Pick your exact hand in “Board & my hand” and re-solve to get a hand-specific plan.'}</div>
  // build parent map for path navigation
  const parent = {}
  Object.entries(nodes).forEach(([k, n]) => {
    n.children.forEach((c) => { const ck = childKey(n, c); if (ck) parent[ck] = k })
    if (n._parent != null) parent[k] = n._parent
  })
  const pathTo = (id) => { const p = [id]; while (parent[p[0]] != null) p.unshift(parent[p[0]]); return p }
  const all = { ...h.nodes, ...riverHero }
  const ids = Object.keys(all).filter((k) => nodes[k]).sort((a, b) => nodes[a].path.length - nodes[b].path.length || (a < b ? -1 : 1))
  return (
    <div className="card-box">
      <div className="hd-head">
        <h3>{prettyCombo(h.combo)}</h3>
        <span>{h.made}{h.draw !== 'No draw' ? ` + ${h.draw}` : ''} · equity vs villain range <b>{pct(h.equity)}</b></span>
      </div>
      <table className="tbl">
        <thead><tr><th>Line</th><th>Strategy ({view === 'exploit' ? 'exploit' : 'GTO'})</th><th>Best EV action</th><th></th></tr></thead>
        <tbody>
          {ids.map((id) => {
            const n = nodes[id]
            const d = all[id]
            const freqs = view === 'exploit' && d.exploit ? d.exploit : d.gto
            const evs = view === 'exploit' && d.ev_exploit ? d.ev_exploit : d.ev_gto
            const colors = actionColors(n.actions)
            const bi = evs.indexOf(Math.max(...evs))
            return (
              <tr key={id}>
                <td>{n.path.length ? n.path.map((x) => (x === 'River' ? `River ${n._river}` : x)).join(' → ') : 'You act first'}</td>
                <td style={{ minWidth: 260 }}><FreqBar actions={n.actions} freqs={freqs} colors={colors} showLabels={false} height={18} />
                  <div className="small muted">{n.actions.map((a, i) => (freqs[i] > 0.005 ? `${a.label} ${pct(freqs[i], 0)}` : null)).filter(Boolean).join(' · ')}</div></td>
                <td>{n.actions[bi].label} <span className="muted">({bb(evs[bi])}bb)</span></td>
                <td><button className="btn tiny ghost" onClick={() => setPath(pathTo(id))}>View</button></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
