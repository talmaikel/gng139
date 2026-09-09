import json,re,pathlib
base=pathlib.Path('data/verification')
audit=json.loads((base/'sample_audit.json').read_text(encoding='utf8'))
for row in audit:
 for f in row.get('files',[]):
  print('\nBUILDING',row['building_id'],'FILE',f['id'])
  print(re.sub(r'\s+',' ',f['text'])[:10000])
  print('ACTIONS',sorted(set(re.findall(r'(?:onclick|href)=["\x27]([^"\x27]+)',f['html'])))[:50])
