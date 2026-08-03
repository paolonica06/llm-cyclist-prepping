"""Persistenza SQLite.

Strategia: ogni `PaperRecord` è serializzato come JSON in colonna `data`, con
alcune colonne indicizzate (state, doi, pmid) per interrogazioni veloci.
Questo mantiene lo schema semplice ma preserva l'intera struttura degli agenti.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .config import get_settings
from .models import PaperRecord, Research, RecordState
from .athlete_models import (ActivitySummary, Assessment, Athlete, Race,
                             TimeseriesPoint, TrainingPlan, TransferabilityMemo,
                             PlanStatus, make_timeseries_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS researches (
    id          TEXT PRIMARY KEY,
    topic       TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS records (
    id          TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    state       TEXT NOT NULL,
    doi         TEXT,
    pmid        TEXT,
    title       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    data        TEXT NOT NULL,
    FOREIGN KEY (research_id) REFERENCES researches(id)
);

CREATE INDEX IF NOT EXISTS idx_records_research ON records(research_id);
CREATE INDEX IF NOT EXISTS idx_records_state    ON records(research_id, state);
CREATE INDEX IF NOT EXISTS idx_records_doi      ON records(doi);
CREATE INDEX IF NOT EXISTS idx_records_pmid     ON records(pmid);

-- ----------------------------------------------------------------------- --
-- Fase B: modello atleta longitudinale (stesso pattern blob-JSON + indici) --
-- ----------------------------------------------------------------------- --
CREATE TABLE IF NOT EXISTS athletes (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    discipline  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS athlete_timeseries (
    id          TEXT PRIMARY KEY,
    athlete_id  TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    date        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ts_athlete ON athlete_timeseries(athlete_id, metric_type, date);

CREATE TABLE IF NOT EXISTS activities (
    id          TEXT PRIMARY KEY,
    athlete_id  TEXT NOT NULL,
    date        TEXT,
    created_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_athlete ON activities(athlete_id, date);

-- Curve di potenza per-attività (mean-max già calcolata da intervals.icu). Tabella
-- separata dalle activities: così la morning-sync (che riscrive le activities) non
-- sovrascrive le curve ingerite dal backfill.
CREATE TABLE IF NOT EXISTS activity_power_curves (
    activity_id TEXT PRIMARY KEY,
    athlete_id  TEXT NOT NULL,
    date        TEXT,
    created_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_apc_athlete ON activity_power_curves(athlete_id, date);

-- Lap/intervalli auto-rilevati per-attività (segmentati da intervals.icu). Tabella
-- separata come activity_power_curves: permette di verificare l'esecuzione blocco
-- per blocco di un allenamento strutturato, non solo la media sull'intera uscita.
CREATE TABLE IF NOT EXISTS activity_intervals (
    activity_id TEXT PRIMARY KEY,
    athlete_id  TEXT NOT NULL,
    date        TEXT,
    created_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_athlete ON activity_intervals(athlete_id, date);

-- Workout PIANIFICATI, ingeriti dal calendario intervals.icu (/events, category
-- WORKOUT). Mirror del "pianificato": senza questo il confronto pianificato-vs-fatto
-- del protocollo coaching userebbe il piano generico interno invece del calendario reale.
CREATE TABLE IF NOT EXISTS planned_workouts (
    id          TEXT PRIMARY KEY,          -- id evento intervals.icu
    athlete_id  TEXT NOT NULL,
    date        TEXT,
    created_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_planned_athlete ON planned_workouts(athlete_id, date);

CREATE TABLE IF NOT EXISTS races (
    id          TEXT PRIMARY KEY,
    athlete_id  TEXT NOT NULL,
    date        TEXT,
    priority    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_races_athlete ON races(athlete_id, date);

CREATE TABLE IF NOT EXISTS assessments (
    id          TEXT PRIMARY KEY,
    athlete_id  TEXT NOT NULL,
    protocol    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assess_athlete ON assessments(athlete_id, protocol);

CREATE TABLE IF NOT EXISTS plans (
    id          TEXT PRIMARY KEY,
    athlete_id  TEXT NOT NULL,
    version     INTEGER NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_athlete ON plans(athlete_id, version);
CREATE INDEX IF NOT EXISTS idx_plans_status  ON plans(athlete_id, status);

CREATE TABLE IF NOT EXISTS transferability_memos (
    id          TEXT PRIMARY KEY,
    athlete_id  TEXT NOT NULL,
    block_id    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memos_athlete ON transferability_memos(athlete_id, block_id);
"""


class Database:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else get_settings().db_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- Ricerche ----------------------------------------------------------- #
    def create_research(self, research: Research) -> Research:
        now = _now()
        research.created_at = research.created_at or now
        research.updated_at = now
        self.conn.execute(
            "INSERT INTO researches (id, topic, status, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (research.id, research.topic, research.status.value,
             research.created_at, research.updated_at, research.model_dump_json()),
        )
        self.conn.commit()
        return research

    def save_research(self, research: Research) -> Research:
        research.updated_at = _now()
        self.conn.execute(
            "UPDATE researches SET topic=?, status=?, updated_at=?, data=? WHERE id=?",
            (research.topic, research.status.value, research.updated_at,
             research.model_dump_json(), research.id),
        )
        self.conn.commit()
        return research

    def get_research(self, research_id: str) -> Optional[Research]:
        row = self.conn.execute(
            "SELECT data FROM researches WHERE id=?", (research_id,)
        ).fetchone()
        return Research.model_validate_json(row["data"]) if row else None

    def list_researches(self) -> List[Research]:
        rows = self.conn.execute(
            "SELECT data FROM researches ORDER BY created_at DESC"
        ).fetchall()
        return [Research.model_validate_json(r["data"]) for r in rows]

    # -- Record ------------------------------------------------------------- #
    def upsert_record(self, record: PaperRecord) -> PaperRecord:
        now = _now()
        exists = self.conn.execute(
            "SELECT created_at FROM records WHERE id=?", (record.id,)
        ).fetchone()
        created_at = exists["created_at"] if exists else now
        self.conn.execute(
            "INSERT INTO records (id, research_id, state, doi, pmid, title, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "state=excluded.state, doi=excluded.doi, pmid=excluded.pmid, title=excluded.title, "
            "updated_at=excluded.updated_at, data=excluded.data",
            (record.id, record.research_id, record.state.value, record.normalized_doi(),
             record.pmid, record.title, created_at, now, record.model_dump_json()),
        )
        self.conn.commit()
        return record

    def get_record(self, record_id: str) -> Optional[PaperRecord]:
        row = self.conn.execute(
            "SELECT data FROM records WHERE id=?", (record_id,)
        ).fetchone()
        return PaperRecord.model_validate_json(row["data"]) if row else None

    def list_records(
        self,
        research_id: str,
        states: Optional[List[RecordState]] = None,
    ) -> List[PaperRecord]:
        if states:
            placeholders = ",".join("?" for _ in states)
            rows = self.conn.execute(
                f"SELECT data FROM records WHERE research_id=? AND state IN ({placeholders}) "
                "ORDER BY created_at ASC",
                (research_id, *[s.value for s in states]),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT data FROM records WHERE research_id=? ORDER BY created_at ASC",
                (research_id,),
            ).fetchall()
        return [PaperRecord.model_validate_json(r["data"]) for r in rows]

    def count_by_state(self, research_id: str) -> dict:
        rows = self.conn.execute(
            "SELECT state, COUNT(*) AS n FROM records WHERE research_id=? GROUP BY state",
            (research_id,),
        ).fetchall()
        return {r["state"]: r["n"] for r in rows}

    # -- Fase B: Atleta ----------------------------------------------------- #
    def save_athlete(self, athlete: Athlete) -> Athlete:
        """Upsert dell'atleta (identità + contesto qualitativo)."""
        now = _now()
        existing = self.conn.execute(
            "SELECT created_at FROM athletes WHERE id=?", (athlete.id,)
        ).fetchone()
        athlete.created_at = (existing["created_at"] if existing else athlete.created_at) or now
        athlete.updated_at = now
        self.conn.execute(
            "INSERT INTO athletes (id, name, discipline, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, discipline=excluded.discipline, "
            "updated_at=excluded.updated_at, data=excluded.data",
            (athlete.id, athlete.name, athlete.discipline, athlete.created_at,
             athlete.updated_at, athlete.model_dump_json()),
        )
        self.conn.commit()
        return athlete

    # Alias esplicito per la creazione (stesso upsert idempotente).
    create_athlete = save_athlete

    def get_athlete(self, athlete_id: str) -> Optional[Athlete]:
        row = self.conn.execute(
            "SELECT data FROM athletes WHERE id=?", (athlete_id,)
        ).fetchone()
        return Athlete.model_validate_json(row["data"]) if row else None

    def list_athletes(self) -> List[Athlete]:
        rows = self.conn.execute(
            "SELECT data FROM athletes ORDER BY created_at ASC"
        ).fetchall()
        return [Athlete.model_validate_json(r["data"]) for r in rows]

    # -- Fase B: Serie storiche --------------------------------------------- #
    def add_timeseries_point(self, point: TimeseriesPoint) -> TimeseriesPoint:
        """Upsert idempotente su (atleta, grandezza, data): ri-sincronizzare non duplica."""
        tid = make_timeseries_id(point.athlete_id, point.metric_type.value, point.date)
        now = _now()
        self.conn.execute(
            "INSERT INTO athlete_timeseries (id, athlete_id, metric_type, date, created_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (tid, point.athlete_id, point.metric_type.value, point.date,
             now, point.model_dump_json()),
        )
        self.conn.commit()
        return point

    def list_timeseries(
        self,
        athlete_id: str,
        metric_type: Optional[str] = None,
        since: Optional[str] = None,
    ) -> List[TimeseriesPoint]:
        clauses = ["athlete_id=?"]
        params: List[str] = [athlete_id]
        if metric_type:
            clauses.append("metric_type=?")
            params.append(metric_type)
        if since:
            clauses.append("date>=?")
            params.append(since)
        rows = self.conn.execute(
            f"SELECT data FROM athlete_timeseries WHERE {' AND '.join(clauses)} ORDER BY date ASC",
            tuple(params),
        ).fetchall()
        return [TimeseriesPoint.model_validate_json(r["data"]) for r in rows]

    # -- Fase B: Attività --------------------------------------------------- #
    def save_activity(self, activity: ActivitySummary) -> ActivitySummary:
        """Upsert idempotente su id: ri-sincronizzare non duplica le attività."""
        now = _now()
        self.conn.execute(
            "INSERT INTO activities (id, athlete_id, date, created_at, data) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET date=excluded.date, data=excluded.data",
            (activity.id, activity.athlete_id, activity.date, now, activity.model_dump_json()),
        )
        self.conn.commit()
        return activity

    def list_activities(
        self, athlete_id: str, since: Optional[str] = None
    ) -> List[ActivitySummary]:
        if since:
            rows = self.conn.execute(
                "SELECT data FROM activities WHERE athlete_id=? AND date>=? ORDER BY date ASC",
                (athlete_id, since),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT data FROM activities WHERE athlete_id=? ORDER BY date ASC",
                (athlete_id,),
            ).fetchall()
        return [ActivitySummary.model_validate_json(r["data"]) for r in rows]

    # -- Fase B: Curve di potenza per-attività ------------------------------ #
    def save_activity_power_curve(
        self, activity_id: str, athlete_id: str, curve: dict,
        date: Optional[str] = None,
    ) -> None:
        """Upsert idempotente della curva mean-max di una singola attività."""
        import json
        self.conn.execute(
            "INSERT INTO activity_power_curves (activity_id, athlete_id, date, created_at, data) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(activity_id) DO UPDATE SET date=excluded.date, data=excluded.data",
            (activity_id, athlete_id, date, _now(), json.dumps(curve)),
        )
        self.conn.commit()

    def get_activity_power_curve(self, activity_id: str) -> Optional[dict]:
        import json
        row = self.conn.execute(
            "SELECT data FROM activity_power_curves WHERE activity_id=?", (activity_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None

    def activity_ids_with_power_curve(self, athlete_id: str) -> set:
        """Id (interni) delle attività che hanno già una curva → skip incrementale."""
        rows = self.conn.execute(
            "SELECT activity_id FROM activity_power_curves WHERE athlete_id=?", (athlete_id,)
        ).fetchall()
        return {r["activity_id"] for r in rows}

    # -- Fase B: Lap/intervalli per-attività --------------------------------- #
    def save_activity_intervals(
        self, activity_id: str, athlete_id: str, intervals: list,
        date: Optional[str] = None,
    ) -> None:
        """Upsert idempotente dei lap auto-rilevati di una singola attività."""
        import json
        self.conn.execute(
            "INSERT INTO activity_intervals (activity_id, athlete_id, date, created_at, data) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(activity_id) DO UPDATE SET date=excluded.date, data=excluded.data",
            (activity_id, athlete_id, date, _now(), json.dumps(intervals)),
        )
        self.conn.commit()

    def get_activity_intervals(self, activity_id: str) -> Optional[list]:
        import json
        row = self.conn.execute(
            "SELECT data FROM activity_intervals WHERE activity_id=?", (activity_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None

    def activity_ids_with_intervals(self, athlete_id: str) -> set:
        """Id (interni) delle attività che hanno già i lap → skip incrementale."""
        rows = self.conn.execute(
            "SELECT activity_id FROM activity_intervals WHERE athlete_id=?", (athlete_id,)
        ).fetchall()
        return {r["activity_id"] for r in rows}

    # -- Fase B: Gare ------------------------------------------------------- #
    def save_race(self, race: Race) -> Race:
        now = _now()
        self.conn.execute(
            "INSERT INTO races (id, athlete_id, date, priority, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET date=excluded.date, priority=excluded.priority, "
            "updated_at=excluded.updated_at, data=excluded.data",
            (race.id, race.athlete_id, race.date, race.priority.value, now, now,
             race.model_dump_json()),
        )
        self.conn.commit()
        return race

    def list_races(self, athlete_id: str) -> List[Race]:
        rows = self.conn.execute(
            "SELECT data FROM races WHERE athlete_id=? ORDER BY date ASC", (athlete_id,)
        ).fetchall()
        return [Race.model_validate_json(r["data"]) for r in rows]

    # -- Fase B: Workout pianificati (calendario intervals.icu) ------------- #
    def save_planned_workout(self, athlete_id: str, workout: dict) -> None:
        """Upsert idempotente di un workout pianificato (chiave = id evento)."""
        import json
        wid = workout.get("external_id") or make_timeseries_id(
            athlete_id, "planned", f"{workout.get('date')}::{workout.get('name')}")
        self.conn.execute(
            "INSERT INTO planned_workouts (id, athlete_id, date, created_at, data) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET date=excluded.date, data=excluded.data",
            (str(wid), athlete_id, workout.get("date"), _now(), json.dumps(workout)),
        )
        self.conn.commit()

    def list_planned_workouts(self, athlete_id: str, since: Optional[str] = None) -> List[dict]:
        import json
        if since:
            rows = self.conn.execute(
                "SELECT data FROM planned_workouts WHERE athlete_id=? AND date>=? ORDER BY date ASC",
                (athlete_id, since),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT data FROM planned_workouts WHERE athlete_id=? ORDER BY date ASC",
                (athlete_id,),
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    # -- Fase B: Valutazioni ------------------------------------------------ #
    def save_assessment(self, assessment: Assessment) -> Assessment:
        now = _now()
        self.conn.execute(
            "INSERT INTO assessments (id, athlete_id, protocol, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET protocol=excluded.protocol, "
            "updated_at=excluded.updated_at, data=excluded.data",
            (assessment.id, assessment.athlete_id, assessment.protocol.value, now, now,
             assessment.model_dump_json()),
        )
        self.conn.commit()
        return assessment

    def list_assessments(
        self, athlete_id: str, protocol: Optional[str] = None
    ) -> List[Assessment]:
        if protocol:
            rows = self.conn.execute(
                "SELECT data FROM assessments WHERE athlete_id=? AND protocol=? "
                "ORDER BY COALESCE(json_extract(data,'$.executed_date'), "
                "json_extract(data,'$.planned_date')) ASC",
                (athlete_id, protocol),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT data FROM assessments WHERE athlete_id=? "
                "ORDER BY COALESCE(json_extract(data,'$.executed_date'), "
                "json_extract(data,'$.planned_date')) ASC",
                (athlete_id,),
            ).fetchall()
        return [Assessment.model_validate_json(r["data"]) for r in rows]

    # -- Fase B: Piani ------------------------------------------------------ #
    def save_plan(self, plan: TrainingPlan) -> TrainingPlan:
        now = _now()
        existing = self.conn.execute(
            "SELECT created_at FROM plans WHERE id=?", (plan.id,)
        ).fetchone()
        plan.created_at = (existing["created_at"] if existing else plan.created_at) or now
        plan.updated_at = now
        self.conn.execute(
            "INSERT INTO plans (id, athlete_id, version, status, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, "
            "updated_at=excluded.updated_at, data=excluded.data",
            (plan.id, plan.athlete_id, plan.version, plan.status.value,
             plan.created_at, plan.updated_at, plan.model_dump_json()),
        )
        self.conn.commit()
        return plan

    def get_plan(self, plan_id: str) -> Optional[TrainingPlan]:
        row = self.conn.execute(
            "SELECT data FROM plans WHERE id=?", (plan_id,)
        ).fetchone()
        return TrainingPlan.model_validate_json(row["data"]) if row else None

    def list_plans(
        self, athlete_id: str, status: Optional[str] = None
    ) -> List[TrainingPlan]:
        if status:
            rows = self.conn.execute(
                "SELECT data FROM plans WHERE athlete_id=? AND status=? ORDER BY version ASC",
                (athlete_id, status),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT data FROM plans WHERE athlete_id=? ORDER BY version ASC",
                (athlete_id,),
            ).fetchall()
        return [TrainingPlan.model_validate_json(r["data"]) for r in rows]

    def active_plan(self, athlete_id: str) -> Optional[TrainingPlan]:
        """La versione attiva più recente, o None se non ce n'è nessuna."""
        plans = self.list_plans(athlete_id, status=PlanStatus.ACTIVE.value)
        return plans[-1] if plans else None

    def supersede_plan(self, new_plan: TrainingPlan) -> TrainingPlan:
        """Transizione atomica: marca SUPERSEDED i piani attivi dell'atleta e
        persiste `new_plan` come nuova versione attiva, in **un solo commit**
        (blob e colonna coerenti). Evita lo stato a metà."""
        now = _now()
        for p in self.list_plans(new_plan.athlete_id, status=PlanStatus.ACTIVE.value):
            p.status = PlanStatus.SUPERSEDED
            p.updated_at = now
            self.conn.execute(
                "UPDATE plans SET status=?, updated_at=?, data=? WHERE id=?",
                (p.status.value, now, p.model_dump_json(), p.id),
            )
        new_plan.created_at = new_plan.created_at or now
        new_plan.updated_at = now
        self.conn.execute(
            "INSERT INTO plans (id, athlete_id, version, status, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, "
            "updated_at=excluded.updated_at, data=excluded.data",
            (new_plan.id, new_plan.athlete_id, new_plan.version, new_plan.status.value,
             new_plan.created_at, new_plan.updated_at, new_plan.model_dump_json()),
        )
        self.conn.commit()
        return new_plan

    def promote_plan(self, plan_id: str) -> TrainingPlan:
        """Transizione atomica PROPOSED→ACTIVE: marca SUPERSEDED gli ACTIVE
        correnti dell'atleta e promuove il PROPOSED, in un solo commit (ADR-0008).
        Solleva ValueError se il piano non è PROPOSED."""
        plan = self.get_plan(plan_id)
        if plan is None:
            raise ValueError(f"Piano {plan_id} inesistente.")
        if plan.status is not PlanStatus.PROPOSED:
            raise ValueError(f"Piano {plan_id} non è PROPOSED (è {plan.status.value}).")
        now = _now()
        for p in self.list_plans(plan.athlete_id, status=PlanStatus.ACTIVE.value):
            p.status = PlanStatus.SUPERSEDED
            p.updated_at = now
            self.conn.execute(
                "UPDATE plans SET status=?, updated_at=?, data=? WHERE id=?",
                (p.status.value, now, p.model_dump_json(), p.id),
            )
        plan.status = PlanStatus.ACTIVE
        plan.updated_at = now
        self.conn.execute(
            "UPDATE plans SET status=?, updated_at=?, data=? WHERE id=?",
            (plan.status.value, now, plan.model_dump_json(), plan.id),
        )
        self.conn.commit()
        return plan

    # -- Fase B: Memoria di trasferibilità ---------------------------------- #
    def save_memo(self, memo: TransferabilityMemo) -> TransferabilityMemo:
        now = _now()
        self.conn.execute(
            "INSERT INTO transferability_memos (id, athlete_id, block_id, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET block_id=excluded.block_id, "
            "updated_at=excluded.updated_at, data=excluded.data",
            (memo.id, memo.athlete_id, memo.block_id, now, now, memo.model_dump_json()),
        )
        self.conn.commit()
        return memo

    def list_memos(
        self, athlete_id: str, block_id: Optional[str] = None
    ) -> List[TransferabilityMemo]:
        if block_id:
            rows = self.conn.execute(
                "SELECT data FROM transferability_memos WHERE athlete_id=? AND block_id=? "
                "ORDER BY created_at ASC",
                (athlete_id, block_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT data FROM transferability_memos WHERE athlete_id=? ORDER BY created_at ASC",
                (athlete_id,),
            ).fetchall()
        return [TransferabilityMemo.model_validate_json(r["data"]) for r in rows]

    def close(self) -> None:
        self.conn.close()
