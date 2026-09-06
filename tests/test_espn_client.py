from draft_picker.espn_client import _normalize_injury_status, relevant_positions


def test_normalize_injury_status_passes_through_plain_string():
    assert _normalize_injury_status("QUESTIONABLE") == "QUESTIONABLE"


def test_normalize_injury_status_handles_none():
    assert _normalize_injury_status(None) == ""


def test_normalize_injury_status_unwraps_a_list():
    # espn_api's generic JSON parser sometimes returns a list here instead of
    # a string (crashed the CLI live: "cannot use 'list' as a dict key").
    assert _normalize_injury_status(["QUESTIONABLE", "ACTIVE"]) == "QUESTIONABLE"


def test_normalize_injury_status_handles_empty_list():
    assert _normalize_injury_status([]) == ""


def test_relevant_positions_excludes_kicker_when_league_has_none():
    # The real league: K capped at 0 starters and 0 max.
    assert "K" not in relevant_positions({"QB": 1, "RB": 2, "K": 0})


def test_relevant_positions_includes_kicker_when_league_starts_one():
    # Was previously hardcoded off everywhere - broke a league that
    # actually starts a kicker (found live against a throwaway league).
    assert "K" in relevant_positions({"QB": 1, "RB": 2, "K": 1})
