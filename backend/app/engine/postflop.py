"""Single-street postflop solver (vectorized CFR+).

Game abstraction
----------------
* The current street is played out exactly: OOP check/bet(sizes); IP check/bet or
  fold/call/raise; one raise allowed, then fold/call.
* When the street ends (check-check or call) the pot is awarded by *equity* over all
  future runouts (exact on river; enumerated on turn; sampled on flop), with an equity
  realization penalty for the OOP player on flop/turn. This is the standard
  "pot-equity at end of street" approximation - accurate on the river, approximate earlier.
* GTO mode: CFR+ self-play to an approximate Nash equilibrium for that tree.
* Exploit mode: villain's equilibrium strategy is node-locked with profile shifts
  (overfold / overcall / overbluff / passive...), then hero re-solves = best response.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .cards import ALL_COMBOS, CLASS_NCOMBOS, COMBO_CLASS, HAND_CLASSES, blocked_mask, combo_str
from .equity import combo_matrix
from .handclass import DRAW_CATS, MADE_CATS, board_texture, classify
from .profiles import Profile


# ------------------------------------------------------------------ tree
@dataclass
class Node:
    id: int
    kind: str                 # "action" | "fold" | "showdown"
    player: int = -1          # 0 = OOP, 1 = IP (actor for action nodes)
    c: tuple = (0.0, 0.0)     # chips put in this street by (OOP, IP)
    actions: list = field(default_factory=list)   # [(key, label, amount)]
    children: list = field(default_factory=list)
    folder: int = -1
    path: list = field(default_factory=list)      # action labels from root
    node_type: str = ""       # "open" (check/bet) | "facing_bet" | "facing_raise"


def _size(frac: float, pot: float, stack_left: float) -> float:
    b = round(frac * pot, 2)
    return stack_left if b >= 0.67 * stack_left else b


def build_tree(pot: float, stack: float, oop_bets: list[float], ip_bets: list[float],
               raise_mult: float, allow_raise: bool, add_allin: bool) -> list[Node]:
    nodes: list[Node] = []

    def new(**kw) -> Node:
        n = Node(id=len(nodes), **kw)
        nodes.append(n)
        return n

    def sizes(fracs, cur_pot, left):
        out = []
        for f in fracs:
            b = _size(f, cur_pot, left)
            if b > 0 and b not in out:
                out.append(b)
        if add_allin and left > 0 and left not in out:
            out.append(left)
        return sorted(out)

    def facing(bettor: int, c: tuple, bet: float, path: list, can_raise: bool) -> Node:
        actor = 1 - bettor
        n = new(kind="action", player=actor, c=c, path=path, node_type="facing_bet" if can_raise else "facing_raise")
        to_call = c[bettor] - c[actor]
        # fold
        f = new(kind="fold", folder=actor, c=c, path=path + ["Fold"])
        n.actions.append(("fold", "Fold", 0.0)); n.children.append(f.id)
        cc = list(c); cc[actor] = c[bettor]
        s = new(kind="showdown", c=tuple(cc), path=path + ["Call"])
        n.actions.append(("call", f"Call {to_call:g}", to_call)); n.children.append(s.id)
        left = stack - c[bettor]
        if can_raise and allow_raise and left > 0:
            raise_to = round(c[bettor] * raise_mult, 2)
            if raise_to >= c[bettor] + 0.67 * left or raise_to >= stack:
                raise_to = stack
            rc = list(c); rc[actor] = raise_to
            lbl = f"Raise {raise_to:g}" if raise_to < stack else f"All-in {raise_to:g}"
            child = facing(actor, tuple(rc), raise_to, path + [lbl], can_raise=False)
            n.actions.append(("raise", lbl, raise_to)); n.children.append(child.id)
        return n

    root = new(kind="action", player=0, c=(0.0, 0.0), path=[], node_type="open")
    # OOP check
    ipn_path = ["Check"]
    ipn = new(kind="action", player=1, c=(0.0, 0.0), path=ipn_path, node_type="open")
    root.actions.append(("check", "Check", 0.0)); root.children.append(ipn.id)
    sd = new(kind="showdown", c=(0.0, 0.0), path=ipn_path + ["Check"])
    ipn.actions.append(("check", "Check", 0.0)); ipn.children.append(sd.id)
    for b in sizes(ip_bets, pot, stack):
        lbl = f"Bet {b:g}" if b < stack else f"All-in {b:g}"
        ch = facing(1, (0.0, b), b, ipn_path + [lbl], can_raise=b < stack)
        ipn.actions.append((f"bet{b:g}", lbl, b)); ipn.children.append(ch.id)
    for b in sizes(oop_bets, pot, stack):
        lbl = f"Bet {b:g}" if b < stack else f"All-in {b:g}"
        ch = facing(0, (b, 0.0), b, [lbl], can_raise=b < stack)
        root.actions.append((f"bet{b:g}", lbl, b)); root.children.append(ch.id)
    return nodes


# ------------------------------------------------------------------ solver
class Solver:
    def __init__(self, nodes, pot, E, M, w0, w1):
        self.nodes = nodes
        self.pot = pot
        self.E = [E, (M - E).T]           # equity matrices from each player's perspective
        self.M = [M, M.T]
        self.w = [w0, w1]
        self.n = [len(w0), len(w1)]
        self.reg = {}
        self.ssum = {}
        self.locked: dict[int, np.ndarray] = {}
        for nd in nodes:
            if nd.kind == "action":
                A = len(nd.actions)
                self.reg[nd.id] = np.zeros((self.n[nd.player], A))
                self.ssum[nd.id] = np.zeros((self.n[nd.player], A))

    @staticmethod
    def _rm(r: np.ndarray) -> np.ndarray:
        pos = np.maximum(r, 0)
        s = pos.sum(axis=1, keepdims=True)
        A = r.shape[1]
        return np.where(s > 0, pos / np.where(s > 0, s, 1), 1.0 / A)

    def current(self, nid):
        if nid in self.locked:
            return self.locked[nid]
        return self._rm(self.reg[nid])

    def average(self, nid):
        if nid in self.locked:
            return self.locked[nid]
        s = self.ssum[nid]
        tot = s.sum(axis=1, keepdims=True)
        A = s.shape[1]
        return np.where(tot > 0, s / np.where(tot > 0, tot, 1), 1.0 / A)

    def terminal(self, nd: Node, p: int, ro: np.ndarray) -> np.ndarray:
        M = self.M[p]
        if nd.kind == "fold":
            mass = M @ ro
            if nd.folder == p:
                return -nd.c[p] * mass
            return (self.pot + nd.c[nd.folder]) * mass
        final = self.pot + nd.c[0] + nd.c[1]
        return (self.E[p] @ ro) * final - nd.c[p] * (M @ ro)

    def cfr(self, nid: int, p: int, rp: np.ndarray, ro: np.ndarray, t: int, update=True) -> np.ndarray:
        nd = self.nodes[nid]
        if nd.kind != "action":
            return self.terminal(nd, p, ro)
        sigma = self.current(nid)
        if nd.player == p:
            vals = np.stack([self.cfr(ch, p, rp * sigma[:, a], ro, t, update)
                             for a, ch in enumerate(nd.children)], axis=1)
            v = (sigma * vals).sum(axis=1)
            if update and nid not in self.locked:
                self.reg[nid] = np.maximum(self.reg[nid] + vals - v[:, None], 0)   # CFR+
                self.ssum[nid] += t * rp[:, None] * sigma                          # linear averaging
            return v
        v = np.zeros(self.n[p])
        for a, ch in enumerate(nd.children):
            v += self.cfr(ch, p, rp, ro * sigma[:, a], t, update)
        return v

    def run(self, iters: int, time_budget: float = 20.0):
        t0 = time.time()
        for t in range(1, iters + 1):
            for p in (0, 1):
                self.cfr(0, p, self.w[p].copy(), self.w[1 - p].copy(), t)
            if time.time() - t0 > time_budget:
                return t
        return iters

    # -------------------------------------------------------- evaluation with average strategy
    def best_response_value(self, p: int) -> float:
        def br(nid, ro):
            nd = self.nodes[nid]
            if nd.kind != "action":
                return self.terminal(nd, p, ro)
            sig = self.average(nid)
            if nd.player == p:
                return np.max(np.stack([br(ch, ro) for ch in nd.children], axis=1), axis=1)
            v = np.zeros(self.n[p])
            for a, ch in enumerate(nd.children):
                v += br(ch, ro * sig[:, a])
            return v
        cf = br(0, self.w[1 - p])
        Z = self.w[0] @ self.M[0] @ self.w[1]
        return float(self.w[p] @ cf / Z)

    def value(self, p: int) -> float:
        def ev(nid, rp, ro):
            nd = self.nodes[nid]
            if nd.kind != "action":
                return self.terminal(nd, p, ro)
            sig = self.average(nid)
            if nd.player == p:
                return sum(sig[:, a] * ev(ch, rp, ro) for a, ch in enumerate(nd.children))
            return sum(ev(ch, rp, ro * sig[:, a]) for a, ch in enumerate(nd.children))
        cf = ev(0, self.w[p], self.w[1 - p])
        Z = self.w[0] @ self.M[0] @ self.w[1]
        return float(self.w[p] @ cf / Z)

    def node_reports(self) -> dict:
        """For every action node: actor reach, opponent reach, per-action EV per actor combo."""
        out = {}

        def walk(nid, r0, r1):
            nd = self.nodes[nid]
            if nd.kind != "action":
                return
            p = nd.player
            sig = self.average(nid)
            rp, ro = (r0, r1) if p == 0 else (r1, r0)
            # per-action cfv for actor
            vals = []
            for a, ch in enumerate(nd.children):
                vals.append(self._cfv_avg(ch, p, ro))
            vals = np.stack(vals, axis=1)
            mass = self.M[p] @ ro
            ev = np.divide(vals, mass[:, None], out=np.zeros_like(vals), where=mass[:, None] > 1e-12)
            out[nid] = {"reach_actor": rp.copy(), "reach_opp": ro.copy(), "strategy": sig.copy(), "ev": ev}
            for a, ch in enumerate(nd.children):
                if p == 0:
                    walk(ch, r0 * sig[:, a], r1)
                else:
                    walk(ch, r0, r1 * sig[:, a])

        walk(0, self.w[0].copy(), self.w[1].copy())
        return out

    def _cfv_avg(self, nid, p, ro):
        nd = self.nodes[nid]
        if nd.kind != "action":
            return self.terminal(nd, p, ro)
        sig = self.average(nid)
        if nd.player == p:
            vals = np.stack([self._cfv_avg(ch, p, ro) for ch in nd.children], axis=1)
            return (sig * vals).sum(axis=1)
        v = np.zeros(self.n[p])
        for a, ch in enumerate(nd.children):
            v += self._cfv_avg(ch, p, ro * sig[:, a])
        return v


# ------------------------------------------------------------------ node locking (profiles)
def lock_strategy(sig: np.ndarray, actions: list, node_type: str, prof: Profile) -> np.ndarray:
    s = sig.copy()
    keys = [a[0] for a in actions]
    if node_type in ("facing_bet", "facing_raise"):
        fi, ci = keys.index("fold"), keys.index("call")
        ri = keys.index("raise") if "raise" in keys else None
        f = prof.fold
        if f < 0:  # calls more
            moved = s[:, fi] * (-f)
            s[:, fi] -= moved
            s[:, ci] += moved
        elif f > 0:
            m1 = s[:, ci] * f
            s[:, ci] -= m1
            s[:, fi] += m1
            if ri is not None:
                m2 = s[:, ri] * f * 0.5
                s[:, ri] -= m2
                s[:, fi] += m2
        if ri is not None:
            r = prof.raise_
            if r > 0:
                m = s[:, ci] * r
                s[:, ci] -= m
                s[:, ri] += m
            elif r < 0:
                m = s[:, ri] * (-r)
                s[:, ri] -= m
                s[:, ci] += m
    else:  # open node: check + bets
        ci = keys.index("check")
        bets = [i for i, k in enumerate(keys) if k != "check"]
        b = prof.bet
        if bets:
            if b > 0:
                moved = s[:, ci] * b
                s[:, ci] -= moved
                bet_mass = s[:, bets]
                tot = bet_mass.sum(axis=1, keepdims=True)
                share = np.where(tot > 1e-9, bet_mass / np.where(tot > 1e-9, tot, 1), 1.0 / len(bets))
                s[:, bets] += share * moved[:, None]
            elif b < 0:
                moved = s[:, bets] * (-b)
                s[:, bets] -= moved
                s[:, ci] += moved.sum(axis=1)
    s = np.clip(s, 0, None)
    return s / s.sum(axis=1, keepdims=True)


# ------------------------------------------------------------------ public API
def _prep_range(w1326: np.ndarray, board: list[int]) -> tuple[np.ndarray, np.ndarray]:
    w = np.asarray(w1326, float).copy()
    w[blocked_mask(tuple(sorted(board)))] = 0
    idx = np.nonzero(w > 1e-4)[0]
    return idx, w[idx]


def solve(board: list[int], oop_w: np.ndarray, ip_w: np.ndarray, pot: float, stack: float,
          oop_bets: list[float], ip_bets: list[float], raise_mult: float = 3.0,
          allow_raise: bool = True, add_allin: bool = False, iterations: int = 400,
          villain_is: int = 1, villain_profile: Profile | None = None,
          hero_combo: tuple[int, int] | None = None, exploit_strength: float = 1.0) -> dict:
    t_start = time.time()
    if len(board) not in (3, 4, 5):
        raise ValueError("board must have 3-5 cards")
    hero_is = 1 - villain_is
    ws = [np.asarray(oop_w, float).copy(), np.asarray(ip_w, float).copy()]
    hero_ci = None
    if hero_combo is not None:
        from .cards import COMBO_INDEX
        hero_ci = COMBO_INDEX[tuple(sorted(hero_combo))]
        if set(hero_combo) & set(board):
            raise ValueError("hero hand conflicts with the board")
        if ws[hero_is][hero_ci] < 1e-3:
            ws[hero_is][hero_ci] = 1e-3   # include with negligible weight so we can report it
    idx0, w0 = _prep_range(ws[0], board)
    idx1, w1 = _prep_range(ws[1], board)
    if len(idx0) == 0 or len(idx1) == 0:
        raise ValueError("a range is empty after removing board cards")

    runouts = 220 if len(board) == 3 else 1000
    E_raw, M = combo_matrix(idx0, idx1, board, max_runouts=runouts)
    # equity realization approx for future streets: OOP under-realizes
    R_oop = {3: 0.90, 4: 0.95, 5: 1.0}[len(board)]
    E = np.where(M > 0, E_raw * R_oop / np.maximum(E_raw * R_oop + (1 - E_raw), 1e-12), 0) * M

    nodes = build_tree(pot, stack, oop_bets, ip_bets, raise_mult, allow_raise, add_allin)
    gto = Solver(nodes, pot, E, M, w0, w1)
    it_done = gto.run(iterations)
    ev0, ev1 = gto.value(0), gto.value(1)
    br0, br1 = gto.best_response_value(0), gto.best_response_value(1)
    exploitability = max(0.0, (br0 - ev0) + (br1 - ev1)) / 2

    gto_rep = gto.node_reports()

    # ---- exploit: lock villain nodes to profile-shifted equilibrium, re-solve hero
    exp_rep = None
    ex_info = None
    if villain_profile is not None and villain_profile.key != "gto":
        a_ = float(np.clip(exploit_strength, 0, 1))
        pr = Profile(**{**villain_profile.__dict__,
                        "fold": villain_profile.fold * a_, "bet": villain_profile.bet * a_,
                        "raise_": villain_profile.raise_ * a_})
        ex = Solver(nodes, pot, E, M, w0, w1)
        for nd in nodes:
            if nd.kind == "action" and nd.player == villain_is:
                ex.locked[nd.id] = lock_strategy(gto.average(nd.id), nd.actions, nd.node_type, pr)
        # warm start hero from GTO
        for nd in nodes:
            if nd.kind == "action" and nd.player == hero_is:
                ex.ssum[nd.id] = gto.average(nd.id) * gto.w[hero_is][:, None] * 5
        ex.run(max(150, iterations // 2))
        exp_rep = ex.node_reports()
        hv_gto_vs_locked = _value_hero_gto_vs_locked(gto, ex, hero_is)
        ex_info = {"hero_ev_exploit": ex.value(hero_is), "hero_ev_gto_vs_profile": hv_gto_vs_locked,
                   "hero_ev_gto": gto.value(hero_is)}

    # ---- packaging
    combos = [idx0, idx1]
    cats = []
    for p in (0, 1):
        cl = []
        for ci in combos[p]:
            cl.append(classify(ALL_COMBOS[ci], board))
        cats.append(cl)

    eq_raw = [_eq_vs(E_raw, M, w1, axis=0), _eq_vs((M - E_raw).T, M.T, w0, axis=0)]
    range_eq = [float((eq_raw[0] * w0 * (M @ w1)).sum() / max((w0 * (M @ w1)).sum(), 1e-12))]
    range_eq.append(1 - range_eq[0])

    eqm = [(E_raw, M), ((M - E_raw).T, M.T)]
    out_nodes = []
    for nd in nodes:
        if nd.kind != "action":
            continue
        p = nd.player
        entry = {
            "id": nd.id, "player": "OOP" if p == 0 else "IP", "player_idx": p,
            "is_hero": p == hero_is, "path": nd.path, "node_type": nd.node_type,
            "pot": round(pot + nd.c[0] + nd.c[1], 2),
            "to_call": round(max(nd.c) - nd.c[p], 2),
            "actions": [{"key": k, "label": l, "amount": a} for k, l, a in nd.actions],
            "children": [c if nodes[c].kind == "action" else None for c in nd.children],
            "gto": _pack_node(gto_rep[nd.id], combos[p], cats[p], eq_raw[p], *eqm[p]),
        }
        entry["gto"]["opp"] = opp_range(gto_rep[nd.id]["reach_opp"], combos[1 - p], cats[1 - p])
        if exp_rep is not None:
            entry["exploit"] = _pack_node(exp_rep[nd.id], combos[p], cats[p], eq_raw[p], *eqm[p])
            entry["exploit"]["opp"] = opp_range(exp_rep[nd.id]["reach_opp"], combos[1 - p], cats[1 - p])
            entry["locked"] = p == villain_is
        out_nodes.append(entry)

    hero_report = None
    if hero_ci is not None:
        hero_report = _hero_report(hero_ci, combos[hero_is], cats[hero_is], eq_raw[hero_is], gto_rep,
                                   exp_rep, nodes, hero_is)

    return {
        "board": board,
        "texture": board_texture(board),
        "pot": pot, "stack": stack,
        "hero": "OOP" if hero_is == 0 else "IP",
        "iterations": it_done,
        "exploitability_pct_pot": round(100 * exploitability / pot, 3),
        "range_equity": {"OOP": round(range_eq[0], 4), "IP": round(range_eq[1], 4)},
        "ev": {"OOP": round(ev0, 3), "IP": round(ev1, 3)},
        "exploit_info": ex_info and {k: round(v, 3) for k, v in ex_info.items()},
        "ranges": [_range_summary(combos[p], (w0, w1)[p], cats[p], eq_raw[p]) for p in (0, 1)],
        "nodes": out_nodes,
        "hero_hand": hero_report,
        "elapsed": round(time.time() - t_start, 2),
    }


def _value_hero_gto_vs_locked(gto: Solver, ex: Solver, hero: int) -> float:
    tmp = Solver(gto.nodes, gto.pot, gto.E[0], gto.M[0], gto.w[0], gto.w[1])
    for nd in gto.nodes:
        if nd.kind == "action":
            tmp.locked[nd.id] = ex.locked[nd.id] if nd.id in ex.locked else gto.average(nd.id)
    return tmp.value(hero)


def _eq_vs(E, M, w_opp, axis=0):
    den = M @ w_opp
    return np.divide(E @ w_opp, den, out=np.zeros(len(den)), where=den > 0)


OPP_BUCKETS = ["Two pair+", "Top pair / overpair", "Weaker pair", "Draw", "Air"]
_STRONG = {"Straight flush", "Quads", "Full house", "Flush", "Straight", "Set", "Trips", "Two pair"}
_DRAWS = {"Combo draw", "Flush draw", "OESD", "Gutshot"}


def _bucket(made: str, draw: str) -> int:
    if made in _STRONG:
        return 0
    if made in ("Overpair", "Top pair"):
        return 1
    if made in ("Middle pair", "Weak pair"):
        return 2
    return 3 if draw in _DRAWS else 4


def opp_range(reach, combos, cats):
    """Opponent's range at a node (169 grid, coloured by hand-strength bucket)."""
    reach = np.asarray(reach, dtype=np.float64)
    cls = COMBO_CLASS[combos]
    bk = np.array([_bucket(m, d) for m, d in cats])
    wsum = np.bincount(cls, weights=reach, minlength=169)
    per = [np.bincount(cls, weights=reach * (bk == b), minlength=169) for b in range(len(OPP_BUCKETS))]
    total = reach.sum()
    grid = [None if wsum[k] <= 1e-9 else {"w": round(float(wsum[k] / CLASS_NCOMBOS[k]), 4),
                                          "f": [round(float(g[k] / wsum[k]), 3) for g in per]} for k in range(169)]
    return {"grid": grid, "legend": OPP_BUCKETS,
            "summary": [round(float(g.sum() / total), 4) if total > 0 else 0 for g in per],
            "combos": round(float(total), 1)}


def _pack_node(rep, combos, cats, eq, Ep=None, Mp=None):
    reach = rep["reach_actor"]
    strat = rep["strategy"]
    ev = rep["ev"]
    # equity vs the hands villain actually holds at this node (his range narrowed by the line)
    if Ep is not None:
        ro = np.asarray(rep["reach_opp"], dtype=np.float64)
        den = np.asarray(Mp, dtype=np.float64) @ ro
        eq_node = np.divide(np.asarray(Ep, dtype=np.float64) @ ro, den, out=np.zeros(len(den)), where=den > 1e-12)
    else:
        eq_node = eq
    total = reach.sum()
    # per combo arrays (only those with reach)
    alive = np.nonzero(reach > 1e-6)[0]
    combo_rows = []
    for i in alive:
        combo_rows.append([combo_str(ALL_COMBOS[combos[i]]), round(float(reach[i]), 4),
                           [round(float(x), 3) for x in strat[i]],
                           [round(float(x), 3) for x in ev[i]],
                           round(float(eq[i]), 3), cats[i][0], cats[i][1],
                           int(COMBO_CLASS[combos[i]]), round(float(eq_node[i]), 3)])
    # 169 aggregation
    cls = COMBO_CLASS[combos]
    A = strat.shape[1]
    wsum = np.bincount(cls, weights=reach, minlength=169)
    grid = []
    for a in range(A):
        grid.append(np.bincount(cls, weights=reach * strat[:, a], minlength=169))
    evc = np.bincount(cls, weights=reach * (strat * ev).sum(axis=1), minlength=169)
    grid_out = []
    for k in range(169):
        if wsum[k] <= 1e-9:
            grid_out.append(None)
            continue
        grid_out.append({
            "w": round(float(wsum[k] / CLASS_NCOMBOS[k]), 4),
            "f": [round(float(g[k] / wsum[k]), 3) for g in grid],
            "ev": round(float(evc[k] / wsum[k]), 3),
        })
    summary = [round(float((reach * strat[:, a]).sum() / total), 4) if total > 0 else 0 for a in range(A)]
    # category breakdown
    catb = {}
    for i in alive:
        for key in (cats[i][0], cats[i][1]):
            d = catb.setdefault(key, {"w": 0.0, "f": np.zeros(A)})
            d["w"] += reach[i]
            d["f"] += reach[i] * strat[i]
    cat_out = []
    for name in MADE_CATS + DRAW_CATS:
        if name in catb and catb[name]["w"] > 1e-9:
            d = catb[name]
            cat_out.append({"name": name, "kind": "draw" if name in DRAW_CATS else "made",
                            "pct": round(float(d["w"] / total), 4),
                            "f": [round(float(x / d["w"]), 3) for x in d["f"]]})
    return {"summary": summary, "combos": combo_rows, "grid": grid_out, "categories": cat_out,
            "range_combos": round(float(total), 2)}


def _range_summary(combos, w, cats, eq):
    total = w.sum()
    buckets = np.zeros(10)
    for i in range(len(combos)):
        buckets[min(9, int(eq[i] * 10))] += w[i]
    cat = {}
    for i in range(len(combos)):
        cat[cats[i][0]] = cat.get(cats[i][0], 0) + w[i]
    order = np.argsort(eq)
    cum = np.cumsum(w[order]) / total
    curve = []
    for q in np.linspace(0, 1, 41):
        j = min(len(order) - 1, int(np.searchsorted(cum, q)))
        curve.append(round(float(eq[order[j]]), 3))
    nut = float(w[eq >= 0.8].sum() / total)
    return {
        "combos": round(float(total), 1),
        "equity_buckets": [round(float(b / total), 4) for b in buckets],
        "equity_curve": curve,
        "made": [{"name": n, "pct": round(float(cat[n] / total), 4)} for n in MADE_CATS if n in cat],
        "nut_share": round(nut, 4),
    }


def _hero_report(hero_ci, combos, cats, eq, gto_rep, exp_rep, nodes, hero_is):
    pos = np.nonzero(combos == hero_ci)[0]
    if len(pos) == 0:
        return None
    i = int(pos[0])
    out = {"combo": combo_str(ALL_COMBOS[hero_ci]), "equity": round(float(eq[i]), 4),
           "made": cats[i][0], "draw": cats[i][1], "nodes": {}}
    for nd in nodes:
        if nd.kind != "action" or nd.player != hero_is:
            continue
        g = gto_rep[nd.id]
        entry = {"gto": [round(float(x), 3) for x in g["strategy"][i]],
                 "ev_gto": [round(float(x), 3) for x in g["ev"][i]]}
        if exp_rep is not None:
            e = exp_rep[nd.id]
            entry["exploit"] = [round(float(x), 3) for x in e["strategy"][i]]
            entry["ev_exploit"] = [round(float(x), 3) for x in e["ev"][i]]
        out["nodes"][nd.id] = entry
    return out
