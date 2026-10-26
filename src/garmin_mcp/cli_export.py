"""Write one row per day (same fields as the get_daily tool) to a JSON file,
and optionally every Garmin run in the same span to a second file.

    uv run garmin-mcp-export --start 2026-10-25 --out exports/garmin-daily.json \
        --runs-out exports/garmin-runs.json

--end defaults to today (Garmin profile timezone). Days are fetched 31 at a
time with a short pause between per-day calls so Garmin does not rate limit.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

from . import service
from .config import load_config
from .dates import chunks, parse_day
from .errors import GarminMcpError
from .session import GarminSession


def _write(path: str, rows: list[dict]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="garmin-mcp-export", description=__doc__.splitlines()[0])
    parser.add_argument("--start", help="first day YYYY-MM-DD (default: 30 days before --end)")
    parser.add_argument("--end", help="last day YYYY-MM-DD (default: today)")
    parser.add_argument("--out", default="exports/garmin-daily.json")
    parser.add_argument("--runs-out", help="also write the Garmin runs in the span to this file")
    parser.add_argument("--pause", type=float, default=0.3, help="seconds between per-day calls")
    args = parser.parse_args(argv)

    sess = GarminSession(load_config())
    try:
        today = sess.call(service.today)
        end = parse_day(args.end, "--end") if args.end else today
        start = parse_day(args.start, "--start") if args.start else end - timedelta(days=29)
        if start > end:
            raise ValueError("--start must not be after --end")
        rows: list[dict] = []
        for a, b in chunks(start, end, 31):
            rows += sess.call(lambda api, a=a, b=b: service.daily_rows(api, a, b, pause=args.pause))
            print(f"  {a} → {b}", file=sys.stderr)
        runs = sess.call(lambda api: service.run_rows(api, start, end)) if args.runs_out else None
    except (GarminMcpError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    out = _write(args.out, rows)
    print(f"Wrote {len(rows)} days ({start} → {end}) to {out}")
    if runs is not None:
        rout = _write(args.runs_out, runs)
        print(f"Wrote {len(runs)} runs to {rout}")


if __name__ == "__main__":
    main()
