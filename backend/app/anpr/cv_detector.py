from __future__ import annotations

import cv2
import numpy as np


class TextBandPlateDetector:
    """Locates the plate's text line using a horizontal projection profile
    instead of contour-polygon matching.

    Classical contour matching (find a closed 4-corner rectangle) only
    works when the plate's border is a clean, unbroken edge in the Canny
    map. At low resolution or with a decorative plate frame, the border
    breaks up and no 4-point contour survives. Text, however, has a
    distinctive signature regardless of resolution: a horizontal band
    where edge density is high, made up of several separate character
    blobs spread across most of the image width. This detector finds
    that band directly instead of trying to find a rectangle.
    """

    def __init__(
        self,
        min_band_height_frac: float = 0.08,
        max_band_height_frac: float = 0.45,
        density_threshold_frac: float = 0.35,
        min_segments: int = 3,
        min_width_coverage: float = 0.4,
        margin_px: int = 2,
    ):
        self.min_band_height_frac = min_band_height_frac
        self.max_band_height_frac = max_band_height_frac
        self.density_threshold_frac = density_threshold_frac
        self.min_segments = min_segments
        self.min_width_coverage = min_width_coverage
        self.margin_px = margin_px

    def _find_dense_bands(self, edged: np.ndarray) -> list[tuple[int, int]]:
        h, _ = edged.shape
        row_density = edged.sum(axis=1) / 255.0

        kernel_size = max(3, h // 20)
        kernel = np.ones(kernel_size) / kernel_size
        smoothed = np.convolve(row_density, kernel, mode="same")

        threshold = smoothed.max() * self.density_threshold_frac
        is_dense = smoothed > threshold

        bands: list[tuple[int, int]] = []
        start = None
        for y in range(h):
            if is_dense[y] and start is None:
                start = y
            elif not is_dense[y] and start is not None:
                bands.append((start, y))
                start = None
        if start is not None:
            bands.append((start, h))

        return bands

    def _char_segments(self, edged: np.ndarray, y0: int, y1: int) -> tuple[int, float]:
        _, w = edged.shape
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
        return segments, coverage

    def detect(self, pre: dict):
        original = pre["original"]
        edged = pre["edged"]
        h, w = edged.shape

        bands = self._find_dense_bands(edged)

        min_h = max(8, int(h * self.min_band_height_frac))
        max_h = int(h * self.max_band_height_frac)
        candidates = [(y0, y1) for (y0, y1) in bands if min_h <= (y1 - y0) <= max_h]

        if not candidates:
            return None

        scored = []
        for (y0, y1) in candidates:
            segments, coverage = self._char_segments(edged, y0, y1)
            if segments >= self.min_segments and coverage >= self.min_width_coverage:
                scored.append(((y0, y1), segments * coverage))

        if not scored:
            return None

        (best_y0, best_y1), _ = max(scored, key=lambda item: item[1])

        y0 = max(0, best_y0 - self.margin_px)
        y1 = min(h, best_y1 + self.margin_px)
        return original[y0:y1, 0:w]