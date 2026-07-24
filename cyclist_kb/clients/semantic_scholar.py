"""Client Semantic Scholar (Graph API, endpoint /paper/search)."""

from __future__ import annotations

from typing import List, Optional

from ..models import PaperRecord, SourceDB, make_record_id
from .base import HttpFetcher

SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = ("title,abstract,year,authors,externalIds,openAccessPdf,venue,"
          "publicationTypes,references.externalIds")


class SemanticScholarClient:
    source = SourceDB.SEMANTIC_SCHOLAR.value

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        self._fetcher = fetcher

    async def search(self, query: str, limit: int, research_id: str) -> List[PaperRecord]:
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            params = {"query": query, "limit": min(limit, 100), "fields": FIELDS}
            data = await fetcher.get_json(SEARCH, params=params)
            if not data:
                return []
            return [self._parse(p, research_id) for p in data.get("data", []) if p]
        finally:
            if own:
                await fetcher.__aexit__()

    def _parse(self, p: dict, research_id: str) -> PaperRecord:
        ext = p.get("externalIds") or {}
        doi = ext.get("DOI")
        pmid = ext.get("PubMed")
        title = p.get("title")
        authors = [a.get("name") for a in p.get("authors", []) if a.get("name")]
        oa = p.get("openAccessPdf") or {}

        # Referenze con DOI note → semi per citation chasing.
        references = []
        for r in p.get("references", []) or []:
            rext = (r or {}).get("externalIds") or {}
            if rext.get("DOI"):
                references.append(f"https://doi.org/{rext['DOI']}")

        return PaperRecord(
            id=make_record_id(research_id, doi=doi, pmid=pmid, title=title),
            research_id=research_id,
            doi=doi,
            pmid=str(pmid) if pmid else None,
            title=title,
            abstract=p.get("abstract"),
            authors=authors,
            year=p.get("year"),
            journal=p.get("venue"),
            url=(f"https://doi.org/{doi}" if doi else None),
            oa_url=oa.get("url"),
            oa_status=oa.get("status"),
            source_dbs=[self.source],
            references=references,
            discovered_via="query",
            raw={self.source: p},  # payload API grezzo
        )
