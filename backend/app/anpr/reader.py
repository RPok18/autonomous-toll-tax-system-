from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ANPRSignal:
    """One plate-read outcome for a single lane pass."""

    plate_number: str | None
    confidence: float  # 0.0-1.0


class BaseANPRReader:
    """Interface both the real pipeline and the simulator implement, so
    fusion and the API layer never need to know which one is behind it."""

    def read(self, frame) -> ANPRSignal:
        raise NotImplementedError

    def health_check(self) -> dict:
        raise NotImplementedError