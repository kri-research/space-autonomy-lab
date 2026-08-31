from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .config import Experiment004Config

BIT_GENERATOR = "PCG64DXSM"
STREAM_CODES = {
    "initial_state": 101,
    "process_disturbance_radial": 102,
    "process_disturbance_alongtrack": 103,
    "primary_measurement": 104,
    "monitor_measurement": 105,
    "fault_parameters": 106,
    "actuator_uncertainty": 107,
    "configuration_run_order": 108,
}


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture_rng(
    config: Experiment004Config,
    *,
    case_code: int,
    replicate: int,
    stream: str,
) -> np.random.Generator:
    """Return an RNG only from the explicitly non-outcome fixture partition."""

    if type(case_code) is not int or case_code < 0:
        raise ValueError("case_code must be a non-negative integer")
    if type(replicate) is not int or replicate < 0:
        raise ValueError("replicate must be a non-negative integer")
    if stream not in STREAM_CODES:
        raise ValueError("unknown Experiment 004 stream")
    sequence = np.random.SeedSequence(
        [
            config.master_seed,
            config.test_fixture_partition_code,
            case_code,
            replicate,
            STREAM_CODES[stream],
        ]
    )
    return np.random.Generator(np.random.PCG64DXSM(sequence))


def _historical_root_ids(root: Path) -> set[str]:
    identifiers: set[str] = set()
    for path in root.glob("experiments/*/seeds/*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line).get("root_seed_id")
            except json.JSONDecodeError:
                continue
            if isinstance(value, str):
                identifiers.add(value)
    return identifiers


def validate_seed_contract(
    config: Experiment004Config,
    contract_path: str | Path,
    root: str | Path = ".",
) -> dict[str, Any]:
    path = Path(contract_path)
    contract = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": config.schema_version,
        "bit_generator": BIT_GENERATOR,
        "master_seed": config.master_seed,
        "derivation": (
            "SeedSequence([master, partition, geometry_case, fault_case, replicate, stream])"
        ),
        "partitions": {
            "dynamics_metric_calibration": {
                "code": config.calibration_partition_code,
                "status": "reserved_not_materialized_or_executed",
                "permitted_use": "prospective dynamics, geometry, and metric calibration only",
            },
            "controller_policy_fit": {
                "code": config.controller_fit_partition_code,
                "status": "reserved_not_materialized_or_executed",
                "permitted_use": (
                    "future fitting only; unused by deterministic reference controller"
                ),
            },
            "design_validation_pilot": {
                "code": config.pilot_partition_code,
                "status": "reserved_not_materialized_or_executed",
                "sample_size": "not_set_in_foundation",
            },
            "future_confirmatory": {
                "code": config.future_confirmatory_partition_code,
                "status": "reserved_not_materialized_size_and_hypothesis_not_set",
                "generator_available": False,
            },
            "non_outcome_test_fixtures": {
                "code": config.test_fixture_partition_code,
                "status": "available_for_deterministic_validation_only",
            },
        },
        "stream_codes": STREAM_CODES,
        "root_identity_namespace": "experiment004:<partition>:<case>:<replicate>",
        "historical_master_domains": [1001, 2002, 3003],
        "replacement_or_extension_allowed": False,
        "outcome_dependent_threshold_selection_allowed": False,
        "pilot_generator_available_at_foundation_freeze": False,
        "future_confirmatory_generator_available_at_foundation_freeze": False,
    }
    errors = [key for key, value in expected.items() if contract.get(key) != value]
    project_root = Path(root)
    forbidden_paths = (
        project_root / "experiments/004/seeds",
        project_root / "experiments/004-confirmatory",
        project_root / "results/experiment-004",
        project_root / "results/experiment-004-confirmatory",
    )
    present = [
        path.relative_to(project_root).as_posix()
        for path in forbidden_paths
        if path.exists()
    ]
    if present:
        errors.append("outcome_or_pilot_paths_present")
    historical_ids = _historical_root_ids(project_root)
    namespace_overlap = sorted(
        identifier for identifier in historical_ids if identifier.startswith("experiment004:")
    )
    if namespace_overlap:
        errors.append("historical_root_namespace_overlap")
    partition_codes = {
        config.calibration_partition_code,
        config.controller_fit_partition_code,
        config.pilot_partition_code,
        config.future_confirmatory_partition_code,
        config.test_fixture_partition_code,
    }
    if len(partition_codes) != 5 or config.master_seed in {1001, 2002, 3003}:
        errors.append("entropy_domain_overlap")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "contract_sha256": sha256_bytes(path.read_bytes()),
        "master_seed": config.master_seed,
        "partition_codes": sorted(partition_codes),
        "historical_root_ids_compared": len(historical_ids),
        "historical_namespace_overlap": len(namespace_overlap),
        "forbidden_paths_present": present,
        "pilot_materialized": False,
        "future_confirmatory_materialized": False,
    }
