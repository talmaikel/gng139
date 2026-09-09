"""Extract and tile one scanned permit sheet for visual inspection and OCR."""
from pathlib import Path

import pymupdf
from PIL import Image


SOURCE = Path(r"C:\Users\talma\Downloads\השושנים 4.pdf")
OUTPUT = Path("data/verification/hashoshanim-4")
TILE_WIDTH = 4200


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(SOURCE)
    image_info = document.extract_image(document[0].get_images(full=True)[0][0])
    sheet_path = OUTPUT / f"permit-sheet.{image_info['ext']}"
    sheet_path.write_bytes(image_info["image"])
    with Image.open(sheet_path) as sheet:
        for index, left in enumerate(range(0, sheet.width, TILE_WIDTH), 1):
            right = min(left + TILE_WIDTH, sheet.width)
            tile = sheet.crop((left, 0, right, sheet.height))
            tile.thumbnail((3200, 2100), Image.Resampling.LANCZOS)
            tile.save(OUTPUT / f"tile-{index:02d}.jpg", quality=82, optimize=True)
        # Evidence crops from the permit title block and quantitative tables.
        crops = {
            "title-block": (26300, 0, 28880, 1350),
            "areas-table": (25200, 500, 28880, 1900),
            "units-and-stamp": (25200, 1250, 28880, 2696),
            "typical-floor": (8700, 200, 13200, 2600),
            "site-plan": (20500, 150, 25200, 2600),
        }
        for name, box in crops.items():
            crop = sheet.crop(box)
            crop.save(OUTPUT / f"crop-{name}.jpg", quality=90, optimize=True)
    print(f"Extracted {sheet.width}x{sheet.height} sheet into {index} tiles at {OUTPUT}")


if __name__ == "__main__":
    main()
