from dataclasses import dataclass
from typing import Dict, List, Set

from espn_api.football import League

from .config import Config

RELEVANT_POSITIONS = {"QB", "RB", "WR", "TE", "D/ST"}


@dataclass
class PlayerRow:
    player_id: int
    name: str
    position: str
    pro_team: str
    projected_points: float
    injury_status: str


@dataclass
class PickRow:
    pick_number: int
    round_num: int
    round_pick: int
    team_name: str
    player_name: str
    player_id: int


def connect(config: Config) -> League:
    return League(
        league_id=config.league_id,
        year=config.year,
        espn_s2=config.espn_s2,
        swid=config.swid,
    )


def fetch_player_pool(league: League, size: int = 3000) -> Dict[int, PlayerRow]:
    """One-time pull of every draftable player with this league's projected points.

    ESPN computes `projected_total_points` using the league's own scoring
    settings (half-PPR etc. are already baked in), so no manual scoring math
    is needed here - just VOR on top of it.
    """
    players = league.free_agents(size=size)
    pool: Dict[int, PlayerRow] = {}
    for p in players:
        if p.position not in RELEVANT_POSITIONS:
            continue
        pool[p.playerId] = PlayerRow(
            player_id=p.playerId,
            name=p.name,
            position=p.position,
            pro_team=p.proTeam,
            projected_points=p.projected_total_points,
            injury_status=p.injuryStatus,
        )
    return pool


def refresh_draft_picks(league: League) -> List[PickRow]:
    """Re-fetches the draft log.

    league.draft is append-only in espn_api (refresh_draft doesn't clear it),
    so we reset it ourselves before refetching to avoid piling up duplicates.
    """
    league.draft = []
    league.refresh_draft()

    picks: List[PickRow] = []
    for i, pick in enumerate(league.draft, start=1):
        picks.append(
            PickRow(
                pick_number=i,
                round_num=pick.round_num,
                round_pick=pick.round_pick,
                team_name=pick.team.team_name if pick.team else "Unknown",
                player_name=pick.playerName,
                player_id=pick.playerId,
            )
        )
    return picks


def drafted_player_ids(picks: List[PickRow]) -> Set[int]:
    return {p.player_id for p in picks}


def my_picks(picks: List[PickRow], my_team_name: str) -> List[PickRow]:
    """Picks belonging to my team, matched straight off the live draft log

    (rather than league.teams[*].roster, which only updates on a full
    League refetch, not on the lightweight refresh_draft poll)."""
    if not my_team_name:
        return []
    target = my_team_name.strip().lower()
    return [p for p in picks if p.team_name.strip().lower() == target]
