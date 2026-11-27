"""Persistent server-owned identities for provider-verified US stocks."""
import json
import sqlite3
import threading
from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid5


class InstrumentDirectory:
    def __init__(self, path: Path, *, lookup=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lookup = lookup
        self._lock = threading.RLock()
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS research_instruments (symbol TEXT PRIMARY KEY, id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)')

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def seed(self, symbol, instrument_id):
        with self._lock, self._connect() as db:
            row = db.execute('SELECT id FROM research_instruments WHERE symbol=?', (symbol,)).fetchone()
            if row is not None and row[0] != str(instrument_id):
                raise ValueError('Instrument identity conflict')
            payload = {'symbol': symbol, 'instrument_id': str(instrument_id), 'name': symbol, 'source': 'server_registration'}
            db.execute('INSERT OR IGNORE INTO research_instruments VALUES (?,?,?)', (symbol, str(instrument_id), json.dumps(payload)))

    @property
    def instrument_ids(self):
        with self._connect() as db:
            return tuple(row[0] for row in db.execute('SELECT id FROM research_instruments ORDER BY symbol'))

    def by_id(self, instrument_id):
        with self._connect() as db:
            row = db.execute('SELECT payload FROM research_instruments WHERE id=?', (str(instrument_id),)).fetchone()
        if row is None:
            raise KeyError('Unregistered research instrument')
        return json.loads(row[0])

    def resolve(self, symbol):
        with self._lock:
            with self._connect() as db:
                row = db.execute('SELECT payload FROM research_instruments WHERE symbol=?', (symbol,)).fetchone()
            if row is not None:
                return json.loads(row[0])
            if self.lookup is None:
                return None
            raw = self.lookup(symbol)
            if not isinstance(raw, dict) or (raw.get('ticker') != symbol or raw.get('market') != 'stocks'
                    or raw.get('locale') != 'us' or raw.get('active') is not True
                    or str(raw.get('currency_name', '')).lower() != 'usd'):
                return None
            identity = str(uuid5(NAMESPACE_URL, 'gabfin:massive:us:stocks:' + symbol))
            payload = {'symbol': symbol, 'instrument_id': identity,
                       'name': raw.get('name') if isinstance(raw.get('name'), str) else symbol,
                       'source': 'massive_reference'}
            with self._connect() as db:
                db.execute('INSERT INTO research_instruments VALUES (?,?,?)', (symbol, identity, json.dumps(payload)))
            return payload
