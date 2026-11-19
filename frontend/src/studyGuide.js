// Study curriculum: ordered from first principles to advanced theory.
// Text supports **bold**. practice: { label, tab, trainer? } — `trainer` is a partial Trainer config.

const T = (label, trainer) => ({ label, tab: 'trainer', trainer })
const TAB = (label, tab) => ({ label, tab })
const M = (label, math) => ({ label, tab: 'trainer', math })

export const LEVELS = [
  {
    id: 'foundations',
    title: 'Level 1 · Foundations',
    blurb: 'The rules, the language and the handful of numbers everything else is built on.',
    lessons: [
      {
        id: 'rules',
        title: 'How a hand of No-Limit Hold\'em works',
        summary: 'Blinds, the four betting rounds and how the best five-card hand wins.',
        points: [
          'Each player gets two hole cards. Five community cards come out in three stages: the **flop** (3), the **turn** (1) and the **river** (1). Your hand is the best five cards from your two plus the five on the board.',
          'Before any cards, the **small blind** (SB) and **big blind** (BB) post forced bets. Everything in this app is measured in **big blinds (bb)**, so "100bb deep" means a stack of 100 big blinds.',
          'There is a betting round preflop, on the flop, on the turn and on the river. If nobody has bet yet on a street you can **check** or **bet** (put in the first chips). Once someone has bet, you can **fold**, **call** (match it) or **raise** (increase it). In no-limit you can bet any amount up to your whole stack.',
          'Preflop the big blind counts as the first bet, so the first player to put in more is **raising** ("opening"), and a re-raise is called a **3-bet** (blind = bet 1, open = bet 2, re-raise = bet 3).',
          'Preflop, action starts left of the BB and the blinds act last. After the flop, the player closest to the left of the button acts first and the **button acts last**.',
          'A hand ends when everyone but one player folds (they win without showing) or at **showdown** after the river.',
        ],
        mistakes: [
          'Thinking you must use both hole cards. You can use one or none ("playing the board").',
          'Forgetting that a raise must be at least the size of the previous bet or raise.',
        ],
        check: {
          q: 'You hold A♠K♠. The board is Q♠J♠4♦T♣2♥. What is your hand?',
          a: 'A straight: A-K-Q-J-T (ace high). Only two spades are on the board, so there is no flush.',
        },
      },
      {
        id: 'rankings',
        title: 'Hand rankings and the starting-hand grid',
        summary: 'What beats what, and how the 169 starting hands are laid out.',
        points: [
          'From strongest: **straight flush**, **four of a kind**, **full house**, **flush**, **straight**, **three of a kind** (a **set** when you hold a pocket pair, **trips** when one of the three is on the board), **two pair**, **one pair**, **high card**.',
          'Ties are broken by **kickers**: the highest remaining cards that are part of the best five.',
          'There are 1,326 two-card combinations, which group into **169 hand classes**: 13 pocket pairs, 78 suited hands and 78 offsuit hands.',
          'In the 13×13 grid used across this app, pairs run down the diagonal, **suited** hands ("s") sit above it and **offsuit** hands ("o") below it. AA is top-left, 22 bottom-right.',
          'Notation: "ATs+" means ATs, AJs, AQs, AKs. "77+" means 77 through AA.',
        ],
        mistakes: [
          'Overvaluing suitedness. Being suited adds only about 2–3% equity; a weak suited hand is still a weak hand.',
          'Overvaluing weak aces like A5o. When they make a pair of aces, the kicker is often beaten.',
        ],
        check: {
          q: 'Which is stronger: a flush or a full house? A straight or three of a kind?',
          a: 'A full house beats a flush, and a straight beats three of a kind.',
        },
        practice: TAB('Explore the grid on the Preflop tab', 'preflop'),
      },
      {
        id: 'position',
        title: 'Position: why the button makes money',
        summary: 'Acting last is an information advantage worth more than almost anything else.',
        points: [
          'At 6-max the seats in order are **UTG, HJ (hijack), CO (cutoff), BTN (button), SB, BB**. Full ring adds earlier seats (UTG+1, UTG+2, LJ).',
          '**In position (IP)** means you act after your opponent on every postflop street. You see what they do before you decide, you control the size of the pot, and you can take free cards.',
          'Because of that, the button is the most profitable seat and the blinds lose money in the long run for everybody. Good players lose less from the blinds, they don\'t win there.',
          'The **fewer players left to act behind you**, the less likely someone has a big hand, so you can open more hands from later seats.',
        ],
        mistakes: [
          'Playing the same hands from every seat.',
          'Calling raises out of position with hands that only play well in position (weak suited connectors, small pairs at shallow stacks).',
        ],
        check: {
          q: 'After the flop, who acts first: the SB or the BTN?',
          a: 'The SB. The button acts last on every postflop street, which is why it is the best seat.',
        },
        practice: T('Practice opening from every seat', { streets: ['preflop'], scenarios: ['rfi'] }),
      },
      {
        id: 'pot-odds',
        title: 'Pot odds: when a call pays',
        summary: 'The single most useful calculation in poker.',
        points: [
          'Pot odds compare what you must pay to what you can win. The equity you need to call is **call ÷ (pot after your call)**.',
          'Facing a bet of B into a pot of P, you need **B ÷ (P + 2B)** equity. A half-pot bet needs 25%, a pot-size bet needs 33%, a 2× pot overbet needs 40%.',
          'If your chance of winning is higher than the price, calling makes money on average, even though you will lose that particular hand most of the time.',
          'On earlier streets, also think about **implied odds** (extra money you win when you hit) and **reverse implied odds** (extra money you lose when you hit a second-best hand).',
        ],
        math: [
          'Pot is 10bb, villain bets 5bb. You must call 5 to win 20 (10 + 5 + your 5). Required equity = 5 ÷ 20 = **25%**.',
          'Pot is 10bb, villain bets 10bb. Call 10 to win 30 → **33%**.',
        ],
        mistakes: [
          'Comparing the call to the pot before the bet instead of the final pot.',
          'Counting implied odds when the opponent has no money behind or will never pay you off.',
        ],
        check: {
          q: 'The pot is 30bb and your opponent bets 20bb on the river. How often must you win to call?',
          a: '20 ÷ (30 + 20 + 20) = 20 ÷ 70 ≈ 29%.',
        },
        practice: M('Drill pot odds', ['potodds', 'callfold']),
      },
      {
        id: 'outs',
        title: 'Outs and the rule of 2 and 4',
        summary: 'A quick way to estimate your equity with a draw.',
        points: [
          'An **out** is a card that improves you to the likely best hand. Common draws: flush draw = 9 outs, open-ended straight draw (OESD) = 8, gutshot = 4, two overcards ≈ 6 (often less).',
          'On the flop with two cards to come, equity ≈ **outs × 4**. On the turn with one card to come, equity ≈ **outs × 2**.',
          'Discount "dirty" outs that also improve your opponent, for example a flush card that pairs the board or a straight card that completes a bigger flush.',
          'Compare your rough equity with your pot odds: 9 outs on the turn ≈ 18% vs a pot-size bet needing 33% is a fold unless implied odds make up the difference.',
        ],
        math: [
          'Flush draw on the turn: 9 outs × 2 ≈ 18% (exact: 9/46 = 19.6%).',
          'Flush draw plus OESD on the flop: 15 outs × 4 ≈ 60%, actually ≈ 54%. The ×4 rule overestimates above about 9 outs, so treat big draws as roughly a coin flip or better.',
        ],
        mistakes: [
          'Using ×4 on the flop when facing a bet that will be followed by another bet on the turn. You only get to see one card for this price.',
        ],
        check: {
          q: 'You have an OESD on the turn. Pot 20bb, bet 10bb. Call on direct odds?',
          a: '8 outs × 2 ≈ 16%, and you need 10 ÷ 40 = 25%. On direct odds it\'s a fold. You need implied odds (they pay you more when you hit) to call.',
        },
        practice: M('Drill outs, equity and implied odds', ['outs', 'equity', 'implied']),
      },
      {
        id: 'bankroll',
        title: 'Variance, bankroll and win rate',
        summary: 'Why good players have losing months, and how to survive them.',
        points: [
          'Results in poker are noisy. A solid player can lose for tens of thousands of hands. Judge your play by **decisions and expected value**, not by single sessions.',
          'Win rates are measured in **bb/100** (big blinds won per 100 hands). A good online cash-game win rate is a few bb/100; live games can be higher with more variance per hour.',
          'Keep a **bankroll** big enough to ride out downswings: a common guideline for cash games is 30–50 buy-ins for your stake, more for tournaments.',
          'Move down in stakes when your bankroll drops below your limit. That isn\'t failure, it\'s risk management.',
        ],
        mistakes: [
          'Results-oriented thinking: "I called and lost, so calling was wrong."',
          'Playing stakes where losing one buy-in changes how you play.',
        ],
        check: {
          q: 'You call an all-in with 80% equity and lose. Was it a mistake?',
          a: 'No. You make money every time you put chips in with more equity than the price. You will still lose 20% of the time.',
        },
      },
    ],
  },

  {
    id: 'preflop',
    title: 'Level 2 · Preflop fundamentals',
    blurb: 'Most of your mistakes are made before the flop. Fix these first; they compound through every street.',
    lessons: [
      {
        id: 'rfi',
        title: 'Opening ranges (raise first in)',
        summary: 'When everyone folds to you: raise or fold, and how wide from each seat.',
        points: [
          'When it folds to you, **raise or fold**. Open-limping (just calling the big blind) lets the blinds in cheaply and gives up the initiative.',
          'Typical 6-max widths at 100bb: **UTG ≈ 15–17%, HJ ≈ 19–21%, CO ≈ 26–28%, BTN ≈ 40–48%, SB ≈ 40–50%**. Full ring early seats are tighter (≈ 11–13%).',
          'Early seats open strong pairs, broadways and the best suited hands. As you move toward the button, add smaller pairs, suited aces, suited connectors and offsuit broadways.',
          'Use a **standard open size** (2–2.5bb from most seats, a bit bigger from the SB or in live games). Using one size for every hand keeps your hand hidden.',
        ],
        mistakes: [
          'Opening offsuit junk like K7o or J8o from early seats.',
          'Folding hands like 76s, A5s and 55 on the button. They are clear opens.',
        ],
        check: {
          q: 'Why can you open far wider on the button than UTG?',
          a: 'Only the two blinds are left to act, so you get folds much more often, and you will be in position postflop against whoever calls.',
        },
        practice: T('Practice opening ranges', { streets: ['preflop'], scenarios: ['rfi'] }),
      },
      {
        id: 'sizing-pre',
        title: 'Preflop bet sizing',
        summary: 'One size per spot, and why bigger hands don\'t get bigger raises.',
        points: [
          'Opens: about **2–2.5bb** online, more in passive live games. From the SB, 3bb is common because you will be out of position.',
          '**3-bets: about 3× the open in position, about 4× out of position.** Add roughly 1bb for each caller.',
          '**4-bets: about 2.2–2.5× the 3-bet**. Deep stacks need more room; at 40bb or less, 4-bets are often all-in.',
          'Against limpers, **isolate to about your open size plus 1bb per limper** (see the next lessons).',
          'Varying your size by hand strength is a tell that good players exploit. Against weak players who never adjust, raising bigger with your value hands can earn more, but that\'s an exploit, not the default.',
        ],
        check: {
          q: 'BTN opens to 2.5bb. You are in the BB. Roughly what size should your 3-bet be?',
          a: 'You are out of position, so about 4× the open: around 10–11bb.',
        },
        practice: TAB('See sizes on the Preflop tab', 'preflop'),
      },
      {
        id: 'vs-open',
        title: 'Facing an open: fold, call or 3-bet',
        summary: 'Your range against a raise depends on their seat and yours.',
        points: [
          'The earlier the opener\'s seat, the stronger their range, so **tighten up against early-position opens**.',
          'From most seats in front of the blinds, a **3-bet-or-fold** strategy is standard; flatting invites squeezes and multiway pots. On the button you can call more because you will have position.',
          'Good 3-bet hands are a **value** range (QQ+, AK, often JJ/AQ) plus **bluffs** that have blockers or play well when called (A5s–A2s, K9s, suited connectors).',
          'Hands that do well when called but poorly against a 3-bet (small pairs, suited connectors) prefer calling in position.',
        ],
        mistakes: [
          'Flat-calling a lot from the SB. You will be out of position against the opener and the BB.',
          'Only 3-betting premium hands. Good opponents simply fold to you.',
        ],
        check: {
          q: 'Why is A5s a common 3-bet bluff while A9o is not?',
          a: 'A5s blocks the opener\'s AA/AK, makes wheels, and flushes when suited, so it plays fine when called. A9o is dominated by much of the opener\'s calling range and makes few strong hands.',
        },
        practice: T('Practice facing opens', { streets: ['preflop'], scenarios: ['vs_open'] }),
      },
      {
        id: 'blinds',
        title: 'Defending the blinds',
        summary: 'The big blind gets a discount, so it defends wide; the small blind doesn\'t.',
        points: [
          'In the BB you already have 1bb invested and you close the action, so you get a great price. Against a 2.5bb button open you need only about 27% equity to call.',
          'That\'s why the BB defends **very wide against late opens (often 55–65%)**, including many suited and connected hands, but tighter against early-position opens.',
          'You will be out of position, so prefer hands that make strong pairs, draws and nut hands. Weak offsuit hands realize their equity poorly.',
          'The SB is the worst seat: you pay more and still play out of position against the opener with the BB behind you. Most solvers prefer **3-bet or fold** from the SB.',
        ],
        check: {
          q: 'BTN opens 2.5bb, SB folds. In the BB, how much equity do you need to call?',
          a: 'You call 1.5 to win 2.5 + 1.5 + 0.5 (SB) = 5.5. 1.5 ÷ 5.5 ≈ 27%. Then adjust for realization: out of position, you realize less of your equity than that.',
        },
        practice: T('Practice blind defense', { streets: ['preflop'], scenarios: ['vs_open'], positions: ['SB', 'BB'] }),
      },
      {
        id: 'limpers',
        title: 'Playing against limpers',
        summary: 'Limping is a weakness. Punish it with isolation raises.',
        points: [
          'Players who limp rarely have premium hands (they would raise them), so their **range is capped**: lots of medium and speculative hands.',
          '**Isolation raise** to about your open + 1bb per limper with hands that dominate a limping range: strong aces, broadways and pairs. You get heads-up, ideally in position, with the initiative.',
          '**Over-limp** with hands that like a cheap multiway pot (small pairs, suited aces, suited connectors) when stacks are deep. At shallow stacks implied odds disappear and over-limping should mostly stop.',
          'Adjust to the limper: against loose-passive fish, isolate wider and value-bet relentlessly; against nits who limp-reraise their big hands, isolate tighter.',
        ],
        check: {
          q: 'Two players limp in front of you on the button (6-max, 100bb). Roughly what should your iso-raise size be?',
          a: 'About 2.5bb + 1bb per limper = 4.5bb.',
        },
        practice: T('Practice vs limpers', { streets: ['preflop'], scenarios: ['vs_limp'] }),
      },
      {
        id: '3bet-pots',
        title: '3-bets, 4-bets and playing back',
        summary: 'Handling aggression after you open.',
        points: [
          'Facing a 3-bet, you will usually **fold a large part of your opening range**. Your price is decent, but you\'re up against a strong range, often out of position.',
          '**Call** with hands that play well in a bigger pot and aren\'t dominated: medium pairs, strong suited broadways, AQ.',
          '**4-bet** for value with the top (QQ+/AK, depending on positions) and bluff with blockers such as A5s or suited Ax. A 4-bet bluff is cheaper than it looks because many players fold.',
          'Position matters a lot: in position you can call 3-bets wider; out of position you should 4-bet or fold more often.',
        ],
        mistakes: [
          'Calling 3-bets with dominated hands like KJo and AJo out of position.',
          'Never 4-bet bluffing, which makes your 4-bets easy to read.',
        ],
        check: {
          q: 'Why does a hand with an ace make a better 4-bet bluff than KQs?',
          a: 'The ace makes it less likely the 3-bettor has AA or AK (blockers), so they fold more often and are less likely to 5-bet.',
        },
        practice: T('Practice vs 3-bets and 4-bets', { streets: ['preflop'], scenarios: ['vs_3bet', 'vs_4bet'] }),
      },
      {
        id: 'stack-depth',
        title: 'Stack depth and push/fold',
        summary: 'How shorter stacks change everything, down to all-in or fold.',
        points: [
          'The **stack-to-pot ratio (SPR)**, your effective stack divided by the pot, shapes postflop play. Low SPR favors top pairs and overpairs; high SPR favors hands that make the nuts (sets, flushes, straights).',
          'As stacks get shorter, speculative hands lose value (less implied odds) and high-card hands like ATo or KJ gain value.',
          'Around **15bb or less**, most decisions become **all-in or fold**. Ranges get wider than you might expect because of the blinds already in the pot and fold equity.',
          'When calling an all-in, it\'s pure pot odds against their jamming range. No future streets to worry about.',
        ],
        check: {
          q: 'Why does 55 drop in value at 25bb compared with 100bb?',
          a: 'It wins mainly by hitting a set (about 12%), which needs big implied odds. At 25bb there is not enough left to win to make that pay.',
        },
        practice: T('Practice push/fold and calling all-ins', { streets: ['preflop'], scenarios: ['vs_jam', 'rfi'], stacks: [15, 25] }),
      },
    ],
  },

  {
    id: 'ranges',
    title: 'Level 3 · Thinking in ranges',
    blurb: 'Stop asking "what does he have?" and start asking "what are all the hands he could have here?"',
    lessons: [
      {
        id: 'hand-vs-range',
        title: 'Hands vs ranges',
        summary: 'Opponents don\'t have one hand; they have a range of hands, narrowed by every action.',
        points: [
          'A **range** is every hand a player could hold given what they have done. A UTG open, a call on the flop and a check on the turn each remove hands from it.',
          'Your decision should be good **against the whole range**, not against the one hand you fear most.',
          'Think about **your own range** too: what would you have here, and how does this hand fit with the rest of it?',
          'In the Trainer, compare the two grids after each answer to see how both ranges have been shaped by the line.',
        ],
        check: {
          q: 'A tight UTG player opens, and you call on the button. The flop is 7♣6♣2♦ and they bet. Is it likely they have 76s?',
          a: 'Not very. Many tight players don\'t open 76s UTG, so it\'s a small part of their range. Their range is mostly overpairs and big cards.',
        },
        practice: T('Compare ranges in postflop spots', { streets: ['flop'] }),
      },
      {
        id: 'combos',
        title: 'Combinatorics and blockers',
        summary: 'Counting hands, and how your cards change what they can have.',
        points: [
          'Each **pocket pair** has 6 combinations, each **suited** hand 4, each **offsuit** hand 12. So AK has 16 combos (4 suited + 12 offsuit), and AA has 6.',
          'Cards you can see remove combos. With one ace on the board, AA has 3 combos left; if you also hold an ace, it has 1.',
          'A **blocker** is a card in your hand that reduces the combos your opponent can hold. Holding the A♥ on a three-heart board means they can\'t have the nut flush.',
          'Blockers matter most for **bluffs** (block their calling hands) and **bluff-catches** (block their value hands, don\'t block their bluffs).',
        ],
        math: [
          'Board K♠7♦2♣. Sets: 3 combos each of KK, 77, 22 = 9. AK: 4 aces × 3 kings = 12. So a top-pair hand like AK is more common than all sets combined.',
        ],
        check: {
          q: 'How many combos of AK remain if you hold A♠ and the flop has a K?',
          a: '3 remaining aces × 3 remaining kings = 9.',
        },
        practice: M('Drill combo counting', ['combos']),
      },
      {
        id: 'ev',
        title: 'Equity vs expected value (EV)',
        summary: 'Having the best hand is not the same as making money.',
        points: [
          '**Equity** is your share of the pot if all cards were dealt with no more betting. **EV** is the average amount you win or lose with an action, including all future betting.',
          'EV = Σ (probability of each outcome × what you win or lose). Folding is always 0 EV from that point.',
          'A bet can be +EV even with low equity (a bluff that folds out better hands) and a call can be −EV even with decent equity (if you will be bet off your equity later).',
          'The solver tables in this app show EV in big blinds for each action. The "vs best" column is how much you give up versus the top action.',
        ],
        math: [
          'Bluff 10bb into 15bb. If they fold 50%: EV = 0.5 × 15 − 0.5 × 10 = **+2.5bb** (assuming you never win when called).',
        ],
        check: {
          q: 'Your opponent folds 30% of the time to a pot-size bluff. Is the bluff profitable if you never win when called?',
          a: 'No. A pot-size bluff needs to work 50% of the time (bet ÷ (pot + bet) = 1/2). At 30%: 0.3 × P − 0.7 × P < 0.',
        },
      },
      {
        id: 'realization',
        title: 'Equity realization and playability',
        summary: 'Why some hands win more than their raw equity and others less.',
        points: [
          'Raw equity assumes you see every card for free. In reality you are often forced to fold before showdown. The share you actually capture is your **realized equity**.',
          'Hands **in position** and hands with good **playability** (suited, connected, pairs that can make sets) realize more. Offsuit, disconnected hands out of position realize less.',
          'That\'s why 76s can be a better call than A8o even with less raw equity: it makes strong hands and draws you can continue with, and folds cleanly when it misses.',
          'Postflop, top-pair-type hands with no improvement potential tend to under-realize when facing lots of pressure.',
        ],
        check: {
          q: 'Which realizes more equity against a button open: K4o in the BB, or K4s in the BB?',
          a: 'K4s. It can make flushes and flush draws that let it continue against bets, while K4o often has to fold when it misses.',
        },
      },
    ],
  },

  {
    id: 'postflop',
    title: 'Level 4 · Postflop fundamentals',
    blurb: 'How board texture, range strength and bet sizing fit together on the flop.',
    lessons: [
      {
        id: 'cbet',
        title: 'Continuation betting and board texture',
        summary: 'When the preflop raiser should bet the flop, and how often.',
        points: [
          'The preflop raiser usually has a stronger range, so they can **continuation bet (c-bet)** often, especially on boards that favor them.',
          '**Dry, high boards** (K♠7♦2♣, A♥8♣3♦) favor the raiser: they have more big pairs and overcards. Bet **small and often** (around 25–33% pot).',
          '**Wet, low, connected boards** (8♥7♥5♣, 6♠5♠4♦) hit the caller\'s range better (sets, two pairs, straights). Bet **less often**, and when you bet, use a bigger size.',
          'In position you can c-bet more than out of position; multiway you should c-bet much less.',
        ],
        mistakes: [
          'C-betting 100% of the time regardless of board.',
          'Using a big size on dry boards where a small bet achieves the same thing for less risk.',
        ],
        check: {
          q: 'You open from the CO and the BB calls. The flop is A♦7♣2♥. Small or large c-bet?',
          a: 'Small and frequent: you have many more aces and strong hands, and the BB rarely has a strong hand on this dry board.',
        },
        practice: T('Practice flop decisions', { streets: ['flop'], pot_types: ['srp'] }),
      },
      {
        id: 'advantage',
        title: 'Range advantage and nut advantage',
        summary: 'The two questions that decide how often and how big to bet.',
        points: [
          '**Range advantage**: whose range has more equity overall on this board? The player with more equity can bet more often.',
          '**Nut advantage**: who has more of the very strongest hands (sets, two pair, straights)? The player with the nut advantage can bet **bigger**, even overbet.',
          'They don\'t always go together. On 7♥6♥5♣ the preflop raiser may have slightly more equity (overpairs) but the caller has more straights and two pairs.',
          'The Postflop Solver\'s range-equity bar and the hand-category breakdown show both. Use them to explain the solver\'s bet frequency and size.',
        ],
        check: {
          q: 'On a K♠K♦4♣ board after a BTN open and BB call, who has the nut advantage?',
          a: 'Usually the BTN: it has more Kx (KQ, KJ, AK) and pocket pairs. The BB folds many Kx hands preflop or 3-bets the best ones.',
        },
        practice: TAB('Inspect ranges on the Postflop Solver', 'postflop'),
      },
      {
        id: 'sizing-post',
        title: 'Bet sizing: small vs big, merged vs polarized',
        summary: 'Your bet size should match what you want worse hands to do.',
        points: [
          'A **small bet** (25–40% pot) works with a wide, **merged** range: many medium-strength hands and some bluffs, often on boards where you have a range advantage.',
          'A **big bet** (66–150% pot) works with a **polarized** range: very strong hands and bluffs, with medium hands checking.',
          'Bigger bets need more fold equity to be profitable as bluffs, but they also earn more from your strong hands when called.',
          'Think about which worse hands call each size. If only better hands call a big bet, your bet is too big for value.',
        ],
        math: [
          'Bluff break-even fold frequency = bet ÷ (pot + bet). 33% pot → 25%; 75% pot → 43%; pot → 50%; 2× pot → 67%.',
        ],
        check: {
          q: 'You hold middle pair on a dry flop. Big bet or small bet or check?',
          a: 'Usually check or bet small. Big bets fold out the worse hands you beat and get called by the better ones.',
        },
      },
      {
        id: 'value',
        title: 'Value betting and thin value',
        summary: 'Most of your profit comes from getting paid by worse hands.',
        points: [
          'A **value bet** is a bet that is called by worse hands more often than by better hands.',
          'Before betting, list the hands that will call. If more than half of them are worse than yours, it is a value bet.',
          '**Thin value**: betting hands like second pair or top pair weak kicker on the river against players who call too much. Against calling stations this is where most profit comes from.',
          'Against tight, observant players, thin value bets get called mainly by better hands, so check more medium hands.',
        ],
        mistakes: [
          'Checking strong hands to "trap" against players who would have called a bet.',
          'Betting medium hands on the river where worse hands always fold.',
        ],
        check: {
          q: 'River: you hold top pair, good kicker. A passive opponent has called two streets. Bet or check?',
          a: 'Usually bet: passive players call with many weaker pairs. The exception is a river that completes obvious draws, where they now call mainly with hands that beat you.',
        },
      },
      {
        id: 'bluffing',
        title: 'Bluffing and semi-bluffing',
        summary: 'Picking the right hands to bluff with.',
        points: [
          'A pure **bluff** wins only when they fold. A **semi-bluff** (a draw) can also win when called by hitting.',
          'The best bluffs on the flop and turn are **semi-bluffs**: flush draws, straight draws, backdoor draws and overcards. They have equity when called.',
          'Good river bluffs usually have **no showdown value** (they lose if you check) and **blockers** to your opponent\'s calling hands.',
          'Hands with some showdown value (weak pairs) often prefer checking: they can win at showdown and make poor bluffs because you fold out only worse hands.',
        ],
        check: {
          q: 'On the river, which is the better bluff: a busted straight draw with no pair, or third pair?',
          a: 'The busted draw. It can never win at showdown, so betting is its only way to win. Third pair often wins by checking, and betting it only folds out worse hands.',
        },
      },
      {
        id: 'checkraise',
        title: 'Check-raising and playing out of position',
        summary: 'Fighting back when you don\'t have position.',
        points: [
          'Out of position, you can\'t control the pot as easily. **Checking much of your range** to the preflop raiser is normal.',
          'A **check-raise** works best with strong hands and strong draws on boards that suit your range (low and connected for the big blind).',
          'Check-raise **for value** with sets and two pairs; **as a semi-bluff** with combo draws, OESDs and flush draws.',
          'Avoid check-raising medium hands. They don\'t want to face a re-raise and they fold out the worse hands you beat.',
        ],
        check: {
          q: 'You defended the BB vs a button open. The flop is 8♥7♥4♣ and the button c-bets small. Which of these is a good check-raise: 9♥8♣, J♥T♥, A♣4♣?',
          a: 'J♥T♥ is a strong semi-bluff (flush draw + gutshot + overcards), and 9♥8♣ (top pair) is happy to just call. A♣4♣ (bottom pair) is usually just a call.',
        },
        practice: T('Practice flop decisions out of position', { streets: ['flop'], positions: ['SB', 'BB'] }),
      },
    ],
  },

  {
    id: 'turn-river',
    title: 'Level 5 · Turn and river play',
    blurb: 'The pots are bigger here, so mistakes cost more. This is where tough decisions get made.',
    lessons: [
      {
        id: 'barreling',
        title: 'Barreling: which turn cards to keep betting',
        summary: 'How the turn card shifts the ranges.',
        points: [
          'A **barrel** is a second (turn) or third (river) bet. Barrel when the turn card **improves your range** more than your opponent\'s.',
          'Good barrel cards for the preflop raiser: overcards (A or K) that hit your range, and cards that give you more draws.',
          'Bad barrel cards: low cards that complete draws or make two pair for the caller.',
          'Keep betting with your strong hands and best draws; give up with your weakest bluffs that picked up nothing.',
        ],
        check: {
          q: 'You c-bet K♠7♦2♣ as the BTN and the BB calls. Turn is the A♥. Good card to keep betting?',
          a: 'Yes. You have far more Ax (AK, AQ, AJ, AT) than the BB, who mostly called with Kx, 7x and draws.',
        },
        practice: T('Practice turn spots (solved exactly)', { streets: ['turn'] }),
      },
      {
        id: 'mdf',
        title: 'Minimum defense frequency (MDF)',
        summary: 'How often you must continue so bluffs don\'t print money.',
        points: [
          'If you fold too often, your opponent can bluff with any two cards. **MDF = pot ÷ (pot + bet)** is how often you must continue so their pure bluffs don\'t automatically profit.',
          'Half-pot bet → MDF 67%. Pot-size bet → 50%. 2× pot overbet → 33%.',
          'MDF is a guide, not a law. Against players who rarely bluff, you can fold more; against players who bluff too much, call more.',
          'On earlier streets, MDF applies less strictly because equity realization and future streets matter.',
        ],
        check: {
          q: 'River: pot 40bb, villain bets 20bb. What is your MDF?',
          a: '40 ÷ (40 + 20) = 67%. You need to continue with your best ⅔ of hands, unless you know they rarely bluff.',
        },
        practice: M('Drill MDF and bluff math', ['mdf']),
      },
      {
        id: 'river-balance',
        title: 'River value-to-bluff ratios',
        summary: 'How many bluffs belong in a balanced river betting range.',
        points: [
          'On the river there are no more cards, so hands are either winning or losing. A balanced bettor bluffs so the caller is **indifferent** between calling and folding.',
          'The bluff fraction of your betting range should equal the caller\'s pot odds: **bluffs = bet ÷ (pot + 2 × bet)**.',
          'Half-pot bet → 25% bluffs (1 bluff for every 3 value bets). Pot-size → 33% (1:2). 2× pot → 40%.',
          'In practice, most players under-bluff the river, so calling them light is a mistake, and most players over-call, so value-betting thinner wins more.',
        ],
        check: {
          q: 'You plan to bet pot on the river with 10 value combos. How many bluff combos make you balanced?',
          a: '33% bluffs → value:bluff = 2:1, so 5 bluff combos.',
        },
        practice: M('Drill value-to-bluff ratios', ['balance']),
      },
      {
        id: 'bluffcatch',
        title: 'Bluff-catching',
        summary: 'Calling with hands that beat only bluffs.',
        points: [
          'A **bluff-catcher** is a hand that beats nothing they bet for value but beats all their bluffs. Your call is only about **how often they are bluffing**.',
          'Prefer bluff-catchers that **block their value hands** and **don\'t block their bluffs**. Holding a card from the missed flush draw makes it less likely they are bluffing with that draw.',
          'Consider their line: does the story make sense? Does this player bluff rivers at all? Passive players who suddenly bet big usually have it.',
          'Use pot odds: if you need 29% and you believe they bluff more than 29% of the time, call.',
        ],
        check: {
          q: 'River: a flush draw missed. You hold a pair with the K of that suit. Is this a better or worse bluff-catcher than the same pair without it?',
          a: 'Worse. Your K blocks some of the busted flush draws they would bluff with, so they are bluffing less often.',
        },
        practice: T('Practice river decisions', { streets: ['river'] }),
      },
      {
        id: 'overbets',
        title: 'Overbets and polarization',
        summary: 'When betting more than the pot is correct.',
        points: [
          'An **overbet** (more than pot) is correct when you have a **strong nut advantage** and your opponent\'s range is **capped** (they would have raised their strongest hands earlier).',
          'Classic spots: the turn or river brings a card that completes your range\'s nuts but not theirs, or they checked twice showing weakness.',
          'Overbet ranges are very polarized: the nuts and bluffs that block their best calls. Medium hands check.',
          'Facing overbets, you must be willing to call with your best bluff-catchers. MDF against 2× pot is about 33%.',
        ],
        check: {
          q: 'Why are overbets rare on the flop but common on the turn and river?',
          a: 'On the flop, ranges are wide and uncapped. By the turn and river, ranges have been narrowed and one player\'s range is often capped, so the nut advantage becomes extreme.',
        },
      },
    ],
  },

  {
    id: 'theory',
    title: 'Level 6 · Game theory (GTO)',
    blurb: 'Why solvers play the way they do, and how to study with them without memorising charts.',
    lessons: [
      {
        id: 'gto-vs-exploit',
        title: 'GTO vs exploitative play',
        summary: 'Unbeatable defense vs maximum profit.',
        points: [
          'A **GTO (game-theory optimal)** strategy is an equilibrium: no opponent strategy can beat it. It is a defensive baseline.',
          'GTO does **not** maximize profit against weak players. It wins because their mistakes cost them, but it doesn\'t go out of its way to punish those mistakes.',
          '**Exploitative play** deviates from GTO to target a specific leak (folding too much, calling too much, never bluffing). It wins more against that opponent but becomes exploitable itself.',
          'The practical approach: know the GTO baseline, then **deviate when you have evidence of a leak**. This app\'s Exploit mode shows exactly that against each player type.',
        ],
        check: {
          q: 'Your opponent folds 80% of the time to a river bet. What is the exploit?',
          a: 'Bluff much more often. Any bet that needs less than 80% fold equity profits immediately, which is nearly every size up to 4× pot.',
        },
        practice: T('Practice against player types', { profile: 'station' }),
      },
      {
        id: 'indifference',
        title: 'Mixed strategies and indifference',
        summary: 'Why a solver plays the same hand two different ways.',
        points: [
          'At equilibrium, when a hand is played two ways, both actions have **(almost) the same EV**. The solver is **indifferent** between them.',
          'Mixing exists to keep ranges balanced: if you always bet a hand type, your check range becomes too weak.',
          'For a human, choosing either action with a mixed hand costs little. Focus on the **big** EV differences, not the 55/45 splits.',
          'That\'s why the Trainer counts any action played ≥ 50% as "Best" and lightly-played actions with tiny EV loss as "Correct".',
        ],
        check: {
          q: 'A solver checks AQ 60% and bets 40% on a flop. You bet. Did you make a mistake?',
          a: 'Basically no. The EV of each action is almost the same. Choose either and move on.',
        },
      },
      {
        id: 'solver-study',
        title: 'How to study with a solver',
        summary: 'Turning solver output into rules you can actually use.',
        points: [
          'Start with **frequent spots** (single-raised pots, BTN vs BB, CO vs BTN). They make up most of your hands.',
          'Don\'t memorize individual hands. Look for **patterns**: which board textures get bet small vs big, which hand categories check, how the opponent\'s range reacts.',
          'Ask **why**. Use the range-equity bar, the hand-category breakdown and the EV table to explain every major action.',
          'Then test yourself. Trainer reps with explanations build the instincts you need at the table, where you cannot run a solver.',
        ],
        practice: TAB('Open the Postflop Solver', 'postflop'),
      },
      {
        id: 'multiway',
        title: 'Multiway pots',
        summary: 'When three or more players see the flop, ranges and bluffs change.',
        points: [
          'With more opponents, someone is more likely to have a strong hand. **Bluff much less** and **value-bet stronger** hands.',
          'C-bet less often. One pair hands lose value; sets, straights, flushes and strong draws gain.',
          'Position becomes even more valuable, because you see several players act before you.',
          'Preflop, speculative hands that make the nuts (small pairs, suited aces, suited connectors) gain value in multiway pots when stacks are deep.',
        ],
        check: {
          q: 'Three players see a flop of K♥9♠4♦. You hold KJ. Should you play this the same as heads-up?',
          a: 'No. Top pair, weak kicker is stronger heads-up. Multiway, someone more often has K-Q, K-A, or two pair, so bet for value with care and avoid bloating the pot.',
        },
      },
    ],
  },

  {
    id: 'exploits',
    title: 'Level 7 · Exploits, mental game and improving',
    blurb: 'Turning knowledge into profit, and staying on your A-game.',
    lessons: [
      {
        id: 'player-types',
        title: 'Reading player types and adjusting',
        summary: 'A few simple stats tell you most of what you need.',
        points: [
          'Key stats: **VPIP** (how often they put money in preflop), **PFR** (how often they raise preflop), **3-bet %** and **fold to c-bet**.',
          '**Calling station** (high VPIP, low PFR): value-bet thinner and bigger, stop bluffing.',
          '**Nit** (low VPIP): fold to their aggression more, steal their blinds relentlessly, bluff them more when they show weakness.',
          '**Maniac / LAG**: call down lighter, trap more, let them bluff into you.',
          '**Over-folder**: bluff more and use bigger sizes. The Trainer\'s Opponent setting lets you practice each of these.',
        ],
        check: {
          q: 'A player has VPIP 45 / PFR 6. How do you play against them?',
          a: 'They are a loose-passive calling station. Value-bet relentlessly, including thin value; bluff rarely; isolate their limps.',
        },
        practice: TAB('Read the player types', 'learn'),
      },
      {
        id: 'live-exploits',
        title: 'Common population leaks',
        summary: 'What the average player gets wrong at low stakes.',
        points: [
          'Most players **under-bluff the river**, especially with big bets. Fold more of your bluff-catchers against large river bets from unknowns.',
          'Most players **call too much preflop and on the flop**, then **fold too much on the turn**. Barrel turns more; value-bet flops wider.',
          'Most players **don\'t 3-bet bluff enough**. Respect 3-bets from passive players.',
          'Limping, min-raising and sizing tells are common. Exploit them with isolation raises and by noting when bet sizes match hand strength.',
        ],
        check: {
          q: 'An unknown low-stakes player makes a pot-size raise on the river. What is the default?',
          a: 'Lean toward folding bluff-catchers. Large river raises are heavily weighted to value at low stakes.',
        },
      },
      {
        id: 'mental',
        title: 'Tilt, focus and decision quality',
        summary: 'Your edge disappears when emotions make your decisions.',
        points: [
          '**Tilt** is any emotional state that makes you play worse: after bad beats, after a big win, from boredom or fatigue.',
          'Have a **stop rule**: quit after a set loss, after a set number of hours, or when you notice tilt signs (playing faster, calling to "keep them honest").',
          'Focus on the quality of decisions. A good fold that turns out wrong is still a good fold.',
          'Sleep, exercise and short sessions all improve decision quality more than most strategy tweaks.',
        ],
      },
      {
        id: 'routine',
        title: 'Building a study routine',
        summary: 'Improve steadily with a mix of play, review and drills.',
        points: [
          'A good split is roughly **1 hour of study for every 2–3 hours played**.',
          'After each session, write down 2–3 hands where you were unsure. Review them in the Postflop Solver or Preflop tab.',
          'Drill one topic at a time in the Trainer (for example, BB defense for a week), and watch your accuracy and average EV loss improve.',
          'Track your results by stake and game type. Combine with hand-history review to find your own leaks, which are worth more than generic advice.',
        ],
        practice: T('Start a mixed drill', { streets: ['preflop', 'flop', 'turn', 'river'] }),
      },
    ],
  },
]

export const ALL_LESSONS = LEVELS.flatMap((lv) => lv.lessons.map((l) => ({ ...l, level: lv.id })))
