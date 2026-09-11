"""
Live client for Herzliya's municipal building-permit archive ("Tik Binyan"),
a legacy CGI-style HTTP API at handasi.complot.co.il — a plain GET/query-string
API, not a JS-rendered page. This is why Herzliya's real scraping doesn't need
`app/pipeline/scraper.py`'s Playwright scaffold; that scaffold stays as the
fallback for a city whose archive turns out to require browser rendering.
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

ARCHIVE_URL = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"
SITE_ID = 121

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
USER_AGENT = "Mozilla/5.0 (compatible; ShakedEngine/1.0)"


class HerzliyaArchiveError(RuntimeError):
    pass


@dataclass
class ArchiveDocument:
    tik_id: str
    url: str


class HerzliyaArchiveClient:
    """Async client for the real Herzliya building-permit archive API."""

    def __init__(self, timeout_seconds: float = 20.0):
        self._client = httpx.AsyncClient(timeout=timeout_seconds, headers={"User-Agent": USER_AGENT})

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "HerzliyaArchiveClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def find_tik_ids(self, gush: str, parcel: str) -> list[str]:
        """Look up building-permit file ("tik binyan") ids for a gush/parcel."""
        params = {
            "appname": "cixpa",
            "prgname": "GetTikimByGush",
            "siteid": SITE_ID,
            "g": gush,
            "h": parcel,
            "m": "",
            "l": "true",
            "arguments": "siteid,g,h,m,l",
        }
        response = await self._client.get(ARCHIVE_URL, params=params)
        response.raise_for_status()
        return sorted(set(TIK_ID_PATTERN.findall(response.text)), key=int)

    async def find_documents(self, tik_id: str) -> list[ArchiveDocument]:
        """Return downloadable PDF links attached to one building-permit file."""
        params = {
            "appname": "cixpa",
            "prgname": "GetTikDocs",
            "siteid": SITE_ID,
            "t": tik_id,
            "arguments": "siteid,t",
        }
        response = await self._client.get(ARCHIVE_URL, params=params)
        response.raise_for_status()
        links = [
            urljoin(ARCHIVE_URL, href)
            for href in PDF_HREF_PATTERN.findall(response.text)
            if ".pdf" in href.lower()
        ]
        return [ArchiveDocument(tik_id=tik_id, url=url) for url in links]

    async def download(self, document: ArchiveDocument) -> bytes:
        host = httpx.URL(document.url).host
        if host not in ALLOWED_DOCUMENT_HOSTS:
            raise HerzliyaArchiveError(f"Refusing to download from untrusted host: {host}")
        response = await self._client.get(document.url)
        response.raise_for_status()
        return response.content
