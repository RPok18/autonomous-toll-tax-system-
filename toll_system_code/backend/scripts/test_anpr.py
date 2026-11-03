from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from app.anpr.ocr_engine import TesseractOCREngine
from app.anpr.pipeline import ANPRPipeline

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe\tesseract.exe"


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/test_anpr.py <path_to_plate_image>")
        sys.exit(1)

    image_path = sys.argv[1]
    frame = cv2.imread(image_path)

    if frame is None:
        print(f"Could not read image at: {image_path}")
        sys.exit(1)

    pipeline = ANPRPipeline(ocr_engine=TesseractOCREngine(tesseract_cmd=TESSERACT_CMD))

    print("Health check:", pipeline.health_check())

    pre = pipeline.preprocess(frame)
    cv2.imwrite("test_images/_debug_edged.jpg", pre["edged"])

    crop = pipeline.detect_plate_region(pre)
    if crop is None:
        print("Detector found NO plate-shaped region.")
    else:
        cv2.imwrite("test_images/_debug_crop.jpg", crop)
        print(f"Detector found a region, shape={crop.shape}. Saved to test_images/_debug_crop.jpg")

    signal = pipeline.run_ocr(crop)
    print("Plate number:", signal.plate_number)
    print("Confidence:  ", signal.confidence)


if __name__ == "__main__":
    main()