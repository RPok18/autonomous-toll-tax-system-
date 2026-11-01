from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from app.anpr.ocr_engine import TesseractOCREngine
from app.anpr.pipeline import ANPRPipeline
from app.anpr.yolo_detector import YoloPlateDetector

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
YOLO_WEIGHTS = r"E:\plates\yolo_runs\plate_detector\weights\best.pt"


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/test_anpr_yolo.py <path_to_vehicle_photo>")
        sys.exit(1)

    image_path = sys.argv[1]
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"Could not read image at: {image_path}")
        sys.exit(1)

    pipeline = ANPRPipeline(
        detector=YoloPlateDetector(YOLO_WEIGHTS),
        ocr_engine=TesseractOCREngine(tesseract_cmd=TESSERACT_CMD),
    )

    print("Health check:", pipeline.health_check())

    pre = pipeline.preprocess(frame)
    crop = pipeline.detect_plate_region(pre)
    if crop is None:
        print("YOLO detector found NO plate region.")
        return

    cv2.imwrite("test_images/_yolo_crop.jpg", crop)
    print(f"YOLO found a region, shape={crop.shape}. Saved to test_images/_yolo_crop.jpg")

    signal = pipeline.run_ocr(crop)
    print("Plate number:", signal.plate_number)
    print("Confidence:  ", signal.confidence)


if __name__ == "__main__":
    main()