import sys,pathlib,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from app.store import Store
from app.sample import import_sample
from app.exports import pdf_export,excel_export
import pymupdf
out=pathlib.Path('test-output');out.mkdir(exist_ok=True)
store=Store();rows=import_sample(store);d=rows[1]
(out/'sample-dossier.pdf').write_bytes(pdf_export(d))
(out/'sample-scenario.xlsx').write_bytes(excel_export(d))
with pymupdf.open(out/'sample-dossier.pdf') as pdf:
    print('PDF pages:',len(pdf))
    for i,page in enumerate(pdf):
        page.get_pixmap(matrix=pymupdf.Matrix(1.2,1.2)).save(out/f'pdf-page-{i+1}.png')
        for block in page.get_text('blocks'):
            if block[0]<35 or block[2]>561 or block[1]<20 or block[3]>815:
                raise AssertionError(f'Text outside margins on page {i+1}: {block[:4]}')
print('Export structure and bounds verified')
