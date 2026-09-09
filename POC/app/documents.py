"""Bounded public document collection; OCR outputs are evidence, not verified facts."""
import hashlib,html,json,re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from .config import DATA
from .sources import SourceError

class Tables(HTMLParser):
    def __init__(self):
        super().__init__();self.tables=[];self.table=None;self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.table=[]
        elif tag=='tr' and self.table is not None:self.row=[]
        elif tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()));self.cell=None
        elif tag=='tr' and self.row is not None:
            self.table.append(self.row);self.row=None
        elif tag=='table' and self.table is not None:
            self.tables.append(self.table);self.table=None

def archive_tables(s):
    p=Tables();p.feed(s)
    out=[]
    private_headers={'שם המבקש','שם בעל עניין','בעלי עניין','שם','ת.ז.','תעודת זהות','טלפון','דוא"ל','דואר אלקטרוני','כתובת בעל עניין'}
    for table in p.tables:
        if not table:continue
        headers=table[0]
        keep=[i for i,h in enumerate(headers) if h and h not in private_headers and h!='מסמכים']
        if not keep:continue
        out.append({'headers':[headers[i] for i in keep],
                    'rows':[[row[i] if i<len(row) else '' for i in keep] for row in table[1:]]})
    return out

ALLOWED_DOCUMENT_HOSTS={'handasa.herzliya.muni.il','handasi.complot.co.il','archive.gis-net.co.il','v5.gis-net.co.il'}

def collect_pdf(client,url):
    if urlsplit(url).scheme!='https' or urlsplit(url).hostname not in ALLOWED_DOCUMENT_HOSTS:
        raise SourceError('Document host is outside configured public sources')
    raw,meta=client.get(url)
    if not raw.startswith(b'%PDF'):raise SourceError('Expected PDF document')
    folder=DATA/'documents';folder.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(raw).hexdigest();path=folder/(digest+'.pdf');path.write_bytes(raw)
    import pymupdf
    pages=[]
    with pymupdf.open(stream=raw,filetype='pdf') as pdf:
        if len(pdf)>100:raise SourceError('Document exceeds 100-page extraction limit')
        for i,page in enumerate(pdf):
            text=page.get_text();method='pdf_text';issue=None
            if len(text.strip())<30:
                try:
                    tp=page.get_textpage_ocr(language='heb+eng',dpi=200,full=True)
                    text=page.get_text(textpage=tp);method='ocr_unverified'
                except Exception:
                    method='ocr_unavailable';issue='Hebrew/English Tesseract language data not installed'
            pages.append({'page':i+1,'text':text,'method':method,'issue':issue})
    result={'id':digest,'source':meta,'pages':pages,'path':str(path),'critical_facts_auto_verified':False}
    (folder/(digest+'.json')).write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
    return result
