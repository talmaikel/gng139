"""Bounded Playwright fallback for public municipal pages without stable APIs."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .sources import ARCHIVE, SourceError, utcnow


ALLOWED_HOSTS = {"handasi.complot.co.il", "archive.gis-net.co.il"}
BLOCK_MARKERS = ("captcha", "recaptcha", "התחברות", "login", "access denied")


def _allowed(url: str):
    if urlsplit(url).hostname not in ALLOWED_HOSTS:
        raise SourceError("Playwright navigation blocked: host is not on the public-source allowlist")
    return url


def _archive_calls(html: str):
    return [tuple(int(value.strip()) for value in call.split(","))
            for call in re.findall(r"showArchiveFile\(([^)]+)\)", html)]


def _address(html: str):
    match = re.search(r'top-navbar-info-desc[^>]*>כתובת:</div>\s*<div[^>]*>([^<]+)', html)
    return match.group(1).strip() if match else None


def _pdf_link(html: str):
    match = re.search(r'href="(https://archive\.gis-net\.co\.il/[^"]+\.pdf)"', html)
    return _allowed(match.group(1)) if match else None


class PlaywrightArchive:
    """Use a real browser only after structured public endpoints are unavailable."""

    def __init__(self, *, browser_channel="msedge", headless=True, timeout_ms=45_000):
        self.browser_channel = browser_channel
        self.headless = headless
        self.timeout_ms = timeout_ms

    def collect_request(self, request_id: int, output_dir: Path):
        if not str(request_id).isdigit():
            raise SourceError("Invalid municipal request id")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise SourceError("Playwright is not installed in the project environment") from exc

        request_url = _allowed(ARCHIVE + "?" + urlencode({
            "appname": "cixpa", "prgname": "GetBakashaFile", "siteid": 121,
            "b": int(request_id), "arguments": "siteid,b",
        }))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=self.browser_channel, headless=self.headless)
            context = browser.new_context(accept_downloads=True, locale="he-IL")
            page = context.new_page(); page.set_default_timeout(self.timeout_ms)
            response = page.goto(request_url, wait_until="domcontentloaded")
            if not response or response.status >= 400:
                browser.close(); raise SourceError("Municipal request page was unavailable in Playwright")
            source_html = page.content()
            lowered = source_html.lower()
            if any(marker in lowered for marker in BLOCK_MARKERS):
                browser.close(); raise SourceError("Browser collection stopped at an access or CAPTCHA page")
            calls = _archive_calls(source_html)
            if not calls:
                browser.close(); raise SourceError("No public archive documents were listed for this request")
            # ec/en/bn/m are emitted by the municipal page. Prefer the first listed signed record.
            ec, en, bn, media = calls[0]
            show_url = _allowed(ARCHIVE + "?" + urlencode({
                "appname": "cixpa", "prgname": "ShowPhoto", "siteid": 121,
                "ec": ec, "en": en, "bn": bn, "m": media,
                "arguments": "siteid,ec,en,bn,m",
            }))
            show_response = context.request.get(show_url, timeout=self.timeout_ms)
            if not show_response.ok:
                browser.close(); raise SourceError("Municipal document page was unavailable")
            pdf_url = _pdf_link(show_response.text())
            if not pdf_url:
                browser.close(); raise SourceError("Municipal document page did not expose a public PDF")
            pdf_response = context.request.get(pdf_url, timeout=self.timeout_ms)
            pdf = pdf_response.body()
            browser.close()
        if not pdf_response.ok or not pdf.startswith(b"%PDF"):
            raise SourceError("Public document link did not return a PDF")
        if len(pdf) > 25_000_000:
            raise SourceError("Public document exceeds the 25 MB pilot limit")
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / f"{request_id}-plan.pdf"
        pdf_path.write_bytes(pdf)
        result = {
            "collector": "playwright", "browser_channel": self.browser_channel,
            "request_id": int(request_id), "address": _address(source_html),
            "request_url": request_url, "download_page_url": show_url, "source_url": pdf_url,
            "retrieved_at": utcnow(), "sha256": hashlib.sha256(pdf).hexdigest(),
            "bytes": len(pdf), "path": str(pdf_path),
        }
        (output_dir / f"{request_id}-source.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result
