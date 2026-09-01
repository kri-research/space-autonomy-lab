from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .config import Experiment005Config

BIT_GENERATOR = "PCG64DXSM"
STREAM_CODES = {
    "initial_truth_state": 201,
    "mechanics_perturbation": 202,
    "primary_navigation": 203,
    "monitor_navigation": 204,
    "challenge_parameters": 205,
    "actuation": 206,
    "cell_order": 207,
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fixture_rng(
    config: Experiment005Config,
    *,
    geometry_case: int,
    challenge_case: int,
    replicate: int,
    stream: str,
) -> np.random.Generator:
    """Return an RNG from only the deterministic non-outcome fixture domain."""

    integers = (geometry_case, challenge_case, replicate)
    if any(type(value) is not int or value < 0 for value in integers):
        raise ValueError("fixture coordinates must be non-negative integers")
    if stream not in STREAM_CODES:
        raise ValueError("unknown Experiment 005 stream")
    sequence = np.random.SeedSequence(
        [
            config.master_seed,
            config.test_fixture_partition_code,
            geometry_case,
            challenge_case,
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
    config: Experiment005Config,
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
            "SeedSequence([master, partition, geometry_case, challenge_case, "
            "replicate, stream])"
        ),
        "partitions": {
            "mechanics_calibration": {
                "code": config.mechanics_calibration_partition_code,
                "status": "reserved_not_materialized_or_executed",
                "permitted_use": (
                    "future prospective mechanics-envelope and metric calibration only"
                ),
            },
            "design_validation_pilot": {
                "code": config.future_pilot_partition_code,
                "status": "reserved_not_materialized_size_and_design_not_set",
                "generator_available": False,
            },
            "future_confirmatory": {
                "code": config.future_confirmatory_partition_code,
                "status": (
                    "reserved_not_materialized_size_hypothesis_and_design_not_set"
                ),
                "generator_available": False,
            },
            "non_outcome_test_fixtures": {
                "code": config.test_fixture_partition_code,
                "status": "available_for_deterministic_validation_only",
            },
        },
        "stream_codes": STREAM_CODES,
        "root_identity_namespace": "experiment005:<partition>:<case>:<replicate>",
        "historical_master_domains": [1001, 2002, 3003, 4004],
        "historical_experiment004_partition_codes": [41, 42, 43, 44, 45, 941],
        "replacement_extension_or_outcome_tuning_allowed": False,
        "experiment004_outcomes_permitted_for_design_selection": False,
        "mechanics_calibration_generator_available_at_foundation_freeze": False,
        "pilot_generator_available_at_foundation_freeze": False,
        "future_confirmatory_generator_available_at_foundation_freeze": False,
    }
    errors = [key for key, value in expected.items() if contract.get(key) != value]
    project_root = Path(root)
    forbidden_paths = (
        project_root / "experiments/005/seeds",
        project_root / "experiments/005-pilot",
        project_root / "experiments/005-confirmatory",
        project_root / "results/experiment-005",
        project_root / "results/experiment-005-pilot",
        project_root / "results/experiment-005-confirmatory",
    )
    present = [
        item.relative_to(project_root).as_posix() for item in forbidden_paths if item.exists()
    ]
    if present:
        errors.append("outcome_or_calibration_paths_present")
    historical_ids = _historical_root_ids(project_root)
    overlap = sorted(
        identifier for identifier in historical_ids if identifier.startswith("experiment005:")
    )
    if overlap:
        errors.append("historical_root_namespace_overlap")
    partition_codes = {
        config.mechanics_calibration_partition_code,
        config.future_pilot_partition_code,
        config.future_confirmatory_partition_code,
        config.test_fixture_partition_code,
    }
    historical_codes = {41, 42, 43, 44, 45, 941}
    if partition_codes & historical_codes or config.master_seed in {1001, 2002, 3003, 4004}:
        errors.append("entropy_domain_overlap")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "contract_sha256": sha256_bytes(path.read_bytes()),
        "master_seed": config.master_seed,
        "partition_codes": sorted(partition_codes),
        "historical_root_ids_compared": len(historical_ids),
        "historical_namespace_overlap": len(overlap),
        "forbidden_paths_present": present,
        "mechanics_calibration_materialized": False,
        "pilot_materialized": False,
        "future_confirmatory_materialized": False,
    }
