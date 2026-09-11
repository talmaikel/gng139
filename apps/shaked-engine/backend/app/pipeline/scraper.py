"""
Playwright scaffolding for downloading municipal planning files
(building-permit archive pages, blueprint PDFs/scans) for a given address.
"""

from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import async_playwright


@dataclass
class ScrapedFile:
    source_url: str
    local_path: Path
    content_type: str


class MunicipalArchiveScraper:
    """Targets a municipality's public building-permit archive site."""

    def __init__(self, base_url: str, download_dir: Path):
        self.base_url = base_url
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_permit_files(self, block: str, parcel: str) -> list[ScrapedFile]:
        """
        Navigate to the archive's search page, look up a block/parcel (Gush/Helka),
        and download every attached planning file for the matching permit record.
        """
        downloaded: list[ScrapedFile] = []

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(self.base_url)

                # NOTE: selectors below are placeholders — wire up the real
                # municipal archive's search form and results/download links
                # per-city (Herzliya's archive lives at a different path than
                # a future Tel Aviv one; keep site-specific selectors here,
                # never in app/cities/*, which stays GIS/rules-only).
                await page.fill("input[name='gush']", block)
                await page.fill("input[name='helka']", parcel)
                await page.click("button[type='submit']")
                await page.wait_for_load_state("networkidle")

                for link in await page.locator("a[href$='.pdf']").all():
                    href = await link.get_attribute("href")
                    if not href:
                        continue
                    async with page.expect_download() as download_info:
                        await link.click()
                    download = await download_info.value
                    local_path = self.download_dir / download.suggested_filename
                    await download.save_as(local_path)
                    downloaded.append(
                        ScrapedFile(source_url=href, local_path=local_path, content_type="application/pdf")
                    )
            finally:
                await browser.close()

        return downloaded
