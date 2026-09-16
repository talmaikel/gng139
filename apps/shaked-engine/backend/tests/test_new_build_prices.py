"""‏P1 · טבלת מחירי הגושים בקוד היא העתק של טבלת הסיכום בדו״ח — והדו״ח בריפו.

‏`new_build_prices.py` נכתב מטבלה שנשלחה בהודעה, והדו״ח עצמו לא היה בפרויקט;
ביום שהוא נמצא (16.09) התברר שאף אחד לא יכול היה לבדוק שהמספרים בקוד הם
המספרים בדו״ח. עכשיו הקובץ ב-`POC/layer_a/data`, והבדיקה קוראת את הטבלה
ממנו ומשווה: גוש שבטבלה עם מחיר מספרי חייב להיות בקוד באותו מחיר, וגוש
שבקוד ואינו בטבלה חייב להיות מסומן ״מהטקסט״.
"""
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from app.cities.herzliya import new_build_prices as nbp
from app.cities.herzliya.seed_layer_a import LAYER_A

REPORT = LAYER_A / "new_build_prices_by_block.docx"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _report_table() -> dict[str, int | None]:
    """גוש → מחיר מטבלת הסיכום; ‏None כשהתא אינו מספר (עתודה, תחזית, בהתהוות)."""
    root = ET.fromstring(zipfile.ZipFile(REPORT).read("word/document.xml"))
    out: dict[str, int | None] = {}
    for table in root.iter(f"{W}tbl"):
        for tr in table.iter(f"{W}tr"):
            cells = ["".join(t.text or "" for t in tc.iter(f"{W}t")).strip()
                     for tc in tr.findall(f"{W}tc")]
            if len(cells) < 3 or not re.fullmatch(r"\d{4}", cells[0]):
                continue
            m = re.fullmatch(r"([\d,]+)\s*₪", cells[2])
            out[cells[0]] = int(m.group(1).replace(",", "")) if m else None
    return out


def test_the_report_is_in_the_repo_and_has_the_summary_table():
    assert REPORT.exists(), REPORT
    table = _report_table()
    assert len(table) >= 16 and table["6536"] == 39_500 and table["6592"] == 72_000


def test_every_priced_block_in_the_report_is_in_the_code_at_the_same_price():
    table = _report_table()
    for block, price in table.items():
        if price is None:
            assert nbp.for_block(block) is None, f"{block}: אין מחיר בדו״ח, ובקוד יש"
        else:
            row = nbp.for_block(block)
            assert row is not None, f"{block}: בדו״ח {price:,} ובקוד אין"
            assert row.price_per_sqm_ils == price, f"{block}: בדו״ח {price:,}, בקוד {row.price_per_sqm_ils:,}"


def test_a_block_priced_only_in_the_prose_says_so():
    """‏6541 ו-6542 נמנים בדו״ח עם נווה עמל (30–32 אלף) ואינם בטבלה. המספר
    נכנס, והאמינות אומרת מאיפה — כדי שהתיק לא יציג אותו כטבלה."""
    table = _report_table()
    for block in nbp.NEW_BUILD_PRICE_BY_BLOCK:
        if block not in table:
            assert block in nbp.FROM_PROSE, f"{block}: בקוד ולא בדו״ח"
            assert "מהטקסט" in nbp.for_block(block).reliability
    for block in nbp.FROM_PROSE:
        assert 30_000 <= nbp.for_block(block).price_per_sqm_ils <= 32_000
    assert "new_build_prices_by_block.docx" in nbp.sale_price("6541", 42_000)[1]
