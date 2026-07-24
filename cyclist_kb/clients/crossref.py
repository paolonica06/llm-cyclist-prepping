"""Client Crossref (endpoint /works e /works/{doi}).

Usato sia per la scoperta (search) sia dalla verifica dei metadati (lookup DOI).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..config import get_settings
from ..models import PaperRecord, SourceDB, make_record_id
from .base import HttpFetcher

WORKS = "https://api.crossref.org/works"


class CrossrefClient:
    source = SourceDB.CROSSREF.value

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        self._fetcher = fetcher
        self._email = get_settings().contact_email

    async def search(self, query: str, limit: int, research_id: str) -> List[PaperRecord]:
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            params = {"query": query, "rows": min(limit, 100), "mailto": self._email,
                      "select": "DOI,title,author,issued,container-title,abstract,URL,type,reference"}
            data = await fetcher.get_json(WORKS, params=params)
            if not data:
                return []
            items = data.get("message", {}).get("items", [])
            return [self._parse(it, research_id) for it in items]
        finally:
            if own:
                await fetcher.__aexit__()

    async def fetch_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Metadati normalizzati per un DOI (per la verifica). None se non trovato."""
        from ..models import normalize_doi

        ndoi = normalize_doi(doi)
        if not ndoi:
            return None
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            params = {"mailto": self._email}
            data = await fetcher.get_json(f"{WORKS}/{ndoi}", params=params)
            if not data or "message" not in data:
                return None
            return _normalize_message(data["message"])
        finally:
            if own:
                await fetcher.__aexit__()

    def _parse(self, it: dict, research_id: str) -> PaperRecord:
        m = _normalize_message(it)
        return PaperRecord(
            id=make_record_id(research_id, doi=m["doi"], title=m["title"]),
            research_id=research_id,
            doi=m["doi"],
            title=m["title"],
            abstract=m["abstract"],
            authors=m["authors"],
            year=m["year"],
            journal=m["journal"],
            url=m["url"],
            source_dbs=[self.source],
            references=m["references"],
            discovered_via="query",
            raw={self.source: it},  # payload API grezzo (item Crossref)
        )


def _normalize_message(m: dict) -> Dict[str, Any]:
    """Estrae i campi comuni da un 'message'/'item' Crossref."""
    title_list = m.get("title") or []
    title = title_list[0] if title_list else None

    authors = []
    for a in m.get("author", []) or []:
        family = a.get("family")
        given = a.get("given")
        name = a.get("name")
        if family:
            authors.append(f"{family} {given}".strip() if given else family)
        elif name:
            authors.append(name)

    year = None
    issued = (m.get("issued") or {}).get("date-parts") or []
    if issued and issued[0]:
        year = issued[0][0]

    container = m.get("container-title") or []
    journal = container[0] if container else None

    abstract = m.get("abstract")
    if abstract:
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()  # rimuove markup JATS

    references = []
    for r in m.get("reference", []) or []:
        if r.get("DOI"):
            references.append(f"https://doi.org/{r['DOI']}")

    return {
        "doi": (f"https://doi.org/{m['DOI']}" if m.get("DOI") else None),
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "abstract": abstract,
        "url": m.get("URL"),
        "type": m.get("type"),
        "references": references,
    }
