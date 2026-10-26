"""Create running workouts in Garmin Connect and put them on the calendar.

    uv run garmin-mcp-workouts push plan.json [--dry-run] [--replace]
    uv run garmin-mcp-workouts scheduled [--start 2026-10-27] [--end 2026-11-22]
    uv run garmin-mcp-workouts list | show ID | move SCHEDULE_ID DATE
    uv run garmin-mcp-workouts unschedule SCHEDULE_ID | delete WORKOUT_ID

plan.json is a list of {"name", "date", "description"?, "steps"} with steps in
the same form as the create_workout tool. Every workout is checked before
anything is uploaded; one that is already on its day under the same name is
skipped, so pushing the same file twice is safe, or with --replace rewritten in
place (same calendar entry). delete and --replace only touch workouts this
tool created.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from . import service
from . import workouts as W
from .config import load_config
from .dates import parse_day
from .errors import GarminMcpError
from .session import GarminSession


def load_plan(path: str) -> list[dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    plan = raw.get("workouts") if isinstance(raw, dict) else raw
    if not isinstance(plan, list) or not plan:
        raise ValueError(f"{path} must hold a non-empty list of workouts")
    for i, w in enumerate(plan, 1):
        label = f"workout {i} ({w.get('name') if isinstance(w, dict) else '?'})"
        if not isinstance(w, dict) or not w.get("name") or "steps" not in w:
            raise ValueError(f"{label} needs a name and steps")
        try:
            if w.get("date"):
                parse_day(w["date"], "date")
            W.build(w["name"], W.parse_items(w["steps"]), w.get("description"))
        except ValueError as e:
            raise ValueError(f"{label}: {e}") from e
    return plan


def _push(sess: GarminSession, plan: list[dict[str, Any]], dry_run: bool, pause: float, replace: bool = False) -> int:
    failed = 0
    for i, w in enumerate(plan):
        day = parse_day(w["date"], "date") if w.get("date") else None
        res = sess.call(
            lambda api, w=w, day=day: service.create_workout(
                api, w["name"], w["steps"], day, w.get("description"), dry_run, replace
            )
        )
        head = f"{res['date'] or 'no date'}  {res['name']}  (~{res['estimated']['minutes']} min, {res['estimated']['km']} km)"
        if dry_run:
            print(f"· {head}")
        elif res.get("replaced"):
            print(f"↻ {head}: workout {res['workout_id']} updated in place")
        elif res.get("skipped"):
            print(f"= {head}: already on the calendar, skipped")
        elif res.get("schedule_error"):
            failed += 1
            print(f"! {head}: created as workout {res['workout_id']} but not scheduled: {res['schedule_error']}")
        else:
            sid = f", schedule {res['schedule_id']}" if res.get("schedule_id") else ""
            print(f"✓ {head}: workout {res['workout_id']}{sid}")
        for line in res["steps"]:
            print(f"      {line}")
        if not dry_run and pause and i < len(plan) - 1:
            time.sleep(pause)
    return failed


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="garmin-mcp-workouts", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push", help="create and schedule the workouts in a plan file")
    p.add_argument("plan")
    p.add_argument("--dry-run", action="store_true", help="check and print, upload nothing")
    p.add_argument("--pause", type=float, default=1.0, help="seconds between workouts")
    p.add_argument("--replace", action="store_true", help="rewrite workouts already on their day")
    p = sub.add_parser("scheduled", help="workouts on the calendar")
    p.add_argument("--start")
    p.add_argument("--end")
    p = sub.add_parser("list", help="workouts in the library")
    p.add_argument("--limit", type=int, default=30)
    sub.add_parser("show", help="one workout as Garmin stored it").add_argument("workout_id")
    p = sub.add_parser("move", help="move a scheduled workout to another day")
    p.add_argument("schedule_id")
    p.add_argument("date")
    sub.add_parser("unschedule", help="take a workout off the calendar").add_argument("schedule_id")
    sub.add_parser("delete", help="delete a workout this tool created").add_argument("workout_id")
    args = parser.parse_args(argv)

    try:
        plan = load_plan(args.plan) if args.cmd == "push" else None
        sess = GarminSession(load_config())
        if args.cmd == "push":
            failed = _push(sess, plan, args.dry_run, args.pause, args.replace)
            if failed:
                sys.exit(2)
            return
        if args.cmd == "scheduled":
            first = parse_day(args.start, "--start") if args.start else sess.call(service.today)
            last = parse_day(args.end, "--end") if args.end else first + timedelta(days=27)
            if first > last:
                raise ValueError("--start must not be after --end")
            for r in sess.call(lambda api: service.scheduled_workouts(api, first, last)):
                print(f"{r['date']}  {r['name']}  (workout {r['workout_id']}, schedule {r['schedule_id']})")
            return
        if args.cmd == "list":
            for r in sess.call(lambda api: service.list_workouts(api, args.limit)):
                mark = " [garmin-mcp]" if r["by_garmin_mcp"] else ""
                print(f"{r['workout_id']}  {r['name']}{mark}")
            return
        if args.cmd == "show":
            r = sess.call(lambda api: service.show_workout(api, args.workout_id))
            print(f"{r['workout_id']}  {r['name']}  (~{r['estimated_minutes']} min)")
            for line in r["steps"]:
                print(f"  {line}")
            return
        if args.cmd == "move":
            day = parse_day(args.date, "date")
            r = sess.call(lambda api: service.move_scheduled(api, args.schedule_id, day))
        elif args.cmd == "unschedule":
            r = sess.call(lambda api: service.unschedule(api, args.schedule_id))
        else:
            r = sess.call(lambda api: service.delete_workout(api, args.workout_id))
        print(json.dumps(r, ensure_ascii=False))
    except (GarminMcpError, ValueError, OSError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if not type(e).__module__.startswith("garminconnect"):
            raise
        print(f"Garmin returned an error: {str(e)[:300]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
