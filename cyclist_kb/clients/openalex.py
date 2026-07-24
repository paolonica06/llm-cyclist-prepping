"""Client OpenAlex (endpoint /works)."""

from __future__ import annotations

from typing import Dict, List, Optional

from ..config import get_settings
from ..models import PaperRecord, SourceDB, make_record_id
from .base import HttpFetcher

WORKS = "https://api.openalex.org/works"


class OpenAlexClient:
    source = SourceDB.OPENALEX.value

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        self._fetcher = fetcher
        self._email = get_settings().contact_email

    async def search(self, query: str, limit: int, research_id: str) -> List[PaperRecord]:
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            params = {
                "search": query,
                "per-page": min(limit, 200),
                "mailto": self._email,
                "select": ("id,doi,title,display_name,publication_year,"
                           "abstract_inverted_index,authorships,primary_location,"
                           "open_access,referenced_works,ids"),
            }
            data = await fetcher.get_json(WORKS, params=params)
            if not data:
                return []
            return [self._parse(w, research_id) for w in data.get("results", [])]
        finally:
            if own:
                await fetcher.__aexit__()

    async def fetch_by_id(self, work_id: str, research_id: str) -> Optional[PaperRecord]:
        """Risolve un singolo lavoro OpenAlex per id (per il citation chasing)."""
        wid = work_id.rstrip("/").split("/")[-1]
        if not wid.startswith("W"):
            return None
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            params = {"mailto": self._email}
            data = await fetcher.get_json(f"{WORKS}/{wid}", params=params)
            if not data or not data.get("id"):
                return None
            return self._parse(data, research_id)
        finally:
            if own:
                await fetcher.__aexit__()

    def _parse(self, w: dict, research_id: str) -> PaperRecord:
        doi = w.get("doi")  # es. https://doi.org/10.xxxx
        title = w.get("title") or w.get("display_name")
        year = w.get("publication_year")
        abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
        authors = [
            a.get("author", {}).get("display_name")
            for a in w.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        journal = None
        loc = w.get("primary_location") or {}
        if loc.get("source"):
            journal = loc["source"].get("display_name")

        oa = w.get("open_access") or {}
        oa_url = oa.get("oa_url")
        oa_status = oa.get("oa_status")

        ids = w.get("ids") or {}
        pmid = None
        if ids.get("pmid"):
            pmid = ids["pmid"].rstrip("/").split("/")[-1]

        # referenced_works: id OpenAlex dei lavori citati → semi per citation chasing.
        references = list(w.get("referenced_works", []) or [])

        return PaperRecord(
            id=make_record_id(research_id, doi=doi, pmid=pmid, title=title),
            research_id=research_id,
            doi=doi,
            pmid=pmid,
            title=title,
            abstract=abstract,
            authors=authors,
            year=year,
            journal=journal,
            url=w.get("id"),
            oa_url=oa_url,
            oa_status=oa_status,
            source_dbs=[self.source],
            references=references,
            discovered_via="query",
            raw={self.source: w},  # payload API grezzo (campi selezionati)
        )


def _reconstruct_abstract(inverted: Optional[Dict[str, List[int]]]) -> Optional[str]:
    """Ricostruisce l'abstract dall'inverted index posizionale di OpenAlex."""
    if not inverted:
        return None
    positions: List[tuple] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return None
    positions.sort()
    return " ".join(word for _, word in positions)
