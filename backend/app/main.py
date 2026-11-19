"""PokerGTO local API."""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional, Union

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import threading
import uuid
from collections import OrderedDict

from .engine import postflop, postflop2, preflop, trainer
from .engine.cards import (ALL_COMBOS, CLASS_NCOMBOS, COMBO_CLASS, HAND_CLASSES, class_weights_to_combo,
                           combo_str, combo_weights_to_class, parse_cards)
from .engine.equity import combo_matrix, preflop_matrix
from .engine.handclass import MADE_CATS, classify
from .engine.profiles import PROFILES, get_profile
from .engine.ranges import format_range169, parse_range, range_pct

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="PokerGTO Local", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _warm():
    preflop_matrix()


RangeIn = Union[str, list[float]]


def to_1326(r: RangeIn) -> np.ndarray:
    if isinstance(r, str):
        return parse_range(r)
    arr = np.asarray(r, dtype=float)
    if arr.shape == (169,):
        return class_weights_to_combo(np.clip(arr, 0, 1))
    if arr.shape == (1326,):
        return np.clip(arr, 0, 1)
    raise HTTPException(400, "range must be text, 169 or 1326 weights")


def bad(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------ meta
@app.get("/api/meta")
def meta():
    return {
        "positions": preflop.POS,
        "seats": {str(k): v for k, v in preflop.SEATS.items()},
        "table_names": {str(k): v for k, v in preflop.TABLE_NAMES.items()},
        "scenarios": preflop.SCENARIOS,
        "profiles": [p.to_dict() for p in PROFILES.values()],
        "hand_classes": HAND_CLASSES,
        "class_combos": CLASS_NCOMBOS.tolist(),
        "made_categories": MADE_CATS,
    }


# ------------------------------------------------------------------ preflop
class PreflopReq(BaseModel):
    scenario: str = "rfi"
    hero: str = "BTN"
    villain: Optional[str] = None
    stack: float = 100
    ante: float = 0
    villain_profiles: dict[str, str] = Field(default_factory=dict)
    exploit_strength: float = 1.0
    n_players: int = 6
    limpers: list[str] = Field(default_factory=list)


@app.post("/api/preflop")
def preflop_spot(req: PreflopReq):
    try:
        villain = ",".join(req.limpers) if req.scenario == "vs_limp" else req.villain
        return preflop.solve_spot(req.scenario, req.hero, villain, req.stack, req.ante,
                                  req.villain_profiles, exploit_strength=req.exploit_strength,
                                  n_players=req.n_players)
    except ValueError as e:
        bad(e)


# ------------------------------------------------------------------ postflop presets
class PresetReq(BaseModel):
    pot_type: str = "srp"           # srp | 3bp | 4bp
    opener: str = "BTN"
    defender: str = "BB"
    stack: float = 100
    ante: float = 0
    profiles: dict[str, str] = Field(default_factory=dict)  # used for the villain's range
    hero: str = "BTN"
    n_players: int = 6


def _freq(res, action):
    return np.array([h["gto"].get(action, 0.0) * h["weight"] for h in res["hands"]])


def _freq_ex(res, action):
    return np.array([h["exploit"][action] * h["weight"] for h in res["hands"]])


@lru_cache(maxsize=256)
def _preset(pot_type, opener, defender, stack, ante, prof_items, hero, n=6):
    with preflop.table(n):
        return _preset_inner(pot_type, opener, defender, stack, ante, prof_items, hero)


def _preset_inner(pot_type, opener, defender, stack, ante, prof_items, hero):
    profs = dict(prof_items)
    seat_list = preflop.seats()
    if opener not in seat_list or defender not in seat_list:
        raise ValueError("those seats don't exist at this table size")
    if seat_list.index(defender) <= seat_list.index(opener):
        raise ValueError("the caller / 3-bettor must act after the opener")
    S = stack
    base = preflop.dead_money(ante)
    o = preflop.open_size(opener, S)
    if o >= S:
        raise ValueError("at this stack depth the open is an all-in: no postflop play")

    def pick(pos, res, action):
        # hero always GTO range; villain range reflects its profile
        if pos != hero and profs.get(pos, "gto") != "gto":
            return _villain_range(pot_type, pos, opener, defender, S, ante, profs[pos], res, action)
        return _freq(res, action)

    if pot_type == "srp":
        r_open = preflop.solve_spot("rfi", opener, None, S, ante, {})
        r_def = preflop.solve_spot("vs_open", defender, opener, S, ante, {})
        ranges = {opener: pick(opener, r_open, "agg"), defender: pick(defender, r_def, "call")}
        pot = base + 2 * o - preflop.POSTED.get(opener, 0) - preflop.POSTED.get(defender, 0)
        stack_left = S - o
    elif pot_type == "3bp":
        T = preflop.threebet_size(defender, opener, o, S)
        if T >= S:
            raise ValueError("at this stack depth the 3-bet is an all-in")
        r_def = preflop.solve_spot("vs_open", defender, opener, S, ante, {})
        r_op = preflop.solve_spot("vs_3bet", opener, defender, S, ante, {})
        ranges = {defender: pick(defender, r_def, "agg"), opener: pick(opener, r_op, "call")}
        pot = base + 2 * T - preflop.POSTED.get(opener, 0) - preflop.POSTED.get(defender, 0)
        stack_left = S - T
    elif pot_type == "4bp":
        T = preflop.threebet_size(defender, opener, o, S)
        F = preflop.fourbet_size(T, preflop.is_ip(opener, defender), S)
        if T >= S or F >= S:
            raise ValueError("at this stack depth the 4-bet is an all-in")
        r_op = preflop.solve_spot("vs_3bet", opener, defender, S, ante, {})
        r_def = preflop.solve_spot("vs_4bet", defender, opener, S, ante, {})
        ranges = {opener: pick(opener, r_op, "agg"), defender: pick(defender, r_def, "call")}
        pot = base + 2 * F - preflop.POSTED.get(opener, 0) - preflop.POSTED.get(defender, 0)
        stack_left = S - F
    else:
        raise ValueError("unknown pot type")
    ip_pos = opener if preflop.is_ip(opener, defender) else defender
    oop_pos = defender if ip_pos == opener else opener
    pack = lambda p: {"pos": p, "weights": [round(float(x), 4) for x in ranges[p]],
                      "pct": round(range_pct(ranges[p]), 4), "text": format_range169(ranges[p])}
    return {"oop": pack(oop_pos), "ip": pack(ip_pos), "pot": round(pot, 2), "stack": round(stack_left, 2),
            "hero": "IP" if hero == ip_pos else "OOP"}


def _villain_range(pot_type, pos, opener, defender, S, ante, prof_key, res_gto, action):
    """Villain's range for this line given its profile (exploit preflop solution from its seat)."""
    prof = get_profile(prof_key)
    if pot_type == "srp":
        if pos == opener:
            return preflop.villain_rfi(opener, S, prof)
        _, call = preflop.villain_vs_open(defender, opener, S, prof)
        return call
    if pot_type == "3bp":
        if pos == defender:
            r3, _ = preflop.villain_vs_open(defender, opener, S, prof)
            return r3
        open_r = preflop.villain_rfi(opener, S, prof)
        f, c = preflop.vs_3bet_width(opener, defender, S, prof)
        from .engine.ranges import build_raise_call
        _, call = build_raise_call(f, c, within=open_r, polar=0.25)
        return call
    return _freq(res_gto, action)


@app.post("/api/postflop/preset")
def postflop_preset(req: PresetReq):
    try:
        if req.hero not in (req.opener, req.defender):
            raise ValueError("hero must be the opener or the defender")
        return _preset(req.pot_type, req.opener, req.defender, float(req.stack), float(req.ante),
                       tuple(sorted(req.profiles.items())), req.hero, int(req.n_players))
    except ValueError as e:
        bad(e)


# ------------------------------------------------------------------ postflop solve
class PostflopReq(BaseModel):
    board: str
    oop_range: RangeIn
    ip_range: RangeIn
    pot: float = 5.5
    stack: float = 97.5
    oop_bets: list[float] = Field(default_factory=lambda: [0.33, 0.75])
    ip_bets: list[float] = Field(default_factory=lambda: [0.33, 0.75])
    raise_mult: float = 3.0
    allow_raise: bool = True
    add_allin: bool = False
    iterations: int = 300
    hero: str = "IP"
    villain_profile: str = "gto"
    custom_profile: Optional[dict] = None
    hero_hand: Optional[str] = None
    exploit_strength: float = 1.0
    exact_river: bool = True                     # turn boards: solve turn + every river exactly
    river_oop_bets: list[float] = Field(default_factory=lambda: [0.75])
    river_ip_bets: list[float] = Field(default_factory=lambda: [0.75])


_SOLVES: "OrderedDict[str, dict]" = OrderedDict()
_SOLVES_LOCK = threading.Lock()
MAX_CACHED_SOLVES = 2   # each turn+river solve keeps ~100-300 MB of tensors for river browsing


@app.post("/api/postflop/solve")
def postflop_solve(req: PostflopReq):
    try:
        board = parse_cards(req.board)
        hero_combo = tuple(parse_cards(req.hero_hand)) if req.hero_hand else None
        if hero_combo is not None and len(hero_combo) != 2:
            raise ValueError("hero hand must be 2 cards")
        bets_o = [b for b in req.oop_bets if 0 < b <= 5][:4]
        bets_i = [b for b in req.ip_bets if 0 < b <= 5][:4]
        if len(board) == 4 and req.exact_river:
            rb_o = [b for b in req.river_oop_bets if 0 < b <= 5][:3]
            rb_i = [b for b in req.river_ip_bets if 0 < b <= 5][:3]
            res, state = postflop2.solve_turn(
                board, to_1326(req.oop_range), to_1326(req.ip_range), req.pot, req.stack,
                bets_o, bets_i, rb_o, rb_i, raise_mult=max(2.0, req.raise_mult),
                allow_raise=req.allow_raise, add_allin=req.add_allin,
                iterations=int(np.clip(req.iterations, 30, 1000)),
                villain_is=1 if req.hero.upper() == "OOP" else 0,
                villain_profile=get_profile(req.villain_profile, req.custom_profile),
                hero_combo=hero_combo, exploit_strength=req.exploit_strength)
            sid = uuid.uuid4().hex
            with _SOLVES_LOCK:
                _SOLVES[sid] = state
                while len(_SOLVES) > MAX_CACHED_SOLVES:
                    _SOLVES.popitem(last=False)
            res["solve_id"] = sid
            return res
        return postflop.solve(board, to_1326(req.oop_range), to_1326(req.ip_range), req.pot, req.stack,
                              bets_o, bets_i, raise_mult=max(2.0, req.raise_mult),
                              allow_raise=req.allow_raise, add_allin=req.add_allin,
                              iterations=int(np.clip(req.iterations, 50, 2000)),
                              villain_is=1 if req.hero.upper() == "OOP" else 0,
                              villain_profile=get_profile(req.villain_profile, req.custom_profile),
                              hero_combo=hero_combo, exploit_strength=req.exploit_strength)
    except ValueError as e:
        bad(e)


class RiverReq(BaseModel):
    solve_id: str
    chance: int
    river: str


@app.post("/api/postflop/river")
def postflop_river(req: RiverReq):
    with _SOLVES_LOCK:
        state = _SOLVES.get(req.solve_id)
    if state is None:
        raise HTTPException(410, "this solve is no longer cached - re-run the solve")
    try:
        cards = parse_cards(req.river)
        if len(cards) != 1:
            raise ValueError("river must be one card")
        return postflop2.river_view(state, req.chance, cards[0])
    except ValueError as e:
        bad(e)


# ------------------------------------------------------------------ trainer
class TrainerReq(BaseModel):
    streets: list[str] = Field(default_factory=lambda: ["preflop", "flop"])
    positions: list[str] = Field(default_factory=lambda: list(preflop.POS))
    scenarios: list[str] = Field(default_factory=lambda: ["rfi", "vs_open", "vs_3bet"])
    pot_types: list[str] = Field(default_factory=lambda: ["srp", "3bp"])
    stacks: list[float] = Field(default_factory=lambda: [100])
    profile: str = "gto"
    tricky: bool = False
    n_players: int = 6


@app.post("/api/trainer/spot")
def trainer_spot(req: TrainerReq):
    try:
        return trainer.generate(req.model_dump())
    except ValueError as e:
        bad(e)


# ------------------------------------------------------------------ equity calculator
class EquityReq(BaseModel):
    hero: str           # hand "AhKh" or range text
    villain: str
    board: str = ""


def _as_weights(s: str, dead: list[int]) -> np.ndarray:
    s = s.strip()
    try:
        cards = parse_cards(s)
        if len(cards) == 2:
            from .engine.cards import COMBO_INDEX
            w = np.zeros(1326)
            w[COMBO_INDEX[tuple(sorted(cards))]] = 1
            return w
    except ValueError:
        pass
    return parse_range(s)


@app.post("/api/equity")
def equity(req: EquityReq):
    try:
        board = parse_cards(req.board)
        if len(board) not in (0, 3, 4, 5):
            raise ValueError("board must have 0, 3, 4 or 5 cards")
        wh = _as_weights(req.hero, board)
        wv = _as_weights(req.villain, board)
        from .engine.cards import blocked_mask
        bm = blocked_mask(tuple(sorted(board)))
        wh[bm] = 0
        wv[bm] = 0
        ih, iv = np.nonzero(wh > 1e-4)[0], np.nonzero(wv > 1e-4)[0]
        if len(ih) == 0 or len(iv) == 0:
            raise ValueError("empty range/hand after board removal")
        if len(ih) * len(iv) > 400_000:
            raise ValueError("ranges too large for the calculator; narrow them")
        runs = 1500 if len(board) == 0 else (400 if len(board) == 3 else 1000)
        if len(board) == 0:
            runs = max(150, min(1500, 3_000_000 // max(1, len(ih) + len(iv)) // 4))
        E, M = combo_matrix(ih, iv, board, max_runouts=runs)
        a, b = wh[ih], wv[iv]
        pair_w = np.outer(a, b) * M
        tot = pair_w.sum()
        if tot <= 0:
            raise ValueError("no non-conflicting combinations")
        eq = float((E * pair_w).sum() / tot)
        per_h = np.divide((E * pair_w).sum(1), pair_w.sum(1), out=np.zeros(len(ih)), where=pair_w.sum(1) > 0)
        out = {"hero_equity": round(eq, 4), "villain_equity": round(1 - eq, 4),
               "hero_combos": len(ih), "villain_combos": len(iv), "exact": len(board) >= 4}
        # villain breakdown by made category (postflop only)
        if board:
            cats = {}
            per_v_eq = np.divide((E * pair_w).sum(0), pair_w.sum(0), out=np.zeros(len(iv)), where=pair_w.sum(0) > 0)
            vw = pair_w.sum(0)
            for k, ci in enumerate(iv):
                made, draw = classify(ALL_COMBOS[ci], board)
                d = cats.setdefault(made, [0.0, 0.0])
                d[0] += vw[k]
                d[1] += vw[k] * per_v_eq[k]
            out["vs_categories"] = [{"name": n, "pct": round(cats[n][0] / tot, 4),
                                     "hero_eq": round(cats[n][1] / cats[n][0], 4)}
                                    for n in MADE_CATS if n in cats and cats[n][0] > 0]
        top = np.argsort(-per_h)
        out["hero_hands"] = [{"combo": combo_str(ALL_COMBOS[ih[k]]), "equity": round(float(per_h[k]), 4)}
                             for k in top[:300]]
        return out
    except ValueError as e:
        bad(e)


# ------------------------------------------------------------------ range utils
class RangeText(BaseModel):
    text: str


@app.post("/api/range/parse")
def range_parse(req: RangeText):
    try:
        w = combo_weights_to_class(parse_range(req.text))
        return {"weights": [round(float(x), 4) for x in w], "pct": round(range_pct(w), 4)}
    except ValueError as e:
        bad(e)


class RangeWeights(BaseModel):
    weights: list[float]


@app.post("/api/range/format")
def range_format(req: RangeWeights):
    w = np.asarray(req.weights, float)
    return {"text": format_range169(w), "pct": round(range_pct(w), 4)}


# ------------------------------------------------------------------ serve built frontend
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
