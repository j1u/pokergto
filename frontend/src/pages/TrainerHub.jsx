import { useEffect, useState } from 'react'
import { Segmented } from '../components/Common'
import MathTrainer from './MathTrainer'
import Trainer from './Trainer'

export default function TrainerHub({ meta }) {
  const [mode, setMode] = useState(() => {
    try { return (localStorage.getItem('pgto_trainer_mode') || '').replace(/"/g, '') === 'math' ? 'math' : 'spots' } catch { return 'spots' }
  })
  useEffect(() => {
    try { localStorage.setItem('pgto_trainer_mode', mode) } catch { /* ignore */ }
  }, [mode])
  const modeSwitch = (
    <div className="mode-switch">
      <Segmented value={mode} onChange={setMode}
        options={[{ value: 'spots', label: 'Strategy spots' }, { value: 'math', label: 'Poker math' }]} />
    </div>
  )
  return mode === 'math' ? <MathTrainer modeSwitch={modeSwitch} /> : <Trainer meta={meta} modeSwitch={modeSwitch} />
}
