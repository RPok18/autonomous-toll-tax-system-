from __future__ import annotations

from dataclasses import dataclass, field

from app.config import get_settings
from app.models.enums import IdentificationMethod
from app.rfid.simulator import RFIDReadResult
from app.anpr.reader import ANPRSignal


@dataclass
class FusionResult:
    identification_method: IdentificationMethod
    plate_number: str | None
    tag_id: str | None
    confidence: float
    is_exception: bool
    notes: list[str] = field(default_factory=list)


class FusionEngine:
    """Combines one ANPR read and one RFID read for the same lane pass into
    a single identification decision.

    Resolution order:
      1. Both signals present and agree (RFID's registered plate == ANPR
         plate) -> HYBRID_AGREED, high confidence, no exception.
      2. Only one signal present and usable -> that signal's method alone.
      3. Both present but disagree -> fall back to configured primary
         signal, but flag as an exception so it gets audited.
      4. Neither signal usable -> UNRESOLVED, exception.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    def resolve(
        self,
        anpr: ANPRSignal,
        rfid: RFIDReadResult,
        registered_plate_for_tag: str | None = None,
    ) -> FusionResult:
        notes: list[str] = []

        anpr_ok = (
            anpr.plate_number is not None
            and anpr.confidence >= self.settings.anpr_min_confidence
        )
        rfid_ok = (
            rfid.tag_id is not None
            and rfid.tag_registered
            and rfid.confidence >= self.settings.rfid_min_confidence
        )

        # Case 1: both usable — check agreement
        if anpr_ok and rfid_ok:
            if registered_plate_for_tag and self._plates_match(
                anpr.plate_number, registered_plate_for_tag
            ):
                notes.append("anpr_rfid_agree")
                return FusionResult(
                    identification_method=IdentificationMethod.HYBRID_AGREED,
                    plate_number=anpr.plate_number,
                    tag_id=rfid.tag_id,
                    confidence=round(max(anpr.confidence, rfid.confidence), 3),
                    is_exception=False,
                    notes=notes,
                )

            # Both present but disagree — conflict
            notes.append("anpr_rfid_conflict")
            primary = self.settings.fusion_primary_signal  # "rfid" or "anpr"
            if primary == "rfid":
                notes.append("resolved_by_primary:rfid")
                return FusionResult(
                    identification_method=IdentificationMethod.HYBRID_RFID_PRIMARY,
                    plate_number=registered_plate_for_tag,
                    tag_id=rfid.tag_id,
                    confidence=rfid.confidence,
                    is_exception=True,
                    notes=notes,
                )
            notes.append("resolved_by_primary:anpr")
            return FusionResult(
                identification_method=IdentificationMethod.HYBRID_ANPR_PRIMARY,
                plate_number=anpr.plate_number,
                tag_id=rfid.tag_id,
                confidence=anpr.confidence,
                is_exception=True,
                notes=notes,
            )

        # Case 2: only RFID usable
        if rfid_ok and not anpr_ok:
            notes.append("rfid_only")
            return FusionResult(
                identification_method=IdentificationMethod.RFID_ONLY,
                plate_number=registered_plate_for_tag,
                tag_id=rfid.tag_id,
                confidence=rfid.confidence,
                is_exception=False,
                notes=notes,
            )

        # Case 3: only ANPR usable
        if anpr_ok and not rfid_ok:
            notes.append("anpr_only")
            return FusionResult(
                identification_method=IdentificationMethod.ANPR_ONLY,
                plate_number=anpr.plate_number,
                tag_id=rfid.tag_id,
                confidence=anpr.confidence,
                is_exception=False,
                notes=notes,
            )

        # Case 4: neither usable
        notes.append("no_usable_signal")
        return FusionResult(
            identification_method=IdentificationMethod.UNRESOLVED,
            plate_number=None,
            tag_id=rfid.tag_id,
            confidence=0.0,
            is_exception=True,
            notes=notes,
        )

    @staticmethod
    def _plates_match(a: str | None, b: str | None) -> bool:
        if not a or not b:
            return False
        return a.strip().upper().replace(" ", "") == b.strip().upper().replace(" ", "")