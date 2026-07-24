"""Demo end-to-end sul tema «interval training and VO2max in trained competitive cyclists».

Esegue l'intera pipeline (search → screen → verify → extract → quality →
synthesize) e la contestualizzazione sul profilo atleta di esempio, poi stampa un
riepilogo e la posizione della wiki generata.

Uso:
    python scripts/demo.py            # live (interroga le API reali)
    python scripts/demo.py --topic "..."   # topic alternativo
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cyclist_kb.config import get_settings
from cyclist_kb.db import Database
from cyclist_kb.models import RecordState
from cyclist_kb.pipeline import Pipeline

DEMO_TOPIC = "interval training and VO2max in trained competitive cyclists"
PROFILE = Path(__file__).resolve().parent.parent / "profiles" / "example_athlete.yaml"


async def main(topic: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    print(f"LLM disponibile: {bool(settings.anthropic_api_key) and not settings.force_offline} "
          f"(altrimenti euristiche offline)")
    print(f"Contatto API: {settings.contact_email}\n")

    pipe = Pipeline()
    research = await pipe.run(topic, PROFILE if PROFILE.exists() else None)

    db = Database()
    counts = db.count_by_state(research.id)
    print("\n==================== RIEPILOGO ====================")
    print(f"Ricerca: {research.id}")
    print(f"Topic:   {research.topic}")
    print("Statistiche:")
    for k, v in research.stats.items():
        print(f"  - {k}: {v}")
    print("Record per stato:")
    for state in RecordState:
        n = counts.get(state.value, 0)
        if n:
            print(f"  - {state.value}: {n}")
    print("\nWiki generata in:", settings.wiki_dir)
    topic_page = settings.wiki_dir / "topics"
    for p in sorted(topic_page.glob("*.md")):
        print("  -", p)
    print("==================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default=DEMO_TOPIC)
    args = parser.parse_args()
    asyncio.run(main(args.topic))
