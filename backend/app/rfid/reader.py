"""Hardware-facing RFID reader interface.

A real FASTag-compatible reader (UHF RFID per IS 15883 / NHAI FASTag spec)
would implement this against its serial/TCP/HTTP SDK. The simulator in
``simulator.py`` implements the same interface so the rest of the system
(fusion, policy, dashboard) is agnostic to whether reads are real or
simulated.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TagRead:
    tag_id: str | None
    confidence: float           # signal-quality-derived confidence, 0-1
    read_latency_ms: float


class BaseRFIDReader:
    def read(self) -> TagRead:
        raise NotImplementedError

    def health_check(self) -> dict:
        raise NotImplementedError