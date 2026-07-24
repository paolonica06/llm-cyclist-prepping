"""Fase B — metriche derivate (funzioni pure) e invarianti (gate + congelamento).

Tutto qui è **puro e deterministico**: nessuna I/O, nessuna rete. CTL/ATL/TSB
NON compaiono: sono ingerite (ramo mirror), mai ricalcolate.

Invarianti incarnati:
- `citable_evidence` / `freeze_citation`: solo Evidenza verificata è citabile.
- `derive_executed_block`: ricava l'*eseguito* dalle Attività reali (≠ pianificato).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .athlete_models import (
    ActivitySummary, EvidenceCitation, ProvenanceKind, TrainingBlock,
    TransferabilityVerdict,
)
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


# --------------------------------------------------------------------------- #
# Task 3 (CP3) — Funzioni pure per il CoachAgent
# --------------------------------------------------------------------------- #

def block_compliance_verdict(planned_load: float, executed_load_: float,
                             threshold: float = DEFAULT_COMPLIANCE_THRESHOLD) -> str:
    """Verdetto compliance di un blocco: 'pass' | 'fail' | 'overload'.

    Usa `compliance` (non cappata) internamente: >1.0 segnala sovraccarico.
    """
    ratio = compliance(planned_load, executed_load_)
    if ratio > 1.0 + 1e-9:
        return "overload"
    return "pass" if ratio >= threshold else "fail"


def attribution_verdict(compliance_ratio: float, metric_delta: Optional[float],
                        threshold: float = DEFAULT_COMPLIANCE_THRESHOLD) -> TransferabilityVerdict:
    """Attribuisce il delta di metrica al blocco, solo se la compliance supera la soglia.

    Se compliance_ratio < threshold → INCONCLUSIVE (US 9: non si impara sotto soglia).
    Se metric_delta è None → INCONCLUSIVE (nessun dato di miglioramento).
    Altrimenti: TRANSFERRED se delta > 0, NOT_TRANSFERRED altrimenti.
    """
    if compliance_ratio < threshold:
        return TransferabilityVerdict.INCONCLUSIVE
    if metric_delta is None:
        return TransferabilityVerdict.INCONCLUSIVE
    return (TransferabilityVerdict.TRANSFERRED if metric_delta > 0
            else TransferabilityVerdict.NOT_TRANSFERRED)


def assessment_gap_to_goal(current: Optional[float], goal: Optional[float]) -> Optional[float]:
    """Distanza assoluta (goal − current). None se uno dei valori manca."""
    if current is None or goal is None:
        return None
    return goal - current


def goal_reached(current: Optional[float], goal: Optional[float],
                 tolerance: float = 0.0) -> bool:
    """True se current >= goal − tolerance. False se uno dei valori manca."""
    if current is None or goal is None:
        return False
    return current >= goal - tolerance


def block_planned_load(block: TrainingBlock) -> float:
    """Somma il carico pianificato derivandolo dalle Prescription; 0.0 se non derivabile.

    Proxy grezzo: ore × reps (TSS non disponibile senza FTP e zone).
    """
    total = 0.0
    for p in block.prescriptions:
        if p.duration_s and p.target_watts:
            total += (p.duration_s / 3600.0) * (p.reps or 1)
    return total


def freeze_athlete_data_citation(ref_id: str, title: Optional[str] = None,
                                 note: Optional[str] = None,
                                 frozen_at: Optional[str] = None) -> EvidenceCitation:
    """Crea una Citazione N=1 da un dato dell'atleta (Assessment, misura, ecc.).

    source_kind = ATHLETE_DATA; mai doi/pmid; verified = False (ADR-0007).
    """
    return EvidenceCitation(
        record_id=ref_id,
        title=title or note,
        doi=None,
        pmid=None,
        verified=False,
        source_kind=ProvenanceKind.ATHLETE_DATA,
        frozen_at=frozen_at,
    )


def overload_guardrail(recent_tsb: Optional[float], hrv_drop: Optional[bool],
                       sleep_drop: Optional[bool],
                       perf_drop: Optional[bool]) -> Optional[str]:
    """Segnala sovraccarico non-funzionale quando TSB molto negativo + ≥1 crash bio.

    Soglie hard-coded (documentate come config-ready — future KB_* var):
    - TSB ≤ −25.0  (soglia ribaltabile)
    - ≥ 1 fra hrv_drop, sleep_drop, perf_drop = True
    Restituisce una stringa di guardrail o None se tutto ok.
    """
    very_negative = recent_tsb is not None and recent_tsb <= -25.0
    crashes = sum(1 for x in (hrv_drop, sleep_drop, perf_drop) if x)
    if very_negative and crashes >= 1:
        return "sovraccarico non-funzionale: declassare il carico del microciclo entrante"
    return None


_MEDICAL_MARKERS = (
    "dolore", "male", "infortun", "sintom", "febbre", "malatt", "red-s", "reds", "amenorrea"
)


def medical_boundary_flag(signals: List[str]) -> Optional[str]:
    """Restituisce un disclaimer medico strutturale se i segnali contengono marcatori clinici.

    Il CoachAgent non diagnostica né prescrive (ADR-0007, PRD 15).
    """
    joined = " ".join(s.lower() for s in signals)
    if any(m in joined for m in _MEDICAL_MARKERS):
        return (
            "segnale a confine medico: il coach non diagnostica né prescrive; "
            "consulta un professionista sanitario"
        )
    return None
