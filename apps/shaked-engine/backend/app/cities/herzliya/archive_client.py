"""
Live client for Herzliya's municipal building-permit archive ("Tik Binyan") at
handasi.complot.co.il: a legacy CGI-style HTTP API, not a JS-rendered page,
which is why Herzliya needs no browser automation (app/pipeline/scraper.py stays
the fallback for a city whose archive does).

Runs on AsyncPublicClient, so every archive request is cached, paced one per
10 s (the archive answers bursts with 429) and retried. Merged with the POC's
BuildingArchive (POC/app/sources.py):

- a search reports whether the archive answered "no results" or answered
  something unrecognised, so a changed page is never read as "no files"
- an address search checks the file count the page declares against the files
  actually parsed, so a partly rendered result cannot pass as complete
- street catalogue and building-file pages, which the archive index (phase 2c)
  builds on

The public methods worker.py already calls (find_tik_ids, find_documents,
download) keep their signatures.
"""

import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import get_settings
from app.sources.client import AsyncPublicClient, SourceError

ARCHIVE_URL = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"
STREETS_URL = "https://handasi.complot.co.il/wsComplotPublicData/ComplotPublicData.asmx/GetStreets"
SITE_ID = 121
HERZLIYA_LAMAS_CODE = 6400

# Hosts the archive is known to link documents from. Downloads outside this
# allowlist are refused so a compromised/altered response can't redirect us
# into fetching from an attacker-controlled host.
ALLOWED_DOCUMENT_HOSTS = {
    "handasa.herzliya.muni.il",
    "handasi.complot.co.il",
    "archive.gis-net.co.il",
    "v5.gis-net.co.il",
}

TIK_ID_PATTERN = re.compile(r"(?:getBuilding\s*\(\s*['\"]?|#building/)(\d+)")
PDF_HREF_PATTERN = re.compile(r'href=["\']([^"\']+)', re.IGNORECASE)
DECLARED_COUNT_PATTERN = re.compile(r"נמצאו\s*(\d+)\s*תיקי\s*בניין")
NO_RESULTS_MARKERS = ("ERR_NO_RESULTS", "לא נמצאו")


class HerzliyaArchiveError(SourceError):
    pass


class ArchiveBlocked(HerzliyaArchiveError):
    """The archive answered with a CAPTCHA or its "cannot display" apology, both as HTTP 200.

    A stop signal (POC/layer_a/data/DATA_LAW.md): never solved, never retried in
    a loop, and never read as an answer about the parcel.
    """


# Both refusals arrive as HTTP 200. The soft block is short; the same sentence
# can appear inside a long legitimate page, hence the length bound (as in the POC).
CAPTCHA_MARKERS = ("g-recaptcha", "VerifyUser", "נדרש אימות משתמש")
SOFT_BLOCK_MARKER = "לא ניתן להציג את המידע המבוקש"
SOFT_BLOCK_MAX_CHARS = 4000


def assert_archive_page(page: str, context: str) -> None:
    if any(marker in page for marker in CAPTCHA_MARKERS):
        raise ArchiveBlocked(f"The archive demanded a CAPTCHA for {context}; stopping")
    if SOFT_BLOCK_MARKER in page and len(page) < SOFT_BLOCK_MAX_CHARS:
        raise ArchiveBlocked(f"The archive refused to display {context}; stopping")


@dataclass
class ArchiveDocument:
    tik_id: str
    url: str


@dataclass
class ArchiveSearch:
    tik_ids: list[str]
    status: str  # "found" | "empty" | "unrecognized"
    source: dict[str, Any] = field(default_factory=dict)


def text_from_html(raw: bytes | str) -> str:
    page = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    page = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", page, flags=re.S | re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", page))


def _tik_ids(page: str) -> list[str]:
    return sorted(set(TIK_ID_PATTERN.findall(page)), key=int)


class HerzliyaArchiveClient:
    """Async client for the real Herzliya building-permit archive API."""

    def __init__(self, public_client: AsyncPublicClient | None = None, timeout_seconds: float = 20.0):
        self._owns_client = public_client is None
        self._public = public_client or AsyncPublicClient(get_settings().source_cache_dir, timeout_seconds=timeout_seconds)

    async def close(self) -> None:
        if self._owns_client:
            await self._public.aclose()

    async def __aenter__(self) -> "HerzliyaArchiveClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def _page(self, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        raw, meta = await self._public.get(ARCHIVE_URL, params)
        page = raw.decode("utf-8", errors="replace")
        try:
            assert_archive_page(page, str(params.get("prgname")))
        except ArchiveBlocked:
            # Otherwise the refusal is cached and served back as the page for a day.
            self._public.forget(ARCHIVE_URL, params)
            raise
        return page, meta

    async def search(self, gush: str, parcel: str) -> ArchiveSearch:
        """Building-permit files ("tik binyan") for a gush/parcel, with how the archive answered."""
        page, meta = await self._page(
            {
                "appname": "cixpa",
                "prgname": "GetTikimByGush",
                "siteid": SITE_ID,
                "g": gush,
                "h": parcel,
                "m": "",
                "l": "true",
                "arguments": "siteid,g,h,m,l",
            }
        )
        ids = _tik_ids(page)
        status = "found" if ids else ("empty" if any(marker in page for marker in NO_RESULTS_MARKERS) else "unrecognized")
        return ArchiveSearch(tik_ids=ids, status=status, source=meta)

    async def find_tik_ids(self, gush: str, parcel: str) -> list[str]:
        """File ids for a gush/parcel. An unrecognised page raises rather than reading as "no files"."""
        result = await self.search(gush, parcel)
        if result.status == "unrecognized":
            raise HerzliyaArchiveError(f"Unrecognised archive response for gush {gush} parcel {parcel}")
        return result.tik_ids

    async def streets(self) -> dict[str, Any]:
        """Herzliya's street catalogue, de-duplicated by code, with the source it came from."""
        data, meta = await self._public.post_json(STREETS_URL, {"site_id": str(SITE_ID)})
        rows = [
            {"code": str(item["v"]), "name": item["label"]}
            for item in data.get("d", [])
            if str(item.get("k")) == str(HERZLIYA_LAMAS_CODE) and str(item.get("v", "")).isdigit()
        ]
        if not rows:
            raise HerzliyaArchiveError("The municipal street catalogue returned no Herzliya streets")
        unique = {row["code"]: row for row in rows}
        return {"streets": sorted(unique.values(), key=lambda row: (row["name"], row["code"])), "source": meta}

    async def search_address(self, street_code: str) -> dict[str, Any]:
        """Every file on a street, checked against the count the page declares."""
        page, meta = await self._page(
            {
                "appname": "cixpa",
                "prgname": "GetTikimByAddress",
                "siteid": SITE_ID,
                "c": HERZLIYA_LAMAS_CODE,
                "s": int(street_code),
                "h": "",
                "l": "false",
                "arguments": "siteid,c,s,h,l",
            }
        )
        plain = text_from_html(page)
        ids = _tik_ids(page)
        declared = DECLARED_COUNT_PATTERN.search(plain)
        if declared and int(declared.group(1)) != len(ids):
            raise HerzliyaArchiveError(
                f"Archive street result is incomplete: declared {declared.group(1)}, parsed {len(ids)}"
            )
        status = "found" if ids else ("empty" if any(marker in plain or marker in page for marker in NO_RESULTS_MARKERS) else "unrecognized")
        if status == "unrecognized":
            raise HerzliyaArchiveError("Unrecognised municipal street-search response")
        return {
            "tik_ids": ids,
            "declared_count": int(declared.group(1)) if declared else len(ids),
            "status": status,
            "source": meta,
        }

    async def file(self, tik_id: str) -> dict[str, Any]:
        """A building file's page: requests, permits, plans and addresses, as HTML and text."""
        page, meta = await self._page(
            {"appname": "cixpa", "prgname": "GetTikFile", "siteid": SITE_ID, "t": int(tik_id), "arguments": "siteid,t"}
        )
        return {"id": str(tik_id), "source": meta, "text": text_from_html(page), "html": page}

    async def requests_by_address(self, street_code: str, request_type: int) -> tuple[str, dict[str, Any]]:
        """Requests of one type on a street (the public request search, "grp=0&t=<type>").

        The type codes come from GetBakashotTypes for site 121, checked 14.09.2026:
        22 = "בקשה להיתר לתמ"א 38", 1 = "בקשה להיתר". The page is returned whole;
        `neighbour_precedents.parse_request_list` reads it without the applicant column.
        """
        return await self._page(
            {
                "appname": "cixpa",
                "prgname": "GetBakashotByAddress",
                "siteid": SITE_ID,
                "grp": 0,
                "t": int(request_type),
                "c": HERZLIYA_LAMAS_CODE,
                "s": int(street_code),
                "h": "",
                "l": "true",
                "arguments": "siteId,grp,t,c,s,h,l",
            }
        )

    async def request_page(self, request_no: int | str) -> tuple[str, dict[str, Any]]:
        """One permit request's page (GetBakashaFile)."""
        return await self._page(
            {"appname": "cixpa", "prgname": "GetBakashaFile", "siteid": SITE_ID, "b": int(request_no), "arguments": "siteid,b"}
        )

    async def find_documents(self, tik_id: str) -> list[ArchiveDocument]:
        """Downloadable PDF links attached to one building-permit file."""
        page, _ = await self._page(
            {"appname": "cixpa", "prgname": "GetTikDocs", "siteid": SITE_ID, "t": tik_id, "arguments": "siteid,t"}
        )
        links = [
            urljoin(ARCHIVE_URL, html.unescape(href))
            for href in PDF_HREF_PATTERN.findall(page)
            if ".pdf" in href.lower()
        ]
        return [ArchiveDocument(tik_id=tik_id, url=url) for url in links]

    async def download_with_source(self, document: ArchiveDocument) -> tuple[bytes, dict[str, Any]]:
        """The document's bytes and its source record (URL, retrieval time, SHA-256), for evidence."""
        host = httpx.URL(document.url).host
        if host not in ALLOWED_DOCUMENT_HOSTS:
            raise HerzliyaArchiveError(f"Refusing to download from untrusted host: {host}")
        return await self._public.get(document.url)

    async def download(self, document: ArchiveDocument) -> bytes:
        content, _ = await self.download_with_source(document)
        return content
