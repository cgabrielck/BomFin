"""SQLite-backed opaque sessions; only SHA256 digests persist."""
import hashlib,secrets,sqlite3,json
from gabfin.storage.database import open_database
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID
from gabfin.contracts.identity import Principal
from gabfin.api.capabilities import CEILINGS
from gabfin.contracts.identity import Role

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
class SessionStore:
    def __init__(self,path:Path,*,owner_id:UUID,session_seconds:int,pairing_seconds:int,max_failures:int,clock=None):
        if min(session_seconds,pairing_seconds,max_failures)<=0:raise ValueError('Invalid security configuration')
        self.path=path;self.owner_id=owner_id;self.session_seconds=session_seconds;self.pairing_seconds=pairing_seconds;self.max_failures=max_failures;self.clock=clock or (lambda:datetime.now(timezone.utc))
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("CREATE TABLE IF NOT EXISTS auth_schema(version INTEGER PRIMARY KEY)")
            versions=[r[0] for r in c.execute("SELECT version FROM auth_schema")]
            if versions and versions!=[1]:raise ValueError("Unknown auth schema")
            if not versions:c.execute("INSERT INTO auth_schema VALUES(1)")
            c.execute('CREATE TABLE IF NOT EXISTS pairings(hash TEXT PRIMARY KEY, expires REAL NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL, owner TEXT NOT NULL, root_owner TEXT NOT NULL, role TEXT NOT NULL, scope TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS failures(at REAL NOT NULL)')
    @contextmanager
    def connect(self):
        connection=open_database(self.path)
        try:
            with connection:yield connection
        finally:connection.close()
    def remaining(self,token):
        self.resolve(token)
        with self.connect() as c:expiry=c.execute("SELECT expires FROM sessions WHERE hash=?",(digest(token),)).fetchone()[0]
        return max(0,expiry-self.now())
    def now(self):
        t=self.clock()
        if t.tzinfo is None:raise ValueError('Aware clock required')
        return t.timestamp()
    def create_pairing(self):
        code=secrets.token_urlsafe(32)
        with self.connect() as c:c.execute('INSERT INTO pairings VALUES(?,?)',(digest(code),self.now()+self.pairing_seconds))
        return code
    def issue_session(self,pairing_code):
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);now=self.now()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');c.execute('DELETE FROM failures WHERE at<=?',(now-self.pairing_seconds,))
            row=c.execute('SELECT expires FROM pairings WHERE hash=?',(digest(pairing_code),)).fetchone()
            blocked=c.execute('SELECT count(*) FROM failures').fetchone()[0]>=self.max_failures
            if blocked or row is None or row[0]<=now:
                c.execute('INSERT INTO failures VALUES(?)',(now,));valid=False
            else:
                c.execute('DELETE FROM pairings WHERE hash=?',(digest(pairing_code),));c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)',(digest(token),digest(csrf),now+self.session_seconds,str(self.owner_id),str(self.owner_id),'owner',json.dumps(sorted(CEILINGS[Role.OWNER]))));valid=True
        if not valid:raise PermissionError('Unauthorized')
        return token,csrf
    def resolve(self,token):
        with self.connect() as c:row=c.execute('SELECT expires,owner,root_owner,role,scope FROM sessions WHERE hash=?',(digest(token),)).fetchone()
        if row is None or row[0]<=self.now() or row[2]!=str(self.owner_id):raise PermissionError('Unauthorized')
        return Principal(schema_version='1.0',actor_id=row[1],role=row[3],scope=json.loads(row[4]))
    def check_csrf(self,token,csrf):
        self.resolve(token)
        with self.connect() as c:row=c.execute('SELECT csrf FROM sessions WHERE hash=?',(digest(token),)).fetchone()
        if not csrf or not secrets.compare_digest(row[0],digest(csrf)):raise PermissionError('Forbidden')
    def revoke(self,token):
        with self.connect() as c:c.execute('DELETE FROM sessions WHERE hash=?',(digest(token),))

    def issue_service(self,*,actor_id,role,scope):
        # Trusted host bootstrap only; never expose as an HTTP endpoint.
        from gabfin.contracts.identity import Role,Capability
        role=Role(role);scope=tuple(Capability(c) for c in scope)
        if role==Role.OWNER or not set(scope)<=CEILINGS[role]:raise PermissionError('Forbidden')
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        with self.connect() as c:c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)',(digest(token),digest(csrf),self.now()+self.session_seconds,str(actor_id),str(self.owner_id),role.value,json.dumps(scope)))
        return token,csrf
