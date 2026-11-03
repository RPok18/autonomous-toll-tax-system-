"""Simulation harness for the identification and billing path (tasks B2, B3).

Scenarios and metrics are defined in the knowledge-base article
"04 Simulation: scenarios and metrics"; this package implements them.
"""
from app.simulation.scenarios import SCENARIOS, Scenario, get_scenarios  # noqa: F401
from app.simulation.runner import PassRecord, process_pass, run_scenario  # noqa: F401
from app.simulation.metrics import aggregate, fusion_gain, summarise  # noqa: F401
