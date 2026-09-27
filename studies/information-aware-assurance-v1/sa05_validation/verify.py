"""Validate the separately recorded full numerical audit and its evidence bindings."""

import hashlib
from pathlib import Path

from iaa.artifact import read_json
from sa05.artifact import PUBLIC, verify

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_report(report, directory=PUBLIC):
    """Identity and semantic accounting, not a repeat of the ODE computation."""
    rows = read_json(directory / "results.json")
    if report["schema"] != "iaa-sa05-independent-numerical-audit/1":
        raise ValueError("Audit schema")
    if (
        report["audit_source_sha256"] != sha(HERE / "postflight.py")
        or report["reference_source_sha256"] != sha(HERE.parent / "sa05/reference.py")
        or report["original_manifest_sha256"] != sha(directory / "manifest.json")
        or report["physical_validation"] is not False
        or report["external_replication"] is not False
    ):
        raise ValueError("Audit source, evidence or scope identity")
    checks = report["checks"]
    if [(r["unit"], r["method"]) for r in rows] != [(c["unit"], c["method"]) for c in checks]:
        raise ValueError("Incomplete or reordered independent audit")
    matched = missing = 0
    for row, checked in zip(rows, checks, strict=True):
        if row["status"] != "completed":
            if checked["status"] != "not_replayed_incomplete_source_cell":
                raise ValueError("Missing source trial promoted")
            missing += 1
            continue
        trajectory = read_json(
            directory / "cases" / (row["unit"] + "--" + row["method"] + ".json")
        )["evidence"]["trajectory"]
        if (
            checked["status"] != "matched"
            or checked["samples"] != len(trajectory)
            or not 0 <= checked["max_position_error_m"] < 1e-5
            or not 0 <= checked["max_velocity_error_mps"] < 1e-7
            or abs(checked["potential_difference_m2"]) >= 5e-5
            or checked["recomputed_constraint_status"] != row["constraint_status"]
            or checked["recomputed_dwell_lower_ms"] != row["dwell_lower_ms"]
            or checked["recomputed_acquired_goal"] is not row["acquired_goal"]
        ):
            raise ValueError("Independent numerical/endpoint mismatch")
        matched += 1
    if (
        report["checked_cells"] != matched
        or report["mismatches"] != 0
        or report["unexecuted_cells"] != missing
    ):
        raise ValueError("Independent audit totals")
    return dict(
        passed=True,
        numerical_cells_matched=matched,
        incomplete_cells=missing,
        independently_reexecuted_now=False,
        physical_validation=False,
        external_replication=False,
    )


def main():
    original = verify(PUBLIC)
    report = validate_report(read_json(HERE / "independent-numerical-audit.json"))
    print({"original_artifact": original, "stored_independent_audit": report})


if __name__ == "__main__":
    main()
