"""Verification Agent: verifica DOI/PMID e coerenza dei metadati.

Impedisce l'ingresso nella wiki di citazioni non verificate: solo i record che
raggiungono lo stato METADATA_VERIFIED vengono poi sintetizzati. I record
incoerenti o non verificabili passano a NEEDS_REVIEW, mai eliminati.
"""

from __future__ import annotations

import asyncio
import logging

from ..clients import CrossrefClient, PubMedClient
from ..config import get_settings
from ..models import (PaperRecord, RecordState, Research, ResearchStatus,
                      VerificationResult, normalize_doi)
from ..textutil import first_author_key, normalize_title, similarity

logger = logging.getLogger("cyclist_kb.verification")

TITLE_MATCH_THRESHOLD = 0.85
JOURNAL_MATCH_THRESHOLD = 0.60


class VerificationAgent:
    def __init__(self, db) -> None:
        self.db = db
        self.settings = get_settings()
        self.crossref = CrossrefClient()
        self.pubmed = PubMedClient()

    async def run(self, research: Research) -> Research:
        records = self.db.list_records(research.id, states=[RecordState.INCLUDED])
        verified = flagged = 0
        results = await asyncio.gather(*(self._verify(rec) for rec in records))
        for rec, vres in zip(records, results):
            rec.verification = vres
            if vres.verified:
                rec.state = RecordState.METADATA_VERIFIED
                verified += 1
            else:
                rec.state = RecordState.NEEDS_REVIEW
                flagged += 1
            self.db.upsert_record(rec)

        research.status = ResearchStatus.VERIFIED
        research.stats.update({"verified": verified, "needs_review": flagged})
        self.db.save_research(research)
        logger.info("Verifica %s: %d verificati, %d da rivedere", research.id, verified, flagged)
        return research

    async def _verify(self, rec: PaperRecord) -> VerificationResult:
        res = VerificationResult()
        crossref_meta = await self.crossref.fetch_by_doi(rec.doi) if rec.doi else None
        pubmed_meta = await self.pubmed.fetch_summary(rec.pmid) if rec.pmid else None

        if rec.doi:
            res.doi_valid = crossref_meta is not None
            if crossref_meta is None:
                res.inconsistencies.append(f"DOI non risolvibile su Crossref: {rec.doi}")
        if rec.pmid:
            res.pmid_valid = pubmed_meta is not None
            if pubmed_meta is None:
                res.inconsistencies.append(f"PMID non risolvibile su PubMed: {rec.pmid}")

        res.crossref_metadata = crossref_meta or {}
        res.pubmed_metadata = pubmed_meta or {}

        # Confronta il record contro OGNI fonte disponibile (non solo Crossref):
        # se il PMID risolve a un lavoro diverso, il disallineamento va rilevato.
        comparisons = []
        if crossref_meta:
            comparisons.append(self._compare_to(rec, crossref_meta, "Crossref", res))
        if pubmed_meta:
            comparisons.append(self._compare_to(rec, pubmed_meta, "PubMed", res))
        self._aggregate(comparisons, res)

        # Coerenza incrociata DOI↔PMID quando entrambi presenti.
        identifiers_consistent = True
        if crossref_meta and pubmed_meta:
            identifiers_consistent = self._cross_check(crossref_meta, pubmed_meta, res)

        res.verified = self._decide(rec, res, identifiers_consistent)
        return res

    def _compare_to(self, rec: PaperRecord, meta: dict, label: str, res: VerificationResult) -> dict:
        """Confronta il record con una singola fonte; ritorna i match per campo (bool/None)."""
        c = {"title": None, "author": None, "year": None, "journal": None}
        if rec.title and meta.get("title"):
            sim = similarity(normalize_title(rec.title), normalize_title(meta["title"]))
            c["title"] = sim >= TITLE_MATCH_THRESHOLD
            if not c["title"]:
                res.inconsistencies.append(
                    f"[{label}] Titolo discordante (similarità {sim:.2f}): «{rec.title}» vs «{meta['title']}»")
        if rec.authors and meta.get("authors"):
            c["author"] = first_author_key(rec.authors) == first_author_key(meta["authors"])
            if not c["author"]:
                res.inconsistencies.append(
                    f"[{label}] Primo autore discordante: '{first_author_key(rec.authors)}' vs "
                    f"'{first_author_key(meta['authors'])}'")
        if rec.year and meta.get("year"):
            c["year"] = abs(int(rec.year) - int(meta["year"])) <= 1  # tolleranza online/print
            if not c["year"]:
                res.inconsistencies.append(f"[{label}] Anno discordante: {rec.year} vs {meta['year']}")
        if rec.journal and meta.get("journal"):
            sim = similarity(normalize_title(rec.journal), normalize_title(meta["journal"]))
            c["journal"] = sim >= JOURNAL_MATCH_THRESHOLD
            if not c["journal"]:
                res.inconsistencies.append(
                    f"[{label}] Rivista discordante: «{rec.journal}» vs «{meta['journal']}»")
        return c

    def _aggregate(self, comparisons: list, res: VerificationResult) -> None:
        """Aggrega i confronti multi-fonte: un match è True solo se nessuna fonte lo contraddice."""
        for field, attr in (("title", "title_match"), ("author", "author_match"),
                            ("year", "year_match"), ("journal", "journal_match")):
            vals = [c[field] for c in comparisons if c[field] is not None]
            setattr(res, attr, (all(vals) if vals else None))

    def _cross_check(self, crossref_meta: dict, pubmed_meta: dict, res: VerificationResult) -> bool:
        """False se DOI e PMID puntano a lavori diversi."""
        c_doi = normalize_doi(crossref_meta.get("doi"))
        p_doi = normalize_doi(pubmed_meta.get("doi"))
        if c_doi and p_doi and c_doi != p_doi:
            res.inconsistencies.append(
                "DOI riportato da PubMed diverso da quello Crossref: DOI e PMID indicano lavori diversi.")
            return False
        return True

    def _decide(self, rec: PaperRecord, res: VerificationResult, identifiers_consistent: bool) -> bool:
        """Verificato solo se: un identificatore presente risolve, DOI/PMID sono coerenti,
        e almeno il titolo è stato confrontato con esito positivo."""
        if not (rec.doi or rec.pmid):
            res.inconsistencies.append("Nessun DOI/PMID: impossibile verificare.")
            return False
        # Ogni identificatore PRESENTE deve risolvere (uno irrisolvibile blocca).
        if rec.doi and res.doi_valid is False:
            return False
        if rec.pmid and res.pmid_valid is False:
            return False
        if not (res.doi_valid or res.pmid_valid):
            return False
        # DOI e PMID non devono puntare a lavori diversi.
        if not identifiers_consistent:
            return False
        # Serve un confronto positivo sul titolo: niente "verificato" senza confronto reale.
        if res.title_match is not True:
            if res.title_match is None:
                res.inconsistencies.append(
                    "Metadati locali insufficienti per il confronto (titolo assente): impossibile verificare.")
            return False
        return True
