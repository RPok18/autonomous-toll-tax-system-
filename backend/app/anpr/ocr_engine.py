from __future__ import annotations

import re

import cv2
import numpy as np
import pytesseract
from app.anpr.text_bands import find_text_bands

# Indian vehicle registration plate pattern, e.g. MH12AB1234 or DL1LT5678
PLATE_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")


class TesseractOCREngine:
    """Wraps Tesseract. Requires the Tesseract-OCR binary installed
    separately on the machine (not just the pytesseract pip package).

    Tries two strategies and keeps whichever reads better:
      1. OCR directly on the crop as given (works well when the
         detector already handed back a roughly front-on, horizontal
         plate region).
      2. A perspective-corrected version of the crop, built from the
         plate's actual four corners (not just a simple rotation),
         which recovers a clean horizontal plate out of a crop taken
         at a steep camera angle. Several corner orderings/rotations
         are tried since there is no reliable way to know which corner
         is "top-left" from geometry alone.
    """

    def __init__(self, tesseract_cmd: str | None = None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def _ocr_once(self, image) -> str:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        raw_text = pytesseract.image_to_string(
            thresh,
            config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )
        return re.sub(r"[^A-Z0-9]", "", raw_text.upper())

    def _perspective_candidates(self, plate_crop) -> list:
        """Find the plate's bright quadrilateral within the crop and
        return several perspective-corrected, flattened versions of it
        (one per plausible corner ordering). Returns an empty list if
        no clean 4-point shape is found."""
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return []

        largest = max(contours, key=cv2.contourArea)
        crop_area = plate_crop.shape[0] * plate_crop.shape[1]
        if cv2.contourArea(largest) < 0.2 * crop_area:
            return []  # no single dominant bright blob — skip perspective attempt

        perimeter = cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, 0.02 * perimeter, True)
        if len(approx) != 4:
            return []

        points = approx.reshape(-1, 2).astype(np.float32)
        centroid = points.mean(axis=0)
        angles = np.arctan2(points[:, 1] - centroid[1], points[:, 0] - centroid[0])
        points = points[np.argsort(angles)]

        edges = [np.linalg.norm(points[i] - points[(i + 1) % 4]) for i in range(4)]
        target_w = int(max(edges))
        target_h = int(min(edges))
        if target_w < 20 or target_h < 10:
            return []

        candidates = []
        dst = np.array(
            [[0, 0], [target_w, 0], [target_w, target_h], [0, target_h]],
            dtype=np.float32,
        )
        for ordering in (points, points[::-1]):
            for start in range(4):
                src = np.roll(ordering, -start, axis=0).astype(np.float32)
                matrix = cv2.getPerspectiveTransform(src, dst)
                warped = cv2.warpPerspective(plate_crop, matrix, (target_w, target_h))
                candidates.append(warped)

        return candidates

    def _try_multi_line(self, plate_crop) -> tuple[str, float] | None:
        """If the crop contains more than one distinct text band, OCR
        each one separately (top to bottom) and concatenate. Returns
        None if only one band (or none) is found, so the caller falls
        through to the normal single-line path unchanged."""
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        gray_f = cv2.bilateralFilter(gray, 11, 17, 17)
        edged = cv2.Canny(gray_f, 30, 200)

        bands = find_text_bands(edged, min_height_frac=0.1, max_height_frac=0.6, min_segments=2)
        if len(bands) < 2:
            return None

        h, w = plate_crop.shape[:2]
        line_texts = []
        for (y0, y1) in sorted(bands):
            yy0, yy1 = max(0, y0 - 2), min(h, y1 + 2)
            line_texts.append(self._ocr_once(plate_crop[yy0:yy1, 0:w]))

        combined = "".join(line_texts)
        if not combined:
            return None

        confidence = 0.85 if PLATE_PATTERN.match(combined) else 0.35
        return combined, confidence

    def recognize(self, plate_crop) -> tuple[str | None, float]:
        if plate_crop is None:
            return None, 0.0

        multi_line_result = self._try_multi_line(plate_crop)
        if multi_line_result is not None:
            return multi_line_result

        attempts = [self._ocr_once(plate_crop)]
        attempts.extend(self._ocr_once(c) for c in self._perspective_candidates(plate_crop))

        exact_matches = [a for a in attempts if PLATE_PATTERN.match(a)]
        if exact_matches:
            return exact_matches[0], 0.85

        non_empty = [a for a in attempts if a]
        if not non_empty:
            return None, 0.0

        best = max(non_empty, key=len)
        return best, 0.35

    def health_check(self) -> bool:
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False