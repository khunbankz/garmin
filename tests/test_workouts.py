import json
from datetime import date

import pytest

from garmin_mcp import cli_workouts, service
from garmin_mcp import workouts as W

from . import fake

TEMPO = [
    {"kind": "warmup", "distance_km": 2},
    {"repeat": 2, "steps": [
        {"kind": "run", "distance_km": 3, "pace": "5:35-5:45", "note": "HR cap 168"},
        {"kind": "recovery", "duration": "2:00"},
    ]},
    {"kind": "cooldown"},
]


def test_build_tempo_matches_garmin_shape():
    w = W.build("Tempo 2x3k", W.parse_items(TEMPO), "เทมโป 2×3 กม.")
    steps = w["workoutSegments"][0]["workoutSteps"]
    assert [s["stepOrder"] for s in steps] == [1, 2, 5]
    warm, block, cool = steps
    assert warm["endCondition"]["conditionTypeKey"] == "distance" and warm["endConditionValue"] == 2000
    assert warm["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert block["type"] == "RepeatGroupDTO" and block["numberOfIterations"] == 2
    assert block["skipLastRestStep"] is True and block["childStepId"] == 1
    run, rec = block["workoutSteps"]
    assert (run["stepOrder"], rec["stepOrder"]) == (3, 4)
    assert run["stepType"]["stepTypeKey"] == "interval" and run["childStepId"] == 1
    # Pace is stored as speed: slower pace (5:45) is the lower value.
    assert run["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    assert run["targetValueOne"] == pytest.approx(1000 / 345, abs=1e-3)
    assert run["targetValueTwo"] == pytest.approx(1000 / 335, abs=1e-3)
    assert run["description"] == "HR cap 168"
    assert rec["endCondition"]["conditionTypeKey"] == "time" and rec["endConditionValue"] == 120
    assert cool["endCondition"]["conditionTypeKey"] == "lap.button" and cool["endConditionValue"] is None
    assert w["description"].endswith(W.MARKER) and w["description"].startswith("เทมโป")
    # 2 km easy (14:00) + 2×3 km at 5:40 (34:00) + one 2:00 recovery; lap-button cooldown counts 0.
    assert w["estimatedDurationInSecs"] == 14 * 60 + 34 * 60 + 120
    assert W.describe(w) == [
        "warmup · 2 km",
        "repeat 2× (skip last recovery):",
        "  run · 3 km · pace 5:35-5:45/km · (HR cap 168)",
        "  recovery · 2:00",
        "cooldown · until lap button",
    ]


def test_pace_and_hr_make_hr_the_secondary_target():
    w = W.build("x", W.parse_items([{"kind": "run", "distance_km": 22, "pace": "6:45-7:15", "hr": "130-150"}]))
    s = w["workoutSegments"][0]["workoutSteps"][0]
    assert s["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    assert s["secondaryTargetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert (s["secondaryTargetValueOne"], s["secondaryTargetValueTwo"]) == (130, 150)
    assert W.describe(w) == ["run · 22 km · pace 6:45-7:15/km · HR 130-150"]


def test_hr_only_target():
    s = W.build("x", W.parse_items([{"kind": "run", "distance_km": 5, "hr": "150-140"}]))["workoutSegments"][0]["workoutSteps"][0]
    assert s["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert (s["targetValueOne"], s["targetValueTwo"]) == (140, 150)


@pytest.mark.parametrize(
    "steps, msg",
    [
        ([{"kind": "run", "distance_km": 1, "duration": "5:00"}], "not both"),
        ([{"kind": "run", "pace": "5:35"}], "range"),
        ([{"kind": "run", "pace": "1:00-1:10"}], "outside"),
        ([{"kind": "run", "hr": "100-260"}], "outside"),
        ([{"kind": "run", "duration": "5:75"}], "59"),
        ([{"kind": "sprint"}], "kind"),
        ([{"repeat": 1, "steps": [{"kind": "run"}]}], "repeat"),
        ([], "at least one"),
    ],
)
def test_bad_steps_are_rejected(steps, msg):
    with pytest.raises(ValueError, match=msg):
        W.parse_items(steps)


def test_create_schedules_and_skips_duplicates():
    api = fake.FakeGarmin()
    res = service.create_workout(api, "Tempo 2x3k", TEMPO, date(2026, 10, 27), "note")
    wid, sid = res["workout_id"], res["schedule_id"]
    assert api.schedules[sid]["calendarDate"] == "2026-10-27"
    assert service.scheduled_workouts(api, date(2026, 10, 27), date(2026, 10, 31)) == [
        {"date": "2026-10-27", "schedule_id": sid, "workout_id": wid, "name": "Tempo 2x3k"},
        {"date": "2026-10-28", "schedule_id": 500, "workout_id": 77, "name": "My own intervals"},
    ]
    again = service.create_workout(api, "Tempo 2x3k", TEMPO, date(2026, 10, 27))
    assert again["skipped"] and again["existing"]["schedule_id"] == sid
    assert len(api.workouts) == 2


def test_dry_run_uploads_nothing():
    api = fake.FakeGarmin()
    res = service.create_workout(api, "Tempo 2x3k", TEMPO, date(2026, 10, 27), dry_run=True)
    assert res["dry_run"] and res["estimated"] == {"minutes": 50, "km": 8.3}
    assert not any(name == "upload_workout" for name, _ in api.calls)


def test_schedule_failure_keeps_the_workout_id():
    api = fake.FakeGarmin()
    api.fail["schedule_workout"] = RuntimeError("boom")
    res = service.create_workout(api, "Tempo 2x3k", TEMPO, date(2026, 10, 27))
    assert res["workout_id"] in api.workouts and "boom" in res["schedule_error"]


def test_scheduled_spans_months():
    api = fake.FakeGarmin()
    service.create_workout(api, "A", TEMPO, date(2026, 11, 3))
    rows = service.scheduled_workouts(api, date(2026, 10, 27), date(2026, 11, 22))
    assert [r["date"] for r in rows] == ["2026-10-28", "2026-11-03"]
    assert ("get_scheduled_workouts", (2026, 11)) in api.calls


def test_move_unschedule_and_delete_only_ours():
    api = fake.FakeGarmin()
    res = service.create_workout(api, "Tempo 2x3k", TEMPO, date(2026, 10, 27))
    moved = service.move_scheduled(api, str(res["schedule_id"]), date(2026, 10, 28))
    assert moved["from"] == "2026-10-27" and moved["to"] == "2026-10-28"
    assert res["schedule_id"] not in api.schedules and api.schedules[moved["schedule_id"]]["calendarDate"] == "2026-10-28"
    with pytest.raises(ValueError, match="not created by garmin-mcp"):
        service.delete_workout(api, "77")
    assert 77 in api.workouts
    assert service.unschedule(api, "500") == {"unscheduled": "500"} and 500 not in api.schedules
    assert service.delete_workout(api, str(res["workout_id"]))["name"] == "Tempo 2x3k"
    assert res["workout_id"] not in api.workouts and not api.schedules


def test_show_reads_back_what_garmin_stored():
    api = fake.FakeGarmin()
    wid = service.create_workout(api, "Tempo 2x3k", TEMPO)["workout_id"]
    shown = service.show_workout(api, str(wid))
    assert shown["by_garmin_mcp"] is True and shown["steps"][2] == "  run · 3 km · pace 5:35-5:45/km · (HR cap 168)"
    listed = service.list_workouts(api)
    assert [(r["name"], r["by_garmin_mcp"]) for r in listed] == [("Tempo 2x3k", True), ("My own intervals", False)]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("GARMIN_MCP_HOME", str(tmp_path))
    monkeypatch.setenv("GARMIN_MCP_FAKE", "tests.fake:FakeGarmin")
    (tmp_path / "garmin_tokens.json").write_text("{}")
    return tmp_path


def test_cli_push_checks_everything_first(home, tmp_path, capsys):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps([
        {"name": "Tempo 2x3k", "date": "2026-10-27", "steps": TEMPO},
        {"name": "Broken", "date": "2026-10-29", "steps": [{"kind": "run", "pace": "fast"}]},
    ]))
    with pytest.raises(SystemExit) as e:
        cli_workouts.main(["push", str(plan)])
    assert e.value.code == 1
    assert "workout 2 (Broken)" in capsys.readouterr().err


def test_cli_push(home, tmp_path, capsys):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"workouts": [
        {"name": "Tempo 2x3k", "date": "2026-10-27", "steps": TEMPO},
        {"name": "HMP 4k", "date": "2026-10-29", "steps": [
            {"kind": "warmup", "distance_km": 2},
            {"kind": "run", "distance_km": 4, "pace": "5:35-5:40"},
            {"kind": "cooldown", "distance_km": 2}]},
    ]}, ensure_ascii=False))
    cli_workouts.main(["push", str(plan), "--pause", "0"])
    out = capsys.readouterr().out
    assert out.count("✓ ") == 2 and "2026-10-29  HMP 4k" in out and "pace 5:35-5:40/km" in out
    cli_workouts.main(["push", str(plan), "--dry-run"])
    assert capsys.readouterr().out.count("· 2026-") == 2
