"""Test delle logiche euristiche degli agenti (screening, quality, synthesis, extraction)."""

from cyclist_kb.agents.extraction import _coerce_int, _detect_design
from cyclist_kb.agents.screening import ScreeningAgent
from cyclist_kb.agents.synthesis import _direction
from cyclist_kb.db import Database
from cyclist_kb.domain import best_design
from cyclist_kb.models import PaperRecord, PopulationType, make_record_id


def _rec(title, abstract):
    return PaperRecord(
        id=make_record_id("r1", title=title), research_id="r1",
        title=title, abstract=abstract,
    )


def _screen(tmp_path, title, abstract, topic="interval training and VO2max in cyclists"):
    agent = ScreeningAgent(Database(path=tmp_path / "kb.sqlite3"))
    return agent._heuristic_screen(_rec(title, abstract), topic)


def test_screening_excludes_non_cycling_mixed(tmp_path):
    # runners + sedentary, nessun ciclista → non deve essere incluso come MIXED.
    r = _screen(tmp_path, "HIIT in runners and sedentary patients",
                "This trial studied runners and sedentary patients performing interval training and VO2max.")
    assert r.population_type in (PopulationType.ENDURANCE_OTHER, PopulationType.UNTRAINED)
    assert r.decision == "exclude"


def test_screening_excludes_out_of_domain(tmp_path):
    # "cycling" fuori dominio (batterie): nessun contesto di esercizio → escluso.
    r = _screen(tmp_path, "Long-term cycling stability of TB-COF electrodes",
                "The battery shows stable cycling with capacity decay per cycle over 10000 cycles.")
    assert r.decision == "exclude"


def test_screening_includes_trained_cyclists(tmp_path):
    r = _screen(tmp_path, "Interval training improves VO2max in trained competitive cyclists",
                "Twelve well-trained cyclists completed interval training; VO2max and power output increased.")
    assert r.is_cycling is True
    assert r.decision == "include"


def test_best_design_picks_highest_rank():
    # Testo che menziona sia 'review' sia RCT: deve vincere l'RCT (rank più alto).
    text = "this randomized controlled trial is discussed in a narrative review of cyclists"
    assert best_design(text) == "randomized controlled trial"
    assert _detect_design(text) == "randomized controlled trial"
    assert best_design("no design markers here") is None


def test_direction_classification():
    assert _direction("VO2max increased significantly") == "positive"
    assert _direction("there was no significant difference between groups") == "null"
    assert _direction("performance decreased after the block") == "negative"
    # coesistenza di segnale positivo e nullo → misto (conflitto conservato)
    assert _direction("VO2max increased but no significant change in power output") == "mixed"


def test_coerce_int_uniforms_sample_size():
    assert _coerce_int(12) == 12
    assert _coerce_int("12") == 12
    assert _coerce_int("n = 12 cyclists") == 12
    assert _coerce_int(None) is None
    assert _coerce_int("many") is None
    assert _coerce_int(True) is None
