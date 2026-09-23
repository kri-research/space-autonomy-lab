"""Executable numerical checks of the baseline's stated mathematical constants.
Uses independently enclosed HCW matrices and interval LDL positivity tests.
No theorem is inferred from a successful optimizer or from simulation agreement.
"""

import numpy as np
from adjudication.interval import iv, ZERO, ONE
from adjudication.flow import Model, propagate_schedule
from .common import (
    A,
    B,
    K,
    P,
    GAMMA,
    ALPHA,
    U_MAX,
    Tube,
    SENSOR,
    W_COMPONENT,
    MODEL_COMPONENT,
    NUMERIC_COMPONENT,
    model_remainder_bound,
    absolute_maps,
)


def imat(m):
    return [[iv(float(x)) for x in row] for row in m]


def transpose(m):
    return [list(x) for x in zip(*m, strict=True)]


def mul(a, b):
    return [
        [sum((x * y for x, y in zip(row, col, strict=True)), ZERO) for col in transpose(b)]
        for row in a
    ]


def add(a, b):
    return [[x + y for x, y in zip(r, s, strict=True)] for r, s in zip(a, b, strict=True)]


def neg(a):
    return [[-v for v in row] for row in a]


def scale(a, c):
    return [[v * iv(c) for v in row] for row in a]


def ldl_positive(m):
    n = len(m)
    lower = [[ZERO for _ in range(n)] for _ in range(n)]
    d = []
    for j in range(n):
        pivot = m[j][j] - sum((lower[j][k].square() * d[k] for k in range(j)), ZERO)
        if pivot.lo <= 0:
            return False, [v.lo for v in d] + [pivot.lo]
        d.append(pivot)
        lower[j][j] = ONE
        for i in range(j + 1, n):
            lower[i][j] = (
                m[i][j] - sum((lower[i][k] * lower[j][k] * d[k] for k in range(j)), ZERO)
            ) / pivot
    return True, [v.lo for v in d]


def enclosed_maps():
    acols = []
    bcols = []
    for j in range(6):
        x = [float(j == k) for k in range(4)]
        u = [float(j == k + 4) for k in range(2)]
        arcs = propagate_schedule(Model("hcw"), x, [(0, 1, u)])
        (acols if j < 4 else bcols).append(list(arcs[-1].point(1).coordinates))
    return transpose(acols), transpose(bcols)


def check_constants(tube=None):
    tube = tube or Tube(SENSOR, W_COMPONENT + MODEL_COMPONENT + NUMERIC_COMPONENT)
    p = imat(P)
    ai, bi = enclosed_maps()
    ki = imat(K)
    f = add(ai, mul(bi, ki))
    contraction = add(scale(p, iv(GAMMA).square()), neg(mul(mul(transpose(f), p), f)))
    assertions = {}
    assertions["positive_P"], pivots = ldl_positive(p)
    assertions["contraction"], decay_pivots = ldl_positive(contraction)
    constraints = [
        ("input", K, tube.support_U),
        ("hold_speed", np.eye(4)[2:, :], tube.support_V),
        ("hold_ellipse", np.diag([0.5, 1.0 / 3.0]) @ np.eye(4)[:2, :], tube.support_E),
    ]
    supports = {}
    for name, c, bound in constraints:
        ci = imat(c)
        matrix = add(scale(p, iv(float(bound)).square()), neg(mul(transpose(ci), ci)))
        valid, piv = ldl_positive(matrix)
        assertions[name + "_support"] = valid
        supports[name] = piv
    from .common import H

    for i, (row, bound) in enumerate(zip(H, tube.support_A, strict=True)):
        c = np.r_[row, 0.0, 0.0][None, :]
        ci = imat(c)
        assertions["approach_support_" + str(i)] = ldl_positive(
            add(scale(p, iv(float(bound)).square()), neg(mul(transpose(ci), ci)))
        )[0]
    state_max = [150.0, 150.0, 3.0, 3.0]
    numerical_box = []
    for i in range(4):
        aerr = sum(
            max(abs(ai[i][j].lo - A[i, j]), abs(ai[i][j].hi - A[i, j])) * state_max[j]
            for j in range(4)
        )
        berr = sum(
            max(abs(bi[i][j].lo - B[i, j]), abs(bi[i][j].hi - B[i, j])) * U_MAX for j in range(2)
        )
        numerical_box.append(aerr + berr)
    from .common import radius_for_box

    numerical_p_bound = radius_for_box(numerical_box)
    assertions["matrix_error_within_reserved_P_radius"] = numerical_p_bound < 1.0e-9
    assertions["terminal_invariance"] = GAMMA * ALPHA + tube.delta < ALPHA
    terminal_u = ALPHA * tube.support_U + tube.input_error
    terminal_v = ALPHA * tube.support_V
    x_max = ALPHA * np.sqrt(np.linalg.inv(P)[0, 0])
    n = 0.0011313666536110223
    drift = 3 * n * n * x_max + 4 * n * terminal_v
    terminal_acc = terminal_u + 2**0.5 * tube.disturbance_component + drift
    assertions["terminal_action"] = terminal_u < U_MAX
    assertions["terminal_continuous_speed"] = terminal_v + terminal_acc < 0.05
    assertions["terminal_continuous_position"] = ALPHA * tube.support_E + 0.5 * 0.006 < 1.0
    assertions["nonlinear_remainder"] = model_remainder_bound() < MODEL_COMPONENT
    assertions["comparison_exponential_encloses_maps"] = all(
        absolute_maps()[0][i, j] >= max(abs(ai[i][j].lo), abs(ai[i][j].hi))
        for i in range(4)
        for j in range(4)
    )
    # Outward intervals for near-zero entries can exceed the exact-zero comparison
    # coefficients by roundoff; the observer explicitly reserves 1e-10 per step.
    if not assertions["comparison_exponential_encloses_maps"]:
        assertions["comparison_exponential_with_reserved_roundoff"] = all(
            absolute_maps()[0][i, j] + 1.0e-10 >= max(abs(ai[i][j].lo), abs(ai[i][j].hi))
            for i in range(4)
            for j in range(4)
        )
        del assertions["comparison_exponential_encloses_maps"]
    return {
        "passed": all(assertions.values()),
        "assertions": assertions,
        "P": P.tolist(),
        "K": K.tolist(),
        "gamma": GAMMA,
        "alpha": ALPHA,
        "P_LDL_lower_pivots": pivots,
        "decay_LDL_lower_pivots": decay_pivots,
        "steady_error_P_radius": tube.steady_radius,
        "one_step_error_P_radius": tube.delta,
        "matrix_discretization_reserved_P_radius": numerical_p_bound,
        "terminal_control_norm_bound": terminal_u,
        "terminal_continuous_speed_bound": terminal_v + terminal_acc,
        "gravity_linearization_remainder_norm_bound": model_remainder_bound(),
        "scope": "mathematical checks under bounded state/observation/disturbance domain; not proof of optimizer or floating-point feedback implementation",
    }
