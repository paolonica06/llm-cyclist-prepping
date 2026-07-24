"""Test della sintesi cumulativa per slug (nessuna sovrascrittura silenziosa)."""

from cyclist_kb.agents.synthesis import SynthesisAgent
from cyclist_kb.db import Database
from cyclist_kb.models import (PaperRecord, RecordState, Research, VerificationResult,
                               make_record_id)


def _verified(research_id, doi, title):
    return PaperRecord(
        id=make_record_id(research_id, doi=doi, title=title),
        research_id=research_id, doi=doi, title=title,
        state=RecordState.SYNTHESIZED,
        verification=VerificationResult(verified=True),
    )


def _seed_research(db, rid, topic, records):
    db.create_research(Research(id=rid, topic=topic))
    for r in records:
        db.upsert_record(r)


def test_cumulative_records_span_researches_same_slug(tmp_path):
    db = Database(path=tmp_path / "kb.sqlite3")
    topic = "Interval training and VO2max"
    # Due ricerche distinte sullo stesso topic, con studi DIVERSI.
    _seed_research(db, "r1", topic, [_verified("r1", "10.1/a", "Study A")])
    _seed_research(db, "r2", "interval training and vo2max", [_verified("r2", "10.1/b", "Study B")])

    cumulative = SynthesisAgent(db)._cumulative_records(topic)
    dois = {r.normalized_doi() for r in cumulative}
    assert dois == {"10.1/a", "10.1/b"}  # nessuno studio precedente perso


def test_cumulative_dedups_same_paper_across_researches(tmp_path):
    db = Database(path=tmp_path / "kb.sqlite3")
    topic = "VO2max in cyclists"
    _seed_research(db, "r1", topic, [_verified("r1", "10.1/same", "Shared study")])
    _seed_research(db, "r2", topic, [_verified("r2", "10.1/same", "Shared study")])

    cumulative = SynthesisAgent(db)._cumulative_records(topic)
    assert len(cumulative) == 1  # stesso DOI → un solo studio nella pagina cumulativa


def test_unverified_records_excluded_from_cumulative(tmp_path):
    db = Database(path=tmp_path / "kb.sqlite3")
    topic = "HIIT in cyclists"
    unverified = _verified("r1", "10.1/x", "Unverified")
    unverified.verification = VerificationResult(verified=False)
    unverified.state = RecordState.NEEDS_REVIEW
    _seed_research(db, "r1", topic, [unverified])
    assert SynthesisAgent(db)._cumulative_records(topic) == []
