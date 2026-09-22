"""Synthetic fixtures for the optional raw-row re-audit; not historical rows."""

from copy import deepcopy
import pytest
from validation.records import aggregate, ARMS


def rows():
    data = []
    for rep in range(2):
        for arm in ARMS:
            data.append(
                dict(
                    case_id="T03_primary_navigation_bias",
                    configuration_id=arm,
                    root_seed_id=f"fixture:{rep}",
                    replicate=rep,
                    physical_collision=False,
                    physical_keep_out_entry=False,
                    physical_corridor_departure=True,
                    hold_acquired=True,
                    infrastructure_failure=False,
                    nonlinear_truth_numerical_valid=True,
                    attempt_status="valid",
                    minimum_separation_m=24.0,
                    minimum_covariance_eigenvalue=1e-6,
                    maximum_covariance_trace=0.1,
                    monitor_override_commands=0,
                    monitor_reason_counts={},
                    primary_disposition_counts={"accepted": 301},
                    monitor_disposition_counts={"accepted": 301},
                    scenario_hash=f"scenario{rep}",
                    stream_hashes={"fixture": "same"},
                    controller_identity="fixture",
                    trace_digest=f"trace{rep}",
                )
            )
    return data


def test_valid_synthetic_aggregation():
    got = aggregate("E005", rows(), {"T03_primary_navigation_bias": 2})
    assert got["pair_tables"][0]["n11"] == 2
    assert all(r["retrospective_closed_union_witness"] for r in got["witnesses"])


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "missing",
        "nonboolean",
        "nonfinite",
        "wrong_arm",
        "bad_reason",
        "different_stream",
        "bad_replicate",
        "terminal_count",
        "invalid_numeric",
    ],
)
def test_invalid_synthetic_rows_rejected(mutation):
    r = rows()
    if mutation == "duplicate":
        r[-1] = deepcopy(r[0])
    if mutation == "missing":
        r.pop()
    if mutation == "nonboolean":
        r[0]["physical_corridor_departure"] = 1
    if mutation == "nonfinite":
        r[0]["minimum_separation_m"] = float("nan")
    if mutation == "wrong_arm":
        r[0]["configuration_id"] = "incorrect"
    if mutation == "bad_reason":
        r[1]["monitor_reason_counts"] = {"ESTIMATOR_QUALITY": 1}
    if mutation == "different_stream":
        r[1]["stream_hashes"] = {"fixture": "changed"}
    if mutation == "bad_replicate":
        r[-1]["replicate"] = 3
    if mutation == "terminal_count":
        r[1]["monitor_override_commands"] = 301
    if mutation == "invalid_numeric":
        r[0]["nonlinear_truth_numerical_valid"] = False
    with pytest.raises(ValueError):
        aggregate("E005", r, {"T03_primary_navigation_bias": 2})
