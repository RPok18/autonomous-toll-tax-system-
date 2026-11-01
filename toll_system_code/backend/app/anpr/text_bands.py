from __future__ import annotations

import cv2
import numpy as np


def find_text_bands(
    edged: np.ndarray,
    min_height_frac: float = 0.08,
    max_height_frac: float = 0.45,
    density_threshold_frac: float = 0.35,
    min_segments: int = 3,
    min_width_coverage: float = 0.4,
) -> list[tuple[int, int]]:
    """Find all horizontal bands within an edge map that look like a
    line of text: a contiguous region of above-threshold edge density,
    made up of several distinct character-shaped segments spread across
    most of the width. Returns a list of (y0, y1) bands, top to bottom.

    Used both to locate a plate's text within a larger scene
    (TextBandPlateDetector) and to split a plate crop into separate
    lines for multi-line plates (TesseractOCREngine).
    """
    h, w = edged.shape
    row_density = edged.sum(axis=1) / 255.0

    kernel_size = max(3, h // 20)
    kernel = np.ones(kernel_size) / kernel_size
    smoothed = np.convolve(row_density, kernel, mode="same")

    threshold = smoothed.max() * density_threshold_frac
    is_dense = smoothed > threshold

    raw_bands: list[tuple[int, int]] = []
    start = None
    for y in range(h):
        if is_dense[y] and start is None:
            start = y
        elif not is_dense[y] and start is not None:
            raw_bands.append((start, y))
            start = None
    if start is not None:
        raw_bands.append((start, h))

    min_h = max(8, int(h * min_height_frac))
    max_h = int(h * max_height_frac)

    text_bands = []
    for (y0, y1) in raw_bands:
        if not (min_h <= (y1 - y0) <= max_h):
            continue
        band = edged[y0:y1, :]
        col_has_edge = band.sum(axis=0) > 0
        segments, in_segment = 0, False
        for v in col_has_edge:
            if v and not in_segment:
                segments += 1
                in_segment = True
            elif not v:
                in_segment = False
        coverage = col_has_edge.sum() / w
        if segments >= min_segments and coverage >= min_width_coverage:
            text_bands.append((y0, y1))

    return text_bands