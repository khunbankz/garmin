"""Write one row per day (same fields as the get_daily tool) to a JSON file.

    uv run garmin-mcp-export --start 2026-10-20 --out exports/garmin-daily.json

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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="garmin-mcp-export", description=__doc__.splitlines()[0])
    parser.add_argument("--start", help="first day YYYY-MM-DD (default: 30 days before --end)")
    parser.add_argument("--end", help="last day YYYY-MM-DD (default: today)")
    parser.add_argument("--out", default="exports/garmin-daily.json")
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
    except (GarminMcpError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} days ({start} → {end}) to {out}")


if __name__ == "__main__":
    main()
