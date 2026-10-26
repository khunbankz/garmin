# garmin-mcp

A small local [MCP](https://modelcontextprotocol.io) server that gives Claude access to your own Garmin Connect data — the metrics Strava does not pass on: Training Readiness, HRV status, training status and load, VO2 max, lactate threshold, race predictor, Body Battery, sleep, and per-activity running dynamics, power and training effect. Everything is read-only except the workout tools, which put structured running workouts on your Garmin calendar so they sync to the watch.

It runs on your own Mac (Claude Desktop starts it over stdio). It uses the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) library, because Garmin's official API is only open to approved businesses. You log in once in your own Terminal; only the resulting tokens are saved, in `~/.garmin-mcp/` (mode 600). Your password is never stored.

> Unofficial means Garmin can change its login at any time and break it for a while (it happened in March 2026). The library usually catches up within days: `uv sync --upgrade` picks up the fix.

## Tools

| Tool | Returns |
|---|---|
| `get_today` | Morning Training Readiness (score, level, factors), last night's HRV and sleep, resting HR, Body Battery, training status and load, race predictions, today's activities |
| `get_readiness` | Per day: morning readiness score, level, recovery time, acute load, factor breakdown |
| `get_hrv` | Per night: last-night average and 5-min high, 7-day average, status, balanced baseline |
| `get_sleep` | Per night: sleep score, bed/wake, hours asleep and stages, overnight HRV, resting HR, Body Battery change |
| `get_training_status` | Status (productive, maintaining, …), 7-day load vs target, acute/chronic load, ACWR, load focus, VO2 max, heat acclimation |
| `get_performance` | Latest VO2 max, lactate threshold HR and pace, race predictor, heat acclimation |
| `get_race_predictions` | Race predictor per day (trend) |
| `get_activities` | Pace and grade-adjusted pace, HR, cadence, stride, ground contact, vertical oscillation/ratio, power, training effect and load, temperature, minutes per HR zone |
| `get_activity_laps` | One activity's summary plus every lap or workout step with the same metrics |
| `get_daily` | One compact row per day for trends |
| `get_raw` | Debugging: the unprocessed response of one whitelisted read call |
| `get_scheduled_workouts` | Workouts on the Garmin calendar (default the next 14 days) |
| `get_workouts` / `get_workout` | The workout library; one workout's steps and targets as Garmin stored them |
| `create_workout` ✏️ | Create a running workout from a short step list and put it on a day |
| `move_workout` ✏️ | Move a scheduled workout to another day |
| `unschedule_workout` ✏️ | Take a workout off the calendar (it stays in the library) |
| `delete_workout` ✏️ | Delete a workout — only ones this server created |

Range tools take optional `start_date` / `end_date` (`YYYY-MM-DD`, inclusive; default last 7 days, max 31). "Today" follows the timezone in your Garmin profile.

## Setup (about 5 minutes)

Requires [uv](https://docs.astral.sh/uv/) (`brew install uv`).

```bash
git clone https://github.com/khunbankz/garmin.git ~/Work/garmin-mcp
cd ~/Work/garmin-mcp
uv sync
uv run garmin-mcp-auth          # email, password (hidden), and the code Garmin sends if you use 2-step
uv run garmin-mcp-auth --status # should print "Connected as …"
```

Then Claude Desktop → **Settings → Developer → Edit Config**, add inside `mcpServers` (absolute path; Claude Desktop does not load your shell `PATH`):

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/Users/YOU/Work/garmin-mcp/.venv/bin/garmin-mcp"
    }
  }
}
```

Restart Claude Desktop and ask: *"What's my Garmin training readiness today?"*

## Export daily rows

```bash
uv run garmin-mcp-export --start 2026-10-25 --out exports/garmin-daily.json \
    --runs-out exports/garmin-runs.json   # --end defaults to today
```

Daily rows are the `get_daily` fields plus the race predictor (seconds), load focus with its target band, weekly load target and chronic-load range; fetched 31 days at a time with a short pause between per-day calls. `--runs-out` also writes every Garmin run in the span as flat numbers (distance, moving time, HR, cadence, stride, ground contact, power, Training Effect and load). `exports/` is git-ignored.

## Workouts

A workout is a list of steps and repeat blocks. A step ends after `distance_km` or `duration` (`m:ss`), or on the lap button if neither is given; `pace` (`"5:35-5:45"` per km) and `hr` (`"140-150"`) are the targets the watch alerts on (with both, HR is the secondary target). A repeat block skips its last recovery by default.

```json
[
  {"name": "Tempo 2x3k", "date": "2026-10-27", "description": "HR cap 168",
   "steps": [
     {"kind": "warmup", "distance_km": 2},
     {"repeat": 2, "steps": [
       {"kind": "run", "distance_km": 3, "pace": "5:35-5:45"},
       {"kind": "recovery", "duration": "2:00"}]},
     {"kind": "cooldown", "distance_km": 2}]}
]
```

```bash
uv run garmin-mcp-workouts push exports/plan.json --dry-run   # check and print only
uv run garmin-mcp-workouts push exports/plan.json             # create + schedule, then sync the watch
uv run garmin-mcp-workouts scheduled --start 2026-10-27       # what is on the calendar
uv run garmin-mcp-workouts show WORKOUT_ID                    # read a workout back from Garmin
```

Every workout in the file is checked before anything is uploaded. One that is already on its day under the same name is skipped, so pushing a file twice is safe. Each workout this tool creates gets `[garmin-mcp]` in its description; `delete` refuses anything without it.

## Troubleshooting

- **"Garmin is not connected yet" / "rejected the saved login"**: run `uv run garmin-mcp-auth` again.
- **"rate limiting"** (HTTP 429/427): wait 15–60 minutes. Do not retry logins in a loop.
- **Login suddenly fails for everyone**: Garmin changed something. `uv sync --upgrade`, then log in again.
- **Revoke access**: delete `~/.garmin-mcp/garmin_tokens.json`.

## How it works

- The server only reads the saved tokens; it never sees your password. The library refreshes the access token itself and saves the rotated tokens.
- The server and the export CLI may run at the same time, so every call holds a lock file in `~/.garmin-mcp/` and reloads the token file first if another process changed it. That way no one refreshes with an already-used refresh token.
- Combined answers (`get_today`, `get_performance`, `get_daily`) keep going when one part fails and show that part's error; a rejected login or a rate limit stops the call with a clear message.
- The only calls that change anything are the workout tools (create, schedule, move, unschedule, delete your own workouts); `get_raw` only allows a fixed list of read calls.

## Development

```bash
uv run pytest   # unit tests plus a stdio end-to-end test against a fake Garmin client
```

`GARMIN_MCP_HOME` moves the token folder. `GARMIN_MCP_FAKE=module:Class` swaps in a fake client (tests only).
