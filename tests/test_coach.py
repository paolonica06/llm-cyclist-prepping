from cyclist_kb.athlete_models import (
    Athlete, Assessment, AssessmentProtocol, MetricGoal, MetricType,
    PlanStatus, ProvenanceKind, make_athlete_id, make_assessment_id,
)
from cyclist_kb.agents.coach import CoachAgent


def _seed_athlete(db):
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo", category="U23", discipline="road"))
    db.save_assessment(Assessment(
        id=make_assessment_id(ath, "ftp", "2026-07-01"),
        athlete_id=ath, protocol=AssessmentProtocol.FTP,
        executed_date="2026-07-01", value=329.0, unit="W"))
    return ath


def _db(tmp_path, monkeypatch):
    from cyclist_kb.config import get_settings
    from cyclist_kb.db import Database
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "kb.sqlite3")
    return Database()


def test_run_produces_proposed_plan_offline(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)
    assert plan.status == PlanStatus.PROPOSED
    assert plan.blocks, "deve periodizzare in blocchi"
    assert plan.target_metric_value == 340.0
    assert plan.target_metric_start == 329.0        # dedotto dall'ultimo Assessment
    # ogni blocco e prescrizione hanno provenance valorizzata
    for b in plan.blocks:
        assert b.provenance in ProvenanceKind
        for p in b.prescriptions:
            assert p.provenance in ProvenanceKind
    # disclaimer strutturale sempre
    assert plan.notes and "ipotesi" in plan.notes.lower()


def test_run_is_not_active_until_accepted(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)
    assert db.active_plan(ath) is None               # PROPOSED non è attivo
    CoachAgent(db).accept(plan.id)
    assert db.active_plan(ath).id == plan.id
