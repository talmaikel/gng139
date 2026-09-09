"""Render every page in the downloaded Hashoshanim 4 evidence PDFs for review."""
from pathlib import Path

import fitz
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "verification" / "hashoshanim-4"
OUTPUT = SOURCE / "rendered"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ("1970-permit.pdf", "2013-plan.pdf", "2013-permit.pdf"):
        document = fitz.open(SOURCE / name)
        stem = Path(name).stem
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            pixmap.save(OUTPUT / f"{stem}-page-{index + 1}.jpg", jpg_quality=88)
    strategic = fitz.open(SOURCE / "strategic-renewal-2023.pdf")
    for page_number in (7, 8):
        pixmap = strategic[page_number - 1].get_pixmap(
            matrix=fitz.Matrix(2.5, 2.5), alpha=False
        )
        pixmap.save(OUTPUT / f"strategic-page-{page_number}.jpg", jpg_quality=92)
    export_path = ROOT / "test-output" / "hashoshanim-4-dossier.pdf"
    if export_path.exists():
        export = fitz.open(export_path)
        for index, page in enumerate(export):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            pixmap.save(OUTPUT / f"dossier-export-page-{index + 1}.jpg", jpg_quality=90)
    plan = Image.open(OUTPUT / "2013-plan-page-1.png").rotate(90, expand=True)
    plan.save(OUTPUT / "2013-plan-rotated.jpg", quality=90)
    width, height = plan.size
    for index in range(4):
        left = index * width // 4
        right = (index + 1) * width // 4
        plan.crop((left, 0, right, height)).save(
            OUTPUT / f"2013-plan-quarter-{index + 1}.jpg", quality=92
        )


if __name__ == "__main__":
    main()
