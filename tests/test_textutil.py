"""Test delle utility testuali critiche per dedup e verifica."""

from cyclist_kb.textutil import first_author_key, normalize_title, title_signature


def test_first_author_key_is_format_agnostic():
    # Stesso autore, tre formati di fonti diverse → stessa chiave.
    assert first_author_key(["Guenette JA"]) == "guenette"                 # PubMed
    assert first_author_key(["Jordan A. Guenette"]) == "guenette"          # OpenAlex/S2
    assert first_author_key(["Guenette Jordan A."]) == "guenette"          # Crossref normalizzato
    assert first_author_key(["Guenette, Jordan"]) == "guenette"            # "Cognome, Nome"


def test_first_author_key_edge_cases():
    assert first_author_key([]) == ""
    assert first_author_key(["Rossi M"]) == "rossi"
    assert first_author_key(["Rossi Mario"]) == "rossi"  # parità → primo token


def test_first_author_key_punctuation_only_does_not_crash():
    # Nome di sola punteggiatura/spazi: niente ValueError da max() su sequenza vuota.
    assert first_author_key([". ."]) == ""
    assert first_author_key(["..."]) == ""
    assert first_author_key(["   "]) == ""


def test_normalize_title_strips_punctuation_and_accents():
    assert normalize_title("High-Intensity Interval Training.") == "high intensity interval training"
    assert normalize_title("VO₂max é importante") == normalize_title("VO₂max e importante")


def test_title_signature_combines_fields():
    sig = title_signature("A Study", 2020, ["Smith J"])
    assert sig == "a study|2020|smith"
