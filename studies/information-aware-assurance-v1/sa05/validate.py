"""Record bounded external-dynamics validation before the evaluation freeze."""

import numpy as np

from .dynamics import NUMERIC_POSITION_M, NUMERIC_VELOCITY_MPS, Plant, mismatch_bound
from .reference import nonlinear


def validation():
    rows = []
    for initial, action, eta in [
        ((0, -45, 0, 0), (0, 0), 1),
        ((1, -45, 0.01, -0.02), (0.02, 0), 1),
        ((-2, -35, -0.03, 0.01), (0, -0.02), 0.8),
        ((-7.9, -30.2, 0.1, -0.04), (-0.02, 0), 1),
    ]:
        disturbance = (1e-6, -2e-6)
        p = Plant(initial, eta, disturbance)
        p.advance(200)
        p.advance(700, action)
        p.advance(1200, (-action[0], -action[1]))
        p.advance(4200)
        reference = nonlinear(
            initial,
            [
                (0.2, (0, 0), eta, disturbance),
                (0.7, action, eta, disturbance),
                (1.2, (-action[0], -action[1]), eta, disturbance),
                (4.2, (0, 0), eta, disturbance),
            ],
            [r["at_ms"] / 1000 for r in p.rows],
        )
        errors = np.abs(
            np.array([r["state"] for r in p.rows]) - np.array([r[1] for r in reference])
        )
        rows.append(
            dict(
                initial=initial,
                action=action,
                effectiveness=eta,
                samples=len(p.rows),
                max_position_error_m=float(errors[:, :2].max()),
                max_velocity_error_mps=float(errors[:, 2:].max()),
            )
        )
    return dict(
        schema="iaa-sa05-adapter-validation/1",
        basilisk_version="2.12.0",
        rows=rows,
        passed=all(
            r["max_position_error_m"] < NUMERIC_POSITION_M / 10
            and r["max_velocity_error_mps"] < NUMERIC_VELOCITY_MPS
            for r in rows
        ),
        analytic_nonlinear_and_hold_acceleration_bound=mismatch_bound(),
        declared_additive_acceleration_bound=1e-5,
        injected_component_disturbance_max=2e-6,
        numerical_position_allowance_m=NUMERIC_POSITION_M,
        numerical_velocity_allowance_mps=NUMERIC_VELOCITY_MPS,
        numerical_not_machine_proof=True,
        external_replication=False,
        physical_validation=False,
    )
