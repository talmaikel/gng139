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

def classify_run(run, street_index, streets, tags, names, step=4):
    """מזהה איזו דרך חוצה את הרווח. מחזיר (tag, name)."""
    from shapely.geometry import LineString
    nx, ny = run['normal']; w = max(run['width'], 3.0)
    hits = []
    for x, y in run['pts'][::step]:
        seg = LineString([(x + nx*0.3, y + ny*0.3), (x + nx*w, y + ny*w)])
        for j in street_index.query(seg):
            if streets[j].intersects(seg):
                hits.append((tags[j], names[j]))
    if not hits:
        return None, None
    st = [h for h in hits if h[0] in STREET_TAGS]
    pool = st or hits
    return max(set(pool), key=pool.count)

def qualifying(runs, street_index, streets, tags, names):
    """מחזיר רשימת חזיתות רחוב כשירות: [(רוחב, tag, שם), ...]."""
    out = []
    for r in runs:
        tag, name = classify_run(r, street_index, streets, tags, names)
        if tag in STREET_TAGS and r['width'] > MIN_ROW_M:
            out.append((r['width'], tag, name))
    return out

def governing_width(runs, street_index, streets, tags, names):
    """הרוחב הקובע: הצר מבין חזיתות הרחוב הכשירות.
    מחזיר (רוחב, נימוק). None = אין חזית רחוב כשירה → נופל בתנאי הסף.
    """
    q = qualifying(runs, street_index, streets, tags, names)
    if not q:
        return None, 'אין חזית רחוב כשירה מעל 8 מ׳'
    w = min(x[0] for x in q)
    desc = ' · '.join(f"{x[0]} מ׳ {x[1]}" + (f" ({x[2]})" if x[2] else "") for x in q)
    return w, f"{desc} → הצרה קובעת {w}"
