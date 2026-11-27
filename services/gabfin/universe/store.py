"""Immutable sourced observations; an expired exclusion does not revive old ideas."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from uuid import UUID

from gabfin.contracts.research import EvidenceItem
from gabfin.contracts.support import CandidateObservation


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError('Aware UTC timestamp required')


class CandidateStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS candidate_evidence (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS candidate_observations (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            ''')

    def _connect(self):
        return sqlite3.connect(self.path)

    @staticmethod
    def _insert(db, table, identity, payload):
        old = db.execute(f'SELECT payload FROM {table} WHERE id=?', (str(identity),)).fetchone()
        if old is not None and old[0] != payload:
            raise ValueError('Immutable identity conflict')
        db.execute(f'INSERT OR IGNORE INTO {table}(id,payload) VALUES (?,?)', (str(identity), payload))

    def ingest(self, item: EvidenceItem) -> UUID:
        item = EvidenceItem.model_validate(item.model_dump())
        if item.published_at is not None and item.published_at > item.available_at:
            raise ValueError('Evidence published after availability')
        with self._connect() as db:
            self._insert(db, 'candidate_evidence', item.evidence_id, item.model_dump_json())
        return item.evidence_id

    def evidence(self, identity: UUID) -> EvidenceItem:
        with self._connect() as db:
            row = db.execute('SELECT payload FROM candidate_evidence WHERE id=?', (str(identity),)).fetchone()
        if row is None:
            raise KeyError('Unknown evidence')
        return EvidenceItem.model_validate_json(row[0])

    def observe(self, item: CandidateObservation) -> None:
        item = CandidateObservation.model_validate(item.model_dump())
        with self._connect() as db:
            for identity in item.evidence:
                row = db.execute('SELECT payload FROM candidate_evidence WHERE id=?', (str(identity),)).fetchone()
                if row is None or EvidenceItem.model_validate_json(row[0]).available_at > item.observed_at:
                    raise ValueError('Evidence unavailable at observation')
            self._insert(db, 'candidate_observations', item.observation_id, item.model_dump_json())

    def universe_at(self, as_of: datetime) -> tuple[CandidateObservation, ...]:
        _utc(as_of)
        with self._connect() as db:
            rows = db.execute('SELECT payload FROM candidate_observations ORDER BY rowid').fetchall()
        latest = {}
        for row in rows:
            item = CandidateObservation.model_validate_json(row[0])
            previous = latest.get(item.instrument)
            if item.observed_at <= as_of and (previous is None or item.observed_at >= previous.observed_at):
                latest[item.instrument] = item
        return tuple(item for item in latest.values() if item.action == 'include' and as_of < item.expires_at)
