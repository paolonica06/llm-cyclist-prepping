"""Utility di normalizzazione testuale condivise (dedup, screening, estrazione)."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, Optional


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def normalize_title(title: Optional[str]) -> str:
    """Titolo normalizzato per il confronto: minuscolo, senza accenti né punteggiatura."""
    if not title:
        return ""
    t = _strip_accents(title.lower())
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def first_author_key(authors: List[str]) -> str:
    """Chiave del primo autore: cognome minuscolo senza accenti.

    Le fonti usano formati diversi e incoerenti — PubMed «Guenette JA» (cognome
    prima), OpenAlex/Semantic Scholar «Jordan A. Guenette» (nome prima), Crossref
    normalizzato «Guenette Jordan A.». Per essere robusti al confronto cross-fonte
    si prende il token alfabetico più lungo (le iniziali vengono scartate): in
    tutti e tre i casi risulta «guenette». Con «Cognome, Nome» si usa la parte
    prima della virgola.
    """
    if not authors:
        return ""
    a = authors[0].strip()
    if not a:
        return ""
    if "," in a:
        return _strip_accents(a.split(",")[0].lower()).strip()
    parts = [p for p in re.split(r"[.\s]+", a) if p]
    words = [p for p in parts if len(p) > 1] or parts
    if not words:  # nome di sola punteggiatura/spazi: nessun cognome estraibile
        return ""
    surname = max(words, key=len)  # a parità di lunghezza vince il primo (di solito il cognome)
    return _strip_accents(surname.lower()).strip()


def similarity(a: str, b: str) -> float:
    """Rapporto di similarità 0-1 fra due stringhe (già normalizzabili dal chiamante)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def title_signature(title: Optional[str], year: Optional[int], authors: List[str]) -> str:
    """Firma composita titolo+anno+primo autore per l'ultimo stadio della dedup."""
    return f"{normalize_title(title)}|{year or ''}|{first_author_key(authors)}"


def tokens(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return re.findall(r"[a-z0-9]+", _strip_accents(text.lower()))
