"""Conservative policy screening. Passing these checks is not final eligibility."""
import hashlib,json
from datetime import datetime,timezone
from functools import cmp_to_key
from .config import POLICY_URL,RULE_VERSION,TEMPLATE_VERSION,SOURCE_MAX_AGE_DAYS

def evidence(value,source=None,certainty='missing',location=None,method=None):
    return {'value':value,'certainty':certainty,'source':source,'location':location,'method':method}

def resolve_evidence(observations):
    """Keep competing observations; a conflict never silently picks the last value."""
    present=[o for o in observations if o.get('value') is not None]
    if not present:return evidence(None)
    distinct={json.dumps(o['value'],sort_keys=True,ensure_ascii=False) for o in present}
    if len(distinct)>1:
        return dict(evidence(None,certainty='conflict'),observations=present)
    return dict(present[0],observations=present)

def usable(f):
    if not f or f['value'] is None or f['certainty'] not in ('official','derived','manually_verified'):return False
    source=f.get('source') or {}
    if not source.get('url') or not source.get('retrieved_at'): return False
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(source['retrieved_at'])).total_seconds()/86400
        return 0<=age<=SOURCE_MAX_AGE_DAYS and f.get('location') is not None
    except (ValueError,TypeError):return False

def evaluate(fields,filters):
    checks=[]
    def check(key,label,fn,page):
        field=fields.get(key)
        status='unknown' if not usable(field) else ('passed' if fn(field['value']) else 'failed')
        checks.append({'id':key,'label':label,'status':status,'source_url':POLICY_URL,'page':page,'field_evidence':field})
    check('residential_zoning','ייעוד הכולל מגורים',lambda x:x is True,3)
    check('residential_share','לפחות 70% שימוש חוקי למגורים',lambda x:x>=.7,3)
    # 1980–1984 requires a structural-engineer opinion; do not collapse to year <=1984.
    date=fields.get('permit_date'); opinion=fields.get('engineer_opinion')
    state='unknown'
    if usable(date):
        v=str(date['value'])
        if v<'1980-01-01':state='passed'
        elif v<='1984-12-31':state='passed' if usable(opinion) and opinion['value'] is True else 'unknown'
        else:state='failed'
    checks.append({'id':'permit_date','label':'מועד היתר וחוות דעת לפי הצורך','status':state,'source_url':POLICY_URL,'page':3})
    check('strengthened','לא חוזק בהיתר לפי תקן רעידות אדמה',lambda x:x is False,3)
    check('floors','לפחות שתי קומות לפי הגדרת המדיניות',lambda x:x>=2,3)
    check('units','לפחות ארבע דירות שנבנו בהיתר',lambda x:x>=4,3)
    check('scope_parcels','חלקת מגורים אחת או שתי חלקות לכל היותר',lambda x:1<=x<=2,2)
    check('scope_buildings','מבנה אחד או שני מבנים לכל היותר',lambda x:1<=x<=2,2)
    check('renewal_policy_category','מיקום באזור המאפשר התחדשות מגרשית',lambda x:x in (
        'התחדשות מגרשית מוטת מגורים','התחדשות עירונית מוטת מגורים נמוכה'),5)
    for key,label in [('planning_lot','זיהוי מגרש תכנוני'),('planning_basis','בסיס תכנוני מבוסס לתרחיש'),('overriding_plans_checked','בדיקת תכניות ומדיניות גוברות')]:
        check(key,label,lambda x:bool(x),2)
    for key,op,val in [('parcel_area','min',filters.get('min_parcel_area')),('units','max',filters.get('max_units')),('floors','max',filters.get('max_floors'))]:
        if val is None:continue
        f=fields.get(key)
        status='unknown' if not usable(f) else ('passed' if (f['value']>=val if op=='min' else f['value']<=val) else 'failed')
        checks.append({'id':'filter_'+key,'label':'תנאי חובה: '+key,'status':status})
    return checks

def eligibility_status(checks):
    if any(x['status']=='failed' for x in checks):return 'ineligible'
    if checks and all(x['status']=='passed' for x in checks):return 'eligible'
    return 'needs_verification'

def rank(candidates,preferences):
    def compare(a,b):
        for pref in preferences:
            def value(d):
                f=d['fields'].get(pref['field']);return f['value'] if usable(f) else None
            x,y=value(a),value(b)
            if x is None and y is None:continue
            if x is None:return 1
            if y is None:return -1
            if x!=y:return (1 if x>y else -1)*(1 if pref['direction']=='asc' else -1)
        return (a['id']>b['id'])-(a['id']<b['id'])
    return sorted(candidates,key=cmp_to_key(compare))

def economics(a):
    revenue=a['sale_area']*a['sale_price']
    construction=a['construction_area']*a['build_cost']
    costs=construction+a['tenant_rent']*a['rent_months']+sum(a[k] for k in ['consultants','finance','levies_taxes','parking','reserve','other_costs'])
    profit=revenue-costs
    if costs<=0:raise ValueError('Costs must be positive')
    return {'revenue':revenue,'costs':costs,'profit':profit,'profit_on_cost':profit/costs,
            'sensitivity':[{'sale_change':s,'build_change':b,'profit':revenue*(1+s)-costs-construction*b} for s in [-.1,0,.1] for b in [-.1,0,.1]]}
