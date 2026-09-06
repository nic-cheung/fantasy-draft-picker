import argparse
import sys
import time
from collections import Counter
from typing import Dict, List

from espn_api.requests.espn_requests import ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from . import espn_client
from .config import load_config
from .vor import RankedPlayer, rank_available_players, roster_needs

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


def slot_for_pick_number(pick_number: int, team_count: int) -> int:
    round_num = (pick_number - 1) // team_count + 1
    position_in_round = (pick_number - 1) % team_count + 1
    if round_num % 2 == 1:
        return position_in_round
    return team_count - position_in_round + 1


def my_position_counts(picks, my_team_name: str, pool) -> Counter:
    counts = Counter()
    for p in espn_client.my_picks(picks, my_team_name):
        player = pool.get(p.player_id)
        if player:
            counts[player.position] += 1
    return counts


def render_header(console_width: int, picks, my_pick_numbers: List[int], needs: Dict[str, int]) -> Panel:
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

    still_needed = [f"{pos}×{count}" for pos, count in needs.items() if count > 0]
    needs_text = "Still need: " + ", ".join(still_needed) if still_needed else "Starting lineup needs: all filled"

    text = f"Pick #{next_pick_number} on the clock  |  {turn_text}\n{needs_text}"
    return Panel(text, title="Draft Status")


def render_top_table(ranked: List[RankedPlayer], top_n: int, needs: Dict[str, int]) -> Table:
    table = Table(title=f"Best Available (Top {top_n} by VOR)")
    table.add_column("#", justify="right")
    table.add_column("Player")
    table.add_column("Pos")
    table.add_column("Team")
    table.add_column("Proj Pts", justify="right")
    table.add_column("VOR", justify="right")
    table.add_column("Need")
    table.add_column("Injury")

    for i, r in enumerate(ranked[:top_n], start=1):
        injury = INJURY_FLAG.get(r.player.injury_status, "")
        need = "[green]NEED[/green]" if needs.get(r.player.position, 0) > 0 else ""
        table.add_row(
            str(i),
            r.player.name,
            r.player.position,
            r.player.pro_team,
            f"{r.player.projected_points:.1f}",
            f"{r.vor:+.1f}",
            need,
            f"[red]{injury}[/red]" if injury else "",
        )
    return table


def render_position_table(ranked: List[RankedPlayer], positions: List[str], needs: Dict[str, int], per_pos: int = 5) -> Table:
    table = Table(title="Best Available by Position")
    table.add_column("Pos")
    table.add_column("Player")
    table.add_column("Proj Pts", justify="right")
    table.add_column("VOR", justify="right")

    for pos in positions:
        pos_players = [r for r in ranked if r.player.position == pos][:per_pos]
        pos_label = f"{pos} [green](need)[/green]" if needs.get(pos, 0) > 0 else pos
        for j, r in enumerate(pos_players):
            table.add_row(
                pos_label if j == 0 else "",
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


def _run_simulation(console: Console, cfg, league, pool, position_slot_counts, team_count, roster_size, my_pick_numbers, positions):
    """Local, in-memory mock draft.

    Doesn't touch ESPN's draft state at all - real settings/projections come
    from your actual league, but picks are typed in here and never sent
    anywhere. Good for rehearsing scenarios (e.g. "what if 3 QBs go in the
    first 5 picks") before the real thing.
    """
    sim_picks = []
    drafted_ids = set()

    console.print(
        "\n[bold]Simulation mode[/bold] - nothing here touches your real league's draft.\n"
        "At each prompt: type part of a player's name to draft them, 'top' to auto-pick "
        "the current best-available player, or 'quit' to stop.\n"
    )

    total_picks = roster_size * team_count
    while len(sim_picks) < total_picks:
        available = [p for p in pool.values() if p.player_id not in drafted_ids]
        ranked = rank_available_players(available, position_slot_counts, team_count)
        needs = roster_needs(my_position_counts(sim_picks, cfg.my_team_name, pool), position_slot_counts)

        console.print(
            Group(
                render_header(console.width, sim_picks, my_pick_numbers, needs),
                render_top_table(ranked, cfg.top_n, needs),
                render_position_table(ranked, positions, needs),
                render_recent_picks(sim_picks),
                render_my_picks(sim_picks, cfg.my_team_name),
            )
        )

        pick_number = len(sim_picks) + 1
        slot = slot_for_pick_number(pick_number, team_count)
        team_name = cfg.my_team_name if slot == cfg.my_draft_position else f"Team {slot}"

        query = console.input(f"\n[Pick #{pick_number}] {team_name} on the clock > ").strip()
        if query.lower() in ("quit", "q", "exit"):
            break

        if query.lower() == "top":
            chosen = ranked[0].player
        else:
            matches = [p for p in available if query.lower() in p.name.lower()]
            if not matches:
                console.print(f"[red]No available player matches '{query}' - try again.[/red]\n")
                continue
            chosen = matches[0]

        drafted_ids.add(chosen.player_id)
        sim_picks.append(
            espn_client.PickRow(
                pick_number=pick_number,
                round_num=(pick_number - 1) // team_count + 1,
                round_pick=slot,
                team_name=team_name,
                player_name=chosen.name,
                player_id=chosen.player_id,
            )
        )
        console.clear()

    console.print("\nSimulation ended.")


def _find_matches(query: str, available) -> list:
    """Bidirectional containment match: works for a short typed fragment
    ("mccaffrey") AND a full noisy line copied straight out of ESPN's Pick
    History panel ("Rd 3, Pick 6 - Team Bob - Christian McCaffrey RB SF"),
    since in the second case the player's full name is a substring of the
    query rather than the other way round."""
    query = query.lower().strip()
    if not query:
        return []
    return [p for p in available if query in p.name.lower() or p.name.lower() in query]


def _run_manual_tracking(console: Console, cfg, position_slot_counts, team_count, roster_size, my_pick_numbers, positions, pool):
    """Track a REAL live draft by hand-entering each pick as it happens.

    ESPN's mDraftDetail endpoint doesn't reflect picks live even with
    cache-busting (confirmed live, both the plain and cache-busted requests
    still returned stale/placeholder data mid-draft) - so there's no working
    API-based path to "who's been drafted" during an in-progress draft.
    This sidesteps ESPN's draft endpoint entirely: real pool/projections/
    settings (all fetched once, pre-draft, which does work), but pick data
    comes from you watching the real draft screen and typing each pick in.
    """
    picks: List = []
    drafted_ids = set()

    console.print(
        "\n[bold]Manual live tracking[/bold] - nothing is read from or sent to ESPN's draft "
        "endpoint. Watch the real draft screen and enter each pick (yours and everyone "
        "else's) as it happens.\n"
        "At each prompt: type part of a player's name to record that pick, 'paste' to enter "
        "several picks at once (e.g. copied from ESPN's Pick History panel, oldest pick "
        "first), 'undo' to remove the last entry (typo recovery), or 'quit' to stop.\n"
    )

    total_picks = roster_size * team_count
    while len(picks) < total_picks:
        available = [p for p in pool.values() if p.player_id not in drafted_ids]
        ranked = rank_available_players(available, position_slot_counts, team_count)
        needs = roster_needs(my_position_counts(picks, cfg.my_team_name, pool), position_slot_counts)

        console.clear()
        console.print(
            Group(
                render_header(console.width, picks, my_pick_numbers, needs),
                render_top_table(ranked, cfg.top_n, needs),
                render_position_table(ranked, positions, needs),
                render_recent_picks(picks),
                render_my_picks(picks, cfg.my_team_name),
            )
        )

        pick_number = len(picks) + 1
        slot = slot_for_pick_number(pick_number, team_count)
        is_mine = slot == cfg.my_draft_position
        team_name = cfg.my_team_name if is_mine else f"Team {slot}"
        on_clock = "[bold green]YOUR PICK[/bold green]" if is_mine else team_name

        query = console.input(f"\n[Pick #{pick_number}] {on_clock} just took > ").strip()
        if query.lower() in ("quit", "q", "exit"):
            break

        if query.lower() == "undo":
            if picks:
                removed = picks.pop()
                drafted_ids.discard(removed.player_id)
                console.print(f"[yellow]Removed pick #{removed.pick_number}: {removed.player_name}[/yellow]")
            else:
                console.print("[yellow]Nothing to undo.[/yellow]")
            console.input("Press Enter to continue...")
            continue

        if query.lower() == "paste":
            console.print(
                "[bold]Paste picks now, oldest pick first, one per line "
                "(a full Pick History row is fine, extra text is ignored).[/bold]\n"
                "Press Enter on an empty line when done."
            )
            pasted_lines = []
            while True:
                line = console.input("").strip()
                if not line:
                    break
                pasted_lines.append(line)

            applied = 0
            for line in pasted_lines:
                cur_available = [p for p in pool.values() if p.player_id not in drafted_ids]
                line_lower = line.lower()

                # Prefer a player whose FULL name literally appears in the line - the
                # expected case for a noisy Pick History row. Only fall back to a short
                # typed-fragment match (line is a substring of the name) when no full
                # name is present, so a bare fragment like "Josh" matching two different
                # full names (Allen vs Jacobs) is correctly flagged as ambiguous rather
                # than silently resolved by name length.
                name_in_line = [p for p in cur_available if p.name.lower() in line_lower]
                if len(name_in_line) == 1:
                    chosen = name_in_line[0]
                elif len(name_in_line) > 1:
                    # e.g. both "Michael Pittman" and "Michael Pittman Jr." appear in
                    # the line - the longer (more specific) one wins if it's unique.
                    name_in_line.sort(key=lambda p: len(p.name), reverse=True)
                    tied = [c for c in name_in_line if len(c.name) == len(name_in_line[0].name)]
                    if len(tied) > 1:
                        console.print(f"[red]Stopped at line {applied + 1}: '{line}' matches multiple players:[/red]")
                        for c in name_in_line[:8]:
                            console.print(f"  {c.name} ({c.position}, {c.pro_team})")
                        break
                    chosen = name_in_line[0]
                else:
                    fragment_matches = [p for p in cur_available if line_lower and line_lower in p.name.lower()]
                    if not fragment_matches:
                        console.print(f"[red]Stopped at line {applied + 1}: no available player found in '{line}'.[/red]")
                        break
                    if len(fragment_matches) > 1:
                        console.print(f"[red]Stopped at line {applied + 1}: '{line}' matches multiple players:[/red]")
                        for c in fragment_matches[:8]:
                            console.print(f"  {c.name} ({c.position}, {c.pro_team})")
                        break
                    chosen = fragment_matches[0]

                cur_pick_number = len(picks) + 1
                cur_slot = slot_for_pick_number(cur_pick_number, team_count)
                cur_team_name = cfg.my_team_name if cur_slot == cfg.my_draft_position else f"Team {cur_slot}"
                drafted_ids.add(chosen.player_id)
                picks.append(
                    espn_client.PickRow(
                        pick_number=cur_pick_number,
                        round_num=(cur_pick_number - 1) // team_count + 1,
                        round_pick=cur_slot,
                        team_name=cur_team_name,
                        player_name=chosen.name,
                        player_id=chosen.player_id,
                    )
                )
                applied += 1

            console.print(f"[green]Applied {applied}/{len(pasted_lines)} pasted picks.[/green]")
            if applied < len(pasted_lines):
                console.print(
                    "[yellow]Fix the name above then re-paste starting from that line "
                    "(pick numbering picks up correctly), or enter it one by one.[/yellow]"
                )
            console.input("Press Enter to continue...")
            continue

        matches = _find_matches(query, available)
        if not matches:
            console.print(f"[red]No available player matches '{query}' - try again.[/red]")
            console.input("Press Enter to continue...")
            continue
        if len(matches) > 1:
            console.print(f"[yellow]Multiple matches for '{query}' - be more specific:[/yellow]")
            for m in matches[:8]:
                console.print(f"  {m.name} ({m.position}, {m.pro_team})")
            console.input("Press Enter to continue...")
            continue

        chosen = matches[0]
        drafted_ids.add(chosen.player_id)
        picks.append(
            espn_client.PickRow(
                pick_number=pick_number,
                round_num=(pick_number - 1) // team_count + 1,
                round_pick=slot,
                team_name=team_name,
                player_name=chosen.name,
                player_id=chosen.player_id,
            )
        )

    console.print("\nManual tracking ended.")


def main():
    parser = argparse.ArgumentParser(description="Live ESPN fantasy draft best-available assistant")
    parser.add_argument("--once", action="store_true", help="print a single snapshot and exit")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="rehearse with a local mock draft (real league settings/projections, fake picks - nothing is sent to ESPN)",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help=(
            "track a REAL live draft by hand-entering each pick (real pool/projections, "
            "no dependency on ESPN's draft endpoint - use this since live pick data via "
            "the API doesn't work)"
        ),
    )
    parser.add_argument(
        "--league-id",
        type=int,
        default=None,
        help="override ESPN_LEAGUE_ID from .env for this run only (e.g. to point at a practice/mock league)",
    )
    parser.add_argument("--year", type=int, default=None, help="override ESPN_YEAR for this run only")
    parser.add_argument("--team-name", type=str, default=None, help="override MY_TEAM_NAME for this run only")
    parser.add_argument(
        "--draft-position", type=int, default=None, help="override MY_DRAFT_POSITION for this run only"
    )
    args = parser.parse_args()

    console = Console()
    cfg = load_config()
    if args.league_id is not None:
        cfg.league_id = args.league_id
    if args.year is not None:
        cfg.year = args.year
    if args.team_name is not None:
        cfg.my_team_name = args.team_name
    if args.draft_position is not None:
        cfg.my_draft_position = args.draft_position

    console.print(f"Connecting to ESPN league {cfg.league_id} ({cfg.year})...")
    try:
        league = espn_client.connect(cfg)
    except ESPNInvalidLeague:
        console.print(
            f"[red]League {cfg.league_id} does not exist for {cfg.year}.[/red] "
            "Double check the league ID (and --year if you overrode it) - practice/mock "
            "draft URLs in particular often use an ID that isn't a real, queryable league."
        )
        sys.exit(1)
    except ESPNAccessDenied:
        console.print(
            f"[red]League {cfg.league_id} exists but can't be accessed with these credentials.[/red] "
            "Either it's private and your SWID/espn_s2 don't grant access to it (they need to belong "
            "to an account that's a member of that league), or the cookies have expired - re-grab them "
            "from your browser."
        )
        sys.exit(1)
    except ESPNUnknownError as e:
        console.print(f"[red]ESPN returned an unexpected error connecting to league {cfg.league_id}:[/red] {e}")
        sys.exit(1)

    position_slot_counts = league.settings.position_slot_counts
    team_count = league.settings.team_count
    roster_size = sum(position_slot_counts.values())

    console.print("Pulling player pool and projections (this can take a few seconds)...")
    pool = espn_client.fetch_player_pool(league)
    console.print(f"Loaded {len(pool)} draftable players.")

    my_pick_numbers = snake_pick_numbers(cfg.my_draft_position, team_count, roster_size)
    ordered_positions = ["QB", "RB", "WR", "TE", "D/ST", "K"]
    league_positions = espn_client.relevant_positions(position_slot_counts)
    positions = [p for p in ordered_positions if p in league_positions]

    if args.simulate:
        _run_simulation(console, cfg, league, pool, position_slot_counts, team_count, roster_size, my_pick_numbers, positions)
        return

    if args.manual:
        _run_manual_tracking(console, cfg, position_slot_counts, team_count, roster_size, my_pick_numbers, positions, pool)
        return

    def build_view():
        picks = espn_client.refresh_draft_picks(league)
        drafted = espn_client.drafted_player_ids(picks)
        available = [p for p in pool.values() if p.player_id not in drafted]
        ranked = rank_available_players(available, position_slot_counts, team_count)
        needs = roster_needs(my_position_counts(picks, cfg.my_team_name, pool), position_slot_counts)

        return Group(
            render_header(console.width, picks, my_pick_numbers, needs),
            render_top_table(ranked, cfg.top_n, needs),
            render_position_table(ranked, positions, needs),
            render_recent_picks(picks),
            render_my_picks(picks, cfg.my_team_name),
        )

    if args.once:
        console.print(build_view())
        return

    try:
        with Live(build_view(), console=console, refresh_per_second=1, screen=False) as live:
            consecutive_failures = 0
            while True:
                time.sleep(cfg.poll_interval_seconds)
                try:
                    new_view = build_view()
                    consecutive_failures = 0
                    live.update(new_view)
                except Exception as e:
                    # A single dropped ESPN request shouldn't kill the tool
                    # mid-draft - log it and keep polling instead of dying.
                    consecutive_failures += 1
                    live.console.print(
                        f"[yellow]Poll failed ({consecutive_failures}x in a row): {e} - "
                        f"retrying in {cfg.poll_interval_seconds}s[/yellow]"
                    )
    except KeyboardInterrupt:
        console.print("\nStopped.")


if __name__ == "__main__":
    main()
