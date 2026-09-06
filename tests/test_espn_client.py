from draft_picker.espn_client import _normalize_injury_status


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
