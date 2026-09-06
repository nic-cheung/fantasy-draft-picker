"""Value Over Replacement (VOR) ranking, tuned for this league's roster shape.

Standard ADP/expert rankings assume a single-QB league. This league has a
QB slot *and* an OP (superflex) slot that any offensive player can fill but
which a second startable QB almost always wins in practice (QBs out-score
flex-quality RB/WR/TE on a per-game basis under standard scoring). So we
treat OP as a second QB slot. The single FLEX slot is split across
RB/WR/TE using a typical redraft flex-usage share.

This is a simplifying assumption, not a solved allocation problem - tune
FLEX_SHARE / OP_SHARE below if your gut says otherwise.

ESPN actually has three flex-type slots, not one: id 23 ("RB/WR/TE", the
"real" FLEX), id 3 ("RB/WR"), and id 5 ("WR/TE"). This league only uses the
first, but another community tool's code comments describe a production bug
where reading only slot 23 silently zeroed out a league using slot 3 - so
all three are counted here for any league this gets reused on.
"""

import math
from dataclasses import dataclass
from typing import Dict, List

from .espn_client import PlayerRow

FLEX_SHARE = {"RB": 0.4, "WR": 0.4, "TE": 0.2}
RB_WR_SHARE = {"RB": 0.5, "WR": 0.5}
WR_TE_SHARE = {"WR": 0.5, "TE": 0.5}
OP_SHARE = {"QB": 1.0}


@dataclass
class RankedPlayer:
    player: PlayerRow
    vor: float
    replacement_points: float


def effective_starters_per_team(position_slot_counts: Dict[str, int]) -> Dict[str, float]:
    base = {
        "QB": position_slot_counts.get("QB", 0),
        "RB": position_slot_counts.get("RB", 0),
        "WR": position_slot_counts.get("WR", 0),
        "TE": position_slot_counts.get("TE", 0),
        "D/ST": position_slot_counts.get("D/ST", 0),
        "K": position_slot_counts.get("K", 0),
    }
    flex_count = position_slot_counts.get("FLEX", 0) + position_slot_counts.get("RB/WR/TE", 0)
    rb_wr_count = position_slot_counts.get("RB/WR", 0)
    wr_te_count = position_slot_counts.get("WR/TE", 0)
    op_count = position_slot_counts.get("OP", 0)

    for pos, share in FLEX_SHARE.items():
        base[pos] += share * flex_count
    for pos, share in RB_WR_SHARE.items():
        base[pos] += share * rb_wr_count
    for pos, share in WR_TE_SHARE.items():
        base[pos] += share * wr_te_count
    for pos, share in OP_SHARE.items():
        base[pos] += share * op_count

    return base


def replacement_ranks(position_slot_counts: Dict[str, int], team_count: int) -> Dict[str, int]:
    effective = effective_starters_per_team(position_slot_counts)
    return {pos: max(1, round(starters * team_count)) for pos, starters in effective.items()}


def roster_needs(my_position_counts: Dict[str, int], position_slot_counts: Dict[str, int]) -> Dict[str, int]:
    """How many more starters you still need at each position.

    Rounds each position's fractional "effective starters" (flex/OP shares
    included) up to a whole target, then subtracts what you've already
    drafted. This is a heuristic, not exact truth - the shared flex/OP slots
    make an exact per-position target impossible - but good enough to flag
    "you still need a TE" versus "you're just adding depth here now."
    """
    effective = effective_starters_per_team(position_slot_counts)
    needs = {}
    for pos, starters in effective.items():
        target = math.ceil(starters)
        have = my_position_counts.get(pos, 0)
        needs[pos] = max(0, target - have)
    return needs


def rank_available_players(
    available: List[PlayerRow],
    position_slot_counts: Dict[str, int],
    team_count: int,
) -> List[RankedPlayer]:
    by_position: Dict[str, List[PlayerRow]] = {}
    for p in available:
        by_position.setdefault(p.position, []).append(p)
    for players in by_position.values():
        players.sort(key=lambda p: p.projected_points, reverse=True)

    ranks = replacement_ranks(position_slot_counts, team_count)

    replacement_points: Dict[str, float] = {}
    for pos, players in by_position.items():
        rank = ranks.get(pos, len(players))
        idx = min(rank, len(players)) - 1
        replacement_points[pos] = players[idx].projected_points if idx >= 0 and players else 0.0

    ranked = [
        RankedPlayer(
            player=p,
            vor=p.projected_points - replacement_points.get(p.position, 0.0),
            replacement_points=replacement_points.get(p.position, 0.0),
        )
        for p in available
    ]
    ranked.sort(key=lambda r: r.vor, reverse=True)
    return ranked
