"""Schemi dati (Pydantic) e stati della pipeline.

Questo modulo è il contratto condiviso da tutti gli agenti. Ogni record
bibliografico attraversa una macchina a stati (`RecordState`) e accumula
risultati strutturati (screening, verifica, estrazione, qualità) senza mai
perdere la provenienza né i record esclusi.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enumerazioni
# --------------------------------------------------------------------------- #
class RecordState(str, Enum):
    """Stati del ciclo di vita di un singolo record bibliografico."""

    DISCOVERED = "discovered"
    PENDING_SCREENING = "pending_screening"
    EXCLUDED = "excluded"
    INCLUDED = "included"
    METADATA_VERIFIED = "metadata_verified"
    FULL_TEXT_AVAILABLE = "full_text_available"
    ABSTRACT_ONLY = "abstract_only"
    EXTRACTED = "extracted"
    SYNTHESIZED = "synthesized"
    NEEDS_REVIEW = "needs_review"


class SourceDB(str, Enum):
    """Banche dati bibliografiche interrogate."""

    PUBMED = "pubmed"
    OPENALEX = "openalex"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    CROSSREF = "crossref"


class PopulationType(str, Enum):
    """Classificazione della popolazione studiata (nodo dello screening)."""

    CYCLING = "cycling"                    # ciclisti (su strada/pista/MTB, ergometro ciclistico)
    ENDURANCE_OTHER = "endurance_other"    # altri sport di endurance (corsa, canottaggio, nuoto...)
    UNTRAINED = "untrained"                # partecipanti non allenati / sedentari / ricreativi
    MIXED = "mixed"                        # popolazione mista o non chiaramente separabile
    UNCLEAR = "unclear"                    # non determinabile da titolo/abstract


class DataSource(str, Enum):
    """Origine di un dato: full text, abstract, metadati bibliografici o assente."""

    FULL_TEXT = "full_text"
    ABSTRACT = "abstract"
    METADATA = "metadata"          # campo proveniente dal record normalizzato (non dal corpo del testo)
    NOT_AVAILABLE = "not_available"


class QualityLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class ResearchStatus(str, Enum):
    CREATED = "created"
    SEARCHED = "searched"
    SCREENED = "screened"
    VERIFIED = "verified"
    EXTRACTED = "extracted"
    SYNTHESIZED = "synthesized"


# --------------------------------------------------------------------------- #
# Record bibliografico
# --------------------------------------------------------------------------- #
class PaperRecord(BaseModel):
    """Un lavoro scientifico normalizzato, aggregato da una o più banche dati."""

    id: str = Field(..., description="Identificativo interno stabile (hash di DOI/PMID/titolo).")
    research_id: str
    state: RecordState = RecordState.DISCOVERED

    # Identificatori esterni
    doi: Optional[str] = None
    pmid: Optional[str] = None

    # Metadati bibliografici
    title: Optional[str] = None
    abstract: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    url: Optional[str] = None

    # Open access / full text
    oa_url: Optional[str] = None
    oa_status: Optional[str] = None          # es. "gold", "green", "closed", "unknown"
    full_text: Optional[str] = None          # popolato solo se recuperabile legalmente
    # Disponibilità del contenuto al momento dell'estrazione: cattura la distinzione
    # degli stati "full_text_available" / "abstract_only" (lo stato di lifecycle
    # avanza a EXTRACTED, quindi la marcatura vive qui). Valori: RecordState.*.value.
    content_availability: Optional[str] = None

    # Provenienza e citation chasing
    source_dbs: List[str] = Field(default_factory=list, description="DB da cui proviene il record.")
    references: List[str] = Field(default_factory=list, description="DOI/ID dei lavori citati (per citation chasing).")
    seed_for_chasing: bool = False           # True se usato come seme per il citation chasing
    discovered_via: Optional[str] = None     # es. "query" oppure "citation_chase:<id>"

    # Payload grezzo per audit, indicizzato per DB di origine
    raw: Dict[str, Any] = Field(default_factory=dict)

    # Risultati degli agenti (popolati progressivamente)
    screening: Optional["ScreeningResult"] = None
    verification: Optional["VerificationResult"] = None
    extraction: Optional["Extraction"] = None
    quality: Optional["QualityAssessment"] = None
    exclusion_reason: Optional[str] = None

    def normalized_doi(self) -> Optional[str]:
        return normalize_doi(self.doi)


# --------------------------------------------------------------------------- #
# Screening
# --------------------------------------------------------------------------- #
class ScreeningResult(BaseModel):
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Pertinenza 0-1 rispetto al topic.")
    population_type: PopulationType = PopulationType.UNCLEAR
    is_cycling: bool = False
    decision: str = Field(..., description="'include' oppure 'exclude'.")
    reason: str = Field(..., description="Motivo sempre registrato (anche in caso di inclusione).")
    signals: Dict[str, Any] = Field(default_factory=dict, description="Segnali usati per la decisione (audit).")
    assessed_by: str = "heuristic"           # "llm" oppure "heuristic"


# --------------------------------------------------------------------------- #
# Verifica
# --------------------------------------------------------------------------- #
class VerificationResult(BaseModel):
    doi_valid: Optional[bool] = None
    pmid_valid: Optional[bool] = None
    title_match: Optional[bool] = None
    author_match: Optional[bool] = None
    year_match: Optional[bool] = None
    journal_match: Optional[bool] = None
    verified: bool = False                   # True solo se i controlli chiave concordano
    inconsistencies: List[str] = Field(default_factory=list)
    crossref_metadata: Dict[str, Any] = Field(default_factory=dict)
    pubmed_metadata: Dict[str, Any] = Field(default_factory=dict)
    checked_by: str = "crossref+pubmed"


# --------------------------------------------------------------------------- #
# Estrazione
# --------------------------------------------------------------------------- #
class ExtractedField(BaseModel):
    """Un singolo dato estratto, con la sua origine. `value=None` = dato assente (mai inventato)."""

    value: Optional[Any] = None
    source: DataSource = DataSource.NOT_AVAILABLE
    note: Optional[str] = None


class Extraction(BaseModel):
    """Estrazione strutturata. Ogni campo indica se proviene da full text o abstract."""

    title: ExtractedField = Field(default_factory=ExtractedField)
    authors: ExtractedField = Field(default_factory=ExtractedField)
    year: ExtractedField = Field(default_factory=ExtractedField)
    journal: ExtractedField = Field(default_factory=ExtractedField)
    doi: ExtractedField = Field(default_factory=ExtractedField)
    pmid: ExtractedField = Field(default_factory=ExtractedField)
    study_design: ExtractedField = Field(default_factory=ExtractedField)
    participants: ExtractedField = Field(default_factory=ExtractedField)
    training_level: ExtractedField = Field(default_factory=ExtractedField)
    sex: ExtractedField = Field(default_factory=ExtractedField)
    age: ExtractedField = Field(default_factory=ExtractedField)
    sample_size: ExtractedField = Field(default_factory=ExtractedField)
    protocol: ExtractedField = Field(default_factory=ExtractedField)
    comparator: ExtractedField = Field(default_factory=ExtractedField)
    duration: ExtractedField = Field(default_factory=ExtractedField)
    outcomes: ExtractedField = Field(default_factory=ExtractedField)
    results: ExtractedField = Field(default_factory=ExtractedField)
    effect_size: ExtractedField = Field(default_factory=ExtractedField)
    limitations: ExtractedField = Field(default_factory=ExtractedField)
    conflicts_of_interest: ExtractedField = Field(default_factory=ExtractedField)

    based_on: DataSource = DataSource.ABSTRACT   # su cosa si è basata l'estrazione complessiva
    extracted_by: str = "heuristic"


# --------------------------------------------------------------------------- #
# Qualità
# --------------------------------------------------------------------------- #
class QualityAssessment(BaseModel):
    study_type: str = "unknown"              # es. "RCT", "crossover", "cohort", "review", "meta-analysis"
    methodological_quality: QualityLevel = QualityLevel.LOW
    confidence_level: QualityLevel = QualityLevel.LOW
    transferability_to_competitive_cyclists: QualityLevel = QualityLevel.LOW
    # Dimensioni valutate: sample, control, randomization, duration, measures, transferability
    dimensions: Dict[str, str] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)
    assessed_by: str = "heuristic"
    # NB: il numero di citazioni non è mai usato come misura di qualità.


# --------------------------------------------------------------------------- #
# Ricerca (contenitore di sessione)
# --------------------------------------------------------------------------- #
class Research(BaseModel):
    id: str
    topic: str
    status: ResearchStatus = ResearchStatus.CREATED
    queries: List[str] = Field(default_factory=list)
    synonyms: Dict[str, List[str]] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    stats: Dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Profilo atleta
# --------------------------------------------------------------------------- #
class AthleteProfile(BaseModel):
    name: str
    age: Optional[int] = None
    sex: Optional[str] = None
    category: Optional[str] = None           # es. "elite", "U23", "master", "amatore cat. 2"
    level: Optional[str] = None              # es. "competitivo", "ricreativo"
    discipline: Optional[str] = None         # es. "strada", "MTB", "pista"
    weekly_hours: Optional[float] = None
    weekly_tss: Optional[float] = None
    ftp_w: Optional[float] = None
    ftp_w_kg: Optional[float] = None
    vo2max: Optional[float] = None
    goals: List[str] = Field(default_factory=list)
    history: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


def make_record_id(
    research_id: str,
    doi: Optional[str] = None,
    pmid: Optional[str] = None,
    title: Optional[str] = None,
) -> str:
    """Id interno stabile per un record, derivato dall'identificatore più forte disponibile.

    Include `research_id` per evitare collisioni globali quando ricerche diverse
    scoprono lo stesso lavoro. Due record della stessa opera provenienti da fonti
    diverse ma con lo stesso DOI/PMID ricevono lo stesso id (utile alla dedup).
    """
    import hashlib
    import re as _re

    key = normalize_doi(doi)
    if not key and pmid:
        key = f"pmid:{pmid.strip()}"
    if not key and title:
        key = _re.sub(r"\s+", " ", title.strip().lower())
    key = key or ""
    digest = hashlib.sha1(f"{research_id}::{key}".encode("utf-8")).hexdigest()
    return digest[:16]


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """Normalizza un DOI per il confronto (lowercase, senza prefisso URL)."""
    if not doi:
        return None
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "https://dx.doi.org/"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.strip("/ ") or None


# Ricostruzione dei forward-reference nei modelli annidati
PaperRecord.model_rebuild()
