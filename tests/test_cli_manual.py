import io

from rich.console import Console

from draft_picker import cli, espn_client


def _pool(*rows):
    return {i: espn_client.PlayerRow(i, name, pos, team, pts, "") for i, (name, pos, team, pts) in enumerate(rows, start=1)}


def _quiet_console() -> Console:
    return Console(file=io.StringIO())


def test_find_matches_short_fragment():
    pool = _pool(("Christian McCaffrey", "RB", "SF", 300.0))
    matches = cli._find_matches("mccaffrey", list(pool.values()))
    assert [p.name for p in matches] == ["Christian McCaffrey"]


def test_find_matches_full_name_pasted_as_single_line():
    pool = _pool(("Christian McCaffrey", "RB", "SF", 300.0))
    matches = cli._find_matches("Rd 2, Pick 1 - Christian McCaffrey RB SF", list(pool.values()))
    assert [p.name for p in matches] == ["Christian McCaffrey"]


def test_plan_pasted_blob_extracts_round_table_and_picks_sidebar():
    pool = _pool(
        ("Josh Allen", "QB", "BUF", 370.6),
        ("Christian McCaffrey", "RB", "SF", 302.4),
    )
    blob = """
Round 1
Pick
Player
Team
2025 PTS
PROJ PTS
RK
1

Josh Allen
BUF
QB
Ashu's Awesome Team
364.6
370.6
1
Picks

Christian McCaffrey / SF RB
R1, P2 - Some Team
"""
    new_players, already, ignored, preview_skipped = cli._plan_pasted_blob(blob, pool, set(), _quiet_console())
    assert [p.name for p in new_players] == ["Josh Allen", "Christian McCaffrey"]
    assert already == 0
    assert preview_skipped == 0


def test_plan_pasted_blob_is_idempotent_on_repeated_full_history():
    pool = _pool(("Josh Allen", "QB", "BUF", 370.6))
    blob = "Josh Allen / BUF QB\nR1, P1 - Some Team"
    console = _quiet_console()

    drafted_ids = set()
    new_players, _, _, _ = cli._plan_pasted_blob(blob, pool, drafted_ids, console)
    assert [p.name for p in new_players] == ["Josh Allen"]
    for p in new_players:
        drafted_ids.add(p.player_id)

    # Re-pasting the SAME (or a growing) block should find nothing new,
    # since Nic's actual workflow is re-pasting the whole history from
    # pick 1 every time rather than tracking where he left off.
    new_players_again, already, _, _ = cli._plan_pasted_blob(blob, pool, drafted_ids, console)
    assert new_players_again == []
    assert already == 1


def test_plan_pasted_blob_ignores_on_the_clock_autopick_preview():
    # Confirmed live: the "You are on the clock!" widget names the
    # AUTOPICK SUGGESTION for the current pick, not a completed one - it
    # must not be recorded as a real pick just because it mentions a real,
    # undrafted player's name.
    pool = _pool(
        ("Josh Allen", "QB", "BUF", 370.6),
        ("Puka Nacua", "WR", "LAR", 292.0),
    )
    blob = """
Roster Limits
0/15 Players
Puka Nacua
You are on the clock!
Your autopick would be: Puka Nacua / Los Angeles Rams WR

Round 1
Pick
Player
Team
2025 PTS
PROJ PTS
RK
1

Josh Allen
BUF
QB
Ashu's Awesome Team
364.6
370.6
1
"""
    new_players, _, _, preview_skipped = cli._plan_pasted_blob(blob, pool, set(), _quiet_console())
    assert [p.name for p in new_players] == ["Josh Allen"]
    assert preview_skipped > 0


def test_plan_pasted_blob_skips_ambiguous_short_fragment():
    # A bare short fragment matching two different full names (as opposed
    # to a full name being a substring of a noisy line) is a genuine
    # ambiguity and must not be guessed at.
    pool = _pool(
        ("Josh Allen", "QB", "BUF", 370.6),
        ("Josh Jacobs", "RB", "GB", 250.0),
    )
    new_players, _, _, _ = cli._plan_pasted_blob("Josh", pool, set(), _quiet_console())
    assert new_players == []


def test_commit_planned_picks_assigns_pick_number_and_team():
    pool = _pool(("Josh Allen", "QB", "BUF", 370.6))
    console = _quiet_console()
    picks: list = []
    drafted_ids: set = set()

    class Cfg:
        my_team_name = "Nic's Nifty Team"
        my_draft_position = 6

    new_players, _, _, _ = cli._plan_pasted_blob("Josh Allen / BUF QB\nR1, P1", pool, drafted_ids, console)
    cli._commit_planned_picks(new_players, picks, drafted_ids, team_count=10, cfg=Cfg())

    assert len(picks) == 1
    assert picks[0].pick_number == 1
    assert picks[0].team_name == "Team 1"  # pick 1 -> slot 1, not Nic's slot 6
    assert 1 in drafted_ids
