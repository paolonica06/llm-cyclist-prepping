"""Fase B — comando CLI `research athlete-sync` (offline: no-op pulito, output corretto)."""

from typer.testing import CliRunner

from cyclist_kb import cli
from cyclist_kb.db import Database
from cyclist_kb.pipeline import Pipeline


def test_cli_athlete_sync_offline(tmp_path, monkeypatch):
    # Instrada la CLI su un DB temporaneo (non tocca data/kb.sqlite3).
    monkeypatch.setattr(cli, "_pipeline",
                        lambda: Pipeline(db=Database(path=tmp_path / "kb.sqlite3")))
    result = CliRunner().invoke(cli.app, ["athlete-sync", "12345"])
    assert result.exit_code == 0
    assert "nessun dato sincronizzato" in result.output      # avviso: key assente/offline
    assert "Serie storiche: 0" in result.output


def test_cli_activity_intervals_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_pipeline",
                        lambda: Pipeline(db=Database(path=tmp_path / "kb.sqlite3")))
    result = CliRunner().invoke(cli.app, ["activity-intervals", "12345"])
    assert result.exit_code == 0
    assert "nessun lap scaricato" in result.output.lower()
    assert "Candidate: 0" in result.output
