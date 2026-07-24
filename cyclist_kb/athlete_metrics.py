"""Fase B — metriche derivate (funzioni pure) e invarianti (gate + congelamento).

Tutto qui è **puro e deterministico**: nessuna I/O, nessuna rete. CTL/ATL/TSB
NON compaiono: sono ingerite (ramo mirror), mai ricalcolate.

Invarianti incarnati:
- `citable_evidence` / `freeze_citation`: solo Evidenza verificata è citabile.
- `derive_executed_block`: ricava l'*eseguito* dalle Attività reali (≠ pianificato).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .athlete_models import ActivitySummary, EvidenceCitation, TrainingBlock
from .models import PaperRecord, RecordState

# Stati in cui un'evidenza è considerata verificata (coerente col Verification gate).
CITABLE_STATES = {RecordState.METADATA_VERIFIED, RecordState.SYNTHESIZED}

# Decisione autonoma (Fase B): soglia di Compliance oltre la quale un blocco è
# considerato "eseguito" come pianificato. Ribaltabile — vedi report.
DEFAULT_COMPLIANCE_THRESHOLD = 0.8


# --------------------------------------------------------------------------- #
# Compliance (pianificato vs eseguito)
# --------------------------------------------------------------------------- #
def compliance(planned_load: float, executed_load_: float) -> float:
    """Rapporto eseguito/pianificato (0.0 se il pianificato è nullo). Non cappato:
    >1.0 segnala sovraccarico rispetto al piano."""
    if not planned_load or planned_load <= 0:
        return 0.0
    return executed_load_ / planned_load


def is_compliant(planned_load: float, executed_load_: float,
                 threshold: float = DEFAULT_COMPLIANCE_THRESHOLD) -> bool:
    return compliance(planned_load, executed_load_) >= threshold


# --------------------------------------------------------------------------- #
# Delta fra Valutazioni (progresso)
# --------------------------------------------------------------------------- #
def assessment_delta(before: Optional[float], after: Optional[float]) -> Optional[float]:
    if before is None or after is None:
        return None
    return after - before


def pct_change(before: Optional[float], after: Optional[float]) -> Optional[float]:
    if before is None or after is None or before == 0:
        return None
    return (after - before) / before * 100.0


# --------------------------------------------------------------------------- #
# Blocco eseguito (ricavato dalle Attività reali)
# --------------------------------------------------------------------------- #
def _in_range(date: Optional[str], start: Optional[str], end: Optional[str]) -> bool:
    if not date:
        return False
    if start and date < start:
        return False
    if end and date > end:
        return False
    return True


def executed_load(activities: List[ActivitySummary], start: Optional[str] = None,
                  end: Optional[str] = None) -> float:
    return sum((a.load or 0.0) for a in activities if _in_range(a.date, start, end))


def derive_executed_block(block: TrainingBlock,
                          activities: List[ActivitySummary]) -> Dict[str, Any]:
    """Ricava lo *stato eseguito* di un Blocco dalle Attività nel suo intervallo pianificato."""
    in_range = [a for a in activities
                if _in_range(a.date, block.planned_start, block.planned_end)]
    dates = sorted(a.date for a in in_range if a.date)
    return {
        "executed_start": dates[0] if dates else None,
        "executed_end": dates[-1] if dates else None,
        "executed_load": sum((a.load or 0.0) for a in in_range),
        "activity_count": len(in_range),
    }


# --------------------------------------------------------------------------- #
# Invariante: citabilità solo su Evidenza verificata + congelamento citazione
# --------------------------------------------------------------------------- #
def citable_evidence(record: PaperRecord) -> bool:
    """True solo se il record ha superato il gate di verifica (stato + flag verified)."""
    return (
        record.state in CITABLE_STATES
        and record.verification is not None
        and bool(record.verification.verified)
    )


def freeze_citation(record: PaperRecord, frozen_at: Optional[str] = None) -> EvidenceCitation:
    """Fotografa un'Evidenza verificata in una Citazione congelata (+ puntatore soft).

    Solleva `ValueError` se il record non è citabile: nessuna letteratura non
    verificata può entrare in un Piano.
    """
    if not citable_evidence(record):
        raise ValueError(
            f"Record {record.id} non citabile: solo evidenza verificata "
            "(METADATA_VERIFIED/SYNTHESIZED + verified) può entrare in un Piano."
        )
    quality = record.quality.methodological_quality.value if record.quality else None
    transfer = (record.quality.transferability_to_competitive_cyclists.value
                if record.quality else None)
    return EvidenceCitation(
        record_id=record.id,
        title=record.title,
        doi=record.doi,
        pmid=record.pmid,
        verified=True,
        quality=quality,
        transferability=transfer,
        frozen_at=frozen_at,
    )
