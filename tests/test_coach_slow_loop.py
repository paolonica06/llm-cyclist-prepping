"""Task 7 (CP7) — loop lento: assess_block → TransferabilityMemo con gate di compliance.

Copre tre casi sullo stesso schema di seeding (compliance omogenea in secondi:
durata eseguita vs durata pianificata):
- compliance < 0.80 → verdict INCONCLUSIVE, caveat "compliance < soglia" (US 9: non si impara sotto soglia);
- compliance >= 0.80 & ΔFTP > 0 → TRANSFERRED, metric_deltas={"ftp": delta};
- durata pianificata non derivabile (block_planned_load == 0) → INCONCLUSIVE,
  compliance_ratio is None, caveat "durata pianificata non derivabile".

Numeri scelti leggendo `block_planned_load` (ora durata pianificata in secondi):
una Prescription (duration_s=3600, reps=None) → planned = 3600.0 s. Un'ActivitySummary
nel range con moving_time_s=2160 dà ratio 0.6 (< soglia); con moving_time_s=3240 dà
ratio 0.9 (>= soglia).
"""

from cyclist_kb.agents.coach import CoachAgent
from cyclist_kb.athlete_models import (
    ActivitySummary, Assessment, AssessmentProtocol, Athlete, BlockState,
    MetricType, PlanStatus, Prescription, TrainingBlock, TrainingPlan,
    TransferabilityVerdict, make_activity_id, make_assessment_id,
    make_athlete_id, make_block_id, make_plan_id,
)


def _db(tmp_path, monkeypatch):
    from cyclist_kb.config import get_settings
    from cyclist_kb.db import Database
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "kb.sqlite3")
    return Database()


def _seed(db, *, moving_time_s, planned_duration_s=3600):
    """Semina atleta + piano FTP con un blocco FROZEN, un'attività nel range e due
    valutazioni FTP (pre/post) con ΔFTP>0. `moving_time_s` regola il ratio; se
    `planned_duration_s` è None il blocco non ha prescrizioni datate (planned==0)."""
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo", category="U23", discipline="road"))

    plan_id = make_plan_id(ath, 1)
    block_id = make_block_id(plan_id, 0)
    # planned = durata pianificata totale in secondi = duration_s * (reps or 1).
    if planned_duration_s is None:
        prescriptions = [Prescription(description="5x4", target_watts=300)]  # no duration
    else:
        prescriptions = [Prescription(description="5x4", target_watts=300,
                                       duration_s=planned_duration_s)]
    block = TrainingBlock(
        id=block_id, plan_id=plan_id, goal="vo2max", order=0,
        planned_start="2026-07-01", planned_end="2026-07-28",
        state=BlockState.FROZEN,
        prescriptions=prescriptions,
    )
    plan = TrainingPlan(
        id=plan_id, athlete_id=ath, version=1, status=PlanStatus.ACTIVE,
        target_metric_type=MetricType.FTP, target_metric_start=329.0,
        target_metric_value=340.0, target_metric_date="2026-09-30",
        blocks=[block],
    )
    db.save_plan(plan)

    # Attività nel range [planned_start, planned_end] con la durata eseguita voluta.
    db.save_activity(ActivitySummary(
        id=make_activity_id(ath, "act-1"), athlete_id=ath,
        date="2026-07-14", type="Ride", moving_time_s=moving_time_s))

    # Valutazioni pre/post con ΔFTP > 0 (325 → 335).
    db.save_assessment(Assessment(
        id=make_assessment_id(ath, "ftp", "2026-07-01"), athlete_id=ath,
        protocol=AssessmentProtocol.FTP, executed_date="2026-07-01",
        value=325.0, unit="W"))
    db.save_assessment(Assessment(
        id=make_assessment_id(ath, "ftp", "2026-07-28"), athlete_id=ath,
        protocol=AssessmentProtocol.FTP, executed_date="2026-07-28",
        value=335.0, unit="W"))
    return ath, plan_id, block_id


def test_assess_block_below_threshold_is_inconclusive(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    # moving_time_s=2160, planned=3600 → ratio 0.6 < 0.80
    ath, plan_id, block_id = _seed(db, moving_time_s=2160)

    memo = CoachAgent(db).assess_block(ath, plan_id, block_id)

    assert memo.verdict == TransferabilityVerdict.INCONCLUSIVE
    assert memo.compliance_ratio is not None and memo.compliance_ratio < 0.80
    assert "compliance < soglia" in memo.caveats


def test_assess_block_above_threshold_transfers(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    # moving_time_s=3240, planned=3600 → ratio 0.9 >= 0.80, ΔFTP = 335-325 = 10 > 0
    ath, plan_id, block_id = _seed(db, moving_time_s=3240)

    memo = CoachAgent(db).assess_block(ath, plan_id, block_id)

    assert memo.verdict == TransferabilityVerdict.TRANSFERRED
    assert memo.metric_deltas == {"ftp": 10.0}
    assert memo.compliance_ratio is not None and memo.compliance_ratio >= 0.80


def test_assess_block_no_planned_duration_is_inconclusive(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    # Blocco senza prescrizioni datate → block_planned_load == 0.
    ath, plan_id, block_id = _seed(db, moving_time_s=3240, planned_duration_s=None)

    memo = CoachAgent(db).assess_block(ath, plan_id, block_id)

    assert memo.verdict == TransferabilityVerdict.INCONCLUSIVE
    assert memo.compliance_ratio is None
    assert "durata pianificata non derivabile" in memo.caveats
