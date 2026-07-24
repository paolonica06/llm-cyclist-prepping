import pytest
from cyclist_kb.athlete_models import (
    Athlete, TrainingBlock, TrainingPlan, PlanStatus, make_block_id,
    make_plan_id, make_athlete_id,
    Assessment, AssessmentProtocol, MetricGoal, MetricType, make_assessment_id,
)
from cyclist_kb.pipeline import Pipeline, PlanNotFound, PlanStateError


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


# ---------------------------------------------------------------------------
# Task 9 (CP8): Pipeline wiring tests
# ---------------------------------------------------------------------------

def _seed_athlete_with_assessment(db):
    """Helper: crea un Athlete + Assessment FTP e ritorna l'athlete_id."""
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo"))
    db.save_assessment(Assessment(
        id=make_assessment_id(ath, "ftp", "2026-07-01"),
        athlete_id=ath,
        protocol=AssessmentProtocol.FTP,
        executed_date="2026-07-01",
        value=329.0,
        unit="W",
    ))
    return ath


def test_pipeline_coach_returns_proposed(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete_with_assessment(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = Pipeline(db).coach(ath, goal)
    assert plan.status == PlanStatus.PROPOSED


def test_pipeline_coach_accept_promotes(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete_with_assessment(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = Pipeline(db).coach(ath, goal)
    Pipeline(db).coach_accept(plan.id)
    assert db.active_plan(ath).id == plan.id


def test_pipeline_coach_accept_missing_raises_plannotfound(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    with pytest.raises(PlanNotFound):
        Pipeline(db).coach_accept("id-inesistente")


def test_pipeline_coach_accept_non_proposed_raises_planstateerror(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete_with_assessment(db)
    # Crea direttamente un piano ACTIVE (senza passare per coach())
    active = TrainingPlan(
        id=make_plan_id(ath, 1), athlete_id=ath, version=1, status=PlanStatus.ACTIVE
    )
    db.save_athlete(Athlete(id=ath, name="Paolo")) if db.get_athlete(ath) is None else None
    db.save_plan(active)
    with pytest.raises(PlanStateError):
        Pipeline(db).coach_accept(active.id)


# ---------------------------------------------------------------------------
# FIX B — coach_assess robusto: piano/blocco inesistente → PlanNotFound
# (mai StopIteration/AttributeError grezzo).
# ---------------------------------------------------------------------------

def test_pipeline_coach_assess_missing_plan_raises(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete_with_assessment(db)
    with pytest.raises(PlanNotFound):
        Pipeline(db).coach_assess(ath, "plan-inesistente", "blk-qualsiasi")


def test_pipeline_coach_assess_missing_block_raises(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete_with_assessment(db)
    plan_id = make_plan_id(ath, 1)
    plan = TrainingPlan(
        id=plan_id, athlete_id=ath, version=1, status=PlanStatus.ACTIVE,
        blocks=[TrainingBlock(
            id=make_block_id(plan_id, 0), plan_id=plan_id, goal="vo2max", order=0,
        )],
    )
    db.save_plan(plan)
    # plan valido ma block_id inesistente → PlanNotFound (non StopIteration).
    with pytest.raises(PlanNotFound):
        Pipeline(db).coach_assess(ath, plan_id, "blk-inesistente")
