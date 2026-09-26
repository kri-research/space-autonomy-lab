"""Separately written nonlinear relative ODE and linear reference.

No production plant, enclosure, observer or assurance function is imported.
The reference uses continuous rotating-frame force, versus the plant's sampled
inertial force. Their small difference is bounded and explicitly tested.
"""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm

MU = 398600441800000.0
OMEGA = 11 / 10000
RADIUS = (MU / OMEGA**2) ** (1 / 3)


def nonlinear(initial, schedule, times):
    t = 0.0
    state = np.asarray(initial, dtype=float)
    output = []
    for stop, action, eta, disturbance in schedule:
        force = np.asarray(action) * eta + np.asarray(disturbance)

        def rhs(_, z, force=force):
            x, y, vx, vy = z
            norm = np.hypot(RADIUS + x, y)
            g = MU / norm**3
            return (
                vx,
                vy,
                -g * (RADIUS + x) + MU / RADIUS**2 + OMEGA**2 * x + 2 * OMEGA * vy + force[0],
                -g * y + OMEGA**2 * y - 2 * OMEGA * vx + force[1],
            )

        sol = solve_ivp(
            rhs,
            (t, stop),
            state,
            method="DOP853",
            rtol=2.5e-13,
            atol=1e-13,
            max_step=0.01,
            dense_output=True,
        )
        if not sol.success:
            raise ArithmeticError(sol.message)
        for time in times:
            if t <= time <= stop and (not output or time > output[-1][0]):
                output.append((time, sol.sol(time)))
        state, t = sol.y[:, -1], stop
    return output


def linear(initial, action, duration, eta=1.0, disturbance=(0.0, 0.0)):
    n = OMEGA
    a = np.zeros((5, 5))
    a[0, 2] = a[1, 3] = 1.0
    a[2, 0], a[2, 3], a[3, 2] = 3 * n**2, 2 * n, -2 * n
    a[2:4, 4] = eta * np.asarray(action) + disturbance
    return (expm(a * duration) @ np.array((*initial, 1.0)))[:4]
