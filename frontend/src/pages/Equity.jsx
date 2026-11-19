import { useState } from 'react'
import { api } from '../api'
import { EquityBar } from '../components/Charts'
import { Card, CardPicker, ErrorBox, Field, Spinner, randomCards } from '../components/Common'
import RangeEditor from '../components/RangeEditor'
import { pct } from '../constants'

export default function Equity() {
  const [hero, setHero] = useState('AhKh')
  const [villain, setVillain] = useState('TT+,AQs+,AKo')
  const [board, setBoard] = useState([])
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [editing, setEditing] = useState(null)

  const run = async () => {
    setLoading(true)
    setErr(null)
    try {
      setRes(await api.equity({ hero, villain, board: board.join('') }))
    } catch (e) {
      setErr(e.message)
      setRes(null)
    } finally {
      setLoading(false)
    }
  }

  const applyRange = async (w) => {
    const r = await api.formatRange(w)
    if (editing === 'hero') setHero(r.text)
    else setVillain(r.text)
    setEditing(null)
  }

  return (
    <div className="page">
      <aside className="side">
        <div className="panel-section"><div className="psb">
          <Field label="Hero — hand (AhKh) or range (TT+,AKs)">
            <div className="btnrow"><input value={hero} onChange={(e) => setHero(e.target.value)} /><button className="btn tiny ghost" onClick={() => setEditing('hero')}>Grid</button></div>
          </Field>
          <Field label="Villain — hand or range">
            <div className="btnrow"><input value={villain} onChange={(e) => setVillain(e.target.value)} /><button className="btn tiny ghost" onClick={() => setEditing('villain')}>Grid</button></div>
          </Field>
          <div className="board-row">
            <span className="flabel">Board</span>
            <button className="btn tiny ghost" onClick={() => setBoard(randomCards(3))}>Random flop</button>
            <button className="btn tiny ghost" onClick={() => setBoard([])}>Clear</button>
          </div>
          <div className="board-show">{[0, 1, 2, 3, 4].map((i) => <Card key={i} c={board[i]} size="sm" />)}</div>
          <CardPicker selected={board} onChange={setBoard} max={5} />
          <div className="solve-bar"><button className="btn primary big" onClick={run} disabled={loading}>Calculate equity</button></div>
        </div></div>
      </aside>
      <main className="main">
        <h2>Equity calculator</h2>
        <ErrorBox error={err} />
        {loading && <Spinner text="Enumerating runouts…" />}
        {res && (
          <>
            <EquityBar a={res.hero_equity} b={res.villain_equity} labelA="Hero" labelB="Villain" />
            <div className="muted small">{res.hero_combos} vs {res.villain_combos} combos · {res.exact ? 'exact enumeration' : 'Monte Carlo over sampled boards'}</div>
            <div className="eq-layout">
              {res.vs_categories && (
                <div className="card-box">
                  <h4>Hero equity vs each part of villain's range</h4>
                  <table className="tbl">
                    <thead><tr><th>Villain holds</th><th>Share</th><th>Hero equity</th></tr></thead>
                    <tbody>{res.vs_categories.map((c) => (
                      <tr key={c.name}><td>{c.name}</td><td>{pct(c.pct)}</td>
                        <td><div className="eqcell"><div style={{ width: `${c.hero_eq * 100}%` }} /><span>{pct(c.hero_eq)}</span></div></td></tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              {res.hero_hands.length > 1 && (
                <div className="card-box">
                  <h4>Hero combos by equity</h4>
                  <div className="scroll"><table className="tbl"><tbody>{res.hero_hands.map((h) => (
                    <tr key={h.combo}><td className="mono">{h.combo}</td><td><div className="eqcell"><div style={{ width: `${h.equity * 100}%` }} /><span>{pct(h.equity)}</span></div></td></tr>
                  ))}</tbody></table></div>
                </div>
              )}
            </div>
          </>
        )}
      </main>
      {editing && <RangeEditor title={`Edit ${editing} range`} onClose={() => setEditing(null)} onApply={applyRange} />}
    </div>
  )
}
