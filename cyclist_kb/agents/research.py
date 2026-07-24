"""Research Agent: genera query, interroga le fonti, salva il grezzo, fa citation chasing."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List, Tuple

from ..clients import CrossrefClient, OpenAlexClient, PubMedClient, SemanticScholarClient
from ..config import get_settings
from ..dedup import deduplicate
from ..domain import SYNONYMS
from ..llm import get_llm
from ..models import PaperRecord, RecordState, Research, ResearchStatus, make_record_id, normalize_doi

logger = logging.getLogger("cyclist_kb.research")


class ResearchAgent:
    def __init__(self, db) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm()

    # -- Generazione query -------------------------------------------------- #
    def generate_queries(self, topic: str) -> Tuple[List[str], Dict[str, List[str]]]:
        if self.llm.available:
            data = self.llm.complete_json(
                prompt=(
                    "Genera query di ricerca scientifica per banche dati bibliografiche "
                    f"sul tema: «{topic}».\n"
                    "Restituisci JSON con: {\"queries\": [5-8 stringhe booleane con sinonimi], "
                    "\"synonyms\": {termine: [sinonimi]}}. Includi varianti terminologiche "
                    "(es. VO2max/maximal oxygen uptake, HIIT/interval training)."
                )
            )
            if data and isinstance(data.get("queries"), list) and data["queries"]:
                queries = [q for q in data["queries"] if isinstance(q, str) and q.strip()]
                synonyms = data.get("synonyms", {}) if isinstance(data.get("synonyms"), dict) else {}
                if queries:
                    return queries[:8], synonyms
        return self._heuristic_queries(topic)

    def _heuristic_queries(self, topic: str) -> Tuple[List[str], Dict[str, List[str]]]:
        """Espande il topic con i sinonimi di dominio in alcune query booleane."""
        topic_low = topic.lower()
        used: Dict[str, List[str]] = {}
        for key, syns in SYNONYMS.items():
            if key in topic_low or any(s.lower() in topic_low for s in syns):
                used[key] = syns

        queries = [topic]  # la query "così com'è" è sempre inclusa
        # Query mirate combinando i gruppi di sinonimi presenti nel topic.
        groups = list(used.values())
        if groups:
            def or_group(g: List[str]) -> str:
                return "(" + " OR ".join(f'"{t}"' for t in g) + ")"

            # Prodotto ristretto: combina i primi due gruppi (di solito intervento×outcome).
            if len(groups) >= 2:
                queries.append(f"{or_group(groups[0])} AND {or_group(groups[1])}")
            if len(groups) >= 3:
                queries.append(
                    f"{or_group(groups[0])} AND {or_group(groups[1])} AND {or_group(groups[2])}"
                )
            for g in groups:
                queries.append(or_group(g) + " AND cycling")
        # Deduplica preservando l'ordine.
        seen = set()
        uniq = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                uniq.append(q)
        return uniq[:8], used

    # -- Esecuzione --------------------------------------------------------- #
    async def run(self, research: Research) -> Research:
        queries, synonyms = self.generate_queries(research.topic)
        research.queries = queries
        research.synonyms = synonyms
        logger.info("Ricerca %s: %d query generate", research.id, len(queries))

        collected: List[PaperRecord] = []
        tasks = []
        for qi, q in enumerate(queries):
            for client in (PubMedClient(), OpenAlexClient(),
                           SemanticScholarClient(), CrossrefClient()):
                tasks.append(self._search_one(client, q, qi, research.id))

        results = await asyncio.gather(*tasks)
        raw_by_source: Dict[str, List[dict]] = {}
        for source, qi, recs in results:
            collected.extend(recs)
            for r in recs:
                # Salva il payload API grezzo (in r.raw[source]), non solo il normalizzato.
                raw_by_source.setdefault(source, []).append(r.raw.get(source, r.model_dump()))

        deduped = deduplicate(collected)
        logger.info("Ricerca %s: %d grezzi → %d dopo dedup", research.id, len(collected), len(deduped))

        chased = await self._citation_chase(deduped, research.id)
        # Include anche i record da citation chasing nel grezzo salvato.
        for r in chased:
            for source in r.source_dbs:
                raw_by_source.setdefault(f"{source}_chased", []).append(r.raw.get(source, r.model_dump()))
        self._save_raw(research.id, raw_by_source)

        all_recs = deduplicate(deduped + chased)

        for rec in all_recs:
            # discovered → pending_screening
            if rec.state == RecordState.DISCOVERED:
                rec.state = RecordState.PENDING_SCREENING
            self.db.upsert_record(rec)

        research.status = ResearchStatus.SEARCHED
        research.stats.update({
            "queries": len(queries),
            "raw_results": len(collected),
            "after_dedup": len(deduped),
            "citation_chased": len(chased),
            "total_records": len(all_recs),
        })
        self.db.save_research(research)
        return research

    async def _search_one(self, client, query: str, qi: int, research_id: str
                          ) -> Tuple[str, int, List[PaperRecord]]:
        try:
            recs = await client.search(query, self.settings.results_per_source, research_id)
            logger.info("  [%s] q%d '%s' → %d", client.source, qi, query[:40], len(recs))
            return client.source, qi, recs
        except Exception as exc:  # nessuna fonte deve far fallire l'intera ricerca
            logger.warning("  [%s] q%d errore: %s", getattr(client, "source", "?"), qi, exc)
            return getattr(client, "source", "unknown"), qi, []

    def _save_raw(self, research_id: str, raw_by_source: Dict[str, List[dict]]) -> None:
        out_dir = self.settings.raw_dir / research_id
        out_dir.mkdir(parents=True, exist_ok=True)
        for source, items in raw_by_source.items():
            (out_dir / f"{source}.json").write_text(
                json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    # -- Citation chasing --------------------------------------------------- #
    async def _citation_chase(self, records: List[PaperRecord], research_id: str
                             ) -> List[PaperRecord]:
        seeds = self._rank_seeds(records)[: self.settings.citation_chase_seeds]
        if not seeds:
            return []

        known_dois = {r.normalized_doi() for r in records if r.normalized_doi()}
        # Raccoglie identificatori di referenza (DOI e id OpenAlex), evitando duplicati noti.
        doi_refs: List[Tuple[str, str]] = []      # (doi_url, seed_id)
        oa_refs: List[Tuple[str, str]] = []       # (openalex_id, seed_id)
        for seed in seeds:
            seed.seed_for_chasing = True
            self.db.upsert_record(seed)
            for ref in seed.references:
                if "doi.org" in ref:
                    if normalize_doi(ref) not in known_dois:
                        doi_refs.append((ref, seed.id))
                elif "openalex.org" in ref or ref.lstrip("/").startswith("W"):
                    oa_refs.append((ref, seed.id))

        limit = self.settings.citation_chase_limit
        doi_refs = doi_refs[:limit]
        oa_refs = oa_refs[: max(0, limit - len(doi_refs))]

        crossref = CrossrefClient()
        openalex = OpenAlexClient()
        chased: List[PaperRecord] = []

        async def resolve_doi(doi_url: str, seed_id: str):
            # Una referenza malformata non deve mai affossare l'intera ricerca.
            try:
                meta = await crossref.fetch_by_doi(doi_url)
                if not meta or not (meta.get("title") or meta.get("doi")):
                    return None
                return self._record_from_crossref(meta, research_id, seed_id)
            except Exception as exc:
                logger.warning("Citation chasing: DOI %s non risolto: %s", doi_url, exc)
                return None

        async def resolve_oa(oa_id: str, seed_id: str):
            try:
                rec = await openalex.fetch_by_id(oa_id, research_id)
                if rec:
                    rec.discovered_via = f"citation_chase:{seed_id}"
                    rec.state = RecordState.DISCOVERED
                return rec
            except Exception as exc:
                logger.warning("Citation chasing: OpenAlex %s non risolto: %s", oa_id, exc)
                return None

        tasks = [resolve_doi(d, s) for d, s in doi_refs] + [resolve_oa(o, s) for o, s in oa_refs]
        for rec in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(rec, PaperRecord):
                chased.append(rec)
            elif isinstance(rec, Exception):
                logger.warning("Citation chasing: errore ignorato: %s", rec)
        logger.info("Ricerca %s: citation chasing → %d nuovi record", research_id, len(chased))
        return chased

    def _rank_seeds(self, records: List[PaperRecord]) -> List[PaperRecord]:
        """Ordina i record per numero di referenze note (più materiale da inseguire)."""
        with_refs = [r for r in records if r.references]
        return sorted(with_refs, key=lambda r: len(r.references), reverse=True)

    def _record_from_crossref(self, meta: dict, research_id: str, seed_id: str) -> PaperRecord:
        return PaperRecord(
            id=make_record_id(research_id, doi=meta.get("doi"), title=meta.get("title")),
            research_id=research_id,
            doi=meta.get("doi"),
            title=meta.get("title"),
            abstract=meta.get("abstract"),
            authors=meta.get("authors", []),
            year=meta.get("year"),
            journal=meta.get("journal"),
            url=meta.get("url"),
            source_dbs=[CrossrefClient.source],
            references=meta.get("references", []),
            state=RecordState.DISCOVERED,
            discovered_via=f"citation_chase:{seed_id}",
            raw={"crossref": {"via": "citation_chase"}},
        )
