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
from dataclasses import dataclass

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

MIN_OCR_CONFIDENCE = 60.0

EXTRACTION_JSON_SCHEMA = {
    "name": "building_area_extraction",
    "schema": {
        "type": "object",
        "properties": {
            "total_building_area_sqm": {"type": ["number", "null"]},
            "unit_areas_sqm": {"type": "array", "items": {"type": "number"}},
            "confidence": {"type": "number"},
            "notes": {"type": ["string", "null"]},
        },
        # OpenAI's strict structured-output mode requires every property to be
        # listed here, even ones that are semantically optional/nullable above.
        "required": ["total_building_area_sqm", "unit_areas_sqm", "confidence", "notes"],
        "additionalProperties": False,
    },
    "strict": True,
}


@dataclass
class ExtractionResult:
    total_building_area_sqm: float | None
    confidence: float
    method: str  # "tesseract_regex" | "openai_gpt4o_mini"
    raw_text: str | None = None
    notes: str | None = None


def _extract_via_tesseract(legend_crop: np.ndarray) -> ExtractionResult:
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

    return ExtractionResult(
        total_building_area_sqm=total_area,
        confidence=mean_confidence,
        method="tesseract_regex",
        raw_text=text,
    )


async def _extract_via_openai(image_bytes: bytes) -> ExtractionResult:
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
                    "Extract the total building area in square meters. If only individual unit "
                    "areas are legible, sum them into the total and list them separately."
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
    return ExtractionResult(
        total_building_area_sqm=payload.get("total_building_area_sqm"),
        confidence=payload.get("confidence", 0.0),
        method="openai_gpt4o_mini",
        notes=payload.get("notes"),
    )


async def extract_total_building_area(legend_crop: np.ndarray, original_image_bytes: bytes) -> ExtractionResult:
    local_result = _extract_via_tesseract(legend_crop)
    if local_result.total_building_area_sqm is not None and local_result.confidence >= MIN_OCR_CONFIDENCE:
        return local_result

    return await _extract_via_openai(original_image_bytes)
