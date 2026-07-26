"""Fase E — CoachChatAgent: ancoraggio a dati+evidenza, ramo LLM + fallback offline."""

from cyclist_kb.agents.conversation import CoachChatAgent
from cyclist_kb.athlete_models import Athlete, MetricType, TimeseriesPoint, make_athlete_id
from cyclist_kb.llm import LLMClient
from cyclist_kb.models import (DataSource, Extraction, ExtractedField, PaperRecord,
                               PopulationType, QualityAssessment, QualityLevel,
                               RecordState, Research, ScreeningResult,
                               VerificationResult, make_record_id)


def _db(tmp_path, monkeypatch):
    from cyclist_kb.config import get_settings
    from cyclist_kb.db import Database
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "kb.sqlite3")
    return Database()


def _seed_athlete_with_data(db):
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo", category="U23", discipline="road"))
    for i, (tsb, hrv) in enumerate([(-5, 55), (-8, 52), (-12, 48)]):
        d = f"2026-07-{20 + i:02d}"
        db.add_timeseries_point(TimeseriesPoint(athlete_id=ath, metric_type=MetricType.TSB, date=d, value=tsb))
        db.add_timeseries_point(TimeseriesPoint(athlete_id=ath, metric_type=MetricType.HRV, date=d, value=hrv))
    return ath


def _seed_pool(db):
    db.create_research(Research(id="r1", topic="recovery"))
    r = PaperRecord(
        id=make_record_id("r1", doi="10.1/rec", title="HRV guided recovery in cyclists"),
        research_id="r1", doi="10.1/rec", title="HRV guided recovery in cyclists",
        abstract="hrv guided training recovery rest in trained cyclists", state=RecordState.SYNTHESIZED,
        verification=VerificationResult(verified=True),
        screening=ScreeningResult(relevance_score=0.9, population_type=PopulationType.CYCLING,
                                  is_cycling=True, decision="include", reason="x"),
        quality=QualityAssessment(confidence_level=QualityLevel.HIGH,
                                  methodological_quality=QualityLevel.HIGH,
                                  transferability_to_competitive_cyclists=QualityLevel.HIGH),
        extraction=Extraction(),
    )
    r.extraction.results = ExtractedField(value="recovery improved with hrv guidance", source=DataSource.ABSTRACT)
    db.upsert_record(r)


def test_ask_offline_anchors_on_data_and_evidence(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete_with_data(db)
    _seed_pool(db)
    ans = CoachChatAgent(db).ask("mi conviene un giorno di recovery per l'HRV?", ath,
                                 as_of="2026-07-26")
    assert ans.used_llm is False
    assert ans.answer                               # mai vuota
    assert "tsb" in ans.snapshot and "hrv" in ans.snapshot
    assert ans.snapshot["hrv"]["last"] == 48.0      # ultimo punto <= as_of
    assert any("hrv" in (e.title or "").lower() for e in ans.evidence)
    assert "prescrizione medica" in ans.answer.lower()   # disclaimer


def test_snapshot_excludes_future_projections(tmp_path, monkeypatch):
    # intervals.icu proietta CTL/ATL/TSB nel futuro: lo snapshot deve fermarsi a as_of.
    db = _db(tmp_path, monkeypatch)
    ath = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath, name="Paolo"))
    db.add_timeseries_point(TimeseriesPoint(athlete_id=ath, metric_type=MetricType.TSB,
                                            date="2026-07-26", value=-10.0))   # oggi (reale)
    db.add_timeseries_point(TimeseriesPoint(athlete_id=ath, metric_type=MetricType.TSB,
                                            date="2026-10-24", value=50.0))    # proiezione futura
    ans = CoachChatAgent(db).ask("come sto?", ath, as_of="2026-07-26")
    assert ans.snapshot["tsb"]["last"] == -10.0    # oggi, NON la proiezione di ottobre


def test_ask_uses_llm_when_available(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete_with_data(db)
    _seed_pool(db)

    def factory():
        c = LLMClient()
        c._available = True
        c._backend = "anthropic"
        c.complete_text = lambda *a, **k: "RIPOSATI OGGI: HRV in calo (dati_atleta)."
        return c
    monkeypatch.setattr("cyclist_kb.agents.conversation.get_llm", factory)

    ans = CoachChatAgent(db).ask("mi posso riposare?", ath)
    assert ans.used_llm is True
    assert ans.answer == "RIPOSATI OGGI: HRV in calo (dati_atleta)."


def test_ask_without_athlete_still_answers(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    _seed_pool(db)
    ans = CoachChatAgent(db).ask("hrv guided recovery", None)
    assert ans.answer
    assert ans.snapshot == {}
    assert ans.plan is None
    assert ans.evidence                              # trova comunque evidenza dal pozzo


def test_ask_llm_none_falls_back_to_heuristic(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    ath = _seed_athlete_with_data(db)

    def factory():
        c = LLMClient()
        c._available = True
        c._backend = "anthropic"
        c.complete_text = lambda *a, **k: None       # errore/offline → euristica
        return c
    monkeypatch.setattr("cyclist_kb.agents.conversation.get_llm", factory)

    ans = CoachChatAgent(db).ask("come sto?", ath)
    assert ans.used_llm is False
    assert ans.answer and "dati_atleta" in ans.answer
