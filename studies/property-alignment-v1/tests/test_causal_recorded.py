"""Regression checks for the retained developmental data; no campaign is rerun."""

from pathlib import Path
import json
import numpy as np
from causal.io import verify_seal, sha
from causal.verify_records import verify, strict_json
from causal.analyze import verify_delivery

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "causal/recorded_execution"
ANALYSIS = ROOT / "causal/recorded_analysis"


def test_retained_source_protocol_binding():
    sealed = verify_seal()
    assert sealed == strict_json(DATA / "seal.json")
    assert sha(ROOT / "causal/protocol.json") == sealed["protocol_sha256"]
    # Execution save_json sorts keys; the copied values are identical but bytes differ.
    assert strict_json(DATA / "protocol.json") == strict_json(ROOT / "causal/protocol.json")
    assert sha(DATA / "protocol.json") == strict_json(DATA / "manifest.json")["protocol.json"]


def test_complete_record_reconstruction():
    result = verify(DATA)
    assert result["cells"] == 56
    assert result["reconstructed_counts"] == {
        "commands": 16800,
        "states": 67256,
        "packet_opportunities": 14448,
        "applied_segments": 67200,
    }


def test_all_outcomes_and_initial_qualification_retained():
    p, rows = verify_delivery(DATA)
    assert len(rows) == 56 and len(p["cases"]) == 7
    qualifications = [strict_json(f) for f in (DATA / "qualification").glob("*/result.json")]
    assert len(qualifications) == 6
    assert all(
        q["finite_horizon_recoverability"] == "demonstrated_fixed_input_continuation"
        for q in qualifications
    )
    assert all(
        r["physical_status"] in ("validated_violation", "validated_containment", "unresolved")
        for r in rows
    )
    assert sum(r["case_role"] == "unrecoverable_control" for r in rows) == 8


def test_same_path_and_predicate_only_contrasts():
    fixed = strict_json(DATA / "classification_only.json")
    assert fixed["shared_continuous_arcs"] and not fixed["control_modified"]
    assert fixed["results"]["in_band"]["status"] == "clear"
    assert fixed["results"]["closed_union"]["status"] == "violated"
    result = strict_json(ANALYSIS / "results.json")
    assert result["same_motion_core_pairs"] == 8 and result["changed_motion_core_pairs"] == 6
    for kind in ("hcw", "nonlinear"):
        old = strict_json(DATA / "cells" / f"midpoint__{kind}__controlled_in_band" / "summary.json")
        aligned = strict_json(
            DATA / "cells" / f"midpoint__{kind}__controlled_union" / "summary.json"
        )
        assert old["overrides"] == 0 and aligned["overrides"] == 45
        assert (
            aligned["changed_commands"] == 0
            and old["selected_command_sha256"] == aligned["selected_command_sha256"]
        )


def test_logged_actual_changes_and_estimator_innovation_pairing():
    for kind in ("hcw", "nonlinear"):
        base = DATA / "cells" / f"estimated_nominal__{kind}__controlled_in_band"
        changed = DATA / "cells" / f"estimated_nominal__{kind}__controlled_union"
        a = strict_json(base / "summary.json")
        b = strict_json(changed / "summary.json")
        assert a["innovation_sha256"] == b["innovation_sha256"]
        assert b["changed_commands"] == 45 and a["motion_sha256"] != b["motion_sha256"]
        records = [
            json.loads(line) for line in (changed / "commands.jsonl").read_text().splitlines()
        ]
        assert all(
            r["command_changed"] == (not np.array_equal(r["proposed"], r["selected"]))
            for r in records
        )
