"""Inspect a bounded set of public permit-detail pages linked from saved files."""
import sys,pathlib,json,re,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from app.sources import PublicClient,ARCHIVE,text_from_html,utcnow
base=pathlib.Path('data/verification/permits');base.mkdir(parents=True,exist_ok=True)
client=PublicClient()
ids=sys.argv[1:] or ['19620127','19440092','20160770','20110048']
for rid in ids:
    assert rid.isdigit()
    try:
        raw,meta=client.get(ARCHIVE,dict(appname='cixpa',prgname='GetBakashaFile',siteid=121,b=int(rid),arguments='siteid,b'))
        record={'id':rid,'source':meta,'html':raw.decode('utf8',errors='replace'),'text':text_from_html(raw)}
        (base/(rid+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
        print('\nREQUEST',rid, re.sub(r'\s+',' ',record['text'])[:18000],flush=True)
        print('ACTIONS',sorted(set(re.findall(r'(?:onclick|href)=["\x27]([^"\x27]+)',record['html'])))[:50],flush=True)
    except Exception as e:
        print(str(e),flush=True)
        if '429' in str(e):break
    time.sleep(5)
