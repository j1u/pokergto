"""Card / combo / hand-class utilities.

Card encoding: int 0..51, rank = c // 4 (0 = deuce .. 12 = ace), suit = c % 4.
"""
from __future__ import annotations

from functools import lru_cache
from itertools import combinations

import numpy as np

RANKS = "23456789TJQKA"
SUITS = "cdhs"
RANK_TO_I = {r: i for i, r in enumerate(RANKS)}
SUIT_TO_I = {s: i for i, s in enumerate(SUITS)}


def card_from_str(s: str) -> int:
    s = s.strip()
    if len(s) != 2:
        raise ValueError(f"bad card '{s}'")
    r, su = s[0].upper(), s[1].lower()
    if r not in RANK_TO_I or su not in SUIT_TO_I:
        raise ValueError(f"bad card '{s}'")
    return RANK_TO_I[r] * 4 + SUIT_TO_I[su]


def card_to_str(c: int) -> str:
    return RANKS[c // 4] + SUITS[c % 4]


def parse_cards(s: str | list[str] | None) -> list[int]:
    if not s:
        return []
    if isinstance(s, list):
        out = [card_from_str(x) for x in s if x]
    else:
        t = s.replace(",", "").replace(" ", "")
        if len(t) % 2:
            raise ValueError(f"bad card string '{s}'")
        out = [card_from_str(t[i:i + 2]) for i in range(0, len(t), 2)]
    if len(set(out)) != len(out):
        raise ValueError("duplicate cards")
    return out


# ---------------------------------------------------------------- combos
# All 1326 two-card combos, ordered.
ALL_COMBOS: list[tuple[int, int]] = [(a, b) for a, b in combinations(range(52), 2)]
COMBO_INDEX = {c: i for i, c in enumerate(ALL_COMBOS)}
COMBO_ARR = np.array(ALL_COMBOS, dtype=np.int16)  # (1326, 2)


def combo_str(c: tuple[int, int]) -> str:
    a, b = c
    if a // 4 < b // 4 or (a // 4 == b // 4 and a < b):
        a, b = b, a
    return card_to_str(a) + card_to_str(b)


# ---------------------------------------------------------------- 169 classes
def _hand_classes() -> list[str]:
    out = []
    for i in range(12, -1, -1):          # row: high rank A..2
        for j in range(12, -1, -1):      # col
            hi, lo = RANKS[max(i, j)], RANKS[min(i, j)]
            if i == j:
                out.append(hi + lo)
            elif i > j:  # upper-right triangle = suited (row rank > col rank -> col to the right)
                out.append(hi + lo + "s")
            else:
                out.append(hi + lo + "o")
    return out


# Grid order (13x13, row-major, AA top-left, suited upper right like every range chart).
HAND_CLASSES: list[str] = _hand_classes()
CLASS_INDEX = {h: i for i, h in enumerate(HAND_CLASSES)}


def class_of_combo(c: tuple[int, int]) -> int:
    a, b = c
    ra, rb = a // 4, b // 4
    hi, lo = max(ra, rb), min(ra, rb)
    if ra == rb:
        name = RANKS[hi] * 2
    elif a % 4 == b % 4:
        name = RANKS[hi] + RANKS[lo] + "s"
    else:
        name = RANKS[hi] + RANKS[lo] + "o"
    return CLASS_INDEX[name]


COMBO_CLASS = np.array([class_of_combo(c) for c in ALL_COMBOS], dtype=np.int16)  # (1326,)
CLASS_COMBOS: list[list[int]] = [[] for _ in range(169)]
for _i, _k in enumerate(COMBO_CLASS):
    CLASS_COMBOS[_k].append(_i)
CLASS_NCOMBOS = np.array([len(x) for x in CLASS_COMBOS], dtype=np.float64)  # 6 / 4 / 12


def class_info(name: str) -> dict:
    hi, lo = RANK_TO_I[name[0]], RANK_TO_I[name[1]]
    return {
        "hi": hi,
        "lo": lo,
        "pair": hi == lo,
        "suited": name.endswith("s"),
        "gap": hi - lo - 1 if hi != lo else -1,
    }


CLASS_INFO = [class_info(h) for h in HAND_CLASSES]


@lru_cache(maxsize=4096)
def blocked_mask(dead: tuple[int, ...]) -> np.ndarray:
    """Boolean mask over 1326 combos: True if combo uses any dead card."""
    if not dead:
        return np.zeros(len(ALL_COMBOS), dtype=bool)
    d = np.zeros(52, dtype=bool)
    d[list(dead)] = True
    return d[COMBO_ARR[:, 0]] | d[COMBO_ARR[:, 1]]


def class_weights_to_combo(w169: np.ndarray) -> np.ndarray:
    """Expand 169-class weights (0..1) to 1326-combo weights."""
    return np.asarray(w169, dtype=np.float64)[COMBO_CLASS]


def combo_weights_to_class(w1326: np.ndarray, dead: tuple[int, ...] = ()) -> np.ndarray:
    """Average combo weights per class (over combos not blocked by dead cards)."""
    w = np.asarray(w1326, dtype=np.float64)
    alive = ~blocked_mask(tuple(sorted(dead)))
    num = np.bincount(COMBO_CLASS, weights=w * alive, minlength=169)
    den = np.bincount(COMBO_CLASS, weights=alive.astype(float), minlength=169)
    return np.divide(num, den, out=np.zeros(169), where=den > 0)
