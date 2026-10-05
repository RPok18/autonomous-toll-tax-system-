from __future__ import annotations

import random

from app.anpr.reader import ANPRSignal, BaseANPRReader

# Characters Indian plates actually use, grouped by how OCR tends to
# confuse them — used to make synthetic misreads look realistic rather
# than uniformly random.
_CONFUSABLE = {
    "0": "O", "O": "0", "8": "B", "B": "8", "1": "I", "I": "1",
    "5": "S", "S": "5", "2": "Z", "Z": "2",
}


class ANPRSimulator(BaseANPRReader):
    """Stands in for a real camera+OCR pipeline during simulated highway
    runs. Tunable so P5 can sweep conditions (night, rain, high speed,
    dirty plate) without needing a labeled plate dataset yet.
    """

    def __init__(
        self,
        detect_rate: float = 0.96,
        misread_rate: float = 0.05,
        mean_confidence_good: float = 0.93,
        mean_confidence_misread: float = 0.55,
        seed: int | None = None,
    ):
        self.detect_rate = detect_rate
        self.misread_rate = misread_rate
        self.mean_confidence_good = mean_confidence_good
        self.mean_confidence_misread = mean_confidence_misread
        self._rng = random.Random(seed)

    def simulate_read(self, true_plate: str | None) -> ANPRSignal:
        """Ground-truth-aware entry point for the simulation harness."""
        if true_plate is None:
            return ANPRSignal(plate_number=None, confidence=0.0)

        roll = self._rng.random()

        # Plate not detected at all (bad angle, glare, occlusion, speed)
        if roll > self.detect_rate:
            return ANPRSignal(plate_number=None, confidence=0.0)

        # Detected but OCR garbled one character
        if roll > self.detect_rate - self.misread_rate:
            chars = list(true_plate)
            idx = self._rng.randrange(len(chars))
            chars[idx] = _CONFUSABLE.get(chars[idx], chars[idx])
            garbled = "".join(chars)
            confidence = round(
                max(0.0, min(1.0, self._rng.gauss(self.mean_confidence_misread, 0.08))), 3
            )
            return ANPRSignal(plate_number=garbled, confidence=confidence)

        # Clean read
        confidence = round(
            max(0.0, min(1.0, self._rng.gauss(self.mean_confidence_good, 0.04))), 3
        )
        return ANPRSignal(plate_number=true_plate, confidence=confidence)

    def read(self, frame) -> ANPRSignal:
        raise NotImplementedError(
            "ANPRSimulator.read() has no ground truth in a live context; "
            "use simulate_read() from the simulation harness, or swap in "
            "ANPRPipeline for production."
        )

    def health_check(self) -> dict:
        return {"status": "online", "mode": "simulated"}