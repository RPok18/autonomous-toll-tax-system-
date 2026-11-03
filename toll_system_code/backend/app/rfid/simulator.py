"""FASTag-like RFID simulator (P2).

Emulates the behavior a real UHF RFID reader would exhibit at a toll lane:
most vehicles with a valid tag read successfully and quickly; a smaller
fraction miss the read (tag misalignment, low battery, no tag), and a
smaller fraction still produce a garbled/low-confidence read. Parameters
are tunable so the P5 experiments can sweep "RFID quality" as an
independent variable alongside ANPR frame quality.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from app.rfid.reader import BaseRFIDReader, TagRead


@dataclass
class RFIDReadResult:
    tag_id: str | None
    confidence: float
    read_latency_ms: float
    tag_registered: bool  # whether the tag_id exists in our vehicle DB


class RFIDSimulator(BaseRFIDReader):
    def __init__(
        self,
        read_success_rate: float = 0.92,
        garbled_rate: float = 0.03,
        mean_latency_ms: float = 45.0,
        seed: int | None = None,
    ):
        self.read_success_rate = read_success_rate
        self.garbled_rate = garbled_rate
        self.mean_latency_ms = mean_latency_ms
        self._rng = random.Random(seed)

    def simulate_pass(self, true_tag_id: str | None, known_tag_ids: set[str]) -> RFIDReadResult:
        """Simulate one vehicle pass. `true_tag_id` is None if the vehicle
        carries no tag at all (e.g. exempt two-wheeler, out-of-state visitor
        without FASTag)."""
        latency = max(5.0, self._rng.gauss(self.mean_latency_ms, self.mean_latency_ms * 0.2))

        if true_tag_id is None:
            return RFIDReadResult(tag_id=None, confidence=0.0, read_latency_ms=latency, tag_registered=False)

        roll = self._rng.random()
        if roll > self.read_success_rate:
            # missed read entirely (misalignment, dead battery, blocked antenna)
            return RFIDReadResult(tag_id=None, confidence=0.0, read_latency_ms=latency, tag_registered=False)

        if roll > self.read_success_rate - self.garbled_rate:
            # garbled read: corrupt a character to simulate a checksum-marginal read
            garbled = list(true_tag_id)
            idx = self._rng.randrange(len(garbled))
            garbled[idx] = self._rng.choice("0123456789ABCDEF")
            tag = "".join(garbled)
            return RFIDReadResult(
                tag_id=tag, confidence=round(self._rng.uniform(0.3, 0.6), 2),
                read_latency_ms=latency, tag_registered=tag in known_tag_ids,
            )

        return RFIDReadResult(
            tag_id=true_tag_id, confidence=round(self._rng.uniform(0.85, 0.99), 2),
            read_latency_ms=latency, tag_registered=true_tag_id in known_tag_ids,
        )

    # BaseRFIDReader interface (no ground truth available at runtime)
    def read(self) -> TagRead:
        raise NotImplementedError(
            "RFIDSimulator.read() has no ground truth in a live context; "
            "use simulate_pass() from the simulation harness, or swap in a "
            "real BaseRFIDReader implementation for production."
        )

    def health_check(self) -> dict:
        return {"status": "online", "mode": "simulated"}