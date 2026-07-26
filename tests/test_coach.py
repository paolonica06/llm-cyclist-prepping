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


# --------------------------------------------------------------------------- #
# Task 6 (CP6) — ramo LLM + integrazione Retriever (stub per-modulo)
# --------------------------------------------------------------------------- #
from cyclist_kb.llm import LLMClient
from cyclist_kb.models import (
    DataSource, Extraction, ExtractedField, PaperRecord, PopulationType,
    QualityAssessment, QualityLevel, RecordState, Research, ScreeningResult,
    VerificationResult, make_record_id,
)


def _install_fake_coach_llm(monkeypatch, complete_json):
    def factory():
        c = LLMClient()
        c._available = True
        c._backend = "anthropic"
        c.complete_json = complete_json
        return c
    monkeypatch.setattr("cyclist_kb.agents.coach.get_llm", factory)


def _verified_rec(title, abstract, *, doi, results,
                  population=PopulationType.CYCLING):
    """Record VERIFICATO (SYNTHESIZED + verification.verified) col testo di risultati
    che `synthesis._direction` classifica (via `direction_of` sull'estrazione)."""
    r = PaperRecord(
        id=make_record_id("r1", doi=doi, title=title), research_id="r1",
        doi=doi, title=title, abstract=abstract, state=RecordState.SYNTHESIZED,
        verification=VerificationResult(verified=True),
        screening=ScreeningResult(relevance_score=0.9, population_type=population,
                                  is_cycling=(population == PopulationType.CYCLING),
                                  decision="include", reason="x"),
        quality=QualityAssessment(confidence_level=QualityLevel.HIGH,
                                  methodological_quality=QualityLevel.HIGH,
                                  transferability_to_competitive_cyclists=QualityLevel.HIGH),
        extraction=Extraction(),
    )
    r.extraction.results = ExtractedField(value=results, source=DataSource.ABSTRACT)
    return r


def test_llm_range_rule_numbers_never_study(tmp_path, monkeypatch):
    # FIX #16: rinominato da test_llm_branch_builds_plan_with_3way_provenance.
    # Verifica la REGOLA DEL RANGE: i numeri (watt, durate) nei blocchi LLM
    # non hanno mai provenance STUDY, anche se l'LLM lo suggerisce.
    # La branch STUDY positiva (block.provenance==STUDY + citations) è coperta
    # da test_conflict_aware_preserved, che asserisce esplicitamente su quel ramo.
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
    assert plan.blocks, "il ramo LLM deve produrre blocchi"
    # numeri al watt MAI provenance study (regola del range)
    for b in plan.blocks:
        for p in b.prescriptions:
            assert p.provenance != ProvenanceKind.STUDY


def test_conflict_aware_preserved(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    # Serve una Research per far vedere i record al Pozzo (verified_pool → list_researches).
    db.create_research(Research(id="r1", topic="interval training vo2max"))
    # Due record verificati DISCORDI sullo stesso tema: uno positivo, uno negativo.
    # Calcoliamo i loro id stabili con make_record_id (SHA1 hex), NON 'pos'/'neg'.
    pos_id = make_record_id("r1", doi="10.1/pos")
    neg_id = make_record_id("r1", doi="10.1/neg")
    db.upsert_record(_verified_rec(
        "Intervals boost VO2max in cyclists",
        "interval training vo2max cyclists",
        doi="10.1/pos", results="VO2max increased significantly and performance improved"))
    db.upsert_record(_verified_rec(
        "Intervals impair VO2max in cyclists",
        "interval training vo2max cyclists",
        doi="10.1/neg", results="VO2max decreased and performance worse, impaired adaptation"))

    def _fake(prompt, system=None, max_tokens=None):
        return {"blocks": [
            {"goal": "vo2max", "provenance": "study",
             "strategy_query": "interval training vo2max cyclists",
             "prescriptions": [{"description": "5x4", "target_watts": 388, "duration_s": 240}]},
        ]}
    _install_fake_coach_llm(monkeypatch, _fake)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)

    block = plan.blocks[0]
    # Il blocco ancorato all'evidenza positiva ha provenance STUDY e citazioni (branch STUDY positiva).
    assert block.provenance == ProvenanceKind.STUDY, \
        "il blocco dovrebbe essere STUDY: ha evidenza verificata positiva"
    assert block.citations, "il blocco STUDY deve avere citazioni"
    # Il record positivo compare nelle citazioni (source_kind STUDY).
    citation_ids = [c.record_id for c in block.citations]
    assert pos_id in citation_ids, \
        f"id del record positivo {pos_id!r} atteso nelle citazioni; trovati: {citation_ids}"
    # Il record negativo compare nei conflitti testuali (conflict-aware conservato).
    assert block.conflicts, "conflict-aware: il record negativo deve generare almeno un conflitto"
    # Il conflitto fa riferimento al titolo o all'id del record negativo.
    conflicts_text = " ".join(block.conflicts)
    neg_title_fragment = "Intervals impair"
    assert neg_title_fragment in conflicts_text or neg_id in conflicts_text, \
        f"atteso riferimento al record negativo nei conflitti; trovati: {block.conflicts}"


# --------------------------------------------------------------------------- #
# FIX D — periodizzazione datata: i blocchi hanno planned_start/planned_end
# consecutivi, con l'ultimo che termina a goal.target_date.
# --------------------------------------------------------------------------- #
def test_heuristic_blocks_have_consecutive_planned_dates(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)

    assert plan.blocks
    # Ogni blocco ha entrambe le date valorizzate.
    for b in plan.blocks:
        assert b.planned_start is not None
        assert b.planned_end is not None
        assert b.planned_start < b.planned_end
    # Finestre CONSECUTIVE: la fine di un blocco == l'inizio del successivo.
    for prev, nxt in zip(plan.blocks, plan.blocks[1:]):
        assert prev.planned_end == nxt.planned_start
    # L'ULTIMO blocco termina esattamente a goal.target_date.
    assert plan.blocks[-1].planned_end == "2026-09-30"


# --------------------------------------------------------------------------- #
# FIX E — conflict-aware anche offline (senza fake LLM): un blocco euristico
# ha conflicts NON vuoto quando il Pozzo contiene direzioni discordi sullo
# stesso tema. Invariante: con Pozzo VUOTO i blocchi restano HEURISTIC senza
# citazioni (coperto anche da test_coach_invariants).
# --------------------------------------------------------------------------- #
def test_heuristic_branch_is_conflict_aware_offline(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    # Pozzo con evidenze verificate discordi sullo stesso tema (pattern di
    # test_conflict_aware_preserved): una positiva e una negativa. La query
    # strategica euristica per "sviluppo" contiene "interval training".
    db.create_research(Research(id="r1", topic="interval training vo2max"))
    db.upsert_record(_verified_rec(
        "Intervals boost FTP in cyclists",
        "interval training ftp cyclists",
        doi="10.1/pos", results="FTP increased significantly and performance improved"))
    db.upsert_record(_verified_rec(
        "Intervals impair FTP in cyclists",
        "interval training ftp cyclists",
        doi="10.1/neg", results="FTP decreased and performance worse, impaired adaptation"))

    # NESSUN fake LLM installato → ramo euristico offline.
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)

    # Almeno un blocco euristico è conflict-aware (conflicts non vuoto).
    assert any(b.conflicts for b in plan.blocks), "conflict-aware offline atteso"
    # Regola del range invariata: i NUMERI restano HEURISTIC anche se il blocco è STUDY.
    for b in plan.blocks:
        for p in b.prescriptions:
            assert p.provenance != ProvenanceKind.STUDY


def test_heuristic_branch_empty_pozzo_stays_heuristic(tmp_path, monkeypatch):
    # Invariante: Pozzo VUOTO → blocchi HEURISTIC, nessuna citazione, nessun conflitto.
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)
    for b in plan.blocks:
        assert b.provenance == ProvenanceKind.HEURISTIC
        assert b.citations == []
        assert b.conflicts == []


# --------------------------------------------------------------------------- #
# FIX #23 — run() senza alcuna Assessment
# --------------------------------------------------------------------------- #
def test_run_without_assessment_does_not_raise(tmp_path, monkeypatch):
    """FIX #23: atleta senza Assessment + goal senza start → run() offline non solleva,
    produce PROPOSED con target_metric_start=None, blocks non vuoto e disclaimer
    strutturale nelle notes."""
    db = _db(tmp_path, monkeypatch)
    # Semina solo l'Athlete, nessuna Assessment.
    ath = make_athlete_id("AtletaSenzaFTP")
    db.save_athlete(Athlete(id=ath, name="AtletaSenzaFTP", category="U23", discipline="road"))
    # goal senza start (start=None → dedotto dall'ultimo Assessment → None)
    goal = MetricGoal(metric_type=MetricType.FTP, target=320.0, target_date="2026-12-31")
    plan = CoachAgent(db).run(ath, goal)
    assert plan.status == PlanStatus.PROPOSED
    assert plan.target_metric_start is None, \
        "senza Assessment, target_metric_start deve essere None"
    assert plan.blocks, "run() deve periodizzare anche senza Assessment"
    # disclaimer strutturale sempre presente
    assert plan.notes and "ipotesi" in plan.notes.lower(), \
        "il disclaimer 'ipotesi' deve sempre comparire nelle notes"
    # con start=None i target_watts euristici sono None (mai 0.0 travestito)
    for b in plan.blocks:
        for p in b.prescriptions:
            assert p.target_watts is None, \
                f"senza Assessment, target_watts deve essere None; trovato {p.target_watts}"


# --------------------------------------------------------------------------- #
# FIX #17 — integrazione confine medico (medical_boundary_flag in plan.notes)
# --------------------------------------------------------------------------- #
from cyclist_kb.models import AthleteProfile


def test_medical_boundary_flag_appears_in_notes_with_clinical_constraint(tmp_path, monkeypatch):
    """FIX #17 (caso clinico): constraints con marcatore medico → disclaimer medico in notes."""
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    profile = AthleteProfile(name="Paolo", constraints=["dolore al ginocchio"])
    plan = CoachAgent(db).run(ath, goal, profile=profile)
    assert plan.notes, "notes non deve essere vuota"
    assert "confine medico" in plan.notes.lower(), \
        f"atteso disclaimer medico in notes; trovato: {plan.notes!r}"
    # il disclaimer strutturale 'ipotesi' deve sempre essere presente
    assert "ipotesi" in plan.notes.lower(), \
        "il disclaimer strutturale 'ipotesi' deve sempre comparire"


def test_medical_boundary_flag_absent_with_benign_constraint(tmp_path, monkeypatch):
    """FIX #17 (caso controllo): constraints benigni → NESSUN disclaimer medico (ma
    il disclaimer strutturale 'ipotesi' resta sempre)."""
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    profile = AthleteProfile(name="Paolo", constraints=["preferisce uscite mattutine"])
    plan = CoachAgent(db).run(ath, goal, profile=profile)
    assert plan.notes, "notes non deve essere vuota"
    assert "confine medico" not in plan.notes.lower(), \
        f"non atteso disclaimer medico per constraints benigni; trovato: {plan.notes!r}"
    # il disclaimer strutturale 'ipotesi' rimane sempre
    assert "ipotesi" in plan.notes.lower(), \
        "il disclaimer strutturale 'ipotesi' deve sempre comparire"


# --------------------------------------------------------------------------- #
# Fase D (chiusura) — narrativa "da preparatore" ricca, con fallback offline
# --------------------------------------------------------------------------- #
def test_run_offline_generates_heuristic_narrative(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)
    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)
    assert plan.narrative, "run() offline deve generare una narrativa deterministica"
    low = plan.narrative.lower()
    assert "ftp" in low                              # cita l'obiettivo
    assert "340" in plan.narrative                   # il valore-target compare
    assert "provenienza" in low                      # marca la provenienza (protocollo)
    assert "ipotesi" in low                          # chiude col disclaimer strutturale


def test_run_uses_llm_narrative_when_available(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)

    def factory():
        c = LLMClient()
        c._available = True
        c._backend = "anthropic"
        c.complete_json = lambda *a, **k: None       # nessun piano LLM → euristico
        c.complete_text = lambda *a, **k: "NARRATIVA RICCA DAL MODELLO."
        return c
    monkeypatch.setattr("cyclist_kb.agents.coach.get_llm", factory)

    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)
    assert plan.narrative == "NARRATIVA RICCA DAL MODELLO."


def test_llm_narrative_falls_back_to_heuristic_on_none(tmp_path, monkeypatch):
    # complete_text ritorna None (errore/offline) → narrativa euristica, mai vuota.
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete(db)

    def factory():
        c = LLMClient()
        c._available = True
        c._backend = "anthropic"
        c.complete_json = lambda *a, **k: None
        c.complete_text = lambda *a, **k: None
        return c
    monkeypatch.setattr("cyclist_kb.agents.coach.get_llm", factory)

    goal = MetricGoal(metric_type=MetricType.FTP, target=340.0, target_date="2026-09-30")
    plan = CoachAgent(db).run(ath, goal)
    assert plan.narrative and "ipotesi" in plan.narrative.lower()
