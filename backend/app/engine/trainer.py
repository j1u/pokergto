"""Trainer: random quiz spots with solver answers.

Preflop spots come straight from the preflop engine. Postflop spots are built as real hands:
preflop ranges -> flop solve -> follow a sampled line (ranges narrowed by each player's strategy)
-> turn (-> river), and the quiz is asked at hero's first decision on the target street.
"""
from __future__ import annotations

import random

import numpy as np

from . import postflop, postflop2, preflop
from .cards import ALL_COMBOS, CLASS_COMBOS, CLASS_NCOMBOS, HAND_CLASSES, card_to_str, class_weights_to_combo, combo_str
from .equity import combo_matrix
from .postflop import Solver, _prep_range, build_tree
from .profiles import get_profile

STREETS = ["preflop", "flop", "turn", "river"]
POS = preflop.POS

PROFILE_LEAKS = {
    "nit": "folds too often and rarely bluffs, so bluffs gain and thin value bets lose",
    "tag": "is solid but folds a little too much to aggression",
    "lag": "bets and raises too much and calls a bit wider, so bluff-catch and trap more",
    "station": "calls far too much, so value bet thinner and bluff much less",
    "maniac": "bets, raises and bluffs constantly, so call down lighter and let him bluff",
    "fish": "plays fit-or-fold and rarely raises, so steal more and respect his aggression",
    "overfolder": "folds too much to bets and raises, so bluff more often",
}


# ------------------------------------------------------------------ helpers
def _verb(label: str) -> str:
    if label == "Check":
        return "checks"
    if label == "Fold":
        return "folds"
    w, _, amt = label.partition(" ")
    return {"Bet": f"bets {amt}", "Call": "calls", "Raise": f"raises to {amt}", "All-in": f"goes all-in ({amt})"}.get(w, label)


def _describe_line(path: list[str], oop: str, ip: str, pot: float) -> str:
    out = []
    for i, a in enumerate(path):
        who = oop if i % 2 == 0 else ip
        v = _verb(a)
        if a.startswith("Bet"):
            amt = float(a.split()[1])
            v += f" ({round(100 * amt / pot)}% pot)"
        out.append(f"{who} {v}")
    return ", ".join(out)


def _random_combo_of_class(k: int, dead: set[int]) -> tuple[int, int] | None:
    opts = [ALL_COMBOS[i] for i in CLASS_COMBOS[k] if not (set(ALL_COMBOS[i]) & dead)]
    return random.choice(opts) if opts else None


def _combo_cards(c: tuple[int, int]) -> list[str]:
    s = combo_str(c)
    return [s[:2], s[2:]]


def _grade_meta(freqs, evs):
    best = int(np.argmax(evs))
    top = int(np.argmax(freqs))
    return best, top


# ------------------------------------------------------------------ preflop
def _random_limpers(hero: str) -> str | None:
    s = preflop.seats()
    cands = [p for p in s[:s.index(hero)] if p != "BB" and (p != "SB" or hero == "BB")]
    if not cands:
        return None
    k = min(len(cands), random.choices([1, 2, 3], weights=[0.55, 0.32, 0.13])[0])
    return ",".join(sorted(random.sample(cands, k), key=s.index))


def _preflop_pairs(scenarios, positions):
    pairs = []
    for sc in scenarios:
        for h in positions:
            if sc == "vs_limp":
                lim = _random_limpers(h)
                if lim:
                    pairs.append((sc, h, lim))
                continue
            for v in ([None] if sc == "rfi" else preflop.seats()):
                try:
                    preflop.validate(sc, h, v)
                except ValueError:
                    continue
                pairs.append((sc, h, v))
    return pairs


def preflop_spot(cfg: dict) -> dict:
    pairs = _preflop_pairs(cfg["scenarios"], cfg["positions"])
    if not pairs:
        raise ValueError("no valid preflop spot for these positions/situations")
    sc, hero, villain = random.choice(pairs)
    if sc == "vs_limp":   # sample one limper configuration per hero seat, not per subset
        hero = random.choice(sorted({h for s_, h, _ in pairs if s_ == "vs_limp"}))
        villain = _random_limpers(hero)
    S = random.choice(cfg["stacks"])
    if sc == "vs_jam":
        S = random.choice([10, 12, 15, 18, 22])
    prof_key = cfg["profile"]
    profs = {p: prof_key for p in preflop.seats() if p != hero}
    res = preflop.solve_spot(sc, hero, villain, S, 0.0, profs, exploit_strength=1.0)
    table_name = preflop.TABLE_NAMES[preflop.n_players()]
    mode = "exploit" if prof_key != "gto" else "gto"
    keys = [a["key"] for a in res["actions"]]
    weights = []
    for h in res["hands"]:
        if h["weight"] <= 0.001:
            weights.append(0.0)
            continue
        f = [h[mode][k] for k in keys]
        n = len(CLASS_COMBOS[HAND_CLASSES.index(h["hand"])])
        base = h["weight"] * n
        if cfg.get("tricky"):
            evs = [h["ev_" + mode][k] for k in keys]
            spread = max(evs) - sorted(evs)[-2] if len(evs) > 1 else 1
            base *= (1 - max(f)) + 0.15 / (1 + 4 * abs(spread))
        else:
            # avoid an endless stream of trivial folds (72o etc.): down-weight pure folds
            base *= 0.2 if f[0] > 0.99 else 1.0
        weights.append(base)
    k = random.choices(range(169), weights=weights)[0]
    h = res["hands"][k]
    combo = _random_combo_of_class(k, set())
    freqs = [h[mode][x] for x in keys]
    evs = [h["ev_" + mode][x] for x in keys]
    eq = h["equity_" + mode]
    pot = res["pot"]
    desc = {
        "rfi": lambda: f"{table_name}. Folds to you in the {hero}.",
        "vs_open": lambda: f"{table_name}. {villain} opens to {preflop.open_size(villain, S):g}bb, folds to you in the {hero}.",
        "vs_3bet": lambda: (f"You open to {preflop.open_size(hero, S):g}bb in the {hero}, {villain} 3-bets to "
                            f"{preflop.threebet_size(villain, hero, preflop.open_size(hero, S), S):g}bb."),
        "vs_4bet": lambda: f"{villain} opens, you 3-bet from the {hero}, {villain} 4-bets.",
        "vs_jam": lambda: f"{villain} moves all-in for {S:g}bb, folds to you in the {hero}.",
        "vs_limp": lambda: (f"{_limp_text(villain)}, folds to you in the {hero}."
                            + (f" Limpers play like: {get_profile(prof_key).name}." if prof_key != "gto" else "")),
    }[sc]()
    if not desc.startswith(table_name):
        desc = f"{table_name}. {desc}"
    expl = _explain_preflop(sc, res, h, keys, freqs, evs, eq, mode, prof_key, S, hero, villain)
    opp = _preflop_opp(sc, res["villains_" + mode])
    cells = [{"w": x["weight"], "f": [x[mode][kk] for kk in keys]} if x["weight"] > 0.001 else None for x in res["hands"]]
    cells_gto = [{"w": x["weight"], "f": [x["gto"][kk] for kk in keys]} if x["weight"] > 0.001 else None for x in res["hands"]]
    return {
        "street": "preflop", "scenario": sc, "hero_pos": hero, "villain_pos": villain,
        "stack": S, "pot": pot, "board": [], "hand": _combo_cards(combo), "hand_class": h["hand"],
        "history": [{"street": "Preflop", "text": desc}],
        "question": "What do you do?",
        "actions": res["actions"], "to_call": None,
        "answer": {"freqs": freqs, "evs": evs, "equity": eq, "mode": mode, "opponents": opp,
                   "gto_freqs": [h["gto"][x] for x in keys], "explanation": expl,
                   "grid": cells, "grid_gto": cells_gto, "hand_index": k,
                   "range_summary": [res["summary"][mode][x] for x in keys]},
        "profile": prof_key, "n_players": preflop.n_players(),
    }


def _seg_grid(base, segs):
    """169 grid of an opponent range (weights = base), split into segments (+ remainder)."""
    base = np.asarray(base, dtype=float)
    S = [np.minimum(np.asarray(s, dtype=float), base) for s in segs]
    grid = []
    for i in range(169):
        if base[i] <= 0.001:
            grid.append(None)
            continue
        f = [float(s[i] / base[i]) for s in S]
        f.append(max(0.0, 1 - sum(f)))
        grid.append({"w": round(float(base[i]), 4), "f": [round(x, 3) for x in f]})
    tot = float((base * CLASS_NCOMBOS).sum())
    summ = [float((s * CLASS_NCOMBOS).sum()) / tot if tot > 0 else 0 for s in S]
    summ.append(max(0.0, 1 - sum(summ)))
    return grid, [round(x, 4) for x in summ], round(tot / 1326, 4)


def _preflop_opp(sc, vill):
    """Opponent range(s) at the decision, split by how they respond to your next action."""
    out = []

    def add(title, base, segs, labels):
        grid, summ, pct = _seg_grid(base, segs)
        out.append({"title": title, "pct": pct, "grid": grid, "legend": labels, "summary": summ})

    if "players" in vill:            # open first in: every player behind
        for p in vill["players"]:
            cont = np.asarray(p["threebet"]) + np.asarray(p["call"])
            if cont.max() > 0.001:
                add(f"{p['pos']} vs your open", cont, [p["threebet"]], ["3-bets", "Calls"])
        return out
    R = {k: v["weights"] for k, v in vill["ranges"].items()}
    if sc == "vs_open" and "open" in R:
        add("Opening range", R["open"], [R.get("fourbet", np.zeros(169)), R.get("call_vs_3bet", np.zeros(169))],
            ["4-bets vs 3-bet", "Calls 3-bet", "Folds to 3-bet"])
    elif sc == "vs_3bet" and "threebet" in R:
        add("3-bet range", R["threebet"], [R.get("fivebet_jam", np.zeros(169)), R.get("call_vs_4bet", np.zeros(169))],
            ["Jams vs 4-bet", "Calls 4-bet", "Folds to 4-bet"])
    elif sc == "vs_4bet" and "fourbet" in R:
        add("4-bet range", R["fourbet"], [R.get("call_vs_jam", np.zeros(169))], ["Calls your jam", "Folds to jam"])
    elif sc == "vs_jam" and "jam" in R:
        add("All-in range", R["jam"], [], ["Jams"])
    elif sc == "vs_limp":
        for k in R:
            if k.startswith("limp_") and not k.startswith("limp_reraise_"):
                pos = k[5:]
                add(f"{pos} limp range", R[k], [R.get(f"limp_reraise_{pos}", np.zeros(169)),
                                                R.get(f"call_iso_{pos}", np.zeros(169))],
                    ["Limp-reraises", "Calls iso", "Folds to iso"])
    return out


def _limp_text(v: str) -> str:
    lim = v.split(",")
    if len(lim) == 1:
        return f"{lim[0]} limps" if lim[0] != "SB" else "SB completes"
    return ", ".join(lim[:-1]) + f" and {lim[-1]} limp"


def _explain_preflop(sc, res, h, keys, freqs, evs, eq, mode, prof, S, hero, villain):
    labels = [a["label"] for a in res["actions"]]
    lines = []
    used = [f"{labels[i]} {round(100 * f)}%" for i, f in enumerate(freqs) if f >= 0.05]
    lines.append(f"Solver strategy for {h['hand']}: " + ", ".join(used) + ".")
    if eq is not None:
        tgt = {"rfi": "the ranges that continue vs your open", "vs_open": f"{villain}'s opening range",
               "vs_3bet": f"{villain}'s 3-bet range", "vs_4bet": f"{villain}'s 4-bet range",
               "vs_jam": f"{villain}'s all-in range",
               "vs_limp": ("the limpers and blinds combined (multiway)" if len((villain or "").split(",")) + 1 +
                           (1 if hero != "BB" else 0) >= 3 else f"{villain}'s limping range")}[sc]
        lines.append(f"{h['hand']} has about {round(100 * eq)}% equity against {tgt}.")
    if sc == "vs_limp":
        lim = villain.split(",")
        n = len(lim)
        size = res["info"].get("size")
        labels_ = [a["label"] for a in res["actions"]]
        best = labels_[int(np.argmax(freqs))]
        players = n + 1 + (1 if hero != "BB" and "BB" in preflop.seats() else 0)
        if best.startswith(("Iso", "All-in")):
            lines.append(f"Raise to isolate: limping ranges are capped (most players raise their premiums), so {h['hand']} "
                         f"dominates much of what they limp. Size up to {size:g}bb (+1bb per limper) to thin the field"
                         + (" and play heads-up in position." if hero not in ("SB", "BB") else
                            " — bigger out of position, since you'll play the hand without position."))
        elif best in ("Over-limp", "Complete", "Check"):
            what = {"Check": "Check your option: it's free", "Complete": "Complete: it's only 0.5bb more",
                    "Over-limp": "Over-limp"}[best]
            if players >= 3:
                lines.append(f"{what}. With {players} players likely to see the flop, {h['hand']} plays well as a cheap "
                             f"multiway hand (sets, draws, disguised strength) but isn't strong enough to raise for value"
                             + (f"; at {S:g}bb deep there's little implied odds, so this is closer." if S <= 30 else "."))
            else:
                lines.append(f"{what}. {h['hand']} is too weak to raise for value against the limping range, "
                             f"but has enough equity to see a flop cheaply.")
        else:
            lines.append(f"Fold: {h['hand']} is too weak to isolate profitably and doesn't make enough strong hands "
                         f"to over-limp into a {players}-way pot.")
        if hero == "BB" and best == "Check":
            lines.append("From the BB you close the action, so checking risks nothing; raise only hands that want a bigger pot.")
    if sc == "vs_jam":
        po = res["info"].get("pot_odds")
        if po:
            lines.append(f"Calling needs about {round(100 * po)}% equity (pot odds); it's pure chip-EV maths at {S:g}bb.")
    if max(freqs) < 0.8:
        lines.append("This hand is at the edge of the range: the actions it mixes between are close in EV, so any of them is acceptable.")
    if sc == "rfi":
        lines.append(f"Fewer players behind = wider opens. From the {hero}, the solver opens {round(100 * res['summary'][mode]['agg'])}% of hands at {S:g}bb.")
    if sc in ("vs_open", "vs_3bet") and "agg" in keys and "call" in keys:
        lines.append("3-bet/4-bet ranges mix strong value hands with blockers (e.g. suited aces); flats are hands that play well postflop but don't want to bloat the pot.")
    if S <= 25 and sc != "vs_jam":
        lines.append(f"At {S:g}bb, flatting loses value (less implied odds) and many raises become all-ins.")
    if mode == "exploit" and prof in PROFILE_LEAKS:
        g = [h["gto"][k] for k in keys]
        diffs = [(labels[i], g[i], freqs[i]) for i in range(len(keys)) if abs(freqs[i] - g[i]) >= 0.1]
        if diffs:
            d = "; ".join(f"{a} {round(100 * x)}% → {round(100 * y)}%" for a, x, y in diffs)
            lines.append(f"Exploit vs {get_profile(prof).name}: {d} (GTO → exploit), because this player type {PROFILE_LEAKS[prof]}.")
    return lines


# ------------------------------------------------------------------ postflop
def _postflop_line(cfg):
    pot_types = cfg["pot_types"]
    options = []
    seat_list = preflop.seats()
    gto = get_profile("gto")
    for pt in pot_types:
        for o in seat_list[:-1]:
            for d in seat_list[seat_list.index(o) + 1:]:
                if pt == "srp" and preflop.vs_open_width(d, o, 100, gto)[1] <= 0:
                    continue
                for hero in (o, d):
                    if hero in cfg["positions"]:
                        options.append((pt, o, d, hero))
    if not options:
        raise ValueError("no valid postflop spot for these positions/pot types")
    pt, o, d, hero = random.choice(options)
    S = random.choice(cfg["stacks"])
    op = preflop.open_size(o, S)
    base = preflop.dead_money(0)
    if pt == "srp":
        r_open = preflop.solve_spot("rfi", o, None, S, 0, {})
        r_def = preflop.solve_spot("vs_open", d, o, S, 0, {})
        ro = np.array([x["gto"].get("agg", 0.0) * x["weight"] for x in r_open["hands"]])
        rd = np.array([x["gto"].get("call", 0.0) * x["weight"] for x in r_def["hands"]])
        pot = base + 2 * op - preflop.POSTED.get(o, 0) - preflop.POSTED.get(d, 0)
        stack = S - op
        text = f"{preflop.TABLE_NAMES[preflop.n_players()]}. {o} opens to {op:g}bb, {d} calls."
    else:
        T = preflop.threebet_size(d, o, op, S)
        if T >= S:
            raise ValueError("3-bet is all-in at this depth")
        r_def = preflop.solve_spot("vs_open", d, o, S, 0, {})
        r_op = preflop.solve_spot("vs_3bet", o, d, S, 0, {})
        rd = np.array([x["gto"].get("agg", 0.0) * x["weight"] for x in r_def["hands"]])
        ro = np.array([x["gto"].get("call", 0.0) * x["weight"] for x in r_op["hands"]])
        pot = base + 2 * T - preflop.POSTED.get(o, 0) - preflop.POSTED.get(d, 0)
        stack = S - T
        text = f"{preflop.TABLE_NAMES[preflop.n_players()]}. {o} opens to {op:g}bb, {d} 3-bets to {T:g}bb, {o} calls."
    ip = o if preflop.is_ip(o, d) else d
    oop = d if ip == o else o
    w = {o: class_weights_to_combo(ro), d: class_weights_to_combo(rd)}
    return {"pot_type": pt, "opener": o, "defender": d, "hero": hero, "ip": ip, "oop": oop, "S": S,
            "pot": round(pot, 2), "stack": round(stack, 2), "w_oop": w[oop], "w_ip": w[ip], "text": text}


def _narrow(board, w0, w1, pot, stack, bets, iters=150):
    """Solve a street (GTO) and sample a line that continues to the next street.
    Returns new (w0, w1, pot, stack, path)."""
    idx0, v0 = _prep_range(w0, board)
    idx1, v1 = _prep_range(w1, board)
    E_raw, M = combo_matrix(idx0, idx1, board, max_runouts=150 if len(board) == 3 else 1000)
    R = {3: 0.90, 4: 0.95}[len(board)]
    E = np.where(M > 0, E_raw * R / np.maximum(E_raw * R + (1 - E_raw), 1e-12), 0) * M
    nodes = build_tree(pot, stack, bets, bets, 3.0, True, False)
    S = Solver(nodes, pot, E, M, v0, v1)
    S.run(iters, time_budget=8)
    ends = []

    def walk(nid, r0, r1):
        nd = nodes[nid]
        if nd.kind == "showdown":
            if stack - max(nd.c) > 0.5:
                ends.append((nd, r0, r1))
            return
        if nd.kind != "action":
            return
        sig = S.average(nid)
        for a, ch in enumerate(nd.children):
            if nd.player == 0:
                walk(ch, r0 * sig[:, a], r1)
            else:
                walk(ch, r0, r1 * sig[:, a])

    walk(0, v0.copy(), v1.copy())
    probs = np.array([(r0.sum() / v0.sum()) * (r1.sum() / v1.sum()) for _, r0, r1 in ends])
    probs[probs < 0.01] = 0
    if probs.sum() <= 0:
        raise ValueError("no continuing line")
    nd, r0, r1 = ends[random.choices(range(len(ends)), weights=probs)[0]]
    n0, n1 = np.zeros(1326), np.zeros(1326)
    n0[idx0] = r0 / max(r0.max(), 1e-12)
    n1[idx1] = r1 / max(r1.max(), 1e-12)
    return n0, n1, pot + nd.c[0] + nd.c[1], stack - max(nd.c), nd.path


def postflop_spot(cfg: dict, street: str) -> dict:
    line = _postflop_line(cfg)
    deck = list(range(52))
    random.shuffle(deck)
    n_board = {"flop": 3, "turn": 4, "river": 5}[street]
    full = deck[:n_board]
    w0, w1, pot, stack = line["w_oop"], line["w_ip"], line["pot"], line["stack"]
    oop, ip, hero = line["oop"], line["ip"], line["hero"]
    history = [{"street": "Preflop", "text": line["text"]}]
    board = full[:3]
    if n_board >= 4:
        w0, w1, pot2, stack2, path = _narrow(board, w0, w1, pot, stack, [0.33, 0.75])
        history.append({"street": "Flop", "cards": [card_to_str(c) for c in board],
                        "text": _describe_line(path, oop, ip, pot) + f" (pot {pot2:g}bb)"})
        pot, stack = pot2, stack2
        board = full[:4]
    if n_board == 5:
        w0, w1, pot2, stack2, path = _narrow(board, w0, w1, pot, stack, [0.5, 1.0])
        history.append({"street": "Turn", "cards": [card_to_str(board[3])],
                        "text": _describe_line(path, oop, ip, pot) + f" (pot {pot2:g}bb)"})
        pot, stack = pot2, stack2
        board = full[:5]

    prof_key = cfg["profile"]
    prof = get_profile(prof_key)
    villain_is = 1 if hero == oop else 0
    pot, stack = round(pot, 2), round(stack, 2)
    if street == "turn":
        try:
            res, _ = postflop2.solve_turn(board, w0, w1, pot, stack, [0.5, 1.0], [0.5, 1.0], [0.75], [0.75],
                                          iterations=80, villain_is=villain_is, villain_profile=prof,
                                          time_budget=25)
        except ValueError:
            res = postflop.solve(board, w0, w1, pot, stack, [0.5, 1.0], [0.5, 1.0], iterations=200,
                                 villain_is=villain_is, villain_profile=prof)
    else:
        bets = [0.33, 0.75] if street == "flop" else [0.5, 1.0]
        res = postflop.solve(board, w0, w1, pot, stack, bets, bets, iterations=220 if street == "flop" else 300,
                             villain_is=villain_is, villain_profile=prof)
    mode = "exploit" if prof_key != "gto" and res.get("exploit_info") else "gto"

    by_path = {tuple(n["path"]): n for n in res["nodes"]}
    hero_mass0 = res["ranges"][0 if hero == oop else 1]["combos"]
    cands, weights = [], []
    for n in res["nodes"]:
        if not n["is_hero"] or len(n["path"]) > 2:
            continue
        p = 1.0
        for i, act in enumerate(n["path"]):
            par = by_path[tuple(n["path"][:i])]
            if not par["is_hero"]:
                p *= par[mode]["summary"][[a["label"] for a in par["actions"]].index(act)]
        p *= n[mode]["range_combos"] / max(hero_mass0, 1e-9)
        if p > 0.01 and n[mode]["combos"]:
            cands.append(n)
            weights.append(p)
    if not cands:
        raise ValueError("no hero decision")
    node = random.choices(cands, weights=weights)[0]
    rows = node[mode]["combos"]
    rw = []
    for r in rows:
        x = r[1]
        if cfg.get("tricky"):
            x *= (1 - max(r[2])) + 0.08
        rw.append(x)
    row = random.choices(rows, weights=rw)[0]
    gto_row = next((r for r in node["gto"]["combos"] if r[0] == row[0]), row)
    combo_s, freqs, evs, eq, made, draw = row[0], row[2], row[3], row[4], row[5], row[6]
    eq_node = row[8] if len(row) > 8 else eq

    if node["path"]:
        history.append({"street": street.capitalize(), "cards": [card_to_str(c) for c in (board if street == "flop" else board[-1:])],
                        "text": _describe_line(node["path"], oop, ip, pot)})
    else:
        history.append({"street": street.capitalize(), "cards": [card_to_str(c) for c in (board if street == "flop" else board[-1:])],
                        "text": "You act first."})
    expl = _explain_postflop(node, freqs, evs, eq, eq_node, made, draw, mode, prof_key, gto_row[2], hero, oop, ip)
    return {
        "street": street, "scenario": line["pot_type"], "hero_pos": hero, "villain_pos": ip if hero == oop else oop,
        "hero_side": "OOP" if hero == oop else "IP",
        "stack": stack, "pot": node["pot"], "board": [card_to_str(c) for c in board],
        "hand": [combo_s[:2], combo_s[2:]], "hand_class": HAND_CLASSES[row[7]],
        "history": history, "question": "What do you do?",
        "actions": node["actions"], "to_call": node["to_call"],
        "answer": {"freqs": freqs, "evs": evs, "equity": eq, "equity_node": eq_node, "mode": mode, "gto_freqs": gto_row[2],
                   "opponents": [{"title": f"{ip if hero == oop else oop} range here", "pct": None,
                                  **{k: node[mode]["opp"][k] for k in ("grid", "legend", "summary", "combos")}}],
                   "made": made, "draw": draw, "explanation": expl,
                   "grid": node[mode]["grid"], "grid_gto": node["gto"]["grid"], "hand_index": row[7],
                   "range_summary": node[mode]["summary"],
                   "solver": {"exploitability_pct_pot": res["exploitability_pct_pot"], "mode": res.get("mode", "single_street")}},
        "profile": prof_key, "n_players": preflop.n_players(),
    }


def _explain_postflop(node, freqs, evs, eq_full, eq, made, draw, mode, prof, gto_freqs, hero, oop, ip):
    labels = [a["label"] for a in node["actions"]]
    lines = []
    hand = made + ("" if draw == "No draw" else f" + {draw}")
    if node["path"] and abs(eq - eq_full) >= 0.04:
        lines.append(f"You hold {hand}. Against villain's whole range you'd have {round(100 * eq_full)}%, but against the hands "
                     f"he actually takes this line with you have only {round(100 * eq)}%." if eq < eq_full else
                     f"You hold {hand}. Villain's line weakens his range: your equity rises from {round(100 * eq_full)}% "
                     f"(vs his whole range) to {round(100 * eq)}% against the hands he plays this way.")
    else:
        lines.append(f"You hold {hand}, with {round(100 * eq)}% equity against villain's range here.")
    used = [f"{labels[i]} {round(100 * f)}%" for i, f in enumerate(freqs) if f >= 0.05]
    lines.append("Solver: " + ", ".join(used) + ".")
    best = int(np.argmax(evs))
    bl = labels[best]
    to_call = node["to_call"]
    if to_call:
        need = to_call / (node["pot"] + to_call)
        lines.append(f"Facing {to_call:g}bb into {node['pot'] - to_call:g}bb, a call needs ~{round(100 * need)}% equity "
                     f"at showdown (more when out of position, less with a strong draw).")
    if bl.startswith(("Bet", "Raise", "All-in")):
        if eq >= 0.65:
            lines.append("This is a value hand: betting/raising builds the pot and gets called by worse.")
        elif eq <= 0.4:
            lines.append("Low showdown value: the solver uses this hand as a bluff/semi-bluff — it can fold out better hands"
                         + (" and has outs when called." if draw != "No draw" else "."))
        else:
            lines.append("A thin or protection bet: it denies equity to overcards/draws and gets value from weaker pairs.")
    elif bl == "Check":
        if eq >= 0.65:
            lines.append("Strong but the solver checks some of these to protect its checking range and induce bluffs.")
        elif eq >= 0.35:
            lines.append("Medium strength: checking keeps the pot small and lets you realize equity; worse hands won't call a bet.")
        else:
            lines.append("Weak hand with no good bluffing properties: give up and check.")
    elif bl.startswith("Call"):
        lines.append("Enough equity to continue but not strong enough to raise for value — calling also keeps villain's bluffs in.")
    elif bl == "Fold":
        lines.append("Not enough equity at this price and too little to gain from raising — fold.")
    if max(freqs) < 0.75:
        lines.append("Mixed spot: the main actions are close in EV, so any action the solver takes at a decent frequency is fine.")
    if mode == "exploit" and prof in PROFILE_LEAKS:
        diffs = [(labels[i], gto_freqs[i], freqs[i]) for i in range(len(labels)) if abs(freqs[i] - gto_freqs[i]) >= 0.1]
        if diffs:
            d = "; ".join(f"{a} {round(100 * x)}% → {round(100 * y)}%" for a, x, y in diffs)
            lines.append(f"Exploit vs {get_profile(prof).name}: {d} (GTO → exploit) because this player {PROFILE_LEAKS[prof]}.")
        else:
            lines.append(f"Against {get_profile(prof).name} this hand plays the same as GTO.")
    return lines


# ------------------------------------------------------------------ entry
def generate(cfg: dict) -> dict:
    n = int(cfg.get("n_players", 6))
    with preflop.table(n):
        return _generate(cfg)


def _generate(cfg: dict) -> dict:
    streets = [s for s in cfg.get("streets", STREETS) if s in STREETS] or ["preflop"]
    seat_list = preflop.seats()
    cfg = {
        "positions": [p for p in cfg.get("positions", seat_list) if p in seat_list] or seat_list,
        "scenarios": [s for s in cfg.get("scenarios", list(preflop.SCENARIOS)) if s in preflop.SCENARIOS] or ["rfi"],
        "pot_types": [p for p in cfg.get("pot_types", ["srp", "3bp"]) if p in ("srp", "3bp")] or ["srp"],
        "stacks": cfg.get("stacks") or [100],
        "profile": cfg.get("profile", "gto"),
        "tricky": bool(cfg.get("tricky", False)),
    }
    last = None
    for _ in range(6):
        st = random.choice(streets)
        try:
            return preflop_spot(cfg) if st == "preflop" else postflop_spot(cfg, st)
        except ValueError as e:
            last = e
    raise ValueError(f"could not build a spot with these settings ({last})")
