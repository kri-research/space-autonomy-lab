"""Endpoint, exact arithmetic, fixed-output and preservation regressions."""

from fractions import Fraction as F
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from post_review_correction_v1 import matrix, checks


@pytest.fixture(scope="module")
def result():
    return checks.calculate()


def test_all_supplied_scientific_fields_match(result):
    refs = json.loads((checks.ROOT / "REFERENCE.json").read_text())
    assert {k: checks.digest(checks.canonical(v)) for k, v in result.items()} == refs[
        "scientific_result_sha256"
    ]


@pytest.mark.parametrize("case", [0, 1])
def test_three_pairwise_prefixes_and_joint_obstruction(result, case):
    row = result["matrix"]["results"][case]
    assert row["all_independently_shifted_triples_verified"]
    assert F(row["minimum_initial_slack_m"]) > 0
    assert F(row["uniform_obstruction_margin_lower_m"]) > 0
    assert len(row["pairwise_continuous_checks"]) == 3
    for pair in row["pairwise_continuous_checks"]:
        assert F(pair["minimum_continuous_slack_lower_m"]) > 0
        assert pair["bernstein_halfspace_checks"] == 184
        assert sum(F(x) ** 2 for x in pair["command"]) <= F(1, 2500)


def test_exact_shift_radius_and_small_residual_are_not_sensor_bounds(result):
    row = result["matrix"]["results"][1]
    assert F(row["position_radius_m"]) == F(row["velocity_radius_mps"]) == F(3, 102400)
    assert F("3.80e-8") < F(row["uniform_obstruction_margin_lower_m"]) < F("4e-8")


def test_every_matrix_coefficient_is_rational_and_satisfies_recurrence():
    c, tail, norm = matrix.matrix_series()
    assert len(c) == 23 and isinstance(tail, F) and norm < 24
    assert all(type(x) is F for m in c for row in m for x in row)
    for k in range(1, 23):
        lhs = matrix.multiply(c[1], c[k - 1])
        assert lhs == [[x * k for x in row] for row in c[k]]


@pytest.mark.parametrize("t", [F(0), F(1, 8), F(1, 4), F(1, 2), F(3, 4), F(1)])
def test_bernstein_conversion_preserves_selected_polynomials(t):
    from math import comb

    for power in range(6):
        b = [F(comb(j, power), comb(5, power)) if j >= power else F(0) for j in range(6)]
        value = sum((b[j] * comb(5, j) * t**j * (1 - t) ** (5 - j) for j in range(6)), F(0))
        assert value == t**power


def test_float_pollution_is_rejected(monkeypatch):
    monkeypatch.setattr(matrix, "N", float(matrix.N))
    with pytest.raises(ValueError):
        matrix.matrix_series()


def test_unsafe_altered_input_is_rejected(monkeypatch):
    monkeypatch.setattr(matrix, "STATE", ((F(0), F(-200), F(0), F(0)), *matrix.STATE[1:]))
    with pytest.raises(ValueError):
        matrix.evaluate()


def test_explicit_failure_survives_optimized_interpreter():
    p = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "from post_review_correction_v1.matrix import require; require(False)",
        ],
        cwd=checks.STUDY,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=10,
    )
    assert p.returncode != 0 and "ValueError" in p.stderr


def test_computational_entry_point_does_not_load_original_numerics():
    code = "from post_review_correction_v1.checks import calculate; calculate(); import sys; assert not any(x.startswith(('independent_hcw_audit_v1','candidate','scipy','numpy')) for x in sys.modules)"
    p = subprocess.run(
        [sys.executable, "-S", "-c", code],
        cwd=checks.STUDY,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert p.returncode == 0, p.stderr
    for name in ("matrix.py", "endpoint.py", "stress.py"):
        tree = ast.parse((checks.ROOT / name).read_text())
        assert not any(isinstance(n, ast.Assert) for n in ast.walk(tree))


@pytest.mark.parametrize("case", [0, 1, 2])
def test_named_larger_stress_is_outside_both_components(result, case):
    row = result["stress"]["cases"][case]
    assert row["outside_both_components"]
    assert row["corridor_violation_lower_m"] > 0 and row["ellipse_polynomial_excess_lower"] > 0
    assert "no all-command impossibility" in result["stress"]["scope"]


def oracle(state, schedule, t):
    c, tail, _ = matrix.matrix_series()

    def response(time):
        return [
            [sum((a[i][j] * time**k for k, a in enumerate(c)), F(0)) for j in range(6)]
            for i in range(4)
        ]

    phi = response(t)
    values = [sum((phi[i][j] * state[j] for j in range(4)), F(0)) for i in range(4)]
    error = tail * max(abs(x) for x in state)
    for a, b, u in schedule:
        if t <= a:
            continue
        start, end = response(t - a), response(max(F(0), t - b))
        for i in range(4):
            values[i] += sum(((start[i][4 + j] - end[i][4 + j]) * u[j] for j in range(2)), F(0))
        error += 2 * tail * max(abs(x) for x in u)
    return [(v - error, v + error) for v in values]


@pytest.mark.parametrize("time", [F(0), F(1, 8), F(1, 4), F(1, 2), F(3, 4), F(1)])
def test_unchanged_kernel_endpoint_superposition_matches_matrix_oracle(time):
    from independent_hcw_audit_v1.hcw import exact_schedule_range

    state = (F(0), F(-80), F(1, 1000), F(-1, 1000))
    schedule = [
        (F(0), F(1, 4), (F(1, 100), F(0))),
        (F(1, 4), F(1, 2), (F(-1, 200), F(1, 300))),
        (F(1, 2), F(1), (F(0), F(-1, 250))),
    ]
    actual = exact_schedule_range(state, schedule, time)
    expected = oracle(state, schedule, time)
    assert all(
        max(a.lower, lo) <= min(a.upper, hi) for a, (lo, hi) in zip(actual, expected, strict=True)
    )


@pytest.mark.parametrize("time", [F(0), F(1, 4), F(1, 2), F(1)])
def test_event_endpoints_are_exact_in_zero_mean_motion_limit(time):
    from independent_hcw_audit_v1.hcw import exact_schedule_range

    state = (F(1), F(-80), F(1, 1000), F(0))
    schedule = [(F(0), F(1, 4), (F(1, 100), F(0))), (F(1, 4), F(1), (F(-1, 200), F(1, 300)))]
    actual = exact_schedule_range(state, schedule, time, n=F(0))
    p = [state[i] + time * state[i + 2] for i in range(2)]
    v = list(state[2:])
    for a, b, u in schedule:
        duration = max(F(0), min(time, b) - a)
        for i in range(2):
            p[i] += u[i] * duration * (time - a - duration / 2)
            v[i] += u[i] * duration
    assert all(x.contains(y) for x, y in zip(actual, p + v, strict=True))


def test_current_segment_counted_twice_is_a_different_formula(result):
    row = result["endpoint"]
    assert F(row["correct_radial_forcing_contribution"][1]) < F(
        row["double_counted_radial_forcing_contribution"][0]
    )
    assert row["intervals_disjoint"] and not row["implementation_contradiction_claimed"]
    note = (checks.ROOT / "ENDPOINT_CONVENTION.md").read_text()
    assert "j < k" in note and "Gamma(0)=0" in note and "remains unchanged" in note


def test_frozen_derivation_and_original_numerical_modules_unchanged():
    audit = checks.STUDY / "independent_hcw_audit_v1"
    protocol = json.loads((audit / "frozen/protocol.json").read_text())
    for name, expected in protocol["auditor_source_sha256"].items():
        assert hashlib.sha256((audit / name).read_bytes()).hexdigest() == expected, name


def test_recorded_result_recomputes_without_replacing_it():
    assert checks.verify(checks.ROOT / "recorded")["passed"]
    with pytest.raises(ValueError):
        checks.record(checks.ROOT / "recorded")


@pytest.mark.parametrize("mutation", ["result", "manifest", "source_commit"])
def test_corrupted_record_is_rejected(tmp_path, mutation):
    for p in (checks.ROOT / "recorded").iterdir():
        if p.is_file():
            shutil.copyfile(p, tmp_path / p.name)
    if mutation == "result":
        p = tmp_path / "results.json"
        doc = json.loads(p.read_text())
        doc["matrix"]["results"][0]["uniform_obstruction_margin_lower_m"] = "1"
        p.write_text(json.dumps(doc))
    else:
        p = tmp_path / "manifest.json"
        doc = json.loads(p.read_text())
        if mutation == "manifest":
            doc["source_sha256"]["matrix.py"] = "0" * 64
        else:
            doc["source_commit"] = "0" * 40
        p.write_text(json.dumps(doc))
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        checks.verify(tmp_path)
