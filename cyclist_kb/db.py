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

    def close(self) -> None:
        self.conn.close()
