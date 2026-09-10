import io,os,textwrap
from xml.sax.saxutils import escape
from .config import ROOT

LABELS={'address':'כתובת','eligibility_summary':'מסקנת בדיקת הסף','building_file_number':'מספר תיק בניין','gush':'גוש','parcel':'חלקה','parcel_area':'שטח חלקה במ״ר','footprint_area':'שטח טביעת מבנה במ״ר','building_use':'שימוש עיקרי','units':'דירות בהיתר','floors':'קומות לפי הגדרת המדיניות','floor_configuration':'תצורת קומות','permit_date':'מועד היתר מקורי','original_permit_number':'מספר היתר מקורי','strengthened':'נמצא היתר חיזוק סיסמי','residential_zoning':'ייעוד מגורים','zoning_designation':'ייעוד רשום בתיק','residential_share':'שיעור מגורים חוקי','planning_lot':'מגרש תכנוני','planning_basis':'בסיס תכנוני','overriding_plans_checked':'בדיקת תכניות גוברות','engineer_opinion':'חוות דעת מהנדס לתנאי הגיל','existing_legal_area':'בסיס שטח חוקי מעל הקרקע','main_residential_area':'שטח מגורים עיקרי','service_area':'שטחי שירות','stair_area':'חדר מדרגות','open_pilotis_area':'קומת עמודים מפולשת','shelter_area':'מקלט','original_permitted_total_area':'סך שטחים בהיתר','post_2005_addition_area':'תוספת שירות מ-2013','shaked_area_cap':'תקרת שטח ראשונית לפי 400%','indicative_unit_range':'טווח יחידות אינדיקטיבי','indicative_additional_units':'תוספת יחידות אינדיקטיבית','additional_balcony_area':'מרפסות נוספות — תקרה','tama70_zone':'סיווג תמ״א 70'}
CERTAINTY={'official':'רשמי','manually_verified':'אומת ידנית','derived':'מחושב','community':'מקור קהילתי','missing':'חסר','conflict':'סתירה','ocr_candidate':'מועמד OCR — דורש אימות'}
CHECK_STATUS={'passed':'עבר','failed':'נכשל','unknown':'טרם אומת'}

def display_value(key,value):
    if value is None:return 'חסר'
    if isinstance(value,bool):return 'כן' if value else 'לא'
    if key=='residential_share':return f'{value*100:.1f}%'
    return value

def pdf_export(d):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import simpleSplit
    from bidi.algorithm import get_display
    candidates=[ROOT/'static'/'fonts'/'DejaVuSans.ttf',ROOT/'static'/'fonts'/'Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','C:/Windows/Fonts/arial.ttf']
    font=next((str(p) for p in candidates if os.path.exists(p)),None)
    if not font:raise RuntimeError('Hebrew PDF font missing; install DejaVu Sans')
    if 'Shaked' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('Shaked',font))
    output=io.BytesIO();c=canvas.Canvas(output,pagesize=(595,842));c.setTitle('Shaked dossier '+d['id'])
    y=780
    def page():
        nonlocal y
        c.setFillColorRGB(.08,.14,.12);c.setFont('Shaked',10);c.drawRightString(550,810,get_display('שקד | תיק הזדמנות — בדיקה ראשונית'));y=775
    def line(text,size=10,color=(.08,.14,.12)):
        nonlocal y
        logical=str(text)
        for chunk in simpleSplit(logical,'Shaked',size,490):
            if y<55:c.showPage();page()
            c.setFont('Shaked',size);c.setFillColorRGB(*color)
            c.drawRightString(550,y,get_display(chunk));y-=size+6
    page();line('תיק גילוי — דורש אימות' if d['status']!='ready' else 'מועמד מתאים לפי הנתונים',18)
    line(d['fields']['address']['value'] or d['building_id'],13)
    line('מועד הפקה: '+d['created_at']);line('גרסת כללים: '+d['rule_version']);line('מזהה תיק: '+d['id'])
    y-=8
    for key,f in d['fields'].items():
        line(f"{LABELS.get(key,key)}: {display_value(key,f['value'])} [{CERTAINTY.get(f['certainty'],f['certainty'])}]")
    line('מפה וגבולות מבנה',13)
    geometry=d['geometry'];coords=None
    if geometry.get('type')=='Polygon':coords=geometry['coordinates'][0]
    elif geometry.get('type')=='MultiPolygon':coords=geometry['coordinates'][0][0]
    if coords:
        if y<230:c.showPage();page()
        xs=[p[0] for p in coords];ys=[p[1] for p in coords]
        scale=min(420/max(max(xs)-min(xs),.000001),130/max(max(ys)-min(ys),.000001))
        path=c.beginPath()
        for i,(x,z) in enumerate(coords):
            px=90+(x-min(xs))*scale;py=y-150+(z-min(ys))*scale
            if i==0:path.moveTo(px,py)
            else:path.lineTo(px,py)
        path.close();c.setFillColorRGB(.92,.90,.97);c.setStrokeColorRGB(.33,.22,.56);c.drawPath(path,fill=1,stroke=1);y-=175
    elif geometry.get('type')=='Point':
        lon,lat=geometry['coordinates'];line(f'נקודת מרכז חלקה בלבד: {lat:.6f}, {lon:.6f}')
    line('מידע חסר ובדיקות שנותרו',14)
    for gap in d['gaps']:line('• '+gap,color=(.55,.28,.12))
    line('בדיקות מדיניות',14)
    for check in d['checks']:line(check['label']+' — '+CHECK_STATUS.get(check['status'],check['status']))
    line('כלכלה ראשונית',14)
    if not d.get('scenario'):line('לא חושב רווח: אין בסיס תכנוני והנחות מאושרות שלמות.')
    else:
        for k,v in d['scenario']['result'].items():
            if k!='sensitivity':line(f'{k}: {v}')
    line('מקורות וראיות',14)
    seen=set()
    sources=[d['building_source']]+[p['source'] for p in d['parcels']]+[r['source'] for r in d['archive_records']]
    sources += [f['source'] for f in d['fields'].values() if f.get('source')]
    sources += [doc['source'] for doc in d.get('documents',[]) if doc.get('source')]
    sources.append({'url':d['policy_source'],'retrieved_at':'ראו גרסת מסמך המדיניות'})
    for src in sources:
        if src['url'] in seen:continue
        seen.add(src['url']);line('מועד שליפה: '+src.get('retrieved_at',''))
        # Explicit line breaks prevent long URLs from overflowing the page.
        for chunk in textwrap.wrap(src['url'],width=83):
            if y<55:c.showPage();page()
            c.setFont('Shaked',8);c.setFillColorRGB(.33,.22,.56);c.drawString(45,y,chunk)
            c.linkURL(src['url'],(45,y-2,550,y+10),relative=0);y-=13
    c.save();return output.getvalue()

def excel_export(d):
    import xlsxwriter
    output=io.BytesIO();workbook=xlsxwriter.Workbook(output,{'in_memory':True,'strings_to_formulas':False,'strings_to_urls':False})
    header=workbook.add_format({'bold':True,'bg_color':'#14231F','font_color':'white','text_wrap':True})
    wrap=workbook.add_format({'text_wrap':True,'valign':'top'});num=workbook.add_format({'num_format':'#,##0.00'})
    inputs=workbook.add_format({'font_color':'#2459A6','bg_color':'#F5F8F3','num_format':'#,##0.00'})
    ws=workbook.add_worksheet('נתונים ומקורות');ws.right_to_left();ws.freeze_panes(1,0);ws.set_column('A:A',28);ws.set_column('B:B',28);ws.set_column('C:C',20);ws.set_column('D:D',75);ws.set_column('E:F',30)
    ws.write_row(0,0,['שדה','ערך','ודאות','מקור','תאריך שליפה','מיקום ראיה'],header)
    for i,(key,f) in enumerate(d['fields'].items(),1):
        src=f.get('source') or {};ws.write_row(i,0,[LABELS.get(key,key),display_value(key,f['value']),CERTAINTY.get(f['certainty'],f['certainty']),src.get('url',''),src.get('retrieved_at',''),f.get('location','')],wrap);ws.set_row(i,42)
    sc=workbook.add_worksheet('תרחיש');sc.right_to_left();sc.set_column('A:A',35);sc.set_column('B:B',24);sc.set_column('C:C',55)
    sc.write_row(0,0,['קלט / חישוב','ערך','יחידה / הערה'],header)
    rows=[('שטח מכירה','sale_area','מ״ר'),('שטח בנייה','construction_area','מ״ר'),('מחיר מכירה','sale_price','₪ למ״ר'),('עלות בנייה','build_cost','₪ למ״ר'),('שכירות חודשית כוללת','tenant_rent','₪ לחודש'),('תקופת שכירות','rent_months','חודשים'),('יועצים','consultants','₪'),('מימון','finance','₪'),('מיסים והיטלים','levies_taxes','₪'),('חניה','parking','₪'),('רזרבה','reserve','₪'),('עלויות נוספות','other_costs','₪')]
    assumptions=d.get('scenario',{}).get('assumptions',{}) if d.get('scenario') else {}
    for i,(label,key,unit) in enumerate(rows,1):
        sc.write(i,0,label);sc.write(i,2,unit)
        if key in assumptions:sc.write_number(i,1,assumptions[key],inputs)
        else:sc.write_blank(i,1,None,inputs)
    sc.write(14,0,'הכנסות');sc.write_formula(14,1,'=IF(COUNT(B2:B13)=12,B2*B4,"")',num,'')
    sc.write(15,0,'הוצאות');sc.write_formula(15,1,'=IF(COUNT(B2:B13)=12,B3*B5+B6*B7+SUM(B8:B13),"")',num,'')
    sc.write(16,0,'הפרש תרחיש');sc.write_formula(16,1,'=IF(COUNT(B15:B16)=2,B15-B16,"")',num,'')
    sc.write(17,0,'רווח על העלות');sc.write_formula(17,1,'=IF(AND(ISNUMBER(B16),B16>0),B17/B16,"")',workbook.add_format({'num_format':'0.0%'}),'')
    sc.write(20,0,'אין אישור זכויות. יש להשלים את כל הקלטים ובסיס מס עקבי.',wrap)
    sc.write(21,0,'בסיס מס');sc.write(21,1,assumptions.get('tax_basis','טרם הוגדר'))
    sc.write(22,0,'הנחות');sc.write(22,1,assumptions.get('assumptions_note','לא אושרו הנחות לתרחיש זה'),wrap)
    workbook.close();return output.getvalue()
