"""Public connectors. No guessed permit facts and no silent truncation."""
import hashlib, html, json, re, threading, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, quote, urljoin
import xml.etree.ElementTree as ET
import httpx
from shapely.geometry import shape, Polygon, mapping
from .config import DATA, CACHE_SECONDS, ARCHIVE_INTERVAL_SECONDS

WFS = 'https://open.govmap.gov.il/geoserver/opendata/wfs'
GIS_PAGE = 'https://v5.gis-net.co.il/v5/Hertzeliya?minisite=public'
GIS_CONFIG = 'https://v5.gis-net.co.il/V5/Hertzeliya/Data/GetMap?minisite=public'
ARCHIVE = 'https://handasi.complot.co.il/magicscripts/mgrqispi.dll'

def utcnow(): return datetime.now(timezone.utc).isoformat()

class SourceError(RuntimeError): pass

class PublicClient:
    def __init__(self, cache=None, transport=None):
        self.cache = Path(cache or DATA/'cache'); self.cache.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(timeout=35, follow_redirects=True, transport=transport,
            headers={'User-Agent':'ShakedPOC/0.1 public-data research'})
        self.lock = threading.Lock(); self.last = 0

    def get(self, url, params=None, ttl=CACHE_SECONDS, headers=None):
        # A single final URL also makes source references replayable.
        if params: url += ('' if url.endswith('?') else ('&' if '?' in url else '?')) + urlencode(params)
        key = hashlib.sha256(url.encode()).hexdigest()
        bodypath=self.cache/(key+'.bin'); metapath=self.cache/(key+'.json')
        if metapath.exists() and bodypath.exists():
            meta=json.loads(metapath.read_text(encoding='utf8'))
            if time.time()-meta['epoch'] < ttl:
                return bodypath.read_bytes(),meta
        error = None
        for attempt in range(3):
            with self.lock:
                interval=ARCHIVE_INTERVAL_SECONDS if 'handasi.complot.co.il' in url else .35
                time.sleep(max(0, interval - (time.monotonic()-self.last)))
                self.last=time.monotonic()
            try:
                r=self.client.get(url,headers=headers)
                if r.status_code in (429,502,503,504):
                    delay = r.headers.get('Retry-After','')
                    time.sleep(min(10,float(delay)) if delay.isdigit() else 2**attempt)
                    error=SourceError(f'HTTP {r.status_code}: {url}'); continue
                r.raise_for_status()
                if len(r.content)>25_000_000: raise SourceError('Source exceeds 25 MB limit')
                meta={'url':url,'retrieved_at':utcnow(),'epoch':time.time(),
                      'sha256':hashlib.sha256(r.content).hexdigest(),'content_type':r.headers.get('content-type','')}
                # atomic replacement permits recovery after interruption
                tmp=bodypath.with_suffix('.tmp'); tmp.write_bytes(r.content); tmp.replace(bodypath)
                tmp=metapath.with_suffix('.tmp'); tmp.write_text(json.dumps(meta),encoding='utf8'); tmp.replace(metapath)
                return r.content,meta
            except (httpx.TransportError,httpx.HTTPStatusError) as exc:
                error=SourceError(f'{type(exc).__name__}: {url}: {exc}')
                if isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code<500: break
                if attempt<2: time.sleep(2**attempt)
        raise error or SourceError(url)

    def json(self, url, params=None, **kwargs):
        body,meta=self.get(url,params,**kwargs)
        try: data=json.loads(body)
        except ValueError: raise SourceError(f'Expected JSON; source returned HTML or invalid data: {meta["url"]}')
        if isinstance(data,dict) and data.get('error'): raise SourceError(str(data['error']))
        return data,meta

    def post_json(self,url,payload,ttl=CACHE_SECONDS):
        encoded=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        key=hashlib.sha256(('POST '+url+' '+encoded).encode()).hexdigest()
        bodypath=self.cache/(key+'.bin');metapath=self.cache/(key+'.json')
        if metapath.exists() and bodypath.exists():
            meta=json.loads(metapath.read_text(encoding='utf8'))
            if time.time()-meta['epoch'] < ttl:
                return json.loads(bodypath.read_bytes()),meta
        error=None
        for attempt in range(3):
            with self.lock:
                interval=ARCHIVE_INTERVAL_SECONDS if 'handasi.complot.co.il' in url else .35
                time.sleep(max(0,interval-(time.monotonic()-self.last)));self.last=time.monotonic()
            try:
                r=self.client.post(url,json=payload)
                if r.status_code in (429,502,503,504):
                    error=SourceError(f'HTTP {r.status_code}: {url}');time.sleep(2**attempt);continue
                r.raise_for_status();data=r.json()
                if isinstance(data,dict) and data.get('error'):raise SourceError(str(data['error']))
                meta={'url':url,'method':'POST','request':payload,'retrieved_at':utcnow(),'epoch':time.time(),
                      'sha256':hashlib.sha256(r.content).hexdigest(),'content_type':r.headers.get('content-type','')}
                tmp=bodypath.with_suffix('.tmp');tmp.write_bytes(r.content);tmp.replace(bodypath)
                tmp=metapath.with_suffix('.tmp');tmp.write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8');tmp.replace(metapath)
                return data,meta
            except (httpx.TransportError,httpx.HTTPStatusError,ValueError) as exc:
                error=SourceError(f'{type(exc).__name__}: {url}: {exc}')
                if attempt<2:time.sleep(2**attempt)
        raise error or SourceError(url)

class GovMap:
    def __init__(self,client): self.client=client
    def discover(self):
        raw,_=self.client.get(WFS,{'service':'WFS','request':'GetCapabilities'})
        root=ET.fromstring(raw)
        types=[e.text for e in root.findall('.//{*}FeatureType/{*}Name')]
        for required in ['opendata:muni_il','opendata:Parcels_ITM']:
            if required not in types: raise SourceError(f'Missing WFS layer: {required}')
        return types
    def schema(self,layer,required):
        data,_=self.client.json(WFS,dict(service='WFS',version='2.0.0',request='DescribeFeatureType',typeNames=layer,outputFormat='application/json'))
        names={p['name'] for p in data['featureTypes'][0]['properties']}
        if not set(required)<=names: raise SourceError(f'WFS schema changed: {layer}')
        return names
    def features(self,layer,cql,limit=300,page_size=100):
        result=[]; seen=set(); offset=0; meta=None
        while True:
            data,meta=self.client.json(WFS,dict(service='WFS',version='2.0.0',request='GetFeature',
                typeNames=layer,outputFormat='application/json',srsName='EPSG:2039',
                CQL_FILTER=cql,count=page_size,startIndex=offset))
            if data.get('type')!='FeatureCollection': raise SourceError('Invalid WFS feature response')
            batch=data['features']; total=data.get('numberMatched')
            for f in batch:
                if f['id'] in seen: raise SourceError('WFS repeated a feature; pagination may be incomplete')
                seen.add(f['id']); f['_source']=dict(meta); result.append(f)
            if len(result)>limit: raise SourceError(f'Parcel limit exceeded ({limit}); draw a smaller area')
            offset+=len(batch)
            if isinstance(total,int) and offset>=total: break
            if not batch:
                if isinstance(total,int) and offset<total: raise SourceError('WFS ended before advertised count')
                break
            if len(batch)<page_size and not isinstance(total,int): break
        return result
    def boundary(self):
        self.discover(); self.schema('opendata:muni_il',['CR_LAMAS','Muni_Heb'])
        rows=self.features('opendata:muni_il',"CR_LAMAS='6400'",10)
        if len(rows)!=1 or rows[0]['properties']['Muni_Heb']!='הרצליה': raise SourceError('Herzliya boundary not uniquely identified')
        return rows[0]
    def parcels(self,polygon,limit=300):
        self.schema('opendata:Parcels_ITM',['GUSH_NUM','GUSH_SUFFI','PARCEL','LEGAL_AREA','SYS_DATE'])
        bounds=','.join(str(round(x,3)) for x in polygon.bounds)
        return self.features('opendata:Parcels_ITM',f"BBOX(the_geom,{bounds},'EPSG:2039')",limit)

class ArcGIS:
    def __init__(self,client,base): self.client=client; self.base=base.rstrip('/')
    def url(self,suffix=''):
        # Only the service URL returned by the public application is proxied.
        target=self.base+suffix
        if urlsplit(target).hostname=='arcgis005':
            return 'https://v5.gis-net.co.il/proxy/proxy.ashx?'+target+'?'
        return target
    def discover(self,name_pattern):
        data,_=self.client.json(self.url(),{'f':'json'})
        candidates=[x for x in data.get('layers',[]) if re.search(name_pattern,x['name']) and x.get('subLayerIds') is None]
        if len(candidates)!=1: raise SourceError(f'Layer mapping ambiguous or unavailable: {name_pattern}')
        layer=candidates[0]
        schema,_=self.client.json(self.url('/'+str(layer['id'])),{'f':'json'})
        if schema.get('geometryType')!='esriGeometryPolygon': raise SourceError('Expected polygon layer')
        return layer,schema
    def features(self,layer,schema,polygon,limit=100):
        url=self.url('/'+str(layer['id'])+'/query')
        geometry=json.dumps({'rings':[list(polygon.exterior.coords)],'spatialReference':{'wkid':2039}})
        ids,_=self.client.json(url,dict(f='json',where='1=1',geometry=geometry,geometryType='esriGeometryPolygon',inSR=2039,spatialRel='esriSpatialRelIntersects',returnIdsOnly='true'))
        object_ids=ids.get('objectIds') or []
        if len(object_ids)>limit: raise SourceError('Building limit exceeded')
        output=[]; size=min(schema.get('maxRecordCount',100),100)
        for start in range(0,len(object_ids),size):
            selected=object_ids[start:start+size]
            data,meta=self.client.json(url,dict(f='geojson',objectIds=','.join(map(str,selected)),outFields='*',returnGeometry='true',outSR=2039))
            if len(data.get('features',[]))!=len(selected) or data.get('exceededTransferLimit'): raise SourceError('ArcGIS response truncated')
            for f in data['features']: f['_source']=meta
            output+=data['features']
        return output

def public_buildings(client,polygon_wgs,limit):
    minx,miny,maxx,maxy=shape(polygon_wgs).bounds
    query=f'[out:json][timeout:25];way["building"]({miny},{minx},{maxy},{maxx});out tags geom;'
    data,meta=client.json('https://overpass-api.de/api/interpreter',{'data':query})
    if data.get('remark'): raise SourceError(data['remark'])
    from .geo import itm,center_selected
    selected=[]; scope=itm(polygon_wgs)
    for element in data.get('elements',[]):
        coords=[(p['lon'],p['lat']) for p in element.get('geometry',[])]
        if len(coords)<4 or coords[0]!=coords[-1]: continue
        geom=itm(Polygon(coords))
        if not geom.is_valid or geom.area==0 or not center_selected(geom,scope): continue
        selected.append({'id':f'osm:way:{element["id"]}','geometry':mapping(geom),'properties':element.get('tags',{}),
            '_source':dict(meta,feature_url=f'https://www.openstreetmap.org/way/{element["id"]}',source_updated_at=data.get('osm3s',{}).get('timestamp_osm_base')),
            'authority':'community'})
    if len(selected)>limit: raise SourceError(f'Building limit exceeded ({limit}); draw a smaller area')
    return sorted(selected,key=lambda f:f['id'])

def text_from_html(raw):
    s=raw.decode('utf8',errors='replace') if isinstance(raw,bytes) else raw
    s=re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '',s,flags=re.S|re.I)
    return html.unescape(re.sub(r'<[^>]+>',' ',s))

class BuildingArchive:
    def __init__(self,client): self.client=client
    def search(self,gush,parcel):
        params=dict(appname='cixpa',prgname='GetTikimByGush',siteid=121,g=int(gush),h=int(parcel),m='',l='true',arguments='siteid,g,h,m,l')
        raw,meta=self.client.get(ARCHIVE,params)
        s=raw.decode('utf8',errors='replace')
        ids=sorted(set(re.findall(r'(?:getBuilding\s*\(\s*[\"\x27]?|#building/)(\d+)',s)))
        # Missing results and unexpected templates remain distinct.
        state='found' if ids else ('empty' if 'ERR_NO_RESULTS' in s or 'לא נמצאו' in s else 'unrecognized')
        return {'ids':ids,'status':state,'source':meta,'text':text_from_html(s)[:16000]}
    def streets(self):
        url='https://handasi.complot.co.il/wsComplotPublicData/ComplotPublicData.asmx/GetStreets'
        data,meta=self.client.post_json(url,{'site_id':'121'})
        rows=[{'code':str(x['v']),'name':x['label']} for x in data.get('d',[]) if str(x.get('k'))=='6400' and str(x.get('v','')).isdigit()]
        if not rows:raise SourceError('The municipal street catalog returned no Herzliya streets')
        unique={x['code']:x for x in rows}
        return {'streets':sorted(unique.values(),key=lambda x:(x['name'],x['code'])),'source':meta}
    def search_address(self,street_code):
        params=dict(appname='cixpa',prgname='GetTikimByAddress',siteid=121,c=6400,s=int(street_code),h='',l='false',arguments='siteid,c,s,h,l')
        raw,meta=self.client.get(ARCHIVE,params)
        s=raw.decode('utf8',errors='replace');plain=text_from_html(s)
        ids=sorted(set(re.findall(r'(?:getBuilding\s*\(\s*["\x27]?|#building/)(\d+)',s)),key=int)
        declared=re.search(r'נמצאו\s*(\d+)\s*תיקי\s*בניין',plain)
        if declared and int(declared.group(1))!=len(ids):
            raise SourceError(f'Archive street result is incomplete: declared {declared.group(1)}, parsed {len(ids)}')
        state='found' if ids else ('empty' if 'ERR_NO_RESULTS' in s or 'לא נמצאו' in plain else 'unrecognized')
        if state=='unrecognized':raise SourceError('Unrecognized municipal street-search response')
        return {'ids':ids,'declared_count':int(declared.group(1)) if declared else len(ids),'status':state,'source':meta}
    def file(self,tik):
        raw,meta=self.client.get(ARCHIVE,dict(appname='cixpa',prgname='GetTikFile',siteid=121,t=int(tik),arguments='siteid,t'))
        s=raw.decode('utf8',errors='replace')
        return {'id':str(tik),'source':meta,'text':text_from_html(s),'html':s}
    def documents(self,tik):
        raw,meta=self.client.get(ARCHIVE,dict(appname='cixpa',prgname='GetTikDocs',siteid=121,t=int(tik),arguments='siteid,t'))
        s=raw.decode('utf8',errors='replace')
        links=re.findall(r'href=["\x27]([^"\x27]+)',s,re.I)
        return {'source':meta,'links':[urljoin(ARCHIVE,html.unescape(x)) for x in links if '.pdf' in x.lower()], 'text':text_from_html(s)}
