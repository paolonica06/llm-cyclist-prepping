"""Fase C — retriever: solo-verificati, in-tema-prima, personalizzazione, conflict-aware, determinismo."""

from cyclist_kb.db import Database
from cyclist_kb.models import (DataSource, Extraction, ExtractedField, PaperRecord,
                               PopulationType, QualityAssessment, QualityLevel,
                               RecordState, Research, ScreeningResult,
                               VerificationResult, make_record_id)
from cyclist_kb.retrieval import retrieve


def _rec(title, abstract, *, doi, population=PopulationType.CYCLING,
         conf=QualityLevel.HIGH, method=QualityLevel.HIGH, transfer=QualityLevel.HIGH,
         results="", verified=True, state=RecordState.SYNTHESIZED):
    r = PaperRecord(
        id=make_record_id("r1", doi=doi, title=title), research_id="r1",
        doi=doi, title=title, abstract=abstract, state=state,
        verification=VerificationResult(verified=verified),
        screening=ScreeningResult(relevance_score=0.5, population_type=population,
                                  is_cycling=(population == PopulationType.CYCLING),
                                  decision="include", reason="x"),
        quality=QualityAssessment(confidence_level=conf, methodological_quality=method,
                                  transferability_to_competitive_cyclists=transfer),
        extraction=Extraction(),
    )
    r.extraction.results = ExtractedField(value=results, source=DataSource.ABSTRACT)
    return r


def _db(tmp_path, recs):
    db = Database(path=tmp_path / "kb.sqlite3")
    db.create_research(Research(id="r1", topic="t"))
    for r in recs:
        db.upsert_record(r)
    return db


def test_only_verified_records_are_retrieved(tmp_path):
    db = _db(tmp_path, [
        _rec("Interval training improves VO2max in cyclists",
             "interval training and VO2max in trained cyclists", doi="10.1/ok"),
        _rec("Interval training and VO2max unverified",
             "interval training and VO2max in cyclists", doi="10.1/bad",
             verified=False, state=RecordState.NEEDS_REVIEW),
    ])
    res = retrieve(db, "interval training VO2max")
    titles = [r.record.title for r in res]
    assert any("improves VO2max" in t for t in titles)
    assert all("unverified" not in t for t in titles)     # non verificato escluso


def test_on_topic_first_off_topic_excluded(tmp_path):
    db = _db(tmp_path, [
        _rec("Interval training improves VO2max in cyclists",
             "interval training and VO2max in cyclists", doi="10.1/on",
             conf=QualityLevel.LOW, method=QualityLevel.LOW),          # in-tema ma bassa qualità
        _rec("Heat acclimatization and thermoregulation in cyclists",
             "heat acclimatization improves thermoregulation during cycling", doi="10.1/off",
             conf=QualityLevel.HIGH, method=QualityLevel.HIGH),         # fuori tema ma alta qualità
    ])
    res = retrieve(db, "interval training VO2max")
    titles = [r.record.title for r in res]
    assert titles and "Interval training" in titles[0]     # l'in-tema (anche se low) è in cima
    assert all("Heat acclimatization" not in t for t in titles)   # il fuori-tema (anche high) è escluso


def test_personalization_cycling_high_beats_untrained(tmp_path):
    db = _db(tmp_path, [
        _rec("VO2max in untrained sedentary adults doing intervals",
             "interval training and VO2max in untrained sedentary participants", doi="10.1/unt",
             population=PopulationType.UNTRAINED, transfer=QualityLevel.LOW),
        _rec("VO2max in competitive cyclists doing intervals",
             "interval training and VO2max in competitive cyclists", doi="10.1/cyc",
             population=PopulationType.CYCLING, transfer=QualityLevel.HIGH),
    ])
    res = retrieve(db, "interval training VO2max")
    assert res[0].record.doi == "10.1/cyc"                 # ciclisti/alta trasferib. prima


def test_conflict_aware_surfaces_both_directions(tmp_path):
    db = _db(tmp_path, [
        _rec("Intervals boost VO2max A", "interval training VO2max cyclists", doi="10.1/pos1",
             results="VO2max increased significantly"),
        _rec("Intervals boost VO2max B", "interval training VO2max cyclists", doi="10.1/pos2",
             results="VO2max increased significantly"),
        _rec("Intervals no effect on VO2max", "interval training VO2max cyclists", doi="10.1/null",
             conf=QualityLevel.LOW, method=QualityLevel.LOW,
             results="no significant difference between groups"),
    ])
    res = retrieve(db, "interval training VO2max", k=2)     # top-2 sarebbero 2 positivi
    dirs = {r.direction for r in res}
    assert "positive" in dirs
    assert "null" in dirs or "negative" in dirs            # la faccia opposta è comunque presente


def test_deterministic_same_query_same_order(tmp_path):
    recs = [
        _rec("Interval training VO2max cyclists one", "interval training VO2max cyclists", doi="10.1/a"),
        _rec("Interval training VO2max cyclists two", "interval training VO2max cyclists", doi="10.1/b",
             conf=QualityLevel.MODERATE),
        _rec("Interval training VO2max cyclists three", "interval training VO2max cyclists", doi="10.1/c",
             population=PopulationType.MIXED),
    ]
    db = _db(tmp_path, recs)
    order1 = [r.record.doi for r in retrieve(db, "interval training VO2max")]
    order2 = [r.record.doi for r in retrieve(db, "interval training VO2max")]
    assert order1 == order2 and len(order1) == 3
