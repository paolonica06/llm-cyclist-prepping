"""Regressioni: le rigenerazioni non cancellano i blocchi curati manualmente."""

from cyclist_kb.agents.synthesis import SynthesisAgent
from cyclist_kb.db import Database
from cyclist_kb.models import Research
from cyclist_kb.wiki import Wiki, update_index


def test_update_index_preserves_curated_preamble_and_topic_entries(tmp_path):
    wiki = Wiki()
    wiki.root = tmp_path / "wiki"
    wiki.root.mkdir()
    existing = """# Knowledge base — Allenamento ciclistico

<!-- BEGIN MANUAL: index-preamble -->
## Governance

- [Safeguards](Safeguards.md)
<!-- END MANUAL: index-preamble -->

## Argomenti
<!-- BEGIN MANUAL: index-topics -->
- [Curated topic](topics/curated-topic.md) — sintesi manuale
<!-- END MANUAL: index-topics -->
"""
    wiki.write(wiki.root / "index.md", existing)

    update_index(
        wiki,
        [{"topic": "Generated topic", "n_studies": 3, "updated": "2026-07-27"}],
    )

    rendered = wiki.read(wiki.root / "index.md")
    assert "## Governance\n\n- [Safeguards](Safeguards.md)" in rendered
    assert "- [Curated topic](topics/curated-topic.md) — sintesi manuale" in rendered
    assert "- [Generated topic](topics/generated-topic.md) — 3 studi sintetizzati" in rendered
    assert rendered.index("## Governance") < rendered.index("## Argomenti")
    assert rendered.index("Curated topic") < rendered.index("Generated topic")


def test_topic_regeneration_preserves_curated_block_before_changelog(tmp_path):
    agent = SynthesisAgent(Database(path=tmp_path / "kb.sqlite3"))
    agent.wiki.root = tmp_path / "wiki"
    (agent.wiki.root / "topics").mkdir(parents=True)
    topic = "Concurrent strength"
    manual = """<!-- BEGIN MANUAL: topic-heavy-strength-2026 -->
## Integrazione manuale

Risultati favorevoli e nulli verificati.
<!-- END MANUAL: topic-heavy-strength-2026 -->"""
    agent.wiki.write(
        agent.wiki.topic_path(topic),
        f"# Vecchia pagina\n\n{manual}\n\n## Cronologia aggiornamenti\n\n- voce precedente",
    )

    rendered = agent._topic_page(Research(id="r1", topic=topic), [])

    assert manual in rendered
    assert rendered.index(manual) < rendered.index("## Cronologia aggiornamenti")
    assert "- voce precedente" in rendered
