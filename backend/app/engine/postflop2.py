"""Exact two-street solver (turn + river), vectorized CFR+.

Starting from a 4-card board, the turn betting tree is played out; whenever the turn ends with
chips behind (check-check or a non all-in call) a chance node deals each of the remaining river
cards and a full river betting tree follows. Unlike the single-street solver there is no
equity-realization approximation: every terminal is either a fold or a real showdown on the
river (or an all-in on the turn, valued by exact enumeration of the river).

Performance design
------------------
All river subtrees share one batch dimension R (one slot per river card). Each CFR traversal is
done in two passes:
  1. top-down: propagate reach probabilities through the whole tree (turn + all rivers);
  2. evaluate every river showdown terminal in ONE batched matmul  W[r] @ reach[r, :, k]
     (the (R, n0, n1) win tensor is read once per traversal), then
  3. bottom-up: back up values, update regrets (CFR+) and the linear-weighted average strategy.
"""
from __future__ import annotations

import copy
import time

import numpy as np

from .cards import ALL_COMBOS, COMBO_ARR, card_to_str
from .evaluator import evaluate7
from .handclass import board_texture, classify
from .postflop import Node, _pack_node, opp_range, _prep_range, _range_summary, build_tree, lock_strategy
from .profiles import Profile

F32 = np.float32
MAX_TENSOR_BYTES = 450e6


# ------------------------------------------------------------------ tree
def build_two_street(pot, stack, turn_oop, turn_ip, river_oop, river_ip, raise_mult, allow_raise,
                     add_allin) -> list[Node]:
    turn = build_tree(pot, stack, turn_oop, turn_ip, raise_mult, allow_raise, add_allin)
    nodes: list[Node] = []
    for nd in turn:
        n = copy.copy(nd)
        n.actions = list(nd.actions)
        n.children = list(nd.children)
        n.river = False
        n.pot = pot
        nodes.append(n)
    for n in list(nodes):
        if n.kind != "showdown":
            continue
        left = stack - max(n.c)
        if left <= 1e-9:
            n.kind = "allin"
            continue
        n.kind = "chance"
        rpot = pot + n.c[0] + n.c[1]
        river = build_tree(rpot, left, river_oop, river_ip, raise_mult, allow_raise, add_allin)
        off = len(nodes)
        for rn in river:
            m = copy.copy(rn)
            m.id = rn.id + off
            m.children = [c + off for c in rn.children]
            m.actions = list(rn.actions)
            m.river = True
            m.pot = rpot
            m.chance = n.id
            m.base_c = n.c          # turn chips already invested (utilities are turn-relative)
            m.path = list(n.path) + ["River"] + list(rn.path)
            nodes.append(m)
        n.children = [off]
    return nodes


# ------------------------------------------------------------------ solver
class TwoStreetSolver:
    def __init__(self, nodes, board, idx, w, rivers, W0, alive, M, share=None):
        # the training loop runs in float32 (memory-bandwidth bound); reported values are float64
        w = [np.asarray(x, F32) for x in w]
        alive = [np.asarray(x, F32) for x in alive]
        M = np.asarray(M, F32)
        self.nodes = nodes
        self.board = board
        self.idx = idx
        self.w = w
        self.rivers = rivers
        self.R = len(rivers)
        self.alive = alive                      # [ (R, n0), (R, n1) ] float
        self.n_valid_rivers = 52 - len(board) - 4   # every valid pair sees exactly 44 rivers
        if share is not None:
            self.M, self.W, self.Et = share.M, share.W, share.Et
        else:
            self.M = [M, M.T.copy()]
            Mr = (M[None, :, :] * alive[0][:, :, None] * alive[1][:, None, :]).astype(F32)
            W1 = np.ascontiguousarray(np.transpose(Mr - W0, (0, 2, 1)))
            del Mr
            self.W = [W0, W1]
            self.Et = [(W0.sum(axis=0, dtype=np.float64) / self.n_valid_rivers).astype(F32),
                       (W1.sum(axis=0, dtype=np.float64) / self.n_valid_rivers).astype(F32)]
        self.reg, self.ssum, self.locked = {}, {}, {}
        n = [len(w[0]), len(w[1])]
        self.n = n
        for nd in nodes:
            if nd.kind == "action":
                shape = ((self.R,) if nd.river else ()) + (n[nd.player], len(nd.actions))
                self.reg[nd.id] = np.zeros(shape, F32)
                self.ssum[nd.id] = np.zeros(shape, F32)
        self.river_sd = [nd for nd in nodes if nd.river and nd.kind == "showdown"]
        self.river_term = [nd for nd in nodes if nd.river and nd.kind in ("showdown", "fold")]
        self.Z = float(w[0].astype(np.float64) @ M.astype(np.float64) @ w[1].astype(np.float64))
        self._eval_cache = {}
        self._cur = {}
        self.algo = "dcfr"

    # -------- strategies
    @staticmethod
    def _rm(r):
        pos = np.maximum(r, 0)
        s = pos.sum(axis=-1, keepdims=True)
        empty = s <= 0
        return pos / np.where(empty, 1, s) + empty * (1.0 / r.shape[-1])

    def current(self, nid):
        if nid in self.locked:
            return self.locked[nid]
        c = self._cur.get(nid)
        if c is None:
            c = self._cur[nid] = self._rm(self.reg[nid])
        return c

    def average(self, nid):
        if nid in self.locked:
            return self.locked[nid]
        s = self.ssum[nid]
        tot = s.sum(axis=-1, keepdims=True)
        return np.where(tot > 0, s / np.where(tot > 0, tot, 1), 1.0 / s.shape[-1])

    # -------- passes
    def _down(self, p, sigma_fn):
        N = len(self.nodes)
        rp, ro, sig = [None] * N, [None] * N, {}
        rp[0], ro[0] = self.w[p], self.w[1 - p]
        for nd in self.nodes:
            i = nd.id
            if rp[i] is None:
                continue
            if nd.kind == "action":
                s = sigma_fn(i)
                sig[i] = s
                for a, ch in enumerate(nd.children):
                    if nd.player == p:
                        rp[ch], ro[ch] = rp[i] * s[..., a], ro[i]
                    else:
                        rp[ch], ro[ch] = rp[i], ro[i] * s[..., a]
            elif nd.kind == "chance":
                ch = nd.children[0]
                rp[ch] = rp[i][None, :] * self.alive[p]
                ro[ch] = ro[i][None, :] * self.alive[1 - p]
        return rp, ro, sig

    def _terminals(self, p, ro):
        vals = {}
        Mp = self.M[p]
        if self.river_term:
            X = np.stack([ro[nd.id] for nd in self.river_term], axis=0)     # (K, R, n_o)
            K, R, no = X.shape
            mass = (Mp @ X.reshape(K * R, no).T).T.reshape(K, R, -1) * self.alive[p][None]
            mass_of = {nd.id: mass[k] for k, nd in enumerate(self.river_term)}
        if self.river_sd:
            Xs = np.stack([ro[nd.id] for nd in self.river_sd], axis=2).astype(F32)  # (R, n_o, K2)
            Y = np.matmul(self.W[p], Xs)                                            # (R, n_p, K2)
        sd_k = {nd.id: k for k, nd in enumerate(self.river_sd)}
        for nd in self.nodes:
            if nd.kind in ("action", "chance"):
                continue
            i = nd.id
            if nd.river:
                m = mass_of[i]
                base = nd.base_c[p]
                if nd.kind == "fold":
                    vals[i] = ((-nd.c[p] if nd.folder == p else nd.pot + nd.c[nd.folder]) - base) * m
                else:
                    vals[i] = Y[:, :, sd_k[i]] * (nd.pot + nd.c[0] + nd.c[1]) - (nd.c[p] + base) * m
            else:
                m = Mp @ ro[i]
                if nd.kind == "fold":
                    vals[i] = (-nd.c[p] if nd.folder == p else nd.pot + nd.c[nd.folder]) * m
                else:  # turn all-in: exact river enumeration
                    vals[i] = (self.Et[p] @ ro[i]) * (nd.pot + nd.c[0] + nd.c[1]) - nd.c[p] * m
        return vals

    def _up(self, p, rp, sig, vals, mode, t=0):
        action_vals = {}
        for nd in reversed(self.nodes):
            i = nd.id
            if nd.kind == "chance":
                vals[i] = vals[nd.children[0]].sum(axis=0) / self.n_valid_rivers
            elif nd.kind == "action":
                v_all = np.stack([vals[ch] for ch in nd.children], axis=-1)
                if nd.player == p:
                    s = sig[i]
                    v = v_all.max(axis=-1) if mode == "br" else (s * v_all).sum(axis=-1)
                    if mode == "train" and i not in self.locked:
                        r = self.reg[i] + v_all - v[..., None]
                        if self.algo == "dcfr":  # Discounted CFR (alpha=1.5, beta=0, gamma=2)
                            ta = t ** 1.5
                            r *= np.where(r > 0, ta / (ta + 1), 0.5)
                            self.ssum[i] = self.ssum[i] * ((t / (t + 1)) ** 2) + rp[i][..., None] * s
                        else:                    # CFR+ with linear averaging
                            np.maximum(r, 0, out=r)
                            self.ssum[i] += t * rp[i][..., None] * s
                        self.reg[i] = r
                        self._cur.pop(i, None)
                    if mode == "eval":
                        action_vals[i] = v_all
                else:
                    v = v_all.sum(axis=-1)
                vals[i] = v
        return vals, action_vals

    def run(self, iters, time_budget=90.0):
        t0 = time.time()
        for t in range(1, iters + 1):
            for p in (0, 1):
                rp, ro, sig = self._down(p, self.current)
                self._up(p, rp, sig, self._terminals(p, ro), "train", t)
            if time.time() - t0 > time_budget:
                return t
        return iters

    def evaluate(self, p):
        if p not in self._eval_cache:
            rp, ro, sig = self._down(p, self.average)
            vals, av = self._up(p, rp, sig, self._terminals(p, ro), "eval")
            self._eval_cache[p] = {"rp": rp, "ro": ro, "vals": vals, "av": av}
        return self._eval_cache[p]

    def value(self, p):
        return float(self.w[p].astype(np.float64) @ self.evaluate(p)["vals"][0].astype(np.float64) / self.Z)

    def best_response_value(self, p):
        rp, ro, sig = self._down(p, self.average)
        vals, _ = self._up(p, rp, sig, self._terminals(p, ro), "br")
        return float(self.w[p].astype(np.float64) @ vals[0].astype(np.float64) / self.Z)

    def node_report(self, nid, r=None):
        nd = self.nodes[nid]
        p = nd.player
        e = self.evaluate(p)
        rp, ro, av = e["rp"][nid], e["ro"][nid], e["av"][nid]
        strat = self.average(nid)
        if r is None:
            mass = self.M[p] @ ro
        else:
            rp, ro, av, strat = rp[r], ro[r], av[r], strat[r]
            mass = self.alive[p][r] * (self.M[p] @ ro)
        ev = np.divide(av, mass[:, None], out=np.zeros_like(av), where=mass[:, None] > 1e-12)
        return {"reach_actor": rp, "reach_opp": ro, "strategy": strat, "ev": ev}

    def river_equity(self, p, r):
        wo = self.w[1 - p] * self.alive[1 - p][r]
        mass = self.alive[p][r] * (self.M[p] @ wo)
        num = self.W[p][r].astype(np.float64) @ wo
        return np.divide(num, mass, out=np.zeros_like(num), where=mass > 0)


# ------------------------------------------------------------------ setup
def _river_tensor(board, idx0, idx1, M):
    rivers = [c for c in range(52) if c not in board]
    c0 = COMBO_ARR[idx0].astype(np.int64)
    c1 = COMBO_ARR[idx1].astype(np.int64)
    R, n0, n1 = len(rivers), len(idx0), len(idx1)
    if R * n0 * n1 * 4 * 2 > MAX_TENSOR_BYTES:
        raise ValueError(f"ranges too wide for an exact turn+river solve ({n0}x{n1} combos); "
                         "narrow a range or disable 'solve river exactly'")
    W0 = np.zeros((R, n0, n1), dtype=F32)
    alive0 = np.zeros((R, n0))
    alive1 = np.zeros((R, n1))
    b = np.array(board, dtype=np.int64)
    for k, rc in enumerate(rivers):
        full = np.concatenate([b, [rc]])
        a0 = ~(c0 == rc).any(axis=1)
        a1 = ~(c1 == rc).any(axis=1)
        s0 = evaluate7(np.concatenate([c0, np.broadcast_to(full, (n0, 5))], axis=1))
        s1 = evaluate7(np.concatenate([c1, np.broadcast_to(full, (n1, 5))], axis=1))
        d = s0[:, None] - s1[None, :]
        valid = M * a0[:, None] * a1[None, :]
        W0[k] = ((d > 0) + 0.5 * (d == 0)) * valid
        alive0[k], alive1[k] = a0, a1
    return rivers, W0, [alive0, alive1]


# ------------------------------------------------------------------ public API
def solve_turn(board, oop_w, ip_w, pot, stack, turn_oop, turn_ip, river_oop, river_ip,
               raise_mult=3.0, allow_raise=True, add_allin=False, iterations=200,
               villain_is=1, villain_profile: Profile | None = None, hero_combo=None,
               exploit_strength=1.0, time_budget=90.0):
    t_start = time.time()
    if len(board) != 4:
        raise ValueError("exact turn+river solving needs a 4-card board")
    hero_is = 1 - villain_is
    ws = [np.asarray(oop_w, float).copy(), np.asarray(ip_w, float).copy()]
    hero_ci = None
    if hero_combo is not None:
        from .cards import COMBO_INDEX
        if set(hero_combo) & set(board):
            raise ValueError("hero hand conflicts with the board")
        hero_ci = COMBO_INDEX[tuple(sorted(hero_combo))]
        if ws[hero_is][hero_ci] < 1e-3:
            ws[hero_is][hero_ci] = 1e-3
    idx0, w0 = _prep_range(ws[0], board)
    idx1, w1 = _prep_range(ws[1], board)
    if len(idx0) == 0 or len(idx1) == 0:
        raise ValueError("a range is empty after removing board cards")
    c0, c1 = COMBO_ARR[idx0].astype(np.int64), COMBO_ARR[idx1].astype(np.int64)
    M = (~(c0[:, None, :, None] == c1[None, :, None, :]).any(axis=(2, 3))).astype(np.float64)

    rivers, W0, alive = _river_tensor(board, idx0, idx1, M)
    nodes = build_two_street(pot, stack, turn_oop, turn_ip, river_oop, river_ip, raise_mult,
                             allow_raise, add_allin)
    gto = TwoStreetSolver(nodes, board, [idx0, idx1], [w0, w1], rivers, W0, alive, M)
    it_done = gto.run(iterations, time_budget)
    ev0, ev1 = gto.value(0), gto.value(1)
    br0, br1 = gto.best_response_value(0), gto.best_response_value(1)
    exploitability = max(0.0, (br0 - ev0) + (br1 - ev1)) / 2

    ex = None
    ex_info = None
    if villain_profile is not None and villain_profile.key != "gto":
        a_ = float(np.clip(exploit_strength, 0, 1))
        pr = Profile(**{**villain_profile.__dict__, "fold": villain_profile.fold * a_,
                        "bet": villain_profile.bet * a_, "raise_": villain_profile.raise_ * a_})
        ex = TwoStreetSolver(nodes, board, [idx0, idx1], [w0, w1], rivers, None, alive, M, share=gto)
        for nd in nodes:
            if nd.kind != "action":
                continue
            avg = gto.average(nd.id)
            if nd.player == villain_is:
                flat = avg.reshape(-1, avg.shape[-1])
                ex.locked[nd.id] = lock_strategy(flat, nd.actions, nd.node_type, pr).reshape(avg.shape)
            else:
                rp = gto.evaluate(hero_is)["rp"][nd.id]
                ex.ssum[nd.id] = avg * rp[..., None] * 5
        ex.run(max(80, iterations // 2), time_budget / 2)
        tmp = TwoStreetSolver(nodes, board, [idx0, idx1], [w0, w1], rivers, None, alive, M, share=gto)
        for nd in nodes:
            if nd.kind == "action":
                tmp.locked[nd.id] = ex.locked.get(nd.id, gto.average(nd.id))
        ex_info = {"hero_ev_exploit": ex.value(hero_is), "hero_ev_gto_vs_profile": tmp.value(hero_is),
                   "hero_ev_gto": gto.value(hero_is)}

    combos = [idx0, idx1]
    cats = [[classify(ALL_COMBOS[ci], board) for ci in combos[p]] for p in (0, 1)]
    eq_raw = []
    for p in (0, 1):
        wo = (w0, w1)[1 - p]
        mass = gto.M[p] @ wo
        eq_raw.append(np.divide(gto.Et[p] @ wo, mass, out=np.zeros(len(mass)), where=mass > 0))
    tot = (w0 * (gto.M[0] @ w1)).sum()
    range_eq0 = float((eq_raw[0] * w0 * (gto.M[0] @ w1)).sum() / max(tot, 1e-12))

    out_nodes = []
    for nd in nodes:
        if nd.kind != "action" or nd.river:
            continue
        out_nodes.append(_node_entry(nd, nodes, gto, ex, combos, cats, eq_raw, hero_is, villain_is, None, pot))

    hero_report = None
    if hero_ci is not None:
        hero_report = _hero(gto, ex, hero_ci, hero_is, combos, cats, eq_raw, None)

    result = {
        "board": board,
        "texture": board_texture(board),
        "pot": pot, "stack": stack,
        "hero": "OOP" if hero_is == 0 else "IP",
        "mode": "turn_river",
        "iterations": it_done,
        "exploitability_pct_pot": round(100 * exploitability / pot, 3),
        "range_equity": {"OOP": round(range_eq0, 4), "IP": round(1 - range_eq0, 4)},
        "ev": {"OOP": round(ev0, 3), "IP": round(ev1, 3)},
        "exploit_info": ex_info and {k: round(v, 3) for k, v in ex_info.items()},
        "ranges": [_range_summary(combos[p], (w0, w1)[p], cats[p], eq_raw[p]) for p in (0, 1)],
        "nodes": out_nodes,
        "hero_hand": hero_report,
        "rivers": [card_to_str(c) for c in rivers],
        "elapsed": round(time.time() - t_start, 2),
    }
    state = {"gto": gto, "ex": ex, "combos": combos, "hero_is": hero_is, "villain_is": villain_is,
             "hero_ci": hero_ci, "pot": pot}
    return result, state


def _children_out(nd, nodes):
    out = []
    for c in nd.children:
        k = nodes[c].kind
        out.append(c if k == "action" else {"chance": c, "river_root": nodes[c].children[0]} if k == "chance" else None)
    return out


def _node_entry(nd, nodes, gto, ex, combos, cats, eq, hero_is, villain_is, r, pot):
    p = nd.player
    entry = {
        "id": nd.id, "player": "OOP" if p == 0 else "IP", "player_idx": p,
        "is_hero": p == hero_is, "path": nd.path, "node_type": nd.node_type,
        "pot": round(nd.pot + nd.c[0] + nd.c[1], 2),
        "to_call": round(max(nd.c) - nd.c[p], 2),
        "actions": [{"key": k, "label": l, "amount": a} for k, l, a in nd.actions],
        "children": _children_out(nd, nodes),
        "street": "river" if nd.river else "turn",
    }
    g = gto.node_report(nd.id, r)
    entry["gto"] = _pack_node(g, combos[p], cats[p], eq[p], *_eqm(gto, p, r))
    entry["gto"]["opp"] = opp_range(g["reach_opp"], combos[1 - p], cats[1 - p])
    if ex is not None:
        x = ex.node_report(nd.id, r)
        entry["exploit"] = _pack_node(x, combos[p], cats[p], eq[p], *_eqm(gto, p, r))
        entry["exploit"]["opp"] = opp_range(x["reach_opp"], combos[1 - p], cats[1 - p])
        entry["locked"] = p == villain_is
    return entry


def _eqm(solver, p, r):
    """(equity matrix, valid mask) from p's perspective: exact turn equity, or one river."""
    if r is None:
        return solver.Et[p], solver.M[p]
    return solver.W[p][r], solver.M[p]


def _hero(gto, ex, hero_ci, hero_is, combos, cats, eq, r, chance=None):
    pos = np.nonzero(combos[hero_is] == hero_ci)[0]
    if len(pos) == 0:
        return None
    i = int(pos[0])
    from .cards import combo_str
    out = {"combo": combo_str(ALL_COMBOS[hero_ci]), "equity": round(float(eq[hero_is][i]), 4),
           "made": cats[hero_is][i][0], "draw": cats[hero_is][i][1], "nodes": {}}
    for nd in gto.nodes:
        if nd.kind != "action" or nd.player != hero_is:
            continue
        if (r is None) != (not nd.river):
            continue
        if r is not None and getattr(nd, "chance", None) != chance:
            continue
        if r is not None and gto.alive[hero_is][r][i] == 0:
            return None
        g = gto.node_report(nd.id, r)
        e = {"gto": [round(float(x), 3) for x in g["strategy"][i]],
             "ev_gto": [round(float(x), 3) for x in g["ev"][i]]}
        if ex is not None:
            x = ex.node_report(nd.id, r)
            e["exploit"] = [round(float(v), 3) for v in x["strategy"][i]]
            e["ev_exploit"] = [round(float(v), 3) for v in x["ev"][i]]
        out["nodes"][nd.id] = e
    return out


def river_view(state, chance_id: int, river_card: int) -> dict:
    gto, ex = state["gto"], state["ex"]
    nodes = gto.nodes
    if nodes[chance_id].kind != "chance":
        raise ValueError("not a chance node")
    if river_card not in gto.rivers:
        raise ValueError("that river card is on the board")
    r = gto.rivers.index(river_card)
    board5 = gto.board + [river_card]
    combos, hero_is, villain_is = state["combos"], state["hero_is"], state["villain_is"]
    cats = [[classify(ALL_COMBOS[ci], board5) for ci in combos[p]] for p in (0, 1)]
    eq = [gto.river_equity(p, r) for p in (0, 1)]
    out = []
    for nd in nodes:
        if nd.kind == "action" and nd.river and nd.chance == chance_id:
            entry = _node_entry(nd, nodes, gto, ex, combos, cats, eq, hero_is, villain_is, r, state["pot"])
            # hide river-dead combos (contain the river card)
            out.append(entry)
    hero = None
    if state["hero_ci"] is not None:
        hero = _hero(gto, ex, state["hero_ci"], hero_is, combos, cats, eq, r, chance=chance_id)
    # range equity on this river at the chance node
    rp = gto.evaluate(0)["rp"][nodes[chance_id].children[0]][r]
    ro = gto.evaluate(0)["ro"][nodes[chance_id].children[0]][r]
    m = gto.alive[0][r] * (gto.M[0] @ ro)
    den = (rp * m).sum()
    req = float((rp * eq[0] * m).sum() / den) if den > 0 else 0.5
    return {"river": card_to_str(river_card), "chance": chance_id, "root": nodes[chance_id].children[0],
            "nodes": out, "hero_hand": hero, "texture": board_texture(board5),
            "range_equity": {"OOP": round(req, 4), "IP": round(1 - req, 4)}}
