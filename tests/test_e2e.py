"""Start the real server over stdio (with the fake Garmin) and call it like Claude does."""

import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def _text(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


async def _exercise(home: Path) -> dict:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "garmin_mcp.server"],
        env={
            **os.environ,
            "GARMIN_MCP_HOME": str(home),
            "GARMIN_MCP_FAKE": "tests.fake:FakeGarmin",
            "PYTHONPATH": f"{ROOT}{os.pathsep}{ROOT / 'src'}",
        },
        cwd=str(ROOT),
    )
    out: dict = {}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            out["tools"] = {t.name: t for t in tools.tools}
            out["today"] = await s.call_tool("get_today", {})
            out["laps"] = await s.call_tool("get_activity_laps", {"activity_id": "20712345678"})
            out["bad_range"] = await s.call_tool("get_daily", {"start_date": "2026-01-01", "end_date": "2026-10-25"})
            out["raw"] = await s.call_tool("get_raw", {"method": "get_race_predictions"})
            steps = [
                {"kind": "warmup", "distance_km": 2},
                {"repeat": 2, "steps": [{"kind": "run", "distance_km": 3, "pace": "5:35-5:45"},
                                        {"kind": "recovery", "duration": "2:00"}]},
                {"kind": "cooldown", "distance_km": 2},
            ]
            out["create"] = await s.call_tool("create_workout", {"name": "Tempo 2x3k", "steps": steps, "date": "2026-10-27"})
            out["scheduled"] = await s.call_tool("get_scheduled_workouts", {"start_date": "2026-10-27"})
            out["bad_step"] = await s.call_tool("create_workout", {"name": "x", "steps": [{"kind": "run", "pace": "fast"}]})
            out["delete_theirs"] = await s.call_tool("delete_workout", {"workout_id": "77"})
    return out


def test_stdio_end_to_end(tmp_path):
    (tmp_path / "garmin_tokens.json").write_text("{}")
    out = anyio.run(_exercise, tmp_path)

    read = {
        "get_today", "get_readiness", "get_hrv", "get_sleep", "get_training_status",
        "get_performance", "get_race_predictions", "get_activities", "get_activity_laps",
        "get_daily", "get_raw", "get_scheduled_workouts", "get_workouts", "get_workout",
    }
    write = {"create_workout", "move_workout", "unschedule_workout", "delete_workout"}
    assert set(out["tools"]) == read | write
    assert all(out["tools"][n].annotations.read_only_hint for n in read)
    assert not any(out["tools"][n].annotations.read_only_hint for n in write)
    assert out["tools"]["delete_workout"].annotations.destructive_hint
    assert "get_activity_splits" in out["tools"]["get_raw"].description

    today = json.loads(_text(out["today"]))
    assert today["readiness"]["score"] == 72 and today["training_status"]["acwr"] == 1.23

    laps = json.loads(_text(out["laps"]))
    assert laps["laps"][1]["pace"] == "5:37"

    assert out["bad_range"].is_error and "at most 31" in _text(out["bad_range"])
    assert json.loads(_text(out["raw"]))["timeMarathon"] == 14820

    created = json.loads(_text(out["create"]))
    assert created["schedule_id"] and created["steps"][2].endswith("pace 5:35-5:45/km")
    names = [json.loads(c.text)["name"] for c in out["scheduled"].content]
    assert names == ["Tempo 2x3k", "My own intervals"]
    assert out["bad_step"].is_error and "pace" in _text(out["bad_step"])
    assert out["delete_theirs"].is_error and "not created by garmin-mcp" in _text(out["delete_theirs"])


def test_not_connected_message(tmp_path):
    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "garmin_mcp.server"],
            env={**os.environ, "GARMIN_MCP_HOME": str(tmp_path), "GARMIN_MCP_FAKE": "tests.fake:FakeGarmin",
                 "PYTHONPATH": f"{ROOT}{os.pathsep}{ROOT / 'src'}"},
            cwd=str(ROOT),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                return await s.call_tool("get_today", {})

    res = anyio.run(run)
    assert res.is_error and "garmin-mcp-auth" in _text(res)
