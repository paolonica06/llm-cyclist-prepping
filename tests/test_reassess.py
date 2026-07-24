"""`research reassess`: ri-esegue SOLO gli step LLM (screening → estrazione →
qualità → sintesi) sui record GIÀ verificati, senza rifare search/verify.

Invarianti coperti:
- ri-applica l'arricchimento LLM ai record esistenti (assessed_by/extracted_by → "llm");
- NON ri-scarica (nessun record nuovo) e NON ri-verifica (la verifica salvata resta intatta);
- degrada all'euristica se l'LLM non è disponibile (offline);
- ignora i record non verificati (restano fuori dalla sintesi);
- pool vuoto → nessun errore.

Come test_llm_batching, l'LLM è stubbato con un client fresco per-modulo, così non
si inquina il singleton `get_llm()` e la suite resta offline/deterministica.
"""

import asyncio

from cyclist_kb.config import get_settings
from cyclist_kb.db import Database
from cyclist_kb.llm import LLMClient
from cyclist_kb.models import (Extraction, PaperRecord, RecordState, Research,
                               ScreeningResult, VerificationResult, make_record_id)
from cyclist_kb.pipeline import Pipeline

_LLM_MODULES = ("screening", "extraction", "quality", "synthesis")


# --------------------------------------------------------------------------- #
# Infrastruttura di test
# --------------------------------------------------------------------------- #
def _configure(monkeypatch, tmp_path) -> Database:
    """Reindirizza wiki/db su tmp_path (il singleton settings è condiviso dagli
    agenti). Con KB_GIT_AUTOCOMMIT=0 la sintesi non tocca git."""
    s = get_settings()
    monkeypatch.setattr(s, "wiki_dir", tmp_path / "wiki")
    monkeypatch.setattr(s, "db_path", tmp_path / "kb.sqlite3")
    return Database(path=tmp_path / "kb.sqlite3")


def _install_fake_llm(monkeypatch, complete_json) -> None:
    """Sostituisce `get_llm` in OGNI modulo-agente con una factory che ritorna un
    client fresco 'disponibile' (nessuna pollution del singleton)."""
    def factory():
        c = LLMClient()
        c._available = True
        c._backend = "claude_code"
        c.complete_json = complete_json
        return c

    for mod in _LLM_MODULES:
        monkeypatch.setattr(f"cyclist_kb.agents.{mod}.get_llm", factory)


def _incl():
    return {"relevance_score": 0.9, "population_type": "cycling", "is_cycling": True,
            "decision": "include", "reason": "pertinente (llm)"}


def _extract_obj():
    return {"study_design": "randomized controlled trial", "sample_size": 24,
            "training_level": "competitive", "outcomes": "vo2max",
            "results": "VO2max increased significantly", "duration": "8 weeks"}


def _quality_obj():
    return {"study_type": "RCT", "methodological_quality": "high",
            "confidence_level": "high",
            "transferability_to_competitive_cyclists": "high",
            "dimensions": {"sample": "adequate"}, "notes": []}


def _smart_fake(prompt, **kw):
    """Un solo stub per tutti gli agenti: instrada in base al testo del prompt.
    Ritorna array sovradimensionati (run() usa solo gli elementi del chunk)."""
    low = prompt.lower()
    if "interpretazione" in low:
        return {"interpretation": "Interpretazione generata dall'LLM di prova."}
    if "estrai i dati" in low:
        return {"results": [_extract_obj() for _ in range(30)]}
    if "qualità metodologica" in low:
        return {"results": [_quality_obj() for _ in range(30)]}
    return {"results": [_incl() for _ in range(30)]}  # screening


def _verified_record(i, checked_by="crossref+pubmed"):
    return PaperRecord(
        id=make_record_id("r1", doi=f"10.1/{i}", title=f"study {i}"),
        research_id="r1", doi=f"10.1/{i}",
        title=f"Interval training study {i}",
        abstract=("Competitive cyclists performed interval training; VO2max and "
                  "power output increased significantly over 8 weeks."),
        year=2020 + i,
        state=RecordState.SYNTHESIZED,
        verification=VerificationResult(verified=True, checked_by=checked_by),
        screening=ScreeningResult(relevance_score=0.5, decision="include",
                                  reason="seed", assessed_by="heuristic"),
    )


def _seed(db, n=2):
    db.create_research(Research(id="r1", topic="interval training in cyclists"))
    for i in range(n):
        db.upsert_record(_verified_record(i))


# --------------------------------------------------------------------------- #
# Test
# --------------------------------------------------------------------------- #
def test_reassess_reenriches_verified_records_with_llm(monkeypatch, tmp_path):
    db = _configure(monkeypatch, tmp_path)
    _seed(db, 2)
    _install_fake_llm(monkeypatch, _smart_fake)

    research = asyncio.run(Pipeline(db).reassess("r1"))

    recs = db.list_records("r1", states=[RecordState.SYNTHESIZED])
    assert len(recs) == 2                                    # entrambi ri-sintetizzati
    assert all(r.screening.assessed_by == "llm" for r in recs)
    assert all(r.extraction and r.extraction.extracted_by == "llm" for r in recs)
    assert all(r.quality and r.quality.assessed_by == "llm" for r in recs)
    assert research.status.value == "synthesized"


def test_reassess_does_not_research_or_reverify(monkeypatch, tmp_path):
    db = _configure(monkeypatch, tmp_path)
    db.create_research(Research(id="r1", topic="interval training in cyclists"))
    db.upsert_record(_verified_record(0, checked_by="SENTINEL"))
    _install_fake_llm(monkeypatch, _smart_fake)

    before = len(db.list_records("r1"))
    asyncio.run(Pipeline(db).reassess("r1"))
    after = db.list_records("r1")

    assert len(after) == before                              # search NON ha aggiunto record
    rec = after[0]
    # La verifica salvata è riusata così com'è: mai sovrascritta da un re-verify.
    assert rec.verification.checked_by == "SENTINEL"
    assert rec.verification.verified is True


def test_reassess_heuristic_fallback(monkeypatch, tmp_path):
    db = _configure(monkeypatch, tmp_path)
    _seed(db, 2)
    # Nessun fake LLM: offline (KB_FORCE_OFFLINE=1) → get_llm indisponibile → euristica.

    asyncio.run(Pipeline(db).reassess("r1"))

    recs = db.list_records("r1", states=[RecordState.SYNTHESIZED])
    assert len(recs) == 2                                    # arricchiti anche senza LLM
    assert all(r.screening.assessed_by == "heuristic" for r in recs)
    assert all(r.extraction and r.extraction.extracted_by == "heuristic" for r in recs)
    assert all(r.quality and r.quality.assessed_by == "heuristic" for r in recs)


def test_reassess_ignores_unverified_records(monkeypatch, tmp_path):
    db = _configure(monkeypatch, tmp_path)
    db.create_research(Research(id="r1", topic="interval training in cyclists"))
    db.upsert_record(_verified_record(0))
    unverified = _verified_record(1)
    unverified.verification = VerificationResult(verified=False, checked_by="SENTINEL")
    unverified.state = RecordState.NEEDS_REVIEW
    # Estrazione-sentinella: reassess NON deve ri-estrarre i needs_review preesistenti
    # (eviterebbe fetch OA di rete e token sprecati su record fuori dalla wiki).
    unverified.extraction = Extraction(extracted_by="SENTINEL")
    db.upsert_record(unverified)
    _install_fake_llm(monkeypatch, _smart_fake)

    asyncio.run(Pipeline(db).reassess("r1"))

    synthesized = db.list_records("r1", states=[RecordState.SYNTHESIZED])
    assert len(synthesized) == 1                             # solo il verificato entra in wiki
    review = db.get_record(unverified.id)
    assert review.state == RecordState.NEEDS_REVIEW          # il non verificato resta intatto
    assert review.verification.checked_by == "SENTINEL"
    assert review.extraction.extracted_by == "SENTINEL"      # non ri-estratto


def test_reassess_empty_pool_no_error(monkeypatch, tmp_path):
    db = _configure(monkeypatch, tmp_path)
    db.create_research(Research(id="r1", topic="interval training in cyclists"))
    unverified = _verified_record(0)
    unverified.verification = VerificationResult(verified=False)
    unverified.state = RecordState.NEEDS_REVIEW
    db.upsert_record(unverified)

    asyncio.run(Pipeline(db).reassess("r1"))                 # nessuna eccezione

    assert db.list_records("r1", states=[RecordState.SYNTHESIZED]) == []
