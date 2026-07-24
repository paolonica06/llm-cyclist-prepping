"""Fase D — comandi CLI coach/coach-accept (offline, db temporaneo)."""

from typer.testing import CliRunner

from cyclist_kb import cli
from cyclist_kb.athlete_models import (
    Assessment,
    AssessmentProtocol,
    Athlete,
    make_assessment_id,
    make_athlete_id,
)
from cyclist_kb.db import Database
from cyclist_kb.pipeline import Pipeline


def _make_db(tmp_path) -> Database:
    """Crea un DB temporaneo su disco e semina un Athlete + Assessment FTP."""
    db = Database(path=tmp_path / "kb.sqlite3")
    ath_id = make_athlete_id("Paolo")
    db.save_athlete(Athlete(id=ath_id, name="Paolo"))
    db.save_assessment(
        Assessment(
            id=make_assessment_id(ath_id, "ftp", "2026-07-01"),
            athlete_id=ath_id,
            protocol=AssessmentProtocol.FTP,
            executed_date="2026-07-01",
            value=310.0,
            unit="W",
        )
    )
    return db


def test_cli_coach_creates_proposed(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    ath = make_athlete_id("Paolo")
    # Instrada Pipeline su DB temporaneo
    monkeypatch.setattr(cli, "_pipeline", lambda: Pipeline(db=db))

    result = CliRunner().invoke(
        cli.app,
        ["coach", ath, "--metric", "ftp", "--to", "340", "--by", "2026-09-30"],
    )

    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    assert "proposed" in result.output.lower()
    # il piano dev'essere stato salvato: active_plan è None (PROPOSED), ma listando
    # i piani troviamo l'id del PROPOSED nell'output
    plans = db.list_plans(ath)
    assert len(plans) == 1
    plan_id = plans[0].id
    assert plan_id in result.output


def test_cli_coach_accept_activates(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    ath = make_athlete_id("Paolo")
    monkeypatch.setattr(cli, "_pipeline", lambda: Pipeline(db=db))

    # Prima generiamo un piano PROPOSED tramite CLI
    CliRunner().invoke(
        cli.app,
        ["coach", ath, "--metric", "ftp", "--to", "340", "--by", "2026-09-30"],
    )
    plans = db.list_plans(ath)
    assert plans, "deve esistere almeno un piano dopo coach"
    plan_id = plans[0].id

    # Ora accettiamo il piano
    result = CliRunner().invoke(cli.app, ["coach-accept", plan_id])

    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    active = db.active_plan(ath)
    assert active is not None
    assert active.status.value == "active"


def test_cli_coach_accept_missing(tmp_path, monkeypatch):
    db = Database(path=tmp_path / "kb.sqlite3")
    monkeypatch.setattr(cli, "_pipeline", lambda: Pipeline(db=db))

    result = CliRunner().invoke(cli.app, ["coach-accept", "id-inesistente"])

    assert result.exit_code == 1
