"""Deduplication Layer.

Deduplica i record in tre passaggi gerarchici:
  1. per DOI normalizzato;
  2. per PMID;
  3. per firma "titolo normalizzato + anno + primo autore" (con fallback fuzzy).

Ogni cluster conserva l'unione di **tutte** le banche dati di provenienza e dei
payload grezzi indicizzati per fonte. Funzione pura e deterministica: non muta
gli input e non tocca la rete → interamente testabile a unità.
"""

from __future__ import annotations

from typing import List, Optional

from .models import PaperRecord
from .textutil import first_author_key, normalize_title, similarity, title_signature

FUZZY_TITLE_THRESHOLD = 0.90


def deduplicate(records: List[PaperRecord]) -> List[PaperRecord]:
    """Restituisce la lista deduplicata di record, preservandone la provenienza."""
    clusters: List[PaperRecord] = []
    doi_index: dict = {}
    pmid_index: dict = {}
    sig_index: dict = {}

    for rec in records:
        ndoi = rec.normalized_doi()
        pmid = (rec.pmid or "").strip() or None
        sig = title_signature(rec.title, rec.year, rec.authors)
        ntitle = normalize_title(rec.title)

        idx: Optional[int] = None
        if ndoi and ndoi in doi_index:                       # 1. DOI
            idx = doi_index[ndoi]
        elif pmid and pmid in pmid_index:                    # 2. PMID
            idx = pmid_index[pmid]
        elif ntitle and sig in sig_index:                    # 3. firma esatta
            idx = sig_index[sig]
        elif ntitle:                                         # 3b. fuzzy sul titolo
            idx = _find_fuzzy(clusters, rec)

        # Guard gerarchico: non fondere a uno stadio debole (PMID/firma/fuzzy) due
        # lavori i cui identificatori FORTI sono in conflitto. Il DOI è
        # l'identificatore più forte: DOI diversi ⇒ lavori distinti.
        if idx is not None and _strong_conflict(rec, clusters[idx]):
            idx = None

        if idx is None:
            clusters.append(rec.model_copy(deep=True))
            idx = len(clusters) - 1
        else:
            _merge_into(clusters[idx], rec)

        # Aggiorna gli indici sia con gli identificatori del record in ingresso
        # sia con quelli (eventualmente arricchiti) del cluster risultante.
        cluster = clusters[idx]
        for d in (ndoi, cluster.normalized_doi()):
            if d:
                doi_index[d] = idx
        for p in (pmid, (cluster.pmid or "").strip() or None):
            if p:
                pmid_index[p] = idx
        # Indicizza le firme solo quando il titolo è presente (evita di
        # collassare fra loro record privi di titolo).
        for title, year, authors in ((rec.title, rec.year, rec.authors),
                                     (cluster.title, cluster.year, cluster.authors)):
            if normalize_title(title):
                sig_index[title_signature(title, year, authors)] = idx

    return clusters


def _strong_conflict(rec: PaperRecord, cluster: PaperRecord) -> bool:
    """True se rec e cluster hanno identificatori forti (DOI o PMID) in conflitto."""
    rd, cd = rec.normalized_doi(), cluster.normalized_doi()
    if rd and cd and rd != cd:
        return True
    rp = (rec.pmid or "").strip()
    cp = (cluster.pmid or "").strip()
    if rp and cp and rp != cp:
        return True
    return False


def _find_fuzzy(clusters: List[PaperRecord], rec: PaperRecord) -> Optional[int]:
    """Trova un cluster con stesso primo autore/anno e titolo molto simile."""
    ntitle = normalize_title(rec.title)
    fkey = first_author_key(rec.authors)
    for i, c in enumerate(clusters):
        if _strong_conflict(rec, c):  # DOI/PMID discordanti ⇒ non è lo stesso lavoro
            continue
        if c.year and rec.year and abs(c.year - rec.year) > 1:  # tolleranza online/print (v. verification.py)
            continue
        if fkey and first_author_key(c.authors) and fkey != first_author_key(c.authors):
            continue
        if similarity(ntitle, normalize_title(c.title)) >= FUZZY_TITLE_THRESHOLD:
            return i
    return None


def _merge_into(target: PaperRecord, incoming: PaperRecord) -> None:
    """Fonde `incoming` in `target` senza perdere provenienza né dati più ricchi."""
    # Provenienza: unione ordinata delle banche dati.
    for db in incoming.source_dbs:
        if db not in target.source_dbs:
            target.source_dbs.append(db)

    # Identificatori e metadati: riempi i buchi.
    if not target.doi and incoming.doi:
        target.doi = incoming.doi
    if not target.pmid and incoming.pmid:
        target.pmid = incoming.pmid
    if not target.title and incoming.title:
        target.title = incoming.title
    if not target.year and incoming.year:
        target.year = incoming.year
    if not target.journal and incoming.journal:
        target.journal = incoming.journal
    if not target.url and incoming.url:
        target.url = incoming.url
    if not target.oa_url and incoming.oa_url:
        target.oa_url = incoming.oa_url
    if not target.oa_status and incoming.oa_status:
        target.oa_status = incoming.oa_status

    # Abstract: preferisci quello più completo (più lungo).
    if incoming.abstract and len(incoming.abstract) > len(target.abstract or ""):
        target.abstract = incoming.abstract

    # Autori: preferisci la lista più ricca.
    if len(incoming.authors) > len(target.authors):
        target.authors = list(incoming.authors)

    # Referenze (citation chasing): unione.
    for ref in incoming.references:
        if ref not in target.references:
            target.references.append(ref)

    # Payload grezzi indicizzati per fonte.
    target.raw.update(incoming.raw)

    target.seed_for_chasing = target.seed_for_chasing or incoming.seed_for_chasing
