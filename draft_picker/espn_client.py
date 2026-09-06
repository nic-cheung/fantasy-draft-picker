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
    """Re-fetches the draft log directly from ESPN's raw response.

    espn_api's own League.refresh_draft()/_fetch_draft() only populates
    league.draft once draftDetail['drafted'] is True - and ESPN doesn't set
    that until the ENTIRE draft is complete, not when it starts (confirmed
    live: 'drafted': False, 'inProgress': True, mid-draft). That makes the
    library's built-in draft tracking useless during a live draft, so we
    parse the raw picks list ourselves: every pick slot already exists in
    the response with playerId -1 as a placeholder before it's made.
    """
    data = league.espn_request.get_league_draft()
    raw_picks = data.get("draftDetail", {}).get("picks", [])

    picks: List[PickRow] = []
    for pick in raw_picks:
        player_id = pick.get("playerId", -1)
        if not player_id or player_id <= 0:
            continue
        team = league.get_team_data(pick.get("teamId"))
        picks.append(
            PickRow(
                pick_number=pick.get("overallPickNumber"),
                round_num=pick.get("roundId"),
                round_pick=pick.get("roundPickNumber"),
                team_name=team.team_name if team else "Unknown",
                player_name=league.player_map.get(player_id, f"Player {player_id}"),
                player_id=player_id,
            )
        )
    picks.sort(key=lambda p: p.pick_number)
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
