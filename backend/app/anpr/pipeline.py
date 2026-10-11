from __future__ import annotations

import cv2

from app.anpr.cv_detector import TextBandPlateDetector
from app.anpr.ocr_engine import TesseractOCREngine
from app.anpr.reader import ANPRSignal, BaseANPRReader


class ANPRPipeline(BaseANPRReader):
    """Real detection+OCR pipeline. Each stage is a seam: swap in an actual
    model (e.g. a YOLO-based plate detector + a trained OCR model for
    Indian plate fonts) without touching callers, which only ever see
    ANPRSignal via read(). Defaults to a horizontal-projection text-band
    detector and Tesseract OCR, which is adequate for a controlled toll
    plaza camera feed but not a research-grade detector.
    """

    def __init__(self, detector=None, ocr_engine=None):
        self.detector = detector or TextBandPlateDetector()
        self.ocr_engine = ocr_engine or TesseractOCREngine()

    def preprocess(self, frame):
        """Grayscale, denoise, edge-detect. Returns both the original
        frame (needed later for cropping/OCR) and the edge map (needed
        for the text-band detector)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        edged = cv2.Canny(gray, 30, 200)
        return {"original": frame, "edged": edged}

    def detect_plate_region(self, frame):
        """frame here is the dict returned by preprocess(). Returns the
        cropped plate region from the original frame, or None if no
        text-like band was found."""
        return self.detector.detect(frame)

    def run_ocr(self, plate_crop) -> ANPRSignal:
        """Run OCR on the cropped plate and return a confidence score."""
        text, confidence = self.ocr_engine.recognize(plate_crop)
        return ANPRSignal(plate_number=text, confidence=confidence)

    def read(self, frame) -> ANPRSignal:
        pre = self.preprocess(frame)
        crop = self.detect_plate_region(pre)
        return self.run_ocr(crop)

    def health_check(self) -> dict:
        ocr_ok = self.ocr_engine.health_check()
        return {
            "status": "online" if ocr_ok else "degraded",
            "mode": "live",
        }