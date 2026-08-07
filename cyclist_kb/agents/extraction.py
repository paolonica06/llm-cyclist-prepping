"""Extraction Agent: estrae i campi strutturati da abstract e (se lecito) full text.

Regole: (1) mai inventare dati assenti → `value=None`; (2) distinguere sempre se
un dato proviene dal full text o dal solo abstract (`ExtractedField.source`); (3)
recuperare il full text solo da fonti open access, senza scaricare PDF protetti.
"""

from __future__ import annotations

import io
import logging
import re
from typing import List, Optional

import pypdf

from ..clients.base import HttpFetcher
from ..config import get_settings
from ..domain import TRAINED_MARKERS, UNTRAINED_MARKERS, best_design
from ..llm import chunked, get_llm
from ..models import (DataSource, Extraction, ExtractedField, PaperRecord,
                      RecordState, Research, ResearchStatus)

logger = logging.getLogger("cyclist_kb.extraction")

MIN_FULLTEXT_CHARS = 1500  # sotto questa soglia non consideriamo "full text" affidabile
MAX_PDF_BYTES = 15_000_000  # non scarichiamo/parsiamo PDF oltre questa soglia (MVP)


class ExtractionAgent:
    def __init__(self, db) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm()

    async def run(self, research: Research,
                  states: Optional[List[RecordState]] = None) -> Research:
        # Estraiamo dai record verificati; i NEEDS_REVIEW restano fuori dalla wiki
        # ma possono comunque essere estratti per ispezione manuale. `states`
        # permette di restringere il perimetro (es. reassess: solo METADATA_VERIFIED,
        # per non ri-estrarre i needs_review preesistenti — niente fetch/token inutili).
        records = self.db.list_records(
            research.id,
            states=states or [RecordState.METADATA_VERIFIED, RecordState.NEEDS_REVIEW],
        )
        full_text = abstract_only = 0
        # 1) preparazione sorgente per-record (async, rete) — non batchabile.
        prepared = []
        for rec in records:
            based_on = await self._prepare_source(rec)
            # Cattura la distinzione degli stati full_text_available / abstract_only.
            if based_on == DataSource.FULL_TEXT:
                full_text += 1
                rec.content_availability = RecordState.FULL_TEXT_AVAILABLE.value
            else:
                abstract_only += 1
                rec.content_availability = RecordState.ABSTRACT_ONLY.value
            prepared.append((rec, based_on))

        # 2) estrazione LLM in batch (N record per chiamata), fallback euristico.
        batch_size = max(1, self.settings.llm_batch_size)
        for chunk in chunked(prepared, batch_size):
            batch = self._llm_extract_batch(chunk) if self.llm.available else None
            for i, (rec, based_on) in enumerate(chunk):
                ex = (batch[i] if batch and i < len(batch) and batch[i] is not None
                      else self._heuristic_extract(rec, based_on))
                rec.extraction = ex
                # I record verificati con estrazione completata passano a EXTRACTED;
                # quelli da rivedere restano NEEDS_REVIEW (fuori dalla sintesi).
                if rec.state == RecordState.METADATA_VERIFIED:
                    rec.state = RecordState.EXTRACTED
                self.db.upsert_record(rec)

        research.status = ResearchStatus.EXTRACTED
        research.stats.update({"extracted_full_text": full_text,
                               "extracted_abstract_only": abstract_only})
        self.db.save_research(research)
        logger.info("Estrazione %s: %d da full text, %d da solo abstract",
                    research.id, full_text, abstract_only)
        return research

    # -- Recupero (lecito) del full text ------------------------------------ #
    async def _prepare_source(self, rec: PaperRecord) -> DataSource:
        """Se disponibile via OA e recuperabile come testo (HTML o PDF), popola rec.full_text."""
        if rec.full_text and len(rec.full_text) >= MIN_FULLTEXT_CHARS:
            return DataSource.FULL_TEXT
        url = rec.oa_url
        if not url:
            return DataSource.ABSTRACT if rec.abstract else DataSource.NOT_AVAILABLE
        try:
            async with HttpFetcher() as fetcher:
                raw = await fetcher.get_bytes(url)
            text = _decode_source(raw)
            if text and len(text) >= MIN_FULLTEXT_CHARS and _looks_like_text(text):
                rec.full_text = text
                return DataSource.FULL_TEXT
        except Exception as exc:
            logger.debug("Full text non recuperato per %s: %s", rec.id, exc)
        return DataSource.ABSTRACT if rec.abstract else DataSource.NOT_AVAILABLE

    # -- Estrazione (LLM in batch, con fallback euristico) ----------------- #
    def _llm_extract_batch(self, chunk):
        """Estrae N record in UNA chiamata. Lista allineata a `chunk` (Extraction o
        None per elemento), o None se la chiamata fallisce."""
        items = []
        for i, (rec, based_on) in enumerate(chunk):
            src = "full text" if based_on == DataSource.FULL_TEXT else "solo abstract"
            items.append(
                f"[{i + 1}] (FONTE: {src}) Titolo: {rec.title}\n"
                f"Testo: {self._text_for(rec, based_on)[:2000]}"
            )
        data = self.llm.complete_json(
            prompt=(
                f"Estrai i dati da CIASCUNO di questi {len(chunk)} studi. NON inventare: usa null "
                "per i campi assenti.\n\n" + "\n\n".join(items) +
                '\n\nRestituisci SOLO JSON {"results": [...]}: array di ESATTAMENTE '
                f"{len(chunk)} oggetti nello STESSO ORDINE. Ogni oggetto con chiavi: study_design, "
                "participants, training_level, sex, age, sample_size, protocol, comparator, "
                "duration, outcomes, results, effect_size, limitations, conflicts_of_interest. "
                "null se il dato non è presente nel testo. Mantieni i valori nella lingua del "
                "testo sorgente (di norma inglese): NON tradurre. Non inferire dal solo titolo "
                "quando il testo è assente."
            )
        )
        if not data:
            return None
        arr = data.get("results")
        if not isinstance(arr, list):
            return None
        return [self._build_extraction(chunk[i][0], chunk[i][1], arr[i]) if i < len(arr) else None
                for i in range(len(chunk))]

    def _text_for(self, rec: PaperRecord, based_on: DataSource) -> str:
        if based_on == DataSource.FULL_TEXT and rec.full_text:
            return rec.full_text
        return rec.abstract or ""

    def _bib_field(self, value, based_on: DataSource) -> ExtractedField:
        """Campo bibliografico: proviene dal record normalizzato (metadati), non dal
        corpo del testo → source=METADATA, non ABSTRACT/FULL_TEXT."""
        if value in (None, "", []):
            return ExtractedField(value=None, source=DataSource.NOT_AVAILABLE)
        return ExtractedField(value=value, source=DataSource.METADATA)

    def _heuristic_extract(self, rec: PaperRecord, based_on: DataSource) -> Extraction:
        text = self._text_for(rec, based_on)
        low = text.lower()
        src = based_on if text else DataSource.NOT_AVAILABLE

        def field(value: Optional[object], note: Optional[str] = None) -> ExtractedField:
            if value in (None, "", []):
                return ExtractedField(value=None, source=DataSource.NOT_AVAILABLE, note=note)
            return ExtractedField(value=value, source=src, note=note)

        ex = Extraction(based_on=based_on, extracted_by="heuristic")
        # Bibliografici (dal record normalizzato).
        ex.title = self._bib_field(rec.title, based_on)
        ex.authors = self._bib_field(rec.authors, based_on)
        ex.year = self._bib_field(rec.year, based_on)
        ex.journal = self._bib_field(rec.journal, based_on)
        ex.doi = self._bib_field(rec.doi, based_on)
        ex.pmid = self._bib_field(rec.pmid, based_on)

        # Da testo.
        ex.study_design = field(_detect_design(low))
        ex.sample_size = field(_sample_size(low))
        ex.age = field(_age(text))
        ex.sex = field(_sex(low))
        ex.training_level = field(_training_level(low))
        ex.duration = field(_duration(low))
        ex.protocol = field(_protocol_snippet(text))
        ex.comparator = field(_comparator(text))
        ex.outcomes = field(_outcomes(text))
        ex.results = field(_results_snippet(text))
        ex.effect_size = field(_effect_size(text))
        ex.participants = field(_participants(text))
        # Limiti e conflitti quasi mai nell'abstract: assenti salvo full text.
        ex.limitations = field(_section_snippet(text, ["limitation", "limitazioni"]),
                               note="Assente se non nel full text.")
        ex.conflicts_of_interest = field(
            _section_snippet(text, ["conflict of interest", "competing interest", "conflitti"]),
            note="Assente se non nel full text.")
        return ex

    def _build_extraction(self, rec: PaperRecord, based_on: DataSource, data) -> Optional[Extraction]:
        """Costruisce un'Extraction da un oggetto JSON (un elemento del batch)."""
        if not isinstance(data, dict):
            return None
        ex = Extraction(based_on=based_on, extracted_by="llm")
        ex.title = self._bib_field(rec.title, based_on)
        ex.authors = self._bib_field(rec.authors, based_on)
        ex.year = self._bib_field(rec.year, based_on)
        ex.journal = self._bib_field(rec.journal, based_on)
        ex.doi = self._bib_field(rec.doi, based_on)
        ex.pmid = self._bib_field(rec.pmid, based_on)
        for name in ("study_design", "participants", "training_level", "sex", "age", "sample_size",
                     "protocol", "comparator", "duration", "outcomes", "results", "effect_size",
                     "limitations", "conflicts_of_interest"):
            val = data.get(name)
            if name == "sample_size":  # uniforma il tipo col ramo euristico (int)
                val = _coerce_int(val)
            if val in ("", []):
                val = None
            src = based_on if val is not None else DataSource.NOT_AVAILABLE
            setattr(ex, name, ExtractedField(value=val, source=src))
        return ex


# --------------------------------------------------------------------------- #
# Estrattori euristici (regex). Restituiscono None se il dato non è presente.
# --------------------------------------------------------------------------- #
def _coerce_int(val) -> Optional[int]:
    """Coerce un valore (int o stringa numerica) a int; None se non numerico."""
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    m = re.search(r"\d+", str(val))
    return int(m.group(0)) if m else None


def _detect_design(low: str) -> Optional[str]:
    return best_design(low)  # disegno a rank di evidenza più alto fra i marcatori presenti


def _sample_size(low: str) -> Optional[int]:
    m = re.search(r"\bn\s*=\s*(\d{1,4})", low)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,4})\s+(?:participants|subjects|cyclists|athletes|men|women|"
                  r"males|females|volunteers|riders)", low)
    if m:
        return int(m.group(1))
    return None


def _age(text: str) -> Optional[str]:
    m = re.search(r"(?:mean age|aged|age)[^.]{0,30}?(\d{1,2}(?:\.\d)?\s*(?:±|\+/-|to|-)\s*\d{1,2}"
                  r"(?:\.\d)?)\s*(?:year|yr|y)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"(\d{1,2}(?:\.\d)?\s*(?:±|\+/-)\s*\d{1,2}(?:\.\d)?)\s*(?:year|yr|y)", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _sex(low: str) -> Optional[str]:
    has_m = any(w in low for w in ("male", "men", "males"))
    has_f = any(w in low for w in ("female", "women", "females"))
    if has_m and has_f:
        return "mixed"
    if has_m:
        return "male"
    if has_f:
        return "female"
    return None


def _training_level(low: str) -> Optional[str]:
    for m in TRAINED_MARKERS:
        if m in low:
            return m
    for m in UNTRAINED_MARKERS:
        if m in low:
            return m
    return None


def _duration(low: str) -> Optional[str]:
    m = re.search(r"(\d{1,3})\s*[- ]?\s*(week|weeks|day|days|month|months|session|sessions)", low)
    return f"{m.group(1)} {m.group(2)}" if m else None


def _protocol_snippet(text: str) -> Optional[str]:
    return _sentence_with(text, ["interval", "hiit", "sprint", "protocol", "training program",
                                 "session", "min at", "% of"])


def _comparator(text: str) -> Optional[str]:
    return _sentence_with(text, ["compared with", "versus", "control group", "control condition",
                                 "vs.", "vs ", "compared to"])


def _outcomes(text: str) -> Optional[str]:
    return _sentence_with(text, ["vo2max", "vo2 max", "maximal oxygen", "power output",
                                 "time trial", "performance", "peak power", "threshold"])


def _results_snippet(text: str) -> Optional[str]:
    return _sentence_with(text, ["increased", "decreased", "improved", "significant", "greater",
                                 "higher", "lower", "no difference", "p <", "p<", "p ="])


def _effect_size(text: str) -> Optional[str]:
    m = re.search(r"(?:cohen'?s?\s*)?(?:\bd\b|\bg\b|es|effect size)\s*=\s*(-?\d+\.\d+)",
                  text, re.IGNORECASE)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,3}(?:\.\d+)?\s*%)\s+(?:increase|improvement|greater|higher)", text, re.IGNORECASE)
    return m.group(0) if m else None


def _participants(text: str) -> Optional[str]:
    return _sentence_with(text, ["participants", "subjects", "cyclists", "athletes", "recruited",
                                 "volunteers"])


def _section_snippet(text: str, keywords: List[str]) -> Optional[str]:
    return _sentence_with(text, keywords)


def _sentence_with(text: str, keywords: List[str]) -> Optional[str]:
    if not text:
        return None
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        low = sentence.lower()
        if any(k in low for k in keywords):
            s = sentence.strip()
            return s[:400]
    return None


def _looks_like_text(text: str) -> bool:
    """Rifiuta contenuti binari (es. PDF): richiede prevalenza di caratteri stampabili."""
    sample = text[:4000]
    if not sample:
        return False
    printable = sum(1 for c in sample if c.isprintable() or c in " \t\n\r")
    return (printable / len(sample)) >= 0.9 and " " in sample


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _decode_source(raw: Optional[bytes]) -> Optional[str]:
    """Decodifica il corpo grezzo di una risposta OA: PDF, HTML o testo semplice.

    Riconosce il contenuto dai byte (magic number), non dall'estensione dell'URL:
    un link OA senza suffisso .pdf può comunque servire un PDF, e viceversa.
    """
    if not raw or len(raw) > MAX_PDF_BYTES:
        return None
    if raw.lstrip().startswith(b"%PDF"):
        return _pdf_to_text(raw)
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return None
    if "<html" in text.lower():
        text = _html_to_text(text)
    return text


def _pdf_to_text(raw: bytes) -> Optional[str]:
    """Estrae il testo da un PDF open access. None se cifrato o illeggibile."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            return None
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        logger.debug("Parsing PDF fallito: %s", exc)
        return None
    return text.strip() or None
