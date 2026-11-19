// Poker-math drills: generated client-side with exact answers.
// Cards are ints 0..51: rank = c >> 2 (0 = deuce .. 12 = ace), suit = c & 3.

const R = '23456789TJQKA'
const S = 'shdc'
const SUIT_SYM = { s: '♠', h: '♥', d: '♦', c: '♣' }
export const cardStr = (c) => R[c >> 2] + S[c & 3]
const pretty = (c) => (R[c >> 2] === 'T' ? '10' : R[c >> 2]) + SUIT_SYM[S[c & 3]]
const rankName = (r) => ({ 12: 'Ace', 11: 'King', 10: 'Queen', 9: 'Jack', 8: 'Ten' }[r] || R[r])

// ------------------------------------------------------------------ hand evaluator (5–7 cards)
const CAT = ['High card', 'Pair', 'Two pair', 'Three of a kind', 'Straight', 'Flush', 'Full house', 'Four of a kind', 'Straight flush']

function straightHigh(mask) {
  for (let hi = 12; hi >= 4; hi--) {
    const need = 0b11111 << (hi - 4)
    if ((mask & need) === need) return hi
  }
  return (mask & 0b1000000001111) === 0b1000000001111 ? 3 : -1 // wheel A-2-3-4-5
}

const enc = (cat, ks) => ks.slice(0, 5).reduce((a, k) => a * 13 + k, cat) * 13 ** (5 - Math.min(5, ks.length))

export function evaluate(cards) {
  const cnt = new Array(13).fill(0)
  const suitMask = [0, 0, 0, 0]
  let mask = 0
  for (const c of cards) {
    cnt[c >> 2]++
    suitMask[c & 3] |= 1 << (c >> 2)
    mask |= 1 << (c >> 2)
  }
  for (let s = 0; s < 4; s++) {
    let n = 0
    for (let m = suitMask[s]; m; m &= m - 1) n++
    if (n >= 5) {
      const sh = straightHigh(suitMask[s])
      if (sh >= 0) return enc(8, [sh])
      const ks = []
      for (let r = 12; r >= 0 && ks.length < 5; r--) if (suitMask[s] >> r & 1) ks.push(r)
      return enc(5, ks)
    }
  }
  const byCount = (k) => { const o = []; for (let r = 12; r >= 0; r--) if (cnt[r] === k) o.push(r); return o }
  const quads = byCount(4), trips = byCount(3), pairs = byCount(2), singles = byCount(1)
  const desc = (excl) => { const o = []; for (let r = 12; r >= 0; r--) if (cnt[r] && !excl.includes(r)) o.push(r); return o }
  if (quads.length) return enc(7, [quads[0], desc([quads[0]])[0]])
  if (trips.length && (trips.length > 1 || pairs.length)) {
    const t = trips[0]
    const p = Math.max(trips[1] ?? -1, pairs[0] ?? -1)
    return enc(6, [t, p])
  }
  const sh = straightHigh(mask)
  if (sh >= 0) return enc(4, [sh])
  if (trips.length) return enc(3, [trips[0], ...desc([trips[0]]).slice(0, 2)])
  if (pairs.length >= 2) return enc(2, [pairs[0], pairs[1], desc([pairs[0], pairs[1]])[0]])
  if (pairs.length) return enc(1, [pairs[0], ...desc([pairs[0]]).slice(0, 3)])
  return enc(0, singles.slice(0, 5))
}
export const handName = (cards) => CAT[Math.floor(evaluate(cards) / 13 ** 5)]

// ------------------------------------------------------------------ helpers
const rnd = (n) => Math.floor(Math.random() * n)
const pick = (a) => a[rnd(a.length)]
const r1 = (x) => Math.round(x * 10) / 10
const half = (x) => Math.max(0.5, Math.round(x * 2) / 2)
const fmt = (x) => (Math.round(x * 10) / 10).toString()
const pctS = (x) => `${r1(100 * x)}%`
const comb2 = (n) => (n * (n - 1)) / 2

function deal(n, exclude = []) {
  const deck = []
  for (let c = 0; c < 52; c++) if (!exclude.includes(c)) deck.push(c)
  for (let i = deck.length - 1; i > 0; i--) { const j = rnd(i + 1); [deck[i], deck[j]] = [deck[j], deck[i]] }
  return deck.slice(0, n)
}

/** Next-card outs for hero vs a known villain hand. */
function countOuts(hero, vil, board) {
  const seen = [...hero, ...vil, ...board]
  const outs = [], ties = []
  for (let c = 0; c < 52; c++) {
    if (seen.includes(c)) continue
    const h = evaluate([...hero, ...board, c]), v = evaluate([...vil, ...board, c])
    if (h > v) outs.push(c)
    else if (h === v) ties.push(c)
  }
  return { outs, ties, unseen: 52 - seen.length }
}

function groupCards(cards) {
  const byRank = {}
  for (const c of cards) (byRank[c >> 2] ||= []).push(c)
  return Object.keys(byRank).sort((a, b) => b - a).map((r) => byRank[r].map(pretty).join(' ')).join(' · ')
}

/** Deal a spot where villain is ahead now and hero has min..max clean outs on the next card. */
function drawingSpot(boardN, min = 2, max = 20) {
  for (let t = 0; t < 4000; t++) {
    const d = deal(4 + boardN)
    const hero = d.slice(0, 2), vil = d.slice(2, 4), board = d.slice(4)
    if (evaluate([...hero, ...board]) >= evaluate([...vil, ...board])) continue
    const o = countOuts(hero, vil, board)
    if (o.outs.length >= min && o.outs.length <= max && o.ties.length <= 3) return { hero, vil, board, ...o }
  }
  return null
}

const cardsOut = (arr) => arr.map(cardStr)

// ------------------------------------------------------------------ drills
export const DRILLS = {
  outs: {
    label: 'Count outs',
    blurb: 'Villain shows their hand. How many cards give you the best hand on the next card?',
    gen() {
      const boardN = pick([3, 4])
      const s = drawingSpot(boardN)
      const n = s.outs.length
      return {
        hero: cardsOut(s.hero), villain: cardsOut(s.vil), board: cardsOut(s.board),
        lines: [`You have ${handName([...s.hero, ...s.board]).toLowerCase()}, villain has ${handName([...s.vil, ...s.board]).toLowerCase()}. Villain is ahead.`],
        question: `How many outs do you have on the ${boardN === 3 ? 'turn' : 'river'}?`,
        input: 'number', unit: 'outs', answer: n, tol: 0, close: 1,
        explain: [
          `**${n} outs**: ${groupCards(s.outs)}.`,
          s.ties.length ? `${s.ties.length} more card${s.ties.length > 1 ? 's' : ''} would give a split pot (${groupCards(s.ties)}). Those don't count as full outs.` : null,
          `Watch for cards that improve you but improve villain more. Those are not outs.`,
          `With ${s.unseen} unseen cards, that's ${pctS(n / s.unseen)} to hit on the next card${boardN === 3 ? `, or ${pctS(1 - (comb2(s.unseen - n) / comb2(s.unseen)))} by the river if you see both cards` : ''}.`,
        ].filter(Boolean),
      }
    },
  },

  equity: {
    label: 'Outs → equity',
    blurb: 'Convert outs into a hit percentage (rule of 2 and 4, or exact).',
    gen() {
      const n = 2 + rnd(14)
      const mode = pick(['flop2', 'flop1', 'turn'])
      const unseen = mode === 'turn' ? 46 : 47
      const exact = mode === 'flop2' ? 1 - comb2(47 - n) / comb2(47) : n / unseen
      const rule = mode === 'flop2' ? n * 4 : n * 2
      const what = { flop2: 'on the flop, seeing both the turn and river (e.g. you\'re all-in)', flop1: 'on the flop, seeing only the turn', turn: 'on the turn, seeing the river' }[mode]
      return {
        lines: [`You have **${n} outs** ${what}. Assume ${unseen} unseen cards.`],
        question: 'What is your chance to hit (in %)?',
        input: 'number', unit: '%', answer: r1(100 * exact), tol: 3, close: 6,
        explain: [
          mode === 'flop2'
            ? `Exact: 1 − (${47 - n}/47 × ${46 - n}/46) = **${pctS(exact)}**.`
            : `Exact: ${n} / ${unseen} = **${pctS(exact)}**.`,
          `Rule of ${mode === 'flop2' ? 4 : 2}: ${n} × ${mode === 'flop2' ? 4 : 2} ≈ ${rule}%.${mode === 'flop2' && n > 8 ? ` Above about 8 outs the ×4 rule overestimates. A common fix is outs × 4 − (outs − 8).` : ''}`,
          mode === 'flop1' ? 'Facing a flop bet, you usually only get one card for the price, so use ×2, not ×4.' : null,
        ].filter(Boolean),
      }
    },
  },

  potodds: {
    label: 'Pot odds',
    blurb: 'Facing a bet, what equity do you need to call?',
    gen() {
      const pot = pick([4, 6, 7.5, 9, 12, 15, 20, 24, 30, 36, 45, 60, 80, 100])
      const frac = pick([0.25, 0.33, 0.5, 0.66, 0.75, 1, 1.25, 1.5, 2])
      const bet = half(pot * frac)
      const need = bet / (pot + 2 * bet)
      return {
        lines: [`The pot is **${fmt(pot)}bb**. Villain bets **${fmt(bet)}bb** (${Math.round((100 * bet) / pot)}% pot).`],
        question: 'What equity do you need to call (in %)?',
        input: 'number', unit: '%', answer: r1(100 * need), tol: 2, close: 5,
        explain: [
          `You call ${fmt(bet)} to win a final pot of ${fmt(pot)} + ${fmt(bet)} + ${fmt(bet)} = ${fmt(pot + 2 * bet)}bb.`,
          `Required equity = ${fmt(bet)} / ${fmt(pot + 2 * bet)} = **${pctS(need)}** (odds of ${fmt((pot + bet) / bet)} : 1).`,
          'Shortcuts: ⅓ pot → 20%, ½ pot → 25%, ⅔ pot → 28.5%, pot → 33%, 2× pot → 40%.',
        ],
      }
    },
  },

  callfold: {
    label: 'Call or fold',
    blurb: 'Villain is all-in on the turn and shows their hand. Do the odds justify a call?',
    gen() {
      for (let t = 0; t < 200; t++) {
        const s = drawingSpot(4, 2, 18)
        const eq = (s.outs.length + s.ties.length / 2) / s.unseen
        const pot = pick([6, 8, 10, 12, 16, 20, 25, 30, 40, 50])
        const bet = half(pot * pick([0.33, 0.5, 0.66, 0.75, 1, 1.5]))
        const need = bet / (pot + 2 * bet)
        if (Math.abs(eq - need) < 0.035) continue
        const call = eq > need
        const ev = eq * (pot + bet) - (1 - eq) * bet
        return {
          hero: cardsOut(s.hero), villain: cardsOut(s.vil), board: cardsOut(s.board),
          lines: [`Pot **${fmt(pot)}bb**. Villain moves all-in for **${fmt(bet)}bb** on the turn (no more betting after this).`],
          question: 'Call or fold?',
          input: 'choice', choices: ['Call', 'Fold'], answer: call ? 0 : 1,
          explain: [
            `Outs: **${s.outs.length}** (${groupCards(s.outs)})${s.ties.length ? `, plus ${s.ties.length} split-pot card${s.ties.length > 1 ? 's' : ''}` : ''}. Equity = ${s.outs.length}${s.ties.length ? ` + ${s.ties.length}/2` : ''} / ${s.unseen} = **${pctS(eq)}**.`,
            `Price: ${fmt(bet)} / ${fmt(pot + 2 * bet)} = **${pctS(need)}** needed.`,
            `${call ? 'Call' : 'Fold'}: calling is worth ${ev >= 0 ? '+' : ''}${fmt(ev)}bb on average (folding is 0).`,
          ],
        }
      }
      return DRILLS.potodds.gen()
    },
  },

  implied: {
    label: 'Implied odds',
    blurb: 'The direct price is wrong, but how much more must you win when you hit?',
    gen() {
      for (let t = 0; t < 100; t++) {
        const n = pick([4, 4, 8, 8, 9, 9, 12, 15])
        const draw = { 4: 'a gutshot', 8: 'an open-ended straight draw', 9: 'a flush draw', 12: 'a flush draw + gutshot', 15: 'a flush draw + open-ender' }[n]
        const pot = pick([10, 12, 15, 20, 24, 30, 40, 50, 60])
        const bet = half(pot * pick([0.5, 0.66, 0.75, 1]))
        const e = n / 46
        const X = ((1 - e) * bet) / e - (pot + bet)
        if (X <= 1) continue
        return {
          lines: [
            `On the turn you have **${draw}** (${n} outs, 46 unseen cards). The pot is **${fmt(pot)}bb** and villain bets **${fmt(bet)}bb**.`,
            `You'll only call if you can win more on the river when you hit.`,
          ],
          question: 'How many extra bb must you win on the river (when you hit) to break even on the call?',
          input: 'number', unit: 'bb', answer: r1(X), tol: Math.max(1.5, 0.1 * X), close: Math.max(4, 0.25 * X),
          explain: [
            `Hit chance e = ${n}/46 = ${pctS(e)}. Direct price needs ${pctS(bet / (pot + 2 * bet))}, so the call loses on its own.`,
            `Break-even: e × (pot + bet + X) = (1 − e) × call → X = (1 − e) × ${fmt(bet)} / e − ${fmt(pot + bet)} = **${fmt(X)}bb**.`,
            `Shortcut: you need to win ${fmt(bet)} × ${fmt((46 - n) / n)} = ${fmt((bet * (46 - n)) / n)}bb in total when you hit (odds against hitting ${46 - n}:${n}). The pot already gives ${fmt(pot + bet)}.`,
            `Ask whether villain will really pay that much. If your draw is obvious or villain is short-stacked, implied odds are small.`,
          ],
        }
      }
      return DRILLS.potodds.gen()
    },
  },

  mdf: {
    label: 'MDF & bluffs',
    blurb: 'How often must you defend, and how often must a bluff work?',
    gen() {
      const pot = pick([6, 10, 12, 20, 30, 40, 60, 100])
      const frac = pick([0.33, 0.5, 0.66, 0.75, 1, 1.5, 2])
      const bet = half(pot * frac)
      const kind = pick(['mdf', 'bluff'])
      const mdf = pot / (pot + bet)
      const bluff = bet / (pot + bet)
      return {
        lines: [kind === 'mdf'
          ? `River. Pot **${fmt(pot)}bb**, villain bets **${fmt(bet)}bb**.`
          : `River. Pot **${fmt(pot)}bb**. You want to bluff **${fmt(bet)}bb** with a hand that can't win at showdown.`],
        question: kind === 'mdf'
          ? 'Minimum defense frequency: what share of your range must you continue with (in %)?'
          : 'How often must villain fold for the bluff to break even (in %)?',
        input: 'number', unit: '%', answer: r1(100 * (kind === 'mdf' ? mdf : bluff)), tol: 2, close: 5,
        explain: kind === 'mdf'
          ? [`MDF = pot / (pot + bet) = ${fmt(pot)} / ${fmt(pot + bet)} = **${pctS(mdf)}**.`,
             'If you fold more than this, villain profits by bluffing any two cards. Against players who rarely bluff, folding more is fine.']
          : [`Break-even fold % = bet / (pot + bet) = ${fmt(bet)} / ${fmt(pot + bet)} = **${pctS(bluff)}**.`,
             'It\'s the mirror of MDF: MDF + bluff break-even = 100%.'],
      }
    },
  },

  combos: {
    label: 'Combos & blockers',
    blurb: 'Count how many combinations of a hand villain can have, given the cards you can see.',
    gen() {
      const boardN = pick([3, 3, 4, 5])
      const d = deal(2 + boardN)
      const hero = d.slice(0, 2), board = d.slice(2)
      const seen = [...hero, ...board]
      const left = (r) => 4 - seen.filter((c) => c >> 2 === r).length
      const suitLeft = (r, s) => !seen.includes(r * 4 + s)
      const ranksSeen = [...new Set(seen.map((c) => c >> 2))]
      const types = ['pair', 'any', 'suited', 'offsuit']
      const type = pick(types)
      let q, ans, how
      if (type === 'pair') {
        const r = Math.random() < 0.75 ? pick(ranksSeen) : rnd(13)
        const n = left(r)
        q = `${R[r]}${R[r]} (pocket ${rankName(r).toLowerCase()}s)`
        ans = comb2(n)
        how = `${n} ${rankName(r).toLowerCase()}${n === 1 ? '' : 's'} left → ${n} × ${n - 1} / 2 = **${ans}**.`
      } else {
        let a = Math.random() < 0.7 ? pick(ranksSeen) : rnd(13)
        let b = rnd(13)
        while (b === a) b = rnd(13)
        if (b > a) [a, b] = [b, a]
        const na = left(a), nb = left(b)
        let suited = 0
        for (let s = 0; s < 4; s++) if (suitLeft(a, s) && suitLeft(b, s)) suited++
        const any = na * nb
        const name = R[a] + R[b]
        if (type === 'any') { q = `${name} (suited or offsuit)`; ans = any; how = `${na} × ${nb} = **${any}**.` }
        else if (type === 'suited') { q = `${name}s (suited only)`; ans = suited; how = `Suits where both cards are still available: **${suited}**.` }
        else { q = `${name}o (offsuit only)`; ans = any - suited; how = `All combos ${na} × ${nb} = ${any}, minus ${suited} suited = **${any - suited}**.` }
      }
      return {
        hero: cardsOut(hero), board: cardsOut(board),
        lines: ['Count only the cards you can see (your hand and the board).'],
        question: `How many combos of ${q} can villain hold?`,
        input: 'number', unit: 'combos', answer: ans, tol: 0, close: 1,
        explain: [how, 'Unblocked: pairs = 6, suited = 4, offsuit = 12 (16 for any non-pair). Each card you see of that rank removes combos.'],
      }
    },
  },

  balance: {
    label: 'River value : bluff',
    blurb: 'How many bluffs make a river betting range balanced?',
    gen() {
      const pot = pick([10, 20, 30, 40, 60, 100])
      const frac = pick([0.33, 0.5, 0.75, 1, 1.5, 2])
      const bet = half(pot * frac)
      const V = pick([6, 8, 10, 12, 15, 18, 20, 24, 30])
      const f = bet / (pot + 2 * bet)
      const B = (V * bet) / (pot + bet)
      return {
        lines: [`River. Pot **${fmt(pot)}bb**. You will bet **${fmt(bet)}bb** with **${V} value combos**.`],
        question: 'How many bluff combos make villain indifferent between calling and folding?',
        input: 'number', unit: 'combos', answer: r1(B), tol: Math.max(0.6, 0.08 * B), close: Math.max(1.5, 0.2 * B),
        explain: [
          `Villain's pot odds: ${fmt(bet)} / ${fmt(pot + 2 * bet)} = ${pctS(f)}. Your betting range should be ${pctS(f)} bluffs.`,
          `Bluffs = value × bet / (pot + bet) = ${V} × ${fmt(bet)} / ${fmt(pot + bet)} = **${fmt(B)}**.`,
          'Bigger bets allow more bluffs: ½ pot → 1 bluff per 3 value, pot → 1 per 2, 2× pot → 2 per 3.',
        ],
      }
    },
  },
}

export function gradeMath(drill, value) {
  if (drill.input === 'choice') return value === drill.answer ? 'right' : 'wrong'
  const err = Math.abs(value - drill.answer)
  if (err <= drill.tol + 1e-9) return 'right'
  if (err <= drill.close + 1e-9) return 'close'
  return 'wrong'
}
