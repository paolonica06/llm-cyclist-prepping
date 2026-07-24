"""Quality Agent: tipo di studio, qualità metodologica, confidenza, trasferibilità.

Il numero di citazioni NON è mai usato come misura di qualità: la valutazione si
basa su campione, controllo, randomizzazione, durata, misure e trasferibilità ai
ciclisti competitivi.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from ..config import get_settings
from ..domain import CONTROL_MARKERS, DESIGN_RANK, RANDOMIZATION_MARKERS, best_design
from ..llm import chunked, get_llm
from ..models import (PaperRecord, PopulationType, QualityAssessment, QualityLevel,
                      RecordState, Research)

logger = logging.getLogger("cyclist_kb.quality")


class QualityAgent:
    def __init__(self, db) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm()

    def run(self, research: Research) -> Research:
        records = self.db.list_records(research.id, states=[RecordState.EXTRACTED])
        assessed = 0
        batch_size = max(1, self.settings.llm_batch_size)
        for chunk in chunked(records, batch_size):
            batch = self._llm_assess_batch(chunk) if self.llm.available else None
            for i, rec in enumerate(chunk):
                rec.quality = (batch[i] if batch and i < len(batch) and batch[i] is not None
                               else self._heuristic_assess(rec))
                self.db.upsert_record(rec)
                assessed += 1
        research.stats.update({"quality_assessed": assessed})
        self.db.save_research(research)
        logger.info("Qualità %s: %d record valutati", research.id, assessed)
        return research

    # -- LLM (in batch, con fallback euristico) ---------------------------- #
    def _llm_assess_batch(self, chunk):
        """Valuta N record in UNA chiamata. Lista allineata a `chunk` (QualityAssessment
        o None per elemento), o None se la chiamata fallisce."""
        items = []
        for i, rec in enumerate(chunk):
            text = (rec.full_text or rec.abstract or "")[:2000]
            items.append(f"[{i + 1}] Titolo: {rec.title}\nTesto: {text}")
        data = self.llm.complete_json(
            prompt=(
                f"Valuta la qualità metodologica di CIASCUNO di questi {len(chunk)} studi per "
                "l'applicazione a ciclisti competitivi. NON usare il numero di citazioni.\n\n"
                + "\n\n".join(items) +
                '\n\nRestituisci SOLO JSON {"results": [...]}: array di ESATTAMENTE '
                f'{len(chunk)} oggetti nello STESSO ORDINE. Ogni oggetto: '
                '{"study_type": str, "methodological_quality": "low|moderate|high", '
                '"confidence_level": "low|moderate|high", '
                '"transferability_to_competitive_cyclists": "low|moderate|high", '
                '"dimensions": {"sample":..,"control":..,"randomization":..,"duration":..,'
                '"measures":..,"transferability":..}, "notes": [..]}.'
            )
        )
        if not data:
            return None
        arr = data.get("results")
        if not isinstance(arr, list):
            return None
        return [self._parse_quality(arr[i]) if i < len(arr) else None for i in range(len(chunk))]

    def _heuristic_assess(self, rec: PaperRecord) -> QualityAssessment:
        text = (rec.full_text or rec.abstract or "")
        low = f"{rec.title or ''} {text}".lower()
        ex = rec.extraction

        study_type = "unknown"
        if ex and ex.study_design.value:
            study_type = str(ex.study_design.value)
        else:
            study_type = best_design(low) or "unknown"  # disegno a rank più alto fra i match

        dims = {}
        notes = []

        # Campione.
        n = ex.sample_size.value if ex and ex.sample_size.value else _num(low, r"\bn\s*=\s*(\d+)")
        if n is None:
            dims["sample"] = "unknown"
            notes.append("Numerosità del campione non riportata nel testo disponibile.")
        elif n >= 20:
            dims["sample"] = "adequate"
        elif n >= 10:
            dims["sample"] = "small"
        else:
            dims["sample"] = "very_small"
            notes.append(f"Campione molto ridotto (n={n}): potenza statistica limitata.")

        # Controllo / comparatore.
        has_control = any(m in low for m in CONTROL_MARKERS) or bool(ex and ex.comparator.value)
        dims["control"] = "present" if has_control else "absent_or_unclear"

        # Randomizzazione.
        has_random = any(m in low for m in RANDOMIZATION_MARKERS)
        dims["randomization"] = "present" if has_random else "absent_or_unclear"

        # Durata.
        dur_weeks = _duration_weeks(low)
        if dur_weeks is None:
            dims["duration"] = "unknown"
        elif dur_weeks >= 6:
            dims["duration"] = "adequate"
        else:
            dims["duration"] = "short"
            notes.append(f"Durata dell'intervento breve (~{dur_weeks} settimane).")

        # Misure.
        objective = any(m in low for m in ("vo2max", "vo2 max", "maximal oxygen", "power output",
                                           "wattage", "gas exchange", "ergometer", "time trial"))
        dims["measures"] = "objective" if objective else "unclear"

        # Trasferibilità ai ciclisti competitivi.
        transfer = self._transferability(rec, low)
        dims["transferability"] = transfer.value

        # Qualità metodologica: aggregazione dei segnali "positivi".
        positive = sum([
            dims["sample"] == "adequate",
            dims["control"] == "present",
            dims["randomization"] == "present",
            dims["duration"] == "adequate",
            dims["measures"] == "objective",
        ])
        if positive >= 4:
            method = QualityLevel.HIGH
        elif positive >= 2:
            method = QualityLevel.MODERATE
        else:
            method = QualityLevel.LOW

        # Confidenza: combina disegno, qualità metodologica e trasferibilità.
        design_rank = DESIGN_RANK.get(study_type, 1)
        confidence = self._confidence(design_rank, method, transfer)

        return QualityAssessment(
            study_type=study_type,
            methodological_quality=method,
            confidence_level=confidence,
            transferability_to_competitive_cyclists=transfer,
            dimensions=dims,
            notes=notes,
            assessed_by="heuristic",
        )

    def _transferability(self, rec: PaperRecord, low: str) -> QualityLevel:
        pop = rec.screening.population_type if rec.screening else PopulationType.UNCLEAR
        competitive = any(w in low for w in ("competitive", "elite", "professional", "well-trained",
                                             "national level", "trained cyclists"))
        if pop == PopulationType.CYCLING and competitive:
            return QualityLevel.HIGH
        if pop == PopulationType.CYCLING:
            return QualityLevel.MODERATE
        if pop == PopulationType.MIXED:
            return QualityLevel.MODERATE
        return QualityLevel.LOW

    def _confidence(self, design_rank: int, method: QualityLevel, transfer: QualityLevel) -> QualityLevel:
        score = design_rank
        score += {QualityLevel.HIGH: 2, QualityLevel.MODERATE: 1, QualityLevel.LOW: 0}[method]
        score += {QualityLevel.HIGH: 1, QualityLevel.MODERATE: 0, QualityLevel.LOW: -1}[transfer]
        if score >= 6:
            return QualityLevel.HIGH
        if score >= 3:
            return QualityLevel.MODERATE
        return QualityLevel.LOW

    def _parse_quality(self, data):
        """Costruisce un QualityAssessment da un oggetto JSON (un elemento del batch)."""
        if not isinstance(data, dict):
            return None
        try:
            return QualityAssessment(
                study_type=str(data.get("study_type", "unknown")),
                methodological_quality=QualityLevel(data.get("methodological_quality", "low")),
                confidence_level=QualityLevel(data.get("confidence_level", "low")),
                transferability_to_competitive_cyclists=QualityLevel(
                    data.get("transferability_to_competitive_cyclists", "low")),
                dimensions={k: str(v) for k, v in (data.get("dimensions") or {}).items()},
                notes=[str(x) for x in (data.get("notes") or [])],
                assessed_by="llm",
            )
        except (ValueError, TypeError):
            return None


def _num(text: str, pattern: str) -> Optional[int]:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def _duration_weeks(low: str) -> Optional[int]:
    m = re.search(r"(\d{1,3})\s*[- ]?\s*week", low)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,3})\s*[- ]?\s*month", low)
    if m:
        return int(m.group(1)) * 4
    return None
