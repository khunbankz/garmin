from datetime import date

import pytest
from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

from garmin_mcp import service
from garmin_mcp.config import Config
from garmin_mcp.errors import NotConnectedError, RateLimitedError
from garmin_mcp.session import GarminSession

from . import fake


def test_today_summary_combines_everything():
    api = fake.FakeGarmin()
    out = service.today_summary(api)
    assert out["date"] == "2026-10-25"
    assert out["readiness"]["score"] == 72 and out["readiness_now"] == 61
    assert out["hrv"]["last_night_avg_ms"] == 44
    assert out["sleep"]["score"] == 78
    assert out["day"]["body_battery"]["at_wake"] == 81
    assert out["training_status"]["status"] == "productive"
    assert out["race_predictions"]["marathon"] == "4:07:00"
    assert out["activities_today"][0]["km"] == 8.01


def test_one_failing_section_does_not_hide_the_rest():
    api = fake.FakeGarmin()
    api.fail["get_sleep_data"] = RuntimeError("boom")
    out = service.today_summary(api)
    assert out["sleep"] == {"error": "RuntimeError: boom"}
    assert out["readiness"]["score"] == 72


def test_auth_and_rate_limit_errors_are_not_swallowed():
    api = fake.FakeGarmin()
    api.fail["get_sleep_data"] = GarminConnectAuthenticationError("expired")
    with pytest.raises(GarminConnectAuthenticationError):
        service.today_summary(api)
    api.fail = {"get_hrv_data": GarminConnectTooManyRequestsError("slow down")}
    with pytest.raises(GarminConnectTooManyRequestsError):
        service.today_summary(api)


def test_daily_rows_merge_range_and_per_day_calls():
    api = fake.FakeGarmin()
    rows = service.daily_rows(api, date(2026, 10, 24), date(2026, 10, 25))
    assert [r["date"] for r in rows] == ["2026-10-24", "2026-10-25"]
    assert rows[0]["readiness"] == 48 and rows[1]["readiness"] == 72
    assert rows[0]["hrv_ms"] == 35 and rows[0]["hrv_status"] == "unbalanced"
    assert rows[1]["sleep_score"] == 78 and rows[1]["acute_load"] == 612 and rows[1]["vo2max"] == 47.6
    assert rows[0]["rhr"] == 49 and rows[0]["body_battery_wake"] == 81
    assert ("get_user_summary", ("2026-10-24",)) in api.calls
    # Race predictor and load focus for the tracker cards.
    assert rows[0]["race_marathon_s"] == 14900 and rows[1]["race_half_s"] == 6912
    assert rows[1]["load_anaerobic"] == 35 and rows[1]["load_anaerobic_min"] == 90
    assert rows[1]["weekly_load_max"] == 811 and rows[1]["chronic_min"] == 398


def test_daily_rows_fall_back_to_max_metrics_vo2max():
    api = fake.FakeGarmin()
    api.get_training_status = lambda d: {"mostRecentTrainingStatus": None}
    rows = service.daily_rows(api, date(2026, 10, 24), date(2026, 10, 25))
    assert rows[0]["vo2max"] == 47.2 and rows[1]["vo2max"] is None


def test_run_rows_are_flat_numbers():
    rows = service.run_rows(fake.FakeGarmin(), date(2026, 10, 25), date(2026, 10, 25))
    r = rows[0]
    assert r["id"] == "20712345678" and r["date"] == "2026-10-25" and r["time"] == "05:31"
    assert r["km"] == 8.012 and r["moving_s"] == 3310 and r["te_label"] == "aerobic base"
    assert r["cadence_spm"] == 171 and r["stride_m"] == 0.84 and r["load"] == 72


def test_performance_falls_back_to_training_status_vo2max():
    out = service.performance(fake.FakeGarmin())
    assert out["vo2max"] == {"value": 47.6, "date": "2026-10-24", "fitness_age": 33}
    assert out["lactate_threshold"]["heart_rate"] == 166
    assert out["heat_acclimation_pct"] == 64


def test_activity_laps_flattens_the_detail_summary():
    out = service.activity_laps(fake.FakeGarmin(), "20712345678")
    assert out["summary"]["type"] == "running" and out["summary"]["km"] == 8.01
    assert len(out["laps"]) == 2


def test_raw_is_limited_to_read_methods_and_prunes():
    api = fake.FakeGarmin()
    out = service.raw(api, "get_hrv_data", {"date": "2026-10-25"})
    assert len(out["hrvReadings"]) == 21 and out["hrvReadings"][-1] == "... 30 more"
    with pytest.raises(ValueError, match="Unknown method"):
        service.raw(api, "delete_activity", {})
    with pytest.raises(ValueError, match="needs: activity_id"):
        service.raw(api, "get_activity_splits", {})


def _session(tmp_path, api):
    return GarminSession(Config(home=tmp_path), factory=lambda: api)


def test_session_requires_saved_tokens(tmp_path):
    with pytest.raises(NotConnectedError, match="garmin-mcp-auth"):
        _session(tmp_path, fake.FakeGarmin()).call(lambda api: 1)


def test_session_logs_in_once_and_reloads_tokens_changed_by_another_process(tmp_path):
    api = fake.FakeGarmin()
    tokens = tmp_path / "garmin_tokens.json"
    tokens.write_text("{}")
    sess = _session(tmp_path, api)
    assert sess.call(lambda a: a.get_full_name()) == "Test Runner"
    sess.call(lambda a: None)
    assert api.logins == 1 and api.client.loads == 0
    # Another process refreshed and rewrote the file.
    tokens.write_text('{"x": 1}')
    import os

    st = tokens.stat()
    os.utime(tokens, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    sess.call(lambda a: None)
    assert api.client.loads == 1 and api.logins == 1
    assert (tmp_path / ".lock").exists()


def test_session_maps_library_errors(tmp_path):
    (tmp_path / "garmin_tokens.json").write_text("{}")
    api = fake.FakeGarmin()
    sess = _session(tmp_path, api)

    def expired(a):
        raise GarminConnectAuthenticationError("401")

    with pytest.raises(NotConnectedError, match="rejected the saved login"):
        sess.call(expired)

    def limited(a):
        raise GarminConnectTooManyRequestsError("429")

    with pytest.raises(RateLimitedError):
        sess.call(limited)
    # After an auth failure the next call logs in again from the token file.
    assert api.logins == 2
