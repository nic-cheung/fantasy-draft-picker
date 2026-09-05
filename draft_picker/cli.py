import argparse
import time
from typing import List

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from . import espn_client
from .config import load_config
from .vor import RankedPlayer, rank_available_players

INJURY_FLAG = {"OUT": "OUT", "DOUBTFUL": "D", "QUESTIONABLE": "Q", "SUSPENSION": "SUSP"}


def snake_pick_numbers(my_slot: int, team_count: int, rounds: int) -> List[int]:
    numbers = []
    for round_num in range(1, rounds + 1):
        if round_num % 2 == 1:
            position_in_round = my_slot
        else:
            position_in_round = team_count - my_slot + 1
        numbers.append((round_num - 1) * team_count + position_in_round)
    return numbers


def render_header(console_width: int, picks, my_pick_numbers: List[int]) -> Panel:
    next_pick_number = len(picks) + 1
    upcoming = [n for n in my_pick_numbers if n >= next_pick_number]
    if not upcoming:
        turn_text = "[green]Draft complete for you[/green]"
    else:
        gap = upcoming[0] - next_pick_number
        if gap == 0:
            turn_text = "[bold green]YOU ARE ON THE CLOCK[/bold green]"
        else:
            turn_text = f"{gap} pick(s) until your turn (pick #{upcoming[0]})"

    text = f"Pick #{next_pick_number} on the clock  |  {turn_text}"
    return Panel(text, title="Draft Status")


def render_top_table(ranked: List[RankedPlayer], top_n: int) -> Table:
    table = Table(title=f"Best Available (Top {top_n} by VOR)")
    table.add_column("#", justify="right")
    table.add_column("Player")
    table.add_column("Pos")
    table.add_column("Team")
    table.add_column("Proj Pts", justify="right")
    table.add_column("VOR", justify="right")
    table.add_column("Injury")

    for i, r in enumerate(ranked[:top_n], start=1):
        injury = INJURY_FLAG.get(r.player.injury_status, "")
        table.add_row(
            str(i),
            r.player.name,
            r.player.position,
            r.player.pro_team,
            f"{r.player.projected_points:.1f}",
            f"{r.vor:+.1f}",
            f"[red]{injury}[/red]" if injury else "",
        )
    return table


def render_position_table(ranked: List[RankedPlayer], positions: List[str], per_pos: int = 5) -> Table:
    table = Table(title="Best Available by Position")
    table.add_column("Pos")
    table.add_column("Player")
    table.add_column("Proj Pts", justify="right")
    table.add_column("VOR", justify="right")

    for pos in positions:
        pos_players = [r for r in ranked if r.player.position == pos][:per_pos]
        for j, r in enumerate(pos_players):
            table.add_row(
                pos if j == 0 else "",
                r.player.name,
                f"{r.player.projected_points:.1f}",
                f"{r.vor:+.1f}",
            )
    return table


def render_recent_picks(picks, limit: int = 8) -> Table:
    table = Table(title="Recent Picks")
    table.add_column("#", justify="right")
    table.add_column("Team")
    table.add_column("Player")

    for p in picks[-limit:][::-1]:
        table.add_row(str(p.pick_number), p.team_name, p.player_name)
    return table


def render_my_picks(picks, my_team_name: str) -> Table:
    mine = espn_client.my_picks(picks, my_team_name)
    table = Table(title=f"My Roster So Far ({my_team_name})")
    table.add_column("Round", justify="right")
    table.add_column("Player")
    for p in mine:
        table.add_row(str(p.round_num), p.player_name)
    return table


def main():
    parser = argparse.ArgumentParser(description="Live ESPN fantasy draft best-available assistant")
    parser.add_argument("--once", action="store_true", help="print a single snapshot and exit")
    args = parser.parse_args()

    console = Console()
    cfg = load_config()

    console.print("Connecting to ESPN...")
    league = espn_client.connect(cfg)

    position_slot_counts = league.settings.position_slot_counts
    team_count = league.settings.team_count
    roster_size = sum(position_slot_counts.values())

    console.print("Pulling player pool and projections (this can take a few seconds)...")
    pool = espn_client.fetch_player_pool(league)
    console.print(f"Loaded {len(pool)} draftable players.")

    my_pick_numbers = snake_pick_numbers(cfg.my_draft_position, team_count, roster_size)
    positions = ["QB", "RB", "WR", "TE", "D/ST"]

    def build_view():
        picks = espn_client.refresh_draft_picks(league)
        drafted = espn_client.drafted_player_ids(picks)
        available = [p for p in pool.values() if p.player_id not in drafted]
        ranked = rank_available_players(available, position_slot_counts, team_count)

        return Group(
            render_header(console.width, picks, my_pick_numbers),
            render_top_table(ranked, cfg.top_n),
            render_position_table(ranked, positions),
            render_recent_picks(picks),
            render_my_picks(picks, cfg.my_team_name),
        )

    if args.once:
        console.print(build_view())
        return

    try:
        with Live(build_view(), console=console, refresh_per_second=1, screen=False) as live:
            while True:
                time.sleep(cfg.poll_interval_seconds)
                live.update(build_view())
    except KeyboardInterrupt:
        console.print("\nStopped.")


if __name__ == "__main__":
    main()
