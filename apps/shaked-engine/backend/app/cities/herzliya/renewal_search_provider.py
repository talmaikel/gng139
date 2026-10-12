"""‏W5 · ספק חיפוש הרשת שמאתר בניין שכבר חודש — הרשת בלבד.

‏`WebSearchProvider` הוא הממשק; `BraveSearchProvider` המימוש הפעיל, מאחורי
משתנה הסביבה `BRAVE_SEARCH_API_KEY` (לעולם לא בקוד ולא במאגר — ‏#config).
בבדיקות מוזרק ספק מזויף (למשל `renewal_search.FakeSearchProvider` בקבצי
הבדיקה) כדי שאף בדיקה לא תבצע קריאת רשת אמיתית.

רץ על `AsyncPublicClient` (‏`app/sources/client.py`) כמו `HerzliyaArchiveClient` —
אותה תשתית pacing/retry/מטמון, בלי לכתוב אותה פעם שנייה. המפתח עובר
כ-header ולא כפרמטר ב-URL, כך שהוא גם לא נכנס למפתח המטמון (שנגזר מה-URL
בלבד) וגם לא לקובץ מטמון על הדיסק. מה שכן נשמר במטמון הוא תשובת ה-API —
כותרת/תקציר/קישור לכל תוצאה, לא עמוד שלם — בדיוק מה שהמדיניות מתירה.
"""
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.sources.client import AsyncPublicClient, SourceError

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class RenewalSearchUnavailable(RuntimeError):
    """הספק לא השיב — שגיאת רשת, timeout, מגבלת קצב, או מפתח חסר.

    זו **אינה** תשובה על הכתובת (השוו ל-`ArchiveUnavailable`). הבדיקה
    נשארת לא שלמה, והחלקה אינה מועברת למסירה עד הרצה חוזרת.
    """


@dataclass(frozen=True)
class RenewalSearchResult:
    title: str
    description: str
    url: str


class WebSearchProvider(Protocol):
    """ממשק כללי — כל ספק חיפוש שיודע להחזיר תוצאות ל-query חופשי."""

    async def search(self, query: str) -> list[RenewalSearchResult]:
        ...


class BraveSearchProvider:
    """המימוש הפעיל, מאחורי Brave Search API."""

    def __init__(self, public_client: AsyncPublicClient | None = None, *,
                 api_key: str | None = None, count: int = 10):
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.brave_search_api_key
        self._count = count
        self._owns_client = public_client is None
        self._public = public_client or AsyncPublicClient(settings.source_cache_dir, timeout_seconds=15.0)

    async def close(self) -> None:
        if self._owns_client:
            await self._public.aclose()

    async def __aenter__(self) -> "BraveSearchProvider":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def search(self, query: str) -> list[RenewalSearchResult]:
        if not self._api_key:
            raise RenewalSearchUnavailable("BRAVE_SEARCH_API_KEY אינו מוגדר")
        try:
            data, _ = await self._public.json(
                BRAVE_SEARCH_URL, {"q": query, "count": self._count},
                headers={"Accept": "application/json", "X-Subscription-Token": self._api_key},
            )
        except SourceError as exc:
            # ‏SourceError כבר מכסה 429/5xx (עם retry) ו-timeout/transport error.
            # הודעת exc אינה מכילה את המפתח — הוא לא חלק מה-URL הזה.
            raise RenewalSearchUnavailable(f"Brave Search API לא השיב: {exc}") from exc
        results = ((data or {}).get("web") or {}).get("results") or []
        return [
            RenewalSearchResult(title=str(r.get("title") or ""),
                                description=str(r.get("description") or ""),
                                url=str(r.get("url") or ""))
            for r in results
        ]
