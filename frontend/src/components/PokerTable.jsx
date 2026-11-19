function seatXY(i, n) {
  const step = 360 / n
  const deg = 270 + (i - (n / 2 - 2)) * step
  const r = (deg * Math.PI) / 180
  return [50 + 40 * Math.cos(r), 50 + 44 * Math.sin(r)]
}

export default function PokerTable({ seats, hero, villain, profiles, profileList, onProfile, onSeatClick, statusOf, pot }) {
  const n = seats.length
  return (
    <div className={`ptable ${n >= 8 ? 'crowded' : ''}`}>
      <div className="felt">
        <div className="pot">{pot != null ? `Pot ${pot} bb` : ''}</div>
      </div>
      {seats.map((p, i) => {
        const [x, y] = seatXY(i, n)
        const role = p === hero ? 'hero' : p === villain ? 'villain' : ''
        const st = statusOf ? statusOf(p) : ''
        return (
          <div key={p} className={`seat ${role} ${st === 'folded' ? 'folded' : ''}`} style={{ left: `${x}%`, top: `${y}%` }}>
            <div className="seat-top" onClick={() => onSeatClick && onSeatClick(p)} title="Click to make this seat Hero">
              <b>{p}</b>
              {role && <span className={`badge ${role}`}>{role === 'hero' ? 'HERO' : 'VILLAIN'}</span>}
              {st && st !== 'folded' && <span className="badge act">{st}</span>}
            </div>
            {p !== hero && (
              <select
                value={profiles[p] || 'gto'}
                onChange={(e) => onProfile(p, e.target.value)}
                title="Player type"
              >
                {profileList.map((pr) => (
                  <option key={pr.key} value={pr.key}>{pr.name}</option>
                ))}
              </select>
            )}
          </div>
        )
      })}
    </div>
  )
}
