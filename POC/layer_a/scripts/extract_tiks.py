"""חילוץ עובדות מעמודי תיק. שמות מבקשים אינם נשמרים."""
import re,json,glob,os,sys
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _paths import RAW, DATA
D=str(RAW)+'/'
C=str(RAW)+'/'
TAG=re.compile(r'<[^>]+>')
REQ=re.compile(r'^(19|20)\d{6}$')
STRENGTH=re.compile(r'תמ["״]?א\s*38|חיזוק|רעידות אדמה')
def txt(x): return TAG.sub('',x).strip()
def parse(path):
    s=open(path,encoding='utf-8',errors='ignore').read()
    tik=os.path.basename(path)[:-5]
    gush=parcel=None
    m=re.search(r'מספר גוש.*?</tr>\s*<tr>(.*?)</tr>',s,re.S)
    reqs=[]
    for t in re.findall(r'<tr>(.*?)</tr>',s,re.S):
        tds=[txt(x) for x in re.findall(r'<td[^>]*>(.*?)</td>',t,re.S)]
        # שורת בקשה: [_, מס' בקשה, הוגש, פעולה, *שם מבקש*, מס' היתר, תאריך היתר, _]
        for i,v in enumerate(tds):
            if REQ.match(v or ''):
                reqs.append(dict(req=int(v),
                    submitted=tds[i+1] if len(tds)>i+1 else None,
                    action=tds[i+2] if len(tds)>i+2 else None,
                    permit=tds[i+4] if len(tds)>i+4 else None,
                    permit_date=tds[i+5] if len(tds)>i+5 else None))
                break            # השם בעמודה i+3 — לא נלקח
        if len(tds)>=2 and tds[0].isdigit() and tds[1].isdigit() and gush is None:
            gush,parcel=tds[0],tds[1]
    if not reqs: return None
    yrs=[int(str(r['req'])[:4]) for r in reqs]
    acts=' '.join((r['action'] or '') for r in reqs)
    return dict(tik=tik,gush=gush,parcel=parcel,
        n_requests=len(reqs),
        earliest_year=min(yrs), latest_year=max(yrs),
        pre1980=min(yrs)<1980,
        post2005=[r['req'] for r in reqs if r['req']>=20050000],
        strengthening_hit=bool(STRENGTH.search(acts)),
        requests=[{k:v for k,v in r.items()} for r in reqs])
if __name__=='__main__':
    out=[]
    for f in sorted(glob.glob(C+'tik/*.html')):
        try:
            r=parse(f)
            if r: out.append(r)
        except Exception as e: print('skip',f,e,file=sys.stderr)
    json.dump(out,open(str(DATA)+'/tiks_parsed.json','w'),ensure_ascii=False)
    print(f"תיקים שנותחו: {len(out)}")
    print(f"  עוברים שער 1980: {sum(1 for x in out if x['pre1980'])}")
    print(f"  נקיים מבקשה אחרי 2005: {sum(1 for x in out if x['pre1980'] and not x['post2005'])}")
