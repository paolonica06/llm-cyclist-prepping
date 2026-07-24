"""Schemi dati (Pydantic) del modello atleta longitudinale — Fase B.

Contratto condiviso per l'atleta tracciato nel tempo: misure (serie storiche),
gare, valutazioni, piano periodizzato (versionato, con blocchi congelati) ed
evidenza citata. Vive accanto a `models.py` (il contratto bibliografico) e ne
riusa `QualityLevel`. Vedi `CONTEXT.md` (glossario) e `docs/adr/0001..0004`.

Invarianti incarnati qui:
- La Trasferibilità personalizzata è un *verdetto con confidenza e caveat*
  (mai un booleano secco): `TransferabilityMemo`.
- Il congelamento produce una *copia* immutabile del blocco eseguito
  (`TrainingBlock.freeze`), così i giudizi sul passato non cambiano.
- Solo evidenza verificata è citabile (vedi `athlete_metrics.freeze_citation`).
"""

from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .models import QualityLevel


# --------------------------------------------------------------------------- #
# Enumerazioni
# --------------------------------------------------------------------------- #
class MetricType(str, Enum):
    """Grandezza di una Serie storica dell'atleta."""

    SLEEP = "sleep"              # wellness
    HRV = "hrv"
    WEIGHT = "weight"
    RESTING_HR = "resting_hr"
    CTL = "ctl"                  # fitness (ingerite, non ricalcolate)
    ATL = "atl"
    TSB = "tsb"
    FTP = "ftp"                  # storico della soglia
    POWER_CURVE = "power_curve"  # curva di potenza (payload strutturato in `extra`)


class RacePriority(str, Enum):
    A = "A"      # obiettivo primario attorno cui si periodizza
    B = "B"
    C = "C"


class AssessmentProtocol(str, Enum):
    FTP = "ftp"
    RAMP = "ramp"
    VO2MAX = "vo2max"


class BlockState(str, Enum):
    PLANNED = "planned"
    EXECUTED = "executed"
    FROZEN = "frozen"


class PlanStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class TransferabilityVerdict(str, Enum):
    TRANSFERRED = "transferred"
    NOT_TRANSFERRED = "not_transferred"
    INCONCLUSIVE = "inconclusive"


# --------------------------------------------------------------------------- #
# Helper per gli id stabili
# --------------------------------------------------------------------------- #
def _hid(prefix: str, *parts: Any) -> str:
    key = "::".join(str(p) for p in parts if p is not None)
    return f"{prefix}-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def make_athlete_id(name: str) -> str:
    key = re.sub(r"\s+", " ", (name or "").strip().lower())
    return _hid("ath", key)


def make_timeseries_id(athlete_id: str, metric_type: str, date: str) -> str:
    """Deterministico su (atleta, grandezza, data) → upsert idempotente della serie."""
    return _hid("ts", athlete_id, metric_type, date)


def make_race_id(athlete_id: str, name: str, date: Optional[str]) -> str:
    return _hid("race", athlete_id, name, date)


def make_assessment_id(athlete_id: str, protocol: str, date: Optional[str]) -> str:
    return _hid("assess", athlete_id, protocol, date)


def make_plan_id(athlete_id: str, version: int) -> str:
    return _hid("plan", athlete_id, version)


def make_block_id(plan_id: str, order: int) -> str:
    return _hid("blk", plan_id, order)


def make_memo_id(block_id: str) -> str:
    return _hid("memo", block_id)


# --------------------------------------------------------------------------- #
# Atleta e misure
# --------------------------------------------------------------------------- #
class Athlete(BaseModel):
    """Identità persistente + contesto stabile/qualitativo.

    Le grandezze variabili (FTP, VO₂max, carico) NON vivono qui: sono Serie
    storiche (vedi ADR/PRD). I campi legacy di `models.AthleteProfile` non sono
    più autoritativi per quelle grandezze.
    """

    id: str
    name: str
    sex: Optional[str] = None
    category: Optional[str] = None
    level: Optional[str] = None
    discipline: Optional[str] = None
    goals: List[str] = Field(default_factory=list)
    history: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TimeseriesPoint(BaseModel):
    """Una misura datata di una singola grandezza dell'atleta."""

    athlete_id: str
    metric_type: MetricType
    date: str                                   # ISO date (YYYY-MM-DD)
    value: Optional[float] = None               # None per POWER_CURVE (usa `extra`)
    extra: Dict[str, Any] = Field(default_factory=dict)  # es. curva: {"300": 320, "1200": 290}
    source: str = "intervals_icu"
    stale: bool = False                          # readiness: valore riportato (carry-forward)


class Race(BaseModel):
    id: str
    athlete_id: str
    name: str
    date: Optional[str] = None
    priority: RacePriority = RacePriority.C
    discipline: Optional[str] = None
    role: Optional[str] = None                   # es. "obiettivo" | "allenante"
    result: Optional[str] = None                 # contesto qualitativo, NON metrica
    notes: Optional[str] = None


class Assessment(BaseModel):
    """Valutazione: punto di misura primario del progresso."""

    id: str
    athlete_id: str
    protocol: AssessmentProtocol
    planned_date: Optional[str] = None
    executed_date: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    block_id: Optional[str] = None               # blocco che la precede/giustifica
    notes: Optional[str] = None


# --------------------------------------------------------------------------- #
# Piano, blocchi, evidenza
# --------------------------------------------------------------------------- #
class Prescription(BaseModel):
    """Un Intervallo/Seduta prescritto con target al watt, con marcatura evidenza."""

    description: str
    target_watts: Optional[float] = None
    duration_s: Optional[int] = None
    reps: Optional[int] = None
    supported: bool = False                      # sostenuta da Evidenza verificata?


class EvidenceCitation(BaseModel):
    """Citazione congelata: fotografia dell'Evidenza verificata + puntatore soft."""

    record_id: Optional[str] = None              # puntatore soft (best-effort) al record KB
    title: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    verified: bool = False
    quality: Optional[str] = None                # QualityLevel.value (metodologica)
    transferability: Optional[str] = None        # trasferibilità DELLO studio
    frozen_at: Optional[str] = None


class TrainingBlock(BaseModel):
    """Mesociclo con scopo fisiologico unico; livello di aggancio di evidenza ed esito."""

    id: str
    plan_id: str
    goal: str                                    # scopo fisiologico (es. "vo2max")
    order: int = 0
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    state: BlockState = BlockState.PLANNED
    prescriptions: List[Prescription] = Field(default_factory=list)
    citations: List[EvidenceCitation] = Field(default_factory=list)
    # Snapshot eseguito/congelato
    executed_start: Optional[str] = None
    executed_end: Optional[str] = None
    ftp_at_time: Optional[float] = None
    frozen_at: Optional[str] = None

    def freeze(
        self,
        *,
        ftp_at_time: Optional[float] = None,
        executed_start: Optional[str] = None,
        executed_end: Optional[str] = None,
        frozen_at: Optional[str] = None,
    ) -> "TrainingBlock":
        """Restituisce una COPIA congelata (immutabile per convenzione): non muta `self`."""
        frozen = self.model_copy(deep=True)
        frozen.state = BlockState.FROZEN
        frozen.ftp_at_time = ftp_at_time
        frozen.executed_start = executed_start
        frozen.executed_end = executed_end
        frozen.frozen_at = frozen_at
        return frozen


class TrainingPlan(BaseModel):
    """Piano periodizzato, aggregato (blocchi inline). Versionato/append-only.

    Il congelamento vive nel versioning: `supersede` crea una nuova versione,
    lasciando intatto il blob della precedente (con i suoi blocchi congelati).
    """

    id: str
    athlete_id: str
    version: int = 1
    status: PlanStatus = PlanStatus.ACTIVE
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    target_race_id: Optional[str] = None
    blocks: List[TrainingBlock] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def supersede(self, *, valid_to: Optional[str] = None) -> "TrainingPlan":
        """Marca `self` come superseded e restituisce la versione successiva (copia).

        Il chiamante persiste entrambi. La nuova versione è una copia profonda,
        quindi modificarla non tocca il blob della versione precedente.
        """
        self.status = PlanStatus.SUPERSEDED
        self.valid_to = valid_to
        nxt = self.model_copy(deep=True)
        nxt.version = self.version + 1
        nxt.id = make_plan_id(self.athlete_id, nxt.version)
        nxt.status = PlanStatus.ACTIVE
        nxt.valid_from = valid_to
        nxt.valid_to = None
        return nxt


class TransferabilityMemo(BaseModel):
    """Verdetto di Trasferibilità personalizzata: mai un booleano secco."""

    id: str
    athlete_id: str
    block_id: str
    verdict: TransferabilityVerdict
    confidence: QualityLevel = QualityLevel.LOW
    metric_deltas: Dict[str, float] = Field(default_factory=dict)  # es. {"ftp": 12.0, "vo2max": 1.5}
    caveats: List[str] = Field(default_factory=list)               # confounder
    assessed_at: Optional[str] = None
