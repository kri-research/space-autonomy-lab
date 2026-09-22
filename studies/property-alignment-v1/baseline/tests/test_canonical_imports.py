"""Compare the diagnostic adapter with ordinary imports from the pinned clone."""

from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.paths import evidence_root

EVIDENCE = evidence_root()
sys.path.insert(0, str(EVIDENCE / "src"))
from validation.loader import originals
from kri_space_autonomy.experiment_004 import control as native
from kri_space_autonomy.experiment_004.config import load_config


@pytest.mark.parametrize(
    "state", [(0, -97.5, 0, 0.12), (0, -25, 0, 0), (0.1, -30, 0, 0), (1, -70, 0.01, 0.12)]
)
@pytest.mark.parametrize("health", ["VALID", "DEGRADED"])
def test_original_controller_and_gate_match_adapter(state, health):
    adapted = originals(expanded_cache=True)[-1]
    cfg = load_config(EVIDENCE / "experiments/004/config.json")
    outputs = []
    for module in [native, adapted]:
        controller = module.DeterministicHoldController(cfg)
        snapshot = SimpleNamespace(
            time_s=0.0,
            mean=np.array(state, dtype=float),
            covariance=np.diag([0.01, 0.01, 0.0001, 0.0001]),
            health=getattr(module.FilterHealth, health),
            prediction_only_age_s=0.0,
            consecutive_innovation_rejections=0,
        )
        proposal = controller.decide(module.observation_from_snapshot(snapshot))
        gate = module.EstimatedGeometryMonitor(
            cfg, controller, controller.controller_identity
        ).gate(snapshot, proposal)
        outputs.append((controller.gain, gate))
    np.testing.assert_array_equal(outputs[0][0], outputs[1][0])
    a, b = outputs[0][1], outputs[1][1]
    np.testing.assert_array_equal(a.executed_acceleration_mps2, b.executed_acceleration_mps2)
    assert (a.overridden, a.reason) == (b.overridden, b.reason)
