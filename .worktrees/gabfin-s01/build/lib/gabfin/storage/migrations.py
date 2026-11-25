"""Atomic initial schema, rejecting unknown or gapped migration history."""
from pathlib import Path
from gabfin.storage.database import open_database

STATEMENTS=(
 'CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)',
 'CREATE TABLE instruments(id TEXT PRIMARY KEY, document TEXT NOT NULL)',
 'CREATE TABLE events(id TEXT PRIMARY KEY, dedup_key TEXT NOT NULL UNIQUE, document TEXT NOT NULL)',
 'CREATE TABLE job_runs(id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, document TEXT NOT NULL)',
 'CREATE TABLE job_leases(job_id TEXT PRIMARY KEY REFERENCES job_runs(id), worker_id TEXT NOT NULL, lease_token TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>0))',
 'CREATE TABLE artifacts(id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, document TEXT NOT NULL)',
)

def migrate(db_path: Path) -> int:
    c=open_database(db_path)
    try:
        c.execute('BEGIN IMMEDIATE')
        exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
        if exists:
            versions=[r[0] for r in c.execute('SELECT version FROM schema_migrations ORDER BY version')]
            if versions!=[1]:raise ValueError('Unknown or incomplete schema version')
        else:
            for statement in STATEMENTS:c.execute(statement)
            c.execute('INSERT INTO schema_migrations VALUES(1)')
        c.commit()
        return 1
    except BaseException:
        c.rollback()
        raise
    finally:c.close()
