# PokerGTO Local

A local GTO-Wizard-style study app for No-Limit Hold'em cash games, heads-up through full ring (2-9 players).
React (Vite) frontend + Python (FastAPI + NumPy) backend.

## Requirements

* Python 3.10+
* Node.js 18+ (with npm)

## Run

**Windows:** double-click **`start.bat`**. It creates the venv / installs packages on first run, starts both
servers and opens http://localhost:5173.

**macOS / Linux:** run `./start.sh`, then open http://localhost:5173 (Ctrl+C stops both servers).

```bash
git clone https://github.com/j1u/pokergto.git
cd pokergto
./start.sh
```

Manual:

```bash
# backend (port 8000)
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000

# frontend (port 5173, proxies /api to :8000)
cd frontend
npm install
npm run dev
```
If backend and frontend already built:

```bash
# backend (port 8000)
cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```
```bash
# frontend (port 5173, proxies /api to :8000)
cd frontend
npm run dev
```

Single-server mode: `npm --prefix frontend run build`, then just run the backend and open http://localhost:8000
(it serves `frontend/dist`).

The first backend start computes a 169x169 preflop equity matrix (~20 s) and caches it in `backend/data/`.

## Features

**Preflop**: open (RFI), vs open, vs 3-bet, vs 4-bet, vs all-in, vs limpers (1-3 limpers: fold / over-limp /
isolation raise, with limp ranges and tendencies by player type), for any table size (heads-up to 9-handed),
every position and any stack depth
(8-200bb, push/fold at 15bb and below), with antes.
* 13x13 strategy grid with mixed frequencies, EV per action, equity vs villain range.
* Give each seat a player type (Nit, TAG, LAG, Calling Station, Maniac, Fish, Weak-Tight).
  **Exploit mode** shows how your optimal range changes against them, with an exploit-strength slider and
  a highlight for the hands that change.
* View every villain's ranges (defend / 3-bet / 4-bet / call vs all-in).

**Postflop solver**: pick the preflop line (SRP / 3-bet / 4-bet pot, positions, stacks). Ranges are generated
by the preflop engine and are fully editable (paint grid or range text). Pick the board (flop, turn or river),
optionally your exact hand, and choose bet sizes, raise size, iterations.
* CFR+ solver; browse the tree (check / bet sizes / fold / call / raise) for both players.
* **Exact turn + river mode** (4-card boards): solves the turn plus all 48 river cards with full river
  betting trees (Discounted CFR, all rivers batched; ~20-60 s). Deal any river after a turn line ends and keep
  browsing, including your hand's river plan.
* Strategy grid, per-combo frequencies + EV + equity, strategy by hand category and draw.
* Range vs range equity, equity distribution curve, nut advantage, made-hand distributions, board texture.
* "My hand" tab: the full plan for your exact combo at every decision.
* Exploit mode: villain's strategy is node-locked with his player type's leaks (overfolds / overcalls /
  overbluffs / passivity) and your best response is solved, with the EV gain vs playing GTO.

**Study Guide**: a 36-lesson curriculum in 7 levels (foundations → preflop → ranges → postflop → turn & river →
game theory → exploits & mental game). Each lesson has key ideas, worked math, common mistakes, a self-check
question and a "practice" button that sets up the Trainer (or opens the right tool) for that topic. Progress is
saved in the browser.

**Trainer → Poker math**: a second Trainer mode with exact-answer drills: count outs (villain's hand shown, outs
counted by a hand evaluator), outs → equity, pot odds, call or fold vs an all-in, implied odds, MDF / bluff
break-even, combos & blockers, and river value-to-bluff ratios. Each answer comes with the worked calculation.

**Trainer → Strategy spots**: random quiz spots filtered by street (preflop / flop / turn / river), your positions, preflop
situations, pot types, stack depths and opponent type (GTO, or a player type to be graded on exploits).
* Postflop spots are real hands: the flop is solved and a likely line is followed, so turn/river ranges and pots
  are narrowed by the earlier action. Turn spots use the exact turn+river solver.
* Pick an action (keys 1-4); you get a verdict (Best / Correct mixed / Inaccuracy / Mistake / Blunder), the
  solver's frequencies and EVs, your EV loss, an explanation (incl. your equity vs the hands villain actually
  takes this line with) and your whole range's strategy. The next spot is solved in the background.
* Session stats: accuracy per street, average EV loss, streaks and a log of recent answers.

**Equity calculator**: hand or range vs hand or range on any board, equity vs each villain hand category.

## How accurate is it?

* Postflop: the current street is solved exactly for the chosen tree. The end of the street is valued by
  equity over all runouts, with a realization discount out of position. That makes **river solves true
  equilibria for the tree**, and turn solves (exact turn + river mode) true equilibria for the turn and river
  trees. Flop solves remain an approximation (no betting on later streets).
  Exploitability is reported for every solve.
* Preflop: an EV model (fold equity, blocker-aware fold frequencies, all-in equity, SPR/position/playability-
  dependent realization) with GTO frequencies anchored to reference equilibrium widths. It's a principled
  heuristic, not a full multiway preflop solve. No limping, multiway pots or ICM.

## Layout

```
backend/app/engine/
  evaluator.py   vectorized 7-card evaluator (~4M hands/s)
  equity.py      preflop 169x169 matrix, combo-vs-combo equity on boards
  ranges.py      range parsing/formatting, hand ranking, range construction
  profiles.py    player-type definitions
  preflop.py     preflop spot engine
  postflop.py    tree builder + single-street CFR+ solver + node locking
  postflop2.py   exact turn+river solver (batched over all rivers, DCFR)
  handclass.py   made-hand / draw classification, board texture
  trainer.py     quiz spot generator (line sampling, grading data, explanations)
backend/app/main.py   FastAPI routes
frontend/src/         React app (pages: Preflop, Postflop, Equity, Learn)
```
