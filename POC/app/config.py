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
ARCHIVE_INTERVAL_SECONDS = float(os.getenv('ARCHIVE_INTERVAL_SECONDS', '10'))
SOURCE_MAX_AGE_DAYS = int(os.getenv('SOURCE_MAX_AGE_DAYS', '30'))
POLICY_URL = 'https://handasa.herzliya.muni.il/wp-content/uploads/2025/09/מדיניות-בניה-חלופת-שקד-מאושרת-בועדה-המקומית-769-מונגשת.pdf'
RULE_VERSION = 'herzliya-policy-2026-02-17-v2'
TEMPLATE_VERSION = 'dossier-1'
SAMPLE_POLYGON = {'type':'Polygon','coordinates':[[[34.838,32.162],[34.841,32.162],[34.841,32.164],[34.838,32.164],[34.838,32.162]]]}
