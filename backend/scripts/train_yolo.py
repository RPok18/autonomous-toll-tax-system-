from __future__ import annotations

from pathlib import Path

from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATES_DIR = REPO_ROOT / "plates"


def main():
    model = YOLO(str(REPO_ROOT / "backend" / "yolov8n.pt"))
    model.train(
        data=str(PLATES_DIR / "yolo_dataset" / "data.yaml"),
        epochs=80,
        imgsz=640,
        batch=8,
        project=str(PLATES_DIR / "yolo_runs"),
        name="plate_detector",
    )


if __name__ == "__main__":
    main()