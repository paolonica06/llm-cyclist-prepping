"""Test comportamentali del lint della wiki Markdown/Obsidian."""

from pathlib import Path
import subprocess
import sys

from cyclist_kb.wiki_lint import lint_wiki


REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_SCRIPT = REPO_ROOT / "scripts" / "lint_wiki.py"


def _write(wiki: Path, relative: str, text: str) -> Path:
    path = wiki / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _codes(wiki: Path):
    return {issue.code for issue in lint_wiki(wiki)}


def test_cli_reports_missing_relative_link(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "index.md").write_text(
        "# Index\n\n- [Topic mancante](topics/missing.md)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), "--root", str(wiki)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert result.returncode == 1, result.stderr
    assert "index.md:3: WIKI001" in result.stderr


def test_reports_unresolved_wikilink(tmp_path):
    wiki = tmp_path / "wiki"
    _write(wiki, "index.md", "# Index\n\n[[Nota mancante]]\n")

    assert "WIKI002" in _codes(wiki)


def test_reports_mismatched_manual_marker(tmp_path):
    wiki = tmp_path / "wiki"
    _write(
        wiki,
        "index.md",
        "# Index\n\n"
        "<!-- BEGIN MANUAL: curated -->\n"
        "testo\n"
        "<!-- END MANUAL: altro -->\n",
    )

    assert "WIKI003" in _codes(wiki)


def test_reports_duplicate_index_target(tmp_path):
    wiki = tmp_path / "wiki"
    _write(wiki, "topics/topic.md", "# Topic\n")
    _write(
        wiki,
        "index.md",
        "# Index\n\n"
        "- [Topic](topics/topic.md)\n"
        "- [Topic duplicato](topics/topic.md)\n",
    )

    assert "WIKI004" in _codes(wiki)


def test_reports_noncanonical_doi_and_malformed_pubmed_url(tmp_path):
    wiki = tmp_path / "wiki"
    _write(
        wiki,
        "index.md",
        "# Index\n\n"
        "- [DOI](http://doi.org/10.1234/example)\n"
        "- [PMID](https://pubmed.ncbi.nlm.nih.gov/not-a-number/)\n",
    )

    assert "WIKI005" in _codes(wiki)


def test_reports_unlabelled_curated_recommendation(tmp_path):
    wiki = tmp_path / "wiki"
    _write(
        wiki,
        "topics/curated.md",
        "# Curated\n\n"
        "> Corpus curato manualmente il **2026-07-27**.\n\n"
        "## Applicazione prudente\n\n"
        "1. Provare la strategia in allenamento.\n",
    )

    assert "WIKI006" in _codes(wiki)


def test_reports_private_identifier_and_secret_prefix(tmp_path):
    wiki = tmp_path / "wiki"
    _write(
        wiki,
        "index.md",
        "# Index\n\n"
        "athlete_id=i215294\n"
        "token=sk-ant-test-only\n",
    )

    assert "WIKI007" in _codes(wiki)


def test_reports_inconsistent_table_columns(tmp_path):
    wiki = tmp_path / "wiki"
    _write(
        wiki,
        "index.md",
        "# Index\n\n"
        "| A | B |\n"
        "|---|---|\n"
        "| uno |\n",
    )

    assert "WIKI008" in _codes(wiki)


def test_reports_heading_level_jump(tmp_path):
    wiki = tmp_path / "wiki"
    _write(wiki, "index.md", "# Index\n\n### Salto\n")

    assert "WIKI009" in _codes(wiki)


def test_reports_curated_whitespace_but_ignores_generated_paper_whitespace(tmp_path):
    wiki = tmp_path / "wiki"
    _write(wiki, "topics/topic.md", "# Topic \n")
    _write(wiki, "papers/paper.md", "# Paper \n")

    issues = lint_wiki(wiki)

    assert any(issue.code == "WIKI010" and issue.path.name == "topic.md" for issue in issues)
    assert not any(issue.code == "WIKI010" and issue.path.name == "paper.md" for issue in issues)


def test_repository_wiki_passes_lint():
    issues = lint_wiki(REPO_ROOT / "wiki")

    assert issues == [], "\n".join(issue.format(REPO_ROOT) for issue in issues)
