import json,glob,collections,numpy as np,pymupdf
from shapely.geometry import shape
from shapely.strtree import STRtree
from PIL import Image
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _paths import RAW, DATA
D=str(RAW)+'/'
C=str(RAW)+'/'
P=[];meta=[]
for k,ft in json.load(open(C+'parcels.json')).items():
    try: g=shape(ft['geometry'])
    except Exception: continue
    if g.is_valid and g.area>0:
        P.append(g); meta.append([k,ft['properties'].get('LEGAL_AREA') or g.area])
B=[];BA=[]
for f in glob.glob(C+'bld_*.json'):
    for ft in json.load(open(f)).get('features',[]):
        try: g=shape(ft['geometry'])
        except Exception: continue
        if g.is_valid and g.area>=5: B.append(g); BA.append(ft['properties'])
btree=STRtree(B)
def load(pat,keep):
    G=[]
    for f in glob.glob(C+pat):
        for ft in json.load(open(f)).get('features',[]):
            if not keep(ft['properties']): continue
            try: g=shape(ft['geometry'])
            except Exception: continue
            if g.is_valid and g.area>0: G.append(g)
    return G
CONS={'מבנה לשימור'}   # רק שימור ברמת מבנה פוסל; אזורי עתיקות/נוף הם סימון, לא פסילה
FLAG={'אתר/מתחם לשימור','שטח עתיקות/הסטורי לשימור','שימור נופי','אתר עתיקות/אתר הסטורי'}
cg=load('shim_*.json',lambda p:p.get('mavat_name') in CONS); ctree=STRtree(cg)
yg=load('yeud_*.json',lambda p:'מגורים' in (p.get('mavat_name') or '') and 'אישור' in (p.get('station_desc') or '')); ytree=STRtree(yg)
fg=load('shim_*.json',lambda p:p.get('mavat_name') in FLAG); ftree=STRtree(fg)
m=np.load(str(DATA)+'/policy_map_affine.npy'); M=np.array([[m[0],m[1]],[m[3],m[4]]]); t=np.array([m[2],m[5]]); Mi=np.linalg.inv(M)
pix=pymupdf.open(str(DATA)+'/strategic.pdf')[7].get_pixmap(matrix=pymupdf.Matrix(6,6))
img=Image.frombytes('RGB',(pix.width,pix.height),pix.samples); W,H=img.size
LEG={(230,230,0):'9',(255,255,190):'5.5',(255,255,189):'5.5',(250,250,207):'5.5',
     (181,53,53):'x',(230,152,0):'x',(156,156,156):'x',(243,237,211):'x',(255,255,255):'x'}
LK=list(LEG); LA=np.array(LK,dtype=float)
def classify(cx,cy):
    # דגימת דיסק ברדיוס 15 מ' + התאמה לצבע הקרוב ביותר, ואז רוב
    votes=collections.Counter()
    for dx in range(-15,16,5):
        for dy in range(-15,16,5):
            if dx*dx+dy*dy>225: continue
            q=Mi@(np.array([cx+dx,cy+dy])-t); jx,jy=int(q[0]*6),int(q[1]*6)
            if not (0<=jx<W and 0<=jy<H): continue
            c=np.array(img.getpixel((jx,jy)),dtype=float)
            d=np.abs(LA-c).sum(1)
            if d.min()<=45: votes[LEG[LK[int(d.argmin())]]]+=1
    if not votes: return None
    return votes.most_common(1)[0][0]
BAD={'הרוס','בבנייה'}
cnt=collections.Counter(); survivors=[]
for g,(key,legal) in zip(P,meta):
    cnt['0_חלקות']+=1
    bl=[(B[i],BA[i]) for i in btree.query(g) if B[i].intersection(g).area/B[i].area>0.5]
    if not bl: cnt['x_אין מבנה']+=1; continue
    cnt['1_יש מבנה']+=1
    if all((a.get('status') in BAD) for _,a in bl): cnt['x_הרוס/בבנייה']+=1; continue
    fl=[]
    for bg,a in bl:
        try: fl.append((bg.area,int(float(a.get('Num_floors')))))
        except (TypeError,ValueError): fl.append((bg.area,0))
    if max((f for _,f in fl),default=0)<2: cnt['x_פחות מ-2 קומות']+=1; continue
    cnt['2_קומות>=2']+=1
    gross=sum(ar*f for ar,f in fl)
    if gross<250: cnt['x_ברוטו<250']+=1; continue
    cnt['3_ברוטו>=250']+=1
    if any(cg[i].intersects(g) for i in ctree.query(g)): cnt['x_שימור']+=1; continue
    cnt['4_לא שימור']+=1
    c=g.centroid
    if not any(yg[i].contains(c) for i in ytree.query(c)): cnt['x_לא מגורים מאושר']+=1; continue
    cnt['5_מגורים מאושר']+=1
    cat=classify(c.x,c.y)
    if cat not in ('9','5.5'): cnt['x_מחוץ למסלול מגרשים']+=1; continue
    cnt['6_מסלול מגרשים']+=1
    flags=sorted({'עתיקות/שימור אזורי' for i in ftree.query(g) if fg[i].intersects(g)})
    survivors.append(dict(key=key,lot=round(legal),gross=round(gross),cat=cat,
                          floors=max(f for _,f in fl),nb=len(bl),
                          foot=round(sum(a for a,_ in fl)),flags=flags))
json.dump(survivors,open(str(DATA)+'/survivors.json','w'),ensure_ascii=False)
print("המשפך העירוני — כל השערים רצים בלי אף פנייה לארכיון\n")
prev=None
for k in sorted(k for k in cnt if not k.startswith('x')):
    v=cnt[k]; lbl=k.split('_',1)[1]
    d='' if prev is None else f'   {v/prev*100:5.1f}% מהשלב הקודם'
    print(f"  {lbl:<22}{v:>7,}{d}")
    prev=v
print("\n  נפסלו:")
for k,v in sorted(((k,v) for k,v in cnt.items() if k.startswith('x')),key=lambda x:-x[1]):
    print(f"    {k[2:]:<24}{v:>7,}")
print(f"\n  >>> עוברים את כל שערי הכשירות החינמיים: {len(survivors):,}")
