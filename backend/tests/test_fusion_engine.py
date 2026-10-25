from app.anpr.reader import ANPRSignal
from app.config import get_settings
from app.fusion.fusion_engine import FusionEngine
from app.models.enums import IdentificationMethod
from app.rfid.simulator import RFIDReadResult


def test_fusion_resolves_agreeing_anpr_and_rfid():
    result = FusionEngine().resolve(
        ANPRSignal("MH12AB1234", 0.9),
        RFIDReadResult("TAG-1", 0.9, 20, True),
        "mh12 ab1234",
    )

    assert result.identification_method is IdentificationMethod.HYBRID_AGREED
    assert result.is_exception is False


def test_fusion_uses_configured_primary_signal_on_conflict(monkeypatch):
    monkeypatch.setattr(get_settings(), "fusion_primary_signal", "rfid")

    result = FusionEngine().resolve(
        ANPRSignal("MH12AB1234", 0.9),
        RFIDReadResult("TAG-1", 0.9, 20, True),
        "DL8CAB1234",
    )

    assert result.identification_method is IdentificationMethod.HYBRID_RFID_PRIMARY
    assert result.plate_number == "DL8CAB1234"
    assert result.is_exception is True
