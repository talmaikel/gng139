"""Evidence-preserving Tel Aviv building-file experiment.

The municipal archive is a SharePoint search UI.  The connector deliberately uses
Playwright/Edge, records the complete public document index, downloads only
planning-relevant documents, and never attempts to solve a CAPTCHA or log in.
"""
from __future__ import annotations

import hashlib
import html
import json
import base64
import mimetypes
import re
import shutil
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from .config import CITY_PROFILES, DATA, TEMPLATE_VERSION
from .local_ocr import ocr_rendered_tiles
from .openai_pipeline import PipelineError, render_tiles


ARCHIVE_URL = CITY_PROFILES["tel-aviv"]["archive_url"]
POLICY_URL = CITY_PROFILES["tel-aviv"]["policy_url"]
RULE_VERSION = CITY_PROFILES["tel-aviv"]["rule_version"]
ALLOWED_HOSTS = {"handasa.tel-aviv.gov.il", "www.tel-aviv.gov.il", "gisn.tel-aviv.gov.il"}
STREET_CODE = 481
MAX_DOCUMENT_BYTES = 25_000_000

TARGETS = {
    23: {"address": "דוד המלך 23, תל אביב-יפו", "file_number": "04810230", "parcels": [(6111, 360), (6111, 375)]},
    25: {"address": "דוד המלך 25, תל אביב-יפו", "file_number": "04810250", "parcels": [(6111, 899)]},
    27: {"address": "דוד המלך 27, תל אביב-יפו", "file_number": "04810270", "parcels": [(6111, 657)]},
}

RELEVANT_TERMS = (
    "היתר", "תכנית", "חישוב שטחים", "החלטת ועדה", "ועדת ערר", "תמא 38",
    "תמ\"א 38", "טופס 4", "תעודת גמר", "טופס 1", "יציבות", "תקנה 27", "התחלת עבודה",
)
EXCLUDED_TERMS = ("שומה", "שובר", "תכתובת", "פניות", "התנגדות", "נסח טאבו", "רישוי עסקים")


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def _allowed(url: str):
    if urlsplit(url).hostname not in ALLOWED_HOSTS:
        raise PipelineError("Tel Aviv source host is not allowlisted")
    return url


def _sha256(data: bytes):
    return hashlib.sha256(data).hexdigest()


def _slug(value: str):
    cleaned = re.sub(r"[^0-9A-Za-z\u0590-\u05ff]+", "-", value).strip("-")
    return cleaned[:70] or "document"


def is_relevant(document_type: str):
    normalized = " ".join(document_type.split())
    return any(term in normalized for term in RELEVANT_TERMS) and not any(term in normalized for term in EXCLUDED_TERMS)


@dataclass
class TimingReport:
    address: str
    stages: list[dict] = field(default_factory=list)

    @contextmanager
    def stage(self, name: str, **metadata):
        started_at = utcnow()
        started = time.perf_counter()
        row = {"name": name, "started_at": started_at, **metadata}
        try:
            yield row
            row["state"] = "completed"
        except Exception as exc:
            row["state"] = "failed"
            row["error"] = str(exc)
            raise
        finally:
            row["finished_at"] = utcnow()
            row["seconds"] = round(time.perf_counter() - started, 3)
            self.stages.append(row)

    def total(self):
        return round(sum(stage["seconds"] for stage in self.stages), 3)


def _row_payload(row):
    """JavaScript function body passed to Playwright's row evaluator."""
    return None


class TelAvivArchiveCollector:
    def __init__(self, *, browser_channel="msedge", headless=True, timeout_ms=60_000):
        self.browser_channel = browser_channel
        self.headless = headless
        self.timeout_ms = timeout_ms

    def _accept_terms(self, page):
        button = page.get_by_role("button", name="אשר והמשך")
        try:
            if button.is_visible(timeout=2_000):
                button.click()
        except Exception:
            pass

    def _wait_for_file(self, page, expected_file):
        page.locator("#EngIdGet").wait_for(state="visible", timeout=self.timeout_ms)
        deadline = time.monotonic() + self.timeout_ms / 1000
        while time.monotonic() < deadline:
            if expected_file in page.locator("#EngIdGet").inner_text():
                return
            if page.locator("iframe[src*='recaptcha']").count() and page.locator("#EngIdGet").inner_text().strip() == "מספר תיק":
                time.sleep(.5)
                continue
            time.sleep(.25)
        raise PipelineError(f"Archive did not expose expected building file {expected_file}; access may be blocked")

    def _page_documents(self, page):
        rows = page.locator("tr[id*='_tableitems_row']")
        payload = rows.evaluate_all("""
            rows => rows.map(row => {
              const cells = Array.from(row.querySelectorAll(':scope > td'));
              const link = row.querySelector("a[href*='DocViewer']");
              const icon = cells[2] && cells[2].querySelector('img');
              const preview = row.querySelector("img[onclick*='preview.aspx']");
              if (!link) return null;
              const id = new URL(link.href).searchParams.get('id');
              const clean = i => cells[i] ? (cells[i].innerText || '').trim() : '';
              return {
                document_id: id,
                document_type: (link.textContent || '').trim(),
                file_type: icon ? (icon.alt || '').toLowerCase() : '',
                document_date: clean(4),
                request_number: clean(5),
                online_request_number: clean(6),
                permit_number: clean(7),
                viewer_url: link.href,
                download_url: new URL(link.getAttribute('downloadurl'), location.origin).href,
                preview_path: preview ? (preview.getAttribute('onclick') || '').match(/'([^']*preview\\.aspx[^']*)'/)?.[1] || null : null
              };
            }).filter(Boolean)
        """)
        return payload

    def _collect_index(self, page):
        documents = []
        seen = set()
        page_number = 1
        while True:
            current = self._page_documents(page)
            new = [doc for doc in current if doc["document_id"] not in seen]
            for doc in new:
                seen.add(doc["document_id"])
                doc["page_number"] = page_number
                doc["relevant"] = is_relevant(doc["document_type"])
                documents.append(doc)
            next_number = page_number + 1
            next_link = page.locator(f"#PageLink_{next_number}")
            if next_link.count() == 0:
                break
            prior = current[0]["document_id"] if current else None
            next_link.click()
            try:
                page.wait_for_function(
                    """prior => {
                      const link = document.querySelector("tr[id*='_tableitems_row'] a[href*='DocViewer']");
                      return link && new URL(link.href).searchParams.get('id') !== prior;
                    }""",
                    arg=prior,
                    timeout=self.timeout_ms,
                )
            except Exception as exc:
                raise PipelineError(f"Archive pagination did not finish loading page {next_number}") from exc
            refreshed = self._page_documents(page)
            if not refreshed or refreshed[0]["document_id"] == prior:
                raise PipelineError(f"Archive pagination did not advance to page {next_number}")
            page_number = next_number
        return documents, page_number

    def _extension(self, response, data, declared, api_filename=None):
        if api_filename:
            suffix = Path(api_filename).suffix.lower()
            if suffix:
                return suffix
        disposition = response.headers.get("content-disposition", "")
        match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
        if match:
            suffix = Path(match.group(1)).suffix.lower()
            if suffix:
                return suffix
        if data.startswith(b"%PDF"):
            return ".pdf"
        if data.startswith(b"PK\x03\x04"):
            return ".zip"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith(b"\x89PNG"):
            return ".png"
        mapping = {"dwf": ".dwf", "dwfx": ".dwfx", "pdf": ".pdf", "jpg": ".jpg", "jpeg": ".jpg", "png": ".png", "zip": ".zip"}
        return mapping.get(declared, mimetypes.guess_extension(response.headers.get("content-type", "").split(";")[0]) or ".bin")

    def _unwrap_api_file(self, data: bytes):
        """The municipal API returns JSON-inside-JSON with a Base64 file buffer."""
        if data.startswith((b"%PDF", b"PK\x03\x04", b"\xff\xd8\xff", b"\x89PNG")):
            return data, None
        try:
            value = json.loads(data.decode("utf-8-sig"))
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, dict) and value.get("buffer"):
                return base64.b64decode(value["buffer"], validate=True), value.get("fileName")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            pass
        return data, None

    def _download(self, request, doc, directory: Path):
        url = _allowed(doc["download_url"])
        response = request.get(url, timeout=self.timeout_ms)
        if response.status == 429:
            raise PipelineError("Tel Aviv archive returned HTTP 429; checkpoint saved")
        if not response.ok:
            raise PipelineError(f"Document {doc['document_id']} returned HTTP {response.status}")
        data, api_filename = self._unwrap_api_file(response.body())
        if len(data) > MAX_DOCUMENT_BYTES:
            return {"state": "too_large", "bytes": len(data)}
        suffix = self._extension(response, data, doc["file_type"], api_filename)
        filename = f"{doc['document_date'].replace('/', '-')}_{doc['document_id']}_{_slug(doc['document_type'])}{suffix}"
        path = directory / filename
        if path.exists() and _sha256(path.read_bytes()) == _sha256(data):
            return {"state": "cached", "bytes": len(data), "sha256": _sha256(data), "path": str(path)}
        path.write_bytes(data)
        return {"state": "downloaded", "bytes": len(data), "sha256": _sha256(data), "path": str(path)}

    def collect(self, house_number: int, output_dir: Path, timing: TimingReport):
        target = TARGETS[house_number]
        search_url = _allowed(f"{ARCHIVE_URL}?partialAddress={STREET_CODE}_{house_number}")
        output_dir.mkdir(parents=True, exist_ok=True)
        documents_dir = output_dir / "documents"
        documents_dir.mkdir(exist_ok=True)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PipelineError("Playwright is not installed") from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=self.browser_channel, headless=self.headless)
            context = browser.new_context(accept_downloads=True, locale="he-IL")
            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                with timing.stage("discovery_and_index") as stage:
                    page.goto(search_url, wait_until="domcontentloaded")
                    self._accept_terms(page)
                    if search_url not in page.url:
                        page.goto(search_url, wait_until="domcontentloaded")
                    self._wait_for_file(page, target["file_number"])
                    file_text = page.locator("#EngIdGet").inner_text()
                    info_text = page.locator("#EngGetInfo").inner_text()
                    if target["file_number"] not in file_text or str(house_number) not in info_text:
                        raise PipelineError("Archive result identity did not match the requested address")
                    documents, pages = self._collect_index(page)
                    stage.update({"documents_indexed": len(documents), "pages": pages})
                manifest = {
                    "city": "tel-aviv", "city_label": "תל אביב-יפו", "address": target["address"],
                    "house_number": house_number, "street_code": STREET_CODE,
                    "building_file_number": target["file_number"],
                    "parcels": [{"gush": gush, "parcel": parcel} for gush, parcel in target["parcels"]],
                    "source_url": search_url, "retrieved_at": utcnow(), "collector": "playwright-msedge",
                    "documents": documents,
                }
                (output_dir / "document-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                with timing.stage("downloads") as stage:
                    selected = [doc for doc in documents if doc["relevant"]]
                    failures = 0
                    for doc in selected:
                        try:
                            doc["download"] = self._download(context.request, doc, documents_dir)
                        except Exception as exc:
                            doc["download"] = {"state": "failed", "error": str(exc)}
                            failures += 1
                            if "429" in str(exc):
                                break
                        time.sleep(.2)
                    stage.update({"selected": len(selected), "downloaded_or_cached": sum(d.get("download", {}).get("state") in ("downloaded", "cached") for d in selected), "failed": failures})
                (output_dir / "document-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                return manifest
            finally:
                browser.close()


def _safe_unzip(path: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    extracted = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist()[:100]:
            target = (destination / info.filename).resolve()
            if destination.resolve() not in target.parents or info.is_dir():
                continue
            total += info.file_size
            if total > 100_000_000:
                raise PipelineError("ZIP exceeds the 100 MB expanded safety limit")
            archive.extract(info, destination)
            extracted.append(target)
    return extracted


def _ocr_candidates(records, document):
    candidates = []
    patterns = {
        "permit_date": re.compile(r"\b([0-3]?\d[./-][01]?\d[./-](?:19|20)?\d{2})\b"),
        "units": re.compile(r"(?:יח[\"'״]?ד|דירות).{0,25}?(\d{1,3})|\b(\d{1,3}).{0,25}?(?:יח[\"'״]?ד|דירות)"),
        "floors": re.compile(r"(?:קומות|קומה).{0,20}?(\d{1,2})|\b(\d{1,2}).{0,20}?(?:קומות|קומה)"),
        "area_m2": re.compile(r"(?:שטח).{0,35}?(\d{2,5}(?:[.,]\d{1,2})?)"),
    }
    for record in records:
        text_value = Path(record["text"]).read_text(encoding="utf-8", errors="replace")
        compact = " ".join(text_value.split())
        for field_name, pattern in patterns.items():
            for match in list(pattern.finditer(compact))[:3]:
                value = next((group for group in match.groups() if group), match.group(0))
                start = max(0, match.start() - 45)
                end = min(len(compact), match.end() + 45)
                candidates.append({
                    "id": str(uuid.uuid4()), "field": field_name, "proposed_value": value,
                    "document_id": document["document_id"], "document_type": document["document_type"],
                    "tile": record["id"], "page": record["page"], "quote": compact[start:end],
                    "image": record["image"], "approved": None, "correction": None,
                })
    return candidates


def process_ocr(manifest: dict, output_dir: Path, timing: TimingReport):
    ocr_root = output_dir / "ocr"
    all_candidates = []
    processed = []
    for document in manifest["documents"]:
        download = document.get("download") or {}
        if download.get("state") not in ("downloaded", "cached"):
            if document.get("relevant"):
                processed.append({"document_id": document["document_id"], "state": download.get("state", "not_downloaded")})
            continue
        source_path = Path(download["path"])
        inputs = [source_path]
        if source_path.suffix.lower() == ".zip":
            try:
                inputs = _safe_unzip(source_path, source_path.parent / "unpacked" / document["document_id"])
            except Exception as exc:
                processed.append({"document_id": document["document_id"], "state": "zip_failed", "error": str(exc)})
                continue
        supported = [path for path in inputs if path.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")]
        if not supported:
            processed.append({"document_id": document["document_id"], "state": "unsupported_format", "file_type": document["file_type"]})
            continue
        document_records = []
        state = "completed"
        error = None
        for index, path in enumerate(supported[:20], 1):
            item_root = ocr_root / document["document_id"] / str(index)
            try:
                if path.suffix.lower() == ".pdf":
                    with timing.stage("render", document_id=document["document_id"], input=str(path)) as stage:
                        tiles = render_tiles(path, item_root / "tiles", max_tiles=24)
                        stage["tiles"] = len(tiles)
                else:
                    with timing.stage("render", document_id=document["document_id"], input=str(path)) as stage:
                        item_root.joinpath("tiles").mkdir(parents=True, exist_ok=True)
                        copied = item_root / "tiles" / f"p1-r1-c1{path.suffix.lower()}"
                        shutil.copy2(path, copied)
                        tiles = [{"id": "p1-r1-c1", "page": 1, "path": copied}]
                        stage["tiles"] = 1
                with timing.stage("ocr", document_id=document["document_id"], input=str(path)) as stage:
                    records = ocr_rendered_tiles(tiles, item_root / "text")
                    stage.update({"tiles": len(records), "characters": sum(row["characters"] for row in records)})
                document_records.extend(records)
            except Exception as exc:
                state, error = "failed", str(exc)
                break
        all_candidates.extend(_ocr_candidates(document_records, document))
        processed.append({"document_id": document["document_id"], "state": state, "error": error, "tiles": len(document_records), "characters": sum(row["characters"] for row in document_records)})
    report = {"address": manifest["address"], "created_at": utcnow(), "documents": processed, "candidates": all_candidates}
    (output_dir / "ocr-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def current_status_assessment(manifest: dict):
    recent = []
    for doc in manifest["documents"]:
        text_value = doc["document_type"]
        year = None
        match = re.search(r"^(20\d{2})", doc.get("request_number", ""))
        if match:
            year = int(match.group(1))
        try:
            date_year = int(doc.get("document_date", "").split("/")[-1])
        except (ValueError, IndexError):
            date_year = None
        if ("38" in text_value or "היתר" in text_value or "תחילת עבודה" in text_value) and (date_year or year or 0) >= 2021:
            recent.append(doc)
    if recent:
        return {
            "status": "not_suitable_currently", "label": "לא מתאים לפי המצב הנוכחי",
            "reason": "בתיק מופיע הליך התחדשות/היתר עדכני; הנכס אינו מוצג כהזדמנות חדשה.",
            "evidence_document_ids": [doc["document_id"] for doc in recent[:10]],
        }
    return {"status": "needs_verification", "label": "דורש אימות", "reason": "לא נמצא חסם עדכני באינדקס, אך נדרש אימות OCR ובסיס תכנוני."}


def build_pre_review_dossier(manifest: dict, ocr_report: dict):
    source = {"url": manifest["source_url"], "retrieved_at": manifest["retrieved_at"], "method": "Playwright public archive index"}
    assessment = current_status_assessment(manifest)
    fields = {
        "address": {"value": manifest["address"], "certainty": "official", "source": source, "location": "כותרת תיק בניין", "method": "structured browser extraction"},
        "building_file_number": {"value": manifest["building_file_number"], "certainty": "official", "source": source, "location": "פרטי תיק בניין", "method": "structured browser extraction"},
        "gush": {"value": sorted({p["gush"] for p in manifest["parcels"]}), "certainty": "official", "source": source, "location": "גושים/חלקות בתיק", "method": "structured browser extraction"},
        "parcel": {"value": [p["parcel"] for p in manifest["parcels"]], "certainty": "official", "source": source, "location": "גושים/חלקות בתיק", "method": "structured browser extraction"},
    }
    for key in ("units", "floors", "permit_date", "original_permit_number", "existing_legal_area", "planning_basis", "overriding_plans_checked"):
        fields[key] = {"value": None, "certainty": "missing", "source": None, "location": None, "method": None}
    checks = [
        {"id": "current_redevelopment", "label": "אין הליך התחדשות/היתר עדכני החוסם הזדמנות חדשה", "status": "failed" if assessment["status"] == "not_suitable_currently" else "unknown", "source_url": manifest["source_url"], "page": None},
        {"id": "planning_basis", "label": "בסיס תכנוני נכסי מאומת", "status": "unknown", "source_url": POLICY_URL, "page": None},
        {"id": "human_ocr_review", "label": "אימות אנושי לשדות OCR קריטיים", "status": "unknown", "source_url": manifest["source_url"], "page": None},
    ]
    return {
        "city": "tel-aviv", "building_id": f"tel-aviv-file:{manifest['building_file_number']}",
        "entity_keys": [f"parcel:{p['gush']}:{p['parcel']}" for p in manifest["parcels"]],
        "status": "needs_verification", "eligibility_status": assessment["status"], "eligibility": assessment,
        "fields": fields, "geometry": {"type": "Point", "coordinates": [34.7868, 32.0816]},
        "parcels": [{"id": f"parcel:{p['gush']}:{p['parcel']}", "gush": p["gush"], "parcel": p["parcel"], "geometry": None, "source": source} for p in manifest["parcels"]],
        "checks": checks, "gaps": ["ממתינים לאישור אנושי של מועמדי ה-OCR", "לא הוכן חישוב כלכלי ללא בסיס זכויות מאומת"],
        "source_issues": [row for row in ocr_report["documents"] if row["state"] != "completed"],
        "archive_records": [{"id": manifest["building_file_number"], "source": source, "document_count": len(manifest["documents"])}],
        "documents": [{"id": row["document_id"], "source": {"url": next(d["viewer_url"] for d in manifest["documents"] if d["document_id"] == row["document_id"]), "retrieved_at": manifest["retrieved_at"]}, "state": row["state"]} for row in ocr_report["documents"]],
        "scenario": None, "rights_analysis": None, "rule_version": RULE_VERSION, "template_version": TEMPLATE_VERSION,
        "policy_source": POLICY_URL, "created_at": utcnow(), "building_source": source,
        "human_review": {"state": "pending", "candidate_count": len(ocr_report["candidates"])},
    }


def write_review_package(dossiers: list[dict], ocr_reports: list[dict], root: Path):
    review_dir = root / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    sections = []
    for dossier, report in zip(dossiers, ocr_reports):
        candidates.extend(report["candidates"])
        rows = []
        for candidate in report["candidates"]:
            image_path = Path(candidate["image"])
            try:
                relative = image_path.relative_to(root.parent.parent.parent.parent)
            except ValueError:
                relative = image_path
            rows.append(
                "<tr><td>{field}</td><td>{value}</td><td>{doctype}</td><td>{page}/{tile}</td><td>{quote}</td><td><a href=\"{image}\">פתיחת ראיה</a></td></tr>".format(
                    field=html.escape(candidate["field"]), value=html.escape(str(candidate["proposed_value"])),
                    doctype=html.escape(candidate["document_type"]), page=candidate["page"], tile=html.escape(candidate["tile"]),
                    quote=html.escape(candidate["quote"]), image=html.escape(str(image_path.resolve())),
                )
            )
        sections.append(f"<h2>{html.escape(dossier['fields']['address']['value'])}</h2><p>{html.escape(dossier['eligibility']['label'])}: {html.escape(dossier['eligibility']['reason'])}</p><table><tr><th>שדה</th><th>ערך</th><th>מסמך</th><th>עמוד/אריח</th><th>ציטוט OCR</th><th>ראיה</th></tr>{''.join(rows)}</table>")
    decisions = {"state": "pending_human_review", "created_at": utcnow(), "instructions": "Set approved to true/false and optionally correction for every candidate used in the final dossier.", "candidates": candidates}
    (review_dir / "review-decisions.json").write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    document = """<!doctype html><html lang=\"he\" dir=\"rtl\"><meta charset=\"utf-8\"><title>אימות OCR — דוד המלך</title><style>body{font-family:Arial;margin:32px;color:#14231f}table{border-collapse:collapse;width:100%;margin-bottom:40px}th,td{border:1px solid #bbb;padding:8px;vertical-align:top}th{background:#14231f;color:white}a{color:#70412c}</style><h1>חבילת אימות OCR — דוד המלך 23, 25, 27</h1><p>אין לאשר ערך לפני בדיקת תמונת המקור. התיקים הסופיים לא ייצרו עד לאישור.</p>""" + "".join(sections) + "</html>"
    (review_dir / "index.html").write_text(document, encoding="utf-8")
    return review_dir / "index.html", review_dir / "review-decisions.json"


def finalize_reviewed_dossier(pre_review: dict, decisions: dict):
    """Create an immutable dossier only after every OCR candidate was reviewed."""
    pending = [row for row in decisions.get("candidates", []) if row.get("approved") is None]
    if pending:
        raise PipelineError(f"Human review is incomplete: {len(pending)} candidates are pending")
    dossier = json.loads(json.dumps(pre_review, ensure_ascii=False))
    accepted = []
    field_map = {
        "permit_date": "permit_date", "units": "units", "floors": "floors",
        "area_m2": "existing_legal_area", "permit_number": "original_permit_number",
    }
    observations = {}
    for row in decisions.get("candidates", []):
        if not row.get("approved"):
            continue
        field_name = field_map.get(row["field"])
        if not field_name:
            continue
        value = row.get("correction") if row.get("correction") not in (None, "") else row["proposed_value"]
        if field_name in ("units", "floors"):
            try:
                value = int(str(value).replace(",", ""))
            except ValueError:
                pass
        elif field_name == "existing_legal_area":
            try:
                value = float(str(value).replace(",", "."))
            except ValueError:
                pass
        source_doc = next((doc for doc in dossier["documents"] if doc["id"] == row["document_id"]), None)
        evidence = {
            "value": value, "certainty": "manually_verified",
            "source": source_doc["source"] if source_doc else dossier["building_source"],
            "location": f"עמוד {row['page']}, tile {row['tile']}", "method": "Tesseract plus human visual review",
            "quote": row.get("quote"),
        }
        observations.setdefault(field_name, []).append(evidence)
        accepted.append({"candidate_id": row["id"], "field": field_name, "value": value})
    for field_name, rows in observations.items():
        distinct = {json.dumps(row["value"], ensure_ascii=False, sort_keys=True) for row in rows}
        dossier["fields"][field_name] = rows[0] if len(distinct) == 1 else {
            "value": None, "certainty": "conflict", "source": None, "location": None,
            "method": "human-reviewed observations conflict", "observations": rows,
        }
    dossier["human_review"] = {"state": "completed", "reviewed_at": utcnow(), "accepted": accepted}
    dossier["checks"] = [dict(row, status="passed") if row["id"] == "human_ocr_review" else row for row in dossier["checks"]]
    dossier["gaps"] = [gap for gap in dossier["gaps"] if "OCR" not in gap]
    dossier["created_at"] = utcnow()
    stable = dict(dossier)
    stable.pop("created_at", None)
    dossier["id"] = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return dossier
