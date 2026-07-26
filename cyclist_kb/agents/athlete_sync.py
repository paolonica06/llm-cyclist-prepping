"""Morning sync: ingestione idempotente dei dati atleta da intervals.icu.

Separato dalla pipeline dei paper: produce Serie storiche e Attività, non
`PaperRecord`. È idempotente (upsert su chiavi deterministiche). Se il client
non è disponibile (no key / offline) è un **no-op pulito**, senza eccezioni.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Sequence

from ..clients.intervals_icu import POWER_CURVE_TYPES, IntervalsClient
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

        # Calendario: gare (RACE_*) + workout pianificati. Senza questo il sistema
        # pianifica alla cieca — gare e piano vivono qui, non in /activities.
        races, planned = await self.intervals.fetch_events(athlete_id, oldest=oldest, newest=newest)
        for race in races:
            self.db.save_race(race)
        for workout in planned:
            self.db.save_planned_workout(athlete_id, workout)

        summary: Dict[str, object] = {
            "athlete_id": athlete_id,
            "available": self.intervals.available,
            "timeseries_points": len(daily),
            "activities": len(activities),
            "power_curve_points": len(power_curve),
            "races": len(races),
            "planned_workouts": len(planned),
        }
        logger.info("Morning sync %s: %s", athlete_id, summary)
        return summary

    async def backfill_activity_power_curves(
        self, athlete_id: str,
        types: Sequence[str] = POWER_CURVE_TYPES,
        limit: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, object]:
        """Ingesta le curve mean-max **per-attività** (Ride + indoor VirtualRide).

        Incrementale: salta le attività che hanno già una curva (a meno di `force`),
        così il primo backfill fa il grosso e i successivi sono a costo ~zero. Le
        attività senza potenza (nessun power meter) tornano None e non vengono salvate.
        `limit` bound il numero di fetch per run (utile per non saturare il rate-limit).
        """
        wanted = set(types)
        done = set() if force else self.db.activity_ids_with_power_curve(athlete_id)
        eligible = [a for a in self.db.list_activities(athlete_id)
                    if a.type in wanted and a.external_id]
        candidates = [a for a in eligible if a.id not in done]
        skipped = len(eligible) - len(candidates)
        fetched = empty = 0
        for activity in candidates:
            if limit is not None and fetched >= limit:
                break
            curve = await self.intervals.fetch_activity_power_curve(activity.external_id)
            if not curve:
                empty += 1
                continue
            self.db.save_activity_power_curve(activity.id, athlete_id, curve, date=activity.date)
            fetched += 1
        summary: Dict[str, object] = {
            "athlete_id": athlete_id,
            "available": self.intervals.available,
            "candidates": len(eligible),
            "fetched": fetched,
            "skipped": skipped,
            "empty": empty,
        }
        logger.info("Backfill power curves %s: %s", athlete_id, summary)
        return summary
