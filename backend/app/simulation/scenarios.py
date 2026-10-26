"""Named simulation scenarios (S0 to S9).

Every scenario changes only the settings it lists and keeps everything else
at the baseline S0. ANPR and RFID overrides are keyword arguments of
ANPRSimulator and RFIDSimulator; anything not listed keeps the simulator's
own default (detect_rate 0.96, misread_rate 0.05, read_success_rate 0.92 ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    name: str
    description: str
    anpr: dict = field(default_factory=dict)
    rfid: dict = field(default_factory=dict)
    tag_share: float = 0.85          # share of vehicles that carry a tag
    clone_share: float = 0.0         # share of tagged vehicles carrying another plate's tag
    low_balance_share: float = 0.0   # share of vehicles registered with a zero balance
    anpr_min_confidence: float = 0.55
    rfid_min_confidence: float = 0.5
    primary_signal: str = "rfid"     # "rfid" | "anpr", used when plate and tag disagree
    fusion_mode: str = "hybrid"      # "hybrid" | "anpr_only" | "rfid_only"


_NIGHT_RAIN = {"detect_rate": 0.85, "misread_rate": 0.15, "mean_confidence_good": 0.85}
_RFID_WORN = {"read_success_rate": 0.70, "garbled_rate": 0.10}

_BASE = [
    Scenario("S0", "Baseline", "Defaults, 85 percent of vehicles tagged"),
    Scenario("S1", "RFID outage", "RFID never reads; what ANPR achieves alone",
             rfid={"read_success_rate": 0.0}),
    Scenario("S2", "ANPR outage", "ANPR never detects; what RFID achieves alone",
             anpr={"detect_rate": 0.0}),
    Scenario("S3", "Night or rain", "Poor visibility at the camera", anpr=_NIGHT_RAIN),
    Scenario("S4", "Weak real ANPR",
             "Detect rate equal to the YOLO detector recall (0.806) on 97 labelled images",
             anpr={"detect_rate": 0.81}),
    Scenario("S5", "RFID degraded", "Worn tags or a poor antenna", rfid=_RFID_WORN),
    Scenario("S6", "Both degraded", "S3 and S5 together", anpr=_NIGHT_RAIN, rfid=_RFID_WORN),
    Scenario("S7", "Many untagged", "Only 40 percent of vehicles carry a tag", tag_share=0.40),
    Scenario("S8", "Cloned tags, RFID primary",
             "5 percent of tagged vehicles carry a tag registered to another plate",
             clone_share=0.05, primary_signal="rfid"),
    Scenario("S8b", "Cloned tags, ANPR primary", "Same as S8, ANPR wins a conflict",
             clone_share=0.05, primary_signal="anpr"),
    Scenario("S10", "Unreadable plates",
             "ANPR cannot read plates and vehicles have no RFID tags",
             anpr={"detect_rate": 0.0}, tag_share=0.0),
]

SCENARIOS: dict[str, Scenario] = {s.scenario_id: s for s in _BASE}

SWEEP_THRESHOLDS = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85)
SWEEP_BASES = ("S0", "S3")


def threshold_sweep() -> list[Scenario]:
    """S9: S0 and S3 with anpr_min_confidence from 0.55 to 0.85 in steps of 0.05."""
    out = []
    for base_id in SWEEP_BASES:
        base = SCENARIOS[base_id]
        for t in SWEEP_THRESHOLDS:
            out.append(replace(
                base,
                scenario_id=f"S9-{base_id}-t{t:.2f}",
                name=f"Threshold sweep on {base_id}",
                description=f"{base.name} with anpr_min_confidence {t:.2f}",
                anpr_min_confidence=t,
            ))
    return out


def get_scenarios(selector: str) -> list[Scenario]:
    """Resolve a selector: "all", "S9", or a comma-separated list of ids."""
    selector = selector.strip()
    if selector.lower() == "all":
        return list(SCENARIOS.values()) + threshold_sweep()
    chosen: list[Scenario] = []
    for part in (p.strip() for p in selector.split(",") if p.strip()):
        if part.upper() == "S9":
            chosen.extend(threshold_sweep())
        elif part in SCENARIOS:
            chosen.append(SCENARIOS[part])
        else:
            known = ", ".join(list(SCENARIOS) + ["S9"])
            raise ValueError(f"Unknown scenario '{part}'. Known scenarios: {known}")
    if not chosen:
        raise ValueError("No scenario selected")
    return chosen
