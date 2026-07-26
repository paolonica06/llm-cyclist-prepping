"""API HTTP: endpoint retrieve/coach/ask su DB isolato (offline, riproducibile).

Gli endpoint creano `Database()`/`Pipeline()` col path di default; qui li dirottiamo
su un DB tmp via monkeypatch, così i test non toccano il DB reale.
"""

import pytest
from fastapi.testclient import TestClient

import cyclist_kb.api as api
from cyclist_kb.athlete_models import Athlete, MetricType, TimeseriesPoint
from cyclist_kb.db import Database
from cyclist_kb.models import (DataSource, Extraction, ExtractedField, PaperRecord,
                               PopulationType, QualityAssessment, QualityLevel,
                               RecordState, Research, ScreeningResult,
                               VerificationResult, make_record_id)
from cyclist_kb.pipeline import Pipeline


def _verified_rec(title, abstract, doi):
    r = PaperRecord(
        id=make_record_id("r1", doi=doi, title=title), research_id="r1",
        doi=doi, title=title, abstract=abstract, state=RecordState.SYNTHESIZED,
        verification=VerificationResult(verified=True),
        screening=ScreeningResult(relevance_score=0.5, population_type=PopulationType.CYCLING,
                                  is_cycling=True, decision="include", reason="x"),
        quality=QualityAssessment(confidence_level=QualityLevel.HIGH,
                                  methodological_quality=QualityLevel.HIGH,
                                  transferability_to_competitive_cyclists=QualityLevel.HIGH),
        extraction=Extraction(),
    )
    r.extraction.results = ExtractedField(value="VO2max increased", source=DataSource.ABSTRACT)
    return r


@pytest.fixture
def client(tmp_path, monkeypatch):
    dbp = tmp_path / "kb.sqlite3"

    def _db(path=None):
        return Database(path=dbp)

    # Tutti i punti in cui l'API materializza storage/pipeline → DB tmp condiviso.
    monkeypatch.setattr(api, "Database", _db)
    monkeypatch.setattr(api, "pipeline", lambda: Pipeline(db=Database(path=dbp)))
    return TestClient(api.app), dbp


def test_health(client):
    tc, _ = client
    assert tc.get("/health").json() == {"status": "ok"}


def test_retrieve_endpoint_returns_verified_only(client):
    tc, dbp = client
    db = Database(path=dbp)
    db.create_research(Research(id="r1", topic="t"))
    db.upsert_record(_verified_rec(
        "Interval training improves VO2max in cyclists",
        "interval training and VO2max in trained cyclists", "10.1/ok"))
    resp = tc.post("/retrieve", json={"query": "interval training VO2max", "k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body and any("VO2max" in r["record"]["title"] for r in body)
    assert all(r["signals"]["verified"] for r in body)


def test_retrieve_endpoint_rerank_offline_ok(client):
    # rerank=True offline non deve rompere: degrada all'ordine deterministico.
    tc, dbp = client
    db = Database(path=dbp)
    db.create_research(Research(id="r1", topic="t"))
    db.upsert_record(_verified_rec("Interval VO2max one", "interval VO2max cyclists", "10.1/a"))
    resp = tc.post("/retrieve", json={"query": "interval VO2max", "rerank": True})
    assert resp.status_code == 200
