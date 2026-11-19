"""Range parsing, formatting, hand ranking and range construction."""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np

from .cards import (ALL_COMBOS, CLASS_COMBOS, CLASS_INDEX, CLASS_INFO, CLASS_NCOMBOS, COMBO_CLASS,
                    COMBO_INDEX, HAND_CLASSES, RANK_TO_I, RANKS, card_from_str)

TOTAL_COMBOS = 1326.0


# ------------------------------------------------------------------ parsing
def _cls(hi: int, lo: int, kind: str) -> str:
    if hi == lo:
        return RANKS[hi] * 2
    return RANKS[max(hi, lo)] + RANKS[min(hi, lo)] + kind


def _expand_token(tok: str) -> list[str] | list[tuple[int, int]]:
    tok = tok.strip()
    if not tok:
        return []
    # specific combo e.g. AsKs
    if re.fullmatch(r"[2-9TJQKA][cdhs][2-9TJQKA][cdhs]", tok, re.I):
        a, b = card_from_str(tok[:2]), card_from_str(tok[2:])
        return [tuple(sorted((a, b)))]
    t = tok.upper().replace("S", "s").replace("O", "o")
    m = re.fullmatch(r"([2-9TJQKA])([2-9TJQKA])([so]?)\-([2-9TJQKA])([2-9TJQKA])([so]?)", t)
    if m:
        a1, b1, k1, a2, b2, k2 = m.groups()
        h1, l1, h2, l2 = (RANK_TO_I[x] for x in (a1, b1, a2, b2))
        out = []
        if h1 == l1 and h2 == l2:  # 99-55
            for r in range(min(h1, h2), max(h1, h2) + 1):
                out.append(_cls(r, r, ""))
            return out
        kinds = [k1] if k1 else ["s", "o"]
        if h1 == h2:  # A9s-A2s
            for r in range(min(l1, l2), max(l1, l2) + 1):
                for k in kinds:
                    out.append(_cls(h1, r, k))
            return out
        # connected sequence T9s-76s
        gap = h1 - l1
        for hi in range(min(h1, h2), max(h1, h2) + 1):
            for k in kinds:
                out.append(_cls(hi, hi - gap, k))
        return out
    m = re.fullmatch(r"([2-9TJQKA])([2-9TJQKA])([so]?)(\+?)", t)
    if not m:
        raise ValueError(f"cannot parse range token '{tok}'")
    a, b, k, plus = m.groups()
    hi, lo = RANK_TO_I[a], RANK_TO_I[b]
    if hi < lo:
        hi, lo = lo, hi
    kinds = [k] if k else ["s", "o"]
    if hi == lo:
        return [_cls(r, r, "") for r in range(hi, 13)] if plus else [_cls(hi, hi, "")]
    if plus:
        return [_cls(hi, r, kk) for r in range(lo, hi) for kk in kinds]
    return [_cls(hi, lo, kk) for kk in kinds]


def parse_range(text: str) -> np.ndarray:
    """Parse range text into 1326 combo weights."""
    w = np.zeros(len(ALL_COMBOS))
    for raw in re.split(r"[,\s]+", text or ""):
        if not raw:
            continue
        weight = 1.0
        if ":" in raw:
            raw, ws = raw.split(":", 1)
            weight = float(ws)
            if weight > 1:  # allow percentages
                weight /= 100.0
        for item in _expand_token(raw):
            if isinstance(item, tuple):
                w[COMBO_INDEX[item]] = weight
            else:
                for ci in CLASS_COMBOS[CLASS_INDEX[item]]:
                    w[ci] = weight
    return np.clip(w, 0, 1)


def format_range169(w169: np.ndarray, eps: float = 0.005) -> str:
    """Compact-ish text representation of 169-class weights."""
    parts = []
    for i, h in enumerate(HAND_CLASSES):
        v = float(w169[i])
        if v <= eps:
            continue
        parts.append(h if v >= 1 - eps else f"{h}:{v:.2f}")
    return ",".join(parts)


def combos_count(w169: np.ndarray) -> float:
    return float((np.asarray(w169) * CLASS_NCOMBOS).sum())


def range_pct(w169: np.ndarray) -> float:
    return combos_count(w169) / TOTAL_COMBOS


# ------------------------------------------------------------------ ranking
@lru_cache(maxsize=1)
def strength_scores() -> np.ndarray:
    """Preflop hand 'playable strength' score used to order ranges (169,)."""
    from .equity import preflop_matrix
    m = preflop_matrix()
    n = CLASS_NCOMBOS
    eq_r = m @ n / n.sum()
    order = np.argsort(-eq_r)
    top = np.zeros(169)
    acc = 0.0
    for k in order:  # top ~15% by raw equity
        if acc >= 0.15 * TOTAL_COMBOS:
            break
        top[k] = 1
        acc += n[k]
    eq_t = m @ (top * n) / (top * n).sum()
    bonus = np.zeros(169)
    for i, info in enumerate(CLASS_INFO):
        if info["pair"]:
            bonus[i] = 0.035 + 0.004 * (12 - info["hi"]) * 0.5
            continue
        if info["suited"]:
            bonus[i] += 0.03
        g = info["gap"]
        bonus[i] += {0: 0.028, 1: 0.016, 2: 0.006}.get(g, 0.0)
        if info["suited"] and info["hi"] == 12:
            bonus[i] += 0.012 if info["lo"] <= 3 else 0.004  # wheel aces
        if not info["suited"] and info["lo"] < 6:
            bonus[i] -= 0.01 + 0.006 * (6 - info["lo"])
    return 0.35 * eq_r + 0.65 * eq_t + bonus


@lru_cache(maxsize=1)
def strength_order() -> np.ndarray:
    return np.argsort(-strength_scores())


@lru_cache(maxsize=1)
def bluff_order() -> np.ndarray:
    """Ordering for light 3-bet / 4-bet bluff candidates (suited blockers & connectors)."""
    s = np.zeros(169)
    for i, info in enumerate(CLASS_INFO):
        if info["pair"]:
            s[i] = -1
            continue
        v = 0.0
        if info["suited"]:
            v += 1.0
        if info["hi"] == 12:
            v += 0.8 if info["lo"] <= 3 else 0.35
        if info["hi"] == 11:
            v += 0.4
        v += {0: 0.5, 1: 0.3, 2: 0.1}.get(info["gap"], 0)
        v += 0.03 * info["lo"]
        s[i] = v
    return np.argsort(-s)


def top_range(frac: float, order: np.ndarray | None = None, within: np.ndarray | None = None,
              exclude: np.ndarray | None = None) -> np.ndarray:
    """Top `frac` (fraction of all 1326 combos, or of `within` if given) of hands in `order`.

    within: 169 parent-range weights (cap per class). exclude: 169 weights already used.
    Returns 169 weights.
    """
    order = strength_order() if order is None else order
    cap = np.ones(169) if within is None else np.asarray(within, float).copy()
    if exclude is not None:
        cap = np.clip(cap - exclude, 0, 1)
    target = frac * (TOTAL_COMBOS if within is None else combos_count(within))
    out = np.zeros(169)
    acc = 0.0
    for k in order:
        if acc >= target - 1e-9:
            break
        avail = cap[k] * CLASS_NCOMBOS[k]
        if avail <= 0:
            continue
        take = min(avail, target - acc)
        out[k] = take / CLASS_NCOMBOS[k]
        acc += take
    return out


def build_raise_call(raise_frac: float, call_frac: float, within: np.ndarray | None = None,
                     polar: float = 0.3) -> tuple[np.ndarray, np.ndarray]:
    """Construct (raise, call) 169 ranges. `polar` share of raises are bluffs from bluff_order
    taken below the calling band (linear when polar=0)."""
    value = top_range(raise_frac * (1 - polar), within=within)
    call = top_range(call_frac, within=within, exclude=value) if call_frac > 0 else np.zeros(169)
    if within is not None:
        # convert call frac (expressed relative to parent) correctly handled by top_range
        pass
    bluff = np.zeros(169)
    if polar > 0 and raise_frac > 0:
        used = value + call
        bluff = top_range(raise_frac * polar, order=bluff_order(), within=within, exclude=used)
    return np.clip(value + bluff, 0, 1), call
