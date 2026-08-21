from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .faults import Fault, fault_from_config
from .types import SpacecraftState


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    description: str
    initial_state: SpacecraftState
    fault: Fault


def load_scenario(path: str | Path) -> Scenario:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    initial = data.get("initial_state", {})
    state = SpacecraftState(
        step=0,
        range_m=float(initial.get("range_m", 100.0)),
        relative_velocity_mps=float(initial.get("relative_velocity_mps", -0.15)),
        propellant=float(initial.get("propellant", 1.0)),
    )
    return Scenario(
        scenario_id=data["id"],
        description=data.get("description", ""),
        initial_state=state,
        fault=fault_from_config(data.get("fault", {"type": "none"})),
    )
