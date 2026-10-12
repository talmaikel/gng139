import os
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings


# ── הסוויטה אינה נוגעת במסד הפיתוח ──
#
# ‏**זה קרה, פעמיים באותו יום.** הפיקסטורה `session` למטה זהירה: היא
# מגלגלת הכול אחורה. אבל קוד ייצור שנקרא מתוך בדיקה פותח סשן משלו דרך
# ‏`AsyncSessionLocal` ו**מקמט** — והקומיט הזה בורח מהגלגול אחורה.
# ‏`test_seed_layer_a` קורא ל-`seed()`, הזריעה רצה בלי שלב ההערכה
# שאחריה, וכל 699 ההזדמנויות במסד הפיתוח איבדו את
# ‏`metadata_json.assessment`.
#
# התוצאה: **כל הרצה של הסוויטה רוקנה את מסך ההדגמה** — בלי שגיאה, בלי
# בדיקה אדומה, בלי שאיש התכוון. אבחנתי בטעות ״מישהו הריץ את הזריעה
# ביד״; איש לא הריץ. `pytest` הריץ.
#
# ההפניה כאן קודמת לכל ייבוא של `app.core.database`, כי המנוע שם נבנה
# בזמן ייבוא מתוך ההגדרות.
def _redirect_to_a_test_database() -> str:
    def swap(url: str) -> str:
        parts = urlsplit(url)
        name = parts.path.lstrip("/") or "shaked_engine"
        if name.endswith("_test"):
            return url
        return urlunsplit(parts._replace(path=f"/{name}_test"))

    settings = get_settings()
    os.environ["DATABASE_URL"] = swap(settings.database_url)
    os.environ["DATABASE_URL_SYNC"] = swap(settings.database_url_sync)
    get_settings.cache_clear()
    return os.environ["DATABASE_URL_SYNC"]


TEST_SYNC_URL = _redirect_to_a_test_database()


def _create_and_migrate(sync_url: str) -> None:
    """יוצר את מסד הבדיקות אם אינו קיים, ומגר אותו.

    בלי זה כל אחד היה צריך להריץ שתי פקודות ביד לפני הבדיקה הראשונה,
    וההודעה על מסד חסר הייתה נראית כמו תקלה.
    """
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    parts = urlsplit(sync_url)
    name = parts.path.lstrip("/")
    admin = urlunsplit(parts._replace(path="/postgres"))
    conn = psycopg2.connect(admin)
    try:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{name}"')
    finally:
        conn.close()

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")


def pytest_sessionstart(session):  # noqa: ARG001
    try:
        _create_and_migrate(TEST_SYNC_URL)
    except Exception as exc:                       # אין שרת, אין הרשאה
        name = urlsplit(TEST_SYNC_URL).path.lstrip("/")
        print(
            f"\n[conftest] לא ניתן להכין את מסד הבדיקות ({type(exc).__name__}).\n"
            f"           הבדיקות שנשענות על מסד ידלגו — הן לא ייכשלו, וזה נראה ירוק.\n"
            f"           פעם אחת, ממשתמש שיש לו הרשאת superuser:\n"
            f"             createdb -O $(whoami) {name}\n"
            f'             psql -d {name} -c "CREATE EXTENSION IF NOT EXISTS postgis;"\n'
        )


async def no_wait(_seconds: float) -> None:
    """Stand-in for asyncio.sleep, so tests assert on pacing without waiting for it."""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "archive_client: בודק את לקוח הארכיון עצמו, עם תעבורה מדומה משלו",
    )


@pytest.fixture(autouse=True)
def never_reach_the_archive(request, monkeypatch):
    """**הסוויטה אינה פונה לארכיון העירוני.**

    זה לא סגנון אלא מדיניות: ‏`POC/layer_a/data/DATA_LAW.md` קובע שעמודי
    תיק נשלפים ״לפי בקשת לקוח, קומץ בכל פעם״. ‏`fetch_for_delivery` נכנס
    למסלול המסירה, ומאותו רגע **כל הרצה של הסוויטה שלחה בקשות אמיתיות
    לארכיון** — בלי שאיש התכוון, ובלי שזה נראה בפלט.

    כל בדיקה שרוצה התנהגות ארכיון מדמה אותה בעצמה; ה-patch שלה נכנס
    פנימה יותר וגובר על זה.
    """
    if request.node.get_closest_marker("archive_client"):
        return                                  # בודק את הלקוח, עם transport משלו

    from app.cities.herzliya.archive_client import HerzliyaArchiveClient

    async def refuse(*_args, **_kwargs):
        raise AssertionError(
            "בדיקה ניסתה לפנות לארכיון העירוני. יש לדמות את "
            "HerzliyaArchiveClient במפורש."
        )

    monkeypatch.setattr(HerzliyaArchiveClient, "find_tik_ids", refuse)
    monkeypatch.setattr(HerzliyaArchiveClient, "file", refuse)
    monkeypatch.setattr(HerzliyaArchiveClient, "request", refuse)


@pytest.fixture(autouse=True)
def never_reach_brave_search(monkeypatch):
    """‏W5 · הסוויטה אינה פונה ל-Brave Search API האמיתי — לעולם.

    כמו `never_reach_the_archive` למעלה: בדיקת חידוש שרוצה תוצאת חיפוש
    מדמה ספק (`FakeSearchProvider` ב-`tests/test_renewal_search.py`) ומזריקה
    אותו במפורש; שום בדיקה לא אמורה להגיע ל-`BraveSearchProvider` עצמו.
    """
    from app.cities.herzliya.renewal_search_provider import BraveSearchProvider

    async def refuse(*_args, **_kwargs):
        raise AssertionError(
            "בדיקה ניסתה לפנות ל-Brave Search API האמיתי. יש לדמות ספק "
            "(FakeSearchProvider) ולהזריק אותו במפורש."
        )

    monkeypatch.setattr(BraveSearchProvider, "search", refuse)


@pytest.fixture
async def session():
    """
    A session on a real, migrated Postgres, inside a transaction that is rolled
    back, so nothing is left behind. Skips, rather than fails, when no migrated
    database is reachable, so the unit suite still runs without Postgres.

    **The session is joined to an outer transaction as a SAVEPOINT.** Without
    that, any `commit()` under test escapes the rollback and writes to the real
    database: the dossier endpoint commits (correctly -- it is production code),
    and every run of the API tests was leaving a tenant, a user and a task row
    behind while reporting green. `create_savepoint` turns those commits into
    savepoint releases, and the outer rollback still discards everything.
    """
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM field_evidence LIMIT 0"))
    except Exception as exc:  # no server, no database, or not migrated
        await engine.dispose()
        pytest.skip(f"no migrated database reachable: {type(exc).__name__}")

    conn = await engine.connect()
    outer = await conn.begin()
    factory = async_sessionmaker(bind=conn, expire_on_commit=False,
                                 join_transaction_mode="create_savepoint")
    async with factory() as s:
        yield s
    await outer.rollback()
    await conn.close()
    await engine.dispose()
