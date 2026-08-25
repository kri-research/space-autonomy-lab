from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from .scenario import load_scenario
from .simulation import run_episode


def run_benchmark(
    scenario_paths: Iterable[str | Path],
    controllers: tuple[str, ...] = ("deterministic", "learned", "protected"),
) -> dict:
    rows: list[dict] = []
    for scenario_path in scenario_paths:
        for controller in controllers:
            scenario = load_scenario(scenario_path)
            rows.append(run_episode(scenario, controller).to_dict())

    summary: dict[str, dict] = defaultdict(
        lambda: {
            "episodes": 0,
            "successes": 0,
            "collisions": 0,
            "interventions": 0,
            "unsafe_state_steps": 0,
        }
    )
    for row in rows:
        bucket = summary[row["controller"]]
        bucket["episodes"] += 1
        bucket["successes"] += int(row["success"])
        bucket["collisions"] += int(row["collision"])
        bucket["interventions"] += row["interventions"]
        bucket["unsafe_state_steps"] += row["unsafe_state_steps"]

    for bucket in summary.values():
        episodes = bucket["episodes"]
        bucket["success_rate"] = bucket["successes"] / episodes if episodes else 0.0
        bucket["collision_rate"] = bucket["collisions"] / episodes if episodes else 0.0

    return {"episodes": rows, "summary": dict(summary)}
