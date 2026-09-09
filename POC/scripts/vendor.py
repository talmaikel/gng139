from pathlib import Path
from urllib.request import urlopen
root=Path(__file__).resolve().parents[1]/'static'/'vendor';root.mkdir(parents=True,exist_ok=True)
for name in ['leaflet.js','leaflet.css','LICENSE']:
    path='dist/'+name if name!='LICENSE' else name
    with urlopen('https://unpkg.com/leaflet@1.9.4/'+path,timeout=30) as response:
        (root/name).write_bytes(response.read())
    print(name)
