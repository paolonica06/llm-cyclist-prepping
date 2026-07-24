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
    assert db.list_timeseries(a.id) == []
    assert db.list_activities(a.id) == []
