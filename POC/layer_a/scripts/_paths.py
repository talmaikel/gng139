"""נתיבים יחסיים לשורש layer_a — כדי שהסקריפטים ירוצו מכל מקום."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW  = ROOT / "raw"          # נתונים גולמיים — לא ב-git, נבנים ע"י fetch_sources.py
RAW.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)
