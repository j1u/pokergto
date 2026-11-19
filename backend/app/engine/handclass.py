"""Postflop hand categorisation (made hands + draws) and board texture."""
from __future__ import annotations

import numpy as np

from .cards import RANKS
from .evaluator import evaluate7

MADE_CATS = ["Straight flush", "Quads", "Full house", "Flush", "Straight", "Set", "Trips",
             "Two pair", "Overpair", "Top pair", "Middle pair", "Weak pair", "Ace high", "Nothing"]
DRAW_CATS = ["Combo draw", "Flush draw", "OESD", "Gutshot", "Backdoor FD", "No draw"]


def _has_straight(mask: int) -> bool:
    for hi in range(12, 3, -1):
        need = 0b11111 << (hi - 4)
        if mask & need == need:
            return True
    return mask & 0b1000000001111 == 0b1000000001111


def _best_score(cards: list[int]) -> int:
    if len(cards) == 7:
        return int(evaluate7(np.array([cards]))[0])
    # pad with impossible-to-help? -> evaluate all completions is costly; use 5/6 card direct scoring
    from itertools import combinations
    from .evaluator import _score_counts, _straight_high, _pack
    best = -1
    for five in combinations(cards, 5):
        ranks = [c // 4 for c in five]
        suits = [c % 4 for c in five]
        counts = [0] * 13
        for r in ranks:
            counts[r] += 1
        flush = len(set(suits)) == 1
        mask = sum(1 << r for r in set(ranks))
        sh = _straight_high(mask) if len(set(ranks)) == 5 else -1
        if flush and sh >= 0:
            s = _pack(8, [sh])
        else:
            s = _score_counts(counts)
            if flush and (s >> 20) < 5:
                s = _pack(5, sorted(ranks, reverse=True))
        best = max(best, s)
    return best


def classify(hole: tuple[int, int], board: list[int]) -> tuple[str, str]:
    """Return (made category, draw category) for a combo on a board (3-5 cards)."""
    h = list(hole)
    allc = h + board
    score = _best_score(allc)
    cat = score >> 20
    hr = sorted([c // 4 for c in h], reverse=True)
    br = sorted([c // 4 for c in board], reverse=True)
    board_score_cat = _best_score(board) >> 20 if len(board) >= 5 else None

    made = "Nothing"
    if cat == 8:
        made = "Straight flush"
    elif cat == 7:
        made = "Quads"
    elif cat == 6:
        made = "Full house"
    elif cat == 5:
        made = "Flush"
    elif cat == 4:
        made = "Straight"
    elif cat == 3:
        made = "Set" if hr[0] == hr[1] else "Trips"
    elif cat == 2:
        board_pairs = len(br) - len(set(br))
        if hr[0] != hr[1] and hr[0] in br and hr[1] in br:
            made = "Two pair"
        elif board_pairs >= 1:
            # one pair on board + our pair
            made = _pair_kind(hr, br, ignore_board_pair=True)
        else:
            made = "Two pair"
    elif cat == 1:
        if len(set(br)) < len(br):  # board paired, we have nothing extra
            made = "Ace high" if 12 in hr else "Nothing"
        else:
            made = _pair_kind(hr, br)
    else:
        made = "Ace high" if 12 in hr else "Nothing"
    if board_score_cat is not None and cat == board_score_cat and cat >= 4:
        # playing the board
        if score == _best_score(board):
            made = "Nothing" if 12 not in hr else "Ace high"

    draw = "No draw"
    if len(board) < 5 and cat < 4:
        suits_all = [c % 4 for c in allc]
        fd = False
        bdfd = False
        for s in range(4):
            n_all = suits_all.count(s)
            n_hole = sum(1 for c in h if c % 4 == s)
            if n_hole and n_all == 4:
                fd = True
            elif n_hole and n_all == 3 and len(board) == 3:
                bdfd = True
        mask = 0
        for c in allc:
            mask |= 1 << (c // 4)
        bmask = 0
        for c in board:
            bmask |= 1 << (c // 4)
        outs = 0
        for x in range(13):
            if mask >> x & 1:
                continue
            if _has_straight(mask | (1 << x)) and not _has_straight(bmask | (1 << x)):
                outs += 1
        if fd and outs >= 1:
            draw = "Combo draw"
        elif fd:
            draw = "Flush draw"
        elif outs >= 2:
            draw = "OESD"
        elif outs == 1:
            draw = "Gutshot"
        elif bdfd:
            draw = "Backdoor FD"
    return made, draw


def _pair_kind(hr: list[int], br: list[int], ignore_board_pair: bool = False) -> str:
    uniq = sorted(set(br), reverse=True)
    if hr[0] == hr[1]:
        if hr[0] > uniq[0]:
            return "Overpair"
        if len(uniq) > 1 and hr[0] > uniq[1]:
            return "Middle pair"
        return "Weak pair"
    paired = [r for r in hr if r in br]
    if not paired:
        return "Ace high" if 12 in hr else "Nothing"
    p = max(paired)
    if p == uniq[0]:
        return "Top pair"
    if len(uniq) > 1 and p == uniq[1]:
        return "Middle pair"
    return "Weak pair"


def board_texture(board: list[int]) -> dict:
    ranks = sorted([c // 4 for c in board], reverse=True)
    suits = [c % 4 for c in board]
    flop = board[:3]
    fs = [c % 4 for c in flop]
    n_suit_flop = max(fs.count(s) for s in range(4))
    max_suit = max(suits.count(s) for s in range(4))
    paired = len(set(ranks)) < len(ranks)
    uniq = sorted(set(ranks))
    # connectivity: number of straights possible using 2 hole cards
    straights = 0
    for hi in range(12, 2, -1):
        window = set(range(hi - 4, hi + 1)) if hi >= 4 else {12, 0, 1, 2, 3}
        if len(window & set(uniq)) >= 3:
            straights += 1
    tags = []
    if n_suit_flop == 3:
        tags.append("Monotone")
    elif n_suit_flop == 2:
        tags.append("Two-tone")
    else:
        tags.append("Rainbow")
    if paired:
        tags.append("Paired")
    if straights >= 3:
        tags.append("Very connected")
    elif straights >= 1:
        tags.append("Connected")
    else:
        tags.append("Disconnected")
    hi = ranks[0]
    if hi >= 10:
        tags.append(f"{RANKS[hi]}-high")
    elif hi >= 8:
        tags.append("Mid")
    else:
        tags.append("Low")
    if len(board) >= 4 and max_suit >= 3 and n_suit_flop < 3:
        tags.append("Flush possible")
    wetness = min(10, straights * 1.5 + (3 if n_suit_flop == 2 else 6 if n_suit_flop == 3 else 0)
                  + (0 if paired else 1))
    return {"tags": tags, "wetness": round(wetness, 1), "paired": paired,
            "flush_draw_possible": n_suit_flop >= 2, "straight_windows": straights}
