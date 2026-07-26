"""Morning sync: ingestione idempotente dei dati atleta da intervals.icu.

Separato dalla pipeline dei paper: produce Serie storiche e Attività, non
`PaperRecord`. È idempotente (upsert su chiavi deterministiche). Se il client
non è disponibile (no key / offline) è un **no-op pulito**, senza eccezioni.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from ..clients.intervals_icu import IntervalsClient
from ..db import Database

logger = logging.getLogger("cyclist_kb.athlete_sync")


class AthleteSyncAgent:
    def __init__(self, db: Database, client: Optional[IntervalsClient] = None) -> None:
        self.db = db
        self.intervals = client or IntervalsClient()

    async def run(self, athlete_id: str, oldest: Optional[str] = None,
                  newest: Optional[str] = None) -> Dict[str, object]:
        daily = await self.intervals.fetch_daily(athlete_id, oldest=oldest, newest=newest)
        for point in daily:
            self.db.add_timeseries_point(point)

        activities = await self.intervals.fetch_activities(athlete_id, oldest=oldest, newest=newest)
        for activity in activities:
            self.db.save_activity(activity)

        # Curva di potenza mean-max, ingerita già calcolata (ramo mirror, ADR-0001).
        # Stessa tabella serie: chiave (atleta, power_curve, data) → upsert idempotente.
        power_curve = await self.intervals.fetch_power_curve(athlete_id)
        for point in power_curve:
            self.db.add_timeseries_point(point)

        summary: Dict[str, object] = {
            "athlete_id": athlete_id,
            "available": self.intervals.available,
            "timeseries_points": len(daily),
            "activities": len(activities),
            "power_curve_points": len(power_curve),
        }
        logger.info("Morning sync %s: %s", athlete_id, summary)
        return summary
