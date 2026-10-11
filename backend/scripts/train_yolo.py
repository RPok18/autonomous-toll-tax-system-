from __future__ import annotations

from ultralytics import YOLO


def main():
    model = YOLO("yolov8n.pt")  # pretrained COCO weights, fine-tuned from here
    model.train(
        data=r"E:\plates\yolo_dataset\data.yaml",
        epochs=80,
        imgsz=640,
        batch=8,
        project=r"E:\plates\yolo_runs",
        name="plate_detector",
    )


if __name__ == "__main__":
    main()