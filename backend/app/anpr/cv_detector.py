from __future__ import annotations

from app.anpr.text_bands import find_text_bands


class TextBandPlateDetector:
    """Locates a plate's text region(s) using a horizontal projection
    profile instead of contour-polygon matching (see find_text_bands
    for why). Returns the union of every qualifying text band found, so
    a multi-line plate's full extent is captured in a single crop —
    the OCR engine is then responsible for splitting that crop back
    into separate lines if more than one is present.
    """

    def __init__(self, margin_px: int = 2, **band_kwargs):
        self.margin_px = margin_px
        self.band_kwargs = band_kwargs

    def detect(self, pre: dict):
        original = pre["original"]
        edged = pre["edged"]
        h, w = edged.shape

        bands = find_text_bands(edged, **self.band_kwargs)
        if not bands:
            return None
        y0 = max(0, min(b[0] for b in bands) - self.margin_px)
        y1 = min(h, max(b[1] for b in bands) + self.margin_px)
        y1 = min(h, max(b[1] for b in bands) + self.margin_px)
        return original[y0:y1, 0:w]