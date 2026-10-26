"""Running workouts: a compact step list in, Garmin's workout JSON out, and back.

A workout is a list of steps and repeat blocks::

    [{"kind": "warmup", "distance_km": 2},
     {"repeat": 2, "steps": [{"kind": "run", "distance_km": 3, "pace": "5:35-5:45"},
                             {"kind": "recovery", "duration": "2:00"}]},
     {"kind": "cooldown", "distance_km": 2}]

A step ends after ``distance_km`` or ``duration`` ("m:ss" / "h:mm:ss"), or when
the lap button is pressed if neither is given. ``pace`` ("min:sec-min:sec" per
km) and ``hr`` ("low-high" bpm) are targets the watch alerts on; with both, pace
is the main target and HR the secondary one.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

# Added to the description of every workout created here, so delete only ever
# removes our own workouts and never one the user made in the app.
MARKER = "[garmin-mcp]"

RUNNING = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}

_STEP_TYPES = {
    "warmup": (1, "warmup"),
    "cooldown": (2, "cooldown"),
    "run": (3, "interval"),
    "recovery": (4, "recovery"),
    "rest": (5, "rest"),
}
_KIND_BY_KEY = {key: kind for kind, (_, key) in _STEP_TYPES.items()}
_REPEAT_TYPE = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}

_LAP = {"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True}
_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
_DISTANCE = {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True}
_ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}

_NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
_HR_TARGET = {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4}
_PACE_TARGET = {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6}

# Used only to estimate how long a distance step with no pace target takes.
_DEFAULT_SEC_PER_KM = 420

_CLOCK = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")
_RANGE = re.compile(r"^\s*(\S+)\s*[-–—]\s*(\S+)\s*$")


def parse_clock(text: str, what: str = "duration") -> int:
    """'2:00' → 120, '1:05:00' → 3900."""
    m = _CLOCK.match(text.strip())
    if not m:
        raise ValueError(f"{what} must look like m:ss or h:mm:ss, got {text!r}")
    h, mnt, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    if s >= 60 or (m.group(1) and mnt >= 60):
        raise ValueError(f"{what} {text!r} has more than 59 minutes or seconds")
    return h * 3600 + mnt * 60 + s


def _split_range(text: str, what: str) -> tuple[str, str]:
    m = _RANGE.match(text)
    if not m:
        raise ValueError(f"{what} must be a range like {'5:35-5:45' if what == 'pace' else '140-150'}, got {text!r}")
    return m.group(1), m.group(2)


def parse_pace(text: str) -> tuple[int, int]:
    """'5:35-5:45' → (335, 345) seconds per km, faster first."""
    a, b = (parse_clock(x, "pace") for x in _split_range(text, "pace"))
    lo, hi = sorted((a, b))
    if lo < 150 or hi > 1200:
        raise ValueError(f"pace {text!r} is outside 2:30-20:00 per km")
    return lo, hi


def parse_hr(text: str) -> tuple[int, int]:
    a, b = _split_range(text, "hr")
    try:
        lo, hi = sorted((int(a), int(b)))
    except ValueError:
        raise ValueError(f"hr must be whole bpm like 140-150, got {text!r}") from None
    if lo < 40 or hi > 230:
        raise ValueError(f"hr {text!r} is outside 40-230 bpm")
    return lo, hi


def fmt_clock(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class Step(BaseModel):
    """One step. Ends after distance_km or duration, else on the lap button."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["warmup", "run", "recovery", "rest", "cooldown"]
    distance_km: float | None = Field(None, gt=0, le=100, description="Step ends after this many km")
    duration: str | None = Field(None, description="Step ends after this time, m:ss or h:mm:ss")
    pace: str | None = Field(None, description="Target pace range per km, e.g. 5:35-5:45")
    hr: str | None = Field(None, description="Target heart-rate range in bpm, e.g. 140-150")
    note: str | None = Field(None, max_length=100, description="Short note shown with the step on the watch")
    about_km: float | None = Field(
        None, gt=0, le=100, description="Expected km of a lap-button step, only for the time estimate"
    )

    @model_validator(mode="after")
    def _check(self) -> Step:
        if self.distance_km is not None and self.duration is not None:
            raise ValueError("give distance_km or duration, not both")
        if self.about_km is not None and (self.distance_km is not None or self.duration is not None):
            raise ValueError("about_km is only for steps that end on the lap button")
        if self.duration is not None and parse_clock(self.duration) <= 0:
            raise ValueError("duration must be more than 0")
        if self.pace is not None:
            parse_pace(self.pace)
        if self.hr is not None:
            parse_hr(self.hr)
        return self


class Repeat(BaseModel):
    """A block of steps done `repeat` times."""

    model_config = ConfigDict(extra="forbid")

    repeat: int = Field(ge=2, le=50, description="How many times to do the steps")
    steps: list[Step] = Field(min_length=1, max_length=10)
    skip_last_recovery: bool = Field(
        True, description="Skip the final recovery/rest step and go straight to the next step"
    )


Item = Step | Repeat
ITEMS = TypeAdapter(list[Item])


def parse_items(raw: Any) -> list[Item]:
    items = ITEMS.validate_python(raw)
    if not items:
        raise ValueError("a workout needs at least one step")
    return items


def _target(spec: tuple[dict, float, float] | None) -> dict[str, Any]:
    if spec is None:
        return {"targetType": dict(_NO_TARGET)}
    kind, one, two = spec
    return {"targetType": dict(kind), "targetValueOne": one, "targetValueTwo": two}


def _targets(step: Step) -> dict[str, Any]:
    pace = hr = None
    if step.pace:
        fast, slow = parse_pace(step.pace)
        # Garmin stores pace as speed in m/s: the slower pace is the lower value.
        pace = (_PACE_TARGET, round(1000 / slow, 4), round(1000 / fast, 4))
    if step.hr:
        lo, hi = parse_hr(step.hr)
        hr = (_HR_TARGET, float(lo), float(hi))
    out = _target(pace or hr)
    if pace and hr:
        out |= {
            "secondaryTargetType": dict(_HR_TARGET),
            "secondaryTargetValueOne": hr[1],
            "secondaryTargetValueTwo": hr[2],
        }
    return out


def _step_json(step: Step, order: int, child: int | None) -> dict[str, Any]:
    type_id, type_key = _STEP_TYPES[step.kind]
    if step.distance_km is not None:
        end, value = _DISTANCE, round(step.distance_km * 1000, 1)
    elif step.duration is not None:
        end, value = _TIME, float(parse_clock(step.duration))
    else:
        end, value = _LAP, None
    out: dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": type_id, "stepTypeKey": type_key, "displayOrder": type_id},
        "endCondition": dict(end),
        "endConditionValue": value,
        **_targets(step),
    }
    if child is not None:
        out["childStepId"] = child
    if step.note:
        out["description"] = step.note
    return out


def _step_estimate(step: Step) -> tuple[float, float]:
    """(seconds, meters) the step is expected to take; a lap-button step counts
    its about_km, or 0 without one."""
    if step.duration is not None:
        sec = float(parse_clock(step.duration))
        per_km = sum(parse_pace(step.pace)) / 2 if step.pace else _DEFAULT_SEC_PER_KM
        return sec, sec / per_km * 1000
    km = step.distance_km if step.distance_km is not None else step.about_km
    if km is not None:
        per_km = sum(parse_pace(step.pace)) / 2 if step.pace else _DEFAULT_SEC_PER_KM
        return km * per_km, km * 1000
    return 0.0, 0.0


def _is_rest(step: Step) -> bool:
    return step.kind in ("recovery", "rest")


def estimate(items: list[Item]) -> tuple[float, float]:
    sec = dist = 0.0
    for item in items:
        if isinstance(item, Step):
            s, d = _step_estimate(item)
            sec, dist = sec + s, dist + d
            continue
        block = [_step_estimate(s) for s in item.steps]
        sec += sum(s for s, _ in block) * item.repeat
        dist += sum(d for _, d in block) * item.repeat
        if item.skip_last_recovery and _is_rest(item.steps[-1]):
            sec -= block[-1][0]
            dist -= block[-1][1]
    return sec, dist


def build(name: str, items: list[Item], description: str | None = None) -> dict[str, Any]:
    """Garmin's workout JSON for POST /workout-service/workout."""
    name = name.strip()
    if not name or len(name) > 60:
        raise ValueError("name must be 1-60 characters")
    steps: list[dict[str, Any]] = []
    order = 0
    group = 0
    for item in items:
        order += 1
        if isinstance(item, Step):
            steps.append(_step_json(item, order, None))
            continue
        group += 1
        block = {
            "type": "RepeatGroupDTO",
            "stepOrder": order,
            "stepType": dict(_REPEAT_TYPE),
            "childStepId": group,
            "numberOfIterations": item.repeat,
            "smartRepeat": False,
            "skipLastRestStep": bool(item.skip_last_recovery and _is_rest(item.steps[-1])),
            "endCondition": dict(_ITERATIONS),
            "endConditionValue": float(item.repeat),
            "workoutSteps": [],
        }
        for step in item.steps:
            order += 1
            block["workoutSteps"].append(_step_json(step, order, group))
        steps.append(block)

    sec, dist = estimate(items)
    text = (description or "").strip()
    return {
        "workoutName": name,
        "description": f"{text}\n{MARKER}" if text else MARKER,
        "sportType": dict(RUNNING),
        "estimatedDurationInSecs": int(round(sec)),
        "estimatedDistanceInMeters": round(dist, 1),
        "workoutSegments": [{"segmentOrder": 1, "sportType": dict(RUNNING), "workoutSteps": steps}],
    }


def is_ours(workout: dict[str, Any]) -> bool:
    return MARKER in (workout.get("description") or "")


# ---- reading a workout back (what Garmin stored) -------------------------------


def _pace_text(one: Any, two: Any) -> str | None:
    try:
        speeds = sorted(float(v) for v in (one, two))
    except (TypeError, ValueError):
        return None
    if speeds[0] <= 0:
        return None
    return f"{fmt_clock(1000 / speeds[1])}-{fmt_clock(1000 / speeds[0])}"


def _target_text(type_: dict | None, one: Any, two: Any) -> str | None:
    key = (type_ or {}).get("workoutTargetTypeKey")
    if key == "pace.zone":
        p = _pace_text(one, two)
        return f"pace {p}/km" if p else None
    if key == "heart.rate.zone" and one is not None and two is not None:
        return f"HR {int(float(one))}-{int(float(two))}"
    return None


def _describe_step(s: dict[str, Any]) -> str:
    kind = _KIND_BY_KEY.get((s.get("stepType") or {}).get("stepTypeKey"), "other")
    end = (s.get("endCondition") or {}).get("conditionTypeKey")
    value = s.get("endConditionValue")
    if end == "distance" and value:
        how = f"{float(value) / 1000:g} km"
    elif end == "time" and value:
        how = fmt_clock(float(value))
    elif end == "lap.button":
        how = "until lap button"
    else:
        how = end or "?"
    parts = [kind, how]
    for t in (
        _target_text(s.get("targetType"), s.get("targetValueOne"), s.get("targetValueTwo")),
        _target_text(s.get("secondaryTargetType"), s.get("secondaryTargetValueOne"), s.get("secondaryTargetValueTwo")),
    ):
        if t:
            parts.append(t)
    if s.get("description"):
        parts.append(f"({s['description']})")
    return " · ".join(parts)


def describe(workout: dict[str, Any]) -> list[str]:
    """One line per step, from either our JSON or Garmin's stored copy."""
    lines: list[str] = []
    for seg in workout.get("workoutSegments") or []:
        for s in seg.get("workoutSteps") or []:
            if s.get("type") == "RepeatGroupDTO" or (s.get("stepType") or {}).get("stepTypeKey") == "repeat":
                skip = " (skip last recovery)" if s.get("skipLastRestStep") else ""
                lines.append(f"repeat {s.get('numberOfIterations')}×{skip}:")
                lines += [f"  {_describe_step(c)}" for c in s.get("workoutSteps") or []]
            else:
                lines.append(_describe_step(s))
    return lines
