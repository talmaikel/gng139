"""Cached citywide XPlan collection and conservative parcel screening."""
import hashlib
import json
import numbers
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .config import DATA, XPLAN_CACHE_SECONDS, XPLAN_OVERLAP_THRESHOLD, XPLAN_SPECIAL_OVERLAP_THRESHOLD, XPLAN_METRO_STATION_BUFFER_M
from .sources import PublicClient, SourceError, utcnow

BASE="https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer"
LAYERS={0:"points",1:"plans",3:"polygons",4:"landuse"}
PURE_RESIDENTIAL_CODES={10,20,60,100,140}
AMBIGUOUS_CODES={995,999}
# Layer 0 station markers. Layer 4 code 808 is Tama 70's citywide TOD zone and covers ~100% of parcels, so it cannot discriminate.
METRO_STATION_CODES={6006,6022,6023,6025}
APPROVED_INTERNET={"התכנית אושרה","פרסום אישור"}
QUEUE_CATEGORIES={"primary_candidate","needs_verification"}


class XPlanClient:
    """Use the normal HTTP client first and a bounded curl fallback for TLS compatibility."""
    def __init__(self,cache=None,transport=None,allow_curl=True):
        self.cache=Path(cache or DATA/"cache");self.cache.mkdir(parents=True,exist_ok=True)
        self.http=PublicClient(self.cache,transport=transport);self.allow_curl=allow_curl;self.http_unavailable=False

    def json(self,path,params,ttl=XPLAN_CACHE_SECONDS):
        url=BASE+path
        if self.http_unavailable and self.allow_curl:return self._curl_json(url,params,ttl,SourceError("normal HTTP transport unavailable"))
        try:return self.http.json(url,params,ttl=ttl)
        except SourceError as primary:
            if not self.allow_curl:raise
            self.http_unavailable=True
            return self._curl_json(url,params,ttl,primary)

    def _curl_json(self,url,params,ttl,primary):
        if urlsplit(url).hostname!="ags.iplan.gov.il" or not url.startswith(BASE):
            raise SourceError("XPlan curl fallback rejected a URL outside the allowlist")
        final=url+"?"+urlencode(params)
        key=hashlib.sha256(final.encode()).hexdigest();bodypath=self.cache/(key+".bin");metapath=self.cache/(key+".json")
        if bodypath.exists() and metapath.exists():
            meta=json.loads(metapath.read_text(encoding="utf-8"))
            if time.time()-meta["epoch"]<ttl:return json.loads(bodypath.read_bytes()),meta
        command=shutil.which("curl.exe") or shutil.which("curl")
        if not command:raise primary
        error=None
        for attempt in range(3):
            completed=subprocess.run([command,"--fail","--silent","--show-error","--max-time","60",final],capture_output=True,check=False)
            if completed.returncode==0:
                if len(completed.stdout)>25_000_000:raise SourceError("XPlan response exceeds 25 MB")
                try:data=json.loads(completed.stdout)
                except ValueError as exc:raise SourceError("XPlan returned invalid JSON") from exc
                if isinstance(data,dict) and data.get("error"):raise SourceError(str(data["error"]))
                meta={"url":final,"retrieved_at":utcnow(),"epoch":time.time(),"sha256":hashlib.sha256(completed.stdout).hexdigest(),"content_type":"application/json","transport":"curl"}
                tmp=bodypath.with_suffix(".tmp");tmp.write_bytes(completed.stdout);tmp.replace(bodypath)
                tmp=metapath.with_suffix(".tmp");tmp.write_text(json.dumps(meta,ensure_ascii=False),encoding="utf-8");tmp.replace(metapath)
                return data,meta
            error=completed.stderr.decode("utf-8",errors="replace").strip();time.sleep(2**attempt)
        raise SourceError(f"XPlan curl fallback failed after normal HTTP failure: {error}")


class XPlanCatalog:
    REQUIRED={
        0:{"objectid","pl_id","pl_number","mavat_code","mavat_name","station_desc"},
        1:{"objectid","pl_id","pl_number","pl_name","station_desc","internet_short_status","entity_subtype_desc","plan_charactor_name","pl_objectives"},
        3:{"objectid","pl_id","pl_number","mavat_code","mavat_name","station_desc"},
        4:{"objectid","pl_id","pl_number","mavat_code","mavat_name","station_desc","last_update_date"},
    }
    FIELDS={
        0:"objectid,pl_id,pl_number,pl_name,mavat_code,mavat_name,station_desc,last_update_date",
        1:"objectid,pl_id,pl_number,pl_name,station_desc,internet_short_status,entity_subtype_desc,plan_charactor_name,pl_url,pl_objectives,pl_date_8,last_update_date",
        3:"objectid,pl_id,pl_number,pl_name,mavat_code,mavat_name,station_desc,last_update_date",
        4:"objectid,pl_id,pl_number,pl_name,mavat_code,mavat_name,station_desc,last_update_date,legal_area,num,layer_id,group_id",
    }
    def __init__(self,client=None):self.client=client or XPlanClient()
    def validate(self):
        service,_=self.client.json("",{"f":"json"})
        ids={x["id"] for x in service.get("layers",[])}
        if not set(LAYERS)<=ids:raise SourceError("Required XPlan layers are missing")
        for layer,required in self.REQUIRED.items():
            meta,_=self.client.json(f"/{layer}",{"f":"json"})
            names={x["name"] for x in meta.get("fields",[])}
            if not required<=names:raise SourceError(f"XPlan layer {layer} schema changed: {sorted(required-names)}")
            if "Query" not in (meta.get("capabilities") or ""):raise SourceError(f"XPlan layer {layer} is not queryable")
        return service
    def _ids(self,layer,bounds):
        envelope=",".join(str(round(x,3)) for x in bounds)
        data,meta=self.client.json(f"/{layer}/query",{"f":"json","where":"1=1","geometry":envelope,"geometryType":"esriGeometryEnvelope","inSR":2039,"spatialRel":"esriSpatialRelIntersects","returnIdsOnly":"true"})
        ids=sorted(set(data.get("objectIds") or []))
        return ids,meta
    def _features(self,layer,ids,chunk_size=150):
        output=[];sources=[]
        for start in range(0,len(ids),chunk_size):
            selected=ids[start:start+chunk_size]
            data,meta=self.client.json(f"/{layer}/query",{"f":"geojson","objectIds":",".join(map(str,selected)),"outFields":self.FIELDS[layer],"returnGeometry":"true","outSR":2039})
            batch=data.get("features") or []
            if data.get("exceededTransferLimit") or len(batch)!=len(selected):raise SourceError(f"XPlan layer {layer} response was truncated")
            output.extend(batch);sources.append(meta)
        seen=[str(x.get("properties",{}).get("objectid")) for x in output]
        if len(seen)!=len(set(seen)):raise SourceError(f"XPlan layer {layer} returned duplicate object IDs")
        return output,sources
    def download(self,boundary):
        self.validate();boundary_geom=shape(boundary["geometry"] if boundary.get("type")=="Feature" else boundary)
        layers={};sources=[]
        for layer,name in LAYERS.items():
            ids,id_source=self._ids(layer,boundary_geom.bounds);features,batch_sources=self._features(layer,ids)
            # The API query uses a bounding envelope; retain only exact city intersections.
            exact=[f for f in features if f.get("geometry") and shape(f["geometry"]).intersects(boundary_geom)]
            layers[name]=exact;sources.append({"layer":layer,"ids":id_source,"batches":batch_sources,"advertised_ids":len(ids),"retained":len(exact)})
        stable={"layers":layers,"sources":sources,"boundary_source":boundary.get("_source") or boundary.get("properties",{}).get("source")}
        snapshot={**stable,"created_at":utcnow(),"cache_seconds":XPLAN_CACHE_SECONDS}
        snapshot["id"]=hashlib.sha256(json.dumps(stable,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
        return snapshot


def _props(feature):return feature.get("properties") or feature.get("attributes") or {}
def _key(value):return str(value) if value is not None else None


class XPlanScreen:
    def __init__(self,snapshot):
        self.snapshot=snapshot
        plans=snapshot.get("layers",{}).get("plans",[])
        self.plans_by_id={_key(_props(x).get("pl_id")):x for x in plans if _props(x).get("pl_id") is not None}
        self.plans_by_number={_key(_props(x).get("pl_number")):x for x in plans if _props(x).get("pl_number")}
        self.indexes={name:self._index(snapshot.get("layers",{}).get(name,[])) for name in ("landuse","points","polygons","plans")}
        self.stations=[(f,shape(f["geometry"])) for f in snapshot.get("layers",{}).get("points",[])
                       if f.get("geometry") and _props(f).get("mavat_code") in METRO_STATION_CODES and self._approved(f)]
        self.station_zone=unary_union([g.buffer(XPLAN_METRO_STATION_BUFFER_M) for _,g in self.stations]) if self.stations else None
    @staticmethod
    def _index(features):
        rows=[f for f in features if f.get("geometry")];geoms=[shape(f["geometry"]) for f in rows]
        return rows,geoms,STRtree(geoms) if geoms else None,{g.wkb:i for i,g in enumerate(geoms)}
    def _hits(self,name,geom):
        rows,geoms,tree,by_wkb=self.indexes[name]
        if not tree:return []
        found=[]
        for hit in tree.query(geom):
            index=int(hit) if isinstance(hit,numbers.Integral) else by_wkb.get(hit.wkb)
            if index is not None and geoms[index].intersects(geom):found.append((rows[index],geoms[index]))
        return found
    def _plan(self,feature):
        p=_props(feature)
        return self.plans_by_id.get(_key(p.get("pl_id"))) or self.plans_by_number.get(_key(p.get("pl_number")))
    def _approved(self,feature):
        plan=self._plan(feature);p=_props(plan) if plan else _props(feature)
        internet=(p.get("internet_short_status") or "").strip()
        return internet in APPROVED_INTERNET if internet else (p.get("station_desc") or "").strip()=="אישור"
    def _permit_local(self,feature):
        plan=self._plan(feature)
        if not plan:return False
        p=_props(plan);kind=p.get("entity_subtype_desc") or "";character=p.get("plan_charactor_name") or ""
        return ("מקומית" in kind or "מפורטת" in kind) and "שמכוחה ניתן" in character and "לא ניתן" not in character
    def screen(self,parcel,scope_parcels=1,scope_buildings=None):
        geom=shape(parcel["geometry"]);area=geom.area
        if not area:raise ValueError("Parcel geometry has no area")
        evidence_rows=[];groups={}
        metro=False;preservation=False;renewal=False;warnings=[]
        for feature,fg in self._hits("landuse",geom):
            p=_props(feature);overlap=fg.intersection(geom).area/area;approved=self._approved(feature)
            row={"objectid":p.get("objectid"),"pl_id":p.get("pl_id"),"pl_number":p.get("pl_number"),"pl_name":p.get("pl_name"),"mavat_code":p.get("mavat_code"),"mavat_name":p.get("mavat_name"),"station_desc":p.get("station_desc"),"overlap":round(overlap,6),"approved":approved,
                 "source_url":f"{BASE}/4/{p.get('objectid')}","evidence_location":f"XPlan layer 4 objectid {p.get('objectid')}","certainty":"official","extraction_method":"ArcGIS REST spatial intersection"}
            evidence_rows.append(row)
            if not approved:
                warnings.append(f"תכנית {p.get('pl_number') or p.get('pl_id')} אינה מאושרת")
                continue
            if not self._permit_local(feature):continue
            code=int(p.get("mavat_code") or -1);name=(p.get("mavat_name") or "").strip()
            classification="ambiguous" if code in AMBIGUOUS_CODES or "מבוטל" in name else ("residential" if code in PURE_RESIDENTIAL_CODES else "non_residential")
            plan_key=_key(p.get("pl_id")) or _key(p.get("pl_number")) or "unknown"
            groups.setdefault((plan_key,classification),[]).append(fg.intersection(geom))
        coverages={}
        for (plan_key,classification),pieces in groups.items():
            coverages[(plan_key,classification)]=unary_union(pieces).area/area
        high_res=[x for x,v in coverages.items() if x[1]=="residential" and v>=XPLAN_OVERLAP_THRESHOLD]
        high_non=[x for x,v in coverages.items() if x[1]=="non_residential" and v>=XPLAN_OVERLAP_THRESHOLD]
        high_amb=[x for x,v in coverages.items() if x[1]=="ambiguous" and v>=XPLAN_OVERLAP_THRESHOLD]
        for name in ("points","polygons"):
            for feature,fg in self._hits(name,geom):
                p=_props(feature);plan=self._plan(feature);text=" ".join(str(x or "") for x in (p.get("mavat_name"),_props(plan).get("entity_subtype_desc") if plan else None,_props(plan).get("pl_name") if plan else None))
                overlap=1.0 if fg.geom_type=="Point" and geom.covers(fg) else (fg.intersection(geom).area/area if fg.geom_type!="Point" else 0)
                if self._approved(feature) and "שימור" in text and overlap>=XPLAN_SPECIAL_OVERLAP_THRESHOLD:preservation=True
        metro_stations=[]
        if self.station_zone is not None and geom.intersects(self.station_zone):
            metro=True
            for feature,sg in self.stations:
                distance=geom.distance(sg)
                if distance<=XPLAN_METRO_STATION_BUFFER_M:
                    p=_props(feature)
                    metro_stations.append({"objectid":p.get("objectid"),"pl_number":p.get("pl_number"),"mavat_code":p.get("mavat_code"),"mavat_name":p.get("mavat_name"),
                                           "distance_m":round(distance,1),"source_url":f"{BASE}/0/{p.get('objectid')}","evidence_location":f"XPlan layer 0 objectid {p.get('objectid')}"})
        for feature,fg in self._hits("plans",geom):
            p=_props(feature);text=" ".join(str(p.get(x) or "") for x in ("pl_name","pl_objectives"));status=p.get("internet_short_status") or ""
            advanced=status in APPROVED_INTERNET or "הפקדה" in status or "הכרעה בהתנגדויות" in (p.get("station_desc") or "")
            if advanced and ("התחדשות" in text or "פינוי" in text and "בינוי" in text):renewal=True
        tags=[]
        if preservation:tags.append("preservation")
        if renewal:tags.append("existing_renewal_plan")
        if metro:tags.append("metro")
        if scope_parcels>2 or (scope_buildings is not None and scope_buildings>2):tags.append("urban_renewal_compound")
        if high_res and high_non:
            land_category="needs_verification";warnings.append("תכניות מקומיות מאושרות מחזירות ייעודי קרקע סותרים")
        elif high_non:land_category="filtered_landuse"
        elif high_res and not high_amb:land_category="primary_candidate"
        else:land_category="needs_verification"
        priority=["preservation","existing_renewal_plan","metro","urban_renewal_compound"]
        category=next((x for x in priority if x in tags),land_category)
        # Code 995 defers to plans that are mostly absent from XPlan; flag it so archive metadata can resolve it.
        ambiguous_only=land_category=="needs_verification" and bool(high_amb) and not high_res and not high_non
        if land_category=="filtered_landuse" and not tags:tags.append("filtered_landuse")
        if land_category=="needs_verification" and not tags:tags.append("needs_verification")
        if land_category=="primary_candidate" and not tags:tags.append("primary_candidate")
        props=parcel.get("properties",{});parcel_key=f"parcel:{props.get('GUSH_NUM')}:{props.get('GUSH_SUFFI',0)}:{props.get('PARCEL')}"
        return {"parcel_key":parcel_key,"snapshot_id":self.snapshot["id"],"category":category,"tags":tags,"queue_eligible":category in QUEUE_CATEGORIES,
                "landuse_category":land_category,"ambiguous_only":ambiguous_only,"threshold":XPLAN_OVERLAP_THRESHOLD,"special_threshold":XPLAN_SPECIAL_OVERLAP_THRESHOLD,
                "metro_station_buffer_m":XPLAN_METRO_STATION_BUFFER_M,"metro_stations":sorted(metro_stations,key=lambda x:x["distance_m"]),
                "matches":sorted(evidence_rows,key=lambda x:(str(x.get("pl_number")),str(x.get("objectid")))),"warnings":list(dict.fromkeys(warnings)),"screened_at":utcnow()}


def combine_screenings(screenings,scope_parcels,scope_buildings=None):
    if not screenings:return {"category":"needs_verification","tags":["needs_verification"],"queue_eligible":True,"warnings":["לא נמצא סיווג XPlan לחלקה"]}
    tags=list(dict.fromkeys(tag for row in screenings for tag in row.get("tags",[])))
    if scope_parcels>2 or (scope_buildings is not None and scope_buildings>2):tags.append("urban_renewal_compound")
    priority=["preservation","existing_renewal_plan","metro","urban_renewal_compound","filtered_landuse","needs_verification","primary_candidate"]
    category=next((x for x in priority if x in tags),"needs_verification")
    return {"category":category,"tags":list(dict.fromkeys(tags)),"queue_eligible":category in QUEUE_CATEGORIES,"parcels":screenings,
            "warnings":list(dict.fromkeys(w for row in screenings for w in row.get("warnings",[])))}


def resolve_with_archive(combined,archive_files,archive_designation):
    """Promote a 995-only result using the municipal archive's own designation; never demote on it."""
    parcels=combined.get("parcels") or []
    if not parcels or not all(p.get("ambiguous_only") for p in parcels):return combined
    evidence=[]
    for payload in archive_files:
        verdict=archive_designation(payload)
        if verdict["residential"] is None:continue
        evidence.append({"file_number":payload.get("file_number"),"address":payload.get("address"),"residential":verdict["residential"],"designations":verdict["designations"],
                         "basis":verdict["basis"],"mixed":verdict["mixed"],"source_url":(verdict["source"] or {}).get("url"),
                         "evidence_location":"טבלת גוש וחלקה בדף הבקשה" if verdict["basis"]=="permit_page" else "רשימת התכניות בדף תיק הבניין",
                         "certainty":"official","extraction_method":"structured public-page extraction"})
    if not evidence:return combined
    out=dict(combined);out["archive_resolution"]=evidence
    # Special routes (metro, preservation, renewal, compound) keep their category; the evidence is still attached.
    if combined["category"]!="needs_verification":return out
    if all(x["residential"] for x in evidence):
        out["category"]="primary_candidate";out["tags"]=list(dict.fromkeys(out["tags"]+["archive_resolved_995","primary_candidate"]));out["queue_eligible"]=True
        out["warnings"]=list(dict.fromkeys(out.get("warnings",[])+["ייעוד המגורים נקבע מדף הבקשה בארכיון העירוני; XPlan מפנה לתכנית מאושרת אחרת (קוד 995)"]))
        if any(x["mixed"] for x in evidence):out["warnings"].append("החלקה נושאת גם ייעוד שאינו מגורים (למשל רצועת דרך); היקפו דורש אימות")
    else:
        out["warnings"]=list(dict.fromkeys(out.get("warnings",[])+["דף הבקשה בארכיון מציין ייעוד שאינו מגורים; החלקה נשארת לאימות ולא נפסלה"]))
    return out


def snapshot_is_fresh(snapshot):
    try:return (datetime.now(timezone.utc)-datetime.fromisoformat(snapshot["created_at"])).total_seconds()<=XPLAN_CACHE_SECONDS
    except (KeyError,TypeError,ValueError):return False
