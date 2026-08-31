from __future__ import annotations

import ast
import inspect
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import scipy

from kri_space_autonomy.experiment_003.workflow import repository_publication_scan
from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004.seeds import canonical_json, sha256_bytes
from kri_space_autonomy.experiment_004.validation import run_foundation_checks

from .analysis import validate_complete_cells
from .calibration import verify_calibration
from .config import (
    CASE_IDS,
    CONFIGURATIONS,
    FOUNDATION_COMMIT,
    FOUNDATION_FREEZE_ID,
    FOUNDATION_READINESS_ID,
    PilotCase,
    PilotConfig,
)
from .runner import _nominal_control, run_block
from .seeds import test_fixture_scenario, validate_seed_contract

FOUNDATION_FREEZE_PATH = Path("experiments/004/freeze-manifest.json")
FOUNDATION_READINESS_PATH = Path("experiments/004/readiness.json")
FOUNDATION_VALIDATION_PATH = Path("experiments/004/validation-evidence.json")
PILOT_CONTRACT_PATH = Path("experiments/004-pilot/seed-contract.json")
PILOT_GATES_PATH = Path("experiments/004-pilot/gates.json")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _self_hashed(path: Path, field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(field)
    if sha256_bytes(canonical_json(value)) != identity:
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def foundation_identity(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest = _self_hashed(root / FOUNDATION_FREEZE_PATH, "freeze_id")
        readiness = _self_hashed(root / FOUNDATION_READINESS_PATH, "readiness_id")
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors_preview": [f"foundation_load:{exc}"]}
    if manifest.get("freeze_id") != FOUNDATION_FREEZE_ID:
        errors.append("foundation_freeze_id")
    if readiness.get("readiness_id") != FOUNDATION_READINESS_ID:
        errors.append("foundation_readiness_id")
    if readiness.get("freeze_id") != FOUNDATION_FREEZE_ID:
        errors.append("foundation_readiness_binding")
    if readiness.get("status") != "READY_FOR_DESIGN_VALIDATION_PILOT":
        errors.append("foundation_status")
    source_mismatches = []
    for relative, expected in manifest.get("source_file_hashes", {}).items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            source_mismatches.append(relative)
    if source_mismatches:
        errors.append("foundation_source_hashes")
    validation = root / FOUNDATION_VALIDATION_PATH
    if (
        not validation.is_file()
        or sha256_bytes(validation.read_bytes()) != manifest.get("validation_sha256")
    ):
        errors.append("foundation_validation_identity")
    head = _git(root, "rev-parse", "HEAD")
    # The foundation's self-hashed manifest is the authoritative byte-identity
    # anchor. CI may use a shallow checkout that does not contain FOUNDATION_COMMIT,
    # so git ancestry is an additional check when that object is locally available,
    # not a prerequisite for verifying the frozen bytes.
    foundation_commit_present = subprocess.run(
        ["git", "cat-file", "-e", f"{FOUNDATION_COMMIT}^{{commit}}"],
        cwd=root,
        capture_output=True,
    ).returncode == 0
    ancestor: bool | None = None
    if foundation_commit_present:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", FOUNDATION_COMMIT, "HEAD"],
            cwd=root,
            capture_output=True,
        ).returncode == 0
        if not ancestor:
            errors.append("foundation_commit_anchor")
    # Raw-byte source hashes above are stricter than a git path-diff check and
    # remain valid after the pilot-design commit as well as in shallow CI clones.
    changed = list(source_mismatches)
    forbidden = (
        root / "experiments/004/seeds",
        root / "results/experiment-004",
        root / "experiments/004-confirmatory",
        root / "results/experiment-004-confirmatory",
        root / "experiments/004-pilot/seeds",
        root / "results/experiment-004-pilot",
    )
    present = [path.relative_to(root).as_posix() for path in forbidden if path.exists()]
    if present:
        errors.append("experiment_004_outcome_paths")
    materialized_root_rows = []
    for path in root.glob("**/*.jsonl"):
        if any(part in {".git", ".venv"} for part in path.parts):
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "experiment004:43:" in line or "experiment004:44:" in line:
                materialized_root_rows.append(f"{path.relative_to(root)}:{line_number}")
    if materialized_root_rows:
        errors.append("partition_43_or_44_root_rows")
    return {
        "passed": not errors,
        "errors_preview": errors[:30],
        "freeze_id": manifest.get("freeze_id"),
        "readiness_id": readiness.get("readiness_id"),
        "status": readiness.get("status"),
        "head": head,
        "foundation_commit_object_present": foundation_commit_present,
        "foundation_commit_ancestor": ancestor,
        "source_files_verified": len(manifest.get("source_file_hashes", {})),
        "source_mismatches": source_mismatches,
        "git_changed_frozen_paths": changed,
        "forbidden_outcome_paths_present": present,
        "materialized_partition_root_rows": materialized_root_rows[:20],
        "pilot_or_confirmatory_outcomes_materialized": False,
    }


def historical_integrity(root: Path) -> dict[str, Any]:
    historical_prefixes = (
        "src/kri_space_autonomy/experiment_001",
        "src/kri_space_autonomy/experiment_002",
        "src/kri_space_autonomy/experiment_003",
        "experiments/001",
        "experiments/002",
        "experiments/003",
        "results/baseline.json",
        "results/experiment-001",
        "results/experiment-002",
        "results/experiment-003",
        "docs/experiment-001",
        "docs/experiment-002",
        "docs/experiment-003",
        "artifacts/experiment-002",
    )
    tracked = _git(root, "ls-files").splitlines()
    historical_paths = [
        path for path in tracked if any(path.startswith(prefix) for prefix in historical_prefixes)
    ]
    changed_output = _git(
        root,
        "diff",
        "--name-only",
        FOUNDATION_COMMIT,
        "--",
        *historical_paths,
    )
    changed = [line for line in changed_output.splitlines() if line]
    checksum_errors = []
    checksum_directories = 0
    for checksum in sorted(root.glob("results/experiment-*/SHA256SUMS")):
        checksum_directories += 1
        for line in checksum.read_text(encoding="utf-8").splitlines():
            expected, name = line.split("  ", 1)
            candidate = checksum.parent / name
            actual = sha256_bytes(candidate.read_bytes()) if candidate.is_file() else None
            if actual != expected:
                checksum_errors.append(f"{checksum.parent.name}/{name}")
    commands = (
        [
            "uv",
            "run",
            "python",
            "-m",
            "kri_space_autonomy.experiment_002_confirmatory.workflow",
            "verify-freeze",
        ],
        [
            "uv",
            "run",
            "python",
            "-m",
            "kri_space_autonomy.experiment_002_confirmatory.workflow",
            "verify-results",
        ],
        [
            "uv",
            "run",
            "python",
            "-c",
            (
                "from pathlib import Path; from kri_space_autonomy.experiment_003.workflow "
                "import verify_freeze,verify_results; r=Path.cwd(); "
                "assert verify_freeze(r,require_unmaterialized=False)['passed']; "
                "assert verify_results(r)['passed']"
            ),
        ],
        [
            "uv",
            "run",
            "python",
            "-c",
            (
                "from pathlib import Path; "
                "from kri_space_autonomy.experiment_003_confirmatory.workflow "
                "import verify_freeze,verify_results; r=Path.cwd(); "
                "assert verify_freeze(r,require_unmaterialized=False)['passed']; "
                "assert verify_results(r)['passed']"
            ),
        ],
    )
    command_results = []
    for command in commands:
        completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
        command_results.append(
            {
                "command": " ".join(command),
                "returncode": completed.returncode,
                "passed": completed.returncode == 0,
            }
        )
    return {
        "passed": bool(
            not changed
            and not checksum_errors
            and checksum_directories == 7
            and all(item["passed"] for item in command_results)
        ),
        "paths_compared_to_foundation_commit": len(historical_paths),
        "changed_paths": changed[:30],
        "checksum_directories_verified": checksum_directories,
        "checksum_errors": checksum_errors[:30],
        "historical_verifiers": command_results,
    }


def runtime_identity(root: Path) -> dict[str, Any]:
    freeze = json.loads((root / FOUNDATION_FREEZE_PATH).read_text(encoding="utf-8"))
    expected = freeze["dependency_runtime_identity"]
    dependency_hashes = {
        path: sha256_bytes((root / path).read_bytes())
        for path in (".python-version", "pyproject.toml", "uv.lock")
    }
    observed = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "os": platform.system(),
        "architecture": platform.machine(),
        "thread_variables": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
            )
            if os.environ.get(name) is not None
        },
    }
    uv = subprocess.run(["uv", "--version"], cwd=root, text=True, capture_output=True)
    mismatches = []
    if dependency_hashes != expected["dependency_file_hashes"]:
        mismatches.append("dependency_file_hashes")
    for key, value in expected["observed"].items():
        if observed.get(key) != value:
            mismatches.append(key)
    return {
        "passed": not mismatches and uv.returncode == 0,
        "dependency_file_hashes": dependency_hashes,
        "foundation_expected_observed": expected["observed"],
        "observed": observed,
        "uv_version": uv.stdout.strip(),
        "mismatches": mismatches,
        "exact_platform_match_required_for_replay": True,
    }


def matrix_and_gates(
    root: Path,
    pilot: PilotConfig,
    cases: tuple[PilotCase, ...],
) -> dict[str, Any]:
    gates = json.loads((root / PILOT_GATES_PATH).read_text(encoding="utf-8"))
    domains = {case.domain for case in cases}
    required_domains = {
        "mission_feasibility",
        "physical_geometry",
        "primary_estimator",
        "monitor_estimator",
        "monitor_logic",
        "shared_cause",
        "actuation",
        "disturbance",
    }
    complete = gates.get("gates", {}).get("complete_cells", {})
    analysis = gates.get("gates", {}).get("analysis", {})
    codes = {(case.geometry_code, case.fault_code, case.case_code) for case in cases}
    return {
        "passed": bool(
            tuple(case.id for case in cases) == CASE_IDS
            and len(codes) == len(cases) == 11
            and required_domains <= domains
            and pilot.pilot_blocks == 44
            and pilot.pilot_episodes == 88
            and complete.get("expected_blocks") == 44
            and complete.get("expected_episodes") == 88
            and analysis
            == {
                "mode": "descriptive_mechanistic_gate_only",
                "p_values_allowed": False,
                "superiority_or_noninferiority_tests_allowed": False,
                "architecture_effect_claims_allowed": False,
                "multiplicity_family_defined": False,
            }
        ),
        "case_ids": [case.id for case in cases],
        "domains": sorted(domains),
        "blocks": pilot.pilot_blocks,
        "episodes": pilot.pilot_episodes,
        "replay_blocks": pilot.replay_blocks,
        "replay_episodes": pilot.replay_episodes,
        "configuration_ids": list(pilot.configuration_ids),
    }


def information_boundary() -> dict[str, Any]:
    signature = tuple(inspect.signature(_nominal_control).parameters)
    expected = (
        "primary_snapshot",
        "monitor_snapshot",
        "controller",
        "monitor",
        "configuration_id",
    )
    tree = ast.parse(inspect.getsource(_nominal_control))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    prohibited = sorted(
        names
        & {
            "latent_state",
            "truth_state",
            "scenario",
            "fault_label",
            "root_seed_id",
            "evaluator",
        }
    )
    return {
        "passed": signature == expected and not prohibited,
        "control_function_parameters": list(signature),
        "prohibited_names_found": prohibited,
        "controller_inputs": "primary navigation snapshot only",
        "monitor_inputs": "monitor navigation snapshot and proposed vector command only",
    }


def deterministic_fixture_replay(
    pilot: PilotConfig,
    cases: tuple[PilotCase, ...],
    root: Path,
) -> dict[str, Any]:
    foundation = load_config(root / "experiments/004/config.json")
    case = next(item for item in cases if item.id == "P01_forced_collision")
    scenario, _ = test_fixture_scenario(pilot, foundation, case, 0)
    first = [row.to_dict() for row in run_block(pilot, foundation, case, scenario)]
    second = [row.to_dict() for row in run_block(pilot, foundation, case, scenario)]
    first_digest = sha256_bytes(canonical_json(first))
    second_digest = sha256_bytes(canonical_json(second))
    cells = validate_complete_cells([], pilot, cases)
    return {
        "passed": bool(
            first_digest == second_digest
            and len(first) == len(CONFIGURATIONS)
            and all(row["physical_collision"] for row in first)
        ),
        "partition_code": pilot.test_fixture_partition_code,
        "root_seed_id": scenario.root_seed_id,
        "configuration_order": list(scenario.configuration_run_order),
        "first_digest": first_digest,
        "second_digest": second_digest,
        "future_complete_cell_validator_expected_rows": cells["expected_rows"],
    }


def partition_44_inert(root: Path, pilot: PilotConfig) -> dict[str, Any]:
    contract = json.loads((root / PILOT_CONTRACT_PATH).read_text(encoding="utf-8"))
    state = contract["partitions"]["future_confirmatory"]
    function_names: set[str] = set()
    for path in (root / "src/kri_space_autonomy/experiment_004_pilot").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function_names.update(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
    forbidden_symbols = ("materialize_confirmatory", "run_confirmatory")
    found = sorted(function_names & set(forbidden_symbols))
    paths = (
        root / "experiments/004-confirmatory",
        root / "results/experiment-004-confirmatory",
    )
    return {
        "passed": bool(
            state
            == {
                "code": pilot.future_confirmatory_partition_code,
                "status": "reserved_unmaterialized_hypothesis_and_sample_size_not_set",
                "generator_available": False,
            }
            and not found
            and not any(path.exists() for path in paths)
        ),
        "state": state,
        "forbidden_symbols_found": found,
        "paths_present": [path.relative_to(root).as_posix() for path in paths if path.exists()],
    }


def publication_privacy(root: Path) -> dict[str, Any]:
    scan = repository_publication_scan(root)
    scan["passed"] = bool(scan["passed"] and scan["opaque_files"] == 0)
    scan["opaque_files_are_fatal"] = True
    return scan


def run_design_checks(
    root: Path,
    pilot: PilotConfig,
    cases: tuple[PilotCase, ...],
    *,
    recompute_calibration: bool = True,
) -> dict[str, Any]:
    foundation = foundation_identity(root)
    historical = historical_integrity(root)
    calibration = verify_calibration(root, recompute=recompute_calibration)
    seed_contract = validate_seed_contract(
        pilot,
        root / PILOT_CONTRACT_PATH,
        root=root,
    )
    matrix = matrix_and_gates(root, pilot, cases)
    foundation_numerical = run_foundation_checks(load_config(root / "experiments/004/config.json"))
    boundaries = information_boundary()
    replay = deterministic_fixture_replay(pilot, cases, root)
    partition44 = partition_44_inert(root, pilot)
    runtime = runtime_identity(root)
    publication = publication_privacy(root)
    checks = {
        "foundation_freeze_readiness_identity": foundation,
        "partition_41_calibration_provenance": calibration,
        "sample_count_matrix_and_gates": matrix,
        "forced_event_and_hcw_foundation": foundation_numerical,
        "controller_monitor_information_boundary": boundaries,
        "deterministic_runner_replay_fixture": replay,
        "seed_domain_and_materialization_contract": seed_contract,
        "partition_44_reserved_inert": partition44,
        "dependency_runtime_identity": runtime,
        "historical_experiment_001_003_integrity": historical,
        "publication_privacy": publication,
    }
    return {
        "passed": all(bool(check.get("passed")) for check in checks.values()),
        "checks": checks,
        "partition_43_materialized": False,
        "partition_43_executed": False,
        "partition_44_materialized": False,
        "confirmatory_inference_enabled": False,
        "scientific_findings_claimed": False,
    }
