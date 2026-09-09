"""Recompute only the frozen pure analysis on recovered, verified E005 records.

No simulator, runner, seed generator, or workflow module is imported. The default
check writes nothing. An explicit output path creates newly dated audit metadata.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import platform
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verify_evidence_supplement import (
    SUPPLEMENT,
    read_original_members,
    read_regular,
    sha256,
    strict_json,
)

SOURCE_COMMIT = "d841a016361974734bd28b27ff39e9df0e2cbaed"
FREEZE_ID = "1acd0af2246fb5ba1e86da0302f6b7f3cda57e59018068186375507000d264ca"
CASES = ("T03_primary_navigation_bias", "T04_primary_navigation_dropout")
CONFIGURATIONS = ("primary_reference", "independent_monitor_gate")
SEEDS = "experiments/005-confirmatory/seeds/"
RESULTS = "results/experiment-005-confirmatory/"
SOURCE = "src/kri_space_autonomy/experiment_005_confirmatory/"
STREAMS = {
    "actuation",
    "cell_order",
    "challenge_parameters",
    "initial_truth_state",
    "mechanics_perturbation",
    "monitor_navigation",
    "primary_navigation",
}
BOOL_FIELDS = {
    "infrastructure_failure",
    "physical_collision",
    "physical_keep_out_entry",
    "physical_corridor_departure",
    "hold_acquired",
    "primary_estimator_fault",
    "monitor_estimator_fault",
    "monitor_logic_fault",
    "shared_cause_fault",
    "actuation_degradation_scheduled",
    "disturbance_scheduled",
    "nonlinear_truth_numerical_valid",
}
INT_FIELDS = {
    "case_code",
    "replicate",
    "run_order",
    "primary_fault_active_packets",
    "monitor_fault_active_packets",
    "monitor_logic_active_commands",
    "actuation_degradation_active_commands",
    "disturbance_active_substeps",
    "monitor_override_commands",
    "model_mismatch_observations",
}
NUMBER_FIELDS = {
    "minimum_separation_m",
    "maximum_admissible_position_excess_m",
    "maximum_abs_crosstrack_m",
    "maximum_contiguous_hold_dwell_s",
    "minimum_covariance_eigenvalue",
    "maximum_covariance_trace",
    "maximum_hcw_position_residual_m",
    "maximum_hcw_velocity_residual_mps",
}
STRING_FIELDS = {
    "schema_version",
    "study_phase",
    "design_freeze_id",
    "case_id",
    "domain",
    "root_seed_id",
    "configuration_id",
    "attempt_status",
    "scenario_hash",
    "controller_identity",
    "trace_digest",
}
COUNT_MAPS = {"monitor_reason_counts", "primary_disposition_counts", "monitor_disposition_counts"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def jsonl(raw: bytes) -> list[dict[str, Any]]:
    require(bool(raw) and raw.endswith(b"\n"), "nonempty newline-terminated JSONL required")
    rows = [strict_json(line) for line in raw.splitlines()]
    require(all(type(row) is dict for row in rows), "JSONL rows must be objects")
    return rows


def number(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(value)


def vector(value: Any, size: int) -> bool:
    return type(value) is list and len(value) == size and all(number(v) for v in value)


def digest(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def check_row_types(row: dict[str, Any]) -> None:
    fields = BOOL_FIELDS | INT_FIELDS | NUMBER_FIELDS | STRING_FIELDS | COUNT_MAPS
    require(
        set(row) == fields | {"stream_hashes", "final_truth_relative_state"},
        "unexpected or missing episode field",
    )
    require(all(type(row[k]) is bool for k in BOOL_FIELDS), "episode booleans must be booleans")
    require(
        all(type(row[k]) is int and row[k] >= 0 for k in INT_FIELDS),
        "episode counts must be nonnegative integers",
    )
    require(all(number(row[k]) for k in NUMBER_FIELDS), "episode numerical field invalid")
    require(all(type(row[k]) is str and row[k] for k in STRING_FIELDS), "episode text invalid")
    require(vector(row["final_truth_relative_state"], 6), "invalid relative-state vector")
    for name in COUNT_MAPS:
        value = row[name]
        require(
            type(value) is dict
            and all(type(k) is str and type(v) is int and v >= 0 for k, v in value.items()),
            "invalid diagnostic count map",
        )
    require(
        all(digest(row[k]) for k in ("design_freeze_id", "scenario_hash", "trace_digest")),
        "invalid episode digest",
    )
    check_streams(row["stream_hashes"])


def check_streams(value: Any) -> None:
    require(
        type(value) is dict and set(value) == STREAMS and all(digest(v) for v in value.values()),
        "invalid stream identities",
    )


def check_seed_types(seed: dict[str, Any]) -> None:
    bools = {"navigation_noise_enabled", "mechanics_noise_enabled", "monitor_logic_fault"}
    ints = {"partition_code", "replicate", "case_code", "challenge_code", "geometry_code"}
    strings = {
        "schema_version",
        "design_freeze_id",
        "case_id",
        "measurement_fault_channel",
        "measurement_fault_kind",
        "root_seed_id",
        "scenario_hash",
    }
    numbers = {
        "actuation_effectiveness",
        "covariance_factor",
        "horizon_s",
        "fault_onset_s",
        "fault_end_s",
    }
    vectors = {"initial_relative_state": 6, "additive_bias": 4, "disturbance_bias_mps2": 2}
    require(
        set(seed)
        == bools
        | ints
        | strings
        | numbers
        | set(vectors)
        | {"configuration_run_order", "stream_hashes", "fixture_command_mps2"},
        "unexpected or missing seed field",
    )
    require(all(type(seed[k]) is bool for k in bools), "seed booleans must be booleans")
    require(all(type(seed[k]) is int and seed[k] >= 0 for k in ints), "invalid seed integer")
    require(all(type(seed[k]) is str and seed[k] for k in strings), "invalid seed string")
    require(all(number(seed[k]) for k in numbers), "invalid seed number")
    require(
        all(
            vector(seed[k], v) or (k == "additive_bias" and seed[k] is None)
            for k, v in vectors.items()
        ),
        "invalid seed vector",
    )
    require(seed["fixture_command_mps2"] is None, "unexpected fixture command")
    order = seed["configuration_run_order"]
    require(
        type(order) is list and len(order) == 2 and set(order) == set(CONFIGURATIONS),
        "invalid paired order",
    )
    require(
        digest(seed["scenario_hash"]) and seed["design_freeze_id"] == FREEZE_ID,
        "seed freeze or scenario identity invalid",
    )
    check_streams(seed["stream_hashes"])


def validate_records(rows: list[dict[str, Any]], seeds: list[dict[str, Any]]) -> None:
    require(len(seeds) == 1068 and len(rows) == 2136, "incorrect campaign size")
    scheduled = {}
    for seed in seeds:
        check_seed_types(seed)
        case = seed["case_id"]
        require(case in CASES, "unexpected case")
        code = CASES.index(case) + 1
        require(seed["case_code"] == code and 0 <= seed["replicate"] < 534, "invalid allocation")
        expected_id = f"experiment005:53:{code:03d}:{seed['replicate']:04d}"
        require(
            seed["root_seed_id"] == expected_id and seed["partition_code"] == 53,
            "root or partition mismatch",
        )
        require(seed["horizon_s"] == 300.0, "horizon changed")
        require(expected_id not in scheduled, "duplicate scheduled root")
        scheduled[expected_id] = seed
    require(Counter(s["case_id"] for s in seeds) == dict.fromkeys(CASES, 534), "case counts differ")
    order_counts = Counter((s["case_id"], s["configuration_run_order"][0]) for s in seeds)
    require(
        all(order_counts[c, a] == 267 for c in CASES for a in CONFIGURATIONS),
        "paired run-order balance differs",
    )
    observed = set()
    for row in rows:
        check_row_types(row)
        key = row["root_seed_id"], row["configuration_id"]
        require(
            key not in observed and key[0] in scheduled and key[1] in CONFIGURATIONS,
            "duplicate or unscheduled row",
        )
        observed.add(key)
        seed = scheduled[key[0]]
        for field in (
            "case_id",
            "case_code",
            "replicate",
            "scenario_hash",
            "stream_hashes",
            "design_freeze_id",
            "schema_version",
        ):
            require(row[field] == seed[field], "episode/seed identity mismatch: " + field)
        require(
            row["run_order"] == seed["configuration_run_order"].index(key[1]) + 1,
            "episode run order differs",
        )
        require(
            row["study_phase"] == "confirmatory_nonlinear_truth_assurance", "episode phase differs"
        )
    require(len(observed) == 2 * len(scheduled), "incomplete paired membership")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Independent counting only, with strict booleans; also usable on tiny fixtures."""
    counts: dict[str, Any] = {}
    totals: dict[str, Any] = {}
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        for field in (
            "physical_collision",
            "physical_keep_out_entry",
            "physical_corridor_departure",
            "hold_acquired",
        ):
            require(type(row[field]) is bool, "outcome fields must be booleans")
        case, arm = row["case_id"], row["configuration_id"]
        require(arm in CONFIGURATIONS, "unknown configuration")
        pair = pairs.setdefault((case, row["root_seed_id"]), {})
        require(arm not in pair, "duplicate root/configuration")
        pair[arm] = row
        values = {
            "episodes": 1,
            "collision": int(row["physical_collision"]),
            "keep_out_entry": int(row["physical_keep_out_entry"]),
            "corridor_departure": int(row["physical_corridor_departure"]),
            "physical_adverse": int(
                any(
                    row[k]
                    for k in (
                        "physical_collision",
                        "physical_keep_out_entry",
                        "physical_corridor_departure",
                    )
                )
            ),
            "hold_acquired": int(row["hold_acquired"]),
        }
        by_case = counts.setdefault(case, {}).setdefault(arm, Counter())
        by_case.update(values)
        totals.setdefault(arm, Counter()).update(values)
    table = dict.fromkeys(
        ("both_safe", "reference_adverse_gate_safe", "gate_adverse_reference_safe", "both_adverse"),
        0,
    )
    harms = 0
    for pair in pairs.values():
        require(set(pair) == set(CONFIGURATIONS), "incomplete pair")
        reference, gate = (pair[a] for a in CONFIGURATIONS)
        adverse = tuple(
            any(
                r[k]
                for k in (
                    "physical_collision",
                    "physical_keep_out_entry",
                    "physical_corridor_departure",
                )
            )
            for r in (reference, gate)
        )
        key = {
            (False, False): "both_safe",
            (True, False): "reference_adverse_gate_safe",
            (False, True): "gate_adverse_reference_safe",
            (True, True): "both_adverse",
        }[adverse]
        table[key] += 1
        harms += int(reference["hold_acquired"] and not gate["hold_acquired"])
    return {
        "by_case": counts,
        "totals_by_configuration": totals,
        "paired_adverse_table": table,
        "paired_roots": len(pairs),
        "observed_gate_induced_hold_loss_pairs": harms,
    }


def check_checkpoints(members: dict[str, bytes], seeds: list[dict[str, Any]], profile: str) -> None:
    prefix = RESULTS + profile + "/"
    campaign = strict_json(members[prefix + "shards/campaign.json"])
    unsigned = {k: v for k, v in campaign.items() if k != "campaign_id"}
    require(campaign["campaign_id"] == sha256(canonical(unsigned)), "campaign identity mismatch")
    require(
        campaign["partition_code"] == 53 and campaign["cell_count"] == len(seeds),
        "checkpoint population differs",
    )
    schedule = []
    assembled = []
    for index, seed in enumerate(seeds):
        identity = {
            "cell_index": index,
            **{
                k: seed[k]
                for k in ("root_seed_id", "case_id", "scenario_hash", "configuration_run_order")
            },
        }
        identity["cell_sha256"] = sha256(canonical(identity))
        schedule.append(identity)
        shard = strict_json(members[prefix + f"shards/cell-{index:06d}.json"])
        body = {k: v for k, v in shard.items() if k != "shard_id"}
        require(shard["shard_id"] == sha256(canonical(body)), "shard identity mismatch")
        require(shard["campaign_id"] == campaign["campaign_id"], "foreign campaign shard")
        require(all(shard[k] == v for k, v in identity.items()), "shard schedule differs")
        require(shard["rows_sha256"] == sha256(canonical(shard["rows"])), "shard row hash differs")
        require(len(shard["rows"]) == 2, "incomplete shard")
        for order, row in enumerate(shard["rows"], 1):
            require(
                row["run_order"] == order
                and row["root_seed_id"] == seed["root_seed_id"]
                and row["configuration_id"] == seed["configuration_run_order"][order - 1],
                "shard row membership differs",
            )
            assembled.append(canonical(row) + b"\n")
    require(
        sha256(canonical(schedule)) == campaign["ordered_schedule_sha256"], "schedule hash differs"
    )
    require(
        b"".join(assembled) == members[prefix + "confirmatory-episodes.jsonl"],
        "assembled checkpoint bytes differ",
    )


def pinned(root: Path, relative: str) -> bytes:
    return subprocess.run(
        [
            "git",
            "--no-replace-objects",
            "-C",
            str(root),
            "cat-file",
            "blob",
            f"{SOURCE_COMMIT}:{relative}",
        ],
        check=True,
        capture_output=True,
        timeout=30,
        env=dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1"),
    ).stdout


def load_frozen(root: Path) -> tuple[Any, Any, dict[str, Any]]:
    """Load three reviewed frozen files under an isolated name, without package-root imports."""
    freeze_raw = pinned(root, "experiments/005-confirmatory/freeze-manifest.json")
    freeze = strict_json(freeze_raw)
    require(freeze["freeze_id"] == FREEZE_ID, "wrong frozen design")
    identities = {}
    for relative, expected in freeze["source_file_hashes"].items():
        observed = sha256(pinned(root, relative))
        require(observed == expected, "frozen source hash mismatch: " + relative)
        identities[relative] = observed
    name = "_sal_reconciliation_frozen"
    for suffix in ("", ".config", ".analysis"):
        relative = (
            SOURCE
            + ({"": "__init__", ".config": "config", ".analysis": "analysis"}[suffix])
            + ".py"
        )
        raw = read_regular(root, relative)
        require(raw == pinned(root, relative), "working pure-analysis source is not frozen")
        spec = importlib.util.spec_from_file_location(
            name + suffix,
            root / relative,
            submodule_search_locations=[str(root / SOURCE)] if not suffix else None,
        )
        require(spec is not None and spec.loader is not None, "module cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name + suffix] = module
        previous = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous
    config_module = sys.modules[name + ".config"]
    config_path = "experiments/005-confirmatory/config.json"
    require(read_regular(root, config_path) == pinned(root, config_path), "configuration changed")
    study = config_module.load_confirmatory_config(root / config_path)
    metadata = {
        "source_commit": SOURCE_COMMIT,
        "design_freeze_id": FREEZE_ID,
        "freeze_manifest_sha256": sha256(freeze_raw),
        "frozen_file_sha256": identities,
    }
    return sys.modules[name + ".analysis"], study, metadata


def initial_position_checks(
    seeds: list[dict[str, Any]], geometry: dict[str, Any]
) -> dict[str, Any]:
    """Algebra on stored initial positions only; no propagation or evaluator import."""
    lower, upper = geometry["approach_y_bounds_m"]
    outer, inner = geometry["approach_radial_halfwidth_m"]
    cx, cy = geometry["hold_center_m"]
    hx, hy = geometry["hold_position_halfwidth_m"]
    outside = dict.fromkeys(CASES, 0)
    for seed in seeds:
        x, y = seed["initial_relative_state"][:2]
        clipped = min(upper, max(lower, y))
        width = outer + (clipped - lower) / (upper - lower) * (inner - outer)
        approach = max(lower - y, y - upper, abs(x) - width)
        hold = (math.hypot((x - cx) / hx, (y - cy) / hy) - 1.0) * min(hx, hy)
        outside[seed["case_id"]] += int(min(approach, hold) > 1e-9)
    return {
        "stored_initial_positions_checked": len(seeds),
        "outside_by_case": outside,
        "method": (
            "closed-corridor/hold-union algebra on stored positions; no trajectory generation"
        ),
    }


def recompute(root: Path) -> dict[str, Any]:
    members = read_original_members(root)
    rows = jsonl(members[RESULTS + "campaign/confirmatory-episodes.jsonl"])
    seeds = jsonl(members[SEEDS + "confirmatory.jsonl"])
    replay_raw = members[RESULTS + "replay/confirmatory-episodes.jsonl"]
    replay = jsonl(replay_raw)
    validate_records(rows, seeds)
    analysis, study, source = load_frozen(root)
    index = strict_json(members[SEEDS + "index.json"])
    readiness_raw = pinned(root, "experiments/005-confirmatory/readiness.json")
    readiness = strict_json(readiness_raw)
    execution = strict_json(members[RESULTS + "execution-summary.json"])
    selection = strict_json(members[SEEDS + "replay-subset.json"])
    require(
        index["design_freeze_id"] == execution["design_freeze_id"] == FREEZE_ID,
        "execution/seed freeze identity differs",
    )
    require(
        index["design_readiness_id"]
        == execution["design_readiness_id"]
        == readiness["readiness_id"],
        "execution/seed readiness differs",
    )
    for field, file in (
        ("manifest_sha256", "confirmatory.jsonl"),
        ("replay_subset_sha256", "replay-subset.json"),
    ):
        require(index[field] == sha256(members[SEEDS + file]), "seed index hash differs")
    require(
        index["seed_contract_sha256"]
        == sha256(pinned(root, "experiments/005-confirmatory/seed-contract.json")),
        "seed contract differs",
    )
    selected = [s for s in seeds if s["replicate"] < 8]
    require(
        selection["root_seed_ids"] == [s["root_seed_id"] for s in selected] and len(selected) == 16,
        "stored replay selection differs from frozen rule",
    )
    selected_ids = set(selection["root_seed_ids"])
    expected_replay = b"".join(
        line + b"\n"
        for line in members[RESULTS + "campaign/confirmatory-episodes.jsonl"].splitlines()
        if strict_json(line)["root_seed_id"] in selected_ids
    )
    require(len(replay) == 32 and expected_replay == replay_raw, "stored replay records differ")
    for profile, population in (("campaign", seeds), ("replay", selected)):
        check_checkpoints(members, population, profile)
        require(
            execution[profile]["output_sha256"]
            == sha256(members[RESULTS + profile + "/confirmatory-episodes.jsonl"]),
            "execution-summary data digest differs",
        )
    result = analysis.analyze_confirmatory_rows(rows, seeds, study)
    independent = summarize(rows)
    for case in CASES:
        for arm in CONFIGURATIONS:
            frozen_counts = result["secondary_descriptive_summary"][case][arm]
            require(
                all(frozen_counts[k] == v for k, v in independent["by_case"][case][arm].items()),
                "independent absolute counts differ from frozen output",
            )
    h1 = result["primary_gatekeeping"]["H1_physical_safety"]
    for key in ("reference_adverse_gate_safe", "gate_adverse_reference_safe"):
        require(h1[key] == independent["paired_adverse_table"][key], "paired counts differ")
    require(
        result["validity"] == execution["complete_cell_validation"],
        "recomputed fixed-cell checks differ from stored execution summary",
    )
    diagnostics = {}
    for case in CASES:
        diagnostics[case] = {}
        for arm in CONFIGURATIONS:
            group = [r for r in rows if r["case_id"] == case and r["configuration_id"] == arm]
            keys = (
                "maximum_admissible_position_excess_m",
                "minimum_separation_m",
                "maximum_contiguous_hold_dwell_s",
                "maximum_abs_crosstrack_m",
                "monitor_override_commands",
            )
            diagnostics[case][arm] = {
                k: {"min": min(r[k] for r in group), "max": max(r[k] for r in group)} for k in keys
            }
    return {
        "source": source,
        "readiness_sha256": sha256(readiness_raw),
        "design_readiness_id": readiness["readiness_id"],
        "inputs_sha256": {
            name: sha256(members[name])
            for name in (
                SEEDS + "confirmatory.jsonl",
                SEEDS + "index.json",
                SEEDS + "replay-subset.json",
                RESULTS + "campaign/confirmatory-episodes.jsonl",
                RESULTS + "replay/confirmatory-episodes.jsonl",
                RESULTS + "execution-summary.json",
            )
        },
        "strict_type_and_membership_checks_passed": True,
        "stored_checkpoint_and_replay_comparison_passed": True,
        "stored_replay_blocks": 16,
        "stored_replay_rows": 32,
        "frozen_analysis_result": result,
        "independent_counts": independent,
        "recorded_diagnostic_ranges": diagnostics,
        "initial_position_checks": initial_position_checks(
            seeds, strict_json(pinned(root, "experiments/005/config.json"))
        ),
        "static_review_source_sha256": {
            path: sha256(pinned(root, path))
            for path in (
                "src/kri_space_autonomy/experiment_005/geometry.py",
                "src/kri_space_autonomy/experiment_005/dynamics.py",
                "src/kri_space_autonomy/experiment_005_transfer_pilot/runner.py",
                "src/kri_space_autonomy/experiment_005_confirmatory/runner.py",
                "experiments/004/config.json",
                "experiments/005/config.json",
            )
        },
        "original_execution_status": execution["status"],
        "method_script_sha256": sha256(Path(__file__).read_bytes()),
    }


def environment() -> dict[str, str]:
    import numpy
    import scipy

    require(
        (platform.python_version(), numpy.__version__, scipy.__version__)
        == ("3.11.16", "2.4.6", "1.17.0"),
        "recorded numerical runtime is required",
    )
    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "implementation": platform.python_implementation(),
        "os": platform.system(),
        "architecture": platform.machine(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output", type=Path, help="Create new audit JSON; refuses an existing file"
    )
    args = parser.parse_args()
    try:
        runtime = environment()
        computation = recompute(args.root)
        if args.output:
            report = {
                "record_kind": "post-release recomputation, not recovered original final analysis",
                "analysis_created_utc": datetime.now(UTC).isoformat(),
                "method": (
                    "unchanged analyze_confirmatory_rows on recovered rows; no simulation execution"
                ),
                "environment": runtime,
                "governance_limit": (
                    "Frozen no-retry booleans are code constants, not independent custody evidence."
                ),
                "physical_limit": (
                    "Recorded evaluator flags, not independently revalidated physical trajectories."
                ),
                "computation": computation,
            }
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
            print(
                json.dumps(
                    {
                        "status": "NEW_DATED_ANALYSIS_WRITTEN",
                        "decision": computation["frozen_analysis_result"]["decision"],
                    }
                )
            )
        else:
            stored = strict_json(read_regular(args.root / SUPPLEMENT, "e005-reconciliation.json"))
            require(stored["computation"] == computation, "post-release recomputation differs")
            print(
                json.dumps(
                    {
                        "status": "FROZEN_ANALYSIS_RECOMPUTATION_MATCHES",
                        "environment": runtime,
                        "simulation_executed": False,
                        "stored_replay_records_match": True,
                    }
                )
            )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(
            json.dumps({"status": "INVALID", "error_type": type(exc).__name__, "reason": str(exc)})
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
