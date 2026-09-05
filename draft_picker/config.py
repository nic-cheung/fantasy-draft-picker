import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    league_id: int
    year: int
    swid: str
    espn_s2: str
    my_team_name: str
    my_draft_position: int
    poll_interval_seconds: int
    top_n: int


def load_config() -> Config:
    swid = os.environ.get("ESPN_SWID", "")
    espn_s2 = os.environ.get("ESPN_S2", "")
    if not swid or not espn_s2:
        raise SystemExit(
            "ESPN_SWID and ESPN_S2 must be set (in .env or the environment) - "
            "see README.md for how to grab them from your browser."
        )

    return Config(
        league_id=int(os.environ.get("ESPN_LEAGUE_ID", "0")),
        year=int(os.environ.get("ESPN_YEAR", "2026")),
        swid=swid,
        espn_s2=espn_s2,
        my_team_name=os.environ.get("MY_TEAM_NAME", ""),
        my_draft_position=int(os.environ.get("MY_DRAFT_POSITION", "1")),
        poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "8")),
        top_n=int(os.environ.get("TOP_N", "15")),
    )
