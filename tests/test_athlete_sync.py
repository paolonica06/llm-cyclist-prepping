"""Fase B — morning sync: idempotenza e no-op offline (client stubbato sull'istanza)."""

import asyncio

from cyclist_kb.agents.athlete_sync import AthleteSyncAgent
from cyclist_kb.athlete_models import (ActivitySummary, Athlete, MetricType,
                                       TimeseriesPoint, make_activity_id,
                                       make_athlete_id)
from cyclist_kb.db import Database


def _db(tmp_path) -> Database:
    return Database(path=tmp_path / "kb.sqlite3")


def _athlete(db) -> Athlete:
    return db.save_athlete(Athlete(id=make_athlete_id("Paolo"), name="Paolo"))


def _stub(agent) -> None:
    async def daily(aid, oldest=None, newest=None):
        return [
            TimeseriesPoint(athlete_id=aid, metric_type=MetricType.CTL, date="2026-07-20", value=80.0),
            TimeseriesPoint(athlete_id=aid, metric_type=MetricType.TSB, date="2026-07-20", value=-8.0),
        ]

    async def acts(aid, oldest=None, newest=None):
        return [ActivitySummary(id=make_activity_id(aid, "i1"), athlete_id=aid,
                                date="2026-07-20", load=65.0, external_id="i1")]

    agent.intervals.fetch_daily = daily
    agent.intervals.fetch_activities = acts


def test_sync_persists_and_is_idempotent(tmp_path):
    db = _db(tmp_path)
    a = _athlete(db)
    agent = AthleteSyncAgent(db)
    _stub(agent)

    s1 = asyncio.run(agent.run(a.id))
    asyncio.run(agent.run(a.id))                 # secondo sync: NON duplica

    assert s1["timeseries_points"] == 2
    assert s1["activities"] == 1
    assert len(db.list_timeseries(a.id)) == 2
    assert len(db.list_activities(a.id)) == 1


def test_sync_offline_is_clean_noop(tmp_path):
    db = _db(tmp_path)
    a = _athlete(db)
    agent = AthleteSyncAgent(db)                  # client reale, offline nei test

    summary = asyncio.run(agent.run(a.id))
    assert summary["available"] is False
    assert summary["timeseries_points"] == 0
    assert summary["activities"] == 0
    assert summary["power_curve_points"] == 0
    assert summary["races"] == 0
    assert summary["planned_workouts"] == 0
    assert db.list_timeseries(a.id) == []
    assert db.list_activities(a.id) == []
    assert db.list_races(a.id) == []
    assert db.list_planned_workouts(a.id) == []


def test_sync_ingests_races_and_planned_from_calendar(tmp_path):
    from cyclist_kb.athlete_models import Race, RacePriority, make_race_id

    db = _db(tmp_path)
    a = _athlete(db)
    agent = AthleteSyncAgent(db)

    async def daily(aid, oldest=None, newest=None):
        return []

    async def acts(aid, oldest=None, newest=None):
        return []

    async def curve(aid, **kw):
        return []

    async def events(aid, oldest=None, newest=None):
        race = Race(id=make_race_id(aid, "Zanè Monte Cengio", "2026-08-01"),
                    athlete_id=aid, name="Zanè Monte Cengio", date="2026-08-01",
                    priority=RacePriority.B)
        workout = {"external_id": "99", "date": "2026-07-28", "name": "TEST CP",
                   "type": "Ride", "load_target": 82}
        return [race], [workout]

    agent.intervals.fetch_daily = daily
    agent.intervals.fetch_activities = acts
    agent.intervals.fetch_power_curve = curve
    agent.intervals.fetch_events = events

    s = asyncio.run(agent.run(a.id))
    asyncio.run(agent.run(a.id))                  # idempotente: NON duplica

    assert s["races"] == 1 and s["planned_workouts"] == 1
    assert len(db.list_races(a.id)) == 1
    assert db.list_races(a.id)[0].priority == RacePriority.B
    planned = db.list_planned_workouts(a.id)
    assert len(planned) == 1 and planned[0]["load_target"] == 82


def test_sync_ingests_power_curve(tmp_path):
    db = _db(tmp_path)
    a = _athlete(db)
    agent = AthleteSyncAgent(db)

    async def daily(aid, oldest=None, newest=None):
        return []

    async def acts(aid, oldest=None, newest=None):
        return []

    async def curve(aid, **kw):
        return [TimeseriesPoint(
            athlete_id=aid, metric_type=MetricType.POWER_CURVE, date="2026-07-27",
            value=None, extra={"as_of": "2026-07-27", "periods": {
                "42 days": {"secs_watts": {"1200": 291}},
                "All time": {"secs_watts": {"1200": 342}},
            }})]

    agent.intervals.fetch_daily = daily
    agent.intervals.fetch_activities = acts
    agent.intervals.fetch_power_curve = curve

    s = asyncio.run(agent.run(a.id))
    asyncio.run(agent.run(a.id))                  # secondo sync: NON duplica (upsert)

    assert s["power_curve_points"] == 1
    pts = db.list_timeseries(a.id, MetricType.POWER_CURVE.value)
    assert len(pts) == 1
    assert pts[0].value is None
    assert pts[0].extra["periods"]["All time"]["secs_watts"]["1200"] == 342
    assert pts[0].extra["periods"]["42 days"]["secs_watts"]["1200"] == 291


def test_backfill_activity_power_curves(tmp_path):
    db = _db(tmp_path)
    a = _athlete(db)
    # 1 Ride + 1 VirtualRide (candidati), 1 Run e 1 stub senza tipo (da ignorare).
    db.save_activity(ActivitySummary(id=make_activity_id(a.id, "i1"), athlete_id=a.id,
                                     date="2026-07-20", type="Ride", external_id="i1"))
    db.save_activity(ActivitySummary(id=make_activity_id(a.id, "i2"), athlete_id=a.id,
                                     date="2026-07-21", type="VirtualRide", external_id="i2"))
    db.save_activity(ActivitySummary(id=make_activity_id(a.id, "i3"), athlete_id=a.id,
                                     date="2026-07-22", type="Run", external_id="i3"))
    db.save_activity(ActivitySummary(id=make_activity_id(a.id, "s9"), athlete_id=a.id,
                                     date="2026-07-19", type=None, external_id="9001"))
    agent = AthleteSyncAgent(db)

    async def apc(external_id):
        return {"secs_watts": {"300": 360}} if external_id in ("i1", "i2") else None

    agent.intervals.fetch_activity_power_curve = apc

    s = asyncio.run(agent.backfill_activity_power_curves(a.id))
    assert s["candidates"] == 2                   # solo Ride + VirtualRide
    assert s["fetched"] == 2
    got = db.get_activity_power_curve(make_activity_id(a.id, "i1"))
    assert got["secs_watts"]["300"] == 360

    s2 = asyncio.run(agent.backfill_activity_power_curves(a.id))   # incrementale
    assert s2["fetched"] == 0 and s2["skipped"] == 2


def test_backfill_activity_intervals(tmp_path):
    db = _db(tmp_path)
    a = _athlete(db)
    # 1 Ride + 1 VirtualRide (candidati), 1 Run (da ignorare).
    db.save_activity(ActivitySummary(id=make_activity_id(a.id, "i1"), athlete_id=a.id,
                                     date="2026-07-20", type="Ride", external_id="i1"))
    db.save_activity(ActivitySummary(id=make_activity_id(a.id, "i2"), athlete_id=a.id,
                                     date="2026-07-21", type="VirtualRide", external_id="i2"))
    db.save_activity(ActivitySummary(id=make_activity_id(a.id, "i3"), athlete_id=a.id,
                                     date="2026-07-22", type="Run", external_id="i3"))
    agent = AthleteSyncAgent(db)

    async def laps(external_id):
        return [{"index": 0, "avg_watts": 300}] if external_id in ("i1", "i2") else None

    agent.intervals.fetch_activity_intervals = laps

    s = asyncio.run(agent.backfill_activity_intervals(a.id))
    assert s["candidates"] == 2                   # solo Ride + VirtualRide
    assert s["fetched"] == 2
    got = db.get_activity_intervals(make_activity_id(a.id, "i1"))
    assert got[0]["avg_watts"] == 300

    s2 = asyncio.run(agent.backfill_activity_intervals(a.id))   # incrementale
    assert s2["fetched"] == 0 and s2["skipped"] == 2


def test_sync_second_run_adds_new_point_without_duplicating(tmp_path):
    db = _db(tmp_path)
    a = _athlete(db)
    agent = AthleteSyncAgent(db)

    calls = {"n": 0}

    async def daily(aid, oldest=None, newest=None):
        calls["n"] += 1
        pts = [TimeseriesPoint(athlete_id=aid, metric_type=MetricType.CTL,
                               date="2026-07-20", value=80.0)]
        if calls["n"] >= 2:                       # secondo sync: un punto NUOVO (data diversa)
            pts.append(TimeseriesPoint(athlete_id=aid, metric_type=MetricType.CTL,
                                       date="2026-07-21", value=82.0))
        return pts

    async def acts(aid, oldest=None, newest=None):
        return []

    agent.intervals.fetch_daily = daily
    agent.intervals.fetch_activities = acts

    asyncio.run(agent.run(a.id))
    asyncio.run(agent.run(a.id))
    points = db.list_timeseries(a.id, MetricType.CTL.value)
    assert [p.date for p in points] == ["2026-07-20", "2026-07-21"]   # aggiunto, non duplicato
