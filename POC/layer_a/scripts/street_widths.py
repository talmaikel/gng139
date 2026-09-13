import json,math,statistics,sys
from shapely.geometry import shape,Point,LineString
from shapely.strtree import STRtree
from shapely.prepared import prep
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from _paths import RAW, DATA
C=str(RAW)+'/'
par=json.load(open(C+'parcels.json'))
sv=[s['key'] for s in json.load(open(str(DATA)+'/survivors.json'))]
PLOTS=[];  
for k,ft in par.items():
    try: g=shape(ft['geometry'])
    except Exception: continue
    if not g.is_valid or g.area<=0: continue
    A,P=g.area,g.length
    if P<=0: continue
    if 4*math.pi*A/(P*P)>=0.22 and A>=120:      # מגרש, לא רצועת דרך
        PLOTS.append(g)
tree=STRtree(PLOTS)
print(f"מגרשים (לא רצועות): {len(PLOTS):,} מתוך {len(par):,}",flush=True)
def width(g):
    b=g.boundary
    if b.geom_type!='LineString':
        b=max(b.geoms,key=lambda x:x.length)
    L=b.length
    if L<=0: return None
    pg=prep(g); hits=[]
    N=160
    for i in range(N):
        d=L*i/N
        pt=b.interpolate(d); p2=b.interpolate(min(d+0.4,L))
        dx,dy=p2.x-pt.x,p2.y-pt.y; m=math.hypot(dx,dy)
        if m==0: hits.append(None); continue
        nx,ny=dy/m,-dx/m
        if pg.contains(Point(pt.x+nx*0.3,pt.y+ny*0.3)): nx,ny=-nx,-ny
        ray=LineString([(pt.x+nx*0.15,pt.y+ny*0.15),(pt.x+nx*55,pt.y+ny*55)])
        best=None
        for j in tree.query(ray):
            o=PLOTS[j]
            if o.equals(g): continue
            it=ray.intersection(o)
            if it.is_empty: continue
            dd=pt.distance(it)
            if best is None or dd<best: best=dd
        hits.append(best)
    runs=[];cur=[]
    for v in hits:
        if v is not None and v>3: cur.append(v)
        else:
            if len(cur)>=6: runs.append(cur)
            cur=[]
    if len(cur)>=6: runs.append(cur)
    if not runs: return None
    ws=[statistics.median(r) for r in runs]
    return round(max(ws)-0.7,1)          # תיקון הטיה שנמדד על מנדלבלט
out={}
for i,k in enumerate(sv):
    if k not in par: continue
    try:
        g=shape(par[k]['geometry'])
        if g.is_valid: out[k]=width(g)
    except Exception: out[k]=None
    if (i+1)%100==0: print(f"  {i+1}/{len(sv)}",flush=True)
json.dump(out,open(str(DATA)+'/street_widths.json','w'))
ok=[v for v in out.values() if v]
print(f"\nנמדדו: {len(ok)} מתוך {len(sv)}")
