"""Test del Deduplication Layer: DOI → PMID → firma titolo/anno/autore + provenienza."""

from cyclist_kb.dedup import deduplicate
from cyclist_kb.models import PaperRecord, make_record_id


def make(source, doi=None, pmid=None, title=None, year=None, authors=None,
         abstract=None, research_id="r1", **extra) -> PaperRecord:
    return PaperRecord(
        id=make_record_id(research_id, doi=doi, pmid=pmid, title=title),
        research_id=research_id,
        doi=doi, pmid=pmid, title=title, year=year,
        authors=authors or [], abstract=abstract,
        source_dbs=[source], raw={source: {}}, **extra,
    )


def test_dedup_by_doi_merges_and_preserves_provenance():
    recs = [
        make("pubmed", doi="10.1000/abc", pmid="111", title="Interval training in cyclists", year=2020),
        make("openalex", doi="https://doi.org/10.1000/ABC", title="Interval training in cyclists", year=2020),
        make("crossref", doi="10.1000/abc", title="Interval training in cyclists", year=2020),
    ]
    out = deduplicate(recs)
    assert len(out) == 1
    merged = out[0]
    # Provenienza: tutte e tre le banche dati conservate.
    assert set(merged.source_dbs) == {"pubmed", "openalex", "crossref"}
    # Il PMID presente in una sola fonte viene ereditato.
    assert merged.pmid == "111"


def test_dedup_by_pmid_when_doi_absent():
    recs = [
        make("pubmed", pmid="222", title="HIIT and VO2max", year=2019),
        make("semantic_scholar", pmid="222", title="HIIT and VO2 max", year=2019),
    ]
    out = deduplicate(recs)
    assert len(out) == 1
    assert set(out[0].source_dbs) == {"pubmed", "semantic_scholar"}


def test_dedup_by_title_year_author_signature():
    # Nessun DOI/PMID condiviso: si deduplica sulla firma titolo+anno+primo autore.
    recs = [
        make("openalex", title="High-Intensity Interval Training and VO2max", year=2021,
             authors=["Rossi M", "Bianchi L"]),
        make("crossref", title="High-intensity interval training and VO2max.", year=2021,
             authors=["Rossi Mario"]),
    ]
    out = deduplicate(recs)
    assert len(out) == 1
    assert set(out[0].source_dbs) == {"openalex", "crossref"}


def test_distinct_papers_not_merged():
    recs = [
        make("pubmed", doi="10.1/x", title="Study A", year=2018, authors=["Smith J"]),
        make("pubmed", doi="10.1/y", title="Completely different study B", year=2018, authors=["Jones K"]),
    ]
    out = deduplicate(recs)
    assert len(out) == 2


def test_merge_keeps_richer_fields():
    short = make("crossref", doi="10.5/z", title="T", year=2020, abstract="short",
                 authors=["A"])
    rich = make("openalex", doi="10.5/z", title="T", year=2020,
                abstract="a much longer and more complete abstract with details",
                authors=["A B", "C D", "E F"])
    out = deduplicate([short, rich])
    assert len(out) == 1
    assert "much longer" in out[0].abstract
    assert len(out[0].authors) == 3  # lista autori più ricca preservata


def test_transitive_merge_via_shared_identifiers():
    # A: DOI+titolo ; B: solo titolo (uguale) ; C: solo DOI (uguale ad A).
    a = make("pubmed", doi="10.9/t", title="Threshold power in trained cyclists", year=2022)
    b = make("openalex", title="Threshold power in trained cyclists", year=2022)
    c = make("crossref", doi="https://doi.org/10.9/T")
    out = deduplicate([a, b, c])
    assert len(out) == 1
    assert set(out[0].source_dbs) == {"pubmed", "openalex", "crossref"}


def test_conflicting_dois_not_merged_via_pmid():
    # Stesso PMID ma DOI DIVERSI ⇒ lavori distinti: non fondere (guard gerarchico).
    recs = [
        make("pubmed", doi="10.1/aaa", pmid="999", title="Study X", year=2020),
        make("openalex", doi="10.1/bbb", pmid="999", title="Study X", year=2020),
    ]
    out = deduplicate(recs)
    assert len(out) == 2


def test_conflicting_dois_not_merged_via_signature():
    recs = [
        make("openalex", doi="10.1/aaa", title="Identical Title", year=2021, authors=["Rossi M"]),
        make("crossref", doi="10.1/bbb", title="Identical Title", year=2021, authors=["Rossi M"]),
    ]
    out = deduplicate(recs)
    assert len(out) == 2


def test_conflicting_pmids_not_merged_via_signature():
    # PMID diversi senza DOI, stessa firma ⇒ distinti.
    recs = [
        make("pubmed", pmid="111", title="Same Title", year=2019, authors=["Neri P"]),
        make("semantic_scholar", pmid="222", title="Same Title", year=2019, authors=["Neri P"]),
    ]
    out = deduplicate(recs)
    assert len(out) == 2


def test_doi_normalization_variants_collapse():
    recs = [
        make("crossref", doi="10.1234/AbC.def"),
        make("openalex", doi="https://doi.org/10.1234/abc.def"),
        make("pubmed", doi="doi:10.1234/abc.DEF"),
    ]
    out = deduplicate(recs)
    assert len(out) == 1
    assert set(out[0].source_dbs) == {"crossref", "openalex", "pubmed"}


def test_fuzzy_merge_tolerates_one_year_drift():
    # Stesso lavoro indicizzato con epub 2020 da una fonte e print 2021 dall'altra
    # (nessun DOI/PMID condiviso): la firma fuzzy deve tollerare ±1 anno, come già
    # fa verification.py per la discrepanza online/print.
    recs = [
        make("openalex", title="Threshold training and durability in cyclists", year=2020,
             authors=["Verdi G"]),
        make("crossref", title="Threshold training and durability in cyclists", year=2021,
             authors=["Verdi G"]),
    ]
    out = deduplicate(recs)
    assert len(out) == 1
    assert set(out[0].source_dbs) == {"openalex", "crossref"}


def test_fuzzy_merge_rejects_two_year_drift():
    # Oltre la tolleranza di ±1 anno restano trattati come lavori distinti.
    recs = [
        make("openalex", title="Threshold training and durability in cyclists", year=2018,
             authors=["Verdi G"]),
        make("crossref", title="Threshold training and durability in cyclists", year=2021,
             authors=["Verdi G"]),
    ]
    out = deduplicate(recs)
    assert len(out) == 2
