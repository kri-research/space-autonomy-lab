"""Reproduce bounded validation; never execute or rewrite historical campaigns."""

from pathlib import Path
from fractions import Fraction as Q
from types import SimpleNamespace
import argparse
import csv
import hashlib
import json
import math
import platform
import os
import sys
import time
import numpy as np
import scipy
from scipy.integrate import solve_ivp
from specification.contract import load_property
from baseline.validation.loader import originals, config
from .interval import Box
from .flow import Model, propagate_schedule
from .polynomial import PolynomialArc
from .engine import adjudicate
from .geometry import bounds, numerical_agreement_witness
from .extrema import bounded_extreme

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_SHA = "391ae439bddb82809995f4905bba395d08e666321d5b281f15be4d4c905d803f"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_csv(path, rows):
    with path.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def polynomial_fixtures(prop):
    center = Q(129, 256)
    cases = [
        ("corridor_only", ((0,), (-70,), (0,), (0,)), 1, "validated_containment"),
        ("hold_only", ((0,), (-28,), (0,), (0,)), 1, "validated_containment"),
        ("component_transition", ((0,), (-40, 12), (0,), (12,)), 1, "validated_containment"),
        (
            "permitted_tangency",
            ((0,), (Q(-109, 4), 1, -1), (0,), (1, -2)),
            1,
            "validated_containment",
        ),
        (
            "narrow_excursion",
            ((0,), (-27 + Q(1, 10**8) - center**2, 2 * center, -1), (0,), (2 * center, -2)),
            1,
            "validated_violation",
        ),
        ("forbidden_contact", ((2,), (Q(-1, 2), 1), (0,), (1,)), 1, "validated_violation"),
        ("closed_hold_dwell", ((0,), (-30,), (0,), (0,)), 300, "validated_containment"),
        ("initially_outside", ((0,), (-105,), (0,), (0,)), 1, "validated_violation"),
    ]
    result = []
    for name, coeffs, end, expected in cases:
        arc = PolynomialArc(Q(0), Q(end), tuple(tuple(map(Q, c)) for c in coeffs))
        observed = adjudicate([arc], prop, end=end, minimum_width=Q(1, 65536))
        assert observed["status"] == expected, (name, observed)
        result.append(
            {
                "name": name,
                "known_answer": expected,
                "observed": observed,
                "coefficients": coeffs,
                "duration_s": end,
                "scope": "exact rational curve fixture; not a spacecraft population",
            }
        )
    return result


def extrema_fixtures(old):
    rows = []
    for name, module in zip(("E004", "E005"), old[2:4], strict=True):
        for maximize in (True, False):
            sign = 1 if maximize else -1
            for mode in ("failed", "nonfinite_fun", "nonfinite_x", "out_of_bracket", "inferior"):

                def objective(t):
                    return sign * (1 - 8 * (t - 0.5) ** 2)

                def optimizer(fun, *, bounds, **kwargs):
                    x = {"nonfinite_x": math.nan, "out_of_bracket": 2.0, "inferior": bounds[0]}.get(
                        mode, 0.5
                    )
                    return SimpleNamespace(
                        success=mode != "failed",
                        x=x,
                        fun=math.nan if mode == "nonfinite_fun" else 0.0,
                    )

                previous = module.minimize_scalar
                try:
                    module.minimize_scalar = optimizer
                    original = module._bounded_extreme(objective, 1.0, maximize=maximize)[0]
                finally:
                    module.minimize_scalar = previous
                corrected = bounded_extreme(objective, 1.0, maximize=maximize, optimizer=optimizer)
                assert corrected.value == sign and corrected.unresolved
                rows.append(
                    {
                        "original_module": name,
                        "maximize": maximize,
                        "failure_mode": mode,
                        "known_sampled_extreme": sign,
                        "original_returned": original if math.isfinite(original) else "nonfinite",
                        "corrected_returned": corrected.value,
                        "unresolved": list(corrected.unresolved),
                        "historical_occurrence_claimed": False,
                    }
                )
    return rows


def reference_trace(commands, initial, cfg, rtol, atol):
    from baseline.scripts.run_diagnostics import relative_rhs

    state = np.array([initial[0], initial[1], 0.0, initial[2], initial[3], 0.0])
    trace = [np.array(initial)]
    for u in commands:
        result = solve_ivp(
            relative_rhs,
            (0.0, 1.0),
            state,
            method="DOP853",
            args=(np.r_[u, 0.0], cfg.gravitational_parameter_m3_s2, cfg.reference_radius_m),
            rtol=rtol,
            atol=atol,
            t_eval=[0.25, 0.5, 0.75, 1.0],
        )
        if not result.success or not np.all(np.isfinite(result.y)):
            raise ArithmeticError("Independent relative integration failed")
        trace.extend(result.y[[0, 1, 3, 4], :].T)
        state = result.y[:, -1]
    return np.asarray(trace)


def inertial_trace(module, commands, initial, cfg, step):
    chief = module.circular_chief_state(cfg.gravitational_parameter_m3_s2, cfg.reference_radius_m)
    relative = np.array([initial[0], initial[1], 0.0, initial[2], initial[3], 0.0])
    state = module.pair_from_relative(chief, relative)
    trace = [module.pair_to_relative(state)[[0, 1, 3, 4]]]
    for u in commands:
        for _ in range(4):
            state = module.propagate_fixed(
                state, np.r_[u, 0.0], cfg.gravitational_parameter_m3_s2, 0.25, step
            )
            relative = module.pair_to_relative(state)
            trace.append(relative[[0, 1, 3, 4]])
    return np.asarray(trace)


def frame_fixtures(module, cfg, protocol):
    rows = []
    mu, radius = cfg.gravitational_parameter_m3_s2, cfg.reference_radius_m
    n = math.sqrt(mu / radius**3)
    rho = np.array([1.0, -80.0, 2.0, 0.01, 0.12, -0.003])
    u = np.array([0.02, 0.0, 0.0])
    for phase in protocol["frame_phases_rad"]:
        for elapsed in (0.0, protocol["frame_checks_duration_s"]):
            angle = phase + n * elapsed
            c, s = math.cos(angle), math.sin(angle)
            rotation = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
            chief = module.circular_chief_state(mu, radius, elapsed, phase_rad=phase)
            expected = np.r_[
                chief[:3] + rotation @ rho[:3],
                chief[3:] + rotation @ np.array([rho[3] - n * rho[1], rho[4] + n * rho[0], rho[5]]),
            ]
            actual = module.relative_to_inertial(chief, rho)
            error = actual - expected
            thrust = module.command_to_inertial(chief, u)
            thrust_error = float(np.linalg.norm(thrust - rotation @ u))
            assert np.linalg.norm(error[:3]) < 2e-8 and np.linalg.norm(error[3:]) < 2e-11
            assert thrust_error < 1e-14
            rows.append(
                {
                    "phase_rad": phase,
                    "elapsed_s": elapsed,
                    "position_difference_m": float(np.linalg.norm(error[:3])),
                    "velocity_difference_mps": float(np.linalg.norm(error[3:])),
                    "command_rotation_difference_mps2": thrust_error,
                    "scope": "separate analytic circular-frame numerical calculation",
                }
            )
    return rows


def main():
    sys.path.insert(0, str(ROOT / "baseline"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw_output = args.output.expanduser().absolute()
    if any(p.is_symlink() for p in (raw_output, *raw_output.parents)):
        raise ValueError("Symlinks are not allowed in validation output paths")
    args.output = raw_output.resolve()
    protected = [ROOT.parents[1]]
    if os.environ.get("SAL_EVIDENCE_ROOT"):
        protected.append(Path(os.environ["SAL_EVIDENCE_ROOT"]).expanduser().resolve())
    if any(args.output.is_relative_to(p) for p in protected):
        raise ValueError(
            "Validation output must be outside the research and historical repositories"
        )
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name("validation_protocol.json")
    assert digest(source) == PROTOCOL_SHA, "Validation protocol drift"
    protocol = json.loads(source.read_text())
    command_file = ROOT / protocol["command_file"]
    assert digest(command_file) == protocol["command_sha256"], "Fixed input drift"
    commands = np.array(json.loads(command_file.read_text())["commands_mps2"])
    assert commands.shape == (300, 2) and np.all(np.isfinite(commands))
    initial = protocol["initial_planar_state"]
    cfg, prop, old = config(), load_property(), originals(expanded_cache=True)
    output = {
        "schema": "sal-adjudication-validation-results/1",
        "protocol_sha256": PROTOCOL_SHA,
        "input_sha256": protocol["command_sha256"],
        "kind": "bounded_validation_not_campaign",
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "system": platform.system(),
            "architecture": platform.machine(),
        },
        "physical_validation": False,
        "historical_records_modified": False,
    }
    try:
        output["analytical_fixtures"] = polynomial_fixtures(prop)
        output["original_extrema_fixtures"] = extrema_fixtures(old)
        output["frame_fixtures"] = frame_fixtures(old[1], cfg, protocol)
        print("Analytical, extrema and frame fixtures passed", flush=True)
        reference = {}
        for tol in protocol["relative_dop853_rtol"]:
            reference[tol] = reference_trace(
                commands, initial, cfg, tol, protocol["relative_dop853_atol"]
            )
        truth = reference[min(reference)]
        comparisons = []
        production = None
        for step in protocol["original_rk4_steps_s"]:
            trace = inertial_trace(old[1], commands, initial, cfg, step)
            if production is None:
                production = trace
            difference = trace - truth
            disagreements = sum(
                bounds(Box.point(a.tolist()), prop)["containment"]
                != bounds(Box.point(b.tolist()), prop)["containment"]
                for a, b in zip(trace, truth, strict=True)
            )
            comparisons.append(
                {
                    "inertial_maximum_step_s": step,
                    "relative_reference_rtol": min(reference),
                    "maximum_position_difference_m": float(
                        np.max(np.linalg.norm(difference[:, :2], axis=1))
                    ),
                    "maximum_velocity_difference_mps": float(
                        np.max(np.linalg.norm(difference[:, 2:], axis=1))
                    ),
                    "sampled_membership_disagreements": disagreements,
                    "certified_error_bound": False,
                }
            )
        output["inertial_relative_comparisons"] = comparisons
        output["relative_tolerance_comparisons"] = [
            {
                "rtol": tol,
                "maximum_position_difference_m": float(
                    np.max(np.linalg.norm((trace - truth)[:, :2], axis=1))
                ),
                "maximum_velocity_difference_mps": float(
                    np.max(np.linalg.norm((trace - truth)[:, 2:], axis=1))
                ),
                "certified_error_bound": False,
            }
            for tol, trace in reference.items()
        ]
        index = int(np.argmin(np.linalg.norm(truth[:, :2], axis=1)))
        output["numerical_exclusion_witness"] = numerical_agreement_witness(
            [truth[index].tolist(), production[index].tolist()], prop
        )
        output["numerical_exclusion_witness"]["time_s"] = index * 0.25
        assert (
            output["numerical_exclusion_witness"]["status"] == "numerically_corroborated_violation"
        )
        save_csv(args.output / "numerical_comparisons.csv", comparisons)
        save_csv(
            args.output / "independent_relative_trace.csv",
            [
                {
                    "time_s": i * 0.25,
                    **dict(zip(("x_m", "y_m", "vx_mps", "vy_mps"), map(float, s), strict=True)),
                }
                for i, s in enumerate(truth)
            ],
        )
        output["validated_flows"] = []
        schedule = [(i, i + 1, u.tolist()) for i, u in enumerate(commands)]
        for model_name in ("hcw", "nonlinear"):
            for step in protocol["interval_maximum_steps_s"]:
                started = time.perf_counter()
                arcs = propagate_schedule(
                    Model(model_name),
                    initial,
                    schedule,
                    maximum_step=step,
                    order=protocol["taylor_order"],
                )
                flow = {
                    "model": model_name,
                    "maximum_step_s": step,
                    "taylor_order": protocol["taylor_order"],
                    "segments": len(arcs),
                    "adjudications": [],
                    "initial_condition": "exact represented midpoint; fixed applied commands",
                }
                for resolution in protocol["event_resolutions_s"]:
                    verdict = adjudicate(
                        arcs, prop, minimum_width=Q(resolution), required_events=range(301)
                    )
                    assert verdict["status"] == "validated_violation", verdict
                    flow["adjudications"].append({"resolution_s": resolution, **verdict})
                flow["last_state_widths"] = list(arcs[-1].point(300).widths)
                trace = []
                points = [(arcs[0].start, arcs[0].point(0))] + [
                    (a.end, a.point(a.end)) for a in arcs
                ]
                for t, box in points:
                    trace.append(
                        {
                            "time_s": float(t),
                            **{
                                name + suffix: value
                                for name, v in zip(
                                    ("x_m", "y_m", "vx_mps", "vy_mps"), box.coordinates, strict=True
                                )
                                for suffix, value in (("_lo", v.lo), ("_hi", v.hi))
                            },
                        }
                    )
                flow["trace_file"] = f"{model_name}-enclosure-{step:g}.csv"
                save_csv(args.output / flow["trace_file"], trace)
                output["validated_flows"].append(flow)
                print(
                    model_name,
                    step,
                    flow["adjudications"][-1]["first_exit_bracket_s"],
                    "widths",
                    flow["last_state_widths"],
                    "elapsed",
                    time.perf_counter() - started,
                    flush=True,
                )
        output["source_sha256"] = {
            str(p.relative_to(ROOT)): digest(p)
            for p in sorted((ROOT / "adjudication").glob("*.py"))
        }
        output["status"] = "passed"
    except Exception as exc:
        output.update(status="failed", error=type(exc).__name__ + ":" + str(exc))
        (args.output / "results.json").write_text(
            json.dumps(output, indent=2, default=str, allow_nan=False) + "\n"
        )
        raise
    from bundle import source_inventory

    output["baseline_source_sha256"] = source_inventory()
    output["property_sha256"] = digest(ROOT / "specification/property_contract.json")
    output["scope_limits"] = [
        "Validated flow is conditional on the stated circular-chief ODE, exact represented initial values and known piecewise-constant inputs.",
        "Inertial/relative disagreement measures numerical differences and slightly different rounded initial states, not a global error bound.",
        "Dense reference sampling is never used to certify containment or continuous dwell.",
        "Interval bounds include rounding and Taylor remainder but not physical model error or unmodeled disturbances.",
        "No new historical campaign, population-level comparison, control advantage or physical validation is reported.",
    ]
    (args.output / "results.json").write_text(
        json.dumps(output, indent=2, default=str, allow_nan=False) + "\n"
    )
    files = {p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}
    (args.output / "manifest.json").write_text(json.dumps(files, indent=2) + "\n")
    print(
        "Validation completed with separately identified numerical and enclosure evidence.",
        flush=True,
    )


if __name__ == "__main__":
    main()
