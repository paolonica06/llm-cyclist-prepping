"""Fase B — client intervals.icu: degradazione offline e normalizzazione dei payload."""

import asyncio

from cyclist_kb.athlete_models import MetricType
from cyclist_kb.clients.intervals_icu import (IntervalsClient, _parse_activities,
                                              _parse_daily)


def test_offline_or_no_key_returns_empty():
    # Nei test KB_FORCE_OFFLINE=1 e nessuna key → il client non è disponibile.
    client = IntervalsClient()
    assert client.available is False
    assert asyncio.run(client.fetch_daily("i1")) == []
    assert asyncio.run(client.fetch_activities("i1")) == []


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
