"""Explicit local SQLite connections; no network or legacy DB discovery."""
import sqlite3
from pathlib import Path

def open_database(path: Path) -> sqlite3.Connection:
    connection=sqlite3.connect(path,timeout=5)
    connection.execute('pragma foreign_keys=ON')
    connection.execute('pragma journal_mode=WAL')
    connection.execute('pragma busy_timeout=5000')
    return connection
