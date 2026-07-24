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
