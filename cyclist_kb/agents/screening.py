"""Screening Agent: pertinenza + classificazione della popolazione.

Non elimina mai i record esclusi (passano a stato EXCLUDED conservando il motivo).
"""

from __future__ import annotations

import logging
from typing import List

from ..config import get_settings
from ..domain import (CLINICAL_NONATHLETE_MARKERS, CYCLING_MARKERS, ENDURANCE_OTHER_MARKERS,
                      EXERCISE_CONTEXT_MARKERS, TRAINED_MARKERS, UNTRAINED_MARKERS)
from ..llm import chunked, get_llm
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
        batch_size = max(1, self.settings.llm_batch_size)
        for chunk in chunked(records, batch_size):
            batch = self._llm_screen_batch(chunk, research.topic) if self.llm.available else None
            for i, rec in enumerate(chunk):
                result = (batch[i] if batch and i < len(batch) and batch[i] is not None
                          else self._heuristic_screen(rec, research.topic))
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

    # -- LLM (in batch: N record per singola chiamata) --------------------- #
    def _llm_screen_batch(self, chunk, topic: str):
        """Valuta N record in UNA chiamata. Ritorna una lista allineata a `chunk`
        (ScreeningResult o None per elemento), o None se l'intera chiamata fallisce.
        Gli elementi None ricadono sull'euristica (in run())."""
        items = "\n\n".join(
            f"[{i + 1}] Titolo: {r.title or ''}\nAbstract: {(r.abstract or '(assente)')[:1500]}"
            for i, r in enumerate(chunk)
        )
        data = self.llm.complete_json(
            prompt=(
                f"Valuta la pertinenza di CIASCUNO di questi {len(chunk)} studi rispetto al "
                f"topic «{topic}».\n\n{items}\n\n"
                'Restituisci SOLO JSON {"results": [...]} dove "results" è un array con ESATTAMENTE '
                f'{len(chunk)} oggetti, uno per studio NELLO STESSO ORDINE. Ogni oggetto: '
                '{"relevance_score": 0-1, "population_type": '
                '"cycling|endurance_other|untrained|mixed|unclear", "is_cycling": bool, '
                '"decision": "include|exclude", "reason": "..."}. '
                "Sii PERMISSIVO nell'inclusione: includi per default se lo studio riguarda "
                "esercizio/allenamento di endurance con un intervento o un esito pertinenti al "
                "topic, ANCHE se la popolazione non è esplicitamente ciclistica (atleti endurance "
                "allenati, coorti miste) — la trasferibilità ai ciclisti competitivi è valutata a "
                "valle nella qualità, NON è compito dello screening escluderla. Non escludere per "
                "abstract assente: giudica dal titolo e nel dubbio includi. Escludi SOLO: (a) ciò "
                "che non è uno studio (didascalie di figure/tabelle, frammenti, titoli-stub "
                "generici); (b) un dominio palesemente estraneo alla fisiologia/allenamento "
                "sportivo; (c) una popolazione clinica/sedentaria senza alcuna rilevanza per atleti "
                "di endurance; (d) una popolazione clinica non atletica esplicitamente dichiarata "
                "(es. pazienti diabetici/oncologici/dializzati, neonati, gravidanza) SENZA alcun "
                "collegamento con atleti o allenamento sportivo — se lo studio riguarda atleti CON "
                "una condizione clinica (es. ciclisti con diabete di tipo 1), non è (d): includi. "
                "Nel dubbio, INCLUDI. Registra sempre il motivo."
            )
        )
        if not data:
            return None
        arr = data.get("results")
        if not isinstance(arr, list):
            return None
        return [self._parse_screen(arr[i]) if i < len(arr) else None for i in range(len(chunk))]

    def _parse_screen(self, data):
        if not isinstance(data, dict):
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
        clinical = _count(blob, CLINICAL_NONATHLETE_MARKERS)
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
                   "trained": trained, "exercise_context": context, "token_overlap": overlap,
                   "clinical_nonathlete": clinical}

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
        elif population == PopulationType.UNCLEAR and clinical and not trained:
            # Popolazione clinica non atletica dichiarata esplicitamente (neonati, gravidanza,
            # dialisi, oncologia...) senza alcun segnale di atleti/allenamento: fuori perimetro.
            # Uno studio su "cyclists with type 1 diabetes" non arriva qui: cyc>0 lo rende CYCLING/MIXED sopra.
            decision, reason = "exclude", "Popolazione clinica non atletica (es. patologia, neonatale, gravidanza) senza segnale di allenamento sportivo: fuori perimetro."
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
