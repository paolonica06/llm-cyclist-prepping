"""Invarianti offline del CoachAgent (ramo euristico, KB_FORCE_OFFLINE)."""

from cyclist_kb.athlete_models import (MetricGoal, MetricType, PlanStatus,
                                      ProvenanceKind)
from cyclist_kb.agents.coach import CoachAgent

from test_coach import _db, _seed_athlete


def _goal():
    return MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")


def test_heuristic_blocks_have_no_study_citations(tmp_path, monkeypatch):
    # (a) un blocco a provenienza euristica non spaccia citazioni di studio come supporto.
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    plan = CoachAgent(db).run(ath, _goal())
    for b in plan.blocks:
        if b.provenance == ProvenanceKind.HEURISTIC:
            assert b.citations == []


def test_proposed_not_active_until_accepted(tmp_path, monkeypatch):
    # (b) il PROPOSED non compare in active_plan finché non viene accettato.
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    plan = CoachAgent(db).run(ath, _goal())
    assert db.active_plan(ath) is None
    CoachAgent(db).accept(plan.id)
    active = db.active_plan(ath)
    assert active is not None and active.id == plan.id


def test_at_most_one_proposed_per_athlete(tmp_path, monkeypatch):
    # (c) rigenerando due volte, l'atleta ha al più un PROPOSED.
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    CoachAgent(db).run(ath, _goal())
    CoachAgent(db).run(ath, _goal())
    proposed = [p for p in db.list_plans(ath) if p.status == PlanStatus.PROPOSED]
    assert len(proposed) == 1
