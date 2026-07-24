from cyclist_kb.athlete_models import ProvenanceKind, PlanStatus, MetricType


def test_provenance_kind_values():
    assert ProvenanceKind.STUDY.value == "study"
    assert ProvenanceKind.ATHLETE_DATA.value == "athlete_data"
    assert ProvenanceKind.HEURISTIC.value == "heuristic"


def test_plan_status_proposed_added_without_breaking_existing():
    assert PlanStatus.PROPOSED.value == "proposed"
    assert PlanStatus.ACTIVE.value == "active"
    assert PlanStatus.SUPERSEDED.value == "superseded"


def test_metric_type_vo2max_added():
    assert MetricType.VO2MAX.value == "vo2max"


# ---------------------------------------------------------------------------
# Task 2 (CP2): estensioni dei modelli
# ---------------------------------------------------------------------------
from cyclist_kb.athlete_models import (
    Prescription, EvidenceCitation, TrainingBlock, TrainingPlan,
    TransferabilityMemo, MetricGoal, ProvenanceKind, PlanStatus, MetricType,
    make_plan_id,
)


def test_prescription_provenance_syncs_supported():
    p = Prescription(description="VO2 5x4", provenance=ProvenanceKind.STUDY)
    assert p.supported is True
    q = Prescription(description="Z2", provenance=ProvenanceKind.HEURISTIC)
    assert q.supported is False


def test_citation_source_kind_defaults_study():
    c = EvidenceCitation(record_id="rec-1")
    assert c.source_kind == ProvenanceKind.STUDY


def test_block_carries_provenance_and_conflicts():
    b = TrainingBlock(id="blk-1", plan_id="plan-1", goal="vo2max",
                      provenance=ProvenanceKind.STUDY, conflicts=["studio X contro"])
    assert b.provenance == ProvenanceKind.STUDY
    assert b.conflicts == ["studio X contro"]


def test_metric_goal_shape():
    g = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    assert g.start is None and g.target == 340.0


def test_next_version_status_parametrized():
    plan = TrainingPlan(id=make_plan_id("ath-1", 1), athlete_id="ath-1")
    nxt = plan.next_version(status=PlanStatus.PROPOSED)
    assert nxt.status == PlanStatus.PROPOSED and nxt.version == 2
    default = plan.next_version()
    assert default.status == PlanStatus.ACTIVE


def test_memo_carries_compliance_and_citations():
    m = TransferabilityMemo(id="memo-1", athlete_id="ath-1", block_id="blk-1",
                            verdict="inconclusive", compliance_ratio=0.6)
    assert m.compliance_ratio == 0.6 and m.citations == []


# ---------------------------------------------------------------------------
# Task 3 (CP3): funzioni pure in athlete_metrics
# ---------------------------------------------------------------------------
import pytest
from cyclist_kb.athlete_metrics import (
    attribution_verdict, block_compliance_verdict, assessment_gap_to_goal,
    goal_reached, block_planned_load, freeze_athlete_data_citation,
    overload_guardrail, medical_boundary_flag,
)
from cyclist_kb.athlete_models import (
    TransferabilityVerdict, ProvenanceKind, TrainingBlock, Prescription,
)


@pytest.mark.parametrize("ratio,delta,expected", [
    (0.6, 12.0, TransferabilityVerdict.INCONCLUSIVE),   # sotto soglia → non impara
    (0.9, 12.0, TransferabilityVerdict.TRANSFERRED),
    (0.9, -3.0, TransferabilityVerdict.NOT_TRANSFERRED),
    (0.9, None, TransferabilityVerdict.INCONCLUSIVE),
])
def test_attribution_verdict(ratio, delta, expected):
    assert attribution_verdict(ratio, delta) == expected


@pytest.mark.parametrize("planned,executed,expected", [
    (100.0, 90.0, "pass"),
    (100.0, 50.0, "fail"),
    (100.0, 130.0, "overload"),   # >1.0 → overload (non cappato)
])
def test_block_compliance_verdict(planned, executed, expected):
    assert block_compliance_verdict(planned, executed) == expected


def test_assessment_gap_and_goal_reached():
    assert assessment_gap_to_goal(329.0, 340.0) == 11.0
    assert assessment_gap_to_goal(None, 340.0) is None
    assert goal_reached(341.0, 340.0) is True
    assert goal_reached(338.0, 340.0) is False


def test_block_planned_load_sums_prescriptions_or_zero():
    b = TrainingBlock(id="b", plan_id="p", goal="vo2max", prescriptions=[
        Prescription(description="x", duration_s=3600, target_watts=300),
    ])
    assert block_planned_load(b) >= 0.0            # degrada a 0.0 se non derivabile


def test_freeze_athlete_data_citation_is_n1():
    c = freeze_athlete_data_citation("assess-1", note="ultima FTP")
    assert c.source_kind == ProvenanceKind.ATHLETE_DATA
    assert c.record_id == "assess-1"
    assert c.doi is None and c.pmid is None and c.verified is False


def test_overload_and_medical_guards():
    assert overload_guardrail(-30.0, True, True, None) is not None
    assert overload_guardrail(5.0, False, False, False) is None
    assert medical_boundary_flag(["dolore al ginocchio"]) is not None
    assert medical_boundary_flag([]) is None
