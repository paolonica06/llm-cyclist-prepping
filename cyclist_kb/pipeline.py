"""Orchestrazione della pipeline.

Ogni fase è eseguibile singolarmente (create → search → screen → verify →
extract → quality → synthesize → athlete) oppure tutte insieme con `run`.
Le fasi che toccano la rete (search, verify, extract) sono asincrone.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .agents import (AthleteContextAgent, ExtractionAgent, QualityAgent,
                     ResearchAgent, ScreeningAgent, SynthesisAgent,
                     VerificationAgent)
from .agents.athlete import load_profile
from .config import get_settings
from .db import Database
from .models import Research
from .wiki import slugify

logger = logging.getLogger("cyclist_kb.pipeline")


class ResearchNotFound(Exception):
    pass


class Pipeline:
    def __init__(self, db: Optional[Database] = None) -> None:
        self.settings = get_settings()
        self.db = db or Database()

    # -- Utilità ------------------------------------------------------------ #
    def _get(self, research_id: str) -> Research:
        r = self.db.get_research(research_id)
        if r is None:
            raise ResearchNotFound(f"Ricerca '{research_id}' inesistente.")
        return r

    @staticmethod
    def _new_id(topic: str) -> str:
        ts = datetime.now(timezone.utc).isoformat()
        h = hashlib.sha1(f"{topic}:{ts}".encode("utf-8")).hexdigest()[:6]
        return f"{slugify(topic)[:32]}-{h}"

    # -- Fasi --------------------------------------------------------------- #
    def create(self, topic: str) -> Research:
        research = Research(id=self._new_id(topic), topic=topic)
        self.db.create_research(research)
        logger.info("Creata ricerca %s per «%s»", research.id, topic)
        return research

    async def search(self, research_id: str) -> Research:
        return await ResearchAgent(self.db).run(self._get(research_id))

    def screen(self, research_id: str) -> Research:
        return ScreeningAgent(self.db).run(self._get(research_id))

    async def verify(self, research_id: str) -> Research:
        return await VerificationAgent(self.db).run(self._get(research_id))

    async def extract(self, research_id: str) -> Research:
        return await ExtractionAgent(self.db).run(self._get(research_id))

    def quality(self, research_id: str) -> Research:
        return QualityAgent(self.db).run(self._get(research_id))

    def synthesize(self, research_id: str) -> Research:
        return SynthesisAgent(self.db).run(self._get(research_id))

    def athlete(self, research_id: str, profile_path: Path) -> Path:
        profile = load_profile(Path(profile_path))
        return AthleteContextAgent(self.db).run(self._get(research_id), profile)

    # -- Fase B: ingestione atleta (separata dalla pipeline paper) ---------- #
    async def sync_athlete(self, athlete_id: str, oldest: Optional[str] = None,
                           newest: Optional[str] = None) -> dict:
        """Morning sync da intervals.icu (no-op pulito se key assente/offline)."""
        from .agents.athlete_sync import AthleteSyncAgent
        return await AthleteSyncAgent(self.db).run(athlete_id, oldest=oldest, newest=newest)

    # -- Pipeline completa -------------------------------------------------- #
    async def run(self, topic: str, profile_path: Optional[Path] = None) -> Research:
        research = self.create(topic)
        rid = research.id
        await self.search(rid)
        self.screen(rid)
        await self.verify(rid)
        await self.extract(rid)
        self.quality(rid)
        self.synthesize(rid)
        if profile_path:
            self.athlete(rid, Path(profile_path))
        research = self._get(rid)
        logger.info("Pipeline completata per %s: %s", rid, research.stats)
        return research
