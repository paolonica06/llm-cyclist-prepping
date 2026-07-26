"""Retriever (Fase C): interroga il Pozzo di Evidenza verificata.

Deterministico e offline. Ranking: **pertinenza lessicale** (in-tema-prima) → **qualità**
→ **personalizzazione** sull'atleta → **selezione conflict-aware** (entrambe le direzioni).
NON scrive risposte: quella è generazione, a valle (operatore / Claude Code / Fase D).
Vedi `docs/specs/fase-c-retrieval-rag.md`, `docs/adr/0005`, `CONTEXT.md`.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .agents.synthesis import _direction
from .dedup import deduplicate
from .domain import SYNONYMS
from .models import (DataSource, PaperRecord, PopulationType, QualityLevel,
                     RecordState)
from .textutil import tokens

# Solo evidenza verificata è recuperabile (invariante, vedi CONTEXT.md / ADR-0003).
CITABLE_STATES = {RecordState.METADATA_VERIFIED, RecordState.SYNTHESIZED}
RELEVANCE_MIN = 0.0          # in-tema-prima: sotto/pari a questa, fuori dal risultato
DEFAULT_K = 8

_QL = {QualityLevel.LOW: 0.0, QualityLevel.MODERATE: 1.0, QualityLevel.HIGH: 2.0}

_RERANK_SYSTEM = "Sei un bibliotecario scientifico. Rispondi SOLO con JSON valido."


class RetrievalResult(BaseModel):
    record: PaperRecord
    relevance: float
    quality: float
    fit: float
    score: float
    direction: str                     # positive | null | negative | mixed | unclear
    signals: Dict[str, object] = Field(default_factory=dict)
    rerank_score: Optional[float] = None   # pertinenza semantica LLM (tier opzionale)


def _sort_key(r: RetrievalResult):
    """Chiave di ordinamento unica per l'intero retriever.

    Il tier di rerank LLM (opzionale) è additivo: quando valorizza `rerank_score`,
    domina; altrimenti si ricade sullo `score` deterministico. Usare la STESSA
    chiave nel sort iniziale e in `_conflict_aware` garantisce che il rerank non
    venga silenziosamente annullato dal riordino finale.
    """
    primary = r.rerank_score if r.rerank_score is not None else r.score
    return (primary, r.score, r.relevance)


# --------------------------------------------------------------------------- #
# Pozzo: tutte le Evidenze verificate, cross-tema, deduplicate
# --------------------------------------------------------------------------- #
def is_verified(rec: PaperRecord) -> bool:
    return (
        rec.state in CITABLE_STATES
        and rec.verification is not None
        and bool(rec.verification.verified)
    )


def verified_pool(db) -> List[PaperRecord]:
    recs: List[PaperRecord] = []
    for research in db.list_researches():
        recs.extend(db.list_records(research.id))
    return deduplicate([r for r in recs if is_verified(r)])


# --------------------------------------------------------------------------- #
# Pertinenza lessicale (BM25-lite con espansione dei sinonimi di dominio)
# --------------------------------------------------------------------------- #
def _rec_text(rec: PaperRecord) -> str:
    parts = [rec.title or "", rec.abstract or ""]
    ex = rec.extraction
    if ex:
        for field in (ex.results, ex.outcomes, ex.protocol):
            if field and field.value:
                parts.append(str(field.value))
    return " ".join(parts)


def expand_query(query: str) -> List[str]:
    """Token della query + varianti dai sinonimi di dominio se il gruppo è toccato."""
    base = tokens(query)
    base_set = set(base)
    extra: List[str] = []
    for canonical, variants in SYNONYMS.items():
        group = [canonical, *variants]
        group_tokens = {tk for term in group for tk in tokens(term)}
        if base_set & group_tokens:                     # la query tocca questo gruppo
            extra.extend(group_tokens)
    return list(dict.fromkeys(base + extra))            # dedup preservando l'ordine


def build_idf(pool: List[PaperRecord]) -> Dict[str, float]:
    n = len(pool) or 1
    df: Dict[str, int] = {}
    for rec in pool:
        for tk in set(tokens(_rec_text(rec))):
            df[tk] = df.get(tk, 0) + 1
    return {tk: math.log(1.0 + n / c) for tk, c in df.items()}


def relevance(query_tokens: List[str], rec: PaperRecord, idf: Dict[str, float]) -> float:
    doc = tokens(_rec_text(rec))
    if not doc or not query_tokens:
        return 0.0
    tf = Counter(doc)
    score = 0.0
    for qt in set(query_tokens):
        f = tf.get(qt, 0)
        if f:
            score += idf.get(qt, 0.0) * (f * 2.0) / (f + 1.0)   # saturazione tf (BM25-lite)
    return score / (1.0 + math.log(1.0 + len(doc)))              # normalizza per lunghezza


# --------------------------------------------------------------------------- #
# Qualità + personalizzazione sull'atleta
# --------------------------------------------------------------------------- #
def quality_score(rec: PaperRecord) -> float:
    q = rec.quality
    if not q:
        return 0.0
    s = _QL.get(q.confidence_level, 0.0) * 1.5 + _QL.get(q.methodological_quality, 0.0)
    if rec.extraction and rec.extraction.based_on == DataSource.FULL_TEXT:
        s += 0.5                                         # full text > abstract (segnale minore)
    return s


def fit_score(rec: PaperRecord, athlete=None) -> float:
    """Adattamento all'atleta ciclista: popolazione ciclistica + alta trasferibilità in alto."""
    s = 0.0
    pop = rec.screening.population_type if rec.screening else None
    if pop == PopulationType.CYCLING:
        s += 2.0
    elif pop == PopulationType.MIXED:
        s += 0.5
    elif pop in (PopulationType.UNTRAINED, PopulationType.ENDURANCE_OTHER):
        s -= 1.5
    if rec.quality:
        s += _QL.get(rec.quality.transferability_to_competitive_cyclists, 0.0)
    return s


def direction_of(rec: PaperRecord) -> str:
    ex = rec.extraction
    text = ""
    if ex:
        for field in (ex.results, ex.outcomes):
            if field and field.value:
                text += " " + str(field.value)
    return _direction(text or (rec.abstract or ""))


# --------------------------------------------------------------------------- #
# Retrieve (conflict-aware)
# --------------------------------------------------------------------------- #
def retrieve(db, query: str, athlete=None, k: int = DEFAULT_K,
             rerank: bool = False, llm=None) -> List[RetrievalResult]:
    """Recupera l'evidenza verificata pertinente, conflict-aware.

    `rerank=True` attiva il tier opzionale di rerank LLM/semantico sopra il ranking
    lessicale deterministico: se un LLM è disponibile riordina i candidati per
    pertinenza semantica alla query, altrimenti degrada in modo pulito all'ordine
    deterministico (offline → risultato identico a `rerank=False`). `llm` è
    iniettabile per i test; se None si usa il client globale.
    """
    pool = verified_pool(db)
    idf = build_idf(pool)
    qtok = expand_query(query)
    results: List[RetrievalResult] = []
    for rec in pool:
        rel = relevance(qtok, rec, idf)
        if rel <= RELEVANCE_MIN:                         # in-tema-prima: fuori tema escluso
            continue
        ql = quality_score(rec)
        fit = fit_score(rec, athlete)
        pop = rec.screening.population_type.value if rec.screening else None
        results.append(RetrievalResult(
            record=rec, relevance=round(rel, 4), quality=ql, fit=fit,
            score=round(ql + fit + rel * 0.5, 4),        # qualità+fit dominano; pertinenza tiebreak
            direction=direction_of(rec),
            signals={"population": pop, "verified": True},
        ))
    if rerank:
        _llm_rerank(query, results, llm)                 # valorizza rerank_score in-place (o no-op)
    results.sort(key=_sort_key, reverse=True)
    return _conflict_aware(results, k)


def _llm_rerank(query: str, results: List[RetrievalResult], llm=None) -> bool:
    """Tier opzionale: chiede all'LLM un punteggio di pertinenza semantica per ogni
    candidato e lo scrive in `rerank_score`. Ritorna True se ha rerankato, False
    (no-op) se offline/errore — mai un'eccezione (degradazione, come gli agenti)."""
    if not results:
        return False
    if llm is None:
        from .llm import get_llm
        llm = get_llm()
    if not getattr(llm, "available", False):
        return False
    payload = [
        {"id": r.record.id, "title": r.record.title or "",
         "abstract": (r.record.abstract or "")[:280]}
        for r in results
    ]
    prompt = (
        f"Query dell'atleta: «{query}».\n"
        f"Studi candidati (già filtrati come pertinenti e verificati): "
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "Assegna a ciascuno studio un punteggio di pertinenza SEMANTICA alla query "
        "fra 0.0 (irrilevante) e 1.0 (centratissimo), considerando popolazione, "
        "intervento ed esito.\n"
        'Rispondi con JSON: {"scores": {"<id>": 0.0}}'
    )
    try:
        data = llm.complete_json(prompt=prompt, system=_RERANK_SYSTEM)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    scores = data.get("scores")
    if not isinstance(scores, dict):
        return False
    touched = False
    for r in results:
        raw = scores.get(r.record.id)
        try:
            r.rerank_score = float(raw)
            touched = True
        except (TypeError, ValueError):
            r.rerank_score = 0.0                         # candidato non citato → in coda
    return touched


def _conflict_aware(results: List[RetrievalResult], k: int) -> List[RetrievalResult]:
    """Top-K, garantendo la presenza di entrambe le direzioni quando esistono."""
    if not results:
        return []
    top = list(results[:k])
    chosen = {id(r) for r in top}

    def best(pred):
        for r in results:                                # results è già ordinato per _sort_key
            if pred(r.direction):
                return r
        return None

    for pred in (lambda d: d == "positive", lambda d: d in ("negative", "null")):
        if not any(pred(r.direction) for r in top):
            cand = best(pred)
            if cand is not None and id(cand) not in chosen:
                if len(top) >= k:
                    top[-1] = cand                       # rimpiazza il più debole (resta ≤ k)
                else:
                    top.append(cand)
                chosen.add(id(cand))

    top.sort(key=_sort_key, reverse=True)
    return top
