"""Test del Verification Agent: verifica DOI/PMID, coerenza metadati, blocco non verificati.

Le chiamate di rete (Crossref/PubMed) sono sostituite con stub asincroni: i test
sono deterministici e offline.
"""

import asyncio

from cyclist_kb.agents.verification import VerificationAgent
from cyclist_kb.db import Database
from cyclist_kb.models import (PaperRecord, RecordState, Research, make_record_id)


def _db(tmp_path) -> Database:
    return Database(path=tmp_path / "kb.sqlite3")


def _seed(db: Database, **kw) -> PaperRecord:
    if db.get_research("r1") is None:
        db.create_research(Research(id="r1", topic="t"))
    rec = PaperRecord(
        id=make_record_id("r1", doi=kw.get("doi"), pmid=kw.get("pmid"), title=kw.get("title")),
        research_id="r1", state=RecordState.INCLUDED, **kw,
    )
    db.upsert_record(rec)
    return rec


def _stub(agent, crossref=None, pubmed=None):
    async def cr(doi):
        return crossref
    async def pm(pmid):
        return pubmed
    agent.crossref.fetch_by_doi = cr
    agent.pubmed.fetch_summary = pm


def _run(agent, db):
    asyncio.run(agent.run(db.get_research("r1")))


def test_matching_metadata_is_verified(tmp_path):
    db = _db(tmp_path)
    _seed(db, doi="10.1/abc", pmid="123", title="Interval training in cyclists",
          authors=["Rossi M"], year=2020, journal="J Sports Sci")
    agent = VerificationAgent(db)
    _stub(agent,
          crossref={"doi": "https://doi.org/10.1/abc", "title": "Interval training in cyclists",
                    "authors": ["Rossi Mario"], "year": 2020, "journal": "Journal of Sports Sciences"},
          pubmed={"pmid": "123", "title": "Interval training in cyclists",
                  "authors": ["Rossi M"], "year": 2020, "journal": "J Sports Sci", "doi": "10.1/abc"})
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.verified is True
    assert rec.state == RecordState.METADATA_VERIFIED
    assert rec.verification.title_match is True


def test_title_mismatch_flags_needs_review(tmp_path):
    db = _db(tmp_path)
    _seed(db, doi="10.1/abc", title="Interval training in cyclists", authors=["Rossi M"], year=2020)
    agent = VerificationAgent(db)
    _stub(agent, crossref={"doi": "https://doi.org/10.1/abc",
                           "title": "Totally unrelated paper about swimming economy",
                           "authors": ["Verdi G"], "year": 2020, "journal": "X"})
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.verified is False
    assert rec.state == RecordState.NEEDS_REVIEW
    assert any("Titolo discordante" in i for i in rec.verification.inconsistencies)


def test_unresolvable_doi_is_flagged(tmp_path):
    db = _db(tmp_path)
    _seed(db, doi="10.1/missing", title="Some cycling study", year=2020)
    agent = VerificationAgent(db)
    _stub(agent, crossref=None, pubmed=None)  # DOI non risolvibile
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.doi_valid is False
    assert rec.verification.verified is False
    assert rec.state == RecordState.NEEDS_REVIEW


def test_no_identifier_cannot_be_verified(tmp_path):
    db = _db(tmp_path)
    _seed(db, title="A study with no DOI and no PMID", year=2020)
    agent = VerificationAgent(db)
    _stub(agent)
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.verified is False
    assert rec.state == RecordState.NEEDS_REVIEW
    assert any("Nessun DOI/PMID" in i for i in rec.verification.inconsistencies)


def test_pmid_only_path_verifies(tmp_path):
    db = _db(tmp_path)
    _seed(db, pmid="999", title="Cycling VO2max study", authors=["Bianchi L"], year=2018)
    agent = VerificationAgent(db)
    _stub(agent, pubmed={"pmid": "999", "title": "Cycling VO2max study",
                         "authors": ["Bianchi L"], "year": 2018, "journal": "Y", "doi": None})
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.pmid_valid is True
    assert rec.verification.verified is True
    assert rec.state == RecordState.METADATA_VERIFIED


def test_unresolvable_doi_blocks_even_with_valid_pmid(tmp_path):
    # #4: DOI presente ma non risolvibile su Crossref → non verificato, anche se il PMID è valido.
    db = _db(tmp_path)
    _seed(db, doi="10.1/missing", pmid="123", title="Cycling study", authors=["Rossi M"], year=2020)
    agent = VerificationAgent(db)
    _stub(agent, crossref=None,
          pubmed={"pmid": "123", "title": "Cycling study", "authors": ["Rossi M"],
                  "year": 2020, "journal": "J", "doi": "10.1/missing"})
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.doi_valid is False
    assert rec.verification.verified is False
    assert rec.state == RecordState.NEEDS_REVIEW


def test_doi_pmid_pointing_to_different_works_blocked(tmp_path):
    # #5: cross-check fallito (DOI Crossref ≠ DOI riportato da PubMed) → non verificato.
    db = _db(tmp_path)
    _seed(db, doi="10.1/aaa", pmid="500", title="Interval training in cyclists",
          authors=["Rossi M"], year=2020)
    agent = VerificationAgent(db)
    _stub(agent,
          crossref={"doi": "https://doi.org/10.1/aaa", "title": "Interval training in cyclists",
                    "authors": ["Rossi M"], "year": 2020, "journal": "J"},
          pubmed={"pmid": "500", "title": "Interval training in cyclists", "authors": ["Rossi M"],
                  "year": 2020, "journal": "J", "doi": "10.1/DIFFERENT"})
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.verified is False
    assert any("indicano lavori diversi" in i for i in rec.verification.inconsistencies)


def test_pmid_resolving_to_different_paper_blocks(tmp_path):
    # #6: Crossref combacia, ma il PMID risolve a un lavoro con titolo diverso → non verificato.
    db = _db(tmp_path)
    _seed(db, doi="10.1/aaa", pmid="600", title="Interval training in cyclists",
          authors=["Rossi M"], year=2020)
    agent = VerificationAgent(db)
    _stub(agent,
          crossref={"doi": "https://doi.org/10.1/aaa", "title": "Interval training in cyclists",
                    "authors": ["Rossi M"], "year": 2020, "journal": "J"},
          pubmed={"pmid": "600", "title": "A completely different swimming paper",
                  "authors": ["Verdi G"], "year": 2020, "journal": "J", "doi": "10.1/aaa"})
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.title_match is False
    assert rec.verification.verified is False


def test_doi_resolvable_but_no_local_metadata_not_verified(tmp_path):
    # #16: DOI risolve ma il record non ha titolo/autori/anno da confrontare → NEEDS_REVIEW.
    db = _db(tmp_path)
    _seed(db, doi="10.1/x")  # nessun titolo/autori/anno
    agent = VerificationAgent(db)
    _stub(agent, crossref={"doi": "https://doi.org/10.1/x", "title": "Some resolved paper",
                           "authors": ["Tizio C"], "year": 2020, "journal": "J"})
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.doi_valid is True
    assert rec.verification.verified is False
    assert rec.state == RecordState.NEEDS_REVIEW


def test_year_mismatch_recorded_as_inconsistency(tmp_path):
    db = _db(tmp_path)
    _seed(db, doi="10.2/z", title="Trained cyclist power study", authors=["Neri P"], year=2015)
    agent = VerificationAgent(db)
    _stub(agent, crossref={"doi": "https://doi.org/10.2/z", "title": "Trained cyclist power study",
                           "authors": ["Neri P"], "year": 2019, "journal": "Z"})
    _run(agent, db)
    rec = db.list_records("r1")[0]
    assert rec.verification.year_match is False
    assert any("Anno discordante" in i for i in rec.verification.inconsistencies)
