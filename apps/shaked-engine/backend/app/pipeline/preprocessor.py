"""
Local OpenCV pre-processing for legacy municipal blueprint scans, ahead of OCR.

Crops the scan down to its legend/schedule table (where per-unit areas are
listed) and applies binarization + contrast enhancement to compensate for
faded, decades-old paper archives.
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PreprocessedPage:
    legend_crop: np.ndarray  # binarized crop of the legend/schedule region
    full_page: np.ndarray    # contrast-enhanced full page, for fallback OCR


def _enhance_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _binarize(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _find_legend_crop(gray: np.ndarray) -> np.ndarray:
    """
    Legend/schedule tables are dense grids of thin horizontal/vertical lines.
    Find the largest rectangular region with high line density and crop to it,
    falling back to the full page when no such region is detected.
    """
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=40, maxLineGap=5)
    if lines is None:
        return gray

    # HoughLinesP's output shape varies by OpenCV version (`(N, 1, 4)` vs `(N, 4)`);
    # reshape to a flat `(N, 4)` array of (x1, y1, x2, y2) rows regardless.
    lines = lines.reshape(-1, 4)
    xs = np.concatenate([lines[:, 0], lines[:, 2]])
    ys = np.concatenate([lines[:, 1], lines[:, 3]])
    x0, x1 = int(np.percentile(xs, 2)), int(np.percentile(xs, 98))
    y0, y1 = int(np.percentile(ys, 2)), int(np.percentile(ys, 98))
    if x1 <= x0 or y1 <= y0:
        return gray
    return gray[y0:y1, x0:x1]


def preprocess_blueprint(image_bytes: bytes) -> PreprocessedPage:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enhanced = _enhance_contrast(gray)

    legend_region = _find_legend_crop(enhanced)
    legend_crop = _binarize(legend_region)

    return PreprocessedPage(legend_crop=legend_crop, full_page=enhanced)
