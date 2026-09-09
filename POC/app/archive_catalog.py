"""Resumable, evidence-preserving Herzliya building-file catalog."""
import hashlib
import re
from .documents import archive_tables
from .sources import BuildingArchive,PublicClient,SourceError,utcnow

def parse_building_file(record):
    tables=archive_tables(record['html']);parcels=[];requests=[];plans=[]
    for table in tables:
        headers=[x.replace('\u200f','').strip() for x in table['headers']]
        if 'מספר גוש' in headers and 'מספר חלקה' in headers:
            gi=headers.index('מספר גוש');pi=headers.index('מספר חלקה')
            for row in table['rows']:
                if len(row)>max(gi,pi) and row[gi].isdigit() and row[pi].isdigit():parcels.append({'gush':int(row[gi]),'parcel':int(row[pi])})
        if 'מספר בקשה' in headers:
            ri=headers.index('מספר בקשה')
            for row in table['rows']:
                if len(row)>ri and row[ri].isdigit():requests.append(int(row[ri]))
        if 'מספר התוכנית' in headers and 'סטטוס התוכנית' in headers:
            for row in table['rows']:
                if row:plans.append({'number':row[0],'name':row[1] if len(row)>1 else None,'status':row[2] if len(row)>2 else None})
    plain=record['text'];address=re.search(r'כתובת:\s*([^\r\n]+)',plain)
    return {'file_number':int(record['id']),'address':address.group(1).strip() if address else None,
            'parcels':list({(p['gush'],p['parcel']):(p) for p in parcels}.values()),
            'requests':sorted(set(requests)),'plans':plans,'tables':tables,'source':record['source'],
            'retrieved_at':utcnow(),'source_html_sha256':hashlib.sha256(record['html'].encode()).hexdigest()}

class ArchiveCatalogSync:
    def __init__(self,store,client=None):self.store=store;self.archive=BuildingArchive(client or PublicClient())
    def seed_streets(self):
        catalog=self.archive.streets();existing={x['id'] for x in self.store.archive_streets()}
        for street in catalog['streets']:
            if street['code'] not in existing:self.store.save_archive_street(street['code'],street['name'])
        return len(catalog['streets'])
    def discover(self,max_streets=None):
        total=self.seed_streets();rows=self.store.archive_streets('pending',max_streets);completed=failed=attempted=0
        for row in rows:
            attempted+=1
            try:
                result=self.archive.search_address(row['id'])
                for number in result['ids']:
                    self.store.save_archive_file(number,{'discovered_on_streets':[{'code':row['id'],'name':row['name']}],'discovery_source':result['source']})
                self.store.save_archive_street(row['id'],row['name'],'complete',len(result['ids']),payload={'source':result['source'],'declared_count':result['declared_count']});completed+=1
            except Exception as exc:
                self.store.save_archive_street(row['id'],row['name'],'failed',error=str(exc));failed+=1
                if '429' in str(exc):break
        return {'catalog_streets':total,'processed':attempted,'completed':completed,'failed':failed,**self.store.archive_status()}
    def retry_failed_streets(self):
        for row in self.store.archive_streets('failed'):
            self.store.save_archive_street(row['id'],row['name'],'pending')
    def hydrate(self,max_files=None):
        rows=self.store.pending_archive_files(max_files);completed=failed=attempted=0
        for row in rows:
            attempted+=1
            try:
                record=self.archive.file(row['id']);payload=parse_building_file(record)
                previous=row['payload'];payload['discovered_on_streets']=previous.get('discovered_on_streets',[])
                self.store.save_archive_file(row['id'],payload,'metadata_complete');completed+=1
            except Exception as exc:
                payload=dict(row['payload']);payload['last_error']=str(exc);payload['last_attempt_at']=utcnow()
                self.store.save_archive_file(row['id'],payload,'metadata_failed');failed+=1
                if '429' in str(exc):break
        return {'processed':attempted,'completed':completed,'failed':failed,**self.store.archive_status()}
