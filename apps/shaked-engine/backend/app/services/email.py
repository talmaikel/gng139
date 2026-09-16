"""שליחת מייל — שחזור סיסמה ואימות כתובת.

עם `RESEND_API_KEY` (או `backend/resend.key`) המייל נשלח דרך Resend. בלעדיו הוא **נכתב ללוג** עם
הקישור, כך שפיתוח מקומי ובדיקות עובדים בלי חשבון ובלי לשלוח דבר החוצה.

כשל בשליחה אינו מפיל את הבקשה: מי שביקש שחזור מקבל תמיד את אותה תשובה
(כדי לא לגלות אם המייל רשום), ומי שנרשם כבר מחובר — אפשר לבקש מייל אימות שוב.
"""
import html
import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger("shaked.email")

RESEND_URL = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, text: str, link: str | None = None) -> bool:
    settings = get_settings()
    api_key = settings.resend_key()
    if not api_key:
        log.warning("[email not sent — RESEND_API_KEY missing] to=%s subject=%s link=%s", to, subject, link)
        return False

    body = f"<p>{html.escape(text)}</p>"
    if link:
        body += f'<p><a href="{html.escape(link)}">{html.escape(link)}</a></p>'
    payload = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": f'<div dir="rtl" style="font-family:Arial,sans-serif;line-height:1.6">{body}</div>',
        "text": f"{text}\n\n{link}" if link else text,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(RESEND_URL, json=payload,
                                  headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code >= 400:
            log.error("resend refused: %s %s", r.status_code, r.text[:300])
            return False
        return True
    except httpx.HTTPError as exc:
        log.error("resend unreachable: %s", exc)
        return False


async def send_password_reset(to: str, token: str) -> bool:
    link = f"{get_settings().frontend_url.rstrip('/')}/reset-password?token={token}"
    return await send_email(
        to, "איפוס סיסמה · שקדן",
        "ביקשתם לאפס את הסיסמה בשקדן. הקישור תקף לשעה. אם לא ביקשתם — אפשר להתעלם מהמייל.",
        link,
    )


async def send_verification(to: str, token: str) -> bool:
    link = f"{get_settings().frontend_url.rstrip('/')}/verify?token={token}"
    return await send_email(
        to, "אימות כתובת המייל · שקדן",
        "כדי לאמת את כתובת המייל בחשבון שקדן, פתחו את הקישור. הקישור תקף לשעה.",
        link,
    )
