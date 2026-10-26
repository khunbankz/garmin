"""A stand-in for garminconnect.Garmin with payloads shaped like Garmin's.

Used by the unit tests directly and by the end-to-end test through
GARMIN_MCP_FAKE=tests.fake:FakeGarmin.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

TODAY = date(2026, 10, 25)

READINESS = [
    {
        "calendarDate": "2026-10-25",
        "timestampLocal": "2026-10-25T13:10:00.0",
        "score": 61,
        "level": "MODERATE",
        "inputContext": "UPDATE_REALTIME_VARIABLES",
    },
    {
        "calendarDate": "2026-10-25",
        "timestampLocal": "2026-10-25T06:41:00.0",
        "score": 72,
        "level": "HIGH",
        "feedbackShort": "WELL_RECOVERED",
        "sleepScore": 78,
        "sleepScoreFactorPercent": 76,
        "sleepScoreFactorFeedback": "GOOD",
        "recoveryTime": 420,
        "recoveryTimeFactorPercent": 70,
        "recoveryTimeFactorFeedback": "MODERATE",
        "acwrFactorPercent": 88,
        "acwrFactorFeedback": "VERY_GOOD",
        "acuteLoad": 612,
        "stressHistoryFactorPercent": 80,
        "stressHistoryFactorFeedback": "GOOD",
        "hrvFactorPercent": 75,
        "hrvFactorFeedback": "GOOD",
        "hrvWeeklyAverage": 41,
        "sleepHistoryFactorPercent": 40,
        "sleepHistoryFactorFeedback": "POOR",
        "inputContext": "AFTER_WAKEUP_RESET",
    },
]

READINESS_RANGE = READINESS + [
    {
        "calendarDate": "2026-10-24",
        "timestampLocal": "2026-10-24T03:45:00.0",
        "score": 48,
        "level": "LOW",
        "inputContext": "AFTER_WAKEUP_RESET",
    }
]

HRV_SUMMARY = {
    "calendarDate": "2026-10-25",
    "weeklyAvg": 41,
    "lastNightAvg": 44,
    "lastNight5MinHigh": 63,
    "baseline": {"lowUpper": 33, "balancedLow": 36, "balancedUpper": 48, "markerValue": 0.5},
    "status": "BALANCED",
    "feedbackPhrase": "HRV_BALANCED_2",
}

SLEEP = {
    "dailySleepDTO": {
        "calendarDate": "2026-10-25",
        "sleepTimeSeconds": 26604,
        "deepSleepSeconds": 8388,
        "lightSleepSeconds": 11340,
        "remSleepSeconds": 6876,
        "awakeSleepSeconds": 1980,
        # 22:43 and 06:39 local, stored as epoch-ms of local wall time.
        "sleepStartTimestampLocal": 1792881780000,
        "sleepEndTimestampLocal": 1792910340000,
        "averageRespirationValue": 15.4,
        "avgSleepStress": 14.2,
        "sleepScores": {"overall": {"value": 78, "qualifierKey": "FAIR"}},
        "sleepNeed": {"baseline": 480, "actual": 510},
    },
    "restingHeartRate": 49,
    "avgOvernightHrv": 44,
    "bodyBatteryChange": 52,
}

USER_SUMMARY = {
    "calendarDate": "2026-10-25",
    "restingHeartRate": 49,
    "lastSevenDaysAvgRestingHeartRate": 51,
    "bodyBatteryAtWakeTime": 81,
    "bodyBatteryHighestValue": 83,
    "bodyBatteryLowestValue": 34,
    "bodyBatteryMostRecentValue": 55,
    "bodyBatteryChargedValue": 52,
    "bodyBatteryDrainedValue": 40,
    "averageStressLevel": 27,
    "totalSteps": 8123,
    "activeKilocalories": 612.4,
}

TRAINING_STATUS = {
    "mostRecentVO2Max": {
        "generic": {"calendarDate": "2026-10-24", "vo2MaxPreciseValue": 47.6, "vo2MaxValue": 48, "fitnessAge": 33},
        "heatAltitudeAcclimation": {"heatAcclimationPercentage": 64},
    },
    "mostRecentTrainingLoadBalance": {
        "metricsTrainingLoadBalanceDTOMap": {
            "3444000001": {
                "calendarDate": "2026-10-25",
                "monthlyLoadAerobicLow": 410.2,
                "monthlyLoadAerobicHigh": 380.9,
                "monthlyLoadAnaerobic": 35.1,
                "monthlyLoadAerobicLowTargetMin": 300,
                "monthlyLoadAerobicLowTargetMax": 620,
                "monthlyLoadAerobicHighTargetMin": 320,
                "monthlyLoadAerobicHighTargetMax": 640,
                "monthlyLoadAnaerobicTargetMin": 90,
                "monthlyLoadAnaerobicTargetMax": 260,
                "trainingBalanceFeedbackPhrase": "ANAEROBIC_SHORTAGE",
                "primaryTrainingDevice": True,
            }
        }
    },
    "mostRecentTrainingStatus": {
        "latestTrainingStatusData": {
            "1111": {"calendarDate": "2026-09-01", "trainingStatusFeedbackPhrase": "DETRAINING_1", "primaryTrainingDevice": False},
            "3444000001": {
                "calendarDate": "2026-10-25",
                "trainingStatus": 7,
                "trainingStatusFeedbackPhrase": "PRODUCTIVE_3",
                "weeklyTrainingLoad": 702.4,
                "loadTunnelMin": 420.1,
                "loadTunnelMax": 810.7,
                "fitnessTrend": 2,
                "acuteTrainingLoadDTO": {
                    "acwrPercent": 62,
                    "acwrStatus": "OPTIMAL",
                    "dailyTrainingLoadAcute": 612,
                    "dailyTrainingLoadChronic": 498,
                    "maxTrainingLoadChronic": 747,
                    "minTrainingLoadChronic": 398,
                    "dailyAcuteChronicWorkloadRatio": 1.2289,
                },
                "primaryTrainingDevice": True,
            },
        }
    },
}

RACE = {"calendarDate": "2026-10-25", "time5K": 1478, "time10K": 3101, "timeHalfMarathon": 6912, "timeMarathon": 14820}

ACTIVITY = {
    "activityId": 20712345678,
    "activityName": "Bangkok - Easy",
    "startTimeLocal": "2026-10-25 05:31:02",
    "activityType": {"typeKey": "running"},
    "distance": 8012.3,
    "duration": 3350.2,
    "movingDuration": 3310.0,
    "elapsedDuration": 3391.0,
    "averageSpeed": 2.39,
    "avgGradeAdjustedSpeed": 2.41,
    "averageHR": 138.4,
    "maxHR": 149.0,
    "averageRunningCadenceInStepsPerMinute": 171.3,
    "avgStrideLength": 83.7,
    "avgGroundContactTime": 262.1,
    "avgVerticalOscillation": 8.43,
    "avgVerticalRatio": 9.6,
    "avgPower": 241.0,
    "normPower": 246.0,
    "aerobicTrainingEffect": 2.8,
    "anaerobicTrainingEffect": 0.2,
    "trainingEffectLabel": "AEROBIC_BASE",
    "activityTrainingLoad": 71.6,
    "minTemperature": 27.0,
    "maxTemperature": 31.0,
    "elevationGain": 12.0,
    "differenceBodyBattery": -12,
    "calories": 512.0,
    "hrTimeInZone_1": 300.0,
    "hrTimeInZone_2": 2400.0,
    "hrTimeInZone_3": 610.0,
    "hrTimeInZone_4": 0.0,
    "hrTimeInZone_5": 0.0,
    "lapCount": 9,
}

ACTIVITY_DETAIL = {
    "activityId": 20712345678,
    "activityName": "Bangkok - Easy",
    "activityTypeDTO": {"typeKey": "running"},
    "summaryDTO": {
        "startTimeLocal": "2026-10-25T05:31:02.0",
        "distance": 8012.3,
        "duration": 3350.2,
        "movingDuration": 3310.0,
        "averageHR": 138.4,
        "averageRunCadence": 171.3,
        "strideLength": 83.7,
        "groundContactTime": 262.1,
        "verticalOscillation": 8.43,
        "verticalRatio": 9.6,
        "averagePower": 241.0,
        "trainingEffect": 2.8,
        "anaerobicTrainingEffect": 0.2,
        "activityTrainingLoad": 71.6,
        "averageTemperature": 29.0,
    },
}

SPLITS = {
    "activityId": 20712345678,
    "lapDTOs": [
        {"lapIndex": 1, "intensityType": "WARMUP", "distance": 2000.0, "duration": 860.0, "movingDuration": 850.0,
         "averageHR": 131.0, "maxHR": 139.0, "averageRunCadence": 168.0, "strideLength": 81.0,
         "groundContactTime": 268.0, "verticalOscillation": 8.5, "verticalRatio": 9.9, "averagePower": 232.0},
        {"lapIndex": 2, "intensityType": "ACTIVE", "distance": 3000.0, "duration": 1013.0, "movingDuration": 1011.0,
         "averageHR": 163.0, "maxHR": 168.0, "averageRunCadence": 179.0, "strideLength": 99.2,
         "groundContactTime": 238.0, "verticalOscillation": 8.9, "verticalRatio": 8.6, "averagePower": 298.0},
    ],
}


class _Client:
    def __init__(self) -> None:
        self.loads = 0

    def load(self, path: str) -> None:
        self.loads += 1

    def dump(self, path: str) -> None:
        pass


class FakeGarmin:
    """Answers every call with the payloads above (for any date)."""

    def __init__(self, email: str | None = None, password: str | None = None, **_: Any) -> None:
        self.client = _Client()
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.full_name = "Test Runner"
        self.display_name = "test-runner"
        self.fail: dict[str, BaseException] = {}
        self.logins = 0
        # An in-memory workout library and calendar, with one workout the user
        # made in the app (no garmin-mcp marker), scheduled on 28 Oct.
        self.workouts: dict[int, dict[str, Any]] = {
            77: {"workoutId": 77, "workoutName": "My own intervals", "description": None,
                 "sportType": {"sportTypeId": 1, "sportTypeKey": "running"}, "workoutSegments": []}
        }
        self.schedules: dict[int, dict[str, Any]] = {
            500: {"workoutScheduleId": 500, "calendarDate": "2026-10-28", "workout": {"workoutId": 77}}
        }
        self._next_id = 1000

    def _rec(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        if name in self.fail:
            raise self.fail[name]

    def login(self, tokenstore: str | None = None) -> tuple[None, None]:
        self.logins += 1
        return None, None

    def today(self) -> date:
        return TODAY

    def get_full_name(self) -> str:
        return self.full_name

    def get_training_readiness(self, d: str) -> list[dict[str, Any]]:
        self._rec("get_training_readiness", d)
        return copy.deepcopy(READINESS)

    def get_training_readiness_range(self, s: str, e: str) -> list[dict[str, Any]]:
        self._rec("get_training_readiness_range", s, e)
        return copy.deepcopy(READINESS_RANGE)

    def get_hrv_data(self, d: str) -> dict[str, Any]:
        self._rec("get_hrv_data", d)
        return {"hrvSummary": copy.deepcopy(HRV_SUMMARY), "hrvReadings": [{"hrvValue": 40}] * 50}

    def get_hrv_data_range(self, s: str, e: str) -> dict[str, Any]:
        self._rec("get_hrv_data_range", s, e)
        prev = {**HRV_SUMMARY, "calendarDate": "2026-10-24", "lastNightAvg": 35, "status": "UNBALANCED"}
        return {"hrvSummaries": [copy.deepcopy(HRV_SUMMARY), prev]}

    def get_sleep_data(self, d: str) -> dict[str, Any]:
        self._rec("get_sleep_data", d)
        out = copy.deepcopy(SLEEP)
        out["dailySleepDTO"]["calendarDate"] = d
        return out

    def get_user_summary(self, d: str) -> dict[str, Any]:
        self._rec("get_user_summary", d)
        return {**USER_SUMMARY, "calendarDate": d}

    def get_daily_summaries(self, s: str, e: str) -> dict[str, Any]:
        self._rec("get_daily_summaries", s, e)
        return {"data": [{**USER_SUMMARY, "calendarDate": s}]}

    def get_training_status(self, d: str) -> dict[str, Any]:
        self._rec("get_training_status", d)
        return copy.deepcopy(TRAINING_STATUS)

    def get_race_predictions(self, s: str | None = None, e: str | None = None, _type: str | None = None) -> Any:
        self._rec("get_race_predictions", s, e, _type)
        if _type:
            return [{**RACE, "calendarDate": "2026-10-24", "timeMarathon": 14900}, dict(RACE)]
        return dict(RACE)

    def get_max_metrics(self, d: str) -> list[dict[str, Any]]:
        self._rec("get_max_metrics", d)
        return [{"generic": None}]

    def get_max_metrics_range(self, s: str, e: str) -> list[dict[str, Any]]:
        self._rec("get_max_metrics_range", s, e)
        return [{"generic": {"calendarDate": "2026-10-24", "vo2MaxPreciseValue": 47.2}}]

    def get_lactate_threshold(self, *, latest: bool = True) -> dict[str, Any]:
        self._rec("get_lactate_threshold")
        return {"speed_and_heart_rate": {"calendarDate": "2026-10-20", "speed": 0.31944, "heartRate": 166}, "power": {}}

    def get_activities_by_date(self, s: str, e: str | None = None, activitytype: str | None = None, sortorder: str | None = None) -> list[dict[str, Any]]:
        self._rec("get_activities_by_date", s, e, activitytype, sortorder)
        return [copy.deepcopy(ACTIVITY)]

    def get_activity(self, activity_id: str) -> dict[str, Any]:
        self._rec("get_activity", activity_id)
        return copy.deepcopy(ACTIVITY_DETAIL)

    def get_activity_splits(self, activity_id: str) -> dict[str, Any]:
        self._rec("get_activity_splits", activity_id)
        return copy.deepcopy(SPLITS)

    def get_devices(self) -> list[dict[str, Any]]:
        self._rec("get_devices")
        return [{"productDisplayName": "Forerunner"}]

    # ---- workouts ----

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def upload_workout(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._rec("upload_workout", payload)
        wid = self._new_id()
        self.workouts[wid] = {**copy.deepcopy(payload), "workoutId": wid, "createdDate": "2026-10-26T14:00:00.0"}
        return copy.deepcopy(self.workouts[wid])

    def get_workouts(self, start: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        self._rec("get_workouts", start, limit)
        return [copy.deepcopy(w) for w in reversed(self.workouts.values())][start : start + limit]

    def get_workout_by_id(self, workout_id: Any) -> dict[str, Any]:
        self._rec("get_workout_by_id", workout_id)
        return copy.deepcopy(self.workouts[int(workout_id)])

    def delete_workout(self, workout_id: Any) -> None:
        self._rec("delete_workout", workout_id)
        wid = int(workout_id)
        del self.workouts[wid]
        self.schedules = {k: v for k, v in self.schedules.items() if v["workout"]["workoutId"] != wid}

    def schedule_workout(self, workout_id: Any, date_str: str) -> dict[str, Any]:
        self._rec("schedule_workout", workout_id, date_str)
        sid = self._new_id()
        self.schedules[sid] = {"workoutScheduleId": sid, "calendarDate": date_str,
                               "workout": {"workoutId": int(workout_id)}}
        return copy.deepcopy(self.schedules[sid])

    def get_scheduled_workout_by_id(self, schedule_id: Any) -> dict[str, Any]:
        self._rec("get_scheduled_workout_by_id", schedule_id)
        return copy.deepcopy(self.schedules[int(schedule_id)])

    def unschedule_workout(self, schedule_id: Any) -> None:
        self._rec("unschedule_workout", schedule_id)
        del self.schedules[int(schedule_id)]

    def get_scheduled_workouts(self, year: int, month: int) -> dict[str, Any]:
        self._rec("get_scheduled_workouts", year, month)
        prefix = f"{year}-{month:02d}-"
        items: list[dict[str, Any]] = [
            {"id": 9, "itemType": "activity", "date": f"{prefix}05", "title": "Morning Run"}
        ]
        # Like Garmin's month grid: the first week of the next month shows too.
        nxt = f"{year + month // 12}-{month % 12 + 1:02d}-0"
        for sid, sch in self.schedules.items():
            if sch["calendarDate"].startswith(prefix) or sch["calendarDate"].startswith(nxt):
                wid = sch["workout"]["workoutId"]
                items.append({"id": sid, "itemType": "workout", "date": sch["calendarDate"],
                              "title": self.workouts[wid]["workoutName"], "workoutId": wid})
        return {"startDate": f"{prefix}01", "calendarItems": items}
