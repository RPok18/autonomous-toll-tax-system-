# ADR-002: OCR engine and plate-read confidence

- Status: Accepted as the current baseline
- Date: 2026-10-23

## Context

The ANPR pipeline needs to recognize characters after plate localization. The
current implementation uses Tesseract through `pytesseract` and applies
OpenCV-based preprocessing, including grayscale conversion, 3x resizing, and
Otsu thresholding. It also tries perspective-corrected crops and separately
reads multiple text lines where detected.

The OCR component is isolated behind an engine interface so another
implementation can be introduced without changing the pipeline callers.

## Decision

Keep Tesseract as the current OCR baseline and preserve the replaceable OCR
engine seam. Continue to use the Indian registration-plate pattern as a
syntactic check for recognized text.

Treat the current confidence values as heuristic scores, not calibrated
probabilities: a pattern-matching read receives 0.85, a non-empty but
non-matching read receives 0.35, and an empty read receives 0.0.

## Consequences

- The baseline is straightforward to run where the separately installed
  Tesseract binary is available.
- Perspective correction and multi-line handling can improve coverage without
  requiring a separately trained OCR model.
- A syntactically valid plate can still be the wrong plate; format validation
  is not proof of identity.
- The fixed confidence scores should not be interpreted as measured
  probabilities or compared across OCR engines without calibration.
- Tesseract's external binary is an operational dependency that must be
  installed and checked in the deployment environment.

## Evidence and implementation

- `backend/app/anpr/ocr_engine.py` implements `TesseractOCREngine`, its
  preprocessing strategies, and the plate-pattern check.
- `backend/app/anpr/pipeline.py` defaults to `TesseractOCREngine` and allows
  an engine to be injected.
- `backend/app/anpr/reader.py` defines the `ANPRSignal` passed from OCR to
  fusion.

## Revisit when

An annotated end-to-end plate-reading dataset is available to compare exact
plate accuracy, false reads, missed reads, confidence calibration, and latency
against alternative OCR engines.
