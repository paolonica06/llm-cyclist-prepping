"""Test delle logiche euristiche degli agenti (screening, quality, synthesis, extraction)."""

from cyclist_kb.agents.extraction import (MAX_PDF_BYTES, _coerce_int, _decode_source,
                                          _detect_design, _pdf_to_text)
from cyclist_kb.agents.screening import ScreeningAgent
from cyclist_kb.agents.synthesis import _direction
from cyclist_kb.db import Database
from cyclist_kb.domain import best_design
from cyclist_kb.models import PaperRecord, PopulationType, make_record_id


def _minimal_pdf_bytes(text: str) -> bytes:
    """Costruisce un PDF valido a una pagina con xref corretto (offset calcolati)."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 300 300] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 18 Tf 10 250 Td ({text}) Tj ET".encode("latin-1")
    objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    body = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(body)
    n = len(objects) + 1
    xref = f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    body += xref + f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return bytes(body)


def _rec(title, abstract):
    return PaperRecord(
        id=make_record_id("r1", title=title), research_id="r1",
        title=title, abstract=abstract,
    )


def _screen(tmp_path, title, abstract, topic="interval training and VO2max in cyclists"):
    agent = ScreeningAgent(Database(path=tmp_path / "kb.sqlite3"))
    return agent._heuristic_screen(_rec(title, abstract), topic)


def test_screening_excludes_non_cycling_mixed(tmp_path):
    # runners + sedentary, nessun ciclista → non deve essere incluso come MIXED.
    r = _screen(tmp_path, "HIIT in runners and sedentary patients",
                "This trial studied runners and sedentary patients performing interval training and VO2max.")
    assert r.population_type in (PopulationType.ENDURANCE_OTHER, PopulationType.UNTRAINED)
    assert r.decision == "exclude"


def test_screening_excludes_out_of_domain(tmp_path):
    # "cycling" fuori dominio (batterie): nessun contesto di esercizio → escluso.
    r = _screen(tmp_path, "Long-term cycling stability of TB-COF electrodes",
                "The battery shows stable cycling with capacity decay per cycle over 10000 cycles.")
    assert r.decision == "exclude"


def test_screening_includes_trained_cyclists(tmp_path):
    r = _screen(tmp_path, "Interval training improves VO2max in trained competitive cyclists",
                "Twelve well-trained cyclists completed interval training; VO2max and power output increased.")
    assert r.is_cycling is True
    assert r.decision == "include"


def test_best_design_picks_highest_rank():
    # Testo che menziona sia 'review' sia RCT: deve vincere l'RCT (rank più alto).
    text = "this randomized controlled trial is discussed in a narrative review of cyclists"
    assert best_design(text) == "randomized controlled trial"
    assert _detect_design(text) == "randomized controlled trial"
    assert best_design("no design markers here") is None


def test_direction_classification():
    assert _direction("VO2max increased significantly") == "positive"
    assert _direction("there was no significant difference between groups") == "null"
    assert _direction("performance decreased after the block") == "negative"
    # coesistenza di segnale positivo e nullo → misto (conflitto conservato)
    assert _direction("VO2max increased but no significant change in power output") == "mixed"


def test_coerce_int_uniforms_sample_size():
    assert _coerce_int(12) == 12
    assert _coerce_int("12") == 12
    assert _coerce_int("n = 12 cyclists") == 12
    assert _coerce_int(None) is None
    assert _coerce_int("many") is None
    assert _coerce_int(True) is None


def test_pdf_to_text_extracts_content():
    raw = _minimal_pdf_bytes("Hello cyclist durability")
    text = _pdf_to_text(raw)
    assert text is not None
    assert "Hello cyclist durability" in text


def test_pdf_to_text_returns_none_on_garbage():
    assert _pdf_to_text(b"%PDF-1.4\nnot a real pdf body") is None


def test_decode_source_dispatches_on_magic_bytes_not_extension():
    # Un URL OA senza suffisso .pdf può comunque servire un PDF: il riconoscimento
    # deve basarsi sui byte, non sull'estensione (che extraction.py non guarda più).
    raw = _minimal_pdf_bytes("Threshold training review")
    text = _decode_source(raw)
    assert text is not None
    assert "Threshold training review" in text


def test_decode_source_strips_html():
    html = b"<html><body><script>evil()</script><p>Findings on VO2max</p></body></html>"
    text = _decode_source(html)
    assert text == "Findings on VO2max"


def test_decode_source_plain_text_passthrough():
    assert _decode_source(b"Plain abstract text about cyclists") == "Plain abstract text about cyclists"


def test_decode_source_rejects_oversized_payload():
    assert _decode_source(b"x" * (MAX_PDF_BYTES + 1)) is None


def test_decode_source_none_on_empty():
    assert _decode_source(None) is None
    assert _decode_source(b"") is None


def test_screening_excludes_clinical_nonathlete_population(tmp_path):
    r = _screen(tmp_path, "Exercise capacity and iron status across pregnancy",
                "Pregnant women completed submaximal exercise testing across gestation; "
                "aerobic fitness and heart rate were monitored throughout pregnancy and "
                "postpartum follow-up.",
                topic="iron status and exercise capacity in pregnant women")
    assert r.decision == "exclude"
    assert "clinica non atletica" in r.reason


def test_screening_keeps_athletes_with_clinical_condition(tmp_path):
    # Atleti CON una condizione clinica restano dentro perimetro: il segnale
    # ciclistico/allenato prevale sul marcatore clinico.
    r = _screen(tmp_path, "Training load management in competitive cyclists with type 2 diabetes",
                "Twelve well-trained competitive cyclists with type 2 diabetes completed "
                "a structured training block; power output and glycaemic control were "
                "monitored throughout.")
    assert r.decision == "include"
