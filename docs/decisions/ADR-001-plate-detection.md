# ADR-001: Plate detection strategy

- Status: Accepted for the current implementation; production validation pending
- Date: 2026-10-23

## Context

The ANPR pipeline needs to locate a plate crop before OCR. The current
`ANPRPipeline` defaults to `TextBandPlateDetector`, which applies grayscale
conversion, bilateral denoising, Canny edge detection, and horizontal text-band
grouping. `YoloPlateDetector` is also available behind the same detector
interface and can be injected into the pipeline.

The YOLOv8n model was fine-tuned on the project's labelled plate images for
80 epochs at 640-pixel image size. In the `plate_detector-2` run, epoch 80
reported precision 0.875, recall 0.806, mAP@0.5 0.794, and mAP@0.5:0.95
0.444. The highest mAP@0.5:0.95 in the run was 0.478 at epoch 50. These
detector metrics are from a small validation split and are not end-to-end
plate-reading or tolling accuracy measurements.

## Decision

Keep plate localization replaceable through the detector interface. Retain the
text-band detector as the pipeline default for now; use the YOLO detector as an
optional, experimentally evaluated implementation rather than silently
switching the default.

Before making YOLO the live default, evaluate it on a representative,
independently labelled set of lane-camera images and measure full-pipeline
plate-read accuracy, latency, and failure cases. Include challenging lighting,
view angles, occlusion, and plate layouts.

## Consequences

- Existing callers continue to use the same `ANPRPipeline` interface when the
  detector changes.
- The current default does not require YOLO weights to be configured.
- YOLO offers a learned localization alternative, but its current validation
  result is too limited to establish production readiness.
- Detection recall alone does not measure OCR correctness, correct vehicle
  association, or toll-charging correctness.

## Evidence and implementation

- `backend/app/anpr/pipeline.py` selects `TextBandPlateDetector` by default and
  accepts an injected detector.
- `backend/app/anpr/cv_detector.py` implements the text-band localization
  baseline.
- `backend/app/anpr/yolo_detector.py` implements the optional YOLOv8 detector.
- `backend/scripts/train_yolo.py` trains from the project's YOLO dataset.
- `backend/app/simulation/scenarios.py` defines S4's 0.81 detection-rate proxy.
- `plates/yolo_runs/plate_detector-2/args.yaml` records the 80-epoch,
  640-pixel YOLOv8n training configuration.
- `plates/yolo_runs/plate_detector-2/results.csv` records the epoch-80
  precision, recall, and mAP values above; its best mAP@0.5:0.95 is at epoch
  50. The validation split contains 18 labelled images.

## Revisit when

A larger, representative validation set and an end-to-end comparison are
available. Reconsider the default based on measured accuracy, latency,
operational dependencies, and the cost of false or missed reads.
