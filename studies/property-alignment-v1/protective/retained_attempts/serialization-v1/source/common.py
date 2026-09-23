"""Shared declared information, HCW dynamics and conservative tube constants.
All baseline arms receive the same timestamped information. No latent state API.
"""

from dataclasses import dataclass
from functools import lru_cache
from itertools import product
from fractions import Fraction as Q
import math
import numpy as np
from scipy.linalg import expm, solve_discrete_lyapunov

N = 0.0011313666536110223
MU = 398600441800000.0
RADIUS = 6778137.0
TARGET = np.array([0.0, -30.0, 0.0, 0.0])
AC = np.array(
    [
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [3 * N * N, 0.0, 0.0, 2 * N],
        [0.0, 0.0, -2 * N, 0.0],
    ]
)
BC = np.array([[0.0, 0.0], [0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
H = np.array([[0.0, -1.0], [0.0, 1.0], [1.0, 0.1], [-1.0, 0.1]])
BAND = np.array([100.0, -30.0, 0.0, 0.0])
ELLIPSE = np.diag([0.5, 1.0 / 3.0])
U_MAX = 0.02
SENSOR = np.array([0.01, 0.01, 0.001, 0.001])
W_COMPONENT = 0.00005
MODEL_COMPONENT = 1.0e-7
NUMERIC_COMPONENT = 1.0e-9
CHORD_MARGIN = 0.006
CHECK_MARGIN = 1.0e-5


@lru_cache(maxsize=20)
def matrices(duration=1.0):
    if not math.isfinite(duration) or duration < 0 or duration > 2:
        raise ValueError("Only bounded zero to two second maps are supported")
    m = np.zeros((6, 6))
    m[:4, :4] = AC
    m[:4, 4:] = BC
    e = expm(m * duration)
    return e[:4, :4], e[:4, 4:]


@lru_cache(maxsize=8)
def absolute_maps(duration=1.0):
    """Outward comparison-system exponential for arbitrary bounded disturbance.
    Positive exact-rational Taylor sum with scalar norm remainder; not abs(expm(A)).
    """
    t = Q(duration)
    if not 0 <= t <= 2:
        raise ValueError("Comparison map interval")
    m = np.zeros((6, 6))
    m[:4, :4] = np.abs(AC)
    m[:4, 4:] = np.abs(BC)
    q = [[Q(float(v)) * t for v in row] for row in m]
    term = [[Q(i == j) for j in range(6)] for i in range(6)]
    total = [r.copy() for r in term]
    for k in range(1, 25):
        term = [
            [sum(term[i][a] * q[a][j] for a in range(6)) / k for j in range(6)] for i in range(6)
        ]
        total = [[total[i][j] + term[i][j] for j in range(6)] for i in range(6)]
    norm = max(sum(row) for row in q)
    # norm <= 2.01; exp(norm)<8. The tail is bounded by exp(norm) norm^25/25!.
    if norm > Q(201, 100):
        raise ValueError("Comparison matrix outside proven remainder domain")
    rem = 8 * norm**25 / math.factorial(25)
    out = np.array([[math.nextafter(float(v + rem), math.inf) for v in row] for row in total])
    return out[:4, :4], out[:4, 4:]


A, B = matrices()
K = np.array([[-0.01 - 3 * N * N, 0.0, -0.2, -2 * N], [0.0, -0.01, 2 * N, -0.2]])
F = A + B @ K
P = solve_discrete_lyapunov(F.T, np.diag([0.01, 0.01, 1.0, 1.0]))
P = 0.5 * (P + P.T)
ROOT_P = np.linalg.cholesky(P).T
ROOT_INV = np.linalg.inv(ROOT_P)
GAMMA = 0.98
ALPHA = 0.075


def corners(bounds):
    return np.array(list(product(*[(-float(v), float(v)) for v in bounds])))


def pnorm(vector):
    return float(np.linalg.norm(ROOT_P @ np.asarray(vector)))


def radius_for_box(error):
    # Tiny arithmetic allowance is independently checked against rational forms.
    return max(pnorm(v) for v in corners(error)) + 1.0e-12


def validate_vector(value, length, name):
    result = np.asarray(value, dtype=float)
    if result.shape != (length,) or not np.all(np.isfinite(result)):
        raise ValueError("Invalid " + name)
    return result


@dataclass(frozen=True)
class Observation:
    measured_at: int
    received_at: int
    value: tuple
    error: tuple
    kind: str = "deterministic_interval"

    def __post_init__(self):
        if type(self.measured_at) is not int or type(self.received_at) is not int:
            raise ValueError("Integer sample epochs required")
        if self.measured_at < 0 or self.received_at < self.measured_at:
            raise ValueError("Packet chronology")
        validate_vector(self.value, 4, "observation")
        if np.any(validate_vector(self.error, 4, "error") < 0):
            raise ValueError("Negative bound")
        if self.kind not in ("ideal", "deterministic_interval", "covariance_only"):
            raise ValueError("Unknown information semantics")


@dataclass(frozen=True)
class Information:
    decision_at: int
    application_at: int
    estimate: np.ndarray
    error: np.ndarray
    deterministic: bool
    current_estimate: np.ndarray
    current_error: np.ndarray
    pending: tuple

    def __post_init__(self):
        for name in ("estimate", "error", "current_estimate", "current_error"):
            object.__setattr__(self, name, validate_vector(getattr(self, name), 4, name).copy())
        if np.any(self.error < 0) or np.any(self.current_error < 0):
            raise ValueError("Negative bound")
        if type(self.deterministic) is not bool:
            raise ValueError("Boolean evidence status")


def observation_to_information(
    packet,
    decision_at,
    application_at,
    command_history,
    disturbance_component=W_COMPONENT + MODEL_COMPONENT + NUMERIC_COMPONENT,
):
    if (
        not packet.received_at <= decision_at <= application_at
        or application_at - packet.measured_at > 2
    ):
        raise ValueError("Information age or input delay outside declared two-second bound")
    if application_at - decision_at not in (0, 1):
        raise ValueError("Unsupported input delay")
    s = np.asarray(packet.value, dtype=float)
    e = np.asarray(packet.error, dtype=float)
    current = None
    current_e = None
    pending = []
    for t in range(packet.measured_at, application_at):
        if t == decision_at:
            current = s.copy()
            current_e = e.copy()
        if t not in command_history:
            raise ValueError("Missing queued/executed command")
        u = validate_vector(command_history[t], 2, "held command")
        if np.linalg.norm(u) > U_MAX + 1.0e-12:
            raise ValueError("Command history exceeds bound")
        s = A @ s + B @ u
        aa, bb = absolute_maps(1.0)
        e = aa @ e + bb @ np.full(2, disturbance_component) + 1.0e-10
        if t >= decision_at:
            pending.append((t, t + 1, u.tolist()))
    if application_at == decision_at:
        current = s.copy()
        current_e = e.copy()
    if current is None:
        raise ValueError("Decision precedes observation")
    return Information(
        decision_at,
        application_at,
        s,
        e,
        packet.kind != "covariance_only",
        current,
        current_e,
        tuple(pending),
    )


def maximum_prediction_error(
    sensor=SENSOR,
    age_and_delay=2,
    disturbance_component=W_COMPONENT + MODEL_COMPONENT + NUMERIC_COMPONENT,
):
    e = np.asarray(sensor, dtype=float)
    aa, bb = absolute_maps(1.0)
    for _ in range(age_and_delay):
        e = aa @ e + bb @ np.full(2, disturbance_component) + 1.0e-10
    return e


@dataclass
class Tube:
    sensor_error: np.ndarray
    disturbance_component: float
    max_age_delay: int = 2

    def __post_init__(self):
        self.sensor_error = validate_vector(self.sensor_error, 4, "sensor bound")
        if self.disturbance_component < 0 or not math.isfinite(self.disturbance_component):
            raise ValueError("Bad disturbance")
        self.estimate_error = maximum_prediction_error(
            self.sensor_error, self.max_age_delay, self.disturbance_component
        )
        eta = corners(self.estimate_error)
        self.input_error = max(float(np.linalg.norm(K @ v)) for v in eta) + 1.0e-12
        _, bb = absolute_maps(1.0)
        force_box = bb @ np.full(2, self.disturbance_component)
        self.delta = (
            max(pnorm(B @ K @ v) for v in eta) + max(pnorm(w) for w in corners(force_box)) + 1.0e-9
        )
        self.steady_radius = self.delta / (1 - GAMMA)
        self.support_A = np.linalg.norm(H @ ROOT_INV[:2, :], axis=1) * 1.000001
        self.support_E = float(np.linalg.norm(ELLIPSE @ ROOT_INV[:2, :], 2)) * 1.000001
        self.support_V = float(np.linalg.norm(ROOT_INV[2:, :], 2)) * 1.000001
        self.support_U = float(np.linalg.norm(K @ ROOT_INV, 2)) * 1.000001
        self.valid_terminal = (
            self.steady_radius < ALPHA and ALPHA * self.support_U + self.input_error < U_MAX
        )

    def radii(self, r0, length):
        out = [float(r0)]
        for _ in range(length):
            out.append(math.nextafter(GAMMA * out[-1] + self.delta, math.inf))
        return np.asarray(out)

    def check_information(self, info):
        return (
            info.deterministic
            and np.all(info.error <= self.estimate_error + 1.0e-8)
            and self.valid_terminal
        )


def model_remainder_bound(relative_radius=150.0):
    # Central-gravity Hessian norm <=24 mu/r^4; half multiplies the quadratic remainder.
    return 12 * MU * relative_radius**2 / (RADIUS - relative_radius) ** 4


def uncertain_ranges(center, error, command, disturbance_component, duration=1.0):
    """Continuous enclosures of HCW with arbitrary bounded perturbations.
    Nominal held-input Taylor arcs plus comparison-system error at interval ends.
    """
    from adjudication.interval import Box, Interval
    from adjudication.flow import Model, propagate_schedule

    arcs = propagate_schedule(
        Model("hcw"), np.asarray(center).tolist(), [(0, duration, np.asarray(command).tolist())]
    )
    result = []
    for arc in arcs:
        aa, bb = absolute_maps(float(arc.end))
        e = aa @ np.asarray(error) + bb @ np.full(2, disturbance_component) + 1.0e-10
        b = arc.range(arc.start, arc.end)
        result.append(
            Box(
                tuple(
                    v + Interval(-float(w), float(w)) for v, w in zip(b.coordinates, e, strict=True)
                )
            )
        )
    return result


def union_box_inside(box):
    x, y, _, _ = box.coordinates
    # Online inequalities independently expressed; no offline event labels.
    approach = y.lo >= -100 and y.hi <= -30 and (x + y / 10).hi <= 0 and (-x + y / 10).hi <= 0
    ellipse = ((x / 2).square() + ((y + 30) / 3).square()).hi <= 1
    return approach or ellipse


def pending_safe(info, tube):
    if not info.pending:
        return info.application_at == info.decision_at
    if len(info.pending) != 1:
        return False
    a, b, u = info.pending[0]
    if a != info.decision_at or b != info.application_at:
        return False
    return all(
        union_box_inside(box)
        for box in uncertain_ranges(
            info.current_estimate, info.current_error, u, tube.disturbance_component
        )
    )
