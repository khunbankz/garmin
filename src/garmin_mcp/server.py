"""MCP server (stdio). Claude Desktop starts it; every tool is read-only."""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import service
from .config import load_config
from .dates import resolve_range
from .errors import GarminMcpError
from .session import GarminSession

INSTRUCTIONS = """\
Read-only access to the user's own Garmin Connect data: Training Readiness,
HRV status, sleep, Body Battery, training status and load (acute/chronic,
ACWR, load focus), VO2 max, lactate threshold, race predictor, and per-activity
running dynamics (cadence, stride, ground contact time, vertical oscillation),
power and training effect. Dates are local calendar days (YYYY-MM-DD),
inclusive. Start with get_today when reviewing training or deciding today's
session. Paces are min:sec per km.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True)

mcp = MCPServer(name="garmin", instructions=INSTRUCTIONS)
_session: GarminSession | None = None


def session() -> GarminSession:
    global _session
    if _session is None:
        _session = GarminSession(load_config())
    return _session


def _run(fn: Any) -> Any:
    """Expected failures reach Claude as a readable message (ToolError); anything
    else is a crash whose text stays in the server log."""
    try:
        return session().call(fn)
    except (GarminMcpError, ValueError) as e:
        raise ToolError(str(e)) from e
    except Exception as e:
        if type(e).__module__.startswith("garminconnect"):
            raise ToolError(f"Garmin returned an error: {str(e)[:300]}") from e
        raise


def _range(api: Any, start: str | None, end: str | None, default_days: int = 7):
    return resolve_range(start, end, service.today(api), default_days=default_days)


@mcp.tool(annotations=READ_ONLY)
def get_today() -> dict[str, Any]:
    """Today's morning Training Readiness (score, level, factors), last night's HRV
    and sleep, resting HR and Body Battery, training status and load, race
    predictions, and today's activities. Use this first when reviewing a run or
    deciding today's training."""
    return _run(service.today_summary)


@mcp.tool(annotations=READ_ONLY)
def get_readiness(start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
    """Morning Training Readiness per day: score (0-100), level, recovery time,
    acute load, and the factor breakdown (sleep, recovery time, acute load, HRV,
    stress history, sleep history). Default last 7 days, max 31."""
    return _run(lambda api: service.readiness_range(api, *_range(api, start_date, end_date)))


@mcp.tool(annotations=READ_ONLY)
def get_hrv(start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
    """Garmin HRV status per night: last-night average and 5-min high (ms), 7-day
    average, status (balanced/unbalanced/low/poor) and the balanced baseline
    range. Default last 7 days, max 31."""
    return _run(lambda api: service.hrv_range(api, *_range(api, start_date, end_date)))


@mcp.tool(annotations=READ_ONLY)
def get_sleep(start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
    """Garmin sleep per night (dated by the wake-up day): sleep score, bed/wake
    time, hours asleep, deep/light/REM/awake, overnight HRV, resting HR, Body
    Battery change, respiration. Default last 7 days, max 31."""
    return _run(lambda api: service.sleep_range(api, *_range(api, start_date, end_date)))


@mcp.tool(annotations=READ_ONLY)
def get_training_status(date: str | None = None) -> dict[str, Any] | None:
    """Training status on a day (default today): status (productive,
    maintaining, peaking, overreaching, unproductive, detraining, recovery),
    7-day load and its target range, acute and chronic load, ACWR, load focus
    (low aerobic / high aerobic / anaerobic vs targets), VO2 max, heat
    acclimation."""

    def fn(api: Any) -> Any:
        day = resolve_range(date, date, service.today(api), default_days=1)[0]
        return service.training_status_on(api, day)

    return _run(fn)


@mcp.tool(annotations=READ_ONLY)
def get_performance() -> dict[str, Any]:
    """Latest running VO2 max, lactate threshold (heart rate and pace), race
    predictor times for 5K/10K/half/marathon, and heat acclimation."""
    return _run(service.performance)


@mcp.tool(annotations=READ_ONLY)
def get_race_predictions(start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
    """Garmin race predictor per day (5K, 10K, half, marathon times and paces)
    to see the trend. Default last 31 days, max 31."""
    return _run(
        lambda api: service.race_prediction_range(api, *_range(api, start_date, end_date, default_days=31))
    )


@mcp.tool(annotations=READ_ONLY)
def get_activities(
    start_date: str | None = None,
    end_date: str | None = None,
    activity_type: str | None = "running",
) -> list[dict[str, Any]]:
    """Activities with Garmin-only metrics: distance, moving time, pace and
    grade-adjusted pace, HR, cadence, stride length, ground contact time,
    vertical oscillation and ratio, power, aerobic/anaerobic training effect,
    training load, temperature, Body Battery change, minutes per HR zone.
    activity_type: running (default), cycling, swimming, walking, hiking, other,
    or empty for all. Default last 7 days, max 31."""
    return _run(
        lambda api: service.activities(api, *_range(api, start_date, end_date), activity_type or None)
    )


@mcp.tool(annotations=READ_ONLY)
def get_activity_laps(activity_id: str) -> dict[str, Any]:
    """One activity's summary plus every lap (the laps you pressed or the steps of
    a structured workout): intensity (warmup/active/rest/cooldown), distance,
    time, pace, grade-adjusted pace, HR, cadence, stride, ground contact,
    vertical oscillation and ratio, power. Get the id from get_activities."""
    return _run(lambda api: service.activity_laps(api, str(activity_id)))


@mcp.tool(annotations=READ_ONLY)
def get_daily(start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
    """One compact row per day for trends: readiness, HRV and status, sleep score
    and hours, bed/wake, resting HR, Body Battery, stress, training status,
    acute/chronic load, ACWR, VO2 max. Default last 7 days, max 31."""
    return _run(lambda api: service.daily_rows(api, *_range(api, start_date, end_date)))


RAW_DESCRIPTION = (
    "Debugging: the unprocessed Garmin response of one read-only call (long arrays "
    "cut to 20 items). Use only when a field is missing from the other tools. "
    "Pass the arguments the method needs (date, start_date/end_date or activity_id). "
    "Allowed methods: " + ", ".join(sorted(service.RAW_METHODS))
)


@mcp.tool(description=RAW_DESCRIPTION, annotations=READ_ONLY)
def get_raw(
    method: str,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    activity_id: str | None = None,
) -> Any:
    args = {"date": date, "start_date": start_date, "end_date": end_date, "activity_id": activity_id}
    return _run(lambda api: service.raw(api, method, args))


def main() -> None:
    # stdout is the MCP channel; logs go to stderr (Claude Desktop shows them).
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
