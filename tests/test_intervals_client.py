"""Fase B — client intervals.icu: degradazione offline e normalizzazione dei payload."""

import asyncio

from cyclist_kb.athlete_models import MetricType, RacePriority
from cyclist_kb.clients.base import WriteResult
from cyclist_kb.clients.intervals_icu import (IntervalsClient,
                                              _build_power_curve_point,
                                              _parse_activities,
                                              _parse_activity_intervals,
                                              _parse_activity_power_curve,
                                              _parse_activity_streams,
                                              _parse_daily, _parse_events,
                                              _parse_power_curve_list)


def test_offline_or_no_key_returns_empty():
    # Nei test KB_FORCE_OFFLINE=1 e nessuna key → il client non è disponibile.
    client = IntervalsClient()
    assert client.available is False
    assert asyncio.run(client.fetch_daily("i1")) == []
    assert asyncio.run(client.fetch_activities("i1")) == []
    assert asyncio.run(client.fetch_power_curve("i1")) == []
    assert asyncio.run(client.fetch_activity_power_curve("i1")) is None
    assert asyncio.run(client.fetch_activity_intervals("i1")) is None
    assert asyncio.run(client.fetch_activity_streams("i1")) is None
    assert asyncio.run(client.fetch_sport_settings("i1")) is None
    assert asyncio.run(client.fetch_events("i1")) == ([], [])


def test_parse_daily_maps_wellness_and_derives_tsb():
    # Payload reale: NESSUN campo 'form'; la TSB si deriva dall'identità CTL - ATL.
    sample = [{"id": "2026-07-20", "ctl": 80.0, "atl": 90.0,
               "hrv": 62, "restingHR": 45, "weight": 70.5, "sleepSecs": 27000}]
    points = _parse_daily("ath1", sample)
    by_metric = {p.metric_type: p.value for p in points}
    assert by_metric[MetricType.CTL] == 80.0
    assert by_metric[MetricType.ATL] == 90.0
    assert by_metric[MetricType.TSB] == -10.0        # derivata: 80 - 90
    assert by_metric[MetricType.HRV] == 62.0
    assert by_metric[MetricType.RESTING_HR] == 45.0
    assert by_metric[MetricType.WEIGHT] == 70.5
    assert all(p.date == "2026-07-20" for p in points)


def test_parse_daily_maps_readiness_ramprate_vo2max():
    # readiness/rampRate/vo2max: esposti dal payload /wellness, ora ingeriti dal
    # loop generico (prima dichiarati nel modello ma non mappati).
    sample = [{"id": "2026-07-26", "readiness": 78, "rampRate": 5.4, "vo2max": 61.2}]
    points = _parse_daily("ath1", sample)
    by_metric = {p.metric_type: p.value for p in points}
    assert by_metric[MetricType.READINESS] == 78.0
    assert by_metric[MetricType.RAMP_RATE] == 5.4
    assert by_metric[MetricType.VO2MAX] == 61.2


def test_tsb_requires_both_ctl_and_atl():
    points = _parse_daily("ath1", [{"id": "2026-07-21", "ctl": 81.0}])   # manca ATL
    metrics = {p.metric_type for p in points}
    assert MetricType.CTL in metrics
    assert MetricType.TSB not in metrics


def test_parse_daily_skips_missing_fields_and_bad_dates():
    sample = [{"id": "2026-07-21", "ctl": 81.0},   # solo ctl → 1 punto
              {"ctl": 99.0}]                        # nessuna data → scartato
    points = _parse_daily("ath1", sample)
    assert len(points) == 1
    assert points[0].metric_type == MetricType.CTL
    assert points[0].value == 81.0


def test_parse_activities_maps_fields():
    sample = [{"id": "i123", "start_date_local": "2026-07-20T09:00:00",
               "type": "Ride", "name": "Z2", "moving_time": 3600,
               "icu_training_load": 65, "icu_intensity": 0.72, "distance": 40000,
               "icu_average_watts": 210,
               "average_heartrate": 142, "max_heartrate": 178}]
    acts = _parse_activities("ath1", sample)
    assert len(acts) == 1
    a = acts[0]
    assert a.date == "2026-07-20"
    assert a.load == 65
    assert a.intensity == 0.72
    assert a.external_id == "i123"
    assert a.avg_power == 210
    assert a.avg_hr == 142
    assert a.max_hr == 178


def test_parse_activities_missing_power_hr_are_none():
    # Gara/uscita senza power meter o cardio attivo: i campi restano assenti, non 0.
    sample = [{"id": "i124", "start_date_local": "2026-08-01T09:00:00",
               "type": "Ride", "name": "Gara", "moving_time": 10801,
               "icu_training_load": 206, "icu_intensity": 0.829}]
    a = _parse_activities("ath1", sample)[0]
    assert a.avg_power is None
    assert a.avg_hr is None
    assert a.max_hr is None


def test_parse_empty_payloads_are_empty():
    assert _parse_daily("a", None) == []
    assert _parse_activities("a", []) == []


def test_parse_power_curve_list_maps_periods_and_wkg():
    # Payload reale di /athlete/{id}/power-curves?curves=42d,all: {list:[curva...], ...}.
    sample = {
        "list": [
            {"label": "42 days", "start_date_local": "2026-06-15T00:00:00",
             "end_date_local": "2026-07-27T00:00:00", "days": 43,
             "secs": [1, 300, 1200], "values": [1200, 395, 318],
             "watts_per_kg": [16.5, 5.35, 4.31]},
            {"label": "All time", "start_date_local": "1986-01-01T00:00:00",
             "end_date_local": "2026-07-27T00:00:00", "days": 859,
             "secs": [1, 300, 1200], "values": [1315, 402, 323],
             "watts_per_kg": [17.8, 5.48, 4.48]},
        ],
        "activities": {"i1": {"name": "Bici"}},
    }
    curves = _parse_power_curve_list(sample)
    assert set(curves) == {"42 days", "All time"}
    assert curves["All time"]["secs_watts"]["1200"] == 323    # PB assoluto 20min
    assert curves["42 days"]["secs_watts"]["1200"] == 318     # 20min recente (< assoluto)
    assert curves["All time"]["watts_per_kg"]["300"] == 5.48
    assert curves["42 days"]["days"] == 43
    assert curves["All time"]["end"] == "2026-07-27T00:00:00"


def test_parse_power_curve_list_empty():
    assert _parse_power_curve_list(None) == {}
    assert _parse_power_curve_list({"list": []}) == {}
    assert _parse_power_curve_list({"list": [{"label": "x"}]}) == {}   # no secs/values


def test_build_power_curve_point_packs_periods_and_dates_as_of():
    periods = {
        "42 days": {"secs_watts": {"1200": 291}, "end": "2026-07-26T00:00:00"},
        "All time": {"secs_watts": {"1200": 342}, "end": "2026-07-27T00:00:00"},
    }
    p = _build_power_curve_point("ath1", periods)
    assert p.metric_type == MetricType.POWER_CURVE
    assert p.date == "2026-07-27"          # as-of = fine periodo più recente
    assert p.value is None
    assert p.extra["periods"]["All time"]["secs_watts"]["1200"] == 342   # PB assoluto
    assert p.extra["periods"]["42 days"]["secs_watts"]["1200"] == 291     # recente


def test_build_power_curve_point_empty_is_none():
    assert _build_power_curve_point("a", {}) is None


def test_parse_activity_power_curve():
    data = {"secs": [1, 2, 300], "values": [586, 580, 360],
            "watts_per_kg": [7.76, 7.68, 4.86]}
    c = _parse_activity_power_curve(data)
    assert c["secs_watts"]["1"] == 586
    assert c["secs_watts"]["300"] == 360
    assert c["watts_per_kg"]["2"] == 7.68


def test_parse_activity_power_curve_empty_is_none():
    assert _parse_activity_power_curve(None) is None
    assert _parse_activity_power_curve({"secs": [], "values": []}) is None
    assert _parse_activity_power_curve({"secs": [1, 2], "values": [None, None]}) is None


def test_parse_activity_intervals_maps_fields():
    data = {"id": "i1", "icu_intervals": [
        {"type": "RECOVERY", "label": None, "start_time": 0, "end_time": 1791,
         "moving_time": 1791, "average_watts": 187, "weighted_average_watts": 194,
         "max_watts": 296, "average_heartrate": 125, "max_heartrate": 143,
         "average_cadence": 78.5, "intensity": 60, "training_load": 15.5, "zone": 2},
        {"type": "WORK", "label": None, "start_time": 1791, "end_time": 2685,
         "moving_time": 894, "average_watts": 295, "weighted_average_watts": 298,
         "max_watts": 343, "average_heartrate": 148, "max_heartrate": 160,
         "average_cadence": 88.0, "intensity": 95, "training_load": 22.1, "zone": 4},
    ]}
    laps = _parse_activity_intervals(data)
    assert len(laps) == 2
    first, second = laps
    assert first["index"] == 0
    assert first["type"] == "RECOVERY"
    assert first["duration_s"] == 1791
    assert first["avg_watts"] == 187
    assert first["weighted_avg_watts"] == 194
    assert first["max_watts"] == 296
    assert first["avg_hr"] == 125
    assert first["max_hr"] == 143
    assert first["avg_cadence"] == 78.5
    assert first["intensity"] == 60
    assert first["training_load"] == 15.5
    assert first["zone"] == 2
    assert second["index"] == 1
    assert second["avg_watts"] == 295


def test_parse_activity_intervals_empty_is_none():
    assert _parse_activity_intervals(None) is None
    assert _parse_activity_intervals({}) is None
    assert _parse_activity_intervals({"icu_intervals": []}) is None


def test_parse_activity_streams_maps_fields():
    data = [
        {"type": "time", "data": [0, 1, 2]},
        {"type": "watts", "data": [200, 210, 220]},
        {"type": "heartrate", "data": [140, 141, 142]},
    ]
    streams = _parse_activity_streams(data)
    assert streams["time"] == [0, 1, 2]
    assert streams["watts"] == [200, 210, 220]
    assert streams["heartrate"] == [140, 141, 142]


def test_parse_activity_streams_empty_is_none():
    assert _parse_activity_streams(None) is None
    assert _parse_activity_streams([]) is None
    assert _parse_activity_streams([{"type": "watts", "data": []}]) is None


def test_parse_events_splits_races_and_workouts():
    data = [
        {"id": 1, "start_date_local": "2026-08-01T00:00:00", "category": "RACE_B",
         "type": "Ride", "name": "Zanè Monte Cengio", "description": "gara-allenamento"},
        {"id": 2, "start_date_local": "2026-07-28T00:00:00", "category": "WORKOUT",
         "type": "Ride", "name": "TEST CP 3+12", "load_target": 82, "moving_time": 5340,
         "description": "- 3m 380-430W"},
        {"id": 3, "start_date_local": "2026-07-27T00:00:00", "category": "NOTE",
         "name": "nota, ignorata"},
        {"id": 4, "category": "WORKOUT", "name": "senza data → scartato"},
    ]
    races, planned = _parse_events("i1", data)
    assert len(races) == 1
    assert races[0].priority == RacePriority.B
    assert races[0].name == "Zanè Monte Cengio"
    assert races[0].date == "2026-08-01"
    assert len(planned) == 1                       # NOTE ignorata, senza-data scartato
    assert planned[0]["external_id"] == "2"
    assert planned[0]["load_target"] == 82
    assert planned[0]["date"] == "2026-07-28"


def test_create_event_offline_returns_error():
    client = IntervalsClient()
    result = asyncio.run(client.create_event("i1", {"name": "x"}))
    assert result.ok is False
    assert result.error


def test_create_event_posts_payload(monkeypatch):
    monkeypatch.setattr(IntervalsClient, "available", property(lambda self: True))
    client = IntervalsClient()
    client._api_key = "test-key"

    calls = []

    class FakeFetcher:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def send_json(self, method, url, payload, headers=None):
            calls.append((method, url, payload))
            return WriteResult(ok=True, status=200, body={"id": 999})

    client._fetcher = FakeFetcher()
    event = {"category": "WORKOUT", "start_date_local": "2026-08-05T07:00:00",
              "type": "Ride", "name": "Test", "description": "d", "moving_time": 1800}
    result = asyncio.run(client.create_event("i215294", event))
    assert result.ok is True
    assert result.body == {"id": 999}
    method, url, payload = calls[0]
    assert method == "POST"
    assert url == "https://intervals.icu/api/v1/athlete/i215294/events"
    assert payload == event


def test_update_sport_settings_offline_returns_error():
    client = IntervalsClient()
    result = asyncio.run(client.update_sport_settings("i1", "Ride", {"ftp": 318}))
    assert result.ok is False
    assert result.error


def test_update_sport_settings_puts_payload(monkeypatch):
    monkeypatch.setattr(IntervalsClient, "available", property(lambda self: True))
    client = IntervalsClient()
    client._api_key = "test-key"

    calls = []

    class FakeFetcher:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def send_json(self, method, url, payload, headers=None):
            calls.append((method, url, payload))
            return WriteResult(ok=True, status=200, body=payload)

    client._fetcher = FakeFetcher()
    settings = {"ftp": 318, "w_prime": 25321, "power_zones": [55, 75, 90, 105, 120, 150, 999]}
    result = asyncio.run(client.update_sport_settings("i215294", "Ride", settings))
    assert result.ok is True
    method, url, payload = calls[0]
    assert method == "PUT"
    assert url == "https://intervals.icu/api/v1/athlete/i215294/sport-settings/Ride"
    assert payload == settings


def test_parse_events_priority_mapping_and_empty():
    assert _parse_events("a", None) == ([], [])
    assert _parse_events("a", []) == ([], [])
    data = [{"id": i, "start_date_local": "2026-01-01T00:00:00", "category": c, "name": c}
            for i, c in enumerate(["RACE_A", "RACE_C"])]
    races, _ = _parse_events("a", data)
    prio = {r.name: r.priority for r in races}
    assert prio["RACE_A"] == RacePriority.A
    assert prio["RACE_C"] == RacePriority.C
