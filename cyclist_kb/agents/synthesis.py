"""Synthesis Agent: aggiorna pagine Markdown interconnesse.

Principi: (1) separa Evidenze / Interpretazione / Applicazione pratica; (2)
conserva i risultati contrastanti invece di appiattirli; (3) non sovrascrive
silenziosamente le conclusioni precedenti (changelog + commit Git); (4) collega
ogni affermazione ai paper che la sostengono; (5) include solo record verificati.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..config import get_settings
from ..dedup import deduplicate
from ..llm import get_llm
from ..models import (ExtractedField, PaperRecord, RecordState, Research, ResearchStatus)
from ..wiki import Wiki, slugify, update_index

logger = logging.getLogger("cyclist_kb.synthesis")

# Temi di outcome per raggruppare le evidenze.
OUTCOME_THEMES: Dict[str, List[str]] = {
    "VO₂max / capacità aerobica": ["vo2max", "vo2 max", "vo2peak", "maximal oxygen", "aerobic capacity"],
    "Performance / potenza": ["performance", "power output", "peak power", "time trial", "watt", "mean power"],
    "Soglia / metabolismo": ["threshold", "lactate", "ftp", "economy", "efficiency"],
}
POSITIVE = ["increased", "improved", "greater", "higher", "enhanced", "significant improvement",
            "significantly higher", "augment", "beneficial", "gains"]
NULL = ["no difference", "no significant", "no change", "did not", "no effect", "unchanged",
        "trivial", "not significant", "not different", "similar"]
NEGATIVE = ["decreased", "reduced", "lower", "worse", "impaired", "declined", "detrimental"]


class SynthesisAgent:
    def __init__(self, db) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm()
        self.wiki = Wiki()

    def run(self, research: Research) -> Research:
        records = self.db.list_records(research.id, states=[RecordState.EXTRACTED,
                                                            RecordState.SYNTHESIZED])
        # Solo record verificati entrano nella wiki (i NEEDS_REVIEW sono esclusi
        # già dallo stato: qui ridondiamo il controllo per sicurezza).
        records = [r for r in records if r.verification and r.verification.verified]
        if not records:
            logger.warning("Sintesi %s: nessun record verificato da sintetizzare.", research.id)
            research.status = ResearchStatus.SYNTHESIZED
            self.db.save_research(research)
            return research

        # Pagine dei singoli paper.
        for rec in records:
            self.wiki.write(self.wiki.paper_path(rec.id), self._paper_page(rec))

        # Stato SYNTHESIZED sui record (prima di costruire la pagina cumulativa).
        for rec in records:
            rec.state = RecordState.SYNTHESIZED
            self.db.upsert_record(rec)

        research.status = ResearchStatus.SYNTHESIZED
        research.stats.update({"synthesized": len(records)})
        self.db.save_research(research)

        # Pagina del topic CUMULATIVA: include gli studi verificati di TUTTE le
        # ricerche sullo stesso slug, così una nuova ricerca non cancella le
        # evidenze precedenti (nessuna sovrascrittura silenziosa).
        cumulative = self._cumulative_records(research.topic)
        page = self._topic_page(research, cumulative)
        self.wiki.write(self.wiki.topic_path(research.topic), page)

        # Indice (dopo l'aggiornamento di stato), deduplicato per slug.
        self._refresh_index()

        rev = self.wiki.commit(f"Sintesi '{research.topic}' — {len(cumulative)} studi (ricerca {research.id})")
        if rev:
            logger.info("Sintesi %s committata (%s)", research.id, rev)
        logger.info("Sintesi %s: %d studi nella wiki", research.id, len(records))
        return research

    # -- Pagina topic ------------------------------------------------------- #
    def _topic_page(self, research: Research, records: List[PaperRecord]) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        findings = self._collect_findings(records)

        out: List[str] = []
        out.append(f"# {research.topic}")
        out.append("")
        out.append(f"> Pagina mantenuta automaticamente. Ultimo aggiornamento: **{now}** · "
                   f"Ricerca `{research.id}` · Studi verificati inclusi: **{len(records)}**.")
        out.append("")
        out.append("Ogni affermazione è collegata ai paper che la sostengono. "
                   "I record non verificati sono esclusi da questa sintesi.")
        out.append("")

        # 1) EVIDENZE (per tema, con citazioni)
        out.append("## Evidenze")
        out.append("")
        conflicts: List[str] = []
        for theme, items in findings.items():
            if not items:
                continue
            out.append(f"### {theme}")
            directions = set()
            for it in items:
                directions.add(it["direction"])
                out.append(
                    f"- {it['snippet']} "
                    f"— [{it['cite']}]({it['link']}) "
                    f"*(disegno: {it['study_type']}; confidenza: {it['confidence']}; "
                    f"popolazione: {it['population']}; fonte dato: {it['based_on']})*"
                )
            # Conflitto: coesistenza di esiti positivi e non-positivi definiti, o
            # presenza di esiti intrinsecamente misti.
            non_positive = directions & {"null", "negative", "mixed"}
            if ("positive" in directions and non_positive) or ("mixed" in directions):
                conflicts.append(theme)
            out.append("")

        if not any(findings.values()):
            out.append("_Nessun outcome quantitativo estraibile dagli studi disponibili "
                       "(spesso solo abstract). Vedere le pagine dei singoli paper._")
            out.append("")

        # 2) RISULTATI CONTRASTANTI (conservati, non appiattiti)
        out.append("## Risultati contrastanti")
        out.append("")
        if conflicts:
            for theme in conflicts:
                out.append(f"- **{theme}**: sono presenti sia evidenze di miglioramento sia "
                           f"risultati nulli/negativi. Le posizioni divergenti sono mantenute "
                           f"entrambe nella sezione Evidenze e non riconciliate d'ufficio.")
        else:
            out.append("_Nessuna contraddizione rilevata fra gli studi attualmente inclusi._")
        out.append("")

        # 3) INTERPRETAZIONE (separata dalle evidenze)
        out.append("## Interpretazione")
        out.append("")
        out.append("> Sintesi derivata dagli studi elencati in *Evidenze* e *Studi inclusi* "
                   "(che riportano i collegamenti ai singoli paper).")
        out.append("")
        out.append(self._interpretation(research, records, findings, conflicts))
        out.append("")

        # 4) APPLICAZIONE PRATICA (ipotesi, non prescrizioni)
        out.append("## Applicazione pratica")
        out.append("")
        out.append("> Indicazioni orientative, da adattare al singolo atleta "
                   "(vedi Athlete Context Agent). Non costituiscono prescrizioni.")
        out.append("")
        for line in self._practical(findings):
            out.append(f"- {line}")
        out.append("")

        # 5) STUDI INCLUSI (tabella)
        out.append("## Studi inclusi")
        out.append("")
        out.append("| Studio | Anno | Disegno | Qualità | Confidenza | Trasferibilità | Fonte dato |")
        out.append("|---|---|---|---|---|---|---|")
        for rec in sorted(records, key=lambda r: (r.year or 0), reverse=True):
            q = rec.quality
            ex = rec.extraction
            out.append(
                f"| [{_cite(rec)}]({_paper_link(rec)}) | {rec.year or '?'} | "
                f"{(q.study_type if q else '?')} | {(q.methodological_quality.value if q else '?')} | "
                f"{(q.confidence_level.value if q else '?')} | "
                f"{(q.transferability_to_competitive_cyclists.value if q else '?')} | "
                f"{(ex.based_on.value if ex else '?')} |"
            )
        out.append("")

        # 6) CRONOLOGIA (append, mai sovrascrittura silenziosa)
        out.append(self._changelog(research, records, now))
        return "\n".join(out)

    def _collect_findings(self, records: List[PaperRecord]) -> Dict[str, List[dict]]:
        findings: Dict[str, List[dict]] = {t: [] for t in OUTCOME_THEMES}
        findings["Altri outcome"] = []
        for rec in records:
            ex = rec.extraction
            snippet = _first_nonempty(ex.results if ex else None, ex.outcomes if ex else None)
            if not snippet:
                continue
            themes = _match_themes(snippet + " " + _val(ex.outcomes if ex else None))
            item = {
                "snippet": _clip(snippet),
                "cite": _cite(rec),
                "link": _paper_link(rec),
                "direction": _direction(snippet),
                "study_type": rec.quality.study_type if rec.quality else "?",
                "confidence": rec.quality.confidence_level.value if rec.quality else "?",
                "population": rec.screening.population_type.value if rec.screening else "?",
                "based_on": ex.based_on.value if ex else "?",
            }
            for theme in themes:
                findings[theme].append(item)
        return findings

    def _interpretation(self, research: Research, records: List[PaperRecord],
                        findings: Dict[str, List[dict]], conflicts: List[str]) -> str:
        if self.llm.available:
            narrative = self._llm_interpretation(research, records)
            if narrative:
                return narrative
        n = len(records)
        high_conf = sum(1 for r in records if r.quality and r.quality.confidence_level.value == "high")
        parts = [
            f"La base attuale include {n} studi verificati "
            f"({high_conf} ad alta confidenza). ",
        ]
        if conflicts:
            parts.append("Su alcuni outcome (" + ", ".join(conflicts) + ") l'evidenza è eterogenea: "
                         "le differenze possono dipendere da protocollo, livello degli atleti e durata. ")
        else:
            parts.append("Le evidenze disponibili sono complessivamente concordi, "
                         "pur con numerosità campionaria spesso limitata. ")
        parts.append("Molti dati provengono da soli abstract: le conclusioni vanno considerate provvisorie "
                     "e riviste all'arrivo di full text e nuovi studi.")
        return "".join(parts)

    def _llm_interpretation(self, research: Research, records: List[PaperRecord]) -> Optional[str]:
        summary = "\n".join(
            f"- {_cite(r)}: {_val(r.extraction.results) if r.extraction else ''} "
            f"[conf: {r.quality.confidence_level.value if r.quality else '?'}]"
            for r in records[:25]
        )
        data = self.llm.complete_json(
            prompt=(
                f"Sintetizza l'interpretazione scientifica per il topic «{research.topic}» "
                "sulla base di questi studi (non prescrittiva, evidenzia incertezze e conflitti):\n"
                f"{summary}\n\n"
                "Restituisci JSON: {\"interpretation\": \"paragrafo\"}."
            )
        )
        if data and data.get("interpretation"):
            return str(data["interpretation"])
        return None

    def _practical(self, findings: Dict[str, List[dict]]) -> List[str]:
        lines = []
        for theme, items in findings.items():
            if not items:
                continue
            pos = sum(1 for i in items if i["direction"] == "positive")
            tot = len(items)
            # Ancora ogni affermazione ai paper conteggiati (link alle pagine).
            cites = ", ".join(f"[{i['cite']}]({i['link']})" for i in items)
            if pos and pos >= tot / 2:
                lines.append(f"**{theme}**: la maggioranza degli studi ({pos}/{tot}) riporta un "
                             f"beneficio; ipotesi applicativa da testare individualmente. "
                             f"Studi: {cites}.")
            else:
                lines.append(f"**{theme}**: evidenza non conclusiva ({pos}/{tot} positivi); "
                             f"evitare generalizzazioni. Studi: {cites}.")
        if not lines:
            lines.append("Dati insufficienti per indicazioni applicative: raccogliere altri studi.")
        return lines

    def _changelog(self, research: Research, records: List[PaperRecord], now: str) -> str:
        existing = self.wiki.read(self.wiki.topic_path(research.topic))
        prior = ""
        m = re.search(r"## Cronologia aggiornamenti\n(.*)$", existing, re.DOTALL)
        if m:
            prior = m.group(1).strip()
        entry = (f"- **{now}** — ricerca `{research.id}`: {len(records)} studi verificati sintetizzati "
                 f"(query: {research.stats.get('queries', '?')}, "
                 f"grezzi: {research.stats.get('raw_results', '?')}).")
        block = "## Cronologia aggiornamenti\n\n" + entry
        if prior:
            block += "\n" + prior
        return block

    # -- Pagina paper ------------------------------------------------------- #
    def _paper_page(self, rec: PaperRecord) -> str:
        ex = rec.extraction
        q = rec.quality
        v = rec.verification
        out = [f"# {rec.title or '(senza titolo)'}", ""]
        out.append(f"- **Autori**: {', '.join(rec.authors) if rec.authors else 'n/d'}")
        out.append(f"- **Anno**: {rec.year or 'n/d'} · **Rivista**: {rec.journal or 'n/d'}")
        out.append(f"- **DOI**: {rec.doi or 'n/d'} · **PMID**: {rec.pmid or 'n/d'}")
        out.append(f"- **Provenienza banche dati**: {', '.join(rec.source_dbs)}")
        out.append(f"- **Scoperto via**: {rec.discovered_via or 'n/d'}")
        if rec.oa_url:
            out.append(f"- **Open access**: [{rec.oa_status or 'oa'}]({rec.oa_url})")
        out.append("")

        if v:
            status = "✔ verificato" if v.verified else "⚠ da rivedere"
            out.append(f"**Verifica metadati**: {status}")
            if v.inconsistencies:
                out.append("")
                for inc in v.inconsistencies:
                    out.append(f"  - ⚠ {inc}")
            out.append("")

        if q:
            out.append("## Qualità metodologica")
            out.append(f"- Tipo di studio: **{q.study_type}**")
            out.append(f"- Qualità: **{q.methodological_quality.value}** · "
                       f"Confidenza: **{q.confidence_level.value}** · "
                       f"Trasferibilità ciclisti competitivi: **{q.transferability_to_competitive_cyclists.value}**")
            for k, val in q.dimensions.items():
                out.append(f"  - {k}: {val}")
            for note in q.notes:
                out.append(f"  - _{note}_")
            out.append("")

        if ex:
            out.append(f"## Dati estratti (fonte: {ex.based_on.value}, metodo: {ex.extracted_by})")
            for label, f in _extraction_rows(ex):
                if f.value not in (None, "", []):
                    src = f"`{f.source.value}`"
                    out.append(f"- **{label}** ({src}): {f.value}")
                else:
                    out.append(f"- **{label}**: _non disponibile_")
            out.append("")

        if rec.abstract:
            out.append("## Abstract")
            out.append(rec.abstract)
            out.append("")
        return "\n".join(out)

    def _cumulative_records(self, topic: str) -> List[PaperRecord]:
        """Tutti i record verificati+sintetizzati di ogni ricerca con lo stesso slug,
        deduplicati fra loro (una nuova ricerca accumula, non sostituisce)."""
        slug = slugify(topic)
        collected: List[PaperRecord] = []
        for research in self.db.list_researches():
            if slugify(research.topic) != slug:
                continue
            recs = self.db.list_records(research.id, states=[RecordState.SYNTHESIZED,
                                                            RecordState.EXTRACTED])
            collected.extend(r for r in recs if r.verification and r.verification.verified)
        return deduplicate(collected)

    def _refresh_index(self) -> None:
        # Deduplica per slug: ricerche diverse sullo stesso topic → una sola voce,
        # con il conteggio degli studi unici cumulativi e la data più recente.
        by_slug: Dict[str, dict] = {}
        for research in self.db.list_researches():
            slug = slugify(research.topic)
            n = self.db.count_by_state(research.id).get(RecordState.SYNTHESIZED.value, 0)
            if not n:
                continue
            unique = len(self._cumulative_records(research.topic))
            updated = (research.updated_at or "")[:10]
            entry = by_slug.get(slug)
            if entry is None or updated >= entry["updated"]:
                by_slug[slug] = {"topic": research.topic, "n_studies": unique, "updated": updated}
        update_index(self.wiki, list(by_slug.values()))


# --------------------------------------------------------------------------- #
# Funzioni pure di supporto
# --------------------------------------------------------------------------- #
def _cite(rec: PaperRecord) -> str:
    first = "Anon"
    if rec.authors:
        parts = rec.authors[0].split(",")[0].split()
        if parts:
            first = parts[0]
    return f"{first} {rec.year or 's.d.'}"


def _paper_link(rec: PaperRecord) -> str:
    return f"../papers/{rec.id}.md"


def _val(f: Optional[ExtractedField]) -> str:
    if f and f.value not in (None, "", []):
        return str(f.value)
    return ""


def _first_nonempty(*fields) -> Optional[str]:
    for f in fields:
        v = _val(f)
        if v:
            return v
    return None


def _match_themes(text: str) -> List[str]:
    low = (text or "").lower()
    matched = [theme for theme, kws in OUTCOME_THEMES.items() if any(k in low for k in kws)]
    return matched or ["Altri outcome"]


def _direction(text: str) -> str:
    low = (text or "").lower()
    has_pos = any(k in low for k in POSITIVE)
    has_null = any(k in low for k in NULL)
    has_neg = any(k in low for k in NEGATIVE)
    # "no significant increase" ecc.: la negazione ha precedenza sul positivo.
    if has_null and has_pos:
        return "mixed"
    if has_pos and has_neg:
        return "mixed"
    if has_pos:
        return "positive"
    if has_neg:
        return "negative"
    if has_null:
        return "null"
    return "unclear"


def _clip(text: str, n: int = 300) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _extraction_rows(ex):
    return [
        ("Disegno dello studio", ex.study_design),
        ("Partecipanti", ex.participants),
        ("Livello di allenamento", ex.training_level),
        ("Sesso", ex.sex),
        ("Età", ex.age),
        ("Numerosità campione", ex.sample_size),
        ("Protocollo", ex.protocol),
        ("Comparatore", ex.comparator),
        ("Durata", ex.duration),
        ("Outcome", ex.outcomes),
        ("Risultati", ex.results),
        ("Effect size", ex.effect_size),
        ("Limiti", ex.limitations),
        ("Conflitti di interesse", ex.conflicts_of_interest),
    ]
