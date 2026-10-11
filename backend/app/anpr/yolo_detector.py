from __future__ import annotations

from ultralytics import YOLO


class YoloPlateDetector:
    """Plate-region detector backed by a YOLOv8 model fine-tuned on a
    hand-labeled set of real vehicle photos (see
    scripts/prepare_yolo_dataset.py and scripts/train_yolo.py). Replaces
    the heuristic TextBandPlateDetector when trained weights are
    available; implements the same detect(pre) contract so it drops
    into ANPRPipeline without any other changes.
    """

    def __init__(self, weights_path: str, conf_threshold: float = 0.25):
        self.model = YOLO(weights_path)
        self.conf_threshold = conf_threshold

    def detect(self, pre: dict):
        frame = pre["original"]
        results = self.model.predict(frame, conf=self.conf_threshold, verbose=False)

        if not results or len(results[0].boxes) == 0:
            return None

        boxes = results[0].boxes
        best_idx = int(boxes.conf.argmax())
        x1, y1, x2, y2 = boxes.xyxy[best_idx].tolist()
        x1, y1, x2, y2 = max(0, int(x1)), max(0, int(y1)), int(x2), int(y2)

        return frame[y1:y2, x1:x2]