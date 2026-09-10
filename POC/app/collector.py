import hashlib,json,re,random
from shapely.geometry import shape,mapping
from .sources import PublicClient,GovMap,ArcGIS,public_buildings,SourceError,GIS_PAGE,GIS_CONFIG,utcnow
from .config import MAX_AREA_M2,MAX_RADIUS_M,MAX_BUILDINGS,MAX_PARCELS,RULE_VERSION,TEMPLATE_VERSION,POLICY_URL
from .geo import validate_polygon,circle_polygon,match_parcels,wgs,center_selected
from .rules import evidence,evaluate,resolve_evidence,eligibility_status
from .documents import archive_tables
from .xplan import XPlanCatalog,XPlanScreen,combine_screenings,resolve_with_archive,snapshot_is_fresh
from .archive_catalog import archive_designation

MISSING_FIELDS=['units','floors','permit_date','strengthened','engineer_opinion','residential_zoning','residential_share','scope_parcels','scope_buildings','renewal_policy_category','planning_lot','planning_basis','overriding_plans_checked','existing_legal_area']

def randomized_order(buildings,seed):
    ordered=sorted(buildings,key=lambda x:str(x['id']))
    random.Random(seed).shuffle(ordered)
    return ordered

def make_dossier(building,parcels,archive,filters,issues,documents=None,xplan_screening=None):
    geom=shape(building['geometry']);matches=match_parcels(geom,parcels)
    fields={key:evidence(None) for key in MISSING_FIELDS}
    source=building['_source']; tags=building['properties']
    fields['footprint_area']=evidence(round(geom.area,2),source,'community' if building.get('authority')=='community' else 'derived','feature '+building['id'],'ITM polygon area')
    fields['address']=evidence(' '.join(str(tags.get(k,'')) for k in ['addr:street','addr:housenumber']).strip() or None,source,'community','OSM address tags','structured')
    gaps=[];keys=[];parcel_rows=[]
    for overlap,p in matches:
        props=p['properties']; key=f"parcel:{props['GUSH_NUM']}:{props.get('GUSH_SUFFI',0)}:{props['PARCEL']}"
        keys.append(key);parcel_rows.append({'id':key,'gush':props['GUSH_NUM'],'suffix':props.get('GUSH_SUFFI',0),'parcel':props['PARCEL'],'overlap':round(overlap,4),'geometry':wgs(shape(p['geometry'])),'source':p['_source']})
    if len(matches)==1 and matches[0][0]>=.95:
        p=matches[0][1];value=p['properties'].get('LEGAL_AREA');sourcep=dict(p['_source'],source_updated_at=p['properties'].get('SYS_DATE'))
        fields['parcel_area']=evidence(value if value and value>0 else round(shape(p['geometry']).area,2),sourcep,'official' if value and value>0 else 'derived',p['id']+'.LEGAL_AREA' if value and value>0 else p['id']+'.geometry','WFS' if value and value>0 else 'ITM area')
    else:
        fields['parcel_area']=evidence(None)
        gaps.append('שיוך המבנה לחלקה אינו חד־משמעי' if matches else 'לא נמצאה חלקה למבנה')
    if matches:
        parcel_sources=[p['_source'] for _,p in matches]
        fields['scope_parcels']=evidence(len(matches),parcel_sources[0],'derived','building footprint / GovMap parcel intersection','local spatial join')
    archive_records=[];addresses=[]
    for record in archive:
        tables=record.get('tables') or archive_tables(record.get('html',''))
        archive_records.append({'id':record['id'],'source':record['source'],'tables':tables})
        # Only a precise archive label yields an official address. Never treat permit-list dates as construction dates.
        address=re.search(r'כתובת:\s*([^\r\n]+)',record['text'])
        if address and len(matches)==1:
            candidate=address.group(1).strip()
            addresses.append(evidence(candidate,record['source'],'official','building file header: כתובת (parcel-linked file; building identity unverified)','HTML label extraction'))
    if addresses:fields['address']=resolve_evidence(addresses)
    if fields['address']['certainty']=='conflict':gaps.append('כתובות שונות בתיקי הארכיון; שיוך המבנה דורש אימות')
    checks=evaluate(fields,filters)
    eligibility=eligibility_status(checks)
    gaps+= [c['label'] for c in checks if c['status']=='unknown']
    gaps+=['מספר דירות קיים ושטחים חוקיים לא אומתו מתוך היתר','טרם הוגדרו הנחות כלכליות מאושרות ושלמות']
    if building.get('authority')=='community':gaps.append('גבול המבנה ממקור קהילתי; נדרש אימות מול מקור עירוני')
    if xplan_screening and not xplan_screening.get('queue_eligible',True):
        status='screened_out';eligibility=xplan_screening['category']
    else:status='rejected' if eligibility=='ineligible' else 'needs_verification'
    d={'building_id':building['id'],'entity_keys':keys,'status':status,'eligibility_status':eligibility,'fields':fields,'geometry':wgs(geom),'parcels':parcel_rows,
       'checks':checks,'gaps':list(dict.fromkeys(gaps)),'source_issues':issues,'archive_records':archive_records,
       'documents':documents or [],'scenario':None,'rule_version':RULE_VERSION,'template_version':TEMPLATE_VERSION,
       'xplan_screening':xplan_screening or {'category':'needs_verification','tags':['needs_verification'],'queue_eligible':True,'warnings':['XPlan טרם נבדק']},
       'policy_source':POLICY_URL,'created_at':utcnow(),'building_source':building['_source'],
       'selection_note':'המועמד נבחר בסדר אקראי ניתן לשחזור; מרכז המבנה בתוך מעגל החיפוש. חלקה אינה מגרש תכנוני.'}
    stable=dict(d);stable.pop('created_at');d['id']=hashlib.sha256(json.dumps(stable,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
    return d

class Collector:
    def __init__(self,store,client=None):self.store=store;self.client=client or PublicClient()
    def run(self,jid):
        job=self.store.job(jid);request=job['request'];result=job['result'];issues=result.get('issues',[])
        try:
            self.store.update(jid,'running',5,result)
            gov=GovMap(self.client);boundary=gov.boundary()
            if request.get('center'):
                polygon=circle_polygon(request['center'],request['radius_m'],shape(boundary['geometry']),MAX_RADIUS_M,MAX_AREA_M2)
                polygon_wgs=wgs(polygon)
                result['selection']={'type':'circle','center':request['center'],'radius_m':request['radius_m'],'polygon':polygon_wgs}
            else:
                polygon=validate_polygon(request['polygon'],shape(boundary['geometry']),MAX_AREA_M2)
                polygon_wgs=request['polygon']
                result['selection']={'type':'legacy_polygon','polygon':polygon_wgs}
            parcels=gov.parcels(polygon,MAX_PARCELS)
            for p in parcels:self.store.entity(p,'cadastral_parcel')
            screener=None
            try:
                snapshot=self.store.latest_xplan_snapshot()
                if not snapshot_is_fresh(snapshot):
                    snapshot=XPlanCatalog().download(boundary);self.store.save_xplan_snapshot(snapshot)
                screener=XPlanScreen(snapshot)
                result['xplan_snapshot_id']=snapshot['id']
            except Exception as exc:
                issues.append({'source':'xplan','message':str(exc),'fallback':'החלקות נשארו בתור כדרושות אימות; לא בוצע סינון שלילי'})
            self.store.update(jid,'running',15,result)
            try:
                self.client.get(GIS_PAGE)
                config,_=self.client.json(GIS_CONFIG,headers={'X-Requested-With':'XMLHttpRequest','Referer':GIS_PAGE})
                service=ArcGIS(self.client,config['value']['layerUrl1'])
                layer,schema=service.discover(r'^בניינים$|^מבנים$')
                buildings=service.features(layer,schema,polygon,MAX_BUILDINGS)
                for b in buildings:b['id']='municipal:'+str(b['id']);b['authority']='official'
                buildings=[b for b in buildings if center_selected(shape(b['geometry']),polygon)]
            except Exception as exc:
                issues.append({'source':'municipal_buildings','message':str(exc),'fallback':'OpenStreetMap community footprints'})
                buildings=public_buildings(self.client,polygon_wgs,MAX_BUILDINGS)
            buildings=randomized_order(buildings,request.get('selection_seed',0))
            result['building_count']=len(buildings); result['parcel_count']=len(parcels);result['issues']=issues
            result['coverage']={'complete':True,'selected_buildings':len(buildings),'processed_buildings':len(result['candidates']),'selection_rule':'building centroid covered by radius circle'}
            self.store.update(jid,'running',25,result)
            done={d['building_id'] for d in result['candidates']};catalog_status=self.store.archive_status()
            selected=[d for d in result['candidates'] if d.get('eligibility_status')=='eligible'][:3]
            for index,building in enumerate(buildings):
                if len(selected)>=3:break
                if building['id'] in done:continue
                self.store.entity(building,'building');records=[];local_issues=[];docs=[]
                matches=match_parcels(shape(building['geometry']),parcels)
                screenings=[]
                if screener:
                    for _,parcel in matches:
                        screening=screener.screen(parcel,scope_parcels=len(matches),scope_buildings=None)
                        self.store.save_parcel_screening(screening);screenings.append(screening)
                xplan=combine_screenings(screenings,len(matches),None)
                pairs=[(p['properties']['GUSH_NUM'],p['properties']['PARCEL']) for _,p in matches]
                archive_payloads=self.store.archive_files_for_parcels(pairs) if pairs else []
                xplan=resolve_with_archive(xplan,archive_payloads,archive_designation)
                if 'archive_resolved_995' in xplan['tags']:result['archive_resolved_995']=result.get('archive_resolved_995',0)+1
                result.setdefault('xplan_categories',{})[xplan['category']]=result.setdefault('xplan_categories',{}).get(xplan['category'],0)+1
                if not xplan['queue_eligible']:
                    d=make_dossier(building,parcels,[],request['filters'],[],[],xplan)
                    d['selection_note']='המבנה נשמר במאגר אך אינו נכנס לתור תיקי הבניין וה־OCR לפי סיווג XPlan.'
                    d['selection_attempt']=len(result['candidates'])+1
                    self.store.save_dossier(d);result['candidates'].append(d)
                    result['estimated_document_pipelines_avoided']=result.get('estimated_document_pipelines_avoided',0)+1
                    result['coverage']['processed_buildings']=len(result['candidates'])
                    self.store.update(jid,'running',25+int(65*(index+1)/max(1,len(buildings))),result)
                    continue
                if matches:
                    for payload in archive_payloads:
                        records.append({'id':str(payload['file_number']),'source':payload['source'],
                                        'text':'כתובת: '+(payload.get('address') or ''),'html':'','tables':payload.get('tables',[])})
                    if not records:
                        local_issues.append({'source':'local_archive_catalog','message':'No hydrated building file is linked to these parcels yet'})
                if not catalog_status['coverage_complete']:
                    local_issues.append({'source':'local_archive_catalog','message':'The citywide archive catalog is still incomplete; absence is not evidence that no file exists'})
                d=make_dossier(building,parcels,records,request['filters'],local_issues,docs,xplan)
                d['selection_attempt']=len(result['candidates'])+1
                self.store.save_dossier(d);result['candidates'].append(d)
                if d['eligibility_status']=='eligible':selected.append(d)
                result['presented']=[x['id'] for x in selected]
                result['presented_candidates']=selected
                result['selection_seed']=request.get('selection_seed',0)
                self.store.update(jid,'running',25+int(65*(index+1)/max(1,len(buildings))),result)
                result['coverage']['processed_buildings']=len(result['candidates'])
            processed_ids=done|{d['building_id'] for d in result['candidates']}
            result['coverage']['pipeline_exhausted']=len(processed_ids)>=len(buildings)
            result['coverage']['unprocessed_buildings']=max(0,len(buildings)-len(processed_ids))
            result['stop_reason']='three_eligible' if len(selected)>=3 else 'radius_exhausted'
            result['delivered']=self.store.deliver(selected)
            result['summary']={'ready':sum(d['status']=='ready' for d in result['candidates']),
                'eligible':sum(d.get('eligibility_status')=='eligible' for d in result['candidates']),
                'needs_verification':sum(d['status']=='needs_verification' for d in result['candidates']),
                'rejected':sum(d['status']=='rejected' for d in result['candidates']),
                'screened_out':sum(d['status']=='screened_out' for d in result['candidates']),
                'xplan_categories':result.get('xplan_categories',{}),
                'estimated_document_pipelines_avoided':result.get('estimated_document_pipelines_avoided',0)}
            self.store.update(jid,'completed',100,result)
        except Exception as exc:
            self.store.update(jid,'failed',job['progress'],result,str(exc))
