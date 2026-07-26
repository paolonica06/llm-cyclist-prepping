"""Fase B — client intervals.icu: degradazione offline e normalizzazione dei payload."""

import asyncio

from cyclist_kb.athlete_models import MetricType
from cyclist_kb.clients.intervals_icu import (IntervalsClient,
                                              _build_power_curve_point,
                                              _parse_activities,
                                              _parse_activity_power_curve,
                                              _parse_daily,
                                              _parse_power_curve_list)


def test_offline_or_no_key_returns_empty():
    # Nei test KB_FORCE_OFFLINE=1 e nessuna key → il client non è disponibile.
    client = IntervalsClient()
    assert client.available is False
    assert asyncio.run(client.fetch_daily("i1")) == []
    assert asyncio.run(client.fetch_activities("i1")) == []
    assert asyncio.run(client.fetch_power_curve("i1")) == []
    assert asyncio.run(client.fetch_activity_power_curve("i1")) is None


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
               "icu_training_load": 65, "icu_intensity": 0.72, "distance": 40000}]
    acts = _parse_activities("ath1", sample)
    assert len(acts) == 1
    a = acts[0]
    assert a.date == "2026-07-20"
    assert a.load == 65
    assert a.intensity == 0.72
    assert a.external_id == "i123"


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
