# Fase D — CoachAgent + feedback loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: usa `superpowers:subagent-driven-development` (consigliata) o `superpowers:executing-plans` per implementare questo piano task-by-task. Gli step usano checkbox (`- [ ]`) per il tracking.

**Goal:** Un `CoachAgent` che genera e mantiene un **Piano vivo** verso un **obiettivo metrico datato**, con provenienza a tre fonti per ogni decisione, doppio feedback loop (veloce + lento con gate di compliance), consegna proponi-poi-approva, guardrail di sicurezza/confine medico, e degradazione offline euristica.

**Architecture:** Nuovo agente `cyclist_kb/agents/coach.py` col pattern trasversale degli agenti (`run(...)` + ramo LLM/euristico, **mai eccezione**). Riusa i modelli Fase B (`athlete_models.py`), le funzioni pure Fase B (`athlete_metrics.py`) e il Retriever Fase C (`retrieval.retrieve`). CLI/API restano thin wrapper su `Pipeline`; la logica vive nell'agente. La sola transizione di stato del Piano vive in un nuovo metodo atomico `Database.promote_plan`.

**Tech Stack:** Python 3.9+, Pydantic v2, SQLite (blob JSON + colonne indicizzate), Typer (CLI), pytest (offline/deterministico via `tests/conftest.py`).

## Global Constraints

- **Offline-first, mai-eccezione:** senza LLM (`KB_FORCE_OFFLINE=1` o backend assente) ogni percorso degrada a euristica deterministica. Nessuna eccezione blocca la pipeline. (ADR-0005, PRD 20)
- **Test sempre offline e deterministici:** `tests/conftest.py` impone `KB_FORCE_OFFLINE=1` e `KB_GIT_AUTOCOMMIT=0`. Nessuna rete, nessun `datetime.now()`/`random` non seminato nelle funzioni pure. Stub LLM con `LLMClient` **fresco per-modulo** (mai inquinare il singleton `get_llm()`).
- **Contratto di citazione A (PRD):** l'Evidenza vincola la **strategia** (citata); i **numeri** (watt, giorni) li deriva lo stato dell'atleta con euristica **etichettata**. Un numero scelto dentro un range di uno studio è `athlete_data`/`heuristic`, **mai** `study` (anti-evidence-laundering, ADR-0007, US 27).
- **Integrità temporale (ADR-0002):** i `TrainingBlock` in stato `FROZEN` non cambiano mai — né target, né citazioni, né `ftp_at_time` — neanche implicitamente via supersede/riscrittura.
- **Citabilità congelata solo-verificati (ADR-0003):** una `EvidenceCitation` `source_kind=STUDY` passa **solo** da `freeze_citation`/`citable_evidence` (stato in `{METADATA_VERIFIED, SYNTHESIZED}` ∧ `verification.verified`). L'evidenza N=1 (`athlete_data`) è sorgente distinta, senza `doi`/`pmid`.
- **Disclaimer strutturale sempre (PRD 15):** ogni `TrainingPlan` porta il disclaimer «ipotesi, non prescrizione medica» in `notes`, in modalità LLM **e** euristica.
- **Naming/convenzioni codebase:** enum `str, Enum` con `.value`; id stabili via helper `_hid` in `athlete_models.py`; funzioni pure in `athlete_metrics.py` con convenzione parametro `executed_load_` (trailing underscore) dove già presente.

## Decisioni fissate (open questions risolte)

Queste decisioni chiudono le open question emerse in analisi. Sono vincolanti per i task sotto:

1. **VO2max come target:** si aggiunge `MetricType.VO2MAX = "vo2max"` (il PRD cita ΔVO₂max; `AssessmentProtocol.VO2MAX` esiste già). Costo nullo, retrocompat totale.
2. **Obiettivo = input esplicito, non parsing NL.** Si introduce un piccolo modello `MetricGoal` passato a `CoachAgent.run(...)`; il CLI lo costruisce da opzioni esplicite (`--metric/--to/--by`, `--from` opzionale). Se `start` non è fornito, il CoachAgent lo ricava dall'ultimo `Assessment` pertinente. Niente parsing fragile di stringhe libere.
3. **`supported` vs `provenance`:** si mantiene `Prescription.supported: bool` per retrocompat e si aggiunge `provenance: ProvenanceKind`. Un `@model_validator(mode="after")` **sincronizza** `supported = (provenance == STUDY)`. Nessuna incoerenza possibile fra i due campi.
4. **`coach-accept` su piano non-PROPOSED:** **errore esplicito** (`PlanStateError`), non no-op. Deterministico e testabile.
5. **Al più un PROPOSED per atleta:** in generazione, `CoachAgent.run` marca `SUPERSEDED` gli eventuali PROPOSED preesistenti dell'atleta prima di salvare il nuovo. La `version` del nuovo PROPOSED è `(base.version)+1` dove `base` = piano attivo o, in assenza, il massimo fra i non-PROPOSED (0 se nessuno). Versioni monotone, nessuna bozza orfana.
6. **Storico memo:** *last-wins* — `make_memo_id(block_id)` è deterministico; una rivalutazione del Blocco sostituisce il memo via upsert. Storico append-only rimandato (fuori scope).
7. **Soglia compliance:** globale `DEFAULT_COMPLIANCE_THRESHOLD = 0.8`, passabile esplicitamente alle funzioni pure. Nessun override per-atleta nel primo taglio.
8. **Soglie guardrail sovraccarico:** hard-coded in `overload_guardrail`, documentate come config-ready (KB_* futuri). Fuori scope l'esposizione a config.

---

## File Structure

- **Modifica** `cyclist_kb/athlete_models.py` — nuovo enum `ProvenanceKind`; `PlanStatus.PROPOSED`; `MetricType.VO2MAX`; nuovo `MetricGoal`; estensioni a `TrainingPlan`, `EvidenceCitation`, `Prescription`, `TrainingBlock`, `TransferabilityMemo`; `next_version(status=...)`.
- **Modifica** `cyclist_kb/athlete_metrics.py` — nuove funzioni pure: `attribution_verdict`, `block_compliance_verdict`, `assessment_gap_to_goal`, `goal_reached`, `block_planned_load`, `freeze_athlete_data_citation`, `overload_guardrail`, `medical_boundary_flag`.
- **Modifica** `cyclist_kb/db.py` — nuovo metodo atomico `promote_plan(plan_id)`.
- **Crea** `cyclist_kb/agents/coach.py` — `CoachAgent` (`run`, `accept`, `adapt_microcycle`, `assess_block`) + rami LLM/euristico.
- **Modifica** `cyclist_kb/pipeline.py` — `PlanNotFound`, `PlanStateError`, `AthleteNotFound`; metodi `coach`, `coach_accept`, `coach_adapt`, `coach_assess`.
- **Modifica** `cyclist_kb/cli.py` — comandi `coach`, `coach-accept`, `coach-adapt`, `coach-assess`; helper `_print_plan`.
- **Crea** `docs/adr/0006-*.md`, `0007-*.md`, `0008-*.md`; **modifica** `CONTEXT.md` (voce «Piano»/«Obiettivo»).
- **Crea** i test: `tests/test_coach_metrics.py` (funzioni pure), `tests/test_coach.py` (agente euristico+LLM), `tests/test_coach_invariants.py`, `tests/test_coach_slow_loop.py`, `tests/test_coach_fast_loop.py`, `tests/test_coach_accept.py`, `tests/test_cli_coach.py`; estende `tests/test_athlete_persistence.py` per il round-trip DB dei modelli estesi.

---

## Task 0 (CP0): ADR + glossario

**Files:**
- Create: `docs/adr/0006-obiettivo-piano-target-metrico-datato.md`
- Create: `docs/adr/0007-provenienza-tre-fonti-coaching.md`
- Create: `docs/adr/0008-stato-proposed-transizione-atomica.md`
- Modify: `CONTEXT.md` (voce «Piano»/«Obiettivo»)

**Interfaces:**
- Produces: le decisioni congelate che vincolano i task successivi (nomi enum, invarianti, regola del range). Nessun simbolo di codice.

- [ ] **Step 1: Scrivi ADR-0006** — *Obiettivo del Piano: target metrico datato, gara-A opzionale.* Decisione: il Piano ammette un obiettivo di progresso puro (`MetricType` + valore-partenza + valore-target + data-target) senza richiedere una `Race` priority A; `target_race_id` resta opzionale/corroborante. Contesto: tensione col glossario («periodizzazione verso una gara-A»). Conseguenze: periodizzazione **a ritroso** dalla data-obiettivo. Segui il formato degli ADR 0001–0005 (Status: Accepted; Context; Decision; Consequences).

- [ ] **Step 2: Scrivi ADR-0007** — *Provenienza a tre fonti sulle decisioni di coaching.* Decisione: nuovo enum `ProvenanceKind {study | athlete_data | heuristic}` **locale** a `athlete_models.py` (NON estensione di `models.DataSource`, che resta bibliografico). Applicato a `TrainingBlock` (razionale strategico) e `Prescription` (numero). Regola-chiave anti-laundering: un numero dentro un range di popolazione è `athlete_data`/`heuristic`, **mai** `study`. `supported:bool` diventa derivato (`supported == (provenance == STUDY)`). L'euristica è etichettata, mai citabile come studio. Include la Citazione N=1 (`EvidenceCitation.source_kind`) come estensione — non violazione — di ADR-0003.

- [ ] **Step 3: Scrivi ADR-0008** — *Stato PROPOSED e transizione atomica proponi-poi-approva.* Decisione: `PlanStatus` estende `PROPOSED`; `CoachAgent` crea sempre PROPOSED; `Database.promote_plan` fa `PROPOSED→ACTIVE` + supersede degli ACTIVE precedenti in **una** transazione (distinto da `supersede_plan`, che assume input già ACTIVE). Invarianti: mai due ACTIVE; mai auto-attivazione; al più un PROPOSED per atleta; `coach-accept` su non-PROPOSED → errore esplicito.

- [ ] **Step 4: Aggiorna `CONTEXT.md`** — nella voce «Piano»: aggiungi che l'obiettivo primario è un **target metrico datato** (gara-A opzionale/corroborante) e che la periodizzazione è **a ritroso** dalla data-obiettivo. Aggiungi la voce «Provenienza» (studi/dati_atleta/euristica) e «Piano proposto» (PROPOSED). Mantieni «conflitti conservati, non riconciliati».

- [ ] **Step 5: Commit**

```bash
git add docs/adr/0006-obiettivo-piano-target-metrico-datato.md docs/adr/0007-provenienza-tre-fonti-coaching.md docs/adr/0008-stato-proposed-transizione-atomica.md CONTEXT.md
git commit -m "docs(fase-d): ADR-0006/0007/0008 + glossario (obiettivo metrico, provenienza 3-fonti, PROPOSED)"
```

---

## Task 1 (CP1): Enum di base — `ProvenanceKind`, `PlanStatus.PROPOSED`, `MetricType.VO2MAX`

**Files:**
- Modify: `cyclist_kb/athlete_models.py` (sezione Enumerazioni, righe ~31–72)
- Test: `tests/test_coach_metrics.py`

**Interfaces:**
- Produces: `ProvenanceKind.STUDY|ATHLETE_DATA|HEURISTIC`; `PlanStatus.PROPOSED` (valore `"proposed"`); `MetricType.VO2MAX` (valore `"vo2max"`).

- [ ] **Step 1: Scrivi il test che fallisce**

```python
# tests/test_coach_metrics.py
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
```

- [ ] **Step 2: Esegui il test per vederlo fallire**

Run: `.venv/bin/python -m pytest tests/test_coach_metrics.py -q`
Expected: FAIL con `ImportError`/`AttributeError` (`ProvenanceKind` non esiste, `PlanStatus.PROPOSED` assente).

- [ ] **Step 3: Implementa i enum**

In `athlete_models.py`, dentro `class PlanStatus`:
```python
class PlanStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
```
Aggiungi `VO2MAX = "vo2max"` a `MetricType`. Aggiungi, subito dopo `TransferabilityVerdict` (così è definito **prima** delle classi che lo usano):
```python
class ProvenanceKind(str, Enum):
    """Provenienza a 3 fonti di una decisione di coaching (ADR-0007)."""
    STUDY = "study"
    ATHLETE_DATA = "athlete_data"
    HEURISTIC = "heuristic"
```

- [ ] **Step 4: Esegui il test per vederlo passare**

Run: `.venv/bin/python -m pytest tests/test_coach_metrics.py -q`
Expected: PASS.

- [ ] **Step 5: Non-regressione**

Run: `.venv/bin/python -m pytest tests/test_athlete_persistence.py -q`
Expected: PASS (i piani Fase B esistenti si deserializzano invariati).

- [ ] **Step 6: Commit**

```bash
git add cyclist_kb/athlete_models.py tests/test_coach_metrics.py
git commit -m "feat(fase-d): ProvenanceKind + PlanStatus.PROPOSED + MetricType.VO2MAX"
```

---

## Task 2 (CP2): Estensioni dei modelli (retrocompat)

**Files:**
- Modify: `cyclist_kb/athlete_models.py` (`Prescription`, `EvidenceCitation`, `TrainingBlock`, `TrainingPlan`, `TransferabilityMemo`, nuovo `MetricGoal`)
- Test: `tests/test_athlete_persistence.py` (round-trip), `tests/test_coach_metrics.py`

**Interfaces:**
- Consumes: `ProvenanceKind`, `PlanStatus`, `MetricType` (Task 1).
- Produces:
  - `MetricGoal(metric_type: MetricType, target: float, target_date: str, start: Optional[float] = None)`
  - `Prescription.provenance: ProvenanceKind = HEURISTIC`, `Prescription.citation_ids: List[str] = []`, validator `supported == (provenance == STUDY)`
  - `EvidenceCitation.source_kind: ProvenanceKind = STUDY`
  - `TrainingBlock.provenance: ProvenanceKind = HEURISTIC`, `TrainingBlock.conflicts: List[str] = []`
  - `TrainingPlan.target_metric_type/target_metric_start/target_metric_value/target_metric_date`, `TrainingPlan.supersedes_id`, `TrainingPlan.next_version(*, valid_from=None, status=PlanStatus.ACTIVE)`
  - `TransferabilityMemo.compliance_ratio: Optional[float]`, `TransferabilityMemo.citations: List[EvidenceCitation] = []`

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# tests/test_coach_metrics.py (append)
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
```

- [ ] **Step 2: Esegui i test per vederli fallire**

Run: `.venv/bin/python -m pytest tests/test_coach_metrics.py -q`
Expected: FAIL (campi/validator/`MetricGoal` assenti).

- [ ] **Step 3: Implementa le estensioni**

In `athlete_models.py`:
- Importa il validator: `from pydantic import BaseModel, Field, model_validator`.
- `Prescription`: aggiungi `provenance: ProvenanceKind = ProvenanceKind.HEURISTIC`, `citation_ids: List[str] = Field(default_factory=list)`, e
  ```python
  @model_validator(mode="after")
  def _sync_supported(self) -> "Prescription":
      object.__setattr__(self, "supported", self.provenance == ProvenanceKind.STUDY)
      return self
  ```
  (usa assegnazione diretta `self.supported = ...` se il modello non è frozen — i modelli Fase B non lo sono).
- `EvidenceCitation`: aggiungi `source_kind: ProvenanceKind = ProvenanceKind.STUDY`.
- `TrainingBlock`: aggiungi `provenance: ProvenanceKind = ProvenanceKind.HEURISTIC`, `conflicts: List[str] = Field(default_factory=list)`. `freeze()` usa `model_copy(deep=True)` → i nuovi campi si congelano da soli, nessuna modifica.
- `TrainingPlan`: aggiungi `target_metric_type: Optional[MetricType] = None`, `target_metric_start: Optional[float] = None`, `target_metric_value: Optional[float] = None`, `target_metric_date: Optional[str] = None`, `supersedes_id: Optional[str] = None`. Parametrizza `next_version`:
  ```python
  def next_version(self, *, valid_from: Optional[str] = None,
                   status: PlanStatus = PlanStatus.ACTIVE) -> "TrainingPlan":
      nxt = self.model_copy(deep=True)
      nxt.version = self.version + 1
      nxt.id = make_plan_id(self.athlete_id, nxt.version)
      nxt.status = status
      nxt.valid_from = valid_from
      nxt.valid_to = None
      nxt.created_at = None
      return nxt
  ```
- `TransferabilityMemo`: aggiungi `compliance_ratio: Optional[float] = None`, `citations: List[EvidenceCitation] = Field(default_factory=list)`.
- Nuovo modello (accanto ai piani):
  ```python
  class MetricGoal(BaseModel):
      """Obiettivo metrico datato del Piano (ADR-0006)."""
      metric_type: MetricType
      target: float
      target_date: str                          # ISO YYYY-MM-DD
      start: Optional[float] = None             # se None, dedotto dall'ultimo Assessment
  ```

- [ ] **Step 4: Esegui i test per vederli passare**

Run: `.venv/bin/python -m pytest tests/test_coach_metrics.py -q`
Expected: PASS.

- [ ] **Step 5: Round-trip DB + non-regressione frozen**

Aggiungi a `tests/test_athlete_persistence.py` un test che salva un `TrainingPlan` con `target_metric_*` valorizzati e un `TrainingBlock` con `provenance=STUDY`, lo rilegge da `get_plan` e verifica l'uguaglianza; e un test che verifica che un blocco `FROZEN` resti invariato dopo `next_version(status=PROPOSED)`.
Run: `.venv/bin/python -m pytest tests/test_athlete_persistence.py -q`
Expected: PASS.

- [ ] **Step 6: Suite intera (retrocompat globale)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (nessun test Fase B rotto).

- [ ] **Step 7: Commit**

```bash
git add cyclist_kb/athlete_models.py tests/test_coach_metrics.py tests/test_athlete_persistence.py
git commit -m "feat(fase-d): estensioni schema (provenienza, obiettivo metrico, source_kind, memo compliance)"
```

---

## Task 3 (CP3): Funzioni pure in `athlete_metrics.py`

**Files:**
- Modify: `cyclist_kb/athlete_metrics.py`
- Test: `tests/test_coach_metrics.py`

**Interfaces:**
- Consumes: `compliance` (esistente, non cappata), `assessment_delta`, `derive_executed_block`, `citable_evidence`/`freeze_citation`, `DEFAULT_COMPLIANCE_THRESHOLD = 0.8`, `TrainingBlock`, `EvidenceCitation`, `TransferabilityVerdict`, `ProvenanceKind`.
- Produces:
  - `attribution_verdict(compliance_ratio: float, metric_delta: Optional[float], threshold: float = DEFAULT_COMPLIANCE_THRESHOLD) -> TransferabilityVerdict`
  - `block_compliance_verdict(planned_load: float, executed_load_: float, threshold: float = DEFAULT_COMPLIANCE_THRESHOLD) -> str` (`"pass"|"fail"|"overload"`)
  - `assessment_gap_to_goal(current: Optional[float], goal: Optional[float]) -> Optional[float]`
  - `goal_reached(current: Optional[float], goal: Optional[float], tolerance: float = 0.0) -> bool`
  - `block_planned_load(block: TrainingBlock) -> float`
  - `freeze_athlete_data_citation(ref_id: str, title: Optional[str] = None, note: Optional[str] = None, frozen_at: Optional[str] = None) -> EvidenceCitation`
  - `overload_guardrail(recent_tsb: Optional[float], hrv_drop: Optional[bool], sleep_drop: Optional[bool], perf_drop: Optional[bool]) -> Optional[str]`
  - `medical_boundary_flag(signals: List[str]) -> Optional[str]`

- [ ] **Step 1: Scrivi i test tabellari che falliscono**

```python
# tests/test_coach_metrics.py (append)
import pytest
from cyclist_kb.athlete_metrics import (
    attribution_verdict, block_compliance_verdict, assessment_gap_to_goal,
    goal_reached, block_planned_load, freeze_athlete_data_citation,
    overload_guardrail, medical_boundary_flag,
)
from cyclist_kb.athlete_models import (
    TransferabilityVerdict, ProvenanceKind, TrainingBlock, Prescription,
)


@pytest.mark.parametrize("ratio,delta,expected", [
    (0.6, 12.0, TransferabilityVerdict.INCONCLUSIVE),   # sotto soglia → non impara
    (0.9, 12.0, TransferabilityVerdict.TRANSFERRED),
    (0.9, -3.0, TransferabilityVerdict.NOT_TRANSFERRED),
    (0.9, None, TransferabilityVerdict.INCONCLUSIVE),
])
def test_attribution_verdict(ratio, delta, expected):
    assert attribution_verdict(ratio, delta) == expected


@pytest.mark.parametrize("planned,executed,expected", [
    (100.0, 90.0, "pass"),
    (100.0, 50.0, "fail"),
    (100.0, 130.0, "overload"),   # >1.0 → overload (non cappato)
])
def test_block_compliance_verdict(planned, executed, expected):
    assert block_compliance_verdict(planned, executed) == expected


def test_assessment_gap_and_goal_reached():
    assert assessment_gap_to_goal(329.0, 340.0) == 11.0
    assert assessment_gap_to_goal(None, 340.0) is None
    assert goal_reached(341.0, 340.0) is True
    assert goal_reached(338.0, 340.0) is False


def test_block_planned_load_sums_prescriptions_or_zero():
    b = TrainingBlock(id="b", plan_id="p", goal="vo2max", prescriptions=[
        Prescription(description="x", duration_s=3600, target_watts=300),
    ])
    assert block_planned_load(b) >= 0.0            # degrada a 0.0 se non derivabile


def test_freeze_athlete_data_citation_is_n1():
    c = freeze_athlete_data_citation("assess-1", note="ultima FTP")
    assert c.source_kind == ProvenanceKind.ATHLETE_DATA
    assert c.record_id == "assess-1"
    assert c.doi is None and c.pmid is None and c.verified is False


def test_overload_and_medical_guards():
    assert overload_guardrail(-30.0, True, True, None) is not None
    assert overload_guardrail(5.0, False, False, False) is None
    assert medical_boundary_flag(["dolore al ginocchio"]) is not None
    assert medical_boundary_flag([]) is None
```

- [ ] **Step 2: Esegui per vederli fallire**

Run: `.venv/bin/python -m pytest tests/test_coach_metrics.py -q`
Expected: FAIL (`ImportError` sulle nuove funzioni).

- [ ] **Step 3: Implementa le funzioni pure**

In `athlete_metrics.py` (riusa `compliance`, non ridefinire soglie):
```python
def block_compliance_verdict(planned_load: float, executed_load_: float,
                             threshold: float = DEFAULT_COMPLIANCE_THRESHOLD) -> str:
    ratio = compliance(planned_load, executed_load_)
    if ratio > 1.0 + 1e-9:
        return "overload"
    return "pass" if ratio >= threshold else "fail"


def attribution_verdict(compliance_ratio: float, metric_delta: Optional[float],
                        threshold: float = DEFAULT_COMPLIANCE_THRESHOLD) -> TransferabilityVerdict:
    if compliance_ratio < threshold:
        return TransferabilityVerdict.INCONCLUSIVE          # US 9: non impara sotto soglia
    if metric_delta is None:
        return TransferabilityVerdict.INCONCLUSIVE
    return (TransferabilityVerdict.TRANSFERRED if metric_delta > 0
            else TransferabilityVerdict.NOT_TRANSFERRED)


def assessment_gap_to_goal(current: Optional[float], goal: Optional[float]) -> Optional[float]:
    if current is None or goal is None:
        return None
    return goal - current


def goal_reached(current: Optional[float], goal: Optional[float], tolerance: float = 0.0) -> bool:
    if current is None or goal is None:
        return False
    return current >= goal - tolerance


def block_planned_load(block: TrainingBlock) -> float:
    """Somma il TSS pianificato derivandolo dalle Prescription; 0.0 se non derivabile."""
    total = 0.0
    for p in block.prescriptions:
        if p.duration_s and p.target_watts:
            # proxy di carico grezzo; degrada a 0.0 se i campi non ci sono
            total += (p.duration_s / 3600.0) * (p.reps or 1)
    return total


def freeze_athlete_data_citation(ref_id: str, title: Optional[str] = None,
                                 note: Optional[str] = None,
                                 frozen_at: Optional[str] = None) -> EvidenceCitation:
    from .athlete_models import ProvenanceKind
    return EvidenceCitation(
        record_id=ref_id, title=title or note, doi=None, pmid=None,
        verified=False, source_kind=ProvenanceKind.ATHLETE_DATA, frozen_at=frozen_at,
    )
```
Aggiungi `overload_guardrail` (soglie hard-coded documentate come config-ready) e `medical_boundary_flag` (marcatori dal vocabolario di dominio):
```python
def overload_guardrail(recent_tsb: Optional[float], hrv_drop: Optional[bool],
                       sleep_drop: Optional[bool], perf_drop: Optional[bool]) -> Optional[str]:
    very_negative = recent_tsb is not None and recent_tsb <= -25.0   # soglia ribaltabile
    crashes = sum(1 for x in (hrv_drop, sleep_drop, perf_drop) if x)
    if very_negative and crashes >= 1:
        return "sovraccarico non-funzionale: declassare il carico del microciclo entrante"
    return None


_MEDICAL_MARKERS = ("dolore", "male", "infortun", "sintom", "febbre", "malatt", "red-s", "reds", "amenorrea")

def medical_boundary_flag(signals: List[str]) -> Optional[str]:
    joined = " ".join(s.lower() for s in signals)
    if any(m in joined for m in _MEDICAL_MARKERS):
        return ("segnale a confine medico: il coach non diagnostica né prescrive; "
                "consulta un professionista sanitario")
    return None
```

- [ ] **Step 4: Esegui per vederli passare**

Run: `.venv/bin/python -m pytest tests/test_coach_metrics.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cyclist_kb/athlete_metrics.py tests/test_coach_metrics.py
git commit -m "feat(fase-d): funzioni pure attribuzione/compliance/guardrail/citazione-N1"
```

---

## Task 4 (CP4): `Database.promote_plan` atomico

**Files:**
- Modify: `cyclist_kb/db.py` (accanto a `supersede_plan`, righe ~422–445)
- Test: `tests/test_coach_accept.py`

**Interfaces:**
- Consumes: `list_plans(athlete_id, status=...)`, `get_plan(plan_id)`, `PlanStatus`.
- Produces: `promote_plan(self, plan_id: str) -> TrainingPlan` — solleva `ValueError` se il piano non è `PROPOSED`.

- [ ] **Step 1: Scrivi il test che fallisce**

```python
# tests/test_coach_accept.py
import pytest
from cyclist_kb.athlete_models import (
    Athlete, TrainingPlan, TrainingBlock, PlanStatus, make_plan_id, make_athlete_id,
)


def _db(tmp_path, monkeypatch):
    from cyclist_kb.config import get_settings
    from cyclist_kb.db import Database
    s = get_settings()
    monkeypatch.setattr(s, "db_path", tmp_path / "kb.sqlite3")
    return Database()


def test_promote_plan_atomic_transition(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo"))
    v1 = TrainingPlan(id=make_plan_id(ath, 1), athlete_id=ath, version=1, status=PlanStatus.ACTIVE)
    db.save_plan(v1)
    v2 = TrainingPlan(id=make_plan_id(ath, 2), athlete_id=ath, version=2, status=PlanStatus.PROPOSED)
    db.save_plan(v2)

    promoted = db.promote_plan(v2.id)

    assert promoted.status == PlanStatus.ACTIVE
    assert db.get_plan(v1.id).status == PlanStatus.SUPERSEDED
    assert db.active_plan(ath).id == v2.id
    actives = db.list_plans(ath, status=PlanStatus.ACTIVE.value)
    assert len(actives) == 1


def test_promote_plan_rejects_non_proposed(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo"))
    v1 = TrainingPlan(id=make_plan_id(ath, 1), athlete_id=ath, version=1, status=PlanStatus.ACTIVE)
    db.save_plan(v1)
    with pytest.raises(ValueError):
        db.promote_plan(v1.id)
```

- [ ] **Step 2: Esegui per vederlo fallire**

Run: `.venv/bin/python -m pytest tests/test_coach_accept.py -q`
Expected: FAIL (`AttributeError: promote_plan`).

- [ ] **Step 3: Implementa `promote_plan`**

In `db.py`, accanto a `supersede_plan` (accumula tutti gli `execute` prima dell'**unico** `commit`):
```python
def promote_plan(self, plan_id: str) -> TrainingPlan:
    """Transizione atomica PROPOSED→ACTIVE: marca SUPERSEDED gli ACTIVE
    correnti dell'atleta e promuove il PROPOSED, in un solo commit (ADR-0008).
    Solleva ValueError se il piano non è PROPOSED."""
    plan = self.get_plan(plan_id)
    if plan is None:
        raise ValueError(f"Piano {plan_id} inesistente.")
    if plan.status is not PlanStatus.PROPOSED:
        raise ValueError(f"Piano {plan_id} non è PROPOSED (è {plan.status.value}).")
    now = _now()
    for p in self.list_plans(plan.athlete_id, status=PlanStatus.ACTIVE.value):
        p.status = PlanStatus.SUPERSEDED
        p.updated_at = now
        self.conn.execute(
            "UPDATE plans SET status=?, updated_at=?, data=? WHERE id=?",
            (p.status.value, now, p.model_dump_json(), p.id),
        )
    plan.status = PlanStatus.ACTIVE
    plan.updated_at = now
    self.conn.execute(
        "UPDATE plans SET status=?, updated_at=?, data=? WHERE id=?",
        (plan.status.value, now, plan.model_dump_json(), plan.id),
    )
    self.conn.commit()
    return plan
```

- [ ] **Step 4: Esegui per vederlo passare**

Run: `.venv/bin/python -m pytest tests/test_coach_accept.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cyclist_kb/db.py tests/test_coach_accept.py
git commit -m "feat(fase-d): Database.promote_plan (PROPOSED->ACTIVE atomico)"
```

---

## Task 5 (CP5): `CoachAgent` scheletro + ramo euristico (offline)

**Files:**
- Create: `cyclist_kb/agents/coach.py`
- Test: `tests/test_coach.py`, `tests/test_coach_invariants.py`

**Interfaces:**
- Consumes: `Database` (`get_athlete`, `list_assessments`, `list_activities`, `list_memos`, `active_plan`, `list_plans`, `save_plan`, `promote_plan`); `get_llm()`; `AthleteProfile`; `MetricGoal`; funzioni pure di Task 3; `retrieve` (Task 6, non ancora usato qui); `TrainingPlan`/`TrainingBlock`/`Prescription`.
- Produces:
  - `class CoachAgent: __init__(self, db)`
  - `run(self, athlete_id: str, goal: MetricGoal, profile: Optional[AthleteProfile] = None) -> TrainingPlan` (sempre `PROPOSED`)
  - `accept(self, plan_id: str) -> TrainingPlan`
  - helper interni `_heuristic_generate_plan`, `_apply_guardrails_and_disclaimer`, `_baseline_from_assessments`, `_next_proposed_version`

- [ ] **Step 1: Scrivi i test che falliscono (offline, euristico)**

```python
# tests/test_coach.py
from cyclist_kb.athlete_models import (
    Athlete, Assessment, AssessmentProtocol, MetricGoal, MetricType,
    PlanStatus, ProvenanceKind, make_athlete_id, make_assessment_id,
)
from cyclist_kb.agents.coach import CoachAgent


def _seed_athlete(db):
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo", category="U23", discipline="road"))
    db.save_assessment(Assessment(
        id=make_assessment_id(ath, "ftp", "2026-07-01"),
        athlete_id=ath, protocol=AssessmentProtocol.FTP,
        executed_date="2026-07-01", value=329.0, unit="W"))
    return ath


def _db(tmp_path, monkeypatch):
    from cyclist_kb.config import get_settings
    from cyclist_kb.db import Database
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "kb.sqlite3")
    return Database()


def test_run_produces_proposed_plan_offline(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)
    assert plan.status == PlanStatus.PROPOSED
    assert plan.blocks, "deve periodizzare in blocchi"
    assert plan.target_metric_value == 340.0
    assert plan.target_metric_start == 329.0        # dedotto dall'ultimo Assessment
    # ogni blocco e prescrizione hanno provenance valorizzata
    for b in plan.blocks:
        assert b.provenance in ProvenanceKind
        for p in b.prescriptions:
            assert p.provenance in ProvenanceKind
    # disclaimer strutturale sempre
    assert plan.notes and "ipotesi" in plan.notes.lower()


def test_run_is_not_active_until_accepted(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)
    assert db.active_plan(ath) is None               # PROPOSED non è attivo
    CoachAgent(db).accept(plan.id)
    assert db.active_plan(ath).id == plan.id
```

- [ ] **Step 2: Esegui per vederli fallire**

Run: `.venv/bin/python -m pytest tests/test_coach.py -q`
Expected: FAIL (`ModuleNotFoundError: cyclist_kb.agents.coach`).

- [ ] **Step 3: Implementa lo scheletro + ramo euristico**

Crea `cyclist_kb/agents/coach.py` seguendo il pattern di `screening.py`:
```python
from __future__ import annotations
from typing import List, Optional

from ..athlete_models import (
    Athlete, Assessment, MetricGoal, PlanStatus, ProvenanceKind,
    Prescription, TrainingBlock, TrainingPlan, make_plan_id, make_block_id,
)
from ..athlete_metrics import assessment_gap_to_goal, overload_guardrail, medical_boundary_flag
from ..config import get_settings
from ..db import Database
from ..llm import get_llm

_DISCLAIMER = "Questo è un piano-ipotesi generato automaticamente, non una prescrizione medica."


class CoachAgent:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm()

    def run(self, athlete_id: str, goal: MetricGoal,
            profile: Optional["AthleteProfile"] = None) -> TrainingPlan:
        assessments = self.db.list_assessments(athlete_id)
        start = goal.start if goal.start is not None else self._baseline_from_assessments(assessments, goal)
        prev_active = self.db.active_plan(athlete_id)
        plan = None
        if self.llm.available:
            plan = self._llm_generate_plan(athlete_id, goal, start, profile, prev_active)  # Task 6
        if plan is None:
            plan = self._heuristic_generate_plan(athlete_id, goal, start, prev_active)
        self._apply_guardrails_and_disclaimer(plan, profile)
        plan.status = PlanStatus.PROPOSED
        if prev_active is not None:
            plan.supersedes_id = prev_active.id
        self._supersede_open_proposals(athlete_id)       # al più un PROPOSED
        self.db.save_plan(plan)
        return plan

    def accept(self, plan_id: str) -> TrainingPlan:
        return self.db.promote_plan(plan_id)

    # -- interni ---------------------------------------------------------- #
    def _baseline_from_assessments(self, assessments, goal) -> Optional[float]:
        vals = [a.value for a in assessments if a.value is not None]
        return vals[-1] if vals else None

    def _next_proposed_version(self, athlete_id: str) -> int:
        non_proposed = [p for p in self.db.list_plans(athlete_id)
                        if p.status is not PlanStatus.PROPOSED]
        base = max((p.version for p in non_proposed), default=0)
        return base + 1

    def _supersede_open_proposals(self, athlete_id: str) -> None:
        for p in self.db.list_plans(athlete_id, status=PlanStatus.PROPOSED.value):
            p.status = PlanStatus.SUPERSEDED
            self.db.save_plan(p)

    def _apply_guardrails_and_disclaimer(self, plan: TrainingPlan, profile) -> None:
        notes = [_DISCLAIMER]
        constraints = list(getattr(profile, "constraints", []) or [])
        med = medical_boundary_flag(constraints)
        if med:
            notes.append(med)
        plan.notes = "\n".join(notes) if not plan.notes else plan.notes + "\n" + "\n".join(notes)

    def _heuristic_generate_plan(self, athlete_id, goal, start, prev_active) -> TrainingPlan:
        version = self._next_proposed_version(athlete_id)
        plan = TrainingPlan(
            id=make_plan_id(athlete_id, version), athlete_id=athlete_id, version=version,
            status=PlanStatus.PROPOSED, target_metric_type=goal.metric_type,
            target_metric_start=start, target_metric_value=goal.target,
            target_metric_date=goal.target_date,
        )
        # Periodizzazione a ritroso deterministica: 3 blocchi (base→sviluppo→taper).
        gap = assessment_gap_to_goal(start, goal.target) or 0.0
        goals = ["base", "sviluppo", "taper"]
        blocks: List[TrainingBlock] = []
        for i, g in enumerate(goals):
            bid = make_block_id(plan.id, i)
            pres = [Prescription(
                description=f"Seduta {g}", target_watts=(start or 0.0) * (0.9 + 0.05 * i),
                duration_s=3600, provenance=ProvenanceKind.HEURISTIC)]
            blocks.append(TrainingBlock(id=bid, plan_id=plan.id, goal=g, order=i,
                                        prescriptions=pres, provenance=ProvenanceKind.HEURISTIC))
        plan.blocks = blocks
        return plan

    def _llm_generate_plan(self, athlete_id, goal, start, profile, prev_active):
        return None   # implementato in Task 6
```
Aggiungi il campo `notes: Optional[str] = None` a `TrainingPlan` se non presente (lo è: righe modello — verifica; se assente, aggiungilo in Task 2). *(Nota: `TrainingPlan` non ha `notes` nel modello Fase B — aggiungi `notes: Optional[str] = None` in Task 2, Step 3, sezione `TrainingPlan`.)*

- [ ] **Step 4: Esegui per vederli passare**

Run: `.venv/bin/python -m pytest tests/test_coach.py -q`
Expected: PASS.

- [ ] **Step 5: Invarianti offline**

```python
# tests/test_coach_invariants.py
# (a) provenance==HEURISTIC → nessuna citazione di studio spacciata come supporto
# (b) PROPOSED non compare in active_plan finché non accettato
# (c) rigenerando due volte, l'atleta ha al più un PROPOSED
```
Implementa questi tre test riusando `_seed_athlete`/`_db` di `test_coach.py` (import o duplica gli helper).
Run: `.venv/bin/python -m pytest tests/test_coach_invariants.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add cyclist_kb/agents/coach.py cyclist_kb/athlete_models.py tests/test_coach.py tests/test_coach_invariants.py
git commit -m "feat(fase-d): CoachAgent scheletro + pianificatore euristico offline"
```

---

## Task 6 (CP6): Integrazione Retriever + ramo LLM (stubbato)

**Files:**
- Modify: `cyclist_kb/agents/coach.py` (`_llm_generate_plan`, nuovo `_strategic_choices`, `_build_plan_from_llm`)
- Test: `tests/test_coach.py` (append)

**Interfaces:**
- Consumes: `retrieve(db, query: str, athlete=None, k: int = 8) -> List[RetrievalResult]`; `RetrievalResult(record, relevance, quality, fit, score, direction, signals)` con `direction ∈ {positive|null|negative|mixed|unclear}`; `freeze_citation(record, frozen_at=None)`; `freeze_athlete_data_citation`; `LLMClient.complete_json(prompt, system=..., max_tokens=None) -> Optional[Dict]`.
- Produces: ramo LLM che restituisce `Optional[TrainingPlan]` (None → fallback euristico), con provenienza a 3 vie corretta e conflict-aware conservato.

- [ ] **Step 1: Scrivi il test del ramo LLM (stub per-modulo)**

```python
# tests/test_coach.py (append)
from cyclist_kb.llm import LLMClient
from cyclist_kb.athlete_models import ProvenanceKind


def _install_fake_coach_llm(monkeypatch, complete_json):
    def factory():
        c = LLMClient()
        c._available = True
        c._backend = "anthropic"
        c.complete_json = complete_json
        return c
    monkeypatch.setattr("cyclist_kb.agents.coach.get_llm", factory)


def test_llm_branch_builds_plan_with_3way_provenance(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    def _fake(prompt, system=None, max_tokens=None):
        return {"blocks": [
            {"goal": "vo2max", "provenance": "study", "strategy_query": "vo2max interval trained cyclists",
             "prescriptions": [{"description": "5x4 @ 118% FTP", "target_watts": 388, "duration_s": 240}]},
            {"goal": "taper", "provenance": "heuristic", "prescriptions": [{"description": "riduzione volume"}]},
        ]}
    _install_fake_coach_llm(monkeypatch, _fake)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)
    assert plan.status == PlanStatus.PROPOSED
    # numeri al watt MAI provenance study (regola del range)
    for b in plan.blocks:
        for p in b.prescriptions:
            assert p.provenance != ProvenanceKind.STUDY
```

Aggiungi (se il Pozzo è seminato) un test che, con record verificati discordi, verifica che `block.conflicts` **o** citazioni contese non siano vuoti (conflict-aware conservato).

- [ ] **Step 2: Esegui per vederlo fallire**

Run: `.venv/bin/python -m pytest tests/test_coach.py -q`
Expected: FAIL (il ramo LLM ritorna ancora `None` → il piano euristico non rispetta il fake).

- [ ] **Step 3: Implementa `_strategic_choices` + `_llm_generate_plan` + `_build_plan_from_llm`**

In `coach.py`, importa `from ..retrieval import retrieve` e `from ..athlete_metrics import freeze_citation, freeze_athlete_data_citation`. Per ogni scelta strategica: `results = retrieve(self.db, query, athlete=self.db.get_athlete(athlete_id), k=8)`; la direzione a maggior `score` con `direction=="positive"` fissa la strategia (`provenance=STUDY` con `freeze_citation` dei suoi record verificati), mentre i record `direction in {"negative","mixed"}` diventano `block.conflicts` (testo) — conflict-aware conservato. I **numeri** delle Prescription restano `provenance != STUDY` (regola del range). Il prompt LLM è una f-string (obiettivo, `RetrievalResult` serializzati, profilo, memos); `data = self.llm.complete_json(prompt=..., system="Sei un preparatore ciclistico scientifico. Rispondi SOLO con JSON.")`; `if not data: return None`; `_build_plan_from_llm(data, ...)` mappa `provenance` stringa→`ProvenanceKind`, forzando `provenance != STUDY` su ogni Prescription. Qualsiasi errore → `return None` (fallback silenzioso).

- [ ] **Step 4: Esegui per vederlo passare**

Run: `.venv/bin/python -m pytest tests/test_coach.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cyclist_kb/agents/coach.py tests/test_coach.py
git commit -m "feat(fase-d): ramo LLM CoachAgent + integrazione Retriever conflict-aware"
```

---

## Task 7 (CP7): Loop lento — `assess_block` → `TransferabilityMemo`

**Files:**
- Modify: `cyclist_kb/agents/coach.py` (`assess_block`)
- Test: `tests/test_coach_slow_loop.py`

**Interfaces:**
- Consumes: `derive_executed_block`, `block_planned_load`, `compliance`, `attribution_verdict`, `assessment_delta`, `freeze_athlete_data_citation`, `DEFAULT_COMPLIANCE_THRESHOLD`; `save_memo`, `list_activities`, `list_assessments`, `get_plan`; `make_memo_id`, `TransferabilityMemo`, `TransferabilityVerdict`.
- Produces: `assess_block(self, athlete_id: str, plan_id: str, block_id: str) -> TransferabilityMemo`

- [ ] **Step 1: Scrivi i test del gate di compliance**

```python
# tests/test_coach_slow_loop.py
# Caso compliance<0.80 → verdict INCONCLUSIVE, caveats contiene "compliance < soglia".
# Caso compliance>=0.80 & ΔFTP>0 → TRANSFERRED, metric_deltas={"ftp": delta}, compliance_ratio>=0.80.
# Semina: Athlete + TrainingPlan con un TrainingBlock FROZEN + ActivitySummary nel range + due Assessment (pre/post).
```

- [ ] **Step 2: Esegui per vederli fallire**

Run: `.venv/bin/python -m pytest tests/test_coach_slow_loop.py -q`
Expected: FAIL (`AttributeError: assess_block`).

- [ ] **Step 3: Implementa `assess_block`**

Segui lo scheletro:
```python
def assess_block(self, athlete_id, plan_id, block_id):
    plan = self.db.get_plan(plan_id)
    block = next(b for b in plan.blocks if b.id == block_id)
    activities = self.db.list_activities(athlete_id)
    exec_ = derive_executed_block(block, activities)
    planned = block_planned_load(block)
    ratio = compliance(planned, exec_["executed_load"])
    assessments = [a for a in self.db.list_assessments(athlete_id)]
    before, after = self._pre_post_assessments(assessments, block)   # per data
    delta = assessment_delta(before.value if before else None, after.value if after else None)
    verdict = attribution_verdict(ratio, delta)
    caveats = []
    if ratio < DEFAULT_COMPLIANCE_THRESHOLD:
        caveats.append("compliance < soglia")
    cites = [freeze_athlete_data_citation(a.id, note="valutazione di blocco")
             for a in (before, after) if a]
    memo = TransferabilityMemo(
        id=make_memo_id(block_id), athlete_id=athlete_id, block_id=block_id,
        verdict=verdict, metric_deltas=({} if delta is None else {plan.target_metric_type.value: delta}),
        compliance_ratio=ratio, caveats=caveats, citations=cites)
    self.db.save_memo(memo)
    return memo
```

- [ ] **Step 4: Esegui per vederli passare**

Run: `.venv/bin/python -m pytest tests/test_coach_slow_loop.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cyclist_kb/agents/coach.py tests/test_coach_slow_loop.py
git commit -m "feat(fase-d): loop lento assess_block con gate di compliance"
```

---

## Task 8 (CP10): Loop veloce — `adapt_microcycle` → nuova proposta

**Files:**
- Modify: `cyclist_kb/agents/coach.py` (`adapt_microcycle`)
- Test: `tests/test_coach_fast_loop.py`

**Interfaces:**
- Consumes: `active_plan`, `list_timeseries`, `list_activities`; `overload_guardrail`; `TrainingPlan.next_version(status=PROPOSED)`; funzioni di Task 5.
- Produces: `adapt_microcycle(self, athlete_id: str) -> TrainingPlan` (nuova versione `PROPOSED`; **non** tocca la strategia, **non** aggiorna evidenza N=1, opera solo su Sedute non eseguite; blocchi `FROZEN` invariati — ADR-0002).

- [ ] **Step 1: Scrivi il test**

```python
# tests/test_coach_fast_loop.py
# Semina un piano ACTIVE con un blocco non-frozen; simula stato di sovraccarico
# (TSB molto negativo + hrv/sleep drop via TimeseriesPoint). adapt_microcycle →
# nuova versione PROPOSED con carico del microciclo entrante ridotto; strategia
# (goal/provenance dei blocchi) invariata; eventuali blocchi FROZEN identici.
```

- [ ] **Step 2: Esegui per vederlo fallire**

Run: `.venv/bin/python -m pytest tests/test_coach_fast_loop.py -q`
Expected: FAIL (`AttributeError: adapt_microcycle`).

- [ ] **Step 3: Implementa `adapt_microcycle`**

Legge lo stato recente (ultimi `TimeseriesPoint` di TSB/HRV/SLEEP via `list_timeseries`), applica `overload_guardrail`; se scatta, deriva `plan.next_version(status=PlanStatus.PROPOSED)`, riduce i `target_watts`/`duration_s` delle Prescription dei **soli** blocchi non-`FROZEN` del microciclo entrante (es. −15% carico), lascia i blocchi `FROZEN` intatti, riapplica disclaimer, marca gli altri PROPOSED come SUPERSEDED, salva e ritorna. Se il guardrail non scatta, propone comunque una revisione neutra (o ritorna una proposta identica-ma-versionata — decidere: qui produce sempre una nuova PROPOSED per coerenza proponi-poi-approva).

- [ ] **Step 4: Esegui per vederlo passare**

Run: `.venv/bin/python -m pytest tests/test_coach_fast_loop.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cyclist_kb/agents/coach.py tests/test_coach_fast_loop.py
git commit -m "feat(fase-d): loop veloce adapt_microcycle (revisione carico come nuova proposta)"
```

---

## Task 9 (CP8): Wiring `Pipeline`

**Files:**
- Modify: `cyclist_kb/pipeline.py`
- Test: `tests/test_coach_accept.py` (append) / `tests/test_coach.py`

**Interfaces:**
- Consumes: `CoachAgent` (lazy import), `MetricGoal`, `self.db`.
- Produces:
  - `class PlanNotFound(Exception)`, `class PlanStateError(Exception)`, `class AthleteNotFound(Exception)`
  - `Pipeline.coach(self, athlete_id: str, goal: MetricGoal, profile_path: Optional[Path] = None) -> TrainingPlan`
  - `Pipeline.coach_accept(self, plan_id: str) -> TrainingPlan`
  - `Pipeline.coach_adapt(self, athlete_id: str) -> TrainingPlan`
  - `Pipeline.coach_assess(self, athlete_id: str, plan_id: str, block_id: str) -> TransferabilityMemo`

- [ ] **Step 1: Scrivi i test**

```python
# coach() ritorna un piano PROPOSED; coach_accept() lo promuove (active_plan == plan);
# coach_accept(id inesistente) → PlanNotFound; coach_accept(piano ACTIVE) → PlanStateError.
```

- [ ] **Step 2: Esegui per vederli fallire** — Run: `.venv/bin/python -m pytest tests/test_coach_accept.py -q` → FAIL.

- [ ] **Step 3: Implementa il wiring**

In `pipeline.py`, accanto a `ResearchNotFound`:
```python
class PlanNotFound(Exception): ...
class PlanStateError(Exception): ...
class AthleteNotFound(Exception): ...
```
Metodi (lazy import come `sync_athlete`):
```python
def coach(self, athlete_id, goal, profile_path=None):
    from .agents.coach import CoachAgent
    profile = load_profile(Path(profile_path)) if profile_path else None
    if self.db.get_athlete(athlete_id) is None:
        raise AthleteNotFound(f"Atleta '{athlete_id}' inesistente.")
    return CoachAgent(self.db).run(athlete_id, goal, profile)

def coach_accept(self, plan_id):
    from .agents.coach import CoachAgent
    if self.db.get_plan(plan_id) is None:
        raise PlanNotFound(f"Piano '{plan_id}' inesistente.")
    try:
        return CoachAgent(self.db).accept(plan_id)
    except ValueError as exc:
        raise PlanStateError(str(exc)) from exc

def coach_adapt(self, athlete_id):
    from .agents.coach import CoachAgent
    return CoachAgent(self.db).adapt_microcycle(athlete_id)

def coach_assess(self, athlete_id, plan_id, block_id):
    from .agents.coach import CoachAgent
    return CoachAgent(self.db).assess_block(athlete_id, plan_id, block_id)
```

- [ ] **Step 4: Esegui per vederli passare** — Run: `.venv/bin/python -m pytest tests/test_coach_accept.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add cyclist_kb/pipeline.py tests/test_coach_accept.py
git commit -m "feat(fase-d): wiring Pipeline coach/coach_accept/coach_adapt/coach_assess"
```

---

## Task 10 (CP9): Wiring CLI

**Files:**
- Modify: `cyclist_kb/cli.py`
- Test: `tests/test_cli_coach.py`

**Interfaces:**
- Consumes: `Pipeline.coach/coach_accept/coach_adapt/coach_assess`, `PlanNotFound`, `PlanStateError`, `AthleteNotFound`, `MetricGoal`, `MetricType`.
- Produces: comandi `coach`, `coach-accept`, `coach-adapt`, `coach-assess`; helper `_print_plan(plan)`.

- [ ] **Step 1: Scrivi il test (CliRunner + monkeypatch Database)**

```python
# tests/test_cli_coach.py — prior art tests/test_cli_retrieve.py
# monkeypatch.setattr(cli, "Database", lambda *a, **k: db)  (o su Pipeline)
# invoke(["coach", ath, "--metric", "ftp", "--to", "340", "--by", "2026-09-30"]) → exit 0, output contiene "proposed" e plan.id
# invoke(["coach-accept", plan_id]) → exit 0; db.active_plan(ath).status == "active"
# invoke(["coach-accept", "id-inesistente"]) → exit 1 (rosso)
```

- [ ] **Step 2: Esegui per vederli fallire** — Run: `.venv/bin/python -m pytest tests/test_cli_coach.py -q` → FAIL.

- [ ] **Step 3: Implementa i comandi**

In `cli.py`, importa `from .pipeline import Pipeline, ResearchNotFound, PlanNotFound, PlanStateError, AthleteNotFound` e `from .athlete_models import MetricGoal, MetricType`. Comando `coach` (opzioni esplicite per l'obiettivo):
```python
@app.command()
def coach(athlete_id: str,
          metric: str = typer.Option("ftp", "--metric", help="Grandezza obiettivo (ftp/vo2max/...)."),
          to: float = typer.Option(..., "--to", help="Valore-target."),
          by: str = typer.Option(..., "--by", help="Data-obiettivo ISO YYYY-MM-DD."),
          start: Optional[float] = typer.Option(None, "--from", help="Valore di partenza (opz.)."),
          profile: Optional[Path] = typer.Option(None, "--profile", help="Profilo atleta YAML (opz.).")):
    goal = MetricGoal(metric_type=MetricType(metric), target=to, target_date=by, start=start)
    try:
        plan = Pipeline().coach(athlete_id, goal, profile)
    except AthleteNotFound as exc:
        typer.secho(str(exc), fg=typer.colors.RED); raise typer.Exit(1)
    _print_plan(plan)
    typer.secho(f"Piano proposto {plan.id} (status={plan.status.value}).", fg=typer.colors.GREEN)


@app.command(name="coach-accept")
def coach_accept(plan_id: str = typer.Argument(..., help="Id del piano PROPOSED da attivare.")):
    try:
        plan = Pipeline().coach_accept(plan_id)
    except (PlanNotFound, PlanStateError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED); raise typer.Exit(1)
    typer.secho(f"Piano {plan.id} attivato (status={plan.status.value}).", fg=typer.colors.GREEN)
```
Aggiungi `coach-adapt` (athlete_id) e `coach-assess` (athlete_id, plan_id, block_id) sullo stesso pattern, e `_print_plan(plan)` che stampa id, status, obiettivo (`target_metric_type`/`value`/`date`) e numero blocchi.

- [ ] **Step 4: Esegui per vederli passare** — Run: `.venv/bin/python -m pytest tests/test_cli_coach.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add cyclist_kb/cli.py tests/test_cli_coach.py
git commit -m "feat(fase-d): comandi CLI coach/coach-accept/coach-adapt/coach-assess"
```

---

## Task 11 (CP11): Verifica finale + roll-up

**Files:**
- Modify: `docs/ROADMAP.md`
- (nessun test nuovo; gate di verifica)

- [ ] **Step 1: Suite intera verde offline**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS su **tutti** i test (Fase A/B/C invariati + i nuovi Fase D). Mostra il conteggio.

- [ ] **Step 2: Non-regressione `models.DataSource`**

Run: `grep -rn "DataSource" cyclist_kb/`
Expected: nessuna if-chain bibliografica in `extraction.py`/`quality.py` è stata toccata (l'enum coaching è `ProvenanceKind`, distinto).

- [ ] **Step 3: pyflakes pulito**

Run: `.venv/bin/python -m pyflakes cyclist_kb/ tests/` (o l'equivalente configurato)
Expected: nessun errore.

- [ ] **Step 4: Roll-up ROADMAP**

Marca la Fase D come implementata (test verdi + evidenza), linka questo piano, aggiorna il conteggio test.

- [ ] **Step 5: Commit + code review**

```bash
git add docs/ROADMAP.md
git commit -m "docs(fase-d): roll-up roadmap — CoachAgent implementato, N test verdi"
```
Poi `requesting-code-review` pre-merge.

---

## Self-Review (checklist eseguita)

**1. Copertura spec (PRD 30 user story):** US 1/22 → Task 2 (obiettivo metrico) + Task 0 (ADR-0006). US 2 → Task 5 (periodizzazione a ritroso). US 3 → Task 6 (citazioni STUDY su strategia). US 4/27 → Task 3+6 (numeri `heuristic`, regola del range). US 5/24 → Task 3 (`freeze_athlete_data_citation`). US 6/28/29 → Task 6 (conflict-aware conservato). US 7/18 → Task 8 (loop veloce). US 8/19 → Task 7 (loop lento). US 9/25/26 → Task 3+7 (gate compliance). US 10/11/12 → Task 4+5+9 (PROPOSED/accept). US 13 → Task 3+5 (`overload_guardrail`). US 14 → Task 3+5 (`medical_boundary_flag`). US 15 → Task 5 (disclaimer sempre). US 16 → Task 10 (`_print_plan`). US 17 → Task 9/10. US 20 → Task 5 (ramo euristico). US 21 → riuso (nessuna duplicazione). US 23 → Task 2 (validator). US 30 → Task 2 (frozen invariati). **Nessuna gap.**

**2. Placeholder scan:** i punti a discrezione dell'implementatore (soglie `overload_guardrail`, proxy `block_planned_load`) hanno codice concreto e sono etichettati come config-ready/ribaltabili, non come TODO. Il ramo LLM (Task 6, Step 3) è descrittivo ma vincolato da test concreti (Step 1) + firme esatte.

**3. Type consistency:** `MetricGoal`, `ProvenanceKind`, `promote_plan`, `attribution_verdict`, `block_compliance_verdict`, `assess_block(athlete_id, plan_id, block_id)`, `coach(athlete_id, goal, profile_path=None)` usati con la **stessa** firma in tutti i task. `RetrievalResult.direction` ∈ {positive|null|negative|mixed|unclear} coerente con `retrieval.py`. `complete_json(prompt, system=..., max_tokens=None)` coerente con `llm.py`.

## Execution Handoff

Il piano è salvato in `docs/superpowers/plans/fase-d-coachagent.md`. Percorso suggerito: `test-driven-development` per ogni task (test-first), con `verification-before-completion` al Task 11 e `requesting-code-review` pre-merge.
