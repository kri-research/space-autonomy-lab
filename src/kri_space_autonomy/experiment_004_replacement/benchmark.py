from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004_pilot.config import load_pilot_config
from kri_space_autonomy.experiment_004_pilot.runner import _scenario_from_row

from .config import load_confirmatory_config
from .runner import _run_checkpointed_tasks, benchmark_worker_counts
from .seeds import load_confirmatory_cases


def _pilot_tasks(root: Path, count: int) -> list[dict[str, Any]]:
    study = load_confirmatory_config(root / "experiments/004-replacement-confirmatory/config.json")
    pilot = load_pilot_config(root / "experiments/004-pilot/config.json")
    foundation = load_config(root / "experiments/004/config.json")
    cases = {
        case.id: case
        for case in load_confirmatory_cases(
            root / "experiments/004-pilot/case-matrix.json", study=study
        )
    }
    rows = [
        json.loads(line)
        for line in (root / "experiments/004-pilot/seeds/pilot.jsonl").read_text().splitlines()
    ]
    selected = rows[:count]
    tasks: list[dict[str, Any]] = []
    for index, row in enumerate(selected):
        scenario = _scenario_from_row(row)
        tasks.append(
            {
                "task_kind": "pilot",
                "block_index": index,
                "case_id": scenario.case_id,
                "root_seed_id": scenario.root_seed_id,
                "scenario_hash": scenario.scenario_hash,
                "configuration_run_order": scenario.configuration_run_order,
                "pilot": pilot,
                "foundation": foundation,
                "case": cases[scenario.case_id],
                "scenario": scenario,
            }
        )
    return tasks


def run_benchmark(root: Path) -> dict[str, Any]:
    cpu = __import__("os").cpu_count()
    numerical = benchmark_worker_counts((1, 4, 8, 10), task_count=24, iterations=1_500_000)
    tasks = _pilot_tasks(root, 2)
    scientific_measurements = []
    hashes = set()
    with tempfile.TemporaryDirectory(prefix="experiment-004-science-equivalence-") as temp:
        base = Path(temp)
        for workers in (1, 2):
            result = _run_checkpointed_tasks(
                tasks,
                checkpoint_dir=base / f"w{workers}" / "shards",
                output_path=base / f"w{workers}" / "episodes.jsonl",
                workers=workers,
                campaign_kind="nonconfirmatory_pilot_equivalence",
                campaign_binding={"pilot_partition": 43, "selected_manifest_rows": [0, 1]},
                progress=False,
            )
            hashes.add(result["episodes_sha256"])
            scientific_measurements.append(
                {
                    "workers": workers,
                    "elapsed_wall_s": result["elapsed_wall_s"],
                    "episodes_sha256": result["episodes_sha256"],
                    "passed": result["passed"],
                }
            )
    serial = scientific_measurements[0]["elapsed_wall_s"]
    for item in scientific_measurements:
        item["speedup_vs_serial"] = serial / item["elapsed_wall_s"]
    numerical_best = min(numerical["measurements"], key=lambda item: item["elapsed_wall_s"])[
        "workers"
    ]
    selected = min(8, max(1, (cpu or 1) - 3), int(numerical_best))
    result = {
        "schema_version": "experiment-004-parallel-benchmark-1.0",
        "outcome_selection_used": False,
        "partition_44_outcomes_used": False,
        "pilot_rows_selected_prospectively_by_position": [0, 1],
        "host_logical_cpu_count": cpu,
        "numerical_fixture": numerical,
        "scientific_serial_parallel_equivalence": {
            "passed": len(hashes) == 1 and all(x["passed"] for x in scientific_measurements),
            "measurements": scientific_measurements,
            "byte_identical": len(hashes) == 1,
        },
        "selected_default_workers": selected,
        "worker_policy": (
            "min(8, max(1, logical_cpu_count - 3)); explicit --workers override allowed"
        ),
    }
    result["passed"] = bool(
        numerical["passed"]
        and result["scientific_serial_parallel_equivalence"]["passed"]
        and selected >= 1
    )
    return result


def main() -> None:
    root = Path.cwd()
    result = run_benchmark(root)
    output = root / "experiments/004-replacement-confirmatory/parallel-benchmark.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not result["passed"]:
        raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
