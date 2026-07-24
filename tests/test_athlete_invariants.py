"""Fase B — invarianti: citabilità solo su evidenza verificata + congelamento immutabile."""

import pytest

from cyclist_kb.athlete_metrics import citable_evidence, freeze_citation
from cyclist_kb.athlete_models import (BlockState, Prescription, TrainingBlock,
                                       TrainingPlan, make_block_id, make_plan_id)
from cyclist_kb.db import Database
from cyclist_kb.models import (PaperRecord, QualityAssessment, QualityLevel,
                               RecordState, VerificationResult, make_record_id)


def _verified_record() -> PaperRecord:
    return PaperRecord(
        id=make_record_id("r", "10.1/a", None, "T"), research_id="r", doi="10.1/a", title="T",
        state=RecordState.SYNTHESIZED,
        verification=VerificationResult(verified=True),
        quality=QualityAssessment(methodological_quality=QualityLevel.HIGH,
                                  transferability_to_competitive_cyclists=QualityLevel.MODERATE),
    )


def test_citable_only_when_verified():
    rec = _verified_record()
    assert citable_evidence(rec) is True
    rec.verification.verified = False
    assert citable_evidence(rec) is False


def test_citable_requires_verified_state():
    rec = _verified_record()
    rec.state = RecordState.NEEDS_REVIEW
    assert citable_evidence(rec) is False


def test_freeze_citation_rejects_unverified():
    rec = _verified_record()
    rec.verification.verified = False
    with pytest.raises(ValueError):
        freeze_citation(rec)


def test_freeze_citation_snapshots_verified():
    rec = _verified_record()
    cit = freeze_citation(rec, frozen_at="2026-07-24")
    assert cit.verified is True
    assert cit.doi == "10.1/a"
    assert cit.quality == "high"                 # QualityLevel.HIGH
    assert cit.transferability == "moderate"     # trasferibilità DELLO studio
    assert cit.record_id == rec.id               # puntatore soft


def test_frozen_block_immutable_across_replanning(tmp_path):
    db = Database(path=tmp_path / "kb.sqlite3")
    aid = "ath-1"
    v1_id = make_plan_id(aid, 1)
    block = TrainingBlock(
        id=make_block_id(v1_id, 0), plan_id=v1_id, goal="vo2max",
        prescriptions=[Prescription(description="4x8' @105%", target_watts=336, supported=True)],
    )
    frozen = block.freeze(ftp_at_time=320.0, executed_start="2026-07-01",
                          executed_end="2026-07-28", frozen_at="2026-07-29")
    v1 = TrainingPlan(id=v1_id, athlete_id=aid, version=1, blocks=[frozen])
    db.save_plan(v1)

    # Ri-pianificazione: nuova versione, poi muto il blocco della nuova versione.
    v2 = v1.supersede(valid_to="2026-08-01")
    v2.blocks[0].prescriptions[0].target_watts = 999
    v2.blocks[0].goal = "soglia"
    db.save_plan(v1)
    db.save_plan(v2)

    # v1 riletta dal DB: lo snapshot congelato è INTATTO (la memoria non mente).
    reloaded = db.get_plan(v1_id)
    assert reloaded.blocks[0].state == BlockState.FROZEN
    assert reloaded.blocks[0].prescriptions[0].target_watts == 336
    assert reloaded.blocks[0].goal == "vo2max"
    assert reloaded.blocks[0].ftp_at_time == 320.0
