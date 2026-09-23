"""Read-only reconstruction of recorded Task06 claims; no rerun of recovery trials."""

from pathlib import Path
from fractions import Fraction as Q
from collections import Counter
import csv
import json
import hashlib
from candidate.artifact import verify
from candidate.fixtures import fixtures
from candidate.refinement.scalar_recovery import result

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "recorded_development"


def read(name):
    return json.loads((DATA / name).read_text())


def test_complete_artifact_and_all_dual_witnesses():
    checked = verify(DATA)
    assert checked["named_cases"] == 24 and checked["grid_cases"] == 48
    assert checked["scalar_exact_checks"] == 8704
    assert checked["rechecked_negative_certificates"] == 22


def test_three_state_claim_preserves_quantifiers():
    rows = {r["case"]: r for r in read("fixtures.json")}
    negative = rows["three_face_conflict"]["candidate"]["negative"]
    assert negative["status"] == "proved_no_common_held_command"
    assert len(negative["active_obligations"]) == 3
    assert Q(negative["checked"]["margin_lower"]) > Q("0.000063")
    for name in ("three_face_pair_01", "three_face_pair_02", "three_face_pair_12"):
        assert rows[name]["fixed_pair_action"]["status"] == "certified_common_prefix"
    assert all(
        r["candidate"].get("positive", {}).get("recovery_status") != "certified_full_recovery"
        for r in rows.values()
    )


def test_exact_origin_recovery_and_command_authority():
    fs = fixtures()
    rows = read("recoveries.json")
    assert len(rows) == 10
    for row in rows:
        assert row["initial_exact"] == list(map(str, fs[row["case"]].hypotheses[0].lower))
        assert row["adjudication"]["status"] == "validated_containment"
        assert row["adjudication"]["hold_acquired"] == "satisfied"
        path = DATA / "recovery" / f"{row['case']}__{row['model']}" / "commands.csv"
        with path.open() as f:
            commands = list(csv.DictReader(f))
        assert len(commands) == 300
        for command in commands:
            assert (
                Q(float(command["ax_mps2"])) ** 2 + Q(float(command["ay_mps2"])) ** 2
                <= Q(1, 50) ** 2
            )


def test_nulls_and_budget_miss_are_retained():
    rows = {r["case"]: r["candidate"] for r in read("fixtures.json")}
    assert rows["outer_geometry_false_safe"]["status"] == "unresolved"
    missed = rows["compound_without_authority_loss"]
    assert missed["status"] == "unresolved_budget" and missed["action"] is None
    assert missed["deadline_exceeded"] and missed["wall_s"] > 1
    assert len(rows) == 24


def test_baseline_protection_not_misreported_as_failure():
    cases = read("comparisons.json")
    protected = 0
    unsupported = 0
    for case in cases:
        unsupported += case["status"] == "unsupported_native_actuation_bounds"
        for method in case.get("methods", {}).values():
            if method["protected"]:
                protected += 1
                assert method["separate_prefix_check"]["status"] == "certified_common_prefix"
    assert protected == 4 and unsupported == 5


def test_separate_scalar_refinement_identity():
    directory = BASE / "refinement"
    record = json.loads((directory / "recorded_result.json").read_text())
    for key, value in result().items():
        assert record[key] == value
    for name, expected in record["source_sha256"].items():
        assert hashlib.sha256((BASE / name).read_bytes()).hexdigest() == expected
    assert (
        hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest()
        == record["protocol_sha256"]
    )


def test_counts_reconstruct_without_population_inference():
    summary = read("summary.json")
    rows = read("fixtures.json")
    counts = Counter(r["candidate"]["status"] for r in rows)
    assert (counts["certified_common_prefix"], counts["proved_no_common_held_command"]) == (18, 4)
    assert summary["broad_novelty_established"] is False
    assert summary["physical_validation"] is False
    assert summary["protected_evaluation_accessed"] is False
