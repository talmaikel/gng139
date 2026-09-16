"""הגבלת קצב לנתיבי הכניסה — בלי זה בוט פותח אלפי חברות או מנחש סיסמאות.

בזיכרון התהליך: מספיק לשרת אחד בפיילוט. כשיהיו כמה תהליכים או שרתים,
כל אחד סופר לעצמו — אז עוברים ל-Postgres או להגבלה ב-Cloudflare.

‏**שני מפתחות, כי כתובת ה-IP אינה אמינה כאן.** הדפדפן מדבר עם Next ו-Next
מעביר לכאן, ולכן העמית הישיר הוא תמיד 127.0.0.1. ‏Next **אינו מוסיף**
‏X-Forwarded-For בהעברה, ומעביר הלאה את זה שהדפדפן שלח — כלומר כל אחד יכול
לכתוב שם כתובת אחרת בכל בקשה. נבדק ב-15.09: ‏11 ניסיונות דרך Next לא נחסמו.

  • **לפי חשבון** (המייל שבבקשה) — אמין תמיד. עוצר ניחוש סיסמה לחשבון
    אחד, והצפת תיבת מייל של מישהו בבקשות שחזור.
  • **לפי כתובת** — רק מכותרת שהפריסה קובעת (`TRUSTED_IP_HEADER`, למשל
    ‏`cf-connecting-ip` מאחורי Cloudflare). בלי כותרת כזו ומאחורי Next
    אין כתובת אמיתית, ולכן **לא** מגבילים לפיה: הגבלה על 127.0.0.1 הייתה
    חוסמת את כל הלקוחות יחד אחרי עשר כניסות.
"""
import json
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request

from app.core.config import get_settings

LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"}

KeyFunc = Callable[[Request], Awaitable[str | None]]


async def client_ip(request: Request) -> str | None:
    """כתובת אמיתית, או None כשאין דרך לדעת אותה."""
    header = get_settings().trusted_ip_header
    if header:
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    peer = request.client.host if request.client else ""
    if not peer or peer in LOOPBACK:
        return None          # מאחורי Next, או dev-auto-login / בדיקות
    return peer


async def account(request: Request) -> str | None:
    """המייל שבבקשה: ‏`username` בטופס הכניסה, ‏`email` ב-JSON של השחזור והאימות."""
    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            value = json.loads(await request.body() or b"{}").get("email")
        else:
            value = (await request.form()).get("username")
    except (ValueError, AttributeError):
        return None
    return str(value).strip().lower() if value else None


class RateLimit:
    def __init__(self, name: str, limit: int, window_seconds: int, key: KeyFunc) -> None:
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self.key = key
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, request: Request) -> None:
        key = await self.key(request)
        if key is None:
            return
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            wait = int(self.window - (now - hits[0])) + 1
            minutes = max(1, round(wait / 60))
            raise HTTPException(
                status_code=429,
                detail=f"יותר מדי ניסיונות. אפשר לנסות שוב בעוד {minutes} דקות.",
                headers={"Retry-After": str(wait)},
            )
        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()


# ‏10 כניסות ב-15 דקות לחשבון מספיקות למי ששכח סיסמה, ומאטות ניחוש עד חוסר תועלת.
login_account_limit = RateLimit("login-account", 10, 15 * 60, account)
login_ip_limit = RateLimit("login-ip", 30, 15 * 60, client_ip)
signup_ip_limit = RateLimit("signup-ip", 5, 60 * 60, client_ip)
# שחזור ואימות שולחים מייל — נמוך, כדי שלא ישמשו להצפת תיבה של מישהו.
email_account_limit = RateLimit("email-account", 3, 60 * 60, account)
email_ip_limit = RateLimit("email-ip", 10, 60 * 60, client_ip)

ALL_LIMITS = (login_account_limit, login_ip_limit, signup_ip_limit,
              email_account_limit, email_ip_limit)
