"""Screening Agent: pertinenza + classificazione della popolazione.

Non elimina mai i record esclusi (passano a stato EXCLUDED conservando il motivo).
"""

from __future__ import annotations

import logging
from typing import List

from ..config import get_settings
from ..domain import (CYCLING_MARKERS, ENDURANCE_OTHER_MARKERS, EXERCISE_CONTEXT_MARKERS,
                      TRAINED_MARKERS, UNTRAINED_MARKERS)
from ..llm import get_llm
from ..models import (PaperRecord, PopulationType, RecordState, Research,
                      ResearchStatus, ScreeningResult)
from ..textutil import tokens

logger = logging.getLogger("cyclist_kb.screening")

RELEVANCE_MIN = 0.12


class ScreeningAgent:
    def __init__(self, db) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm()

    def run(self, research: Research) -> Research:
        records = self.db.list_records(
            research.id, states=[RecordState.PENDING_SCREENING, RecordState.DISCOVERED]
        )
        included = excluded = 0
        for rec in records:
            result = self._screen(rec, research.topic)
            rec.screening = result
            if result.decision == "include":
                rec.state = RecordState.INCLUDED
                rec.exclusion_reason = None
                included += 1
            else:
                rec.state = RecordState.EXCLUDED
                rec.exclusion_reason = result.reason
                excluded += 1
            self.db.upsert_record(rec)

        research.status = ResearchStatus.SCREENED
        research.stats.update({"screened_included": included, "screened_excluded": excluded})
        self.db.save_research(research)
        logger.info("Screening %s: %d inclusi, %d esclusi", research.id, included, excluded)
        return research

    def _screen(self, rec: PaperRecord, topic: str) -> ScreeningResult:
        if self.llm.available:
            r = self._llm_screen(rec, topic)
            if r is not None:
                return r
        return self._heuristic_screen(rec, topic)

    # -- LLM ---------------------------------------------------------------- #
    def _llm_screen(self, rec: PaperRecord, topic: str):
        text = f"Titolo: {rec.title or ''}\nAbstract: {rec.abstract or '(assente)'}"
        data = self.llm.complete_json(
            prompt=(
                f"Valuta la pertinenza di questo studio rispetto al topic «{topic}».\n{text}\n\n"
                "Restituisci JSON: {\"relevance_score\": 0-1, "
                "\"population_type\": \"cycling|endurance_other|untrained|mixed|unclear\", "
                "\"is_cycling\": bool, \"decision\": \"include|exclude\", \"reason\": \"...\"}.\n"
                "Includi solo se pertinente e riferito (anche parzialmente) a ciclisti. "
                "Registra sempre il motivo."
            )
        )
        if not data:
            return None
        try:
            return ScreeningResult(
                relevance_score=max(0.0, min(1.0, float(data.get("relevance_score", 0)))),
                population_type=PopulationType(data.get("population_type", "unclear")),
                is_cycling=bool(data.get("is_cycling", False)),
                decision="include" if data.get("decision") == "include" else "exclude",
                reason=str(data.get("reason", "n/d")),
                assessed_by="llm",
            )
        except (ValueError, TypeError):
            return None

    # -- Euristica ---------------------------------------------------------- #
    def _heuristic_screen(self, rec: PaperRecord, topic: str) -> ScreeningResult:
        blob = f"{rec.title or ''} {rec.abstract or ''}".lower()
        topic_tokens = set(tokens(topic))
        text_tokens = set(tokens(blob))
        overlap = len(topic_tokens & text_tokens)
        relevance = min(1.0, overlap / max(3, len(topic_tokens))) if topic_tokens else 0.0

        cyc = _count(blob, CYCLING_MARKERS)
        endo = _count(blob, ENDURANCE_OTHER_MARKERS)
        untr = _count(blob, UNTRAINED_MARKERS)
        trained = _count(blob, TRAINED_MARKERS)
        context = _count(blob, EXERCISE_CONTEXT_MARKERS)
        is_cycling = cyc > 0

        # Bonus di pertinenza se la popolazione è ciclistica e allenata.
        if is_cycling:
            relevance = min(1.0, relevance + 0.2)
        if trained:
            relevance = min(1.0, relevance + 0.1)

        # Classificazione popolazione. MIXED è riservato al caso con coorte
        # ciclistica insieme ad altre; senza ciclisti si ricade sul segnale
        # dominante (endurance_other / untrained) → esclusione con motivo.
        if cyc and (endo or untr):
            population = PopulationType.MIXED
        elif cyc:
            population = PopulationType.CYCLING
        elif endo and untr:
            population = PopulationType.ENDURANCE_OTHER if endo >= untr else PopulationType.UNTRAINED
        elif endo:
            population = PopulationType.ENDURANCE_OTHER
        elif untr:
            population = PopulationType.UNTRAINED
        else:
            population = PopulationType.UNCLEAR

        signals = {"cycling": cyc, "endurance_other": endo, "untrained": untr,
                   "trained": trained, "exercise_context": context, "token_overlap": overlap}

        # Decisione: includi se pertinente e con segnale ciclistico o incertezza.
        if context == 0:
            decision, reason = "exclude", (
                "Nessun contesto di esercizio/fisiologia: termini come 'cycling' usati "
                "fuori dal dominio sportivo (es. elettrochimica, cicli mestruali).")
        elif relevance < RELEVANCE_MIN:
            decision, reason = "exclude", f"Bassa pertinenza al topic (score {relevance:.2f})."
        elif population == PopulationType.UNTRAINED:
            decision, reason = "exclude", "Popolazione non allenata/sedentaria: non trasferibile a ciclisti competitivi."
        elif population == PopulationType.ENDURANCE_OTHER:
            decision, reason = "exclude", "Altro sport di endurance senza coorte ciclistica."
        elif population in (PopulationType.CYCLING, PopulationType.MIXED):
            decision, reason = "include", (
                "Popolazione ciclistica pertinente al topic."
                if population == PopulationType.CYCLING
                else "Popolazione mista con coorte ciclistica: incluso, distinzione da verificare in estrazione."
            )
        else:  # UNCLEAR
            decision, reason = "include", "Popolazione non chiara ma pertinente: incluso in via cautelativa (da rivedere)."

        return ScreeningResult(
            relevance_score=round(relevance, 3),
            population_type=population,
            is_cycling=is_cycling,
            decision=decision,
            reason=reason,
            signals=signals,
            assessed_by="heuristic",
        )


def _count(blob: str, markers: List[str]) -> int:
    return sum(1 for m in markers if m in blob)
