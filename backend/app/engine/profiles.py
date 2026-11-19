"""Player-type profiles.

Preflop: multipliers applied to reference (GTO-like) action widths.
Postflop: node-lock "shifts" applied to the equilibrium strategy of the villain.
  fold  > 0  : moves that share of call/raise mass into fold (overfolds); < 0 moves fold mass into call
  bet   > 0  : moves that share of check mass into bets;          < 0 moves bets into checks
  raise > 0  : moves that share of call mass into raises;          < 0 moves raises into calls
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Profile:
    key: str
    name: str
    description: str
    # preflop multipliers (1 = reference)
    open: float = 1.0
    threebet: float = 1.0
    call: float = 1.0
    cont_vs_3bet: float = 1.0
    fourbet: float = 1.0
    call_vs_jam: float = 1.0   # >1 calls all-ins lighter
    # postflop node-lock shifts
    fold: float = 0.0
    bet: float = 0.0
    raise_: float = 0.0
    stats: dict = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d["raise"] = d.pop("raise_")
        return d


PROFILES: dict[str, Profile] = {p.key: p for p in [
    Profile("gto", "GTO / Balanced", "Reference equilibrium-style player. No exploitable leaks.",
            stats={"VPIP": "~23%", "PFR": "~19%", "3B": "~8%", "AF": "balanced"}),
    Profile("nit", "Nit", "Plays very few hands, overfolds to aggression, rarely bluffs.",
            open=0.65, threebet=0.55, call=0.75, cont_vs_3bet=0.7, fourbet=0.5, call_vs_jam=0.8,
            fold=0.30, bet=-0.30, raise_=-0.6,
            stats={"VPIP": "~13%", "PFR": "~10%", "3B": "~4%", "AF": "low bluffs"}),
    Profile("tag", "TAG Reg", "Solid tight-aggressive regular, folds a bit too much to raises.",
            open=0.95, threebet=0.95, call=0.85, cont_vs_3bet=0.95, fourbet=0.9,
            fold=0.08, bet=0.0, raise_=-0.1,
            stats={"VPIP": "~21%", "PFR": "~18%", "3B": "~7%", "AF": "solid"}),
    Profile("lag", "LAG", "Loose-aggressive: opens and 3-bets wide, barrels and raises a lot.",
            open=1.3, threebet=1.6, call=1.0, cont_vs_3bet=1.2, fourbet=1.5, call_vs_jam=1.1,
            fold=-0.12, bet=0.30, raise_=0.35,
            stats={"VPIP": "~30%", "PFR": "~25%", "3B": "~12%", "AF": "high"}),
    Profile("station", "Calling Station", "Calls far too much, rarely raises or folds. Value bet thin, don't bluff.",
            open=1.15, threebet=0.45, call=2.3, cont_vs_3bet=1.7, fourbet=0.35, call_vs_jam=1.35,
            fold=-0.60, bet=-0.35, raise_=-0.6,
            stats={"VPIP": "~45%", "PFR": "~8%", "3B": "~3%", "AF": "passive"}),
    Profile("maniac", "Maniac", "Hyper-aggressive: huge ranges, constant betting and raising.",
            open=1.9, threebet=2.6, call=1.2, cont_vs_3bet=1.6, fourbet=2.6, call_vs_jam=1.3,
            fold=-0.30, bet=0.65, raise_=0.7,
            stats={"VPIP": "~55%", "PFR": "~40%", "3B": "~20%", "AF": "very high"}),
    Profile("fish", "Loose-Passive Fish", "Limps/calls too wide preflop, plays fit-or-fold-ish postflop.",
            open=1.4, threebet=0.6, call=2.0, cont_vs_3bet=1.4, fourbet=0.5, call_vs_jam=1.2,
            fold=0.10, bet=-0.25, raise_=-0.4,
            stats={"VPIP": "~38%", "PFR": "~10%", "3B": "~4%", "AF": "passive"}),
    Profile("overfolder", "Weak-Tight Reg", "Decent ranges but folds too much versus bets and raises.",
            open=0.9, threebet=0.8, call=0.9, cont_vs_3bet=0.75, fourbet=0.7, call_vs_jam=0.85,
            fold=0.30, bet=-0.05, raise_=-0.3,
            stats={"VPIP": "~19%", "PFR": "~15%", "3B": "~5%", "AF": "overfolds"}),
]}


def get_profile(key: str | None, custom: dict | None = None) -> Profile:
    base = PROFILES.get(key or "gto", PROFILES["gto"])
    if not custom:
        return base
    d = base.to_dict()
    d.update({k: v for k, v in custom.items() if v is not None})
    d["raise_"] = d.pop("raise")
    d["key"] = "custom"
    d["name"] = "Custom"
    return Profile(**d)
