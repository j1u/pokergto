"""Equity computations.

* preflop_matrix(): 169x169 all-in equity of hand class i vs class j (Monte Carlo, cached to disk).
* combo_matrix(): exact/sampled equity of every hero combo vs every villain combo on a board.
"""
from __future__ import annotations

import logging
import math
from itertools import combinations
from pathlib import Path

import numpy as np

from .cards import ALL_COMBOS, CLASS_COMBOS, COMBO_ARR, blocked_mask
from .evaluator import evaluate7

log = logging.getLogger("equity")
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PRE_PATH = DATA_DIR / "preflop_equity_169.npy"

_PRE: np.ndarray | None = None


def _compute_preflop_matrix(samples: int = 2600, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pad = np.full((169, 12), -1, dtype=np.int64)
    cnt = np.zeros(169, dtype=np.int64)
    for k, lst in enumerate(CLASS_COMBOS):
        pad[k, :len(lst)] = lst
        cnt[k] = len(lst)
    pairs = np.array([(i, j) for i in range(169) for j in range(i, 169)], dtype=np.int64)
    wins = np.zeros(len(pairs))
    tot = np.zeros(len(pairs))
    chunk_pairs = 400
    for start in range(0, len(pairs), chunk_pairs):
        p = pairs[start:start + chunk_pairs]
        pid = np.repeat(np.arange(len(p)), samples)
        ci, cj = p[pid, 0], p[pid, 1]
        hi = pad[ci, rng.integers(0, 1 << 30, len(pid)) % cnt[ci]]
        hj = pad[cj, rng.integers(0, 1 << 30, len(pid)) % cnt[cj]]
        a = COMBO_ARR[hi].astype(np.int64)
        b = COMBO_ARR[hj].astype(np.int64)
        board = rng.integers(0, 52, (len(pid), 5))
        allc = np.concatenate([a, b, board], axis=1)
        s = np.sort(allc, axis=1)
        ok = (np.diff(s, axis=1) != 0).all(axis=1)
        a, b, board, pid2 = a[ok], b[ok], board[ok], pid[ok]
        sa = evaluate7(np.concatenate([a, board], axis=1))
        sb = evaluate7(np.concatenate([b, board], axis=1))
        res = (sa > sb) + 0.5 * (sa == sb)
        wins[start:start + len(p)] += np.bincount(pid2, weights=res, minlength=len(p))
        tot[start:start + len(p)] += np.bincount(pid2, minlength=len(p))
    eq = wins / np.maximum(tot, 1)
    m = np.zeros((169, 169))
    m[pairs[:, 0], pairs[:, 1]] = eq
    m[pairs[:, 1], pairs[:, 0]] = 1 - eq
    np.fill_diagonal(m, 0.5)
    return m


def preflop_matrix() -> np.ndarray:
    """169x169 matrix: M[i, j] = equity of class i vs class j."""
    global _PRE
    if _PRE is None:
        if PRE_PATH.exists():
            _PRE = np.load(PRE_PATH)
        else:
            log.warning("Computing preflop equity matrix (one-time, ~1 min)...")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _PRE = _compute_preflop_matrix()
            np.save(PRE_PATH, _PRE)
            log.warning("Preflop equity matrix cached to %s", PRE_PATH)
    return _PRE


def preflop_eq_vs_range(range169: np.ndarray) -> np.ndarray:
    """Equity of each of the 169 classes vs a class-weighted range (combo-weighted)."""
    from .cards import CLASS_NCOMBOS
    m = preflop_matrix()
    w = np.asarray(range169, dtype=np.float64) * CLASS_NCOMBOS
    s = w.sum()
    if s <= 0:
        return np.full(169, 0.5)
    return m @ w / s


# ------------------------------------------------------------------ postflop
def _runouts(board: list[int], dead: set[int], max_runouts: int, rng) -> np.ndarray:
    need = 5 - len(board)
    deck = [c for c in range(52) if c not in dead]
    if need == 0:
        return np.zeros((1, 0), dtype=np.int64)
    total = math.comb(len(deck), need)
    if total <= max_runouts:
        return np.array(list(combinations(deck, need)), dtype=np.int64)
    deck_arr = np.array(deck)
    out = set()
    while len(out) < max_runouts:
        pick = tuple(sorted(rng.choice(deck_arr, need, replace=False).tolist()))
        out.add(pick)
    return np.array(sorted(out), dtype=np.int64)


def combo_matrix(h_idx: np.ndarray, v_idx: np.ndarray, board: list[int],
                 max_runouts: int = 300, seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    """Return (E, M): E[h, v] equity of hero combo h vs villain combo v, M valid-pair mask.

    h_idx / v_idx are indices into ALL_COMBOS (already filtered for board conflicts).
    Flop: sampled runouts; turn/river: exact enumeration.
    """
    rng = np.random.default_rng(seed)
    h_cards = COMBO_ARR[h_idx].astype(np.int64)
    v_cards = COMBO_ARR[v_idx].astype(np.int64)
    nh, nv = len(h_idx), len(v_idx)
    runs = _runouts(board, set(board), max_runouts, rng)
    b = np.array(board, dtype=np.int64)

    win = np.zeros((nh, nv), dtype=np.float64)
    cnt = np.zeros((nh, nv), dtype=np.float64)
    batch = max(1, 200_000 // max(nh + nv, 1))
    for s in range(0, len(runs), batch):
        rr = runs[s:s + batch]                              # (R, need)
        R = len(rr)
        full = np.concatenate([np.broadcast_to(b, (R, len(b))), rr], axis=1)  # (R,5)
        hb = np.concatenate([np.broadcast_to(h_cards, (R, nh, 2)),
                             np.broadcast_to(full[:, None, :], (R, nh, 5))], axis=2)
        vb = np.concatenate([np.broadcast_to(v_cards, (R, nv, 2)),
                             np.broadcast_to(full[:, None, :], (R, nv, 5))], axis=2)
        hs = evaluate7(hb.reshape(-1, 7)).reshape(R, nh)
        vs = evaluate7(vb.reshape(-1, 7)).reshape(R, nv)
        if rr.shape[1]:
            hv = ~((h_cards[None, :, :, None] == rr[:, None, None, :]).any(axis=(2, 3)))  # (R,nh)
            vv = ~((v_cards[None, :, :, None] == rr[:, None, None, :]).any(axis=(2, 3)))
        else:
            hv = np.ones((R, nh), bool)
            vv = np.ones((R, nv), bool)
        for k in range(R):
            valid = np.outer(hv[k], vv[k])
            d = hs[k][:, None] - vs[k][None, :]
            win += valid * ((d > 0) + 0.5 * (d == 0))
            cnt += valid
    # pair conflicts (shared hole cards)
    conflict = (h_cards[:, None, :, None] == v_cards[None, :, None, :]).any(axis=(2, 3))
    M = (cnt > 0) & ~conflict
    E = np.divide(win, cnt, out=np.zeros_like(win), where=cnt > 0) * M
    return E, M.astype(np.float64)


def alive_combos(board: list[int], extra_dead: list[int] | None = None) -> np.ndarray:
    dead = tuple(sorted(set(board) | set(extra_dead or [])))
    return np.nonzero(~blocked_mask(dead))[0]


def hand_vs_range(hero: tuple[int, int], v_weights: np.ndarray, board: list[int],
                  max_runouts: int = 600) -> float:
    """Equity of a specific hand vs a 1326-weighted range."""
    dead = set(board) | set(hero)
    alive = np.array([i for i in np.nonzero(v_weights > 1e-6)[0]
                      if ALL_COMBOS[i][0] not in dead and ALL_COMBOS[i][1] not in dead])
    if len(alive) == 0:
        return float("nan")
    from .cards import COMBO_INDEX
    h = np.array([COMBO_INDEX[tuple(sorted(hero))]])
    E, M = combo_matrix(h, alive, board, max_runouts=max_runouts)
    w = v_weights[alive]
    den = (M[0] * w).sum()
    return float((E[0] * w).sum() / den) if den > 0 else float("nan")
