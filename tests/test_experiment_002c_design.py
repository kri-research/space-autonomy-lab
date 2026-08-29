import json
from pathlib import Path

from kri_space_autonomy.experiment_002.config import PILOT_STRATA
from kri_space_autonomy.experiment_002c.config import (
    NumericalBounds,
    load_numerical_amendment_config,
)
from kri_space_autonomy.experiment_002c.seeds import materialize_scenario_002c


def _historical_root_ids() -> set[str]:
    root_ids: set[str] = set()
    for directory in (Path("experiments/002/seeds"), Path("experiments/002b/seeds")):
        for path in directory.glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                root_id = json.loads(line).get("root_seed_id")
                if root_id is not None:
                    root_ids.add(str(root_id))
    return root_ids


def test_numerical_only_scope_size_partition_and_bounds_are_frozen():
    amendment, _ = load_numerical_amendment_config("experiments/002c/config.json")

    assert amendment.replay_partition_code == 24
    assert amendment.replay_seeds_per_stratum == 1
    assert amendment.replay_cases == 24
    assert amendment.convergence_bound_fraction == 0.25
    assert amendment.acceptance_bounds == NumericalBounds(
        range_m=1e-8,
        velocity_mps=1e-10,
        achieved_acceleration_mps2=1e-12,
        propellant_fraction=1e-10,
        event_time_s=2e-7,
        dwell_fraction=1e-10,
        collision_residual_m=1e-10,
        depletion_residual_fraction=1e-12,
    )


def test_002c_seed_roots_are_disjoint_from_experiments_002_and_002b():
    amendment, production = load_numerical_amendment_config(
        "experiments/002c/config.json"
    )
    historical = _historical_root_ids()
    generated: set[str] = set()
    for stratum in PILOT_STRATA:
        scenario = materialize_scenario_002c(amendment, production, stratum, 0)
        assert scenario.root_seed_id not in historical
        assert scenario.root_seed_id not in generated
        generated.add(scenario.root_seed_id)
        assert scenario.schema_version == amendment.schema_version
    assert len(generated) == 6
