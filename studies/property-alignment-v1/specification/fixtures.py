"""Reproduce exact analytical illustrations; no stochastic evaluation is executed."""

from fractions import Fraction as F
from pathlib import Path
import argparse
import json
from .analytical import robust_braking, endpoint_input_interval, quadratic_extrema


def results() -> dict:
    base = dict(
        clearance="3/5",
        speed="1/10",
        position_error=0,
        speed_error=0,
        age=0,
        delay=0,
        inward_acceleration=0,
        brake="1/50",
    )
    variations = {
        "position_error": "1/10",
        "speed_error": "1/50",
        "age": 1,
        "delay": 1,
        "brake": "3/200",
    }
    single = {key: robust_braking(**(base | {key: value})) for key, value in variations.items()}
    joint = robust_braking(**(base | variations))
    assert all(item["robust_arrest_possible"] for item in single.values())
    assert joint["margin"] == F(-11, 50)
    right = endpoint_input_interval("9/10", "1/5", 1, "2/5")
    left = endpoint_input_interval("-9/10", "-1/5", 1, "2/5")
    assert right[1] < left[0]
    trajectories = []
    for sign in (-1, 1):
        q, v = sign * F(9, 10), sign * F(1, 5)
        arcs = []
        for u in (-sign * F(2, 5), sign * F(1, 5), F(0)):
            lo, hi, q, v = quadratic_extrema(q, v, u, 1)
            assert -1 <= lo <= hi <= 1
            arcs.append(
                dict(
                    control=u,
                    minimum_position=lo,
                    maximum_position=hi,
                    final_position=q,
                    final_velocity=v,
                )
            )
        assert v == 0
        trajectories.append({"initial_sign": sign, "one_second_held_arcs": arcs})
    return {
        "kind": "exact_background_analytical_fixtures",
        "novelty_claim": False,
        "spacecraft_recovery_certificate": False,
        "compound_braking": {
            "base_inputs": base,
            "individual_changes": variations,
            "single_factor_results": single,
            "joint_result": joint,
        },
        "common_policy_counterexample": {
            "plant": "qdot=v; vdot=u; |q|<=1; |u|<=2/5",
            "observation_assumption": "No distinguishing observation for the next second",
            "input_assumption": "Commands held for one second",
            "right_necessary_endpoint_interval": right,
            "left_necessary_endpoint_interval": left,
            "common_first_input_exists": False,
            "individually_recoverable_paths": trajectories,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = (
        json.dumps(results(), indent=2, default=lambda v: str(v) if isinstance(v, F) else v) + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
