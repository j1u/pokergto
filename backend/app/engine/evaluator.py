"""Vectorized 7-card hand evaluator (numpy).

Non-flush hands are scored via a lookup on the rank multiset (base-5 key, searchsorted
over all 49,205 seven-card rank multisets). Flush hands are scored via a 13-bit rank-mask
table. In 7 cards a flush can never coexist with quads/full house, so flush score wins.

Scores are int32, larger = better. Category = score >> 20.
"""
from __future__ import annotations

import numpy as np

CATEGORY_NAMES = [
    "High card", "Pair", "Two pair", "Trips", "Straight",
    "Flush", "Full house", "Quads", "Straight flush",
]

_POW5 = (5 ** np.arange(13)).astype(np.int64)


def _straight_high(mask: int) -> int:
    """Return high rank of best straight in 13-bit mask, or -1."""
    for hi in range(12, 3, -1):
        need = 0b11111 << (hi - 4)
        if mask & need == need:
            return hi
    if mask & 0b1000000001111 == 0b1000000001111:  # A-5 wheel
        return 3
    return -1


def _pack(cat: int, ks: list[int]) -> int:
    ks = (ks + [0, 0, 0, 0, 0])[:5]
    return (cat << 20) | (ks[0] << 16) | (ks[1] << 12) | (ks[2] << 8) | (ks[3] << 4) | ks[4]


def _score_counts(counts: list[int]) -> int:
    """Score a (non-flush) rank multiset of up to 7 cards."""
    mask = 0
    for r, c in enumerate(counts):
        if c:
            mask |= 1 << r
    by = sorted(((c, r) for r, c in enumerate(counts) if c), reverse=True)
    singles_desc = [r for r in range(12, -1, -1) if counts[r]]
    c0 = by[0][0]
    c1 = by[1][0] if len(by) > 1 else 0
    if c0 == 4:
        q = by[0][1]
        return _pack(7, [q, max(r for r in singles_desc if r != q)])
    if c0 == 3 and c1 >= 2:
        return _pack(6, [by[0][1], by[1][1]])
    sh = _straight_high(mask)
    if sh >= 0:
        return _pack(4, [sh])
    if c0 == 3:
        t = by[0][1]
        return _pack(3, [t] + [r for r in singles_desc if r != t][:2])
    if c0 == 2 and c1 == 2:
        p1, p2 = by[0][1], by[1][1]
        return _pack(2, [p1, p2, max(r for r in singles_desc if r not in (p1, p2))])
    if c0 == 2:
        p = by[0][1]
        return _pack(1, [p] + [r for r in singles_desc if r != p][:3])
    return _pack(0, singles_desc[:5])


def _build_tables():
    keys, vals = [], []
    counts = [0] * 13

    def rec(r: int, left: int):
        if r == 13:
            if left == 0:
                keys.append(sum(c * 5 ** i for i, c in enumerate(counts)))
                vals.append(_score_counts(counts))
            return
        for c in range(0, min(4, left) + 1):
            counts[r] = c
            rec(r + 1, left - c)
        counts[r] = 0

    rec(0, 7)
    keys = np.array(keys, dtype=np.int64)
    vals = np.array(vals, dtype=np.int32)
    order = np.argsort(keys)
    keys, vals = keys[order], vals[order]

    flush = np.zeros(1 << 13, dtype=np.int32)
    for m in range(1 << 13):
        if bin(m).count("1") < 5:
            continue
        sh = _straight_high(m)
        if sh >= 0:
            flush[m] = _pack(8, [sh])
        else:
            top = [r for r in range(12, -1, -1) if m >> r & 1][:5]
            flush[m] = _pack(5, top)
    return keys, vals, flush


_KEYS, _VALS, _FLUSH = _build_tables()


def evaluate7(cards: np.ndarray) -> np.ndarray:
    """cards: int array (N, 7) of card ids 0..51 -> int32 scores (N,)."""
    cards = np.asarray(cards)
    ranks = (cards // 4).astype(np.int64)
    suits = cards % 4
    key = _POW5[ranks].sum(axis=1)
    out = _VALS[np.minimum(np.searchsorted(_KEYS, key), len(_KEYS) - 1)]

    suit_counts = np.stack([(suits == s).sum(axis=1) for s in range(4)], axis=1)
    fs = suit_counts.argmax(axis=1)
    has_flush = suit_counts.max(axis=1) >= 5
    if has_flush.any():
        idx = np.nonzero(has_flush)[0]
        r = ranks[idx]
        s = suits[idx]
        in_suit = s == fs[idx][:, None]
        mask = np.bitwise_or.reduce((1 << r) * in_suit, axis=1)
        out[idx] = _FLUSH[mask]
    return out


def category(score) -> np.ndarray | int:
    return np.asarray(score) >> 20
