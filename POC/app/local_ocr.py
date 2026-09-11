"""Local, zero-cost OCR for scanned public building-file documents."""
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .openai_pipeline import PipelineError, render_tiles


def _tesseract_command():
    command = shutil.which("tesseract")
    if command:
        return command
    default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if default.exists():
        return str(default)
    raise PipelineError(
        "Tesseract was not found. Install it, or add C:\\Program Files\\Tesseract-OCR to PATH."
    )


def _languages(command: str):
    completed = subprocess.run(
        [command, "--list-langs"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if completed.returncode:
        raise PipelineError(f"Tesseract language check failed: {completed.stderr.strip()}")
    return {line.strip() for line in completed.stdout.splitlines() if line.strip() and not line.startswith("List of")}


def prepare_tesseract(language: str = "heb+eng"):
    """Return a validated local Tesseract command for the requested languages."""
    command = _tesseract_command()
    available = _languages(command)
    missing = set(language.split("+")) - available
    if missing:
        raise PipelineError(f"Tesseract is installed but missing language data: {', '.join(sorted(missing))}")
    return command


def ocr_rendered_tiles(tiles, output_dir: Path, *, language: str = "heb+eng", psm: int = 11):
    """OCR already-rendered tiles so render and OCR time can be measured separately."""
    command = prepare_tesseract(language)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for tile in tiles:
        text_path = output_dir / f"{tile['id']}.txt"
        if not text_path.exists():
            completed = subprocess.run(
                [command, str(tile["path"]), "stdout", "-l", language, "--psm", str(psm)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
            )
            if completed.returncode:
                raise PipelineError(f"OCR failed for {tile['id']}: {completed.stderr.strip()}")
            text_path.write_text(completed.stdout, encoding="utf-8")
        text = text_path.read_text(encoding="utf-8")
        records.append({
            "id": tile["id"], "page": tile["page"], "image": str(tile["path"]),
            "text": str(text_path), "characters": len(text),
        })
    return records


def extract_local(pdf_path: Path, output_dir: Path, *, language: str = "heb+eng", psm: int = 11,
                  max_tiles: int = 24):
    """Render a permit to tiles and retain every raw OCR output as evidence."""
    tiles = render_tiles(pdf_path, output_dir / "tiles", max_tiles=max_tiles)
    text_dir = output_dir / "ocr"
    records = ocr_rendered_tiles(tiles, text_dir, language=language, psm=psm)

    result = {
        "provider": "tesseract",
        "cost_usd": 0,
        "document": str(pdf_path),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "language": language,
        "page_segmentation_mode": psm,
        "tile_limit": max_tiles,
        "tiles": records,
        "combined_text": str(output_dir / "ocr.txt"),
        "notes": "Raw OCR only. Values must be verified against the cited tile before entering a dossier.",
    }
    (output_dir / "ocr.txt").write_text(
        "\n\n".join(f"--- {record['id']} ---\n{Path(record['text']).read_text(encoding='utf-8')}" for record in records),
        encoding="utf-8",
    )
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
