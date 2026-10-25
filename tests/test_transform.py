from garmin_mcp import transform as T

from . import fake


def test_units():
    assert T.pace(2.39) == "6:58"
    assert T.pace(0) is None and T.pace(None) is None
    assert T.hms(3101) == "51:41"
    assert T.hms(14820) == "4:07:00"
    assert T.hours(26604) == 7.39
    assert T.phrase("PRODUCTIVE_3") == "productive"
    assert T.phrase("ANAEROBIC_SHORTAGE") == "anaerobic shortage"
    assert T.local_clock(fake.SLEEP["dailySleepDTO"]["sleepStartTimestampLocal"]) == "22:43"


def test_readiness_uses_the_morning_score():
    r = T.readiness(T.pick_morning(fake.READINESS))
    assert r["score"] == 72 and r["time"] == "06:41" and r["level"] == "high"
    assert r["recovery_time_h"] == 7.0
    assert r["factors"]["sleep_history"] == {"pct": 40, "feedback": "poor"}
    assert T.latest_entry(fake.READINESS)["score"] == 61


def test_readiness_by_day_picks_one_row_per_day():
    rows = T.readiness_by_day(fake.READINESS_RANGE)
    assert [(r["date"], r["score"]) for r in rows] == [("2026-10-24", 48), ("2026-10-25", 72)]


def test_hrv_single_and_range_shapes():
    one = T.hrv_rows({"hrvSummary": fake.HRV_SUMMARY})
    assert one[0]["last_night_avg_ms"] == 44 and one[0]["status"] == "balanced"
    assert one[0]["baseline_low_ms"] == 36 and one[0]["baseline_high_ms"] == 48
    rng = T.hrv_rows({"hrvSummaries": [fake.HRV_SUMMARY, {**fake.HRV_SUMMARY, "calendarDate": "2026-10-24"}]})
    assert [r["date"] for r in rng] == ["2026-10-24", "2026-10-25"]
    assert T.hrv_rows(None) == []


def test_sleep():
    s = T.sleep(fake.SLEEP)
    assert s["score"] == 78 and s["bedtime"] == "22:43" and s["wake"] == "06:39"
    assert s["asleep_h"] == 7.39 and s["deep_h"] == 2.33 and s["need_h"] == 8.5
    assert s["avg_overnight_hrv_ms"] == 44 and s["rhr"] == 49
    assert T.sleep({"dailySleepDTO": {"sleepTimeSeconds": None}}) is None


def test_training_status_prefers_primary_device():
    t = T.training_status(fake.TRAINING_STATUS)
    assert t["status"] == "productive" and t["date"] == "2026-10-25"
    assert t["acute_load"] == 612 and t["chronic_load"] == 498 and t["acwr"] == 1.23
    assert t["load_target_range"] == [420, 811]
    assert t["load_focus"]["anaerobic_target"] == [90, 260]
    assert t["load_focus"]["feedback"] == "anaerobic shortage"
    assert t["vo2max"] == 47.6 and t["heat_acclimation_pct"] == 64


def test_race_predictions():
    r = T.race_predictions(fake.RACE)
    assert r["half"] == "1:55:12" and r["half_pace"] == "5:28"
    assert r["marathon"] == "4:07:00" and r["marathon_pace"] == "5:51"
    assert T.race_predictions({}) is None


def test_lactate_threshold_speed_is_tens_of_mps():
    lt = T.lactate_threshold({"speed_and_heart_rate": {"speed": 0.31944, "heartRate": 166}})
    assert lt["pace"] == "5:13" and lt["heart_rate"] == 166


def test_activity_list_row():
    a = T.activity(fake.ACTIVITY)
    assert a["km"] == 8.01 and a["moving"] == "55:10" and a["pace"] == "6:53"
    assert a["cadence_spm"] == 171 and a["stride_m"] == 0.84
    assert a["ground_contact_ms"] == 262 and a["vertical_osc_cm"] == 8.4 and a["vertical_ratio_pct"] == 9.6
    assert a["training_effect_label"] == "aerobic base" and a["training_load"] == 72
    assert a["temp_c"] == [27, 31]
    assert a["hr_zone_min"] == {"z1": 5.0, "z2": 40.0, "z3": 10.2, "z4": 0.0, "z5": 0.0}


def test_activity_detail_field_names():
    flat = {**fake.ACTIVITY_DETAIL, **fake.ACTIVITY_DETAIL["summaryDTO"], "activityType": {"typeKey": "running"}}
    a = T.activity(flat)
    assert a["type"] == "running" and a["cadence_spm"] == 171 and a["power_w"] == 241
    assert a["training_effect_aerobic"] == 2.8 and a["temp_c"] == [29, 29]


def test_laps():
    laps = T.laps(fake.SPLITS)
    assert [l["intensity"] for l in laps] == ["warmup", "active"]
    work = laps[1]
    assert work["km"] == 3.0 and work["pace"] == "5:37" and work["avg_hr"] == 163
    assert work["stride_m"] == 0.99 and work["ground_contact_ms"] == 238


def test_daily_row_tolerates_missing_parts():
    row = T.daily_row("2026-10-25", None, None, None, None, None)
    assert row["date"] == "2026-10-25" and row["readiness"] is None and row["vo2max"] is None
