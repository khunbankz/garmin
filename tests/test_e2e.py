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
    return out


def test_stdio_end_to_end(tmp_path):
    (tmp_path / "garmin_tokens.json").write_text("{}")
    out = anyio.run(_exercise, tmp_path)

    assert set(out["tools"]) == {
        "get_today", "get_readiness", "get_hrv", "get_sleep", "get_training_status",
        "get_performance", "get_race_predictions", "get_activities", "get_activity_laps",
        "get_daily", "get_raw",
    }
    assert all(t.annotations and t.annotations.read_only_hint for t in out["tools"].values())
    assert "get_activity_splits" in out["tools"]["get_raw"].description

    today = json.loads(_text(out["today"]))
    assert today["readiness"]["score"] == 72 and today["training_status"]["acwr"] == 1.23

    laps = json.loads(_text(out["laps"]))
    assert laps["laps"][1]["pace"] == "5:37"

    assert out["bad_range"].is_error and "at most 31" in _text(out["bad_range"])
    assert json.loads(_text(out["raw"]))["timeMarathon"] == 14820


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
