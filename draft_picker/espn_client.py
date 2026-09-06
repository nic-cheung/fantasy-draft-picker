import time
from dataclasses import dataclass
from typing import Dict, List, Set

import requests
from espn_api.football import League

from .config import Config

BASE_POSITIONS = {"QB", "RB", "WR", "TE", "D/ST"}


def relevant_positions(position_slot_counts: Dict[str, int]) -> Set[str]:
    """Which positions this league actually drafts.

    QB/RB/WR/TE/D/ST are always included. K is excluded unless the league
    actually starts one - it was previously hardcoded off everywhere, which
    was only correct by coincidence (the real league has K capped at 0
    starters/0 max) and silently broke a league that does use a kicker.
    """
    positions = set(BASE_POSITIONS)
    if position_slot_counts.get("K", 0) > 0:
        positions.add("K")
    return positions


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
    positions = relevant_positions(league.settings.position_slot_counts)
    players = league.free_agents(size=size)
    pool: Dict[int, PlayerRow] = {}
    for p in players:
        if p.position not in positions:
            continue
        pool[p.playerId] = PlayerRow(
            player_id=p.playerId,
            name=p.name,
            position=p.position,
            pro_team=p.proTeam,
            projected_points=p.projected_total_points,
            injury_status=_normalize_injury_status(p.injuryStatus),
        )
    return pool


def _normalize_injury_status(raw) -> str:
    """espn_api's generic JSON parser sometimes returns a list here instead
    of a string (e.g. for D/ST "players" where the field appears more than
    once in ESPN's nested response) - confirmed live, crashed the CLI
    ('list' isn't hashable as a dict key). Always return a plain string."""
    if isinstance(raw, list):
        return raw[0] if raw else ""
    return raw or ""


def _get_league_draft_uncached(league: League) -> dict:
    """Fetches the draft view with cache-busting - bypasses espn_api's
    get_league_draft(), which sends a plain GET with no cache-prevention
    headers or unique query param. That's exactly the kind of request a
    caching layer between us and ESPN (a corporate proxy, a CDN) can serve
    stale from cache indefinitely - confirmed live: real picks visible on
    ESPN's own draft screen still came back as unpicked (playerId -1)
    several minutes later through the plain request.
    """
    endpoint = league.espn_request.LEAGUE_ENDPOINT
    params = {"view": "mDraftDetail", "_": str(int(time.time() * 1000))}
    headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
    response = requests.get(endpoint, params=params, headers=headers, cookies=league.espn_request.cookies)
    response.raise_for_status()
    return response.json()


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
    data = _get_league_draft_uncached(league)
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
