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
