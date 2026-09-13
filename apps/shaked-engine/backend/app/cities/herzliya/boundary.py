"""גבול העיר ואימות אזור החיפוש.

‏`PRD MAP-01`: הפוליגון חייב להיות תקין, חסום בשטח, ובתוך תחום הרצליה.
‏`app/geo.validate_polygon` כבר בודק את שלושתם; מה שחסר לו הוא הגבול עצמו.

הגבול נשמר בקובץ ולא נשלף לכל בקשה. שתי סיבות: הוא כמעט אינו משתנה, ו-WFS
של GovMap מחזיר שגיאה מעת לעת — ב-13.09 הוא החזיר דף שגיאה גם ל-GetCapabilities.
תלות רשת בכל חיפוש הייתה הופכת תקלה אצלם לתקלה אצלנו.

העותק הוא התכונה הרשמית `muni_il.54`, קוד למ״ס 6400, 24.2 קמ״ר. נבדק: כל
700 המועמדים של שכבה א׳ נמצאים בתוכו.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.core.config import get_settings
from app.geo import itm, validate_polygon

BOUNDARY_FILE = Path(__file__).resolve().parents[6] / "POC" / "layer_a" / "data" / "herzliya_boundary.json"


@lru_cache(maxsize=1)
def boundary_itm() -> BaseGeometry:
    """גבול הרצליה ב-ITM. נטען פעם אחת."""
    d = json.loads(BOUNDARY_FILE.read_text(encoding="utf-8"))
    return shape(d["geometry"])          # כבר ב-EPSG:2039


def validate_search_area(geo: dict[str, Any]) -> BaseGeometry:
    """פוליגון מצויר (WGS84) → ITM, אחרי כל בדיקות MAP-01. זורק ValueError בעברית."""
    return validate_polygon(geo, boundary_itm(), get_settings().max_search_area_sqm)


def search_polygon_wkt(geo: dict[str, Any]) -> str:
    """WKT ב-4326 לשאילתת PostGIS, אחרי שהפוליגון אומת."""
    validate_search_area(geo)            # נזרק לפני שנוגעים בבסיס הנתונים
    ring = shape(geo).exterior.coords
    return "POLYGON((" + ",".join(f"{x:.7f} {y:.7f}" for x, y, *_ in ring) + "))"
