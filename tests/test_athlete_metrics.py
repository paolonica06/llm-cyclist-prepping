"""Fase B — metriche derivate (funzioni pure): compliance, delta, blocco eseguito."""

from cyclist_kb.athlete_metrics import (assessment_delta, compliance,
                                        derive_executed_block, executed_load,
                                        is_compliant, pct_change)
from cyclist_kb.athlete_models import ActivitySummary, TrainingBlock


def _act(date, load) -> ActivitySummary:
    return ActivitySummary(id=f"a-{date}", athlete_id="x", date=date, load=load)


def test_compliance_ratio_and_threshold():
    assert compliance(100, 80) == 0.8
    assert compliance(0, 50) == 0.0            # pianificato nullo → 0
    assert compliance(100, 120) == 1.2         # non cappato: sovraccarico visibile
    assert is_compliant(100, 80) is True       # soglia default 0.8
    assert is_compliant(100, 79) is False


def test_assessment_delta_and_pct():
    assert assessment_delta(290, 305) == 15
    assert assessment_delta(None, 305) is None
    assert round(pct_change(290, 305), 4) == round(15 / 290 * 100, 4)
    assert pct_change(0, 10) is None           # divisione per zero → None


def test_executed_load_respects_range():
    acts = [_act("2026-07-10", 50), _act("2026-07-20", 60), _act("2026-08-01", 40)]
    assert executed_load(acts, "2026-07-01", "2026-07-31") == 110
    assert executed_load(acts) == 150          # senza intervallo: tutte


def test_derive_executed_block_from_activities():
    block = TrainingBlock(id="b1", plan_id="p1", goal="vo2max",
                          planned_start="2026-07-01", planned_end="2026-07-31")
    acts = [_act("2026-07-05", 50), _act("2026-07-25", 70), _act("2026-08-10", 99)]
    out = derive_executed_block(block, acts)
    assert out["executed_start"] == "2026-07-05"
    assert out["executed_end"] == "2026-07-25"      # l'attività di agosto è fuori dal blocco
    assert out["executed_load"] == 120
    assert out["activity_count"] == 2
