import pytest
from cyclist_kb.athlete_models import (
    Athlete, TrainingPlan, TrainingBlock, PlanStatus, make_plan_id, make_athlete_id,
)


def _db(tmp_path, monkeypatch):
    from cyclist_kb.config import get_settings
    from cyclist_kb.db import Database
    s = get_settings()
    monkeypatch.setattr(s, "db_path", tmp_path / "kb.sqlite3")
    return Database()


def test_promote_plan_atomic_transition(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo"))
    v1 = TrainingPlan(id=make_plan_id(ath, 1), athlete_id=ath, version=1, status=PlanStatus.ACTIVE)
    db.save_plan(v1)
    v2 = TrainingPlan(id=make_plan_id(ath, 2), athlete_id=ath, version=2, status=PlanStatus.PROPOSED)
    db.save_plan(v2)

    promoted = db.promote_plan(v2.id)

    assert promoted.status == PlanStatus.ACTIVE
    assert db.get_plan(v1.id).status == PlanStatus.SUPERSEDED
    assert db.active_plan(ath).id == v2.id
    actives = db.list_plans(ath, status=PlanStatus.ACTIVE.value)
    assert len(actives) == 1


def test_promote_plan_rejects_non_proposed(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo"))
    v1 = TrainingPlan(id=make_plan_id(ath, 1), athlete_id=ath, version=1, status=PlanStatus.ACTIVE)
    db.save_plan(v1)
    with pytest.raises(ValueError):
        db.promote_plan(v1.id)
