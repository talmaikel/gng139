"""הסביבה עצמה — הבדיקה שהייתה חסרה כשהיא נשברה.

‏13-14.09.2026: ה-venv היה כלאיים. ‏`pyvenv.cfg` הצהיר 3.14, המפרש בפועל
היה 3.12, והחבילות התפצלו לשני עצי `site-packages` — אחד שהמפרש רואה,
ואחד שלא. ‏`pip install` דיווח **הצלחה** והחבילה לא הייתה שם.

זה בזבז זמן פעמיים, ולא הייתה שום בדיקה שיכלה לתפוס אותו: הסוויטה רצה
ירוקה כל הזמן, כי היא רצה במפרש שכן היו לו החבילות.
"""
import sys
from pathlib import Path

import pytest


def _venv_root() -> Path | None:
    """שורש ה-venv, או None כשרצים מחוץ לסביבה וירטואלית."""
    root = Path(sys.prefix)
    return root if (root / "pyvenv.cfg").exists() else None


def test_the_interpreter_matches_the_environment_that_created_it():
    """‏`pyvenv.cfg` מצהיר גרסה. אם היא אינה זו שרצה — מישהו החליף את
    הסמלינק, וממקבילה לזה גם ה-`site-packages` התפצלו."""
    root = _venv_root()
    if root is None:
        pytest.skip("רץ מחוץ ל-venv")

    # ‏`python -m venv` כותב `version`; ‏uv כותב `version_info`. שניהם
    # נבדקים, אחרת הבדיקה מדלגת בשקט על הסביבה שהיא אמורה לשמור עליה.
    declared = None
    for line in (root / "pyvenv.cfg").read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() in ("version", "version_info"):
            declared = value.strip()
            break
    if declared is None:
        pytest.skip("‏pyvenv.cfg אינו מצהיר גרסה")

    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert declared.startswith(running), (
        f"‏pyvenv.cfg מצהיר {declared} והמפרש הוא {running}. "
        "‏ה-venv אינו קוהרנטי — יש לבנות אותו מחדש: "
        "rm -rf .venv && uv venv --python 3.12 --seed .venv"
    )


def test_there_is_exactly_one_site_packages_tree():
    """שני עצי `site-packages` פירושם שחבילה יכולה להיות מותקנת ובלתי
    נראית בעת ובעונה אחת — וזה בדיוק מה שקרה."""
    root = _venv_root()
    if root is None:
        pytest.skip("רץ מחוץ ל-venv")

    trees = sorted(p.name for p in (root / "lib").iterdir()
                   if p.is_dir() and p.name.startswith("python"))
    assert len(trees) == 1, (
        f"‏{len(trees)} עצי חבילות ב-venv: {', '.join(trees)}. "
        "‏pip יתקין לאחד והמפרש יקרא מהאחר."
    )


def test_pip_installs_where_the_interpreter_reads():
    """‏`pip --version` מדפיס לאיזה מפרש הוא שייך. אם אינו זה שרץ,
    ‏`pip install` ידווח הצלחה וייעלם."""
    pip = pytest.importorskip("pip", reason="‏pip אינו מותקן ב-venv (uv venv ללא --seed)")
    assert Path(pip.__file__).is_relative_to(Path(sys.prefix)), (
        f"‏pip נטען מ-{pip.__file__}, מחוץ ל-{sys.prefix}"
    )
