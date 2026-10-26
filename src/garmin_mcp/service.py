"""What each tool fetches from Garmin and how it is put together.

Every function takes a logged-in ``garminconnect.Garmin`` (or a stand-in in
tests) and returns plain JSON-able data.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date
from typing import Any

from . import transform as T
from . import workouts as W
from .dates import each_day

# Errors that mean "stop and tell the user", not "this one section failed".
_FATAL_NAMES = {"GarminConnectAuthenticationError", "GarminConnectTooManyRequestsError"}


def _fatal(e: BaseException) -> bool:
    return type(e).__name__ in _FATAL_NAMES or any(c.__name__ in _FATAL_NAMES for c in type(e).__mro__)


def _section(fn: Callable[[], Any]) -> Any:
    """Run one part of a combined answer; a failure there should not hide the rest."""
    try:
        return fn()
    except Exception as e:
        if _fatal(e):
            raise
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}


def today(api: Any) -> date:
    """Garmin dates days in the profile's timezone, not the machine's."""
    fn = getattr(api, "today", None)
    return fn() if callable(fn) else date.today()


def today_summary(api: Any) -> dict[str, Any]:
    d = today(api).isoformat()
    return {
        "date": d,
        "readiness": _section(lambda: T.readiness(T.pick_morning(api.get_training_readiness(d)))),
        "readiness_now": _section(
            lambda: T.get(T.readiness(T.latest_entry(api.get_training_readiness(d))), "score")
        ),
        "hrv": _section(lambda: next(iter(T.hrv_rows(api.get_hrv_data(d))), None)),
        "sleep": _section(lambda: T.sleep(api.get_sleep_data(d))),
        "day": _section(lambda: T.day_stats(api.get_user_summary(d))),
        "training_status": _section(lambda: T.training_status(api.get_training_status(d))),
        "race_predictions": _section(lambda: T.race_predictions(api.get_race_predictions())),
        "activities_today": _section(
            lambda: [T.activity(a) for a in api.get_activities_by_date(d, d) or []]
        ),
    }


def readiness_range(api: Any, start: date, end: date) -> list[dict[str, Any]]:
    return T.readiness_by_day(api.get_training_readiness_range(start.isoformat(), end.isoformat()))


def hrv_range(api: Any, start: date, end: date) -> list[dict[str, Any]]:
    return T.hrv_rows(api.get_hrv_data_range(start.isoformat(), end.isoformat()))


def sleep_range(api: Any, start: date, end: date, pause: float = 0.0) -> list[dict[str, Any]]:
    rows = []
    for d in each_day(start, end):
        row = T.sleep(api.get_sleep_data(d.isoformat()))
        if row:
            row["date"] = row.get("date") or d.isoformat()
            rows.append(row)
        if pause:
            time.sleep(pause)
    return rows


def training_status_on(api: Any, day: date) -> dict[str, Any] | None:
    return T.training_status(api.get_training_status(day.isoformat()))


def performance(api: Any) -> dict[str, Any]:
    d = today(api)
    return {
        "date": d.isoformat(),
        "vo2max": _section(lambda: _vo2(api, d)),
        "lactate_threshold": _section(lambda: T.lactate_threshold(api.get_lactate_threshold(latest=True))),
        "race_predictions": _section(lambda: T.race_predictions(api.get_race_predictions())),
        "heat_acclimation_pct": _section(
            lambda: T.get(T.heat_acclimation(api.get_training_status(d.isoformat())), "heatAcclimationPercentage")
        ),
    }


def _vo2(api: Any, d: date) -> dict[str, Any] | None:
    raw = api.get_max_metrics(d.isoformat())
    entry = raw[0] if isinstance(raw, list) and raw else raw
    g = T.get(entry, "generic")
    if not g:
        # No new estimate today: fall back to the most recent one Garmin keeps.
        g = T.get(api.get_training_status(d.isoformat()), "mostRecentVO2Max", "generic")
    if not g:
        return None
    return {
        "value": T.rnd(g.get("vo2MaxPreciseValue") or g.get("vo2MaxValue"), 1),
        "date": g.get("calendarDate"),
        "fitness_age": g.get("fitnessAge"),
    }


def race_prediction_range(api: Any, start: date, end: date) -> list[dict[str, Any]]:
    return T.race_prediction_rows(api.get_race_predictions(start.isoformat(), end.isoformat(), "daily"))


def activities(api: Any, start: date, end: date, activity_type: str | None) -> list[dict[str, Any]]:
    raw = api.get_activities_by_date(start.isoformat(), end.isoformat(), activity_type or None, "asc")
    return [T.activity(a) for a in raw or [] if isinstance(a, dict)]


def activity_laps(api: Any, activity_id: str) -> dict[str, Any]:
    def summary() -> dict[str, Any]:
        raw = api.get_activity(activity_id) or {}
        # get_activity keeps the numbers under summaryDTO and the type under
        # activityTypeDTO; flatten so it reads like a get_activities row.
        flat = {**raw, **(raw.get("summaryDTO") or {})}
        if "activityType" not in flat and raw.get("activityTypeDTO"):
            flat["activityType"] = raw["activityTypeDTO"]
        return T.activity(flat)

    return {"summary": _section(summary), "laps": T.laps(api.get_activity_splits(activity_id))}


def daily_rows(api: Any, start: date, end: date, pause: float = 0.0) -> list[dict[str, Any]]:
    """One row per day. Range endpoints where Garmin has them, per-day calls otherwise."""
    s, e = start.isoformat(), end.isoformat()
    ready = {r["date"]: r for r in _section(lambda: readiness_range(api, start, end)) or [] if isinstance(r, dict) and r.get("date")}
    hrv = {r["date"]: r for r in _section(lambda: hrv_range(api, start, end)) or [] if isinstance(r, dict) and r.get("date")}
    # Day stats come from get_user_summary per day: the range endpoint
    # (get_daily_summaries) leaves resting HR and Body Battery empty.
    stats: dict[str, Any] = {}
    race =_section(lambda: T.race_seconds_by_day(api.get_race_predictions(s, e, "daily")))
    race = race if isinstance(race, dict) and "error" not in race else {}
    vo2 = _section(lambda: T.vo2max_by_day(api.get_max_metrics_range(s, e)))
    vo2 = vo2 if isinstance(vo2, dict) and "error" not in vo2 else {}
    rows = []
    for d in each_day(start, end):
        k = d.isoformat()
        slp = _section(lambda: T.sleep(api.get_sleep_data(k)))
        status = _section(lambda: T.training_status(api.get_training_status(k)))
        if k not in stats:
            stats[k] = _section(lambda: T.day_stats(api.get_user_summary(k)))
        rows.append(
            T.daily_row(
                k,
                ready.get(k),
                hrv.get(k),
                slp if isinstance(slp, dict) and "error" not in slp else None,
                stats.get(k) if isinstance(stats.get(k), dict) and "error" not in stats[k] else None,
                status if isinstance(status, dict) and "error" not in status else None,
                race.get(k),
                vo2.get(k),
            )
        )
        if pause:
            time.sleep(pause)
    return rows


def run_rows(api: Any, start: date, end: date) -> list[dict[str, Any]]:
    """Garmin runs (all running sub-types) as flat rows, oldest first."""
    raw = api.get_activities_by_date(start.isoformat(), end.isoformat(), "running", "asc")
    return [T.run_row(a) for a in raw or [] if isinstance(a, dict)]


# ---- workouts: the only calls that change anything in Garmin Connect ----------


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def scheduled_workouts(api: Any, start: date, end: date) -> list[dict[str, Any]]:
    """Workouts on the Garmin calendar between two days (from the calendar service)."""
    s, e = start.isoformat(), end.isoformat()
    rows = []
    for y, m in _months(start, end):
        cal = api.get_scheduled_workouts(y, m) or {}
        for item in cal.get("calendarItems") or []:
            d = item.get("date") or ""
            if item.get("itemType") == "workout" and s <= d <= e:
                rows.append(
                    {
                        "date": d,
                        "schedule_id": item.get("id"),
                        "workout_id": item.get("workoutId"),
                        "name": item.get("title"),
                    }
                )
    return sorted(rows, key=lambda r: (r["date"], r["name"] or ""))


def _schedule_id(resp: Any) -> Any:
    if not isinstance(resp, dict):
        return None
    return resp.get("workoutScheduleId") or resp.get("scheduleId") or resp.get("id")


def create_workout(
    api: Any,
    name: str,
    steps: Any,
    day: date | None = None,
    description: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upload a running workout and, with a day, put it on the calendar.

    A workout with the same name already on that day is left alone, so running
    the same plan twice does not create duplicates.
    """
    items = W.parse_items(steps)
    payload = W.build(name, items, description)
    sec, dist = W.estimate(items)
    out: dict[str, Any] = {
        "name": payload["workoutName"],
        "date": day.isoformat() if day else None,
        "steps": W.describe(payload),
        "estimated": {"minutes": round(sec / 60), "km": round(dist / 1000, 1)},
    }
    if dry_run:
        return {**out, "dry_run": True}
    if day:
        same = [r for r in scheduled_workouts(api, day, day) if (r["name"] or "").strip() == payload["workoutName"]]
        if same:
            return {**out, "skipped": "a workout with this name is already on the calendar that day", "existing": same[0]}
    created = api.upload_workout(payload) or {}
    workout_id = created.get("workoutId") if isinstance(created, dict) else None
    if not workout_id:
        raise ValueError("Garmin accepted the workout but returned no workout id")
    out["workout_id"] = workout_id
    if day:
        try:
            resp = api.schedule_workout(workout_id, day.isoformat())
        except Exception as e:
            if _fatal(e):
                raise
            out["schedule_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            return out
        out["schedule_id"] = _schedule_id(resp)
    return out


def _brief(w: dict[str, Any]) -> dict[str, Any]:
    return {
        "workout_id": w.get("workoutId"),
        "name": w.get("workoutName"),
        "sport": T.get(w, "sportType", "sportTypeKey"),
        "created": w.get("createdDate"),
        "updated": w.get("updatedDate"),
        "estimated_minutes": round(w["estimatedDurationInSecs"] / 60) if w.get("estimatedDurationInSecs") else None,
        "by_garmin_mcp": W.is_ours(w) if "description" in w else None,
    }


def list_workouts(api: Any, limit: int = 30) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200:
        raise ValueError("limit must be 1-200")
    return [_brief(w) for w in api.get_workouts(0, limit) or [] if isinstance(w, dict)]


def show_workout(api: Any, workout_id: str) -> dict[str, Any]:
    w = api.get_workout_by_id(workout_id) or {}
    return {**_brief(w), "description": w.get("description"), "steps": W.describe(w)}


def move_scheduled(api: Any, schedule_id: str, day: date) -> dict[str, Any]:
    """Schedule the same workout on the new day, then take it off the old one."""
    cur = api.get_scheduled_workout_by_id(schedule_id) or {}
    workout_id = T.get(cur, "workout", "workoutId") or cur.get("workoutId")
    if not workout_id:
        raise ValueError(f"No scheduled workout with id {schedule_id}")
    resp = api.schedule_workout(workout_id, day.isoformat())
    api.unschedule_workout(schedule_id)
    return {
        "workout_id": workout_id,
        "from": cur.get("calendarDate") or cur.get("date"),
        "to": day.isoformat(),
        "schedule_id": _schedule_id(resp),
    }


def unschedule(api: Any, schedule_id: str) -> dict[str, Any]:
    api.unschedule_workout(schedule_id)
    return {"unscheduled": schedule_id}


def delete_workout(api: Any, workout_id: str) -> dict[str, Any]:
    """Delete a workout template, but only one this server created."""
    w = api.get_workout_by_id(workout_id) or {}
    if not W.is_ours(w):
        raise ValueError(
            f"Workout {workout_id} ({w.get('workoutName') or 'unknown'}) was not created by garmin-mcp, "
            "so it is left alone. Delete it in the Garmin Connect app if you really want it gone."
        )
    api.delete_workout(workout_id)
    return {"deleted": workout_id, "name": w.get("workoutName")}


# Read-only methods the debug tool may call, with the arguments each takes.
RAW_METHODS: dict[str, tuple[str, ...]] = {
    "get_training_readiness": ("date",),
    "get_training_readiness_range": ("start_date", "end_date"),
    "get_training_status": ("date",),
    "get_weekly_training_status": ("start_date", "end_date"),
    "get_hrv_data": ("date",),
    "get_hrv_data_range": ("start_date", "end_date"),
    "get_sleep_data": ("date",),
    "get_user_summary": ("date",),
    "get_daily_summaries": ("start_date", "end_date"),
    "get_body_battery": ("start_date", "end_date"),
    "get_max_metrics": ("date",),
    "get_race_predictions": (),
    "get_lactate_threshold": (),
    "get_endurance_score": ("start_date", "end_date"),
    "get_hill_score": ("start_date", "end_date"),
    "get_running_tolerance": ("start_date", "end_date"),
    "get_heat_altitude_acclimation": ("date",),
    "get_activity": ("activity_id",),
    "get_activity_splits": ("activity_id",),
    "get_activities_by_date": ("start_date", "end_date"),
    "get_devices": (),
}


def raw(api: Any, method: str, args: dict[str, str | None]) -> Any:
    if method not in RAW_METHODS:
        raise ValueError(f"Unknown method {method!r}. Allowed: {', '.join(sorted(RAW_METHODS))}")
    params = RAW_METHODS[method]
    missing = [p for p in params if not args.get(p)]
    if missing:
        raise ValueError(f"{method} needs: {', '.join(missing)}")
    values = [args[p] for p in params]
    if method == "get_lactate_threshold":
        return getattr(api, method)(latest=True)
    return _prune(getattr(api, method)(*values))


def _prune(x: Any, depth: int = 0) -> Any:
    """Keep debug output readable: cut long arrays (HR/stress samples) short."""
    if isinstance(x, list):
        items = [_prune(v, depth + 1) for v in x[:20]]
        if len(x) > 20:
            items.append(f"... {len(x) - 20} more")
        return items
    if isinstance(x, dict):
        return {k: _prune(v, depth + 1) for k, v in x.items()}
    return x
