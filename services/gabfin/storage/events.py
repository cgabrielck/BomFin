"""Durable canonical market observations; conflicts never overwrite evidence."""
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter

from gabfin.contracts.events import MarketEvent
from gabfin.storage.database import open_database
from gabfin.storage.migrations import migrate

_EVENTS = TypeAdapter(MarketEvent)


class EventLedger:
    def __init__(self, path: Path):
        self._path = Path(path)
        migrate(self._path)

    def append(self, event: MarketEvent) -> bool:
        validated = _EVENTS.validate_json(event.model_dump_json())
        document = validated.model_dump_json()
        connection = open_database(self._path)
        try:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute(
                'SELECT document FROM events WHERE id=? OR dedup_key=?',
                (str(validated.event_id), validated.dedup_key)).fetchall()
            if existing:
                from gabfin.market.coordinator import _market_facts
                if any(_market_facts(_EVENTS.validate_json(row[0])) != _market_facts(validated)
                       for row in existing):
                    raise ValueError('Event identity conflict')
                connection.rollback()
                return False
            connection.execute('INSERT INTO events(id,dedup_key,document) VALUES(?,?,?)',
                (str(validated.event_id), validated.dedup_key, document))
            connection.commit()
            return True
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read(self, event_id: UUID) -> MarketEvent | None:
        connection = open_database(self._path)
        try:
            row = connection.execute('SELECT document FROM events WHERE id=?', (str(event_id),)).fetchone()
            return None if row is None else _EVENTS.validate_json(row[0])
        finally:
            connection.close()
