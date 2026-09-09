"""Bounded OpenAI vision extraction for public building-file documents.

The model proposes values and their visual evidence. It never decides eligibility
or overwrites verified data; those steps remain deterministic and auditable.
"""
import base64
import json
import math
import os
from pathlib import Path

import httpx
import pymupdf


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_INPUT_TOKENS_URL = "https://api.openai.com/v1/responses/input_tokens"
MODEL_RATES = {
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20},
    "gpt-5.6-terra": {"input": 2.00, "output": 12.00},
}


class PipelineError(RuntimeError):
    """A bounded, user-safe error from the extraction pipeline."""


FIELD_NAMES = [
    "permit_number",
    "permit_date",
    "units",
    "residential_floors",
    "pilotis_floors",
    "main_residential_area_m2",
    "stair_area_m2",
    "pilotis_area_m2",
    "shelter_area_m2",
    "original_total_area_m2",
]


def _field_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "value": {"type": ["string", "null"]},
            "page": {"type": ["integer", "null"]},
            "tile": {"type": ["string", "null"]},
            "quote": {"type": ["string", "null"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["value", "page", "tile", "quote", "confidence"],
    }


PERMIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fields": {
            "type": "object",
            "additionalProperties": False,
            "properties": {name: _field_schema() for name in FIELD_NAMES},
            "required": FIELD_NAMES,
        },
        "notes": {"type": "string"},
    },
    "required": ["fields", "notes"],
}

INSTRUCTIONS = """You extract evidence from a public Israeli building-permit document.
Read Hebrew accurately, including right-to-left tables. Return only facts visible in the
provided images. If a value is absent or unreadable, return null and confidence 0.
Do not infer development rights, eligibility, dates, apartment counts, or areas.
For every non-null value, quote the visible Hebrew text or formula and identify its page
and tile exactly as labeled in the images."""


def render_tiles(pdf_path: Path, output_dir: Path, *, dpi: int = 144,
                 max_side_px: int = 2048, overlap: float = 0.08,
                 max_tiles: int = 16):
    """Render bounded, overlapping JPEG tiles without loading a giant sheet at once."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scale = dpi / 72
    tiles = []
    with pymupdf.open(pdf_path) as document:
        for page_index, page in enumerate(document, 1):
            rect = page.rect
            cols = max(1, math.ceil(rect.width * scale / max_side_px))
            rows = max(1, math.ceil(rect.height * scale / max_side_px))
            for row in range(rows):
                for column in range(cols):
                    if len(tiles) >= max_tiles:
                        raise PipelineError(f"Document exceeds the {max_tiles}-tile pilot limit")
                    unit_w, unit_h = rect.width / cols, rect.height / rows
                    extra_w, extra_h = unit_w * overlap, unit_h * overlap
                    clip = pymupdf.Rect(
                        max(rect.x0, rect.x0 + column * unit_w - extra_w),
                        max(rect.y0, rect.y0 + row * unit_h - extra_h),
                        min(rect.x1, rect.x0 + (column + 1) * unit_w + extra_w),
                        min(rect.y1, rect.y0 + (row + 1) * unit_h + extra_h),
                    )
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
                    tile_id = f"p{page_index}-r{row + 1}-c{column + 1}"
                    path = output_dir / f"{tile_id}.jpg"
                    path.write_bytes(pix.tobytes("jpeg", jpg_quality=85))
                    tiles.append({"id": tile_id, "page": page_index, "path": path})
    return tiles


def request_payload(tiles, model: str):
    content = [{"type": "input_text", "text": "Extract the requested permit fields from these labeled image tiles."}]
    for tile in tiles:
        encoded = base64.b64encode(tile["path"].read_bytes()).decode("ascii")
        content.append({"type": "input_text", "text": f"Tile label: {tile['id']} (page {tile['page']})."})
        content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}", "detail": "high"})
    return {
        "model": model,
        "store": False,
        "reasoning": {"effort": "none"},
        "instructions": INSTRUCTIONS,
        "input": [{"role": "user", "content": content}],
        "max_output_tokens": 1800,
        "text": {"format": {"type": "json_schema", "name": "permit_extraction", "strict": True, "schema": PERMIT_SCHEMA}},
    }


def _headers(api_key: str):
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _text_from_response(response: dict):
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content["text"]
    raise PipelineError("OpenAI response did not contain structured output text")


def _cost(model: str, usage: dict):
    rates = MODEL_RATES.get(model)
    if not rates:
        return None
    return round((usage.get("input_tokens", 0) * rates["input"] + usage.get("output_tokens", 0) * rates["output"]) / 1_000_000, 8)


def extract(pdf_path: Path, output_dir: Path, *, model: str = "gpt-5.6-luna",
            max_usd: float = 1.0, transport=None):
    """Render, preflight cost, then extract one document through the Responses API."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise PipelineError("OPENAI_API_KEY is not set in this PowerShell session")
    if model not in MODEL_RATES:
        raise PipelineError(f"Unsupported pilot model: {model}")
    tiles = render_tiles(pdf_path, output_dir / "tiles")
    payload = request_payload(tiles, model)
    with httpx.Client(timeout=120, transport=transport) as client:
        preflight = client.post(OPENAI_INPUT_TOKENS_URL, headers=_headers(api_key), json={
            "model": model, "instructions": payload["instructions"], "input": payload["input"],
        })
        if preflight.status_code >= 400:
            raise PipelineError(f"OpenAI token preflight failed ({preflight.status_code})")
        input_tokens = preflight.json().get("input_tokens", 0)
        maximum = _cost(model, {"input_tokens": input_tokens, "output_tokens": payload["max_output_tokens"]})
        if maximum is None or maximum > max_usd:
            raise PipelineError(f"Pilot call ceiling ${maximum:.4f} exceeds configured ${max_usd:.2f}")
        response = client.post(OPENAI_RESPONSES_URL, headers=_headers(api_key), json=payload)
        if response.status_code >= 400:
            raise PipelineError(f"OpenAI extraction failed ({response.status_code})")
    raw = response.json()
    try:
        extraction = json.loads(_text_from_response(raw))
    except json.JSONDecodeError as exc:
        raise PipelineError("OpenAI returned invalid structured JSON") from exc
    result = {
        "provider": "openai",
        "model": model,
        "document": str(pdf_path),
        "tiles": [{"id": tile["id"], "page": tile["page"], "path": str(tile["path"])} for tile in tiles],
        "input_tokens_preflight": input_tokens,
        "usage": raw.get("usage", {}),
        "estimated_cost_usd": _cost(model, raw.get("usage", {})),
        "extraction": extraction,
        "response_id": raw.get("id"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    return result


def extract_images(images, output_dir: Path, *, document_label: str, model: str = "gpt-5.6-luna",
                   max_usd: float = 0.25, transport=None):
    """Run the same evidence-only schema on a small, preselected set of image crops."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise PipelineError("OPENAI_API_KEY is not set in this PowerShell session")
    if model not in MODEL_RATES or not images:
        raise PipelineError("A supported pilot model and at least one image are required")
    tiles = [{"id": item["id"], "page": item.get("page", 1), "path": Path(item["path"])} for item in images]
    if any(not item["path"].exists() for item in tiles):
        raise PipelineError("A selected evidence image is missing")
    payload = request_payload(tiles, model)
    with httpx.Client(timeout=120, transport=transport) as client:
        preflight = client.post(OPENAI_INPUT_TOKENS_URL, headers=_headers(api_key), json={"model": model, "instructions": payload["instructions"], "input": payload["input"]})
        if preflight.status_code >= 400:
            raise PipelineError(f"OpenAI token preflight failed ({preflight.status_code})")
        input_tokens = preflight.json().get("input_tokens", 0)
        maximum = _cost(model, {"input_tokens": input_tokens, "output_tokens": payload["max_output_tokens"]})
        if maximum is None or maximum > max_usd:
            raise PipelineError(f"Pilot call ceiling ${maximum:.4f} exceeds configured ${max_usd:.2f}")
        response = client.post(OPENAI_RESPONSES_URL, headers=_headers(api_key), json=payload)
        if response.status_code >= 400:
            raise PipelineError(f"OpenAI extraction failed ({response.status_code})")
    raw = response.json()
    try:
        extraction = json.loads(_text_from_response(raw))
    except json.JSONDecodeError as exc:
        raise PipelineError("OpenAI returned invalid structured JSON") from exc
    result = {"provider": "openai", "model": model, "document": document_label, "tiles": [{"id": tile["id"], "page": tile["page"], "path": str(tile["path"])} for tile in tiles], "input_tokens_preflight": input_tokens, "usage": raw.get("usage", {}), "estimated_cost_usd": _cost(model, raw.get("usage", {})), "extraction": extraction, "response_id": raw.get("id")}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    return result
