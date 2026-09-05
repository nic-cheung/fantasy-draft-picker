"""Value Over Replacement (VOR) ranking, tuned for this league's roster shape.

Standard ADP/expert rankings assume a single-QB league. This league has a
QB slot *and* an OP (superflex) slot that any offensive player can fill but
which a second startable QB almost always wins in practice (QBs out-score
flex-quality RB/WR/TE on a per-game basis under standard scoring). So we
treat OP as a second QB slot. The single FLEX slot is split across
RB/WR/TE using a typical redraft flex-usage share.

This is a simplifying assumption, not a solved allocation problem - tune
FLEX_SHARE / OP_SHARE below if your gut says otherwise.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from .espn_client import PlayerRow

FLEX_SHARE = {"RB": 0.4, "WR": 0.4, "TE": 0.2}
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
    }
    flex_count = position_slot_counts.get("FLEX", 0) + position_slot_counts.get("RB/WR/TE", 0)
    op_count = position_slot_counts.get("OP", 0)

    for pos, share in FLEX_SHARE.items():
        base[pos] += share * flex_count
    for pos, share in OP_SHARE.items():
        base[pos] += share * op_count

    return base


def replacement_ranks(position_slot_counts: Dict[str, int], team_count: int) -> Dict[str, int]:
    effective = effective_starters_per_team(position_slot_counts)
    return {pos: max(1, round(starters * team_count)) for pos, starters in effective.items()}


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
