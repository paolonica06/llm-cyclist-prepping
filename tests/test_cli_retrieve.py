"""Fase C — comando CLI `research retrieve` (instradamento + output)."""

from typer.testing import CliRunner

from cyclist_kb import cli
from cyclist_kb.db import Database
from cyclist_kb.models import (PaperRecord, PopulationType, QualityAssessment,
                               QualityLevel, RecordState, Research,
                               ScreeningResult, VerificationResult, make_record_id)


def _seeded_db(tmp_path) -> Database:
    db = Database(path=tmp_path / "kb.sqlite3")
    db.create_research(Research(id="r1", topic="t"))
    db.upsert_record(PaperRecord(
        id=make_record_id("r1", doi="10.1/x", title="Interval training improves VO2max in cyclists"),
        research_id="r1", doi="10.1/x",
        title="Interval training improves VO2max in cyclists",
        abstract="interval training and VO2max in trained cyclists",
        state=RecordState.SYNTHESIZED,
        verification=VerificationResult(verified=True),
        screening=ScreeningResult(relevance_score=0.5, population_type=PopulationType.CYCLING,
                                  is_cycling=True, decision="include", reason="x"),
        quality=QualityAssessment(confidence_level=QualityLevel.HIGH,
                                  methodological_quality=QualityLevel.HIGH,
                                  transferability_to_competitive_cyclists=QualityLevel.HIGH)))
    return db


def test_cli_retrieve_outputs_verified_study(tmp_path, monkeypatch):
    db = _seeded_db(tmp_path)
    monkeypatch.setattr(cli, "Database", lambda *a, **k: db)
    result = CliRunner().invoke(cli.app, ["retrieve", "interval training VO2max"])
    assert result.exit_code == 0
    assert "Interval training improves" in result.output


def test_cli_retrieve_empty_when_no_match(tmp_path, monkeypatch):
    db = Database(path=tmp_path / "kb.sqlite3")            # pozzo vuoto
    monkeypatch.setattr(cli, "Database", lambda *a, **k: db)
    result = CliRunner().invoke(cli.app, ["retrieve", "xyzzy nothing relevant here"])
    assert result.exit_code == 0
    assert "Nessuno studio" in result.output
