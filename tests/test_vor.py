from draft_picker.espn_client import PlayerRow
from draft_picker.vor import effective_starters_per_team, rank_available_players, replacement_ranks

# Mirrors the real league: QB1, RB2, WR3, TE1, FLEX1, OP1, D/ST1, 10 teams
POSITION_SLOT_COUNTS = {
    "QB": 1,
    "RB": 2,
    "WR": 3,
    "TE": 1,
    "FLEX": 1,
    "OP": 1,
    "D/ST": 1,
    "K": 0,
    "BE": 5,
    "IR": 1,
}
TEAM_COUNT = 10


def make_pool(position: str, count: int, start: float, step: float) -> list:
    return [
        PlayerRow(
            player_id=hash((position, i)),
            name=f"{position}{i}",
            position=position,
            pro_team="XXX",
            projected_points=start - i * step,
            injury_status="ACTIVE",
        )
        for i in range(count)
    ]


def test_superflex_pushes_qb_starters_to_two_per_team():
    effective = effective_starters_per_team(POSITION_SLOT_COUNTS)
    assert effective["QB"] == 2.0  # 1 (QB) + 1.0 * OP share


def test_qb_replacement_rank_is_20_deep_in_a_10_team_superflex():
    ranks = replacement_ranks(POSITION_SLOT_COUNTS, TEAM_COUNT)
    assert ranks["QB"] == 20


def test_flex_share_lands_between_rb_wr_te():
    effective = effective_starters_per_team(POSITION_SLOT_COUNTS)
    assert effective["RB"] == 2.4
    assert effective["WR"] == 3.4
    assert effective["TE"] == 1.2


def test_vor_ranks_scarce_position_higher_than_deep_one_at_similar_projection():
    # 25 QBs available (scarce relative to a 20-deep replacement rank) vs
    # 60 WRs available (deep relative to a 34-deep replacement rank).
    # A QB and a WR projected identically should have the QB rank higher.
    pool = make_pool("QB", 25, start=300, step=5) + make_pool("WR", 60, start=300, step=2)

    ranked = rank_available_players(pool, POSITION_SLOT_COUNTS, TEAM_COUNT)
    top = ranked[0]
    assert top.player.position == "QB"


def test_available_pool_shrinks_replacement_level_as_position_thins_out():
    # Only 15 RBs left on the board (fewer than the ~24-deep replacement rank)
    # means even a replacement-level RB left is worth more than usual.
    pool = make_pool("RB", 15, start=200, step=5)
    ranked = rank_available_players(pool, POSITION_SLOT_COUNTS, TEAM_COUNT)
    # replacement rank of 24 exceeds pool size of 15, so baseline should
    # fall back to the worst player left, keeping every VOR non-negative
    assert all(r.vor >= 0 for r in ranked)
