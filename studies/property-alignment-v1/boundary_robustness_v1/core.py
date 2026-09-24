"""Fixed-witness sufficient margins for uncertain boxes and all shifted triples.

Uses the unchanged R02 interval/HCW response. No original policy is called.
"""

from dataclasses import dataclass
from fractions import Fraction as Q
from functools import lru_cache
from pathlib import Path
import json
from independent_hcw_audit_v1.arithmetic import Interval as I, dot, rational
from independent_hcw_audit_v1.hcw import N, maps
from independent_hcw_audit_v1.certificates import geometry, halfspaces_valid
from independent_hcw_audit_v1.schema import identity

ROOT = Path(__file__).resolve().parent
ANCHORS = json.loads((ROOT / "anchors.json").read_text())
STATES = tuple(tuple(Q(v) for v in s) for s in ANCHORS["states"])
PAIRS = tuple(
    (tuple(x["pair"]), tuple(Q(v) for v in x["command"])) for x in ANCHORS["pair_witnesses"]
)
U = Q(ANCHORS["authority"])
WEIGHTS = tuple(Q(v) for v in ANCHORS["weights"])
NEG_NORMALS = tuple(tuple(Q(v) for v in n) for n in ANCHORS["negative_normals"])
NEG_BOUNDS = tuple(Q(v) for v in ANCHORS["negative_bounds"])
NORMALS = ((Q(0), Q(-1)), (Q(0), Q(1)), (Q(1), Q(1, 10)), (Q(-1), Q(1, 10)))
BOUNDS = (Q(100), Q(-30), Q(0), Q(0))
SLICES = 256


def require(value, message):
    if not value:
        raise ValueError(message)


def magnitude(x):
    return max(abs(x.lower), abs(x.upper))


def projected(matrix, normal):
    return tuple(dot(normal, [matrix[0][j], matrix[1][j]]) for j in range(len(matrix[0])))


@dataclass(frozen=True)
class Parameters:
    position_m: Q = Q(0)
    velocity_mps: Q = Q(0)
    mean_motion_relative: Q = Q(0)
    queue_delay_s: Q = Q(0)

    def __post_init__(self):
        for key in self.__dataclass_fields__:
            object.__setattr__(self, key, rational(getattr(self, key)))
        require(
            0 <= self.position_m <= Q(1, 100) and 0 <= self.velocity_mps <= Q(1, 100),
            "State perturbation domain",
        )
        require(
            0 <= self.mean_motion_relative <= 1 and 0 <= self.queue_delay_s <= 1,
            "Model/delay domain",
        )

    def payload(self):
        return {key: str(getattr(self, key)) for key in self.__dataclass_fields__}

    @property
    def n(self):
        return I.bounds(N * (1 - self.mean_motion_relative), N * (1 + self.mean_motion_relative))


def family_parameters(family, radius):
    radius = rational(radius)
    require(0 <= radius <= 1, "Dimensionless radius outside registered range")
    return Parameters(*(radius * Q(x) for x in family["scale"]))


def initial_margin(p):
    values = []
    for index, state in enumerate(STATES):
        for face, (normal, bound) in enumerate(zip(NORMALS, BOUNDS, strict=True)):
            base = bound - sum(a * x for a, x in zip(normal, state[:2], strict=True))
            values.append((base - sum(abs(a) for a in normal) * p, index, face))
    m, i, f = min(values)
    return {"lower_m": str(m), "state": i, "face": f, "all_initial_boxes_in_corridor": m >= 0}


@lru_cache(maxsize=256)
def response_envelope(n_relative, delay):
    """Min nominal residual and max state gains over COMPLETE time cells.

    Each post-application cell uses Phi([a,b+delay]) and Gamma([a,b]).
    Every known delay d in [0,delay] is covered, conservatively losing their
    common-time correlation. Before application the zero queue is checked on
    the whole [0,delay]. The original commands remain fixed.
    """
    model = Parameters(mean_motion_relative=n_relative, queue_delay_s=delay)
    n, D = model.n, model.queue_delay_s
    require(N == Q(ANCHORS["mean_motion"]), "Changed represented mean motion")
    halfspaces_valid()
    queue_rows = []
    held_rows = []
    for k in range(SLICES):
        a, b = Q(k, SLICES), Q(k + 1, SLICES)
        phi, _ = maps(a, b + D, n)
        _, gamma = maps(a, b, n)
        for face, normal in enumerate(NORMALS):
            held_rows.append((k, face, projected(phi, normal), projected(gamma, normal)))
        if D:
            phi, _ = maps(a * D, b * D, n)
            for face, normal in enumerate(NORMALS):
                queue_rows.append((k, face, projected(phi, normal), None))
    pairs = []
    for pair, command in PAIRS:
        require(sum(v * v for v in command) <= U * U, "Original command bound")
        minimum = None
        position_gain = Q(0)
        velocity_gain = Q(0)
        limiting = None
        cells = 0
        for phase, rows in (("queue", queue_rows), ("hold", held_rows)):
            for k, face, pr, gr in rows:
                forcing = I.value(0) if gr is None else dot(gr, command)
                gp = sum(magnitude(x) for x in pr[:2])
                gv = sum(magnitude(x) for x in pr[2:])
                position_gain = max(position_gain, gp)
                velocity_gain = max(velocity_gain, gv)
                for i in pair:
                    upper = (dot(pr, STATES[i]) + forcing).upper
                    residual = BOUNDS[face] - upper
                    if minimum is None or residual < minimum:
                        minimum = residual
                        limiting = {
                            "state": i,
                            "face": face,
                            "phase": phase,
                            "cell": k,
                            "normalized_cell": [str(Q(k, SLICES)), str(Q(k + 1, SLICES))],
                            "projected_state_coefficients": [v.payload() for v in pr],
                            "nominal_projection_upper_m": str(upper),
                        }
                    cells += 1
        pairs.append(
            {
                "pair": list(pair),
                "command": list(map(str, command)),
                "base_residual_lower_m": str(minimum),
                "position_gain_upper": str(position_gain),
                "velocity_gain_upper_s": str(velocity_gain),
                "limiting_nominal_row": limiting,
                "continuous_halfspace_checks": cells,
            }
        )
    # At post-application time one, the zero queue contributes no forcing.
    phi, _ = maps(1, 1 + D, n)
    _, gamma = maps(1, 1, n)
    rows = []
    upper = Q(0)
    beta_p = Q(0)
    beta_v = Q(0)
    for i, (normal, bound, w) in enumerate(zip(NEG_NORMALS, NEG_BOUNDS, WEIGHTS, strict=True)):
        pr = projected(phi, normal)
        row = projected(gamma, normal)
        b = I.value(bound) - dot(pr, STATES[i])
        gp = sum(magnitude(x) for x in pr[:2])
        gv = sum(magnitude(x) for x in pr[2:])
        upper += w * b.upper
        beta_p += w * gp
        beta_v += w * gv
        rows.append(
            {
                "state": i,
                "normal": list(map(str, normal)),
                "bound_m": str(bound),
                "weight": str(w),
                "rhs_center_interval_m": b.payload(),
                "state_coefficients": [v.payload() for v in pr],
                "action_coefficients_s2": [v.payload() for v in row],
                "position_gain_upper": str(gp),
                "velocity_gain_upper_s": str(gv),
            }
        )
    residuals = []
    for j in range(2):
        lo = sum(
            w * Q(row["action_coefficients_s2"][j][0]) for w, row in zip(WEIGHTS, rows, strict=True)
        )
        hi = sum(
            w * Q(row["action_coefficients_s2"][j][1]) for w, row in zip(WEIGHTS, rows, strict=True)
        )
        residuals.append(max(abs(lo), abs(hi)))
    delta = -upper - U * sum(residuals)
    return {
        "n_interval_s_inverse": n.payload(),
        "delay_interval_s": ["0", str(D)],
        "pairs": pairs,
        "negative": {
            "rows": rows,
            "center_margin_lower_m": str(delta),
            "weighted_rhs_upper_m": str(upper),
            "coefficient_residual_upper_s2": list(map(str, residuals)),
            "position_loss_gain": str(beta_p),
            "velocity_loss_gain_s": str(beta_v),
        },
        "continuous_time_cells_per_phase": SLICES,
        "finite_time_grid_is_interval_coverage": True,
    }


def evaluate(parameters):
    require(isinstance(parameters, Parameters), "Explicit parameters required")
    envelope = response_envelope(parameters.mean_motion_relative, parameters.queue_delay_s)
    pairs = []
    for row in envelope["pairs"]:
        loss = (
            Q(row["position_gain_upper"]) * parameters.position_m
            + Q(row["velocity_gain_upper_s"]) * parameters.velocity_mps
        )
        margin = Q(row["base_residual_lower_m"]) - loss
        pairs.append(
            {
                **row,
                "state_error_loss_upper_m": str(loss),
                "residual_lower_m": str(margin),
                "certified": margin >= 0,
            }
        )
    init = initial_margin(parameters.position_m)
    neg = envelope["negative"]
    center = Q(neg["center_margin_lower_m"])
    loss = (
        Q(neg["position_loss_gain"]) * parameters.position_m
        + Q(neg["velocity_loss_gain_s"]) * parameters.velocity_mps
    )
    shifted = center - loss
    positive = init["all_initial_boxes_in_corridor"] and all(x["certified"] for x in pairs)
    result = {
        "schema": "sal-three-state-sensitivity-result/1",
        "parameters": parameters.payload(),
        "family_id": identity(
            {
                "anchors": ANCHORS,
                "parameters": parameters.payload(),
                "scope": "all independent shifted states, common constant n and known zero queue",
            }
        ),
        "initial": init,
        "pair_bounds": pairs,
        "center_obstruction": center > 0,
        "uniform_shifted_obstruction": shifted > 0,
        "center_obstruction_margin_lower_m": str(center),
        "shifted_obstruction_margin_lower_m": str(shifted),
        "shifted_rhs_loss_upper_m": str(loss),
        "negative_details": neg,
        "n_interval_s_inverse": envelope["n_interval_s_inverse"],
        "delay_interval_s": envelope["delay_interval_s"],
        "gates": {
            "information_boxes": positive and center > 0,
            "shifted_triples": positive and shifted > 0,
        },
        "noncertified_meaning": "insufficient bound, not proof of a safe joint command or failed physical operation",
        "physical_or_sensor_performance_claim": False,
    }
    result["result_sha256"] = identity(result)
    return result


def check_stress(spec):
    index = spec["state_index"]
    shift = tuple(Q(x) for x in spec["shift"])
    state = tuple(x + dx for x, dx in zip(STATES[index], shift, strict=True))
    pair = tuple(spec["pair"])
    command = next(u for ids, u in PAIRS if ids == pair)
    d, t = Q(spec["delay_s"]), Q(spec["time_s"])
    require(index in pair and d >= 0 and 0 <= t <= d + 1 and d + 1 <= 3, "Stress timing/membership")
    phi, _ = maps(t, t)
    current = tuple(dot(row, state) for row in phi)
    if t > d:
        _, g = maps(t - d, t - d)
        current = tuple(x + dot(row, command) for x, row in zip(current, g, strict=True))
    initial = geometry(tuple(I.value(x) for x in state))
    status = geometry(current)
    return {
        "name": spec["name"],
        "initial_state": list(map(str, state)),
        "shift": list(map(str, shift)),
        "pair": list(pair),
        "command": list(map(str, command)),
        "initial_status": initial,
        "enclosure_at_time": [x.payload() for x in current],
        "time_s": str(t),
        "delay_s": str(d),
        "status": status,
        "admissible_stress_realization": initial == "contained"
        and sum(x * x for x in command) <= U * U,
        "fixed_command_counterexample": initial == "contained" and status == "outside",
        "scope": "This named stress realization only; not within a claimed smaller certified family and not proof of absence of other pair commands",
    }
