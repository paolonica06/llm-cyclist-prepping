"""Task 8 (CP10) — loop veloce `adapt_microcycle`.

In stato di sovraccarico non-funzionale (TSB molto negativo + calo HRV/sonno),
`adapt_microcycle` produce una NUOVA versione PROPOSED con il carico del
microciclo entrante (blocchi non-FROZEN) ridotto, lasciando invariata la
strategia (goal/provenance) e — invariante ADR-0002 — i blocchi FROZEN.
"""

from cyclist_kb.agents.coach import CoachAgent
from cyclist_kb.athlete_models import (
    Athlete, BlockState, MetricType, PlanStatus, Prescription, TimeseriesPoint,
    TrainingBlock, TrainingPlan, make_athlete_id, make_block_id, make_plan_id,
)


def _db(tmp_path, monkeypatch):
    from cyclist_kb.config import get_settings
    from cyclist_kb.db import Database
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "kb.sqlite3")
    return Database()


# Valori noti dei carichi originali del blocco entrante (PLANNED).
_ENTER_WATTS = 300.0
_ENTER_DURATION = 3600
# Valori del blocco FROZEN precedente (non devono cambiare — ADR-0002).
_FROZEN_WATTS = 280.0
_FROZEN_FTP = 320.0


def _seed_overloaded(db):
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo", category="U23", discipline="road"))

    plan_id = make_plan_id(ath, 1)
    frozen = TrainingBlock(
        id=make_block_id(plan_id, 0), plan_id=plan_id, goal="base", order=0,
        state=BlockState.FROZEN, ftp_at_time=_FROZEN_FTP,
        prescriptions=[Prescription(description="Seduta base",
                                    target_watts=_FROZEN_WATTS, duration_s=_ENTER_DURATION)],
    )
    entering = TrainingBlock(
        id=make_block_id(plan_id, 1), plan_id=plan_id, goal="sviluppo", order=1,
        state=BlockState.PLANNED,
        prescriptions=[Prescription(description="Seduta sviluppo",
                                    target_watts=_ENTER_WATTS, duration_s=_ENTER_DURATION)],
    )
    plan = TrainingPlan(
        id=plan_id, athlete_id=ath, version=1, status=PlanStatus.ACTIVE,
        blocks=[frozen, entering],
    )
    db.save_plan(plan)

    # Serie storiche: sovraccarico non-funzionale.
    for d, v in [("2026-07-20", -28.0), ("2026-07-21", -29.0), ("2026-07-22", -30.0)]:
        db.add_timeseries_point(TimeseriesPoint(
            athlete_id=ath, metric_type=MetricType.TSB, date=d, value=v))
    # HRV in calo: ultimo < media dei precedenti.
    for d, v in [("2026-07-20", 70.0), ("2026-07-21", 68.0), ("2026-07-22", 55.0)]:
        db.add_timeseries_point(TimeseriesPoint(
            athlete_id=ath, metric_type=MetricType.HRV, date=d, value=v))
    # Sonno in calo: ultimo < media dei precedenti.
    for d, v in [("2026-07-20", 8.0), ("2026-07-21", 7.5), ("2026-07-22", 5.0)]:
        db.add_timeseries_point(TimeseriesPoint(
            athlete_id=ath, metric_type=MetricType.SLEEP, date=d, value=v))
    return ath, plan


def test_adapt_microcycle_reduces_entering_load_and_freezes_frozen(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath, active = _seed_overloaded(db)

    new = CoachAgent(db).adapt_microcycle(ath)

    # Nuova proposta versionata.
    assert isinstance(new, TrainingPlan)
    assert new.status == PlanStatus.PROPOSED
    assert new.version > active.version

    frozen_new = next(b for b in new.blocks if b.state == BlockState.FROZEN)
    entering_new = next(b for b in new.blocks if b.state != BlockState.FROZEN)

    # Il blocco entrante ha carico RIDOTTO (watt e/o durata minori degli originali).
    p = entering_new.prescriptions[0]
    reduced_watts = p.target_watts is not None and p.target_watts < _ENTER_WATTS
    reduced_duration = p.duration_s is not None and p.duration_s < _ENTER_DURATION
    assert reduced_watts or reduced_duration

    # ADR-0002: il blocco FROZEN è INVARIATO (target e ftp_at_time identici).
    assert frozen_new.state == BlockState.FROZEN
    assert frozen_new.ftp_at_time == _FROZEN_FTP
    assert frozen_new.prescriptions[0].target_watts == _FROZEN_WATTS
    assert frozen_new.prescriptions[0].duration_s == _ENTER_DURATION

    # Strategia invariata: goal e provenance dei blocchi restano quelli originali.
    assert [b.goal for b in new.blocks] == [b.goal for b in active.blocks]
    assert [b.provenance for b in new.blocks] == [b.provenance for b in active.blocks]

    # Disclaimer strutturale sempre presente.
    assert new.notes and "ipotesi" in new.notes.lower()
