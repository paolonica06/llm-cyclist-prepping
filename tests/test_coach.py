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
    # conflict-aware conservato: o conflitti testuali, o citazioni che coprono
    # entrambe le direzioni (positiva + non-positiva).
    covers_both_directions = (
        any(c.record_id and "pos" in (c.record_id or "") for c in block.citations)
        and any(c.record_id and "neg" in (c.record_id or "") for c in block.citations)
    )
    assert block.conflicts or covers_both_directions


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
