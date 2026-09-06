# fantasy-draft-picker

Live best-available assistant for a private ESPN fantasy football draft.
Polls your league's draft room and ranks remaining players by Value Over
Replacement (VOR), tuned for this league's specific roster shape - notably
the `OP` superflex slot, which is treated as a second QB slot (see
`draft_picker/vor.py` for why).

## Setup

```
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

- `ESPN_LEAGUE_ID` / `ESPN_YEAR` - already set for this league (1023983259 / 2026).
- `MY_TEAM_NAME` - already set to "Nic's Nifty Team".
- `MY_DRAFT_POSITION` - already set to 6 (your snake draft slot).
- `ESPN_SWID` / `ESPN_S2` - required for a private league. Grab these from your browser:
  1. Log into ESPN Fantasy in Chrome/Firefox and open your league.
  2. Open DevTools (F12) → Application (Chrome) or Storage (Firefox) tab → Cookies → `https://fantasy.espn.com`.
  3. Copy the value of `SWID` (looks like `{ABC123-...}`, keep the curly braces) into `ESPN_SWID`.
  4. Copy the value of `espn_s2` (a long encoded string) into `ESPN_S2`.
  5. Never commit `.env` - it's already gitignored.

## Usage

```
python -m draft_picker.cli          # live, refreshes every POLL_INTERVAL_SECONDS
python -m draft_picker.cli --once   # single snapshot, no polling loop
python -m draft_picker.cli --manual # hand-enter picks - see "Manual tracking" below
```

Ctrl+C to stop.

### Manual tracking (use this for your live draft)

ESPN's `mDraftDetail` endpoint does not reflect picks live even with
cache-busting - confirmed live, it still returned stale/placeholder
(`playerId -1`) data mid-draft. There is currently no working API-based way
to know "who's been drafted" during an in-progress draft, so `--manual`
sidesteps it entirely: real player pool/projections/settings are still
pulled from ESPN (that part works fine, it's a one-time pre-draft fetch),
but you watch the real ESPN draft screen and type each pick in yourself as
it happens - yours and everyone else's.

```
python -m draft_picker.cli --manual
```

At each prompt, type part of a player's name to record that pick, `undo` to
remove the last entry (typo recovery), or `quit` to stop. Multiple name
matches show a disambiguation list instead of silently guessing.

### Testing against a practice/mock draft

ESPN's "practice draft" feature creates a real league object with its own
league ID (visible in the URL, e.g.
`.../draft?leagueId=1133703302&seasonId=2026&teamId=1&...`) - same API as
a real league, so no code changes needed. Override the config for a single
run instead of editing `.env` back and forth:

```
python -m draft_picker.cli --once --league-id 1133703302 --team-name "Team 1" --draft-position 1
```

`--year`, `--team-name`, and `--draft-position` are also available if the
practice league's season/team/slot differ from your real one. Drop the
flags entirely to fall back to whatever's in `.env` - i.e. your real draft.

## What it shows

- **Draft status** - current pick number, and how many picks until you're on the clock (computed from your fixed snake slot).
- **Best available (top N by VOR)** - overall ranking.
- **Best available by position** - top 5 per position.
- **Recent picks** - last 8 picks made league-wide.
- **My roster so far** - what you've drafted, pulled straight from the live pick log.

## How the ranking works

1. Pulls the full draftable player pool once at startup via `league.free_agents()`, which includes ESPN's own `projected_total_points` - already computed under this league's exact scoring rules (half-PPR, etc.), so no manual point-value math needed.
2. Each poll, re-fetches the draft log, removes drafted players from the pool, and recomputes a replacement baseline per position from what's *still available* - so the baseline rises as a position gets drafted out, same as live VBD.
3. `VOR = player's projected points - replacement baseline for their position`. Ranks are sorted by VOR, not raw points, so a scarce position isn't buried under generically-higher-scoring ones.

### The superflex assumption

This league's `OP` slot lets any offensive player start there, but in
practice a second startable QB almost always beats a second flex-quality
RB/WR/TE under standard per-game scoring. So the replacement-level math
treats `OP` as a second QB slot outright, and splits the single `FLEX`
slot 40% RB / 40% WR / 20% TE (typical redraft flex usage). This is a
tunable heuristic, not solved optimization - adjust `FLEX_SHARE` /
`OP_SHARE` in `draft_picker/vor.py` if you disagree.

## Known limitations (v1, built same-day as the draft)

- No FantasyPros/consensus rankings blend yet - this runs entirely on
  ESPN's own projections. Good enough for one draft night; swap in
  another source later if ESPN's projections annoy you mid-draft.
- No "handcuff" or bye-week awareness.
- No working live pick source via the API at all (not just a polling lag) -
  `mDraftDetail` doesn't reflect picks mid-draft even with cache-busting.
  Use `--manual` for a real draft; the plain polling mode's picks list will
  stay stale/empty until ESPN marks the whole draft complete.
- "On the clock" only tracks *your* turn precisely (from your fixed snake
  slot); it doesn't name which other team is picking right now.
