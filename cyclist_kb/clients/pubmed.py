"""Client PubMed via NCBI E-utilities (esearch + efetch)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List, Optional

from ..config import get_settings
from ..models import PaperRecord, SourceDB, make_record_id
from .base import HttpFetcher

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


class PubMedClient:
    source = SourceDB.PUBMED.value

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        self._fetcher = fetcher
        self._settings = get_settings()

    def _common_params(self) -> dict:
        p = {"db": "pubmed", "tool": "cyclist-kb", "email": self._settings.contact_email}
        if self._settings.ncbi_api_key:
            p["api_key"] = self._settings.ncbi_api_key
        return p

    async def search(self, query: str, limit: int, research_id: str) -> List[PaperRecord]:
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            pmids = await self._esearch(fetcher, query, limit)
            if not pmids:
                return []
            return await self._efetch(fetcher, pmids, research_id)
        finally:
            if own:
                await fetcher.__aexit__()

    async def fetch_summary(self, pmid: str) -> Optional[dict]:
        """Metadati normalizzati per un PMID via esummary (per la verifica)."""
        pmid = (pmid or "").strip()
        if not pmid:
            return None
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            params = self._common_params()
            params.update({"id": pmid, "retmode": "json"})
            data = await fetcher.get_json(ESUMMARY, params=params)
            if not data:
                return None
            doc = (data.get("result", {}) or {}).get(pmid)
            if not doc:
                return None
            authors = [a.get("name") for a in doc.get("authors", []) if a.get("name")]
            year = None
            pubdate = doc.get("pubdate") or doc.get("sortpubdate") or ""
            digits = "".join(ch for ch in pubdate[:4] if ch.isdigit())
            if len(digits) == 4:
                year = int(digits)
            doi = None
            for aid in doc.get("articleids", []):
                if aid.get("idtype") == "doi":
                    doi = aid.get("value")
            return {
                "pmid": pmid,
                "title": doc.get("title"),
                "authors": authors,
                "year": year,
                "journal": doc.get("fulljournalname") or doc.get("source"),
                "doi": doi,
            }
        finally:
            if own:
                await fetcher.__aexit__()

    async def _esearch(self, fetcher: HttpFetcher, query: str, limit: int) -> List[str]:
        params = self._common_params()
        params.update({"term": query, "retmax": limit, "retmode": "json"})
        data = await fetcher.get_json(ESEARCH, params=params)
        if not data:
            return []
        return data.get("esearchresult", {}).get("idlist", []) or []

    async def _efetch(self, fetcher: HttpFetcher, pmids: List[str], research_id: str) -> List[PaperRecord]:
        params = self._common_params()
        params.update({"id": ",".join(pmids), "retmode": "xml"})
        xml_text = await fetcher.get_text(EFETCH, params=params)
        if not xml_text:
            return []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        records: List[PaperRecord] = []
        for art in root.findall(".//PubmedArticle"):
            rec = self._parse_article(art, research_id)
            if rec:
                records.append(rec)
        return records

    def _parse_article(self, art: ET.Element, research_id: str) -> Optional[PaperRecord]:
        pmid_el = art.find(".//MedlineCitation/PMID")
        pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else None

        title_el = art.find(".//Article/ArticleTitle")
        title = _text(title_el)

        # Abstract: può avere più sezioni (Background/Methods/Results/Conclusions).
        abstract_parts = []
        for ab in art.findall(".//Article/Abstract/AbstractText"):
            label = ab.get("Label")
            txt = _text(ab)
            if txt:
                abstract_parts.append(f"{label}: {txt}" if label else txt)
        abstract = "\n".join(abstract_parts) or None

        authors = []
        for a in art.findall(".//Article/AuthorList/Author"):
            last = _text(a.find("LastName"))
            initials = _text(a.find("Initials"))
            collective = _text(a.find("CollectiveName"))
            if last:
                authors.append(f"{last} {initials}".strip())
            elif collective:
                authors.append(collective)

        journal = _text(art.find(".//Article/Journal/Title"))
        year = None
        year_el = art.find(".//Article/Journal/JournalIssue/PubDate/Year")
        if year_el is None:
            year_el = art.find(".//Article/Journal/JournalIssue/PubDate/MedlineDate")
        if year_el is not None and year_el.text:
            digits = "".join(ch for ch in year_el.text[:4] if ch.isdigit())
            year = int(digits) if len(digits) == 4 else None

        doi = None
        for aid in art.findall(".//ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi" and aid.text:
                doi = aid.text.strip()

        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
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
            url=url,
            source_dbs=[self.source],
            discovered_via="query",
            raw={self.source: {"pmid": pmid, "doi": doi,
                               "xml": ET.tostring(art, encoding="unicode")}},  # payload grezzo
        )


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None:
        return None
    # itertext gestisce tag inline (es. <i>, <sup>) dentro titoli/abstract.
    txt = "".join(el.itertext()).strip()
    return txt or None
