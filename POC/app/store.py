"""Single local pilot company. PostgreSQL/PostGIS or explicit SQLite local mode."""
import json, sqlite3, uuid
from contextlib import contextmanager
from .config import DATA,DATABASE_URL
from .sources import utcnow

class Store:
    def __init__(self,url=None,path=None):
        self.url=DATABASE_URL if url is None else url
        self.path=path or DATA/'shaked.sqlite3'
        self.pg=bool(self.url)
    @contextmanager
    def connect(self,write=False):
        if self.pg:
            import psycopg
            from psycopg.rows import dict_row
            c=psycopg.connect(self.url,row_factory=dict_row)
            if write: c.execute('SELECT pg_advisory_xact_lock(1396400)')
        else:
            c=sqlite3.connect(self.path,timeout=30); c.row_factory=sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON')
            if write: c.execute('BEGIN IMMEDIATE')
        try: yield c; c.commit()
        except Exception: c.rollback(); raise
        finally: c.close()
    def run(self,c,sql,args=()): return c.execute(sql.replace('?', '%s') if self.pg else sql,args)
    def init(self):
        with self.connect(write=True) as c:
            for sql in [
              'CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,state TEXT NOT NULL,request TEXT NOT NULL,result TEXT NOT NULL,progress INTEGER NOT NULL,error TEXT,created_at TEXT NOT NULL)',
              'CREATE TABLE IF NOT EXISTS dossiers(id TEXT PRIMARY KEY,payload TEXT NOT NULL,created_at TEXT NOT NULL)',
              'CREATE TABLE IF NOT EXISTS packages(id TEXT PRIMARY KEY,used INTEGER NOT NULL CHECK(used BETWEEN 0 AND 3),created_at TEXT NOT NULL)',
              'CREATE TABLE IF NOT EXISTS deliveries(entity_key TEXT PRIMARY KEY,dossier_id TEXT NOT NULL REFERENCES dossiers(id),package_id TEXT NOT NULL REFERENCES packages(id))',
              'CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL)',
              'CREATE TABLE IF NOT EXISTS archive_files(id TEXT PRIMARY KEY,state TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL)',
              'CREATE TABLE IF NOT EXISTS archive_streets(id TEXT PRIMARY KEY,name TEXT NOT NULL,state TEXT NOT NULL,file_count INTEGER NOT NULL,error TEXT,payload TEXT NOT NULL,updated_at TEXT NOT NULL)',
              'CREATE TABLE IF NOT EXISTS scenarios(id TEXT PRIMARY KEY,dossier_id TEXT NOT NULL REFERENCES dossiers(id),payload TEXT NOT NULL,created_at TEXT NOT NULL)',
              'CREATE TABLE IF NOT EXISTS pipeline_runs(id TEXT PRIMARY KEY,building_id TEXT NOT NULL,dossier_id TEXT NOT NULL REFERENCES dossiers(id),scan_seconds REAL NOT NULL,data_entry_seconds REAL NOT NULL,total_seconds REAL NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL)']:
                self.run(c,sql)
            if self.pg:
                c.execute('CREATE EXTENSION IF NOT EXISTS postgis')
                c.execute('ALTER TABLE entities ADD COLUMN IF NOT EXISTS geom geometry(Geometry,2039)')
                c.execute('CREATE INDEX IF NOT EXISTS entities_geom_idx ON entities USING GIST(geom)')
            if not self.run(c,'SELECT id FROM packages LIMIT 1').fetchone():
                self.run(c,'INSERT INTO packages VALUES(?,?,?)',('pilot-package-1',0,utcnow()))
            self.run(c,"UPDATE jobs SET state='queued' WHERE state='running'")
            # The public pages may contain applicant names. They are not needed for
            # the planning screen, so old pilot rows are scrubbed during migration.
            rows=self.run(c,'SELECT id,payload FROM archive_files').fetchall()
            for row in rows:
                payload=json.loads(row['payload'])
                if payload.pop('raw_html',None) is not None:
                    self.run(c,'UPDATE archive_files SET payload=?,updated_at=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),utcnow(),row['id']))
    def create_job(self,request):
        jid=str(uuid.uuid4())
        with self.connect(write=True) as c:
            self.run(c,'INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',(jid,'queued',json.dumps(request),json.dumps({'candidates':[],'issues':[]}),0,None,utcnow()))
        return jid
    def job(self,jid):
        with self.connect() as c: row=self.run(c,'SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row:return None
        d=dict(row); d['request']=json.loads(d['request']);d['result']=json.loads(d['result']); return d
    def jobs(self):
        with self.connect() as c: rows=self.run(c,'SELECT id,state,progress,error,created_at,request FROM jobs ORDER BY created_at DESC LIMIT 100').fetchall()
        output=[]
        for row in rows:
            item=dict(row);request=json.loads(item.pop('request'));item['polygon']=request.get('polygon');item['center']=request.get('center');item['radius_m']=request.get('radius_m');output.append(item)
        return output
    def update(self,jid,state,progress,result,error=None):
        with self.connect(write=True) as c:
            self.run(c,'UPDATE jobs SET state=?,progress=?,result=?,error=? WHERE id=?',(state,progress,json.dumps(result,ensure_ascii=False),error,jid))
    def entity(self,entity,kind):
        with self.connect(write=True) as c:
            self.run(c,'INSERT INTO entities(id,kind,payload) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(entity['id'],kind,json.dumps(entity,ensure_ascii=False)))
            if self.pg and entity.get('geometry'):
                self.run(c,'UPDATE entities SET geom=ST_SetSRID(ST_GeomFromGeoJSON(?),2039) WHERE id=?',(json.dumps(entity['geometry']),entity['id']))
    def save_dossier(self,d):
        # Snapshot identifiers are content addressed and never overwritten.
        with self.connect(write=True) as c:
            self.run(c,'INSERT INTO dossiers VALUES(?,?,?) ON CONFLICT(id) DO NOTHING',(d['id'],json.dumps(d,ensure_ascii=False),utcnow()))
    def dossier(self,did):
        with self.connect() as c: row=self.run(c,'SELECT payload FROM dossiers WHERE id=?',(did,)).fetchone()
        return json.loads(row['payload']) if row else None
    def dossiers(self):
        with self.connect() as c: rows=self.run(c,'SELECT payload FROM dossiers ORDER BY created_at DESC LIMIT 300').fetchall()
        return [json.loads(x['payload']) for x in rows]
    def prune_dossier_versions(self,building_id,keep=1):
        """Explicit maintenance operation; delivered snapshots are never removed."""
        keep=max(1,int(keep))
        with self.connect(write=True) as c:
            rows=self.run(c,'SELECT id,payload,created_at FROM dossiers ORDER BY created_at DESC').fetchall()
            matches=[x for x in rows if json.loads(x['payload']).get('building_id')==building_id]
            remove=matches[keep:]
            for row in remove:
                if self.run(c,'SELECT 1 FROM deliveries WHERE dossier_id=?',(row['id'],)).fetchone():
                    raise ValueError(f"Cannot remove delivered dossier snapshot: {row['id']}")
                self.run(c,'DELETE FROM scenarios WHERE dossier_id=?',(row['id'],))
                self.run(c,'DELETE FROM pipeline_runs WHERE dossier_id=?',(row['id'],))
                self.run(c,'DELETE FROM dossiers WHERE id=?',(row['id'],))
        return {'building_id':building_id,'kept':[x['id'] for x in matches[:keep]],'deleted':[x['id'] for x in remove]}
    def save_pipeline_run(self,run):
        with self.connect(write=True) as c:
            self.run(c,'INSERT INTO pipeline_runs VALUES(?,?,?,?,?,?,?,?)',(
                run['id'],run['building_id'],run['dossier_id'],float(run['scan_seconds']),
                float(run['data_entry_seconds']),float(run['total_seconds']),
                json.dumps(run,ensure_ascii=False),run.get('created_at') or utcnow()))
    def pipeline_runs(self):
        with self.connect() as c:rows=self.run(c,'SELECT payload FROM pipeline_runs ORDER BY created_at DESC').fetchall()
        return [json.loads(x['payload']) for x in rows]
    def balance(self):
        with self.connect() as c:
            rows=self.run(c,'SELECT * FROM packages ORDER BY created_at').fetchall()
            delivered=self.run(c,'SELECT DISTINCT dossier_id FROM deliveries').fetchall()
        return {'packages':[dict(x) for x in rows],'remaining':sum(3-x['used'] for x in rows),'delivered':[x['dossier_id'] for x in delivered],'simulated':True}
    def new_package(self):
        with self.connect(write=True) as c:
            if self.run(c,'SELECT id FROM packages WHERE used<3').fetchone(): return
            self.run(c,'INSERT INTO packages VALUES(?,?,?)',(str(uuid.uuid4()),0,utcnow()))
    def deliver(self,candidates):
        delivered=[]
        with self.connect(write=True) as c:
            for d in candidates:
                saved=self.run(c,'SELECT payload FROM dossiers WHERE id=?',(d['id'],)).fetchone()
                if not saved:continue
                d=json.loads(saved['payload'])
                if d['status']!='ready' or d['gaps'] or not d.get('scenario'): continue
                keys=d['entity_keys']
                if not keys: continue
                if any(self.run(c,'SELECT 1 FROM deliveries WHERE entity_key=?',(k,)).fetchone() for k in keys):continue
                pkg=self.run(c,'SELECT id FROM packages WHERE used<3 ORDER BY created_at LIMIT 1').fetchone()
                if not pkg:break
                for k in keys: self.run(c,'INSERT INTO deliveries VALUES(?,?,?)',(k,d['id'],pkg['id']))
                self.run(c,'UPDATE packages SET used=used+1 WHERE id=?',(pkg['id'],)); delivered.append(d['id'])
        return delivered
    def scenario(self,did,payload):
        sid=str(uuid.uuid4())
        with self.connect(write=True) as c:self.run(c,'INSERT INTO scenarios VALUES(?,?,?,?)',(sid,did,json.dumps(payload),utcnow()))
        return sid
    def save_archive_file(self,file_number,payload,state='discovered'):
        with self.connect(write=True) as c:
            existing=self.run(c,'SELECT state,payload FROM archive_files WHERE id=?',(str(file_number),)).fetchone()
            if existing and existing['state']=='metadata_complete' and state=='discovered':return
            if existing:
                old=json.loads(existing['payload'])
                if 'discovered_on_streets' in payload:
                    merged={(str(x.get('code')),x.get('name')):x for x in old.get('discovered_on_streets',[])+payload['discovered_on_streets']}
                    payload=dict(payload,discovered_on_streets=list(merged.values()))
                old.update(payload);payload=old
            self.run(c,'INSERT INTO archive_files VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,payload=excluded.payload,updated_at=excluded.updated_at',
                     (str(file_number),state,json.dumps(payload,ensure_ascii=False),utcnow()))
    def pending_archive_files(self,limit=None):
        sql="SELECT id,payload FROM archive_files WHERE state!='metadata_complete' ORDER BY CAST(id AS INTEGER)"
        args=()
        if limit is not None:sql+=' LIMIT ?';args=(int(limit),)
        with self.connect() as c:rows=self.run(c,sql,args).fetchall()
        return [{'id':x['id'],'payload':json.loads(x['payload'])} for x in rows]
    def retry_failed_archive_files(self):
        with self.connect(write=True) as c:self.run(c,"UPDATE archive_files SET state='discovered' WHERE state='metadata_failed'")
    def save_archive_street(self,code,name,state='pending',file_count=0,error=None,payload=None):
        with self.connect(write=True) as c:
            self.run(c,'INSERT INTO archive_streets VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,state=excluded.state,file_count=excluded.file_count,error=excluded.error,payload=excluded.payload,updated_at=excluded.updated_at',
                     (str(code),name,state,int(file_count),error,json.dumps(payload or {},ensure_ascii=False),utcnow()))
    def archive_streets(self,state=None,limit=None):
        sql='SELECT * FROM archive_streets';args=[]
        if state:sql+=' WHERE state=?';args.append(state)
        sql+=' ORDER BY name,id'
        if limit is not None:sql+=' LIMIT ?';args.append(int(limit))
        with self.connect() as c:rows=self.run(c,sql,tuple(args)).fetchall()
        return [dict(x) for x in rows]
    def archive_status(self):
        with self.connect() as c:
            streets=self.run(c,'SELECT state,COUNT(*) n,SUM(file_count) files FROM archive_streets GROUP BY state').fetchall()
            files=self.run(c,'SELECT state,COUNT(*) n FROM archive_files GROUP BY state').fetchall()
        return {'streets':{x['state']:{'count':x['n'],'reported_files':x['files'] or 0} for x in streets},
                'files':{x['state']:x['n'] for x in files},'coverage_complete':bool(streets) and all(x['state']=='complete' for x in streets)}
    def archive_files_for_parcels(self,pairs):
        wanted={(int(g),int(p)) for g,p in pairs};output=[]
        if not wanted:return output
        with self.connect() as c:rows=self.run(c,"SELECT payload FROM archive_files WHERE state='metadata_complete'").fetchall()
        for row in rows:
            payload=json.loads(row['payload'])
            if any((int(x['gush']),int(x['parcel'])) in wanted for x in payload.get('parcels',[])):output.append(payload)
        return sorted(output,key=lambda x:x['file_number'])
