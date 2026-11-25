import sqlite3
import pytest

def test_migrations_reentrant_and_unknown(tmp_path):
 from gabfin.storage.database import open_database
 from gabfin.storage.migrations import migrate
 p=tmp_path/'db.sqlite';assert migrate(p)==1;assert migrate(p)==1
 with open_database(p) as c:
  assert c.execute('pragma foreign_keys').fetchone()[0]==1
  tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
  assert {'schema_migrations','instruments','events','job_runs','job_leases','artifacts'}<=tables
  c.execute('insert into schema_migrations values(999)')
 with pytest.raises(ValueError):migrate(p)

def test_migration_crash_atomic(tmp_path,monkeypatch):
 from gabfin.storage import migrations as m
 p=tmp_path/'crash.sqlite'
 monkeypatch.setattr(m,'STATEMENTS',m.STATEMENTS+('INVALID SQL',))
 with pytest.raises(sqlite3.Error):m.migrate(p)
 with sqlite3.connect(p) as c:assert not c.execute("select name from sqlite_master where type='table'").fetchall()
def test_foreign_keys_and_unique_keys(tmp_path):
 from gabfin.storage.database import open_database
 from gabfin.storage.migrations import migrate
 p=tmp_path/'db';migrate(p);c=open_database(p)
 try:
  with pytest.raises(sqlite3.IntegrityError):c.execute("insert into job_leases values('missing','worker','token','time',1)")
  c.rollback();c.execute("insert into events values('e1','dedup','{}')")
  with pytest.raises(sqlite3.IntegrityError):c.execute("insert into events values('e2','dedup','{}')")
 finally:c.close()
