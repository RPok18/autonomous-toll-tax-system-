from __future__ import annotations

from app.anpr.reader import ANPRSignal, BaseANPRReader


class ANPRPipeline(BaseANPRReader):
    """Real detection+OCR pipeline. Each stage is a seam: swap in an actual
    model (e.g. a YOLO-based plate detector + a trained OCR model for
    Indian plate fonts) without touching callers, which only ever see
    ANPRSignal via read().
    """

    def __init__(self, detector=None, ocr_engine=None):
        self.detector = detector
        self.ocr_engine = ocr_engine

    def preprocess(self, frame):
        """Grayscale, denoise, contrast-normalize. Plug in OpenCV here."""
        raise NotImplementedError("preprocess: wire in OpenCV once frames are available")

    def detect_plate_region(self, frame):
        """Return the cropped plate region from a preprocessed frame."""
        if self.detector is None:
            raise NotImplementedError("detect_plate_region: no detector configured")
        return self.detector.detect(frame)

    def run_ocr(self, plate_crop) -> ANPRSignal:
        """Run OCR on the cropped plate and return a confidence score."""
        if self.ocr_engine is None:
            raise NotImplementedError("run_ocr: no OCR engine configured")
        text, confidence = self.ocr_engine.recognize(plate_crop)
        return ANPRSignal(plate_number=text, confidence=confidence)

    def read(self, frame) -> ANPRSignal:
        pre = self.preprocess(frame)
        crop = self.detect_plate_region(pre)
        return self.run_ocr(crop)

    def health_check(self) -> dict:
        return {
            "status": "online" if self.detector and self.ocr_engine else "not_configured",
            "mode": "live",
        }