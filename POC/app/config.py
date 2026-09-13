import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('SHAKED_DATA', str(ROOT / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', '')
MAX_AREA_M2 = float(os.getenv('MAX_AREA_M2', '250000'))
MAX_RADIUS_M = float(os.getenv('MAX_RADIUS_M', '250'))
MAX_BUILDINGS = int(os.getenv('MAX_BUILDINGS', '500'))
MAX_PARCELS = int(os.getenv('MAX_PARCELS', '1000'))
CACHE_SECONDS = int(os.getenv('CACHE_SECONDS', '86400'))
XPLAN_CACHE_SECONDS = int(os.getenv('XPLAN_CACHE_SECONDS', '604800'))
XPLAN_OVERLAP_THRESHOLD = float(os.getenv('XPLAN_OVERLAP_THRESHOLD', '0.90'))
XPLAN_SPECIAL_OVERLAP_THRESHOLD = float(os.getenv('XPLAN_SPECIAL_OVERLAP_THRESHOLD', '0.02'))
XPLAN_METRO_STATION_BUFFER_M = float(os.getenv('XPLAN_METRO_STATION_BUFFER_M', '500'))
ARCHIVE_INTERVAL_SECONDS = float(os.getenv('ARCHIVE_INTERVAL_SECONDS', '10'))
SOURCE_MAX_AGE_DAYS = int(os.getenv('SOURCE_MAX_AGE_DAYS', '30'))
# מסמך המדיניות המצוטט בכל שער ב-rules.py. נבדק 13.09.2026: מחזיר 200,
# והטקסט זהה ל-layer_a/data/policy_shaked_apr2026.pdf.
# הכתובת הקודמת (‎/2025/09/‎, ועדה 769) החזירה 404 — כלומר כל תיק שנמסר
# ציטט קישור מת. אותה כתובת נמצאת גם ב-layer_a/data/documents.json,
# ולכן check_documents.py יתפוס אם היא תישבר שוב.
# אזהרה: גרסת ועדה 769 מספטמבר 2025 אינה זהה — שם תקרת הדירות היא
# 32 יח"ד לדונם, ולא מכפיל 2.8–3.18 על המצב הקיים. אין להשתמש בה.
POLICY_URL = 'https://handasa.herzliya.muni.il/wp-content/uploads/2026/04/%D7%9E%D7%93%D7%99%D7%A0%D7%99%D7%95%D7%AA-%D7%91%D7%A0%D7%99%D7%94-%D7%97%D7%9C%D7%95%D7%A4%D7%AA-%D7%A9%D7%A7%D7%93-%D7%90%D7%A4%D7%A8%D7%99%D7%9C-2026.pdf'
RULE_VERSION = 'herzliya-policy-2026-02-17-v2'
TEMPLATE_VERSION = 'dossier-1'
CITY_PROFILES = {
    'herzliya': {
        'label': 'הרצליה',
        'archive_url': 'https://handasa.herzliya.muni.il/tikbinyan/',
        'rule_version': RULE_VERSION,
    },
    'tel-aviv': {
        'label': 'תל אביב-יפו',
        'archive_url': 'https://handasa.tel-aviv.gov.il/Pages/SearchResultsAnonPageNew.aspx',
        'policy_url': 'https://www.tel-aviv.gov.il/Residents/Development/Pages/KoleletTlv.aspx?Iccid=4',
        'rule_version': 'tel-aviv-current-status-2026-09-10-v1',
    },
}
SAMPLE_POLYGON = {'type':'Polygon','coordinates':[[[34.838,32.162],[34.841,32.162],[34.841,32.164],[34.838,32.164],[34.838,32.162]]]}
