"""
Multi-tier extraction of total building area from a (possibly degraded)
legacy blueprint scan:

  1. Local Tesseract OCR (Hebrew + English) over the pre-processed legend crop,
     parsed with strict regex patterns for area rows.
  2. If step 1's confidence is low or no rows matched, fall back to
     OpenAI gpt-4o-mini with a structured-output JSON schema, which can read
     complex legends and sum/derive the total from individual unit areas.
"""

import json
import re
from dataclasses import dataclass, field

import numpy as np
import pytesseract
from openai import AsyncOpenAI
from PIL import Image

from app.core.config import get_settings

settings = get_settings()
pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

# Matches rows like: "שטח כולל 245.50 מ"ר" or "Total area: 245.50 sqm"
AREA_ROW_PATTERN = re.compile(
    r"(שטח\s*(כולל|בניה|עיקרי)|total\s*area)\D{0,10}([\d,.]+)\s*(מ\"?ר|sq\s*m|m2|sqm)?",
    re.IGNORECASE,
)

# W10 (#115): the same legend sometimes states how much of the building is
# residential use -- "שטח למגורים" / "שטח עיקרי למגורים" / "סה״כ מגורים" --
# distinct from AREA_ROW_PATTERN's "שטח כולל/עיקרי" rows, which don't say
# residential vs. any other use. Matched opportunistically, same as the unit
# schedule: most sheets won't have it, and that's not a failure.
RESIDENTIAL_AREA_ROW_PATTERN = re.compile(
    r"שטח\s*(?:עיקרי\s*)?ל?מגורים\D{0,10}([\d,.]+)\s*(?:מ\"?ר|sq\s*m|m2|sqm)?",
    re.IGNORECASE,
)

# One schedule row per apartment: a unit number, optionally a floor, and an
# area. Two orderings are tried because Hebrew RTL text comes back from
# Tesseract with the number on either side depending on the sheet.
UNIT_ROW_PATTERNS = (
    re.compile(
        r"(?:דירה|יח[\"'״]?ד)\s*[:\-]?\s*(?P<label>\d{1,3}[א-ת]?)"
        r"(?:\D{0,15}?קומה\s*[:\-]?\s*(?P<floor>-?\d{1,2}|קרקע))?"
        # 1-4 digits on purpose: a 4-digit value here is almost always the
        # building total misplaced in the unit column, and it has to be matched
        # to be flagged. Narrowing the pattern instead would drop it silently.
        r"\D{0,20}?(?P<area>\d{1,4}(?:[.,]\d{1,2})?)\s*(?:מ[\"'״]?ר|sqm|m2)",
    ),
    # Column layout: "12   3   78.50" -- label, floor, area separated by gaps.
    re.compile(
        r"^\s*(?P<label>\d{1,3})\s+(?P<floor>-?\d{1,2})\s+(?P<area>\d{1,4}(?:[.,]\d{1,2})?)\s*$",
        re.MULTILINE,
    ),
)

# Declared unit count, e.g. "סה\"כ 6 יחידות דיור".
UNIT_COUNT_PATTERNS = (
    re.compile(r"(?:סה[\"'״]?כ|סך\s*הכל)?\s*(?:יח[\"'״]?ד|יחידות\s*דיור|דירות)\D{0,12}?(\d{1,3})\b"),
    re.compile(r"\b(\d{1,3})\s*(?:יח[\"'״]?ד|יחידות\s*דיור|דירות)"),
)

# Declared floor count for the whole building, e.g. "מספר קומות: 7" or
# "בניין בן 7 קומות". Distinct from a unit row's own `floor` group in
# UNIT_ROW_PATTERNS (which apartment sits on which floor) -- this is how
# many floors the permit describes the building as having overall.
FLOOR_COUNT_PATTERNS = (
    re.compile(r"(?:מספר\s*)?קומות\D{0,10}?(\d{1,2})\b"),
    re.compile(r"\bבן\s*[\-]?\s*(\d{1,2})\s*קומות\b"),
)

MIN_OCR_CONFIDENCE = 60.0

# Bounds for a single dwelling unit, deliberately wider than any normal
# apartment: the point is to reject a floor number, a permit year or a
# building total that landed in the area column, not to second-guess an
# unusual but real apartment.
MIN_PLAUSIBLE_UNIT_SQM = 15.0
MAX_PLAUSIBLE_UNIT_SQM = 400.0

# Bounds-based sanity check on an extracted area, independent of how it was
# read. Catches grossly wrong values (e.g. a gush/tik number mistaken for an
# area) -- it will NOT catch a plausible-looking wrong number (e.g. a plot
# number that happens to fall in a normal building-size range), which is why
# the AI fallback's result is never trusted as fact regardless of whether it
# passes this check; see `requires_human_review` below.
MIN_PLAUSIBLE_AREA_SQM = 20.0
MAX_PLAUSIBLE_AREA_SQM = 5000.0
MAX_AREA_TO_PLOT_RATIO = 3.0  # generous allowance for a multi-floor building on a small plot


def _check_plausibility(area_sqm: float | None, plot_area_sqm: float | None) -> tuple[bool, str | None]:
    if area_sqm is None:
        return False, "No area was extracted"
    if area_sqm < MIN_PLAUSIBLE_AREA_SQM:
        return False, f"{area_sqm} sqm is implausibly small for a building"
    if area_sqm > MAX_PLAUSIBLE_AREA_SQM:
        return False, f"{area_sqm} sqm exceeds the {MAX_PLAUSIBLE_AREA_SQM} sqm ceiling for this archive's typical low-rise permits"
    if plot_area_sqm and area_sqm > plot_area_sqm * MAX_AREA_TO_PLOT_RATIO:
        return False, f"{area_sqm} sqm exceeds {MAX_AREA_TO_PLOT_RATIO}x the plot area ({plot_area_sqm} sqm)"
    return True, None

@dataclass
class DwellingUnitReading:
    """One apartment as read off a schedule, before any human confirms it."""

    area_sqm: float | None
    unit_label: str | None = None
    floor: str | None = None
    raw_text: str | None = None
    is_plausible: bool = True
    plausibility_reason: str | None = None


def _unit_plausibility(area_sqm: float | None) -> tuple[bool, str | None]:
    if area_sqm is None:
        return False, "No area was read for this unit"
    if area_sqm < MIN_PLAUSIBLE_UNIT_SQM:
        return False, f"{area_sqm} sqm is too small to be a dwelling unit"
    if area_sqm > MAX_PLAUSIBLE_UNIT_SQM:
        return False, f"{area_sqm} sqm is too large for a single unit; likely a building total"
    return True, None


def _parse_unit_rows(text: str) -> list[DwellingUnitReading]:
    """Read per-apartment schedule rows out of OCR text.

    Rows that fail the per-unit bounds check are kept, flagged rather than
    dropped: a schedule where three of eight rows are implausible is a
    different (and more informative) situation than one where the parser
    found nothing, and only the caller can tell them apart.

    De-duplicated on the unit label because the two patterns overlap on some
    layouts, and because a schedule repeated in a title block would otherwise
    double the unit count.
    """
    readings: list[DwellingUnitReading] = []
    seen_labels: set[str] = set()

    for pattern in UNIT_ROW_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            label = (groups.get("label") or "").strip() or None
            if label and label in seen_labels:
                continue
            try:
                area = float(groups["area"].replace(",", "."))
            except (TypeError, ValueError):
                continue
            is_plausible, reason = _unit_plausibility(area)
            readings.append(
                DwellingUnitReading(
                    area_sqm=area,
                    unit_label=label,
                    floor=(groups.get("floor") or "").strip() or None,
                    raw_text=" ".join(match.group(0).split()),
                    is_plausible=is_plausible,
                    plausibility_reason=reason,
                )
            )
            if label:
                seen_labels.add(label)

    return readings


def _parse_residential_area(text: str) -> float | None:
    """The legend's own residential-use figure, when it states one.

    Returns the first match rather than summing multiple: a legend that
    states residential area once did not intend it to be added to itself,
    and a repeated title-block line is the same value twice, not two rows.
    """
    match = RESIDENTIAL_AREA_ROW_PATTERN.search(text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_unit_count(text: str) -> int | None:
    for pattern in UNIT_COUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                count = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= count <= 300:
                return count
    return None


def _parse_floor_count(text: str) -> int | None:
    """The building's own declared floor count, when the legend states one.

    Unverified against a real scan (no sample with this exact wording was
    available while writing it) -- opportunistic like the rest of this
    module: taken when found, left None otherwise, and never the only
    source a floor count can come from (see worker.py, which only ever
    displays a disagreement against the existing official reading, never
    overwrites it).
    """
    for pattern in FLOOR_COUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                count = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= count <= 40:
                return count
    return None


EXTRACTION_JSON_SCHEMA = {
    "name": "building_area_extraction",
    "schema": {
        "type": "object",
        "properties": {
            "total_building_area_sqm": {"type": ["number", "null"]},
            # Was a bare list of numbers whose result was never read. Now a
            # row per apartment, because compensation is allocated per
            # household: an unlabelled 78.5 cannot be attributed to anyone.
            "units": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "unit_label": {"type": ["string", "null"]},
                        "floor": {"type": ["string", "null"]},
                        "area_sqm": {"type": ["number", "null"]},
                    },
                    "required": ["unit_label", "floor", "area_sqm"],
                    "additionalProperties": False,
                },
            },
            "declared_unit_count": {"type": ["integer", "null"]},
            # W10 (#115): how much of total_building_area_sqm is residential
            # use, when the legend states it -- feeds the §70א 70%-residential
            # gate as a candidate, never as a decided answer (see worker.py).
            "residential_area_sqm": {"type": ["number", "null"]},
            # The building's own declared floor count, when the legend
            # states one -- distinct from a unit row's individual floor.
            "declared_floor_count": {"type": ["integer", "null"]},
            "confidence": {"type": "number"},
            "notes": {"type": ["string", "null"]},
        },
        # OpenAI's strict structured-output mode requires every property to be
        # listed here, even ones that are semantically optional/nullable above.
        "required": ["total_building_area_sqm", "units", "declared_unit_count",
                    "residential_area_sqm", "declared_floor_count", "confidence", "notes"],
        "additionalProperties": False,
    },
    "strict": True,
}


@dataclass
class ExtractionResult:
    total_building_area_sqm: float | None
    confidence: float
    method: str  # "tesseract_regex" | "openai_gpt4o_mini"
    is_plausible: bool
    plausibility_reason: str | None
    # True whenever this figure should never be treated as verified fact:
    # every AI-fallback result (regardless of how plausible it looks -- see
    # _check_plausibility's docstring), plus any result that failed the
    # bounds check outright.
    requires_human_review: bool
    raw_text: str | None = None
    notes: str | None = None

    # Per-apartment detail, when the sheet carried a unit schedule. Empty is
    # the normal case for a sheet that only states a building total -- it is
    # not a failure, and `total_building_area_sqm` stands on its own.
    units: list[DwellingUnitReading] = field(default_factory=list)
    # Unit count as *declared* on the sheet ("סה"כ 6 יח"ד"), which is not the
    # same thing as len(units): a schedule can be partly illegible while the
    # summary line is readable, and the disagreement is worth keeping.
    declared_unit_count: int | None = None
    # W10 (#115): the legend's own residential-area figure, when it states
    # one. Left unvalidated against total_building_area_sqm here -- the
    # caller (worker.py) already has to re-check it against whichever total
    # it ends up selecting, which may come from a different page.
    residential_area_sqm: float | None = None
    # The building's own declared floor count, when the legend states one.
    # Never used to overwrite the existing official floor count (see
    # worker.py) -- only to display a disagreement, the same caution as
    # every other OCR-read figure in this module.
    declared_floor_count: int | None = None

    @property
    def units_total_area_sqm(self) -> float | None:
        areas = [u.area_sqm for u in self.units if u.area_sqm is not None]
        return round(sum(areas), 2) if areas else None


def _extract_via_tesseract(legend_crop: np.ndarray, plot_area_sqm: float | None) -> ExtractionResult:
    image = Image.fromarray(legend_crop)
    ocr_data = pytesseract.image_to_data(
        image, lang=settings.tesseract_lang, output_type=pytesseract.Output.DICT
    )
    confidences = [float(c) for c in ocr_data.get("conf", []) if c not in ("-1", -1)]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    text = pytesseract.image_to_string(image, lang=settings.tesseract_lang)
    matches = AREA_ROW_PATTERN.findall(text)

    total_area = None
    if matches:
        # Prefer an explicit "total" row; otherwise sum the individual matches.
        totals = [m for m in matches if m[1] in ("כולל", "")]
        values = [float(m[2].replace(",", "")) for m in (totals or matches)]
        total_area = sum(values) if not totals else values[0]

    units = _parse_unit_rows(text)
    declared_unit_count = _parse_unit_count(text)
    residential_area_sqm = _parse_residential_area(text)
    declared_floor_count = _parse_floor_count(text)

    # A schedule that lists every apartment but no total is common on older
    # sheets. Summing the plausible unit rows is a legitimate reading of that
    # sheet -- but only when every row read cleanly, since summing a partly
    # illegible schedule silently understates the building.
    if total_area is None and units and all(u.is_plausible for u in units):
        total_area = round(sum(u.area_sqm for u in units), 2)

    is_plausible, plausibility_reason = _check_plausibility(total_area, plot_area_sqm)
    return ExtractionResult(
        total_building_area_sqm=total_area,
        confidence=mean_confidence,
        method="tesseract_regex",
        is_plausible=is_plausible,
        plausibility_reason=plausibility_reason,
        requires_human_review=not is_plausible,
        raw_text=text,
        units=units,
        declared_unit_count=declared_unit_count,
        residential_area_sqm=residential_area_sqm,
        declared_floor_count=declared_floor_count,
    )


async def _extract_via_openai(image_bytes: bytes, plot_area_sqm: float | None) -> ExtractionResult:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured; cannot use the AI fallback extractor")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    import base64

    encoded = base64.b64encode(image_bytes).decode("ascii")

    response = await client.chat.completions.create(
        model=settings.openai_extraction_model,
        response_format={"type": "json_schema", "json_schema": EXTRACTION_JSON_SCHEMA},
        messages=[
            {
                "role": "system",
                "content": (
                    "You read degraded Hebrew architectural blueprint legends and schedules. "
                    "Extract the total building area in square meters, and, when the sheet "
                    "carries a per-apartment schedule, one row per dwelling unit with its "
                    "number, floor and area. If only individual unit areas are legible, sum "
                    "them into the total. Report a unit you cannot read as a row with a null "
                    "area rather than omitting it or guessing a value, and return an empty "
                    "list when the sheet has no per-apartment schedule at all. Also extract "
                    "residential_area_sqm when the legend states how much of the building is "
                    "for residential use specifically (e.g. \"שטח למגורים\"), as opposed to the "
                    "total built area alone -- null when the legend does not distinguish "
                    "residential from any other use. Also extract declared_floor_count: the "
                    "building's own stated number of floors (e.g. \"מספר קומות\", \"בניין בן 7 "
                    "קומות\"), not any individual unit's floor -- null when the legend does not "
                    "state one."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the total building area (sqm) from this legend/schedule."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                ],
            },
        ],
    )

    payload = json.loads(response.choices[0].message.content)
    area = payload.get("total_building_area_sqm")
    is_plausible, plausibility_reason = _check_plausibility(area, plot_area_sqm)

    units: list[DwellingUnitReading] = []
    for row in payload.get("units") or []:
        unit_area = row.get("area_sqm")
        unit_plausible, unit_reason = _unit_plausibility(unit_area)
        units.append(
            DwellingUnitReading(
                area_sqm=unit_area,
                unit_label=row.get("unit_label"),
                floor=row.get("floor"),
                raw_text=None,  # the model reads the image, so there is no source line to quote
                is_plausible=unit_plausible,
                plausibility_reason=unit_reason,
            )
        )

    return ExtractionResult(
        total_building_area_sqm=area,
        confidence=payload.get("confidence", 0.0),
        method="openai_gpt4o_mini",
        is_plausible=is_plausible,
        plausibility_reason=plausibility_reason,
        units=units,
        declared_unit_count=payload.get("declared_unit_count"),
        residential_area_sqm=payload.get("residential_area_sqm"),
        declared_floor_count=payload.get("declared_floor_count"),
        # Always True: an AI-read figure is never auto-trusted as verified
        # fact, even when it clears the bounds check -- the live test showed
        # gpt-4o-mini confidently misread a plot number as a building area,
        # a plausible-looking number this check can't catch.
        requires_human_review=True,
        notes=payload.get("notes"),
    )


async def extract_total_building_area(
    legend_crop: np.ndarray, original_image_bytes: bytes, plot_area_sqm: float | None = None
) -> ExtractionResult:
    """Read a sheet, preferring local OCR and escalating to the model only when
    the local read is unusable.

    **The escalation gate deliberately ignores `units`.** A confident local
    total with no unit schedule does not trigger the AI path, because most
    sheets in a permit file carry no per-apartment schedule at all: escalating
    on their absence would send nearly every page to the paid model to
    discover there was nothing to find. Per-apartment detail is therefore
    opportunistic -- taken when a schedule is present and legible, and left to
    the footprint-average fallback otherwise.
    """
    local_result = _extract_via_tesseract(legend_crop, plot_area_sqm)
    if (
        local_result.total_building_area_sqm is not None
        and local_result.confidence >= MIN_OCR_CONFIDENCE
        and local_result.is_plausible
    ):
        return local_result

    return await _extract_via_openai(original_image_bytes, plot_area_sqm)
