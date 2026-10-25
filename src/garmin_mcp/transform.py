"""Turn Garmin Connect JSON into small, readable rows.

Garmin's payloads are large and change with firmware, so every lookup here is
defensive: a missing field becomes ``None`` instead of an error. Units are
converted to what a runner reads: km, min:sec per km, hours, cm/ms for running
dynamics.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any


def get(d: Any, *path: Any) -> Any:
    """Nested lookup that returns None as soon as something is missing."""
    cur = d
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and -len(cur) <= key < len(cur):
            cur = cur[key]
        else:
            return None
        if cur is None:
            return None
    return cur


def rnd(x: Any, n: int = 1) -> float | int | None:
    if x is None:
        return None
    try:
        v = round(float(x), n)
    except (TypeError, ValueError):
        return None
    return int(v) if n == 0 else v


def hours(seconds: Any) -> float | None:
    return None if seconds is None else rnd(float(seconds) / 3600, 2)


def minutes(seconds: Any) -> float | None:
    return None if seconds is None else rnd(float(seconds) / 60, 1)


def hms(seconds: Any) -> str | None:
    """1:02:03 or 25:07."""
    if seconds is None:
        return None
    s = int(round(float(seconds)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def pace(speed_mps: Any) -> str | None:
    """m/s -> 'm:ss' per km."""
    try:
        v = float(speed_mps)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    sec = 1000 / v
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def local_clock(epoch_ms_local: Any) -> str | None:
    """Garmin's *TimestampLocal* epoch values are local wall time stored as UTC."""
    if epoch_ms_local is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch_ms_local) / 1000, tz=UTC).strftime("%H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def phrase(code: Any) -> str | None:
    """'PRODUCTIVE_3' -> 'productive', 'AEROBIC_HIGH_SHORTAGE' -> 'aerobic high shortage'."""
    if not code or not isinstance(code, str):
        return None
    return re.sub(r"_\d+$", "", code).replace("_", " ").lower()


def primary_device_entry(by_device: Any) -> dict[str, Any] | None:
    """Garmin keys some metrics by device id; prefer the primary training device."""
    if not isinstance(by_device, dict) or not by_device:
        return None
    entries = [v for v in by_device.values() if isinstance(v, dict)]
    if not entries:
        return None
    for e in entries:
        if e.get("primaryTrainingDevice"):
            return e
    return max(entries, key=lambda e: str(e.get("calendarDate") or ""))


# ---------------------------------------------------------------- readiness


def pick_morning(entries: Any) -> dict[str, Any] | None:
    """Training readiness is recalculated during the day; the morning one is the
    score computed right after waking (inputContext AFTER_WAKEUP_RESET)."""
    if isinstance(entries, dict):
        return entries
    if not isinstance(entries, list) or not entries:
        return None
    rows = [e for e in entries if isinstance(e, dict)]
    for e in rows:
        if e.get("inputContext") == "AFTER_WAKEUP_RESET":
            return e
    return min(rows, key=lambda e: str(e.get("timestampLocal") or e.get("timestamp") or ""), default=None)


def latest_entry(entries: Any) -> dict[str, Any] | None:
    if isinstance(entries, dict):
        return entries
    rows = [e for e in entries or [] if isinstance(e, dict)]
    return max(rows, key=lambda e: str(e.get("timestampLocal") or e.get("timestamp") or ""), default=None)


def readiness(e: dict[str, Any] | None) -> dict[str, Any] | None:
    if not e:
        return None

    def factor(prefix: str) -> dict[str, Any]:
        return {
            "pct": e.get(f"{prefix}FactorPercent"),
            "feedback": phrase(e.get(f"{prefix}FactorFeedback")),
        }

    if e.get("score") is None:
        # A new watch, or no valid sleep yet: Garmin sends an entry with
        # level NONE, zeroed factors and placeholder numbers.
        return {"date": e.get("calendarDate"), "score": None, "note": "not calculated yet"}
    recovery_min = e.get("recoveryTime")
    hrv_week = e.get("hrvWeeklyAverage")
    return {
        "date": e.get("calendarDate"),
        "time": (e.get("timestampLocal") or "")[11:16] or None,
        "score": e.get("score"),
        "level": phrase(e.get("level")),
        "feedback": phrase(e.get("feedbackShort")),
        "recovery_time_h": rnd(recovery_min / 60, 1) if isinstance(recovery_min, (int, float)) else None,
        "acute_load": e.get("acuteLoad"),
        # Seen as 511 on a watch without an HRV baseline yet; real RMSSD is far lower.
        "hrv_weekly_avg": hrv_week if isinstance(hrv_week, (int, float)) and 0 < hrv_week < 250 else None,
        "sleep_score": e.get("sleepScore"),
        "factors": {
            "sleep": factor("sleepScore"),
            "recovery_time": factor("recoveryTime"),
            "acute_load": factor("acwr"),
            "hrv": factor("hrv"),
            "stress_history": factor("stressHistory"),
            "sleep_history": factor("sleepHistory"),
        },
        "context": e.get("inputContext"),
    }


def readiness_by_day(entries: Any) -> list[dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for e in entries or []:
        if isinstance(e, dict) and e.get("calendarDate"):
            by_day.setdefault(e["calendarDate"], []).append(e)
    return [readiness(pick_morning(v)) for _, v in sorted(by_day.items())]


# ---------------------------------------------------------------------- HRV


def hrv_summary(s: dict[str, Any] | None) -> dict[str, Any] | None:
    if not s:
        return None
    return {
        "date": s.get("calendarDate"),
        "last_night_avg_ms": s.get("lastNightAvg"),
        "last_night_5min_high_ms": s.get("lastNight5MinHigh"),
        "weekly_avg_ms": s.get("weeklyAvg"),
        "status": phrase(s.get("status")),
        "baseline_low_ms": get(s, "baseline", "balancedLow"),
        "baseline_high_ms": get(s, "baseline", "balancedUpper"),
        "feedback": phrase(s.get("feedbackPhrase")),
    }


def hrv_rows(payload: Any) -> list[dict[str, Any]]:
    """Accepts the single-day shape ({hrvSummary}) or the range shape ({hrvSummaries: [...]})."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("hrvSummaries"), list):
        items = payload["hrvSummaries"]
    elif isinstance(payload, dict) and payload.get("hrvSummary"):
        items = [payload["hrvSummary"]]
    else:
        items = []
    rows = [hrv_summary(x.get("hrvSummary", x)) for x in items if isinstance(x, dict)]
    return sorted([r for r in rows if r], key=lambda r: r.get("date") or "")


# -------------------------------------------------------------------- sleep


def sleep(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    s = get(payload, "dailySleepDTO")
    if not s or not s.get("sleepTimeSeconds"):
        return None
    return {
        "date": s.get("calendarDate"),
        "score": get(s, "sleepScores", "overall", "value"),
        "quality": phrase(get(s, "sleepScores", "overall", "qualifierKey")),
        "bedtime": local_clock(s.get("sleepStartTimestampLocal")),
        "wake": local_clock(s.get("sleepEndTimestampLocal")),
        "asleep_h": hours(s.get("sleepTimeSeconds")),
        "deep_h": hours(s.get("deepSleepSeconds")),
        "light_h": hours(s.get("lightSleepSeconds")),
        "rem_h": hours(s.get("remSleepSeconds")),
        "awake_h": hours(s.get("awakeSleepSeconds")),
        "need_h": rnd((get(s, "sleepNeed", "actual") or 0) / 60, 2) if get(s, "sleepNeed", "actual") else None,
        "avg_overnight_hrv_ms": get(payload, "avgOvernightHrv") or s.get("avgSleepHRV"),
        "rhr": get(payload, "restingHeartRate"),
        "body_battery_change": get(payload, "bodyBatteryChange"),
        "respiration": rnd(s.get("averageRespirationValue"), 1),
        "avg_sleep_stress": rnd(s.get("avgSleepStress"), 0),
    }


# ---------------------------------------------------------------- day stats


def day_stats(s: dict[str, Any] | None) -> dict[str, Any] | None:
    if not s:
        return None
    return {
        "date": s.get("calendarDate"),
        "rhr": s.get("restingHeartRate"),
        "rhr_7d_avg": s.get("lastSevenDaysAvgRestingHeartRate"),
        "body_battery": {
            "at_wake": s.get("bodyBatteryAtWakeTime"),
            "high": s.get("bodyBatteryHighestValue"),
            "low": s.get("bodyBatteryLowestValue"),
            "now": s.get("bodyBatteryMostRecentValue"),
            "charged": s.get("bodyBatteryChargedValue"),
            "drained": s.get("bodyBatteryDrainedValue"),
        },
        "stress_avg": s.get("averageStressLevel"),
        "steps": s.get("totalSteps"),
        "active_kcal": rnd(s.get("activeKilocalories"), 0),
    }


# ---------------------------------------------------------- training status


def heat_acclimation(payload: Any) -> dict[str, Any] | None:
    """Garmin has sent this both inside mostRecentVO2Max and at the top level."""
    return get(payload, "mostRecentVO2Max", "heatAltitudeAcclimation") or get(payload, "heatAltitudeAcclimationDTO")


def training_status(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    st = primary_device_entry(get(payload, "mostRecentTrainingStatus", "latestTrainingStatusData")) or {}
    acute = st.get("acuteTrainingLoadDTO") or {}
    bal = primary_device_entry(
        get(payload, "mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap")
    ) or {}
    vo2 = get(payload, "mostRecentVO2Max", "generic") or {}
    heat = heat_acclimation(payload) or {}
    if not (st or bal or vo2 or heat):
        return None  # e.g. a new watch: every section is null

    def band(lo: str, hi: str) -> list[Any] | None:
        a, b = bal.get(lo), bal.get(hi)
        return None if a is None and b is None else [rnd(a, 0), rnd(b, 0)]

    return {
        "date": st.get("calendarDate"),
        "status": phrase(st.get("trainingStatusFeedbackPhrase")),
        "fitness_trend": st.get("fitnessTrend"),
        "weekly_load": rnd(st.get("weeklyTrainingLoad"), 0),
        "load_target_range": (
            [rnd(st.get("loadTunnelMin"), 0), rnd(st.get("loadTunnelMax"), 0)]
            if st.get("loadTunnelMin") is not None
            else None
        ),
        "acute_load": rnd(acute.get("dailyTrainingLoadAcute"), 0),
        "chronic_load": rnd(acute.get("dailyTrainingLoadChronic"), 0),
        "chronic_optimal_range": (
            [rnd(acute.get("minTrainingLoadChronic"), 0), rnd(acute.get("maxTrainingLoadChronic"), 0)]
            if acute.get("minTrainingLoadChronic") is not None
            else None
        ),
        "acwr": rnd(acute.get("dailyAcuteChronicWorkloadRatio"), 2),
        "acwr_status": phrase(acute.get("acwrStatus")),
        "load_focus": {
            "aerobic_low": rnd(bal.get("monthlyLoadAerobicLow"), 0),
            "aerobic_low_target": band("monthlyLoadAerobicLowTargetMin", "monthlyLoadAerobicLowTargetMax"),
            "aerobic_high": rnd(bal.get("monthlyLoadAerobicHigh"), 0),
            "aerobic_high_target": band("monthlyLoadAerobicHighTargetMin", "monthlyLoadAerobicHighTargetMax"),
            "anaerobic": rnd(bal.get("monthlyLoadAnaerobic"), 0),
            "anaerobic_target": band("monthlyLoadAnaerobicTargetMin", "monthlyLoadAnaerobicTargetMax"),
            "feedback": phrase(bal.get("trainingBalanceFeedbackPhrase")),
        }
        if bal
        else None,
        "vo2max": rnd(vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue"), 1),
        "vo2max_date": vo2.get("calendarDate"),
        "fitness_age": vo2.get("fitnessAge"),
        "heat_acclimation_pct": heat.get("heatAcclimationPercentage"),
    }


# ------------------------------------------------------------- performance


RACES = (("5k", "time5K"), ("10k", "time10K"), ("half", "timeHalfMarathon"), ("marathon", "timeMarathon"))


def race_predictions(p: dict[str, Any] | None) -> dict[str, Any] | None:
    if not p or not any(p.get(k) for _, k in RACES):
        return None
    out: dict[str, Any] = {"date": p.get("calendarDate")}
    for name, key in RACES:
        secs = p.get(key)
        out[name] = hms(secs)
        dist = {"5k": 5, "10k": 10, "half": 21.0975, "marathon": 42.195}[name]
        out[f"{name}_pace"] = pace(dist * 1000 / secs) if secs else None
    return out


def race_prediction_rows(payload: Any) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else [payload]
    rows = [race_predictions(x) for x in items if isinstance(x, dict)]
    return sorted([r for r in rows if r], key=lambda r: r.get("date") or "")


def lactate_threshold(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    sh = get(payload, "speed_and_heart_rate") or {}
    hr, speed = sh.get("heartRate"), sh.get("speed")
    if hr is None and speed is None:
        return None
    # Garmin stores this speed in tens of m/s (0.32 = 3.2 m/s); guard in case
    # it is ever sent in plain m/s.
    mps = None
    if isinstance(speed, (int, float)) and speed > 0:
        mps = speed * 10 if speed < 1.5 else speed
    return {
        "date": sh.get("calendarDate"),
        "heart_rate": hr,
        "pace": pace(mps),
        "speed_raw": speed,
    }


# --------------------------------------------------------------- activities


def _zones(a: dict[str, Any]) -> dict[str, float] | None:
    z = {f"z{i}": minutes(a.get(f"hrTimeInZone_{i}")) for i in range(1, 6)}
    return z if any(v is not None for v in z.values()) else None


def first(d: dict[str, Any], *keys: str) -> Any:
    """The activity list and the single-activity summary name some fields differently."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def activity(a: dict[str, Any]) -> dict[str, Any]:
    dist = a.get("distance")
    moving = a.get("movingDuration") or a.get("duration")
    stride = first(a, "avgStrideLength", "strideLength")
    tmin, tmax = a.get("minTemperature"), a.get("maxTemperature")
    return {
        "id": a.get("activityId"),
        "start": a.get("startTimeLocal"),
        "name": a.get("activityName"),
        "type": get(a, "activityType", "typeKey"),
        "km": rnd(dist / 1000, 2) if isinstance(dist, (int, float)) else None,
        "moving": hms(moving),
        "elapsed": hms(a.get("elapsedDuration") or a.get("duration")),
        "pace": pace(dist / moving) if dist and moving else pace(a.get("averageSpeed")),
        "gap_pace": pace(a.get("avgGradeAdjustedSpeed")),
        "avg_hr": rnd(a.get("averageHR"), 0),
        "max_hr": rnd(a.get("maxHR"), 0),
        "cadence_spm": rnd(first(a, "averageRunningCadenceInStepsPerMinute", "averageRunCadence"), 0),
        "stride_m": rnd(stride / 100, 2) if isinstance(stride, (int, float)) else None,
        "ground_contact_ms": rnd(first(a, "avgGroundContactTime", "groundContactTime"), 0),
        "vertical_osc_cm": rnd(first(a, "avgVerticalOscillation", "verticalOscillation"), 1),
        "vertical_ratio_pct": rnd(first(a, "avgVerticalRatio", "verticalRatio"), 1),
        "power_w": rnd(first(a, "avgPower", "averagePower"), 0),
        "norm_power_w": rnd(first(a, "normPower", "normalizedPower"), 0),
        "training_effect_aerobic": rnd(first(a, "aerobicTrainingEffect", "trainingEffect"), 1),
        "training_effect_anaerobic": rnd(a.get("anaerobicTrainingEffect"), 1),
        "training_effect_label": phrase(a.get("trainingEffectLabel")),
        "training_load": rnd(a.get("activityTrainingLoad"), 0),
        "vo2max": a.get("vO2MaxValue"),
        "temp_c": (
            [rnd(tmin, 0), rnd(tmax, 0)]
            if tmin is not None or tmax is not None
            else ([rnd(a["averageTemperature"], 0)] * 2 if a.get("averageTemperature") is not None else None)
        ),
        "elev_gain_m": rnd(a.get("elevationGain"), 0),
        "body_battery_change": a.get("differenceBodyBattery"),
        "kcal": rnd(a.get("calories"), 0),
        "hr_zone_min": _zones(a),
        "laps": a.get("lapCount"),
    }


def laps(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    out = []
    for i, lap in enumerate(get(payload, "lapDTOs") or [], start=1):
        if not isinstance(lap, dict):
            continue
        dist = lap.get("distance")
        moving = lap.get("movingDuration") or lap.get("duration")
        out.append(
            {
                "lap": lap.get("lapIndex") or i,
                "intensity": phrase(lap.get("intensityType")),
                "km": rnd(dist / 1000, 2) if isinstance(dist, (int, float)) else None,
                "time": hms(lap.get("duration")),
                "pace": pace(dist / moving) if dist and moving else pace(lap.get("averageSpeed")),
                "gap_pace": pace(lap.get("avgGradeAdjustedSpeed")),
                "avg_hr": rnd(lap.get("averageHR"), 0),
                "max_hr": rnd(lap.get("maxHR"), 0),
                "cadence_spm": rnd(lap.get("averageRunCadence"), 0),
                "stride_m": rnd((lap.get("strideLength") or 0) / 100, 2) if lap.get("strideLength") else None,
                "ground_contact_ms": rnd(lap.get("groundContactTime"), 0),
                "vertical_osc_cm": rnd(lap.get("verticalOscillation"), 1),
                "vertical_ratio_pct": rnd(lap.get("verticalRatio"), 1),
                "power_w": rnd(lap.get("averagePower"), 0),
                "elev_gain_m": rnd(lap.get("elevationGain"), 0),
            }
        )
    return out


# ------------------------------------------------------------- daily rows


def daily_row(
    day: str,
    ready: dict[str, Any] | None,
    hrv: dict[str, Any] | None,
    slp: dict[str, Any] | None,
    stats: dict[str, Any] | None,
    status: dict[str, Any] | None,
) -> dict[str, Any]:
    """One flat row per day for trends and the tracker."""
    return {
        "date": day,
        "readiness": get(ready, "score"),
        "readiness_level": get(ready, "level"),
        "hrv_ms": get(hrv, "last_night_avg_ms"),
        "hrv_weekly_ms": get(hrv, "weekly_avg_ms"),
        "hrv_status": get(hrv, "status"),
        "sleep_score": get(slp, "score"),
        "sleep_h": get(slp, "asleep_h"),
        "deep_h": get(slp, "deep_h"),
        "rem_h": get(slp, "rem_h"),
        "bedtime": get(slp, "bedtime"),
        "wake": get(slp, "wake"),
        "rhr": get(stats, "rhr") or get(slp, "rhr"),
        "body_battery_wake": get(stats, "body_battery", "at_wake"),
        "body_battery_high": get(stats, "body_battery", "high"),
        "body_battery_low": get(stats, "body_battery", "low"),
        "stress_avg": get(stats, "stress_avg"),
        "training_status": get(status, "status"),
        "acute_load": get(status, "acute_load"),
        "chronic_load": get(status, "chronic_load"),
        "acwr": get(status, "acwr"),
        "vo2max": get(status, "vo2max"),
    }
