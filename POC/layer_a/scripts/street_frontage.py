"""זיהוי חזיתות רחוב כשירות, וקביעת הרוחב הקובע.

הבעיה שזה פותר: מדידת הרווח סביב חלקה מוצאת גם שבילים, דרכי שירות וחצרות חניה.
בהצנחנים 15 הגבול הצפוני הוא שביל של ~2.4 מ', ושתי שיטות קודמות החזירו לו
8.0 ו-20.4 מ' — שתיהן שגויות. בלי לדעת מה רחוב, מודדים את הדבר הלא נכון.

הפתרון: OpenStreetMap מתייג כל דרך. `residential` / `tertiary` / `living_street`
הם רחוב; `footway` / `service` / `path` אינם. באזור מרכז הרצליה: 622 רחובות מול
1,357 שבילים ודרכי שירות — הבחנה שאין צורך לגזור מתצלום אוויר.

התכנית האסטרטגית דורשת "רח' ברוחב של מעל 8 מ' **זכות דרך**". דרך שירות בתוך
שיכון אינה זכות דרך ציבורית, ולכן הסיווג אינו רק נוחות טכנית.

אומת על ארבעה בניינים: הר מירון 1 (14.0, 'הר מירון' residential — תואם מדידה
בלתי תלויה), בר-כוכבא 105 (16.1 'בר כוכבא' tertiary), והצנחנים 15 ו-191 שנדחו
בצדק — הראשון גובל בשביל, השני בחצר חניה, שניהם אומתו בתצלום אוויר.
"""
STREET_TAGS = {'residential', 'tertiary', 'secondary', 'primary',
               'living_street', 'unclassified', 'trunk'}
MIN_ROW_M = 8.0        # "עד 8 מ' כולל — לא תותר תוספת"

def classify_run(run, street_index, streets, tags, names, step=3, reach=1.8):
    """מזהה איזו דרך חוצה את הרווח. מחזיר (tag, name).

    משתמש בנורמל פר-נקודה ולא בממוצע החזית: על חזית מעוקלת הממוצע מצביע
    לכיוון שגוי ושולח את הקרן לחלקה שכנה במקום אל מעבר לרווח.
    """
    from shapely.geometry import LineString
    samples = run.get('samples') or [(x, y, *run['normal'], run['width'])
                                     for x, y in run['pts']]
    hits = []
    for x, y, nx, ny, w in samples[::step]:
        r = max((w or run['width']) * reach, 4.0)
        seg = LineString([(x + nx*0.3, y + ny*0.3), (x + nx*r, y + ny*r)])
        for j in street_index.query(seg):
            if streets[j].intersects(seg):
                hits.append((tags[j], names[j]))
    if not hits:
        return None, None
    st = [h for h in hits if h[0] in STREET_TAGS]
    pool = st or hits
    return max(set(pool), key=pool.count)

def has_street(parcel, street_index, streets, tags, reach=12.0):
    """האם קו רחוב עובר סמוך לגבול החלקה.

    שאלה נפרדת מ"מה רוחבו". כשהכביש הוא חלקה רשומה הצמודה למגרש, מדידת
    הרווח מדלגת עליו — היא מחפשת את המגרש שמעבר — ולכן היעדר רווח אינו
    ראיה להיעדר רחוב. הצנחנים 15 נדחתה כך בטעות: קו רחוב נוגע בגבולה המזרחי.
    """
    b = parcel.buffer(reach)
    for j in street_index.query(b):
        if tags[j] in STREET_TAGS and streets[j].intersects(b):
            return True
    return False

def qualifying(runs, street_index, streets, tags, names):
    """מחזיר רשימת חזיתות רחוב כשירות: [(רוחב, tag, שם), ...]."""
    out = []
    for r in runs:
        tag, name = classify_run(r, street_index, streets, tags, names)
        if tag in STREET_TAGS and r['width'] > MIN_ROW_M:
            out.append((r['width'], tag, name))
    return out

def narrow_frontages(runs, street_index, streets, tags, names, min_width=3.0):
    """חזיתות מתויגות-רחוב שצרות מ-8 מ׳. `qualifying` משמיט אותן, ולכן הן מוחזרות בנפרד.

    הן לא "אין תוספת" אוטומטית: באימות (validation/narrow_streets.json) שלוש מתוך
    שש היו דרך שירות או כניסה לחניון ש-OSM מתייג כרחוב. הרוחב נכון; הסיווג לא.
    """
    out = []
    for r in runs:
        if min_width <= r['width'] <= MIN_ROW_M:
            tag, name = classify_run(r, street_index, streets, tags, names)
            if tag in STREET_TAGS:
                out.append((r['width'], tag, name))
    return out

def governing_width(runs, street_index, streets, tags, names, parcel=None):
    """הרוחב הקובע: הצר מבין חזיתות הרחוב הכשירות.

    מחזיר (רוחב, נימוק, יש_רחוב). שלושה מצבים שונים שאסור למזג:
      (w, ..., True)     — יש רחוב ורוחבו נמדד
      (None, ..., True)  — יש רחוב אך הרוחב לא נמדד (כביש צמוד, למשל)
      (None, ..., False) — אין רחוב כלל → נופל בתנאי הסף
    """
    street = has_street(parcel, street_index, streets, tags) if parcel is not None else None
    q = qualifying(runs, street_index, streets, tags, names)
    if not q:
        if street:
            return None, 'קו רחוב סמוך אך הרוחב לא נמדד — ייתכן כביש צמוד', True
        return None, 'אין קו רחוב בסביבת החלקה', False
    w = min(x[0] for x in q)
    desc = ' · '.join(f"{x[0]} מ׳ {x[1]}" + (f" ({x[2]})" if x[2] else "") for x in q)
    return w, f"{desc} → הצרה קובעת {w}", True
