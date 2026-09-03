from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import load_config as load_e004_config
from kri_space_autonomy.experiment_005.config import load_config as load_e005_config
from kri_space_autonomy.experiment_005.workflow import dependency_runtime_identity
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    TransferCase,
    TransferPilotConfig,
    load_case_matrix,
)
from kri_space_autonomy.experiment_005_transfer_pilot.runner import (
    _scan_shards,
    validate_complete_cells,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    TransferScenario,
    canonical_json,
    scenario_from_row,
)
from kri_space_autonomy.experiment_005_transfer_pilot.validation import (
    information_boundary,
    partition_53_inert,
    publication_privacy,
)
from kri_space_autonomy.experiment_005_transfer_pilot_closeout import (
    verify as verify_invalid_closeout,
)
from kri_space_autonomy.experiment_005_transfer_pilot_replacement.runner import (
    _campaign_record,
)
from kri_space_autonomy.experiment_005_transfer_pilot_replacement.seeds import (
    RESULT_DIRECTORY,
    SEED_DIRECTORY,
    materialize_replacement_scenario,
    replacement_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot_replacement.workflow import (
    verify_freeze,
)

SCHEMA_VERSION = "experiment-005-transfer-pilot-replacement-closeout-1.0"
CLOSEOUT_BASE_COMMIT = "a311c4f6439c13666a1df6b102fd0fd2bbd35a55"
AMENDMENT_FREEZE_ID = "01504ff16ccf8a79dad67f88c4d40920be39dfa929169ccb72fdfcede18b34c1"
AMENDMENT_READINESS_ID = "3181e1a9b40c3ab32b684934d8c975b3eeeee44c2b38cd9dc80e0f0c589328c0"
ORIGINAL_DESIGN_FREEZE_ID = "3fa9fd6e9e4d3146af6495c07599ed792cfb52ce16e90d0dca234ed64295be8b"
SEED_MANIFEST_SHA256 = "45aa70402ee19586c14c24e4f75dedfd572d8cced9e8d9c51969c801e6704fab"
REPLAY_SPEC_SHA256 = "405801069294307513f86239f9b218b77ec62cc84a490fc34d759f17798b5aab"
SEED_INDEX_SHA256 = "818ee087d144385d6e75919d10406701fe9acb1831622802a696fe96984173e9"
CAMPAIGN_ROWS_SHA256 = "0a890fce567b0a6138c487b8ce34da5ed63ee8343a222e110434c832e05de338"
REPLAY_ROWS_SHA256 = "88435a577419c3e426ede0f1fd9191fcc40b30d041900fcabef117b54e4e21cb"
EXECUTION_SUMMARY_SHA256 = "14e45aad15b1de8b7a43efeeea45b3c6a220ddfd1a25e399e063f16ca54584d4"
CAMPAIGN_ID = "445e8e689dee7f4d01ff1e41c6fa161811426595cdd6218e35c00f108b1e8123"
REPLAY_CAMPAIGN_ID = "833e6b06fb14b3c59abdce659a85006c8c8c413d801508bfb7ee453a5edea651"

DESIGN_DIRECTORY = Path("experiments/005-transfer-pilot")
RESULT = RESULT_DIRECTORY
SEEDS = SEED_DIRECTORY
ANALYSIS_PATH = RESULT / "analysis.json"
QC_PATH = RESULT / "qc.json"
DESIGN_INTEGRITY_PATH = RESULT / "design-integrity-postexecution.json"
REPRODUCIBILITY_PATH = RESULT / "reproducibility.json"
LEDGER_PATH = RESULT / "execution-ledger.json"
REPORT_PATH = RESULT / "execution-report.md"
PHASE_PATH = RESULT / "phase-validation.json"
RELEASE_SCAN_PATH = RESULT / "release-scan.json"
VERIFICATION_PATH = RESULT / "result-verification.json"
MANIFEST_PATH = RESULT / "manifest.json"
CHECKSUMS_PATH = RESULT / "checksums.sha256"
DOC_PATH = Path("docs/experiment-005-transfer-pilot-results.md")
ROADMAP_PATH = Path("docs/research-roadmap.md")
SOURCE_PATH = Path(
    "src/kri_space_autonomy/experiment_005_transfer_pilot_replacement_closeout.py"
)
TEST_PATH = Path("tests/test_experiment_005_transfer_pilot_replacement_closeout.py")
CONFTEST_PATH = Path("tests/conftest.py")

CLOSEOUT_ARTIFACTS = (
    ANALYSIS_PATH,
    QC_PATH,
    DESIGN_INTEGRITY_PATH,
    REPRODUCIBILITY_PATH,
    LEDGER_PATH,
    REPORT_PATH,
    PHASE_PATH,
    RELEASE_SCAN_PATH,
    VERIFICATION_PATH,
    MANIFEST_PATH,
    CHECKSUMS_PATH,
)

NEXT_TASK = (
    "freeze a separate prospective partition-53 confirmatory design that defines its scientific "
    "question, estimands, case matrix, sample size and power basis, gatekeeping and multiplicity, "
    "analysis, replay subset, seed contract, and write-once execution protocol while leaving "
    "partition 53 unmaterialized and unexecuted"
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path.name}")
    return value


def _jsonl(path: Path) -> tuple[list[bytes], list[dict[str, Any]]]:
    raw = path.read_bytes().splitlines()
    rows = [json.loads(line) for line in raw]
    if not all(isinstance(row, dict) for row in rows):
        raise RuntimeError(f"expected JSON objects: {path.name}")
    return raw, rows


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(value)


def _run(root: Path, command: list[str], ident: str) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    return {
        "id": ident,
        "command": " ".join(command),
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
    }


def _is_ancestor(root: Path, commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
        ).returncode
        == 0
    )


def _finite(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _load_inputs(
    root: Path,
) -> tuple[
    TransferPilotConfig,
    tuple[TransferCase, ...],
    tuple[TransferScenario, ...],
    list[bytes],
    list[dict[str, Any]],
]:
    pilot = replacement_pilot_config(root)
    cases = load_case_matrix(root / DESIGN_DIRECTORY / "case-matrix.json")
    raw, rows = _jsonl(root / SEEDS / "pilot.jsonl")
    scenarios = tuple(scenario_from_row(row) for row in rows)
    return pilot, cases, scenarios, raw, rows


def frozen_identity(root: Path) -> dict[str, Any]:
    amendment = verify_freeze(root, require_unmaterialized=False)
    invalid = verify_invalid_closeout(root)
    pilot = replacement_pilot_config(root)
    partition_53 = partition_53_inert(root, pilot)
    runtime = dependency_runtime_identity(root)
    checks = {
        "closeout_base_is_ancestor": _is_ancestor(root, CLOSEOUT_BASE_COMMIT),
        "amendment_freeze": bool(
            amendment.get("passed")
            and amendment.get("freeze_id") == AMENDMENT_FREEZE_ID
            and amendment.get("readiness_id") == AMENDMENT_READINESS_ID
            and amendment.get("scientific_design", {}).get("passed") is True
            and amendment.get("scientific_design", {}).get("scientific_field_drift") == []
        ),
        "invalid_partition_52_preserved": bool(
            invalid.get("passed")
            and invalid.get("decision") == "pilot_invalid_infrastructure_failure"
            and invalid.get("terminal_failure", {}).get("completed_blocks") == 0
            and invalid.get("terminal_failure", {}).get("durable_episode_rows") == 0
        ),
        "partition_53_untouched": partition_53.get("passed") is True,
        "runtime_identity": runtime.get("passed") is True,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "closeout_base_commit": CLOSEOUT_BASE_COMMIT,
        "amendment_freeze_id": amendment.get("freeze_id"),
        "amendment_readiness_id": amendment.get("readiness_id"),
        "original_design_freeze_id": ORIGINAL_DESIGN_FREEZE_ID,
        "scientific_design": amendment.get("scientific_design"),
        "invalid_partition_52": invalid,
        "partition_53": partition_53,
        "runtime_identity": runtime,
    }


def _historical_root_and_scenario_ids(root: Path) -> tuple[set[str], set[str]]:
    roots: set[str] = set()
    scenarios: set[str] = set()
    excluded = (root / SEEDS, root / RESULT)
    for base in (root / "experiments", root / "results"):
        for path in base.rglob("*.jsonl"):
            if any(
                parent == excluded_path
                for parent in path.parents
                for excluded_path in excluded
            ):
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                root_id = row.get("root_seed_id")
                scenario_hash = row.get("scenario_hash")
                if isinstance(root_id, str):
                    roots.add(root_id)
                if isinstance(scenario_hash, str):
                    scenarios.add(scenario_hash)
    return roots, scenarios


def seed_evidence(root: Path) -> dict[str, Any]:
    pilot, cases, scenarios, raw, rows = _load_inputs(root)
    foundation = load_e005_config(root / "experiments/005/config.json", root=root)
    e004 = load_e004_config(root / "experiments/004/config.json")
    index = _json(root / SEEDS / "index.json")
    replay = _json(root / SEEDS / "replay-subset.json")
    expected_keys = [
        (case.id, replicate)
        for case in cases
        for replicate in range(pilot.pilot_roots_per_case)
    ]
    observed_keys = [(scenario.case_id, scenario.replicate) for scenario in scenarios]
    roots = [scenario.root_seed_id for scenario in scenarios]
    rederived = []
    case_map = {case.id: case for case in cases}
    for scenario in scenarios:
        expected = materialize_replacement_scenario(
            pilot,
            foundation,
            e004,
            case_map[scenario.case_id],
            scenario.replicate,
            amendment_freeze_id=AMENDMENT_FREEZE_ID,
        )
        rederived.append(canonical_json(scenario.to_dict()) == canonical_json(expected.to_dict()))
    expected_replay = [scenario.root_seed_id for scenario in scenarios if scenario.replicate == 0]
    historical_roots, historical_scenarios = _historical_root_and_scenario_ids(root)
    current_scenarios = {scenario.scenario_hash for scenario in scenarios}
    order_balanced = all(
        {
            scenario.configuration_run_order
            for scenario in scenarios
            if scenario.case_id == case.id
        }
        == {
            tuple(pilot.configuration_ids),
            tuple(reversed(pilot.configuration_ids)),
        }
        for case in cases
    )
    checks = {
        "canonical_manifest": all(
            line == canonical_json(row) for line, row in zip(raw, rows, strict=True)
        ),
        "exact_frozen_order": observed_keys == expected_keys,
        "twenty_unique_partition_54_roots": bool(
            len(roots) == len(set(roots)) == pilot.pilot_blocks == 20
            and all(root.startswith("experiment005:54:") for root in roots)
        ),
        "amendment_freeze_binding": all(
            scenario.design_freeze_id == AMENDMENT_FREEZE_ID for scenario in scenarios
        ),
        "deterministic_rederivation": all(rederived),
        "historical_root_overlap_zero": not (set(roots) & historical_roots),
        "partition_52_scenario_reuse_zero": not (current_scenarios & historical_scenarios),
        "within_case_order_balance": order_balanced,
        "replay_selection_frozen": bool(
            replay.get("root_seed_ids") == expected_replay
            and replay.get("expected_blocks") == pilot.replay_blocks == 10
            and replay.get("expected_episodes") == pilot.replay_episodes == 20
        ),
        "index_identity": bool(
            index.get("partition_code") == 54
            and index.get("root_rows") == 20
            and index.get("planned_episode_rows") == 40
            and index.get("replay_root_rows") == 10
            and index.get("replay_episode_rows") == 20
            and index.get("amendment_freeze_id") == AMENDMENT_FREEZE_ID
            and index.get("amendment_readiness_id") == AMENDMENT_READINESS_ID
            and index.get("maximum_retries") == 0
            and index.get("maximum_replacement_roots") == 0
            and index.get("replacement_extension_or_count_drift_allowed") is False
        ),
        "frozen_hashes": bool(
            _sha(root / SEEDS / "pilot.jsonl") == SEED_MANIFEST_SHA256
            and _sha(root / SEEDS / "replay-subset.json") == REPLAY_SPEC_SHA256
            and _sha(root / SEEDS / "index.json") == SEED_INDEX_SHA256
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "root_rows": len(rows),
        "unique_roots": len(set(roots)),
        "historical_root_overlap": len(set(roots) & historical_roots),
        "partition_52_scenario_hash_overlap": len(current_scenarios & historical_scenarios),
        "manifest_sha256": _sha(root / SEEDS / "pilot.jsonl"),
        "replay_spec_sha256": _sha(root / SEEDS / "replay-subset.json"),
        "index_sha256": _sha(root / SEEDS / "index.json"),
        "replay_root_ids": expected_replay,
    }


def _checkpoint_evidence(
    root: Path,
    relative: str,
    scenarios: tuple[TransferScenario, ...],
    expected_id: str,
    expected_rows_sha256: str,
) -> dict[str, Any]:
    directory = root / RESULT / relative
    checkpoint = directory / "shards"
    record = _campaign_record(scenarios)
    campaign_path = checkpoint / "campaign.json"
    campaign_exact = campaign_path.read_bytes() == canonical_json(record) + b"\n"
    try:
        shards = _scan_shards(checkpoint, scenarios, record["campaign_id"])
        shard_validation = True
    except RuntimeError:
        shards = {}
        shard_validation = False
    content = b""
    if shard_validation and len(shards) == len(scenarios):
        content = b"".join(
            canonical_json(row) + b"\n"
            for index in range(len(scenarios))
            for row in shards[index]["rows"]
        )
    output_path = directory / "pilot-episodes.jsonl"
    output = output_path.read_bytes()
    failure_files = list((checkpoint / "failures").glob("*.json"))
    transient = [
        path.relative_to(root).as_posix()
        for path in checkpoint.rglob("*")
        if path.is_file() and (path.name.endswith(".tmp") or path.name == ".campaign.lock")
    ]
    checks = {
        "campaign_identity": bool(
            campaign_exact
            and record["campaign_id"] == expected_id
            and record["partition_code"] == 54
            and record["maximum_retries"] == 0
            and record["maximum_replacement_roots"] == 0
        ),
        "all_content_hashed_shards_valid": shard_validation
        and len(shards) == len(scenarios),
        "canonical_assembly": output == content,
        "frozen_output_hash": hashlib.sha256(output).hexdigest() == expected_rows_sha256,
        "zero_terminal_failures": not failure_files,
        "zero_transient_files": not transient,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "campaign_id": record["campaign_id"],
        "blocks": len(shards),
        "episodes": len(output.splitlines()),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "terminal_failure_files": len(failure_files),
        "transient_files": transient,
    }


def execution_evidence(root: Path) -> dict[str, Any]:
    pilot, _, scenarios, _, _ = _load_inputs(root)
    replay_scenarios = tuple(scenario for scenario in scenarios if scenario.replicate == 0)
    campaign = _checkpoint_evidence(
        root,
        "campaign",
        scenarios,
        CAMPAIGN_ID,
        CAMPAIGN_ROWS_SHA256,
    )
    replay = _checkpoint_evidence(
        root,
        "replay",
        replay_scenarios,
        REPLAY_CAMPAIGN_ID,
        REPLAY_ROWS_SHA256,
    )
    _, rows = _jsonl(root / RESULT / "campaign/pilot-episodes.jsonl")
    replay_bytes = (root / RESULT / "replay/pilot-episodes.jsonl").read_bytes()
    selected = {scenario.root_seed_id for scenario in replay_scenarios}
    expected_replay = b"".join(
        canonical_json(row) + b"\n" for row in rows if row.get("root_seed_id") in selected
    )
    summary = _json(root / RESULT / "execution-summary.json")
    recorded_campaign = summary.get("campaign", {})
    recorded_replay = summary.get("replay", {})
    checks = {
        "campaign_checkpoint_integrity": campaign["passed"],
        "replay_checkpoint_integrity": replay["passed"],
        "replay_byte_equivalent": replay_bytes == expected_replay,
        "execution_summary_hash": _sha(root / RESULT / "execution-summary.json")
        == EXECUTION_SUMMARY_SHA256,
        "summary_matches_raw_campaign": bool(
            recorded_campaign.get("campaign_id") == campaign["campaign_id"]
            and recorded_campaign.get("output_sha256") == campaign["output_sha256"]
            and recorded_campaign.get("cells") == campaign["blocks"] == 20
            and recorded_campaign.get("rows") == campaign["episodes"] == 40
            and recorded_campaign.get("complete") is True
            and recorded_campaign.get("canonical_assembly") is True
        ),
        "summary_matches_raw_replay": bool(
            recorded_replay.get("campaign_id") == replay["campaign_id"]
            and recorded_replay.get("output_sha256") == replay["output_sha256"]
            and recorded_replay.get("cells") == replay["blocks"] == 10
            and recorded_replay.get("rows") == replay["episodes"] == 20
            and recorded_replay.get("complete") is True
            and recorded_replay.get("canonical_assembly") is True
        ),
        "zero_failures_retries_replacements": bool(
            recorded_campaign.get("infrastructure_failures") == 0
            and recorded_replay.get("infrastructure_failures") == 0
            and summary.get("retries") == 0
            and summary.get("replacement_roots") == 0
            and recorded_campaign.get("retries") == 0
            and recorded_replay.get("retries") == 0
            and recorded_campaign.get("replacement_roots") == 0
            and recorded_replay.get("replacement_roots") == 0
            and campaign["terminal_failure_files"] == 0
            and replay["terminal_failure_files"] == 0
        ),
        "fresh_execution_no_checkpoint_reuse": bool(
            recorded_campaign.get("completed_shards_reused") == 0
            and recorded_campaign.get("new_shards_written") == 20
            and recorded_replay.get("completed_shards_reused") == 0
            and recorded_replay.get("new_shards_written") == 10
        ),
        "spawn_module_execution": bool(
            recorded_campaign.get("process_start_method") == "spawn"
            and recorded_replay.get("process_start_method") == "spawn"
            and recorded_campaign.get("workers") == recorded_replay.get("workers") == 8
        ),
        "frozen_counts": bool(
            pilot.pilot_blocks == 20
            and pilot.pilot_episodes == 40
            and pilot.replay_blocks == 10
            and pilot.replay_episodes == 20
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "campaign": campaign,
        "replay": replay,
        "execution_summary_sha256": _sha(root / RESULT / "execution-summary.json"),
    }


def _case_rows(rows: list[dict[str, Any]], case_id: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("case_id") == case_id]


def _activation_gates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checks = {
        "primary_bias": all(
            row["primary_fault_active_packets"] == 30
            and row["monitor_fault_active_packets"] == 0
            and row["primary_estimator_fault"]
            and not row["monitor_estimator_fault"]
            and not row["shared_cause_fault"]
            for row in _case_rows(rows, "T03_primary_navigation_bias")
        ),
        "primary_dropout": all(
            row["primary_fault_active_packets"] == 6
            and row["primary_disposition_counts"].get("dropout") == 6
            and row["monitor_fault_active_packets"] == 0
            for row in _case_rows(rows, "T04_primary_navigation_dropout")
        ),
        "monitor_bias": all(
            row["primary_fault_active_packets"] == 0
            and row["monitor_fault_active_packets"] == 30
            and not row["primary_estimator_fault"]
            and row["monitor_estimator_fault"]
            for row in _case_rows(rows, "T05_monitor_navigation_bias")
        ),
        "monitor_logic": all(
            row["monitor_logic_fault"]
            and (
                row["monitor_logic_active_commands"] == 6
                if row["configuration_id"] == "independent_monitor_gate"
                else row["monitor_logic_active_commands"] == 0
            )
            for row in _case_rows(rows, "T06_monitor_logic_false_trip")
        ),
        "shared_navigation": all(
            row["primary_fault_active_packets"] == 30
            and row["monitor_fault_active_packets"] == 30
            and row["shared_cause_fault"]
            and not row["primary_estimator_fault"]
            and not row["monitor_estimator_fault"]
            for row in _case_rows(rows, "T07_shared_navigation_bias")
        ),
        "actuation": all(
            row["actuation_degradation_scheduled"]
            and row["actuation_degradation_active_commands"] == 60
            and not row["disturbance_scheduled"]
            for row in _case_rows(rows, "T08_actuation_degradation")
        ),
        "disturbance": all(
            row["disturbance_scheduled"]
            and row["disturbance_active_substeps"] == 240
            and not row["actuation_degradation_scheduled"]
            for row in _case_rows(rows, "T09_disturbance_burst")
        ),
        "unaffected_channels_inactive": all(
            (
                row["monitor_fault_active_packets"] == 0
                if row["case_id"]
                in {"T03_primary_navigation_bias", "T04_primary_navigation_dropout"}
                else True
            )
            and (
                row["primary_fault_active_packets"] == 0
                if row["case_id"] == "T05_monitor_navigation_bias"
                else True
            )
            and (
                row["primary_fault_active_packets"] == 0
                and row["monitor_fault_active_packets"] == 0
                if row["case_id"]
                in {
                    "T00_nominal_transfer",
                    "T01_truth_model_mismatch_stress",
                    "T02_truth_keep_out_crossing_fixture",
                    "T06_monitor_logic_false_trip",
                    "T08_actuation_degradation",
                    "T09_disturbance_burst",
                }
                else True
            )
            for row in rows
        ),
    }
    expected_nonempty = all(
        len(_case_rows(rows, case_id)) == 4
        for case_id in (
            "T03_primary_navigation_bias",
            "T04_primary_navigation_dropout",
            "T05_monitor_navigation_bias",
            "T06_monitor_logic_false_trip",
            "T07_shared_navigation_bias",
            "T08_actuation_degradation",
            "T09_disturbance_burst",
        )
    )
    return {"passed": expected_nonempty and all(checks.values()), "checks": checks}


def _descriptive_summary(
    rows: list[dict[str, Any]],
    cases: tuple[TransferCase, ...],
    pilot: TransferPilotConfig,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for case in cases:
        summary[case.id] = {}
        for configuration in pilot.configuration_ids:
            selected = [
                row
                for row in rows
                if row["case_id"] == case.id and row["configuration_id"] == configuration
            ]
            summary[case.id][configuration] = {
                "episodes": len(selected),
                "event_counts": {
                    "collision": sum(bool(row["physical_collision"]) for row in selected),
                    "keep_out_entry": sum(
                        bool(row["physical_keep_out_entry"]) for row in selected
                    ),
                    "corridor_departure": sum(
                        bool(row["physical_corridor_departure"]) for row in selected
                    ),
                    "hold_acquired": sum(bool(row["hold_acquired"]) for row in selected),
                },
                "minimum_separation_m": min(
                    float(row["minimum_separation_m"]) for row in selected
                ),
                "maximum_hcw_position_residual_m": max(
                    float(row["maximum_hcw_position_residual_m"]) for row in selected
                ),
                "maximum_hcw_velocity_residual_mps": max(
                    float(row["maximum_hcw_velocity_residual_mps"]) for row in selected
                ),
                "fault_activation_totals": {
                    "primary_packets": sum(
                        int(row["primary_fault_active_packets"]) for row in selected
                    ),
                    "monitor_packets": sum(
                        int(row["monitor_fault_active_packets"]) for row in selected
                    ),
                    "monitor_logic_commands": sum(
                        int(row["monitor_logic_active_commands"]) for row in selected
                    ),
                    "actuation_commands": sum(
                        int(row["actuation_degradation_active_commands"])
                        for row in selected
                    ),
                    "disturbance_substeps": sum(
                        int(row["disturbance_active_substeps"]) for row in selected
                    ),
                },
            }
    return summary


def frozen_gate_evaluation(
    root: Path,
    identity: dict[str, Any],
    seeds: dict[str, Any],
    execution: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    pilot, cases, _, _, _ = _load_inputs(root)
    _, rows = _jsonl(root / RESULT / "campaign/pilot-episodes.jsonl")
    frozen_gates = _json(root / DESIGN_DIRECTORY / "gates.json")
    cells = validate_complete_cells(rows, pilot, cases)
    expected_roots = {
        f"experiment005:54:{case.case_code:03d}:{replicate:04d}"
        for case in cases
        for replicate in range(pilot.pilot_roots_per_case)
    }
    observed_roots = {str(row.get("root_seed_id")) for row in rows}
    case_map = {case.id: case for case in cases}
    scenario_map = {
        (scenario.case_id, scenario.replicate): scenario
        for scenario in _load_inputs(root)[2]
    }
    row_identity = all(
        row.get("case_id") in case_map
        and type(row.get("replicate")) is int
        and (row["case_id"], row["replicate"]) in scenario_map
        and row.get("case_code") == case_map[row["case_id"]].case_code
        and row.get("root_seed_id")
        == f"experiment005:54:{case_map[row['case_id']].case_code:03d}:{row['replicate']:04d}"
        and row.get("design_freeze_id") == AMENDMENT_FREEZE_ID
        and row.get("scenario_hash")
        == scenario_map[(row["case_id"], row["replicate"])].scenario_hash
        and row.get("stream_hashes")
        == scenario_map[(row["case_id"], row["replicate"])].stream_hashes
        and row.get("study_phase") == "design_validation_pilot"
        and type(row.get("run_order")) is int
        and 1 <= row["run_order"] <= 2
        and row.get("configuration_id")
        == scenario_map[(row["case_id"], row["replicate"])].configuration_run_order[
            row["run_order"] - 1
        ]
        for row in rows
    )
    numerical = all(
        row.get("attempt_status") == "valid"
        and row.get("infrastructure_failure") is False
        and row.get("nonlinear_truth_numerical_valid") is True
        and len(row.get("final_truth_relative_state", [])) == 6
        and all(_finite(value) for value in row.get("final_truth_relative_state", []))
        and _finite(row.get("maximum_hcw_position_residual_m"))
        and _finite(row.get("maximum_hcw_velocity_residual_mps"))
        for row in rows
    )
    covariance = all(
        _finite(row.get("minimum_covariance_eigenvalue"))
        and float(row["minimum_covariance_eigenvalue"]) >= -1e-12
        and _finite(row.get("maximum_covariance_trace"))
        and float(row["maximum_covariance_trace"]) < 1_000_000.0
        for row in rows
    )
    truth_event = _case_rows(rows, "T02_truth_keep_out_crossing_fixture")
    mismatch = _case_rows(rows, "T01_truth_model_mismatch_stress")
    information = information_boundary()
    analysis_boundary = frozen_gates["gates"]["analysis"]
    checks = {
        "foundation_and_freeze_identity": {"passed": identity["passed"]},
        "complete_cells": {**cells, "passed": bool(cells["passed"] and len(rows) == 40)},
        "root_identity": {
            "passed": bool(
                observed_roots == expected_roots
                and row_identity
                and seeds["historical_root_overlap"] == 0
                and seeds["partition_52_scenario_hash_overlap"] == 0
            ),
            "unique_roots": len(observed_roots),
            "episode_seed_and_run_order_binding": row_identity,
            "historical_overlap": seeds["historical_root_overlap"],
            "partition_52_scenario_hash_overlap": seeds[
                "partition_52_scenario_hash_overlap"
            ],
        },
        "nonlinear_truth_numerical_validity": {"passed": numerical},
        "estimator_covariance": {
            "passed": covariance,
            "minimum_observed_eigenvalue": min(
                float(row["minimum_covariance_eigenvalue"]) for row in rows
            ),
            "maximum_observed_trace": max(float(row["maximum_covariance_trace"]) for row in rows),
            "minimum_allowed_eigenvalue": -1e-12,
            "maximum_trace_exclusive_upper_bound": 1_000_000.0,
        },
        "truth_event_geometry": {
            "passed": bool(
                len(truth_event) == 4
                and all(
                    row["physical_collision"] is False
                    and row["physical_keep_out_entry"] is True
                    for row in truth_event
                )
            ),
            "episodes": len(truth_event),
            "collision_count": sum(bool(row["physical_collision"]) for row in truth_event),
            "keep_out_entry_count": sum(
                bool(row["physical_keep_out_entry"]) for row in truth_event
            ),
        },
        "model_mismatch_observability": {
            "passed": bool(
                len(mismatch) == 4
                and all(
                    row["model_mismatch_observations"] == 120
                    and _finite(row["maximum_hcw_position_residual_m"])
                    and _finite(row["maximum_hcw_velocity_residual_mps"])
                    and (
                        float(row["maximum_hcw_position_residual_m"]) > 0.0
                        or float(row["maximum_hcw_velocity_residual_mps"]) > 0.0
                    )
                    for row in mismatch
                )
            ),
            "episodes": len(mismatch),
            "observations_per_episode": sorted(
                {int(row["model_mismatch_observations"]) for row in mismatch}
            ),
            "maximum_position_residual_m": max(
                float(row["maximum_hcw_position_residual_m"]) for row in mismatch
            ),
            "maximum_velocity_residual_mps": max(
                float(row["maximum_hcw_velocity_residual_mps"]) for row in mismatch
            ),
            "absolute_favorable_or_unfavorable_threshold": None,
        },
        "fault_and_domain_activation": _activation_gates(rows),
        "information_boundary": information,
        "infrastructure": {
            "passed": execution["checks"]["zero_failures_retries_replacements"],
            "infrastructure_failures": 0,
            "retries": 0,
            "replacement_roots": 0,
        },
        "deterministic_replay": {
            "passed": execution["checks"]["replay_byte_equivalent"],
            "blocks": execution["replay"]["blocks"],
            "episodes": execution["replay"]["episodes"],
            "replay_sha256": execution["replay"]["output_sha256"],
        },
        "descriptive_analysis_boundary": {
            "passed": bool(
                analysis_boundary.get("mode") == "descriptive_mechanistic_gate_only"
                and analysis_boundary.get("p_values_allowed") is False
                and analysis_boundary.get("confidence_intervals_for_architecture_effects_allowed")
                is False
                and analysis_boundary.get("superiority_or_noninferiority_tests_allowed") is False
                and analysis_boundary.get("hazard_rate_claims_allowed") is False
                and analysis_boundary.get("architecture_effect_claims_allowed") is False
                and analysis_boundary.get("architecture_ranking_allowed") is False
                and analysis_boundary.get(
                    "model_mismatch_sign_interpreted_as_favorable_or_unfavorable"
                )
                is False
            )
        },
        "partition_53_untouched": {
            "passed": identity["partition_53"]["passed"] is True
        },
    }
    passed = all(bool(check.get("passed")) for check in checks.values())
    qc = {
        "schema_version": SCHEMA_VERSION,
        "phase": "noninferential_design_validation_pilot",
        "gate_policy": "conjunctive_fail_closed",
        "overall_passed": passed,
        "checks": checks,
    }
    analysis = {
        "schema_version": SCHEMA_VERSION,
        "phase": "noninferential_design_validation_pilot",
        "analysis_mode": "descriptive_mechanistic_gate_only",
        "scientific_hypothesis_tested": False,
        "architecture_effect_estimated": False,
        "p_values_computed": False,
        "architecture_confidence_intervals_computed": False,
        "superiority_or_noninferiority_tested": False,
        "hazard_rate_claimed": False,
        "architecture_ranking_performed": False,
        "descriptive_mechanistic_summary": _descriptive_summary(rows, cases, pilot),
        "aggregate_observations": {
            "episodes": len(rows),
            "collision_count": sum(bool(row["physical_collision"]) for row in rows),
            "keep_out_entry_count": sum(bool(row["physical_keep_out_entry"]) for row in rows),
            "corridor_departure_count": sum(
                bool(row["physical_corridor_departure"]) for row in rows
            ),
            "hold_acquired_count": sum(bool(row["hold_acquired"]) for row in rows),
        },
        "progression": {
            "passed": passed,
            "decision": (
                "pilot_design_gates_passed"
                if passed
                else "pilot_design_gates_failed_do_not_progress"
            ),
            "basis": "frozen_conjunctive_design_validation_gates_only",
            "descriptive_outcomes_used_to_change_progression": False,
            "confirmatory_partition_53_campaign_authorized": False,
            "confirmatory_design_freeze_scientifically_justified": passed,
            "partition_53_materialized_or_executed": False,
            "smallest_next_task": NEXT_TASK if passed else None,
        },
        "limitations": [
            "The pilot was selected for mechanics coverage rather than statistical power.",
            (
                "Event counts are descriptive and do not estimate operational rates or "
                "architecture effects."
            ),
            (
                "Every episode recorded corridor departure; corridor outcome was not a frozen "
                "favorable or unfavorable progression gate."
            ),
            "The result does not authorize partition-53 materialization or execution.",
        ],
    }
    return analysis, qc


def collect_evidence(root: Path) -> dict[str, Any]:
    identity = frozen_identity(root)
    seeds = seed_evidence(root)
    execution = execution_evidence(root)
    if not all(item["passed"] for item in (identity, seeds, execution)):
        return {
            "passed": False,
            "identity": identity,
            "seeds": seeds,
            "execution": execution,
        }
    analysis, qc = frozen_gate_evaluation(root, identity, seeds, execution)
    return {
        "passed": qc["overall_passed"],
        "identity": identity,
        "seeds": seeds,
        "execution": execution,
        "analysis": analysis,
        "qc": qc,
    }


def _phase_validation(root: Path) -> dict[str, Any]:
    commands = [
        _run(root, ["uv", "sync", "--frozen", "--extra", "dev"], "dependency_lock"),
        _run(root, ["uv", "run", "ruff", "check", "."], "ruff"),
        _run(root, ["uv", "run", "pytest", "-q"], "phase_appropriate_repository_tests"),
        _run(
            root,
            ["uv", "run", "python", "-m", "compileall", "-q", "src", "tests"],
            "compileall",
        ),
        _run(root, ["uv", "run", "kri-space-lab", "verify-gate"], "stable_gate"),
        _run(root, ["git", "diff", "--check"], "diff_whitespace"),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": "post_partition_54_pilot_closeout",
        "scientific_cells_executed": 0,
        "commands": commands,
        "passed": all(command["passed"] for command in commands),
    }


def _report(analysis: dict[str, Any], qc: dict[str, Any]) -> str:
    covariance = qc["checks"]["estimator_covariance"]
    mismatch = qc["checks"]["model_mismatch_observability"]
    return f"""# Experiment 005 partition-54 transfer-pilot closeout

## Decision

**All prospectively frozen design-validation gates passed.** Partition 54 contains 20 complete
paired blocks and 40 episodes. The 10-block, 20-episode replay is byte-identical to the frozen
replicate-0 subset. No infrastructure failure, retry, replacement root, extension, or partition-52
reuse was observed. Partition 53 remains untouched.

This is a noninferential mechanics result. No architecture effect, superiority, noninferiority,
hazard rate, confidence interval for an architecture effect, ranking, or operational event rate was
estimated.

## Frozen gate results

- Seed and cell identity: 20/20 unique partition-54 roots and 40/40 canonical episode rows; no
  historical root overlap and no partition-52 scenario-hash reuse.
- Checkpoints: 20/20 campaign shards and 10/10 replay shards passed campaign, content-hash,
  canonical-order, and assembled-output checks.
- Nonlinear truth and covariance: every episode was finite and valid; minimum covariance eigenvalue
  was `{covariance['minimum_observed_eigenvalue']:.6g}` and maximum covariance trace was
  `{covariance['maximum_observed_trace']:.6g}` against frozen limits `-1e-12` and `<1e6`.
- Truth-event fixture: keep-out entry occurred in 4/4 episodes and collision in 0/4.
- Model-mismatch fixture: every episode had 120 finite observations and a positive residual;
  maximum position and velocity residuals were `{mismatch['maximum_position_residual_m']:.6g} m`
  and `{mismatch['maximum_velocity_residual_mps']:.6g} m/s`. No favorable or unfavorable absolute
  mismatch threshold was defined.
- Primary, monitor, monitor-logic, shared-navigation, actuation, and disturbance activation gates
  all passed with unaffected channels remaining inactive.
- Frozen source, design, information-boundary, runtime, replay, and historical partition-52 evidence
  checks passed.

## Descriptive observations

Across all 40 episodes there were
{analysis['aggregate_observations']['collision_count']} collisions,
{analysis['aggregate_observations']['keep_out_entry_count']} keep-out entries,
{analysis['aggregate_observations']['corridor_departure_count']} corridor departures, and
{analysis['aggregate_observations']['hold_acquired_count']} hold acquisitions. The nominal case
acquired hold in 4/4 episodes with no collision or keep-out entry. The actuation-degradation case
entered keep-out in 4/4 episodes with no collision and no hold. Every episode recorded corridor
departure. These are descriptive observations, not architecture comparisons or additional
progression criteria.

## Progression

The frozen progression decision is `pilot_design_gates_passed`. A separate prospective
partition-53 confirmatory-design freeze is scientifically justified solely because every frozen
conjunctive design-validation gate passed. This closeout does not authorize a confirmatory campaign
and does not create, materialize, or execute partition 53.

The smallest next task is to {NEXT_TASK}.
"""


def _artifact_entries(root: Path) -> list[dict[str, Any]]:
    paths = [
        *sorted((root / SEEDS).rglob("*")),
        *sorted((root / RESULT).rglob("*")),
        root / DOC_PATH,
        root / ROADMAP_PATH,
        root / SOURCE_PATH,
        root / TEST_PATH,
        root / CONFTEST_PATH,
    ]
    excluded = {root / MANIFEST_PATH, root / CHECKSUMS_PATH}
    files = sorted(
        {path for path in paths if path.is_file() and path not in excluded},
        key=lambda path: path.relative_to(root).as_posix(),
    )
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha(path),
        }
        for path in files
    ]


def package(root: Path) -> dict[str, Any]:
    present = [path.as_posix() for path in CLOSEOUT_ARTIFACTS if (root / path).exists()]
    if present:
        raise RuntimeError(f"refusing to overwrite closeout artifact: {present[0]}")
    evidence = collect_evidence(root)
    if not evidence["passed"]:
        raise RuntimeError("partition-54 execution or frozen gate validation failed")

    _write_json(root / ANALYSIS_PATH, evidence["analysis"])
    _write_json(root / QC_PATH, evidence["qc"])
    design_integrity = {
        "schema_version": SCHEMA_VERSION,
        "phase": "post_partition_54_execution_design_integrity",
        "passed": True,
        "frozen_identity": evidence["identity"],
        "materialized_seed_evidence": evidence["seeds"],
        "partition_52": "infrastructure_invalid_permanently_retired",
        "partition_54": "sole_valid_replacement_design_validation_pilot",
        "partition_53": "reserved_untouched_unmaterialized_and_unexecuted",
    }
    _write_json(root / DESIGN_INTEGRITY_PATH, design_integrity)
    reproducibility = {
        "schema_version": SCHEMA_VERSION,
        "passed": evidence["execution"]["checks"]["replay_byte_equivalent"],
        "selection": "replicate 0 in every frozen case",
        "blocks": evidence["execution"]["replay"]["blocks"],
        "episodes": evidence["execution"]["replay"]["episodes"],
        "original_subset_sha256": REPLAY_ROWS_SHA256,
        "replay_sha256": evidence["execution"]["replay"]["output_sha256"],
        "runtime_identity": evidence["identity"]["runtime_identity"],
    }
    _write_json(root / REPRODUCIBILITY_PATH, reproducibility)
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "authorization": "one frozen replacement design-validation pilot on partition 54",
        "partition_code": 54,
        "retired_partition_code": 52,
        "complete_blocks": 20,
        "episode_rows": 40,
        "workers": 8,
        "campaign_invocations_recorded": 1,
        "replay_invocations_recorded": 1,
        "completed_campaign_shards_reused": 0,
        "completed_replay_shards_reused": 0,
        "infrastructure_failures_recorded": 0,
        "retries_recorded": 0,
        "replacement_roots_recorded": 0,
        "extensions_recorded": 0,
        "write_once_evidence": {
            "seed_manifest_sha256": SEED_MANIFEST_SHA256,
            "campaign_rows_sha256": CAMPAIGN_ROWS_SHA256,
            "replay_rows_sha256": REPLAY_ROWS_SHA256,
        },
    }
    _write_json(root / LEDGER_PATH, ledger)
    _write_text(root / REPORT_PATH, _report(evidence["analysis"], evidence["qc"]))

    phase = _phase_validation(root)
    _write_json(root / PHASE_PATH, phase)
    if not phase["passed"]:
        raise RuntimeError("phase validation failed")

    verification = {
        "schema_version": SCHEMA_VERSION,
        "phase": "post_partition_54_result_verification",
        "passed": True,
        "decision": "pilot_design_gates_passed",
        "counts": {
            "root_rows": 20,
            "complete_blocks": 20,
            "episode_rows": 40,
            "replay_blocks": 10,
            "replay_episode_rows": 20,
        },
        "digests": {
            "seed_manifest_sha256": SEED_MANIFEST_SHA256,
            "campaign_rows_sha256": CAMPAIGN_ROWS_SHA256,
            "replay_rows_sha256": REPLAY_ROWS_SHA256,
        },
        "all_frozen_gates": evidence["qc"]["overall_passed"],
        "frozen_identity": evidence["identity"]["passed"],
        "seed_integrity": evidence["seeds"]["passed"],
        "checkpoint_integrity": evidence["execution"]["passed"],
        "partition_52_invalid_attempt_preserved": evidence["identity"]["checks"][
            "invalid_partition_52_preserved"
        ],
        "partition_53_untouched": evidence["identity"]["checks"][
            "partition_53_untouched"
        ],
        "confirmatory_design_freeze_scientifically_justified": True,
        "confirmatory_partition_53_campaign_authorized": False,
        "phase_validation": True,
    }
    _write_json(root / VERIFICATION_PATH, verification)

    scan = publication_privacy(root)
    _write_json(root / RELEASE_SCAN_PATH, scan)
    if not scan["passed"]:
        raise RuntimeError("publication and secret scan failed")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "phase": "completed_partition_54_design_validation_pilot",
        "decision": "pilot_design_gates_passed",
        "amendment_freeze_id": AMENDMENT_FREEZE_ID,
        "partition_code": 54,
        "retired_partition_code": 52,
        "future_confirmatory_partition_code": 53,
        "counts": verification["counts"],
        "artifacts": _artifact_entries(root),
        "embedded_hash_exclusions": [
            {
                "path": MANIFEST_PATH.as_posix(),
                "reason": "self-referential; covered by checksums",
            },
            {
                "path": CHECKSUMS_PATH.as_posix(),
                "reason": "checksum file cannot hash itself",
            },
        ],
    }
    _write_json(root / MANIFEST_PATH, manifest)
    checksum_paths = [Path(item["path"]) for item in manifest["artifacts"]] + [MANIFEST_PATH]
    _write_text(
        root / CHECKSUMS_PATH,
        "".join(f"{_sha(root / path)}  {path.as_posix()}\n" for path in checksum_paths),
    )
    verified = verify_package(root)
    if not verified["passed"]:
        raise RuntimeError(f"package verification failed: {verified['errors_preview']}")
    return verified


def verify_package(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        evidence = collect_evidence(root)
        missing = [path.as_posix() for path in CLOSEOUT_ARTIFACTS if not (root / path).is_file()]
        if missing:
            errors.extend(f"missing:{path}" for path in missing)
        if not evidence.get("passed"):
            errors.append("evidence")
        if not missing:
            analysis = _json(root / ANALYSIS_PATH)
            qc = _json(root / QC_PATH)
            phase = _json(root / PHASE_PATH)
            verification = _json(root / VERIFICATION_PATH)
            release = _json(root / RELEASE_SCAN_PATH)
            manifest = _json(root / MANIFEST_PATH)
            if analysis.get("progression", {}).get("decision") != "pilot_design_gates_passed":
                errors.append("analysis_decision")
            if qc.get("overall_passed") is not True:
                errors.append("qc")
            if phase.get("passed") is not True:
                errors.append("phase_validation")
            if verification.get("passed") is not True:
                errors.append("result_verification")
            if release.get("passed") is not True:
                errors.append("release_scan")
            for item in manifest.get("artifacts", []):
                path = root / item["path"]
                if (
                    not path.is_file()
                    or path.stat().st_size != item["bytes"]
                    or _sha(path) != item["sha256"]
                ):
                    errors.append(f"manifest:{item['path']}")
            for line in (root / CHECKSUMS_PATH).read_text(encoding="utf-8").splitlines():
                expected, relative = line.split("  ", 1)
                path = root / relative
                if not path.is_file() or _sha(path) != expected:
                    errors.append(f"checksum:{relative}")
            scan = publication_privacy(root)
            if not scan["passed"]:
                errors.append("publication_privacy")
    except (OSError, KeyError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"verification_exception:{type(exc).__name__}")
        evidence = {}
        missing = []
    transient = [
        path.relative_to(root).as_posix()
        for path in (root / RESULT).rglob("*")
        if path.is_file() and (path.name.endswith(".tmp") or path.name == ".campaign.lock")
    ]
    if transient:
        errors.append("transient_execution_files")
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": not errors,
        "decision": "pilot_design_gates_passed" if not errors else "verification_failed",
        "errors_preview": errors[:30],
        "missing": missing,
        "transient_execution_files": transient,
        "evidence_passed": evidence.get("passed", False),
        "confirmatory_design_freeze_scientifically_justified": not errors,
        "confirmatory_partition_53_campaign_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package or verify the completed Experiment 005 partition-54 pilot"
    )
    parser.add_argument("command", choices=("collect", "package", "verify"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "collect":
        result = collect_evidence(root)
    elif args.command == "package":
        result = package(root)
    else:
        result = verify_package(root)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if not result.get("passed", True):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
