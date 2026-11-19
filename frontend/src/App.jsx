import { useEffect, useState } from 'react'
import { api } from './api'
import { ErrorBox, Spinner } from './components/Common'
import Equity from './pages/Equity'
import Learn from './pages/Learn'
import Postflop from './pages/Postflop'
import Preflop from './pages/Preflop'
import Study from './pages/Study'
import TrainerHub from './pages/TrainerHub'

const TABS = [
  ['study', 'Study Guide'],
  ['preflop', 'Preflop'],
  ['postflop', 'Postflop Solver'],
  ['trainer', 'Trainer'],
  ['equity', 'Equity'],
  ['learn', 'Player Types & Method'],
]

export default function App() {
  const [meta, setMeta] = useState(null)
  const [err, setErr] = useState(null)
  const [tab, setTab] = useState(() => {
    try { return localStorage.getItem('pgto_tab') || 'preflop' } catch { return 'preflop' }
  })
  useEffect(() => {
    api.meta().then(setMeta).catch((e) => setErr(`Cannot reach the backend (${e.message}). Is it running on port 8000?`))
  }, [])
  useEffect(() => {
    try { localStorage.setItem('pgto_tab', tab) } catch { /* ignore */ }
  }, [tab])

  return (
    <div className="app">
      <header className="top">
        <div className="logo">♠ PokerGTO <span>local</span></div>
        <nav>
          {TABS.map(([k, l]) => (
            <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
          ))}
        </nav>
      </header>
      <ErrorBox error={err} />
      {!meta && !err && <Spinner text="Loading engine…" />}
      {meta && (
        <>
          <div style={{ display: tab === 'preflop' ? 'contents' : 'none' }}><Preflop meta={meta} /></div>
          <div style={{ display: tab === 'postflop' ? 'contents' : 'none' }}><Postflop meta={meta} /></div>
          <div style={{ display: tab === 'equity' ? 'contents' : 'none' }}><Equity /></div>
          {tab === 'trainer' && <TrainerHub meta={meta} />}
          {tab === 'learn' && <Learn meta={meta} />}
          {tab === 'study' && <Study meta={meta} setTab={setTab} />}
        </>
      )}
    </div>
  )
}
