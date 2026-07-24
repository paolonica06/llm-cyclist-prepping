"""Fase B — persistenza del modello atleta longitudinale (round-trip, idempotenza, versioning)."""

from cyclist_kb.db import Database
from cyclist_kb.athlete_models import (
    Assessment, AssessmentProtocol, Athlete, MetricType, PlanStatus,
    Prescription, ProvenanceKind, Race,
    RacePriority, TimeseriesPoint, TrainingBlock, TrainingPlan,
    TransferabilityMemo, TransferabilityVerdict, make_assessment_id,
    make_athlete_id, make_block_id, make_memo_id, make_plan_id, make_race_id,
)
from cyclist_kb.models import QualityLevel


def _db(tmp_path) -> Database:
    return Database(path=tmp_path / "kb.sqlite3")


def _athlete() -> Athlete:
    return Athlete(id=make_athlete_id("Paolo"), name="Paolo", discipline="strada",
                   level="competitivo", goals=["gran fondo"])


def test_athlete_roundtrip(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    got = db.get_athlete(a.id)
    assert got is not None
    assert got.name == "Paolo"
    assert got.discipline == "strada"
    assert got.goals == ["gran fondo"]
    assert [x.id for x in db.list_athletes()] == [a.id]


def test_timeseries_upsert_is_idempotent(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    db.add_timeseries_point(TimeseriesPoint(athlete_id=a.id, metric_type=MetricType.CTL,
                                            date="2026-07-20", value=80.0))
    # Stessa (grandezza, data): un secondo sync aggiorna, NON duplica.
    db.add_timeseries_point(TimeseriesPoint(athlete_id=a.id, metric_type=MetricType.CTL,
                                            date="2026-07-20", value=82.0))
    points = db.list_timeseries(a.id, metric_type=MetricType.CTL.value)
    assert len(points) == 1
    assert points[0].value == 82.0


def test_timeseries_filters_by_metric_and_since(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    db.add_timeseries_point(TimeseriesPoint(athlete_id=a.id, metric_type=MetricType.HRV,
                                            date="2026-07-18", value=60.0))
    db.add_timeseries_point(TimeseriesPoint(athlete_id=a.id, metric_type=MetricType.HRV,
                                            date="2026-07-21", value=65.0))
    db.add_timeseries_point(TimeseriesPoint(athlete_id=a.id, metric_type=MetricType.TSB,
                                            date="2026-07-21", value=-5.0))
    hrv = db.list_timeseries(a.id, metric_type=MetricType.HRV.value)
    assert [p.value for p in hrv] == [60.0, 65.0]              # ordinati per data
    recent = db.list_timeseries(a.id, metric_type=MetricType.HRV.value, since="2026-07-20")
    assert [p.value for p in recent] == [65.0]


def test_power_curve_point_uses_extra(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    db.add_timeseries_point(TimeseriesPoint(
        athlete_id=a.id, metric_type=MetricType.POWER_CURVE, date="2026-07-21",
        extra={"5": 900, "60": 500, "1200": 320}))
    pc = db.list_timeseries(a.id, metric_type=MetricType.POWER_CURVE.value)
    assert pc[0].extra["1200"] == 320


def test_race_roundtrip_and_priority(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    race = Race(id=make_race_id(a.id, "Nove Colli", "2026-05-24"), athlete_id=a.id,
                name="Nove Colli", date="2026-05-24", priority=RacePriority.A, role="obiettivo")
    db.save_race(race)
    races = db.list_races(a.id)
    assert len(races) == 1
    assert races[0].priority == RacePriority.A


def test_assessment_roundtrip_and_ordering(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    db.save_assessment(Assessment(id=make_assessment_id(a.id, "ftp", "2026-06-01"),
                                  athlete_id=a.id, protocol=AssessmentProtocol.FTP,
                                  executed_date="2026-06-01", value=300.0, unit="W"))
    db.save_assessment(Assessment(id=make_assessment_id(a.id, "ftp", "2026-04-01"),
                                  athlete_id=a.id, protocol=AssessmentProtocol.FTP,
                                  executed_date="2026-04-01", value=290.0, unit="W"))
    ftp = db.list_assessments(a.id, protocol="ftp")
    assert [x.value for x in ftp] == [290.0, 300.0]           # ordinate per data eseguita


def test_plan_versioning_supersede(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    v1_id = make_plan_id(a.id, 1)
    v1 = TrainingPlan(id=v1_id, athlete_id=a.id, version=1)
    v1.blocks.append(TrainingBlock(id=make_block_id(v1_id, 0), plan_id=v1_id, goal="base"))
    db.save_plan(v1)

    v2 = v1.next_version(valid_from="2026-05-01")   # copia pura, NON muta v1
    db.supersede_plan(v2)                           # transizione atomica (un solo commit)

    assert db.active_plan(a.id).id == v2.id
    assert db.active_plan(a.id).version == 2
    statuses = {p.version: p.status for p in db.list_plans(a.id)}
    assert statuses == {1: PlanStatus.SUPERSEDED, 2: PlanStatus.ACTIVE}


def test_memo_roundtrip(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    block_id = "blk-xyz"
    db.save_memo(TransferabilityMemo(
        id=make_memo_id(block_id), athlete_id=a.id, block_id=block_id,
        verdict=TransferabilityVerdict.TRANSFERRED, confidence=QualityLevel.MODERATE,
        metric_deltas={"ftp": 10.0}, caveats=["sonno scarso nell'ultima settimana"]))
    memos = db.list_memos(a.id, block_id=block_id)
    assert len(memos) == 1
    assert memos[0].verdict == TransferabilityVerdict.TRANSFERRED
    assert memos[0].confidence == QualityLevel.MODERATE
    assert memos[0].caveats == ["sonno scarso nell'ultima settimana"]


def test_timeseries_since_boundary_is_inclusive(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    db.add_timeseries_point(TimeseriesPoint(athlete_id=a.id, metric_type=MetricType.CTL,
                                            date="2026-07-21", value=80.0))
    # since == data del punto → incluso (>=); since successivo → escluso.
    assert len(db.list_timeseries(a.id, MetricType.CTL.value, since="2026-07-21")) == 1
    assert db.list_timeseries(a.id, MetricType.CTL.value, since="2026-07-22") == []


def test_prescription_defaults_unsupported(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    pid = make_plan_id(a.id, 1)
    plan = TrainingPlan(id=pid, athlete_id=a.id, version=1, blocks=[
        TrainingBlock(id=make_block_id(pid, 0), plan_id=pid, goal="vo2max",
                      prescriptions=[Prescription(description="4x8'", target_watts=336)])])
    db.save_plan(plan)
    reloaded = db.get_plan(pid)
    # Una prescrizione senza evidenza dichiarata è "non supportata" di default.
    assert reloaded.blocks[0].prescriptions[0].supported is False


def test_plan_supersede_to_v3(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    v1 = TrainingPlan(id=make_plan_id(a.id, 1), athlete_id=a.id, version=1)
    db.save_plan(v1)
    v2 = v1.next_version(); db.supersede_plan(v2)
    v3 = v2.next_version(); db.supersede_plan(v3)
    assert db.active_plan(a.id).version == 3
    versions = {p.version: p.status for p in db.list_plans(a.id)}
    assert versions == {1: PlanStatus.SUPERSEDED, 2: PlanStatus.SUPERSEDED, 3: PlanStatus.ACTIVE}


def test_active_plan_none_when_no_active(tmp_path):
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    assert db.active_plan(a.id) is None                       # nessun piano
    v1 = TrainingPlan(id=make_plan_id(a.id, 1), athlete_id=a.id, version=1)
    db.save_plan(v1)
    v2 = v1.next_version(); db.supersede_plan(v2)
    v2.status = PlanStatus.SUPERSEDED; db.save_plan(v2)        # solo piani superseded
    assert db.active_plan(a.id) is None


# ---------------------------------------------------------------------------
# Task 2 (CP2): round-trip DB + frozen-block invariante
# ---------------------------------------------------------------------------

def test_plan_with_target_metric_and_provenance_roundtrip(tmp_path):
    """Round-trip DB: TrainingPlan con target_metric_* e un blocco provenance=STUDY."""
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    pid = make_plan_id(a.id, 1)
    block = TrainingBlock(
        id=make_block_id(pid, 0), plan_id=pid, goal="vo2max",
        provenance=ProvenanceKind.STUDY,
        conflicts=["studio Y contro"],
    )
    plan = TrainingPlan(
        id=pid, athlete_id=a.id, version=1,
        target_metric_type=MetricType.FTP,
        target_metric_start=329.0,
        target_metric_value=340.0,
        target_metric_date="2026-09-30",
        blocks=[block],
    )
    db.save_plan(plan)
    reloaded = db.get_plan(pid)
    assert reloaded.target_metric_type == MetricType.FTP
    assert reloaded.target_metric_start == 329.0
    assert reloaded.target_metric_value == 340.0
    assert reloaded.target_metric_date == "2026-09-30"
    assert reloaded.blocks[0].provenance == ProvenanceKind.STUDY
    assert reloaded.blocks[0].conflicts == ["studio Y contro"]


def test_frozen_block_unchanged_after_next_version_proposed(tmp_path):
    """Un blocco FROZEN resta invariato (target_watts, ftp_at_time) dopo next_version(PROPOSED)."""
    db = _db(tmp_path)
    a = db.save_athlete(_athlete())
    pid = make_plan_id(a.id, 1)
    block = TrainingBlock(
        id=make_block_id(pid, 0), plan_id=pid, goal="base",
        prescriptions=[Prescription(description="Z2", target_watts=280)],
    )
    frozen_block = block.freeze(ftp_at_time=329.0, executed_start="2026-07-01",
                                executed_end="2026-07-28", frozen_at="2026-07-28")
    plan = TrainingPlan(id=pid, athlete_id=a.id, version=1, blocks=[frozen_block])
    db.save_plan(plan)

    # next_version con status PROPOSED non deve alterare i blocchi congelati del piano originale
    nxt = plan.next_version(status=PlanStatus.PROPOSED)
    assert nxt.status == PlanStatus.PROPOSED
    assert nxt.version == 2

    # il piano originale (con blocco frozen) rimane invariato
    reloaded = db.get_plan(pid)
    assert reloaded.blocks[0].ftp_at_time == 329.0
    assert reloaded.blocks[0].state.value == "frozen"
    assert reloaded.blocks[0].prescriptions[0].target_watts == 280
