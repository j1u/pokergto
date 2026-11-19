export default function Learn({ meta }) {
  const fmt = (v) => (v === 1 ? '—' : `${v > 1 ? '+' : ''}${Math.round((v - 1) * 100)}%`)
  const sh = (v) => (v === 0 ? '—' : `${v > 0 ? '+' : ''}${Math.round(v * 100)}%`)
  return (
    <div className="page single">
      <main className="main narrow">
        <h2>Player types</h2>
        <p className="muted">Each profile modifies (1) preflop action widths relative to the GTO reference and (2) postflop tendencies, applied as node-locks on top of the equilibrium strategy. Your exploitative strategy is the solver's best response to that locked opponent.</p>
        <div className="profile-grid">
          {meta.profiles.map((p) => (
            <div key={p.key} className="card-box">
              <h3>{p.name}</h3>
              <p className="muted">{p.description}</p>
              <div className="stats">{Object.entries(p.stats || {}).map(([k, v]) => <span key={k}><b>{k}</b> {v}</span>)}</div>
              <table className="tbl small">
                <tbody>
                  <tr><td>Open width</td><td>{fmt(p.open)}</td><td>Overfold postflop</td><td>{sh(p.fold)}</td></tr>
                  <tr><td>3-bet</td><td>{fmt(p.threebet)}</td><td>Extra betting</td><td>{sh(p.bet)}</td></tr>
                  <tr><td>Flat call</td><td>{fmt(p.call)}</td><td>Extra raising</td><td>{sh(p.raise)}</td></tr>
                  <tr><td>Continue vs 3-bet</td><td>{fmt(p.cont_vs_3bet)}</td><td>Calls all-ins</td><td>{fmt(p.call_vs_jam)}</td></tr>
                </tbody>
              </table>
            </div>
          ))}
        </div>

        <h2>How the engine works</h2>
        <div className="card-box prose">
          <h4>Preflop (heads-up to full ring, chip EV)</h4>
          <p>Table size works through the number of players left to act behind each seat (9-max UTG has 8 players behind and opens ~11%; 4-handed the first seat plays like a cutoff); heads-up the small blind is the button, opens ~80% and is in position postflop. Ranges come from an EV model over all 169 hand classes: fold equity against each opponent's (profile-adjusted) continuing ranges, all-in equity from a precomputed 169×169 equity matrix, card-removal (blocker) effects on fold frequencies, and postflop <i>equity realization</i> that depends on position, SPR and playability (suitedness, connectivity, set-mining). In GTO mode the per-action frequencies are anchored to reference equilibrium widths; the EV model decides which hands fill them. Exploit mode keeps the anchors but re-computes EVs against your chosen player types, so ranges move only where the opponent's leaks make it profitable. Facing an all-in is a pure chip-EV best response. Facing limpers is also a pure best response (limping is exploitable by nature): limpers get capped ranges and fold/call/limp-reraise tendencies by player type, isolation raises are sized open + 1bb per limper (+1bb from the blinds), and over-limping uses a multiway equity estimate with implied-odds credit for speculative hands.</p>
          <h4>Postflop</h4>
          <p>A vectorized CFR+ solver plays the current street's betting tree exactly (bet sizes you choose, one raise). When the street ends, the pot is split by equity over every runout (exact on turn/river, sampled on flop) with an equity-realization discount for the out-of-position player on earlier streets. On the river this is a true equilibrium for the chosen tree; on the flop it is a well-known approximation (no future-street betting). The exploitability number shows how far from equilibrium the result is.</p>
          <h4>Exact turn + river</h4>
          <p>With a 4-card board (and "Solve turn + river exactly" on), the solver plays the turn tree and then every one of the 48 possible river cards with its own full river betting tree — no equity approximation at all. All rivers are solved simultaneously as one batched computation using Discounted CFR; each traversal evaluates every river showdown in a single tensor operation. After a turn line ends you can deal any river card and keep walking the tree.</p>
          <h4>Limitations</h4>
          <p>This is a study tool, not a commercial solver: preflop is a heuristic model (not a full multiway equilibrium), limped/multiway pots use an equity approximation rather than a multiway solve, the postflop solver is heads-up only, ICM is ignored, and flop solves approximate the turn and river (turn solves are exact). Use it to understand <i>why</i> ranges shift — position, stack depth, board texture, range/nut advantage and opponent tendencies — rather than as exact frequencies.</p>
        </div>
      </main>
    </div>
  )
}
