"""
Async client for public data sources.

Ported from POC/app/sources.py (PublicClient) and rewritten for asyncio. What
the POC guaranteed, and this keeps:

- every response is cached with its original retrieval time and SHA-256, so a
  cached answer still cites when it was actually fetched, not when it was read
- a request is replayable: query params are folded into one final URL
- 429 and 5xx are retried and Retry-After is honoured; other 4xx fail at once
- an HTML page served with HTTP 200 is not accepted as a JSON answer
- a response over 25 MB is refused rather than silently truncated

Pacing is per host. The municipal archive rate-limits hard, and Overpass frees
its two per-IP slots on a ~15 s cycle, so a 1 s / 2 s backoff would spend every
attempt inside the same closed window.

‏**הקצב משותף לכל התהליך, ולא לכל מופע של הלקוח.** (A24, 15.09) עד היום כל
‏`AsyncPublicClient` זכר לבד מתי פנה לכל שרת. ‏`worker._fetch_permit_pdfs` יוצר
לקוח חדש לכל חלקה, ולכן בלולאה על 39 חלקות (PR #19) הבקשה הראשונה של כל חלקה
יצאה בלי המתנה — גם לארכיון העירוני שמוגדר ל-10 שניות. קצב של 10 שניות שמתאפס
בכל מופע הוא לא קצב.
"""
import threading

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

MAX_BODY_BYTES = 25_000_000
DEFAULT_TTL_SECONDS = 86_400
USER_AGENT = "ShakedEngine/1.0 public-data research"


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class HostPolicy:
    min_interval_seconds: float = 0.35
    retry_base_seconds: float | None = None  # None: exponential 1 s, 2 s, 4 s


DEFAULT_POLICIES: dict[str, HostPolicy] = {
    "handasi.complot.co.il": HostPolicy(min_interval_seconds=10.0),
    # ‏A24 · הגרמושקות עצמן. ‏`robots.txt` של archive.gis-net הוא `Disallow: /`,
    # ו-`DATA_LAW.md` קובע שהגישה אליו ביוזמת אדם בלבד. עד היום הורדה רצה
    # בברירת המחדל — 0.35 שניות — כלומר ריצה על 39 חלקות הייתה מורידה עשרות
    # קבצים בשניות. **הקצב אינו רשות:** הוא רצפה למקרה שמישהו כן מריץ.
    # ‏v5.gis-net הוא אותו מפעיל (proxy של שכבות העירייה, וקישורי מסמכים).
    "archive.gis-net.co.il": HostPolicy(min_interval_seconds=10.0),
    "v5.gis-net.co.il": HostPolicy(min_interval_seconds=10.0),
    "overpass-api.de": HostPolicy(min_interval_seconds=1.0, retry_base_seconds=15.0),
}


class HostSlots:
    """מתי מותר לפנות לכל שרת — **אחד לכל התהליך.**

    ההזמנה נעשית תחת נעילה רגילה ובלי המתנה בתוכה: מחשבים את התור הבא,
    רושמים אותו, ורק אז ממתינים מחוץ לנעילה. כך שני לקוחות, או שתי בקשות
    מקבילות באותו לקוח, מקבלים תורות עוקבים ולא אותו תור. נעילה רגילה ולא
    ‏`asyncio.Lock`, כי הרישום משותף גם ללולאות אירועים שונות.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}

    def reserve(self, host: str, interval: float, now: float) -> float:
        """מזמין את התור הבא לשרת, ומחזיר כמה שניות להמתין עד אליו."""
        with self._lock:
            start = max(now, self._next.get(host, float("-inf")))
            self._next[host] = start + interval
            return start - now


SHARED_SLOTS = HostSlots()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_retryable(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def final_url(url: str, params: dict[str, Any] | None) -> str:
    # One final URL keeps the request replayable from its cited source. The
    # trailing "?" case matters: the municipal ArcGIS proxy expects "...?&f=json".
    if not params:
        return url
    separator = "" if url.endswith("?") else ("&" if "?" in url else "?")
    return url + separator + urlencode(params)


class AsyncPublicClient:
    """Cached, paced, retrying HTTP client. Use as `async with AsyncPublicClient(...) as client:`."""

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        policies: dict[str, HostPolicy] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 35.0,
        max_attempts: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        slots: HostSlots | None = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._policies = {**DEFAULT_POLICIES, **(policies or {})}
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds, follow_redirects=True, transport=transport, headers={"User-Agent": USER_AGENT}
        )
        self._max_attempts = max_attempts
        self._sleep = sleep  # injectable, so tests assert on waits instead of waiting
        # ברירת המחדל היא הרישום המשותף. בדיקות מעבירות רישום משלהן, כי
        # ‏`sleep` מדומה אינו מקדם את השעון והתורות היו מצטברים בין בדיקות.
        self._slots = slots if slots is not None else SHARED_SLOTS

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncPublicClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ---- public API -------------------------------------------------------

    async def get(
        self, url: str, params: dict[str, Any] | None = None, *, ttl: int | None = None, headers: dict | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        url = final_url(url, params)
        key = hashlib.sha256(url.encode()).hexdigest()
        cached = self._read_cache(key, self.ttl_seconds if ttl is None else ttl)
        if cached:
            return cached
        response = await self._fetch("GET", url, headers=headers)
        meta = self._meta(url, response)
        self._write_cache(key, response.content, meta)
        return response.content, meta

    async def json(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
        body, meta = await self.get(url, params, **kwargs)
        return self._parse_json(body, meta), meta

    async def post_json(self, url: str, payload: Any, *, ttl: int | None = None) -> tuple[Any, dict[str, Any]]:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        key = hashlib.sha256(("POST " + url + " " + encoded).encode()).hexdigest()
        cached = self._read_cache(key, self.ttl_seconds if ttl is None else ttl)
        if cached:
            return self._parse_json(*cached), cached[1]
        response = await self._fetch("POST", url, json_payload=payload)
        meta = {**self._meta(url, response), "method": "POST", "request": payload}
        data = self._parse_json(response.content, meta)
        self._write_cache(key, response.content, meta)
        return data, meta

    # ---- internals --------------------------------------------------------

    async def _fetch(
        self, method: str, url: str, *, headers: dict | None = None, json_payload: Any = None
    ) -> httpx.Response:
        host = urlsplit(url).hostname or ""
        error: SourceError | None = None
        for attempt in range(self._max_attempts):
            last_attempt = attempt == self._max_attempts - 1
            await self._pace(host)
            try:
                response = await self._client.request(method, url, headers=headers, json=json_payload)
            except httpx.TransportError as exc:
                error = SourceError(f"{type(exc).__name__}: {url}: {exc}")
                if not last_attempt:
                    await self._sleep(self._backoff(host, attempt))
                continue
            if _is_retryable(response.status_code):
                error = SourceError(f"HTTP {response.status_code}: {url}")
                if not last_attempt:
                    retry_after = response.headers.get("Retry-After", "")
                    await self._sleep(min(30.0, float(retry_after)) if retry_after.isdigit() else self._backoff(host, attempt))
                continue
            if response.status_code >= 400:
                raise SourceError(f"HTTP {response.status_code}: {url}")
            if len(response.content) > MAX_BODY_BYTES:
                raise SourceError(f"Source exceeds 25 MB limit: {url}")
            return response
        raise error or SourceError(url)

    async def _pace(self, host: str) -> None:
        policy = self._policies.get(host, HostPolicy())
        if policy.min_interval_seconds <= 0:
            return
        wait = self._slots.reserve(host, policy.min_interval_seconds, time.monotonic())
        if wait > 0:
            await self._sleep(wait)

    def _backoff(self, host: str, attempt: int) -> float:
        base = self._policies.get(host, HostPolicy()).retry_base_seconds
        return base if base is not None else float(2**attempt)

    @staticmethod
    def _meta(url: str, response: httpx.Response) -> dict[str, Any]:
        return {
            "url": url,
            "retrieved_at": utcnow_iso(),
            "epoch": time.time(),
            "sha256": hashlib.sha256(response.content).hexdigest(),
            "content_type": response.headers.get("content-type", ""),
        }

    @staticmethod
    def _parse_json(body: bytes, meta: dict[str, Any]) -> Any:
        try:
            data = json.loads(body)
        except ValueError:
            raise SourceError(f"Expected JSON; source returned HTML or invalid data: {meta['url']}") from None
        if isinstance(data, dict) and data.get("error"):
            raise SourceError(str(data["error"]))
        return data

    def _read_cache(self, key: str, ttl: int) -> tuple[bytes, dict[str, Any]] | None:
        body_path, meta_path = self.cache_dir / f"{key}.bin", self.cache_dir / f"{key}.json"
        if not (body_path.exists() and meta_path.exists()):
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if time.time() - meta["epoch"] >= ttl:
            return None
        return body_path.read_bytes(), meta

    def _write_cache(self, key: str, body: bytes, meta: dict[str, Any]) -> None:
        # Write-then-rename, so an interrupted write never leaves a half cache entry behind.
        body_path, meta_path = self.cache_dir / f"{key}.bin", self.cache_dir / f"{key}.json"
        tmp = body_path.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(body_path)
        tmp = meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        tmp.replace(meta_path)
