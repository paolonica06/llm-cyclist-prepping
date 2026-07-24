"""Batching LLM: N record per singola chiamata, con fallback euristico per gli elementi mancanti."""

from cyclist_kb.agents.screening import ScreeningAgent
from cyclist_kb.db import Database
from cyclist_kb.llm import LLMClient
from cyclist_kb.models import PaperRecord, RecordState, Research, make_record_id


def _db(tmp_path) -> Database:
    return Database(path=tmp_path / "kb.sqlite3")


def _seed(db, n):
    db.create_research(Research(id="r1", topic="interval training in cyclists"))
    for i in range(n):
        db.upsert_record(PaperRecord(
            id=make_record_id("r1", title=f"study {i}"), research_id="r1",
            title=f"study {i}", abstract="cyclists interval training and VO2max",
            state=RecordState.PENDING_SCREENING))


def _fake_llm(agent, complete_json):
    """Rimpiazza il singleton con un LLMClient fresco 'disponibile' (niente pollution)."""
    llm = LLMClient()
    llm._available = True
    llm._backend = "claude_code"
    llm.complete_json = complete_json
    agent.llm = llm


def _incl(reason="ok"):
    return {"relevance_score": 0.9, "population_type": "cycling", "is_cycling": True,
            "decision": "include", "reason": reason}


def _excl(reason="no"):
    return {"relevance_score": 0.1, "population_type": "untrained", "is_cycling": False,
            "decision": "exclude", "reason": reason}


def test_batch_one_call_applies_per_record(tmp_path):
    db = _db(tmp_path)
    _seed(db, 3)
    agent = ScreeningAgent(db)
    calls = {"n": 0}

    def fake(prompt, **kw):
        calls["n"] += 1
        return {"results": [_incl(), _excl(), _incl()]}

    _fake_llm(agent, fake)
    agent.settings.llm_batch_size = 10                       # tutti e 3 in UNA chiamata
    agent.run(db.get_research("r1"))

    recs = sorted(db.list_records("r1"), key=lambda r: r.title)
    assert calls["n"] == 1                                    # una sola chiamata per 3 record
    assert [r.screening.decision for r in recs] == ["include", "exclude", "include"]
    assert all(r.screening.assessed_by == "llm" for r in recs)


def test_batch_falls_back_to_heuristic_on_missing_items(tmp_path):
    db = _db(tmp_path)
    _seed(db, 3)
    agent = ScreeningAgent(db)
    # il batch torna un solo risultato su 3 → gli altri 2 ricadono sull'euristica
    _fake_llm(agent, lambda prompt, **kw: {"results": [_incl()]})
    agent.settings.llm_batch_size = 10
    agent.run(db.get_research("r1"))

    assessed = [r.screening.assessed_by for r in db.list_records("r1")]
    assert assessed.count("llm") == 1
    assert assessed.count("heuristic") == 2


def test_batch_chunks_by_size(tmp_path):
    db = _db(tmp_path)
    _seed(db, 5)
    agent = ScreeningAgent(db)
    calls = {"n": 0}

    def fake(prompt, **kw):
        calls["n"] += 1
        return {"results": [_incl() for _ in range(10)]}       # abbondante; run usa solo quelli del chunk

    _fake_llm(agent, fake)
    agent.settings.llm_batch_size = 2                          # 5 record → chunk 2+2+1 → 3 chiamate
    agent.run(db.get_research("r1"))
    assert calls["n"] == 3


def test_batch_whole_call_failure_falls_back(tmp_path):
    db = _db(tmp_path)
    _seed(db, 2)
    agent = ScreeningAgent(db)
    _fake_llm(agent, lambda prompt, **kw: None)               # chiamata fallita → tutto euristico
    agent.settings.llm_batch_size = 10
    agent.run(db.get_research("r1"))
    assert all(r.screening.assessed_by == "heuristic" for r in db.list_records("r1"))
