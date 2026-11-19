"""Preflop spot engine (2-9 handed cash, chip EV).

Approach
--------
1. Villain ranges are built from reference (equilibrium-like) action widths, scaled by each
   villain's profile (nit / LAG / station ...).
2. For every one of the 169 hand classes we compute the EV (bb, relative to folding) of each
   hero action using a one-decision-deep model: fold equity, all-in equity, and postflop
   equity *realization* (depends on position, SPR and playability).
3. GTO mode: per-action EV offsets are calibrated so hero's action frequencies match the
   reference widths; the EV model decides *which* hands take each action, with soft mixing
   near indifference.
4. Exploit mode: identical offsets, but EVs computed against the villains' actual profiles,
   so hero's ranges widen/tighten exactly where the opponent's leaks make that profitable.
Facing an all-in is solved as a pure chip-EV best response (no calibration needed).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

import numpy as np

from .cards import CLASS_INFO, CLASS_NCOMBOS, HAND_CLASSES
from .equity import preflop_eq_vs_range
from .profiles import Profile, get_profile
from .ranges import build_raise_call, combos_count, format_range169, range_pct, top_range

POS = ["UTG", "HJ", "CO", "BTN", "SB", "BB"]          # default 6-max seats
SEATS = {
    2: ["SB", "BB"],                                   # heads-up: SB is the button
    3: ["BTN", "SB", "BB"],
    4: ["CO", "BTN", "SB", "BB"],
    5: ["HJ", "CO", "BTN", "SB", "BB"],
    6: ["UTG", "HJ", "CO", "BTN", "SB", "BB"],
    7: ["UTG", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
    8: ["UTG", "UTG1", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
    9: ["UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
}
TABLE_NAMES = {2: "Heads-up", 3: "3-handed", 4: "4-handed", 5: "5-handed", 6: "6-max",
               7: "7-handed", 8: "8-handed", 9: "Full ring (9)"}
POSTED = {"SB": 0.5, "BB": 1.0}

_N = ContextVar("n_players", default=6)


@contextmanager
def table(n: int):
    """Run engine calls for an n-handed table (thread/request local)."""
    if n not in SEATS:
        raise ValueError("table size must be 2-9 players")
    tok = _N.set(n)
    try:
        yield SEATS[n]
    finally:
        _N.reset(tok)


def seats() -> list[str]:
    return SEATS[_N.get()]


def n_players() -> int:
    return _N.get()


def behind(p: str) -> int:
    s = seats()
    return len(s) - 1 - s.index(p)


def heads_up() -> bool:
    return _N.get() == 2


# Range widths are driven by how many players are left to act behind the opener.
RFI_BY_BEHIND = {2: 0.44, 3: 0.28, 4: 0.21, 5: 0.17, 6: 0.145, 7: 0.125, 8: 0.11}
PUSH10_BY_BEHIND = {2: 0.32, 3: 0.21, 4: 0.15, 5: 0.12, 6: 0.10, 7: 0.09, 8: 0.08}
CANON_BEHIND = {"UTG": 5, "HJ": 4, "CO": 3, "BTN": 2}
RFI = {"UTG": 0.17, "HJ": 0.21, "CO": 0.28, "BTN": 0.44, "SB": 0.40, "SB_HU": 0.80}


def canon(p: str) -> str:
    """Map a seat to its 6-max equivalent (by players behind)."""
    if p == "SB":
        return "SB_HU" if heads_up() else "SB"
    if p == "BB":
        return "BB"
    k = behind(p)
    return "UTG" if k >= 5 else {4: "HJ", 3: "CO", 2: "BTN"}[k]


def rfi_base(p: str) -> float:
    if p == "SB":
        return 0.80 if heads_up() else 0.40
    return RFI_BY_BEHIND[min(8, behind(p))]


def push10_base(p: str) -> float:
    if p == "SB":
        return 0.60 if heads_up() else 0.52
    return PUSH10_BY_BEHIND[min(8, behind(p))]


VS_OPEN = {  # (hero, opener) in 6-max-equivalent seats: (3bet width, call width) as fraction of all hands
    ("HJ", "UTG"): (0.060, 0.030),
    ("CO", "UTG"): (0.065, 0.035), ("CO", "HJ"): (0.075, 0.040),
    ("BTN", "UTG"): (0.065, 0.060), ("BTN", "HJ"): (0.075, 0.070), ("BTN", "CO"): (0.090, 0.080),
    ("SB", "UTG"): (0.065, 0.0), ("SB", "HJ"): (0.075, 0.0), ("SB", "CO"): (0.095, 0.0),
    ("SB", "BTN"): (0.130, 0.0),
    ("BB", "UTG"): (0.065, 0.24), ("BB", "HJ"): (0.075, 0.27), ("BB", "CO"): (0.090, 0.31),
    ("BB", "BTN"): (0.120, 0.38), ("BB", "SB"): (0.150, 0.42),
    ("BB", "SB_HU"): (0.160, 0.50),
}
POLAR_PROFILES = {"gto", "tag", "lag", "maniac", "custom"}

SCENARIOS = {
    "rfi": "Open (first in)",
    "vs_open": "Facing an open",
    "vs_3bet": "Facing a 3-bet",
    "vs_4bet": "Facing a 4-bet",
    "vs_jam": "Facing an all-in",
    "vs_limp": "Facing limpers",
}


def post_rank(p: str) -> int:
    if heads_up():
        return {"SB": 1, "BB": 0}[p]          # the button (SB) acts last postflop
    if p == "SB":
        return 0
    if p == "BB":
        return 1
    return seats().index(p) + 2


def is_ip(a: str, b: str) -> bool:
    return post_rank(a) > post_rank(b)


def dead_money(ante: float) -> float:
    return 1.5 + n_players() * ante


def depth(S: float) -> float:
    return float(np.clip((S - 20) / 80, 0, 1))


def open_size(pos: str, S: float) -> float:
    if S <= 15:
        return S
    std = 2.5 if S >= 60 else 2.2 if S >= 30 else 2.0
    base = (min(2.5, std) if heads_up() else 3.0) if pos == "SB" else std
    return min(base, S)


def threebet_size(hero: str, opener: str, o: float, S: float) -> float:
    mult = 3.0 if is_ip(hero, opener) else (3.8 if hero in ("SB", "BB") else 3.3)
    T = round(o * mult * 2) / 2
    return S if T >= 0.45 * S else T


def fourbet_size(T: float, ip: bool, S: float) -> float:
    F = round(T * (2.3 if ip else 2.6) * 2) / 2
    return S if F >= 0.45 * S else F


# ------------------------------------------------------------------ widths
def rfi_width(pos: str, S: float, prof: Profile) -> float:
    w = push10_base(pos) * (10 / S) ** 0.7 if S <= 15 else rfi_base(pos)
    return float(min(0.95, w * prof.open))


def vs_open_width(hero: str, opener: str, S: float, prof: Profile) -> tuple[float, float]:
    hc, oc = canon(hero), canon(opener)
    key = (hc, oc)
    if key not in VS_OPEN:  # several early seats map to "UTG" at 7-9 handed tables
        key = ("HJ", "UTG") if hc not in ("SB", "BB") else (hc, "UTG")
    t, c = VS_OPEN[key]
    # tighter opener than the 6-max reference -> defend tighter; more players behind hero -> tighter
    scale = (rfi_base(opener) / RFI[key[1]]) ** 0.7
    if key[0] in CANON_BEHIND:
        scale *= 0.9 ** max(0, behind(hero) - CANON_BEHIND[key[0]])
    t, c = t * scale, c * scale
    c *= 0.55 + 0.45 * depth(S)
    t, c = t * prof.threebet, c * prof.call
    tot = t + c
    if tot > 0.7:
        t, c = t * 0.7 / tot, c * 0.7 / tot
    return t, c


def vs_3bet_width(opener: str, threebettor: str, S: float, prof: Profile) -> tuple[float, float]:
    f, c = (0.14, 0.40) if is_ip(opener, threebettor) else (0.12, 0.32)
    c *= 0.4 + 0.6 * depth(S)
    f, c = f * prof.fourbet, c * prof.cont_vs_3bet
    tot = f + c
    if tot > 0.95:
        f, c = f * 0.95 / tot, c * 0.95 / tot
    return f, c


def vs_4bet_width(threebettor: str, fourbettor: str, prof: Profile, jammed: bool) -> tuple[float, float]:
    j, c = (0.22, 0.22) if is_ip(threebettor, fourbettor) else (0.22, 0.17)
    if jammed:
        j, c = 0.0, (j + c) * 0.9
    return min(0.9, j * prof.fourbet), min(0.9, c * prof.cont_vs_3bet)


# ------------------------------------------------------------------ helpers
@lru_cache(maxsize=1)
def _playability() -> np.ndarray:
    p = np.zeros(169)
    for i, info in enumerate(CLASS_INFO):
        if info["pair"]:
            continue  # pairs handled SPR-dependently in realization()
        if info["suited"]:
            p[i] += 0.07
        p[i] += {0: 0.03, 1: 0.015}.get(info["gap"], 0.0)
        if info["lo"] >= 8:
            p[i] += 0.02
        if not info["suited"] and info["lo"] < 6:
            p[i] -= 0.06
    return p


@lru_cache(maxsize=1)
def _pair_mask() -> np.ndarray:
    return np.array([1.0 if i["pair"] else 0.0 for i in CLASS_INFO])


@lru_cache(maxsize=1)
def _ranks_hi() -> np.ndarray:
    return np.array([float(i["hi"]) for i in CLASS_INFO])


@lru_cache(maxsize=1)
def _compat() -> np.ndarray:
    """C[h, k]: average fraction of class-k combos that don't collide with a class-h combo."""
    from .cards import COMBO_ARR, COMBO_CLASS
    a = COMBO_ARR.astype(np.int64)
    share = ((a[:, None, 0] == a[None, :, 0]) | (a[:, None, 0] == a[None, :, 1]) |
             (a[:, None, 1] == a[None, :, 0]) | (a[:, None, 1] == a[None, :, 1]))
    D = (~share).astype(np.float64)
    A = np.zeros((1326, 169))
    A[np.arange(1326), COMBO_CLASS] = 1
    num = A.T @ D @ A
    return num / (CLASS_NCOMBOS[:, None] * CLASS_NCOMBOS[None, :])


def frac_vec(r: np.ndarray) -> np.ndarray:
    """Per hero hand: probability a random remaining villain hand is in r (blocker-aware)."""
    C = _compat()
    return C @ (r * CLASS_NCOMBOS) / (C @ CLASS_NCOMBOS)


def pct_vec(sub: np.ndarray, parent: np.ndarray) -> np.ndarray:
    C = _compat()
    den = C @ (parent * CLASS_NCOMBOS)
    return np.divide(C @ (sub * CLASS_NCOMBOS), den, out=np.zeros(169), where=den > 0)


def realization(eq: np.ndarray, ip: bool, spr: float, multiway: int = 0) -> np.ndarray:
    base = 0.98 if ip else 0.80
    pairs = _pair_mask()
    small = pairs * np.clip((9 - _ranks_hi()) / 7, 0, 1)
    pair_adj = pairs * 0.10 * min(1.0, spr / 12) - small * 0.12 * (1 - min(1.0, spr / 8))
    R = base + _playability() + pair_adj + 0.45 * (eq - 0.5) - 0.03 * multiway
    R = 1 - (1 - R) * min(1.0, spr / 8.0)
    return np.clip(R, 0.4, 1.35)


def realized(eq: np.ndarray, ip: bool, spr: float, multiway: int = 0) -> np.ndarray:
    return np.minimum(eq * realization(eq, ip, spr, multiway), 0.97)


def eqv(r169: np.ndarray) -> np.ndarray:
    return preflop_eq_vs_range(r169)


def pct_of(sub: np.ndarray, parent: np.ndarray) -> float:
    pc = combos_count(parent)
    return combos_count(sub) / pc if pc > 0 else 0.0


def br_call_vs_jam(candidates: np.ndarray, jam_range: np.ndarray, total_pot: float, cost: float,
                   mult: float) -> np.ndarray:
    """Villain calls a jam with candidate classes whose equity clears the price (profile-adjusted)."""
    if combos_count(jam_range) <= 0:
        return candidates * 0
    eq = eqv(jam_range)
    need = cost / total_pot
    return candidates * (eq * mult >= need)


# ------------------------------------------------------------------ villain range builders
def villain_vs_open(pos: str, opener: str, S: float, prof: Profile):
    t, c = vs_open_width(pos, opener, S, prof)
    return build_raise_call(t, c, polar=0.3 if prof.key in POLAR_PROFILES else 0.1)


def villain_rfi(pos: str, S: float, prof: Profile) -> np.ndarray:
    return top_range(rfi_width(pos, S, prof))


# ------------------------------------------------------------------ EV models
def ev_rfi(hero: str, S: float, ante: float, profs: dict[str, Profile]):
    dead = dead_money(ante)
    hp = POSTED.get(hero, 0.0)
    o = open_size(hero, S)
    jam = o >= S
    s = seats()
    behind_seats = s[s.index(hero) + 1:]
    ev = np.zeros(169)
    p_none = 1.0
    villains = []
    hero_jam_est = top_range(rfi_width(hero, S, get_profile("gto")))
    eq_primary = None
    for j in behind_seats:
        prof = profs[j]
        pj = POSTED.get(j, 0.0)
        ipj = is_ip(hero, j)
        if jam:
            total = dead + (S - hp) + (S - pj)
            cand = np.ones(169)
            call = br_call_vs_jam(cand, hero_jam_est, total, S - pj, prof.call_vs_jam)
            d = frac_vec(call)
            p_first = p_none * d
            branch = eqv(call) * total - (S - hp) if combos_count(call) > 0 else 0
            villains.append({"pos": j, "profile": prof.key, "call": call, "threebet": np.zeros(169)})
            if eq_primary is None or j == "BB":
                eq_primary = eqv(call) if combos_count(call) > 0 else eq_primary
        else:
            r3, rc = villain_vs_open(j, hero, S, prof)
            d3, dc = frac_vec(r3), frac_vec(rc)
            d = d3 + dc
            dsafe = np.maximum(d, 1e-9)
            p_first = p_none * d
            villains.append({"pos": j, "profile": prof.key, "call": rc, "threebet": r3})
            branch = np.zeros(169)
            if combos_count(rc) > 0:
                pot_c = dead + (o - hp) + (o - pj)
                eqc = eqv(rc)
                spr = (S - o) / pot_c
                ev_called = realized(eqc, ipj, spr) * pot_c - (o - hp)
                branch = branch + (dc / dsafe) * ev_called
                if j == "BB" or eq_primary is None:
                    eq_primary = eqc
            if combos_count(r3) > 0:
                T = threebet_size(j, hero, o, S)
                eq3 = eqv(r3)
                pot_now = dead + (o - hp) + (T - pj)
                fold = -(o - hp) * np.ones(169)
                if T >= S:
                    call3 = eq3 * (dead + (S - hp) + (S - pj)) - (S - hp)
                    best = np.maximum(fold, call3)
                else:
                    pot3 = pot_now + (T - o)
                    call3 = realized(eq3, ipj, (S - T) / pot3) * pot3 - (T - hp)
                    # get it in vs the value part of the 3-bet range
                    value = top_range(0.5, within=r3)
                    q = np.minimum(1.0, pct_vec(value, r3) * min(1.5, prof.call_vs_jam))
                    jam_ev = (1 - q) * (pot_now - (o - hp)) + q * (
                        eqv(value) * (dead + (S - hp) + (S - pj)) - (S - hp))
                    best = np.maximum(np.maximum(fold, call3), jam_ev)
                branch = branch + (d3 / dsafe) * best
            if eq_primary is None and combos_count(r3) > 0:
                eq_primary = eqv(r3)
        ev = ev + p_first * branch
        p_none *= (1 - d)
    ev = ev + p_none * dead
    label = f"All-in {S:g}" if jam else f"Raise {o:g}"
    return {"agg": ev}, {"agg": label}, villains, eq_primary, {"p_all_fold": float(np.mean(p_none)), "size": o}


def ev_vs_open(hero: str, opener: str, S: float, ante: float, prof: Profile):
    base = dead_money(ante)
    hp, pi = POSTED.get(hero, 0.0), POSTED.get(opener, 0.0)
    o = open_size(opener, S)
    open_range = villain_rfi(opener, S, prof)
    eq_open = eqv(open_range)
    pot_before = base + (o - pi)
    ip = is_ip(hero, opener)
    n_behind = behind(hero)
    evs, labels, extra = {}, {}, {}
    villain_ranges = {"open": open_range}

    if o >= S:  # opener jammed -> treat as vs_jam
        total = base + (S - pi) + (S - hp)
        evs["call"] = eq_open * total - (S - hp)
        labels["call"] = "Call"
        return evs, labels, villain_ranges, eq_open, {"size": o}

    pot_c = pot_before + (o - hp)
    evs["call"] = realized(eq_open, ip, (S - o) / pot_c, multiway=min(n_behind, 2)) * pot_c - (o - hp)
    labels["call"] = "Call"

    T = threebet_size(hero, opener, o, S)
    if T >= S:
        hero_jam_est = top_range(sum(vs_open_width(hero, opener, S, get_profile("gto"))) * 0.8)
        total = base + (S - hp) + (S - pi)
        callers = br_call_vs_jam(open_range, hero_jam_est, total, S - pi, prof.call_vs_jam)
        pc = pct_vec(callers, open_range)
        eq_c = eqv(callers) if combos_count(callers) > 0 else np.full(169, 0.5)
        evs["agg"] = (1 - pc) * pot_before + pc * (eq_c * total - (S - hp))
        labels["agg"] = f"All-in {S:g}"
        villain_ranges["call_vs_jam"] = callers
    else:
        f4w, ccw = vs_3bet_width(opener, hero, S, prof)
        f4, cc = build_raise_call(f4w, ccw, within=open_range,
                                  polar=0.25 if prof.key in POLAR_PROFILES else 0.05)
        p4, pc = pct_vec(f4, open_range), pct_vec(cc, open_range)
        pf = np.maximum(0.0, 1 - p4 - pc)
        pot3 = base + (T - hp) + (T - pi)
        ev_called = realized(eqv(cc), ip, (S - T) / pot3) * pot3 - (T - hp) if combos_count(cc) > 0 else 0
        F = fourbet_size(T, is_ip(opener, hero), S)
        total = base + (S - hp) + (S - pi)
        cont = eqv(f4) * total - (S - hp)
        if F < S:
            # vs a non all-in 4-bet hero either folds or gets it in (opener's 4-bets are mostly
            # stacked off with value, bluffs fold => use value half for showdown)
            val = top_range(0.6, within=f4)
            pv = pct_of(val, f4)
            cont = (1 - pv) * (base + (F - pi) + (T - hp) - (T - hp)) + pv * (
                eqv(val) * total - (S - hp)) if pv > 0 else cont
        ev_4b = np.maximum(-(T - hp), cont) if combos_count(f4) > 0 else 0
        evs["agg"] = pf * pot_before + pc * ev_called + p4 * ev_4b
        labels["agg"] = f"3-Bet {T:g}"
        villain_ranges.update({"fourbet": f4, "call_vs_3bet": cc})
        extra["fold_to_3bet"] = float(1 - pct_of(f4, open_range) - pct_of(cc, open_range))
    return evs, labels, villain_ranges, eq_open, {"size": T, **extra}


def ev_vs_3bet(hero: str, threebettor: str, S: float, ante: float, prof: Profile):
    base = dead_money(ante)
    hp, pj = POSTED.get(hero, 0.0), POSTED.get(threebettor, 0.0)
    o = open_size(hero, S)
    T = threebet_size(threebettor, hero, o, S)
    r3, _ = villain_vs_open(threebettor, hero, S, prof)
    eq3 = eqv(r3)
    ip = is_ip(hero, threebettor)
    pot_now = base + (o - hp) + (T - pj)
    evs, labels = {}, {}
    vr = {"threebet": r3}
    total = base + (S - hp) + (S - pj)
    if T >= S:
        evs["call"] = eq3 * total - (S - o)
        labels["call"] = "Call"
        return evs, labels, vr, eq3, {"size": T}
    pot_c = pot_now + (T - o)
    evs["call"] = realized(eq3, ip, (S - T) / pot_c) * pot_c - (T - o)
    labels["call"] = "Call"
    F = fourbet_size(T, ip, S)
    if F >= S:
        hero_est = top_range(0.15 * 0.6, within=None)
        callers = br_call_vs_jam(r3, hero_est, total, S - pj, prof.call_vs_jam)
        pc = pct_vec(callers, r3)
        eq_c = eqv(callers) if combos_count(callers) > 0 else np.full(169, 0.5)
        evs["agg"] = (1 - pc) * pot_now + pc * (eq_c * total - (S - o))
        labels["agg"] = f"All-in {S:g}"
        vr["call_vs_jam"] = callers
    else:
        jw, cw = vs_4bet_width(threebettor, hero, prof, jammed=False)
        j5, c5 = build_raise_call(jw, cw, within=r3, polar=0.0)
        pj5, pc5 = pct_vec(j5, r3), pct_vec(c5, r3)
        pf = np.maximum(0.0, 1 - pj5 - pc5)
        pot4 = base + (F - hp) + (F - pj)
        ev_c = realized(eqv(c5), ip, (S - F) / pot4) * pot4 - (F - o) if combos_count(c5) > 0 else 0
        ev_j = np.maximum(-(F - o), eqv(j5) * total - (S - o)) if combos_count(j5) > 0 else 0
        evs["agg"] = pf * pot_now + pc5 * ev_c + pj5 * ev_j
        labels["agg"] = f"4-Bet {F:g}"
        vr.update({"fivebet_jam": j5, "call_vs_4bet": c5})
    return evs, labels, vr, eq3, {"size": F}


def ev_vs_4bet(hero: str, fourbettor: str, S: float, ante: float, prof: Profile):
    base = dead_money(ante)
    hp, pi = POSTED.get(hero, 0.0), POSTED.get(fourbettor, 0.0)
    o = open_size(fourbettor, S)
    T = threebet_size(hero, fourbettor, o, S)
    F = fourbet_size(T, is_ip(fourbettor, hero), S)
    open_range = villain_rfi(fourbettor, S, prof)
    f4w, ccw = vs_3bet_width(fourbettor, hero, S, prof)
    f4, _ = build_raise_call(f4w, ccw, within=open_range,
                             polar=0.25 if prof.key in POLAR_PROFILES else 0.05)
    eq4 = eqv(f4)
    total = base + (S - hp) + (S - pi)
    pot_now = base + (F - pi) + (T - hp)
    evs, labels = {}, {}
    vr = {"open": open_range, "fourbet": f4}
    if F >= S:
        evs["call"] = eq4 * total - (S - T)
        labels["call"] = "Call"
        return evs, labels, vr, eq4, {"size": F}
    ip = is_ip(hero, fourbettor)
    pot_c = pot_now + (F - T)
    evs["call"] = realized(eq4, ip, (S - F) / pot_c) * pot_c - (F - T)
    labels["call"] = "Call"
    q = min(0.95, 0.6 * prof.call_vs_jam)
    callers = top_range(q, within=f4)
    pc = pct_vec(callers, f4)
    evs["agg"] = (1 - pc) * pot_now + pc * (eqv(callers) * total - (S - T))
    labels["agg"] = f"All-in {S:g}"
    vr["call_vs_jam"] = callers
    return evs, labels, vr, eq4, {"size": S}


def ev_vs_jam(hero: str, jammer: str, S: float, ante: float, prof: Profile):
    base = dead_money(ante)
    hp, pi = POSTED.get(hero, 0.0), POSTED.get(jammer, 0.0)
    w = push10_base(jammer) * (10 / S) ** 0.7 * prof.open
    jam_range = top_range(min(0.95, w))
    eqj = eqv(jam_range)
    total = base + (S - pi) + (S - hp)
    return ({"call": eqj * total - (S - hp)}, {"call": "Call"}, {"jam": jam_range}, eqj,
            {"size": S, "pot_odds": (S - hp) / total})


# ------------------------------------------------------------------ limped pots
# Limper styles by profile: (limp width, top share raised instead of limped,
#                            share of limp range that calls an iso-raise, share that limp-reraises)
LIMP_STYLE = {
    "gto": (0.30, 0.06, 0.50, 0.05),        # baseline = typical recreational limper
    "custom": (0.30, 0.06, 0.50, 0.05),
    "fish": (0.40, 0.05, 0.60, 0.04),
    "station": (0.50, 0.03, 0.80, 0.02),
    "nit": (0.14, 0.03, 0.40, 0.10),
    "tag": (0.16, 0.08, 0.45, 0.08),
    "lag": (0.24, 0.08, 0.45, 0.12),
    "maniac": (0.35, 0.10, 0.40, 0.20),
    "overfolder": (0.20, 0.06, 0.30, 0.05),
}
SB_LIMP_STYLE = (0.50, 0.08, 0.55, 0.10)     # SB completing vs the BB (solvers do limp the SB)


def parse_limpers(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [x for x in v.split(",") if x]
    return list(v)


def limper_ranges(seat: str, prof: Profile):
    width, top, call_share, rr_share = SB_LIMP_STYLE if seat == "SB" else LIMP_STYLE.get(prof.key, LIMP_STYLE["gto"])
    excluded = top_range(top)                          # premiums they would have raised
    limp = top_range(max(0.01, width - top), exclude=excluded)
    rr = top_range(rr_share, within=limp)              # limp-reraises (strongest limps / traps)
    call = top_range(call_share, within=limp, exclude=rr)
    return limp, call, rr


@lru_cache(maxsize=1)
def _speculative() -> np.ndarray:
    """Hands that gain in multiway, deep pots: small/medium pairs, suited connectors, suited aces."""
    m = np.zeros(169)
    for i, info in enumerate(CLASS_INFO):
        if info["pair"] and info["hi"] <= 8:
            m[i] = 1.0
        elif info["suited"] and (info["gap"] <= 1 or info["hi"] == 12):
            m[i] = 0.8
    return m


def mw_equity(eqs: list) -> np.ndarray:
    """Approximate multiway equity from heads-up equities vs each opponent.

    A plain product (independence) badly understates multiway equity; the exponent makes a hand
    that is 50% vs each of n opponents get exactly its fair share 1/(n+1)."""
    n = len(eqs)
    if n == 0:
        return np.ones(169)
    if n == 1:
        return eqs[0]
    alpha = np.log(n + 1) / (n * np.log(2))
    logs = sum(np.log(np.clip(e, 1e-6, 1)) for e in eqs)
    return np.exp(alpha * logs)


def realized_multi(eq, ip, spr, n_opp):
    """Realized share of the pot vs n_opp opponents (eq = probability to win at showdown)."""
    R = realization(np.clip(eq * (n_opp + 1) / 2, 0, 1), ip, spr, multiway=max(0, n_opp - 1))
    # implied odds: speculative hands make disguised strong hands that get paid in multiway, deep pots
    R = R + _speculative() * 0.12 * max(0, n_opp - 1) * min(1.0, spr / 10)
    return np.minimum(eq * R, 0.97)


def iso_size(hero: str, k: int, S: float) -> float:
    std = 2.5 if S >= 60 else 2.2 if S >= 30 else 2.0
    I = std + k * 1.0 + (1.0 if hero in ("SB", "BB") and not heads_up() else 0.0)
    I = round(I * 2) / 2
    return S if I >= 0.45 * S else I


def ev_vs_limp(hero: str, limpers_s, S: float, ante: float, profs: dict[str, Profile]):
    limpers = parse_limpers(limpers_s)
    base = dead_money(ante)
    hp = POSTED.get(hero, 0.0)
    k = len(limpers)
    pot_before = base + sum(1.0 - POSTED.get(l, 0.0) for l in limpers)
    s = seats()
    behind_seats = [j for j in s[s.index(hero) + 1:]]
    ip = hero not in ("SB", "BB") or (heads_up() and hero == "SB")
    rng = {l: limper_ranges(l, profs[l]) for l in limpers}
    eq_limp = {l: eqv(rng[l][0]) for l in limpers}
    vr = {}
    for l in limpers:
        vr[f"limp_{l}"] = rng[l][0]
        vr[f"call_iso_{l}"] = rng[l][1]
        vr[f"limp_reraise_{l}"] = rng[l][2]

    evs, labels = {}, {}
    # ---- over-limp / complete / check
    cost = 1.0 - hp
    bb_behind = "BB" in behind_seats
    p_raise = 1.0
    for j in behind_seats:
        w = (0.15 if j in ("SB", "BB") else 0.5 * rfi_base(j)) * profs[j].open
        p_raise *= (1 - min(0.5, w))
    p_raise = 1 - p_raise
    opp_eqs = [eq_limp[l] for l in limpers] + ([eqv(np.ones(169))] if bb_behind else [])
    eq_mw = mw_equity(opp_eqs)
    n_opp = len(opp_eqs)
    pot_final = pot_before + cost
    spr = (S - 1) / pot_final
    share = realized_multi(eq_mw, ip, spr, n_opp)
    evs["call"] = (1 - p_raise) * (share * pot_final - cost) + p_raise * (-cost)
    labels["call"] = "Check" if hero == "BB" else ("Complete" if hero == "SB" else "Over-limp")

    # ---- isolation raise
    I = iso_size(hero, k, S)
    allin = I >= S
    t_b = []
    for j in behind_seats:
        if allin:
            t_b.append((j, np.zeros(169), 0.0))
            continue
        r3, _ = villain_vs_open(j, hero, S, profs[j])
        t_b.append((j, r3, frac_vec(r3)))
    rho = {l: pct_vec(rng[l][2], rng[l][0]) for l in limpers}
    kap = {l: pct_vec(rng[l][1], rng[l][0]) for l in limpers}
    if allin:  # jam over limpers: they call with their limp-reraise + some calling hands
        for l in limpers:
            rho[l] = np.minimum(1.0, rho[l] + 0.35 * kap[l] * profs[l].call_vs_jam)
            kap[l] = np.zeros(169)
    total_allin = pot_before + (S - hp) + (S - 1.0)
    ev = np.zeros(169)
    p_clear = np.ones(169)                   # nobody has re-raised so far
    for j, r3, f3 in t_b:                    # players behind act first on the raise
        if combos_count(r3) > 0:
            ev_rr = np.maximum(-(I - hp), eqv(top_range(0.6, within=r3)) * total_allin - (S - hp))
            ev = ev + p_clear * f3 * ev_rr
            p_clear = p_clear * (1 - f3)
    for l in limpers:
        ev_rr = np.maximum(-(I - hp), eqv(rng[l][2]) * total_allin - (S - hp)) if combos_count(rng[l][2]) > 0 \
            else -(I - hp)
        if allin:
            ev_rr = eqv(rng[l][2] + 0.35 * rng[l][1]) * total_allin - (S - hp)
        ev = ev + p_clear * rho[l] * ev_rr
        p_clear = p_clear * (1 - rho[l])
    # no re-raise: every subset of limpers may call
    stay = {l: np.divide(kap[l], np.maximum(1 - rho[l], 1e-9)) for l in limpers}
    for mask in range(1 << k):
        callers = [limpers[i] for i in range(k) if mask >> i & 1]
        p = np.ones(169)
        for i, l in enumerate(limpers):
            p = p * (stay[l] if mask >> i & 1 else (1 - stay[l]))
        if not callers:
            val = pot_before
        else:
            pot_s = pot_before + (I - hp) + sum(I - 1.0 for _ in callers)
            eq_s = mw_equity([eqv(rng[l][1]) for l in callers])
            if allin:
                val = eq_s * pot_s - (I - hp)
            else:
                val = realized_multi(eq_s, ip, (S - I) / pot_s, len(callers)) * pot_s - (I - hp)
        ev = ev + p_clear * p * val
    evs["agg"] = ev
    labels["agg"] = f"All-in {S:g}" if allin else f"Iso-raise {I:g}"
    info = {"size": I, "limpers": limpers, "p_raise_behind": float(np.mean(p_raise))}
    return evs, labels, vr, eq_mw, info


# ------------------------------------------------------------------ strategy from EVs
def _freqs(evs: dict, offsets: dict, tau: float, actions: list[str], no_fold: bool = False) -> np.ndarray:
    u = np.stack([np.full(169, -1e6 if no_fold else 0.0)] + [evs[a] - offsets.get(a, 0.0) for a in actions], axis=1)
    z = (u - u.max(axis=1, keepdims=True)) / max(tau, 1e-6)
    p = np.exp(z)
    p /= p.sum(axis=1, keepdims=True)
    p[p < 0.03] = 0
    p /= p.sum(axis=1, keepdims=True)
    return p  # columns: fold, *actions


def _calibrate(evs, actions, targets, hero_range, tau):
    """Find per-action offsets so frequencies (within hero_range) hit the targets."""
    off = {a: 0.0 for a in actions}
    for a in actions:
        if targets.get(a, 0) <= 1e-6:
            off[a] = 1e6
    w = hero_range * CLASS_NCOMBOS
    W = w.sum()
    for _ in range(30):
        for k, a in enumerate(actions):
            if off[a] >= 1e6:
                continue
            lo, hi = -60.0, 60.0
            for _ in range(45):
                mid = (lo + hi) / 2
                off[a] = mid
                f = (_freqs(evs, off, tau, actions)[:, k + 1] * w).sum() / W
                if f > targets[a]:
                    lo = mid
                else:
                    hi = mid
            off[a] = (lo + hi) / 2
    return off


def _solve(scenario, hero, villain, S, ante, profs):
    if scenario == "rfi":
        evs, labels, villains, eq, info = ev_rfi(hero, S, ante, profs)
        return evs, labels, villains, eq, info
    if scenario == "vs_limp":
        return ev_vs_limp(hero, villain, S, ante, profs)
    v = profs[villain]
    fn = {"vs_open": ev_vs_open, "vs_3bet": ev_vs_3bet, "vs_4bet": ev_vs_4bet, "vs_jam": ev_vs_jam}[scenario]
    return fn(hero, villain, S, ante, v)


@lru_cache(maxsize=512)
def _hero_range(scenario: str, hero: str, villain: str, S: float, ante: float, n: int) -> tuple:
    """Hero's own (GTO) range entering this node."""
    if scenario == "vs_3bet":
        res = solve_spot("rfi", hero, None, S, ante, {}, _internal=True, n_players=n)
        return tuple(res["_gto_agg"])
    if scenario == "vs_4bet":
        res = solve_spot("vs_open", hero, villain, S, ante, {}, _internal=True, n_players=n)
        return tuple(res["_gto_agg"])
    return tuple(np.ones(169))


def _targets(scenario, hero, villain, S, labels):
    g = get_profile("gto")
    if scenario == "rfi":
        return {"agg": rfi_width(hero, S, g)}
    if scenario == "vs_open":
        t, c = vs_open_width(hero, villain, S, g)
        return {"agg": t, "call": c}
    if scenario == "vs_3bet":
        f, c = vs_3bet_width(hero, villain, S, g)
        return {"agg": f, "call": c}
    if scenario == "vs_4bet":
        jammed = "agg" not in labels
        j, c = vs_4bet_width(hero, villain, g, jammed)
        return {"agg": j, "call": c}
    return {}


def validate(scenario: str, hero: str, villain: str | None):
    POS = seats()
    if hero not in POS:
        raise ValueError(f"{hero} is not a seat at a {TABLE_NAMES[n_players()]} table")
    hi = POS.index(hero)
    if scenario == "rfi":
        if hero == "BB":
            raise ValueError("BB cannot open first in (everyone folded = walk)")
        return
    if scenario == "vs_limp":
        lim = parse_limpers(villain)
        if not 1 <= len(lim) <= 3 or len(set(lim)) != len(lim):
            raise ValueError("choose 1-3 limpers")
        for l in lim:
            if l not in POS or POS.index(l) >= hi:
                raise ValueError("limpers must act before hero")
            if l == "BB" or (l == "SB" and hero != "BB"):
                raise ValueError("the SB can only 'limp' (complete) when hero is the BB")
        return
    if villain not in POS or villain == hero:
        raise ValueError("choose a villain position")
    vi = POS.index(villain)
    if scenario in ("vs_open", "vs_jam", "vs_4bet"):
        if vi >= hi:
            raise ValueError(f"the {'opener' if scenario != 'vs_jam' else 'jammer'} must act before hero")
    if scenario == "vs_3bet":
        if vi <= hi or hero == "BB":
            raise ValueError("the 3-bettor must act after hero (hero opened)")


def solve_spot(scenario: str, hero: str, villain: str | None, S: float, ante: float,
               villain_profiles: dict[str, str], _internal: bool = False,
               exploit_strength: float = 1.0, n_players: int | None = None) -> dict:
    with table(n_players or _N.get()):
        return _solve_spot(scenario, hero, villain, S, ante, villain_profiles, _internal, exploit_strength)


def _solve_spot(scenario, hero, villain, S, ante, villain_profiles, _internal, exploit_strength):
    validate(scenario, hero, villain)
    S = float(np.clip(S, 5, 300))
    gto = get_profile("gto")
    POS = seats()
    gto_profs = {p: gto for p in POS}
    ex_profs = {p: get_profile(villain_profiles.get(p, "gto")) for p in POS}

    hero_range = np.array(_hero_range(scenario, hero, villain or "", S, ante, n_players()))
    evs_g, labels, vill_g, eq_g, info = _solve(scenario, hero, villain, S, ante, gto_profs)
    evs_x, _, vill_x, eq_x, info_x = _solve(scenario, hero, villain, S, ante, ex_profs)
    actions = [a for a in ("call", "agg") if a in evs_g]
    a_ = float(np.clip(exploit_strength, 0, 1))
    evs_x = {k: evs_g[k] + a_ * (evs_x[k] - evs_g[k]) for k in evs_g}
    pot_scale = dead_money(ante) + (S if scenario == "vs_jam" else 0)
    tau = 0.012 * max(pot_scale, 1.5) * (2.5 if scenario in ("vs_3bet", "vs_4bet") else 1)

    no_fold = scenario == "vs_limp" and hero == "BB"
    if scenario == "vs_jam":
        offsets = {a: 0.0 for a in actions}
        tau = 0.02
    elif scenario == "vs_limp":   # limpers are exploitable by nature: pure best response
        offsets = {a: 0.0 for a in actions}
        tau = 0.012 * _pot_before(scenario, hero, villain, S, ante)
    else:
        targets = _targets(scenario, hero, villain, S, labels)
        targets = {a: targets.get(a, 0) for a in actions}
        offsets = _calibrate(evs_g, actions, targets, hero_range, tau)
        actions = [a for a in actions if offsets[a] < 1e6]   # target 0: never played, don't offer it

    fg = _freqs(evs_g, offsets, tau, actions, no_fold)
    fx = _freqs(evs_x, offsets, tau, actions, no_fold)
    if _internal:
        return {"_gto_agg": fg[:, actions.index("agg") + 1] * hero_range if "agg" in actions else np.zeros(169)}

    keys = (["fold"] if not no_fold else []) + actions
    if no_fold:
        fg, fx = fg[:, 1:], fx[:, 1:]
    act_labels = {"fold": "Fold", **labels}
    # Reported EVs are the calibrated ones the strategy is built from (raw model EV minus the
    # per-action offset that anchors widths to the equilibrium reference), so the most frequent
    # action is also the highest-EV one. Raw model EVs overstate e.g. calling 4-bets.
    evs_g = {a: evs_g[a] - offsets.get(a, 0.0) for a in actions}
    evs_x = {a: evs_x[a] - offsets.get(a, 0.0) for a in actions}
    hands = []
    for i, h in enumerate(HAND_CLASSES):
        hands.append({
            "hand": h,
            "weight": round(float(hero_range[i]), 4),
            "gto": {k: round(float(fg[i, j]), 4) for j, k in enumerate(keys)},
            "exploit": {k: round(float(fx[i, j]), 4) for j, k in enumerate(keys)},
            "ev_gto": {**({} if no_fold else {"fold": 0.0}), **{a: round(float(evs_g[a][i]), 3) for a in actions}},
            "ev_exploit": {**({} if no_fold else {"fold": 0.0}), **{a: round(float(evs_x[a][i]), 3) for a in actions}},
            "equity_gto": None if eq_g is None else round(float(eq_g[i]), 4),
            "equity_exploit": None if eq_x is None else round(float(eq_x[i]), 4),
        })

    def summary(f):
        w = hero_range * CLASS_NCOMBOS
        tot = w.sum()
        return {k: round(float((f[:, j] * w).sum() / tot), 4) for j, k in enumerate(keys)}

    def pack_villains(v):
        if isinstance(v, list):
            out = []
            for x in v:
                out.append({"pos": x["pos"], "profile": x["profile"],
                            "threebet": [round(float(t), 3) for t in x["threebet"]],
                            "call": [round(float(t), 3) for t in x["call"]],
                            "threebet_pct": round(range_pct(x["threebet"]), 4),
                            "call_pct": round(range_pct(x["call"]), 4)})
            return {"players": out}
        return {"ranges": {k: {"weights": [round(float(t), 3) for t in r], "pct": round(range_pct(r), 4),
                               "text": format_range169(r)} for k, r in v.items()}}

    gto_range = {k: [round(float(fg[i, j] * hero_range[i]), 4) for i in range(169)] for j, k in enumerate(keys)}
    return {
        "scenario": scenario, "hero": hero, "villain": villain, "stack": S, "ante": ante,
        "n_players": n_players(), "seats": seats(),
        "actions": [{"key": k, "label": act_labels[k]} for k in keys],
        "hands": hands,
        "summary": {"gto": summary(fg), "exploit": summary(fx)},
        "hero_range_pct": round(range_pct(hero_range), 4),
        "villains_gto": pack_villains(vill_g),
        "villains_exploit": pack_villains(vill_x),
        "info": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in info.items()},
        "info_exploit": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in info_x.items()},
        "gto_action_ranges": {k: format_range169(np.array(v)) for k, v in gto_range.items() if k != "fold"},
        "pot": round(_pot_before(scenario, hero, villain, S, ante), 2),
    }


def _pot_before(scenario, hero, villain, S, ante):
    base = dead_money(ante)
    if scenario == "rfi":
        return base
    if scenario == "vs_limp":
        return base + sum(1.0 - POSTED.get(l, 0.0) for l in parse_limpers(villain))
    o = open_size(villain if scenario in ("vs_open", "vs_4bet", "vs_jam") else hero, S)
    if scenario == "vs_jam":
        return base + S - POSTED.get(villain, 0)
    if scenario == "vs_open":
        return base + o - POSTED.get(villain, 0)
    if scenario == "vs_3bet":
        T = threebet_size(villain, hero, o, S)
        return base + (o - POSTED.get(hero, 0)) + (T - POSTED.get(villain, 0))
    T = threebet_size(hero, villain, o, S)
    F = fourbet_size(T, is_ip(villain, hero), S)
    return base + (F - POSTED.get(villain, 0)) + (T - POSTED.get(hero, 0))
